# 模板提取静态 E2E Eval 顶层设计

## Eval 项目文件目录

> 注：下面是模板提取静态 Eval 实施完成后的目标项目目录，只展开本模块直接相关的
> 文件。`[现有]` 表示仓库中已经存在且继续保留，`[扩展]` 表示修改现有文件，`[新增]`
> 表示本模块需要创建，`[生成]` 表示运行产物且不进入源代码，`[临时]` 表示当前设计
> 阶段使用、正式接入 case 时需要迁移或固定的输入。

```text
docfit_agent_SDK/
├── src/docfit/                                          # [现有][不修改] 产品代码；不得导入或承载本 Eval
│   └── ...                                              # 产品只产生模板与填写契约，不调用质量评测器
│
├── evals/
│   ├── README.md                                        # [扩展] 登记 template-extraction suite 的运行方式和边界
│   ├── fixtures/                                        # [现有] core suite 的通用/风险 fixture，保持独立
│   ├── e2e/                                             # [现有] 当前 synthetic-core case，保持独立
│   │
│   └── template-extraction/                             # [新增] 模板提取 Eval 的版本化数据资产
│       ├── README.md                                    # [新增] case 制作、运行、Gold 审核和更新规则
│       ├── pyproject.toml                               # [新增] Eval 独立依赖、测试和静态检查配置
│       ├── uv.lock                                      # [新增] Eval 独立锁文件，不改变产品依赖
│       ├── run_eval.py                                  # [新增] 独立命令入口；不导入 docfit 产品包
│       │
│       ├── template_extraction_eval/                    # [新增] Eval 自有运行代码，与 src/docfit 物理解耦
│       │   ├── __init__.py                              # [新增] Eval 包公共入口
│       │   ├── models.py                                # [新增] 事实、定位器、断言、issue、分数和结论模型
│       │   ├── contracts.py                             # [新增] case、契约、Registry 和配置加载校验
│       │   ├── alignment.py                             # [新增] Actual—Gold 稳定对齐
│       │   ├── scoring.py                               # [新增] 权重、F1、覆盖率和硬失败结论
│       │   ├── reporting.py                             # [新增] JSON/Markdown 同源报告
│       │   ├── runner.py                                # [新增] 只读串联预检、分析、断言与输出
│       │   ├── facts/
│       │   │   ├── __init__.py                          # [新增] Eval 自有统一文档事实入口
│       │   │   ├── reader.py                            # [新增] 独立读取 DOCX parts、story、关系和 OOXML
│       │   │   ├── content.py                           # [新增] 文字、空白、槽标记和非文本内容
│       │   │   ├── structure.py                         # [新增] 节、段落、Run、表格、单元格和范围
│       │   │   ├── effective_style.py                   # [新增] Eval 自有有效样式解析
│       │   │   └── objects.py                           # [新增] 图片、公式、域、书签和合并事实
│       │   └── evaluators/
│       │       ├── __init__.py                          # [新增] 三类评测器入口
│       │       ├── protected.py                         # [新增] protected 四个分项
│       │       ├── slots.py                             # [新增] slot 四个分项
│       │       └── forbidden_residue.py                 # [新增] remove 禁止残留断言
│       │
│       ├── schemas/
│       │   ├── case.schema.json                         # [新增] case manifest 的结构约束
│       │   ├── fill-contract.schema.json                # [新增] protected/slot/remove、字段、定位和样式契约
│       │   ├── field-catalog.schema.json                # [新增] Registry 快照的消费侧结构校验
│       │   ├── eval-config.schema.json                  # [新增] 标记协议、容差和评分版本约束
│       │   └── report.schema.json                       # [新增] JSON 评分报告的机器契约
│       │
│       ├── config/
│       │   └── scoring-v1.yaml                          # [新增] 固定 100 分权重、容差和硬失败规则
│       │
│       ├── fixtures/
│       │   ├── build_samples.py                         # [新增] 只生成 S00–S13 小型合成样本
│       │   ├── manifest.yaml                            # [新增] 样本用途、预期和 hash
│       │   └── S00-*/ ... S13-*/                       # [新增] 单变量正反例，不含真实学校内容
│       │
│       ├── cases/
│       │   ├── 01-hunau-undergraduate/
│       │   │   ├── case.yaml                            # [新增] Gold、字段、配置、标记协议和 case 元数据
│       │   │   └── gold/
│       │   │       ├── template.docx                    # [新增] 人工确认的湖南农业大学 Gold 模板
│       │   │       └── fill-contract.yaml               # [新增] 对应 Gold 填写契约
│       │   ├── 02-njau-undergraduate/
│       │   │   ├── case.yaml                            # [新增] 南京农业大学本科 case manifest
│       │   │   └── gold/
│       │   │       ├── template.docx                    # [新增] 人工确认的 Gold 模板
│       │   │       └── fill-contract.yaml               # [新增] 对应 Gold 填写契约
│       │   └── 03-pku-graduate/
│       │       ├── case.yaml                            # [新增] 北京大学研究生 case manifest
│       │       └── gold/
│       │           ├── template.docx                    # [新增] 人工确认的 Gold 模板
│       │           └── fill-contract.yaml               # [新增] 对应 Gold 填写契约
│
│       ├── tests/                                       # [新增] Eval 自有测试，不进入产品 tests 目录
│       │   ├── unit/
│       │   │   ├── test_public_api.py                   # [新增] Eval 包导出与无产品 import
│       │   │   ├── test_models.py                       # [新增] status、fact、issue、score 和 report
│       │   │   ├── test_contracts.py                    # [新增] schema、Registry 和模板—契约一致性
│       │   │   ├── test_alignment.py                    # [新增] ID、定位器、锚点和 AMBIGUOUS
│       │   │   ├── test_scoring.py                      # [新增] 权重、F1、覆盖率和硬失败
│       │   │   ├── test_reporting.py                    # [新增] JSON/Markdown 同源和稳定排序
│       │   │   ├── test_runner.py                       # [新增] PASS、FAIL、UNKNOWN 和输入失败
│       │   │   ├── test_sample_builder.py               # [新增] 样本完整、确定性和 schema 有效
│       │   │   ├── facts/
│       │   │   │   ├── test_reader.py                   # [新增] parts、story、关系和坏包
│       │   │   │   ├── test_content.py                  # [新增] 文本、空白、槽标记和非文本 token
│       │   │   │   ├── test_structure.py                # [新增] 段落、Run、表格、单元格和文本框
│       │   │   │   ├── test_effective_style.py          # [新增] 默认值、继承、直接格式和单位
│       │   │   │   └── test_objects.py                  # [新增] 图片、公式、域、书签和合并关系
│       │   │   └── evaluators/
│       │   │       ├── test_protected.py                # [新增] protected 四个分项
│       │   │       ├── test_slots.py                    # [新增] slot 集合、位置、字段和样式
│       │   │       └── test_forbidden_residue.py        # [新增] remove 明确命中与不推断
│       │   ├── contract/
│       │   │   └── test_eval_contract.py                # [新增] 独立 CLI、输入、输出和 report schema
│       │   └── integration/
│       │       └── test_run_eval.py                     # [新增] 最小 Actual—Gold 全链路
│       │
│       └── .runs/<run-id>/<case-id>/                    # [生成] Eval 私有运行输出，保持 gitignore
│           ├── template-extraction-eval-report.json     # [生成] 评分与门禁机器真源
│           └── template-extraction-eval-report.md       # [生成] 人工审查摘要
│
├── temp/manual-gold-preparation/eval-template-truth-candidates/
│   ├── build_candidates.py                              # [临时] 候选资产生成器，不进入评测运行路径
│   ├── 01-hunau-undergraduate/                          # [临时] 湖南农业大学候选模板和契约
│   ├── 02-njau-undergraduate/                           # [临时] 南京农业大学本科候选模板和契约
│   └── 03-pku-graduate/                                 # [临时] 北京大学研究生候选模板和契约
│
├── docs/plans/docfit-content-field-registry/
│   ├── DESIGN.md                                        # [现有] 跨阶段字段语义、版本和未知字段权威
│   └── content-fields-v0.1.yaml                         # [现有] 研发期固定 Registry 快照
│
└── docs/plans/docfit-template-extraction-eval/
    ├── DESIGN.md                                        # [现有] 顶层目标、比较和评分合同
    └── PLAN.md                                          # [现有] 实施顺序、逐代码测试和完成门
```

