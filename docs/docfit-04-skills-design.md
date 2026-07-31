# DocFit Skill 设计（04）

> 状态：设计说明
> 日期：2026-07-30
> 原则：Skill 是 Agent 的领域操作手册，不是工作流定义。

## 1. Skill 在架构中的位置

Skill 是 DocFit 最重要、迭代最频繁的产品资产。它把论文处理经验交给 Claude Agent，但把执行权留给 Agent SDK 与 Agent。

一个好的 Skill 回答：

- 用户想完成什么；
- 开始前要确认什么；
- 应读取哪些 Knowledge；
- 可使用哪些 Tools；
- 哪些判断可以自主完成；
- 哪些情况应回看、重试或询问用户；
- 什么结果可以称为完成；
- 哪些行为绝对禁止。

Skill 不定义：

- 固定阶段 ID；
- 阶段输入输出协议；
- 状态转换；
- checkpoint；
- 任务队列；
- 学校具体字号、页边距和固定文案；
- OOXML 实现细节。

## 2. 两个 Skill 的边界

DocFit 只维护两个业务目标型 Skill：

| Skill | 面向的用户目标 | 主要产物 |
|---|---|---|
| `prepare-school-template` | 把学校官方材料建设成以后可重复使用的格式资产 | School Knowledge Package |
| `convert-thesis` | 把当前学生论文转换成目标格式 | 最终 DOCX、预览与验证结果 |

三层职责保持分开：

| 层 | 职责 |
|---|---|
| Skill | 描述用户目标、触发条件、判断边界和最终输出 |
| 共享能力 | 把模板证据解释为统一的 `SchoolKnowledgeDraft` |
| Tool / 内部模块 | 确定性读取文件、提取客观结构、计算 digest 和校验 schema |

“学生论文内容提取”通常不是独立用户目标，而是 `convert-thesis` 内部的一次只读分析。它由 `docx_inspect` 等 Tool 完成，产生任务级内容清单，不单独设计成 Skill。

两个 Skill：

- 不互相调用；
- 不复制模板解析或 DOCX 分析实现；
- 共用模板提取协议、`SchoolKnowledgeDraft` schema、Tools、格式规则定义和必要参考资料；
- 不定义固定阶段、任务队列或 checkpoint。

每个 Skill 都要明确两层输出：

1. **文件产物**：供用户、后续任务或人工复核使用；
2. **Agent 最终回复**：说明实际生成了什么、依据是什么、还存在什么问题。

## 3. `prepare-school-template`

### 3.1 触发与输入

当用户要求导入新学校、整理官方模板、提取学校格式要求或更新学校资料时触发。

输入可以包括：

- 学校官方 DOCX 模板；
- PDF、网页或文字版格式要求；
- 学校提供的示例论文；
- 学校、学历层次、专业范围、语言、学年或模板版本；
- 用户对来源优先级和冲突的补充说明。

### 3.2 文件产物

产出一个可供后续论文转换重复使用的 School Knowledge Package，逻辑内容包括：

```text
knowledge draft          共享模板提取能力生成的 SchoolKnowledgeDraft
manifest                 学校、版本、适用范围、来源与 content digest
school guide             面向 Agent 的规则、判断说明和已确认例外
format profile           Tool 需要的确定性格式参数
template                 可复用模板；只有来源和结构足够可靠时提供
sources                  原始来源及各自 hash
extraction report        来源冲突、未确认项、Tool 警告和验证证据
review record            必要人工确认及其依据
```

具体文件名和存储方式由 Knowledge 设计决定。Skill 不把学校具体规则复制进自己的 `SKILL.md`。

### 3.3 关键判断

- 模板证据到规则草稿的解释必须使用共享模板提取协议，不在本 Skill 中重写；
- 保存每条重要学校规则的来源，不把常识伪装成学校要求；
- 同时检查文字要求与模板实际格式，发生冲突时保留两份证据；
- 只把确定性参数写入 format profile，解释性规则保留在 school guide；
- 区分模板中最终保留的文字、条件文字、内容槽位和仅供填写者阅读的说明；
- 无法确认的规则进入 extraction report，不猜测性固化；
- 用合成论文验证 Knowledge 与模板能够被 Tool 消费，但不把单个样本当成学校全部规则。

