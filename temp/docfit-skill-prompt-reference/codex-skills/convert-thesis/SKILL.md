---
name: convert-thesis
description: 把学生论文 DOCX 转换成已验收学校模板要求的最终 Word（正文原地改版式、前置模板填空与嫁接、目录页码测算），并生成内容零丢失、占位符、分页和逐页渲染的审计证据。凡是用户要求论文排版、毕业论文格式调整、按学校要求改 Word、套用学校模板、论文格式转换，或同时提供学校/模板与学生论文 DOCX 时都使用本 skill，即使用户没有说“转换”或“skill”。
---

# Convert Thesis

把学校差异只从 accepted 学校库读取。把学生文字、图片、表格、公式、脚注、批注和修订视为受保护内容；只改变学校要求覆盖的版式与结构。

## 先确认支持范围

要求用户或工作区提供：

- 一份学生原稿 `.docx`；
- 学校 ID，必要时提供库版本；
- 一个满足 [学校库输入契约](references/library-contract.md) 的 `library/<school>/<version>/`。

遇到以下任一情况立即停止并明确报告“不支持/输入未就绪”，不要硬做：

- 输入不是 `.docx`、ZIP 包损坏、加密或受密码保护；
- 文档是纯扫描件，除图片外没有可定位文字；
- 学校条目不存在、版本不唯一、`entry.yaml.status` 不是 `accepted`；
- accepted 条目记录的三件套 SHA-256 与当前文件不一致；
- 必填槽位无法从学生原稿可靠取值；
- 发现无法保真的未知可见对象，而当前工具不能安全处理。

## 建立只写输出区

创建独立输出目录，绝不修改学生原稿或学校库文件。至少规划：

```text
conversion-output/
├── final.docx
├── final.pdf
├── pages/
├── analysis/
│   ├── student/structure.json
│   ├── student/dump_summary.md
│   └── template/...
├── diff_checklist.md
├── slot_fill_report.md
├── anchors.yaml
├── pagination_report.md
├── content_check.md
├── placeholder_check.md
└── run_log.md
```

将脚本路径解析为本 skill 目录下的 `scripts/`。脚本退出码统一为：`0=PASS/成功`、`1=FAIL`、`2=UNKNOWN 或输入/环境错误`。任何非零退出码都必须原样保留。

## 执行六步转换

### 1. 校验学校库并剖析输入

完整阅读 [坑清单](references/pitfalls.md)，再动学生文档。

校验 `entry.yaml` 状态和三件套哈希。把选择的学校 ID、版本、entry 路径和所有哈希写入 `run_log.md`。

分别剖析学生原稿和 `prefill_template.docx`：

```bash
python3 <skill-dir>/scripts/dump_docx.py student.docx \
  --out-dir conversion-output/analysis/student

python3 <skill-dir>/scripts/dump_docx.py prefill_template.docx \
  --out-dir conversion-output/analysis/template
```

阅读两个 `dump_summary.md` 和必要的 `structure.json`。尤其检查 SDT、文本框、字段、批注、修订、脚注/尾注、媒体、嵌入对象、分节和页眉页脚。

阅读该校 `requirements.md`，产出 `diff_checklist.md`。逐项写：

- 学校要求及来源位置；
- 学生现状；
- 将执行的修改；
- 修改层级（节/段落/表格/run/字段/编号）；
- 内容风险与验证方式；
- 状态：`pending`、`done`、`needs_review`。

不要把“整份换字体”当清单；按可审计要求拆项。

### 2. 在学生正文原位改版式

从学生原稿复制工作副本。保留原 OOXML 元素身份，优先只改属性：

- 页面/页眉页脚/页码改 `sectPr`；
- 段落对齐、缩进、段前后、行距改 `pPr`；
- 字体、字号、粗斜体改 `rPr` 或已确认样式；
- 标题编号改编号定义与引用；
- 表格只改宽度、边框、对齐、分页属性；
- 图片只改显示尺寸/环绕，保留二进制和关系。

每完成一项就在 `diff_checklist.md` 标 `done` 并记录具体对象。修改文本前先断言目标段落的去空白文字与分析记录一致；格式任务不得改变 `w:t`。

需要跨文档复制、分节、域、制表位或三线表时先读 [OOXML 手术配方](references/ooxml-recipes.md)。不要用删除学生内容、合并内容或改写句子解决分页问题。

### 3. 填充并嫁接前置模板

从 `slots.yaml` 逐项定位学生来源。只取原值，不翻译、不润色、不猜测。把每个槽位的以下信息写入 `slot_fill_report.md`：

- 槽位 ID 和 required 状态；
- 写入值；
- 学生来源 part、段落/表格坐标和原文；
- 提取方式；
- 置信度；
- 是否需要人工确认。

必填槽位有歧义时停止；可选槽位缺失时保留为空并显式记录，不能保留 `{{slot}}`。

