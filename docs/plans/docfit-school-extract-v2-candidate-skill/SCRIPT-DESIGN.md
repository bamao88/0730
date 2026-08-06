# `docfit-school-extract` v2 两个编译脚本详细设计

> 状态：候选实现合同，尚未加入生产 Skill。
>
> 本文固定两份 Agent 决定文件、两个编译脚本及其 canonical 输出。架构取舍以
> `DESIGN.md` 为准，实施与验收顺序以 `PLAN.md` 为准，五个 Tool 的消费合同见
> `TOOL-DESIGN.md`。
>
> **修改约束：**先检查 `PLAN.md` 第 0 节。本文件只定义两个编译器在 Tool / Code Gate 中
> 可直接断言的输入、输出、拒绝与原子性，不增加独立测试层或当前 Eval 责任。两个脚本的
> CLI 入口、接收对象、编译能力、成功产物、关键拒绝和非职责以 `DESIGN.md` 第 1.1 节为准，
> 本文件不得增加 mode，也不得把它们变成公开 Tool、语义决策者或工作流节点。

## 1. 设计目标

两个脚本分别保护两个真实副作用边界：

```text
修改 DOCX 前
mutation-decisions.yaml
  └─ compile_mutation_plan.py
       └─ mutation-plan.json
            └─ template_mutate

生成 candidate 前
artifact-decisions.yaml
  └─ compile_artifact_spec.py
       ├─ 内部构造并验证 ReviewRecordV1
       └─ artifact-spec.json
            └─ template_build
```

脚本是确定性“决定编译器”，不是工作流引擎，也不是文档事实提取器：

- Agent 对语义、责任迁移、冲突和视觉结果作决定；
- Tool 建立事实、执行副作用并保存不可变证据；
- 脚本把 Agent 决定与 Tool 证据编译成 Tool 可重验的 typed input；
- 脚本不读取或修改 DOCX，不渲染图片，不替 Agent 接受视觉结果；
- 脚本成功不代表 mutation、build 或 freeze 一定成功。

不增加 `compile_review_record.py`。视觉审查没有独立副作用边界，规范化的
`ReviewRecordV1` 直接嵌入 `artifact-spec.json`。

## 2. 共享 CLI 与进程合同

两个薄入口随生产 Skill 发布，并从产品包导入版本化 schema 和编译逻辑：

```text
uv run python <skill-root>/scripts/compile_mutation_plan.py \
  --task-root <task-root> \
  --input work/decisions/mutation-decisions.yaml \
  --output work/compiled/mutation-plan.json

uv run python <skill-root>/scripts/compile_artifact_spec.py \
  --task-root <task-root> \
  --input work/decisions/artifact-decisions.yaml \
  --output work/compiled/artifact-spec.json
```

v1 不提供 mode、provider、backend、overwrite、best-effort 或跳过验证参数。`--help` 和
`--version` 是唯一不要求三个路径参数的调用。

### 2.1 参数

| 参数 | 约束 |
|---|---|
| `--task-root` | 必须存在且是目录；解析 symlink 后为本次任务根 |
| `--input` | `.yaml`、`.yml` 或 `.json`；必须位于 task root 的 `work/` 内 |
| `--output` | 必须位于 task root 的 `work/` 内；扩展名必须是 `.json`；不能等于 input |

相对路径以 `task_root` 为根。绝对路径规范化后也必须在同一根内。输入决定文件可位于
`work/decisions/`，输出固定建议位于 `work/compiled/`。脚本不能写 `input/` 或 `output/`。

### 2.2 退出码和输出流

| 退出码 | 含义 | 输出文件 |
|---:|---|---|
| `0` | 编译成功 | 原子发布完整 canonical JSON |
| `2` | Agent 决定、schema、证据覆盖或引用关系无效 | 不创建、不替换 |
| `1` | 路径、权限、I/O、证据仓库损坏或内部故障 | 不创建、不替换 |

stdout 只写一行不含文档正文的 JSON 摘要：

```json
{"compiler":"compile_mutation_plan","input_sha256":"<sha256>","output_sha256":"<sha256>","schema_version":1,"status":"ok"}
```

stderr 每行一个诊断 JSON object，不输出 traceback、凭据、文档正文或 Agent 决定中的自由文本：

```json
{"code":"missing_migration_target","json_pointer":"/operations/1/migration_targets","message":"surviving responsibility has no earlier materialized target","operation_id":"remove-demo"}
```

