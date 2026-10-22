# 模板提取模块

本文是模板提取的唯一模块流程文档。它合并并取代旧的单元拆分、post-unit 和阶段恢复同级文档；
后续不要再把模板提取流程拆成多个 `docs/modules/template-extraction-*.md` 文档。

本文不是绝对正确或不可调整的规范，而是当前认知下的最佳流程基线。后续实现、调试或验证过程中，
如果证据表明需要调整流程、职责或文档结构，可以调整；但调整前必须先说明问题、替代方案和影响范围，
并与用户沟通确认。最终目标始终是模板提取效果最佳，而不是维护某份文档本身的形式。

本文回答：

- 模板提取从输入到交付的完整流程；
- Skill、Agent、Subagent、Harness、Tool、Schema、App、Test/Eval 各自负责什么；
- `unit-boundary`、post-unit、`UnitBoundaryProof` 和 resume proof 在同一个流程里的位置；
- 调试时如何先归因到正确层，再决定改 Skill、Harness、Tool、Schema、App、Test/Eval 还是文档。

状态: 当前模块流程与责任边界
Contract 文件: [template-extraction](../contracts/template-extraction.md)
当前状态: [docfit-school-extract-v2](../status/active/docfit-school-extract-v2.md)
长期 ADR: [ADR 0001 视觉判断与统一源对象边界](../adr/0001-template-unit-boundary-visual-first.md)
阶段 replay: [../../evals/template-extraction/stage-replay.md](../../evals/template-extraction/stage-replay.md)

模板提取对外产品交付始终只有：

```text
output/final-template.docx
output/fill-contract.yaml
```

阶段 proof、render、trace、candidate、replay fixture 和 diagnostics 都是内部证据，不是新的产品模块，
也不是跨模块最终合同。

## 顶层构成职责

模板提取的流程可以分阶段调试，但构成层高度一致：Agent 做学校语义判断，Harness 组织流程和机械门禁，
Tool 提供确定性证据与物化，App 保护输入输出和恢复发布。

| 构成 | 负责 | 不负责 |
| --- | --- | --- |
| Skill / Reference | 教 Agent 如何识别学校模板语义、阶段入口、证据类型和失败恢复口径 | Harness protocol、Tool schema 字段清单、operation 枚举、内部 state、timeout、trace path、临时 workaround |
| Agent | 基于当前证据做学校语义裁决、输出边界判断、责任判断、干净模板处理、`needs_input` 和后续 `open_questions` | 文件复制、权限、路径、hash、snapshot、发布、机械 coverage、最终 postcondition |
| Subagent | 只读局部分析、候选整理、冲突摘要 | 最终裁决、Registry 最终绑定、调用 post-unit 机械检查/物化 Tool、completion 判断 |
| Harness | 准备上下文、调度阶段、执行 Tool、保存 proof/state、校验 schema、coverage、顺序、冲突、可执行性、原判断效果、hash 和发布门 | 判断学校语义是否正确 |
| Tool | 渲染、结构/视觉/Registry/style 取证、locator/span 解析、按原范围完成 DOCX mutation、提供实际效果的 validation | 第二套 Agent loop、学校语义判断、长期业务状态机 |
| Schema | 固定 Agent/Harness/Tool 交换的数据形状和 fail-closed 条件 | 表达所有运行策略或替代流程文档 |
| App / CLI | 输入隔离、`--until`/`--from`/`--resume-proof`、task workspace、原子发布、路径和 postcondition | 学校领域语义 |
| Test / Eval | 证明合同、门禁、replay 和 Actual-vs-Gold 离线评分 | 作为 runtime oracle 注入 Agent prompt |

如果一次修复必须同时改 Skill、Harness、Tool、Schema 和 App，先说明这是跨层合同变更，并为每层留下独立 proof。

## 完整流程

