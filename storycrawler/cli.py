# cli.py - command line for the story crawler.
#
#   python crawl_story.py crawl            # fetch (network, polite)
#   python crawl_story.py crawl --dry-run  # print URLs, fetch none
#   python crawl_story.py build            # cache -> chapters+gaps
#   python crawl_story.py validate         # seeds sanity, offline
#   python crawl_story.py diff             # crawl vs addon catalogue
#   python crawl_story.py emit-lua --chapter elwynn
#   python crawl_story.py discover --wiki-slug The_Defias_Brotherhood
#   python crawl_story.py quest 147        # one quest, all sources
#
# `crawl` is the only command that touches the network, and only when
# neither --offline nor --dry-run is passed. Everything else reads the
# on-disk cache / facts file.
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storycrawler import builder, emit_html, graph       # noqa: E402
from storycrawler.fetcher import Fetcher              # noqa: E402
from storycrawler.parsers import parse_wiki_chain     # noqa: E402
from storycrawler.sources import DEFAULT_CRAWL_SOURCES, SOURCES  # noqa: E402

FACTS_FILE = "facts.json"


def _fetcher(args) -> Fetcher:
    return Fetcher(builder.DEFAULT_CACHE,
                   delay=args.delay, offline=args.offline,
                   dry_run=args.dry_run)


def _merged_and_shapes(args):
    facts_path = Path(args.out) / FACTS_FILE
    facts = builder.load_facts(facts_path) if facts_path.exists() else []
    merged = graph.merge_facts(facts)
    pairs = builder.build_chapters(
        merged, builder.load_seeds(args.seeds), args.include_class)
    chapters = [c for c, _s in pairs]
    shapes = [s for _c, s in pairs]
    return chapters, facts, merged, shapes


def cmd_validate(args) -> int:
    chapters = builder.load_seeds(args.seeds)
    seeded = sum(len(c.seeds) for c in chapters)
    unseeded = [c.id for c in chapters if not c.seeds]
    print(f"{len(chapters)} chapters, {seeded} seed quests")
    if unseeded:
        print("unseeded (TODO discover): " + ", ".join(unseeded))
    for c in chapters:
        if c.entry is not None and c.seeds and c.entry != c.seeds[0]:
            print(f"WARN {c.id}: entry {c.entry} is not first seed")
        if c.exit is not None and c.seeds and c.exit != c.seeds[-1]:
            print(f"WARN {c.id}: exit {c.exit} is not last seed")
    print("sources: " + ", ".join(SOURCES))
    return 0


def cmd_crawl(args) -> int:
    chapters = builder.load_seeds(args.seeds)
    if args.faction:
        chapters = [c for c in chapters if c.faction == args.faction]
    if args.chapter:
        chapters = [c for c in chapters if c.id in args.chapter]
    seed_ids = {q for c in chapters for q in c.seeds}
    print(f"crawling {len(seed_ids)} seed quests from "
          f"{len(chapters)} chapters; sources={args.sources}")
    rxp = builder.load_rxp_facts([Path(p) for p in args.rxp or []])
    fetcher = _fetcher(args)
    facts, crawled, unclosed = builder.crawl(
        fetcher, seed_ids, tuple(args.sources),
        max_rounds=args.max_rounds, rxp_facts=rxp, verbose=args.verbose)
    out = Path(args.out)
    if not fetcher.dry_run:
        # A dry run fetched nothing, so it must never touch the saved
        # facts; a real (or --offline) partial crawl merges into them.
        out.mkdir(parents=True, exist_ok=True)
        saved = out / FACTS_FILE
        if saved.exists():
            facts = builder.merge_saved_facts(builder.load_facts(saved),
                                              facts)
        builder.save_facts(facts, saved)
    print(f"facts={len(facts)} quests parsed={len(crawled)} "
          f"fetched={fetcher.stats['fetched']} "
          f"cached={fetcher.stats['cached']} "
          f"failed={fetcher.stats['failed']} blocked={fetcher.blocked}")
    if unclosed:
        print(f"UNCLOSED ({len(unclosed)} referenced but unfetched; "
              f"re-run with --max-rounds above {args.max_rounds}): "
              f"{sorted(unclosed)[:20]}")
    if fetcher.dry_run:
        print(f"DRY RUN: {len(fetcher.planned)} URLs would be fetched:")
        for url in fetcher.planned:
            print("  " + url)
    return 0


def _gaps_for(args):
    """The one gap pipeline: build, then find_gaps. build and report use it."""
    _chapters, _facts, merged, shapes = _merged_and_shapes(args)
    gaps = graph.find_gaps(merged, _chapters, shapes, set(merged),
                           include_class=args.include_class)
    return merged, shapes, gaps


def cmd_build(args) -> int:
    merged, shapes, gaps = _gaps_for(args)
    written = builder.write_outputs(Path(args.out), merged, shapes, gaps)
    for shape in shapes:
        print(f"{shape['id']}: {len(shape['quests'])} quests "
              f"{shape['entry']} -> {shape['exit']}")
    open_gaps, done_gaps = graph.split_gaps(gaps)
    print(f"gaps: {len(open_gaps)} open, {len(done_gaps)} explained "
          "(see gaps.md)")
    print("wrote: " + ", ".join(p.name for p in written))
    return 0


