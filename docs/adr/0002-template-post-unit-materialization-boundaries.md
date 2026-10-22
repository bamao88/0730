# ADR 0002: 模板 post-unit 物化采用意图编译与 handler 边界

日期: 2026-08-26
状态: accepted

2026-09-28 校准：本 ADR 保留“编译、上下文、执行、验收分责”的决策。当前输入输出形状和失败归属以
[模块流程](../modules/template-extraction.md) 与 [Contract](../contracts/template-extraction.md) 为准；
下文目标目录、初始 intent 和工程字段是设计背景，不是当前代码已实现的证明，也不是新增 Agent 输出要求。
工程能力不足时 fail closed 是运行时保护，修复完成仍要求原合法任务成功交付。

## 背景

模板提取 post-unit 阶段的目标，是把通过 Harness review 的学校语义判断物化为一份干净、可填写、
可追踪的 Word 模板。当前实现的主要风险不是某个具体 case 没处理，而是多个职责挤在同一层：

- 根据 Agent 输出的自由文本、`semantic_role` 字符串片段或模板可见 wording 选择执行路径；
- 在 materializer 内推断 Registry 字段、正文结构分支、格式说明清理和视觉占位处理；
- handler 逻辑、上下文解析、删除安全检查、OOXML 写入和 receipt 生成互相交织；
- 新学校模板出现新形态时，容易继续在主流程里加窄规则。

这违反模板提取的核心边界：Agent 负责学校语义判断，Harness/Tool/App 负责机械不变量和 DOCX 物化。
确定性代码可以执行已接受的语义判断，但不能用单个学校 wording、字段 label 或模型自由文本替代
Agent-facing schema、Registry affordance 或 accepted judgment。

## 决策

post-unit 物化采用稳定的内部意图层和分层 handler：

```text
accepted SemanticJudgmentSet
  -> Shape / Closure Review
  -> IntentCompiler
  -> ContextResolver
  -> PlanValidator
  -> ExecutionReadinessGate
  -> MaterializationPlan
  -> MaterializationHandlers
  -> OoxmlExecutor
  -> Receipt / Evidence
  -> Reopen Validation / Completion Review
```

该流程定义的是 post-unit materialization 的内部工程边界，不改变模板提取模块对外合同。对外产品交付仍然
只有：

```text
output/final-template.docx
output/fill-contract.yaml
```

### 流程层级

| 层级 | 输入 | 输出 | 负责 | 不负责 |
| --- | --- | --- | --- | --- |
| Agent-facing schema | unit reading packet、pre-input field vocabulary、Harness semantic feedback | `semantic_judgments[]` | 用 `source_entry_id + ordered parts` 表达学校语义、字段选择、样式义务、结构关系和 `needs_input` | DOCX locator、hash、执行顺序、删除安全证明、OOXML 操作 |
| Harness review | `semantic_judgments[]`、canonical source-entry inventory、reading view mapping、field vocabulary、Registry snapshot | accepted SemanticJudgmentSet | shape、source-entry span coverage、overlap、字段词表来源、span 解析、执行可消费性、反馈归因 | 判断学校语义对不对 |
| IntentCompiler | accepted SemanticJudgmentSet | typed `MaterializationIntent[]` | 把 Harness-accepted parts 和 resolved spans 编译成内部 enum 和参数 | 从 Agent 自然语言、学校 wording 或 label 猜意图 |
| ContextResolver | intents、reading packet mapping、Word tree、样式/布局事实 | `MaterializationContext[]` | 解析段落、表格、单元格、父子范围、固定标题、样例、布局载体、保护祖先 | 改写 DOCX、决定学校语义 |
| PlanValidator | intents + contexts + Registry/style facts | executable 或 rejected `MaterializationPlan` | 删除安全、唯一规则/唯一样式/唯一填写位置保护、冲突、unsupported fail closed | 为了跑通 case 自动补字段或补语义 |
| ExecutionReadinessGate | rejected plan / incomplete intents | 按责任归属的反馈 | 语义缺失或冲突返回 Agent 修订；映射、执行能力及环境缺口归工程层 | 写 DOCX、替 Agent 补字段、把工程缺口交给 Agent 或静默降级成 no-op |
| Handlers | 单类 intent + context | typed mutation commands | 按类别生成可执行 mutation，不直接写 zip | 跨类别调度、全局冲突检测、自由文本推断 |
| OoxmlExecutor | typed mutation batch、当前 candidate | 新 candidate | 统一修改 DOCX、校验 package、绑定 hash、失效旧 evidence | 选择语义分支、猜 Registry 字段 |
| Receipt/Evidence | plan、mutation result、validation | materialization receipt、刷新证据 | 说明每处变化为何发生、由哪个 judgment 支撑、哪些检查通过 | 作为运行时 Agent 的新语义 oracle |

