# `docfit-school-extract` v2 候选实施与验收计划

> 状态：候选合同已定义到可实施、可验收；尚未实现，也未切换生产。
>
> 本轮唯一允许修改的是本候选目录。生产 Skill、生产 Tool、长期文档和下游转换链均保持
> 不变。

## 1. 本轮权威与裁决顺序

在候选设计优化与后续获批实现期间，本目录是 Agent、Skill scripts、五个领域 Tool、候选/
冻结产物和验证责任的临时权威。不得以现有生产 Skill、旧 Tool 名称、旧产物或长期文档的
既有描述反向削弱本候选合同。

本目录内部按以下顺序裁决：

1. `DESIGN.md`：目标架构、领域边界和不可违反的不变量；
2. `PLAN.md`：实施顺序、文件责任、验收门和发布边界；
3. `TOOL-DESIGN.md` 与 `SCRIPT-DESIGN.md`：五个 Tool、两份决定文件和两个脚本的实现级
   schema、错误、原子性与测试合同；
4. `SKILL.md`：未来生产 Agent 实际读取的操作指导；
5. `references/*.md`：按需加载的判断与编译细节；
6. `evals/evals.json`：Agent 行为场景，不得覆盖确定性合同。

如这些文件互相冲突，先在候选目录内统一合同，再实施；不能借用当前生产实现或长期文档
替任一方“解释通过”。生产切换前再单独把已获批候选合同同步到受影响的长期文档。

## 2. 本轮完成定义

本轮只完成计划，不生产代码。完成时必须同时满足：

- Agent、Skill scripts、Tool、产物和验证方的责任没有重叠或空档；
- 两份 Agent 决定文件和两个编译脚本都有确定的输入、输出、CLI、失败与原子写语义；
- 五个 Tool 都有调用方式、引用绑定、副作用、结果状态和失败不发布语义；
- `candidate` 与 `frozen` 的目录、状态转换和独立验证合同唯一；
- 零修改模板、返工循环、来源变化、旧引用、图片过量和冻结失败都有安全路径；
- 后续实现被拆成有依赖的工作包，每包都有机器可判定的验收项；
- 生产切换、长期文档更新和 M3/真实样本资格不被冒充为本轮完成结果。

## 3. 已固定的系统不变量

### 3.1 责任边界

| 责任 | Agent | Skill scripts | Tool | 验证方 |
|---|---:|---:|---:|---:|
| 判断学校材料语义、来源优先级和冲突 | owner | 不参与 | 只返回事实 | Skill eval |
| 决定存续责任、槽位、manual/gap 和删除意图 | owner | 只校验/编译 | 不推导 | compiler tests + Skill eval |
| 观察 DOCX、解析有效格式和建立稳定 ref | 检查结果 | 不参与 | owner | Tool unit/contract/integration |
| 执行 DOCX 修改并证明原子性 | 决定并复核 | 不参与 | owner | Tool integration |
| 判断视觉结果是否合理 | owner | 只编译判断 | 提供差异和图片 | Skill eval + review contract |
| 生成 candidate | 检查结果 | 编译 artifact spec | owner | build contract |
| 判断 candidate 是否满足机器冻结条件 | 不得绕过 | 不参与 | `template_freeze` owner | freeze integration |
| 确认最终结果可交付 | owner | 不参与 | 不能替代 | live Agent gate |

### 3.2 数据与副作用

- 所有顶层模型使用 `schema_version: 1`；所有 hash 使用小写 SHA-256。
- 所有 ref 对 Agent 不透明，但必须绑定精确文档 hash、任务根和 Tool 管理的证据记录。
- 源文件只读；mutation 只写新 work DOCX；build/freeze 只写新目录，不覆盖源文件或已发布
  目录。
- 编译脚本不读写 DOCX、不调用 Tool、不推导语义、不发布 candidate/frozen。
- `template_mutate` 只执行有文档副作用的 `materialize_slot` 和 `remove_content`。
  `manual_region` 与 `gap` 属于 artifact spec，不伪装成 mutation。
