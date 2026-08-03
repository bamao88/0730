# DocFit 本地运行观测与问题定位界面

> 状态：目标设计已批准；实现尚未开始
> 日期：2026-08-03
> 所属范围：M2 后核心转换优化的 O0 观测面
> 上位契约：`docfit-00-index.md`–`docfit-06-development-roadmap.md`
> 实施计划：`plans/docfit-o0-local-observability.md`

## 0. 产品定义

DocFit 本地运行观测与问题定位界面，是薄应用壳中的本地只读可观测界面。它把
Claude Agent SDK 实际发生的 Agent loop、Tool 调用、权限判断和 Subagent 活动，整理为
人能够阅读的运行轨迹，并通过稳定引用连接到本地任务证据。

它不保存论文正文，不执行文档操作，也不参与 Agent 的判断、委派或调度。这里的“不保存”
只约束 O0 观测索引、日志和导出；SDK 自身 transcript 是第 3.4 节单独治理的数据面。

更完整的一句话定义是：

> DocFit 监控网站是薄应用壳中的本地只读可观测界面，负责展示 Agent SDK 实际运行
> 轨迹、汇总隐私安全的运行指标、定位 Tool 与 Subagent 问题，并通过稳定引用连接到
> 本地任务证据；它不保存论文正文、不执行文档操作，也不参与 Agent 决策和调度。

本文定义目标产品、数据边界和验收要求，不表示这些能力已经实现。当前 schema v1
`conversion-report.json` 保存最终状态、会话 ID、Tool 名称序列、版本/hash 与产物摘要，
既有字段还可能包含 artifact 绝对路径和 warning/detail 文本；逐事件输入输出摘要、耗时、
Subagent 树、历史比较和实时页面仍属于后续 O0 实现。O0 reader 必须先按第 10.3 节做
allowlist 投影，不能把现有报告完整复制进观测索引。

O0 的核心不是先画页面，而是先满足四份可验证合同：

| 合同 | 必须回答 | 本文位置 |
|---|---|---|
| 来源合同 | 每个页面事实来自哪条 SDK/App/Tool/report/evidence 来源 | 第 3 节 |
| 关联合同 | Tool、Subagent 和本地证据为什么属于同一次调用或快照 | 第 4.6、6 节 |
| 留存合同 | 哪些字段可以保存、条件保存或必须丢弃 | 第 4.5、7 节 |
| 降级合同 | 来源、脱敏、队列、存储或 UI 失败时转换与页面各如何表现 | 第 10、11 节 |

## 1. 要解决的问题

界面必须直接回答五个问题：

1. 这次任务现在运行到哪里，最终成功、需要补充输入还是失败？
2. 主 Agent 发生了哪些可观察的判断、回复和动作？
3. 调用了哪些 Tool，实际顺序、耗时、输入摘要、结果和副作用是什么？
4. 什么时候启动了 Subagent，Subagent 收到什么范围、调用了什么 Tool、返回了什么？
5. 出现异常时，问题绑定哪个文档快照、对象、渲染证据、页面或 Tool 调用？

它的核心价值是：

- **运行过程可见**：不用从终端碎片和多个 JSON 文件拼接当前进度；
- **问题位置可查**：错误能够落到一次可识别的 Agent、Tool 或证据引用；
- **性能瓶颈可量化**：能够区分模型等待、Tool 执行、渲染、图片读取和重试成本；
- **本地证据可回溯**：运行摘要可以连接到仍然有效的本地任务证据；
- **不同运行可比较**：同一测试样本在代码、Skill、Knowledge 或模型版本变化后可以
  比较耗时、调用、载荷和失败差异。

“主 Agent 做了哪些判断”只指 SDK 可观察的回复、Tool 选择、结构化结果与行动摘要。
界面不采集、推断或展示模型隐藏思维链。

## 2. 产品边界

### 2.1 网站负责

- 近实时展示一条 `docfit convert` 运行的活动状态与最终结果；
- 按 SDK 实际事件重建可阅读的 Agent 行动时间线；
- 展示主 Agent、Subagent、Tool 调用和父子关系；
- 展示经过字段级脱敏的 Tool 输入与输出摘要；
- 记录状态、耗时、Token、成本估算、错误码与权限判断；
- 关联文档 hash、`object_ref`、`render_ref`、`evidence_ref` 和页码；
- 标识 Tool 允许/拒绝、用户追问、`needs_input` 与异常；
- 为单个异常事件生成不含正文的“调试上下文”；
- 在本机保存有上限、可删除的隐私安全历史记录；
- 比较同一可比样本在不同版本间的运行差异。

### 2.2 网站不负责

- 决定 Agent 下一步做什么；
- 启动、取消、重试或调度主 Agent、Subagent 或 Tool；
- 替代 Claude Agent SDK 的 Agent loop、会话或恢复能力；
- 解释 `needs_input` 并代替 Agent 向用户提问；
- 修改 DOCX、生成 render、验证论文或发布产物；
- 判断论文是否符合学校要求；
- 保存完整论文正文、学校材料正文或完整页面图片；
- 保存完整模型请求、完整模型响应或隐藏思维链；
- 建立第二套工作流、任务状态机、Tool 协议、checkpoint 或 replay 系统；
- 在本地证据已经丢失或失效时，根据旧摘要猜测正文或声称可以精确回放。

### 2.3 控制关系

```text
Claude Agent SDK     负责唯一 Agent loop、会话、Tool 与 Subagent 运行
DocFit Tools         负责确定性取证、修改、渲染、视觉证据读取与验证
本地任务目录         保存文档、render、validation 与交付事实
监控网站             只观察、整理、索引、比较和定位
```

监控网站对运行路径只有单向读取关系。它的故障不能改变转换结果；转换也不能依赖网站
已经启动。关闭网站后，`docfit convert` 仍应按原合同运行。

## 3. 数据从哪里来

监控网站属于现有薄应用壳的一个本地视图，不是第六类产品资产，也不是新的 Agent
runtime。它复用 Claude Agent SDK 已公开的消息流和 hooks、DocFit Tool 结构化结果、
薄应用壳最终报告，以及本地任务证据。

### 3.1 当前基线与 O0 差距

本文按仓库锁定的 `claude-agent-sdk==0.2.128` 定义来源字段。当前实现只在 SDK 响应流中
读取 `AssistantMessage` 的 `ToolUseBlock`，收集 Tool 名称和
Skill 名称；结束时读取 `ResultMessage` 的 `session_id` 与结构化最终结果。现有
schema v1 `conversion-report.json` 保存最终状态、版本/hash、Tool 名称序列和产物摘要，
同时可能带 artifact 绝对路径及 warning/detail 文本。权限审计只为 `Agent` Tool 保存
Subagent 类型与 allow/deny 结果。

当前实现还没有：

- `PreToolUse`/`PostToolUse`/`PostToolUseFailure` 的通用逐调用采集；
- `ToolUseBlock.id` 与 `ToolResultBlock.tool_use_id` 的持久化关联；
- `SubagentStart`/`SubagentStop` 与 `agent_id` 的生命周期采集；
- Tool 输入输出的字段级脱敏投影；
- 单调耗时、丢弃计数、观测覆盖率或本地历史索引；
- 运行级临时 `CLAUDE_CONFIG_DIR` 与 SDK transcript 清理；
- report v2、历史目录显式挂载、本地 Web 会话/同源安全与 O0 资源预算；
- 实时网站。

因此下述采集链路是 O0 必须新增的目标设计，不是当前代码已经具备的能力。
SDK 升级时必须先用合成 message/hook fixture 重新证明字段存在性与关联链，不能假设
私有 transcript 格式或历史 hook 语义保持不变。

### 3.2 采集链路

