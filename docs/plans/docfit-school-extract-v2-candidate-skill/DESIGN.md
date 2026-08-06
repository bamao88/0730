# `docfit-school-extract` 绿地重设计方案

> 状态：目标合同已确定到可实施、可验收，尚未实现。本文描述新的生产设计，不承担旧
> Tool、旧 Skill 或旧产物的兼容迁移；实施顺序与验收门见 `PLAN.md`。
>
> 候选设计优化与获批实现期间，本目录是 Agent、Skill scripts、Tool、产物和验证责任的
> 临时权威。现有生产实现和长期文档不能反向削弱本合同；生产切换前再统一更新受影响的
> 长期文档。
>
> 五个 Tool 的实现级接口见 `TOOL-DESIGN.md`；两份决定文件和两个脚本的实现级合同见
> `SCRIPT-DESIGN.md`。
>
> **修改约束：**`PLAN.md` 第 0 节是本目录最高原则。修改本文或任何下层实施文档前必须
> 先检查阶段、轻量产品、分阶段落地和两个当前测试 Gate；冲突的下层内容应修改或延期。

## 1. 设计结论

`docfit-school-extract` 把当前任务中的学校模板与文字要求整理为一个可独立消费的冻结模板产物：

```text
frozen-template-artifact/
├── clean-template.docx
├── template-artifact.json
├── visual-review.json
├── build-report.json
└── freeze-report.json
```

生产运行采用五个有类型合同的领域 Tool：

```text
template_observe
template_mutate
template_compare
template_build
template_freeze
```

它们分别负责观察、执行修改、前后对账、编译候选产物和独立冻结。Agent 是任务和最终
产物的 owner：既负责材料语义、删除意图、槽位责任、来源冲突和视觉判断，也负责检查
每次脚本/Tool 结果；发现失败、误伤或不符合目标时，修改决定或操作并重新执行，直到
产物正确冻结或出现当前范围内无法解决的真实阻塞。Tool 负责可重复的文档事实、修改、
验证和原子发布，不承担最终任务结果。

生产 Skill 包含两个确定性“决策编译”脚本，分别保护修改 DOCX 和生成 candidate 这两个
真实副作用边界。它们把 Agent 的两份决定文件规范化为 mutation plan 与 artifact spec；
artifact spec 内嵌规范化的 typed review record。脚本不读取或修改 DOCX，不替 Agent 做
语义或视觉判断，也不发布 candidate/frozen；五个 Tool 仍是文档事实、副作用、对账和冻结
的权威边界。

### 1.1 五个 Tool 与两个脚本的产品能力合同

本节固定 v1 候选产品到底提供哪些能力、能力入口、可调用 action/mode、主要输入、成功输出
和关键拒绝。这里列出的 action/mode 才属于产品能力；未列出的能力默认不支持。分阶段实现
可以逐项开放，但某项只有在对应 Tool / Code Gate 通过后才能称为“已支持”。

`TOOL-DESIGN.md` 与 `SCRIPT-DESIGN.md` 只能细化字段和错误码，不得增加本节未定义的公开
能力，也不得把本节的一项能力暗中转移给 Agent、脚本或另一个 Tool。

| 入口 | v1 公开能力面 | 是否产生持久副作用 |
|---|---|---|
| `template_observe` | `create`、`query`、`images` | 只发布不可变 snapshot/render evidence，不改 DOCX |
| `template_mutate` | 请求本身无 action；执行 plan 内的 `materialize_slot`、`remove_content`，删除有六种 mode | 原子发布新 DOCX、after snapshot 和 mutation evidence |
| `template_compare` | `create`（`mutation_review`、`final_review`）及 `images` | 只发布不可变 comparison/image evidence，不改 DOCX |
| `template_build` | 单一 build 入口 | 原子发布 candidate 四文件目录 |
| `template_freeze` | 单一 freeze 入口 | 检查全绿后原子发布 frozen 五文件目录 |
| `compile_mutation_plan.py` | 单一 CLI；无 mode | 原子发布 canonical mutation plan JSON |
| `compile_artifact_spec.py` | 单一 CLI；无 mode | 原子发布 canonical artifact spec JSON |

#### 1.1.1 统一入口与调用规则

五个 Tool 通过 Agent 可见的 MCP 名称调用：

```text
mcp__docfit__template_observe
mcp__docfit__template_mutate
mcp__docfit__template_compare
mcp__docfit__template_build
mcp__docfit__template_freeze
```

调用体统一是 JSON object，至少包含 `schema_version: 1` 和 `task_root`。所有路径解析后
必须位于当前任务根；源文件保持只读；需要写文件或目录的入口只接受尚不存在的新目标。
snapshot/render/mutation/comparison ref 对 Agent 不透明，调用方只能原样传递，不能解析或
自行拼接。

两个脚本通过当前 Skill 根下的 CLI 调用：

```text
uv run python <skill-root>/scripts/<script>.py \
  --task-root <task-root> --input <decision-file> --output <canonical-json>
```

脚本只有 `--task-root`、`--input`、`--output`、`--help`、`--version`，不提供 mode、overwrite、
best-effort、provider/backend 或跳过验证参数。

#### 1.1.2 `template_observe`：观察、查询和读取图片

公开入口：`mcp__docfit__template_observe`。

| action | 核心输入 | 产品能力 | 成功输出 |
|---|---|---|---|
| `create` | `input_docx`、`visual_level`、可选 `focus` | 只读解析 DOCX，建立绑定精确 hash 的不可变事实 snapshot；可按 focus 提取结构、可见对象、有效样式和槽位候选；识别不支持能力；按视觉等级建立或复用 render | `snapshot_ref`、document/source hash、objects、styles、sections、`unsupported_features`，以及可选 `render_ref`/page count |
| `query` | `snapshot_ref`、`query{text, match, include?}` | 在既有 snapshot 中按 `exact`、`casefold` 或 `regex` 查询全部匹配；可返回周边上下文、有效样式解析和视觉位置 | 稳定排序的 `matches[]`、opaque object refs 和 `match_count`；零匹配仍是成功结果 |
| `images` | `render_ref`；可选且互斥的 `pages`/`cursor`；可选 `max_images` | 分批读取已有 render 的原生页面图片，不重新解释文档 | 图片 metadata、原生 image blocks、`next_cursor` |

