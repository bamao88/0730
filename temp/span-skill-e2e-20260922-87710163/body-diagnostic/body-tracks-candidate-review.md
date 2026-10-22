# 两个正文分支的候选语义审阅

验证层级：真实运行中已落盘的 **未接受候选**，只读审阅。未证明整体校验、DOCX 物化、real replay 或 product acceptance 通过。读取对象仅为本次源 DOCX、requirements PDF 可见文字、输入 Registry 和候选公开字段；没有读取 Gold 或隐藏思考，没有修改 live task。

## 主要发现

1. **batch 7 把序号当成完整第四级标题，且同一 entry 出现两个正文成员。** `source-entry-7ea6a5525cb5350f7459b141` 原文为 `□□（1）……[1]。（四级标题不单独占行书写）`；parts[1] 仅 `（1）` 绑定 `body.heading.outline4`，parts[2] 的 `……[1]。` 又绑定 `body.paragraph`。序号不等于可填写标题，且违反当前每个 entry 最多一个带字段正文成员的合同。可能把学生标题替换到序号位置，仍需以整体校验和最终产物确认实际后果。
2. **batch 7 将写作位置提示当成固定正文。** `source-entry-e190b04a11e55c8a8e6aa5ec` 的 parts[1] 把 `（导入语）` 判为 fixed_label，reason 断言学生应保留该字面。它在源材料中位于省略号正文占位之前，缺少最终正文必须显示该提示的依据，存在模板说明残留风险。此项属于语义风险，不是字段范围机械错误。
3. **batch 6 对自动编号作了未经来源证明的假设。** 五个标题的 `1 / 2 / 2.1 / 2.1.1 / 5` 均为 style_only，reason 由 Registry 的“使用模板 Heading 1 编号”推成已有自动编号机制；这些源段落的序号实际是可见文字，且没有直接 pStyle/numPr。不能据此声称编号生成已闭合。若此举只是记录待承接的编号义务，是否可消费仍需后续结构与物化证据；不直接宣判这种拆分一定失败。
4. **batch 6 有两处候选字符拼接缺空格。** 前言 entry `cd6aa8…` 与第一正文 entry `344bb6…` 在说明前原本各有两个 ASCII 空格，候选对应 style_only part 的 text 却为空串。各少两个空格；非空白字符均完整。此项仅反映落盘候选，不在未比较原始 Tool 参数前归因于模型或规范化，也不代替原生校验。

## 同时确认

- batch 6 一级/二级/三级分别绑定 outline1/outline2/outline3，层级没有错位；`（1）……[1]。` 整体作为普通正文成员，没有误造独立第四级标题。
- batch 7 前三级标题整体保留编号与标题样例字样，分别绑定 outline1/outline2/outline3；`五、结束语` 实际 part 也是整体 body_structure，并非 summary 所称 fixed label。
- batch 6 为 9/11 条原文精确拼接；batch 7 为 11/11。全部 22 条非空白字符均一致。只检查文字分段，未调用运行时反馈或改动候选。

逐条原文、parts、reason、候选摘要及 digest 见同目录 `body-tracks-candidate-review.json`。上述结果不应作为运行 Agent 的新输入或自动修订答案。
