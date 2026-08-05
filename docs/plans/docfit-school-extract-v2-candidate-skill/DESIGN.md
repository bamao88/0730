# `docfit-school-extract` 绿地重设计方案

> 状态：目标合同已确定，尚未实现。本文只描述新的生产设计，不承担旧 Tool、旧 Skill
> 或旧产物的兼容迁移。

## 1. 设计结论

`docfit-school-extract` 把当前任务中的学校模板与文字要求整理为一个可独立消费的冻结模板产物：

```text
frozen-template-artifact/
├── clean-template.docx
├── template-artifact.json
├── visual-review.json
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

生产 Skill 包含三个确定性“决策编译”脚本，把 Agent 的语义判断规范化为 Tool 可稳定
消费的 typed JSON：mutation plan、visual review record 和 artifact spec。脚本不读取或
修改 DOCX，不替 Agent 做语义判断，也不发布 candidate/frozen；五个 Tool 仍是文档事实、
副作用、对账和冻结的权威边界。

## 2. 四类资产各自负责什么

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
  → Skill script 编译 review record 与 artifact spec
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
8. 把视觉解释编译为 review record，把最终内容责任编译为 artifact spec；只将这些绑定
   已确认最终快照的结构化输入交给 build。build/freeze 拒绝时根据 findings 返回对应环节
   修正；只有独立冻结通过且 Agent 确认最终结果正确后才交付 frozen artifact。

## 4. 三个生产 Skill 脚本

三个脚本随 Skill 发布，由 Agent 在当前任务 work 目录中运行。它们使用与 Tool 共享的
版本化类型模型，输入支持人可编辑的 YAML/JSON，输出为 canonical JSON；验证失败时不
覆盖旧输出，也不生成部分文件。

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
删除。

### 4.2 `compile_review_record.py`

输入是 `template_compare` 的结构化结果和 Agent 写出的 `review-decisions.yaml`。每项判断
必须引用 comparison finding 或原生图片证据，并给出 `accepted | blocking | needs_edit`
及理由。

脚本检查 before/after snapshot 绑定、必需图片均有判断、blocking finding 未被静默清除、
最终页面覆盖属于同一 hash，并输出 `review-record.json`。脚本只记录 Agent 判断，不决定
视觉结果是否正确。

### 4.3 `compile_artifact_spec.py`

输入是最终 snapshot、内容责任/来源/样式决定、槽位、fixed/manual/gap 清单和
`review-record.json`。脚本检查 `slot_id` 唯一、责任和内容种类/基数完整、来源与样式状态
可追溯、manual/gap 显式、所有 ref 属于最终 snapshot，并输出 `artifact-spec.json`，供
`template_build` 直接消费。

脚本输出不是权威事实。`template_mutate` 和 `template_build` 必须按自己的 typed schema
再次验证；`template_freeze` 更不能相信脚本的成功返回。

## 5. 五个生产 Tool

### 5.1 `template_observe`

职责是建立不可变模板证据快照，或查询已有快照。

新观察的核心输入：

```yaml
input_docx: school-template.docx
visual_level: quick | authoritative | none
focus: [structure, visible_objects, styles, slots]
```

查询已有快照的核心输入：

```yaml
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

### 5.2 `template_mutate`

职责是安全执行 Agent 已经决定、并由 `compile_mutation_plan.py` 编译的显式操作计划。

```yaml
snapshot_ref: ...
input_docx: work-v1.docx
output_docx: work-v2.docx
operations:
  - operation_id: clean-title
    action: remove_content
    target_ref: ...
    removal_mode: clear_text_preserve_container
    expected_text: 请填写论文标题
  - operation_id: slot-title
    action: materialize_slot
    target_ref: ...
    slot_id: thesis_title
    expected_content: scalar
    cardinality: {min: 1, max: 1}
```

删除模式固定为：

- `clear_text_preserve_container`
- `remove_inline_fragment`
- `remove_container`
- `remove_bounded_block`
- `clear_cell_preserve_grid`
- `unwrap_control_preserve_content`

槽位动作覆盖既有段落、表格单元格、段落流边界、物理锚点以及 manual 区域登记。

Tool 校验引用属于当前快照、expected text/fingerprint 成立；全部操作原子执行；修改后重新
打开 DOCX，确认需保留的容器与非目标内容；成功返回新 hash、after snapshot 和
`mutation_ref`。任何前置或后置检查失败时不发布输出。Tool 不替 Agent 选择目标、模式或
槽位语义。

### 5.3 `template_compare`

职责是把修改计划与实际前后变化对账，并把 Agent 需要看的原生图片直接放入结果。

```yaml
before_snapshot_ref: ...
after_snapshot_ref: ...
mutation_ref: ...
visual_scope: automatic
```

它比较对象增删改、固定文字、样式签名、表格网格、节、页眉页脚、分页边界、槽位容器、
页数和视觉布局。输出分为：

- `expected_changes`：能够与 operation 对上的变化；
- `unexpected_changes`：计划外变化及其 blocking 属性；
- `visual_review`：选择图片的原因和前后 crop、整页或 contact sheet。

图片范围由变化风险确定：短文字清空看 crop 与修改后整页；段落删除看目标页及相邻页；
连续块或表格删除看前后 contact sheet 与边界页；分节、页眉页脚、分页或页数变化扩大到
相关 section；映射失败扩大检查范围；最终检查覆盖全部页面。

