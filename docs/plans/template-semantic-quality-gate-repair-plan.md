---
plan_scope: template-semantic-quality-gate
status: SUPERSEDED
created: 2026-08-27
superseded_on: 2026-09-03
superseded_by: docs/plans/template-field-id-vocabulary-boundary-refactor.md
retention: historical tombstone only
---

# 模板 post-unit 语义质量门修复计划

本计划已被 `docs/plans/template-field-id-vocabulary-boundary-refactor.md`
和 `docs/contracts/template-extraction.md` 取代，只保留为历史 tombstone。

当前合同不再接受本计划早期探索过的旧字段别名、旧结构绑定形状、Agent-authored coverage、
自然语言 fallback 或 post-unit runtime Tool 物化协议。后续实现、测试和排障只能依据当前边界：

- Runtime Agent 只看到 unit reading packet、可见文本、相邻语义块、布局线索和
  pre-input `field_id_vocabulary`。
- Agent post-unit 输出只能是 `scope.reading_block_id` / `scope.reading_range_id`
  上的 ordered `parts[]`，并且只从输入词表选择 `parts[].field_id`。
- Harness 负责把 ordered parts 映射到底层 Word runs/ranges，生成可追踪的
  `span_ref` / `slot_ref`，并验证覆盖、冲突、词表来源和可执行性。
- Compiler、handler、materializer、publication 和 fill-contract 生成逻辑不能创建、
  猜测、补造或迁移字段 ID。
- 旧输出形状、旧字段别名、旧 fallback 和依赖后置字段推断的旧测试必须删除，
  或反转为 fail-closed 证明。

如需了解当前阶段目标、验收标准和执行记录，请只读：

- `docs/plans/template-field-id-vocabulary-boundary-refactor.md`
- `docs/contracts/template-extraction.md`
- `docs/modules/template-extraction.md`
