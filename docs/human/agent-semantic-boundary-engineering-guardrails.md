# Agent 语义边界与工程护栏讨论记录

> 文档性质：human-facing 讨论记录，不是当前 Agent 默认规则。
> 记录日期：2026-08-24
> 背景：记录一次模板提取真实流程后，对“Agent 只输出语义判断”为什么仍会失守，以及后续如何用工程护栏避免边界漂移的讨论。

本文记录的是一次人工讨论中形成的判断。它不能直接替代 `AGENTS.md`、模块文档、Skill、Contract、
Harness schema 或测试。若其中某条结论要变成稳定规则，应提升到对应层，并用测试或 Eval 锁住。

## 1. 触发背景

一次新的 HUNAU 模板提取真实流程没有生成最终产物。流程停在 `unit-boundary`，没有进入 post-unit，也没有
生成 `final-template.docx` 和 `fill-contract.yaml`。

从 checkpoint 看，Agent 已经基于 `document_map` 切出了 14 个单元：

- 封面
- 诚信声明
- 目录
- 摘要前置
- 正文
- 参考文献
- 致谢
- 附录
- 毕业设计任务书
- 开题报告
- 开题论证记录表
- 答辩记录表
- 题目变更审批表
- 成绩评定表

但 runtime 仍然没有接受这个结果。原因是 `docfit_evidence(render_snapshot)` 返回
`visual_renderer_unavailable`，后续 `visual_page` 因缺少 `render_ref` 返回 `render_ref_missing`。
最终主流程包装成 `template_agent_backends_exhausted / unit_boundary_checkpoint_failed`。

这个结果暴露出一个边界问题：

> Agent 已经完成了可见的语义判断，但 Harness/runtime 因视觉渲染链路不可用拒收结果，最后表现成
> Agent 没完成 unit-boundary。

## 2. 这里的视觉证据是什么

“视觉证据”不是 `document_map` 里的纯文本，而是 Word 模板真实渲染成页面后，Agent 或 Harness 可使用的页面级证据。

它通常包括：

- 页面截图或页面渲染快照；
- 标题位置、字号感、居中、缩进；
- 表格外壳、签名栏、填写横线；
- 页眉页脚、分页、跨页延续；
- 章节之间的视觉分隔；
- 目录缩进、点线、页码对齐和层级关系。

视觉证据可以帮助判断“这段文字是不是正文标题”“这是目录缓存还是正文内容”“这是签署页还是普通段落”。
但 `render_ref` 本身不是 Agent 的业务概念。它只是 Harness/Tool 内部用来引用渲染结果的执行句柄。

因此正确边界应该是：

```text
Harness/Tool 负责获取视觉证据和管理 render_ref。
Agent 可以阅读被整理后的视觉描述。
Agent 不管理 render_ref，也不因 render_ref 缺失承担语义失败。
```

## 3. 用户指出的真正问题

需求本来很简单：

> Agent 只需要输出学校模板语义判断。

这个边界在文档和聊天中已经被反复说清楚。但系统仍然做不好，原因不是这句话本身不清楚，而是它没有被工程结构强制执行。

只要 prompt、schema、tool feedback、checkpoint 或测试里仍然把 Harness/Tool 内部概念暴露给 Agent，Agent 的工作面就会被污染。
于是表面上 Agent 在做语义判断，实际上被迫承担：

- hash 生命周期；
- candidate/source 映射；
- locator/object_ref 解析；
- render_ref 调度；
- coverage 计算；
- checkpoint backend 失败恢复；
- publish 或物化前检查。

这些都不是学校模板语义判断。

## 4. 为什么“写清楚”仍然不够

自然语言文档只能告诉人边界在哪里，但不能阻止代码、schema 或 runtime feedback 把边界打破。

只要存在下面任一情况，边界就会继续漂移：

