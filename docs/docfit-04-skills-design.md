# DocFit Skill 设计（04）

> 状态：最终方案
> 日期：2026-08-05
> 原则：Skill 是 Agent 的论文领域操作手册，不是工作流定义。

本文定义已经批准并在 Provider-independent P1 落地的两个领域 Skill。当前实现已从
M0 discovery marker 重写 `convert-thesis`，并从零增加只产生当前任务证据的
`docfit-school-extract`。五个真实 DOCX Tool 与 `docfit convert` 薄应用壳现已接入；
Skill 的完成声明仍要求当前 Adobe candidate、全页视觉证据和独立验证；凭据、额度、
网络或 backend 失败时必须保留缺口。本地锁屏不属于产品依赖。

2026-08-05 批准的目标职责对两个 Skill 的产物边界作了收紧：学校提取 Skill 将生产
冻结干净模板与 hash 绑定槽位索引，转换 Skill 将只消费该 Interface 与学生 DOCX。
当前 P1/M2 Skill、CLI 和验证合同仍是旧实现，尚不具备完整槽位索引、固定内容保护和
源内容覆盖门；实施必须遵循 06 的独立候选切片。本文件以下部分描述目标合同，不能
用来声称当前实现已经完成该修订。

两个 Skill 采用显式渐进式披露：`SKILL.md` 保留任务、输入输出、推荐操作方法、常用
判断标准和真实失败提炼的高风险规则；同目录 references 展开主文件放不下的可复用判断
问题，不按封面、目录等输入部件逐一枚举。

## 1. Skill 在架构中的位置

Skill 把论文转换经验交给 Claude Agent，但执行权始终留在 Claude Agent SDK 与 Agent。

一个 Skill 回答：

- 用户要完成什么；
- 输入和稳定交付边界分别是什么；
- 模板提取或论文转换通常怎样开展，各步需要做什么语义判断；
- 哪些已经发生过的高风险错误需要特别避免；
- 哪些行为禁止，以及最终回复提供什么。

Skill 不定义持久化阶段、checkpoint、任务队列或运行时状态机，也不保存学校具体字号、
页边距和固定文案。它可以给出“观察—判断—修改—对账—冻结”这样的推荐方法，以及
删除、槽位、样式和视觉判断标准。hash 绑定、唯一性校验、原子发布、固定内容保护和源
内容覆盖由 Tool/App 与测试强制。

完整 Tool schema 和错误码通过 Claude Agent SDK 注册给 Agent。Skill 可以点名稳定领域
Tool，说明其责任边界和 Agent 应如何使用结果，但不复制字段手册或 Bash 命令。references
只展开主文件不宜完整承载、但仍属于当前任务操作手册的判断方法。

## 2. 批准的领域 Skill

目标架构维护两个用户目标型 Skill：

| Skill | 用户目标 | 主要产物 |
|---|---|---|
| `docfit-school-extract` | 把当前任务学校材料整理成可安全填写的模板 | 原子冻结模板 artifact（干净 DOCX + hash 绑定 manifest） |
| `convert-thesis` | 把学生论文内容放入合格的冻结模板产物 | 最终 DOCX、`conversion-report.json` |

模板提取可以作为独立用户目标，也可以服务当前转换任务。两个 Skill 共享通用
Knowledge，但使用按任务域注册的 Tool 面，并且只通过冻结模板产物 Interface 耦合，不要求按“先提取、
再转换”的固定顺序运行，也不要求转换端知道生产者 Skill 名称。人工或其他受控适配器
生成的产物只要通过同一合同，也可直接进入转换。
`docfit-school-extract` 不产出长期学校 Knowledge 或可自动复用的学校包；历史学校
提取资产只能作为迁移参考，新 Skill 必须按当前任务证据边界重新设计。

## 3. `docfit-school-extract`

### 3.1 目标、输入和产物

当用户要求清理学校模板、解释要求文件、识别模板槽位/固定文字/说明文字、比较模板与
文字要求，或准备可填写冻结模板时使用。输入可以包含模板 DOCX、要求 PDF/文字、官方
示例、适用范围说明和用户确认；源文件保持只读。

它不填学生内容，不从经验补造学校样式，也不发布跨任务学校资产。输出是一个原子冻结
artifact，其中包含可独立打开的干净模板、绑定精确 hash 的 manifest、逐页视觉审查和
freeze report。对下游而言这是一个产物 Interface，而不是四个可分别替换的交付物。

### 3.2 推荐操作方法

Skill 明确指导 Agent：

