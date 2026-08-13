# DocFit Skill 设计（04）

> 状态：最终方案
> 日期：2026-08-06
> 原则：Skill 是 Agent 的论文领域操作手册，不是工作流定义。

本文定义已经批准并在 Provider-independent P1 落地的两个领域 Skill。当前实现已从
M0 discovery marker 重写 `convert-thesis`，并从零增加只产生当前任务证据的
`docfit-school-extract`。五个真实 DOCX Tool 与 `docfit convert` 薄应用壳现已接入；
Skill 的完成声明要求当前 V2 LibreOffice render、全页视觉证据和独立验证；renderer、
Poppler 或环境失败时必须保留缺口。本地锁屏不属于产品依赖。

两个 Skill 已采用显式渐进式披露：`SKILL.md` 保留目标与判断入口，并用项目相对路径
指向同目录 `references/`。主 Agent 通过路径受限的 Read 按需加载；关联文件不会由
Skill 工具自动带入。主 Agent 虽拥有受信任 Bash，但 Skill references 的稳定加载契约
仍是明确路径的 Read，而不是 shell 行为。

## 1. Skill 在架构中的位置

Skill 把论文转换经验交给 Claude Agent，但执行权始终留在 Claude Agent SDK 与 Agent。

一个 Skill 只回答：

- 用户要完成什么；
- 开始前需要哪些事实；
- 何时读取 Knowledge；
- 何时调用五个 DocFit Tool；
- 哪些判断可以自主完成；
- 哪些情况应回看、重试、询问或停止；
- 什么结果可以称为完成；
- 哪些行为绝对禁止。

Skill 不定义固定阶段、状态转换、checkpoint、任务队列或工具调用图，也不保存学校具体字号、页边距和固定文案。

较长的冲突处理、模板文字分类、委派任务包、视觉复核和完成 schema 可以进入
`references/`，但 `SKILL.md` 必须说明在什么判断下读取哪一份明确路径。Agent 可以使用
Read/Glob/Grep 在批准根内发现相关材料；Skill 不应假定关联文件自动加载，也不应把
Bash、管道、重定向或网络作为读取 references 的必要条件。

## 2. 批准的领域 Skill

目标架构维护两个用户目标型 Skill：

| Skill | 用户目标 | 主要产物 |
|---|---|---|
| `docfit-school-extract` | 逐对象整理当前学校模板、要求和示例；最终角色逐页判断渲染缺陷 | 原子交付一份可填写 Word 与一份绑定该 Word hash 的填写契约 |
| `convert-thesis` | 使用通用 Knowledge 和当前任务学校材料，把学生论文转换成目标格式 | 最终 DOCX、预览和验证结果 |

模板提取可以作为独立用户目标，也可以服务当前转换任务。两个 Skill 共享通用
Knowledge 和五个 Tool，但不要求按“先提取、再转换”的固定顺序运行。
`docfit-school-extract` 不产出长期学校 Knowledge 或可自动复用的学校包；历史学校
提取资产只能作为迁移参考，新 Skill 必须按当前任务证据边界重新设计。

## 3. `docfit-school-extract`

### 3.1 目标与输入

当用户要求分析或整理学校模板、解释要求文件、识别模板槽位/固定文字/说明文字，或产出
可填写学校 Word 时触发。

输入可以包含模板 DOCX、要求 PDF/文字、官方示例、历史或社区样本、适用范围说明和用户确认。
Skill 使用模块化通用 Knowledge 解释当前材料。书面要求可选；没有时以用户选定模板作为任务
证据。测试阶段来源是否官方只记录为 provenance，不阻止进入准确度 Gold；若来源冲突，则由
用户明确本次 hash 绑定的目标材料。

### 3.2 输出边界

Agent 通过一个当前对象和有界局部上下文完成“判断 → 直接修改 → 回读/视觉反馈”循环。
Registry 是 Tool 私下绑定的版本化语义词典，只有在当前对象已被判断为填写位后才做精确
lookup 或最多五条 search；不得枚举 Registry 或把它当作学校模板的槽位待办表。