### 执行就绪门

handler 只能处理已经闭合的 typed plan。就绪检查必须同时确认语义范围完整与对应操作可执行。
只有判断缺失、冲突或表达不完整等语义问题才返回 Agent 修订；已接受范围无法映射或无法修改时，
保留正确判断并由对应工程层补齐能力，不能让 Agent 改用途或输出内部安全证明来绕过缺陷。

典型就绪条件：

| intent | 必须已闭合 | 缺失时的责任与处理 |
| --- | --- | --- |
| `MATERIALIZE_SLOT` | `field_ids` 非空，且每个 field_id 来自 accepted ordered part 并已通过输入词表/Registry 校验 | 这个 fill slot 缺少 `parts[].field_id`；请从 pre-input `field_id_vocabulary` 选择字段 ID，证据不足则返回 `needs_input` |
| `MATERIALIZE_BODY_STRUCTURE` | ordered `body_structure` parts 已解析为 canonical source-entry spans，结构 parent 从 Registry metadata 派生，必要的条件已明确 | 缺 member 或语义条件可请求补判断；已提交范围的 span 映射失败归 Harness/Tool |
| `DELETE_BLOCK` / cleanup | 已判断清理范围及相关保留/样式义务，Harness/Tool 确定性验证删除安全 | 仅反馈缺少或冲突的语义责任；映射、删除能力与安全检查实现由工程层负责 |
| `KEEP_MANUAL_TABLE_CELL` | manual table/cell scope 和保护范围已明确 | 表格人工填写范围未闭合；请判断整表/整单元是否作为人工填写 affordance 保留 |
| `TRANSFER_STYLE_ONLY` | `style_obligations` 和目标 carrier 已明确 | 样式义务缺少承载对象；请补 style obligation 或说明无样式义务 |

revision packet 面向 Agent 时只使用 semantic work surface：

```text
status: needs_input
affected_unit_id
source_entry_ids
visible_text_summary
missing_requirement
why_it_blocks_execution
suggested_agent_action
field_id_vocabulary / needed_evidence_focus
```

禁止在这个反馈里要求 Agent 输出 `locator`、`object_ref`、`target_ref`、`candidate_hash` 或 OOXML operation。
reading block/range 只可补充阅读上下文，不代替源引用。上述 revision packet 只适用于语义缺口，
不能把所有 rejected plan 都投影成 Agent 修订任务。

### 内部意图模型

`MaterializationIntent` 是执行层唯一入口。它必须是 typed data，不是字符串搜索结果。

最低字段：

```text
intent_ref
intent_type
source_judgment_refs
scope_refs                 # 内部 canonical source_entry 引用；不是 Agent-authored reading view scope
context_requirements        # paragraph / table_cell / body_structure / fixed_heading 等
field_ids                   # 只来自已接受 ordered parts
structure_ref / members      # 内部 payload；structure_ref 从 Registry parent 派生
resolved_spans
condition / reason           # 只作已表达条件/解释，不驱动字段推断
unsupported_policy
```

初始 intent type：

