---
name: docfit-school-extract
description: 逐对象理解和整理学校论文 Word，直接清除说明/示例并物化必要内容槽，检查结构与局部视觉反馈，最终只发布一份可填写 Word。
---

# 学校模板整理

你的目标不是复刻 Registry，也不是产出一份分析报告，而是把当前学校 Word 整理成一份真正干净、
可填写、保留学校固定版式的最终模板：

```text
output/final-template.docx
```

你对语义判断、修改范围和最终质量负责。Tool 提供对象、修改能力、机械回读和局部视觉反馈；它不替你
判断某段内容是否该删，也没有独立的语义检查器。

## 核心循环

1. 调用 `template_view open`。它从应用 checkpoint 恢复最新 Word 和当前视觉游标，但不会恢复旧
   Agent transcript。默认只返回一个目标对象裁剪图，以及该对象、父对象和有界的必要邻接对象；
   不返回整页图片、整页对象清单或完整 Registry。`checkpoint_summary` 是已提交槽位/结构的短摘要：
   用它判断已有正文结构是否需要被更完整的代表块替换，并持续检查
   `toc.refresh_needed` 是否已变为 false。`style` / `format_hint` 只提供当前判断所需事实。
   若 `pending_edit_intents` 非空，它表示你在旧会话中已请求、但从未提交成功的语义编辑；先用当前引用
   重新定位并完成它，再刷新目录或发布。这是你自己的失败操作意图，不是 Tool 的语义判断。
2. 根据当前裁剪图判断这个局部区域中哪些对象是学校固定内容、可填写值、应删除的说明/示例。只
   处理你在这张图和局部对象中能够明确识别的对象；Tool 的区域导航不替你做语义分类。空白或
   含义不明确的 run 必须结合其 `parent_context` 标签判断字段，不得仅按相邻空白对象的出现顺序
   猜测“题目”“姓名”等对应关系。
3. 把当前局部区域、同一 `document_ref` 上已经判断清楚的对象合并成一次 `template_edit`：普通对象可批量
   `materialize_slot`、`normalize_format`、`remove_object` 或 `clear_content`；正文代表单元用一次
   `materialize_structure`；目录复合域用一次 `refresh_toc`。若稍后看到更完整的代表章节，再次
   `materialize_structure` 会原子替换旧结构，不会生成第二份。不要为同一区域的每个对象各开 Tool 回合。
4. 已经确信 Registry `field_id` 时直接随 `materialize_slot` 提交；只有字段含义不确定时才调用
   `template_registry`。同一区域有多个不确定对象时，在一次调用中批量查询；每个对象只返回精确
   字段或最多五个候选。Registry 是词典，不是待办清单。
5. `template_edit` 原子执行整批操作、重开 Word、逐项检查效果，保存最新文档 checkpoint，并自动
   返回修改目标附近的裁剪图和新对象引用。直接检查结果图：正确则调用 `template_view next`，传回
   它的 `region_ref` 和 `region_outcome=handled`；有残留或误伤则基于新引用再处理。若当前区域确实
   只有必须原样保留的学校固定内容，可用 `region_outcome=preserve` 并给出简短理由。不得用 preserve
   跳过写作说明、示例/学生内容，或尚未建立填写接口的学生撰写区域。
6. `next` 只推进到下一个尚未遍历的物理视觉区域，不判断语义。只有当前裁剪确实缺少判断依据时才
   使用 `search` 或 `focus`；不要请求整页、逐页加载，也不要对刚由 `template_edit` 返回的区域重复
   `focus`。
7. Agent 可见的 `object_ref` 只是当前 checkpoint 上的短 `object_id`；修改后旧 ID 自动失效，继续操作必须
   使用最新 Tool 结果中的引用，不要复制或猜测文档 hash/fingerprint。会话达到上下文
   边界或 backend 切换时，新会话从最新 Word、视觉游标和待复核区域继续，不从封面重做，也不加载
   已处理图片历史；未提交的语义编辑意图则通过 `pending_edit_intents` 继续。内部版本不是用户产物。
8. 当你根据实际修改区域的反馈确认模板干净、可填写且版式正常后，直接调用 `template_publish`。
   发布没有全页打卡门禁，最终只能发布一次、只发布一份 Word。

## 对象判断

优先保留学校身份和制度责任：校名、固定封面标签、声明原文、学校表格、页眉页脚、节设置、目录
机制和样式骨架。优先清理会污染学生成稿的内容：

