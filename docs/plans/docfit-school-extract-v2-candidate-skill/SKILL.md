---
name: docfit-school-extract
description: 逐对象理解和整理学校论文 Word，直接清除说明/示例、物化必要内容槽、维护生成内容与分页边界，并最终只发布一份可填写 Word。凡是准备、清理或提取学校论文模板都应使用本 Skill。
---

# 学校模板整理

把当前学校 Word 整理成一份真正干净、可填写、保留学校固定版式的最终模板：

```text
output/final-template.docx
```

你负责语义判断、修改范围和最终质量。Tool 负责对象身份、Word 执行、结构安全、有效结果回读、
局部视觉反馈和最终全页图片；不要把 Tool 返回的样式、风险或成员事实当成语义结论。

## 先判断当前阶段

本任务有四个顺序阶段。局部对象判断与最终逐页检查解决的是不同问题，不能混在同一阶段：

| 阶段 | 目标 | 允许的视觉范围 | 结束条件 |
|---|---|---|---|
| A. 局部对象处理 | 判断当前对象应保留、删除、物化还是修正 | 当前对象、父对象、必要邻接对象和修改后局部反馈 | `navigation.done` |
| B. 收尾 | 处理未提交意图和目录等生成内容 | 仍只看完成当前收尾决定所需的有界局部 | 无 `pending_edit_intents`，生成内容已完成 |
| C. 最终视觉自检 | 检查最终 Word 的整篇渲染结果 | 最终 `document_ref` 的每一页原生全页 PNG | `coverage_complete: true` 且未发现缺陷 |
| D. 发布 | 发布已经完成终局检查的精确版本 | 不再产生新的判断证据 | `template_publish` 成功 |

阶段 A/B 禁止逐页巡检，因为整篇视觉信息会污染当前对象的语义判断并扩大上下文。阶段 C
必须逐页检查，因为文本、XML 和局部图不能发现跨页裁切、重叠、缺字、表格损坏、分页漂移或
页眉页脚错位。不要把任一阶段的规则外推到另一个阶段。

发现最终页面缺陷时，退出阶段 C，只为该缺陷回到有界的定位与编辑；编辑产生新
`document_ref` 后，旧版本的全页证据全部失效。完成局部修复和收尾后，从第一页重新进入阶段 C。

## 阶段 A：局部对象循环

1. 调用 `template_open()`，从最新应用 checkpoint 取得当前有界区域、短对象引用、事实摘要和
   未完成的 Agent 编辑意图。它不恢复旧 transcript，也不返回整篇图片历史。
2. 只判断当前目标、父对象和必要邻接对象。打开后应先编辑当前区域，或把确实固定的当前区域
   标记为 preserve；除非同一区域缺少一个必要事实，否则不要先搜索其他地标。
   `template_search` 不是模板盘点器。区分学校固定内容、学生值、写作说明、样例、生成内容、
   条件区和结构对象。标签与值同段时聚焦最小 run，不按空白对象的位置猜字段。

   摘要页在任何删除前先做一次视觉责任枚举：论文题目、固定“摘要/ABSTRACT”标题、摘要正文、
   关键词，当前页展示哪项就必须在同一视觉位置保留固定文字或建立填写接口。同一
   `thesis.title.zh` 已在封面物化，绝不代表摘要页题目可以删除；题目中的“论文题目/TITLE”与
   括号格式说明混在同段时，物化题目 run 并删除说明 run，不能删除整个题目位置。四项没有逐一
   落实前，不提交该摘要区域的删除操作，也不推进到下一 region。