在已验收 `prefill_template.docx` 的副本中按跨 run 规则填值，再将前置节嫁接到学生工作副本的正文前。复制样式、编号、关系、媒体、页眉页脚和分节引用；不要只复制 `document.xml` 节点。

嫁接后立即重跑 `dump_docx.py`，确认：

- 学生媒体、嵌入对象、批注和修订未减少；
- 没有新增未知 SDT 或重复 TOC；
- 正文后的原分节仍存在；
- 前置与正文页码体系按学校要求断开。

### 4. 正文定稿后生成目录与页码

先完成全部会改变分页的字体、行距、表格、图片和分节修改。再从最终正文提取唯一标题锚点，按 [锚点契约](references/anchors.md) 写 `anchors.yaml`。

先只测算：

```bash
python3 <skill-dir>/scripts/measure_pages.py final-before-pagination.docx \
  --anchors conversion-output/anchors.yaml \
  --out-dir conversion-output
```

若目录是手工条目，使用 `--output-docx conversion-output/final.docx` 让脚本回填并迭代到稳定。若目录由 Word TOC/PAGEREF 字段管理，保留字段，在 Microsoft Word 更新全部字段；脚本返回 `UNKNOWN` 时不得改写为通过。

将 `pagination_report.md` 原样保留。报告标记 `approximate` 时，在 Word 中人工核对全部目录页码；即使标记稳定，也抽查至少 3–5 个条目。

### 5. 渲染并逐页检查

渲染最终 DOCX：

```bash
python3 <skill-dir>/scripts/render_pages.py conversion-output/final.docx \
  --out-dir conversion-output
```

逐页查看所有 `pages/page_NNN.png`，不要只抽封面。把每页结论写入 `run_log.md`，至少检查：

- 封面与固定前置页没有溢出；
- 没有意外空白页、重复目录或模板说明文字；
- 前置页、目录、正文的页码格式/起始值正确；
- 页眉没有跨节串联；
- 标题不孤行，图表/题注不错误分离；
- 图片、公式、表格、脚注和参考文献完整；
- 长标题、长表格和横向页没有裁切；
- 修订和批注未被静默清除。

无法可靠判断的页面写 `needs_review`，不要写“看起来可以”。

### 6. 运行最终裁判

按 `requirements.md` 的边界正则运行内容检查；未配置时先自动检测：

```bash
python3 <skill-dir>/scripts/check_content.py \
  student.docx conversion-output/final.docx \
  --report conversion-output/content_check.md
```

自动边界返回 `UNKNOWN` 时，从学校要求确定显式边界并用
`--source-start-regex`、`--source-end-regex`、`--final-start-regex`、
`--final-end-regex` 重跑。禁止扩大到全文件后用相似度给假绿。

运行占位符与说明文字检查：

```bash
python3 <skill-dir>/scripts/check_placeholders.py \
  conversion-output/final.docx slots.yaml requirements.md \
  --report conversion-output/placeholder_check.md
```

把两个脚本的 Markdown 结果原文附入或链接到最终报告。禁止总结、改写或解释性弱化脚本结论；例如“差 3 个字符但应该没关系”属于违规。例外只能由人基于逐条差异接受，不能由 agent 替人接受。

## 始终保持的判断规则

- 保留全部学生内容；学校格式要求与内容完整性冲突时优先保内容并报告版式残留。
- 保留批注、修订和原始可恢复值——它们是用户的沟通与证据记录。
- 颜色异常先判断是否来自修订显示；不是字体问题就不要改字体颜色。
- 只处理 `requirements.md` 明确覆盖的学校差异；不要在 skill 或脚本里写学校名分支。
- 发现未覆盖情况先写 `run_log.md`，再决定安全处理或停止；禁止静默跳过。
- 把自动裁判与人工视觉检查分开：脚本决定确定性事实，人检查页面质量。
- 每次保存都写新文件；不覆盖输入，不修改 accepted 学校库。

## 完成定义

只有同时满足以下条件才说“转换完成”：

- `final.docx` 可打开且 `dump_docx.py` 成功；
- `final.pdf` 与全部逐页 PNG 已生成；
- `diff_checklist.md` 无 `pending`，所有 `needs_review` 已明确交给人；
- `slot_fill_report.md` 覆盖每个槽位且没有残留 `{{...}}`；
- `content_check.md` 为 `PASS`；
- `placeholder_check.md` 为 `PASS`，两个残留数字均为 0；
- `pagination_report.md` 的所有标题已定位；手工目录回填时 `stable=true`；
- `run_log.md` 含每页检查结论、Word 目录抽查结果和所有未覆盖情况；
- 最终输出没有未解释的 FAIL/UNKNOWN。

缺任一产物或存在未解释 FAIL/UNKNOWN 时，准确说“部分完成/待人工确认”，列出阻塞项；不要用文件已生成代替完成信号。