```text
DELETE_BLOCK
KEEP_FIXED_CONTENT
MATERIALIZE_SLOT
MATERIALIZE_BODY_STRUCTURE
KEEP_MANUAL_TABLE_CELL
TRANSFER_STYLE_ONLY
REFRESH_GENERATED_CONTENT
NO_OP
UNRESOLVED
```

约束：

- `intent_type` 只能来自 Harness 已接受的 ordered `parts[].role` 和 plan validator 的机械上下文闭包。
- `field_ids` 只能来自 Harness 已接受的 ordered `parts[].field_id`，且必须已经由输入
  `field_id_vocabulary` 和 Registry snapshot 验证。
- 结构分支条件必须由 Agent/schema 或明确的结构条件表达，不能由 `农理工`、`文法`、`经管` 这类模板 wording
  在 materializer 内硬编码选择。
- 自由文本 `judgment`、`reason`、`rationale` 只进入 receipt 作为解释证据，不能驱动执行分支。

### 目标目录

迁移完成后，post-unit materialization 的代码目录应稳定为：

```text
src/docfit/template/materialization/
  __init__.py
  models.py                 # typed intents, contexts, plan, receipt dataclass / TypedDict
  compiler.py               # accepted SemanticJudgmentSet -> MaterializationIntent[]
  context.py                # reading packet + Word tree -> MaterializationContext
  plan.py                   # MaterializationPlan assembly
  validators.py             # delete safety, overlap, registry/style, executable closure
  instruction_notes.py      # 格式说明识别与迁移规则，只消费 typed context
  layout_placeholders.py    # □、××、…… 等布局/样例载体处理，只消费 typed context
  field_binding.py          # 已确认字段绑定的校验和投影，不做文本猜字段
  receipts.py               # action receipt、before/after 摘要、evidence refs
  executor.py               # 唯一 DOCX 写入入口
  runtime.py                # package 内唯一公开编排入口，不保存旧顶层实现
  handlers/
    fixed_content.py
    slots.py
    body_structure.py
    table_manual_cells.py
    generated_content.py
    cleanup.py
```

旧顶层 materializer 文件不保留。最终状态下 `docfit.template.materialization` 是唯一公开入口；
`runtime.py` 只承担 package 内编排，不让新旧两套 materializer 同时长期存在。

## 模块边界

### Agent-facing schema / Skill

负责：

- 定义 runtime Agent 能表达的学校语义词表；
- 明确 `source_entry_id`、ordered `parts[].role`、`parts[].field_id`、`reason`、`open_questions` 和
  `needs_input` 的含义；reading block/range ID 只组织输入 view，不是 judgment scope；
- 遇到字段或结构证据不足时返回 `needs_input`。

不负责：

- 输出 object ref、locator、target ref、candidate hash；
- 输出 OOXML 操作枚举；
- 为了避开 materializer 限制而改写学校语义。

问题归因：

- Agent 把人工填写表格拆成字段槽：修 Skill/Reference/schema。
- Agent 没表达正文结构适用条件：修 schema 或 Skill，再由 Harness review 要求补对应 source entry 的
  ordered parts。
- Agent 语义正确但执行失败：不要先修 prompt，先看 Harness/Context/Plan/Handler/Executor。

### Harness review

负责：

- 接收并保存 accepted SemanticJudgmentSet；
- 检查 canonical source-entry span coverage、overlap、unknown ref、field vocabulary 来源、Registry field
  存在、Harness span 解析和明确 closure 字段；reading block/range 只用于输入 view 和反馈分组；
- 区分语义可修订问题与工程失败，仅把前者转换成 Agent 可读的语义工作面反馈；
- 为 materialization 提供已接受且可消费的 judgment batch。

不负责：

- 判断“某段学校模板语义是否应该是固定内容或字段槽”；
- 把缺失字段自动补成最接近 Registry field；
- 替 Agent 选择正文分支。

问题归因：

- 未注册字段被放进 accepted batch：修 Harness Registry binding gate。
- Agent 输出 object locator 而 reading packet 已存在：修 Harness feedback / schema lint。
- 缺字段却进入 materializer：修 Harness review，不修 handler。