```text
输入隔离
  -> 完整 canonical source inventory（首次 Agent 判断前）
  -> evidence startup context
  -> unit-boundary checkpoint
  -> UnitBoundaryProof / resolved_units
  -> unit reading packet projection
  -> SemanticJudgmentSet
  -> post-unit Harness phase review
  -> deterministic materialization from accepted judgments
  -> refreshed evidence
  -> completion review
  -> fail-closed publish
```

| 阶段 | Agent 负责 | Harness / Tool / App 负责 | 阶段出口 |
| --- | --- | --- | --- |
| 输入隔离 | 不读取学生论文，不扩展输出边界 | 复制只读输入、绑定 source hash、建立唯一完整源对象清单、准备 task root 和 tool surface | 源、候选、Registry、输出目录清楚 |
| 建立视野 | 识别学校模板大致结构和证据缺口 | 提供 render、document map、结构/视觉 evidence handles | 能进入单元边界判断 |
| unit-boundary | 结合视觉线索提出正文功能单元名称及已有源对象上的起止边界 | 在正文 story 上检查连续边界，并按原 Word story 事实覆盖所有辅助条目，检查完整 source inventory、顺序、重叠和 snapshot | `UnitBoundaryProof` / `resolved_units` |
| post-unit evidence construction | 选择当前 unit 或范围取证 | 把初始清单按 accepted unit 源范围投影成 Agent-readable reading packet，保持原 ID 和底层映射 | 当前 source/candidate 上的 source entries 和 unit reading packet |
| semantic judgment set | 对初始 source entries 的当前单元范围表达有序语义分段、字段选择、样式义务、输出效果和 open questions | 提供 reading view、维护底层映射、evidence refs、Registry identity 和 session ledger | `SemanticJudgmentSet` |
| phase review | 声明判断阶段完成或说明缺证据 | 自动检查目标可解析、Registry 存在、coverage、overlap、conflict、可执行性和 blocking open questions | `HarnessReviewResult` |
| materialization | 不逐对象手动过门禁；仅在语义反馈需要时修订判断 | 按 accepted source spans 完成修改，独立核验原义务及范围外保留内容，刷新证据 | 原判断效果已兑现、绑定新 hash 的候选 |
| completion review | 只在宿主反馈暴露语义缺口时补判断，或明确 `needs_input` | 提供 candidate validation、visual coverage、completion gate 和发布门 | Harness/App 发布或结构化失败 |

上一阶段 proof 没闭合前，不继续修下一阶段。例如单元边界不可信时不调字段槽；apply no-op 未归因时不调
Schema；completion gate 没过时不宣称模板质量。

## 单元边界 Checkpoint

单元拆分的目标是在正式生成模板资产前，把学校模板的正文 story 切成顶层、连续、可验证的逻辑单元；页眉、页脚、脚注和尾注由 Harness 另建辅助取证范围，仍须进入 post-unit 判断。典型单元包括封面、
声明页、目录、中文摘要、英文摘要、正文结构、参考文献、附录、致谢、评阅/答辩/学校附表。

单元拆分只回答“从哪里开始，到哪里结束”。它不负责识别姓名槽、删除提醒、字段绑定、样式合同或最终
Word 物化；这些都属于 post-unit。

Agent 输入包含初始清单中的可读文本、源对象 ID、源顺序和可用布局/页面线索。视觉帮助判断
学校功能区，源对象 ID 负责唯一定位。同名标题、相同文字出现在不同位置时，必须选择对应对象，
不能通过全文搜索、页码或“第一个/最后一个同名项”重新找位置。

Agent 输出顶层 units，包含分组名称 `unit_id`、`unit_name` 和 `start_boundary` / `end_boundary`。
每个边界引用已有 `source_entry_id`，`edge` 选择 `start`、`end` 或 `split`。内部切点用 `before` / `after` 前后两段
精确原文表达，两段拼接必须等于源对象全文；Harness 计算 offsets 并调用共享源范围解析器。
起点包含、终点不包含。空文本结构对象只能取对象开始/结束。

