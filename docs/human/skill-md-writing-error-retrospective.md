# Skill MD 撰写错误复盘

> 文档性质：human-facing 复盘，不是新的 Skill 撰写规范。
> 记录日期：2026-08-23
> 范围：围绕 `.claude/skills/docfit-school-extract/SKILL.md` 近期改写中暴露的写作错误。

本文记录的是本项目写 Skill MD 过程中已经发生的错误。它不直接替代
`.claude/skills/**/SKILL.md`、`docs/modules/**`、Contract、Harness schema 或测试。若其中某条结论要
变成 Agent 默认规则，应再提升到对应位置并用测试或 Eval 锁住。

## 证据来源

这次复盘综合了三类证据：

- Git 版本：`07440a5`、`d56ef97`、`ab7ebf9`、`060a62e` 以及当前未提交修正。
- 已有文档：`AGENTS.md` 的 Skill 修改纪律、`docs/modules/template-extraction.md` 的分层职责、
  `docs/human/agent-skill与代码tool的职责边界经验.md`、`docs/human/post-unit-skill-writing-boundary.md`、
  `docs/human/agent-development-failure-attribution-and-boundary-governance.md`。
- 本轮用户反馈：五个入口概念缺关系树、whole-unit terminal 会结束当前 unit、Tool/Reference 应进入流程而非百科、
  新版本不是否定旧版、目录需要在下一层判断收录层级、目录专项不应占主流程步骤。

## 错误 1：把术语清单当成心智模型

早期版本已经把 `unit`、`reading_block/range_id`、`semantic_judgment`、Registry/style、`needs_input`
压成五个概念，但只是平铺解释，没有说清它们之间的父子和停止关系。

真实问题不是术语不够，而是 Agent 不知道先看哪个、什么时候停止、什么时候下钻。结果是：

- `unit` 被理解成边界容器，而不是学校功能区和下游默认语义上下文；
- `reading_block/range_id` 被理解成必须覆盖的列表，而不是只在 unit 不能闭合时使用的下一层判断范围；
- `needs_input` 和 Registry/style 只是附属说明，没有进入判断树。

正确的改法不是继续发明概念，而是写出关系树：`unit` 先判断，whole-unit terminal 可以停止；不能停止才进入
`reading_block/range_id`；Registry/style 只在局部判断触发时补证据。

## 错误 2：把“unit-boundary 只做边界”写得过窄

`07440a5` 附近的写法强调 `unit-boundary` 只回答开始和结束，把字段、样式、删除、清理都留到 post-unit。
这半句是对的，但它被写成了过窄的阶段理解。

用户指出后，问题变清楚了：unit 判断不仅是几何边界，也可以形成整个功能区的语义姿态。例如原创性声明、人工签署页、
学校审批表等，Agent 有能力直接判断“整体保留，不进入字段绑定”。如果 Skill 把 unit 阶段写成纯边界，
下游就会被迫重复拆这些内容。

这类错误的本质是把工程 checkpoint 写成了 Agent 的语义能力上限。

## 错误 3：修正过头，把 whole-unit terminal 泛化到目录

`ab7ebf9` 修正了 whole-unit terminal，可以让声明、人工表单等在 unit 层结束。但这次又把目录或图表清单放进
terminal 示例，写成“整体保留/刷新机制”。

这属于过度套用新模型。目录确实不是学生字段，也不应逐条绑定缓存；但它也不是普通 unit-level terminal。
它需要 Agent 在下一层判断：

- 是否存在真实 TOC、样式目录、题注目录或只是缓存文本；
- 应收录哪些标题族；
- 目录最深到几级；
- 摘要、ABSTRACT、参考文献、附录、致谢、图目录/表目录等前后置标题是否进入目录；
- 可见缓存里的“第一章”“参考文献”等不能当正文标题。

因此目录单元在 unit 层只应被识别为 generated area，闭合发生在 `reading_block/range_id` 的
`generated_mechanism` 判断。

## 错误 4：发现特殊案例后，把它塞进主流程表

`060a62e` 已经把目录从 unit-level terminal 里拿出来，但又在主流程表中新增了“目录/清单下钻”步骤。
用户指出这仍然不对。

主流程表应该承载所有 unit 共享的工作骨架：确认阶段、whole-unit 判断、选择下钻范围、局部判断、按需补证据、
大范围只读分析、反馈处理。目录是一个重要领域案例，但不是所有 unit 的主流程步骤。

这类错误说明：即使结论本身正确，也不能把每个新发现都提升成主流程节点。特殊案例应放在专项小节或 Reference；
主流程只放跨案例稳定结构。

## 错误 5：把 Tool 和 Reference 写成百科表

旧版 Skill 多次出现独立的 `Tool 使用`、`Reference 路由` 和“当前问题 -> 读取”大表。表面上它让内容更完整，
实际会让 Agent 把 Skill 当成工具手册或索引页。

用户反复指出：Tool 和 Reference 应该嵌入流程。也就是说，Agent 在某一步遇到某类判断时，才知道该取什么证据、
该读哪份 Reference。把所有 Tool/Reference 列到后面，会造成两个问题：

- Agent 先看工具，再倒推任务；
- Skill 主体变成百科，真正的工作路径反而不清楚。

