# `docfit-school-extract` v2 两个编译脚本详细设计

> 上位合同：`PLAN.md` 第 0 节、`DESIGN.md`。
>
> 两个脚本分别保护 mutation 与最终 artifact build 的输入边界。

## 1. 设计目标

```text
mutation-decisions.yaml
  └─ compile_mutation_plan.py
       └─ mutation-plan.json
            └─ template_mutate

artifact-decisions.yaml
  └─ compile_artifact_spec.py
       └─ artifact-spec.json
            └─ template_build
```

脚本提供：严格输入解析、领域完整性预检、opaque ref 解析、Registry/field 校验、canonical JSON、
digest 和失败不覆盖的原子写入。

脚本不提供：DOCX 解析/修改、渲染、视觉判断、自动字段映射、工作流控制或最终产物发布。
compiler success 只表示输入可交给 Tool 重验。

## 2. 共享 CLI 与进程合同

```text
uv run python <skill-root>/scripts/compile_mutation_plan.py \
  --task-root <task-root> \
  --input work/decisions/mutation-decisions-attempt-1.yaml \
  --output work/compiled/mutation-plan-attempt-1.json

uv run python <skill-root>/scripts/compile_artifact_spec.py \
  --task-root <task-root> \
  --input work/decisions/artifact-decisions-attempt-1.yaml \
  --output work/compiled/artifact-spec-attempt-1.json
```

### 2.1 参数与路径

| 参数 | 合同 |
|---|---|
| `--task-root` | 必须存在、为目录、canonicalize 后属于批准任务根 |
| `--input` | `.yaml/.yml/.json`；位于 task root `work/decisions/**` |
| `--output` | `.json`；位于 task root `work/compiled/**`；必须不存在且不等于 input |
| `--help` | 输出无任务数据的 usage，退出 0 |
| `--version` | 输出脚本/contract version，退出 0 |

拒绝 symlink escape、特殊文件、输入输出相同、目标已存在和跨文件系统原子发布风险。不提供
overwrite、mode、best-effort、provider/backend 或 skip-validation。

### 2.2 退出码和流

| 退出码 | 含义 |
|---:|---|
| 0 | canonical 输出已原子发布 |
| 2 | CLI、路径、解析、schema、ref 或领域输入错误 |
| 3 | IO、原子写或内部运行错误 |

stdout 成功只输出：script、contract version、output relative path、output SHA-256、input SHA-256
和关键 document/Registry binding。stderr 失败只输出 code、field path 和安全摘要；不回显 decision
body、文档正文、OOXML 或绝对敏感路径。

### 2.3 严格输入解析

- UTF-8；拒绝 BOM、无效编码和超出大小上限；
- YAML/JSON object 顶层；
- 拒绝 duplicate keys、unknown keys、YAML aliases/tags、自定义类型；
- 拒绝 NaN/Infinity、非字符串 key 和隐式日期；
- 每个数组和字符串有显式上限；
- schema/领域错误使用稳定 field path。

### 2.4 Canonical JSON

- UTF-8、无 BOM；
- object key 递归字典序；领域 set-like 数组按稳定 ID 排序；operation/lineage 数组保留语义顺序；
- 最小必要空白、LF、文件尾一个换行；
- 不写绝对 task root、input path 或编译时间；
- digest 对不含自身字段的完整 canonical object 计算 SHA-256。

### 2.5 原子写

在 output 同目录创建随机临时文件，写入、flush/fsync、重读、hash/schema 校验后使用 no-replace
rename 发布，再 fsync 目录。任何失败删除临时项并保持目标不存在；不提供 attempt registry。

## 3. 共享类型

### 3.1 ID

稳定业务 ID 使用小写字母开头的点/下划线/短横线受限字符串：

- `decision_id`、`operation_id`；
- `source_id`；
- `region_id`、`slot_id`；
- `field_id` 使用 Registry 规则；
- `style_claim_id`、`finding_id`、`manual_id`、`gap_id`、`unresolved_id`。

同一命名空间内唯一；unknown ID/ref 稳定拒绝。

### 3.2 Opaque evidence ref

脚本只通过 `<task_root>/work/.docfit/template-v1/` 的只读 resolver 验证 ref manifest，不解析 ref
字符串。resolver 验证：存在、类型、task store version、document hash、producer version、parent
lineage、payload path/hash 和 manifest 完整性。

### 3.3 两种 locator

execution locator 只服务当前任务：

```yaml
execution_locator:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
```

artifact locator 服务独立消费者并写入 fill contract：

```yaml
artifact_locator:
  type: content_control_tag
  value: slot.cover.thesis_title
  story: document
  part: word/document.xml
  paragraph_index: 0
  left_anchor: 论文题目
  occurrence: 1
  expected_match_count: 1
```

