# builder.py - orchestration: crawl-to-closure, build, report, emit.
from __future__ import annotations

import json
import re
from pathlib import Path

from . import graph
from .fetcher import Fetcher, FetchError, SourceBlocked
from .models import MergedQuest, QuestFact, SeedChapter
from .parsers import PARSERS, parse_rxp_lines
from .sources import DEFAULT_CRAWL_SOURCES, SOURCES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / ".cache" / "storycrawler"
DEFAULT_OUT = ROOT / "out"
DEFAULT_SEEDS = ROOT / "storycrawler" / "seeds.json"
# The addon this research feeds. Separate repo on purpose: the crawler
# reads Data_*.lua for `diff`, it never writes into the addon tree.
DEFAULT_ADDON_DIR = ROOT.parent / "MainStoryGuide" / "MainStoryGuide"


def load_seeds(path: Path = DEFAULT_SEEDS) -> list[SeedChapter]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    chapters = [SeedChapter.from_json(d) for d in data["chapters"]]
    ids = [c.id for c in chapters]
    known = set(ids)
    if len(ids) != len(known):
        raise ValueError("duplicate chapter id in seeds")
    for c in chapters:

        if c.next_chapter and c.next_chapter not in known:
            raise ValueError(f"{c.id}: next_chapter {c.next_chapter!r} unknown")
    return chapters


def load_rxp_facts(paths: list[Path]) -> list[QuestFact]:
    facts: list[QuestFact] = []
    for p in paths:
        facts.extend(parse_rxp_lines(Path(p).read_text(encoding="utf-8",
                                                       errors="replace")))
    return facts


def crawl(fetcher: Fetcher, seed_ids: set[int],
          source_names: tuple[str, ...] = DEFAULT_CRAWL_SOURCES,
          max_rounds: int = 12, rxp_facts: list[QuestFact] | None = None,
          verbose: bool = False
          ) -> tuple[list[QuestFact], set[int], set[int]]:
    """Fetch every seed quest, then keep feeding newly referenced ids
    back in until the before/after graph is closed (or max_rounds).
    Returns (facts, ids for which at least one page was parsed,
    referenced-but-unfetched ids left when max_rounds ran out)."""
    facts: list[QuestFact] = list(rxp_facts or [])
    crawled: set[int] = {f.qid for f in facts}
    frontier = set(seed_ids)
    attempted: set[int] = set()
    unclosed: set[int] = set()
    for _round in range(max_rounds):
        todo = sorted(frontier - attempted)
        if not todo:
            break
        for qid in todo:
            attempted.add(qid)
            for name in source_names:
                src = SOURCES[name]
                if not src.quest_url or "{qid}" not in src.quest_url:
                    continue
                url = src.quest_url.format(qid=qid)
                try:
                    page = fetcher.fetch(name, url)
                except SourceBlocked as e:
                    print(f"  blocked: {e}")
                    break
                except FetchError as e:
                    print(f"  fetch failed: {e}")
                    continue
                if page is None:
                    continue
                fact = PARSERS[src.parser](qid, page, url)
                facts.append(fact)
                crawled.add(qid)
                if verbose:
                    print(f"  {name} {qid}: before={fact.before} "
                          f"after={fact.after}")
        merged = graph.merge_facts(facts)
        frontier = graph.referenced_ids(merged, attempted | crawled)
    unclosed = set(frontier - attempted)
    return facts, crawled, unclosed


def build_chapters(merged: dict[int, MergedQuest],
                   chapters: list[SeedChapter],
                   include_class: bool = False
                   ) -> list[tuple[SeedChapter, dict]]:
    """Build one shape per chapter, sorted by (faction, order). Returns
    (chapter, shape) pairs so gap attribution can never mis-pair a
    chapter with another chapter's shape."""
    pairs = []
    for chapter in sorted(chapters, key=lambda c: (c.faction, c.order)):
        members = graph.expand_from_seeds(
            merged, chapter.seeds, set(chapter.exclude), include_class,
            max_level=None if chapter.is_attunement else graph.MAX_LEVEL)
        ordered, in_cycle = graph.topo_order(merged, members, chapter.seeds)
        shape = graph.chapter_shape(merged, chapter, members, ordered)
        shape["in_cycle"] = in_cycle
        pairs.append((chapter, shape))
    return pairs


def merge_saved_facts(old: list[QuestFact],
                      new: list[QuestFact]) -> list[QuestFact]:
    """Keep earlier facts a partial crawl (--chapter / --faction) did
    not re-read. A fresh fact replaces the saved one for the same
    (quest, source); everything else is preserved."""
    fresh = {(f.qid, f.source) for f in new}
    return [f for f in old if (f.qid, f.source) not in fresh] + list(new)


def save_facts(facts: list[QuestFact], path: Path) -> None:
    Path(path).write_text(json.dumps([f.to_json() for f in facts],
                                      indent=1), encoding="utf-8")


def load_facts(path: Path) -> list[QuestFact]:
    return [QuestFact.from_json(d)
            for d in json.loads(Path(path).read_text(encoding="utf-8"))]


