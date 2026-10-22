# AI Coding Boundary Guardrails

状态: 模板提取 Agent-facing 边界开发护栏
适用模块: 模板提取 / `docfit prepare-template`

本文给 coding agent 使用。它不是产品 Agent 的 runtime prompt，也不是学校模板语义规则。
它的目的只有一个：后续任何 AI 开发者修改 prompt、Skill、schema、Tool feedback、Harness
checkpoint 或测试时，都要把“Agent 只做学校语义判断，Harness/Tool/App 管内部不变量”落实成代码、
接口、测试和运行流程的护栏。

## 两个读者

必须先区分两个读者：

| 读者 | 可以看到 | 不应承担 |
| --- | --- | --- |
| Coding agent | 本文、源码、测试、内部账本概念、failure origin、contract 演进计划 | 把内部概念直接复制进 runtime Agent prompt 或 Skill |
| Runtime 产品 Agent | unit reading packet、canonical `source_entry_id` / text、reading view、相邻语义块、布局线索、pre-input vocabulary、语义判断反馈 | hash、render ref、object ref、locator、coverage、publish、checkpoint backend、task root、stale ref 账本 |

禁词测试只针对 runtime Agent 会看到的文本和 schema 描述。不要扫描 `AGENTS.md`、`docs/agents/**`
或开发者测试说明；这些文档必须能讨论内部概念，才能指导 coding agent 修正确层。

## 受保护开发面

改下面任一文件面时，先读本文并在 PR 里说明 guardrail 影响：

- `.claude/skills/docfit-school-extract/**`
- `src/docfit/app/prepare_template.py`
- `src/docfit/app/agent.py`
- `src/docfit/tools/surface.py`
- `src/docfit/tools/service.py`
- `src/docfit/template/harness.py`
- `src/docfit/template/judgment_shape.py`
- `src/docfit/template/reading_packet.py`
- `tests/contract/**` 中与 Agent schema、Tool contract、Harness feedback、runtime checkpoint 有关的测试

如果一次修改同时碰 Skill、Harness、Tool、Schema 和 App，先把它当作跨层合同变更；不要把它描述成
“补 prompt”或“调 Skill”。

## 护栏 1: Agent-facing Contract

runtime Agent 的 post-unit 判断合同必须从 reading packet 出发。默认允许字段是：

```text
source_entry_id
parts[].text
parts[].role
parts[].field_id  # only from the pre-input vocabulary, when the role requires it
needs_input
open_questions
reason
```

精确原文传输允许 `parts[].whitespace` 以及同一片段的 `leading_whitespace` /
`trailing_whitespace`，用于显式表达空白字符及数量。它们是文字表达，不是对象定位或版本账本；
Harness 解码不得改变片段数量、用途或字段，也不得从源文自动补足未提交字符。

整条原文确为单一用途时允许 Agent 显式提交唯一 part 的 `whole_entry: true`，不携带 text 或
空白编码。它声明语义责任的完整范围，不是内部对象引用；Harness 只按显式范围取原文并重跑原有
检查。缺少该声明、仅一个 role 或部分 text 均不能推断为整条用途。

只有当合同明确需要时，才增加面向学校语义的 schema enum，例如：

```text
responsibility
output_effect
style_obligation
visible_evidence_summary
```

默认禁止把以下内部账本字段放进 Agent 输出结构、prompt 指令、Skill 操作步骤或 Tool feedback 正文：

```text
hash
candidate_hash
render_ref
object_ref
target_ref
locator
coverage
publish
checkpoint_backend
task_root
stale_ref
fingerprint
```

允许这些概念存在的位置：

- Harness、Tool、App 内部账本；
- 落盘 proof、trace、publication receipt 和 deterministic validation；
- coding-agent 文档和测试实现；
- Contract 中面向下游机器消费者的黑盒产物字段，例如 Fill Contract 的最终 template hash 和 locator。

不允许的位置：

