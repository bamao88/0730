---
plan_scope: template-field-id-vocabulary-boundary
status: CONTINUE
created: 2026-09-03
phase: 0-8 cleanup and representative matrix pass
phase_0_conclusion: ACCEPTED
phase_1_conclusion: ACCEPTED
phase_2_conclusion: ACCEPTED
phase_3_conclusion: ACCEPTED
phase_4_conclusion: ACCEPTED
phase_5_conclusion: ACCEPTED
phase_6_conclusion: ACCEPTED
phase_0_last_audited: 2026-09-11
verification_level: logic/contract + source-noop semantic gate + vocabulary-only Skill tree + real replay + E2E agent loop + representative product provenance + HUNAU 10/10 current-hash live provenance + NJAU 10/10 current-hash live provenance + PKU 1/12 current-hash live provenance + PKU copyright cleanup-span real replay + registry_binding retired + semantic_part_index fail-closed + apply package-only phase-review gate + tool-audit alias removal + direct-intent helper removal + App accepted-review current-shape gate
---

# 字段 ID 词表边界迁移清单

本文是 `template-field-id-vocabulary-boundary-refactor.md` 的 Phase 0 审计证据。
它不表示迁移完成，只固定后续必须删除、封死或迁移的运行时路径。

## Phase 0 结论（2026-09-11）

**ACCEPTED**。

本轮完成了入口归属、目标调用图、旧输入处置、负向测试目标和 hash-bound 真实输入 manifest，
并冻结了 exact-text / structural extent / cross-entry / candidate mapping 合同。当前生产树仍有四个
已归属、已有唯一处置的 P1 implementation residual；它们说明 Phase 1–6 尚未实施完成，不是 Phase 0
的未决合同或未归属入口：

1. `src/docfit/tools/inspection.py::source_entry_id_for()` 为每个 inspect component 生成一套
   `source-entry-*`；`src/docfit/template/source_entries.py::source_entry_id_for_entry()` 又为归一化
   content unit 生成另一套同前缀 ID。二者含义和 hash payload 不同，当前 inspect/Harness
   `inspect_objects` 路径仍可把 component credential 当作 source entry。
2. `src/docfit/app/prepare_template.py::_post_unit_inventory_from_checkpoint()` 与
   `src/docfit/tools/service.py::DocFitToolService.evidence(focus=unit_evidence_packet)` 都调用
   `normalize_source_entries_from_objects()`。前者用全 inventory 的 `start_block`，后者每个 unit 从默认
   block 1 重新开始；而 `source_order` 进入 ID hash，因此同一输入内容可随入口、unit 和窗口得到不同 ID。
3. `src/docfit/app/prepare_template.py` 的 Agent schema/prompt、`src/docfit/template/harness.py`、
   `semantic_review.py`、`materialization/compiler.py`、`context.py` 和 `runtime.py` 仍接受或执行
   `reading_block_id` / `reading_range_id` / unit/object-only compatibility scope。新旧主定位仍双读，
   不能把 reading view 宣称为纯投影。
4. `normalize_source_entries_from_objects()` 通过 `" ".join(value.split())` 改写空白，并跳过空文本
   group；尚无 frozen typed structural extent。它与 canonical plan 的 exact Python-code-point 文本、
   空白/换行不任意 normalize、非文本/空结构显式 extent 合同相冲突。

这些 residual 都有下表中的 owner、delete-or-explicit-reject disposition、责任阶段和负向测试目标，
不需要用户新增合同选择；因此 Phase 0 的“找全、定责、冻结合同”停止条件已满足。本轮不改 production
code，也不把当前树误报为已经完成 source-location unification。若后续 source scan 发现本表以外的成功
入口，或实现证明冻结合同不可执行，Phase 0 立即 REOPEN；否则下一步按 Phase 1 开始关闭 residual 1/2/4。

## Phase 1 结论（2026-09-11）

**ACCEPTED** at `logic/contract` + deterministic `real replay`。

- residual 1 已关闭：inspection component generator/public alias/ref 已删除；canonical ID 仅由
  `template/source_entries.py::source_entry_id_for_entry()` 生成。P0-N01 旧 credential 明确拒绝。
- residual 2 已关闭：App 仅在接受 unit checkpoint 后、任何 unit projection 前构建一次
  `CanonicalSourceInventory`；Harness 持久化；Tool 只读 unit packet。缺失、source hash 或 unit projection
  digest 陈旧均 fail closed。P0-N02/P0-N03 已由 contract 与三校 replay 覆盖。
- residual 4 已关闭：canonical text 不 trim/collapse/rewrite/normalize；所有文本 offset 均按 Python Unicode
  code point；空白/非文本结构使用 typed `whole_entry`，未知结构显式 unsupported。P0-N04/P0-N05 已覆盖。
- downstream consumption：HUNAU/NJAU/PKU 32 个 logical pages 的真实 inspect inventory 在窗口、顺序与重试
  下稳定；三校代表页的 App → Harness → Tool 路径复用同一 persisted inventory，Tool 未重新 inspect。
- residual 3 保留并明确归 Phase 2/3/5/6：reading block/range 与 object-only compatibility 尚未按 Phase 2
  删除。本阶段没有增加 alias、fallback、双读、old-to-new normalizer 或 Agent bookkeeping。
- 证据不包含 `E2E agent loop` 或 `product acceptance`；总体计划保持 `CONTINUE/REOPEN`，下一阶段是 Phase 2。

## Phase 2 结论（2026-09-11）

**ACCEPTED** at `logic/contract` + real `E2E agent loop`。

- `POST_UNIT_OUTPUT_SCHEMA` 与 shared ordered-parts validator 只接受
  `semantic_judgments[].source_entry_id + parts[]`；`scope.reading_block_id` / `reading_range_id` 在 schema、
  raw Agent-output contract 和 Harness submission 均 fail closed，Harness 不落盘，不做旧转新。
- Agent-authored span/slot/object/locator refs 和旧 field aliases 继续由 schema/denylist 拒绝；本阶段未增加
  alias、fallback、双读或 normalizer。
- reading block/range 保留为 packet view 与 feedback grouping。Harness 允许 view 使用已声明的
  `covered_source_entry_ids` 而不强制 view 自己成为 text-span locator，并拒绝 view 引用 inventory 外的 entry。
- prompt 与正文 Reference 已删除 compatibility scope 指引；跨 source-entry 责任按文档顺序拆成各 entry 的
  judgment，不创建独立 range 主定位。
- P0-N06 red baseline `3 failed`；最终 focused contract `58 passed`，Ruff、strict mypy、legacy-scope source scan
  和 `git diff --check` 通过。探索性全 contract 为 `483 passed / 68 failed`，失败主要来自 Phase 3/6 仍按旧
  reading scope 构造的 fixtures；这些不通过兼容层修复。
- 90 秒首次尝试在 `temp/phase2-p0-n06-e2e-20260911` 以
  `template_agent_no_progress_timeout` 安全失败，未作为成功证据。依据同 backend 的既有延迟记录，将
  no-progress 门限隔离提高到 600 秒后，在全新 root
  `temp/phase2-p0-n06-e2e-long-20260911` 完成真实 post-unit loop：post-unit 第一次 structured output
  获得 Harness `needs_feedback`，Agent 第二次输出修订后 `accepted`。最终落盘 16 个 judgments，全部使用
  `source_entry_id + parts + Harness resolved_spans`，旧 `scope` 数量为 0；checkpoint 为 `status=ok`。
- 该 E2E 只证明 Phase 2 Agent 合同、反馈和修订闭合，不证明 Phase 3 精确 resolver、实际 DOCX 写入或
  product acceptance。探索性全 contract 的旧 scope fixtures 仍归 Phase 3/6 迁移，不允许恢复兼容路径。

## Phase 3 结论（2026-09-11）

**ACCEPTED** at `logic/contract` + hash-bound `real replay`。

- Harness resolver 入口、shared persisted-review gate、App resume 和 Tool shared review 已统一到
  `template/source_spans.py`；exact part text 以 Python code-point 半开区间顺序解析，返回 source content、
  typed extent、source/inventory identity 与 ordered Word fragments。
- P0-N07/P0-N08 已关闭：无 source entries 的 object-only inventory/review 不再成功；旧 reading block/range
  judgment fixtures 已删除或反转为显式拒绝。Harness 内旧 reading-scope resolver 与 shared review 的
  object-only coverage fallback 已删除，无兼容转换器。
- swapped offsets/fragments 在重算全部可重算引用与摘要后仍拒绝；wrong text/entry、parent expansion、
  out-of-bounds、ambiguity、duplicate、overlap/gap/omission 由 focused resolver/re-read tests fail closed。
- 下游 fixture 使用 Harness-owned resolved spans；现有 compiler/materializer 合同断言消费原对象相等的
  `span_ref` / `slot_ref`，不从文本、locator 或 `covered_object_ids` 重选位置。本阶段未实施 Phase 5/6。
- focused proof 为 `210 passed`，Ruff 与相关 production mypy 通过。real replay 证据见
  `temp/phase3-source-span-replay-structural-20260911/phase3-replay-evidence.json`：source hash
  `5456f95d56424fccf72bc606b2c75db9eb85a561a0a6bbd2cee6af47a3d6a8cc`，8 个 exact Agent judgments 加
  5 个显式 whole-entry replay judgments，共 13 entries、19 spans（含 5 个无伪 offsets 的 structural spans），
  submit/re-read/App resume/Tool review/next-consumer exact checks 全部为 true。
