# DocFit O0 Local Observability Active Capsule

- Capsule status: BLOCKED
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.0 代码与自动化证明已完成；等待真实 macOS 原生目录选择器点选证明
- Blocker fingerprint: `native_picker_ui/mac_locked`；选择框和 Open-and-Save Panel Service 已实际
  拉起，但锁屏阻止 Computer Use 点击，取消后安全返回 `picker_unavailable`；相同锁屏状态已在
  连续三次目标轮次中复现，等待用户手动解锁
- Root cause classification: 外部本机 UI 会话不可用；不是产品代码、SDK 或 SQLite 失败
- Last decision delta: 达到连续三次相同 blocker 的阈值，因此从 ACTIVE 转为 BLOCKED
- Last proven evidence: O0.0 基础提交 `0200e4c`；全量 `143 passed`，ruff、mypy、lock、build、
  base doctor 通过；SDK direct-field gaps 为空；10,000 次 Null recorder 基准低于 1ms
- Completed slice batch: Null recorder、外部私有 state root、SQLite v1/WAL/query-only/busy PoC、
  SDK 字段 inventory、原生 picker 失败安全、benchmark 和 CLI contract 已落地
- Next action: 用户解锁 Mac 后重跑 `NativeDirectoryPicker.select()`，在原生选择框选择任意目录，
  仅验证返回 `selected` 且结果是目录；通过后关闭 O0.0 并进入 O0.1
- Next proof: 真实 picker 返回 `status=selected`、`selected_directory=true`，且不输出绝对路径；
  随后复核 O0.0 focused tests 和阶段状态
- Stop condition: 触发计划 O0.0 的 SDK direct-ID、SQLite nonblocking、native picker 或依赖停止门
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.1–O0.7；O1–O4；M3
- Parked work: transcript/report v2、event projectors、correlation、bounded recorder、Web/UI
