# Bug：unit-boundary / post-unit resume 后 Agent 与工具反馈回路未收敛

- Status: `OPEN / TRIAGED`
- Severity: `P1`
- Discovered: `2026-08-27`
- Subsystem: Template Extraction Skill output contract、unit-boundary、post-unit Agent loop、`docfit_evidence` Tool feedback、App timeout/trace
- Affected flow: `prepare-template --until post-unit`、`prepare-template --from unit-boundary --until post-unit`

## 1. 本次被测模块结论

本轮原始目标是修正 Agent 语义输出里的绑定缺口：Agent 不能只用自然语言描述“这是正文结构”或“这是字段”，
而必须把可执行对象与 Registry field / body member 明确绑定。对应修改落在 Skill / Agent-facing 输出合同：

```text
Agent semantic_judgment
  -> structure_ref / members / covered_reading_block_ids
  -> 每个正文结构成员有明确 field_id
  -> members 与 covered_reading_block_ids 按文档顺序一一对应
```

本轮已完成的验证结论：

- `logic/contract`：通过。Skill 文档已经要求正文结构逐块绑定，contract 测试已固定这个要求。
- `runtime wiring`：通过。`prepare-template` runtime 配置加载 `docfit-school-extract` Skill，post-unit prompt 仍指向
  accepted unit context 和 `unit_evidence_packet`。
- `real Agent output`：未验证到。真实运行没有走到“Agent 输出新的正文结构 semantic_judgments”这一步。
- `product acceptance`：未验证。没有生成新的 final template，也没有检查 DOCX 物化结果。

因此，对本次修改模块的准确结论是：

```text
Skill / output contract 已经补上并通过 contract 层验证；
真实 Claude Agent 是否会稳定按该合同输出，还没有被验证；
未验证的原因不是该模块已经失败，而是测试链路在 unit-boundary / resume / Tool feedback loop 之前被阻断。
```

后续讨论 unit-boundary、SDK 等待、Tool feedback，都应放在这个结论之后：它们是验证这次修改时暴露出的
阻塞问题，不是本轮修改模块本身的验证结论。

## 2. 测试暴露的当前阶段 blocker

当前阶段目标要先明确：我们不是先去做中间解析层，也不是先证明正文结构 Skill 已经稳定。当前阶段必须先让
模板提取 Agent 在“单元识别 / 已接受单元 resume / 工具反馈修复”这条链路上闭合：

```text
真实输入 / accepted unit
  -> Agent 能识别或复用单元
  -> Agent 能读取 unit evidence
  -> Tool feedback 能让 Agent 修正或清晰退出
  -> Harness/App 能写出 checkpoint、semantic judgments 或明确 failure
```

这次测试暴露了三个同属当前阶段的 blocker：

1. 从单正文输入直接跑 `--until post-unit` 时，unit-boundary 阶段被 Harness 拒绝，流程没有进入
   post-unit。这说明“单元识别入口”仍可能阻断当前阶段验证。
2. 使用 accepted unit-boundary proof 做 resume 后，Claude SDK 多次停在 `receive_response()` 等待，
   没有自然返回，也没有稳定写出清晰 failure。
3. 单正文 resume 中，Agent 收到可恢复的 `unit_slice_scope_missing` 工具反馈后，没有继续修正 Tool
   调用，也没有返回 `needs_input` 或 `semantic_judgments`。

因此，本 bug 的核心不是“Tool 单点返回是否正确”，而是 Agent/Tool/Host feedback loop 没有形成可收敛闭环。
这是当前阶段要修的范围，不能推迟到后续优化。

## 3. 真实复现事例

### 3.1 事例 A：从头跑单正文输入，卡在 unit-boundary

输入包：

```text
temp/skill-body-structure-output-20260827-115844/input

selected unit:
04-paper-body
```

运行方式：

```bash
uv run docfit prepare-template \
  --school-template temp/skill-body-structure-output-20260827-115844/input/school-template.docx \
  --school-requirements temp/skill-body-structure-output-20260827-115844/input/school-requirements.pdf \
  --field-registry temp/skill-body-structure-output-20260827-115844/input/field-registry.yaml \
  --output temp/skill-body-structure-output-20260827-115844/run-post-unit \
  --until post-unit
```