同一次失败可返回多个决定错误，但环境/I/O 错误立即退出。诊断顺序按
`json_pointer`、`code`、相关 ID 排序，保证测试稳定。

### 2.3 输入解析

- 文件必须是 UTF-8，顶层必须是 mapping/object，`schema_version` 必须等于 `1`。
- YAML 使用 safe loader；拒绝自定义 tag、merge key、anchor/alias 和重复 mapping key。
- JSON 拒绝重复 key、NaN、Infinity、注释和 trailing comma。
- 单个决定文件上限 2 MiB；集合字段分别设模型级上限，防止意外放大。
- 所有 schema 都拒绝未知字段，不做拼写猜测或静默迁移。
- 自由文本只保存在 canonical 产物需要审计的位置；日志和摘要不回显它。

### 2.4 Canonical JSON

canonical bytes 固定为：

- UTF-8；
- object key 递归按 Unicode code point 排序；
- arrays 保留具有语义的输入顺序，集合型 arrays 在编译器中按稳定 key 排序；
- 分隔符为 `,` 和 `:`，不加缩进或多余空白；
- 非 ASCII 字符不转义；
- 只允许有限 JSON 值，不写 NaN/Infinity；
- 文件末尾不加换行。

canonical 产物不含编译时间、主机名、绝对路径或随机 ID。相同决定 bytes、相同编译器版本
和相同 Tool store manifests 必须产生逐字节相同的输出。

每个输出都包含：

```yaml
schema_version: 1
compiler:
  name: compile_mutation_plan | compile_artifact_spec
  contract_version: 1
  implementation_version: <package-version>
input_sha256: <raw-input-file-sha256>
task_binding:
  task_store_version: 1
  snapshot_ref: snapshot:v1:...
  document_sha256: <sha256>
```

`implementation_version` 来自安装包版本，不能来自当前时间或 git dirty 状态。

### 2.5 原子写

1. 在 output 的同一目录创建权限 `0600` 的唯一临时文件。
2. 写入 canonical bytes，flush 并 `fsync` 文件。
3. 重读临时文件，校验 bytes 和 SHA-256。
4. 如果 output 已存在：先读取；内容完全相同时视为幂等成功，不替换；不同时返回退出码 `2`
   和 `output_exists`。
5. output 不存在时使用同文件系统原子 rename，再 `fsync` 父目录。
6. 任一步失败都清理本次临时文件，不改变既有 output。

修改决定后重新编译时，Agent 必须按 `PLAN.md` 第 3.3 节选择新的未占用 attempt 输出路径；
编译器不提供 overwrite 参数，也不引入 attempt registry。

## 3. 共享类型和引用规则

### 3.1 ID

Agent 提供的 ID 使用 `^[a-z][a-z0-9_-]{0,62}$`：

- decision：`decision_id`；
- responsibility：`responsibility_id`；
- operation：`operation_id`；
- source：`source_id`；
- slot：`slot_id`；
- fixed/manual/gap/style claim：各自类型 ID。

ID 在本类型内唯一。跨类型引用必须明确字段名，不能靠字符串前缀推断类型。

### 3.2 Opaque evidence ref

脚本只接受候选 Tool 合同定义的 opaque ref：

```text
snapshot:v1:<digest>
render:v1:<digest>
mutation:v1:<digest>
comparison:v1:<digest>
```

脚本通过 `<task_root>/work/.docfit/template-v1/` 的只读 manifest resolver 验证 ref，不解析 ref
字符串推导事实。resolver 返回经过 schema 验证的最小 metadata；编译器不直接读取 DOCX 或
图片 bytes。

### 3.3 Object locator

文档目标只接受 Tool 产生的结构化 object ref：

```yaml
snapshot_ref: snapshot:v1:...
object_id: obj-0123456789abcdef01234567
expected_fingerprint: <sha256>
```

page、bbox、裸文本、数组序号或样式名不能作为 mutation/build locator。它们可作为观察或
视觉证据，但不能独立定位副作用目标。

## 4. `mutation-decisions.yaml`

### 4.1 顶层模型

```yaml
schema_version: 1
snapshot_ref: snapshot:v1:...
decisions: []
responsibilities: []
operations: []
```

一份文件只绑定一个当前 snapshot。允许 `operations: []`，用于确认无需修改；这时可编译，
但通常直接进入最终 review，不调用 mutate。

### 4.2 Decision

