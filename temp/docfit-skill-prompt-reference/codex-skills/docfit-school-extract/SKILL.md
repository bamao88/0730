---
name: docfit-school-extract
description: 将用户提供的学校论文模板、旧版 Word 文件、PDF、要求文档和论文样例转换为经验证的 Docfit 学校包。适用于接入或更新学校目录，以及将字体、页边距、标题、题注、参考文献、前置部分和正文后逻辑页面提取到 school.yaml、带顶层 checks 的 requirements.yaml、style_mapping.yaml、封面片段、参考固件或可供 template-manifest 使用的证据中。
---

# Docfit 学校要求提取

## 核心规则

不要假装这是一键式自动提取。凡是程序能够生成证据的地方，都应使用程序；对于需要人工推理的部分，则应基于明确证据作出显式判断。

每条最终学校规则都应回答：

- 哪个来源提出了这条规则？
- 它是由程序提取、在来源中明确写明，还是通过推断得出？
- 还存在哪些冲突或不确定性？
- 验证如何证明该学校包可用？

当提取的规则不止少数几条，或不同来源之间存在分歧时，请使用 `references/evidence-template.md`。

## 工作流

### 0. 选择模式

对于新学校，运行下面完整的提取工作流。

对于已有的学校包，先执行审计/更新流程：将 `school.yaml`、`requirements.yaml`（包括顶层 `checks:`）、`style_mapping.yaml`、`README.md`、`reference.docx` 和 `fixtures/` 与已提交的上游来源进行比较。不要仅仅因为脚本能够生成受版本控制的黄金固件或二进制资产就刷新它们；只有在发现规则/来源不匹配，或用户明确要求更新固件时，才进行刷新。

### 1. 盘点来源

列出用户提供的所有文件，并将每个文件归入以下类别之一：

- 官方 Word 模板
- 旧版 `.doc` 模板
- PDF/规范文本
- 要求/说明文档
- 已通过验收的论文样例
- 学校固定表单包

将原始文件保存在 `schools/<school-id>/upstream/` 下，通常放在 `upstream/word/` 中。如果必须检查旧版 `.doc`，请使用 LibreOffice 转换它，并同时保留原文件和转换后的文件：

```bash
soffice --headless --convert-to docx --outdir /tmp/docfit-school schools/<school-id>/upstream/word/source.doc
```

如果来源中可见的学校名称与目录 slug 冲突，应在学校 README 和最终回复中清楚标明。除非用户已经要求重命名，否则在重命名受版本控制的学校 ID 之前先征求确认。

如果官方规范未纳入版本控制，应在 README 和证据台账中链接学校页面或附件的确切地址。第三方模板、已通过验收的论文或社区 LaTeX/Word 项目必须标记为视觉/参考证据，不能作为规范性来源，除非学校本身将其作为官方材料发布。

### 2. 提取程序化证据

推理之前优先使用确定性工具：

```bash
file <source>
uv run docfit features extract <source.docx>
uv run python - <<'PY'
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

path = Path("SOURCE.docx")
doc = Document(path)
print("paragraphs", len(doc.paragraphs), "tables", len(doc.tables), "sections", len(doc.sections))
for i, section in enumerate(doc.sections):
    print("section", i, section.top_margin.mm, section.bottom_margin.mm, section.left_margin.mm, section.right_margin.mm)
for i, paragraph in enumerate(doc.paragraphs):
    text = paragraph.text.strip()
    if text:
        print(f"{i:03d}", paragraph.style.style_id, paragraph.style.name, text[:160])
for style in doc.styles:
    if style.type.name != "PARAGRAPH":
        continue
    if style.name in {"Normal", "Heading 1", "Heading 2", "Heading 3", "Caption"} or not style.builtin:
        rpr = style._element.rPr
        ppr = style._element.pPr
        size = None
        fonts = None
        spacing = None
        if rpr is not None:
            sz = rpr.find(qn("w:sz"))
            if sz is not None:
                size = int(sz.get(qn("w:val"))) / 2
            rf = rpr.find(qn("w:rFonts"))
            if rf is not None:
                fonts = {k: rf.get(qn("w:" + k)) for k in ["ascii", "hAnsi", "eastAsia", "cs"]}
        if ppr is not None:
            sp = ppr.find(qn("w:spacing"))
            if sp is not None:
                spacing = {k: sp.get(qn("w:" + k)) for k in ["before", "after", "line", "lineRule"]}
        print(style.style_id, repr(style.name), "size", size, "fonts", fonts, "spacing", spacing)
PY
```

