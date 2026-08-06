---
name: docfit-school-extract
description: 整理学校论文模板和书面要求，生成干净模板、Registry 对齐的填写契约、视觉审查与构建报告。
---

# 学校模板整理

把用户提供的学校模板、文字要求、官方示例和确认信息整理为开发期模板产物：

```text
template-artifact/
├── clean-template.docx
├── fill-contract.json
├── visual-review.json
└── build-report.json
```

只有 `template_build` 返回 `call_status: ok`、`artifact_status: built`、`published: true`，且你已
检查最终结构、页面和用户目标，才可以交付该目录。`built` 只表示本次开发期产物完整且机械
有效，不表示模板已经定版、Human accepted、通过正式质量 Eval 或达到 M3。

## 结果责任

你是任务和最终结果的 owner。你负责判断：

- 哪份材料对哪个范围有效；
- 哪些内容是学校 protected 内容、自动 slot、应删除内容或人工区域；
- 每个自动 slot 对应哪个 Registry `field_id`；
- 来源/样式冲突如何处理；
- 删除前内容责任如何迁移或是否已有明确授权；
- Tool 返回的结构/视觉证据是否符合用户目标；
- 何时返工、何时询问用户、何时报告真实阻断。

Tool 负责确定性 DOCX 事实、受控修改、比较和原子构建。compiler 只校验并规范化你的决定。
任何 Tool/compiler 成功都不能替代你的结果检查。

## 推荐方法

1. 确认当前 task root、只读输入、Registry 文件和输出目录。不要修改原始模板、要求、示例或
   Registry。
2. 读取 Registry ID/version/hash，理解可用 `field_id`、类型、字段基数和 value source。
3. 调用 `template_observe.create` 建立结构 snapshot；根据任务需要选择 structure、visible
   objects、styles 和 slot candidates。
4. 需要定位文字或对象时使用 `template_observe.query`。保留全部匹配；不要凭页码、段落序号
   或相似文字静默选一个。
5. 用 `quick` 页面证据检查复杂结构或修改范围。图片通过 `template_observe.images` 分批读取。
6. 区分四类身份：Registry `field_id`、模板 `slot_id/region_id`、task-local execution locator、
   最终 artifact locator。不要把它们互相替代。
7. 把需要修改的语义判断、字段、授权和目标写入新的 `mutation-decisions.yaml`，运行
   `scripts/compile_mutation_plan.py`。
8. 把 canonical mutation plan 交给 `template_mutate`。目标失效或歧义时重新 observe 和编译；
   不手改 compiled JSON。
9. 调用 `template_compare.create` 的 `mutation_review`，检查预期变化、意外变化和 required
   images。发现误伤或目标未发生时返工并使用新的 output 路径。
10. 修改完成后，对当前最终 snapshot 调用 `template_compare.create` 的 `final_review`，使用
    `candidate_verification` 覆盖最终 hash 的全部页面。通过 `template_compare.images` 实际查看
    每一张 required image，并记录 disposition/finding。
11. 把最终 Registry、sources、protected/slot/remove、样式、manual/gap/unresolved、mutation
    lineage 和 final review 写入新的 `artifact-decisions.yaml`，运行
    `scripts/compile_artifact_spec.py`。
12. 把 artifact spec 交给 `template_build`。根据 findings 回到对应的观察、字段、修改、比较或
    决定环节修正；成功后重查四文件目录和 structured output。

零 mutation 模板仍必须执行最终全页 review、artifact compile 和 build。局部修改成功、quick
预览或 compiler success 都不能替代最终构建检查。

## Registry、字段和槽位

自动 slot 必须同时满足：

- `field_id` 存在于本次绑定的 Registry；
- content type 与 Registry 兼容；
- `slot_id` 在当前模板中唯一；
- content control 使用 `w:alias = field_id`、`w:tag = slot_id`；
- 有唯一、持久且绑定最终模板 hash 的 artifact locator；
- required、cardinality 和 expected value style 明确。

`field_id` 只表示语义，不是 DOCX locator 或写入授权。未注册字段不得猜测；把它登记为
manual/gap/unresolved。若它是本次必须自动填写的字段，向用户说明阻断或请求先扩展 Registry。

execution locator 只在当前 task snapshot 中用于 Tool 执行。最终填写契约不能依赖 snapshot ref、
临时 object ID、单一页码或未约束的段落序号。

## 删除与责任迁移