### IntentCompiler

负责：

- 将 accepted judgment 的每个 part 及原 span 的义务映射成 `MaterializationIntent`，整条分类不能覆盖局部义务；
- 拒绝含混、互斥或不完整的执行意图；
- 保留 `source_judgment_refs`，让后续 receipt 可追踪。

不负责：

- 字符串包含判断，例如 `if "fixed" in judgment_text`；
- 从 block 文本里的 `学生姓名`、`摘要`、`农理工` 猜字段或分支；
- 解析 DOCX 上下文。

问题归因：

- 同一个 judgment 被编译成多个互斥 intent：修 compiler 或 schema。
- 需要读自然语言才知道 intent：修 schema/Skill，不在 compiler 加 regex。

### ContextResolver

负责：

- 将 accepted canonical source-entry spans 映射到当前 Word tree 的段落、run、表格、单元格、SDT、父子范围；
- 判定 context kind，例如 `fixed_heading`、`paragraph_indent`、`sample_value`、
  `manual_table_cell`、`body_numbering`、`instruction_note`；
- 发现受保护祖先，比如整表人工填写区、唯一规则、唯一样式证据、唯一填写位置。

不负责：

- 删除、替换或写入 DOCX；
- 猜该内容是否应成为字段；
- 自行覆盖 Agent 的语义判断。
- 把上下文容器替换成原 span 的授权修改范围。

问题归因：

- `□` 被当成错误形态：先看 Agent/intent 是否给出 context，再修 ContextResolver 或
  `layout_placeholders.py`。
- 表格内子段落被误处理：修 ContextResolver 的 protected ancestor 识别和 PlanValidator。

### PlanValidator

负责：

- 在写 DOCX 前检查整批 plan 是否可执行；
- 检查删除不会破坏唯一规则、唯一样式证据、唯一填写位置、图片锚点、表格边界和 section/layout；
- 检查 manual table cell、generated content、body structure 和 slots 之间没有冲突；
- fail closed，返回可归因的 blocker；
- 把缺少字段、结构 member、variant、style obligation 或 cleanup safety 的 blocker 交给
  ExecutionReadinessGate，投影成 Agent 可修的 revision packet。

不负责：

- 自动选择 fallback intent；
- 自动把 unsupported case 转成 no-op 且继续发布；
- 替 handler 修改 XML。

问题归因：

- 输出文档丢掉人工填写表格：PlanValidator 应该挡住，若没挡住修 validator。
- 删除了唯一格式说明：PlanValidator 应该挡住或要求 style_obligation，若没挡住修 validator。
- 字段槽缺 `field_id` 却写入 DOCX：PlanValidator / ExecutionReadinessGate 漏拦，应修 gate，
  不在 slot handler 补字段。

### Handlers

负责：

- 每类 intent 生成 typed mutation command；
- 只处理自己的类别；
- 遇到上下文不支持时返回 structured unsupported reason。

不负责：

- 直接写 zip；
- 全局调度；
- 跨 handler 删除或替换别人的目标；
- 通过文本猜字段、猜结构、猜学校分支。

问题归因：

- slot placeholder 生成不符合载体：修 `handlers/slots.py`。
- 正文结构成员顺序错：修 `handlers/body_structure.py` 或 ContextResolver 的顺序映射。
- 固定标题括号清理误删“毕业论文（设计）”：修 `instruction_notes.py` 的类别规则和反向测试。

### OoxmlExecutor

负责：

- 作为唯一 DOCX 写入入口执行 mutation batch；
- 维护 package validation、atomic write、hash binding、旧 evidence 失效；
- 返回 mutation result 给 receipt。

不负责：

- 选择 handler；
- 解释学校语义；
- 根据字段 label 生成额外文本。

问题归因：

- XML 写坏、DOCX 打不开、hash 不一致：修 Executor / Tool package 层。
- 语义选择错但 XML 写入正确：不要修 Executor。