实际结果：

```json
{
  "status": "failed",
  "failure": {
    "code": "unit_boundary_checkpoint_failed",
    "message": "Harness rejected unit boundary candidates before main flow.",
    "origin": "harness",
    "retryable": true,
    "status": "needs_input",
    "suggested_actions": ["revise units[] against Harness feedback"]
  },
  "sdk_query_count": 0,
  "tool_uses": []
}
```

Tool audit 显示 unit-boundary Agent 读取过 document map：

```json
{"input":{"focus":"document_map","schema_version":"docfit_evidence_input_v1"},"result":{"focus":"document_map","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"document_map","offset":20,"schema_version":"docfit_evidence_input_v1"},"result":{"focus":"document_map","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"document_map","offset":40,"schema_version":"docfit_evidence_input_v1"},"result":{"focus":"document_map","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"document_map","limit":200,"offset":0,"schema_version":"docfit_evidence_input_v1"},"result":{"focus":"document_map","status":"ok"},"tool":"docfit_evidence"}
```

暴露问题：

- 单元识别失败阻断了 post-unit Skill 验证；
- failure 只说 Harness 拒绝 boundary candidate，没有保留可读的 rejected unit shape、具体缺口或下一轮 Agent
  应如何修；
- 这属于当前阶段的入口稳定性问题，不能被“改用 resume 规避”彻底抹掉。

### 3.2 事例 B：多单元 resume 后 SDK 等待，无清晰 completion

输入使用已 accepted 的多单元 proof：

```text
source task root:
temp/complete-real-input-validation-20260826-toc-body-proposal/run-fixed-readiness

accepted checkpoint:
temp/complete-real-input-validation-20260826-toc-body-proposal/run-fixed-readiness/work/.docfit/unit-boundary-checkpoint.json
```

该 checkpoint 的关键事实：

```text
status=ok
checkpoint=unit-boundary
units:
- unit-toc-sample
- unit-body-sample
- unit-opening-report-form
```

一次 resume 运行：

```text
temp/skill-body-structure-resume-20260827-120534
```

结果只写出：

```text
work/.docfit/prepare-template-task.json
```

没有 tool audit、没有 unit-boundary checkpoint 副本、没有 template-agent-execution。人工中断时栈停在
Claude SDK `receive_response()`。

另一次多单元 resume 运行：

```text
temp/skill-body-structure-resume-20260827-120554
```

Tool audit 显示 Agent 已经读取多个 unit 和 Registry：

```json
{"input":{"focus":"unit_evidence_packet","schema_version":"docfit_evidence_input_v1","unit_id":"unit-opening-report-form"},"result":{"focus":"unit_evidence_packet","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"unit_evidence_packet","schema_version":"docfit_evidence_input_v1","unit_id":"unit-toc-sample"},"result":{"focus":"unit_evidence_packet","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"unit_evidence_packet","schema_version":"docfit_evidence_input_v1","unit_id":"unit-body-sample"},"result":{"focus":"unit_evidence_packet","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"registry_field","schema_version":"docfit_evidence_input_v1","semantic_field":"thesis title Chinese"},"result":{"focus":"registry_field","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"registry_field","schema_version":"docfit_evidence_input_v1","semantic_field":"student name"},"result":{"focus":"registry_field","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"registry_field","schema_version":"docfit_evidence_input_v1","semantic_field":"advisor name"},"result":{"focus":"registry_field","status":"ok"},"tool":"docfit_evidence"}
```

但该运行没有写出：

```text
work/.docfit/harness/semantic-judgments.json
work/.docfit/post-unit-checkpoint.json
work/.docfit/template-agent-execution.json
```

暴露问题：

- resume 能把 accepted units 交给 Agent，但 Agent/SDK loop 仍可能无清晰 completion；
- Tool 调用已有足够证据时，Host 没有提供“最后一次工具调用之后 Agent 无输出”的 liveness failure；
- 这不是未来产品验收问题，而是当前阶段真实 post-unit 验证的 blocker。