def cmd_diff(args) -> int:
    _c, _f, _m, shapes = _merged_and_shapes(args)
    addon_dir = Path(args.addon_dir or builder.DEFAULT_ADDON_DIR)
    data_files = sorted(addon_dir.glob("Data_*.lua"))
    if not data_files:
        print(f"no Data_*.lua under {addon_dir}; pass --addon-dir")
        return 2
    addon = builder.load_addon_catalogue(data_files)
    for line in builder.diff_catalogue(shapes, addon):
        print(line)
    return 0


def cmd_emit_html(args) -> int:
    graph_path = Path(args.graph) if args.graph else Path(args.out) / "story-graph.json"
    if not graph_path.exists():
        print(f"no graph at {graph_path}; run `build` first")
        return 2
    dest = Path(args.output) if args.output else Path(args.out) / "story-tree.html"
    emit_html.write_html(graph_path, dest)
    print(f"wrote {dest}")
    return 0


def cmd_emit_lua(args) -> int:
    _c, _f, merged, shapes = _merged_and_shapes(args)
    shape = next((s for s in shapes if s["id"] == args.chapter), None)
    if shape is None:
        print(f"unknown chapter {args.chapter!r}")
        return 2
    print(builder.emit_lua_draft(merged, shape))
    return 0


def cmd_discover(args) -> int:
    src = SOURCES["wiki"]
    url = src.quest_url.format(slug=args.wiki_slug)
    fetcher = _fetcher(args)
    page = fetcher.fetch("wiki", url)
    if page is None:
        print("no page (offline miss or dry-run; crawl it first)")
        for u in fetcher.planned:
            print("  would fetch " + u)
        return 1
    ids = parse_wiki_chain(page)
    print(f"{args.wiki_slug}: {len(ids)} quest ids in article order")
    print('"seeds": [' + ", ".join(str(i) for i in ids) + "]")
    print("Paste into seeds.json after a human skim; wiki membership is a "
          "lead, not proof. The crawl then verifies every link.")
    return 0


def cmd_quest(args) -> int:
    fetcher = _fetcher(args)
    facts, _, _ = builder.crawl(fetcher, {args.qid}, tuple(
        s for s in DEFAULT_CRAWL_SOURCES), max_rounds=1, verbose=True)
    merged = graph.merge_facts(facts)
    mq = merged.get(args.qid)
    if mq is None:
        print(f"no facts for quest {args.qid}")
        return 1
    import json
    print(json.dumps(mq.to_json(), indent=1))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crawl_story",
        description="Build a gap-free linear WoW Forever main-story "
                    "graph (all races, both factions, to level 60) "
                    "from curated seeds by crawling quest databases.")
    p.add_argument("--seeds", type=Path, default=builder.DEFAULT_SEEDS)
    p.add_argument("--out", type=Path, default=builder.DEFAULT_OUT)
    p.add_argument("--offline", action="store_true",
                   help="cache only; never touch the network")
    p.add_argument("--dry-run", action="store_true",
                   help="print URLs that would be fetched; fetch none")
    p.add_argument("--delay", type=float, default=2.0,
                   help="seconds between requests per source")
    p.add_argument("--include-class", action="store_true",
                   help="keep class-specific quests (excluded by default)")
    p.add_argument("--addon-dir", type=Path, default=None,
                   help="folder holding the addon's Data_*.lua for `diff` "
                        "(default: ../MainStoryGuide/MainStoryGuide)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="check seeds.json (offline)")
    c = sub.add_parser("crawl", help="fetch pages to graph closure")
    c.add_argument("--sources", nargs="+", default=list(DEFAULT_CRAWL_SOURCES),
                   choices=sorted(SOURCES))
    c.add_argument("--faction", choices=["Alliance", "Horde", "Neutral"])
    c.add_argument("--chapter", nargs="+")
    c.add_argument("--rxp", nargs="*", default=None,
                   help="local RestedXP guide files (offline source)")
    c.add_argument("--max-rounds", type=int, default=12)
    c.add_argument("--verbose", action="store_true")
    sub.add_parser("build", help="facts -> chapters, gaps, chart")
    sub.add_parser("diff", help="crawl vs MainStoryGuide/Data_*.lua")
    rp = sub.add_parser("report", help="regenerate docs/race-gaps.md")
    rp.add_argument("--doc", default="docs/race-gaps.md")
    e = sub.add_parser("emit-lua", help="print a draft chain block")
    e.add_argument("--chapter", required=True)
    h = sub.add_parser("emit-html", help="render story-graph.json as an interactive HTML tree")
    h.add_argument("--graph", default=None,
                   help="story-graph.json to render (default: <out>/story-graph.json)")
    h.add_argument("-o", "--output", default=None,
                   help="HTML file to write (default: <out>/story-tree.html)")
    d = sub.add_parser("discover", help="propose seeds from a wiki article")
    d.add_argument("--wiki-slug", required=True)
    q = sub.add_parser("quest", help="inspect one quest across sources")
    q.add_argument("qid", type=int)
    return p


def cmd_report(args) -> int:
    from storycrawler import report
    _merged, shapes, gaps = _gaps_for(args)
    text = report.race_report(
        shapes, gaps, f"crawl_story.py report --doc {args.doc}")
    Path(args.doc).parent.mkdir(parents=True, exist_ok=True)
    Path(args.doc).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.doc}")
    return 0


_COMMANDS = {"validate": cmd_validate, "crawl": cmd_crawl,
             "report": cmd_report,
             "build": cmd_build, "diff": cmd_diff,
             "emit-lua": cmd_emit_lua, "emit-html": cmd_emit_html, "discover": cmd_discover,
             "quest": cmd_quest}


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return _COMMANDS[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
