# DocFit Skill 设计（04）

> 状态：最终方案
> 日期：2026-08-04
> 原则：Skill 是 Agent 的论文领域操作手册，不是工作流定义。

本文定义已经批准并在 Provider-independent P1 落地的两个领域 Skill。当前实现已从
M0 discovery marker 重写 `convert-thesis`，并从零增加只产生当前任务证据的
`docfit-school-extract`。五个真实 DOCX Tool 与 `docfit convert` 薄应用壳现已接入；
Skill 的完成声明仍要求当前 Adobe candidate、全页视觉证据和独立验证；凭据、额度、
网络或 backend 失败时必须保留缺口。本地锁屏不属于产品依赖。

两个 Skill 已采用显式渐进式披露：`SKILL.md` 保留目标与判断入口，并用项目相对路径
指向同目录 `references/`。主 Agent 通过路径受限的 Read 按需加载；关联文件不会由
Skill 工具自动带入，Bash 也不属于读取或执行 Skill 的能力面。

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
Read/Glob/Grep 在批准根内发现相关材料；Skill 不应假定关联文件自动加载，也不能要求
任意 Bash、管道、重定向或网络。

## 2. 批准的领域 Skill

目标架构维护两个用户目标型 Skill：

| Skill | 用户目标 | 主要产物 |
|---|---|---|
| `docfit-school-extract` | 解释当前任务模板、要求和示例 | 带来源引用、仅对当前任务有效的模板事实、冲突、不确定性和候选参数 |
| `convert-thesis` | 使用通用 Knowledge 和当前任务学校材料，把学生论文转换成目标格式 | 最终 DOCX、预览和验证结果 |

模板提取可以作为独立用户目标，也可以服务当前转换任务。两个 Skill 共享通用
Knowledge 和五个 Tool，但不要求按“先提取、再转换”的固定顺序运行。
`docfit-school-extract` 不产出长期学校 Knowledge 或可自动复用的学校包；历史学校
提取资产只能作为迁移参考，新 Skill 必须按当前任务证据边界重新设计。

## 3. `docfit-school-extract`

### 3.1 目标与输入

当用户要求分析学校模板、解释要求文件、识别模板槽位/固定文字/说明文字、比较模板与
文字要求，或为当前转换准备可追溯任务证据时触发。

输入可以包含模板 DOCX、要求 PDF/文字、官方示例、适用范围说明和用户确认。Skill
使用模块化通用 Knowledge 解释当前材料，输出只在授权任务目录和当前 SDK 会话中有效。

### 3.2 输出边界

输出包括来源 hash、证据位置、观察事实、冲突、不确定性、适用范围和候选 Tool 参数。
它不创建 `school profile`、学校目录、跨任务规则包或 Knowledge 写入请求。无法由当前
材料确认的事项保持未知，并交给当前用户确认。

### 3.3 可选委派

Skill 可以让主 Agent 直接分析，也可以把证据密集或需要专门通用知识的局部范围交给
`docfit-unit-analyst`。复合前置结构、声明页、符号表、图表目录或学校特有结构不必
匹配预设单元；主 Agent 可以直接处理，或把复合范围与相关 Knowledge 模块一起委派。

## 4. `convert-thesis`

### 4.1 触发与输入

当用户要求论文排版、套用学校模板、按学校要求修改格式或检查转换结果时触发。

输入通常包括：

- 学生论文 DOCX；
- 当前任务提供的目标学校模板、要求文件、官方示例或用户确认；
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

### 4.3 论文分析

修改前，Agent 使用 `docx_inspect` 获取高信号摘要和对象引用，并使用
`docx_render(render_intent=baseline)` 首次建立 Adobe 服务转换分页基线。`docx_render` 可以
随结果附带一张有大小限制的 contact sheet；需要指定页面、裁剪或前后比较时，Agent
再使用 `docx_visual_review` 读取同一个 `render_ref`。完整解析结果和渲染证据由 Tool
保存在任务临时目录，原始论文及其 hash 始终是学生内容真值。渲染结果附带元素 bbox
映射时，Agent 用它把视觉问题缩小到候选 `object_ref`，但仍通过
`docx_inspect` / `docx_edit` 的前置条件确认真正目标。