成功时用户可见主交付物固定为 `output/final-template.docx` 和 `output/fill-contract.yaml`。
二者是一个原子产品单元：契约必须绑定精确 Word hash，缺少任一文件或绑定不一致均失败。
内部不可变 Word 版本、修改回执、manifest、hash、PNG/PDF 和视觉覆盖记录留在
`work/.docfit/**`，不构成第三份主交付物。它不创建
`school profile`、跨任务规则包或 Knowledge 写入请求。无法由当前材料确认且会实质改变
删除/字段映射的事项才交给用户确认。

对样式，输出必须区分“Tool 已观测的有效值”“当前材料明确声明的目标值”、
覆盖范围、冲突和未决属性。Skill 不要求 Agent 从样式经验、历史任务或常识补值。

公开填写契约、内部审计和未来 M3 Template Actual 必须能够从最终 Word/回执表达：Registry ID/version/hash；
模板 hash；`slot_id` / `region_id → field_id`；
内容类型、slot required 状态、字段语义基数、条件与填充策略；绑定模板快照的
locator/区域边界；槽值
样式；`protected/slot/remove` 责任；逻辑页顺序、必填/选填/条件页与 `manual_only` 动作；
来源证据、覆盖和未决项。复合槽保存组件 locator，
连续内容保存 start/end locator。跨模板 field-alignment 只能从各模板合同派生，不取代
单个模板合同的 target locator。

`field_id` 只表示语义，不携带学校位置或样式。Registry 中还必须区分学生源可提取值、
任务输入、系统生成和外部/人工资产；否则目录、评审配置或二维码页会被错误要求从学生
DOCX 中提取。当前三校 candidate 文件仍待 Human 签署和 schema 冻结；它们是运行后 Eval
依据，不得作为 Agent 的 requirements 或运行时待办输入。

### 3.3 工具与反馈边界

`prepare-template` 使用两个互相隔离的 Agent 角色。语义角色只开放
`template_get_current_work_item`、`template_request_current_context`、
`template_submit_current_decision` 和 `template_report_ambiguity`；视觉角色只开放
`template_get_review_batch`。两个角色都只额外获得 Skill 和受限 Read，不开放 Bash、Write、
AskUserQuestion 或 Subagent。字段 ID 必须来自当前工作项已返回的 Registry 候选；对象 ID 只在
当前有界上下文中有效。

Skill 说明领域目标、对象判断、填写责任、按需知识和视觉缺陷标准，不描述遍历、cursor、
document/region ref、重试、终态或发布 API。应用拥有这些确定性控制：选择工作项、原子执行修改、
回读局部结果、推进 checkpoint、有界重试、组织全部页面批次、验证每页 verdict、失效旧版本证据
并自动发布。Tool 机械验证对象承载能力、Registry 字段、Word 边界、有效格式、包重开和非目标
文本保护；它不替 Agent 做局部语义或页面视觉判断。

局部语义角色只看当前对象、必要邻接对象和修改后局部反馈，禁止主动逐页扫描；全部局部工作
完成后，独立视觉角色才读取应用绑定的原生全页 PNG。图片成功返回不等于已审查，只有当前精确
版本每页都有显式 clean 且没有 defect 才能通过。任何后续编辑都会使旧 hash 的页面结论失效，
应用从第一页重新组织检查。PNG/PDF/evidence 保留在内部，不扩展用户交付集合。

## 4. `convert-thesis`

### 4.1 触发与输入

当用户要求论文排版、套用学校模板、按学校要求修改格式或检查转换结果时触发。

输入通常包括：

- 只读学生论文 DOCX，作为学生内容真值来源；
- 当前任务提供的干净、可填写目标学校模板，作为候选文档主干；
- 要求文件、官方示例或用户确认；
- 可选的学生信息和补充说明。

### 4.2 规则来源

Agent 先读取随产品发布的通用 Knowledge，获得论文格式概念、识别方法、解释原则
和通用处理模式；学校具体规则只能从当前任务提供的模板、文字要求、官方示例和
用户确认中推导。

