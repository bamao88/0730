# `docfit-school-extract` v2 候选实施与验收计划

> 状态：候选合同已定义到可实施、可验收；尚未实现，也未切换生产。
>
> 本轮唯一允许修改的是本候选目录。生产 Skill、生产 Tool、长期文档和下游转换链均保持
> 不变。获批后的纵向 TDD 顺序、目标文件目录和逐阶段测试标准见
> `TDD-IMPLEMENTATION-PLAN.md`。

## 0. 用户已确认的控制原则（修改下文前必查）

本节记录本轮对话中已经确认的产品与工程原则，是本候选目录的最高约束。修改本 Plan
后续章节、`DESIGN.md`、`TOOL-DESIGN.md`、`SCRIPT-DESIGN.md`、
`TDD-IMPLEMENTATION-PLAN.md`、候选 `SKILL.md` 或 references 前，必须先逐项检查是否与
本节冲突；如有冲突，应修改或延期下层内容，不能用实现细节反向解释本节。

### 0.1 阶段与产品尺度

- 当前仍是研发设计阶段。本轮只把候选合同整理到足以开始实现，不生产代码、不切换生产，
  也不提前建设尚未需要的扩展系统。
- DocFit 当前是轻量产品。只保留直接保护用户结果和实施正确性的设计；不为假设中的规模、
  长文档、第三方消费者或未来评测提前增加工作流、兼容层、复杂测试矩阵和性能体系。
- 外部评审建议分阶段处理，不要求一次性采纳。当前只修复会让实施者无法确定行为的合同
  冲突，以及本节规定的测试责任；其余建议必须等实现证据或真实需求出现后再决定。
- 下方详细 schema、错误码、fixture 数量、测试文件拆分和性能常量是实现候选，不与本节及
  已批准系统边界冲突时可在实现中小步调整。只有改变产品责任、公开 Tool/编译器边界、
  产物生命周期、失败发布语义或 W6 切换范围时，才需要再次提交用户批准。

### 0.2 分阶段落地

1. **当前设计整理**：统一五个 Tool、两个编译器、candidate/frozen 和测试责任的硬冲突；
   不实现代码，不更新 00–06。
2. **实现起步**：先以一个已干净模板跑通零 mutation 的最小链路，验证 ref/hash、最终审查、
   build、freeze 和原子发布。它是 W1–W4 内部的首个纵向结果，不新增 W0.5、状态机或审批层。
3. **能力递增**：再按真实产品场景增加 mutation mode、返工路径和对应 Tool/Code 断言；不因
   设计文档列出了候选全集就要求一次实现所有假设分支。
4. **生产切换**：W6 获得单独批准后，一次替换旧 Tool/Skill、所有消费者、测试和 00–06；
   不保留旧别名、双 schema 或并行生产路径，除非届时存在另行批准的真实外部迁移要求。
5. **质量 Eval**：作为后续独立模块实施，不属于本候选实现和当前完成门。

### 0.3 当前测试责任只有两个 Gate

**A. Tool / Code Gate**

直接调用五个公开 Tool 和两个编译器，给定输入验证它们必须产出什么、必须拒绝什么。断言
范围是：输入校验、源文件不变、输出原子性、DOCX 可打开、文件集合完整、schema 合法、
hash/ref/`artifact_ref` 自洽，以及失败不发布半成品。该 Gate 不启动 Agent，也不判断模板
语义或视觉质量。

**B. Agent Gate**

只在 Tool / Code Gate 通过后运行。验证 Agent 满足合同要求的调用先后依赖、传递有效
ref/hash、处理 Tool 失败、生成完整 frozen artifact，并确保最终回复中的路径、hash、状态和
结构化数量与磁盘产物一致。这里断言影响正确性的顺序和结果，不绑定无关的精确调用次数、
完整 transcript 文案或内部思考过程，也不承担最终内容质量评分。

**后续 Quality Eval（当前不做）**

后续独立 Quality Eval 判断 slot、fixed、manual、gap、unresolved 的语义正确性、学校要求覆盖度、
视觉质量和质量层 blocking findings，即判断“这个对象做得好不好”。当前候选不实现 Eval
runner、评分器、Gold、行为 token 或 Eval case 矩阵；其独立顶层边界见
[模板提取静态 E2E Eval 顶层设计](../docfit-template-extraction-eval/DESIGN.md)。

三个责任可简写为：Tool / Code 证明对象合法且过程安全；Agent 证明系统按合同完成任务；
未来 Quality Eval 判断结果质量。

