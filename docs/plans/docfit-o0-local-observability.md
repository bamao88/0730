# DocFit O0 本地运行观测实施计划

> 状态：COMPLETED（O0.0–O0.7 已完成）
> 日期：2026-08-04
> 上位合同：`docs/docfit-00-index.md`–`docs/docfit-06-development-roadmap.md`
> 目标设计：`docs/docfit-local-observability-design.md`
> 上位计划：`docs/plans/docfit-development-plan.md`（M1/M2 已完成）

## Plan Ledger

- Plan status: COMPLETED
- Session scope: o0-local-observability
- Current milestone: M2 后优化轨道的 O0 已完成；O1–O4 尚未开始
- Canonical implementation plan: `docs/plans/docfit-o0-local-observability.md`
- Design authority: `docs/docfit-local-observability-design.md`
- Start point: 已验证的 M2 `docfit convert` 基线；不重新实现 M2
- First executable phase: O0.0 基线、技术骨架与风险 PoC（DONE）
- Current phase: none；O0.7 已完成
- Completed phases: O0.0（`0200e4c` + `e0eb220`）；O0.1（`3d02172`）；
  O0.2（`bf7ab8e`）；O0.3（`524fdd4`）；O0.4（`0e1bd53`）；
  O0.5（`cb294f8` + `fadab03`）；O0.6（`40094f1` + `d45d1ed`）；
  O0.7（`d8f92b3` + `6579fa4` + `df33f92` + `17f4fea` + 本完成回执提交）
- Active capsule: `docs/status/active/docfit-o0-local-observability.md`
- Route: `$intuitive-flow` durable execution；阶段完成后先验证、提交，再进入下一阶段
- Worker strategy: 每次只委派一个有界阶段；主会话持有合同、集成、证明和最终完成判断
- Unknown-unknown scout: 计划阶段已核对 SDK 0.2.128 本地 transcript/公开 hook 字段、当前
  `convert.py`/`agent.py` 接线，以及 Starlette/Uvicorn/SQLite 官方能力；O0.0 的 SQLite
  busy 和真实 SDK fixture PoC 是核心实证，本地 GUI 选择器只验证可选适配器的失败安全，
  不改变平台无关边界或构成完成门
- Blocked on: none
- Completion claim: O0.0–O0.7 与总体 Definition of Done 已通过，O0 完成
- Deferred: O1 调用降重、O2 单次运行复用、O3 证据载荷、O4 重试收紧、M3 Eval

## Execution Contract

```text
Root goal: 按 docs/plans/docfit-o0-local-observability.md 顺序完成 O0.0–O0.7，并通过总体 Definition of Done。（ACHIEVED）
Current slice: 已完成 O0.7；O1 调用降重尚未开始。
Scope: 本计划第 11 节的跨运行可比性、指标差异、资源/安全/live 总门、观测默认启用、O1 基线和文档收口。
Non-goals: O1–O4 行为优化、M3、第二 Agent loop、远程 collector、正文持久化。
Acceptance: O0.7 成功标准和目标设计 18 项验收已有自动或明确人工回执，default-auto 不改变转换、Tool/权限或 Adobe 调用事实。
Verification: 全量 unit/contract/integration/security/fault/capacity/benchmark/live smoke + canary 扫描 + ruff/mypy/build/lock/doctor；不读取 SDK transcript/论文正文，也不为页面或比较额外发起 Adobe 调用。
Execution: 主会话为 root owner并直接完成该有界串行阶段；如范围扩张再恢复独立 worker。
Stop gate: 页面必须伪造节点/顺序/关系、读取正文/图片才能显示默认视图，或任一路由可以触发转换/Tool 副作用。
```

## 0. 计划目标

本计划把已经批准的本地观测目标设计拆成可独立验收的实施阶段。最终交付是：

- `docfit convert` 在不改变 Agent 决策和 Tool 行为的前提下，非阻断地写入脱敏运行事件；
- 本地 Web 能展示真实 Agent loop、Tool、Subagent、权限、耗时、覆盖状态和证据引用；
- SDK 原生 transcript 使用运行级临时配置目录，并有可验证的清理回执；
- 历史证据默认未挂载，只有用户重新授权并通过 report/hash/ref 验证后才能打开；
- 观测失败、Web 关闭和数据库故障不改变转换结果；
- 资源、安全、隐私与性能门全部可自动复查。

本计划只实现 O0。它不通过监控页面控制转换，不建立第二个 Agent loop、工作流、任务
队列、replay 协议或第三方 trace 平台，也不以页面上线为理由提前进入 O1–O4。

## 1. 固定实施边界

### 1.1 必须保持

- Claude Agent SDK 继续拥有唯一 Agent loop、Tool 调用和 Subagent 调度；
- 五个 `mcp__docfit__...` Tool 名称、输入输出合同和未匹配工具默认拒绝边界不变；
- `docfit-unit-analyst` 继续只读；在主/子 Agent 分工中，主 Agent 统一合并与发布；
- OfficeCLI 与 Adobe PDF Services 的固定职责、缓存和 Document Transaction 语义不变；
- 五个 DocFit Tool 与正常转换路线保持源文档只读、任务产物写入授权目录；当前受信任
  主 Agent Bash/Write 无 DocFit 路径 gate，不能把该行为合同表述为强制文件隔离；
- O0 数据库不保存论文正文、完整页面图片、完整模型请求/响应或凭据；
- conversion report 仍是任务目录内的最终转换事实，观测索引只是脱敏投影；
- 核心转换、云端运行和平台无关观测代码不导入本地 Word、AppleScript 或 GUI 适配器；
  本地调试壳的平台能力可选且不作为核心阶段完成门；
