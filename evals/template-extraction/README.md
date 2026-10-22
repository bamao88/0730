# 模板提取 Eval

本文应该回答：

- 已生成的模板提取 Actual 产物如何与 accepted Gold 做离线评分；
- Gold/candidate 准备、评分配置、schema、报告和 evaluator 自身回归如何组织；
- 为什么本目录不能作为 `prepare-template` 生成测试的 expected output 来源；
- 哪些内容属于最终 Actual-vs-Gold Eval，哪些阶段 replay 应该去单独文档查看。

本 README 只用于离线 Actual—Gold 评分、Gold/candidate 准备和 evaluator 自身回归。
如果任务只是测试 `docfit prepare-template` 能否从输入生成文档，先读
`../../tests/README.md`，不要在本目录寻找 expected output 或 Gold 样例。
如果任务是模板提取的中间阶段 replay，例如只验证 unit-boundary checkpoint，读
[stage-replay.md](stage-replay.md)，不要把 Gold 注入 Agent runtime。

这是一个与 DocFit 产品代码、依赖和 CLI 物理解耦的只读静态评测工程。它只承接已经生成
的 Actual 模板与 Actual 填写契约，和 case 绑定的 Gold 模板、Gold 填写契约做确定性对比；
不关心模板由哪个 Agent、模型或提取流程生成。

早期正文模板生成计划已从当前计划入口移除；本 Eval 不依赖该计划，只读取已生成 Actual
与 accepted Gold 做独立评分。

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

本阶段只承接 Actual 与 clean Gold，不把 Gold 的上游生成或验收状态混入质量评分。protected
责任面以 clean Gold 中 slot/remove 的补集为真值；每一个 Gold protected 事实都必须产生一条
PASS/FAIL/UNKNOWN 断言。段落先通过单调内容与容器证据对齐，再比较文字、逻辑结构、有效样式
与对象，因此 Actual 前面多出待删除说明时，不会把后续全文按绝对段落序号误判为错位。

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
├── README.md                           # Eval 模块说明：运行方式、Gold 状态、目录约定
├── pyproject.toml                      # Eval 自己的 Python 项目配置
├── uv.lock                             # Eval 独立依赖锁文件，不改变产品依赖
├── run_eval.py                         # 正式评分入口：Actual 模板/契约 vs accepted Gold
├── run_raw_source_sentinel.py          # 原始学校模板诊断哨兵，不算正式评分
├── materialize_candidate_cases.py      # 候选 case 物化脚本；拒绝覆盖 accepted Gold
├── prepare_v05_gold_pairs.py           # v0.5 Gold pair 准备脚本
│
├── config/                             # 评分配置
│   ├── eval-config-v1.yaml             # Eval 运行配置
│   └── scoring-v1.yaml                 # 双视角和分项权重配置
│
├── schemas/                            # 输入/输出合同 schema
│   ├── case.schema.json                # case.yaml 的 schema
│   ├── eval-config.schema.json         # eval 配置 schema
│   ├── field-catalog.schema.json       # 字段目录 schema
│   ├── fill-contract.schema.json       # fill-contract.gold.yaml 的 schema
│   └── report.schema.json              # 评分报告 schema
│
├── cases/                              # 三校正式 accepted Gold case
│   ├── 01-hunau-undergraduate/         # 湖南农大本科模板提取 Gold
│   │   ├── case.yaml                   # case 元数据、Gold hash、accepted 状态和权限
│   │   ├── candidate-package-receipt.json # 候选准备/物化收据
│   │   ├── gold/                       # 正式评分 Truth；评分只认这里
│   │   │   ├── final-template.gold.docx # 正式 Gold Word，含 Word 原生批注
│   │   │   └── fill-contract.gold.yaml # 正式 Gold 填写契约
│   │   └── review/accepted-2026-08-17/ # 人工批准留档，不作为第三份评分 Truth
│   │       ├── reviewed-final-template.gold.docx # 批准时查看的批注版 Word 快照
│   │       └── approval-record.yaml    # 快照与 Gold pair 的 hash 对应记录
│   │
│   ├── 02-njau-undergraduate/          # 南京农大本科模板提取 Gold；结构同上
│   └── 03-pku-graduate/                # 北京大学研究生模板提取 Gold；结构同上
│
├── candidate-sources/                  # 候选来源材料；不是正式评分 Truth
│   ├── v0.5.yaml                       # v0.5 候选来源清单
│   └── v0.5/                           # 三校候选源材料
│
├── fixtures/                           # S00-S13 合成测试样本，不是真实学校 Gold
│   ├── build_samples.py                # 合成 fixture 生成器
│   ├── field-registry.yaml             # 合成样本字段目录
│   ├── manifest.yaml                   # 合成样本清单
│   ├── S00-minimal-pass/               # 最小 PASS 样本
│   ├── ...
│   └── S13-simple-formula-field-bookmark/ # 公式/域/书签覆盖样本
│
├── template_extraction_eval/           # Eval 核心运行代码
│   ├── facts/                          # 共享 DOCX/OOXML 事实分析
│   ├── evaluators/                     # protected、slot、remove 断言
│   ├── aligned_protected.py            # Gold 全量 protected 事实对齐与逐原子断言
│   ├── alignment.py                    # Actual 与 Gold 稳定对齐
│   ├── contracts.py                    # case、contract、hash、accepted 状态校验
│   ├── markers.py                      # 主槽、组件、连续区域的标记闭包
│   ├── models.py                       # Eval 数据模型
│   ├── reporting.py                    # JSON/Markdown 报告输出
│   ├── responsibility.py               # 全文事实责任归类与 protected 补集比较
│   ├── runner.py                       # Eval 编排入口
│   ├── scoring.py                      # 双视角评分和覆盖率
│   └── sentinel.py                     # diagnostic-only 哨兵编排
│
├── template_extraction_prep/           # Gold/candidate 准备辅助代码
│   ├── candidate_package.py            # 候选包生成/校验
│   ├── docx_package.py                 # DOCX 包处理
│   ├── normalizers.py                  # 准备阶段归一化工具
│   ├── sources.py                      # 来源读取
│   └── writers.py                      # 输出写入
│
└── tests/                              # Eval 自己的测试
    ├── contract/                       # 输入合同、CLI、Gold gate 测试
    ├── integration/                    # 集成链路测试
    └── unit/                           # 单元测试
        ├── evaluators/                 # evaluator 单元测试
        └── facts/                      # facts 分析器单元测试