- 每个 mutation plan 的操作按数组顺序执行；`depends_on` 只能引用更早的 operation。删除
  提示前，负责承接其存续责任的槽位必须已经存在或由更早操作创建。
- Tool 调用成功不等于产物可交付；`candidate` 也不等于 `frozen`。

### 3.3 任务目录与引用仓库

五个 Tool 和两个脚本都显式接收 `task_root`。路径可以是绝对路径或相对该根的路径，但经
规范化后必须仍位于当前任务根内：

```text
task-root/
├── input/                         # 源材料，只读
├── work/
│   ├── decisions/                 # Agent 可编辑的 YAML/JSON
│   ├── compiled/                  # 两个脚本的 canonical JSON
│   └── .docfit/template-v1/       # Tool 管理的不可变 snapshot/comparison/render 证据
└── output/                        # frozen artifact 的发布位置
```

Tool 不要求用户直接理解 `.docfit/template-v1/` 的内部布局。每次调用都用同一 `task_root`
解析 opaque ref。ref 记录缺失、hash 不匹配、来自另一任务根或指向已变化文件时，调用失败
且不产生副作用。

## 4. 共享调用与编译合同

### 4.1 Tool 结果状态

所有 Tool 使用同一调用层 envelope：

```yaml
schema_version: 1
call_status: ok | needs_input | error
checks: []
warnings: []
failure: null | {origin, code, retryable, message, suggested_actions}
```

领域状态使用独立字段，不能塞进 `call_status`：

- observe/mutate/compare 成功分别返回 `result_state: observed | mutated | compared`；
- build 成功返回 `artifact_status: candidate`；
- freeze 完成验证后返回 `artifact_status: frozen | blocked` 和 `published: true | false`；
- `artifact_status: blocked` 表示冻结检查完整执行但未通过，不自动等于 Agent 任务阻塞；
- 请求无效、ref 过期或运行故障分别用 `needs_input`/`error`，不得伪装成 `blocked`。

错误消息、检查、日志和报告不得包含凭据或文档正文。

### 4.2 两个 Skill scripts 的统一 CLI

脚本相对于活跃 `SKILL.md` 定位，并作为很薄的入口导入产品包中的共享模型/编译逻辑：
决定文件的完整字段、canonical bytes、拒绝码和 golden tests 见 `SCRIPT-DESIGN.md`。

```text
uv run python <skill-root>/scripts/compile_mutation_plan.py \
  --task-root <task-root> --input work/decisions/mutation-decisions.yaml \
  --output work/compiled/mutation-plan.json

uv run python <skill-root>/scripts/compile_artifact_spec.py \
  --task-root <task-root> --input work/decisions/artifact-decisions.yaml \
  --output work/compiled/artifact-spec.json
```

统一行为：

- 成功退出码 `0`；决定/schema 错误退出码 `2`；环境或 I/O 故障退出码 `1`；
- stdout 只返回不含正文的 JSON 摘要；诊断写 stderr；
- 输出为 UTF-8 canonical JSON：key 排序、无多余空白、非 ASCII 不转义；
- 先在目标目录写临时文件并 `fsync`，完整成功后原子替换；
- 失败不创建部分文件，也不覆盖既有有效输出；
- canonical 输出包含 `schema_version`、编译器版本、输入内容 hash 和所绑定的 snapshot/hash。

### 4.3 mutation plan 的执行约束

`mutation-decisions` 顶层只绑定一个当前 snapshot。每个 decision 记录语义与证据；每个
operation 记录文档副作用。operation 最小字段为：

```yaml
operation_id: slot-title
action: materialize_slot | remove_content
target_ref: opaque-object-ref
expected_fingerprint: <sha256>
depends_on: []
responsibility_refs: [title-fill]
```

仅 `materialize_slot` 可携带完整 slot 语义；仅 `remove_content` 可携带
`removal_mode`、`migrated_responsibility_refs` 和 `migration_targets`。编译器必须拒绝：

- 删除操作早于它依赖的槽位创建；
- 环依赖、向后依赖、重复 ID 或跨 snapshot ref；
- 把 page/bbox/裸文本当 locator；
- 非删除动作携带删除字段；
- unresolved 的破坏性删除；
- 存续责任没有已存在或更早创建的迁移目标；
- 未获当前任务授权的 fixed 删除。

