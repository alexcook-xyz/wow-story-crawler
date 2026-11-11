# test_crawler.py - offline tests for wow-story-crawler. No network:
# parsers run on fixture HTML, the fetcher runs in dry-run/offline/cache
# modes, and the graph builder runs on synthetic facts.
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storycrawler import builder, emit_html, graph  # noqa: E402
from storycrawler.fetcher import Fetcher        # noqa: E402
from storycrawler.models import GAP_KINDS, QuestFact, SeedChapter  # noqa: E402
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
check("foreverdb: quest level and zone", f.level == 10
      and f.zone == "Elwynn Forest")
check("foreverdb: faction gate", f.faction == "Alliance")
check("foreverdb: giver card", f.giver == "Marshal Dughan"
      and f.turnin == "Marshal Dughan")
check("foreverdb: map and coords", f.map_id == 1429
      and f.gx == 42.1 and f.gy == 65.9
      and f.tx == 42.1 and f.ty == 65.9)
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
check("closure: before-only by default (prereq joins, successor does not)",
      members == {123, 147})
members_both = graph.expand_from_seeds(merged, chapter.seeds, set(),
                                       direction="both")
check("closure: both directions on request", members_both == {123, 147, 239})
check("closure: class quest excluded by default", 999 not in members_both)
members_cls = graph.expand_from_seeds(merged, [239], set(),
                                      include_class=True, direction="both")
check("closure: class quest opt-in", 999 in members_cls)

ordered, cyc = graph.topo_order(merged, members_both, chapter.seeds)
check("topo: linear order", ordered == [123, 147, 239] and cyc == [])
shape = graph.chapter_shape(merged, chapter, members_both, ordered)
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
pairs = builder.build_chapters(gap_merged, [chapter])
check("build: chapter stays paired with its own shape",
      len(pairs) == 1 and pairs[0][0].id == "elwynn_tail"
      and pairs[0][1]["id"] == "elwynn_tail")
gshape = pairs[0][1]
gaps = graph.find_gaps(gap_merged, [chapter], [gshape], set(gap_merged))
check("gaps: uncrawled predecessor reported",
      any(g.kind == "missing_page" and "123" in g.detail for g in gaps))
check("gaps: referenced ids feed next crawl round",
      graph.referenced_ids(gap_merged, {147}) == {123})

chain = graph.merge_facts([
    QuestFact(1, "foreverdb", name="One", after=[2]),
    QuestFact(2, "foreverdb", name="Two", before=[1], after=[3]),
    QuestFact(3, "foreverdb", name="Three", before=[2], after=[9]),
    QuestFact(9, "foreverdb", name="Nine", before=[3]),
])
ch3 = SeedChapter(id="trio", name="Trio", faction="Alliance",
                  seeds=[1, 2, 3], entry=1, exit=3, next_chapter=None)
mem3 = graph.expand_from_seeds(chain, ch3.seeds, set())
o3, _c3 = graph.topo_order(chain, mem3, ch3.seeds)
sh3 = graph.chapter_shape(chain, ch3, mem3, o3)
check("shape: curated entry/exit kept",
      sh3["entry"] == 1 and sh3["exit"] == 3)
ch3m = SeedChapter(id="trio", name="Trio", faction="Alliance",
                   seeds=[1, 2, 3], entry=2, exit=2)
shm = graph.chapter_shape(chain, ch3m, mem3, o3)
check("shape: mid-chain curated entry/exit honored",
      shm["entry"] == 2 and shm["exit"] == 2)
g3 = graph.find_gaps(chain, [ch3], [sh3], set(chain))
check("gaps: tail continuation reported",
      any(g.kind == "tail_continues" and g.qid == 3
          and "9" in g.detail for g in g3))
check("gaps: no false exit_continues on true exit",
      not any(g.kind == "exit_continues" for g in g3))
gm = graph.find_gaps(chain, [ch3m], [shm], set(chain))
check("gaps: mid-thread exit flagged",
      any(g.kind == "exit_continues" and g.qid == 2 for g in gm))

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
rich = graph.merge_facts([QuestFact(
    147, "foreverdb", name="Manhunt", before=[123],
    reqlevel=7, zone="Elwynn Forest", giver="Marshal Dughan",
    map_id=1429, gx=42.1, gy=65.9)])
