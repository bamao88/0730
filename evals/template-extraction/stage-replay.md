# 模板提取阶段 Replay

本文应该回答：

- 模板提取阶段 replay 与最终 Actual-vs-Gold Eval 有什么区别；
- HUNAU、PKU、NJAU 这类真实学校输入应该怎样作为可复现 replay case；
- 单元阶段 proof 应该记录哪些输入、输出、断言和失败归因；
- replay 测试、fixture、reference proof 和 CI gate 应放在哪里；
- 为什么 replay 不能把 Gold 答案注入 Agent runtime。

状态: 设计目标
模块: 模板提取
测试入口: [../../tests/README.md](../../tests/README.md)
模块流程: [../../docs/modules/template-extraction.md](../../docs/modules/template-extraction.md)

## Replay 与 Eval

阶段 replay 是开发反馈环，不是最终质量评分。

Replay 回答：

```text
同一个真实输入、同一个 checkpoint、同一类 Agent-style payload，
当前 Tool/Harness/runtime 是否仍能产出可消费 proof？
```

Eval 回答：

```text
已经生成的 final-template.docx 和 fill-contract.yaml，
与 accepted Gold 相比质量如何？
```

因此 replay 可以使用 reference proof、期望 unit 数量、unit 名称和边界证据来判断阶段是否闭合；
但不能在 Agent runtime 中读取 Gold Word、Gold contract 或最终 accepted answer。

## 标准输入

模板提取阶段 replay 应优先覆盖三校真实输入：

- HUNAU undergraduate；
- NJAU undergraduate；
- PKU graduate。

每个 case 需要记录：

- 原始学校模板 DOCX；
- 可选学校要求文件；
- `source_hash`；
- `render_ref` 或可重建 render 的配置；
- 页数；
- 单元阶段 reference payload；
- 当前代码生成的 proof；
- 失败时的 Tool/Harness feedback。

这些材料可以放在 `temp/**` 作为一次性调试产物；进入 CI 或长期 replay 后，需要提升到稳定 fixture
或 manifest。长期 fixture 不应依赖某轮临时 run 目录。

## 单元阶段 Replay

单元阶段 replay 从初始完整源对象清单开始，提交已有对象上的边界。视觉、页码和文本提供语义
证据，不是另一套定位。下列 ID 是形状示意；实际 replay 必须从该输入的初始清单读取真实 ID：

```yaml
units:
  - unit_id: cover
    unit_name: 封面
    start_boundary:
      source_entry_id: source-entry-from-initial-inventory
      edge: start
    end_boundary:
      source_entry_id: source-entry-at-cover-end
      edge: end
```

对象内边界使用 `edge: split`，`before` / `after` 两段精确原文拼接必须等于该对象全文。
Harness 计算 offsets。起点包含、终点不包含；同一个对象跨区不重新编号。
测试必须证明分区前后、分页/重试及后续写入引用同一身份。旧页码/seen_text payload 和 locator
直传只作为拒绝测试；不得将历史 proof 自动转换后算作新合同从头跑通。

## Reference Proof

reference proof 不是 Gold final template。它只用于阶段 replay。

单元阶段 reference proof 可以断言：

- `checkpoint == unit-boundary`；
- `status == ok`；
- `source_hash` 匹配；
- `unit_count` 匹配；
- `unit_id` 和 `unit_name` 集合匹配；
- proof 绑定第一次判断前建立的完整 inventory；
- 每个 unit 的源对象 start/end boundary 存在；
- 重解 exact source spans 与 proof 一致，并能沿同一映射解析 Word fragments；
- coverage missing/overlap 为空。

如果要评估单元语义质量，可以离线比较 actual proof 与 accepted reference proof；这仍然属于 replay/eval
层，不能变成运行时 prompt 答案。

## 建议测试位置

工程测试建议放在主测试树：

```text
tests/integration/test_template_extraction_unit_boundary_replay.py
```

它应该做最小闭环：

```text
真实输入 -> 初始完整 inventory + 页面线索 -> 源对象边界 payload -> unit_coverage -> proof ok
```

质量评估和三校 reference proof 可以放在 Eval 目录：

```text
evals/template-extraction/stage-replay/
  cases/
  references/
  reports/
```

如果该目录未来落地，需要在 `evals/template-extraction/README.md` 中链接，并说明它不同于
`run_eval.py` 的 final Actual-vs-Gold 评分。

## CI Gate

CI 中的 replay gate 应该快、确定、可归因。建议分层：

- contract tests：覆盖 稳定 ID、对象内部切点、重复文本、分区 coverage、schema、fail-closed；
- integration replay：三校真实输入只跑到 unit-boundary；
- optional eval：只在 actual 产物生成后跑 final Actual-vs-Gold。

当 replay 失败时，报告必须说清楚失败层：

- input/hash/render 失败；
- Agent-style source-entry boundary payload 无法解析；
- Harness source-span resolver 或 Tool Word fragment 映射失败；
- Harness coverage missing/overlap；
- proof schema 或 runtime resume 校验失败。

不要把 replay 失败直接解释成最终模板质量问题。

## 维护规则

- replay reference 更新必须说明原因：学校输入变化、schema 变化、Tool resolver 修复、Harness coverage
  修复，还是语义 reference 调整；
- 更新 reference proof 前应保留旧失败结果和新通过结果；
- synthetic/smoke 只能覆盖最小机制，不得冒充三校真实验证；
- Gold 只能用于离线评分或人工 review，不能作为 runtime oracle；
- 后续字段、样式、Registry 或 apply 阶段 replay 应从已接受的 unit proof 继续，不重新拆单元。
