# Agent 修复走偏、层级边界漂移与目录治理分析

> 文档性质：human discussion / 架构分析草稿，非当前操作规则
> 日期：2026-08-18
> 背景：记录一次对 Template Extraction 调试走偏现象的人工观察，并分析如何用目录结构、文档层级和测试放置减少同类问题。

## 1. 这类问题可以怎么命名

用户直觉上感受到的问题不是“某个函数写错了”，而是 Agent 在解决问题时没有先分清问题属于哪一层。
比较准确的说法可以是：

- **层级责任混淆**：Agent、Skill、Harness、Tool、Schema、App 各自负责什么没有先划清。
- **主路径未证明就扩散修复**：单元拆分主路径还没跑通，就去修 Tool、Schema、发布或其他下游问题。
- **checkpoint 范围膨胀**：当前阶段只应该检查结构边界闭合，却把视觉、Registry、字段绑定等后续缺口提升成当前失败。
- **语义判断和机械校验混在一起**：Agent 应判断学校模板语义；Harness 应验证结构声明是否闭合、可消费、无遗漏或重叠。
- **修复边界不清**：一个现象可能有多种修法，但每种修法属于哪一层、会改变什么合同、如何验收没有先说明。
- **上下文污染**：历史计划、讨论稿、失败日志或过期状态被当成当前真相，导致 Agent 继承了错误路线。

一句话概括：

> Agent 看到了症状，但没有先做层级归因和 checkpoint 收口，于是用局部代码修改代替了架构边界判断。

## 2. 用普通话解释这个问题

可以把 DocFit 的模板提取流程看成几个人协作：

- Agent 像一个懂论文模板的人，负责判断“这一块在学校模板里是什么意思”。
- Skill 像工作手册，提醒 Agent 应该怎么观察、什么时候补证据、遇到失败怎么回退。
- Harness 像验收员，检查 Agent 交上来的结构化判断是否完整、是否覆盖全部对象、是否能进入下一阶段。
- Tool 像受控机器，只做确定性读写；做不了时必须说清为什么做不了，以及下一步该换什么证据或目标。
- Schema 像表格格式，规定 Agent 交来的内容长什么样。
- App 像门禁，管路径、权限、hash、发布和不可逆动作。

因此，“结构边界闭合”需要拆成两句话：

1. Agent 决定它认为的结构边界是什么，因为这依赖学校语义判断。
2. Harness 检查这个结构边界声明是否闭合、完整、可消费、无遗漏和无重叠。

如果 Harness 发现视觉证据不足或 Registry 字段还没绑定，它不应直接让“单元拆分”失败。更合理的处理是把这些记录到
`open_questions`，交给后续阶段处理。除非这些缺口会让结构边界本身无法判断。

## 3. Template Extraction 的责任边界

| 层 | 应该负责 | 不应该负责 | 典型文件位置 |
| --- | --- | --- | --- |
| Agent | 学校语义判断、结构边界选择、字段语义选择、是否需要继续取证 | 路径权限、hash 生命周期、发布原子性、机械覆盖计算 | Claude Agent SDK runtime |
| Skill | 告诉 Agent 观察顺序、Reference 路由、失败后如何回到判断问题 | 复述完整 Tool schema、写成应用状态机、替代 Harness 验收 | `.claude/skills/docfit-school-extract/SKILL.md` |
| Skill Reference | 展开复杂领域例子和边界案例 | 承担主流程规则、定义当前产品合同 | `.claude/skills/docfit-school-extract/references/*.md` |
| Harness | 检查 Agent 产物的形状、覆盖、闭包、可消费性、阶段出口 | 替 Agent 判断学校语义；把后续阶段缺口提升成当前阶段失败 | `src/docfit/template/harness.py`、`src/docfit/app/prepare_template.py` |
| Tool | 读取证据、执行确定性 DOCX 修改、返回可行动失败 | 决定哪个学校字段语义正确、决定单元边界 | `src/docfit/tools/**`、`src/docfit/template/object_mutation.py` |
| Schema | 约束输入输出字段、类型、版本 | 表达学校语义规则或运行时策略 | `src/docfit/tools/schemas.py`、合同测试 |
| App | 权限、路径、hash、任务边界、发布、不可逆动作 | 给 Agent 分配语义 work item、隐藏地决定学校模板含义 | `src/docfit/app/**` |
| Tests / Eval | 机器化证明合同和行为 | 作为长期产品说明书 | `tests/contract/**`、`tests/agent/**`、`evals/**` |
| Human docs | 讨论、学习、复盘、人工解释 | 直接成为 Agent 默认启动规则 | `docs/human/**` |

## 4. 当前例子的正确收口方式

### 4.1 单元拆分主路径

当前最小目标应该先收敛为：

```text
给定 startup context + docfit-school-extract Skill
Agent 能产出结构边界声明
Harness 只按结构闭包检查这个声明
视觉、Registry、字段绑定缺口进入 open_questions
units 阶段不因为后续缺口失败
```

这时不应该先修：

- `docfit_apply` 的写入能力；
- 发布阶段 Fill Contract；
- 字段绑定 Schema；
- 视觉渲染覆盖门；
- 完整 Agent E2E 准确率。

这些可能都重要，但它们不是“单元拆分 checkpoint”的第一验收条件。

### 4.2 Harness 应该检查什么

单元拆分 checkpoint 里，Harness 可以机械检查：

- 是否覆盖了源模板中需要覆盖的对象范围；
- 是否存在遗漏或重叠；
- 每个 unit 是否有稳定 id、边界引用、责任类型和证据引用；
- 边界引用是否绑定当前 source hash；
- `open_questions` 是否结构化记录了未闭合项。