这和 `skill-creator` 的原则一致：主 `SKILL.md` 保留入口、核心约束和路由；复杂案例放 Reference，但 Reference
不能变成未分流的总目录。

## 错误 6：把 Harness/Tool 内部概念泄漏给 Agent

已有文档已经反复说明：hash、candidate、locator、object_ref、coverage、publish、cursor、reviewed_pages、
trace path 等属于 Harness/Tool/App，不属于 Agent 主判断面。

但早期 Skill 仍倾向于通过文字约束 Agent：

- 不要用旧 hash；
- 不要复用 stale ref；
- 每个对象后手动检查；
- 进入 publish 前证明页面覆盖；
- 按 Tool schema 拼 payload。

这些内容越写越多，Skill 就越像第二套 runtime。真实责任应该是：

- Skill 说明 Agent 如何判断学校语义；
- Tool 提供有边界证据和受控执行；
- Harness 检查 shape、coverage、Registry、冲突、可执行性和阶段出口；
- App 负责路径、权限、发布和 fail-closed。

如果 Tool/Harness feedback 不可行动，应修 feedback；不应把内部账本字段写进 Skill 让 Agent 手动维护。

## 错误 7：把一次调试补丁写成长期规则

这几轮修改里，我多次根据一个具体反馈直接改 Skill 主体。例如：

- 因为原创性声明误判，就加强 whole-unit terminal；
- 因为目录需要判断层级，就加主流程步骤；
- 因为工具反馈出现缺口，就试图在 Skill 中增加检查义务。

这些都是没有先做足“责任层归因”的表现。`AGENTS.md` 和 `docs/modules/template-extraction.md` 都要求先判断问题属于
Agent、Skill、Harness、Tool、Schema、App、Test、Eval 还是 Docs，再决定修改位置。

稳定的学校语义规则可以进入 Skill；一次运行的失败码、工具参数、状态字段、临时 workaround 不应该进入 Skill。

## 错误 8：误解“新版本用于 AB 测试”

用户要求“重新出一个版本”，目的是保留旧 Skill 作为一个可比较版本，而不是宣称旧内容全部无价值。

我一开始的倾向是把旧内容整体替换掉，导致两个问题：

- 丢掉旧版里已经正确的经验，例如“目录缓存不是正文”“Registry/style 按需取证”“Tool 不替你判断学校语义”；
- 新版虽然更短，但没有解释为什么某些旧内容被保留、降级到 Reference，或从主流程移除。

正确处理是：重构心智模型，但保留已验证的语义经验；把旧内容按职责重新安放，而不是机械删除。

## 错误 9：Runtime prompt 和 Skill 没同步校准

Skill 改了以后，`src/docfit/app/prepare_template.py` 的启动提示也会影响 Agent。之前出现过 Skill 说 whole-unit
可以 terminal，但 runtime 仍强制每个 accepted unit 先拿 `unit_evidence_packet` 并覆盖 reading blocks；后来又出现
runtime 把 generated TOC/list 写进 terminal 示例。

这说明 Skill 不是唯一入口。只改 `SKILL.md` 但不检查 runtime prompt，会让实际 Agent 收到互相冲突的指令。

每次 Skill 改动都应检查：

- runtime prompt 有没有同一口径；
- contract test 有没有锁住关键边界；
- Reference 是否和主 Skill 分工一致；
- 测试是否只锁住行为边界，而不是把坏措辞固定下来。

## 错误 10：测试容易锁住措辞，而不是锁住行为

当前 Skill contract tests 使用大量字符串断言。这能防止重要边界丢失，但也有风险：它可能鼓励为了通过测试保留某个
具体句子，而不是验证 Agent 是否真的按正确关系工作。

更合理的测试重点应该是：

- 主流程有没有关系树和停止条件；
- 是否禁止泄漏 Harness/Tool 内部术语；
- Tool/Reference 是否嵌入流程而非百科清单；
- whole-unit terminal 是否只覆盖固定/人工类单元；
- 目录/清单是否被排除在 unit-level terminal 外；
- generated judgment 是否要求下一层范围和来源层级。

字符串断言可以保留，但应尽量锁边界和反例，而不是锁整段文案。

## 这份复盘本身的边界

这不是新的 Skill 撰写手册，也不是要求之后每次改 Skill 都照本文逐条检查。它只记录本项目中已经暴露的错误模式。

如果要把这些经验变成稳定规则，应分别提升到：

- `.claude/skills/docfit-school-extract/SKILL.md`：Agent 每次必须遵守的领域判断入口；
- `.claude/skills/docfit-school-extract/references/**`：复杂领域案例和反例；
- `docs/modules/template-extraction.md`：模板提取模块长期流程与分层边界；
- `AGENTS.md`：所有 Agent 进仓都必须遵守的操作纪律；
- `tests/**` / `evals/**`：可机器验证的边界。

当前最重要的教训是：Skill MD 的质量不取决于写得多完整，而取决于它是否把 Agent 的主工作面压到正确层级。
在 DocFit 模板提取里，这个主工作面是学校语义判断；流程、证据、工具、Reference 都应该服务这个判断，而不是把
Harness 或 Tool 的运行时概念搬给 Agent。
