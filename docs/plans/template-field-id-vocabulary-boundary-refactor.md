---
plan_scope: template-field-id-vocabulary-boundary
refactor_scope: template-field-id-vocabulary-boundary-cleanup
status: ACCEPTED
created: 2026-09-02
compatibility_policy: no_old_logic_compatibility
accepted_severities:
  - P0
  - P1
  - P2
historical_last_verified: "2026-09-04 logic/contract + source-noop semantic gate + vocabulary-only Skill tree + cover/toc/proposal/body live slices + HUNAU/NJAU/PKU representative live provenance matrix + HUNAU 10/10 current-hash live provenance + NJAU 10/10 current-hash live provenance + PKU 1/12 current-hash live provenance + PKU copyright cleanup-span real replay + registry_binding retired + semantic_part_index fail-closed + apply package-only phase-review gate + tool-audit alias removal + direct-intent helper removal + App accepted-review current-shape gate + Tool apply inventory/vocabulary/provenance gate + retired completion_payload schema alias removed + semantic_part_index input fallback removed + compiler/materializer vocabulary provenance gate + publication materialization receipt provenance gate + registry-unknown compiler code retired + unit_evidence_packet Agent-visible projection gate + legacy scope_ref checkpoint fail-closed + eval/gold retired field alias migration fail-closed + eval slot locator fallback removed + materialization slot_ref/span_ref provenance gate + direct docx_edit post-unit review/registry gate + slot handler/runtime slot_ref derivation gate + eval fill-contract v1 main loader fail-closed + content projection v1/style_id fail-closed + eval slot_id identity retired + synthetic Eval fixtures rebuilt to v2 slot_ref + formal/candidate Gold fail-closed + full Eval suite green + Agent-authored resolved_spans retired + resolved span current-shape gates + compiler/readiness part legacy fields fail-closed + body_structure container field unpublished + semantic_part_index output retired + docfit_apply stale target/carrier fallback fail-closed + eval region locator fallback removed + eval slot synthetic control fallback removed + Harness status resolved_spans coverage fallback removed + Harness object_text_spans span precision gate + Harness exact ordered part gap gate + object_text_spans Agent denylist/sanitizer + HUNAU/NJAU/PKU current-code inventory real replay + materializer paragraph-index fallback removed + slot execution closure gate + no-slot publication semantic provenance gate + body_structure section control publication fail-closed + direct docfit_apply body_structure parent slot_ref retired + unit-boundary checkpoint unit alias fallback retired + slot handler field-prefix layout inference retired + semantic coverage feedback object-action sanitizer + Harness whitespace separator span gate + PKU 04 abstract-en real replay publication slice + scoped_closure / coverage_closure object-id coverage protocol retired + observability proof current post-unit contract gate + superseded quality-gate tombstone current-doc gate + post-unit materialization tombstone and template_gate docx_edit reversal + full-tool agent school Skill decoupled + remove_hint fallback and registry_field test branch removed + PKU 04 abstract-en provenance validation refreshed + three-school inspect packet matrix + unit_coverage resolved_units fallback removed + post-unit write package explicit Registry gate + unit_evidence_packet requires input vocabulary + docfit_apply field writes require phase review + Harness inventory requires input vocabulary + unit-boundary and reading packet unit_id fallback removed + public field_not_registered surface retired + stale tool-surface compatibility names retired + unit_evidence_packet checkpoint unit aliases fail-closed + post-unit prompt resolved_units context + App/Tool/Publication accepted-review source-hash and object_text_spans span coverage gates + current module doc accepted_units guidance retired + shared accepted semantic-review gate helper + accepted-review object_text_spans fail-closed coverage gate + Harness inventory object_text_spans-required submit gate + Harness object_text_spans complete-text submit gate + Harness covered-object object_text_spans closure submit gate + docfit_apply outer operation surface retired + docfit_apply package-only target_ref surface retired + publication/style stale legacy wording retired + Tool runtime source_hash input retired + registry_binding feedback rebrand retired + object mutation migrated_boundaries key retired + App unit-boundary check source_hash input retired + unit_slice/scope_ref Tool input retired + App feedback legacy focus/code translators retired + materialization field-binding single source + cleanup/style legacy obligation validators retired + Harness-reviewed wording cleanup"
acceptance_requires:
  - logic_contract
  - real_replay
  - e2e_agent_loop
  - artifact_identity_verification
updated: 2026-09-22
current_scope: full-flow-source-object-identity
historical_phase_0_status: ACCEPTED
historical_phase_1_status: ACCEPTED
historical_phase_2_status: ACCEPTED
historical_phase_3_status: ACCEPTED
historical_phase_4_status: ACCEPTED
historical_phase_5_status: ACCEPTED
historical_phase_6_status: ACCEPTED
historical_phase_7_status: ACCEPTED
historical_phase_8_status: REOPEN
field_id_closure_status: HISTORICAL_POST_UNIT_ONLY
full_flow_object_identity_status: ACCEPTED
field_id_closure_audited: 2026-09-22
---

# 模板字段与源定位闭环完整重构计划

## Status

ACCEPTED — 2026-09-22 全流程对象身份专项工程验收已收口；不是学校语义和版式产品签收。
首次分区已统一原 ID；真实 Agent 写入/保留、发布/恢复已取证。7 项剩余失败/历史记录复核未发现
新增身份缺陷；同一对象跨区后的实际写入与重试证据已补齐（分区切点由测试构造，非新 Agent E2E）。
下文 Phase 0–8 状态和矩阵保留为历史；本次唯一当前验收门是本节三步门，不沿用旧阶段签收。

## 2026-09-22 全流程对象身份合同（用户已授权范围）

目标：第一次选择的源对象及范围，到最终实际 Word 修改仍是同一来源。
ID 在此指文档源对象 `source_entry_id`；Registry `field_id` 表示填写责任，`unit_id` 仅表示分组。
只做身份闭环；学校语义识别率、样式和版式的全面产品验收不属于本次目标。

架构图：原始 DOCX 不可变快照 → 完整 canonical source inventory → 功能区语义边界 →
Harness 已解析源范围 → 同清单的 unit reading packets → semantic parts → accepted spans →
Word fragments → 写入回执 → 发布/恢复来源核对。

责任与唯一合同：

1. App 在第一次 Agent query 前从完整输入建立并持久化唯一清单，绑定输入 SHA 和清单摘要。
   分页、局部读取、分组、重试和恢复只能投影或重读清单；不能据此重新生成对象身份。
2. Agent 读取可读内容、布局线索及已有 `source_entry_id`，边界必须引用清单里的对象。
   边界点统一表达为对象开始、对象结束或对象内切分。对象内切分提供精确的前后原文，
   两段拼接必须等于原对象全文；Harness 计算 offset，Agent 不算 offset/hash/Word locator。
   区间采用起点包含、终点不包含；空文本结构对象只允许对象开始/结束。
3. Harness 校验对象存在、快照一致、单元有序且非空、完整覆盖、无重叠/缺口，并通过共享 span
   resolver 落到 Word。任何额外独立定位字段、错对象、错范围、错版本都拒绝。
4. 同一个源对象可以跨功能区，但不改 ID、不复制成新对象。unit 范围只表示该对象的子区间。
   后续判断仍按源对象给出完整 ordered parts；分批时一个对象只由一个 batch 负责，
   输入必须保留涉及的全部分区语义上下文，且 parts 不得跨越已接受的分区切点。
5. Tool 页面、全文、局部读取都来自同一清单的视图；底层 inspect/locator 只作执行账本。
   恢复必须具备当前合同版本及初始 inventory 绑定。旧 proof/旧 ledger 明确拒绝，不自动升级。
6. 发布来源链包括初始清单、已接受功能区范围、语义范围和实际 Word 修改结果。
   现有后半段 resolver、materializer、receipt 验证尽量复用，不能另选 paragraph/target_ref。

删除清单与归属：

| 入口 | 归属及切换要求 |
| --- | --- |
| `prepare_template_task` / 首次 query | App 建立初始 inventory 和读包；输入准备失败时不能启动语义判断 |
| `UNIT_BOUNDARY_OUTPUT_SCHEMA` / prompt / Skill Reference | 只接受已有源对象边界；撤销页码+seen_text 的独立定位合同 |
| `docfit_check(unit_coverage)` / structural、visual resolver | 统一 ID 范围解析；删除 locator直传、全篇文本搜索、first/last match 成功路径 |
| `_post_unit_inventory_from_checkpoint` / `unit_evidence_packet` | 只投影初始清单及 accepted unit spans；删除 checkpoint 后重新生成身份 |
| semantic batch / source span review | 共享对象跨组保持同一 ID；负责批次唯一，范围/上下文完整 |
| checkpoint load/validate、resume、trace | 缺初始清单绑定或旧协议直接拒绝；不复用旧分区作为新从头证据 |
| materialize / publish / artifact consumers | 绑定初始清单、分区与同一 accepted span；保留错目标/错范围拒绝 |
| tests / 当前文档 | 正常路径迁至唯一合同；旧输入只能用于拒绝或明确历史诊断 |

工程评审：这是 App/Schema/Harness/Tool/Skill 的同一跨层合同切换，缺一层便会留下另一套
选择对象的成功路径，所以必须同批接通。拒绝双读、fallback、自动转换、按 unit 重新编号、
从文字全篇搜索定位，以及仅重命名字段而保留旧行为。允许中间开发状态暂时不可运行。
代码侦察已定位上述入口，不另启宽泛架构扫描。P0/P1/P2 仅限此身份合同；范围外问题保留记录。

### 当前三步验收门

| 步骤 | 状态 | 交付与验收 |
| --- | --- | --- |
| 1 冻结合同和删除清单 | ACCEPTED | 本节记录用户已明确的范围、身份生命周期、对象内边界、入口及拒绝规则 |
| 2 完成统一切换 | IMPLEMENTED `9ad1d87` | 首次分区到发布/恢复统一；旧入口删除；专项 contract 与静态检查通过，完整回归中的基线失败和计时抖动见专项记录 |
| 3 验证并收口 | ACCEPTED | 三校清单/映射、声明页保留、NJAU 原 Agent 写入及重放/恢复通过；剩余失败身份审计无新增缺陷；跨区同 ID 的两侧实际写入、重试及未选中内容保护已补核 |

验证阶梯：

- logic/contract：分页/分批/重试 ID 不变，分区不重造 ID，对象内切点精确；重复文本不可偷换对象；
  旧定位、独立 target、错源版本、offset 交换后重算摘要、缺口/重叠全部拒绝。
- real replay：真实输入+此次新合同的真实判断，从初始 inventory 核对 unit span、semantic span、
  Word fragment、实际修改范围；旧 proof 不自动转换成新成功记录。
- E2E agent loop：公开 `uv run docfit prepare-template --school-template <原始输入> --output <新目录>`
  从第一步跑；证明 Agent 用已有对象分区，并消费反馈修订，后续写入仍指向同一源范围。
- 产物身份核验：重新打开 Word 核对选中内容与未选中内容，发布和恢复保持初始来源。
  不做学校语义或版式全面产品签收。

停止条件：以上三步的身份不变量达到实际证据要求才收口；外部凭证/运行环境不可用则明确缺失
层级，不能以单测替代真实输入。样本失败先核是否换对象、错接范围或丢原身份；候选原文错误被
拒、同对象操作不支持、模型无输出和历史快照缺失，分别保留而不自动计为运行时 ID 缺陷。
不再要求 PKU 修订成功或另一个正文样本发布成功。此前 30/32 replay 仅为后半段历史证据；
NJAU03 执行冲突和 NJAU07 原始快照缺失不计入新成功矩阵。

收口证据见[专项记录](../status/active/template-full-flow-object-identity-20260922.md)。
同一真实对象的两个原填写范围 `[5:22]`、`[24:39]` 在测试构造的两分区中保持同 ID；原 Agent
判断未改，经正式 Harness 接受后，两次实际写入与原发布包一致。原表格槽、局部清理、48 个
未选中段落和 38 个包部件独立核验通过。跨区切点不是 Agent 自主产生，不能称该场景 E2E 通过；
页眉 fresh 写入、历史缺快照样本和学校全面产品质量仍有各自验证限制，不扩大本身份任务。

执行分工：主会话维护唯一计划、当前文档、集成审查与真实验证；skill-runner worker 负责
运行时、Agent Skill/Reference 与自动测试的连贯切换。用户已授权本节任务和真实 Agent 验证，
不引入新的产品验收或额外批准环节。

## 历史计划背景：对最终产品和唯一定位体系负责

以下为本次收紧验收范围前的历史 Phase 0–8 记录。学校语义正确、所有样本生成成功和人工产品
签收要求不反向扩大上面的当前对象身份三步门；本次 ACCEPTED 也不代签历史产品验收。

本计划的总目标是：从学校模板识别出的填写责任，经输入字段词表、Agent 语义判断、Harness 校验、
Tool 执行和发布，形成字段正确、范围准确、可追溯且可用的 Word 模板。整个链路只有一套源定位事实：

```text
填写槽 / 其他处理结果
  → accepted span（准确的源范围）
  → source_entry_id（输入归一化生成的源内容单元）
  → 底层 Word 内容及位置
  → 本次候选中的实际变更

field_id 只来自 Agent 判断前的输入词表，不承担源定位职责。
```

实施 Agent 对这个总目标负责，不只是对分配到的文件、阶段清单或测试通过负责。
**完成一个阶段只是建立总目标的一部分；只有证明该部分方向正确、足够完整且不会迫使后续阶段绕行，
才能接受为阶段完成。** 不得用阶段数量、代码量、通过测试数、引用命名或单个成功样例代替这一判断。

目标的硬约束：

- Tool 和 Harness 使用同一份 canonical source inventory 和同一个精确 span resolver。
- span 必须依附 source_entry_id，准确绑定内容与范围，能解析到实际 Word 内容；字符串包含源 ID 不算闭合。
- 所有模板业务写入从 accepted spans 推导目标，不能另选 target_ref、paragraph 或对象集合覆盖该结果。
- object ID、locator、fingerprint 可以保留为内部映射；不得成为绕过源单元与 span 的另一套主定位路径。
- 零过渡兼容：不保留旧 scope 输入、双读、fallback、自动旧转新或失败时退回旧定位。
- Agent 只判断学校语义；hash、offset 解析、候选位置变化、恢复和发布账本由确定性代码承担。
- “成功发布”“架构定位统一”“学校语义正确”“产品可用”分别取证，不能相互代替。

### 阶段完成前必须执行的总目标审查

实施者在阶段开始时说明该阶段对总目标的贡献，在阶段结束时根据实际 diff、调用路径和证据重新审查。
不是复述本节，而是逐项回答下表；每项必须有具体对象和可核验依据。

| 审查问题 | 必须提供的依据 | 不通过时如何处理 |
| --- | --- | --- |
| 本阶段让总目标的哪项要求成立？ | 总目标条款 → 实现入口 → 验收案例 → 证据路径 | 不能只报“阶段任务已做”；补齐贡献或调整实现 |
| 当前实现是否仍沿唯一定位方向？ | 实际调用路径；新路径与旧路径的进入条件 | 存在双主路径或后置猜定位，撤回完成结论 |
| 当前阶段的职责是否做足？ | 边界、错误输入、真实数据与下游消费验证 | 缺口属于本阶段则本阶段关闭，不留给最后总验收 |
| 交给下一阶段的产物能直接使用吗？ | 下一消费者按正式合同读取/执行的证据；尚未实现时至少做消费合同验证并明确验证层级 | 需要额外适配、补造字段或重新猜范围则不通过 |
| 旧路径是否真正退出？ | 删除 diff、可达性检查、旧输入拒绝案例 | 仅增加新实现不算替代完成 |
| 什么反例能推翻当前完成结论？ | 错范围、错目标、旧协议等负向案例，以及独立 Word 内容检查 | 反例仍成功则重新打开责任阶段 |
| 是否把已知阻断风险推给后续？ | 遗留事项、责任阶段、对总目标的影响、处理方式 | 会导致下游补丁或最终目标不可达的事项不得标成普通 TODO |

只有全部适用项通过，才能标记阶段 ACCEPTED。任何未知的跨层正确性风险应标 REOPEN/未验证，
不能因当前测试通过就判定安全。后续发现推翻早期阶段的反例，立即重新打开责任阶段，修复根因；
禁止为了维护既有完成状态而缩小目标、放宽门禁或修改正确的验收预期。

“做到足够优化”指消除本阶段已知的正确性、边界和可维护性障碍，形成可直接消费的单一合同；
不是追求无限重构。只有影响总目标、当前阶段合同或下一阶段可消费性的工作才纳入本轮。
无关性能、美观和其他模块扩展记录后置，不得借总目标审查扩大任务。
不能保证实施后永不发现新问题；必须保证已知问题不被掩盖、证据不足不被宣称完成。

### 唯一计划与当前状态

本文件是此任务唯一活跃实施计划，沿用原 Phase 0–8 编号。
`template-source-location-unification.md` 的目标、范围合同和验收要点已合并到本文件；其独立阶段编号停止使用。
本轮实现与验证已推进到 32/32 E2E/publication 矩阵；旧证据仍只按其原证明范围保留，不能拼接成
不存在的单次通过结果。

| 原阶段 | 当前状态判断 | 本轮处置 |
| --- | --- | --- |
| Phase 0 | ACCEPTED（2026-09-11，`logic/contract` 文档审计） | 入口、owner、处置、反例、manifest 和冻结合同已闭合；实现 residual 进入 Phase 1–6 |
| Phase 1 | ACCEPTED（2026-09-11，`logic/contract` + deterministic `real replay`） | 单一 inventory build/persist/project 路径、exact text、typed structural extent 与快照绑定已闭合 |
| Phase 2 | ACCEPTED（2026-09-11，`logic/contract` + real `E2E agent loop`） | 唯一 Agent 合同及真实 feedback → revision → accepted 已闭合 |
| Phase 3 | ACCEPTED（2026-09-11，`logic/contract` + hash-bound `real replay`） | 共享 exact typed SourceSpan resolver、Harness closure 与重读/恢复/下一消费者一致性已闭合 |
| Phase 4 | ACCEPTED（2026-09-11，`logic/contract` + call-path/source audit） | Agent runtime 字段搜索与直接 Tool target/source override 已退出 |
| Phase 5 | ACCEPTED（2026-09-11，`logic/contract` + hash-bound `real replay`） | compiler/readiness/context 只消费 current accepted review、输入词表和 exact resolved spans |
| Phase 6 | ACCEPTED（2026-09-11，`logic/contract` + actual DOCX/publication/consumer `real replay`） | typed span-only 执行、原子发布、持久化 provenance、恢复与消费者拒旧已闭合 |
| Phase 7 | ACCEPTED（2026-09-12，`logic/contract` 文档与 reachability 审计） | 默认长期文档、ADR、旧输入拒绝和内部 source-entry scope 已闭合 |
| Phase 8 | current-digest E2E/publication 矩阵 32/32；fixed-render 32/32、section 回归、锁定 OfficeCLI 与 Microsoft Word 实机复核均已闭合；human acceptance 未完成 | REOPEN：等待人工产品签收 |

已有反例：真实姓名槽记录中交换姓名与标签的 offsets、重算摘要后，shared review 仍接受；
物化未拒绝错误范围；Tool 对同槽的所属段落与实际 run 都可通过对象集合检查。
Phase 0–7 已按各自证据层级 ACCEPTED；Phase 8 的代码、真实 Agent、实际发布矩阵、32/32
fixed-render coverage、锁定 OfficeCLI 与 Microsoft Word 实机复核已闭合。LibreOffice 近似渲染差异
已由真实 Word 复核定性为 non-blocking；剩余 human product acceptance 不能由 coding agent 代签。

## 范围与唯一合同


覆盖模板提取的 input normalization、reading packet、Agent output schema、Harness review、
Tool evidence/check/write、compiler/readiness、所有 materialization handler、checkpoint/resume、
publication、Fill Contract 及读取这一模板交接协议的 validator/Eval/下游消费者。

不扩展到学生内容提取的领域模型重构、学校语义算法重写或独立 UI 设计。共享底层 Word 操作仍可使用
object ID、locator、fingerprint；它们是 resolver/executor 的私有材料，不是模板业务的另一套输入协议。
下游消费模板产物的代码必须同步新协议，不能以“其他模块”为由保留旧模板定位读取路径。

责任边界：Agent 只判断学校语义和拆分有序 parts；输入层生成源单元；共享 resolver 解析范围；
Harness 检查闭合；Executor/Tool 维护候选与物化；App 发布；Test/Eval 验证。禁止代码通过学校 wording、
字段名称或模型 reason 猜定位和语义。不让 Agent 管 offsets、hash、checkpoint、执行目标和发布账本。


### 精确源定位合同


### 源单元与文本基准

- 在绑定不可变源 DOCX 快照的归一化阶段，一次生成规范源单元及精确 provenance。
- reading packet、分页、unit slice 只能投影/选择这份源单元，不能重新归一化并产生另一组 ID。
- 同一快照、同一源内容在不同调用顺序、窗口和重试中保持同一 ID；新快照不能沿用旧映射。
- 文本范围采用 Python Unicode code point 的半开区间 `[start, end)`，不是 UTF-16 单元或字节偏移。
  不在校验时任意 trim、压缩空格、改换行或做 Unicode 归一化。若输入投影执行这些转换，必须一次性
  定义且保存可逆到原始 Word 内容的映射；歧义不能用首个文本匹配消解。
- 非文本对象/空白结构采用源单元内明确的 typed structural extent；不能靠空 text 或假 offsets 绕过覆盖。
  Phase 0 冻结该类型的语义，Phase 1 验证其映射。每个 extent 仍必须依附一个 source_entry_id。

### 精确 span 与派生引用

逻辑形态为 `SourceSpan(source_entry_id, extent)`；源快照由所引用的 source inventory 固定。
文字 extent 为 start/end，结构 extent 为规范源单元内的明确结构范围。
跨单元动作表示为有序 SourceSpan 集合，不引入可独立定位的 range ID；每个成员单独可解析。

`span_ref` 是上述事实的派生引用。其登记/生成至少绑定源快照、source_entry_id、extent 类型和完整范围；
不能只由 part_index 命名。相同范围重试稳定、不同范围或快照不可混用。字符串不可替代解析与内容验证。
`slot_ref` 引用 accepted span 和输入词表字段，不拥有独立的源定位权。

共享 resolver 输入源 inventory 与 SourceSpan，返回 typed resolved span：规范范围、预期源内容、
有序 Word fragments 及其局部范围、源快照身份。覆盖检查、Tool execution、receipt 和发布复核消费它。
内部 Word fragments 可含 object/locator，但不能由调用方重新选择目标，也不能以所属父对象替代子范围。

### 写入与候选变化

源位置保持绑定输入快照；候选变化由 Executor 维护明确的 source-span → candidate 映射。
所有变更先解析与检查，再在隔离候选上执行；同段多槽、清理导致偏移变化、跨 run 范围必须保持同一解释。
结果重新打开后，按已登记映射核对实际变化区间和未触及内容。不能全文搜索同名文本“找回”位置。
失败不得部分发布；需要新语义判断时回到 Harness 阶段反馈，不让 Agent 重建内部映射。


## 分阶段实施与验收（唯一有效的 Phase 0–8）

每阶段遵守开篇的总目标审查。阶段验收包含正向能力成立、对应旧路径退出和下一阶段可消费，
不能将旧路径删除统一延期到 Phase 7。开发允许尚不可用于产品的中间提交，不允许用双协议维持中间版本运行。

### Phase 0：冻结总合同、影响面与反例

目标：明确字段来源与唯一源定位的所有入口和职责，确保没有遗漏的第二执行路径。
交付：SourceEntry/SourceSpan/ResolvedSourceSpan/ExecutionReceipt 合同；入口与调用图；逐项删除清单；
真实输入 manifest（DOCX/要求/Registry/hash/单元列表）；当前错误反例及预期拒绝结果。

验收：覆盖 input、inspection、packet、schema、Harness、Tool 全部模板读写、compiler/readiness、
所有 handler、恢复、发布、Fill Contract 和实际消费者/Eval。冻结字符/结构/跨单元/候选变化语义；
无未归属入口与影响后续实现的未决合同。旧输入处理唯一方案是显式拒绝并重新生成。
层级：设计审查 + logic/contract 基线；通过才实施 runtime。

#### Phase 0 验收记录（2026-09-11）

结论：**ACCEPTED**，证据层级仅为 `logic/contract` 文档/源码审计。

- 总目标贡献：把 canonical inventory、SourceEntry、SourceSpan、ResolvedSourceSpan、ExecutionReceipt、
  candidate mapping 和 Fill Contract transport locator 的边界冻结为单一合同；字符范围固定为 exact Python
  Unicode code-point 半开区间，空白不隐式 normalize，无文本结构使用 typed whole-entry extent，跨 entry
  行为使用 ordered spans。
- 完整影响面与调用图：
  `docs/plans/template-field-id-vocabulary-boundary-migration-inventory.md` 逐行覆盖 input isolation、raw
  inspection、normalization、App inventory、Tool packet、Agent schema、Harness inventory/review、Tool
  check/write、compiler/readiness、全部 handler 类别、candidate mapping、checkpoint/resume、publication、
  Fill Contract、style/final-fill consumer 和 template Eval/Gold。每行都有 owner、删除或显式拒绝处置、
  责任 Phase 和下游/负向证据；没有保留“以后决定”的 compatibility 选择。
- 当前树确认的四项实现 residual 已有归属：inspect component 与 canonical content-unit 双 ID generator
  归 Phase 1；App/Tool 两次 normalization 归 Phase 1/4；reading scope/object-only compatibility success paths
  归 Phase 2/3/5/6；whitespace normalization 与空结构遗漏归 Phase 1。这些是后续实施清单，不是 Phase 0
  未决合同。
- 旧输入统一处置：旧 checkpoint、inventory、reading-scope judgment、action package 和 Fill Contract
  缺新绑定时一律 fail closed 并从当前 source 重建；不提供 alias、fallback、双读或 old-to-new normalizer。
  inventory 中 P0-N01 至 P0-N14 是精确 negative-test targets。
- 真实输入 manifest：inventory 冻结 0820 manifest 与 HUNAU/NJAU/PKU 三校 32 个 logical-page DOCX 的
  当前 paths、sha256、ordered unit list、Registry hash、requirements nullable 语义和
  `gold_in_agent_context=false`；dirty artifact bytes 改变时必须重新基线，不能继承旧运行结论。
- 下游直接消费证据：当前源码确认 publication 写 Fill Contract v2，final-fill placement 要求 v2
  `slot_ref` + content-control transport locator，Eval slot alignment 以 `slot_ref` 对齐且已有 locator/text
  fallback 负例。Phase 6 仍须实现并重跑这些 gates，Phase 0 只证明责任和验收入口已指定。
- LSP/tooling：repo 固定 Python 3.12、Ruff py312 和 strict mypy；当前 `.venv` 有 Python 3.12.11、
  Ruff 0.16.1、mypy 1.20.2，但没有 repo-local pyright/basedpyright/pylsp 或 editor LSP config。因此本次只把
  Ruff/mypy 视为可用静态 tooling，不宣称 definition/reference/rename/hover LSP 健康。
- Reopen trigger：source scans 出现 inventory 未列出的成功入口；实现证明 exact-text/typed-extent 合同不可执行；
  或任一 consumer 必须保留独立源定位协议。否则 Phase 0 保持 ACCEPTED，下一执行阶段是 Phase 1。
- 未验证：本轮没有运行 production behavior tests、真实 replay、E2E agent loop 或 product acceptance，
  也不能从历史 implementation log 继承这些层级为本轮 source-location 合同验收。

### Phase 1：输入词表与唯一源单元

目标：保留字段前置词表成果，让 Tool/Harness 消费同一规范源 inventory。
交付：唯一 normalization、精确 Word provenance、只投影不重新生成源 ID 的 reading packet。

验收：词表在判断前进入 Agent；同源快照跨窗口/分页/调用顺序/重试的 ID、文本、映射一致。
覆盖中文、emoji、组合字符、空白、换行、跨 run、表格、SDT、空段及非文本结构。
缺 provenance、矛盾映射、旧快照明确拒绝；不支持对象显式阻断，不能静默漏掉。
删除重复生成与缺失映射补造路径。真实学校 inspect/normalize 证明需要处理的内容没有遗漏。
层级：logic/contract + real replay。

#### Phase 1 验收记录（2026-09-11）

结论：**ACCEPTED**。证据层级为 `logic/contract` 与 deterministic `real replay`；没有运行
`E2E agent loop` 或 `product acceptance`。

- 总目标贡献：输入隔离后的当前 source snapshot 现在先生成一个 `CanonicalSourceInventory`，再按已接受
  units 投影 reading packets；App、Harness 与 Tool 共享持久化 inventory，不再各自归一化或生成 ID。
- 实际入口：`prepare_template._ensure_post_unit_inventory()` 在 post-unit Agent 启动前调用
  `build_canonical_source_inventory()` 一次；Harness 同时持久化 `source-inventory.json` 和带 unit projections
  的 `object-inventory.json`；`DocFitToolService.evidence(unit_evidence_packet)` 只读取、校验并分页该投影。
- 删除：移除 inspection component 的 `source_entry_id` generator、公开 alias/ref 与 payload 字段；移除
  `normalize_source_entries_from_objects()` 以及 Tool/App 的重复 normalization 调用。生产源码仅保留
  `source_entries.py::source_entry_id_for_entry()` 一个 source-entry ID generator，canonical inventory builder
  仅有一个 App 调用点。
- P0-N01–N05：旧 inspect component credential 提交被拒绝；缺失、source-stale、unit-projection-stale
  inventory fail closed；同一快照跨 unit/window/order/serialization retry 保持 ID、文本、provenance 稳定；
  Unicode code points、组合字符、emoji、NBSP、tab、CRLF/newline 与首尾空白原样保存；paragraph、table、
  picture、shape、SDT、fieldChar、instrText、tab、break 使用 text extent 或 typed `whole_entry`，未知
  `text_box` 显式报 unsupported。
- Agent 边界：typed extent 和 Word provenance 保留在 persisted inventory/unit projection 供 Harness/Tool
  校验；`agent_visible_unit_reading_packet()` 与 Tool evidence 只暴露 source entry ID、原文、类型、顺序和
  语义线索，不把 offsets/extent 交给 Agent 管理。
- 下游消费证据：HUNAU/NJAU/PKU 共 32 个当前 hash-bound logical-page DOCX 通过真实 inspect 后，逆序/正序
  projection 与 serialization retry 的 ID/text/provenance 完全一致；三校各一个代表页进一步证明 App 只构建
  一次、Harness 持久化同一 inventory、Tool 两次读取产生相同 packet，且 Tool 未调用 inspect。
- 可复现验证：聚焦 contract 最终 `143 passed`（含 Agent-visible extent 隔离回归）；Phase 1 manifest-bound replay `36 passed`（1 manifest + 32
  logical pages + 3 App/Harness/Tool representatives）；完整 materialization replay 文件曾通过 `50 passed`；
  随后的 missing-provenance fail-closed 收紧已再跑上述 `133 + 36` 相关矩阵。Ruff、strict mypy、source
  scans 与 `git diff --check` 最终通过。
- 当前 Registry bytes 在本次 replay 前按 manifest 规则重算为
  `e139059b03883d5fbb07ebc1a35d5dffac654fad7241a61d520d7ecd4dac7ffd`；该文件是继承的 workspace 修改，
  本阶段未编辑它，也没有沿用 Phase 0 的旧 hash 声明真实证据。
- Phase 1 内无已知 residual。Phase 2 的 reading-scope schema/Harness compatibility removal、Phase 3+ 精确
  SourceSpan resolver、E2E Agent loop 和最终 Word 产品验收仍按原阶段归属，不能由本阶段证据推导为完成。
- Reopen trigger：出现第二个 source-entry generator/build owner；App/Tool/resume 再次从 raw objects 重建；
  exact text 被隐式转换；结构对象静默遗漏；或 persisted inventory 未绑定 source/unit projection 仍可成功。

### Phase 2：Agent 只提交唯一源定位合同

目标：Agent 只从输入词表选字段，用 source_entry_id + ordered parts 表达语义。
交付：schema、输入 packet、反馈和必要 Skill/Reference；reading view 仅展示，不承担 judgment 定位。

验收：旧 scope.reading_block_id/reading_range_id、Agent 自造 span/slot/object refs、旧字段别名一律拒绝；
没有 old-to-new normalizer。单元内多责任拆分、跨单元语义分别引用各自 entry，不引入独立 range 主定位。
真实 Agent 能输出新合同或准确 needs_input；机械账本不得转嫁给 Agent。
层级：logic/contract + E2E agent loop（needs_input 仅证明安全失败，不算该输入产品成功）。

#### Phase 2 验收记录（2026-09-11）

结论：**ACCEPTED**。证据层级为 `logic/contract` 与真实 `E2E agent loop`；不包含 Phase 3
精确 resolver、DOCX 写入或 `product acceptance`。

- 总目标贡献：post-unit JSON schema 与机械 validator 现在只接受
  `semantic_judgments[].source_entry_id + parts[]`；`scope.reading_block_id`、
  `scope.reading_range_id` 即使指向当前 view 也返回 `legacy_reading_scope_unsupported`，Harness 不落盘，
  没有 old-to-new normalizer。既有 Agent-authored span/slot/object/locator refs 与旧字段 aliases 继续由
  denylist/schema fail closed。
- Agent 工作面：raw Agent-output contract 从 inventory 的 `source_entries[]` 建 allowlist，不再用 reading
  view ID 验证 judgment；prompt 明确 reading blocks/ranges 只用于阅读和分组，跨 entry 责任按文档顺序分别
  提交 judgment；正文 Reference 删除 compatibility range scope 指引。
- Harness packet：真实封面 resume 首次暴露 reading view 在已有 canonical source-entry mapping 时仍强制
  `object_text_spans` 的旧门禁。修复后 reading view 可用已声明的 `covered_source_entry_ids`，且 view 中的
  entry ID 必须属于 submitted canonical entries；这使真实 run 进入 SDK Agent session，未触碰 Phase 3
  resolver、编译或物化。
- contract red/green：实施前 P0-N06 两层测试为 `3 failed`；实现和 `$simplify` 后聚焦命令
  `uv run pytest -q tests/contract/test_template_judgment_shape.py tests/contract/test_agent_boundary_guardrails.py tests/contract/test_agent_output_contract_runtime.py tests/contract/test_template_agent_io_contract_loop.py tests/contract/test_template_field_id_contract_loop.py`
  为 `58 passed`。相关 Ruff 通过，strict mypy 对 5 个修改源码文件通过，Agent-facing legacy-scope source
  scan 无命中，`git diff --check` 通过。
- E2E attempt：使用真实 hash `5456f95d...a8cc` 封面输入、已有 accepted unit-boundary proof、当前修改代码和
  MiniMax backend，在新 task root `temp/phase2-p0-n06-e2e-20260911` 运行 `--from unit-boundary --until post-unit`。
  修复 packet gate 后进入真实 SDK session，但 90 秒内没有 Tool call 或 structured result，返回
  `origin=agent`、`code=template_agent_no_progress_timeout`；该次安全失败未计作成功。
- E2E acceptance：依据同 backend 已知长延迟，将 no-progress 门限隔离提高到 600 秒，并使用全新 root
  `temp/phase2-p0-n06-e2e-long-20260911` 重跑同一真实输入。post-unit 第一次 structured output（总 query 2）
  收到 Harness `needs_feedback`；第二次输出（总 query 3）修订后 `accepted`。最终
  `post-unit-checkpoint.json` 为 `status=ok`，落盘 16 个 semantic judgments；每个 judgment 都有
  `source_entry_id`、ordered `parts` 和 Harness `resolved_spans`，旧 `scope` 为 0。该 run 的
  `harness_feedback_attempts=1`、`semantic_feedback_attempts=1`，构成真实 feedback → revision → accepted 证据。
- `$simplify`：reuse 无问题；quality 发现并修复 reading view 可用未声明 source-entry ID 绕过
  `object_text_spans` 门禁的风险；efficiency 无问题。未扩大到 Phase 3 resolver、compiler、materializer 或
  product acceptance。
- exploratory broad contract run 为 `483 passed / 68 failed`；失败主体是仍构造旧 reading-scope judgments 的
  Phase 3/6 fixture/acceptance tests，另含当前 dirty fixture 的既有生成测试失败。本阶段不把这些旧成功预期
  normalizer 成新合同，也不据此宣称全套回归通过。
- Reopen trigger：schema、raw output contract 或 Harness 再次接受 reading scope；出现 old-to-new normalizer；
  Agent 可提交 locator/object/span/slot 引用；或真实 loop 无法再以 source-entry judgments 完成反馈修订。
  Phase 3 继续负责精确范围解析与旧 downstream fixtures 迁移，不得据此恢复 Phase 2 双协议。

### Phase 3：共享精确 span resolver 与 Harness 闭合

目标：范围、原文、Word fragments 是同一事实，首次接受与重读检查不能采用不同解释。
交付：唯一 resolver 和 typed resolved spans；Harness 检查词表、范围、内容、覆盖、冲突与可执行性。

验收：每个 part 对应精确源切片；交换 offsets、扩大到父段、错 entry/fragment、越界、歧义、重复/遗漏
均失败，即使重算所有可重算摘要仍不能通过。重复文本不能选首个匹配凑数。
删除无 source entries 时的 object-only coverage fallback；首次提交、持久化重读、恢复的判断一致。
下一层消费精确解析结果，不再把范围压缩为 covered_object_ids 集合。
层级：logic/contract + 真实 inventory/judgments 的 real replay。

#### Phase 3 验收记录（2026-09-11）

结论：**ACCEPTED**，证据层级为 `logic/contract` + hash-bound `real replay`；未执行新的
`E2E agent loop`，也不包含 Phase 5 compiler 重构、Phase 6 物化/发布实现或 `product acceptance`。

- canonical swapped-offset red 先成立：姓名/label 等价反例在交换 offsets 与 Word fragments、同步重算
  source-inventory digest、`span_ref` / `slot_ref` 和 semantic-review digest 后仍被旧 shared review 接受，
  新 resolver 接入后同一反例 fail closed。专项矩阵同时覆盖 wrong text、wrong source entry、越界、
  equal-precision ambiguity、fragment gap、parent-range expansion、duplicate judgment 与 entry/part omission；
  resolver 顺序按 Python code point 推进，不调用首个文本匹配、trim 或 Unicode normalization。
- `src/docfit/template/source_spans.py` 成为唯一 exact resolver：typed `TextSourceExtent` / `WholeEntrySourceExtent`、`SourceSpan`、
  `ResolvedSourceSpan` 与 ordered `WordFragment` 同时绑定 source snapshot、canonical inventory digest、
  exact expected source content 和 fragment-local offsets。`span_ref` 由 source snapshot + source entry +
  完整 typed extent 派生，不再只由 `part_index` 命名。
- Harness 首次 submit、`semantic_review.review_uses_current_semantic_shape()` persisted re-read、App resume
  `_accepted_harness_semantics()` 与 Tool shared review `_post_unit_phase_review()` 共用相同 resolver 解释；
  无 source entries 的 object-only acceptance 分支与旧 reading block/range resolver 已删除。reading blocks
  只保留为 Agent reading context，不再是 judgment scope，也没有 old-to-new normalization。
- `$simplify` 复核实际 diff 后删除 Harness 旧 reading-scope span 映射死代码和 shared review 的 object-only
  coverage fallback；source `slot_ref` 的 Tool/publication parser 复用 canonical SourceSpan ref parser。
- 空文本结构单元不能再被 replay 子集跳过：`whole_entry` 使用一个空文本、非字段 role 的显式 Agent judgment，
  resolver 产出无伪造 offsets 的 structural fragment；遗漏、把它伪装成 text extent、绑定字段或多对象歧义均失败。
- focused contract：`210 passed`；Ruff 通过，mypy 对 6 个相关 production 文件通过。探索性全 contract 为
  `537 passed / 5 failed`；4 个失败来自工作区既有 Registry YAML/hash 不一致，1 个来自既有
  `unit_evidence_packet` fixture 未写 persisted inventory，均不在 Phase 3 changed scope，未通过修改用户
  dirty Registry 或无关 fixture 掩盖。
- real replay 位于 `temp/phase3-source-span-replay-structural-20260911/`，绑定接受的 Phase 2 source hash
  `5456f95d56424fccf72bc606b2c75db9eb85a561a0a6bbd2cee6af47a3d6a8cc`。从原 16 个 Agent judgments
  中机械选择 8 个无需改写即可逐 code point 等于 source entry 的 Agent judgments（其余含被 Agent 丢弃的前后
  空白，不能 normalize 后冒充通过），并对真实 inventory 的 5 个空结构 entries 显式提供 whole-entry replay
  judgments。共覆盖 13 entries / 50 inventory objects，Harness 接受并解析 19 spans，其中 5 个 structural spans
  无 text offsets；resolved-spans digest 为 `b824d08b6e9d135d984fe82976a43c84e26aad3cd26478c5899dc110748bf26a`。
  evidence 证明 submit、persisted re-read、App resume、Tool shared review 均为 exact `true`；现有 compiler
  产生 13 intents / 0 unsupported，且 payload 中的 resolved spans 与 accepted review 逐对象相等，没有重选
  locator 或退化成 `covered_object_ids`。这只是下一消费者合同 proof，不把 Phase 5 标为完成。

### Phase 4：移除后置字段搜索并封闭 Tool 输入

目标：保持输入词表是字段唯一来源；Tool 不重新获取字段或独立选择业务源位置。
交付：可达 Tool schema/service/feedback 审计、删除清单与旧输入拒绝测试。

验收：semantic_field/query/运行时 Registry semantic search 不可达；反馈不要求后置查询。
模板业务写接口不能接收覆盖 span 解析结果的独立 target_ref/locator/paragraph；
底层 raw 操作仅由受控 Executor 调用，不能构成另一条模板业务路径。
层级：logic/contract + 调用路径审查；已有正确字段治理实现复用，不无理由重写。

#### Phase 4 closeout（2026-09-11）

- 状态：**ACCEPTED at `logic/contract` + call-path/source audit**。模板产品 Agent 的实际 App 调用点都以
  `include_docx_tools=False, template_semantic_only=True` 构建 Tool server，因此只公开
  `docfit_evidence(document_map|unit_evidence_packet)`；`docfit_check`、`docfit_apply` 和 raw `docx_*`
  操作不在该 runtime surface。
- 字段来源：公开 schema 不含 `semantic_field` / `query` / `registry_field` / `field_id` 搜索输入；
  `FieldRegistrySnapshot` 不再有 `search()` API，AST source scan 也未发现 App/Tool/Template runtime 的
  非正则 `.search()` 调用。保留的 `focus=registry_field` 与 `check=registry_binding` 只返回专用
  fail-closed 结果，不读取 Registry 或返回候选。
- SourceSpan 边界：公开 `docfit_apply` schema 只接收 Harness action-package `batch_ref`，不接收
  `operation`、`target_ref`、`object_ref`、`locator`、`paragraph(_index)`、`scope_ref`、
  `source_entry_id`、`span_ref`、`slot_ref`、reading view ref 或直接字段/替换参数。service 直调也对这些
  legacy 顶层参数统一返回 `schema_envelope_invalid`，不能静默忽略后继续写入。action package 内的 raw
  DOCX refs 仍是 Harness/Executor 内部账本；其 Phase 6 provenance/materialization 行为本阶段未改。
- 删除清单：删除 Agent/runtime Tool surface 的 `unit_slice`、Registry lookup、旧 check kinds、direct
  apply operation/target 字段和旧 surface compatibility aliases；audit summary 不再记录这些退役输入；
  旧测试已反转为 schema 不可见、service 显式拒绝、模板调用路径不挂载 raw tools。
- 证明：`uv run pytest -q tests/contract/test_docfit_evidence_tool.py
  tests/contract/test_docfit_check_tool.py tests/contract/test_docfit_apply_tool.py
  tests/contract/test_tool_surface.py tests/contract/test_tool_contract.py tests/contract/template_gate`
  -> `158 passed`；`uv run ruff check` 聚焦 owned scope -> pass；`uv run mypy src/docfit/tools` ->
  `Success: no issues found in 11 source files`。为避免把工作区其他阶段的大型测试迁移带入本提交，
  Phase 4 还有独立可提交的 `test_template_tool_boundary.py` 覆盖 24 种 direct-apply 旧输入；
  提交边界聚焦矩阵为 `43 passed`。当前沙箱使用 `UV_CACHE_DIR=/tmp/docfit-uv-cache`。
- 未完成层级：本阶段没有新增 `real replay`、`E2E agent loop` 或 `product acceptance`，也没有实施
  Phase 5 compiler 或 Phase 6 materialization/publication 行为。

### Phase 5：编译与 readiness 只消费 accepted spans

目标：执行计划既不补造字段，也不重选目标。
交付：typed-only plan，绑定输入词表、accepted judgment、精确 spans 与 resolver 结果。

验收：自然语言、role/reason、学校 wording、默认 catalog 都不能生成字段或猜目标。
缺 span、错快照、不可解析 fragments 时不得形成可执行计划；不先执行再靠发布失败兜底。
真实输入的每条执行计划都可追到 accepted source range；不能用 receipt 名称代替内容绑定。
层级：logic/contract + real replay，含下一层执行合同验证。

#### Phase 5 closeout（2026-09-11）

- 状态：**ACCEPTED at `logic/contract` + hash-bound `real replay`**。这不包含 Phase 6 handler、
  DOCX mutation、publication、resume、consumer，也不构成 `E2E agent loop` 或 `product acceptance`。
- 字段闭环：compiler 先验证 accepted-review envelope、semantic-judgments digest、source snapshot、
  全局唯一 canonical `span_ref` 和顶层 resolved-span ledger；每个产出的 `field_id` 另有 typed
  `field_bindings`，机械绑定 accepted part index/role、原 `span_ref` / `slot_ref`，并继续受当前
  pre-input vocabulary digest 和 Registry snapshot 约束。自然语言、reason、学校 wording 或 catalog
  不参与字段生成，runtime 源码无业务 field-ID default。
- 目标闭环：`AcceptedResolvedSpan` 对 canonical SourceSpan ref、source/inventory digest、extent、原文、
  ordered Word fragments、object-ref/fingerprint 绑定和 fragment 连续覆盖做 fail-closed 解析；intent
  在 `payload.resolved_spans` 中无损保留 accepted JSON。context 不再展开 reading block/range/unit，
  不按文本、locator、`target_ref` 或 `covered_object_ids` 重选目标；它只重新调用 shared
  `resolve_source_span()` 并把当前解析结果与 accepted fragments 精确比较。
- 负向证据：缺 span 或不完整 review 在 readiness 前置门返回
  `materialization_semantic_review_not_current`；不可解析 ref、缺 fragments（即使补 locator、target_ref
  或 covered-object IDs）由 compiler 阻断；source inventory locator/digest/fragments 陈旧由 readiness /
  context 在执行前阻断。reopened adjacent fixture audit 已把 readiness/context/plan 中仍把
  reading block/range/unit 当成功输入的测试迁移为 current source-entry + canonical resolved span +
  accepted-review fixture，并把退役 target-selection 路径反转为 fail-closed 断言。五文件 focused
  `logic/contract` suite -> `82 passed`；owned Ruff、strict mypy 与 `git diff --check` 均通过。
- `real replay`：读取
  `temp/phase3-source-span-replay-structural-20260911/work/.docfit/harness/{object-inventory.json,semantic-judgments.json}`
  和同 root Registry，`materialization_readiness_feedback` 无 blocker，正式
  `build_shadow_materialization_plan` ready；13 个 intents 携带 19 个 typed spans、3 个 field bindings。
  accepted flattened spans 与下一执行合同 flattened spans 的 digest 都是
  `b824d08b6e9d135d984fe82976a43c84e26aad3cd26478c5899dc110748bf26a`，并逐 intent 断言 JSON
  相等。对同 inventory 的 source-entry locator 造 stale 后，readiness 与 context 均在执行前拒绝。
- 下一阶段 handoff：Phase 6 只能消费 intent 上的 typed `resolved_spans` / `field_bindings` 及 context
  中同一份 fragments；不得重新按 reading/object/text/locator 选择范围。本阶段没有改 handler，故不能
  把本 replay 描述为实际 Word 写入或发布验证。

### Phase 6：实际写入、发布、恢复与消费者统一

目标：所有实际变更由 accepted span 决定，持久化后仍保持该事实。
交付：统一 Executor/候选映射；slot/body/generated/cleanup/manual/style 全 handler；
新版 checkpoint、receipt、Fill Contract 与消费者验证。

验收：
- 同一 span 无法被替换成所属整段、相邻 run 或同名文本；错误范围在写入前拒绝。
- 同段多槽、跨 run、跨单元有序 spans、清理后填写、重试保持位置正确；source/candidate stale 失败关闭。
- Tool 与宿主直接物化消费同一 resolver，得到相同 fragments 和等价实际变更。
- 独立重开 Word 验证选定内容被处理、未选定文字/样式/结构不被误改；不只检查内部 receipt。
- 候选变化由 Executor 维护映射，不全文搜索“找回”位置；局部失败无部分发布。
- 发布槽可追到字段、accepted span、源 entry、Word fragments 和实际结果；错接引用、孤立槽、
  同引用不同范围、receipt 与产物不符必须失败。
- 新包可重开、恢复并被实际消费者读取；旧 checkpoint/package/Fill Contract 明确拒绝，不双读或转换。
  发布来源证据不能仅存在于一次性 temp 目录。
层级：logic/contract + 实际 DOCX 读写、发布与消费者 real replay。

#### Phase 6 closeout（2026-09-11）

- 状态：**ACCEPTED at `logic/contract` + actual DOCX/publication/consumer `real replay`**。
  没有运行新的 `E2E agent loop`，也不构成 `product acceptance`。
- 唯一执行合同：宿主 materializer 在第一次 mutation 前解析并核对全部 typed
  `AcceptedResolvedSpan.word_fragments`；slot/body/generated/cleanup/manual/style 路径只从 intent 的
  `resolved_spans` / `field_bindings` 取得目标与字段。body member 顺序来自 typed binding 与 span 的 join，
  structure parent 只从 Registry parent 机械取得；handler 不再从 payload 的 reading block/range、对象集合、
  文本或业务默认值重选目标。宿主与直接 Tool mutation 共用 `object_mutation.resolve_word_locator()`。
- 持久化合同：materialization receipt schema v2、publication receipt schema v2 与 Fill Contract v2 的
  materialization provenance 共同绑定 source/inventory/review/vocabulary/Registry、完整 accepted span、
  ordered Word fragments、candidate before/after hash 与实际 operation/receipt digest。publication 先在临时目录
  完成全合同验证再原子替换；resume、placement consumer 拒绝 legacy、缺 span 或引用不一致的包。
- `logic/contract`：相关 14 文件矩阵 `343 passed`；覆盖同段多槽、跨 run/ordered spans、cleanup 后 fill、
  retry、source/candidate stale、相邻/同文本错目标、原子无部分发布、receipt/product mismatch 与 legacy package
  rejection。相关 Ruff、strict mypy（25 个 source files）及 `git diff --check` 通过。
- `real replay`：证据位于
  `temp/phase6-materialization-real-replay-20260911c/phase6-replay-evidence.json`。真实 source hash
  `5456f95d56424fccf72bc606b2c75db9eb85a561a0a6bbd2cee6af47a3d6a8cc` 写出并独立重开 hash
  `01d3577e32db695c141cb1fdeeb36dc7a3456c8ccf40be1b8f11b5d956f71d2d`：3 个 accepted 段落改变，
  19 个未选段落、表格结构、段落属性及 15 个非 `word/document.xml` package members 不变；3 个 published
  controls 与 persisted slot/span/field 一致。第二次 host run 从完成态恢复；真实 `load_fill_contract` /
  `build_placement` 对未人工接受包正确返回 `PARTIAL`，模拟接受同一已验证包后返回 `COMPLETE` 和 3 条操作。
- 后续边界：Phase 7 只做全路径删除复核与长期文档同步；Phase 8 的完整 E2E / 产品验收矩阵仍保留，
  不能把本阶段 real replay 升级为学校语义正确或最终产品可用。

### Phase 7：全路径删除复核与长期文档同步

目标：确认阶段中已退出的旧能力无遗漏、无回流，文档只指导唯一合同。
交付：逐入口 deletion checklist、schema/Contract/module/Skill/ID ledger 与相关 Test/Eval 更新。

验收：Phase 0 每条入口均有去向、删除 diff、旧输入拒绝案例；调用图与 source scan 同时通过。
残留 object/locator 必须说明内部调用者，不能以改名通过扫描。不存在 alias、fallback、旧 ref 解码、
双读、补来源、按文本/locator 补匹配。旧夹具需要重建则注明依据，不修改 Gold 来接受错误产品。
相关 lint、type-check、contract/integration/consumer/Eval 通过；文档不再允许过渡主定位。
层级：logic/contract。此阶段是全局复核，不是允许 Phase 1–6 留下旧路径的缓冲区。

#### Phase 7 closeout（2026-09-12）

- 状态：**ACCEPTED at `logic/contract`**。这只证明旧定位/字段查找合同没有留在当前成功路径或默认长期
  指导中；不代表 Phase 8 真实矩阵、外部视觉 review 或 product acceptance 完成。
- 总目标贡献：默认阅读路径中的 `docs/contracts/template-extraction.md`、
  `docs/modules/template-extraction.md`、`docs/agents/ai-coding-boundary-guardrails.md` 与 accepted ADR 0002
  现统一规定 Agent 只输出 `source_entry_id + ordered parts`，reading block/range 只作为输入 view 或反馈
  分组。superseded ADR 0003 的“当前决策”摘要也已改为同一合同，不再用 tombstone 复述旧正向协议。
- 删除/迁移清单：模块文档不再把 `source_content_id` 写成模板 runtime 的 legacy compatibility；ADR 0002
  不再指导 `scope.reading_block_id / reading_range_id`、reading-scope coverage 或 scoped judgment。
  历史计划、bug 复盘和明确 fail-closed 示例保留旧词只用于解释/拒绝，不能作为默认操作入口。
- reachability 证据：production source scan 中 `semantic_field` / `registry_field` / retired source override
  仅位于 denylist、sanitizer、显式 `schema_envelope_invalid` 或 `registry_field_runtime_removed` 路径；compiler
  的 `_scope_refs()` 只从 current judgment 的 `source_entry_id` 构造
  `ScopeRef(kind="source_entry")`，production 中没有构造 reading-block/range/unit/object scope 的成功路径。
  因此内部字段名 `scope_refs` 是 accepted source-entry 执行账本，不是改名保留的旧 Agent scope。
- 负向与文档证据：`tests/contract/test_documentation_contract.py`、
  `test_source_location_documentation_contract.py`、`test_agent_boundary_guardrails.py` 共 `22 passed`；Ruff、
  `git diff --check` 和长期文档 forbidden-phrase scan 通过。更宽的 contract/materialization replay/agent
  回归在同轮为 `727 passed`。
- 下游消费：Phase 8 继续直接消费 Phase 1–6 的 current source inventory、accepted source-entry spans、
  materialization receipts 和 publication provenance；不需要为真实矩阵补 alias、fallback 或旧输入转换。
  若后续 source scan 发现新的旧协议成功入口，Phase 7 必须 REOPEN，而不是在 Phase 8 绕过。

### Phase 8：真实矩阵、产品验收与总目标签收

目标：逐项证明整个唯一链路工作且最终模板可用，而非仅证明各阶段局部正确。
输入：0820 封面、目录、正文、开题报告；HUNAU/NJAU/PKU 已约定全部 logical units。
以 Phase 0 的 hash-bound manifest 为准，不能为了通过而缩小矩阵；Gold 不进入产品 Agent。

验收：每行记录 logic/contract、real replay、E2E agent loop、product acceptance 的完成情况。
至少有真实反馈 → Agent revision → accepted → 实际写入证据；没有自然修订时可用另行标明的
受控故障实验触发真实 Agent，不能把故障注入称为自然失败。环境失败和 needs_input 不算该输入成功。
全部产物可打开、字段正确可填、范围准确，无误删/错替换/漏字段/重复；全页视觉检查通过。
当前中文题目漏槽、姓名职称混合、格式说明残留和占位换行按 Agent 语义/Executor/呈现分别归因并复验。
总目标各条均有正向证据、绕过反例拒绝证据、实际 Word 结果和无旧路径证据，才允许 DONE。
人工签收要求未满足时不能代签；整个计划保持 CONTINUE。

## 阶段交付记录与推进门

每阶段固定交付以下记录，不用泛泛“对齐总目标”作为答案：

1. 对应的总目标条款，以及本阶段实际建立的不变量。
2. 本阶段目标证据与总目标审查证据，标明验证层级和未验证范围。
3. 删除了哪条旧能力；哪些底层映射合法保留，为什么不构成绕过。
4. 下一阶段如何直接消费交付物，实测/合同验证结果是什么。
5. 错误反例如何被拒绝；独立 Word 检查如何避免 resolver 自证正确。
6. 遗留事项及其影响：当前职责内/阻断下游/影响总目标的缺口必须关闭；真正后续职责要明确归属，
   不能用“以后处理”掩盖依赖未成立。无关优化另记，不阻塞本任务。
7. 结论 ACCEPTED / REOPEN / 尚未验证，以及可复现基线、提交、输入 hash 和证据路径。

推进顺序沿 Phase 0–8；保留已有合格成果，重新打开的阶段补齐后才能重新授予完成状态。
固定并审阅 Git/工作区基线，不能只给 commit hash 却隐去运行依赖的 dirty tree。
后续发现反例时回到责任阶段，不能给 Tool、Skill 或下游增加旁路补丁维持绿色结果。
计划文件的完成项只记证据已证明的事实，不把目标设计写成当前能力。

## 历史计划与实施记录（不再作为当前执行指令）

以下原文保留用于追溯已有工作，包括旧阶段目标、完成口径、临时失败和历史环境。
它不覆盖上述总目标、唯一合同、Phase 0–8 验收与当前状态；其中 reading scope 主定位、仅凭 ref/receipt
判断闭合、兼容路径及“只剩 Phase 8”表述均已失效。引用历史证据必须说明其原始验证范围，
不能把历史执行记录再次读成待执行命令。历史内容不代表本轮重新验证通过。

# 模板字段 ID 词表边界完整重构计划

## Status

REOPEN — 32/32 live E2E/publication 已闭合；完整 fixed-render 与 human acceptance 待签收。

## Refactor Scope Gate

- Target: 模板提取字段 ID 来源、semantic judgment、Harness span 解析、slot 发布 identity 这条 seam。
- Change type: aggressive cleanup；不保留旧 schema、旧字段别名、旧 coverage 输入协议、旧 slot_id
  生成协议或旧中间态迁移层。
- Accepted severities: P0/P1/P2 inside the target seam。
- Accepted cleanup checklist:
  - Agent-visible Tool / schema / feedback 不再暴露 `slot_id`，只接受 Harness `slot_ref`。
  - publication、Fill Contract、Style Contract handoff 和 downstream placement 不再把发布槽位 identity
    表达为旧业务 `slot_id`。
  - runtime 不再使用代码内 `body.*` 字段 catalog 作为字段来源或结构默认值；body/generated 字段只来自
    accepted ordered parts 和 Registry parent / metadata。
  - long-term Contract、Skill 和 plan status 不再指导后置查字段、fallback 或旧 wrapper 兼容。
  - source scan 对旧字段别名、旧 coverage Agent 输入、旧 slot_id 生成协议和 fallback 只有 fail-closed
    denylist、内部 Harness ledger 或非模板模块 allowlist 残留。
- Parked issues: 用户内容提取和 final word 生成中作为 Student Content / placement 领域字段存在的
  `body.*` 字段，不在本次模板提取边界内重命名。
- Compatibility kept: none for the template field-ID / slot identity seam。
- Compatibility removed: old Agent field aliases, runtime semantic Registry search, Agent-authored coverage IDs,
  slot identity as `slot_id`, and code-owned body field catalog as runtime source。
- Minimum confidence level: L2 contract/source scan；真实 task root replay、E2E agent loop 和 product
  acceptance 作为最终 completion gate。
- Existing evidence: Phase 0-7 contract/source-scan slices, vocabulary-only Skill tree guard,
  0820 body range Harness replay, 0820
  `01-cover` / `03-toc` / `06-proposal` / `04-paper-body` live post-unit/product-provenance
  slices, HUNAU/NJAU/PKU representative logical-unit live provenance matrix from 2026-09-03,
  HUNAU 10/10 current-hash live provenance matrix, NJAU 10/10 current-hash live provenance matrix,
  PKU `03-abstract-cn` current-hash representative live provenance slice,
  PKU `04-abstract-en` current-code real replay through publication slice,
  2026-09-04 HUNAU/NJAU/PKU representative current-code inventory real replay,
  NJAU `06-body` whole-unit body-structure product-provenance slice, NJAU
  `07-references` collection slot provenance slice, NJAU `08-appendix`
  appendix-title provenance slice, and NJAU `09-academic-achievements` /
  `10-acknowledgement` terminal provenance slices，以及 2026-09-13 HUNAU/NJAU/PKU current-digest
  10/10、10/10、12/12 live E2E/publication 矩阵。
- Missing evidence: Phase 8 的完整 32 项 fixed-render coverage、锁定 OfficeCLI 验证与 human acceptance；
  live Agent / actual DOCX publication 不再有缺失 logical unit。
- Architecture packet: 本计划第 2-3 节提供 public contract、data flow、accepted seam、rejected fallback
  和 verification ladder。
- LSP status: Python repo uses strict mypy/ruff in `pyproject.toml`; no separate LSP config is required for this
  deterministic refactor gate。
- Local-only gates: live Agent E2E and product acceptance require local credentials / OfficeCLI environment。
- Persistent gate file: `docs/plans/template-field-id-vocabulary-boundary-refactor.md`。
- Stop condition: accepted cleanup checklist green, relevant tests and source scan pass, plan status updated to
  `DONE` only after real replay, E2E agent loop and product acceptance evidence cover the required matrix.

## 1. 当前产品结论

本计划只处理模板提取 post-unit 阶段的字段 ID 来源和使用边界。

当前系统已经能把 `field-registry.yaml` 复制进 task input，并能在后置阶段校验某个
`field_id` 是否存在于 Registry；但这还没有达到产品目标。真正目标是：

```text
字段 ID 必须在 Agent 对模板单元内部元素做语义判断前就已经存在、
已经进入 Agent 输入工作面、并且后续全链路可验证。
```

Agent 只能从这份输入词表选择字段 ID，并对已输入的 reading block / range 输出有序语义拆分。
Harness 负责把 Agent 的 ordered parts 映射到底层 Word runs/ranges，生成可追踪的 `span_ref`，
并验证覆盖、冲突和可执行性。
compiler、handler、materializer、publication 和 fill-contract 生成逻辑都不能创建、猜测、
补造或迁移字段 ID。

这次修复是完整重构，不保留旧逻辑兼容。任何旧输出形状、旧字段别名、旧 fallback 或
旧测试，只要依赖后置推断字段 ID，就必须删除或反转为 fail closed。

## 2. 硬边界

### 2.1 允许存在的 ID 来源

| ID / reference 类别 | 唯一允许来源 | 出现时机 | 后续可做什么 |
| --- | --- | --- | --- |
| Registry `field_id` | 当前 task input 绑定的 Field Registry snapshot | Agent post-unit 语义判断前 | Agent 只能选择；Harness 只能校验；后续只能消费 |
| `reading_block_id` / `range_id` | unit reading packet 构建阶段 | Agent post-unit 语义判断前 | Agent 引用；Harness 映射到底层对象 |
| Agent semantic parts | Agent 对输入 reading block / range 的有序语义拆分 | Agent 输出阶段 | Harness 按数组顺序赋予 `part_index` 并解析物理 span |
| `span_ref` | HarnessSpanResolver 根据输入 reading ref + Agent ordered parts 生成 | Harness review 阶段 | 内部执行引用；不能作为字段来源，Agent 不输出 |
| `slot_ref` / Word tag | Harness 或 materializer 按 `span_ref + field_id` 机械序列化 | Harness 接受后、DOCX 写入时 | 保证发布槽位唯一；不是新的业务字段 ID |

说明：

- 内容 hash、文件 hash、schema version 可继续作为完整性校验材料，但不能作为字段、slot、
  judgment、intent 或发布契约中的业务 ID。
- 文件名或候选路径可以作为存储路径存在，但不能进入 Agent 输入、semantic judgment、
  materialization plan、content control tag 或 fill-contract 作为业务 ID。
- 凡是对外字段名、槽位名、判断名、intent 名、receipt 追踪名中包含 `*_id` 的值，都必须能追溯到
  `field_id`、`reading_block_id`、`range_id` 或 Harness 解析出的 `span_ref` / `slot_ref`；
  追溯不到就删除或改成非 ID 的结构位置，例如数组下标、JSON path 或 Harness-resolved `span_ref`。

### 2.2 明确禁止的后置 ID 行为

以下行为在目标架构中全部禁止，不做兼容：

- Agent 用 `semantic_field`、`query`、自然语言 label、reason、role、handler 反馈去查询或生成字段 ID。
- Harness 只做 Registry existence check，却不验证 field ID 是否来自本轮 Agent 输入词表。
- compiler/readiness/materializer 根据 `judgment`、`reason`、`semantic_role`、
  `clean_template_treatment`、visible text 或 Registry label 推字段。
- 代码硬编码 `generated.toc`、`body.chapters`、`body.heading.outline*` 等字段 ID 作为默认值或可选项来源。
- `docfit_apply`、legacy mutation 或 handler 在缺字段时补默认 field ID。
- publication/fill-contract 仅从最终 DOCX alias 读取 field ID 并信任 Registry lookup。
- Agent 输出 `span_id`、`slot_id`、`judgment_id`、`intent_id` 或 content-control tag。
- runtime 生成新的 `judgment_id`、`intent_id`、`slot_id`、content-control tag digest，并把它们作为业务 ID。
  Word tag 若必须是字符串，只能是 `span_ref + field_id` 的机械序列化。

## 3. 目标链路

目标链路如下：

```text
Field Registry snapshot
  -> PreInputFieldVocabulary
  -> UnitReadingPacket(reading_block_id / range_id / visible text)
  -> AgentSemanticSegmentation(ordered parts)
  -> HarnessSpanResolver
  -> Harness Vocabulary/Span/Coverage Gate
  -> Typed Semantic Plan
  -> Deterministic Materialization
  -> Publication Cross-check
  -> final-template.docx + fill-contract.yaml
```

每层责任：

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| PreInputFieldVocabulary | 从已绑定 Registry snapshot 生成 Agent 可见字段词表、usage affordance、digest | 根据模板文本裁剪或猜字段 |
| UnitReadingPacket | 生成 Agent 可见 `reading_block_id`、`range_id` 和可见文本 | 预生成 `span_id`，或让 Agent 直接引用 Word locator/object_ref |
| Agent | 选择输入词表中的 field ID；对 block/range 输出有序语义 parts | 发明 ID、查询 ID、补 ID、输出 `span_id` 或 DOCX 操作 |
| HarnessSpanResolver | 把 Agent ordered parts 映射到 Word runs/ranges，生成 `span_ref` / `slot_ref` | 判断字段语义或选择 field ID |
| Harness | 验证 field ID 来源、span 解析、覆盖、重复、冲突、缺失和可执行性 | 替 Agent 判断学校语义或选近似字段 |
| Compiler | 把已通过 Harness 的 typed judgment 编译成执行计划 | 从自然语言推 intent 或 field ID |
| Materializer/Handler | 执行 typed plan；只消费已验证 field refs 和 Harness-resolved `span_ref` / `slot_ref` | 创建业务 slot ID、猜 label 对应字段、处理旧 schema |
| Publication/fill-contract | 验证最终 DOCX 中每个发布槽位来自 accepted judgment 和输入词表 | 只凭 SDT alias 或 Registry lookup 接受字段 |

### 3.1 影响面基线

实施前必须把以下影响面纳入同一张迁移清单。可以分阶段落地，但不能在实施前假定某层无关。

| 影响面 | 当前代表文件 / 组件 | 为什么必须纳入 |
| --- | --- | --- |
| Registry 输入绑定 | `src/docfit/fields/registry.py`、task input registry copy | 字段 ID 唯一来源，只能在 Agent 输入前快照化 |
| Agent 输入工作面 | `src/docfit/template/reading_packet.py`、startup brief、unit evidence packet | 必须同时提供 field vocabulary、`reading_block_id` / `range_id` 和可见文本 |
| Agent schema / Skill | post-unit output schema、`.claude/skills/docfit-school-extract/**` | 必须删除旧字段别名、Agent-authored ID 和 registry lookup 指令 |
| Harness review | `src/docfit/template/harness.py`、phase review checkpoints | 必须执行 vocabulary、scope、part mapping、coverage、conflict gates |
| Tool runtime surface | `src/docfit/tools/surface.py`、`src/docfit/tools/schemas.py`、`src/docfit/tools/service.py`、`src/docfit/tools/__init__.py` | 当前存在 runtime 查字段、legacy mutation 和 schema 兼容入口 |
| Compiler / readiness | semantic plan compiler、readiness gate、artifact assembly | 只能消费 Harness accepted typed output，不能根据 prose 补 intent/field |
| Materialization handlers | `src/docfit/template/materialization/**`、`object_mutation.py`、`intent_classification.py` | 当前最容易按 handler、role、label、fallback 生成或补 ID |
| Style / content fill | `src/docfit/styles/**`、`src/docfit/content/fill.py`、`student_content_fill.py` | 现有 `slot_id`、tag、occurrence 逻辑会影响 fill-contract 和最终 Word |
| Publication / fill-contract | `src/docfit/template/artifact.py`、fill-contract writer、content control publication | 必须把最终发布槽位交叉验证到词表、accepted parts、`span_ref` / `slot_ref` |
| Eval / contract schema | `evals/template-extraction/**`、contract schemas、alignment / markers | 当前大量以 `slot_id`、alias、tag 对齐，必须迁移成新 provenance |
| Tests | `tests/contract/**`、`tests/unit/**`、`tests/integration/**` | 旧兼容测试要删除或反转为 fail closed，不能作为回归保护 |
| 长期文档 | `docs/contracts/**`、`docs/modules/**`、`docs/agents/**`、其它 active plans | 防止实施后旧文档继续指导后置猜字段 |

### 3.2 风险和预案

| 风险 | 预案 |
| --- | --- |
| 误把已有 Registry 文件当成 Agent 输入词表已完成 | 验收必须检查每个 startup brief / unit packet 中的 `field_id_vocabulary`、digest 和 Harness 基线，而不是只检查 task input 文件存在 |
| 字段词表过大导致 Agent 输入压力 | 先定义确定性的当前可用子集和 digest；子集本身仍必须在 Agent 输入前生成并进入输入面，不允许 runtime query 补候选 |
| 当前可用子集漏掉真实需要的字段 | Harness fail closed 为 `needs_input` / vocabulary gap；只能修 Registry 绑定或 pre-input builder，不能让后续层补 ID |
| Agent parts 的文本在同一 block 中重复导致 span 解析歧义 | `HarnessSpanResolver` 以 scoped block/range、ordered parts、连续覆盖和 exact text 校验解析；歧义时返回 revision packet，不猜 occurrence |
| 复合槽位的 `part_index` 因 Agent revision 改变而影响发布引用 | `slot_ref` 只在 Harness accepted semantic set 后生成；revision 产生新的 accepted set 和 receipt，不提供旧 `slot_id` 兼容 |
| 下游仍依赖 `slot_id` / digest tag / alias-only 对齐 | fill-contract、eval marker、alignment 和 downstream tests 同步迁移；旧 `slot_id` 作为业务 ID 一律 fail closed |
| Word 内部必须存在 `w:id` 或 content-control tag 字符串 | 明确它们只是 DOCX 内部 locator/tag；可由 `slot_ref` 机械序列化或由 Word 生成，但不得作为字段来源或业务 ID |
| 旧 task root / resume 中仍有旧 schema 输出 | 不做 normalizer；Harness 直接返回旧 schema failure，真实链路需重新构造 packet 并让 Agent 按新 schema 重做 |
| handler/materializer 借 role、label、reason、fallback 继续推字段 | 增加 forbidden path lint 和 contract tests；执行计划中新增的任何 `field_id` 必须能追到 accepted Agent part |
| 文档、Skill 或反馈语继续引导 Agent 查字段 | 建 forbidden phrase scan；长期文档和 active plans 必须同步迁移后才能标记本计划完成 |
| 只用 mock / 单元测试误报为真实链路完成 | 验收汇报强制区分 `logic/contract`、`real replay`、`E2E agent loop`、`product acceptance` |

## 4. 阶段实施计划

### 4.0 阶段推进规则

本重构按 fail-closed 迁移推进。每个阶段都必须留下阶段证据包，至少包含产品层结论、
本阶段触达的代码/文档面、删除或反转的旧逻辑、验证命令和未完成的验证层级。阶段汇报不得把
`logic/contract` 测试说成真实链路完成。

阶段推进只允许向更严格的合同前进：

- 前一阶段的入口产物或门禁不存在时，后一阶段不能用 fallback 暂时代替。
- 任何旧 schema、旧字段别名、旧 `semantic_field` 查询、旧字段默认值或旧 `slot_id` 业务 ID，
  要么在当前阶段删除，要么在当前阶段反转成 fail-closed 测试；不能标成“后续兼容”。
- 每个新出现的 runtime `field_id` 必须能追溯到同一轮 `field_id_vocabulary` 和 accepted Agent part。
- 每个新出现的发布槽位必须能追溯到 Harness-resolved `span_ref` / `slot_ref` 和 materialization receipt。
- 文档、Skill、schema、Harness feedback、compiler、handler、publication 任一层仍引导后置推字段时，
  本计划不能进入最终验收。

### 4.1 实施波次

| 波次 | 阶段 | 目标 | 完成后用户能依赖什么 | 不能宣称什么 |
| --- | --- | --- | --- | --- |
| Wave A | Phase 0 | 冻结旧逻辑和测试清单 | 迁移影响面完整，旧兼容入口有删除或反转目标 | 不能宣称 runtime 行为已改变 |
| Wave B | Phase 1-3 | 建立输入词表、Agent ordered parts 合同和 Harness span/coverage 门 | Agent 只能在输入工作面选择字段；Harness 能拒绝旧形状和无来源字段 | 不能宣称 materializer/publication 已无后置造 ID |
| Wave C | Phase 4-6 | 删除 Tool semantic search、compiler/readiness 默认字段、handler/materializer/publication 运行时 ID 生成 | 执行链路只消费 accepted typed output；发布槽位有 provenance | 不能宣称真实学校模板已产品验收 |
| Wave D | Phase 7-8 | 同步长期文档并跑真实验收矩阵 | 默认文档、真实 replay、E2E agent loop 和产品产物证据一致 | 不能宣称未来 Registry 版本无需重新验收 |

### 4.2 阶段总览与验收门

| 阶段 | 实施目标 | 主要交付物 | 验收标准 | 最低验证层级 |
| --- | --- | --- | --- | --- |
| Phase 0 | 找全后置推字段、旧 schema、旧测试和文档误导点 | 迁移清单、`rg` allowlist、待删除/反转测试列表 | 清单覆盖 `src/docfit/app`、`tools`、`template`、`styles`、`content`、`.claude/skills`、`tests`、`evals`、长期文档；未修改 runtime 行为 | `logic/contract` |
| Phase 1 | 在 Agent 判断前生成 `PreInputFieldVocabulary`，并把它放进 startup brief / unit packet | vocabulary builder、packet schema、digest baseline、真实 task root packet proof | Agent 输入中存在 `field_id_vocabulary` / digest；字段集合来自 task Registry snapshot 或确定性子集；输入面没有 `span_id` 或后置 query 路径 | `logic/contract` + `real replay` |
| Phase 2 | 收紧 Agent schema / Skill 为 reading scope + ordered parts + input `field_id` | 新 post-unit schema、Skill/Reference 更新、forbidden-field 测试 | 旧字段别名、Agent-authored ID、`span_id` 均被拒绝；Skill 只指导从输入词表选择；真实 Agent 可输出新形状或 `needs_input` | `logic/contract` + `E2E agent loop` |
| Phase 3 | 让 Harness 完成 vocabulary、scope、span、coverage、conflict 和 executability gate | `HarnessSpanResolver`、accepted semantic set receipt、revision packet sanitizer | 未在本轮词表内的字段、缺字段的可执行 part、未知 reading ref、重复/遗漏/冲突、span 歧义全部 fail closed；receipt 记录 vocabulary/packet digest 和 resolved spans | `logic/contract` + `real replay` |
| Phase 4 | 删除 Agent runtime 可达的 Registry semantic search | Tool surface/schema/service 清理、旧 tool tests 反转 | Agent 不能通过 `semantic_field` / `query` 获取候选；feedback 不再要求调用 registry lookup；`FieldRegistrySnapshot.search()` 不在 runtime 路径可达 | `logic/contract` |
| Phase 5 | readiness / compiler 改成 typed-only，删除硬编码字段默认 | compiler/readiness 改造、hardcoded field allowlist、反向测试 | 自然语言、role、reason、TOC/body/outline 字样不会生成字段 ID；编译计划每个 field ID 可追到 accepted part 和输入词表 | `logic/contract` + `real replay` |
| Phase 6 | materializer、handler、publication 和 fill-contract 删除运行时业务 ID 生成 | `slot_ref` 序列化、materialization receipt、publication cross-check、fill-contract provenance | `fill-contract.yaml` 每个 slot 都能追到 input vocabulary、accepted part、`span_ref` / `slot_ref` 和 receipt；orphan/unknown/duplicate slot fail closed | `logic/contract` + `real replay` |
| Phase 7 | 把长期边界迁移到 Contract、模块文档、guardrails 和必要 ADR | 长期文档更新、旧 active plan 历史标注、文档 lint | 默认阅读路径不再表达后置查字段或硬编码默认字段；计划文档只保留历史证据，不再覆盖长期合同 | `logic/contract` |
| Phase 8 | 用真实输入证明四层验收闭合 | 真实 replay root、E2E agent loop root、产品产物、receipt/report | `01-cover`、`03-toc`、`04-paper-body`、`06-proposal` 和 HUNAU/NJAU/PKU 代表链路均按四层汇报；缺任一层不得标记完成 | `logic/contract` + `real replay` + `E2E agent loop` + `product acceptance` |

### 4.3 阶段间门禁

- Phase 1 未证明词表进入 Agent 输入面前，不改 Skill 让 Agent 依赖新字段选择规则。
- Phase 2 未拒绝旧 schema 前，Phase 3 不写 old-to-new normalizer。
- Phase 3 未产出 `span_ref` / `slot_ref` receipt 前，Phase 5/6 不让 compiler 或 materializer 自行创建发布引用。
- Phase 4 未删除 runtime semantic search 前，Phase 5/6 的 typed-only 验收不成立。
- Phase 6 未完成 publication cross-check 前，Phase 8 不进入 product acceptance。
- Phase 7 文档未同步前，即使代码通过，也只能说迁移代码路径完成，不能说本计划完成。

### 4.4 每阶段证据包格式

每个阶段完成时在最终汇报或阶段记录中固定列出：

- 产品结论：用户现在能依赖什么，仍不能依赖什么。
- 责任层：本阶段主要关闭 Agent、Skill、Schema、Harness、Tool、Compiler、Materializer、Publication、
  Test/Eval 或 Docs 中的哪一层。
- 删除清单：删掉或反转成 fail-closed 的旧 schema、fallback、默认字段、测试或文档口径。
- 证明：命令、测试文件、replay root、E2E root、产物路径或报告路径。
- 验证层级：明确标注 `logic/contract`、`real replay`、`E2E agent loop`、`product acceptance`
  哪些已完成、哪些尚未完成。

### Phase 0: 冻结旧逻辑清单和反向测试目标

实施目标：

- 把当前所有后置字段 ID 推断点列成删除清单。
- 把现有测试分为长期合同测试和旧兼容测试。
- 明确本次重构不提供 v1/v2 双 schema、不提供字段别名兼容、不保留 semantic lookup。

涉及文件：

- `src/docfit/fields/registry.py`
- `src/docfit/template/reading_packet.py`
- `src/docfit/tools/surface.py`
- `src/docfit/tools/schemas.py`
- `src/docfit/tools/service.py`
- `src/docfit/tools/__init__.py`
- `src/docfit/template/harness.py`
- `src/docfit/template/materialization/**`
- `src/docfit/template/materialization/handlers/**`
- `src/docfit/template/artifact.py`
- `src/docfit/styles/**`
- `src/docfit/content/fill.py`
- `src/docfit/content/student_content_fill.py`
- `src/docfit/app/prepare_template.py`
- `evals/template-extraction/**`
- `.claude/skills/docfit-school-extract/**`
- `docs/contracts/**`
- `docs/modules/**`
- `docs/agents/**`
- `docs/plans/**`
- `tests/contract/**`
- `tests/unit/**`
- `tests/integration/**`

验收标准：

- `rg` 级别有一份 allowlist，说明哪些 `field_id` 字符串只允许出现在 Registry fixture、
  contract fixture 或 pre-input vocabulary builder。
- 所有断言 `semantic_field`、`registry_field_no_candidates`、旧 `registry_field` 绑定、
  old alias、fallback default 的测试被标为待删除或待反转。
- 没有开始改 runtime 行为；只形成准确迁移清单。

验证层级：

- `logic/contract`：源码和测试清单审计。

### Phase 1: 建 PreInputFieldVocabulary 和 UnitReadingPacket 输入工作面

实施目标：

- 在 `prepare_template_task` 之后、Agent post-unit 语义判断之前，生成字段 ID 词表。
- 词表必须来自当前 task input 的 Registry snapshot，包含 Registry identity、sha256、
  `allowed_field_ids`、field label、content_type、cardinality、parent relation 和 usage affordance。
- 词表作为 Agent 输入工作面的一部分进入 startup brief 和每个 unit evidence packet。
- Agent 输入前只生成 `reading_block_id` / `range_id` 和可见文本；不生成 Agent 可写的 `span_id`。
- Agent 后续只能引用已有 reading block / range，并对其中可见文本输出有序 semantic parts。
- 未来 fill-contract slot identity 来自 Harness 解析出的 `slot_ref = span_ref + field_id`；
  发布槽位不得由 materializer 临场生成业务 `slot_id`。

验收标准：

- 任一 post-unit prompt / unit packet 都能看到 `field_id_vocabulary` 和 `field_vocabulary_digest`。
- Agent 输入中可见的字段 ID 集合与 task input Registry snapshot 完全一致，或与预定义的确定性可用子集一致。
- Harness 能读取同一 digest 并保存为 phase review 的验证基线。
- `reading_block_id` / `range_id` 和可见文本都在 Agent 语义判断前生成。
- Agent 输入和 schema 中都没有 `span_id`。
- 没有 `semantic_field` 或 query 才能获得字段候选的路径。

验证层级：

- `logic/contract`：packet schema、digest、字段集合一致性测试。
- `real replay`：真实 task root 重新构造 packet，检查 field vocabulary、reading block/range refs
  和可见文本已落盘。

### Phase 2: 重写 Agent 输入合同和 Skill

实施目标：

- Agent output 只保留一个字段绑定形状，例如：

```yaml
semantic_judgments:
  - scope:
      reading_block_id: <input reading block id>
    parts:
      - text: <visible text segment>
        role: fixed_label | fill_slot | body_structure | generated_content | manual_region | style_only | cleanup
      - text: <visible text segment>
        role: fill_slot
        field_id: <allowed field id>
```

- 删除旧字段别名和旧兼容字段：
  - `semantic_field`
  - `registry_field`
  - `registry_field_id`
  - `bound_field_id`
  - `bound_field_ids`
  - `required_field_ids`
  - `generated_field_id`
  - Agent-authored `judgment_id`
- Agent 不输出 `span_id`、`slot_id`、`intent_id` 或 content-control tag。
- 复合槽位必须在一个 typed judgment 的 ordered parts 内声明同一 block/range 中的多个
  `role=fill_slot` part，不能靠多个重叠 judgment 合并。
- body/generated 字段也只能从输入词表选择；Skill 不再把 `body.chapters`、`generated.toc` 写成硬编码示例。
- Agent 不再调用 Registry lookup 来寻找 field ID；如字段不在输入词表中，只能输出非可执行语义或
  `needs_input`。

验收标准：

- post-unit output schema 中不再出现旧字段名。
- prompt 不再出现“when known / semantic_field / registry lookup is needed”这类后置查字段指令。
- Skill / Reference 只要求 Agent 从已给 `field_id_vocabulary` 选择。
- Agent 输出未知 field ID、旧字段形状、`span_id` 或 Agent-authored ID 时，Harness 返回 revision packet。

验证层级：

- `logic/contract`：prompt/schema/Skill contract tests。
- `E2E agent loop`：真实 accepted unit resume 中，Agent 能按新 schema 输出字段绑定或明确 `needs_input`。

### Phase 3: Harness 字段词表门和语义覆盖门

实施目标：

- Harness phase review 必须同时验证：
  - 每个 `field_id` 都属于本轮 Agent 输入词表；
  - 每个需要字段的 typed judgment 都有 `field_id`；
  - 每个 scope ref 都属于本轮输入的 `reading_block_id` / `range_id`；
  - 每个 Agent part 都能由 HarnessSpanResolver 无歧义映射到 Word runs/ranges；
  - 每个 coverage-required reading block / range 都有且只有一个语义 owner；
  - 复合槽位在一个 owner 的 ordered parts 内表达多个 fill-slot parts，不产生重复 judgment；
  - overlap、遗漏、未知引用、互斥语义冲突全部 fail closed。
- Harness 保存 accepted semantic set 时，保留 `field_vocabulary_digest`、`reading_packet_digest`、
  source packet digest 和 `resolved_spans`。
- Harness 不再解析旧字段别名，不再接受 `registry_field_no_candidates` sentinel。

验收标准：

- 引用 Registry 中存在但未进入当前词表的 field ID 会失败。
- 缺 field ID 的 fill slot/body structure/generated content 会失败。
- 旧 schema 字段会失败，不会被 normalize 成新字段。
- Agent 输出 `span_id` 会失败；span 只能由 Harness 根据 ordered parts 解析。
- 对象映射由 Harness 执行；Agent 不能输出 locator、object_ref、target_ref、fingerprint 或 hash。
- reading block coverage 的结果能回答：遗漏、重复、冲突分别在哪里，责任层是什么。

验证层级：

- `logic/contract`：Harness 单元和合同测试。
- `real replay`：真实 inventory + 人工构造的非法/缺失/重复 semantic judgments 回放。

### Phase 4: 删除 Registry semantic search 和 Tool 后置查字段路径

实施目标：

- `docfit_evidence focus=registry_field` 不再向 Agent 提供 `semantic_field` / `query` 搜索。
- Runtime Agent 不再通过 tool 获取字段候选；候选在 Phase 1 已输入。
- `FieldRegistrySnapshot.search()` 若仍保留，只能用于离线研发/诊断或 pre-input builder 的内部工具，
  不能被 Agent runtime、Harness feedback、compiler、handler 调用。
- 旧错误码 `registry_field_semantic_field_missing`、`registry_field_no_candidates` 删除或只保留为
  历史迁移文档中的非运行时文字。

验收标准：

- `src/docfit/app`、`src/docfit/tools`、`src/docfit/template` 中没有 Agent runtime 可达的
  `semantic_field`、`query` 字段查找路径。
- Harness feedback 不再建议“call registry_field with semantic_field”。
- 旧 tool tests 被删除或改成断言该路径不可用。

验证层级：

- `logic/contract`：Tool surface/schema tests、feedback sanitizer tests。

### Phase 5: Readiness / compiler 改为 typed-only，删除硬编码字段默认

实施目标：

- readiness 只检查 typed semantic judgments，不根据自然语言推断 slot/body/generated intent。
- compiler 只消费 Harness accepted typed fields 和 Harness-resolved `span_ref`。
- 删除所有字段 ID hardcode default：
  - `generated.toc`
  - `body.chapters`
  - `body.heading.outline*`
  - `body.paragraph`
  - 其它 body/generated/section 字段
- body structure 合法性从输入词表及 Registry parent/usage metadata 判断；代码常量只能作为测试 fixture
  或预输入词表派生结果，不作为 runtime 字段来源。
- TOC、list of figures/tables 等 generated content 的字段也必须由 Agent 从输入词表选择；没有选择就
  fail closed 或 `needs_input`。

验收标准：

- 删除字段后，readiness/compiler 不会自动补回任何默认 field ID。
- 改写旧测试：自然语言里提到 title、TOC、body、outline 等不会产生 field ID。
- 编译计划中的每个 field ID 都能追到 accepted judgment 的 field binding，再追到 pre-input vocabulary。
- `rg` 检查 runtime 源码中没有 hardcoded field ID default；必要 fixture 走 allowlist。

验证层级：

- `logic/contract`：readiness/compiler tests。
- `real replay`：真实 TOC/body/cover/proposal semantic judgments 在删除 fallback 后仍能靠 typed output 通过。

### Phase 6: Materializer / handler / publication 删除运行时 ID 生成

实施目标：

- materializer 不生成 `slot_id`、`intent_id` 或新的 content-control tag 业务 ID。
- published slot identity 复用 HarnessSpanResolver 生成的
  `slot_ref = {reading_block_id/range_id, part_index, field_id}`。
- content control alias 只能是 accepted `field_id`；tag 只能是 `slot_ref` 的机械字符串序列化，
  例如 `rb001.p02.advisor.name.zh`，或其明确定义的非 ID locator carrier。
- handler 只消费 typed plan；label、prefix、content type、style policy 从 Registry field metadata 或
  accepted plan 中读取，不通过硬编码字段表决定语义。
- publication 不再只信任 SDT alias + Registry lookup；必须交叉验证 final DOCX 中每个 slot 都来自：
  - accepted semantic judgment；
  - pre-input field vocabulary；
  - Harness-resolved `span_ref` / `slot_ref`；
  - materialization receipt。
- fill-contract 只发布通过上述交叉验证的 slots。

验收标准：

- `fill-contract.yaml` 不再发布旧业务 `slot_id`；如外部格式必须保留字符串字段，字段语义必须迁移为
  `slot_ref` 的机械序列化，且每个值都能追到 Harness-resolved `slot_ref`。
- 每个 `field_id` 都能追到 Agent 输入词表和 accepted judgment。
- 删除或重写 `_slot_id()`、digest tag、operation/intent synthetic ID 逻辑。
- duplicate tag、unknown alias、orphan content control、receipt missing source 全部 fail closed。

验证层级：

- `logic/contract`：handler/publication/fill-contract tests。
- `real replay`：真实 candidate DOCX publish 后，每个 slot 都有完整 provenance。

### Phase 7: Contract、模块文档和 ADR 迁移

实施目标：

- 将长期有效结论迁移到：
  - `docs/contracts/template-extraction.md`
  - `docs/modules/template-extraction.md`
  - `docs/agents/ai-coding-boundary-guardrails.md`
  - 必要时新增 ADR
- `docs/plans/template-semantic-quality-gate-repair-plan.md` 中仍保留的 `registry_field`、
  `body.chapters` 示例和 semantic lookup 口径，要么标为历史，要么迁移成新合同。
- `docs/plans/docfit-content-field-registry/DESIGN.md` 保持 Registry 作为字段来源，但不被误读为
  Agent 输入面已经完成。

验收标准：

- 默认阅读路径中的长期文档都表达同一边界。
- 没有文档继续指导 Agent 或 handler 通过自然语言找字段。
- 计划完成后，本计划可降级为历史计划，长期规则已迁移。

验证层级：

- `logic/contract`：文档 lint / forbidden phrase scan。

### Phase 8: 真实链路验收矩阵

实施目标：

- 证明重构后不是单元逻辑自洽，而是真实模板输入可用。

验收输入：

| 输入 | 覆盖重点 |
| --- | --- |
| `01-cover` 或非封面字段页 | 单字段 slot、复合 slot、label carrier、样例值删除 |
| `03-toc` | generated content 字段选择、TOC source family、不可手填区域 |
| `04-paper-body` | body structure、heading/paragraph members、多正文候选选择、非正文 slot 拦截 |
| `06-proposal` / 开题报告表格 | manual region、整表保留、子 slot 拦截 |
| HUNAU / NJAU / PKU 三校真实 logical units | 跨学校 Registry vocabulary 与 span provenance 稳定性 |

每个输入都要完成：

- `logic/contract`：相关规则有测试。
- `real replay`：真实 task root + 真实 inventory + accepted/revised semantic judgments 回放。
- `E2E agent loop`：真实 Agent 在看到字段词表和 span 工作面后能输出 accepted semantic set 或
  `needs_input`。
- `product acceptance`：最终 `final-template.docx`、`fill-contract.yaml`、receipt/report 中的 field/span
  provenance 可检查。

最终通过标准：

- 没有任何 runtime 后置创建、猜测或补造字段 ID 的路径。
- 没有旧 schema 兼容路径。
- 没有 handler/materializer/compiler 根据文本、label、reason、role、handler feedback 或 fallback 补字段。
- Agent 输出所有 field IDs 都来自输入词表。
- Agent 不输出 `span_id`；所有 published slots 都能追到输入词表、Agent ordered parts 和
  Harness-resolved `span_ref` / `slot_ref`。
- 真实 replay 与 E2E agent loop 均通过；单元测试通过不能单独作为真实链路完成证明。

## 5. 必删 / 必封 / 必迁移清单

| 对象 | 当前问题 | 处理方式 |
| --- | --- | --- |
| `semantic_field` / `query` | Agent 后置查字段候选 | 删除 runtime surface；只允许 pre-input vocabulary |
| `registry_field` / `registry_field_id` / `bound_field_id(s)` | 多套旧字段形状，Harness normalize 兼容 | 删除旧 schema；新 schema 只保留规范 `field_id(s)` / `field_bindings` |
| `registry_field_no_candidates` | 把查不到候选当成可携带状态 | 删除；字段不在词表时只能 `needs_input` 或非可执行语义 |
| `FieldRegistrySnapshot.search()` runtime 调用 | 根据文本、label、alias 推候选 | 从 Agent runtime 和 feedback 路径移除 |
| `generated.toc` hardcode | generated 字段后置硬要求 | 仅作为 Registry 输入词表项出现；Agent 不选就不自动补 |
| `body.chapters` hardcode/default | body 结构后置默认 | 仅作为 Registry 输入词表项出现；runtime 不默认 |
| `semantic_types.py` 字段 catalog | 代码内字段 ID 词表 | 从 Registry 派生或改成非 ID 分类校验；不能作为来源 |
| `_slot_id()` / digest content-control tag | materializer 运行时生成发布 slot ID | 改为 `slot_ref` 机械序列化；`slot_ref` 由 HarnessSpanResolver 从 reading ref、part_index 和 field_id 生成 |
| Agent-authored `judgment_id` | Agent 生成新的追踪 ID | 删除；用数组 path + Harness-resolved `span_ref` 追踪 |
| compiler/readiness prose inference | 根据自然语言推 intent/field | typed-only；缺字段 fail closed |
| handler 字段特例表 | 字段 label/prefix/pattern 影响语义 | 语义部分迁到 Registry/input affordance；handler 只渲染 |
| publication alias-only acceptance | 最终 DOCX alias 存在于 Registry 即通过 | 增加 accepted judgment + vocabulary + span provenance 交叉验证 |

## 6. 验收口径

本计划的验收必须按层级汇报：

| 层级 | 可以证明什么 | 不能宣称什么 |
| --- | --- | --- |
| `logic/contract` | schema、Harness gate、compiler、handler、publication 规则正确 | 不能宣称真实模板输入跑通 |
| `real replay` | 真实 task root / inventory / semantic judgments 可回放 | 不能宣称 Agent feedback 闭环可用 |
| `E2E agent loop` | Agent 看到词表后能完成或返回 `needs_input` | 不能替代最终 DOCX 人工/产品验收 |
| `product acceptance` | final-template、fill-contract、receipt/report 可依赖 | 不能证明未来 Registry 新版本无需再验收 |

完成时最终汇报必须说明每个层级是否完成。只跑单元测试、contract test 或 mock replay 时，不得写
“真实输入跑通”“完整跑通”或“端到端通过”。

## 7. 停止条件

本计划完成的必要条件：

- pre-input vocabulary、`reading_block_id` / `range_id` 和可见文本已进入 Agent 输入面。
- Agent schema 没有旧字段 ID 别名和 Agent-authored ID。
- Agent schema 不允许 `span_id`；span 语义拆分只用 ordered parts 表达。
- Harness 验证 field ID 来源于本轮输入词表，而不是只验证 Registry 存在。
- HarnessSpanResolver 把 ordered parts 映射到底层 Word runs/ranges，并记录 `span_ref` / `slot_ref`。
- Harness 验证所有 required reading block / range / resolved span 的语义 owner、字段绑定、遗漏、
  重复和冲突。
- Tool runtime 不再提供 semantic field search。
- readiness/compiler/materializer/handler 不再根据文本、label、reason、role、handler 或 fallback
  推字段 ID。
- publication/fill-contract 对每个 slot 做 vocabulary + accepted judgment + span provenance
  交叉验证。
- source-noop 只能来自 accepted `manual_region` / 非执行 ordered parts；原始 DOCX 的物理 publishability
  不能绕过 Harness semantic provenance。
- 旧兼容测试已删除或反转为 fail closed。
- `real replay`、`E2E agent loop` 和 `product acceptance` 均有真实路径证据。

## 8. 当前实施进度

更新日期: 2026-09-04

已完成:

- Phase 0 `logic/contract` 审计证据已落盘到
  `docs/plans/template-field-id-vocabulary-boundary-migration-inventory.md`。
- Phase 1 的首个 `logic/contract` 切片已实现：`FieldRegistrySnapshot` 可从当前 Registry snapshot
  派生 `docfit_pre_input_field_vocabulary_v1`，`unit_evidence_packet` 会在有 task Registry 时向
  Agent-visible packet 暴露 `field_id_vocabulary` 和 `field_vocabulary_digest`，Harness inventory /
  semantic judgment receipt 会记录同一词表基线。本轮已补
  `usage_affordance.allowed_part_roles`，从 Registry metadata 派生每个字段可用于
  `fill_slot`、`body_structure`、`generated_content` 还是当前没有可执行 part role；Agent 不再只
  看到裸 `allowed_field_ids`。
- Phase 2 的 `logic/contract` 切片已实现：post-unit structured output schema 只暴露
  `scope + parts[]`，runtime prompt / Skill / Reference / Contract 都要求从 pre-input
  `field_id_vocabulary` 选择字段；Agent-visible materialization feedback 会把旧 readiness
  blocker sanitize 成 ordered-parts / field-vocabulary 语言，不再要求 `semantic_field`、
  `registry_field`、`semantic_parts`、`toc_contract`、`generated_field_id`、Agent-authored
  `judgment_id` 或 covered-span 旧形状。通过 gate 的 ordered parts 会先投影给当前覆盖检查，
  作为后续 `HarnessSpanResolver` 和 typed-only downstream 的迁移中间态。
- Phase 3 的首个 `logic/contract` 切片已实现：Harness 在 accepted semantic set 写入前会按
  scoped reading block / range 文本顺序解析 ordered parts，生成结构化 `span_ref`；带 `field_id`
  的 part 生成机械序列化 `slot_ref`，并拒绝未覆盖的非空文本 gap。本轮已修正
  `reading_range_id` 只映射最后一个 block 的问题：同一 range 现在按 inventory 顺序聚合多个
  reading block，resolved span 会落回对应 block/object，同时保持 range-scope `span_ref` /
  `slot_ref`。本轮继续补齐 `order` 保留链路：`reading_block_mappings` 到 Harness inventory
  不再丢失 `reading_blocks[].order`；materialization context 对旧落盘 inventory 也只用数组顺序补
  内部执行顺序，不要求 Agent 生成任何排序 ID。
- Phase 4 的 `logic/contract` 切片已实现：`docfit_evidence` 的 Agent-visible focus enum 和 schema
  不再包含 `registry_field` / `semantic_field`；即使绕过 schema 直接调用，service 也会在读取
  source 或 Registry 前返回 `registry_field_runtime_removed`，不再执行 Registry semantic search。
  Tool/Harness feedback 不再建议通过 `focus=registry_field` 或 `semantic_field` 获取候选字段。
- Phase 5-6 的本轮 `logic/contract` 清理已推进：Registry runtime search / alias helper 已删除；
  Harness 不再 normalise Agent-authored object / locator / covered-span coverage 输入；compiler /
  readiness 只消费 `scope + parts + resolved_spans`，旧字段别名、旧 coverage 字段、Agent-authored
  `judgment_id` / `span_id` / `slot_id` / `intent_id` 只作为 fail-closed denylist；materialization
  plan / context / handler / receipt 的运行时追踪名已从 `*_id` 迁成 `*_ref`；`docfit_apply`、
  publication、style handoff、fill-contract、student placement 的 slot identity 已迁为
  Harness-derived `slot_ref`；`semantic_types.py` 代码字段目录已删除，body/generated 字段只能来自
  accepted ordered parts 和 Registry metadata。body handler 不再读取 legacy
  `variant_id` / `variant_role`；单个连续正文代表集合可以由多个新协议 scoped judgments 机械汇总，
  多个非连续 body_structure 候选必须在 readiness 阶段退回 Agent 选择。
- Phase 6 publication 的孤儿槽位门已收紧：候选 DOCX 中只要出现 Registry alias，就不能再被
  publication 当作学校原始 SDT 静默跳过；它必须同时携带匹配的 Harness `slot_ref`，否则
  `publication_slot_protocol_status` 和最终 `publish_template_artifact` 都 fail closed。这个
  `logic/contract` 切片防止 fill-contract 只发布部分合法 slot、同时漏掉 alias-only 残留。
- Phase 5-6 的 readiness / materializer fail-closed 门已补齐：`shadow_intent_plan` 只要存在
  `unsupported`，`materialization_readiness_feedback` 就必须把 blocker 退回 Agent，runtime
  自身也会在写 candidate 前抛出 `template_materialization_readiness_incomplete`。这关闭了
  `04-paper-body` 暴露的漏洞：已接受的 `body_structure` span 若缺少可执行结构字段组、或同一
  reading block 产生多个正文结构成员，不能被 materializer 静默跳过，也不能等到 publication
  provenance 才发现。runtime 还增加了 body_structure 后置门禁：ready plan 若存在正文结构 intent
  但 handler 没产出 `materialize_structure` 操作，直接 `body_structure_materialization_unexecutable`。
- Phase 3/5-6 的 whole-unit body range 缺口已补齐：unit reading packet 现在给每个可见
  reading block 附带 Harness-owned `unit_range_id`，并在 `reading_ranges[]` / Tool summary 中暴露
  whole-unit `range_id`；Harness、readiness 和 materialization context 都把它作为合法
  `scope.reading_range_id` 索引，同时保留 block-local `range_id`。从 unit-boundary checkpoint
  resume 到 post-unit 时，inventory 会给跨 unit reading blocks 重新分配全局顺序，避免正文
  structure gap 被 per-unit `order` 重置误判。body handler 只允许跨过同一 accepted whole-unit
  judgment 中标为 `cleanup` 的 block，并用 Harness `span_ref` receipt 记录清理，不创建或猜测字段 ID。
- Phase 7 的本轮 `logic/contract` 清理已推进：Contract、Skill 和 prepare-template prompt 不再指导
  runtime Registry lookup、字段 fallback 或旧 wrapper 兼容；相邻反馈 sanitizer 测试已反转为
  field-vocabulary / ordered-parts 语言。
- Phase 2/7 的 Agent-facing Skill tree 已收紧为 vocabulary-only：`docfit-school-extract` 的正文、
  目录、模板文字分类、集合/附录/致谢和 Registry 绑定 references 不再给出
  `advisor.name.en`、`submission.date`、`generated.toc`、`body.chapters`、`body.heading.*`、
  `body.paragraph`、`references.entries`、`acknowledgement.body`、`appendix.*` 这类 canonical
  字段 ID 示例；只描述如何从当前 `field_id_vocabulary` 中选择允许对应 role 的字段。合同测试
  `tests/contract/test_skill_contract.py::test_school_extract_skill_tree_does_not_seed_canonical_field_ids`
  固定该边界。
- Phase 7 文档边界已继续收敛：`docs/agents/ai-coding-boundary-guardrails.md` 的优先迁移点已改成
  `scope + ordered parts + field_id_vocabulary`；ADR 0002 的字段来源口径已改为 Harness-accepted
  parts；ADR 0003 和旧 `template-semantic-quality-gate-repair-plan.md` 已标记为 superseded
  historical context，不再作为旧 `registry_field` / `covered_reading_block_ids` schema 的当前执行依据。
- post-unit reading packet / inventory 的空白版式输入面已收紧：无可见文本的段落进入
  `layout_context`，不再进入 Agent 必须输出非空 ordered parts 的 semantic coverage 面；从
  unit-boundary checkpoint 构造 post-unit inventory 时，只纳入 reading block mapping 覆盖到的
  对象，避免要求 Agent 为无文本版式段落编造语义。
- Phase 8 的 `01-cover` 切片已推进到三层证据：
  - `real replay`：`temp/field-id-vocab-boundary-current-cover-product-20260903-120046` 用当前
    HEAD 复用真实 cover checkpoint/inventory，Harness 接受 16 个 judgments / 24 个 resolved
    spans，机器发布 9 个 slots；materialization 和 fill-contract 扫描无 `slot_id` / `intent_id` /
    `judgment_id` 等旧输出字段。
  - `E2E agent loop`：`temp/field-id-vocab-boundary-cover-live2-20260903-120309/run`
    从真实 0820 `01-cover` 输入运行 live Agent，unit-boundary 和 post-unit checkpoint 均为
    `ok`；post-unit receipt 记录 16 个 judgments、97 个 objects、16 个 reading blocks、29 个
    resolved spans 和同一 `field_vocabulary_digest`。
  - `product-provenance`：同一 live root 复用 accepted post-unit checkpoint 发布
    `output/final-template.docx` 和 `output/fill-contract.yaml`；fill-contract 有 6 个 slots，
    全部 field_id 在输入词表内，全部 slot_ref 能回到 Harness resolved span 和 provenance；
    当前 YAML/JSON 产物扫描无旧字段 ID 协议残留。
- Phase 8 的 `03-toc` 切片已补到 live E2E + product-provenance：
  - `E2E agent loop`：`temp/field-id-vocab-boundary-toc-live-20260903-123117/run`
    从真实 0820 `03-toc` 最小输入运行 live Agent；unit-boundary checkpoint 为 `ok`，
    3 个目录子单元，post-unit checkpoint 为 `ok`，Harness 接受 28 个 judgments、
    83 个 objects、28 个 reading blocks。Agent 输出的 generated-content 字段均来自
    输入 `field_id_vocabulary` 中的 `generated.toc`。
  - `product-provenance`：同一 root 复用 accepted post-unit checkpoint 发布
    `output/final-template.docx` 和 `output/fill-contract.yaml`；这是 generated-only
    no-slot 产物，fill-contract `slots=[]`，style capture 为 `skipped`，materialization
    receipt 记录 22 个 `generated_content` policy receipts，均含 `source_judgment_refs`、
    `field_ids=["generated.toc"]` 和 Harness `span_refs`，不伪造 fill slot `slot_refs`。
  - `logic/contract`：generated-only candidate 以 `allow_no_slots=True` 通过 publishability，
    但 `fill_slot` / `body_structure` 仍要求发布槽位；`generated_content` policy receipt
    记录字段和 span provenance。相关测试：
    `tests/contract/test_publication_style_handoff.py::test_o1_host_candidate_selection_allows_generated_only_candidate_without_slots`
    和
    `tests/contract/test_template_materialization_runtime.py::test_materializer_generated_content_policy_receipt_tracks_field_provenance`。
- Phase 8 的 `06-proposal` 切片已补到 live E2E + product-provenance：
  - `E2E agent loop`：`temp/field-id-vocab-boundary-proposal-live-20260903/run`
    复用同 hash 0820 accepted unit-boundary proof 跑真实 post-unit Agent，得到
    19 个 judgments、23 个 objects、19 个 reading blocks；semantic roles 只有
    `fixed_label` 和 `manual_region`，没有任何 Agent field_id。
  - `product-provenance`：同一 root 直接发布
    `output/final-template.docx` 和 `output/fill-contract.yaml`；这是 terminal/manual
    no-slot source-noop 产物，fill-contract `slots=[]`，style capture 为 `skipped`，
    OfficeCLI OpenXML validation 为 `ok`。发布产物、fill-contract、build-report 和 accepted
    semantics 扫描无 `slot_id`、`intent_id`、`judgment_id`、旧 coverage 字段、
    `semantic_field` / `registry_field`、`toc_contract`、`generated_field_id`、
    `variant_id` / `variant_role`、`object_ref` 或 `fingerprint`。
  - `product acceptance`：未完成。fill-contract 仍标记
    `candidate_pending_human_acceptance`，且完整全页 visual review 未完成。
- Phase 8 的 `04-paper-body` 切片已暴露真实 blocker，并已改成正确 fail closed：
  - `E2E agent loop` blocker：`temp/field-id-vocab-boundary-body-live-20260903-124457/run`
    用真实 0820 `04-paper-body` 输入从空 task root 跑 `--until unit-boundary` 两次，均停在
    `template_agent_no_progress_timeout`。Agent 只读取 document map 分页后未在 180 秒内产出
    tool call 或 structured result；因此不能宣称 live unit-boundary 通过。
  - `real replay`：同一输入 hash 复用既有 accepted unit-boundary proof 后，post-unit live
    Agent 产出 53 个 judgments、228 个 objects、53 个 reading blocks。Harness 接受了
    ordered parts / resolved spans，但 shadow materialization plan 对 references、acknowledgement
    和 appendix 区段返回 11 个 unsupported blocker。
  - `logic/contract`：当前代码会在 materialization readiness 阶段返回
    `template_materialization_readiness_incomplete`，revision packet 的 affected codes 为
    `materialization_intent_unclassified` 和 `body_structure_field_group_incomplete`，且反馈扫描无
    `judgment_id`、旧 coverage 字段、`structure_ref` / `members`、`variant_id` / `variant_role`、
    `parent_field_id`、`object_ref`、`locator` 或 `fingerprint` 泄露。runtime 直接调用不再为
    not-ready plan 写 candidate。
  - `product acceptance`：未完成。`04-paper-body` 当前正确状态是可修复的 Agent 语义拆分输入，
    不是可发布的最终 DOCX / fill-contract。
- Phase 8 的 `04-paper-body` role-affordance live2 replay 已验证输入面改善：
  - `E2E agent loop`：`temp/field-id-vocab-boundary-body-live2-20260903-roles/run`
    复用同 hash unit-boundary proof 跑真实 post-unit Agent，得到 53 个 judgments、228 个
    objects、53 个 reading blocks。新的 `field_id_vocabulary.fields[].usage_affordance.allowed_part_roles`
    让 Agent 不再把 `references.entries`、`acknowledgement.body`、`appendix.title` 误标成
    `body_structure`；这些字段在词表中分别只允许 `fill_slot`，`appendix.body` 当前无可执行 role。
  - `real replay`：同一 accepted post-unit 输出的 shadow plan 不再有 references / acknowledgement /
    appendix 的 parent-field blocker，但暴露了新的执行闭合问题：Agent 把理工和文法两套正文样例
    共 19 个块都标成 `body_structure`，形成两个非连续候选组。当前代码已改为：
    连续 body_structure intents 可由 materializer 按 Harness-resolved `span_ref` 机械汇总成一个
    `body.chapters` 结构；多个非连续候选组则在 plan validator / runtime readiness 阶段
    fail closed，不能由 handler 按文档顺序猜选，也不能等到 publication provenance 才失败。
  - `real replay` candidate selection：同一 live2 root 调用
    `_select_host_candidate_for_accepted_semantics` 返回
    `template_materialization_readiness_incomplete`；`agent_revision_packet.affected[0]` 只暴露
    `reading_block_ids`、`reading_blocks[].block_id/range_id/unit_id/text` 和新协议消息，扫描无
    `judgment_id`、旧 coverage 字段、`structure_ref` / `members`、`variant_id` / `variant_role`、
    `object_ref`、`locator` 或 `fingerprint`。
  - `product acceptance`：仍未完成。下一步需要让 Agent 根据 revision packet 只保留一套正文代表
    结构，或返回 `needs_input`；完成前不能发布 `04-paper-body` 最终 DOCX / fill-contract。
- Phase 8 的 `04-paper-body` 已补到 live7 E2E + product-provenance：
  - `regression real replay`：`temp/field-id-vocab-boundary-body-live5-20260903-fullpass/run`
    的真实 Agent 输出曾被 Harness 接受但 publication 停在 `published_slot_receipt_missing`。
    归因后确认不是字段推断问题，而是同一正文 heading block 被拆成多个带同字段的
    `body_structure` parts，旧 plan validator 去重 block 后漏过执行性检查。当前代码对该真实
    persisted semantics 的 real replay 返回 `template_materialization_readiness_incomplete`，
    blocker 为 `materialization_body_structure_member_block_ambiguous`，且不写 candidate。
  - `E2E agent loop`：`temp/field-id-vocab-boundary-body-live7-20260903-source-text-feedback/run`
    从真实 0820 `04-paper-body` 输入和 accepted unit-boundary proof 运行 live Agent；
    `sdk_query_count=3`，`harness_feedback_attempts=2`，`semantic_feedback_attempts=2`。
    首轮缺覆盖、二轮 span text 精确匹配失败后，Harness feedback 暴露 `scoped_text` /
    `submitted_text`，Agent 修正弯引号和正文 member 拆分，第三轮 Harness accepted。
  - `real replay` / `product-provenance`：同一 root 写出
    `work/.docfit/post-unit-materialization/candidate-0001.docx`、`output/final-template.docx` 和
    `output/fill-contract.yaml`；materialization `status=ok`，`operation_count=17`，
    `cleanup_count=18`，`receipt_count=35`，handlers 覆盖 `body_structure`、`slots`、
    `fixed_content`。body_structure receipt 含 `body.chapters`、正文成员字段、Harness
    `span_refs` 和 `slot_refs`。
  - `product acceptance`：同一 root 的 publication slot protocol 为 `ok`，`slot_count=26`；
    Agent 53 个 judgments 中 25 个 field_id 全部来自输入 `field_id_vocabulary`，Agent 输出无
    `span_ref` / `slot_ref` / `object_ref` / 旧 coverage 字段；Harness persisted semantics 有
    72 个 resolved spans、无重复 body_structure block；fill-contract 扫描到的字段全部在输入词表内。
- Phase 8 的 HUNAU / NJAU / PKU 代表 logical unit live provenance matrix 已补齐：
  - `E2E agent loop`：`temp/field-id-vocab-boundary-three-school-live-20260903/hunau-cover`、
    `temp/field-id-vocab-boundary-three-school-live-20260903/njau-abstract-cn` 和
    `temp/field-id-vocab-boundary-three-school-live-20260903/pku-abstract-cn` 分别使用三校真实
    logical-page DOCX 与 Registry v0.5 从空 task root 运行 `prepare-template`，均返回
    `status=built` 并发布 `output/final-template.docx` / `output/fill-contract.yaml`。三次 live
    Agent 均为 `num_turns=2`；session 分别为
    `b8b564c3-cadb-4abb-91cc-fb3e063fdfda`、
    `55d9db8e-65f2-4515-b137-7f8a5bd7fc25`、
    `9ee2c4f9-ec22-4152-8961-6da339ed606b`。
  - `product-provenance`：结构化扫描三校 `template-agent-execution.json`、
    `semantic-judgments.json`、`materialization.json`、`build-report.json` 和
    `fill-contract.yaml`，确认 Agent 原始输出没有 `semantic_field`、`registry_field`、
    `span_id`、`slot_id`、`intent_id`、`judgment_id`、旧 coverage 字段、`object_ref`、
    `locator`、`fingerprint` 等旧协议；Agent / materialization / fill-contract 中所有
    `field_id` 均属于同一输入 `field_id_vocabulary`。
  - `product acceptance`：三校主交付物均通过 publication `status=ok`，`package_reopens=ok`，
    `fill_contract_hash_matches_word=ok`。主 `slots` 数分别为 HUNAU 8、NJAU 3、PKU 1；
    字段分别覆盖 HUNAU 封面字段、NJAU `thesis.title.zh` / `abstract.zh` / `keywords.zh`、
    PKU `keywords.zh`。`docfit tools validate` 的 ZIP/XML 与 OfficeCLI OpenXML 检查通过，
	  但完整全页 visual review 仍因本机 `visual_renderer_unavailable` 未完成。
- Phase 8 的 HUNAU `02-integrity-statement` / `05-design-task` 缺口 logical units 已补到
  live source-noop product-provenance：
  - 归因和修复：最初 180s 阈值下两者停在 `template_agent_no_progress_timeout`。使用
    `DOCFIT_PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS=600` 隔离重试后，Agent 能产出
    unit-boundary proposals，但 Harness 暴露 `invalid_unit_ranges`：结构边界 resolver 为首个
    unit 向前扩展时选中了无可见文本、也不在 coverage 面上的页首空段落。当前
    `src/docfit/tools/service.py` 只把首个 unit 起点扩展到第一个可覆盖的结构候选；合同测试
    `tests/contract/test_docfit_check_tool.py::test_t2_unit_coverage_skips_blank_leading_structural_boundary`
    锁住该行为。
  - `02-integrity-statement`：`temp/field-id-vocab-boundary-hunau-missing-live-20260903/02-integrity-statement/run-long600-skill-manual`
    用新 Skill 语义规则从 clean input 跑完整 `prepare-template`，返回 `status=built`。unit-boundary
    `unit_count=1`；post-unit trace `num_turns=2`、`sdk_query_count=4`、
    `harness_feedback_attempts=2`、`semantic_feedback_attempts=2`，session
    `cfa4a6ea-0de3-4a94-a1a8-3d1af23aaebc`。accepted semantics 有 5 个 judgments /
    5 个 resolved spans，roles 为 `fixed_label=3`、`manual_region=2`，无 `field_id`。
    publication 走 manual terminal source-noop，`counts.manual=1`、`slot=0`，
    `fill-contract.yaml` 的 `slots=[]`；Agent / semantics / build / fill-contract 扫描无旧字段别名、
    旧 coverage 字段、Agent-authored `span_id` / `slot_id` / `intent_id` / `judgment_id`。
    `docfit tools validate` 的 ZIP/XML reopen 和 OfficeCLI OpenXML 为 `ok`；完整 visual review
    coverage 仍未完成。
  - `05-design-task`：`temp/field-id-vocab-boundary-hunau-missing-live-20260903/05-design-task/run-long600-fixed`
    从 clean input 跑完整 `prepare-template`，返回 `status=built`。unit-boundary `unit_count=4`；
    post-unit trace `num_turns=2`、`sdk_query_count=4`、`harness_feedback_attempts=2`、
    `semantic_feedback_attempts=2`，session `f272e3ff-ec63-4377-8635-1eef83b18d33`。
    accepted semantics 有 39 个 judgments / 39 个 resolved spans，roles 为
    `fixed_label=33`、`manual_region=6`，无 `field_id`。publication 走 manual terminal
    source-noop，`counts.manual=1`、`slot=0`，fill-contract `slots=[]`；旧协议扫描无命中。
    `docfit tools validate` 的 ZIP/XML reopen 为 `ok`，OfficeCLI OpenXML 为 source/final
    同类 backend warning，归类为 source-inherited 非新回归；完整 visual review coverage 仍未完成。
  - Skill 语义修复：`.claude/skills/docfit-school-extract/SKILL.md` 和
    `references/template-text-classification.md` 明确声明正文、作者签名和年月日骨架同属声明页终端
    人工区时应使用 `manual_region`，不复用日期字段，也不把整页拆成纯 `fixed_label`。合同测试
    `tests/contract/test_skill_contract.py` 已覆盖该规则。
- Phase 8 的 HUNAU `02-integrity-statement` through `05-design-task` current-hash logical units
  已补到 live E2E + product-provenance：
  - `02-integrity-statement`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-02-integrity-statement-vocabonly`
    使用当前 worktree hash 的真实 logical-page DOCX 跑完整 `prepare-template`，返回
    `status=built`。post-unit execution `status=complete`、session
    `fd937ab0-6ce6-46c4-bca7-a0e1b6fb8287`、`num_turns=2`、`sdk_query_count=4`、
    `semantic_feedback_attempts=2`。Harness accepted semantics 有 5 个 judgments /
    5 个 resolved spans，roles 为 `fixed_label=4`、`manual_region=1`，无 `field_id`；
    publication `counts.manual=1`、`slot=0`，fill-contract v2、`slots=[]`。旧协议扫描无命中。
    `docfit tools validate` 的 ZIP/XML reopen、OfficeCLI OpenXML、source unchanged、
    content preservation 和 placeholder scan 为 `ok`；visual review coverage 未完成。
  - `03-toc`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-03-toc-vocabonly`
    返回 `status=built`。post-unit execution `status=complete`、session
    `cc34150f-6723-44d8-8bf8-a5f1040acca6`、`num_turns=5`、`sdk_query_count=3`、
    `semantic_feedback_attempts=0`。Harness accepted semantics 有 28 个 judgments /
    29 个 ordered parts，roles 为 `cleanup=1`、`fixed_label=5`、`style_only=1`、
    `generated_content=22`；唯一字段 `generated.toc` 来自输入词表。materialization
    `status=ok`、`operation_count=0`、`cleanup_count=2`、`receipt_count=24`；
    publication generated-only no-fill-slot，fill-contract v2、`slots=[]`。旧协议扫描无命中。
    `docfit tools validate` 的 ZIP/XML reopen、OfficeCLI OpenXML、source unchanged 和
    placeholder scan 为 `ok`，content preservation 有 `missing_object_count=2` warning；
    visual review coverage 未完成。
  - `04-paper-body`：
    初始 current-hash root
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-04-paper-body-vocabonly`
    失败为 `body_structure_materialization_unexecutable`。归因确认 shadow plan validator
    用 whole range context 判断连续性，导致相邻的农理工科和文法经管两套互斥正文轨道被误判为
    ready；body handler 再因两套 member blocks 之间存在非 cleanup 的轨道说明而拒绝执行。当前
    `src/docfit/template/materialization/validators.py` 改为按 body member bindings 分组，只允许
    accepted `cleanup` blocks 填补 member gap；非 cleanup 轨道说明隔开的多个 candidates 在
    readiness 阶段 fail closed。合同测试
    `tests/contract/test_template_materialization_plan.py::test_shadow_plan_blocks_adjacent_alternate_body_range_candidates`
    固定该行为；同一修复对 NJAU `06-body` persisted semantics 仍返回 ready。
    修复后 root
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-04-paper-body-vocabonly-candidate-gate`
    返回 `status=built`，说明反馈进入真实 Agent loop 后 Agent 改成单一 executable body track。
    session `b5af353c-eac8-495f-bcd1-260010ffec4f`、`num_turns=2`、`sdk_query_count=4`、
    `semantic_feedback_attempts=2`；unit-boundary `unit_count=7`。Harness accepted semantics 有
    7 个 judgments / 86 个 ordered parts，其中只有 1 个 body_structure judgment，
    scope 为 `body:range-whole-unit`、19 个 body parts；所有 field IDs 均属于输入词表。
    materialization `status=ok`、`operation_count=15`、`cleanup_count=1`、`receipt_count=16`，
    actions 为 `materialize_structure=1`、`materialize_slot=14`；fill-contract v2、33 个 slots，
    全部为 Harness-resolved provenance。旧协议扫描无命中。
    `docfit tools validate` 的 ZIP/XML reopen、OfficeCLI OpenXML、source unchanged 和
    placeholder scan 为 `ok`，content preservation 有 `missing_object_count=32` warning；
    visual review coverage 未完成。
  - `05-design-task`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-05-design-task-vocabonly`
    返回 `status=built`；session `7e42a3ff-67e5-42d2-b8d7-aa5ba227447f`、`num_turns=2`、
    `sdk_query_count=4`、`semantic_feedback_attempts=2`。Harness accepted semantics 有
    3 个 judgments / 39 个 ordered parts，roles 为 `fixed_label=23`、`fill_slot=1`、
    `manual_region=15`；唯一字段 `author.cohort_class` 属于输入词表。materialization
    `status=ok`、`operation_count=1`、`receipt_count=2`；fill-contract v2、1 个 slot，
    provenance 为 Harness-resolved span。旧协议扫描无命中。`docfit tools validate` 的
    ZIP/XML reopen、source unchanged 和 placeholder scan 为 `ok`；OfficeCLI OpenXML 为
    source/final 同类 backend warning，content preservation 有 `missing_object_count=1` warning，
    visual review coverage 未完成。
- Phase 8 的 HUNAU `06-proposal` through `10-grade-form` current-hash logical units 已补到
  live E2E + product-provenance，HUNAU 当前 10/10 logical units 均有 built provenance：
  - `06-proposal`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-06-proposal-vocabonly`
    返回 `status=built`；session `54cb6e47-df21-479a-ab54-d19077fb5608`、
    `num_turns=2`、`sdk_query_count=6`、`semantic_feedback_attempts=4`。Harness accepted
    semantics 有 1 个 judgment / 19 个 ordered parts，roles 全部为 `manual_region`，无
    `field_id`；publication `counts.manual=1`、`slot=0`，fill-contract v2、`slots=[]`。
  - `07-proposal-record`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-07-proposal-record-vocabonly`
    返回 `status=built`；session `38db86e8-7f09-4655-9bae-4a1036b46c8a`、
    `num_turns=2`、`sdk_query_count=3`、`semantic_feedback_attempts=1`。Harness accepted
    semantics 有 1 个 judgment / 16 个 ordered parts，roles 全部为 `manual_region`，无
    `field_id`；fill-contract v2、`slots=[]`。
  - `08-defense-record`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-08-defense-record-vocabonly`
    返回 `status=built`；session `cf626c36-f848-4b94-af8d-bc6811d9eaa2`、
    `num_turns=2`、`sdk_query_count=5`、`semantic_feedback_attempts=3`。Harness accepted
    semantics 有 1 个 judgment / 16 个 ordered parts，roles 全部为 `manual_region`，无
    `field_id`；fill-contract v2、`slots=[]`。
  - `09-topic-change-approval`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-09-topic-change-approval-vocabonly`
    返回 `status=built`；session `4e685984-027f-49a0-b595-b4cedea77e35`、
    `num_turns=5`、`sdk_query_count=3`、`semantic_feedback_attempts=1`。Harness accepted
    semantics 有 16 个 judgments / 16 个 ordered parts，roles 为 `fixed_label=13`、
    `manual_region=3`，无 `field_id`；fill-contract v2、`slots=[]`。
  - `10-grade-form`：
    `temp/field-id-vocab-boundary-current-hunau-live-20260903/hunau-10-grade-form-vocabonly`
    返回 `status=built`；session `da4fd526-7da2-4d62-83bf-a465bc657f1c`、
    `num_turns=2`、`sdk_query_count=6`、`semantic_feedback_attempts=4`。Harness accepted
    semantics 有 1 个 judgment / 25 个 ordered parts，roles 全部为 `manual_region`，无
    `field_id`；fill-contract v2、`slots=[]`。
  - 这些 root 的 `work` / `output` 旧协议扫描均无命中。`docfit tools validate` 对
    `06-proposal` through `10-grade-form` 的 ZIP/XML reopen、OfficeCLI OpenXML、
    source unchanged、content preservation 和 placeholder scan 均为 `ok`；全部仍因缺少完整
    visual review coverage 不能算 product acceptance。
- Phase 8 的 NJAU `01-cover` through `05-abstract-en` front-matter logical units 已补到
  live E2E + product-provenance：
  - `01-cover`：
    `temp/field-id-vocab-boundary-more-live-20260903/njau-01-cover-vocabonly`
    用真实 NJAU 封面 logical-page DOCX 与 Registry v0.5 从空 task root 跑完整
    `prepare-template`，返回 `status=built`。post-unit execution `status=complete`、
    session `d1d0c8b2-3fb4-4a54-a38a-95c978974bbb`、`num_turns=4`、
    `sdk_query_count=5`、`semantic_feedback_attempts=3`。Harness accepted semantics 有
    10 个 judgments / 17 个 resolved spans，roles 为 `fixed_label=10`、`fill_slot=7`；
    字段为 `thesis.title.zh`、`author.name.zh`、`author.student_id`、
    `author.department`、`author.major`、`advisor.name.zh`、`submission.date`，全部属于输入词表。
    final fill-contract 为 v2、7 个 slots，均为 `provenance.source=harness_resolved_span`；
    旧协议扫描无命中。
  - `02-declarations`：
    `temp/field-id-vocab-boundary-more-live-20260903/njau-02-declarations-vocabonly`
    返回 `status=built`；unit-boundary `unit_count=2`。Agent accepted semantics 有
    2 个 judgments / 7 个 ordered parts，roles 全部为 `manual_region`，无 `field_id`、
    无 `slot_ref`。这是 source-noop/manual terminal 产物，未写
    `post-unit-materialization/materialization.json`，publication `counts.manual=1`、`slot=0`，
    fill-contract v2、`slots=[]`；旧协议扫描无命中，且 `docfit tools validate` 的
    content preservation 为 `ok`。
  - `03-toc`：
    `temp/field-id-vocab-boundary-more-live-20260903/njau-03-toc-vocabonly`
    返回 `status=built`。Agent accepted semantics 有 27 个 judgments / 27 个 ordered parts，
    roles 为 `fixed_label=1`、`generated_content=25`、`cleanup=1`；唯一字段
    `generated.toc` 来自输入词表。Harness resolved spans 中有 25 个 generated-content
    `slot_ref`，但 publication 为 generated-only no-fill-slot 产物，`counts.manual=1`、
    `slot=0`，fill-contract v2、`slots=[]`；旧协议扫描无命中。
  - `04-abstract-cn`：
    `temp/field-id-vocab-boundary-more-live-20260903/njau-04-abstract-cn-vocabonly`
    返回 `status=built`；session `402d5b71-3ff1-41fc-99ce-94fd3f3f3061`、
    `num_turns=5`、`sdk_query_count=2`、`semantic_feedback_attempts=0`。Agent accepted
    semantics 有 8 个 judgments / 12 个 ordered parts，roles 为 `fill_slot=3`、
    `style_only=3`、`fixed_label=2`、`cleanup=4`；字段 `thesis.title.zh`、
    `abstract.zh`、`keywords.zh` 全部属于输入词表。materialization `status=ok`、
    `operation_count=3`、`cleanup_count=5`、`receipt_count=8`；fill-contract v2、3 个 slots，
    均为 Harness-resolved provenance；旧协议扫描无命中。
  - `05-abstract-en`：
    初始 root `temp/field-id-vocab-boundary-more-live-20260903/njau-05-abstract-en-vocabonly`
    在 publication postcondition 失败为 `school_style_observation_failed`。归因发现直接原因不是字段
    ID 推断，而是 Agent 把 `KEY WORDS` 标签后的全角冒号吞入 `keywords.en` 的 `fill_slot`，
    导致槽位 span 从固定标签样式 run 开始。当前修复在 `judgment_shape` 中新增
    `fill_slot_includes_label_delimiter` fail-closed blocker，Skill / Reference 明确标签分隔符归
    `fixed_label`，slot handler 改为按 ordered part 的原始 run 样式生成槽位 run。
    修复后的 root
    `temp/field-id-vocab-boundary-more-live-20260903/njau-05-abstract-en-vocabonly-delimiter-fixed`
    返回 `status=built`；session `fb21842f-1d93-42c5-9376-ae33403ae3e5`、
    `num_turns=2`、`sdk_query_count=3`、`semantic_feedback_attempts=1`。Agent accepted
    semantics 有 1 个 whole-unit judgment / 11 个 ordered parts，roles 为 `fixed_label=4`、
    `fill_slot=3`、`cleanup=4`；字段 `thesis.title.en`、`abstract.en`、`keywords.en`
    全部属于输入词表，且 `leading_delimiter_fill_slots=[]`。Harness resolved spans 有
    11 个，其中 3 个 slot spans；`KEY WORDS`、格式说明和 `：` 均为非字段 parts，
    `keywords.en` slot 从 `×××；×××；×××；×××（小四号Times New Roman）` 开始。
    materialization `status=ok`、`operation_count=3`、`cleanup_count=2`、`receipt_count=5`；
    fill-contract v2、3 个 slots，均为 `provenance.source=harness_resolved_span`；旧协议扫描无命中。
  - `product acceptance`：上述 NJAU 01-05 的 ZIP/XML reopen、OfficeCLI OpenXML、source unchanged
    和 placeholder scan 均为 `ok`；`01-cover`、`04-abstract-cn`、`05-abstract-en` 仍有预期替换带来的
    content preservation warning，所有 slice 仍因缺少完整 visual review coverage 不能算
    product acceptance。`docfit doctor --require visual-renderer` 仍返回
    `libreoffice_visual_renderer=NOT_READY`。
- Phase 8 的 NJAU `06-body` whole-unit body-structure 切片已补到 live E2E + product-provenance：
  - 归因和修复：真实 NJAU 正文单元最初在 post-unit resume 中返回 `template_agent_needs_input`，
    因为单个 `body_structure` judgment 需要覆盖多个 reading blocks，而 Agent 输入面只有
    block-local `range_id`。当前 packet / Tool summary 提供 whole-unit `reading_ranges[].range_id`，
    Agent 可用该输入 token 输出有序正文结构 parts；Harness 再映射到 Word block/range 并生成
    `span_ref`。
  - `E2E agent loop`：`temp/field-id-vocab-boundary-more-live-20260903/njau-06-body-resume-final-unit-range-body-gap`
    复用同 root 的 accepted unit-boundary proof 跑真实 post-unit Agent，最终返回 `status=built`。
    unit-boundary checkpoint 为 `status=ok`、`unit_count=3`、`sdk_query_count=2`；
    post-unit execution 为 `status=complete`、session `5504e143-7216-48ae-a56f-ecd07cca4e63`、
    `num_turns=2`、`sdk_query_count=5`、`semantic_feedback_attempts=2`。
  - `real replay` / `product-provenance`：Harness accepted semantics 有 3 个 judgments /
    39 个 resolved spans，roles 为 `body_structure=28`、`cleanup=11`；所有 fields 都来自输入
    vocabulary：`body.heading.outline1`、`body.heading.outline2`、`body.heading.outline3`、
    `body.paragraph`。三个 semantic scopes 均为对应 unit 的 `:range-whole-unit`。
    materialization `status=ok`、`operation_count=1`、`receipt_count=12`、`cleanup_count=11`，
    receipt actions 为 `materialize_structure=1`、`remove_body_structure_cleanup=11`，handler
    全部为 `body_structure`。publication `build-report.json` 为 `status=ok`，final
    `fill-contract.yaml` 是 v2、`candidate_pending_human_acceptance`、28 个 slots；semantics、
    materialization 和 fill-contract 的字段集合均是输入词表子集。
  - `product acceptance`：未完成。`docfit tools validate` 对 final-template 的 ZIP/XML reopen、
    OfficeCLI OpenXML、source unchanged 和 placeholder scan 为 `ok`，但返回
    `content_preservation` warning（`missing_object_count=39`）和 blocking
    `visual_review_coverage` issue，因为当前最终候选尚未完成全页渲染 review。
- Phase 8 的 NJAU `07-references` 集合接口切片已补到 live E2E + product-provenance：
  - 真实 blocker：`temp/field-id-vocab-boundary-more-live-20260903/njau-07-references-vocabonly`
    最初在 postcondition 失败为 `materialization_slot_ref_missing`。归因为 range-scope judgment
    覆盖多个 blocks 时，slot runtime 对每个 block 重放整条 judgment 的所有 parts，导致非 slot
    block 也查找最后一个 `fill_slot` part 的 `slot_ref`。
  - 修复：slot runtime 现在用 Harness `resolved_spans.part_index` 把 ordered parts 投影到当前
    reading block，并保留原始 `semantic_part_index` 追踪 `span_ref` / `slot_ref`；cleanup-only
    block 作为 accepted cleanup paragraph 删除。slot handler 和 existing SDT adoption 都使用
    原始 part index，而不是本地 enumerate 下标。
  - `real replay`：同一失败 root 的 persisted whole-unit range semantics 重新调用
    `_select_host_candidate_for_accepted_semantics` 后通过，写出
    `work/.docfit/post-unit-materialization/candidate-0001.docx`；materialization `status=ok`、
    `operation_count=1`、`cleanup_count=18`、`receipt_count=19`，slot operation 的
    `semantic_part_index=19`，`slot_ref=reading_range_id=unit-references:range-whole-unit;part_index=19;field_id=references.entries`。
  - `E2E agent loop` / `product-provenance`：
    `temp/field-id-vocab-boundary-more-live-20260903/njau-07-references-vocabonly-slotref-fixed`
    用真实 NJAU `07-references.docx` 和 Registry v0.5 从空 task root 跑完整
    `prepare-template`，返回 `status=built`。unit-boundary `status=ok`、`unit_count=1`；
    post-unit execution `status=complete`、session `bc710148-b903-40a6-bce8-97390c049217`、
    `num_turns=2`、`sdk_query_count=5`、`semantic_feedback_attempts=3`。Harness accepted
    semantics 有 20 个 judgments / 20 个 resolved spans，roles 为 `fixed_label=2`、
    `cleanup=8`、`fill_slot=10`；唯一字段为输入词表中的 `references.entries`。
    materialization `status=ok`、`operation_count=10`、`cleanup_count=8`、`receipt_count=18`；
    final fill-contract 为 v2、10 个 slots，字段集合全部是输入词表子集。最终 root 旧协议扫描无
    `semantic_field`、`registry_field`、旧 coverage 字段或 Agent-authored `span_id` /
    `slot_id` / `intent_id` / `judgment_id`。
  - `product acceptance`：未完成。`docfit tools validate` 的 ZIP/XML reopen、OfficeCLI
    OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有 `content_preservation`
    warning（`missing_object_count=18`）和 blocking `visual_review_coverage` issue。
- Phase 8 的 NJAU `08-appendix` appendix-title 切片已补到 live E2E + product-provenance：
  - `E2E agent loop`：
    `temp/field-id-vocab-boundary-more-live-20260903/njau-08-appendix-vocabonly`
    用真实 NJAU `08-appendix.docx` 和 Registry v0.5 从空 task root 跑完整
    `prepare-template`，返回 `status=built`。unit-boundary `status=ok`、`unit_count=1`；
    post-unit execution `status=complete`、session `5e547e31-083e-412c-b162-18e2e512b6f1`、
    `num_turns=5`、`sdk_query_count=3`、`semantic_feedback_attempts=0`。
  - `real replay` / `product-provenance`：Agent accepted semantics 有 1 个 judgment /
    2 个 ordered parts，roles 为 `fill_slot=1`、`cleanup=1`；唯一字段为输入词表中的
    `appendix.title`。Harness resolved spans 有 2 个，slot part 生成
    `span_ref=reading_range_id=unit-appendix-0001:range-whole-unit;part_index=0` 和
    `slot_ref=reading_range_id=unit-appendix-0001:range-whole-unit;part_index=0;field_id=appendix.title`。
    materialization `status=ok`、`operation_count=1`、`cleanup_count=1`、`receipt_count=2`；
    final fill-contract 为 v2、1 个 slot，`provenance.source=harness_resolved_span`，字段集合是输入词表子集。
    最终 root 的 `work` / `output` 旧协议扫描无 `semantic_field`、`registry_field`、旧 coverage
    字段或 Agent-authored `span_id` / `slot_id` / `intent_id` / `judgment_id`。
  - `product acceptance`：未完成。`docfit tools validate` 对 final-template 的 ZIP/XML reopen、
    OfficeCLI OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有
    `content_preservation` warning（`missing_object_count=2`）和 blocking
    `visual_review_coverage` issue。`docfit doctor --require visual-renderer` 仍返回
    `libreoffice_visual_renderer=NOT_READY`。
- Phase 8 的 NJAU `09-academic-achievements` terminal source-noop 切片已补到 live E2E + product-provenance：
  - `temp/field-id-vocab-boundary-more-live-20260903/njau-09-academic-achievements-vocabonly`
    用真实 NJAU `09-academic-achievements.docx` 和 Registry v0.5 从空 task root 跑完整
    `prepare-template`，返回 `status=built`。unit-boundary `status=ok`、`unit_count=1`；
    post-unit execution `status=complete`、session `819dd2ae-e0b9-4deb-b6e5-ca49e9582d30`、
    `num_turns=5`、`sdk_query_count=3`、`semantic_feedback_attempts=0`。
  - Agent accepted semantics 有 1 个 judgment / 2 个 ordered parts，roles 为
    `fixed_label=1`、`cleanup=1`，无 `field_id`；Harness resolved spans 有 2 个，均无
    `slot_ref`。materialization `status=ok`、`operation_count=0`、`cleanup_count=1`、
    `receipt_count=1`；publication `counts.manual=1`、`slot=0`，final fill-contract 为 v2、
    `slots=[]`。最终 root 的 `work` / `output` 旧协议扫描无命中，未创建、猜测或迁移
    `achievements.*` 字段 ID。
  - `product acceptance`：未完成。`docfit tools validate` 的 ZIP/XML reopen、OfficeCLI
    OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有 `content_preservation`
    warning（`missing_object_count=1`）和 blocking `visual_review_coverage` issue。
- Phase 8 的 NJAU `10-acknowledgement` 致谢正文 slot 切片已补到 live E2E + product-provenance：
  - `temp/field-id-vocab-boundary-more-live-20260903/njau-10-acknowledgement-vocabonly`
    用真实 NJAU `10-acknowledgement.docx` 和 Registry v0.5 从空 task root 跑完整
    `prepare-template`，返回 `status=built`。unit-boundary `status=ok`、`unit_count=1`；
    post-unit execution `status=complete`、session `b892cf68-5242-4eb1-a535-0702f27a9d11`、
    `num_turns=2`、`sdk_query_count=4`、`semantic_feedback_attempts=1`。
  - Agent accepted semantics 有 1 个 judgment / 5 个 ordered parts，roles 为
    `fixed_label=1`、`cleanup=3`、`fill_slot=1`；唯一字段为输入词表中的
    `acknowledgement.body`。Harness resolved spans 有 5 个，slot part 生成
    `span_ref=reading_range_id=unit-acknowledgement:range-whole-unit;part_index=4` 和
    `slot_ref=reading_range_id=unit-acknowledgement:range-whole-unit;part_index=4;field_id=acknowledgement.body`。
    materialization `status=ok`、`operation_count=1`、`cleanup_count=2`、`receipt_count=3`；
    final fill-contract 为 v2、1 个 slot，`provenance.source=harness_resolved_span`，字段集合是输入词表子集。
    最终 root 的 `work` / `output` 旧协议扫描无 `semantic_field`、`registry_field`、旧 coverage
    字段或 Agent-authored `span_id` / `slot_id` / `intent_id` / `judgment_id`。
  - `product acceptance`：未完成。`docfit tools validate` 的 ZIP/XML reopen、OfficeCLI
    OpenXML、source unchanged 和 placeholder scan 为 `ok`；仍有 `content_preservation`
    warning（`missing_object_count=3`）和 blocking `visual_review_coverage` issue。
- Phase 5-6 的本轮 source-noop 和字段清单清理已补齐：
  - `_select_host_candidate_for_accepted_semantics` 不再先按 source physical publishability 选择原始 DOCX；
    source-noop 必须先有 Harness accepted semantics，并且只能是 `manual_region` / 非执行 ordered parts。
    这防止带 DocFit slot protocol 的原始 DOCX 在没有 accepted post-unit provenance 时假绿发布。
  - 删除了 materialization layout helper 中仅供测试使用的具体字段 ID 清单
    `references.entries` / `acknowledgement.body` / `appendix.*`，模板 runtime 源码扫描中不再有
    `generated.toc`、`body.chapters`、`body.heading.*`、`body.paragraph` 或上述 terminal 字段作为
    代码内字段来源；只剩 `src/docfit/app/student_content_fill.py` 的 Student Content parked 口径。
  - `logic/contract` 验证：`uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `422 passed`；本轮相关 `ruff` 和 `mypy` 通过。
- Phase 5-6 的 PKU `02-copyright` mixed fixed/cleanup materialization 缺口已修复到
  `logic/contract` + `real replay`：
  - 真实 blocker：`temp/field-id-vocab-boundary-current-pku-live-20260903/pku-02-copyright-vocabonly`
    的初始完整流程中，Agent accepted semantics 为 1 个 whole-unit judgment / 3 个 resolved
    spans，roles 为 `fixed_label=2`、`cleanup=1`，没有任何 `field_id` 或 `slot_ref`；Host
    candidate selection 停在 `template_materialization_required`。归因为 mixed
    `fixed_label + cleanup` judgment 被编译为 `KEEP_FIXED_CONTENT` 后，runtime 只处理整条
    judgment 全部为 `cleanup` 的删除，没有消费同一 judgment 内已由 Harness resolve 的
    cleanup-only block span。
  - 修复：`src/docfit/template/materialization/runtime.py` 现在按当前 reading block 投影
    `ordered_parts`，当该 block 的 resolved parts 全部为 `cleanup` 时由 Harness 删除对应段落；
    cleanup mutation item 和 `src/docfit/template/materialization/receipts.py` 的 mutation receipt
    都保留 `span_refs`，从而可追踪到
    `reading_range_id=unit-copyright-statement:range-whole-unit;part_index=2`。没有新增字段别名、
    字段猜测或 Agent-authored `slot_id`。
  - `real replay`：同一 failed root 的 persisted accepted semantics 重新调用
    `_select_host_candidate_for_accepted_semantics` 后写出
    `work/.docfit/post-unit-materialization/candidate-0002.docx`；materialization
    `status=ok`、`operation_count=0`、`cleanup_count=1`、`publishability=ok`，cleanup receipt
    的 `field_ids=[]`、`handler=cleanup`、`span_refs=[reading_range_id=unit-copyright-statement:range-whole-unit;part_index=2]`。
  - `logic/contract` 验证：新增
    `tests/contract/test_template_materialization_runtime.py::test_materializer_removes_cleanup_block_inside_mixed_fixed_judgment`
    和 cleanup receipt `span_refs` 断言；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_receipts.py`
    -> `41 passed`；更宽合同/回放门禁
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `423 passed`；相关 `ruff` / `mypy` 通过。
  - `E2E agent loop`：本轮 fresh PKU `01-cover` 两次和 schema-fix 后一次仍停在
    `unit_checkpoint_result_invalid`，没有写出 unit-boundary proof；fresh PKU
    `02-copyright` 也停在 `unit_checkpoint_result_invalid`。复用已 accepted unit-boundary proof
    重跑 PKU `02-copyright` post-unit 时，Minimax SDK 连续 `api_retry` 后返回 plain text /
    `has_structured_output=false`，最终为 `template_agent_result_invalid`。环境 smoke
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache DOCFIT_PREPARE_TEMPLATE_NO_PROGRESS_TIMEOUT_SECONDS=120 uv run docfit agent-smoke --case denied-tools`
    同样返回 `status=FAIL`、`backend=minimax`、`MiniMax-M3 timed out after 180 seconds`。
    因此不能把 PKU `01-cover` 或 PKU `02-copyright` 本轮 fresh run 宣称为 E2E 通过。
  - schema hygiene：`UNIT_BOUNDARY_OUTPUT_SCHEMA` 不再要求 `units` 出现在所有状态中，避免
    prompt 允许 `status=needs_input` 但 schema 强制 `units[]` 的合同矛盾；完整 checkpoint
    仍由 `_unit_boundary_feedback` 和 Harness `unit_coverage` 要求 non-empty `units[]` 后才能进入主流程。
- Phase 4-6 的 runtime Registry check / internal index cleanup 已补齐到 `logic/contract`：
  - `docfit_check(registry_binding)` 不再是 Agent 可见 Tool schema 枚举，`DOCFIT_CHECK_SCHEMA`
    不再暴露 `field_id` 参数；旧调用即使传入当前 Registry 中存在的字段，也只返回
    `check_kind_retired`。字段 ID 只能从 unit packet 的 `field_id_vocabulary.allowed_field_ids`
    进入 Agent 输出，并由 Harness semantic submission 校验，不再通过 Tool runtime Registry
    check 探测或确认。
  - `semantic_part_index` 已加入 Agent judgment / part forbidden keys；它只允许作为
    Harness/materializer 内部 execution trace，用来把 block-local materialization 操作回连到
    Harness `resolved_spans.part_index`，不能由 Agent 输出。
  - `logic/contract` 验证：`tests/contract/test_template_judgment_shape.py` 新增
    Agent-authored `semantic_part_index` fail-closed 覆盖；`tests/contract/test_docfit_check_tool.py`
    将旧 `registry_binding` ok 路径反转为 retired/fail-closed；`tests/contract/test_tool_surface.py`
    固定 `registry_binding` 和 check-level `field_id` 均不在公开 schema 中。
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_judgment_shape.py tests/contract/test_tool_surface.py tests/contract/test_docfit_check_tool.py tests/contract/test_harness_feedback_helpfulness.py tests/unit/test_materialization_readiness.py`
    -> `61 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `422 passed`；相关 `ruff` / `mypy` 通过。
  - 源码扫描确认模板运行时代码没有 `generated.toc`、`body.chapters`、`body.heading.*`、
    `body.paragraph`、`references.entries`、`acknowledgement.body` 或 `appendix.*` 等具体字段 ID
    作为代码内字段来源；旧协议词只剩 denylist、feedback sanitizer、retired error code、
    Harness/generated `content_control_tag` locator 或 Word XML tag/alias 语义。
- Phase 4-6 的 `docfit_apply` 后置写入入口已补齐到 package-only `logic/contract`：
  - post-unit `docfit_apply` 不再仅凭 `semantic-judgments.json` 存在且非空就解锁写入；Harness phase
    review 必须携带当前形状的 `field_id_vocabulary.allowed_field_ids`、
    `semantic_judgments_sha256`、`scope + parts[]` 和 `resolved_spans`。每个 resolved span 必须覆盖
    一个且仅一个 Agent ordered part；带 `field_id` 的 part 必须有匹配的 Harness `slot_ref`，
    无字段 part 不能携带 `slot_ref`。
  - `DOCFIT_APPLY_SCHEMA` 不再暴露 `field_id`、`slot_ref`、`replacement_text`、
    `style_contract_ref` 或 `evidence_ref` 等直接 mutation 参数，并把 `batch_ref` 收紧为必填；
    写入只能来自 reviewed `operations[]` action package。旧 singular `edit_operation` package
    形状统一 fail closed 为 `action_package_shape_retired`。
  - 旧 review 形状（如 Agent-authored `judgment_id`、`registry_field`、`covered_object_ids`）和重复
    `resolved_spans.part_index` 均不能解锁 post-unit 写入；相关测试已反转为 fail-closed。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py tests/contract/test_docfit_evidence_tool.py::test_t1_candidate_hash_evidence_reads_the_candidate_snapshot tests/contract/test_tool_surface.py`
    -> `34 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `426 passed`；相关 `ruff` / `mypy` 和 `git diff --check` 通过。
- Phase 4-6 的 Tool audit / direct-intent residual cleanup 已补齐到 `logic/contract`：
  - `src/docfit/tools/__init__.py` 的 tool-call audit 不再识别旧 `payload.judgments` alias，也不再记录
    已移除的 top-level `field_id` 或 direct `replacement_text` mutation 参数；audit 只统计 canonical
    `payload.semantic_judgments`。
  - 未被生产代码引用的 `src/docfit/template/materialization/intent_classification.py` 已删除；旧
    `materialization_intent` / `intent_type` direct-intent 输入只剩 compiler/readiness denylist、内部
    compiled intent 产物字段和 fail-closed 测试。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_tool_surface.py`
    -> `10 passed`；materialization fail-closed gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py tests/contract/test_publication_style_handoff.py::test_o1_host_candidate_selection_rejects_legacy_invalid_direct_intent_review tests/contract/test_publication_style_handoff.py::test_o1_host_candidate_selection_rejects_legacy_direct_intent_before_source_noop`
    -> `34 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `428 passed`；相关 `ruff` / `mypy` 和 `git diff --check` 通过。
- Phase 4-7 的 App accepted-review gate 已补齐到 `logic/contract` + fixture `real replay`：
  - `src/docfit/app/prepare_template.py` 的 accepted Harness review 校验现在要求 inventory/review
    绑定当前输入 `template_sha256`，review 的 `semantic_judgments_sha256` 匹配当前
    `semantic_judgments`，inventory 和 review 的 `field_id_vocabulary` 都等于当前 task input
    Registry snapshot 派生的 pre-input vocabulary，且 digest 一致。
  - 每个 judgment 必须是当前 `scope + ordered parts` 形状；每个 part 必须有一个
    Harness-resolved span，`span_ref` 必须等于 `scope_kind=scope_id;part_index=N`，带字段的 part
    必须有匹配 `slot_ref`，非字段 part 不能带 `slot_ref`。App gate 还检查 `span_ref`
    不重复，并按 judgment scope 验证 inventory object 覆盖一次且仅一次。
  - `_post_unit_checkpoint_report` 在写 `post-unit-checkpoint.json` 前复用同一 gate；发布候选选择
    继续通过 `_accepted_harness_semantics` 进入同一 gate。因此旧 persisted review、伪造词表、
    重复 scope、旧 `registry_field` / `materialization_intent` / Agent-authored coverage 形状，都不能
    产生 checkpoint、candidate 或 materialization receipt。
  - 测试 fixture 同步分层：synthetic Agent 输出只保留 `scope + parts`；Harness accepted review
    fixture 才写 `resolved_spans`、词表、digest 和 hash。publication / integration 中仍使用旧 shape
    的 host-candidate tests 已反转为 `template_materialization_semantics_invalid` fail-closed。
  - 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_publication_style_handoff.py`
    -> `53 passed`；fixture replay gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2/test_agent_first_prepare_template.py::test_clean_source_may_be_selected_without_forcing_docx_edit`
    -> `12 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `428 passed`；相关 `ruff` / `mypy` 和 `git diff --check` 通过。
- Phase 4-7 的 Tool `docfit_apply` phase-review false green 已补齐到 `logic/contract`：
  - `src/docfit/tools/service.py` 的 post-unit 写入 gate 不再接受只和自己一致的
    `semantic-judgments.json`。它现在要求 `object-inventory.json` 存在，inventory 和 review
    都绑定当前 `source_hash`，二者的 `field_id_vocabulary` 都等于当前 task input Registry
    snapshot 派生的 pre-input vocabulary，并且 `field_vocabulary_digest` 一致。
  - Tool gate 现在用 inventory 中的 reading block / range 作为唯一 scope 来源校验 ordered
    semantic parts；每个 resolved span 必须等于
    `scope_kind=scope_id;part_index=N`，带字段 part 必须有匹配的 Harness `slot_ref`，非字段
    part 不能携带 `slot_ref`，span refs 必须全局唯一，inventory objects 必须被 judgment
    scope 覆盖一次且仅一次。
  - `docfit_apply` post-unit action package 还会反查 accepted review：`materialize_slot` /
    `materialize_structure` 中的每个 `field_id + slot_ref` 必须出现在 accepted
    `resolved_spans`，且目标 object 若可解析，必须落在该 span 的 `covered_object_ids` 中。这样
    Tool 入口不能用“Registry 中存在但 Agent ordered parts 未选择”的字段写入新槽位。
  - `tests/contract/test_docfit_apply_tool.py` 的 accepted review fixture 改为真实当前形状：从
    `input/field-registry.json` 生成 vocabulary，写入 matching inventory 和 digest；新增缺
    inventory、伪造 vocabulary、未覆盖 inventory object、未 review package slot 的 fail-closed
    用例。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py`
    -> `29 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `432 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/tools/service.py tests/contract/test_docfit_apply_tool.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；`git diff --check` -> passed。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这些仍按
    Phase 8 gate 继续追踪，不能把本轮合同测试表述为真实链路完整跑通。
- Phase 7 的 stale host receipt schema alias 已补齐到 `logic/contract`：
  - `src/docfit/template/judgment_shape.py` 删除旧 `completion_payload_v1` host receipt 兼容枚举和
    `validate_completion_payload_v1()` alias。host-owned completion receipt 现在只接受
    `host_completion_receipt_v1`，不再保留旧输出 schema 的兼容接收面。
  - `tests/contract/test_template_exchange_contracts.py` 将旧 `"completion_payload_v1"` 固定为
    fail-closed 反例；源码扫描确认该旧 schema 只剩测试中的拒绝字符串。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_exchange_contracts.py tests/contract/test_template_judgment_shape.py`
    -> `20 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `432 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/judgment_shape.py tests/contract/test_template_exchange_contracts.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed。
- Phase 5-6 的 materializer `semantic_part_index` 输入 fallback 已删除到 `logic/contract`：
  - `src/docfit/template/materialization/runtime.py` 不再通过向 part dict 写入
    `semantic_part_index` 来把 block-local parts 传给 slot handler；它现在传递显式
    `(original_part_index, part)`，原始 ordered parts 保持 Agent/Harness current shape。
  - `src/docfit/template/materialization/handlers/slots.py` 不再从 part 输入读取
    `semantic_part_index`，也不再在缺失时 fallback 到本地数组下标。handler 只消费调用者传入的
    original part index，并对仍夹带 `semantic_part_index` 的旧中间态输入返回
    `materialization_legacy_semantic_part_index`。
  - `semantic_part_index` 仍允许出现在 materialization operation / receipt 里，作为 Harness
    accepted ordered part 的内部 trace；不再是 Agent 或旧中间态可提交的输入字段。
  - `tests/contract/test_template_materialization_handlers.py` 新增旧 `semantic_part_index` 输入反向用例，
    并把 slot handler fixtures 迁到 explicit indexed parts。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_runtime.py`
    -> `32 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `433 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/materialization/runtime.py src/docfit/template/materialization/handlers/slots.py tests/contract/test_template_materialization_handlers.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed。
- Phase 5-6 的 compiler/materializer vocabulary provenance gate 已补齐到 `logic/contract`：
  - `src/docfit/template/materialization/vocabulary.py` 新增 accepted vocabulary provenance 校验：
    review / inventory 必须携带 `field_id_vocabulary` 和 `field_vocabulary_digest`，词表必须绑定当前
    Registry snapshot，digest 必须自洽，且 executable ordered parts 的 `field_id` 必须来自
    `allowed_field_ids`。Registry lookup alone 不再足以让 direct materialization path 进入执行。
  - `src/docfit/template/materialization/compiler.py` 在编译 Harness accepted review 前先拒绝缺词表、
    词表 Registry 不匹配、digest 不匹配或 field_id 不在 accepted vocabulary 的 review；不再把
    “Registry 中存在”当作可执行来源证明。
  - `src/docfit/template/materialization/readiness.py` 先校验 inventory/review 双方绑定同一份词表，
    再进入字段兼容、resolved span 和 shadow plan 检查。
  - `src/docfit/template/materialization/runtime.py` 在写 DOCX 之前强制调用 readiness gate；即使绕开 App
    直接调用 `materialize_template_from_semantics()`，无 accepted vocabulary provenance 的输入也会以
    `template_materialization_readiness_incomplete` fail closed，不生成候选 DOCX。
  - 测试 fixture 同步迁到 current shape：
    `tests/contract/test_template_materialization_compiler.py`、`tests/contract/test_template_materialization_plan.py`、
    `tests/contract/test_template_materialization_handlers.py`、`tests/contract/test_template_materialization_runtime.py`、
    `tests/contract/test_template_materialization_receipts.py`、`tests/contract/test_template_materialization_readiness.py`
    和 `tests/unit/test_materialization_readiness.py` 的成功路径都显式带 accepted vocabulary；新增缺词表和
    Registry 存在但不在 allowed vocabulary 的反向用例。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_plan.py tests/contract/test_template_materialization_receipts.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py tests/contract/test_template_materialization_readiness.py`
    -> `86 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `439 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/materialization/vocabulary.py src/docfit/template/materialization/compiler.py src/docfit/template/materialization/readiness.py src/docfit/template/materialization/runtime.py tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_plan.py tests/contract/test_template_materialization_receipts.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py tests/contract/test_template_materialization_readiness.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed。
- Phase 6 的 publication/materialization receipt provenance gate 已补齐到 `logic/contract`：
  - `src/docfit/template/materialization/runtime.py` 和 `src/docfit/app/prepare_template.py` 写出的
    post-unit materialization receipt 现在携带 `semantic_judgments_sha256`、`field_vocabulary_digest`
    和 `field_registry_ref`，使发布层能确认物化结果绑定的是同一批 accepted ordered parts 和同一份
    pre-input field vocabulary。
  - `src/docfit/template/artifact.py` 的 publication gate 现在要求
    `object-inventory.json`、`semantic-judgments.json` 和 `materialization.json` 同时存在，并复用
    vocabulary provenance 校验确认 inventory/review 绑定当前 Registry snapshot、digest 自洽且字段来自
    `allowed_field_ids`。
  - Fill Contract 组装前，每个 published slot 必须在 materialization operation 和 mutation receipt 中
    同时有 matching `slot_ref + span_ref + field_id`；只在 DOCX 里出现 Harness-looking `slot_ref`，
    或只在 receipt 中松散出现同名 `slot_ref`，不再足以发布。
  - `tests/contract/test_publication_style_handoff.py` 新增缺 inventory provenance、materialization vocabulary
    digest 不匹配、mutation receipt field/span 不匹配、不能从 `slot_ref` 反推 materialization operation
    field/span 的反向用例；成功发布 fixture 迁到 current materialization receipt shape。
  - `logic/contract` 验证：publication focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_publication_style_handoff.py`
    -> `34 passed`；相邻 App/materialization gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_template_materialization_receipts.py tests/contract/test_template_materialization_runtime.py`
    -> `42 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `443 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/artifact.py src/docfit/template/materialization/runtime.py src/docfit/app/prepare_template.py tests/contract/test_publication_style_handoff.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；`git diff --check` -> passed。
- Phase 5 的旧 Registry-unknown compiler/readiness 口径已退役到 `logic/contract`：
  - `src/docfit/template/materialization/readiness.py` 不再把
    `materialization_registry_field_unknown` / generated/body unknown code 映射到旧
    `materialization_field_not_in_registry`，也不再对 current ordered part 输出该旧 code；异常场景统一表述为
    field 不在 accepted pre-input vocabulary。
  - `src/docfit/template/materialization/compiler.py` 的防御性 unknown-field 分支改为
    `materialization_field_vocabulary_registry_mismatch`，不再保留“后置 Registry unknown”reason_code。
  - `src/docfit/app/prepare_template.py` 的 Agent-visible blocker sanitizer 删除已退役的
    `materialization_body_structure_parent_unknown` 分支。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/unit/test_materialization_readiness.py tests/contract/test_template_materialization_readiness.py tests/contract/test_template_materialization_compiler.py tests/contract/test_prepare_template_runtime.py`
    -> `60 passed`；旧 code source scan
    `rg -n "materialization_field_not_in_registry|materialization_registry_field_unknown|materialization_generated_content_field_unknown|materialization_body_structure_field_unknown|materialization_body_structure_parent_unknown|registered_generated_field_id|registered_parent_field_id|registered_structure_ref_or_member_field_id|registered_field_id" src/docfit/template src/docfit/app src/docfit/tools tests/unit/test_materialization_readiness.py tests/contract/test_template_materialization_readiness.py tests/contract/test_template_materialization_compiler.py tests/contract/test_prepare_template_runtime.py`
    -> no matches；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `443 passed`；相关 `ruff`、`mypy src` 和 `git diff --check` 通过。
- Phase 1/4 的 `unit_evidence_packet` Agent-visible 投影已补齐到 `logic/contract`：
  - `src/docfit/template/reading_packet.py` 新增 `agent_visible_unit_reading_packet()`，把内部
    reading packet 投影成产品 Agent 可见工作面；`reading_block_mappings`、`covered_object_ids`、
    coverage 账本、locator/object/fingerprint/span 等 Harness 映射材料继续留在内部 packet，
    不进入 Tool 返回的 unit packet。
  - `src/docfit/tools/service.py` 的 `focus=unit_evidence_packet` 现在只返回 `unit_id` /
    `unit_name`、reading blocks/ranges、layout cues 和 `field_id_vocabulary`；不再在
    `refs` 暴露 `scope_ref` 或 `unit_boundary_checkpoint`，不再在 `summary` 暴露 object/scoped
    object count 或 `coverage_contract.harness_maps_to`。
  - 旧 `scope_ref` locator fallback 已删除：post-unit packet 必须使用 accepted `unit_id`，
    历史 checkpoint 只有 `scope_ref`、没有 resolved readable range 时 fail closed，不做旧形状迁移。
  - `src/docfit/app/prepare_template.py` 从 unit-boundary checkpoint 构建 Harness inventory 时也不再
    接受 `unit.scope_ref` 兜底；缺少 resolved readable range 的历史 checkpoint 会以
    `post_unit_inventory_range_missing` fail closed，而不是静默生成新 inventory。
  - `tests/contract/test_docfit_evidence_tool.py` 和
    `tests/contract/test_template_reading_packet.py` 新增全 JSON 禁止词断言，
    `tests/contract/test_prepare_template_runtime.py` 新增旧 checkpoint 反向用例，证明
    `unit_evidence_packet` 可见响应不包含 `scope_ref`、`start_locator`、`end_locator`、
    `reading_block_mappings`、`covered_object_ids`、`coverage_required`、`coverage_contract`、
    `object_ref`、`target_ref`、`expected_fingerprint` 或 `span_ref`；旧 scope fallback 和
    legacy `scope_ref` checkpoint 都反转为 fail-closed。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_evidence_tool.py tests/contract/test_template_reading_packet.py`
    -> `58 passed`；Tool surface focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_evidence_tool.py tests/contract/test_template_reading_packet.py tests/contract/test_tool_surface.py`
    -> `44 passed`；公共 Tool context / prepare-template gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_tool_context_return_contract.py tests/contract/test_docfit_evidence_tool.py tests/contract/test_template_reading_packet.py tests/contract/test_prepare_template_runtime.py`
    -> `67 passed`；Agent boundary guardrail gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_agent_boundary_guardrails.py tests/contract/test_tool_context_return_contract.py`
    -> `16 passed`；更宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py`
    -> `447 passed`；相关 `ruff`、`mypy src`、`git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这些仍按
    Phase 8 gate 继续追踪，不能把本轮 Tool 返回面收紧表述为真实链路完整跑通。
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run docfit doctor --require visual-renderer`
    -> `Gate visual-renderer: NOT_READY`；当前环境仍报告 `officecli_backend` executable hash
    不匹配锁定 M1 binary，`libreoffice_visual_renderer=NOT_READY`，因此完整视觉 product
    acceptance 不能宣称完成。
- Phase 7 的 eval/gold 旧字段别名迁移层已反转为 fail-closed：
  - `evals/template-extraction/prepare_v05_gold_pairs.py` 删除 `FIELD_RENAMES` 和旧
    `migrate_field_values()` 改写逻辑；Gold 准备现在通过 `require_current_field_values()` 只接受
    当前 Registry 字段 ID，遇到 `body.heading.level1` 到 `body.heading.level5` 或旧
    `acknowledgement` 字段别名直接抛出 `retired field_id`，不再迁移到新字段 ID。
  - DOCX content-control alias 处理从 `migrate_aliases` 改为 `reject_retired_aliases=True`，旧
    alias 不再被静默改写，所有学校 Gold 准备入口都会拒绝旧 alias。
  - Gold/candidate fixture provenance 中的 `registry_migration: v0.5_clean_break_field_ids` 改为
    `field_id_vocabulary_policy: current_registry_field_ids_required_no_alias_migration`，避免评测材料继续表达
    “迁移”语义。
  - 因 Gold contract YAML 发生 metadata-only 变化，同步刷新了三校 `case.yaml`、
    `candidate-package-receipt.json`、accepted approval record 和 `candidate-sources/v0.5.yaml`
    中绑定的 contract / case sha256；这只保持 eval 账本一致，不代表重新完成产品人工验收。
  - `evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py` 新增旧字段 ID 反向用例，
    覆盖 `field_id`、`canonical_field_id`、`alias`、`field_ids` 和 `applies_to`；当前字段 ID 保持原样。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `6 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check evals/template-extraction/prepare_v05_gold_pairs.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> passed；source scan
    `rg -n "FIELD_RENAMES|migrate_field_values|migrate_aliases|registry_migration|v0\\.5_clean_break_field_ids" evals/template-extraction/prepare_v05_gold_pairs.py evals/template-extraction/cases evals/template-extraction/candidate-sources/v0.5 evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> no matches。
  - 更宽验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py tests/contract/test_template_observability_proof.py`
    -> `9 passed`；`PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/contract/test_candidate_gate.py`
    -> `9 passed`；模板边界宽套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `453 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；相关
    `git diff --check` -> passed。
  - 已知非本切片失败：`PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/contract/test_eval_contract.py evals/template-extraction/tests/contract/test_candidate_gate.py`
    中 `test_env_03_build_targets_are_mutually_isolated` 失败，因为 eval pyproject 当前 wheel packages
    已包含 `template_extraction_prep`，而测试仍期望只有 `template_extraction_eval`；这属于 eval packaging
    合同漂移，不是旧字段 ID 别名迁移路径。
  - 未完成层级：本轮没有新增真实 Gold 重建、真实 DOCX replay、live Agent E2E 或 product acceptance；
    不能把该 eval/gold fail-closed 改动表述为真实链路完整跑通。
- Phase 7 的 eval slot locator/tag fallback 已删除到 `logic/contract`：
  - `evals/template-extraction/template_extraction_eval/alignment.py` 的 `align_slot()` 现在只按
    `slot_ref` 对齐；Actual 合同没有相同 `slot_ref` 时直接返回
    `Actual contract has no matching slot_ref`，不再用相同 content-control locator / tag 兜底匹配。
  - `evals/template-extraction/tests/unit/test_alignment.py` 将原来的 slot locator fallback 预期反转为
    fail-closed，并新增不依赖 DOCX fixture hash 的 hermetic 反向用例，证明相同 locator、不同
    `slot_ref` 不会匹配。
  - `logic/contract` 验证：`PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_alignment.py -k ali_05`
    -> `1 passed, 4 deselected`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check evals/template-extraction/template_extraction_eval/alignment.py evals/template-extraction/tests/unit/test_alignment.py`
    -> passed；source scan
    `rg -n "tag fallback|matching slot_ref or tag fallback|multiple Actual slots match the tag|unique_locator_fallback_matches_changed_contract_ids" evals/template-extraction/template_extraction_eval/alignment.py evals/template-extraction/tests/unit/test_alignment.py evals/template-extraction/tests -g '*.py'`
    -> no matches。
  - 当前文件状态下的 Eval 全套
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests`
    -> `174 passed`；`git diff --check` -> passed。
  - 未完成层级：本轮没有新增真实 Gold 重建、live Agent E2E 或 product acceptance；
    只能说明 slot locator fallback 已 fail closed，并且当前 Eval 对齐链路已迁到 `slot_ref`。
- Phase 5-6 的 materialization `slot_ref` / `span_ref` provenance gate 已补严到 `logic/contract`：
  - `src/docfit/template/materialization/compiler.py` 的 executable part span gate 现在不仅要求
    `span_ref` 和 `slot_ref` 存在，还要求 `slot_ref == span_ref + ";field_id=" + parts[].field_id`；
    错配时返回 `materialization_resolved_span_missing`，payload 标出
    `slot_ref_mismatch_part_indices`。
  - `src/docfit/template/materialization/handlers/body_structure.py` 的直接 plan 消费路径现在只接受完整
    `span_ref`、`slot_ref`、`member_field_id` 三元组；member `slot_ref` 不等于
    `span_ref + field_id`、或声明 member 数和有效 binding 数不一致时，handler 不物化结构槽位。
  - `tests/contract/test_template_materialization_compiler.py` 新增错配 `slot_ref` 反向用例；
    `tests/contract/test_template_materialization_handlers.py` 新增绕过 compiler 直接传错配 body-structure
    plan 的反向用例，证明不会写 DOCX content control。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_compiler.py tests/contract/test_template_materialization_handlers.py`
    -> `41 passed`；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `455 passed`；相关 `ruff` 和 `mypy src` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    compiler/body-structure handler 不再接受错配的 slot provenance。
- Phase 5-6 的普通 slot handler / existing-SDT adoption `slot_ref` derivation gate 已补严到
  `logic/contract`：
  - `src/docfit/template/materialization/handlers/slots.py` 的 `_span_for_part()` 现在要求
    `span_ref` 存在，且 `slot_ref == span_ref + ";field_id=" + field_id`；直接调用普通 slot
    handler 时，错配 `slot_ref` 不会再被写进 content control。
  - `src/docfit/template/materialization/runtime.py` 的 `_span_for_slot_part()` 同步执行相同检查，
    防止 existing SDT adoption 路径只凭 `part_index + field_id + slot_ref存在` 接受伪造 tag。
  - `tests/contract/test_template_materialization_handlers.py` 新增普通 slot handler 反向用例；
    `tests/contract/test_template_materialization_runtime.py` 新增 existing SDT adoption 私有路径反向用例。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_runtime.py`
    -> `36 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/materialization/handlers/slots.py src/docfit/template/materialization/runtime.py tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_runtime.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `461 passed`。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    handler/runtime 层不再接受错配的 Harness slot provenance。
- Phase 4/6 的底层 `docx_edit` post-unit 写入后门已反转为 fail-closed：
  - `src/docfit/tools/service.py` 现在在 direct `docx_edit` 领域写入进入 `_edit_domain()` 前，先识别
    当前 task root 是否已有 unit-boundary checkpoint；一旦进入 post-unit，底层 domain write 与
    `docfit_apply` 一样必须找到 accepted Harness phase review，缺失时返回 `phase_review_required`，
    不会调用 `mutate_objects()` 写 DOCX。
  - direct `docx_edit` 和 `docfit_apply` 的 post-unit materialization 都固定使用 task input
    中生成 Agent-visible `field_id_vocabulary` 的 pre-input Registry；action package 或 direct edit
    传入另一份 `field_registry` 时返回 `field_registry_not_pre_input`，避免同名 field ID 借外部
    Registry metadata 改变 materialization 行为。
  - 每个实际写入的 materialized slot 仍必须匹配 accepted review 中的
    `(field_id, slot_ref, object_id)` provenance；错配 `slot_ref` 会在写入前返回
    `phase_review_action_package_unaccepted`。
  - `tests/contract/test_docfit_apply_tool.py` 新增 direct `docx_edit` 反向用例，覆盖无 phase review、
    未 accepted `slot_ref`、以及 post-unit registry swap；同时新增 `docfit_apply` action package
    registry swap 反向用例。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py -k 'direct_docx_edit_post_unit or action_package_field_registry_swap'`
    -> `4 passed, 29 deselected`；完整 apply contract
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py`
    -> `33 passed`；materialization/publication 回归
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py tests/contract/test_template_materialization_compiler.py tests/contract/test_template_materialization_handlers.py tests/contract/test_publication_style_handoff.py`
    -> `108 passed`；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `459 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/tools/service.py tests/contract/test_docfit_apply_tool.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；`git diff --check`
    -> passed。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    post-unit 工具写入入口不会再绕过 accepted Harness review 或 pre-input Registry。
- Phase 7 的 Eval fill-contract v1 主加载路径已反转为 fail-closed：
  - `evals/template-extraction/template_extraction_eval/contracts.py` 删除
    `load_legacy_fill_contract()`、`_legacy_slot_style()`、v1 `style_id` 解析和
    `load_fill_contract()` 的 v1 分发分支；`load_fill_contract()` 现在在 schema 校验前识别
    `docfit-template-fill-contract/v1` 并返回 `CONTRACT_MISMATCH`，不会把旧 Gold / candidate
    合同转换成当前评分输入。
  - `evals/template-extraction/schemas/fill-contract.schema.json` 改为 v2-only：
    `schema_version` 只允许 `docfit-template-fill-contract/v2`，`styles` 和
    `style_contract_set_digest` 成为必填，slot/style items 固定引用 v2 定义，旧
    `legacySlotV1` / `legacyStyleV1` schema definition 已删除。
  - `evals/template-extraction/schemas/report.schema.json` 同步要求 report config 中的
    `actual_contract` / `gold_contract` 只能声明 v2；单测中的 v1 report 期望已改为 v2。
  - `evals/template-extraction/prepare_v05_gold_pairs.py` 的 HUNAU `existing_v1` 和 PKU
    `pku_r02` Gold 准备路径现在在 case 分发前 fail closed，且对应生成函数只报告
    “retired fill-contract/v1”，不再生成 v1 合同或承认 legacy surface。
  - `evals/template-extraction/tests/unit/test_style_contract_v2.py` 将旧 reader 正向测试反转为
    `fill contract v1 is retired`；`evals/template-extraction/tests/contract/test_eval_contract.py`
    改用最小 v2 schema 正例，并把旧 S00 v1 fixture 反转为 schema failure。Eval packaging
    隔离测试同步按当前 `template_extraction_prep` 包事实验证产品包和 Eval 包仍隔离。
  - `logic/contract` 验证：focused gate
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_style_contract_v2.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py evals/template-extraction/tests/contract/test_eval_contract.py evals/template-extraction/tests/unit/test_reporting.py evals/template-extraction/tests/unit/test_aligned_protected.py`
    -> `49 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check evals/template-extraction/template_extraction_eval/contracts.py evals/template-extraction/template_extraction_eval/evaluators/slots.py evals/template-extraction/prepare_v05_gold_pairs.py evals/template-extraction/tests/unit/test_style_contract_v2.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py evals/template-extraction/tests/contract/test_eval_contract.py evals/template-extraction/tests/unit/test_reporting.py evals/template-extraction/tests/unit/test_aligned_protected.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy template_extraction_eval template_extraction_prep`
    from `evals/template-extraction` -> passed。
  - Source scan:
    `rg -n "load_legacy_fill_contract|_legacy_slot_style|legacy v1 read support|legacySlotV1|legacyStyleV1" evals/template-extraction/template_extraction_eval evals/template-extraction/tests evals/template-extraction/schemas evals/template-extraction/prepare_v05_gold_pairs.py`
    -> no matches；`rg -n "docfit-template-fill-contract/v1" ...` 只剩 loader denylist 常量和
    fail-closed 单测。旧 formal/candidate YAML 中仍有 v1 合同或 `slot_id` 字段；这些现在不再是
    可加载的绿色输入，后续必须从真实 Harness `slot_ref` 产物重建，不能通过 loader 兼容继续评分。
  - 未完成层级：本轮没有重建三校 formal Gold，也没有新增真实 replay、live Agent E2E 或
    product acceptance；只能说明 Eval 主加载路径对 v1/旧 slot 形状已经 fail closed。
- Phase 6 的最终内容投影旧 fill-contract/style alias fallback 已反转为 fail-closed：
  - `src/docfit/content/projection.py` 的 `resolve_template_style_map()` / `_contract_style_map()`
    现在要求输入合同是 `docfit-template-fill-contract/v2`，并且 style role 只能来自
    `style_contract_id`；v2 样式条目里出现旧 `style_id`，或传入 v1 合同，都会返回
    `projection_contract_retired_style_id` / `projection_fill_contract_version_retired`。
  - `tests/unit/test_student_content_projection.py` 将旧 “v1 style_id alias 可解析” 测试反转为
    fail-closed；最终填充路径不再通过旧合同 shape 影响正文/标题样式投影。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/unit/test_student_content_projection.py tests/unit/test_student_content.py -k 'style_roles or template_style or placement_refuses'`
    -> `3 passed, 13 deselected`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/content/projection.py tests/unit/test_student_content_projection.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed。
  - 未完成层级：本轮没有跑真实 student content fill replay 或最终 Word product acceptance；
    只能说明旧 fill-contract/style alias fallback 已在内容投影入口 fail closed。
- Phase 7 的 Eval / fill-contract 槽位业务 identity 已从 `slot_id` 迁到 `slot_ref`：
  - `evals/template-extraction/template_extraction_eval/models.py` 的 `SlotContract`、
    `AssertionResult`、`Issue` 使用 `slot_ref`；`alignment.py`、slot evaluator、responsibility
    assertion 和 report 生成都按 `slot_ref` 对齐/归因，不再以 `slot_id` 作为业务槽位 identity。
  - `evals/template-extraction/schemas/fill-contract.schema.json` 的 slot item 现在要求
    `slot_ref`，并用 Harness 形状
    `reading_block_id|reading_range_id + part_index + field_id` 约束；旧 `slot_id` 字段因
    `additionalProperties: false` fail closed。
  - `evals/template-extraction/schemas/report.schema.json` 的 issue 字段从 `slot_id` 改为
    `slot_ref`；`test_models.py`、`test_reporting.py` 和 alignment 单测同步使用当前
    Harness `slot_ref` 形状。
  - `evals/template-extraction/tests/unit/test_alignment.py` 不再加载旧 v1 fixture 做正例；前 4 个
    alignment 用例已改成内存 facts / v2 `slot_ref` 合同，避免旧 fixture hash 或旧 slot identity
    继续作为绿色路径。
  - Source scan:
    `rg -n "\bslot_id\b" evals/template-extraction/template_extraction_eval evals/template-extraction/tests evals/template-extraction/schemas evals/template-extraction/prepare_v05_gold_pairs.py`
    -> 只剩 fail-closed 单测断言文本；业务 `slot_id` 不再出现在 Eval 代码、schema 或 Gold prep
    脚本。marker 配置仍保留 `slot_identity_property` / `slot_identity_rule`，业务含义是 DOCX
    tag 载体，不是旧 `slot_id`。
  - `logic/contract` 验证：focused gate
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_alignment.py evals/template-extraction/tests/unit/test_style_contract_v2.py evals/template-extraction/tests/contract/test_eval_contract.py evals/template-extraction/tests/unit/test_reporting.py evals/template-extraction/tests/unit/test_models.py evals/template-extraction/tests/unit/test_aligned_protected.py evals/template-extraction/tests/unit/test_style_observations.py`
    -> `55 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check evals/template-extraction/template_extraction_eval evals/template-extraction/prepare_v05_gold_pairs.py evals/template-extraction/tests/unit/test_alignment.py evals/template-extraction/tests/unit/test_style_contract_v2.py evals/template-extraction/tests/contract/test_eval_contract.py evals/template-extraction/tests/unit/test_reporting.py evals/template-extraction/tests/unit/test_models.py evals/template-extraction/tests/unit/test_aligned_protected.py evals/template-extraction/tests/unit/test_style_observations.py evals/template-extraction/tests/integration/test_raw_source_sentinel.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy template_extraction_eval template_extraction_prep`
    from `evals/template-extraction` -> passed。
  - 合成 fixtures 已通过 `fixtures/build_samples.py` 重新生成成 v2 `slot_ref` 形状；fixture 扫描
    `rg -n "schema_version: docfit-template-fill-contract/v1|\bslot_id:" evals/template-extraction/fixtures`
    -> no matches。formal `cases/**/gold/fill-contract.gold.yaml` 和
    `candidate-sources/v0.5/**/fill-contract.yaml` 仍保留旧历史形状，但
    `test_candidate_gate.py` / `test_raw_source_sentinel.py` 已反转为 fail-closed。
  - 当前 `logic/contract` 验证：builder
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run python evals/template-extraction/fixtures/build_samples.py --output-root evals/template-extraction/fixtures --scoring evals/template-extraction/config/scoring-v1.yaml`
    -> `{"sample_count": 14}`；Eval 全套
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests`
    -> `174 passed`；Eval ruff -> passed；Eval mypy
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy template_extraction_eval template_extraction_prep`
    from `evals/template-extraction` -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；`git diff --check` -> passed；`fill-contract.schema.json` 和 `report.schema.json`
    均通过 `python -m json.tool`。
  - 未完成层级：当前仅完成 Eval `logic/contract` 和合成 fixture contract 验证；formal 三校 Gold
    仍需从真实 Harness `span_ref` / `slot_ref` 产物重建。未新增真实 replay、live Agent E2E 或
    product acceptance，不能宣称 Phase 8 完成。
- Phase 4-6 的 accepted review `resolved_spans` 与 Agent ordered parts 对齐门已继续收紧到
  `logic/contract`：
  - `src/docfit/template/judgment_shape.py` 已把 Agent-authored `resolved_span` /
    `resolved_spans` / `resolved_span_refs` 加入 forbidden keys；Agent post-unit 输出只能提交
    `scope + parts[]`，不能把 Harness-owned span 结果伪装成输入。
  - `src/docfit/app/prepare_template.py` 和 `src/docfit/tools/service.py` 的 accepted Harness phase-review
    gate 现在先把 accepted review 投影回 Agent-facing `scope + parts[]` 再跑 ordered-parts
    validator，避免把 Harness 生成的 `resolved_spans` 当成 Agent 输入字段；随后再单独校验
    resolved span 的字段 provenance 与对应 Agent ordered part 完全一致。带
    `field_id` 的 part 仍必须匹配 `span_ref + field_id` 机械生成的 `slot_ref`；不带 `field_id`
    的 part 对应 resolved span 也不得携带 `field_id` 或 `slot_ref`。同一个 gate 还要求
    `resolved_spans[].text` 等于 `parts[].text.strip()`，`resolved_spans[].role` 等于
    `parts[].role.strip()`，并且每个 resolved span 的 `covered_object_ids` 是当前 judgment
    scope 对应对象集合的非空子集。
  - 这些反向门防止 Harness / Tool/App 接收“Agent 未选择字段，但底层 span 后置补了 field_id”，
    或“part_index 对上但 span 文本/role/covered objects 被后置改写”的伪 provenance。字段 ID
    仍只能从 input `field_id_vocabulary` 进入 Agent part，再由 Harness 映射成 `span_ref` /
    `slot_ref`。
  - `logic/contract` 验证：新增
    `tests/contract/test_template_judgment_shape.py::test_ordered_semantic_parts_rejects_agent_authored_resolved_spans`、
    `tests/contract/test_prepare_template_runtime.py::test_host_candidate_selection_rejects_resolved_span_field_without_part_field`
    / `test_host_candidate_selection_rejects_resolved_span_part_mismatch`
    / `test_host_candidate_selection_rejects_resolved_span_objects_outside_scope`
    和
    `tests/contract/test_docfit_apply_tool.py::test_t3_post_unit_apply_rejects_span_field_without_part_field`
    / `test_t3_post_unit_apply_rejects_resolved_span_part_mismatch`
    / `test_t3_post_unit_apply_rejects_resolved_span_objects_outside_scope`。
    `test_publication_style_handoff.py` 和 `test_template_materialization_replay.py` 的 accepted-review
    fixtures 同步补齐 span object provenance，避免旧不完整 Harness fixture 继续作为绿色路径。
    Agent validator / Harness / App / Tool focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_judgment_shape.py tests/contract/test_template_harness_reading_blocks.py tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py`
    -> `96 passed`；App/Tool/publication/replay affected files
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `110 passed`；
    Focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py::test_host_candidate_selection_rejects_resolved_span_field_without_part_field tests/contract/test_prepare_template_runtime.py::test_host_candidate_selection_rejects_resolved_span_part_mismatch tests/contract/test_prepare_template_runtime.py::test_host_candidate_selection_rejects_resolved_span_objects_outside_scope tests/contract/test_docfit_apply_tool.py::test_t3_post_unit_apply_rejects_span_field_without_part_field tests/contract/test_docfit_apply_tool.py::test_t3_post_unit_apply_rejects_resolved_span_part_mismatch tests/contract/test_docfit_apply_tool.py::test_t3_post_unit_apply_rejects_resolved_span_objects_outside_scope`
    -> `8 passed`；affected App/Tool/publication/replay files
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `110 passed`；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `472 passed`；`ruff`、`mypy src` 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    App/Tool gate 不再接受非字段 part 的后置 `field_id` 注入，也不接受与 Agent ordered part
    文本、role 或 scope object provenance 不一致的 resolved span。
- Phase 5 的 compiler/readiness part-level legacy shape 入口已补成 fail-closed 到
  `logic/contract`：
  - `src/docfit/template/materialization/compiler.py` 现在不仅拒绝 judgment 顶层旧字段，也拒绝
    `parts[]` 内的旧字段别名、旧 coverage/object/locator/span 账本字段和旧 plural
    `field_ids` 形状。合法字段输入仍只有 `parts[].field_id`，且后续 vocabulary provenance gate
    继续证明它来自当前输入词表。
  - `src/docfit/template/materialization/readiness.py` 同步拒绝 `parts[]` 内 legacy shape，并在
    readiness blocker 中写出 `legacy_part_fields`；只要 review 中存在旧 shape，就不再运行
    shadow materialization plan，避免同一旧输入被重复包装成下游执行问题。
  - 新增反向测试：
    `tests/contract/test_template_materialization_compiler.py::test_compiler_rejects_legacy_part_field_shapes`
    和
    `tests/unit/test_materialization_readiness.py::test_materialization_readiness_blocks_legacy_part_shape`。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py`
    -> `49 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/materialization/compiler.py src/docfit/template/materialization/readiness.py tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    `git diff --check` -> passed；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `489 passed`。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    compiler/readiness 核心层不再接受 part 内部旧中间态或旧字段别名。
- Phase 5-6 的 body-structure 容器字段已从发布 field/slot 面拆掉到 `logic/contract`：
  - `src/docfit/template/materialization/compiler.py` 的 body-structure intent `field_ids` 现在只包含
    Agent ordered `body_structure` parts 显式选择的 member fields；Registry
    `parent_field_id` 仍作为 `payload.structure_ref` 和 `structure_ref_provenance` 保留，用于结构一致性校验，
    但不再进入通用 `field_ids`。
  - `src/docfit/template/materialization/handlers/body_structure.py` 不再用 `structure_ref` 生成外层
    `slot_ref`，也不再把 `body.chapters` 作为外层 Word content-control alias/tag 写入。外层结构容器只保留
    无发布 alias/tag 的 Word 分组；可发布槽位仍全部来自 Harness-resolved member `span_ref + field_id`
    的 `slot_ref`。
  - Runtime、publication handoff、integration replay 和 Eval region fixture 的旧断言已反转：
    receipt/operation/fill-contract 发布面不再承认 `body.chapters` 是发布字段或 slot；member fields
    仍按 Agent part provenance 验证。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_compiler.py tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_runtime.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `112 passed`；`PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_case_materializer.py`
    -> `7 passed`；`rg -n "field_ids=\\(\\\"body\\.chapters|field_ids == \\(\\s*\\\"body\\.chapters|\\[\\s*\\\"body\\.chapters\\\"|field_ids.*body\\.chapters|field_id=body\\.chapters|\\\"field_ids\\\": \\[\\\"body\\.chapters" tests src/docfit evals/template-extraction/tests`
    -> no matches；`PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests`
    -> `174 passed` after rebuilding synthetic fixtures；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `489 passed`；`ruff`、`mypy src` 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    body-structure 的发布 field/slot 面不再包含由 compiler/handler 后置派生的结构容器字段。
- Phase 5-6 的 `semantic_part_index` 成功输出形状已退役到 `logic/contract`：
  - `src/docfit/template/materialization/runtime.py` 和
    `src/docfit/template/materialization/handlers/slots.py` 的 materialize-slot operation 不再输出旧
    `semantic_part_index`，改为规范 `part_index`。旧字段名仍只保留在输入 denylist 和 fail-closed
    错误码文本中。
  - `src/docfit/template/materialization/readiness.py` 的 part context blocker 同步输出 `part_index`，
    不再把旧字段名作为反馈结构继续传播。
  - `tests/contract/test_template_materialization_handlers.py` 和
    `tests/integration/test_template_materialization_replay.py` 的成功路径断言已反转，明确 operation
    不含 `semantic_part_index`。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_runtime.py tests/integration/test_template_materialization_replay.py tests/unit/test_materialization_readiness.py`
    -> `65 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/materialization/runtime.py src/docfit/template/materialization/handlers/slots.py src/docfit/template/materialization/readiness.py tests/contract/test_template_materialization_handlers.py tests/integration/test_template_materialization_replay.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests`
    -> `174 passed`；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `489 passed`；`git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    slot materialization 成功输出和 readiness blocker context 不再传播旧 part-index 字段名。
- Phase 5 的 `docfit_apply` stale target / carrier metadata fallback 已删除到
  `logic/contract`：
  - `src/docfit/tools/service.py` 不再在 `candidate_hash` 不匹配时按旧 `target_ref.locator`
    扫描当前 candidate 并机械刷新 object_ref；`target_ref` 只接受当前 candidate snapshot
    绑定的引用，旧 source snapshot 或其它 candidate 的引用一律以 `stale_object_ref` fail closed。
  - `docfit_apply` 也不再修复 action package 中拼错或未知的 target carrier metadata。当前 candidate
    的 object_ref 仍能作为账本引用解析，但坏 carrier 不再通过 inspection fallback 重写为可执行类型。
  - 旧测试
    `test_t3_apply_refreshes_stale_locator_bound_target_ref_against_candidate`
    已反转为
    `test_t3_apply_fails_closed_on_stale_locator_bound_target_ref_after_candidate_change`；
    旧 `test_t3_apply_repairs_typoed_carrier_metadata_from_current_candidate`
    已反转为 `test_t3_apply_fails_closed_on_typoed_carrier_metadata`。
  - `logic/contract` 验证：focused Tool gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py tests/contract/test_docfit_evidence_tool.py`
    -> `77 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/tools/service.py tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py tests/contract/test_docfit_evidence_tool.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `489 passed`；`git diff --check` -> passed；残留扫描
    `_decode_or_refresh_apply_target_ref|_repair_unknown_apply_target_carrier|Refresh target evidence|cannot be refreshed|refreshes_stale|repairs_typoed_carrier|repair-typoed-carrier|current candidate_hash|_TARGET_REF_REFRESH_ACTIONS`
    -> no matches。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    Tool apply 请求层不再迁移旧 target_ref 或修复坏 carrier metadata。
- Phase 6-7 的 Eval region structural locator fallback 已删除到 `logic/contract`：
  - `evals/template-extraction/template_extraction_eval/alignment.py` 不再在 Actual fill-contract
    缺少 Gold `region_id` 时，按 owner + paragraph location + locator 猜一个唯一 region
    当作匹配。Actual `region_id` 不一致现在直接返回 `MISSING`，避免 region / field 身份漂移
    被评分层兜底掩盖。
  - `evals/template-extraction/tests/unit/test_alignment.py` 将旧
    `region_locator_fallback_kept` 断言反转为
    `test_ali_02_region_id_mismatch_fails_closed_without_locator_fallback`；slot_ref
    mismatch 仍保持 fail closed。
  - `logic/contract` 验证：focused Eval gate
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_alignment.py evals/template-extraction/tests/unit/test_aligned_protected.py evals/template-extraction/tests/contract/test_eval_contract.py`
    -> `35 passed`；相关 ruff
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check evals/template-extraction/template_extraction_eval/alignment.py evals/template-extraction/tests/unit/test_alignment.py`
    -> passed；残留扫描
    `fallback locator|structural fallback|unique locator fallback|locator fallback|Gold fallback`
    -> no matches。
  - 完整 Eval 初跑发现 synthetic fixture 输入 hash 未同步，状态为 `INPUT_ERROR`，归因为
    fixture/Gold 账本而不是 alignment 行为；重新运行
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run python evals/template-extraction/fixtures/build_samples.py --output-root evals/template-extraction/fixtures --scoring evals/template-extraction/config/scoring-v1.yaml`
    -> `{"sample_count": 14}` 后，完整 Eval
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests`
    -> `174 passed`；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `489 passed`。
  - 未完成层级：本轮没有新增 live Agent E2E 或 product acceptance；只能说明 Eval
    region identity 评分不再通过 locator fallback 容忍旧/错误 region ID。
- Phase 6-7 的 Eval slot synthetic content-control fallback 已删除到 `logic/contract`：
  - `evals/template-extraction/template_extraction_eval/alignment.py` 的 slot alignment 现在只承认
    `content_control_tag` locator 对应的真实 Word content control；即使 slot_ref 一致，`text_anchor` /
    `placeholder_anchor` / `text_range` 也不会再合成 `ContentControlFact(alias=slot.field_id)` 来让
    slot 边界、字段映射或样式比较继续通过。
  - 新增
    `evals/template-extraction/tests/unit/test_alignment.py::test_ali_06_slot_text_anchor_does_not_synthesize_content_control`，
    证明文本 anchor 能定位段落但没有真实 content control 时，slot alignment 必须返回
    `MISSING`。
  - `logic/contract` 验证：focused Eval gate
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests/unit/test_alignment.py evals/template-extraction/tests/unit/test_aligned_protected.py evals/template-extraction/tests/contract/test_eval_contract.py`
    -> `36 passed`；相关 ruff
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check evals/template-extraction/template_extraction_eval/alignment.py evals/template-extraction/tests/unit/test_alignment.py`
    -> passed；完整 Eval
    `PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q evals/template-extraction/tests`
    -> `175 passed`；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `489 passed`。
  - 未完成层级：本轮没有新增 live Agent E2E 或 product acceptance；只能说明 Eval
    slot identity 不再由非 marker locator 合成真实 content-control 事实。
- Phase 3 的 Harness persisted `resolved_spans` coverage fallback 已删除到
  `logic/contract`：
  - `src/docfit/template/harness.py` 的 `_state()` / status 路径不再在 judgment 缺少当前
    `scope` 时，回退读取旧 persisted `resolved_spans[].covered_object_ids` 来计算 semantic
    coverage。覆盖只能来自当前 `scope + ordered parts` 对应的 reading block / range 投影。
  - 已删除 `_resolved_span_object_ids()` helper；旧 persisted review 即使带有覆盖 object ids，也不会
    被 status 看成 semantic coverage ok。
  - 新增
    `tests/contract/test_template_harness_reading_blocks.py::test_template_harness_status_does_not_use_legacy_resolved_spans_for_coverage`，
    证明手工落盘旧 `resolved_spans` judgment 后，Harness status 的 `covered_object_count=0`，
    并报告 missing object / uncovered judgment。
  - `logic/contract` 验证：focused Harness gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_harness_reading_blocks.py tests/contract/test_template_judgment_shape.py`
    -> `37 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/harness.py tests/contract/test_template_harness_reading_blocks.py`
    -> passed；App/Tool/publication/replay gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `110 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `490 passed`。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    Harness status 不再把旧中间态 `resolved_spans` 当 coverage 输入。
- Phase 3 的 Harness ordered part 到 Word text span 精度门已补到 `logic/contract`：
  - `src/docfit/template/reading_packet.py` 会在内部 `reading_block_mappings` 中生成
    `object_text_spans`，把可见 block 文本字符区间映射到源 Word text object；Agent-visible
    reading packet 投影仍隐藏 `reading_block_mappings`、`covered_object_ids`、`object_text_spans`、
    locator/object ref 和 `span_ref`。
  - `src/docfit/template/harness.py` 的 span resolver 优先消费 `object_text_spans` 生成
    part-level `covered_object_ids`；如果只有粗粒度 reading-block mapping，且 Agent ordered part
    只覆盖多对象 block 的局部文本，则返回 `ordered_part_span_object_ambiguous`，不再给每个 part
    继承整个 block 的对象集合来制造假 provenance。
  - `tests/contract/test_template_harness_reading_blocks.py::test_template_harness_allows_multiple_field_slots_on_one_reading_block`
    现在必须提供对象级 text spans 才能在同一 reading block 内拆多个 field slot；新增
    `test_template_harness_rejects_sub_block_parts_without_precise_object_text_spans` 证明缺少精确账本时
    fail closed。`tests/contract/test_template_reading_packet.py::test_unit_reading_packet_records_internal_object_text_spans_for_harness`
    证明真实 packet builder 会生成内部字符段，且 Agent-visible 投影不泄露它。
  - `logic/contract` 验证：focused reading/Harness gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py tests/contract/test_template_judgment_shape.py`
    -> `43 passed`；App/Tool/publication/replay gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `110 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/reading_packet.py src/docfit/template/harness.py tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `492 passed`；`git diff --check` -> passed。
  - 残留扫描：
    `rg -n "object_text_spans|mapping_precision|ordered_part_span_object_ambiguous|ordered_part_span_unmapped" src/docfit/template src/docfit/app/prepare_template.py src/docfit/tools/service.py tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py`
    仅命中内部 packet/Harness 和合同测试；Agent-facing scan 没有新增 `object_text_spans`。
  - 未完成层级：本轮没有新增三校真实 inventory replay、live Agent E2E 或 product acceptance；只能说明
    Harness 在 `logic/contract` 层不再把多对象 block 的局部 part 当成可追踪 Word range。
- Phase 3 的 Harness ordered parts exact partition gap 已补到 `logic/contract`：
  - `src/docfit/template/harness.py` 不再用 `skipped.strip()` / trailing whitespace tolerance
    容忍 Agent 省略 reading block 内的可见空格。`find(text, cursor)` 只能跨越 reading range
    scope 中由 Harness 拼接多个 reading block 时插入的结构性 `\n`，不能跳过单个 block 内可见
    whitespace 或其它文本。
  - 新增
    `tests/contract/test_template_harness_reading_blocks.py::test_template_harness_rejects_visible_whitespace_gap_inside_reading_block`，
    证明 `姓名： 张三` 被拆成 `姓名：` + `张三` 时会返回 `ordered_part_text_gap`，不会靠跳过空格
    继续生成 `span_ref` / `slot_ref`。
  - `logic/contract` 验证：focused Harness gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_harness_reading_blocks.py tests/contract/test_template_judgment_shape.py`
    -> `39 passed`；focused reading/Harness gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py tests/contract/test_template_judgment_shape.py`
    -> `44 passed`；App/Tool/publication/replay gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `110 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/reading_packet.py src/docfit/template/harness.py tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `493 passed`；`git diff --check` -> passed。
  - 残留扫描：
    `rg -n "non-whitespace gaps|ordered_part_gap_is_structural_separator|visible_whitespace_gap|ordered_part_text_gap|ordered_part_text_trailing_gap" src/docfit/template/harness.py tests/contract/test_template_harness_reading_blocks.py docs/plans/template-field-id-vocabulary-boundary-refactor.md`
    仅命中当前 exact gap helper、反向测试和计划记录；`skipped.strip()` / trailing strip tolerance
    已无残留。
  - 未完成层级：本轮没有新增三校真实 inventory replay、live Agent E2E 或 product acceptance；只能说明
    Harness 在 `logic/contract` 层不再靠跳过可见 whitespace 来解析 ordered parts。
- Phase 2-3 的新增内部 span ledger Agent-facing denylist 已补到 `logic/contract`：
  - `src/docfit/template/judgment_shape.py` 现在把 `object_text_spans` 作为 Agent-authored internal
    ref 拒绝，top-level semantic judgment 和 `parts[]` 中都不能夹带该内部账本字段。
  - `src/docfit/app/prepare_template.py` 的 Agent revision packet sanitizer 也把
    `object_text_spans` 作为内部 token 清洗；即使下游 blocker code / missing_requirement /
    message 误提这个词，Agent-visible packet 也会落回 semantic judgment / reading packet 语言。
  - 新增/更新
    `tests/contract/test_template_judgment_shape.py::test_ordered_semantic_parts_rejects_legacy_field_aliases_and_agent_ids`、
    `test_ordered_semantic_parts_rejects_agent_authored_part_internal_refs` 和
    `tests/contract/test_prepare_template_runtime.py::test_materialization_readiness_feedback_is_sanitized_for_agent_revision`
    证明该字段不能由 Agent 输出，也不会泄露到 revision packet。
  - `logic/contract` 验证：denylist/sanitizer focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_judgment_shape.py tests/contract/test_prepare_template_runtime.py`
    -> `42 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/judgment_shape.py src/docfit/app/prepare_template.py tests/contract/test_template_judgment_shape.py tests/contract/test_prepare_template_runtime.py`
    -> passed；本轮相关完整 focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py tests/contract/test_template_judgment_shape.py tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py`
    -> `155 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；宽模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `494 passed`；`git diff --check` -> passed。
  - 残留扫描：`rg -n "object_text_spans" .claude/skills/docfit-school-extract src/docfit/app/prepare_template.py src/docfit/template/judgment_shape.py src/docfit/template/reading_packet.py src/docfit/template/harness.py tests/contract/test_agent_boundary_guardrails.py tests/contract/test_prepare_template_runtime.py tests/contract/test_template_judgment_shape.py tests/contract/test_template_reading_packet.py tests/contract/test_template_harness_reading_blocks.py`
    仅命中内部实现、denylist/sanitizer 和合同测试；Skill 树没有新增该内部字段。
  - 未完成层级：本轮没有新增三校真实 inventory replay、live Agent E2E 或 product acceptance；只能说明
    新增内部 span ledger 不进入 Agent 输出合同或 Agent revision 工作面。
- Phase 3 的三校代表 current-code inventory replay 已补到 `real replay`：
  - replay root:
    `/private/tmp/docfit-phase3-inventory-replay-20260904024116`。脚本把
    `temp/field-id-vocab-boundary-three-school-live-20260903/{hunau-cover,njau-abstract-cn,pku-abstract-cn}`
    复制到 `/private/tmp`，读取既有 unit-boundary checkpoint 和既有 Agent structured output，
    再用当前代码路径 `_post_unit_inventory_from_checkpoint()` + `_semantic_coverage_feedback()`
    重建 Harness inventory 并重新提交 semantic judgments；没有信任旧落盘 inventory。
  - HUNAU cover: `objects=128`、`reading_blocks=16`、`blocks_with_object_text_spans=16`、
    `judgments=16`、`ordered_parts=16`、`resolved_spans=16`、`slot_refs=8`、`vocabulary_size=54`。
  - NJAU Chinese abstract: `objects=43`、`reading_blocks=8`、`blocks_with_object_text_spans=8`、
    `judgments=8`、`ordered_parts=9`、`resolved_spans=9`、`slot_refs=3`、`vocabulary_size=54`。
  - PKU Chinese abstract: `objects=95`、`reading_blocks=10`、`blocks_with_object_text_spans=10`、
    `judgments=10`、`ordered_parts=11`、`resolved_spans=11`、`slot_refs=1`、`vocabulary_size=54`。
  - 三个 case 均为 `status=ok`；Agent semantic output 中未出现
    `semantic_field`、`registry_field`、`slot_id`、`span_id`、`resolved_spans`、
    `covered_object_ids` 或 `object_text_spans`；`fields_missing_from_vocabulary=[]`，
    且 Harness `resolved_spans.field_id` 集合与 Agent ordered parts 的 `field_id` 集合一致。
  - 未完成层级：这只是三校代表 current-code `real replay`，不是新的 live Agent E2E，也不是
    final DOCX / fill-contract / visual review 的 product acceptance。Phase 8 的三校所有 logical
    units 完整矩阵仍未完成。
- Phase 5-6 的 materializer 段落顺序 fallback 已删除到 `logic/contract`：
  - `src/docfit/template/materialization/runtime.py` 不再在 Harness inventory object locator / paraId
    无法解析时，按 reading block 数组下标 fallback 到第 N 个 Word paragraph。已接受的
    `fill_slot` 必须通过明确的 Harness inventory object locator 映射到真实段落；否则不能写
    candidate DOCX。
  - runtime 新增 slot execution closure gate：compiled plan 中每个 accepted
    `MATERIALIZE_SLOT` 的 Harness `slot_ref` 都必须产生对应 `materialize_slot` operation。缺失时抛出
    `slot_materialization_unexecutable`，责任层归为 `harness`，而不是静默跳过到 publication 阶段。
  - `tests/contract/test_template_materialization_runtime.py` 的 runtime fixture inventory 不再使用
    `objects=[]` 隐式依赖段落顺序；新增
    `test_materializer_fails_closed_on_unresolved_slot_paragraph_locator` 证明 slot paragraph locator
    无法解析时 fail closed 且不写 output file。
  - `logic/contract` 验证：focused materializer gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_runtime.py`
    -> `20 passed`；wider focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py tests/integration/test_template_materialization_replay.py tests/contract/test_publication_style_handoff.py tests/contract/test_prepare_template_runtime.py`
    -> `159 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/materialization/runtime.py tests/contract/test_template_materialization_runtime.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    `git diff --check` -> passed；残留扫描
    `rg -n "index fallback|fallback to paragraph|paragraphs\\[index\\]|slot_materialization_unexecutable|unresolved_slot_paragraph_locator" src/docfit/template/materialization/runtime.py tests/contract/test_template_materialization_runtime.py`
    仅命中新 fail-closed error code 和测试名，不再有 paragraph-index fallback。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    materializer runtime 在 `logic/contract` 层不再通过段落顺序 fallback 制造可执行闭合。
- Phase 6 的 no-slot publication source-noop 语义 provenance 门已补到 `logic/contract`：
  - `src/docfit/template/artifact.py` 不再允许调用方只传 `allow_no_slots=True` 就发布
    `slots=[]` 的 fill-contract。无 slot 发布现在也必须读取 accepted Harness
    `object-inventory.json` 和 `semantic-judgments.json`，校验 source hash、semantic digest、
    input `field_id_vocabulary` 和 ordered parts 当前形状。
  - 若发布的 no-slot candidate 不是原始 source path，还必须存在并通过绑定检查的
    `post-unit-materialization/materialization.json`；因此 generated-only 或 cleanup-only no-slot
    candidate 不能绕过 materialization receipt。若 candidate 就是原始 source，则 review 中不能含
    `cleanup` 或 `generated_content` 这类需要 materialization effect 的 part。
  - no-slot review 中出现的任何 `field_id` 也必须来自 accepted `field_id_vocabulary` 并存在于当前
    Registry snapshot；`fill_slot` / `body_structure` 仍必须发布 slot，不能被 no-slot 路径吞掉。
  - `tests/contract/test_publication_style_handoff.py` 新增
    `test_o1_publish_rejects_no_slot_publication_without_accepted_semantics` 和
    `test_o1_publish_rejects_no_slot_materialized_candidate_without_receipt`；合法
    `test_o1_publish_allows_accepted_terminal_source_noop_without_slots` 现在必须先写入 accepted
    Harness review，并断言 fill-contract provenance 记录
    `accepted_no_slot_semantic_review`。
  - `logic/contract` 验证：publication focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_publication_style_handoff.py`
    -> `36 passed`；wider app/materializer gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py`
    -> `144 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/artifact.py tests/contract/test_publication_style_handoff.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    `git diff --check` -> passed。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    publication / fill-contract 在 `logic/contract` 层不再让无 slot 输出绕过 Harness semantic
    provenance。
- Phase 6 的 body-structure section content-control 发布残留已删除到 `logic/contract`：
  - `src/docfit/template/artifact.py` 不再把 Registry `content_type=section` 的 content control
    当作 `structure_count` 计数后静默跳过。任何带 `body.chapters` 这类 section field alias/tag 的
    final DOCX content control 都返回 `body_structure_container_field_published`。
  - 这与前序 body-structure container field unpublished 决策保持一致：外层正文结构容器只能是无发布
    alias/tag 的 Word 分组；fill-contract 和 publication slot protocol 只承认可发布 member
    fields 的 Harness `span_ref + field_id` 派生 `slot_ref`。
  - `tests/contract/test_publication_style_handoff.py` 新增
    `test_o1_publication_slot_protocol_rejects_body_structure_container_field_marker` 和
    `test_o1_publish_rejects_body_structure_container_field_control`，分别覆盖轻量 publishability
    检查和最终 `publish_template_artifact`。
  - `logic/contract` 验证：publication focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_publication_style_handoff.py`
    -> `38 passed`；wider app/materializer gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_publication_style_handoff.py tests/integration/test_template_materialization_replay.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_compiler.py tests/unit/test_materialization_readiness.py`
    -> `146 passed`；相关 ruff
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check src/docfit/template/artifact.py tests/contract/test_publication_style_handoff.py`
    -> passed；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    `git diff --check` -> passed。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    publication 在 `logic/contract` 层不再容忍旧 body-structure container field content control。
- Phase 4-6 的 direct `docfit_apply(materialize_structure)` 父级 slot identity 已删除到
  `logic/contract`：
  - direct post-unit action package 仍能请求正文结构物化，但父级结构字段现在只能作为
    `structure_ref` 选择已输入 Registry 的 section parent；不能再携带顶层 `field_id` /
    `slot_ref`，也不能把 `body.chapters` 这类 section parent 写成发布字段控件。
  - `src/docfit/tools/service.py` 对旧包形状 fail closed 为
    `body_structure_parent_slot_ref_retired`，并且只从 reviewed members 的
    `field_id + slot_ref` 校验 Harness accepted `resolved_spans`。`src/docfit/template/object_mutation.py`
    的外层 body-structure Word 分组控件只写内部 `w:id`，不写 `w:alias` 或 `w:tag`；
    member content controls 继续使用 Harness `span_ref + field_id` 派生的 `slot_ref`。
  - `tests/contract/test_docfit_apply_tool.py` 将合法 direct structure package 更新为
    `structure_ref + members[]`，并新增旧父级 `field_id/slot_ref` fail-closed 反例；
    `tests/unit/test_object_mutation_content_controls.py` 新增 XML 级断言，证明外层结构控件无发布
    field identity，内层成员控件保留 member `field_id/slot_ref`。
  - `tests/contract/test_template_materialization_receipts.py` 的 receipt fixture 同步补上
    `covered_object_ids + locator`，不再用 `objects=[]` 隐式依赖已删除的 paragraph-index fallback。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py tests/unit/test_object_mutation_content_controls.py`
    -> `42 passed`；receipt/apply/XML gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_template_materialization_receipts.py tests/contract/test_docfit_apply_tool.py tests/unit/test_object_mutation_content_controls.py`
    -> `43 passed`；wider materialization gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_apply_tool.py tests/unit/test_object_mutation_content_controls.py tests/contract/test_publication_style_handoff.py tests/contract/test_template_materialization_runtime.py tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_compiler.py tests/integration/test_template_materialization_replay.py tests/unit/test_materialization_readiness.py`
    -> `177 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py`
    -> `496 passed`；相关 `ruff`、`mypy src` 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    direct apply / DOCX mutation 在 `logic/contract` 层不再保留 body-structure 父级 slot
    identity 旧协议。
- Phase 3/7 的 unit-boundary checkpoint unit alias fallback 已删除到 `logic/contract`：
  - Agent 当轮 unit-boundary structured output 仍使用当前 schema 的 `units[]`，但 Host 落盘后的
    resume proof / checkpoint / post-unit inventory 入口只接受 Harness-resolved `resolved_units[]`。
    旧持久态只有 `units[]` 或 `accepted_units[]` 时，不再被当成可恢复 checkpoint 迁移。
  - `src/docfit/app/prepare_template.py` 的 `_validate_unit_boundary_checkpoint()` 不再用
    checkpoint `units[]` 兜底；`_checkpoint_units()` 不再用 `accepted_units[]` / `units[]`
    兜底，缺 `resolved_units[]` 时返回 `post_unit_inventory_units_missing`。post-unit prompt
    context 也只从 `resolved_units[]` 摘要 accepted units。
  - `tests/contract/test_prepare_template_runtime.py` 新增 resume proof 旧 `units[]` 反向用例和
    post-unit inventory 旧 `units[]` / `accepted_units[]` 反向用例。
  - `logic/contract` 验证：focused runtime gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py`
    -> `30 passed`；相关边界 gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_evidence_tool.py tests/contract/test_docfit_check_tool.py tests/contract/test_tool_context_return_contract.py tests/agent/school_extract_v2/test_agent_first_prepare_template.py`
    -> `110 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py`
    -> `498 passed`；相关 `ruff`、`mypy src` 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    checkpoint / post-unit inventory 在 `logic/contract` 层不再从旧 unit alias 持久态恢复。
- Phase 5-6 的 slot handler 字段名前缀版式推断已删除到 `logic/contract`：
  - `src/docfit/template/materialization/handlers/slots.py` 不再把
    `thesis.title.*` 这类字段 ID 命名模式当作标题版式规则。title slot 是否需要清理缩进并居中，
    只来自当前 Registry snapshot 的内部 `materialization.slot_layout: centered_title` 元数据。
  - `src/docfit/fields/registry.py` 现在保留并校验内部 `materialization` 元数据，但
    `pre_input_vocabulary()` 不把该元数据暴露给 Agent；Agent 仍只能从输入词表选择字段 ID，
    不能看到或填写物化版式策略。
  - 新增/更新
    `tests/unit/test_field_registry_v2.py::test_registry_keeps_materialization_metadata_internal_to_snapshot`、
    `tests/contract/test_template_materialization_handlers.py::test_slot_handler_uses_registry_materialization_layout_not_field_id_prefix`
    和
    `tests/contract/test_template_materialization_runtime.py::test_materializer_preserves_title_prefix_layout_without_registry_layout_metadata`；
    反向证明同样是 `thesis.title.zh`，没有 Registry 版式声明时 runtime 会保留源段落右对齐和缩进。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/unit/test_field_registry_v2.py tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_runtime.py`
    -> `52 passed`；相关 `ruff` 通过；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `513 passed`。
  - 未完成层级：本轮没有新增 live Agent E2E 或 product acceptance；只能说明 handler/materializer
    在 `logic/contract` 层不再根据字段 ID 前缀推断版式行为。
- Phase 2-3 的 semantic coverage feedback 旧对象动作口径已删除到 `logic/contract`：
  - `src/docfit/app/prepare_template.py` 不再把 raw Harness semantic coverage
    `failure.suggested_actions` 原样抛到 postcondition `ToolFailure`。post-unit checkpoint report
    和 complete-output candidate selection 都改用 Agent/用户可见投影：只给
    `reading_block_id` / `reading_range_id`、当前 unit reading packet、ordered parts 和
    `field_id_vocabulary` 相关动作。
  - `src/docfit/template/harness.py` 的 semantic coverage raw suggested actions 不再生成
    `cover_missing_objects`、`remove_or_resubmit_inventory_for_unknown`、
    `merge_or_split_overlapping_objects` 或 `fill_empty_judgments_for`。缺失/重叠/空判断优先命名
    reading blocks；无法映射到 reading block 时 fail closed 为重建 current reading packet 或修正
    semantic scope，而不是要求调用者按底层 object id 修复。
  - `docs/contracts/template-extraction.md` 的 runtime Agent deny-list 明确补入
    `object_id`、`object_ids`、`covered_object_ids`；`tests/contract/test_agent_boundary_guardrails.py`
    新增 object/coverage blocker 和 failure action sanitizer 反例，`tests/contract/test_prepare_template_runtime.py`
    新增 postcondition failure action sanitizer 反例。
  - `logic/contract` 验证：focused feedback gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_agent_boundary_guardrails.py tests/contract/test_harness_feedback_helpfulness.py tests/contract/test_prepare_template_runtime.py`
    -> `45 passed`；Harness/Tool coverage gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_agent_boundary_guardrails.py tests/contract/test_harness_feedback_helpfulness.py tests/contract/test_prepare_template_runtime.py tests/contract/test_template_harness_reading_blocks.py tests/contract/test_tool_contract.py tests/contract/test_docfit_check_tool.py`
    -> `113 passed`；相关 `ruff`、`mypy src` 和 `git diff --check` 通过；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `516 passed`。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    App/Harness semantic coverage feedback 在 `logic/contract` 层不再保留旧 object-id 修复动作。
- Phase 3 / Phase 8 的 ordered parts 空白分隔符和 PKU `04-abstract-en` 真实回放已补到
  `logic/contract` + `real replay` + publication 证据：
  - 产品影响：`Directed by Professor Your Professor` 和
    `KEY WORDS: Your; English; Keywords; Here` 这类 label + 空格 + slot 的真实文本现在可由
    Agent 输出两个有序语义 part 表达；Agent 仍不能输出空白-only part、`span_ref`、`slot_ref`
    或底层 Word/object 引用，非空白 gap 仍 fail closed。
  - 发现并修复的 Harness 缺口：PKU `04-abstract-en` real replay v2 使用当前代码时停在
    `template_ordered_span_resolution_incomplete`，两个 blocker 都是 `ordered_part_text_gap`
    且 `uncovered_text=" "`。根因是 `parts[].text` 被 trim 后，Harness 又把纯空白分隔符当成
    可见覆盖缺口；这让常见 label/slot 空格边界不可表达。
  - 代码证据：`src/docfit/template/harness.py` 的 ordered span resolver 现在允许跳过纯空白分隔符；
    `tests/contract/test_template_harness_reading_blocks.py` 反转旧 whitespace-gap 测试为成功路径，
    并新增非空白 gap 仍返回 `ordered_part_text_gap` 的反例。
  - live E2E 尝试：fresh PKU `04-abstract-en`
    `temp/field-id-vocab-boundary-current-pku-live-20260904/pku-04-abstract-en-vocabonly`
    在 Minimax backend 下 120s 内没有任何 SDK event、tool call 或 structured result：
    `template_agent_no_progress_timeout`，trace 中 `sdk_query_count=0`、`tool_uses=[]`、
    `skills_loaded=[]`。归因是 live Agent/backend no-progress，不是 Harness/Tool/schema
    接受失败，因此不能宣称该切片 live E2E 通过。
  - real replay root:
    `temp/field-id-vocab-boundary-current-pku-live-20260904/pku-04-abstract-en-real-replay-v3`。
    输入为真实 PKU 英文摘要 DOCX，source hash
    `55fe7daeec89735a51fde6382869749770ccd2c54a3d911a565cccad7855c3d3`，Field Registry
    digest `7dd6c3682923b6de07da9f1c80941f9c363fa71b50a43a41bea28645ac037cc4`，
    pre-input vocabulary size `54`。
  - Harness 结果：`submit_object_inventory=ok`、`submit_semantic_judgments=ok`；
    `object_count=27`、`covered_object_count=27`、`judgment_count=6`、`resolved_span_count=8`、
    `slot_ref_count=5`。Agent 原始判断落盘后除 Harness 附加的 `resolved_spans` 外只包含
    `scope` 和 `parts`；slot 字段为 `thesis.title.en`、`author.name.en`、`advisor.name.en`、
    `abstract.en`、`keywords.en`，全部来自输入词表。
  - Materialization / publication 结果：
    `_select_host_candidate_for_accepted_semantics()` 生成
    `work/.docfit/post-unit-materialization/candidate-0002.docx`，hash
    `af3c7e4a8cf4cfbd595b7c46f00fd890bf010427b180f6f60086326d27e9827d`；
    `work/.docfit/post-unit-materialization/materialization.json` 为 `status=ok`、
    `operation_count=5`、`receipt_count=5`、`publishability.status=ok`。`publish_template_artifact()`
    生成 `output/final-template.docx` 和 `output/fill-contract.yaml`，build report 为 `status=ok`、
    `counts.slot=5`，每个 fill-contract slot 的 `slot_ref` 均为
    `reading_block_id + part_index + field_id` 的 Harness 派生形式。
  - 验证结果：`docfit tools validate input/school-template.docx output/final-template.docx`
    中 ZIP/XML reopen 和 OfficeCLI OpenXML 为 `ok`，source hash 绑定为 `ok`，placeholder scan 为
    `ok`；因为发生预期 slot 替换，content preservation 有 `missing_object_count=5` warning；
    `visual_review_coverage` 仍是 blocking issue（`current_visual_snapshot=false`），完整全页视觉
    review 尚未完成；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run docfit doctor --require visual-renderer`
    -> `Gate visual-renderer: NOT_READY`，当前本机 `libreoffice_visual_renderer=NOT_READY`。
    输出 `fill-contract.yaml`、publication、materialization 和 Harness semantic
    账本扫描未发现 `slot_id`、旧字段 alias、旧 fallback 或后置 registry field 形状。
    2026-09-04 复查确认同一 root 的 fill-contract 有 `slot_count=5`，slot 字段集合为
    `abstract.en`、`advisor.name.en`、`author.name.en`、`keywords.en`、`thesis.title.en`；
    所有 slot 字段都属于同一输入词表和 accepted Agent parts，所有 `slot_ref` 都是
    `reading_block_id + part_index + field_id` 的 Harness 派生形式。
  - `logic/contract` 验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py` -> `27 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py
    tests/integration/test_template_materialization_replay.py
    tests/contract/test_prepare_template_runtime.py
    tests/contract/test_publication_style_handoff.py` -> `107 passed`；相关 `ruff` 通过；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `517 passed`；`git diff --check` -> passed。
  - 未完成层级：fresh live Agent E2E 在 backend no-progress 前失败；全页视觉 review / human
    product acceptance 未完成；Phase 8 三校所有 logical units 的完整矩阵仍未完成。
- Phase 2-4 的隐藏 `scoped_closure_v1` / `closure_aggregation` 和
  `coverage_closure` 旧 coverage Tool 协议已删除到
  `logic/contract`：
  - 产品影响：模板提取不再保留一条“提交 subagent closure payload，里面带
    `assigned_scope.object_ids`，再由 Tool 聚合覆盖”的旁路。post-unit coverage 只通过当前
    Harness 的 unit reading packet、`scope + ordered parts`、field vocabulary、resolved span
    和覆盖/冲突 gate 闭合；也不再保留单独 `docfit_check(coverage_closure)` 返回 ok 的
    post-unit semantic coverage Tool 门禁。
  - 代码证据：删除 `src/docfit/template/closure.py`；`src/docfit/template/judgment_shape.py`
    不再导出 `SCOPED_CLOSURE_V1`、`CLOSURE_REVIEW_CONTEXT_V1` 或对应 validator，
    `EXCHANGE_SCHEMA_VERSIONS` 只保留当前语义 exchange；`src/docfit/tools/service.py`
    对 `docfit_check(closure_aggregation)` 和 `docfit_check(coverage_closure)` 统一返回
    `check_kind_retired`，即使调用者传入旧 `scoped_closure_v1` payload 也不会读取或聚合
    `object_ids`；`src/docfit/tools/surface.py` 不再把 `coverage_closure` 暴露为 check enum。
  - 测试证据：删除 `tests/contract/test_subagent_closure_aggregation.py` 的正向旧协议保护；
    `tests/contract/test_subagent_runtime_context_contract.py` 删除旧 closure task packet 正向断言；
    `tests/contract/test_template_exchange_contracts.py` 固定 `scoped_closure_v1` 和
    `closure_review_context_v1` 不属于 active exchange schema；`tests/contract/test_docfit_check_tool.py`
    新增 `closure_aggregation` 和 `coverage_closure` 直接 fail-closed 反例；
    `tests/contract/test_tool_surface.py` 固定 `coverage_closure` 不属于公开 check enum。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_exchange_contracts.py tests/contract/test_docfit_check_tool.py
    tests/contract/test_subagent_runtime_context_contract.py tests/contract/test_tool_surface.py`
    -> `50 passed`；相关 `ruff` 通过；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `505 passed`；`git diff --check` -> passed。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    旧 subagent/object-id coverage 输入协议在 `logic/contract` 层不再存在正向执行路径。
- Phase 7 / E1 observability proof 的旧 post-unit false-green 已反转到
  `logic/contract`：
  - 产品影响：质量门不再把旧 `semantic_judgments: [{judgment_id, judgment}]`、
    Agent-authored `final_docx` / render 字段，或 post-unit Agent 使用
    `docfit_check` / `docfit_apply` 当作完整模板提取证据。当前 green trace 必须表达
    `status + summary + scope + ordered parts`，runtime Agent tool surface 只能出现
    `docfit_evidence`，Host 侧 publication receipt 负责验证和视觉证据绑定。
  - 代码证据：`src/docfit/evals/template_observability.py` 的 vertical-slice gate 改为验证
    current post-unit completion contract、retired runtime tools denylist、publication
    `validation_bound` / `visual_review_bound` receipt；`tests/contract/test_observability_design_conformance.py`
    和 `tests/contract/test_template_observability_proof.py` 的正向 trace 改成 current
    `scope + parts`，并新增旧 `judgment_id` shape fail-closed 反例。
  - 文档证据：`docs/status/active/docfit-school-extract-v2.md` 不再声明 Subagent 返回
    `scoped_closure_v1`，也不再把 `docfit_check` / `docfit_apply` 说成 post-unit
    Agent-visible Tool surface；`tests/contract/test_documentation_contract.py` 固定该 active
    status 只能以“已退役”口径提旧 closure/coverage 协议。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_observability_design_conformance.py
    tests/contract/test_template_observability_proof.py
    tests/contract/test_documentation_contract.py
    tests/contract/test_agent_boundary_guardrails.py tests/contract/test_tool_surface.py`
    -> `29 passed`；相关 `ruff` 通过；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；只能说明
    observability/E1 证明层不再接受旧 post-unit 输出形状和旧 Agent tool surface。
- Phase 7 的旧 quality-gate plan 当前入口误导已压缩为 tombstone：
  - 产品影响：默认文档入口不再保留整段旧 post-unit 字段别名、结构绑定、coverage 和 fallback
    正向说明；后续执行只应读取当前 field vocabulary boundary plan、Contract 和模块流程文档。
  - 文档证据：`docs/plans/template-semantic-quality-gate-repair-plan.md` 只保留
    `status: SUPERSEDED` / `retention: historical tombstone only` 和当前边界指针；
    `docs/modules/template-extraction.md` 不再把提交 `docfit_apply` 写成 subagent 不负责的当前
    post-unit 交接项；`docs/plans/README.md` 更新时间同步到 2026-09-04。
  - 测试证据：`tests/contract/test_documentation_contract.py` 新增 tombstone 合同和模块文档
    `docfit_apply` 暴露反例，防止旧计划正文或旧 tool 责任描述被重新引入当前入口。
  - `logic/contract` 验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_documentation_contract.py` -> `7 passed`；当前入口旧词扫描只剩
    Contract fail-closed 禁止清单和 active status 的已退役说明。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这是文档
    contract 收口，不能替代 Phase 8 产品验收。
- Phase 7 的旧 post-unit materialization plan / ADR / template gate 当前入口误导已反转到
  `logic/contract`：
  - 产品影响：默认计划索引不再把 2026-08-26 的 materialization 分层迁移计划列为活跃计划；
    该计划和 ADR 0003 都只保留 tombstone，不再传播旧 `registry_field`、`structure_ref`、
    `members`、`covered_reading_block_ids` 或 docx-edit-first 的模板执行口径。
  - 文档证据：`docs/plans/refactor-post-unit-materialization.md` 压缩为历史 tombstone，但作为
    refactor gate 仍保留 `status: DONE`；`docs/adr/0003-template-semantic-quality-gate-boundaries.md`
    压缩为 superseded tombstone；`docs/plans/README.md` 将 post-unit materialization 计划从
    活跃计划表移到已完成/已迁移。
  - 测试证据：`tests/contract/template_gate/test_agent_first_tool_contract.py` 不再正向断言模板
    mechanics 建在 `docx_edit` 的 `field_registry` / `members` / `toc_entries` schema 上，而是
    固定 template runtime profile 只暴露 `docfit_evidence`；`tests/contract/test_documentation_contract.py`
    新增 materialization plan 与 ADR tombstone 合同。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_documentation_contract.py tests/contract/template_gate/test_agent_first_tool_contract.py
    tests/contract/test_template_observability_proof.py` -> `14 passed`；相关 `ruff` 通过；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `510 passed`；`git diff --check` -> passed。当前入口旧词扫描只剩
    Contract fail-closed 禁止清单和测试反例。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这是当前入口
    文档和测试 false-green 清理，不能替代 Phase 8 产品验收。
- Phase 7 / runtime profile 的全工具 agent 与模板抽取 Skill 已解耦到 `logic/contract`：
  - 产品影响：默认五工具 Agent profile 不再同时加载 `docfit-school-extract` 和
    `docx_edit` / `docfit_apply` 等全量 DOCX 操作面；模板抽取 Skill 只保留在
    `prepare-template` 的 semantic-only runtime profile 中，final word 生成的 legacy conversion
    route 只加载 `convert-thesis`。
  - 代码证据：`src/docfit/app/agent.py` 拆出 `DOMAIN_SKILL_NAMES` 和默认
    `SKILL_NAMES=("convert-thesis",)`；`src/docfit/app/convert.py` 的 startup/system prompt 与
    postcondition 不再要求加载两个 project Skills；`src/docfit/app/smoke.py` 的 subagent smoke
    不再要求加载模板抽取 Skill；`src/docfit/app/doctor.py` 仍检查两个领域 Skill 文件存在，但
    SDK 配置验收固定 full-tool profile 只加载转换 Skill。
  - 测试证据：`tests/contract/test_permission_contract.py` 固定默认 full-tool options 不包含
    `docfit-school-extract`，且不会再出现 “two enabled domain Skills” 运行时提示；
    `tests/integration/test_m2_convert.py` 的转换 fixture 改为只证明 `convert-thesis` 被加载。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_permission_contract.py tests/contract/test_skill_contract.py
    tests/contract/test_prepare_template_runtime.py
    tests/agent/school_extract_v2/test_prepare_template_startup_context_snapshot.py
    tests/unit/test_doctor.py tests/integration/test_m2_convert.py` -> `80 passed, 1 warning`；
    相关 `ruff` 通过；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `510 passed`；
    运行时双 Skill 指令扫描
    `rg -n "Load both project Skills|both required DocFit domain Skills|docfit-school-extract as adaptive|Use the two enabled domain Skills|skills_loaded=\\(\\"docfit-school-extract\\", \\"convert-thesis\\"" src tests docs -g '!temp/**'`
    -> no matches。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这是运行时
    profile / prompt / postcondition 的 contract 收口，不能替代 Phase 8 产品验收。
- Phase 5-6 的无 `resolved_spans` hint 删除兜底和旧测试正向分支已删除到
  `logic/contract`：
  - 产品影响：materializer 不再保留一条“slot judgment 没有 Harness-resolved span 时，根据
    可见文本包含另起一页/字体字号参照就删除段落”的旁路。删除段落只能来自 accepted ordered
    `cleanup` part 和 Harness `span_ref`；可执行 `fill_slot` 缺 `slot_ref` 时继续 fail closed。
  - 代码证据：`src/docfit/template/materialization/runtime.py` 删除 `not resolved_spans` +
    `block_removes_hint_without_slot()` 的 `remove_hint` 分支；`src/docfit/template/materialization/layout_placeholders.py`
    删除该 helper；`src/docfit/template/materialization/__init__.py` 不再导出它；
    `src/docfit/template/materialization/models.py` 和 `receipts.py` 不再承认 `remove_hint`
    mutation action。
  - 测试证据：`tests/contract/test_template_materialization_handlers.py` 删除旧 helper 正向测试；
    `tests/contract/test_tool_context_return_contract.py` 删除已经不可达的 `registry_field`
    evidence focus 正向分支，防止未来把该 focus 加回 enum 时意外变成 green path。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_materialization_handlers.py
    tests/contract/test_template_materialization_runtime.py
    tests/contract/test_template_materialization_receipts.py
    tests/unit/test_materialization_readiness.py
    tests/contract/test_tool_context_return_contract.py
    tests/contract/test_docfit_evidence_tool.py tests/contract/test_tool_surface.py`
    -> `106 passed`；相关 `ruff` 通过；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`
    -> passed；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `509 passed`；`git diff --check` -> passed。
    旧 helper / action 扫描
    `rg -n 'remove_hint|REMOVE_HINT|block_removes_hint_without_slot' src/docfit/template src/docfit/app src/docfit/tools tests/contract tests/integration tests/unit -g '!**/__pycache__/**'`
    -> no matches。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这是旧
    materializer fallback 和旧测试 residual 清理，不能替代 Phase 8 产品验收。
- Phase 0/5-7 的旧协议正向路径 residual 已复查到 `logic/contract`：
  - 产品影响：本轮复查没有发现新的目标内旧字段 ID 推断、旧字段别名、旧 coverage 输入协议、
    旧 slot identity 或旧 materializer fallback 成功路径。`covered_object_ids` 的残留命中仍限定在
    Harness / reading packet 内部账本、resolved span provenance、unit-boundary coverage 输出或
    fail-closed 反例；`registry_field` / `semantic_field` 的残留命中限定在 denylist、feedback
    sanitizer、`registry_field_runtime_removed` 和反向测试。
  - 审计证据：`test_tool_contract.py` 的旧 object / locator coverage 用例均断言
    `ordered_semantic_parts_invalid`；`test_template_harness_reading_blocks.py` 的
    `registry_field_no_candidates` 用例断言旧字段别名或 sentinel 失败；Tool service 对
    `focus=registry_field` 在读取 source / Registry 前返回 `registry_field_runtime_removed`；
    production `slot_id` / `intent_id` / `judgment_id` 扫描只剩 Agent-output denylist 和
    parent structure slot_ref retired gate。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_materialization_handlers.py
    tests/contract/test_template_materialization_runtime.py
    tests/contract/test_template_materialization_receipts.py
    tests/unit/test_materialization_readiness.py
    tests/contract/test_tool_context_return_contract.py
    tests/contract/test_docfit_evidence_tool.py tests/contract/test_tool_surface.py`
    -> `106 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `509 passed`；相关 `ruff` 通过；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> passed；`git diff --check`
    -> passed。旧 helper/action 扫描
    `rg -n 'remove_hint|REMOVE_HINT|block_removes_hint_without_slot' src/docfit/template src/docfit/app src/docfit/tools tests/contract tests/integration tests/unit -g '!**/__pycache__/**'`
    -> no matches。
  - 未完成层级：本轮没有新增真实 DOCX replay、live Agent E2E 或 product acceptance；这是旧
    协议正向路径 residual 的 contract 复查，不能替代 Phase 8 产品验收。
- Phase 1/3/8 的三校 current-code inspect packet 输入面矩阵已补到 `logic/contract` +
  deterministic real-input replay：
  - 产品影响：真实 logical-page DOCX 经过当前 inspect + reading packet builder 后，Agent
    输入面稳定包含 `field_id_vocabulary`、`field_vocabulary_digest`、`reading_blocks[].block_id`、
    `reading_blocks[].range_id` 和可见文本；Agent-visible packet 不暴露 `span_id`、
    `span_ref`、`slot_ref`、`object_id`、`object_ref`、`covered_object_ids`、
    `object_text_spans`、`fingerprint` 或 `locator`。这证明真实输入面继续满足“Agent 只能从词表选择
    field_id，Harness 才持有底层 Word mapping”的入口合同。
  - 默认测试证据：新增
    `tests/integration/test_template_materialization_replay.py::test_three_school_current_inspect_packets_carry_vocabulary_without_internal_refs`
    覆盖 HUNAU `01-cover`、NJAU `04-abstract-cn`、PKU `03-abstract-cn` 三校代表真实
    logical-page DOCX；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/integration/test_template_materialization_replay.py::test_three_school_current_inspect_packets_carry_vocabulary_without_internal_refs`
    -> `3 passed`。完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `512 passed`。
  - 全量手动 proof：本轮用相同 current-code inspect + packet builder 跑
    `temp/manual-gold-preparation/gold/10-school-assets/**/logical-pages/*.docx` 共 32 个真实
    logical-page DOCX，结果 `failures=[]`；代表计数包括 HUNAU `01-cover`
    `objects=28` / `reading_blocks=16`、HUNAU `04-paper-body` `objects=71` /
    `reading_blocks=53`、PKU `12-declarations` `objects=53` / `reading_blocks=14`。
  - 未完成层级：这不是 live Agent E2E，也不是 final-template / fill-contract 产品验收；它只证明
    三校真实输入在当前代码下能形成受控 Agent reading packet 和 pre-input vocabulary 工作面。
- Phase 3/7 的 unit-boundary proof `units -> resolved_units` fallback 已删除到
  `logic/contract`：
  - 产品影响：从 unit-boundary resume 进入 post-unit 时，App 不再把 Tool 返回的旧/非 canonical
    `units` 覆盖结果迁移成可继续执行的 `resolved_units`。当前 `docfit_check(unit_coverage)`
    会在自己的机械检查结果中写 canonical `resolved_units`；App 只接受该字段，缺失时直接
    `unit_boundary_proof_invalid`，不会继续构造 post-unit inventory。
  - 代码证据：`src/docfit/tools/service.py` 的 unit coverage 成功结果总是把 Harness-projected
    coverage units 写入 `resolved_units`；`src/docfit/app/prepare_template.py` 删除
    `result["units"]` fallback，并要求非空 `resolved_units`。
  - 测试证据：`tests/contract/test_prepare_template_runtime.py` 新增
    `test_resume_proof_rejects_unit_coverage_result_without_resolved_units`，反转旧 Tool result
    shape；`tests/contract/test_docfit_check_tool.py` 固定 current `unit_coverage` 对已解析 locator
    也返回带 `covered_object_ids` 的 `resolved_units`。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_prepare_template_runtime.py::test_resume_proof_validation_does_not_require_agent_render_ref
    tests/contract/test_prepare_template_runtime.py::test_resume_proof_rejects_unit_coverage_result_without_resolved_units
    tests/contract/test_prepare_template_runtime.py::test_resume_proof_rejects_legacy_units_only_checkpoint
    tests/contract/test_docfit_check_tool.py::test_t2_unit_coverage_expands_composite_text_anchors_into_closed_partition`
    -> `4 passed`；wider gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_check_tool.py`
    -> `63 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `513 passed`；相关 `ruff` / `mypy src` /
    `git diff --check` 通过。
  - 未完成层级：本轮没有新增 live Agent E2E 或 product acceptance；这是 App/Tool checkpoint
    shape 的 fail-closed 清理，不能替代 Phase 8 产品验收。
- Phase 3/6 的 post-unit 写包 Registry 隐式补全已删除到 `logic/contract`：
  - 产品影响：post-unit `docfit_apply` 和 direct `docx_edit` 写入口不再在 action package /
    Tool args 缺少 `field_registry` 时，自动补用 task root 中的默认 Registry。可写包必须显式携带
    与 accepted Harness phase review 同源的 `input/field-registry.*`，否则在写入前
    `field_registry_missing` fail closed；这避免把“task input 里存在 Registry 文件”误当成
    写包 provenance。
  - 代码证据：`src/docfit/tools/service.py::_require_pre_input_field_registry()` 现在先定位当前
    task input Registry，再要求 supplied Registry 非空且等于该输入 Registry；缺失和 swap 都在
    materializer/handler 之前失败。非 post-unit 的通用底层 `docx_edit` 仍要求显式
    `field_registry`，不会自行猜字段来源。
  - 测试证据：`tests/contract/test_docfit_apply_tool.py` 的 canonical `_write_action_package()`
    现在显式写 `field_registry: input/field-registry.json`；新增
    `test_t3_post_unit_apply_rejects_action_package_missing_field_registry` 和
    `test_t3_direct_docx_edit_post_unit_materialize_slot_requires_input_registry`，分别反转旧
    action package 缺 registry 和 direct write args 缺 registry 的隐式默认行为。
  - `logic/contract` 验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_apply_tool.py` -> `40 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `515 passed`；相关 `ruff` / `mypy src` /
    `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 post-unit 写入口 provenance 的 contract fail-closed 清理，不能替代 Phase 8 产品验收。
- Phase 1 的 `unit_evidence_packet` 无词表假入口已删除到 `logic/contract`：
  - 产品影响：post-unit Agent 不会再收到不带 `field_id_vocabulary` 的 unit reading packet。
    当 task input 缺少 Field Registry 时，`docfit_evidence(focus=unit_evidence_packet)` 在 packet
    返回前以 `field_registry_missing` fail closed；Agent 只能在已准备输入词表的工作面中做
    ordered semantic parts 判断。
  - 代码证据：`src/docfit/tools/service.py` 在 `focus == "unit_evidence_packet"` 时强制
    `_pre_input_field_vocabulary(root)` 非空；缺失时返回 request-origin failure，并指向先准备
    task input Field Registry，而不是构造无词表 packet。
  - 测试证据：`tests/contract/test_docfit_evidence_tool.py` 新增
    `test_unit_evidence_packet_requires_pre_input_field_vocabulary`；所有 unit packet 正向测试均显式
    准备 `input/field-registry.json`。`tests/contract/test_tool_context_return_contract.py` 的
    Agent-facing context 正向用例也同步准备 Registry，避免旧 mock 误导。
  - `logic/contract` 验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_evidence_tool.py` -> `31 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_tool_context_return_contract.py` -> `9 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_evidence_tool.py tests/contract/test_docfit_apply_tool.py`
    -> `71 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `516 passed`；相关 `ruff` / `mypy src` /
    `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Agent 输入面必须携带 pre-input vocabulary 的 contract fail-closed 清理，不能替代
    Phase 8 产品验收。
- Phase 4/6 的 Agent-visible `docfit_apply` 无 review 字段写入已删除到
  `logic/contract`：
  - 产品影响：`docfit_apply` 只要 action package 中的真实 edit action 需要 Field Registry
    (`materialize_slot` / `materialize_structure`)，就必须先存在 accepted Harness phase review；
    即使 task 尚无 unit-boundary checkpoint，也不能用 `batch_ref + input Registry` 直接写入字段槽位。
    普通非字段写入仍可走原有 candidate/source hash 保护，但不能借 `bind_field` 外层 operation 绕过
    ordered parts / span provenance。
  - 代码证据：`src/docfit/tools/service.py::DocFitToolService.apply()` 现在先读取 `batch_ref`
    并解析 packaged edit action，再按 action spec 判断是否强制 `_post_unit_phase_review()`；字段写入
    package 缺 review 时统一 `phase_review_required`，不会进入 Registry lookup、handler 或 edit。
  - 测试证据：`tests/contract/test_docfit_apply_tool.py` 新增
    `test_t3_apply_field_write_requires_phase_review_even_without_checkpoint`；旧
    `test_t3_apply_defaults_source_hash_from_bound_task_root` 改用非字段 `clear_content` package
    测 source_hash 默认；旧 invalid-field 无 review 断言反转为先停在 `phase_review_required`，
    edit failure 包装测试则显式准备 accepted review 后再进入 fake edit。
  - `logic/contract` 验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_apply_tool.py` -> `41 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `517 passed`；相关 `ruff` / `mypy src` /
    `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Agent-visible Tool 写入口的 fail-closed 清理，不能替代 Phase 8 产品验收。
- Phase 1/3 的 Harness object inventory 无词表中间态已删除到 `logic/contract`：
  - 产品影响：Harness 不再允许 post-unit object inventory 在缺少 task input Field Registry 时
    先写入、后等待 semantic submission 再失败。inventory 初始化本身必须带
    `field_id_vocabulary` 和 `field_vocabulary_digest`，否则 `field_registry_missing` fail closed；
    这让 Agent reading packet、Harness inventory 和 accepted review 三者都从同一份 pre-input
    vocabulary 起步。
  - 代码证据：`src/docfit/template/harness.py::_task_field_vocabulary()` 不再返回 `None`；
    `_store_inventory()` 总是写入 `field_id_vocabulary` / `field_vocabulary_digest`。读取旧无词表
    inventory 的 submit/status 防御门仍保留为 fail-closed，不作为成功路径。
  - 测试证据：`tests/contract/test_template_harness_reading_blocks.py` 新增
    `test_template_harness_inventory_requires_pre_input_vocabulary`，证明缺 Registry 时不写
    `work/.docfit/harness/object-inventory.json`；原有
    `test_template_harness_records_pre_input_vocabulary_baseline` 继续证明 inventory 和 accepted
    semantic review 共享同一 vocabulary digest。
  - `logic/contract` 验证：`UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py` -> `28 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `518 passed`；相关 `ruff` / `mypy src` /
    `test_documentation_contract.py` / `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Harness checkpoint 输入基线的 contract fail-closed 清理，不能替代 Phase 8 产品验收。
- Phase 1/3 的 unit / reading packet ID fallback 已删除到 `logic/contract`：
  - 产品影响：Harness 和 App 不再为缺失的 accepted `unit_id` 合成 `unit-0001` 或 `unit`，
    `UnitReadingPacket` 也不会生成无来源的 `unit:block-*` / `unit:range-*`。因此 Agent 看到的
    `reading_block_id` / `reading_range_id` 只能来自已接受的 unit-boundary 输出；Malformed
    checkpoint 或 Tool payload 会在进入 post-unit 语义拆分前 fail closed。
  - 代码证据：`src/docfit/template/harness.py::_unit_boundary()` 现在要求 `units[].unit_id`
    是非空字符串；`src/docfit/template/reading_packet.py::build_unit_reading_packet()` 要求
    `unit.unit_id` 非空；`src/docfit/app/prepare_template.py::_checkpoint_units()` 显式拒绝
    malformed `resolved_units`；`src/docfit/tools/service.py::_check_unit_boundaries()` 把低层
    `ToolFailure` 转成标准 mechanical feedback，而不是让异常泄出或继续执行。
  - 测试证据：`tests/contract/test_docfit_check_tool.py` 新增 direct Harness 和 Tool feedback
    两条缺 `unit_id` 反向测试；`tests/contract/test_template_reading_packet.py` 新增
    `test_unit_reading_packet_requires_unit_id_without_default_range_ids`；`tests/contract/test_prepare_template_runtime.py`
    新增 `test_post_unit_inventory_rejects_resolved_unit_without_unit_id`。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_check_tool.py tests/contract/test_prepare_template_runtime.py
    tests/contract/test_template_reading_packet.py` -> `72 passed`；packet/evidence/replay focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_reading_packet.py tests/contract/test_docfit_evidence_tool.py
    tests/integration/test_template_materialization_replay.py::test_three_school_current_inspect_packets_carry_vocabulary_without_internal_refs`
    -> `40 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `522 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache
    uv run mypy src`、相关 `ruff`、`test_documentation_contract.py` 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 unit / reading packet ID 来源的 contract fail-closed 清理，不能替代 Phase 8 产品验收。
- Phase 4 的公开 Tool failure-code 旧字段确认码已删除到 `logic/contract`：
  - 产品影响：公开 DocFit Tool surface 不再把旧 `field_not_registered` 暴露为 front contract
    failure code；`registry_binding` 已 retired，字段选择错误应回到 `field_id_vocabulary`
    工作面和 Harness semantic submission，而不是通过旧 Registry lookup 码让 Agent 认为还能后置查字段。
  - 代码证据：`src/docfit/tools/surface.py::TOOL_FAILURE_CODES` 移除 `field_not_registered`；
    `src/docfit/fields/registry.py::FieldRegistrySnapshot.lookup()` 的底层 fail-closed 错误保留为
    内部 Registry API 行为，不再属于公开 Tool surface contract。
  - 测试证据：`tests/contract/test_tool_surface.py::test_p2_failure_codes_cover_front_contract_failures`
    反转旧公开失败码断言；源码扫描 `rg -n "field_not_registered" src tests docs .claude ...`
    只剩 `src/docfit/fields/registry.py` 的底层 Registry lookup。
  - `logic/contract` 验证：focused gate `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_tool_surface.py` -> `10 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `522 passed`；`UV_CACHE_DIR=/private/tmp/docfit-uv-cache
    uv run mypy src` 和相关 `ruff` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Tool surface contract 的旧字段确认码清理，不能替代 Phase 8 产品验收。
- Phase 4 的公开 Tool surface 兼容命名已删除到 `logic/contract`：
  - 产品影响：公开 Tool surface 不再保留 `CANONICAL_*` / `*_FULL_AGENT_TOOL_NAMES`
    兼容别名，也不再接受 `include_legacy_tools` 参数。template semantic runtime 仍只暴露
    `docfit_evidence`；通用 DOCX tool adapters 改用当前 `DOCX_TOOL_ADAPTERS` 命名，不再把
    “legacy” 作为成功路径概念。
  - 代码证据：`src/docfit/tools/surface.py` 只导出当前
    `DOCFIT_GENERAL_*_FULL_TOOL_NAMES` 与 `DOCX_TOOL_ADAPTERS`；`src/docfit/tools/__init__.py`
    改为 `include_docx_tools`；`src/docfit/app/agent.py`、`src/docfit/app/prepare_template.py`
    和相关 contract tests 全部切到当前命名。源码扫描
    `rg -n "include_legacy_tools|LEGACY_DOCX_TOOL_ADAPTERS|CANONICAL_AGENT_TOOL_NAMES|READ_ONLY_AGENT_TOOL_NAMES|WRITE_AGENT_TOOL_NAMES|SUBAGENT_AGENT_TOOL_NAMES|CANONICAL_FULL_AGENT_TOOL_NAMES|READ_ONLY_FULL_AGENT_TOOL_NAMES|WRITE_FULL_AGENT_TOOL_NAMES|SUBAGENT_FULL_AGENT_TOOL_NAMES" src tests -g '*.py'`
    无命中。
  - 测试证据：`tests/contract/test_tool_surface.py` 反转旧别名断言；
    `tests/contract/test_tool_contract.py`、`tests/contract/template_gate/test_agent_first_tool_contract.py`、
    `tests/contract/test_subagent_runtime_context_contract.py` 和
    `tests/contract/test_prepare_template_security.py` 覆盖当前 surface 命名。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_tool_surface.py tests/contract/test_tool_contract.py tests/contract/template_gate/test_agent_first_tool_contract.py tests/contract/test_subagent_runtime_context_contract.py tests/contract/test_prepare_template_security.py tests/contract/test_prepare_template_runtime.py`
    -> `62 passed`；本轮合并 focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_evidence_tool.py tests/contract/test_tool_context_return_contract.py tests/contract/test_prepare_template_runtime.py tests/contract/test_tool_surface.py tests/contract/test_tool_contract.py tests/contract/template_gate/test_agent_first_tool_contract.py tests/contract/test_subagent_runtime_context_contract.py tests/contract/test_prepare_template_security.py`
    -> `104 passed`；完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `524 passed`；相关 `ruff` / `mypy src` / `test_documentation_contract.py` /
    `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Tool surface 命名和可调用参数的兼容层删除，不能替代 Phase 8 产品验收。
- Phase 1/3 的 `unit_evidence_packet` checkpoint unit alias fallback 已删除到
  `logic/contract`：
  - 产品影响：`docfit_evidence(focus=unit_evidence_packet)` 现在只从
    `unit-boundary-checkpoint.json` 的 `resolved_units[]` 查找 post-unit startup unit。旧
    `accepted_units[]` / `units[]` 持久态即使带有合法 `unit_id` 和 locator，也不能再构造
    Agent-visible reading packet；post-unit prompt JSON context 也只暴露 `resolved_units`。
  - 代码证据：`src/docfit/tools/service.py::_resolved_units()` 不再读取
    `accepted_units` 或 `units`；unit packet 缺 unit 时的修复建议不再提旧 shape；
    `src/docfit/app/prepare_template.py` 的特殊 Reference prompt 和 checkpoint summary 改为
    `resolved_units`。
  - 测试证据：`tests/contract/test_docfit_evidence_tool.py` 新增
    `test_t1_unit_evidence_packet_rejects_legacy_checkpoint_unit_aliases` 和
    `test_t1_unit_evidence_packet_rejects_resolved_unit_without_unit_id`；
    `tests/contract/test_prepare_template_runtime.py` 反转 post-unit prompt 中的
    `accepted_units` 断言。源码扫描
    `rg -n "accepted_units|checkpoint\\.get\\(\"units\"|checkpoint\\.get\\('units'\\)|resolved_units.*accepted_units" src/docfit/app src/docfit/tools src/docfit/template -g '*.py'`
    无命中。
  - `logic/contract` 验证：focused gate
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract/test_docfit_evidence_tool.py tests/contract/test_tool_context_return_contract.py`
    -> `42 passed`；本轮合并 focused gate -> `104 passed`；完整模板边界套件 ->
    `524 passed`；相关 `ruff` / `mypy src` / `test_documentation_contract.py` /
    `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Tool evidence unit packet 入口的旧 checkpoint alias fail-closed 清理，不能替代
    Phase 8 产品验收。
- Phase 3/6 的 accepted review span provenance 门禁已收紧到 `logic/contract`
  并用真实 agent-loop 失败样本校准：
  - 产品影响：App host candidate selection、`docfit_apply` 字段写入口和 publication/fill-contract
    发布入口现在都要求 accepted semantic review 绑定当前 source hash、当前
    `field_id_vocabulary`、当前 ordered parts 和 Harness-resolved `resolved_spans`。span
    覆盖必须覆盖 reading block/range 中 `object_text_spans` 指向的可映射文本对象；结构性
    carrier 对象仍参与 inventory 覆盖/重叠检查，但不会被误要求进每个 semantic part 的
    `covered_object_ids`。
  - 代码证据：`src/docfit/app/prepare_template.py`、`src/docfit/tools/service.py` 和
    `src/docfit/template/artifact.py` 增加 scope-level required span object 计算；有
    `object_text_spans` 时以 text-span object 为 span 必达集合，没有该元数据的旧/synthetic
    inventory 仍按粗 `covered_object_ids` fail closed。publication 同时拒绝 review/inventory
    与 source template hash 不一致的 slot provenance。
  - 测试证据：`tests/contract/test_prepare_template_runtime.py`、
    `tests/contract/test_docfit_apply_tool.py` 和
    `tests/contract/test_publication_style_handoff.py` 新增正向 text-span carrier 用例；已有
    outside-scope 和 missing-scope-object 用例继续反转不完整 span 证据。真实失败样本来自
    `tests/agent/school_extract_v2/test_agent_design_dry_run_trace.py`，其 inventory 中
    paragraph carrier + run text-span 的合法输出不再被误拒。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/agent/school_extract_v2/test_agent_design_dry_run_trace.py::test_scripted_sdk_run_repairs_materialization_readiness_in_same_session`
    -> `2 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py
    tests/contract/test_publication_style_handoff.py` -> `119 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `531 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`、相关 `ruff`、
    `tests/contract/test_documentation_contract.py` 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 accepted semantic review / publication provenance 的 contract 和真实 dry-run
    regression 清理，不能替代 Phase 8 全量产品验收。
- Phase 7 的当前模块文档 `accepted_units` 旧 checkpoint alias 指引已删除到
  `logic/contract`：
  - 产品影响：默认模块流程文档不再把 `accepted_units` 描述为 `UnitBoundaryProof`
    或 post-unit 的稳定接口；后续字段、样式、Registry、apply 调试都从
    Host-resolved `resolved_units` 进入，和当前 App/Tool checkpoint 接收条件一致。
    这降低了下一轮开发把旧 `units[]` / `accepted_units[]` 持久态恢复为成功路径的风险。
  - 文档证据：`docs/modules/template-extraction.md` 的流程图、unit-boundary 出口、
    proof 字段、resume 校验和 post-unit 主流程都改为 `resolved_units`；历史计划执行日志
    仍保留旧词作为过往证据，不作为当前默认入口。
  - 测试证据：`tests/contract/test_documentation_contract.py` 新增
    `test_current_module_doc_uses_resolved_units_not_legacy_unit_alias`，固定当前模块文档
    不得重新出现 `accepted_units`。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_documentation_contract.py` -> `10 passed`；当前入口扫描
    `rg -n "accepted_units" README.md AGENTS.md ARCHITECTURE.md STATUS.md docs/README.md
    docs/docfit-00-index.md docs/docfit-01-architecture-core.md
    docs/docfit-02-testing-and-iteration.md docs/adr/README.md
    docs/contracts/template-extraction.md docs/human/README.md docs/modules/README.md
    docs/modules/final-word-generation.md docs/modules/student-content-extraction.md
    docs/modules/template-extraction.md docs/plans/README.md
    docs/status/active/docfit-school-extract-v2.md
    .claude/skills/docfit-school-extract/SKILL.md memory/README.md tests/README.md
    tests/manual-diagnostics/README.md` -> no matches；`git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是长期文档入口的 current-contract 清理，不能替代 Phase 8 产品验收。
- Phase 3/6 的 accepted semantic-review 机械门禁实现已收敛到共享 helper：
  - 产品影响：App host candidate selection、Tool phase-review gate 和 publication/fill-contract
    gate 不再各自复制一份 current review / vocabulary / resolved span / coverage 判定规则。
    同一个 accepted semantic review 现在只由 `docfit.template.semantic_review` 的共享合同判定，
    降低未来某个入口重新接受旧字段别名、旧 coverage 输入协议或不完整 `resolved_spans`
    的漂移风险。
  - 代码证据：新增 `src/docfit/template/semantic_review.py`，集中
    `review_uses_current_semantic_shape()`、`review_judgment_has_current_resolved_spans()`
    和 `review_spans_cover_inventory_once()`；`src/docfit/app/prepare_template.py`、
    `src/docfit/tools/service.py`、`src/docfit/template/artifact.py` 改为调用共享 helper。
    Tool service 只保留一个获取 task pre-input vocabulary 的薄包装；publication 仍保留
    source-hash / semantic-digest 的专用 failure code，以维持发布归因。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py
    tests/contract/test_publication_style_handoff.py` -> `119 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/agent/school_extract_v2/test_agent_design_dry_run_trace.py::test_scripted_sdk_run_repairs_materialization_readiness_in_same_session`
    -> `2 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `532 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> no issues in
    `108 source files`；相关 `ruff` 和 `git diff --check` 通过。duplicate helper scan 只剩
    Tool service 的 `_phase_review_uses_current_semantic_shape()` 薄包装。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 boundary gate implementation 的 P2 drift cleanup，不能替代 Phase 8 全量产品验收。
- accepted semantic-review 门禁已删除旧 coverage input 的粗粒度 fallback：
  - 产品影响：App host candidate selection、Tool phase-review gate 和 publication/fill-contract
    gate 现在要求 accepted inventory 的文本覆盖来自 Harness-only `object_text_spans`；缺失
    或空的 `object_text_spans` 不再退回 `covered_object_ids`。新增文本承载对象如果只被塞进
    `covered_object_ids`、没有 span mapping，也会失败关闭；结构性 carrier 仍可作为粗覆盖
    账本对象存在，但不能代替文本 span provenance。
  - 代码证据：`src/docfit/template/semantic_review.py` 的
    `review_spans_cover_inventory_once()` 增加文本对象 span-mapping 闭合检查；
    `tests/contract/test_template_semantic_review.py` 固定当前 accepted shape、缺
    `object_text_spans` fail-closed、空映射 fail-closed、text object missing mapping
    fail-closed，以及 carrier/text-object 区分。现有 App/Tool/Publication accepted-review
    synthetic fixtures 与 replay fixture 已升级到当前 `object_text_spans` 协议。
  - `logic/contract` + `real replay` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_semantic_review.py
    tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_apply_tool.py
    tests/contract/test_publication_style_handoff.py` -> `124 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/integration/test_template_materialization_replay.py
    tests/agent/school_extract_v2/test_agent_first_prepare_template.py` -> `24 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `537 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> no issues in
    `108 source files`；相关 `ruff`、entrypoint `accepted_units` scan 和 `git diff --check`
    通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 accepted semantic-review coverage contract 清理，不能替代 Phase 8 全量产品验收。
- Harness ordered-span resolver 的 `reading_block` 粗粒度映射 fallback 已删除：
  - 产品影响：Harness 不再因为一个 reading block 只有一个 `covered_object_id`，就把 Agent
    的 whole-block ordered part 解析成 resolved span。所有可解析文本都必须来自
    `object_text_spans` 这种 Harness 映射账本；缺失映射会返回
    `ordered_part_span_unmapped`，不会生成可执行 provenance。
  - 代码证据：`src/docfit/template/harness.py` 删除
    `_reading_block_text_segments()` 的 `mapping_precision="reading_block"` fallback 和
    对应的 ambiguous sub-block 分支；`tests/contract/test_template_harness_reading_blocks.py`
    新增 whole-block single-object no-span fail-closed 回归，并把成功路径 synthetic inventory
    全部升级为 `object_text_spans`；`tests/contract/test_tool_contract.py` 的旧 Agent-authored
    coverage 回归测试也升级了“新协议成功对照”。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py tests/contract/test_tool_contract.py`
    -> `40 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_tool_contract.py tests/contract/test_agent_boundary_guardrails.py
    tests/contract/test_harness_feedback_helpfulness.py
    tests/contract/test_template_harness_reading_blocks.py` -> `53 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `538 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`、相关 `ruff`、旧
    `mapping_precision="reading_block"` scan 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Harness resolver 旧 coverage fallback 清理，不能替代 Phase 8 全量产品验收。
- Harness `submit_object_inventory` 入口已对旧 coverage-only reading block 失败关闭：
  - 产品影响：旧协议不再能先落盘为 Harness object inventory，再等语义提交阶段才失败。任何带
    可见文本和 `covered_object_ids` 的 reading block 都必须同时提交 Harness-only
    `object_text_spans`；缺失该映射会在 inventory 提交阶段以
    `template_harness_argument_invalid` 拒绝。
  - 代码证据：`src/docfit/template/harness.py` 的 `_inventory_reading_block()` 在 normalization
    阶段要求 text reading block 的 `object_text_spans` 非空；`tests/contract/test_template_harness_reading_blocks.py`
    将 whole-block 和 multi-object no-span 用例反转为 submit-stage fail-closed，并把需要进入
    semantic 阶段的成功/反馈夹具全部升级到当前 span-mapped inventory。`tests/contract/test_tool_contract.py`
    的旧 Agent coverage 字段回归测试继续保留，但其“当前协议对照”也使用 `object_text_spans`。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py tests/contract/test_tool_contract.py
    tests/contract/test_agent_boundary_guardrails.py tests/contract/test_harness_feedback_helpfulness.py`
    -> `54 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `538 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`、相关 `ruff`、旧
    `mapping_precision="reading_block"` / ambiguous fallback scan 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Harness inventory 输入协议清理，不能替代 Phase 8 全量产品验收。
- Harness `object_text_spans` 输入映射已从“存在”收紧到“完整可追踪”：
  - 产品影响：`object_text_spans` 不能只提交一个局部 span 来绕过 coverage-only 禁令。Harness
    在 inventory normalization 阶段要求 spans 按顺序覆盖 reading block 的所有非空白可见字符，
    且不得重叠；否则不会落盘为可供 semantic review 使用的 object inventory。
  - 代码证据：`src/docfit/template/harness.py` 新增
    `_require_object_text_spans_cover_block_text()`；`tests/contract/test_template_harness_reading_blocks.py`
    新增 partial mapping 和 overlapping mapping 的 submit-stage fail-closed 回归。当前成功路径
    继续使用完整 `object_text_spans`，而不是回退到整块 `covered_object_ids`。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py` -> `31 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py tests/contract/test_tool_contract.py
    tests/contract/test_agent_boundary_guardrails.py tests/contract/test_harness_feedback_helpfulness.py`
    -> `56 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `540 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src`、相关 `ruff`、旧 mapping
    fallback scan 和 `git diff --check` 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Harness span mapping 输入合同清理，不能替代 Phase 8 全量产品验收。
- Harness covered object 到 `object_text_spans` 的对象闭合已前移到 inventory submit：
  - 产品影响：`covered_object_ids` 不能再夹带没有文本映射的 run/sdt/text/未知对象来制造
    false-green 覆盖结论。带可见文本的 reading block 中，所有非结构 carrier 覆盖对象都必须出现在
    `object_text_spans`；`paragraph`/`table`/`picture`/`shape` 这类结构 carrier 可以参与范围覆盖，
    但不会被当成文本 span。未知 covered object 也在 submit 阶段失败关闭。
  - 代码证据：`src/docfit/template/harness.py` 新增
    `_require_reading_block_text_span_object_closure()`，并在 `_submit_object_inventory()` 保存 inventory
    前执行；`tests/contract/test_template_harness_reading_blocks.py` 新增 unmapped text object
    submit-stage fail-closed 回归，以及 unmapped structural carrier 正向路径，断言 resolved span 只来自
    显式文本 run。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py tests/contract/test_tool_contract.py`
    -> `44 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_template_harness_reading_blocks.py tests/contract/test_tool_contract.py
    tests/contract/test_agent_boundary_guardrails.py tests/contract/test_harness_feedback_helpfulness.py`
    -> `58 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `542 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check
    src/docfit/template/harness.py tests/contract/test_template_harness_reading_blocks.py` -> pass；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> no issues in `108 source files`；
    `git diff --check`、旧 `mapping_precision="reading_block"` / `ordered_part_span_object_ambiguous`
    source scan 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Harness inventory 输入闭合合同清理，不能替代 Phase 8 全量产品验收。
- `docfit_apply` 外层旧 operation surface 已退役为 package-action-only：
  - 产品影响：`docfit_apply` 不再把 `bind_field`、`replace_instruction`、`remove_sample`、
    `refresh_generated`、`preserve_layout` 或 `apply_style_fact` 作为公开输入枚举或行为来源。
    写入语义、carrier 支持、phase-review 判断和 receipt 里的操作名都来自 reviewed
    `batch_ref` action package 的 `operations[].action`，也就是 materializer/Harness 生成的
    canonical domain action。
  - 代码证据：`src/docfit/tools/surface.py` 从 `DOCFIT_APPLY_SCHEMA` 删除 `operation` 属性和
    `APPLY_OPERATIONS` 枚举；`src/docfit/tools/service.py` 删除 `args["operation"]` 行为依赖，
    新增 `_APPLY_ACTION_ALLOWED_CARRIERS` / `_apply_package_action()`，并用 package action 做 carrier
    校验、phase-review 触发和 receipt/failure 文案；`src/docfit/template/artifact.py` 的 publication
    修复建议不再提示 `docfit_apply(bind_field)`。`tests/contract/test_docfit_apply_tool.py` 删除旧
    operation 输入夹具，新增 receipt 来自 packaged `clear_content` action 的合同；`tests/contract/test_tool_surface.py`
    反向断言 apply schema 不再暴露旧 operation 名。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py`
    -> `47 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `536 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check
    src/docfit/tools/surface.py src/docfit/tools/service.py src/docfit/template/artifact.py
    tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py` -> pass；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> no issues in `108 source files`；
    `git diff --check` 和旧 apply operation surface scan 通过，旧 operation 字符串只剩 schema
    fail-closed 断言。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Tool surface / package-action 合同清理，不能替代 Phase 8 全量产品验收。
- `docfit_apply` 顶层 `target_ref` 和 package-level `target_refs` 已退役为 package-only target：
  - 产品影响：`docfit_apply` 不再让调用方顶层 `target_ref` 决定 carrier 校验、stale target
    校验或 receipt target。唯一可执行目标对象来自 reviewed `batch_ref` 中唯一
    `operations[].target_ref`；旧 package-level `target_refs` 形状失败关闭为 retired shape。这样
    顶层直写参数不能再与 materializer/Harness 生成的 action package 竞争写入目标。
  - 代码证据：`src/docfit/tools/surface.py` 从 `DOCFIT_APPLY_SCHEMA` 删除顶层 `target_ref`；
    `src/docfit/tools/service.py` 删除 `args.get("target_ref")` 行为入口和 package-level
    `target_refs` 合并逻辑，`_apply_edit_operation()` 现在直接解析/规范化唯一 packaged
    `operations[].target_ref` 并把该 target 用于 carrier 校验和 receipt；`src/docfit/tools/__init__.py`
    的 Tool audit 不再记录顶层 `operation` / `target_ref`；相关错误文案改为
    `operations[].target_ref`。`tests/contract/test_docfit_apply_tool.py` 中的 `service.apply` /
    `docfit_apply.handler` 旧顶层 `target_ref` 输入夹具已删除，stale/invalid target 只通过
    package 内 `operations[].target_ref` 触发。
  - `logic/contract` 验证：
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q
    tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py`
    -> `47 passed`；
    完整模板边界套件
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run pytest -q tests/contract
    tests/integration/test_template_materialization_replay.py tests/agent/school_extract_v2
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py
    tests/unit/test_field_registry_v2.py` -> `536 passed`；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run ruff check
    src/docfit/tools/__init__.py src/docfit/tools/surface.py src/docfit/tools/service.py
    tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py` -> pass；
    `UV_CACHE_DIR=/private/tmp/docfit-uv-cache uv run mypy src` -> no issues in `108 source files`；
    `git diff --check`、旧顶层 target 行为入口 scan、旧 apply 测试输入夹具 scan 通过。
  - 未完成层级：本轮没有新增真实 live Agent E2E、完整视觉 review 或 product acceptance；
    这是 Tool surface / package target 合同清理，不能替代 Phase 8 全量产品验收。
- publication/style stale legacy wording 已清理：
  - 产品影响：发布与 fill-contract 写出当前仍必须把最终 Word slot 回连到 accepted semantic
    review、输入 `field_id_vocabulary`、Harness `span_ref/slot_ref`、materialization operation
    和 mutation receipt；没有发现 publication 只凭 SDT alias / Registry lookup 发布字段的成功路径。
    底层 DOCX mutation 的用户可见失败提示不再暴露旧 `bind_field` 操作名，style capture 内部
    `_legacy_*` 命名也改为当前 v2 school style / content type 口径。
  - 代码证据：`src/docfit/template/object_mutation.py` 的 existing content-control boundary 提示
    改成 `materialize_slot`；`src/docfit/styles/capture.py` 将 `_legacy_application_scope` /
    `_legacy_contract_from_candidate` 重命名为 `_application_scope_from_content_type` /
    `_contract_from_school_candidate`。残留扫描显示生产代码没有 `FieldRegistrySnapshot.search()`、
    `field_id` fallback、`bind_field` 成功路径；`slot_id` / `intent_id` / `judgment_id` 和旧字段
    alias 只剩 denylist / fail-closed sanitizer。
  - `logic/contract` 验证：
    `.venv/bin/pytest -q
    tests/contract/test_publication_style_handoff.py tests/contract/test_docfit_apply_tool.py
    tests/contract/test_tool_surface.py` -> `88 passed`；
    `.venv/bin/pytest -q tests/unit/test_style_capture_observation.py` -> `5 passed`；
    Eval 退役 loader/fail-closed 切片
    `PYTHONPATH=evals/template-extraction .venv/bin/pytest -q
    evals/template-extraction/tests/unit/test_contracts.py::test_con_04_through_06_retired_school_gold_contracts_fail_closed
    evals/template-extraction/tests/unit/test_style_contract_v2.py::test_v1_fill_contract_is_retired_from_eval_loader
    evals/template-extraction/tests/contract/test_eval_contract.py::test_sch_fill_04_retired_v1_version_fails_closed
    evals/template-extraction/tests/contract/test_candidate_gate.py::test_gold_01_through_03_retired_school_gold_fails_closed
    evals/template-extraction/tests/integration/test_raw_source_sentinel.py::test_sentinel_01_through_03_retired_school_gold_fails_closed
    evals/template-extraction/tests/unit/test_gold_preparation_field_policy.py`
    -> `19 passed`；
    相邻模板边界矩阵
    `.venv/bin/pytest -q tests/contract/test_docfit_apply_tool.py
    tests/unit/test_object_mutation_content_controls.py tests/contract/test_publication_style_handoff.py
    tests/contract/test_template_materialization_runtime.py
    tests/contract/test_template_materialization_handlers.py
    tests/contract/test_template_materialization_compiler.py
    tests/integration/test_template_materialization_replay.py tests/unit/test_materialization_readiness.py
    tests/unit/test_style_capture_observation.py tests/contract/test_tool_surface.py`
    -> `198 passed`；
    `.venv/bin/ruff check ...` -> pass；
    `.venv/bin/mypy src` -> no issues in `108 source files`；
    `git diff --check` -> pass。
  - 未完成层级：本轮没有新增 `real replay`、`E2E agent loop` 或 `product acceptance`；
    Eval 旧 v1/`slot_id` fixture 仍作为 fail-closed 反例留存，不是当前成功输入。
  - 提交状态：`git add docs/plans/template-field-id-vocabulary-boundary-refactor.md
    src/docfit/template/object_mutation.py src/docfit/styles/capture.py` 因
    `/Volumes/ExtSSD2601/Docfit/.git/worktrees/template-extraction/index.lock`
    `Operation not permitted` 失败；当前沙箱无提权权限，无法完成 stage/commit。
- Tool runtime `source_hash` 输入面已退役：
  - 产品影响：`docfit_evidence`、`docfit_check` 和 `docfit_apply` 不再接受顶层
    `source_hash` 作为 Agent/Tool 请求输入。绑定 task root 的 `input/school-template.docx`
    是唯一 source identity；Tool 结果、feedback、receipt 中的 `source_hash` 仍可作为内部账本和证据
    输出，但不能由 compiler、handler、materializer、publication 或 fill-contract 逻辑从请求里创建、
    猜测、补造或迁移。
  - 代码证据：`src/docfit/tools/service.py` 新增 retired argument gate，三条 Tool runtime
    在解析业务参数前拒绝 `source_hash`；旧 `_resolve_template_source_hash()` 和
    `source_hash_invalid` 路径已移除，`docfit_apply` 失败 receipt 改为使用绑定 task root 计算出的
    source hash。`src/docfit/tools/__init__.py` 的 tool-call audit 不再摘要 retired `source_hash`
    输入字段。`tests/contract/test_docfit_apply_tool.py`、`tests/contract/test_docfit_evidence_tool.py`、
    `tests/contract/test_docfit_check_tool.py` 和 `tests/contract/test_harness_feedback_helpfulness.py`
    已把旧输入调用删除或反转为 `schema_envelope_invalid` fail-closed。
  - `logic/contract` 验证：
    `.venv/bin/pytest -q tests/contract/test_docfit_apply_tool.py
    tests/contract/test_docfit_evidence_tool.py tests/contract/test_docfit_check_tool.py
    tests/contract/test_tool_context_return_contract.py tests/contract/test_tool_surface.py`
    -> `124 passed`；
    `.venv/bin/pytest -q tests/contract/test_docfit_apply_tool.py
    tests/contract/test_docfit_evidence_tool.py tests/contract/test_docfit_check_tool.py
    tests/contract/test_tool_context_return_contract.py tests/contract/test_tool_surface.py
    tests/contract/test_prepare_template_runtime.py tests/contract/test_tool_contract.py
    tests/contract/template_gate/test_agent_first_tool_contract.py
    tests/contract/test_subagent_runtime_context_contract.py tests/contract/test_prepare_template_security.py`
    -> `178 passed`；
    宽模板边界矩阵
    `.venv/bin/pytest -q tests/contract tests/integration/test_template_materialization_replay.py
    tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py
    tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `538 passed`；
    `.venv/bin/ruff check ...` -> pass；
    `.venv/bin/mypy src` -> no issues in `108 source files`；
    `git diff --check` -> pass；
    retired `source_hash` input wording / resolver / args scan -> no matches except dedicated fail-closed tests
    and internal checkpoint/receipt ledger fields。
  - 提交状态：`git add docs/plans/template-field-id-vocabulary-boundary-refactor.md
    src/docfit/tools/service.py src/docfit/tools/__init__.py tests/contract/test_docfit_apply_tool.py
    tests/contract/test_docfit_evidence_tool.py tests/contract/test_docfit_check_tool.py
    tests/contract/test_tool_context_return_contract.py tests/contract/test_tool_surface.py
    tests/contract/test_harness_feedback_helpfulness.py src/docfit/template/object_mutation.py
    src/docfit/styles/capture.py` 因
    `/Volumes/ExtSSD2601/Docfit/.git/worktrees/template-extraction/index.lock`
    `Operation not permitted` 失败；当前沙箱无提权权限，无法完成 stage/commit。
  - 未完成层级：本轮没有新增 `real replay`、`E2E agent loop` 或 `product acceptance`；这是
    Tool runtime input-contract 清理，不能替代 Phase 8 全 logical-unit live 验收矩阵。
- `registry_binding` feedback rebrand 和 `migrated_boundaries` 旧结果 key 已退役：
  - 产品影响：旧 `registry_binding` 反馈类型不再被 App 包装成当前 `field_meaning_review` 给
    Agent 继续处理；如果旧 feedback 中带有 `registry_binding` / `registry_field` 等旧词，它只会被
    sanitized 成当前 `field_id_vocabulary` / `mechanical_review` 语义，不会保留旧检查名或把旧中间态
    伪装成新接口。底层 Word slot materialization 的边界节点调整回执也从
    `migrated_boundaries` 改为 `relocated_boundaries`，表达为 DOCX 边界 relocation 账本，而不是旧
    schema / 中间态迁移。
  - 代码证据：`src/docfit/app/prepare_template.py` 删除 `registry_binding -> field_meaning_review`
    的兼容重命名，并把 `registry_binding` 纳入 Agent-visible feedback denylist；
    `tests/contract/test_harness_feedback_helpfulness.py` 新增旧 feedback 不重命名、不泄露旧检查名的
    合同。`src/docfit/template/object_mutation.py` 将 materialize_slot 的边界结果字段改为
    `relocated_boundaries`；`tests/unit/test_object_mutation_content_controls.py` 反向断言旧
    `migrated_boundaries` key 不再存在。`tests/contract/test_docfit_check_tool.py` 的 handler fake
    不再从请求 args 读取 `source_hash`。
  - `logic/contract` 验证：
    `.venv/bin/pytest -q tests/contract/test_harness_feedback_helpfulness.py` -> `6 passed`；
    `.venv/bin/pytest -q tests/unit/test_object_mutation_content_controls.py` -> `4 passed`；
    `.venv/bin/pytest -q tests/contract/test_harness_feedback_helpfulness.py
    tests/contract/test_docfit_check_tool.py tests/unit/test_object_mutation_content_controls.py
    tests/contract/test_docfit_apply_tool.py` -> `81 passed`；
    宽模板边界矩阵
    `.venv/bin/pytest -q tests/contract tests/integration/test_template_materialization_replay.py
    tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py
    tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `539 passed`；
    `.venv/bin/ruff check ...` -> pass；
    `.venv/bin/mypy src` -> no issues in `108 source files`；
    `git diff --check` -> pass；
    `field_meaning_review` / args `source_hash` / `migrated_boundaries` scan 仅剩 fail-closed
    测试断言。
  - 提交状态：`git add docs/plans/template-field-id-vocabulary-boundary-refactor.md
    src/docfit/app/prepare_template.py src/docfit/template/object_mutation.py
    tests/contract/test_harness_feedback_helpfulness.py tests/contract/test_docfit_check_tool.py
    tests/unit/test_object_mutation_content_controls.py` 因
    `/Volumes/ExtSSD2601/Docfit/.git/worktrees/template-extraction/index.lock`
    `Operation not permitted` 失败；当前沙箱无提权权限，无法完成 stage/commit。
  - 未完成层级：本轮没有新增 `real replay`、`E2E agent loop` 或 `product acceptance`；这是
    App feedback sanitizer 和底层 mutation receipt 命名的 contract/source-scan 清理，不能替代
    Phase 8 全 logical-unit live 验收矩阵。
- App unit-boundary coverage check 的 retired `source_hash` 输入和 `unit_slice` /
  `scope_ref` Tool 输入面已退役：
  - 产品影响：App 在 resume proof validation 和 unit-boundary feedback review 中调用
    `docfit_check(unit_coverage)` 时不再传入顶层 `source_hash`；Tool source identity 只来自
    绑定 task root 的 `input/school-template.docx`。`docfit_evidence` 公开枚举和 service 成功路径
    不再提供旧 `unit_slice` locator 切片，顶层 `scope_ref` 也从 evidence/check schema 和 direct
    service 成功路径移除，旧调用 fail closed。materialization readiness 给 Agent 的下一取证面改为
    当前 `unit_evidence_packet`，避免继续引导旧 coverage / locator 输入协议。
  - 代码证据：`src/docfit/app/prepare_template.py` 删除两处 App 传给 `DocFitToolService.check()`
    的 retired `source_hash`；`src/docfit/tools/surface.py` 从 `EVIDENCE_FOCUS`、evidence schema
    和 check schema 移除 `unit_slice` / `scope_ref`，并增加 `unit_slice_runtime_removed` 失败码；
    `src/docfit/tools/service.py` 让 `unit_slice` focus 和顶层 `scope_ref` 直接失败关闭，删除
    `scope_ref` 文档路径 hash-binding 路径和 locator-scoped object slicing helper；
    `src/docfit/tools/__init__.py` 的 Tool audit 不再摘要 `scope_ref`；
    `src/docfit/template/materialization/readiness.py` 的 blocker 取证面改为
    `unit_evidence_packet`。`tests/contract/test_prepare_template_runtime.py` 断言 App check args
    不再带 `source_hash`；`tests/contract/test_docfit_evidence_tool.py` /
    `tests/contract/test_docfit_check_tool.py` 把 `unit_slice` / `scope_ref` 反转为 fail-closed；
    `tests/contract/test_tool_surface.py` 和
    `tests/contract/test_tool_context_return_contract.py` 锁住 schema/context 形状。
  - `logic/contract` 验证：
    `.venv/bin/pytest -q
    tests/contract/test_prepare_template_runtime.py::test_unit_boundary_checkpoint_records_per_query_timing
    tests/contract/test_prepare_template_runtime.py::test_resume_proof_validation_does_not_require_agent_render_ref`
    -> `2 passed`；
    `.venv/bin/pytest -q tests/contract/test_prepare_template_runtime.py` -> `35 passed`；
    `.venv/bin/pytest -q tests/contract/test_docfit_evidence_tool.py
    tests/contract/test_docfit_check_tool.py tests/contract/test_tool_surface.py
    tests/contract/test_tool_context_return_contract.py tests/contract/test_harness_feedback_helpfulness.py
    tests/contract/test_prepare_template_runtime.py` -> `125 passed`；
    相邻 materialization 矩阵
    `.venv/bin/pytest -q tests/contract/test_docfit_evidence_tool.py
    tests/contract/test_docfit_check_tool.py tests/contract/test_tool_surface.py
    tests/contract/test_tool_context_return_contract.py tests/contract/test_harness_feedback_helpfulness.py
    tests/contract/test_prepare_template_runtime.py tests/contract/test_template_materialization_readiness.py
    tests/unit/test_materialization_readiness.py tests/contract/test_template_materialization_runtime.py`
    -> `165 passed`；
    宽模板边界矩阵
    `.venv/bin/pytest -q tests/contract tests/integration/test_template_materialization_replay.py
    tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py
    tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `537 passed`；
    `.venv/bin/ruff check ...` -> pass；
    `.venv/bin/mypy src` -> no issues in `108 source files`；
    `git diff --check` -> pass；
    `unit_slice` / `scope_ref` scan 仅剩退役失败码、sanitizer 反向输入、fail-closed 测试断言和
    materialization 内部 `scope_refs` 账本。
  - 提交状态：`git add docs/plans/template-field-id-vocabulary-boundary-refactor.md
    src/docfit/app/prepare_template.py src/docfit/tools/surface.py src/docfit/tools/service.py
    src/docfit/tools/__init__.py src/docfit/template/materialization/readiness.py
    tests/contract/test_prepare_template_runtime.py tests/contract/test_docfit_evidence_tool.py
    tests/contract/test_docfit_check_tool.py tests/contract/test_tool_surface.py
    tests/contract/test_tool_context_return_contract.py tests/contract/test_harness_feedback_helpfulness.py`
    因 `/Volumes/ExtSSD2601/Docfit/.git/worktrees/template-extraction/index.lock`
    `Operation not permitted` 失败；当前沙箱无提权权限，无法完成 stage/commit。
  - 未完成层级：本轮没有新增 `real replay`、`E2E agent loop` 或 `product acceptance`；这是
    App/Tool input-contract 和 feedback-context 清理，不能替代 Phase 8 全 logical-unit live
    验收矩阵。
- App feedback legacy focus/code translators、materialization 字段抽取单一来源和旧 validator obligation 已清理：
  - 产品影响：旧 `evidence_focus=unit_slice/registry_field` 进入 App feedback sanitizer 时不再被
    “升级”为当前 `unit_evidence_packet` / `field_id_vocabulary`，而是被丢弃并只保留通用可修复反馈；
    `toc_contract`、`materialization_semantic_parts_*`、`materialization_structure_variant_*` 和
    `unknown_registry_field` 等旧错误码不再有专门迁移文案。当前 materialization readiness 直接输出
    当前缺失项，例如 `field_id_vocabulary.fillable_leaf_field_id` 和 `parts[].field_id`。compiler 的字段 ID
    抽取只剩 `field_binding.explicit_materialization_field_ids()` 一个实现，validators 不再保留
    `style_obligation` 死分支或 `cleanup_reason` 缺失项，Tool/publication/DOCX mutation 文案也改为
    Harness-reviewed 责任归属。
  - 代码证据：`src/docfit/app/prepare_template.py` 删除旧 focus/code/missing-requirement 的专门翻译路径；
    `src/docfit/template/materialization/compiler.py` 删除重复的 `explicit_materialization_field_ids()` 副本并改用
    `field_binding` 单一实现；`src/docfit/template/materialization/readiness.py` 将 fillable leaf blocker
    缺失项改为当前 `field_id_vocabulary.fillable_leaf_field_id`；`src/docfit/template/materialization/validators.py`
    删除 style obligation dead gate，并把 cleanup safety 改成 ordered-parts 语言；
    `src/docfit/tools/surface.py`、`src/docfit/tools/service.py`、`src/docfit/template/object_mutation.py` 和
    `src/docfit/template/artifact.py` 将写入/发布文案改为 Harness-reviewed final Word / package 责任。
    `tests/contract/test_prepare_template_runtime.py`、`tests/contract/test_harness_feedback_helpfulness.py` 和
    `tests/unit/test_materialization_readiness.py` 同步锁住旧 focus 不升级、当前 readiness code 原样返回和旧
    `registry_field` missing requirement 不回流。
  - `logic/contract` 验证：
    `.venv/bin/pytest -q tests/contract/test_harness_feedback_helpfulness.py` -> `6 passed`；
    `.venv/bin/pytest -q tests/contract/test_prepare_template_runtime.py` -> `35 passed`；
    `.venv/bin/pytest -q tests/contract/test_prepare_template_runtime.py
    tests/contract/test_harness_feedback_helpfulness.py tests/contract/test_template_materialization_compiler.py
    tests/contract/test_template_materialization_handlers.py tests/contract/test_template_materialization_plan.py
    tests/contract/test_template_materialization_runtime.py tests/contract/test_publication_style_handoff.py
    tests/contract/test_docfit_apply_tool.py tests/contract/test_tool_surface.py
    tests/unit/test_materialization_readiness.py tests/unit/test_object_mutation_content_controls.py`
    -> `236 passed`；
    宽模板边界矩阵
    `.venv/bin/pytest -q tests/contract tests/integration/test_template_materialization_replay.py
    tests/agent/school_extract_v2 tests/unit/test_materialization_readiness.py
    tests/unit/test_object_mutation_content_controls.py tests/unit/test_field_registry_v2.py`
    -> `537 passed`；
    `.venv/bin/ruff check ...` -> pass；
    `.venv/bin/mypy src` -> no issues in `108 source files`；
    `git diff --check` -> pass。
  - Source scan：
    `materialization_semantic_parts_*`、`materialization_toc_contract*`、`materialization_structure_variant*`、
    `unknown_registry_field` 的生产专门迁移分支已清空；`unit_slice` / `registry_field` 旧
    `evidence_focus` 只剩 sanitizer/fail-closed 测试输入；`explicit_materialization_field_ids` 生产定义只剩
    `src/docfit/template/materialization/field_binding.py`。
  - 提交状态：`git add docs/plans/template-field-id-vocabulary-boundary-refactor.md
    src/docfit/app/prepare_template.py src/docfit/template/artifact.py
    src/docfit/template/materialization/compiler.py src/docfit/template/materialization/readiness.py
    src/docfit/template/materialization/validators.py src/docfit/template/object_mutation.py
    src/docfit/tools/service.py src/docfit/tools/surface.py
    tests/contract/test_harness_feedback_helpfulness.py tests/contract/test_prepare_template_runtime.py
    tests/unit/test_materialization_readiness.py && git commit -m "Retire legacy feedback translators"` 因
    `/Volumes/ExtSSD2601/Docfit/.git/worktrees/template-extraction/index.lock`
    `Operation not permitted` 失败；当前沙箱无提权权限，无法完成 stage/commit。
  - 未完成层级：本轮没有新增 `real replay`、`E2E agent loop` 或 `product acceptance`；这是
    App feedback 和 materialization contract/source-scan 清理，不能替代 Phase 8 全 logical-unit live
    验收矩阵。

### 2026-09-12 Phase 8 canonical-span representative replay (Registry 0.1.0)

- 产品结果：Registry 0.1.0 下 HUNAU 封面、目录、正文和开题报告四个代表 logical-page task root 均完成
  真实 Agent loop，并发布 `final-template.docx` 与 `fill-contract.yaml`。这证明 canonical
  source-entry/span 合同已覆盖普通填槽、generated TOC policy、正文结构和复杂表格/空白槽位；不代表
  三校 32 个 logical units 或外部视觉产品验收已经完成。
- 真实失败归因与修复：封面首次因 123 字符说明项末尾 5 个空格不可见而在 7 次反馈后失败；开题报告
  v1 中，Agent 在 `reason` 声明保留 13 个尾随空格和 4 个前导空格，但未把它们写入
  `parts[].text`。`1accfd4` 为 Agent packet 增加文本长度、首尾空白数量/码点，并为 span gap 增加
  精确缺口反馈；`111f7d8` 进一步明确空白必须作为字面字符进入 `parts[].text`，只在 `reason`
  描述不构成覆盖，并为前导错位提供数量/码点。Harness 未自动补语义或扩展 span。
- `logic/contract`：
  `uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent`
  -> `701 passed`；相关 Ruff pass；mypy 对修改源文件 pass。
- `E2E agent loop` / `real replay`：
  - `hunau-01-cover-v11`：`status=complete`，1 unit，21 judgments，43 resolved spans，9 slots；
    123 字符说明项精确解析为 `text[0:123]`，末尾 5 个 U+0020 落到 Word fragment。
  - `hunau-03-toc-v1`：`status=complete`，3 units，28 judgments，29 resolved spans；22 个
    `generated.toc` span 全部进入 materialization policy receipt，不伪造 fill slot。
  - `hunau-04-paper-body-v1`：`status=complete`，9 units，54 judgments，100 resolved spans，
    35 个发布 slots。
  - `hunau-06-proposal-v2`：`status=complete`，4 units，143 judgments，144 resolved spans；
    `学  院：` 后 13 个 U+0020 成为 `author.department` 的精确 `text[5:18]` slot，四空格前缀
    说明项精确解析为 `text[0:39]`。
- 发布一致性：四个 build report 均为 `status=ok`、`published=true`，source/Registry/validation/
  package reopen/fill-contract hash checks 为 `ok`；所有 resolved refs 都是
  `source_entry_id + extent + source_snapshot_sha256`，没有 reading-range 或 `part_index` 旧引用。
  cover/body/proposal 的发布 fill slots 与 accepted span/slot/field 三元组完全一致；TOC 的
  generated-only 交接按 policy receipt 验证。
- 未完成层级：完整 HUNAU/NJAU/PKU logical-unit matrix、独立外部视觉 review 和最终
  `product acceptance` 尚未完成；内建 `visual_review_bound=ok` 不能替代外部视觉验收。

### 2026-09-12 Phase 8 whitespace transport and matrix continuation

- 产品结果：结构化输出不能稳定保留全空白字符串时，Agent 现在可以用单个 Unicode
  `codepoint/count` 表达一个独立的纯空白语义 part。Harness 只做机械解码，并立即用当前
  source entry 的下一段原文校验；accepted judgment 仍持久化字面 `parts[].text`，transport
  字段不会进入 accepted span、编译或发布合同，因此没有新增第二套定位协议。
- fail-closed 边界：transport 只接受空 `text`、`U+` 加 4–6 位大写十六进制 Unicode 空白码点、
  正整数 count，且对象不得有额外键。非空白字符、短码点和试图携带 `source_offset` 的输入均拒绝。
- `logic/contract`：
  `uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent`
  -> `705 passed`；相关 Ruff pass；mypy 对修改源文件 pass。实现提交为 `d9e06d6`、
  `e484018` 和 `dd70eb8`。
- `real replay` / `E2E agent loop` 新增通过项：
  - `hunau-02-integrity-v3`：复用 hash-bound unit proof，10 judgments / 12 resolved spans；
    20 与 39 个 U+0020 的独立 parts 在 accepted 文件中均为字面空格，已无 `whitespace`
    transport 字段；build report 全部检查为 `ok` 并发布。
  - `hunau-07-proposal-record-v2`：复用匹配 clean source hash 的 unit proof，38 judgments /
    39 resolved spans；所有 refs 均为 canonical source-entry/extent/source-snapshot，build report
    全部检查为 `ok` 并发布。
- 未通过/未完成项：`hunau-05-design-task-v3` 与
  `hunau-09-topic-change-approval-v1` 在 evidence 读取后等待模型 structured output，达到
  20 分钟执行 timebox 后人工中止；`hunau-08-defense-record-v1` 的 3-unit boundary 已接受，
  post-unit 随后以可重试 `template_agent_no_progress_timeout` 失败。`hunau-10-grade-form-v1`
  完成 7 轮 mechanical span feedback，但仍把 1 个 U+00A0 source entry、混合 U+00A0/U+0020
  前缀和三个日期骨架的纯空白 parts 留成裸空 `text`，最终 6 个 source entries 未被接受。
  `dd70eb8` 消除了反馈中“不要创建同责任 whitespace part”的矛盾，并明确混合码点要按 source
  order 使用多个 transport parts；v2 因模型服务迟迟未交付首轮 structured result，在 20 分钟
  timebox 后中止，因此该指引目前只有 `logic/contract` 证据，尚无 E2E 通过证据。以上项目均不能
  记作 E2E 或产品验收通过；current-contract NJAU/PKU matrix 与外部视觉 review 仍未完成。

### 2026-09-12 Phase 8 inline field instruction interface closure

- 产品缺陷与归因：NJAU `10-acknowledgement` 的同一正文位置由“占位 + 仅约束该字段的
  内联格式说明 + 占位”组成。旧规则要求格式说明总是单独分类，真实 Agent 因而生成两个
  `acknowledgement.body` slots；final-word placement 会逐 slot 写入同一 Student Content，实际会把
  致谢正文写两次。Gold 在该位置只有一个正文 content control，因此这不是合法镜像位置。
- 修复边界：`b270ebf` 只修改学校语义 Skill 与文字分类 reference。规则现在要求：同一视觉填写
  位置中，一个字段的连续占位若仅被该字段的内联说明切开，且拆分会生成重复接口，则把连续范围
  整体判断为一个 `fill_slot`，在 `reason` 记录说明义务；跨页或真实镜像位置仍分别判断。没有新增
  字段名、学校 wording、Harness 合并规则或第二套定位合同。
- `logic/contract`：新增回归先在旧 Skill 上失败，修复后
  `uv run pytest -q tests/contract/test_skill_contract.py` -> `20 passed`，Ruff 和
  `git diff --check` 通过。
- `E2E agent loop` / `real replay`：
  `temp/phase8-canonical-20260912/njau-10-acknowledgement-v2` 从 clean input 运行完整
  `prepare-template`，返回 `status=built`，session
  `60c944de-55bf-4e30-86e7-c422e1f5caab`，`num_turns=2`。accepted semantics 将该 source
  entry 的完整 `text[0:129]` 判断为单个 `acknowledgement.body` fill slot；build report
  `status=ok`、`published=true`、`counts.slot=1`，source/Registry/validation/内建视觉绑定/package
  reopen/fill-contract hash checks 全部为 `ok`。最终 DOCX 与 Gold 均只有一个致谢正文 content
  control。
- 下游消费 proof：用发布 fill contract 和一个 synthetic READY Student Content item 调用真实
  `build_placement`，只生成 1 个 `replace_block_content_control` operation；状态仍为 `PARTIAL`，
  唯一原因是 fill contract 为 `candidate_pending_human_acceptance`，不能表述为产品验收完成。
- 未完成层级：本页的重复写入缺陷已取得 Registry 0.1.0 下的
  `logic/contract + real replay + E2E agent loop` 证据；这证明语义规则对该真实输入生效，但不能计作
  Registry 0.5.0 字段合同验收。外部视觉 review、human acceptance 和三校完整 logical-unit matrix
  仍未完成。

### 2026-09-12 Registry provenance correction and v0.5 TOC replay

- 证据纠偏：`temp/phase8-canonical-20260911/**`、
  `temp/phase8-canonical-20260912/**` 的 task-local Registry 实际均为 `0.1.0`，SHA-256 为
  `9779d0272fc395245002184d43e8356b0722a6821e8ca0a36ced0db6d26d522d`；此前把这些运行写成
  “Registry v0.5 / current-contract matrix”的表述不成立。它们仍可证明当时代码下的 canonical
  source-entry/span、Agent feedback 和发布链，但不能证明当前字段词表合同。当前 accepted Registry
  `docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml` 为 `0.5.0`，SHA-256 为
  `e139059b03883d5fbb07ebc1a35d5dffac654fad7241a61d520d7ecd4dac7ffd`，后续 Phase 8 计数必须核对
  task-local build report 的 Registry identity，不能只依据运行目录名称。
- NJAU `03-toc` 的 v0.5 真实 replay 连续暴露并关闭三个确定性执行缺口：`448ced8` 让空段落的
  whole-entry provenance 在嵌套空 run 中选择唯一外层 carrier；`c5994e4` 在 span preflight 中恢复正文
  `<w:tab>`；`b6473dc` 让共享 Word locator 按 OfficeCLI 的公开序号解析 `<w:hyperlink>` 内扁平 run；
  `6fac11c` 排除段落属性 `<w:pPr><w:tabs><w:tab>`，避免把格式制表位声明计入可见文本。每个缺口均先
  由回归测试复现，再修生产代码。
- `logic/contract`：object mutation 与 materialization 聚焦测试共 `32 passed`；
  `uv run pytest -q tests/contract tests/integration/test_template_materialization_replay.py tests/agent`
  -> `708 passed`；相关 Ruff 和 mypy 通过。
- `real replay`：对
  `temp/phase8-v05-20260912/njau-03-toc-v2` 的真实 source inventory、Harness-accepted semantic
  judgments 和 Registry 0.5.0 直接调用 materializer，结果 `status=ok`、`operation_count=0`、
  `cleanup_count=1`、`receipt_count=30`，并生成 `real-replay-6fac11c.docx`。这证明 accepted spans 能
  唯一解析和执行；不等于 E2E Agent loop。
- `E2E agent loop` 未闭合：新 task `njau-03-toc-v3` 首轮在 unit-boundary checkpoint 经三次机械反馈
  后仍留下未覆盖 run，Harness 以 `unit_boundary_checkpoint_failed` 正确拒绝；同 task 恢复轮次在
  180 秒内没有 Tool call 或 structured result，以可重试 `template_agent_no_progress_timeout` 退出。
  因此当前只能声明 v0.5 `real replay` 已通过，不能声明本页 v0.5 E2E 或 product acceptance 已通过。
- 后续恢复式 E2E 已关闭上述 post-unit 缺口：
  `temp/phase8-v05-20260912/njau-03-toc-v4` 使用 v2 中同 source hash、已由 Harness 接受的
  unit-boundary proof，并以 Registry 0.5.0 执行 `--from unit-boundary --resume-proof` 进入 post-unit，返回
  `status=built`、`num_turns=2`。30/30 source entries 由 30 个 judgments 覆盖，解析为 80 个 canonical
  spans（75 generated-content、4 fixed-label、1 cleanup），`legacy_refs=0`；materialization 产生 29 个
  policy receipts、1 个 cleanup、共 30 个 mutation receipts，不伪造 fill slot。build report 全部检查为
  `ok`，`gap=0 / unresolved=0`。这证明当前恢复入口、post-unit Agent、accepted spans、materializer 和
  发布链消费同一快照；完整从 unit-boundary Agent 自主拆分开始的 v3 仍保留为失败证据，v4 则达到
  恢复式 v0.5 `E2E agent loop`，但 fill contract 仍待 human acceptance。
- v0.5 代表 E2E：
  `temp/phase8-v05-20260912/njau-10-acknowledgement-v1` 从真实 logical-page DOCX 与 accepted
  Registry 0.5.0 空 task root 运行完整 `prepare-template`，返回 `status=built`、`num_turns=2` 并发布
  `final-template.docx` 与 `fill-contract.yaml`。4 个 source entries 全部有 accepted judgment；正文
  source entry 的完整 `text[0:129]` 物化为唯一 `acknowledgement.body` content control，两个说明段按
  accepted cleanup span 删除，build report 的 source/Registry/validation/内建视觉绑定/package reopen/
  fill-contract hash checks 全部为 `ok`。CLI 的 `unresolved=6` 与 `gap=1` 来自 fill contract 中 6 个
  unresolved style properties 和 1 个 `known_school_style_gap`，不是语义覆盖缺口；contract 状态仍为
  `candidate_pending_human_acceptance`，所以本页达到 v0.5 `E2E agent loop`，未达到 product acceptance。
- HUNAU v0.5 代表 E2E：
  `temp/phase8-v05-20260912/hunau-01-cover-v1` 从真实封面 logical-page DOCX 与同一 accepted
  Registry 0.5.0 空 task root 完整运行，返回 `status=built`、`num_turns=2`。21 个 source entries
  全部由 21 个 judgments 覆盖，生成 40 个 canonical resolved spans，`legacy_refs=0`；发布 9 个 slots，
  字段为中英文题名、作者姓名/学号/院系/班级、导师姓名/职称和提交日期。build report 的全部检查为
  `ok`，Registry identity 为 `0.5.0 / e139059b…`。`gap=9 / unresolved=79` 与 fill contract 的 9 个
  `known_school_style_gaps`、79 个 unresolved style properties 完全对应，不是 source-entry 或字段覆盖
  缺口；产物仍为 `candidate_pending_human_acceptance`，所以达到 v0.5 `E2E agent loop`，未达到
  product acceptance。
- PKU v0.5 代表 E2E：
  `temp/phase8-v05-20260912/pku-11-acknowledgement-v1` 从真实致谢 logical-page DOCX 与 accepted
  Registry 0.5.0 空 task root 完整运行，返回 `status=built`、`num_turns=2`。22 个 source entries
  全部由 22 个 judgments / 22 个 canonical resolved spans 覆盖，`legacy_refs=0`；正文样例唯一物化为
  `acknowledgement.body` slot，其余 20 个 changelog/模板维护说明 source entries 由 accepted cleanup
  spans 删除。build report 全部检查为 `ok`，Registry identity 为 `0.5.0 / e139059b…`；
  `gap=1 / unresolved=6` 与唯一 slot 的 known style gap 完全对应。产物仍为
  `candidate_pending_human_acceptance`，所以本轮已形成 HUNAU/NJAU/PKU 各一个 current-Registry E2E
  代表项，但没有完成三校全 logical-unit matrix 或 product acceptance。
- NJAU v0.5 正文执行闭合：
  `temp/phase8-v05-20260912/njau-06-body-v1` 首次虽返回 `status=built`，但复核发现 accepted review
  含 42 个 body_structure bindings，其中 14 个 source entries 各有两个同字段正文 parts；handler 对同一
  段落重复替换后，materialization JSON 仍声称 42 个 members，而最终 DOCX/fill contract 只有 28 个
  interfaces。该运行是“中间账本与产物不一致”的失败证据，不计入 E2E 通过项。
- 责任层与修复：同一正文视觉位置的占位被仅约束它的内联格式说明切开时，正确学校语义仍是一个
  body member。`ce00800` 将单接口规则从 `fill_slot` 扩展到 `body_structure`，并在 readiness 增加确定性
  fail-closed：每个 source entry 最多一个带字段的 body_structure part；重复时在 DOCX 写入前返回受影响
  source entry 与 part indexes 给 Agent 修订。门禁不按学校 wording 或字段名合并语义，也不替 Agent
  选择范围。回归测试先证明旧 Skill、readiness 和 materializer 都接受错误形态，修复后聚焦套件
  `68 passed`，广泛 contract/integration/agent 回归 `709 passed`，相关 Ruff/mypy/diff check 通过。
- 修复后 `temp/phase8-v05-20260912/njau-06-body-v2` 使用同一 source-bound unit proof 和 Registry 0.5.0
  运行真实 post-unit Agent loop，返回 `status=built`、`num_turns=2`。39/39 source entries 由 39 个
  judgments 覆盖，52 个 resolved spans 中恰有 28 个 body_structure bindings，分属 28 个 source
  entries，重复数为 0；字段为 outline1/outline2/outline3 和 body.paragraph。materialization members、
  最终 DOCX field controls、fill-contract slots 均为 28，三者 `slot_ref` 集合完全相等；build report
  全部检查为 `ok` 并绑定 `0.5.0 / e139059b…`。151 个 unresolved 对应 28 个 known style gaps，产物仍为
  `candidate_pending_human_acceptance`，所以达到 v0.5 E2E agent loop，尚未达到 product acceptance。
- NJAU v0.5 参考文献集合闭合：
  `temp/phase8-v05-20260912/njau-07-references-v1` 虽机械覆盖 20/20 source entries 并返回
  `status=built`，但 Agent 把固定“参考文献”标题误绑为正文标题字段并清理全部真实条目，最终没有
  `references.entries`，因此是语义失败证据，不计 E2E 通过。集合 reference 原有规则没有在该运行中被
  路由读取；`7b1bc89` 将稳定入口提升到主 Skill：已识别为参考文献或成果集合时，至少保留一个真实
  条目作为集合接口，集合标题不能代替条目接口。回归先在旧 Skill 上失败，修复后 Skill contract
  `21 passed`，广泛 contract/integration/agent 回归 `710 passed`；没有把学校 wording、canonical
  field ID 或执行参数写入指引。
- 修复后 `temp/phase8-v05-20260912/njau-07-references-v2` 返回 `status=built`、`num_turns=5`。
  20/20 source entries 分别由 1 fixed title、1 fill slot 和 18 cleanup spans 覆盖；一个真实普通图书条目
  绑定当前词表的 `references.entries`，其它格式说明、类别标签和样例被精确清理。最终 DOCX content
  control 与 fill-contract slot 的 identity 一致，build report 全部检查为 `ok` 并绑定
  `0.5.0 / e139059b…`。`gap=1 / unresolved=7` 属于该集合槽位的 known style gap，contract 仍待
  human acceptance，因此达到 v0.5 E2E agent loop，尚未达到 product acceptance。
- NJAU v0.5 附录正文接口闭合：`njau-08-appendix-v1/v2` 虽返回 `status=built`，但 Agent 清理可见说明
  后只留下 `appendix.title`，并错误声称不可见空段或宿主会建立正文接口；`v3` 在加强 Skill 后正确返回
  `needs_input`，暴露 `appendix.body` 的 `usage_affordance.allowed_part_roles=[]`。归因确认 runtime 把所有
  `content_type: section` 混成同一类：`body.chapters` 是有 Registry 子字段的内部结构容器，
  `appendix.body` 则是没有子字段、需整体填写的叶子结构区。`62ded68` 将该类别边界统一落实到 pre-input
  vocabulary、readiness、Tool edit 校验和 publication：叶子 section 可作为 `fill_slot`，有子字段的
  section 容器仍禁止发布为 slot；Skill 只要求按词表允许角色选择 `fill_slot` 或 `body_structure`，未加入
  字段名特判。红测覆盖词表、readiness、实际 DOCX 物化和发布协议；广泛
  `contract/integration/agent + registry/readiness` 回归为 `748 passed`。
- 修复后 `temp/phase8-v05-20260912/njau-08-appendix-v5` 复用同 source hash 的 accepted
  unit-boundary proof，但重新生成 post-unit inventory，以 digest `861eccc3…` 向 Agent 暴露
  `appendix.body.allowed_part_roles=[fill_slot]`。真实 Agent loop 返回 `status=built`、`num_turns=5`；2/2
  source entries 形成 2 judgments / 4 canonical spans，字段分别为 `appendix.title` 与 `appendix.body`，
  `legacy_refs=0`。materialization 为 `status=ok`、2 operations / 2 receipts；最终 DOCX 与 fill contract
  均有且仅有这两个 controls，`field_id + slot_ref` 集合完全一致。build report 全部检查为 `ok` 并绑定
  Registry `0.5.0 / e139059b…`。`gap=1 / unresolved=4` 是 style closure 缺口，fill contract 仍为
  `candidate_pending_human_acceptance`，所以达到恢复式 v0.5 `E2E agent loop`，尚未达到 product
  acceptance。`v4` 因测试目录误带 v3 的旧 post-unit inventory，Agent 仍看到旧 digest 并返回相同字段
  缺口，只保留为测试搭建失败证据，不计产品失败或通过。
- 词表投影更新影响：叶子 section affordance 使同一 Registry `0.5.0 / e139059b…` 派生的 vocabulary
  digest 从 `f9ff558a…` 变为 `861eccc3…`。因此本节较早绑定旧 digest 的 v0.5 运行保留为修复前历史
  E2E，不能单独证明当前投影合同。当前 digest 的代表重跑中，
  `temp/phase8-v05-20260912/njau-10-acknowledgement-v2` 为 4 entries / 4 judgments / 5 spans / 1
  `acknowledgement.body` slot；`pku-11-acknowledgement-v2` 为 22 entries / 22 judgments / 22 spans /
  1 个同字段 slot。两者 `legacy_refs=0`，materialization 与 build report 均为 `ok`，最终 DOCX 与
  fill-contract identity 一致，并继续绑定 accepted Registry SHA。HUNAU `hunau-01-cover-v2` 在一次
  evidence 读取后长期未交付 structured output，约 7 分钟后人工取消，execution 记录
  `CancelledError`；独立串行 `hunau-01-cover-v3` 仍在一次 evidence 读取后无 structured output，约
  5 分钟后人工取消并记录同一 failure。两次均不计产品或合同失败/通过；当前 digest 的 HUNAU live
  代表仍未闭合。
- 当前 digest 的 NJAU 执行类型重跑中，`njau-03-toc-v5` 与 `njau-06-body-v3` 均在首次 evidence
  读取后长期没有 structured output，约 5 分钟后人工取消并记录 `CancelledError`，不能计为 E2E
  通过或代码失败。`njau-07-references-v3` 则真实返回并发布，但把 10 个格式样例全部物化为
  `references.entries` slots；最终内容填充会重复写入同一集合，所以该 built 产物是语义失败证据。
  `6eed6a7` 将主 Skill 与集合 reference 收紧为：同一集合区只选择一个真实代表条目，其余样例清理，
  仅真实镜像输出区另建接口。该规则没有下沉为按字段名去重的 Harness 窄规则。
- `njau-07-references-v4` 在上述修复后收敛为一个条目接口，但又把固定“参考文献”标题借用
  `body.heading.outline1`，会让 final fill 用正文章标题替换集合地标，因此仍是语义失败证据。
  `5bf6651` 明确集合标题没有专用字段时保持固定内容，不得仅因 Heading 样式或大纲级别改绑正文
  标题字段。最终 `temp/phase8-v05-20260912/njau-07-references-v5` 返回 `status=built`、
  `num_turns=2`：20/20 entries 形成 20 judgments / 20 canonical spans，固定标题保留，恰有一个真实
  图书条目绑定 `references.entries`，18 个说明、类别和其余样例按 accepted cleanup spans 删除；
  `legacy_refs=0`，materialization 为 1 operation / 18 cleanup / 20 receipts。最终 DOCX 与 fill contract
  均只有一个 `references.entries` control，build report 全部为 `ok`，绑定 vocabulary digest
  `861eccc3…` 与 Registry `0.5.0 / e139059b…`。广泛回归仍为 `748 passed`；产物状态是
  `candidate_pending_human_acceptance`，达到当前 digest 的恢复式 E2E agent loop，未达到 product
  acceptance。
- 当前 digest 的 NJAU 正文与 TOC 后续串行重试已闭合先前 live 无输出缺口：
  `temp/phase8-v05-20260912/njau-06-body-v4` 返回 `status=built`、`num_turns=9`，39/39 source
  entries 形成 39 judgments / 52 canonical spans；28 个 body_structure bindings 分属 28 个不同
  source entries，重复数为 0，字段分布为 outline1=3、outline2=5、outline3=6、paragraph=14。
  materialization 的 28 个 member slot_refs 与最终 fill contract 的 28 个 slots 完全相等，build report
  全部为 `ok`。`gap=28 / unresolved=151` 仍是 style closure，不是语义覆盖缺口。
- `temp/phase8-v05-20260912/njau-03-toc-v6` 返回 `status=built`、`num_turns=2`，30/30 source
  entries 形成 30 judgments / 30 canonical spans，其中 25 `generated.toc`、4 fixed-label、1 cleanup，
  `legacy_refs=0`。materialization 不产生 fill operation，写出 29 policy receipts（25
  `refresh_generated_content`、4 `preserve_exact_fragments`）和 1 cleanup receipt；最终 fill contract
  为零 slots，build report 全部为 `ok`，`gap=0 / unresolved=0`。两项均绑定 vocabulary digest
  `861eccc3…` 与 Registry `0.5.0 / e139059b…`，达到当前 digest 的恢复式 E2E agent loop；产物仍为
  `candidate_pending_human_acceptance`，未达到外部视觉或最终 product acceptance。

### 2026-09-12 PKU Chinese abstract Markup Compatibility text closure

- 产品缺陷与责任层：当前 digest 的 PKU `03-abstract-cn` 首次 post-unit 运行
  `temp/phase8-v05-20260912/pku-03-abstract-cn-v1` 已得到完整 Agent 语义判断，但 Harness 在物化前以
  `cleanup_span_not_whole_paragraph` 拒绝“欢迎提交 pull request”模板维护说明。归因不是 Agent、Skill
  或范围门禁错误，而是 inspect/source fact 层遗漏了段尾 `😊`：OfficeCLI 把
  `mc:AlternateContent` 中的 `w16se:symEx` / fallback run 返回为空，使 canonical source entry 只有
  16 个字符，而 materializer 从真实 OOXML 看到 17 个字符。
- 最小修复：`6260a98` 把 OfficeCLI public locator 解析与 Word visible-text 提取收口到共享事实模块；
  inspect 对含 Markup Compatibility 内容的段落/run 采用单一有效分支，并解码 `symEx` Unicode；
  materializer 复用同一 visible-text 规则。没有放宽 whole-paragraph cleanup、没有按学校 wording
  特判，也没有把缺失字符降级为结构范围。
- `logic/contract`：回归先稳定复现段落和第 5 个 run 分别缺失 emoji，修复后 canonical entry 为
  `欢迎提交pull request😊`，最后 provenance 为精确 `text[16:17]`。聚焦 locator/inspect/materializer
  测试 `35 passed`；广泛
  `contract + template materialization replay + agent + registry/readiness + locator/inspect` 回归
  `756 passed`；相关 Ruff 与 mypy 通过。
- `real replay`：对真实 source SHA `e706a91d…` 重新运行 OfficeCLI inspect，目标段落、5 个 runs 与
  canonical source entry 分别得到完整可见文本，emoji run 的 fingerprint、object ref 和 `[16,17]`
  span 均绑定同一 source snapshot。
- `E2E agent loop`：`temp/phase8-v05-20260912/pku-03-abstract-cn-v2` 复用同 source-hash accepted
  unit-boundary proof，Agent 在 2 turns 内提交 12 judgments / 13 canonical spans，明确将完整
  `欢迎提交pull request😊` 判断为 cleanup。post-unit checkpoint 后由同一 task root 的确定性阶段复用
  accepted review，最终返回 `status=built`；materialization 为 2 field operations、7 cleanup、
  12 mutation receipts，发布 `abstract.zh` 与 `keywords.zh` 两个且仅两个 content controls。
  build report 的 source/Registry/validation/内建视觉绑定/package reopen/fill-contract hash checks
  全部为 `ok`，并绑定 vocabulary digest `861eccc3…` 与 Registry `0.5.0 / e139059b…`。最终 DOCX
  已不含该维护说明或 emoji；fill contract 仍为 `candidate_pending_human_acceptance`，2 个 style gaps /
  12 个 unresolved properties 属于样式闭合，不是定位或语义覆盖缺口。
- 同一 current-digest PKU 矩阵继续新增两个恢复式 E2E：
  - `pku-02-copyright-v1` 复用 source SHA `48c3c89d…` 的 accepted unit proof，2 turns 内返回
    `status=built`。当前 unit packet 的 6/6 source entries 形成 6 judgments / 6 canonical spans：
    2 fixed-label、3 style-only、1 cleanup；materialization 为 0 field operations、1 cleanup、
    5 policy receipts / 6 mutation receipts。最终 fill contract 为合法零槽位合同，no-slot semantic
    provenance 绑定 digest `861eccc3…`，build checks 全部为 `ok`，`gap=0 / unresolved=0`。
  - `pku-04-abstract-en-v1` 复用 source SHA `55fe7dae…` 的 accepted unit proof，6 turns 内返回
    `status=built`。12/12 source entries 形成 12 judgments / 14 canonical spans，恰有 5 个字段接口：
    `thesis.title.en`、`author.name.en`、`advisor.name.en`、`abstract.en`、`keywords.en`；
    materialization 5 operations / 12 receipts，最终 DOCX 与 fill contract 的 5 个 slot identities
    一致，build checks 全部为 `ok`。`gap=5 / unresolved=34` 仅对应 style closure。
  两项均无 reading-range、reading-block 或 `part_index` 旧定位引用，均绑定 Registry
  `0.5.0 / e139059b…`，达到恢复式 `E2E agent loop`，但合同仍待 human acceptance。
- PKU `05-toc` 的 fresh boundary 已从失败归因推进到完整 Agent loop：
  - `pku-05-toc-v1` 从当前 logical-page 输入启动真实 `--until unit-boundary`，Agent 成功执行 3 次分页
    `document_map` evidence 读取，但约 5 分钟内未提交 structured output，人工中止后没有 checkpoint；
    该运行只保留为模型执行未完成证据。
  - `pku-05-toc-v2` 随后提交 14 个 unit proposals，但它们都是同一 live TOC content control 内的
    标题或缓存行，且全部映射到同一 `sdt` object；Harness 在 3 轮 feedback 中持续拒绝这些重叠范围。
    该证据证明范围门禁正确 fail closed，缺口属于 Agent/Skill 对“目录缓存不等于真实章节”的稳定学校语义规则。
  - 依照先归因、再写反例的诊断流程，`c90d41f` 先在
    `tests/contract/test_skill_contract.py` 固定反例，再在 `references/unit-boundary.md` 明确目录/图表清单
    的标题与缓存行必须作为一个 generated unit，不能把缓存条目拆成正文功能单元。`pku-05-toc-v3`
    仍同时输出正确 TOC unit 与重叠伪单元，说明规则只放在深层 reference 可发现性不足；`ae63947`
    将同一稳定规则提升到主 Skill 的 unit-boundary 入口并增加合同断言。`pku-05-toc-v4` 的 fresh
    unit-boundary 随后接受且只接受 `unit-toc-generated-region` 一个单元。
  - v4 从 accepted proof 进入 post-unit 时，物化前以 `materialization_word_fragment_stale` 拒绝外层
    `sdt` 的 aggregate text。这不是允许 materializer 绕过精确 span 的理由，而是 canonical inventory
    同时让 40 个后代段落和第 41 个祖先容器拥有同一可见文本。`54c8fb7` 在
    `src/docfit/template/source_entries.py` 只在祖先 `sdt` / `table` 的规范化聚合文本与后代 leaf text
    完全相等时，把祖先条目收敛为保留 object ref/fingerprint 的空 `whole_entry` 结构来源；不相等时不丢弃文本。
    回归 `test_canonical_inventory_does_not_duplicate_ancestor_container_text` 固定了该 inspect/normalize
    ownership 边界，没有新增模板文字特判或 materializer fallback。
- PKU `05-toc` 分层验证结果：
  - `logic/contract`：`contract + template materialization replay + agent + registry/readiness +
    locator/inspect` 广泛回归 `757 passed`；相关 Ruff、mypy 和 `git diff --check` 通过。
  - `real replay`：当前 source SHA `bd89fabf…` 仍生成 41 个可逆 canonical entries；外层 `sdt`
    保留为空 `whole_entry` 结构来源，40 个后代条目独占可见文本，未发生静默丢字或重复文本所有权。
  - `E2E agent loop`：`temp/phase8-v05-20260912/pku-05-toc-v5` 从 v4 的 fresh accepted
    unit-boundary proof 继续运行并构建成功；Agent 提交 41 judgments / 41 spans，其中 37 个
    `generated_content(generated.toc)`、4 个 `fixed_label`。materialization 为 0 fill operations、
    0 cleanup、41 policy/total receipts；最终 DOCX 和零槽 fill contract 的 source unchanged、Registry
    `0.5.0 / e139059b…`、vocabulary digest `861eccc3…`、validation binding、internal visual-review
    binding、package reopen 与 fill-contract hash checks 全部为 `ok`，`gap=0 / unresolved=0`。
  - `product acceptance`：尚未完成。产物仍为 `candidate_pending_human_acceptance`；上述 internal
    visual-review binding 只证明报告绑定关系，不等于外部全页视觉验收。
- 同一 generated-list 规则已在两个独立 logical pages 上取得当前 digest 的 fresh E2E 证据：
  - `temp/phase8-v05-20260912/pku-06-list-of-figures-v1` 从空 task root 运行，fresh unit-boundary
    只接受 1 个 generated unit；post-unit 构建为 `status=built`。45 个 canonical entries 中 15 个
    可见语义条目形成 15 judgments / 15 exact spans：1 个 `fixed_label`、14 个
    `generated_content(generated.list_of_figures)`；0 operations / 0 cleanup / 15 policy 与 mutation
    receipts，`gap=0 / unresolved=0`。source SHA `7ebf73e8…`、final SHA `3e0b47a5…`，来源文本
    preservation 为 21 objects，build checks 全部为 `ok`。
  - `temp/phase8-v05-20260912/pku-07-list-of-tables-v1` 的 unit-boundary checkpoint 同样只接受
    `pku-list-of-tables` 1 个单元。Host 在 checkpoint 落盘后的承接等待中一度返回 retryable
    `template_agent_no_progress_timeout`；从同一 hash-bound accepted proof 恢复 post-unit 后构建为
    `status=built`，证明恢复没有要求 Agent 重造另一套映射。34 个 canonical entries 中 4 个可见语义
    条目形成 4 judgments / 4 exact spans：1 个 `fixed_label`、3 个
    `generated_content(generated.list_of_tables)`；0 operations / 0 cleanup / 4 policy 与 mutation
    receipts，`gap=0 / unresolved=0`。source SHA `9e38d8f6…`、final SHA `664ef374…`，来源文本
    preservation 为 10 objects，build checks 全部为 `ok`。
  - 两项均绑定 Registry `0.5.0 / e139059b…` 与 vocabulary digest `861eccc3…`，fill contract 均为
    零 slots 且 `candidate_pending_human_acceptance`。它们达到 `real replay + E2E agent loop`，但
    `final_visual_review.status=host_review_not_requested`，不能计为外部视觉或最终 product acceptance。
- PKU `08-body` fresh boundary 暴露并修复了页眉制造伪单元的 Agent/Skill 缺口，但真实 Agent 采用
  新规则的正向证明尚未闭合：
  - `temp/phase8-v05-20260912/pku-08-body-v1` 中，Agent 正确找到 5 个真实正文章标题，却又仅凭
    section header 中的“图目录”“致谢”新增两个 unit。Harness 无法从 structural source text 解析
    `unit-figure-list.start_boundary=图目录`，连续 3 轮以 `unit_structural_boundary_unresolved` 拒绝，
    没有错误 checkpoint 被接受。责任层不是 resolver：页眉页脚可以是所属 unit 的辅助对象，但不能
    单独证明正文存在同名功能区。
  - 按诊断流程先增加 `test_school_extract_unit_boundary_mode_is_boundary_only` 红色合同反例，再由
    `94d61c7` 在主 Skill 和 `references/unit-boundary.md` 明确“页眉页脚标签不能单独创建功能区或
    充当正文边界”，并固定“图目录/致谢/论文名称页眉不是同名正文单元”的反例。未修改 Harness、
    Tool、resolver 或 materializer。
  - `logic/contract`：定向测试先失败、修复后 Skill 合同 `22 passed`；更宽
    `tests/contract + tests/agent/school_extract_v2` 为 `664 passed`，Ruff 与 `git diff --check` 通过。
  - `temp/phase8-v05-20260912/pku-08-body-v2` 与 `pku-08-body-v3` 均加载新 Skill，并分别完成多次
    document-map evidence 调用，但在提交 structured output 前触发 retryable
    `template_agent_no_progress_timeout`，没有 unit-boundary checkpoint。有限重试到此停止：这两次只算
    模型执行未完成证据，不能宣称 `real replay`、`E2E agent loop` 或 Skill 效果已被真实输入证明。
- PKU `09-references` 已取得当前 digest 的 fresh unit-boundary + post-unit E2E 证据：
  - `temp/phase8-v05-20260912/pku-09-references-v1` 从空 task root 只接受 1 个参考文献功能单元；
    post-unit 构建为 `status=built`。38 个 canonical entries 中 9 个可见语义条目形成 9 judgments /
    9 exact spans：3 个 `fixed_label`、1 个 `fill_slot(references.entries)`、5 个 `cleanup`。
  - 唯一槽精确绑定第一条真实参考文献的 `source-entry-7014523a…;text[0:51]`，其余 5 条格式样例按
    accepted spans 整段清理；materialization 为 1 operation / 5 cleanup / 9 mutation receipts，
    publication 为 1 slot 且 provenance 中的 field/span/slot/source snapshot 完全一致。
  - source SHA `26ae4203…`、final SHA `a888986a…`，Registry `0.5.0 / e139059b…`、vocabulary
    digest `861eccc3…`；build checks 全部 `ok`。`gap=1 / unresolved=7` 仅来自
    `references.entries` 的 known school style properties，最终 style occurrence verification 为 passed，
    不是来源定位、字段或可执行性缺口。
  - `content_preservation` 的 `missing_object_count=6` 对应 1 个预期槽替换和 5 个 accepted cleanup，
    仍需视觉核对；fill contract 为 `candidate_pending_human_acceptance` 且
    `final_visual_review.status=host_review_not_requested`。因此达到 `real replay + E2E agent loop`，
    未达到 product acceptance。
- PKU `10-appendix-achievements` 已取得当前 digest 的 fresh unit-boundary + post-unit E2E 证据：
  - `temp/phase8-v05-20260912/pku-10-appendix-achievements-v1` 从空 task root 只接受正文中真实存在的
    `附录A  博士期间工作成果` 一个功能单元；边界由正文 start/end anchors 解析，没有按文件名或页眉拆出
    额外单元。40 个 canonical entries 中 10 个语义条目形成 10 judgments / 20 exact spans。
  - accepted parts 为 14 个 `fixed_label`、5 个 `fill_slot`、1 个 `cleanup`。五个槽分别绑定输入词表中的
    `appendix.title`、`achievements.journal_articles`、`achievements.conference_papers`、
    `achievements.projects`、`achievements.intellectual_property`；四个成果集合各只选择第一条真实代表
    条目，第二条知识产权格式样例按 accepted whole-entry span 清理，没有让表头或集合标题替代条目接口。
  - materialization 为 5 operations / 1 cleanup / 10 mutation receipts，publication 为 5 slots；每个
    field/span/slot/source snapshot 在 semantic review、materialization 和 fill contract 间一致。
    source SHA `a3971941…`、final SHA `f4095926…`，Registry `0.5.0 / e139059b…`、vocabulary digest
    `861eccc3…`，build checks 全部 `ok`。
  - `gap=5 / unresolved=31` 仅为五个槽的 known school style properties，最终 5 个 style occurrences
    均 passed；`content_preservation.missing_object_count=6` 对应 5 个预期槽替换和 1 个 accepted cleanup。
    fill contract 仍为 `candidate_pending_human_acceptance`，且 `final_visual_review` 未请求，因此达到
    `real replay + E2E agent loop`，未达到 product acceptance。
- PKU `11-acknowledgement` 已取得当前 digest 的 fresh unit-boundary + post-unit E2E 证据：
  - `pku-11-acknowledgement-v1/v2` 的目录已绑定其它输入，本轮复用请求被
    `prepare_source_mismatch` 正确 fail closed，未覆盖旧 task root；
    `temp/phase8-v05-20260912/pku-11-acknowledgement-v3` 使用全新 root，只接受 1 个真实致谢单元并
    构建为 `status=built`。
  - 51 个 canonical entries 中 22 个可见语义条目形成 22 judgments / 22 exact spans：标题与一个
    空白结构条目为 2 个 `fixed_label`，样例正文“感谢铁岭TV。”为唯一
    `fill_slot(acknowledgement.body)`，19 条模板作者 changelog 为 `cleanup`。没有把维护日志并入学生
    致谢正文，也没有让不可见空段代替填写接口。
  - materialization 为 1 operation / 19 cleanup / 22 mutation receipts，publication 为 1 slot；
    semantic review、materialization 与 fill contract 的 field/span/slot/source snapshot 一致。
    source SHA `d5e12420…`、final SHA `c22b1d15…`，Registry `0.5.0 / e139059b…`、vocabulary digest
    `861eccc3…`，build checks 全部 `ok`。
  - `gap=1 / unresolved=6` 仅为致谢正文槽的 known style properties；
    `content_preservation.missing_object_count=20` 与 1 个 accepted slot 替换和 19 个 accepted cleanup
    对应。fill contract 仍为 `candidate_pending_human_acceptance` 且未做 final visual review，因此达到
    `real replay + E2E agent loop`，未达到 product acceptance。
- PKU `12-declarations` 已取得当前 digest 的 fresh unit-boundary + post-unit terminal source-noop 证据：
  - `temp/phase8-v05-20260912/pku-12-declarations-v1` 从空 task root 将原创性声明、授权文字与签名/
    日期区域接受为 1 个真实声明功能单元；53 个 canonical entries 中 23 个可见语义条目形成
    23 judgments / 24 exact spans。
  - 所有 accepted parts 均为 `manual_region`，不绑定字段。法律文字、签名线和日期位置完整保留，交由
    人工阅读、确认和签署；Agent 没有因看见“签名”“日期”等标签而自造 Registry 字段，也没有执行
    cleanup。该 terminal source-noop 没有物化 receipt，fill contract 通过
    `accepted_no_slot_semantic_review` 绑定同一 semantic digest 和 23 个 judgments。
  - source/final SHA 均为 `b520e601…`，0 slots、`gap=0 / unresolved=0`；Registry
    `0.5.0 / e139059b…`、vocabulary digest `861eccc3…`，source unchanged、content preservation、
    package reopen 和 fill-contract hash 等 build checks 全部 `ok`。
  - fill contract 仍为 `candidate_pending_human_acceptance` 且
    `final_visual_review.status=host_review_not_requested`。因此达到 `real replay + E2E agent loop`，
    但声明人工责任本身和最终视觉仍未完成 product acceptance。
- PKU `01-cover` 已关闭空白值单元格无法成为字段接口的跨层合同缺口：
  - `pku-01-cover-v1` 的 fresh unit-boundary 正确接受 1 个封面单元；post-unit 在两轮完整 semantic
    output 后仍因 span feedback 未收敛，并在第三轮等待超时。`pku-01-cover-v2` 进一步暴露
    Wingdings 传统 `w:sym` 字符在 reading packet 中不可见；`e17eabe` 给 Agent-readable source entry
    增加 offset/codepoint/category 提示，随后 `c5cb4f4` 让 inspect 与 materializer 共用的 Word 可见文本
    同时解码 `w:sym` 和 `w16se:symEx`。两项修复均保持原字符和精确 source span，不做 checkbox
    wording 特判。
  - `pku-01-cover-v3` 已能提交 27 个完整 judgments，但旧合同明确禁止空 `whole_entry` 承担字段角色，
    导致姓名、学号、院系、专业、研究方向和导师姓名的六个真实表格值单元格虽被 Agent 识别为填写位置，
    仍只能输出为非字段固定结构。Host-tail real replay 可发布 4 个字段位置，但产品复核确认上述六个
    必要接口缺失，因此 v3 只算定位/执行诊断证据，不计产品可用 E2E。
  - `dbd23c1` 将唯一合同修正为：只有当前 canonical inventory 明确提供、文本为空且
    `extent.kind=whole_entry` 的 source entry，才可以由 Agent 根据相邻标签和可见布局判断为
    `fill_slot + field_id`；Harness 从同一 entry 派生 `extent=whole_entry` 的 span/slot identity。
    非空 source entry 提交空 part 会以 `ordered_part_empty_for_text_entry` 和 coverage gap 拒绝；不存在的
    空位仍不能提交。该改动没有按学校标签字符串选择字段，也没有恢复隐式 host slot 或后置位置搜索。
  - `logic/contract`：先增加 output shape、精确 span、非空反例、Skill 规则和真实 DOCX 空白表格值单元格
    物化测试；修复后相关合同/物化/reading packet/runtime 套件 `229 passed`，Ruff 与 mypy 通过。
    更广的 `tests/contract tests/unit` 为 `1005 passed / 14 failed`；14 项失败全部属于既有
    observability SQLite storage/web 读取为空问题，与本次 8 个改动文件和模板链路无交集，不能表述为
    全量回归通过。
  - `E2E agent loop`：`temp/phase8-v05-20260912/pku-01-cover-v4` 复用同 source SHA
    `93b1956f…` 的 Harness-accepted unit proof 和 Registry `0.5.0 / e139059b…`，2 turns 内返回
    `status=built`。27/27 source entries 形成 27 judgments / 28 exact spans，`legacy_refs=0`；9 个字段
    接口为 `thesis.title.zh`、`author.name.zh`、`author.student_id`、`author.department`、
    `author.major`、`author.research_direction`、`advisor.name.zh`、`degree.type` 和
    `submission.date`。其中六个空白表格值单元格逐行绑定各自真实 paragraph locator 和
    `whole_entry` span，没有把其它 10 个布局空段或图片误判为字段。
  - materialization 为 9 operations / 0 cleanup / 27 receipts；accepted semantics、operation ledger、
    最终 DOCX 的 9 个 content-control aliases/tags 和 fill-contract slots 的 field/span/slot 集合一致。
    final SHA `de6d70ec…`，source unchanged、Registry、validation、internal visual binding、package reopen
    与 fill-contract hash checks 全部为 `ok`。`gap=9 / unresolved=70` 只对应九个 known school style
    gaps；合同仍为 `candidate_pending_human_acceptance`，且没有外部全页视觉 review，因此本页达到
    `logic/contract + real replay + E2E agent loop`，未达到 product acceptance。
- PKU `08-body` 已完成正文复合载体与精确清理的跨层归因和代码闭合，但本页新的 E2E 尚未闭合：
  - `temp/phase8-v05-20260912/pku-08-body-v4` 使用 current Registry `0.5.0 / e139059b…`
    fresh 运行，unit-boundary 正确接受 5 个真实正文单元，没有再把图目录或致谢误切为正文单元。
    post-unit 提交 292 个 canonical judgments/spans 后在旧 materializer 以
    `body_structure_materialization_unexecutable` 失败。真实 review 显示三个示例表格分别有
    45/42/42 个内部单元格与外层表格同时绑定 `body.table`，且 direct Registry parents 分散在
    `body.chapters`、`body.figure`、`body.table`；这证明失败属于 Skill + readiness + materializer
    的复合载体合同缺口，不是 stale locator。
  - `962e871` 明确“表格、图片、公式整体只有一个外层正文接口”，readiness 在写入前拒绝同一顶层
    可见载体上的多个字段绑定；runtime 将 accepted span 映射到顶层 `w:p` / `w:tbl`，handler 沿 Registry
    parent chain 选择最深共同结构父级，按真实 Word 顺序物化段落与块级表格，并保留首末成员之间的
    fixed/style-only 内容。PKU v4 review 的 `real replay` 因 6 组真实载体冲突返回 `needs_input`，反馈只含
    source entry / field，不向 Agent 暴露 locator。
  - `pku-08-body-v5` 经 3 次 semantic feedback 得到 292 个 accepted judgments，复合对象重复绑定已被
    修订；随后暴露同一物理段落由空段落/图片或说明段/shape 两个合法 source entries 共同 cleanup，及
    顶层示例表格 whole-entry cleanup 尚不可执行。`6a53e4f` 让 Harness 合并同一物理载体的删除结果，并
    允许唯一 canonical top-level table `whole_entry` 删除整表，不放宽 partial paragraph 删除检查。
    使用 v5 真实 object inventory、accepted review 与 Registry 0.5.0 的确定性 materializer replay 返回
    `status=ok / operation_count=1 / cleanup_count=262 / receipt_count=263`，生成
    `work/real-replay-shared-cleanup.docx`。这是 `real replay`，不是 E2E 发布成功。
  - `pku-08-body-v6` 的 Agent/revision 流程形成 65 个正文字段成员，但其中两个 `body.equation` 仍位于
    表格单元格内部；旧 readiness 接受后 handler fail closed。`00cfd93` 新增稳定的
    `materialization_body_structure_nested_composite_member` feedback：内部 entry 必须改为无字段角色，
    或使用输入中真实提供的外层复合对象 entry。v6 accepted review 的真实 readiness replay 恰好返回这
    2 个 blocker，不含 locator。
  - `logic/contract`：相关 readiness/compiler/handler/runtime/exact-span/receipt/plan/Skill 套件
    `147 passed`，Ruff 与 `mypy src`（112 source files）通过。测试覆盖共同 Registry ancestor、段落/题注/
    整表按 Word 顺序物化、区间内固定内容保留、共享 cleanup coalescing、顶层表格删除、同载体冲突和
    表格内部字段成员前置拒绝。更宽的 `tests/contract + template materialization replay integration +
    tests/agent` 回归在新增 runtime 诊断测试后为 `727 passed`。
  - 后续 `pku-08-body-v7`、`v8` 均在首轮 post-unit 生成后以可重试
    `template_agent_result_invalid` 退出，`semantic_feedback_attempts=0`；`v9` 完成 evidence 读取后又以
    可重试 `template_agent_no_progress_timeout` 退出。三次都没有进入新 readiness，因此属于 Agent
    structured-output/progress 层失败，不能用来否定或证明新门禁的 E2E 效果，也不应以临时
    prompt/schema workaround 写入 Skill。
  - `73847cc` 为 ResultMessage 增加不含正文的安全诊断：stop/terminal reason、result 长度、错误数量和
    token 计数；`02a816f` 又为 Harness feedback timing event 增加 blocker 数量和去重错误码，不保存
    message、source entry、locator 或 expected/submitted text。runtime 合同测试为 `44 passed`，Ruff 与
    mypy 通过。这些只提升失败归因能力，不改变 Agent、Harness 或 materialization 的接受条件。
  - 带上述第一层诊断的 `pku-08-body-v10` 首轮 post-unit 实际得到
    `structured_status=complete`，Harness 在 259 ms 内以 `ordered_semantic_parts` 要求一次语义修订；第二轮
    已产生 Tool/文本/JSON/thinking stream，但最后一个有效生成事件后 180 秒仍无 ResultMessage，故以
    `template_agent_no_progress_timeout` 退出。它证明 292-entry 首轮并非必然超过 schema/output 上限，但
    没有形成 accepted review 或发布产物。
  - `pku-08-body-v11` 直接复用 v10 的当前 source checkpoint，只重放 post-unit；首轮持续 550.5 秒后返回
    `subtype=success / is_error=false / terminal_reason=completed`，但 `has_structured_output=false`、
    `result_text_length=0`。模型用量为 `output_tokens=10942 / max_output_tokens=32000`，所以不能归因为明确的
    output-token 截断；SDK 也没有返回 validation error 文本。该结果属于 provider/SDK structured-output
    交付失败，不是 Harness 拒绝。有限诊断重试到此停止；当前正文页只能声明
    `logic/contract + real replay` 通过，新的 `E2E agent loop`、发布产物和 product acceptance 尚未完成。
  - PKU 正文 structured-output blocker 的 bounded semantic-batch architecture packet：
    - Zoom-out map：unit-boundary checkpoint 冻结 `resolved_units`；App 在任何 packet projection 前只构建一次
      canonical source inventory，并持久化 per-unit reading packets；Agent 只返回 semantic judgment candidate；
      Harness 只有在全局 exact coverage / overlap / vocabulary / span / readiness 闭合后才持久化唯一 accepted
      review；materializer、publication 和 consumer 继续只读该 accepted review。
    - Eng-review recommendation：在 App/SDK orchestration seam 将 post-unit 输出按 accepted unit、再按固定
      source-order entry 上限分成有界 batch。重叠 source entry 优先归属其 provenance 恰好命中
      `start_locator` 的 unit，否则归属包含范围更窄的 unit，再以 unit 文档顺序稳定决胜；重叠 unit packet
      仍可提供上下文，但不能重复提交。batch candidate 由 Harness/session 维护 source hash、inventory
      digest、batch manifest 和完成状态，Agent 不维护 batch checkpoint。
    - Public contract / boundary：`POST_UNIT_OUTPUT_SCHEMA`、`unit_evidence_packet`、Agent-visible
      `source_entry_id + ordered parts`、最终 `semantic-judgments.json` 和 materializer 输入均不改变。batch 不是
      partial acceptance；缺批、重复、旧 hash、manifest drift 或全局门失败时不得生成 accepted review。
    - Rejected alternatives：不从 stream delta 恢复 partial JSON；官方 SDK 明确 structured JSON 只在最终
      `ResultMessage.structured_output` 可用。不给 Agent 增加逐对象/逐批 submit Tool；不保留 full-output 与
      batched-output 两条成功路径；不以 prompt/schema workaround 或无限 provider 重试替代分批边界。
    - Feedback/recovery：全局 Harness blocker 必须能按 `source_entry_id` / source-entry group 映射回 batch，
      只重做受影响 candidate；不能映射的全局冲突 fail closed，不退回一次全量 structured output。candidate
      ledger 必须绑定当前 source/inventory/Registry，并在最终 accepted review 写入后退出成功路径。
    - Verification ladder：先做 deterministic batch manifest / overlap ownership / stale-resume contract，再做
      aggregate → global Harness review contract；随后使用真实 PKU inventory + accepted judgments 做
      hash-bound `real replay`，最后才运行新的 PKU `08-body` E2E agent loop。批次单测不能替代后两层。
    - Stop condition：只有单次 batch 大小有硬上限、全局 accepted review 仍原子、所有下游继续消费同一
      canonical spans、旧全量成功路径删除且恢复一致时才允许实现切片放行；否则该方案保持设计态。
    - Preflight/scout：本 slice 沿用用户批准的唯一 Phase 0–8 目标与 no-compatibility 边界；unknown-unknown
      scout 由 v5/v10/v11 对比、当前调用图和 Claude Agent SDK 官方 structured-output/streaming 文档完成。
      本轮不使用并行 subagent，因为当前 host 指令禁止未由用户显式要求的 delegation。
    - Batch-manifest tracer bullet：新增纯 deterministic planner，将 current source hash、canonical inventory
      digest、unit projection digest、field vocabulary digest、固定 entry limit、唯一 ownership 和 batch list
      绑定成 manifest digest。PKU v10 真实 inventory 得到 `292 required entries / 8 batches / max 64`，各 unit
      ownership 为 `52/140/30/66/4`；此前 first-owner 方案会吞掉 unit_5 全部 4 个结论 entries，已由真实
      probe 否决并替换为上述 specific-unit 规则。聚焦合同 `8 passed`，Ruff、mypy 与 diff check 通过。
      该切片尚未接入 Agent loop，只达到 `logic/contract + real manifest replay`，不算新的 E2E。
    - Candidate-ledger tracer bullet：batch candidate 必须 `status=complete`，且 source-entry 集合与顺序精确
      等于 manifest 中自己的 batch；跨批 entry、漏项、重复、乱序和 stale manifest binding 均 fail closed。
      ledger 未收齐所有 batch 时不能 aggregate，也不会写 accepted review；收齐后按 manifest 的 canonical
      source order 生成一次完整 semantic set。聚焦合同累计 `12 passed`，Ruff、mypy 与 diff check 通过。
      使用 `pku-08-body-v5` 的 292 个真实 accepted Agent judgments 去除 Harness-owned resolved spans 后，
      依 manifest 分成 8 个 candidates、重新 aggregate，再交当前 `TemplateHarnessService` 全局提交，得到
      `292 judgments / source order match / judgment set match / Harness status=ok`。证据 root 为
      `/private/tmp/docfit-semantic-batch-replay.DWwhMO`；层级是 hash-bound `real replay`，还不是 SDK E2E。
    - Candidate resume contract：持久化 manifest 必须与 current deterministic manifest 逐字段相等；ledger
      重读同时校验 schema、source/inventory/unit-projection/field-vocabulary/manifest 五项绑定、candidate 顺序、
      candidate digest 和 ledger digest，不提供旧 shape migration。聚焦合同累计 `15 passed`。PKU v5 真实
      ledger replay 在 4/8 candidates 后序列化并重读，再补齐后四批，最终 `8 candidates / 292 judgments /
      canonical order match=true`，ledger digest 为 `36c801ae…`。层级是 `real replay`；尚未证明 App 原子写盘、
      SDK 分批调用或失败后真实 resume。
    - App persistence seam：`prepare_template` 现在为 deterministic manifest 和 candidate ledger 分配固定
      task-local 路径，首次进入时原子写盘，resume 时按 source hash、canonical inventory digest、unit
      projection、field vocabulary、manifest/candidate/ledger digest 严格重读；篡改或 stale 文件 fail closed，
      不做旧 shape migration。新增聚焦测试 `2 passed`，Ruff、mypy、diff check 通过。层级仍是
      `logic/contract`；SDK 尚未改为逐批调用，真实中断续跑尚未完成。
    - Global-feedback routing contract：全局 Harness blocker 只有显式携带 manifest 内当前
      `source_entry_id` / `source_entry_ids` 时，才映射并失效对应 candidate batch；无 source entry、未知
      source entry 或空 blocker 均 fail closed，不扩大重跑范围，也不保留部分接受状态。semantic-batch
      聚焦合同累计 `19 passed`。层级是 `logic/contract`；尚未接入 SDK 批次循环。
    - App/SDK batching tracer bullet：旧的整阶段单次 structured-output 主循环已删除；App 现在逐 manifest
      batch 创建独立 SDK client，只把精确 batch source-entry 列表作为输出边界，候选通过 shape/vocabulary/
      exact-set 校验后立即原子写 ledger，全部候选聚合后才调用现有全局 Harness 接受一次。可路由全局反馈
      失效并重跑受影响批次，`needs_input` 停止整个阶段；完整 ledger resume 不再创建 SDK client。聚焦
      `prepare_template_runtime + semantic_batches` 为 `66 passed`，并包含 65 entries -> 2 clients/batches ->
      ledger resume 0 clients 的 fake-SDK contract；Ruff、mypy、diff check 通过。层级是 `logic/contract`，
      尚未完成真实 SDK batch replay / E2E agent loop。
    - PKU `pku-08-body-v12` 首次真实 batched E2E：manifest 为 `8 batches / 292 entries / max 64`；8 个
      batch 均曾形成合法 candidate，随后全局 semantic coverage 接受，但 materialization readiness 将
      batch 6 中 40 个表格内部 source entries 的 `body.table/body.equation` 绑定退回修订。App 只失效 batch 6，
      ledger 保留其余 `7/8`；运行最终因整阶段 3600 秒预算耗尽退出。真实 resume 证明只重做 batch 6，
      但多轮仍重复同一错误后人工中止，未形成 post-unit checkpoint。因此已证明真实 SDK batching、原子
      candidate persistence、全局反馈路由和断点恢复，层级是 partial `E2E agent loop` evidence；不能声明
      E2E 通过或 product acceptance。
    - 上述真实 failure 归 Agent 机械修订口径：readiness blocker 已明确指出内部 composite member 不能承载
      body field，但通用 batch feedback 未把禁止动作写进 next step。App feedback prompt 现对稳定的
      `materialization_body_structure_nested_composite_member` 类别明确要求移除内部 entry 的
      `body_structure/generated_content field_id`，仅允许 packet 实际提供的 distinct outer composite source
      entry 承载字段，禁止臆造/转移到不存在的 entry。新增 prompt contract，semantic-batch 聚焦测试
      `4 passed`；下一步从现有 7/8 ledger 再次真实 resume。
    - PKU `pku-08-body-v12` 修订后真实 resume 已闭合：App 从 `7/8` ledger 启动，仅创建 1 个 SDK client
      重做 batch 6；Agent 按 nested-composite feedback 修订后，ledger 达到 `8/8`，digest
      `6395bb47…`。全局 Harness 原子接受并写出 post-unit checkpoint：`292 judgments / 976 covered
      objects / 1661 inventory objects / 238 reading blocks`，field vocabulary digest `861eccc3…`；报告为
      `status=checkpointed`，无 final artifact。层级是新的 PKU 正文 `E2E agent loop` post-unit 通过，同时
      证明真实中断恢复不会重做其余 7 批；尚未执行最终 DOCX materialization/publication/visual review，
      因此不是 `product acceptance`。
    - 后续 carrier-safe 修订关闭了上述 post-unit 结果尚不能稳定进入执行的两个合同缺口。`1a78bd4`
      将共享 Word carrier 的 readiness blocker 合并并携带全部 source entries；`00a64e1` 让 scoped
      revision 只替换受影响 judgments、保留完整 ledger；`80cdc35` 进一步保证同一 Word paragraph
      carrier 的 source entries 永不跨 semantic batches，单 carrier 超过 64 时显式失败。重新生成的
      manifest 仍为 `8 batches / 292 entries / max 64`，digest 为 `743dfd7a…`，batch entry counts 为
      `52/64/64/12/30/64/2/4`。
    - carrier-safe 真实 rerun 最终写出 `status=ok` 的 post-unit checkpoint：`292/292` source entries、
      `292` judgments、`292` resolved spans、`976` covered objects、`1661` inventory objects、`238`
      reading blocks、`7` SDK queries；semantic digest 为 `64102bbd…`，Registry/vocabulary 继续绑定
      `0.5.0 / e139059b… / 861eccc3…`。这取代前述 `6395bb47…` 作为 v12 当前 accepted semantic
      baseline，并构成 carrier-safe 的真实 `E2E agent loop` 通过证据。
    - 首次继续 publication 时暴露 non-style composite/table slots 被错误送入 paragraph style capture，
      以 `effective_style_paragraph_not_unique` fail closed。`072e968` 让 style capture 仅处理
      `handling=styled` 槽位，publication 也只给 styled slots 附 `style_contract_ref`；non-style slots
      保持无 style ref。修复后同一 task root 完成实际物化和原子发布：materialization 为
      `status=ok / 1 operation / 72 cleanup / 183 receipts`，输出 110 slots（98 styled、12 non-style），
      `final-template.docx` SHA 为 `7125825b…`，Fill Contract 状态为
      `candidate_pending_human_acceptance`。build report 的 source/Registry/validation/internal visual
      binding/package reopen/fill-contract hash checks 全部为 `ok`。
    - 独立 package/consumer contract 复核：DOCX ZIP 58 个 members 可重开且 CRC 正常；110 个
      `slot_ref` 全部唯一，98 个 styled slots 都有 style contract，12 个 non-style slots 都没有错误 style
      ref。CLI validate 的 source unchanged、OpenXML reopen、placeholder scan 通过；content-preservation
      因 250 个 accepted cleanup objects 只给 warning。固定 visual-review coverage 仍因没有 current fixed
      render 而阻断，不能把 build report 的 internal binding 当成全页视觉验收。
    - 作为非验收性质的辅助检查，本机 LibreOffice 将最终 DOCX 转为 13 页 A4 PDF并逐页目检，未见明显
      裁切、重叠、乱码、表格破损或黑块；第 4、8、10、11、13 页存在较大留白，可能来自保留的分页/分节
      结构，仍需 fixed renderer 与人工 review 判断。因此 PKU `08-body` 现在达到
      `logic/contract + real replay + E2E agent loop + actual DOCX/publication`，但未达到
      `product acceptance`。
    - 代码回归收口：旧 whole-stage feedback 测试已迁移到 scoped batch/fresh-client 合同，M1 integration
      fixture 已迁移到 canonical SourceSpan；观测性 storage/web 的固定 2026-08-03/04 事件在当前日期越过
      产品 30 天保留窗口，测试夹具改用当前 UTC 时间且不修改生产 retention。最终全仓
      `uv run pytest -q` 为 `1144 passed / 5 skipped / 1 deprecation warning`；相关提交为
      `4b9bd24`、`4f92372`、`54cb966`。
    - current-digest HUNAU 代表项也已从长期无 structured output 推进到可发布证据。
      `temp/phase8-v05-20260912/hunau-01-cover-v4` 使用 v3 的 hash-bound unit-boundary proof，manifest
      为单批 `21 entries / max 64`，source/inventory/vocabulary digest 分别为 `3c8dfd62… / 42109e6d… /
      861eccc3…`。两次有界运行在人工中止前分别原子保存 candidate，第三次 resume 继续同一 ledger，
      经 3 SDK queries、2 次全局 semantic feedback、12 turns 返回 `status=built`。accepted review 为
      `21/21 entries / 21 judgments / 117 covered objects`，semantic digest `64afd372…`；发布 9 个唯一
      slots，字段为中英文题名、作者姓名/学号/班级、导师姓名/职称、院系和提交日期，final SHA
      `d25da2be…`。build report、ZIP CRC、slot identity 和 OpenXML reopen 均通过，Registry 绑定
      `0.5.0 / e139059b…`；Fill Contract 仍为 `candidate_pending_human_acceptance`。
    - HUNAU 辅助视觉对照同时发现阻断性呈现回归：本机 LibreOffice 下 source 与 final 都为 2 页 A4，
      但 source 的提交日期留在第 1 页且第 2 页为空；final 中较长的年级/班级、导师等字段占位文案发生
      换行，将提交日期单独挤到第 2 页。该问题属于 placeholder/style materialization 或呈现责任层，
      不是 SourceSpan、字段选择或 Harness 接受错误。`55adbf0` 建立不依赖学校/字段 ID 的通用呈现
      合同：已有可见 fixed label 的内联槽使用紧凑 `【填】`，独立内容槽仍使用 Registry label；
      SDT alias/tag、slot/span identity 与 Fill Contract 不变。官方 OOXML `w:fitText` 方案被否决：
      [Microsoft MS-OE376](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/5e74e347-a9e3-4f00-97d5-b8bea59a748c)
      明确 Word 在 structured document tag 内会忽略该属性。
    - `hunau-01-cover-v5` 复制 v4 的 hash-bound inventory/accepted review/ledger，另存旧输出后仅重做
      确定性物化和发布：`client_count=0 / num_turns=0 / status=built`，9 个字段身份与 Registry
      绑定不变，final SHA 更新为 `2f8931ed…`。独立 ZIP/Fill Contract 复核通过；本机 LibreOffice
      产出 1 页 A4，年级、导师和提交日期都保持在封面单页，无换行溢出。聚焦物化/发布/
      consumer 回归 `150 passed / 1 skipped`，全仓 `1144 passed / 5 skipped`，Ruff/mypy/diff check
      通过。这关闭了已发现的 HUNAU 封面呈现回归，但 fixed renderer 和 human acceptance 仍未完成。
    - current-digest NJAU `09-academic-achievements` 首次真实 post-unit 运行在 31.7 秒内提交
      2/2 source-entry judgments：固定“相关的学术成果目录”标题 + style-only 格式说明，以及
      “此项非必需项”的学校固定说明。输入没有真实成果条目或 canonical 空白 source entry，Agent
      因此没有臆造 achievements slot。Harness exact coverage 接受，但 Host 旧逻辑只允许含
      `manual_region` 的 no-effect review 走 source-noop，错误返回 `template_materialization_required`。
    - `ef7e6a6` 删除这个 Host 角色特判：当且仅当 current Harness review 没有
      fill/body/generated/cleanup materialization effect 时，fixed/style/manual 内容可原样发布。legacy review、
      缺 coverage、需要 slot 或 cleanup 的输入仍 fail closed。聚焦 runtime/publication 为 `92 passed`，
      全仓为 `1145 passed / 5 skipped`，Ruff/mypy/diff check 通过。
    - 同 task root 恢复后 `client_count=0` 并返回 `status=built`；source/final SHA 均为
      `7499473d…`，DOCX 39 package members 的 CRC 正常，0 slots / 0 gaps / 0 unresolved，Fill Contract
      以 `accepted_no_slot_semantic_review` 绑定 semantic digest `b93e6aa1…`与 vocabulary
      `861eccc3…`。本机 LibreOffice 为 1 页 A4，未见裁切、重叠或乱码。这使 NJAU 09
      达到 current-digest `E2E agent loop + terminal source-noop publication`，但仍不是 human/
      fixed-render `product acceptance`。
    - current-digest NJAU `01-cover` 首次 `v1` 虽返回 `status=built`，辅助全页对照却发现校徽与校名
      被裁出页面，且 Agent 将标签行后的 36 个空格和紧邻续行空白分别建成两个
      `thesis.title.zh` 槽。DOCX 中 2 个 drawing、2 个 media、关系和绘图段落均未丢失；
      `126843c` 仍补齐所有 Word 重写入口的标准 DrawingML `a/pic/a14` 前缀并以回归测试保护，
      但 `v2` 的真实重放证明命名空间不是本例裁切的充分原因。将第二题名槽恢复为布局空白后，
      两张图片立即恢复，责任最终归到 Agent 对同一视觉填写区的重复接口判断。
    - `95fc135`、`f4642da`、`09df834` 将稳定规则落到 Registry reference 和主 Skill：标签后留白延续到
      相邻空白 entry 时只建立一个字段接口，其余空白必须以无字段 fixed/style 责任保留，不能为行宽、
      换行或布局借用正文字段。`v4` 首次 revision 已去掉重复题名，却错误绑定 `body.paragraph`；真实
      readiness replay 以 `materialization_body_structure_nested_composite_member` fail closed。`v5` fresh
      loop 的首个候选又因 fixed part 重复包含空格被 Harness coverage 拒绝，resume 后最终接受
      `25 judgments / semantic digest 7e9e22de…`：题名、姓名、学号、学院、专业、导师姓名/职称和提交日期
      各一个槽，续行空白无字段；CLI 经 1 client、6 turns 返回 `status=built`。
    - `v5` 仍暴露通用呈现问题：垂直居中的表格单元格内，独立 `【提交年月】` 占位会改变排版度量并把
      顶部图片推出可见页；只把该可见占位缩为 `【填】` 即恢复。`def40c2` 因此按 OOXML 布局事实建立
      通用规则：`w:tcPr/w:vAlign=center` 容器内的普通文本槽统一使用紧凑可见占位，Registry alias、
      Harness tag、slot/span identity 和 Fill Contract 不变；显式 `centered_title` 布局仍保留其专用行为。
      `njau-01-cover-v6` 复用 v5 accepted semantics，以 `client_count=0 / num_turns=0` 重做物化和发布，
      输出 8 个唯一槽，final SHA `72bb2c62…`，ZIP CRC、2 个 drawing 和标准命名空间均正常。本机
      LibreOffice 为 1 页 A4，校徽、校名、标题、字段和日期槽均在页内；这是 `real replay + auxiliary
      visual`，fixed renderer 与 human acceptance 仍未完成。相关聚焦回归 49 项通过，全仓为
      `1150 passed / 5 skipped / 1 deprecation warning`。
    - current-digest NJAU `02-declarations-v1` 从真实 logical-page DOCX 与 Registry 0.5.0 空 task root
      运行；unit-boundary 接受原创性声明、使用授权声明 2 个功能单元，post-unit 两批覆盖 12/12
      source entries。Agent 将两个学校声明标题和制度正文保留为 fixed，空白作为 style/layout，作者、
      导师签名与年月日骨架作为 manual region，未复用封面姓名或提交日期字段。首次运行原子保存两批
      candidate 后 SDK 汇总请求无进展，中止并从同一 ledger resume；最终 1 client、5 turns 返回
      `status=built`，semantic digest `33bb2cbf…`。该 accepted review 无自动物化 effect，按
      `accepted_no_slot_semantic_review` 发布 source-noop：source/final SHA 均为 `a2431b30…`，39 个 ZIP
      members CRC 正常，0 slots / 0 gaps / 0 unresolved。辅助 LibreOffice source/final 均为 1 页 A4，
      两个声明、签名和日期框架完整，无明显裁切、重叠或乱码；fixed renderer 与 human acceptance
      仍未完成。
    - current-digest NJAU `04-abstract-cn-v1` 与 `05-abstract-en-v1` 首次都返回 `status=built`，但产品复核
      分别发现两类不能计入矩阵的问题：中文摘要把摘要与关键词之间只承担排版留白的空 entry 错绑为
      `body.paragraph`；中英文最终 DOCX 仍显示蓝色字号、字体和行距说明。归因后前者属于 Agent 稳定
      语义规则缺口，后者属于 materializer 将 `style_only` 要求误当成可见正文保留。
    - `31b7081` 使普通 slot、fixed/style 混合段中的非空 `style_only` 说明只保留语义、来源和样式责任，
      不再写入可见正文，并让 mutation/preservation receipt 按实际清理结果一致记录。`3a8845c` 将“两个
      已有完整内容承载之间、只提供段间距或留白的空 entry 必须无字段保留，不能借用
      `body_structure`/近似字段”写入主 Skill 和布局 reference。全仓回归同时发现整张正文表格已被外层
      `body.table` 接口接管后，内部 exemplar 的 `style_only` 文本不能被二次删除；`6c173cc` 将这类复合
      表格内部内容归还外层接口所有，相关聚焦回归 `55 passed`。
    - `njau-04-abstract-cn-v2` 清空旧 candidate/manifest/accepted review 后运行真实 Agent loop，1 client、
      5 turns 覆盖 `9/9` source entries，接受 semantic digest `f2eeea33…`，只建立
      `thesis.title.zh`、`abstract.zh`、`keywords.zh` 三个唯一槽，旧 `body.paragraph` 误绑消失。
      `njau-05-abstract-en-v2` 复用 v1 正确的 `8/8` accepted semantics（digest `e15fc276…`），以
      0 client / 0 turns 重做确定性物化和发布；只建立 `thesis.title.en`、`abstract.en`、
      `keywords.en` 三个唯一槽。两份最终 DOCX 的 ZIP CRC 正常，可见文本扫描中字号、字体和行距说明
      残留均为 0，final SHA 分别为 `5de6ea3c…` 与 `50cce1e6…`，Fill Contract 均绑定 Registry 0.5.0
      且状态为 `candidate_pending_human_acceptance`。
    - 在复合表格保护修复后，`njau-04-abstract-cn-v3` 与 `njau-05-abstract-en-v3` 又以 0 client / 0 turns
      对同一 accepted semantics 重放，输出 SHA 与 v2 完全一致。本机 LibreOffice 辅助渲染均为 1 页
      A4，题名、摘要和关键词接口可见且未见说明文字残留。中文 v2 提供 `E2E agent loop`，两份 v3
      提供 latest-code `real replay + actual DOCX/publication + auxiliary visual`；fixed renderer 与 human
      acceptance 仍未完成。最终全仓 `uv run pytest -q` 为
      `1153 passed / 5 skipped / 1 deprecation warning`。
    - current-digest HUNAU `02-integrity-statement` 在 fresh task root 首轮完成两批 10/10 source-entry
      candidates 后，最终 structured 汇总以可重试 `semantic_batch_result_invalid` 结束；同一
      `hunau-02-integrity-v1` 从 hash-bound unit proof 和原子 candidate ledger 恢复，1 client、5 turns
      返回 `status=built`。accepted review 的 semantic digest 为 `ccd3f168…`，角色闭合为学校固定标题、
      布局空白和一个整体人工签署区，0 Registry 字段绑定，未借用作者姓名或提交日期槽。Host 按
      terminal source-noop 发布，source/final SHA 均为 `f5e6bc5b…`，ZIP CRC 正常，0 slots / 0 gaps /
      0 unresolved。LibreOffice 辅助渲染为 2 页 A4，第 2 页为空白；因 source/final 字节完全相同，
      该空页是源模板已有结构而非本轮回归，但仍须 fixed renderer 与 human acceptance 决定是否接受。
    - current-digest HUNAU `03-toc-v1` 首轮经 2 clients / 12 turns 返回 `status=built`，29/29 entries 中
      22 条目录缓存正确绑定 `generated.toc`；但产品复核发现“（空三行）”“（空两行）”被当作最终
      `fixed_label`，模板已声明只表示字宽间距的 `□` 也留在可见目录标题，因此该 build 是 false-green，
      不计矩阵。`b387bd5` 将“可见空若干行指令”和“被模板明确声明为间距的符号”收口为
      `style_only` 布局义务，27 项 Skill contract 通过。
    - `hunau-03-toc-v2` 清空 v1 candidate/manifest/accepted review 后重新运行。新 candidate 已正确把
      两条空行指令与标题中的 `□□` 判为 `style_only`，但又把大部分目录缓存误判为 cleanup；Harness
      反馈后 `generated.toc` 从 0 条恢复到 2 条。初始运行及两次同 ledger resume 均以可重试
      `template_agent_timeout` 结束，后两轮 candidate digest 停在 `d38e2c5b…`，仍有 20/22 条目录缓存
      未由 `generated.toc` 接管。该相同阻塞已连续三轮，当前停止重试并保留 task root；HUNAU 03 尚未
      达到 `E2E agent loop`、real replay 或 publication，不得计入 current-digest 矩阵。
    - current-digest HUNAU `04-paper-body-v1` 的 fresh 运行与两次 same-ledger resume 共保存 9/9 批
      candidates，并形成覆盖 54/54 source entries 的 accepted review，semantic digest 为
      `65ec3809…`；但三轮均以可重试 `template_agent_timeout` 结束，没有发布产物。Harness readiness
      持续拒绝两个分别来自农理工科与文法经管轨道的 source entry：每个可见段落都同时包含行内四级
      标题样例 `（1）` 和紧随其后的正文样例 `……[1]。`，Agent 因而分别绑定
      `body.heading.outline4` 与 `body.paragraph`，现有 `one_body_structure_member_per_source_entry` /
      `one_body_member_per_visible_carrier` 合同却要求只能保留一个接口。
    - 该冲突不能继续归为 Agent 未遵守 Skill：学校原文明确规定四级标题不单独占行，两个字段责任均有
      语义依据；若为通过 gate 强迫 Agent 丢弃其中一个，会把 materializer/schema 的表达能力缺口转嫁
      成错误语义。责任层重新归到 Agent-facing schema、Harness readiness 和 body materializer 的行内
      复合正文成员合同。修复前 HUNAU 04 不得进入 DOCX materialization/publication，也不计入矩阵。
    - 当前实现已关闭上述执行能力缺口：readiness 仅允许同一 source entry、同一顶层段落、不同字段且
      part index 唯一的多个 `body_structure` span；body materializer 按 accepted part 顺序在一个段落中
      生成多个 SDT，并删除同 entry 的 `style_only`/`cleanup` 可见说明。不同 source entry 共用载体、
      重复字段、表格内部成员和跨载体继续 fail closed。相关 readiness/materialization/runtime/plan
      回归为 `59 passed`，全仓为 `1156 passed / 5 skipped / 1 deprecation warning`，Ruff 与 mypy 通过。
    - 使用 `hunau-04-paper-body-v1` 的真实 Registry、object inventory 和 semantic digest `65ec3809…`
      做 deterministic real replay，readiness 返回无 blocker，物化 `status=ok / 22 operations`；两个
      农理工科/文法经管 source entry 都各自产生 `body.heading.outline4 text[0:5]` 与
      `body.paragraph text[5:11]` 两个成员，未重新选择 Word 位置。这证明原 accepted semantics 已可被
      当前执行链消费，层级为 `real replay`，不是 Agent loop 或 product acceptance。
    - `hunau-04-paper-body-v2` 从 v1 的 hash-bound proof 和 candidate ledger 以 0 client / 0 turns 恢复，
      返回 `status=built`，发布 41 slots，build report 的 source/Registry/validation/internal visual/
      package reopen/fill-contract hash checks 均为 `ok`。LibreOffice 辅助渲染为 3 页 A4，正确分拆的
      文法经管样例在同一行显示两个接口且说明文字消失。但 ledger 重组出的 digest `d7642a1b…` 将另一
      个相似农理工科样例整段收为单一 outline4 span，与 v1 accepted review 不一致；因此该 build 只证明
      E2E 执行/发布链路可达，不计 current-digest 矩阵，仍需 fresh semantic closure。固定 renderer 与
      human acceptance 也未完成。
    - 随后新建的 `hunau-04-paper-body-v3` 只继承输入与 hash-bound unit proof，不继承旧 candidate 或
      accepted review。fresh loop 在约 9 分钟内原子保存前 2/9 批后，第三批 SDK 持续无响应，人工安全
      中止；task root 保留可恢复 ledger，没有 accepted review 或发布产物。本次不计 E2E 通过，也不改变
      `24/32` 矩阵；后续可从同一 ledger 恢复，但不应把 backend 无响应重新归到 materializer。
    - current-digest HUNAU `05-design-task-v1` 从真实 logical-page DOCX 与 Registry 0.5.0 新建 task root；
      unit-boundary 在 1 次 SDK query 后以 5 个功能单元写出 hash-bound proof。post-unit 的 5 个 batches
      覆盖 83/83 source entries，全部 candidate 已原子保存。确定性 aggregate + Harness closure 将唯一
      blocker 定位到 `source-entry-6799048ce2a49010761939f6`：Agent 在“教学基层组织负责人签名”前漏掉
      一个 U+0020 空格，并把冒号与后续 18 个空格切错，返回 `ordered_part_text_mismatch/gap`。
    - 初始 loop 在全局反馈后进入该 scoped revision，随后两次 same-ledger resume 也只重做受影响 batch；
      三次 SDK revision 均持续无响应并由人工安全中止。当前有完整 5/5 candidate ledger，但没有 Harness
      accepted review、materialization 或 publication；这属于 backend/Agent revision 进度阻塞，不是
      SourceSpan 校验失败。HUNAU 05 不计矩阵，后续恢复不得重跑已完成的其余四批。
    - current-digest HUNAU `05-design-task-v2-m27hs` 使用 `MiniMax-M2.7-highspeed` fresh 运行：unit-boundary
      约 39 秒接受一个完整任务书单元，post-unit 两批覆盖 108/108 source entries 并保存完整 candidate
      ledger。首次 aggregate 发现一个无效 whitespace transport，但 blocker 只带 judgment/part 字段路径，
      没有 `source_entry_id`，batch router 因而返回 `semantic_batch_feedback_unroutable`。责任层是 Harness
      feedback metadata，不是 Agent 语义或 SourceSpan 定位。
    - `_decode_whitespace_parts` 现把当前 judgment 的 canonical `source_entry_id` 附到 transport blocker；
      三种无效 transport contract 先红后绿，同一真实 ledger 的反馈 replay 可机械映射到唯一 source entry
      与 batch。恢复后 Agent 已修正该 transport，下一轮 exact-span 检查进一步定位一条弯引号被转成直引号
      的 source entry；随后 scoped revision 超过 7 分钟停在 SDK `receive_response`，安全中止且没有 accepted
      review/materialization/output。该项证明反馈路由缺口已关闭并有一次 live revision 进展，但仍未达到
      E2E/publication，HUNAU 05 继续不计矩阵。
    - HUNAU `05-design-task-v2-m27hs` 使用 `MiniMax-M2.7-highspeed` fresh 运行：unit-boundary 在约 39 秒
      接受一个完整任务书单元，post-unit 两批覆盖 108/108 source entries 并保存完整 candidate ledger。
      首次全局检查发现一个无效 whitespace transport，但原 blocker 只有 judgment/part 字段路径，没有
      `source_entry_id`，导致 batch router 抛出 `semantic_batch_feedback_unroutable`。这是 Harness 可修复反馈
      元数据缺口，不是学校语义判断。
    - `_decode_whitespace_parts` 现把当前 judgment 的 canonical `source_entry_id` 附到该预校验 blocker；三个
      非法 transport contract 反例先红后绿，55 项 judgment/batch 合同和 787 项相关 contract/agent/replay
      回归通过。使用 v2 完整 ledger 的 real replay 证明反馈可映射到唯一 source entry 和 batch。随后公开
      `--resume-proof` 恢复完成了一轮 scoped revision，原 whitespace blocker 消失；下一轮只剩同批另一条
      curly quote 被改为 straight quote 的 exact-text mismatch，但再次等待超过 7 分钟无 structured output，
      已安全中止并保留 ledger。HUNAU 05 仍无 accepted review/materialization/publication，不计矩阵；当前
      证据层级是 `logic/contract + real replay feedback routing + partial E2E revision progress`。
    - current-digest HUNAU `06-proposal-v1` 从真实 logical-page DOCX 与 Registry 0.5.0 新建 task root；
      unit-boundary 经 1 次 SDK query 接受 5 个功能单元，post-unit 三批覆盖 140/140 source entries，
      accepted semantic digest 为 `12f3502b…`。readiness 暴露两个不同责任：一个“指导教师及职称”空白
      entry 同时绑定 `advisor.name.zh` 并保留 title 无独立位置的 `open_questions`，应由 Agent 继续收口；
      另一条“论证地点 + 论证日期”行已正确拆成 fixed/manual/fixed/manual，却被 compiler 错判为
      `materialization_intent_unclassified`。
    - compiler 现将只含 `fixed_label/manual_region/style_only/cleanup` 的混合 entry 编译为一个保留的人工
      复合载体，不补造字段；字段角色、重复/冲突和写入门禁不放宽。53 项 plan/readiness/runtime 回归、
      Ruff 与 mypy 通过；同一 HUNAU accepted review 的 readiness real replay 已只剩前述 Agent
      `open_questions` blocker。HUNAU 06 尚无 materialization/publication，仍不计矩阵。
    - 修复后的 same-ledger scoped revision 去掉该 `open_questions`，其余 139 judgments 保持不变；最终
      accepted digest 为 `550d9f74…`，物化 `status=ok / 6 operations / 140 receipts`，并原子发布 6 个
      唯一 slots：学院、学生姓名、学号、年级专业班级、导师姓名及论文题目。build report 的 source/
      Registry/validation/internal visual/package reopen/fill-contract hash checks 全部为 `ok`，final SHA
      为 `d5426469…`，ZIP CRC 正常。随后一次重复 resume 被 `template_publication_exists` 正确拒绝；该失败
      trace 不覆盖先前 build report 的成功事实。
    - LibreOffice 辅助渲染为 5 页 A4，封面字段保持在表格内，论证地点/日期的固定标签和人工填写骨架
      保留，未见明显裁切、重叠或说明文字外泄。该项达到 current-digest `E2E agent loop + actual DOCX/
      publication + auxiliary visual`，计入矩阵；fixed renderer 与 human acceptance 仍未完成。全仓回归
      更新为 `1157 passed / 5 skipped / 1 deprecation warning`。
    - current-digest HUNAU `07-proposal-record-v1` 从真实 logical-page DOCX 与 Registry 0.5.0 新建 task
      root；unit-boundary 接受 1 个功能单元，post-unit 单批覆盖 38/38 source entries 并原子保存 candidate。
      deterministic aggregate + Harness closure 只拒绝最后的论证地点/日期行
      `source-entry-ac23efc71b88a822618c705a`：submitted parts 漏掉开头 3 个 U+0020 空格，导致后续
      fixed/manual/fixed/manual 分段从 offset 0 起全部错位，返回 4 个 `ordered_part_text_mismatch` 和 1 个
      `ordered_part_text_gap`。
    - scoped revision 未返回 structured output。检查发现一次旧等待进程未随父命令中断退出，短时存在两个
      同 task-root 请求；已终止全部相关进程。ledger 仍为一个可解析的原子 candidate，digest
      `148ca108…`，无 accepted review、materialization 或 output 文件。HUNAU 07 不计矩阵；后续只能以
      单进程从该 ledger 恢复，不能把未返回的 revision 当成已接受语义。
    - 随后按单进程约束再次从同一 ledger 恢复，持续 5 分钟没有新 candidate 或 accepted review；中断栈
      明确停在 Claude Agent SDK `receive_response`，全部相关进程随后清空，ledger 仍保持一个原子 candidate。
      该实验把阻塞归因为 backend/Agent structured-output 无进展，而不是并发污染、Harness 校验或物化错误；
      HUNAU 07 继续不计矩阵，不再用重复 resume 制造低信息尝试。
    - current-digest HUNAU `08-defense-record-v1` 从真实 logical-page DOCX 与 Registry 0.5.0 新建 task
      root；unit-boundary 接受 1 个功能单元，post-unit 单批覆盖 46/46 source entries。6 轮交互后 accepted
      review 含 46 judgments / 64 exact resolved spans、0 open questions，semantic digest 为 `28fd1b5e…`；
      parts 只含 25 个 fixed labels 与 39 个 style-only spans，符合原表“记录、签名栏必须用黑色笔手工填写”
      的学校语义，没有补造自动字段。
    - HUNAU 08 build report 为 `status=ok`，source/Registry/validation/internal visual/package reopen/
      fill-contract hash checks 全部通过；终态采用 accepted no-slot semantic provenance，final DOCX 与 source
      SHA 均为 `053ac434…`，ZIP CRC 正常。LibreOffice 独立重开渲染为 2 页 A4，逐页辅助目检未见裁切、
      重叠或说明文字泄漏。该项达到 current-digest `real replay + E2E agent loop + actual DOCX/publication +
      auxiliary visual`，计入矩阵；fill contract 仍为 `candidate_pending_human_acceptance`，fixed renderer 与
      human acceptance 尚未完成。
    - current-digest HUNAU `09-topic-change-approval-v1` 的 unit-boundary 接受 3 个功能单元，post-unit
      三批覆盖 28/28 source entries 并完整保存 3/3 candidates。deterministic aggregate + Harness closure
      精确拒绝 U2 的两条签名/日期 source entries：两处 submitted parts 都漏掉标签前一个 U+0020，合计
      8 个 `ordered_part_text_mismatch` 与 2 个 `ordered_part_text_gap`；其余两批无需重做。
    - HUNAU 09 scoped revision 等待 5 分钟仍未返回 structured output，安全中止后无残留进程、无 accepted
      review/materialization/output。该项证明 exact-span gate 正确 fail closed，但只达到 candidate-ledger
      `real replay` 诊断层，不计 E2E/publication 矩阵；后续只能恢复受影响的 U2 batch。
    - current-digest HUNAU `10-grade-form-v1` 的 unit-boundary 接受 4 个功能单元，post-unit 以 5 个 batches
      覆盖 79/79 source entries，并保存完整 5/5 candidate ledger。首次 aggregate 的 8 个问题 entries / 14
      个 blockers 覆盖 NBSP 被改为 U+0020、纯 NBSP 留空、混合空白前缀被替成可见点及日期骨架空格类型
      错误；Harness 全部按 exact source text fail closed。
    - HUNAU 10 的一次 scoped revision 将问题缩小到 5 个 entries / 10 blockers：纯 NBSP 与复杂前缀部分已
      修正，剩余 `学号` 和三条日期骨架仍把 U+00A0 归一为 U+0020，两个单空格 entries 则被扩成多空格。
      第二次 revision 等待 6 分钟无新 structured output 后安全中止；ledger digest 为 `0ab0f865…`，无
      accepted review/materialization/output。该项证明 whitespace 指引有部分 E2E 改善，但尚未闭合，
      仍不计矩阵。
    - HUNAU `04-paper-body-v1` 的正确 accepted review（54/54 entries，semantic digest `65ec3809…`）在
      readiness 修复后通过 current Harness 再校验。恢复过程先剥离持久化 review 中 Harness 自己追加的
      `resolved_spans`，只把 `source_entry_id/parts/reason/open_questions` 投影回 Agent 输入合同；Harness
      重新解析后的 semantic digest 与原值完全相同，随后签发标准 post-unit proof。直接提交含内部 refs 的
      persisted shape 会被 54 条 `agent_authored_legacy_or_internal_id` 正确拒绝，没有放宽边界。
    - 公开 `prepare-template` 从该 post-unit proof 以 0 新 Agent turns 完成 deterministic recovery：物化
      `22 operations / 49 receipts`，发布 42/42 唯一 slots，build report 所有检查为 `ok`，final SHA 为
      `b6bcd941…`。两个关键 source entries 都各自发布 `body.heading.outline4 text[0:5]` 与
      `body.paragraph text[5:11]`，没有重选位置或丢失同行正文。LibreOffice source/final 均为 3 页 A4，
      第 3 页空白是源结构已有；前两页格式说明已清理，未见明显裁切或重叠。该项以“既有 live Agent
      accepted review + current deterministic real replay/publication + auxiliary visual”计入矩阵；不是新的
      单命令 E2E，fixed renderer 与 human acceptance 仍未完成。
    - 为避免复用 HUNAU 03 已知 false-green 的 v1/v2 candidates，新建 `hunau-03-toc-v3` fresh task root；
      但 unit-boundary 在 180 秒内没有任何 Tool call 或 structured result，Harness 以可重试
      `template_agent_no_progress_timeout` 退出。该 root 没有 hash-bound checkpoint、candidate 或 output，
      不提供 real replay/E2E 证据；HUNAU 03 继续不计矩阵。当前不再用相同 backend 做无差别重试。
    - HUNAU `03-toc-v4-m27hs` 改用同一 MiniMax Anthropic 兼容端点的 `MiniMax-M2.7-highspeed`，fresh
      unit-boundary 接受 4 个功能单元，post-unit 四批覆盖 28/28 source entries；一次 scoped revision 后
      accepted review 含 28 judgments / 33 exact spans，semantic digest 为 `a63394f5…`。其中目录缓存 25 个
      `generated_content` parts 绑定 `generated.toc`，目录标题中的两个间距符号、两处空行提示及格式说明均
      正确判为 `style_only`。Agent 语义和 Harness span closure 正确，但首个 build 仍显示 `目□□录`：根因是
      runtime 把 mixed judgment 编译成 `REFRESH_GENERATED_CONTENT` 后只写 policy receipt，从未调用现有的
      exact-fragment rewrite，责任层是确定性物化而不是 Agent/Skill。
    - `src/docfit/template/materialization/runtime.py` 现让 `REFRESH_GENERATED_CONTENT` 走同一个基于 accepted
      spans 的非槽位清理路径；实现不读取学校文字或占位符形状。新增 contract 先稳定复现旧输出
      `目□□录`，修复后输出 `目录`。同一真实 inventory/accepted review 的 current-code replay 物化为
      `0 operations / 4 cleanup / 25 policy receipts / 29 mutation receipts`，正式发布为 `slot=0 / manual=1 /
      gap=0 / unresolved=0`，final SHA 为 `7623da00…`；Fill Contract v2 与 publication provenance 交叉校验
      通过。固定 Docker LibreOffice 25.2.3.2 渲染为 1 页，标题、空行提示和格式说明均已清理，25 个目录
      生成内容条目保留。该项以“fresh live Agent accepted semantics + current deterministic real replay /
      publication + fixed-render auxiliary visual”计入矩阵；不是修复后一轮从头 Agent E2E，human acceptance
      仍未完成。
    - HUNAU `07-proposal-record-v1` 随后通过原 source-bound unit proof 恢复并完成发布，但 Agent 把
      “记录、签名栏必须手工填写”错误扩大成整表责任，只发布 `submission.date` 一个字段；学生姓名、学号、
      年级专业班级、导师姓名/职称与论文题目等相邻标签后的独立值单元格仍为空。固定 Docker LibreOffice
      25.2.3.2 渲染为 2 页且机械版式稳定，但字段语义明显漏失，因此是 `E2E agent loop + publication`
      的产品假绿，不计矩阵。
    - HUNAU `09-topic-change-approval-v1` 同样从原 source-bound unit proof 恢复并完成发布，28/28 judgments
      的 exact-span closure、物化和 build report 均通过；但只发布学院及两处签名姓名字段，学生姓名、学号、
      年级专业班级和题目前后值单元格没有形成正确接口。该项再次证明 mechanical closure 不能替代学校
      语义验收，HUNAU 09 仍不计矩阵。
    - 对 07/09 的共同归因位于 post-unit Agent-facing Skill/Reference：reading packet 已按文档顺序提供
      标签与独立空白 source entries，Registry 0.5.0 也提供对应学生基础信息字段；旧规则却把“人工表单”
      默认扩大为 whole-unit manual，与学校文字仅点名记录/签名区域的范围冲突。主 Skill、模板文字分类和
      Registry reference 现明确按点名范围区分基础信息与记录/签名/评语，并要求无匹配字段的地点、记录人
      保持人工责任或 `needs_input`，禁止借用研究方向/姓名等近似字段；复合年级专业班级字段须覆盖整个
      复合值骨架。新增 Skill contract 均先红后绿，完整 Skill contract 为 `29 passed`；Agent boundary、
      documentation、source-location 与 Skill 合并回归为 `50 passed`。
    - 修正规则后的 `hunau-07-proposal-record-v2-manual-scope` 已证明模型能把基础信息与人工记录区分开，
      并发布学院、学生姓名/学号/年级专业班级、导师姓名/职称和论文题目；但它又把论证地点错误绑定为
      `author.research_direction`，且只把复合骨架的年份片段绑定 `author.cohort_class`。该次运行虽返回
      `status=built`，仍因字段含义和 span 错误不计矩阵，并直接促成上述字段替换自检规则。
    - `hunau-07-proposal-record-v3-field-meaning` 正确关闭地点误绑和复合 span，却漏掉学院并把模板下载/
      手写说明保留为固定文字；`hunau-07-proposal-record-v4-form-closure` 又正确清理说明、保留人工地点日期、
      覆盖完整复合骨架，但错误声称当前词表没有学院字段。真实 packet 中 `author.department.meaning`
      明确覆盖“所属院、系或培养单位”，所以 v4 仍是 Agent 同义语义匹配漏判，不是词表或 Harness 缺口。
      Skill/Registry reference 已补“学院/院系/培养单位按 meaning 匹配”和混合行独立责任规则；v3/v4 即使
      build report 全绿也均不计矩阵。
    - `hunau-07-proposal-record-v5-org-unit` 的首稿终于同时包含学院、其余基础字段、完整复合骨架、人工
      地点日期和说明清理；但它只因“记录人”后的 13 个空格缺失收到 mechanical revision 后，把同一 entry
      的学院字段责任一并删除，最终 6-slot 产物再次假绿。Skill 现明确纯原文字符/空白传输修订必须保持原
      字段责任不变；`v6-revision-stability` 随后未返回合法 structured result，属可重试 Agent 输出失败。
      两者均不计矩阵。
    - HUNAU 09 在新人工区范围规则下的 `v2-manual-scope` 发布 9 slots，基础信息已补齐，但把变更原因绑成
      `thesis.title.zh`、基层组织意见绑成 `author.major`、表单容器绑成 `body.table`，并让变更前后题目复用
      同一个单值字段；`v3-approval-semantics` 清除了原因/意见/正文表格误绑，却仍让变更前后复用题目字段，
      且把固定“学院”标签包进填充值 span。两次 build report 均为 ok，但字段含义或范围错误，均不计矩阵。
      主 Skill 与两份 Reference 现进一步冻结：变更原因、审批意见和签署内容无专用字段时保持人工责任；
      表单容器不是正文代表结构；不同时间状态或预期值不是真实镜像，不能复用一个单值字段。
    - `hunau-10-grade-form-v2-revision-stability` 使用原 4-unit source-bound checkpoint 与更新后的 Skill
      重跑，标题、学院、64-entry 主表尾部和说明共 5/5 batches 均原子保存；aggregate 后的 scoped revision
      在 Claude Agent SDK `receive_response` 超过 9 分钟仍无新 structured output，已安全中止并确认无残留
      prepare-template 进程。ledger 保留 79/79 candidate judgments，但没有 accepted review、物化或 output，
      因此只算 candidate-level real replay 诊断，HUNAU 10 仍不计矩阵。
    - `hunau-05-design-task-v3-revision-stability` 使用原单元 source-bound proof 与同一更新 Skill 做独立重跑；
      108-entry 大批次完成一次 evidence 读取后返回可重试 `semantic_batch_result_invalid`，没有保存 candidate、
      accepted review、物化或 output。它没有提供修正规则的正向 E2E 证据，HUNAU 05 仍不计矩阵，也不以
      无 structured result 反推 Harness 或字段合同失败。
    - 后续核对本机实际配置发现默认 MiniMax backend 已为 `MiniMax-M3`，而前述部分恢复实验显式降到了
      `MiniMax-M2.7-highspeed`。保持 source DOCX、Registry、hash-bound proof、schema 与 Harness 不变，
      改回 M3 后 HUNAU `07-proposal-record-v7-m3` 完成 38/38 exact judgments 并发布 7 个字段：学院、
      学生姓名/学号/年级专业班级、导师姓名/职称和论文题目；论证地点、日期及记录人继续为人工区，模板
      下载/手写说明被清理。final SHA 为 `c0232e02…`，build report 全绿；Docker LibreOffice
      25.2.3.2 固定渲染 source/final 均为 2 页，字段、表格和人工区未见裁切、重叠或乱码。该项达到
      current-digest `real replay + E2E agent loop + actual DOCX/publication + fixed-render auxiliary
      visual`，计入矩阵，但仍无 human acceptance。
    - HUNAU `09-topic-change-approval-v4-m3` 的 M3 首稿已正确区分变更前题目、原因、意见、签名等人工责任，
      只建立学院、学生姓名/学号/年级专业班级及变更后题目 5 个字段；Harness 只拒绝两条签名日期行的
      前后边界空白。`8c59c58` 将稳定修复写入主 Skill：签名/日期可见内容保持 `manual_region`，大段边界
      空白单独作为 `style_only` parts。same-ledger resume 后 exact spans 全部闭合，final SHA
      `f0402eb4…`，build report 全绿；固定 LibreOffice source/final 均为 2 页，表单、人工区和字段位置
      正常。该项计入矩阵，仍不是 human acceptance。
    - HUNAU `10-grade-form-v3-m3` 在 M3 下保存 5/5 批、79/79 candidate judgments；字段语义正确，
      包含学院、学生姓名/学号/年级专业班级、导师、题目、中文摘要和关键词，但 deterministic Harness
      只剩 5 个 entries / 10 个 exact blockers：`学号`、单 NBSP 和三条日期把 U+00A0 与 U+0020
      归一。`4b7b382` 以红绿合同要求按 packet 的 offset 将连续 U+00A0 和普通空格拆成独立 parts，禁止
      视觉等价归一；两次 same-ledger scoped resume 均在 SDK `receive_response` 超过约 12 分钟无新
      candidate 后安全中止，因此 v3 仍无 accepted review 或发布。
    - `hunau-10-grade-form-v4-m3-nbsp` fresh loop 证明上述字符规则能进入真实 Agent 输出并完成 79/79
      exact-span closure、物化和发布，final SHA `3d391a77…`；但产品复核发现 Agent 把固定“学　　号”
      标签本身绑定为 `author.student_id`，同时漏掉相邻学生姓名、真实学号空值、年级班级、导师和题目
      空值。该 build 是 mechanical green / semantic false-green，不计矩阵；不得把 v3 的正确字段语义与
      v4 的正确字符分段人工拼成一个不存在的通过结果。HUNAU 10 仍是唯一缺失项。
    - `849ea3c` 进一步把通用标签/值边界写入主 Skill：可见字段标签旁有独立值 source entry 时，标签
      必须 fixed，字段只能绑定独立值位置。`hunau-10-grade-form-v5-m3-label-value` fresh loop 的 5/5 批
      随后保存 79/79 judgments；学院、学生姓名/真实学号空值、年级班级、导师、题目、中文摘要和关键词
      8 类字段均回到独立值位置，证明新规则进入真实 Agent 输出。该候选仍把两个日期的 NBSP 归一，并把
      最后一条评审签署日期误绑为论文提交时间字段；scoped revision 超过 12 分钟无新 candidate 后安全
      中止。`41de718` 用 task-local meaning 而不是 canonical ID 冻结：论文/文档提交时间字段不得代替
      评阅、签署或审批日期，无专用字段时保持人工责任。v5 只有 candidate-level real replay，不计矩阵。
    - HUNAU `05-design-task-v4-m3` 首次让 108-entry 真实输入完成多轮 Agent revision 和发布，7 个基础
      字段位置均可执行，但固定渲染复核发现 Agent 把 `□生产实际或社会实际`、`□其他` 误判为
      cleanup，导致“选题来源”能力被删；该机械全绿产物不计矩阵。`408e1cb` 以红绿 Skill contract 冻结
      “未预选复选/单选项是等待人工选择的表单能力，必须保留为 `manual_region`”。
      `hunau-05-design-task-v5-m3-checkbox` fresh loop 随后以 2 批 108/108 judgments、2 sessions / 15 turns
      完成 accepted review 和发布：学生姓名、学号、年级专业班级、学院、提交日期和论文题目 6 个字段
      精确绑定；“指导教师及职称”的单一空值位置因无法无重叠承载姓名与职称两个字段而保持人工；三类
      选题来源复选项全部保留。final SHA `175a2319…`，build report 全绿；Docker LibreOffice 25.2.3.2
      固定渲染 source 6 页、final 5 页，清理说明后表格连续，未见裁切、重叠、乱码或表格破损。该项达到
      current-digest `real replay + E2E agent loop + actual DOCX/publication + fixed-render auxiliary
      visual`，计入矩阵，仍无 human acceptance。
    - HUNAU `10-grade-form-v6-m3-full-rules` 保存 79/79 正确字段语义候选，但旧 scoped revision 要求
      Agent 重发整批 64 条；`b335a14` 将修订合同改为只返回受影响 source entries，并在 ledger 原位合并。
      同一 v6 ledger 的真实恢复把 5 entries / 13 blockers 缩至 1 entry / 4 blockers 并最终发布 8 slots，
      但产品复核发现最后一次纯字符修订把“答辩委员会主任签名”日期从 `manual_region` 改为
      `fixed_label`，因此 v6 是新的 semantic false-green，仍不计矩阵。
    - `820d050` 进一步冻结纯 `ordered_part_text_*` 修订的 ordered role/field_id responsibility；真实
      `hunau-10-grade-form-v7-m3-semantic-lock` 首轮保存 64 + 13 共 77/77 candidates，Harness 实际拒绝
      Agent 把最后签名日期责任改掉，并以 `semantic_batch_candidate_failed` fail closed。`9e1ad12` 随后
      把“单一责任 + 纯 exact-text blocker”归还 Harness：直接用 canonical source text 机械闭合，混合
      责任仍由 Agent 修订。同一 v7 ledger 以 `client_count=0` 完成恢复、accepted review、8-operation
      物化和发布；final SHA 为 `76498c60…`。8 个字段分别为学院、学生姓名、学号、年级专业班级、导师、
      论文题目、中文摘要和关键词，全部位于独立值位置；三条签名日期均保持 `manual_region`。
      固定 Docker LibreOffice 25.2.3.2 source/final 均为 3 页，高分辨率检查未见裁切、重叠、乱码、
      表格破损或分页漂移。该项达到 current-digest `real replay + E2E agent loop + actual DOCX/publication
      + fixed-render auxiliary visual`，计入矩阵，但仍不是 human acceptance。
    - 本轮新增五个语义/字符规则的完整 Skill contract 为 `34 passed`；关闭 Docker renderer 后全仓
      `uv run pytest -q` 为 `1172 passed / 5 skipped / 1 warning`。Docker 开启时另有一个用户内容提取
      模块的环境条件集成测试失败（期望 `PARTIAL`、实际 `NEEDS_INPUT`），与本轮模板提取调用面无关，
      未跨模块修改。上述 task roots 提供真实 replay、E2E、发布和固定渲染证据，不能与 contract 回归
      混为同一验证层级。
- Phase 7 reachability 复核：旧 Tool alias、`accepted_units` fallback、`remove_hint`、Eval legacy loader
  与 `FIELD_RENAMES` migration 没有重新进入生产成功路径；`object_text_spans` 只保留在 Harness/
  reading-packet 内部账本与 Agent denylist/sanitizer，`slot_materialization_unexecutable` 仍只作为失败码。
- 外部验收门复查：本轮临时启动固定 Docker LibreOffice 25.2.3.2（image digest `64726dd7…`、font
  digest `841467b1…`）并完成三校 32/32 source/final 固定渲染与全页复核。整体
  `docfit doctor --require visual-renderer` 仍为 `NOT_READY`，因为 OfficeCLI 1.0.144 executable hash
  不匹配锁定版本，agent smoke receipts 也不完整。该辅助渲染证据不能代替 Word pixel parity 或
  human acceptance。

### 2026-09-13 Phase 8 complete fixed-render review

- 覆盖层级：对 current Registry 0.5.0 / `e139059b…` 的 32 个 canonical task roots，使用固定 Docker
  LibreOffice 25.2.3.2 分别渲染 source 和 final，共 64 次，全部 `status=ok`；随后逐份查看 final 全页，
  对页数变化或可疑布局补看 source 对照及单页高分辨率图。该证据是 `fixed-render auxiliary visual`，
  不是 Word pixel parity 或 human product acceptance。
- 结果：29/32 未发现新的阻断性裁切、重叠、乱码或表格破损。HUNAU `01-cover` 的第二空白页等若干
  页面差异在 source 中已存在，按本次 source/final 对照不归为新回归；HUNAU `05-design-task` 的 contact
  sheet 初看异常经逐页原图排除，封面、说明、未选复选项和连续表格均完整。
- 首轮尚未接受的 3 项及处置：
  - NJAU `06-body` 的三章被压到第一页、后两页只剩页眉页脚；根因是单个外层 body structure SDT 跨越
    section-break 段落。`3c43656` 改为在 section 边界处分块，section-break 段落保持 body 顶层；真实
    accepted ledger 回放和固定渲染恢复为三章三页，关闭该项。v4 task root 的输入在复核期间被外部软件
    追加一条 `docProps/custom.xml` 属性，SHA 不再匹配账本；回放明确改用同内容且 SHA 与 v4 ledger
    完全匹配的 v3 immutable source，未覆盖或伪造 v4 输入。
  - PKU `08-body` 的第五章标题与页眉区域叠排由同一 section 分块修复关闭。剩余竖排 `(2.1)/(4.3)`
    来自 Agent 明确保留的公式表格、自动编号域和人工填写区，不是 cleanup 残片；LibreOffice 对未更新
    STYLEREF/SEQ 域的近似显示在当时仍需锁定 Office 后端复核；后续验证与处置见下方
    “Phase 8 Word compatibility closure”。
  - PKU `04-abstract-en` 的 source 为一页，final 增加仅含页眉页脚的第二页。差分探针排除 SDT 容器：
    解包全部内容控件仍为两页；恢复原英文示例后回到一页；任一单个中文占位不触发，前四个中文占位
    组合才触发。当前归因为 LibreOffice 字体/行网格累积分页差异，不能在没有 Word parity 的情况下
    通过缩短通用占位符或删除布局载体掩盖。
- 该轮结束时 Phase 8 保持 REOPEN：fixed-render coverage 和已确认的 section 代码回归已关闭；当时
  剩余内部门是 PKU 04/08 的锁定 OfficeCLI 验证。该历史状态已由下方 Word compatibility closure
  替代；最终 human acceptance 仍必须由人签收，coding agent 不得代签。

尚未完成，不能宣称:

- Phase 0–7 在 section-boundary 修复后的全仓 `1173 passed / 5 skipped / 1 warning` 中仍保持 ACCEPTED；按 current vocabulary
  digest `861eccc3…` 的 task-local 成功产物计，E2E/publication 矩阵现为 `32/32`：HUNAU `10/10`、
  NJAU `10/10`、PKU `12/12`。Phase 8 仍是唯一 REOPEN 阶段：64 次 source/final 固定渲染和 32/32
  全页复核已完成，NJAU 06/PKU 08 的 section 回归已修复；PKU 04/08 的锁定 OfficeCLI 与 Word
  实机复核已在后续 closure 中关闭，human acceptance 尚未签收。
- 现有 32 个 current-digest 发布项都没有 human acceptance；HUNAU `01-cover` 的换行溢出、
  NJAU `01-cover` 的居中容器裁切，以及 NJAU `06-body` / PKU `08-body` 的 section-boundary 回归
  已在真实 ledger replay 和固定渲染中关闭。PKU `04-abstract-en` 的尾部空白页与 PKU `08-body`
  的尾部空白页与 PKU `08-body` 的自动编号域已由锁定 OfficeCLI 和 Microsoft Word 实机复核定性；
  不能凭 internal `visual_review_bound=ok` 或 LibreOffice 近似显示签收，仍需人工产品签收正式产物。

- 下列历史 live provenance 项若未在 task-local build report 中绑定 Registry 0.5.0 / `e139059b…`，
  只能计作 canonical source-entry/span 与当时代码行为证据，不能计入当前 Registry 0.5.0 验收矩阵。

- Phase 2 的 `E2E agent loop` 已完成 0820 `01-cover`、`02-integrity-statement`、
  `03-toc`、`04-paper-body`、`05-design-task` 和 `06-proposal` 切片；HUNAU current-hash
  10/10 logical-unit 切片；NJAU `06-body`
  whole-unit body-structure 切片；NJAU `07-references` 集合接口切片；NJAU `08-appendix`
  appendix-title/body 双接口切片；NJAU `01-cover` through `05-abstract-en` front-matter 切片；
  NJAU `09-academic-achievements` 和 `10-acknowledgement` 切片；
  HUNAU/NJAU/PKU 代表 logical unit live Agent 验收也已完成。
  三校 32/32 logical units 的 live Agent/publication 矩阵已完成；human acceptance 尚未完成。
- Phase 3 已补 range 多 block span 解析、cover 真实 inventory 输入面、内部 object text span
  精度门、block 内 exact gap 门和三校 current-code inventory replay；32/32 live E2E/publication
  矩阵已闭合，完整 fixed-render 与 human acceptance 尚未完成。
- Phase 5-6 已完成 cover 当前代码 real replay / live product-provenance、HUNAU current-hash
  10/10 logical-unit product-provenance、`02-integrity-statement`
  manual source-noop product-provenance、HUNAU current-hash `03-toc` generated-only no-slot
  product-provenance、HUNAU current-hash `04-paper-body` body candidate feedback/product-provenance、
  HUNAU current-hash `05-design-task` mixed manual/slot provenance、`06-proposal` manual no-slot
  product-provenance、`04-paper-body` live7 可发布产物切片、NJAU `06-body` whole-unit
  body-structure product-provenance、NJAU `07-references` collection slot provenance、NJAU
  `08-appendix` appendix-title/body provenance、NJAU `09-academic-achievements` terminal
  source-noop provenance、NJAU `10-acknowledgement` body slot provenance、NJAU
  `01-cover` through `05-abstract-en` front-matter provenance，以及三校 32/32 logical unit provenance
  matrix；真实 task root replay / publication 矩阵已完成，human acceptance 尚未完成。
- Phase 6 publication/fill-contract 已有三校 32/32 产物 provenance 证据；完整 32 项 fixed-render
  coverage 已完成，section-boundary 回归已有真实 ledger 回放和固定渲染修复证据；PKU 04/08 的锁定
  OfficeCLI 验证和 human acceptance 未完成，不能宣称视觉验收通过。
- Phase 8 的代码与回归基线已收口到全仓 `1173 passed / 5 skipped / 1 warning`，PKU 正文已推进到
  110-slot 发布产物，HUNAU/NJAU/PKU current-digest publication 达到 10/10、10/10、12/12；但测试绿色
  和固定 LibreOffice 辅助目检都不能替代完整 fixed-render 矩阵与人工签收。
- `real replay`、`E2E agent loop` 与 actual DOCX/publication 已覆盖 0820 代表单元和三校 32/32
  logical units；PKU 04/08 的锁定 OfficeCLI 验证已由下方 closure 关闭，Phase 8 只剩 human
  product acceptance，不能由 coding agent 代签。

### 2026-09-13 Phase 8 Word compatibility closure

- 先用 Microsoft Word 复核剩余两项，而不是把固定 LibreOffice 近似渲染当作 Word parity：
  PKU `04-abstract-en` 的 final 直接打开且状态栏为 1/1 页，确认 LibreOffice 的第二空白页不是
  DOCX 产品缺陷；旧 PKU `08-body` final 则稳定触发“发现无法读取的内容”恢复提示，因此 Phase 6/8
  曾按真实产品故障重新打开。
- 短归因与最小探针排除了 section 分块和内容控件本身。第一个确定性根因是三个 Word 写入入口分别
  使用不完整的 ElementTree namespace map：例如源文档的 `mc:Choice Requires="wps"` 在无修改回写后
  仍引用 `wps`，声明却漂移为 `ns10`。`5c5e613` 将 materialization、object mutation 和 section import
  收敛到共享 Word XML serializer，稳定保留常用 OOXML 前缀，并补齐所有 Markup Compatibility
  prefix-valued attributes 所引用的声明。修复后的 PKU08 source no-op roundtrip 在 Word 中无恢复提示
  打开为 15 页。
- 第二个确定性根因是 accepted cleanup 删除表格单元格的唯一段落后，留下 49 个没有 block content 的
  `w:tc`。诊断件只补回空 `w:p` 后即可在 Word 中直接打开；runtime 现保证清理后的 table cell 仍有
  合法尾段落。包级 postcondition 同时新增两类 fail-closed 检查：未声明的 Markup Compatibility 前缀、
  以及没有 block content 的 table cell 均返回 `invalid_word_xml_contract`，不再生成“ZIP/XML 检查绿、
  Word 打开修复”的候选件。
- exact accepted ledger 的 current-code deterministic replay 为 `1 operation / 72 cleanup / 183 receipts`，
  随后以 0 新 Agent turns 从 post-unit proof 正式重新发布 PKU08：110 slots、98 gaps、0 manual、
  final SHA `0ffb5b8a…`，Fill Contract SHA `9aefb7bf…`，build report 的 source/Registry/validation/
  internal visual/package reopen/hash checks 全部为 `ok`。这替换矩阵中旧的不可直接打开候选，不改变
  Agent accepted semantic judgments 或 source-entry/span 定位。
- 锁定验证使用 OfficeCLI 1.0.143、executable SHA `2f158d46…`：ZIP/XML reopen、OpenXML validation、
  source hash、placeholder scan 与 13/13 fixed-render page coverage 均通过。固定 LibreOffice 仍把若干
  公式编号域近似显示为竖排并渲染 13 页；同一 SHA 的 Microsoft Word 实机无恢复提示打开为 10 页，
  因而该差异继续记为 non-blocking approximate-render warning，而不是修改学校模板语义或缩短内容来
  迎合 LibreOffice。实际 Word 补充复核覆盖第 5 页公式/编号/数据表、第 9 页第四章公式编号与 13 列表格，
  以及第 10 页末章收尾：公式和编号均为正常横向布局，宽表格结构完整，末章页眉、正文和分页无叠排。
- 回归层级：相关 materialization/Tool 套件 `106 passed`；ruff 与五个生产文件 mypy 通过；关闭 Docker
  后全仓 `1178 passed / 5 skipped / 1 warning`。全量首次运行暴露一个测试 helper 也会丢失
  `mc:Ignorable` 声明；该 synthetic DOCX 在 Word 中同样触发恢复，helper 已改用共享 serializer 后通过。
- 当前结论：Phase 0–7 继续 ACCEPTED；Phase 8 的代码、real replay、重新 publication、锁定 OfficeCLI、
  fixed-render 全页复核和 Microsoft Word 打开门均已关闭。唯一不能由 coding agent 完成的是最终
  human product acceptance，因此 Phase 8 仍只在人工签收层保持 REOPEN；不得表述为产品验收已经完成。
