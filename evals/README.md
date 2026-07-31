# Eval

`evals/` 保存会调用 Agent 的离线评测资产，不进入正常用户请求的运行路径：

- `fixtures/`：合成、脱敏或获授权的输入；
- `skills/`：Skill 行为评测；
- `e2e/`：从用户任务到最终产物的端到端评测。

不在这里保存真实学生隐私、模型隐藏思维链、运行时 checkpoint 或 replay 数据。
