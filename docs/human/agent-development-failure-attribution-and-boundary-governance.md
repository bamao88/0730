# AI Agent 开发故障归因与模块边界治理通用框架

> 文档性质：human framework / 通用开发治理草案，非当前操作规则
> 日期：2026-08-18
> 适用范围：DocFit 各模块在 AI Agent 参与开发、调试、修复、评审和文档更新时的分层诊断

## 1. 目标

这套框架解决一个反复出现的问题：

> Agent 看到失败现象后，直接跳到代码修改；但它没有先判断失败属于哪个模块、哪个阶段、哪一层责任。

目标不是限制 Agent 做事，而是让它每次修改前先完成故障归因，再做最小、可验证、可回退的改动。

## 2. 三个定位坐标

任何问题先用三个坐标定位：

| 坐标 | 要回答的问题 | 示例 |
| --- | --- | --- |
| 模块 | 问题属于哪个产品模块？ | Template Extraction、Student Content Extraction、Final Content Fill |
| 阶段 | 问题发生在流水线哪个 checkpoint？ | 输入合同、预处理、组合、物化、验证、发布 |
| 层级 | 应由哪一层负责修复或验证？ | Agent、Skill、Harness、Tool、Schema、App、Test、Eval、Docs |

只有这三个坐标清楚后，才允许进入代码修改。

## 3. 标准阶段词表

不同模块可以有自己的业务阶段，但推荐统一映射到下面的通用阶段词表。

| 阶段 | 负责什么 | 失败归因关键词 |
| --- | --- | --- |
| Input Contract | 外部输入是否存在、版本/hash/schema 是否匹配 | 输入合同失败、缺文件、hash mismatch |
| Precondition | 当前任务能否安全开始 | 权限、路径、只读边界、依赖缺失 |
| Preprocessing | 把输入整理成内部可消费结构 | 解析错误、inventory 错、归一化错 |
| Semantic Judgment | Agent 基于证据做领域判断 | 字段语义、学校要求、学生内容语义 |
| Mapping / Composition | 多个输入之间如何显式连接 | slot/content mapping、placement plan |
| Materialization | 把计划写入具体产物 | DOCX 写入、图片/表格/公式插入、样式应用 |
| Postcondition Validation | 输出是否满足客观条件 | 可打开、内容完整、视觉覆盖、非目标内容未变 |
| Publication | 是否可以作为正式交付物发布 | 原子输出、最终 hash、Fill Contract、禁止覆盖 |

每个模块的文档可以使用自己的名称，但必须能映射回这个词表。

## 4. 层级责任矩阵

| 层级 | 应该负责 | 不应该负责 |
| --- | --- | --- |
| Agent | 领域语义判断、证据取舍、冲突解释、是否需要继续探索 | 路径权限、hash 生命周期、机械覆盖计算、发布事务 |
| Skill | 指导 Agent 如何观察、何时读 Reference、失败后如何回到判断问题 | 充当应用状态机、复述完整 schema、替代测试 |
| Skill Reference | 展开领域案例、反例、边界样本 | 承担主流程入口规则、定义稳定产品合同 |
| Harness | 检查结构化产物是否闭合、可消费、覆盖完整、阶段出口有效 | 替 Agent 判断业务语义 |
| Tool | 提供确定性证据、执行确定性操作、返回可行动失败 | 决定语义正确性或跨阶段推进策略 |
| Schema | 约束字段、类型、版本和结构形状 | 表达业务判断或动态运行策略 |
| App | 权限、路径、任务边界、持久化、发布和不可逆动作 | 给 Agent 分配隐藏语义 work item |
| Test | 固定机器可验证的行为 | 保存临时讨论和产品解释 |
| Eval | 证明用户级质量和真实样本趋势 | 替代局部 contract test |
| Docs | 说明边界、状态、讨论和决策 | 替代代码、测试或 Eval |

## 5. 修复前必须产出的 Attribution Brief

在复杂 bug、跨层修改、Agent 行为失败或 E2E 失败时，Agent 动手前应先写：

