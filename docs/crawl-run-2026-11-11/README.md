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

Observations to triage (not conclusions):
- Many chapters share the same Forever starter chain (quest ids ~95998-98286,
  ending at 98286). Closure pulls it into Human, Dwarf, Gnome and Night Elf
  chapters alike, which inflates entries/exits. It needs a shared-starter
  chapter or `exclude` lists.
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
