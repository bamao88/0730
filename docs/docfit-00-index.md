# DocFit 设计文档索引（00）

> 状态：最终架构索引
> 日期：2026-08-05

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
页面批次与图片载荷、收紧无效重试。该轨道已完成 O0.0–O0.7：平台无关骨架、SDK
transcript/report v2 隐私合同、入队前字段 allowlist projector，以及直接 ID 关联、覆盖维度
和安全指标聚合，并已加入有界 queue、后台单 writer、SQLite 历史、保留/删除与非阻断
降级、免登录 loopback 安全壳、自动短期会话、会话内证据重新挂载，以及运行总览、Transcript/时间线、
Agent/Subagent 树、Tool/事件详情、调查交接、跨运行比较与 O0 总体验收；O1 尚未开始。
它不能产生真实交付质量、MVP
或 M3 已通过的声明。

论文转换的文档方向固定为“模板主干”：干净、可填写的目标模板工作副本是候选与最终
DOCX 的唯一主干；学生 DOCX 始终只读，只提供内容真值和来源证据。Agent 根据当前任务
绑定把学生内容放入模板槽位或区域，不得从学生论文副本开始构建候选，再把模板节导入
其中。底层仍可保留兼容性的跨文档模板组合操作，但它不是 `convert-thesis` 的默认路线，
也不能替代学生内容到目标模板的位置映射。

已批准的下一版目标把这条方向收紧为显式的任务级产物合同：
`docfit-school-extract` 负责把学校材料整理成“冻结干净模板 + 与该模板 hash 绑定的
artifact manifest”，`convert-thesis` 只消费这份模板产物与只读学生 DOCX，并交付“最终
DOCX + conversion report”。模板产物内部可以包含 visual review 与 freeze report，但
对消费者仍是一个原子 artifact，不增加独立交付类型。
两者通过产物 Interface 耦合，不通过 Skill 名称、调用顺序或共享隐藏状态耦合；同一
Interface 也允许人工或其他受控适配器准备。当前 M2 实现只具备模板主干和跨文档内容
导入基础，尚未实现完整槽位索引、固定内容保护与源内容覆盖完成门；实施状态和进入条件
以 06 的独立候选切片为准。

该轨道的 O0 已进一步批准为一个薄应用壳内的本地只读观测界面，详细目标见
`docfit-local-observability-design.md`。它只投影 SDK 实际运行事件、脱敏 Tool 摘要与
本地证据引用，不控制 Agent、不复制任务文件，也不建立第二套 loop、工作流或 replay。
当前已完成设计与 O0.0–O0.7 的安全事件投影、直接关联、有界历史索引、免登录 Web 会话安全、
证据重新挂载、Agent loop 核心页面、跨运行比较与总门。

O0 的 metadata-only 只描述观测索引，不掩盖 SDK 原生 transcript：实现必须使用运行级
临时 `CLAUDE_CONFIG_DIR` 并管理清理回执。CLI 结束后的历史证据默认 unmounted，只有
用户显式重新选择任务目录并通过 report ID/hash/ref 验证后才能打开；网站不保存路径
映射或扫描目录。schema v2 报告、本地 Web 自动短期会话、同源/CSRF 安全与资源硬上限
都是 O0 完成门。

## 一句话架构

DocFit 以 **Claude Agent SDK** 为运行时边界，产品只维护五类资产：

```text
Skill + Knowledge + Tools + Eval + 薄应用壳
```

DocFit 不再自建 Agent 工作流运行时。会话、Agent loop、工具调用、上下文延续、用户追问、
原生 Subagent 与恢复能力均优先使用 Claude Agent SDK；只有论文领域能力留在 DocFit。

批准的顶层运行关系是：两个领域 Skill（`docfit-school-extract` 与 `convert-thesis`）说明
论文转换目标、输入输出、推荐操作方法、判断标准与已经验证的高风险机制，一个模块化
通用 Knowledge Package 提供可选择的知识内容，领域 Tool 面提供确定性文档能力。当前
转换链使用五个 `docx_*` Tool；学校模板目标面使用五个职责独立的 `template_*` Tool，
只在该 Skill 的生产运行中暴露。论文转换目标 Tool 面若需重设计，另行确定，不由学校
模板方案兼容性倒推。薄应用壳只额外配置一个通用只读
`docfit-unit-analyst`，以 SDK 原生隔离上下文执行局部分析；它不是新的产品资产、
单元专家目录或固定工作流节点。

两个 Skill 的目标职责不同：学校提取 Skill 产出冻结模板 Interface，转换 Skill 消费
该 Interface 并产出最终论文。Skill 可以给出可调整的操作步骤，说明何时观察、如何把
可见角色、存续责任、修饰字段、证据状态和修改动作分开记录、如何仅为删除动作选择删除
模式和定义槽位语义、怎样解释比较结果；其 bundled scripts 把 Agent 已完成的语义决定
确定性编译为 Tool typed input，但不替 Agent 判断或操作 DOCX。主 Agent 是任务和最终
产物的 owner：它检查每次脚本/Tool 结果，发现失败、误伤或结果不合理时修正并重新执行；
Tool 的单次成功/失败不是任务终态。Skill 不把这套自适应返工变成持久化状态机。模板 hash
绑定、槽位唯一定位、原子写入、固定内容保护、源内容覆盖与“失败不发布”属于 Tool/
应用壳的确定性合同。把这些机制放进现有五类资产，不新增 Harness 或工作流节点。