`create.focus` 只支持：

```text
structure
visible_objects
styles
slot_candidates
```

`create.visual_level` 只支持：

- `none`：只建立结构事实；
- `quick`：生成或复用返工定位图片；
- `authoritative`：生成或复用可进入最终审查的权威页面证据。

观察层至少能识别段落/run、表格/行/单元格、文本框、内容控件、书签、域、分节、页眉页脚、
分页边界、命名样式、继承、直接格式和最终有效格式。它不支持判断“这是不是论文标题”、
“该不该删除”或“应该建什么槽位”。

关键拒绝：越界路径、非 DOCX/损坏 package、观察期间源 hash 变化、无效 query、跨任务或
不存在的 ref、不可用的渲染和超出图片批次预算。失败不发布 snapshot/render 半成品。

三种 action 的调用形态：

```jsonl
{"schema_version":1,"action":"create","task_root":"/task","input_docx":"input/template.docx","visual_level":"none","focus":["structure","visible_objects","styles","slot_candidates"]}
{"schema_version":1,"action":"query","task_root":"/task","snapshot_ref":"snapshot:v1:...","query":{"text":"标题","match":"casefold","include":["surrounding_context","style_resolution","visual_location"]}}
{"schema_version":1,"action":"images","task_root":"/task","render_ref":"render:v1:...","pages":[1,2],"max_images":8}
```

#### 1.1.3 `template_mutate`：建立槽位和删除内容

公开入口：`mcp__docfit__template_mutate`。

```json
{"schema_version":1,"task_root":"/task","input_docx":"work/template-v1.docx","output_docx":"work/template-v2.docx","mutation_plan_path":"work/compiled/mutation-plan.json"}
```

Tool 不接受 inline operation 或自然语言指令，只执行编译后的 mutation plan。plan 中的公开
operation 只有两类：

| operation | 支持的能力 | 主要约束 |
|---|---|---|
| `materialize_slot` | 在现有段落、表格单元格或有显式起止的段落流边界写入不可见的 DocFit slot anchor，使 after snapshot 能按 `slot_id` 唯一定位；内容种类支持 `scalar`、`paragraph_stream`、`composite` | 保留容器、样式和当前可见内容；不插入占位文字，也不顺带清空示例。清理可见内容必须是单独的 `remove_content`；manual responsibility 不得自动建槽；同一 `slot_id` 只能建立一次 |
| `remove_content` | 按下表六种物理删除方式移除已确认内容，并在删除前验证所有存续责任已经迁移 | 必须使用当前 snapshot 的精确 ref/fingerprint；删除模式必须与 object kind 匹配；fixed 删除需要当前任务明确授权 |

`remove_content` 的六种候选删除能力固定为：

| `removal_mode` | 实际动作 | 必须保留 |
|---|---|---|
| `clear_text_preserve_container` | 清空目标容器中的可见文字 | 段落/run 容器、属性、锚点和邻近内容 |
| `remove_inline_fragment` | 删除混合内容中的精确 inline 片段 | 周边 run、空格、标点、域和顺序 |
| `remove_container` | 删除一个完整且已定位的物理容器 | 邻接结构、编号、分页和分节保护项；容器内不得有未迁移责任 |
| `remove_bounded_block` | 删除显式起止边界间的连续逻辑块 | 两端边界及范围外对象 fingerprints |
| `clear_cell_preserve_grid` | 清空目标单元格内容 | cell/row、table grid、merge、行高、单元格属性和相邻单元格 |
| `unwrap_control_preserve_content` | 移除内容控件外壳 | 控件内部获准内容、顺序、格式和锚点 |

`materialize_slot` 的 v1 可修改目标只有段落、表格单元格和有显式起止的段落流边界。其他对象
即使能被 observe 看见，也不能因此自动获得建槽能力；必须在后续阶段明确加入能力合同和
Tool / Code 断言。slot anchor 的 OOXML 表示属于 Tool 内部实现，但公开后置条件固定为：不可见、
不改变当前正文、绑定唯一 `slot_id`，并能在输出 DOCX 重开后由 after snapshot 唯一重解。

成功结果是新 DOCX、before/after snapshot refs、`mutation_ref`、输入/输出 hash 和逐 operation
结果；输入 DOCX 始终不变。所有 operation 在临时副本中按数组顺序执行并做后置检查，全部
通过才原子发布；任何一步失败都不发布 output。

关键拒绝：plan 非法、input hash 与 snapshot 不一致、ref 过期/歧义、依赖顺序错误、删除
模式与对象不匹配、责任未迁移、未授权 fixed 删除、目标已存在、后置误伤或输出 DOCX 无法
打开。尚未通过当前阶段 Code Gate 的候选 removal mode 必须返回不支持，不能静默降级。

#### 1.1.4 `template_compare`：修改对账、最终覆盖和图片读取

公开入口：`mcp__docfit__template_compare`。支持两个 action：

| action / mode | 核心输入 | 产品能力 | 成功输出 |
|---|---|---|---|
| `create` + `mutation_review` | `before_snapshot_ref`、`after_snapshot_ref`、`mutation_ref` | 对账计划 operation 与实际对象/结构/样式/分页变化；区分 expected 与 unexpected；按风险选择 crop、整页或 contact sheet | `comparison_ref`、expected/unexpected changes、machine findings、required image manifest |
| `create` + `final_review` | `final_snapshot_ref` | 为精确最终 hash 建立 authoritative 全页审查清单，覆盖零 mutation 模板 | `comparison_ref`、最终 hash/page coverage、每页 `final_full_page` required image item |
| `images` | `comparison_ref`；可选且互斥的 `pages`/`cursor`；可选 `max_images` | 分批读取 comparison 已登记的 required images，不临时重渲染 | required image metadata、原生 image blocks、`next_cursor` |

