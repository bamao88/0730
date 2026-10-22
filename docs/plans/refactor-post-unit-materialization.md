---
refactor_scope: post-unit-materialization
status: DONE
created: 2026-08-26
superseded_on: 2026-09-04
superseded_by: docs/plans/template-field-id-vocabulary-boundary-refactor.md
retention: historical tombstone only
---

# Post-unit Materialization 分层重构迁移计划

本计划完成了 2026-08-26 的 materialization package 分层迁移，但其字段绑定、正文结构和
Tool 交接描述早于 field-vocabulary boundary 重构。它不再是当前模板提取执行规则。

当前 post-unit materialization 只消费 Harness accepted semantic set：

- Agent 输出 `scope.reading_block_id` / `scope.reading_range_id` 上的 ordered `parts[]`。
- `parts[].field_id` 只能来自本轮 pre-input `field_id_vocabulary.allowed_field_ids`。
- Harness 解析 ordered parts，生成 `span_ref` / `slot_ref`，并验证覆盖、冲突、词表来源和可执行性。
- Compiler、readiness、handler、materializer、publication 和 fill-contract 生成逻辑只能消费
  Harness-accepted typed output，不得从自然语言、模板文字、Registry label、旧字段别名或旧
  coverage shape 推断字段 ID。
- 发布槽位 identity 是 Harness `slot_ref`，不是运行时生成的业务槽位 ID。

如需当前架构和验收依据，请只读：

- `docs/plans/template-field-id-vocabulary-boundary-refactor.md`
- `docs/contracts/template-extraction.md`
- `docs/modules/template-extraction.md`
- `docs/adr/0002-template-post-unit-materialization-boundaries.md`
