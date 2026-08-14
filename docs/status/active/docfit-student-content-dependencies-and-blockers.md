# DocFit 三模块责任、产品原则与当前修复状态

> 本文档是当前产品责任、真实状态、修复目标和验收口径的总入口。
> 最近更新：2026-08-12。当前总状态：`FAIL`，尚未形成可交付的最终论文。

## 0. 责任划分（先于实现细节）

DocFit 当前只有三个产品模块：

```text
学校模板与要求 ──→ 模板生成模块 ──┐
                                  ├──→ 最终内容填写模块 ──→ 一份最终 Word
学生原始论文 ────→ 用户内容提取模块 ─┘
```

| 模块 | 唯一责任 | 不承担的责任 |
|---|---|---|
| **模板生成模块** | 忠实保留学校模板；说明学校提供了哪些结构、填写位置、规则和样式，以及缺少哪些样式 | 不读取学生论文；不注入通用兜底；不对最终论文视觉效果负责 |
| **用户内容提取模块** | 把学生原始论文转换为忠实、无损、有层级、有顺序、可溯源的 Student Content Model | 不读取学校模板；不决定目标位置和目标样式；不修改、归一化或重排学生正文 |
| **最终内容填写模块** | 消费前两个模块结果；在写入前统一选择并物化学校样式或通用兜底；完成放置、机械复制、目录分页、缺失处理和最终质量验收 | 不重新识别学校要求；不重新识别学生标题、段落、图表、图注、表注或公式 |

Placement、样式选择、目录更新、内容审计、渲染和 Eval 都是上述模块的内部能力或验收手段，
不是额外产品模块。

## 1. 产品原则（所有模块共同遵守）

1. **用户只收到一份最终 Word。** 模板、Student Content Model、Contract、PDF、页图和运行报告
   都是内部产物，不是并列交付物。
2. **学校模板是最终 Word 的主干，学生论文是只读内容来源。** 不覆盖学生原文件，也不从学生
   论文副本反向伪造学校模板。
3. **不得删除学校模板中的完整章节、页面、表格或附表。** 即使学校不强制填写，也要保留内容，
   并在对应填写区域标注统一文案“本项无需填写”。
4. **学校任务书、开题报告、评审表不得作为独立交付物。** 它们必须保留在同一份最终 Word 的
   原有组成和顺序中。
5. **必填缺失和非必填缺失必须区分。** 必填内容没有可靠来源时返回字段级 `NEEDS_INPUT`；只有
   非必填或明确不适用的内容才能标注“本项无需填写”。
6. **学生内容不得静默丢失、猜测或未授权改写。** 无法可靠识别的内容必须进入明确的复核或不支持
   状态，不能为了表面完整而丢弃。
7. **正文当前不支持重排。** 提取、放置和填写都必须保持学生原始阅读顺序；简化架构不能降低
   内容、样式、分页、对象保留和逐页视觉质量。
8. **模板生成当前不是独立可手填模板产品。** 因而只报告学校样式事实和缺口，不提前补通用兜底；
   通用兜底只由最终内容填写模块根据本次学生内容统一选择和物化。

如果未来将模板生成定义为可脱离 DocFit 手工填写的完整模板产品，才另行批准其发布时兜底责任。

## 2. 当前真实状态

| 模块 | 当前状态 | 已有事实 | 当前关闭条件 |
|---|---|---|---|
| 模板生成 | `FAIL` | 已有模板检查、对象编辑和后续行为修订 | 在真实学校模板上有界完成，忠实保留全部结构，并输出可直接消费的学校规则、槽位和样式事实 |
| 用户内容提取 | `STUDENT_002_QUALITY_AND_PERFORMANCE_PASSED` | Student Content Model v2 在真实 API 下保持 Gold r5 的 188/188 语义一致和 8/8 维度通过；编排优化后墙钟从 29 分 17 秒降至 2 分 05.82 秒 | 扩展 Student 001/003 Gold 验证跨文档泛化；此前 Template Workspace 合同测试与 `preceding_landmarks` 实现不同步的问题已经关闭，不再作为本模块或当前工作区的 blocker |
| 最终内容填写 | `FAIL`，底层能力部分可用 | 已证明模板主干写入和图片、表格、公式运输能力 | 消费新 `items` 合同，完成实际角色样式选择/物化、必填补值、非填写标注、目录分页和最终逐页验收 |

