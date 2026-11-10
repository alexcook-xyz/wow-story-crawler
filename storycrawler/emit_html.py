# emit_html.py - render out/story-graph.json as a single self-contained
# interactive HTML quest-planning tree (no CDN, vanilla JS/SVG).
#
# Layout: one swimlane per chapter in story order, quest nodes in the
# chapter's topological order, edges for before/after links, entry/exit
# highlighting, click-a-node detail panel, zoom/pan, faction/race/chapter
# filters, and gap markers (multiple heads/tails, cycles).
from __future__ import annotations

import html
import json
from pathlib import Path


def _h(s: object) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def load_graph(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_html(data: dict) -> str:
    quests: dict = data.get("quests", {})
    chapters: list = data.get("chapters", [])

    # Position map: qid(str) -> (cx, cy, chapter_id, x_index)
    NODE_W, NODE_H, X_STEP, LANE_H = 132, 46, 168, 130
    TOP, LEFT = 56, 230
    lane_width = max([len(c.get("quests", [])) for c in chapters] + [1])
    width = LEFT + lane_width * X_STEP + 60
    height = TOP + len(chapters) * LANE_H + 40

    pos: dict[str, tuple] = {}
    for ci, ch in enumerate(chapters):
        cy = TOP + ci * LANE_H + LANE_H // 2
        for qi, qid in enumerate(ch.get("quests", [])):
            cx = LEFT + qi * X_STEP + NODE_W // 2
            pos[str(qid)] = (cx, cy, ch.get("id"), qi)

    # Edges (dedupe): union of before-edges and after-edges within layout.
    edges: list[tuple[str, str, bool]] = []
    seen: set[tuple[str, str]] = set()
    for qid_s, mq in quests.items():
        if not isinstance(mq, dict):
            continue
        for pred in (mq.get("before") or []):
            a, b = str(pred), str(qid_s)
            if a in pos and b in pos and (a, b) not in seen:
                seen.add((a, b))
                same = pos[a][2] == pos[b][2]
                edges.append((a, b, same))
        for succ in (mq.get("after") or []):
            a, b = str(qid_s), str(succ)
            if a in pos and b in pos and (a, b) not in seen:
                seen.add((a, b))
                same = pos[a][2] == pos[b][2]
                edges.append((a, b, same))

    parts: list[str] = []
    parts.append('<svg id="tree" viewBox="0 0 %d %d" xmlns='
                 '"http://www.w3.org/2000/svg">' % (width, height))
    parts.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" '
                 'refY="5" markerWidth="7" markerHeight="7" '
                 'orient="auto-start-reverse">'
                 '<path d="M0,0 L10,5 L0,10 z" fill="#5b6b7b"/></marker>'
                 '<marker id="arrx" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="7" markerHeight="7" '
                 'orient="auto-start-reverse">'
                 '<path d="M0,0 L10,5 L0,10 z" fill="#b3541e"/></marker>'
                 '</defs>')

    for ci, ch in enumerate(chapters):
        y = TOP + ci * LANE_H
        n = len(ch.get("quests", []))
        badges = []
        if len(ch.get("heads", []) or []) > 1:
            badges.append("multiple heads: %s"
                          % ", ".join(str(q) for q in ch["heads"]))
        if len(ch.get("tails", []) or []) > 1:
            badges.append("multiple tails: %s"
                          % ", ".join(str(q) for q in ch["tails"]))
        if ch.get("in_cycle"):
            badges.append("cycle: %s"
                          % ", ".join(str(q) for q in ch["in_cycle"]))
        badge = (" <span class='gap'>GAP: %s</span>" % _h("; ".join(badges))
                 if badges else "")
        lane_label = ("<text x='12' y='%d' class='lane-label'>%s</text>"
                      % (y + 24, _h(ch.get("name", ch.get("id")))))
        lane_meta = ("<text x='12' y='%d' class='lane-meta'>%s%s%s</text>"
                     % (y + 42, _h(ch.get("faction", "") or ""),
                        (" / " + _h(ch.get("race") or "") if ch.get("race")
                         else ""),
                        (" · %d quests" % n)))
        parts.append("<g class='lane' data-chapter='%s' "
                     "data-faction='%s' data-race='%s'>"
                     % (_h(ch.get("id")), _h(ch.get("faction", "") or ""),
                        _h(ch.get("race", "") or "")))
        parts.append("<rect x='0' y='%d' width='%d' height='%d' "
                     "class='lane-bg'/>" % (y, width, LANE_H))
        parts.append(lane_label)
        parts.append(lane_meta)
        if badges:
            parts.append("<text x='12' y='%d' class='lane-gap'>GAP: %s</text>"
                         % (y + 60, _h("; ".join(badges))))
        parts.append("</g>")
        _ = badge  # lane gap text carries the marker; badge unused in DOM

    # Edges under nodes.
    for a, b, same in edges:
        ax, ay, _, _ = pos[a]
        bx, by, _, _ = pos[b]
        x1 = ax + NODE_W // 2
        x2 = bx - NODE_W // 2
        if same and ay == by:
            parts.append("<line x1='%d' y1='%d' x2='%d' y2='%d' "
                         "class='edge' marker-end='url(#arr)' "
                         "data-a='%s' data-b='%s'/>"
                         % (x1, ay, x2, by, _h(a), _h(b)))
        else:
            mx = (x1 + x2) / 2
            parts.append("<path d='M%d,%d C%.0f,%d %.0f,%d %d,%d' "
                         "class='edge edge-x' marker-end='url(#arrx)' "
                         "data-a='%s' data-b='%s'/>"
                         % (x1, ay, mx, ay, mx, by, x2, by, _h(a), _h(b)))

    # Nodes.
    for ci, ch in enumerate(chapters):
        cyc = {str(q) for q in (ch.get("in_cycle") or [])}
        entry = str(ch.get("entry")) if ch.get("entry") is not None else None
        exit_ = str(ch.get("exit")) if ch.get("exit") is not None else None
        for qid in ch.get("quests", []):
            qid_s = str(qid)
            cx, cy, _, _ = pos[qid_s]
            mq = quests.get(qid_s, {}) or {}
            cls = ["node"]
            if qid_s == entry:
                cls.append("entry")
            if qid_s == exit_:
                cls.append("exit")
            if qid_s in cyc:
                cls.append("cycle")
            name = mq.get("name") or qid_s
            short = name if len(name) <= 18 else name[:17] + "…"
            lvl = mq.get("reqlevel")
            parts.append("<g class='%s' data-qid='%s' "
                         "data-chapter='%s' tabindex='0'>"
                         % (" ".join(cls), _h(qid_s), _h(ch.get("id"))))
            parts.append("<rect x='%d' y='%d' width='%d' height='%d' rx='8'/>"
                         % (cx - NODE_W // 2, cy - NODE_H // 2,
                            NODE_W, NODE_H))
            parts.append("<text x='%d' y='%d' class='node-id'>%s</text>"
                         % (cx, cy - 6, _h(qid_s)))
            parts.append("<text x='%d' y='%d' class='node-name'>%s</text>"
                         % (cx, cy + 10, _h(short)))
            parts.append("<text x='%d' y='%d' class='node-lvl'>%s</text>"
                         % (cx, cy + 22,
                            _h(("lvl %s" % lvl) if lvl is not None else "")))
            parts.append("<title>%s</title>" % _h(name))
            parts.append("</g>")

    parts.append("</svg>")

    factions = sorted({c.get("faction", "") or "" for c in chapters
                       if c.get("faction")})
    races = sorted({c.get("race") or "" for c in chapters if c.get("race")})

    def opts(vals: list[str]) -> str:
        return ("<option value=''>All</option>"
                + "".join("<option value='%s'>%s</option>"
                          % (_h(v), _h(v)) for v in vals))

    ch_opts = ("<option value=''>All chapters</option>"
               + "".join("<option value='%s'>%s</option>"
                         % (_h(c.get("id")), _h(c.get("name",
                                                      c.get("id"))))
                         for c in chapters))

    data_json = json.dumps({"quests": quests, "chapters": chapters})
    css = (
        "body{font-family:sans-serif;margin:0;display:flex;height:100vh}"
        "#side{width:300px;min-width:260px;border-left:1px solid #ccc;"
        "padding:12px;overflow:auto;background:#fafafa}"
        "#main{flex:1;display:flex;flex-direction:column;overflow:hidden}"
        "#bar{padding:8px;border-bottom:1px solid #ccc;background:#f0f0f0;"
        "display:flex;gap:8px;flex-wrap:wrap;align-items:center}"
        "#wrap{flex:1;overflow:hidden;cursor:grab;background:#fff}"
        ".lane-bg{fill:#f7f9fb;stroke:#e2e6ea}"
        ".lane-label{font-size:15px;font-weight:bold;fill:#222}"
        ".lane-meta{font-size:11px;fill:#666}"
        ".lane-gap{font-size:11px;fill:#b3541e}"
        ".node rect{fill:#fff;stroke:#5b6b7b;stroke-width:1.5}"
        ".node.entry rect{stroke:#1a7f37;stroke-width:3}"
        ".node.exit rect{stroke:#0b5cad;stroke-width:3}"
        ".node.cycle rect{stroke:#b3541e;stroke-dasharray:5 3;"
        "stroke-width:2.5}"
        ".node.selected rect{fill:#fff8dc;stroke:#000}"
        ".node-id{font-size:10px;fill:#555;text-anchor:middle}"
        ".node-name{font-size:12px;font-weight:bold;text-anchor:middle}"
        ".node-lvl{font-size:10px;fill:#777;text-anchor:middle}"
        ".edge{stroke:#5b6b7b;stroke-width:1.5}"
        ".edge-x{stroke:#b3541e;stroke-dasharray:6 3;fill:none}"
        ".hidden{display:none}"
    )
    js = """(function(){
var svg=document.getElementById('tree');
var vb=svg.viewBox.baseVal;var start=null;
function setVB(x,y,w,h){vb.x=x;vb.y=y;vb.width=w;vb.height=h;}
document.getElementById('zin').onclick=function(){zoom(1/1.25);};
document.getElementById('zout').onclick=function(){zoom(1.25);};
document.getElementById('zreset').onclick=function(){setVB(0,0,W,H);};
function zoom(f){var cx=vb.x+vb.width/2,cy=vb.y+vb.height/2;
var w=Math.min(W,vb.width*f),h=w*H/W;
setVB(cx-w/2,cy-h/2,w,h);}
var wrap=document.getElementById('wrap');
wrap.addEventListener('wheel',function(e){e.preventDefault();
var r=svg.getBoundingClientRect();
var mx=vb.x+(e.clientX-r.left)/r.width*vb.width;
var my=vb.y+(e.clientY-r.top)/r.height*vb.height;
var f=e.deltaY>0?1.15:1/1.15;var w=Math.min(W,vb.width*f),h=w*H/W;
setVB(mx-(mx-vb.x)/vb.width*w,my-(my-vb.y)/vb.height*h,w,h);},
{passive:false});
svg.addEventListener('pointerdown',function(e){start={x:e.clientX,y:e.clientY,
vx:vb.x,vy:vb.y};wrap.style.cursor='grabbing';svg.setPointerCapture(e.pointerId);});
svg.addEventListener('pointermove',function(e){if(!start)return;
var r=svg.getBoundingClientRect();
setVB(start.vx-(e.clientX-start.x)/r.width*vb.width,
start.vy-(e.clientY-start.y)/r.height*vb.height,vb.width,vb.height);});
svg.addEventListener('pointerup',function(){start=null;wrap.style.cursor='grab';});
var DATA=JSON.parse(document.getElementById('graph-data').textContent);
var panel=document.getElementById('detail');
function show(qid){var q=DATA.quests[qid]||{};
var ch=(DATA.chapters||[]).filter(function(c){return (c.quests||[]).indexOf(Number(qid))>=0
||(c.quests||[]).indexOf(qid)>=0;})[0]||{};
function linkList(ids){if(!ids||!ids.length)return 'none';
return ids.map(function(i){return '<a href="#" data-go="'+i+'">'+i+'</a>';}).join(', ');}
var cls=q.class_specific?'yes':'no';
panel.innerHTML='<h3>Quest '+qid+'</h3>'
+'<p><b>'+esc(q.name||'?')+'</b></p>'
+'<p>Level: '+(q.reqlevel==null?'?':q.reqlevel)+'<br>'
+'Faction: '+esc(q.faction||'?')+'<br>'
+'Race: '+esc(q.race||'?')+'<br>'
+'Class-specific: '+cls+'<br>'
+'Chapter: '+esc(ch.name||ch.id||'?')+'<br>'
+'Entry: '+esc(ch.entry)+' · Exit: '+esc(ch.exit)+'</p>'
+'<p>Before (requires): '+linkList(q.before)+'</p>'
+'<p>After (unlocks): '+linkList(q.after)+'</p>'
+'<p>Sources: '+esc((q.sources||[]).join(', ')||'?')+'</p>'
+'<p>Conflicts: '+esc((q.conflicts||[]).join('; ')||'none')+'</p>';
panel.querySelectorAll('[data-go]').forEach(function(a){
a.onclick=function(e){e.preventDefault();show(a.getAttribute('data-go'));hi(a.getAttribute('data-go'));};});}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;')
.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function hi(qid){svg.querySelectorAll('.node').forEach(function(n){
n.classList.toggle('selected',n.getAttribute('data-qid')===String(qid));});}
svg.querySelectorAll('.node').forEach(function(n){
n.addEventListener('click',function(){show(n.getAttribute('data-qid'));hi(n.getAttribute('data-qid'));});
n.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){
show(n.getAttribute('data-qid'));hi(n.getAttribute('data-qid'));}});});
function applyFilters(){var f=document.getElementById('ffac').value;
var r=document.getElementById('frac').value;var c=document.getElementById('fch').value;
svg.querySelectorAll('.lane').forEach(function(l){
var ok=(!f||l.getAttribute('data-faction')===f)
&&(!r||l.getAttribute('data-race')===r)
&&(!c||l.getAttribute('data-chapter')===c);
l.classList.toggle('hidden',!ok);});
svg.querySelectorAll('.node').forEach(function(n){
var q=DATA.quests[n.getAttribute('data-qid')]||{};
var lane=svg.querySelector('.lane[data-chapter="'+n.getAttribute('data-chapter')+'"]');
var laneOk=!lane||!lane.classList.contains('hidden');
var qOk=(!f||!q.faction||q.faction===f||q.faction==='Neutral')
&&(!r||!q.race||q.race===r);
n.classList.toggle('hidden',!(laneOk&&qOk));});
svg.querySelectorAll('.edge,.edge-x').forEach(function(e){
var a=svg.querySelector('.node[data-qid="'+e.getAttribute('data-a')+'"]');
var b=svg.querySelector('.node[data-qid="'+e.getAttribute('data-b')+'"]');
var ok=(!a||!a.classList.contains('hidden'))&&(!b||!b.classList.contains('hidden'));
e.classList.toggle('hidden',!ok);});}
['ffac','frac','fch'].forEach(function(id){
document.getElementById(id).addEventListener('change',applyFilters);});
})();"""
    # Note: W/H injected below as constants for zoom math.
    doc = ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,"
           "initial-scale=1'>"
           "<title>WoW Forever - Main Story Map</title>"
           "<style>%s</style></head><body>"
           "<div id='main'><div id='bar'>"
           "<b>WoW Forever - Main Story Map</b>"
           "<label>Faction <select id='ffac'>%s</select></label>"
           "<label>Race <select id='frac'>%s</select></label>"
           "<label>Chapter <select id='fch'>%s</select></label>"
           "<button id='zin'>Zoom +</button>"
           "<button id='zout'>Zoom &#8722;</button>"
           "<button id='zreset'>Reset</button>"
           "<span class='lane-meta'>drag to pan, wheel to zoom, "
           "click a node for details</span>"
           "</div><div id='wrap'>%s</div></div>"
           "<div id='side'><h2>Detail</h2>"
           "<div id='detail'>Click a quest node.</div>"
           "<h2>Legend</h2><p class='lane-meta'>Green ring = chapter "
           "entry, blue ring = exit, dashed orange = in a before-link "
           "cycle, dashed orange edge = cross-chapter link, "
           "GAP badge = multiple heads/tails or cycle.</p></div>"
           "<script type='application/json' id='graph-data'>%s</script>"
           "<script>var W=%d,H=%d;\n%s</script>"
           "</body></html>"
           % (css, opts(factions), opts(races), ch_opts,
              "\n".join(parts), _h(data_json).replace("'", "&#x27;"),
              width, height, js))
    # Undo double-escaping inside the JSON script block: it was escaped
    # for HTML; keep valid JSON by only escaping <, >, &.
    safe_json = (data_json.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;"))
    doc = doc.replace(_h(data_json).replace("'", "&#x27;"), safe_json)
    return doc


def write_html(graph_path: Path, out_path: Path) -> Path:
    data = load_graph(graph_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(data), encoding="utf-8")
    return out
