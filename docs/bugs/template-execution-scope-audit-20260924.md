# 模板执行范围与结果核验审计 — 2026-09-24

状态：E1/E2 已实现并完成合同回归与限定真实回放；E3/E4 未实施，产品验收未完成。
下文保留原诊断基线，修复证据见文末，不以新结论覆盖原失败记录。
模块：模板提取；checkpoint：post-unit readiness → materialization → result verification。
代码基线：`1924c15`。执行计划沿用
[Harness 修复计划的本轮补充](../plans/template-harness-repair-20260923.md#2026-09-24-执行范围与结果核验修复计划待实施)。

## 产品结论

不能仅凭当前 materializer 返回 `ok` 或 `actual_result=preserved`，认定判断已被忠实落实。
本轮构造 DOCX 探针证明：局部文字清理和填写槽均可能删除同段独立保留对象；人工混合区的清理可能
完全不执行。这些问题已在实际 DOCX 写入中复现，但输入是构造合同用例，不能声称真实学校已经发生误删。

真实 NJAU 原任务在写入前停止，没有证据证明该任务已经误删或发布错误产物。其两个图片清理 intent
都把目标 run 扩为所在段落；底层共有三组清理冲突，反馈去重后只保留两组。

统一 source ID 的已有验证保留。问题发生在正确源范围之后的操作推导、执行组合、结果检查与反馈投影，
不以此重新宣称整项身份迁移失败，也不据此新建坐标系统。

## 证据与复现

- 原真实任务：`temp/harness-repair-20260923/phase5-three-schools/njau-boundary-diagnostics-task/`。
- 本轮输出：`temp/template-execution-audit-20260924-final/audit.json`。
- 可重跑入口：[audit.py](../../tests/manual-diagnostics/template-execution-audit/audit.py)；命令见同目录 README。
- 原任务源 SHA：`d87b1a4b17f7162590cde28f8871c210f11f3476a8ebcf3b0bd3767a4bd34b6e`。
- 读取并验证初始清单、分区、Registry、211 条原始判断及其 resolved spans，原七项输入/证据文件 hash 不变。
- 构造探针复用现有 `test_shape_cleanup_materialization._case`，显式编写诊断判断；不 monkeypatch、
  不跳过 readiness，调用正式 `materialize_template_from_semantics` 并重读输出 XML。
- 诊断没有调用 Agent，没有发布或恢复旧任务，也没有读取 Gold。

原任务属于旧阅读上下文，当前 App 已要求新增的结构关系证据；本轮直接回放确定性检查和目标解析，
不冒充当前公开 CLI 能恢复这份旧上下文。后续 Agent 验证必须从当前代码重新准备输入，不迁移旧 ID。

## 已证实的问题

### F1：普通图片清理仍把源对象扩大为段落（P1，Tool）

两个原始图片条目：

| source entry 后缀 | 已接受的 Word 对象 | 实际选择的删除对象 |
| --- | --- | --- |
| `779d09452b5c02ad0b871941` | `/body/tbl[1]/tr[1]/tc[1]/p[1]/r[1]`，含 drawing 的 run | 所在 `p[1]` |
| `741bd7ca7aa2e4c4e09bec91` | `/body/tbl[1]/tr[1]/tc[1]/p[2]/r[1]`，含 drawing 的 run | 所在 `p[2]` |

两个段落本身被判断为保留空白布局的 `style_only`。当前 `_cleanup_carrier_for_intent` 只为 VML
shape 保留精确对象路径，其余只要有一个段落就选择整段。空字符串覆盖检查无法证明空段里的非文字
对象、布局和属性都已授权删除；本案被冲突检查拦截。

代码：`materialization/runtime.py:473–504`、`handlers/cleanup.py:30`。
层级：**real replay / 目标解析与 readiness**，没有执行两个被阻塞的删除。
语义限制：图片是否应删仍须根据新阅读上下文重新判断；工程能力缺口不证明原删除判断正确。

### F2：局部修改重建整段，删除独立保留对象；回执仍声称保留（P1，Tool + 结果验证）

同一构造段落中有独立文字 entry 和两个明确 `fixed_label` 的 VML shape entries。

| 探针 | 文字判断 | 实际结果 |
| --- | --- | --- |
| `fixed` | `same` 保留，` text` 清理 | readiness 通过；两个保留 shape 从 2 变 0；结果 `ok` |
| `slot` | `same` 保留，` text` 建题目槽 | readiness 通过；两个保留 shape 从 2 变 0；结果 `ok` |

`_rewrite_non_slot_intent` 把当前 entry 的剩余文字重建成一个 run；填写槽也调用相同的
`replace_paragraph_content`。该 helper 保留段落属性和部分断点，但替换所有其他段落子节点。
当前冲突检查主要围绕 `DELETE_BLOCK`，未完整覆盖这种重写对其他 intent 的影响。

随后 `_preservation_policy_receipts` 仅根据 intent 类型及该判断是否出现在 cleanup 列表，写入
`actual_result=preserved`。它没有据实际产物检查 shape 是否仍存在。本轮两个探针均为已经删除的
shape 生成保留回执。写包阶段的 package validation 仍通过；XML 合法不等于范围正确。

代码：`runtime.py:524–540,685–716,782–795`、`paragraph_rewrite.py:26–73`、
`handlers/slots.py:47–117`、`executor.py:53`。
层级：**logic/contract，构造 DOCX + 正式物化 + 输出 XML 复读**。
未证明：真实学校该类误删、通过 App 最终视觉门或错误产物已发布。未测试的书签、域、run 样式等
同段内容列为修复时必须检查的受影响路径，不作为已发生缺陷计数。

### F3：人工混合区接受了 cleanup，但执行时完全遗漏（P1，compiler/Tool）

`manual` 探针把同一 entry 的 `same` 判为 `manual_region`，` text` 判为 `cleanup`。
compiler 将整条分派为 `KEEP_MANUAL_TABLE_CELL`，runtime 没有执行其 cleanup parts 的分支；
只生成 `keep_as_single_manual_carrier` policy。

输出仍是 `same text`，`cleanup_count=0`，返回 `ok`。这证明“保留人工承载结构”在执行中吞掉了
“删除其中已判断文字”的独立义务。不能通过整条改判或静默保留说明来掩盖。

代码：`compiler.py:626–634`、`runtime.py:760–795`、`handlers/table_manual_cells.py:28–51`。
层级：**logic/contract，构造输入**；未声称真实 NJAU 含有此组合并已输出残留。

### F4：不同冲突在反馈去重中丢失（P1，Harness）

原 NJAU 的三组冲突分别是：

1. `/body/tbl[1]` 整表删除与表内固定文字/槽/布局保留；
2. `/body/tbl[1]/tr[1]/tc[1]/p[1]` 第一张图片删除扩大到保留段落；
3. `/body/tbl[1]/tr[1]/tc[1]/p[2]` 第二张图片删除扩大到保留段落。

第一组与第二组按原判断顺序都以 `semantic_judgments[0]` 为第一引用。
`_plan_readiness_blockers` 只取第一个 judgment ref；`_append_unique_blockers` 以
`code + first judgment ref + missing_requirement` 去重，第二组因此被丢弃。
第一张图片的 source entry 不在任何最终 cleanup blocker 的 affected entries 中。

因此当前反馈是 **7 个页脚载体问题 + 2 个清理冲突 = 9 个 blocker**；计划层清理冲突实际是 **3 组**。
若只修正当前去重投影且其它判定不变，反馈应有 **10 项**。这不是 10 个独立根因，也不是新增学校输入。
`04ff044` 修正了终态摘要只显示前五条的问题，未修本轮发现的更早一级去重遗漏。

代码：`readiness.py:330–386,795–809`。
层级：**real replay**，原输入和判断未修改。当前样本仍被其他 blocker 阻止，未证明因此错误放行。

### F5：冲突归责未区分原判断矛盾和执行范围扩大（P2，Harness 合同/路由）

上述整表 intent 精确选择 `/body/tbl[1]`，并非执行器误把子段落选成表。
原判断理由称它是“空表、说明区样例”，却与表内固定标题及姓名/学号等填写槽判断共存。
旧 reading packet 把表与两张图片放在 `unit-spec-instructions`，只显示各自空文本，没有现在的
包含关系。已知输入顺序/上下文缺陷与这一原判断有关，不能简单归咎为 Agent 忽略事实。

在当前删除整表的操作语义下，这与保留表内内容不能同时兑现；与“删图片、保留段落”可同时兑现
但工具做不到，是两类问题。当前 `materialization_cleanup_carrier_conflict` 一律进入
`execution_unsupported / tool / stop`，无法给出这个区别。

修复需基于已接受范围、明确操作效果及真实包含关系建立区别。不得仅按相同 carrier、错误码或
Agent reason 关键词猜归责；也不得暗自将删除表变为解包表、移动子内容。
层级：**real replay + 代码审计**，尚未运行新 Agent 证明整表冲突已修订。

## 已知的独立问题与证据边界

- **页脚误绑定**：7 个真实判断明确知道对象是 footer，仍选择 `body.paragraph`，其中一条还声称
  渲染器会替换成 PAGE 域。Registry 对该字段的含义是“普通正文段落流”；当前 generated 字段只有
  TOC、图目录、表目录，没有专用页码字段。现有 generated handler 记录填充后刷新既有域的策略，
  不能证明能将这些静态数字建成 PAGE 域。不能通过支持“页脚正文槽”让错误语义通过。
  缺正确字段或生成能力时，应明确保留未解决责任；不把静态数字简单保留就宣称页码生成已完成。
- **已修输入事实**：`7df1192` 增加实际 Word 顺序，`aefe343` 增加包含关系。需要以当前新任务检查
  它们是否帮助 Agent 改正；不能拿旧 packet 的缺陷认定新实现仍未修，也不能以投影通过代替新判断。
- **已有 VML 精确删除**：旧 `shape-cleanup-replay` 成功仅证明指定 VML shape 的 Tool 切片。
  与本轮 drawing-run 清理、同段重写保留义务是不同路径，不重复声称该修复无效。
- **PKU 新任务**：本轮可见目录尚无最终 semantic judgments、materialization 或 output 文件。
  未查询实时运行句柄，不从文件缺失推断“仍运行”或“已失败”，不计新增成功。

## 本轮验证范围

| 层级 | 本轮完成 | 未完成 |
| --- | --- | --- |
| logic/contract | 三个构造 DOCX 探针复现 F2/F3；正式物化和重读产物，无 monkeypatch | 修复后回归、全部操作类别 |
| real replay | NJAU 211 条原判断绑定核验；三组冲突、两张图片目标扩大、反馈遗漏 | 原学校完整物化；当前新准备输入的 Agent 判断 |
| E2E agent loop | 无新增 | 本轮全部 |
| product acceptance | 无新增 | 最终 Word、Fill Contract、视觉及人工签收 |

此轮仅增加诊断脚本、问题记录及计划。没有修改产品代码、Skill、Registry、原任务或既有学校 DOCX。

## E1 修复记录 — 2026-09-24

F2/F3 的共同执行缺陷已修复。文字清理、字段槽、正文接口先绑定原始文本节点与字符范围，再统一执行；
不再把一个 entry 的文字当作整个段落重建。人工混合区也执行 cleanup/style_only，整表接口内的独立
文字清理不再被表接口分支吞掉。run 样式、独立图形、书签、域、段落/表格属性保留。

独立结果检查验证原范围的文本、行内位置、保留子树/属性/顺序、预期槽与删除义务；写包后重读再提交。
回执记录与源稿、原判断、候选 SHA 绑定的 effects proof，App 重建没有 proof 的旧缓存，发布拒绝缺失
或失配的 proof。必须跨 Tool、App 与发布边界接入，才能避免旧成功回执绕过新的结果检查；未改 Agent
语义合同、提示词、Skill 或 Registry。

| 层级 | E1 结果 | 边界 |
| --- | --- | --- |
| logic/contract | 原 fixed/cleanup、slot、manual/cleanup 三例先失败后通过；保留两个同文字 VML 图形；跨 run 样式、重复文字、域、书签及现有断点/story/表内回归通过 | 构造 DOCX，不代表真实学校发生过这些误删 |
| logic/contract 故障注入 | 跳过 handler 并伪造成功清理、跳过编辑、删保留图形、移动槽、篡改序列化输出均拒绝成功；缺失/失配 proof 拒绝发布 | monkeypatch 检查，不是 Agent 回放 |
| real replay | 原 NJAU cover task 全部判断经正式物化：10 个操作、1 个清理记录、10 个文字编辑、86 个保留子树，写包复读通过 | 只验证该历史输入的物化，不重新运行学校语义判断 |
| real replay 执行切片 | NJAU 17 个正文片段形成 8 个接口，167 个其他段落不变；HUNAU 76 个表内接口，508 个其他段落与表/行/单元格拓扑不变 | 保留原整校 blockers，不视为整校物化通过 |
| E2E agent loop / product acceptance | 本轮未执行 | E2/E3 尚未解决，不能声称整校闭环或最终产品验收完成 |

真实回放产物位于 `temp/e1-scope-repair-20260924/` 的 `njau-cover-final/`、`njau-body-final/`、
`hunau-nested-final/`，各自 `replay.json` 保留输入 hash。三个原任务与原判断未修改。

未支持的被选文字位于嵌套 wrapper、域结果或存在无法确定输出位置的显式断点时，工具在成功写入前停止。
未被选择的这些对象继续原样保留；这不是全体 OOXML 编辑能力验收。E2 图片范围扩大、E3 反馈丢失及
新 Agent 对语义冲突的修订仍保持原状态。

回归记录：`tests/contract` 全量 **1029 passed**；随后新增的 5 个发布 proof 拒绝场景与聚焦回归共
**61 passed**；`mypy src`（131 个源文件）与本次变更 Ruff 均通过。首次扩大到 contract + integration
得到 1102 passed / 6 failed：其中 4 个是发布合同 fixture 缺新增 proof，已修正并回归；1 个是相同原因的
M1 发布集成 fixture，已更新，但复跑因测试收集时 Docker inspect 5 秒超时而未完成；另 1 个是学生内容
模块的既有 provenance 缺失，已用 `git archive b25390d src` 的修改前代码单独复现，未改该模块。
不能将本轮记录表述为全仓或全部集成测试通过。后期系统盘临时空间耗尽，后续 `TMPDIR` 切到外置盘的
本轮产物目录；未清除用户数据或调整渲染器配置。

## E2 修复记录 — 2026-09-26

F1 的 drawing-run → paragraph 扩大已修复。检查与执行共同按 accepted fragments 区分文字范围和
对象范围；初始清单中 picture 对象对应的 run 只删除唯一直接 drawing，保留 run 的其他内容。含两张 drawing 或无唯一映射
时停止，不能选第一张或删除祖先。VML 精确 shape 删除沿用；独立文字清理、填写槽、正文接口可与同段
图片清理组合执行，不再因共用段落误报冲突。

纯文字 cleanup 使用 E1 的精确编辑，清空文字也不再隐式删除段落；直接 whole-entry 段落/表格仍可
删除。相应旧测试的“删除段落”预期已改为“文字删除、段落保留”，新增显式整段删除和父子重复清理的
正例，未把范围缩小后的返回成功冒充旧的段落删除效果。最终版式仍需视觉与产品验收。

F5 的原整表冲突已区分：删除表与保留表内标题/槽/布局不能同时成立，返回
`materialization_semantic_scope_conflict`，附全部关联源 ID 与原文，归 Agent 修订。无法唯一执行的对象
归 Tool。检查扩展到重叠文字、填写范围和整对象保留义务；写入前另按实际节点复核，防止不同 locator
写法绕过范围保护。混合反馈保留每项 recovery，任何工程阻塞仍让整轮停止。Agent schema、Skill 和
学校字段语义未变，未声称新 Agent 已作正确修订。

执行 proof 升至 v2，旧 v1 候选须重新物化后才可复用/发布，避免恢复绕过新删除范围规则；不修改已保存
原判断或历史回放。E3 的反馈去重机制未改，不能因该样本只剩一组冲突就认定去重问题已解决。

验证证据：

- `logic/contract`：图片与保留文字/槽/文字清理共 run；同名相邻图片；多图歧义；显式父子删除；整表与
  子保留/子修改冲突；混合归责；错误 handler 删除父段落；locator 别名下实际节点重叠；旧 proof 拒绝。
  故障注入属于构造测试，不是 Agent replay。
- `real replay`：原 NJAU 211 条判断不变。原两张图片执行切片只删除对应 drawing，整棵 Word XML 与
  独立预期一致，保留 run、段落属性、相邻对象及表格；写包后重读、未改包部件及七项原证据 hash 均通过。
  证据：`temp/e2-scope-repair-20260926/njau-pictures-final/replay.json`。
- `real replay`：完整原 review 仍阻塞，反馈从基线 9 项变为 **7 项页脚载体问题 + 1 组整表语义冲突**。
  页脚错误字段绑定的原诊断保留，当前反馈仍沿用 Tool 能力阻塞归类，E2 未修该独立问题。
  两个原图片问题因精确删除能力修复而消失，不是去重丢失；两个原 source ID 均在执行切片回执中。
  `njau-audit/audit.json` 保存新审计，原基线报告未覆盖。
- `real replay`：NJAU cover 正式物化回放仍为 10 操作 / 1 清理记录 / 10 文字编辑 / 86 个保留子树；
  候选 SHA 与 E1 回放相同，新增 v2 proof。证据：`njau-cover-final/replay.json`。
- `E2E agent loop` / `product acceptance`：本轮未运行或签收。M1 发布集成复跑仍在收集阶段因
  Docker inspect 5 秒超时阻断；不计集成通过，未通过修改环境探测或 fixture 绕过该失败。

最终代码检查：`uv run pytest -q tests/contract --tb=short` **1050 passed**；`uv run mypy src`
（131 个源文件）与本次变更 Ruff、`git diff --check` 通过。上述 real replay 与合同回归分别记账，
没有把 Docker 阻断的集成测试计入通过数。

## 2026-09-26：原判断范围作为执行与验收依据

用户要求先解决“Agent 判断的对象及范围，与实际修改没有始终对齐”。本轮继续处理 post-unit
物化 Tool 的共同范围机制，不改 Agent 判断格式、学校语义、Registry 字段或 source ID。

### 新证据与归因

在 E2 基线上，构造故障注入证实以下错误可得到成功候选：删除目标推导把图片换成父段落；编译结果
及其 payload 同时漏掉 cleanup span；执行时扩大文字字符锚点；生成接口带错误字段 alias。
一个未注入故障的构造输入还证明：原控件 `KeepValue` 的 `Value` 被判为填写区，工具会将整个控件
接管成字段，连带把 `Keep` 纳入填写边界。仅检查 source ID、slot 存在、成功 receipt 不能发现这些错误。

共同原因是验收权限和必做义务仍从执行计划、执行目标和编辑器请求生成。E1/E2 对各自案例的成功
证据保留；这些新证据说明不能用它们证明所有内部转换均保持范围。

### 修复机制与分支覆盖

`AcceptedEffects` 直接读取 accepted review 的原 spans 与原 Word，固定文字字符锚点、对象删除、
必做编辑及字段位置。它不消费 handler 返回的目标，也不从 intent 类型生成权限。编译结果必须完整
保留原 span 集；执行编辑器使用相同源输入，但检查持有独立绑定，并将字符锚点与原 fragment offsets
再核对。成功前逐项对照原义务及实际 Word 树，重读包之后才写入成功结果。

| 分支 | 约束与验证 |
| --- | --- |
| fixed/manual/generated/no-op | 未授权内容受保护；混合 cleanup/style 仍有逐 span 必做义务 |
| 文字 cleanup/style | 只删除原字符；映射或执行时扩大范围、遗漏编辑、插入内容均拒绝 |
| 图片/shape/整段/整表删除 | 删除集合从原 extent 生成；执行选择父容器不能扩大检查权限 |
| 新文字槽、正文文字接口与合并接口 | 核对原行内位置、slot_ref 与 field_id；两个接口齐全但互换绑定仍拒绝 |
| 现有内容控件 | 只有完整可接管范围可复用；部分控件内文字目前由 Tool 明确报能力不足，不提升为整控件 |
| 整表正文接口 | 包装内容必须恰为原表，原表内容和属性受保护；不允许吸收相邻保留段落 |
| 结构与写包 | 原父子边界、范围外新内容及未选择包部件受检查；失败不替换已有候选 |
| 恢复与发布 | proof 升为 v3；v1/v2 均不能直接复用或发布，须按原判断重新生成 |

顺带修正了一个相关误拦：没有文字修改的整表接口原先会因整棵父树被快照为“不得改变”而失败。
现在仅允许包裹该表，仍保护表自身子树，不将表或父容器整体列为可修改。

### 验证层级

- `logic/contract`：新增 `test_materialization_scope_authority.py` 12 项，包含上述故障注入、部分
  控件拒绝、范围外新段落、保留对象被搬入字段、整表合法包装/扩大包装、两个字段交换位置及旧候选
  不被失败覆盖。原 E1/E2 文字、图片、样式和单元格回归继续通过。恢复和发布分别拒绝旧 v1/v2 proof。
- `real replay`：`temp/scope-authority-20260926/njau-cover-final/replay.json` 使用原封面全部判断
  经正式入口，10 操作、1 清理记录、10 文字编辑、86 保留子树；候选 SHA
  `0c5ed6aa3995d137f194abc65879afb5505bd4669e8fabd790aa0dfe8137033e` 与 E1/E2 一致，proof 为 v3。
- `real replay` 执行切片：同目录 `njau-pictures-final/replay.json` 只删除原两张图片，整树与独立
  预期一致；`njau-body-final/replay.json` 的 17 个正文 span 形成 8 个接口、167 个其他段落保持；
  `hunau-nested-final/replay.json` 的 76 个表内接口、508 个其他段落及表/行/单元格拓扑保持。
  三个脚本均实际调用新增授权检查、重读写包，并保留原有独立检查。原输入、清单和判断 hash 不变。
- `E2E agent loop`：本轮未运行。原整校的页脚绑定和父表/子内容语义矛盾仍保留，不改判断制造通过。
- `product acceptance`：未完成，不以本次执行机制修复代替学校语义、视觉与最终产物签收。

新增控件内局部编辑的能力阻塞属于 Tool；范围问题不会转交 Agent 改写正确判断来规避。E3 反馈去重及
原学校语义错误仍是独立问题，本轮没有扩大处理范围。

最终检查：`uv run pytest -q tests/contract --tb=short` **1063 passed**；`uv run mypy src`
**132 个源文件通过**，本次文件 Ruff 与 `git diff --check` 通过。未运行的 Agent/E2E 或发布集成不计入。

### 交付状态纠正

用户指出：任务要求按原 source ID/span 正确完成修改，将越界改为失败不是交付完成。
接受该纠正：`02bc6f1` 的保护机制、合同测试与四组真实回放证据仍有效，但整体执行问题保持未完成。
当前控件内局部填写仍被拒绝，须补齐原范围树编辑和对应正向产物验证；不能继续把该拒绝本身称为
解决方案。具体实施纳入既有[修复计划](../plans/template-harness-repair-20260923.md#2026-09-27当前归因修复边界与推进顺序)。

2026-09-27 增补归因证据：40 组构造承载结构对照及复跑结果一致，全部 source span 映射和 readiness
通过，实际 20 组完成、20 组失败。单 run/段落内跨 run 正常；控件内局部填写、清理、人工混合区清理
失败，整控件填写正常；超链接内四类操作均失败。换原文不改变结果。共同文字能力限制、整控件分派
和就绪依据不足分别有代码路径支持；图片对象删除不能据此归为同源。此处是 logic/contract 诊断，
不是新增学校 replay 或完成声明。结果与可重跑入口见当前修复计划。

## 2026-09-28：承载结构首次偏离与正向修复

固定相同的原文分段、用途与字段，只改变普通 run、跨 run、行内控件、嵌套控件、超链接承载。
40 组构造输入在 Harness span 解析、compiler intent 和 readiness 均保持原判断；基线 20 组
执行失败。红灯合同测试与代码路径确定两处首次偏离：

| 原判断与承载 | 首次偏离 | 责任层 | 修复后效果 |
| --- | --- | --- | --- |
| 控件内局部文字为填写槽 | `AcceptedEffects` 曾把控件祖先当作整控件接管目标，拒绝局部 span | Tool 效果授权与分派 | 仅完整覆盖控件时复用；局部在原控件内建立字段，固定字与控件属性保留 |
| 控件内局部清理、超链接内填写/清理 | `TextEdits.bind` 曾要求 run 直接属于段落，无法绑定原字符 | Tool 文字绑定与编辑 | 按原 run 的直接容器编辑，保留控件/链接边界，候选写出并重读 |
| 同段普通 run 与超链接同时修改 | 旧绑定限制使链接内修改失败 | Tool 文字编辑组合 | 普通 run 清理与链接内字段同时兑现，段落外字保留 |

这里的 `readiness` 基线误报是检查与执行能力不一致的附带缺口，不是正向任务失败的全部原因。
修复优先补足执行能力，未把合法判断改写成错误或让 Agent 避开控件。一次跨 readiness、App 与
恢复的通用预检尝试造成既有合同退步，已撤回；当前代码只修改 Tool 物化与对应合同测试。

验证层级：

- `logic/contract`：同一 40 组构造探针从 20/40 提升到 40/40；新增局部控件、嵌套控件、
  超链接及同段混合修改正向合同测试。输出均重读核对原文/字段/保留边界。三份代表性
  候选（行内控件、嵌套控件、超链接局部填写）另经 OfficeCLI OpenXML schema 校验通过；
  这不等于 Word 版式或实际填写验收。
- `real replay`：NJAU cover 的全部原判断重新物化，10 操作、1 清理、10 文字编辑、86 个受保护
  子树；NJAU 正文切片 20 个接口与 155 个其他段落、HUNAU 表内切片 76 个接口与 508 个其他段落
  均通过原范围与写包复读检查。原输入和判断 hash 不变。这些真实判断未选择行内控件或超链接
  内局部文字，故只证明相关既有路径未退步，不能充当新能力的真实回放。
- `E2E agent loop`、`product acceptance`：尚未验证本次能力；旧 NJAU 整校仍有整表语义冲突与
  页脚字段问题，不能通过本修复直接发布可用模板。

诊断结果：`temp/flow-diagnosis-20260928/`、`temp/flow-diagnosis-after-edit-20260928/`；
真实回放：`temp/nested-carrier-repair-20260928/`。HTML 仅展示原判断、各层转换与 DOCX 结果，
基线失败位置和修复后路径可在 Codex 浏览器中切换查看。
