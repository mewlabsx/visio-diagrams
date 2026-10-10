# Archify 自动布局适配（实验性）

需要已安装 Archify、Node.js、Python 3 和可用的 PowerShell。历史 COM 路线还需桌面 Visio；Python 生成需 VSSX，真实验收与 PNG 导出仍需 Visio。历史验证版本为 Archify 2.17.0-dev.1；它是外部依赖，不包含在包中。本预览版没有重新验收完整 Archify 集成，保留为实验性入口。

输入采用 Archify workflow schema v2，使用逻辑 lane、col、关系及 route 偏好，而非逐个手写坐标。读已安装 Archify 的 SKILL.md 和 workflow schema 后制作输入。使用 assets/archify-workflow.json 作为字段示例。

```powershell
pwsh -NoProfile -File scripts/render-archify-visio.ps1 -SpecPath assets/archify-workflow.json -OutputPath C:\work\auto-layout.vsdx
```

默认从用户目录 .agents/skills/archify 寻找依赖，其他位置使用 -ArchifyRoot。入口依次取得 --layout-json 回执、检查 showcase 质量、独立核对全部导入线路，再调用原生 Visio 生成器。已有目标不覆盖。布局或验收失败保留诊断 JSON，不生成 Visio；不能把未生成或陈旧文件当成通过结果。

输出 .layout.json、.archify-validation.json、.native.json、.vsdx 和 .validation.json；默认 Python 后端不自动导出 PNG。显式 -Backend com 使用旧 COM 生成路线。比例为 72 个几何单位对应 1 英寸；原始页顶坐标转换为 Visio 坐标，连接端点按实际边上位置胶合。节点使用 Process 母版；lane 仅用标题保留，不是原生泳道。语义明确的判断图形、UML、复杂母版尚未映射。

支持矩形工作流节点及纯文本关系标签。存在 groups、phases、cards 或节点 sublabel/tag/brand 时拒绝适配，避免静默丢失内容；其他丰富表达需另行扩展。仍需视觉检查标签、字体与最终插图尺寸。

独立检查覆盖源/结果节点和线路 ID、关系方向、正交性、非端点节点穿越、任意导入线路间正长度共线重叠、标签缺失和端点落边。保存后原生生成器检查母版、文字、胶合数量和所有显式路由顶点。没有数学最优性或复杂回路可行性保证，也未自动搜索重叠修复。

实测发现：原始八节点九线回路示例的 Archify showcase 报告通过，但严格共线检查发现重叠；几次修订未收敛，保留为失败证据。最终独立八节点七线分支示例，在两条主线上加入 straight 路由偏好后，自动求解节点坐标与其他路径，独立检查和 Visio 保存验证通过。不能把这一结果描述为原复杂回路已经解决或完全自动排线。

下一步优先做基于明确诊断的有限修复与回归样例集，而不是直接扩大支持声明。当前职责是自动布局器＋严格适配验收，失败需调整逻辑结构或路线偏好。
