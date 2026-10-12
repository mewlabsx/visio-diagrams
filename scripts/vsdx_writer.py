"""Generate a native, editable .vsdx directly in Python -- no Visio, no COM.

Shapes are genuine master instances copied from the installed Visio stencil
(BASFLO_M.VSSX); connectors are Dynamic-connector master instances whose
geometry rows carry the planner's verified orthogonal route, glued with
PAR(PNT(...)) formulas so they follow when a node is moved.

Input: the skill planner's planned.json (same schema as spec.json).
"""
import json
import argparse
import math
import re
import sys
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from containers import prepare, hierarchy, validate_geometry

STENCIL = r"C:\Program Files\Microsoft Office\Root\Office16\Visio Content\2052\BASFLO_M.VSSX"
BASE = Path(__file__).resolve().parent.parent / 'assets' / 'vsdx-base'
FONT = "Microsoft YaHei"
MIN_DIM = 0.19685039370079      # Visio's default 1D thickness, used when a route is axis-aligned
THICKNESS = 109.34897296069 / 25.4   # Visio's default Height for a 1D connector, in inches


def local(tag):
    return tag.split("}")[-1]


def read_zip(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def _attr(head, name):
    m = re.search(r"\b%s\s*=\s*(['\"])(.*?)\1" % re.escape(name), head)
    return m.group(2) if m else None


def _set_attr(text, name, value):
    return re.sub(r"(\b%s\s*=\s*)(['\"])([^'\"]*)\2" % re.escape(name),
                  lambda m: m.group(1) + m.group(2) + value + m.group(2), text, count=1)


def master_conn_points(part):
    """[(row_ix, norm_x, norm_y)] for a master's Connection section."""
    root = ET.fromstring(part)
    shape = next((e for e in root.iter() if local(e.tag) == "Shape"), None)
    if shape is None:
        return []
    cells = {c.get("N"): c.get("V") for c in shape if local(c.tag) == "Cell"}
    w = float(cells.get("Width", 1) or 1)
    h = float(cells.get("Height", 1) or 1)
    out = []
    for sec in shape:
        if local(sec.tag) == "Section" and sec.get("N") == "Connection":
            for row in sec:
                if local(row.tag) != "Row":
                    continue
                x = y = 0.0
                for c in row:
                    if local(c.tag) == "Cell":
                        if c.get("N") == "X":
                            x = float(c.get("V") or 0)
                        elif c.get("N") == "Y":
                            y = float(c.get("V") or 0)
                out.append((int(row.get("IX")), x / w, y / h))
    return out


def load_masters(stencil=STENCIL):
    """Pair each <Master> metadata block with its geometry part via <Rel r:id>."""
    st = read_zip(stencil)
    raw = st["visio/masters/masters.xml"].decode("utf-8")
    rels = ET.fromstring(st["visio/masters/_rels/masters.xml.rels"])
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for m in re.finditer(r"<Master\b[^>]*>.*?</Master>", raw, re.S):
        blk = m.group(0)
        head = re.match(r"<Master\b[^>]*>", blk).group(0)
        nameu = _attr(head, "NameU")
        tgt = target.get(_attr(blk, "r:id"))
        if not nameu or not tgt or ("visio/masters/" + tgt) not in st:
            continue
        part = st["visio/masters/" + tgt]
        out[nameu] = {"meta": blk, "part": part, "conn": master_conn_points(part)}
    return out


def master_meta(block, new_id, new_rid):
    head = re.match(r"<Master\b[^>]*>", block).group(0)
    inner = block[len(head):block.rindex("</Master>")]
    return "%s%s</Master>" % (_set_attr(head, "ID", str(new_id)),
                              _set_attr(inner, "r:id", new_rid))


SIDE_TARGET = {"bottom": (0.5, 0.0), "top": (0.5, 1.0), "left": (0.0, 0.5), "right": (1.0, 0.5)}


def pick_point(conn, side):
    """(row_ix, norm_x, norm_y) of the connection nearest the requested side."""
    tx, ty = SIDE_TARGET[side]
    best, bd = None, None
    for ix, nx, ny in conn:
        d = (nx - tx) ** 2 + (ny - ty) ** 2
        if bd is None or d < bd:
            best, bd = (ix, nx, ny), d
    return best


def row_number(conn, side):
    """1-based ShapeSheet row number: Connections.X<n> / ToPart = 99 + n."""
    p = pick_point(conn, side)
    return (p[0] + 1) if p else 1


def side_point(node, side, conn):
    """Absolute top-down page point of the glued connection on the given side."""
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    p = pick_point(conn, side)
    if p:
        return (x + p[1] * w, y + (1 - p[2]) * h)
    return {"top": (x + w / 2, y), "bottom": (x + w / 2, y + h),
            "left": (x, y + h / 2), "right": (x + w, y + h / 2)}[side]


# connection points for shapes with no stencil master (same order as BASFLO:
# IX 0=left 1=right 2=bottom 3=top), so edge midpoints stay connectable
SELF_CONN = [(0, 0.0, 0.5), (1, 1.0, 0.5), (2, 0.5, 0.0), (3, 0.5, 1.0)]


def _conn_formula(axis, side_ix):
    x = {0: "0", 1: "Width", 2: "Width*0.5", 3: "Width*0.5"}[side_ix]
    y = {0: "Height*0.5", 1: "Height*0.5", 2: "0", 3: "Height"}[side_ix]
    return x if axis == "X" else y


def connection_section(w, h, extra=()):
    """Scaled connection points (IX 0=left 1=right 2=bottom 3=top, as BASFLO).

    Written per instance because an inherited section keeps the stencil's cached
    coordinates; without this the glue lands at the 25mm-native offsets.
    """
    pts = [(0.0, h / 2.0), (w, h / 2.0), (w / 2.0, 0.0), (w / 2.0, h)]
    pts.extend((nx * w, ny * h) for nx, ny in extra)
    out = ["<Section N='Connection'>"]
    for ix, (x, y) in enumerate(pts):
        out.append("<Row T='Connection' IX='%d'>"
                   "<Cell N='X' V='%s' F='Width*%s'/><Cell N='Y' V='%s' F='Height*%s'/>"
                   "<Cell N='DirX' V='0' F='No Formula'/><Cell N='DirY' V='0' F='No Formula'/>"
                   "<Cell N='Type' V='0' F='No Formula'/><Cell N='AutoGen' V='0' F='No Formula'/>"
                   "<Cell N='Prompt' V='' F='No Formula'/></Row>"
                   % (ix, num(x), num(x / w if w else 0), num(y), num(y / h if h else 0)))
    out.append("</Section>")
    return "".join(out)


def num(v):
    return ("%.10g" % float(v))


def poly_geom(pts, w, h):
    """Closed polygon geometry scaled to the instance size.

    Visio rewrites an instance's geometry when it resizes a dropped master; a
    shape that only inherits the master keeps the stencil's native 25mm outline.
    V must carry the evaluated value and F the Width/Height-relative formula.
    """
    out = ["<Section N='Geometry' IX='0'><Cell N='NoFill' V='0'/><Cell N='NoLine' V='0'/>"
           "<Cell N='NoShow' V='0'/><Cell N='NoSnap' V='0'/><Cell N='NoQuickDrag' V='0'/>"]
    for i, (x, y) in enumerate(pts):
        out.append("<Row T='%s' IX='%d'><Cell N='X' V='%s' F='Width*%s'/>"
                   "<Cell N='Y' V='%s' F='Height*%s'/></Row>"
                   % ("MoveTo" if i == 0 else "LineTo", i + 1,
                      num(x), num(x / w if w else 0), num(y), num(y / h if h else 0)))
    out.append("</Section>")
    return "".join(out)


def shape_geom(kind, w, h):
    if kind == "ellipse":
        return ellipse_geom(w, h)
    if kind == "diamond":
        return poly_geom([(0, h / 2.0), (w / 2.0, h), (w, h / 2.0), (w / 2.0, 0), (0, h / 2.0)], w, h)
    return poly_geom([(0, 0), (w, 0), (w, h), (0, h), (0, 0)], w, h)


def ellipse_geom(w, h):
    """Self-drawn ellipse. V must carry the evaluated value, not 0."""
    return ("<Section N='Geometry' IX='0'>"
            "<Cell N='NoFill' V='0'/><Cell N='NoLine' V='0'/><Cell N='NoShow' V='0'/>"
            "<Cell N='NoSnap' V='0'/><Cell N='NoQuickDrag' V='0'/>"
            "<Row T='Ellipse' IX='1'>"
            "<Cell N='X' V='%s' F='Width*0.5'/><Cell N='Y' V='%s' F='Height*0.5'/>"
            "<Cell N='A' V='%s' U='DL' F='Width*1'/><Cell N='B' V='%s' U='DL' F='Height*0.5'/>"
            "<Cell N='C' V='%s' U='DL' F='Width*0.5'/><Cell N='D' V='%s' U='DL' F='Height*1'/>"
            "</Row></Section>" % (num(w / 2.0), num(h / 2.0), num(w), num(h / 2.0), num(w / 2.0), num(h)))


def fmt_cells(pairs):
    out = []
    sections = {'Character': [], 'Paragraph': []}
    for name, v, u in pairs:
        target = out
        if name.startswith('Char.'):
            name = name.split('.', 1)[1]
            target = sections['Character']
        elif name.startswith('Para.'):
            name = name.split('.', 1)[1]
            target = sections['Paragraph']
        if name in ('Font', 'AsianFont'):
            target.append("<Cell N='%s' V='1' F='FONT(&quot;%s&quot;)'/>" % (name, FONT))
        else:
            target.append("<Cell N='%s' V='%s'%s/>" % (name, num(v) if isinstance(v, float) else v,
                                                    (" U='%s'" % u) if u else ""))
    for name, cells in sections.items():
        if cells:
            out.append("<Section N='%s'><Row IX='0'>%s</Row></Section>" % (name, ''.join(cells)))
    return "".join(out)


def text_el(txt):
    return "<Text><cp IX='0'/><pp IX='0'/>%s\n</Text>" % escape(txt) if txt else ""


def build(spec, stencil=STENCIL):
    masters = load_masters(stencil)
    by_kind = {"box": "Process", "diamond": "Decision", "terminator": "Start/End"}
    nodes = spec["nodes"]
    node_map, parents, children, ancestors = hierarchy(spec)
    node_ids = {n['id']: i + 1 for i, n in enumerate(nodes)}
    ph = float(spec["page"]["height"])
    pw = float(spec["page"]["width"])

    chosen = {}
    for n in nodes:
        nm = n.get("master") or by_kind.get(n.get("kind") or "box")
        if nm and nm not in by_kind.values():
            raise ValueError('Unsupported master geometry: ' + nm)
        if nm and nm not in masters:
            raise ValueError('Required stencil master missing: ' + nm)
        if nm and nm in masters:
            chosen[n["id"]] = nm

    if 'Dynamic connector' not in masters:
        raise ValueError('Required stencil master missing: Dynamic connector')
    # Fractional ports must exist as connection rows, not just route coordinates.
    extra = {n['id']: [] for n in nodes}
    edge_rows = []
    for e in spec['edges']:
        rows = []
        for end, default in (('from', 'bottom'), ('to', 'top')):
            side = e.get(end + 'Port') or default
            fraction = e.get(end + 'Fraction', .5)
            row = row_number(SELF_CONN, side)
            if abs(fraction - .5) > 1e-9:
                nx, ny = {'top': (fraction, 1), 'bottom': (fraction, 0),
                          'left': (0, 1-fraction), 'right': (1, 1-fraction)}[side]
                ports = extra[e[end]]
                point = (nx, ny)
                if point not in ports:
                    ports.append(point)
                row = 5 + ports.index(point)
            rows.append(row)
        edge_rows.append(rows)

    used = []
    for nm in list(chosen.values()) + ["Dynamic connector"]:
        if nm not in used:
            used.append(nm)
    mid = {nm: i + 1 for i, nm in enumerate(used)}

    shapes, connects = [], []
    sid = 0
    sheet = {}

    # ---- nodes ----
    for n in nodes:
        sid += 1
        sheet[n["id"]] = sid
        kind = n.get("kind") or "box"
        base = [("PinX", n["x"] + n["w"] / 2.0, None),
                ("PinY", ph - (n["y"] + n["h"] / 2.0), None),
                ("Width", n["w"], "IN"), ("Height", n["h"], "IN"),
                ("LocPinX", n["w"] / 2.0, "IN"), ("LocPinY", n["h"] / 2.0, "IN"),
                # text block: also cached in the master at the stencil's native
                # size, so it must be written per instance for text to centre
                ("TxtPinX", n["w"] / 2.0, "IN"), ("TxtPinY", n["h"] / 2.0, "IN"),
                ("TxtWidth", n["w"], "IN"), ("TxtHeight", n["h"], "IN"),
                ("TxtLocPinX", n["w"] / 2.0, "IN"), ("TxtLocPinY", n["h"] / 2.0, "IN")]
        base.append(("FillForegnd", n.get('fill') or '#FFFFFF', None))
        base.append(("FillPattern", '0' if kind == 'text' else '1', None))
        base.append(("LinePattern", '0' if kind == 'text' else ('2' if n.get('dashed') else '1'), None))
        base.append(('Rounding', min(n['w'], n['h']) / 2 if kind == 'terminator' else 0, 'IN'))
        if kind == 'container':
            # The title occupies a dedicated strip; the rest remains clear for members.
            header=n['headerHeight']
            base=[(key,value,unit) for key,value,unit in base if not key.startswith('Txt')]
            base.extend([('TxtPinX',n['w']/2,'IN'),('TxtPinY',n['h']-header/2,'IN'),
                         ('TxtWidth',n['w']-2*n['padding'],'IN'),('TxtHeight',header,'IN'),
                         ('TxtLocPinX',(n['w']-2*n['padding'])/2,'IN'),('TxtLocPinY',header/2,'IN')])
        base += [("LineColor", "#404040", None), ("LineWeight", 0.01041666666666667, "PT"),
                 ("Char.Font", None, None), ("Char.AsianFont", None, None),
                 ("Char.Size", (n.get("fontSize") or 11) / 72.0, "PT"),
                 ("Char.Color", "#000000", None),
                 ("Para.HorzAlign", "1", None), ("VerticalAlign", "1", None)]
        if n.get('bold'):
            base.append(('Char.Style', '1', None))
        m = chosen.get(n["id"])
        mattr = (" Master='%d'" % mid[m]) if m else ""
        body = fmt_cells(base)
        # Text frames must also follow instance resizing, not just initial caches.
        text_formulas={'LocPinX':'Width*0.5','LocPinY':'Height*0.5',
                       'TxtPinX':'Width*0.5','TxtPinY':'Height*0.5',
                       'TxtWidth':'Width','TxtHeight':'Height',
                       'TxtLocPinX':'Width*0.5','TxtLocPinY':'Height*0.5'}
        if kind=='container':
            text_formulas.update(TxtPinY='Height-%s in'%num(n['headerHeight']/2),
                                 TxtWidth='Width-%s in'%num(2*n['padding']),
                                 TxtHeight='%s in'%num(n['headerHeight']),
                                 TxtLocPinX='(Width-%s in)*0.5'%num(2*n['padding']),
                                 TxtLocPinY='%s in'%num(n['headerHeight']/2))
        for cell,formula in text_formulas.items():
            body=re.sub(r"(<Cell N='%s'[^>]*?)/>"%re.escape(cell),lambda m:m.group(1)+" F='%s'/>"%formula,body)
        relationships=[]
        if n['id'] in parents:
            relationships.append('DEPENDSON(4,Sheet.%d!SheetRef())'%node_ids[parents[n['id']]])
        if children[n['id']]:
            relationships.append('DEPENDSON(1,%s)'%','.join('Sheet.%d!SheetRef()'%node_ids[c] for c in children[n['id']]))
        if relationships:
            body += "<Cell N='Relationships' V='0' F='SUM(%s)'/>"%','.join(relationships)
        if kind=='container':
            body += "<Cell N='ShapePlaceStyle' V='15'/><Section N='User'><Row N='msvStructureType'><Cell N='Value' V='Container' U='STR'/></Row></Section>"
        # every shape carries its own scaled geometry and connection points
        body += shape_geom(kind, n["w"], n["h"])
        body += connection_section(n["w"], n["h"], extra[n['id']])
        body += text_el(n.get("text") or "")
        shapes.append("<Shape ID='%d' NameU='node_%s' IsCustomNameU='1' Name='node_%s' IsCustomName='1' "
                      "Type='Shape'%s>%s</Shape>" % (sid, escape(n['id'], {"'": '&apos;', '"': '&quot;'}), escape(n['id'], {"'": '&apos;', '"': '&quot;'}), mattr, body))

    # ---- title (mirrors the COM renderer: y 0.1..0.55 across the page) ----
    if spec["page"].get("title"):
        sid += 1
        tw = pw - 0.6
        shapes.append("<Shape ID='%d' NameU='diagram_title' IsCustomNameU='1' Name='diagram_title' "
                      "IsCustomName='1' Type='Shape'>%s%s</Shape>"
                      % (sid, fmt_cells([("PinX", pw / 2.0, None), ("PinY", ph - 0.325, None),
                                         ("Width", tw, "IN"), ("Height", 0.45, "IN"),
                                         ('LocPinX', tw/2, 'IN'), ('LocPinY', .225, 'IN'),
                                         ('TxtPinX', tw/2, 'IN'), ('TxtPinY', .225, 'IN'),
                                         ('TxtWidth', tw, 'IN'), ('TxtHeight', .45, 'IN'),
                                         ('TxtLocPinX', tw/2, 'IN'), ('TxtLocPinY', .225, 'IN'),
                                         ("Char.Font", None, None), ("Char.AsianFont", None, None),
                                         ("Char.Size", 16 / 72.0, "PT"), ("Char.Color", "#000000", None),
                                         ('Char.Style', '1', None), ('Para.HorzAlign', '1', None), ('VerticalAlign', '1', None),
                                         ("FillPattern", "0", None), ("LinePattern", "0", None)]),
                         text_el(spec["page"]["title"])))

    # ---- connectors ----
    node_by_id = {n["id"]: n for n in nodes}
    edge_no = 0
    for e in spec["edges"]:
        edge_no += 1
        a, b = node_by_id[e["from"]], node_by_id[e["to"]]
        ca = cb = SELF_CONN
        fp, tp = e.get("fromPort") or "bottom", e.get("toPort") or "top"
        ra, rb = edge_rows[edge_no - 1]
        pa = side_point(a, fp, ca)
        pb = side_point(b, tp, cb)
        if ra > 4:
            nx, ny = extra[a['id']][ra - 5]
            pa = (a['x'] + nx*a['w'], a['y'] + (1-ny)*a['h'])
        if rb > 4:
            nx, ny = extra[b['id']][rb - 5]
            pb = (b['x'] + nx*b['w'], b['y'] + (1-ny)*b['h'])
        pts = e.get("routePoints") or [pa, pb]
        if any(math.dist(p, q) > 1e-6 for p, q in ((pts[0], pa), (pts[-1], pb))):
            raise ValueError('Route endpoints disagree with glued ports on edge %d' % edge_no)
        vpts = [(float(p[0]), ph - float(p[1])) for p in pts]
        ax, ay = vpts[0]
        bx, by = vpts[-1]
        sid += 1
        # Visio 1D connector: the shape's frame is rotated onto Begin->End and the
        # route is stored in that rotated frame. Deriving Pin/Width/Angle from
        # Begin/End (exactly as Visio does) is what keeps the glue elastic.
        ang = math.atan2(by - ay, bx - ax)
        cw = math.hypot(bx - ax, by - ay)
        ch = THICKNESS
        lpx, lpy = cw * 0.5, ch * 0.68055555555556
        px_, py_ = (ax + bx) / 2.0, (ay + by) / 2.0
        ca, sa = math.cos(ang), math.sin(ang)
        ox = px_ - (lpx * ca - lpy * sa)
        oy = py_ - (lpx * sa + lpy * ca)
        rows = []
        for i, (x, y) in enumerate(vpts):
            u, v = x - ox, y - oy
            rows.append("<Row T='%s' IX='%d'><Cell N='X' V='%s'/><Cell N='Y' V='%s'/></Row>"
                        % ("MoveTo" if i == 0 else "LineTo", i + 1,
                           num(u * ca + v * sa), num(-u * sa + v * ca)))
        rows.append("<Row T='LineTo' IX='%d' Del='1'/>" % (len(vpts) + 1))
        geom = ("<Section N='Geometry' IX='0'><Cell N='NoFill' V='1'/><Cell N='NoLine' V='0'/>"
                "<Cell N='NoShow' V='0'/><Cell N='NoSnap' V='0'/><Cell N='NoQuickDrag' V='0'/>%s</Section>"
                % "".join(rows))
        body = ("<Cell N='PinX' V='%s' F='(BeginX+EndX)/2'/><Cell N='PinY' V='%s' F='(BeginY+EndY)/2'/>"
                "<Cell N='Width' V='%s' F='SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)'/>"
                "<Cell N='Height' V='%s' F='%s in'/>"
                "<Cell N='LocPinX' V='%s' F='Width*0.5'/><Cell N='LocPinY' V='%s' F='Height*0.68055555555556'/>"
                "<Cell N='Angle' V='%s' F='ATAN2(EndY-BeginY,EndX-BeginX)'/>"
                "<Cell N='FlipX' V='0' F='FALSE'/><Cell N='FlipY' V='0' F='FALSE'/>"
                % (num(px_), num(py_), num(cw), num(ch), num(ch), num(lpx), num(lpy), num(ang)))
        for cell, val, sheetid, row in (("BeginX", ax, sheet[e["from"]], ra), ("BeginY", ay, sheet[e["from"]], ra),
                                        ("EndX", bx, sheet[e["to"]], rb), ("EndY", by, sheet[e["to"]], rb)):
            body += ("<Cell N='%s' V='%s' F='PAR(PNT(Sheet.%d!Connections.X%d,Sheet.%d!Connections.Y%d))'/>"
                     % (cell, num(val), sheetid, row, sheetid, row))
        body += ("<Cell N='BegTrigger' V='2' F='_XFTRIGGER(Sheet.%d!EventXFMod)'/>"
                 "<Cell N='EndTrigger' V='2' F='_XFTRIGGER(Sheet.%d!EventXFMod)'/>" % (sheet[e["from"]], sheet[e["to"]]))
        body += ("<Cell N='LineWeight' V='0.01041666666666667' U='PT'/><Cell N='LineColor' V='#404040'/>"
                 "<Cell N='BeginArrow' V='0'/><Cell N='EndArrow' V='4'/>")
        body += "<Cell N='LinePattern' V='%s'/>" % ('2' if e.get('dashed') else '1')
        body += fmt_cells([('Char.Font', None, None), ('Char.AsianFont', None, None), ('Char.Size', 10/72, 'PT')])
        body += geom
        if e.get('text') and not e.get('label'):
            # Connector Height is a frame convention, not the text block height.
            # Inheriting the master's Txt* caches places labels far below the route.
            lines = e['text'].split('\n')
            text_w = max(.3, max(sum(1 if ord(c)>127 else .6 for c in line) for line in lines)*10/72+.12)
            text_h = len(lines)*10/72*1.3+.08
            body += fmt_cells([('TxtPinX', lpx + sa*.14, 'IN'), ('TxtPinY', lpy + ca*.14, 'IN'),
                               ('TxtWidth', text_w, 'IN'), ('TxtHeight', text_h, 'IN'),
                               ('TxtLocPinX', text_w/2, 'IN'), ('TxtLocPinY', text_h/2, 'IN'),
                               ('TxtAngle', -ang, None)])
            body += fmt_cells([('Para.HorzAlign', '1', None), ('VerticalAlign', '1', None)])
            body += text_el(e['text'])
        shapes.append("<Shape ID='%d' NameU='edge_%d' IsCustomNameU='1' Name='edge_%d' IsCustomName='1' "
                      "Type='Shape' Master='%d'>%s</Shape>"
                      % (sid, edge_no, edge_no, mid["Dynamic connector"], body))
        connects.append("<Connect FromSheet='%d' FromCell='BeginX' FromPart='9' ToSheet='%d' ToCell='Connections.X%d' ToPart='%d'/>"
                        % (sid, sheet[e["from"]], ra, 99 + ra))
        connects.append("<Connect FromSheet='%d' FromCell='EndX' FromPart='12' ToSheet='%d' ToCell='Connections.X%d' ToPart='%d'/>"
                        % (sid, sheet[e["to"]], rb, 99 + rb))
        # independent edge label, if the planner placed one
        if e.get("label") and e.get("text"):
            lb = e["label"]
            sid += 1
            shapes.append("<Shape ID='%d' NameU='edge_label_%d' IsCustomNameU='1' Name='edge_label_%d' "
                          "IsCustomName='1' Type='Shape'>%s%s</Shape>"
                          % (sid, edge_no, edge_no,
                             fmt_cells([("PinX", lb["x"] + lb["w"] / 2.0, None),
                                        ("PinY", ph - (lb["y"] + lb["h"] / 2.0), None),
                                        ("Width", lb["w"], "IN"), ("Height", lb["h"], "IN"),
                                        ('LocPinX', lb['w']/2, 'IN'), ('LocPinY', lb['h']/2, 'IN'),
                                        ('TxtPinX', lb['w']/2, 'IN'), ('TxtPinY', lb['h']/2, 'IN'),
                                        ('TxtWidth', lb['w'], 'IN'), ('TxtHeight', lb['h'], 'IN'),
                                        ('TxtLocPinX', lb['w']/2, 'IN'), ('TxtLocPinY', lb['h']/2, 'IN'),
                                        ("Char.Font", None, None), ("Char.AsianFont", None, None),
                                        ("Char.Size", 10 / 72.0, "PT"), ("Char.Color", "#000000", None),
                                        ('Para.HorzAlign', '1', None), ('VerticalAlign', '1', None),
                                        ("FillPattern", "0", None), ("LinePattern", "0", None)]),
                             text_el(e["text"])))

    page = ("<?xml version='1.0' encoding='utf-8' ?>\n"
            "<PageContents xmlns='http://schemas.microsoft.com/office/visio/2012/main' "
            "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships' "
            "xml:space='preserve'><Shapes>%s</Shapes><Connects>%s</Connects></PageContents>"
            % ("".join(shapes), "".join(connects)))

    mx, rl = [], []
    for i, nm in enumerate(used, start=1):
        mx.append(master_meta(masters[nm]["meta"], i, "rId%d" % i))
        rl.append("<Relationship Id='rId%d' Type='http://schemas.microsoft.com/visio/2010/relationships/master' Target='master%d.xml'/>" % (i, i))
    masters_xml = ("<?xml version='1.0' encoding='utf-8' ?>\n<Masters xmlns='http://schemas.microsoft.com/office/visio/2012/main' "
                   "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships' xml:space='preserve'>%s</Masters>"
                   % "".join(mx))
    return page, masters_xml, rl, used, masters, pw, ph


def write_vsdx(spec, out, stencil=STENCIL):
    spec = prepare(spec)
    validate_spec(spec)
    out = Path(out)
    if out.exists():
        raise FileExistsError('Refusing to overwrite: ' + str(out))
    page, masters_xml, rels, used, masters, pw, ph = build(spec, stencil)
    tpl = {'visio/document.xml': (BASE/'document.xml').read_bytes(),
           'visio/pages/pages.xml': (BASE/'pages.xml').read_bytes(),
           'visio/windows.xml': (BASE/'windows.xml').read_bytes(),
           '_rels/.rels': b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/></Relationships>'}

    pages_xml = tpl["visio/pages/pages.xml"].decode("utf-8")
    pages_xml = re.sub(r"(N=[\"']PageWidth[\"'][^/]*?V=[\"'])[\d.]+", r"\g<1>%s" % num(pw), pages_xml)
    pages_xml = re.sub(r"(N=[\"']PageHeight[\"'][^/]*?V=[\"'])[\d.]+", r"\g<1>%s" % num(ph), pages_xml)

    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="emf" ContentType="image/x-emf"/>',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>',
          '<Override PartName="/visio/masters/masters.xml" ContentType="application/vnd.ms-visio.masters+xml"/>']
    for i in range(1, len(used) + 1):
        ct.append('<Override PartName="/visio/masters/master%d.xml" ContentType="application/vnd.ms-visio.master+xml"/>' % i)
    ct += ['<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>',
           '<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>',
           '<Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>',
           '</Types>']

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct).encode("utf-8"))   # must be first
        z.writestr("_rels/.rels", tpl["_rels/.rels"])
        z.writestr("visio/document.xml", tpl["visio/document.xml"])
        z.writestr("visio/windows.xml", tpl["visio/windows.xml"])
        z.writestr("visio/pages/pages.xml", pages_xml.encode("utf-8"))
        z.writestr("visio/pages/page1.xml", page.encode("utf-8"))
        z.writestr("visio/pages/_rels/pages.xml.rels",
                   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   "<Relationship Id='rId1' Type='http://schemas.microsoft.com/visio/2010/relationships/page' Target='page1.xml'/></Relationships>")
        z.writestr("visio/_rels/document.xml.rels",
                   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   "<Relationship Id='rId1' Type='http://schemas.microsoft.com/visio/2010/relationships/masters' Target='masters/masters.xml'/>"
                   "<Relationship Id='rId2' Type='http://schemas.microsoft.com/visio/2010/relationships/pages' Target='pages/pages.xml'/>"
                   "<Relationship Id='rId3' Type='http://schemas.microsoft.com/visio/2010/relationships/windows' Target='windows.xml'/></Relationships>")
        z.writestr("visio/masters/masters.xml", masters_xml.encode("utf-8"))
        z.writestr("visio/masters/_rels/masters.xml.rels",
                   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   + "".join(rels) + "</Relationships>")
        for i, nm in enumerate(used, start=1):
            z.writestr("visio/masters/master%d.xml" % i, masters[nm]["part"])
        for p in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
            if p in tpl:
                z.writestr(p, tpl[p])
    return used


