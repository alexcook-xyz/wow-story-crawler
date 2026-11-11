# graph.py - merge facts, close chains, linearise, find gaps.
#
# The "no gaps" contract: starting from a chapter's seed quests, walk
# `before` links until a quest with no predecessors (the entry) and
# `after` links until a quest with no successors (the exit). Every link
# that points at a quest we have no page for is a reported gap, never a
# silently dropped edge. Class-specific quests are excluded from the
# main story by default, matching the addon.
from __future__ import annotations

from collections import deque

from .models import Gap, MergedQuest, QuestFact, SeedChapter
from .sources import SOURCES

MAX_LEVEL = 60


def _trust(source: str) -> int:
    s = SOURCES.get(source)
    return s.trust if s else 99


def merge_facts(facts: list[QuestFact]) -> dict[int, MergedQuest]:
    """Merge per-source facts. Link sets union; scalar fields take the
    highest-trust value and record any disagreement as a conflict."""
    merged: dict[int, MergedQuest] = {}
    by_qid: dict[int, list[QuestFact]] = {}
    for f in facts:
        by_qid.setdefault(f.qid, []).append(f)
    for qid, group in by_qid.items():
        group.sort(key=lambda f: _trust(f.source))
        mq = MergedQuest(qid=qid)
        for f in group:
            if f.source not in mq.sources:
                mq.sources.append(f.source)
            for attr in ("before", "after"):
                for link in getattr(f, attr):
                    if link != qid and link not in getattr(mq, attr):
                        getattr(mq, attr).append(link)
            for attr in ("name", "reqlevel", "faction", "race",
                         "class_", "zone", "giver"):
                val = getattr(f, attr)
                if val is None:
                    continue
                cur = getattr(mq, attr)
                if cur is None:
                    setattr(mq, attr, val)
                elif cur != val:
                    mq.conflicts.append(
                        f"{attr}: {cur!r} ({mq.sources[0]}) vs "
                        f"{val!r} ({f.source})")
        merged[qid] = mq
    # Back-fill reverse links: A.before=[B] implies B.after gains A.
    for qid, mq in merged.items():
        for pred in mq.before:
            if pred in merged and qid not in merged[pred].after:
                merged[pred].after.append(qid)
    return merged


# Races that start in the same zone and share quests (Forever: Dwarf and
# Gnome in Coldridge Valley, Orc and Troll in the Valley of Trials).
SHARED_START = ({"Dwarf", "Gnome"}, {"Orc", "Troll"})


def _other_player(mq: MergedQuest, faction: str | None,
                  race: str | None) -> bool:
    if faction in ("Alliance", "Horde") and mq.faction in ("Alliance", "Horde") \
            and mq.faction != faction:
        return True
    if not (race and mq.race) or mq.race == race:
        return False
    return not any(race in g and mq.race in g for g in SHARED_START)


def expand_from_seeds(merged: dict[int, MergedQuest], seeds: list[int],
                      exclude: set[int], include_class: bool = False,
                      max_level: int = MAX_LEVEL,
                      attunement: set[int] | frozenset[int] = frozenset(),
                      faction: str | None = None,
                      race: str | None = None) -> set[int]:
    """Transitive closure over before+after links from the seed quests.
    `attunement` ids are exempt from the level cutoff (raid/dungeon
    attunements sit at or above the boundary); class gating still applies."""
    seed_set = set(seeds)   # curated seeds are never filtered out
    seen: set[int] = set()
    queue = deque(q for q in seeds if q not in exclude)
    while queue:
        qid = queue.popleft()
        if qid in seen or qid in exclude:
            continue
        mq = merged.get(qid)
        if mq is None:
            continue
        if mq.class_specific and not include_class:
            continue
        if qid not in seed_set and _other_player(mq, faction, race):
            continue
        if (mq.reqlevel is not None and mq.reqlevel > max_level
                and qid not in attunement):
            continue
        seen.add(qid)
        queue.extend(mq.before)
        queue.extend(mq.after)
    return seen


