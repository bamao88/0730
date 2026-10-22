# Agent-facing Style Evidence 工具层

> 日期：2026-08-17
> 文档类型：讨论结论与推荐设计
> 状态：设计讨论稿，不表示当前代码已经完整实现
> 范围：模板提取中的样式证据、删除风险、代表对象选择，以及它们与 Agent、Tool、Harness、
> publication/style capture 的边界。

## 1. 一句话定义

Agent-facing Style Evidence 是一层给 Agent 使用的“样式证据翻译器”：

> 它把 Word 底层样式事实提取、归一、聚合成 Agent 可读的证据和风险提示，帮助 Agent 判断
> 哪些对象能作为 Registry-bound slot 或 body member 的样式代表；但它不替 Agent 判断学校语义，
> 不自动绑定 Registry field，也不生成最终 Style Contract。

在当前工具分层中，它属于：

```text
docfit_evidence(focus="style_evidence")
```

这里的 Agent-facing 有三个含义：

- Agent 可以通过 `docfit_evidence` 的 `style_evidence` focus 取得这些证据；
- 返回内容面向判断，不要求 Agent 理解 OOXML、styleId、`w:rPr`、`w:pPr` 等底层结构；
- 证据足够短、足够稳定、足够可追溯，能进入主 Agent 或只读 subagent 的上下文。

## 2. 它解决什么问题

模板提取里经常会出现一种危险情况：某段文字内容看起来只是说明或样例，应该删除；但这段文字
同时又是某个下游可填写字段或正文角色的唯一格式样本。

例如：

- `（请在此填写论文题目）` 内容是样例，但它所在位置可能承载 `title.zh` 的真实字号、对齐、
  下划线和间距；
- 假章节标题 `1 绪论` 内容可能要清理，但它可能是正文一级标题的唯一可见样式代表；
- 示例图题、表题、公式编号可能是假内容，但它们可能证明了本校 caption/numbering 样式；
- 红色说明文字本身应删除，但它附近可能说明了后续 slot 的格式要求。

如果 Agent 只能看到结构对象和原始文本，它容易做出两个错误：

1. 把样例当噪声直接删掉，导致最终模板丢失可捕获的样式代表；
2. 把所有可见格式都当成下游样式义务，导致固定内容外观、说明格式和 Style Contract 混在一起。

Style Evidence 层的目标就是在删除、清理、slot 物化、正文结构物化之前，给 Agent 一个可读的
样式事实视图和风险视图。

## 3. 它不是什么

Agent-facing Style Evidence 不是以下东西：

- 不是 OOXML dump；
- 不是让 Agent 手写 Style Contract；
- 不是 Registry 自动匹配器；
- 不是学校语义分类器；
- 不是视觉复核的替代品；
- 不是发布工具；
- 不是每个 run 都必须单独判断的样式流水账。

它只回答：

```text
这个对象或范围有什么有效样式事实？
这些样式事实从哪里来？
文档里还有没有相同或相近的 surviving representative？
如果删除或清空它，会不会丢失某类样式证据？
这些事实更适合支持 slot/member 代表选择，还是只是固定外观/说明/噪声？
```

最后一项只能作为风险提示和候选解释，不能成为 Tool 的语义裁决。

## 4. 当前做得不好的地方

当前工具体系已经有一些样式能力，但它们还没有形成清晰的 Agent-facing Style Evidence 层。

### 4.1 样式事实分散在不同能力里

当前工具体系已经有结构取证、编辑和 publication/style capture 能力。问题不是缺少底层读取，
而是这些能力没有统一翻译成 `docfit_evidence(focus="style_evidence")` 这种 Agent-facing 证据视图：

- 结构取证更偏底层对象事实；
- 编辑能力更偏候选修改动作；
- publication/style capture 发生在最终发布阶段，属于 Harness internal publish；
- Agent 在“删除某个对象前”缺少一个高信号样式风险摘要。

结果是 Agent 可能在做清理决策时还不知道：这个准备删除的对象是否是唯一可用样式代表。

### 4.2 返回层级不够贴近 Agent 判断

Agent 不应该通过底层样式属性自己推理：

```text
styleId + basedOn + direct formatting + pPr + rPr + numbering + border
```

它需要的是：

