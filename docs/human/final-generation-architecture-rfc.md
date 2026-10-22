# final-generation 顶层架构契约

状态：草案

本文档只定义 final-generation 的上层边界：它接什么、做什么、交什么。  
具体 Word 写入顺序、样式属性物化、表格/图片/公式处理、Word 域刷新和报告 schema，属于下一层设计。

## 1. 核心结论

final-generation 是坐标对齐后的成稿模块。

```text
Registry 给统一语义坐标。
学生内容包把学生内容挂到 field_id。
学校模板包把模板目标挂到 field_id。
学校模板包发布 complete school style candidates 和 known gaps。
样式策略基于这些证据决定每个内容角色使用 school style 还是 preset。

final-generation 消费这些对象，产出 candidate.docx 或 final.docx。
```

它不重新抽取学生内容，不重新理解学校模板，不修复上游包缺口。

## 2. 输入对象

final-generation 接收三个产品对象，它们必须绑定同一个 Registry 身份。

| 输入对象 | 必须已经回答的问题 |
| --- | --- |
| 学生内容包 | 写什么、正文顺序是什么、复杂对象从哪里搬运 |
| 学校模板包 | 写到哪里、哪些区域保留/删除/生成、哪些 role 有 complete school style candidate，哪些 role 是 known gap |
| 样式策略 | 基于模板包的 candidates / gaps 和已批准 preset，决定每个内容角色最终样式来源 |

Registry 不是业务内容包，而是三者共同使用的语义坐标系。它只回答“语义上是什么”，不回答来源、目标位置或具体样式值。

## 3. 样式规则

样式选择只在内容角色级别发生：

```text
有 complete school style candidate -> 使用 school style
没有 candidate，且模板包声明 known gap -> 使用 preset
school candidate 冲突、过期、残缺或不可校验 -> 不能产出 final
school 和 preset 都不可用 -> 不能产出 final
```

两个约束：

- 最终样式不来自学生源文档。
- 同一个内容角色不能混用 school style 和 preset。
- final-generation 不自己判断“学校模板样式是否完整”；它只消费模板包发布的 complete candidate / known gap 证据。

## 4. 模块职责

final-generation 负责：

| 职责 | 含义 |
| --- | --- |
| 校验输入身份 | 学生内容包、学校模板包、样式策略绑定同一 Registry 和任务身份 |
| 连接内容与目标 | 根据共同的 `field_id` 把学生内容放入模板目标 |
| 保持正文顺序 | 正文按学生论文阅读顺序进入正文目标 |
| 应用样式策略 | 每个内容角色使用唯一的 school 或 preset 样式来源 |
| 产出 Word 结果 | 输出 candidate 或 final，并说明原因 |

final-generation 不负责：

- 重新抽取学生内容；
- 重新理解模板语义；
- 修复学生内容包或模板包；
- 发明缺失字段、缺失目标或缺失样式；
- 从学生源样式推断目标样式；
- 建立新的 Agent workflow。

## 5. 输出语义

| 输出语义 | 产物 | 含义 |
| --- | --- | --- |
| `candidate` | `candidate.docx` | 本模块已完成可确定的成稿工作，但仍有发布条件未满足 |
| `final` | `final.docx` | 输入、坐标连接、样式策略和 Word 结果都满足发布条件 |
| `blocked` | 报告，必要时无 Word 产物 | 输入或关键决策不足，不能生成可信候选 |

`candidate.docx` 不是失败产物；它是可人工验收的候选稿。  
`final.docx` 是发布产物，只能在本模块确认全部 required 条件满足后产出。

## 6. 下一层设计

本文档不展开实现。下一层设计单独放在：

- [final-generation 模块设计](./final-generation-module-design.md)
