# final word 生成模块

状态: 当前模块边界
更新日期: 2026-08-18
文件合同 CLI: `uv run docfit generate-final`
模块合同：[final-generation.md](../contracts/final-generation.md)
legacy E2E CLI 入口: `uv run docfit convert`
当前 fill 实现: `src/docfit/app/student_content_fill.py`

final word 生成，也称 Final Content Fill，消费模板提取和用户内容提取的输出，生成一份最终
Word 文档。placement、样式选择/物化、内容运输、生成内容刷新和最终质量门都在这里汇合。

当前仓库仍保留 legacy 端到端 Agent 路由（`docfit convert`）以及
`src/docfit/app/student_content_fill.py` 中的独立 debug fill 路径。这些路径是实现或调试面，
不授权在常规模块工作中合并模板提取和用户内容提取上下文。

## 边界

| 允许输入 | 输出 | 禁止事项 |
| --- | --- | --- |
| `final-template.docx`、`fill-contract.yaml`、Student Content Model、Field Registry、已批准任务补充信息 | 候选/最终 Word、placement/fill/style/evidence report | 重新识别学校要求、重新提取学生内容、原地修改源 DOCX 或模板产物 |

当必填学生值缺失、源对象不支持、generated region 未解决、style contract 过期或
renderer/validation evidence 不完整时，本模块可以返回 `PARTIAL`、`NEEDS_INPUT` 或 `ERROR`。

## 数据流

```text
模板产物 + Student Content Model + Registry
  -> Placement Actual
  -> 确定性 template fill
  -> 样式物化与 occurrence audit
  -> 内容审计、render 和 validation
  -> 最终 Word 就绪决策
```

final word 生成按学生源顺序消费 `items[]`。它不得用目标 placement 或正则分类重新解释学生内容。

## 本模块加载范围

- 根状态：`STATUS.md`
- Style closure 状态：
  `docs/status/active/docfit-field-style-property-closure.md`
- Stable style 状态：
  `docs/status/active/docfit-stable-style-contract.md`
- 调试 candidate 质量时读取 Placement/fill debug 状态：
  `docs/status/active/docfit-student-content-placement-debug.md`
- E2E Eval 入口：`evals/e2e/README.md`

只有直接处理 legacy Agent conversion 路由时才读取 `.claude/skills/convert-thesis`。不要用该
Skill 定义模板提取或用户内容提取边界。

## 独立生成与 Eval

`generate-final` 直接消费已提取学生内容和已发布模板包，不调用上游提取 Agent。
模板包须满足当前来源证明和 canonical `slot_ref` 合同；历史只有 `slot_id` 的调试包不能
替代当前已发布模板包。Eval 入口见 [final-generation Eval](../../evals/final-generation/README.md)。
`input,style` 检查只验证基础输入与样式绑定，不证明生成、产物质量或产品验收通过。