```yaml
decision_id: clean-demo-title
target_ref:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
observed_roles: [example, placeholder]
resolution: resolved | unresolved
responsibility_refs: [thesis-title]
rationale: 示例标题需要移除，但题名填写责任继续存在。
evidence_refs: [snapshot:v1:..., render:v1:...]
```

`observed_roles` 的允许值固定为 `fixed_content | placeholder | instruction | example | mechanism |
structural_container | unknown`。`resolution` 只表达当前证据是否足以作决定，不表达保留、删除
或建槽；实际副作用只在 operation 的 `action` 中出现。`resolution: unresolved` 只能留作未执行
判断，任何 operation 都不能引用它。每个 operation 必须引用至少一个 resolved decision；
编译输出只保留会影响当前计划的 decisions。

### 4.3 Responsibility

```yaml
responsibility_id: thesis-title
kind: fill
content_kind: scalar
cardinality:
  min: 1
  max: 1
condition: null
handling: automatic
```

字段含义：

| 字段 | 值 |
|---|---|
| `kind` | `fixed | fill | generate` |
| `content_kind` | `scalar | paragraph_stream | composite`；`fixed` 时省略或为 null |
| `cardinality.min` | 非负整数 |
| `cardinality.max` | 大于等于 min 的整数或 `null`（无上限） |
| `condition` | `null` 或人可读、非可执行条件文本 |
| `handling` | `automatic | manual` |

`scalar` 表示一个有界值，`paragraph_stream` 表示有边界的可变段落序列，`composite` 表示
表格、图片、域、目录或其他需保留内部结构/生成机制的对象。`fixed` 的 `content_kind` 省略或
为 null，且通常为 `handling: automatic`；`fill/generate` 必须有完整 content kind 和
cardinality。
输入可省略 `condition`；无上限 cardinality 可省略 `max`。canonical 输出分别规范化为 null。
`repeat`、`conditional`、`manual`、`remove`、`unresolved` 不是
responsibility kind：重复用 cardinality，条件用 condition，处理方式用 handling。

### 4.4 Operation 公共字段

```yaml
operation_id: materialize-title
decision_refs: [clean-demo-title]
action: materialize_slot
target_ref:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
depends_on: []
responsibility_refs: [thesis-title]
expected_text_sha256: <optional-normalized-visible-text-sha256>
```

- operation 顺序就是执行顺序。
- `depends_on` 只能引用数组中更早的 operation，不允许环、未来引用或冗余的传递依赖。
- 所有 `target_ref.snapshot_ref` 必须等于顶层 snapshot。
- `expected_text_sha256` 只作额外 stale guard；不能用正文或裸文本替代 fingerprint。
- 两种 action 的专属字段互斥，未知 action 一律拒绝。

### 4.5 `materialize_slot`

```yaml
slot:
  slot_id: thesis-title
  responsibility_ref: thesis-title
  content_kind: scalar
  cardinality: {min: 1, max: 1}
  condition: null
  handling: automatic
  preserve_container: true
  placeholder_policy: empty
```

约束：

- 只能绑定一个 responsibility，且两者语义完全一致；
- v1 的 `placeholder_policy` 固定为 `empty`；脚本不生成示例占位正文；
- `empty` 表示不插入可见占位文字，不表示该 action 会清空目标；清理现有示例必须另列
  `remove_content`；
- automatic slot 的目标只允许现有段落、表格单元格或有显式起止的段落流边界，必须有
  Tool object locator 和可验证的物理容器；
- manual responsibility 不得伪装成 `materialize_slot`，它进入最终 manual region；
- 同一 `slot_id` 只能 materialize 一次。

### 4.6 `remove_content`

```yaml
removal:
  removal_mode: clear_text_preserve_container
  migration_targets:
    - responsibility_ref: thesis-title
      target_kind: materialized_slot
      slot_id: thesis-title
      object_ref: null
  preserve_invariants: [table_grid, paragraph_anchor, section_boundary]
  fixed_removal_authorization: null
```

v1 六种 removal mode：

| mode | 允许清理的最小物理范围 |
|---|---|
| `clear_text_preserve_container` | 清空目标可见文字，保留段落/run 容器、属性和锚点 |
| `remove_inline_fragment` | 删除混合内容中的精确片段，保持周边 run、空格、标点和域 |
| `remove_container` | 删除一个已定位且无存续责任的完整容器，保持邻接结构 |
| `remove_bounded_block` | 删除显式起止边界间的连续逻辑块，保持边界外 fingerprints |
| `clear_cell_preserve_grid` | 清空单元格内容，保留 cell、row、grid、merge 和属性 |
| `unwrap_control_preserve_content` | 删除内容控件外壳，保留获准的内部内容、顺序、格式和锚点 |