对于分页敏感的论文转换，Adobe PDF Services 可用时，Agent 在修改前
为输入论文和模板建立一次 `baseline` 证据，不把初始文件冒充最终交付。
基线页面应尽量绑定当前快照的 `object_ref`、节引用、首尾对象或文字锚点；没有
可靠映射时只能作为人工视觉参考，不能根据页码驱动修改。Adobe 服务尚不可用
时，Agent 使用近似渲染开始工作，并保留对应 `verification_gap`。

分析必须覆盖可能承载可见内容或版式关系的对象，包括：

- 段落、表格和合并单元格；
- 图片、公式、脚注尾注和文本框；
- 域、内容控件、书签、编号；
- 节、页眉页脚和页面相关属性；
- 跨多个 run 的逻辑文本；
- Tool 无法可靠识别的可见对象。

Agent 根据上下文、页面、样式和相邻内容判断语义。Tool 只提供事实和稳定引用，不替 Agent 判断标题、正文或模板说明。

结构事实不能替代页面图片。涉及溢出、空白页、分页、遮挡、图表位置、页眉页脚、
长标题和整体版式的判断，Agent 必须基于 `docx_render` 随结果返回的有限预览，或
`docx_visual_review` 从有效 `render_ref` 读取的当前图片证据完成。

整页批次必须同时服从 Tool 图片预算和 SDK transport 消息预算。整页缩放后无法辨认
的小字、域结果、标题/图题编号或页边界细节，应通过同一 render ref 的受控 crop
复核。页面中可见的应用错误标记、断裂域/交叉引用、未完成占位或截断必需内容属于
blocking finding；DOCX 能打开、Adobe 转换成功或结构验证通过都不能覆盖这些视觉事实。
记录类别和 evidence ref 即可，不在日志或报告中复制周围学生正文。

### 4.4 核心判断原则

- 先观察再修改，不凭段落序号或文件名定位；
- 优先在原论文上做受控格式修改，能局部修改时不整体重建；
- 必须使用模板前置部分时，明确区分学校固定内容、条件内容、学生槽位和最终应删除的说明文字；
- 模板中的旧目录不是学生正文，学生正文中的标题也不能因外观相似而被当作目录；
- 空的附录标题、双语图题、跨 run 占位符等边界情况必须根据证据处理；
- 学生文字与学校固定文字冲突时，优先保护学生内容并询问；
- 无法可靠定位时重新 inspect，不扩大修改范围；
- 页码只在生成它的 render ref 内有意义；不能把 Adobe 第 N 页直接当作近似 Provider 第 N 页，也不能把页码作为 `docx_edit` 的目标；
- 修改前保留输入和模板的 `baseline`；修改过程中可以多次使用 OfficeCLI
  `edit_feedback`，并根据当前 render 的对象映射观察受影响对象、所在页和相邻页；
- 当 Agent 认为当前文档可能结束本轮时，使用Adobe PDF Services API
  `candidate_verification` 生成候选证据；在 Agent 实际查看图片前不得称为 final；
- Agent 只选择 `baseline`、`edit_feedback` 或 `candidate_verification`，不选择或
  传入具体后端；固定路由由 `docx_render` 内部完成，后端失败不得跨职责静默回退；
- 如果候选图片暴露问题，Agent 修改文档并继续判断；上一候选 render 可以作为新候选
  的 `baseline_render_ref`，不需要为了标记“新一轮”再次调用 Adobe PDF Services API；
- 相同文档 hash、intent、Provider/SDK、转换 profile、环境证据和渲染参数下不得重复
  请求 Adobe 转换；缓存命中返回已有证据，不产生新的文档渲染；
- 多次调用 `docx_visual_review` 只是在同一 `render_ref` 上读取不同视图，不产生新
  render，也不构成新一轮；
- 目录、页码和跨页对象依赖交付转换时，若没有经过 Agent 查看且绑定当前文档的
  `candidate_verification` 证据，明确人工复核要求和 `verification_gap`；
- 结构检查和页面渲染冲突时保留两类证据，不静默选择其中一个。

这些是判断原则，不是必须按顺序执行的阶段。

### 4.5 Tool 使用

