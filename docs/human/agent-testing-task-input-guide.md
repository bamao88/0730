# 给 Agent 输入测试任务的验证合同写法

状态: 学习笔记
更新日期: 2026-08-26

这份文档记录一个常见协作问题：Agent 做开发后容易偏向证明代码逻辑成立，
但没有证明真实输入链路成立。它用于帮助人给 Agent 下测试任务时，把“完整测试”的
边界先定义清楚，避免阶段还没闭合就推进到下一阶段。

## 核心原则

完整测试不等于全量测试。

完整测试应该是：对当前阶段承诺负责的行为，覆盖关键成功路径、失败路径、边界路径，
并明确哪些没有覆盖。

因此，不能只问“有没有跑测试”，而要先问：

- 当前阶段到底负责保证什么？
- 当前阶段不负责保证什么？
- 哪些测试没做时，不能宣称这个阶段完成？
- 每个验证证明什么，又不证明什么？

## 验证层级

涉及 Agent + DOCX + 真实模板链路时，建议固定使用四个验证层级：

| 层级 | 含义 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| `logic/contract` | 单元测试、contract test、mock/monkeypatch、最小构造输入 | 代码分支、schema、异常、receipt shape 正确 | 不证明真实输入会走到这条路径 |
| `real replay` | 使用真实 task root、真实 inventory、真实 semantic judgments 回放 | 真实材料下 Harness/App 路径可复现 | 不证明 Agent 能收到反馈并修正 |
| `E2E agent loop` | 跑真实 Agent + prepare-template 回路 | feedback 能回到 Agent，Agent 能 revision 后继续 | 不证明最终 DOCX 产品质量完全合格 |
| `product acceptance` | 检查最终 DOCX、fill-contract、evidence/report | 用户可依赖最终产物 | 不自动定位中间层 bug 原因 |

没有完成 `real replay` 或 `E2E agent loop` 时，不应说“真实输入跑通”“完整跑通”
或“端到端验证通过”。更准确的说法是：“logic/contract 验证通过，真实输入验证尚未完成。”

## 怎么判断一次测试是否能代表“Agent 会收到具体反馈”

如果目标是证明：

> 当 Agent 的输出不完整时，系统能够把不完整的具体点反馈给 Agent，让 Agent 补充。

那么一次有效验证至少要包含这些证据：

- 使用真实输入，最好不是只用最小 fixture 或封面样例。
- Agent 第一次输出确实存在不完整点。
- Harness/App 没有继续执行下游 materialization 或发布。
- feedback 里包含具体缺失项，例如 `registry_field`、`structure_ref`、`members`。
- feedback 里包含具体定位，例如 `reading_block_id`、`reading_range_id` 或 `judgment_id`。
- Agent 在同一个回路收到 feedback 后，第二次输出补齐缺失项。
- 补齐前 candidate 或最终产物没有被提前生成。

例如，真实非封面输入验证可以支持这样的结论：

> 已用真实非封面输入验证：materialization readiness 不完整时，Harness 能生成包含具体
> reading block 和缺失项的 Agent-readable feedback，Agent 能在同一回路补充后继续执行。
> 当前证据覆盖缺字段和缺正文结构语义，不等于所有语义不完整场景已全覆盖。

这个结论是合格的，因为它同时说明了“证明了什么”和“没有证明什么”。

## 开发前要 Agent 先交验证合同

为了避免 Agent 事后用一句“完整相关回归”概括测试，可以在实现前要求它先输出验证合同。

推荐输入：

```text
先不要写代码。先给我这个阶段的验证合同：

1. 当前阶段负责保证什么？
2. 当前阶段不负责保证什么？
3. 必须覆盖哪些失败类型？
4. 必须覆盖哪些正向放行类型？
5. 哪些用 logic/contract 测试，哪些必须用真实 replay，哪些必须用 E2E agent loop？
6. 每个测试完成后能证明什么，不能证明什么？
7. 哪些测试没做时，不能宣称进入下一阶段？
```

验证合同应该落成矩阵，而不是自然语言承诺。

| 场景 | 层级 | 输入 | 预期结果 | 证明什么 | 不证明什么 | 阻塞下一阶段 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| slot 缺 `registry_field` | real replay + E2E | 真实 `06-proposal` | 返回具体 block + missing field | Agent 可补字段 | 不证明所有学校 | 是 | done |
| body 缺 `structure_ref/members` | real replay | 真实 `04-paper-body` | 返回 missing structure | readiness gate 拦截 | 不证明 Agent 会补 | 是 | done |
| 字段 ID 不在 Registry | contract 或 real replay | 真实或构造 | 返回 unknown field | Registry gate 生效 | 不证明 Agent 修正质量 | 视阶段而定 | pending |
| 完整 slot judgment | contract | 构造输入 | 放行 materializer | gate 不误拦 | 不证明最终 DOCX 质量 | 是 | done |

