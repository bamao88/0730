# DocFit Agent SDK

DocFit 是基于 Claude Agent SDK 的论文格式处理应用。当前系统由两个领域 Skill、一个
只读分析 Subagent、五个 DOCX Tool、通用 Knowledge、Eval、薄应用壳和本地可观测性组成。
Agent 负责语义判断与执行策略；确定性代码保护输入只读、快照绑定、原子发布和证据完整性。

视觉证据采用 clean-break V2 架构：固定 Docker LibreOffice 是唯一页面视觉来源，
OfficeCLI 只负责 DOCX 结构、编辑、验证和语义对象定位。DocFit 把对象锚点映射到
LibreOffice PDF，并按需生成联系表、完整页面、局部图和前后比较图。不存在 Provider
选择、自动回退、第二视觉路径或旧 `render_ref` 兼容层。视觉结果始终标记为
`approximate`，不声称与 Microsoft Word 像素一致。

架构基线从 [docs/docfit-00-index.md](docs/docfit-00-index.md) 开始；视觉 V2 的决策和
验收见
[docs/plans/docfit-libreoffice-visual-evidence-v2.md](docs/plans/docfit-libreoffice-visual-evidence-v2.md)。

## Requirements

- Python 3.12（由 `.python-version` 固定）
- [uv](https://docs.astral.sh/uv/)
- OfficeCLI 1.0.143
- Docker，以及仓库内固定的 `docfit-libreoffice-visual:25.2.3.2` 镜像
- Poppler：`pdfinfo`、`pdftotext`、`pdftoppm`
- 运行真实 Agent 时使用 Kimi Code 或 MiniMax API key

构建视觉镜像：

```bash
docker build \
  -t docfit-libreoffice-visual:25.2.3.2 \
  docker/visual-renderer
```

如默认 Debian mirror 在本地不可达，可显式传入镜像源；镜像内容版本仍由
`docker/visual-renderer/packages.lock` 固定。

## Install and verify

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check src tests
uv run mypy src
uv run pytest -q
uv run docfit doctor
uv run docfit doctor --require visual-renderer
```

`docfit doctor` 是基础确定性门。`--require visual-renderer` 额外验证锁定的 OfficeCLI、
LibreOffice 镜像身份、字体环境 digest 和 Poppler 工具；缺失时返回非零，不会换用其他
渲染器。

开发者 Tool CLI 示例：

```bash
uv run docfit tools inspect evals/fixtures/smoke/student.docx
uv run docfit tools render evals/fixtures/smoke/student.docx
uv run docfit tools visual render:v2:<hash> --mode pages --pages 1
```

`docx_render` 输入只包含 `input_docx` 和可选 `overview`；应用会话注入 `task_root`。
`docx_visual_review` 支持 `contact_sheet`、`pages`、`regions` 和 `compare`。PDF 只生成一次，
页面与局部图片按需栅格化并缓存在任务目录的 `.docfit/evidence/`。Tool 结果返回紧凑 JSON
文本块及原生 `image` 内容块；长文档通过 cursor 分批查看。

## Agent and product commands

将 Agent 凭据保存在仓库外的 `~/.config/docfit/agent.env`，权限必须为 `0600`。进程环境
变量可以覆盖文件配置。不要把 key 写入仓库、测试证据或日志。

```dotenv
DOCFIT_AGENT_BACKEND_ORDER=minimax,kimi
DOCFIT_KIMI_API_KEY=...
DOCFIT_KIMI_BASE_URL=https://api.kimi.com/coding/
DOCFIT_KIMI_MODEL=kimi-for-coding
DOCFIT_MINIMAX_API_KEY=...
DOCFIT_MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic
DOCFIT_MINIMAX_MODEL=MiniMax-M3
```

```bash
chmod 600 ~/.config/docfit/agent.env
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit agent-smoke --case path-tools
uv run docfit agent-smoke --case subagent
uv run docfit doctor --require agent-smoke
```

五个 smoke case 验证真实 MCP 图片、同会话用户提问、隐藏工具拒绝、路径权限和只读
Subagent。MiniMax-M3 是默认模型和首选 backend，Kimi 仅作回退。`.docfit/smoke/` 只保存
不含凭据与论文正文、但绑定实际 backend/model 的回执元数据。

模板准备：

```bash
uv run docfit prepare-template \
  --school-template path/to/school-template.docx \
  --school-requirements path/to/school-requirements.pdf \
  --field-registry docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml \
  --output .tmp/template-preparation-task
```

转换：

```bash
uv run docfit convert \
  --input evals/fixtures/smoke/student.docx \
  --school-template evals/fixtures/smoke/school-template.docx \
  --school-requirements evals/fixtures/smoke/school-requirements.pdf \
  --output .tmp/smoke-output
```

完成报告只引用当前最终 DOCX 的 V2 LibreOffice render、全页 Agent 视觉覆盖和独立验证；
中间渲染或旧快照不能证明最终结果。

本地观察器通过 `uv run docfit observe` 启动，只绑定 `127.0.0.1`。观察索引不保存论文
正文；SDK transcript 使用每次运行隔离目录并显式清理。历史本地证据只有在当前会话重新
授权任务目录并验证 ID/hash 后才可访问。

## Test layout

- `tests/unit`：纯本地逻辑与视觉证据核心
- `tests/contract`：公开 Tool/schema、权限与 MCP 原生图片合同
- `tests/integration`：真实 OfficeCLI、Docker LibreOffice、三校视觉链路、转换壳和本地观察器
- `evals`：离线开发与回归资产，不进入一次用户任务的在线决策环
