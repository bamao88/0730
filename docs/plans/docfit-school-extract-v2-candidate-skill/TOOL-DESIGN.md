# `docfit-school-extract` v2 五个 Tool 详细设计

> 状态：候选实现合同，尚未实现或注册到生产。
>
> 本文是五个领域 Tool 的实现级 reference。架构取舍以 `DESIGN.md` 为准，实施顺序与验收门
> 以 `PLAN.md` 为准，两份编译器合同见 `SCRIPT-DESIGN.md`。
>
> **修改约束：**先检查 `PLAN.md` 第 0 节。本文件只定义五个公开 Tool 在 Tool / Code Gate
> 中可直接断言的输入、输出、拒绝、源只读与原子发布；Agent 编排和后续质量 Eval 不在本
> 文件扩展成额外测试层。五个 Tool 的公开入口、action/mode、必要输入、底层动作、成功
> 产物、关键拒绝和非职责以 `DESIGN.md` 第 1.1 节为准，本文件不得增加或重新分配这些能力。

## 1. 目标和边界

五个 Tool 组成一条可返工、可审计、失败不发布的模板冻结链：

```text
template_observe ── snapshot/object/render refs ─┐
                                                 │
mutation-plan.json ─→ template_mutate ─→ mutation_ref + after snapshot
                                                 │
                                                 v
                                      template_compare
                                      ├─ mutation comparison
                                      └─ final full-page review
                                                 │
artifact-spec.json ─→ template_build ─→ candidate artifact
                                                 │
                                                 v
                                      template_freeze
                                                 │
                                                 └─ frozen artifact
```

固定职责如下：

| Tool | 唯一职责 | 明确不负责 |
|---|---|---|
| `template_observe` | 建立/查询不可变文档事实和视觉证据 | 判断对象语义或修改意图 |
| `template_mutate` | 原子执行已编译的文档修改 | 选择目标、删除模式或槽位语义 |
| `template_compare` | 对账实际变化并提供原生图片 | 决定视觉结果是否可接受 |
| `template_build` | 从最终 snapshot + artifact spec 生成 candidate | 宣布 frozen 或替 Agent 补决定 |
| `template_freeze` | 独立重读、验证并原子发布 frozen | 信任上游“成功”或修正文档 |

任何两个 Tool 都不合并。观察与修改、修改与对账、对账与判断、构建与冻结分别是独立的
事实、副作用或发布边界。

## 2. 公开名称与注册属性

候选公开名称固定为：

```text
mcp__docfit__template_observe
mcp__docfit__template_mutate
mcp__docfit__template_compare
mcp__docfit__template_build
mcp__docfit__template_freeze
```

逻辑名称分别是去掉 `mcp__docfit__` 前缀后的部分。W6 原子切换前不注册这些名称，也不为旧
`docx_*` Tool 提供别名或兼容参数。

五个 Tool 必须使用 Claude Agent SDK 原生 `@tool` 声明，并在 W6 中加入现有
`src/docfit/tools/__init__.py::build_docfit_server()` 的单个
`create_sdk_mcp_server(name="docfit", ...)`。`template_tools.py` 只保存五个 Tool 定义和薄
handler，不创建第二个 MCP server、transport、dispatcher、registry 或 RPC envelope。

| Tool | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | 说明 |
|---|---:|---:|---:|---:|---|
| observe | false | false | true | true | 写 task-local 证据/cache；`authoritative` 可经固定 Adobe adapter 访问进程外服务，同 hash/profile 复用结果 |
| mutate | false | false | false | false | 只创建新 DOCX，目标已存在时失败 |
| compare | false | false | true | false | 写 immutable comparison/image evidence，相同输入复用；不临时访问外部服务 |
| build | false | false | false | false | 只创建新 candidate 目录，拒绝覆盖 |
| freeze | false | false | false | false | 只创建新 frozen 目录，拒绝覆盖 |