- 探索性全 contract 为 `537 passed / 5 failed`；失败均来自本轮开始前已有 dirty Registry hash 或缺 persisted
  inventory 的无关 fixture，不属于 Phase 3，未修改或掩盖。没有新的 E2E Agent loop 或产品验收证据。

## Phase 5 结论（2026-09-11）

**ACCEPTED** at `logic/contract` + hash-bound `real replay`。

- compiler 只接受带 current accepted-review envelope 的 `source_entry_id + parts + resolved_spans`；
  reading block/range compatibility scope、缺失或不可解析 span、缺/错 fragments 均不能形成 intent。
- 所有产出 field ID 都以 typed binding 指向 accepted Agent part 和其 canonical span/slot ref，并由同一
  pre-input vocabulary + Registry snapshot gate 约束；没有自然语言、role/reason 或默认 catalog 补字段。
- context 只用 shared resolver 对当前 inventory 重解析 accepted SourceSpan，并逐项比对 snapshot、inventory
  digest、source content 和 Word fragments；reading/unit/object/text/locator/covered-object fallback 已从该层删除。
- reopened adjacent fixture audit 将旧 reading block/range/unit 成功 fixture 迁移为 current
  source-entry + canonical resolved span + accepted-review fixture，并把退役 target-selection 路径保留为
  fail-closed 覆盖；五文件 focused contract 为 `82 passed`，owned Ruff、strict mypy、diff check 通过。
  Phase 3 hash-bound 真实输入
  replay 产出 13 intents / 19 spans / 3 field bindings；accepted 与 next-contract flattened-span digest 均为
  `b824d08b6e9d135d984fe82976a43c84e26aad3cd26478c5899dc110748bf26a`，stale inventory 在执行前拒绝。
- 这只证明 compiler/readiness 与下一执行合同；Phase 6 handler、实际 DOCX 写入、发布、恢复和消费者未在
  本阶段实现或验证，也没有新增 E2E Agent loop / product acceptance。

## Phase 6 结论（2026-09-11）

**ACCEPTED** at `logic/contract` + actual DOCX/publication/consumer `real replay`。

- handler/executor 只以 Phase 5 typed `resolved_spans` / `field_bindings` 为执行输入，并在 mutation 前解析、
  核对全部 ordered Word fragments；宿主和 Tool 共用同一个 exact locator resolver。
- receipt、原子 publication、Fill Contract provenance、resume 和 placement consumer 绑定完整 accepted span、
  source entry/fragments、Registry/review/vocabulary digest 与实际 candidate/result hash；旧或错接包 fail closed。
- 相关 14 文件合同矩阵 `343 passed`，Ruff、strict mypy 与 diff check 通过。真实回放证据见
  `temp/phase6-materialization-real-replay-20260911c/phase6-replay-evidence.json`：3 个 selected paragraphs
  改变，19 个 unselected paragraphs、表格/段落属性及 15 个其他 package members 不变；恢复与真实 consumer
  均读取同一持久化合同。
- 本结论不包含新的 `E2E agent loop` 或 `product acceptance`；Phase 7/8 保持后续责任。

## 冻结的源定位合同

以下决定是 Phase 1–6 的实现输入，不再留给下游自行猜测：

- `CanonicalSourceInventory` 由输入隔离后、任何 unit 分页或 Agent 取证前一次性生成，绑定不可变
  `source_snapshot_sha256`；App/Harness 持久化它，Tool、packet、resume、compiler 和 publication 只读或投影，
  不重新 normalize。
- `SourceEntry` 是该 inventory 中的 canonical content unit。`source_entry_id` 是 inventory-owned opaque ID；
  只有 normalization 层生成，消费者不得从 locator、fingerprint、窗口顺序或可见文本重新计算。
- 文本 entry 的 `text` 是 canonical inspect fragments 按文档顺序的精确 Python Unicode code-point 序列；
  不 trim、不压缩空白、不转换换行、不做 Unicode normalization。每个 provenance fragment 必须给出
  entry-local 半开区间 `[start, end)`，按原文可逆到 Word fragment。
- 无文本但会影响 coverage/布局/执行的 paragraph、table、picture、shape、SDT 等使用
  `extent: {kind: whole_entry}`；文本范围使用
  `extent: {kind: text, start: <int>, end: <int>}`。unsupported structure 显式阻断，不能静默遗漏。
- `SourceSpan` 是 `{source_entry_id, extent}`。跨 entry 动作是有序 `SourceSpan[]`，不创建拥有独立定位权的
  range ID。reading block/range/unit 仅是 packet view 与 feedback grouping，不是 judgment 或执行输入。
- `ResolvedSourceSpan` 绑定 source snapshot、规范 span、精确 `expected_source_content`、有序 Word fragments
  及 fragment-local ranges。内部 fragment 可携带 object ID/locator/fingerprint，但调用者不能替换它们。
- `ExecutionReceipt` 至少绑定 accepted-semantics digest、source snapshot、ordered source spans、resolved
  fragments、candidate-before/after hashes、实际 changed ranges、operation outcome；局部失败不发布。
- `slot_ref` 只机械绑定 accepted `SourceSpan + field_id`；Fill Contract 的 locator 是已发布 DOCX 的传输定位，
  不能反向替代 source span。publication 必须交叉验证 judgment、resolved span、receipt 和实际 DOCX。
- 旧 checkpoint、inventory、judgment、action package 或 Fill Contract 缺任一新合同绑定时，唯一处置是
  显式拒绝并要求从当前 source 重新生成；无 alias、双读、fallback 或 old-to-new normalizer。

## 入口与目标调用图

目标单一路径：

```text
prepare_template_task(input copy + hashes)
  -> canonical inspect facts
  -> build CanonicalSourceInventory once
  -> persist object-inventory/source-inventory
  -> unit reading packet projection
  -> Agent SourceEntry + ordered-parts judgments
  -> Harness resolve SourceSpan -> ResolvedSourceSpan
  -> accepted semantic review
  -> compiler/readiness typed plan
  -> Executor + handlers (resolved fragments only)
  -> ExecutionReceipt + candidate map
  -> publication cross-check
  -> Fill Contract v2
  -> final-fill consumer / template Eval (slot_ref identity; published locator transport only)
```

| 面 | 当前入口 / 调用者 | 最终 owner | delete-or-explicit-reject disposition | 责任阶段 | 下游消费证据 / 负向目标 |
| --- | --- | --- | --- | --- | --- |
| public launch | `app/cli.py` 的 `prepare-template` -> `run_prepare_template()` | App | 保留一个产品入口；`convert` legacy route 不定义本模块合同，也不得成为第二套 source-location 实现 | 1/7 | CLI contract/docs scan |
| input isolation | `prepare_template_task()` / `PreparedTemplateTask` | App | 保留 source/requirements/Registry copy 与 hash；禁止下游自选另一 source | 1 | resume/publication 校验同一 hash |
| raw inspection | `inspect_document_snapshot()`、`InspectedObject.public()` | Tool inspection | 保留 object/locator/fingerprint 私有事实；删除 component `source_entry_*` 命名/生成，不能进入 canonical ID 面 | 1 | `test_template_source_entry_ids.py` 反转 component-ID 预期 |
| normalization | `template/source_entries.py` | App/Harness normalization | 成为唯一 generator；exact text + typed structural extent；任何第二次调用只允许读取已存 inventory | 1 | 新增跨窗口/调用顺序/重试/空白/结构稳定性矩阵 |
| App inventory | `_post_unit_inventory_from_checkpoint()` | App | 改为选择 canonical inventory 的 accepted-unit entries；不得 per-unit 重新 normalize | 1 | `test_prepare_template_runtime.py` 锁定单次构建/同 ID |
| Tool evidence | `DocFitToolService.evidence(unit_evidence_packet)` | Tool projection | 删除 inline normalize；只按 unit/window 投影 persisted inventory；缺 inventory 显式拒绝 | 1/4 | `test_docfit_evidence_tool.py` 与三校 packet replay |
| reading packet | `build_unit_reading_packet()` / `agent_visible_unit_reading_packet()` | packet projector | reading blocks/ranges 只作 view；Agent coverage 只引用 source entries | 1/2 | `test_template_reading_packet.py` 拒绝 view ID 作 judgment scope |
| Agent schema/prompt | `POST_UNIT_OUTPUT_SCHEMA`、post-unit prompt、`agent_output_contract.py` | Schema/App | 删除 `scope.reading_block_id/reading_range_id` alternative；只收 `source_entry_id + parts` | 2 | schema negative tests；旧 scope result fail closed |
| Harness inventory | `TemplateHarnessService.inspect_objects/submit_object_inventory` | Harness | 删除 component-only `inspect_objects` 成功路径；`source_entries` 必填，object-only inventory 显式拒绝 | 1/3 | `test_template_harness_reading_blocks.py` 新负例 |
| Harness resolver/review | `_reading_scope_by_ref()`、`_resolve_ordered_span_refs()`、coverage | Harness | resolver 只收 SourceSpan；删除 reading/unit/object fallback；内部 object mapping 合法保留 | 3 | swapped-offset、parent-expansion、duplicate/omission 负例 |
| persisted review | `semantic_review.review_uses_current_semantic_shape()` | shared Harness/App/Tool/publication gate | 删除 `source_entry_mode=False` fallback；缺 source inventory/spans 直接 false | 3/6 | `test_template_semantic_review.py` 旧 object coverage 负例 |
| Tool check/write | `DocFitToolService.check/apply()`、action package | Tool/Executor | source identity 由 task ledger 注入；公开输入不可用 target_ref/locator 覆盖 resolved span；旧包显式拒绝 | 4/6 | `test_docfit_apply_tool.py` legacy target/carrier 负例 |
| compiler | `compile_materialization_intents()` / `_scope_refs()` | Compiler | 只消费 accepted SourceSpan；删除 “compatibility reading scope” | 5 | `test_template_materialization_compiler.py` 旧 scope 负例 |
| readiness/context | `readiness.py`、`resolve_materialization_contexts()` | Readiness | source entry/resolved fragments 必填；reading/unit indexes 仅可作 UI summary，不可决定 target | 5 | missing/stale/wrong fragment fail closed |
| slot handler | `handlers/slots.py`、runtime slot adoption | Handler/Executor | 只消费 resolved fragment + derived slot_ref；locator 仅 resolver 输出；删除 paragraph/index/text fallback | 6 | handler/runtime wrong span/slot_ref tests |
| body/generated/manual/style/cleanup handlers | `handlers/**`、`runtime.py` | Handler/Executor | 每个操作绑定 ordered spans；policy/no-op 也写 receipt；不能按 block/unit/object 重选范围 | 6 | 每类 handler 的 missing/wrong span 负例 |
| candidate mapping | materialization `executor.py` / `runtime.py` | Executor | 维护 source-span -> candidate changed-range map；禁止全文搜索恢复位置 | 6 | 同段多槽、cleanup-before-fill、retry tests |
| checkpoint/resume | unit proof、post-unit inventory/review/materialization checkpoint | App/Harness | unit-boundary locator 只作前置内部边界；post-unit 必须绑定 canonical inventory；旧 proof/package 拒绝重建 | 1/3/6 | resume stale/hash/schema/legacy-scope negative matrix |
| publication | `template/artifact.py::publish_template_artifact()` | App/publication | 只发布 accepted review + receipt + actual DOCX 一致的 slots/no-op；旧 ref 或孤立 locator 拒绝 | 6 | `test_publication_style_handoff.py` provenance negative matrix |
| Fill Contract | `docfit-template-fill-contract/v2` writer/schema | Publication contract | `slot_ref` 为 identity，published locator 为 transport；不得发布 reading/object scope 或旧 v1 | 6 | contract loader/schema negative tests |
| final-fill consumer | `content/placement.py` -> `content/fill.py` / `student_content_fill.py` | final word generation | 保留 v2 `slot_ref` + content-control tag transport；拒绝 v1、缺 slot_ref、locator mismatch | 6 | `test_student_content_fill.py` reopen/stale tests |
| style consumer | `styles/capture.py` | style handoff | style identity 绑定 published slot_ref；locator 仅解析 final candidate，不能证明 source provenance | 6 | publication style handoff tests |
| template Eval/Gold | `template_extraction_eval/contracts.py`、`alignment.py`、`evaluators/slots.py` | Eval | slot identity 只按 slot_ref；locator 只评分位置/边界；旧 slot/region fallback 显式拒绝 | 6/7 | `test_alignment.py::test_ali_02...`、`test_ali_05...`、`test_ali_06...` |
| observability/report | `src/docfit/evals/template_observability.py`、build/publication report | Eval/observability | 只读取正式 output/report 路径和状态；不得从 trace/temp locator 补 source provenance | 6/7 | observability proof/design contract tests |