mutation diff 至少覆盖对象增删改、fixed fingerprints、有效样式、表格 grid、内容控件、域、
书签、分节、页眉页脚、编号、分页边界、页数和 slot anchors。Tool 只产出事实和
`machine_blocking`，不产出 Agent disposition，不判断视觉结果是否可接受。

关键拒绝：before/mutation/after lineage 不一致、snapshot hash 不匹配、authoritative render
不可用、页面映射失败、无效 cursor、请求未登记图片或混用不同 hash 的图片。

两种 create mode 与 images 的调用形态：

```jsonl
{"schema_version":1,"action":"create","task_root":"/task","review_mode":"mutation_review","before_snapshot_ref":"snapshot:v1:...","after_snapshot_ref":"snapshot:v1:...","mutation_ref":"mutation:v1:..."}
{"schema_version":1,"action":"create","task_root":"/task","review_mode":"final_review","final_snapshot_ref":"snapshot:v1:..."}
{"schema_version":1,"action":"images","task_root":"/task","comparison_ref":"comparison:v1:...","cursor":"opaque-cursor","max_images":8}
```

#### 1.1.5 `template_build`：生成 candidate artifact

公开入口：`mcp__docfit__template_build`。

```json
{"schema_version":1,"task_root":"/task","final_snapshot_ref":"snapshot:v1:...","artifact_spec_path":"work/compiled/artifact-spec.json","candidate_output_dir":"work/candidate-attempt-1"}
```

它支持把以下已编译对象与最终 DOCX 组合为 candidate：sources、fixed regions、automatic
slots、manual regions、gaps、unresolved、style claims/conflicts、mutation evidence chain、
final review dispositions 和内嵌 `ReviewRecordV1`。build 会重新验证最终 hash、source hash、
slot locator 唯一性、fixed fingerprints、lineage、审查覆盖和 machine blockers。

成功只原子发布四个文件：

```text
clean-template.docx
template-artifact.json        # artifact_status: candidate
visual-review.json
build-report.json
```

关键拒绝：artifact spec 无效、final snapshot/hash 不一致、source 漂移、slot 重复或无法唯一
定位、fixed 内容变化、审查缺页、存在 blocking finding、目标目录已存在或候选文件集不完整。
build 不支持修正决定、填补 gap、降级 automatic slot、生成 freeze report 或返回 frozen。

#### 1.1.6 `template_freeze`：独立验证并发布 frozen artifact

公开入口：`mcp__docfit__template_freeze`。

```json
{"schema_version":1,"task_root":"/task","candidate_dir":"work/candidate-attempt-1","frozen_output_dir":"output/frozen-attempt-1"}
```

freeze 固定执行以下产品检查：

1. candidate 恰好包含四个规定文件；
2. DOCX package 可重新打开；
3. candidate manifest、template/source/file hashes 可复算且一致；
4. 所有 source 当前 hash 未变化；
5. automatic slot 可在 DOCX 上唯一重解，语义和基数有效；
6. fixed fingerprints 一致；
7. manual/gap/unresolved 显式且没有 blocking unresolved；
8. review record 与 `visual-review.json` 一致；
9. authoritative final review 覆盖精确最终 hash 的全部页面；
10. mutation lineage 连续且没有未处理 machine blocker；
11. build report 与 candidate 文件 hashes 完整；
12. frozen 临时目录完整写入、重读和 hash 校验成功。

全部通过后原子发布五个文件：

```text
clean-template.docx
template-artifact.json        # artifact_status: frozen
visual-review.json
build-report.json
freeze-report.json
```

成功返回 `artifact_status: frozen`、`published: true`、模板 hash、frozen 路径和可复算的
`artifact_ref`。机器检查完整执行但未通过时返回 `artifact_status: blocked`、
`published: false`；请求或运行错误使用 `needs_input | error`。任何非成功路径都不创建 frozen
目标。freeze 不支持修正文档、跳过检查、接受 Agent pass flag、覆盖已有目录或把 candidate
原地改成 frozen。

#### 1.1.7 `compile_mutation_plan.py`：编译修改决定

调用入口：

```text
uv run python <skill-root>/scripts/compile_mutation_plan.py \
  --task-root <task-root> \
  --input work/decisions/mutation-decisions.yaml \
  --output work/compiled/mutation-plan-attempt-1.json
```

输入支持 YAML/JSON，包含：当前 snapshot、Agent decisions、`fixed | fill | generate`
responsibilities、`scalar | paragraph_stream | composite` content kinds、cardinality、condition、
`automatic | manual` handling，以及按顺序排列的 `materialize_slot | remove_content` operations。
删除 operation 还可包含六种 removal mode、责任迁移目标、保护项和 fixed 删除授权。

脚本执行 schema/ref/fingerprint 校验、operation 依赖排序校验、action/mode 与 object kind 校验、
责任存续/迁移校验和 canonical 序列化。成功原子生成带 digest 的 `mutation-plan.json`；相同输入
和证据逐字节稳定。它拒绝未知字段/action/mode、跨 snapshot 或过期 ref、未决破坏性操作、
依赖环/向后依赖、责任未迁移、未授权 fixed 删除和已存在的不同输出；失败不覆盖旧输出。

脚本不读取或修改 DOCX，不调用 Tool，不生成语义决定，也不管理 attempt。

#### 1.1.8 `compile_artifact_spec.py`：编译候选产物合同

调用入口：

```text
uv run python <skill-root>/scripts/compile_artifact_spec.py \
  --task-root <task-root> \
  --input work/decisions/artifact-decisions.yaml \
  --output work/compiled/artifact-spec-attempt-1.json
```

输入支持 YAML/JSON，固定接收：

```text
final_snapshot_ref
sources
fixed_regions
slots
manual_regions
gaps
unresolved
style_claims
mutation_evidence_chain
final_review
```