### 0.4 七个产品能力的定义约束

五个公开 Tool 与两个 Skill 内置编译脚本的唯一产品能力合同在 `DESIGN.md` 第 1.1 节。它
逐项固定公开入口、action/mode、必要输入、底层动作、成功产物、关键拒绝和非职责；未列出的
action/mode 默认不支持。五个 Tool 是 Agent 可见的事实、副作用与发布能力；两个脚本是随
Skill 交付的决定预检能力，不是公开 Tool、用户入口或工作流节点。更新下面任何接口、工作包
或测试时，都必须按这些能力项逐项核对。增加、删除、改名或重新分配任一能力属于需用户批准
的产品/架构变更，不能作为字段调整或实现细节处理。

### 0.5 五阶段产品链（阶段不等于五个测试 Gate）

本产品按以下顺序推进：

```text
产品决策 → 能力合同 → Tool 证明 → Agent 编排 → Quality Eval
```

前两个阶段决定“做什么”，中间两个阶段证明“能否按合同工作”，最后一个阶段判断“结果做得
好不好”。当前测试责任仍只有 Tool / Code Gate 与 Agent Gate；产品决策和能力合同不是测试
Gate，Quality Eval 是后续独立质量模块。

| 阶段 | 必须回答的问题 | 权威输入 | 本阶段产物 | 进入下一阶段的条件 | 当前状态 |
|---|---|---|---|---|---|
| 产品决策 | 本次产品切片开放哪些能力、哪些延期、是否改变责任或发布边界 | 用户最新明确决定、当前产品尺度和真实场景 | 本 Plan 第 0 节及明确的增量能力选择 | 范围、非目标、分阶段顺序和需再次批准的变化都清楚 | 当前基线已记录；后续 mutation slice 开始前仍需明确选择本次开放的既有 mode |
| 能力合同 | 每项能力如何进入、能做哪些 action/mode、产出/拒绝什么、谁不负责 | 已确认的产品决策 | `DESIGN.md` 第 1.1 节；`TOOL-DESIGN.md`、`SCRIPT-DESIGN.md` 只做实现级细化 | 每个已选能力都有入口、输入、底层动作、成功产物、关键拒绝和非职责；未列出能力默认不支持 | v1 候选合同已定义，尚未实现 |
| Tool 证明 | 五个 Tool 和两个编译器是否真实符合能力合同 | 已实现的明确能力切片 | Tool / Code Gate 的直接调用证据 | 每个开放 action/mode/CLI 的成功产物与代表性拒绝、不发布断言全绿 | 未开始；由 W0–W4 建设并证明 |
| Agent 编排 | Agent 是否能只使用已证明能力完成任务、处理失败并交付一致结果 | 全绿的 Tool / Code Gate、候选 Skill、测试任务输入 | Agent Gate 证据与完整 frozen artifact | 必要依赖顺序、有效 ref/hash、返工和最终回复/磁盘一致性全绿 | 未开始；由 W5 建设并证明 |
| Quality Eval | frozen artifact 的语义、学校覆盖和视觉质量是否合格 | 已通过前两 Gate 的 frozen 五文件产物，以及后续获批的 Eval case/Gold/质量规则 | 绑定 `artifact_ref`/template hash 的机器质量报告和人工摘要 | 按后续独立 Eval 合同形成质量结论；不能用评分替代前两 Gate | 交接边界在本 Plan 中固定；实现、Gold 和评分仍延期 |

阶段交接固定遵守：

1. 没有产品决策的新增能力，不得直接写进实现；先更新能力合同。
2. 没有能力合同的 action/mode，不得通过 Agent 提示词或脚本旁路实现。
3. Tool / Code Gate 未通过的能力不得进入 Agent Gate；Agent Gate 不重复证明 Tool 内部正确性。
4. 只有完整 frozen artifact 才能进入 Quality Eval；candidate、失败调用或 Agent transcript 不是
   Quality Eval 的替代输入。
5. 后续 Quality Eval 发现问题时，先归因到产品能力缺口、Tool 实现、Agent 判断/编排或
   Eval/Gold 本身，再回到对应阶段修正；不得通过放宽下游评分掩盖上游合同失败。

### 0.6 产品代码与测试代码必须物理解耦

- 产品代码只放在产品包、Tool 注册层和当前候选 Skill 的运行脚本目录；测试代码、fixture、
  fake、测试 builder、断言 helper 和 Agent harness 只放在 `tests/` 下。
