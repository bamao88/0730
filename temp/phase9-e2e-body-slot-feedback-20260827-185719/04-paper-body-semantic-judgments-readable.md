# 04-paper-body Agent 语义判断结果（中文可读副本）

来源：

- 原始文件：`work/.docfit/harness/semantic-judgments.json`
- 原始副本：`04-paper-body-semantic-judgments.raw-copy.json`
- 样本根目录：`temp/phase9-e2e-body-slot-feedback-20260827-185719`

## 总览

- 单元：`u-paper-body`，正文模板单元。
- Agent 最终输出：`28` 条 semantic judgments。
- 覆盖范围：`53` 个 required reading blocks 全部覆盖，且每个 required block 只被一个 judgment 覆盖。
- 质量门反馈：发生过 `1` 次。反馈点是 Agent 先前把附录正文区域错误绑定成普通 `body.paragraph` 字段槽；最终版已修正。
- 最终状态：无 `needs_input`，无 `open_questions`。

Agent 最终汇总的中文意思：

> 只修正了 `jd-028`，其他 27 条判断保持不变，并且仍覆盖全部 53 个必须覆盖的 reading blocks。质量门反馈暴露的是“绑定意图错误”，不是学校语义判断冲突。Registry 中附录字段只有 `appendix.title` 和 `appendix.body`；其中 `appendix.body` 是 section/container，不是普通可填写 leaf field，也不存在 appendix paragraph leaf field。因此不能用 `body.paragraph` 凑字段。最终把 `jd-028` 改为附录正文区域的版式/样式载体：保留空段落作为样式承载，不绑定普通 Registry slot，也不返回 `needs_input`，因为学校语义证据本身已经足够。

最终净结果：

- 自动字段槽：15 类语义字段，发布后形成 23 个具体 slot 控件。
- 正文结构：1 个 canonical `body.chapters` 代表结构，外加 1 个 alternate 学科分支结构记录。
- 固定标题：保留 `参考文献`、`致谢`、`附录`。
- 附录正文：保留为 layout/style carrier，不绑定 `body.paragraph`。
- 模板说明：删除可见说明文字，但将规则迁移为样式或版式义务。

## 语义判断列表

### 1. `jd-001`：全局正文格式说明

- 覆盖 blocks：`u-paper-body:block-0001`
- 语义分类：`format_instruction`（格式说明）
- 处理方式：`delete`（删除可见说明）
- 字段绑定：无
- 结构绑定：无
- 中文判断：这一段是学校对正文整体格式的说明，包括固定 22 磅行距、上下页边距 2.54 厘米、左右页边距 2.6 厘米，以及 `□` 表示 1 个字宽 / 2 个字符空格。它是给作者看的格式规则，不是学生要填写的正文内容。因此清洁模板中删除这段可见文字，但这些格式规则必须迁移到文档或样式设置中。
- 中文原因：只有在格式语义已经迁移后，删除格式说明才是安全的；这一段是当前单元行距、页边距和字宽规则的来源。

### 2. `jd-002`：垂直间距说明段

- 覆盖 blocks：`u-paper-body:block-0002`、`0007`、`0010`、`0015`、`0018`、`0040`、`0044`、`0047`
- 语义分类：`format_instruction`（格式说明）
- 处理方式：`delete`（删除说明文字，保留间距承载）
- 字段绑定：无
- 结构绑定：无
- 中文判断：这些段落是垂直间距说明，例如“小二号字空两行”“五号字空一行”“小四号字空一行”等。可见说明文字需要删除，但它们指定的空行和字号间距必须作为版式节奏保留下来，用来维持标题、摘要、英文摘要、正文、参考文献、致谢和附录之间的学校格式。
- 中文原因：说明文字和它描述的空行使用同一段落承载，所以应当清空文字而不是移除段落，这样才能保留学校要求的空白间距。

### 3. `jd-003`：中文论文题目

- 覆盖 blocks：`u-paper-body:block-0003`
- 语义分类：`fill_slot`（字段槽）
- 处理方式：`convert_to_field_slot`（转为字段槽）
- 字段绑定：`thesis.title.zh`
- 结构绑定：无
- 中文判断：`毕业论文（设计）中文题目（小二黑体，加粗，居中）` 是中文论文题目的填写位置。可见文字是占位说明，不是固定学校文本，因此该段落转为中文题目字段槽，括号里的格式说明删除并迁移为样式。
- 中文原因：Registry 中 `thesis.title.zh` 与该位置的语义、内容类型和语言一致。

