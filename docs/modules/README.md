# DocFit 模块上下文路由

状态: 当前模块上下文路由
更新日期: 2026-08-18

DocFit 有三个并行推进的产品模块。始终先读根目录 `README.md`、`STATUS.md`、
`ARCHITECTURE.md` 和 `AGENTS.md`，然后选择当前实际要改的模块行。

默认不要加载所有模块状态文件。长 status capsule、计划和 human note 是证据，不是启动上下文。

| 模块 | 适用场景 | 继续读取 | 默认排除 |
| --- | --- | --- | --- |
| 模板提取 | 准备学校模板或 Fill Contract | [template-extraction.md](template-extraction.md)、[../contracts/template-extraction.md](../contracts/template-extraction.md)；测试/验证任务读 [../../tests/README.md](../../tests/README.md)；阶段 replay 读 [../../evals/template-extraction/stage-replay.md](../../evals/template-extraction/stage-replay.md)；只有对已生成 Actual 产物离线评分时才读 [../../evals/template-extraction/README.md](../../evals/template-extraction/README.md) | 学生 DOCX、Student Content Model、最终 Word 候选、runtime 完成前的 Template Eval Gold |
| 用户内容提取 | 从学生源论文中提取学生内容 | [student-content-extraction.md](student-content-extraction.md)、[../../evals/student-content-extraction/README.md](../../evals/student-content-extraction/README.md)，必要时读取 student-content Gold/Eval 状态 | 学校模板、Fill Contract、目标 placement、目标样式 |
| final word 生成 / Final Content Fill | 把模板产物和学生内容合成为一份 Word 文档 | [final-word-generation.md](final-word-generation.md)、[../status/active/docfit-field-style-property-closure.md](../status/active/docfit-field-style-property-closure.md)、[../status/active/docfit-stable-style-contract.md](../status/active/docfit-stable-style-contract.md)、[../../evals/e2e/README.md](../../evals/e2e/README.md) | 模板提取内部实现、用户内容提取内部实现、runtime 完成前的 Eval Gold |

共享参考只在当前模块确实需要时读取：

- Field Registry：[../plans/docfit-content-field-registry/DESIGN.md](../plans/docfit-content-field-registry/DESIGN.md)
- 测试与证据：[../../tests/README.md](../../tests/README.md)
- Gold 系统：[../docfit-03-gold-system-design.md](../docfit-03-gold-system-design.md)
- human/background note：[../human/README.md](../human/README.md)