- 允许测试代码单向导入产品公开入口；产品代码不得导入 `tests`，不得读取测试 fixture，也
  不得依赖 pytest、测试 fake、golden 路径或仅供测试使用的环境变量才能运行。
- 为可测试性提供的边界必须是具有真实产品意义的依赖注入或 `ports.py` 协议，不能在产品
  API 中增加 `test_mode`、测试专用 action、fake provider selector 或测试后门。
- 测试生成的 DOCX、evidence、candidate/frozen 和临时文件只写 pytest 临时目录或测试工作
  目录，不能写回 `src/`、候选 Skill 或生产资源目录。
- W6 打包结果不得包含 `tests/`、测试 fixture、fake 或 harness；产品需要随包携带的真实
  schema/资源必须拥有独立产品目录和产品用途，不能借用测试资产。
- 物理解耦是代码组织和依赖规则，不新增第三个测试 Gate；其行为证明仍归属于 Tool / Code
  Gate 与 Agent Gate。

## 1. 本轮权威与裁决顺序

在候选设计优化与后续获批实现期间，本目录是 Agent、Skill scripts、五个领域 Tool、候选/
冻结产物和验证责任的临时权威。不得以现有生产 Skill、旧 Tool 名称、旧产物或长期文档的
既有描述反向削弱本候选合同。

本目录内部按以下顺序裁决：

1. 本 Plan 第 0 节：用户已确认的产品尺度、分阶段策略和测试责任；
2. `DESIGN.md`：目标架构、领域边界和不可违反的不变量；
3. 本 Plan 其余章节：实施顺序、文件责任、验收门和发布边界；
4. `TOOL-DESIGN.md` 与 `SCRIPT-DESIGN.md`：五个 Tool、两份决定文件和两个脚本的实现级
   schema、错误、原子性与测试合同；
5. `TDD-IMPLEMENTATION-PLAN.md`：不改变上述合同的纵向开发顺序、目标文件和阶段测试标准；
6. `SKILL.md`：未来生产 Agent 实际读取的操作指导；
7. `references/*.md`：按需加载的判断与编译细节。

如这些文件互相冲突，先在候选目录内统一合同，再实施；不能借用当前生产实现或长期文档
替任一方“解释通过”。生产切换前再单独把已获批候选合同同步到受影响的长期文档。

## 2. 本轮完成定义

本轮只完成计划，不生产代码。完成时必须同时满足：

- Agent、Skill scripts、Tool、产物和验证方的责任没有重叠或空档；
- 五个 Tool 和两个脚本各自有唯一的公开入口、action/mode、必要输入、底层动作、成功产物、
  关键拒绝和非职责；
- 两份 Agent 决定文件和两个编译脚本都有确定的输入、输出、CLI、失败与原子写语义；
- 五个 Tool 都有调用方式、引用绑定、副作用、结果状态和失败不发布语义；
- `candidate` 与 `frozen` 的目录、状态转换和独立验证合同唯一；
- 零修改模板、返工循环、来源变化、旧引用、图片过量和冻结失败都有安全路径；
- 后续实现被拆成可递增的工作包，并由 Tool / Code Gate 与 Agent Gate 验收；
- TDD 子计划按公开行为执行小步 RED→GREEN→REFACTOR，给出目标文件目录、规模约束、每阶段
  目标与测试通过标准，不先水平实现全部底层模块；
- 产品代码与测试代码目录、依赖和打包边界完全分离，测试辅助设施不会进入产品包；
- 产品决策、能力合同、Tool 证明、Agent 编排和后续 Quality Eval 的输入、产物、退出条件与
  交接关系完整，任何下游阶段都不能替代上游责任；
- 生产切换、长期文档更新和 M3/真实样本资格不被冒充为本轮完成结果。

## 3. 已固定的系统不变量

### 3.1 责任边界

| 责任 | Agent | Skill scripts | Tool | 验证方 |
|---|---:|---:|---:|---:|
| 判断学校材料语义、来源优先级和冲突 | owner | 不参与 | 只返回事实 | 后续 Quality Eval |
| 决定存续责任、槽位、manual/gap 和删除意图 | owner | 只校验/编译 | 不推导 | Code Gate；语义质量后续 Quality Eval |
| 观察 DOCX、解析有效格式和建立稳定 ref | 检查结果 | 不参与 | owner | Tool / Code Gate |
| 执行 DOCX 修改并证明原子性 | 决定并复核 | 不参与 | owner | Tool / Code Gate |
| 判断视觉结果是否合理 | owner | 只编译判断 | 提供差异和图片 | 后续 Quality Eval |
| 生成 candidate | 检查结果 | 编译 artifact spec | owner | Tool / Code Gate |
| 判断 candidate 是否满足机器冻结条件 | 不得绕过 | 不参与 | `template_freeze` owner | Tool / Code Gate |
| 按依赖编排、处理失败并确认最终交付 | owner | 不参与 | 不能替代 | Agent Gate |

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