```text
有效样式：黑体，小三，居中，段前 24pt，段后 18pt
样式来源：命名样式 + 局部直接格式
相似对象：p88、p120
唯一性：不是唯一代表
删除风险：低
适合用途：可能支持 section heading representative
```

当前能力更像“结构和样式都能查到”，但还没有稳定表达“这个事实如何影响删除、保留和代表选择”。

### 4.3 缺少删除前风险反馈

模板整理最常见动作是删除说明、样例和残留。真正需要提前挡住的是这类风险：

- 删除前没有 surviving representative；
- 删除对象是某个候选 Registry field 的唯一值位样式；
- 删除对象是某类 body heading/caption/list/equation 的唯一代表；
- 清空文本会保留样式，但删除整个段落/表格会丢样式承载者；
- 删除说明文字前，说明中的格式规则还没有迁移到真正承载者。

这些都不是学校语义裁决，而是机械可提取的风险提示。

### 4.4 样式合同发生太晚

最终 Style Contract 应该从 final Word 的 Registry-bound slots/members 捕获，这个方向是对的。
但如果只有最终捕获，Agent 在前面选择和删除代表对象时就缺少反馈。

理想状态是：

```text
编辑前：Style Evidence 帮 Agent 判断代表对象是否合理、删除是否安全
发布时：Style Capture 从最终 Word 捕获可执行 Style Contract
```

前者是证据，后者是交付合同。不能混成一个工具。

### 4.5 容易混淆固定外观和下游 Style Contract

固定学校内容的字体、表格线、页眉页脚、分页和装饰属于固定内容保留义务；只有 Registry-bound
slot 或 body member 的代表样式才进入下游 Style Contract。

当前如果没有明确 Style Evidence 层，Agent 容易把“看见了样式”误解成“要生成样式合同”。

## 5. 好的目标形态

Style Evidence 不应第一轮独立成 Agent-visible Tool。它应作为 `docfit_evidence` 的一个高层 focus：

```text
docfit_evidence(focus="style_evidence")
```

名字不是关键，关键是返回内容的抽象层级。只有当 trace/eval 证明它的权限、schema、返回体规模或失败恢复
必须独立时，才考虑把这个 focus 拆成新的 Agent-visible Tool。

### 5.1 典型输入粒度

合适的输入粒度是 Agent 已经选中的对象、范围或候选操作，而不是全篇每个 run：

| 输入意图 | 示例 |
| --- | --- |
| 查看对象样式 | 某个 paragraph/table cell/SDT/object_ref |
| 查看范围样式 | 封面题名区域、摘要标题区域、正文代表区 |
| 删除前风险检查 | 准备删除的说明/样例对象列表 |
| slot 代表检查 | 候选 `title.zh`、`author.name` 等目标承载对象 |
| body member 代表检查 | 候选一级标题、正文段落、图题、表题、公式、列表 |
| 相似样式搜索 | 找与某对象有效样式相近的 surviving representatives |

不要把它设计成“对文档内每个 XML object 生成一张语义判定表”。Agent 的语义范围仍由 Agent 选择。

### 5.2 典型输出内容

Style Evidence 的输出应包含：

- 文档 hash 和 snapshot 绑定信息；
- 查询 scope 和参与对象；
- 每个对象的可读 effective style summary；
- 样式来源：命名样式、继承、直接格式、表格样式、编号样式等；
- 段落、字符、表格、边框、编号、缩进、间距等可物化属性；
- 与相邻固定标签、值位、说明文字、样例文字的关系；
- 相似样式组和 surviving representatives；
- 唯一样式承载风险；
- 删除/清空/物化 slot/物化 structure 对样式证据的影响；
- 可追溯 object refs、locator、页码或 visual evidence refs；
- 风险级别和需要 Agent 再判断的问题。

示例形态：

