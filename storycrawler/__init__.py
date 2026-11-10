"""Story-crawler: build a gap-free linear main-story graph for WoW Forever.

Pipeline: seed chapters (quests known to belong to a storyline) -> crawl
each source page -> walk predecessor ("Before this") and successor links
until every chain head and tail is closed -> merge sources with
provenance -> linearise per race/faction to level 60 -> report gaps and
emit draft chapter data for human review. Nothing is written into the
addon data files automatically.
"""

__all__ = ["models", "fetcher", "parsers", "graph", "sources"]
__version__ = "0.1.0"
