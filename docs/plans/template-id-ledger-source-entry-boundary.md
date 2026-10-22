---
plan_scope: template-id-ledger-source-entry-boundary
status: CURRENT_LEDGER
created: 2026-09-04
verification_level: source/documentation audit
---

# 模板提取 ID 账本与 Source Entry 边界

本文固定当前 ID 词汇的责任层，避免把 `field_id` 误读为原始 DOC 定位 ID。

核心结论：

- `field_id` 是 Content Field Registry 的内容字段 key，只表达“这段模板接口应该接收哪类内容”。
  它不是 DOCX 源对象、Word locator、render 区域、候选目标或物理 span 的定位凭证。
- `source_entry_id` 应成为 canonical source entry 的唯一 ID。canonical source entry 由输入 normalize
  层在绑定 source hash 的源 inventory 中生成，不由 Agent 生成；它可以归并一个或多个 raw Word object。
- 未来唯一 source 定位层应收敛为 `source_entry_id` 加基于该 entry 的 span ID/ref。当前的
  `reading_block_id` / `range_id` / `span_ref` / `slot_ref` 都只能归类为 `source_entry_id`
  的派生层或过渡层，不能反过来当作原始源定位 ID。

## 层级定义

| 层 | 含义 | 可否给 runtime Agent | 稳定动作 |
| --- | --- | --- | --- |
| Source entry | 输入 normalize 层生成的 canonical 源内容单元；`source_entry_id` 是其唯一 ID，provenance 绑定 source hash、backend locator/type/fingerprint | 已给 Agent source-entry 投影；raw provenance 不给 Agent | 迁移到 `source_entry_id + span` |
| Source span | 一个 source entry 内或多个连续 source entry 上的文本/结构子范围 | 默认不由 Agent 写；Harness 可返回语义化反馈 | 由 `source_entry_id + offsets/order` 派生 |
| Reading packet | 给 Agent 判断学校语义的 source-entry 投影和可读 view | 可以给；`source_entry_id` 是主入口，`reading_block_id/range_id` 只是辅助 view token | 保留，但写明是 source-entry 派生工作面 |
| Content field | Registry 里的内容语义 key | 可以给；来自 `field_id_vocabulary` | 保留 `field_id`，禁止当 locator |
| Fill interface | 最终模板上可填槽/区域的目标引用 | 下游可见；Agent 不输出 | `slot_ref` 保留为 fill interface ref，不是源定位 ID |
| Runtime ledger | hash、candidate、object refs、locator、coverage、Tool/SDK trace | 不给 runtime Agent | 留在 Harness/Tool/App/trace |

## 当前 `*_id` / `*_ref` 含义