目录和依赖边界固定为：所有新 Eval 代码、schema、配置、fixture、Gold case、测试和运行
报告都位于 `evals/template-extraction/`；`src/docfit/**` 不为本模块新增代码、入口或 import。
产品与 Eval 只通过模板、填写契约、Registry ID/version/hash 和报告 schema 交换数据，
双方不得互相导入 Python 包或调用内部函数。Eval 使用自己的 `pyproject.toml` 和 `uv.lock`，
不能把 Eval-only 依赖加入产品依赖。字段语义由独立的研发期 Content Field
Registry 负责；Eval 只固定引用，不拥有或重写字段目录。Temp 目录只作为当前人工准备
来源，正式接入后不能继续成为 Eval 的隐式依赖。

最新用户决定进一步区分“最终目录位置”和“Gold 验收状态”：三校可以先按最终
`cases/<case-id>/gold/` 结构物化，但只要 `case_status/gold_review/fill-contract.status`
仍为 candidate，比较器就必须把该 case 作为输入失败，不得计入 Gold 通过率。路径名本身
不是 Human acceptance 证据；从 candidate 改为 accepted 仍必须满足 PLAN 的 Human
readiness、hash 和验证门。Temp 只作为显式、hash 绑定的准备来源，不进入 Eval 运行路径。

这项隔离有意允许 Eval 拥有自己的只读 OOXML 事实分析实现。它会增加少量重复代码，
但避免产品解析器和质量裁判共享同一实现缺陷，从而使 Actual—Gold 结论具备独立性。

隔离不是目录命名约定，而是以下可测试的工程合同：

| 边界 | 产品侧 | Eval 侧 | 强制约束 |
|---|---|---|---|
| 源码 | `src/docfit/**` | `evals/template-extraction/template_extraction_eval/**` | 新模块不修改产品源码 |
| Python 包 | `docfit` | `template_extraction_eval` | 双方不得相互 import |
| 依赖 | 根 `pyproject.toml` / `uv.lock` | Eval 自有 `pyproject.toml` / `uv.lock` | Eval-only 依赖不得进入产品依赖图 |
| 入口 | 产品 `docfit` CLI | `evals/template-extraction/run_eval.py` | 不新增产品子命令，也不从 Eval 启动产品 CLI |
| 测试 | 根 `tests/**` | `evals/template-extraction/tests/**` | Eval 测试可在未安装产品包时独立运行 |
| 产物 | 产品任务工作/输出目录 | `evals/template-extraction/.runs/**` | 不共用缓存、运行状态或默认输出目录 |
| 发布 | 产品 wheel / runtime image | 独立 Eval 环境或 CI job | 任一发布产物不得捎带另一方 Python 包 |
| 数据交互 | 生成模板与填写契约 | 只读消费 Actual、Gold、Registry 快照并发布报告 | 只通过版本化文件/schema/hash 交互，无内部 API 或共享内存状态 |