Agent 调用 `docx_inspect` 获取当前模板的客观结构、有效样式、槽位、说明文字和
来源 hash，并在当前 SDK 会话中使用这些证据。任务证据和推导结论不得写回产品
Knowledge，也不要求先运行另一个 Skill；如果当前任务已经产生
`docfit-school-extract` 输出，`convert-thesis` 将它作为当前任务证据消费，而不是把两个
Skill 固定成串行阶段。

如果来源冲突、适用范围不明或证据不足，Agent 提出最小问题；不能根据文件名、
历史任务或通用 Knowledge 猜测学校规则。

字段槽连接使用同一份固定的 Content Field Registry ID/version/hash。模板提取结果与
学生内容提取结果可以共享同一
`field_id`，但它们分别保留模板 target locator 与学生 source locator；任一 locator 只在
绑定的文档 hash 下有效。字段相同只能提出候选，不能替代具体 placement、条件裁决或
写入前置检查。

样式处理使用“观测—语义绑定—确定性解析”边界：Tool 先返回模板中命名样式、
直接格式、继承后有效值、覆盖、缺失和冲突；Agent 仅判断这些事实对应哪个语义对象。
当属性仍缺失时，Agent 不读取样式值经验表或国家标准数值表，也不自行选值；它只能
请求现有 Tool/程序使用已明确选定的版本化国家级标准做逐属性确定性解析，
或者保留未决并说明缺口。标准无明文、不适用或与当前任务证据冲突时不得静默继续。

### 4.2.1 学生内容投影与 Placement

`convert-thesis` 不增加第三个“学生提取 Skill”。主 Agent 使用现有 `docx_inspect`、通用
Knowledge、当前任务证据和必要的 Human 确认识别学生内容；当任务或 Eval 需要物化结果
时，形成绑定学生源 hash 的 Student Content Actual。每项至少保留任务内 `content_id`、
`field_id` 或未注册状态、内容类型、规范值/原始观测值或复杂对象引用、source
locator、父项、顺序、
来源证据和未决状态。

论文级题名、作者等共享事实与它们在封面、摘要等位置的 occurrence 必须分离。一份事实
可以有多个 source locator；多处值冲突时保留各 occurrence 并询问或标记 unresolved，
不得任选一处。章节、段落、图、表、公式等有序局部内容继续使用各自 `content_id`、父子
关系和顺序，不能因 `field_id` 相同而合并。Registry 中没有的可见内容使用
`field_id: null` 和产物内 `local_field_key` 标记为 `unregistered`；没有目标槽的内容
另标记为 `unmapped`。两者都要保留来源证据和最终处置，不能为了生成漂亮映射而删除。

主 Agent 根据 Student Content 与 Template Truth 形成当前任务 placement：显式引用一个
或多个 source `content_id`、共享 `field_id`、具体 target `slot_id/region_id`、action、
projection/formatter、order、condition、status 和证据。日期拆分、复合值组合或
枚举显示只能使用可追溯的输入与规则，不得猜测缺失值。以下情况不得仅凭字段
同名自动确认：一对多、多对一、
复合槽、连续正文、条件内容、重复/冲突事实、retain/exclude、`generated.*`、任务配置和
外部整页资产。`unresolved` 必须留给用户或最终报告。

placement 是任务证据，不是 Tool locator。真正调用 `docx_edit` 前，主 Agent 仍使用
当前学生源/模板工作副本的有效 opaque ref 和 hash 前置条件；文档变化后重新 inspect。
这是一条可按需物化的数据连接，不是固定的三阶段工作流、全局 Content Ledger 或新的
运行时组件。

### 4.3 论文分析

修改前，Agent 使用 `docx_inspect` 获取结构摘要和当前对象引用，并调用
`docx_render(input_docx=..., overview=true)` 建立 V2 LibreOffice 视觉快照。默认联系表用于
全局扫描；Agent 再按风险通过 `docx_visual_review` 请求完整页面、object/text region 或
修改前后 compare。原始论文及 hash 是学生内容真值，目标模板及 hash 是候选主干真值。

分析必须覆盖可能承载可见内容或版式关系的段落、表格、合并单元格、图片、公式、脚注
尾注、文本框、域、内容控件、书签、编号、节、页眉页脚、跨 run 文本和 Tool 无法可靠
识别的对象。Agent 根据结构、样式、上下文和当前页面判断语义；Tool 只提供事实、稳定
引用与证据。