脚本解析不可变 evidence refs，验证所有领域 ID/引用、source 与 final hash、automatic slot
locator、manual/gap 显式性、style conflict resolution、mutation lineage、required images/
findings dispositions、逐页覆盖和 machine blockers；然后构造内嵌 `ReviewRecordV1`。

成功原子生成 canonical `artifact-spec.json`，包含上述领域对象、review record、review digest
和 spec digest。它拒绝 stale/cross-snapshot ref、重复 ID、不完整责任、automatic slot 缺
locator、blocking unresolved、未解决 style conflict、lineage 缺口、未审查边、非 accepted
disposition、缺页审查、残留 machine blocker 和已存在的不同输出；失败不覆盖旧输出。

脚本不打开或修改 DOCX，不渲染图片，不替 Agent 判断质量，也不 build/freeze。

#### 1.1.9 七个入口共用的底层产品能力

| 底层能力 | 由哪些入口使用 | 产品行为 |
|---|---|---|
| task-root 路径与源只读保护 | 全部入口 | 解析 canonical path/symlink 并拒绝任务根越界；直接读取 DOCX/source 的 Tool 在对应边界重查 hash，两个脚本只验证声明的路径与 evidence ref，不打开源文档 |
| canonical JSON、SHA-256 与 digest | 两个脚本、build、freeze | 同一输入产生稳定 bytes/hash；digest 可由消费者独立重算 |
| immutable evidence store 与 opaque refs | observe、mutate、compare、两个脚本、build、freeze | snapshot/render/mutation/comparison evidence 绑定任务根和精确文档 hash，旧/跨任务 ref 失败 |
| DOCX 事实提取与有效样式解析 | observe，并由 compare/build/freeze 重验需要的子集 | 解析结构、对象、关系、命名/继承/直接/有效格式，不由 Agent 猜测底层文档事实 |
| DOCX 修改原语与后置保护 | mutate | 在临时副本执行 slot/删除动作，重开并检查容器、表格、分节、页眉页脚和邻近内容 |
| 固定渲染、缓存和图片分批 | observe、compare | `quick` 使用固定返工路由，`authoritative` 使用固定交付路由；同 key 复用，图片按 cursor 返回 |
| 结构/视觉变化对账 | compare | 将 mutation plan 与实际对象/页面变化对应，产出 expected/unexpected 和 required evidence |
| artifact 组装 | build | 从最终 DOCX 与已编译合同确定性生成 candidate 四文件集合 |
| 独立冻结验证 | freeze | 不信任上游成功，重读 candidate/source/evidence 后生成 frozen 五文件集合和 artifact ref |
| 原子文件/目录发布 | 两个脚本、mutate、build、freeze | 临时写入、重读校验、fsync/rename；失败不发布半成品且不覆盖已有目标 |

底层执行固定复用 OfficeCLI 的 DOCX 观察/修改/验证能力和 Adobe 的 authoritative 转换能力；
公开入口不接受 provider/backend 选择，也不增加第二 Agent loop 或工作流引擎。

七个入口共同遵守三个产品结论：

1. Tool 负责可信事实、受控副作用和发布边界；脚本只把 Agent 决定编译成 Tool 可重验输入；
   Agent 负责语义判断、返工和最终任务结果。
2. compiler、observe、mutate、compare 或 build 成功都只是链路中的有效中间结果；只有
   `template_freeze` 成功发布的 frozen artifact 才具备产品交付资格，Agent 仍对最终任务结果
   负责。
3. 未来 Eval 只评价 frozen 对象做得好不好，不接管上述七个入口的运行责任，也不依据
   Agent transcript 替代产物评测。

### 1.2 Claude Agent SDK 原生运行合同

Agent 运行层不属于本模块的自研产品能力。实现固定复用仓库现有 Claude Agent SDK 接缝：

```text
filesystem Skill（SKILL.md + scripts + references）
  └─ setting_sources=["project"] + skills allowlist
       └─ ClaudeSDKClient 的一个任务 query/session
            ├─ SDK 原生 agent/tool loop、消息、compaction、turn/budget 终止
            ├─ 现有 build_docfit_server() 中的五个 in-process MCP Tool
            ├─ 现有 permissions / PreToolUse hooks / can_use_tool
            └─ output_format JSON Schema → ResultMessage.structured_output
```

SDK 与领域合同的边界固定如下：

- 五个 Tool 使用 SDK `@tool` 定义并由 `create_sdk_mcp_server()` 统一注册；Tool input schema、
  handler、领域失败码和原子副作用由 DocFit 定义，MCP transport 和 tool loop 不自建。
- Tool 返回 SDK 原生 `content`、`structuredContent` 和 error 标记；图片直接使用原生 image
  content block。领域 `call_status`/`artifact_status` 仍在结构化 payload 内，不能用 transport
  success/error 替代产品状态。
- Tool 失败返回给 SDK 后，SDK 保持 Agent loop，Agent 根据稳定失败码重新观察、修正决定或
  使用新 attempt；DocFit 不实现通用 retry engine。`retryable` 只描述领域事实，不自动重放
  有副作用的调用。
- 缺少必要用户裁决时使用 SDK 原生 `AskUserQuestion` 与现有 `can_use_tool` 回调；不得发明
  question file、pause status 或另一套多轮协议。
- 成功或阻断的最终机器结果由 SDK structured output 输出。v1 schema 固定要求
  `status: frozen | blocked`、`frozen_path`、`template_sha256`、`artifact_ref` 和
  `counts{slot,fixed,manual,gap,unresolved}`；除 `status` 外的交付值在尚未形成可验证 frozen 时为
  `null`，不能伪造路径/hash/counts。Agent Gate 读取
  `ResultMessage.structured_output` 并与磁盘重算，不解析最终自然语言。
- 当前一次提取任务不需要自建 session registry、resume/fork 流程或 subagent scheduler。
  SDK session 只保留对话；DocFit evidence/ref/artifact 必须独立落盘并绑定 task root/hash。
- hooks 和 permissions 保护 Agent 可调用边界；Tool handler 仍必须独立重验路径、source hash、
  ref lineage 和发布原子性。任何 hook 放行都不能视为领域检查通过。

