# Final-generation Eval

这个目录只保存 final-generation 调试/回归用例索引。真实运行输入仍放在独立输入包目录，运行输出必须写到单独输出目录。

固定入口：

```bash
uv run docfit eval --suite final-generation --list-cases
uv run docfit eval --suite final-generation --list-combinations
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --checks input,style --json
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --checks input,style,generate --output temp/final-generation-e2e-verify-20260816/eval-complete-debug-001 --json
uv run docfit eval --suite final-generation --case student-001-njau-complete-debug --checks input,style,generate,quality --output temp/final-generation-quality-compare-20260818/eval-complete-debug-quality-001 --json
uv run docfit eval --suite final-generation --student 001 --school njau --checks input,style --output temp/final-generation-regression/student-001-njau-input-style --json
uv run docfit eval --suite final-generation --student 001,002,003 --school njau --checks input,style,generate --output temp/final-generation-regression/three-students-njau-generate --json
uv run docfit eval --suite final-generation --matrix --checks input,style --output temp/final-generation-regression/base-3x3-input-style --json
```

带 `expected.quality.gold_docx` 的 case 是 release 级 case；不显式传 `--checks` 时固定执行
`input,style,generate,quality`。显式传 `--checks input,style,generate` 仍只表示生成流程回归，
报告里的 `check_status` 可以 PASS，但 `release_status` 不能 PASS，`releasable` 必须为 false。

`--checks` 可选值：

- `input`：只校验输入包文件、哈希、schema 和 Registry 绑定。
- `style`：校验模板侧 school style candidate / known gap 事实。
- `generate`：调用 `generate-final` 跑候选稿、渲染和当前预期状态检查。
- `quality`：依赖同一轮 `generate`，把生成 DOCX/PDF 与 case 配置的 gold DOCX 做
  文本、结构、媒体和 LibreOffice 渲染差异检查。对没有 gold 的普通流程回归，这个
  check 只有显式选择时才执行。`generate` PASS 只表示流程和当前状态符合预期，不表示
  成品质量已经达到 gold，也不等于 release PASS。

Eval JSON 顶层同时写出 `check_status`、`generate_status`、`quality_status`、
`release_status` 和 `releasable`。只有 `release_status=PASS` 且 `releasable=true` 时，
这次 `final.docx` 才允许被描述为可发布。

`--case` 入口用于已登记的 debug/release case。`--student/--school/--matrix` 入口用于从
base packages 稳定组合学生论文和学校模板；支持 `001`、`student-001`、`njau`、
`njau-undergraduate` 这类别名。组合入口会在本次 `--output` 下生成临时 input package，
再走同一套 `input/style/generate/quality` 检查。当前 quality gold 只覆盖
`student-001/002/003 x njau-undergraduate`；其他学校组合可以跑生成回归，但没有 quality
gold 时不能作为 release PASS。

对话框交付约定：每次运行 final-generation 端到端测试后，必须在对话框里给出本次 run
产生的 Word 文件链接。`COMPLETE` run 给 `generate-final/final.docx`；`PARTIAL` run 给
`generate-final/candidate.docx`，并明确标注该文件不可发布。即使 release gate 失败，也要
给出 Word 文件供人工查看，但不能描述为可发布成稿。

## Base Packages

基础包只验证输入本身，不生成 `candidate.docx` 或 `final.docx`。后续 AI 需要准备
3 个学生内容包和 3 个学校模板包时，固定使用：

```bash
uv run python evals/final-generation/scripts/base_packages.py --prepare --root temp/final-generation-base-packages-20260816
uv run python evals/final-generation/scripts/base_packages.py --check --runtime-inventory --root temp/final-generation-base-packages-20260816
```

输出目录：

- `temp/final-generation-base-packages-20260816/students/<student-id>/`
- `temp/final-generation-base-packages-20260816/schools/<school-id>/`
- `temp/final-generation-base-packages-20260816/check-report.json`

调用组合时，从一个学生包取 `student.docx` 和 `student-content.json`，从一个学校包取
`final-template.docx` 和 `fill-contract.yaml`，并使用对应包里的 `content-fields.yaml`。
这个层级只检查文件哈希、Registry 绑定、Fill Contract v2 加载、3x3 placement 组合，以及
当前运行态 inventory 的 transport id 是否可用。

注意：3 个学校模板包的 `fill-contract.status` 保持为
`candidate_pending_human_acceptance`。它们是用于基础包和 placement 校验的候选模板包，
不代表模板合同已人工验收。

## Cases

- `student-001-njau-complete-debug`：完整调试 case。补入源文档缺失的封面元数据作为
  `task_input_debug`，contract 状态为 `accepted`，预期 `generate-final` 返回
  `COMPLETE` 并发布 `final.docx`。该 case 额外配置了 NJAU student-001 converted DOCX
  作为 quality gold；默认 release 检查会按 gold 目标阈值检查成品质量。
- `student-001-njau-known-gap`：partial 回归 case。保留未接受 contract、缺失封面字段、
  body style role 和 required generated region 的组合，预期 `generate-final` 返回
  `PARTIAL`。

后续 AI 开发默认使用 `student-001-njau-complete-debug` 做端到端验证；只有在验证 partial
降级路径时才使用 `student-001-njau-known-gap`。