```text
App / SDK message / SDK hook / Tool result / final report
                         |
                         v
              来源专属投影器与字段 allowlist
              （同步删除正文、图片、路径和原始错误）
                         |
                         v
                 有上限的脱敏事件通道
                         |
                         v
                   本地观测索引
                         |
                         v
                   只读监控网站
                         |
                  hash/ref 重新验证
                         |
                         v
                 授权的本地任务目录
```

脱敏必须发生在事件进入队列、数据库、日志或导出之前。对 O0 采集器而言，原始 prompt、
Tool input、`tool_response`、图片块和 Provider 错误只允许在当前同步投影调用中短暂存在；
观测代码不能把它们复制到异步队列后再清洗。这个约束只描述 O0 的复制行为；Claude
Agent SDK 自己仍会把 session transcript 写入本地磁盘，并由第 3.4 节的独立合同管理。
每种来源使用独立投影器，
未知事件类型和未知字段默认丢弃，不采用“先完整序列化、以后再遮盖”的方式。

本地索引写入与 Web 进程分离。网站未启动或浏览器断开时，转换和本地采集仍可继续；
网站只读取已经脱敏的投影，不订阅能够控制 SDK 的双向通道。

### 3.3 来源矩阵

| 网站事实 | 权威来源 | 直接关联字段 | 可持久化内容 | 来源缺失时 |
|---|---|---|---|---|
| run 开始、`task_ref`、输入 hash、版本 | 薄应用壳在调用 SDK 前建立的运行上下文 | `run_id` | opaque task ref、hash、版本、开始时间 | 没有 run 记录；不能由任务目录时间猜测 |
| Agent 可观察消息与 Tool use | SDK `AssistantMessage` 和 `ToolUseBlock` | message UUID/ID、block `id`、`session_id`、`parent_tool_use_id` | actor、Tool/Skill 名、usage、模板化行动摘要 | 显示消息源缺口，不读取 SDK transcript 补齐 |
| Tool 正常结果 | SDK `PostToolUse` hook 和流中的 `ToolResultBlock` | 相同 `tool_use_id` | Tool 专属 allowlist 摘要、status、refs、committed | 调用节点保留，结果标为未观测 |
| Tool 执行失败 | SDK `PostToolUseFailure` 或可解析的 DocFit Tool failure | `tool_use_id` | 安全错误码、origin、retryable、interrupt 标记 | 显示失败详情不可用，不保存 raw error |
| Tool 调用者 | Tool lifecycle hook | `agent_id`、`agent_type`；主 Agent 时为空 | main/Subagent actor 与类型 | actor 标为 unknown，不按时间猜测 |
| Subagent 开始/结束 | SDK `SubagentStart`/`SubagentStop` hooks | 相同 `agent_id`、`agent_type` | 生命周期时间、类型、覆盖状态 | Subagent 节点标为部分观测 |
| Subagent 与父 `Agent` 调用 | `Agent` 的 Tool use，加上子消息的 `parent_tool_use_id` | `Agent` ToolUseBlock `id` = 子消息 `parent_tool_use_id` | 已验证父调用引用 | 无直接 ID 时标为 partial，不按相邻时间连线 |
| Subagent 内部 Tool | 子消息的 ToolUseBlock 加 Tool hook | block `id` = hook `tool_use_id`，hook `agent_id` | Tool 与具体 Subagent 的直接关联 | 缺任一桥接字段时保持未关联 |
| 权限 allow/deny | `PreToolUse` hook 与 `can_use_tool` callback | `tool_use_id`、可选 `agent_id` | decision、工具、Subagent 类型、安全原因码 | Tool 事件显示“权限来源未观测” |
| 用户追问 | `AskUserQuestion` 的 Tool use、权限回调和结果 | `tool_use_id` | 问题类别、选项数、answered、耗时 | 不保存问题/答案原文；结果缺失时为 unknown |
| turn、Token、成本、终止原因 | `AssistantMessage.usage` 与 `ResultMessage` | `session_id`、message ID/UUID | usage、model usage、reported cost、duration、num_turns、terminal reason | 明确显示 unknown，不能当作 0 |
| SDK transcript privacy | App 管理的运行级 `CLAUDE_CONFIG_DIR` lifecycle | `run_id` | active/cleaned/residual/cleanup_failed、数量、年龄区间 | 显示 unknown；不读取 transcript 内容确认 |
| backend 尝试、超时与选定项 | 薄应用壳 backend 循环 | `run_id` + attempt 序号 | backend/model 名、开始/结束、清洗后的失败分类 | 只显示最终 backend 时标记 attempt history unavailable |
| 最终转换事实 | `conversion-report.json` 与最终 App 结果 | `run_id`、`session_id`、文档 hash | `COMPLETED/NEEDS_INPUT/ERROR`、产物类型、warning/error 计数 | 没有终态时显示“终态未知” |
| 文档、对象、render、页面证据 | 五个 Tool 结果与授权任务目录 | document/render/image hash 和 opaque refs | hash/ref/page、Provider、证据可用性 | 显示 unavailable/broken/conflict，不缓存正文 |

SDK `ThinkingBlock`、hook 中的 `prompt`、`transcript_path`/`cwd`、Tool 的原始 input/
response 和 `ResultMessage.result` 不进入观测索引。OpenTelemetry 可以补充标准耗时与
usage，但不能覆盖上述直接 ID，也不能成为父子关系或文档证据关联的唯一依据。

网站只展示真实取得的事件。某个 backend 或 SDK 版本没有暴露子事件、Token、成本或
精确时间时，对应字段显示“未观测到”或“不可用”，不能从最终结果反推并伪造轨迹。

### 3.4 SDK 原生 transcript 是独立的数据面

当前 Claude Agent SDK 子进程会把完整主 Agent/Subagent session transcript 写到
`CLAUDE_CONFIG_DIR` 下；即使没有配置 `SessionStore`，本地副本仍然存在。当前 DocFit 没有
为每次转换设置独立 `CLAUDE_CONFIG_DIR`，因此这是 O0 实现前必须修复的既有隐私缺口。
“观测索引 metadata only”不能被扩大解释为“整台机器没有正文副本”。

O0 的目标合同固定为：

1. 每次 SDK 运行在 DocFit 管理的私有临时父目录下创建独立配置目录，目录权限为 `0700`，
   不放进任务证据目录或观测数据库；
2. 只把该目录通过当前 backend environment 作为本次子进程的 `CLAUDE_CONFIG_DIR`，不配置
   SDK `SessionStore`，也不镜像 transcript；
3. SDK client 完成 disconnect 后在 `finally` 中立即清理整个运行目录；hook 暴露的
   `transcript_path`/`agent_transcript_path` 既不持久化，也不作为观测缺口的回读来源；
4. 临时父目录只包含 DocFit 自己创建且带无正文 owner marker 的子目录。每次 DocFit
   启动前只扫描这个固定父目录；能够确认 owner 已退出的残留可立即清理，owner 状态无法
   确认时只有超过 24 小时且没有活跃 lock 才可清理。不跟随 symlink，也不扫描用户配置
   目录或任意 `/tmp`；
5. 正常退出的保留期是 0；进程崩溃后，残留在下一次 DocFit preflight 或操作系统临时
   目录清理前可能继续存在。文档和 UI 必须如实说明这段窗口，不能声称 hard TTL；
6. 清理失败只保存 `sdk_transcript_cleanup_failed`、残留数量和年龄区间，不保存具体路径、
   prompt 或文件名；它是 runtime privacy warning，不得被观测系统吞掉或伪装为已清理；
7. SDK 自带 `cleanupPeriodDays` 只能作为补充防线，不能替代本次运行目录的主动清理。

实现前必须用真实 SDK smoke 证明：空的运行级 user config 不影响项目 Skill、hooks、MCP
Tools、backend environment 和唯一 Subagent；进程正常退出后目录消失，强制终止后残留
能够在下次安全 preflight 被发现和清理。若某个 SDK 版本不能在该隔离目录下运行，不得
静默退回用户全局 `CLAUDE_CONFIG_DIR`，必须先重新批准隐私合同。