| 名称 | 当前实际含义 | 分类 | 处理 |
| --- | --- | --- | --- |
| `source_entry_id` | 长期主名：canonical source entry ID；entry 由 normalize 层生成，可覆盖一个或多个 raw object | 源定位 ID | 所有新增 source-localization 合同使用该字段 |
| `object_id` | inspect 快照对象 ID，当前由 `document_sha256 + locator + type` 哈希生成 | 现有源/候选对象账本 | 迁移为 source entry provenance 或 `candidate_entry_id`；不得 Agent-authored |
| `object_ref` | `document_sha256 + object_id + expected_fingerprint` 的快照对象 ref | 内部账本 ref | 保留为 backend 私有 ref 或迁到 `source_entry_ref`；不得给 Agent 默认面 |
| `locator` | Word/OOXML 路径或 content-control tag locator | 内部/backend 定位 | 只在 Tool/App/Fill Contract 机器合同中使用；不得让 Agent 输出 |
| `target_ref` | 候选 DOCX mutation 目标对象 ref | 内部候选目标 ref | 保留内部；不是 source 定位 |
| `source_object_id` / `source_object_ref` / `source_object_ids` / `source_locators` | 用户内容模块里指学生源 DOC 物理对象 | 现有源对象账本 | 迁移到 `source_entry_id` / `source_entry_ref` / `source_entry_ids` |
| `transport_source_object_id` | 复制块或富内容时选定的学生源 transport 对象 | 派生传输锚点 | 迁移为 `transport_source_entry_id` |
| `covered_object_ids` | reading block、unit、resolved span 覆盖的底层 inspect 对象集合 | 内部 coverage 账本 | 迁移为 `covered_source_entry_ids` |
| `object_text_spans` | reading block 文本与底层对象的字符映射 | 内部 span mapping | 迁移为 `source_entry_text_spans` |
| `field_id` | Registry 内容字段 key，例如 `author.name.zh`、`body.paragraph` | 内容字段 key | 保留；只能来自 Registry / `field_id_vocabulary` |
| `parent_field_id` | Registry 字段父子关系，例如正文成员归属容器字段 | 内容字段 key | 保留；不是 locator |
| `member_field_id` / `member_field_ids` | body structure 成员字段 key | 内容字段 key | 保留内部；必要时统一为 field key 命名 |
| `field_ids` / `allowed_field_ids` | 字段 key 列表；前者多为内部 materialization payload，后者是 Agent 输入词表 | 内容字段 key 列表 | `allowed_field_ids` 保留 Agent 可见；`field_ids` 不作 Agent 输出字段 |
| `field_id_vocabulary` | 当前 task Registry snapshot 派生的 Agent 可选字段词表 | 内容字段词表 | Agent 可见，唯一正向字段来源 |
| `field_registry_ref` / `registry_id` / `registry_ref` | Registry snapshot identity/hash/version 或 Registry 账本引用 | Registry 身份 | 保留；不是源定位 |
| `unit_id` | Agent 提出的学校功能单元逻辑 ID | Agent 语义分组 ID | 保留 Agent 可见；不是源定位 |
| `reading_block_id` / `block_id` | unit reading packet 中的可读块 ID；当前由 `unit_id + order` 生成 | source-entry 派生工作面 | 保留给 Agent scope；底层 provenance 应迁到 source entry |
| `reading_range_id` / `range_id` / `unit_range_id` | reading block 或 whole-unit reading range ID | source-entry 派生工作面 | 保留给 Agent scope；不得当原始 DOC ID |
| `span_ref` | Harness 从 `scope kind + scope id + part_index` 解析出的 ordered part span ref | source-entry 派生/过渡 ref | 保留内部/下游 provenance；下一步应基于 source entry span 生成 |
| `slot_ref` | `span_ref + field_id` 派生出的可填写接口 ref；写入 content-control tag 和 Fill Contract | 派生 fill interface ref | 保留；不是源定位 ID，也不是 Agent 输出 |
| `region_id` | Fill Contract 中非槽位 region 的逻辑目标 ID；当前多为 legacy/eval | 派生 fill interface ID | 后续若继续使用，迁为 `region_ref` 并绑定 source span provenance |
| `content_id` | Student Content Model 中归一化后的内容事实/实例 ID | 内容实例 ID | 保留；不是源 DOC 组件 |
| `source_content_id` | 历史命名来源和既有用户内容 inventory 兼容字段 | legacy/compat 内容项 ID | 不再作为新增合同主字段；既有 Student Content Model 使用按兼容处理 |
| `parent_content_id` / `source_content_id` / `target_content_id` | Student Content Model 中层级或关系边 | 内容关系 ID / legacy compatibility | 新合同不得用 `source_content_id` 表达 source entry |
| `style_contract_id` / `style_contract_ref` | 样式合同 identity 和 digest ref | 样式合同 ref | 保留；不是源定位 |
| `style_role_id` / `style_role_ref` / `property_profile_ref` | 样式角色和属性 profile 引用 | 样式账本 ref | 保留；内部或下游机器合同 |
| `style_id` / `word_style_id` / `run_id` / `para_id` / `num_id` / `relationship_id` / `image_id` | Word/backend 样式、段落、编号、关系、媒体对象 ID | backend 内部 ID | 不作为 DocFit 源定位合同 |
| `render_ref` / `candidate_render_ref` / `compare_render_ref` / `evidence_ref` | 视觉或证据存储引用 | 内部证据 ref | 不给 Agent 默认输出；反馈需改写成可见文本/页码 |
| `judgment_ref` / `judgment_refs` / `source_judgment_refs` | Harness 接受后的 semantic judgment 数组位置引用 | 内部 review provenance | 保留内部；Agent 不自造 |
| `scope_ref` / `scope_refs` | materialization plan 对 reading scope 的内部引用 | 内部派生 ref | 保留内部 |
| `intent_ref` / `plan_ref` / `context_ref` / `command_ref` / `unsupported_ref` / `batch_ref` / `payload_ref` | materialization/apply 阶段的内部执行账本引用 | 内部派生 ref | 保留；不作为业务 ID |
| `session_id` / `tool_use_id` / `parent_tool_use_id` / `agent_id` / `event_id` / `message_id` | SDK、Tool、trace 或观测事件 ID | runtime trace | 内部账本 |
| `case_id` / `gold_id` / `actual_id` / `report_run_id` / `eval_config_ref` | Eval/Gold/report identity | Eval 账本 | 不进入 runtime Agent 语义合同 |

