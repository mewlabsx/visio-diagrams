"""Offline structural regression tests for the Python VSDX writer.

No running Visio or COM; a local VSSX resource is required. This generates
the .vsdx and checks the currently supported package structure.  Every one of the 8 pitfalls hit during
development shows up here as a structural failure, so this is the FAST tier.
validate-vsdx.ps1 is the optional Visio tier (resolves Master.NameU, reads
saved routes via XYToPage, and does the move-the-node glue test).

Run:  python -X utf8 test_vsdx_writer.py
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "..", "assets", "k8s-activity-example.json")
WRITER = os.path.join(HERE, "vsdx_writer.py")

# the planner lives in the skill; look in the usual places
SKILL_CANDIDATES = [os.path.dirname(HERE)]
STENCIL = r"C:\Program Files\Microsoft Office\Root\Office16\Visio Content\2052\BASFLO_M.VSSX"
VNS = "{http://schemas.microsoft.com/office/visio/2012/main}"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def L(tag):
    return tag.split("}")[-1]


def find_skill():
    for c in SKILL_CANDIDATES:
        if os.path.isfile(os.path.join(c, "scripts", "local_layout.py")):
            return c
    return None


def cells(el):
    return {c.get("N"): c for c in el if L(c.tag) == "Cell"}


def sections(el):
    return {s.get("N"): s for s in el if L(s.tag) == "Section"}


def val(c):
    return float(c.get("V")) if c is not None and c.get("V") not in (None, "") else None


def local_to_page(lx, ly, pinx, piny, locpinx, locpiny, angle):
    """Inverse of the writer's rotated-frame transform."""
    ca, sa = math.cos(angle), math.sin(angle)
    ox = pinx - (locpinx * ca - locpiny * sa)
    oy = piny - (locpinx * sa + locpiny * ca)
    return (ox + lx * ca - ly * sa, oy + lx * sa + ly * ca)


