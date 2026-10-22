# DocFit 文档管理原则模板

本文是后续 DocFit 文档整理的默认原则。目标不是补写更多实现说明，而是让文档保持稳定、
分层、可审查，并适合人和 Agent 快速判断当前边界。

核心原则：

> 文档约束方向和边界，评测和测试约束行为，代码表达实现。

## 1. 默认文档面

人类当前事实优先放在：

- `README.md`
- `ARCHITECTURE.md`
- `STATUS.md`
- `docs/human/**`

`AGENTS.md` 和 `CLAUDE.md` 只放 Agent 启动规则、工作方式和人类文档指针。它们不承载产品事实、
模块状态或长期架构真相。

计划、执行过程、历史证据、调试记录和生成报告应放在 `.planning/**`、`docs/plans/**`、
`docs/status/active/**`、`docs/retrospectives/**`、`output/**` 或对应 evidence 目录中。只有当
人类文档明确提升它们时，它们才成为当前事实入口。

## 2. 分层写文档

- 全局架构文档：写产品模块、责任边界、共同原则和稳定数据流。
- 模块 Contract：写黑盒边界，包括 allowed inputs、forbidden reads、required outputs、状态语义、
  隐私边界、CLI/API 成功失败语义和验收门。
- Handoff Contract：写模块之间能相信什么，尤其是 ID、hash、顺序、来源追溯和下游禁止重新判断的内容。
- Eval / CI Inventory：用 YAML/JSON 管理 case、source、Registry、Gold、命令、expected、gate 和隐私级别。
- Status / Evidence Index：只写当前状态、最新 proof、blocker、next proof 和证据入口，保持短。
- ADR / Decision Notes：只记录未来不能随便推翻的长期决策。

## 3. 什么不要写进稳定文档

除非它本身是外部合同，不要把这些内容写进 Contract、架构索引或跨模块 handoff：

- 当前 batch size、并发数、retry 次数、prompt 长文本或 checkpoint 内部字段。
- 某次运行的完整 timing table、失败流水账或临时性能诊断。
- 当前函数名、私有 helper、内部数据结构细节。
- 能由测试、Eval 或 case inventory 更准确表达的行为。
- 其他模块不应该依赖的实现选择。

如果实现重构但外部行为不变，文档通常不应跟着改。

## 4. 写前检查

修改或新增文档前先判断：

1. 这段内容是在约束产品目标、模块边界或交接合同，还是在复述当前实现？
2. 未来实现重构但外部行为不变时，这段内容是否仍必须成立？
3. 它是否能由测试、Eval 或 case inventory 更可靠地表达？
4. 它是否混入了其他模块的责任？
5. 它是否包含真实学生正文、受限路径、私有样本细节或不该公开的证据？
6. 它是否会让未来 Agent 把历史方案误认为当前架构？
7. 下游真正需要知道的是实现细节，还是稳定输出合同？

判断结果：

- 长期必须保持的边界：写入 Contract、Handoff 或 ADR。
- 当前实现选择：留在代码、测试或局部注释。
- 当前进展：写入短 Status / Evidence Index。
- 验收行为：写入 Eval / CI Inventory。
- 历史过程：放入 planning、status active、retrospective 或 evidence 目录。

## 5. 模块 PR 的落地顺序

1. 先确认或更新全局模块责任和当前状态。
2. 更新本模块 Contract，只保留黑盒边界。
3. 更新相关 Handoff Contract，说明下游能依赖什么、不能重新判断什么。
4. 把可执行 case 与 gate 迁入 Eval / CI Inventory。
5. 把 active status 压成短状态索引。
6. 删除、归档或迁移会误导未来 Agent 的历史实现细节。

完成后的理想状态是：新 Agent 先读全局架构，负责某模块时读本模块 Contract，集成时读
Handoff，行为是否达标交给 Eval/CI，具体实现留给代码和测试。
