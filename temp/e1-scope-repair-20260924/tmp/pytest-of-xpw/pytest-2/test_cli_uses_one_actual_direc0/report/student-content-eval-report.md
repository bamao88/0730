# synthetic-student.extraction 内容提取 Actual–Gold 评测报告

- 结论：`PASS`
- Gold revision：`2026-08-12.r1`
- Actual 模型状态：`READY`
- 隐私：报告只包含 hash、计数、field_id、源对象 ID 和运行元数据，不包含学生正文。

## 评测维度

| 维度 | 结论 | 核心证据 |
|---|---|---|
| 来源与版本绑定 | PASS | source、Registry、inventory 一致性 |
| 源内容覆盖 | PASS | Gold 映射 2；遗漏 0；未知多出 0 |
| Registry 字段语义 | PASS | 命中 2/2；字段差异 0 |
| 原文值忠实度 | PASS | 命中 2/2 |
| 语义实例拆分/合并 | PASS | 精确绑定组 2/2 |
| 内容顺序 | PASS | Gold 2；Actual 对齐 2 |
| 父子与题注关系 | PASS | 差异 0 |
| 真实运行证据 | PASS | batch 1/1；session 1 |

## 内容规模

- Inventory 内容项：2
- Actual 内容项：2
- Gold 语义内容项：3（其中无源结构项 1）
- Gold 源引用对齐：2/2（直接 ID 2；locator crosswalk 0）

## 阻断项与研发含义

- 无；本次 Actual 可作为该 Gold revision 下的通过结果。

## 顺序判定

- 权威来源：`Gold items[] under docfit-source-order/v1`
- 完整语义序列一致：`True`
- 已匹配内容的相对顺序一致：`True`
- 首个差异位置及对应源对象 ID 见同目录 JSON 的 `order_comparison.first_mismatch`。

## 详细差异入口

- 字段漏项/错项：`field_comparison`
- 原文值差异：`value_comparison`
- 拆分/合并差异：`semantic_grouping_comparison`
- 顺序差异：`order_comparison`
- 父子与题注关系：`hierarchy_comparison`
- 源覆盖与排除项：`source_coverage_comparison`
