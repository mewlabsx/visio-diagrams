"""Authored Kubernetes examples for the existing Python Visio skill.

Does not change the skill. The process uses its bounded router; architecture
routes are explicitly authored and independently audited before rendering.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1]
sys.path.insert(0, str(SKILL/'scripts'))
from local_layout import crosses_node, solve
from plan_routes import segments, overlap, simplify, point as planner_point

BLUE, GREEN, ORANGE, YELLOW = '#BDD7EE', '#D7E3BF', '#F7CBAC', '#FEE599'


def node(id, text, x, y, w, h, kind='box', fill='#FFFFFF', size=12, bold=False):
    return dict(id=id, text=text, x=x, y=y, w=w, h=h, kind=kind,
                fill=fill, fontSize=size, bold=bold)


def port(n, side, fraction=.5):
    x,y,w,h=(n[k] for k in ('x','y','w','h'))
    return [round(v,8) for v in {'left':[x,y+h*fraction], 'right':[x+w,y+h*fraction],
            'top':[x+w*fraction,y], 'bottom':[x+w*fraction,y+h]}[side]]


def architecture():
    s={'page':{'width':16.5,'height':13.2,'title':'Kubernetes 架构：控制平面、节点执行与服务数据面','colorFill':True},
       'nodes':[], 'edges':[], '_authoring':{'routing':'explicit authored orthogonal routes',
       'grouping':'logical captions; no native container membership', 'fontPolicy':'preserve input sizes'}}
    ns=s['nodes']
    ns.extend([
      node('control_caption','控制平面：所有资源状态读写经 API；下方箭头表示逻辑交互',.7,.8,14.7,.4,'text',size=13,bold=True),
      node('client','kubectl / CI/CD\n应用 Deployment 清单',.7,1.5,3,.9,fill=GREEN),
      node('api','kube-apiserver（可多副本）\n认证 / 授权 / 准入 / 资源 API\nREST 请求与 watch',5.1,1.5,4.5,1.25,fill=BLUE,bold=True),
      node('etcd','etcd\n资源状态持久化 / 一致性存储',11.2,1.5,3.6,.9,fill=BLUE),
      node('scheduler','kube-scheduler\n筛选 / 打分 / Pod 绑定',.7,3.8,3,.95,fill=BLUE),
      node('controllers','kube-controller-manager\nDeployment / ReplicaSet / Node\nEndpointSlice 等控制器调谐',5.1,3.8,4.5,.95,fill=BLUE),
      node('cloud','cloud-controller-manager\n可选：节点 / 路由 / 云负载均衡',11.2,3.8,3.6,.95,fill=BLUE),
      node('worker_caption','工作节点与集群扩展：以一个 Worker 的执行链为例，可水平扩展',.7,5.25,10.6,.4,'text',size=13,bold=True),
      node('kubelet','kubelet\n同步 PodSpec / 上报状态',.7,6.4,3,.85,fill=GREEN),
      node('runtime','CRI 容器运行时\n例如 containerd / CRI-O',4.6,6.4,3,.85,fill=GREEN),
      node('pod','Pod / 应用容器\n共享网络与卷 / 执行工作负载',8.5,6.4,3,.85,fill=GREEN),
      node('registry','镜像仓库（集群外）\n镜像 / 凭据 / 分发',12.4,6.4,3,.85,fill=ORANGE),
      node('csi','CSI 驱动（可选）\n卷发布 / 挂载 / 存储接入',.7,8,3,.9,fill=YELLOW),
      node('cni','CNI 网络插件\nPod IP / 网络配置',4.6,8,3,.9,fill=YELLOW),
      node('proxy','kube-proxy / 替代实现\n监听 Service / EndpointSlice\n编程 Service 转发数据面',8.5,8,3,.9,fill=YELLOW),
      node('dns','CoreDNS\nService 名称解析\n作为集群 Pod 运行',12.4,8,3,.9,fill=YELLOW),
      node('storage','外部存储（可选）\n块 / 文件 / 云盘',.7,9.8,3,.65,fill=ORANGE),
      node('network','节点网络 / 转发数据面\nPod 网络与网络策略',4.6,9.8,3,.65,fill=YELLOW),
      node('service','Service / EndpointSlice\n声明对象 ≠ 转发进程',8.5,9.8,3,.65,fill=BLUE),
      node('ingress','Gateway / Ingress Controller\n可选的北南向流量入口',12.4,9.8,3,.65,fill=YELLOW),
      node('user','业务客户端 / 外部请求',12.4,11.25,3,.6,fill=ORANGE),
      node('notes','图例：虚线 = API 观察与控制；实线 = 调用 / 配置 / 数据流（以标签区分）。交叉线不表示连接。\n这是通用逻辑架构，非某一集群部署清单；CoreDNS、代理及插件的实际部署位置取决于实现。\nService 访问由数据面实现转发，apiserver 不承载普通应用请求；入口图省略了部分逐跳转发细节。',.7,12.2,14.7,.8,'text',size=11),
    ])
    by={n['id']:n for n in ns}
    def edge(a,b,ap,bp,way=(),text='',label=None,af=.5,bf=.5,dashed=False):
        pts=simplify([port(by[a],ap,af), *[list(p) for p in way], port(by[b],bp,bf)])
        e=dict(fromPort=ap,toPort=bp,fromFraction=af,toFraction=bf,routePoints=pts,text=text,dashed=dashed)
        e['from'],e['to']=a,b
        if label: e['label']=dict(zip(('x','y','w','h'),label))
        s['edges'].append(e)
    edge('client','api','right','left',text='HTTPS',label=(3.95,1.62,.85,.24),bf=.36)
    edge('api','etcd','right','left',text='资源读写',label=(9.78,1.62,1.1,.24),af=.36)
    edge('scheduler','api','top','bottom',way=((2.2,3.2),(5.91,3.2)),text='watch / bind',label=(3.15,2.86,1.65,.24),bf=.18,dashed=True)
    edge('controllers','api','top','bottom',text='watch / reconcile',label=(7.65,3.39,2.25,.24),dashed=True)
    edge('cloud','api','top','bottom',way=((13,3.2),(8.79,3.2)),text='资源观察 / 云协调',label=(10,2.9,2,.24),bf=.82,dashed=True)
    edge('kubelet','api','left','left',way=((.35,6.825),(.35,2.625)),text='watch Pod / 状态',label=(.75,2.87,2.15,.24),bf=.9,dashed=True)
    edge('kubelet','runtime','right','left',text='CRI',label=(3.92,6.52,.45,.24))
    edge('runtime','pod','right','left',text='创建与执行',label=(7.61,6.5,.85,.24))
    edge('runtime','registry','top','top',way=((6.1,5.94),(13.9,5.94)),text='镜像拉取',label=(10.6,5.7,1.25,.2))
    edge('kubelet','csi','bottom','top',text='卷准备',label=(2.45,7.46,.8,.24))
    edge('runtime','cni','bottom','top',text='网络配置',label=(6.36,7.46,1,.24))
    edge('cni','pod','right','bottom',way=((8.04,8.45),(8.04,7.65),(9.1,7.65)),text='Pod 网络',label=(8.6,7.72,1.1,.2),bf=.2)
    edge('proxy','api','right','right',way=((12,8.45),(12,4.98),(15.9,4.98),(15.9,2.5625)),text='watch 网络资源',label=(12.2,5.15,1.9,.24),bf=.85,dashed=True)
    edge('pod','dns','right','top',way=((11.95,6.825),(11.95,7.55),(13.9,7.55)),text='DNS 查询',label=(12.5,7.70,1.1,.2))
    edge('csi','storage','bottom','top',text='存储接入',label=(2.44,9.18,1.05,.24))
    edge('cni','network','bottom','top',text='配置连通 / 策略',label=(6.34,9.18,1.9,.24))
    edge('service','proxy','top','bottom',text='规则来源',label=(10.24,9.18,1,.24),dashed=True)
    edge('proxy','network','bottom','right',way=((9.04,9.6),(8.15,9.6),(8.15,10.125)),text='转发规则',label=(8.24,9.26,.8,.24),af=.18)
    edge('ingress','pod','right','bottom',way=((16,10.125),(16,7.43),(10.9,7.43)),text='应用请求（逻辑）',label=(12.5,9.18,2.4,.24),bf=.8)
    edge('user','ingress','top','bottom',text='HTTPS',label=(14.15,10.72,.85,.24))
    return s


def process():
    s={'page':{'width':22.5,'height':15.2,'title':'kubectl apply Deployment YAML：Pod 创建与异常判断','colorFill':True,'diagramType':'flowchart'},
       'nodes':[],'edges':[], 'localLayout':{'routing':{'maxStates':600000,'clearance':.16,'bendPenalty':2,'crossingPenalty':6}}}
    columns=[
      [('start','开始：提交 Deployment\n目标 replicas > 0','terminator'),
       ('parse','kubectl 读取清单\n解析 YAML / 资源类型','box'),
       ('yaml_gate','清单解析与\n客户端检查通过？','diamond'),
       ('send','API 执行认证 / 授权 / 准入\n持久化 Deployment 后返回','box'),
       ('api_gate','API 请求成功\n且结果已确认？','diamond'),
       ('persist','kubectl 显示 created / configured\n仅确认 Deployment 已提交','box'),
       ('deploy_ctrl','Deployment 控制器异步调谐\n创建 / 调整 ReplicaSet','box')],
      [('rs_ctrl','ReplicaSet 控制器异步调谐\n经 API 请求创建 Pod','box'),
       ('pod_gate','Pod 对象创建成功？\n准入 / 配额等通过？','diamond'),
       ('schedule','scheduler 筛选 / 打分 / 绑定\n通过 API 写回调度结果','box'),
       ('schedule_gate','节点选择与\n绑定写回成功？','diamond'),
       ('bind','Pod 已绑定目标节点\n等待该节点 kubelet 同步','box'),
       ('kubelet','目标节点 kubelet 同步 Pod\n准备卷 / CRI sandbox / CNI','box'),
       ('setup_gate','卷、sandbox 与\n网络初始化成功？','diamond')],
      [('image','容器运行时准备所需镜像\n按 imagePullPolicy 获取 / 复用','box'),
       ('image_gate','所需镜像\n获取成功？','diamond'),
       ('start_containers','按需运行 initContainers\n创建并启动应用容器','box'),
       ('runtime_gate','初始化完成且应用\n能持续运行？','diamond'),
       ('observe','kubelet 检查探针 / readinessGates\n上报状态；控制器汇总 rollout','box'),
       ('ready_gate','期望副本达到可用条件\n且 rollout 完成？','diamond'),
       ('success','完成：目标 Pod Ready\nDeployment rollout 完成','terminator')],
    ]
    by={}
    for col,items in enumerate(columns):
        x=1.0+col*7.25
        s['nodes'].append(node('phase_'+str(col),['① 客户端与资源提交','② 控制器、Pod 对象与调度','③ 节点执行与工作负载就绪'][col],x,.78,6.3,.42,fill=BLUE,size=14,bold=True))
        for row,(id,text,kind) in enumerate(items):
            h=1.12 if kind=='diamond' else .8
            y=1.55+row*1.72
            n=node(id,text,x,y,3.15,h,kind,YELLOW if kind=='diamond' else (GREEN if kind=='terminator' else '#FFFFFF'))
            n['fixed']=True; s['nodes'].append(n); by[id]=n
    errors=[
      ('yaml_gate','err_yaml','清单无效 / 字段或类型错误\n修复 YAML 后重新 apply',0,2),
      ('api_gate','err_api','API 拒绝：修复凭据 / RBAC / 准入\n超时：先 GET 确认结果\n不要把响应丢失当成未创建',0,4),
      ('pod_gate','err_pod','Pod 尚未创建；检查控制器 Events\n配额 / 准入 / ServiceAccount\n修复后由控制器继续调谐',1,1),
      ('schedule_gate','err_schedule','Pending / FailedScheduling\n资源不足、亲和性、污点或 PVC\n修复约束 / 容量后等待重调度',1,3),
      ('setup_gate','err_setup','FailedMount / sandbox / CNI 错误\n检查存储与节点网络\n修复后 kubelet 继续同步',1,6),
      ('image_gate','err_image','ErrImagePull / ImagePullBackOff\n检查镜像、凭据与网络\n修复后等待退避重试',2,1),
      ('runtime_gate','err_runtime','Init 失败 / CrashLoopBackOff\n检查日志、退出码 / OOMKilled\n修复应用或配置；按策略重启',2,3),
      ('ready_gate','err_ready','Running 但未 Ready / rollout 超时\n排查探针、依赖与全部期望副本\n超时不代表自动回滚',2,5),
    ]
    for parent,id,text,col,row in errors:
        y=by[parent]['y']+.02
        n=node(id,text,4.72+col*7.25,y,2.53,1.0,fill=ORANGE,size=11)
        n['fixed']=True;s['nodes'].append(n);by[id]=n
    path=[id for col in columns for id,_,_ in col]
    for a,b in zip(path,path[1:]):
        ap='bottom';bp='top';pa,pb=planner_point(by[a],ap),planner_point(by[b],bp)
        if (a,b)==('deploy_ctrl','rs_ctrl'):
            ap='right';pa=planner_point(by[a],ap)
            pts=[pa,[7.58,pa[1]],[7.58,1.3],[pb[0],1.3],pb]
        elif (a,b)==('setup_gate','image'):
            pts=[pa,[pa[0],13.45],[14.83,13.45],[14.83,1.3],[pb[0],1.3],pb]
        else:pts=[pa,pb]
        e={'from':a,'to':b,'fromPort':ap,'toPort':bp,'fixedRoute':simplify(pts)}
        if by[a]['kind']=='diamond': e['text']='是'
        s['edges'].append(e)
    for parent,id,_,_,_ in errors:
        a,b=planner_point(by[parent],'right'),planner_point(by[id],'left')
        # Align the exception center to the decision's right vertex.
        by[id]['y']=a[1]-by[id]['h']/2;b=planner_point(by[id],'left')
        s['edges'].append({'from':parent,'to':id,'fromPort':'right','toPort':'left','text':'否', 'fixedRoute':[a,b]})
    s['nodes'].append(node('notes','阅读顺序：左列 → 中列 → 右列；箭头表示逻辑检查点，不是同步 RPC 调用；卷、网络与镜像步骤可交错。\n各控制器、scheduler 与 kubelet 异步协调；Deployment 请求通过不保证后续 Pod 准入、调度或就绪。\n异常框是观察与修复路径，并非统一终止状态；修复后按阶段重新提交或等待调谐。图中未展开自动重试循环。',.8,14.05,21,.8,fill=BLUE,size=11))
    planned=solve(s)
    # Preplanning uses the existing skill, then authorship pins one ambiguous label.
    # Do not route again at render time, which would discard this visual correction.
    planned.pop('localLayout')
    for e in planned['edges']:
        if e['from']=='setup_gate' and e['to']=='image':
            a=e['routePoints'][0]
            e['label']={'x':a[0]+.2,'y':a[1]+.07,'w':.35,'h':.24}
    planned['_authoring']={'routing':'existing local_layout.solve + authored fixedRoute',
                          'labelCorrection':'setup_gate true label pinned near source',
                          'fontPolicy':'preserve input sizes'}
    return planned


def audit(s):
    nodes={n['id']:n for n in s['nodes']}; failures=[]; crossings=0; paths=[]
    def collides(a,b):
        return min(a['x']+a['w'],b['x']+b['w'])-max(a['x'],b['x'])>1e-8 and min(a['y']+a['h'],b['y']+b['h'])-max(a['y'],b['y'])>1e-8
    ns=list(nodes.values())
    for i,a in enumerate(ns):
        for b in ns[i+1:]:
            if collides(a,b):failures.append(f'nodes {a["id"]}/{b["id"]} overlap')
    for i,e in enumerate(s['edges'],1):
        pts=e.get('routePoints') or e.get('fixedRoute')
        for a,b in segments(pts):
            if abs(a[0]-b[0])>1e-8 and abs(a[1]-b[1])>1e-8: failures.append(f'non-orthogonal edge {i}')
            for n in nodes.values():
                if crosses_node(a,b,n): failures.append(f'edge {i} crosses node {n["id"]}')
        paths.append((i,list(segments(pts))))
        if e.get('label'):
            box=e['label']
            for n in nodes.values():
                if collides(box,n):
                    failures.append(f'label {i} overlaps {n["id"]}')
    labels=[(i,e['label']) for i,e in enumerate(s['edges'],1) if e.get('label')]
    for i,box in labels:
        for j,p in paths:
            if any(crosses_node(a,b,box) for a,b in p):failures.append(f'label {i} crossed by edge {j}')
    for ii,(i,box) in enumerate(labels):
        for j,other in labels[ii+1:]:
            if collides(box,other):failures.append(f'labels {i}/{j} overlap')
    for ii,(i,p) in enumerate(paths):
        for j,q in paths[ii+1:]:
            for a,b in p:
                for c,d in q:
                    if overlap(a,b,c,d): failures.append(f'edges {i}/{j} overlap')
                    if a[1]==b[1] and c[0]==d[0] and min(a[0],b[0])<c[0]<max(a[0],b[0]) and min(c[1],d[1])<a[1]<max(c[1],d[1]):crossings+=1
                    if a[0]==b[0] and c[1]==d[1] and min(a[1],b[1])<c[1]<max(a[1],b[1]) and min(c[0],d[0])<a[0]<max(c[0],d[0]):crossings+=1
    if failures:raise ValueError('\n'.join(sorted(set(failures))))
    return {'status':'PASS','nodes':len(nodes),'edges':len(paths),'crossings':crossings,
            'scope':'Orthogonal routes, node interiors, node/label overlap, labels vs all routes, collinear overlap; not native container or global optimality'}


if __name__=='__main__':
    for name,spec in (('k8s-architecture',architecture()),('deployment-pod-flow',process())):
        receipt=audit(spec)
        (HERE/(name+'.spec.json')).write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
        (HERE/(name+'.authoring-audit.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,receipt)