- M3、Gold、真实样本资格验证和外部人工复核继续延期。

### 1.2 明确不做

- 不采用 Langfuse、Phoenix、OpenLIT 等第三方 trace schema 作为 DocFit 内部合同；
- 不上传到 SaaS，不依赖互联网才能查看本地运行；
- 不引入 Node、SPA、前端构建流水线、WebSocket 或远程字体/CDN；
- 不读取 SDK transcript 来补采集缺口；
- 不保存 `task_ref -> 绝对路径` 映射，不扫描磁盘寻找历史任务；
- 不从相邻时间、Tool 名称或最终文本猜测父子关系；
- 不让 Web 启动、重试、取消 Agent、Subagent 或 Tool；
- 不为性能 benchmark 产生新的 Adobe API 调用。

### 1.3 扩张停止门

实现过程中如果必须引入以下任一项，停止并重新审批：

- 第六个 Agent 可见 Tool 或新的公共 Tool 协议；
- 第二个 Agent loop、工作流引擎、任务队列或 exact replay；
- 远程 collector、外部 SaaS、正文上传或完整 prompt capture；
- 跨任务持久缓存、并发转换调度或通用 Provider 抽象；
- 为历史证据建立全局绝对路径注册表；
- 放宽字段留存矩阵、Web 安全合同或第 10.5 节资源硬上限；
- 无法隔离 SDK transcript，只能继续写用户全局配置目录。

## 2. 固定技术基线

本计划锁定下面的首版实现方式。版本号在执行 O0.0 时选择与 Python 3.12 兼容的稳定版，
由 `uv.lock` 精确锁定；不得自动采用 release candidate。

| 责任 | 首版选择 | 原因与限制 |
|---|---|---|
| 转换内采集 | Python 进程内 `ObservationRecorder`，同步 projector + 有界内存队列 + 后台单写入者 | hook 只做脱敏和非阻断入队；Web 不在转换进程中 |
| 本地索引 | Python 标准库 `sqlite3`，WAL、`PRAGMA user_version` 迁移 | 单机、单用户、无需新数据库服务；Web 读与转换写可分离 |
| Web | Starlette ASGI + Uvicorn，程序化固定绑定 `127.0.0.1` | 小而明确；可实现精确 Host/Origin/CSRF 中间件和流式响应 |
| 页面 | Jinja2 服务端 HTML + 仓库内少量原生 JS/CSS | 无 Node/SPA/CDN；资源、CSP 和数据面更容易审计 |
| 近实时更新 | Server-Sent Events（SSE）或等价的单向 `StreamingResponse` | 浏览器只接收索引变化，不建立控制 Agent 的双向通道 |
| 历史变化检测 | SQLite `PRAGMA data_version` + 有界轮询 | Web 只观察其他连接提交，不要求事件总线或 daemon |
| Web 会话 | 服务端内存中的随机 session，浏览器只持有 opaque HttpOnly cookie | 不把会话内容放进可读签名 cookie，不持久化 secret |
| 证据挂载 | 当前 Web session 内存中的已验证目录 capability | 会话关闭即失效，绝对路径不进入数据库、URL、日志或导出 |
| 本地平台适配 | 调试壳组合根按需加载的可选 adapter | 核心/云端不导入；无 adapter 时挂载 unavailable，真实 GUI smoke 不是核心门 |

数据库写入由 `docfit convert` 所在进程负责；Web 使用独立连接读取。Web 的历史删除动作
只能通过窄化的 observer-admin connection 删除观测记录，不能写转换事件、任务目录或
文档。当前不支持并发转换作业，因此不为多 writer 设计新调度层；SQLite busy、锁冲突和
Web 关闭一律进入观测降级，不得阻塞 Agent/Tool。

### 2.1 计划中的公共入口

- 新增 `docfit observe [--port PORT]`：启动本地 Web，固定 loopback，默认 `PORT=0` 选择
  空闲端口，在当前 TTY 分别打印本地 URL 和一次性登录码；不提供 `--host`，登录码不放进
  URL、参数、环境变量或日志；
- `docfit convert` 提供 `--observation {auto,off}`；O0.7 总门通过后默认值已切为 `auto`，
  并保留 `off` 用于基线和故障排查；
- 不新增面向 Agent 的 Tool，不把 Web 路由当作公共自动化 API。

上述 flag 在 O0.0 由 CLI contract test 锁定。后续不得在实现中静默增加远程 host、token
query parameter 或任意路径挂载参数。

### 2.2 建议代码责任面

下面是责任边界，不要求为每一行建立新抽象。只有出现第二个真实消费者时才继续拆层。

```text
src/docfit/observability/
├── models.py       # allowlist 后的事件、状态、ID 与 schema
├── privacy.py      # 来源 projector、大小门、固定安全摘要
├── runtime.py      # run context、recorder、queue、coverage、transcript lifecycle
├── storage.py      # SQLite schema/migration、写入、查询、保留与删除
├── report.py       # conversion report v1/v2 reader/projector
├── evidence.py     # 平台无关的 session mount capability、hash/ref/canonical path 重验
├── local_debug/    # 可选 OS/GUI 适配器；仅由本地调试壳组合根延迟加载
└── web/
    ├── app.py      # Starlette routes/middleware/SSE
    ├── templates/  # 服务端页面
    └── static/     # 本地 JS/CSS，无第三方资产
```

主要接线点：