这些 `ToolAnnotations` 是 SDK/MCP 的执行提示，不是安全证明。observe 因同一 Tool 内包含可能
调用固定 Adobe 服务的 `authoritative` action，只能在 Tool 粒度保守标记
`openWorldHint: true`；它仍不接受任意 URL 或 provider/backend/engine 参数。五个 Tool 都会
写 task-local evidence 或产物，因此不能为了 SDK 并行调度错误标记为 read-only，也不为了
action 级注解把轻量产品拆成更多公开 Tool。

结构化文本和原生图片复用应用壳现有的共享传输上限，不在本候选中定义第二套 chars/bytes
常量。图片通过 cursor 分批返回；公开 schema 不暴露传输预算参数，边界测试读取同一组共享
常量，避免文档数值与运行时口径漂移。

## 3. 共享请求合同

### 3.1 Schema 形态

- 顶层必须是 object，并包含 `schema_version: 1`。
- 所有公开输入 schema 使用 `additionalProperties: false`。
- 顶层和嵌套层都不使用 `oneOf`、`anyOf` 或 `allOf`。
- 多 action Tool 使用顶层 `action` 字段；action-specific 必填和互斥关系由 service validator
  执行。
- 所有 SHA-256 都是 64 位小写十六进制字符串。
- 时间使用 UTC RFC 3339，例如 `2026-08-05T11:00:00Z`。

### 3.2 `task_root` 与路径

每次调用必须显式传入 `task_root`。所有相对路径以它为根；绝对路径规范化后也必须位于该根
内。Tool store 固定在：

```text
<task_root>/work/.docfit/template-v1/
├── snapshots/
├── renders/
├── mutations/
└── comparisons/
```

路径规则：

- `input/` 下文件只读；任何 Tool 都不能向其中发布。
- mutate 输出必须位于 task root 内且不等于输入。
- candidate 通常位于 `work/`；frozen 只允许发布到 `output/`。
- 输出文件/目录必须不存在；不支持 `overwrite`。
- symlink 解析后的最终路径也必须仍在 task root 内。
- 请求、报告、错误和日志不得包含凭据或文档正文。

### 3.3 Opaque refs

ref 的可传输形式是带类型前缀的不可解释字符串：

```text
snapshot:v1:<64-hex-digest>
render:v1:<64-hex-digest>
mutation:v1:<64-hex-digest>
comparison:v1:<64-hex-digest>
artifact:v1:<64-hex-digest>
```

digest 来自对应 immutable manifest 的 canonical bytes，不等于文档 hash。Agent 只能保存、
比较和回传 ref，不能解析它推导事实。

文档对象使用结构化 ref：

```yaml
schema_version: 1
snapshot_ref: snapshot:v1:...
object_id: obj-0123456789abcdef01234567
expected_fingerprint: 64-hex-sha256
```

`object_id` 只在其 snapshot 内稳定。任何目标 ref 的 snapshot/hash 不匹配、证据记录缺失或
来自另一 task root 时，调用以 `needs_input` 失败且无副作用。

### 3.4 共享结果 envelope

每个结构化结果都使用：

```yaml
schema_version: 1
call_status: ok | needs_input | error
checks:
  - check_id: request.paths_authorized
    status: pass | fail | skipped
    evidence_refs: []
warnings: []
failure: null
```

失败时 `failure` 为：

```yaml
origin: request | compiler_input | document | provider | internal
code: stable_snake_case_code
retryable: false
message: 不含文档正文的说明
suggested_actions: []
```

领域状态不能塞进 `call_status`：

- observe/mutate/compare 使用 `result_state: observed | mutated | compared`；
- build 使用 `artifact_status: candidate`；
- freeze 使用 `artifact_status: frozen | blocked` 和 `published`。

SDK Tool handler 返回原生 `CallToolResult` 形态：

- `structuredContent`：上述完整 JSON object；
- 第一项 text content：同一 object 的 JSON 序列化；
- image action：在结构化/text 之后附加原生 image content blocks。

`call_status: needs_input | error` 时 Python handler 设置 SDK 的 `is_error: true`（MCP wire 对应
`isError`），让 SDK 将错误交回同一 Agent loop；`call_status: ok` 且
`artifact_status: blocked` 是已完成的领域检查结果，不标 transport error。领域 payload 仍保留
稳定失败码和 `retryable`。不能抛出自定义 transport exception 来终止整个任务，也不能在
handler 内建立通用自动重试。

