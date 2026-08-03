# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.2 来源 adapter 与字段级隐私 projector
- Last decision delta: O0.1 通过实现、契约、真实 SDK 正常/强制终止门并提交 `3d02172`
- Last proven evidence: `168 passed`，ruff、mypy、lock、build、base doctor overall PASS；四个真实
  SDK smoke PASS；强制终止前 owned residual=1、下一次 preflight 后=0；正常退出 residual=0
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite/SDK inventory、可选
  platform adapter 与基线；O0.1 每 backend 私有 `CLAUDE_CONFIG_DIR`、owner/lock/preflight、
  随机 run/task ID、report v2 writer/reader/projector、summary 安全 fallback 与 final hash
- Next action: 定义 sanitized event schema 与 queue 只接受安全事件的 API，再逐来源实现 SDK、
  hook、App、permission、用户追问和五个 Tool projector
- Next proof: 字段 allowlist 快照、隐私 canary/超大/异常 fixture、64 KiB 大小门、deadline/drop
  receipt、P95/P99 projector benchmark 和原 Tool/permission 非干扰集成
- Stop condition: raw payload 必须先进队列、绝对路径/正文成为必需字段，或 projector 异常回抛
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.3–O0.7；O1–O4；M3
- Parked work: correlation、coverage/metrics、bounded recorder、Web/UI；O1–O4；M3