Harness 不应该在这个阶段要求：

- 每个填写位置已经绑定 Registry；
- 所有页面已经视觉复核；
- 每个 slot 都已经物化到 DOCX；
- 最终发布合同已经生成。

## 5. 从目录结构上怎么避免走偏

### 5.1 让每个目录只承载一种真相

| 目录 / 文件 | 建议承载 | 防偏作用 |
| --- | --- | --- |
| `docs/contracts/**` | 黑盒输入输出、状态语义、下游可依赖内容 | 防止把实现细节当产品合同 |
| `docs/modules/**` | 模块内 Agent、Skill、Harness、Tool、Eval 的责任边界 | 防止修 bug 时跨层乱改 |
| `.claude/skills/**/SKILL.md` | Agent 主流程、Reference 路由、失败恢复节奏 | 防止 Tool schema 和 app 状态机塞进 Skill |
| `.claude/skills/**/references/**` | 领域案例、判断边界、反例 | 防止主 Skill 过长或遗漏复杂例子 |
| `src/docfit/template/harness.py` | 结构化产物闭包与可消费性检查 | 防止 Agent 自己计算机械闭包 |
| `src/docfit/tools/**` | 确定性证据和写入能力 | 防止 Tool 替 Agent 做学校语义判断 |
| `tests/contract/**` | 跨层合同是否稳定 | 防止口头规则没有机器证明 |
| `tests/agent/**` | Agent runtime / Skill / feedback loop 是否接通 | 防止只测 Tool 而主路径不通 |
| `docs/human/**` | 分析、学习、讨论、复盘 | 防止讨论稿污染启动上下文 |

### 5.2 每个 bug 文档先写“层级归因”

建议任何架构相关 bug 文档开头都先填一个小表：

```text
Observed symptom:
Current checkpoint:
Layer suspected:
Layer explicitly not changing:
Semantic decision owner:
Mechanical validation owner:
Minimum passing path:
Verification command:
```

如果这个表填不出来，就先不要改代码。否则 Agent 很容易看到一个失败现象，就同时改 Skill、Harness、Tool、
Schema 和测试。

### 5.3 每次跨层修改必须声明“为什么非跨层不可”

如果一次修改同时碰到 Skill、Harness、Tool、Schema、App，应要求 Agent 先说明：

- 每一层的具体失败是什么；
- 每一层的修改是否可以独立验收；
- 哪些修改只是测试暴露，不改变产品语义；
- 如果只修其中一层，主路径会不会仍然失败；
- 有没有把下游缺口误提升为上游门禁。

这不是为了禁止跨层修改，而是防止“看起来相关”的扩散。

### 5.4 Human 文档不能自动变成当前规则

本文件这类 `docs/human/**` 文档应该只作为分析草稿。若其中某条规则被确认，应按性质提升到对应位置：

- 产品模块边界 -> `docs/modules/template-extraction.md`
- 黑盒输入输出或状态语义 -> `docs/contracts/template-extraction.md`
- Agent 主流程规则 -> `.claude/skills/docfit-school-extract/SKILL.md`
- 复杂领域例子 -> `.claude/skills/docfit-school-extract/references/*.md`
- 长期架构决定 -> `docs/adr/**`
- 可执行验收 -> `tests/contract/**` 或 `tests/agent/**`
- AI 操作入口规则 -> `AGENTS.md`

不应直接从 `AGENTS.md` 链接一篇长 human 讨论稿。否则下一轮 Agent 会把讨论过程当成启动真相。

## 6. 可以要求 Agent 使用的修复前检查

之后遇到类似问题，可以直接要求 Agent 在动手前回答：

```text
1. 这个失败属于哪个 checkpoint？
2. 当前 checkpoint 的完成条件是什么？
3. 哪些缺口只应进入 open_questions，而不应导致当前 checkpoint 失败？
4. Agent、Skill、Harness、Tool、Schema、App 各自是否需要修改？
5. 如果需要跨层修改，每一层的最小修改和独立测试是什么？
6. 哪个测试证明主路径跑通，而不是只证明某个工具能工作？
7. 哪些历史计划、状态或 human 文档只是证据，不能作为当前真相？
```

如果 Agent 不能回答第 1 到第 3 点，说明它还没有完成层级归因，不应直接进入代码修复。

## 7. 面向当前项目的建议动作

短期可以先做三件事：

1. 在 Template Extraction 的 bug/plan 模板里增加“checkpoint + layer ownership”小节。
2. 为单元拆分新增一个独立 agent/harness 测试，只验证结构边界闭合和 `open_questions` 分流。
3. 在 `docs/modules/template-extraction.md` 中用一张表明确 Agent、Skill、Harness、Tool、App 在每个 checkpoint 的责任。

中期再考虑：

- 把已确认的规则提升到 Contract 或模块文档；
- 给 `docs/human/README.md` 增加“讨论稿如何提升为规则”的指针；
- 在 PR review checklist 中要求跨层修改必须附带层级归因。

## 8. 一段可直接复制给 Agent 的话

```text
先不要继续修 Tool、Schema 或发布逻辑。当前问题先收敛到 Template Extraction 的单元拆分主路径：
Agent 在给定 startup context 和 Skill 的情况下，是否能产出结构边界声明；Harness 是否能只按结构闭包检查它，
而不是把视觉、Registry、字段绑定等后续缺口提升为 units 阶段失败。

请先画清 Agent、Skill、Harness、Tool、Schema、App 的责任边界，再做最小改动。每次改动必须说明它属于哪一层、
解决哪个 checkpoint、不会改变哪些边界。若某个缺口属于后续阶段，应进入 open_questions，不要让当前 checkpoint 失败。
```