## 4. 观测模型

### 4.1 运行记录

每次 `docfit convert` 对应一条观测运行。网站自己的 `run_id` 只是本地投影主键，不替代
SDK `session_id`、任务目录或任何公开 CLI/Tool 标识。

运行级信息至少包括：

| 字段 | 含义 | 主要来源 |
|---|---|---|
| `run_id` | 网站内部运行标识 | 观测投影 |
| `task_ref` | 不编码路径或内容的 opaque 任务身份；CLI 结束后不可直接解析 | 薄应用壳 |
| `session_id` | Claude Agent SDK 会话标识 | SDK result |
| report schema | `conversion-report.json` 的 v1/v2 与解析状态 | App/report reader |
| 开始/结束时间 | 本次运行的观测边界 | App + SDK |
| 当前/最终状态 | 活跃、等待用户或最终 `COMPLETED/NEEDS_INPUT/ERROR` | SDK + conversion report |
| 总耗时 | 从应用接收任务到最终报告的时间 | App |
| Agent turn 数 | SDK 可观察的主 Agent turn 数 | SDK |
| Tool 调用数 | 按唯一 `tool_use_id` 计数；重复来源不重复累计 | SDK + Tool adapter |
| Subagent 数量 | 按唯一 `Agent` Tool use/`agent_id` 计数；缺少桥接的两类节点不强行合并 | SDK |
| Token 与成本 | Provider 报告值或带版本的估算值 | SDK telemetry |
| warning/error 数 | 当前最终报告与逐事件错误的分开统计 | App + Tool |
| 产物状态 | final DOCX、candidate、review、validation 是否存在且有效 | App + task directory |
| 运行版本 | app、SDK、model/backend、Skill、Knowledge、Tool、Provider 版本 | App + Tool |
| 输入/最终 hash | 输入、模板、要求和最终文档 SHA-256 | App + Tool |
| evidence mount | `unmounted/available/stale/missing/unauthorized/conflict`，历史运行默认 unmounted | 当前 Web 授权会话 |
| SDK transcript | `active/cleaned/residual/cleanup_failed/unknown`，不含路径 | App runtime privacy |

状态徽标必须保留来源语义。Tool 的 `ok/needs_input/error`、权限的 `allow/deny` 与最终
转换的 `COMPLETED/NEEDS_INPUT/ERROR` 不能被压成一个含义模糊的全局状态机。网站可以
提供统一颜色，但事件详情必须显示原始状态与来源。

如果进程结束而没有可验证的终止事件，网站显示“运行中断/终态未知”，不能自动判为
失败或成功。

### 4.2 事件记录

事件是用于阅读和定位的内部投影，不是新的公共事件协议或 event-sourcing 合同。
每个可观察事件至少保留：

| 字段 | 说明 |
|---|---|
| `source_event_id` | 来源已有的 message UUID、`tool_use_id` 或本地稳定事件 ID；用于去重，不冒充 SDK 标识 |
| `source_sequence` | 同一来源的接收顺序；并行来源不强行伪装为一个全局串行 |
| `observed_at` | 墙钟观测时间；与来源时间、本地单调时钟分开保存和展示 |
| `monotonic_offset_ms` | 相对本次 run 开始的本地单调时间，用于计算非负耗时和稳定排序 |
| `source` | `app`、`sdk`、`permission`、`tool` 或 `report` |
| `kind` | 用户任务、Agent 回复、Skill、Tool use/result、Subagent、权限、追问、终止等 |
| `actor` | main Agent、具体 Subagent、App 或 Tool adapter |
| `tool_use_id` | Tool use、result、hook 和权限判断的直接关联键；不适用时为空 |
| `agent_id` / `agent_type` | SDK 暴露时标识具体 Subagent；主 Agent 或不可用时为空/unknown |
| `parent_tool_use_id` | SDK 暴露的父 `Agent` Tool use ID；不由时间邻近推断 |
| `parent_ref` | 由已经验证的直接键生成的内部父事件引用 |
| `association_status` | `verified/partial/broken/conflict`，说明关联证据质量 |
| `status` | 来源状态，不另造领域含义 |
| `duration_ms` | 能够观测时记录；否则为 unknown |
| `summary` | 按事件类型生成的脱敏摘要 |
| `error` | 稳定错误码、origin、retryable 与安全消息摘要 |
| `evidence_refs` | 与该事件直接相关的 hash/ref/page |
| `sanitization_status` | `accepted/dropped` 及安全原因码；不保存被丢弃的原始字段 |

事件投影允许升级内部 schema，但不会成为 Skill、Tool 或 Eval 必须消费的产品协议。
删除观测数据库不能破坏任务产物；删除任务目录也不能由观测数据库重建产物。

O0.2 实现把可变摘要限制为固定 attribute-key allowlist；safe event 类型没有
`prompt/tool_input/tool_response/result/body/text/content/path/bytes/raw` 等逃逸字段。每个
事件在进入 sink 前完成 schema 与 64 KiB 大小检查；同步 projector 单次达到 10 ms、抛错、
遇到未知类型或产生无效 shape 时，只返回固定 drop receipt，不记录异常详情或 raw
fallback。禁用观测时不安装额外 SDK lifecycle hook/audit，也不执行 projector。

O0.3 在 safe event 之后提供纯直接关联投影，不读取 SDK transcript、任务文件、正文或图片，
也不写数据库。它按 `source + source_event_id + kind/phase` 做语义幂等；时间不同但安全事实
相同的事件合并，事实矛盾的变体全部保留并标为 `conflict`。Tool/Subagent/父子与证据关系
只携带直接 proof fields；四个展示维度互不覆盖，聚合指标显式区分
`reported/estimated/unknown`，coverage 降级时未知总量不补 0。

### 4.3 事件类型

首版需要覆盖：

- 任务接收与任务结束；
- 可观察的主 Agent 消息与 turn 边界；
- `Skill` 加载；
- 五个 DocFit Tool 的 use/result；
- `Agent` Tool 启动、完成或失败；
- Subagent 内部能够被 SDK 真实暴露的 Tool use/result；
- 权限允许、拒绝和拒绝原因；
- `AskUserQuestion` 发起、已回答或未回答；
- backend 尝试、超时与切换；
- 最终 conversion report 与产物检查。

一次真实运行在 Transcript 中可能呈现为：

```text
用户任务 -> Agent 可观察回复 -> 加载 Skill -> 调用 Tool -> Tool 结果
         -> Agent 再次行动 -> 启动 Subagent -> Subagent 结果
         -> 编辑 -> 渲染 -> 视觉取证 -> 验证 -> 最终回复
```

这只是对已发生事件的阅读示例，不是要求 Agent 遵循的固定调用序列。

“Transcript”是上述脱敏事件的可读串联，不是完整模型对话副本。用户任务、Agent 回复、
问题和答案默认只保存任务类型、长度、类别、状态与安全摘要，不保存原文。

### 4.4 Agent 与 Subagent 树

树只根据真实观察到的父子关系构建：

```text
Main Agent
├── Skill: docfit-school-extract
├── Tool: docx_inspect
├── Subagent: docfit-unit-analyst
│   ├── Tool: docx_inspect
│   ├── Tool: docx_visual_review
│   └── Result: unit_analysis_v1
├── Tool: docx_edit
├── Tool: docx_render
└── Tool: docx_validate
```

Subagent 节点展示：

- 启动和结束时间；
- `subagent_type`；
- 父 Agent 与调用 `tool_use_id`，仅在直接 ID 桥已经验证时展示为确定关系；
- 接收任务的安全元数据：payload 大小，以及来源直接提供时的 Knowledge ID/version、
  evidence ref/page 数量；不保存或解析 `Agent` Tool 的 prompt/description 正文；