3. 把同一 checkpoint 上已判断清楚的对象合并为一次 `template_edit`。每个 `operations` 成员
   直接声明一种动作：

   - `materialize_slot`
   - `materialize_structure`
   - `normalize_effective_format`
   - `refresh_toc`
   - `clear_content`
   - `remove_object`
   - `ensure_page_start`

   `template_edit` 顶层只允许一个 `operations` 数组；`action`、`field_id`、`object_ref` 等参数
   必须放在数组成员内。Tool 会吸收“删父对象 + 冗余删/清子对象”等重复操作；“删父对象 +
   要求子对象物化”是真冲突，需要修改决定。

   ```json
   {
     "operations": [
       {
         "action": "materialize_slot",
         "object_ref": {"object_id": "obj-..."},
         "field_id": "abstract.zh",
         "effective_format": {"color": "black", "underline": "none"}
       }
     ]
   }
   ```

   `materialize_slot` 只用于一个可以独立填写的值位置。当前学校已经证明标题、正文、列表、
   图表等对象共同构成可重复正文能力时，不要把这些 `body.*` 成员分别做成互不相关的 slot；
   使用一次 `materialize_structure` 把实际出现的成员按文档顺序纳入 `body.chapters`：

   ```json
   {
     "operations": [
       {
         "action": "materialize_structure",
         "object_ref": {"object_id": "obj-heading-1"},
         "field_id": "body.chapters",
         "members": [
           {"object_ref": {"object_id": "obj-heading-1"}, "field_id": "body.heading.level1"},
           {"object_ref": {"object_id": "obj-heading-2"}, "field_id": "body.heading.level2"},
           {"object_ref": {"object_id": "obj-body"}, "field_id": "body.paragraph"}
         ]
       }
     ]
   }
   ```

   `object_ref` 是其中一个成员锚点，`members` 只列当前学校实际证明存在的类型；不要为满足
   示例凭空补 H1/H2/H3。建立结构前先区分具名固定地标和普通可重复章：`第一章 文献综述`、
   `第X章 结论与展望` 等具名标题可以保留，但 `第X章（正文标题）` 这类通用中间章样例是可填写
   `body.heading.level1` 的直接证据。模板已展示通用章标题时，不得先建立一个缺少该成员的正文
   结构，也不得随后把该通用章标题当说明文字删除。固定首章/末章地标下的单个填写位置仍可
   独立物化，但它不能替代中间可重复正文体系。

   `body-structure` 信号是“先收集同一普通章、再一次提交”的例外：当前对象一旦证明它属于通用
   中间章，不要先把 H1/H2/H3/正文分别物化，也不要先删除其中任何一个。先对该章向后的标题和
   正文做有目标的 search/focus，取得同一前向块的全部实际成员，再用一次
   `materialize_structure` 建立 `body.chapters`。固定首章或末章里的标题样例不得拿来拼接普通章
   结构；它们的固定标题保留，所需正文接口独立处理。
4. 新任务中每个 `field_id` 第一次使用前，都必须通过一次 `template_registry` 的精确 lookup 或
   对象相关 search 确认；把同一区域的多个请求合并查询。此后只有 Registry 或 checkpoint
   已明确给出的准确 ID 才能直接复用，绝不按命名习惯猜造。Registry 分栏项是扁平结构：
   `object_id` 与 `field_id` / `query` 同级，不使用嵌套 `object_ref`。
5. 查看 `template_edit` 返回的修改区域、`absorbed_operations`、边界回执、有效格式前后来源、
   `materialized_members`、`style_signatures` 和 `structural_risks`。这些是执行事实；根据当前
   学校语义判断结果是否正确。
6. 结果正确后调用 `template_next(region_ref, outcome="handled")`。当前区域确实只有应原样保留
   的固定内容时，使用 `outcome="preserve"` 并说明理由。不得用 preserve 跳过说明、样例或缺少
   填写接口的学生内容区。
7. 只有当前局部证据不足时才使用 `template_search(query)` 或
   `template_focus(object_ref, scope)`。本阶段不要逐页巡检，也不要对刚返回的修改区域重复 focus。
8. 旧 `object_ref` 在编辑后失效；继续使用新 checkpoint 返回的短引用，不复制或猜测 document
   hash/fingerprint。

## 对象责任

优先保留学校身份和制度责任：校名、固定封面标签、声明原文、学校表格、页眉页脚、节设置、
目录机制和样式骨架。优先清理会污染学生成稿的内容：

- 操作说明、编写提示、格式讲解和括号指导文字；
- 示例题目、摘要、关键词、章节、图表、公式和参考文献；
- 只用于展示格式的目录缓存样例、多余占位词和学生实例；
- 清理后无职责的孤立标题、空白页或空容器。

一个对象看起来像标题，不代表它是填写槽。先判断它是固定标签、结构标题、学生值还是示例。
每个需要学生填写的内容区在清理后都应保留明确的填写或生成接口；不能只留下标题。