- runtime Agent prompt；
- runtime Agent structured output schema；
- `.claude/skills/docfit-school-extract/SKILL.md` 中给产品 Agent 的阶段步骤；
- Tool feedback 返回给产品 Agent 的可见正文；
- Harness revision packet 给产品 Agent 的修复指令。

迁移判断标准：如果字段的正确性只能由代码解析、hash 绑定或快照账本证明，它不该由产品 Agent 填写。
产品 Agent 应该引用 canonical source entry 并给出 ordered parts；Harness 再解析 span 并映射到底层对象。

## 护栏 2: Forbidden Concept Lint

新增或修改 Agent-facing 文本时，必须能回答“这个文本会不会被产品 Agent 看到”。如果会看到，就需要
forbidden concept lint。

建议测试范围：

```text
.claude/skills/docfit-school-extract/**/*.md
runtime prompt builder 输出
Agent structured output schema description / property names
Tool schema description 中暴露给 MCP Agent 的 name / enum / description
Tool feedback 和 Harness revision packet 的 Agent-visible message / suggested_actions
```

建议排除范围：

```text
AGENTS.md
CLAUDE.md
docs/agents/**
docs/human/**
docs/contracts/** 中面向下游机器产物的合同字段
src/** 内部实现注释和测试代码
trace / proof / receipt fixture
```

禁词 lint 不是为了隐藏系统实现，而是防止产品 Agent 被引导去修内部账本。测试失败时优先做三件事：

1. 如果这是产品 Agent 需要做的语义判断，把词改成 reading packet 语言。
2. 如果这是 Harness/Tool 必须知道的内部状态，把字段移到内部账本或 feedback sanitizer 之前。
3. 如果这是下游机器合同字段，确认它不进入 runtime Agent prompt，并在测试排除清单中写明原因。

## 护栏 3: Tool Feedback Sanitizer

Tool 和 Harness 可以产生内部错误码，但返回给产品 Agent 前必须转换成语义工作面语言。

内部错误示例：

```text
render_ref_missing
visual_renderer_unavailable
candidate_hash_mismatch
object_ref_unresolved
locator_span_ambiguous
coverage_closure_incomplete
publish_output_dirty
```

产品 Agent 可见反馈应表达为：

```text
当前页面视觉证据不可用；请基于 unit reading packet 的可见文本判断。
如果文本证据不足，返回 needs_input 并说明缺少哪类学校语义证据。
```

```text
这些 reading block 尚未被语义判断覆盖；请为列出的 block 补充责任判断，或把它们合并进已有语义 range。
```

```text
这个字段选择尚未闭合；请基于可见标签、邻近说明和当前输入的 field_id_vocabulary 选择 parts[].field_id，词表中没有安全字段时返回 needs_input。
```

sanitizer 的输出要求：

- 说明 affected unit、reading block、range 或可见文本；
- 说明产品 Agent 下一次应补什么语义判断；
- 保留 `origin`、`code`、`retryable` 给 Harness/App/trace，但不把内部 code 当作 Agent 要修的对象；
- 不给产品 Agent 下一步 Tool 调用脚本；
- 不要求产品 Agent 重填 hash、render ref、object ref、locator 或 publish 参数。

## 护栏 4: Failure Ownership

失败必须按责任层归因，不能把 Harness 或环境问题包装成 Agent 语义失败。

推荐 `origin`：

