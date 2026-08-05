# `docfit-school-extract` v2 实施草案

> 状态：设计草案，未进入生产 Skill
> 日期：2026-08-05
> 长期合同：`docs/docfit-00-index.md` 至 `docs/docfit-06-development-roadmap.md`

## 1. 目标

把当前“只读学校材料证据提取”改造成“冻结模板产物生产”能力：读取当前任务的学校
模板、书面要求和可选官方示例，在不覆盖来源文件的前提下，交付一份可重复填充的干净
模板，以及描述该模板接口的槽位索引。

本方案不直接替换生产 Skill。当前应用仍使用旧 P1/M2 合同；只有现有五个 Tool、应用壳、
转换消费者和普通产品门同时具备新能力后，才能原子切换。

## 2. 用户目标与触发边界

应触发：

- 清理、规范、解释或冻结学校论文模板；
- 把模板、要求和官方示例整理成可供后续转换使用的模板接口；
- 识别学校固定内容、可填责任、生成/重复区域、条件区域和人工区域；
- 对既有冻结模板进行审计，或在模板修改后重新冻结。

不应触发：

- 把学生论文内容填入模板；
- 转换或排版学生论文；
- 单纯检查一份已经生成的学生论文；
- 创建跨任务学校 profile、学校 Knowledge、模板注册表或共享学校数据库。

## 3. 输入与稳定产物

输入：

- 必需：学校模板 DOCX；
- 必需：当前适用的书面要求或等价正式材料；
- 可选：官方示例、适用范围说明和用户确认。

稳定交付只有两个：

1. 可独立打开且不再原地修改的冻结干净模板 DOCX；
2. 绑定冻结模板精确 SHA-256 的槽位索引。

槽位索引不是“空白位置列表”，而是冻结模板的消费接口。它同时表达固定、填充、生成、
重复、条件、人工和未决责任。来源、冲突、验证摘要和 gap 都是索引内容或工作目录证据，
不增加第三种稳定交付。

候选物理形态：

```text
output/template-artifact/
├── clean-template.docx
└── slot-index.json
```

产物只在当前任务内有效，不包含学生内容，也不自动晋升为产品 Knowledge。

## 4. 冻结的 Interface 语义

这里先冻结消费者真正依赖的语义，不提前锁死所有 JSON 字段：

- 模板 DOCX 可独立打开，并以精确 hash 标识；
- 索引只描述该 hash 对应的模板；模板字节变化后旧索引失效；
- 固定区域与可处理区域可以区分，转换端没有当前证据时不得修改固定内容；
- 自动处理区域具有任务内唯一 ID、最终快照中的唯一定位、期望内容形态和基数；
- 生成区域保留生成关系，不被压成静态文本槽位；
- 重复区域表达可变数量，不把源示例数量冻结成最终实例数量；
- 条件区域记录适用条件；条件未知时不静默删除；
- 签字、盖章、审批等人工责任显式存在，不伪装成自动槽位；
- 无法安全表达的区域进入未决或 gap，不从索引中消失；
- 文字材料声明的目标样式与 DOCX 当前实现出的有效格式是两类事实，必须分别保留证据；
- 每项被采纳的样式结论都要绑定语义对象和作用范围，并记录声明与实现的一致、冲突或未决状态；
- 页码、bbox、颜色或一个近似文字命中不能单独构成稳定定位。

候选最小形态：

```yaml
schema_version: 1
scope: current_task_only
template:
  path: clean-template.docx
  sha256: <frozen-template-sha256>
  source_template_sha256: <source-template-sha256>
sources:
  - source_id: <task-local-id>
    kind: template | written_requirement | official_example | user_confirmation
    sha256: <sha256-or-null>
    applicability: <scope>
format_requirements:
  - requirement_id: <task-local-id>
    semantic_target: <heading-level-1-or-other-role>
    scope: <applicable-scope>
    condition: <condition-or-null>
    properties: {<semantic-property>: <normalized-value>}
    authority: declared | inferred
    evidence_refs: [<text-evidence-ref>]
    observed_format_ref: <docx-observation-ref-or-null>
    resolution: confirmed | conflict | missing | not_observable | unresolved
regions:
  - region_id: <task-local-id>
    responsibility: fixed | fill | generate | repeat | conditional | manual | unresolved
    locator: <snapshot-bound-locator>
    expected_content: none | scalar | paragraph_stream | composite
    cardinality: {min: 0, max: 1 | many}
    condition: <condition-or-null>
    expected_fingerprint: <fingerprint-or-null>
    format_requirement_refs: [<requirement-id>]
    evidence_refs: [<ref>]
gaps: []
review:
  document_sha256: <frozen-template-sha256>
  evidence_refs: [<visual-evidence-ref>]
validation:
  document_sha256: <frozen-template-sha256>
  status: ok | blocked
  evidence_ref: <validation-ref>
```

