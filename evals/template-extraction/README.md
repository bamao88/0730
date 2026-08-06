# Template Extraction Eval

这是一个与 DocFit 产品代码、依赖和 CLI 物理解耦的只读静态评测工程。它只承接已经生成
的 Actual 模板与 Actual 填写契约，和 case 绑定的 Gold 模板、Gold 填写契约做确定性对比；
不关心模板由哪个 Agent、模型或提取流程生成。

## 评测目标与输出

评测分为两个各 50 分的业务视角：

- `protected`：内容 20、结构位置 10、有效样式 15、结构化对象 5；
- `slot`：槽集合 15、位置与边界 15、字段映射 10、槽值样式契约 10。

Gold 明确声明的 remove 残留作为共享硬失败检查。最终同时输出 `PASS`、`FAIL` 或
`UNKNOWN` 门禁结论、总分、双视角分数、八个分项、文档责任覆盖率、分析覆盖率和可定位
issue。分数不覆盖硬失败；输入/schema/hash/Gold 状态错误不生成伪质量分数。

评分语义遵守以下可靠性约束：

- 没有断言的维度得 0 分并使结果成为 provisional/`UNKNOWN`，不能空断言满分；
- 显式且真实的 `NOT_APPLICABLE` 可以获得该维度分数，但缺失槽的下游维度属于 FAIL；
- `responsibility_coverage` 衡量全文事实是否全部归入 protected / slot / remove；必须为 100%；
- `analysis_coverage` 按八个维度权重计算，未生成断言和 UNKNOWN 都会降低该覆盖率；
- protected 不再由少量 anchor 抽样声明，而是自动取“全部语义文档事实减去 slot/remove”的补集；
- accepted Gold 必须绑定 `semantic_document_facts/v1` 全量责任策略并具有非空 slot Truth。

全量责任面以共享分析器输出的事实为边界：每个段落的文字、结构坐标和受保护 Run 有效样式，
每个表格结构、结构化对象、关系和 DOCX part 都进入分母；块级槽内事实归 slot，行内槽内容被
统一遮罩后再比较两侧固定内容。分析器识别但不能解释的对象仍完成责任归类，但断言必须输出
`UNKNOWN`，不能用“已归类”冒充“已正确分析”。

默认输出目录为 `.runs/<run-id>/<case-id>/`：

```text
template-extraction-eval-report.json   # 机器真源；通过 report schema
template-extraction-eval-report.md     # 从同一 report model 派生的人工摘要
```

## 独立工程边界

运行时只依赖 Python 标准库的 ZIP/XML 读取、`PyYAML` 和 `jsonschema`。本目录拥有独立
`pyproject.toml`、`uv.lock`、包、测试和输出目录；不 import `docfit`，不启动产品 CLI，
也不依赖 Claude SDK、Adobe、OfficeCLI、Word GUI、网络或产品缓存。

```text
evals/template-extraction/
├── run_eval.py                         # 正式 accepted-Gold 评分入口
├── run_raw_source_sentinel.py          # 原始模板作为 Actual 的诊断哨兵
├── config/                             # 评分权重和 Eval 容差
├── schemas/                            # case、契约、Registry consumer、报告合同
├── cases/                              # 三校 candidate Gold；不属于产品运行目录
├── fixtures/                           # S00–S13 合成回归样本
├── template_extraction_eval/           # 独立 Eval Python 包
│   ├── facts/                          # 共享 DOCX/OOXML 事实分析
│   ├── evaluators/                     # protected、slot、remove 断言
│   ├── contracts.py                    # 输入和 Gold 资格门禁
│   ├── markers.py                      # 主槽、组件、连续区域的标记闭包
│   ├── responsibility.py               # 全文事实责任归类与 protected 补集比较
│   ├── scoring.py                      # 双视角评分和覆盖率
│   └── sentinel.py                     # diagnostic-only 哨兵编排
├── tests/                              # contract、unit、integration 测试
└── .runs/                              # 被忽略的本地报告，不进入正式 Gold
```

核心脚本与能力责任如下：

| 脚本/模块 | 责任 |
|---|---|
| `run_eval.py` | 唯一评分 CLI；解析四个运行参数并调用独立 runner |
| `run_raw_source_sentinel.py` | diagnostic-only 三校哨兵；不会绕过或修改 Gold 接受状态 |
| `template_extraction_eval/contracts.py` | 校验 case、Gold 状态、schema、hash、Registry 和模板—契约闭包 |
| `template_extraction_eval/facts/` | Actual/Gold 共用的 DOCX 内容、结构、有效样式和对象事实分析 |
| `template_extraction_eval/markers.py` | 校验主槽、组件槽、连续区域和 DOCX 标记的双向闭包 |
| `template_extraction_eval/responsibility.py` | 枚举全文事实、完成 protected/slot/remove 归类并比较全部 protected 原子 |
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

运行原始学校模板哨兵：

```bash
uv run python run_raw_source_sentinel.py \
  --output-dir .runs/raw-source-sentinel-v3
```

该命令明确标记 `diagnostic_only=true`，并使用两套互不污染的事实基线：protected 层以原始
模板自身作为保留真值，slot 层以 Gold 提取模板与填写契约作为提取真值。最新全量结果为：

| 学校 | protected 全量事实 | protected | slot 失败断言 | slot |
|---|---:|---|---:|---|
| 湖南农业大学 | 2301 | `50/50 + PASS` | 96 | `0/50 + FAIL` |
| 南京农业大学 | 1227 | `50/50 + PASS` | 128 | `0/50 + FAIL` |
| 北京大学 | 4367 | `50/50 + PASS` | 112 | `0/50 + FAIL` |

三校的责任覆盖率和分析覆盖率均为 100%。此前湖南农大基于三个 anchor 得出的 `35/50` 已
撤销：那只能证明三个样本中的页边距差异，不能代表全文保留质量，也不再进入正式口径。

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