具名章节和集合标题是学校的固定语义地标，不是通用学生标题槽。当前模板明确显示“文献综述”
“结论与展望”“参考文献”“附录”等固定文字时，保留该文字和所在标题样式；即使章号暂写为
`X`，也不要把整段物化成 `body.heading.level*` 而抹掉固定名称。只有 Registry 已有能精确承载
动态局部的字段且对象边界能只选中该局部时，才物化动态部分。固定标题下仍需另行保留或建立
对应内容接口。

“致谢”也是固定区域标题，不是学生正文。只要当前学校保留该标题，就必须保留一个
`acknowledgement.body` 填写接口。删除致谢样文前先复用其中一个真实正文段落建立该接口；不能
先删光样文，再凭空搜索已经不存在的内容位置。

## 内容槽、删除与清空

`materialize_slot` 内部处理 Registry 校验、唯一 tag、Human 可读括号占位、格式保留、包重开和
效果回读。只提交当前对象引用、字段 ID 和必要的有效格式结果；不写 YAML，不调用 compiler，
不管理中间 DOCX 路径。

可见占位只用 `【字段标签】`，不增加灰底、底纹或 `w:showingPlcHdr`。带下划线的空白 run 可能
用空格宽度形成填写线；物化后检查它没有缩成占位文字长度。同一语义值可以在多个视觉位置
出现；已有一个 `thesis.title.zh` 不代表摘要页的题名位置自动可填写。

每个 `remove_object` 提交前都要逐对象做一次“原位置职责”检查：如果删掉该对象会让当前页面
失去一个本应由学生填写的题名、摘要、关键词、正文或其他值位置，就必须在同一位置物化槽，
不能因为同一 `field_id` 已在封面或别页存在而删除。对某对象执行过精确 Registry lookup，说明
你已经识别了它可能承载的职责；随后只能根据当前局部证据把该对象物化为已确认字段，或明确
判定它只是固定标签/说明并保留或清理。不得查出 `thesis.title.zh` 后，仅因 checkpoint 已有一个
同名槽就删除摘要页题名。完成摘要类页面时逐一核对“题名 + 固定摘要标题 + 摘要正文 + 关键词”
四项，当前学校显示其中哪项，清理后该项就必须仍有固定内容或本页填写接口。

- 一整段说明或样例不应存在：使用 `remove_object`。
- 容器、边框、行距、单元格或固定标签必须保留，只去掉值：聚焦更小的 run 后使用
  `clear_content`，或直接物化该 run。
- 不逐行清空目录缓存；目录是复合生成对象。
- 删除成功只证明机械执行与结构校验通过；语义和视觉是否正确仍由你判断。

## 按信号加载知识

不得在开始时读取任何 Reference。`knowledge_signals` 只提示当前涉及哪类客观机制，不替你决定
删除或保留。必须等当前 Tool 反馈命中后，只读取对应的一张短卡；同一次判断即使出现多个信号，
也先按当前主要机制选择一张，其余等实际需要时再读：

| 信号或当前问题 | 读取 |
|---|---|
| 颜色、下划线、主题色、字符样式或 `effective.*.src` | [有效样式](references/effective-style.md) |
| 摘要/章节是否另起页，删除后空白页或重复分页 | [逻辑页起点](references/logical-page-starts.md) |
| 当前学校展示了正文标题、段落、列表、图表、公式等可复用体系 | [正文代表结构](references/body-structure.md) |
| 目录、点引导线、页码、题注、字段缓存或交叉引用 | [生成内容](references/generated-content.md) |
| 参考文献、附录、成果等集合或可选区 | [集合与可选区](references/collection-and-optional-sections.md) |
| 删除靠近节/页/表格，或含书签、字段、图片、批注、脚注 | [对象安全](references/object-safety.md) |

只把知识卡应用到当前对象或局部区域；卡片中的案例不是每个学校的全局清单。阶段 C 不为逐页
图片重新加载知识卡；只有发现具体缺陷并退回局部修复时，才根据新的局部信号按需读取。

## 阶段 B：收尾门禁

`navigation.done` 后不要立即发布。再次调用 `template_open()`，完成以下收尾：

- 解决全部 `pending_edit_intents`；它们是先前未提交成功的 Agent 语义意图，不是 Tool 猜测；
- 根据 `pending_generated_content` 一次性完成目录等生成内容，不逐行修改缓存；
- 检查当前学校已经展示的责任是否都有填写或生成接口；
- 确认没有为了清理样例而留下失去职责的标题、容器或空白页。