因此 Eval 可以在只拿到四份核心输入文件和版本化配置的环境中运行；删除产品源码、关闭
Agent 或不安装产品 wheel，都不应改变同一组输入的评分结果。

> 状态：当前任务的顶层设计基线；W0/G1 与三校 candidate case 目录已物化，评分实现尚未完成
> 本文负责：定义评测目标、输入输出、比较维度、评分口径、能力依赖和现有代码覆盖情况
> 本文不负责：定义模板如何生成、Gold 如何生产，或安排具体代码实施步骤

## 1. 目标

本阶段只承接已经生成的模板和填写契约，并将它们与对应 Gold 做静态对比和评分。

它不关心上一个阶段采用了什么提取流程、调用了什么模型，也不依据上一个阶段的运行状态判断结果。只要给定一组可读取的实际产物和 Gold，本阶段就应独立、确定性地回答：

1. 原始模板中应保留的内容、结构、样式和结构化对象，在生成模板中是否仍然正确。
2. 应提取的填写槽是否完整，槽位位置和边界是否正确。
3. 每个填写槽对应的字段是否正确。
4. 每个槽未来填入值时应采用的样式契约是否正确。
5. 哪些差异导致失败，差异发生在哪里，评分如何计算。

最终目标不是只给出一个总分，而是同时产出：

- 可作为质量门禁的明确结论：`PASS`、`FAIL` 或 `UNKNOWN`；
- 原始模板保留视角与填写槽视角各自的分数；
- 每个评测维度的分数、通过数、失败数和不可判定数；
- 可以定位到具体区域、槽位和属性的差异证据。

## 2. 本阶段要做的事情

评测器必须完成下面五件事：

1. 分别读取实际模板、实际填写契约、Gold 模板和 Gold 填写契约。
2. 把实际产物与 Gold 归一化为同一种文档事实模型。
3. 使用同一套内容、结构、定位、有效样式和结构化对象分析能力，生成可比较事实。
4. 从“原始模板保留”和“填写槽”两个业务视角分别执行断言。
5. 计算分项分数与总分，并生成机器可读和人工可读报告。

评测器不得修改任何输入文件，也不得调用模板提取流程重新生成实际产物。

## 3. 输入与最终输出

### 3.1 必需输入

每个 Eval case 至少包含四个核心输入：

| 输入 | 含义 | 评测中的角色 |
|---|---|---|
| 实际模板 | 被测模板提取流程生成的干净模板 | Actual |
| 实际填写契约 | 被测流程生成的槽、字段和槽值样式声明 | Actual |
| Gold 模板 | 人工确认正确的目标模板 | Expected |
| Gold 填写契约 | 人工确认正确的槽、字段、定位、区域责任和槽值样式声明 | Expected |

以下输入按 case 或数据集配置提供：

| 输入 | 是否必需 | 用途 |
|---|---:|---|
| 字段标准 / 字段目录 | 当填写契约引用字段 ID 时必需 | 验证字段是否存在、类型是否允许 |
| 槽标记协议 | 必需 | 声明槽在 DOCX 中使用的特殊标记类型及其标识规则 |
| Eval 配置 | 必需 | 声明 schema 版本、容差、忽略项和评分版本 |

v1 固定引用
`docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml`
（`docfit.thesis.content_fields@0.1.0`）作为研发期字段对齐基线。case 与报告必须记录
Registry ID、版本和文件 hash；以后升级 Registry 时要显式更新 case，不能在同一 case
或评分版本下静默改名或改变字段语义。Registry 是跨阶段语义合同，Eval 只是消费者；
它不会因此成为产品 Knowledge 或 Eval Gold。

#### 3.1.1 DOCX 内容控件槽标记协议

v1 内容控件使用两个正交身份，不能把字段 ID 和物理槽位 ID 合并为一个值：

| OOXML 属性 | 责任 | v1 约束 |
|---|---|---|
| `w:sdtPr/w:alias/@w:val` | 字段语义身份 | 必须精确等于 Registry 中的 canonical `field_id` |
| `w:sdtPr/w:tag/@w:val` | 物理槽位或区域定位身份 | 在绑定的 DOCX 快照内唯一，并与填写契约 locator 一一对应 |
| `w:sdtPr/w:id/@w:val` | Word 内部内容控件标识 | 不承担业务语义，不参与 Actual—Gold 字段或槽位匹配 |

同一字段允许出现在封面、摘要、正文等多个物理位置，因此多个控件可以共享同一个
`w:alias`；复合槽也可以由多个共享 `w:alias` 的组件控件组成。上述控件必须分别拥有
唯一 `w:tag`，并由填写契约通过 `slot_id`、主 locator 和 `component_locators` 声明其逻辑
归属。评测器不得因为 alias 重复而合并槽，也不得要求 `w:tag == field_id`。

输入预检必须双向验证：模板每个受管控件的 `w:tag` 都能解析到契约槽或区域，契约每个
自动 locator 都能在模板中精确匹配一次；同时模板 `w:alias`、契约 `field_id` 与 Registry
字段 ID 三者必须完全一致。任一断链、未知字段或 alias/field 不一致均为输入硬失败，
不得进入正式评分。

当前阶段不要求把“提取前原始学校模板”作为运行时输入。Gold 已经声明正确的保留区域、槽区域、预期结构和预期样式；评测器比较的是 Actual 与 Gold，而不是复盘模板生成过程。

### 3.2 输出

每个 case 必须输出：

```text
<output-dir>/
├── template-extraction-eval-report.json
└── template-extraction-eval-report.md
```

未显式指定 `--output-dir` 时，独立入口写入
`evals/template-extraction/.runs/<run-id>/<case-id>/`；该目录属于 Eval 私有运行产物并保持
gitignore，不进入产品 `.docfit/` 运行目录。