第一项 text mirror 只是锁定 SDK 0.2.128 in-process bridge 的已知兼容点：当前 bridge 构造
Agent 可见的 `CallToolResult` 时会漏掉 `structuredContent`。实现必须复用现有 `tool_result()`
的同一序列化路径，并让该集中 helper 同时识别旧 `status` 与候选 `call_status`，不能另写第二
套字段或错误协议；SDK 升级后先用 Tool/Agent contract 证明直接可见性，再删除镜像。

### 3.5 Check、warning 与 finding

确定性检查使用 `checks[]`，非阻断提示使用 `warnings[]`，比较/冻结发现使用统一 finding：

```yaml
finding_id: finding-...
code: unexpected_section_change
severity: info | warning | blocking
machine_blocking: true
message: 不含文档正文的摘要
evidence_refs: [comparison:v1:...]
object_refs: []
page_refs: []
suggested_action: rerun_with_narrower_target
```

Agent 不能把 `machine_blocking: true` 改成 false。它只能修正决定/文档并产生新的证据链。

## 4. `template_observe`

### 4.1 目的

建立一个绑定精确 DOCX hash 的不可变事实快照，或查询已有快照/图片。它返回全部候选事实，
不判断哪个对象是论文标题、说明、示例或槽位。

### 4.2 输入

Tool 支持三个 action。

#### `action: create`

```yaml
schema_version: 1
action: create
task_root: /authorized/task
input_docx: input/school-template.docx
visual_level: none | quick | authoritative
focus:
  - structure
  - visible_objects
  - styles
  - slot_candidates
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `input_docx` | string path | 是 | 存在、`.docx`、位于 task root |
| `visual_level` | enum | 是 | 必须显式选择，避免意外外部 transaction |
| `focus` | unique string[] | 否 | 省略时使用四项全集，空数组非法 |

视觉等级：

- `none`：只建立结构事实，不能计入 freeze 视觉覆盖。
- `quick`：固定编辑反馈路由，只用于返工定位。
- `authoritative`：固定交付渲染路由，可计入最终审查。

#### `action: query`

```yaml
schema_version: 1
action: query
task_root: /authorized/task
snapshot_ref: snapshot:v1:...
query:
  text: 标题
  match: exact | casefold | regex
  include: [surrounding_context, style_resolution, visual_location]
```

`query.text` 必须非空；regex 使用受限、带超时的实现。结果返回全部匹配，不支持
`first_match`。

query 成功输出全部匹配及其稳定对象身份；匹配文字与上下文只保留在授权 task-local snapshot
事实和 Tool 结果中，不写结构化日志：

```yaml
schema_version: 1
call_status: ok
result_state: observed
snapshot_ref: snapshot:v1:...
matches:
  - object_ref:
      snapshot_ref: snapshot:v1:...
      object_id: obj-...
      expected_fingerprint: 64-hex
    matched_text: 标题
    surrounding_context: ...
    effective_style: {...}
    visual_location: {pages: [1]}
match_count: 1
checks: []
warnings: []
failure: null
```

`include` 未请求的字段显式省略；`matches` 按文档对象顺序稳定排序。`match_count: 0` 仍是
`call_status: ok`，不能把“没有事实匹配”伪装成 Tool 错误。

#### `action: images`

```yaml
schema_version: 1
action: images
task_root: /authorized/task
render_ref: render:v1:...
pages: [1, 2]
cursor: null
max_images: 8
```

`pages` 与非空 `cursor` 互斥。二者都省略时从第一页开始；`max_images` 默认 8，范围 1–16。

### 4.3 Create 输出

```yaml
schema_version: 1
call_status: ok
result_state: observed
snapshot_ref: snapshot:v1:...
document_sha256: 64-hex
source:
  path: input/school-template.docx
  sha256: 64-hex
objects: []
styles: []
sections: []
unsupported_features: []
render:
  level: authoritative
  render_ref: render:v1:...
  page_count: 12
  cache_hit: true
