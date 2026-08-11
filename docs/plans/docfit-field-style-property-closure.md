# DocFit 字段样式提取属性闭包与修复计划

## Plan Ledger

- Status: `APPROVED_IN_PROGRESS`
- Date: `2026-08-11`
- Task source: 用户确认“字段样式提取也必须使用稳定属性列表”，并要求形成文档与跨模块修复计划
- Status authority: `docs/status/active/docfit-student-content-dependencies-and-blockers.md`
- Canonical scope: 模板生成模块中的学校字段/slot 样式观测与缺口报告，以及最终内容填写模块中的实际角色集计算、整角色兜底选择、物化和最终验证
- Current implementation state: P0-P4 核心已实施；P5 完成 paragraph 核心 typed VALUE/NONE codec；P6 已把 presentation-role inventory、actual role set、整角色选择和可执行合同串成写入前 task-local target 纯编排；P8 已加入不 import 产品 resolver 的固定列表/双轴/digest 独立门禁。完整 caption/table/section/document codec、最终 Fill Contract/Placement 接线与 final-fill 重排尚未完成
- Current product status: `FAIL`，`production_fill_allowed=false`；修订计划不改变该运行状态
- Product boundary: 模板生成只报告学校样式事实、完整学校候选和已知缺口，禁止选择或注入兜底；最终内容填写才在实际角色集上执行学校完整角色与版本化兜底完整角色二选一，禁止逐属性混合
- Artifact boundary: Profile、Observation、Style Contract 和选择 receipt 都是三模块内部能力，不新增产品模块、学校资产类型或用户交付物；用户仍只获得一个最终 Word
- Approval boundary: 本文获批后才可修改产品代码；新增 Tool 名称、修改 Tool 输入 schema、改变 Claude Agent SDK runtime 或发现真实外部合同消费者时必须重新审批
- Unknown-unknown scout: `COMPLETE_2026_08_11`。现有提交 `819fb50` 已完成 Style Contract v2、
  核心 resolver/materializer、模板代表 occurrence、Placement ref 和最终 occurrence audit 的第一垂直
  切片；尚缺 Profile Registry、双轴 Observation、学校 candidate/gap 发布、actual role set 与整角色
  preset 选择。仓库内消费者仅为当前产品代码、测试/Eval 和临时运行产物，未发现真实外部 v2
  消费者。脏工作区中的属性级国标 fallback 实验与本计划冲突，只保留其稳定 occurrence 证据，
  不得按属性混入；用户内容提取 v2 改动为 no-touch scope。
- Execution evidence: `3779165` 固定 Profile/双轴 Observation；`3b4eaeb` paragraph resolver；
  `997e6a4` 模板发布 school observation/candidate/gap；`09bdd55`/`5845897`/`7c9645f`
  accepted preset、actual role set 与整角色选择；`b293706` typed occurrence codec；`b8727fb` 写入前
  presentation-role inventory；`27182f8` task-local preflight target；`3458ecc` 独立 Eval
  Observation 闭包门禁。模板 Tool 输入和 Claude Agent SDK runtime 未改变。当前仍为
  `APPROVED_IN_PROGRESS`，不得把上述核心切片描述成完整 P5-P8 或产品完成。

## 1. 结论

字段样式提取必须采用稳定属性列表，但稳定列表不直接归属于 `field_id`，而归属于字段在一个
具体 Presentation Slot 中引用的 Style Role Type：

```text
field_id
  → presentation slot
  → style role
  → versioned style property profile
  → fixed property result list
```

同一 `field_id` 可以在封面、题名页、目录或正文引用不同 Style Role，因此可以合法拥有不同
样式合同。非样式字段必须明确记录 `handling=non_style`，不能为了表面统一而伪造样式。

学校模板提取与通用兜底应共享：

- 属性名称、类型和适用范围；
- Style Role Type 到稳定属性列表的映射；
- `VALUE`、`NONE`、`N/A`、`UNRESOLVED` 的状态语义；
- 学校证据状态、观测可信度与学校角色候选资格的聚合规则；
- 属性规范、canonicalization、完整性门禁、物化和验证规则。

二者不得共享或混合具体值。学校值只能来自当前模板及其 Word 继承上下文；兜底值只能来自
已批准、版本化的 preset。模板提取阶段不得用兜底值补齐学校模板。

三模块职责必须保持如下边界：

- **模板生成**：提取并报告学校样式事实，产出完整学校角色候选和已知学校缺口；不读取学生内容，
  不计算本次任务的实际角色集，不选择或物化兜底；
- **用户内容提取**：继续只产出已经验收的学生内容合同。本计划将其作为只读输入和回归门禁，
  不修改其 v2 合同或提取逻辑；
- **最终内容填写**：结合学生内容与保留的学校模板结构计算实际角色集，按整角色选择学校候选或
  preset，在写内容前形成任务局部 fused target，并对最终所有 occurrence 审计。

## 2. 为什么“模板没有写”不能直接等于 `NONE`

Word 的最终显示值来自多层级联，而不是当前 XML 节点：

```text
docDefaults
  → 默认段落/字符样式
  → basedOn 样式链
  → 段落样式与字符样式
  → 编号、表格条件样式、Theme 和 section/container 上下文
  → 段落标记与 Run 直接格式
  → Word 规范默认及环境依赖行为
```

因此，一个属性在当前样式节点中没有声明，可能意味着：

1. 从 `basedOn`、默认样式、Theme、编号或容器继承；
2. Word 有明确的规范默认，例如段前距为零；
3. 属性适用且最终行为是明确关闭，例如无下划线、无编号；
4. 属性对当前角色根本不适用；
5. 当前 resolver 尚不能覆盖该来源或依赖环境，因而无法确定。

