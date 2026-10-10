import copy,unittest
from import_archify import convert
class AdapterTests(unittest.TestCase):
 def setUp(self):
  self.source={'schema_version':2,'meta':{'title':'test'},'nodes':[{'id':'a','label':'A'},{'id':'b','label':'B'}],'edges':[{'id':'e','from':'a','to':'b'}]}
  self.layout={'contract':'readable-v2','viewBox':[600,300],'diagnostics':[],'nodes':[{'id':'a','lane':'main','x':72,'y':72,'width':144,'height':72},{'id':'b','lane':'main','x':360,'y':72,'width':144,'height':72}],'edges':[{'id':'e','from':'a','to':'b','points':[[216,108],[360,108]]}],'labels':[]}
 def test_geometry_and_ports(self):
  s=convert(self.source,self.layout);e=s['edges'][0]
  self.assertEqual(e['routePoints'],[[3,1.5],[5,1.5]])
  self.assertEqual(e['fromPort'],'right');self.assertEqual(e['toPort'],'left')
  self.assertEqual(e['fromFraction'],.5)
 def test_shared_segment_rejected(self):
  self.source['edges'].append(dict(self.source['edges'][0],id='e2'))
  self.layout['edges'].append(dict(self.layout['edges'][0],id='e2'))
  with self.assertRaisesRegex(ValueError,'Shared'):convert(self.source,self.layout)
 def test_missing_label_rejected(self):
  self.source['edges'][0]['label']='meaning'
  with self.assertRaisesRegex(ValueError,'Missing semantic'):convert(self.source,self.layout)
 def test_diagnostics_rejected(self):
  self.layout['diagnostics']=[{'severity':'error'}]
  with self.assertRaisesRegex(ValueError,'diagnostics'):convert(self.source,self.layout)
 def test_node_crossing_rejected(self):
  self.source['nodes'].append({'id':'c','label':'C'})
  self.layout['nodes'].append({'id':'c','lane':'main','x':260,'y':90,'width':40,'height':40})
  with self.assertRaisesRegex(ValueError,'crosses'):convert(self.source,self.layout)
if __name__=='__main__':unittest.main()
