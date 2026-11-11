# parsers.py - page HTML -> QuestFact. Regex/stdlib only, like the
# existing extractors. Parsers are defensive: a layout change yields an
# empty fact (recorded as a gap upstream), never a guessed link.
from __future__ import annotations

import html as _html
import re

from .models import CLASSES, FACTIONS, QuestFact, RACES


def _clean(text: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _dedupe(ids: list[int], self_id: int) -> list[int]:
    out: list[int] = []
    for i in ids:
        if i != self_id and i not in out:
            out.append(i)
    return out


def _h1(page: str) -> str | None:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    return _clean(m.group(1)) or None if m else None


def _gates(page_text: str) -> tuple[str | None, str | None, str | None]:
    """Heuristic faction/race/class gates from visible requirement text.
    Only fires on explicit phrasing; silence means unknown, not neutral."""
    faction = race = class_ = None
    for f in FACTIONS:
        if re.search(rf"\b(?:Faction|Side)\s*:?\s*{f}\b", page_text, re.I):
            faction = f
    m = re.search(r"\bRace\s*:?\s*([A-Z][A-Za-z ]+)", page_text)
    if m and m.group(1).strip() in RACES:
        race = m.group(1).strip()
    m = re.search(r"\bClass\s*:?\s*([A-Z][a-z]+)", page_text)
    if m and m.group(1).strip() in CLASSES:
        class_ = m.group(1).strip()
    return faction, race, class_


def _giver_card(page: str, label: str) -> tuple[str | None, str | None]:
    """'Starts at' / 'Hand in to' card -> (npc name, 'npc middle-dot ZONE
    at 0.xxx, 0.yyy' basis text). Both None when the card is absent."""
    m = re.search(rf"<dt><strong>{label}</strong></dt>(.*?)</(?:dl|dd)>",
                  page, re.S)
    if not m:
        return None, None
    seg = m.group(1)
    nm = re.search(r"/forever/npcs/\d+\">([^<]+)</a>", seg)
    bs = re.search(r'<span class="basis">(.*?)</span>', seg, re.S)
    name = _clean(nm.group(1)) if nm else None
    basis = _clean(bs.group(1)) if bs else None
    return name, basis


def _basis_zone_xy(basis: str | None) -> tuple[str | None, float | None,
                                               float | None]:
    """'npc middle-dot Loch Modan at 0.522, 0.694' -> (zone, x, y)."""
    if not basis:
        return None, None, None
    m = re.search(r"\S+\s*·\s*([^0-9<]+?)\s+at\s+([\d.]+)\s*,\s*([\d.]+)",
                  basis)
    if not m:
        return None, None, None
    try:
        return (m.group(1).strip(), round(float(m.group(2)) * 100, 1),
                round(float(m.group(3)) * 100, 1))
    except ValueError:
        return None, None, None


def parse_foreverdb(qid: int, page: str, url: str) -> QuestFact:
    """pd.zroot.it quest page: 'Before this' / 'After this' sections with
    /forever/quests/<id> links, 'requires level N', the 'level N Forever
    quest in ZONE' line, 'FACTION only' gates, and the giver card
    (NPC names, zones, mapId, 0-100 giver/turn-in coordinates)."""
    fact = QuestFact(qid=qid, source="foreverdb", url=url, name=_h1(page))
    for heading, attr in (("Before this", "before"), ("After this", "after"),
                          ("Followed by", "after")):
        m = re.search(rf"<h3>{heading}</h3>(.*?)(?:<h3>|</section>|$)",
                      page, re.S)
        if not m:
            continue
        ul = re.search(r'<ul class="plain-list">(.*?)</ul>', m.group(1), re.S)
        body = ul.group(1) if ul else ""
        ids = [int(x) for x in re.findall(r"/forever/quests/(\d+)", body)]
        setattr(fact, attr, _dedupe(getattr(fact, attr) + ids, qid))
    m = re.search(r"requires level (\d+)", page, re.I)
    if m:
        fact.reqlevel = int(m.group(1))
    m = re.search(r"level (\d+) Forever quest in ([A-Za-z' \-]+)", page)
    if m:
        fact.level = int(m.group(1))
        fact.zone = m.group(2).strip()
    m = re.search(r"\b(Alliance|Horde) only\b", page)
    if m:
        fact.faction = m.group(1)
    giver, gbasis = _giver_card(page, "Starts at")
    turnin, tbasis = _giver_card(page, "Hand in to")
    if giver:
        fact.giver = giver
    if turnin:
        fact.turnin = turnin
    gzone, gx, gy = _basis_zone_xy(gbasis)
    tzone, tx, ty = _basis_zone_xy(tbasis)
    if fact.zone is None:
        fact.zone = gzone or tzone
    if gx is not None:
        fact.gx, fact.gy = gx, gy
    if tx is not None:
        fact.tx, fact.ty = tx, ty
    m = re.search(r'id="map-givers-data">(\{.*?\})</script>', page, re.S)
    if m:
        import json as _json
        try:
            data = _json.loads(m.group(1))
        except ValueError:
            data = {}
        if isinstance(data.get("mapId"), int):
            fact.map_id = data["mapId"]
        for key, xk, yk in (("pickup", "gx", "gy"), ("turnIn", "tx", "ty")):
            pt = data.get(key) or {}
            try:
                x, y = round(float(pt["x"]) * 100, 1), round(
                    float(pt["y"]) * 100, 1)
            except (KeyError, TypeError, ValueError):
                continue
            if getattr(fact, xk) is None:
                setattr(fact, xk, x)
                setattr(fact, yk, y)
    gfaction, grace, gclass = _gates(_clean(page))
    if fact.faction is None:
        fact.faction = gfaction
    if fact.race is None:
        fact.race = grace
    if fact.class_ is None:
        fact.class_ = gclass
    return fact


def parse_wowhead(qid: int, page: str, url: str) -> QuestFact:
    """Wowhead quest page: a 'Series' list gives the ordered chain; the
    position of this quest in it yields before/after. Falls back to
    'Requires ... quest=<id>' links when no Series block is present."""
    source = "wowhead-forever" if "/forever/" in url else "wowhead-classic"
    name = _h1(page)
    if name is None:
        m = re.search(r"<title>(.*?)(?:\s*[-|]|$)</title>", page, re.S)
        name = _clean(m.group(1)) or None if m else None
    fact = QuestFact(qid=qid, source=source, url=url, name=name)
    m = re.search(r"Series</[^>]+>(.*?)(?:</ul>|</ol>|<h\d)", page, re.S)
    if m:
        series = _dedupe([int(x) for x in
                          re.findall(r"quest=(\d+)", m.group(1))], -1)
        if qid in series:
            i = series.index(qid)
            fact.before = series[:i][-1:]   # immediate predecessor(s) only:
            fact.after = series[i + 1:i + 2]  # the graph closes the rest
    if not fact.before:
        req = re.search(r"[Rr]equire[sd]?[^<]{0,80}?(?:quest=|quests/)(\d+)",
                        page)
        if req:
            fact.before = _dedupe([int(req.group(1))], qid)
    m = re.search(r"(?:Requires|Required) level[^\d]{0,20}(\d+)", page, re.I)
    if m:
        fact.reqlevel = int(m.group(1))
    fact.faction, fact.race, fact.class_ = _gates(_clean(page))
    return fact


def parse_rxp_lines(text: str) -> list[QuestFact]:
    """RestedXP guide text -> ordered accept facts. Consecutive distinct
    .accept steps for one guide imply order, NOT hard prerequisites, so
    links are recorded as 'after' hints on the earlier quest only."""
    facts: dict[int, QuestFact] = {}
    order: list[int] = []
    # Conditions ride on the `step` header (step << Alliance) and apply
    # to every .accept in that block; an accept-line condition wins.
    events: list[tuple[int, str]] = []
    step_cond = ""
    for line in text.splitlines():
        head = re.match(r"\s*step\b(.*)$", line)
        if head:
            m = re.search(r"<<\s*(.+)$", head.group(1))
            step_cond = m.group(1) if m else ""
            continue
        acc = re.match(r"\s*\.accept\s+(\d+)\b(.*)$", line)
        if acc:
            own = re.search(r"<<\s*(.+)$", acc.group(2))
            events.append((int(acc.group(1)),
                           own.group(1) if own else step_cond))
    for qid, c in events:
        if qid not in facts:
            facts[qid] = QuestFact(qid=qid, source="rxp")
            order.append(qid)
        if c:
            hit = [x for x in CLASSES if re.search(rf"\b{x}\b", c)
                   and not re.search(rf"!\s*{x}\b", c)]
            if len(hit) == 1:
                facts[qid].class_ = hit[0]
            if re.search(r"\bAlliance\b", c) and not re.search(r"\bHorde\b", c):
                facts[qid].faction = "Alliance"
            if re.search(r"\bHorde\b", c) and not re.search(r"\bAlliance\b", c):
                facts[qid].faction = "Horde"
    for prev, nxt in zip(order, order[1:]):
        if nxt not in facts[prev].after:
            facts[prev].after.append(nxt)
    return [facts[q] for q in order]


def parse_wiki_chain(page: str) -> list[int]:
    """warcraft.wiki.gg chain article -> ordered quest ids, for seeding.
    Accepts quest=<id> and /quests/<id> link shapes; order preserved."""
    ids = [int(x) for x in re.findall(r"(?:quest=|/quests/)(\d+)", page)]
    return _dedupe(ids, -1)


PARSERS = {
    "foreverdb": parse_foreverdb,
    "wowhead": parse_wowhead,
}