- `src/docfit/app/convert.py`：run identity、recorder 生命周期、report v2、backend attempt；
- `src/docfit/app/agent.py`：SDK 消息/hook/权限 projector 接线，不改变现有权限结果；
- `src/docfit/app/cli.py`：`docfit observe` 与 convert 观测开关；
- `tests/unit/`：纯 projector、ID、queue、storage、report、path 逻辑；
- `tests/contract/`：SDK 字段、字段留存、report schema、HTTP 安全、CLI 合同；
- `tests/integration/`：转换接线、Web/SQLite、重挂载、故障注入；
- `tests/live` 仍通过现有 smoke 命令表达，不建设第二套 live runner。

## 3. 阶段总览

| 阶段 | 状态 | 目标 | 硬依赖 | 成功后得到什么 |
|---|---|---|---|---|
| O0.0 | DONE | 冻结基线、技术骨架和高风险 PoC | 已完成 M2 | 可执行骨架、禁用基线、平台适配边界结论 |
| O0.1 | DONE | SDK transcript 隔离、run identity、report v2 | O0.0 | 两个 P1 闭环，不含逐事件 UI |
| O0.2 | DONE | 来源 adapter 与字段级隐私 projector | O0.1 | 原始载荷入队前被删除，得到安全事件 |
| O0.3 | DONE | 直接 ID 关联、覆盖状态和指标聚合 | O0.2 | 可信 Tool/Subagent 树模型与 coverage |
| O0.4 | DONE | 有界 SQLite 投影、保留、删除和故障降级 | O0.3 | Web 未启动时仍可安全积累历史 |
| O0.5 | DONE | 本地 Web 安全壳与证据重新挂载 | O0.4 | 已认证、同源、路径安全的本地入口 |
| O0.6 | DONE | 总览、单次运行、Transcript、树、详情与调查交接 | O0.5 | 核心监控页面可用 |
| O0.7 | DONE | 指标比较、资源/安全/live 总门与文档收口 | O0.6 | O0 完成，可决定是否进入 O1 |

阶段必须顺序执行。每一阶段应形成一个可回滚、可单独复查的提交；前一阶段成功标准未
满足时，不得通过 UI mock 或手工截图绕过后端合同进入下一阶段。

## 4. O0.0：基线、骨架与风险 PoC

> 状态：DONE；实现提交 `0200e4c`，平台边界与完成门收口提交 `e0eb220`。

### 目标

在改变真实转换行为之前，冻结可比较基线，锁定最小依赖、文件责任、CLI 入口和三个高
风险事实：SDK hook fixture 是否足够、SQLite 读写方式是否满足非阻断目标、本地平台
便利能力是否能与核心/云端代码完全隔离并在不可用时安全降级。

### 实施内容

1. 记录 M2 基线提交、完整测试结果和一个不调用 Adobe 的确定性 synthetic convert 指标：
   wall/CPU/peak RSS、Tool 结果、报告 hash、输出 hash；
2. 增加 `docfit.observability` 包骨架、`NullObservationRecorder` 和依赖注入点；
3. 加入 Starlette、Uvicorn、Jinja2 和 Web 测试依赖并锁定版本，不创建业务页面；
4. 建立仓库和任务目录之外的 observer data root，固定目录 `0700`、数据库 `0600`；
5. 建立 SQLite schema v1 草案与迁移测试，验证 WAL、query-only reader、busy/只读失败；
6. 用已锁定 SDK 0.2.128 建立 message/hook fixture inventory，列出每种来源的直接 ID；
7. 在 `evidence.py` 固定平台无关的内存目录 capability/selector 合同，并把最小 macOS
   目录选择器放入本地调试壳 adapter。核心转换和云端代码不得导入 adapter；平台/GUI
   不可用时返回 `picker_unavailable`，不能退化成文本路径框；真实 GUI 点选仅为可选 smoke；
8. 建立 O0 benchmark runner 和完全禁用 recorder 的对照入口；
9. 写出 `docfit observe` 与 convert 观测开关的 CLI contract test，阶段内仍默认关闭。

### 成功标准

- 全量现有测试、ruff、mypy、build、doctor 与 M2 synthetic integration 在 recorder 关闭时
  结果不变；最终 DOCX/report hash 与固定基线一致；
- `NullObservationRecorder` 不创建数据库、线程、任务目录文件或 Adobe 调用；
- SQLite WAL 下一个写入连接和一个只读连接能并行工作；锁冲突在测试预算内返回安全失败，
  不无限等待；
- 数据根权限、数据库权限、schema migration 和损坏/未知 schema 拒绝都有测试；
- SDK fixture inventory 覆盖设计来源矩阵，不支持的字段明确记为 unavailable；
- 平台无关 capability 合同不接受浏览器路径，核心转换 import graph 不加载本地调试
  adapter；合成 adapter 测试覆盖选择、取消、无 GUI 和非法结果，真实 GUI 不作为完成门；
- benchmark 能输出 wall/CPU/RSS，并证明本阶段关闭 recorder 的增量在测量噪声内；
- 技术选型与本计划不冲突，不需要 Node、远程服务或新的 Agent/Tool 协议。

### 停止条件

- SDK 公开消息/hooks 无法提供设计要求的直接 ID，且只能通过 transcript 取得；
- SQLite 必须通过长时间阻塞 hook 才能保持一致；
- 核心证据挂载必须导入具体 GUI/AppleScript 实现，或只能让浏览器提交任意绝对路径；
- Web 依赖要求 Python 3.13、引入远程资产或与现有锁文件不可兼容。

## 5. O0.1：SDK runtime privacy、run identity 与 report v2

