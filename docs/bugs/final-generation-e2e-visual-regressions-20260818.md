# Bug：final-generation E2E 成稿视觉与结构质量回归

- Status: `OPEN`
- Severity: `P0`
- Bug type: `code-logic`
- Discovered: `2026-08-18`
- Subsystem: `final-generation`
- Affected cases:
  - `student-001-njau-known-gap`
  - `student-001-njau-complete-debug`
- Evidence root:
  - `temp/final-generation-e2e-verify-20260818/eval-known-gap-001/generate-final`
  - `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final`

## 1. 摘要

这轮 E2E 暴露了成稿代码逻辑中的多层质量问题。测试、Gold、报告和发布验收等配套设施另有独立文档跟踪，本文只处理“生成出来的 DOCX/PDF 为什么质量不对”。

Scope：

- 本文处理：TOC、heading、caption、slot、style binding、table、image 等生成逻辑。
- 本文不处理：测试检查组合、`generate PASS` 是否应发布、release gate 如何判定、gold 文件是否可信、报告证据链是否绑定同一 snapshot。

独立非代码生成逻辑配套设施文档：

- [final-generation 非代码生成逻辑配套设施问题](./final-generation-supporting-facilities-20260818.md)

本文聚焦这些代码逻辑问题：

1. 目录和模板生成区没有被真正物化，Word field 只被标 dirty，静态目录缓存和占位符仍留在 PDF 中。
2. 正文入口保留了模板自带的未标记标题和说明文字，同时又导入了学生源正文，导致标题重复、关键词说明残留。
3. 学生内容模型里的标题值本身缺少或混用目标编号，final-generation 当前没有标题编号 materializer。
4. 图题、表题虽然有语义 role，但 Fill Contract 仍用 debug 绑定，最终被应用成参考文献/正文样式。
5. 表格只做了宽度和居中等结构整理，没有目标表格/cell 样式 materialization。
6. 图片对象数量被保留，但没有几何和分页验收，出现图片塌缩、压成细线、叠到正文或表格下方。

所以后续不要逐个修“目录样式”“图片居中”这类表象。应该按结构、填写、样式/对象三个实现层收敛根因。

## 2. 证据范围

### 2.1 已检查 PDF

- `known-gap-001` 的报告绑定 PDF：
  `temp/final-generation-e2e-verify-20260818/eval-known-gap-001/generate-final/.docfit/evidence/renders/794bd880a5e25a9cc71d0a359b94c9a438d593a17daac30aa57157818a055f48/document.pdf`
  - LibreOffice 渲染，34 页。
  - `run-report.json` 状态为 `PARTIAL`，`partial_reasons` 包含 `generated_regions_not_materialized`。
- `complete-debug-002` 的报告绑定 PDF：
  `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final/.docfit/evidence/renders/24852a6615507e248bd060d1ef010e999ece66e80171221d93b5c2fae138cd01/document.pdf`
  - LibreOffice 渲染，34 页。
  - `run-report.json` 状态为 `COMPLETE`，`partial_reasons=[]`，`style_occurrence_counts.failed=0`。
  - 这条状态和发布资格问题属于独立配套设施文档；本文只把该输出作为质量问题观察样本。
- `complete-debug-002` 目录下另有 `final.pdf`：
  `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final/final.pdf`
  - macOS Quartz 渲染，33 页。
  - 与 run-report 绑定 PDF 的页数不同。报告证据链归独立配套设施文档，本文只记录这两个渲染结果暴露的质量差异。

### 2.2 额外质量检查

当前复验运行了带 `quality` 的 complete-debug case：

```bash
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --checks input,style,generate,quality --output temp/final-generation-quality-compare-20260818/eval-complete-debug-quality-002 --json
```

结果：`input/style/generate` 通过，`quality` 失败，报告位于：

- `temp/final-generation-quality-compare-20260818/eval-complete-debug-quality-002/quality/quality-report.json`
- `temp/final-generation-quality-compare-20260818/eval-complete-debug-quality-002/quality/quality-report.md`

关键指标：

