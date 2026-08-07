# `docfit-school-extract` v2 绿地重设计

> 状态：当前候选合同已经收敛到可实施、可验收，尚未实现，也未切换生产。
>
> 用户最新决定：候选目录是本轮设计与后续获批实现的权威；与长期文档不一致时，以本目录
> 为准，并在生产切换阶段一次同步受影响的长期合同。当前研发阶段不建立模板
> `candidate/frozen` 生命周期，也不判断模板是否“定版”。
>
> 实施顺序见 `PLAN.md`，四个 Tool 的实现合同见 `TOOL-DESIGN.md`，两份决定文件和两个
> 编译脚本见 `SCRIPT-DESIGN.md`。

## 1. 产品目标

`docfit-school-extract` 把当前任务中的学校模板、文字要求、官方示例和用户确认整理为一个
可独立消费的开发期模板产物：

```text
template-artifact/
├── clean-template.docx
├── fill-contract.json
├── visual-review.json
└── build-report.json
```

产物回答四个问题：

1. 哪些学校内容必须保留；
2. 哪些内容是说明、示例或应删除内容；
3. 哪些位置是可填写槽位，分别对应哪个 Registry `field_id`；
4. 后续消费者如何在绑定精确模板 hash 的前提下稳定定位并填写这些槽位。

当前阶段的 `built` 只表示产物机械完整、来源与 hash 自洽、槽位可重解、视觉审查记录完整、
并已原子发布。它不表示模板已经 Human accepted、已通过正式学校质量门、已完成 M3，或已经
“定版”。质量结论由现有独立模板 Eval 和后续 Human Gold 负责。

## 2. 当前产品能力

生产能力由四个有类型合同的领域 Tool 和两个确定性 Skill 脚本组成。

### 2.1 四个领域 Tool

| Tool | 责任 | 持久副作用 |
|---|---|---|
| `template_observe` | 建立不可变 DOCX snapshot；查询对象、样式、槽位候选并读取已有页面图片 | 只发布 task-local evidence，不改 DOCX |
| `template_mutate` | 执行已编译 mutation plan；物化 content-control 槽位或删除已授权内容 | 原子发布新 DOCX、after snapshot 和 mutation evidence |
| `template_compare` | 对账预期/意外结构变化；生成或复用快速证据与最终候选验证证据 | 只发布 task-local comparison/image evidence |
| `template_build` | 重验最终语义、Registry/marker/locator、来源、审查和文件完整性并发布模板产物 | 原子发布四文件目录 |

公开 MCP 名称固定为：

```text
mcp__docfit__template_observe
mcp__docfit__template_mutate
mcp__docfit__template_compare
mcp__docfit__template_build
```

这四个 Tool 不是四个彼此独立的叶子操作，而是模板生产流水线上的四个阶段：

```text
看清模板                    按已批准计划修改
template_observe  ────────> template_mutate
       │                           │
       │                           v
       │                    检查是否改对、是否误伤
       └──────────────────> template_compare
                                   │
                                   v
                           重验并发布候选产物
                              template_build
```

只有 `template_mutate` 修改 DOCX；`template_observe` 和 `template_compare` 只生产任务内证据，
`template_build` 只在全部重验通过后发布四文件目录。四个 Tool 共同负责学校模板生产，不负责
提取学生论文内容、执行 Placement 或生成最终论文。

#### 2.1.1 `template_observe`：建立事实快照、查询对象和读取图片

它回答“当前这份学校模板里实际有什么、目标对象在哪里”，只报告事实，不产生“应该保留、
删除或映射到哪个字段”的语义结论。

公开 action 为：

| action | 输入重点 | 能力与输出 |
|---|---|---|
| `create` | 只读 `input_docx`、`visual_level`、`focus` | 解析 DOCX，建立绑定源 hash 的不可变 `snapshot_ref`；按需产生 `render_ref` |
| `query` | `snapshot_ref`、文字、匹配方式、对象 kind | 返回零个或全部稳定排序的匹配及 task-local execution locator，不在重复匹配中静默挑选一个 |
| `images` | 已存在的 `render_ref`、页码或 cursor | 分批返回已有页面图片；不触发新的 Word 转换 |

