# Python VSDX 后端

## 入口与资源

`scripts/render_native.py input.json output.vsdx [--stencil path.vssx] [--color-fill spec|on|off]`

入口先复用 `local_layout.py` 或 `plan_routes.py`，再调用 `vsdx_writer.py` 写 OOXML。
没有规划字段时使用直连，报告列出 `unplannedEdges`；这不等于全线路避障。
字号按输入写入真实 Character 节，生成器不做自动缩字号。

发布版以本 skill 目录为维护真源；旧探索原型不是正式入口。

默认 VSSX 路径为 Office16 的 `Visio Content/2052/BASFLO_M.VSSX`。
Python 生成不启动 Office，但读取该模具资源，不能宣传为零 Office 资源依赖。
`--stencil` 优先于默认路径；旧 spec 的 page.stencilPath 仅供 COM，Python 不自动
采纳它，以免把历史自绘降级路径误当成正确资源。未分发微软模具。

`assets/vsdx-base/` 包含从本项目 COM 样本提取的文档样式、页面与窗口 XML，
没有源图形、作者属性或缩略图；生成时重新写页宽、高和全部 shapes/masters。
原型根关系曾保留指向未复制缩略图的悬空引用，正式入口已经移除。

## 覆盖与拒绝

- box / diamond / terminator 使用 Process / Decision / Start/End；ellipse 与 text 自绘。
- 仅支持这些基本几何的母版映射，拒绝任意复杂母版，不能用几何覆盖冒充其语义。
- 连接线使用 Dynamic connector；规划折点写入旋转局部坐标；端点用 Connection 行胶合。
- 成组分数端口追加连接行，坐标与 Width/Height 相对公式一起写入；路线端点必须匹配胶合点。
- 容器模型、原生成员关系、泳道和复杂 UML 仍未接受；container 输入明确拒绝。
- 直连边与线上标签的整体观感仍需检查；独立标签保留固定位置，移动节点不会随动。
- 生成成功不能证明完整编辑行为：代表节点移动测试仅覆盖被测节点/边。

## 容易丢失的文件契约

母版元数据在 masters.xml，几何在独立 masterN.xml；配对由子元素 Rel 的 r:id 指向关系。
复制母版部件保持原始 XML，避免不必要的命名空间改写；XML 前缀本身不是普遍的非法条件。
实例必须覆盖实际尺寸的 Geometry、Txt*、Connection 缓存值，不能仅改 Width/Height。
Connection IX 是零基，引用 Connections.Xn 是一基，ToPart 是 99+n。
自绘几何同时写实际 V 值；连接线使用 Begin/End 派生的 Pin、Width、Angle 公式。
`Char.*`、`Para.*` 是 ShapeSheet 地址，文件中应写 Character、Paragraph 的 Section/Row，
不能直接写成顶层 Cell N='Char.Size'。否则文件能打开，文字却可能沿用默认样式。
标题与标签必须显式给 LocPin/Txt*，避免文字或对象偏离中心。
当前写入器把 Content_Types 放在 ZIP 第一项以保持已测写入顺序；不把这一经验当成 OPC 普遍要求。

## 证据分层

1. `.validation.json`：GENERATED、离线 ZIP/XML/关系目标与对象计数，未运行项为 NOT_RUN。
2. `.visio-validation.json`：真实打开、母版解析记录、文字/字号、规划路线逐点比对和代表节点移动。
3. PNG 人工检查：版面、文字裁切、最终观看尺寸；另记是否做过，不拿机器 PASS 替代。

真实验收要求 planned.json；缺文件、缺路线或覆盖数量不足必须失败。
独立隐藏实例与用户窗口分开，正常路径关闭自己的实例。COM 可能卡住，应以受限时长
的外层进程运行；发现旧隐形进程只报告，不把“无标题”当成可以任意结束的所有权证据。
Visio 的 AlertResponse 抑制弹窗不是“没有发生修复”的证据，本验证未检测全部修复事件。

回归：`python -X utf8 -m unittest discover -s scripts -p "test_*.py"`。
写入器测试需要本地 VSSX；资源缺失时的 skip 不能写成已通过该层。
当前结构测试不依赖 Visio/COM，真实验收仍依赖 Visio；跨版本未验证。
