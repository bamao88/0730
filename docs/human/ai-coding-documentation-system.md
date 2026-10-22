# AI Coding 文档体系构建调研

状态: human-facing 调研与建议
更新日期: 2026-08-24

本文记录一次关于 AI coding 文档体系的调研和 DocFit 适配建议。它属于
`docs/human/**` 背景材料，不是默认 Agent 启动上下文，也不是当前运行规则。

如果本文中的结论被采纳，应按性质提升到 `AGENTS.md`、`CLAUDE.md`、`docs/agents/**`、
`docs/contracts/**`、测试、Hook、CI 或 ADR。不要让本文直接变成 runtime Agent prompt、
Skill 或 Tool feedback。

## 调研问题

DocFit 当前的问题不是缺少一句原则，而是缺少一个能持续约束后续 AI 开发方向的体系：

- coding agent 需要知道项目边界、文档入口、应该改哪一层；
- runtime Agent 不能看到 Harness/Tool/App 内部账本概念；
- prompt、Skill、schema、Tool feedback 和 checkpoint 的边界要能被测试保护；
- 临时失败不能继续被写成新的 Agent 任务或 Skill 规则。

因此需要调研的问题是：AI coding 文档体系应该如何组织，才能既减少后续 AI 进场成本，
又避免把内部实现概念泄漏回 runtime Agent 面。

## 核心结论

AI Coding 文档体系不应该追求“文档多”，而应该追求“权威面分清楚”：

- 根部 Agent 文件负责启动，不承载长手册；
- agent-only runbook 负责指导 coding agent 如何开发、调试、归因；
- Contract 负责稳定边界和可依赖字段；
- 模块文档负责产品流程；
- ADR 负责长期决策原因；
- 状态、计划、bug 文档负责时间性证据；
- 测试、Hook 和 CI 负责把文档边界变成可失败的工程护栏。

最重要的分界是：

```text
coding agent 可以理解内部机制；
runtime Agent 不应该被内部机制引导。
```

例如 `hash`、`object_ref`、`render_ref`、`locator`、`coverage`、`publish` 这些词可以出现在
coding-agent runbook、Contract 说明和测试说明里，但不应该进入 runtime Agent 默认 prompt、
Agent-facing schema 或面向 Agent 的 Tool feedback。

这里的两个 Agent 是两个语境，不一定是两个不同模型：

| 角色 | 类比 | 该知道什么 |
| --- | --- | --- |
| coding agent | 开发 DocFit 系统的工程师 | 系统内部机制、代码结构、测试、错误归因 |
| runtime Agent | DocFit 产品运行时的受限语义判断组件 | 学校模板语义、可见文本、reading packet、证据不足时提问 |

coding agent 的任务是改 DocFit 仓库，所以它可以理解 `hash`、`render_ref`、`object_ref`、
`locator`、`coverage`、`publish`、Tool schema 和 Harness ledger。runtime Agent 的任务是
在 `prepare-template` 过程中判断学校模板语义，所以它应该处理“这个 block 是填写槽、说明文字、
固定学校内容还是正文样例”“证据够不够”“应该保留、删除、转成 slot 还是返回 open question”，
而不是维护候选 hash、render ref、coverage 或发布账本。

例如：

```text
错误反馈：
render_ref_missing，请重新生成 render_ref 并修复 coverage。
```

这会把 runtime Agent 拉进 Harness/Tool 内部账本。正确做法是让 Harness/Tool 在内部记录
`render_ref_missing`，但面向 runtime Agent 改写为：

```text
当前页面视觉证据不可用，请基于 text reading packet 判断；
如果文本证据不足，返回 needs_input。
```

也就是说：

```text
coding agent 可以修 render_ref_missing；
runtime Agent 只应该判断“证据够不够做学校语义判断”。
```

## 调研依据摘要

OpenAI Codex 官方文档把 `AGENTS.md` 定义为会自动进入上下文的项目指导。它适合记录仓库布局、
运行命令、测试命令、工程约定、限制规则和 Done 定义；当文件变大时，应引用任务专用 Markdown
文件，而不是继续扩写根文件。

Claude Code 官方文档也强调 `CLAUDE.md` 应保持短、具体、可验证；多步骤流程或只在局部相关的知识，
应放入 Skill、path-scoped rules 或其他按需加载机制。Claude 文档还明确指出这类记忆文件是
context，不是强制安全边界；若要阻止动作，需要 Hook 等确定性机制。

OpenAI Codex Code Review 规则经验表明，repository rules 应该小、具体、可归属，并说明安全路径。
能用测试、linter 或 CI 表达的机械检查，不应该只靠文档提醒。

近期研究对 AGENTS/CLAUDE 类上下文文件的结论并不完全一致，但共同指向几个风险：

