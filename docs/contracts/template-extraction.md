# 模板提取模块 Contract

状态: 当前模块 Contract
模块: 模板提取 / `docfit prepare-template`
分支范围: `codex/template-extraction`

本文定义模板提取模块的黑盒边界。它约束调用方、下游最终内容填写模块、测试和 PR 审查可以依赖
的稳定事实；不记录 Agent 如何分解任务、如何选择页面证据、具体 edit operation 序列或某次运行
耗时。

## 责任

模板提取模块负责把当前任务提供的学校模板、可选学校要求和 Field Registry 整理成一份干净、
可填写、可审查的学校模板产物。

它负责：

- 忠实保留学校模板中应保留的固定内容、结构、页眉页脚、对象和规则；
- 识别并物化最终内容填写可消费的 `slot` / `region`；
- 将每个可填写接口绑定到 Field Registry 的 `field_id`；
- 从最终 Word 快照捕获学校样式事实、样式合同和已知缺口；
- 发布与最终 Word hash 原子绑定的 Fill Contract；
- 在发布前检查输入 hash、DOCX package、Registry 引用、locator、样式合同 digest 和最终视觉证据绑定。

它不负责：

- 读取学生论文或学生内容模型；
- 注入本次学生内容；
- 决定最终内容填写时的 placement；
- 选择通用兜底样式或把学校缺口补成最终填写样式；
- 生成最终论文 Word；
- 把学校事实写入长期 Knowledge、学校 profile 或跨任务资产。

## 允许输入

CLI 入口：

```bash
uv run docfit prepare-template \
  --school-template school-template.docx \
  --school-requirements school-requirements.md \
  --field-registry content-fields.yaml \
  --output out/template
```

稳定输入边界：

| 输入 | 必填 | 说明 |
|---|---:|---|
| `school-template.docx` | 是 | 当前任务的学校模板，只读复制到 `input/school-template.docx` |
| `school-requirements.*` | 否 | 支持文字、YAML/JSON、PDF、DOCX；只表达当前任务学校要求 |
| `content-fields.yaml` | 否 | 不显式提供时使用仓库固定研发 Registry `content-fields-v0.5.yaml` |

模块可以在任务目录内创建 `input/`、`work/`、`output/`。恢复运行必须匹配同一组输入 hash，并且只接受
`main_agent_full_context/v1` 任务 manifest。

## 禁止读取

模板提取模块不得把以下材料作为运行时输入、要求、oracle 或隐式上下文：

- `student.docx`、学生源目录或任意学生论文正文；
- `student-content.json`、Student Content Model、学生内容提取工作区；
- 最终内容填写输出目录、最终论文候选或最终生成报告；
- Template Extraction Eval 的 Gold、accepted answer、评分报告或 case oracle；
- 其他学校/其他任务的历史模板结论，除非用户把它们明确作为本次学校要求输入。

Eval 与 Gold 只在模块运行后离线评分，不进入 `prepare-template` Agent prompt 或 Tool 输入。

## Source 定位命名

长期主定位入口冻结为：

```text
source_entry_id + span
```

`source_entry_id` 的全名语义是 canonical source entry ID。canonical source entry 是输入 normalize
层从学校模板 inspect 事实生成的 Agent 可判断最小源内容单元；它不是 raw Word object，也不是 unit
reading packet 里的临时 `reading_block_id`。一个 canonical source entry 可以由一个或多个 raw Word
object 组成，但 `text` 是后续 Agent span 判断和 Harness span 解析的唯一文本基准。

`source_content_id` 是历史命名来源和兼容别名，不再作为模板提取或任何新增 source-localization
合同的主字段。既有 Student Content Model 中仍出现的 `source_content_id` 只能按 legacy/compat
内容项 ID 理解，不能反向定义新的 source entry 合同。

raw `object_id` / `object_ref`、`locator`、`fingerprint` 和 backend hash 只能作为 canonical source
entry 的内部 provenance、执行账本或机器合同材料存在。它们不是 Agent 主定位入口，不能要求 runtime
产品 Agent 输出或修复。

生成顺序固定为：