局部变量如 `raw_id`、`new_id`、`by_id`、`seen_ids`、`current_id`、`expected_ids` 不是产品合同字段；
它们按所承载的数据归入上表对应层，不单独定义语义。

## 当前字段影响面 inventory

调查范围：`src/`、`tests/`、`.claude/skills/docfit-school-extract/`、`docs/contracts/`、
`docs/modules/`、`docs/plans/`、`evals/`。本文只记录字段责任层和迁移判断，不修改行为。

| 字段 | 当前使用层 | 当前语义 | 迁移判断 | Agent 可见性 |
| --- | --- | --- | --- | --- |
| `source_content_id` | Agent 输入、Agent 输出、Student Content Model、legacy | 用户内容提取 inventory 和 annotation schema 的源内容项 key；`src/docfit/content/extraction.py` 用它验证每个学生源内容项正好标注一次，并写入 Student Content Model；`src/docfit/app/student_content_fill.py` 把它放进学生内容提取 prompt | 对新增 source-localization 合同不是改名入口，而是 legacy/compat 清理；既有 Student Content Model 需要单独迁移或兼容读取 | 模板提取 Agent 不可见；用户内容提取 Agent 当前可见，属 legacy 兼容工作面 |
| `source_entry_id` | Agent 输入、Agent 输出、Harness 内部、Tool 执行、legacy 迁移测试 | post-unit 入口已由 normalize 层生成 canonical source entry，可覆盖一个或多个 raw object；`reading_packet.py` 生成 Agent-visible `source_entries` 投影；Agent 新输出合同使用 `semantic_judgments[].source_entry_id + parts`；Harness gate 以 source entry span 闭包为准；materialization 入口消费 Harness-resolved source-entry spans | 生成、Agent 输入、Agent 输出、Harness gate 和 materialization 入口已切到 source-entry-based；后续只剩 denylist/legacy 清理与更大范围 replay | 可作为 source entry 投影给模板 Agent；不能携带 raw provenance |
| `object_id` / `object_ref` | Harness 内部、Tool 执行、Fill Contract/Eval 辅助、Student Content Model、legacy | inspect/backend 快照对象和 stale-check ref；模板侧 raw 对象已作为 canonical source entry provenance 和 legacy 执行账本存在；学生内容模块用 `source_object_ref.object_id` 做物理源对象账本 | 模板侧不再作为 source closure 或 materialization 入口；执行层只从 source entry span 展开到 backend-private raw ref/locator/fingerprint，并在写入前 fail closed | 不能给 runtime 产品 Agent 看或让 Agent 输出；只能在内部账本、trace、测试和机器合同中出现 |
| `source_object_id` / `source_object_ids` / `source_object_ref` | Student Content Model、Tool 执行、final fill、legacy | 用户内容模块的学生源 DOC 物理对象账本；`source_object_ids` 记录内容项覆盖的源对象，`transport_source_object_id` 选择可搬运对象 | 需要行为迁移到 `source_entry_id` / `source_entry_ids` / `source_entry_ref`；不能只字符串改名，因为 transport 和 projection 需要重新绑定 provenance | 用户内容提取 Agent 当前不应看到；final fill 和 eval 可作为 legacy 机器账本读取 |
| `covered_object_ids` | Harness 内部、Tool 执行、Agent 输出 denylist、legacy | 模板 reading block、inventory、semantic review 和 materialization context 的 legacy coverage 集合；canonical inventory 存在时，Harness gate 已改用 source entry span 判 missing/overlap/unknown | 不再作为模板 source closure 主入口；保留为兼容执行账本和旧测试辅助 | 不能让 Agent 输出；反馈应优先改写成 source entry 或 reading view 语言 |
| `object_text_spans` | Harness 内部、Tool 执行、legacy | reading packet text 到 raw object 的字符映射；当前仅用于 legacy scope 展开和内部 provenance 映射 | 不再作为 Agent span 文本基准；source-entry gate 以 canonical entry text 和 source-entry span 为准 | 不能给 Agent 看；只用于 Harness/Tool/App mapping |
| `reading_block_id` / `block_id` | Agent 输入、Agent 输出兼容、Harness 内部、Tool 执行、Fill Contract/Eval legacy | unit reading packet 的可读 view token；Agent 新合同优先在 `semantic_judgments[].source_entry_id` 引用 source entry，只有 view 范围无法用单个 entry 表达时才兼容 `scope.reading_block_id` | 已降级为 source-entry 派生 view token；不得继续作为主定位 ID | 可给模板 Agent 作为过渡 view token；不能作为主源定位 ID |
| `reading_range_id` / `range_id` | Agent 输入、Agent 输出兼容、Harness 内部、Tool 执行、Fill Contract/Eval legacy | unit reading packet 的范围 token，包括 whole-unit range；仅在分页、合并或窗口展示需要时作为 legacy scope | 已降级为 view/range projection；新增主合同不使用它生成 source closure | 可给模板 Agent 作为过渡 view token；不能作为主源定位 ID |
| `span_ref` | Harness 内部、Tool 执行、Fill Contract、Eval、Agent 输出 denylist | Harness 从 accepted ordered part 解析出的 source span ref；新 source-entry judgment 生成 `source_entry_id=<id>;part_index=<n>`，legacy scope 仅兼容生成旧 ref | 生成、closure 和 materialization 入口已按 source-entry span 工作；字段名保留为下游机器 ref | 不给 Agent 输出；可出现在 Fill Contract、receipt、trace 和 Eval 中 |
| `slot_ref` | Tool 执行、Fill Contract、Eval、legacy | `span_ref + field_id` 派生的最终 fill interface ref，同时写入 content-control tag | 不需要改名；需要行为迁移，保证 provenance 经 `slot_ref -> span_ref -> source_entry_id + span` 闭合 | 不给 Agent 输出；下游 final fill 可消费，runtime Agent 只通过字段语义判断间接产生 |

