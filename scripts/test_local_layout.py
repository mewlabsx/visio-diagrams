import copy,json,pathlib,unittest
from local_layout import solve,propagate,fold,topology
ROOT=pathlib.Path(__file__).parents[1]/'assets'
class LocalLayoutTests(unittest.TestCase):
 def setUp(self):self.s=json.loads((ROOT/'local-adjust-example.json').read_text(encoding='utf-8'))
 def test_improve_and_same_direction(self):
  result=solve(self.s)
  self.assertEqual(topology(result),topology(self.s))
  self.assertEqual(result['_localLayout']['totalBends'],0)
  self.assertGreater(result['_localLayout']['initialBends'],0)
  ns={n['id']:n for n in result['nodes']}
  self.assertEqual(ns['b']['y'],2);self.assertEqual(ns['c']['y'],2)
 def test_cumulative_limit(self):
  self.s['localLayout']['adjust']['maxShift']=.2
  result=solve(self.s)
  self.assertEqual(result['_localLayout']['moves'],[])
 def test_fixed_successor_blocks(self):
  self.s['nodes'][2]['fixed']=True
  self.assertIsNone(propagate(self.s,'b','y',-.5,self.s['localLayout']['adjust']))
 def test_minimum_gap_blocks(self):
  self.s['nodes'].append({'id':'obstacle','text':'固定障碍','x':4,'y':1.3,'w':2,'h':.6,'fixed':True})
  self.assertIsNone(propagate(self.s,'b','y',-.5,self.s['localLayout']['adjust']))
 def test_move_receipt_never_reverses(self):
  result=solve(self.s);seen={}
  for move in result['_localLayout']['moves']:
   for id in move['affected']:
    key=(id,move['axis']);sign=1 if move['delta']>0 else -1
    self.assertEqual(seen.get(key,sign),sign);seen[key]=sign
 def test_page_boundary_blocks(self):
  self.s['page']['width']=9.2
  self.assertIsNone(propagate(self.s,'b','x',.5,self.s['localLayout']['adjust']))
 def test_wrong_dependency_order(self):
  cfg=dict(self.s['localLayout']['adjust'],order=['c','b'])
  with self.assertRaisesRegex(ValueError,'reachability'):propagate(self.s,'c','y',-.5,cfg)
 def test_budget_fails_closed(self):
  self.s['localLayout']['routing']['maxStates']=1
  with self.assertRaisesRegex(ValueError,'budget'):solve(self.s)
 def test_fold_safe_split_and_topology(self):
  s=json.loads((ROOT/'folded-flow-example.json').read_text(encoding='utf-8'))
  result=solve(s)
  self.assertEqual(topology(result),topology(s))
  cols=result['_localLayout']['fold']['columns']
  self.assertEqual(len(cols),2);self.assertEqual(len(cols[0]),6)
  self.assertLess(result['page']['height'],s['page']['height'])
  self.assertEqual(result['_routingValidation']['overlaps'],0)
 def test_branch_anchor_required(self):
  s=json.loads((ROOT/'folded-flow-example.json').read_text(encoding='utf-8'))
  s['localLayout']['fold']['branchAnchors'].pop('fix')
  with self.assertRaisesRegex(ValueError,'branchAnchor'):solve(s)
 def test_fixed_fold_rejected(self):
  s=json.loads((ROOT/'folded-flow-example.json').read_text(encoding='utf-8'));s['nodes'][0]['fixed']=True
  with self.assertRaisesRegex(ValueError,'fixed'):solve(s)
 def test_preserve_valid_original_on_adjust_failure(self):
  self.s['localLayout']['failurePolicy']='preserve'
  self.s['localLayout']['adjust']['step']=-1
  r=solve(self.s)
  self.assertEqual(r['_localLayout']['status'],'DEGRADED')
  self.assertEqual(r['nodes'],self.s['nodes'])
 def test_preserve_cannot_hide_unroutable(self):
  self.s['localLayout']['failurePolicy']='preserve'
  self.s['localLayout']['routing']['maxStates']=1
  with self.assertRaisesRegex(ValueError,'budget'):solve(self.s)
 def test_fixed_route_preserved(self):
  self.s['nodes'][1]['fixed']=True
  self.s['localLayout'].pop('adjust')
  self.s['edges'][0]['fixedRoute']=[[2.7,2.5],[3.1,2.5],[3.1,3],[4,3]]
  r=solve(self.s)
  self.assertEqual(r['edges'][0]['routePoints'],self.s['edges'][0]['fixedRoute'])
 def test_fixed_route_requires_locked_endpoints(self):
  self.s['edges'][0]['fixedRoute']=[[2.7,2.5],[4,3]]
  with self.assertRaisesRegex(ValueError,'fixed endpoint'):solve(self.s)
 def test_fixed_route_rejects_diagonal(self):
  self.s['nodes'][1]['fixed']=True
  self.s['edges'][0]['fixedRoute']=[[2.7,2.5],[4,3]]
  with self.assertRaisesRegex(ValueError,'orthogonal'):solve(self.s)
if __name__=='__main__':unittest.main()