artifact locator 不包含 snapshot ref、绝对路径或临时 object ID，并最终由
`template_sha256` 约束。复合槽使用 `component_locators`；连续区域使用
`start_locator`/`end_locator`。

### 3.4 Registry ref

```yaml
field_registry_ref:
  path: input/content-fields.yaml
  registry_id: docfit.thesis.content_fields
  registry_version: 0.1.0
  sha256: <sha256>
```

脚本读取 Registry 文件，验证 declared hash、schema、开放世界规则、field ID 唯一性和 parent
引用。输出保留 ID/version/hash，不把 Registry 内容复制进 plan/spec。

## 4. `mutation-decisions.yaml`

### 4.1 顶层模型

```yaml
schema_version: 1
snapshot_ref: snapshot:v1:...
document_sha256: <sha256>
field_registry_ref: {...}
sources: []
decisions: []
operations: []
```

snapshot/document/Registry 必须存在且自洽。`sources` 使用第 6.2 节的 source 结构并绑定当前任务
hash；operations 的顺序具有语义，不重新排序。

### 4.2 Decision 与责任

```yaml
decision_id: decision-title-slot
subject: 封面中文题名
responsibility:
  kind: protected | fill | generate
  content_type: text | rich_text | section | image | table | formula | asset
  cardinality: one | many | optional
  required: true
  condition: null
  handling: automatic | manual
source_refs: [school-template]
evidence_refs: [snapshot:v1:...]
rationale: 当前模板和书面要求均把该位置定义为论文题名
```

`rationale` 只保存最小判断摘要，不复制长正文。manual/gap/unresolved 不生成伪 operation，留到
artifact decisions。

### 4.3 `materialize_slot`

```yaml
operation_id: op-title-slot
operation: materialize_slot
decision_ref: decision-title-slot
execution_locator: {...}
slot_id: slot.cover.thesis_title
field_id: thesis.title.zh
content_type: text
required: true
cardinality: one
marker:
  protocol: docfit-content-control-marker/v1
  alias: thesis.title.zh
  tag: slot.cover.thesis_title
preserve_container: true
expected_after:
  content_control_count: 1
  visible_placeholder_text: false
```

编译规则：

- `field_id` 必须存在于绑定 Registry；
- `alias == field_id`、`tag == slot_id`；
- `slot_id` 只能 materialize 一次；
- decision responsibility 必须是 automatic fill；
- 目标 fingerprint 与当前 snapshot manifest 一致；
- operation 不得清空现有示例文字；需要删除时另列 remove operation。

### 4.4 `remove_content`

```yaml
operation_id: op-remove-instruction
operation: remove_content
decision_ref: decision-instruction
execution_locator: {...}
mode: clear_text_preserve_container
migration_targets:
  - responsibility_ref: decision-title-slot
    target_kind: materialized_slot
    slot_id: slot.cover.thesis_title
deletion_authority:
  authority_kind: current_user_instruction | supplied_written_requirement
  authority_sha256: <sha256-of-exact-authorizing-text>
  source_ref: user-confirmation-1
expected_after: {...}
```

`mode` 枚举为 `clear_text_preserve_container`、`remove_paragraph`、`remove_table_row`、
`remove_table`、`remove_bounded_block`、`remove_shape`；只有当前能力 slice 已开放的值可通过编译。

删除必须满足其一：责任已迁移到更早 materialize 的 slot/protected target；或有精确当前任务删除
授权。长期文档或目标描述不能替代 `deletion_authority`。bounded block 必须有明确起止 execution
locator。

## 5. `compile_mutation_plan.py`

编译顺序：

1. 解析 CLI/path/input；
2. schema 校验；
3. 解析 snapshot/document/Registry；
4. 验证 sources、decision/ref 和责任完整性；
5. 按顺序验证 operation、字段、marker、目标和责任迁移；
6. 规范化 set-like 数据，保留 operation 顺序；
7. 构造 canonical plan 与 `plan_digest`；
8. 原子写入。

输出：

```yaml
schema_version: 1
compiler:
  name: compile_mutation_plan
  contract_version: 1
  implementation_version: 0.x.y
input_sha256: <sha256>
task_binding:
  task_store_version: 1
  snapshot_ref: snapshot:v1:...
  document_sha256: <sha256>
field_registry_ref: {...without absolute path...}
sources: []
decisions: []
operations: []
plan_digest: <sha256>
```

稳定拒绝至少包括：`invalid_schema_version`、`duplicate_key`、`unknown_field`、
`snapshot_ref_not_found`、`cross_snapshot_ref`、`document_hash_mismatch`、
`registry_hash_mismatch`、`field_not_registered`、`duplicate_slot_id`、
`marker_identity_mismatch`、`unknown_decision_ref`、`invalid_operation_order`、
`source_ref_not_found`、`deletion_authority_missing`、`migration_target_not_materialized`、
`output_exists`。

