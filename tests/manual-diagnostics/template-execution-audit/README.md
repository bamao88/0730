# 执行范围审计

本脚本为 2026-09-24 的诊断入口，不纳入 pytest。它先使用真实任务的原始判断回放
plan/readiness/目标解析，再用构造 DOCX 运行三个正式物化探针。不运行 Agent，不发布模板，
不读取 Gold，不写原任务。

```sh
PYTHONPATH=. uv run python tests/manual-diagnostics/template-execution-audit/audit.py \
  --task temp/harness-repair-20260923/phase5-three-schools/njau-boundary-diagnostics-task \
  --output temp/template-execution-audit-NEW
```

输出目录必须不存在。真实任务须保有初始绑定、分区、原输入、Registry、inventory、review 和失败回执。
缺文件或绑定失败时停止，不能造旧证据。此旧任务缺当前新增的结构关系上下文；诊断直接进入确定性
检查，不表示当前公开 CLI 可以恢复它。后续 live 验证须重新准备任务。

- `audit.json.real_task`：real replay，三组真实冲突、执行目标与反馈投影；没有原学校实际删除。
- `fixed/`：构造 fixed/cleanup 文字加两个独立保留图形，观察局部清理是否伤及同段对象。
- `slot/`：同样对象，文字建立填写槽，观察同一共享重写路径。
- `manual/`：构造 manual/cleanup 组合，观察清理是否实际执行。

三个 DOCX 都是诊断件。成功运行脚本仅表示诊断完成，不能把 `result_status=ok` 当作正确结果。
基线 `1924c15` 上 fixed/slot 各从 2 个保留图形变为 0，manual 保留了应删除文字；检查回执与输出
XML 的差异，不能只统计 return code。修复时把这些性质提升为稳定 contract 测试。

此脚本复用测试 fixture 构造代码；这部分属于 logic/contract，不是学校真实 replay。
本轮结果目录为 `temp/template-execution-audit-20260924-final/`，详细结论见
[问题记录](../../../docs/bugs/template-execution-scope-audit-20260924.md)。

## E1 修复后真实回放

`e1_replay.py` 使用原 task 的全部 accepted judgments 运行正式物化入口，核验初始绑定，并确认原输入、
清单、分区与判断 hash 不变。它不调用 Agent、不发布，也不自动绕过 readiness。

```sh
uv run python tests/manual-diagnostics/template-execution-audit/e1_replay.py \
  --task temp/full-flow-id-20260922/njau-cover-live \
  --output temp/e1-scope-repair-20260924/njau-cover-final
```

输出 `candidate.docx`、`materialization.json` 和带输入 hash 的 `replay.json`；
已有输出目录应换新路径，保留历史证据。构造回归已提升到
`tests/contract/test_materialization_effect_closure.py`，其故障注入仍只属 logic/contract。

## E2 原图片执行切片

```sh
uv run python tests/manual-diagnostics/template-execution-audit/e2_replay.py \
  --task temp/harness-repair-20260923/phase5-three-schools/njau-boundary-diagnostics-task \
  --output temp/e2-scope-repair-20260926/njau-pictures
```

输出目录必须不存在且位于原任务之外。使用两张图片的原 accepted judgments，只执行对象删除原语；
独立预期仅移除各自 run 的唯一 drawing，比较整棵 Word 树并重读候选包。原完整 review 的 blocker
完整保存在结果中，不能把这个切片当作整校物化或 Agent 修订通过。`audit.py` 同时识别旧执行冲突与
新语义冲突码；基线报告不覆盖，E3 去重修复仍单独验证。

2026-09-26 范围授权修复后，这个切片及 `template-harness-repair/body_interface_replay.py`、
`nested_body_replay.py` 均从选中判断的原 spans 构造 `AcceptedEffects`，执行后核验原授权、重读写包，
并保留原有独立 XML/段落/拓扑检查。选中判断和原文件不改写，完整 review 的 blocker 不移除；
`accepted_scope_verified` 仅指所选执行切片，不表示完整 Agent 流程通过。

## 2026-09-27 承载结构归因对照

```sh
PYTHONPATH=. uv run python tests/manual-diagnostics/template-execution-audit/carrier_diagnosis.py \
  --output temp/scope-cause-audit-NEW
```

使用五种 Word 承载结构、四种已表达用途及两组文字构造 40 组对照；保持角色、字段与语义分段要求，
比较原范围映射、readiness 与实际执行结果。成功候选重读检查文字和字段标识，失败不应写出候选。
输出每例原输入、inventory、review、汇总 `diagnosis.json` 和单页 `flow.html`，输出目录须不存在。
`flow.html` 按输入、语义判断、范围解析、编译、执行前检查、Tool 操作和 DOCX 结果纵向展示；
选择案例可切换承载结构与用途，Tool 步骤可切换范围授权和 Word 操作视角。页面中的
控件分派说明标为代码路径推断，失败与成功状态来自本次诊断运行；不将构造判断表述为 Agent 输出。
这属于 logic/contract，不是学校真实 replay、实际填写或视觉验收。基线结果是 40 组映射/就绪通过，
20 组实际成功、20 组因嵌套文字能力缺失失败；脚本完成不等于产品完成。用于检验归因和后续正向能力。

2026-09-28 正向修复后同一脚本 40/40 组成功，重读候选检查字段、文字和保留范围；
`temp/flow-diagnosis-after-edit-20260928/flow.html` 是修复后页面，基线页面保留在
`temp/flow-diagnosis-20260928/flow.html`。两者均是构造 `logic/contract` 对照。