- `docx_inspect`：通过 OfficeCLI 读取模板与论文事实，复用相同输入的分析缓存；
- `docx_edit`：通过 OfficeCLI 一次提交一组带前置条件的修改，只使用当前文档的有效对象引用；
- `docx_render`：用 `render_intent` 区分首次 Adobe 基线、OfficeCLI 编辑反馈和 Adobe 候选
  验证；产生新的 `render_ref`，或在缓存命中时返回已有 ref，并记录 fidelity、实际
  后端/SDK、转换 profile、环境可见性、parent ref、分页差异和可选元素映射；
- `docx_visual_review`：只读取已有 `render_ref`，把指定页面、裁剪图、contact sheet
  或前后对比图送入当前 Agent 上下文；它不调用 Adobe PDF Services API 或 CLI 渲染，不产生新的
  文档 render，也不返回 `pass` / `fail`；Agent 以受控批次覆盖整页，并在小字或域错误
  无法辨认时请求 crop；
- `docx_validate`：通过 OfficeCLI 与 DocFit 后置检查从源文件和最终文件重新取证，独立检查内容保留、适用格式、占位符、结构和渲染，不把 OfficeCLI 的成功声明当作唯一 oracle。

`docx_visual_review` 不替 Agent 做视觉判断。Agent 根据图片形成带页码和 evidence ref 的结构化 finding；应用壳保存这些 findings，`docx_validate` 只核对它们是否对应当前文档、是否覆盖必查页面，以及是否存在 blocking finding。

Agent 不直接修改 OOXML，也不能仅凭底层 MCP 返回成功、输出文件存在或确定性结构检查通过就宣布完成。

### 4.6 Tool 失败时

- `needs_input` 或引用失效：根据现有证据修正调用或重新 inspect；
- 文档定位歧义或对象不支持：缩小范围，可能损坏内容时停止并询问；
- 后端或环境错误：仅在输入、调用方式、范围或环境有实际变化时重试固定后端；
- Adapter 或后置检查失败：不消费该产物，停止并说明；首版不切换到另一职责的后端补位；
- Adobe PDF Services API 不可用时：可以继续 OfficeCLI 编辑迭代，但保留 `verification_gap`，不得把近似预览作为 Adobe 交付证据或宣布完成；
- 相同错误在没有新证据时不循环重试；
- 所有写入产物必须是 `committed: true`，并通过必要后置检查。

### 4.7 完成条件

只有以下事实成立时，Agent 才能报告转换完成：

- 源文件未被覆盖；
- 最终 DOCX 存在、能重新打开且 package 关系可解析；
- 支持范围内的学生文本、表格、图片、公式和其他关键对象没有丢失、重复或错序；
- 当前任务证据支持的关键格式和模板要求已应用；
- 必填槽位已填写，模板占位符和说明文字已处理；
- 输入、模板和最终文件的图片证据与各自文档 hash、Provider、字体和页面绑定；
- 同一文档 hash 的 OfficeCLI / Adobe 页面比较使用当前快照的对象引用、节引用或文字锚点，不根据相同页码假设内容范围相同；文档 hash 变化后重新 inspect，不复用旧 `object_ref`；
- 可能影响分页或布局的修改已经通过变化页与相邻页图片复核；
- 最终文件的全部页面已经由 Agent 分批视觉审查，未解决的 blocking finding 为零；
- 若声称已经通过 Adobe 交付转换复核，必须存在绑定当前文档、已被 Agent 查看且没有
  后续修改的 `candidate_verification` + `official_service_conversion` 证据；否则只能
  说明近似渲染已观察并明确后续交付复核要求；
- 严重 Tool 错误已解决；
- 无法自动确认的事项已在最终回复中明确说明。

### 4.8 Agent 最终回复

最终回复至少说明：

- 最终 DOCX 和可用预览的实际位置；
- 使用的通用 Knowledge 版本，以及当前任务模板和要求文件的来源 hash；
- 内容保留、格式、占位符、结构和渲染的验证摘要；
- Agent 已审查的页面范围、视觉 finding 摘要和对应 evidence refs；
- 实际使用的 render intent、fidelity、Provider、parent ref 和重要 warning；
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
`docx_validate`，也不拥有 Read/Glob/Grep、Bash 或持久记忆。缺少页面或其他证据时，
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

### 5.6 单一写入

Subagent 只分析。主 Agent 合并目录与正文标题、引用与参考文献、前置内容与节、页眉
页脚与多个范围之间的依赖，控制 inspect/render/visual-review 成本，串行调用
`docx_edit`，并在修改后重新取证和验证。这是安全不变量，不是固定执行阶段。