只有第 3 类才是 `NONE`。把 1、2、4、5 都压成 `NONE` 会丢失继承事实、隐藏实现缺口，并让
最终写入无法保证相同结果。

## 3. 稳定属性双轴状态合同

每个 profile 规定的属性都必须出现在提取结果中。缺少属性键不是合法状态，而是 schema 或
实现错误。

### 3.1 最终有效状态轴

| `effective_state` | 定义 | 是否带 `value` | 是否进入可执行合同 | 例子 |
|---|---|---:|---:|---|
| `VALUE` | 属性适用，最终有效值已确定 | 是 | 是 | `space_before_pt=0`、`bold=false` |
| `NONE` | 属性适用，目标行为是明确不存在或关闭 | 否 | 是，使用属性专属清除编码 | `numbering`、`underline` |
| `N/A` | 属性在该 Role Type 上结构性不适用 | 否 | 否 | 字符样式的段落分页属性 |
| `UNRESOLVED` | 属性适用，但当前证据不足，无法确定学校最终有效值 | 否 | 否，并阻断学校完整角色 | 缺少学校声明且没有安全默认 |

`0`、`false`、空集合和 `NONE` 不可互换：

- `0` 是确定数值；
- `false` 是确定布尔关闭值；
- 空集合是一个确定集合值；
- `NONE` 是该属性领域定义的“无此行为/关系”；
- `N/A` 表示该属性不属于当前角色。

### 3.2 学校证据状态轴

最终有效状态不能独自表达“学校明确要求”与“Word 恰好给了默认值”的差异。每个属性还必须
具有一个独立的 `school_evidence_status`：

| `school_evidence_status` | 含义 | 对模板生成的影响 | 对学校角色候选的影响 |
|---|---|---|---|
| `EXPLICIT_OR_VERIFIED` | 学校模板显式声明，或继承链已被学校模板事实与受控验证封闭 | 正常 | 可进入学校候选 |
| `IMPLICIT_WORD_DEFAULT_ONLY` | 只有 Word 规范默认，没有学校特定声明 | 记录事实；按属性策略判定 | 仅当默认可跨环境验证并显式物化时可进入，否则为已知缺口 |
| `MISSING_SCHOOL_DECLARATION` | 属性适用，但学校材料没有足够声明 | 记录为已知缺口 | 不进入完整学校候选 |
| `CONFLICT` | 多个学校证据相互冲突，无法形成可信单值事实 | 阻断可信观测 | 不生成候选 |
| `RESOLVER_UNSUPPORTED` | 证据存在，但当前 resolver 或环境不能可靠解释 | 阻断可信观测 | 不生成候选 |

这两个轴聚合为两个不同的角色级状态：

```yaml
observation_closure: COMPLETE | FAILED
school_role_eligibility: COMPLETE | INCOMPLETE_KNOWN_GAPS | NOT_EVALUABLE
```

- `observation_closure=COMPLETE` 表示 profile 全键存在且每个属性被可信分类；它允许
  `IMPLICIT_WORD_DEFAULT_ONLY`、`MISSING_SCHOOL_DECLARATION` 这类已知学校缺口；
- `observation_closure=FAILED` 只用于 `CONFLICT`、`RESOLVER_UNSUPPORTED`、缺键、schema 错误或
  provenance 无法验证等提取系统失败；
- `school_role_eligibility=COMPLETE` 要求全部适用属性均为 `VALUE/NONE`，且学校证据为
  `EXPLICIT_OR_VERIFIED`，或 `IMPLICIT_WORD_DEFAULT_ONLY` 已被该属性 profile 明确允许、可稳定
  canonicalize 并将在写入时显式物化；
- `INCOMPLETE_KNOWN_GAPS` 是合法的模板生成结果，不使模板生成模块失败，但最终填写不得把它
  当成学校完整角色使用；
- `NOT_EVALUABLE` 用于观测闭包失败，此时模板生成必须 fail closed。

继承方式不作为最终有效状态，而保存在 provenance 中：

```yaml
property_path: paragraph.space_before_pt
effective_state: VALUE
value: 0
school_evidence_status: EXPLICIT_OR_VERIFIED
provenance:
  - source_kind: paragraph_style
    source_id: BodyText
    action: inherited
```

原始观测层还必须区分某个来源层的 `declared` / `absent_at_layer`；后者只描述该层没有声明，
不能直接进入最终 Style Contract。

## 4. 稳定列表的归属与版本化

### 4.1 Style Property Profile Registry

建立一份与具体 preset 值分离的版本化属性规范。第一版至少覆盖现有产品已经接受的 Role Type：

- `paragraph`
- `heading`
- `toc_entry`
- `character`
- `table_cell`
- `caption`
- `equation`
- `header_footer`
- `footnote`
- 已批准的 page、section、figure、table、equation 等 document/layout role type

每个 property definition 必须声明：

```yaml
property_path: paragraph.numbering
value_type: numbering_definition
applicable_role_types: [paragraph, heading, equation]
allows_none: true
allows_n_a: false
resolution_strategy: effective_numbering_chain
canonicalization: docfit_numbering_v1
materialization_strategy: explicit_no_numbering_or_bound_numbering
validation_strategy: reopen_and_resolve_effective_numbering
implicit_word_default_policy: ALLOW_IF_PORTABLE_AND_EXPLICITLY_MATERIALIZED
```

`implicit_word_default_policy` 的另一个合法值是 `GAP`。该策略属于属性语法，不是学校或 preset
具体值。

