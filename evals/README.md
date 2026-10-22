# Eval 入口

`evals/` 保存离线评测资产，不进入正常用户请求的运行路径：

- `fixtures/`：合成、脱敏或获授权的输入；
- `skills/`：Skill 行为评测；
- `e2e/`：从用户任务到最终产物的端到端评测。
- `final-generation/`：final-generation 输入包与成稿链路的可选调试/回归 case 索引。
- `manual/`：Adobe 交付高风险页面人工复核清单。
- `template-extraction/`：与产品代码、依赖和 CLI 解耦的模板提取静态 Actual—Gold Eval；
  三校 accepted Gold case、合成 evaluator 回归 fixture 和独立评分 CLI 都在该目录内。

如果任务只是验证产品 CLI 能否从输入生成文档，不要进入 `evals/template-extraction/` 寻找输出样例。
生成测试入口见 [../tests/README.md](../tests/README.md)。

`uv run docfit eval --suite core` 运行不调用模型或 Adobe API 的确定性核心回归；它会明确
把真实 SDK、Adobe candidate、授权/脱敏真实样本和人工复核保留为独立门，而不会用
OfficeCLI 近似预览替代这些证据。

模板提取的 Actual-vs-Gold 评分只在产物已生成后运行；合成 S00-S13 fixture 是
evaluator 自身的回归资产，不是产品生成测试的 expected output。

`uv run docfit eval --suite final-generation --list-cases` 列出可选 final-generation
case。后续开发中可用 `student-001-njau-complete-debug --checks input,style` 做快速输入门
检查；需要真实跑候选稿、最终稿、渲染和当前状态断言时，再加 `generate`，并显式传
`--output` 到独立验证目录。带 quality gold 的 release case 默认运行
`input,style,generate,quality`，报告里的 `release_status=PASS` 才表示可发布；
`generate` PASS 不等于 `quality` PASS，也不等于 release PASS。`student-001-njau-known-gap`
只用于验证 intentional `PARTIAL` 降级路径。


不在这里保存真实学生隐私、模型隐藏思维链、运行时 checkpoint 或 replay 数据。
授权真实样本的 PDF、逐页图片、anchor map、Agent review 和人工签字记录保留在仓库外或
被忽略的授权任务目录；仓库只记录去正文的 PASS/FAIL/UNKNOWN 汇总。
