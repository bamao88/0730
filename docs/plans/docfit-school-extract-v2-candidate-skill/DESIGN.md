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
5. 把成功产物发布到 `<output>/template-artifact/`；
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

`template_mutate` 对计划执行顺序、snapshot/hash、目标唯一性、容器边界、受保护内容和 DOCX
可打开性做前置/后置检查。任何失败都不发布新 DOCX；重试使用新输出路径。

## 7. 视觉证据与最终审查

视觉级别固定为：

- `none`：只建立结构事实；
- `quick`：OfficeCLI 快速返工定位；
- `candidate_verification`：Adobe 路由的最终候选全页证据。

`candidate_verification` 表示固定的高保真验证路由，不表示 Word/WPS 质量已经被权威认证。
Agent 必须实际读取最终模板 hash 的每一页图片，为 required images 和 findings 写结构化
disposition。结构检查、渲染事实和 Agent 视觉判断必须分开保存。

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
`src/docfit/tools/template_schemas/**` 与 `src/docfit/tools/template_tools.py`。领域层通过 ports
接收 OfficeCLI/Adobe 能力，不反向导入 Tool 注册层。

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