仓库锁定版本是 `claude-agent-sdk==0.2.128`。该版本 in-process MCP bridge 的
`structuredContent` 可见性兼容点继续集中复用现有结果 helper：首个 text block 镜像相同的紧凑
JSON。它不是第二套结果协议；只有升级后 contract proof 证明 Agent 可稳定直接消费
`structuredContent`，才删除镜像。

## 2. 五类资产各自负责什么

| 资产 | 负责 | 不负责 |
|---|---|---|
| Skill | 推荐做法、判断步骤、结果检查、错误诊断、返工规则、删除与槽位决策原则、冲突处理和询问用户的时机 | 实现 DOCX 操作、把 Tool 成功等同于任务完成 |
| Skill scripts | 把 Agent 已完成的语义决定校验、规范化并编译为版本化 Tool 输入 | 观察/修改 DOCX、生成语义决定、证明视觉正确、发布产物 |
| Tool | 不可变观察、带前置条件的原子修改、结构与视觉差异、候选编译、独立冻结 | 判断哪个“标题”是论文标题、决定说明是否该删、解释版式是否合理 |
| references | 多场景复用但不宜全部放在主文件的判断方法，以及决策文件/编译器的使用合同 | 学校事实、脚本实现源码、完整 Tool 手册、固定工作流状态机 |
| 开发脚本 | 原型验证、fixture 生成、人工调试 | 冒充生产决策编译器或 frozen 发布边界 |

`Skill` 可以明确告诉 Agent 通常先做什么、后做什么，以及每一步的判断标准。这是一种
可调整的操作方法，不是由程序强制的工作流状态机。Agent 可以按证据需要回到观察、修改
或询问用户；Tool/脚本错误和 compare/freeze findings 是返工输入，不是自动终点。Agent
不能绕过冻结验证取得 `frozen` 状态，也不能仅凭 freeze 成功忽略仍可见的语义或视觉错误。

### 2.1 为什么是两个编译脚本

编译器按需要独立预检的副作用边界设置，而不是每种 typed 数据各配一个脚本。系统只有
两个这样的边界：修改 DOCX 之前，以及生成 candidate 之前。视觉判断没有独立副作用，也
没有 build 之前的独立消费者，因此保留内部 typed review model，但不制造第三个 Agent
编译阶段。

| 方案 | 主要问题 | 结论 |
|---|---|---|
| 0 个脚本 | Tool 同时承担语义输入编译和副作用，缺少可审阅预检产物 | 太少 |
| 1 个通用脚本 | mutation 与 artifact 生命周期混入多模式入口，容易演变成工作流引擎 | 边界不清 |
| 2 个脚本 | 分别保护修改和 candidate build 两个真实边界 | 采用 |
| 3 个脚本 | review compiler 没有独立副作用边界，增加文件、调用和状态同步 | 过度拆分 |

## 3. Skill 的推荐操作方法

```text
盘点来源
  → 观察不可变模板快照
  → Agent 分开记录可见角色、存续责任、修饰字段与证据状态
  → Agent 决定修改动作；仅为删除动作选择删除模式
  → Skill script 编译 mutation plan
  → Tool 原子修改
  → Tool 对账并返回原生图片
  → Agent 解释视觉结果
  → Agent 把最终语义与审查判断写入 artifact decisions
  → Skill script 编译内嵌 review record 的 artifact spec
  → Tool 编译 candidate
  → Tool 独立验证并发布 frozen
  ↺ 任一步发现错误时，Agent 回到相应决定、观察或修改点继续修正
```

Agent 在这个过程中应完成以下工作：

1. 盘点模板、文字要求、官方示例及其来源状态，记录冲突和无法确认的内容。
2. 观察模板结构、可见对象、有效样式、槽位候选和页面证据，不把页码当成编辑身份。
3. 不使用混合的单一内容分类。分别记录当前可见角色，清理后存续的 fixed/fill/generate
   责任，基数、条件与 automatic/manual 处理方式，以及 resolved/unresolved 证据状态。
4. 先依据语义决定保留、槽位、manual 或 `remove_content` 操作；只有删除操作才选择
   `removal_mode`。删除说明或示例前，先迁移其中仍需保留的格式、基数、生成机制或填写
   责任。
5. 将文字要求与模板的最终有效格式交叉验证；冲突不能靠样式名、历史经验或常识消解。
6. 对每个修改给出明确目标、前置指纹、删除模式或槽位合同，由 Skill script 编译并校验
   mutation plan，再交给 Tool 执行。
7. 阅读结构差异和 Tool 直接返回的图片；预期变化缺失、出现误伤或视觉结果不合理时，
   修改决定/操作并重新执行，不能只把 finding 记录下来。
8. 把最终内容责任、完整 mutation/comparison evidence chain 和逐页视觉解释写入同一份
   artifact decisions，由脚本构造内嵌 review record 的 artifact spec；只将这份绑定已确认
   最终快照的结构化输入交给 build。build/freeze 拒绝时根据 findings 返回对应环节修正；
   只有独立冻结通过且 Agent 确认最终结果正确后才交付 frozen artifact。

## 4. 两个生产 Skill 脚本

两个脚本随 Skill 发布，由 Agent 在当前任务 work 目录中运行。它们使用与 Tool 共享的
版本化类型模型，输入支持人可编辑的 YAML/JSON，输出为 canonical JSON；验证失败时不
覆盖旧输出，也不生成部分文件。两个脚本都显式接收 `--task-root`、输入和输出路径；成功、
决定/schema 错误、环境/I/O 错误分别使用退出码 `0`、`2`、`1`。输出携带 schema/compiler
版本、输入 hash 和绑定的 snapshot/hash。完整 CLI 与原子写合同见 `PLAN.md` 第 4.2 节。
字段模型、canonical bytes、拒绝码和直接编译器断言以 `SCRIPT-DESIGN.md` 为实现依据。

### 4.1 `compile_mutation_plan.py`

