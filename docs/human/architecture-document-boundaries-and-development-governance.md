# 架构文档边界与开发治理说明

> 文档性质：human discussion / 写作边界说明，非当前操作规则
> 日期：2026-08-18
> 背景：整理关于“架构设计、模块文档、阶段门禁、故障归因和文档膨胀”的讨论，帮助后续和 Agent 协作时控制文档边界。

## 1. 架构设计和开发治理有什么不同

架构设计和开发治理有区别，但它们是上下级关系。

**架构设计**回答的是：

> 系统应该由哪些部分组成？这些部分怎么协作？长期边界是什么？

比如 DocFit 的架构设计会说：

```text
Template Extraction -> 产出 final-template.docx + fill-contract.yaml
Student Content Extraction -> 产出 Student Content Model
Final Content Fill -> 合成最终 Word

Agent 负责语义判断
Harness 负责闭包检查
Tool 负责确定性读写
App 负责权限、hash、发布
```

这是系统的“结构设计”。

而 `unit_split`、checkpoint、失败归因这类内容，属于：

**架构设计之下的开发治理 / 运行边界设计 / 阶段门禁设计。**

它回答的是：

> 当系统开发或运行失败时，我们怎么判断是哪一层的问题？每个阶段到底验收什么？Agent 不能乱改什么？

比如：

```text
unit_split 阶段只输出顶层逻辑单元边界
不输出 field_id、slot、cleanup action
Harness 只检查结构覆盖和重叠
Registry/视觉缺口进入 open_questions
```

这不是整个系统架构，而是把架构落实到某个阶段的**边界规则**。

## 2. 几类文档/治理内容的区别

| 类型 | 关注点 | 例子 |
| --- | --- | --- |
| 架构设计 | 系统由哪些模块组成，各模块长期职责 | 三大模块；Agent/Skill/Harness/Tool 分层 |
| 模块设计 | 某个模块内部有哪些阶段和产物 | Template Extraction 里有单元拆分、字段绑定、候选生成、最终复核 |
| 阶段门禁设计 | 每个阶段什么叫完成，什么只能进入 open_questions | `unit_split` 只验收逻辑边界闭合 |
| 故障归因逻辑 | 失败时先判断是哪个模块/阶段/层的问题 | Final Fill 失败先分模板预处理、学生预处理、组合、写入、验证 |
| 开发治理 | Agent 修复前必须说明改哪里、不改哪里、怎么验证 | Attribution Brief、跨层修改说明、动态内容提升规则 |

所以：

> 架构设计是“系统应该长什么样”。
> 开发治理 / 阶段门禁 / 故障归因是“开发和修复时怎样不破坏这个架构”。

更准确地说，开发治理是架构设计的操作化版本。

也就是把抽象架构变成 Agent 每次开发时必须遵守的具体规则：

- 这个阶段只输出什么；
- 不应该输出什么；
- 谁判断语义；
- 谁做机械校验；
- 哪些失败可以继续；
- 哪些失败必须停止；
- 哪个测试证明边界没被破坏。

可以把它理解成：

```text
架构设计：画地图
开发治理 / 阶段门禁 / 故障归因：规定怎么按地图走，走错了怎么定位
```

如果这套东西稳定下来，最终应该有一部分被提升进架构文档或模块文档里；但在还没验证之前，先放在
`docs/human/**` 是合适的。

## 3. 为什么 Agent 容易把架构文档写长

常见问题可以叫：

**架构文档膨胀**，或者更准确一点：

**把架构文档写成了“全部背景 + 当前计划 + 调试记录 + 实现说明 + 操作手册”的混合体。**

这会导致两个坏结果：

1. 人读不动。
2. Agent 下次读的时候，会把历史讨论、临时方案、实现细节都当成当前规则。

所以架构文档必须有清晰边界。

## 4. 架构文档应该写什么

架构文档只回答这几个问题：

```text
系统由哪些模块组成？
每个模块负责什么？
每个模块不负责什么？
模块之间通过什么产物交接？
哪些边界不能被破坏？
哪些设计决定是长期有效的？
```