> 状态：DONE；实现提交 `3d02172`。

### 目标

先关闭两个 P1：治理 SDK 原生 transcript 生命周期，并让历史 run 能通过随机身份与 report
重新验证。此阶段还不承诺逐事件时间线。

### 实施内容

1. 在 `run_conversion` 最外层创建随机 `run_id` 与 opaque `task_ref`，二者不编码路径、
   文件名、用户或文档内容；
2. 每次 backend SDK attempt 创建独立 `0700 CLAUDE_CONFIG_DIR`，不配置 `SessionStore`；
3. SDK client disconnect 后在 `finally` 中清理 attempt 目录，聚合本 run 的
   `active/cleaned/residual/cleanup_failed/unknown`；
4. 建立固定私有父目录、owner marker、lock/process identity 和安全 preflight；只处理
   DocFit owned 目录，不跟随 symlink，不扫描用户全局配置或任意临时目录；
5. 将 `conversion-report.json` writer 升级到 additive schema v2，保留 v1 字段，新增
   `run_id/task_ref/final_sha256/observation_coverage/sdk_transcript`；
6. 基础 report 先独立构造，观测 summary provider 超时、异常或 shape 错误时写入固定
   `unavailable/unknown` fallback，仍原子发布基础 v2 report；
7. 实现 report reader/projector：支持 v1/v2，拒绝未知更高版本，v1 缺失观测值为
   `unavailable/unknown/null`；绝对 path、warning/detail 原文不进入观测模型；
8. 将 backend attempt 失败记录为安全分类，不持久化 Provider 原始错误或 config path。

### 成功标准

- 每次真实 SDK smoke 使用独立 `0700 CLAUDE_CONFIG_DIR`，没有 `SessionStore` mirror；
- 项目 Skill、hooks、MCP、backend environment 和唯一 Subagent 在空运行级 config 下仍工作；
- 正常退出后 attempt 目录立即消失；强制终止后的 owned 残留能在下一次 preflight 被发现，
  并按 owner-dead/24 小时规则安全清理；路径和正文不进日志/report；
- schema v2 report 保留所有 v1 转换事实，并包含随机 run/task ID、最终文档 hash 与固定
  shape privacy/coverage 摘要；
- v1、有效 v2、无效 v2、未知版本、缺失字段和 summary provider 异常都有契约测试；
- v1 缺失计数是 `null` 而不是 0，关联最多为 partial；
- task 文件系统不可写时仍按原 App storage failure 失败；observer summary 失败不改变
  转换终态、产物发布或公开 Tool 结果；
- 凭据扫描和正文 canary 扫描在 report、日志和新 runtime metadata 中均为零命中。

### 停止条件

- SDK 隔离后必须退回用户全局 `CLAUDE_CONFIG_DIR` 才能加载项目资产；
- report v2 只能依赖 observer 成功才能生成；
- `run_id/task_ref` 必须保存或推导绝对路径才能工作。

## 6. O0.2：来源 adapter 与字段级隐私 projector

> 状态：DONE；实现提交 `bf7ab8e`。

### 目标

让所有原始 SDK/App/Tool 对象在进入队列前变成固定、可验证、无正文的安全事件。此阶段
先证明“能安全采”，不急于建页面。

### 实施内容

1. 定义内部 observation event schema、source ID、单调时间、墙钟时间、actor、priority、
   schema/version 和 bounded safe payload；
2. 为 SDK `AssistantMessage/ToolUseBlock/ToolResultBlock/ResultMessage` 建独立 projector；
3. 为 `PreToolUse/PostToolUse/PostToolUseFailure/SubagentStart/SubagentStop` 建独立 hook
   projector，并保留现有 Agent permission gate 的实际结果；
4. 为 App run/backend attempt/report、用户追问和五个 DocFit Tool 建独立 projector；
5. 五个 Tool 只保存设计字段矩阵允许的 status、code、count、hash/ref、page、committed、
   cache/provider 摘要，未知字段默认丢弃；
6. 原始 prompt、Tool input/output、问题/答案、raw error、图片、正文、`cwd`、
   `transcript_path`、绝对路径不得进入 queue API 类型；
7. 实施 64 KiB 事件上限、固定安全错误码、projector deadline 和 drop receipt；
8. 为每种来源建立正常、未知字段、超大载荷、异常对象和隐私 canary fixture。

### 成功标准

- 类型和 API 结构使 queue 只能接受 sanitized event，不能直接接受 SDK/raw Tool 对象；
- prompt、Tool input/output、问题/答案、raw error、路径、图片字节和正文 canary 在安全
  event、日志、临时文件中零命中；
- 五个 Tool 的成功、needs_input、error、committed、副作用、产物、hash/ref/page 摘要
  均有字段级快照测试；
- 未知事件类型、未知字段、projector 异常和超过 64 KiB 的载荷被整项丢弃或缩成固定
  header/drop reason，不保留 raw fallback；
- 合成最大合法事件下 projector P95 `<= 2 ms`、P99 `<= 5 ms`；单次达到 `10 ms` 时停止
  可变投影并记录 drop；
- 原有 permission allow/deny、用户追问和 Tool 调用结果与禁用 O0 基线一致；
- 没有读取 SDK transcript 补事件。

### 停止条件

- 必须先把 raw payload 放入异步队列才能完成脱敏；
- 某个关键 UI 字段只能保存正文、绝对路径或 Provider 原始异常才能得到；
- projector 超时会传播回 SDK hook 或 permission callback。

## 7. O0.3：直接 ID 关联、覆盖状态与指标聚合