```text
不可变原始 DOCX
  -> full raw inspect objects
  -> normalize / canonical source inventory（首次 Agent 判断前）
  -> 源对象边界 / 功能区分组
  -> 同清单的 reading packet projection
```

`reading_block_id` / `range_id` 只是在 source entry 之后生成的 reading view token，不是 canonical
source entry 的生成输入，也不能升级成主源定位字段。

功能区边界也必须引用初始清单的 `source_entry_id`。页码、文本和视觉区域是判断证据，不能作为
另一套独立定位合同。对象内边界用原 ID 与精确前后原文表达，Harness 计算范围并校验原文完全一致。
首次生成 canonical 身份前，App 必须将完整 inspect objects 按绑定 Word 中的实际位置排序：正文按
XML 前序（容器在其子对象前），其他 story 按包关联顺序、story 内按实际位置；这不表示跨 story 的页面顺序。
不能直接采用后端按 paragraph/table/picture 类型分组的返回顺序。只改变初始事实的排列，不修改对象、文字、
底层映射或 ID 生成协议；新顺序会影响新任务的 source_order 与 source_entry_id，旧 proof 不得混用。
初始清单保存 `source_order_version`；缺少当前版本的旧任务禁止从产品入口静默恢复，须保留历史并重新准备。
边界检查须提供可行动的诊断：在端点能解析的相邻单元之间，报告具体重复/遗漏原文、涉及单元及其原提交
边界；空源条目也必须明确列出。无效端点单独定位到相应单元的 start/end 字段，不因此隐藏其他可确定的
边界问题。不能推测无效端点的位置，也不能自动把 end 改为 start 或替 Agent 决定文字归属。
相同诊断必须保留到 Agent 可见反馈：包含单元名称、源条目、精确文字、原边界；不泄露底层 Word 定位或摘要账本。
端点含义是相对于被引用条目的位置：start 在条目前，end 在条目后；两个相邻单元须在同一个位置交接。
源清单缺失、损坏或与输入绑定不符属于 Harness 状态故障，必须保留原失败归属与原因，停止当前阶段，
不转成边界修订，也不消耗语义修订次数。检查服务、反馈路由和后端选择均须遵守这一边界。
模型后端切换只用于模型请求超时、后端 API 失败或可重试的模型响应失败；工具能力、工程状态与已耗尽
的语义预算不能通过切换模型重新开始。`retryable` 本身不构成换后端授权。
单元边界阶段须在每次 SDK 请求前保存实际 prompt 和反馈，在收到最终响应后、检查前保存原始结构化提交
及相对上一提交的差异，随后保存检查结果或工程失败。记录使用 task-local 的独立运行目录，不覆盖历史运行；
普通可见输出可留档，隐藏推理与 API 错误正文不得进入判断记录。持久化失败归 Harness 并阻止下一步。
新分区 proof 的 `revision_evidence` 绑定接受检查与完整事件链，恢复时须验证原提交、检查结果和 proof
一致；不能从未检查的提交恢复为已接受结果。没有该字段的历史 proof 沿用原身份检查，其缺失逐轮证据不能补造。
同一个对象跨功能区保持同一身份；`unit_id` 仅为分组名。后续 ordered parts 必须尊重已接受切点，
同一对象的完整判断只提交一次，分批输入必须包含该对象涉及的全部分区上下文。

初始清单与快照绑定必须保留到恢复和发布。初始账本版本为 `docfit-initial-source-inventory/v1`，
分区 proof 为 `docfit-unit-boundary-proof/v3`：Agent 提交的 `units` 仅连续覆盖正文 story，Harness 从同一初始清单按 story 类别生成 `auxiliary_scopes`，并以 `story_regions` 区分各个 Word story 实例。`resolved_body_units` 与辅助范围共同组成供后续阶段消费的 `resolved_units`；完整 canonical 源条目必须恰好得到覆盖，辅助范围不能并入最后一个正文功能区。辅助 story 的区域编号不是物理页码。发布 provenance 包含 `source_partition`，
使消费者可以重解最早的分区范围并核对初始 inventory，而不只核对后半段 slot。旧 proof、缺绑定 ledger、独立 locator/target 覆盖输入
明确拒绝；不双读、不自动转换、不通过文字搜索重新定位。ID 闭环的范围包括第一次功能区判断，
仅复核 post-unit 来源不足以宣称全流程身份统一；验收还需从头真实 Agent 与实际 Word 范围证据。
这不等于学校语义、字段识别率或版式的全面产品验收。