- 实际调用过的 Tool；
- 耗时、Token 与成本可用性；
- 返回状态，以及 `unit_analysis_v1` 中经过 allowlist 的 confidence、finding/
  `evidence_requests`/cross-link 数量；不保存分析正文；
- `evidence_requests` 是否非空及其安全 ref/page 数量；
- 权限拒绝、错误与未观测区间。

如果 SDK 只暴露 `Agent` Tool 的入口和结果，没有暴露某段子调用，树必须把中间区间标为
“子事件未观测”，不能根据最终文本虚构 Tool 节点。

### 4.5 Tool 调用

每个 Tool 节点展示：

- Tool 名称与调用者；
- `tool_use_id`；
- 开始时间、结束时间和耗时；
- `ok`、`needs_input` 或 `error`；
- 脱敏输入摘要与输出摘要；
- `failure.origin`、错误码、retryable 与安全消息；
- 是否可能有副作用、`committed` 与产物是否发布；
- `document_sha256`、`object_ref`、`render_ref`、`evidence_ref` 和相关页码；
- cache hit、Provider、intent、页面数、图片字节等 Tool 专属指标。

例如：

```text
docx_edit
状态：error
耗时：1.24 s
输入文档：sha256:abc123...
操作数：6
操作类型：apply_style × 4，replace_text × 2
目标对象：obj-12、obj-18、另 4 个
committed：false
错误：postcondition_failed
正文内容：未持久化
```

输入输出摘要采用每种 Tool 的字段 allowlist，而不是对任意 JSON 先存储再遮盖：

| Tool | 可持久化摘要 | 不持久化 |
|---|---|---|
| `docx_inspect` | 文档 hash、focus、对象/风险数量、返回 ref 数 | 文本、完整对象清单、analysis 正文 |
| `docx_edit` | 输入/输出 hash、操作类型与数量、opaque ref、committed、错误 | expected/replacement 文本、文档内容 |
| `docx_render` | intent、cache、Provider、ref、页数、DPI、产物可用性 | DOCX、PDF 或页面图片内容 |
| `docx_visual_review` | render/evidence ref、模式、页码、图片数与字节 | 图片数据、OCR 文本、视觉正文 |
| `docx_validate` | 检查数、errors/issues/warnings、错误码、证据 ref | 论文片段和完整 validation evidence 文本 |

未知字段默认不持久化。新增 Tool 字段只有经过脱敏评审后才可进入 allowlist。

### 4.6 如何证明关联正确

页面中的连线必须有可复查的直接证据。首版只接受以下关联：

| 关联 | 证明条件 |
|---|---|
| Tool use -> Tool result | Tool block `id` 与至少一个 result/hook `tool_use_id` 相等；存在多个来源时所有已观测 ID 必须一致 |
| Tool -> Subagent actor | Tool lifecycle hook 的 `agent_id` 与 `SubagentStart/Stop.agent_id` 相等 |
| 父 `Agent` 调用 -> 子消息 | `Agent` ToolUseBlock `id` 与子消息 `parent_tool_use_id` 相等 |
| 子消息 Tool -> 子 actor | 子消息 ToolUseBlock `id = hook.tool_use_id`，且同一 hook 带有 `agent_id` |
| 对象 -> 文档 | `object_ref` 通过现有 Tool 规则验证，且绑定的 `document_sha256` 与当前文件重算值相等 |
| render/evidence -> 文档 | ref 内的文档 hash、Provider、profile、render/image hash 均通过现有证据检查 |
| 页码 -> 页面证据 | 页码只在已经验证的同一 `render_ref` 内解释 |

一条完整的 Subagent 证明链可以是：

```text
父 Agent ToolUseBlock.id = A
  -> 子 AssistantMessage.parent_tool_use_id = A
  -> 子 ToolUseBlock.id = B
  -> Pre/PostToolUse.tool_use_id = B, agent_id = C
  -> SubagentStart/Stop.agent_id = C
```

SDK 没有在单一事件中同时给出 `parent_tool_use_id` 和 `agent_id` 时，上述子消息与 Tool hook
是必要的桥。桥接字段缺失时，只能显示“观察到一个 Subagent 调用”和“观察到一个子
actor”，父子连线标为 `partial`；不能把两者强行合并。

关联状态含义固定为：

- `verified`：所需直接 ID 或 hash/ref 检查全部通过；
- `partial`：至少一个来源缺失，但已有信息不矛盾；
- `broken`：引用指向的事件或本地证据已经缺失、失效或未授权；
- `conflict`：两个直接来源对 ID、hash、Provider 或 profile 给出互相矛盾的事实。

这些是观测投影的证据标签，不是新的运行状态机。Tool 名称相同、时间相邻、页码相同、
文件名相似或“看起来属于同一次调用”都不能作为关联证明。重复事件按
`source + source_event_id + kind/phase` 幂等合并；无法确认是否重复时保留两条并标注冲突，
不能静默覆盖。展示顺序以来源序号和本地单调时间为主，墙钟时间只用于人类阅读。

## 5. 信息架构

网站采用五层信息结构：

```text
运行总览
  -> 单次任务总览
    -> Agent loop / Subagent 树 / 时间线
      -> 具体 Tool 或 Agent 事件
        -> 本地证据定位与进一步调查
```

### 5.1 运行总览

回答“最近哪些任务成功、失败或变慢”：

- 任务/run ID、开始时间、状态与总耗时；
- Tool 调用数、Subagent 数、turn 数；
- warning/error 摘要；
- 版本和输入指纹；
- 与选定基线相比的耗时、调用与载荷变化；
- 本地证据是否仍然可用。

默认不显示输入文件名、学校名、论文题目或正文片段。

### 5.2 单次任务总览

回答“这次任务总体发生了什么”：

- 任务、会话、版本和最终产物摘要；
- 模型/backend、Skill 与 Knowledge 版本；
- 总耗时、Token、成本与 Tool/Agent 指标；
- 总体时间线和最慢事件；
- 当前最终状态、错误与 warning；
- 输入和最终文档 hash；
- 本地证据可用性。

### 5.3 Agent loop

回答“Agent 实际按什么顺序做了什么”，提供三种互相同步的视图：

- **Transcript**：按时间阅读脱敏的用户、Agent、Skill、Tool、Subagent 和结果事件；
- **Tree**：查看主 Agent、Subagent 和 Tool 的层级；
- **Timeline**：查看顺序、并行关系、耗时和空闲等待。

这里展示实际调用，不把常见的 inspect/edit/render/validate 组合描述成预设工作流。

### 5.4 事件详情

回答“这个 Tool 为什么失败、为什么慢、与什么证据有关”：

- 来源、actor、父事件与原始状态；
- 脱敏输入/输出；
- 错误码、origin、retryable 与 permission；
- 耗时拆分；
- 副作用和发布状态；
- 证据引用与有效性；
- 可复制的调试上下文。

### 5.5 本地调查

回答“如何找到真正的详细证据”：

- 复制调试上下文；
- 为历史运行显式重新选择/挂载本地任务目录；验证通过后才可在系统文件管理器中打开
  该目录或产物；
- 复制 `object_ref`、`render_ref`、`evidence_ref`、页码或 hash；
- 生成供现有 DocFit/Claude Agent SDK 调查入口使用的只读上下文；
- 提示可以通过五个 DocFit Tool 重新取证。

网站本身不启动 Agent 或 Tool。任何后续只读调查都是用户明确发起的独立操作，使用
现有 SDK runtime 和现有只读 Tool 权限；不得从监控页面形成第二个隐藏 Agent loop。

## 6. 与本地任务数据的关系

本地任务目录是事实来源，监控网站是索引和运行投影。