收尾时把 `checkpoint_summary` 当作 Agent 自己的责任账本逐项核对，而不是 Tool 的语义结论：

- 当前学校已确认普通中间章且展示多个正文成员时，`materialized_structures` 必须有且只有一个
  `body.chapters`；已确认的 H1/H2/H3/正文成员必须归属该结构，不能只出现在
  `materialized_fields` 中成为独立槽；
- 保留“致谢”固定标题时必须出现 `acknowledgement.body`；
- 保留附录、成果、参考文献等固定区域时，逐一核对本校已证明的配对接口；
- 缺少任何已确认责任时，回到对应有界对象修复；不得用目录条目数量或 `navigation.done` 代替
  语义完成检查。

只有 `navigation.done`、无 `pending_edit_intents` 且生成内容不再待处理时，才进入阶段 C。

## 阶段 C：最终逐页视觉自检

调用 `template_final_review(document_ref)`。第一次调用必须省略 `cursor`，不得发明 `start`、`0`
或 `page-1`；只有 Tool 返回 `next_cursor` 后才原样传回。该 Tool 只在收尾门禁满足后工作，并把精确最终版本按
顺序分批返回为原生全页 PNG。实际读取每一张图片；有 `next_cursor` 时，用同一
`document_ref` 和该 cursor 继续，直到 `coverage_complete: true`。

全页检查不是重新进行对象语义提取。只检查最终渲染缺陷：

- 文字、图片、公式或内容控件是否被裁切、重叠、缺失或替换成错误字形；
- 表格是否断裂、越界、列宽异常，图片和题注是否错位；
- 是否有异常空白、孤立标题、重复/缺失页面或错误分页；
- 页眉页脚、页码、节边界、目录和跨页间距是否异常；
- 说明、样例、旧缓存和无职责残留是否仍然可见。

读取原生全页图片，对可疑区域放大检查；不要用 contact sheet、图片 metadata、文本提取、
Office 校验或 OOXML 代替逐页视觉判断。

如果任何一页有缺陷：

1. 不调用 `template_publish`；
2. 用有界的 `template_search` / `template_focus` 定位该缺陷，只修改必要对象；
3. 检查修改后的局部反馈并完成收尾；
4. 对新的 `document_ref` 从头重新调用 `template_final_review`。旧 hash 的页面覆盖不能复用。

如果渲染失败，保留精确错误证据并判断是否能通过当前环境恢复。不得把渲染失败当成文档通过，
不得用旧 hash、局部图或结构检查补齐门禁。当前任务无法恢复固定渲染器时返回 `blocked`，不发布
未经最终逐页检查的 Word。

## 阶段 D：发布与交付

只有最终精确 `document_ref` 的全部页面已经实际检查且没有发现缺陷，才调用一次
`template_publish(document_ref)`。内部版本、全页 PNG、PDF 和 render evidence 只用于内部质检；
除非用户明确要求，不把它们作为交付物。唯一用户产物是 `output/final-template.docx`。

发布前确认：

- 学校固定内容与版式责任仍在；
- 当前学校展示的学生内容责任都有填写或生成接口；
- 已确认通用中间章及多个正文成员类型时，`body.heading.level*` 全部归属唯一
  `body.chapters`，固定首/末章不另留标题样例槽；
- 保留的固定可选区标题已有配对接口：附录同时有标题与正文，成果目录有集合条目；
- 没有未完成的 `pending_edit_intents` 或生成内容；
- `structural_risks` 已根据当前学校语义处理或接受；
- 最终逐页检查覆盖发布版本的全部页面，且没有已知视觉缺陷；
- 发布的精确 `document_ref` 就是完成全页检查的版本。

发布成功后 structured output 必须与 `template_publish` 和磁盘一致：

```yaml
status: built
artifact_path: output/final-template.docx
template_sha256: <sha256>
counts:
  slot: <实际物化数量>
  remove: <删除或清空数量>
  manual: <实际数量>
  gap: <实际数量>
  unresolved: <实际数量>
```

无法消除的实质语义歧义或无法恢复的最终渲染故障返回 `blocked`；此时产物路径和 hash 为 null，
不得暗示 Word 已通过最终视觉门禁。