Canonical source entry 的稳定模型是：

```json
{
  "source_entry_id": "source-entry-xxx",
  "text": "姓名：张三",
  "entry_type": "text",
  "source_order": {"block": 1, "inline": 0},
  "provenance": [
    {
      "object_id": "obj-a",
      "locator": "/body/p[1]/r[1]",
      "text_span": [0, 3]
    }
  ]
}
```

模型约束：

- 一个 `source_entry_id` 可以对应一个或多个 raw Word object。
- `text` 是 Agent span 判断和 Harness offset 解析的唯一文本基准。
- `provenance[].text_span` 指向 canonical entry text 内的字符范围，并能展开到 raw object 执行材料。
- 该模型不包含 `field_id`；字段绑定只能出现在后续 accepted semantic part 或 Fill Contract 派生物中。

## Runtime Agent 可见合同

`prepare-template` 的 runtime 产品 Agent 只承担学校模板语义判断。它可以看到 unit reading packet 中的
`source_entries[].source_entry_id`、`source_entries[].text`、相邻语义块、布局线索、pre-input
`field_id_vocabulary`，以及 Harness 已改写成语义工作面语言的反馈。`reading_block_id` / `range_id`
只保留为 reading view token，不是主源定位入口。Agent 不负责维护底层 DOCX、render、hash、coverage、
发布或 checkpoint backend 账本。

核心字段 ID 合同闭环只证明字段 ID 来源和传播边界，不证明 Agent 在真实学校模板里语义选对。验收时必须能证明：

- `field_id_vocabulary` 是 runtime Agent 正向选择字段 ID 的唯一合法来源；
- 旧 alias、旧字段形状和旧字段搜索接口不能作为正向输入被兼容迁移；
- runtime Registry search 不向 Agent 返回可选字段，字段只随 unit reading packet 预输入；
- compiler、readiness、materializer、publication 和 `fill-contract.yaml` 都不能从 Registry lookup、
  materialization receipt、Word content-control alias/tag 或旧 payload 自行补字段 ID；
- 旧路径若仍出现在仓库，只能出现在 fail-closed 实现、denylist、负向测试或历史/说明文档中。

post-unit 的 `semantic_judgments[]` 只能引用语义工作面范围，并且只能使用输入词表中的字段 ID。
默认允许：

```text
source_entry_id
parts[].text
parts[].whole_entry = true  # alternative: explicit sole-part responsibility for the entire entry
parts[].role = fixed_label | fill_slot | body_structure | generated_content | manual_region | style_only | cleanup
parts[].field_id  # only when role requires a Registry field
open_questions
reason
```

`scope.reading_block_id` / `scope.reading_range_id` 不属于当前输出合同，出现时必须 fail closed。
reading view token 只能帮助 Agent 阅读上下文，不能成为 judgment scope 或 span/slot identity。

`parts[].text` 必须是 `source_entries[].text` 内的有序可见文本拆分。Agent 不输出
`semantic_part_index`、`span_ref`、`slot_ref`、Word locator、object ref 或 content-control tag；Harness/App 的阻塞性闭包必须基于
`source_entry_id`、ordered parts、pre-input vocabulary、Harness-resolved
`span_ref` / `slot_ref` 和后续 materialization receipt。

若 Agent 明确判断整条 entry 承担同一种责任，可用唯一 part 的 `whole_entry: true` 代替 text；
它不得与 text、空白编码或其他 part 并存。Harness 按该显式声明取同一已绑定 entry 的完整原文，
保留 role／field_id，再经原有切点、范围、词表和执行检查。最终保存的接受结果使用展开后的
原文及常规 span／slot，不把声明交给 Word 执行器。未声明 whole_entry 的部分文字或单一 role
不得自动扩为全文；混合用途仍须分段。

