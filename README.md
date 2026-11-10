# Story crawler

Builds one linear, gap-free "main story" for World of Warcraft Forever:
every required quest of every storyline chapter, for all races and both
factions, up to level 60. It is a developer research tool. It never
edits the addon's data files; it produces drafts and gap reports for a
human to review and apply.

## How it works

1. **Seeds** (`seeds.json`) name the storyline chapters and at least one
   quest known to belong to each. Seeds are curated, never guessed. The
   Human chapters are imported from the addon's verified catalogue;
   other races start as stubs to be seeded (see `discover` below).
2. **Crawl** fetches each seed quest's page, reads its predecessor
   ("Before this") and successor links, then keeps fetching newly
   referenced quests until the graph is closed. Walking predecessors
   to a quest with none gives the chapter's true **entry**; walking
   successors gives the true **exit**. That is how gaps are removed:
   if a prerequisite has a prerequisite, it is pulled in too.
3. **Merge** combines sources per quest with provenance. Trust order:
   local RestedXP Forever guides, then the Forever quest database,
   then Wowhead (Forever, then Classic). Disagreements are reported,
   not silently resolved. Class-specific quests are excluded by
   default, matching the addon; quests above level 60 are cut off.
4. **Build** linearises each chapter (topological order over the
   prerequisite links, ties broken by curated seed order and level)
   and writes outputs to `out/`:
   - `story-graph.json` — every quest fact and chapter, machine-readable
   - `storyline.md` — the linear main story, chapter by chapter
   - `storyline.mmd` — a Mermaid flow chart (the visual line map:
     one line per chapter, stations in story order, chapter links)
   - `gaps.md` — everything still open: uncrawled pages, chapters with
     multiple entries/exits, links that point outside a chapter and
     need a `requires` bridge, chapter exits that do not connect to
     the next chapter's entry, cycles, and source conflicts

## Sources

| Source | Role | Notes |
| --- | --- | --- |
| Local RXPGuides Forever files | Offline ground truth for accept order | Pass with `--rxp <files>` on crawl |
| [pd.zroot.it](https://pd.zroot.it/forever/quests/) | Primary Forever quest database | The source the addon already verifies against |
| [Wowhead Forever](https://www.wowhead.com/forever/quests) | Cross-check, chain "Series" links | Advisory; may bot-wall bulk fetching |
| [Wowhead Classic](https://www.wowhead.com/classic/quests) | Classic-era cross-check | Forever may differ; never sole proof |
| [warcraft.wiki.gg](https://warcraft.wiki.gg) | Storyline membership discovery | Seeds only; the crawl verifies every link |

Facts only are collected: quest IDs, names, links, required level, and
faction/race/class gates. No quest text, gossip, or descriptions are
copied. Giver names and coordinates are **not** harvested into the
addon by this tool; emitted Lua drafts leave them as `TODO` for
in-game verification (the addon never invents markers).

## Manners

One request at a time, 2 s apart per source by default (`--delay`).
Every page is cached under `.cache/storycrawler/` (gitignored), so
re-runs are offline. HTTP 403/429 stops that source for the run. If a
host disallows automated access, respect that and rely on the Forever
database plus local guides instead.

## Commands

```text
python crawl_story.py validate            # seeds sanity (offline)
python crawl_story.py crawl --dry-run     # list URLs, fetch nothing
python crawl_story.py crawl               # crawl to closure
python crawl_story.py crawl --chapter elwynn --verbose
python crawl_story.py crawl --rxp "<Forever>\RXPGuides\Guides\forever\*.lua"
python crawl_story.py build               # out/: chapters, gaps, chart
python crawl_story.py diff                # crawl vs MainStoryGuide/Data_*.lua
python crawl_story.py emit-lua --chapter elwynn   # draft chain block
python crawl_story.py discover --wiki-slug <Article>  # propose seeds
python crawl_story.py quest 147           # one quest, all sources
```

`--offline` on any command reads cache only. `--include-class` keeps
class-specific quests (default: excluded). `--faction` limits a crawl.

## Seeding a new race/faction storyline

1. Find the saga's chain article on warcraft.wiki.gg, then:
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

## Tests

`python tests/test_crawler.py` — fully offline: fixture HTML for each
parser, dry-run/offline/cache fetcher behaviour, graph closure,
linearisation, cycle and gap detection, seed coverage for all races
and factions, and the catalogue diff against `Data_Human.lua`.