### Receipt / Evidence

负责：

- 记录每个 action 的 intent、handler、source judgment、scope、before/after 摘要、field/style 绑定、
  safety check 和 skipped/unsupported reason；
- 支持 completion review 和 replay；
- 证明最终 candidate 来自当前 accepted judgment batch。
- 验收以原始 accepted spans 的修改及保留义务为准，不能只对照执行器派生出的目标或成功回执。

不负责：

- 作为 Agent runtime oracle；
- 保存 Gold 答案；
- 替代 final render、candidate validation 或 Fill Contract 校验。

问题归因：

- 最终文本看起来变了但 receipt 解释不了：修 receipts。
- receipt 和 DOCX 不一致：修 Executor/Receipt binding。

## 特殊规则归属

| 补充点 | 归属层 | 规则 |
| --- | --- | --- |
| `JudgmentClassifier` 改为 `IntentCompiler` | IntentCompiler + schema | 只编译显式字段，不读自由文本猜 intent |
| Registry 字段绑定 fail closed | Agent-facing evidence + Harness review + ExecutionReadinessGate + `field_binding.py` | 字段槽必须有已验证 field_id；缺字段时返回 Agent 修 judgment，materializer 不根据 block 文本猜字段 |
| 人工填写表格整表保留 | Agent schema + ContextResolver + PlanValidator + handler | 表格祖先被判断为 manual cell/form 后，子元素 slot handler 不可拆 |
| 括号格式说明 | Agent schema + ContextResolver + `instruction_notes.py` | 只有 context 表明是格式说明时清理；普通括号必须保留 |
| `□`、`××`、`……` | ContextResolver + `layout_placeholders.py` + handler | 按 fixed heading、indent、sample value、manual cell、body numbering 分别处理 |
| 正文结构分支 | Agent schema + Harness review + body_structure handler | source-entry ordered parts 和必要条件显式表达；不在 handler 用学校 wording 选分支 |
| 可解释账本 | `receipts.py` + Executor | 每个 mutation 必须能追到 judgment 和 safety check |

## 备选方案

方案一：继续在现有 materializer 中局部抽函数。

这个方案 diff 小，但仍会让字段绑定、上下文解析、执行分支和 OOXML 写入共用同一主流程。它不能防止新学校
继续堆 `if/regex`。

方案二：直接重写为一套新 runtime。

这个方案可以一次性整理目录，但风险过大，容易绕开现有 Harness、Tool、receipt、publication 和测试边界。
DocFit 不应长出第二套 Agent runtime。

方案三：采用意图编译与 handler 边界，迁移完成后删除旧实现。

这个方案保留 Agent-native + Harness-controlled 的现有架构，把混在 materializer 内的职责拆回正确层。
迁移期间可以用 shadow plan 和 replay 控制风险，最终目录稳定且没有遗留旧实现。

选择方案三。

## 后果

正向后果：

- 新学校模板优先新增 schema/context/handler 测试，而不是改主流程；
- 执行器只看 typed plan，减少模型 wording 对结果的影响；
- field binding、manual table、body structure、layout placeholder 的归因更清晰；
- receipt 能解释最终每处文本为什么变化；
- 重构完成后目录与责任边界更可维护。

代价：

- 需要一次完整迁移，不能只修单点函数；
- 需要补 Agent-facing schema、Harness review、contract tests 和 replay；
- 迁移期间要维护 shadow plan 与旧行为对比，直到新实现接管；
- 现有依赖 materializer 文本推断的测试必须改成 fail-closed 或显式 judgment。

## 何时重看

出现以下情况时重看本 ADR：

- Claude Agent SDK 或 Office backend 原生提供稳定的 semantic-to-DOCX materialization contract；
- post-unit 不再由 Agent 输出学校语义判断；
- Fill Contract 或 Word 产物不再是模板提取的交付边界；
- 三校 replay 和真实模板运行证明该分层引入了不可接受的复杂度。