### 3.3 事例 C：单正文 resume 后 unit_slice scope 反馈未收敛

本复现使用已接受的单正文单元 task root：

```text
source task root:
temp/template-minimal-0820-regression-151901/04-paper-body-long/postunit

accepted unit:
u-paper-body

accepted checkpoint:
temp/template-minimal-0820-regression-151901/04-paper-body-long/postunit/work/.docfit/unit-boundary-checkpoint.json
```

该 checkpoint 的关键事实：

```text
status=ok
checkpoint=unit-boundary
resolved_units[0].unit_id=u-paper-body
coverage.status=ok
covered_object_count=228
```

运行命令：

```bash
RUN_ROOT=temp/skill-body-structure-resume-single-20260827-121200
SOURCE_ROOT=/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/template-minimal-0820-regression-151901/04-paper-body-long/postunit

DOCFIT_PREPARE_TEMPLATE_TIMEOUT_SECONDS=600 \
DOCFIT_PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS=120 \
uv run docfit prepare-template \
  --school-template "$SOURCE_ROOT/input/school-template.docx" \
  --school-requirements "$SOURCE_ROOT/input/school-requirements.pdf" \
  --field-registry "$SOURCE_ROOT/input/field-registry.yaml" \
  --output "$RUN_ROOT" \
  --from unit-boundary \
  --resume-proof "$SOURCE_ROOT/work/.docfit/unit-boundary-checkpoint.json" \
  --until post-unit
```

这是后续复现正文单元 post-unit loop 的首选入口。它不重新运行完整 unit-boundary。

实际 Tool 调用：

`temp/skill-body-structure-resume-single-20260827-121200/work/.docfit/tool-call-audit.jsonl`
记录到 3 次 Tool 调用：

```json
{"input":{"focus":"unit_evidence_packet","schema_version":"docfit_evidence_input_v1","unit_id":"u-paper-body"},"result":{"focus":"unit_evidence_packet","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"document_map","limit":60,"schema_version":"docfit_evidence_input_v1"},"result":{"focus":"document_map","status":"ok"},"tool":"docfit_evidence"}
{"input":{"focus":"unit_slice","limit":60,"offset":0,"schema_version":"docfit_evidence_input_v1","unit_id":"u-paper-body"},"result":{"failure":{"code":"unit_slice_scope_missing","message":"unit_slice requires scope_ref. Use document_map.summary.text_outline for the full boundary index, then request unit_slice for a specific locator when local context is needed.","origin":"request","retryable":true},"status":"needs_input"},"tool":"docfit_evidence"}
```

关键点：

- 第一次调用已经拿到了 `u-paper-body` 的单元证据包。
- 第三次调用把 `unit_id` 传给了 `unit_slice`，但没有传 `scope_ref`。
- Tool 正确返回 `status=needs_input`、`origin=request`、`retryable=true`、`code=unit_slice_scope_missing`。
- 后续没有新的 Tool 调用，没有写出 `post-unit-checkpoint.json`，也没有写出
  `work/.docfit/harness/semantic-judgments.json`。
- 运行没有自然退出；人工 `Ctrl-C` 后栈停在 `claude_agent_sdk.client.receive_response()` 等待。

## 4. 当前阶段目标

当前阶段的目标应改成下面这个闭环，而不是直接跳到中间解析层：

```text
1. unit-boundary 对单元输入能给出可修复 feedback 或 accepted unit；
2. --from unit-boundary resume 不重新拆单元；
3. Agent 优先读取 unit_evidence_packet；
4. Tool feedback 如果是 retryable，Agent 能修正调用或返回 needs_input；
5. 如果 SDK 等待无后续输出，App 写出 partial trace 和清晰 failure；
6. 只有这条链路稳定后，再验证正文结构 Skill 是否产出逐块 members。
```

当前阶段必须处理：

- 单元识别失败的 Harness feedback 可读性；
- resume 后 Claude SDK 等待响应但没有 failure 的 liveness 出口；
- 工具反馈没有被 Agent/Host 转成下一步行动；
- 单元级 evidence routing，尤其是 `unit_evidence_packet` 与 `unit_slice(scope_ref=...)` 的边界。

