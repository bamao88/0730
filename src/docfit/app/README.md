# App boundary

本目录是 DocFit 薄应用壳的长期代码归属，负责：

- CLI 入口；
- Claude Agent SDK 配置和会话接入；
- 本地环境检查与 live smoke；
- 将 Skill、Knowledge 和五个 DocFit Tool 暴露给 SDK。

这里不承载论文语义、学校规则、DOCX 实现或第二套工作流。现有 M0 平铺模块
将在后续 M0 调整中迁入本目录；本次只建立计划已经规定的目录边界。