精确字段和 locator 结构由实现 fixture 与转换端真实消费者共同锁定。统一 `regions`
只是当前候选，不能因为本文出现就视为公共 schema 已发布。

## 5. Skill 的内容模型

`SKILL.md` 应把学校材料抽象成一份可重复填充的文档接口，而不是按学校、页面或论文部件
复述处理动作。主文件需要让 Agent 理解五件事：

1. 模板同时包含结构、内容责任、生成行为和呈现方式；四者不能互相替代；
2. 来源中的固定文字、示例、说明、缓存和物理载体需要转成稳定的模板责任；
3. 清理必须保留模板能力，不能只得到一份没有学生内容的空文档；
4. 样式要求既存在于书面说明、模板说明和示例语境中，也存在于 DOCX 的实现属性中；
5. 实际反复发生的 Word 错误来自哪些错误假设。

主文件可以用简短步骤说明任务要完成什么，也允许 Agent 回看、比较和重复检查；它不保存
阶段状态、checkpoint 或固定 Tool 调用图。

主文件需要直接写出的通用经验包括：

- 说明语义先迁移后删除；
- 目标样式要求不等于代码观察到的当前样式；
- 逻辑单元与物理页分离；
- 有效格式不等于样式名；
- 生成机制不等于缓存结果；
- 覆盖完整不等于所有权正确；
- 示例数量不等于实例基数；
- 没有可见文字不等于没有结构职责；
- 未知内容不因无法分类而消失。

这些是对 `temp/` 中真实失败的跨学校抽象，不是把具体学校的页数、数值、截图或修复动作
复制进 Skill。

### 5.1 样式提取的三层职责

样式提取不是单纯读取某个字段背后的样式代码，而是由 Skill/Agent 和现有 Tool 协作完成：

1. **文字声明层**：Skill/Agent 从书面要求、模板说明、官方示例语境和用户确认中提取目标
   格式要求；
2. **Word 实现层**：Tool 观察 DOCX 当前通过默认值、样式继承、命名样式、段落/run 直接
   格式、编号、内容控件和生成结果缓存实际实现出的格式事实；
3. **语义裁决层**：Skill/Agent 把文字要求绑定到正确的语义对象和作用范围，再与代码观察
   结果交叉验证，形成可追溯的样式结论。

Skill/Agent 在文字声明层负责识别：

- 被约束的语义对象，例如论文题目、一级标题、目录一级条目或图题，而不只匹配“标题”二字；
- 属性、规范值、适用范围、条件和例外，例如字体、字号、间距、缩进、分页及中英文差异；
- “同上”“此页”“另页开始”“标题前空三行”等依赖上下文的指代和排版语义；
- 文字属于正式规则、模板作者的实现说明、操作教程、示例现状还是尚待确认的要求声称；
- 每个判断的来源、证据位置和置信状态。

Tool 不负责判断一句自然语言究竟约束哪个论文对象，也不把命名样式或当前可见效果直接声明
为学校目标。它负责返回可复查的 Word 实现事实和候选对象，必要时在 Agent 已提供结构化
要求后做确定性属性比较。

Skill/Agent 必须逐项比较文字声明与实现观察。结果至少区分 `confirmed`、`conflict`、
`missing`、`not_observable` 和 `unresolved`：文字规则与模板实现冲突时保留两边证据，不以
代码结果静默覆盖文字要求；只有实现事实而没有充分文字依据时，也不能把它自动提升为学校
规则。证据不足、对象歧义或来源权威性无法判断时，保留未决状态，必要时请求用户确认。

这一职责模型落实
`docs/plans/docfit-school-extract-core-problem-classes.md` 中“说明语义先迁移后删除”和
“有效格式，而不是样式名”两类问题：前者保护文字承载的排版规则，后者保证验证面向最终
生效属性。两者缺一不可。

## 6. Reference 目录方案

候选树位于 `docs/plans/docfit-school-extract-v2-fresh-draft/`：