`materialize_slot` 只物化 content control，不插入可见占位文字，也不自动清空示例内容。清理
示例或说明时必须使用独立 `remove_content` operation。

删除前必须满足至少一个条件：

- 被删内容承载的责任已经迁移到已物化 slot 或 protected target；
- 当前用户指令或本次提供的书面要求明确授权删除，并记录精确授权摘要/hash。

不要用长期文档、最终目标描述或“看起来像说明”替代删除授权。删除范围歧义、可能吞入学校
固定内容或影响 section/table/shape 边界时停止并询问。

## 样式与来源冲突

区分：Tool 观测的有效值、当前材料声明的要求值、来源、适用范围和冲突状态。不要用经验或
常识补缺失样式。

当模板、书面要求和官方示例冲突时：

1. 先确认是否适用于同一对象和范围；
2. 保留各自 source/hash；
3. 根据当前用户指令和任务材料裁决；
4. 无法裁决时登记 gap/unresolved 或询问用户；
5. 不把冲突静默压成一个值。

## 视觉证据

- `quick` 用于返工定位；
- `candidate_verification` 用于最终候选全页证据；
- 它们是固定渲染路由，不是模板质量认证。

`template_compare` 只报告结构差异和 required images，不判断图片是否正确。你必须实际查看图片，
检查截断、重叠、空白异常、字体/对齐错误、断裂字段、错误分页、残留说明、图片/表格/公式异常
等，并为每张 required image 和 finding 写 disposition。

如果最终图片暴露问题，即使 Tool 的其他机械检查通过，也继续返工，不能交付已知错误产物。

## 失败后继续修正

- compiler 拒绝：修正决定文件、Registry/field、引用、授权或 review；使用新的 output JSON。
- mutate 拒绝 stale/ambiguous ref：重新 observe，缩小目标，重新编译；使用新的 DOCX 路径。
- mutate post-check 失败：不要消费 output/ref；检查 operation 范围和保护不变量。
- compare 出现 unexpected change 或缺 evidence：返工或扩大审查，不接受旧 hash 证据。
- build 返回 blocked：根据 finding 回到 Registry、marker、locator、protected/remove、lineage 或
  review；修正后使用新的 output directory。
- 同一后端错误没有新证据时不要循环重试。

不要覆盖旧 attempt，也不要混用不同 hash 的 snapshot、mutation、comparison、图片或决定。

## 询问用户

缺少会改变删除范围、字段映射、来源优先级或最终结果的必要裁决时，使用 SDK 原生
`AskUserQuestion`/`can_use_tool` 并等待答案。不要创建 question file、pause status、session
registry 或自定义多轮协议。

用户拒绝授权或无法提供必要事实时返回真实 `blocked`，不得通过猜测得到 built。

## 两个 compiler

| 脚本 | 决定输入 | canonical 输出 | 下游 |
|---|---|---|---|
| `compile_mutation_plan.py` | snapshot、Registry、责任、字段、授权、operations | `mutation-plan.json` | `template_mutate` |
| `compile_artifact_spec.py` | final snapshot、Registry、sources、protected/slot/remove、style、manual/gap/unresolved、lineage、review | `artifact-spec.json` | `template_build` |

调用形态：

```text
uv run python <skill-root>/scripts/<script>.py \
  --task-root <task-root> --input <decision.yaml> --output <new-output.json>
```

脚本只允许 task root `work/` 内路径，不覆盖已有输出。编译错误是返工输入，不是任务终点。

## 按需读取 references

- 语义、protected/slot/remove/manual/gap：`references/template-semantics.md`
- 删除授权和槽位物化：`references/deletion-and-slot-decisions.md`
- 来源和样式冲突：`references/style-reconciliation.md`
- 结构/视觉回归：`references/visual-regression.md`
- 两份决定和 compiler 使用：`references/decision-compilation.md`

只在相关问题出现时读取对应 reference，不一次加载全部内容。

## 完成与回复

最终 structured output 必须与磁盘事实一致：

```yaml
status: built | blocked
artifact_path: <path> | null
template_sha256: <sha256> | null
fill_contract_sha256: <sha256> | null
counts:
  slot: 0
  protected: 0
  remove: 0
  manual: 0
  gap: 0
  unresolved: 0
```

成功回复说明四文件路径、模板/contract hash、结构化数量和仍需人工/质量验证的限制。blocked
回复说明可定位的阻断与所需输入，不伪造产物路径或 hash，也不声称模板已经定版。
