# 2026-08-20 Agent 只做语义判断

范围: 模板提取 post-unit、Tool/Harness/Schema 设计。

记住: Agent 只承担学校模板语义判断；hash、checkpoint、task root、stale ref、coverage、
DOCX 物化、发布账本和 provenance 不能交给 Agent 记忆或区分。post-unit 脚手架必须先有
体系化交互合同，再按合同改 Tool、Harness、Skill 和 schema。不要设计成每个对象判断后让
Agent 手动调用 `docfit_check(action_plan)` 过门禁；应由 Harness 在阶段完成点自动验收对象判断全集。

原因: 之前把 `template.sha256`、`requirements.sha256`、`field_registry.sha256` 和泛化的
`source_hash` 同时暴露给 Agent，导致 Agent 在 Tool 参数里传错 hash。症状发生在 Tool call，
根因是接口 affordance 不清晰；schema 数量和命名平铺也会把机械记账伪装成 Agent 任务。
同类问题也会表现为每个对象判断都要求 Agent 手动 check/apply，导致简单需求被脚手架复杂化。
当用户给出两个示例问题时，不要只 patch 这两个点；先反推整个阶段合同是否缺少对象全集、
完成判定、反馈包、重试语义、执行边界、失败归因和 Skill 改进闭环。