规则：

- removal mode 必须与 observed object kind 相容；编译器根据 snapshot manifest 校验；
- `preserve_invariants` 必须覆盖该模式的强制保护项，Agent 可以增加但不能取消；
- 每个 `migration_targets[]` 都包含 `responsibility_ref`、`target_kind`、`slot_id` 和
  `object_ref`。`target_kind` 只能是 `materialized_slot | existing_object`；不用的目标字段显式为
  null；
- `materialized_slot` 必须引用更早 `materialize_slot` 创建的 `slot_id`，且 removal 的
  `depends_on` 包含该 operation；`existing_object` 必须引用当前 snapshot 中另一个唯一、未被
  删除的 object ref；
- `operation.responsibility_refs` 是该删除涉及的存续责任全集；其中每一项都必须恰有一个
  语义匹配的 `migration_targets[].responsibility_ref`，不再维护第二份重复列表；
- 如果 fixed 责任被删除，`fixed_removal_authorization` 必须包含当前任务授权证据和明确的
  `replace | migrate | terminate` disposition；仅有 rationale 不算授权；
- unresolved decision、未确认 target 或无法唯一映射的内容不能进入删除 operation。

fixed 删除授权模型：

```yaml
fixed_removal_authorization:
  authority_kind: current_user_instruction | supplied_written_requirement
  authority_sha256: <sha256-of-exact-authorizing-text>
  disposition: replace | migrate | terminate
  replacement_responsibility_ref: null
  rationale: 学校旧版本固定提示已由当前明确要求取代。
```

Agent 负责识别当前任务内真正明确的授权，并记录授权原文的 SHA-256；脚本只验证字段完整、
disposition 与责任迁移一致，不能自行证明自然语言是否构成授权。`template_mutate` 保留该记录
用于审计，并仍按 target/fingerprint/postcondition 限定副作用范围。仅有 rationale、一般清理
目标或长期文档声明不能替代这组授权字段。`replace/migrate` 必须给出新的 responsibility ref，
`terminate` 必须将其设为 null。

## 5. `compile_mutation_plan.py`

### 5.1 编译步骤

1. 解析公共 CLI、规范化路径并读取 input bytes。
2. 按第 2.3 节解析 `mutation-decisions`。
3. 从 Tool store 解析顶层 snapshot、对象 refs 和 evidence refs。
4. 验证 decision、responsibility、operation 的 ID 和引用完整性。
5. 验证 action-specific schema、目标 object kind、fingerprint 和 snapshot 一致性。
6. 建立 operation DAG；验证数组顺序是合法拓扑序。
7. 对每个删除操作做 responsibility survival/migration 分析。
8. 规范化集合字段和审计字段，生成 `MutationPlanV1`。
9. 以独立 schema 重新解析生成对象，再做 canonical 序列化和原子写。

### 5.2 `mutation-plan.json`

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
decisions:
  - decision_id: clean-demo-title
    target_ref: {...}
    resolution: resolved
    responsibility_refs: [thesis-title]
    evidence_refs: [...]
responsibilities:
  - responsibility_id: thesis-title
    kind: fill
    content_kind: scalar
    cardinality: {min: 1, max: 1}
    condition: null
    handling: automatic
operations:
  - operation_id: materialize-title
    action: materialize_slot
    target_ref: {...}
    depends_on: []
    responsibility_refs: [thesis-title]
    slot: {...}