checks: []
warnings: []
failure: null
```

`objects[]` 至少覆盖段落、run、表格/行/单元格、文本框、内容控件、书签、域、页眉页脚、
分节和分页边界。样式事实必须区分 named style、继承、直接格式与最终有效值。

`unsupported_features[]` 每项至少包含稳定 code、受影响 object/scope 和
`machine_blocking: true | false`。blocking 项表示当前 Tool 无法安全定位、修改或冻结对应
范围，后续 mutate/build/freeze 必须拒绝；非 blocking 项必须由 Agent 显式归入 manual、gap
或 unresolved，并由 build/freeze 检查其没有静默消失。这里是能力边界，不是语义质量评分。

`action: images` 的结构化输出先列出本批图片 metadata，再按相同顺序附加原生 image content
blocks：

```yaml
schema_version: 1
call_status: ok
result_state: observed
render_ref: render:v1:...
images:
  - page: 1
    mime_type: image/png
    image_sha256: 64-hex
next_cursor: opaque-cursor-or-null
checks: []
warnings: []
failure: null
```

Agent 以 metadata 顺序把 image block 对应到页面；image block bytes 的 hash 必须等于
`image_sha256`。

### 4.4 执行算法

1. 规范化 task/input 路径并计算 source hash。
2. 检查以 `(document_sha256, inspector_version, visual_level, render_profile_version)` 为 key 的
   immutable cache。
3. cache miss 时只读检查 DOCX package，并建立结构/object/style manifests。
4. 根据 visual level 选择固定 render route；authoritative cache miss 才产生一次外部转换。
5. 建立 object-to-page 映射和图片 manifests。
6. 再次计算 source hash；若变化则丢弃临时证据并失败。
7. 原子发布 snapshot/render manifests，返回 ref。

### 4.5 失败与验收

稳定错误码至少包括：`path_not_authorized`、`unsupported_document_type`、
`invalid_docx_package`、`source_changed_during_observation`、`render_unavailable`、
`provider_timeout`、`snapshot_not_found`、`invalid_query`、`image_batch_too_large`。

必须测试：同 hash cache、来源中途变化不发布、重复“标题”返回全部候选、跨 task ref 拒绝、
none/quick 不满足 authoritative 覆盖、cursor 无重复无缺页、日志不含正文。

## 5. `template_mutate`

### 5.1 目的

在临时副本上按顺序执行已编译 mutation plan，完成全部前置和后置检查后才发布新 DOCX。
它不读取自然语言决定，也不接受 inline operations。

### 5.2 输入

```yaml
schema_version: 1
task_root: /authorized/task
input_docx: work/template-v1.docx
output_docx: work/template-v2.docx
mutation_plan_path: work/compiled/mutation-plan.json
```

三个路径均必须位于 task root。`input_docx` 必须存在；`output_docx` 必须不存在且不能位于
`input/`；plan 必须是 `compile_mutation_plan.py` 的 canonical v1 输出。

### 5.3 成功输出

```yaml
schema_version: 1
call_status: ok
result_state: mutated
committed: true
before_snapshot_ref: snapshot:v1:...
after_snapshot_ref: snapshot:v1:...
mutation_ref: mutation:v1:...
input_sha256: 64-hex
output_sha256: 64-hex
operation_results:
  - operation_id: slot-title
    status: applied
    before_object_ref: {...}
    after_object_refs: [{...}]