`template-extraction-eval-report.json` 是评分、门禁和聚合统计的唯一机器真源，至少包含：

- 输入文件身份、哈希和 schema 版本；
- 总体结论和总分；
- 分视角、分维度得分；
- 分析覆盖率；
- 断言统计；
- 结构化差异列表；
- 使用的容差和评分规则版本；
- 不支持或不可判定的事实。

`template-extraction-eval-report.md` 是由同一份结果派生的人工审查报告，至少包含：

- 结论和分数摘要；
- 两个业务视角的结果；
- 按严重程度排序的差异；
- 每个差异的 Gold 区域 ID、实际位置、预期值和实际值；
- `UNKNOWN` 的原因及缺失能力。

默认报告不得复制完整文档正文。内容差异应优先使用区域 ID、稳定定位器、摘要哈希和必要的短锚点表达。

## 4. 顶层评测模型

整体评测结构固定为：一个共享事实分析层，两套上层业务断言。

```text
模板提取静态 E2E Eval
├── 一、共享事实分析层
│   ├── 内容分析
│   │   ├── 文字、标点、空格、换行
│   │   └── 图片、公式、域等内容
│   │
│   ├── 结构与定位分析
│   │   ├── 段落、Run、表格、行、单元格
│   │   ├── 页眉页脚、节、文本框
│   │   ├── 前后固定锚点
│   │   └── 稳定结构定位器
│   │
│   ├── 有效样式分析
│   │   ├── 字符样式
│   │   │   └── 中英文字体、字号、粗体、颜色等
│   │   ├── 段落样式
│   │   │   └── 对齐、缩进、行距、段前段后等
│   │   ├── 容器样式
│   │   │   └── 单元格边距、边框、底纹、垂直对齐等
│   │   └── 页面样式
│   │       └── 页边距、纸张、分节、页眉页脚等
│   │
│   ├── 结构化对象分析
│   │   ├── 图片关系
│   │   ├── 公式语义
│   │   ├── 域和书签
│   │   └── 表格合并关系
│   │
│   └── 区域责任标注
│       ├── protected：原始模板保留区
│       ├── slot：填写槽区域
│       └── remove：明确不应出现在最终模板中的说明或示例
│
├── 二、原始模板保留视角
│   ├── 内容是否保留
│   ├── 结构和位置是否保留
│   ├── 有效样式是否保留
│   └── 结构化对象功能是否保留
│
└── 三、填写槽视角
    ├── 槽位是否完整、准确
    ├── 槽位位置和边界是否正确
    ├── 槽位对应字段是否正确
    └── 槽值的预期样式是否正确
```

共享能力与两个上层视角的关系如下：

| 共享底层能力 | 原始模板保留视角 | 填写槽视角 |
|---|---|---|
| 内容分析 | Gold 固定文字和对象在 Actual 中有没有被修改 | Gold 要求的特殊槽标记在 Actual 中是否存在且正确 |
| 结构与定位分析 | Gold 固定内容在 Actual 中是否仍处于对应结构位置 | Actual 槽是否位于 Gold 指定的段落、Run、单元格或对象内部 |
| 有效样式分析 | Gold 受保护区域与 Actual 对应区域的有效样式是否一致 | Actual 槽值样式契约是否等于 Gold 声明 |
| 对象分析 | 图片、公式、域、书签和表格关系是否完整 | 槽是否正确位于域、表格或复合对象内部 |
| 区域责任标注 | 哪些 Gold 范围在 Actual 中禁止被修改 | 哪些范围允许由槽标记占据，以及槽边界在哪里 |

底层事实定义只能有一套。两套上层评测器可以选择不同事实做断言，但不得分别实现字体、结构、定位或对象解析逻辑。

## 5. 共享事实分析层

### 5.1 内容事实

内容分析必须区分并保留以下事实：

- Unicode 文字；
- 全角、半角标点；
- 普通空格、不换行空格、制表符；
- 显式换行和段落边界；
- 图片、公式、域、书签等非纯文本内容；
- 槽标记及其标识。

归一化不得把本来应该比较的差异抹掉。比如连续空格、中文冒号与英文冒号、段内换行与新段落默认都不是等价的。只有 Eval 配置明确声明的差异才可以忽略。

### 5.2 结构与定位事实

统一结构模型至少要覆盖：

- story：正文、页眉、页脚、脚注等；
- section；
- paragraph 和 run；
- table、row、cell 及合并关系；
- text box 或其他可承载文字的对象；
- 段内字符范围；
- 左右固定锚点；
- 同一锚点多次出现时的 occurrence。

一个稳定定位器可表示为：

```yaml
locator:
  story: document
  section_index: 0
  table_index: 0
  row: 2
  cell: 1
  paragraph_index: 0
  left_anchor: "姓名："
  occurrence: 1
```

结构索引不能单独作为长期稳定身份。评测匹配应综合使用区域 ID、结构路径、前后锚点、内容摘要和邻近对象；若仍存在多个同等候选，必须报告 `AMBIGUOUS`，不得任意选择一个位置继续评分。

### 5.3 有效样式事实

样式比较的对象是“有效样式”，不是只比较 run 或段落 XML 上显式写出的属性。分析器必须计算文档默认值、命名样式、继承关系、直接格式以及容器影响后的最终值。

两边输出同一种事实结构，例如：

