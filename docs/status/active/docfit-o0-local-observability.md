# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.7 跨运行比较、总门与文档收口
- Last decision delta: O0.6 的离线运行总览、单次运行、Transcript/时间线、verified Agent 树与
  显式关系缺口、Tool/Subagent/事件详情、四维状态、SSE/轮询、调试上下文、证据状态和
  历史管理页面通过并提交 `40094f1`
- Last proven evidence: `280 passed`，ruff、mypy、lock、sdist/wheel、base doctor overall PASS；
  synthetic convert→SQLite→HTML、真实 loopback login/HTML/JSON/SSE、直接 ID/去重后 debug
  index、五种 evidence 状态、无副作用 route 与 packaged static 均有自动覆盖。人工 UI 覆盖
  375/768/1280、键盘/skip focus、长 ID、空/冲突状态、复制回退、无浏览器 storage 和仅
  loopback 网络；未读取正文/transcript，未调用 Adobe
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite/SDK inventory、可选
  platform adapter 与基线；O0.1 每 backend 私有 `CLAUDE_CONFIG_DIR`、owner/lock/preflight、
  随机 run/task ID、report v2 writer/reader/projector、summary 安全 fallback 与 final hash；
  O0.2 冻结 safe event schema、SDK/App/Tool/权限 projector、大小/耗时门与 drop receipt；
  O0.3 完成直接关联、Tool/Subagent lifecycle、证据 scope、coverage 维度和指标来源；
  O0.4 完成有界 queue/SQLite 历史、保留/删除、ack summary 与非阻断故障降级；O0.5
  完成 Web 安全壳、会话内证据重挂载和可选本地 platform adapter；O0.6 完成核心页面与
  调查交接
- Next action: 实现同输入/hash 条件下的 strict/conditional/not comparable 运行比较，完成
  资源、安全、故障、canary、live SDK 和 default-auto 总门，并记录 O1 基线
- Next proof: 缺失指标不产生伪胜负；observer enabled/disabled、Web/DB/UI 故障不改变
  转换终态、产物、Tool/权限或 Adobe 次数；18 项总验收和 00–06 收口一致
- Stop condition: 比较在条件不一致或 metric unknown 时生成性能胜负，default-auto 改变
  转换事实，或任一隐私、安全、资源、transcript live 门失败
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O1–O4；M3
- Parked work: O1–O4；M3
