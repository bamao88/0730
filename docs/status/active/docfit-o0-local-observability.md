# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.3 直接 ID 关联、覆盖状态与指标聚合
- Last decision delta: O0.2 的 safe event、字段级 projector、SDK/App/Tool/权限接线与
  非干扰门通过并提交 `bf7ab8e`
- Last proven evidence: `201 passed`，ruff、mypy、lock、build、base doctor overall PASS；四个真实
  SDK smoke PASS；最大合法事件 P95/P99、64 KiB/10 ms 门、隐私 canary 与禁用路径均通过
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite/SDK inventory、可选
  platform adapter 与基线；O0.1 每 backend 私有 `CLAUDE_CONFIG_DIR`、owner/lock/preflight、
  随机 run/task ID、report v2 writer/reader/projector、summary 安全 fallback 与 final hash；
  O0.2 冻结 safe event schema、SDK/App/Tool/权限 projector、大小/耗时门与 drop receipt
- Next action: 只用 `run_id/session_id/message id/tool_use_id/parent_tool_use_id/agent_id` 和
  hash/ref 建立幂等关联，再计算独立 coverage 维度与带来源的安全指标
- Next proof: 两个交错 Subagent、缺桥、冲突、重复、乱序 fixture；直接 ID 边；
  verified/partial/broken/conflict；reported/estimated/unknown 指标与未知值不归零
- Stop condition: 任何树边依赖相邻时间、Tool 名称、最终回复或固定工作流猜测，或指标读取正文/图片
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.4–O0.7；O1–O4；M3
- Parked work: bounded recorder、SQLite、Web/UI；O1–O4；M3