### 4.4 artifact spec 内嵌 review record 的覆盖约束

`template_compare` 支持两种创建模式：

- `mutation_review`：绑定 before/after snapshot 与 mutation ref，自动选择风险相关图片；
- `final_review`：只绑定最终 snapshot，生成该精确 hash 的逐页权威图片清单。

两种结果都持久化为 immutable `comparison_ref`。图片通过同一 Tool 的读取动作按批返回，
每批受 Agent Tool 传输上限约束，并带 `next_cursor`；不能因为长文档图片过多而跳过全页
审查。

Agent 把完整 mutation/comparison evidence chain、最终 `comparison_ref` 和逐项 disposition
直接写入 `artifact-decisions.yaml`。`compile_artifact_spec.py` 读取 Tool 管理的不可变证据，
先在内部构造并验证 typed `ReviewRecordV1`，再把规范化 `review_record` 嵌入
`artifact-spec.json`；不生成独立 `review-decisions.yaml` 或 `review-record.json`。只有当
所有 required image/finding ref 均有 Agent disposition、mutation lineage 没有未审查边、
且最终全页记录来自同一 hash 时，artifact spec 才能生成。

Tool 的机器 finding 使用 `machine_blocking: true | false`；Agent 的判断使用
`disposition: accepted | blocking | needs_edit`。Agent 不能用 `accepted` 清除机器 blocking，
只能通过新修改和新 comparison 使其消失。

## 5. 五个 Tool 的可实施接口

下列是 v1 的逻辑输入。公开 schema 使用扁平对象和 `action` 鉴别，运行时做 action-specific
校验；完整字段、envelope、错误码、图片 cursor 与逐 Tool 测试见 `TOOL-DESIGN.md`。
公开 schema 不依赖 `oneOf`/`anyOf`/`allOf`。

| Tool | action/核心输入 | 成功产物 | 失败副作用 |
|---|---|---|---|
| `template_observe` | `create`: `task_root,input_docx,visual_level,focus`; `query`: `snapshot_ref,query`; `images`: `snapshot_ref/render_ref,cursor/pages` | immutable snapshot、对象 refs、可选权威 render | 无 |
| `template_mutate` | `task_root,input_docx,output_docx,mutation_plan_path` | 新 DOCX、after snapshot、mutation ref | 不发布 output DOCX |
| `template_compare` | `create`: mutation review 用 `before_snapshot_ref,after_snapshot_ref,mutation_ref`，final review 用 `final_snapshot_ref`；`images`: `comparison_ref,cursor/pages` | immutable comparison、结构差异、分批原生图片 | 无 |
| `template_build` | `task_root,final_snapshot_ref,artifact_spec_path,candidate_output_dir` | 原子发布 candidate 目录 | 不发布目录 |
| `template_freeze` | `task_root,candidate_dir,frozen_output_dir` | 原子发布 frozen 目录 | `published: false`，不发布目录 |

视觉等级固定为：

- `none`：只建立结构证据，不能满足 build/freeze 的最终视觉覆盖；
- `quick`：复用确定性编辑反馈渲染，仅用于返工；
- `authoritative`：使用固定候选交付渲染路由，可计入最终逐页审查；
- 同一文档 hash、render intent 和 provider 版本命中缓存时不得重复外部转换；缓存 miss 才能
  发起一次外部转换。

`template_mutate` 必须验证 input DOCX hash 等于 mutation plan 的 snapshot hash，按顺序在
临时副本执行全部操作，重开 DOCX 并完成后置检查后才原子发布 output。任何一步失败时，
原 input 与目标 output 都保持不变。

## 6. candidate 与 frozen 的唯一合同

### 6.1 Candidate

`template_build` 在相邻临时目录完成全部文件后原子 rename；目标目录已存在时失败，不合并
也不覆盖：

```text
candidate-template-artifact/
├── clean-template.docx
├── template-artifact.json        # artifact_status: candidate
├── visual-review.json
└── build-report.json
```