输入是 Agent 写出的 `mutation-decisions.yaml`，包含当前 `snapshot_ref`、decision/operation
ID、目标 ref、当前可见角色、存续责任、责任的内容种类/基数/条件/处理方式、证据状态、
expected text/fingerprint、动作、删除动作的 `removal_mode`、槽位语义、迁移目标、理由和
证据 ref。

脚本检查 operation ID 唯一、action/`removal_mode` 合法、必填前置条件存在、自动槽位
语义完整、页码/bbox/裸文本未被冒充 locator，并输出 `mutation-plan.json`，供
`template_mutate` 直接消费。它拒绝把 repeat/conditional/manual/remove/unresolved 写成
责任 kind，拒绝非删除动作携带删除模式、删除动作缺少模式、未决内容被破坏性删除、
删除前存续责任没有迁移目标，以及没有当前任务明确授权和责任替代/迁移/终止决定的 fixed
删除。文档 mutation action 只有 `materialize_slot` 和 `remove_content`；manual region 与
gap 进入 artifact decisions，不作为无副作用的伪 mutation。操作按数组顺序执行，
`depends_on` 只能引用更早操作；编译器拒绝在迁移目标存在前删除承载该责任的内容。

### 4.2 `compile_artifact_spec.py`

输入是 Agent 写出的 `artifact-decisions.yaml`：最终 snapshot、内容责任/来源/样式决定、
槽位、fixed/manual/gap 清单、完整 mutation/comparison evidence chain，以及最终全页图片
的 Agent dispositions。脚本解析 Tool 管理的不可变 evidence refs，先在内部构造并验证
typed `ReviewRecordV1`，再把规范化 `review_record` 嵌入 `artifact-spec.json`。

脚本检查 `slot_id` 唯一、责任和内容种类/基数完整、来源与样式状态可追溯、manual/gap
显式、所有 ref 属于最终 snapshot、mutation lineage 没有未审查边、必需图片均有判断、
machine-blocking finding 未被静默清除，并且最终页面覆盖属于同一 hash。它只校验和记录
Agent 判断，不替 Agent 决定视觉结果是否正确，也不生成独立 `review-decisions.yaml` 或
`review-record.json`。

脚本输出不是权威事实。`template_mutate` 和 `template_build` 必须按自己的 typed schema
再次验证；`template_freeze` 更不能相信脚本的成功返回。

### 4.3 共享路径、引用和状态合同

五个 Tool 与两个脚本都接收同一个 `task_root`。源材料保持只读，Agent 决定与编译输出写入
work，Tool 的不可变 snapshot/comparison/render 证据由 task root 内的 Tool store 管理，
frozen 只发布到 output。opaque ref 必须绑定任务根与精确文档 hash；缺失、跨任务或 stale
ref 一律失败且不产生副作用。

Tool 调用状态统一使用 `call_status: ok | needs_input | error`。领域状态另行表达：build 返回
`artifact_status: candidate`；freeze 完成检查后返回 `artifact_status: frozen | blocked` 与
`published`。冻结检查被阻断和 Tool 请求/运行错误不是同一种状态。完整 envelope、路径布局
与失败语义见 `PLAN.md` 第 3–6 节。

## 5. 五个生产 Tool

本节固定职责和主要数据流；公开输入/输出 schema、稳定错误码、原子性、图片 cursor 和逐
Tool 的直接输入、输出与拒绝断言以 `TOOL-DESIGN.md` 为实现依据。

### 5.1 `template_observe`

职责是建立不可变模板证据快照，或查询已有快照。

新观察的核心输入：

```yaml
action: create
task_root: ...
input_docx: school-template.docx
visual_level: quick | authoritative | none
focus: [structure, visible_objects, styles, slot_candidates]
```

查询已有快照的核心输入：

```yaml
action: query
task_root: ...
snapshot_ref: ...
query:
  text: 标题
  match: exact
  include: [surrounding_context, style_resolution, visual_location]
```

输出至少包含文档 hash、`snapshot_ref`、稳定对象引用、段落/表格/文本框/内容控件等结构、
命名样式/直接格式/继承链/最终有效格式、书签/域/分节/页眉页脚、PDF/逐页图片/contact
sheet、页面与对象映射，以及无法观察的内容。

查询“标题”时，Tool 返回全部候选及其上下文和样式事实，不判断哪个候选具有论文标题语义。
图片使用 `action: images` 按页或 cursor 分批返回；`none`/`quick` 证据不能满足最终冻结所需
的 authoritative 全页覆盖。

### 5.2 `template_mutate`

职责是安全执行 Agent 已经决定、并由 `compile_mutation_plan.py` 编译的显式操作计划。

```yaml
task_root: ...
input_docx: work-v1.docx
output_docx: work-v2.docx
mutation_plan_path: work/compiled/mutation-plan.json
```

规范 mutation plan 中相关操作的安全顺序是：

```yaml
operations:
  - operation_id: slot-title
    action: materialize_slot
    target_ref: ...
    slot_id: thesis-title
    content_kind: scalar
    cardinality: {min: 1, max: 1}
    depends_on: []
  - operation_id: clean-title
    action: remove_content
    target_ref: ...
    removal_mode: clear_text_preserve_container
    expected_text_sha256: ...
    depends_on: [slot-title]
    migration_targets:
      - responsibility_ref: thesis-title
        target_kind: materialized_slot
        slot_id: thesis-title
        object_ref: null
```

删除模式固定为：

- `clear_text_preserve_container`
- `remove_inline_fragment`
- `remove_container`
- `remove_bounded_block`
- `clear_cell_preserve_grid`
- `unwrap_control_preserve_content`

槽位动作只覆盖既有段落、表格单元格和有显式起止的段落流边界；它写入不可见、可按
`slot_id` 唯一重解的 anchor，不插入占位文字，也不清空现有内容。需要清理示例时必须另列
`remove_content`。manual 区域只登记在 artifact decisions/spec 中，不交给 mutation Tool 执行。