```text
docfit-school-extract/
├── SKILL.md
├── references/
│   ├── template-model.md
│   ├── word-behavior.md
│   └── failure-patterns.md
└── evals/
    └── evals.json
```

references 不按处理阶段，也不按封面、目录、声明等论文部件枚举：

- `template-model.md` 展开模板接口的稳定抽象，包括文字样式要求、Word 实现观察及其裁决；
- `word-behavior.md` 解释可见内容之外的 Word 行为和有效格式来源链；
- `failure-patterns.md` 保存已经去学校化的系统性错误假设，包括把样式代码误当目标规则。

三份文件由 `SKILL.md` 直接引用，不增加只有导航作用的 `index.md`。`temp/` 中的原始复盘
只作为设计证据，不成为生产 Skill 的运行时依赖。

## 7. 确定性能力放在哪里

不新增模板专用 Agent loop、五个新 Tool、Skill 生产脚本或第二套文档执行面。Agent 仍
只看到现有五个 `mcp__docfit__...` Tool；其名称、参数和错误语义以 SDK 注册信息为准，
不复制进 Skill。

文字材料中的样式要求提取属于 Skill/Agent 的语义职责，不能下沉为纯代码解析。确定性
能力负责提供 Word 实现事实、稳定定位和比较结果，不代替 Agent 判断规则对象、作用范围、
来源性质和证据冲突。

所需能力在现有边界内扩展：

| 现有边界 | 冻结模板切片需要增加的职责 |
|---|---|
| `docx_inspect` | 观察命名样式、继承、直接格式和最终有效格式等 Word 实现事实，以及字段/编号/关系、模板责任候选和稳定定位所需事实；不宣称其等于目标样式规则 |
| `docx_edit` | 在工作副本上执行保留结构的清理、槽位锚点物化和必要的结构规范化 |
| `docx_render` | 为模板基线、修改反馈和冻结候选产生绑定快照的页面证据 |
| `docx_visual_review` | 读取局部、相邻页、contact sheet 和最终全页证据 |
| `docx_validate` | 独立检查 package、索引/hash、固定内容、区域定位和最终可见覆盖 |
| 薄应用壳 | 校验产物 shape、授权路径和版本，并原子发布两个稳定产物 |

确定性重复工作可以成为 Tool 内部模块，但不作为 Agent 可见脚本：

```text
src/docfit/template/
├── model.py
├── mutation.py
├── artifact.py
└── validation.py
```

具体模块名由实现决定。它们不拥有 Agent loop、阶段状态或新的公共协议。

## 8. 冻结点

必要因果关系是：

```text
最后一次模板修改
  → 重新检查最终工作副本
  → 取得最终 template SHA-256
  → 在该快照上建立区域 locator 和槽位索引
  → 完成最终页面复核与独立验证
  → 原子发布两个产物
```

这是一组数据依赖，不是 Agent 工作流。索引生成后发生任何 DOCX 修改，都使索引、页面
证据和验证结论失效；程序必须拒绝旧结果，Agent 不负责手工维护引用生命周期。

## 9. 实施切片

### I0：Interface 与人工 adapter

- 用合成 fixture 锁定两个文件、schema 版本和授权路径；
- 锁定统一区域责任、内容形态、基数、manual/unresolved/gap 和 hash 失效语义；
- 提供一个最小人工产物 adapter，证明消费者不依赖生产者 Skill 名称。

### I1：现有 Tool 能力补齐

- 补齐命名样式、继承链、直接覆盖、外层结构和最终有效格式的可追溯观察；
- 支持对 Agent 提供的结构化样式要求做确定性属性比较，但不从自然语言自行裁决目标对象；
- 补齐生成对象、关系闭包和区域定位观察；
- 补齐保留结构的清理与槽位锚点物化；
- 补齐固定内容比较、索引绑定和失败不发布；
- 保持五个公开 Tool 名称、固定 OfficeCLI/Adobe 职责和现有权限面不变。

### I2：候选 Skill 与行为用例

- 迁移新的 `SKILL.md` 和三份机制型 references；
- 写入从文字材料提取样式要求、绑定语义对象并与 Word 实现交叉验证的判断标准；
- 要求样式结论保留来源、作用范围、观察证据和冲突/未决状态；
- 删除旧的证据工作流、Tool 使用说明和按论文部件复述的 references；
- 用真实失败提炼的合成用例验证抽象，而不是验证固定调用轨迹。