post-unit closure gate 以 source entry span 为准。Harness 必须检查每个需要覆盖的
canonical source entry 都被 accepted semantic spans 覆盖，span 不能 missing、overlap 或引用未知
`source_entry_id`，且每个 accepted span 都能展开到内部 provenance。raw `object_id` /
`covered_object_ids` / locator 只能作为内部执行账本和负向测试材料，不再作为 Agent 输出合同或 source
coverage 主入口。

materialization 入口只消费 Harness-accepted review 中的 ordered parts 和 Harness-resolved
source-entry spans。执行层可以在内部把 span 展开成 raw `object_ref`、locator、fingerprint 或
paragraph/table target，但不得要求 Agent 输出 `reading_block_id` 才能执行新合同路径。写入 DOCX 前必须
fail closed：source DOCX hash、source entry provenance locator、object_ref document hash 和
fingerprint 账本都必须保持 current。同一 source entry 中解析到同一可执行段落的多个、不同字段
`body_structure` span 可以按 accepted part 顺序物化为行内复合接口；不同 source entry 共用载体、
同字段片段只有在删除已接受的 cleanup/style_only 文字后相邻，且属于同一 source entry、段落与
已接受单元时，才可合成一个物理填写接口。保留文字、其他字段、单元切点、不同来源或跨段落载体均阻止合并；
合并后仍有重复字段接口、重叠范围、跨载体或未支持的复合成员时继续阻塞。原 parts 和 resolved spans 不变，
接口以首段 span 为稳定锚点，完整记录所有贡献 span 及被删除的分隔 span，不把外包范围改判为字段。
含合并接口的产物使用嵌套 materialization provenance v2（Fill Contract 本身仍为 v2），显式声明
coalesced_body_slot_refs；生产端按原判断重新计算分组并核对执行/receipt，消费端重验全部贡献范围、分隔用途、
邻接关系和单元切点。普通单 span 产物继续用 provenance v1；v1 不得携带或掩盖合并接口。
表格内精确定位到单个段落的正文文字成员，在 Registry content_type 为 text/rich_text 时可在原段落
建立接口。不同单元格分别执行，保留表格/行/单元格结构、段落属性及同 entry 的固定文字；单个接口也不能
吞掉已判定保留的前后文字。不得将子段落定位扩大成整表，不得因表内存在文字接口而跳过其他已接受的清理。
表内的 table/equation 等非文字接口继续归 Tool 能力阻塞，整表接口与内部接口同时占用时也须阻塞，
不能自动改字段或把复合结构降为文字。单元格内不另包裹或移动原段落，保留末尾段落与表格布局。
当一个 cleanup-only entry 的所有已接受 Word fragments 精确引用同一个 VML shape 时，执行器可
只删除该 shape，并保留所在段落、兄弟对象及段落属性。运行时必须确认清理文字覆盖 shape 的完整可见文字；
不能从部分文字扩大删除范围。删除父段落会影响保留子对象、或同段还存在字段物化/文字重写时，继续阻塞。
其他未支持的图形载体不得自动套用此操作；不通过原文搜索或修改语义判断来选择删除对象。
初始清单中的 whole-entry picture 引用落到一个 run 时，仅在该 run 有唯一直接 drawing 子对象时
删除该 drawing；未知对象不能因为所在 run 含有图片就改按图片执行。
保留 run、其中的文字/属性及相邻对象。多个 drawing、嵌套而无唯一映射或不支持的对象类型由 Tool
停止。文字范围的 cleanup 只清理对应字符，即使清空段落也保留段落；整段或整表删除必须有直接引用
该容器的 whole-entry 范围，不能因文本为空、文字恰好覆盖全段或共用 run 而扩大授权。