rshape = {"id": "elwynn_tail", "name": "Elwynn Tail", "race": "Human",
          "zone": "Elwynn Forest", "quests": [147]}
rdraft = builder.emit_lua_draft(rich, rshape)
check("emit-lua: fills sourced giver/coords",
      'giver = "Marshal Dughan"' in rdraft and "map = 1429" in rdraft
      and "x = 42.1, y = 65.9" in rdraft)

# --- attunement chapters: no level cutoff, explicit cutoff gaps -------
att = {1: QuestFact(1, "foreverdb", name="Key Start", after=[2], reqlevel=58),
       2: QuestFact(2, "foreverdb", name="Key Mid", before=[1], after=[3],
                    reqlevel=60),
       3: QuestFact(3, "foreverdb", name="Gate Finale", before=[2],
                    reqlevel=62)}
amerged = graph.merge_facts(list(att.values()))
check("attunement: story expansion cuts above 60",
      graph.expand_from_seeds(amerged, [3], set()) == set())
check("attunement: max_level=None lifts the cutoff",
      graph.expand_from_seeds(amerged, [3], set(), max_level=None)
      == {1, 2, 3})
a_ch = SeedChapter.from_json({"id": "gate", "name": "Gate", "faction":
                              "Neutral", "seeds": [3],
                              "gate": "Test Raid"})
s_ch = SeedChapter.from_json({"id": "story", "name": "Story", "faction":
                              "Neutral", "seeds": [2, 3]})
apairs = builder.build_chapters(amerged, [a_ch, s_ch])
ashapes = {c.id: s for c, s in apairs}
check("attunement: chapter keeps the >60 finale",
      ashapes["gate"]["quests"] == [1, 2, 3]
      and ashapes["gate"]["gate"] == "Test Raid")
check("attunement: story chapter still cut at 60",
      ashapes["story"]["quests"] == [1, 2])
agaps = graph.find_gaps(amerged, [c for c, _ in apairs],
                        [s for _, s in apairs], set(amerged))
check("attunement: cut thread reported on story chapter only",
      [g.kind for g in agaps if g.chapter == "story"
       and g.kind == "level_cutoff"] == ["level_cutoff"]
      and not [g for g in agaps if g.chapter == "gate"
               and g.kind == "level_cutoff"])
for bad in ({"gate": "Raid", "next_chapter": "nonexistent"},):
    try:
        SeedChapter.from_json({"id": "x", "name": "X", "faction": "Neutral",
                               **bad})
        check(f"attunement: rejects {bad}", False)
    except ValueError:
        check(f"attunement: rejects {bad}", True)

# --- decisions: one mechanism, identified by kind and quests --------------
emerged = graph.merge_facts(list(att.values()) + [
    QuestFact(4, "foreverdb", name="Side Thread", reqlevel=50)])


def gaps_with(decs):
    ch = SeedChapter.from_json({"id": "story", "name": "Story",
                                "faction": "Neutral", "seeds": [2, 3, 4],
                                "explained": decs})
    pp = builder.build_chapters(emerged, [ch])
    shapes = [s for _, s in pp]
    return graph.find_gaps(emerged, [ch], shapes, set(emerged)), shapes


base_gaps, _ = gaps_with([])
heads = [g.members for g in base_gaps if g.kind == "open_head"]
check("decisions: story chapter has an open head to decide", heads != [])
dec_gaps, dec_shapes = gaps_with([{"kind": "open_head",
                                   "qids": list(heads[0]),
                                   "reason": "parallel threads"}])
check("decisions: matching decision explains that head only",
      [g.explained for g in dec_gaps if g.kind == "open_head"]
      == ["parallel threads"]
      and any(g.explained is None for g in dec_gaps
              if g.kind == "level_cutoff"))
stale_gaps, _ = gaps_with([{"kind": "open_head", "qids": [999],
                            "reason": "x"}])