## 6. `artifact-decisions.yaml`

### 6.1 顶层模型

```yaml
schema_version: 1
final_snapshot_ref: snapshot:v1:...
template_sha256: <sha256>
field_registry_ref: {...}
marker_protocol: docfit-content-control-marker/v1
sources: []
protected_regions: []
slots: []
remove_regions: []
manual: []
gaps: []
unresolved: []
style_claims: []
mutation_evidence_chain: []
final_review: {}
```

所有文档对象、lineage 和 review 必须收敛到同一 task root 与最终 document hash。

### 6.2 Sources

```yaml
source_id: school-template
path: input/school-template.docx
sha256: <sha256>
authority: supplied_school_template | supplied_written_requirement |
  supplied_official_example | current_user_instruction
scope: template_structure
```

authority 是来源类型，不自动决定优先级。冲突在 style/semantic claim 中显式裁决。build 会直接
重算 source hash。

### 6.3 Protected region

```yaml
region_id: protected.school_name
owner: protected
required: true
execution_locator: {...}
artifact_locator:
  type: text_anchor
  story: document
  part: word/document.xml
  left_anchor: 某某大学
  occurrence: 1
  expected_match_count: 1
expected_fingerprint: <sha256>
source_refs: [school-template]
expected_style: {...}
```

正文不复制进 spec；只保存最小 anchor、fingerprint、style 和来源。

### 6.4 Slot

```yaml
slot_id: slot.cover.thesis_title
owner: slot
field_id: thesis.title.zh
content_type: text
required: true
cardinality: one
execution_locator: {...}
artifact_locator:
  type: content_control_tag
  value: slot.cover.thesis_title
  story: document
  part: word/document.xml
  expected_match_count: 1
marker:
  alias: thesis.title.zh
  tag: slot.cover.thesis_title
expected_value_style: {...}
source_refs: [school-template]
style_claim_refs: [title-font, title-alignment]
```

automatic slot 必须绑定已注册 field、稳定 marker、唯一 artifact locator 和 value style。manual
区域不进入 slots。

`expected_style` / `expected_value_style` 的公开输出固定为 Eval v1 effective-style 结构：顶层只允许
`font`、`paragraph`、`container`、`page`。Agent 决定可以直接使用该结构，也可以使用 observe
事实名（例如 `run.font_ascii`、`run.font_east_asia`、`run.font_size_pt`、`run.bold`、
`paragraph.alignment`、`paragraph.line_rule`、`paragraph.line_value`）；compiler 必须确定性映射为
公开嵌套结构。混合两种结构、未知字段或类型/取值非法时返回 `invalid_effective_style`，不得把
observe 私有字段泄漏到 `fill-contract.json`；builder 独立重验 spec 决定与公开合同一致。

### 6.5 Remove region

```yaml
region_id: remove.cover_instruction
owner: remove
required: true
artifact_locator: {...}
forbidden_text: 请在此填写
source_refs: [written-requirement]
```

remove region 在最终 DOCX 中必须不存在。locator 只用于确定 Eval/审计范围；不能指向仍存在的
forbidden residue。

### 6.6 Manual、gap、unresolved

```yaml
manual:
  - manual_id: manual.signature
    subject: 手写签名
    instructions: 提交前人工签署
    blocking: false
    evidence_refs: []
gaps:
  - gap_id: gap.defense_date_format
    subject: 答辩日期格式
    impact: 不能自动验证显示格式
    blocking: false
    evidence_refs: []
unresolved:
  - unresolved_id: unresolved.logo_variant
    subject: 校徽版本
    blocking: true
    evidence_refs: []
```

它们进入 build report，不扩展现有 fill-contract v1。blocking 项不能编译可发布 spec；非阻断项
必须保留并计数。

### 6.7 Style claims

每个属性保存 observed value、required value、source refs、scope、conflict status 和 resolution。
compiler 只验证来源与裁决完整性，不自行判断哪个值更权威。缺值不能由 Agent 经验补齐。

### 6.8 Mutation evidence chain

```yaml
mutation_evidence_chain:
  - sequence: 1
    mutation_ref: mutation:v1:...
    before_snapshot_ref: snapshot:v1:...
    after_snapshot_ref: snapshot:v1:...
    comparison_ref: comparison:v1:...
```

链必须连续，after hash 等于下一项 before hash，最后到达 final snapshot；零 mutation 使用空链。

### 6.9 Final review