| origin | 示例 | 下一步 |
| --- | --- | --- |
| `agent` | 语义判断缺失、互斥判断、证据不足但未返回 `needs_input` | 修 prompt、Skill、Reference 或 Agent-facing contract |
| `skill` | Agent 重复走错阶段、把 post-unit 当 unit-boundary | 修 Skill 阶段路由或 Reference |
| `schema` | Agent 输出 shape 不满足当前合同 | 修 schema 或 revision packet；不要放宽内部字段 |
| `harness` | phase review、mapping、coverage、conflict、executable closure 判断错误 | 修 Harness gate 或 reading packet mapping |
| `tool` | evidence、render、inspect、DOCX mutation、validation 实现错误 | 修 Tool service 或 adapter |
| `environment` | renderer 不可用、OfficeCLI 缺失、Docker 不可用、凭据缺失 | 修环境或 doctor，不改 Skill |
| `application` | 输入隔离、resume proof、task root、发布目录、postcondition | 修 App/CLI |
| `eval` | Actual-vs-Gold 评分、Gold fixture、离线 review oracle | 修 Eval/Gold，不注入 runtime |

判断原则：

- renderer 不可用是 `environment`，不是 Agent 没有修 `render_ref`。
- 旧 snapshot 解析失败是 Harness/session ledger 或 Tool resolvability，不是 Agent 要学习 stale ref。
- publication 失败是 App postcondition，不是 Agent 输出不够努力。
- 语义判断错才优先修 Skill/Reference；机械账本失败优先修代码和反馈。

## 护栏 5: Checkpoint 接收条件拆分

Agent 完成条件只检查语义工作面：

```text
是否给出可解释的 semantic_judgment
是否引用当前 unit packet 的有效 source_entry_id
是否用 ordered parts 按可见文本顺序表达局部语义
可执行 part 的 field_id 是否来自当前输入词表
字段与 part role 的组合是否符合词表声明的 allowed_part_roles
证据不足时是否明确 needs_input
是否留下只属于后续阶段的 open_questions
```

Harness / Tool / App 完成条件检查机械不变量：

```text
底层对象是否仍可解析
reading packet mapping 是否闭合
Registry field 是否来自当前输入词表和 Registry snapshot
coverage / overlap / conflict 是否闭合
DOCX 是否能物化
最终产物是否能发布
```

字段用途检查复用输入词表的 `usage_affordance.allowed_part_roles`，不依赖字段命名。
不兼容提交可返回语义修订；词表角色元数据本身缺失或损坏归 Harness，不能让 Agent 猜测修复。
局部检查、全局检查与已保存 review 的复用不得采用不同兼容性规则。

不要把两类条件合并成“Agent 必须完成”。Agent 可以完成语义判断，同时 Harness 因环境或账本问题失败。
这种失败应回到对应责任层，而不是继续扩大 prompt。

## 护栏 6: 禁止代码替 Agent / Schema 补语义

模板提取里最危险的短期捷径，是在 Harness、Tool、App 或 materializer 中写窄规则来补 Agent 或 schema
没有表达清楚的语义判断。这类规则通常能跑通当前 fixture，但跨学校、跨模板或跨模型输出 wording 后会变脆。

以下形态必须先停下来归因，不能直接继续加 `if text contains ...`：

- 根据学校模板里的固定中文片段决定字段绑定，例如用 `学生姓名`、`指导老师`、`学院` 推 Registry field；
- 根据某个学校的说明词决定正文结构分支，例如用 `农理工`、`文法`、`经管` 选择 body track；
- 根据 Agent 输出 role / treatment / judgment 的自由文本片段决定执行路径，而不是 schema enum 或显式字段；
- 根据单个 fixture 的可见文本清理或保留内容，例如只匹配 `附录(小三号黑体)`；
- 把 `□`、`××`、括号内容、空段、样例值一概当成删除对象，而不先判断它们是视觉空格、填写占位、
  格式说明、样例值、布局载体还是固定内容。

正确处理顺序：

1. 如果判断依赖学校语义，先让产品 Agent 在 reading packet 工作面输出明确语义，或补 Skill/Reference。
2. 如果判断依赖可枚举阶段意图，先改 Agent-facing schema 或 Harness contract，使用显式 enum / typed field。
3. 如果判断依赖 Registry 候选，先补 Registry 字段元数据、field affordance 或 evidence packet，而不是在代码里猜字段。
4. 如果判断确实是确定性 DOCX 物化，规则必须消费 accepted semantic judgment，并按类别解释可见文本。
   例如括号清理应识别“括号内是格式说明”，而不是列出几个学校样例字符串。