当 `python-docx` 隐藏细节时，直接检查 OOXML：

```bash
unzip -p <source.docx> word/styles.xml | rg "styleId|rFonts|spacing|outlineLvl|jc"
unzip -p <source.docx> word/document.xml | rg "pgMar|pgSz|tbl|sdt|bookmark"
```

不要将 `uv run docfit features extract` 或 `word/styles.xml` 视为最终的样式权威。特征提取和原始样式定义只是证据，而官方模板经常包含可见示例，其中的段落或文本运行直接格式会有意覆盖命名样式。对于可见示例，应按 `docDefaults` → 基于样式的继承链 → 样式 `pPr/rPr` → 段落 `pPr/rPr` → 文本运行 `rPr` 的顺序计算有效格式；然后记录原始样式与可见结果之间的任何冲突。目录域结果段落、超链接和生成的示例尤其需要这样处理：检查 `word/document.xml` 中实际的结果段落/文本运行，而不能只检查 `toc 1`/`toc 2` 样式定义。

当可选文件可能存在也可能不存在时，应使用 `find`、数组或 shell 的 `nullglob`/存在性检查，而不要直接使用未受保护的 glob。glob 匹配失败不应导致提取中止，也不应让某类来源被静默跳过。

### 3. 有意识地解决冲突

最终取值按以下优先级确定：

1. 学校规范中可见的规范性文本。
2. 官方模板中可见的说明文本。
3. 官方模板中有效的可见示例，包括段落/文本运行直接格式和继承的样式值。
4. 官方模板中的原始 OOXML 样式和节属性。
5. 已通过验收的论文样例。
6. 保守的论文格式启发式规则。

记录所有冲突。例如：如果转换后的 OOXML 显示上边距为 `20mm`，但可见文本写的是 `2.54cm`，则采用 `25.4mm`，并注明原因。
当原始样式与有效的可见示例不一致时，不要静默选择样式定义。增加一条冲突记录，解释最终取值来自哪一层，以及渲染器/测试固件是否必须编码直接覆盖。

### 4. 推断实际的论文契约

至少推断并记录以下方面：

- 页面：纸张尺寸、页边距、装订线、页眉/页脚距离。
- 正文：中日韩文字/拉丁文字字体、字号、行距、对齐方式、首行缩进。
- 标题：H1/H2/H3 的字体、字号、间距、对齐方式、大纲级别、编号方案和所需的分隔空格。
- 摘要/关键词/目录：标题和正文样式、从可见域结果/示例获得的有效目录条目格式、目录深度，以及是否必须用 Word 目录域替换手工输入的目录行。
- 题注/表格/图形：标签文本、编号模式、重置策略、图题是否位于图下方及表题是否位于表上方，以及字体/对齐规则。
- 参考文献：标题样式、条目样式、方括号编号或句点编号、GB/T 规则证据、续行处理。
- 公式和单位：编号是否按章、是否右对齐、项/运算符是否使用正体，或是否只能手工处理。
- 前置/正文后内容：封面、声明、目录前说明、学术成果、任务书、数据集表、附录、作者简历、答辩/成绩表。让这些内容保持由学校所有，并置于通用正文规范化范围之外。

### 4a. 构建逻辑页面契约

不要让提取器仅根据学生源文档中碰巧存在的内容来决定逻辑页面。页面顺序由目标学校的官方模板和要求文档决定。

为正文前后每个类似页面的部分创建有序的逻辑页面台账。包括：

- `id`：稳定的 snake_case ID，例如 `cover`、`originality_statement`、`toc`、`academic_achievements`、`author_resume`、`dataset`、`design_task`、`proposal`、`defense_record`、`grade_form`、`appendix` 或 `acknowledgement`。
- `titles`：可见的中英文标题和别名。包括 `相关的学术成果目录`、`攻读硕士学位期间取得的学术成果`、`作者简历及攻读硕士学位期间取得的研究成果` 和 `学位论文数据集` 等长标题。
- `owner`：通常为 `target_school_template`。只有应移入目标学校所有槽位的正文内容才使用 `source_student_content`。
- `position`：封面前、目录前、目录与正文之间、参考文献后、附录后，或证据明确规定的其他顺序位置。
- `status`：`required`、`optional`、`conditional` 或 `manual_only` 之一。
- `source_policy`：内容是从学生源文档复制、根据元数据生成、作为学校表单保留，还是留待手工填写。
- `empty_policy`：学生/源文档中不存在内容时的处理方式。
- `implementation_notes`：所需模板槽位、manifest 槽位、解析器块类型、标题别名、终止标题行为和验证/审查检查。