- 上下文文件会膨胀；
- lint/format 细节容易泄漏到文档里，替代了本该由工具执行的检查；
- task-specific skill 或长流程容易泄漏进每次启动上下文；
- 冲突规则和陈旧状态会降低指令有效性；
- 有效的 repo guidance 主要帮助 agent 找到正确文件和工作面，不替代实现能力或测试。

## 推荐文档体系

### 1. `AGENTS.md`: 启动入口

职责：

- 项目心智模型；
- 必读入口；
- 关键命令；
- 最高优先级边界；
- 文档分层规则；
- 何时读取更深层文档。

不放：

- 长调试流程；
- 详细 Tool schema 字段清单；
- 临时 failure code；
- 当前任务计划；
- 已完成状态流水账；
- 可由代码、测试或配置推断的常识。

DocFit 建议：`AGENTS.md` 只增加一条指针即可：

```text
改 prompt、Skill、schema、Tool feedback 或 Harness checkpoint 前，先读
docs/agents/ai-coding-boundary-guardrails.md。
```

### 2. `CLAUDE.md`: Claude 适配层

职责：

- 引入 `AGENTS.md`；
- 只补 Claude Code 特有差异。

推荐形态：

```text
# Claude Code 项目指引

@AGENTS.md
```

如果确实需要 Claude-specific 规则，应短且明确，不复制 `AGENTS.md` 内容，避免双份漂移。

### 3. `docs/agents/README.md`: Coding-agent Runbook 索引

职责：

- 说明 `docs/agents/**` 是给 coding agent 的操作手册；
- 列出每份 runbook 的用途；
- 标明这些文档不是产品真相，也不是 runtime Agent prompt。

适合收录：

- AI coding boundary guardrails；
- CI failure triage；
- release/publish procedure；
- repo-specific tool quirks；
- PR review/fix workflow；
- 长环境准备说明。

### 4. `docs/agents/ai-coding-boundary-guardrails.md`: AI Coding 护栏手册

这是 DocFit 当前最需要补的 agent-only 文档。

建议结构：

```text
# AI Coding Boundary Guardrails

## 适用场景
改 prompt / Skill / schema / Tool feedback / Harness checkpoint / runtime Agent output
前必须阅读。

## 关键分界
coding agent 可见内部机制；runtime Agent 不可见内部账本。

## Agent-facing Contract
允许字段、禁止字段、拥有者、对应测试。

## Forbidden Concept Lint
扫描哪些文件，排除哪些开发文档，命中后怎么修。

## Tool Feedback Sanitizer
内部错误码如何翻译成 Agent 可行动语言。

## Checkpoint Failure Ownership
Agent / Skill / Harness / Tool / Schema / App / Test / Eval 的归因规则。

## 不允许的修法
不能把临时失败码、Tool schema 字段清单、timeout 策略写回 Skill。
不能让 Agent 手动维护 hash、coverage、publish 或 stale ref。
```

这份文档可以讨论 `hash/object_ref/render_ref/locator/coverage/publish`，因为读者是 coding agent。
但它必须反复强调：这些概念不能进入 runtime Agent 默认工作面。

### 5. `docs/contracts/**`: 稳定合同

职责：

- 黑盒输入输出；
- 可依赖字段；
- 版本化 schema；
- failure status / origin；
- 发布产物；
- 下游可以依赖什么，不能依赖什么。

DocFit 建议：

- `docs/contracts/template-extraction.md` 继续承载模块黑盒合同；
- 如 runtime Agent-facing 字段边界变复杂，可新增
  `docs/contracts/template-extraction-agent-facing.md`；
- Contract 中明确 runtime Agent 允许字段和禁止字段。

示例：

```text
runtime Agent 可输出：
- unit_id
- reading_block_id / range_id
- semantic_judgment
- needs_input
- open_questions

runtime Agent 不输出：
- hash / candidate_hash
- render_ref
- object_ref
- locator
- coverage
- publish
- checkpoint backend
```

### 6. `docs/modules/**`: 模块流程边界

职责：

- 模块输入输出；
- 阶段顺序；
- checkpoint；
- 上下游交接；
- Skill / Agent / Harness / Tool / App / Test 的职责表。

不负责：

- 长 coding-agent 操作手册；
- 一次性 bug 复盘；
- 当前任务计划；
- PR 级执行步骤。

### 7. `docs/adr/**`: 长期设计原因

职责：

- 已经沉淀的设计决策；
- 备选方案；
- 取舍原因；
- 后续违反该决策时应重新评审的条件。

不负责：

- 临时状态；
- 运行日志；
- “今天为什么失败”的调试记录。

### 8. `docs/status/**`、`docs/plans/**`、`docs/bugs/**`: 时间性证据

职责：

- 当前状态；
- 执行计划；
- bug 归因；
- proof、trace、Eval 和复盘链接。

这些文件默认不进入 Agent 启动上下文。只有处理相关任务时才读取。

### 9. `tests/**`、Hook、CI: 可执行护栏

文档只能说明边界，不能保证边界。DocFit 的关键边界应由测试或 Hook 兜住：