最新完整真实产品运行仍是
`temp/e2e-real-fallback-v1-20260811/E2E-REPORT.md`，结论为 `FAIL`。旧的“15 个标量字段 +
4 个连续段”的 v2 提取证明只能作为历史诊断证据；它已被新合同替代，不能证明当前提取模块通过。

## 3. 用户内容提取模块：正式合同

### 3.1 数据流

```text
学生 DOCX
  → 确定性 Word 事实提取
  → 有序、无语义的 Source Content Items
  → Agent 逐项语义标注与关系识别
  → 确定性验证、层级组装和覆盖率闭合
  → Student Content Model
  → 模块级验收
```

这是提取模块内部的四段式流水线，不是四个产品模块。模板前处理与学生内容提取可以共享中立的
Word 文档事实能力，例如文档快照、对象图和视觉证据；不得复用模板语义、模板过滤、样式捕获、
模板专用工作流；只可共享稳定 `docx_*` Tool 的中立 Word 事实/编辑/视觉能力。

### 3.2 Registry 的边界

Content Field Registry 是只读语义词典，只向提取模块提供：

- `field_id`：这类内容的稳定名称；
- `label` / `meaning`：这类内容的语义；
- `content_type`：允许绑定的内容类型。

Registry 不保存学生内容，不决定学生内容顺序，不决定字段是否出现、是否必填、是否缺失、是否
不适用，也不决定内容在目标模板中的位置。提取 Agent 看不到模板和 Fill Contract。

### 3.3 `items` 与 `field_results`

`items` 是学生内容实例和顺序的唯一真相源：

- 每个可见文本、标题、段落、图片、图标题、表格、表标题、表注、公式等都是一个内容实例；
- 每个实例保留稳定 `content_id`、Registry `field_id`、物理类型、源对象、源 locator、运输对象、
  原始顺序、父子关系、语义关系和置信证据；
- 正文按 `source_order.block + source_order.inline` 严格保持学生原始阅读顺序；
- 任何分类都无权改变 `items` 顺序。

`field_results` 只是从 `items` 派生的索引摘要：

- 回答出现了哪些 Registry 类型、各有多少实例、状态是什么、对应哪些 `content_id`；
- 不保存内容正文，不承担前后顺序，不为 Registry 中未出现的字段制造 `missing` 行；
- 删除并重建 `field_results` 不得改变正式内容模型。

非正文内容（封面字段、摘要、关键词等）同样保留源位置用于追溯，但最终位置由 `field_id` 与模板
槽连接。正文没有目标侧重排规则，最终填写只能按 `items` 原顺序运输。

### 3.4 Agent 与确定性代码的权限

Agent 只能对预先生成的每个 `source_content_id` 返回：分类状态、`field_id`、置信度、说明
以及显式语义关系。语义识别可在模块内部按源顺序切成小批次，并携带少量相邻只读上下文；批次
只降低单次模型负担，不产生第二套顺序。结构化输出中不存在顺序、连续范围或正文序号字段，最终
确定性合并必须证明全量 ID 集合完全相等且无重复，因此 Agent 数组顺序不会成为内容顺序。

确定性后处理负责：

1. 校验标注键与源内容实例一一相等；
2. 校验 `field_id` 存在且 Registry 类型与物理类型兼容；
3. 只从源事实层复制文本值，Agent 无权生成或改写学生内容；
4. 原样复制唯一 `source_order`，生成稳定正式 `content_id`；
5. 根据已标注标题层级组装父子关系，但不改变顺序；
6. 校验关系闭包并把源 ID 转为正式内容 ID；
7. 从 `items` 派生 `field_results`，对全部源对象完成映射、依赖、布局或不支持记账；
8. 只有全部语义和覆盖率关闭后才返回 `READY`。