checks: []
warnings: []
failure: null
```

### 5.4 执行算法与原子性

1. 验证路径和 compiled plan schema/version/digest。
2. 验证 input hash 等于 plan 绑定的 snapshot hash，并重新解析每个 target ref/fingerprint。
3. 在 output 同级临时目录创建输入副本；不修改 input。
4. 按 operations 数组顺序执行；`depends_on` 必须指向已成功操作。
5. 每步只允许 `materialize_slot` 或 `remove_content`，并记录实际 object diff。
6. 重开临时 DOCX，验证 package、目标结果、protected containers、固定内容、表格网格、分节、
   页眉页脚和未授权邻近对象。
7. 建立 after snapshot 和 mutation manifest。
8. 所有检查通过后 `fsync` 并原子 rename 为 output；否则删除临时副本。

单个 operation 失败会回滚整次调用。不存在“前两项成功、第三项失败但仍发布”的结果。

### 5.5 后置保护

不同 action 至少验证：

- `materialize_slot`：目标只能是段落、表格单元格或有显式起止的段落流边界；写入不可见且
  按 `slot_id` 唯一的 anchor，重开后仍可重解；容器、样式、边界和当前可见内容保持，责任
  refs 完整。该 action 不插入占位文字，也不代替 `remove_content` 清理示例。
- `clear_text_preserve_container`：容器、属性、anchors、邻近内容保持。
- `remove_inline_fragment`：周边 run、空格、标点、域和顺序保持。
- `remove_container`：邻接结构、编号、分页和分节边界符合 protected invariants。
- `remove_bounded_block`：两个边界仍匹配，范围外 object fingerprints 不变。
- `clear_cell_preserve_grid`：grid、merge、row height、cell properties 与相邻单元格保持。
- `unwrap_control_preserve_content`：内部内容、顺序、格式和 anchors 保持。

### 5.6 失败与验收

稳定错误码至少包括：`invalid_mutation_plan`、`input_hash_mismatch`、`stale_object_ref`、
`ambiguous_target`、`output_exists`、`operation_dependency_failed`、`operation_failed`、
`postcondition_failed`、`protected_content_changed`、`invalid_output_docx`。

所有失败结果都必须包含 `committed: false`，且 output 不存在。测试必须覆盖两类 action、
当前已经开放的 removal mode、顺序/依赖、stale ref、后置误伤、目标已存在和多操作中途失败；
未开放的候选 mode 必须稳定拒绝。

## 6. `template_compare`

### 6.1 目的

建立不可变 comparison，把授权 operation 与实际结构/视觉变化对账，并选择 Agent 必须检查
的原生图片。它输出机器事实，不输出视觉 pass/fail。

### 6.2 输入

#### Mutation review

```yaml
schema_version: 1
action: create
task_root: /authorized/task
review_mode: mutation_review
before_snapshot_ref: snapshot:v1:...
after_snapshot_ref: snapshot:v1:...
mutation_ref: mutation:v1:...
```

三个 ref 必须形成同一 mutation manifest 中的 `before → mutation → after`。

#### Final review

```yaml
schema_version: 1
action: create
task_root: /authorized/task
review_mode: final_review
final_snapshot_ref: snapshot:v1:...
```

final review 不需要虚构 before/mutation。Tool 必须取得或复用 authoritative render，并要求
全部页面进入 required image manifest。

#### Images

```yaml
schema_version: 1
action: images
task_root: /authorized/task
comparison_ref: comparison:v1:...
pages: [1, 2]
cursor: null
max_images: 8
```

分页规则与 observe images 相同。返回的图片必须是 comparison manifest 中记录的原始 bytes，
不得按调用临时重渲染。

### 6.3 成功输出

```yaml
schema_version: 1
call_status: ok
result_state: compared
review_mode: mutation_review
comparison_ref: comparison:v1:...
before_snapshot_ref: snapshot:v1:...
after_snapshot_ref: snapshot:v1:...
mutation_ref: mutation:v1:...
expected_changes: []
unexpected_changes:
  - finding_id: finding-...
    code: unexpected_section_change
    machine_blocking: true
required_images:
  total: 6
  page_coverage: [2, 3]
  items:
    - required_image_id: image-change-after-page-2
      kind: before_crop | after_crop | before_full_page | after_full_page | contact_sheet | final_full_page
      pages: [2]
      image_sha256: 64-hex
  first_cursor: opaque-cursor
checks: []
warnings: []
failure: null
```

final review 额外返回：

```yaml
final_snapshot_ref: snapshot:v1:...
coverage:
  page_count: 160
  required_pages: {start: 1, end: 160}
  authoritative: true