当前阶段不应该处理：

- 中间解析层自动修 Agent 语义；
- DOCX materialization handler 的正文结构执行；
- final-template publication / renderer 产品验收；
- 跨学校通用 body parser 规则。

## 5. 暴露的问题

### 5.1 unit-boundary feedback 不够可修复

事例 A 的 failure 停在 `unit_boundary_checkpoint_failed`，但记录里没有足够信息说明 Agent 提交的候选单元为什么
被拒绝、哪一段 boundary 不闭合、下一轮应该如何修。结果是 current-stage 验证只能绕路使用旧 proof。

正确目标不是跳过 unit-boundary，而是让单元识别失败也能闭合：

- 保留 rejected units 或 sanitized shape；
- 返回 affected visible text / document_map window；
- 指明缺少 start/end、coverage overlap、missing block 还是 schema shape；
- 写入 execution trace。

### 5.2 Skill / prompt 的证据路由不够收敛

单元级 post-unit 测试中，Agent 已经拿到了 `unit_evidence_packet`。如果证据包足够，Agent 应直接产出
当前单元的 `semantic_judgments`；如果证据不足，应基于 evidence packet 里的可见边界决定是否需要
具体 `scope_ref`。

当前实际行为是：Agent 又回到 `document_map`，随后尝试不带 `scope_ref` 的 `unit_slice`。这说明
Agent-facing 证据路由还不够明确：

- 单元入口下应优先使用 `unit_evidence_packet`；
- `unit_slice` 只用于具体 locator 的局部上下文；
- `unit_id` 不是 `unit_slice` 的替代范围参数。

这属于 Skill / startup prompt / Tool schema description 的共同边界，不应通过中间物化层修复。

### 5.3 Tool feedback 是可恢复的，但 Agent loop 没有恢复

`docfit_evidence` 对缺 `scope_ref` 的返回本身是合理的。现有 contract 已覆盖：

```text
tests/contract/test_docfit_evidence_tool.py::test_t1_unit_slice_requires_scope_ref_instead_of_returning_global_window
```

该测试证明 Tool 不会把缺范围的 `unit_slice` 静默降级成全局窗口。

但这次真实问题不止是 Tool contract。缺口在 Agent loop：

- Agent 收到 retryable Tool feedback 后没有改为 `unit_evidence_packet` 或补 `scope_ref`；
- Agent 没有返回 `needs_input`；
- Host 没有把这类停滞转成清晰 failure。

因此需要新增或修正 Agent-loop 级测试，而不是只看 Tool contract。

### 5.4 App / SDK 等待缺少清晰 liveness 出口

本次运行设置了：

```text
DOCFIT_PREPARE_TEMPLATE_TIMEOUT_SECONDS=600
DOCFIT_PREPARE_TEMPLATE_IDLE_TIMEOUT_SECONDS=120
```

实际观察是，进程长时间停在 Claude SDK `receive_response()`，没有写出完整 execution trace；最终通过
人工中断结束。当前 timeout 机制没有把“Tool feedback 后无后续 Agent 输出”稳定转成产品可解释 failure。

这属于 App runtime / SDK loop liveness 问题。它和正文结构 Skill 输出质量是两个问题，不能混在一起归责。

### 5.5 可观测性不足

`tool-call-audit.jsonl` 有每次 Tool 的 input/result/duration，但没有时间戳，也没有在人工中断时写出
partial execution summary。排查时只能从少量 audit 和 KeyboardInterrupt 栈判断停滞点。

建议后续至少补：

- Tool audit timestamp；
- Agent receive 阶段最后一次消息时间；
- 人工中断或 timeout 时写 partial execution trace；
- retryable Tool feedback 后无后续输出的专门 failure code。

## 6. 非问题范围

本 bug 不证明以下结论：

- 不证明正文结构 Skill 的逐块绑定要求无效；
- 不证明 Agent 已经或没有稳定输出 `members` 与 `covered_reading_block_ids` 一一对应；
- 不证明需要立刻开发中间解析层；
- 不证明 DOCX materialization handler 有问题；
- 不证明 renderer、publication 或 final Word 产品验收失败。

