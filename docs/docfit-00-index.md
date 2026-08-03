# DocFit 设计文档索引（00）

> 状态：最终架构索引
> 日期：2026-08-03

本文描述已经批准的目标架构；当前实现边界与完成判定以 06 为准。当前代码已包含
M0、通用 Knowledge Package v1、Provider-independent P1、五个真实 DOCX Tool、
固定 OfficeCLI/Adobe PDF Services 薄适配、`docfit convert` 薄应用壳，以及最小
`docfit eval --suite core`。第二个后端已纠正为 Adobe PDF Services API；核心转换和
云端运行链路不依赖本地 Microsoft Word、AppleScript、macOS 图形会话、用户电脑或
本地字体库存。本地调试壳可以提供可选的平台适配器，但核心代码不得导入该实现，
平台适配能力也不构成核心完成门。确定性与 live 完成情况仍分别按 06 判定。当前用户
批准的产品开发范围已在 M2 结束并完成；M3 的
Eval 扩展、真实样本资格验证、Gold 和外部人工复核保留为后续独立范围，不能因此
宣称 M3 已通过，也不再作为当前计划 blocker。

M2 完成之后的核心转换性能与效率优化是一条独立开发轨道，不等同于恢复 M3。
06 已记录该轨道的开始条件、执行顺序和延期项：先补齐不含正文或凭据的运行指标，
再基于同一合成产品链路依次减少重复 Tool 调用、复用单次运行解析/渲染结果、优化
页面批次与图片载荷、收紧无效重试。该轨道已完成 O0.0–O0.3：平台无关骨架、SDK
transcript/report v2 隐私合同、入队前字段 allowlist projector，以及直接 ID 关联、覆盖维度
和安全指标聚合；历史索引、网站和 O0 总体验收尚未实现。它不能产生真实交付质量、MVP
或 M3 已通过的声明。

该轨道的 O0 已进一步批准为一个薄应用壳内的本地只读观测界面，详细目标见
`docfit-local-observability-design.md`。它只投影 SDK 实际运行事件、脱敏 Tool 摘要与
本地证据引用，不控制 Agent、不复制任务文件，也不建立第二套 loop、工作流或 replay。
当前已完成设计与 O0.0–O0.3 的安全事件投影和直接关联；事件持久化、历史索引和网站
尚未实现。

O0 的 metadata-only 只描述观测索引，不掩盖 SDK 原生 transcript：实现必须使用运行级
临时 `CLAUDE_CONFIG_DIR` 并管理清理回执。CLI 结束后的历史证据默认 unmounted，只有
用户显式重新选择任务目录并通过 report ID/hash/ref 验证后才能打开；网站不保存路径
映射或扫描目录。schema v2 报告、本地 Web 同源/会话安全与资源硬上限都是 O0 完成门。

## 一句话架构

DocFit 以 **Claude Agent SDK** 为运行时边界，产品只维护五类资产：

```text
Skill + Knowledge + Tools + Eval + 薄应用壳
```

DocFit 不再自建 Agent 工作流运行时。会话、Agent loop、工具调用、上下文延续、用户追问、
原生 Subagent 与恢复能力均优先使用 Claude Agent SDK；只有论文领域能力留在 DocFit。

批准的顶层运行关系是：两个领域 Skill（`docfit-school-extract` 与 `convert-thesis`）负责
任务判断与可选委派，一个模块化通用 Knowledge Package 提供可选择的知识内容，五个
DocFit MCP Tool 提供确定性文档能力。薄应用壳只额外配置一个通用只读
`docfit-unit-analyst`，以 SDK 原生隔离上下文执行局部分析；它不是新的产品资产、
单元专家目录或固定工作流节点。

第一版在五个 Tool 内只适配两个职责不重叠的具体后端：OfficeCLI 负责
inspect、edit、validate 和高频截图，Adobe PDF Services API 负责 `baseline` 与
`candidate_verification` 的 DOCX→PDF 服务转换。Agent 只表达 `baseline`、
`edit_feedback` 或
`candidate_verification`，不选择后端；当前不建设通用
Provider 接口、注册表、动态选择或故障转移。