5. 每个物化规则至少配一条反向测试：证明普通正文、真实括号、视觉空格或填写占位不会被误删。

可接受的确定性规则必须满足：

- 输入来自已接受的 `semantic_judgments`、Registry snapshot 或 Word 结构事实；
- 规则描述的是类别，不是某个 fixture 的完整字符串；
- 失败时能回到 Agent/schema/Registry/Harness 的明确责任层；
- 验证看最终 DOCX / Fill Contract / replay 结果，不只看中间语义 JSON。

## 必补测试

涉及边界的改动至少选择对应测试：

| 改动 | 最小测试 |
| --- | --- |
| Agent output schema | allowlist 测试：post-unit schema 不接受内部账本字段 |
| Skill / prompt | forbidden concept lint：产品 Agent 可见文本不能出现内部账本词 |
| Tool feedback | sanitizer 测试：内部错误码不会直接出现在 Agent-visible message / suggested_actions |
| Harness phase review | ownership 测试：failure origin 正确，revision packet 用 reading block/range 语言 |
| renderer / OfficeCLI / Docker 失败处理 | 流程测试：停在 `environment` 或 `needs_input`，不要求 Agent 修内部引用 |
| resume / checkpoint | replay 测试：proof 校验失败回到对应 checkpoint，不静默进入下一阶段 |

一个最小真实流程测试应覆盖：

```text
输入 unit reading packet
Agent 返回 semantic_judgment
Harness 映射到底层对象并 review
当视觉 renderer 不可用时，流程归因为 environment 或 evidence unavailable
产品 Agent 只看到 reading packet 语言，不看到内部 render 或 object 账本
```

## PR 检查清单

改模板提取 Agent-facing 边界时，PR 描述必须回答：

```text
当前改动属于哪个 checkpoint
runtime 产品 Agent 新看到或少看到什么
是否新增或移除了 Agent-facing schema 字段
是否引入了 forbidden concept lint 或更新排除理由
Tool/Harness 内部错误如何 sanitizer
failure origin 如何归因
最小 deterministic proof 是哪个测试或 replay
有没有把临时失败码、Tool schema 字段清单或 workaround 写进 Skill
```

不能用的 shortcut：

- 为了让 Agent “更懂工具”，把内部字段清单写进 Skill；
- 为了快速过关，让 Agent 手动调用机械检查 Tool；
- 为了解释一次失败，把一次性错误码写进 prompt；
- 为了避免 sanitizer，直接把 Tool 原始错误回传给 Agent；
- 为了让 Eval 分数变好，把 Gold 或 accepted answer 注入 runtime。

## 当前仓库的优先迁移点

以下是后续代码 PR 的优先级；第一项已经冻结为当前合同，其余按实际改动持续执行：

1. 保持 post-unit `SemanticJudgmentSet`：以 canonical `source_entry_id`、ordered `parts` 和
   pre-input `field_id_vocabulary` 为唯一合同；reading block/range 只作为输入 view；
   Harness 负责把 parts 映射成 `span_ref` / `slot_ref`，不接受 Agent-authored coverage、
   object locator 或 object ref 路径。
2. 拆分 MCP Tool surface：产品 Agent 的 evidence/check/apply schema 不应要求填写 candidate hash、render ref
   或 object ref；这些由 session ledger 注入或由 Harness 内部调用。
3. 给 Tool/Harness feedback 加 sanitizer，并用测试证明 Agent-visible message 不泄露内部账本词。
4. 给 runtime prompt、Skill 和 feedback 输出加 forbidden concept lint，排除 coding-agent 文档和机器产物合同。
5. 给 renderer unavailable、stale mapping、publish failure 各补一个 ownership 测试。
