# Endgame chapter seeds (snapshot, issues #22-#27)

Seeds come from Forever DB name searches (`pd.zroot.it/forever/quests?search=<name>`), then the crawler closes each chain over the DB's before/after links. Nothing here comes from memory: every ID, level and link was read from the DB.

## Structure the crawl found

- `dragonflight_spine` (8286 -> 8555) is shared. 8555 fans out to three branches: `bwl_attunement` (Azuregos's ledger to the Wrath of Neptulon, 8575 -> 8729), `nefarian_arc` (8730) and `eranikus_awakening` (8733 -> 8741).
- All three converge on 8742 *The Might of Kalimdor*, which opens 8743 and 8745 (`aq_opening`). This is the real hand-off between the Blackwing/Nefarian arc and the Ahn'Qiraj gates (capstone #27).
- Molten Core: `mc_attunement` (7848, stand-alone) and `mc_hydraxis` (Azshara chain 6804/6805 -> 7486).
- Stratholme: `stratholme_dawn` is a linear 9-quest chain to Dawn's Gambit (4726 -> 4771).

| Chapter | Quests | Entry -> exit | Open | Explained |
|---|---|---|---|---|
| dragonflight_spine | 7 | 8286 -> 8555 | 0 | 1 |
| bwl_attunement | 14 | 8575 -> 8729 | 0 | 2 |
| bwl_blackhand | 1 | 7761 -> 7761 | 0 | 0 |
| nefarian_arc | 1 | 8730 -> 8730 | 0 | 2 |
| eranikus_awakening | 5 | 8733 -> 8741 | 0 | 2 |
| aq_opening | 3 | 8742 -> 8745 | 0 | 4 |
| eranikus_essence | 3 | 3373 -> 3512 | 0 | 0 |
| sunken_temple | 2 | 3445 -> 3445 | 0 | 4 |
| atalhakkar_prelude | 7 | 1448 -> 1475 | 0 | 0 |
| hakkar_egg | 8 | 3520 -> 8182 | 0 | 0 |
| zul_gurub | 3 | 8246 -> 8195 | 0 | 2 |
| aq_scepter | 3 | 8341 -> 8364 | 0 | 0 |
| cenarion_allegiance | 1 | 9338 -> 9338 | 0 | 0 |
| aq_conqueror | 6 | 8752 -> 8766 | 0 | 0 |
| aq_armaments | 3 | 8784 -> 8790 | 0 | 2 |
| naxx_attunement | 4 | 9121 -> 9120 | 0 | 1 |
| stratholme_dawn | 9 | 4726 -> 4771 | 0 | 0 |
| mc_attunement | 1 | 7848 -> 7848 | 0 | 0 |
| mc_hydraxis | 7 | 6804 -> 7486 | 0 | 1 |
| onyxia | 19 | 4182 -> 7497 | 0 | 0 |
| horde_onyxia | 17 | 4903 -> 7493 | 0 | 0 |
| blackrock | 2 | 4742 -> 4743 | 0 | 0 |
| dark_iron_war | 2 | 303 -> 378 | 0 | 0 |
| brd_dark_iron_legacy | 2 | 3801 -> 3802 | 0 | 0 |
| brd_kill_on_sight | 5 | 4081 -> 4132 | 0 | 0 |

## Not found in the Forever DB by name

Searched with no result: Lothos, Ragnaros, Thorium Brotherhood, Hydraxian, Warchief, Nefarian, Razorgore, Vaelastrasz, Emperor, Fordring, Redpath, Blackwing, Ahn'Qiraj, Orb of Command, Riftwalker. Before closing #22/#23/#26, find these under other names (or confirm Forever lacks them). The Horde Molten Core attunement is also unidentified.

## Still to decide

- `naxx_attunement` 9033 and 9233 each have 12 class-variant successors (9034-9046, 9234-9245); they are not seeded as story.
- `zul_gurub` and `aq_armaments` are stand-alone hand-ins with no links in the DB.
- `Pamela/Linken/Tirion` (#4): Pamela's chain sits in `eastern_plaguelands`; Linken is quests 3914/3942/3961; Tirion had no name hit.
