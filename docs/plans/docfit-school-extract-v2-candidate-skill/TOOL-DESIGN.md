# `docfit-school-extract` v2 四个 Tool 详细设计

> 上位合同：`PLAN.md` 第 0 节、`DESIGN.md`。
>
> 当前阶段只有四个 Tool：observe、mutate、compare、build。

## 1. 目标与边界

四个 Tool 是模板领域的可信事实、副作用和发布边界。它们通过 Claude Agent SDK 原生
`@tool` 定义，并由 `create_sdk_mcp_server()` 注册。Tool 只执行其明确合同：

- 不判断“这是不是论文标题”或“说明是否应该删除”；
- 不替 Agent 决定来源优先级、字段映射或视觉正确性；
- 不信任 compiler、Agent disposition 或上一个 Tool 的成功结论；
- 不创建第二 Agent loop、dispatcher、MCP transport 或工作流状态机。

## 2. 公开名称与 annotations

| 逻辑名 | MCP 名称 | readOnly | destructive | idempotent | openWorld |
|---|---|---:|---:|---:|---:|
| `template_observe` | `mcp__docfit__template_observe` | false | false | true | true |
| `template_mutate` | `mcp__docfit__template_mutate` | false | false | false | false |
| `template_compare` | `mcp__docfit__template_compare` | false | false | true | true |
| `template_build` | `mcp__docfit__template_build` | false | false | false | false |

`template_observe`/`template_compare` 的部分 action 只读，但同一个 Tool 的 create action 会写
task-local evidence，且可能调用外部渲染，因此 Tool 级 annotation 必须保守标为
`readOnlyHint: false`、`openWorldHint: true`。annotation 是 SDK 调度提示，不是安全机制；所有
handler 都必须独立执行路径、hash、ref 和发布检查。

## 3. 共享请求合同

### 3.1 Schema

所有请求是 JSON object：

```yaml
schema_version: 1
task_root: /canonical/authorized/task
```

公开 schema 使用 `additionalProperties: false`；枚举、长度、数组上限和互斥分支在 schema 中
表达。handler 仍重验 schema，因为调用不一定来自模型。

### 3.2 路径

- `task_root` 必须存在、为目录，并在应用批准根内；
- 输入只允许 `input/**`、`work/**` 或当前 task evidence store；
- decision/compiler/attempt 写入只允许 `work/**`；
- 最终 build 只允许 `output/template-artifact`；
- canonicalize 后拒绝 `..`、symlink escape、跨设备原子 rename 风险、特殊文件和目标已存在；
- Tool 直接读取的 source/DOCX 在开始和提交前重算 hash。

### 3.3 Opaque refs

```text
snapshot:v1:<opaque>
render:v1:<opaque>
mutation:v1:<opaque>
comparison:v1:<opaque>
```

Agent 只能原样传递。ref manifest 至少绑定 task store version、document SHA-256、producer schema/
implementation version、parent ref、evidence paths/hashes 和创建顺序。缺失、跨任务、跨 hash、
stale 或 manifest 不完整都稳定拒绝。

### 3.4 共享结果 envelope

```yaml
schema_version: 1
call_status: ok | needs_input | error
result_state: observed | mutated | compared | built | blocked | null
checks: []
warnings: []
failure: null
```

`failure`：

```yaml
code: stable_snake_case
message: safe summary
field: optional.input.path
retryable: true | false
```

- 无效请求、stale ref 或缺授权：`needs_input`，SDK `isError: true`；
- 后端/IO/内部失败：`error`，SDK `isError: true`；
- 完整 build 检查发现业务 blocker：`ok/blocked`，SDK transport 成功但不发布；
- 正常事实或已提交副作用：`ok` 加对应 result state。

Tool 同时返回原生 `content` 和 `structuredContent`。图片使用原生 image block；JSON 不内嵌
base64。仓库锁定 SDK 版本需要的首 text compact JSON mirror 集中复用现有 helper，不在四个
handler 中复制协议。

## 4. `template_observe`

### 4.1 目的

从只读 DOCX 建立绑定精确 hash 的不可变事实 snapshot，并提供查询和页面图片读取。它不产生
语义结论。

### 4.2 `create`

请求：

```yaml
schema_version: 1
task_root: ...
action: create
input_docx: input/school-template.docx
visual_level: none | quick | candidate_verification
focus:
  - structure
  - visible_objects
  - styles
  - slot_candidates
```

执行：

1. canonicalize 路径并记录起始 hash；
2. 解析 DOCX package、relationships、stories、sections、paragraph/run、table、textbox、content
   control、bookmark、field、header/footer、分页边界；