| 指标 | 实际值 | 阈值 | 结论 |
| --- | ---: | ---: | --- |
| full text similarity | `0.962531` | `>=0.99` | FAIL |
| paragraph sequence similarity | `0.753165` | `>=0.95` | FAIL |
| page count delta | `-3` | `0` | FAIL |
| placeholder residue count | `7` | `0` | FAIL |
| mean visual changed ratio | `0.196102` | `<=0.02` | FAIL |
| max page visual changed ratio | `0.43453` | `<=0.08` | FAIL |

这说明当前成稿质量仍未达到 gold。Gold、测试和发布判定由独立配套设施文档处理。

## 3. 现象聚类

### 3.1 目录和生成区

PDF 中仍有模板目录占位符、错误页码和重复条目。

典型表现：

- `known-gap-001` 第 4 页目录保留 `【一级章标题】`、`【二级标题】`、`【三级标题】`、`第X章 结论与展望`，多项页码都是 `1`。
- `complete-debug-002` 第 3-4 页目录既有真实条目，也有重复的 `第一章 文献综述` / `第一章文献综述` 和模板尾部占位符。

### 3.2 模板残留和标题重复

正文中出现模板静态标题和学生源标题并存：

- 模板保留 `第一章 文献综述`。
- 学生源又导入 `第一章文献综述`。
- 关键词段落仍含模板说明文字，例如 `关键词（四号黑体）：...（3-5个，小四号宋体）`。

这不是单纯的 heading 样式问题，而是模板目标清理、正文入口和内容导入的边界没有闭合。

### 3.3 标题编号和层级文本

`student-content.json` 中标题值本身不稳定：

- 一级标题有 `第一章文献综述`，后续又有不带章号的 `材料与方法`、`结果与分析`、`结论与展望`。
- 三级标题有的缺少编号，如 `PGPR促进植物生长的直接作用`、`实验材料`。
- 有的保留源编号但编号上下文错误，如 `1.3 打靶片段的扩增、检测及回收`、`1.1 基因缺失突变株的PCR验证结果`。

final-generation 当前只搬运和套用样式，没有把标题树转成目标模板要求的 display numbering。

### 3.4 图题和表题

图题、表题在 PDF 中普遍没有按目标居中，且表题缺少目标序号：

- 表题出现 `表 PCR反应体系` / `Table PCR Reaction System`，不是 `表 2-2 ...` 这类目标编号。
- 图题、表题中英双语行保留了源格式，位置和对齐不一致。
- 部分 Figure/Table 英文编号与中文编号不同步。

### 3.5 表格样式

表格结构和内容被搬运了，但目标表格样式没有完成：

- 边框和三线表风格不符合目标。
- 表头/正文 cell 样式没有目标化。
- 表题位置和表格块间距不符合目标。

### 3.6 图片布局

图片对象没有丢失，但可视结果不可发布：

- 技术路线图几乎压成一条细线。
- 多张实验图片变成黑色横条或极小 strip。
- 折线/柱状图只剩坐标轴或标题，主体叠在正文/表格区域下方。
- 图与图题、图与后续正文没有稳定分页/间距约束。

这类问题不能用“media count match”证明通过。

## 4. 问题分层和模块归因

gold 对比失败时，先按模块层级定位，不能直接归因到某一个样例、某一个学校或某一条样式。