## Legacy-input 负向测试目标

以下是 Phase 1–7 必须落地的精确 target；已有同名测试只能证明其当前断言，不能替代尚未添加的反例：

| ID | legacy 输入 / 绕过 | 必须失败的位置与预期 | 测试目标 |
| --- | --- | --- | --- |
| P0-N01 | inspect component `source_entry_id` 提交为 canonical entry | inventory submit: `template_source_entry_inventory_invalid` | 反转 `tests/contract/test_template_source_entry_ids.py::test_public_inspection_object_carries_source_entry_and_object_alias` |
| P0-N02 | 同一 source 从 Tool window 与 App inventory 重建出不同 IDs | Tool packet construction: 禁止 normalize，缺 persisted inventory fail closed | 新增 `test_docfit_evidence_tool.py::test_unit_packet_reads_persisted_canonical_inventory_without_renormalizing` |
| P0-N03 | `source_entry_id` 随 unit/window/start_block 改变 | normalization contract: stable IDs/order | 新增 `test_template_canonical_source_entry.py::test_source_entry_ids_are_stable_across_unit_windows_and_call_order` |
| P0-N04 | trim/space collapse/newline rewrite/Unicode normalization | normalization contract: exact code points or explicit reversible map | 新增参数化 exact-text test |
| P0-N05 | blank paragraph/picture/table/shape without text silently omitted | normalization contract: typed whole-entry extent or explicit unsupported blocker | 新增 structural-extent matrix |
| P0-N06 | Agent `scope.reading_block_id` / `reading_range_id` | schema/Harness: legacy source scope rejected, no conversion | `test_template_judgment_shape.py` + Agent output schema test |
| P0-N07 | Harness `inspect_objects` / submit inventory without canonical `source_entries` | Harness: explicit legacy inventory rejection | 新增 `test_template_harness_reading_blocks.py` negative cases |
| P0-N08 | review without source entries falls back to object coverage | shared semantic review: false / fail closed | 反转 `test_current_semantic_review_accepts_current_span_mapping_shape`，保留 source-entry success case |
| P0-N09 | compiler “compatibility scope” | compiler: `materialization_legacy_source_scope_unsupported` | 反转 `test_compiler_requires_source_entry_or_compatibility_scope_not_object_ids` |
| P0-N10 | handler/runtime uses reading block, paragraph index, parent locator or text match after accepted span exists | readiness before write: unresolved-source-span blocker | 各 handler + runtime negative matrix |
| P0-N11 | resume old checkpoint/inventory/review/package lacking canonical inventory digest and spans | App: reject and rebuild from source; never auto-convert | `test_prepare_template_runtime.py` resume matrix |
| P0-N12 | publication slot locator/tag exists but source span/receipt mismatches | publication: fail before output | existing `test_o1_publish_rejects_*provenance*` plus swapped-span case |
| P0-N13 | Fill Contract v1 / missing slot_ref / slot_ref-locator mismatch | consumer/Eval loader: fail closed | placement, contracts, alignment negative tests |
| P0-N14 | Eval region/slot falls back by locator, tag, text anchor or synthetic control | Eval alignment: unmatched/ambiguous, never first-match | existing `test_ali_02` / `05` / `06` |

## 真实输入 manifest contract

Phase 8 的矩阵必须读取本节，不能从历史 temp run 反推输入。manifest 每个 case 必须固定：
`case_id`、`school_id`、source DOCX path+sha256、requirements path+sha256 或显式 `null`、Registry
path+sha256、ordered `logical_units[]`（unit_id、path、sha256），以及 `gold_in_agent_context: false`。
运行前逐文件重算 hash；任一不符即记录新 baseline，不得沿用旧 replay/E2E/product 结论。

固定公共 Registry：

```text
docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml
sha256=e139059b03883d5fbb07ebc1a35d5dffac654fad7241a61d520d7ecd4dac7ffd
```

该 hash 于 2026-09-11 Phase 1 deterministic replay 前重新计算；Registry 是继承的 workspace 修改，
其 bytes 已再次变化，因此按本节规则重基线；本切片未修改 Registry。

0820 最小输入由现有
`evals/fixtures/template-extraction/minimal-units-0820/manifest.yaml`
完整承载，manifest 当前 sha256 为
`97403592fec81a1ad99a1d0b909740d848020b65f0ee9e2caa90cf2cb2dd33f0`；Phase 8 必验子集是
`01-cover`、`03-toc`、`04-paper-body`、`06-proposal`，其 DOCX/PDF hashes 已在该 manifest 冻结，
`gold_in_agent_context=false`。

三校完整矩阵的 current-workspace baseline（这些 logical-page artifacts 当前有继承的未提交修改，
supervisor 若改变其 bytes，必须同步重算本节，不能只沿用日期或路径）：

