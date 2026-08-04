# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.6 核心监控页面与调查交接
- Last decision delta: O0.5 的 loopback fail-closed 服务、一次性登录/server-side session、
  Host/Origin/CSRF/CSP、无副作用 route、会话内证据 capability、v1/v2 重验和窄化 macOS
  picker/opener 通过并提交 `cb294f8`
- Last proven evidence: `274 passed`，ruff、mypy、lock、build、base doctor overall PASS；
  unit/contract/真实 loopback integration 覆盖非 loopback/错误 Host/Origin/null Origin、登录
  重放与失败上限、idle/absolute expiry、CSRF/GET、无 TTY fail closed、v2 verified、v1
  partial、错误 ID/hash、traversal/absolute/device/symlink/replacement、重启丢失 mount、
  删除仅影响 observer；响应和安全错误不含本地路径，核心 import 不加载 platform adapter
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite/SDK inventory、可选
  platform adapter 与基线；O0.1 每 backend 私有 `CLAUDE_CONFIG_DIR`、owner/lock/preflight、
  随机 run/task ID、report v2 writer/reader/projector、summary 安全 fallback 与 final hash；
  O0.2 冻结 safe event schema、SDK/App/Tool/权限 projector、大小/耗时门与 drop receipt；
  O0.3 完成直接关联、Tool/Subagent lifecycle、证据 scope、coverage 维度和指标来源；
  O0.4 完成有界 queue/SQLite 历史、保留/删除、ack summary 与非阻断故障降级；O0.5
  完成 Web 安全壳、会话内证据重挂载和可选本地 platform adapter
- Next action: 在既有安全壳上实现运行总览、单次运行、Transcript、Agent/Subagent 树与
  时间线、事件详情、四维状态 banner、SSE/轮询、调试上下文和认证后的证据入口
- Next proof: HTML/JSON/SSE 仅含 allowlist 数据；直接 ID 的 verified/partial/conflict 展示
  正确；unknown/null 不补 0；断线/刷新不增加 Tool/Adobe 调用；证据状态、键盘、溢出和
  空状态通过自动与人工检查
- Stop condition: 页面必须伪造节点/顺序/关系、读取正文/图片才能显示默认视图，或任一
  route 可以启动、重试、取消或影响 Agent/Tool
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.7；O1–O4；M3
- Parked work: 跨运行比较与 O0 总门；O1–O4；M3