同一源对象可以跨两个功能区，两个分组都继续引用原 ID 及各自的子范围，不能生成新的对象身份。
Harness 校验正文单元在正文阅读序列上连续且无重叠/缺口，并校验辅助 story scope 与正文单元共同完整覆盖初始清单；同时校验 source snapshot 和 inventory binding。
页码、文字和视觉区域只作语义证据，不存在独立定位成功入口，Agent 也不输出 Word locator。

边界证据不足时返回顶层 `needs_input`。姓名槽、字段绑定、样式、清理、生成机制和后续 open questions
不进入 unit 输出。反馈说明出错单元、源对象可读内容和边界问题，让 Agent 修订语义选择；不要求
Agent 算 hash、offset 或维护执行账本。Harness 不判定学校单元命名是否最佳。

单元阶段常见归因：

| 现象 | 首选归因 |
| --- | --- |
| Agent 把姓名槽、删除提醒或图片拆成顶层单元 | Skill / Reference 语义规则不足 |
| Agent 把目录项当成正文真实标题 | reading packet 未提供充分上下文或 Agent 选择了错误的源对象 |
| 同一对象内部边界有缺口/重叠 | Harness 范围解析或 Agent 切点原文不完整 |
| Agent 重复请求同一 slice | evidence API 缺少 cursor/window 或 feedback 不可发现 |
| Harness 只返回内部 id | Harness feedback 不够可行动 |
| 发布产物缺文件或 hash 不一致 | App postcondition 失败 |

后续 Registry、样式、字段槽、删除提醒和最终模板质量只能作为后续阶段问题，不能阻断当前单元边界候选，
也不能作为 unit 输出字段。

## UnitBoundaryProof 与 Resume

每个可恢复 checkpoint 应产出机器可读 proof。单元阶段 proof 的长期接口名是 `UnitBoundaryProof`；
当前默认落盘路径是：

```text
work/.docfit/initial-source-inventory.json
work/.docfit/unit-boundary-checkpoint.json
```

初始账本为 `docfit-initial-source-inventory/v1`，单元 proof 为 `docfit-unit-boundary-proof/v3`。
任务 manifest 绑定初始 `source_inventory_digest`；proof 保存 `units` 原始边界和
`resolved_body_units`、`auxiliary_scopes` 与合并后的 `resolved_units[].source_spans`，`unit_projection_digest` 绑定解析结果。辅助 scope 按 story 类别分组，内部 `story_regions` 保留各 Word story 实例的源条目归属；不会按页码推断。

以下 proof 字段由 Harness/App 写入，不是 Agent 输出要求。proof 至少表达：

- `schema_version`、`checkpoint`、`status`；
- `source_hash`、输入 DOCX 引用和首次判断前持久化的完整 source inventory binding；
- `render_ref`；
- `resolved_units`；
- 每个 unit 的 `unit_id`、`unit_name`、源对象边界和解析后的精确 source spans；
- Word locator/fragment 是这些 spans 的内部推导证据，不能反向覆盖 Agent 选择；
- coverage stats，包括 missing/overlap 为零的证明；
- 生成时间、工具版本或代码版本摘要；
- 后续阶段遗留问题摘要（可选），但不能反馈成 unit-boundary Agent 输出字段。

`resolved_units` 是后续阶段的稳定 work-scope 接口；其中只有 `resolved_body_units` 是学校功能区，`auxiliary_scopes` 是来源事实范围。后续字段、样式、Registry 和 apply 调试默认从 scope-scoped
evidence 开始，不重新拆单元。

CLI 语义：

| 参数 | 含义 |
| --- | --- |
| `--until unit-boundary` | 只运行到单元边界 checkpoint，通过后写 proof 并停止 |
| `--from unit-boundary` | 读取默认 proof，校验后从单元之后继续 |
| `--resume-proof PATH` | 显式读取指定 proof，校验后恢复 |
| `--force-rebuild-checkpoint unit-boundary` | 忽略旧 proof，重新跑该 checkpoint |

从 proof 恢复前，runtime 必须 fail closed 地校验：