| 层级 | 判断问题 | 当前证据 | 当前结论 | 本 bug 是否处理 |
| --- | --- | --- | --- | --- |
| 输入包完整性 | Registry、学生内容包、模板包、样式策略是否身份一致、文件完整 | `input` check 通过；complete case `missing_required_count=0` | 不是当前主问题 | 否；输入包和 case 配置归配套设施文档 |
| 内容解析和语义绑定 | 学生内容是否缺字段、错 `field_id`、正文顺序错、复杂对象缺搬运引用 | 图片、表格数量匹配；正文 heading/table/figure 已绑定 Registry 字段；`unsupported_source_object_count=0` | 不是当前主问题；源编号文本可作为 evidence，但不能把目标编号生成责任退回解析层 | 否；除非发现 required 内容或复杂对象引用缺失 |
| placement / 填写 | 正确内容是否写到正确 slot / region，是否多段截断，是否留下模板说明文字 | rich text 多段截断曾发生；关键词说明、模板占位仍可能残留 | 有明确问题；slot 替换边界、generated/remove region 处置不完整 | 是 |
| 结构 materialization | heading 编号、caption 编号、TOC 缓存、section、页码和前置页编号是否按目标模板生成 | `_request_toc_update()` 只标 dirty；caption Registry 写明目标编号，但 projection 未生成；页数与 gold 差异明显 | 当前主问题；只搬运正文并套样式，不等于已经生成目标模板结构 | 是 |
| 样式 contract 应用 | 每个实际 role 是否有 school / preset 决策，是否写入并回读校验 | style occurrence 可 `failed=0/unresolved=0`，但视觉和编号仍失败 | 不是当前主问题；style PASS 只说明 contract 落地，不说明 gold 质量通过 | 仅处理 role 绑定错位和属性覆盖不足 |
| 表格和图片可视质量 | 对象是否不仅存在，而且在 PDF 中可见、尺寸合理、不叠压 | media count 可匹配，但历史 PDF 中出现图片塌缩、表格样式未目标化 | 对象处理需要从“数量存在”扩展到“可视可发布” | 是 |
| gold 质量门和发布证据链 | 文本、结构、媒体、分页和视觉渲染是否接近 gold；报告是否绑定唯一 final snapshot | `generate` 可 PASS 但 `quality` FAIL；报告 PDF 与目录下 PDF 可能不是同一 renderer/snapshot | 这是测试、Gold、报告和发布语义问题，不是本文的代码修复范围 | 否；移到独立配套设施文档 |

## 5. 代码证据

测试、Gold、报告和发布验收相关证据已移到独立配套设施文档：  
[final-generation 非代码生成逻辑配套设施问题](./final-generation-supporting-facilities-20260818.md)。

### 5.1 TOC 只是标 dirty

`src/docfit/content/projection.py:_request_toc_update()` 做了两件事：

1. 给 TOC field begin 标 `dirty=true`。
2. 在 `word/settings.xml` 设置 `w:updateFields=true`。

返回值仍明确写着：

```json
"word_refresh_still_requires_canonical_word_verification": true
```

这说明当前 projection 没有实际刷新并回读 TOC 缓存。相关位置：`src/docfit/content/projection.py:970-1018`。

### 5.2 Fill 只清理 content-control tag

`fill_template()` 的 block 导入使用 `replace_content_control_tag=tag`，最后只调用：

```python
mutate_content_controls(..., remove_body_tags=tuple(dict.fromkeys(remove_tags)))
```

也就是说，没有被模板抽取标成 content control 或 remove tag 的静态段落不会被删除。正文中的模板标题、目录缓存、说明文字如果是普通段落，就会保留下来。

相关位置：

- `src/docfit/content/fill.py:167-177`
- `src/docfit/content/fill.py:220-225`

### 5.3 分区识别了 generated/remove，但没有保证物化闭环

`compile_final_content_partition()` 会把 template regions 分成 `generated_regions`、`retained_regions`、`remove_regions`。但这只是视图，后续如果 Fill Contract 接受了不完整 region 或 complete case 没有把 residue 设为 blocking，模板残留仍会进入 final。

相关位置：`src/docfit/content/partition.py:106-175`。

### 5.4 题注 role 有映射，但 contract 绑定错位

`src/docfit/content/style_application.py` 的 role 映射是合理的：

```python
"figure_caption": "body.figure.caption"
"table_caption": "body.table.caption"
```

但本次 Fill Contract 中实际 slot 是：

- `body.figure.caption.1` -> `style.slot.references.entries.1`
- `body.table.caption.1` -> `style.slot.references.entries.1`
- `body.figure.1` -> `style.slot.body.paragraph.1`

并且标记为 `mapping_status: debug_e2e_role_binding`。

所以 style audit 的 `passed=244` 只能说明 occurrence 被写入并回读，不说明 semantic role 绑定到了正确目标样式。

