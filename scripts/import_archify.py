"""Convert a workflow v2 layout receipt to native Visio geometry; fail closed."""
import argparse,json,math
from pathlib import Path
from plan_routes import segments,overlap

def convert(source,layout,scale=72):
    if not math.isfinite(scale) or scale<=0:raise ValueError('Invalid scale')
    if source.get('schema_version')!=2 or layout.get('contract')!='readable-v2':raise ValueError('Requires workflow v2 layout')
    if any(source.get(k) for k in ('groups','phases','cards')):raise ValueError('Groups, phases and cards are not supported by this adapter')
    if any(n.get('sublabel') or n.get('tag') or n.get('brand') for n in source['nodes']):raise ValueError('Rich node content is not supported')
    if layout.get('diagnostics'):raise ValueError('Unresolved layout diagnostics')
    sn={n['id']:n for n in source['nodes']}; ln={n['id']:n for n in layout['nodes']}
    if set(sn)!=set(ln):raise ValueError('Layout node IDs differ from source')
    se={e['id']:e for e in source['edges']}; le={e['id']:e for e in layout['edges']}
    if set(se)!=set(le):raise ValueError('Layout edge IDs differ from source')
    labels={l['edge']:l for l in layout.get('labels',[])}
    conflicts=[]
    for i,e in enumerate(layout['edges']):
        for f in layout['edges'][i+1:]:
            if any(overlap(a,b,c,d) for a,b in segments(e['points']) for c,d in segments(f['points'])):conflicts.append([e['id'],f['id']])
        for a,b in segments(e['points']):
            for id,n in ln.items():
                if id in (e['from'],e['to']):continue
                x,y,w,h=n['x'],n['y'],n['width'],n['height']
                if (a[0]==b[0] and x<a[0]<x+w and min(max(a[1],b[1]),y+h)>max(min(a[1],b[1]),y)) or (a[1]==b[1] and y<a[1]<y+h and min(max(a[0],b[0]),x+w)>max(min(a[0],b[0]),x)):
                    raise ValueError('Route crosses node '+id)
    if conflicts:raise ValueError('Shared line segments: '+json.dumps(conflicts))
    spec={'page':{'width':layout['viewBox'][0]/scale,'height':layout['viewBox'][1]/scale,'title':source['meta']['title'],'diagramType':'flowchart'},'nodes':[],'edges':[]}
    for lane in source.get('lanes',[]):
        members=[n for n in ln.values() if n['lane']==lane['id']]
        if members:
            left=min(n['x'] for n in members);top=min(n['y'] for n in members)-25
            spec['nodes'].append({'id':'lane_'+lane['id'],'kind':'text','text':lane['label'],'x':left/scale,'y':top/scale,'w':2,'h':.25,'fontSize':10,'bold':True})
    for id,n in ln.items():
        s=sn[id]
        spec['nodes'].append({'id':id,'kind':'box','text':s['label'],'x':n['x']/scale,'y':n['y']/scale,'w':n['width']/scale,'h':n['height']/scale,'fontSize':10})
    def port(n,p):
        x,y,w,h=n['x'],n['y'],n['width'],n['height'];px,py=p
        for side,dist,f in [('left',abs(px-x),(py-y)/h),('right',abs(px-x-w),(py-y)/h),('top',abs(py-y),(px-x)/w),('bottom',abs(py-y-h),(px-x)/w)]:
            if dist<.001 and -.00001<=f<=1.00001:return side,f
        raise ValueError('Endpoint is not on node boundary')
    for id,e in le.items():
        if (e['from'],e['to'])!=(se[id]['from'],se[id]['to']):raise ValueError('Topology mismatch')
        edge={'from':e['from'],'to':e['to'],'routePoints':[[x/scale,y/scale] for x,y in e['points']],'text':se[id].get('label','')}
        for end,index in [('from',0),('to',-1)]:edge[end+'Port'],edge[end+'Fraction']=port(ln[e[end]],e['points'][index])
        if edge['text']:
            if id not in labels:raise ValueError('Missing semantic label')
            l=labels[id];edge['label']={'x':(l['x']-l['width']/2)/scale,'y':(l['y']-l['height']/2)/scale,'w':l['width']/scale,'h':l['height']/scale}
        spec['edges'].append(edge)
    spec['_routingValidation']={'plannedEdges':len(le),'overlaps':0,'scope':'All imported edge segments; unrelated nodes checked; labels require visual QA'}
    spec['_archifyImport']={'contract':layout['contract'],'scalePxPerInch':scale,'nodeCount':len(ln),'edgeCount':len(le),'scope':'Rectangular workflow nodes; no UML or native lanes'}
    return spec

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('layout');p.add_argument('output');a=p.parse_args()
    source=json.loads(Path(a.source).read_text(encoding='utf-8-sig'));layout=json.loads(Path(a.layout).read_text(encoding='utf-8-sig'))
    result=convert(source,layout)
    out=Path(a.output)
    if out.exists():raise ValueError('Refusing to overwrite output')
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