```text
本地任务目录
├── 输入 DOCX
├── 工作副本
├── PDF 与页面图片
├── render evidence
├── visual-review.json
├── validation.json
└── conversion-report.json
          ^
          | 通过 hash/ref 只读定位
          |
监控网站
├── task_ref / run_id / session_id
├── tool_use_id
├── document_sha256
├── object_ref
├── render_ref / evidence_ref / page
├── 状态、耗时与错误
└── 脱敏摘要
```

稳定定位含义如下：

| 引用 | 作用域 | 失效条件 |
|---|---|---|
| `task_ref` | 一次 run 的 opaque 任务身份；不是可持久解析的路径 | CLI 授权上下文结束后默认处于 unmounted |
| `session_id` | 一次 SDK 会话 | 只用于关联，不保证本地证据存在 |
| `tool_use_id` | 一次 SDK Tool 调用 | 只在该观测运行内定位调用 |
| `document_sha256` | 一个精确文档快照 | 文件内容变化即不再匹配 |
| `object_ref` | 一个文档快照内的对象 | 文档 hash 变化即失效 |
| `render_ref` | 一个精确渲染快照 | 文件/配置不匹配、证据删除或校验失败 |
| `evidence_ref` | 一个派生视觉证据 | 对应 render/image 不可验证时失效 |
| 页码 | 一个 `render_ref` 内的视觉位置 | 不得跨 render 或 Provider 复用 |

`task_ref` 是薄应用壳在当前授权上下文中签发的不透明任务身份，不是绝对路径的编码或
hash；`run_id` 与 `task_ref` 都使用与路径、文件名和文档内容无关的随机标识。观测索引
可以保存该身份和 task-relative opaque artifact locator，但不复制
`task_ref -> path` 映射。当前 `docfit convert` 是会退出的 CLI，因此 CLI 结束后，历史运行
默认只能查看脱敏摘要，本地证据状态为 `unmounted`，不能假设独立 Web 进程仍持有原授权。

需要重新调查时，用户在认证页面发起 POST。本地调试壳可以按平台加载可选目录选择器，
把用户选择的候选任务目录转换成仅存于服务端内存的授权 capability；浏览器不能提交任意
路径字符串来绕过选择。核心转换、云端运行和平台无关的观测/证据验证代码不导入
AppleScript、GUI toolkit 或具体桌面适配器。挂载只在当前 Web 会话内有效，绝对路径只
保留在 capability 中，不写入观测索引、cookie、URL、日志或导出。无平台适配器或无图形
会话时挂载保持 `unavailable`，历史摘要和其他观测功能继续可用；真实桌面选择器 smoke
属于本地兼容性验证，不是 O0 核心完成门。验证规则是：

1. schema v2 报告的 `run_id`、`task_ref` 必须与历史记录相同；
2. `session_id` 以及 source/template/requirements/final 的所有可用 hash 必须一致；
3. 所有 artifact locator 必须是候选根内的相对路径，并通过第 7.4 节的 canonicalize、
   symlink 和目录逃逸检查；
4. schema v1 没有 `run_id/task_ref`，即使用户显式选择目录，也只能在 `session_id` 与全部
   可用输入 hash 相等时标为 `partial`，不能升级为 `verified`；
5. 任一直接标识或 hash 矛盾时拒绝挂载并显示 `conflict`，不提供“仍然打开”绕过入口。

关闭会话或重启 Web 服务后必须重新挂载。O0 不为此建立全局任务注册表，不扫描文件系统，
也不在后台自动寻找“可能匹配”的目录。

打开任何本地证据前，网站重新检查任务授权、文件存在性和适用 hash/ref。它不能仅凭
数据库中曾经记录过路径就宣布证据有效。

如果本地任务已删除、hash 已变化或引用失效，网站明确显示：

```text
本地证据不可用
原因：未重新挂载 / 文件缺失 / hash 不匹配 / 引用失效 / 权限已撤销
旧运行摘要仍可查看，但不能据此精确回放或恢复正文。
```

监控数据库不复制 DOCX、PDF、页面图片、render evidence 或 validation 正文。

## 7. 隐私与安全

### 7.1 字段留存矩阵

采集器以“明确允许才保留”为准。所有投影器先构造新的最小对象，再把它交给有上限的
事件通道；原始对象不得进入队列、数据库、应用日志、浏览器消息或导出文件。

| 类别 | 可以保存 | 条件允许 | 禁止保存 |
|---|---|---|---|
| 关联标识 | `run_id`、opaque `task_ref`、`session_id`、message UUID/ID、`tool_use_id`、`agent_id/type`、`parent_tool_use_id` | task-relative opaque artifact locator，且打开时重新授权 | 任意绝对路径、`cwd`、`transcript_path`、用户名或私人目录名 |
| 时间与顺序 | 来源序号、接收序号、墙钟时间、单调 offset、duration | Provider 时间只在标明来源时使用 | 从文件时间或相邻事件猜出的时间 |
| 运行元数据 | event source/kind、model/backend/Tool/Skill/Knowledge/SDK/App/Provider 版本、状态、计数 | backend/模型标签需确认不含凭据或用户文本 | prompt、Assistant 文本、`ResultMessage.result`、模型完整请求/响应 |
| 用量与成本 | input/output/cache Token、reported cost、num_turns、来源 | 带版本的价格估算，明确标为 `estimated` | 缺失值补 0、把估算值冒充账单 |
| Tool 摘要 | 第 4.5 节每个已命名 Tool 的 allowlist 字段 | `object_ref` 仅在结构有界且不嵌入正文时；安全消息仅来自固定模板/allowlist | 原始 `tool_input`、`tool_response`、raw error、文本参数、完整对象/validation 载荷 |
| 文档证据 | SHA-256、opaque render/evidence ref、Provider/profile、页码、数量/字节数、可用性 | `object_ref` 与页码只在绑定 hash/ref 验证通过时 | DOCX/PDF、页面/base64 图片、OCR/论文/模板/学校要求正文 |
| Agent/用户事件 | actor、任务类别、有上限的 content 字节数/选项数、是否回答、权限 decision、安全原因码 | 直接来源提供的 Knowledge ID/version、evidence ref/page 与固定枚举；只由这些允许元数据生成确定性模板摘要 | 用户任务、问题、答案、`Agent` prompt/description、Assistant 回复、Subagent 分析正文、`ThinkingBlock` 或隐藏思维链 |
| 失败 | 稳定 code、origin、retryable、interrupt、sanitizer/drop reason | 已审查的固定安全消息模板 | SDK/Provider/OfficeCLI/Adobe 原始异常体或堆栈中可能携带的文档/路径 |
| 系统与凭据 | schema/version、采集覆盖统计、SDK transcript lifecycle/残留数量/年龄区间 | 无 | transcript 路径/内容、API key、token、service principal、环境变量值或任意 credential 派生值 |

“确定性模板摘要”只根据允许字段生成，例如“`docx_edit` 六项操作未提交”；不得把原始
文本交给另一个模型生成摘要，因为那既扩大数据面，也不能证明没有正文泄漏。未知事件、
未知 Tool 或新增字段默认整字段丢弃，只有经过隐私审查和测试后才可加入 allowlist。

本矩阵只约束 O0 观测索引、日志、浏览器消息和导出。SDK 原生 transcript 可能包含本表
禁止的正文，必须由第 3.4 节的独立临时目录与清理合同管理，不能把两类存储混称为
metadata-only。

### 7.2 脱敏失败的硬边界

脱敏器、schema 校验或大小限制失败时，采集器丢弃该事件的整个可变载荷，只记录不含
原值的 `sanitization_status=dropped`、安全原因码和计数。它不能降级为保存 raw JSON、
截断后的原文、异常 `repr` 或 base64 前缀；也不能把原始载荷送入死信队列。用于排查
脱敏器的问题只能是事件来源、kind、字段名的固定枚举和代码版本。

### 7.3 SDK transcript 隐私状态

