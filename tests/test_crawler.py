# test_crawler.py - offline tests for wow-story-crawler. No network:
# parsers run on fixture HTML, the fetcher runs in dry-run/offline/cache
# modes, and the graph builder runs on synthetic facts.
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storycrawler import builder, graph          # noqa: E402
from storycrawler.fetcher import Fetcher        # noqa: E402
from storycrawler.models import QuestFact, SeedChapter  # noqa: E402
from storycrawler.parsers import (parse_foreverdb, parse_rxp_lines,  # noqa: E402
                                  parse_wiki_chain, parse_wowhead)

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "crawler"
fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails += 1


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


# --- parsers ----------------------------------------------------------
f = parse_foreverdb(147, load("foreverdb_147.html"),
                    "https://pd.zroot.it/forever/quests/147")
check("foreverdb: name", f.name == "Manhunt")
check("foreverdb: before", f.before == [123])
check("foreverdb: after", f.after == [239])
check("foreverdb: reqlevel", f.reqlevel == 7)
empty = parse_foreverdb(1, "<html><h1>X</h1></html>", "u")
check("foreverdb: no sections -> empty links, no guess",
      empty.before == [] and empty.after == [] and empty.reqlevel is None)

w = parse_wowhead(147, load("wowhead_147.html"),
                  "https://www.wowhead.com/classic/quest=147")
check("wowhead: series predecessor", w.before == [123])
check("wowhead: series successor", w.after == [239])
check("wowhead: reqlevel", w.reqlevel == 7)

check("wiki: ordered deduped ids",
      parse_wiki_chain(load("wiki_chain.html")) == [123, 147, 239])

rxp = parse_rxp_lines(load("guide.lua"))
by_id = {x.qid: x for x in rxp}
check("rxp: accept order links", by_id[123].after == [147])
check("rxp: faction condition", by_id[147].faction == "Alliance")
check("rxp: class condition", by_id[999].class_ == "Warrior")

# --- fetcher: offline / dry-run / cache, never network ----------------
with tempfile.TemporaryDirectory() as td:
    cache = pathlib.Path(td)
    url = "https://pd.zroot.it/forever/quests/147"
    off = Fetcher(cache, offline=True)
    check("fetcher: offline miss is None", off.fetch("foreverdb", url) is None)
    dry = Fetcher(cache, dry_run=True)
    check("fetcher: dry-run fetches nothing", dry.fetch("foreverdb", url) is None)
    check("fetcher: dry-run records plan", dry.planned == [url])
    check("fetcher: dry-run wrote no cache", not list(cache.glob("*.html")))
    dry._cache_file("foreverdb", url).write_text("<h1>cached</h1>",
                                                 encoding="utf-8")
    check("fetcher: cache hit beats dry-run",
          dry.fetch("foreverdb", url) == "<h1>cached</h1>")

# --- graph: merge, close, linearise, gaps -----------------------------
facts = [
    QuestFact(239, "foreverdb", name="Westbrook", before=[147], reqlevel=6),
    QuestFact(147, "foreverdb", name="Manhunt", before=[123], after=[239],
              reqlevel=7),
    QuestFact(123, "foreverdb", name="The Collector", after=[147],
              reqlevel=7),
    QuestFact(147, "wowhead-classic", name="Manhunt!", reqlevel=9),
    QuestFact(999, "foreverdb", name="Class Trial", class_="Warrior",
              before=[239]),
]
merged = graph.merge_facts(facts)
check("merge: higher trust wins name", merged[147].name == "Manhunt")
check("merge: conflict recorded",
      any("name" in c for c in merged[147].conflicts))
check("merge: sources listed",
      merged[147].sources == ["foreverdb", "wowhead-classic"])

chapter = SeedChapter(id="elwynn_tail", name="Elwynn Tail",
                      faction="Alliance", race="Human", seeds=[147])
members = graph.expand_from_seeds(merged, chapter.seeds, set())
check("closure: walks both directions from mid seed",
      members == {123, 147, 239})
check("closure: class quest excluded by default", 999 not in members)
members_cls = graph.expand_from_seeds(merged, [239], set(),
                                      include_class=True)
check("closure: class quest opt-in", 999 in members_cls)

ordered, cyc = graph.topo_order(merged, members, chapter.seeds)
check("topo: linear order", ordered == [123, 147, 239] and cyc == [])
shape = graph.chapter_shape(merged, chapter, members, ordered)
check("shape: single entry/exit",
      shape["entry"] == 123 and shape["exit"] == 239
      and shape["heads"] == [123] and shape["tails"] == [239])

cyc_merged = graph.merge_facts([
    QuestFact(1, "foreverdb", before=[2]), QuestFact(2, "foreverdb",
                                                     before=[1])])
_o, cyc = graph.topo_order(cyc_merged, {1, 2}, [1])
check("topo: cycle detected, not hidden", cyc == [1, 2])

gap_merged = graph.merge_facts([
    QuestFact(147, "foreverdb", name="Manhunt", before=[123])])
gshape = builder.build_chapters(gap_merged, [chapter])[0]
gaps = graph.find_gaps(gap_merged, [chapter], [gshape], set(gap_merged))
check("gaps: uncrawled predecessor reported",
      any(g.kind == "missing_page" and "123" in g.detail for g in gaps))
check("gaps: referenced ids feed next crawl round",
      graph.referenced_ids(gap_merged, {147}) == {123})

# --- seeds file + addon diff (real repo data, still offline) ----------
chapters = builder.load_seeds()
ids = [c.id for c in chapters]
check("seeds: loads with unique chapters", len(ids) == len(set(ids)))
check("seeds: all races present",
      {c.race for c in chapters if c.race} >= {
          "Human", "Dwarf", "Night Elf", "Gnome",
          "Orc", "Undead", "Tauren", "Troll"})
check("seeds: both factions plus neutral",
      {c.faction for c in chapters} == {"Alliance", "Horde", "Neutral"})
elwynn = next(c for c in chapters if c.id == "elwynn")
check("seeds: elwynn entry/exit pinned",
      elwynn.entry == elwynn.seeds[0] and elwynn.exit == 239
      and 147 in elwynn.seeds)

# Addon catalogue checks run only when the sibling MainStoryGuide repo is
# present (the dev setup); standalone clones exercise diff on fixtures.
ADDON_DATA = ROOT.parent / "MainStoryGuide" / "MainStoryGuide" / "Data_Human.lua"
if ADDON_DATA.exists():
    addon = builder.load_addon_catalogue([ADDON_DATA])
    check("catalogue: human chain parsed", addon.get("elwynn", [])[-3:]
          == [123, 147, 239])
else:
    addon = {"elwynn": [3903, 123, 147, 239]}
    print("SKIP catalogue: sibling MainStoryGuide not present")
self_shapes = [{"id": cid, "quests": qs} for cid, qs in addon.items()]
check("diff: identical catalogue agrees",
      builder.diff_catalogue(self_shapes, addon)
      == ["Catalogue and crawl agree on every shared chain."])
drift = [{"id": "elwynn", "quests": [3903]}]
check("diff: drift reported",
      any("elwynn" in line for line in builder.diff_catalogue(drift, addon)))

draft = builder.emit_lua_draft(merged, shape | {"zone": "Elwynn Forest"})
check("emit-lua: leads on entry and exit", draft.count('kind = "lead"') == 2)
check("emit-lua: never invents coords", "map = TODO" in draft
      and "x =" not in draft)

print()
print("ALL TESTS PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