| case | source DOCX sha256 | requirements | ordered logical units (`name=sha256`) |
| --- | --- | --- | --- |
| HUNAU | `30290bad5ff0b0843ee752ce3371da7d4ce615c4b24f2a1e8f07ab9c362760c5` | `null` | `01-cover=6c547b586f150d8076db10ce6ec0ea7c5f829ba3d8fa0d50c745abc7ec8d1aa2`; `02-integrity-statement=f5e6bc5be6165caa7e26349f036d54f7d45c7c38f712878d571c26bf7dc9d5c0`; `03-toc=d67905351dec342a2cd5ec07926e50eea1d9139385e128d7b54d02c0e8613247`; `04-paper-body=5c83e6db134dbb595ba006f895e503437e6f2acc440e67abe084b92f3f609e6a`; `05-design-task=a177fa5f0742642ed7b3194b6852df5901fd3445492644f6b61364bca9ea0c73`; `06-proposal=507fa8d6d1a53ea6e015a70a9dca8cccb0e9a4f20e937956015280a8d158e86b`; `07-proposal-record=89d5ebbea1acb145f4ee694266a154dfb50b27f9b9b03de7c43563510b645ef9`; `08-defense-record=053ac43474d537965106f0d61b3897cc9a91b76f202f4739b5a71bed37577714`; `09-topic-change-approval=f62fdd6ddc3ceeab0151c921acd4ce0b656936a309b1350fadde83af942a90da`; `10-grade-form=7f2f73d4b4535cc8e94cb338722bfa14222c245be7667aba0e3960e89af45896` |
| NJAU | `d87b1a4b17f7162590cde28f8871c210f11f3476a8ebcf3b0bd3767a4bd34b6e` | `null` | `01-cover=8b2e3b15d9d85ef81e4d1e84dae1764b6eca636c5992932b465299ce68bd8268`; `02-declarations=a2431b306ecd2e1dfdf09d67d0de5e24f073b7941d1eef309fefc55da4d3500a`; `03-toc=d379bb8f9251e71e614c1d2e8b61710abca6cbf1381c7854c60d0fee1963a80f`; `04-abstract-cn=09ef82a1d09ffbceeaee063119faaea9fa584969c04ef0c7803dce07b625e3d5`; `05-abstract-en=e17b785610eac198498cf77be5efa38b24f2d98425efddef7789a9f150e532d7`; `06-body=108b5c1930c1493532670135a92490011c0b427d59aece2b11bd70ef0804c763`; `07-references=641929f1e92f8aa6ca1714479c5a038712cfe4aa7ee562d05345dc2b55aab951`; `08-appendix=db72c42efd75e5c33b1663e6c879ca5fb85bd40c98e8c4199b4c7282ac3fe7dd`; `09-academic-achievements=7499473d6ae8263e0a70c65b4ddfa68c7ec3b729632fd5818b694090d2586a4c`; `10-acknowledgement=843374b6b131d456c151ad33372fd3a2f6b7da5fc4e0013c5f0426dd29c5a850` |
| PKU | `e27cabb7771f15526488536dc4d06251e0efcd827cad6faeb400b7a017b84375` | `null` | `01-cover=93b1956f6552d423a63e2a352b787dca88b7f25bc3315c4acfd388eef716a0a5`; `02-copyright=48c3c89df24619939160475dc2c21b80d72d1c6a1559edf14b360bf40e9e1f43`; `03-abstract-cn=e706a91da9503507e6bafaf7614a0ef4ed585148758d2e03a557731feb86d80c`; `04-abstract-en=55fe7daeec89735a51fde6382869749770ccd2c54a3d911a565cccad7855c3d3`; `05-toc=bd89fabfa63a4bcf7421ad6cfe84e45bc01358fc399845721299ad0088e47f70`; `06-list-of-figures=7ebf73e8ed285ff1487c75b381bb3286e9f353d335d5d264fb638a036729fd99`; `07-list-of-tables=9e38d8f6f31ec987c82fc2f971dd4a66c754b6e3f5e256a4e611f3b2ed8b9045`; `08-body=d86fcb99a03f25f443935d2257a5a62cc153a700b89446614512637b7b1f05d3`; `09-references=26ae4203e272a3f1687823a0795190623ee8503249c67514e83912178eef157c`; `10-appendix-achievements=a3971941f59975b7b00b8ef75ac553973be7d98da6a8e3502cfaf05793b3cc88`; `11-acknowledgement=d5e12420e0555e9d59f394f0e69bcc934918a59baaf1db906150cb6c26517904`; `12-declarations=b520e60149fb30e4032175dfb6315f12fd2229a5d439a372cf315097082947d9` |

三校 source paths 分别为
`temp/manual-gold-preparation/gold/00-inputs/schools/{hunau-undergraduate,njau-undergraduate,pku-graduate}__source-template.docx`；
logical unit root 分别为
`temp/manual-gold-preparation/gold/10-school-assets/{01-hunau-undergraduate,02-njau-undergraduate,03-pku-graduate}/logical-pages/`。

## Python LSP / tooling 证据

- `.python-version` 固定 `3.12`，`pyproject.toml` 要求 `>=3.12,<3.13`。
- `pyproject.toml` 配置 Ruff `target-version = py312` 与 strict mypy；`.venv` 当前为 Python 3.12.11、
  Ruff 0.16.1、mypy 1.20.2。
- 仓库没有 `pyrightconfig.json`、`.vscode/**`、repo-local pylsp 配置；`.venv/bin` 也没有 pyright、
  basedpyright 或 pylsp。故本轮能声明的是 Ruff/mypy 的静态 tooling 可用，不能声明 definition/reference/
  rename/hover 等 LSP 信号已配置或健康。
- 本轮无 symbol-level production edit，因此 LSP 缺失不阻断 Phase 0 文档审计；Phase 1 开始改 generator/
  callers 前，应先决定采用现有 mypy+`rg` 证据，或通过 repo-local 开发环境任务补 LSP，不能把未检查的
  editor 能力记为 refactor 证据。

## 可复现 source scans 与 allowlist

```bash
# S1: canonical ID generator definitions. ACCEPTED target: exactly one definition,
# src/docfit/template/source_entries.py::source_entry_id_for_entry.
rg -n --glob '*.py' 'def source_entry_id_for(_entry)?\(' src/docfit

# S2: normalization call sites. ACCEPTED target: one generator implementation and one
# App/Harness build call; Tool/packet/resume paths must not call it.
rg -n --glob '*.py' 'normalize_source_entries_from_objects\(|project_source_entries_onto_objects\(' src/docfit

# S3: all source-location protocol mentions across the in-scope production path.
rg -n --glob '*.py' 'source_entry_id|SourceSpan|ResolvedSourceSpan|source_entry_spans|span_ref|slot_ref|reading_block_id|reading_range_id|scope_ref|object_ref|target_ref|locator|covered_object_ids|object_text_spans' \
  src/docfit/app/prepare_template.py src/docfit/tools src/docfit/template \
  src/docfit/styles/capture.py src/docfit/content/fill.py src/docfit/content/placement.py

# S4: old business-input surfaces. ACCEPTED target: no success-path matches; allow only
# judgment/readiness denylist, explicit retired-error branches, sanitizer and negative tests.
rg -n --glob '*.py' 'compatibility reading scope|source_entry_id_or_compatibility_scope|scope\.reading_(block|range)_id|scope_ref|unit_slice|registry_field|semantic_field|target_ref' \
  src/docfit/app/prepare_template.py src/docfit/tools src/docfit/template

# S5: downstream Fill Contract / final-fill / Eval consumers. Every match must be either
# slot_ref identity, final-DOCX transport locator, explicit reject logic, or score-only evidence.
rg -n --glob '*.py' 'slot_ref|source_entry_id|span_ref|locator|tag|region_id' \
  src/docfit/content/fill.py src/docfit/content/placement.py src/docfit/app/student_content_fill.py \
  evals/template-extraction/template_extraction_eval

# S6: exact real-input hash baseline.
shasum -a 256 docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml \
  evals/fixtures/template-extraction/minimal-units-0820/manifest.yaml \
  temp/manual-gold-preparation/gold/00-inputs/schools/*__source-template.docx \
  temp/manual-gold-preparation/gold/10-school-assets/*/logical-pages/*.docx
```

S3/S5 的词本身不是错误；allowlist 按 owner 而不是仅按文件名判断：

- `source_entry_id` / SourceSpan：只允许 canonical inventory、Harness resolver、accepted review、
  materialization provenance、receipt/publication cross-check 和对应 tests。
- object ID/locator/fingerprint：只允许 inspection/resolver/executor 私有映射、unit-boundary 前置 proof、
  final-DOCX transport locator、Eval score evidence；不能成为 Agent judgment、compiler target 或 fallback。
- reading block/range/unit IDs：只允许 packet view、Agent feedback grouping 和迁移期 explicit rejection；
  不允许 success-path judgment scope、compiler scope 或 handler target。
- `slot_ref`：只允许 Harness-derived identity、DOCX tag 机械序列化、Fill Contract/final-fill/Eval 精确消费；
  不能由 locator/tag/text 反推或替代 source span。
- 旧词只允许 denylist、retired failure branch、sanitizer、历史文档和 fail-closed tests；任何新的成功路径命中
  都重新打开其责任阶段。

## 运行时必须删除或封死

| 类别 | 当前代表位置 | 目标处理 |
| --- | --- | --- |
| Agent runtime registry lookup | `src/docfit/tools/surface.py` 的 `registry_field` / `semantic_field` schema，`src/docfit/tools/service.py` 的 `focus == "registry_field"` | 从模板 runtime Agent surface 删除；字段候选只来自 pre-input vocabulary |
| Harness 旧字段 alias normalize | `src/docfit/template/harness.py` 的 `registry_field`、`bound_field_id(s)`、`registry_field_id` 提取 | 改为只接受新 ordered parts 里的规范 `field_id`，旧字段形状 fail closed |
| Registry no-candidates sentinel | `registry_field_no_candidates` 相关 Harness/Tool/test 路径 | 删除 sentinel；字段不在词表时只允许非执行语义或 `needs_input` |
| readiness / compiler 默认字段 | `src/docfit/template/materialization/readiness.py`、`compiler.py`、`toc_contract.py` 中的 `generated.toc`、`body.chapters`、`body.*` 默认语义 | 只消费 accepted Agent part 中来自输入词表的字段；不能由 TOC/body 文字补字段 |
| materializer 运行时业务 ID | `src/docfit/template/materialization/models.py`、`context.py`、`runtime.py`、handlers 中的 `intent_id` / `slot_id` | 迁移为 Harness-resolved `span_ref` / `slot_ref` 机械引用 |
| publication alias-only acceptance | `src/docfit/template/artifact.py` 和 fill-contract writer | 每个 slot 交叉验证 input vocabulary、accepted part、`span_ref` / `slot_ref`、materialization receipt |
| Skill / prompt 后置查字段指导 | `.claude/skills/docfit-school-extract/**`、`src/docfit/app/prepare_template.py` startup/system prompt | 改为只从 `field_id_vocabulary` 选择；不再建议 `semantic_field` lookup |

