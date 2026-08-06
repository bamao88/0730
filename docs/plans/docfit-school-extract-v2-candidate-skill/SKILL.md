---
name: docfit-school-extract
description: 将学校论文 Word 模板整理为冻结且可安全填写的模板产物。当用户提供学校模板、格式要求或官方示例，并希望获得干净的可复用模板及与模板 hash 绑定的槽位 manifest 时，使用本 Skill。
---

# 学校模板提取

将当前任务的学校材料整理为两个核心交付内容：

1. 一份干净的模板 DOCX，保留必需结构、固定内容、样式和 Word 行为；
2. 一份与该模板精确 hash 绑定的冻结产物 manifest，包含自动槽位、人工区域、gap、来源
   和审查发现。

只有同时包含 `clean-template.docx`、`template-artifact.json`、`visual-review.json`、
`build-report.json` 和 `freeze-report.json`，并由 `template_freeze` 发布的目录才是 frozen
artifact。candidate 只有前四项，且 manifest 状态仍为 `candidate`。

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

本 Skill 文档列出的是 v1 候选能力合同全集，不表示所有 mutation mode 必须同时上线。实际
运行只选择当前获批能力切片中、且已经通过 Tool / Code Gate 的 mode/target/content kind；
其余候选能力必须保持 unsupported。不要把未开放 mode 映射为相近动作，也不要通过 Bash、
脚本或提示词旁路实现；出现真实需要时，先回到产品决定和能力合同增加下一切片。

## 推荐方法

根据实际证据调整以下顺序。这是操作方法，不是固定状态机。

1. 盘点所有模板、文字要求和官方示例。记录来源、冲突、缺失输入，以及必须保持只读的
   文件。
2. 调用 `template_observe` 建立不可变快照。观察结构、可见对象、最终有效格式、槽位候选、
   PDF 页面和不支持内容。初次结构盘点使用 `visual_level: none`；返工定位需要图片时使用
   `quick`；只有最终精确快照的交付级审查使用或复用 `authoritative`，避免无意义的外部转换。
3. 分别记录当前可见角色、清理后必须存续的责任、责任修饰字段和证据状态；不要把这些
   不同问题压成一个分类字段。
4. 根据语义决定需要保留、建立槽位、登记 manual 区域或删除哪些当前内容。只有明确形成
   `remove_content` 操作后才选择删除模式；内容责任本身不能写成 `remove`。
5. 删除说明或示例前，先把其中仍需保留的格式、基数、生成或放置责任迁移到槽位或区域
   决定中。
6. 将文字要求与模板最终有效格式交叉验证。保留重要冲突；不要仅凭样式名、历史学校或
   惯例裁决冲突。
7. 为每项修改选择精确目标、预期指纹、删除模式和必要的槽位语义。当歧义会实质改变
   可复用模板时，询问用户。
8. 在当前任务 work 目录写入 `mutation-decisions.yaml`，按 decision compilation reference
   运行 `scripts/compile_mutation_plan.py`，再把 `mutation-plan.json` 路径交给
   `template_mutate`。不要单独使用页码或文本作为编辑身份；目标过期或歧义时重新观察和
   判断。
9. 调用 `template_compare`。检查它返回的预期变化、意外变化和原生图片，判断结果是否
   合理、是否需要继续修改，或是否需要用户输入。
10. 必要时用 compare 的 image cursor 分批读取原生图片；对精确最终 snapshot 运行
    `review_mode: final_review` 并完成全页审查。把最终语义、完整 mutation/comparison
    evidence chain 和图片 dispositions 一并写入 `artifact-decisions.yaml`，再运行
    `scripts/compile_artifact_spec.py`。把生成的 `artifact-spec.json` 交给 `template_build`，
    并且只把其输出视为 candidate。
11. 把 candidate 提交给 `template_freeze`。根据 findings 继续修正；只有这个独立 Tool
    返回 `call_status: ok`、`artifact_status: frozen`、`published: true`，并且你确认最终
    结果满足任务语义和视觉要求后，才能交付。

## 三条核心判断原则

1. 先确定清理后必须继续存在的责任。
2. 删除前先为这些责任安排自动槽位、manual region 或其他明确目标。
3. 只删除当前可见内容，并采用不破坏周边结构的最小安全范围。

固定内容、未知内容和无法唯一定位的自动槽位都必须安全失败或转为 manual/unresolved；
修改成功、局部审查或 build 成功都不能代替最终全页审查和 `template_freeze`。

## 发现错误后继续修正

把脚本和 Tool 返回的问题当作下一步修改依据，而不是任务终点：

- 编译器拒绝 decision file：根据错误补齐或修正语义决定和证据，然后重新编译；不要
  手改规范输出绕过检查。
- `template_mutate` 拒绝 stale/ambiguous ref 或后置检查失败：重新 observe，修正目标、
  fingerprint、删除模式或槽位语义，再生成和执行新的 mutation plan。
