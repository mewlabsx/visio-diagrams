import copy
import json
import unittest
from pathlib import Path

from containers import hierarchy, prepare
from local_layout import solve, placement_ok, crosses_node
from plan_routes import segments, overlap, point

ROOT=Path(__file__).resolve().parent.parent


class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((ROOT/'assets/nested-architecture-example.json').read_text(encoding='utf-8'))

    def test_geometry_and_order_are_derived_bottom_up(self):
        result=prepare(self.spec);ns,parents,children,ancestors=hierarchy(result)
        self.assertEqual(ancestors['a'],['services','worker','root'])
        self.assertEqual([n['id'] for n in result['nodes'][:4]],['root','control','worker','services'])
        for id,parent in parents.items():
            n,c=ns[id],ns[parent]
            self.assertGreaterEqual(n['y'],c['y']+c['headerHeight']+c['padding']-1e-8)
            self.assertGreaterEqual(n['x'],c['x']+c['padding']-1e-8)
            self.assertLessEqual(n['x']+n['w'],c['x']+c['w']-c['padding']+1e-8)
        self.assertNotIn('x',self.spec['nodes'][0])
        self.assertEqual(prepare(result),result)

    def test_cycle_rejected(self):
        self.spec['nodes'][0]['parent']='services'
        with self.assertRaisesRegex(ValueError,'cycle'):prepare(self.spec)

    def test_unknown_or_noncontainer_parent_rejected(self):
        for parent in ('unknown','client'):
            with self.subTest(parent=parent):
                spec=copy.deepcopy(self.spec);spec['nodes'][-1]['parent']=parent
                with self.assertRaisesRegex(ValueError,'Parent'):prepare(spec)

    def test_empty_container_rejected(self):
        self.spec['nodes'].append({'id':'empty','kind':'container'})
        with self.assertRaisesRegex(ValueError,'Empty'):prepare(self.spec)

    def test_unrelated_geometry_cannot_hide_in_container(self):
        s=prepare(self.spec)
        client=next(n for n in s['nodes'] if n['id']=='client')
        client.update(x=6.4,y=3.0)
        self.assertFalse(placement_ok(s,0))

    def test_ancestor_overlap_is_legal(self):
        self.assertTrue(placement_ok(self.spec,0))

    def test_sibling_overlap_is_rejected(self):
        s=copy.deepcopy(self.spec)
        a=next(n for n in s['nodes'] if n['id']=='a')
        b=next(n for n in s['nodes'] if n['id']=='b')
        b.update(x=a['x'],y=a['y'])
        self.assertFalse(placement_ok(s,0))

    def test_container_recomputed_after_leaf_translation(self):
        original=prepare(self.spec)
        s=copy.deepcopy(self.spec)
        for n in s['nodes']:
            if n.get('parent')=='services':n['x']+=.4
        result=prepare(s)
        a=next(n for n in original['nodes'] if n['id']=='services')
        b=next(n for n in result['nodes'] if n['id']=='services')
        self.assertAlmostEqual(b['x']-a['x'],.4)

    def test_shared_port_capacity_failure_is_explicit(self):
        api=next(n for n in self.spec['nodes'] if n['id']=='api');api['h']=.2
        with self.assertRaisesRegex(ValueError,'endpoint space'):solve(self.spec)

    def test_shared_ports_are_real_route_endpoints(self):
        result=solve(self.spec)
        ns={n['id']:n for n in result['nodes']}
        fan=[e for e in result['edges'] if e['from']=='api']
        self.assertEqual(len({e['fromFraction'] for e in fan}),4)
        for e in result['edges']:
            self.assertEqual(e['routePoints'][0],point(ns[e['from']],e['fromPort'],e.get('fromFraction',.5)))
            self.assertEqual(e['routePoints'][-1],point(ns[e['to']],e['toPort'],e.get('toFraction',.5)))
        self.assertEqual([(e['from'],e['to']) for e in result['edges']],[(e['from'],e['to']) for e in self.spec['edges']])

    def test_routes_avoid_text_headers_and_nodes_and_each_other(self):
        from containers import obstacles
        result=solve(self.spec);obs=obstacles(result)
        paths=[list(segments(e['routePoints'])) for e in result['edges']]
        for path in paths:
            for a,b in path:
                self.assertFalse(any(crosses_node(a,b,n) for n in obs))
        for i,path in enumerate(paths):
            for other in paths[i+1:]:
                self.assertFalse(any(overlap(a,b,c,d) for a,b in path for c,d in other))

    def test_attempt_and_crossing_budgets_checked(self):
        for key,value in (('routeAttempts',5),('maxCrossings',-1)):
            with self.subTest(key=key):
                self.spec['localLayout']['routing'][key]=value
                with self.assertRaises(ValueError):solve(self.spec)
                self.spec['localLayout']['routing'].pop(key)

    def test_fold_recomputes_ancestor_bounds(self):
        from local_layout import fold
        s=json.loads((ROOT/'assets/folded-flow-example.json').read_text(encoding='utf-8'))
        for n in s['nodes']:
            n['parent']='frame';n['y']+=1
        s['nodes'].insert(0,{'id':'frame','kind':'container','text':'流程'})
        s['localLayout']['fold']['top']=1.5
        result,receipt=fold(s,s['localLayout']['fold'])
        self.assertEqual(receipt['status'],'folded')
        self.assertTrue(placement_ok(result,0))
        self.assertEqual(prepare(result),result)

    def test_container_adjustment_not_silently_discarded(self):
        from local_layout import propagate
        s=prepare(self.spec)
        with self.assertRaisesRegex(ValueError,'leaf nodes'):
            propagate(s,'root','x',.2,{'order':['root'],'maxShift':1})

    def test_crossing_limit_failure_cannot_be_reported_as_success(self):
        from local_layout import route_all
        ns=[{'id':id,'text':id,'x':x,'y':y,'w':1,'h':1,'fixed':True} for id,x,y in [('a',1,3),('b',7,3),('c',4,1),('d',4,6)]]
        s={'page':{'width':10,'height':9},'nodes':ns,'edges':[
            {'from':'a','to':'b','fromPort':'right','toPort':'left','fixedRoute':[[2,3.5],[7,3.5]]},
            {'from':'c','to':'d','fromPort':'bottom','toPort':'top','fixedRoute':[[4.5,2],[4.5,6]]}]}
        with self.assertRaisesRegex(ValueError,'Crossing limit'):route_all(s,{'maxCrossings':0})


if __name__=='__main__':unittest.main()
