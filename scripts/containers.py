"""Explicit containment, derived geometry and native relationship metadata."""
import copy
import math


def hierarchy(spec):
    nodes={}
    for n in spec['nodes']:
        if not isinstance(n.get('id'),str) or not n['id'] or n['id'] in nodes:
            raise ValueError('Empty or duplicate node id')
        nodes[n['id']]=n
    parents={};children={id:[] for id in nodes};ancestors={}
    for id,n in nodes.items():
        if n.get('parent') is not None:
            parent=n['parent']
            if parent not in nodes or nodes[parent].get('kind')!='container':
                raise ValueError('Parent must reference a container: '+id)
            parents[id]=parent;children[parent].append(id)
    def visit(id,active):
        if id in active:raise ValueError('Containment cycle at '+id)
        if id in ancestors:return ancestors[id]
        ancestors[id]=[] if id not in parents else [parents[id],*visit(parents[id],active|{id})]
        return ancestors[id]
    for id in nodes:visit(id,set())
    return nodes,parents,children,ancestors


def prepare(spec):
    result=copy.deepcopy(spec)
    ns,parents,children,ancestors=hierarchy(result)
    for id in sorted(ns,key=lambda id:len(ancestors[id]),reverse=True):
        n=ns[id]
        if n.get('kind')!='container':continue
        if n.get('fixed'):raise ValueError('Derived containers cannot be fixed; fix their leaf members')
        if not children[id]:raise ValueError('Empty containers are not supported: '+id)
        padding=n.get('padding',.25);header=n.get('headerHeight',.45)
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in (padding,header)):
            raise ValueError('Invalid container padding/header height')
        members=[ns[c] for c in children[id]]
        if any(any(not isinstance(c.get(k),(int,float)) or isinstance(c.get(k),bool) or not math.isfinite(c[k]) for k in ('x','y','w','h')) for c in members):
            raise ValueError('Invalid child geometry in '+id)
        left=min(c['x'] for c in members)-padding
        top=min(c['y'] for c in members)-padding-header
        right=max(c['x']+c['w'] for c in members)+padding
        bottom=max(c['y']+c['h'] for c in members)+padding
        n.update(x=left,y=top,w=right-left,h=bottom-top,padding=padding,headerHeight=header)
    containers=sorted((n for n in result['nodes'] if n.get('kind')=='container'),key=lambda n:len(ancestors[n['id']]))
    result['nodes']=containers+[n for n in result['nodes'] if n.get('kind')!='container']
    return result


def related(a,b,ancestors):
    return a['id'] in ancestors[b['id']] or b['id'] in ancestors[a['id']]


def validate_geometry(spec):
    nodes,_,_,ancestors=hierarchy(spec)
    if not any(n.get('kind')=='container' for n in nodes.values()):return
    ns=list(nodes.values())
    for i,a in enumerate(ns):
        if a.get('kind')=='container' and spec['page'].get('title') and a['y']<.65:
            raise ValueError('Container overlaps page title: '+a['id'])
        for b in ns[i+1:]:
            if related(a,b,ancestors):continue
            if min(a['x']+a['w'],b['x']+b['w'])-max(a['x'],b['x'])>1e-8 and min(a['y']+a['h'],b['y']+b['h'])-max(a['y'],b['y'])>1e-8:
                raise ValueError('Unrelated nodes overlap: '+a['id']+'/'+b['id'])


def obstacles(spec):
    result=[]
    for n in spec['nodes']:
        if n.get('kind')=='container':
            result.append(dict(n,id='__heading_'+n['id'],h=n['headerHeight']))
        else:result.append(n)
    return result
