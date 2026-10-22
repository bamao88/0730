# 用户内容提取 Gold 与 Eval

本目录保存用户内容提取的 Gold 物化脚本、受限本地 case inventory 和稳定 Eval 入口说明。
真实学生源、Gold JSON、产品核对文档和图片证据继续保存在受限本地目录，不进入公开 CI、
仓库日志或 Agent prompt。

## Current Scope

- Module: `user-content-extraction`
- Contract: `docs/contracts/user-content-extraction.md`
- Case inventory: `evals/student-content-extraction/case-inventory.yaml`
- Stable E2E CLI: `docfit student-content-e2e`
- Stable Eval CLI: `docfit eval-student-content`

Student Content Extraction Eval 只比较“已完成提取任务目录”与“已接受 Extraction Gold”。Gold 是
oracle-only 输入，必须在 Agent 提取结束后离线读取；它不能作为提取 prompt、恢复输入或运行时
纠错来源。

## Case Inventory

`case-inventory.yaml` 是当前受限本地回归清单，不是公开 CI fixture：

- `student-002`：Gold r5，当前 required restricted gate，质量和性能已接受。
- `student-001` / `student-003`：Gold r2 已接受，当前为 trend-only，等待 live quality closure。

这些 case 行只保存路径、Registry、Gold revision、预期和 gate 语义，不保存学生正文。

## Gold Materialization

```bash
uv run python evals/student-content-extraction/materialize_student_001_003_gold.py
uv run python evals/student-content-extraction/materialize_student_001_003_gold.py --check
uv run ruff check evals/student-content-extraction/materialize_student_001_003_gold.py
```

`materialize_student_002_gold.py` 重放 Student 002 accepted Gold r5，并固定绑定 Registry v0.3。
`materialize_student_001_003_gold.py` 物化 Student 001/003 accepted Gold r2，并固定绑定
Registry v0.4。三个 Gold 均使用 `docfit-student-content-extraction-gold/v2`；`items[]` 按
`docfit-source-order/v1` 排列，`field_results` 只是派生字段索引。

## Run E2E

固定端到端入口按 case inventory 读取 source、Registry 和 Gold 路径。这个入口是给 AI
调用的机器契约：stdout/stderr 都是 JSON，`--json` 只为兼容保留，不需要依赖人读文本。

AI 调用顺序固定为：先发现 case，再预检输入包，再运行提取；需要质量 gate 时显式打开
评测。产物判断优先看最终 `student-content.json`。

发现可用 case：

```bash
uv run docfit student-content-e2e --list-cases
```

只校验输入包，不跑模型：

```bash
uv run docfit student-content-e2e \
  --case student-002 \
  --validate-inputs-only
```

运行真实提取，不追加 Gold 评测：

```bash
uv run docfit student-content-e2e \
  --case student-002 \
  --output temp/student-002-actual-live
```

如需在同一命令中追加离线 Gold 评测，显式打开评测：

```bash
uv run docfit student-content-e2e \
  --case student-002 \
  --output temp/student-002-actual-live \
  --eval on
```

`--eval off|on` 是选择项；`--eval on` 时 CLI 会先检查 Gold 包存在，再在提取完成后读取
Actual 目录中的最终 `student-content.json`、inventory 和 Agent evidence。`run-report.json`
只作为内部诊断路径返回，不作为产品质量判断入口。

E2E JSON summary 的稳定字段包括：

- `schema_version: docfit-student-content-e2e-cli/v1`
- `status`: `INPUT_PACKAGE_OK` / `READY` / `PASS` / `FAIL` / `INPUT_ERROR`
- `input_package.paths`: inventory、source、Registry、Gold 路径
- `input_package.checks`: source、Registry、Gold 是否存在
- `extraction.student_content`: 最终 Student Content JSON 路径
- `eval.mode`: `off` 或 `on`
- `eval.json_report`: 仅在 `--eval on` 时存在

## Run Eval Directly

先运行真实提取，生成 Actual 任务目录：

```bash
uv run docfit extract-student-content \
  --input temp/manual-gold-preparation/student-content-real-student-002.docx \
  --field-registry docs/plans/docfit-content-field-registry/content-fields-v0.3.yaml \
  --output temp/student-002-actual-live
```

再离线比较 Accepted Gold：

```bash
uv run docfit eval-student-content \
  --actual temp/student-002-actual-live \
  --gold temp/manual-gold-preparation/gold/20-student-assets/student-002 \
  --output temp/student-002-actual-live/eval \
  --json
```

Eval 自动读取 Actual 目录中的：

- `student-content.json`
- `work/student-inventory.json`
- `work/agent-evidence.json`

稳定输出：

- `student-content-eval-report.json`
- `student-content-eval-report.md`

## Verdict And Privacy

报告维度：

- provenance
- source coverage
- Registry field semantics
- value fidelity
- semantic grouping
- content order
- hierarchy/relations
- live Agent evidence

`PASS` 返回 `0`；质量 `FAIL` 或输入错误返回 `2`。报告只保存 hash、计数、`field_id`、源对象
ID、source locator 对齐结果和 session 元数据，不复制学生正文或字段值。Gold-local object ID 与
当前 runtime inventory ID 不一致时，runner 只在源 hash 一致且 locator crosswalk 明确时对齐；
crosswalk 不完整或有歧义时 fail closed。
