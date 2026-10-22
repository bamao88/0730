# DocFit

状态: temp 候选稿，未替换根目录 `README.md`
更新日期: 2026-08-18

## 这个项目是什么

DocFit 是一个基于 Claude Agent SDK 的论文 Word 格式处理项目。它把学校格式要求、
学校 Word 模板和学生论文转换成可验证的 Word 产物。

当前产品分为三个并行模块：

- 模板提取：学校模板和学校要求 -> `final-template.docx` + `fill-contract.yaml`
- 用户内容提取：学生源论文 -> Student Content Model
- final word 生成：模板产物 + Student Content Model -> 最终 Word 文档

## 怎么跑

环境要求：

- Python 3.12，由 `.python-version` 固定。
- `uv`。
- OfficeCLI 1.0.143。
- Docker，用于固定的 `docfit-libreoffice-visual:25.2.3.2` 渲染器。
- Poppler 工具：`pdfinfo`、`pdftotext`、`pdftoppm`。
- 真实 Agent workflow 需要在 `~/.config/docfit/agent.env` 配置 Agent 凭据。

安装和本地环境检查：

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

主要产品入口：

```bash
uv run docfit prepare-template \
  --school-template path/to/school-template.docx \
  --school-requirements path/to/school-requirements.pdf \
  --field-registry docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml \
  --output .tmp/template-preparation

uv run docfit extract-student-content \
  --input path/to/student.docx \
  --field-registry docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml \
  --output .tmp/student-content

uv run docfit eval-student-content \
  --actual .tmp/student-content \
  --gold path/to/accepted-extraction-gold-package \
  --output .tmp/student-content-eval \
  --json
```

仍保留的辅助入口：

```bash
uv run docfit convert \
  --input evals/fixtures/smoke/student.docx \
  --school-template evals/fixtures/smoke/school-template.docx \
  --school-requirements evals/fixtures/smoke/school-requirements.pdf \
  --output .tmp/smoke-output

uv run docfit tools inspect path/to/file.docx
uv run docfit tools render path/to/file.docx
uv run docfit observe
```

`convert` 是 legacy 端到端路由。做具体模块工作时，优先进入模块文档，不用它反推模块边界。

## 当前主要入口

- 当前状态：[STATUS.md](STATUS.md)
- 系统架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- Agent 操作规则：[AGENTS.md](AGENTS.md)
- 文档路由与维护：[docs/README.md](docs/README.md)
- 三模块上下文路由：[docs/modules/README.md](docs/modules/README.md)
- 测试与 Eval 入口：[tests/README.md](tests/README.md)