Adobe 路由通过锁定的 `pdfservices-sdk==4.2.0` 和仓库外 `0600` 凭据运行。每个未命中
缓存的 DOCX→PDF 调用消耗一个 Document Transaction；免费开发额度当前按每月 500 次
做容量规划。配额是运行资源约束，不进入公开 Tool schema，也不允许失败后回退到
OfficeCLI 冒充交付证据。Adobe 未公开的字体库存和替代详情必须标记为
`service-managed` / `opaque`，不得用本地字体指纹代替。

Claude Agent SDK 兼容边界也属于薄应用壳与 Tool adapter：公开 Tool schema 使用兼容
backend 能稳定消费的扁平 JSON Schema 子集；Tool 的完整结构化结果同时以紧凑 JSON
text 对当前 Agent 可见，图片仍使用原生 image content block。应用壳为真实页面批次
配置足够的 SDK 消息缓冲，但单次视觉返回仍受图片数量和字节预算限制。这些兼容处理
不增加第六个 Tool、第二套协议或新的 Agent loop。

`docx_render` 是新渲染证据的生产边界；`docx_visual_review` 只读取有效
`render_ref` 的已有页面产物并将图片投递给 Agent，不调用任何渲染后端，也不产生新
的文档 render。Tool 不维护编辑轮次，是否继续由 Agent 判断。

## 文档清单

| 编号 | 文档 | 回答的问题 |
|---|---|---|
| 01 | `docfit-01-architecture-core.md` | 产品边界是什么，五类资产如何协作 |
| 06 | `docfit-06-development-roadmap.md` | 如何按阶段开发，每个阶段如何验收和停止 |
| 04 | `docfit-04-skills-design.md` | Skill 如何指导 Agent，而不变成固定工作流 |
| 05 | `docfit-05-tools-and-data-design.md` | Knowledge 如何组织，Tools 提供哪些确定性能力 |
| 02 | `docfit-02-testing-and-iteration.md` | 如何区分普通回归、运行指标与 Eval，并据此迭代 Skill、Knowledge 与 Tools |
| 03 | `docfit-03-gold-system-design.md` | Eval case 与 Gold 数据如何保持简单、可维护 |

`docs/human/` 存放面向人的示例，不定义架构。

`docfit-local-observability-design.md` 是受 00–06 约束的 M2 后专题设计，定义本地运行
观测页面的职责、数据边界、信息层次与验收要求。它不是第八份顶层架构合同，也不把
监控事件升级为新的产品资产或公共协议。

00–06 共同构成 DocFit 的长期开发基准：01 负责稳定架构，06 负责开发顺序和
阶段验收，02–05 负责各类资产的长期设计。它们可以随经过批准的方案、实现证据
和真实样本演进，但必须作为一个协调一致的文档集合维护。

代码、目录、公开契约、测试分层或里程碑发生变化时，必须在同一批变更中更新
所有受影响的 00–06 文档；不得让实现长期领先于文档，也不得用临时计划或执行
状态覆盖这里的长期基准。设计说明中的字段和工具内部数据仍不会自动升级为新的
架构组件，新增边界必须经过明确审批。

## 推荐阅读顺序

1. 只想理解产品：读 01。
2. 准备开发：读 01 → 06。
3. 实现第一条论文转换链路：按 06 的阶段读取 04 → 05。
4. 建立质量闭环：再读 02 → 03。
5. 开始 M2 后运行观测与性能优化：读 06 第 6.6 节 →
   `docfit-local-observability-design.md` → 02 第 2.4、10 节。

## 五类资产的权威边界

