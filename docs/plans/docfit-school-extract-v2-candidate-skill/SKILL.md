---
name: docfit-school-extract
description: 逐对象理解和整理学校论文 Word，直接清除说明/示例、物化必要内容槽、维护生成内容与分页边界，并最终只发布一份可填写 Word。凡是准备、清理或提取学校论文模板都应使用本 Skill。
---

# 学校模板整理

把当前学校 Word 整理成一份真正干净、可填写、保留学校固定版式的最终模板：

```text
output/final-template.docx
```

你负责语义判断、修改范围和最终质量。Tool 负责对象身份、Word 执行、结构安全、有效结果回读和局部视觉反馈；不要把 Tool 返回的样式、风险或成员事实当成语义结论。

知识加载有一道硬门禁：只有当前 Tool 反馈明确返回某个 `knowledge_signals` 值时，才读取下表对应的一张 Reference。没有信号就不读取；一次局部决定只读一张；不得因为整项任务最终可能涉及多个机制而预读、枚举或批量读取 Reference。违反这条门禁会污染当前判断上下文。

## 核心循环

1. 调用 `template_open()`，从最新应用 checkpoint 取得当前有界区域、短对象引用、事实摘要和未完成的 Agent 编辑意图。它不恢复旧 transcript，也不返回完整 Registry 或整篇图片历史。
2. 只判断当前目标、父对象和必要邻接对象。打开后应先编辑当前区域，或把确实固定的当前区域标记为 preserve；除非同一区域缺少一个必要事实，否则不要先搜索其他地标。`template_search` 不是模板盘点器。区分学校固定内容、学生值、写作说明、样例、生成内容、条件区和结构对象。标签与值同段时聚焦最小 run，不按空白对象的位置猜字段。
3. 把同一 checkpoint 上已判断清楚的对象合并为一次 `template_edit`。使用对应动作分栏：

   - `materialize_slots`
   - `materialize_structures`
   - `normalize_effective_formats`
   - `refresh_tocs`
   - `clear_contents`
   - `remove_objects`
   - `ensure_page_starts`

   `template_edit` 顶层只允许这些动作分栏；`field_id`、`object_ref` 等参数必须放在对应分栏的 item 内。Tool 会吸收“删父对象 + 冗余删/清子对象”等重复操作；“删父对象 + 要求子对象物化”是真冲突，需要修改决定。
4. 新任务中每个 `field_id` 第一次使用前，都必须通过一次 `template_registry` 的精确 lookup 或对象相关 search 确认；把同一区域的多个请求合并查询。此后只有 Registry 或 checkpoint 已明确给出的准确 ID 才能直接复用，绝不按命名习惯猜造。Registry 分栏项是扁平结构：`object_id` 与 `field_id` / `query` 同级，不使用嵌套 `object_ref`：

   ```json
   {
    "lookups": [
       {"object_id": "obj-...", "field_id": "thesis.title.zh"}
    ],
    "searches": [
       {"object_id": "obj-...", "query": "中文导师职称"}
    ]
   }
   ```

   Registry 是词典，不是待办清单。
5. 查看 `template_edit` 返回的修改区域、`absorbed_operations`、边界回执、有效格式前后来源、`materialized_members`、`style_signatures` 和 `structural_risks`。这些是执行事实；根据事实判断结果是否符合当前学校。
6. 结果正确后调用 `template_next(region_ref, outcome="handled")`。当前区域确实只有应原样保留的固定内容时，使用 `outcome="preserve"` 并说明理由。不得用 preserve 跳过说明、样例或缺少填写接口的学生内容区。
7. 只有当前局部证据不足时才使用 `template_search(query)` 或 `template_focus(object_ref, scope)`。不要逐页巡检，也不要对刚返回的修改区域重复 focus。
8. 旧 `object_ref` 在编辑后失效；继续使用新 checkpoint 返回的短引用，不复制或猜测 document hash/fingerprint。
9. 处理完当前学校实际展示的责任并确认局部反馈后，调用一次 `template_publish(document_ref)`。内部版本不是用户产物。