### I3：转换消费者迁移

- 让转换入口只消费冻结模板和槽位索引；
- 不要求同一运行加载学校提取 Skill；
- 以冻结模板为候选主干，关闭对原始学校材料的重新解释；
- 保持学生源内容覆盖、固定内容保护和现有最终报告合同。

### I4：原子切换

- 同一变更更新生产 Skill、应用接线、普通测试和受影响的 00–06；
- 删除旧的双 Skill 强制加载和旧提取产物断言；
- 通过确定性与 live 产品门后再声称新 Interface 已实现。

## 10. 行为与契约用例

| 用例 | 关键断言 |
|---|---|
| 说明文字同时承载格式与必填规则 | 先迁移语义，再删除说明载体 |
| 书面要求声明一级标题格式，模板当前实现不同 | 分别保留目标要求与实现事实，标记冲突，不让代码结果覆盖文字规则 |
| 多处材料都出现“标题”但所指对象不同 | Agent 结合上下文绑定语义对象和作用范围，不按近似文字统一套用 |
| 样式名相同但段落或 run 存在直接覆盖 | Tool 返回来源链与最终有效值，Agent 以有效格式交叉验证 |
| 只有模板实现值，没有充分文字规则 | 允许记录实现观察，不自动提升为学校目标样式 |
| 多个同构示例章节 | 表达重复能力，不冻结示例数量 |
| 源块无遗漏无重复但边界归属错误 | 同时检查覆盖和逻辑所有权 |
| 动态目录缓存正常但重建失真 | 保留生成机制和有效结果样式，以重建结果验收 |
| 空段或无文字结构被当作垃圾 | 不因缺少可见文字删除结构职责 |
| 彩色或括号文字用途不明 | 不因外观删除，保留为未决 |
| 索引后模板被修改 | 旧 locator、页面证据和验证全部拒绝 |
| 同时提供学生论文 | 不填学生内容，只处理模板产物 |

普通产品门至少包括：

- source hash 不变；
- schema/hash/授权路径合同通过；
- 自动区域零命中、多命中和快照失效全部拒绝；
- 固定内容未经允许变化全部拒绝；
- manual、conditional、unresolved 和 gap 不被伪装成自动槽位；
- 说明载体删除前，其文字承载的样式语义已经迁移到可追溯的格式要求；
- 每项采纳的样式属性都能追溯到语义对象、作用范围和文字证据，并具有实现观察与裁决状态；
- 代码观察到的命名样式或有效格式没有被无依据地声明为学校目标要求；
- 文字要求与 Word 实现不一致时，冲突没有被静默消解；
- 生成区域和重复区域没有被压成有限静态槽位；
- package 关系、最终页面覆盖和 blocking finding 没有缺口；
- 同一产物由 Skill 和人工 adapter 生成时，转换消费者行为等价；
- `convert-thesis` 不要求两个 Skill 同时加载；
- 源 hash、Adobe candidate、全页视觉审查和现有独立验证不退化。

合成 fixture 上“Interface 或源内容覆盖未闭合却被接受完成”的拒绝率必须为 100%。这些
是 unit/contract/integration/live 产品门，不依赖延期的 M3 Eval。

## 11. 真实经验的吸收边界

本轮设计读取了 `temp/manual-gold-preparation/` 中的模板审计、错误反馈、逻辑分页、目录
重建和学生稿修复记录，以及 `temp/docfit-unit-boundary-tool-poc-results.md`。

进入 Skill/reference 的只有反复成立的机制：内容职责、规则迁移、边界所有权、有效格式、
生成对象、关系闭包和目标渲染作用域。以下内容不进入：

- 学校名称、页数、字体字号、间距和具体坐标；
- 针对某个文件加减空段或修改制表位的配方；
- 临时 Gold 路径、截图、hash 和人工验收状态；
- 已由现有 Tool/App 硬门保证的执行细节。

## 12. 完成与非目标

本草案完成只表示候选 Interface、Skill 结构、现有 Tool 扩展面、迁移切片和测试边界可供
评审。它不表示：

- 生产 Skill 已替换；
- slot index schema 已成为公共合同；
- 当前五个 Tool 已实现全部冻结模板能力；
- 当前 `docfit convert` 已消费槽位索引；
- M3 Eval、授权/脱敏真实样本资格验证或外部人工复核已经恢复。