> 状态：DONE；实现提交 `524fdd4`。

### 目标

把安全事件转换成可信的 run/Agent/Subagent/Tool 关系和指标。只能使用直接 ID/hash/ref；
不能把“看起来相邻”当作关联证明。

### 实施内容

1. 以 `run_id/session_id/message id/tool_use_id/parent_tool_use_id/agent_id` 建立关联；
2. Tool use/result 的多个来源必须对同一 `tool_use_id` 一致，矛盾标为 conflict；
3. `Agent` Tool use 与子消息通过 `parent_tool_use_id` 关联，子 Tool 与 Subagent 通过
   `agent_id + tool_use_id` 关联；
4. 文档、对象、render、evidence、page 只通过 hash/ref 和 scope 关联；
5. 实施 `verified/partial/broken/conflict`，以及运行结果、observation coverage、本地证据、
   SDK transcript 四个独立维度；
6. 实施重复/乱序幂等处理，保留来源内顺序和真实并行，不创造伪全局顺序；
7. 计算 Tool 次数/耗时、Agent turns、Token/cost source、Subagent、cache、Adobe call、页面、
   图片字节、权限和错误来源等安全指标；
8. 缺失值使用 `unknown/null`，不把“未观测到”统计为 0。

### 成功标准

- 两个交错 Subagent fixture 能准确关联父 Agent Tool、子 actor 和内部 Tool；
- Tool use/result 通过同一 `tool_use_id` 精确关联；多来源 ID 冲突得到 conflict；
- 缺桥、目标缺失、hash/ref 失配分别稳定得到 partial/broken/conflict，不错连；
- 重复和跨来源乱序 fixture 幂等，真实并行不会被伪装为串行；
- 没有任何按 Tool 名称、相邻时间、固定工作流或最终回复反推的边；
- coverage 只根据 adapter 回执、drop/error 和未闭合 lifecycle 计算；没有 Subagent 或
  某 Tool 为 0 不会自动变成 degraded；
- 指标来源为 reported/estimated/unknown，缺失 Token/cost/page 不显示 0；
- `general-purpose` 和未知 Subagent 的拒绝能通过直接 ID 落到对应事件。

### 停止条件

- 树或时间线必须依赖时间邻近猜测才能成立；
- 为了得到完整 coverage 必须规定 Agent 的固定调用顺序或次数；
- 指标需要读取页面图片、论文正文或完整模型历史。

## 8. O0.4：有界本地投影、保留与非阻断降级

> 状态：DONE；实现提交 `0e1bd53`。

### 目标

把可信安全事件持久化成有硬上限的本地历史，并证明任何 observer 故障都不会改变转换。
Web 此时仍可不存在。

### 实施内容

1. 实现 `1024 events / 16 MiB` 有界 queue、P0/P1/P2 优先级和 P0 保留槽；
2. 实现后台单 writer、批量事务、ack 后 `events_persisted`、shutdown 有界 flush；
3. 实现 SQLite tables/indexes/migration、WAL checkpoint、query API 和损坏隔离；
4. 实现单 run `10,000 events / 64 MiB`、全库 `512 MiB`、30 天/500 completed runs、磁盘
   `max(1 GiB, 5%)` 低水位；只淘汰最旧 completed run；
5. 实现按 run 删除和全部清除。删除只影响 observer 数据，不触碰任务文件或 transcript；
6. 实现 collector unavailable、queue full、quota full、SQLite busy/locked/corrupt、写入
   permission、磁盘低水位和 UI disconnected 故障注入；
7. 在 report summary 中写入已 ack 计数、drop、missing sources 和安全 failure codes；
8. Web reader 使用独立连接；普通查询 query-only，observer-admin 只允许删除观测记录。

### 成功标准

- queue、单事件、单 run、数据库、历史和低水位硬上限都有确定性边界测试；
- 至少 10% 且不少于 64 个 queue slot 留给 P0；压力下先丢 P2、再丢 P1；
- queue/配额满、DB locked/corrupt/只读、writer 崩溃、collector 未启动时转换状态、产物
  hash、Tool/permission 结果和 Adobe 调用次数与禁用 O0 基线一致；
- P0 也无法落盘时，只更新有界内存 coverage/drop 并降级，不阻塞 hook；
- `events_persisted` 只包含 report summary 读取前已 ack 的事件；
- Web 关闭后 convert 仍可写入，Web 重启能读取已提交历史；
- 删除单 run/全部历史不会删除或修改任务目录、SDK transcript 或 conversion report；
- observer 配额耗尽显示 observer degradation；任务文件系统耗尽单独按 App storage failure
  失败，两者测试和错误码不混淆；
- benchmark 相对禁用 O0 满足 wall P95 `<= 3%` 或 `250 ms` 中较大者、CPU `<= 5%`、
  peak RSS `<= 64 MiB`。

### 停止条件

- writer 必须同步阻塞 SDK hook 才能保证终态；
- observer DB 必须放进任务目录或与任务产物争用保留空间；
- 容量/保留只能靠人工清理，没有可测试的硬限制。

## 9. O0.5：本地 Web 安全壳与证据重新挂载

> 状态：DONE；实现提交 `cb294f8`。

### 目标

先建立安全边界，再开放任何历史删除、目录选择和本地文件操作。loopback 本身不算认证。

### 实施内容

1. 实现 `docfit observe`，Uvicorn 只绑定 `127.0.0.1` 空闲端口，关闭 proxy header 信任、
   access log 中的敏感字段和宽松 server 配置；
