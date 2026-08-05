# 冻结模板产物 Interface

## 产物组成

冻结模板产物包含一个不可再原地修改的干净 DOCX 和一个绑定其精确 SHA-256 的 manifest。
manifest 保存当前任务来源、固定区域、槽位、manual 区域、gap、未决项和验证引用。

它是任务级数据合同，不是学校 profile、跨任务模板包或全局 ArtifactRef。

## 槽位

每个自动槽位至少表达：

```yaml
slot_id: <task-local-id>
locator: <snapshot-bound-locator>
expected_content: scalar | paragraph_stream | composite | manual
cardinality: {min: 0, max: 1}
evidence_refs: [<current-task-evidence-ref>]
```

- `slot_id` 只在当前 manifest 内唯一。
- locator 只在 `template.sha256` 对应快照内有效。
- `min/max` 表达允许数量；`max: null` 表示无固定上限。
- 自动处理缺乏唯一 locator 时，不创建虚假槽位，改记 manual 或 gap。

locator 应包含 opaque 结构引用、相对关系和必要前置指纹。页码、bbox、颜色和近似文本
只能提供辅助证据。若多个对象满足同一 locator，合同校验失败。

## 固定区域与清理决定

固定区域保存 snapshot-bound locator、预期指纹和来源证据。清理掉的说明文字或示例值
必须保留清理决定和原来源证据，便于证明“内容消失”是有意且有据的结果。

条件文字在适用性已经确定时可以成为固定或清理决定；适用性仍未知时保留并标记
manual/unresolved，不替用户做无依据选择。

## Manual、gap 与未决项

- `manual_regions`：区域可定位，但必须由人或后续任务判断/填写。
- `gaps`：当前材料或 Tool 无法安全表达、定位或验证。
- `unresolved`：存在可描述问题，但缺少能够改变结论的证据。

这些字段是有效产物的一部分，不是失败后可以省略的附注。

## 冻结不变量

1. 干净模板可独立打开，来源模板未变化。
2. manifest 中的 template hash 与实际 DOCX 一致。
3. 所有 locator 在该 hash 上重新验证。
4. 自动槽位零命中或多命中都会阻止完成。
5. 全页视觉证据和确定性验证都绑定同一 hash。
6. manifest 生成后的任何 DOCX 写入都会使整个产物失效。

当前产品未实现完整 validator 时，Skill 必须返回 capability gap，不能自行宣布上述
不变量已经通过。