默认的空内容策略：

- 目标学校所有的必需页面缺少内容：保留页面或表单外壳，添加醒目的“需要人工处理”占位符，并让严格/最终验证失败或报告缺失值。
- 目标学校所有的可选页面缺少内容：在草稿/审查输出中保留该逻辑页面和醒目的占位符，除非学校官方来源明确说明应省略该页面。使用类似下面的句子：`【源文档中未识别到本页内容；如学校不要求，可删除本页。】`
- 条件页面：记录条件；在条件尚不明确时采用可选页面策略。不要仅仅因为源论文省略了该页面就静默删除它。
- 只能手工处理的签字表单或行政页面：保留学校所有的表单外壳或占位符并将其标记为只能手工处理；不要将它作为正文文本进行规范化。
- 输入论文中仅属于来源学校的前置内容：转换时移除或忽略，除非它为目标页面提供元数据。此规则并不授权删除目标学校的逻辑页面。

对于模板优先的学校包，每个具有可见锚点、内容控件或书签且由目标学校所有的逻辑页面，都应在 `template_manifest.yaml` 或等效的学校专用渲染契约中表示。对于可选逻辑页面，优先使用 `placeholder_review` 等显式空内容策略。只有学校来源明确说明最终文档应省略该页面，并且 README 解释了此决定时，才使用 `remove_block`。

解析器和渲染器指导：

- 将逻辑页面标题和别名视为块起点/终止标题，而不是普通正文标题。
- 学术成果、作者简历、论文数据集、附录和致谢等正文后页面必须终止参考文献块，防止它们被参考文献块吞入。
- 声明、使用授权、摘要、目录和目录前说明等前置页面不得成为章标题。
- 如果运行时模型缺少学校所有页面所需的块类型，应在 `implementation_notes` 中记录需要新增的类型或学校专用映射；不要通过将页面映射到 `UNKNOWN` 来隐藏它而不产生审查发现。

### 4b. 构建起页布局契约

不要仅通过统计空 OOXML 段落来推断逻辑页面可见的顶部空白。自然分页、`pageBreakBefore`、显式分页符和 `nextPage` 分节边界可能让 Microsoft Word 与 LibreOffice 将同一个空段落分配到不同的可见页面。

对于每个从新页开始的逻辑单元，记录并验证：

- `boundary_mode`：文档起点、`pageBreakBefore`、显式分页符或 `nextPage` 分节。
- `boundary_owner`：拥有该边界的确切段落。一个单元必须只有一个边界所有者；禁止重复的分页符和分节符。
- `first_anchor`：第一个可见标题、表单标签或稳定的文本锚点。
- `leading_blank_paragraphs`：仅计算在规范渲染器中，边界之后可见的空段落。边界与第一个锚点之间出现未声明的块时，构建必须失败。
- `first_anchor_spacing_before`：用于替代说明衍生或其他含义不明确的空段落的显式段前间距。
- 分节页面的页边距、页码以及页眉/页脚继承关系。
- 规范渲染器中的页码和锚点偏移量（或等效截图引用），并设置较小的容差。

优先使用段落间距或分节几何属性，而不是可编辑的空段落。只有当官方可见示例要求保留前导空段落，并且规范渲染器证明它属于新页面时，才保留该段落。

用于布局 QA 的渲染器优先级：

1. 学校/用户用于最终交付 Word 文档的渲染器（通常为 Microsoft Word；如果用户明确将 WPS 视为权威，则使用 WPS）。
2. 来自该渲染器的官方 PDF 或截图证据。
3. 用于广泛扫描整个文档的 LibreOffice。
4. 作为结构证据而非可见布局权威的原始 OOXML。

当 Word 与 LibreOffice 的结果不一致时，不要对坐标取平均值，也不要因为其中一个渲染器通过就将构建标记为已验收。记录冲突，并以规范渲染器的结果为准。只有在规范渲染器中审查完每个逻辑页面的起始位置后，才能验收最终模板。

本台账应涵盖的跨学校示例：