模板文字通常分为：

```text
fixed_content       最终必须保留的学校固定文字
conditional_content 根据学生类型决定是否出现
slot_placeholder    等待学生内容填入的位置
format_instruction  只用于说明格式、最终应清理的文字
```

### 3.4 完成条件

只有以下条件满足时，Agent 才能说明模板提取已经完成：

- 来源文件、来源 hash、适用范围和 Knowledge digest 已记录；
- 已提取的规则能够追溯到来源；
- 模板可重新打开，结构检查没有未处理的严重错误；
- 已知冲突、不支持对象和待人工确认项已明确记录；
- 需要人工确认的规则已经确认并留下依据；
- 没有把未经确认的推断写成确定学校规则。

存在阻断性来源冲突或必要人工确认尚未完成时，可以交付 Draft 和提取报告，但不能声称已经形成可复用的正式 School Knowledge Package。

### 3.5 Agent 最终回复

最终回复必须包括：

- 识别到的学校、学历、专业范围、语言、学年和版本；
- Knowledge 包及可复用模板的实际位置；
- 输入 Draft 的 source digest；
- 使用了哪些官方来源；
- 已提取并验证了哪些规则类别；
- 已完成人工确认的规则及仍待确认项；
- 来源冲突、不支持能力和待人工确认项；
- 当前材料是否足以用于论文转换，以及判断依据。

## 4. `convert-thesis`

### 4.1 触发与输入

当用户要求套用学校模板、按学校要求排版或生成最终论文时触发。

输入通常包括：

- 原始学生论文 DOCX；
- 学校标识以及可用的 School Knowledge Package；或者用户直接提供的模板和要求文件；
- 可选的学生信息和用户补充说明。

用户只要求完成当前论文转换时，即使同时上传模板和论文，也只加载 `convert-thesis`。Agent 使用 Tool 提取本次任务需要的模板规则和论文内容清单，不要求先运行 `prepare-school-template`。

用户提供模板时，`convert-thesis` 使用与 `prepare-school-template` 完全相同的共享模板提取协议，生成 `SchoolKnowledgeDraft`。这个 Draft 是任务级临时 Knowledge：

- 保留模板来源和 hash；
- 只服务当前转换；
- 不自动注册成长期学校资产；
- 不宣称已经完成学校级来源审核和复用验证。

这里的“临时 Knowledge”只表示 Agent 在本次上下文中使用的规则证据，不是新增的架构组件，也不是正式 School Knowledge Package。

如果用户模板的 source digest 与已有 School Knowledge Package 的来源完全匹配，并且适用范围一致，可以直接复用已有 Knowledge；否则使用新的任务级 Draft，不自动更新正式资产。

只有当用户明确要求“把这个学校加入 DocFit、供以后重复使用”时，才触发 `prepare-school-template`。

### 4.2 内部分析数据

`convert-thesis` 在修改前使用 Tool 生成任务级分析数据，例如：

```yaml
source:
  document_sha256: ...
school_rules:
  kind: draft
  draft:
    source_digest: ...
    rules: [...]
    conflicts: [...]
    uncertainties: [...]
thesis_content:
  student_fields: ...
  sections: [...]
  object_refs: [...]
  unsupported_objects: [...]
  unresolved_boundaries: [...]
```

这些数据用于保护学生内容、定位对象和应用当前模板，不是独立 Skill 的最终产物，也不替代原始 DOCX。原始论文和 `document_sha256` 始终是学生内容真值。

分析不得把 DOCX 降级成纯文本后丢弃表格、图片、公式、脚注、域、书签或节关系。含真实学生内容的分析数据属于敏感任务数据，不进入公开仓库或公开 Eval。

### 4.3 文件产物

在不覆盖源文件、不静默丢失学生内容的前提下，生成：

- 最终 DOCX；
- 可用时的 PDF 和逐页预览；
- validation 结果；
- 修改摘要以及仍需人工复核的问题。

最终 DOCX 是交付产物；任务级分析、Knowledge、Tool 日志和中间工作副本不是最终论文。