```

本地生成目录不属于正式 Eval 结构：`.runs/`、`.venv/`、`.pytest_cache/`、`.ruff_cache/`、
`__pycache__/`、`.DS_Store` 和 Word 打开文件时生成的 `~$*.docx` 临时锁文件。

核心脚本与能力责任如下：

| 脚本/模块 | 责任 |
|---|---|
| `run_eval.py` | 唯一评分 CLI；解析四个运行参数并调用独立 runner |
| `run_raw_source_sentinel.py` | diagnostic-only 三校哨兵；不会绕过或修改 Gold 接受状态 |
| `template_extraction_eval/contracts.py` | 校验 case、Gold 状态、schema、hash、Registry 和模板—契约闭包 |
| `template_extraction_eval/facts/` | Actual/Gold 共用的 DOCX 内容、结构、有效样式和对象事实分析 |
| `template_extraction_eval/markers.py` | 校验主槽、组件槽、连续区域和 DOCX 标记的双向闭包 |
| `template_extraction_eval/responsibility.py` | 枚举全文事实、完成 protected/slot/remove 归类并比较全部 protected 原子 |
| `template_extraction_eval/aligned_protected.py` | 以 clean Gold 为参考，完成段落单调对齐，并为每一个 protected 原子生成断言 |
| `template_extraction_eval/evaluators/` | protected、slot 与 Gold 声明的 remove 业务断言 |
| `template_extraction_eval/scoring.py` | 双视角、八分项、slot F1、覆盖率和硬失败结论 |
| `template_extraction_eval/reporting.py` | 原子发布同源 JSON/Markdown 报告 |
| `fixtures/build_samples.py` | 只生成 S00–S13 合成样本，不生成正式 Gold |
| `materialize_candidate_cases.py` | 只准备候选数据包；拒绝覆盖 accepted case，不参与正式评分运行 |

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
  --output-dir .runs/source-clean-audit-v2
```