2. 启动时生成至少 128 bit 一次性登录码，只打印到交互 TTY；5 分钟或 5 次失败后失效；
3. 同源 POST 交换至少 256 bit server-side session；idle 30 分钟、absolute 8 小时；cookie
   为 HttpOnly、SameSite=Strict、Path=/、无 Domain，HTTPS 时再加 Secure；
4. 实现精确 Host/port、Origin、CSRF custom header、无 CORS、null Origin 拒绝、严格 CSP；
5. GET/HEAD 无副作用；登录、删除、清空、挂载、打开证据只接受认证 POST + CSRF；
6. 无交互 TTY 且没有受保护本地 IPC/FD 时拒绝启动管理面，不把 secret 改放 URL、CLI
   参数或环境变量；
7. Web 核心只接收注入的目录 selector/capability；本地调试壳可以延迟加载 O0.0 的可选
   平台 adapter，绝对路径只保存在当前 server session 内存；无 adapter 时挂载 unavailable；
8. v2 挂载必须验证 run/task/session 和全部输入/产物 hash；v1 最多 partial；错误目录
   conflict；关闭 session 或服务后重新变为 unmounted；
9. task-relative locator 逐段拒绝 `..`、绝对路径、设备文件和 symlink；canonicalize 后及
   实际打开前再次确认仍在 mount root；
10. 打开文件管理器/产物通过窄化 platform adapter 执行，不把 path 返回浏览器。

### 成功标准

- 非 loopback socket、错误 Host/port、恶意/缺失/null Origin、宽松 CORS 请求全部拒绝；
- 无 session、过期 session、错误 CSRF、GET side effect 和重放一次性登录码全部拒绝；
- login/session/CSRF secret 不出现在 URL、access log、数据库、导出或页面持久存储；
- 页面和响应不加载 CDN、远程 script/font/image/analytics，CSP 合同测试通过；
- 无 TTY/无受保护 IPC 时 fail closed，不降级成无认证网站；
- 历史 run 初始为 unmounted；选择正确 v2 目录后 verified，错误目录 conflict，v1 最多
  partial；Web 重启后路径消失；
- 浏览器不能提交任意绝对路径字符串；无平台 adapter 时历史证据保持 unmounted，其他
  观测页面仍可用；adapter 的真实 GUI smoke 不属于本阶段核心完成门；
- path traversal、absolute locator、symlink escape、挂载后替换和未授权 `task_ref` 全部
  被拒绝，安全错误中不包含本地路径；
- Web 的所有 route 都不能启动、重试、取消或影响 Agent/Tool。

### 停止条件

- secret 必须进入 URL 才能登录；
- 核心必须导入平台 GUI/AppleScript 才能启动，或目录挂载只能通过浏览器提交绝对路径；
- Web 框架默认行为无法落实精确 Host/Origin/CSRF/CSP；
- 文件打开必须绕过 mount capability 或 canonical path 重验。

## 10. O0.6：核心监控页面与调查交接

> 状态：DONE；实现提交 `40094f1`。

验证回执：离线 server-rendered 页面、JSON/SSE、直接关系与缺口、四维状态、调试上下文、
会话证据状态和仅观测删除均有 unit/contract/integration 覆盖；synthetic convert 落库后可
在页面读取。人工 UI 检查覆盖 375/768/1280 视口、键盘焦点、长 ID、空/冲突状态、复制
回退、无浏览器 storage 和仅 loopback 资源。阶段收口时 `280 passed`，lock、build、ruff、
mypy 和 base doctor 全部通过，wheel 包含本地模板/CSS/JavaScript，未发起 Adobe 调用。

### 目标

在安全数据面上完成用户真正需要的阅读体验：先看运行，再下钻 Agent loop、Tool、
Subagent、事件和本地证据。页面只显示实际观测事实。

### 实施内容

1. 运行总览：状态、时间、耗时、Agent turns、Tool/Subagent 数、Token/cost、错误/warning、
   coverage、transcript privacy 和 evidence mount；
2. 单次运行总览：输入/最终 hash、模型/backend、Skill/Knowledge/Tool 版本、产物和关键指标；
3. Transcript：按来源内顺序展示用户任务类别、Agent 可观察回复摘要、Skill、Tool use/
   result、权限、追问、Subagent start/stop 和最终结果；
4. Agent 树与时间线：只展示 verified 直接关系，partial/broken/conflict 用显式缺口节点；
5. Tool 详情：caller、tool_use_id、时间/耗时、状态、输入/输出摘要、code、committed、
   副作用、产物、hash/ref/page；
6. Subagent 详情：类型、任务安全摘要、Tool、Token、耗时、状态、证据缺口和权限错误；
7. coverage/privacy/evidence banner：四个维度独立显示；
8. SSE 单向刷新 run list/detail，断线后回退到有界轮询，不建立 WebSocket 控制面；
9. 调试上下文复制：使用 `debug_context_schema_version: 1` 的 allowlist 导出；
10. 已挂载证据提供认证 POST 的“打开本地产物/复制 ref”，未挂载时只显示重新授权入口；
11. 历史删除/清空界面只删除观测记录，显示不会删除任务证据或 SDK transcript。

### 成功标准

- 一次 synthetic `docfit convert` 能近实时出现在列表，终态与 schema v2 report 一致；
- Transcript 显示真实 Skill、Tool、权限、追问、Subagent 和结果顺序，不展示 hidden thought；
- Agent 树正确显示主 Agent、交错 Subagent 和内部 Tool；缺桥/冲突不会画成 verified；
- Tool/Subagent 详情覆盖设计要求字段，unknown/null 不显示为 0 或成功；
- 原始 prompt、论文正文、完整 Tool payload、raw error、图片、绝对路径和 secret 不出现在
  HTML、JSON、SSE、浏览器 storage、剪贴板导出或访问日志；