1. 盘点来源、冲突、缺口和不可修改的源文件；
2. 用 `template_observe` 建立不可变快照并查询全部候选、有效样式和页面证据；
3. 分类 fixed、fill、generate、repeat、conditional、manual、remove、unresolved 责任；
4. 在删除说明或示例前迁移仍需保留的格式、基数、生成和放置语义；
5. 交叉验证文字要求与模板最终有效格式，材料不能裁决的高影响冲突询问用户；
6. 选择最小安全删除模式和完整槽位语义，再由 `template_mutate` 原子执行；
7. 用 `template_compare` 对账结构变化并直接查看它返回的原生图片，由 Agent 解释结果；
8. 只把确认后的最终快照交给 `template_build` 生成 candidate；
9. 由 `template_freeze` 独立重读并发布 frozen artifact。

这是可按证据回退或重复的推荐方法，不是应用壳的固定调用图。Agent 做语义判断；Tool
做事实、执行、对账和发布。生产 Skill 不包含脚本。

### 3.3 删除、槽位与样式判断

删除必须显式选择最小安全模式：清文字保留容器、删除行内片段、删除完整容器、删除有
稳定边界的连续块、清空单元格保留网格，或解包内容控件保留内容。Tool 校验当前快照、
目标引用、expected text/fingerprint、保留容器和非目标内容；Agent 决定为什么删、删哪
个语义单元以及使用哪种模式。

每个自动槽位至少表达任务内唯一 `slot_id`、最终快照唯一 locator、内容种类
（scalar、paragraph stream 或 composite）、基数、物理边界、样式观测和 fill/generate/
repeat/conditional 责任。示例数量不是重复基数，生成对象不是缓存文字。不能唯一自动
处理的区域标为 manual；证据无法定义的责任进入 gap/unresolved。

样式判断区分命名样式、直接格式、继承链、最终有效值、文字要求、适用范围、来源、
冲突和未决属性。Tool 返回所有“标题”等文本候选及格式事实，不替 Agent 判断哪个候选
具有论文标题语义。Agent 不从历史任务、常识或样式名补值。

### 3.4 比较与完成

`template_compare` 报告 expected/unexpected changes，并根据改动风险直接返回 crop、整页、
相邻页或 contact sheet。Tool 不输出视觉 pass/fail；Agent 必须解释分页、固定内容、表格、
分节、页眉页脚和槽位容器的变化。最终审查覆盖提交 build 的精确 hash 的全部页面。

`template_build` 只能产生 candidate。只有 `template_freeze` 独立验证 package、hash、槽位
唯一性与基数、固定内容指纹、manual/gap、最终逐页审查、blocking findings、来源未变化、
引用时效和 bundle 完整性后，才能原子发布 frozen。失败时不发布，Agent 不能用最终文本
或先前 Tool 成功代替这一结果。

## 4. `convert-thesis`

### 4.1 触发与输入

当用户要求论文排版、套用学校模板、按学校要求修改格式或检查转换结果时触发。

输入通常包括：

- 只读学生论文 DOCX，作为学生内容真值来源；
- 通过合同检查的冻结干净模板及其槽位索引，作为候选文档主干与放置边界；
- 可选的学生信息和补充说明。

原始学校要求、官方示例和提取过程不是转换 Skill 的必需输入。若冻结模板产物存在
未决项或 gap，转换端只消费其显式状态并询问/报告，不重新解释原始材料，也不修改
已标记的模板固定内容。

### 4.2 规则来源

Agent 按需读取随产品发布的通用 Knowledge，获得论文格式概念、识别方法、解释原则
和通用处理模式；学校具体规则已经由冻结模板产物承载，转换 Skill 不再次推导它们。

Agent 调用 `docx_inspect` 核对冻结模板的客观结构、有效样式、固定内容和来源 hash，
并由应用壳/Tool 校验槽位索引确实绑定该快照。任务证据不得写回产品 Knowledge，也
不要求先运行另一个 Skill；`convert-thesis` 只要求输入满足产物合同。

如果产物报告来源冲突、适用范围不明、manual 区域或 gap，Agent 提出最小问题或如实
保留未执行项；不能根据文件名、历史任务或通用 Knowledge 猜测学校规则。

样式处理使用“观测—语义绑定—来源交叉验证”边界：Tool 先返回模板中命名样式、
直接格式、继承后有效值、覆盖、缺失和冲突；Agent 仅判断这些事实对应哪个语义对象。
当属性仍缺失时，Agent 不读取样式值经验表或国家标准数值表，也不自行选值；只有当前
任务明文且适用范围清楚的要求可以成为目标值，否则保留未决并说明缺口。要求与模板
有效值冲突时保留双方来源并询问或阻止无条件完成。

