# Post-unit Registry Field Affordance 错误记录

日期: 2026-08-21
范围: 模板提取模块 unit-boundary 之后的 post-unit 语义判断流程
状态: human-facing 复盘记录；不是默认 Agent 操作规则

## 发生了什么

在 `02-integrity-statement` 最小单元的真实 post-unit flow 测试中，Agent 的第一步是正确的：

```json
{"schema_version": "docfit_evidence_input_v1", "focus": "unit_evidence_packet", "unit_id": "u-integrity-statement"}
```

这说明前一轮 Skill/prompt 收敛后，Agent 没有先跳到 render、visual review 或 reviewed_pages，而是从单元证据包进入语义判断。

但随后 Agent 连续调用了三次：

```json
{"schema_version": "docfit_evidence_input_v1", "focus": "registry_field"}
```

这些调用没有 `field_id`，也没有 `query`。Tool 仍返回 `status=ok`，并给出较宽的 Registry 字段列表。

## 错误归因

表面看是 Agent 太早查 Registry，或者没有带查询参数。但更准确的归因是 Tool affordance 过宽。

在当前 post-unit 合同里，Agent 应先判断对象是什么，再判断干净模板里怎么处理。只有当对象被判断为字段槽，才需要查询 Registry。也就是说 Registry evidence 是条件依赖，不是每个对象默认都该拿到的背景材料。

但 Tool 接口允许这种无条件调用：

```json
{"focus": "registry_field"}
```

并且无参数时返回全量 Registry 候选。这等于把“是否需要 Registry”这个机械流程约束重新压回 Agent，让它自己克制不要提前查。这个设计不符合项目边界：Agent 负责学校语义判断，Harness/Tool 负责把可用证据入口约束成正确阶段。

## 具体问题

1. `registry_field` 无 `field_id/query` 仍返回成功。
   这会鼓励 Agent 在还没有字段槽判断时翻 Registry。

2. 返回内容太宽。
   全量 Registry 让 Agent 从“判断对象语义”转向“在一堆字段里匹配”，增加耗时和跑偏概率。

3. `unit_evidence_packet` 信息也偏重。
   实测一个 10 对象诚信声明单元返回约 53KB，包含完整 `object_ref`、`target_ref` 和大量 format。post-unit 语义判断阶段不应该默认暴露写入 handle；写入 handle 应在 Harness review 通过后的执行阶段再进入。

## 正确设计方向

`registry_field` 可以继续作为 `docfit_evidence` 的一个 focus，因为它本质是只读证据，不是执行或检查。但它必须变窄：

```json
{"focus": "registry_field", "query": "作者签名"}
{"focus": "registry_field", "field_id": "author.name.zh"}
```

如果 Agent 只传：

```json
{"focus": "registry_field"}
```

Tool 应返回可修复 feedback，而不是返回全量 Registry：

```text
registry_field requires field_id or query.
Only request Registry evidence after judging the object as a field slot.
For keep/delete/no-op judgments, return semantic_judgments without Registry evidence.
```

`unit_evidence_packet` 也应该区分阶段视图：

- 语义判断视图：object id、locator、type、text、必要 style summary、邻近关系、风险提示。
- 执行视图：target_ref、fresh object_ref、candidate hash、写入 affordance。

默认 post-unit 入口应给语义判断视图，不应默认把执行视图混进来。

## 以后怎么避免

流程测试不能只看 Agent 最终是否失败，也要看 Tool 调用序列和 Tool 返回内容：

1. 第一调用是否是 `unit_evidence_packet`。
2. 是否在字段槽判断前提前查 Registry。
3. `registry_field` 是否带 `field_id/query`。
4. Harness review 前是否出现 `docfit_apply`、render、visual review 或 reviewed_pages。
5. Evidence packet 是否把执行阶段 handle 提前暴露给语义阶段。

遇到这类问题时，优先检查 Tool/Harness 的 affordance，而不是继续给 Skill 加规则。Skill 只能表达阶段语义；Tool 接口必须让错误路径不容易发生。
