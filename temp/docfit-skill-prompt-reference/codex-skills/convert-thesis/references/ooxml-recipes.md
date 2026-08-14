# OOXML 手术配方

在需要前置页嫁接、跨文档复制、分节、页码、目录字段、制表位、三线表或跨 run 替换时阅读本文件。只做与当前 `requirements.md` 对应的操作。

## 1. 不变量

- 把学生原稿和学校库视为只读输入，只写新的工作副本。
- 修改前记录输入 SHA-256；每次较大操作后重新运行 `dump_docx.py`。
- 文本样式调整只改 `w:pPr`、`w:rPr`、样式定义或编号引用，不改 `w:t`。
- 跨文档复制带 `r:id` 的节点时，必须同步复制关系、目标 part 和内容类型；只复制 XML 节点会产生“能打开但图片/页眉丢失”的损坏文件。
- 不接受/拒绝修订，不删除批注，不清理未知 OOXML 节点。
- 不用整段 `paragraph.text = ...` 或整文档搜索替换处理格式；这会重建 runs，破坏域、超链接、批注锚点和修订。

## 2. 前置页嫁接

优先以学生原稿的副本作为最终文档基础，在其正文开始前插入已验收 `prefill_template.docx` 的前置节。原因是学生正文中的图片、批注、修订、编号和自定义 XML 关系更难完整迁移。

跨包复制前建立四张映射：

1. `styles.xml`：按 `styleId` 合并；同 ID 不同定义时为学校样式分配新 ID，并重写复制节点的 `w:pStyle`/`w:rStyle`。
2. `numbering.xml`：复制依赖的 `w:abstractNum` 与 `w:num`，分配不冲突的新 ID，并重写 `w:numId`。
3. 主文档关系：为图片、超链接、页眉、页脚、脚注等分配新 `rId`，复制目标 part，并重写所有相关属性。
4. 内容类型：向 `[Content_Types].xml` 补充新 part 的 Override/Default。

前置节最后必须有独立 `w:sectPr`；正文首节按学校要求设置：

- 断开不应继承的页眉/页脚关系；
- 设置正文页码格式和起始值；
- 保留学生正文的纸张方向切换、横向表格节和后续分节；
- 不把模板末尾的最终 `body/sectPr` 原样塞到正文中间。

若当前环境已有经过验证的文档组合库，可用它完成关系和 part 迁移；仍必须用 `dump_docx.py` 对比合并前后关系、节、媒体、SDT、批注和修订数量。

## 3. 跨 run 填充 `{{slot}}`

占位符可能被 Word 拆到多个 `w:t`。替换步骤：

1. 在一个段落或表格单元格内按顺序拼接所有可见 `w:t`，建立字符偏移到原节点的映射。
2. 在拼接文本中精确寻找 `{{slot_id}}`，要求命中一次。
3. 将值写入命中范围的第一个 `w:t`，保留该 run 的 `w:rPr`；清空命中范围其余 `w:t`，不要删除周围 run。
4. 值含换行时按模板约定创建 `w:br` 或新段落，不把换行符直接塞进单个 `w:t`。
5. 记录槽位 ID、写入值、学生来源段落/表格坐标和是否人工确认到 `slot_fill_report.md`。

填充值前后都运行 `check_placeholders.py`。禁止用模糊关键词替换槽位。

## 4. PAGE、TOC 与 PAGEREF 域

复杂域结构通常是：

```text
w:fldChar type=begin
w:instrText
w:fldChar type=separate
显示结果 runs
w:fldChar type=end
```

规则：

- 不删除 begin/separate/end 中任何一个节点。
- 修改域指令时保留 `xml:space="preserve"`。
- `PAGE` 用于页脚当前页；`PAGEREF bookmark` 用于锚点页；`TOC` 用于自动目录。
- 设置 `w:updateFields w:val="true"` 只能请求 Word 更新，不能证明 Word 已更新。
- LibreOffice 与 Microsoft Word 的域更新/分页可能不同。最终验收以 Word 更新后的文件和逐页渲染抽查共同决定。
- 手工目录才使用 `measure_pages.py --output-docx`；检测到字段管理目录时让脚本返回 `UNKNOWN`，不要把字段结果当普通数字 run 改写。

## 5. 分节与页码

- 页面属性属于 `w:sectPr`，不是普通段落样式。
- 中间节的 `w:sectPr` 位于上一节最后段落的 `w:pPr`；全文件最后一节位于 `w:body` 末尾。
- 新建节后检查 `headerReference`、`footerReference`、`titlePg`、`pgNumType`、`pgSz`、`pgMar` 和节类型。
- 正文从 1 开始时在正文首节使用 `w:pgNumType w:start="1"`；前置罗马页码和正文阿拉伯页码必须处于不同节。
- 取消“链接到前一节”意味着为本节建立独立关系，不能只改可见页脚文字。

## 6. 制表位

目录点引导线、参考文献编号后空位等应使用 `w:tabs/w:tab`，不要用重复空格或点号模拟。

- `w:pos` 使用 twips。
- `w:val="right"` + `w:leader="dot"` 适合右对齐目录页码。
- 写入制表符使用 `w:tab`，不是文字 `\t`。
- 修改后逐页渲染，检查长标题换行时页码仍靠右且不掉到下一行。

## 7. 三线表

- 保留表格、合并单元格、单元格内容和批注，只改边框属性。
- 在 `w:tblBorders` 设置上、下边框和表头下边框；清除不允许的内部竖线。
- 若表头跨多行，表头下边框应加在最后一行表头的 `w:tr`/单元格边框，而不是猜第一行。
- 不用删除空行或合并单元格解决分页；优先调列宽、字号、段前后和 `cantSplit`。

## 8. 完成一次手术后的最低检查

1. DOCX 仍是合法 ZIP，含 `[Content_Types].xml` 和 `word/document.xml`。
2. `dump_docx.py` 可完整运行。
3. 源媒体/嵌入对象哈希、批注内容和修订计数未减少。
4. `check_content.py` 没有 FAIL/UNKNOWN。
5. LibreOffice 能转 PDF；逐页 PNG 没有空白页、重复目录、错节、丢图或页眉串节。
