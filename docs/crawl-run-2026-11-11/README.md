# Crawl run 2026-11-11 (foreverdb only)

What ran: `crawl --sources foreverdb` over all 55 seeded chapters
(676 seeds -> 1043 quest pages, 0 failed), then `build` and `diff
--addon-dir <MainStoryGuide/MainStoryGuide>`.

What did NOT run:
- `--rxp`: no local Forever/RXP guide files were available.
- Wowhead (Forever and Classic): HTTP 403 from this environment.
- Endgame / mid-game seeds were not added in this run.

## Result: gaps are NOT clean
`gaps.md` has 102 open entries: 48 open_tail, 46 open_head, 5 orphan_link,
3 unbridged_chapter. None have been triaged, so there are no explained
entries yet. The acceptance criterion is not met.

Observations to triage (measured on this run's facts, not yet fixed):
- 45 of 55 chapters have both multiple entries and multiple exits.
  Two separate causes:
  1. A 35-quest Forever "Camping 101" profession-tutorial family
     (95998 "The Great Outdoors", 96031-96059, 96101-96102, 96604-96608,
     96629, 96646-96661, 97963-97973, 98285-98286) is pulled into the early
     chapters of every race through shared links. Excluding it everywhere
     except where a chapter seeds it did NOT reduce open_head/open_tail
     (still 46/48) and raised orphan_link from 5 to 107, so excluding it
     alone is not the fix. Whether Camping 101 belongs to the main story
     (Dwarf `dwarf_lodgings` has 96608 as its curated entry) is a
     curation decision I did not make.
  2. Genuinely multi-chain zone chapters (hillsbrad, arathi, desolace,
     barrens, ...) need `entry`/`exit` curated or splitting.
- Cross-race contamination: for example `elwynn` and `peoples_militia`
  list Dwarf starter quests (179, 183, ...) as entries, and
  `defias_brotherhood` lists Night Elf ones (456, 916, ...). Human
  chapters should not contain these; the cause has not been found.
- Exits differ from the curated ones for several race chapters (for example
  Orc/Troll exit 842, Tauren exit 6382, Undead exit 1113).
- Gnome/Dwarf chapters are shared-starter stubs (names still start TODO).

## Human audit (diff vs Data_Human.lua, complements MainStoryGuide #5)
- elwynn: order differs; the crawl places 3903/3904/3905 after 123/147/239.
- duskwood_darkness: quest 55 is last in the crawl, first in the addon.
- redridge: 89 and 91 swapped.
- missing_diplomat: crawl adds 1324. onyxia: crawl adds 7495, 7496, 7497.
- "crawl adds" lists for other chains mostly reflect the over-broad closure
  above, not confirmed missing links.
- Addon chain ids gnome_* do not match seed chapter ids, so they show as
  "addon-only (unreached)"; that is an id mapping gap, not missing quests.

Files: `gaps.md`, `storyline.md` (generated, not yet linear per race),
`diff-vs-addon.txt`.