### 4.3 论文分析

修改前，Agent 使用 `docx_inspect` 获取高信号摘要和对象引用，并使用
`docx_render(render_intent=baseline)` 首次建立 Adobe 服务转换分页基线。`docx_render` 可以
随结果附带一张有大小限制的 contact sheet；需要指定页面、裁剪或前后比较时，Agent
再使用 `docx_visual_review` 读取同一个 `render_ref`。完整解析结果和渲染证据由 Tool
保存在任务临时目录，原始论文及其 hash 始终是学生内容真值，目标模板及其 hash 始终是
候选主干真值。渲染结果附带元素 bbox
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

### 4.4 程序强制的内容安全

目标 locator 必须唯一、文档变化后旧引用必须失效、固定内容不得被非授权修改、学生
内容不得无理由消失。这些事实由 Tool/App 的 hash、前置条件、固定内容比较和源内容
覆盖合同强制。Agent 只完成论文转换任务，不在 Skill 中维护“判断阈值”或错误状态机。

### 4.5 实现行为约束

- 先观察再修改，不凭段落序号或文件名定位；
- 始终从干净、可填写的目标模板产生候选工作副本，不以学生论文副本作为候选主干；
- 把学生内容按槽位索引放入模板区域；固定内容留在模板主干中，提取端声明已清理的
  说明文字不得由转换端重新解释或保留；
- 跨文档复制学生表格、图片、公式或连续正文时使用来源学生对象引用和目标模板锚点，
  不把旧的模板节导入兼容操作当作默认转换路线；
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

这些是实现和质量设计中的行为约束，不逐条复制进 L0 `SKILL.md`。Skill 说明转换任务；
Tool 注册信息说明完整 schema；Tool/App 和测试保证执行正确性；references 只展开模板
语义和 Word 风险，不重复确定性执行合同。

### 4.6 Tool 能力来源

Agent 从 Claude Agent SDK 注册信息获得可用 Tool 的完整输入 schema 和错误语义。Skill
可以说明稳定 Tool 的领域责任以及 Agent 如何解释其结果，不复制字段定义。当前转换五
Tool 和目标学校模板五 Tool 的确定性合同分别在 05 与实现测试中维护。

### 4.7 完成条件

只有以下事实成立时，Agent 才能报告转换完成：

- 源文件未被覆盖；
- 最终 DOCX 由目标模板工作副本构建，而不是由学生论文副本构建；
- 冻结模板与槽位索引 hash 绑定有效，所有自动槽位在该快照内唯一，manual/gap 已
  显式处理或报告；
- 模板固定内容没有被未经证据修改；
- 最终 DOCX 存在、能重新打开且 package 关系可解析；
- 学生源内容清单中每一项都已放置到明确槽位，或具有明确且可审计的不放置原因；
  支持范围内的文本、表格、图片、公式和其他关键对象没有丢失、重复或错序；
- 当前任务证据支持的关键格式和模板要求已应用；
- 必填槽位已填写，槽位占位符已按索引处理，冻结产物声明不应存在的说明文字无残留；
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

- 最终 DOCX 的实际位置；
- `conversion-report.json` 的实际位置；
- 仍需人工复核或用户补充的事项。

Knowledge 版本、模板 hash、内容覆盖、视觉/验证摘要、Provider 信息、warning、未放置项、
manual 和 gap 都写入 `conversion-report.json`，不形成额外交付产物。

## 5. 主 Agent 的可选委派契约

### 5.1 主 Agent 与 SDK 配置的责任

主 Agent 负责：

- 为什么和何时委派；
- 如何划定一个或多个分析范围；
- 选择模块化 Knowledge Package 中的哪些通用模块；
- 传递哪些当前任务证据与依赖；
- 期待什么结构化返回，以及如何把返回合并进任务结果。

Claude Agent SDK 配置只负责把安全边界落实为真实权限和上下文隔离。薄应用壳配置一个
具名 `docfit-unit-analyst`；技术上可以使用内联 `AgentDefinition`，但它不是领域
组件、专家目录或委派策略。SDK 原生 `PreToolUse` 权限钩子只允许该
`subagent_type`，拒绝 SDK 内置 `general-purpose` 和未知类型；普通
`can_use_tool` 回调不被当作 `Agent` 调用必经边界。