Claude Agent SDK 继续拥有单一 Agent loop，应用通过 SDK 原生 JSON Schema structured output 约束
返回形态；DocFit 只实现论文领域合同和确定性验证。官方依据：
[Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) 与
[Structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)。

## 4. 本轮代码状态与验收

### 4.1 已实现

- `src/docfit/content/student.py`：从中立 inspection 生成 Source Inventory v2 和不可变有序内容实例；
- `src/docfit/content/extraction.py`：v3 逐项标注 Schema、Registry 精简词典、确定性 Student Content
  Model v2 组装、层级、关系、字段摘要和覆盖率；
- `src/docfit/app/student_content_fill.py`：独立提取请求/准备/运行/恢复接口，以及预算分批、有界并发、
  hash 绑定批次检查点和 task-local 轻量 SDK 运行时；Agent 任务目录只含学生 DOCX 与 Registry，
  不含模板或 Fill Contract；
- `src/docfit/app/sdk_execution.py`：模板生成与学生提取共同使用的 SDK metadata-only timing/usage 事实；
  不包含任一模块的领域语义或学生正文；
- `src/docfit/content/placement.py` 与 `fill.py`：直接按 `items` 原顺序去重运输 Word 顶层对象，并把
  内容语义和关系随 Fill evidence 传给下游；
- `src/docfit/content/presentation_roles.py`、`projection.py`、`style_application.py`：消费正式
  `field_id` 和关系，不再通过标题、图注、表注正则重新识别学生内容。

本轮采用清晰的新合同，不保留旧 `fields + segments` 兼容层；当前没有真实外部消费者要求承担这项
迁移复杂度。

### 4.2 模块验收门

用户内容提取只有同时满足以下条件才可升级为 `PASSED`：

1. **忠实性：** 所有可见内容和复杂对象都有内容实例或明确的依赖/布局/不支持记账；
2. **无损性：** 源文字、图片、表格、公式和关系没有静默丢失或推断补写；
3. **顺序性：** `items` 与源 Word 结构顺序完全一致，Agent 输出和 `field_results` 均不能改变顺序；
4. **层级性：** 标题、正文及图表/图注等关系闭合，所有父子/语义引用都指向现存 `content_id`；
5. **可追溯性：** 每个实例绑定源 hash、对象 ID、locator 和运输对象；文本值可回查原文；
6. **模块独立：** Agent 无模板、Fill Contract、目标槽和目标样式访问面；
7. **直接可消费：** 最终填写只做放置、样式选择和物化，不再识别学生内容；
8. **工程回归：** Ruff、Mypy、模块单测、真实 DOCX 集成和全仓测试全部通过；
9. **真实证明：** 至少一次新的真实 v3 Agent 运行达到 `READY`，并与人工 Gold 做模块级对比；
   同源重复运行和更多样本用于后续稳定性与泛化验收。

### 4.3 Student 002 真实 API 与 Gold 验收

2026-08-12 使用 Student 002 原始 DOCX 发起完整真实 API 提取。Gold 从未进入 Agent prompt，也没有
用 Gold 回放替代模型输出；Gold 只在 Student Content Model 生成后由正式 Eval 离线比较。

| 证据 | 结果 |
|---|---|
| 来源绑定 | 源 DOCX SHA-256 `fc39ac02efd152ddf609199615256393e3077b49629e1cca48e1f437b2e44a9b`；Registry v0.3 SHA-256 `a6df179b7a4112672b275289df2e43870ca9a363cb3e46b74a77e9921cff570b` |
| 真实 Agent 运行 | MiniMax + Kimi；12/12 批次、12 个 SDK session 均有 `StructuredOutput` 证据 |
| 中立事实层 | 371 个源对象；191 个有序内容实例：180 文本、6 图片、4 公式、1 表格 |
| Gold | `student-002.extraction` revision `2026-08-12.r5`；188 个源绑定语义实例，另含 1 个无源结构根 |
| Actual | `READY`；191 个 `items`，其中 188 个 `classified`、3 个 `layout_only` |
| 正式 Eval | `PASS`；来源/版本、源覆盖、字段语义、原文值、实例分组、内容顺序、层级关系、真实运行证据 8/8 全部通过 |