- Agent-facing schema 允许或暗示内部字段；
- runtime prompt 让 Agent 补 `render_ref`、`candidate_hash` 或对象引用；
- Tool feedback 把底层失败码原样返回给 Agent；
- checkpoint 把环境问题包装成 Agent 阶段失败；
- 测试只验证“流程失败了”，没有验证失败归因属于哪一层；
- Skill 为了补一次 runtime 缺陷，不断增加工具字段、失败码和操作步骤。

所以后续不能只继续补充说明，而要做工程护栏。

## 5. 什么是工程护栏

工程护栏是：

> 不只在文档里说某件事不该发生，而是在 schema、prompt、feedback、checkpoint、测试和真实流程里让它很难发生，
> 一旦发生就立即暴露。

面向模板提取，最小护栏包括以下几类。

### 5.1 冻结 Agent-facing contract

Agent 默认只允许接触这些工作概念：

- `unit`
- `reading_block_id` / `range_id`
- 可读文本和必要版面描述
- `semantic_judgment`
- 按需补充的 Registry/style 上下文
- `needs_input`

Agent-facing 输出可以引用 `unit_id`、`reading_block_id` 或 `range_id`，但不应该引用 Harness 内部对象。

默认禁止暴露给 Agent 的概念包括：

- `hash`
- `candidate_hash`
- `source_hash`
- `render_ref`
- `object_ref`
- `locator`
- `coverage`
- `publish`
- `checkpoint_backend`
- stale ref
- trace path

这些概念可以存在于 Harness、Tool、App、日志和内部账本里，但不能成为 Agent 主工作说明的一部分。

### 5.2 Agent-facing schema 不给内部字段入口

如果 Agent 输出 schema 里允许 `render_ref`、`object_ref`、`coverage` 等字段，Agent 就会被引导去维护它们。

更合理的输出结构应该围绕语义判断：

```yaml
unit_id: cover
reading_block_ids:
  - block-001
semantic_judgment:
  kind: school_fixed
  action: preserve
needs_input: false
open_questions: []
```

Harness 再负责把这些语义判断投影到底层 Word 对象、覆盖集合和物化计划。

### 5.3 Prompt、Skill 和 Tool feedback 做 forbidden concept lint

需要有测试扫描所有 Agent 会看到的文本，包括：

- Skill 主文档；
- runtime prompt；
- Tool feedback；
- checkpoint repair message；
- Agent-facing schema description。

只要这些文本中出现未豁免的内部词，例如 `render_ref`、`candidate_hash`、`object_ref`、`locator`、`coverage`、`publish`，
测试就应该失败。

豁免只应出现在明确的反面说明或内部测试里，不能成为 Agent 实际工作项。

### 5.4 Tool feedback 必须分层改写

底层 Tool 可以返回内部失败：

```text
visual_renderer_unavailable
render_ref_missing
candidate_hash_mismatch
object_ref_unresolved
```

但返回给 Agent 的修复信息必须翻译成语义工作面语言。

例如 renderer 不可用时，Agent-facing feedback 不应是：

```text
render_ref missing, please call render_snapshot again.
```

而应是：

```text
当前页面视觉证据不可用。请基于当前 text reading packet 判断；如果文本证据不足，返回 needs_input 并说明缺少哪类可读证据。
```

这样 Agent 仍然只做语义判断，证据获取和句柄管理留在 Harness/Tool。

### 5.5 checkpoint 失败归因不能混层

renderer 不可用是 environment/Harness 问题，不应最后表现成 Agent 没完成单元边界。

正确的失败归因应该区分：

```text
Agent semantic status:
- complete
- needs_input
- invalid_output

Harness/runtime status:
- evidence_unavailable
- object_mapping_failed
- coverage_failed
- materialization_failed
- publish_failed
```

如果 Agent 已经输出可解释的语义判断，但 Harness 因视觉渲染不可用无法验收，应明确报环境或证据链路失败。
不应让用户或后续 Agent 误以为应该继续改 Skill。

### 5.6 checkpoint 接收条件按职责拆开