组合检查按原对象子树及文字区间判定，不按“同属一段”判冲突。整段/整表删除与内部保留或填写义务、
重叠的文字清理/保留/填写范围属于语义冲突，返回全部关联源条目及原文供修订。整对象 fixed/manual
保留其内容；空白布局与正文表格接口保留其承载结构，允许明确的子内容清理。同范围重复清理可合并，
父对象删除覆盖的子清理不重复编辑已删除对象。原 Word 节点复核发现范围映射与静态检查不一致时，
Tool 停止，不能生成成功回执。每项 blocker 保留自身归责；存在工程阻塞时，整轮不进入语义重试。
只含 `fixed_label`、`manual_region`、`style_only`、`cleanup` 的混合 entry 可以作为一个保留的人工复合
载体编译；这不授权执行层把其中任何片段补成 Registry 字段。
当一个 entry 只有 `style_only` 与 `cleanup` 且包含样式说明时，沿用样式说明的精确文字清理路径：
保留原 accepted parts、来源证据、段落和段落属性，只清除已判定的文字。不把该组合升级成删除整个
载体，也不补出填写字段；固定内容或其他用途仍走各自的既有分类及范围检查。

局部文字清理、字段槽和正文文字接口共用源范围编辑：写入前绑定 accepted Word fragments 的原始文本
节点及字符范围，之后不重选段落内容或搜索相同原文。跨 run 修改保留各自样式，其他源条目的图形、域、
书签、结构与属性保持不变；人工混合区内已接受的 cleanup/style_only 仍须执行。无法确定性映射的嵌套
文字、域结果或内部显式断点由 Tool 停止，不扩大范围，也不要求 Agent 改变正确判断。

成功回执必须在实际效果核验后生成：检查清理义务、槽的实际存在与原始行内位置、保留对象及属性、
对象顺序和预期文字；临时 DOCX 写包后重读，核对修改部件与已验证树一致，其他部件字节不变，再提交。
执行授权直接从 accepted review 的每个原始 span 建立，不能由 intent 分类、执行器选择的容器或成功
receipt 反推。编译后的 span 集必须与原判断完全相等；文字编辑的字符锚点、必做义务、对象删除与字段
接口分别按原判断核验。执行器扩大文字范围、遗漏局部义务、交换两个接口的原位置或字段，即使所有
slot_ref 都存在，也必须失败。检查同时保护原对象的父子边界，禁止向允许修改的容器夹带新内容。
正文分组的无字段包装不改变语义范围；整表接口只包裹该原表，不能纳入相邻段落，表自身内容与属性
继续受保护。现有内容控件只有在原填写 span 覆盖完整可接管范围时才能复用；部分文字不能自动提升
为整个控件的字段，当前不支持的控件内局部编辑由 Tool 停止，不要求 Agent 改判断来绕过能力缺口。

`effect_verification` v3 绑定源稿、accepted review 与候选 SHA，记录原判断范围核验及重读已通过。
App 不复用缺少该记录或仍为 v1/v2 的旧物化缓存，须按原判断重新生成；发布入口拒绝缺失、旧版或绑定
不一致的验证记录。该记录是 Harness/Tool
执行账本，不增加 Agent 判断字段，不替代最终视觉检查及产品验收。

默认 source-entry 阅读行必须携带与不可变源文档绑定的 `layout_facts`（有事实时）：显式换页、换栏、
换行、段前分页与分节属性均由 Word 结构读取，不能只把这些对象表述为普通空白。该补充信息不改变原文、
源对象身份、分区或用途；同一段落内的多个源条目明确描述“所在段落”的事实，不能据此自动分配字段。
正文中的文字或学校名称不参与此类事实提取。渲染缓存分页不视为显式分页；无法取得的局部映射明确标为
布局信息不可用，不能声称没有断点。初始单元判断、post-unit 阅读包和修订上下文消费相同事实投影。
初始 document_map、单元阅读包和修订上下文须提供绑定原 Word 的物理包含关系：`structure_context`
分别列出祖先条目及后代条目的源 ID、类型与完整原文，明确“自身文字为空”不等于“整个容器为空”。
关系由现有 provenance 对应的实际 XML 祖先关系证明，不能按文字相同、学校标签或条目顺序推测。
关联文字仅为上下文，不并入当前条目的 text、判断范围或允许修订范围，也不能据此确定用途或字段。
投影不能泄露底层 locator/object_ref；无法解析的关系明确标记证据不可用，不猜测包含关系。
内部阅读包记录 `structure_evidence_version`；旧缓存缺少当前包含关系版本时停止恢复/提供给 Agent，
保留历史并重新准备 post-unit。补充关系事实本身不得改变 canonical 身份、文字或已接受分区。