### 4. `jd-004`：作者中文姓名

- 覆盖 blocks：`u-paper-body:block-0004`
- 语义分类：`fill_slot`（字段槽）
- 处理方式：`convert_to_field_slot`
- 字段绑定：`author.name.zh`
- 结构绑定：无
- 中文判断：`学□□生：×××（或×□×）` 中，`学生` 是学校固定标签，中间的全角空格样式要保留；只有 `×××` 是作者姓名填写值。
- 中文原因：Registry 中 `author.name.zh` 表示作者中文姓名，与这个签名位置匹配；标签本身不是字段。

### 5. `jd-005`：导师中文姓名

- 覆盖 blocks：`u-paper-body:block-0005`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`advisor.name.zh`
- 结构绑定：无
- 中文判断：`指导老师：×××` 中，`指导老师` 是固定标签，`×××` 是导师姓名填写值。
- 中文原因：Registry 中 `advisor.name.zh` 匹配导师中文姓名。Registry 明确提醒不要自动加入职称；该位置也只出现姓名，因此不创建 `advisor.title` 字段槽。

### 6. `jd-006`：中文院系 / 学院

- 覆盖 blocks：`u-paper-body:block-0006`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`author.department`
- 结构绑定：无
- 中文判断：`(湖南农业大学××××学院，长沙 410128)` 是作者院系行。`湖南农业大学`、`长沙 410128` 和括号是固定学校内容；只有 `××××学院` 中的院系部分是可填写内容。
- 中文原因：Registry 中 `author.department` 匹配院系空位；学校名、城市和邮编是固定机构内容，不绑定字段。

### 7. `jd-007`：中文摘要

- 覆盖 blocks：`u-paper-body:block-0008`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`abstract.zh`
- 结构绑定：无
- 中文判断：`□□摘□要：……` 是中文摘要区：`摘要` 是固定标签，`……` 是摘要正文占位。
- 中文原因：Registry 中 `abstract.zh` 是中文摘要正文，匹配该位置；标签不绑定字段。

### 8. `jd-008`：中文关键词

- 覆盖 blocks：`u-paper-body:block-0009`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`keywords.zh`
- 结构绑定：无
- 中文判断：`□□关键词：×××；×××；×××；×××` 是中文关键词区：`关键词：` 是固定标签，后面的示例关键词整体作为一个关键词字段槽。
- 中文原因：Registry 中 `keywords.zh` 匹配；其归一化规则也说明标签不属于字段值。

### 9. `jd-009`：英文论文题目

- 覆盖 blocks：`u-paper-body:block-0011`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`thesis.title.en`
- 结构绑定：无
- 中文判断：`Title of Graduation Paper` 是英文论文题目的填写位置；可见英文不是固定学校文本，而是英文题目占位。
- 中文原因：Registry 中 `thesis.title.en` 匹配该位置和语言。

### 10. `jd-010`：作者英文姓名

- 覆盖 blocks：`u-paper-body:block-0012`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`author.name.en`
- 结构绑定：无
- 中文判断：`Student:×××` 中，`Student:` 是固定英文标签，`×××` 是作者英文姓名占位。
- 中文原因：Registry 中 `author.name.en` 匹配英文摘要页上的作者英文姓名；标签固定保留。

### 11. `jd-011`：导师英文姓名

- 覆盖 blocks：`u-paper-body:block-0013`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`advisor.name.en`
- 结构绑定：无
- 中文判断：`Tutor:××××` 中，`Tutor:` 是固定英文标签，`××××` 是导师英文姓名占位。
- 中文原因：Registry 中 `advisor.name.en` 匹配该位置的导师英文姓名责任。

### 12. `jd-012`：英文院系 / 学院

- 覆盖 blocks：`u-paper-body:block-0014`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`author.department.en`
- 结构绑定：无
- 中文判断：`(College of×××××××, Hunan Agricultural University, Changsha 410128, China)` 是英文单位行。`College of`、学校名、城市、邮编、国家和括号是固定内容；只有学院英文名空位可填写。
- 中文原因：Registry 中 `author.department.en` 匹配英文学院空位。

