# 转换前必读的坑清单

动手修改任何学生文档前通读本文件。每条均是跨学校的防错规则，不包含具体学校格式。

## 内容与结构

- **可见文字相同不等于内容完整。** 图片、嵌入对象、公式、脚注、批注和修订都可能在纯文本比对中消失。必须同时看 `check_content.py` 的资产、结构和审阅信息检查。[来源: DocFit V3 `format-conversion-predevelopment-alignment.md`]
- **python-docx 的顶层段落列表不是完整文档。** SDT、文本框、批注、修订和部分字段可能不在其普通 API 视图中。先用 `dump_docx.py` 扫 OOXML。[事故: 双目录；来源: DocFit V3 `template_gap/inspector.py`]
- **段落拆分/合并会制造段落 diff。** 以去空白字符流是否逐字同序作为文本硬裁判，同时保留段落 diff 给人检查结构；不要只看其中一个。[来源: DocFit 双 Skill 设计稿]
- **未知可见对象必须暴露。** 无法确认去向的对象写入 `run_log.md` 并停止相关修改；不要因为脚本不认识就把它当空内容。[来源: DocFit V3 unsupported-visible-object 门禁]
- **批注和修订是用户沟通记录。** 不得接受/拒绝修订、删除批注、清理“看起来多余”的 comments/customXml part。[来源: DocFit 双 Skill 设计稿]

## 跨文档复制

- **只复制 document.xml 节点会丢关系。** 图片、超链接、页眉页脚、脚注和外部对象都依赖 `.rels` 与目标 part；每个 `r:id` 必须重映射。[来源: DocFit V3 OOXML package 模型]
- **样式 ID 同名不一定同义。** 两个 DOCX 的 `Heading1` 或自定义 styleId 可能定义不同；合并前对定义做哈希或重命名。[来源: DocFit V3 source-tree/style facts]
- **编号是两级引用。** `w:numId` 指向 `w:num`，再指向 `w:abstractNum`；漏任一层会导致标题编号或列表错乱。[来源: DocFit V3 numbering facts]
- **节属性挂在上一节末尾。** 把模板 `sectPr` 放错位置会制造空白页、页码重置或页眉串节。[来源: OOXML 规范；DocFit V3 section facts]

## 替换与格式

- **整段赋值会毁掉 run 级结构。** 它可能删除域、超链接、批注锚点和修订边界。格式调整只改属性；槽位替换按跨 run 偏移映射做。[来源: DocFit V3 逐 run 事实与 Word 手术经验]
- **不要用删学生内容解决分页。** 表格/图片冲突时先调版式；仍无法满足时标记人工处理，内容完整性优先。[来源: DocFit 双 Skill 设计稿]
- **颜色可能来自修订显示。** 看到彩色文字先查修订节点，不要把审阅颜色误判成字体颜色并覆盖。[来源: DocFit 双 Skill 设计稿]
- **空格不是版式工具。** 目录点线、编号后间隔和对齐用制表位/缩进；重复空格在不同渲染器下会漂移。[来源: 湖南农业模板审查与 OOXML 制表位规则]

## 目录与分页

- **目录可能同时存在字段、结果和 SDT 示例。** 只看可见段落容易保留两份目录或把示例当正文；先检查字段和 SDT。[事故: 双目录]
- **内容定稿前不要测页码。** 任何字体、行距、图表尺寸或分节变化都可能让目录失效。[来源: DocFit 双 Skill 设计稿]
- **LibreOffice 页码不是 Word 页码的数学证明。** 它适合自动测算和回归；交付前仍要在 Microsoft Word 更新字段并抽查。[来源: DocFit V3 LibreOffice 渲染链]
- **字段结果不是普通数字。** 目录由 TOC/PAGEREF 管理时更新字段，不要手工改显示 run 后声称完成。[来源: OOXML 域结构]

## 裁判与报告

- **“文件生成成功”不是质量通过。** 有 `final.docx`、PDF 或 PASS 字样都不能替代内容、占位符、分页和逐页检查。[来源: DocFit V3 AGENTS.md]
- **自动边界不确定必须是 UNKNOWN。** 找不到正文首标题或参考文献边界时，提供显式正则再跑；不要扩大到全文件后给假绿。[来源: DocFit V3 三态门禁]
- **检查输出不得解释性弱化。** FAIL/UNKNOWN 原样进入总报告；是否接受例外由人决定。[来源: DocFit 双 Skill 设计稿]
- **学校差异只能来自 accepted 库。** 不在脚本或 skill 内增加学校名分支；新增/变更要求必须新建并验收库版本。[来源: DocFit 双 Skill 总体架构]
