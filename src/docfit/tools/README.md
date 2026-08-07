# Tools boundary

本目录是五个 DocFit Tool 的长期代码归属：

- `docx_inspect`
- `docx_edit`
- `docx_render`
- `docx_visual_review`
- `docx_validate`

Tool 负责确定性文档能力和受控视觉证据，不负责学校规则或 Agent 语义判断。
当前实现提供真实 inspect/edit/render/visual-review/validate、快照 ref、原子发布、独立
package 检查、模板依赖闭包与图片证据。LibreOffice 是唯一视觉渲染器，OfficeCLI 仅提供
结构读取、编辑与验证；不存在 Provider 选择、自动回退或第二条视觉路径。

公开 schema 保持扁平，不使用兼容 backend 会误解释的 composition 关键字。当前 SDK
bridge 不把 `structuredContent` 保留给 Agent，因此 Tool 同时返回语义相同的紧凑 JSON
text；图片仍是原生 image block。visual-review 按需栅格化并限制单次返回图片数量。

O0 观测面只读取五个 Tool 已发布的安全状态、耗时、错误码、hash/ref、cache 和 renderer
摘要，不改变 Tool schema、调用权限或执行顺序，也不从页面触发 Tool。比较页不会为了
补指标重新 render 或读取正文；观测启用、关闭或失败时，五个 Tool 的公开结果保持不变。