### 13. `jd-013`：英文摘要

- 覆盖 blocks：`u-paper-body:block-0016`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`abstract.en`
- 结构绑定：无
- 中文判断：`Abstract:……` 是英文摘要区：`Abstract` 是固定标签，`……` 是英文摘要正文占位。
- 中文原因：Registry 中 `abstract.en` 匹配英文摘要正文；标签不绑定字段。

### 14. `jd-014`：英文关键词

- 覆盖 blocks：`u-paper-body:block-0017`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`keywords.en`
- 结构绑定：无
- 中文判断：`Key words: ×××；×××；×××；×××` 是英文关键词区：`Key words:` 是固定标签，示例关键词整体绑定成英文关键词字段槽。
- 中文原因：Registry 中 `keywords.en` 匹配；其归一化规则说明标签不属于字段值。

### 15. `jd-015`：学科分支选择提示

- 覆盖 blocks：`u-paper-body:block-0019`、`u-paper-body:block-0029`
- 语义分类：`conditional_content`（条件分支提示）
- 处理方式：`delete`（删除可见提示，迁移条件语义）
- 字段绑定：无
- 结构绑定：无
- 中文判断：`（以下农理工科类用）` 和 `（以下文法经管类用）` 是学科分支选择说明。可见说明文字删除，但它们表达的条件要迁移到两个 `body.chapters` 分支上。
- 中文原因：这两段是判断两套编号体系属于“条件替代分支”而不是连续正文的唯一学校证据，所以条件语义不能丢。

### 16. `jd-016`：农理工科正文结构（primary）

- 覆盖 blocks：`u-paper-body:block-0020`、`0021`、`0022`、`0023`、`0024`、`0025`、`0027`、`0028`
- 语义分类：`body_representative`（正文代表结构）
- 处理方式：`transfer_style_to_slot`（迁移样式到正文结构槽）
- 字段绑定：无普通字段槽
- 结构绑定：`structure_ref=body.chapters`
- 分支：`variant_id=body.chapters.agriculture_science_engineering`，`variant_role=primary`
- 中文判断：这些 blocks 是农理工科正文结构样板，成为清洁模板中的可复用正文接口。十进制编号表达层级：`1 前言`、`2 ××××`、`5 结论` 是章标题；`2.1` 是下一级标题；`2.1.1` 是再下一级标题；`□□` 缩进段落，包括含 `[1]` 引用的段落，都是普通正文段落。样例文字不作为学生内容保留，只迁移其结构和样式能力。
- 中文原因：这些成员来自同一个连续的学校正文样板，并按真实文档顺序排列；每个标题层级和正文段落都有学校原始样式载体。
- 执行效果：清洁模板暴露一个可填写的正文结构，包含三级标题和正文段落载体；样例中的编号 `1/2/5` 只说明可重复结构，不代表必须生成这些固定章节。
- 成员绑定：
  - `block-0020` -> `body.heading.outline1`
  - `block-0021` -> `body.paragraph`
  - `block-0022` -> `body.heading.outline1`
  - `block-0023` -> `body.heading.outline2`
  - `block-0024` -> `body.heading.outline3`
  - `block-0025` -> `body.paragraph`
  - `block-0027` -> `body.heading.outline1`
  - `block-0028` -> `body.paragraph`

### 17. `jd-017`：文法经管类正文结构（alternate）

- 覆盖 blocks：`u-paper-body:block-0030`、`0031`、`0032`、`0033`、`0034`、`0035`、`0038`、`0039`
- 语义分类：`body_representative`
- 处理方式：`delete`（样例块从清洁模板删除，但作为 alternate 结构记录保留）
- 字段绑定：无普通字段槽
- 结构绑定：`structure_ref=body.chapters`
- 分支：`variant_id=body.chapters.humanities_law_economics_management`，`variant_role=alternate`
- 中文判断：这些 blocks 是文法经管类正文结构样板，采用另一套编号系统：`一、`、`二、`、`五、结束语` 是章标题；`（一）` 是下一级；`1、` 是再下一级；`□□` 缩进段落，包括导入段、含 `[1]` 引用段和结尾段，都是普通正文段落。它被记录为 alternate 分支，但样例块从清洁模板中删除，避免最终模板出现两套相互竞争的正文填写接口。
- 中文原因：这套层级确实是学校语义，必须作为分支记录；但如果保留它的样例段落，会让学生误以为需要填写两套正文结构。
- 成员绑定：
  - `block-0030` -> `body.paragraph`
  - `block-0031` -> `body.heading.outline1`
  - `block-0032` -> `body.heading.outline1`
  - `block-0033` -> `body.heading.outline2`
  - `block-0034` -> `body.heading.outline3`
  - `block-0035` -> `body.paragraph`
  - `block-0038` -> `body.heading.outline1`
  - `block-0039` -> `body.paragraph`

