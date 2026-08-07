# 逐对象判断补充

## 先判断对象责任

对当前对象依次问：

1. 它是否承载学校身份、制度文本、固定标签或版式结构？是则保留。
2. 它是否是学生每篇论文都会变化的值？是则考虑物化为槽。
3. 它是否只是告诉学生“怎么写”、展示一段成品或展示格式效果？是则清理。
4. 删除它是否会让相邻标题、表格、节、页眉页脚或目录机制失去依托？会则缩小目标或改为清空。

## 常见槽位映射信号

| 模板标签/位置 | 常见字段方向 |
|---|---|
| 题目、论文题目 | `thesis.title.zh` / `thesis.title.en` |
| 姓名、作者 | `author.name.zh` / `author.name.en` |
| 学号 | `author.student_id` |
| 学院、院系 | `author.department` |
| 专业 | `author.major` |
| 指导教师、导师 | `advisor.name.zh` / `advisor.name.en` |
| 职称 | `advisor.title` |
| 日期、年月日 | `submission.date` |
| 中文/英文摘要正文 | `abstract.zh` / `abstract.en` |
| 中文/英文关键词 | `keywords.zh` / `keywords.en` |
| 正文承载区 | `body.chapters` 或更具体的正文结构字段 |
| 参考文献承载区 | `references.entries` |
| 附录名称、附录标题 | `appendix.title` |
| 附录正文、附录内容 | `appendix.body` |
| 相关学术成果目录正文 | `achievements.entries` |
| 致谢正文 | `acknowledgement.body` |

表格只是常见线索，不是强制映射。当前对象、相邻标签、语言和学校结构优先。

## 示例与固定标题的区别

“摘 要”“Abstract”“参考文献”“致谢”通常是结构标题，应保留；标题下面的一整段完整内容若在
多处展示字号、行距、引文或关键词格式，通常是示例，应删除并在需要的位置留下填写槽/承载区。
目录域本身应保留。目录中的点引导线、章节文本和页码是域的可见缓存；它们显示 `XXX`、`XX`、
示例章名或“此项非必需项”时，应批量清空缓存结果段落中的可见文字，但保留域代码、域边界和目录段落样式。
