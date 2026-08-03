# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: 按最新边界修正 O0.0：核心/云端平台无关，本地调试 adapter 可选
- Resolved blocker: `native_picker_ui/mac_locked` 不再是核心完成门；无 GUI 时挂载保持
  unavailable，不能阻塞 O0 或使核心导入 AppleScript/GUI
- Last decision delta: 用户明确平台适配边界；从 BLOCKED 恢复 ACTIVE，重新运行无头 O0.0 门
- Last proven evidence: O0.0 基础提交 `0200e4c`；全量 `143 passed`，ruff、mypy、lock、build、
  base doctor 通过；SDK direct-field gaps 为空；10,000 次 Null recorder 基准低于 1ms
- Completed slice batch: Null recorder、外部私有 state root、SQLite v1/WAL/query-only/busy PoC、
  SDK 字段 inventory、原生 picker 失败安全、benchmark 和 CLI contract 已落地
- Next action: 运行平台隔离合同、可选 adapter 合成测试和 O0.0 全门；通过后关闭 O0.0 并进入 O0.1
- Next proof: 核心 import graph 不加载 `local_debug.macos`，无 GUI 安全 unavailable，focused/
  full tests、ruff、mypy、lock/build 和 base doctor 通过
- Stop condition: 触发计划 O0.0 的 SDK direct-ID、SQLite nonblocking、核心路径挂载或依赖停止门
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.1–O0.7；O1–O4；M3
- Parked work: transcript/report v2、event projectors、correlation、bounded recorder、Web/UI
