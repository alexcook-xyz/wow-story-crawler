# sources.py - where facts come from, in trust order.
#
# 1. foreverdb  pd.zroot.it Forever quest pages. Primary: this is the
#    Forever database the addon already verifies against. Plain HTTPS.
# 2. rxp        Local RestedXP Forever guides on this PC. Offline, exact
#    accept/turn-in order; no network. Wins ties with Forever DB pages.
# 3. wowhead-forever / wowhead-classic  Advisory cross-check. Classic-era
#    databases carry Classic IDs and "Series" links, but bulk fetching is
#    often bot-walled; the fetcher stops that source on 403/429.
# 4. wiki       warcraft.wiki.gg quest-chain articles. Good for storyline
#    membership (which quests belong to a named saga), weak on exact
#    Forever availability. Used for seed discovery, never as sole proof.
#
# URL templates are configuration, not promises: if a host changes its
# scheme, fix the template here, not the parsers.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    parser: str            # key into parsers.PARSERS
    quest_url: str         # "" = not fetchable per-quest (local/wiki)
    trust: int             # lower wins on conflict
    note: str = ""


SOURCES: dict[str, Source] = {
    "foreverdb": Source(
        "foreverdb", "foreverdb",
        "https://pd.zroot.it/forever/quests/{qid}", 1,
        "Project database for the Forever server. Primary source."),
    "rxp": Source(
        "rxp", "rxp", "", 0,
        "Local RXPGuides Forever guide files. Offline; highest trust."),
    "wowhead-forever": Source(
        "wowhead-forever", "wowhead",
        "https://www.wowhead.com/forever/quest={qid}", 2,
        "Wowhead Forever mirror. Advisory; may bot-wall bulk fetches."),
    "wowhead-classic": Source(
        "wowhead-classic", "wowhead",
        "https://www.wowhead.com/classic/quest={qid}", 3,
        "Wowhead Classic database. Classic-only; Forever may differ."),
    "wiki": Source(
        "wiki", "wiki",
        "https://warcraft.wiki.gg/wiki/{slug}", 4,
        "Storyline articles. Seed discovery for saga membership."),
}

DEFAULT_CRAWL_SOURCES = ("foreverdb", "wowhead-forever", "wowhead-classic")
