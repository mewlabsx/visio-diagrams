import copy,json,pathlib,unittest
from plan_routes import plan

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((pathlib.Path(__file__).parents[1]/'assets/grouped-example.json').read_text(encoding='utf-8'))
    def test_unequal_edges_uniform(self):
        result=plan(self.spec)
        self.assertEqual(result['_routingValidation']['plannedEdges'],4)
        edges=result['edges']
        for end in ('from','to'):
            values=[e[end+'Fraction'] for e in edges]
            delta=values[1]-values[0]
            for a,b in zip(values,values[1:]):self.assertAlmostEqual(b-a,delta)
        lanes=[e['routePoints'][1][0] for e in edges]
        for a,b in zip(lanes,lanes[1:]):self.assertAlmostEqual(b-a,.35)
    def test_horizontal(self):
        for n in self.spec['nodes']:
            n['x'],n['y']=n['y'],n['x'];n['w'],n['h']=n['h'],n['w']
        self.spec['page']['width'],self.spec['page']['height']=7,10
        self.spec['routingGroups']['parallel']['axis']='horizontal'
        for e in self.spec['edges']:e['fromPort']='bottom';e['toPort']='top'
        self.assertEqual(plan(self.spec)['_routingValidation']['plannedEdges'],4)
    def test_insufficient_space(self):
        self.spec['nodes'][0]['h']=.3
        with self.assertRaisesRegex(ValueError,'Insufficient'):plan(self.spec)
    def test_restricted_vertex(self):
        self.spec['nodes'][0]['kind']='diamond'
        with self.assertRaisesRegex(ValueError,'restricted'):plan(self.spec)
    def test_obstacle(self):
        self.spec['nodes'].append(dict(id='obstacle',x=4,y=1,w=2,h=5))
        with self.assertRaisesRegex(ValueError,'crosses'):plan(self.spec)
    def test_overlap_rejected(self):
        self.spec['edges'][1]['routeGroup']='other'
        self.spec['routingGroups']['other']=dict(axis='vertical',center=5,spacing=.35)
        self.spec['routingGroups']['parallel']['spacing']=.4
        with self.assertRaisesRegex(ValueError,'overlap'):plan(self.spec)
    def test_layout_straight_and_minimal_shift(self):
        self.spec['routingGroups']['parallel']['optimizeLayout']={'moveNode':'b','maxShift':1.4}
        result=plan(self.spec)
        self.assertEqual(result['_layoutOptimization']['status'],'straight')
        self.assertAlmostEqual(result['_layoutOptimization']['delta'],-.79)
        for e in result['edges']:
            self.assertEqual(len(e['routePoints']),2)
            self.assertAlmostEqual(e['routePoints'][0][1],e['routePoints'][1][1])
    def test_layout_bound_fallback(self):
        self.spec['routingGroups']['parallel']['optimizeLayout']={'moveNode':'b','maxShift':.2}
        result=plan(self.spec)
        self.assertEqual(result['_layoutOptimization']['status'],'fallback')
        self.assertEqual(result['nodes'][1]['y'],3)
    def test_layout_other_edges_rejected(self):
        self.spec['routingGroups']['parallel']['optimizeLayout']={'moveNode':'b','maxShift':1.4}
        self.spec['edges'].append(dict(self.spec['edges'][0],routeGroup=None))
        with self.assertRaisesRegex(ValueError,'other edges'):plan(self.spec)

if __name__=='__main__':unittest.main()
