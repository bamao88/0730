# DocFit O0 Local Observability Active Capsule

- Capsule status: ACTIVE
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done
- Latest user intent: 执行，不是继续讨论或重新规划
- Current slice: O0.5 本地 Web 安全壳与证据重新挂载
- Last decision delta: O0.4 的有界优先级 queue、后台单 writer、SQLite v2 历史、保留/删除、
  coverage ack 和 observer/App storage 故障隔离通过并提交 `0e1bd53`
- Last proven evidence: `249 passed`，ruff、mypy、lock、build、base doctor overall PASS；
  真实 1 MiB 小容量 DB/WAL、P0 预留、busy/corrupt/readonly/低水位、bounded flush/delete、
  Web 关闭持久化和转换非干扰均通过；8 轮 48-event 合成 benchmark 为 wall P95 `+12.049 ms`
  / `+2.763%`、CPU `+2.514%`、增量 peak RSS `1,900,544 bytes`
- Completed slice batch: O0.0 Null recorder、外部私有 state root、SQLite/SDK inventory、可选
  platform adapter 与基线；O0.1 每 backend 私有 `CLAUDE_CONFIG_DIR`、owner/lock/preflight、
  随机 run/task ID、report v2 writer/reader/projector、summary 安全 fallback 与 final hash；
  O0.2 冻结 safe event schema、SDK/App/Tool/权限 projector、大小/耗时门与 drop receipt；
  O0.3 完成直接关联、Tool/Subagent lifecycle、证据 scope、coverage 维度和指标来源；
  O0.4 完成有界 queue/SQLite 历史、保留/删除、ack summary 与非阻断故障降级
- Next action: 实现 `docfit observe` 的 loopback fail-closed 服务、一次性登录/session、
  Host/Origin/CSRF/CSP 和无副作用路由，再加入会话内证据目录 capability 与 v1/v2 重验
- Next proof: 无 TTY fail closed、secret 不入 URL/日志/DB、错误 Host/Origin/CSRF 全拒绝、
  GET 无副作用、正确 v2 verified/v1 partial/错误目录 conflict，以及 traversal/symlink/替换拒绝
- Stop condition: secret 必须进入 URL、核心必须导入 GUI/AppleScript、浏览器必须提交任意
  绝对路径，或框架无法落实精确 Host/Origin/CSRF/CSP
- No-touch scope: 当前并行的 Skill、Eval、预设样式计划和 `temp/`；O0.6–O0.7；O1–O4；M3
- Parked work: 页面/UI 和跨运行比较；O1–O4；M3