- 当前输入 DOCX hash 等于 proof 的 `source_hash`；
- proof schema 版本受支持，`status` 为 `ok`；
- `resolved_units` 非空，且 `unit_id` 唯一；
- 初始 inventory 版本、摘要和当前不可变源一致，不在恢复时按分区重新生成 ID；
- 源对象边界重解后的 exact spans 与 proof 完全一致，不能靠交换 offsets 后重算摘要通过；
- coverage 对同一完整清单仍为 `ok`，或返回具体缺口；
- proof 不引用 Gold、旧 run 输出、学生论文或 task root 外未授权文件。

旧页码/文字定位 proof 或缺少初始清单绑定的记录明确拒绝，没有自动转换或旧定位兜底。
校验失败须从当前合同的输入准备重跑对应阶段，不能静默继续下一阶段。

## Post-unit 主流程

`unit-boundary` 只证明顶层学校功能单元边界已经机械闭合。它不证明字段、样式、删除、保留、生成或最终
完成已经正确。

post-unit 的稳定顺序是：

```text
初始 canonical source inventory + resolved_units 精确源范围
  -> unit reading packet projection
  -> SemanticJudgmentSet
  -> Harness phase review
  -> deterministic materialization + refreshed evidence
  -> completion review
```

关键约束：

- 不能从 `resolved_units` 直接跳到可物化编辑意图。提交前必须先有当前范围的责任判断。
- 不能先按字段名猜绑定对象。只有判断出范围承担填写接口、正文 member、生成机制或样式义务后，
  才进入 Registry 字段匹配。
- 不能先抽样式再决定对象责任。样式证据只服务于已确认的 slot、body member、生成内容或固定内容保留。
- 不能把样例、说明、空白或 heading 示例直接删除。删除前必须证明它不是唯一规则、唯一样式证据或唯一填写位置。
- 不让 Agent 每判断一个对象就手动做机械门禁；Harness 在阶段完成点自动 review。
- `source_hash`、当前 candidate、stale ref 和执行顺序由 Harness/session/Executor 维护，不进入 Agent 的判断对象。
- materializer 不能用代码窄规则替 Agent 或 schema 做语义判断。字段绑定、正文结构 variant、固定标题、
  格式说明、填写占位和视觉空格必须先由 Agent-facing judgment、Registry affordance 或 schema enum 表达；
  确定性代码只在 accepted judgment 之后按类别物化，不能根据单个学校 wording 或模型自由文本片段猜测。

长期主定位入口冻结为 `source_entry_id + span`。`source_entry_id` 是输入 normalize 层生成的
canonical source entry ID，指向 Agent 可判断的最小源内容单元；它不是 raw Word object ID，也不是
unit reading packet 临时生成的 `reading_block_id` / `range_id`。raw `object_id`、`object_ref`、
`locator` 和 `fingerprint` 只能作为 source entry provenance 留在 Harness/Tool/App 内部账本中。
`source_content_id` 只允许出现在历史说明或其它模块自身的既有合同中；模板提取 runtime 不接受它作为
兼容别名，也不把它迁移成新增合同的主定位字段。

unit reading packet 是 post-unit 默认输入。它由 Harness/Tool 在 Agent 判断前构建：把 accepted unit
范围使用初始清单中的 canonical `source_entries`，再把可见文本、Word 结构、相邻关系、
空白布局、源段落样式、页眉/正文所属 story、标题大纲级别、列表编号、签名区、日期区、说明文字、固定正文和生成内容投影成 Agent 可读的 source-entry rows。
`reading_blocks` / `range_id` 只保留为分页、合并和上下文展示用的 reading view。底层 Word inspect
objects、locator、object_ref、target_ref、fingerprint 和 hash 继续存在，但只作为 Harness/Tool 的
mapping、校验和执行账本，不作为 Agent 默认输入。