3. 解析命名样式、继承、直接格式和最终有效属性；
4. 识别 unsupported features，但不猜测其语义；
5. 按 visual level 调用固定 port：`quick` 使用 OfficeCLI，`candidate_verification` 使用 Adobe；
6. 重查 source hash，原子发布 snapshot/render manifests。

成功至少返回：

```yaml
call_status: ok
result_state: observed
document_sha256: <sha256>
snapshot_ref: snapshot:v1:...
render_ref: render:v1:... | null
page_count: 0 | null
objects: []
styles: []
sections: []
unsupported_features: []
checks: []
warnings: []
```

### 4.3 `query`

```yaml
action: query
snapshot_ref: snapshot:v1:...
query:
  text: 姓名
  match: exact | casefold | regex
  kinds: [paragraph] | [run] | [paragraph, run]  # 省略时默认 paragraph
  include: [context, effective_style, visual_location]
```

返回全部匹配并稳定排序；零匹配仍是成功。重复匹配不能由 Tool 静默选一个。regex 有长度、
复杂度和 timeout 限制。标签与填写区共享段落时应查询 `run`，避免把学校固定标签一起物化；
run match 的 context 同时返回 `paragraph_index` 与 `run_index`。

每个 match 返回 task-local execution locator：

```yaml
object_ref:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
```

该 ref 只用于本次 mutation/evidence，不能直接写入最终 `fill-contract.json`。

### 4.4 `images`

```yaml
action: images
render_ref: render:v1:...
pages: [1, 2]       # 与 cursor 互斥
cursor: null
max_images: 4
```

只读取已有 render，不触发新转换。返回 image metadata、原生 image blocks 和 `next_cursor`。
请求页必须属于该 render 且在预算内。

### 4.5 拒绝与测试

稳定错误至少包括：`task_root_outside_scope`、`input_path_outside_task_root`、
`invalid_docx_package`、`source_changed`、`snapshot_ref_not_found`、`cross_task_ref`、
`invalid_query`、`regex_budget_exceeded`、`render_ref_not_found`、`image_budget_exceeded`。

测试覆盖 source 不变、重复/零匹配、样式继承、多个 story、unsupported object、三种视觉等级、
render cache、图片 cursor 和失败不发布。

## 5. `template_mutate`

### 5.1 目的与请求

只执行 `compile_mutation_plan.py` 产生且通过重验的 canonical plan：

```yaml
schema_version: 1
task_root: ...
mutation_plan_path: work/compiled/mutation-plan-attempt-1.json
output_docx: work/attempts/template-attempt-1.docx
```

不接受 inline operation、overwrite、best-effort 或 provider 参数。

### 5.2 当前 operation

#### `materialize_slot`

在唯一 execution target 上物化 content control：

```yaml
operation: materialize_slot
slot_id: slot.cover.thesis_title
field_id: thesis.title.zh
content_type: text
target_ref: {...}
marker:
  alias: thesis.title.zh
  tag: slot.cover.thesis_title
```

要求：

- `field_id` 存在于 plan 绑定的 Registry；
- `slot_id` 在计划和文档中唯一；
- `w:alias = field_id`、`w:tag = slot_id`；
- 保留外层 paragraph/cell/textbox container 和既有有效样式；
- 不插入可见占位文字，也不清空示例内容。

#### `remove_content`

删除只允许计划中已经编译的 mode：

```text
clear_text_preserve_container
remove_paragraph
remove_table_row
remove_table
remove_bounded_block
remove_shape
```

分阶段实现时只开放当前 tracer 需要的 mode。每个删除 operation 必须带：target ref、预期
fingerprint、责任迁移或精确删除授权、边界、保护不变量和预期后状态。

### 5.3 事务算法

1. 重验 task/path、plan schema/digest、Registry hash、snapshot/document hash；
2. 把 source 复制到同文件系统临时项；
3. 按 plan 顺序重解 target 并验证 fingerprint；
4. 对临时项执行 operation；
5. 重新打开 DOCX，验证 content controls、protected content、relationships、styles、sections、
   headers/footers 和 package 完整性；
6. 建立 after snapshot 与 mutation evidence；
7. source final recheck；
8. fsync 并原子 rename 为新 output。

任何一步失败都删除临时项，不发布 output、after snapshot 或 committed mutation ref。

成功：

```yaml
call_status: ok
result_state: mutated
committed: true
output_docx: work/attempts/template-attempt-1.docx
output_sha256: <sha256>
after_snapshot_ref: snapshot:v1:...
mutation_ref: mutation:v1:...
operation_results: []
```