### 4.4 关键判断

- 学校具体格式来自适用的正式 Knowledge，或共享模板提取协议生成的任务级 `SchoolKnowledgeDraft`；
- 学生内容只从当前 hash 匹配的原始论文和任务级分析读取；
- 优先在原论文上做受控格式修改；确需套用模板时，按对象引用迁移并验证文本、表格、图片和公式；
- 先观察再修改，不凭文件名或段落序号猜测；
- 能局部修改时不整体重建；
- 无法可靠定位时重新 inspect，不扩大修改范围；
- 学生文字与学校固定文字冲突时，优先保护学生内容并询问；
- 渲染结果与结构检查冲突时，两者都要呈现，不静默选择；
- 目录和页码依赖具体 Word 渲染时，明确人工复核要求。

### 4.5 建议处理思路

Skill 应把下面内容写成可调整的建议，而不是必须逐步提交的流程：

1. 核对源论文，并对用户模板计算 source digest，检查是否精确匹配适用的正式 Knowledge。
2. 未命中正式 Knowledge 时，使用共享模板提取协议生成任务级 `SchoolKnowledgeDraft`；同时用 Tool 分析论文结构和内容对象。
3. 选择对当前文档破坏最小的修改或模板迁移方式。
4. 执行小范围、带前置条件且原子发布的修改。
5. 重新 inspect，并对源论文与最终论文做内容和对象覆盖检查。
6. 渲染并检查封面、目录、跨页表格、参考文献等高风险页面。
7. 运行 validation，处理可恢复问题，记录仍需人工复核的证据。

Agent 可以根据真实文档跳过、重复或调整这些动作。

### 4.6 必须询问或停止

以下情况不应靠 Agent 猜测：

- 找不到适用的学校 Knowledge，且用户没有提供足够模板或要求材料；
- 任务级分析引用与源论文 hash 不匹配；
- 学校来源互相冲突且 Knowledge 未给出结论；
- 无法确认正文边界并可能导致内容删除；
- 出现 Tool 未支持的可见对象；
- 必填学生信息缺失；
- 字体或渲染环境使分页证据不可信；
- 修改工具报告定位歧义或结构损坏；
- 用户要求覆盖原文件。

能通过最小澄清继续时提问；存在内容损坏风险时停止修改并说明。

### 4.7 完成条件

只有以下条件满足时，Agent 才能报告最终论文转换完成：

- 源文件未被覆盖；
- 最终 DOCX 存在且能重新打开；
- 任务级内容清单中的支持对象已全部保留或迁移，并明确说明例外；
- 关键学生内容检查未发现丢失、重复或错序；
- 已应用目标学校的关键格式和模板要求；
- 必填占位符和模板说明文字已处理；
- 能生成时，预览文件已生成；
- 严重 Tool 错误已解决；
- 所有交付产物都来自 `committed: true` 且必要后置检查通过的 Tool 调用；
- 未解决的不确定项已明确告诉用户。

### 4.8 Agent 最终回复

最终回复必须包括：

- 最终 DOCX 的实际位置；
- PDF 或页面预览的实际位置；没有生成时说明原因；
- 使用的正式 Knowledge 标识、版本、适用范围和 content digest；或者本次 Draft 的 source digest；
- 原始论文 hash，以及任务级内容分析的覆盖摘要；
- validation 摘要：源文件、内容保留、学校规则、占位符、结构和渲染；
- Tool provider、重要 warning 和 `verification_gap`；
- 仍需人工复核或用户补充的事项；
- 未完成时，明确区分 Agent 判断问题、输入问题、Tool 问题和环境问题。

## 5. 共享模板提取能力与 Tool 失败恢复

两个 Skill 共同使用：

- 共享模板提取协议：Agent 如何从模板证据推导学校规则；
- `SchoolKnowledgeDraft` schema：规则、来源引用、冲突和不确定项的统一结构；
- `docx_inspect`：通过不同 `focus` 分析模板规则或学生论文内容；
- `docx_edit`、`docx_render`、`docx_validate`；
- Draft validator、source-ref checker 和 digest calculator；
- School Knowledge schema 和格式规则定义；
- 模板文字分类、内容保护与渲染复核方法。

