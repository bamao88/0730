# DocFit 学校模板提取状态

状态: 当前短指针
更新日期: 2026-09-22
Contract 文件: `docs/contracts/template-extraction.md`
模块边界: `docs/modules/template-extraction.md`
Runtime manifest: `main_agent_full_context/v1`

本文只保留模板提取的短状态指针，避免旧阶段计划污染 Agent 启动上下文。长期架构以根目录
`ARCHITECTURE.md`、Contract 和模块边界为准；历史计划和详细索引只作为按需入口或证据。

## 当前状态

模板提取的产品边界保持不变：

```text
学校模板 + 可选学校要求 + Field Registry
        -> docfit prepare-template
        -> output/final-template.docx + output/fill-contract.yaml
```

当前 live-at-HEAD 方向是 Agent-native + Harness-controlled：

- 主 Agent 保留完整任务目标并做学校语义判断；
- Harness 管理任务上下文、Tool 执行、schema/reading-block coverage/权限/路径/发布校验和结构化反馈；
- 反馈回到同一个 SDK Agent loop / session；
- 旧 subagent `scoped_closure_v1` / `coverage_closure` 对象覆盖协议已退役；post-unit 只接受当前
  `source_entry_id + ordered parts + field_id_vocabulary`，覆盖、冲突和 span/slot provenance 由 Harness 闭合；
- DOCX 和学校要求文本全部作为不可信数据处理；
- post-unit Agent-visible Tool surface 只保留 `docfit_evidence` 的模板语义 profile；机械 check/apply
  属于 Harness/App 内部执行面；
- 成功发布只产生 `final-template.docx` 与 `fill-contract.yaml` 两份主交付物。

2026-09-22：当前任务为全流程对象身份统一，从首次功能区判断前建立清单，到实际写入、恢复与
发布保持同一源对象及范围。身份专项工程验收 **ACCEPTED**：真实写入/恢复、失败逐项身份审计及
测试构造跨区边界后的实际写入核验已完成；最后一项不是新 Agent E2E。
见[专项证据](template-full-flow-object-identity-20260922.md)与
[当前唯一计划](../../plans/template-field-id-vocabulary-boundary-refactor.md)。
本任务不纳入学校语义和版式的全面产品验收。2026-09-11 的封面结果仅为历史后半段证据。

## 证据

当前长期证据入口：

- Contract: `docs/contracts/template-extraction.md`
- 模块边界: `docs/modules/template-extraction.md`
- 模块流程: `docs/modules/template-extraction.md`
- 阶段 replay: `evals/template-extraction/stage-replay.md`
- final offline Eval: `evals/template-extraction/README.md`

旧 redesign 分模块 proof 已迁移到上述当前入口和测试资产；不要再把旧 plan/status 当成 Agent
默认上下文或当前执行规则。

## 待确认

真实 Agent / 真实学校模板链路仍应按当前 bug、Eval 和 live run evidence 单独确认。若存在
`docs/bugs/**` 中的当前阻断项，先以 bug 文档和最新复验结果为准，不要把本短状态当作 live E2E
全部通过证明。

## 不属于本模块

- 不读取学生论文或 Student Content Model；
- 不执行 Student Content -> Template placement；
- 不选择最终填写时的通用兜底样式；
- 不生成最终论文 Word；
- 不把 Eval Gold 注入 Agent prompt。