Agent 阶段完成条件应该问：

- 是否给出了可解释的 `semantic_judgment`；
- 是否引用了有效的 `unit_id`、`reading_block_id` 或 `range_id`；
- 证据不足时是否明确返回 `needs_input`；
- 是否把不能判断的问题留在 `open_questions`，而不是编造结论。

Harness 阶段完成条件才应该问：

- reading block 是否能投影到 Word 对象；
- 对象引用是否仍然可解析；
- coverage 是否闭合；
- Registry field 是否存在；
- DOCX 是否能物化；
- publish 是否能原子完成。

这两类条件混在一个“Agent 必须完成”的门禁里，就会继续让 Agent 背 runtime 的锅。

### 5.7 加真实流程边界测试

需要一条最小真实流程测试，不只证明函数能跑，而是证明边界不漂移：

```text
输入 reading packet
Agent 输出 semantic_judgment
Harness 接收并投影到对象
renderer 不可用时，流程明确停在 environment/evidence unavailable
Agent-facing feedback 不出现 render_ref/hash/object_ref/coverage/publish
```

这个测试的价值不是追求一次完整产物，而是防止重构后内部概念再次漏到 Agent 工作面。

## 6. 对 Skill MD 的影响

这次讨论也解释了为什么 Skill MD 不能继续写成工具百科。

Skill 应该描述：

- 当前阶段的语义任务；
- Agent 读什么；
- Agent 判断什么；
- 什么时候可以停止；
- 什么时候进入下一层范围；
- 证据不足时怎么 `needs_input`；
- 哪些复杂案例读 Reference。

Skill 不应该描述：

- Tool schema 字段清单；
- hash/candidate 生命周期；
- object_ref/locator 解析策略；
- render_ref 调用细节；
- coverage 计算；
- publish 前置账本；
- 单次调试失败码和 workaround。

如果 Skill 为了让流程跑通而开始要求 Agent 管这些内容，说明真正需要修的是 Harness、Tool、Schema、App 或测试。

## 7. 后续可提升为稳定规则的内容

如果要把本文结论变成长期规则，建议分别提升到以下位置：

- `AGENTS.md`：Agent 每次进仓都必须遵守的职责边界；
- `docs/modules/template-extraction.md`：模板提取各 checkpoint 的 Agent/Harness/Tool/App 责任；
- `.claude/skills/docfit-school-extract/SKILL.md`：Agent 语义判断入口和阶段流程；
- `.claude/skills/docfit-school-extract/references/**`：目录、声明、签署表、审批表等复杂领域案例；
- `tests/contract/**`：Agent-facing prompt/schema/feedback forbidden concept lint；
- `tests/agent/**`：真实流程中失败归因和 feedback 是否维持语义边界；
- `evals/**`：真实学校样本的最终模板质量。

## 8. 一段可直接复制给 Agent 的要求

```text
先不要把 runtime、Tool 或 Harness 内部概念补进 Skill。

当前边界是：Agent 只输出学校模板语义判断；Agent 可以引用 unit_id、reading_block_id 或 range_id；
Agent 可以在证据不足时返回 needs_input。Agent 不管理 hash、candidate、render_ref、object_ref、locator、
coverage、publish 或 checkpoint backend。

请先判断当前失败属于 Agent 语义、Skill 指引、Harness 验收、Tool 证据、Schema、App、Test 还是 Eval。
如果失败来自 renderer、object mapping、coverage 或 publish，不要用 Skill/prompt 让 Agent 承担这些内部工作。
```

## 9. 本文边界

本文是讨论记录，不是可执行合同。它的价值是说明“为什么一个看似简单的 Agent 语义需求会反复失败”，以及后续应该用
哪些工程护栏防止边界再次漂移。

当前最重要的结论是：

> “Agent 只输出语义判断”不能只靠文档声明。它必须被 Agent-facing contract、schema、prompt、Tool feedback、
> checkpoint 归因和真实流程测试共同保护。