Registry 是学校提取、preset 校验、Style Contract 编译、materializer 和 Eval 共享的“属性
语法”，不是第三套样式值真源。当前 preset 中的 `required_effective_properties` 应迁移或生成自
该 Registry，避免两份稳定列表漂移。

### 4.2 Field/Slot 到 Role Type

Field Registry 继续只表达跨阶段语义身份。具体样式归属由模板 slot/结构成员引用：

```yaml
field_id: thesis.title
slot_id: thesis.title.cover.1
style_role_id: style.cover.title
style_role_type: heading
property_profile_ref:
  profile_id: docfit.style.heading
  profile_version: 1.0.0
  profile_digest: ...
```

一个复合字段可以拥有多个结构成员，每个成员分别引用 Style Role。不能把一整个
`body.chapters` 聚合字段压成单一段落样式。

## 5. 学校观测与最终可执行合同必须分离

### 5.1 Field Style Observation

学校模板提取首先生成只读、证据完整的观测产物。它必须按 profile 返回固定属性集合，并允许
`UNRESOLVED`：

```yaml
schema_version: docfit-field-style-observation/v1
field_id: body.inline_emphasis
slot_id: body.inline_emphasis.1
style_role_type: character
property_profile_ref: {...}
properties:
  run.cjk_font:
    effective_state: VALUE
    value: 宋体
    school_evidence_status: EXPLICIT_OR_VERIFIED
    provenance: [...]
  run.underline:
    effective_state: NONE
    school_evidence_status: EXPLICIT_OR_VERIFIED
    provenance: [...]
  paragraph.alignment:
    effective_state: N/A
    school_evidence_status: EXPLICIT_OR_VERIFIED
    provenance: []
closure:
  observation_closure: COMPLETE
  school_role_eligibility: COMPLETE
  known_gap_properties: []
  unresolved_properties: []
```

Observation 忠实反映学校模板，不执行兜底选择，不产生学校未提供的值。

### 5.2 Executable Style Contract

只有满足以下条件，Observation 才能在模板生成模块中编译为**完整学校 Style Contract
candidate**：

- profile 要求的每个属性都有记录；
- 全部适用属性为 `VALUE` 或可物化的 `NONE`；
- 不存在 `UNRESOLVED`；
- `observation_closure=COMPLETE` 且 `school_role_eligibility=COMPLETE`；
- 全部适用属性的学校证据均满足 profile 的候选资格策略；若为
  `IMPLICIT_WORD_DEFAULT_ONLY`，必须被属性策略明确允许并编译成显式、可重开验证的操作；
- 每个属性都有稳定 canonicalizer、materializer 和 reopen validator；
- Theme、编号、表格、section/container 等 digest-bound 依赖已经封闭。

`N/A` 只参与属性闭包验证，不进入可执行属性集合。`NONE` 必须编译成属性专属操作，不能直接
解释为 JSON `null` 或“省略 XML”。

如果 Observation 可信但学校证据存在已知缺口，模板生成仍然可以成功发布 Observation、完整
学校候选集合和精确缺口集合；它不得在此阶段选择 preset，也不得伪造学校合同。最终内容填写
模块只消费完整学校候选，并对本次任务的实际角色集独立执行整角色选择。

## 6. 核心不变量

1. **列表闭包**：同一 profile 版本的所有 Observation 具有完全相同的 property path 集合。
2. **状态闭包**：每个 property path 恰有一个合法 `effective_state` 和一个合法
   `school_evidence_status`；空白、缺键、非法组合和通用 `null` 非法。
3. **来源忠实**：学校 Observation 不含 preset 值，preset 不从学校样本反向学习运行时值。
4. **角色粒度**：最终填写中，学校角色完整则整体选学校；不完整则整体选 preset；禁止逐属性混合。
5. **可执行闭包**：合同拥有的每个属性必须有确定物化和 reopen 验证能力。
6. **结果稳定**：同一 `style_contract_id + contract_digest` 的所有 occurrence 具有一致的受管
   有效属性，与学生源直接格式、相邻内容和共享命名样式变化无关。
7. **上下文绑定**：依赖 Theme、编号、表格条件或 section/story 的结果必须绑定对应依赖 digest。
8. **无隐式默认**：完整合同不依赖未记录的 Word `Normal`、环境字体替换或模型猜值。
9. **模块边界**：模板生成只产学校 Observation、完整学校 candidate 和已知缺口；只有最终内容
   填写可以计算实际角色集、选择 preset 并物化任务局部目标。
10. **身份分离**：模板生成与最终填写共享 `profile_digest`，但学校
    `school_observation_set_digest` 与最终选择后的
    `selected_style_contract_set_digest` 是不同身份，禁止把二者描述成同一合同。
11. **单一用户交付物**：所有样式闭包 artifact 都是内部证据，不能成为额外用户资产或第二份
    可编辑模板；最终仍交付一个以学校模板为结构主干的 Word。

## 7. 目标数据流

```text
模板生成模块
  最终学校模板快照
    → Word raw observation
       docDefaults / styles / direct formatting / theme / numbering / container
    → Effective resolver + versioned property profile
    → Field Style Observation Set
       固定列表 + 双轴状态 + provenance + school_observation_set_digest
    → 发布：完整学校角色 candidates + 已知学校 gaps
       observation FAILED 时 fail closed；不得选择/物化 preset

用户内容提取模块（已验收，只读输入，本计划不修改）
  学生论文
    → Student Content Contract v2

最终内容填写模块
  学校模板主干 + Student Content Contract v2 + 学校 candidates/gaps
    → 计算本次任务 actual role set
       学生真实内容角色
       + 模板中必须保留的任务书/评阅表/章节/附录/无内容说明
       + 目录、页码、section、header/footer 等全局角色
    → 对 actual role set 中每个角色整角色选择
       school candidate COMPLETE → school
       否则 approved preset COMPLETE → preset
       否则仅在缺少获批可补输入时 NEEDS_INPUT，其余 fail closed
    → 生成 selected_style_contract_set_digest
    → 写内容前把角色/容器能力物化到 task-local fused target
    → student fill + occurrence projection
    → 对每个新增或复用 occurrence 显式物化受管属性
    → reopen effective validation
    → 最终全部 occurrence audit
    → 一个最终 Word
```