- UI 断开、刷新、SSE 重连不会增加 Agent turn、Tool、OfficeCLI 或 Adobe 调用；
- evidence unmounted/stale/missing/unauthorized/conflict 都有明确且不猜测的页面表现；
- 复制的调试上下文不含正文/路径，能够用 run/tool/hash/ref 定位后续只读调查；
- 页面可在无外网、无 Node runtime、无第三方静态资源时完整使用；
- 基本键盘导航、状态非纯颜色表达、长 ID/摘要溢出和空状态通过人工 UI 检查。

### 停止条件

- 为了让树完整必须伪造节点、顺序或父子关系；
- 页面需要读取任务正文/图片才能正常渲染默认视图；
- 浏览器能够通过某个 route 触发转换或 Tool 副作用。

## 11. O0.7：跨运行比较、总门与文档收口

> 状态：DONE；实现提交 `d8f92b3`，窄屏可用性修正 `6579fa4`，并行 transcript 归属修正
> `df33f92`，性能门稳定性修正 `17f4fea`；完成回执由本次文档提交收口。

### 目标

完成性能优化所需的可比运行视图，并一次性通过隐私、安全、故障、资源和真实 SDK 门。
只有本阶段通过，O0 才能标记完成并成为 O1 的硬前置。

### 实施内容

1. 实现同输入/模板/要求 hash 的运行选择和 comparability 摘要；
2. strict comparable 要求输入、backend/model、SDK/App/Skill/Knowledge/Tool/OfficeCLI/
   Adobe 版本、路由和最终证据类别一致；差异存在时标 conditionally comparable；
3. 比较总耗时、Tool 次数/耗时、Subagent、Token/cost source、cache、Adobe call、页面、
   图片字节、重试、权限、错误/warning 和最终证据；
4. 缺失值保持 unknown，不输出伪性能胜负；Agent 序列只作调查线索，不作 Gold；
5. 执行全部 unit/contract/integration、安全、故障注入、容量、benchmark 和 live SDK smoke；
6. 扫描 observer DB、WAL、日志、report、HTML/SSE 和导出中的隐私/凭据 canary；
7. 证明关闭 Web、清空索引和完全禁用 O0 均不改变 convert；
8. 将观测默认开关从开发期 opt-in 改为默认启用，同时保留显式禁用基线；
9. 更新 README、00–06、应用/Tool README、CLI help、active capsule 和本计划 ledger；
10. 记录 O1 基线指标，但不在本阶段修改 Agent 调用策略。

### 成功标准

- 同一 synthetic case 的两个运行可以比较，strict/conditional/not comparable 判定正确；
- 所有缺失 metrics 显示 unknown/null，不能以 0 影响排序或胜负结论；
- 目标设计第 11 节 18 项验收全部有自动或明确人工回执；
- 正常和强制终止 live SDK smoke 证明 transcript 隔离、清理和残留 preflight；
- 恶意 Host/Origin/CORS/CSRF/path/symlink/未授权 task_ref 合同测试全部通过；
- projector、queue、run、DB、历史、低水位、wall/CPU/RSS 全部满足硬预算；
- collector/DB/UI 故障不改变转换终态、产物 hash、Tool/permission 或 Adobe 调用次数；
- 任务文件系统耗尽按 App storage failure 表现，不被 observer degradation 掩盖；
- 全量验证命令通过，凭据和正文 canary 扫描零命中；
- 00–06、专题设计、README、CLI help、代码和 active capsule 一致；
- 本计划状态更新为 COMPLETED，06 的 O0 完成事实有可核对提交与测试回执；
- 只记录 O1 候选指标，不顺手实现调用降重、缓存、载荷或重试优化。

### 停止条件

- 任一隐私、安全或 transcript live 门失败；
- O0 启用后突破资源预算，且只能通过放宽设计硬上限解决；
- 默认启用会改变转换结果或增加 Adobe Document Transaction；
- 长期文档与实现无法在同一变更中对齐。

### 完成回执

- 比较实现以输入/模板/要求 hash、backend/model、SDK/App/Skill/Knowledge/Tool/
  OfficeCLI/Adobe 版本、固定路由 fingerprint、任务授权和最终验证证据为条件，稳定输出
  `strict/conditional/not_comparable`；关键条件未知或输入/验证门不同均禁止性能结论，
  所有比较结果固定 `winner=null`；
- `/compare`、`/api/compare` 与总览双运行选择器已完成；375 px 窄屏表格使用可聚焦横向
  滚动，768/1280 px、键盘、长 ID、unknown、条件差异和无外部资源均经人工检查；
- 固定 synthetic benchmark 三次样本的 baseline wall P95 为 1.20085 s，启用 O0 的 wall
  P95 增量为 19.10 ms（预算 250 ms）、CPU 增量 1.39%（预算 5%）、peak RSS 增量
  1.5 MiB（预算 64 MiB）；同步 projector、queue 和容量硬界另有自动测试；
- 在 observer DB/WAL、conversion report、HTML、JSON API、SSE、debug export 与捕获日志
  放置并扫描隐私 canary，七个表面均为 0 命中；实际卷可用率约 4% 时 observer 按合同
  进入 `observer_storage_low_space`，转换不被 observer 主动中止；