- 南京农业大学本科模板可能包含 `相关的学术成果目录（此项非必需项）`；该页面为可选、由目标学校所有，缺失时应成为审查占位页面。
- 北京交通大学研究生模板包含附录、作者简历/研究成果和学位论文数据集等正文后部分。
- 湖南农业大学学校包可能包含任务书、开题报告、答辩记录和成绩表页面，这些是学校所有的行政表单。
- 在多所学校中，通用的 `致谢` 和 `附录` 都是可选页面，但“可选”并不自动意味着“在草稿转换期间删除”。

常用的中文字号换算：

| 名称 | pt |
| --- | ---: |
| 一号 | 26 |
| 小二 | 18 |
| 二号 | 22 |
| 三号 | 16 |
| 小三 | 15 |
| 四号 | 14 |
| 小四 | 12 |
| 五号 | 10.5 |
| 小五 | 9 |

将中文格式文档中的 `□` 视为显式空格标记，通常表示一个汉字宽度或两个 ASCII 空格。当它影响标题/题注/参考文献解析时，将其保留为一项要求。

### 5. 生成 Docfit 资产

创建或更新：

- `schools/<school-id>/school.yaml`
- `style_mapping.yaml`
- 带顶层 `checks:` 的 `requirements.yaml`
- `cover_fragment.xml`；如果封面/前置内容由模板所有，则设置 `cover.inject: false`
- `README.md`
- `upstream/` 来源追踪资产
- `reference.docx`
- `fixtures/reference.docx`
- `fixtures/features.json`

对于浅层学校包，根据 `school.yaml` 生成参考资产：

```bash
uv run python scripts/gen_school_reference.py <school-id>
uv run python scripts/build_golden.py <school-id>
```

对于深层的模板优先学校包，优先使用包含内容控件或书签槽位的学校自有 `template.docx`，并配合 `template_manifest.yaml`。文本锚点仅作为现有模板的迁移过渡方案。

模板优先学校包可以将 `template.docx` 和 `template_manifest.yaml` 保留在学校根目录，同时仍生成用于验证的样式 `reference.docx` 和 `fixtures/reference.docx`。如果学校包有意省略其中某项资产，应在 `README.md` 中记录例外，并让验证命令使用实际的规范资产。

生成的资产应保留逻辑页面契约：

- `school.yaml` 的 `sections:` 应列出目标学校的页面顺序，包括可选或只能手工处理的页面。
- `requirements.yaml` 应为每个由目标学校所有、且其存在、缺失或只能手工处理状态具有实际意义的逻辑页面包含证据记录和检查。
- `template_manifest.yaml` 应将由目标学校所有的逻辑页面公开为槽位、固定块或显式的学校专用渲染器职责。可选内容缺失时，应优先采用审查占位符策略，而非静默删除；只有学校证据支持删除时才能例外。
- `README.md` 应说明哪些逻辑页面是必需、可选、条件性或只能手工处理的，以及哪些页面以占位符形式生成供学生审查。

### 6. 验证

先运行范围最窄且有用的检查；如果运行时资产发生变化，再扩大检查范围：

```bash
uv run docfit schools validate <school-id>
uv run docfit schools coverage <school-id>
uv run docfit schools validate --all
uv run ruff check src/ tests/ scripts/
uv run mypy src/
uv run pytest tests/unit/test_school_coverage.py tests/integration/test_student_fixture_matrix.py
```

如果变更涉及共享运行时、学校发现机制或学生源学校到目标学校的转换矩阵，请使用 `uv run pytest`。

对于深层的模板优先学校包，验证还必须包括：

- 覆盖每个拥有页面的逻辑单元、而非仅覆盖当前审查页面的机器可读起页契约。
- 一个负向回归固件，用于证明多一行或少一行起页内容时验证器会拒绝。
- 在 LibreOffice 中渲染完整文档，检查溢出、页数和表单完整性。
- 对所有逻辑单元起始位置进行最终的规范渲染器审查。在证据台账中保留截图或导出的 PDF 锚点测量结果。

### 7. 回报结果

总结：

- 使用了哪些来源
- 哪些值由程序提取
- 哪些值通过推断得到，以及推断原因
- 逻辑页面台账，包括必需/可选/条件性/只能手工处理状态和空内容策略
- 尚未解决的冲突或只能手工处理的要求
- 执行的确切验证命令及结果
- 该学校包是仅支持浅层验证，还是已经具有可供通用渲染使用的基于槽位的工程模板
