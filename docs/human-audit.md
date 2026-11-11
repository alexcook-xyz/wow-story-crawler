# Human saga audit: crawl vs Data_Human.lua (snapshot)

Source: `python crawl_story.py --offline --addon-dir <MainStoryGuide/MainStoryGuide> diff`, Human chain ids only. Crawl-adds are candidates, not verdicts: a Human chain may deliberately omit a quest that another chapter owns. Verify in game before editing the addon.

- defias_brotherhood: crawl adds [165 (The Hermit), 214 (Red Silk Bandanas), 389 (Bazil Thredd), 391 (The Stockade Riots), 392 (The Curious Visitor), 393 (Shadow of the Past), 350 (Look to an Old Friend), 2745 (Infiltrating the Castle), 2746 (Items of Some Consequence), 434 (The Attack!), 394 (The Head of the Beast), 395 (Brotherhood's End), 396 (An Audience with the King)]
- duskwood_darkness: crawl adds [310 (Bitter Rivals), 311 (Return to Marleth), 312 (Tundra MacGrann's Stolen Stash), 313 (The Grizzled Den), 314 (Protecting the Herd), 315 (The Perfect Stout), 298 (Excavation Progress Report), 301 (Report to Ironforge), 302 (Powder to Ironband), 273 (Resupplying the Excavation), 454 (After the Ambush), 309 (Protecting the Shipment), 148 (Supplies from Darkshire), 149 (Ghost Hair Thread), 154 (Return the Comb), 157 (Deliver the Thread), 158 (Zombie Juice), 156 (Gather Rot Blossoms), 159 (Juice Delivery), 133 (Ghoulish Effigy), 134 (Ogre Thieves), 160 (Note to the Mayor), 251 (Translate Abercrombie's Note), 401 (Wait for Sirra to Finish), 252 (Translation to Ello), 253 (Bride of the Embalmer), 323 (Proving Your Worth), 269 (Seeking Wisdom), 270 (The Doomed Fleet), 321 (Lightforge Iron), 324 (The Lost Ingots), 322 (Blessed Arm), 325 (Armed and Ready)]
- duskwood_darkness: order differs addon=[55, 56, 57, 58, 95, 230, 262, 265, 266, 453, 268] crawl=[56, 57, 58, 95, 230, 262, 265, 266, 453, 268, 55]
- elwynn: crawl adds [33 (Wolves Across the Border), 783 (A Threat Within), 5261 (Eagan Peltskinner), 7, 15 (Investigate Echo Ridge), 21 (Skirmish at Echo Ridge), 96627 (The Adventurer), 18 (Brotherhood of Thieves), 85 (Lost Necklace), 86 (Pie for Billy), 84 (Back to Billy), 87 (Goldtooth), 40 (A Fishy Peril), 46 (Bounty on Murlocs), 59 (Cloth and Leather Armor)]
- elwynn: order differs addon=[3903, 3904, 3905, 62, 76, 35, 37, 45, 71, 39, 52, 11, 176, 123, 147, 239] crawl=[62, 76, 52, 11, 176, 123, 147, 239, 3903, 3904, 3905, 35, 37, 45, 71, 39]
- loch_modan: crawl adds [224 (In Defense of the King's Lands), 237 (In Defense of the King's Lands), 263 (In Defense of the King's Lands), 267 (The Trogg Threat), 217 (In Defense of the King's Lands)]
- missing_diplomat: crawl adds [1324 (The Missing Diplomat)]
- onyxia: crawl adds [7495 (Victory for the Alliance), 7496 (Celebrating Good Times), 7497 (The Journey Has Just Begun)]
- redridge: crawl adds [180 (WANTED: Lieutenant Fangore), 246 (Assessing the Threat), 98387 (Blackrock Blockade), 19 (Tharil'zun), 115 (Shadow Magic), 125 (The Lost Tools), 98386 (Alther's Mill)]
- redridge: order differs addon=[244, 20, 34, 89, 91] crawl=[244, 20, 34, 91, 89]
- stalvan: crawl adds [649 (Ripple Recovery), 650 (Ripple Recovery), 77 (A Sticky Situation)]
- stockade: crawl adds [373 (The Unsent Letter)]