### 5.4 拒绝与测试

稳定错误至少包括：`invalid_mutation_plan`、`plan_digest_mismatch`、`registry_hash_mismatch`、
`snapshot_hash_mismatch`、`target_not_found`、`target_ambiguous`、`target_fingerprint_mismatch`、
`field_not_registered`、`slot_id_not_unique`、`unsupported_operation`、
`deletion_authority_missing`、`protected_content_changed`、`post_check_failed`、
`output_exists`、`source_changed`。

测试覆盖 alias/tag、无占位文字、重复目标、每个已开放删除 mode、责任迁移、rollback、source
只读、目标不覆盖和 committed evidence。

## 6. `template_compare`

### 6.1 目的

确定性报告结构变化与所需视觉证据。它不替 Agent判断视觉正确性。

### 6.2 `create`

mutation review：

```yaml
action: create
review_mode: mutation_review
before_snapshot_ref: snapshot:v1:...
after_snapshot_ref: snapshot:v1:...
mutation_ref: mutation:v1:...
```

final review：

```yaml
action: create
review_mode: final_review
final_snapshot_ref: snapshot:v1:...
visual_level: candidate_verification
```

final review 不要求 mutation ref，因此零 mutation 模板也可完成。它必须生成或复用精确最终
hash 的全页 `candidate_verification` render。

成功返回：

```yaml
call_status: ok
result_state: compared
comparison_ref: comparison:v1:...
expected_changes: []
unexpected_changes: []
required_images:
  - required_image_id: image-final-page-0001
    kind: final_full_page
    pages: [1]
    image_sha256: <sha256>
machine_blockers: []
next_cursor: null
```

### 6.3 Diff 与图片选择

至少比较 object 增删改、protected fingerprints、有效格式、table grid、content control
alias/tag、field、bookmark、section、header/footer、numbering、分页边界和页数。

| 变化 | Required evidence |
|---|---|
| 文本清空 | before/after crop + after full page |
| container 删除 | target page + adjacent pages |
| bounded block/表格 | before/after contact sheet + boundary pages |
| section/header/footer/page break | 所有受影响 section pages |
| 映射失败或无法限定影响 | 扩大范围，必要时全页 |
| final review | 最终 hash 的每一页 |

预期变化未发生、operation 范围外 protected/grid/section/header/footer 变化、映射失败或缺少最终
页面证据必须形成 machine blocker。

### 6.4 `images`

```yaml
action: images
comparison_ref: comparison:v1:...
required_image_ids: [image-final-page-0001]
cursor: null
max_images: 4
```

只返回 comparison manifest 已声明的 required images，不接受任意页绕过 review coverage。

### 6.5 拒绝与测试

稳定错误至少包括：`comparison_ref_not_found`、`mutation_lineage_mismatch`、
`snapshot_hash_mismatch`、`candidate_verification_unavailable`、`page_mapping_failed`、
`invalid_image_cursor`、`requested_image_not_required`。

测试覆盖 expected/unexpected diff、zero mutation final review、section/table/protected 误伤、全页
覆盖、cursor、旧 hash 图片拒绝，以及 Tool 从不生成 Agent disposition。

## 7. `template_build`

### 7.1 目的与输入

把最终 snapshot 和已编译 artifact spec 重验后，一次原子发布开发期模板产物：

```yaml
schema_version: 1
task_root: ...
final_snapshot_ref: snapshot:v1:...
artifact_spec_path: work/compiled/artifact-spec.json
output_dir: output/template-artifact
```

output 必须不存在。Tool 不接受 inline spec、Agent pass flag、skip check、overwrite 或 quality
status。

### 7.2 四文件集合

```text
template-artifact/
├── clean-template.docx
├── fill-contract.json
├── visual-review.json
└── build-report.json
```

`fill-contract.json` 必须符合 `docfit-template-fill-contract/v1`，并至少包含：

- `template_sha256`；
- Registry ID/version/hash；
- `docfit-content-control-marker/v1`；
- protected/slot/remove regions；
- 每个 slot 的 `slot_id`、`field_id`、type、required、cardinality、artifact locator、
  component/boundary locators 和 expected value style；
- provenance/evidence refs，不含 task root 绝对路径或正文副本。

`visual-review.json` 绑定最终 hash，保存 comparison/ref/image hashes、逐页 coverage 和 Agent
dispositions。`build-report.json` 保存 source/spec/review digest、另外三个 payload 文件的 hashes、
checks、warnings、manual/gap/unresolved/unregistered fields 和 `artifact_status: built`。为避免
自引用，report 不嵌入自己的 hash；Tool 返回值或外部消费者可对完整目录重新计算。