本轮确定性后处理只做两类不改变内容和顺序的闭合：同一文档中强共识编号形态的孤立标题层级
偏差校正，以及按不可变源顺序绑定相邻的图/表题注。它不读取模板、不使用 Gold 规则、不重排正文。

旧质量基线工程回归：`ruff check src tests` 通过；Mypy `83 source files` 通过；全仓测试 `486 passed`
（1 条既有 Starlette/httpx 弃用警告）。优化后回归，以及历史 Template Workspace 返回合同同步问题的
当前结论见 4.4.4。

证据目录：
`temp/student-content-extraction-eval-20260812/student-002-actual-live-v3/`；正式报告：
`eval-final/student-content-eval-report.md` 与 `student-content-eval-report.json`。

### 4.4 性能优化：Student 002 编排瓶颈已关闭

#### 4.4.1 结论与测量边界

优化前，Student 002 正式提取从任务目录创建到首次生成 `READY` 运行报告，共耗时
**29 分 17 秒**：

| 环节 | 当前可确认耗时 | 判断 |
|---|---:|---|
| 输入快照、Word inspection、Source Inventory | 约 8 秒 | 正常，不是当前主要瓶颈 |
| 12 批 prompt 构建 | 本地重复测量中位数约 522 ms | 可忽略 |
| 12 批 JSON Schema 构建 | 本地重复测量中位数约 3.6 ms | 可忽略 |
| 真实 Agent 语义标注、SDK 会话、失败重试和路由切换 | 约 29 分 09 秒 | 占总耗时约 99.5%，是当前核心问题 |
| 191 个 items 的确定性校验、层级和关系组装 | 本地重复测量中位数约 6.4 ms | 可忽略 |

已知旧运行的 29 分 09 秒中包含一次约 600 秒的超时，以及首批一次 structured output 缺失后的重试。
旧证据只能精确区分完整墙钟耗时和确定性本地耗时，不能继续可靠拆分 CLI、连接、模型与 API 时间，
因为旧版没有保存 SDK `ResultMessage` 的 timing/usage。优化后已经补齐该观测合同，正式新数据见
4.4.5。

本节暂不把具体 API 服务商速度作为架构结论。即使假设每次 API 延迟不变，当前编排仍会系统性放大
墙钟耗时、失败恢复时间和调用成本。

#### 4.4.2 优化前已确认的架构问题

1. **12 个小批次完全串行。** Student 002 的 191 个内容实例按固定 16 项拆成 12 批，后一批必须等待
   前一批完成。正式顺序本来由 Source Inventory 决定，API 完成顺序不决定 `items` 顺序，因此全串行
   不是产品合同要求。
2. **每批都新建并关闭一个 SDK/CLI Session。** 12 个成功批次对应 12 个独立 SDK session；每批重复
   启动 Claude CLI 子进程、加载配置、建立连接和关闭运行时，没有复用长生命周期客户端。
3. **提取任务仍继承通用重型 Agent 配置。** 虽然最终禁用了工具，但配置仍从通用 Agent options
   构建并携带 MCP、project settings、hooks、permission callback 和项目根目录上下文。提取任务实际
   只需要读取应用传入的事实 JSON 并返回 structured output。
4. **批次按固定实例数，而不是按 token/语义负载规划。** 16 个短标题和 16 个长正文段落被视为相同
   工作量，容易同时产生批次数量过多和批次耗时不均衡。
5. **输入重复传输。** 12 批 prompt 共约 453 KB，Schema 约 46 KB；191 个正式内容实例加相邻上下文
   实际传输 257 次，上下文重复率约 34.6%。54 个 Registry 字段和不参与本批语义判断的 hash、locator、
   transport 引用也被重复发送。