主 Agent 的 SDK 内置能力面固定为 `Skill`、受路径权限约束的 `Read/Glob/Grep`、受信任且
自动批准的 `Bash/Write`、`AskUserQuestion` 与 `Agent`，并直接调用当前任务域注册的
DocFit Tool。当前转换链仍注册五个 `docx_*` Tool；学校模板目标运行注册五个
`template_*` Tool。
`Read/Glob/Grep` 只直接读取
项目 `.claude/skills/**`、产品 Knowledge Package 和当前任务 input/work/output；权限
判断先解析真实绝对路径，再拒绝敏感文件、项目外/其他任务路径与 symlink 逃逸。
`Bash/Write` 不经过 DocFit 路径 hook，可访问 Agent 进程本来可访问的路径和环境；因此
前述直接 Read allowlist 不是 sandbox，也不再声称 input、任务外路径或文档产物对主 Agent
不可写。`Edit` 和网络工具仍不开放。`docfit-unit-analyst` 不继承这组主 Agent 能力；其
当前转换只读 Tool 子集保持不变。生产文档修改、对账和发布只通过任务域注册的权威 Tool。

当前转换实现的五个 `docx_*` Tool 只适配两个职责不重叠的具体后端：OfficeCLI 负责
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
不增加第二套协议或新的 Agent loop。

在当前转换 Tool 面中，`docx_render` 是新渲染证据的生产边界；`docx_visual_review` 只读取有效
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
6. 设计样式观测与缺口补全：读 01 的 Knowledge/Tool 边界 → 05 第 2.4.1 节 →
   04 的 Skill 边界 → 02 的后续契约门 → 06 第 6.8 节。
7. 实现冻结模板产物 Interface：读 01 的 Skill/产物不变量 → 04 第 2–4 节 →
   05 的任务级产物合同 → 02 的普通契约门 → 06 第 6.9 节；候选 Skill 文字、reference
   树和原子迁移范围见非权威实施草案 `plans/docfit-school-extract-v2.md`。

## 五类资产的权威边界

| 资产 | 负责 | 不负责 |
|---|---|---|
| Skill | 论文转换目标、输入输出、推荐操作方法、语义判断标准、真实失败提炼的高风险规则和最终答复；bundled scripts 将 Agent 决定编译为版本化 Tool 输入 | 观察/修改 DOCX、替 Agent 生成语义决定、实现冻结发布、持久化状态机、真实工具权限实现 |
| Knowledge | 面向所有学校和任务共享、可按消费范围组合的论文格式概念、识别方法、解释原则和通用处理模式 | 任何学校专属要求、模板、格式参数、任务证据、执行流程、Agent 调度和运行日志 |
| Tools | 不可变文档事实、受控修改、结构/视觉证据、候选编译和独立验证等确定性能力；具体 Tool 面按任务域注册 | 在 Tool 内启动第二个 Agent、把近似渲染冒充权威证据，或替当前 Agent 做学校材料语义判断 |
| Eval | 离线样本、断言、回归与质量比较 | 在线运行编排、交付状态管理 |
| 薄应用壳 | 收集输入、配置 SDK、暴露领域资产、落实主 Agent 直接读取路径策略、受信任 Bash/Write 与 Subagent 上下文隔离/最小权限、返回回复与产物；按批准的 O0 设计投影隐私安全的本地运行观测 | 领域判断、委派策略、工作流引擎、第二套 shell/runtime、用监控事件控制或精确回放 Agent |

Claude Agent SDK 是运行时行为的权威来源。DocFit 文档不得复制一套 SDK 会话、事件、
阶段、checkpoint、Subagent 或恢复协议。`AgentDefinition` 只是 SDK 接线配置，不与
Skill、Knowledge、Tools、Eval 或薄应用壳并列为第六类产品资产。

Claude Agent SDK 没有一个与 Skill、Tool 并列的 DocFit Knowledge Base runtime。
稳定通用知识由产品 Knowledge Package 提供；主 Agent 选择本次委派所需模块，并将
选中内容及版本/digest 与当前任务证据一起放入 `Agent` Tool 的 prompt。

Knowledge Package 随产品发布且必须保持通用。学校事实只来自当前任务提供的
模板、要求、示例和用户确认；Agent 在任务中提取或推导的学校结论不会因此自动
成为长期 Knowledge。

样式值也遵守同一边界：Agent 可以使用 Knowledge 中的通用概念识别语义角色、
绑定模板观测与暴露缺口，但不读取或杜撰可直接套用的“样式经验表”。模板的
有效样式由任务域 Tool 确定性观测；学校模板目标面把当前任务文字要求作为独立来源与
观测事实逐属性交叉验证。缺少当前任务明文、适用范围不清或来源冲突时保持未决，不从
历史学校、常识、样式名或内置国家标准值自动补全。当前实现状态与后续实现门以 06 为准。

页面不是新的架构资产或稳定编辑身份。页码只在某次 `render_ref` 内有意义；
不同 Provider 的同页码不得被视为同一内容范围。Agent 使用页面图片观察版式，
但精确修改仍通过绑定当前 DOCX 快照的 opaque `object_ref` 完成。

冻结模板产物也不是全局 Artifact 系统。其 `slot_id` 只在一份明确 hash 的冻结模板
快照内成立；索引的责任 kind 必须区分 fixed、fill 和 generate，并分别记录 cardinality、
condition、automatic/manual handling 与 resolved/unresolved 状态。自动区域必须能够在该
快照中唯一定位，并声明期望内容种类与基数；人工区域和无法表达的 gap 显式。
模板一经修改，旧槽位 locator 不得继续作为当前事实。
转换完成时，学生源内容清单中的每一项必须已经放置，或具有明确且可审计的不放置原因；
该任务级覆盖合同不升级为跨任务 Content Ledger。

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