相关位置：

- `src/docfit/content/style_application.py:16-26`
- `src/docfit/content/style_application.py:148-192`
- `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final/input/fill-contract.yaml:2086-2145`

### 5.5 Registry 要求目标编号，但 projection 未实现

`content-fields.yaml` 对图题/表题写明：

- 源 prefix 应从 normalized value 中移除。
- `generation_owner: target_template_caption_numbering`。
- number mismatch 需要保留证据并要求人工确认。

但 projection 当前只做 paragraph normalize，没有重建目标编号，也没有中英文并行题注编号同步。

相关位置：

- `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final/input/content-fields.yaml:417-450`
- `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final/input/content-fields.yaml:470-499`
- `src/docfit/content/projection.py:772-775`

### 5.6 表格 materialization 能力不足

`_normalize_table()` 当前只处理表格宽度、layout、居中、grid 缩放和 row 不拆分。`SUPPORTED_MATERIALIZED_PROPERTIES` 只包含 run 和 paragraph 属性，没有 table/cell property。

Fill Contract 里已经出现 cell 属性期望，如 `cell.vertical_alignment`、`cell.padding_mm.*`，但 materializer 不支持。

相关位置：

- `src/docfit/content/projection.py:867-913`
- `src/docfit/styles/materialization.py:42-79`
- `temp/final-generation-e2e-verify-20260818/eval-complete-debug-002/generate-final/input/fill-contract.yaml:1070-1095`

### 5.7 图片 layout 只有对象级整理，没有视觉几何验收

`_normalize_drawing_paragraph()` 当前会：

- 段落居中；
- anchor 转 inline；
- 超宽时 clamp width。

但不会检查：

- 图片是否接近 0 高度；
- 宽高比是否异常；
- 图片是否被表格/正文覆盖；
- 图片和题注是否作为 block 一起分页；
- 图前图后间距是否符合目标模板。

相关位置：

- `src/docfit/content/projection.py:778-799`
- `src/docfit/content/projection.py:843-865`
- `src/docfit/content/projection.py:916-967`

## 6. 修复计划和验收标准

本 bug 的修复顺序不能从某个页面表象开始。先补结构 materialization，再补 slot 残留清理，最后看 style coverage 对分页和视觉的影响。测试、Gold、报告和发布验收不是本 bug 的阶段。

### 6.1 阶段一：结构 materialization

目标：把 Registry 语义坐标和模板目标规则，真正生成成 Word 的结构结果，而不是只搬运源段落。

| 范围 | 计划 | 通过标准 |
| --- | --- | --- |
| heading 编号 | 根据正文流中的 `body.heading.outline*` 重建目标模板标题层级和编号；源文档编号只作为 evidence，最终显示归目标模板 | 正文标题显示目标模板编号；目录中的标题编号与正文一致；不会出现第二章下仍延续上一章编号 |
| caption 编号 | 根据图、表与章节关系生成图题、表题编号；剥离源 caption 旧 prefix 后重建中英并行编号 | 中英文图题、表题编号与 gold 一致；没有 `表 PCR反应体系` 这类缺编号结果；图表数量和 media hash 不变 |
| TOC 缓存 | 在最终 heading、caption、页码稳定之后刷新或物化目录字段缓存，并回读验证 | 目录不再出现 `【一级章标题】`、`第X章` 等占位；目录页码与渲染页码一致；CLI 产物不依赖人工打开 Word 才正确 |
| 页码和 section | 按模板规则处理封面、摘要、目录、正文、参考文献等 section；前置页按模板要求使用 Roman 或其他格式，正文按要求重启 | gold 对比页数差为 0；前置页页码格式正确；正文第一页编号正确；页眉页脚未丢失 |

阶段通过标准：

- heading、caption、TOC、page numbering 各有独立单元或集成测试；
- `quality` 不再因为目录占位、标题编号、题注编号或页码失败；
- 媒体和表格数量不下降，media delta 为 0；
- 若仍失败，失败项必须落在样式覆盖或视觉分页微差，不能再落在结构生成。

### 6.2 阶段二：slot 残留清理