class WriterContract(unittest.TestCase):
    planned = None
    pack = None          # {name: bytes}
    order = None         # zip entry order
    shapes = None        # list of page <Shape>
    connects = None
    masters = None       # list of (ID, NameU)
    ph = None

    @classmethod
    def setUpClass(cls):
        skill = find_skill()
        if not skill:
            raise unittest.SkipTest("skill scripts not found (local_layout.py)")
        if not os.path.isfile(STENCIL):
            raise unittest.SkipTest("BASFLO stencil not installed: " + STENCIL)
        if not os.path.isfile(SPEC):
            raise unittest.SkipTest("spec not found: " + SPEC)

        cls.temp_dir = tempfile.TemporaryDirectory(prefix="vsdxtest-", dir=HERE)
        cls.addClassCleanup(cls.temp_dir.cleanup)
        tmp = cls.temp_dir.name
        cls.planned_path = os.path.join(tmp, "planned.json")
        cls.vsdx_path = os.path.join(tmp, "out.vsdx")

        r = subprocess.run([sys.executable, "-X", "utf8",
                            os.path.join(skill, "scripts", "local_layout.py"),
                            SPEC, cls.planned_path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("planner failed: " + r.stderr.strip())

        r = subprocess.run([sys.executable, "-X", "utf8", WRITER,
                            cls.planned_path, cls.vsdx_path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("writer failed: " + r.stderr.strip())

        with open(cls.planned_path, encoding="utf-8") as fh:
            cls.planned = json.load(fh)
        cls.ph = float(cls.planned["page"]["height"])

        with zipfile.ZipFile(cls.vsdx_path) as z:
            cls.order = z.namelist()
            cls.pack = {n: z.read(n) for n in cls.order}

        page = ET.fromstring(cls.pack["visio/pages/page1.xml"])
        cls.shapes = [e for e in page if L(e.tag) == "Shapes"][0]
        cls.shapes = [e for e in cls.shapes if L(e.tag) == "Shape"]
        conns = [e for e in page if L(e.tag) == "Connects"]
        cls.connects = [e for e in conns[0] if L(e.tag) == "Connect"] if conns else []

        mx = ET.fromstring(cls.pack["visio/masters/masters.xml"])
        cls.masters = [e for e in mx if L(e.tag) == "Master"]

    def node_shapes(self):
        # node shapes are named node_<id>, matching render-visio.ps1's convention
        want = {"node_" + n["id"]: n["id"] for n in self.planned["nodes"]}
        return {n.get("NameU"): n for n in self.shapes if n.get("NameU") in want}

    def node(self, nid):
        return self.node_shapes()["node_" + nid]

    def edge_shapes(self):
        return {s.get("NameU"): s for s in self.shapes
                if (s.get("NameU") or "").startswith("edge_")
                and not (s.get("NameU") or "").startswith("edge_label_")}

    # ---- pitfall 1/2/3/4: package + master plumbing -----------------------

    def test_content_types_is_first_entry(self):
        """OPC requires [Content_Types].xml first (pitfall 4)."""
        self.assertEqual(self.order[0], "[Content_Types].xml")

    def test_every_xml_part_is_well_formed(self):
        for n in self.order:
            if n.endswith((".xml", ".rels")):
                with self.subTest(part=n):
                    ET.fromstring(self.pack[n])

    def test_no_elementtree_ns0_prefix(self):
        """pitfall 1: tostring() renames the default ns and Visio drops the page."""
        for n in ("visio/masters/masters.xml", "visio/pages/page1.xml"):
            self.assertNotIn(b"ns0:", self.pack[n], n)

    def test_master_holds_metadata_not_geometry(self):
        """pitfall 2: <Master> children must be PageSheet/Icon/Rel, not MasterContents."""
        for m in self.masters:
            kids = {L(c.tag) for c in m}
            with self.subTest(master=m.get("NameU")):
                self.assertNotIn("MasterContents", kids)
                self.assertIn("PageSheet", kids)
                self.assertTrue(kids <= {"PageSheet", "Icon", "Rel"}, kids)

    def test_master_rel_links_resolve(self):
        """pitfall 3: pairing is via <Rel r:id>, not positional order."""
        rels = ET.fromstring(self.pack["visio/masters/_rels/masters.xml.rels"])
        by_id = {r.get("Id"): r.get("Target") for r in rels}
        for m in self.masters:
            rel = next((c for c in m if L(c.tag) == "Rel"), None)
            self.assertIsNotNone(rel, "Master %s has no <Rel>" % m.get("NameU"))
            rid = rel.get("{%s}id" % RNS)
            self.assertIn(rid, by_id, "Rel r:id=%s not in masters.xml.rels" % rid)
            self.assertIn("visio/masters/" + by_id[rid], self.pack)

    def test_master_part_overrides_declared(self):
        """pitfall 4: every master part needs a Content_Types Override."""
        ct = self.pack["[Content_Types].xml"].decode("utf-8")
        for i in range(1, len(self.masters) + 1):
            self.assertIn('/visio/masters/master%d.xml' % i, ct)
            self.assertIn("visio/masters/master%d.xml" % i, self.order)

    # ---- counts ----------------------------------------------------------

    def test_shape_and_connect_counts(self):
        n_nodes = len(self.planned["nodes"])
        n_edges = len(self.planned["edges"])
        n_labels = sum(1 for e in self.planned["edges"] if e.get("label") and e.get("text"))
        n_title = 1 if self.planned["page"].get("title") else 0
        self.assertEqual(len(self.shapes), n_nodes + n_edges + n_labels + n_title)
        self.assertEqual(len(self.connects), 2 * n_edges,
                         "glued endpoints must be exactly 2 per edge")

    # ---- master choice ---------------------------------------------------

    def test_master_choice_per_kind(self):
        want = {"box": "Process", "diamond": "Decision", "terminator": "Start/End"}
        by_id = {m.get("ID"): m.get("NameU") for m in self.masters}
        for n in self.planned["nodes"]:
            s = self.node(n["id"])
            got = by_id.get(s.get("Master"))
            exp = want.get(n.get("kind") or "box")
            with self.subTest(node=n["id"]):
                self.assertEqual(got, exp)
        for name, s in self.edge_shapes().items():
            with self.subTest(edge=name):
                self.assertEqual(by_id.get(s.get("Master")), "Dynamic connector")

    # ---- pitfall 8: inherited cells must be written per instance ---------

    def test_geometry_scaled_to_instance(self):
        """pitfall 8: a dropped master keeps the stencil's native outline unless
        geometry is written per instance (symptom: 0.984x0.591 instead of 3x0.62)."""
        for n in self.planned["nodes"]:
            s = self.node(n["id"])
            geo = sections(s).get("Geometry")
            self.assertIsNotNone(geo, "%s has no Geometry section" % n["id"])
            rows = [r for r in geo if L(r.tag) == "Row"]
            with self.subTest(node=n["id"]):
                if any(r.get("T") == "Ellipse" for r in rows):
                    # an Ellipse row carries X,Y centre plus A,B,C,D extents
                    cs = {c.get("N"): val(c) for r in rows for c in r if L(c.tag) == "Cell"}
                    self.assertAlmostEqual(cs["A"], n["w"], places=6)
                    self.assertAlmostEqual(cs["D"], n["h"], places=6)
                else:
                    xs = [val(c) for r in rows for c in r
                          if L(c.tag) == "Cell" and c.get("N") == "X"]
                    ys = [val(c) for r in rows for c in r
                          if L(c.tag) == "Cell" and c.get("N") == "Y"]
                    self.assertAlmostEqual(max(xs), n["w"], places=6)
                    self.assertAlmostEqual(max(ys), n["h"], places=6)

    def test_text_block_scaled_to_instance(self):
        """pitfall 8: otherwise text hugs the stencil's native width (left-aligned)."""
        for n in self.planned["nodes"]:
            c = cells(self.node(n["id"]))
            with self.subTest(node=n["id"]):
                self.assertAlmostEqual(val(c["TxtWidth"]), n["w"], places=6)
                self.assertAlmostEqual(val(c["TxtPinX"]), n["w"] / 2.0, places=6)
                self.assertAlmostEqual(val(c["TxtLocPinX"]), n["w"] / 2.0, places=6)

    def test_connection_points_scaled_and_ordered(self):
        """pitfall 5+8: BASFLO rows are IX 0=left 1=right 2=bottom 3=top, and an
        inherited section keeps native offsets (glue then lands at x+0.4921)."""
        for n in self.planned["nodes"]:
            s = self.node(n["id"])
            sec = sections(s).get("Connection")
            self.assertIsNotNone(sec, "%s has no Connection section" % n["id"])
            rows = [r for r in sec if L(r.tag) == "Row"]
            self.assertEqual(len(rows), 4)
            pts = []
            for r in rows:
                cs = {c.get("N"): val(c) for c in r if L(c.tag) == "Cell"}
                pts.append((cs["X"], cs["Y"]))
            w, h = n["w"], n["h"]
            exp = [(0.0, h / 2.0), (w, h / 2.0), (w / 2.0, 0.0), (w / 2.0, h)]
            with self.subTest(node=n["id"]):
                for (gx, gy), (ex, ey) in zip(pts, exp):
                    self.assertAlmostEqual(gx, ex, places=6)
                    self.assertAlmostEqual(gy, ey, places=6)

    def test_ellipse_geometry_has_real_values(self):
        """pitfall 6: V must carry the evaluated value, not 0."""
        for n in self.planned["nodes"]:
            if (n.get("kind") or "box") != "ellipse":
                continue
            s = self.node(n["id"])
            row = next(r for r in sections(s)["Geometry"] if L(r.tag) == "Row")
            cs = {c.get("N"): val(c) for c in row if L(c.tag) == "Cell"}
            with self.subTest(node=n["id"]):
                self.assertAlmostEqual(cs["A"], n["w"], places=6)
                self.assertAlmostEqual(cs["D"], n["h"], places=6)
                self.assertGreater(cs["A"], 0)

    # ---- pitfall 7: 1D connector semantics -------------------------------

    def test_connector_cells_follow_visio_formulas(self):
        for name, s in self.edge_shapes().items():
            c = cells(s)
            with self.subTest(edge=name):
                self.assertEqual(c["PinX"].get("F"), "(BeginX+EndX)/2")
                self.assertEqual(c["PinY"].get("F"), "(BeginY+EndY)/2")
                self.assertTrue(c["Width"].get("F", "").startswith("SQRT("))
                self.assertEqual(c["Angle"].get("F"), "ATAN2(EndY-BeginY,EndX-BeginX)")
                self.assertEqual(c["LocPinX"].get("F"), "Width*0.5")

    def test_connector_endpoints_are_glued_formulas(self):
        for name, s in self.edge_shapes().items():
            c = cells(s)
            for cell in ("BeginX", "BeginY", "EndX", "EndY"):
                with self.subTest(edge=name, cell=cell):
                    self.assertIn("PAR(PNT(", c[cell].get("F", ""))
            self.assertIn("_XFTRIGGER(", c["BegTrigger"].get("F", ""))
            self.assertIn("_XFTRIGGER(", c["EndTrigger"].get("F", ""))

    def test_every_connect_targets_an_existing_connection_row(self):
        """pitfall 5: ToCell must be Connections.X(IX+1) and must exist."""
        name_by_id = {s.get("ID"): s.get("NameU") for s in self.shapes}
        conn_pts = {}
        for n in self.planned["nodes"]:
            sec = sections(self.node(n["id"])).get("Connection")
            self.assertIsNotNone(sec, "%s has no Connection section" % n["id"])
            conn_pts["node_" + n["id"]] = len([r for r in sec if L(r.tag) == "Row"])
        for cn in self.connects:
            tgt = name_by_id.get(cn.get("ToSheet"))
            m = re.match(r"Connections\.X(\d+)$", cn.get("ToCell") or "")
            with self.subTest(connect=cn.get("ToCell")):
                self.assertIsNotNone(m, "unexpected ToCell")
                self.assertIn(tgt, conn_pts)
                self.assertLessEqual(int(m.group(1)), conn_pts[tgt])
                self.assertEqual(int(cn.get("ToPart")), 99 + int(m.group(1)))

    # ---- route fidelity, offline ----------------------------------------

    def test_saved_route_matches_planned_route(self):
        """The planner's verified route must survive into the file, in the
        connector's rotated local frame (pitfall 7)."""
        by_name = self.edge_shapes()
        worst = 0.0
        for i, e in enumerate(self.planned["edges"], start=1):
            s = by_name["edge_%d" % i]
            c = cells(s)
            pinx, piny = val(c["PinX"]), val(c["PinY"])
            locx, locy = val(c["LocPinX"]), val(c["LocPinY"])
            ang = val(c["Angle"])
            rows = [r for r in sections(s)["Geometry"] if L(r.tag) == "Row"]
            pts = []
            for r in rows:
                cs = {x.get("N"): val(x) for x in r if L(x.tag) == "Cell"}
                if cs.get("X") is None:
                    continue          # endpoint sentinel row
                pts.append(local_to_page(cs["X"], cs["Y"], pinx, piny, locx, locy, ang))
            want = [(float(p[0]), self.ph - float(p[1])) for p in e["routePoints"]]
            with self.subTest(edge=i):
                self.assertEqual(len(pts), len(want))
                for (gx, gy), (ex, ey) in zip(pts, want):
                    worst = max(worst, abs(gx - ex), abs(gy - ey))
                    self.assertAlmostEqual(gx, ex, places=4)
                    self.assertAlmostEqual(gy, ey, places=4)
        self.assertLess(worst, 1e-4, "route drifted %.6f in" % worst)

    def test_page_size_matches_plan(self):
        pages = ET.fromstring(self.pack["visio/pages/pages.xml"])
        pw = re.search(r"N=['\"]PageWidth['\"][^/]*?V=['\"]([0-9.]+)",
                       self.pack["visio/pages/pages.xml"].decode("utf-8"))
        ph = re.search(r"N=['\"]PageHeight['\"][^/]*?V=['\"]([0-9.]+)",
                       self.pack["visio/pages/pages.xml"].decode("utf-8"))
        self.assertAlmostEqual(float(pw.group(1)), float(self.planned["page"]["width"]), places=4)
        self.assertAlmostEqual(float(ph.group(1)), float(self.planned["page"]["height"]), places=4)


if __name__ == "__main__":
    print("spec   :", SPEC)
    print("writer :", WRITER)
    print("skill  :", find_skill())
    print("-" * 60)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
