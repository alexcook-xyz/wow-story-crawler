# models.py - shared data shapes. Facts only: ids, names, links, levels,
# faction/race/class gates. No quest text, gossip, or journal prose.
from __future__ import annotations

from dataclasses import dataclass, field, asdict

FACTIONS = ("Alliance", "Horde", "Neutral")
RACES = ("Human", "Dwarf", "Night Elf", "Gnome",
         "Orc", "Undead", "Tauren", "Troll")
GAP_KINDS = ("missing_page", "open_head", "open_tail", "cycle",
             "name_conflict", "level_conflict", "orphan_link",
             "unbridged_chapter", "unknown_quest", "level_cutoff",
             "tail_continues", "entry_has_pred", "exit_continues",
             "shared_member", "stale_decision")
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
    reqlevel: int | None = None       # minimum level to accept
    level: int | None = None          # quest level (difficulty), if shown
    faction: str | None = None        # Alliance/Horde/Neutral when stated
    race: str | None = None           # set only when race-locked
    class_: str | None = None         # set only when class-locked
    zone: str | None = None
    giver: str | None = None          # pickup NPC / object name
    turnin: str | None = None         # turn-in NPC / object name
    map_id: int | None = None         # UiMapID when the page states one
    gx: float | None = None           # giver x (0-100), when stated
    gy: float | None = None           # giver y (0-100), when stated
    tx: float | None = None           # turn-in x (0-100), when stated
    ty: float | None = None           # turn-in y (0-100), when stated

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
    level: int | None = None
    faction: str | None = None
    race: str | None = None
    class_: str | None = None
    zone: str | None = None
    giver: str | None = None
    turnin: str | None = None
    map_id: int | None = None
    gx: float | None = None
    gy: float | None = None
    tx: float | None = None
    ty: float | None = None
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
    notes: str = ""
    # `gate` names the raid/dungeon an attunement unlocks. A chapter with
    # a gate is an attunement: its level cap is lifted (raid-gated quests
    # are not silently dropped) and it is a terminal (no next_chapter).
    gate: str | None = None
    # Curated decisions: each names one gap by kind and the quests it covers
    # (qids), with the reason. A decision that matches no current gap is
    # reported as stale, so it cannot silently absorb a new gap.
    explained: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, d: dict) -> "SeedChapter":
        known = {f for f in cls.__dataclass_fields__}
        bad = set(d) - known
        if bad:
            raise ValueError(f"seed {d.get('id')!r}: unknown keys {sorted(bad)}")
        if d.get("gate") and d.get("next_chapter"):
            raise ValueError(f"seed {d.get('id')!r}: attunement chapters "
                             "are terminals; drop `next_chapter`")
        for dec in d.get("explained", []):
            if set(dec) != {"kind", "qids", "reason"}:
                raise ValueError(f"seed {d.get('id')!r}: a decision needs "
                                 "exactly kind, qids and reason")
            if dec["kind"] not in GAP_KINDS:
                raise ValueError(f"seed {d.get('id')!r}: decision kind "
                                 f"{dec['kind']!r} is not a gap kind")
            qids = dec["qids"]
            if (not isinstance(qids, list) or not qids
                    or not all(isinstance(q, int) for q in qids)):
                raise ValueError(f"seed {d.get('id')!r}: decision qids must "
                                 "be a non-empty list of quest ids")
            if not isinstance(dec["reason"], str) or not dec["reason"].strip():
                raise ValueError(f"seed {d.get('id')!r}: decision reason must "
                                 "be non-empty text")
        return cls(**d)

    @property
    def is_attunement(self) -> bool:
        return self.gate is not None


@dataclass
class Gap:
    kind: str       # one of GAP_KINDS (checked on construction)
    detail: str
    qid: int | None = None
    chapter: str | None = None
    explained: str | None = None    # reason, when a decision accounts for it
    members: tuple = ()             # quests the gap is about (its identity)

    def __post_init__(self) -> None:
        if self.kind not in GAP_KINDS:
            raise ValueError(f"gap kind {self.kind!r} not in GAP_KINDS")
        if not self.members and self.qid is not None:
            self.members = (self.qid,)

    def line(self) -> str:
        where = f"[{self.chapter}] " if self.chapter else ""
        q = f"quest {self.qid}: " if self.qid else ""
        why = f" -- explained: {self.explained}" if self.explained else ""
        return f"- {self.kind}: {where}{q}{self.detail}{why}"