```

`required_image_id` 在一个 comparison manifest 内唯一且稳定。final review 必须为每一页包含
一个 `kind: final_full_page` 的 item；mutation review 根据风险可含 crop、full page 或 contact
sheet。`action: images` 的结构化输出返回本批 `required_image_id`、kind、pages、mime type 和
hash，并按相同顺序附加原生 image content blocks。Agent dispositions 引用
`required_image_id`，不拼接或解析 render ref。

```yaml
schema_version: 1
call_status: ok
result_state: compared
comparison_ref: comparison:v1:...
images:
  - required_image_id: image-final-page-0001
    kind: final_full_page
    pages: [1]
    mime_type: image/png
    image_sha256: 64-hex
next_cursor: opaque-cursor-or-null
checks: []
warnings: []
failure: null
```

### 6.4 Diff 与图片选择

结构 diff 至少比较 object 增删改、固定文字 fingerprints、最终有效格式、表格 grid、内容
控件、字段、书签、分节、页眉页脚、编号、分页边界、页数和 slot anchors。

图片选择固定为：

| 变化 | Required evidence |
|---|---|
| 文本清空 | before/after crop + after full page |
| container 删除 | target page + adjacent pages |
| bounded block/表格 | before/after contact sheet + boundary pages |
| 分节/页眉页脚/分页 | 所有受影响 section pages |
| 页数变化或映射失败 | 扩大范围，必要时全页 |
| final review | 最终 hash 的每一页 |

expected change 没发生、operation 范围外 fixed/grid/section/header/footer 变化、对象映射失败、
缺失 authoritative page 等至少标为 `machine_blocking: true`。

### 6.5 失败与验收

稳定错误码至少包括：`comparison_ref_not_found`、`mutation_lineage_mismatch`、
`snapshot_hash_mismatch`、`authoritative_render_unavailable`、`page_mapping_failed`、
`invalid_image_cursor`、`requested_page_not_required`。

必须测试 expected/unexpected 对账、分节/表格/fixed 误伤、风险图片范围、零 mutation final
review、多批 cursor、不同 hash 图片不能混用，以及 Tool 从不生成 Agent disposition。

## 7. `template_build`

### 7.1 目的

把最终 snapshot 与已编译 artifact spec 转换成完整 candidate 目录。它重新验证 spec，但只能
产生 `candidate`，不能发布 frozen。

### 7.2 输入

```yaml
schema_version: 1
task_root: /authorized/task
final_snapshot_ref: snapshot:v1:...
artifact_spec_path: work/compiled/artifact-spec.json
candidate_output_dir: work/candidate-template-artifact
```

spec 的 `final_snapshot_ref`、template hash、source hashes 和 embedded `ReviewRecordV1` 必须
与显式输入及 Tool store 一致。candidate 目标必须不存在。

### 7.3 Candidate 文件集

```text
candidate-template-artifact/
├── clean-template.docx
├── template-artifact.json
├── visual-review.json
└── build-report.json
```

- `clean-template.docx`：final snapshot 对应 DOCX 的字节副本。
- `template-artifact.json`：`artifact_status: candidate` 的规范 manifest。
- `visual-review.json`：由 embedded review record 确定性生成的页级 dispositions/evidence hashes。
- `build-report.json`：输入 hashes、compiler/spec digest、checks、warnings 和文件 hashes。

### 7.4 执行算法

1. 验证路径、final snapshot 和 artifact spec schema/digest。
2. 重新解析 sources、fixed regions、slots、manual/gaps、style claims 和 review record。
3. 验证完整 mutation lineage、所有 ref 同 task/final hash、无未处理 machine blocker。
4. 在最终 DOCX 上重解每个 automatic slot locator，验证唯一性、内容 kind、cardinality、
   condition、handling 和 preserved container。
5. 重算 fixed fingerprints 和 source hashes。
6. 在相邻临时目录写四个文件，重读并计算文件 hashes。
7. 全部通过后原子 rename 为 candidate 目标。

### 7.5 失败与验收

稳定错误码至少包括：`invalid_artifact_spec`、`final_snapshot_mismatch`、
`source_hash_mismatch`、`duplicate_slot_id`、`slot_locator_not_unique`、
`fixed_fingerprint_mismatch`、`incomplete_review_coverage`、`blocking_finding_present`、
`candidate_output_exists`、`candidate_incomplete`。

失败时 candidate 目录不存在。测试必须证明 build 不产生 freeze report、不返回 frozen、不会
静默降级 automatic slot，并能从 embedded review record 重建稳定 `visual-review.json`。

## 8. `template_freeze`

### 8.1 目的

在不信任 build 成功结论的前提下，独立重读 candidate、来源和证据，生成新的 frozen 目录。
它是唯一允许返回 `artifact_status: frozen` 的 Tool。

### 8.2 输入

```yaml
schema_version: 1
task_root: /authorized/task
candidate_dir: work/candidate-template-artifact
frozen_output_dir: output/frozen-template-artifact
```

candidate 必须完整存在；frozen 目标必须不存在。freeze 不接受“skip checks”、inline manifest、
Agent pass flag 或旧 snapshot ref。

### 8.3 独立检查

至少执行：

1. candidate 目录只有并完整包含四个规定文件；
2. DOCX package 可独立打开；
3. candidate manifest/template/source hashes 可重算且一致；
4. 所有 source 当前 hash 未变化；
5. automatic slot 在 DOCX 上唯一重解，语义和基数有效；
6. fixed fingerprints 一致；
7. manual/gap/unresolved 显式；
8. embedded review 与 `visual-review.json` 一致；
9. final authoritative review 覆盖精确最终 hash 的全部页面；
10. mutation lineage 连续且没有未处理 machine blocker；
11. build report/file hashes 完整；
12. frozen 临时目录写入、重读和 hash 校验成功。

### 8.4 Frozen 文件集与 artifact ref

```text
frozen-template-artifact/
├── clean-template.docx
├── template-artifact.json        # artifact_status: frozen
├── visual-review.json
├── build-report.json
└── freeze-report.json
```

DOCX、visual review 和 build report 与 candidate 对应文件逐字节一致。freeze 只重建 manifest
的生命周期字段并新增 report。final manifest 记录 `freeze_report: freeze-report.json`，不包含
`artifact_ref`，避免自引用。

`build-report.json` 中的文件 hash 只证明 candidate 构建时的四文件集合。freeze 先在 candidate
状态下用它完成校验；把 manifest 从 candidate 重建为 frozen 后，由 `freeze-report.json`
单独记录 candidate manifest hash 与 frozen manifest hash。不得用 build report 中的旧 manifest
hash 验证 frozen manifest。

`artifact_ref` preimage 是 canonical object：

```yaml
schema_version: 1
payload_files:
  build-report.json: 64-hex
  clean-template.docx: 64-hex
  template-artifact.json: 64-hex
  visual-review.json: 64-hex