check("decisions: a decision matching no gap is stale and leaves the head open",
      [g.explained for g in stale_gaps if g.kind == "open_head"] == [None]
      and any(g.kind == "stale_decision" for g in stale_gaps))
hand = graph.find_gaps(
    graph.merge_facts([QuestFact(1, "foreverdb", name="A", after=[2]),
                       QuestFact(2, "foreverdb", name="B", before=[1])]),
    [SeedChapter.from_json({"id": "a", "name": "A", "faction": "Neutral",
                            "seeds": [1]}),
     SeedChapter.from_json({"id": "b", "name": "B", "faction": "Neutral",
                            "seeds": [2]})],
    [{"id": "a", "quests": [1], "entry": 1, "exit": 1, "heads": [1],
      "tails": [1], "next_chapter": None},
     {"id": "b", "quests": [2], "entry": 2, "exit": 2, "heads": [2],
      "tails": [2], "next_chapter": None}], {1, 2})
hq = graph.merge_facts([QuestFact(1, "foreverdb", name="A", after=[2]),
                        QuestFact(2, "foreverdb", name="B", before=[1])])
hch = [SeedChapter.from_json({"id": "a", "name": "A", "faction": "Neutral",
                              "seeds": [1], "next_chapter": "b"}),
       SeedChapter.from_json({"id": "b", "name": "B", "faction": "Neutral",
                              "seeds": [2], "exclude": [1]})]
hp = builder.build_chapters(hq, hch)
hg = graph.find_gaps(hq, [c for c, _ in hp], [s for _, s in hp], {1, 2})
check("orphan link: declared next_chapter is not a bridge by itself",
      [g.explained for g in hg if g.kind == "orphan_link"] == [None])
bridged = [SeedChapter.from_json({"id": "a", "name": "A", "faction": "Neutral",
                                  "seeds": [1]}),
           SeedChapter.from_json({"id": "b", "name": "B", "faction": "Neutral",
                                  "seeds": [2], "exclude": [1],
                                  "explained": [{"kind": "orphan_link",
                                                 "qids": [1, 2],
                                                 "reason": "bridge from a"}]})]
bg = graph.find_gaps(hq, bridged, [s for _, s in builder.build_chapters(hq, bridged)],
                     {1, 2})
check("orphan link: a decision on its quest pair explains it",
      [g.explained for g in bg if g.kind == "orphan_link"] == ["bridge from a"])

# --- findings 2-4: cutoff honours exclude, class flag, shared members ---
ex_m = graph.merge_facts([QuestFact(1, "foreverdb", name="A", before=[2],
                                    reqlevel=50),
                          QuestFact(2, "foreverdb", name="B", reqlevel=70)])
for label, extra, want in (("no exclude", {}, [2]),
                           ("excluded prereq", {"exclude": [2]}, [])):
    xc = SeedChapter.from_json({"id": "x", "name": "X", "faction": "Neutral",
                                "seeds": [1], **extra})
    xp = builder.build_chapters(ex_m, [xc])
    xg = graph.find_gaps(ex_m, [xc], [s for _, s in xp], set(ex_m))
    check(f"cutoff: {label} -> level_cutoff {want}",
          [g.qid for g in xg if g.kind == "level_cutoff"] == want)
cls_m = graph.merge_facts([QuestFact(1, "foreverdb", name="A", reqlevel=50),
                           QuestFact(2, "foreverdb", name="B", reqlevel=70,
                                     class_="Warrior")])
cls_ch = SeedChapter.from_json({"id": "k", "name": "K", "faction": "Neutral",
                                "seeds": [1, 2]})
for inc, want in ((False, []), (True, [2])):
    kp = builder.build_chapters(cls_m, [cls_ch], inc)
    kg = graph.find_gaps(cls_m, [cls_ch], [s for _, s in kp], set(cls_m),
                         include_class=inc)
    check(f"cutoff: include_class={inc} -> level_cutoff {want}",
          [g.qid for g in kg if g.kind == "level_cutoff"] == want)
sh_m = graph.merge_facts([QuestFact(1, "foreverdb", name="A", after=[2]),
                          QuestFact(2, "foreverdb", name="B")])
