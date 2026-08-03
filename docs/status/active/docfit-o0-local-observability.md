# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.0 基线、技术骨架与风险 PoC
- Last proven evidence: 设计与实施计划提交 `4924e84`；当前生产代码没有 observability
  package、Web 依赖、report v2 或 transcript isolation
- Next action: 建立 Null recorder、repository-external state root、SQLite v1 migration/
  reader-writer PoC、SDK source fixture inventory、原生目录选择器 PoC、benchmark/CLI contract
- Next proof: O0.0 focused tests + ruff/mypy + `uv lock --check` + build + base doctor；观测关闭时
  M2 synthetic convert 结果不变且不创建 observer 数据
- Stop condition: 触发计划 O0.0 的 SDK direct-ID、SQLite nonblocking、native picker 或依赖停止门
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.1–O0.7；O1–O4；M3
- Parked work: transcript/report v2、event projectors、correlation、bounded recorder、Web/UI
