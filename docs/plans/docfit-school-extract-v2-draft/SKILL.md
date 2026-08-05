---
name: docfit-school-extract
description: 将学校论文 Word 模板整理为冻结且可安全填写的模板产物。当用户提供学校模板、格式要求或官方示例，并希望获得干净的可复用模板及与模板 hash 绑定的槽位 manifest 时，使用本 Skill。
---

# 学校模板提取

将当前任务的学校材料整理为两个核心交付内容：

1. 一份干净的模板 DOCX，保留必需结构、固定内容、样式和 Word 行为；
2. 一份与该模板精确 hash 绑定的冻结产物 manifest，包含自动槽位、人工区域、gap、来源
   和审查发现。

不要填入学生论文内容。不要把学校专属结论提升为产品 Knowledge。

## 结果责任

你是整个任务和最终模板产物的 owner，不只是语义判断者。你需要确定预期结果，判断哪些
材料具有权威性、哪些可见内容是说明或示例、删除前必须保留哪些责任、槽位表示什么，
并检查脚本和 Tool 返回的实际结果。结果错误时，诊断原因，修改决定、操作或候选文档，
重新执行并验证，直到产物正确冻结或出现当前权限和证据下确实无法解决的阻塞。

Skill 内置脚本负责校验并把你已经完成的语义判断编译为规范的 Tool 输入。模板 Tool
负责建立事实、执行显式操作、比较实际变化、编译候选产物和独立冻结。Tool 只证明当前
调用是否符合其确定性合同；它不承担任务结果。脚本或 Tool 返回成功，都不能免除你检查、
修正和交付最终正确产物的责任。

## 推荐方法

根据实际证据调整以下顺序。这是操作方法，不是固定状态机。

1. 盘点所有模板、文字要求和官方示例。记录来源、冲突、缺失输入，以及必须保持只读的
   文件。
2. 调用 `template_observe` 建立不可变快照。观察结构、可见对象、最终有效格式、槽位候选、
   PDF 页面和不支持内容。
3. 将模板内容分类为 fixed、fill、generate、repeat、conditional、manual、remove 或
   unresolved。
4. 删除说明或示例前，先把其中仍需保留的格式、基数、生成或放置责任迁移到槽位或区域
   决定中。
5. 将文字要求与模板最终有效格式交叉验证。保留重要冲突；不要仅凭样式名、历史学校或
   惯例裁决冲突。
6. 为每项修改选择精确目标、预期指纹、删除模式和必要的槽位语义。当歧义会实质改变
   可复用模板时，询问用户。
7. 写入 `mutation-decisions.yaml`，然后运行 `scripts/compile_mutation_plan.py`。把生成的
   `mutation-plan.json` 交给 `template_mutate`。不要单独使用页码或文本作为编辑身份。
   如果编译或修改因为目标过期或歧义而被拒绝，重新观察并重新判断。
8. 调用 `template_compare`。检查它返回的预期变化、意外变化和原生图片，判断结果是否
   合理、是否需要继续修改，或是否需要用户输入。
9. 把图片判断写入 `review-decisions.yaml`，运行 `scripts/compile_review_record.py`。完成
   最终快照全页审查后，使用已确认的语义清单和审查记录运行
   `scripts/compile_artifact_spec.py`。把 `artifact-spec.json` 交给 `template_build`，并且
   只把其输出视为 candidate。
10. 把 candidate 提交给 `template_freeze`。根据 findings 继续修正；只有这个独立 Tool
    返回 `status: frozen`，并且你确认最终结果满足任务语义和视觉要求后，才能交付。

## 核心判断规则

- 说明文字可能承载要求。删除文字前先迁移要求。
- 逻辑单元不等于物理页面。页码是视觉证据，不是持久编辑 locator。
- 样式名不等于最终有效格式。还要考虑直接格式、继承、分节设置和其他适用的 Word 行为。
- 生成对象不等于当前缓存的显示文字。需要时保留生成责任。
- 示例数量不等于重复区域的基数。
- 除非当前任务证据明确授权修改，否则固定内容保持不变。
- 未知或不支持的内容应保留并标为 unresolved；缺少证据不代表允许删除。
- 自动槽位必须能在最终模板快照中唯一定位，否则将区域标为 manual 或 unresolved。
- 修改成功或 build 成功都不代表产物已经冻结。只有 `template_freeze` 可以发布 frozen
  产物。

## 发现错误后继续修正

把脚本和 Tool 返回的问题当作下一步修改依据，而不是任务终点：

- 编译器拒绝 decision file：根据错误补齐或修正语义决定和证据，然后重新编译；不要
  手改规范输出绕过检查。
- `template_mutate` 拒绝 stale/ambiguous ref 或后置检查失败：重新 observe，修正目标、
  fingerprint、删除模式或槽位语义，再生成和执行新的 mutation plan。