共享逻辑不复制进两个 Skill，也不要求一个 Skill 调用另一个 Skill。

```text
模板与要求文件
      ↓
客观证据提取（Tool / 内部模块）
      ↓
共享模板提取协议（Agent）
      ↓
SchoolKnowledgeDraft
      ├─ prepare-school-template：适用范围 + 版本 + 审核 → 正式 Knowledge
      └─ convert-thesis：限定在当前任务 → 最终论文
```

逻辑资产可以组织为：

```text
shared/template-extraction-protocol.md
shared/schemas/school-knowledge-draft.schema.json
internal/template-evidence-extractor
internal/knowledge-draft-validator
internal/knowledge-digest-calculator
```

具体目录遵循实现环境，但只能有一个权威版本。前三类确定性模块可以由 Tool adapter 或普通内部代码实现，不因为“共享”就自动成为新的 Agent Tool。

Agent 必须把 Tool 结果视为可验证证据，而不是只判断“有没有返回文件”：

- `status: ok` 表示调用正常完成；对写入 Tool，还必须确认 `committed: true` 和必要后置检查；
- `status: needs_input` 时，优先使用已有信息修正调用；只有缺少领域事实时才询问用户；
- `failure.origin: request` 或 stale ref 时，读取 schema、重新 inspect 并生成新引用；
- `failure.origin: document` 时，缩小操作范围；可能损坏内容时停止并询问；
- `failure.origin: engine` 或 `environment` 时，仅在 `retryable: true` 且调用方式有所调整时重试，可用时切换 provider；
- `failure.origin: adapter` 或 `postcondition` 时，不消费该产物；可切换经过验证的 provider，否则停止并报告 Tool 问题；
- 相同 `code` 在没有新证据或新处理方式时再次出现，不继续循环重试。

Agent 最终回复应区分“输入需要用户处理”“Agent 无法确定”“Tool 或运行环境失败”，不能把它们统一描述成处理失败。

## 6. Skill 组成

```text
<skill>/
├── SKILL.md
├── references/       # 按需加载的通用方法和示例
└── scripts/          # 仅在确有轻量辅助脚本时存在
```

Skill 的实际目录和发现配置遵循所采用的 Claude Agent SDK 集成方式，不在领域设计中固定。

Tool 实现不复制到 Skill。Skill 中的脚本只做本 Skill 特有的轻量准备；通用 DOCX 能力由 Tool 契约统一暴露，底层可以通过适配层复用开源 MCP、CLI 或库。

Knowledge 不放在 references 中。references 是通用方法；学校事实进入 Knowledge。

## 7. 写作规范

1. `description` 写清触发条件，让 Agent 能正确发现 Skill。
2. 正文保持短小，只保留高频且重要的指引。
3. 复杂背景、示例和陷阱按需放入 references。
4. 使用目标、原则和检查清单，不使用固定状态图。
5. 每条规则尽量能追溯到真实样本或学校来源。
6. 明确允许 Agent 适应的范围和不可突破的底线。
7. Tool 名称和用途写清楚，参数细节留在 Tool schema。
8. 学校具体要求只通过 Knowledge 获取。
9. 发现重复失败时先补 Eval，再修改 Skill。
10. 删除已经由 Tool 前置条件或 SDK 能力保证的重复说明。

## 8. Skill 评审问题

- Agent 是否知道目标，而不只是知道步骤？
- 指引是否给 Agent 留出适应文档差异的空间？
- 学校事实是否被误写进通用 Skill？
- OOXML 细节是否泄漏到 Skill？
- 是否出现固定阶段、状态或 checkpoint 设计？
- 文件产物与 Agent 最终回复是否分别明确？
- 学生内容分析是否仍以原始 DOCX 和 hash 为内容真值，而不是有损文本副本？
- 当前用户模板是否被误注册成未经审核的长期学校 Knowledge？
- 失败后应该改 Skill、Knowledge 还是 Tool，边界是否清楚？
- 这条新增规则是否有真实样本或 Eval 支持？

如果 Skill 需要一张复杂状态图才能解释，应先检查是否已经把 Agent 任务重新设计成工作流。