归类结论：

- 只是命名收口：`source_content_id` 在新增合同中降级为 legacy/compat；`slot_ref` 保留为 fill interface ref。
- 需要行为迁移：`source_entry_id`、`object_id/object_ref`、`source_object_ids`、`covered_object_ids`、
  `object_text_spans`、`reading_block_id/range_id`、`span_ref`。
- 不能给 runtime 产品 Agent 看的字段：raw `object_id/object_ref`、`source_object_ids/source_object_ref`、
  `covered_object_ids`、`object_text_spans`、`span_ref`、`slot_ref`、`locator`、`fingerprint`、hash。
- 当前给模板 Agent 看的主定位字段：canonical source entry 投影 `source_entry_id`；过渡期仍可能给
  `reading_block_id` / `reading_range_id` 作为 view token。当前仍给用户内容提取 Agent 看的 legacy 字段：
  `source_content_id`。
- 模板 Agent 的主定位字段只能是 canonical source entry 的投影：`source_entry_id` 和基于其
  `text` 的 span/parts，不包含 raw provenance。

## 哪些是源定位 ID

目标源定位 ID：

- `source_entry_id`：唯一 canonical source entry ID。
- 基于 `source_entry_id` 派生的 source span ID/ref：用于指向源组件内的字符范围、结构范围或连续
  entry 范围。

Canonical source entry 的正式模型：