结构事实不能替代页面图片。涉及溢出、空白页、分页、遮挡、图表位置、页眉页脚、长
标题和整体版式的判断必须引用当前 V2 evidence。整页不足以辨认小字、域结果、图题编号
或边界时请求 detail region。可见应用错误、断裂域/交叉引用、未完成占位或截断必需内容
属于 blocking finding；DOCX 能打开或 renderer 成功不能覆盖这些视觉事实。

### 4.4 核心判断原则

- 先观察再修改，不凭段落序号、文件名或旧页码定位；
- 始终从目标模板工作副本产生候选，不以学生论文副本作为候选主干；
- 学生内容放入当前证据支持的模板槽位/区域，固定内容保留，说明文字在交付前清理；
- 跨文档复制复杂对象时使用当前来源对象 ref 与目标模板锚点；
- 无法可靠定位时重新 inspect，不扩大修改范围；
- 页码只在生成它的 V2 render 内有意义，不能作为 `docx_edit` 目标；
- OfficeCLI 语义对象必须在 LibreOffice PDF 中重新定位；mapping 歧义时查看候选完整页；
- 修改后重新 render；旧 object/evidence ref 不能证明新快照；
- 相同 render/view identity 使用缓存，不重复启动 renderer 或栅格化；
- 结构检查与页面观察冲突时保留两类证据，不静默选择其中一个。

这些是判断原则，不是固定阶段。

### 4.5 Tool 使用

- `docx_inspect`：读取模板与论文结构事实，返回绑定当前 hash 的 opaque refs；
- `docx_edit`：一次提交一组带前置条件的修改，只使用当前文档 ref；
- `docx_render`：输入只有 DOCX 与 overview，固定生成 `render:v2:` LibreOffice PDF、
  索引和可选联系表，始终声明 `fidelity: approximate`；
- `docx_visual_review`：从已有 render 按需返回 contact sheet、pages、regions 或 compare
  原生图片；它不修改文档、不选择 renderer、不返回语义 pass/fail；
- `docx_validate`：从源文件和最终文件重新取证，独立检查内容、结构、规则、当前
  render 和视觉覆盖。

Agent 根据图片形成带 evidence ref 的 findings；应用壳保存 findings，validate 只核对
当前文档绑定、完整页面覆盖和 blocking finding，不重新解释图片。Agent 不直接修改
OOXML，也不能仅凭底层成功声明或文件存在就宣布完成。

### 4.6 Tool 失败时

- `needs_input` 或引用失效：修正调用或重新 inspect/render；
- 对象映射歧义：查看候选完整页面，必要时缩小 selector 或询问用户；
- LibreOffice/Poppler/环境错误：只有输入或环境实际变化时重试；不切换视觉路径；
- adapter 或后置检查失败：不消费、不发布该产物；
- 相同错误没有新证据时不循环重试；
- 五个 DocFit Tool 的写入产物必须经过发布后置检查；Bash/Write 支持性产物不能替代。

### 4.7 完成条件

只有以下事实成立时，Agent 才能报告转换完成：

- 源文件未被覆盖；
- 最终 DOCX 由目标模板工作副本构建，存在、可重新打开且 package 关系可解析；
- 支持范围内的学生文本与复杂对象没有丢失、重复或错序；
- 当前任务证据支持的关键格式、模板要求、槽位、占位符和说明文字已处理；
- 使用 field/placement 合同时，每个 in-scope source 与 required target 都有明确处置；
- 当前最终 DOCX 有 V2 LibreOffice render，manifest hash 与最终文件一致；
- renderer/container/font identity 完整且 fidelity 为 `approximate`；
- 全部最终页面已由 Agent 分批审查，必要细节有 region evidence；
- findings 引用有效 evidence ref，未解决 blocking finding 为零；
- 文档在最终 render 后没有再次修改，独立 validate 通过；
- 无法自动确认的事项已在最终回复中说明。

### 4.8 Agent 最终回复

最终回复至少说明：