plan_digest: <sha256>
```

`plan_digest` 计算时把该字段视为缺失；即对其余完整 canonical object 求 SHA-256。mutate
重新计算并验证。输出不含 input 文件路径、绝对 task root 或编译时间。

### 5.3 稳定拒绝码

至少固定：

```text
invalid_decisions_schema
unknown_field
duplicate_id
snapshot_ref_not_found
cross_snapshot_ref
object_ref_not_found
stale_object_fingerprint
invalid_locator
unsupported_action
action_field_mismatch
invalid_removal_mode
removal_mode_object_mismatch
dependency_not_found
dependency_cycle
forward_dependency
unresolved_destructive_operation
missing_migration_target
migration_target_not_earlier
responsibility_semantics_mismatch
fixed_removal_not_authorized
output_exists
```

退出码 `2` 的错误优先使用最具体拒绝码；同一节点有 schema 错误时不继续做需要该字段的
语义验证。

## 6. `artifact-decisions.yaml`

### 6.1 顶层模型

```yaml
schema_version: 1
final_snapshot_ref: snapshot:v1:...
sources: []
fixed_regions: []
slots: []
manual_regions: []
gaps: []
unresolved: []
style_claims: []
mutation_evidence_chain: []
final_review: {}
```

这份文件只在最终 snapshot 已确认后编写。顶层所有文档对象、review 和 lineage 最终都必须
收敛到同一 task root 与 final document hash。

### 6.2 Sources

```yaml
source_id: school-template
path: input/school-template.docx
sha256: <sha256>
authority: supplied_school_template | supplied_written_requirement | supplied_official_example
scope: template_structure
```

- path 必须在 task root 内；编译器只校验规范化路径和 hash 格式，不打开 source 文件；
- `sha256` 是 Agent 绑定的来源摘要。若已有对应 snapshot/evidence manifest，编译器验证声明与
  manifest 一致；`template_build` 和 `template_freeze` 再直接重算当前 source hash；
- authority 是来源类型，不是优先级；冲突必须在 style claim 中显式解决；
- source 可指向当前任务获准的 requirement 文件，但不能指向长期 Knowledge 替代当前证据。

### 6.3 Fixed regions

```yaml
fixed_region_id: school-name
responsibility:
  kind: fixed
  content_kind: null
  cardinality: {min: 1, max: 1}
  condition: null
  handling: automatic
locator:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
source_refs: [school-template]
```

fixed region 在 build/freeze 时重算 fingerprint。正文不复制进 spec；manifest 保存的是 locator、
hash 与来源关系。

### 6.4 Slots

```yaml
slot_id: thesis-title
responsibility:
  kind: fill
  content_kind: scalar
  cardinality: {min: 1, max: 1}
  condition: null
  handling: automatic
locator:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
preserved_container:
  kind: paragraph
  fingerprint: <sha256>
source_refs: [school-template]
style_claim_refs: [title-font, title-alignment]
```

automatic slot 必须有唯一可重解 locator、preserved container 与完整责任语义。manual slot 不
进入 `slots`，而进入 `manual_regions`。

### 6.5 Manual regions、gaps 与 unresolved

manual region：

```yaml
manual_region_id: handwritten-signature
responsibility:
  kind: fill
  content_kind: composite
  cardinality: {min: 0, max: 1}
  condition: 仅纸质签署版本需要
  handling: manual
locator: {...}
instructions: 由人工在提交前签署；系统不得自动填充。
source_refs: [school-template]
```

gap：

```yaml
gap_id: defense-date-rule
subject: 答辩日期格式
reason: 当前授权来源未规定格式
impact: 不能自动验证日期显示格式
recommended_action: 向用户或学校要求来源确认
evidence_refs: [snapshot:v1:...]
```

unresolved：

```yaml
unresolved_id: cover-logo-variant
subject: 封面校徽版本
status: non_blocking | blocking
reason: 两个当前来源互相冲突且无优先级依据
evidence_refs: [snapshot:v1:...]
```

blocking unresolved 不能编译 candidate spec。non-blocking unresolved 必须转入 manifest 的显式
限制，不能省略。gap 表示缺证据，unresolved 表示已有证据尚未裁决，两者不能混用。

### 6.6 Style claims 与冲突

每个样式属性一条 claim：

```yaml
style_claim_id: title-font
target_ref: thesis-title
property: font.family
observations:
  - source_ref: school-template
    evidence_refs: [snapshot:v1:...]
    value: 宋体
  - source_ref: written-requirement
    evidence_refs: []
    value: 黑体
evidence_state: conflict
resolution:
  state: resolved
  chosen_value: 黑体
  source_ref: written-requirement
  unresolved_ref: null
  rationale: 当前任务提供的明确文字要求指定黑体。