```json
{
  "source_entry_id": "source-entry-xxx",
  "text": "姓名：张三",
  "entry_type": "text",
  "source_order": {"block": 1, "inline": 0},
  "provenance": [
    {
      "object_id": "obj-a",
      "locator": "/body/p[1]/r[1]",
      "text_span": [0, 3]
    }
  ]
}
```

约束：一个 entry 可覆盖一个或多个 raw Word object；`text` 是唯一 Agent span 文本基准；
`provenance` 保留回源执行材料；模型不含 `field_id`。

当前生成顺序已经前移到输入 normalize 层：

```text
raw inspect objects
  -> normalize / canonical source entries
  -> reading packet projection
```

落点：

- `src/docfit/template/source_entries.py` 负责从 accepted unit scope 内的 raw inspect objects 生成
  canonical source entries，并提供 legacy raw-object projection。
- `prepare-template` 的 post-unit inventory 先写入顶层 `source_entries`，再把 canonical
  `source_entry_id` 投影到旧 `objects` / `reading_blocks` 内部账本。
- `docfit_evidence focus=unit_evidence_packet` 也先 normalize，再生成 Agent-visible source-entry packet；
  返回 evidence 主窗口是 `source_entry_id + text` 的 source-entry rows，reading blocks/ranges 只作为
  view context。
- Agent 输出合同、Harness closure gate 和 materialization 入口已切到 source-entry-based：Harness 校验所有
  required source entries 的非空字符被覆盖一次、span 无 missing/overlap/unknown，并且每个 accepted span
  能展开到 source entry provenance；materializer 从 Harness-resolved source-entry spans 展开 raw
  object provenance，并在写入前检查 source DOCX hash、locator 和 object_ref/fingerprint 一致性。当前只
  完成 logic/contract 层验证，不宣称 real replay、E2E agent loop 或产品验收完成。

当前代码里的过渡源定位材料：

- `object_id` / `object_ref` / `locator`：当前 inspect/backend 层定位材料，应被包进
  `source_entry_id` provenance，而不是继续暴露为产品源定位名。
- `covered_object_ids` / `object_text_spans`：当前 reading packet 到 inspect 对象的 mapping，应迁为
  `covered_source_entry_ids` / `source_entry_text_spans`。
- `source_object_id` / `source_object_ref` / `source_object_ids` / `source_locators`：用户内容模块同类
  物理源对象名，应纳入同一迁移。

不是源定位 ID：

- `field_id`、`parent_field_id`、`member_field_id`。
- `reading_block_id`、`range_id`、`span_ref`、`slot_ref`。
- `content_id`；既有 `source_content_id` 只按 legacy/compat 内容项 ID 处理。

## 哪些是内容字段 key

这些字段表达 Registry 内容语义，不表达 DOCX 位置：

- `field_id`
- `parent_field_id`
- `member_field_id` / `member_field_ids`
- `slot_field_id` / `span_field_id` / `part_field_id` / `normalized_field_id`
- `allowed_field_ids` / `field_ids` / `unknown_field_ids` / `retained_field_ids`
- `structure_ref` 当前在 body materialization 中实际承载 `parent_field_id`，命名不准，应迁为
  `structure_field_id` 或 `body_structure_field_id`。

约束：

- Runtime Agent 只能从 `field_id_vocabulary.allowed_field_ids` 选择 `parts[].field_id`。
- 固定标签、人工区、样式说明、清理片段不得写 `field_id`。
- Compiler、materializer、publication、content-control alias/tag 不得自行补造字段 key。

## 哪些是派生 ref

以下 ref 不应该被当成原始源定位 ID：

- `reading_block_id` / `block_id`：source entries 投影成 Agent 可读块后的 token。
- `reading_range_id` / `range_id` / `unit_range_id`：多个 reading blocks 或 whole unit 的工作面范围。
- `span_ref`：Harness 按 accepted ordered part 解析出的语义 span；新合同下由
  `source_entry_id + part_index/span` 生成，legacy reading view scope 仅兼容保留。
- `slot_ref`：从 `span_ref + field_id` 派生的 fill interface ref。
- `style_contract_ref`、`property_profile_ref`、`render_ref`、`evidence_ref`、`intent_ref`、`command_ref`、
  `plan_ref`、`batch_ref` 等：分别属于样式、视觉证据或执行账本。