sh_ch = [SeedChapter.from_json({"id": "a", "name": "A", "faction": "Neutral",
                                "seeds": [1]}),
         SeedChapter.from_json({"id": "b", "name": "B", "faction": "Neutral",
                                "seeds": [2]}),
         SeedChapter.from_json({"id": "c", "name": "C", "faction": "Neutral",
                                "seeds": [2]})]
sp = builder.build_chapters(sh_m, sh_ch)
sg = graph.find_gaps(sh_m, [c for c, _ in sp], [s for _, s in sp], {1, 2})
check("shared member: quest in two chapters is reported",
      [g.qid for g in sg if g.kind == "shared_member"] == [2])
dec_sh = [SeedChapter.from_json({"id": "a", "name": "A", "faction": "Neutral",
                                "seeds": [1]}),
          SeedChapter.from_json({"id": "b", "name": "B", "faction": "Neutral",
                                 "seeds": [2],
                                 "explained": [{"kind": "shared_member",
                                                "qids": [2],
                                                "reason": "shared starter"}]}),
          SeedChapter.from_json({"id": "c", "name": "C", "faction": "Neutral",
                                 "seeds": [2]})]
dsp = builder.build_chapters(sh_m, dec_sh)
dsg = graph.find_gaps(sh_m, [c for c, _ in dsp], [s for _, s in dsp], {1, 2})
check("shared member: a decision on the owning chapter explains it",
      [g.explained for g in dsg if g.kind == "shared_member"]
      == ["shared starter"])
check("tail into another chapter stays open until decided",
      [g.explained for g in sg if g.kind == "tail_continues"] == [None])
check("tail into another chapter stays open (no automatic hand-off)",
      [g.explained for g in hand if g.kind == "tail_continues"] == [None])
wr = pathlib.Path(tempfile.mkdtemp())
builder.write_outputs(wr, emerged, dec_shapes + [s for _, s in builder.build_chapters(emerged, [a_ch])], dec_gaps)
gtext = (wr / "gaps.md").read_text(encoding="utf-8")
check("explained: gaps.md splits Open and Explained",
      "## Open" in gtext and "## Explained" in gtext
      and "-- explained: parallel threads" in gtext)
check("attunement: storyline.md tags the gate",
      "[attunement: Test Raid]" in (wr / "storyline.md").read_text(
          encoding="utf-8"))
sk = {c.id: c for c in builder.load_seeds()}
check("seeds: attunement chapters carry a gate",
      all(c.gate for c in sk.values() if c.is_attunement)
      and {"onyxia", "horde_onyxia", "mc_attunement", "bwl_attunement",
           "blackrock"} <= {c.id for c in sk.values() if c.is_attunement})
check("seeds: decision kinds are real gap kinds",
      all(dec["kind"] in GAP_KINDS for c in sk.values()
          for dec in c.explained))

# --- regression: bug-hunt findings -----------------------------------
top = graph.merge_facts([QuestFact(3, "foreverdb", name="Finale",
                                   reqlevel=62)])
tch = SeedChapter.from_json({"id": "s", "name": "S", "faction": "Neutral",
                             "seeds": [3]})
tpairs = builder.build_chapters(top, [tch])
tg = graph.find_gaps(top, [tch], [tpairs[0][1]], set(top))
check("cutoff: chapter seeded only above 60 still reports level_cutoff",
      tpairs[0][1]["quests"] == []
      and [g.qid for g in tg if g.kind == "level_cutoff"] == [3])
succ = graph.merge_facts([QuestFact(1, "foreverdb", name="A", after=[2],
                                    reqlevel=50),
                          QuestFact(2, "foreverdb", name="B", reqlevel=70)])
sch = SeedChapter.from_json({"id": "s", "name": "S", "faction": "Neutral",
                             "seeds": [1]})
sg = graph.find_gaps(succ, [sch],
                     [builder.build_chapters(succ, [sch])[0][1]],
                     set(succ))
check("cutoff: >60 successor is tail_continues only, not level_cutoff",
      [g.kind for g in sg if g.kind in ("tail_continues", "level_cutoff")]
      == ["tail_continues"])
