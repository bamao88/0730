# 用户内容提取模块

状态: 当前模块边界
更新日期: 2026-08-18
主要 CLI: `uv run docfit extract-student-content`
Eval CLI: `uv run docfit eval-student-content`
Case CLI: `uv run docfit student-content-e2e`
黑盒合同：[user-content-extraction.md](../contracts/user-content-extraction.md)

本模块把只读学生论文转换为忠实、有序、可追溯的 Student Content Model。它与模板提取并行，
不是模板 workflow 的子流程。

## 边界

| 允许输入 | 输出 | 禁止读取或决定 |
| --- | --- | --- |
| 学生源 DOCX、Field Registry | `student-content.json`、`run-report.json`、Eval report | 学校模板、Fill Contract、目标 placement、目标样式、最终 Word 候选 |

提取 Agent 接收 source inventory item 和 Registry semantic lexicon。它可以标注语义和关系，
但 ordering、源值复制、coverage closure、Registry compatibility 和最终 model assembly 由确定性代码负责。

## 数据流

```text
学生 DOCX
  -> 确定性 Word inspection
  -> 有序 source inventory
  -> Agent 语义标注与关系
  -> 确定性 validation 与 assembly
  -> Student Content Model
```

`items[]` 是顺序真相。`field_results` 只是派生索引，不得改变内容顺序。

## 本模块加载范围

- 根状态：`STATUS.md`
- Gold / Eval contract：`docs/docfit-03-gold-system-design.md`
- Eval 入口：`evals/student-content-extraction/README.md`
- 必要时读取当前详细状态：
  `docs/status/active/docfit-student-content-extraction-gold.md`,
  `docs/status/active/docfit-student-content-extraction-eval.md`

除非任务明确是 integration，否则不要读取模板提取计划、学校模板 workspace、Fill Contract 或 final-fill debug log。

## 输入清单与验收

`evals/student-content-extraction/case-inventory.yaml` 保存受限本地用例入口。先用
`uv run docfit student-content-e2e --list-cases` 检查输入可用性；实际提取与离线评分分开执行。
验收直接检查 `student-content.json` 的内容、字段、顺序、关系和来源；运行报告用于诊断。
学生内容包与复杂对象载荷设计见
[学生内容包架构](../docfit-student-content-package-architecture.md)。