## 旧测试处理策略

| 测试区域 | 当前问题 | 处理方式 |
| --- | --- | --- |
| `tests/contract/test_docfit_evidence_tool.py` | 断言 `registry_field` 会按 `semantic_field` 返回候选 | 反转为模板 runtime 不暴露 semantic lookup |
| `tests/contract/test_tool_surface.py` | 断言 template semantic profile 包含 `registry_field` / `semantic_field` | 反转为只暴露 `document_map` / `unit_evidence_packet` 及输入词表 |
| `tests/contract/test_template_harness_reading_blocks.py` | 断言 Harness 接受 `registry_field`、`bound_field_id(s)` 和 sentinel | 反转为旧字段形状 fail closed；新增 ordered parts + vocabulary gate |
| `tests/contract/test_template_materialization_compiler.py` | 旧字段 alias、`intent_id`、TOC/body 默认字段仍是可接受路径 | 改为 typed-only compiler tests |
| `tests/unit/test_materialization_readiness.py` | 缺字段时要求 call `registry_field`，并硬编码 `generated.toc` / `body.chapters` | 改为 vocabulary gap / needs_input，不允许后置补字段 |

## `field_id` 字符串 allowlist

迁移完成前，源码与测试中的具体字段 ID 字符串只允许出现在以下位置：

- Field Registry snapshot 和 Registry fixture：`docs/plans/docfit-content-field-registry/*.yaml`。
- Registry parser / pre-input vocabulary builder 的 fixture 或 contract tests。
- Student content extraction / final-fill 模块的独立输入、fixture 和 projection tests；它们不定义模板提取
  runtime 字段来源。
- 迁移期 fail-closed 测试，用具体字段 ID 证明旧 runtime path 不会补造或接受字段。
- 文档中的历史问题描述，但不得作为 runtime Agent 指令、Skill 步骤或 handler 逻辑。

迁移完成后，`src/docfit/app`、`src/docfit/tools`、`src/docfit/template` 中新增 runtime `field_id`
不得来自硬编码常量或字符串匹配；必须能追溯到当前 task input Registry snapshot 生成的
`field_id_vocabulary`。

## 2026-09-11 Phase 4 Tool boundary 删除清单

| 旧入口 / 绕过 | 当前处理 | 证明 |
| --- | --- | --- |
| `semantic_field` / `query` / `registry_field` / direct `field_id` lookup | public schema 删除；service 夹带输入显式 `schema_envelope_invalid`；退役 focus/check 仅返回专用 fail-closed 结果 | `test_tool_surface.py`、`test_docfit_evidence_tool.py`、`test_docfit_check_tool.py` |
| `unit_slice` / `scope_ref` 与 source/reading ref 顶层覆盖 | template focus enum 删除；service 拒绝 `scope_ref`、`source_entry_id`、`span_ref`、`reading_block_id`、`reading_range_id`、`range_id` | `test_tool_surface.py`、`test_agent_first_tool_contract.py` |
| direct `docfit_apply operation/target_ref/object_ref/locator/paragraph` | apply schema 只保留 `batch_ref`；service 对 direct mutation/target/carrier/field 参数显式拒绝 | `test_template_tool_boundary.py::test_template_apply_rejects_legacy_direct_write_inputs_before_io` |
| raw `docx_edit` / `docx_validate` 作为模板 Agent 旁路 | raw adapters 可供内部 deterministic service/diagnostics 使用，但两个 `prepare-template` App 构建点都只挂 semantic-only evidence profile | `test_agent_first_tool_contract.py::test_prepare_template_call_paths_always_select_the_semantic_only_tool_profile` |
| runtime `FieldRegistrySnapshot.search()` | API 已删除；App/Tool/Template AST scan 禁止非正则 `.search()` 调用 | `test_agent_first_tool_contract.py::test_runtime_source_scan_has_no_registry_semantic_search_call_path` |
| Tool audit 继续承认 legacy input | audit summary 删除 source/scope/direct mutation 字段及 `judgments` alias | `test_tool_surface.py` audit negative cases |

Phase 4 只关闭公开 Tool 输入和 runtime call path。Harness action package 内部解析 raw DOCX refs 属于受控
Executor 账本；其 exact span 到实际写入/发布的 Phase 6 验收本阶段未实现或重写。

## 2026-09-03 清理状态

已关闭的模板提取 runtime 路径：

- `FieldRegistrySnapshot.search()` 与旧 alias/search helper 已删除；runtime 不能再按自然语言查字段候选。
- `docfit_evidence focus=registry_field` 只返回 `registry_field_runtime_removed` fail-closed，不读取 source
  或 Registry。
- Harness 不再接受或投影 Agent-authored `covered_object_ids`、locator/range/object refs、
  `covered_reading_spans`、`covered_unit_ids` 等旧 coverage 输入；覆盖只能从输入 reading
  block/range 和 ordered parts 投影。
- `src/docfit/template/semantic_types.py` 已删除；body/generated 字段不再来自代码字段目录。
- materialization plan/context/handler/receipt 中 runtime-generated `intent_id`、`plan_id`、`context_id`、
  `command_id`、`unsupported_id` 已迁成 `*_ref`；Agent-authored `judgment_id` / `intent_id` 仍作为
  fail-closed denylist。
- `docfit_apply`、object mutation、publication、style handoff、fill-contract 和 downstream placement
  已把发布槽位 identity 从 `slot_id` 迁为 `slot_ref`。
- `_select_host_candidate_for_accepted_semantics` 不再允许原始 DOCX 仅凭 physical publishability 走
  source-noop；source-noop 需要 Harness accepted `manual_region` / 非执行 ordered parts 语义证据。
- materialization layout 层已删除未被 runtime 使用、且硬编码 terminal 字段 ID 的测试 helper；模板 runtime
  源码中不再保留 `references.entries`、`acknowledgement.body`、`appendix.*`、`generated.toc`、
  `body.chapters`、`body.heading.*`、`body.paragraph` 作为代码字段目录或默认字段来源。
- unit-boundary 结构边界 resolver 不再把首个 unit 起点向前扩展到无可见文本、也不在 coverage 面上的
  页首空段落；它只扩展到第一个可覆盖的结构候选，避免真实 HUNAU `02-integrity-statement` /
  `05-design-task` 被空结构 locator 卡在 `invalid_unit_ranges`。
- Skill / Reference 已明确声明页语义：声明正文、作者签名和年月日骨架合在同一声明页时，应作为
  `manual_region` 终端人工区，不复用日期字段，也不把整页拆成纯 `fixed_label`。
- `docfit-school-extract` Skill tree 不再播种 canonical Registry field IDs；正文、目录、模板文字分类、
  集合/附录/致谢和 Registry 绑定 references 只描述如何从当前 `field_id_vocabulary` 中选择允许对应
  role 的字段。
- unit reading packet / Tool summary 已提供 Harness-owned whole-unit `unit_range_id` /
  `reading_ranges[].range_id`；Harness、readiness 和 materialization context 将其作为合法
  `scope.reading_range_id` 解析，同时保留 block-local `range_id`。post-unit resume inventory
  会给跨 unit reading blocks 重新分配全局顺序。
- `body_structure` handler 只允许跨过同一 accepted whole-unit judgment 中的 `cleanup` blocks，
  materialization receipt 用 Harness `span_ref` 记录 `materialize_structure` 和
  `remove_body_structure_cleanup`；handler 不创建、猜测或迁移字段 ID。
- shadow plan validator 也改为按 body member bindings 判断正文候选连续性，只允许 accepted
  `cleanup` blocks 填补 member gap；相邻但被 `style_only` / 固定轨道说明隔开的多个 body
  candidates 会在 readiness 阶段 fail closed，而不是等到 handler 无法执行后才报 postcondition。
- slot materializer 处理 range-scope judgment 时，不再对每个 block 重放整条 ordered parts；
  runtime 用 Harness `resolved_spans.part_index` 把 parts 投影到当前 reading block，并保留原始
  `semantic_part_index` 追踪 `span_ref` / `slot_ref`。cleanup-only block 在同一 accepted
  range judgment 中按 cleanup 删除，不创建字段 ID。
- ordered semantic parts shape gate 已新增 `fill_slot_includes_label_delimiter`，`fill_slot` 不能以
  冒号或全角冒号开头；标签分隔符必须留在 `fixed_label`。slot handler 同步改为按 ordered part
  对应的原始 run 样式生成固定文字和槽位 run，避免同块固定标签样式泄漏到字段槽。

当前源码扫描允许残留：

- `src/docfit/template/judgment_shape.py`、`materialization/compiler.py`、
  `materialization/readiness.py`、`src/docfit/app/prepare_template.py` 中的旧字段名只作为 denylist 或
  feedback sanitizer 出现。
- `src/docfit/tools/surface.py` / `src/docfit/tools/service.py` 的 `registry_field_runtime_removed` 是
  runtime removed error code。
- `docfit_check(registry_binding)` 旧调用只允许出现在 `src/docfit/tools/service.py` 的 retired /
  fail-closed 分支和对应 contract tests；它不再出现在公开 Tool schema 枚举中。
- `docfit_apply` 的旧 direct write 协议只允许作为 fail-closed 测试残留；公开 schema 不暴露直接
  mutation 参数，`batch_ref` 必填，service 只接受 reviewed `operations[]` action package。
- tool-call audit 不再识别旧 `payload.judgments` alias，也不再记录已移除的 direct top-level
  `field_id` / `replacement_text` 参数。
