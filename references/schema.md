# 中间 JSON 格式

UTF-8，单位英寸，节点坐标 x/y 为左上角，y 从页顶向下。不要使用 Visio 底部原点坐标；脚本负责转换。

## 后端区别

默认 Python 后端的资源、母版范围和证据状态见 [python-backend.md](python-backend.md)。
下文的动态中心胶合、自动路由、自绘降级及原生打开报告描述旧 COM 后端。
Python 对未规划边使用指定端口间直线，端口省略时为 from bottom / to top；
不保证自动避障，报告用 unplannedEdges 标明数量。Python 支持显式 parent 的原生 container，仍拒绝任意复杂母版；旧视觉边界且未声明成员的输入使用 `-Backend com`。
Python 与 COM 均保留输入字号；长图应根据最终可用宽高决定扩页、重排或拆图。
当前还没有自动化最终插入宽高与有效字号检查，不得宣称已经保证大图可读性。

## 字段

page：width、height 为正数，title 可选。

page.colorFill：可选布尔值，默认 true。false 关闭彩色填充，所有节点使用白色；命令行 -ColorFill on / off 优先于 JSON，默认 spec。

page.diagramType=flowchart：box（含省略 kind）、diamond、terminator 优先映射基本流程母版。page.stencilPath 可显式指定本机模具绝对路径；节点 master 使用母版 NameU，显式选择优先于映射。默认只定位本机 Office 的 2052/BASFLO_M.VSSX；其他语言/安装路径使用 stencilPath。不可用时警告并自绘，报告记录来源。其他图型没有自动母版映射；复杂 UML 母版适配尚未验证。

成组排线：顶层 routingGroups 为命名对象，示例 {"parallel":{"axis":"vertical","center":5,"spacing":0.35}}；edge.routeGroup 引用名称，且必须提供两端 fromPort/toPort。vertical 通道须使用左右端口，horizontal 须用上下端口。center 是页顶原点坐标中的 x 或 y，spacing 是英寸。routing.portMargin 默认 0.12 英寸，routing.minSpacing 默认 0.12 英寸。矩形同边的分组线自动均分端点；菱形、椭圆和开始/结束不允许多条分组线共用一个端口，会拒绝并要求分流。参考 assets/grouped-example.json。fromFraction/toFraction 和 routePoints 是规划器生成的内部字段，不应手写。

kind 另支持 terminator：开始/结束胶囊形圆角框（矩形直边、半圆端部），圆角半径取较短边的一半；流程开始/结束必须用此类型。ellipse 仅用于需求明确要求的椭圆节点。

routingGroups.<名称>.optimizeLayout 可设 {"moveNode":"b","maxShift":1.4}，启用单个线组、一个共享矩形节点对的局部直连优化。节点两端必须使用面对的左右或上下一对端口；两端不得参与其他连线。移动仅沿端口分布方向（左右端口移动 y，上下端口移动 x），不超过 maxShift，检查页边界、节点碰撞和候选直线路径；共同投影需容纳端点留白及 (线数-1)×spacing。无可行直连时保持原位置并回退固定通道。容器归属、固定标签的随动、UML 约束及一般关联关系不自动处理；需要这些约束的节点不要开启此模式。示例见 assets/layout-optimized-example.json；实际位移和结果在 planned.json 与 validation.json 中记录。

nodes 数组：id 唯一且非空；text 字符串；x/y 非负；w/h 正数且节点完全在页内。kind 为 box（默认）、container、text、ellipse、diamond。可选 fill 为 #RRGGBB、fontSize 为正 pt、bold 为布尔值、dashed 为布尔值。Python 中 kind=container 使用原生成员关系；子节点 parent 指向容器 ID，容器 padding/headerHeight 与子节点包围盒决定 x/y/w/h。不要用 children 或按位置隐式归属。COM 旧路线中的 container 仍仅是视觉边界。

先列容器，再列节点，以保证绘制层次。容器标题默认顶部；普通节点文字居中。长标签主动加 \n 换行。

edges 数组：from/to 引用节点 id；text 可选；dashed 可选；label 可选为 {x,y,w,h} 指定独立标签框。默认标签是连接线文字；密集接口图优先独立 label。箭头由 from 指向 to，动态胶合到节点中心，由 Visio 负责路由。不同意义的双向关系使用两条 edge；复杂路由需观察并调整，不保证自动避开所有框。

独立 label 是固定位置的独立文字形状，移动节点后不会自动跟随连接线；编辑布局后必须重新检查标签。默认线上文字随连接线布局。动态胶合只解决端点跟随，不是全图排版器。

可选 fromPort / toPort：top、bottom、left、right。指定后通过 GlueToPos 胶合到对应边中点（菱形为顶点，椭圆为轴端）；未指定时使用中心动态胶合。流程图应显式指定两端的 port，并对照预览确认正交路由。

限制：单页，无图片导入或现有图无损导入；Python 有原生容器成员但不是 group 子形状，无泳道。母版通过已安装模具或显式 stencilPath 投放；不支持任意位置的手写端口（分组均分端口由规划器生成）。支持基本几何和连接线，不等同完整 Visio 功能。所有业务关系在生成前检查。