同三个 Agent 阅读入口还须提供 `word_format`：源条目所属 Word story（正文、页眉、页脚等）、原段落样式名，以及原件确有的大纲级别、列表级别与编号格式。它们是从原 Word 和样式/编号定义解析的**格式事实**，不是 Agent 应提交的 role，也不能凭标题字样或学校用语推断。一个源条目跨多个原段落且事实不同时保留各个值，不假装只有一种格式；不可解析时明确标记。内部编号 ID、locator 和 object_ref 不出现在 Agent 可见投影中。内部阅读包以 `word_format_evidence_version` 防止旧缓存绕过该证据；旧缓存应保持历史并重新准备，不能静默把新事实塞进已经接受的判断。

内部阅读包记录 `layout_evidence_version`；旧缓存缺少当前布局证据版本时停止恢复/提供给 Agent，保留原历史并
要求重新准备 post-unit，不静默覆写原判断或把新证据加入旧会话后视为已重审。这个版本字段不交给产品 Agent。

文字重写不得顺带删除未进入可见原文的显式 Word 换页、换栏和换行节点。填写接口、正文接口与
保留段落的文字清理共享同一重写原语：原文首尾断点保留相对位置、节点属性和 run 样式；段落属性继续保留。
位于文字内部或嵌套载体内的断点，以及向仅含断点的空载体插入文字，在缺少输出边界映射时归 Tool 能力缺口，
在写出候选前停止，不要求 Agent
改变语义来绕过。`lastRenderedPageBreak` 是渲染缓存，不作为显式分页指令复制。

以下旧 Agent 输出字段不属于 runtime 可见合同，出现时必须 fail closed，不做兼容迁移：

```text
judgment_id
judgment / semantic_judgment
covered_unit_ids
covered_reading_block_ids
covered_reading_range_ids
covered_reading_spans
semantic_field / registry_field / registry_field_id
bound_field_id / bound_field_ids / required_field_ids
semantic_parts
toc_contract
generated_field_id
semantic_part_index
source_content_id / source_content_ids
source_object_id / source_object_ids / source_object_ref
source_entry_ref
```

runtime Agent-facing prompt、Skill、structured output schema、Tool feedback 和 Harness revision packet
不得要求产品 Agent 输出或修复以下内部账本概念：

```text
hash
candidate_hash
render_ref
object_ref
object_id
object_ids
covered_object_ids
target_ref
locator
coverage
publish
checkpoint_backend
task_root
stale_ref
fingerprint
```

这些内部概念可以存在于 Harness、Tool、App、trace、checkpoint receipt、publication receipt、Fill Contract、Eval 和
coding-agent 文档中。进入产品 Agent 前必须被投影或改写成 `field_id_vocabulary`、
`source_entry_id`、reading view 上下文、可见文本、缺失语义上下文或 `needs_input`。

模板提取不得把跨学校语义判断隐藏在确定性代码窄规则里。字段绑定、正文结构 variant、固定内容保留、
格式说明迁移、填写占位和视觉空格处理，必须由 Agent-facing 语义判断、schema、Registry affordance 或
accepted judgment 支撑。Harness / Tool / App 可以做机械校验和 DOCX 物化，但不能用单个模板 wording、
学校专属短语或模型自由文本片段替代 Agent/schema 的稳定合同。

目录单元不再有独立的旧 post-unit 输出形状。固定“目录”标题、空行说明、分支标签和格式说明仍按普通
`semantic_judgments[]` 覆盖；真正代表目录缓存或目录字段的片段必须是 scoped ordered part，
`role=generated_content`，并且只在 pre-input `field_id_vocabulary` 中已经存在目录字段时携带该
`field_id`。Harness 只校验这份有序拆分、输入词表来源、目录来源范围和层级自洽；它不替 Agent 从旧缓存、
标题词、编号外观或样式名选择目录字段或来源。

