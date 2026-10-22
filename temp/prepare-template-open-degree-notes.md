# Prepare Template 代码层开放度说明

本文记录临时对话中对 `src/docfit/app/prepare_template.py` 入口 prompt 开放度的理解，供后续讨论
Skill 和应用边界时参考。

## 核心判断

当前问题不是“让 Agent 自主”本身，而是代码没有区分：

```text
Agent 可以自主决定怎么理解学校模板；
Agent 不应该自主决定什么算最终交付闭合。
```

更准确的边界应该是：

```text
语义路线开放；
机械闭环不开放。
```

## 好的开放度

代码不应该替 Agent 做学校语义判断。例如：

- 哪段是学校固定文字；
- 哪段是说明文字；
- 哪个表格是学生填写区；
- 哪个标题属于正文层级；
- 哪些页面构成一个逻辑单元；
- 什么时候需要跨页比较或视觉确认。

这些判断依赖学校材料、上下文、视觉证据和 Registry meaning，应该由 Agent 在 Skill/reference 指导下完成。

## 当前过度开放的位置

`src/docfit/app/prepare_template.py` 的入口 prompt 大意是：

```text
Prepare one clean... own the result end to end.
decide your own inspection order, visual checks, batching, retries...
Before completion, render..., visually review..., call docx_validate...
Return complete only with...
```

这等于应用只给 Agent 一个最终目标、一组工具和输出 schema，然后让 Agent 自己组织完整交付流程。

实际开放度变成：

```text
应用壳：启动一次 Agent、给输入、给工具、给输出 schema；
Agent：自己决定观察、分解、修改、复核、验证、完成判断；
代码：最后再尝试看结果是否能 publish。
```

这个方向是 Agent-native，但自由度放得过宽，因为“交付闭环”也被开放给了 Agent。

## 应该由代码压住的低自由度边界

代码不需要写学校模板状态机，但应该强制客观边界：

- 输入必须复制到 task root，原始样本只读；
- 最终交付只能是 `output/final-template.docx` 和 `output/fill-contract.yaml`；
- Word 读取、修改、渲染、验证只能走 DocFit Tool；
- publish 前必须有同一个 final DOCX hash 绑定的 render、reviewed pages 和 validate；
- `fill-contract.yaml` 必须存在、schema 正确，并绑定 final Word hash；
- 没有 contract、没有完整 final review、没有 validate，就不能被包装成 `complete`；
- 失败时必须留下可判断的 `first_bad_stage` 和 missing evidence，而不是只留下半截 render。

## 失败机制

当代码把语义判断和交付流程设计一起开放给 Agent，而 Skill 又没有充分教它如何走完闭环时，Agent
自然会滑进开放式观察或视觉复核循环。

这解释了之前端到端测试中看到的现象：

- Agent 做了 inspect；
- Agent 做了 render；
- Agent 看了部分页面；
- 但没有稳定进入候选门禁；
- 没有构建并绑定 Fill Contract；
- 没有形成 `final-template.docx + fill-contract.yaml` 的原子发布结果。

因此，问题不是单纯少一个步骤，而是缺少：

```text
候选门禁 -> contract 构建 -> final review -> validate -> publish
```

这条低自由度交付闭环。