| 资产 | 负责 | 不负责 |
|---|---|---|
| Skill | 领域目标、判断方法、工具使用、为什么/何时委派、如何拆分、选择哪些 Knowledge、传递哪些证据及期待什么返回 | 固定调度图、持久化状态机、真实工具权限实现 |
| Knowledge | 面向所有学校和任务共享、可按消费范围组合的论文格式概念、识别方法、解释原则和通用处理模式 | 任何学校专属要求、模板、格式参数、任务证据、执行流程、Agent 调度和运行日志 |
| Tools | DOCX 分析、修改、按 intent 生产渲染证据、读取已有视觉证据、可选元素映射和确定性检查 | 在 Tool 内启动第二个 Agent、把近似渲染冒充 Adobe 交付转换证据，或替当前 Agent 做语义判断 |
| Eval | 离线样本、断言、回归与质量比较 | 在线运行编排、交付状态管理 |
| 薄应用壳 | 收集输入、配置 SDK、暴露领域资产、落实 Subagent 上下文隔离和最小权限、返回回复与产物；按批准的 O0 设计投影隐私安全的本地运行观测 | 领域判断、委派策略、工作流引擎、用监控事件控制或精确回放 Agent |

Claude Agent SDK 是运行时行为的权威来源。DocFit 文档不得复制一套 SDK 会话、事件、
阶段、checkpoint、Subagent 或恢复协议。`AgentDefinition` 只是 SDK 接线配置，不与
Skill、Knowledge、Tools、Eval 或薄应用壳并列为第六类产品资产。

Claude Agent SDK 没有一个与 Skill、Tool 并列的 DocFit Knowledge Base runtime。
稳定通用知识由产品 Knowledge Package 提供；当前 Skill 选择本次委派所需模块，主
Agent 将选中内容及版本/digest 与当前任务证据一起放入 `Agent` Tool 的 prompt。

Knowledge Package 随产品发布且必须保持通用。学校事实只来自当前任务提供的
模板、要求、示例和用户确认；Agent 在任务中提取或推导的学校结论不会因此自动
成为长期 Knowledge。

页面不是新的架构资产或稳定编辑身份。页码只在某次 `render_ref` 内有意义；
不同 Provider 的同页码不得被视为同一内容范围。Agent 使用页面图片观察版式，
但精确修改仍通过绑定当前 DOCX 快照的 opaque `object_ref` 完成。

## 明确不建设

以下内容不属于当前 DocFit 架构：

- 自定义工作流引擎、阶段 DAG 或任务调度器；
- 六个或更多文档单元专家目录、固定 AgentDefinition 注册表或穷尽式文档类型枚举；
- “发现某单元就必须委派”的规则、固定复杂度阈值或应用壳领域路由；
- `StageExecution`、Run Evidence Module、事件 hash chain；
- 自定义 checkpoint、exact replay、comparative replay；
- Delivery Preflight 子系统和多层交付状态机；
- 独立 Runtime Verifier 或 Finalizer；
- 为未来平台预建的 Adapter、Port、发布事务与 schema 总线；
- 只有一处消费者的抽象层；
- 与 Claude Agent SDK 重叠的路由、会话和恢复实现。

只读历史比较不等于 comparative replay：它比较已经落盘的脱敏指标和证据可用性，
不会重放模型请求、Tool 副作用或文档内容。

OfficeCLI 与 Adobe PDF Services API 分担不同职责，不构成“两个实现共同消费一套通用
Provider 抽象”的证据。只有未来真实接入第三个引擎，并且确实需要动态选择或
故障转移时，才重新评估该抽象。

如果未来真实需求证明必须增加其中某项，应以独立 ADR 说明：当前痛点、最小方案、为什么 SDK 或普通工具不能解决，以及删除成本。

## 变更原则

架构变更先回答四个问题：

1. 这项能力能否放进 Skill、Knowledge、Tool 或 Eval？
2. Claude Agent SDK 是否已经提供同类运行时能力？
3. 是否有当前真实样本证明需要新组件？
4. 新抽象是否至少有两个明确消费者？

任一问题没有清楚答案时，不新增架构组件。

增加新的通用 Knowledge 模块不等于增加 Agent 类型。未匹配、复合或简单文档范围可以
由主 Agent 直接分析，或连同所需 Knowledge 交给同一个 `docfit-unit-analyst`。
