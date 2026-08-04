# App boundary

本目录是 DocFit 薄应用壳的长期代码归属，负责：

- CLI 入口；
- Claude Agent SDK 配置和会话接入；
- 本地环境检查与 live smoke；
- 将 Skill、路径受限的 Read/Glob/Grep、受信任的 Bash/Write、Knowledge 和五个 DocFit Tool
  暴露给主 Agent。

Provider-independent P1 已完成 SDK 接线：`Agent` 对主 Agent 可见但不裸批准，SDK
原生 `PreToolUse` 权限钩子只允许具名 `docfit-unit-analyst`，该 Subagent 只看见
inspect + visual-review。`can_use_tool` 继续处理 `AskUserQuestion` 与防御性的未匹配工具默认拒绝。
为什么委派、如何拆分、选择哪些 Knowledge 和如何合并返回仍属于两个领域 Skill，
不进入本目录的应用壳逻辑。

主 Agent 的 Read/Glob/Grep 不自动批准。`PreToolUse` 与 `can_use_tool` 先解析真实绝对路径，
只允许项目 `.claude/skills/**`、产品 Knowledge Package 和当前任务 input/work/output 的
直接读取；允许时把 canonical path 写回 SDK Tool input。Bash 与 Write 则可见且自动批准，
不经过 DocFit 路径 hook，可访问 Agent 进程本来可访问的路径与环境，因此直接读取 allowlist
不是 sandbox。权限与观测事件不保存路径、命令、pattern、正文或文件内容。
`docfit-unit-analyst` 不继承主 Agent 的文件工具、Bash 或 Write。

这里不承载论文语义、学校规则、DOCX 实现或第二套工作流。现有应用模块
已经迁入本目录；`docfit convert` 只负责挂载只读输入、加载完整通用 Knowledge、调用
同一个 SDK runtime，并对 Agent 声称的最终产物执行独立完成门。`docfit eval` 只转发到
离线 core runner。论文单元识别、Knowledge 选择、委派和 Tool 顺序仍不进入应用壳。

应用壳把 SDK subprocess message buffer 固定为 16 MiB，以承载受控的多页 image
content block；Tool 自身的图片数量与字节预算仍是更窄的业务边界。convert 在某个
backend route 超时后不会仅因 credential 不同而重复等待同一 name/base URL/model
路由；Kimi 按官方 Claude Code 配置显式保持 high effort 且关闭 Tool Search，Provider
返回 HTTP 400 请求格式拒绝时也不会轮换同路由 credential 重放相同请求，而是保留安全
错误码并进入下一个不同 backend route。其他错误仍可按既定 credential 顺序恢复。

O0 本地观测已完成。`docfit convert` 默认使用 `--observation auto`，也可显式传
`--observation off` 取得无观测基线；`docfit observe` 只在 loopback 提供免登录直接打开的
只读运行、Agent loop、Tool/Subagent 详情、证据状态和跨运行比较。首次合法访问自动建立
内存短期会话，管理 POST 仍要求同源与 CSRF。观测失败不改变转换事实，
比较缺少关键条件时不产生性能结论。Web 核心只接收平台无关 capability；可选本地
picker/opener 由调试组合根延迟加载，不被核心转换或云端路径导入，也不构成完成门。
