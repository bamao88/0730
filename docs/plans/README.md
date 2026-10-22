# DocFit 计划

状态: 当前计划清单
更新日期: 2026-09-22

`docs/plans/**` 默认不是项目真相来源。计划只描述一次任务：目标、非目标、涉及文件、
实现步骤、验收标准、测试方法和风险。任务完成后，长期有效结果必须迁移到 Contract、
`ARCHITECTURE.md`、`STATUS.md`、Eval 入口或 ADR。

## 活跃计划

| 计划 | 用途 |
| --- | --- |
| [template-harness-repair-20260923.md](template-harness-repair-20260923.md) | 实施中：阶段 0、1 完成；继续修订可靠性与最终视觉发布门，E2E / 产品验收尚未完成 |
| [docfit-field-style-property-closure.md](docfit-field-style-property-closure.md) | 当前活跃的 style-property closure 工作，用于 handoff/fill readiness |
| [template-field-id-vocabulary-boundary-refactor.md](template-field-id-vocabulary-boundary-refactor.md) | 全流程源对象身份的唯一实施计划；2026-09-22 起以首次判断前清单、统一切换、真实验证三步门为当前范围，Phase 0–8 保留历史 |

源定位独立计划已[合并](template-source-location-unification.md)，不再并行推进。

## 已完成 / 已迁移

已完成模板提取 redesign 和 post-unit materialization 分层的长期结论已经迁移到 Contract、
模块边界、根架构、ADR、测试入口和 Eval/replay 文档。历史 plan 只保留 tombstone 或
handoff 价值，不得被重新提升为当前执行规则。

| 计划 | 状态 |
| --- | --- |
| [refactor-post-unit-materialization.md](refactor-post-unit-materialization.md) | 已由 field-vocabulary boundary 计划和 Contract 取代，仅保留历史 tombstone |

## 支撑设计

| 设计 | 用途 |
| --- | --- |
| [template-story-aware-unit-boundary-model-20261006.md](template-story-aware-unit-boundary-model-20261006.md) | 正文功能区与辅助 Word story 分轴表达；NJAU/PKU 已回放，NJAU 单元 E2E 通过，后续阶段待做 |
| [docfit-content-field-registry/DESIGN.md](docfit-content-field-registry/DESIGN.md) | 当前 Field Registry 设计与快照 |
| [docfit-template-extraction-eval/DESIGN.md](docfit-template-extraction-eval/DESIGN.md) | 模板提取 offline Eval 设计 |
| [docfit-template-extraction-eval/PLAN.md](docfit-template-extraction-eval/PLAN.md) | Eval 仍处于 Human Gold gate 时的实现 ledger |
| [docfit-libreoffice-visual-evidence-v2.md](docfit-libreoffice-visual-evidence-v2.md) | 当前 LibreOffice V2 视觉证据设计 |

## 清理规则

已完成 milestone plan、被取代的 Tool 设计、一次性 debugging plan 和历史 implementation ledger
不得被提升为当前真相。如果已完成计划包含长期产品价值，把这些价值迁移到 Contract、模块边界、
Eval 设计、Gold contract、ADR 或短 status 文件中。
