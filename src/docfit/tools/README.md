# Tools boundary

本目录是五个 DocFit Tool 的长期代码归属：

- `docx_inspect`
- `docx_edit`
- `docx_render`
- `docx_visual_review`
- `docx_validate`

Tool 负责确定性文档能力和受控视觉证据，不负责学校规则或 Agent 语义判断。
当前实现保留 M0 合成图片传输 smoke，并已实现真实 inspect/edit/render/
visual-review/validate、快照 ref、原子发布、独立 package 检查、模板依赖闭包与图片
证据。OfficeCLI 和 Adobe PDF Services 是职责固定的具名薄适配，不共享通用 Provider
抽象；公开 schema 也不接受 backend selector。Adobe 路由使用锁定 SDK 和仓库外凭据，
不依赖本地 Word、AppleScript 或图形会话；服务端字体环境按 opaque 证据记录。

公开 schema 保持扁平，不使用兼容 backend 会误解释的 composition 关键字。当前 SDK
bridge 不把 `structuredContent` 保留给 Agent，因此 Tool 同时返回语义相同的紧凑 JSON
text；图片仍是原生 image block。Adobe adapter 使用固定 30 秒 connect 与 120 秒
read/upload timeout，visual-review 继续受图片数量/字节预算约束。

O0 观测面只读取五个 Tool 已发布的安全状态、耗时、错误码、hash/ref、cache 和 Provider
摘要，不改变 Tool schema、调用权限或执行顺序，也不从页面触发 Tool。比较页不会为了
补指标重新 render、读取正文或调用 Adobe；观测启用、关闭或失败时，五个 Tool 的公开
结果与 Adobe Document Transaction 事实保持不变。