- `semantic_part_index` 只允许作为 Harness/materializer 内部 trace 或 fail-closed 测试出现；
  Agent-facing judgment / part shape validator 已禁止 Agent 输出。
- `materialization_intent` / `intent_type` direct-intent 输入只允许出现在 compiler/readiness denylist、
  内部 compiled intent 产物字段和 fail-closed 测试；独立 direct-intent helper 模块已删除。
- App accepted-review gate 不再接受仅“看起来 accepted”的手写旧 review；inventory/review 必须绑定
  当前输入 registry 派生的 `field_id_vocabulary`、正确 digest、`semantic_judgments_sha256`、
  `scope + ordered parts`、Harness `resolved_spans`、唯一 `span_ref` 和完整非重叠 inventory 覆盖。
  旧 persisted review、伪造词表、旧 `registry_field` / `materialization_intent` / Agent-authored
  coverage 形状只允许作为 fail-closed 测试残留。
- `src/docfit/content/**`、`src/docfit/app/student_content_fill.py` 中的 `body.*` 和 `context_content_ids`
  属于用户内容提取 / final word 生成模块，不定义模板提取字段来源；本计划继续 parked。
- 样式层 `word_font_fallback` / no-builtin-fallback style 文案是 Word 样式继承语义，不是字段 ID
  fallback。

仍不能标记完成：

- Phase 8 已有 0820 `01-cover` / `03-toc` / `04-paper-body` / `06-proposal` live
  product-provenance 切片，HUNAU 10/10 current-hash live provenance matrix，NJAU 10/10
  current-hash live provenance matrix，以及 PKU `03-abstract-cn` current-hash representative
  live provenance slice；整体 current-hash logical-unit coverage 为 21/32。
- 2026-09-03 当前更宽 template-boundary 合同套件通过：
  `uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
  -> `422 passed`。
- 三校代表矩阵的结构化 provenance 扫描确认 Agent 原始输出没有旧字段别名、旧 coverage 字段、
  Agent-authored `span_id` / `slot_id` / `intent_id` / `judgment_id`，且 Agent / materialization /
  fill-contract 中所有 `field_id` 均属于同一输入 `field_id_vocabulary`。
- 2026-09-03 用 0820 clean input packages 补齐 HUNAU 缺口单元：
  `02-integrity-statement` 的 `run-long600-skill-manual` 返回 `status=built`，unit-boundary
  `unit_count=1`，post-unit trace `num_turns=2`、`sdk_query_count=4`，accepted semantics 为
  5 个 judgments / 5 个 resolved spans，roles 为 `fixed_label=3`、`manual_region=2`，无
  `field_id`，fill-contract `slots=[]`；`docfit tools validate` 的 ZIP/XML reopen 和 OfficeCLI
  OpenXML 为 `ok`，但 visual review coverage 未完成。
- `05-design-task` 的 `run-long600-fixed` 返回 `status=built`，unit-boundary `unit_count=4`，
  post-unit trace `num_turns=2`、`sdk_query_count=4`，accepted semantics 为 39 个 judgments /
  39 个 resolved spans，roles 为 `fixed_label=33`、`manual_region=6`，无 `field_id`，
  fill-contract `slots=[]`；ZIP/XML reopen 为 `ok`，OfficeCLI OpenXML 是 source/final 同类
  backend warning，归类为 source-inherited 非新回归，visual review coverage 未完成。
- 两个缺口单元的 Agent / semantics / build / fill-contract 扫描无旧字段别名、旧 coverage 字段、
  Agent-authored `span_id` / `slot_id` / `intent_id` / `judgment_id`；发布均为 manual terminal
  source-noop，不创建、猜测或迁移字段 ID。
- 2026-09-03 HUNAU current-hash `02-integrity-statement` live root：
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-02-integrity-statement-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `fd937ab0-6ce6-46c4-bca7-a0e1b6fb8287`、`num_turns=2`、
  `sdk_query_count=4`、`semantic_feedback_attempts=2`。Harness accepted semantics 有 5 个
  judgments / 5 个 resolved spans，roles 为 `fixed_label=4`、`manual_region=1`，无
  `field_id`。publication `counts.manual=1`、`slot=0`，fill-contract v2、`slots=[]`；
  最终 root 旧协议扫描无命中。`docfit tools validate` 的 ZIP/XML reopen、OfficeCLI OpenXML、
  source unchanged、content preservation 和 placeholder scan 为 `ok`；visual review coverage 未完成。
- 2026-09-03 HUNAU current-hash `03-toc` live root：
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-03-toc-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `cc34150f-6723-44d8-8bf8-a5f1040acca6`、`num_turns=5`、
  `sdk_query_count=3`、`semantic_feedback_attempts=0`。Harness accepted semantics 有 28 个
  judgments / 29 个 ordered parts，roles 为 `cleanup=1`、`fixed_label=5`、
  `style_only=1`、`generated_content=22`；唯一字段 `generated.toc` 属于输入词表。
  materialization `status=ok`、`operation_count=0`、`cleanup_count=2`、`receipt_count=24`；
  publication generated-only no-fill-slot，fill-contract v2、`slots=[]`；旧协议扫描无命中。
- 2026-09-03 HUNAU current-hash `04-paper-body` live root：
  初始 root `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-04-paper-body-vocabonly`
  失败为 `body_structure_materialization_unexecutable`。root cause 是 validator 用 whole range
  context 把相邻的农理工科 / 文法经管互斥正文轨道误判成 ready。当前 validator 用 body member
  bindings + cleanup-only gap 判定正文候选连续性；合同测试
  `test_shadow_plan_blocks_adjacent_alternate_body_range_candidates` 覆盖该真实形状，且 NJAU
  `06-body` persisted semantics 仍 ready。修复后 root
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-04-paper-body-vocabonly-candidate-gate`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=7`，post-unit execution
  `status=complete`、session `b5af353c-eac8-495f-bcd1-260010ffec4f`、`num_turns=2`、
  `sdk_query_count=4`、`semantic_feedback_attempts=2`。Harness accepted semantics 有 7 个
  judgments / 86 个 ordered parts，只有 1 个 body_structure judgment，scope 为
  `body:range-whole-unit`、19 个 body parts；全部 field IDs 属于输入词表。materialization
  `status=ok`、`operation_count=15`、`cleanup_count=1`、`receipt_count=16`；
  final fill-contract 为 v2、33 个 slots，均为 Harness-resolved provenance。旧协议扫描无命中。
- 2026-09-03 HUNAU current-hash `05-design-task` live root：
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-05-design-task-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=3`，post-unit execution
  `status=complete`、session `7e42a3ff-67e5-42d2-b8d7-aa5ba227447f`、`num_turns=2`、
  `sdk_query_count=4`、`semantic_feedback_attempts=2`。Harness accepted semantics 有 3 个
  judgments / 39 个 ordered parts，roles 为 `fixed_label=23`、`fill_slot=1`、
  `manual_region=15`；唯一字段 `author.cohort_class` 属于输入词表。materialization
  `status=ok`、`operation_count=1`、`receipt_count=2`；fill-contract v2、1 个 slot，provenance
  为 Harness-resolved span。旧协议扫描无命中。`docfit tools validate` 有 source/final 同类
  OfficeCLI backend warning、content preservation warning 和 visual review coverage blocker，
  因此仍不能算 product acceptance。
- 2026-09-03 HUNAU current-hash `06-proposal` through `10-grade-form` live roots：
  HUNAU 当前 10/10 logical units 已有 built provenance。`06-proposal` root
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-06-proposal-vocabonly`
  返回 `status=built`，session `54cb6e47-df21-479a-ab54-d19077fb5608`、`num_turns=2`、
  `sdk_query_count=6`、`semantic_feedback_attempts=4`，Harness accepted semantics 为
  1 个 judgment / 19 个 ordered parts，roles 全部 `manual_region`，无 `field_id`。
  `07-proposal-record` root
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-07-proposal-record-vocabonly`
  返回 `status=built`，session `38db86e8-7f09-4655-9bae-4a1036b46c8a`、`num_turns=2`、
  `sdk_query_count=3`、`semantic_feedback_attempts=1`，Harness accepted semantics 为
  1 个 judgment / 16 个 ordered parts，roles 全部 `manual_region`，无 `field_id`。
  `08-defense-record` root
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-08-defense-record-vocabonly`
  返回 `status=built`，session `cf626c36-f848-4b94-af8d-bc6811d9eaa2`、`num_turns=2`、
  `sdk_query_count=5`、`semantic_feedback_attempts=3`，Harness accepted semantics 为
  1 个 judgment / 16 个 ordered parts，roles 全部 `manual_region`，无 `field_id`。
  `09-topic-change-approval` root
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-09-topic-change-approval-vocabonly`
  返回 `status=built`，session `4e685984-027f-49a0-b595-b4cedea77e35`、`num_turns=5`、
  `sdk_query_count=3`、`semantic_feedback_attempts=1`，Harness accepted semantics 为
  16 个 judgments / 16 个 ordered parts，roles 为 `fixed_label=13`、`manual_region=3`，
  无 `field_id`。`10-grade-form` root
  `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-10-grade-form-vocabonly`
  返回 `status=built`，session `da4fd526-7da2-4d62-83bf-a465bc657f1c`、`num_turns=2`、
  `sdk_query_count=6`、`semantic_feedback_attempts=4`，Harness accepted semantics 为
  1 个 judgment / 25 个 ordered parts，roles 全部 `manual_region`，无 `field_id`。
  五个 root 均为 manual terminal source-noop，publication `counts.manual=1`、`slot=0`，
  fill-contract v2、`slots=[]`；最终 root 旧协议扫描无命中。