base_seed = {"id": "x", "name": "X", "faction": "Neutral"}
for label, bad in (
        ("decision with unknown kind",
         {"explained": [{"kind": "open-head", "qids": [1], "reason": "r"}]}),
        ("decision with no quests",
         {"explained": [{"kind": "open_head", "qids": [], "reason": "r"}]}),
        ("decision with blank reason",
         {"explained": [{"kind": "open_head", "qids": [1], "reason": " "}]}),
        ("decision with an extra key",
         {"explained": [{"kind": "open_head", "qids": [1], "reason": "r",
                         "x": 1}]}),
        ("explained as a mapping", {"explained": {"open_head": "r"}}),
        ("attunement next_chapter", {"gate": "G", "next_chapter": "y"})):
    try:
        SeedChapter.from_json({**base_seed, **bad})
        check(f"validate: rejects {label}", False)
    except ValueError:
        check(f"validate: rejects {label}", True)

# --- cycle gaps pass through the explained mapping --------------------
cm = graph.merge_facts([QuestFact(1, "foreverdb", name="A", before=[2],
                                  after=[2]),
                        QuestFact(2, "foreverdb", name="B", before=[1],
                                  after=[1])])
for decs, want in (
        ([], None),
        ([{"kind": "cycle", "qids": [1], "reason": "known loop"},
          {"kind": "cycle", "qids": [2], "reason": "known loop"}],
         "known loop")):
    cch = SeedChapter.from_json({"id": "c", "name": "C", "faction":
                                 "Neutral", "seeds": [1, 2],
                                 "explained": decs})
    cp = builder.build_chapters(cm, [cch])
    cg = [g for g in graph.find_gaps(cm, [cch], [s for _, s in cp],
                                     set(cm)) if g.kind == "cycle"]
    check(f"cycle: find_gaps reports both members (explained={want!r})",
          sorted(g.qid for g in cg) == [1, 2]
          and all(g.explained == want for g in cg))

# --- shared_ok is retired: unknown keys are rejected -----------------
import json  # noqa: E402
try:
    SeedChapter.from_json({"id": "t", "name": "T", "faction": "Neutral",
                           "shared_ok": ["x"]})
    check("shared_ok: the retired key is rejected", False)
except ValueError:
    check("shared_ok: the retired key is rejected", True)

# --- cutoff reports the whole over-cap chain, not one hop ----------------
deep = graph.merge_facts([QuestFact(1, "foreverdb", name="M", reqlevel=50,
                                    before=[2]),
                          QuestFact(2, "foreverdb", name="A", reqlevel=62,
                                    before=[3]),
                          QuestFact(3, "foreverdb", name="B", reqlevel=70)])
dch = SeedChapter.from_json({"id": "d", "name": "D", "faction": "Neutral",
                             "seeds": [1]})
dp = builder.build_chapters(deep, [dch])
dg = graph.find_gaps(deep, [dch], [s for _, s in dp], set(deep))
check("cutoff: deeper over-cap prerequisite is reported too",
      sorted(g.qid for g in dg if g.kind == "level_cutoff") == [2, 3])

# --- decisions pin head and tail reasons to the quests they cover -----
pm = graph.merge_facts([QuestFact(1, "foreverdb", name="P"),
                        QuestFact(2, "foreverdb", name="Q")])


def pinned(decs):
    pc = SeedChapter.from_json({"id": "p", "name": "P", "faction": "Neutral",
                                "seeds": [1, 2], "explained": decs})
    pp = builder.build_chapters(pm, [pc])
    return [g.explained is not None
            for g in graph.find_gaps(pm, [pc], [s for _, s in pp], set(pm))
            if g.kind in ("open_head", "open_tail")]


check("decisions: heads and tails matched exactly are explained",
      pinned([{"kind": "open_head", "qids": [1, 2], "reason": "r"},
              {"kind": "open_tail", "qids": [1, 2], "reason": "r"}])
      == [True, True])
check("decisions: a head decision naming other quests leaves the head open",
      pinned([{"kind": "open_head", "qids": [1, 9], "reason": "r"},
              {"kind": "open_tail", "qids": [1, 2], "reason": "r"}])
      == [False, True])