## 6. 当前任务学校材料

学校模板、PDF/文字要求、官方示例、适用范围和人工确认都属于当前任务输入。
Agent 可以在授权任务目录中形成结构化分析、来源 hash、冲突记录和本次转换所需的
精确参数，但这些内容是任务证据或中间产物，不是 Knowledge Package。

处理原则：

- Tool 确定性提取模板结构、有效样式、可见对象、槽位和来源 hash；
- Agent 使用通用 Knowledge 解释证据并形成仅对当前任务有效的学校规则；
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

适合进入 references 的场景经验包括：

- 学校前置页与学生正文的边界；
- 旧目录、空附录标题和双语图题；
- 跨 run 的说明文字与占位符；
- 合并单元格、脚注尾注、文本框、域和内容控件；
- 页眉页脚、编号和节属性；
- 不同渲染器造成的分页差异；
- Adobe 服务分页基线、CLI 高频反馈、候选证据继承和页面锚点；
- 对象引用失效、定位漂移和 Provider 伪成功。

这些经验帮助 Agent 判断，不扩展 Tool 数量，也不定义固定路线。

首批 references 围绕真实消费拆分：学校提取 Skill 使用证据/冲突、模板文字分类、Tool
恢复、场景边界、本地委派说明和输出 schema；转换 Skill 使用任务证据/冲突、Tool 恢复、
结构/视觉证据、场景边界、本地委派说明以及编辑/验证/完成说明。第 5 节定义共同的
Subagent 运行时字段和权限边界；每份 Skill 只在自己的 `references/` 中解释本领域何时
拆分、任务包携带哪些本领域证据以及怎样合并返回，不跨目录引用另一份 Skill 或项目级
共享操作手册。文件名不是新的运行时协议；`SKILL.md` 必须逐个引用真实存在的本地
reference，契约测试验证引用完整性和两棵 Skill 的领域隔离。

当前两个 Skill 不包含可执行脚本。未来若确有确定性脚本需求，不开放任意 Bash；必须
另行设计只允许随产品发布固定脚本、固定解释器、结构化参数、授权任务输入输出、无
shell expansion/管道/重定向/网络且不传 Agent API 凭据的执行面。

## 9. Skill 评审问题

- Agent 是否知道目标、证据和完成条件，而不只是知道步骤？
- 当前用户模板、学校规则或精确参数是否被写入长期 Knowledge？
- 学校事实是否被误写进通用 Skill？
- OOXML 细节是否泄漏到 Skill？
- 是否出现固定阶段、状态或 checkpoint？
- 是否绕过五个 Tool 新增了一个模板处理层？
- 是否在修改前、布局变化后和最终交付前使用了当前图片证据，而不是只看结构数据或旧截图？
- 是否错误地把页码当成稳定编辑身份，或把 Adobe 与 CLI 的同页码当成同一内容范围？
- Adobe 转换是否遵守缓存和调用额度，只用于首次 baseline 与必要的 candidate verification？
- Agent 是否只表达 `render_intent`，而没有选择具体后端或要求跨职责回退？
- OfficeCLI 与 Adobe PDF Services API 是否仍只承担各自固定职责，没有在 Skill 中出现通用 Provider 平台逻辑？
- 学生内容是否仍以原始 DOCX 和 hash 为真值？
- Tool 失败是否根据实际错误语义处理？
- 新增 Knowledge 是否已经去除学校值，并有多个任务或跨学校 Eval 支持其通用性？
- 委派原因、范围、Knowledge 选择和返回解释是否仍由两个领域 Skill 指导？
- 应用壳是否只落实 `docfit-unit-analyst` 的上下文隔离和最小权限，而没有识别论文
  单元或编排调用？
- 是否误建了多个单元专家、固定阈值、强制委派映射或动态
  `AgentDefinition.skills` 的虚假契约？
- Subagent 是否只分析，所有 render、edit、validate、用户询问和跨范围合并是否仍由
  主 Agent 负责？
- `SKILL.md` 是否以明确项目相对路径按需读取 references，而不是依赖自动加载或 Bash？

如果 Skill 需要复杂状态图才能解释，说明设计已经偏离 Agent-first 架构。