```text
Observed symptom:
用户或测试看到了什么坏结果？

User impact:
如果不修，用户最终会遇到什么问题？

Module:
属于哪个产品模块？

Checkpoint:
属于哪个阶段？Input Contract / Preprocessing / Mapping / Materialization / Validation / Publication？

Suspected layer:
Agent / Skill / Harness / Tool / Schema / App / Test / Eval / Docs？

Why this layer:
为什么判断是这一层的问题？

Why not other layers:
为什么不是相邻层的问题？至少说明两个容易混淆的层。

Current checkpoint done means:
当前阶段完成条件是什么？

Allowed open_questions:
哪些缺口只能记录为 open_questions，不应让当前阶段失败？

Layers explicitly not changing:
本次明确不改哪些层？

Minimum change:
最小改动是什么？

Verification:
哪个测试或 Eval 证明这次修复正好覆盖该层？

Rollback:
如果判断错了，如何撤回或降级这次改动？
```

如果无法回答 `Checkpoint`、`Current checkpoint done means`、`Allowed open_questions`，就不应直接修改代码。

## 6. 每个阶段的完成条件与 open questions

每个 checkpoint 都应写清两类内容：

```text
Done:
- 当前阶段必须闭合的事实。

Open questions:
- 后续阶段需要解决，但不阻止当前阶段通过的问题。

Hard blockers:
- 会让当前阶段不能继续的问题。
```

例子：Template Extraction 的单元拆分阶段。

```text
Done:
- 单元边界非空。
- 单元覆盖当前 source 中需要覆盖的对象。
- 单元之间没有无法解释的重叠。
- 每个 unit 有稳定 id、边界引用、责任类型和证据引用。

Open questions:
- Registry 字段候选还没最终选择。
- 某个填写位置需要视觉证据确认。
- 某个样式代表对象需要后续比较。

Hard blockers:
- 结构边界无法从当前输入中声明。
- 对象引用不属于当前 source hash。
- Harness 无法判断覆盖是否闭合。
```

例子：Final Content Fill 的模板预处理阶段。

```text
Done:
- final-template.docx 存在且能打开。
- fill-contract.yaml 存在且 schema 有效。
- Fill Contract 绑定的 template hash 匹配 Word 文件。
- required slot locator 在 Word 中唯一可解析。

Open questions:
- 某个学生内容应放入哪个 slot。
- 最终视觉分页是否完美。
- 某个样式应用后是否需要微调。

Hard blockers:
- Fill Contract 与模板 hash 不匹配。
- required slot 找不到或重复。
- 模板侧输入不是本模块可消费的产物。
```

## 7. 动态内容的生命周期

产品开发中有些事实是动态的，不应马上写进稳定规则。

| 生命周期 | 放哪里 | 进入条件 | 退出条件 |
| --- | --- | --- | --- |
| Observation | `docs/bugs/**`、trace、test failure | 看到失败或异常现象 | 被归因为 hypothesis |
| Hypothesis | `docs/human/**`、bug analysis | 有合理解释但未验证 | 被测试证明或推翻 |
| Active Status | `STATUS.md`、`docs/status/active/**` | 当前团队需要按它推进 | 被完成、阻塞、取代或过期 |
| Contract | `docs/contracts/**` | 外部调用方或下游必须依赖 | 通过版本化变更更新 |
| Module Boundary | `docs/modules/**` | 模块内责任长期稳定 | 模块架构变更时更新 |
| Agent Rule | `AGENTS.md`、Skill | Agent 每次执行都必须遵守 | 规则不再适用或被更具体规则取代 |
| Executable Truth | `tests/**`、`evals/**` | 可机器验证 | 测试被替换或合同变更 |
| Retired Evidence | 历史计划、旧状态、归档 bug | 只保留追溯价值 | 不作为启动上下文 |

动态内容的治理原则：

> 动态判断先作为证据保存；只有经过验证、稳定且需要反复约束行为时，才提升为 Contract、Module doc、Skill、AGENTS 或测试。

## 8. 目录放置规则