页面只展示 `active/cleaned/residual/cleanup_failed/unknown`、残留数量和年龄区间，不展示
transcript 文件名、绝对路径或内容。`cleaned` 必须来自本次主动删除成功或安全 preflight
确认目录不存在；不能因为观测索引里没有正文就推断 SDK transcript 已清理。用户删除
O0 历史不会被描述为删除 SDK transcript；两种删除动作有独立来源和回执。

### 7.4 本地 Web 安全边界

loopback 只是网络可达性限制，不是完整认证。首版 Web 安全合同固定为：

- 只绑定明确的 `127.0.0.1` 和/或 `::1`，拒绝非 loopback socket；启动时生成至少 128 bit
  随机的一次性本地登录码，由发起 CLI 直接显示在当前 TTY，用户通过同源 POST 交换
  短期会话；登录码 5 分钟过期或连续失败 5 次后立即轮换；
- 登录码和会话 secret 不进入 URL、查询参数、fragment、浏览器 local storage、应用日志、
  观测数据库或导出；一次性码使用后立即失效，服务重启后全部轮换；
- 没有交互 TTY 时不能降级为无认证服务；实现计划只能采用受保护的本地 IPC/文件描述符
  交接，或拒绝启动需要管理动作的 Web 服务，不能把 secret 改放命令行参数或环境变量；
- session secret 至少 256 bit，idle 30 分钟、absolute 8 小时后失效；cookie 使用
  `HttpOnly`、`SameSite=Strict`、`Path=/` 且不设置 `Domain`，使用 HTTPS 时同时设置
  `Secure`；
- `SameSite` 只是补充防线。每个修改请求还必须在自定义 header 中携带与当前 session
  绑定的不可预测 CSRF token；token 不放入 cookie、URL 或日志，校验失败一律拒绝；
- `Host` 必须精确匹配实际绑定的 loopback host/port，浏览器修改请求的 `Origin` 必须精确
  匹配当前 origin；不允许 wildcard/反射 CORS，不接受未授权或 `null` Origin；
- GET/HEAD 不产生副作用。删除历史、清空记录、重新挂载目录、打开文件管理器/产物等
  本地管理动作只接受认证后的 POST，并通过 CSRF 校验；
- 响应使用禁止远程 script/frame 的严格 CSP，不加载第三方字体、analytics、图片或 CDN；
- 用户选择的根目录先做 strict canonicalize。相对 artifact locator 必须逐段拒绝 symlink、
  `..`、绝对路径和设备文件，解析结果必须仍在当前挂载根内；打开前再次校验，避免检查后
  被替换造成目录逃逸；
- 未授权 `task_ref`、恶意 Host/Origin、CSRF 缺失、路径穿越、symlink 逃逸和挂载后替换
  都必须有合同测试，并只返回不含本地路径的安全错误。

这里的“只读”表示网站不能控制转换、Agent、Subagent、Tool 或任务产物。删除观测历史和
显式挂载本地证据是观测数据管理动作，不得被包装成 Agent 或文档操作。

### 7.5 本地运行与删除

- 网站遵守第 7.4 节的 loopback、认证和同源安全合同，不对局域网或公网开放；
- 观测数据默认只保存在本机，不自动上传到任何第三方 trace 服务；
- 历史记录必须支持按单次运行删除、全部清除和可配置保留上限；
- 观测文件权限不得宽于现有任务与凭据策略；
- 任何导出都继续执行同一字段 allowlist，不导出隐藏原始载荷。

默认保留天数、运行数和容量上限由第 10.5 节锁定；实现计划可以把用户配置范围收紧，
不能取消硬容量或以“方便调试”为由无限保留运行数据。

## 8. 调试上下文

每个异常事件可以复制一个最小调试上下文，用于后续本地调查：

```yaml
debug_context_schema_version: 1
run_id: run-...
task_ref: task-...
session_id: session-...
actor: main-agent | docfit-unit-analyst | tool | app
event_kind: tool_result
tool_name: mcp__docfit__docx_edit
tool_use_id: toolu_...
status: error
duration_ms: 1240
failure:
  origin: postcondition
  code: postcondition_failed
  retryable: false
document_sha256: sha256:...
object_refs: [obj-12, obj-18]
render_ref: null
evidence_refs: []
pages: []
committed: false
local_evidence: available
summary: 六项编辑未发布；正文未持久化
```

该结构是监控界面的导出格式，不是第六个 Tool、公共 Agent 消息协议或 exact replay
载荷。它不包含正文、完整参数或任意文件路径。

## 9. 运行指标

### 9.1 单次运行

- 总耗时、主 Agent turn 数和等待用户时间；
- 每个 Tool 的调用次数、成功/needs_input/error 数、累计/平均/P95 耗时；
- 最慢 Tool 与最慢单次事件；
- 重复 inspect/render/visual-review/validate 次数；
- OfficeCLI 解析次数和单次运行解析缓存命中；
- Adobe baseline/candidate API 调用与 cache hit；
- Agent 实际读取页数、重复读取页数和最终覆盖率；
- 图片输入数量与字节数；
- Subagent 数量、耗时、Token、Tool 调用与证据请求；
- 权限拒绝、用户追问、首个失败来源，以及按 App/SDK、main Agent、Subagent、Skill、
  Tool、OfficeCLI 和 Adobe 聚合的错误；
- 最终产物、validation、blocking/warning 状态。

### 9.2 Token 与成本

Token 与成本必须标记来源：

- `reported`：SDK 或 backend 直接报告；
- `estimated`：根据已知 usage、模型和带版本价格表计算；
- `unknown`：信息不足。

缺失值不能当作 0。估算值不能与 Provider 账单混称为实际成本。

“Subagent 是否减少主 Agent 上下文压力”只能使用代理指标，例如主/子 Agent Token、
显式任务包大小、主 Agent turn 数与相同样本的前后比较。界面必须标记这是相关性观察，
不能仅凭一次运行得出因果结论。

### 9.3 跨运行比较

比较前先生成可比性摘要：

- 输入、模板和要求 hash 是否一致；
- model/backend 与 Claude Agent SDK 版本是否一致；
- App、Skill、Knowledge、Tool、OfficeCLI 和 Adobe SDK 版本是否一致；
- 固定路由、任务授权与最终验证要求是否一致；
- 是否都取得相同类别的最终证据。

完全一致时标记为“严格可比”；存在已知差异时标记为“条件可比”并列出差异；输入或
验证门不同则不生成性能胜负结论。

比较内容包括：

- 总耗时、Token、估算成本；
- 各 Tool 的调用数与耗时；
- Subagent 使用与上下文代理指标；
- cache hit、Adobe API 次数、页面与图片字节；
- 重试、权限拒绝、错误与 warning；
- 最终状态和产物证据是否一致。

Agent 的具体调用序列可以作为调查线索，但不能成为必须复现的 Gold，也不能用更少调用
自动证明质量更好。

## 10. 采集完整性与失败表现

### 10.1 四个互不覆盖的展示维度

页面必须同时展示以下四类事实，不能因为转换成功就隐藏观测或隐私缺口，也不能因为
采集失败就把转换标成失败：

| 维度 | 允许值 | 权威来源 |
|---|---|---|
| 运行结果 | `COMPLETED/NEEDS_INPUT/ERROR/unknown` | App 最终结果和 `conversion-report.json` |
| 观测覆盖 | `complete/degraded/unavailable` | 各来源采集回执、drop 计数和终止边界 |
| 本地证据 | `unmounted/available/stale/missing/unauthorized/conflict` | 用户挂载状态，以及打开时的授权、存在性与 hash/ref 重验 |
| SDK transcript | `active/cleaned/residual/cleanup_failed/unknown` | 第 3.4 节的运行级临时目录与清理回执 |

这些值是四个独立的投影维度，不是控制 Agent 的新状态机。`complete` 只表示当前声明的
必需来源均已收到且没有 drop/conflict；它不表示论文质量合格。`degraded` 表示仍有可读
轨迹但存在明确缺口；`unavailable` 表示没有足够逐事件数据重建轨迹。