- 最终 DOCX 和可用预览的实际位置；
- 使用的通用 Knowledge 版本，以及当前任务模板和要求文件的来源 hash；
- 内容保留、格式、占位符、结构和渲染的验证摘要；
- Agent 已审查的页面范围、视觉 finding 摘要和对应 evidence refs；
- 当前 render/evidence refs、fidelity、renderer identity 和重要 warning；
- 仍需人工复核或用户补充的事项。

## 5. 两个 Skill 共享的可选委派契约

### 5.1 Skill 与 SDK 配置的责任

Skill 负责：

- 为什么和何时委派；
- 如何划定一个或多个分析范围；
- 选择模块化 Knowledge Package 中的哪些通用模块；
- 传递哪些当前任务证据与依赖；
- 期待什么结构化返回，以及如何把返回合并进主 Agent 判断。

Claude Agent SDK 配置只负责把安全边界落实为真实权限和上下文隔离。薄应用壳配置一个
具名 `docfit-unit-analyst`；技术上可以使用内联 `AgentDefinition`，但它不是领域
组件、专家目录或委派策略。SDK 原生 `PreToolUse` 权限钩子只允许该
`subagent_type`，拒绝 SDK 内置 `general-purpose` 和未知类型；普通
`can_use_tool` 回调不被当作 `Agent` 调用必经边界。

### 5.2 委派判断维度

主 Agent 根据当前证据判断，而不是执行阈值表：

- 分析对象是否实际存在；
- 证据量是否会显著挤占主上下文；
- 是否需要某类专门通用 Knowledge；
- 是否存在高风险版式或内容保护问题；
- 是否能够与其他分析独立并行；
- 委派收益是否高于额外上下文、调用和合并成本。

主 Agent 可以直接处理、合并多个范围、并行或串行调用同一 Subagent，也可以补充新
证据后再次委派。不能写成“检测到目录就必须启动 Subagent”或固定页数/对象数阈值。

### 5.3 Knowledge 与任务包

Knowledge 是 DocFit 的模块化产品资产，不是 SDK 中独立的 Knowledge Base runtime。
应用壳把当前产品包交给主 Agent；当前 Skill 选择本次委派所需模块。由于当前 Python
SDK 的 `Agent` Tool 单次输入不支持动态覆盖 `AgentDefinition.skills`，主 Agent 将
选中模块的内容、ID、版本和 digest 与当前任务证据一起写入 `Agent` prompt。

最小任务包包含：

```yaml
document_sha256: ...
analysis_scope:
  id: ...
  description: ...
  object_refs: [...]
  page_evidence_refs: [...]
knowledge_modules:
  - id: ...
    version: ...
    content_digest: ...
    content: ...
task_evidence:
  requirements_refs: [...]
  template_refs: [...]
known_rules: [...]
dependencies: [...]
requested_output: unit_analysis_v1
```

Subagent 不继承父对话、父系统提示词或父 Tool 结果。未显式传入的任务事实不能被当作
已知；学校值只能来自 `task_evidence` 或当前用户确认。

### 5.4 最小只读权限

`docfit-unit-analyst` 只拥有：

- `mcp__docfit__docx_inspect`；
- `mcp__docfit__docx_visual_review`。

它不拥有 `Agent`、`Skill`、`AskUserQuestion`、`docx_edit`、`docx_render` 或
`docx_validate`，也不拥有 Read/Glob/Grep/Write、Bash 或持久记忆。缺少页面或其他证据时，
它返回证据请求，由主 Agent 决定是否生成证据和是否再次委派。主 Agent 必须把选中的
Knowledge/reference 结论与当前任务证据显式放入任务包，不能让 Subagent 自行遍历项目。

### 5.5 结构化返回

```yaml
status: complete | needs_more_evidence | blocked
findings: [...]
confirmed_rules: [...]
uncertainties: [...]
dependencies: [...]
cross_unit_links: [...]
evidence_requests: [...]
proposed_operations: [...]
confidence: high | medium | low
```

`complete` 只表示本轮局部分析完成；`needs_more_evidence` 不触发隐藏工作流；
`blocked` 保留冲突或能力缺口。`proposed_operations` 不是写入授权，`confidence` 也
不能替代证据引用和主 Agent 复核。

