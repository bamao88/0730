# DocFit

DocFit 是一个 Claude Agent SDK-native 的论文格式处理项目。它把学校格式要求、
学校 Word 模板和学生论文转换为经过验证的 Word 产物，同时让语义判断留在 Agent，
让客观不变量由确定性代码保护。

当前产品分为三个并行模块：

- 模板提取：学校模板 -> `final-template.docx` +
  `fill-contract.yaml`
- 用户内容提取：学生源论文 -> Student Content Model
- final word 生成：模板产物 + 学生内容 -> 一份最终 Word

## 运行

环境要求：

- Python 3.12，由 `.python-version` 固定
- `uv`
- OfficeCLI 1.0.143
- Docker，用于固定的 `docfit-libreoffice-visual:25.2.3.2` 渲染器
- Poppler 工具：`pdfinfo`、`pdftotext`、`pdftoppm`
- 运行真实 Agent workflow 时，需要在 `~/.config/docfit/agent.env` 放置 Agent 凭据

安装与验证：

```bash
uv sync --frozen
docker build -t docfit-libreoffice-visual:25.2.3.2 docker/visual-renderer
uv run docfit doctor
uv run docfit doctor --require visual-renderer
```

基础开发检查：

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

生成测试和 Eval 分开：只验证文档生成时，只准备输入并运行产品 CLI；Actual-vs-Gold 评分才进入
`evals/**`。具体入口见 [tests/README.md](tests/README.md)。

主要命令：

```bash
uv run docfit prepare-template \
  --school-template path/to/school-template.docx \
  --output .tmp/template-preparation-task

uv run docfit extract-student-content \
  --input path/to/student.docx \
  --field-registry docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml \
  --output .tmp/student-extraction

uv run docfit eval-student-content \
  --actual .tmp/student-extraction \
  --gold path/to/accepted-extraction-gold-package \
  --output .tmp/student-extraction/eval \
  --json

uv run docfit student-content-e2e --list-cases

uv run docfit generate-final \
  --source path/to/student.docx \
  --student-content path/to/student-content.json \
  --template path/to/final-template.docx \
  --fill-contract path/to/fill-contract.yaml \
  --field-registry path/to/content-fields.yaml \
  --output .tmp/final-generation

uv run docfit convert \
  --input evals/fixtures/smoke/student.docx \
  --school-template evals/fixtures/smoke/school-template.docx \
  --school-requirements evals/fixtures/smoke/school-requirements.pdf \
  --output .tmp/smoke-output
```

`convert` 是 legacy 端到端 Agent 路由。做某个模块的工作时，先使用下面的模块上下文路由，
再判断产品就绪状态。

常用本地工具：

```bash
uv run docfit tools inspect evals/fixtures/smoke/student.docx
uv run docfit tools render evals/fixtures/smoke/student.docx
uv run docfit observe
```

## 当前入口

- 当前状态：[STATUS.md](STATUS.md)
- 系统架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- AI 操作规则：[AGENTS.md](AGENTS.md)
- 按模块加载上下文：
  [docs/modules/README.md](docs/modules/README.md)
- 文档入口与维护规则：
  [docs/README.md](docs/README.md)
- 详细文档索引：[docs/docfit-00-index.md](docs/docfit-00-index.md)
- 测试与 Eval 入口：
  [tests/README.md](tests/README.md)
- 模板提取 Contract：
  [docs/contracts/template-extraction.md](docs/contracts/template-extraction.md)
- 模板提取边界：
  [docs/modules/template-extraction.md](docs/modules/template-extraction.md)
- 计划文档是任务证据，不是项目真相：
  [docs/plans/README.md](docs/plans/README.md)
- human 讨论文档是背景材料，不是默认 Agent 上下文：
  [docs/human/README.md](docs/human/README.md)