def _write_lf(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Generated outputs always use LF, so diffs match on every OS."""
    Path(path).write_text(text, encoding=encoding, newline="\n")


def write_outputs(out_dir: Path, merged: dict[int, MergedQuest],
                  shapes: list[dict], gaps: list) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    graph_json = {"quests": {str(q): merged[q].to_json()
                             for q in sorted(merged)},
                  "chapters": shapes}
    p = out / "story-graph.json"
    _write_lf(p, json.dumps(graph_json, indent=1), encoding="utf-8")
    written.append(p)
    p = out / "gaps.md"
    lines = ["# Story graph gaps", ""]
    open_gaps, done_gaps = graph.split_gaps(gaps)
    lines += [f"{len(open_gaps)} open, {len(done_gaps)} explained.", "",
              "## Open", ""]
    lines += [g.line() for g in open_gaps] or ["None. Every chapter is closed."]
    lines += ["", "## Explained", ""]
    lines += [g.line() for g in done_gaps] or ["None."]
    _write_lf(p, "\n".join(lines) + "\n", encoding="utf-8")
    written.append(p)
    p = out / "storyline.md"
    lines = ["# Linear main story (draft, generated)", ""]
    for shape in shapes:
        race = f" / {shape['race']}" if shape["race"] else ""
        tag = f" [attunement: {shape['gate']}]" if shape.get("gate") else ""
        lines.append(f"## {shape['name']} ({shape['faction']}{race}){tag}")
        lines.append(f"Entry {shape['entry']} -> exit {shape['exit']}; "
                     f"{len(shape['quests'])} quests")
        for qid in shape["quests"]:
            mq = merged[qid]
            lvl = f" lvl {mq.reqlevel}" if mq.reqlevel else ""
            lines.append(f"- {qid} {mq.name or '?'}{lvl}")
        lines.append("")
    _write_lf(p, "\n".join(lines), encoding="utf-8")
    written.append(p)
    p = out / "storyline.mmd"
    lines = ["flowchart LR"]
    for shape in shapes:
        lines.append(f"  subgraph {shape['id']}[\"{shape['name']}\"]")
        qs = shape["quests"]
        for a, b in zip(qs, qs[1:]):
            lines.append(f"    q{a} --> q{b}")
        if qs:
            lines.append(f"    q{qs[0]}[\"{qs[0]} entry\"]")
            lines.append(f"    q{qs[-1]}[\"{qs[-1]} exit\"]")
        lines.append("  end")
        if shape["next_chapter"]:
            lines.append(f"  {shape['id']} --> {shape['next_chapter']}")
    _write_lf(p, "\n".join(lines) + "\n", encoding="utf-8")
    written.append(p)
    return written


_CHAIN_RE = re.compile(r'\{\s*id\s*=\s*"([a-z0-9_]+)"')
_QUEST_RE = re.compile(r'\{\s*id\s*=\s*(\d+),\s*name\s*=\s*"((?:[^"\\]|\\.)*)"')


def load_addon_catalogue(data_files: list[Path]) -> dict[str, list[int]]:
    """chain id -> ordered quest ids, parsed from Data_*.lua the same
    way tools/extract_prereqs.py does."""
    chains: dict[str, list[int]] = {}
    for path in data_files:
        text = Path(path).read_text(encoding="utf-8")
        cur: str | None = None
        for m in re.finditer(
                _CHAIN_RE.pattern + "|" + _QUEST_RE.pattern, text):
            if m.group(1):
                cur = m.group(1)
                chains.setdefault(cur, [])
            elif cur is not None and m.group(2):
                chains[cur].append(int(m.group(2)))
    return chains


def diff_catalogue(shapes: list[dict],
                   addon: dict[str, list[int]]) -> list[str]:
    """Per chain: quests the crawl found that the addon lacks, quests
    the addon has that the crawl did not reach, and order drift."""
    lines: list[str] = []
    crawled = {s["id"]: s["quests"] for s in shapes}
    for cid in sorted(set(addon) | set(crawled)):
        have = addon.get(cid, [])
        found = crawled.get(cid, [])
        missing = [q for q in found if q not in have]
        extra = [q for q in have if q not in found]
        common_have = [q for q in have if q in found]
        common_found = [q for q in found if q in have]
        if missing:
            lines.append(f"{cid}: crawl adds {missing}")
        if extra:
            lines.append(f"{cid}: addon-only (unreached) {extra}")
        if common_have != common_found:
            lines.append(f"{cid}: order differs "
                         f"addon={common_have} crawl={common_found}")
    return lines or ["Catalogue and crawl agree on every shared chain."]


def emit_lua_draft(merged: dict[int, MergedQuest], shape: dict) -> str:
    """Draft Data_* chain block for human review. Giver/zone/map/coords
    come from the crawled database pages when present (still marked for
    in-game verification); missing ones stay TODOs. This tool never
    invents markers or coordinates."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    lines = [f'-- DRAFT from storycrawler; verify giver/map/x/y in game.',
             f'{{ id = "{shape["id"]}", name = "{esc(shape["name"])}", '
             f'race = "{shape["race"] or "TODO"}",',
             f'  zone = "{esc(shape["zone"] or "TODO")}", '
             f'verified = "crawler-draft",',
             f'  summary = "TODO: original one-line summary.",',
             '  quests = {']
    members = set(shape["quests"])
    for i, qid in enumerate(shape["quests"]):
        mq = merged[qid]
        kind = ""
        if i == 0 or i == len(shape["quests"]) - 1:
            kind = ', kind = "lead"'
        req = [p for p in mq.before if p not in members]
        req_s = f', requires = {{{",".join(str(r) for r in req)}}}' if req else ""
        lvl = f", reqlevel = {mq.reqlevel}" if mq.reqlevel else ""
        giver = f'"{esc(mq.giver)}"' if mq.giver else '"TODO"'
        zone = f'"{esc(mq.zone)}"' if mq.zone else '"TODO"'
        map_ = str(mq.map_id) if mq.map_id else "TODO"
        xy = (f", x = {mq.gx}, y = {mq.gy}"
              if mq.gx is not None and mq.gy is not None else "")
        lines.append(f'    {{ id = {qid}, name = "{esc(mq.name or "TODO")}", '
                     f'giver = {giver}, zone = {zone}, map = {map_}{xy}'
                     f'{kind}{req_s}{lvl} }},')
    lines += ["  } },", ""]
    return "\n".join(lines)