### 7.3 独立检查

1. task root、output、final snapshot、DOCX hash 和 source hashes；
2. artifact spec schema/digest 与内嵌 review digest；
3. Registry ID/version/hash、字段存在性、字段类型/基数兼容；
4. 文档中每个 content control 的 `w:alias`/`w:tag` 与 spec 一致且唯一；
5. 每个 artifact locator 在最终 DOCX 上按 expected count 重解；
6. protected fingerprints、remove residue 和 preserved container；
7. mutation lineage 连续且无未提交 attempt；
8. final comparison 绑定精确最终 hash；
9. `candidate_verification` 全页 coverage、required image dispositions 和无未处理 machine blocker；
10. blocking manual/gap/unresolved/unregistered field；
11. 四个临时文件 schema/hash/重读；
12. fsync 后原子 rename 完整目录。

### 7.4 成功与阻断

成功：

```yaml
call_status: ok
result_state: built
artifact_status: built
published: true
output_path: output/template-artifact
template_sha256: <sha256>
fill_contract_sha256: <sha256>
counts:
  slot: 1
  protected: 1
  remove: 0
  manual: 0
  gap: 0
  unresolved: 0
```

完整检查执行但有 blocker：

```yaml
call_status: ok
result_state: blocked
artifact_status: blocked
published: false
output_path: null
findings: []
```

任何非成功路径都不创建 output；已有 output 永不覆盖。

### 7.5 拒绝与测试

稳定错误至少包括：`invalid_artifact_spec`、`final_snapshot_mismatch`、
`source_hash_mismatch`、`registry_hash_mismatch`、`field_not_registered`、
`marker_protocol_mismatch`、`slot_id_not_unique`、`slot_locator_not_unique`、
`protected_fingerprint_mismatch`、`remove_residue_present`、`incomplete_review_coverage`、
`blocking_finding_present`、`output_exists`、`artifact_incomplete`。

测试必须证明：四文件集合、DOCX 可打开、contract schema、Eval input compatibility、hash
可重算、失败不发布、目标不覆盖和 source final recheck。

## 8. 缓存、性能和隐私

- snapshot cache key 包含 document hash 和 extractor/schema version；
- render cache 额外包含 visual level、provider profile/version 和环境证据；
- 相同 `candidate_verification` key 最多一次外部 Document Transaction；
- comparison JSON 只保存 image refs/hashes，不内嵌 base64；
- query/diff 有资源上限和 regex timeout；图片通过 cursor 分批；
- structured logs 不记录正文、decision body、OOXML、绝对敏感路径或凭据；
- 临时文件与目标位于同一文件系统，异常失败清理未发布临时项。

## 9. 实现落点

```text
src/docfit/template/
├── contracts/          # Registry、semantics、evidence、mutation、review、artifact
├── runtime/            # paths、canonical、atomic、task-local store
├── ports.py            # OfficeCLI/Adobe/filesystem failure boundaries
├── observation.py
├── mutation.py
├── mutation_modes.py
├── comparison.py
└── artifact_build.py

src/docfit/tools/
├── template_schemas/
│   ├── common.py
│   ├── observe.py
│   ├── mutate.py
│   ├── compare.py
│   └── build.py
└── template_tools.py   # 4 个薄 @tool handler
```

领域层不 import `docfit.tools`；Tool handler 不复制领域实现。产品代码不 import tests 或
`evals/template-extraction`。Eval 兼容性通过版本化文件/schema 的独立测试证明。

## 10. Tool / Code Gate

测试位于 `tests/contract/template_gate/`，按 observe、mutate、compare、build、两个 compiler
拆文件，但共同构成一个 Gate。测试直接调用 `SdkMcpTool.handler`，不创建自定义 MCP client/
server harness 重测 SDK transport。

每个已开放 action/mode 至少有：

- 一个成功产物断言；
- 一个代表性拒绝；
- 一个失败不发布断言；
- schema/content/image/structured/error 形态断言；
- 与 source/ref/hash/atomic 边界相关的直接证据。

## 11. 相关文档

- [总体设计](DESIGN.md)
- [实施与验收计划](PLAN.md)
- [两个编译脚本](SCRIPT-DESIGN.md)
- [分阶段 TDD](TDD-IMPLEMENTATION-PLAN.md)
- [模板语义](references/template-semantics.md)
- [删除与槽位决定](references/deletion-and-slot-decisions.md)
- [视觉回归](references/visual-regression.md)
