# Template Extraction Eval

这是一个与 DocFit 产品代码、依赖和 CLI 物理解耦的只读静态评测工程。它只承接已经生成
的 Actual 模板与 Actual 填写契约，和 case 绑定的 Gold 模板、Gold 填写契约做确定性对比；
不关心模板由哪个 Agent、模型或提取流程生成。

## 评测目标与输出

评测分为两个各 50 分的业务视角：

- `protected`：内容 20、结构位置 10、有效样式 15、结构化对象 5；
- `slot`：槽集合 15、位置与边界 15、字段映射 10、槽值样式契约 10。

Gold 明确声明的 remove 残留作为共享硬失败检查。最终同时输出 `PASS`、`FAIL` 或
`UNKNOWN` 门禁结论、总分、双视角分数、八个分项、分析覆盖率和可定位 issue。分数不覆盖
硬失败；输入/schema/hash/Gold 状态错误不生成伪质量分数。

默认输出目录为 `.runs/<run-id>/<case-id>/`：

```text
template-extraction-eval-report.json   # 机器真源；通过 report schema
template-extraction-eval-report.md     # 从同一 report model 派生的人工摘要
```

## 独立工程边界

运行时只依赖 Python 标准库的 ZIP/XML 读取、`PyYAML` 和 `jsonschema`。本目录拥有独立
`pyproject.toml`、`uv.lock`、包、测试和输出目录；不 import `docfit`，不启动产品 CLI，
也不依赖 Claude SDK、Adobe、OfficeCLI、Word GUI、网络或产品缓存。

核心脚本与能力责任如下：

| 脚本/模块 | 责任 |
|---|---|
| `run_eval.py` | 唯一评分 CLI；解析四个运行参数并调用独立 runner |
| `template_extraction_eval/contracts.py` | 校验 case、Gold 状态、schema、hash、Registry 和模板—契约闭包 |
| `template_extraction_eval/facts/` | Actual/Gold 共用的 DOCX 内容、结构、有效样式和对象事实分析 |
| `template_extraction_eval/evaluators/` | protected、slot 与 Gold 声明的 remove 业务断言 |
| `template_extraction_eval/scoring.py` | 双视角、八分项、slot F1、覆盖率和硬失败结论 |
| `template_extraction_eval/reporting.py` | 原子发布同源 JSON/Markdown 报告 |
| `fixtures/build_samples.py` | 只生成 S00–S13 合成样本，不生成正式 Gold |
| `materialize_candidate_cases.py` | 只准备三校 candidate；拒绝覆盖 accepted case，不参与评分运行 |

## 运行

```bash
cd evals/template-extraction
uv sync --frozen
uv run python run_eval.py \
  --case fixtures/S00-minimal-pass/case.yaml \
  --actual-template fixtures/S00-minimal-pass/actual-template.docx \
  --actual-contract fixtures/S00-minimal-pass/actual-contract.yaml \
  --output-dir .runs/manual/s00
```

退出码：`PASS=0`，`FAIL/UNKNOWN=2`，`INPUT_ERROR=3`。质量状态以 JSON 报告为准；
`INPUT_ERROR` 只向 stderr 输出结构化诊断且不发布报告。

验证独立工程：

```bash
uv lock --check
uv build
uv run ruff check .
uv run mypy --strict template_extraction_eval run_eval.py \
  fixtures/build_samples.py materialize_candidate_cases.py
uv run pytest -q
```

## 三校 Gold 状态

`cases/01-hunau-undergraduate`、`02-njau-undergraduate` 和 `03-pku-graduate` 已按最终
case 目录物化，但三者仍是 `candidate / candidate_pending_human_acceptance`。运行时会以
`GOLD_NOT_ACCEPTED` 拒绝评分，不计入 Gold 通过率。只有字段语义、必填性、槽样式、
protected/remove Truth、validation finding、数据权限和 reviewer 记录全部完成人工确认后，
才能原地改为 accepted 并启用每校三条正式评分回归。