## 8. 当前实现与目标差距

| 维度 | 当前实现 | 目标 | 主要风险 |
|---|---|---|---|
| 属性规范 | preset 内已有按 Role Type 的 `required_effective_properties` | 独立共享的版本化 Registry | preset 与学校提取列表漂移 |
| 属性词汇 | preset 使用 `run.cjk_font` 等产品词汇，当前合同使用 `run.font_east_asia` 等 Word 词汇 | Registry 定义唯一 canonical path，并声明 Word codec/迁移别名 | 同一属性被重复、误配或漏检 |
| Resolver | 覆盖 docDefaults、默认样式、basedOn、段落/字符样式、核心直接格式及少量隐式默认 | 覆盖完整 profile 需要的 Word 上下文 | 把未覆盖误报为 NONE |
| Capture | 从 resolver 当前非空且 materializer 支持的属性动态生成 `owned_properties` | 按 profile 遍历固定列表并返回双轴状态 | 不同字段合同长度不同 |
| Contract | v2 主要保存 scalar `effective_properties` | 支持 typed property state、结构值和 digest-bound 依赖 | `none`/`null` 语义不清 |
| Materializer | 核心 Run/段落属性 | 每个适用属性都有 VALUE/NONE codec | 省略 XML 后重新继承 |
| Tool | Agent 看到局部对象/格式事实，完整 resolved style 主要留在内部 | Agent 看紧凑学校观测 closure 摘要；完整矩阵留在内部 artifact | Tool result 上下文膨胀 |
| Template Publish | 发布时捕获核心可物化属性并验证代表 occurrence | 发布学校 Observation Set、完整学校 candidates 和精确 gaps；不选 fallback | 模板模块承担了最终填写策略 |
| Final Fill selection | 已有人评通过的完整 preset 产品定义；运行时尚未实现整角色选择 | 根据学生内容和保留结构形成 actual role set，再 school-complete/preset-complete 二选一 | 逐属性混合或漏掉保留结构角色 |
| Eval | 已验证 v2 digest/引用和核心属性 | 独立验证固定列表、双轴状态、provenance 与全链路结果 | 产品实现自证 |
| Module status | 用户内容提取已通过；模板生成与最终内容填写仍失败 | 不回退已通过提取；分别关闭模板观测门和最终填写样式门；整体仍服从三模块 E2E | 局部样式通过被误报为产品 COMPLETE |

## 9. 修复计划

### P0：冻结属性语言与版本策略

目标：在写 resolver 或 Tool 前先锁定不会歧义的数据语言。

工作：

- 从已接受 preset 提取 Role Type、required property paths、value types 和适用性；
- 统一 preset 产品词汇与现有 resolver/contract property paths，形成唯一 canonical vocabulary；
- 定义 `effective_state=VALUE/NONE/N/A/UNRESOLVED` 与
  `school_evidence_status=EXPLICIT_OR_VERIFIED/IMPLICIT_WORD_DEFAULT_ONLY/MISSING_SCHOOL_DECLARATION/CONFLICT/RESOLVER_UNSUPPORTED`
  双轴 schema、合法组合和禁止状态；
- 定义 `observation_closure` 与 `school_role_eligibility` 的独立聚合规则，禁止把已知学校缺口误报成
  resolver 失败，也禁止把 resolver 失败降级成学校缺口；
- 为每个 `NONE` 属性定义实际 Word 语义，禁止通用 null 解释；
- 盘点 Style Contract v2 / Fill Contract v2 的真实消费者；
- 若无真实外部消费者，使用明确新 schema version 做 clean break，不保留仅服务历史实现的兼容层；
- 若发现真实消费者，停止并提交迁移方案与成本供用户决定。

完成门：属性 Registry 和 Observation 双轴 schema 通过产品、人评、schema 合成测试；不存在未分类属性或含糊的聚合结果。

### P1：建立共享 Style Property Profile Registry

目标：让学校提取与 preset 校验共享一份属性语法，而不是复制列表。

建议边界：

- 新增一个 Registry artifact/schema 及薄加载器；
- preset 只保留角色值与 `profile_ref`；
- 学校 extractor、contract compiler、materializer、validator 和 Eval 都引用同一 profile identity；
- profile digest 进入学校 Observation Set、最终选定 Style Contract Set 与各自审计，但不把两个
  artifact digest 合并成同一身份。

完成门：全部已接受 Role Type 与字段 handling 引用闭包通过；任一新增属性缺少解析/物化/验证声明时拒绝晋升。

### P2：扩展 Word 有效样式 Resolver

目标：对 profile 要求的每个属性返回可信的双轴状态和完整 provenance。

按风险分组实施：

1. 核心 Run/段落：字体、字号、粗斜体、颜色、下划线、字符间距、对齐、缩进、间距、分页控制；
2. Theme 和脚本字体：ascii/hAnsi/eastAsia/cs、theme token、语言与可验证的字体环境边界；
3. 编号、outline、tab stop 和 TOC 上下文；
4. 表格条件样式、单元格边框/底纹/边距/对齐；
5. section/page、header/footer、footnote、textbox 等跨 story/context；
6. 图、表、公式的对象/容器布局角色。