编译器、mutate、build 和 freeze 的输出都采用“目标已存在则不覆盖”。每次返工必须改用一个
新的、尚不存在的 attempt 路径；首次示例中的 `work-v2.docx`、`work/candidate-template-artifact`
和 `output/frozen-template-artifact` 只是示例名，不是所有重试复用的固定地址。attempt 名由
Agent 在当前任务 work/output 范围内选择即可，本方案不增加 attempt registry 或工作流状态机。

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
决定文件的完整字段、canonical bytes、拒绝码和直接编译器断言见 `SCRIPT-DESIGN.md`。

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
`removal_mode` 和 `migration_targets`。编译器必须拒绝：

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
| `template_observe` | `create`: `task_root,input_docx,visual_level,focus`; `query`: `snapshot_ref,query`; `images`: `render_ref,cursor/pages` | immutable snapshot、对象 refs、可选权威 render | 无 |
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

`unsupported_features` 中每项都必须说明受影响对象/范围与 `machine_blocking`。blocking 项不能
进入 mutate/build/freeze；非 blocking 项必须由 Agent 显式归入 manual、gap 或 unresolved，
不能在冻结产物中静默消失。

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
manifest hash、frozen manifest hash、`artifact_ref` 和发布时间。原样保留的
`build-report.json` 只证明 candidate 构建时的四文件 hash；freeze 先用它验证 candidate，再由
`freeze-report.json` 记录生命周期字段变化后的 frozen manifest hash，不能拿 build report 中的
candidate manifest hash 去验证 frozen manifest。`artifact_ref` 的 preimage
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
| 现有 Agent smoke 骨架 | 仅复用运行入口实现轻量 Agent Gate；不沿用 Skill Eval 评分责任 |

旧的五个 `docx_*` Tool、旧只读 school-extract Skill 和旧产物 schema 不作为兼容目标。
生产切换前保持它们不变；切换时用一个受控变更同时替换注册、权限、Skill 与消费方。

## 8. 实施工作包

W0–W6 是责任工作包，不要求按模块水平交付。实际开发按
[`TDD-IMPLEMENTATION-PLAN.md`](TDD-IMPLEMENTATION-PLAN.md) 的 P1–P5 纵向切片推进：公共
模型/runtime 由第一个公开行为按需拉入，每次只为一个失败行为写最小实现；F1 Quality Eval
保持后续独立范围。

### W0：最小共享模型与 fixture 合同

负责范围：`src/docfit/template/` 的版本化模型/validator/runtime，及 template fixtures。

产出：

- snapshot/object ref、decision、operation、comparison、review、artifact、report 模型；
- 统一 hash、canonical JSON、task-root 和原子目录发布 helper；
- 先提供已干净模板、一个需要安全清理的模板和损坏 DOCX 三类最小 fixture；只有后续已批准
  mutation mode 需要时再增加对应结构 fixture。

W0 不作为水平式“先写完全部模型/runtime”的独立阶段，也不建立独立测试 Gate。P1/P2 tracer
按第一个公开行为只加入当前需要的 shared contract/runtime；准备并行 W1/W2 前再稳定当前切片
共用的最小接口。其 round-trip、非法组合、canonical bytes/hash 和临时项清理最终都通过
W1–W4 的直接 Tool / Code 断言证明。

### W1：两个决策编译器与 Skill 入口

依赖：W0。

负责范围：产品包编译逻辑、候选 Skill 的两个薄脚本及 compiler tests；内部保留 typed
`ReviewRecordV1` validator，但不暴露第三个脚本或第三份 Agent 决定文件。

验收：

- 本 Plan 4.2 的 CLI/退出码，以及 4.3/4.4 的拒绝矩阵全部有测试；
- 同一输入重复编译得到逐字节相同输出；
- 验证失败不覆盖旧输出；
- 脚本能从当前候选 `<skill-root>/scripts/` 运行，且不需要从源码仓库外导入私有文件；W6
  再验证生产 Skill 安装路径。

### W2：observe + mutate 递增实现

依赖：W0；可与 W1 并行到共享模型冻结为止。