Registry 候选和样式事实不是每个 block 的默认输入。post-unit 入口必须已经带入当前 Registry snapshot
派生的 `field_id_vocabulary`；只有字段槽判断、正文/生成绑定或样式继承不清时，Agent 才基于这份输入词表
和必要 evidence 选择字段。reading block/range 分割不合理时，Agent 只能在对应
`source_entry_id` 的 judgment 内用有序 `parts` 拆分可见文本，或返回 `needs_input` 说明缺少的学校语义上下文；
由 Harness 把 parts 映射到底层对象和可写 target。

post-unit 的覆盖全集由 Harness 从 accepted units、canonical source entries 和 reading packet mapping
给出。Agent 只围绕 `source_entries[].source_entry_id` 和 `source_entries[].text` 输出语义判断；
`reading_block_id` / `reading_range_id` 只能组织 reading view，不能表达 judgment scope。
Harness 的 closure gate 以 source entry span 为准：每个需要覆盖的 canonical source entry 必须被覆盖一次，
span 不能 missing、overlap 或引用未知 entry，且每个 accepted span 必须能展开到内部 provenance。raw
object coverage 只保留为内部执行账本和负向测试材料。Harness 同时检查 Registry vocabulary 来源和执行可消费性。
materializer / Tool 执行入口只消费 Harness-accepted ordered parts 和 Harness-resolved source-entry
spans；内部再展开到 raw object_ref、locator、fingerprint 和可写 Word target，并在写入前检查 source
DOCX hash 与 provenance freshness，stale raw object 必须 fail closed。
可见文本既是 Agent 拆分依据，也是 Harness 解析 `span_ref` 的输入。当 unit reading packet 已存在时，
runtime Agent 提交 `covered_object_ids`、locator 或 object ref 视为
走错工作面；这类对象级覆盖只保留给 Harness/Tool 内部映射账本，不能作为产品 Agent 默认合同。

每个进入处理的 unit 或 unit 内范围，都按 ordered parts 形成可消费语义判断：

1. 用 `source_entry_id` 指向一个 canonical source entry；reading view 无法表达成 canonical entry 时，
   必须由 normalize / packet projection 修正，不能回退到 legacy scope。
2. 用有序 `parts` 说明该 entry 文本片段是固定标签、填写槽、正文代表、生成内容、人工区、样式说明、清理片段或 unresolved。
3. 只有需要执行字段绑定的 `fill_slot`、`body_structure`、`generated_content` part 才写 `field_id`，
   且必须来自本轮 `field_id_vocabulary.allowed_field_ids`；词表中没有安全字段时返回 `needs_input`。

同一 canonical source entry 可以包含多个有序 `body_structure` part；当它们解析到同一个顶层 Word
段落时，readiness 与 materializer 必须按 accepted span 顺序生成行内复合接口。不同 source entry
落到同一载体、重叠 span、跨载体或表格内部成员仍须 fail closed。
同字段的正文片段可在已接受 cleanup/style_only 文字删除后合成一个连续接口，但必须同一来源、顶层段落和
单元，不能跨保留文字或其他字段；不满足这些条件的重复接口仍阻塞。该操作不改原判断，执行及交付记录保留
首段锚点、全部贡献来源和删除分隔范围；含合并接口的嵌套物化来源合同使用 v2 并由发布端和消费端重验。
同一 source entry 内交替出现的 `fixed_label`、`manual_region`、`style_only`、`cleanup` 属于一个保留的
人工复合载体，不需要拆成多个执行 intent；只要混入字段角色，仍按对应字段 intent 和冲突门禁处理。

`semantic_judgments` 是 Agent 提交给 Harness 的可消费语义结果。Harness 可以检查 shape、coverage、
target resolvability、Registry identity、overlap、conflict 和 execution consumability，但不判断学校语义是否正确。
检查失败先按责任归因：只有可通过补充或修订语义判断解决的问题才返回 revision packet，Agent 按
affected scopes 修正判断集；工程问题由对应责任层处理。不是让 Agent 主动调用新的检查 Tool。

候选的用途和字段尚不是语义正确性的证明。原文分段错误的修订可以改变受影响条目的 role / field_id，
新候选必须重新通过范围、字段和关联约束检查。Harness 不得把“已提交 parts 用途相同”解释为
“未提交文字用途也相同”，不能自动把部分文本扩成全文；显式空白传输只按提交字符和数量解码，
随后仍须与原文精确匹配。

