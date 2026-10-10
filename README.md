# Visio 技术方案制图 / visio-diagrams

**v0.1.0-preview.1 · 可编辑 VSDX 生成技能预览版**

把中文技术需求整理为可编辑的 Visio 图。默认 Python 直接写入 VSDX：原生形状、
基本流程母版、真正胶合的连接线，以及可复查的生成报告。适合人工组织的架构、
接口与流程图；这不是任意复杂图的全自动布局器。

**依赖区别：**生成阶段需要 Python 3 与本地基本流程 VSSX，不启动 Office；
真实打开验收和 PNG 导出需要 Windows 桌面 Visio。模具和字体不随本包分发。
现有默认模具路径是中文 Office16；其他位置使用 `--stencil`。

## 安装和使用

从 [GitHub Release](https://github.com/mewlabsx/visio-diagrams/releases/tag/v0.1.0-preview.1)
下载 `visio-diagrams-v0.1.0-preview.1.zip`，把包中的 `visio-diagrams/` 解压到
当前 Agent 的 skills 目录。例如 Codex 的用户目录是 `~/.codex/skills/`。
也可将本仓库克隆为 skills 目录中的 `visio-diagrams` 文件夹。

在 skill 目录下运行：

```powershell
python -X utf8 scripts/render_native.py assets/folded-flow-example.json C:\work\diagram.vsdx
# 模具不在默认位置时：
python -X utf8 scripts/render_native.py assets/folded-flow-example.json C:\work\diagram.vsdx --stencil C:\resources\BASFLO_M.VSSX
```

输出 `.vsdx`、`.planned.json`、`.validation.json`，拒绝覆盖旧输出。
默认不会生成 PNG；安装了 Visio 时另行验收并导出：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate-vsdx.ps1 -Vsdx C:\work\diagram.vsdx -Report C:\work\diagram.visio-validation.json -PreviewPath C:\work\diagram.png
```

COM 自动化可能阻塞，请在受限时长的外层进程中执行。旧 COM 生成后端通过
`scripts/render-visio.ps1 -Backend com` 显式选择。

## 能力与当前边界

- 支持基本矩形、菱形、开始/结束、椭圆、文字与原生连接线；固定字号，优先重排而非缩字。
- 支持显式成组排线、受限局部调整、两列折排、人工固定路线与离线几何检查。
- Python 尚不支持容器、原生成员关系、泳道或任意复杂母版；完整 UML 生成尚未验证。
- 局部规划器上限为 40 节点 / 80 连线；复杂架构可能需要人工位置和路线。
- GENERATED、离线 structure.PASS、真实 Visio 验收、视觉审查分别报告。
- 字号按输入写入；尚无最终插图宽高与有效字号的自动检查，大图不应直接缩入 A4 正文。
- 仅在本机 Visio 环境验证过所列样例，跨版本兼容与任意编辑行为仍待验证。
- Archify 集成保留为实验性入口，不包含 Archify，不计入完整通过的能力声明。

规则见 [SKILL.md](SKILL.md)，输入与后端细节见
[schema.md](references/schema.md) 和 [python-backend.md](references/python-backend.md)。

## 测试与示例

```powershell
python -X utf8 -m unittest discover -s scripts -p "test_*.py"
```

本机 55 项回归测试通过，未跳过。部分写入器测试需本地 VSSX；资源缺失时跳过，
不能把跳过描述成已验证。六类基础样例与两张复杂 Kubernetes 图已做本机 Visio
真实验收和预览检查；代表节点移动测试不覆盖所有编辑场景。

复杂图与说明在 [examples/k8s-complex](https://github.com/mewlabsx/visio-diagrams/tree/main/examples/k8s-complex)，
可编辑文件与 PNG 也单独打包为 Release 的 examples ZIP。公开样例不来自任何真实集群。

## English

This preview generates editable native VSDX with Python. It requires Python 3 and a local basic
flowchart VSSX resource, but does not start Office during generation. Windows desktop Visio is
required for native acceptance checks and PNG export. Stencils and fonts are not distributed.

It supports basic shapes, glued connectors, explicit grouped routes, bounded local layout and
authored fixed routes. It is not a general automatic diagram layout engine. Native containers,
swimlanes, arbitrary complex masters and cross-version guarantees are not implemented or accepted.
Generation, structural checks, Visio acceptance and visual review are separate evidence layers.