## 可以直接给 Agent 的硬性要求

下面这些句子可以直接放进任务里：

```text
“完整测试”必须先枚举场景，不允许事后说完整。
```

```text
每个验证必须写清楚证明范围和不证明的范围。
```

```text
任何“跑通”“完成”“可进入下一阶段”的表述，都必须绑定测试矩阵中的 done 行。
如果矩阵还有 pending 行，只能说“当前阶段部分完成”，并说明 pending 是否阻塞下一阶段。
```

```text
如果只跑了 unit/contract/mock/monkeypatch 测试，最终汇报必须写成 logic/contract 验证通过，
不能写成真实输入跑通或 E2E 跑通。
```

```text
如果声称 real replay，请给出真实 task root、真实 source、reading block/object 数量、
篡改点或失败点、receipt 路径、candidate 数量和关键 feedback 字段。
```

```text
如果声称 E2E agent loop，请给出 Agent 第一次输出的问题、Harness 返回的 feedback 类型、
Agent 第二次修正的字段、query/attempt 次数，以及补齐前是否没有提前生成 candidate。
```

## DocFit 场景里的常见误导说法和纠正

### 误导 1：把 contract test 说成跑通

不准确：

> 验证已跑通，缺字段会返回给 Agent。

如果实际只用了 monkeypatch 或最小构造输入，应该改成：

> logic/contract 验证通过：缺字段时会生成 Agent-readable packet，且 fake materializer
> 未被调用。真实 replay 和 E2E agent loop 尚未验证。

### 误导 2：只测封面或 S00，却说代表真实模板链路

不准确：

> 用 S00/cover 跑过了，可以代表真实模板。

应该改成：

> S00/cover 只能证明最小或封面路径。若要证明 post-unit materialization readiness，
> 还需要至少覆盖非封面单元，例如 `06-proposal` 表格字段槽、`04-paper-body` 正文结构。

### 误导 3：测试矩阵只列“正向成功”，没有失败路径

不准确：

> 正常 slot judgment 能生成 candidate，所以 readiness gate 没问题。

应该补充失败路径：

- 缺 `registry_field`
- 字段 ID 不在 Registry
- 缺 `structure_ref`
- 缺 `members`
- 没有 `semantic_judgments`
- reading block 覆盖缺失
- judgment 覆盖冲突或 overlap

### 误导 4：只证明拦截，没有证明反馈能回到 Agent

不准确：

> receipt 里有 `agent_revision_packet`，所以 Agent 会修。

应该改成：

> real replay 证明 receipt 内容正确；还需要 E2E agent loop 证明这个 packet 真的回到
> Agent，并且 Agent 在同一 session 里补齐后继续。

### 误导 5：把“所有测试”当成阶段完整

不准确：

> 我跑了完整测试。

更好的汇报应该绑定矩阵：

> 本阶段负责的 5 个阻塞场景中，4 个已完成，1 个 pending。pending 是字段 ID 不在
> Registry 的真实 replay；它阻塞“readiness 对真实输入完全闭合”的结论，但不阻塞
> contract 层合并。

## 推进下一阶段前的判断

推进下一阶段前，不要求“全部测试都跑完”，但要求阶段边界内的阻塞项清楚。

可以用这个判断：

- 如果 pending 场景属于当前阶段承诺负责的核心失败类型，不能推进。
- 如果 pending 场景只影响更高层级结论，例如 product acceptance，可以推进代码重构，
  但汇报时不能声称产品验收完成。
- 如果只完成了 `logic/contract`，可以进入局部代码 review，但不能进入“真实链路已闭合”的阶段。
- 如果完成了 `real replay`，可以说明真实输入路径可复现，但不能替代 Agent 回路验证。
- 如果完成了 `E2E agent loop`，可以说明 Agent feedback/revision 闭环成立，但仍需区分最终 DOCX 质量验收。

## 推荐的最终汇报格式

```text
验证层级：
- logic/contract: done。证明 ...
- real replay: done/pending。证明 ...；不证明 ...
- E2E agent loop: done/pending。证明 ...；不证明 ...
- product acceptance: done/pending。

阶段结论：
当前可以宣称 ...
当前不能宣称 ...

阻塞下一阶段的 pending：
- ...

非阻塞后续项：
- ...
```

这样的汇报方式能把“做了多少测试”转成“这个阶段到底闭合了没有”，更适合判断是否推进。