覆盖判断基于来源 adapter 在 run 开始/结束时的健康回执、drop/error 计数，以及已经打开
的 Tool/Subagent 生命周期是否有可解释的终止事件；不能因为“本次没有 Subagent”或
“某 Tool 调用数为 0”就判定缺失。`missing_sources` 只记录已注册来源故障、应到未到的
配对事件或明确不可用的 adapter，不根据期望工作流猜测。

O0 在 schema v2 `conversion-report.json` 中只写稳定、无正文的任务级覆盖与 runtime
privacy 摘要，不嵌入逐事件轨迹：

```yaml
schema_version: 2
run_id: run_0123456789abcdef0123456789abcdef
task_ref: task_fedcba9876543210fedcba9876543210
final_sha256: <64 lowercase hex characters or null>
observation_coverage:
  state: degraded
  events_persisted: 37
  events_dropped: 2
  missing_sources: [post_tool_use]
  last_observed_at: 2026-08-03T08:31:00Z
  failure_codes: [observer_queue_full]
sdk_transcript:
  status: cleaned
  residual_count: 0
  oldest_age_bucket: null
  failure_codes: []
```

`events_persisted` 只统计生成报告摘要前已经由本地索引确认写入的事件，不把仍在队列中的
事件算作落盘。字段不可得时用 `null/unknown`，不能补 0。该摘要是诊断投影，不参与转换
完成判定；写入失败也不能改写原有最终结果或产物发布。

### 10.2 失败矩阵

| 故障 | 转换行为 | 网站与记录必须如何表现 |
|---|---|---|
| SDK source/hook 回调异常 | 转换继续；观测异常不得从 hook 抛回 SDK | 对应 source 进入 `degraded`，记录安全错误码和缺口起点 |
| 脱敏/schema/大小校验失败 | 丢弃整个可变载荷；转换继续 | `events_dropped` 增加，只记录 `observer_sanitization_failed` 等固定码，不保留 raw fallback |
| 观测队列/配额满、观测库锁冲突或观测写入失败 | 有界非阻断写入；超限事件丢弃，转换继续 | 显示 `degraded`、drop 数和持续区间；不能无限占内存或阻塞 Tool |
| 任务文件系统或整个共享卷耗尽 | 最终 DOCX、证据或 report 可能无法写出；O0 不承诺转换继续 | 按 App/Tool 原有错误报告 task storage failure，不能伪装成纯 observer 故障 |
| 网站未启动、浏览器断开或 UI 崩溃 | collector 与转换继续 | 重连后只读已持久化事件；UI 断开不计作运行失败 |
| collector 在 run 开始时不可用 | 转换继续 | 运行结束后最多从最终报告生成任务级摘要；逐事件覆盖为 `unavailable` |
| 进程崩溃且没有最终报告 | 无法由观测面改变 | 终态显示 `unknown`，最后事件之后标记未观测区间 |
| 事件重复或跨来源乱序 | 不影响转换 | 直接 source ID 幂等去重；保留来源顺序，并行不造全局次序，矛盾显示 `conflict` |
| CLI 结束后没有重新挂载任务目录 | 历史摘要仍可读 | 证据显示 `unmounted`；不尝试解析 `task_ref` 或扫描目录 |
| 本地任务删除、授权撤销或 hash 变化 | 历史摘要仍可读 | 证据显示 `missing/unauthorized/stale/conflict`，不声称可精确回放 |
| SDK transcript 清理失败 | 文档转换事实不被 O0 改写 | 单独显示 `cleanup_failed/residual` 和安全错误码，不能声称整机 metadata-only |

运行页顶部必须给出人可以理解的提示，例如：

```text
观测降级：14:31:08 之后未收到 PostToolUse 来源；转换结果未受影响；2 个事件被丢弃。
```

“转换结果未受影响”只有在原有 App 结果和产物事实仍可读取时才展示；进程崩溃或最终
事实缺失时应写“转换结果未知”。

### 10.3 `conversion-report.json` schema v2 与旧报告

O0 将当前报告从 schema v1 升级为 v2。v2 保留全部 v1 转换字段，并新增：

- `run_id` 与 opaque `task_ref`；
- `final_sha256`，成功产物可读时绑定最终文档快照，否则为 `null`；
- 固定 shape 的 `observation_coverage`；
- 固定 shape 的 `sdk_transcript` runtime privacy 摘要。

报告文件仍属于用户选择的本地任务证据，v1/v2 既有字段可能包含绝对 artifact path、
warning/detail 文本。Web report reader 必须先执行独立 allowlist projection，只把状态、
安全 code、hash、计数、版本和 task-relative locator 放进索引；不得因为报告位于任务目录
就复制全部 JSON。

App 必须先构造不依赖 observer 的基础转换报告，再通过异常隔离的 summary provider 读取
覆盖与 transcript 清理状态。summary provider 超时、抛错或返回无效 shape 时，App 使用
固定的 `unavailable/unknown` fallback 和安全错误码，仍然原子写出 schema v2 基础报告。
只有任务目录本身无法写入时，报告写入才按现有 App storage error 失败；不能把这种情况
误报为 observer 降级。

网站 reader 只支持明确的 v1 和 v2：

- v2 按新增字段读取，缺失必需字段视为无效报告；
- v1 只能在用户显式选择目录后作为临时 `legacy_v1` 摘要读取已有转换状态、session/hash
  和产物摘要；它不自动导入历史索引，也不生成事件时间线；
- v1 的观测覆盖显示 `unavailable`、transcript 状态显示 `unknown`，所有缺失计数为 `null`
  而不是 0；如果用 session 与全部可用 hash 对照一个已有记录，因为没有 `run_id/task_ref`，
  关联最多为 `partial`；
- 未知更高 schema 版本显示 `unsupported_report_schema`，不能按 v1 猜测解析。

字段新增、v1/v2 读取、v1 缺失值、无效 v2、未知版本、summary provider 异常和基础报告
仍可写出都必须有契约测试。

### 10.4 重启后的有限对账

collector 或 Web 重启后，历史记录默认保持 `unmounted`。只有用户显式选择目录且第 6 节
验证通过，网站才能从该目录的 `conversion-report.json` 补入最终状态、hash、产物类型与
稳定汇总，并标记 `provenance=reconciled_from_report`。它不能扫描任意本地目录寻找相似
文件，不能读取 SDK transcript，也不能根据 report 反造 Tool、Subagent 或权限时间线。
逐事件缺失仍保持 `unavailable/degraded`。

### 10.5 O0 资源与性能预算

以下是首版默认硬边界。实现计划可以通过测量收紧；任何放宽都必须先更新本设计和对应
合同测试。

| 项目 | 首版预算 |
|---|---|
| 同步 projector | 合成最大合法事件下 P95 `<= 2 ms`、P99 `<= 5 ms`；单次达到 `10 ms` 即停止该可变投影并记 drop |
| 单事件尺寸 | 脱敏并编码后的 JSON 最大 `64 KiB`；超出时丢弃可变载荷，只保留有界 header/drop reason |
| 内存队列 | 最多 `1024` 个事件或 `16 MiB`，先到者为准；不得动态无限扩容 |
| 单 run 上限 | 最多 `10,000` 个事件或 `64 MiB` 脱敏事件，先到者为准；超过后只保留最高优先级事件和计数 |
| 观测存储 | 数据库、索引和 WAL 合计硬上限 `512 MiB`；不得写入任务目录 |
| 历史保留 | 默认最多 `30` 天且最多 `500` 个已完成 run，先到的上限生效；只淘汰最旧已完成 run，不淘汰活动 run |
| 磁盘低水位 | 所在卷可用空间低于 `1 GiB` 或 `5%` 中较大者时停止新的观测写入，报告 `observer_storage_low_space` |
| 进程开销 | 固定合成 benchmark 相对禁用 O0：P95 增量 wall time `<= 3%` 或 `250 ms` 中较大者，CPU time 增量 `<= 5%`，peak RSS 增量 `<= 64 MiB` |

