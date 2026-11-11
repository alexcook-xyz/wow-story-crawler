# Crawl run 2026-11-11 (foreverdb only)

What ran: `crawl --sources foreverdb` over all 55 seeded chapters
(676 seeds -> 1043 quest pages, 0 failed), then `build` and `diff
--addon-dir <MainStoryGuide/MainStoryGuide>`.

What did NOT run:
- `--rxp`: no local Forever/RXP guide files were available.
- Wowhead (Forever and Classic): HTTP 403 from this environment.
- Endgame / mid-game seeds were not added in this run.

## Result: gaps are NOT clean
Rule applied (from the maintainer): a quest is main story only if it is in
the required quest chain online. Finding: the databases list every race's
variant of a quest as a "before" link (alternatives, not requirements), so
closure merged all races into each chapter. `expand_from_seeds` and
`find_gaps` now ignore quests gated to the other faction or to a different,
non-shared-start race (Dwarf/Gnome and Orc/Troll share starters). Curated
seeds are never filtered.

After that fix `gaps.md` had 175 open entries. Maintainer then decided
the Camping 101 profession tutorials (35 quests, 95998 and family) are not
main story; they are excluded from every chapter with a race via the
top-level `exclude_in_race_chapters` in `seeds.json` (the two Skyborne
chapters, which have no race, still list them). Now `gaps.md` has
**110 open entries** (48 open_tail, 46 open_head, 13 orphan_link,
3 unbridged_chapter), none triaged. Not clean.

Open: starter chapters are many parallel quest lines, not one chain, so a
linear `storyline.md` per race still needs a main-chain extraction rule.

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
