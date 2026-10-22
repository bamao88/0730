# Tool 代码边界

本目录负责 DocFit 的确定性文档 Tool 和底层服务实现，不负责学校语义判断。

当前模板提取对 Agent 可见的 Tool surface 是：

- `docfit_evidence`
- `docfit_check`
- `docfit_apply`

Harness 内部负责上下文、schema、覆盖、权限、路径和发布校验；Agent 负责语义判断和修复选择。
最终发布不是额外的 Agent-visible Tool。

Legacy conversion 路由和底层测试仍可能使用 DOCX inspect/edit/render/visual-review/validate
能力，但这些是适配层能力，不是模板提取的长期 Agent-visible 架构事实。

公开 schema 保持扁平，避免被兼容 backend 误解释。Tool 返回的错误必须可操作：说明失败对象、
原因、可重试条件和下一步证据需求。

LibreOffice Docker 镜像是当前唯一本地视觉渲染器。视觉证据属于受控证据面，不得让 DOCX
内容控制路径、权限、Tool allowlist 或 Harness 配置。