每组都必须先有合成 DOCX，覆盖显式值、继承值、Word 规范默认、toggle、明确关闭、学校未声明、
缺失依赖和冲突。学校未声明按证据轴报告已知缺口；resolver 不支持按观测轴失败，二者不得互换。

完成门：profile 每个属性都有 resolver coverage；改变无关样式或对象顺序不会改变结果。

### P3：重构字段样式 Capture 与合同编译

目标：把当前动态属性抓取改成固定 profile 闭包。

工作：

- Capture 输入由“slot locator”扩展为“slot + field + style role + profile ref”；
- 对 profile 全列表逐项产出 Field Style Observation；
- 分别计算 `observation_closure` 和 `school_role_eligibility`；前者回答“提取是否可信”，后者回答
  “学校是否给出了可执行完整角色”；
- 分离 placeholder/样例直接格式和目标槽值格式，避免灰色占位、超链接或示例强调污染合同；
- 必要时使用受控 probe 或清理后的最终 representative 读取目标样式；
- 已知学校缺口生成精确 gap，不生成伪完整学校合同；`CONFLICT/RESOLVER_UNSUPPORTED` 阻断发布；
- 编译器把 `VALUE/NONE` 转成 executable operations，排除 `N/A`；
- 所有 identity、profile 和 dependency 进入 semantic digest。

完成门：同 profile 的所有学校字段 Observation 键集合完全一致；每个模板结果可无歧义地区分
可信观测、完整学校候选和已知学校缺口；动态 `owned_properties` 不再承担属性规范职责。

### P4：调整 Template Workspace 与 Tool 投影

目标：让模板生成 Tool 提供稳定、低噪声、可追溯的**学校样式事实与缺口**，同时保持 Agent
SDK-native Tool loop，并确保 Tool 层不承担最终兜底策略。

推荐 Tool 边界：

- 不新增 Tool；保留 `template_open/next/search/focus/registry/edit/publish`；
- 不让 Agent 输入或生成完整属性值；Agent 只判断字段、slot、结构成员和 Style Role；
- `template_open/focus/edit` 对当前局部对象返回紧凑摘要：`profile_ref`、
  `observation_closure`、`school_role_eligibility`、双轴 counts 和有界 gaps/failures 列表；
- 完整固定属性矩阵写入任务内 Field Style Observation artifact，并以 digest/ref 绑定；
- `template_publish` 只返回 `school_observation_set_digest`、`profile_digest`、完整学校角色
  candidates、已知学校 gaps 和 observation audit counts；不得返回 fallback 选择结果，不得写入
  preset 值，不得生成 `selected_style_contract_set_digest`；
- Tool result 不重复输出每个字段的全量矩阵，避免长任务上下文膨胀；只有局部诊断需要时才返回
  当前目标的有界属性详情；
- 当前窄的 `effective_format` 修复动作不能扩张为 Agent 自由提交样式表，它只作为明确的确定性
  Word 修复操作存在。

Claude Agent SDK 约束：Tool 的输入 schema 和描述应承担结构化调用合同，应用执行确定性 Word
操作并返回 `tool_result`；DocFit 不另建 Agent loop。完整矩阵属于领域 artifact，不应因为是
结构化数据就全部注入模型上下文。官方依据：
[Custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)、
[Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)、
[Manage tool context](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context)。

完成门：Tool 名称和输入面无非必要变化；Agent 可区分可信观测、已知学校缺口和 resolver 失败；
模板发布即使包含已知学校 gaps 也可成功，观测失败则 fail closed；发布结果中不存在 fallback 选择。

### P5：扩展 Style Contract、Materializer 与 Validator

目标：从“核心 scalar 属性稳定”升级为“profile 声明范围内完整角色稳定”。

工作：

- 引入 typed property values 和 typed state，避免字符串 `none`、JSON null 与业务状态混用；
- 为每个属性实现 canonicalize / apply VALUE / apply NONE / reopen resolve / compare；
- `NONE` 必须阻断继承，例如明确关闭 toggle、编号、tab、边框、底纹等，而不是简单删除 XML；
- dependency refs 绑定 Theme、numbering、table style、section/story 等所需上下文 digest；
- materializer 继续逐 occurrence 写入，不修改共享学校命名样式；
- validator 对 profile 全部适用属性重新打开比较，并把缺少 coverage 判为
  `effective_state=UNRESOLVED + school_evidence_status=RESOLVER_UNSUPPORTED`；
- 观测失败阻断模板发布；已知学校缺口只阻断该学校角色成为完整 candidate，不阻断模板模块
  产出可信 Observation/gap；最终填写选中学校或 preset 合同后的任何物化/验证失败都阻断最终候选。

完成门：同合同重复应用 1、10、100 次结果一致；学生直接格式、相邻段落或共享样式变化不能影响受管结果。

### P6：在最终内容填写模块实现实际角色集与整角色兜底选择

目标：在学生内容和最终学校模板结构都已知后接入已经接受的 preset，同时不破坏来源、模块和
角色边界。

选择算法：

```text
actual role ∈ complete school candidates
  → select complete school role
else preset role COMPLETE + applicable
  → select complete preset role
else exact missing source is approved user-providable input
  → NEEDS_INPUT with exact role/property request
else
  → FAIL with exact role and property reason
```

工作：

