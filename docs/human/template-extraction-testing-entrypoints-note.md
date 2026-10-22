# 模板提取测试入口说明

本文应该回答：

- `tests/README.md` 和 `evals/template-extraction/README.md` 分别是什么入口；
- 做生成测试、阶段 replay、离线 Eval 时应该读哪个文档；
- 为什么“只到单元阶段”的验证不应该进入 final Actual-vs-Gold 评分入口。

状态: human 说明材料
适用范围: 模板提取测试、阶段 replay、final Eval 入口区分

## 两个 README 的边界

`tests/README.md`

这是**测试总入口**。它应该告诉 Agent：

```text
我要验证流程，该从哪里开始？
哪些是生成测试？
哪些是阶段 replay？
哪些是离线 Eval？
哪些输入可以读？
哪些 Gold 不能读？
```

它覆盖整个 DocFit 测试体系，不只模板提取。

`evals/template-extraction/README.md`

这是**模板提取最终质量评分入口**。它只回答：

```text
已经生成了 final-template.docx 和 fill-contract.yaml，
现在怎么拿它们和 accepted Gold 做离线评分？
```

它不应该指导 Agent 怎么跑 `prepare-template`，也不应该作为中间阶段调试入口。

两者关系是：

```text
tests/README.md
  先告诉你：当前是在做生成测试、阶段 replay，还是离线 Eval

evals/template-extraction/README.md
  只有当 tests/README.md 判断“这是已生成产物的离线评分”时才进入
```

如果是“只到单元阶段”的验证，不应该优先读 `evals/template-extraction/README.md`，而应该读：

```text
tests/README.md
evals/template-extraction/stage-replay.md
docs/modules/template-extraction-unit-boundary-checkpoint.md
```

`evals/template-extraction/README.md` 只在 final Actual-vs-Gold 评分时读。