- Agent-facing schema allowlist；
- forbidden concept lint；
- Tool feedback sanitizer 测试；
- failure origin / ownership 测试；
- 最小真实流程 replay；
- prompt / Skill / Tool feedback 的快照或文本扫描。

注意：forbidden concept lint 不能无差别扫描全部文档。它应该扫描 runtime Agent 会看到的文本面，
并显式排除 coding-agent runbook、human 调研、Contract 解释和测试说明，否则会误伤开发资料。

## DocFit 最小落地路径

建议按小步落地，不一次性重构全部文档。

### 第一步：补 human 调研材料

本文就是这一步。它用于让人确认方向，不直接改变 runtime。

### 第二步：新增 agent-only 护栏文档

新增：

```text
docs/agents/README.md
docs/agents/ai-coding-boundary-guardrails.md
```

然后在 `AGENTS.md` 增加一条短指针。

### 第三步：固化 Agent-facing Contract

在 `docs/contracts/template-extraction.md` 或独立 Agent-facing Contract 中写清：

- runtime Agent 允许字段；
- runtime Agent 禁止字段；
- 哪些内部字段只属于 Harness/Tool/App ledger；
- failure origin 的归属规则。

### 第四步：加测试护栏

最小测试集：

- schema allowlist 测试；
- forbidden concept lint；
- feedback sanitizer 测试；
- renderer unavailable / stale ref / unresolved object 等 failure ownership 测试。

### 第五步：收紧 runtime 面

逐步把 runtime Agent-facing prompt、Skill、Tool schema 和 feedback 中的内部账本概念迁移到
Harness/Tool/App 层。不要一次性大改，优先从 post-unit Agent output schema 和 Tool feedback
开始。

## 文档晋升规则

human 文档里的结论被确认后，按性质晋升：

| 结论类型 | 晋升位置 |
| --- | --- |
| 每次 coding agent 进场都必须知道 | `AGENTS.md` |
| Claude Code 特有启动规则 | `CLAUDE.md` |
| coding agent 长流程 / 调试手册 | `docs/agents/**` |
| runtime Agent 可见字段和黑盒边界 | `docs/contracts/**` |
| 模块阶段和职责 | `docs/modules/**` |
| 长期设计原因 | `docs/adr/**` |
| 机械可检查规则 | `tests/**`、Hook、CI |
| 当前任务证据或临时复盘 | `docs/status/**`、`docs/plans/**`、`docs/bugs/**` |

## 反模式

以下做法会让 AI coding 文档体系失效：

- 把所有规则都塞进 `AGENTS.md` 或 `CLAUDE.md`；
- 把当前任务状态复制进根 Agent 文件；
- 把 Tool schema 字段清单写进 Skill；
- 用文档提醒替代可写测试的边界；
- forbidden concept lint 扫描 human/runbook 文档，导致开发文档不能解释内部机制；
- Contract、模块文档、Skill、测试各写一套不同字段；
- 每次失败都追加一条新规则，但不删除旧规则；
- 让 runtime Agent 看到 `hash/render_ref/object_ref/locator/coverage/publish` 后再要求它“不要使用”。

## 参考文献

- OpenAI Codex: Best practices  
  <https://developers.openai.com/codex/learn/best-practices>

- OpenAI Codex: Custom instructions with AGENTS.md  
  <https://developers.openai.com/codex/agent-configuration/agents-md>

- OpenAI Developers Blog: Custom Code Review rules for Codex  
  <https://developers.openai.com/blog/custom-code-review-rules-for-codex>

- Open AGENTS.md format  
  <https://agents.md/>

- Claude Code Docs: How Claude remembers your project  
  <https://code.claude.com/docs/en/memory>

- Claude Code Docs: Best practices for Claude Code  
  <https://code.claude.com/docs/en/best-practices>

- Shepard, Asa; Albrecht, Jeannie. "Probe-and-Refine Tuning of Repository Guidance
  for Coding Agents." arXiv:2606.20512, 2026.  
  <https://arxiv.org/abs/2606.20512>

- Khatri, Prakhar. "Do Context Files Help Coding Agents? A Two-Agent Ablation Study
  on Real Repositories." arXiv:2607.27250, 2026.  
  <https://arxiv.org/abs/2607.27250>

- dos Santos, Helio Victor F.; Costa, Vitor; Montandon, Joao Eduardo; Silva,
  Luciana Lourdes; Valente, Marco Tulio. "Configuration Smells in AGENTS.md Files:
  Common Mistakes in Configuring Coding Agents." arXiv:2606.15828, 2026.  
  <https://arxiv.org/abs/2606.15828>

- Chakrabarti, Kushal. "Why Does CLAUDE.md Keep Growing? Catastrophic Remembering
  in Agentic Coding." arXiv:2608.11095, 2026.  
  <https://arxiv.org/abs/2608.11095>
