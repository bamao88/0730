# Eval

`evals/` 保存离线评测资产，不进入正常用户请求的运行路径：

- `fixtures/`：合成、脱敏或获授权的输入；
- `skills/`：Skill 行为评测；
- `e2e/`：从用户任务到最终产物的端到端评测。
- `manual/`：Adobe 交付高风险页面人工复核清单。
- `template-extraction/`：与产品代码、依赖和 CLI 解耦的模板提取静态 Actual—Gold Eval；
  当前 W0–W5 独立评分链路、全文责任补集比较和 132 个模块测试已实现，三校数据仍为待
  Human 验收的 `candidate`；比较器会拒绝正式评分，不能计入 Gold 通过率。

`uv run docfit eval --suite core` 运行不调用模型或 Adobe API 的确定性核心回归；它会明确
把真实 SDK、Adobe candidate、授权/脱敏真实样本和人工复核保留为独立门，而不会用
OfficeCLI 近似预览替代这些证据。

当前开发范围在 M2 产品链路处完成。该 core runner 与现有 fixture 继续保留为可选
开发资产；M3 Skill/E2E Eval 扩展、Gold、真实样本资格验证和人工复核已延期，需新的
用户批准计划，不作为当前完成门。

不在这里保存真实学生隐私、模型隐藏思维链、运行时 checkpoint 或 replay 数据。
授权真实样本的 PDF、逐页图片、anchor map、Agent review 和人工签字记录保留在仓库外或
被忽略的授权任务目录；仓库只记录去正文的 PASS/FAIL/UNKNOWN 汇总。