新提交的混合文字片段使用同一 part 的 `leading_whitespace` / `trailing_whitespace`
有序 codepoint/count 数组表达边界空白，`text` 保留中间原文及内部空白。解码只还原显式字符，
不得增加、合并或拆分 part，也不得改变 role、field_id 或从原文推断缺失字符。
纯空白片段继续使用空 `text` 加 `whitespace`；两种传输形式不能混用。
历史候选中已有的字面空白仍可回放。传输形式不参与最终范围或填写位置身份计算。

当一个 source entry 的全部原文承担同一种语义责任时，Agent 可明确提交唯一一个
`parts: [{whole_entry: true, role: ..., field_id: ...}]`。该声明包含原文中的全部文字、符号和空白；
不能同时提交 text／空白编码，也不能与其他 part 混用。Harness 仅按这个显式声明取回同一条
已绑定原文，再走原有范围、跨单元切点、字段和执行检查，最终 span／slot 身份与逐字提交相同。
混合用途仍提交分段 text；没有 whole_entry 声明时，单一 role 或部分 text 绝不触发全文补齐。
这只减少整条判断的抄写负担，不证明用途判断正确；误把混合用途判为整条仍属于语义错误。

执行前检查区分可修订的判断合同错误与工程失败。字段缺失或角色与字段不兼容可返回 Agent；
字段与用途兼容性属于 Harness 的机械合同检查：每批提交先根据输入词表的
`usage_affordance.allowed_part_roles` 检查，整体检查与已保存 review 的复用使用同一规则。
组合不兼容时向 Agent 返回相关条目、提交用途与允许用途，允许重选字段或用途；词表本身的
元数据缺失或损坏时停止并归 Harness。仅检查字段存在不足以接受候选，不得用字段名猜角色。

已接受范围对应的 Word 操作不支持时，保留判断并归为 Tool 能力阻塞；映射、词表来源、快照或
未知执行状态错误归 Harness 处理。后两类不消耗语义修订次数、不生成候选、不发布，也不要求
把填写或正文用途改成非字段用途来迁就执行器。App 与直接物化入口使用同一失败分类。

post-unit 修订记录保存在 task-local 的 `work/.docfit/harness/semantic-revisions/`。
每次请求在发送前保存实际 prompt，结构化响应在检查前保存；失败提交、needs_input、局部拒绝、
全局检查、运行失败和候选版本差异均单独留档，不记录模型隐藏推理，不复制到普通 trace。
每个事件绑定当前 manifest 和前序事件；候选版本必须能由关联请求的真实提交重新计算，
原始提交本身不能成为已接受结果。候选事件先于候选账本投影落盘，中断恢复只修复该投影，
随后仍重新进行全局检查。记录或持久化失败属于 Harness 故障，不能静默继续。
没有修订历史的旧候选不能作为新运行恢复基线；需保留旧证据并从有效输入重新开始语义阶段。
诊断回放使用独立 evidence mode，不能被 runtime 当作真实会话历史恢复。

需要连带修订其它已判断条目时，post-unit Agent 可返回 `status=expand_revision`、空的
`semantic_judgments` 和 `revision_request={source_entry_ids, reason}`。该请求不能夹带修改，
只能引用当前任务已有判断的源条目。Harness 验证新增范围，补完整原文、旧判断与关联反馈，
按原有批次重新开放；先前已经完成的批次也可重开，未开放条目保持原样。所有待修订范围完成后
再执行全局检查。扩展请求和待修订范围随事件账本恢复；重复、未知条目、无理由或无新增范围
返回具体合同反馈。扩展次数有整次任务上限，恢复不会重置该计数。

源文检查只把明确可由判断修复的错误反馈给 Agent。文字到 Word 的映射缺口、歧义、条目类型
不一致、缺少输入词表及未知检查失败归 Harness；保留具体 blocker 并停止，不消耗语义修订次数。
反馈投影保留完整原文、实际提交、具体原因与责任归属。无法转换成可读诊断的内部错误也需工程调查，
不得替换成泛泛的“重新判断”。