### 5.6 Subagent 只分析，主 Agent 统一文档决策

Subagent 只分析。主 Agent 合并目录与正文标题、引用与参考文献、前置内容与节、页眉
页脚与多个范围之间的依赖，控制 inspect/render/visual-review 成本，串行调用
`docx_edit`，并在修改后重新取证和验证。这是取得可审计文档证据的产品完成条件，不是
固定执行阶段，也不是唯一物理写入权限。这里的固定安全边界是 Subagent 不写入。
主 Agent 可以用自动批准且无 DocFit 路径 gate 的 Bash/Write 保存支持性产物或执行命令。
五个 DocFit Tool 仍是证据绑定、可验证的文档操作路线；Skill 应优先通过 `docx_edit`
修改 DOCX，但这不是对受信任主 Agent 的文件系统 sandbox。

## 6. 当前任务学校材料

学校模板、PDF/文字要求、官方示例、适用范围和人工确认都属于当前任务输入。
Agent 可以形成结构化分析、来源 hash、冲突记录和本次转换所需的精确参数，并可用
Bash/Write 保存结果；无论路径位于何处，这些当前任务内容仍是任务证据或中间产物，
不是 Knowledge Package，也不得自动晋升到产品 Knowledge。

未来 M3 数据准备中，Content Field Registry、Template Truth、Student Content Truth 和
Placement Truth 也遵守同一边界：Registry 是开放、版本化的跨阶段研发语义合同，
不由 Eval 或任一 Skill 所有；后三者分别绑定模板 hash、学生源 hash 和双方明确版本。
它们可以服务多个 Eval 断言，但不会因为被保存就成为学校数据库、产品 Knowledge 或
跨任务自动复用规则。

处理原则：

- Tool 确定性提取模板结构、有效样式、可见对象、槽位和来源 hash；
- Agent 使用通用 Knowledge 解释证据、绑定语义角色并形成仅对当前任务有效的
  学校规则，但不生成未观测的样式值；
- 已批准的程序内部规则解析可在当前任务属性缺失时引用适用的国家级标准，
  并返回属性级来源；Agent 不直接读取该规则表；
- 文字要求与模板表现冲突时保留两份证据并要求当前用户确认；
- 字体、字号、行距、页边距、编号和节属性可以规范化为当前 Tool 调用参数，
  但不得保存到长期 `format-profile.yaml`；
- 无法确认的事实保持不确定，不从历史任务补齐；
- 任务结束后不自动复制模板、规则、参数或确认结论到产品 Knowledge。

如果同类处理方法在多个任务反复成立，只能把去除学校名称、数值和固定文案后的
通用概念、识别方法、解释原则或处理模式作为产品 Knowledge 的候选变更；该变更
仍需独立评审、测试并随新的产品版本发布。

## 7. 模板文字分类

`convert-thesis` 使用产品通用 Knowledge 来理解模板文字：

```text
fixed_content       最终必须保留的学校固定文字
conditional_content 根据学生类型决定是否出现
slot_placeholder    等待学生内容填入的位置
format_instruction  只用于说明格式、最终应清理的文字
```

这是一种 Agent 判断方法，不是 schema 或处理阶段。无法可靠分类时保留原文并询问，不猜测性删除。

## 8. Skill 内容组织

```text
<skill>/
├── SKILL.md
└── references/       # 由 SKILL.md 通过明确项目相对路径按需加载
```

Tool 实现不复制到 Skill。两个领域 Skill 的 references 保存任务操作指引；Knowledge Package
保存跨 Skill、跨学校和跨任务成立的领域概念与方法。学校事实只留在当前任务证据中。

Knowledge 模块不伪装成额外的用户 Skill，也不建立 cover/toc/body 等 Subagent 专家
目录。模块可以按消费场景演进；同一个 `docfit-unit-analyst` 接收本次真正需要的模块。
场景经验也不保存可直接套用的样式值、国家标准数值表或通用缺省补全表；
这些值不进入 Agent 的 Skill/Knowledge 上下文。

适合进入 references 的场景经验包括：