- 操作说明、编写提示、格式讲解和括号中的指导文字；
- 示例题目、示例摘要、示例关键词、示例章节、示例图表、示例参考文献；
- 只用于展示格式的样本文本、目录缓存示例和多余占位词；
- 删除样例后遗留的空白页、孤立标题、错误分页或无意义空段落。

一个对象看起来像标题，不代表它就是填写槽。先判断它是固定标签、结构标题、学生值还是示例。
若标签和值在同一段，聚焦到具体 run：保留标签 run，把值/空白 run 物化为槽。不要为了方便而
清空整个段落。

对每个学生实际要填写的内容区，清理样例后必须留下至少一个可填写槽。不能只保留“参考文献”、
“致谢”或“第 X 章”等标题，却把它们下面的学生内容承载位一起删掉。在同一批中，选一个格式
最合适的样例对象物化为槽，再批量删除其余说明和样例。常见承载字段包括 `abstract.zh`、
`abstract.en`、`references.entries`、`appendix.body`、
`achievements.entries` 和 `acknowledgement.body`；只根据当前对象判断，不需要遍历这个列表。

## 内容槽

`materialize_slot` 会内部完成 Registry 字段校验、`alias/tag`、唯一 slot ID、可见填写占位、格式保留、包重开、
效果回读和新版本创建。你只在当前批次操作中提交 `object_ref` 与已经判断好的 `field_id`，不写
决定文件，不调用 compiler，也不管理 DOCX 路径。

目标已有可见示例文字或空白时，物化会用 Registry 的 Human 可读标签替换为可见填写占位，后续填充时
整体替换。占位协议只有 `【字段标签】`，不添加灰色、底纹或 `w:showingPlcHdr`；学校对象原有的实际
字体、字号、段落和容器样式仍作为槽值样式保留。字段匹配仍由你判断。若最多五个 Registry 候选仍无法区分，结合当前标签、上下文和
可选书面要求继续判断；确有实质歧义再询问用户。

当前对象的红、蓝或其他颜色是语义证据，不是全局删除规则。判断颜色只用于标示说明/示例、而非学校
正式版式时，在 `materialize_slot` / `materialize_structure` 成员中提交
`clear_direct_format: ["color"]`，或对固定文字使用 `normalize_format`。Tool 只移除直接颜色，保留学校
字体、字号、段距等其余样式；颜色本身有正式含义时不提交该选项。

## 正文代表结构

正文不是一个大字符串槽，也不是把 Registry 的所有 `body.*` 字段逐一塞进学校 Word。看到一个能够
代表学校正文体系的局部章节时，按需读取 `references/body-structure.md`：只选择当前章节中确实出现且
样式不同的对象，逐个映射为代码内置的 `body.heading.level1/2/3`、`body.paragraph` 等语义类型，然后
用一次 `materialize_structure` 将这些按文档顺序选择的代表对象物化为 `body.chapters`。成员不要求
相邻：Tool 只提取被选中的学校对象，夹在中间的写作说明和冗余样例仍留给后续清理。不要因为先看到
H2 和一个正文段落就过早锁定不完整结构；继续查看当前章节，直到找到能代表该校层级体系的 H1、
H2、H3 和正文对象。
裁剪图可能同时包含 H1 前后的视觉邻近对象；用响应中的 `document_order` 核对物理顺序，只选择位于
当前代表 H1 之后、属于同一章的 H2/H3/正文，Tool 不会据此替你判断语义。
Tool 保留每个学校对象的真实样式并建立成员槽；后续正文可以按这个结构重复。语义映射由你负责，
Tool 只检查 Word 对象是否能承载该类型。后续发现更完整的代表块时直接替换旧结构。看到视觉样式
不同的正文标题或复合对象，而其语义类型尚未出现在 `checkpoint_summary.materialized_fields` 时，不要
当作重复样例删除；先保留并继续导航，直到找到可按物理顺序提交的更完整代表对象集。
源目录和正文若共同展示了具名首章或末章，例如“第一章 文献综述”和“第 X 章 结论与展望”，它们
是学校模板的独立章节地标，不是普通重复样例。保留对应正文标题位置并加入代表目录；中间可重复
章节仍只保留一套完整的 H1/H2/H3/正文能力结构。
保留具名地标不等于保留该页的样例和说明：它们下方的红蓝格式文字、`×××`样文和写作指导仍应清理；
需要学生填写的章内容必须留下一个真正正文样式的 `body.paragraph` 槽，不能把写作说明当成正文。

## 删除与清空