## 必需输出

成功发布后，`output/` 中对下游可见的产品主交付物只有两份：

```text
output/
├── final-template.docx
└── fill-contract.yaml
```

二者是原子产品单元；缺少任一文件、被覆盖写入、hash 不一致或契约不可解析都视为失败。

内部证据保留在 `work/.docfit/**`，包括 Agent execution trace、不可变候选、render/visual evidence、
validation receipt、`template-publication/fill-contract.yaml` 和
`template-publication/school-style-observations.json`。这些是审计材料，不是第三份产品交付物。

## Fill Contract 交接

`fill-contract.yaml` 是模板提取交给最终内容填写模块的稳定 handoff。下游可以依赖：

- `schema_version == docfit-template-fill-contract/v2`；
- `template_sha256` 绑定 `output/final-template.docx`；
- `field_registry_ref` 绑定本次 Registry identity/hash/version；
- `marker_protocol == docfit-content-control-marker/v1`；
- `slots[]` / `regions[]` 表达目标可填写接口；
- 每个 required slot 至少包含 `slot_ref`、`span_ref`、`field_id`、`content_type`、`required`、`locator` 和
  `style_contract_ref`；
- 每个 `slot_ref` 都是 Harness 根据 `span_ref + field_id` 机械序列化得到，且其 `provenance`
  能追到 pre-input `field_id_vocabulary`、accepted ordered part、Harness-resolved span 和
  materialization receipt；
- locator 在绑定的最终 Word hash 内可解析，且旧 snapshot ref 不可跨 hash 复用；
- `styles[]` 与 `style_contract_set_digest` 形成不可变 Style Contract Set；
- 学校样式观测、完整学校 candidates 和 `known_school_style_gaps` 只描述学校模板事实，不代表最终填写
  已选择任何兜底样式或补造值。

下游不得把相同 `field_id` 当作自动写入授权。具体 placement 仍必须显式连接 Student Content 的
`content_id` 与模板 `slot_ref` / `region_id`。

## 状态与退出语义

CLI 成功时返回 JSON report，`status == "built"`，退出码为 `0`。报告中的 `artifact_path` 和
`fill_contract_path` 指向已发布的两份主交付物。

失败或缺证据时退出码为 `2`，stderr 输出结构化 failure。常见语义：

- `needs_input`：输入、恢复目录、Agent 证据或用户确认不足，未发布新产物；
- `error`：后置条件、DOCX package、Registry/locator、样式观测、视觉绑定或 backend 失败；
- 已完成目录可恢复读取，但必须有当前架构 execution trace，且输出目录只能包含两份主交付物。

Fill Contract 内部的 `review.status` 可为 `machine_checked_pending_human_signoff`。这表示机器发布门已通过，
但学校 Gold / Human acceptance 仍由运行后 Eval 与人工审查决定；不能据此宣称 M3 或真实学校质量通过。

## 隐私边界

任务输入、学校要求、render 图片、trace、validation 和样式观测均继承当前任务授权边界。模板提取报告和
日志不得复制学生正文，因为模块本身不读取学生材料。Template Eval 报告也必须默认只输出定位、分数和
issue 摘要，不把学校或用户未授权正文扩散到公共 CI。

## 验收门

模块级验收由代码测试和运行后 Eval 共同约束：

- `docfit prepare-template` 只接受学校模板、可选学校要求、Registry 和输出目录；
- 源模板和 Registry 在任务中只读复制，运行期间 hash 不变；
- DOCX 与学校要求文本是 untrusted source data，不能影响权限、路径、Tool allowlist、
  Harness 配置、Subagent 类型或发布目标；
- Agent/Harness 交换结构必须版本化并通过 shape/closure 校验；
- Harness 对可由 Agent 修正的判断缺失、重叠和格式错误返回结构化修订反馈；源映射/快照故障、
  执行能力不支持不伪装成语义错误，不因这些工程失败要求 Agent 改变用途；
