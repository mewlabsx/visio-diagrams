"""Plan explicitly grouped orthogonal routes. Standard library only."""
import argparse, copy, json, math
from collections import defaultdict

PORTS = {'top','bottom','left','right'}
def point(n, port, fraction=.5):
    x,y,w,h = (float(n[k]) for k in ('x','y','w','h'))
    return {'top':[x+w*fraction,y], 'bottom':[x+w*fraction,y+h],
            'left':[x,y+h*fraction], 'right':[x+w,y+h*fraction]}[port]

def simplify(points):
    out=[]
    for p in points:
        if out and p==out[-1]: continue
        out.append(p)
        while len(out)>2 and ((out[-3][0]==out[-2][0]==out[-1][0]) or (out[-3][1]==out[-2][1]==out[-1][1])):
            out.pop(-2)
    return out

def segments(points):
    for a,b in zip(points,points[1:]):
        if a[0]!=b[0] and a[1]!=b[1]: raise ValueError('Non-orthogonal route')
        yield a,b

def overlap(a,b,c,d):
    for axis in (0,1):
        other=1-axis
        if abs(a[axis]-b[axis])<1e-8 and abs(c[axis]-d[axis])<1e-8 and abs(a[axis]-c[axis])<1e-8:
            if min(max(a[other],b[other]),max(c[other],d[other]))-max(min(a[other],b[other]),min(c[other],d[other]))>1e-8: return True
    return False

