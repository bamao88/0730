# DocFit Current Development Capsule

- Capsule status: COMPLETED
- Visual architecture supersession: 2026-08-07 clean break 已由
  `docs/plans/docfit-libreoffice-visual-evidence-v2.md` 与对应 active capsule 取代本文件中
  旧视觉后端、intent、成本和 live evidence 描述；这些历史证据不再满足当前视觉合同
- Source plan: `docs/plans/docfit-development-plan.md`
- Child plan: `docs/plans/docfit-m1-tools-v1.md`
- Latest user intent: 保持已完成 M2 基线，按
  `docs/plans/docfit-o0-local-observability.md` 完成 O0；O0.0–O0.7 已通过，执行回执见
  `docs/status/active/docfit-o0-local-observability.md`；完成已知 Kimi Claude Code HTTP 400
  请求格式兼容 hotfix，O1 尚未开始，M3 继续延期
- Current slice: M0–M2 产品链路及其非评测支撑已完成；当前计划无剩余开发项
- Frozen baseline: `7cd72fc`（`feat: complete DocFit M2 conversion baseline`）；该提交
  已在提交前通过全量确定性、doctor、live 产品门和凭据值扫描
- Follow-on status: 06 第 6.6 节的核心转换优化边界与 O0 可执行计划已经批准；O0.0–O0.7
  已完成，O1 尚未开始；
  不改变本 capsule 的 COMPLETED 状态，也不构成 M3 恢复或通过
- Approved follow-on design: `docs/docfit-local-observability-design.md` 定义薄壳内本地
  只读观测页；当前已有 privacy-safe 逐事件投影、runtime 接线、直接关联/指标聚合、
  有界 SQLite 历史索引、免登录 loopback 安全壳、自动短期会话、会话内证据重挂载、核心监控页面与跨运行
  比较；O0 总门已通过
- Approved execution plan: `docs/plans/docfit-o0-local-observability.md` 按 O0.0–O0.7
  锁定 transcript/report、projector、关联、存储、Web 安全、页面和最终验收的实施顺序；
  当前状态为 COMPLETED / O0.0–O0.7
- Required first slice: O0 先以来源级 allowlist projector 在原始载荷入队前完成脱敏，
  采集 SDK 实际 Agent/Skill/Tool/Subagent/权限事件；Tool use/result 通过 `tool_use_id`，
  Subagent 通过 `parent_tool_use_id + child tool_use_id + agent_id`，本地证据通过重验
  hash/ref 证明，缺桥或矛盾显示 partial/conflict；稳定无正文的 coverage 汇总进入扩展后
  的 schema v2 `conversion-report.json`；每次 SDK 运行使用私有临时
  `CLAUDE_CONFIG_DIR` 且管理 transcript 清理；CLI 结束后历史证据默认 unmounted，用户
  显式选择目录并通过 report/hash 验证后才可打开；Web 直接打开并具备自动短期
  session/同源/CSRF/路径安全；
  采集/观测存储/UI 故障非阻断且必须显示 degraded/unavailable，不得记录正文、完整图片、
  完整模型历史、隐藏思维链、凭据或未经授权的绝对路径
- O0 gate: 隐私 canary 扫描、交错 Subagent/缺失/冲突/重复/乱序 fixture、证据失效测试和
  projector/队列/观测存储/collector/UI 故障注入、transcript 正常/崩溃清理、v1/v2 report、
  显式挂载、恶意 Host/Origin/CSRF/path/symlink 和资源预算全部通过；观测关闭或失败不得
  改变转换状态、产物 hash、Tool/权限结果或 render execution 次数；任务文件系统耗尽仍按原
  storage failure 报告；否则不得进入 O1
- First measured target: 先减少没有产生新快照或新证据的重复 Tool 调用。当前两页真实
  合成基线观察到 render 6 次、visual-review 11 次、validate 4 次、inspect 3 次；这些
  是待优化的历史观测，不是固定流程、调用上限或验收 Gold
- Follow-on order: O0 观测 → O1 调用降重 → O2 单次运行解析/渲染复用 → O3 页面批次、
  crop/contact sheet 与图片载荷 → O4 同条件无效重试；每次只设一个主要指标并保留全部
  普通产品回归门
- Completed foundation: M0、通用 Knowledge v1、P1 两个 Skill/选择性 Knowledge/唯一
  只读 Subagent；五个 Tool、M2 薄壳与 M3 core Eval 的既有实现保留
