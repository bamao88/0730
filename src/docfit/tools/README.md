# Tools boundary

本目录是五个 DocFit Tool 的长期代码归属：

- `docx_inspect`
- `docx_edit`
- `docx_render`
- `docx_visual_review`
- `docx_validate`

Tool 负责确定性文档能力和受控视觉证据，不负责学校规则或 Agent 语义判断。
Provider 适配和内部 DOCX 模块只有在对应里程碑实际实现时才增加；本次不创建
Provider 抽象。