负责范围：snapshot store、观察/query/image batching、两类 mutation action 及注册 schema。

验收：

- 重复文本返回全部候选；旧/跨任务 ref 拒绝；源 DOCX 不变；
- 首个产品场景需要的 removal mode 与 materialize-slot 顺序由 fixture 证明；其余候选 mode
  按真实场景逐个加入，并在加入时同时开放 compiler/Tool 支持和补齐直接 Tool 断言；
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

### W5：Agent Skill 与 Agent Gate

依赖：W1–W4。

负责范围：候选 `SKILL.md`/references 的最终运行校准，以及轻量端到端 Agent Gate。未来
Quality Eval 不在本工作包内。

验收：

- Agent 满足 observe/compile/mutate/compare/build/freeze 之间必要的先后依赖，不要求无关的
  精确调用次数或逐字 transcript；
- 每个下游调用使用当前有效 ref/hash，返工使用新的未占用输出路径，不混用旧 attempt 证据；
- 至少覆盖一次正常完成和一次可恢复 Tool 失败，失败后能回到对应环节并最终形成完整 frozen；
- 最终回复中的 frozen 路径、template hash、状态及 slot/fixed/manual/gap/unresolved 数量与
  实际文件一致；
- Agent Gate 不输出语义质量分数，也不冒充 M3 Eval 或真实样本资格。

### W6：原子生产切换与文档对齐

依赖：W0–W5 全绿；需要用户再次批准。

负责范围：替换生产 Tool 注册、权限/观测映射、生产 Skill、下游调用与长期文档。

验收：安装包只携带一份生产 `docfit-school-extract`；Agent 可调用的 Tool 面与候选一致；
`convert-thesis`、Tool 注册、权限/观测映射、README、测试和 00–06 全部在同一变更中改用新
合同；doctor、权限、隐私、全量现有回归与本方案两个 Gate 全绿；旧生产 Tool/Skill 路径和
仅服务旧合同的测试被移除。W6 不属于本轮修改范围。

## 9. 依赖与并行策略

| 工作包 | 对应五阶段链 | 模块范围 | 依赖 | 执行方式 |
|---|---|---|---|---|
| W0 | 能力合同的共享实现基础 | template models/runtime + fixtures | — | 随 P1/P2 tracer 按需完成；不形成独立 Gate |
| W1 | Tool 证明 | compilers + Skill scripts | W0 models | 模型冻结后独立 lane |
| W2 | Tool 证明 | observation/mutation + MCP schema | W0 models | 模型冻结后独立 lane |
| W3 | Tool 证明 | comparison/render evidence | W2 | W2 后 |
| W4 | Tool 证明 | artifact/validation | W1 + W3 | 汇合后 |
| W5 | Agent 编排 | Skill + Agent Gate | W1–W4 Tool / Code Gate 全绿 | 核心实现后 |
| W6 | 链外的发布/切换动作 | production/docs | W0–W5 + 用户批准 | 单独原子切换 |

P1 先拉入 W0 的最小公共合同并跨 W1–W4 跑通零 mutation 纵向链路，再由 P2 按已批准场景
补 mutation 和返工分支；这不新增工作包或正式 gate。W1 与 W2 后续可以并行，但并行前需
稳定当前切片共用的 models/runtime，且不得各自复制。W3 依赖 W2 的 snapshot/mutation 事实；
W4 同时依赖 compiler 与 final review；W5/W6 顺序执行。
产品决策与能力合同是 W0 的准入，不另设实现工作包；Quality Eval 使用后续独立计划，也不
伪装成 W7。W6 只负责已证明候选的生产切换，不产生质量评分，也不替代 Quality Eval。

## 10. 两个当前验收 Gate

| Gate | 被测对象 | 只证明什么 | 当前完成门 |
|---|---|---|---|
| Tool / Code Gate | 五个公开 Tool + 两个编译器 | 给定输入的输出/拒绝、源只读、DOCX/文件集、schema、hash/ref 与原子发布 | 所有已实现公开分支通过 |
| Agent Gate | 候选 Agent Skill | 必要调用顺序、有效 ref/hash、失败处理、完整 frozen 和最终回复一致性 | 最小正常场景与可恢复失败场景通过 |

`DESIGN.md` 第 1.1 节是 Tool / Code Gate 的能力覆盖基线。每个已经开放的 Tool action/mode
和两个脚本 CLI 都至少要有一个成功产物断言及一个代表性的拒绝/不发布断言；本节未列出的
action/mode 必须稳定拒绝。候选能力可以分阶段开放，但在其直接断言通过前只能标为未支持，
不能靠 Agent 绕行或静默降级后宣称已支持。