```yaml
status: ok
document_sha256: "<sha256>"
scope:
  object_refs: ["obj-..."]
style_evidence:
  - object_id: "obj-..."
    text_sample: "（请在此填写论文题目）"
    effective_style_summary:
      font_family: "SimSun"
      font_size_pt: 16
      bold: false
      alignment: "center"
      underline: "single"
      paragraph_spacing: "..."
    style_sources:
      named_style: "Normal"
      direct_formatting: ["font_size", "underline", "alignment"]
    nearby_relations:
      previous_label: "论文题目："
      relation: "label_value_pair_candidate"
    similar_surviving_representatives: []
    uniqueness:
      is_unique_candidate: true
      reason: "No surviving object with equivalent title value style was found."
    deletion_risk:
      level: "high"
      reason: "Removing this paragraph may remove the only title value style carrier."
    agent_questions:
      - "If this is a real fill interface, materialize it as a Registry-bound slot before deleting sample text."
```

这类输出仍然不说“它就是 `title.zh`”。它只说：如果 Agent 判断它是 `title.zh` 的承载者，
那直接删除会有样式风险。

### 5.3 与视觉证据配合

Style Evidence 不是视觉复核。它告诉 Agent 有哪些有效样式事实和风险；视觉证据告诉 Agent 页面上
实际看起来怎样。

好的组合是：

```text
docfit_evidence(structure/object_context) 找对象
docfit_evidence(style_evidence) 看样式事实和删除风险
docfit_evidence(visual_region) 看页面视觉关系
Agent 判断责任与 Registry-bound 代表
docfit_check(action_plan) 检查计划是否可执行
docfit_apply 执行清理或物化
docfit_evidence(render/visual_region) + docfit_check(completion_gate) 做最终复核
Harness internal publish/style capture 捕获 Style Contract
```

## 6. 与 Style Contract 的边界

Style Evidence 和 Style Contract 必须分开：

| 层 | 时间点 | 责任 | 产物性质 |
| --- | --- | --- | --- |
| Style Evidence | 编辑前、修改中、代表选择时 | 给 Agent 样式事实、相似组和风险 | 判断证据 |
| Style Contract Capture | 最终 Word 确认后 | 从 Registry-bound slots/members 捕获可执行格式合同 | 下游交付合同 |

Agent 可以根据 Style Evidence 选择或修正代表对象；Agent 不应该根据 Style Evidence 手写最终
Style Contract。最终 Style Contract 必须从 final Word 中重新捕获，并与 Fill Contract 以 digest
绑定。

## 7. 推荐的判断边界

Style Evidence 层可以给出以下风险或候选提示：

- `unique_style_carrier`
- `has_surviving_representative`
- `style_similar_to_body_heading`
- `style_similar_to_slot_value`
- `style_mostly_instruction_noise`
- `style_conflicts_with_candidate_role`
- `clear_content_safer_than_remove_object`
- `representative_requires_visual_review`

但它不能输出以下结论：

- `this_is_title.zh`
- `delete_this`
- `bind_this_registry_field`
- `publish_style_contract`
- `school_requires_this_format`

这些仍然是 Agent 结合学校材料、Registry、结构证据、视觉证据和 Skill 后做出的判断。

## 8. 何时算做得好

一个好的 Agent-facing Style Evidence 层应满足：

- Agent 不需要读取 OOXML 就能理解有效样式；
- Agent 在删除样例/说明前能看到样式承载风险；
- Agent 能知道是否已有相同或相近 surviving representative；
- Agent 能区分固定外观保留义务和下游 Style Contract 义务；
- Agent 能把样式证据挂到 Registry-bound slot/member 代表，而不是先建立泛化“呈现责任”；
- Tool 输出短而可追溯，详细属性可按需展开；
- Style Evidence 不生成、伪造或替代最终 Style Contract；
- Harness/publish 仍然从 final Word 重新验证和捕获交付合同。

## 9. 初始落地建议

第一步不新增新的 Agent-visible Tool。更稳妥的方式是在 `docfit_evidence` 中增加
`style_evidence` focus，验证 Agent 是否真的能用这些证据改善删除和代表选择。

如果后续发现样式证据查询足够独立、输入输出稳定、返回体过大或需要专门风险模型，再提出单独拆分
Agent-visible Tool 的 ADR。默认不拆。

无论采用哪种形式，对外语义都应保持一致：

```text
Style Evidence 提供样式事实和风险；
Agent 负责责任判断和代表选择；
docfit_check 负责机械闭包和计划检查；
docfit_apply 负责受控候选修改；
Harness internal publish/style capture 负责最终 Style Contract；
Harness 负责发布门禁。
```