也就是说，架构文档写的是 **稳定结构和长期边界**。

它不应该写：

```text
某次 bug 怎么调的
某个测试为什么失败
当前正在尝试哪个方案
某个函数怎么实现
某个字段暂时叫什么
某次 smoke 的输出
Agent 这次应该先跑哪个命令
完整历史讨论
```

这些应该放到别处。

## 5. 推荐长度

建议：

- 根 `ARCHITECTURE.md`：最好 3-6 页以内。
- 单个模块文档：最好 2-5 页以内。
- 超过这个长度，就要拆出去。

判断标准：

> 如果这段内容在三个月后还应该被遵守，它可以进架构文档。
> 如果它只是解释当前怎么修、怎么调、怎么跑，它不该进架构文档。

## 6. 根架构文档建议结构

```markdown
# Architecture

## System Goal
一句话说明系统目标。

## Modules
三大模块表格：
- Template Extraction
- Student Content Extraction
- Final Content Fill

每个模块只写：
- 输入
- 输出
- 负责
- 不负责

## Data Flow
用一张图说明数据怎么流动。

## Trust Boundaries
哪些输入是不可信的，哪些目录不能互读。

## Stable Contracts
模块之间靠哪些稳定产物交接。

## Non-Negotiable Boundaries
绝不能破坏的规则。

## Extension Points
未来可以扩展哪里，但不现在展开。

## References
只链接当前合同和模块文档，不链接历史计划。
```

## 7. 模块文档应该写什么

模块文档比根架构细一点，但仍然不能变成实现日志。

一个模块文档可以这样写：

```markdown
# Template Extraction Module

## Purpose
这个模块解决什么问题。

## Inputs
允许输入什么。

## Forbidden Inputs
不能读取什么。

## Outputs
必须输出什么。

## Internal Responsibilities
Agent / Skill / Harness / Tool / App 各自负责什么。

## Pipeline Checkpoints
只列阶段名和完成条件：
- Unit Split
- Responsibility Judgment
- Binding
- Candidate Generation
- Final Review
- Publication

## Failure Attribution
失败时先归因到哪个 checkpoint。

## Verification
哪些测试或 Eval 证明模块边界。
```

注意：模块文档可以写 checkpoint，但不要写完整调试过程。

## 8. 内容应该拆到哪里

| 内容 | 放哪里 |
| --- | --- |
| 系统模块和长期边界 | `ARCHITECTURE.md` |
| 某模块的职责和阶段 | `docs/modules/*.md` |
| 输入输出合同 | `docs/contracts/*.md` |
| 当前状态/下一步 | `STATUS.md` 或 `docs/status/active/*.md` |
| 调试复盘/人类解释 | `docs/human/*.md` |
| 实施计划 | `docs/plans/*.md` |
| 可执行验收 | `tests/**`、`evals/**` |
| Agent 操作规则 | `AGENTS.md` 或 Skill |
| 领域判断案例 | Skill references |

## 9. 可以直接要求 Agent 这样写

```text
请把架构文档控制成稳定边界文档，不要写成长计划、调试记录、实现细节或操作日志。

每一段都必须通过这个判断：
如果三个月后实现重构但产品边界不变，这段话是否仍然成立？
如果不是，把它移到 docs/human、docs/plans、docs/status 或测试里。

根 ARCHITECTURE.md 只写：
1. 系统目标
2. 三个模块
3. 数据流
4. 信任边界
5. 模块交接合同
6. 不可破坏的长期边界
7. 当前真相入口

单个模块文档只写：
1. 模块目的
2. 输入/禁止输入
3. 输出
4. Agent / Skill / Harness / Tool / App 职责
5. pipeline checkpoints
6. failure attribution
7. verification references

不要超过 5 页。超出的内容必须拆出去。
```

核心就是一句话：

> 架构文档不是“我知道的一切”，而是“未来必须遵守的稳定边界”。
