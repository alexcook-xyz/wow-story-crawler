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
            for attr in ("name", "reqlevel", "level", "faction", "race",
                         "class_", "zone", "giver", "turnin", "map_id",
                         "gx", "gy", "tx", "ty"):
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


def _blocked_reason(mq: MergedQuest, include_class: bool,
                    cap: int | None) -> str | None:
    """Why a quest may not join a chapter: 'class', 'level', or None.
    The single admission rule; expansion and the cutoff report both use it."""
    if mq.class_specific and not include_class:
        return "class"
    if cap is not None and mq.reqlevel is not None and mq.reqlevel > cap:
        return "level"
    return None


def expand_from_seeds(merged: dict[int, MergedQuest], seeds: list[int],
                      exclude: set[int], include_class: bool = False,
                      max_level: int | None = MAX_LEVEL,
                      direction: str = "before") -> set[int]:
    """Transitive closure from the seed quests. Chapters expand over
    "before" only: a prerequisite's prerequisite joins, but successors
    never do, so a chapter cannot swallow the next chapter (the handoff
    is verified separately as a bridge, not absorbed as membership).
    "both" also follows after-links; the crawl loop uses it to discover
    the full graph, chapter building must not. `max_level=None` lifts the
    level cutoff (attunement chapters)."""
    if direction not in ("before", "both"):
        raise ValueError(f"direction must be before|both, got {direction!r}")
    seen: set[int] = set()
    queue = deque(q for q in seeds if q not in exclude)
    while queue:
        qid = queue.popleft()
        if qid in seen or qid in exclude:
            continue
        mq = merged.get(qid)
        if mq is None:
            continue
        if _blocked_reason(mq, include_class, max_level):
            continue
        seen.add(qid)
        queue.extend(mq.before)
        if direction == "both":
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
    heads = [q for q in ordered
             if not any(p in members for p in merged[q].before)]
    tails = [q for q in ordered
             if not any(s in members for s in merged[q].after)]
    # Curated entry/exit win when they survived the crawl: topo order is
    # evidence, curation is intent. Tails that continue outside the
    # chapter are reported as gaps, not silently crowned exits.
    entry = (chapter.entry if chapter.entry in members
             else (ordered[0] if ordered else None))
    exit_ = (chapter.exit if chapter.exit in members
             else (ordered[-1] if ordered else None))
    return {
        "id": chapter.id, "name": chapter.name,
        "faction": chapter.faction, "race": chapter.race,
        "zone": chapter.zone, "order": chapter.order,
        "entry": entry, "exit": exit_,
        "heads": heads, "tails": tails,
        "quests": ordered, "next_chapter": chapter.next_chapter,
        "gate": chapter.gate,
    }