freeze_report_payload_sha256: 64-hex
```

最后一项通过暂时省略 freeze report 的 `artifact_ref` 字段后计算。再对整个 canonical object
计算 SHA-256，形成 `artifact:v1:<digest>`。验证者使用相同省略规则复算。

### 8.5 成功与阻断输出

成功：

```yaml
schema_version: 1
call_status: ok
artifact_status: frozen
published: true
artifact_ref: artifact:v1:...
template_sha256: 64-hex
frozen_dir: output/frozen-template-artifact
checks: []
warnings: []
failure: null
```

机器检查完整执行但不通过：

```yaml
schema_version: 1
call_status: ok
artifact_status: blocked
published: false
findings: []
checks: []
warnings: []
failure: null
```

请求/schema/provider/internal 错误仍使用 `call_status: needs_input | error`，不能伪装成
artifact blocked。

### 8.6 失败与验收

blocking finding codes 至少包括：`candidate_file_missing`、`candidate_file_hash_mismatch`、
`invalid_docx_package`、`source_changed`、`slot_not_unique`、`fixed_content_changed`、
`manual_or_gap_implicit`、`review_hash_mismatch`、`review_page_missing`、
`blocking_finding_present`、`stale_snapshot_reference`、`artifact_ref_mismatch`。

任何 blocked/error 路径都不得创建 frozen 目标；candidate 保留供诊断。成功路径必须证明
五文件集合、manifest 状态、artifact ref 复算、目标不覆盖和 source final recheck。

## 9. 跨 Tool 缓存、性能和隐私

- snapshot cache key 包含文档 hash 和 extractor/schema 版本；render cache 额外包含 intent 与
  provider profile/version。
- authoritative cache hit 不重复外部 Document Transaction；cache miss 每个 key 最多一次。
- comparison 只保存 image refs/hashes，不把 base64 写入结构化 JSON。
- query/diff 必须有资源上限和 regex timeout；长文档通过分页/cursor，不一次展开全部对象图片。
- structured logs 只记录 refs、hashes、counts、codes、durations 和 cache status；不记录正文、
  YAML decision body、DOCX XML 或凭据。
- 所有临时文件和目录都创建在目标同一文件系统，确保原子 rename；异常退出后由安全清理器
  删除未发布临时项。

## 10. 实现与 Tool / Code Gate 落点

候选实施的实际目录和文件规模边界见
[`TDD-IMPLEMENTATION-PLAN.md`](TDD-IMPLEMENTATION-PLAN.md) 第 2 节。Tool owner 分别落在
`observation.py`、`mutation.py`/`mutation_modes.py`、`comparison.py`、`artifact_build.py` 和
`artifact_freeze.py`；contracts 与 runtime 使用各自子目录，避免单一 models/runtime 文件
膨胀。外部 OfficeCLI/Adobe 依赖通过 `ports.py` 注入，领域服务不得反向导入 Tool 注册层；
未开放的 mutation mode 不提前创建空实现文件。

公开注册/schema 仍放在 `src/docfit/tools/`：五个 schema 按 Tool 责任拆在
`template_schemas/`，`template_tools.py` 只做五个 SDK `@tool` 声明、薄 handler 和对现有结果
helper 的调用；领域实现不得复制进 Tool registration functions。唯一 composition root 仍是
现有 `src/docfit/tools/__init__.py::build_docfit_server()`，W6 只把新的 `DOCFIT_TOOLS` 集合原子
接入，不增加第二个 server。

OfficeCLI/Adobe fake、DOCX fixture builder 和 artifact 断言只放在 `tests/support/template_v1/`；
产品 Tool、schema、ports 和领域服务不得导入它们或读取 `tests/fixtures/`。真实适配器与测试
fake 都实现同一产品 port，但只有真实适配器进入产品 composition 与安装包。

候选 Tool / Code Gate 位于 `tests/contract/template_gate/`，按 observe、mutate、compare、
artifact 和 compilers 拆文件控制规模，但仍是一个 Gate。所有测试通过公开注册边界调用五个
Tool 或真实 compiler CLI，覆盖已实现输入分支、代表性拒绝、失败不发布、DOCX 可打开、文件
集合、cursor、cache、hash/ref binding 和 candidate/frozen 状态转换。内部模块测试可以用于
诊断，但不形成新的产品 Gate，也不能代替公开 Tool 断言。

Tool contract 沿用仓库现有做法，直接调用 `@tool` 产生的 `SdkMcpTool.handler`，断言 input
schema/annotations、原生 content/image/structured/error 形态和磁盘副作用；不启动 Agent，也
不通过自建 MCP client/server harness 重测 SDK transport。

Agent 是否按必要顺序使用这些合同、处理失败并让最终回复与产物一致，由 `PLAN.md` 定义的
Agent Gate 验证；槽位语义、学校要求覆盖和视觉质量由后续独立 Eval 验证。

## 11. 相关文档

- [总体架构](DESIGN.md)
- [实施与验收计划](PLAN.md)
- [两个编译脚本详细设计](SCRIPT-DESIGN.md)
- [分阶段 TDD 实施计划](TDD-IMPLEMENTATION-PLAN.md)
- [内容语义](references/template-semantics.md)
- [删除与槽位决定](references/deletion-and-slot-decisions.md)
- [视觉回归](references/visual-regression.md)