- HUNAU current-hash `06-proposal` through `10-grade-form` 的 `docfit tools validate`
  对 final-template 的 ZIP/XML reopen、OfficeCLI OpenXML、source unchanged、content preservation
  和 placeholder scan 均为 `ok`；仍因 blocking `visual_review_coverage` 未完成而不能算
  product acceptance。
- 2026-09-03 NJAU `01-cover` front-matter slot live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-01-cover-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `d1d0c8b2-3fb4-4a54-a38a-95c978974bbb`、`num_turns=4`、
  `sdk_query_count=5`、`semantic_feedback_attempts=3`。Harness accepted semantics 有 10 个
  judgments / 17 个 resolved spans，roles 为 `fixed_label=10`、`fill_slot=7`；字段
  `thesis.title.zh`、`author.name.zh`、`author.student_id`、`author.department`、
  `author.major`、`advisor.name.zh`、`submission.date` 均属于输入 `field_id_vocabulary`。
  materialization `status=ok`、`operation_count=7`、`cleanup_count=0`、`receipt_count=7`；
  final fill-contract 为 v2、7 个 slots，均为 `provenance.source=harness_resolved_span`。
  最终 root 旧协议扫描无命中。
- 2026-09-03 NJAU `02-declarations` terminal manual source-noop live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-02-declarations-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=2`。Agent accepted semantics 有
  2 个 judgments / 7 个 ordered parts，roles 全部为 `manual_region`，无 `field_id`、无
  `slot_ref`；publication `counts.manual=1`、`slot=0`，final fill-contract 为 v2、`slots=[]`。
  未写 materialization candidate，旧协议扫描无命中，未创建、猜测或迁移字段 ID。
- 2026-09-03 NJAU `03-toc` generated-only live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-03-toc-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`。Agent accepted semantics 有
  27 个 judgments / 27 个 ordered parts，roles 为 `fixed_label=1`、`generated_content=25`、
  `cleanup=1`；唯一字段 `generated.toc` 属于输入词表。Harness resolved spans 有 27 个，
  其中 25 个 generated-content part 生成 `slot_ref`，但 publication 为 generated-only no-fill-slot，
  `counts.manual=1`、`slot=0`，fill-contract v2、`slots=[]`。最终 root 旧协议扫描无命中。
- 2026-09-03 NJAU `04-abstract-cn` front-matter slot live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-04-abstract-cn-vocabonly`
  返回 `status=built`；post-unit execution `status=complete`、session
  `402d5b71-3ff1-41fc-99ce-94fd3f3f3061`、`num_turns=5`、`sdk_query_count=2`、
  `semantic_feedback_attempts=0`。Harness accepted semantics 有 8 个 judgments /
  12 个 ordered parts，roles 为 `fill_slot=3`、`style_only=3`、`fixed_label=2`、
  `cleanup=4`；字段 `thesis.title.zh`、`abstract.zh`、`keywords.zh` 均属于输入词表。
  materialization `status=ok`、`operation_count=3`、`cleanup_count=5`、`receipt_count=8`；
  final fill-contract 为 v2、3 个 slots，均为 Harness-resolved provenance；旧协议扫描无命中。
- 2026-09-03 NJAU `05-abstract-en` delimiter/style fail-closed live root：
  初始 root `temp/field-id-vocab-boundary-more-live-20260903/njau-05-abstract-en-vocabonly`
  暴露 `school_style_observation_failed`；归因为 Agent 把 `KEY WORDS` 标签后的全角冒号并入
  `keywords.en` 的 `fill_slot`，使槽位 span 从固定标签样式 run 开始。当前 shape gate 和 Skill
  规则要求标签分隔符归 `fixed_label`，slot handler 使用 part-local 原始 run 样式。
  修复后 root
  `temp/field-id-vocab-boundary-more-live-20260903/njau-05-abstract-en-vocabonly-delimiter-fixed`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `fb21842f-1d93-42c5-9376-ae33403ae3e5`、`num_turns=2`、
  `sdk_query_count=3`、`semantic_feedback_attempts=1`。Harness accepted semantics 有 1 个
  whole-unit judgment / 11 个 resolved spans，roles 为 `fixed_label=4`、`fill_slot=3`、
  `cleanup=4`；字段 `thesis.title.en`、`abstract.en`、`keywords.en` 均属于输入词表，
  且 `leading_delimiter_fill_slots=[]`。`keywords.en` slot 的
  `span_ref=reading_range_id=unit-en-abstract:range-whole-unit;part_index=10`，
  `slot_ref=reading_range_id=unit-en-abstract:range-whole-unit;part_index=10;field_id=keywords.en`。
  materialization `status=ok`、`operation_count=3`、`cleanup_count=2`、`receipt_count=5`；
  final fill-contract 为 v2、3 个 slots，均为 `provenance.source=harness_resolved_span`。
  最终 root 旧协议扫描无命中。
- NJAU `01-cover` through `05-abstract-en` 的 `docfit tools validate` 对 final-template 的
  ZIP/XML reopen、OfficeCLI OpenXML、source unchanged 和 placeholder scan 均为 `ok`；
  `02-declarations` / `03-toc` content preservation 为 `ok`，slot 替换页仍有预期
  `content_preservation` warning，全部 slice 仍因 blocking `visual_review_coverage` 未完成而不能算
  product acceptance。
- Skill tree 合同测试新增
  `test_school_extract_skill_tree_does_not_seed_canonical_field_ids`；当前 `rg` 扫描确认
  `.claude/skills/docfit-school-extract` 中不再出现 `advisor.name.en`、`submission.date`、
  `generated.toc`、`body.chapters`、`body.heading.*`、`body.paragraph`、
  `references.entries`、`acknowledgement.body`、`appendix.*` 等 canonical 字段 ID 示例。
- 2026-09-03 NJAU `06-body` whole-unit body-structure live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-06-body-resume-final-unit-range-body-gap`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=3`，post-unit execution
  `status=complete`、session `5504e143-7216-48ae-a56f-ecd07cca4e63`、`num_turns=2`、
  `sdk_query_count=5`、`semantic_feedback_attempts=2`。Harness accepted semantics 有 3 个
  judgments / 39 个 resolved spans，roles 为 `body_structure=28`、`cleanup=11`，scope
  使用三个 `:range-whole-unit`；字段只包括 `body.heading.outline1`、`body.heading.outline2`、
  `body.heading.outline3`、`body.paragraph`，均属于输入 `field_id_vocabulary`。materialization
  `status=ok`、`operation_count=1`、`receipt_count=12`、`cleanup_count=11`；final
  fill-contract 为 v2、28 个 slots。最终 root 扫描无旧字段别名、旧 coverage 字段、
  Agent-authored `span_id` / `slot_id` / `intent_id` / `judgment_id`。
- NJAU `06-body` 的 `docfit tools validate` 对 final-template 的 ZIP/XML reopen、OfficeCLI
  OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有 `content_preservation` warning
  和 blocking `visual_review_coverage` issue，因此不能算 product acceptance 完成。
- 2026-09-03 NJAU `07-references` collection slot live/root replay：
  最初 root `temp/field-id-vocab-boundary-more-live-20260903/njau-07-references-vocabonly`
  暴露 `materialization_slot_ref_missing`。同一 persisted whole-unit range semantics 经当前代码
  real replay 后 materialization `status=ok`、`operation_count=1`、`cleanup_count=18`、
  `receipt_count=19`，slot operation 保留 `semantic_part_index=19` 和 Harness
  `slot_ref=reading_range_id=unit-references:range-whole-unit;part_index=19;field_id=references.entries`。
- 新 live root
  `temp/field-id-vocab-boundary-more-live-20260903/njau-07-references-vocabonly-slotref-fixed`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `bc710148-b903-40a6-bce8-97390c049217`、`num_turns=2`、
  `sdk_query_count=5`、`semantic_feedback_attempts=3`。Harness accepted semantics 有 20 个
  judgments / 20 个 resolved spans，roles 为 `fixed_label=2`、`cleanup=8`、`fill_slot=10`，
  唯一字段为输入词表中的 `references.entries`。materialization `status=ok`、
  `operation_count=10`、`cleanup_count=8`、`receipt_count=18`；final fill-contract 为 v2、
  10 个 slots。最终 root 旧协议扫描无命中，semantics/materialization/fill-contract 字段集合均是
  输入词表子集。
- NJAU `07-references` 的 `docfit tools validate` 对 final-template 的 ZIP/XML reopen、
  OfficeCLI OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有
  `content_preservation` warning 和 blocking `visual_review_coverage` issue，因此不能算
  product acceptance 完成。
- 2026-09-03 NJAU `08-appendix` appendix-title live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-08-appendix-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `5e547e31-083e-412c-b162-18e2e512b6f1`、`num_turns=5`、
  `sdk_query_count=3`、`semantic_feedback_attempts=0`。Harness accepted semantics 有
  1 个 judgment / 2 个 resolved spans，roles 为 `fill_slot=1`、`cleanup=1`；唯一字段为
  输入词表中的 `appendix.title`。materialization `status=ok`、`operation_count=1`、
  `cleanup_count=1`、`receipt_count=2`；final fill-contract 为 v2、1 个 slot，
  `provenance.source=harness_resolved_span`，`slot_ref` 和 `span_ref` 均由 Harness
  `reading_range_id` + `part_index` 生成。最终 root 的 `work` / `output` 旧协议扫描无命中，
  semantics/materialization/fill-contract 字段集合均是输入词表子集。
- NJAU `08-appendix` 的 `docfit tools validate` 对 final-template 的 ZIP/XML reopen、
  OfficeCLI OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有
  `content_preservation` warning（`missing_object_count=2`）和 blocking
  `visual_review_coverage` issue，因此不能算 product acceptance 完成。
- 2026-09-03 NJAU `09-academic-achievements` terminal source-noop live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-09-academic-achievements-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `819dd2ae-e0b9-4deb-b6e5-ca49e9582d30`、`num_turns=5`、
  `sdk_query_count=3`、`semantic_feedback_attempts=0`。Harness accepted semantics 有
  1 个 judgment / 2 个 resolved spans，roles 为 `fixed_label=1`、`cleanup=1`，无
  `field_id`，无 `slot_ref`。materialization `status=ok`、`operation_count=0`、
  `cleanup_count=1`、`receipt_count=1`；publication `counts.manual=1`、`slot=0`，
  final fill-contract 为 v2、`slots=[]`。最终 root 的 `work` / `output` 旧协议扫描无命中，
  未创建、猜测或迁移 `achievements.*` 字段 ID。
- NJAU `09-academic-achievements` 的 `docfit tools validate` 对 final-template 的 ZIP/XML reopen、
  OfficeCLI OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有
  `content_preservation` warning（`missing_object_count=1`）和 blocking
  `visual_review_coverage` issue，因此不能算 product acceptance 完成。
- 2026-09-03 NJAU `10-acknowledgement` body slot live root：
  `temp/field-id-vocab-boundary-more-live-20260903/njau-10-acknowledgement-vocabonly`
  返回 `status=built`；unit-boundary `status=ok`、`unit_count=1`，post-unit execution
  `status=complete`、session `b892cf68-5242-4eb1-a535-0702f27a9d11`、`num_turns=2`、
  `sdk_query_count=4`、`semantic_feedback_attempts=1`。Harness accepted semantics 有
  1 个 judgment / 5 个 resolved spans，roles 为 `fixed_label=1`、`cleanup=3`、
  `fill_slot=1`；唯一字段为输入词表中的 `acknowledgement.body`。materialization
  `status=ok`、`operation_count=1`、`cleanup_count=2`、`receipt_count=3`；final
  fill-contract 为 v2、1 个 slot，`provenance.source=harness_resolved_span`，`slot_ref` 和
  `span_ref` 均由 Harness `reading_range_id` + `part_index=4` 生成。最终 root 的 `work` /
  `output` 旧协议扫描无命中，semantics/materialization/fill-contract 字段集合均是输入词表子集。
- NJAU `10-acknowledgement` 的 `docfit tools validate` 对 final-template 的 ZIP/XML reopen、
  OfficeCLI OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有
  `content_preservation` warning（`missing_object_count=3`）和 blocking
  `visual_review_coverage` issue，因此不能算 product acceptance 完成。
- 2026-09-03 PKU `02-copyright` cleanup-span real replay：
  初始 root `temp/field-id-vocab-boundary-current-pku-live-20260903/pku-02-copyright-vocabonly`
  的 Agent accepted semantics 有 1 个 whole-unit judgment / 3 个 resolved spans，roles 为
  `fixed_label=2`、`cleanup=1`，没有 `field_id` 或 `slot_ref`；Host selection 停在
  `template_materialization_required`。归因为 mixed `fixed_label + cleanup` judgment 中的
  cleanup-only block span 已被 Harness resolve，但 runtime 只删除整条 judgment 全部为 cleanup
  的情况。修复后，同一 persisted accepted semantics 走
  `_select_host_candidate_for_accepted_semantics` 写出
  `work/.docfit/post-unit-materialization/candidate-0002.docx`，materialization
  `status=ok`、`operation_count=0`、`cleanup_count=1`、`publishability=ok`；cleanup receipt
  `field_ids=[]`，并保留
  `span_refs=[reading_range_id=unit-copyright-statement:range-whole-unit;part_index=2]`。
- 2026-09-03 PKU fresh live blocker：
  `pku-01-cover-vocabonly-rerun`、`pku-01-cover-vocabonly-rerun2` 和
  `pku-01-cover-vocabonly-schemafix` 均在 unit-boundary 阶段停于
  `unit_checkpoint_result_invalid`，没有 accepted unit-boundary proof；fresh
  `pku-02-copyright-vocabonly-cleanupfix` 也停于同一错误。复用原 root 已 accepted
  unit-boundary proof 运行 `pku-02-copyright-vocabonly --from unit-boundary` 时，Minimax
  SDK 连续 `api_retry` 后返回 `has_structured_output=false`，最终为
  `template_agent_result_invalid`。环境 smoke
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache DOCFIT_PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS=120 uv run docfit agent-smoke --case denied-tools`
  同样返回 `status=FAIL`、`backend=minimax`、`MiniMax-M3 timed out after 180 seconds`。
  这些不能计为 PKU fresh E2E 通过。