`template-artifact.json` 至少包含 artifact/schema 版本、模板/source hash、fixed regions、
slots、manual regions、gaps、样式 claim/conflict、unresolved 项、review record hash 和语义
payload hash。`visual-review.json` 保存逐页 review disposition、图片 hash 和受控 evidence ref，
不嵌入文档正文。

这里的“可独立消费”指下游只凭 frozen 目录即可解析槽位并安全填写，不依赖 work evidence
store。`visual-review.json` 中的 evidence ref 只用于冻结时追溯；下游语义不得依赖 ref 仍可
解析。本产物不是完整图片证据归档，避免把长文档逐页图片永久复制进交付目录。

### 6.2 Frozen

`template_freeze` 不复用 build 的“通过”结论。它重开 candidate、重算所有文件 hash、重解
自动 locator、核对 source/current hash、final review 覆盖和 blocking findings，在新的
临时目录构造 frozen：

```text
frozen-template-artifact/
├── clean-template.docx
├── template-artifact.json        # artifact_status: frozen
├── visual-review.json
├── build-report.json
└── freeze-report.json
```

其中 DOCX、visual review 和 build report 与 candidate 对应文件字节一致；freeze 只重建
manifest 的生命周期/冻结字段并新增 freeze report。final manifest 只记录
`freeze_report: freeze-report.json`，不嵌入 `artifact_ref`，避免自引用。

`freeze-report.json` 包含每个 payload 文件 hash、执行过的检查、source hash、candidate
manifest hash、frozen manifest hash、`artifact_ref` 和发布时间。`artifact_ref` 的 preimage
是排序后的四个 payload 文件 hash，以及把 `artifact_ref` 字段暂时省略后得到的规范化
freeze-report payload hash；最终 freeze-report 文件自身不直接进入 preimage。验证者用同样
的“省略字段后重算”规则复算，合同中不存在自引用 hash。

冻结失败时 candidate 保留供诊断，frozen 目标不存在。已存在的 frozen 目标绝不覆盖。

## 7. 可复用现有能力与替换边界

当前代码已经提供可复用的底层能力，但它们不决定候选公开合同：

| 现有能力 | 后续实现如何利用 |
|---|---|
| task-root 路径规范化、SHA-256、canonical JSON、原子文件写 | 下沉为候选共享 runtime，不复制第二套 |
| OfficeCLI inspect/edit/validate 与 Adobe 渲染/cache | 作为五个领域 Tool 的内部适配器，不暴露 backend selector |
| DOCX package、OOXML、对象 ref、图片和布局模块 | 复用底层事实与修改原语，新增 template 领域规则 |
| MCP Tool 注册、扁平 schema 和错误 envelope 测试 | 扩展为五个候选 Tool 的合同测试 |
| Skill/eval/doctor/live smoke 测试骨架 | 改造为候选 Skill 的静态、场景和 live Agent gate |

旧的五个 `docx_*` Tool、旧只读 school-extract Skill 和旧产物 schema 不作为兼容目标。
生产切换前保持它们不变；切换时用一个受控变更同时替换注册、权限、Skill 与消费方。

## 8. 实施工作包

### W0：共享模型与 fixture 合同

负责范围：`src/docfit/template/` 的版本化模型/validator/runtime，及 template fixtures。

产出：

- snapshot/object ref、decision、operation、comparison、review、artifact、report 模型；
- 统一 hash、canonical JSON、task-root 和原子目录发布 helper；
- 覆盖普通段落、混合 run、表格、内容控件、字段、分节/页眉页脚、重复文本和损坏 DOCX 的
  最小 fixture 集。

验收：模型 round-trip 稳定；非法组合全部 fail closed；canonical bytes/hash 固定；临时文件/
目录清理测试通过。

### W1：两个决策编译器与 Skill 入口

依赖：W0。

负责范围：产品包编译逻辑、候选 Skill 的两个薄脚本及 compiler tests；内部保留 typed
`ReviewRecordV1` validator，但不暴露第三个脚本或第三份 Agent 决定文件。

验收：

