# DocFit 设计文档索引（00）

> 状态：架构收缩版
> 日期：2026-07-30

## 一句话架构

DocFit 以 **Claude Agent SDK** 为运行时边界，产品只维护五类资产：

```text
Skill + Knowledge + Tools + Eval + 薄应用壳
```

DocFit 不再自建 Agent 工作流运行时。会话、Agent loop、工具调用、上下文延续、用户追问与恢复能力均优先使用 Claude Agent SDK；只有论文领域能力留在 DocFit。

## 文档清单

| 编号 | 文档 | 回答的问题 |
|---|---|---|
| 01 | `docfit-01-architecture-core.md` | 产品边界是什么，五类资产如何协作 |
| 06 | `docfit-06-project-structure.md` | 整个仓库如何组织，目录之间如何依赖 |
| 04 | `docfit-04-skills-design.md` | Skill 如何指导 Agent，而不变成固定工作流 |
| 05 | `docfit-05-tools-and-data-design.md` | Knowledge 如何组织，Tools 提供哪些确定性能力 |
| 02 | `docfit-02-testing-and-iteration.md` | 如何用 Eval 驱动 Skill、Knowledge 与 Tools 迭代 |
| 03 | `docfit-03-gold-system-design.md` | Eval case 与 Gold 数据如何保持简单、可维护 |

`docs/human/` 存放面向人的示例，不定义架构。

01 是稳定架构基线；02–06 是各类资产的设计与实现参考，可以随实现和真实样本调整。设计说明中的目录、字段和工具形态不自动升级为新的架构组件。

## 推荐阅读顺序

1. 只想理解产品：读 01。
2. 准备开发：读 01 → 06。
3. 实现第一条论文转换链路：读 04 → 05。
4. 建立质量闭环：再读 02 → 03。

## 五类资产的权威边界

| 资产 | 负责 | 不负责 |
|---|---|---|
| Skill | 领域目标、判断方法、工具使用、询问与停止条件 | 运行时调度、持久化状态机 |
| Knowledge | 学校要求、来源、模板、示例和已确认经验 | 执行流程、Agent 调度、运行日志 |
| Tools | DOCX 分析、修改、渲染、确定性检查 | 自主决定论文语义 |
| Eval | 离线样本、断言、回归与质量比较 | 在线运行编排、交付状态管理 |
| 薄应用壳 | 收集输入、配置 SDK、暴露领域资产、返回回复与产物 | 领域判断、工作流引擎 |

Claude Agent SDK 是运行时行为的权威来源。DocFit 文档不得复制一套 SDK 会话、事件、阶段、checkpoint 或恢复协议。

## 明确不建设

以下内容不属于当前 DocFit 架构：

- 自定义工作流引擎、阶段 DAG 或任务调度器；
- `StageExecution`、Run Evidence Module、事件 hash chain；
- 自定义 checkpoint、exact replay、comparative replay；
- Delivery Preflight 子系统和多层交付状态机；
- 独立 Runtime Verifier 或 Finalizer；
- 为未来平台预建的 Adapter、Port、发布事务与 schema 总线；
- 只有一处消费者的抽象层；
- 与 Claude Agent SDK 重叠的路由、会话和恢复实现。

如果未来真实需求证明必须增加其中某项，应以独立 ADR 说明：当前痛点、最小方案、为什么 SDK 或普通工具不能解决，以及删除成本。

## 变更原则

架构变更先回答四个问题：

1. 这项能力能否放进 Skill、Knowledge、Tool 或 Eval？
2. Claude Agent SDK 是否已经提供同类运行时能力？
3. 是否有当前真实样本证明需要新组件？
4. 新抽象是否至少有两个明确消费者？

任一问题没有清楚答案时，不新增架构组件。
