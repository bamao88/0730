# DocFit 文档入口

状态: 文档目录入口
更新日期: 2026-08-18

本文负责 `docs/` 目录的文档路由和维护规则。项目启动仍从根目录 `README.md`、
`STATUS.md`、`ARCHITECTURE.md` 和 `AGENTS.md` 进入；不要从这里递归读取所有文档。

## 文档面

| 文档面 | 典型位置 | 生命周期 |
| --- | --- | --- |
| 当前真相 | 根目录 `README.md`、`STATUS.md`、`ARCHITECTURE.md` | 长期，必须保持当前有效 |
| Agent 操作 | 根目录 `AGENTS.md`、`CLAUDE.md`，必要时 `docs/agents/**` | 长期，只放稳定规则和操作经验 |
| 模块与合同 | [modules/](modules/)、[contracts/](contracts/) | 模块边界或交接产物变化时更新 |
| 任务执行 | [plans/](plans/)、[status/active/](status/active/) | 短期到中期，任务结束后归档或提炼 |
| 决策记录 | [adr/](adr/) | 长期，低频新增，过期时 superseded |
| 操作手册 | 必要时创建 `docs/runbooks/**` | 中长期，命令或环境变化时必须更新 |
| human 背景 | [human/](human/) | 面向人的讨论、学习、复盘和评审材料 |
| 证据归档 | `output/**`、`temp/**`、必要时 `docs/retrospectives/**` | 证明当时发生过，不直接代表当前事实 |

## 当前入口

| 需要什么 | 读取哪里 | 说明 |
| --- | --- | --- |
| 模块上下文 | [modules/README.md](modules/README.md) | 三个并行模块的下一层路由 |
| 模板提取合同 | [contracts/template-extraction.md](contracts/template-extraction.md) | `prepare-template` 的黑盒输入、输出和失败语义 |
| 模板提取模块流程 | [modules/template-extraction.md](modules/template-extraction.md) | 完整流程、分层职责、unit-boundary、post-unit、resume proof 和调试归因 |
| 详细文档索引 | [docfit-00-index.md](docfit-00-index.md) | `docs/` 下重要文档的二级索引 |
| ADR | [adr/README.md](adr/README.md) | 长期重要决策 |
| 计划 | [plans/README.md](plans/README.md) | 一次任务的计划和执行证据 |
| human 文档 | [human/README.md](human/README.md) | 面向人的讨论、学习、复盘和评审材料 |
| 测试与 Eval | [../tests/README.md](../tests/README.md) | 生成测试与 Actual-vs-Gold 评分入口 |

## 文档维护

- 修改文档前先确认目标层级：当前真相、模块边界、合同、计划、ADR、human 背景或证据。
- 保留链接前检查目标是否仍是当前事实；过期链接应更新或移除。
- `docs/plans/**` 和 `docs/status/active/**` 是任务证据。任务完成后，不要让它们继续充当项目真相。
- `docs/human/**` 是 human-facing 背景，不是 Agent 默认上下文。确认后的结论应提升到 Contract、模块文档、Skill、test 或 ADR。
- 索引文档只做路由，不展开长计划、历史证据或模块内部细节。
- 长期有效的新事实应从 plan、status capsule、bug 记录或 human 讨论中提炼到正确文档面。
- 临时证据只证明“当时发生过”，不能直接覆盖当前真相。
- 长期文档默认使用中文。