Tool 校验引用属于当前快照、expected text/fingerprint 成立；全部操作原子执行；修改后重新
打开 DOCX，确认需保留的容器与非目标内容；成功返回新 hash、after snapshot 和
`mutation_ref`。任何前置或后置检查失败时不发布输出。Tool 不替 Agent 选择目标、模式或
槽位语义。

### 5.3 `template_compare`

职责是把修改计划与实际前后变化对账，并把 Agent 需要看的原生图片直接放入结果。

```yaml
action: create
task_root: ...
review_mode: mutation_review
before_snapshot_ref: ...
after_snapshot_ref: ...
mutation_ref: ...
```

`review_mode: final_review` 时改为传入 `final_snapshot_ref`，不要求 before snapshot 或
mutation ref，并产出该精确 hash 的全页权威图片清单，从而覆盖零 mutation 模板和最终
快照复核。mutation review 比较对象增删改、固定文字、样式签名、表格
网格、节、页眉页脚、分页边界、槽位容器、
页数和视觉布局。输出分为：

- `expected_changes`：能够与 operation 对上的变化；
- `unexpected_changes`：计划外变化及其 `machine_blocking` 属性；
- `visual_review`：选择图片的原因和前后 crop、整页或 contact sheet。

图片范围由变化风险确定：短文字清空看 crop 与修改后整页；段落删除看目标页及相邻页；
连续块或表格删除看前后 contact sheet 与边界页；分节、页眉页脚、分页或页数变化扩大到
相关 section；映射失败扩大检查范围；最终检查覆盖全部页面。

Tool 不输出视觉 `pass`/`fail`。是否合理仍由 Agent 结合语义和图片判断。
完整 comparison 持久化为 immutable `comparison_ref`；图片使用 `action: images` 和 cursor
分批返回，保证长文档可以在 Tool 传输预算内完成无缺页审查。

### 5.4 `template_build`

职责是把 Agent 已确认、并由 `compile_artifact_spec.py` 编译的最终快照与语义判断编译成
候选产物。

```yaml
task_root: ...
final_snapshot_ref: ...
artifact_spec_path: work/compiled/artifact-spec.json
candidate_output_dir: work/candidate-template-artifact
```

Tool 再次验证 artifact spec 中内嵌的 typed review record，生成规范槽位 manifest 与
`visual-review.json`，绑定最终模板 hash，检查重复 `slot_id`、字段完整性和引用时效，记录
样式观测与来源，并输出：

```text
candidate-template-artifact/
├── clean-template.docx
├── template-artifact.json
├── visual-review.json
└── build-report.json
```

`template_build` 只能生成 `candidate`，不能宣布冻结完成。

### 5.5 `template_freeze`

职责是独立重读候选产物并原子发布。它不直接相信 mutate/compare/build 的成功返回，也
不接受 Agent 的“已检查”作为机器事实。

```yaml
task_root: ...
candidate_dir: work/candidate-template-artifact
frozen_output_dir: output/frozen-template-artifact
```

冻结至少验证：

- DOCX package 可独立打开；
- manifest 中的模板 hash 与文件一致；
- 每个自动槽位唯一定位，内容种类和基数有效；
- 固定内容指纹一致；
- manual 与 gap 显式；
- 所有最终页面都有绑定当前 hash 的审查记录；
- 没有未处理的 blocking finding；
- 来源文件未变化，manifest 不引用旧快照；
- 候选目录内容完整。

成功返回 `call_status: ok`、`artifact_status: frozen`、`published: true`、`artifact_ref`
和 `template_sha256`。冻结检查执行完成但未通过时返回 `call_status: ok`、
`artifact_status: blocked`、`published: false` 和 findings，不发布半成品。请求或运行
错误使用 `needs_input | error`，不能伪装为 `blocked`。只有这个 Tool 能把 `candidate`
变为 `frozen`。

`blocked` 是本次冻结调用的机器结果，不自动等于任务无法继续。Agent 必须把 finding
定位到观察、语义决定、mutation、视觉审查或 artifact spec，修正后重新 build/freeze。
同理，任一 Tool 返回 `ok` 只表示调用成功；如果 Agent 仍发现语义或视觉错误，必须继续
修改。只有缺少用户裁决、授权输入或不可替代外部能力，并且没有安全修正路径时，才把
任务报告为真正阻塞。

## 6. 冻结产物的最小语义

`template-artifact.json` 的物理 schema 由 Tool 合同定义，长期必须表达以下语义：

- 模板精确 hash 与来源 hash；
- 固定区域及其指纹；
- 自动槽位的 `slot_id`、唯一 locator、内容种类和基数；
- fixed/fill/generate responsibility kind，以及独立的 cardinality、condition、handling 和
  resolution，而不是只保存当前缓存文字或把不同维度压进一个枚举；
- manual 区域、gap、冲突和未决项；
- 样式的观测值、要求值、来源、覆盖范围与冲突状态；
- 绑定最终模板 hash 的逐页视觉审查记录；
- `artifact_status: candidate | frozen`、build 结果与 freeze 结果引用。

逻辑责任不能被物理分页替代；源模板中的示例数量不能自动成为重复区域的实例基数；
生成对象不能退化为当前缓存结果。

## 7. Skill、scripts 与 references 目录

当前候选设计目录为：

```text
docs/plans/docfit-school-extract-v2-candidate-skill/
├── DESIGN.md
├── PLAN.md
├── TOOL-DESIGN.md
├── SCRIPT-DESIGN.md
├── SKILL.md
└── references/
    ├── decision-compilation.md
    ├── template-semantics.md
    ├── deletion-and-slot-decisions.md
    ├── style-reconciliation.md
    └── visual-regression.md
```

本轮没有编译脚本源码或 Eval case。W1–W5 隔离实现时，本目录本身就是候选
`<skill-root>`，届时两个薄入口位于 `<skill-root>/scripts/`；W6 再把已验证内容原子替换到
生产 `.claude/skills/docfit-school-extract/`。逻辑调用路径始终相对活跃 `SKILL.md`，不会同时
加载候选与旧生产 Skill。质量 Eval 使用后续独立模块，不放回本候选 Skill 目录。