```yaml
effective_style:
  font:
    east_asia: 宋体
    latin: Times New Roman
    size_pt: 12
    bold: false
    italic: false
    color: "000000"

  paragraph:
    alignment: center
    first_line_indent_pt: 0
    left_indent_pt: 0
    right_indent_pt: 0
    line_spacing_rule: fixed
    line_spacing_pt: 20
    space_before_pt: 0
    space_after_pt: 0

  container:
    vertical_alignment: center
    cell_margin_left_pt: 5.4
    borders: {}
    shading: null

  page:
    page_width_pt: 595.3
    page_height_pt: 841.9
    margin_top_pt: 72
    margin_bottom_pt: 72
```

统一分析器由两个上层评测器使用：

```text
EffectiveStyleAnalyzer
├── ProtectedStyleEvaluator
│   └── actual_effective_style == gold_effective_style
└── SlotStyleEvaluator
    └── actual_expected_value_style == gold_expected_value_style
```

单位换算、默认值解析、继承计算、缺失值语义和数值容差必须由共享层统一处理。

### 5.4 结构化对象事实

至少要能比较：

- 图片内容身份、关系目标、尺寸、锚定方式和所在位置；
- OMML 公式的语义 XML，而不是仅比较渲染截图；
- 域代码、域结果及其范围；
- 书签名称、范围和引用关系；
- 表格横向、纵向合并关系；
- 槽标记位于结构化对象内部时的包含关系。

当前静态评测不以页面截图或视觉相似度代替这些结构事实。渲染比较以后可以作为补充证据，但不能成为本阶段的唯一判据。

### 5.5 区域责任事实

区域必须细到段内文本范围或对象范围，不能只把整个段落标为某一种责任。例如：

```text
姓名：张三
```

其 Gold 责任可以是：

```yaml
regions:
  - region_id: student_name_label
    owner: protected
    text: "姓名："

  - region_id: student_name_slot
    owner: slot
    slot_id: cover_student_name
    field_id: student.name
```

这样才能判断固定标签是否被误删、槽边界是否错误地包含冒号，以及未来填写是否会覆盖固定文字。

三种责任的语义固定为：

- `protected`：Actual 必须保留 Gold 声明的内容、结构、有效样式和对象功能。
- `slot`：Actual 必须在 Gold 声明的边界内放置正确槽标记，并由实际填写契约声明正确字段和槽值样式。
- `remove`：Gold 声明的禁留内容或模式不得出现在 Actual 中。

由于当前阶段不读取提取前原始模板，`remove` 只能验证 Gold 已明确声明的“禁止残留断言”，不能推断未在 Gold 中声明的内容是否原本应该删除。禁止残留一旦命中就是硬失败，但不另设第三个业务视角。

## 6. 原始模板保留视角

这里的“原始模板保留”是业务语义：Gold 模板中的 `protected` 区域代表必须保留的模板事实。运行时实际比较为：

```text
Gold 模板 / Gold 契约中的 protected 事实
                    VS
Actual 模板中的对应事实
```

### 6.1 内容保留

逐个 Gold `protected` 区域判断：

- 文字、标点、空格和换行是否一致；
- 非文本内容是否存在；
- 是否出现新增、删除、替换或顺序变化；
- `remove` 禁止残留是否误出现在 Actual 中。

评分单位是 Gold 区域断言，不按字符数量加权。某个受保护区域内任一必须内容不一致，该区域的内容断言即失败，报告再展开具体差异。

### 6.2 结构和位置保留

逐个 Gold `protected` 区域或对象判断：

- story 和 section 是否对应；
- 段落、表格、行、单元格及文本框归属是否一致；
- 相对前后锚点是否一致；
- 表格内位置和合并关系是否一致；
- 是否发生跨容器移动、拆分或错误合并。

纯粹因 DOCX 保存造成、且不改变语义的 run 拆分不得自动判失败；共享分析层应把多个等价 run 归一化到可比较的文本范围。但如果 run 边界承载了不同有效样式、域边界或对象关系，则必须保留并比较。

### 6.3 有效样式保留

比较：

```text
Gold protected 区域的有效样式
                 VS
Actual 对应区域的有效样式
```

至少覆盖字符、段落、容器和页面四层。每个样式属性都要输出 `PASS`、`FAIL`、`UNKNOWN` 或 `NOT_APPLICABLE`，不能只输出一个模糊的“样式不同”。

### 6.4 结构化对象功能保留

对每个 Gold 受保护对象判断：

- 对象是否仍存在且可解析；
- 关系是否仍可达；
- 内容或语义身份是否一致；
- 尺寸、锚定和结构位置是否一致；
- 公式、域、书签和表格合并关系是否仍有效。

只有对象二进制存在但关系断裂，不能算作保留成功。

## 7. 填写槽视角

填写槽评测同时使用模板与填写契约：模板提供槽标记和物理位置，填写契约提供槽身份、字段映射、定位声明和槽值样式契约。

### 7.1 槽位完整、准确

建立 Gold 槽集合与 Actual 槽集合后计算：

- `TP`：Gold 与 Actual 中一一匹配的槽；
- `FN`：Gold 要求但 Actual 缺失的槽；
- `FP`：Actual 多出的槽；
- `Duplicate`：一个槽 ID 在不允许重复的位置出现多次；
- `Broken`：模板中有标记但契约无定义，或契约有定义但模板无标记。

指标为：

```text
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 * precision * recall / (precision + recall)
```

“完整、准确”分项使用 F1 计分，但任何必需槽缺失、多余槽、非法重复或模板—契约断链都会让 case 结论为 `FAIL`。

### 7.2 槽位位置和边界

对每个匹配槽判断：

- story、section 和容器是否正确；
- 段落、表格、行、单元格、文本框等结构位置是否正确；
- 左右固定锚点和 occurrence 是否正确；
- 槽边界是否精确；
- 槽标记是否错误吞入 `protected` 内容；
- 一个 Gold 槽是否被错误拆成多个 Actual 槽，或多个槽是否被合并。

