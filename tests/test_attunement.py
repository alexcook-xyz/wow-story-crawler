# test_attunement.py - offline tests for the raid/dungeon attunement quest
# type (seed field `attunement`). Standalone so it runs even while
# tests/test_crawler.py is out of sync with the parsers.
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storycrawler import builder, graph          # noqa: E402
from storycrawler.models import QuestFact, SeedChapter  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails += 1


# chain 1 -> 2 -> 3 -> 4; quest 3 and 4 sit above the level-60 boundary.
facts = [
    QuestFact(1, "foreverdb", name="Lead", after=[2], reqlevel=58),
    QuestFact(2, "foreverdb", name="Key part", before=[1], after=[3],
              reqlevel=60),
    QuestFact(3, "foreverdb", name="Attune", before=[2], after=[4],
              reqlevel=61),
    QuestFact(4, "foreverdb", name="Above cap", before=[3], reqlevel=62),
]
merged = graph.merge_facts(facts)

plain = graph.expand_from_seeds(merged, [1, 2], set())
check("cutoff: >60 quests are cut by default", plain == {1, 2})
att = graph.expand_from_seeds(merged, [1, 2], set(), attunement={3})
check("attunement id survives the level cutoff", att == {1, 2, 3})
check("non-attunement quest above 60 is still cut", 4 not in att)

chapter = SeedChapter(id="att", name="Attunement", faction="Neutral",
                      seeds=[1, 2], attunement=[3])
members = graph.expand_from_seeds(merged, chapter.seeds, set(),
                                  attunement=set(chapter.attunement))
ordered, cyc = graph.topo_order(merged, members, chapter.seeds)
shape = graph.chapter_shape(merged, chapter, members, ordered)
check("shape: attunement quests listed", shape["attunement"] == [3])
check("shape: chain is linear to the attunement exit",
      shape["quests"] == [1, 2, 3] and shape["exit"] == 3)

gaps = graph.find_gaps(
    merged, [chapter], [shape], set(merged))
check("no attunement_missing gap when member", not any(
    g.kind == "attunement_missing" for g in gaps))
missing = SeedChapter(id="att2", name="Bad", faction="Neutral",
                      seeds=[1, 2], attunement=[4])
members2 = graph.expand_from_seeds(merged, missing.seeds, set(),
                                   attunement=set(missing.attunement))
ordered2, _ = graph.topo_order(merged, members2, missing.seeds)
shape2 = graph.chapter_shape(merged, missing, members2, ordered2)
gaps2 = graph.find_gaps(merged, [missing], [shape2], set(merged))
check("attunement_missing gap when listed id is not reachable", any(
    g.kind == "attunement_missing" and g.qid == 4 for g in gaps2))

built = builder.build_chapters(merged, [chapter])
check("build_chapters passes the attunement list through",
      built[0]["quests"] == [1, 2, 3] and built[0]["attunement"] == [3])

# --- faction/race filter: alternatives are not requirements -----------
v = [
    QuestFact(10, "foreverdb", name="Hub", after=[20], reqlevel=5),
    QuestFact(20, "foreverdb", name="Human variant", before=[10], after=[50],
              faction="Alliance", race="Human"),
    QuestFact(21, "foreverdb", name="Orc variant", before=[10], after=[50],
              faction="Horde", race="Orc"),
    QuestFact(22, "foreverdb", name="Dwarf variant", before=[10], after=[50],
              faction="Alliance", race="Dwarf"),
    QuestFact(50, "foreverdb", name="Joins all variants",
              before=[20, 21, 22]),
]
vm = graph.merge_facts(v)
hum = graph.expand_from_seeds(vm, [50], set(), faction="Alliance",
                              race="Human")
check("filter: other faction/race variants are not pulled in",
      hum == {50, 20, 10})
gnome = graph.expand_from_seeds(vm, [50], set(), faction="Alliance",
                                race="Gnome")
check("filter: Gnome shares Dwarf quests, not Human ones",
      22 in gnome and 20 not in gnome and 21 not in gnome)
seeded = graph.expand_from_seeds(vm, [21, 50], set(), faction="Alliance",
                                 race="Human")
check("filter: curated seeds are never filtered out", 21 in seeded)
nofilter = graph.expand_from_seeds(vm, [50], set())
check("filter: off when faction/race not given", nofilter == {50, 20, 21, 22, 10})

print("ALL ATTUNEMENT TESTS PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
