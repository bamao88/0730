# Bug：段落清理被错误判定为修改受保护内容

- Status: `OPEN / CONFIRMED`
- Severity: `P1`
- Discovered: `2026-08-07`
- Subsystem: `docfit.template.mutation`
- Error code: `protected_content_changed`
- Affected operation: `remove_content / clear_text_preserve_container`

## 1. 摘要

当 mutation plan 明确要求清空整个 paragraph 时，Tool 会在临时 DOCX 中正确清空该段落下的
所有可见文字，但后置保护检查只把 paragraph 对象本身视为允许变化的 target，没有把它下面的
run 对象纳入允许变化范围。

检查器随后发现这些 run 的文字发生变化，将预期变化误判为非目标内容变化，抛出
`protected_content_changed`，并丢弃本次 mutation 的全部临时结果。

这会阻止 Agent 使用段落级清理能力删除模板中的说明文字、示例正文和其他明确授权删除的内容。

## 2. 用户影响

真实南农模板运行中，Agent 曾尝试：

- `18` 个 `materialize_slot` + `79` 个清理操作；
- `18` 个 `materialize_slot` + `67` 个清理操作；
- `67` 个独立清理操作；
- 单段落、单内容控件和多个段落 run 的缩小实验。

段落级和内容控件级清理多次因 `protected_content_changed` 被回滚。Agent 最终退回只包含
`materialize_slot` 的版本，导致交付 DOCX 的可见文字与原模板完全相同，说明文字和示例内容均未
清除。

run 级清理实验可以成功，进一步证明失败集中在“paragraph target 与其 descendant runs 的允许
变化范围”上，而不是所有文字清理都不可用。

## 3. 确定性复现

### 3.1 前置结构

一个 paragraph 在 snapshot 中同时表示为：

```text
paragraph P
├── run R1
├── run R2
└── run R3
```

mutation operation 的 `execution_locator.object_id` 指向 `paragraph P`，operation 为：

```yaml
operation: remove_content
mode: clear_text_preserve_container
execution_locator:
  object_id: <paragraph-P-object-id>
expected_after:
  visible_text: ""
```

### 3.2 实际执行

1. `mutation_package._remove_content()` 遍历 paragraph 下的全部 `w:t`。
2. R1、R2、R3 的文字被正确清空。
3. `_verify_after()` 的 `target_ids` 只包含 paragraph P 的 object ID。
4. 检查器跳过 paragraph P，却继续逐个检查 R1、R2、R3。
5. 因为 R1、R2、R3 不在 `target_ids` 且文字已经变化，检查器抛出：

```text
protected_content_changed: A non-target paragraph changed during mutation.
```

错误信息中的 `paragraph` 也不够准确；实际触发比较的对象可能是目标 paragraph 下的 run。

## 4. 根因

相关实现：

- `src/docfit/template/mutation_package.py::_remove_content`
- `src/docfit/template/mutation.py::_verify_after`

`_verify_after()` 当前使用 operation 显式引用的 object ID 建立 `target_ids`。它虽然计算了
`target_paragraphs`，但只对 paragraph 对象本身做特殊处理，没有建立“目标对象的允许后代集合”。

因此当前保护模型实际是：

```text
允许变化：paragraph P
错误地视为受保护：P 下的 R1、R2、R3
```

正确模型应根据 target kind 计算允许变化范围：

- paragraph target：允许该 paragraph 内的目标文字节点及其 descendant runs 发生计划内变化；
- run target：只允许该 run 变化，同段其他 runs 仍受保护；
- content-control target：只允许对应 content control 内部发生计划内变化；
- 其他 paragraphs、兄弟 runs、styles、sections、表格和外部容器继续保持受保护。

## 5. 事务与回滚行为

当前回滚行为本身符合安全设计。

mutation 不直接修改输入 DOCX，而是：

1. 创建临时 DOCX；
2. 在临时 DOCX 中执行当前 plan 的全部 operations；
3. 运行 package、内容保护、marker、style 和 section 后置检查；
4. 全部通过后才原子发布新的 `work/attempts/*.docx`。

本 Bug 触发后：

- 临时 DOCX 被删除；
- 当前 plan 不发布目标 DOCX；
- 不发布 after snapshot；
- 不发布 mutation evidence；
- 输入 DOCX 保持不变；
- 当前 plan 中已经执行的其他 operations 也全部不提交。

已经由更早 plan 成功发布的 attempt 不会被删除。例如 `slots-only.docx` 会继续存在，失败的后续
cleanup attempt 只是不产生新的子版本。

## 6. 修复方向

建议不要通过关闭保护检查解决，而应显式引入 operation-aware 的允许变化范围：

1. 从 before snapshot 和 OOXML containment 计算每个 operation 的 target closure。
2. paragraph 清理将该 paragraph 的 descendant runs 纳入允许文字变化范围。
3. 允许范围只覆盖 operation 声明的属性变化，不放宽结构、样式、section 或相邻内容保护。
4. 对重叠 operations 做前置规范化或拒绝，避免前序 operation 清空内容后，后序 operation 得到
   `target_not_found`。
5. 失败结果应返回 operation index、operation ID、target kind 和触发保护的实际 object kind，便于
   Agent 缩小范围和返工。

## 7. 回归验收条件

修复至少需要以下测试：

1. **多 run 段落清理成功**：以 paragraph 为 target，三个 runs 的文字清空；paragraph/container、
   styles、sections 保持不变。
2. **同段非目标 run 仍受保护**：以单个 run 为 target 时，其他 runs 的变化必须触发阻断。
3. **相邻段落仍受保护**：目标 paragraph 之外的任何可见文字变化必须触发阻断。
4. **content control 内清理成功**：只清空指定 slot 的可见内容，不修改标签、marker 和外层容器。
5. **混合计划保持原子性**：任一 operation 或后置检查失败时，整个当前 plan 不发布。
6. **重叠目标可诊断**：重叠清理 operation 被前置拒绝，或返回精确失败 operation，而不是模糊的
   `target_not_found`。
7. **真实南农回放**：至少一个此前因 `protected_content_changed` 失败的说明段落可以被安全清理，
   mutation comparison 为预期变化且无 unexpected changes。

## 8. 相关但独立的问题

以下问题与本 Bug 同时影响最终模板质量，但不应混在同一个修复中：

- `materialize_slot` 只包裹现有文字，不生成可见 placeholder；
- Agent 在清理失败后将问题降级为 non-blocking manual/gap；
- 最终视觉 review 允许“已知残留 + accepted”；
- build 未校验 requirements 中 required slots 的完整覆盖；
- SDK transcript 和 Tool 失败 operation 未持久化。

这些问题需要分别建立 Bug 或后续工作项。本文件只跟踪 paragraph/content-control 清理被 descendant
保护模型误判的问题。
