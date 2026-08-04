# 标题锚点与目录页码

只在运行 `measure_pages.py` 前阅读本文件。

## 锚点文件

首选 YAML：

```yaml
anchors:
  - id: chapter_1
    text: "1 前言"
    toc_text: "1 前言"
    occurrence: last
    toc_occurrence: 1
  - id: chapter_2
    text: "2 材料与方法"
    toc_text: "2 材料与方法"
    occurrence: last
    toc_occurrence: 1
  - id: references
    text: "参考文献"
    toc_text: "参考文献"
    occurrence: last
    toc_occurrence: 1
```

也可传 JSON，或每行 `id<TAB>text<TAB>toc_text` 的 TSV。

字段：

- `id`：报告中的稳定标识，使用小写字母、数字、`_` 或 `-`。
- `text`：正文标题的完整可见文字。使用足够长且唯一的文字，不用“摘要”“1”等短锚点。
- `toc_text`：目录行开头的可见文字；省略时等于 `text`。
- `occurrence`：PDF 中取第几次命中。目录通常先出现一次，所以默认 `last`。
- `toc_occurrence`：正文标题之前第几条同前缀目录行，默认 `1`。

## 两种模式

只测算：

```bash
python3 scripts/measure_pages.py final.docx \
  --anchors anchors.yaml \
  --out-dir conversion-output
```

测算并回填手工目录：

```bash
python3 scripts/measure_pages.py final-before-pagination.docx \
  --anchors anchors.yaml \
  --out-dir conversion-output \
  --output-docx final.docx
```

脚本只安全修改“同一标题至少出现两次”时正文标题之前的目录行。若目录由 Word `TOC`/`PAGEREF` 字段管理，脚本不冒险篡改字段结果，而返回 `UNKNOWN`；使用 Microsoft Word 更新全部字段，再重跑只测算模式核对。

## 验收

- 所有锚点都必须找到。
- 自动回填时 `stable` 必须为 `true`。
- 若报告把行距标为 `approximate`，LibreOffice 页码只是测算值；必须在 Microsoft Word 打开最终文件、更新字段并抽查目录。
- 无论行距判定如何，最终都从逐页 PNG 抽查 3–5 个目录条目。