- 正常五项 SDK live smoke（image、ask-user、denied-tools、path-tools、subagent）与
  `doctor --require agent-smoke` 通过；真实 SDK 强制终止探针从 1 个 owned residual 经下一次
  preflight 清理到 0；另一条仍持活动锁的合法 attempt 不再被误算成本 run residual，
  没有读取 transcript 内容或输出路径；
- enabled/off synthetic convert 的状态、最终 hash、Tool facts、warnings、backend 和最终
  文件字节一致；observer DB 故障不改变转换，任务文件系统故障仍由 App 报告；O0 验证
  没有发起 Adobe 调用；
- O1 候选基线已锁定为重复 inspect/render、各 Tool 调用数/耗时、retries、cache/Adobe
  calls、实际查看页数/图片字节、Agent turns、Token/cost source 与主/子上下文代理指标。
  当前产品运行值在下一次授权且可比的 cached/live conversion 中记录；O0 没有为了凑
  数字制造 Adobe Document Transaction，也没有实施任何 O1 行为优化；
- 目标设计第 11.1 节逐项映射 18 项验收。未触发扩张停止门；核心与云端路径没有导入
  Word、AppleScript 或 GUI，本地调试 adapter 继续只是可选便利能力。
- 最终确定性门为 `299 passed`（另有 1 个已知 Starlette/httpx 弃用 warning）；
  `uv sync --frozen`、lock、sdist/wheel、Ruff、mypy、base doctor、五项 live receipt doctor
  与 `git diff --check` 全部通过。

## 12. 测试矩阵

| 测试层 | 主要覆盖 | 禁止替代 |
|---|---|---|
| Unit | ID、projector、allowlist、queue、coverage、correlation、metrics、report reader、path、session helper | 不调用真实 SDK/Adobe |
| Contract | SDK 字段桥、五 Tool 摘要、隐私 canary、report v1/v2、CLI、HTTP 安全、数据库 schema | 不用截图代替字段断言 |
| Integration | synthetic convert + recorder + SQLite + Web、SSE、挂载、删除、故障注入 | 不要求固定 Agent 轨迹 |
| Live SDK | Skill/hooks/MCP/Subagent、正常/崩溃 transcript 生命周期 | 不读取 transcript 补断言 |
| Benchmark | projector、queue、SQLite、全 convert enabled/disabled wall/CPU/RSS | 不调用 Adobe、网络或真实模型掩盖开销 |
| Manual UI | 信息层次、键盘、空/长/缺失/冲突状态、浏览器重连 | 不作为隐私/安全唯一证据 |

每阶段至少运行受影响的 unit/contract/integration；O0.7 运行完整门：

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit agent-smoke --case path-tools
uv run docfit agent-smoke --case subagent
uv run docfit doctor --require agent-smoke
git diff --check
```

真实 Adobe/provider smoke 只在既有回归门确实需要时复用缓存证据。O0 专属测试和 benchmark
不得制造新的 Document Transaction。

## 13. 每阶段完成回执

每个阶段完成时必须在 active capsule 记录：

- 阶段 ID、完成提交和日期；
- 新增/修改的责任面；
- 成功标准逐项回执；
- 测试命令与结果；
- 隐私 canary、安全、资源或 live 门的实际数字；
- 明确剩余缺口和下一阶段；
- 是否触发扩张停止门。

页面截图只能补充人工 UI 检查，不能替代 schema、ID、隐私、安全、失败注入或资源预算
证据。任何阶段存在未通过硬门时，状态保持 IN_PROGRESS 或 BLOCKED，不得用“基本可用”
提前标记完成。

## 14. O0 总体 Definition of Done

O0 完成必须同时满足：

1. O0.0–O0.7 全部成功标准通过；
2. 目标设计第 11 节 18 项验收逐项有回执；
3. 本地页面能从真实 SDK synthetic convert 展示可信 Agent/Tool/Subagent 轨迹；
4. SDK transcript、O0 索引和本地任务证据三类数据面有独立生命周期和状态；
5. 历史 evidence 未重新授权时绝不解析路径，授权后按 report/hash/ref 重验；
6. observer 的所有失败都安全降级，任务磁盘失败如实失败；
7. Web 的 session、同源、CSRF、CSP、路径和本地动作合同全部通过；
8. 隐私/凭据 canary 在所有持久化、传输和导出面零命中；
9. 资源和性能预算全部通过，O0 不增加 Adobe 调用；
10. 代码、README、00–06、专题设计、CLI help、active capsule 和本计划同步；
11. O1 尚未实施，只得到可用于 O1 的可信基线。

达到上述条件后，才可以由新的执行决定开始 O1 调用降重。O0 完成不表示 M3、真实论文
质量、受控试用 MVP 或外部人工复核已经通过。

2026-08-04 回执：上述 11 项同时满足，O0 标记为 COMPLETED；O1 尚未开始，必须由新的
执行决定选择首个主要指标后再进入。

## 15. 参考依据

- Starlette 提供 ASGI middleware、Trusted Host、cookie、静态资源与 streaming response
  能力；本计划仍使用自定义精确 Host/Origin/CSRF 和 server-side session，不依赖默认宽松值：
  <https://www.starlette.io/middleware/>、<https://www.starlette.io/responses/>；
- Uvicorn 支持程序化固定 host/port，本计划不暴露非 loopback host 配置：
  <https://www.uvicorn.org/settings/>；
- SQLite WAL 允许 reader 与 writer 并行，但仍可能返回 busy；本计划把 busy 视为 observer
  degradation，并使用 `user_version` 管理应用 schema：
  <https://www.sqlite.org/wal.html>、<https://www.sqlite.org/pragma.html>。