## 字段、样式与阶段执行

字段和样式依赖责任判断：

```text
责任判断
  -> 需要填写/正文/生成时从 pre-input vocabulary 选择 field_id
  -> accepted field binding 后确认承载对象
  -> 承载对象确认后提取样式证据
  -> 样式证据进入 Fill Contract 或明确 no-op/gap
```

典型例子：

- 学生姓名占位范围：先判断为填写接口，再匹配 `author.name.zh`，再确认承载段落/SDT，最后提取该槽值样式义务。
- Heading 示例：先判断它是正文代表、样例还是唯一 heading 样式证据；闭合后才能决定绑定 body heading、
  保留为样式代表或删除。
- 删除提示文字：先判断它是否只是说明/样例；再确认它不承载唯一规则或唯一样式证据；最后才进入 remove action。

阶段执行只在 `SemanticJudgmentSet` 通过 Harness review 之后出现。它消费完整判断集，不是 Agent 每个对象
边判断边提交的 action plan。

Harness phase review 必须满足：

- 判断集覆盖 accepted units 的 canonical source-entry spans；
- 每个 accepted span 仍能在当前 snapshot 中精确解析；
- judgment 之间没有 missing、overlap、duplicate 或互斥 output effect；
- field_id 来自本轮 pre-input vocabulary，且 Registry snapshot/digest 未漂移；
- 删除或替换不会破坏唯一规则、唯一样式证据、唯一填写位置、图片锚点、表格边界或 section/layout；
- 样式义务已记录，或明确该动作不产生样式义务。
- 原范围上的每项执行义务都能由当前 Tool 能力兑现；覆盖完整、字段存在或能找到段落本身不足以证明可执行。

各 part 的用途不构成可由代码自行排序的语义优先级。互不重叠或合同允许组合的义务都要履行；
互斥判断交回 Agent 修订；合法但当前无法执行的组合由工程层补齐，不能靠扩大范围或改用途消解。

Harness revision packet 必须给 Agent 最小可修复上下文：

- affected unit / source entry；
- 原 judgment 和冲突 judgment 摘要；
- 可见文本、相邻语义块、布局线索和必要 evidence；
- 当前输入词表中的相关字段，或缺失字段语义说明；
- 需要修正的目标，而不是下一步 Tool 调用脚本。

代码层物化后必须重新取相关结构、对象、style evidence 和 render，并由 completion review 验收最终候选。
旧 snapshot 的 object_ref/evidence 不可证明新候选；这些快照账本由 Harness/session/Executor 维护。

## Completion 与发布

模板提取完成不是“所有工具都返回 ok”，也不是 Agent 交出最终候选路径或视觉复核账本。完成必须同时具备：

- accepted units 内所有需要处理的范围都有责任判断；
- 所有填写接口、正文 member、生成机制和样式义务已按合同落实，无阻止当前阶段交付的未完成项；
- 删除、保留、绑定及合法 no-op 均有与原判断对应的实际效果证据；生成机制区分模板阶段的保留与交接义务、
  内容填写后的刷新义务，记录未来刷新策略不能冒称已经刷新；
- Agent 输出的 `semantic_judgments` 只引用当前 packet 的 canonical `source_entry_id`；
- Harness/App 从已接受的语义判断生成或选择当前候选，并绑定当前 candidate hash；
- 最终 render、全页视觉检查、`candidate_validation` 和 `completion_gate` 都属于 Harness/App 机械验收；
  实际视觉结论由具名人工或外部视觉复核者提供，现有图片证据工具本身不产生版式合格结论。
  App 先准备原稿和最终候选全页图片；缺少当前版本逐页观察记录时停在待复核，不自动发布。
  复核入口为 task-local `work/.docfit/final-visual-review/current.json` 所指请求和记录路径；
  Agent 不输出该复核账本，产品人工签收另行完成。