位置相同但边界错误不能通过；边界正确但放在错误单元格也不能通过。报告必须分别给出 `location_match` 和 `boundary_match`。

### 7.3 槽位对应字段

对每个匹配槽比较：

```text
Actual contract.field_id == Gold contract.field_id
```

并使用字段标准验证：

- 字段 ID 是否存在；
- 模板内容控件 `w:alias` 是否精确等于契约 `field_id`；
- 字段类型是否与槽允许的值类型一致；
- 重复使用是否符合 Gold 声明；
- 别名是否经过 schema 明确允许，而不是评测器自行猜测。

槽标记正确但字段映射错误，属于独立失败，不能被位置分掩盖。

### 7.4 槽值样式契约

当前比较的是：

```text
Gold 声明的 expected_value_style
                    VS
Actual 填写契约和槽标记携带的 expected_value_style
```

这里评测的是“未来填入内容应该采用什么样式”的静态契约，不是已经执行填写后的视觉效果。因此本维度名称固定为“槽值样式契约”。

实际契约与模板槽标记都声明样式时，两者内部也必须一致；任一方缺失必需样式属性、两者冲突，或与 Gold 不一致，都要单独报告。

## 8. 对齐与比较规则

Actual 与 Gold 的匹配顺序固定为：

1. 使用 schema 内稳定的 `region_id` 或 `slot_id` 建立首选对应关系。
2. 校验该 ID 在模板标记与填写契约之间是否一一对应。
3. 使用结构路径、固定锚点、occurrence 和邻近对象验证位置。
4. 在位置确定后比较文本范围、有效样式和对象事实。
5. ID 缺失时，只允许使用 Gold 明确声明的备用定位器匹配。
6. 出现多个同等候选时返回 `AMBIGUOUS`，不得按“最接近”静默通过。

这套匹配只用于对齐事实，不能把本应失败的移动、边界变化或字段变化归一化掉。

## 9. 评分与结论

### 9.1 两个结果层次

报告同时提供“质量结论”和“诊断分数”：

- 质量结论用于门禁，遵循必需断言，不允许高分掩盖关键错误。
- 诊断分数用于比较版本、学校和错误分布。

结论规则固定为：

| 条件 | 结论 |
|---|---|
| 任一必需断言明确失败 | `FAIL` |
| 无明确失败，但任一必需断言因能力或数据不足不可判定 | `UNKNOWN` |
| 所有必需断言均通过 | `PASS` |

`UNKNOWN` 不是通过，也不能进入通过率分子。

### 9.2 v1 分值结构

总分为 100 分，两个业务视角各 50 分：

| 业务视角 | 分项 | 权重 |
|---|---|---:|
| 原始模板保留 | 内容保留 | 20 |
| 原始模板保留 | 结构和位置保留 | 10 |
| 原始模板保留 | 有效样式保留 | 15 |
| 原始模板保留 | 结构化对象功能保留 | 5 |
| 填写槽 | 槽位完整、准确 | 15 |
| 填写槽 | 槽位位置和边界 | 15 |
| 填写槽 | 字段映射 | 10 |
| 填写槽 | 槽值样式契约 | 10 |
| **合计** |  | **100** |

v1 权重是数据集级固定规则，不能由单个 case 临时改写。以后调整权重必须升级 `scoring_version`，避免不同版本分数被错误比较。

### 9.3 分项计算

除槽位完整、准确使用 F1 外，其他分项按 Gold 断言单位计算：

```text
dimension_ratio = passed_assertions / comparable_assertions
dimension_score = dimension_weight * dimension_ratio
```

规则如下：

- 一个区域很长不会因此比另一个区域权重更高；默认每个 Gold 区域或对象断言权重相同。
- 样式分项以 Gold 声明的必需样式属性断言为单位。
- Gold 明确声明“不存在该类对象”且分析器能够确认时，该断言算通过。
- `NOT_APPLICABLE` 不进入分母。
- `UNKNOWN` 不伪装成失败或通过；分数标记为 `provisional`，同时单独报告分析覆盖率。
- 存在必需 `UNKNOWN` 时，即使可比较部分得到 100 分，质量结论仍为 `UNKNOWN`。

分析覆盖率计算为：

```text
analysis_coverage = observed_required_assertions / all_required_assertions
```

### 9.4 硬失败

至少以下情况是硬失败：

- Actual 模板不可读取或不是有效 DOCX 包；
- Actual 填写契约不可解析或不符合 schema；
- 模板槽标记与实际填写契约不能一一对应；
- 任一 Gold 必需 `protected` 内容或对象缺失、被修改或失效；
- 任一 Gold 必需槽缺失，或 Actual 存在多余槽；
- 槽越界覆盖 `protected` 内容；
- 槽字段映射错误或引用不存在的字段；
- 命中 Gold 声明的 `remove` 禁止残留；
- 定位结果明确落在错误 story、段落、单元格或对象中。

高总分不能覆盖这些失败。比如只缺一个必需槽时，诊断分数可能仍然较高，但 case 结论必须是 `FAIL`。

## 10. 报告中的差异模型

每个差异至少包含：

```yaml
issue_id: ISS-0001
severity: error
view: slot
dimension: field_mapping
assertion_id: slot.cover_student_name.field_id
region_id: student_name_slot
slot_id: cover_student_name
gold_locator: {}
actual_locator: {}
expected: student.name
actual: student.number
status: FAIL
message: 槽位存在且位置正确，但映射到了错误字段
```

`dimension` 至少允许：

```text
protected.content
protected.structure
protected.style
protected.object
slot.inventory
slot.location
slot.boundary
slot.field_mapping
slot.value_style
shared.forbidden_residue
shared.input_integrity
shared.analysis_coverage
```