- 用户内容提取 v2 作为只读输入，不修改其已通过的 schema、提取或归一化逻辑；
- 最终填写根据 Student Content Contract v2 与模板保留结构形成 `actual_role_set`；
- `actual_role_set` 不只包含学生有内容的字段，还必须包含任务书、评阅表等保留表单，无内容章节/
  附录及“本项无需填写”说明角色，以及目录、页码、section、header/footer 等最终文档全局角色；
- 学校 candidates 与 preset 必须引用相同 profile identity；
- 禁止属性级 merge；
- 记录 role selection receipt、来源、preset identity/parameters 和 digest；
- 选择结果只在当前任务形成 `selected_style_contract_set_digest`，不得反写学校模板资产；
- 先在任务局部副本物化完整 fused target，再写入 Student Content Contract v2；
- 国家标准来源、产品预设和学校证据继续分别标注，不产生未经授权的符合性声明。

完成门：实际角色集完整覆盖学生内容与必须保留结构；完整学校角色不被 preset 改写；任一不完整
学校角色整体切换 preset；无可用完整角色时，只有缺口属于获批的可补输入才进入明确
`NEEDS_INPUT`，否则 fail closed；不修改已通过的
用户内容提取模块。

### P7：贯通最终内容填写、最终审计与观测

目标：最终内容填写只消费已闭合且 digest-bound 的选定 Style Contract，并保留从学校观测到最终
选择的可追溯关系。

工作：

- Fill Contract slot 只引用选定的完整 Style Contract；
- Placement 不根据字段猜样式，也不携带第二份 inline 样式；
- Projection 为所有最终 occurrence 生成稳定 locator 和 role ref；
- Final Audit 比较合同全部受管属性，不允许 PARTIAL 掩盖样式失败；
- run report 同时记录共享 `profile_digest`、上游 `school_observation_set_digest`、最终
  `selected_style_contract_set_digest`、school/preset selection、occurrence counts 和 unresolved/failed；
- 本地观测界面只投影摘要和 evidence refs，不保存文档正文或完整私有样式载荷。

完成门：模板生成与最终填写使用同一 `profile_digest`；最终填写、候选重开验证和最终报告使用
同一 `selected_style_contract_set_digest`；学校 Observation Set 通过独立 digest/ref 追溯，不能
被误写成最终选择合同。

### P8：独立 Eval、真实 Word 验证与文档同步

目标：避免产品实现用自身 resolver 自证。

验证矩阵：

- schema：固定键集合、双轴合法组合、禁止 null/缺键、profile/digest 引用闭包；
- unit：每个属性的继承、NONE 编码、canonicalization 和 reopen compare；
- metamorphic：无关样式重排、无关对象新增、学生直接格式变化不改变合同结果；
- contract：所有 Template Tool 学校观测摘要和 publish receipt 稳定，且不含 fallback 选择；
- integration：模板生成学校 observation/candidates/gaps → 用户内容合同只读输入 → 最终填写 actual
  role set → school/preset 选择 → task-local fused target → student fill → final audit；
- independent Eval：使用独立事实解析，不 import 产品 resolver；
- real template：至少覆盖有完整学校角色、部分学校角色、缺失角色、Theme/编号/表格/section 高风险模板；
- local/live：Microsoft Word 打开、字段更新、保存、关闭、重开；固定 LibreOffice 只作 approximate 视觉回归；
- human：完整属性表、角色选择表和最终视觉样例验收。

强制真实反例门禁：HUNAU 模板缺失的 `body.table.caption` 必须在模板生成报告中稳定呈现为学校
角色已知缺口；最终填写在实际论文包含表题时必须整角色选择已批准 preset，生成一致的表题
occurrences，并通过 reopen 与最终审计。不得通过删除该角色、降级为 `PARTIAL`、把缺口改成
`NONE` 或放宽 audit 来获得通过。

如果 HUNAU 真实任务的 11 个 required 值尚未由可靠来源提供，样式专项集成验证可使用明确标记、
不可发布的已批准测试 fixture 来关闭 `body.table.caption` 技术门；该 fixture 不得写回真实任务，
不得解除其 `NEEDS_INPUT`，也不得改变 `production_fill_allowed=false`。

完成门：确定性、集成、产品运行和 Word 人工验证全部通过；缺少 Word/渲染环境时状态为
`BLOCKED_NEEDS_LOCAL_VALIDATION`，不能宣称完整修复完成。该完成门只证明本计划的样式能力；
三模块产品整体 `COMPLETE` 仍以 active status 为准，并继续依赖 HUNAU 11 个 required 输入可靠
到位、目录/页码、无内容章节和附录保留、学校模板全结构保真及最终 Word/Human 验收。

## 10. 建议交付顺序与提交边界

1. `contract:` 属性 Registry、双轴状态 schema、Observation schema、consumer inventory；
2. `resolver:` 按属性组扩展 Word 解析、学校证据分类和 provenance；
3. `template-capture:` 固定 profile Observation、学校 candidate 编译和 gap 分类；
4. `template-tools:` Workspace 摘要、artifact ref 和不含 fallback 的 publish receipt；
5. `template-eval:` 独立验证模板观测闭包，确保已知学校 gap 可发布、resolver 失败不可发布；
6. `materialization:` typed VALUE/NONE codec 与 reopen validator；
7. `final-fill-selection:` actual role set、整角色选择和 task-local fused target；
8. `final-fill-pipeline:` Fill/Projection/Final Audit 与三种 digest 的追溯；
9. `eval:` HUNAU `body.table.caption` 强制反例、三模块样式链 run、真实 Word 和 Human gate；
10. `docs:` 同步 00/01/05/06、相关 human review 与 active status。