6. **输出合同包含较多非必要生成文本。** 原始 structured output 压缩后约 77 KB；191 条强制 note
   共约 23.8 KB，12 批 summary 约 6.6 KB。下游当前只消费 `caption_of`，但 Agent 还生成大量
   `note_of`、`parallel_of` 和 `same_fact_as`，没有形成对应的当前产品价值。
7. **没有应用级批次检查点。** 批次结果全部留在内存，只有 12 批全部完成后才写正式原始提取和
   evidence。后段失败会导致重启后重复执行已经成功的批次。

Claude Agent SDK 官方说明：每个 Agent session 对应一个 Claude CLI 子进程；Python
`ClaudeSDKClient` 可以保持同一 session 并连续接收多个 query；官方 OpenTelemetry 可以提供每个
`claude_code.interaction` 和 `claude_code.llm_request` 的延迟和 token 证据。当前优化应继续采用 SDK
原生机制，不另造 Agent runtime。官方依据：
[Python SDK](https://code.claude.com/docs/en/agent-sdk/python)、
[Hosting](https://code.claude.com/docs/en/agent-sdk/hosting)、
[Observability](https://code.claude.com/docs/en/agent-sdk/observability) 和
[Structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)。

#### 4.4.3 具体优化计划与实施状态

本轮不改变 Student Content Model、Registry、正文顺序或三个产品模块的责任，只替换提取模块内部
编排。计划、目标和实现结果如下：

| 工作项 | 目标效果 | 实施结果 |
|---|---|---|
| 共享层收敛 | 模板与学生提取共享事实，不共享语义或编辑流程 | 保留 `inspect_document` 及其对象引用/OOXML 事实作为中立 Word 事实层；新增只含元数据的 `SDKResultMetrics` 供两个 Agent 模块复用。学生侧继续投影为 Source Inventory，模板侧继续投影为 Template Workspace |
| 提取专用 SDK 配置 | 不加载模板、MCP、Skill、Subagent、文件工具和 project settings | 直接构造 task-local `ClaudeAgentOptions`；仅使用原生 structured output，所有读写/工具能力禁用。应用显式拥有路由和重试，官方 `CLAUDE_CODE_MAX_RETRIES` 设为 0，避免 SDK 内部默认 10 次重试与应用重试相乘 |
| 语义输入精简 | Agent 只看做语义判断所需事实，完整追溯仍由应用保存 | Annotation View 只包含短内容 ID、物理类型、原文、局部源顺序和必要 source facts；删除任务绝对路径、package summary、locator、transport、content_ref 等重复输入 |
| 双预算分批 | 减少批次数，同时避免长段落造成超大批次 | 每批最多 32 项且 Annotation View 最多约 24 KB；Student 002 从固定 16 项的 12 批变为 6 批（31/32/32/32/32/32），源顺序不变 |
| 3 路有界并发 | API 完成顺序不再线性累加到产品墙钟 | 同时最多运行 3 批；全部结果只按 Source Inventory ID 序列确定性合并，完成先后无权改变 `items` |
| 原子批次检查点 | 后段失败不重复支付前段成功调用 | 每个成功批次立即写入 task-local checkpoint；身份绑定 source、Registry、inventory、batch、prompt、schema 和 system prompt hash；任何一个变化都会使旧证据失效 |
| 输出合同压缩 | 删除没有下游价值的生成文本 | classified annotation 和 relation 的 note 改为可选；逐批 summary/uncertainties 不再要求 Agent 生成，应用仍兼容并可聚合旧返回 |
| 可观测性 | 能从证据区分本地、并发墙钟、SDK/API、attempt、usage、成本与收尾 | `run-report.json`、`agent-evidence.json` 和 batch checkpoint 保存 metadata-only SDK 指标；未来批次证据进一步拆分 queue wait 与 execution wall |

本轮没有强行把多个批次塞进同一个长生命周期 session。原因是批次相互独立且需要有界并发，当前
6 个隔离 session 已把墙钟降到可接受范围；复用 session 会重新引入串行依赖。只有更多 Gold 样本证明
CLI 固定成本仍是主要瓶颈时，才把 warm client 作为可逆实验，而不是当前主架构。

#### 4.4.4 性能优化验收标准与结果

| 验收标准 | 正式结果 |
|---|---|
| Gold r5 质量不回退 | `PASS`；8/8 维度通过，188/188 源绑定字段、值、分组、顺序和层级一致 |
| 正文顺序不受并发影响 | `PASS`；191 个 Actual items，188 个 Gold 语义实例完整原序对齐 |
| 并发有界且结果确定 | `PASS`；受控异步测试证明最大并发为 3，逆序完成仍按源序合并 |
| 失败可局部恢复 | `PASS`；测试中 5 批有 1 批首次失败，4 个成功 checkpoint 被复用，第二次只调用失败批 |
| checkpoint 不错误复用 | `PASS`；source、Registry、inventory、batch、prompt/schema/system prompt 均参与身份 hash |
| 真实 API 性能证据完整 | `PASS`；6/6 批、6 个真实 session、每批 1 次成功 attempt，无超时、无路由切换 |
| 静态与模块回归 | `PASS`；Ruff、Mypy 84 个源文件、提取单元/集成/权限/Eval 合同测试均通过 |
| 历史全仓运行中的 Template Workspace 合同失败 | `CLOSED（合同测试已同步）`；此前 509 项中 508 通过的唯一失败，只是实现新增 `preceding_landmarks` 后严格字段集合断言尚未同步。当前测试已把该字段纳入返回合同，并专项验证它只返回目标前面的对象、`distance` 正确且不暴露 `object_ref`。该历史失败不表示 Word 提取、用户内容提取、正文顺序或 `preceding_landmarks` 计算存在回归，也不再是当前工作区 blocker |
| 当前全仓回归 | `OPEN（与本模块和上述合同同步无关）`；2026-08-13 当前工作区为 540 passed、1 failed，唯一失败是 `test_maximum_legal_tool_event_meets_projector_latency_and_drop_contract` 的 observability projector p95 延迟超过 2 ms；单独复跑仍为 2.603 ms。该性能合同应由 observability 工作包处理，不能重新解释为 Template Workspace 或用户内容提取回归 |

#### 4.4.5 Student 002 优化后真实数据

2026-08-12 使用同一 Student 002 原始 DOCX 与 Registry v0.3 发起全新真实 API 调用；没有复用旧 12 批
输出，Gold 仍只在生成正式模型后离线比较。

| 指标 | 串行基线 | 优化后 | 变化 |
|---|---:|---:|---:|
| 完整 CLI 墙钟 | 29 分 17 秒 | 2 分 05.82 秒 | 减少约 92.8%，约 14.0 倍加速 |
| 模块内总墙钟 | 未记录分项 | 125.262 秒 | 前处理、Agent、收尾已分项 |
| 确定性前处理 | 约 8 秒 | 4.330 秒 | 均非主要瓶颈 |
| Agent 编排墙钟 | 约 29 分 09 秒 | 120.900 秒 | 由 6 批、3 路并发完成 |
| SDK duration 求和 | 未记录 | 296.455 秒 | 是 6 个并发 session 的总工作量，不等于用户等待时间 |
| SDK API duration 求和 | 未记录 | 296.378 秒 | 与 SDK 总 duration 接近 |
| 确定性组装收尾 | 约 6.4 ms 本地基准 | 29 ms 正式运行 | 可忽略 |
| API attempt | 含 600 秒超时和 structured-output 重试 | 6 次调用全部一次成功 | 没有隐藏失败放大 |
| SDK usage/cost | 未保存 | input 76,357；output 46,714；总成本 USD 1.5500355 | 已形成后续成本基线，不能与旧运行比较成本降幅 |

正式证据目录：
`temp/student-content-extraction-eval-20260812/student-002-actual-live-optimized-v1/`；Gold 报告：
`eval-gold-r5/student-content-eval-report.md` 与 `student-content-eval-report.json`。

## 5. 另外两个模块的修复与验收计划

### 5.1 模板生成模块

目标是忠实发布学校模板事实，而不是制作通用成品模板。验收只看：真实模板能在有界运行内完成；
全部章节、页面、附表和固定内容保留；填写槽、条件、学校样式和缺口可定位；没有伪造学校样式或
提前注入通用兜底；最终填写可直接消费。

### 5.2 最终内容填写模块

目标是对唯一最终 Word 负责。正式写入前，先根据本次 Student Content Model 和保留的模板内容计算
实际样式角色，并对每个角色在完整学校样式与版本化通用完整样式之间二选一、物化和闭包校验；
然后按 `items` 放置和机械复制，处理必填 `NEEDS_INPUT` 与非填写备注，保留学校附表，完成目录、
页码、分页、对象布局、内容守恒、DOCX 验证和逐页视觉验收。

验收必须证明：没有重新识别学生内容；正文顺序未变；学生文字和复杂对象无损；非填写章节未删；
任务书/开题/评审表未拆分；目录与最终分页一致；所有实际样式角色唯一且完整；最终只发布一份
可正常打开、保存和渲染的 Word。

## 6. 总体完成门

当前真实案例只有同时满足以下条件才能从 `FAIL` 升级为 `COMPLETE`：

1. 三个模块分别通过自己的合同与真实输入验收；
2. 必填学生信息已获得可靠输入，否则任务保持 `NEEDS_INPUT`；
3. 全部实际样式角色在写入前完成完整来源选择和物化；
4. 全部学生内容和复杂对象有明确写入结果，正文顺序不变；
5. 非填写章节保留并标注“本项无需填写”，学校附表保留在同一最终 Word；
6. 目录、页码、分页、占位符、DOCX 结构和逐页视觉检查全部关闭；
7. 最终只发布一份可提交 Word，不存在 `FAIL`、`UNKNOWN` 或 `NEEDS_INPUT`。

## 7. 更新记录

| 日期 | 变更 | 结论 |
|---|---|---|
| 2026-08-10 | 建立真实学生内容与最终填写诊断入口 | 历史诊断候选不代表产品完成 |
| 2026-08-11 | 产品负责人确认三个模块、模板内容保留、附表不拆分和样式物化归最终填写 | 重新收敛产品责任 |
| 2026-08-11 | 旧提取合同升级为 keyed `fields + segments` v2，并完成两次真实重复性证明 | 该证据现为历史基线，已被新模型替代 |
| 2026-08-12 | 用户内容提取改为有序 Source Items → v3 Agent 标注 → Student Content Model v2；填写端改为消费语义 | 代码已实现，470 项全仓回归通过；真实源事实层完成，但两条实时路由全量超时，紧凑批次仍无及时返回，状态为 `IMPLEMENTED_LIVE_PROOF_BLOCKED` |
| 2026-08-12 | Student 002 完整真实 API 提取并与 Gold r5 正式比较 | 12/12 批次有 SDK structured-output 证据；188/188 源绑定实例一致，8/8 维度 `PASS`；提取模块升级为 `PASSED_STUDENT_002_GOLD_R5` |
| 2026-08-12 | 记录 Student 002 正式提取 29 分 17 秒的性能问题 | 质量验收保持通过；当前瓶颈定位到提取编排层，状态调整为 `QUALITY_PASSED_PERFORMANCE_OPEN`，按观测、有界并发/检查点、轻量运行时、合同压缩和动态批次顺序关闭 |
| 2026-08-12 | 完成提取编排优化并重新执行 Student 002 真实 API + Gold r5 | 6 批、3 路并发、2 分 05.82 秒；相对基线减少约 92.8%，Gold 仍为 188/188、8/8 `PASS`；状态升级为 `STUDENT_002_QUALITY_AND_PERFORMANCE_PASSED` |