报告不得只给出“文档不一致”或“样式错误”这种无法行动的结论。

## 11. 需要定义的评测入口与 runner

本模块使用 Eval 目录内的独立入口，不扩展产品 `docfit` CLI：

```bash
uv run --project evals/template-extraction \
  python evals/template-extraction/run_eval.py \
  --case <case.yaml> \
  --actual-template <actual.docx> \
  --actual-contract <actual-contract.yaml> \
  --output-dir <output-dir>
```

`case.yaml` 负责版本化引用 Gold 模板、Gold 填写契约、字段标准、槽标记协议、Eval
配置和 scoring version；Actual 模板与 Actual 填写契约由本次被测运行显式传入。
`run_eval.py` 只解析参数并调用同目录 `template_extraction_eval/runner.py`，所有评测逻辑
只在 Eval 包内部实现。入口和包都不得 import `docfit`。

runner 必须具备以下能力：

1. **输入预检**：文件存在性、DOCX 包完整性、契约 schema、字段 schema、哈希记录。
2. **模板事实提取**：从 Actual 与 Gold 提取统一内容、结构、定位、有效样式和结构化对象事实。
3. **契约归一化**：读取区域责任、槽 ID、字段 ID、定位器、标记协议和槽值样式。
4. **模板—契约一致性检查**：分别检查 Actual 内部和 Gold 内部的模板标记与契约是否一一对应。
5. **事实对齐**：按稳定 ID、结构定位器和锚点建立 Actual—Gold 映射，并显式处理歧义。
6. **两视角断言**：执行原始模板保留评测器和填写槽评测器。
7. **评分与门禁**：按固定评分版本计算分项、视角和总分，独立计算 `PASS/FAIL/UNKNOWN`。
8. **差异报告**：生成 JSON 真源和 Markdown 摘要。
9. **确定性**：同样的输入、配置和工具版本必须得到同样的事实、分数和 issue 顺序。
10. **显式降级**：遇到暂不支持的 DOCX 特性时报告 `UNKNOWN` 和能力缺口，不得跳过后判为通过。

用户可见入口只有这一条独立 CLI 路径。内部拆成事实分析器、定位器、比较器和报告器
模块，但不要求用户手工依次运行多个脚本，也不在产品 CLI 中提供镜像入口。

该 runner 明确不做：

- 调用模板提取 Agent；
- 生成或修复 Actual 模板；
- 自动生成 Gold；
- 执行正式填写；
- 修改 Actual 或 Gold；
- 使用模型主观判断替代确定性断言。

## 12. 所依赖的工具与能力

这里的“工具”指评测脚本需要调用的确定性能力，不等同于必须新增公共 MCP Tool。

| 能力 | 必要性 | 需要提供的事实 | 实现边界 |
|---|---:|---|---|
| DOCX 包校验器 | 必需 | ZIP、Content Types、主文档和关系完整性 | Eval 自有只读实现 |
| OOXML 文档事实读取器 | 必需 | story、段落、run、表格、文本框、对象和关系 | Eval 自有只读实现 |
| 填写契约 / 字段 schema 读取器 | 必需 | 区域、槽、字段、定位器、样式声明 | Eval 包内部 |
| StructuralLocator | 必需 | 稳定 ID、结构路径、锚点、occurrence、边界 | Eval 包内部 |
| EffectiveStyleAnalyzer | 必需 | 字符、段落、容器和页面有效样式 | Eval 自有实现 |
| StructuredObjectAnalyzer | 必需 | 图片、公式、域、书签、合并关系 | Eval 自有实现 |
| ProtectedEvaluator | 必需 | 四类 protected 断言 | Eval 包内部 |
| SlotEvaluator | 必需 | 槽集合、位置边界、字段和样式断言 | Eval 包内部 |
| Scorer | 必需 | 分项分数、总分、覆盖率和门禁结论 | Eval 包内部 |
| ReportWriter | 必需 | 稳定 JSON 和 Markdown 报告 | Eval 包内部 |

v1 直接读取 OOXML，不把 OfficeCLI 或 `src/docfit` 中的 package/inspection/ooxml/adapter
作为运行依赖。Eval 可以使用 Python 标准库和通用第三方库，也可以在独立实验中拿
OfficeCLI 结果做旁证，但正式 verdict 只来自本 Eval 的版本化事实模型。这样会牺牲一部分
代码复用，换取质量裁判与被测产品的实现独立性。

本阶段不依赖：

- Microsoft Word GUI 或 AppleScript；
- Adobe DOCX-to-PDF；
- 页面渲染或截图视觉比较；
- LLM 语义评审；
- 模板提取 Agent 的运行日志。

这些以后可以补充行为或视觉证据，但不能成为静态评测 v1 的前置条件。

## 13. 当前代码现状审计

结论：仓库已经完成独立环境、schema、评分配置、S00–S13 合成 fixture 和三校 candidate
case 数据包的第一批合同资产，但尚没有符合本文完整定义的模板提取静态 E2E 评分器。

