# ADR 0003: 模板 post-unit 语义质量门先于中间编译层

日期: 2026-08-27
状态: superseded

Superseded on 2026-09-03 by `docs/contracts/template-extraction.md` and
`docs/plans/template-field-id-vocabulary-boundary-refactor.md`. This ADR is a
historical tombstone only.

当前决策已迁移为 field-vocabulary boundary：

- Runtime Agent 只基于 unit reading packet、可见文本、相邻语义块、布局线索和
  pre-input `field_id_vocabulary` 做学校语义判断。
- Post-unit Agent 输出只接受 `source_entry_id + ordered parts[]`；`reading_block_id` / `reading_range_id`
  只组织输入 reading view，不能成为 judgment scope。
- 需要字段的 part 只能选择 `field_id_vocabulary.allowed_field_ids` 中的字段。
- Harness 负责解析 ordered parts 到 `span_ref` / `slot_ref`，并验证覆盖、冲突、词表来源和
  可执行性。
- Compiler、readiness、handler、materializer、publication 和 fill-contract 生成逻辑不得创建、
  猜测、补造或迁移字段 ID。

不要再依据本 ADR 的 2026-08-27 早期输出形状设计 runtime schema、Skill、Tool feedback、
Harness gate 或测试。当前权威文件：

- `docs/contracts/template-extraction.md`
- `docs/modules/template-extraction.md`
- `docs/plans/template-field-id-vocabulary-boundary-refactor.md`