### 5.2 委派考虑因素

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
应用壳把当前产品包交给主 Agent；主 Agent 选择本次委派所需模块。由于当前 Python
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
当前转换五个 `docx_*` Tool 仍是证据绑定、可验证的文档操作路线；学校模板目标运行由
五个 `template_*` Tool 承担对应权威边界。这不是对受信任主 Agent 的文件系统 sandbox。

## 6. 当前任务学校材料

学校模板、PDF/文字要求、官方示例、适用范围和人工确认都属于当前任务输入。
学校提取 Skill 可以据此形成冻结模板和槽位索引；结构化分析、来源 hash、冲突记录和
精确参数写入索引或作为工作数据保存。转换 Skill 只消费通过合同的
冻结模板产物，不把这些原始材料重新纳入规则解释。无论路径位于何处，这些内容仍是
任务证据或中间产物，不是 Knowledge Package，也不得自动晋升到产品 Knowledge。

处理原则：

- Tool 确定性提取模板结构、有效样式、可见对象、槽位和来源 hash；
- Agent 使用通用 Knowledge 解释证据、绑定语义角色并形成仅对当前任务有效的
  学校规则，但不生成未观测的样式值；
- 缺失属性保持未决；只有当前任务明确提供且适用范围清楚的要求值才能成为目标值；
- 文字要求与模板表现冲突时保留两份证据并要求当前用户确认；
- 字体、字号、行距、页边距、编号和节属性可以规范化为当前 Tool 调用参数，
  但不得保存到长期 `format-profile.yaml`；
- 无法确认的事实保持不确定，不从历史任务补齐；
- 任务结束后不自动复制模板、规则、参数或确认结论到产品 Knowledge。

如果同类处理方法在多个任务反复成立，只能把去除学校名称、数值和固定文案后的
通用概念、识别方法、解释原则或处理模式作为产品 Knowledge 的候选变更；该变更
仍需独立评审、测试并随新的产品版本发布。

## 7. 模板责任模型

`docfit-school-extract` 不只给可见文字分类，而是把学校材料中的具体表达转换为模板责任：

```text
fixed        学校拥有、后续不得随意改写的内容和结构
fill         等待后续内容进入的稳定接口
generate     由标题、题注或其他关系生成的区域
repeat       承接可变数量同构内容的区域
conditional  只在已记录条件成立时出现的区域
manual       签字、盖章、审批等人工责任
remove       不进入成稿、但删除前必须先迁移其有效语义的示例或说明
unresolved   当前材料或能力不足以可靠解释的内容
```

这是一种通用处理模型，不是阶段或固定分类器。同一区域可以组合多种责任；例如表单可以
同时具有 fixed、fill、conditional 和 manual 部分。颜色、括号、下划线、空白或源文件中
出现了几个示例，都不能单独决定责任。

无法可靠解释时保留原文或结构并进入 unresolved，不猜测性删除。说明和示例只有在其
承载的结构、格式、顺序、必填性和生成规则已经迁移后才能进入 remove。`convert-thesis`
不重新分类学校模板，只消费冻结模板索引已经表达的责任。

## 8. Skill 内容组织

信息按消费成本分为四层：L0 是 `SKILL.md` 中的任务、输入输出、推荐操作方法、常用判断
标准和高频风险；L1 是同目录 `references/` 中展开的模板语义、删除/槽位、样式交叉验证
和视觉回归方法；
L2 是随产品发布、跨 Skill 使用的通用 Knowledge；L3 是当前任务材料、冻结模板产物和
Tool 证据。下层可以更具体，但不得把学校事实向上晋升，也不得把 Tool 注册说明或机器
不变量重复进 Skill。

```text
<skill>/
├── SKILL.md
└── references/
    └── ...           # 按可复用问题机制组织，由 SKILL.md 直接指向
```

Tool 实现不复制到 Skill。两个领域 Skill 的 references 保存任务操作指引；Knowledge Package
保存跨 Skill、跨学校和跨任务成立的领域概念与方法。学校事实只留在当前任务证据中。

Knowledge 模块不伪装成额外的用户 Skill，也不建立 cover/toc/body 等 Subagent 专家
目录。模块可以按消费场景演进；同一个 `docfit-unit-analyst` 接收本次真正需要的模块。
场景经验也不保存可直接套用的样式值、国家标准数值表或通用缺省补全表；
这些值不进入 Agent 的 Skill/Knowledge 上下文。

适合进入 references 的内容必须同时满足：它会在同一 Skill 的多类任务中复用；主文件
完整展开会显著增加负担；它仍然是操作指引而不是跨 Skill Knowledge 或 Tool 实现。
reference 应围绕问题机制组织，例如模板内容责任如何表达、删除前如何迁移语义、Word
有效格式如何与文字要求交叉验证、视觉变化如何解释。封面、目录、声明等可以作为这些机制的
示例，但不各自形成默认文件和固定处理路线。