第 1–5 步关闭模板生成的“学校样式观测是否可信”门；第 6–9 步关闭最终内容填写的“结果样式
是否稳定”门。用户内容提取仅参与回归，不建立修改提交。样式计划通过后也不得跳过 active status
中的其他三模块产品 blocker。

每一提交只包含本计划拥有的文件；当前工作区中其他会话的 preset、TOC、正文结构和实验改动必须保留并单独提交。

## 11. 风险与停止条件

| 风险 | 处理 |
|---|---|
| 把 Word 未声明误判为 NONE | 原始声明与最终有效状态分层；未知一律 UNRESOLVED |
| 属性 Registry 变成第二份 preset | Registry 只含类型、适用性和 codec，不含学校或 preset 值 |
| Tool result 过大 | 全量矩阵落 artifact，Agent 只看局部摘要和有界缺口 |
| 模板模块提前选择 fallback | `template_publish` schema/contract test 明确禁止 selection 与 preset 值；选择只存在于最终填写 |
| 已知学校缺口被当成提取失败 | 双轴状态；known gap 允许模板发布，resolver unsupported 才阻断观测 |
| 合同 schema 版本膨胀 | 先盘点消费者；无外部消费者时 clean break，有消费者时单独迁移决策 |
| NONE 删除 XML 后重新继承 | 每属性专属 NONE materializer + reopen effective validation |
| Resolver 与 Eval 同源自证 | Eval 不 import 产品 resolver，使用独立事实分析和 Gold |
| 学校/preset 逐属性混合复发 | 选择粒度固定为 complete semantic role，合同与测试双门禁 |
| 环境字体造成视觉差异 | 字体环境 digest、UNRESOLVED 环境状态和 Word 人工门禁 |
| 样式局部通过被宣称产品完成 | 验收分层；产品总状态继续由 active status 的三模块 E2E 与全部 blocker 决定 |

必须停止并重新请求用户决策的情况：

- 需要新增 Tool、修改现有 Tool 输入 schema 或扩大 Agent 权限；
- 需要改变 Claude Agent SDK loop/session/permission/lifecycle；
- 发现真实外部 Fill/Style Contract 消费者需要迁移；
- 需要把未授权标准数值写入产品 preset；
- 必须依赖 Microsoft Word 自动化才能进入产品核心；
- 为实现完整闭包需要扩大已经接受的属性/字段/角色产品范围。

## 12. 验收标准

### 12.1 本计划的样式能力 SUCCESS

- 每个 styled slot 都引用一个 versioned property profile；
- 每个 Field Style Observation 的 property path 集合与 profile 完全相等；
- 每个属性恰有一个 `effective_state` 和一个 `school_evidence_status`，不存在缺键、空白、通用
  null 或非法组合；
- 学校 Observation 的值和 provenance 只来自当前模板；
- 模板模块能区分可信学校 gap 与 resolver/证据失败，前者可发布、后者 fail closed；
- 完整学校 candidate 不存在 `UNRESOLVED`，且每个适用属性可物化、可重开验证；
- 最终填写先计算 actual role set，再在学校 candidate 与 preset 之间按完整角色二选一，无逐属性 merge；
- Tool 不要求 Agent 生成样式值，不新增 Agent runtime；
- `template_publish` 不选择 fallback、不写 preset 值，只发布学校 Observation/candidates/gaps；
- 模板与最终填写共享 `profile_digest`；学校 `school_observation_set_digest` 与最终
  `selected_style_contract_set_digest` 各自稳定、可追溯且不混同；
- HUNAU `body.table.caption` 缺口与最终 preset 选择强制反例通过，不允许弱化审计；
- 独立 Eval、真实模板产品运行、Microsoft Word 重开和 Human acceptance 全部通过。

### 12.2 三个产品模块中由本计划负责的样式门禁

| 模块 | 本计划负责的门 | 能否据此单独判定模块 PASSED |
|---|---|---:|
| 模板生成 | 学校 Observation 全键可信；完整 candidates 与已知 gaps 可追溯；无 fallback 选择 | 否，还需 active status 中其余模板发布门 |
| 用户内容提取 | 已验收的 Student Content Contract v2 与现有 `434 passed` 回归基线继续通过 | 已 PASSED；本计划只回归 |
| 最终内容填写 | actual role set 完整；整角色选择、task-local 物化和全部 occurrence audit 通过 | 否，还需必填输入、目录分页、结构保留等门 |

### 12.3 产品整体 COMPLETE

本计划 `SUCCESS` 不等于 DocFit 三模块产品整体 `COMPLETE`。整体完成状态继续由
`docs/status/active/docfit-student-content-dependencies-and-blockers.md` 管理，至少还必须同时满足：

- HUNAU 11 个 required 输入可靠到位，缺失时走 `NEEDS_INPUT`；
- 学校模板作为最终 Word 结构主干，所有原有 section、页面、表格、任务书、评阅表和附录保留；
- 无学生内容但模板要求保留的部分输出“本项无需填写”，而不是删除结构；
- 目录、页码、分页和字段更新正确；
- 三模块完整 E2E、最终 Word 重开、逐页渲染和 Human acceptance 通过；
- 用户只收到一个最终 Word，不暴露内部 Observation、Contract 或 receipt artifact。

### 非目标

- 不在本计划中修改兜底 preset 的已接受具体值；
- 不修改已通过的用户内容提取 v2 schema、提取或归一化逻辑；
- 不把 11 个 required 输入、目录页码、模板全结构保留等非样式 blocker 伪装为本计划已解决；
- 不声明国家标准合规；
- 不增加全局学校 profile、Content Ledger、通用 schema registry 或第六类产品资产；
- 不把内部样式 artifact 变成新产品模块、学校资产或用户交付物；
- 不把每个 Word XML 属性都纳入 v1，范围以已批准 Style Property Profile 为准；
- 不让 Agent 直接编辑 Field Style Observation 或 Style Contract artifact；
- 不用 LibreOffice approximate 结果代替 Microsoft Word 最终验证。

