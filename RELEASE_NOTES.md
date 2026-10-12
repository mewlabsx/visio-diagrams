# v0.2.0-dev.2 — 开发预览

补充图型契约、自由/矩阵/重复结构判断、模板—实例分层规划、关键需求澄清和最小范围局部让步；区分业务事实与布局偏好。本次规则修订完成16组作者场景走查；它本身未修改渲染/布局算法。本版同时包含此前0.2开发阶段新增的原生容器与有界排线，71项回归通过；时序、泳道、矩阵共享外框和联合布局仍不是已实现能力。

# 当前开发版 v0.2.0-dev — 2026-10-12（尚未发布）

新增显式原生嵌套容器、递归成员边界、标题避障、矩形共享端口、平行候选通道与最多四种线序重排。71 项本机测试通过；真实移动跟随与路线保存见 references/containers-routing.md。复杂压力图仍有交叉，不保证全图最优或交互自动重排。

# v0.1.0-preview.1 — 2026-10-10

首个公开预览版：以 Python 直写 VSDX 为默认生成后端，旧 COM 生成显式选择。

- 保留原生基本流程母版及连接线，写入规划路线和真正胶合的端点。
- 处理实例几何、文本框、连接点缓存与分数端口，修复字体/字号写入和标签偏移。
- 提供离线生成报告、独立 Visio 验收与 PNG 导出；拒绝覆盖输出。
- 分发 skill 说明、脚本、55 项回归测试与通用 JSON 样例。
- 另附 Kubernetes 架构与 Deployment 创建 Pod 的复杂图示例，包含 8 个异常判断。

验收范围：本机 55 项回归测试无跳过；六类基础样例和两张复杂图通过 Visio
路线/字号/文字与代表节点移动验收，预览已查看。复杂流程的 8 个判断包含清单、
API、Pod 准入、调度、卷/网络、镜像、容器运行与就绪问题。

边界：仍需本地 VSSX；PNG 与真实验收仍需 Visio。未实现原生容器成员关系、
泳道、任意复杂母版与最终插图尺寸可读性检查。复杂架构含人工布局与路线，
本版不声明全图自动优化、所有编辑行为或跨版本兼容。Archify 为实验性入口。

## English

First public preview with Python-based native VSDX generation, glued connectors, explicit
route preservation, structural receipts, optional Visio acceptance and PNG export.
The local regression suite passed 55 tests without skips. Native containers, swimlanes,
general automatic layout, final-placement readability and cross-version compatibility
remain outside the accepted scope. A local stencil resource is still required.