目标：内容已经写入后，模板说明文字、示例文字和占位符不能继续留在同一段或同一区域。

| 范围 | 计划 | 通过标准 |
| --- | --- | --- |
| named text slot | 替换时识别 slot 的完整可写边界，不只替换 content control 内部最小文本 | 关键词、题名、作者等字段不残留字号说明、字数说明或示例文字 |
| generated / remove region | 对模板声明为生成或删除的区域执行明确处置，并输出 materialized evidence | `【未细分的相关学术成果】`、静态 TOC cache、正文示例标题不会进入 final |
| 残留检测 | 把模板占位、说明文字和示例文字作为 quality blocking 项 | `quality-report` 的 residue sample 为空 |

阶段通过标准：

- placeholder / template-instruction residue 为 0；
- named fields 的文本只包含最终内容和模板规定的固定标签，例如 `关键词：`；
- known-gap case 仍按预期保持 `PARTIAL`，不会因为清理策略误删需要保留的模板内容。

### 6.3 阶段三：style coverage、表格图片和视觉分页

目标：结构和残留已经正确之后，再判断分页差异是否来自 style contract 覆盖不足、表格/cell materialization 不足或图片几何问题。

| 范围 | 计划 | 通过标准 |
| --- | --- | --- |
| style coverage | 检查影响分页的属性闭包：字体、字号、行距、段前后、缩进、keep-with-next、page-break-before、页边距、表格内边距 | style occurrence `failed=0`、`unresolved=0`，且影响分页的 required 属性没有 silent default |
| 表格/cell 样式 | 扩展 table/cell property 写入和校验，覆盖 border、padding、vertical alignment、header row、表内段落样式 | 表格边框、表头、表内字体、行距、表题位置与 gold 接近，visual diff 明显下降 |
| 图片几何和分页 | 增加 image geometry audit；图和题注组成 block，应用 keep-with-next、spacing、page-fit 规则 | 图片完整可见，非近零尺寸，不叠压正文或表格，图题居中且跟随图片 |
| render diff | 使用 gold quality check 比较 PDF 页数和页面像素差异 | 页数差为 0；平均视觉变化像素比例不高于阈值；最大单页变化比例不高于阈值 |

本 bug 的复验标准如下。这些指标用于证明成稿代码逻辑已修复，不定义 Gold 管理、测试组合、报告证据链或发布门禁：

- `style_occurrence_counts.failed=0` 且 `style_occurrence_counts.unresolved=0`；
- `quality.status=PASS`；
- gold 文本相似度不低于 0.99；
- 段落序列相似度不低于 0.95；
- 页数差绝对值为 0；
- media delta 为 0；
- placeholder residue 为 0；
- 平均视觉变化像素比例不高于 0.02，最大单页不高于 0.08；
- 不只看单个样例：所有已注册 complete quality case 全部 `input/style/generate/quality` 通过；known-gap case 只验证预期 partial 原因。

## 7. 回归检查清单

本清单只用于复验成稿代码质量，不定义发布资格。每次修复后至少跑：

```bash
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --checks input,style,generate,quality --output temp/final-generation-regression/<run-id>/complete-debug --json
```

known-gap case 要先确认当前 case.json 与输入包期望一致，再跑同样的 quality/generate 组合。

`generate`、`quality`、Gold 和 release gate 的语义区分，见独立配套设施文档。

## 8. 架构约束

按照本仓库 `AGENTS.md` 和官方 Claude Agent SDK/Skills 文档，本问题不要通过新增一套应用内语义工作流来解决。推荐边界是：

- 语义判断、模板理解、异常恢复：由 Agent + Skill + References + Tool feedback 承担。
- 确定性约束：由 Tools/scripts 实现，例如 field refresh、编号 materializer、table/cell 写入、image geometry audit。
- 发布资格和不可逆输出：由 application code 强制 gate。

参考：

- <https://code.claude.com/docs/en/agent-sdk/overview>
- <https://code.claude.com/docs/en/agent-sdk/claude-code-features>
- <https://code.claude.com/docs/en/agent-sdk/skills>
- <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>
