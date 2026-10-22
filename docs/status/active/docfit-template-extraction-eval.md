# DocFit 模板提取静态 Eval 状态

状态: `IMPLEMENTATION_PASS / SCHOOL_GOLD_ACCEPTED`
Runtime 边界: `evals/template-extraction/**`
Eval 说明: `evals/template-extraction/README.md`
来源设计: `docs/plans/docfit-template-extraction-eval/DESIGN.md`

## 当前状态

模板提取静态 Eval 已实现为与产品运行时代码物理解耦的只读评测工程。它只读取已经生成的
Actual 模板与 Fill Contract，并与 case 绑定的 Gold 模板与 Fill Contract 比较；不调用
`docfit prepare-template`，不 import `src/docfit/**`，不读取 Agent prompt，也不反向控制模板提取运行时。

评测产物是同源 JSON/Markdown 报告：

```text
template-extraction-eval-report.json
template-extraction-eval-report.md
```

质量结论分为 `PASS`、`FAIL`、`UNKNOWN`；输入、schema、hash 或 Gold 资格错误返回
`INPUT_ERROR`，不生成伪质量分数。

## 已实现证据

- 独立 `pyproject.toml`、`uv.lock`、`run_eval.py`、`run_raw_source_sentinel.py`、包、schema、fixtures 和测试
  均位于 `evals/template-extraction/**`。
- 已实现 Actual/Gold 共用 DOCX facts、protected/slot/remove 断言、责任覆盖、双 50 分评分、
  coverage、hard failure 和同源报告发布。
- S00-S13 合成 fixture 覆盖 pass、单变量 fail、UNKNOWN、INPUT_ERROR、表格和公式/域/书签事实。
- 三校 accepted Gold case 已冻结，每校只保留
  `final-template.gold.docx + fill-contract.gold.yaml` 两份核心 Truth 文件。
- 三个原始 Word Gold 文件已用 Word 原生批注完成全覆盖 Review：HUNAU 227 条、NJAU 96 条、
  PKU 159 条；对象级批注覆盖字段槽、处理区域、逻辑页和已接受样式缺口，覆盖批注覆盖
  正文所有可见内容块，并用总览批注说明页眉/页脚保留策略。
- 三校自比较均为 `PASS / 100.0`；这证明静态 Eval 能消费三校 Gold，不证明端到端 M3 完成。

## 已接受学校 Gold

2026-08-17，三校模板提取 Gold 已由 `xpw` accepted：

- 每校只保留 `final-template.gold.docx + fill-contract.gold.yaml` 两份核心 Truth 文件；
- `case.yaml`、Fill Contract、receipt 中的 template hash、contract hash、reviewer 记录和数据权限已绑定；
- Word 批注以原始 `.docx` 的批注/评论功能呈现，不另造 review 文档作为 Truth；
- 每校保留 `review/accepted-2026-08-17/reviewed-final-template.gold.docx` 和
  `approval-record.yaml`，用于追溯批注版 Word 与 Gold pair 的 hash 对应关系；
- 2026-08-18 已按人工反馈补齐全覆盖批注，当前批注记录为
  `coverage_completed_pending_manual_recheck`；
- 已完成 protected / slot / remove Truth、样式合同、locator 边界和 validation finding 的人工确认；
- HUNAU/NJAU 的 validation finding 以验收证据记录，PKU 重新按本轮 Gold 接受，不继承历史 r02 signoff。

## 下一步证据

1. 将三校 accepted case 纳入后续 CI/case inventory。
2. 为每校补齐文字反例、字段反例等正式回归。
3. 再讨论是否升级为产品质量门。

## 不属于本 Eval

- 不评估 Agent 轨迹、模型选择、运行耗时或 Tool 调用策略。
- 不证明 Student Content Extraction、Placement、Filling 或端到端 M3 已通过。
- 不把 Gold 或评分答案暴露给 `prepare-template` 运行时。