## 哪些只能留在内部账本

默认只能留在 Harness/Tool/App/trace/checkpoint/publication receipt 中：

- `source_entry_ref`、source entry backend provenance、`object_id`、`object_ref`、`target_ref`、`locator`、
  `object_text_spans`、`covered_source_entry_ids` / legacy `covered_object_ids`。
- `hash`、`source_hash`、`candidate_hash`、`document_sha256`、`template_sha256`。
- `render_ref`、`candidate_render_ref`、`compare_render_ref`、`evidence_ref`。
- `judgment_ref`、`intent_ref`、`plan_ref`、`context_ref`、`command_ref`、`unsupported_ref`、`batch_ref`。
- `session_id`、`tool_use_id`、`agent_id`、`event_id`、`message_id`。
- Word/backend 私有 ID：`para_id`、`run_id`、`num_id`、`relationship_id`、`image_id`、`internal_id`。

下游 Fill Contract 可以保留机器合同字段，如 `slot_ref`、`span_ref`、`locator`、`template_sha256`、
`field_registry_ref` 和 `style_contract_ref`；这些是机器消费者合同，不是 runtime Agent 判断输入。

## 哪些不能给 Agent 看或不能让 Agent 输出

Runtime 产品 Agent 默认可见：

- unit reading packet 的 `unit_id`、`reading_blocks[].block_id`、`reading_blocks[].range_id`、
  `reading_ranges[].range_id`、可见文本、布局线索、样式摘要。
- `source_entries[].source_entry_id`、`source_entries[].text`、entry 类型和 source order。
- `field_id_vocabulary`。
- Harness 已改写成 source entry 或 reading view 语言的反馈。

Runtime 产品 Agent 可以输出：

- `semantic_judgments[].source_entry_id`。
- 过渡兼容：`semantic_judgments[].scope.reading_block_id` 或
  `semantic_judgments[].scope.reading_range_id`，只作为 reading view token，不作为新增主合同。
- `semantic_judgments[].parts[].text`、`parts[].role`。
- 仅当 role 需要 Registry 字段时输出 `parts[].field_id`，且必须来自输入词表。

Runtime 产品 Agent 不应看到或输出：

- `source_entry_ref`、source entry provenance、`object_id`、`object_ref`、`target_ref`、`locator`、`covered_object_ids`、
  `object_text_spans`、`fingerprint`。
- `span_ref`、`slot_ref`、`span_id`、`slot_id`、content-control `tag` / `alias`。
- `hash`、`source_hash`、`candidate_hash`、`render_ref`、`task_root`、`checkpoint_backend`、`stale_ref`。
- 任何让 Agent 维护 coverage、publication、candidate 或 Tool backend 状态的字段。

## 旧字段名 denylist

以下旧字段名进入 Agent-facing schema/prompt/Skill/Tool feedback denylist。若仍出现在源码，只能用于
fail-closed、负向测试、内部账本或历史说明：

- 字段别名/后置查字段：`semantic_field`、`registry_field`、`registry_field_id`、
  `bound_field_id`、`bound_field_ids`、`required_field_ids`、`generated_field_id`、
  `registry_field_no_candidates`、`registry_binding`。
- Agent-authored ID：`judgment_id`、`span_id`、`slot_id`、`intent_id`。
- Agent-authored derived ref：`span_ref`、`slot_ref`、`resolved_span`、`resolved_spans`,
  `resolved_span_refs`、`content_control_tag`、`tag`。
- 旧 coverage 输入：`covered_object_ids`、`covered_object_refs`、`covered_reading_block_ids`,
  `covered_reading_range_ids`、`covered_reading_spans`、`covered_unit_ids`、
  `reading_block_ids`、`reading_range_ids`、`range_ids`、`block_ids`、`unit_coverage_ids`、
  `whole_unit_ids`。
- 内部定位/backend：`object_id`、`object_ids`、`object_ref`、`object_refs`、`source_object_refs`,
  `target_ref`、`target_refs`、`locator`、`object_locator`、`covered_locators`,
  `source_object_locators`、`target_locators`、`fingerprint`。
