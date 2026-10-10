# Kubernetes 复杂图实测

2026-10-10：使用当前 `visio-diagrams` 的 Python 后端生成两张通用技术示意图。
没有连接实际 Kubernetes 集群，也没有提交 Deployment。此目录包含经视觉修订的 VSDX、PNG、源输入和脱敏后的本机验收记录。

## 交付与验收

| 图 | 内容节点（含标题栏/说明） | 连线 | 判断 | 页面 | 正文/说明字号 |
|---|---:|---:|---:|---|---|
| k8s-architecture | 22 | 20 | 0 | 419.1 × 335.3 mm | 12 / 11 pt |
| deployment-pod-flow | 33 | 28 | 8 | 571.5 × 386.1 mm | 12 / 11 pt |

图内总标题 16 pt，流程阶段标题 14 pt；连线标签 10 pt，未自动缩字号。
适合大幅页面或放大查看，不把整张缩进 A4 正文后声称仍可读。
若缩至 146.6 mm 宽，流程正文会变成约 3.08 pt，架构正文约 4.20 pt。

两图已用独立隐藏 Visio 实例真实打开、读取文字/字号、核对全部规划路线顶点并
移动一个代表节点测试胶合跟随。实际字号误差小于 0.01 pt，路线偏差为 0；
代表节点移动 0.3 in，连接端点同量跟随。真实预览均已查看，未检测全部文件修复事件，
未承诺任意编辑或跨 Visio 版本兼容。

架构图人工路由：4 处正交交叉，无共线重叠；虚线表示 API 控制/观察，交叉不表示连接。
流程图：无交叉、无共线重叠；8 个否分支均有问题类型与修复/恢复说明。
独立审查覆盖节点与标签重叠、线路穿框、标签被线路穿越、正交性与共线重叠。
这些几何检查不代替业务语义审查。

## 当前 skill 暴露的边界

- Python 后端仍拒绝 container。本架构使用逻辑分区标题，不能声称是可拖动的原生嵌套容器。
- 复杂架构使用人工编写的正交路径与分数端口，由当前 writer 保存、独立审查。
  它证明生成与保存能力，不证明全图自动布局。
- 流程的固定主路径和分支由作者给定，复用当前 `local_layout.solve` 检查并放置标签。
  本次路径搜索状态为 0，不能当成复杂网格搜索能力的证据。
- 自动标签曾把跨列“是”放到另一判断旁；最终将该标签固定在原判断的出口附近，
  再独立检查。source spec 保存预规划结果，渲染时不再次路由。
- 生成阶段只运行 Python；仍需本机 VSSX 模具。Visio/COM 用于真实验收与 PNG 导出。
- 原有 skill 代码未为本次出图修改；新输入、作者脚本与说明位于此目录。

## Kubernetes 语义

架构图是通用逻辑组件关系，不是某个真实集群的部署或 HA 配置。图中控制平面、
节点运行时及扩展的位置不意味着都部署在同一机器；CoreDNS 作为集群 Pod 运行。
Service/EndpointSlice 是资源对象，服务转发由 kube-proxy 或替代数据面实现。
入口请求到 Pod 的箭头为逻辑路径，省略部分逐跳转发细节。

流程区分 Deployment 请求成功与工作负载完成：Deployment 控制器调谐 ReplicaSet，
ReplicaSet 控制器请求创建 Pod；每次 API 写入仍要经过对应权限/准入检查。
API 请求超时可能使结果未知，需要先查询对象，而不是直接认为资源未创建。
调度失败、配额/准入失败、挂载/网络失败、镜像失败、初始化/容器退出和未就绪
都是不同观察点。Running 不等于 Ready，Deployment rollout 超时也不意味着自动回滚。
箭头表示逻辑检查点；调谐是异步的，卷、网络与镜像准备的实现步骤可能交错。
异常框没有统一的自动恢复承诺：有的需要修复清单后重新 apply，有的等待控制器或节点重试。

机制来源（查阅日期 2026-10-10）：

- [Kubernetes Components](https://kubernetes.io/docs/concepts/overview/components/)
- [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [ReplicaSet](https://kubernetes.io/docs/concepts/workloads/controllers/replicaset/)
- [Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Admission Control](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)
- [Images / ImagePullBackOff](https://kubernetes.io/docs/concepts/containers/images/)
- [Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Services, Load Balancing, and Networking](https://kubernetes.io/docs/concepts/services-networking/)
- [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [kubectl apply](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_apply/)

## 复现

在仓库根运行 `python -X utf8 examples/k8s-complex/build_specs.py`，再将生成的 `.spec.json` 交给 `scripts/render_native.py`。输出路径必须不存在。