### 18. `jd-018`：正文样例中的省略号续写标记

- 覆盖 blocks：`u-paper-body:block-0026`、`0036`、`0037`
- 语义分类：`author_instruction`（作者说明 / 重复提示）
- 处理方式：`delete`
- 字段绑定：无
- 结构绑定：无
- 中文判断：这些单独的 `……` 是正文样例里的续写标记，表示还有更多章节。它们不是正文结构成员，也不是内容载体，因此删除，并且不放进 `jd-016` 或 `jd-017` 的正文结构成员里。
- 中文原因：如果把省略号当结构成员，会把无意义 block 绑定到 Registry 字段，并破坏正文成员与 reading block 的一一对应。

### 19. `jd-019`：参考文献标题

- 覆盖 blocks：`u-paper-body:block-0041`
- 语义分类：`fixed_content`（固定内容）
- 处理方式：`keep`
- 字段绑定：无
- 结构绑定：无
- 中文判断：`参考文献` 是学校要求的参考文献章节标题。标题文字固定保留；括号里的格式说明删除并迁移为样式。
- 中文原因：这是学校固定章节名，不随学生内容变化，不是填写位置。

### 20. `jd-020`：参考文献条目

- 覆盖 blocks：`u-paper-body:block-0042`
- 语义分类：`example_value`（样例值）
- 处理方式：`convert_to_field_slot`
- 字段绑定：`references.entries`
- 结构绑定：无
- 中文判断：`[1] 作者.论文题名[J].期刊名，出版年，卷（期）：页码A-B.` 是参考文献条目的填写位置，同时展示学校引用格式。它转为参考文献条目字段槽，引用格式作为填写阶段的格式义务保留。
- 中文原因：Registry 中 `references.entries` 是多值 rich text 字段，准确匹配参考文献条目责任；不能用 `body.paragraph`，因为 `body.*` 只属于正文代表结构。

### 21. `jd-021`：参考文献续写标记

- 覆盖 blocks：`u-paper-body:block-0043`
- 语义分类：`author_instruction`
- 处理方式：`delete`
- 字段绑定：无
- 结构绑定：无
- 中文判断：参考文献下方的 `……` 表示还有更多编号参考文献，属于重复提示，删除。
- 中文原因：它只是说明上一条参考文献条目可以重复，不承担独立的参考文献语义。

### 22. `jd-022`：致谢标题

- 覆盖 blocks：`u-paper-body:block-0045`
- 语义分类：`fixed_content`
- 处理方式：`keep`
- 字段绑定：无
- 结构绑定：无
- 中文判断：`致□□谢` 是学校要求的致谢章节标题。标题文字和中间全角间距保留；括号里的格式说明删除并迁移为样式。
- 中文原因：这是固定学校章节标题，不随学生内容变化。注意它是居中标题，不能和 `参考文献`、`附录` 的标题样式混同。

### 23. `jd-023`：致谢正文

- 覆盖 blocks：`u-paper-body:block-0046`
- 语义分类：`example_value`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`acknowledgement.body`
- 结构绑定：无
- 中文判断：`本论文是在×××老师的悉心指导和热情关怀下完成的……` 是致谢样例句，也是致谢正文的填写位置。它转为致谢字段槽；样例文字不作为固定学校文本保留，因为里面含有导师姓名占位。
- 中文原因：Registry 中 `acknowledgement.body` 匹配致谢正文；不能用 `body.paragraph`，因为 `body.*` 只用于正文代表结构。

### 24. `jd-024`：附录标题

- 覆盖 blocks：`u-paper-body:block-0048`
- 语义分类：`fixed_content`
- 处理方式：`keep`
- 字段绑定：无
- 结构绑定：无
- 中文判断：`附录` 是学校要求的附录章节标题。标题文字固定保留；括号里的格式说明删除并迁移为样式。
- 中文原因：这是固定学校章节名，不随学生内容变化。

