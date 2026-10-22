# document_map 分页与 Word 区域顺序不可当作页面边界

状态：**诊断已记录；输入组织方案待验证，本文不实施修复。**

模块：模板提取 `unit-boundary`。真实案例：南京农业大学本科模板，
`tests/manual-diagnostics/input/school-template-nannong-undergraduate.docx`，
2026-10-02 运行目录 `temp/template-diagnostic-20261002-njau-full/`。
本记录针对该次运行时的代码基线 `62c1477`；同日后续的 Word 格式事实改动见下文，
不能反推该次 Agent 已收到新事实。

## 产品问题

`document_map` 的 `limit`、`offset` 只控制一次工具回复传输多少源条目，
不表示 Word 的物理页，也不表示学校功能区。该次 Agent 自选 `limit=100`，
依次读取 100、100、11 条，再基于全部 211 条提出 15 个功能区。
提示词只要求沿 `next_offset` 读完，没有要求每页 100 条。
默认 `limit` 为 20，工具 schema 的上限为 200；改变 100 这个数字本身不会建立页面语义，
若仍读完全部条目，也未必减少总上下文。

更关键的是，底层 Word 正文、页眉、页脚和尾注是不同的内容区域（story）。
当前清单的 `source_order` 是供读取与覆盖的统一顺序，不是逐页视觉顺序。
Agent 若没有明确的条目所属区域，就可能把排在正文之后的页眉文字当成正文尾段或标题，
并据此划错单元。页眉在纸面上位于页面顶部，也不能把它在对象流中的位置当成两页之间的切点。

## 本次真实输入的证据

```text
DOCX
  -> inspect 得到 798 个底层 Word 对象
  -> Harness 合并为 211 个有 source_entry_id 的源条目
  -> document_map 按 offset/limit 分三次传输：100 + 100 + 11
  -> Agent 看完全部条目，提出 15 个学校功能区
  -> Harness 检查功能区覆盖
```

- 初始清单 `work/.docfit/initial-source-inventory.json` 中，源条目 1–177 属于正文；
  从第 178 条开始出现页眉、页脚及尾注对象。第 182 条
  `source-entry-5b31861d0bedfba97d7c65ff` 的文字是
  “南京农业大学本科毕业论文（设计）”，底层来源为 `/header[3]/p[1]`。
  第 180 条“5”来自 `/footer[1]/p[1]`。这里的 `header[3]` 是对象区域编号，
  **不是第 3 页**；可见页脚数字在源条目顺序中也不是 1、2、3……的页面顺序。
- `work/.docfit/tool-call-audit.jsonl` 记录了 Agent 的三次 `document_map` 调用：
  `(offset=0, limit=100)`、`(100, 100)`、`(200, 100)`。
  分页发生在完整初始清单建好之后；100 条不是源条目分组规则，也不是 15 个功能区的预切割。
- 运行时的原始源条目有 `/header[...]`、`/footer[...]` 来源；当时 Agent 阅读视图
  对个别条目只给出了 `style_summary.style: header/footer` 一类样式线索，
  没有把 Word story 作为明确、逐条绑定的事实。样式名不能代替实际所属区域。
- 同次运行的 `document_map` 在 `summary.source_entries` 与 `evidence` 重复返回同一窗口条目。
  三次回复约 172 KB，其中约 85 KB 是条目重复包装。这是传输冗余，
  与“页眉归属事实缺失”可同时发生；删掉重复本身不会补齐所属区域。

## 原因与责任边界

本例包含三个应分开的层次：

1. **Word 事实层**需要知道条目属于正文、页眉、页脚或其他 story，以及关联的节与必要布局事实；
   底层 locator 可供 Harness 映射，不应成为 Agent 默认判断输入。
2. **Agent 阅读层**需要把上述已知事实以可读、逐条绑定的方式呈现，
   并维持正文的相邻语义上下文。按 100 条切窗只是传输机制，不能替 Agent 决定功能区或页面。
3. **边界判断层**仍由 Agent 根据学校模板语义提出功能区；Harness 负责源条目映射、连续覆盖与冲突检查。
   不应由代码根据 `/header[3]` 猜“第 3 页”，也不应把页眉页脚强行追加成最后一个正文单元的语义内容。

## 建议的解决方案（未实施）

- 将 `document_map` 的**阅读组织**与**传输分页**分开：先给 Agent 文档区域概览，
  正文按源阅读顺序呈现；页眉、页脚、尾注作为各自 story 的关联上下文呈现，
  每个条目明确带所属区域，并继续使用原 `source_entry_id + span` 判断及映射。
- 分页仅作为有界传输：稳定游标与总数，按可观测的 payload/token 预算选择窗口，
  保留跨窗口必要相邻上下文；不要给 `limit=100` 页面或语义含义。
  一页条目只传一次，概览字段保留总数、窗口和下一游标，详细条目放单一位置。
- 需要**实际物理页**时，使用明确分页/分节事实和渲染后的页面映射验证；
  页眉 story 的顺序和区域编号不能作为页面边界证据。
- 在真实模板上比较输入 bytes/tokens、Agent 查询时间、边界质量及后续语义判断。
  缩短输入不能以丢失页眉归属、图片或相邻学校要求为代价。

## 当前状态与验收

同日提交 `f6544c2` 已增加源 Word 格式事实投影；
`template-semantic-image-evidence-gap-20261002.md` 记录了 PKU 案例中
`document_map`、`unit_evidence_packet` 与修订上下文可见 story 的验证。
这解决了相应案例的**事实可见性**，不证明上述 NJAU 整校在新代码下重新完成了
`E2E agent loop` 或产品验收，也不证明分页/重复传输已优化。

后续验收应分别报告：

| 层级 | 需要证明 |
| --- | --- |
| `logic/contract` | 同一页源条目不重复传输；不同 `limit` 不改变条目身份、顺序和覆盖；每条页眉页脚有明确 story，且不把底层 locator 交给 Agent。 |
| `real replay` | 在 NJAU、PKU 等真实 Word 上核对正文与页眉页脚归属、窗口邻接和分页游标；输入压缩后必要学校事实仍在。 |
| `E2E agent loop` | Agent 看到真实 story 与相邻上下文后，不把页眉当正文标题或物理分页切点；Harness 边界反馈可促成正确修订。 |
| `product acceptance` | 发布的同版本模板与填写契约可用；Word 中核对页眉页脚、实际分页及代表性填写结果。 |

本文只记录问题、既有证据和待验证方案；没有修改 Tool、Agent 或 Harness 行为。