```

`evidence_state` 固定为 `observed | required | aligned | conflict | unresolved`，保留该属性在
当前证据中的客观状态。`resolution.state` 为 `resolved | unresolved`：resolved 必须选中某一
当前 source/value 并将 `unresolved_ref` 设为 null；unresolved 必须清空 chosen source/value，
引用一个顶层 unresolved 项并给出 rationale。不同值不能标成 aligned，已裁决的冲突仍保持
`evidence_state: conflict`，不能抹去冲突事实。是否 blocking 由所引用 unresolved 项显式记录；
编译器只验证决定完整性与 source 可追溯性，不自行判定哪个值更权威。

### 6.7 Mutation evidence chain

```yaml
mutation_evidence_chain:
  - sequence: 1
    before_snapshot_ref: snapshot:v1:...
    mutation_ref: mutation:v1:...
    after_snapshot_ref: snapshot:v1:...
    comparison_ref: comparison:v1:...
    disposition: accepted | needs_edit
    reason: 目标示例已移除，标题槽位与周边结构保持。
    image_dispositions:
      - required_image_id: image-change-after-page-1
        disposition: accepted | blocking | needs_edit
        reason: 修改后的整页布局正确。
    finding_dispositions:
      - finding_id: finding-...
        disposition: accepted | blocking | needs_edit
        reason: 该 finding 与预期修改一致。
    superseded_by_sequence: null
```

链规则：

- sequence 从 1 连续递增；
- 每个 mutation manifest 的 before/after 必须与记录一致；
- comparison 必须是对应边的 `mutation_review`；
- comparison manifest 中每个 required image 和 finding 必须恰有一个 disposition；
- 边级 disposition 只有在全部逐项 disposition accepted 且没有 machine blocker 时才能 accepted；
- 下一条的 before 必须等于上一条 after；
- `accepted` 的 `superseded_by_sequence` 必须为 null；
- 历史 `needs_edit` 允许保留审计证据，但必须由一个更晚 sequence 明确 supersede；
- superseding 边必须修正同一风险对象，且前序 after 能沿链到达它的 before；
- 最后一条必须 accepted，其 after 等于 final snapshot；
- 零 mutation 时允许空链，但 final snapshot 必须来自 observe 且仍需 final review。

### 6.8 Final review 与 Agent dispositions

```yaml
final_review:
  comparison_ref: comparison:v1:...
  final_snapshot_ref: snapshot:v1:...
  document_sha256: <sha256>
  image_dispositions:
    - required_image_id: image-final-page-0001
      page: 1
      disposition: accepted | blocking | needs_edit
      reason: 页面版式、固定内容和槽位位置正确。
  finding_dispositions:
    - finding_id: finding-...
      disposition: accepted | blocking | needs_edit
      reason: 该提示不影响模板责任。
```

规则：

- comparison 必须是 `final_review` mode、authoritative、绑定 final snapshot 精确 hash；
- Tool manifest 列出的每个 `required_image_id` 必须恰有一个 disposition；Agent 可重复记录 page
  方便审阅，但必须与 manifest 相同；
- 每个 finding 必须恰有一个 disposition；未知 page/finding 也拒绝；
- candidate 编译要求所有 Agent dispositions 为 `accepted`；`blocking`/`needs_edit` 要先修正并
  产生新的 final comparison；
- `machine_blocking: true` 的 finding 即使被 Agent 写为 accepted，仍拒绝编译；只有新
  comparison 中该 blocker 消失才算解决；
- reason 必须非空，但脚本不判断其审美质量。

## 7. 内部 `ReviewRecordV1`

`compile_artifact_spec.py` 从 evidence manifests 和 final review decisions 构造内部 typed model：

```yaml
schema_version: 1
final_snapshot:
  snapshot_ref: snapshot:v1:...
  document_sha256: <sha256>
lineage:
  initial_snapshot_ref: snapshot:v1:...
  final_snapshot_ref: snapshot:v1:...
  edges:
    - mutation_ref: mutation:v1:...
      comparison_ref: comparison:v1:...
      disposition: accepted
      image_dispositions: [...]
      finding_dispositions: [...]
      superseded_by_sequence: null
      evidence_digest: <sha256>
final_comparison:
  comparison_ref: comparison:v1:...
  authoritative: true
  page_count: 160
  required_image_ids: [...]
image_dispositions: [...]
finding_dispositions: [...]
machine_blockers:
  count: 0
  finding_ids: []
