# 原生嵌套容器与架构自动排线（0.2.0-dev）

本机已实现并验收，作为开发预览提供。默认仍用 Python 生成 VSDX，Visio 用于验收和预览。

## 显式成员与派生几何

```json
{
  "page": {"width": 12, "height": 8},
  "nodes": [
    {"id": "system", "kind": "container", "text": "系统"},
    {"id": "zone", "kind": "container", "text": "服务域", "parent": "system"},
    {"id": "service", "text": "服务", "parent": "zone", "x": 3, "y": 3, "w": 2, "h": 1}
  ],
  "edges": []
}
```

`parent` 只允许指向 container，单父关系，无环；不是根据几何位置猜归属。
容器必须有成员，`padding` 默认 0.25 in，`headerHeight` 默认 0.45 in。
框体自底向上按直接成员包围盒、留白、标题高度派生，作者给的容器 x/y/w/h 会被重算。
坐标仍是页顶原点的绝对英寸。只允许祖先/后代重叠；兄弟及其他无关节点重叠会失败。
容器必须在页内，并避开已有页标题；长标题需要明确增加宽度或 headerHeight。
如需锁定位置，对叶子节点设 fixed；派生容器本身不接受 fixed。

容器用原生 `User.msvStructureType="Container"` 标记，成员双方写 `Relationships`
中的 `DEPENDSON(1,...)` 和 `DEPENDSON(4,...)`。成员仍是页面形状，并非 group 内子形状。
先画祖先再画后代，容器标题占独立文字条；文本框带随实例尺寸变化的公式。
fold/adjust 后重新派生边界；此机制不是容器间自动布局。跨列后无关容器互压时拒绝。
adjust.order 必须列叶子节点，不能移动一份会被重算掉的容器坐标。

## 有界排线

```json
"localLayout": {
  "routing": {
    "spreadPorts": true,
    "routeAttempts": 4,
    "channelLanes": 3,
    "channelSpacing": 0.12,
    "portMargin": 0.12,
    "minPortSpacing": 0.12,
    "clearance": 0.12,
    "maxStates": 350000
  }
}
```

输入节点位置仍由作者组织；算法只求边的路径。最多 40 节点（含容器/文字）、80 边。
容器边界可穿越，成员及标题条为障碍物；独立文字也避让。边端点暂仅支持实体叶子节点。
同侧多线可在矩形边上按对端位置排序、均分端口；端口会真实写入 Connection 行。
空间不足明确失败，不能靠缩字号或把菱形端点移到斜边补救。共享固定路线及非矩形共享端口仍拒绝。

`routeAttempts` 为 1..4（默认 1），尝试输入顺序、逆序、短边优先和长边优先；保持最终边序与拓扑。
`channelLanes` 为 1..6（默认 1），为障碍物外增加候选平行通道；间距为 channelSpacing。
这些参数增加搜索空间与时间，不能无上限增大。maxStates 是每次尝试的状态预算，不是整个请求的总预算。
若设置 `maxCrossings`，超过交叉上限必须失败；不设置时允许交叉，并报告数量。
共线重叠与穿入节点/标题始终不允许。标签有避碰检查，但最终仍要查看实际预览。
四种线序重排不等于一般 rip-up/reroute，也不是全图最优解。

## 真实验收与边界

验收脚本逐容器检查直接业务成员，并单独记录 Visio 自动归属的连接线/标签。
移动每级容器时，检查所有业务后代同量移动、无关业务节点保持原位。
COM 自动化要显式设置 `Document.DiagramServicesEnabled=2` 维护已有结构关系；默认是关闭，
这个设置不跨会话持久化，也不改变 UI 自身的行为。

- 三层样例：4 个容器，12 个内容节点，9 条自动边，1 处交叉，0 共线重叠；逐级移动跟随通过。
- 压力样例：5 个容器，25 个内容节点，37 条自动边，18 路共享端口；24 处交叉，0 共线重叠。
- 两图真实保存路线偏差为 0，字号保持输入值，成员与后代移动检查通过。
- 这些是本机特定样例，不能推成任意规模、跨版本或所有鼠标编辑行为保证。
- 人工修改节点或容器后，端点仍可胶合跟随，但中间路径不保证继续避障，需要重新生成规划。

样例：`assets/nested-architecture-example.json`、`assets/complex-routing-stress.json`。
当前压力图虽然可读出关系，交叉偏多，不作为优质自动版式的验收样本。

依据：[Relationships](https://learn.microsoft.com/en-us/office/client-developer/visio/relationships-cell-shape-layout-section)、
[DiagramServicesEnabled](https://learn.microsoft.com/en-us/office/vba/api/visio.document.diagramservicesenabled)、
[GetMemberShapes](https://learn.microsoft.com/en-us/office/vba/api/visio.containerproperties.getmembershapes)。