`create` 可观察结构、可见对象、有效样式和槽位候选，并按 `none`、`quick` 或
`candidate_verification` 决定是否产生页面证据。`query` 支持 `exact`、`casefold`、`regex`，
默认查询 paragraph；标签和填写文字共享一个段落时可以限定 `run`，避免后续把学校固定标签
一起修改。匹配返回的：

```yaml
object_ref:
  snapshot_ref: snapshot:v1:...
  object_id: obj-...
  expected_fingerprint: <sha256>
```

只用于当前任务中的 mutation/evidence，不能直接充当最终 `fill-contract.json` 的持久 locator。
`template_observe` 不修改源 DOCX，不判断视觉是否正确，也不决定字段责任。

#### 2.1.2 `template_mutate`：事务执行已编译的修改计划

它回答“语义决定已经完成后，怎样安全、确定地修改 Word”。Tool 只接受
`compile_mutation_plan.py` 产生并通过重验的 canonical `mutation-plan.json`：

```yaml
schema_version: 1
task_root: ...
mutation_plan_path: work/compiled/mutation-plan-attempt-1.json
output_docx: work/attempts/template-attempt-1.docx
```

它不接受 inline operations、overwrite、best-effort 或 provider 参数。当前实现只开放两种
operation：

- `materialize_slot`：在唯一 execution target 上物化 Word content control；令
  `w:alias = field_id`、`w:tag = slot_id`，保留外层 paragraph/cell/textbox 和有效样式。该操作
  只建立槽位，不负责自动清理原有示例文字。
- `remove_content`：删除已获得责任迁移或精确删除授权的内容。当前只开放
  `clear_text_preserve_container`，即清空目标文字但保留段落、表格单元格或 content control
  容器。`remove_paragraph`、`remove_table_row`、`remove_table`、`remove_bounded_block` 和
  `remove_shape` 只是未来可按真实场景逐项开放的合同名称，不是当前已经实现的能力。

执行时，Tool 在同文件系统的临时副本上按顺序重解 target、核对 fingerprint、执行 operation，
再重新打开 DOCX 验证 package 有效性。它确认源文件未变化后原子发布：

```yaml
output_docx: work/attempts/template-attempt-1.docx
after_snapshot_ref: snapshot:v1:...
mutation_ref: mutation:v1:...
committed: true
```

任何机械执行步骤失败都不发布 output、after snapshot 或 committed mutation ref。Tool 不判断
“该不该修改”，也不检查 protected content、样式或页面语义是否正确；这些判断由 Agent 根据
`template_compare` 的 before/after 差异和实际渲染页面完成。

#### 2.1.3 `template_compare`：对账结构变化并确定必看视觉证据

它回答“修改是否按计划发生、是否误伤其他结构，以及 Agent 必须查看哪些图片”。公开 action
为 `create` 和 `images`；`create` 有两种 review mode：

| review mode | 输入 | 目的 |
|---|---|---|
| `mutation_review` | before/after snapshot 和 `mutation_ref` | 把实际差异与 mutation plan 对账，区分预期变化、意外变化和 machine blocker |
| `final_review` | 最终 snapshot 和 `candidate_verification` | 绑定最终 DOCX hash，生成或复用全页候选验证证据；零 mutation 模板也可执行 |

成功结果至少包含：

```yaml
comparison_ref: comparison:v1:...
expected_changes: []
unexpected_changes: []
required_images: []
machine_blockers: []
```

`images` 只返回 comparison manifest 已声明的 required images，不能用任意页请求绕过 review
coverage。Tool 负责确定性 diff、页面覆盖和 blocker，不接受 Agent 写入的 disposition，也不替
Agent 判断图片是否美观、学校语义是否理解正确。Agent 必须实际读取 required images，再把
自己的视觉结论写入 artifact decisions。

#### 2.1.4 `template_build`：独立重验并原子发布四文件产物