- 本 Plan 4.2 的 CLI/退出码，以及 4.3/4.4 的拒绝矩阵全部有测试；
- 同一输入重复编译得到逐字节相同输出；
- 验证失败不覆盖旧输出；
- 脚本在安装后的 Skill 路径运行，且不需要从源码仓库导入私有文件。

### W2：observe + mutate

依赖：W0；可与 W1 并行到共享模型冻结为止。

负责范围：snapshot store、观察/query/image batching、两类 mutation action 及注册 schema。

验收：

- 重复文本返回全部候选；旧/跨任务 ref 拒绝；源 DOCX 不变；
- 六种 removal mode 的保留边界和 materialize-slot 顺序均由 fixture 证明；
- 前置/后置检查任一失败都没有 output；
- quick/authoritative cache key 和外部转换次数可观察且可断言。

### W3：compare + review evidence

依赖：W0、W2。

负责范围：mutation/final 两种 review mode、结构/视觉差异、comparison store 和图片分批。

验收：

- 每个 operation 都能对账 expected change；计划外分节、表格、fixed、页数变化被标记；
- 风险范围选择正确，final review 精确覆盖当前 hash 的全部页面；
- 超过单次传输预算时可用 cursor 无重复、无缺页地读完；
- 旧 comparison/image ref 不能满足新 hash 的审查。

### W4：build + freeze

依赖：W0、W1、W3。

负责范围：candidate 编译、artifact manifest、独立 freeze 和原子目录发布。

验收：

- build 永远只产生 candidate；冻结是唯一产生 frozen 的入口；
- hash/source drift、重复/不唯一槽位、缺页审查、blocking finding、旧 snapshot 和目录缺件
  各自阻止发布；
- candidate/frozen 文件集合与第 6 节逐字一致；
- freeze 失败时 candidate 可诊断，frozen 目录不存在；成功时 `artifact_ref` 可重算。

### W5：Agent Skill、eval 与集成链

依赖：W1–W4。

负责范围：候选 `SKILL.md`/references 的最终运行校准、eval fixture/runner、端到端 Agent gate。

验收：

- `evals/evals.json` 每个场景都有 required/forbidden behavior 的机器断言；
- Agent 能完成正常模板、零 mutation 模板和至少一次 compare/freeze 返工链；
- 任一 Tool `ok`、candidate 或局部图片审查都不会被报告为 frozen；
- 最终回复包含 frozen 路径、template hash、slot/manual/gap 摘要；
- deterministic 与 live gate 均通过，但不把此结果称为 M3 Eval 或真实样本资格。

### W6：原子生产切换与文档对齐

依赖：W0–W5 全绿；需要用户再次批准。

负责范围：替换生产 Tool 注册、权限/观测映射、生产 Skill、下游调用与长期文档。

验收：安装包只携带一份生产 `docfit-school-extract`；Agent 可调用的 Tool 面与候选一致；
doctor、权限、隐私、完整单测/合同/集成/live smoke 全绿；所有受影响长期文档在同一变更中
对齐。W6 不属于本轮修改范围。

## 9. 依赖与并行策略

| 工作包 | 模块范围 | 依赖 | 执行方式 |
|---|---|---|---|
| W0 | template models/runtime + fixtures | — | 首先完成 |
| W1 | compilers + Skill scripts | W0 models | 模型冻结后独立 lane |
| W2 | observation/mutation + MCP schema | W0 models | 模型冻结后独立 lane |
| W3 | comparison/render evidence | W2 | W2 后 |
| W4 | artifact/validation | W1 + W3 | 汇合后 |
| W5 | Skill/eval/integration | W1–W4 | 核心实现后 |
| W6 | production/docs | W0–W5 + 用户批准 | 单独原子切换 |

可以并行启动 W1 与 W2，但两者不得各自复制 shared models。W3 依赖 W2 的 snapshot/mutation
事实；W4 同时依赖 compiler 与 final review；W5/W6 顺序执行以避免测试目标漂移。

## 10. 验收矩阵

