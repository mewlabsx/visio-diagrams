"""Bounded local placement, direction-preserving propagation and grid routing."""
import argparse,copy,heapq,json,math
from collections import defaultdict,deque
from pathlib import Path
from plan_routes import point,simplify,segments,overlap

def topology(s):return [(e['from'],e['to'],e.get('text','')) for e in s['edges']]
def solids(s):return [n for n in s['nodes'] if n.get('kind') not in ('container','text')]
def placement_ok(s,gap):
 ns=solids(s)
 for n in ns:
  if n['x']<0 or n['y']<0 or n['x']+n['w']>s['page']['width'] or n['y']+n['h']>s['page']['height']:return False
 for i,a in enumerate(ns):
  for b in ns[i+1:]:
   if min(a['x']+a['w']+gap,b['x']+b['w']+gap)>max(a['x'],b['x']) and min(a['y']+a['h']+gap,b['y']+b['h']+gap)>max(a['y'],b['y']):return False
 return True

def propagate(s,id,axis,delta,cfg):
 """Explicit dependency order: all later nodes translate equally, never backwards."""
 trial=copy.deepcopy(s);ns={n['id']:n for n in trial['nodes']};order=cfg['order']
 if len(set(order))!=len(order) or id not in order or any(i not in ns for i in order):raise ValueError('Invalid propagation order')
 if axis not in ('x','y') or not math.isfinite(delta):raise ValueError('Invalid displacement')
 graph=defaultdict(list)
 for e in s['edges']:graph[e['from']].append(e['to'])
 for a,b in zip(order,order[1:]):
  queue=[a];seen=set()
  while queue:
   current=queue.pop()
   if current in seen:continue
   seen.add(current);queue.extend(graph[current])
  if b not in seen:raise ValueError('Propagation order must follow directed reachability')
 affected=order[order.index(id):]
 if abs(delta)>cfg['maxShift']+1e-9 or any(ns[i].get('fixed') for i in affected):return None
 for i in affected:ns[i][axis]+=delta
 if not placement_ok(trial,cfg.get('minGap',.15)):return None
 return trial,affected

def fold(s,cfg):
 trial=copy.deepcopy(s);ns={n['id']:n for n in trial['nodes']};path=cfg['mainPath']
 if len(set(path))!=len(path) or any(id not in ns for id in path):raise ValueError('Invalid mainPath')
 links={(e['from'],e['to']) for e in trial['edges']}
 if any((a,b) not in links for a,b in zip(path,path[1:])):raise ValueError('mainPath order is not supported by edges')
 if any(n.get('kind')=='container' or n.get('fixed') for n in trial['nodes']):raise ValueError('Fold does not support containers or fixed nodes')
 centers=[ns[id]['x']+ns[id]['w']/2 for id in path]
 vertical=max(centers)-min(centers)<cfg.get('columnTolerance',.5)
 if cfg.get('mode','auto')=='auto' and (not vertical or len(path)<cfg.get('minNodes',8)):
  return trial,{'status':'not-needed'}
 # Never split immediately before/after a decision; require explicit branch anchoring.
 choices=[k for k in range(2,len(path)-1) if ns[path[k-1]].get('kind')!='diamond' and ns[path[k]].get('kind')!='diamond']
 if not choices:raise ValueError('No safe midpoint split')
 k=min(choices,key=lambda k:abs(k-len(path)/2));anchors=cfg.get('branchAnchors',{})
 extras=set(ns)-set(path)
 if extras-set(anchors):raise ValueError('Every off-main node needs a branchAnchor')
 original=copy.deepcopy(ns);width=max(ns[id]['w'] for id in path)
 for col,ids in enumerate((path[:k],path[k:])):
  y=cfg.get('top',.9);cx=cfg.get('firstCenter',4)+col*cfg.get('columnPitch',6)
  for id in ids:
   n=ns[id];n['x']=cx-n['w']/2;n['y']=y;y+=n['h']+cfg.get('rowGap',.5)
 for id,parent in anchors.items():
  if id not in extras or parent not in path:raise ValueError('Invalid branch anchor')
  ns[id]['x']=ns[parent]['x']+original[id]['x']-original[parent]['x']
  ns[id]['y']=ns[parent]['y']+original[id]['y']-original[parent]['y']
 trial['page']['width']=max(n['x']+n['w'] for n in ns.values())+.6
 trial['page']['height']=max(n['y']+n['h'] for n in ns.values())+1
 if not placement_ok(trial,cfg.get('minGap',.15)):raise ValueError('Fold violates node spacing; adjust columnPitch/branch offsets')
 # Recompute routing and labels rather than preserve stale coordinates.
 for e in trial['edges']:
  if e.get('fixedRoute'):raise ValueError('Fold does not support fixedRoute')
  for key in ('routePoints','fromFraction','toFraction','label','routeGroup'):e.pop(key,None)
  if (e['from'],e['to']) in set(zip(path,path[1:])):
   e['fromPort']='right' if (e['from'],e['to'])==(path[k-1],path[k]) else 'bottom'
   e['toPort']='top'
 return trial,{'status':'folded','splitAfter':path[k-1],'columns':[path[:k],path[k:]],'readingOrder':'left column top-down, then right column top-down'}