它回答“当前最终模板和全部合同、证据是否已经自洽，可以形成一个完整的开发期候选产物”。
输入只接受最终 snapshot 和 `compile_artifact_spec.py` 产生的 canonical artifact spec：

```yaml
schema_version: 1
task_root: ...
final_snapshot_ref: snapshot:v1:...
artifact_spec_path: work/compiled/artifact-spec.json
output_dir: output/template-artifact
```

Tool 会独立重验最终 DOCX 与来源 hash、Registry、`field_id`、marker、artifact locator、保护内容、
删除残留、mutation lineage、final comparison、全页 required images、Agent dispositions 和
manual/gap/unresolved 阻塞项。它不信任 compiler success、Agent pass flag 或已有摘要，且不允许
覆盖已有 output 目录。

通过后一次原子发布：

```text
template-artifact/
├── clean-template.docx       # 处理后的 Word 模板
├── fill-contract.json        # 下游字段、marker、locator 和填写合同
├── visual-review.json        # 最终视觉证据及 Agent disposition
└── build-report.json         # 来源、hash、检查结果和产物摘要
```

`artifact_status: built` 只表示这四个文件机械完整、互相绑定并已发布；不表示 Human accepted、
学校质量认证、模板定版或 M3 完成。`template_build` 也不填入学生内容或生成最终论文。

#### 2.1.5 两条实际调用路径

需要修改模板时：

```text
template_observe.create/query/images
  -> Agent 编写 mutation-decisions.yaml
  -> compile_mutation_plan.py
  -> template_mutate
  -> template_compare.mutation_review/images
  -> 按需重复修改与比较
  -> template_compare.final_review/images
  -> Agent 编写 artifact-decisions.yaml
  -> compile_artifact_spec.py
  -> template_build
```

原始模板已经干净、不需要修改时：

```text
template_observe.create/query/images
  -> template_compare.final_review/images
  -> Agent 编写 artifact-decisions.yaml
  -> compile_artifact_spec.py
  -> template_build
```

因此四个 Tool 可以简记为：`observe` 看清楚，`mutate` 按计划修改，`compare` 确认没有改错，
`build` 重验并发布。

### 2.2 两个 Skill 脚本

| 脚本 | 输入 | 输出 | 下游 |
|---|---|---|---|
| `compile_mutation_plan.py` | Agent 编写的 `mutation-decisions.yaml` | canonical `mutation-plan.json` | `template_mutate` |
| `compile_artifact_spec.py` | Agent 编写的 `artifact-decisions.yaml` | canonical `artifact-spec.json` | `template_build` |

脚本只做 schema 校验、引用解析、规范化、digest 和原子写入。它们不打开或修改 DOCX，不渲染
页面，不替 Agent 判断语义/视觉，也不发布最终产物。Tool 必须独立重验脚本输出，不能把
compiler success 当作可信事实或发布结论。

### 2.3 能力非目标

当前候选不提供：

- 模板定版、质量认证或 Human acceptance；
- 第二套 Agent loop、MCP transport、Tool dispatcher、权限引擎、会话/attempt registry；
- 旧 `docx_*` Tool 的兼容别名或双 schema；
- 学生内容提取、Placement 或转换端的新 Tool 合同；
- Eval runner、Gold 生产或评分逻辑。

现有模板 Eval 已经实现，不属于本模块源码；本模块只保证产物能作为其 Actual 输入。

## 3. 产品入口与任务目录

独立模板生产的公共入口固定为：

```text
docfit prepare-template \
  --school-template <template.docx> \
  --school-requirements <requirements-file> \
  --field-registry <content-fields.yaml> \
  --output <task-output-directory>
```

当前研发期显式传入 Registry 文件，避免产品运行时隐式依赖仓库 `docs/` 路径。生产切换时，
可以在另行批准的产品打包合同中把已接受 Registry 作为默认资源；在此之前不假定它已进入
产品 wheel。

应用壳负责：

