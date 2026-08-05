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

它们分别负责观察、执行修改、前后对账、编译候选产物和独立冻结。Agent 负责材料语义、
删除意图、槽位责任、来源冲突和视觉合理性的判断；Tool 负责可重复的文档事实、修改、
验证和原子发布。

生产 Skill 不包含脚本。原型、fixture 生成和人工调试脚本可以存在于开发目录，但它们
不是 Agent 能力面，不能定义公开合同，也不能成为生产任务的必经步骤。

## 2. 四类资产各自负责什么

| 资产 | 负责 | 不负责 |
|---|---|---|
| Skill | 推荐做法、判断步骤、删除与槽位决策原则、冲突处理、视觉解释、询问用户的时机 | 实现 DOCX 操作、复制 Tool schema、宣称机器验证成功 |
| Tool | 不可变观察、带前置条件的原子修改、结构与视觉差异、候选编译、独立冻结 | 判断哪个“标题”是论文标题、决定说明是否该删、解释版式是否合理 |
| references | 多场景复用但不宜全部放在主文件的判断方法 | 学校事实、Tool 手册、脚本命令、固定工作流状态机 |
| 开发脚本 | 原型验证、fixture 生成、人工调试 | 生产执行、发布、公开合同和 Agent 路由 |

`Skill` 可以明确告诉 Agent 通常先做什么、后做什么，以及每一步的判断标准。这是一种
可调整的操作方法，不是由程序强制的工作流状态机。Agent 可以按证据需要回到观察、修改
或询问用户，但不能绕过冻结验证取得 `frozen` 状态。

## 3. Skill 的推荐操作方法

```text
盘点来源
  → 观察不可变模板快照
  → Agent 分类内容责任并解决关键歧义
  → Agent 选择删除模式和槽位语义
  → Tool 原子修改
  → Tool 对账并返回原生图片
  → Agent 解释视觉结果
  → Tool 编译 candidate
  → Tool 独立验证并发布 frozen
```

Agent 在这个过程中应完成以下工作：

1. 盘点模板、文字要求、官方示例及其来源状态，记录冲突和无法确认的内容。
2. 观察模板结构、可见对象、有效样式、槽位候选和页面证据，不把页码当成编辑身份。
3. 把内容分类为固定内容、待填槽位、生成责任、重复结构、条件区域、人工区域、应删除
   内容或未决内容。
4. 删除说明或示例前，先迁移其中仍需保留的格式、基数、生成机制或填写责任。
5. 将文字要求与模板的最终有效格式交叉验证；冲突不能靠样式名、历史经验或常识消解。
6. 对每个修改给出明确目标、前置指纹、删除模式或槽位合同，然后交给 Tool 执行。
7. 阅读结构差异和 Tool 直接返回的图片，判断变化是合理结果、需要继续修改，还是必须
   询问用户。
8. 只把已经确认的最终快照编译为 candidate；只有独立冻结通过后才交付 frozen artifact。

## 4. 五个生产 Tool

### 4.1 `template_observe`

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

### 4.2 `template_mutate`

职责是安全执行 Agent 已经决定的显式操作计划。

```yaml
snapshot_ref: ...
input_docx: work-v1.docx
output_docx: work-v2.docx
operations:
  - operation_id: clean-title
    action: remove_content
    target_ref: ...
    mode: clear_text_preserve_container
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

### 4.3 `template_compare`

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

### 4.4 `template_build`

职责是把 Agent 已确认的最终快照和语义判断编译成候选产物。

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

### 4.5 `template_freeze`

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

## 5. 冻结产物的最小语义

`template-artifact.json` 的物理 schema 由 Tool 合同定义，长期必须表达以下语义：

- 模板精确 hash 与来源 hash；
- 固定区域及其指纹；
- 自动槽位的 `slot_id`、唯一 locator、内容种类和基数；
- 生成责任、重复责任和条件责任，而不是只保存当前缓存文字；
- manual 区域、gap、冲突和未决项；
- 样式的观测值、要求值、来源、覆盖范围与冲突状态；
- 绑定最终模板 hash 的逐页视觉审查记录；
- build 与 freeze 结果。

逻辑责任不能被物理分页替代；源模板中的示例数量不能自动成为重复区域的实例基数；
生成对象不能退化为当前缓存结果。

## 6. Skill 与 references 目录

唯一候选目录为：

```text
docs/plans/docfit-school-extract-v2-draft/
├── SKILL.md
├── evals/
│   └── evals.json
└── references/
    ├── template-semantics.md
    ├── deletion-and-slot-decisions.md
    ├── style-reconciliation.md
    └── visual-regression.md
```

四份 reference 分别负责：

- `template-semantics.md`：内容责任、逻辑单元、说明语义迁移、复合/生成对象和来源冲突；
- `deletion-and-slot-decisions.md`：删除模式、选择条件、槽位内容种类、基数、manual/gap；
- `style-reconciliation.md`：命名/直接/继承/有效格式，以及文字要求与模板事实的交叉验证；
- `visual-regression.md`：预期与意外变化、图片范围、Agent 视觉解释和最终全页审查。

主文件直接给出通用操作方法和高频判断规则；只有遇到相应问题时才加载 reference。
references 不保存学校具体要求，不复述 Tool schema，也不提供 Tool 路由/错误恢复手册。

## 7. 开发期实现形态

生产 Tool 的内部实现可以按职责拆分：

```text
src/docfit/template/
├── observation.py
├── mutation.py
├── comparison.py
├── artifact.py
└── validation.py
```

开发脚本只允许放在开发或测试目录，用于原型、fixture 和人工调试。满足下列任一条件的
逻辑必须进入有类型 Tool 或其内部模块，而不是留在脚本里：

- 决定允许哪些文档变化；
- 判定是否发生误伤；
- 定义槽位和 artifact 格式；
- 决定 candidate 是否能发布为 frozen。

## 8. 最小验证集

Tool contract tests 至少覆盖：

- 不可变 snapshot/hash、旧引用拒绝和查询返回全部同文候选；
- 六种删除模式的保留/删除边界与失败不发布；
- 槽位唯一性、内容种类、基数、manual/gap 和复合/重复/生成责任；
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

## 9. 实施边界

本次提交只确定长期架构、候选 Skill 和 references，不实现五个 Tool，也不切换当前生产
Skill。后续实现应先冻结五个 Tool 的 typed schema 和 artifact schema，再完成 Tool contract
tests，最后以一次原子变更替换生产 Skill。论文转换端的目标 Tool 面属于另一项设计；本
方案不为兼容旧的 `docx_*` Tool 而扭曲学校模板领域合同。
