# DocFit 详细文档索引

状态: 二级索引
更新日期: 2026-08-18

本文只索引 `docs/` 下的重要文档，不定义当前架构、项目状态、模块合同或 Agent 操作规则。
当前入口和文档生命周期规则见 [README.md](../README.md)、[STATUS.md](../STATUS.md)、
[ARCHITECTURE.md](../ARCHITECTURE.md)、[AGENTS.md](../AGENTS.md) 和 [docs/README.md](README.md)。

不要从本文递归读取所有链接。先根据任务选择对应文档面，再继续进入下一层。

## 按任务读取

| 任务 | 入口 | 说明 |
| --- | --- | --- |
| 选择产品模块 | [modules/README.md](modules/README.md) | 模板提取、用户内容提取、final word 生成的上下文路由 |
| 查看模板提取合同 | [contracts/template-extraction.md](contracts/template-extraction.md) | `prepare-template` 的输入、输出和失败语义 |
| 查看模板提取模块流程 | [modules/template-extraction.md](modules/template-extraction.md) | 完整流程、分层职责、unit-boundary、post-unit、resume proof 和调试归因 |
| 查看系统结构补充 | [docfit-01-architecture-core.md](docfit-01-architecture-core.md) | 架构细节补充；上位结构以根目录 `ARCHITECTURE.md` 为准 |
| 查看测试说明 | [../tests/README.md](../tests/README.md) | 生成测试、Eval、manual diagnostics 的入口分离 |
| 查看 Gold 体系 | [docfit-03-gold-system-design.md](docfit-03-gold-system-design.md) | Student、Template、Filling Truth 的长期合同 |
| 查看本地可观测性 | [docfit-local-observability-design.md](docfit-local-observability-design.md) | observer 和可视化证据设计 |
| 查看 ADR | [adr/README.md](adr/README.md) | 重要长期决策索引 |
| 查看计划 | [plans/README.md](plans/README.md) | 当前计划、已完成计划和支撑设计索引 |
| 查看 active status 证据 | [status/active/](status/active/) | 阶段状态 capsule，只在处理对应主题时读取 |
| 查看 bug 记录 | [bugs/](bugs/) | 具体 bug 的复现、归因和修复证据 |
| 查看 human 背景 | [human/README.md](human/README.md) | 面向人的讨论、学习、复盘和评审材料 |

## 支撑设计

| 文档 | 用途 |
| --- | --- |
| [plans/docfit-content-field-registry/DESIGN.md](plans/docfit-content-field-registry/DESIGN.md) | Field Registry 设计与快照入口 |
| [plans/docfit-template-extraction-eval/DESIGN.md](plans/docfit-template-extraction-eval/DESIGN.md) | 模板提取 offline Eval 设计 |
| [modules/template-extraction.md](modules/template-extraction.md) | 模板提取完整流程、分层职责、unit-boundary、post-unit 和阶段恢复设计 |
| [../evals/template-extraction/stage-replay.md](../evals/template-extraction/stage-replay.md) | 模板提取中间阶段 replay 入口 |
| [plans/docfit-template-extraction-eval/PLAN.md](plans/docfit-template-extraction-eval/PLAN.md) | Eval 仍处于 Human Gold gate 时的实现 ledger |
| [plans/docfit-libreoffice-visual-evidence-v2.md](plans/docfit-libreoffice-visual-evidence-v2.md) | LibreOffice V2 视觉证据设计 |
| [status/active/docfit-school-extract-v2.md](status/active/docfit-school-extract-v2.md) | 模板提取短状态证据 |

## 不在本文维护

- 项目是什么、怎么跑、主要入口：维护在 [README.md](../README.md)。
- 当前可用能力、已知问题、下一步：维护在 [STATUS.md](../STATUS.md)。
- 模块边界、数据流、关键接口、扩展点：维护在 [ARCHITECTURE.md](../ARCHITECTURE.md)。
- 三模块下一层上下文路由：维护在 [modules/README.md](modules/README.md)。
- 文档生命周期和维护规则：维护在 [docs/README.md](README.md)。
- Agent 操作规则和提交纪律：维护在 [AGENTS.md](../AGENTS.md)。