def topo_order(merged: dict[int, MergedQuest], members: set[int],
               preferred: list[int] | None = None,
               ) -> tuple[list[int], list[int]]:
    """Kahn order over before-edges inside `members`. Ties break by the
    curated seed order, then required level, then id. Returns
    (ordered, in_cycle)."""
    rank = {q: i for i, q in enumerate(preferred or [])}
    indegree = {q: 0 for q in members}
    succ: dict[int, list[int]] = {q: [] for q in members}
    for q in members:
        for pred in merged[q].before:
            if pred in members:
                indegree[q] += 1
                succ[pred].append(q)

    def key(q: int):
        return (rank.get(q, 10 ** 6), merged[q].reqlevel or 0, q)

    ready = sorted((q for q, d in indegree.items() if d == 0), key=key)
    out: list[int] = []
    while ready:
        q = ready.pop(0)
        out.append(q)
        for nxt in succ[q]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=key)
    in_cycle = sorted(members - set(out))
    return out, in_cycle


def chapter_shape(merged: dict[int, MergedQuest], chapter: SeedChapter,
                  members: set[int], ordered: list[int]) -> dict:
    att = set(chapter.attunement)
    heads = [q for q in ordered
             if not any(p in members for p in merged[q].before)]
    tails = [q for q in ordered
             if not any(s in members for s in merged[q].after)]
    return {
        "id": chapter.id, "name": chapter.name,
        "faction": chapter.faction, "race": chapter.race,
        "zone": chapter.zone, "order": chapter.order,
        "entry": ordered[0] if ordered else None,
        "exit": ordered[-1] if ordered else None,
        "heads": heads, "tails": tails,
        "quests": ordered, "next_chapter": chapter.next_chapter,
        "attunement": [q for q in ordered if q in att],
    }


def find_gaps(merged: dict[int, MergedQuest], chapters: list[SeedChapter],
              shapes: list[dict], crawled: set[int]) -> list[Gap]:
    gaps: list[Gap] = []
    member_of: dict[int, str] = {}
    for shape in shapes:
        for q in shape["quests"]:
            member_of[q] = shape["id"]
    for chapter, shape in zip(chapters, shapes):
        members = set(shape["quests"])
        for qid in chapter.seeds:
            if qid not in merged:
                gaps.append(Gap("unknown_quest", "seed has no page in any "
                                "source", qid, chapter.id))
        for qid in chapter.attunement:
            if qid not in members:
                gaps.append(Gap("attunement_missing", "curated attunement "
                                "quest is not in the chapter (no page, "
                                "class-gated, or excluded)", qid, chapter.id))
        for qid in sorted(members):
            mq = merged[qid]
            for pred in mq.before:
                if pred not in merged:
                    gaps.append(Gap("missing_page", f"predecessor {pred} "
                                    "was not crawled", qid, chapter.id))
                elif _other_player(merged[pred], chapter.faction,
                                   chapter.race):
                    continue   # another race's variant, not a requirement
                elif pred not in members and pred in crawled:
                    gaps.append(Gap("orphan_link", f"requires {pred} "
                                    f"({merged[pred].name}) outside the "
                                    "chapter; needs a requires bridge",
                                    qid, chapter.id))
            for conflict in mq.conflicts:
                kind = ("name_conflict" if conflict.startswith("name")
                        else "level_conflict")
                gaps.append(Gap(kind, conflict, qid, chapter.id))
        if len(shape["heads"]) > 1:
            gaps.append(Gap("open_head", f"multiple entries {shape['heads']};"
                            " curate `entry` or add the missing lead quest",
                            None, chapter.id))
        if len(shape["tails"]) > 1:
            gaps.append(Gap("open_tail", f"multiple exits {shape['tails']};" 
                            " curate `exit` or split the chapter",
                            None, chapter.id))
        if chapter.next_chapter:
            nxt = next((s for s in shapes
                        if s["id"] == chapter.next_chapter), None)
            bridged = bool(nxt and nxt["quests"] and shape["quests"] and (
                nxt["entry"] in merged[shape["exit"]].after or
                shape["exit"] in merged[nxt["entry"]].before or
                chapter.exit == shape["exit"]))
            if not bridged:
                gaps.append(Gap("unbridged_chapter",
                                f"exit {shape['exit']} does not link into "
                                f"{chapter.next_chapter} entry "
                                f"{(nxt or {}).get('entry')}",
                                shape["exit"], chapter.id))
    return gaps


def referenced_ids(merged: dict[int, MergedQuest],
                   members: set[int]) -> set[int]:
    """Quest ids linked from members but not themselves crawled yet.
    The crawl loop feeds these back in until the graph is closed."""
    want: set[int] = set()
    for qid in members:
        mq = merged.get(qid)
        if mq:
            want.update(mq.before)
            want.update(mq.after)
    return want - set(merged)