# --- gap kinds are checked on construction; report is generated ----------
try:
    graph.Gap("not_a_kind", "x")
    check("Gap: unknown kind is rejected", False)
except ValueError:
    check("Gap: unknown kind is rejected", True)
from storycrawler import report as _report                    # noqa: E402
rep_text = _report.race_report(
    [{"id": "orc_valley_trials", "race": "Orc", "quests": [1, 2],
      "entry": 1, "exit": 2},
     {"id": "elsewhere", "quests": [3], "entry": 3, "exit": 3}],
    [graph.Gap("open_head", "x", None, "orc_valley_trials")], "cmd")
check("report: starter row counts open gaps",
      "| orc_valley_trials | Orc | 2 | 1 -> 2 | 1 | 0 |" in rep_text)
check("report: non-starter chapters are left out",
      "elsewhere" not in rep_text)
check("report: says which chapters still have gaps",
      "Still open: orc_valley_trials 1." in rep_text)

# --- partial crawls keep earlier facts ---------------------------------
old_f = [QuestFact(1, "foreverdb", name="Old"), QuestFact(2, "rxp"),
         QuestFact(3, "foreverdb", name="Keep")]
new_f = [QuestFact(1, "foreverdb", name="Fresh"), QuestFact(4, "foreverdb")]
mf = builder.merge_saved_facts(old_f, new_f)
check("merge_saved_facts: fresh replaces, others kept",
      sorted((f.qid, f.source, f.name) for f in mf)
      == [(1, "foreverdb", "Fresh"), (2, "rxp", None),
          (3, "foreverdb", "Keep"), (4, "foreverdb", None)])

# --- crawl save paths: dry-run leaves facts.json alone ------------------
import contextlib, io, json                                  # noqa: E402
from storycrawler import cli                                  # noqa: E402
cdir = pathlib.Path(tempfile.mkdtemp())
(cdir / "seeds.json").write_text(json.dumps({"version": 1, "about": "t",
    "chapters": [{"id": "t", "name": "T", "faction": "Neutral",
                  "seeds": [999999999]}]}), encoding="utf-8")
(cdir / "out").mkdir()
builder.save_facts([QuestFact(7, "foreverdb", name="Saved")],
                   cdir / "out" / "facts.json")
before = (cdir / "out" / "facts.json").read_bytes()
for mode in ("--dry-run", "--offline"):
    with contextlib.redirect_stdout(io.StringIO()):
        rc = cli.main(["--seeds", str(cdir / "seeds.json"),
                       "--out", str(cdir / "out"), mode, "crawl"])
    kept = [f.qid for f in builder.load_facts(cdir / "out" / "facts.json")]
    check(f"crawl {mode}: exits 0 and keeps saved facts",
          rc == 0 and kept == [7])
    if mode == "--dry-run":
        check("crawl --dry-run: facts.json is byte-identical",
              (cdir / "out" / "facts.json").read_bytes() == before)
with contextlib.redirect_stdout(io.StringIO()):
    cli.main(["--seeds", str(cdir / "seeds.json"),
              "--out", str(cdir / "empty"), "--dry-run", "crawl"])
check("crawl --dry-run: writes no facts.json when none existed",
      not (cdir / "empty" / "facts.json").exists())

# --- emit-html chapters-only map -----------------------------------
# The map shows curated chapters only: quests no chapter references
# render no node and no edge (class lines, profession guides, sides).
syn_graph = {"quests": {"1": {"name": "Alpha", "before": [], "after": ["2"]},
                        "2": {"name": "Beta", "before": ["1"], "after": [],
                              "zone": "Duskwood"}},
             "chapters": [{"id": "c1", "name": "C1", "quests": [1]}]}
syn_html = emit_html.build_html(syn_graph)
check("emit-html: chaptered quest renders", "data-qid='1'" in syn_html)
check("emit-html: quest outside any chapter renders no node",
      "data-qid='2'" not in syn_html)
check("emit-html: edge to outside quest omitted",
      "data-b='2'" not in syn_html)

print()
print("ALL TESTS PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