### 25. `jd-025`：附录枚举样例

- 覆盖 blocks：`u-paper-body:block-0049`、`u-paper-body:block-0050`
- 语义分类：`example_value`
- 处理方式：`delete`
- 字段绑定：无
- 结构绑定：无
- 中文判断：`附录1……` 和 `附录2……` 是附录枚举样例，说明论文可以有多个附录。它们和后面真正的附录布局承担同一责任，所以删除，而不是再物化出额外的附录接口。
- 中文原因：该模板一贯用枚举样例表示重复结构，例如章节 `1/2/5`、参考文献 `[1] + ……`、附录 `附录1/附录2 + ……`。模板和要求里没有说需要单独的附录索引列表；如果保留这两组，会重复物化同一个附录责任。

### 26. `jd-026`：附录续写标记

- 覆盖 blocks：`u-paper-body:block-0051`
- 语义分类：`author_instruction`
- 处理方式：`delete`
- 字段绑定：无
- 结构绑定：无
- 中文判断：附录枚举后的 `……` 表示还有更多附录，属于续写/重复提示，删除。
- 中文原因：它只表达重复，不承担独立附录责任。

### 27. `jd-027`：附录标题字段

- 覆盖 blocks：`u-paper-body:block-0052`
- 语义分类：`fill_slot`
- 处理方式：`convert_to_field_slot`
- 字段绑定：`appendix.title`
- 结构绑定：无
- 中文判断：`附录1（另起一页，小四号黑体）` 是真正的单个附录标题填写位置，同时说明附录需要另起一页。它转为附录标题字段槽，`另起一页` 的规则迁移为版式义务。
- 中文原因：Registry 中 `appendix.title` 是文本 leaf field，匹配附录页或附录章节标题；真正的可填写接口应放在这里，而不是前面被删除的枚举样例上。

### 28. `jd-028`：附录正文区域 / 样式载体

- 覆盖 blocks：`u-paper-body:block-0053`
- 语义分类：`layout_carrier`（版式 / 样式载体）
- 处理方式：`keep`
- 字段绑定：无
- 结构绑定：无
- 中文判断：这是根据物化质量门反馈修正后的判断。`……（附录内容的字体字号参照正文的格式要求）` 不是普通单值填写位置。它在学校语义上是附录正文区域：一个开放的 section-level 区域，可能包含多个段落、表格、图片或代码，且唯一明确学校规则是字体字号参照正文格式。因此它保留为 `appendix.title` 下方的附录内容版式 / 样式载体，不转成文本字段槽，也不绑定普通 Registry slot。
- 中文原因：学校语义没有变化，错误的是原先的绑定意图。Registry 中附录字段只有 `appendix.title` 和 `appendix.body`；其中 `appendix.body` 是 section container，不是可填写 leaf field，也没有 appendix paragraph leaf field。规则禁止用 `body.paragraph` 代替附录内容，所以拒绝近似字段绑定，改成非普通字段槽判断。这里没有缺学校证据，因此不返回 `needs_input`。

## 按类型汇总

字段槽：

- `thesis.title.zh`
- `author.name.zh`
- `advisor.name.zh`
- `author.department`
- `abstract.zh`
- `keywords.zh`
- `thesis.title.en`
- `author.name.en`
- `advisor.name.en`
- `author.department.en`
- `abstract.en`
- `keywords.en`
- `references.entries`
- `acknowledgement.body`
- `appendix.title`

正文结构：

- `body.chapters.agriculture_science_engineering`：primary，保留为实际正文结构接口。
- `body.chapters.humanities_law_economics_management`：alternate，记录为替代结构，样例块从最终模板删除。

固定保留：

- `参考文献`
- `致□□谢`
- `附录`

删除 / 清理：

- 全局格式说明文字。
- 垂直间距说明文字。
- 学科分支说明文字。
- 正文、参考文献、附录中的 `……` 续写标记。
- 附录枚举样例 `附录1……`、`附录2……`。

特殊处理：

- `jd-028` 附录正文区域保留为空的版式 / 样式载体，不绑定 `body.paragraph`，也不绑定 `appendix.body` 普通字段槽。