- 学校前置页与学生正文的边界；
- 旧目录、空附录标题和双语图题；
- 跨 run 的说明文字与占位符；
- 合并单元格、脚注尾注、文本框、域和内容控件；
- 页眉页脚、编号和节属性；
- renderer/font 环境变化造成的分页差异；
- 联系表、按需页面、局部证据、compare 和语义页面锚点；
- 对象引用失效、定位漂移和 renderer 伪成功。

这些经验帮助 Agent 判断，不扩展 Tool 数量，也不定义固定路线。

首批 references 围绕真实消费拆分：学校提取 Skill 使用证据/冲突、模板文字分类、Tool
恢复、场景边界、本地委派说明和输出 schema；转换 Skill 使用任务证据/冲突、Tool 恢复、
结构/视觉证据、场景边界、本地委派说明以及编辑/验证/完成说明。第 5 节定义共同的
Subagent 运行时字段和权限边界；每份 Skill 只在自己的 `references/` 中解释本领域何时
拆分、任务包携带哪些本领域证据以及怎样合并返回，不跨目录引用另一份 Skill 或项目级
共享操作手册。文件名不是新的运行时协议；`SKILL.md` 必须逐个引用真实存在的本地
reference，契约测试验证引用完整性和两棵 Skill 的领域隔离。

当前两个 Skill 不包含可执行脚本。主 Agent 现已拥有受信任 Bash；未来若 Skill 增加脚本，
必须明确命令、输入输出、凭据处理和测试边界，且不能把 shell 输出、凭据或文档正文写入
观测事件。该能力没有 DocFit sandbox，不能把提示词约束描述成强制隔离。

## 9. Skill 评审问题

- Agent 是否知道目标、证据和完成条件，而不只是知道步骤？
- 当前用户模板、学校规则或精确参数是否被写入长期 Knowledge？
- 学校事实是否被误写进通用 Skill？
- OOXML 细节是否泄漏到 Skill？
- 是否出现固定阶段、状态或 checkpoint？
- 是否绕过五个 Tool 新增了一个模板处理层？
- 是否在修改前、布局变化后和最终交付前使用了当前图片证据，而不是只看结构数据或旧截图？
- 是否错误地把页码、OfficeCLI 页码或 HTML 坐标当成稳定编辑/视觉身份？
- 相同 render/view identity 是否命中缓存，文档或环境变化后是否生成新 ref？
- Agent 是否只请求视图与 selector，而没有选择 renderer 或要求回退？
- OfficeCLI 与 LibreOffice 是否仍只承担各自固定职责，没有在 Skill 中出现 Provider 平台逻辑？
- 学生内容是否仍以原始 DOCX 和 hash 为真值？
- Tool 失败是否根据实际错误语义处理？
- 新增 Knowledge 是否已经去除学校值，并有多个任务或跨学校 Eval 支持其通用性？
- 委派原因、范围、Knowledge 选择和返回解释是否仍由两个领域 Skill 指导？
- Skill 是否要求 Agent 获取模板可观测的全部样式事实，同时禁止它读取经验值或
  杜撰缺失值？国家级标准补全是否仍是程序的确定性职责？
- 应用壳是否只落实 `docfit-unit-analyst` 的上下文隔离和最小权限，而没有识别论文
  单元或编排调用？
- 是否误建了多个单元专家、固定阈值、强制委派映射或动态
  `AgentDefinition.skills` 的虚假契约？
- Subagent 是否只分析，所有 render、edit、validate、用户询问和跨范围合并是否仍由
  主 Agent 负责？
- `SKILL.md` 是否以明确项目相对路径按需读取 references，而不是依赖自动加载或临时
  shell 约定？
- 模板侧是否输出 `slot_id/region_id + target locator + field_id`，学生侧是否输出
  `content_id + source locator + field_id/未注册状态`，且两侧 locator 分别绑定自己的 hash？
- placement 是否显式覆盖一对多、多对一、复合、条件、生成、外部和未映射内容，而
  没有把字段同名当作写入授权？

如果 Skill 需要复杂状态图才能解释，说明设计已经偏离 Agent-first 架构。