def plan(spec):
    spec=copy.deepcopy(spec); nodes={n['id']:n for n in spec['nodes']}; groups=defaultdict(list)
    configs=spec.get('routingGroups',{})
    optimized=[(name,cfg) for name,cfg in configs.items() if cfg.get('optimizeLayout')]
    if optimized:
        if len(optimized)!=1: raise ValueError('Only one layout-optimized group is supported')
        name,cfg=optimized[0]; es=[e for e in spec['edges'] if e.get('routeGroup')==name]
        signatures={(e['from'],e['to'],e.get('fromPort'),e.get('toPort')) for e in es}
        if len(signatures)!=1: raise ValueError('Layout optimization requires one shared node pair')
        aid,bid,ap,bp=next(iter(signatures)); opt=cfg['optimizeLayout']; moving=opt['moveNode']
        if moving not in (aid,bid): raise ValueError('moveNode must be an endpoint')
        if any(e.get('routeGroup')!=name and (e['from'] in (aid,bid) or e['to'] in (aid,bid)) for e in spec['edges']):
            raise ValueError('Optimized endpoints must not participate in other edges')
        if (ap,bp) not in (('right','left'),('left','right'),('bottom','top'),('top','bottom')): raise ValueError('Optimization requires facing ports')
        if any(nodes[id].get('kind','box')!='box' for id in (aid,bid)):raise ValueError('Optimization supports rectangles only')
        coord,size=('y','h') if ap in ('left','right') else ('x','w')
        limit=float(opt['maxShift']); margin=float(spec.get('routing',{}).get('portMargin',.12))
        spacing=float(cfg.get('spacing',.2)); required=(len(es)-1)*spacing
        if limit<0 or not math.isfinite(limit):raise ValueError('Invalid maxShift')
        fixed=nodes[bid if moving==aid else aid]; mobile=nodes[moving]
        flo=fixed[coord]+margin; fhi=fixed[coord]+fixed[size]-margin
        mlo=mobile[coord]+margin; mhi=mobile[coord]+mobile[size]-margin
        candidates=sorted(set([0,flo+required-mhi,fhi-required-mlo,(flo+fhi-mlo-mhi)/2,-limit,limit]),key=lambda d:(abs(d),d))
        failures=[]
        for delta in candidates:
            if abs(delta)>limit+1e-8:continue
            trial=copy.deepcopy(spec); tn={n['id']:n for n in trial['nodes']}; n=tn[moving]; n[coord]+=delta
            if n['x']<0 or n['y']<0 or n['x']+n['w']>spec['page']['width'] or n['y']+n['h']>spec['page']['height']:continue
            if any(id!=moving and o.get('kind') not in ('container','text') and min(n['x']+n['w'],o['x']+o['w'])>max(n['x'],o['x']) and min(n['y']+n['h'],o['y']+o['h'])>max(n['y'],o['y']) for id,o in tn.items()):continue
            low=max(flo,mlo+delta); high=min(fhi,mhi+delta)
            if high-low+1e-8<required:continue
            tc=trial['routingGroups'][name];tc.pop('optimizeLayout');tc['_straightRange']=[low,high]
            try:
                result=plan(trial)
                result['_layoutOptimization']={'status':'straight','movedNode':moving,'axis':coord,'delta':delta,'totalBends':0,'scope':'One isolated rectangular node pair; bounded translation'}
                return result
            except ValueError as ex:failures.append(str(ex))
        configs[name].pop('optimizeLayout')
        result=plan(spec)
        result['_layoutOptimization']={'status':'fallback','movedNode':moving,'delta':0,'reason':'No feasible straight candidate within allowed shift','candidateFailures':failures}
        return result
    endpoints=defaultdict(list)
    for i,e in enumerate(spec.get('edges',[])):
        if not e.get('routeGroup'): continue
        if e['routeGroup'] not in configs: raise ValueError('Undefined routeGroup')
        groups[e['routeGroup']].append((i,e))
        for end in ('from','to'):
            port=e.get(end+'Port')
            if port not in PORTS: raise ValueError('Grouped edges require explicit ports')
            if e[end] not in nodes: raise ValueError('Unknown endpoint')
            endpoints[(e[end],port)].append((i,e,end))
    for (id,port),items in endpoints.items():
        n=nodes[id]; length=float(n['h'] if port in ('left','right') else n['w'])
        margin=float(spec.get('routing',{}).get('portMargin',.12))
        minimum=float(spec.get('routing',{}).get('minSpacing',.12))
        items.sort(key=lambda item: (point(nodes[item[1]['to' if item[2]=='from' else 'from']],item[1]['toPort' if item[2]=='from' else 'fromPort'])[1 if port in ('left','right') else 0],item[0]))
        if len(items)>1 and n.get('kind','box') not in ('box','container'):
            raise ValueError('Multiple grouped edges on a restricted vertex: split into separate corridors')
        if len(items)>1 and (length-2*margin)/(len(items)-1)<minimum:
            raise ValueError('Insufficient endpoint space; enlarge node or split group')
        for rank,(_,e,end) in enumerate(items):
            fraction=.5 if len(items)==1 else (margin+rank*(length-2*margin)/(len(items)-1))/length
            e[end+'Fraction']=fraction
    for name,items in groups.items():
        cfg=configs[name]; axis=cfg['axis']; center=float(cfg['center']); spacing=float(cfg.get('spacing',.2))
        if axis not in ('vertical','horizontal') or spacing<float(spec.get('routing',{}).get('minSpacing',.12)):
            raise ValueError('Invalid corridor axis or spacing')
        items.sort(key=lambda item: (point(nodes[item[1]['from']],item[1]['fromPort'],item[1]['fromFraction'])[1 if axis=='vertical' else 0],item[0]))
        for rank,(_,e) in enumerate(items):
            if cfg.get('_straightRange'):
                low,high=cfg['_straightRange'];value=(low+high)/2 if len(items)==1 else low+rank*(high-low)/(len(items)-1)
                for end in ('from','to'):
                    node=nodes[e[end]];port=e[end+'Port'];coordinate,dimension=('y','h') if port in ('left','right') else ('x','w')
                    e[end+'Fraction']=(value-node[coordinate])/node[dimension]
            a=point(nodes[e['from']],e['fromPort'],e['fromFraction']); b=point(nodes[e['to']],e['toPort'],e['toFraction'])
            lane=center+(rank-(len(items)-1)/2)*spacing
            required=('left','right') if axis=='vertical' else ('top','bottom')
            if e['fromPort'] not in required or e['toPort'] not in required: raise ValueError('Port orientation incompatible with corridor')
            e['routePoints']=[a,b] if cfg.get('_straightRange') else simplify([a,[lane,a[1]],[lane,b[1]],b] if axis=='vertical' else [a,[a[0],lane],[b[0],lane],b])
            for x,y in e['routePoints']:
                if not math.isfinite(x+y) or not 0<=x<=spec['page']['width'] or not 0<=y<=spec['page']['height']: raise ValueError('Route outside page')
            for a,b in segments(e['routePoints']):
                for id,n in nodes.items():
                    if id in (e['from'],e['to']) or n.get('kind') in ('container','text'): continue
                    x,y,w,h=(float(n[k]) for k in ('x','y','w','h'))
                    if (a[0]==b[0] and x<a[0]<x+w and min(max(a[1],b[1]),y+h)>max(min(a[1],b[1]),y)) or (a[1]==b[1] and y<a[1]<y+h and min(max(a[0],b[0]),x+w)>max(min(a[0],b[0]),x)):
                        raise ValueError('Route crosses node '+id+'; choose another corridor')
    routed=[(i,e) for i,e in enumerate(spec.get('edges',[])) if e.get('routePoints')]
    for index,(i,e) in enumerate(routed):
        for j,f in routed[index+1:]:
            if any(overlap(a,b,c,d) for a,b in segments(e['routePoints']) for c,d in segments(f['routePoints'])):
                raise ValueError(f'Routes {i+1} and {j+1} overlap; split or relocate corridors')
    spec['_routingValidation']={'plannedEdges':len(routed),'groups':len(groups),'overlaps':0,'scope':'Explicit grouped routes only; not ungrouped auto routes or label collision'}
    return spec

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');a=p.parse_args()
    with open(a.input,encoding='utf-8-sig') as f: result=plan(json.load(f))
    with open(a.output,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
