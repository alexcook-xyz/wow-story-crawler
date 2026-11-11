# models.py - shared data shapes. Facts only: ids, names, links, levels,
# faction/race/class gates. No quest text, gossip, or journal prose.
from __future__ import annotations

from dataclasses import dataclass, field, asdict

FACTIONS = ("Alliance", "Horde", "Neutral")
RACES = ("Human", "Dwarf", "Night Elf", "Gnome",
         "Orc", "Undead", "Tauren", "Troll")
CLASSES = ("Warrior", "Paladin", "Priest", "Mage", "Warlock",
           "Rogue", "Hunter", "Druid", "Shaman")


@dataclass
class QuestFact:
    """One quest as claimed by ONE source. Sources never overwrite each
    other; graph.py merges facts and records disagreements."""

    qid: int
    source: str
    url: str = ""
    name: str | None = None
    before: list[int] = field(default_factory=list)   # must be done first
    after: list[int] = field(default_factory=list)    # unlocked by this
    reqlevel: int | None = None
    faction: str | None = None        # Alliance/Horde/Neutral when stated
    race: str | None = None           # set only when race-locked
    class_: str | None = None         # set only when class-locked
    zone: str | None = None
    giver: str | None = None

    def to_json(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("class_")
        return d

    @classmethod
    def from_json(cls, d: dict) -> "QuestFact":
        d = dict(d)
        d["class_"] = d.pop("class", None)
        return cls(**d)


@dataclass
class MergedQuest:
    qid: int
    name: str | None = None
    before: list[int] = field(default_factory=list)
    after: list[int] = field(default_factory=list)
    reqlevel: int | None = None
    faction: str | None = None
    race: str | None = None
    class_: str | None = None
    zone: str | None = None
    giver: str | None = None
    sources: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def class_specific(self) -> bool:
        return self.class_ is not None

    def to_json(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("class_")
        d["class_specific"] = self.class_specific
        return d


@dataclass
class SeedChapter:
    """A curated storyline seed. The crawler expands `seeds` to the full
    transitive chain; it never invents chapter membership on its own."""

    id: str
    name: str
    faction: str                      # Alliance / Horde / Neutral
    race: str | None = None           # None = shared by the whole faction
    zone: str | None = None
    order: int = 0                    # intended story order within faction
    min_level: int | None = None
    max_level: int | None = None
    seeds: list[int] = field(default_factory=list)   # quest ids, any point
    entry: int | None = None          # known first quest, when curated
    exit: int | None = None           # known last/lead-out quest
    next_chapter: str | None = None   # chapter this one's exit leads into
    exclude: list[int] = field(default_factory=list)  # pulled in, not story
    # Raid/dungeon attunement quests (curated ids). They are exempt from
    # the level-60 cutoff, and are tagged in the outputs, so a raid-gated
    # chain is not chopped at the boundary. Never guessed: list ids only
    # after checking them against the Forever database.
    attunement: list[int] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_json(cls, d: dict) -> "SeedChapter":
        known = {f for f in cls.__dataclass_fields__}
        bad = set(d) - known
        if bad:
            raise ValueError(f"seed {d.get('id')!r}: unknown keys {sorted(bad)}")
        return cls(**d)


@dataclass
class Gap:
    kind: str       # missing_page / open_head / open_tail / cycle /
                    # name_conflict / level_conflict / orphan_link /
                    # unbridged_chapter / unknown_quest
    detail: str
    qid: int | None = None
    chapter: str | None = None

    def line(self) -> str:
        where = f"[{self.chapter}] " if self.chapter else ""
        q = f"quest {self.qid}: " if self.qid else ""
        return f"- {self.kind}: {where}{q}{self.detail}"
