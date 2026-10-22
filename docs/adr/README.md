# DocFit ADR

状态: ADR 索引
更新日期: 2026-09-22

`docs/adr/**` 只记录未来工作不能随意推翻的重要决策。普通实现步骤、临时 bug、任务计划或
proof log 不写 ADR。

每份 ADR 使用这个结构：

```text
# ADR N: <决策标题>

日期: YYYY-MM-DD
状态: proposed | accepted | superseded

## 背景

## 决策

## 备选方案

## 后果

## 何时重看
```

如果决策仍在探索中，先放在 `docs/plans/**` 或 `docs/status/active/**`，直到它变成长期有效决策。

## 当前 ADR

| ADR | 状态 | 说明 |
| --- | --- | --- |
| [ADR 0001: 视觉语义判断与统一源对象边界](0001-template-unit-boundary-visual-first.md) | accepted | 先建立统一源对象清单；Agent 结合视觉判断功能区，Harness 解析同一源身份上的精确范围 |
| [ADR 0002: 模板 post-unit 物化采用意图编译与 handler 边界](0002-template-post-unit-materialization-boundaries.md) | accepted | post-unit materialization 的长期分层、职责边界和无遗留目标目录 |
| [ADR 0003: 模板 post-unit 语义质量门先于中间编译层](0003-template-semantic-quality-gate-boundaries.md) | superseded | 2026-08-27 质量门历史分析；字段 ID/coverage 合同已被当前模板提取 Contract 和 field-vocabulary boundary 计划取代 |