review_digest: <sha256>
```

每条 `lineage.edges[]` 同时保存该 mutation comparison 的规范化 image/finding dispositions。
规范化时历史 `needs_edit` 边仍保留，并记录其 superseding edge；candidate 资格只由最终收敛
状态判断。`review_digest` 对不含自身的完整 canonical review record 求 SHA-256。

它不是第三份 Agent 文件，也不单独发布：

- 没有 `review-decisions.yaml`；
- 没有 `review-record.json`；
- 没有第三个脚本；
- 它只作为 `artifact-spec.json.review_record` 存在；
- `template_build` 必须从嵌入对象重算 digest，并生成最终 `visual-review.json`。

## 8. `compile_artifact_spec.py`

### 8.1 编译步骤

1. 解析 CLI、规范化路径和 input bytes。
2. 解析并 schema 校验 `artifact-decisions`。
3. 校验 sources 路径/hash 声明；存在 evidence manifest 时交叉验证，但不打开 source DOCX 或
   图片 bytes。
4. 从 Tool store 解析 final snapshot、mutation、comparison 和 render manifests。
5. 验证 fixed、slot、manual、gap、unresolved 和 style claim 的 ID/引用/责任完整性。
6. 验证 mutation lineage 连续、每条边已审查且最终收敛到 final snapshot。
7. 解析 final comparison 的 required pages/findings，验证逐项 disposition 完整。
8. 拒绝 blocking unresolved、未接受 disposition 和残留 machine blocker。
9. 构造并独立 schema 校验 `ReviewRecordV1`。
10. 构造 `ArtifactSpecV1`，重验、canonical 序列化并原子写。

### 8.2 `artifact-spec.json`

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
sources: [...]
fixed_regions: [...]
slots: [...]
manual_regions: [...]
gaps: [...]
unresolved: [...]
style_claims: [...]
review_record:
  schema_version: 1
  final_snapshot: {...}
  lineage: {...}
  final_comparison: {...}
  image_dispositions: [...]
  finding_dispositions: [...]
  machine_blockers: {count: 0, finding_ids: []}
  review_digest: <sha256>
spec_digest: <sha256>
```

`spec_digest` 对不含自身的完整 canonical spec 求 SHA-256。sources 按 `source_id`，领域对象按
各自 ID，dispositions 按 Tool manifest 的 required 顺序规范化。mutation lineage 保留 sequence
顺序，不能按 ID 重排。

### 8.3 稳定拒绝码

至少固定：

```text
invalid_decisions_schema
source_path_outside_task_root
final_snapshot_ref_not_found
final_snapshot_hash_mismatch
duplicate_id
cross_snapshot_ref
object_ref_not_found
stale_object_fingerprint
incomplete_responsibility
automatic_slot_missing_locator
slot_locator_not_unique
manual_region_marked_automatic
unknown_source_ref
style_conflict_unresolved
blocking_unresolved_present
mutation_ref_not_found
comparison_ref_not_found
mutation_lineage_gap
mutation_lineage_mismatch
unreviewed_mutation_edge
unsuperseded_needs_edit
final_comparison_not_authoritative
final_comparison_hash_mismatch
incomplete_page_coverage
missing_finding_disposition
unknown_disposition_target
nonaccepted_disposition_present
machine_blocking_finding_present
output_exists
```

## 9. Tool 端重验责任

脚本与 Tool 使用同一产品包模型，但不能形成“脚本签过即可执行”的信任捷径：

| 消费者 | 必须独立重验 |
|---|---|
| `template_mutate` | mutation plan schema/digest、snapshot/hash、object fingerprint、DAG、action 与 postcondition |
| `template_build` | artifact spec/review digest、sources、final hash、locators、coverage、machine blockers |
| `template_freeze` | candidate 文件集、独立 DOCX 重读、artifact/visual review 一致性及发布条件 |

脚本不签名，不持有秘密密钥。digest 只用于完整性与可重复性，不构成来源认证。

## 10. 安全、隐私与性能

- 只在授权 task root 内读写；source DOCX 和 Tool evidence bytes 保持只读。
- 决定文件中的 rationale/reason 可能包含敏感描述，不写日志；测试 fixture 使用虚构内容。
- 解析 YAML/JSON、resolver 和 schema 校验都必须有 size/count/depth 上限。
- 不执行 YAML tag、condition 文本、路径中的 shell 内容或任何外部命令。
- 一次编译只读取所引用的 manifests；resolver 按 ref 去重并缓存 schema 验证结果。
- 本阶段不设独立性能门；只保留输入大小上限，且不得以跳过 evidence 校验换取速度。

## 11. 实现落点

候选实施的实际产品包、Skill scripts、测试目录和文件规模边界见
[`TDD-IMPLEMENTATION-PLAN.md`](TDD-IMPLEMENTATION-PLAN.md) 第 2 节。领域类型按 common、
semantics、mutation、review、evidence、artifact spec 和 artifact 生命周期拆分；两个 compiler
保持两个具名 owner 文件，不合并成通用多 mode 编译器。Skill 脚本的逻辑位置始终相对活跃
`<skill-root>/scripts/`。