def crosses_node(a,b,n):
 x,y,w,h=n['x'],n['y'],n['w'],n['h'];eps=1e-8
 if abs(a[0]-b[0])<eps:return x+eps<a[0]<x+w-eps and min(max(a[1],b[1]),y+h)-max(min(a[1],b[1]),y)>eps
 return y+eps<a[1]<y+h-eps and min(max(a[0],b[0]),x+w)-max(min(a[0],b[0]),x)>eps

def route_all(s,cfg):
 if len(s['nodes'])>40 or len(s['edges'])>80:raise ValueError('Local solver supports at most 40 nodes and 80 edges')
 if any(n.get('kind') in ('container','text') for n in s['nodes']):raise ValueError('Local solver does not yet support containers or preplaced text nodes')
 if not placement_ok(s,0):raise ValueError('Original placement overlaps or exceeds page')
 result=copy.deepcopy(s);ns={n['id']:n for n in solids(s)};clear=cfg.get('clearance',.18)
 if clear<=0 or not math.isfinite(clear) or cfg.get('bendPenalty',2)<0 or cfg.get('crossingPenalty',4)<0 or cfg.get('maxStates',80000)<1:raise ValueError('Invalid routing budget or cost')
 if any(e['from'] not in ns or e['to'] not in ns for e in s['edges']):raise ValueError('All routed endpoints must be solid nodes')
 def sides(e):
  a,b=ns[e['from']],ns[e['to']];dx=b['x']+b['w']/2-a['x']-a['w']/2;dy=b['y']+b['h']/2-a['y']-a['h']/2
  return (('right','left') if dx>0 else ('left','right')) if abs(dx)>abs(dy) else (('bottom','top') if dy>0 else ('top','bottom'))
 used=defaultdict(int)
 for e in result['edges']:
  ap,bp=sides(e);e['fromPort']=e.get('fromPort',ap);e['toPort']=e.get('toPort',bp)
  for end in ('from','to'):
   used[(e[end],e[end+'Port'])]+=1
 # Refuse multi-line shared port until explicit legal port spreading is provided.
 if any(count>1 for count in used.values()):raise ValueError('Shared endpoint ports: specify distinct fromPort/toPort before local routing')
 xs={.25,s['page']['width']-.25};ys={.7,s['page']['height']-.25}
 for n in ns.values():
  xs.update([n['x']-clear,n['x'],n['x']+n['w']/2,n['x']+n['w'],n['x']+n['w']+clear])
  ys.update([n['y']-clear,n['y'],n['y']+n['h']/2,n['y']+n['h'],n['y']+n['h']+clear])
 xs=sorted(x for x in xs if 0<=x<=s['page']['width']);ys=sorted(y for y in ys if .6<=y<=s['page']['height'])
 reserved=[];states=0;limit=cfg.get('maxStates',80000);crossings=0
 for e in sorted(result['edges'],key=lambda e:not bool(e.get('fixedRoute'))):
  a=point(ns[e['from']],e['fromPort']);b=point(ns[e['to']],e['toPort'])
  if e.get('fixedRoute'):
   pts=e['fixedRoute']
   if not ns[e['from']].get('fixed') or not ns[e['to']].get('fixed'):raise ValueError('fixedRoute requires fixed endpoint nodes')
   if len(pts)<2 or pts[0]!=a or pts[-1]!=b:raise ValueError('fixedRoute endpoint mismatch')
   if any(len(p)!=2 or any(not math.isfinite(v) for v in p) or not 0<=p[0]<=s['page']['width'] or not .6<=p[1]<=s['page']['height'] for p in pts):raise ValueError('Invalid fixedRoute point')
   path=list(segments(pts))
   if any(overlap(a,b,c,d) for i,(a,b) in enumerate(path) for c,d in path[i+1:]):raise ValueError('fixedRoute self overlap')
   if any(crosses_node(c,d,n) for c,d in path for n in ns.values()) or any(overlap(c,d,f,g) for c,d in path for f,g in reserved):raise ValueError('fixedRoute collision')
   for side,p,q in ((e['fromPort'],pts[0],pts[1]),(e['toPort'],pts[-1],pts[-2])):
    if not {'right':q[0]>p[0] and q[1]==p[1],'left':q[0]<p[0] and q[1]==p[1],'top':q[1]<p[1] and q[0]==p[0],'bottom':q[1]>p[1] and q[0]==p[0]}[side]:raise ValueError('fixedRoute must leave endpoint outward')
   e['routePoints']=simplify(pts);reserved.extend(path);continue
  start=(xs.index(a[0]),ys.index(a[1]));end=(xs.index(b[0]),ys.index(b[1]))
  queue=[(0,0,start,None)];best={(start,None):0};parent={};finish=None;serial=0
  while queue:
   cost,_,v,direction=heapq.heappop(queue);state=(v,direction)
   if cost>best.get(state,float('inf')):continue
   states+=1
   if states>limit:raise ValueError('Routing search budget exceeded')
   if v==end:finish=state;break
   i,j=v;p=[xs[i],ys[j]]
   for ni,nj,axis in ((i-1,j,'h'),(i+1,j,'h'),(i,j-1,'v'),(i,j+1,'v')):
    if not 0<=ni<len(xs) or not 0<=nj<len(ys):continue
    q=[xs[ni],ys[nj]]
    if v==start:
     if (e['fromPort']=='right' and not(q[0]>p[0] and axis=='h')) or (e['fromPort']=='left' and not(q[0]<p[0] and axis=='h')) or (e['fromPort']=='top' and not(q[1]<p[1] and axis=='v')) or (e['fromPort']=='bottom' and not(q[1]>p[1] and axis=='v')):continue
    if (ni,nj)==end:
     side=e['toPort']
     if (side=='right' and not(p[0]>q[0] and axis=='h')) or (side=='left' and not(p[0]<q[0] and axis=='h')) or (side=='top' and not(p[1]<q[1] and axis=='v')) or (side=='bottom' and not(p[1]>q[1] and axis=='v')):continue
    if any(crosses_node(p,q,n if id in (e['from'],e['to']) else dict(n,x=n['x']-clear,y=n['y']-clear,w=n['w']+2*clear,h=n['h']+2*clear)) for id,n in ns.items()) or any(overlap(p,q,c,d) for c,d in reserved):continue
    cross=sum(1 for c,d in reserved if (p[1]==q[1] and c[0]==d[0] and min(p[0],q[0])<c[0]<max(p[0],q[0]) and min(c[1],d[1])<p[1]<max(c[1],d[1])) or (p[0]==q[0] and c[1]==d[1] and min(p[1],q[1])<c[1]<max(p[1],q[1]) and min(c[0],d[0])<p[0]<max(c[0],d[0])))
    nc=cost+abs(p[0]-q[0])+abs(p[1]-q[1])+(cfg.get('bendPenalty',2) if direction and direction!=axis else 0)+cross*cfg.get('crossingPenalty',4)
    nextstate=((ni,nj),axis)
    if nc<best.get(nextstate,float('inf')):
     best[nextstate]=nc;parent[nextstate]=state;serial+=1;heapq.heappush(queue,(nc,serial,(ni,nj),axis))
  if finish is None:raise ValueError('No legal route for '+e['from']+' -> '+e['to'])
  points=[];current=finish
  while current:
   (i,j),_=current;points.append([xs[i],ys[j]]);current=parent.get(current)
  e['routePoints']=simplify(list(reversed(points)));reserved.extend(segments(e['routePoints']))
  e.pop('label',None)
 labels=[]
 for e in result['edges']:
  if not e.get('text'):continue
  w=max(.35,len(e['text'])*.15+.1);h=.24;found=None
  paths=sorted(list(segments(e['routePoints'])),key=lambda ab:-(abs(ab[0][0]-ab[1][0])+abs(ab[0][1]-ab[1][1])))
  for a,b in paths:
   for fraction in (.5,.25,.75):
    for offset in (-.23,.23,-.4,.4):
     cx=a[0]+fraction*(b[0]-a[0]);cy=a[1]+fraction*(b[1]-a[1])
     if a[0]==b[0]:cx+=offset+w/2 if offset>0 else offset-w/2
     else:cy+=offset
     box={'x':cx-w/2,'y':cy-h/2,'w':w,'h':h}
     if box['x']<0 or box['y']<.65 or box['x']+w>s['page']['width'] or box['y']+h>s['page']['height']:continue
     if any(min(box['x']+w,n['x']+n['w'])>max(box['x'],n['x']) and min(box['y']+h,n['y']+n['h'])>max(box['y'],n['y']) for n in list(ns.values())+labels):continue
     if any(crosses_node(c,d,box) for c,d in reserved):continue
     found=box;break
    if found:break
   if found:break
  if not found:raise ValueError('No label clearance for '+e['text'])
  e['label']=found;labels.append(found)
 crossings=sum(1 for i,e in enumerate(result['edges']) for other in result['edges'][i+1:] for a,b in segments(e['routePoints']) for c,d in segments(other['routePoints']) if (a[1]==b[1] and c[0]==d[0] and min(a[0],b[0])<c[0]<max(a[0],b[0]) and min(c[1],d[1])<a[1]<max(c[1],d[1])) or (a[0]==b[0] and c[1]==d[1] and min(a[1],b[1])<c[1]<max(a[1],b[1]) and min(c[0],d[0])<a[0]<max(c[0],d[0])))
 result['_routingValidation']={'plannedEdges':len(result['edges']),'overlaps':0,'crossings':crossings,'searchStates':states,'totalBends':sum(len(e['routePoints'])-2 for e in result['edges']),'labelsPlaced':len(labels),'scope':'All local routes and label rectangles checked; crossings penalized; visual QA still required'}
 return result

