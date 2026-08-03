# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.4 有界本地投影、保留与非阻断降级
- Last decision delta: O0.3 的直接 ID/hash/ref 关联、幂等冲突、四维状态和安全指标通过并
  提交 `524fdd4`
- Last proven evidence: `216 passed`，ruff、mypy、lock、build、base doctor overall PASS；
  交错 Subagent、缺桥/目标、冲突、重复/乱序、unknown 指标和生产 safe-event 接线均通过
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite/SDK inventory、可选
  platform adapter 与基线；O0.1 每 backend 私有 `CLAUDE_CONFIG_DIR`、owner/lock/preflight、
  随机 run/task ID、report v2 writer/reader/projector、summary 安全 fallback 与 final hash；
  O0.2 冻结 safe event schema、SDK/App/Tool/权限 projector、大小/耗时门与 drop receipt；
  O0.3 完成直接关联、Tool/Subagent lifecycle、证据 scope、coverage 维度和指标来源
- Next action: 实现 `1024 events / 16 MiB` 优先级 queue、后台单 writer 与 SQLite 事件/run
  投影，再加入 ack summary、保留/删除和配额/磁盘/锁故障降级
- Next proof: P0 保留槽、queue/单事件/单 run/全库硬上限、WAL/query-only、bounded flush、
  busy/corrupt/readonly/quota/低水位/writer 故障注入，以及转换状态/产物/Adobe 非干扰对比
- Stop condition: writer 同步阻塞 SDK hook、DB 进入任务目录，或容量/保留依赖人工清理
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.5–O0.7；O1–O4；M3
- Parked work: Web 安全壳、证据挂载、页面/UI；O1–O4；M3
