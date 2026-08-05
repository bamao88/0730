# Tool 使用与恢复

当需要选择具体 Tool、处理失败或判断旧证据是否还能使用时读取本文。

## Inspect

用 `mcp__docfit__docx_inspect` 取得当前文件 hash、结构事实、有效样式和 opaque 对象引用。
引用只属于返回它的快照。文件变化、前置条件失败或目标歧义后，重新 inspect。

## Edit

用 `mcp__docfit__docx_edit` 修改工作副本。每次提交保持范围小而语义完整，带当前快照
前置条件，并只接受 `committed: true` 且后置检查通过的结果。不要直接修改 OOXML，也
不要让 Bash/Write 代替文档编辑合同。

## Render 与视觉检查

用 `mcp__docfit__docx_render` 产生新页面证据；用
`mcp__docfit__docx_visual_review` 查看已有 render 的整页、crop 或对比图。visual review
不会产生新 render。页码只在对应 `render_ref` 内成立，不能作为编辑身份。

修改前建立足够的视觉基线；修改中按风险查看受影响页面；最后一次写入后，为最终 hash
重新生成并检查全部页面。旧 render 可以用于对比，不能证明新快照通过。

## Validate

用 `mcp__docfit__docx_validate` 从来源与最终候选独立核对结构、固定内容、清理结果、
产物绑定和阻断项。Tool 调用成功不等于结果通过；读取结构化发现和证据引用。

## 按错误语义恢复

- 零命中或多命中：重新观察、增加独立信号或降级为 manual/gap。
- 快照/前置条件失效：重新 inspect 当前副本，不重放旧引用。
- 编辑未提交或后置检查失败：不消费输出，缩小修改并查明原因。
- 页面证据不可读：对同一 render 请求受控 crop；不是盲目重复渲染。
- 固定后端失败：保留 verification/capability gap，不用另一职责的预览冒充最终证据。
- 没有新证据：不要循环重试；询问、保留或停止。
