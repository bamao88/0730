# DocFit O0 Local Observability Active Capsule

- Capsule status: COMPLETED
- Source plan: `docs/plans/docfit-o0-local-observability.md`
- Root goal: 按批准计划完成 O0.0–O0.7，并通过 O0 总体 Definition of Done（ACHIEVED）
- Latest user intent: 完成 O0 本地观测实施，不恢复 M3，也不顺手实施 O1–O4
- Current slice: none；O0.7 跨运行比较、总门与文档收口已完成
- Completion commits: O0.0 `0200e4c` + `e0eb220`；O0.1 `3d02172`；O0.2
  `bf7ab8e`；O0.3 `524fdd4`；O0.4 `0e1bd53` + `54907ec`；O0.5
  `cb294f8` + `fadab03`；O0.6 `40094f1` + `d45d1ed`；O0.7 `d8f92b3` +
  `6579fa4` + `df33f92` + `17f4fea` + 最终文档回执提交
- Delivered surface: 私有 SDK transcript 生命周期、run/task identity、report v2、来源级
  allowlist projector、直接 Tool/Subagent/hash/ref 关联、四维状态、安全指标、有界 queue/
  SQLite 历史、保留/删除/低水位与非阻断降级、免登录 loopback Web、自动短期会话、会话内证据重挂载、
  运行总览、Transcript/时间线、verified Agent 树、详情、SSE/轮询、调试上下文和
  strict/conditional/not_comparable 跨运行比较
- Deterministic proof: O0 收口时免登录简化后的全量回归为 `314 passed`；后续主 Agent
  权限切片的当前全量回归为 `312 passed`（均有 1 个已知 Starlette/httpx 弃用 warning），build/lock/
  ruff/mypy/base doctor 通过；enabled/off
  synthetic convert 的终态、最终 hash、Tool facts、warnings、backend 和文件字节一致；
  observer storage failure 不改变转换，任务文件系统失败仍由 App 报告
- Resource proof: 三次 fixed synthetic benchmark 的 wall P95 增量 19.10 ms（预算
  250 ms）、CPU 增量 1.39%（预算 5%）、peak RSS 增量 1.5 MiB（预算 64 MiB）；实际卷
  可用率约 4% 时安全进入 `observer_storage_low_space`
- Privacy/security proof: observer DB/WAL、report、HTML、JSON API、SSE、debug export 和
  捕获日志七个表面 canary 零命中；免登录直接打开、自动 session、Host/Origin/CORS/
  CSRF/POST/path/symlink/task-ref 合同通过；浏览器 storage 为空且只访问 loopback
- SDK proof: image、ask-user、denied-tools、path-tools、subagent 五项 live smoke 与
  `doctor --require agent-smoke` 通过；后续权限切片已用 denied-tools/path-tools v3 证明
  主 Agent Bash/Write 自动批准、无 DocFit 路径 gate，同时直接 Read 与 Subagent gate
  保持；真实强制终止探针留下 1 个 owned residual，下一次
  preflight 清理后为 0；持活动锁的其他合法 attempt 不计作本 run residual；未读取
  transcript 内容或输出路径
- UI proof: 375/768/1280 px、键盘与 focus、长 ID、unknown、条件差异、禁止性能结论、
  comparison 横向滚动、空状态、无第三方资源和无 console error 已检查
- O1 candidate baseline: 重复 inspect/render、各 Tool 调用数/耗时、retries、cache hit/
  render executions、实际查看页数、图片字节、Agent turns、Token/cost source 和主/子上下文代理
  指标；具体产品运行值留给下一次授权且可比的 cached/live conversion，O0 未为测量制造
  新 renderer execution
- Next decision: 如继续，先批准 O1 的单一主要指标和可比样本；O1 尚未开始
- Stop condition: 任何 O1–O4、M3、第二 Agent loop、第六 Tool、远程 collector、正文
  留存、跨任务持久缓存，或让核心/云端导入 Word、AppleScript、GUI adapter，都需要新的
  明确批准
- No-touch scope: M3、Gold、真实样本资格验证、外部人工复核；后续已完成的主 Agent
  Bash/Write 权限切片属于独立合同，不改写 O0 完成范围