## 13. Preflight Contract

Preflight status: `APPROVED`

Task source: user decision on 2026-08-11 plus this plan

Canonical source: `docs/plans/docfit-field-style-property-closure.md`

Status authority: `docs/status/active/docfit-student-content-dependencies-and-blockers.md`

Route: durable `$intuitive-flow`

Goal: make template generation publish trustworthy fixed-list school style observations, complete school candidates and known gaps without fallback selection; then make final content fill compute the task's actual role set, choose a complete school or preset role, materialize it task-locally, and audit every final occurrence.

Scope:

- shared property profile, dual-axis state/schema and consumer inventory;
- Word effective resolver and provenance;
- template-generation Field Style Observation, school candidate compiler and known-gap classification;
- Template Workspace/Tool compact school-fact projection and no-fallback publish receipt;
- final-fill actual role set and school/preset whole-role selection;
- occurrence materialization/reopen validation;
- Fill/Projection/Final Audit integration;
- independent Eval, real-template product runs, Word/manual validation, and docs.

Read-only dependency: accepted Student Content Contract v2 and its regression suite. No user-content extraction implementation changes are authorized by this plan.

Non-goals: preset value redesign; national-conformance claim; new Tool names; Agent runtime replacement; property-level school/preset mixing; Microsoft Word dependency in product core; creating a fourth product module or a second user deliverable; closing unrelated 11-input, TOC/page-number or structure-preservation blockers.

Entity budget:

- reuse: existing `src/docfit/styles/**`, Template Workspace, seven preparation Tools, Fill Contract, preset review artifact, Field Registry, accepted Student Content Contract v2, existing Eval project;
- remove/merge: dynamic materializer-supported paths as the de facto property universe; duplicated profile lists; generic null/string-none semantics;
- new: one versioned Style Property Profile Registry, one Field Style Observation schema/artifact, and one final-fill role-selection receipt, because current surfaces cannot express fixed-list dual-axis evidence or separate school observation identity from task-local selection identity;
- expansion triggers: new Tool/input schema, external contract migration, new product property scope, new standards values, Agent SDK runtime changes.

Context:

- must-read: this plan; `docs/status/active/docfit-student-content-dependencies-and-blockers.md`; `docs/plans/docfit-general-style-preset-v1.review.yaml`; `docs/human/docfit-general-style-preset-v1-product-review.md`; `src/docfit/styles/**`; `src/docfit/template/workspace.py`; `src/docfit/tools/template_tools.py`; `src/docfit/tools/inspection.py`; Fill Contract schemas; independent template-extraction Eval contracts;
- useful: `docs/docfit-00-index.md` through `docs/docfit-06-development-roadmap.md`; accepted Student Content Contract v2/body extraction spec and regression evidence; real-template reports;
- avoid-unless-needed: generated temp runs, private thesis contents, unrelated TOC/fallback experiments, old template Tool versions.

Acceptance:

- SUCCESS: section 12.1 style-capability criteria and section 12.2 module-internal style gates pass; this does not independently set template generation/final fill to PASSED or the whole product to COMPLETE;
- BLOCKED_NEEDS_DECISION: external consumer migration, public Tool/input change, new property scope or standards-value decision;
- BLOCKED_NEEDS_LOCAL_VALIDATION: Microsoft Word save/reopen, fixed renderer or Human visual acceptance unavailable;
- INTERMEDIATE_ONLY: none unless user explicitly approves a phase checkpoint;
- No regressions: public Tool names, Claude Agent SDK-native loop, object-ref safety, accepted user-content extraction v2 and its `434 passed` baseline, school-template final trunk, all required retained sections/pages/tables/appendices, one-final-Word delivery, independent Eval boundary.

Verification:

- deterministic: Ruff, Mypy, full unit tests, schema tests, profile/state/property codec tests, metamorphic tests;
- integration: template observation/candidate/gap gate, user-content extraction no-regression suite, final-fill actual-role-set/selection contract, style occurrence audit, independent Eval suite;
- product-run A: `docfit prepare-template` on representative schools publishes school observation/candidates/gaps without preset values or selection;
- product-run B: final fill consumes an approved Student Content Contract fixture, computes actual roles, creates `selected_style_contract_set_digest`, materializes before content write, and audits all final occurrences;
- mandatory real run: HUNAU `body.table.caption` remains a reported school gap during template generation and selects the approved complete preset only during final fill when the student paper contains table captions; if the 11 real required values remain unavailable, use an explicitly non-publishable approved fixture and keep the real task in `NEEDS_INPUT` with `production_fill_allowed=false`;
- local-live-manual: Microsoft Word open/update/save/close/reopen, fixed LibreOffice approximate render, complete property/role tables and Human acceptance;
- product-complete follow-on: after 11 reliable required inputs are available, run the full three-module HUNAU E2E including TOC/page numbers, retained no-content sections/appendices, per-page rendering and Human acceptance; this is required for overall product COMPLETE but is not evidence that style code alone must wait for those inputs;
- optional: additional schools and adversarial Word packages outside the accepted profile scope.

Execution: main=root supervisor; worker=none by default; worker-goal=none.

To execute: `/goal execute docs/plans/docfit-field-style-property-closure.md with intuitive-flow`

Optional tracking: none.

Approval: `LGTM` / `approve` / `go ahead` approves this implementation contract; edits request revision.