队列至少预留 `10%` 且不少于 `64` 个槽位给最高优先级事实。优先级固定为：

1. **P0**：run/终态、coverage、SDK transcript 清理、permission deny、error/needs_input、
   Tool/Subagent terminal；
2. **P1**：Tool/Subagent start、permission allow、直接 ID、证据 ref 和耗时；
3. **P2**：progress、usage sample 和可重新计算的派生指标。

压力下先拒绝 P2，再拒绝 P1，不用低优先级事件占用 P0 预留。P0 也无法入队时，只更新
有界内存 drop/coverage 计数，并让最终报告显示 degraded；不能阻塞 SDK hook。性能门使用
确定性 synthetic runner 和最大合法 projector fixture，不能用网络/Adobe 延迟掩盖 O0
开销，也不能为 benchmark 增加 Adobe Document Transaction。

## 11. 页面与采集验收要求

O0 只有在以下事实都可自动或人工复查时才算完成：

1. 一次真实合成 `docfit convert` 运行能够近实时出现在列表中，运行结束状态与
   schema v2 `conversion-report.json` 一致；
2. Transcript 能显示真实 Skill、Tool、Subagent、权限和结果顺序；Tool use/result 通过
   同一 `tool_use_id` 精确关联；
3. 并行 Subagent fixture 能通过 `parent_tool_use_id`、子 Tool `tool_use_id` 与 `agent_id`
   证明父调用、子 actor 和内部 Tool；缺桥时为 `partial`，ID 矛盾时为 `conflict`，不得错连；
4. Tool 详情显示耗时、字段 allowlist 摘要、错误、committed 与证据引用；未知字段不入库；
5. 在 prompt、问题/答案、Tool input/output、raw error、图片字节和路径中放置隐私 canary，
   数据库、导出、应用日志和 `conversion-report.json` 均扫描不到 canary；
6. 每次真实 SDK smoke 使用独立 `0700` `CLAUDE_CONFIG_DIR` 且没有 `SessionStore`；正常退出
   立即清理，强制终止后的 owned 残留可由下一次 preflight 安全发现，并在 owner 已退出或
   模拟超过 24 小时后清理，路径不入日志；
7. 注入脱敏失败、队列/配额满、数据库锁/观测写失败与 UI 断开后，原转换最终状态、
   产物 hash 和公开 Tool 结果与无观测基线一致，页面显示正确的 coverage/drop 原因；
8. 任务文件系统耗尽测试按原 App/Tool storage failure 失败，不能声称“观测降级但转换
   未受影响”；O0 低水位不得主动吃掉任务产物所需的保留空间；
9. collector 从开始不可用时仍能完成转换，并且只允许从显式挂载目录的最终报告做
   summary-only 对账；无最终报告时终态保持 unknown；
10. 重复、乱序和缺失事件 fixture 能稳定得出去重、并行、`partial/broken/conflict` 结果，
   不使用 Tool 名称或时间邻近补链；
11. CLI 退出后的历史运行先显示 `unmounted`；显式选择正确 v2 目录后通过
    `run_id/task_ref/hash` 验证，错误目录为 conflict，v1 最多为 partial，关闭会话后不保留路径；
12. 恶意 Host/Origin、CORS、CSRF、GET side effect、未授权 `task_ref`、路径穿越、symlink
    和挂载后替换测试全部被拒绝；登录码/session secret 不出现在 URL、日志或导出；
13. schema v1/v2、无效 v2、未知版本、缺失字段和 summary provider 异常均有契约测试；
    v1 观测字段为 unavailable/null，基础 v2 report 仍可原子写出；
14. 本地证据挂载后通过授权与 hash/ref 定位，删除、修改或撤权后明确显示对应不可用原因；
15. 同一合成样本的两个运行可以比较调用、耗时、cache、页面与图片字节，缺失指标不按 0；
16. `general-purpose` 或未知 Subagent 的权限拒绝可通过直接 ID 定位；
17. 删除观测历史不会删除任务产物或 SDK transcript，删除任务产物也不会被网站伪装为
    可恢复；
18. hook、事件/队列/run、存储、保留、磁盘低水位、CPU、RSS 和 wall time 都通过第 10.5
    节预算；关闭网站、清空索引或完全禁用 O0 不改变 `docfit convert`，也不增加 Adobe
    Document Transaction。

## 12. 实现顺序与复用原则

本文只锁定产品边界。后续 O0 可执行计划按以下顺序落地：

已批准的阶段、技术基线和逐阶段成功标准见
`plans/docfit-o0-local-observability.md`。下列顺序继续作为专题设计层的强制依赖关系；
实施计划只能细化，不能倒置或绕过。

1. **SDK runtime privacy 与 report v2**：先建立运行级临时 `CLAUDE_CONFIG_DIR`、正常/崩溃
   清理、`run_id/task_ref` 和 v1/v2 report reader/writer；
2. **来源适配与隐私投影器**：为 SDK 消息、lifecycle hooks、权限、App/backend、Tool
   和最终报告建立独立 allowlist projector；原始载荷不得进入队列；
3. **关联与覆盖合同测试**：用合成 ID、并行 Subagent、缺失/冲突/乱序和隐私 canary
   fixture 锁定 `verified/partial/broken/conflict` 与 `complete/degraded/unavailable`；
4. **非阻断本地投影**：按第 10.5 节建立有界通道、优先级、容量/保留/低水位、删除能力、
   drop 计数与故障注入，证明转换结果和资源预算；
5. **Web 安全与重新挂载**：先完成登录/session、Host/Origin/CORS/CSRF、POST 和路径逃逸
   合同，再提供平台无关的目录 capability、v2 验证和会话级挂载；本地调试壳的 OS 选择器
   是可选适配器，不进入核心依赖或完成门；
6. **单次运行页**：完成运行总览、Transcript、事件详情、覆盖/privacy 状态和证据有效性；
7. **Agent 树与时间线**：只在父子关联和时间数据真实可得后展示；
8. **指标与比较**：在同一合成基线上验证 O1–O4 优化；
9. **调查交接**：最后增加复制调试上下文与打开本地证据，不在网站内启动第二个 Agent。

复用优先级是：

- 优先使用 Claude Agent SDK 公开消息流、hooks 和 OpenTelemetry 能力；
- 优先复用五个 Tool 已有 status/failure/ref/cache/Provider 字段；
- 可以复用成熟开源 trace UI 的展示组件、时间线或查询逻辑；
- 不让第三方 trace schema 反向成为 DocFit 的 Tool、Skill 或任务目录合同；
- 不要求外部 SaaS、云端 collector 或完整 prompt capture 才能运行本地页面。

具体 Web 框架、数据库、实时传输方式和开源 UI 选型留给 O0 实现计划。选型必须服从
本文件的只读、离线、脱敏、可删除与不干扰转换原则。

## 13. 与 00–06 的关系

- 01 定义它属于薄应用壳的只读视图，不改变唯一 SDK runtime；
- 02 定义它如何支撑非 Eval 性能测量与跨运行比较；
- 05 定义 hash/ref、Tool 摘要、本地证据与隐私数据边界；
- 06 把它放在 M2 后优化轨道的 O0；当前已完成 O0.0–O0.3，有界存储与网站仍待后续阶段；
- 03 的 Gold 与 04 的 Skill 不消费监控轨迹，也不因此改变。

如果后续实现需要第六个 Tool、第二个 Agent loop、远程上传正文、任务调度、跨任务
持久缓存或公开事件协议，必须先修改 00–06 并获得新的明确批准，不能以“监控需要”为由
绕过现有架构边界。