Tool 不输出视觉 `pass`/`fail`。是否合理仍由 Agent 结合语义和图片判断。

### 5.4 `template_build`

职责是把 Agent 已确认、并由 `compile_artifact_spec.py` 编译的最终快照与语义判断编译成
候选产物。

```yaml
final_snapshot_ref: ...
sources: [...]
fixed_regions: [...]
slots: [...]
manual_regions: [...]
gaps: [...]
visual_findings: [...]
```

Tool 生成规范槽位 manifest，绑定最终模板 hash，检查重复 `slot_id`、字段完整性和引用
时效，记录样式观测与来源，并输出：

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

成功返回 `status: frozen`、`artifact_ref` 和 `template_sha256`。失败返回
`status: blocked`、`published: false` 和 findings，不发布半成品。只有这个 Tool 能把
`candidate` 变为 `frozen`。

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
- build 与 freeze 结果。

逻辑责任不能被物理分页替代；源模板中的示例数量不能自动成为重复区域的实例基数；
生成对象不能退化为当前缓存结果。

## 7. Skill、scripts 与 references 目录

唯一候选目录为：

```text
docs/plans/docfit-school-extract-v2-candidate-skill/
├── DESIGN.md
├── SKILL.md
├── evals/
│   └── evals.json
├── scripts/
│   ├── compile_mutation_plan.py
│   ├── compile_review_record.py
│   └── compile_artifact_spec.py
└── references/
    ├── decision-compilation.md
    ├── template-semantics.md
    ├── deletion-and-slot-decisions.md
    ├── style-reconciliation.md
    └── visual-regression.md
```

五份 reference 分别负责：

- `decision-compilation.md`：三份 Agent 决策输入、脚本调用、canonical 输出和失败语义；
- `template-semantics.md`：内容责任、逻辑单元、说明语义迁移、复合/生成对象和来源冲突；
- `deletion-and-slot-decisions.md`：删除模式、选择条件、槽位内容种类、基数、manual/gap；
- `style-reconciliation.md`：命名/直接/继承/有效格式，以及文字要求与模板事实的交叉验证；
- `visual-regression.md`：预期与意外变化、图片范围、Agent 视觉解释和最终全页审查。

主文件直接给出通用操作方法、脚本使用点和高频判断规则；只有遇到相应问题时才加载
reference。references 不保存学校具体要求，不复述完整 Tool schema，也不提供 Tool
路由/错误恢复手册。

## 8. 实现形态

生产 Tool 的内部实现可以按职责拆分：

```text
src/docfit/template/
├── observation.py
├── mutation.py
├── comparison.py
├── artifact.py
└── validation.py
```

生产 Skill scripts 只编译 Agent 决定；共享类型模型和真实校验逻辑由产品包提供，避免
脚本复制一套会漂移的 schema。另有开发脚本可以放在开发或测试目录，用于原型、fixture
和人工调试。

满足下列任一条件的逻辑必须进入有类型 Tool 或其内部模块，而不是留在 Skill script：

- 决定允许哪些文档变化；
- 判定是否发生误伤；
- 定义槽位和 artifact 格式；
- 决定 candidate 是否能发布为 frozen。

Skill script tests 还要覆盖 canonical 输出、schema 版本、无部分写入、非法
`removal_mode`/ref、语义字段混层、非删除动作携带删除模式、删除动作缺少模式、未决内容
删除、存续责任未迁移、未获授权的 fixed 删除、槽位字段缺失、review 证据未覆盖、跨
snapshot 引用和 blocking finding 保留。

## 9. 最小验证集

Tool contract tests 至少覆盖：

- 不可变 snapshot/hash、旧引用拒绝和查询返回全部同文候选；
- 六种删除模式的保留/删除边界与失败不发布；
- 槽位唯一性、内容种类、fixed/fill/generate kind、cardinality/condition/handling、
  resolution、manual/gap 和复合/生成机制；
- expected/unexpected diff、分节/表格/固定内容误伤和自动图片范围；
- build 只能产生 candidate；
- freeze 独立发现 hash 不一致、旧快照、缺页审查、blocking finding 和来源变化。

Skill eval 至少观察 Agent 是否：

- 在删除说明前迁移其中有效约束；
- 面对多个“标题”候选时使用上下文和样式事实而不是随意选择；
- 面对文字要求与有效格式冲突时显式保留冲突或询问用户；
- 选择与意图匹配的删除模式和槽位语义；
- 阅读 compare 返回的原生图片并解释变化；
- 不把 candidate、局部视觉检查或 Tool 成功自报成 frozen。
- 在 mutate/compare/build/freeze 返回错误或不符合目标的结果后继续诊断和修正，而不是
  把 Tool finding 直接交付给用户。

## 10. 实施边界

本次提交只确定长期架构、候选 Skill、scripts 接口和 references，不实现三个脚本或五个
Tool，也不切换当前生产 Skill。后续实现应先冻结共享 typed schema，再实现三个决策编译
脚本和五个 Tool，完成 script/Tool contract tests，最后以一次原子变更替换生产 Skill。
论文转换端的目标 Tool 面属于另一项设计；本方案不为兼容旧的 `docx_*` Tool 而扭曲学校
模板领域合同。