- `template_compare` 显示预期变化未发生、出现误伤或视觉结果不合理：不要把 finding
  直接标为 accepted；形成纠正决定，执行新的修改并重新比较。
- `template_build` 拒绝 artifact spec：修正最终语义清单、来源、槽位、manual/gap 或
  review record 后重新 build。
- `template_freeze` 返回 blocking findings：定位到对应的观察、决定、修改、视觉审查或
  artifact 问题，修正后重新 build 和 freeze。即使 freeze 成功，只要你发现语义或视觉
  错误，也不得交付，必须继续修正。

只有缺少必要用户裁决、授权材料或不可替代的外部能力，并且当前范围内没有安全修正路径
时，才报告阻塞。报告时说明已经确认的事实、阻塞原因和解除阻塞所需输入。

## 在调用 Tool 前编译决定

相对于当前 `SKILL.md` 解析 `scripts/` 路径；不要临时重新实现这些编译器。

| 脚本 | Agent 编写的输入 | 规范输出 | 消费方 |
|---|---|---|---|
| `compile_mutation_plan.py` | `mutation-decisions.yaml` | `mutation-plan.json` | `template_mutate` |
| `compile_review_record.py` | compare 结果 + `review-decisions.yaml` | `review-record.json` | artifact 编译与冻结证据 |
| `compile_artifact_spec.py` | 最终语义清单 + review record | `artifact-spec.json` | `template_build` |

先写清语义决定及其证据，再运行脚本；脚本只负责检查和序列化。编译错误表示决定缺失或
互相矛盾，不代表可以弱化 schema。脚本必须原子生成规范输出，不得读取或修改 DOCX、
调用 Tool、推导文档语义，也不得宣称审查或冻结已经通过。Tool 会重新验证每一份编译结果。

准备三份决定文件或解释编译错误前，阅读
[references/decision-compilation.md](references/decision-compilation.md)。

## 谨慎选择删除模式

| 意图 | 模式 |
|---|---|
| 清空占位文字，同时保留段落/run 容器及其格式 | `clear_text_preserve_container` |
| 只删除混合内容中已确认的行内片段 | `remove_inline_fragment` |
| 删除整个段落、行或其他已定位容器 | `remove_container` |
| 删除两个稳定边界之间已确认的连续逻辑块 | `remove_bounded_block` |
| 清空单元格内容，同时保留表格网格和单元格属性 | `clear_cell_preserve_grid` |
| 删除内容控件包装，同时保留已经批准的内部内容 | `unwrap_control_preserve_content` |

不要为了方便而选择范围更大的模式。如果一个安全目标或有界范围不能表达预期逻辑单元，
就先保留它，或在进一步观察后拆分操作。

## 定义槽位责任

为每个自动槽位确定：

- 稳定的 `slot_id` 和最终快照中的唯一 locator；
- 内容属于 `scalar`、`paragraph_stream` 还是 `composite`；
- 不从示例数量推断的最小与最大基数；
- 必须保留的物理容器或边界；
- 最终有效样式观测，以及独立存在的文字要求；
- 责任属于 fill、generate、repeat 还是 conditional。

当下游工作需要人工或语义放置，且无法唯一、安全地自动执行时，使用 manual 区域。当
当前证据完全无法定义责任时，记录 gap。

## 解释比较证据

`template_compare` 报告事实并选择相关图片，但不判断视觉是否正确。

确认每项预期变化都能对应到一个 operation，每项意外变化都已经解释或解决，固定内容和
容器保持完整，分页变化符合预期，而且局部裁剪与整页上下文一致。页数变化、对象到页面
的映射失败或分节行为受影响时，扩大审查范围。最终审查必须覆盖提交给 build 的精确快照
中的全部页面。

## 按需读取 references

- 处理内容责任、逻辑单元、说明语义迁移、生成对象或来源冲突时，阅读
  [references/template-semantics.md](references/template-semantics.md)。
- 选择删除模式、槽位内容种类、基数、manual 区域或 gap 时，阅读
  [references/deletion-and-slot-decisions.md](references/deletion-and-slot-decisions.md)。
- 解析最终有效格式，或比较文字要求与模板证据时，阅读
  [references/style-reconciliation.md](references/style-reconciliation.md)。
- 解释结构/视觉变化或决定审查范围时，阅读
  [references/visual-regression.md](references/visual-regression.md)。

## 完成与回复

返回 frozen artifact 的位置、模板 hash、自动槽位与 manual/gap 区域的简要摘要，以及
下游消费者需要知道的非阻断发现。如果冻结被阻止，先根据 findings 继续修正；只有确认
当前范围内没有安全修正路径时，才报告具体阻塞和所需输入。任何情况下都不要把 candidate
描述为可交付产物。