- 2026-09-03 本 slice 合同验证：
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_receipts.py`
  -> `41 passed`；更宽合同/回放门禁
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
  -> `423 passed`；相关 `ruff` 和 `mypy` 通过。`UNIT_BOUNDARY_OUTPUT_SCHEMA` 现在允许
  `status=needs_input` 不带 `units[]`，但 complete checkpoint 仍由 Harness feedback /
  `unit_coverage` 要求 non-empty `units[]`，不放宽通过门槛。
- 2026-09-03 runtime Registry check / internal index cleanup 合同验证：
  `docfit_check(registry_binding)` 已从公开 Tool schema enum 删除，旧调用统一返回
  `check_kind_retired`；`DOCFIT_CHECK_SCHEMA` 不再暴露 `field_id`。Agent-authored
  `semantic_part_index` 已由 ordered semantic parts validator 拒绝，只允许 runtime 内部 trace 使用。
  focused gate
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_judgment_shape.py tests/contract/test_tool_surface.py tests/contract/test_docfit_check_tool.py tests/contract/test_harness_feedback_helpfulness.py tests/unit/test_materialization_readiness.py`
  -> `61 passed`；更宽模板边界套件
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
  -> `422 passed`；相关 `ruff` / `mypy` 通过。
- 2026-09-03 `docfit_apply` package-only phase review gate 合同验证：
  post-unit 写入不再信任仅存在且非空的 `semantic-judgments.json`；review 必须有当前
  `field_id_vocabulary`、`semantic_judgments_sha256`、`scope + parts[]` 和 Harness
  `resolved_spans`。旧 `judgment_id` / `registry_field` / `covered_object_ids` 形状、重复
  `resolved_spans.part_index` 和 singular `edit_operation` action package 都 fail closed。
  `DOCFIT_APPLY_SCHEMA` 不再暴露 `field_id` / `slot_ref` / `replacement_text` /
  `style_contract_ref` / `evidence_ref` 直接 mutation 参数，并把 `batch_ref` 设为必填。
  focused gate
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py tests/contract/test_docfit_evidence_tool.py::test_t1_candidate_hash_evidence_reads_the_candidate_snapshot tests/contract/test_tool_surface.py`
  -> `34 passed`；更宽模板边界套件
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
  -> `426 passed`；相关 `ruff` / `mypy` 和 `git diff --check` 通过。
- 2026-09-03 tool-call audit alias / direct-intent helper cleanup 合同验证：
  tool-call audit 不再识别 `payload.judgments` 旧 alias，也不再记录已移除的 top-level
  `field_id` / `replacement_text` 参数；未被生产代码引用的
  `src/docfit/template/materialization/intent_classification.py` 已删除。`materialization_intent` /
  `intent_type` direct input 只剩 compiler/readiness denylist、内部 compiled intent 产物字段和
  fail-closed 测试。focused gate
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_tool_surface.py`
  -> `10 passed`；materialization fail-closed gate
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py tests/contract/test_publication_style_handoff.py::test_o1_host_candidate_selection_rejects_legacy_invalid_direct_intent_review tests/contract/test_publication_style_handoff.py::test_o1_host_candidate_selection_rejects_legacy_direct_intent_before_source_noop`
  -> `34 passed`；更宽模板边界套件
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
  -> `428 passed`；相关 `ruff` / `mypy` 和 `git diff --check` 通过。
- 2026-09-03 App accepted-review current-shape gate 合同验证：
  `_accepted_harness_semantics` 和 `_post_unit_checkpoint_report` 现在共享同一 current-shape gate：
  accepted review 必须与当前输入 `template_sha256`、当前 Registry pre-input vocabulary、digest、
  `semantic_judgments_sha256`、ordered parts、Harness `span_ref` / `slot_ref` 和 inventory 覆盖闭合。
  旧 persisted review 不能解锁 source-noop、post-unit checkpoint、materialization candidate 或
  publication host candidate。Synthetic Agent fixture 已改为只输出 `scope + parts`；Harness fixture
  才能写 `resolved_spans`。focused gate
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_publication_style_handoff.py`
  -> `53 passed`；fixture replay gate
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2/test_agent_first_prepare_template.py::test_clean_source_may_be_selected_without_forcing_docx_edit`
  -> `12 passed`；更宽模板边界套件
  `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
  -> `428 passed`；相关 `ruff` / `mypy` 和 `git diff --check` 通过。
- 仍不能标记整个计划完成：三校所有 logical units 的完整 live Agent/product acceptance 矩阵尚未完成；
  本机 `docfit doctor --require visual-renderer` 返回 `libreoffice_visual_renderer=NOT_READY`，
  完整全页视觉 review 尚未完成。