当前已证明的问题是：unit-boundary、resume、Tool feedback、SDK wait 这条 current-stage loop 没有稳定闭合。

## 7. 修复方向

### Step 1：补 current-stage bug 回归测试

新增聚焦测试，不从头跑完整模板业务流，但覆盖当前阶段真实 blocker：

1. unit-boundary checkpoint rejected 时，`template-agent-execution.json` 必须包含 sanitized rejected units、
   affected evidence 和可修复 feedback；
2. post-unit resume 后，如果 SDK 等待无后续输出，必须写出 partial execution trace；
3. retryable Tool feedback 后无后续 Agent 输出，必须返回稳定 failure，而不是无限等待；
4. 单正文 resume 使用 accepted `u-paper-body`，不重新拆单元。

### Step 2：收紧单元级 evidence 路由

主 prompt、Skill 或 Tool schema description 应明确：

```text
post-unit 单元入口优先使用 focus=unit_evidence_packet + unit_id。
只有当需要具体 locator 附近上下文时，才调用 focus=unit_slice + scope_ref。
不要用 unit_id 调用 unit_slice。
```

这属于 Agent-facing 证据路由，不是 DOCX 物化规则。

### Step 3：补 runtime liveness 出口

如果 SDK 长时间没有后续 message，App 应写出 partial trace 并返回稳定 failure。建议 failure 记录：

```text
origin=agent 或 application
code=post_unit_agent_stalled_after_tool_feedback
last_tool=docfit_evidence
last_tool_code=unit_slice_scope_missing
last_tool_retryable=true
affected_unit_id=u-paper-body
```

归责可以先保守标为 `application`，因为 Host 没有把停滞变成可解释结果；如果后续证明 prompt/Skill
导致 Agent 必然卡住，再把修复点归到 Skill。

### Step 4：修 unit-boundary rejected feedback

unit-boundary 被 Harness 拒绝时，当前阶段需要可修复反馈，而不是只给 `revise units[]`：

```text
origin=harness
code=unit_boundary_checkpoint_failed
affected_document_window=...
rejected_unit_summary=...
missing_or_overlap_reason=...
agent_action=revise unit boundaries using document_map visible text
```

这仍然不让 Agent 接触内部 object/hash 账本，只给 readable boundary context。

## 8. 验证计划

### logic / contract

现有 Tool contract：

```bash
uv run pytest -q tests/contract/test_docfit_evidence_tool.py::test_t1_unit_slice_requires_scope_ref_instead_of_returning_global_window
```

应继续通过，证明 Tool 没有静默返回全局窗口。

### focused Agent-loop

后续新增测试应从单元内容或 accepted checkpoint 进入，不跑完整多单元业务流：

```text
accepted unit checkpoint -> post-unit prompt -> unit_evidence_packet -> retryable Tool feedback -> clear recovery or clear failure
```

还需要覆盖 unit-boundary rejected 的反馈可读性：

```text
unit-boundary Agent output rejected -> harness feedback packet includes affected visible context and repair action
```

### real replay

真实回放只使用单正文输入：

```bash
uv run docfit prepare-template \
  --school-template "$SOURCE_ROOT/input/school-template.docx" \
  --school-requirements "$SOURCE_ROOT/input/school-requirements.pdf" \
  --field-registry "$SOURCE_ROOT/input/field-registry.yaml" \
  --output "$RUN_ROOT" \
  --from unit-boundary \
  --resume-proof "$SOURCE_ROOT/work/.docfit/unit-boundary-checkpoint.json" \
  --until post-unit
```

验收不是 final DOCX，而是：

- 不重新拆 unit；
- 不再卡在 `unit_slice_scope_missing` 后无输出；
- 如果 resume 后 SDK 等待超时，返回清晰 failure 和 partial trace；
- 如果 unit-boundary 被拒绝，返回可修复 boundary feedback；
- 如果 Agent 输出正文结构 judgment，再检查 `members` 与 `covered_reading_block_ids` 是否一一对应。