## 对象责任

优先保留学校身份和制度责任：校名、固定封面标签、声明原文、学校表格、页眉页脚、节设置、目录机制和样式骨架。优先清理会污染学生成稿的内容：

- 操作说明、编写提示、格式讲解和括号指导文字；
- 示例题目、摘要、关键词、章节、图表、公式和参考文献；
- 只用于展示格式的目录缓存样例、多余占位词和学生实例；
- 清理后无职责的孤立标题、空白页或空容器。

一个对象看起来像标题，不代表它是填写槽。先判断它是固定标签、结构标题、学生值还是示例。每个需要学生填写的内容区在清理后都应保留明确的填写或生成接口；不能只留下标题。

## 内容槽

`materialize_slots` 内部处理 Registry 校验、唯一 tag、Human 可读括号占位、格式保留、包重开和效果回读。只提交当前对象引用、字段 ID 和必要的有效格式结果；不写 YAML，不调用 compiler，不管理中间 DOCX 路径。

可见占位只用 `【字段标签】`，不增加灰底、底纹或 `w:showingPlcHdr`。带下划线的空白 run 可能用空格宽度形成填写线；物化后检查它没有缩成占位文字长度。

同一语义值可以在多个视觉位置出现。已有一个 `thesis.title.zh` 不代表摘要页的题名位置自动可填写；当前可见位置仍需单独判断和物化。

## 删除与清空

- 一整段说明或样例不应存在：放入 `remove_objects`。
- 容器、边框、行距、单元格或固定标签必须保留，只去掉值：聚焦更小的 run 后放入 `clear_contents`，或直接物化该 run。
- 不逐行清空目录缓存；目录是复合生成对象。
- 删除成功只证明机械执行与结构校验通过；语义和视觉是否正确仍由你判断。

## 按信号加载知识

不得在开始时读取任何 Reference。`knowledge_signals` 只提示当前涉及哪类客观机制，不替你决定删除或保留。必须等当前 Tool 反馈命中后，只读取对应的一张短卡；同一次判断即使出现多个信号，也先按当前主要机制选择一张，其余等实际需要时再读：

| 信号或当前问题 | 读取 |
|---|---|
| 颜色、下划线、主题色、字符样式或 `effective.*.src` | [有效样式](references/effective-style.md) |
| 摘要/章节是否另起页，删除后空白页或重复分页 | [逻辑页起点](references/logical-page-starts.md) |
| 当前学校展示了正文标题、段落、列表、图表、公式等可复用体系 | [正文代表结构](references/body-structure.md) |
| 目录、点引导线、页码、题注、字段缓存或交叉引用 | [生成内容](references/generated-content.md) |
| 参考文献、附录、成果等集合或可选区 | [集合与可选区](references/collection-and-optional-sections.md) |
| 删除靠近节/页/表格，或含书签、字段、图片、批注、脚注 | [对象安全](references/object-safety.md) |

只把知识卡应用到当前对象或局部区域；卡片中的案例不是每个学校的全局清单。

## 完成判断

发布前确认：

- 学校固定内容与版式责任仍在；
- 当前学校展示的学生内容责任都有填写或生成接口；
- 说明、样例、旧缓存和无职责残留已清理；
- `structural_risks` 已由你根据当前语义处理或接受；
- 目录、分页与删除后的局部图没有已知异常；
- 没有未完成的 `pending_edit_intents`；
- 发布的精确 `document_ref` 就是已检查版本。

发布成功后 structured output 必须与 `template_publish` 和磁盘一致：

```yaml
status: built
artifact_path: output/final-template.docx
template_sha256: <sha256>
counts:
  slot: <实际物化数量>
  remove: <删除或清空数量>
  manual: 0
  gap: 0
  unresolved: 0
```

只有无法从当前对象、模板、可选书面要求、Tool 反馈和按需知识中消除的实质歧义才返回 `blocked`；此时产物路径和 hash 为 null。
