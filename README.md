# wow-story-crawler

Research tool for [MainStoryGuide](https://github.com/alexcook-xyz/MainStoryGuide):
builds one linear, gap-free "main story" for World of Warcraft Forever —
every required quest of every storyline chapter, for all races and both
factions, up to level 60. It produces drafts and gap reports for a human
to review and apply. It never writes into the addon repo; `diff` only
reads the addon's `Data_*.lua` (pass `--addon-dir` when they are not
side-by-side checkouts).

Stdlib-only Python 3. `python crawl_story.py --help` lists the commands.

## How it works

1. **Seeds** (`storycrawler/seeds.json`) name the storyline chapters and
   at least one quest known to belong to each. Seeds are curated, never
   guessed: Human chapters mirror the addon's verified catalogue,
   Skyborne chapters mirror `Data_Forever.lua`, and race-starter
   chapters mirror the local RestedXP Forever guides section by
   section (class-gated accepts skipped).
2. **Crawl** fetches each seed quest's page, reads its predecessor
   ("Before this") and successor links, then keeps fetching newly
   referenced quests until the graph is closed (a prerequisite's
   prerequisite is pulled in too). Chapters expand over predecessors
   only, so a chapter can never swallow the next one; the handoff is
   verified separately as a bridge. If `--max-rounds` runs out first,
   the crawl prints the UNCLOSED remainder for the next run.
3. **Merge** combines sources per quest with provenance. Trust order:
   local RestedXP Forever guides, then the Forever quest database.
   (Wowhead stays available via explicit `--sources` but answers 403
   to script fetches, so it is out of the default set.) Disagreements
   are reported, not silently resolved. Class-specific quests are
   excluded by default, matching the addon; quests above level 60
   are cut off.
4. **Build** linearises each chapter (topological order over the
   prerequisite links, ties broken by curated seed order and level;
   curated entry/exit win when they survive the crawl) and writes
   outputs to `out/`:
   - `story-graph.json` — every quest fact and chapter, machine-readable
   - `storyline.md` — the linear main story, chapter by chapter
   - `storyline.mmd` — a Mermaid flow chart (the visual line map:
     one line per chapter, stations in story order, chapter links)
   - `story-tree.html` (via `emit-html`) — the interactive graphical
     quest tree: one swimlane per chapter, nodes in story order,
     entry/exit rings, click-a-node details, filters, zoom/pan, and
     gap badges. One self-contained file, no CDN. Open in a browser.
   - `gaps.md` — everything still open: uncrawled pages, chapters with
     multiple entries/exits, tails whose thread continues outside the
     chapter, curated entries with predecessors and exits with
     successors inside the chapter, links that point outside a chapter
     and need a `requires` bridge, chapter exits that do not connect
     to the next chapter's entry, cycles, and source conflicts

## Sources