- 内部 runtime 状态：`hash`、`source_hash`、`candidate_hash`、`render_ref`、`coverage`、`publish`,
  `checkpoint_backend`、`task_root`、`stale_ref`。
- 旧 judgment shape：`judgment`、`semantic_judgment`、`semantic_parts`、`semantic_part_index`,
  `materialization_intent`、`intent_type`、top-level `field_id`、top-level `field_ids`、
  top-level `structure_ref`、top-level `members`、`toc_contract`。

`field_id` 本身不能进入 denylist；只禁止错误位置。合法位置只有输入词表和需要字段的 ordered part。

## 命名保留与迁移判断

不需要改名，只需要明确语义：

- `field_id`：保留为 content field key。
- `field_id_vocabulary` / `allowed_field_ids`：保留为 Agent 正向字段来源。
- `unit_id`：保留为学校功能单元语义 ID。
- `reading_block_id` / `reading_range_id` / `range_id`：保留为 Agent working-scope token，
  但文档和 schema 要写明它们是 source-entry 派生层。
- `slot_ref`：保留为最终 fill interface ref，不能叫 slot locator/source ID。
- `content_id` / 既有 `source_content_id`：`content_id` 保留为 Student Content Model 的内容层 ID；
  `source_content_id` 只保留为 legacy/compat 字段，不进入新增主合同。
- `style_contract_id` / `style_contract_ref`：保留为样式合同 ID/ref。
- `intent_ref` / `command_ref` / `plan_ref` / `context_ref`：保留为内部执行 ref。

需要改名或迁移：

- `object_id` / `object_ref`：模板源 inventory 中迁到 `source_entry_id` / `source_entry_ref`；
  候选 mutation 侧若仍需要对象 ref，改名为 `candidate_entry_id` / `candidate_target_ref` 或保留为
  backend-private `object_ref`，不得作为产品源定位名。
- `covered_object_ids`：迁到 `covered_source_entry_ids`。
- `object_text_spans`：迁到 `source_entry_text_spans`。
- `source_object_id` / `source_object_ref` / `source_object_ids` / `source_locators`：
  用户内容模块迁到 source entry vocabulary，避免模板提取和学生内容两套物理源名。
- `transport_source_object_id`：迁到 `transport_source_entry_id`。
- `span_ref`：短期保留；生成规则从 `reading_block_id/range_id + part_index` 迁到
  `source_entry_id + source span offsets/order`。
- `slot_ref`：短期保留；其 provenance 必须指向 source-entry-based `span_ref`，不能只靠旧
  `reading_block_id/range_id + part_index`。
- `structure_ref`：当前实际是 Registry parent field key，应改为 `structure_field_id` 或
  `body_structure_field_id`。
- `region_id`：若继续作为最终填写接口，迁到 `region_ref` 并要求 source span provenance；否则保持
  Eval/legacy 内部用途。

## 最小后续迁移顺序

1. 在 inspect/source inventory 层新增 `source_entry_id`，保留旧 `object_id` 作为 backend alias，
   但所有新 mapping 写 source entry 名。
2. 把 reading packet 内部 mapping 从 `covered_object_ids` / `object_text_spans` 迁到
   `covered_source_entry_ids` / `source_entry_text_spans`，Agent-visible packet 返回 source-entry rows。
3. Agent 输出合同迁到 `source_entry_id + parts`，legacy `scope.reading_block_id/range_id` 只作兼容。
4. Harness span resolver 生成 source-entry-based `span_ref`，并把旧 `reading_block_id/range_id + part_index`
   只作为兼容期 provenance。
5. Materializer 和 publication 继续消费 `slot_ref`，但 gate 要证明 `slot_ref -> span_ref -> source_entry_id`
   闭合。
6. 用户内容模块把物理源对象命名迁到 source entry vocabulary，保留 `source_content_id/content_id`
   的内容层语义。
6. 更新 Agent-facing denylist：禁止 Agent-authored `source_entry_id`、旧 object/source_object/coverage
   字段和所有旧字段别名；`field_id` 只允许在 ordered part 的合法位置。