**后续 Quality Eval 的交接合同（不是当前第三个 Gate）**

- 唯一 Actual 输入是前两 Gate 已通过且由 `template_freeze` 发布的五文件目录；
  `clean-template.docx` 是实际模板，`template-artifact.json` 是 slots/fixed/manual/gaps/
  unresolved 的实际结构化合同，`visual-review.json`、`build-report.json` 和
  `freeze-report.json` 提供审查、来源、hash 与 `artifact_ref` 绑定。
- Eval case/Gold、学校要求覆盖规则、视觉判定规则和评分版本属于后续获批 Eval 数据与合同，
  不得从 Agent transcript、work evidence 或当前任务未授权材料临时拼出。
- `visual-review.json` 和 manifest 中的 Agent dispositions 只能作为被测产物事实，不能直接当作
  Quality Eval 的正确结论；Eval 必须依据独立 Gold/规则重新判断语义、覆盖和视觉质量。
- 输出必须至少包含绑定 `artifact_ref` 和 template hash 的机器可读质量结论、分维度 findings
  与人工摘要；评价维度固定覆盖 slot、fixed、manual、gap、unresolved 的语义正确性、学校
  要求覆盖度、视觉质量和质量层 blocking findings。
- Quality Eval 不重新证明 Tool 输入校验、原子性、ref/hash 或 Agent 调用顺序；前两 Gate
  失败时不得通过 Quality Eval 分数补救。
- 现有 `docfit-template-extraction-eval` 顶层设计在真正实施前必须完成一次合同对齐：把其
  “Actual 模板/填写契约”明确映射为上述 frozen 文件，补齐 manual/gap/unresolved 与视觉质量
  维度，并让报告绑定 `artifact_ref`。这项对齐属于后续 Eval 计划，不阻塞当前 W0–W6。

测试按能力拆文件以控制规模，但所有 contract 文件仍共同组成一个 Tool / Code Gate，所有
Agent 文件仍共同组成一个 Agent Gate：

```text
tests/
├── fixtures/template_v1/
├── support/template_v1/
├── contract/template_gate/
│   ├── test_observe.py
│   ├── test_mutate.py
│   ├── test_compare.py
│   ├── test_artifact.py
│   ├── test_compile_mutation.py
│   └── test_compile_artifact.py
└── agent/school_extract_v2/
    ├── test_zero_mutation.py
    ├── test_mutation.py
    └── test_recovery.py
```

内部 helper 的单元测试可以用于定位缺陷，但不是本模块额外的产品 Gate。当前不创建
`tests/evals/`、行为 token、transcript golden、质量分数或 live/deterministic 双矩阵。
测试 fixture、boundary fake、DOCX builder 和断言 helper 只允许位于上述 `tests/fixtures/`
与 `tests/support/`，不得放入 `src/docfit/` 或候选 Skill 运行目录。

实现完成时至少运行：

```bash
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
```

W1–W5 的定向验收命令为：

```bash
uv run pytest -q \
  tests/contract/template_gate \
  tests/agent/school_extract_v2
```

这些文件在实现前不存在是预期状态；W5 完成时必须存在并全绿。仓库已有的全量检查仍在
W6 运行，但不被重新包装为本模块的第三种测试责任。

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
- 实现 `evals.json`、行为 token、transcript golden、语义/视觉评分器或 Eval runner；
- 为旧 `docx_*` Tool 或旧 school-extract 产物提供兼容层；
- 定义论文内容填充端的新 Tool 面。

## 13. 开始实施的准入条件

只有以下条件满足后才能从 W0 开始：

- 用户确认本目录作为候选实施权威，并确认第 0.5 节五阶段产品链；
- `DESIGN.md`、本 Plan、`SKILL.md` 与 references 的字段/状态/产物名称一致；
- 用户确认 `TDD-IMPLEMENTATION-PLAN.md` 的纵向阶段、目标目录和文件规模边界；
- 初始产品切片固定为第 0.2 节的零 mutation 最小链路；开始任何后续 mutation slice 前，必须
  明确记录本次从既有合同中开放的 action/mode 及延期项。若需要新增或改变能力，先回到产品
  决策并更新 `DESIGN.md` 第 1.1 节，不能直接进入实现；
- W0–W6 的范围与顺序获批；
- 明确本次批准是开始候选实现，还是连同 W6 生产切换一起批准。

没有新的用户批准，本轮在文档验收后结束。
