# 应用壳代码边界

本目录负责 DocFit 薄应用壳：

- CLI 入口；
- Claude Agent SDK 配置、会话和权限接入；
- 本地环境检查、doctor 和 live smoke；
- 把 Skill、受限文件读取、受信任写入、Knowledge 与当前路由允许的 DocFit Tool 暴露给 Agent；
- 对 Agent 声称的最终产物执行独立完成门。

本目录不承载论文语义、学校规则、DOCX 细节实现、第二套 Agent runtime 或产品工作流状态机。

主 Agent 的 Read/Glob/Grep 必须走路径 allowlist；Subagent 只拿到当前任务批准的最小工具面。
Bash/Write 属于受信任能力，不能把 Read allowlist 误当作系统 sandbox。

`docfit convert` 是 legacy 论文转换路由；`docfit prepare-template` 是模板提取入口；
`docfit eval` 只转发离线核心回归。

观测面只读取已发布的安全状态、耗时、错误码、hash/ref、cache 和 renderer 摘要；观测失败
不得改变转换事实或完成门结论。
