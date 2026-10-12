import copy
import json
import tempfile
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from render_native import render
from vsdx_writer import STENCIL

ROOT = Path(__file__).resolve().parent.parent
NS = {'v': 'http://schemas.microsoft.com/office/visio/2012/main'}


@unittest.skipUnless(Path(STENCIL).is_file(), 'Requires local basic flowchart stencil resource, not Visio COM')
class NativeEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'scripts')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)/'output.vsdx'

    def fixture(self, name):
        return json.loads((ROOT/'assets'/f'{name}.json').read_text(encoding='utf-8-sig'))

    def package(self):
        with zipfile.ZipFile(self.out) as package:
            return ET.fromstring(package.read('visio/pages/page1.xml'))

    def test_supported_planner_paths(self):
        for name in ('k8s-activity-example','folded-flow-example','local-adjust-example',
                     'grouped-example','layout-optimized-example','manual-route-example'):
            with self.subTest(name=name):
                report = render(self.fixture(name), self.out.with_name(name+'.vsdx'))
                self.assertEqual(report['structure']['status'], 'PASS')
                self.assertEqual(report['unplannedEdges'], 0)
                self.assertEqual(report['visioAcceptance'], 'NOT_RUN')
                self.assertEqual(report['visualReview'], 'NOT_RUN')
                self.assertIsNone(report['png'])

    def test_fractional_glue_matches_route_coordinates(self):
        render(self.fixture('grouped-example'), self.out)
        plan = json.loads(self.out.with_suffix('.planned.json').read_text(encoding='utf-8'))
        page = self.package()
        shapes = {s.get('NameU'): s for s in page.findall('v:Shapes/v:Shape', NS)}
        seen_fraction = False
        for i, edge in enumerate(plan['edges'], 1):
            for end, cell in (('from', 'BeginX'), ('to', 'EndX')):
                conn = next(c for c in page.findall('v:Connects/v:Connect', NS)
                            if c.get('FromSheet') == shapes[f'edge_{i}'].get('ID') and c.get('FromCell') == cell)
                row_index = int(conn.get('ToCell').split('X')[1])-1
                node = shapes['node_'+edge[end]]
                row = next(r for r in node.findall("v:Section[@N='Connection']/v:Row", NS)
                           if int(r.get('IX')) == row_index)
                cells = {c.get('N'): float(c.get('V')) for c in row.findall('v:Cell', NS) if c.get('N') in ('X','Y')}
                data = next(n for n in plan['nodes'] if n['id'] == edge[end])
                expected = edge['routePoints'][0 if end == 'from' else -1]
                self.assertAlmostEqual(data['x']+cells['X'], expected[0], places=7)
                self.assertAlmostEqual(data['y']+data['h']-cells['Y'], expected[1], places=7)
                if edge.get(end+'Fraction', .5) != .5:
                    seen_fraction = True
                    self.assertGreaterEqual(row_index, 4)
        self.assertTrue(seen_fraction)

    def test_monochrome_preserves_font_sizes(self):
        spec = self.fixture('grouped-example')
        original = copy.deepcopy(spec)
        render(spec, self.out, 'off')
        self.assertEqual(spec, original)
        page = self.package()
        for node in spec['nodes']:
            shape = next(s for s in page.findall('v:Shapes/v:Shape', NS) if s.get('NameU') == 'node_'+node['id'])
            cells = {c.get('N'): c.get('V') for c in shape.findall('v:Cell', NS)}
            self.assertEqual(cells['FillForegnd'], '#FFFFFF')
            size = shape.find("v:Section[@N='Character']/v:Row/v:Cell[@N='Size']", NS)
            self.assertAlmostEqual(float(size.get('V'))*72, node.get('fontSize', 11), places=6)

    def test_existing_target_not_overwritten(self):
        self.out.write_bytes(b'keep this file')
        with self.assertRaises(FileExistsError):
            render(self.fixture('grouped-example'), self.out)
        self.assertEqual(self.out.read_bytes(), b'keep this file')
        self.assertFalse(self.out.with_suffix('.planned.json').exists())

    def test_bad_input_leaves_no_deliverable(self):
        for failure in ('duplicate', 'unsupported', 'nonfinite', 'missing-stencil', 'bad-route'):
            with self.subTest(failure=failure):
                spec = self.fixture('manual-route-example')
                stencil = None
                if failure == 'duplicate': spec['nodes'].append(copy.deepcopy(spec['nodes'][0]))
                if failure == 'unsupported': spec['nodes'][0]['master'] = 'Database'
                if failure == 'nonfinite': spec['nodes'][0]['w'] = float('nan')
                if failure == 'missing-stencil': stencil = str(self.out.parent/'missing.vssx')
                if failure == 'bad-route':
                    spec.pop('localLayout', None)
                    spec['edges'][0]['routePoints'] = [[.1,.1],[.2,.2]]
                with self.assertRaises((ValueError, OSError)):
                    render(spec, self.out, stencil=stencil)
                self.assertEqual(list(self.out.parent.iterdir()), [])

    def test_source_document_metadata_and_thumbnail_not_inherited(self):
        render(self.fixture('grouped-example'), self.out)
        with zipfile.ZipFile(self.out) as package:
            self.assertFalse(any(name.startswith('docProps/') for name in package.namelist()))
            self.assertNotIn('thumbnail', package.read('_rels/.rels').decode())

    def test_inline_labels_use_connector_frame_not_master_cache(self):
        render(self.fixture('layout-optimized-example'), self.out)
        for shape in self.package().findall('v:Shapes/v:Shape', NS):
            if not shape.get('NameU', '').startswith('edge_') or shape.find('v:Text', NS) is None:
                continue
            wanted = ('TxtPinX','TxtPinY','LocPinX','LocPinY','TxtHeight','TxtWidth','TxtLocPinX')
            cells = {c.get('N'): float(c.get('V')) for c in shape.findall('v:Cell', NS) if c.get('N') in wanted}
            self.assertAlmostEqual(cells['TxtPinX'], cells['LocPinX'], places=6)
            self.assertAlmostEqual(cells['TxtPinY'], cells['LocPinY']+.14, places=6)
            self.assertLess(cells['TxtHeight'], 1)
            self.assertAlmostEqual(cells['TxtLocPinX'], cells['TxtWidth']/2, places=6)

    def test_writer_runs_from_relocated_skill_without_source_template(self):
        relocated = self.out.parent/'relocated'
        (relocated/'scripts').mkdir(parents=True)
        for name in ('render_native.py','vsdx_writer.py','local_layout.py','plan_routes.py','containers.py'):
            shutil.copyfile(ROOT/'scripts'/name, relocated/'scripts'/name)
        shutil.copytree(ROOT/'assets'/'vsdx-base', relocated/'assets'/'vsdx-base')
        result = subprocess.run([sys.executable, '-X', 'utf8', str(relocated/'scripts'/'render_native.py'),
                                 str(ROOT/'assets'/'grouped-example.json'), str(self.out)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.out.is_file())

    def test_nested_containers_write_reciprocal_native_relationships(self):
        spec=self.fixture('nested-architecture-example')
        render(spec,self.out)
        page=self.package()
        shapes={s.get('NameU')[5:]:s for s in page.findall('v:Shapes/v:Shape',NS) if s.get('NameU','').startswith('node_')}
        for node in spec['nodes']:
            shape=shapes[node['id']]
            relation=shape.find("v:Cell[@N='Relationships']",NS)
            if node.get('parent'):
                parent_id=shapes[node['parent']].get('ID')
                self.assertIn(f'DEPENDSON(4,Sheet.{parent_id}!SheetRef())',relation.get('F'))
                parent_rel=shapes[node['parent']].find("v:Cell[@N='Relationships']",NS).get('F')
                self.assertIn(f'Sheet.{shape.get("ID")}!SheetRef()',parent_rel)
            if node.get('kind')=='container':
                marker=shape.find("v:Section[@N='User']/v:Row[@N='msvStructureType']/v:Cell[@N='Value']",NS)
                self.assertEqual(marker.get('V'),'Container')
                self.assertIsNone(shape.find('v:Shapes',NS))


if __name__ == '__main__':
    unittest.main()