- Fixed adapter contract: OfficeCLI 1.0.143 负责 inspect/edit/validate/语义定位；固定 Docker
  LibreOffice 25.2.3.2 是唯一视觉 renderer；Poppler 建立索引并按需派生图片；无本地
  Word、AppleScript、GUI session、远程视觉凭据或视觉后端回退
- Frozen M2 evidence: `uv sync --frozen`、lock check、sdist/wheel、ruff、strict mypy、124
  pytest、base/provider/agent-smoke doctor、真实 SDK 合成 convert 与 diff check 全部 PASS；
  O0 的 299-test 与 live 总门见 O0 active capsule；core Eval 7/7（41 assertions）仅作为
  已存在的可选开发资产
- Current visual proof: 固定镜像、真实 OfficeCLI+LibreOffice M1 链路、V2 MCP 原生图片块和
  三校“联系表→页面→对象局部图”服务链均已通过；当前证据和 live 限制见 V2 active capsule
- Current blocker: 当前默认仍选择 `MiniMax-M2.7`。V2 Tool 已产生原生 image block，M2.7
  按官方合同只支持文本与 Tool 相关内容块；bounded `MiniMax-M3` image live 已在相同
  Anthropic-compatible 接口 PASS，证明无需 base64 文本或文件 Read 兼容层。后续是默认模型
  升级和 M3 只读 Subagent qualification；Kimi 当前候选仍在 Tool 循环层 error。
- Receipt truth: V2 image/subagent case version 已提升，旧回执不再有效；当前
  `doctor --require agent-smoke` 为 NOT_READY。此前 denied-tools/path-tools v3 的权限证据
  不因视觉迁移失效，但不能替代新的视觉 live receipt。
- Live M2 proof: MiniMax 真实 SDK convert 返回 COMPLETED；两 Skills 与五 Tool 均有调用，
  源 hash 不变，根目录 final.docx、当时的 candidate PDF/ref、2 页全页 review、
  validation 均发布；candidate 绑定 final hash，errors=0、verification_gap=0、blocking=0
- Live defects fixed: 兼容 backend 不支持 JSON Schema composition；SDK MCP bridge 丢弃
  structuredContent；只读输入 mode 被 copy2 传播到编辑副本；同 route 超时重复轮换 key。
  Kimi 现显式保持官方 high-effort Tool 上下文并关闭 Tool Search；HTTP 400 请求格式拒绝
  使用安全错误码且不再轮换同 route credential 重放。
  历史远程 SDK 默认写超时不足以上传复杂 DOCX；SDK 默认 1 MiB 消息 buffer 无法承载真实
  页面图片；过长小字号 image-smoke marker 导致 OCR 不稳定；无凭据 CLI 测试污染真实
  smoke 回执；成功 conversion report 重放中间 Agent 的旧 warning/summary。九项均已有
  修正和回归证明
- Deferred M3 evidence: 旧视觉合同下授权复杂样本曾完成 15 页全页 Agent review、页 7
  局部 crop、对象 anchor 对照和独立高风险复核；该证据已因 V2 clean break 失效；源 hash
  不变，私有正文未进入仓库。结果为 FAIL，共 6 个 blocking finding；外部人工签字为
  NOT_PERFORMED。该证据不属于当前完成门，不继续作为 blocker，也不代表 M3 通过
- Deferred scope: M3 Skill/E2E Eval、Gold、真实样本资格验证和外部人工复核；恢复时
  依据 06 第 7 节另建计划；同时延期 M4/M5、第三引擎/通用 Provider、更多 Subagent/
  第二 Agent loop、并发与跨任务持久缓存、OCR/更多格式、精确版式/像素判定、高级 Word
  对象编辑/桌面兼容性、集中式 trace/实验服务、Eval 平台/replay/学校数据库
- Stop condition: 当前计划与 O0 已完成；任何第六 Tool、第三引擎、第二 Agent loop、恢复
  M3 或长期合同冲突须先请求决定；开始 O1 时先锁定单一主要指标和可比样本
- No-touch scope: M4/M5、面向转换用户的 GUI/API/任务队列、学校规则持久化、通用
  Provider 抽象；O1–O4 完整切片与 M3 尚未开始；已知 Kimi HTTP 400 的窄正确性
  hotfix 不构成 O4 启动
