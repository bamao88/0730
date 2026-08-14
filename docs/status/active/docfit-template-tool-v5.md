# Template Tool v5（已被取代）

- Status: `SUPERSEDED`
- Superseded by: [Agent-first template status](docfit-school-extract-v2.md)
- Historical plan: [docfit-template-tool-v5.md](../../plans/docfit-template-tool-v5.md)

Tool v5 曾把应用编排收窄到四个语义 work-item Tool 和一个视觉批次 Tool，但仍由应用选择语义
视野、推进 checkpoint、切 session 和决定下一步。2026-08-13 的架构复盘确认这仍是“传统工作流
系统 + LLM 节点”，不是目标 Agent-first 架构。

当前源码已删除 `template_*` Tool、Template Workspace 和对应状态机。其仍有价值的确定性 Word
操作被并入稳定 `docx_edit` action；历史 NJAU/Word 证据只说明底层文档机械能力，不再授权 v5
运行合同。不要从本 capsule 恢复兼容层。