每份 Skill 只引用自己的 references，不跨目录引用另一份 Skill。文件较少时由
`SKILL.md` 直接指向；只有真实文件数量和导航收益证明需要时才增加 index。契约测试验证
所有引用存在和两棵 Skill 的领域隔离，不把某种目录形状永久写死。

`docfit-school-extract` 的生产目录不包含可执行脚本。决定允许哪些文档变化、检查误伤、
编译 artifact 或决定冻结的逻辑属于有类型 Tool 合同。开发期原型、fixture 生成和人工
调试脚本可以位于开发/测试目录，但不向 Agent 暴露，不能成为生产步骤或合同真值。

冻结模板 Interface 的候选 Skill 采用以下目标 reference 树；它是
`docs/plans/docfit-school-extract-v2.md` 中的实施草案，也不表示当前
`.claude/skills/docfit-school-extract/**` 已经切换：

```text
docfit-school-extract/
├── SKILL.md
└── references/
    ├── template-semantics.md
    ├── deletion-and-slot-decisions.md
    ├── style-reconciliation.md
    └── visual-regression.md
```

Skill 正文说明 Agent 必须理解和判断的完成语义；hash、locator、原子发布和固定内容
保护由 Tool/App 强制。完整字段 schema 不复制到 Skill。

## 9. Skill 评审问题

- Agent 是否清楚任务、输入和稳定产物边界，而没有被要求维护运行时状态？
- 当前用户模板、学校规则或精确参数是否被写入长期 Knowledge？
- 学校事实是否被误写进通用 Skill？
- OOXML 细节是否泄漏到 Skill？
- 是否出现固定阶段、状态或 checkpoint？
- 学校模板生产是否只通过五个 `template_*` Tool，而没有退回生产脚本或一个自动做完
  全部语义判断的大 Tool？
- 是否在修改前、布局变化后和最终交付前使用了当前图片证据，而不是只看结构数据或旧截图？
- 是否错误地把页码当成稳定编辑身份，或把 Adobe 与 CLI 的同页码当成同一内容范围？
- Adobe 转换是否遵守缓存和调用额度，只用于首次 baseline 与必要的 candidate verification？
- Agent 是否只表达 `render_intent`，而没有选择具体后端或要求跨职责回退？
- OfficeCLI 与 Adobe PDF Services API 是否仍只承担各自固定职责，没有在 Skill 中出现通用 Provider 平台逻辑？
- 学生内容是否仍以原始 DOCX 和 hash 为真值？
- Skill 是否说明了稳定 Tool 的职责和 Agent 如何解释结果，同时避免复制字段级 schema？
- 新增 Knowledge 是否已经去除学校值，并有多个任务或跨学校 Eval 支持其通用性？
- 委派原因、范围、Knowledge 选择和返回解释是否仍由主 Agent 负责？
- Skill 是否要求 Agent 获取模板可观测的全部样式事实，同时禁止它读取经验值或
  杜撰缺失值？
- 应用壳是否只落实 `docfit-unit-analyst` 的上下文隔离和最小权限，而没有识别论文
  单元或编排调用？
- 是否误建了多个单元专家、固定阈值、强制委派映射或动态
  `AgentDefinition.skills` 的虚假契约？
- Subagent 是否只分析，所有 render、edit、validate、用户询问和跨范围合并是否仍由
  主 Agent 负责？
- `SKILL.md` 是否用稳定任务模型解释复杂模板，而没有按输入部件照抄处理动作？
- references 是否按可复用问题机制组织、引用真实存在，并保持本 Skill 的领域隔离？
- 从真实复盘吸收的内容是否已经去除学校名称、具体数值和一次性修复配方？
- 两个 Skill 是否只通过冻结模板产物 Interface 耦合，而没有互相点名、要求固定调用
  顺序或共享隐藏状态？
- 每个自动槽位是否在冻结模板 hash 内唯一，manual/gap 是否显式，快照变化后旧 locator
  是否失效？
- hash、唯一定位、内容覆盖和原子发布是否全部由 Tool 硬门保证，同时 Skill 清楚说明
  Agent 需要完成的语义判断？
- 转换是否闭合学生源内容清单，并对每个不放置项给出理由，而不是只检查最终文档中
  看得见的内容？

如果 Skill 需要复杂状态图才能解释，说明设计已经偏离 Agent-first 架构。