五份 reference 分别负责：

- `decision-compilation.md`：两份 Agent 决策输入、脚本调用、内嵌 review record、canonical
  输出和失败语义；
- `template-semantics.md`：内容责任、逻辑单元、说明语义迁移、复合/生成对象和来源冲突；
- `deletion-and-slot-decisions.md`：删除模式、选择条件、槽位内容种类、基数、manual/gap；
- `style-reconciliation.md`：命名/直接/继承/有效格式，以及文字要求与模板事实的交叉验证；
- `visual-regression.md`：预期与意外变化、图片范围、Agent 视觉解释和最终全页审查。

主文件直接给出通用操作方法、脚本使用点和高频判断规则；只有遇到相应问题时才加载
reference。references 不保存学校具体要求，不复述完整 Tool schema，也不提供 Tool
路由/错误恢复手册。

## 8. 实现形态

实际目标目录、文件 owner、规模阈值和按阶段创建顺序以
[`TDD-IMPLEMENTATION-PLAN.md`](TDD-IMPLEMENTATION-PLAN.md) 第 2 节为准。实现保持一个
`src/docfit/template/` 领域包，但把 contracts、runtime、两个 compiler、observe、mutate、
compare、build 和 freeze 按变化原因分开；公开 MCP schema/handler 留在 `src/docfit/tools/`
薄层。不得把全部模型、六种 mutation mode 或 build/freeze 重新堆回单个大文件，也不得为了
行数制造只有转发逻辑的浅模块。

领域服务通过 `src/docfit/template/ports.py` 接收 OfficeCLI/Adobe 等外部边界，不反向导入
`docfit.tools`；`template_tools.py` 只保存五个原生 `@tool` 定义/handler，现有
`src/docfit/tools/__init__.py` 中的 `build_docfit_server()` 继续作为唯一 SDK MCP composition
root，注入适配器并汇总注册。依赖方向、schema 拆分和硬性文件规模上限以 TDD 子计划第 2 节
为准。

产品包和候选 Skill 运行脚本不得包含测试 fixture、fake、builder、pytest helper 或 Agent
harness，也不得反向导入 `tests/`。测试辅助设施只位于 `tests/fixtures/` 与 `tests/support/`，
通过产品公开入口和 `ports.py` 协议单向使用产品代码；产品打包不包含任何测试资产。

生产 Skill scripts 只编译 Agent 决定；共享类型模型和真实校验逻辑由产品包提供，避免
脚本复制一套会漂移的 schema。另有开发脚本可以放在开发或测试目录，用于原型、fixture
和人工调试。

满足下列任一条件的逻辑必须进入有类型 Tool 或其内部模块，而不是留在 Skill script：

- 决定允许哪些文档变化；
- 判定是否发生误伤；
- 定义槽位和 artifact 格式；
- 决定 candidate 是否能发布为 frozen。

两个编译器的 Code Gate 直接调用 CLI，覆盖 canonical 输出、schema 版本、无部分写入、非法
`removal_mode`/ref、语义字段混层、未决内容删除、存续责任未迁移、未获授权的 fixed 删除、
review 证据未覆盖、跨 snapshot 引用、操作依赖顺序和退出码。是否拆分内部 helper 测试不构成
额外验收层。

## 9. 最小验证集

### 9.1 Tool / Code Gate

测试直接调用五个公开 Tool 和两个编译器，不启动 Agent。至少覆盖：

- 不可变 snapshot/hash、旧引用拒绝和查询返回全部同文候选；
- 每个已经纳入当前实现的删除模式，其保留/删除边界与失败不发布；
- 槽位唯一性及 fixed/fill/generate、cardinality/condition/handling、resolution、manual/gap
  等 schema 的合法/非法输入；
- expected/unexpected diff、分节/表格/固定内容误伤和自动图片范围；
- mutation/final 两种 review mode、图片 cursor 无重复无缺页和精确 hash 全页覆盖；
- build 只能产生 candidate；
- freeze 独立发现 hash 不一致、旧快照、缺页审查、blocking finding 和来源变化。
- candidate/frozen 的文件集合、manifest 状态、原子目录发布和 `artifact_ref` 可重算。

### 9.2 Agent Gate

Tool / Code Gate 通过后，Agent Gate 只断言：

- 调用满足必要先后依赖，并把当前有效的 ref/hash 传给下一边界；
- Tool 失败或 findings 要求返工时，不把旧 attempt/candidate 当作成功结果，并使用新输出路径
  继续处理；
- 最终形成完整 frozen 文件集合；
- SDK `ResultMessage.structured_output` 中的路径、hash、状态、`artifact_ref` 和
  slot/fixed/manual/gap/unresolved 数量与磁盘产物一致；自然语言摘要不作为机器断言来源。

本 Gate 不评价槽位、来源裁决、删除决定或视觉判断做得好不好，也不建立 transcript golden、
行为 token 或 live/deterministic 双矩阵。

### 9.3 后续独立 Eval（当前不实施）

slot、fixed、manual、gap、unresolved 的语义正确性、学校要求覆盖度、视觉质量及质量层
blocking findings 由后续独立 Eval 负责。当前只保持接口可供该模块读取，不在本方案中实现
case、Gold、评分器或 runner；边界见
[模板提取静态 E2E Eval 顶层设计](../docfit-template-extraction-eval/DESIGN.md)。

## 10. 实施边界

本轮只优化本候选目录，把架构、候选 Skill、scripts/Tool 接口、产物和验证责任定义到可
实施、可验收；不实现两个脚本或五个 Tool，不修改生产 Skill/Tool，也不更新长期文档。
后续获批实现按 `PLAN.md` 的 W0–W5 建立候选并完成验证；只有再次获得用户批准后，才执行
W6，以一个原子切换同步生产注册、权限、Skill、消费方与受影响长期文档。论文转换端的
目标 Tool 面属于另一项设计；本方案不为兼容旧 `docx_*` Tool 扭曲学校模板领域合同。
