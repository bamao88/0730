# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.1 SDK transcript 隔离、run identity 与 conversion report v2
- Last decision delta: 用户明确平台适配边界后，O0.0 按无头核心门验收完成并进入 O0.1
- Last proven evidence: O0.0 提交 `0200e4c` + `e0eb220`；`144 passed`，ruff、mypy、lock、
  build、base doctor 通过；核心 import graph 不加载 `local_debug*`；SDK gaps 为空
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite v1/WAL/busy、SDK
  inventory、可选平台 adapter、benchmark/CLI contract；synthetic convert wall 7.17s、CPU
  4.06s、peak RSS 87,556,096 bytes，final/report SHA-256 为 `b52153cb…1fe7` / `e562b003…bd33`
- Next action: 实现运行级私有 `CLAUDE_CONFIG_DIR` 生命周期、随机 run/task ID、report v2
  writer/reader 与 observer summary 安全 fallback
- Next proof: report v1/v2 契约、正常/异常 summary、owned transcript preflight/cleanup、转换
  非干扰集成测试；随后真实 SDK 正常/强制终止 lifecycle smoke
- Stop condition: 隔离 config 破坏项目 Skill/hooks/MCP，基础 report 依赖 observer，或 ID 需要路径
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.1–O0.7；O1–O4；M3
- Parked work: event projectors、correlation、bounded recorder、Web/UI；O1–O4；M3