- `template_compare` 显示预期变化未发生、出现误伤或视觉结果不合理：不要把 finding
  直接标为 accepted；形成纠正决定，执行新的修改并重新比较。
- `template_build` 拒绝 artifact spec：修正最终语义清单、来源、槽位、manual/gap、
  evidence chain 或图片 dispositions 后重新编译和 build。
- `template_freeze` 返回 blocking findings：定位到对应的观察、决定、修改、视觉审查或
  artifact 问题，修正后重新 build 和 freeze。即使 freeze 成功，只要你发现语义或视觉
  错误，也不得交付，必须继续修正。

编译器、mutate、build 或 freeze 返工时，为新的尝试选择尚不存在的 work/output 路径；不要
覆盖或复用旧 attempt 的输出，也不要为此建立额外的工作流状态机。observe 返回的
`unsupported_features` 如果是 machine-blocking，不能继续处理受影响范围；非 blocking 项必须
显式登记为 manual、gap 或 unresolved，不能在 artifact 中静默丢失。

只有缺少必要用户裁决、授权材料或不可替代的外部能力，并且当前范围内没有安全修正路径
时，才报告阻塞。报告时说明已经确认的事实、阻塞原因和解除阻塞所需输入。

缺少会实质改变结果的用户裁决时，使用宿主提供的原生 `AskUserQuestion`，在同一任务会话中
等待答案；不要创建问题文件、暂停状态、session registry 或自定义问答协议。Tool 返回错误
时，根据稳定失败码在当前 Agent loop 中修正或询问，不要由脚本自动重放有副作用的调用。

Tool 的 `call_status: ok` 只说明调用完成。build 的领域状态是
`artifact_status: candidate`；freeze 验证未通过时是 `artifact_status: blocked` 且
`published: false`。后者仍是返工输入，不是自动的任务阻塞。

## 在调用 Tool 前编译决定

相对于当前 `SKILL.md` 解析 `scripts/` 路径；不要临时重新实现这些编译器。

| 脚本 | Agent 编写的输入 | 规范输出 | 消费方 |
|---|---|---|---|
| `compile_mutation_plan.py` | `mutation-decisions.yaml` | `mutation-plan.json` | `template_mutate` |
| `compile_artifact_spec.py` | 最终语义、evidence chain 与视觉 dispositions 的 `artifact-decisions.yaml` | 内嵌 typed review record 的 `artifact-spec.json` | `template_build` |

先写清语义决定及其证据，再运行脚本；脚本只负责检查和序列化。编译错误表示决定缺失或
互相矛盾，不代表可以弱化 schema。脚本必须原子生成规范输出，不得读取或修改 DOCX、
调用 Tool、推导文档语义，也不得宣称审查或冻结已经通过。Tool 会重新验证每一份编译结果。

准备两份决定文件或解释编译错误前，阅读
[references/decision-compilation.md](references/decision-compilation.md)。

## 决定文件只回答两个边界

- `mutation-decisions.yaml` 回答当前对象、存续责任、迁移目标、修改动作和需要保留的物理
  结构。
- `artifact-decisions.yaml` 回答最终 sources、fixed/slot/manual/gap、样式冲突、完整
  evidence chain 和最终全页 dispositions。

不要在主 Skill 中临时发明字段或删除方式。涉及内容责任、槽位字段、六种删除模式、样式
冲突或视觉覆盖时，读取对应 reference，并让编译器执行确定性约束。

## 解释比较证据

`template_compare` 报告事实并选择相关图片，但不判断视觉是否正确。

确认每项预期变化都能对应到一个 operation，每项意外变化都已经解释或解决，固定内容和
容器保持完整，分页变化符合预期，而且局部裁剪与整页上下文一致。页数变化、对象到页面
的映射失败或分节行为受影响时，扩大审查范围。最终审查必须覆盖提交给 build 的精确快照
中的全部页面。长文档必须通过 comparison image cursor 分批读完，不能因单次传输预算而
省略页面。

Tool 的确定性阻断事实使用 `machine_blocking`，你的解释使用
`disposition: accepted | blocking | needs_edit`。不能用 `accepted` 清除 machine-blocking
finding；必须通过新的修改和 comparison 使它消失。

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

通过宿主要求的 structured output 返回 `status`、frozen artifact 位置、模板 hash、
`artifact_ref`，以及 slot、fixed、manual、gap、unresolved 的结构化数量；这些值必须与磁盘
中的最终 manifest 一致。自然语言只做简要摘要，不把 JSON 嵌进回复等待下游解析。另列下游
消费者需要知道的非阻断发现。如果冻结被阻止，先根据 findings 继续修正；只有确认当前范围
内没有安全修正路径时，才报告具体阻塞和所需输入。任何情况下都不要把 candidate 描述为
可交付产物。