- 发布只由 App 写出 `output/final-template.docx` 和 `output/fill-contract.yaml`。

缺少会改变语义判断的证据时，返回 `needs_input`；工程能力或环境阻塞按责任归属报告。阻塞与待复核
均表示尚未完成。不要用“已通过一次 apply”“candidate validation ok”或“错误已被拦截”代替交付。
可填写性需要最终 DOCX 与 Fill Contract 的实际接口消费证据；低层测试不能代替真实回放、Agent 闭环
或产品验收，各层按 [AGENTS.md](../../AGENTS.md#汇报口径) 分别报告。

## 调试归因

后续修模板提取任意 bug 时，先复用这条分层链路：

```text
正确输入 -> 当前 checkpoint -> Agent 语义/动作 -> Tool 证据或执行 -> Harness 机械验收 -> App 发布门
```

所有修复先回答：

1. 当前问题属于哪个 checkpoint：单元边界、字段/区域识别、样式证据、Registry 绑定、apply、
   completion gate、发布，还是 Eval/Gold 离线评分。
2. 这个 checkpoint 的完成条件是什么；哪些缺口只是后续阶段 open questions。
3. 失败 trace 证明问题在哪一层：Agent、Skill/Reference、Tool evidence、Tool execution、
   Harness feedback/gate、Schema、App postcondition、Test fixture 还是 Eval oracle。
4. 是否使用了正确输入、当前 source hash、当前 render/evidence，而不是合成文件、旧缓存、旧 PDF、
   Gold 答案或下游产物。
5. 哪个对照能排除错误归因、共同机制影响哪些入口；修复后原失败任务应如何成功完成，同类与已认可能力如何回归。
   更具体的反馈只能证明诊断进展。工程缺陷关闭需要合法任务成功完成的证据；语义问题则验证真实反馈修订闭环。

post-unit 常见归因：

| 现象 | 首选归因 |
| --- | --- |
| Agent 恢复后重新拆单元或查 `unit_coverage` | resume context / prompt / Skill 路由缺口 |
| Agent 直接 apply，没有完整判断集 | post-unit flow 缺口或 prompt/Skill 把执行暴露太早 |
| 字段绑定错 | 对比原字段选择、映射和最终位置，区分语义选择错误、绑定传播错误与执行错位 |
| 样式义务缺失 | 承载对象未确认，或 style evidence / Fill Contract handoff 缺口 |
| 执行后复用旧 refs | Harness/session candidate ledger 或 evidence invalidation 反馈缺口 |
| completion gate 前语义覆盖缺失 | `semantic_judgments` / closure 没闭合 |
| validation ok 但结果明显不对 | 对比输入事实、原判断与实际结果；判断错查语义依据，执行偏离查 Tool，漏检则查验收，不能凭 validation ok 排除工程错误 |

表中归因是调查入口，不能仅凭现象定责。一个 observed model error 不能直接变成应用自有语义状态机。
先检查事实、上下文和合同表达；语义判断确实错误且领域指引不足时，再改 Skill/Reference。

## 文档维护

本文维护模板提取的当前完整流程。相关信息按文档面维护：

- 黑盒输入输出和发布语义放在 [template-extraction Contract](../contracts/template-extraction.md)；
- 长期设计原因放在 [ADR 0001](../adr/0001-template-unit-boundary-visual-first.md)；
- 当前任务证据放在 `docs/plans/**` 或 `docs/status/active/**`；
- 事故复盘和临时证据放在 `docs/bugs/**`、`temp/**` 或 `output/**`；
- Skill 只保留 Agent 识别学校模板和处理阶段路由所需的稳定语义指导；
- 测试入口和阶段 replay 分别维护在 [../../tests/README.md](../../tests/README.md) 和
  [stage-replay](../../evals/template-extraction/stage-replay.md)。

如果旧 Skill、plan、status、human note、runtime architecture 或工具文档与本文冲突，先把旧文档当成
历史材料；不要把它们反向恢复成当前架构。