def validate_spec(spec):
    validate_geometry(spec)
    def number(value):
        return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)
    pw, ph = spec['page']['width'], spec['page']['height']
    if not all(number(v) and v > 0 for v in (pw, ph)):
        raise ValueError('Invalid page dimensions')
    ids = set()
    kinds = {n['id']: n.get('kind') or 'box' for n in spec['nodes']}
    for n in spec['nodes']:
        if not isinstance(n.get('id'), str) or not n['id'] or n['id'] in ids:
            raise ValueError('Empty or duplicate node id')
        ids.add(n['id'])
        if n.get('kind', 'box') not in ('box', 'diamond', 'ellipse', 'terminator', 'text', 'container'):
            raise ValueError('Unsupported Python node kind: ' + str(n.get('kind')))
        if not all(number(n[k]) for k in ('x', 'y', 'w', 'h')):
            raise ValueError('Non-finite node dimensions')
        if n['x'] < 0 or n['y'] < 0 or n['w'] <= 0 or n['h'] <= 0 or n['x']+n['w'] > pw+1e-9 or n['y']+n['h'] > ph+1e-9:
            raise ValueError('Node outside page: ' + n['id'])
        if not isinstance(n.get('text', ''), str):
            raise ValueError('Node text must be a string')
        if n.get('fill') and not re.fullmatch(r'#[0-9a-fA-F]{6}', n['fill']):
            raise ValueError('Invalid node fill')
        if not number(n.get('fontSize', 11)) or n.get('fontSize', 11) <= 0:
            raise ValueError('Invalid font size')
    for e in spec['edges']:
        if e['from'] not in ids or e['to'] not in ids:
            raise ValueError('Unknown edge endpoint')
        for end in ('from', 'to'):
            if e.get(end+'Port') and e[end+'Port'] not in SIDE_TARGET:
                raise ValueError('Invalid edge port')
            f = e.get(end+'Fraction', .5)
            if not number(f) or not 0 <= f <= 1:
                raise ValueError('Invalid port fraction')
            if kinds[e[end]] in ('diamond','ellipse','terminator') and abs(f-.5)>1e-9:
                raise ValueError('Nonrectangular ports must use axis endpoints')
        for p in e.get('routePoints', []):
            if len(p) != 2 or not all(number(v) for v in p) or not 0 <= p[0] <= pw or not 0 <= p[1] <= ph:
                raise ValueError('Invalid route point')
        if e.get('routePoints') is not None and len(e['routePoints']) < 2:
            raise ValueError('Route needs at least two points')
        if e.get('label'):
            lb = e['label']
            if not all(number(lb[k]) for k in ('x','y','w','h')) or lb['x'] < 0 or lb['y'] < 0 or lb['w'] <= 0 or lb['h'] <= 0 or lb['x']+lb['w'] > pw or lb['y']+lb['h'] > ph:
                raise ValueError('Invalid label rectangle')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('output')
    parser.add_argument('--stencil', default=STENCIL)
    args = parser.parse_args()
    try:
        spec = json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
        used = write_vsdx(spec, args.output, args.stencil)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error))
    print('masters used:', used)
    print('wrote', args.output)
