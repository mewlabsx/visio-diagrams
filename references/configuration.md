# 配置与人工约束

所有几何尺寸单位为英寸，原点在页左上；配置写入同一输入 JSON，不增加第二套入口。

| 设置 | 默认值 | 实际作用 |
|---|---|---|
| page.colorFill | true | 白底黑字或彩色；CLI -ColorFill on/off 优先 |
| 节点 x/y/w/h | 必填 | 初始布局与尺寸；没有全局 direction 字段 |
| 节点 fixed | false | 禁止局部移动；折排模式遇到固定节点拒绝 |
| 边 fromPort/toPort | 按相对位置推断 | 局部模式支持四边中点；菱形四顶点 |
| 边 fixedRoute | 无 | 完整正交路径 [[x,y],…]，必须锁定两端节点并指定端口；优先占用通道 |
| localLayout.failurePolicy | stop | stop 报错；preserve 尝试原布局重新排线，成功标记 DEGRADED；仍失败不输出成功图 |
| adjust.maxShift | 必填 | 每节点每轴累计移动上限 |
| adjust.step / maxRounds / minGap | 0.2 / 2 / 0.15 | 候选移动步长、最多五轮、节点最小间距 |
| fold.mode / minNodes | auto / 8 | 符合单列条件的显式主路径折为两列 |
| fold.columnPitch / rowGap | 6 / 0.5 | 列中心间距及纵向间距 |
| routing.clearance | 0.18 | 自动线对无关节点的避让距离 |
| routing.maxStates | 80000 | 每次全线路解算的搜索状态预算；每个移动候选重新计数 |
| routing.bendPenalty / crossingPenalty | 2 / 4 | 转折和交叉成本；不保证零交叉 |

fixedRoute 是人工指定必经通道的具体方式，尚不支持只指定中间 waypoint 自动补齐。该路径检查页面、正交、节点内部穿越、端点出入方向与其他线重叠；不承诺自动线路的 clearance 缓冲。标签重新规划。局部模式可通过 routing.spreadPorts=true 为矩形共享边均分端口；它不与 routeGroup 同时解算。

## 交付报告

以下字段说明针对旧 COM 报告。默认 Python 后端的 GENERATED、structure.PASS 与独立 Visio 验收须分开阅读，详见 [python-backend.md](python-backend.md)。

validation.json 分开记录总 status、nativeVerification、visualReview、shapeSources、routing、localLayout、warnings 与 unresolvedIssues。PASS 表示脚本检查通过，仍需视觉验收；DEGRADED 表示原布局通过排线和原生保存检查，但优化未完成，必须说明 reason。routing.crossings 是不同线路在各自线段内部的正交交叉计数，不包含端点相接，也不等价于 Visio 线跳显示。

失败时 local_layout.py 保存 planned.failure.json（不覆盖已有诊断），状态 FAILED、错误原因及 nativeOutputAccepted=false；没有原生成功输出。报告不证明业务关系正确或整批历史素材均可自动重绘。