```yaml
final_review:
  final_snapshot_ref: snapshot:v1:...
  comparison_ref: comparison:v1:...
  visual_level: candidate_verification
  page_count: 12
  image_dispositions:
    - required_image_id: image-final-page-0001
      disposition: accepted | rejected
      finding_refs: []
  finding_dispositions: []
```

comparison 必须是 final review、绑定精确最终 hash、覆盖每页，并且 required images 全部有 Agent
disposition。任一 rejected image、未处理 machine blocker 或 blocking finding 阻止编译可发布
spec。

## 7. `compile_artifact_spec.py`

编译顺序：

1. 解析 CLI/path/input；
2. schema 校验；
3. 验证 final snapshot/template hash/Registry/marker；
4. 验证 sources 与 hash 声明；
5. 验证 protected/slot/remove、field、两种 locator 和 style；
6. 验证 manual/gap/unresolved 且没有 blocking 项；
7. 验证 mutation lineage；
8. 从 comparison manifests 与 dispositions 构造 typed `ReviewRecordV1`；
9. 构造 fill-contract model 与 artifact spec；
10. 计算 review/spec digest 并原子写入。

输出：

```yaml
schema_version: 1
compiler:
  name: compile_artifact_spec
  contract_version: 1
  implementation_version: 0.x.y
input_sha256: <sha256>
task_binding:
  task_store_version: 1
  snapshot_ref: snapshot:v1:...
  document_sha256: <sha256>
field_registry_ref: {...}
marker_protocol: docfit-content-control-marker/v1
sources: []
protected_regions: []
slots: []
remove_regions: []
manual: []
gaps: []
unresolved: []
style_claims: []
mutation_lineage: []
review_record: {...}
fill_contract: {...docfit-template-fill-contract/v1...}
spec_digest: <sha256>
```

稳定拒绝至少包括：`source_path_outside_task_root`、`source_hash_declaration_mismatch`、
`final_snapshot_ref_not_found`、`final_document_hash_mismatch`、`registry_hash_mismatch`、
`field_not_registered`、`marker_protocol_mismatch`、`duplicate_slot_id`、
`artifact_locator_invalid`、`artifact_locator_not_persistent`、`style_claim_unresolved`、
`manual_or_gap_implicit`、`blocking_unresolved`、`mutation_lineage_gap`、
`final_comparison_not_candidate_verification`、`review_page_missing`、
`required_image_without_disposition`、`blocking_finding_present`、`output_exists`。

## 8. Tool 端重验责任

| Tool | 不可信输入 | 必须重验 |
|---|---|---|
| `template_mutate` | mutation plan | schema/digest、snapshot/hash、Registry、field/marker、target、授权、post-check |
| `template_build` | artifact spec/review/fill contract | schema/digest、sources、final DOCX、Registry/marker、artifact locator、protected/remove、lineage、review、四文件发布 |

脚本只读 evidence manifest；Tool 在实际副作用边界直接读取 DOCX/source/Registry 并重算事实。

## 9. 安全、隐私与性能

- 决定文件和 canonical 输出继承任务材料敏感级别，不写日志或最终摘要；
- compiler 不访问网络、Adobe、OfficeCLI 或凭据；
- source path 在输出中使用 task-relative path，禁止绝对路径；
- 限制 input bytes、数组项、文本长度、ref 数量和 resolver IO；
- 同一输入相同版本产生稳定输出，便于 cache 和审计；
- 失败不输出部分 plan/spec，不覆盖已有 attempt。

## 10. 实现落点

产品编译逻辑位于：

```text
src/docfit/template/compile_mutation.py
src/docfit/template/compile_artifact.py
src/docfit/template/contracts/**
src/docfit/template/runtime/**
```

Skill 下两个 `.py` 只是薄 CLI，调用产品公开编译入口。安装后的 Skill 脚本必须能找到产品包，
但不得从源码仓库路径动态 import 私有文件。

## 11. Tool / Code Gate

两个 compiler 的测试直接运行真实 CLI，至少覆盖：

- YAML/JSON 正例、duplicate/unknown/alias/tag/非法数字；
- canonical bytes 与 digest 稳定；
- task path、symlink、input/output、target exists、原子失败；
- snapshot/ref/Registry/hash；
- field/marker/two-locator；
- 删除授权和 operation 顺序；
- protected/slot/remove/manual/gap/unresolved；
- zero/multi mutation lineage；
- final page/image/finding dispositions；
- 失败 stderr 无正文，成功 stdout 可机器解析；
- 输出只包含 mutation 或 build 所需字段。

## 12. 相关文档

- [总体设计](DESIGN.md)
- [实施计划](PLAN.md)
- [四个 Tool](TOOL-DESIGN.md)
- [分阶段 TDD](TDD-IMPLEMENTATION-PLAN.md)
- [决定编译方法](references/decision-compilation.md)