| 内容 | 首选位置 | 不应放到 |
| --- | --- | --- |
| 用户能依赖的输入输出规则 | `docs/contracts/**` | `docs/human/**`、代码注释 |
| 模块内部责任分工 | `docs/modules/**` | 单个 bug 文档 |
| Agent 工作方法 | `.claude/skills/**/SKILL.md` | Tool 实现 |
| 复杂领域案例 | `.claude/skills/**/references/**` | 主 Skill 长文 |
| 失败复盘和思考 | `docs/human/**`、`docs/bugs/**` | `AGENTS.md` |
| 当前短状态 | `STATUS.md`、`docs/status/active/**` | 长计划文档 |
| 长期不可随便推翻的决定 | `docs/adr/**` | 临时状态文档 |
| 可执行行为证明 | `tests/**`、`evals/**` | 只写自然语言文档 |

`docs/human/**` 是分析和学习层，不是默认 Agent 启动真相。若其中内容被确认，必须按性质提升到正确目录。

## 9. 测试如何证明“修的是对的层”

| 层级 | 推荐测试 | 证明内容 |
| --- | --- | --- |
| Schema | contract test | 输入输出形状稳定 |
| Tool | unit / contract test | 确定性能力和失败语义正确 |
| Harness | contract test | 结构化闭包、覆盖和阶段出口正确 |
| Skill | skill contract test / scripted agent test | 主流程、Reference 路由、失败恢复存在 |
| App | integration test | 权限、hash、路径、发布和 SDK session 行为正确 |
| Module | module integration / Eval | 模块黑盒行为正确 |
| Product | E2E / visual Eval | 用户最终结果正确 |

大 E2E 失败不能直接说明应该改哪一层。正确流程是：

```text
E2E 失败
  -> Attribution Brief
  -> 最小分层复现测试
  -> 修对应层
  -> 跑对应层测试
  -> 再跑 E2E
```

## 10. Final Content Fill 的示例分层

| 阶段 | 输入 | 输出 | 失败归因 |
| --- | --- | --- | --- |
| Template Preprocessing | `final-template.docx`、Fill Contract | slot inventory、style/region inventory | 模板侧输入合同或模板预处理问题 |
| Student Preprocessing | Student Content Model | content inventory、field/content index | 学生内容输入合同或学生预处理问题 |
| Placement Planning | 两侧 inventory | explicit placement plan | 映射/组合逻辑问题 |
| DOCX Materialization | placement plan + template | candidate final Word | 写入物化或样式应用问题 |
| Final Validation | candidate final Word | validation report | 后置验证或真实输出质量问题 |
| Publication | validated final Word | single deliverable | 发布原子性或输出边界问题 |

遇到最终 Word 失败时，不应直接假设“填充代码错了”。应先回答：

```text
模板侧输入是否满足合同？
学生侧输入是否满足合同？
预处理是否把输入解释错了？
placement plan 是否错误？
DOCX 写入是否执行错了？
validation 是否误报或漏报？
```

## 11. Review Checklist

评审跨层修复时，可以逐项检查：

- [ ] 是否先写了 Attribution Brief？
- [ ] 是否明确当前模块、checkpoint 和层级？
- [ ] 是否列出本次不改的层？
- [ ] 是否区分 Done、Open questions、Hard blockers？
- [ ] 是否避免把后续阶段缺口提升为当前阶段失败？
- [ ] 是否有对应层级的最小测试？
- [ ] 是否没有用 E2E 失败直接倒推实现层修改？
- [ ] 是否说明动态发现是否需要提升为稳定规则？
- [ ] 是否避免把 `docs/human/**` 讨论稿接入默认启动上下文？

## 12. 可直接给 Agent 的指令

```text
先不要修代码。先做故障归因。

请说明：
1. 这个失败属于哪个产品模块？
2. 属于哪个 checkpoint？
3. 当前 checkpoint 的完成条件是什么？
4. 哪些缺口应该进入 open_questions，而不是让当前 checkpoint 失败？
5. 责任层是 Agent、Skill、Harness、Tool、Schema、App、Test、Eval 还是 Docs？
6. 为什么不是相邻层的问题？
7. 本次明确不改哪些层？
8. 最小改动是什么？
9. 哪个测试证明这次改动修的是正确层？
10. 这条发现是否只是动态证据，还是需要提升为 Contract、Module doc、Skill、AGENTS 或测试？

在回答清楚之前，不要进入代码修改。
```

