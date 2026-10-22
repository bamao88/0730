# final-generation 模块设计

状态：草案

上层边界见：[final-generation 顶层架构契约](./final-generation-architecture-rfc.md)。

本文档是下一层设计，只回答 final-generation 模块内部如何组织成稿。  
它不讨论学生内容如何抽取、学校模板如何理解，也不展开具体 OOXML 操作和报告 schema。

## 1. 模块输入和输出

final-generation 消费已经准备好的输入包：

| 输入 | 用途 |
| --- | --- |
| Registry 身份 | 校验学生内容包、模板包和样式策略使用同一语义坐标 |
| 学生内容包 | 提供内容、正文顺序、复杂对象搬运引用和内容关系 |
| 学校模板包 | 提供可写目标、保留/删除/生成区域和学校样式证据 |
| 样式策略 | 提供 style profile、complete school candidates、known gaps、已批准 preset 和选择规则 |

模块输出：

| 输出 | 含义 |
| --- | --- |
| `candidate.docx` | 已完成可确定成稿工作的候选 Word |
| `final.docx` | 全部 required 条件通过后的发布 Word |
| 运行报告 | 说明输入、placement、样式、对象、域、渲染和最终状态 |

## 2. 内部视图

模块先把输入包转成三类内部视图。

| 视图 | 作用 |
| --- | --- |
| 内容视图 | 区分正文流、非正文字段、生成内容来源、待复核内容 |
| 模板目标视图 | 区分字段目标、正文入口、保留区、删除区、生成区 |
| 样式视图 | 列出本次实际出现的内容角色，以及每个角色的 candidate / known gap / preset 证据 |

这三类视图都来自输入包，不重新做语义判断。

## 3. 执行顺序

模块内顺序固定为：

```text
输入门
-> 建立内容视图
-> 建立模板目标视图
-> 建立样式视图
-> 生成 placement
-> 写入内容
-> 整理 Word 结构
-> 应用样式
-> 处理 Word 动态域
-> 质量门
-> 发布 candidate / final
```

关键约束：

- placement 之前必须先有内容视图和模板目标视图。
- 样式选择必须在写入前确定；样式应用发生在内容写入和结构整理之后。
- Word 动态域依赖最终标题、题注、编号和分页，所以必须在内容和样式之后处理。
- 质量门只判断本次成稿结果，不回头修学生内容包或模板包。

## 4. Placement 设计

placement 是本模块的核心连接结果。

它把学生内容和模板目标连接起来：

```text
content_id + field_id + source_order
  -> placement
  -> slot_id / region_id + action + style role
```

placement 必须显式表达每个范围内对象的处置：

| 对象 | 必须回答 |
| --- | --- |
| 学生内容 | placed、retained、excluded、manual、unresolved 或 blocked |
| 模板目标 | filled、retained、removed、generated、manual、unresolved 或 blocked |

正文流按 `source_order` 作为一个整体进入正文入口；不能把正文拆成无序字段逐个填槽。

## 5. 样式设计

样式在内容角色级别决策。

| 输入证据 | 决策 | final 资格 |
| --- | --- | --- |
| role 有 complete school style candidate | 使用 school | 可进入 final，前提是写入和校验通过 |
| role 没有 candidate，且模板包明确记录该 role 为 known gap；preset 完整可用 | 使用 preset | 可进入 final，前提是写入和校验通过 |
| role 有 candidate，但 candidate 冲突、过期、残缺或不可校验 | blocked | 不能进入 final |
| role 没有 candidate，也没有 known gap | blocked | 不能进入 final |
| role 有 known gap，但 preset 不完整或不可写入校验 | blocked | 不能进入 final |

完整 school style 不是 final-generation 临场判断出来的。它必须是学校模板包提供的事实：某个 role 有绑定当前模板、Registry 和样式 profile 的 complete school style candidate。这个 candidate 至少满足：

- 覆盖该 role 的必需样式属性闭包；
- 每个属性都有可执行值，或被 profile 明确允许为 N/A；
- 没有 unresolved、conflict、stale digest 或缺失证据；
- 能被编译成最终可写入、可回读校验的 style contract。

如果模板包只声明 known gap，说明模板阶段已经确认学校样式不足，本模块才可以使用 preset。  
如果模板包给出了候选但候选本身不可信，本模块不能把它当作“没有 school style”而自动 fallback。

样式视图必须为每个实际 role 记录：

- role identity；
- 使用的 style profile；
- school candidate digest，或 known gap id；
- preset id / version / digest；
- 最终选择 source；
- 不能选择时的 blocked reason。

设计约束：

- 同一个 role 不能混用 school 和 preset。
- 学生源文档样式不是最终样式来源。
- 样式决策必须能追踪到 role、来源、版本或 digest。
- 写入后必须能按 occurrence 校验样式是否落到最终 Word 中。
- 样式写入或校验失败时，不能自动换用另一个来源；只能进入报告。

## 6. 对象处理

复杂对象按 Word 对象处理，不按纯文本处理。

| 对象 | 模块原则 |
| --- | --- |
| 表格 | 从学生源搬运结构和内容，最终样式来自 school 或 preset |
| 图片 | 从学生源搬运图片对象，最终尺寸、对齐和题注关系由目标规则决定 |
| 公式 | 保留公式结构，最终对齐、编号和溢出处理由目标规则决定 |
| 题注 | 与图、表、公式关系绑定，不能只当普通段落 |

如果复杂对象没有可执行搬运引用，本模块不能降级成纯文本 final。

## 7. Word 动态域

目录、图目录、表目录、页码、交叉引用属于 Word 动态域。

模块原则：

- 保留 Word field 结构；
- 不把动态域替换成静态文本；
- 在内容写入、结构整理和样式应用之后处理；
- 不能证明动态域可用时，只能产出 candidate 或 blocked 报告，不能产出 final。

## 8. 质量门

`final.docx` 必须通过这些 required 门：

| 质量门 | 判断对象 |
| --- | --- |
| 输入门 | 输入包身份一致，Registry 绑定一致 |
| Placement 门 | 内容和模板目标都有非 unresolved / blocked 的明确处置 |
| 内容门 | 应写入内容没有丢失，待复核内容没有静默写入 |
| 样式门 | 每个实际 role 都有基于 candidate / known gap / preset 的可追踪决策，且写入校验通过 |
| 对象门 | 表格、图片、公式没有降级或丢失 |
| 动态域门 | Word field 保留，并已有可发布的刷新或可刷新证据 |
| 渲染门 | 当前 Word 结果可打开、保存、渲染并绑定报告 |

未通过 required 门时，模块可以产出 `candidate.docx`，但不能发布 `final.docx`。

## 9. 非目标

本设计不引入：

- final-generation Agent；
- 上游学生内容补抽取；
- 上游模板语义补理解；
- 历史学校规则回退；
- 学生源样式到目标样式的推断；
- school 和 preset 的逐属性混合。