def find_gaps(merged: dict[int, MergedQuest], chapters: list[SeedChapter],
              shapes: list[dict], crawled: set[int],
              include_class: bool = False) -> list[Gap]:
    gaps: list[Gap] = []
    by_id = {c.id: c for c in chapters}
    owners_of: dict[int, set[str]] = {}
    for shape in shapes:
        for q in shape["quests"]:
            owners_of.setdefault(q, set()).add(shape["id"])
    for qid in sorted(owners_of):
        if len(owners_of[qid]) > 1:
            first = sorted(owners_of[qid])[0]
            gaps.append(Gap("shared_member", f"quest {qid} is a member of "
                            f"chapters {sorted(owners_of[qid])}; decide "
                            "which chapter owns it", qid, first))
    for chapter, shape in zip(chapters, shapes):
        members = set(shape["quests"])
        for qid in chapter.seeds:
            if qid not in merged:
                gaps.append(Gap("unknown_quest", "seed has no page in any "
                                "source", qid, chapter.id))
        for qid in sorted(members):
            mq = merged[qid]
            for pred in mq.before:
                if pred not in merged:
                    gaps.append(Gap("missing_page", f"predecessor {pred} "
                                    "was not crawled", qid, chapter.id))
                elif pred not in members and pred in crawled:
                    gaps.append(Gap(
                        "orphan_link", f"requires {pred} "
                        f"({merged[pred].name}) outside the chapter; "
                        "needs a requires bridge", qid, chapter.id,
                        members=(qid, pred)))
            for conflict in mq.conflicts:
                kind = ("name_conflict" if conflict.startswith("name")
                        else "level_conflict")
                gaps.append(Gap(kind, conflict, qid, chapter.id))
        for qid in shape.get("in_cycle", []):
            gaps.append(Gap("cycle", "quest is in a before-link cycle",
                            qid, chapter.id))
        if not chapter.is_attunement:
            # The level cutoff must never be silent: a thread that runs
            # past the cap is either an attunement chain (give the
            # chapter a gate) or genuinely out of scope.
            # Successors are not chapter members by design (tail_continues
            # reports them), so only seeds and prerequisites can be cut.
            excl = set(chapter.exclude)
            # Walk outward through level-blocked quests only: a cut quest's
            # own over-cap prerequisites are reported too, not just the first.
            cut: set[int] = set()
            todo = list(chapter.seeds) + [n for q in members
                                          for n in merged[q].before]
            while todo:
                n = todo.pop()
                if n in cut or n in members or n in excl or n not in merged:
                    continue
                if _blocked_reason(merged[n], include_class,
                                   MAX_LEVEL) != "level":
                    continue
                cut.add(n)
                todo.extend(merged[n].before)
            for n in sorted(cut):
                gaps.append(Gap("level_cutoff",
                                f"{n} ({merged[n].name}) needs level "
                                f"{merged[n].reqlevel}, above the "
                                f"{MAX_LEVEL} cutoff; split it into an "
                                "attunement chapter or accept the cut",
                                n, chapter.id))
        for tail in shape["tails"]:
            cont = [s for s in merged[tail].after if s not in members]
            if cont:
                known = [f"{s} ({merged[s].name})" for s in cont
                         if s in merged]
                missing = [s for s in cont if s not in merged]
                gaps.append(Gap("tail_continues",
                                f"{merged[tail].name} continues into "
                                f"{known + missing}; fetch and decide if "
                                "the thread belongs to the chapter",
                                tail, chapter.id))
        if shape["entry"] is not None:
            preds = [p for p in merged[shape["entry"]].before
                     if p in members]
            if preds:
                gaps.append(Gap("entry_has_pred",
                                f"curated entry needs {preds} first; "
                                "make sure the addon bridges them "
                                "(requires/lead)",
                                shape["entry"], chapter.id))
        if shape["exit"] is not None:
            succs = [s for s in merged[shape["exit"]].after
                     if s in members]
            if succs:
                gaps.append(Gap("exit_continues",
                                f"curated exit leads to {succs} inside "
                                "the chapter; the exit may be mid-thread",
                                shape["exit"], chapter.id))
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
    # Decisions (SeedChapter.explained) are the only thing that accounts for
    # a gap. Head and tail gaps are identified by their heads and tails.
    shape_by_id = {s["id"]: s for s in shapes}
    for g in gaps:
        if g.kind in ("open_head", "open_tail") and not g.members:
            side = "heads" if g.kind == "open_head" else "tails"
            g.members = tuple(shape_by_id[g.chapter][side])
    used: set[tuple] = set()
    for g in gaps:
        ch = by_id.get(g.chapter)
        if ch is None:
            continue
        for dec in ch.explained:
            if (dec["kind"] == g.kind
                    and sorted(dec["qids"]) == sorted(g.members)):
                g.explained = dec["reason"]
                used.add((ch.id, dec["kind"], tuple(sorted(dec["qids"]))))
    for ch in chapters:
        for dec in ch.explained:
            key = (ch.id, dec["kind"], tuple(sorted(dec["qids"])))
            if key not in used:
                gaps.append(Gap("stale_decision",
                                f"{dec['kind']} decision for {dec['qids']} "
                                "matches no current gap; remove or update it",
                                None, ch.id))
    return gaps


def split_gaps(gaps: list[Gap]) -> tuple[list[Gap], list[Gap]]:
    """(open, explained). The one definition of 'accounted for'."""
    return ([g for g in gaps if not g.explained],
            [g for g in gaps if g.explained])


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