| Source | Role | Notes |
| --- | --- | --- |
| Local RXPGuides Forever files | Offline ground truth for accept order | Pass with `--rxp <files>` on crawl |
| [pd.zroot.it](https://pd.zroot.it/forever/quests/) | Primary Forever quest database | Name, links, required + quest level, faction gate, giver/turn-in NPCs with zone, map ID and 0-100 coordinates |
| [Wowhead Forever](https://www.wowhead.com/forever/quests) | Opt-in cross-check only | Probed 403 to plain script fetches; pass `--sources wowhead-forever` to try anyway |
| [Wowhead Classic](https://www.wowhead.com/classic/quests) | Classic-era cross-check | Forever may differ; never sole proof |
| [warcraft.wiki.gg](https://warcraft.wiki.gg) | Storyline membership discovery | Seeds only; the crawl verifies every link. Note: current wiki markup links quests internally (`/wiki/Quest_Name`), so `discover` needs the name-to-ID step done by hand for now |

Facts only are collected: quest IDs, names, links, levels, gates,
giver/turn-in NPCs, zones, map IDs and coordinates. No quest text,
gossip, or descriptions are copied. Emitted Lua drafts fill
giver/zone/map/coords from the crawled pages but stay header-marked
for in-game verification — the addon never invents markers, and
`/story logquest` still wins on any conflict.

## Manners

One request at a time, 2 s apart per source by default (`--delay`).
Every page is cached under `.cache/storycrawler/` (gitignored), so
re-runs are offline. HTTP 403/429 stops that source for the run, and
dropped connections retry with backoff. If a host disallows automated
access, respect that and rely on the Forever database plus local
guides instead.

## Commands

```text
python crawl_story.py validate            # seeds sanity (offline)
python crawl_story.py crawl --dry-run     # list URLs, fetch nothing
python crawl_story.py crawl --sources foreverdb --max-rounds 25
python crawl_story.py crawl --chapter elwynn --verbose   # merges into out/facts.json
python crawl_story.py crawl --rxp "<Forever>\RXPGuides\Guides\forever\*.lua"
python crawl_story.py build               # out/: chapters, gaps, charts
python crawl_story.py report              # docs/race-gaps.md (generated)
python crawl_story.py emit-html           # out/story-tree.html
python crawl_story.py diff                # crawl vs MainStoryGuide/Data_*.lua
python crawl_story.py emit-lua --chapter elwynn   # draft chain block
python crawl_story.py discover --wiki-slug <Article>  # propose seeds
python crawl_story.py quest 147           # one quest, all sources
```

`--offline` on any command reads cache only. `--include-class` keeps
class-specific quests (default: excluded). `--faction` limits a crawl.

## Seeding a new race/faction storyline

1. Prefer the local RXP Forever guide for that starter: split its
   `#name` sections and seed one chapter per section (skip
   class-gated sections). Wiki chain articles work too:
   `python crawl_story.py discover --wiki-slug <Article>`
2. Paste the proposed seed list into that chapter in `seeds.json`
   after a skim, set `entry`/`exit` if known, and `next_chapter`
   where the exit hands off to another chapter.
3. Crawl that chapter, build, and work `gaps.md` to zero: every
   chapter must end with one entry, one exit, and a bridge into the
   next chapter (or be a true terminal like an attunement finale).
4. `diff` against the addon, `emit-lua` for a draft block, then fill
   giver/map/coords from in-game verification before adding it to
   `MainStoryGuide/Data_*.lua` with route tasks and journal entries.

## Attunement chapters and explained gaps

- `"kind": "attunement"` + `"gate": "<raid/dungeon>"` on a chapter marks
  a raid/dungeon attunement or key chain (Onyxia, Molten Core, UBRS
  Seal of Ascension, Blackwing Lair). It lifts the level-60 cutoff for
  that chapter and makes it a true terminal (no `next_chapter` needed).
  On every other chapter, a thread that runs past the cutoff is now
  reported as `level_cutoff` instead of being dropped silently.
- `"explained": {"<gap kind>": "<reason>"}` on a chapter accounts for
  gaps of that kind. `gaps.md` lists `## Open` and `## Explained`
  separately; a `tail_continues` that lands in another chapter is
  explained automatically as a hand-off. Only explain a gap you have
  checked: the reason is the audit trail.
- `docs/endgame-seeds.md` records how the endgame chapters were seeded
  (Forever DB name search, `?search=<name>` on the quest list) and the
  structure the crawl found.
- `docs/race-gaps.md` summarises the race starters; `docs/human-audit.md`
  is the crawl-vs-`Data_Human.lua` audit (candidates to verify in game).

## Tests

`python tests/test_crawler.py` — fully offline: fixture HTML for each
parser (links, levels, faction gate, giver card with map/coords),
dry-run/offline/cache fetcher behaviour, graph closure in both
directions, curated entry/exit, linearisation, cycle and gap
detection (including tail continuations and mid-thread exits), seed
coverage for all races and factions, and the catalogue diff.