def _solve(s):
 original=topology(s);cfg=s['localLayout'];work=copy.deepcopy(s);receipt={'moves':[]}
 if len(s['nodes'])>40 or len(s['edges'])>80:raise ValueError('Local solver supports at most 40 nodes and 80 edges')
 if any(n.get('kind') in ('container','text') for n in s['nodes']):raise ValueError('Local solver does not yet support containers or preplaced text nodes')
 if cfg.get('fold') and cfg.get('adjust'):raise ValueError('Fold and local adjustment must run in separate requests')
 if cfg.get('fold'):work,receipt['fold']=fold(work,cfg['fold'])
 baseline=route_all(work,cfg.get('routing',{}));score=baseline['_routingValidation']['totalBends']
 receipt['initialBends']=score
 if cfg.get('adjust'):
  directions={}
  adj=cfg['adjust'];step=adj.get('step',.2);rounds=adj.get('maxRounds',2)
  if step<=0 or not math.isfinite(step) or not 0<=adj['maxShift'] or not 1<=rounds<=5:raise ValueError('Invalid adjustment budget')
  for _ in range(rounds):
   improved=False
   for id in adj['order']:
    for axis in ('x','y'):
     for delta in (-step,step):
      candidate=propagate(work,id,axis,delta,adj)
      if not candidate:continue
      trial,affected=candidate
      sign=1 if delta>0 else -1
      if any(directions.get((id,axis),sign)!=sign for id in affected):continue
      # Cumulative movement remains inside the configured bounds.
      initial={n['id']:n for n in s['nodes']}
      if any(abs(n[k]-initial[n['id']][k])>adj['maxShift']+1e-9 for n in trial['nodes'] for k in ('x','y')):continue
      try:planned=route_all(trial,cfg.get('routing',{}))
      except ValueError:continue
      newscore=planned['_routingValidation']['totalBends']
      if newscore<score:
       work=trial;baseline=planned;score=newscore
       for id in affected:directions[(id,axis)]=sign
       receipt['moves'].append({'axis':axis,'delta':delta,'affected':affected});improved=True;break
     if improved:break
    if improved:break
   if not improved:break
 if topology(baseline)!=original:raise ValueError('Topology changed')
 receipt['status']='PASS';receipt['totalBends']=score
 baseline['_localLayout']=receipt
 return baseline

def solve(s):
 policy=s['localLayout'].get('failurePolicy','stop')
 if policy not in ('stop','preserve'):raise ValueError('Invalid failurePolicy')
 try:return _solve(s)
 except ValueError as error:
  if policy=='stop':raise
  # Only deliver a independently routed original layout, never unchecked auto-lines.
  baseline=route_all(s,s['localLayout'].get('routing',{}))
  baseline['_localLayout']={'status':'DEGRADED','moves':[],'reason':str(error),'preservedOriginalPositions':True}
  return baseline

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');args=p.parse_args()
 target=Path(args.output)
 if target.exists():raise SystemExit('Refusing to overwrite: '+str(target))
 s=json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
 try:result=solve(s)
 except (ValueError,KeyError,TypeError) as error:
  diagnostic=target.with_suffix('.failure.json')
  if not diagnostic.exists():diagnostic.write_text(json.dumps({'status':'FAILED','reason':str(error),'nativeOutputAccepted':False},ensure_ascii=False,indent=2),encoding='utf-8')
  raise SystemExit(str(error))
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