| 能力 / 代码 | 当前状态 | 当前能做什么 | 与本文目标的差距 |
|---|---|---|---|
| `src/docfit/tools/package.py` | 已有产品代码，本模块不导入 | DOCX 包和内容类型基础校验 | 共享实现会降低 Eval 独立性；只允许对照行为，不形成代码依赖 |
| `src/docfit/tools/inspection.py` | 已有产品代码，本模块不导入 | OfficeCLI 基础 inspect | 既不覆盖完整事实，也不能作为被测产品与裁判的共享实现 |
| `src/docfit/tools/ooxml.py` | 已有产品代码，本模块不导入 | 产品编辑/复制所需 OOXML 原语 | 本 Eval 建立自己的只读事实模型，不从产品模块调用 |
| `src/docfit/adapters/officecli.py` | 已有产品代码，本模块不导入 | OfficeCLI 进程与结果适配 | 不属于独立 Eval 运行依赖 |
| `src/docfit/evals/runner.py` | 已有旧 core Eval | 运行当前 core conversion 确定性检查 | 不被新模块导入；是否迁出产品代码属于独立切换决策 |
| `evals/template-extraction/schemas/**`、`config/**`、`fixtures/**` | W0/G1 已实现 | 独立 schema、100 分配置和 S00–S13 确定性合成数据 | 只证明能力合同与样本，不证明评分器或学校 Gold 正确性 |
| `evals/template-extraction/materialize_candidate_cases.py` | 已实现 | 把三校 Temp 候选显式投影到最终 case 目录，绑定 Registry/template/contract hash 并校验 `alias/tag/field_id` 闭包 | 只生成 `candidate_pending_human_acceptance`，拒绝覆盖 accepted case，不执行 Gold 晋升 |
| `evals/template-extraction/cases/01-*`、`02-*`、`03-*` | candidate 数据包已物化 | 提供 `case.yaml + gold/template.docx + gold/fill-contract.yaml` 的稳定目录和字段槽合同 | `expected_verdict: INPUT_ERROR`；尚缺 Human signoff、完整 protected/remove Truth 和两校 validation 裁决 |
| `temp/manual-gold-preparation/eval-template-truth-candidates/build_candidates.py` | 候选资产生成器 | 构建候选模板、填写契约，并包含局部 `effective_style` 读取逻辑 | 它生成产物，不对 Actual—Gold 做完整比较或评分；局部逻辑尚不是共享评测能力 |
| Content Field Registry v0.1、候选 `template-spec.yaml` 和三校模板资产 | 已有研发基线/样本 | Registry 提供固定字段语义；候选模板资产支持 Gold 契约和 case 设计 | Registry 不等于 Gold；候选资产不能代替经确认的 Gold schema 和 Eval case manifest |
| StructuralLocator | 缺失 | — | 需要新增统一稳定定位能力 |
| 完整 EffectiveStyleAnalyzer | 缺失 | — | 现有局部逻辑需评估后再决定复用或重构 |
| StructuredObjectAnalyzer | 缺失 | — | 需要覆盖图片、公式、域、书签和合并关系 |
| ProtectedEvaluator | 缺失 | — | 需要新增 |
| SlotEvaluator | 缺失 | — | 需要新增 |
| 本文评分器与报告器 | 缺失 | — | 需要新增固定 schema、权重和结论规则 |
| `evals/template-extraction/run_eval.py` 与 `template_extraction_eval/runner.py` | 缺失 | — | 需要新增完全位于 Eval 目录的独立入口和 runner |

因此，不能把现有候选物化脚本、候选 case 或旧 Eval runner 描述为“已经支持模板提取
E2E 评分”。
新模块只复用开放的数据格式、Registry 快照和通用第三方依赖，不复用 `src/docfit` 的
Python 实现。现有旧 core Eval 的目录迁移不夹带进本模块实施。

## 14. 本阶段明确不评测的内容

以下内容属于后续填写运行时行为测试，不进入当前静态 Eval：

```text
填写运行时行为
├── 实际内容替换
├── 长文本和空值
├── 重复字段同步
├── 条件区域增删
├── 填写后的自动扩行、分页和布局变化
└── 保存重开稳定性
```

当前脚本可以检查 DOCX 是否可解析、契约是否有效和标记是否一致，但不能把这些静态检查表述为已经验证了正式填写行为。

## 15. 后续实施文档的顺序

详细实施与逐代码测试合同见 [PLAN.md](PLAN.md)。该计划已经获批并开始实施；评分代码
仍必须以本文为上层输入，并按以下顺序展开：

1. 冻结 Gold 填写契约、区域责任、定位器、有效样式和报告 schema。
2. 为每一类断言准备最小正例和单错误反例。
3. 设计共享文档事实模型及其可观测边界。
4. 设计并实现统一评测脚本及内部模块。
5. 接入三个学校的 Actual / Gold case。
6. 验证确定性、评分计算、硬失败和 `UNKNOWN` 路径。

实施计划必须逐项回答：实现哪个本文能力、使用哪个接口、消费什么输入、产生什么中间事实、由什么测试证明，而不能再次跳过顶层定义直接从脚本步骤开始。

## 16. 顶层验收标准

后续实现只有同时满足以下条件，才可以声称本阶段完成：

- 能在不调用上游提取流程的情况下独立运行；
- 能在未安装 `docfit` 产品包的独立环境中运行，且不启动产品 CLI；
- 产品与 Eval 的源码、依赖、测试、默认产物和发布包均无交叉包含；
- 同时消费 Actual 模板、Actual 契约、Gold 模板和 Gold 契约；
- 共享事实分析只实现一套，两个业务视角只负责断言；
- 原始模板保留四个分项和填写槽四个分项都有独立结果；
- 模板槽标记和填写契约之间完成双向一致性检查；
- 总分、分项分数、覆盖率与门禁结论均按版本化规则生成；
- 任一差异可定位到 Gold 区域或槽，并给出预期与实际事实；
- 不支持的事实显示为 `UNKNOWN`，不会静默通过；
- 输入文件只读且哈希可核验；
- JSON 和 Markdown 报告由同一份结果生成，内容一致。

一句话总结：

> 本阶段是一个只读、确定性的 Actual—Gold 静态评测器：以统一文档事实分析为底座，分别判断“模板保留是否正确”和“填写槽提取是否正确”，输出可门禁的结论、可比较的分数和可追踪的差异证据。