- 一整段说明或示例都不应存在：用 `remove_object`。
- 容器、边框、行距、表格单元格或固定标签必须保留，只去掉内部示例值：聚焦更小的 run 后用
  `clear_content`，或将该 run 直接物化为槽。
- 删除后检查相邻对象，防止标题失去正文、分页断裂、表格行列缺口、目录或声明被误伤。
- Tool 的“修改已提交”只代表机械执行成功；语义和视觉是否正确仍由你根据新反馈判断。
- 目录页中的点引导线和章节列表是复合域的可见缓存；不要逐行 `clear_content`。完成最终标题结构后，
  对目录域调用一次 `refresh_toc`，提交应在模板中可见的标题对象及 1–3 级层级，让 Tool 保留真实 TOC
  域、复用 `TOC 1/2/3` 样式并生成非空代表缓存。
- 每次新会话都查看 `checkpoint_summary.toc.sample_marker_count`；大于 0 表示目录缓存仍含 `XXX`、
  `XX` 等学校样例，不能发布。合法的“第 X 章”章节号占位本身不是残留。目录在流程前部出现也不能
  把这项工作只留在旧会话记忆里。
- `checkpoint_summary.toc.missing_body_heading_types` 来自你已经物化的正文语义对象；非空时，目录尚未
  展示正文所支持的标题深度。`pending_generated_content.required_body_heading_candidates` 中的对象必须
  按对应 1–3 级加入代表缓存，直到 `toc.refresh_needed` 为 false。
- 视觉区域完成后若目录仍待刷新，`open`/`next` 会用 `pending_generated_content` 一次返回目录目标、
  目录裁剪图和有界标题候选。候选不是 Tool 的语义结论；由你选择应进入本校模板的标题、指定 1–3 级，
  然后在一次 `refresh_toc` 中提交，不再用多轮 `search/focus` 拼装引用。
- 固定标题与蓝/红色字号说明在同一段时，保留标题 run，批量删除说明 run；不得因为整段也含固定标题就
  把说明一并保留。

## 视觉反馈

- `open` 和 `next` 一次只给一个目标对象裁剪图、父对象和必要邻接对象。
- `focus` 一次只给一个具体对象的局部图；默认导航已经提供足够上下文时不要重复调用。
- `template_edit` 总是优先把修改目标附近的裁剪图作为反馈返回。先看这张图，再决定继续修改还是 `next`。
- 没有“最终必须看完每一页”的规则。检查范围由你根据实际对象、修改影响和疑点决定；不为覆盖
  率重复加载无关图片。

LibreOffice 页面是近似反馈，不是 Word 像素级认证；但已知视觉问题不能被忽略或用“工具通过”
掩盖。

## 常见错误

- 把 Registry 当成 54 个（或任何数量的）必做槽位；
- 先写决定文件，再编译，再把路径交给 Tool；
- 把旧 `object_ref` 误当成新 checkpoint 对象；
- 一个区域已经支持多个明确决定，却为每个对象分别 focus/edit/review；
- 只增加内容控件，不删除说明和示例；
- 只删除说明和示例，却没有给学生内容区留下可填写槽；
- 把固定标签、章节标题、参考文献标题误当成学生填写值；
- 不看 `template_edit` 自动返回的修改后区域图；
- 在全部内容完成前发布 Word，或把内部版本当作多份候选 Word 交付。

## 按当前信号加载知识

不要在开始时一次读取所有 Reference。只当当前区域/对象命中下列信号时，用 `Read` 加载对应短文：

| 当前信号 | 读取 |
|---|---|
| 不确定对象是固定标签、学生值还是示例，或不确定字段方向 | `references/object-decisions.md` |
| 要删说明/样例或建立封面、摘要、正文、参考文献、致谢填写区 | `references/cleaning-and-fill-interfaces.md` |
| 当前出现多个重复章节、正文各级标题/段落/图表公式样例，需要保留一个可复用章节 | `references/body-structure.md` |
| 当前出现目录、点引导线、页码、题注、字段缓存或交叉引用 | `references/generated-content.md` |
| 删除对象靠近分页/分节/表格边界，包含图表公式书签，或产生异常空白页 | `references/boundaries-and-object-safety.md` |

读完只应用于当前对象/局部区域；不把 Reference 里的案例数量、学校结构或验收步骤当成每个任务的全局待办清单。

## 完成输出

发布成功后，structured output 必须与 `template_publish` 和磁盘一致：

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

确有无法消除的实质歧义时才返回 `blocked`，产物路径和 hash 必须为 null，不伪造 Word。