- 原文修订允许受影响条目的用途和合法字段改变，并重新检查；Harness 不将遗漏文字自动扩展到已有用途；
- 字段存在并不等于字段与用途兼容。局部提交、整体检查、诊断输出和已保存 review 的复用统一校验
  输入词表 `usage_affordance.allowed_part_roles`；不从字段名称或学校文字推断角色。
  不兼容组合在当前批次返回修订，保留提交用途及允许用途，允许同时重审字段与用途。
  词表角色元数据缺失、重复或损坏归 Harness 并停止，不要求 Agent 修复词表；不自动改写判断。
- 每批输出在记为有效候选前完成 shape、词表、范围和精确原文分段检查；局部原文检查与全局检查
  共用解析规则，只排除当前批次外尚未提交的条目。跨批次覆盖、冲突与执行组合仍须整体检查；
- 修订额度由 Harness 按稳定源条目及问题类别计数，并受整次任务调用量和时间上限约束；
  重复无进展、问题额度耗尽和总预算耗尽以工程停止报告，不伪装成学校资料缺失。
  策略及已耗预算随逐轮账本恢复，改用途、反馈码、扩大范围或重启不能重置已有问题计数；
- post-unit 的 `expand_revision` 只请求重新开放已有条目，提交 `revision_request.source_entry_ids` 与语义理由，
  不能同时提交判断；Harness 补齐上下文、留档并恢复待修订范围，相关批次完成后重新整体检查；
- 默认恢复须验证并复用已存在的单元边界 checkpoint，不能因未写 `--from` 就重跑已完成阶段；
- 修订请求、结构化响应（包括拒绝和 needs_input）、实际反馈、候选父版本及差异须在任务内留档；
  缺少历史、版本过期或记录写入失败不能静默继续。恢复候选仍须重新进行全局检查，回放证据不能冒充 runtime 历史；
- App 与直接物化入口均保留失败判断及归责；工程阻塞不进入语义重试，不写入或发布未经闭合的候选；
- Subagent 只能返回结构化 closure，受只读、深度、数量、并发、超时和预算限制；
- DocFit Tool surface 是版本化、分阶段能力面；模板 runtime Agent 只暴露语义取证工具，写入和发布
  由 Harness/App 消费 accepted judgments 后确定性执行，不保留旧 schema 兼容作为产品合同；
- 成功发布只产生 `final-template.docx + fill-contract.yaml` 两份主交付物；
- `final-template.docx` 可由 OfficeCLI 重开验证；
- Fill Contract v2 的 schema、Registry identity、template hash、slot locator 和
  `style_contract_set_digest` 自洽；
- 学校样式观测失败时 fail closed；已知学校样式缺口可发布为 gap，但不能静默补值；
- final render、全页 visual review 与 `docx_validate` 必须绑定同一最终 Word hash；
- 全页复核须使用 `docfit-final-visual-review/v1`：记录实际复核者、时间、当前源稿/候选渲染、
  每页完整图片及逐项观察结论；页码列表或空 findings 不能单独证明已完成复核。待复核、待确认、
  阻塞、漏页、证据损坏或旧版本复核均不得发布；正常完成、直接发布和已完成任务恢复均检查此合同；
- 宿主先准备原稿/最终候选的全页图片及 `work/.docfit/final-visual-review/current.json` 所指请求。
  默认没有自动视觉判断者；实际人工或外部视觉复核者按请求填写版本专属 `review.json` 后恢复。
  此步骤不是学校语义 Agent 的新记账任务，也不代替产品签收。LibreOffice 歧义未解决时保持待确认；
- 等待复核期间，已接受语义、源稿、词表与 Registry 未变时复用同一份物化候选；改变判断生成新候选，
  候选意外缺失/变化明确失败，不静默替换正在复核的文件。旧任务没有有效复核时不能复用完成状态；

- Template Extraction Eval 只在产物生成后读取 Actual 与 Gold，评分不能反向控制运行时语义。

推荐本 PR 的基础验证：

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

独立静态 Eval 的运行和 Gold 状态见 `evals/template-extraction/README.md`。