1. 验证输入并创建新的 task root；
2. 把输入作为只读任务材料挂载或复制到 `input/`，记录精确 hash；
3. 使用现有 `ClaudeSDKClient` 启动一个 SDK query/session；
4. 向 Agent 暴露候选 Skill、四个 Tool、允许的基础文件 Tool 和 structured output schema；
5. 把成功产物发布到 `<output>/output/template-artifact/`；
6. 根据机器 structured output 返回稳定退出码和 JSON 摘要。

任务目录逻辑结构为：

```text
<task-root>/
├── input/                         # 只读输入与 hash 绑定材料
├── work/
│   ├── decisions/                 # Agent 决定文件
│   ├── compiled/                  # canonical plans/specs
│   ├── attempts/                  # 新路径写入的 DOCX 尝试
│   └── .docfit/template-v1/       # task-local immutable evidence store
└── output/
    └── template-artifact/         # 唯一成功发布目录
```

所有 Tool 与脚本都接收同一个 canonical `task_root`。输入保持只读；写入目标必须不存在；路径
解析必须拒绝绝对路径越界、`..`、symlink escape、跨任务 ref 和 stale ref。

## 4. Claude Agent SDK 原生运行合同

Agent 运行层固定复用仓库锁定的 `claude-agent-sdk==0.2.128`：

```text
filesystem Skill
  └─ setting_sources=["project"] + skills allowlist
       └─ ClaudeSDKClient 的一个 query/session
            ├─ SDK 原生 agent/tool loop、消息、compaction 与预算终止
            ├─ create_sdk_mcp_server() 注册的四个 @tool
            ├─ permissions / hooks / can_use_tool
            └─ output_format JSON Schema → ResultMessage.structured_output
```

边界固定如下：

- Tool 使用 SDK `@tool` 和 `create_sdk_mcp_server()`；DocFit 不自建 MCP transport 或 Tool loop。
- Tool 返回原生 text/image content、`structuredContent` 和 `isError`；领域状态保存在结构化 payload。
- Tool-level annotation 覆盖该 Tool 的全部 action；observe/compare 会发布 evidence，因此保守使用
  `readOnlyHint: false`。任何 Tool 都不依赖 annotation 实现安全检查。
- Tool 失败返回 Agent loop；Agent 根据稳定失败码修正决定、重新观察或使用新路径。DocFit 不实现
  通用 retry engine，也不自动重放有副作用调用。
- 缺少用户授权或语义裁决时使用 SDK `AskUserQuestion` 与现有 `can_use_tool`；不创建问题文件、
  pause 状态或另一套问答协议。
- 最终机器结果使用 SDK `output_format`。应用和测试读取 `ResultMessage.structured_output`，不从
  自然语言回复反向解析 JSON。
- hooks/permissions 保护 Agent 可调用边界；Tool handler 仍独立重验路径、hash、ref lineage、
  source readonly 和原子发布。

官方依据：

- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)
- [Agent Skills](https://code.claude.com/docs/en/agent-sdk/skills)
- [User input](https://code.claude.com/docs/en/agent-sdk/user-input)
- [Structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)

## 5. 语义、Registry 与填写契约

### 5.1 唯一字段语义来源

`fill-contract.json` 必须绑定：

```yaml
schema_version: docfit-template-fill-contract/v1
template_sha256: <sha256>
field_registry_ref:
  registry_id: docfit.thesis.content_fields
  registry_version: <version>
  sha256: <sha256>
marker_protocol: docfit-content-control-marker/v1
```

Registry 决定 `field_id` 的语义、类型和字段基数；模板决定 `slot_id`、位置、样式和是否必填。
四种身份不得混用：

| 身份 | 作用域 | 含义 |
|---|---|---|
| `field_id` | Registry version/hash | 语义上是什么 |
| `slot_id` / `region_id` | 当前模板 hash | 模板允许写到哪里 |
| execution locator | 当前 task snapshot | 本次 Tool 如何安全执行/取证 |
| artifact locator | 最终模板 hash | 后续独立消费者如何重解目标 |

`field_id` 不是 locator，也不授权自动写入。未注册字段不能伪造 ID：Agent 必须将其归入
manual/gap/unresolved；如果它是本次必须自动填写的槽位，`template_build` 必须阻止发布并返回
稳定 finding。

### 5.2 Marker protocol

自动槽位使用 Word content control：

- `w:alias` 保存 `field_id`；
- `w:tag` 保存稳定 `slot_id`；
- `w:id` 只作为 Word 内部身份，不承担业务语义；
- 槽位标记不插入面向用户的占位文字；需要删除示例文字时使用独立、已授权的
  `remove_content` operation。

`fill-contract.json` 的 slot 形态与现有
`evals/template-extraction/schemas/fill-contract.schema.json` 对齐，至少包含：

```yaml
slot_id: slot.cover.thesis_title
field_id: thesis.title.zh
content_type: text
required: true
cardinality: one
locator:
  type: content_control_tag
  value: slot.cover.thesis_title
  story: document
  part: word/document.xml
  expected_match_count: 1
expected_value_style: {...}
```

复合槽位保存 `component_locators`；连续内容区域使用 `start_locator`/`end_locator`。单一页码、
临时段落序号或任务内 opaque ref 不能独立成为 artifact locator。

### 5.3 Protected、slot 与 remove

填写契约沿用现有 Eval 的三个区域 owner：

- `protected`：学校固定内容、结构或对象，构建时重算 fingerprint；
- `slot`：注册字段的自动填写目标；
- `remove`：已获授权且在交付模板中不得残留的说明/示例内容。

`manual`、`gap`、`unresolved` 不伪装成自动 slot。它们写入 `build-report.json` 的结构化 findings：

- blocking 项阻止发布；
- non-blocking 项随产物交付并计入 structured output counts；
- 现有 Eval 尚未评分的维度不通过扩展 `fill-contract/v1` 偷渡进去。

## 6. 两份决定与受控修改

Agent 在执行副作用前写两份人类可审查决定：

1. `mutation-decisions.yaml`：当前 snapshot、责任、授权、目标和 operation；
2. `artifact-decisions.yaml`：最终 snapshot、Registry、sources、protected/slot/remove、样式、
   manual/gap/unresolved、mutation lineage 和 final review dispositions。

`compile_mutation_plan.py` 输出的计划只能包含当前已支持的 operation：

- `materialize_slot`；
- `remove_content`，并使用获批的删除 mode。

所有删除必须记录内容责任如何迁移或为什么得到明确删除授权。用户最新指令或当前任务中提供
的书面要求可以构成授权；长期文档或目标描述不能替代精确授权记录。

`template_mutate` 对计划执行顺序、snapshot/hash、目标可定位性、操作输入和 DOCX 可打开性做
机械校验。它不以内置检查器裁决受保护内容、样式或页面语义；Agent 必须使用 mutation diff 和
渲染结果自行核对，发现问题后使用新输出路径返工。

## 7. 视觉证据与最终审查

模板领域 Tool 不再拥有 visual level 或图片 action。主 Agent 使用共享的 `docx_render`
建立最终模板 hash 的 V2 LibreOffice 快照，再用 `docx_visual_review` 查看联系表、完整页
和必要对象局部图。Agent 必须实际读取每一页图片，为 evidence refs 和 findings 写结构化
disposition。所有结果标记为 `approximate`；结构检查、渲染事实和 Agent 视觉判断分开保存。

`template_compare` 报告预期变化、意外变化和 required images，不替 Agent 返回视觉
`pass/fail`。若最终图片暴露语义或视觉问题，即使 build 的机械检查可以通过，Agent 也必须返工，
不能发布已知错误产物。

## 8. 一次原子构建

`template_build` 是当前阶段唯一发布入口。输入为最终 snapshot 和已编译 artifact spec：

```yaml
schema_version: 1
task_root: <task-root>
final_snapshot_ref: snapshot:v1:...
artifact_spec_path: work/compiled/artifact-spec.json
output_dir: output/template-artifact
```

它至少重验：

1. task root、路径和 source hashes；
2. final snapshot 与当前 DOCX hash；
3. Registry ID/version/hash 以及所有 `field_id`；
4. content-control 的 `w:alias`/`w:tag` 与 slot 合同；
5. artifact locator 唯一性、expected match count 和模板 hash 绑定；
6. protected fingerprints 与 remove residue；
7. mutation lineage 连续性；
8. final `candidate_verification` 覆盖精确最终 hash 的所有页面；
9. 没有未处理 machine blocker 或 blocking manual/gap/unresolved；
10. 四文件 schema、hash、重读和原子目录发布。

成功返回：

```yaml
call_status: ok
artifact_status: built
published: true
output_path: output/template-artifact
template_sha256: <sha256>
fill_contract_sha256: <sha256>
counts:
  slot: 0
  protected: 0
  remove: 0
  manual: 0
  gap: 0
  unresolved: 0
```

请求/运行错误使用 `needs_input | error`；完整检查已执行但存在阻断 finding 时使用
`artifact_status: blocked`、`published: false`。任何非成功路径都不创建输出目录，也不覆盖已有
目标。

## 9. 已实现 Eval 的消费合同

仓库中的独立模板 Eval 已完成 W0–W5，当前 98 个测试通过；三校目录仍为 candidate，Human
accepted Gold 为 0/3。它不是当前 Tool/Agent Gate，但已经是实际消费者，不再以“未来可能的
Eval”描述。

映射固定为：

| 模板产物 | Eval Actual |
|---|---|
| `clean-template.docx` | Actual template |
| `fill-contract.json` | Actual fill contract |
| Registry ref/hash | Eval Registry binding |
| `visual-review.json`、`build-report.json` | 来源与审查证据；当前静态评分器不直接把 Agent disposition 当质量结论 |

Tool / Code Gate 必须证明 `fill-contract.json` 符合
`docfit-template-fill-contract/v1`，并至少用一个合成产物通过现有 Eval 的输入加载边界。产品运行时
不 import Eval Python 包，Eval 也不 import 产品包；兼容性通过文件/schema/hash 证明。

## 10. 实现与切换边界

候选实现位于 `src/docfit/template/**`，公开 SDK schema/handler 位于
`src/docfit/tools/template_schemas/**` 与 `src/docfit/tools/template_tools.py`。模板领域层只
管理结构 snapshot/mutation/comparison/build；视觉能力由共享 `src/docfit/visual/**` 提供。

W0–W5 可以在不切换生产的情况下实现和验证。W6 是单独批准的原子生产切换，必须同时更新：

- `docfit prepare-template` 公共入口；
- 生产 Skill 与四个 Tool 注册；
- permissions、hooks、observability 和 doctor/smoke；
- `convert-thesis` 及其他下游消费者；
- 包内容、测试和长期文档；
- 旧 `docx_*` Tool/Skill 路径的删除。

W6 有一个硬前置条件：转换端的新 Tool 合同必须另行完成设计、实现和迁移证明。当前
`convert-thesis` 仍依赖旧 `docx_*` 能力；在转换消费者可以使用新合同之前，不得执行旧 Tool
删除或生产切换。

## 11. 当前验收责任

当前只有两个产品 Gate：

### 11.1 Tool / Code Gate

直接调用四个 Tool 和两个编译器，证明：输入/拒绝、源只读、DOCX 可打开、Registry/marker/
locator、hash/ref、视觉证据、四文件集合和原子发布符合合同。它不启动 Agent，也不评分学校
语义质量。

### 11.2 Agent Gate

使用真实 SDK 接缝验证 Agent 能正确传递当前 ref/hash、处理失败、返工并形成完整 built 产物；
最终 `ResultMessage.structured_output` 与磁盘路径、hash、状态和 counts 一致。它不绑定无关精确
调用次数、完整 transcript 或语义质量分数。

现有独立 Quality Eval 判断模板做得好不好，但 Human Gold 未完成；它既不能替代前两个 Gate，
也不成为本轮模板生产实现的完成门。