该命令明确标记 `diagnostic_only=true`，把原始学校 DOCX 当作 Actual，直接对比 clean Gold
模板和填写契约。它不是自比较，也不抽取少量 anchor；Gold 的全部 protected 原子和全部 slot
都会进入断言集合：

| 学校 | Gold protected 原子 | 责任覆盖 | protected P/F/U | protected 得分 | slot FAIL | 总分 |
|---|---:|---:|---:|---:|---:|---:|
| 湖南农业大学 | 1692 | 100% | 1598 / 85 / 9 | 46.9088 / 50 | 124 | 46.9088 |
| 南京农业大学 | 659 | 100% | 417 / 230 / 12 | 34.4072 / 50 | 128 | 34.4072 |
| 北京大学 | 486 | 100% | 468 / 9 / 9 | 48.2307 / 50 | 112 | 48.2307 |

三校结论均为 `FAIL`，槽层符合哨兵预期：Gold 的每个槽均产生 inventory、位置边界、字段映射
和槽值样式四条失败断言。湖南农大 Gold 已把上下页边距恢复为原模板的 56.7pt，并将原先单一
`body.chapters` 聚合槽拆成一级/二级/三级标题、对应正文和结论共 8 个结构化正文槽；保留层
剩余差异集中在模板清理造成的文本/结构差异、少量直接样式差异和对象差异。31 个填写槽均
使用 `w:showingPlcHdr`，占位文字统一显示为灰色；灰色仅属于占位 UI，不属于填充后的槽值
样式契约。中文摘要和关键词后的隐藏 `TC` 域是原模板目录收集机制，不是填写槽，继续作为
protected 对象保留。南农存在字号、
行距、颜色、结构和书签语义无法完全证明等问题；北大主体接近，但仍有页眉内容、段落间距/
颜色和书签语义问题。UNKNOWN 不会冒充 PASS，当前三校分析覆盖率均高于 99%。

此前“原始模板与自身比较”得到的三校 protected `50/50` 已撤销；自比较只能验证程序可运行，
不能验证 clean Gold 的真实性或完整性。

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
case 目录冻结为正式 accepted Gold。每校核心 Truth 只保留
`gold/final-template.gold.docx + gold/fill-contract.gold.yaml`，并由 `case.yaml`、hash、
reviewer 和数据权限记录绑定。

2026-08-18 已在三个原始 Word Gold 文件中用 Word 原生批注补齐全覆盖 Review：
HUNAU 227 条、NJAU 96 条、PKU 159 条。批注分为对象级批注和覆盖批注：对象级批注覆盖
字段槽、处理区域、逻辑页和已接受样式缺口；覆盖批注覆盖正文所有可见内容块，并用总览批注
说明页眉/页脚内容的保留策略。批注包含字段、处理动作、样式和人工确认结论。三校自比较均为
`PASS / 100.0`。

每校在 `review/accepted-2026-08-17/` 保留批注版 Word 快照
`reviewed-final-template.gold.docx` 和 `approval-record.yaml`。2026-08-18 已按人工反馈补齐
全覆盖批注，当前记录为 `coverage_completed_pending_manual_recheck`。该目录只用于追溯批注版
Word 与当前 Gold pair 的 hash 对应关系；评分 Truth 仍只来自 `gold/` 下两份核心文件。

当前测试阶段以准确度为 Gold 核心：来源是否官方只记录，不参与资格或评分。每校产品结果是
`final-template.docx + fill-contract.yaml` 两份原子绑定的主文件；在 Eval 内分别物化为
`gold/final-template.gold.docx + gold/fill-contract.gold.yaml`。`case.yaml`、Registry、reviewer 与报告属于数据集
元数据/验收证据，不是第三份产品交付物。
