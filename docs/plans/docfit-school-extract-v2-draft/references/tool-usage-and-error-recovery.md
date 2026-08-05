# Tool 使用与错误恢复

## Inspect

使用 `mcp__docfit__docx_inspect` 取得来源 hash、结构、有效样式、对象引用和不支持对象。
每次文档 hash 变化后重新 inspect。旧 ref 可以解释历史决定，不能驱动当前编辑。

## Edit

使用 `mcp__docfit__docx_edit` 只修改新的工作副本。执行前确认输入 hash、目标 ref、预期
指纹和清理依据；把能够在同一快照验证的操作作为原子批次提交。`committed: false` 或
后置检查失败的文件不能成为候选产物。

## Render 与视觉检查

- 在需要理解原始页面关系时请求 `baseline`。
- 修改过程中需要低成本反馈时请求 `edit_feedback`。
- 冻结候选值得做交付级页面检查时请求 `candidate_verification`。
- 使用 `mcp__docfit__docx_visual_review` 查看已有 render 的页面、crop 或 compare。

Agent 只表达 intent，不选择后端。页码和 bbox 只在对应 render 内成立，不能单独作为
编辑身份。冻结前必须查看绑定最终 hash 的全部页面。

## Validate

使用 `mcp__docfit__docx_validate` 从来源模板和冻结候选重新取证。目标合同需要核对：
来源不变、候选可打开、固定内容、槽位索引 hash/唯一性、manual/gap、全页视觉覆盖和
blocking finding。

当前 `docx_validate` 没有返回其中任一必要事实时，将该事实记录为 capability gap；不要
用已有的普通内容保留 warning 推导新合同已经通过。

## 恢复

| 失败 | 恢复 |
|---|---|
| ref 陈旧或 hash 变化 | 重新 inspect，并重建受影响决定 |
| locator 零命中或多命中 | 缩小范围、询问或记录 gap，不猜测 |
| 文字功能不明 | 保留内容并记录 unknown/manual |
| 编辑未提交或后置检查失败 | 隔离产物，不继续冻结 |
| 最终视觉证据缺失 | 保留 verification gap，不完成 |
| validator 不支持必要合同 | 返回 blocked + capability gap |
| 相同失败且没有新证据 | 停止重复调用 |