| 验收层 | 证明什么 | 必须通过 |
|---|---|---|
| Unit | 模型、compiler、ref、删除原语、diff、manifest、freeze check 的每个分支 | 全部 |
| Contract | 五个 Tool 名称/扁平 schema、结果 envelope、Skill 路由、脚本 CLI、artifact 文件集 | 全部 |
| Integration | fixture DOCX 从 observe→mutate→compare→build→freeze 及各失败不发布路径 | 全部 |
| Packaging/doctor | 安装后能找到 Skill、references、scripts 和共享产品包 | 全部 |
| Deterministic Agent eval | 10 个候选场景的 required/forbidden 行为 | 10/10 |
| Live Agent smoke | 正常、询问用户、拒绝危险删除、返工、零 mutation、图片分批 | 全部 |
| Full regression | `ruff`、`mypy`、全量 pytest、build、doctor | 全部 |

候选实现固定使用以下测试落点；实施者可以在同一目录内细分文件，但不能把对应责任移出
这些 test tier：

```text
tests/
├── fixtures/template_v1/                         # W0 DOCX/source/corruption fixtures
├── unit/template/                                # models/runtime/compilers/五个领域模块
├── contract/test_template_tool_contract.py       # 五 Tool 名称、扁平 schema、结果 envelope
├── contract/test_template_skill_scripts_contract.py
├── contract/test_template_artifact_contract.py
├── integration/test_template_artifact_flow.py    # 正常、零 mutation、返工和失败不发布
└── evals/
    ├── test_school_extract_v2_candidate.py        # 10 个 deterministic transcript assertions
    └── test_school_extract_v2_candidate_live.py   # live Agent smoke
```

实现完成时至少运行：

```bash
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
```

W1–W5 的定向验收命令固定为：

```bash
uv run pytest -q tests/unit/template \
  tests/contract/test_template_tool_contract.py \
  tests/contract/test_template_skill_scripts_contract.py \
  tests/contract/test_template_artifact_contract.py \
  tests/integration/test_template_artifact_flow.py
uv run pytest -q tests/evals/test_school_extract_v2_candidate.py
uv run pytest -q -m live tests/evals/test_school_extract_v2_candidate_live.py
```

这些测试文件和命令在实现前不存在是预期状态；W5 完成时必须存在并全绿，不能用人工口头
检查或另一个未记录命令替代。

## 11. 关键失败路径与可见结果

```text
decision 编译失败 ─→ 无 canonical 输出 ─→ Agent 修正决定/证据
stale/ambiguous ref ─→ 无新 DOCX       ─→ 重新 observe 并重编译
post-check 失败     ─→ 无新 DOCX       ─→ 缩小/调整 operation
unexpected diff    ─→ comparison 保留  ─→ Agent 修正并新建 mutation cycle
审查缺页/跨 hash   ─→ 无 artifact spec ─→ 补齐精确 hash 的 final review/dispositions
build schema 失败  ─→ 无 candidate     ─→ 修正 artifact decisions
freeze check 失败  ─→ candidate 保留、无 frozen ─→ 回到对应阶段返工
缺用户裁决/授权    ─→ Agent 报告真实阻塞和所需输入，不发布 candidate
```

任何“无输出”都必须由测试确认目标路径不存在或保持原有效内容；不能只断言返回了错误码。

## 12. 不在本轮范围

- 实现 `src/docfit/template/**`、两个生产脚本或五个 Tool；
- 修改 `.claude/skills/docfit-school-extract/**` 等生产 Skill；
- 修改现有 Tool 注册、权限、观测、CLI、转换链或包发布配置；
- 更新 `docs/docfit-00-index.md` 至 `docs/docfit-06-development-roadmap.md`；
- M3 Eval、授权/去标识真实样本资格、Gold、外部人工评审；
- 为旧 `docx_*` Tool 或旧 school-extract 产物提供兼容层；
- 定义论文内容填充端的新 Tool 面。

## 13. 开始实施的准入条件

只有以下条件满足后才能从 W0 开始：

- 用户确认本目录作为候选实施权威；
- `DESIGN.md`、本 Plan、`SKILL.md` 与 references 的字段/状态/产物名称一致；
- W0–W6 的范围与顺序获批；
- 明确本次批准是开始候选实现，还是连同 W6 生产切换一起批准。

没有新的用户批准，本轮在文档验收后结束。