Skill scripts 只负责参数、调用和输出流；schema/编译逻辑在产品包中，供 Tool 与测试复用。
W1–W5 的 `<skill-root>` 是本候选目录；W6 才原子替换生产
`.claude/skills/docfit-school-extract/`。实现中的文件细分可小步调整并同步本文；只有改变
产品责任、公开边界或生产切换范围才需要重新批准。

编译器 fixture、CLI runner helper 和拒绝输入只放在 `tests/fixtures/` 或 `tests/support/`；
两个产品 compiler 及 Skill CLI 不导入 pytest/test helper，不从 `tests/` 读取默认输入，也不
通过测试专用参数或环境变量改变产品行为。W6 的 Skill 包只携带两份产品脚本及其产品依赖。

## 12. 两个编译器的 Tool / Code Gate

测试直接执行两个公开 CLI；内部函数怎样拆分不构成额外 Gate。

### 12.1 共享输入、输出与拒绝

- YAML/JSON 等价输入得到相同语义输出；
- 重复 key、alias、未知字段、过深/过大输入被拒绝；
- 相同输入和 manifests 逐字节稳定；
- output 同 bytes 幂等成功，不同 bytes 不覆盖；
- 路径越界、symlink 越界、向 `input/`/`output/` 写入被拒绝；
- I/O 失败退出 `1`，决定失败退出 `2`，成功退出 `0`；
- stdout/stderr 不泄露正文、rationale 或凭据。

### 12.2 `compile_mutation_plan.py`

- materialize 后 remove 的合法责任迁移；
- 删除早于 slot、未来依赖、环、重复 ID；
- 当前已经开放的 removal mode 与 object kind 的正反例；未开放的候选 mode 必须稳定拒绝；
- 非删除 action 携带 removal 字段、删除缺 mode；
- unresolved destructive operation；
- fixed 删除无授权/有授权；
- manual responsibility 不得编成 automatic slot；
- 跨 snapshot ref 与 stale fingerprint；
- 零 operation 合法编译。

### 12.3 `compile_artifact_spec.py`

- 零 mutation + 完整 final review；
- 多轮 needs-edit 被后续 accepted 边明确 supersede；
- lineage 缺边、错序、最终 hash 不一致；
- 单批与多批图片 manifest 的完整覆盖；
- 缺 page/finding disposition、未知 disposition target；
- machine blocker 不能被 accepted 静默清除；
- style conflict resolved/unresolved；
- blocking/non-blocking unresolved；
- automatic slot locator、fixed fingerprint、source hash；
- review/spec digest 可重算且无独立 review 文件。

编译器测试分别落在 `tests/contract/template_gate/test_compile_mutation.py` 与
`tests/contract/template_gate/test_compile_artifact.py`，与其他 Tool contract 文件共同构成一个
Tool / Code Gate。fixture 只保存最小有效输入、预期 canonical output/digest 和代表性拒绝
输入。测试不得依赖当前机器时间、文件 inode 或绝对 workspace path，也不要求为每个内部
validator 单独建测试文件。

## 13. 验收门

两个脚本设计视为可实施、可验收，当且仅当：

1. 每个 Agent 字段都有唯一消费方或审计目的，没有“先收着以后再说”的字段；
2. 每个 Tool 所需输入都能从 canonical output 得到，Tool 不必猜 Agent 意图；
3. removal 的责任存续、执行顺序和 fixed 授权可在 mutation 前确定性拒绝；
4. final review 的 lineage、逐页覆盖、findings 和 machine blockers 可在 build 前确定性拒绝；
5. 同输入同证据逐字节稳定，失败不覆盖输出；
6. `ReviewRecordV1` 只内嵌于 artifact spec，没有第三份决定文件或第三个编译阶段；
7. mutate/build/freeze 仍独立重验，脚本未变成副作用执行器。

## 14. 相关文档

- [架构设计](DESIGN.md)
- [实施与验收计划](PLAN.md)
- [五个 Tool 详细设计](TOOL-DESIGN.md)
- [分阶段 TDD 实施计划](TDD-IMPLEMENTATION-PLAN.md)
- [候选 Skill](SKILL.md)
- [决定编译参考](references/decision-compilation.md)
- [删除与槽位决定](references/deletion-and-slot-decisions.md)
- [样式冲突处理](references/style-reconciliation.md)
- [视觉回归](references/visual-regression.md)
