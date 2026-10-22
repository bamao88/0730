# Harness 修复执行证据（2026-09-23）

计划：[分阶段修复](../../plans/template-harness-repair-20260923.md)。
当前：阶段 0—3 已有分层实现与验证证据；阶段 4 已取得真实完整 NJAU 候选的全页复核及阻塞证据，
正向发布仍未完成；阶段 5 尚无本轮完整学校交付与产品验收。
`4bde3e0` 的 PKU / HUNAU / NJAU 均已终止并核对输入、runtime、Skill 摘要一致。HUNAU 完成 15 批判断后
因执行检查停止，输出为空。隔离 NJAU `cbefb17` 完成 13 批判断、物化和渲染，停在最终复核；实际查看全部
12 页后发现摘要合页、正文页码缺失和说明残留，复核为 blocked，未发布。
所有上述运行已终止，冻结已解除。主分支已合入连续正文接口 `9a4b28c`、交接测试 `ac6abfa`、
混合样式清理 `77a2119` 和显式断点保留 `0e1f774`。原有无关修改的二进制 diff 摘要保持一致。
断点修复的中间真实候选恢复摘要分开及 I/II 页码，但暴露空分页/分节载体被插入正文接口后多出一页；
最终实现对这类缺少插入侧映射的情况停止。两轮 NJAU 原判断在最终版本回放均准确阻塞，不能宣称完整物化通过。

当前证据索引：`temp/harness-repair-20260923/acceptance-evidence/audit.json`。最新索引已替换过时的
“性能未合入”“字段用途自然闭环待补”等状态，保留历史测试的版本和层级；未把新旧测试数相加，
也未把准确停止、合成视觉证据或局部回放算作完整发布。完整产品验收仍为未完成。

## 阶段 0 基线

代码基线 `5ba6a29`；已有 Skill、测试及 DOCX 工作区修改保持原样，不纳入本轮提交。
运行 `PYTHONPATH=. uv run python temp/harness-repair-20260923/baseline.py`，结果在同目录 `baseline.json`。
该脚本用于修复前取证，引用旧 API；后续回归由阶段测试承接，不能要求修复后的代码继续保留旧 API。

| 项目 | 基线证据 | 修复应证明 | 验证入口 / 层级 |
| --- | --- | --- | --- |
| A 自动扩展用途 | 构造判断“姓名：”固定标签被自动扩成“姓名：张三”固定标签 | 未判断的实质文字不能自动继承角色 | baseline probe A；阶段 1 contract + 原始候选 replay |
| B 执行不支持要求改语义 | readiness / batch prompt 明确要求内部表格字段改非字段角色；真实降级影响未确认 | 执行能力缺口保留判断、停止执行；语义错误仍可修订 | 阶段 1 readiness 路由测试；真实表格 / 混合载体 replay |
| C 修订基线缺失 | 构造修订 prompt 要求 prior role，但没有旧 role/text | 空白新会话收到可独立理解的修订材料 | baseline probe C；阶段 2 contract + E2E |
| D 检查延迟 / 预算牵连 | 批次先落盘，汇总才检查原文；局部失败累加全局计数 | 局部当批检查，独立预算仍受总上限约束 | 阶段 3 多批次模拟时序断言 + 真实多批次 E2E |
| E 原因丢失 | 定位失败消息被转换成泛泛的 revised semantic_judgment | 保留故障原因和责任，不把工程故障送去重判 | baseline probe E；阶段 2 sanitizer / routing contract |
| F 未实际视觉检查 | mocked 客观验证后 `_validate_host_candidate` 返回未请求复核、空页面记录 | 当前最终候选无实际全页复核不得发布 | baseline probe F 仅 logic/contract；阶段 4 真候选 replay + 发布测试 |
| G 用途锁 / 记录缺口 | 已有测试强制拒绝用途变化；原始摘要最后七次拒绝输出未保存 | 允许受影响用途重判并重检；每次提交和实际反馈可追溯 | 阶段 1 用途变化测试；阶段 2 账本 / 恢复 / E2E |

真实回放根目录：`temp/span-skill-e2e-20260922-87710163/body-task`。
使用其真实 input、inventory、unit proof 和 ledger，经当前 manifest 构建、ledger digest 校验、空白解码、源范围解析。
没有调用 Agent、没有写回旧 task、没有人工修改判断。

- 源 SHA-256：`4eb1b296b01997fb6be9d930f6fbf13f45081edbea7cdd678f5577159dc4fdbc`。
- 候选账本 SHA-256：`a534bce5ad37f6bb5a729a1e9360d12841ea4c5403ec2b3d3e4fc65116877ec6`。
- 原始 71 条判断仍返回 12 个源文范围 blocker，与既有事故记录一致。
- 这属于 **real replay 的失败复现**，不属于通过、更不是本轮 E2E。
- 最后七次被拒绝的完整输出缺失，保持缺证据，不重建假历史。

三校完整输入已只从 `00-inputs/schools` 冻结到 `temp/harness-repair-20260923/inputs/<school>/school-template.docx`；
未读取 Gold 模板或最终答案。Registry 使用当前 0.5 快照，SHA-256 为
`e139059b03883d5fbb07ebc1a35d5dffac654fad7241a61d520d7ecd4dac7ffd`。

| 学校 | 冻结源 SHA-256 |
| --- | --- |
| HUNAU | `30290bad5ff0b0843ee752ce3371da7d4ce615c4b24f2a1e8f07ab9c362760c5` |
| NJAU | `d87b1a4b17f7162590cde28f8871c210f11f3476a8ebcf3b0bd3767a4bd34b6e` |
| PKU | `e27cabb7771f15526488536dc4d06251e0efcd827cad6faeb400b7a017b84375` |

内部失败合同按可修订判断、学校证据缺失、执行能力不支持、系统映射/状态故障、环境故障、预算耗尽分流。
只有可修订判断返回 Agent；其它问题保留判断并交对应工程层或真实输入提供者处理。
后续 open questions 是否阻塞按当前 checkpoint 的完成条件判断，不能一概升级为当前失败。

## 阶段 1：判断安全边界

删除按统一用途自动补全文字的实现和 exact-text 用途锁；受影响条目可重新分类、选择合法字段，
仍需经过原范围/词表/整体检查。删除为适应 Word 承载而要求改变用途的批次提示。
readiness 统一区分可修订判断、Tool 执行能力阻塞和 Harness 状态故障；未知执行错误默认停止。
App 和直接 materializer 共享失败构造。工程阻塞保留原候选，记录内部问题，不生成 Agent 修订包，
不消耗语义反馈次数，不写候选或发布。没有扩展 Word 能力，也没有修改 Skill 或学校语义规则。

验证：

- 相关批次、运行时、readiness、materializer、compiler、plan 用例 180 项；末轮 179 项通过，
  另 1 项残留旧 `needs_input` 预期修正后单独复测通过。全部为 `logic/contract`，SDK loop 使用 mock。
- Agent 边界与文档合同 22 项通过；相关 Ruff、严格 mypy（116 个源文件）、diff check 通过。
- `tests/manual-diagnostics/template-harness-repair/replay.py` 使用两个原始真实 task 回放，结果在
  `temp/harness-repair-20260923/phase1-replay/replay.json`。真实正文 71 条判断仍报告 12 个范围问题，
  没有被自动扩展或接受。PKU 原整表字段判断准确返回 `execution_unsupported` / `tool`，
  直接物化在写入前停止；原判断及全部监测的输入/账本 JSON hash 不变。
- 另外对真实候选注入一次用途变化，候选接收允许变化，范围检查仍保留 12 项错误。
  这是明确标记的 contract 故障注入，不是新 Agent 输出或学校语义正确性的证明。

限制：真实原候选中的语义和文字错误尚未由新 Agent 修复；PKU 不支持的整表填写操作也未新增实现。
这些失败保留，不把“正确阻塞”当作生成成功。下一阶段补完整修订上下文、逐次候选/反馈持久化和恢复。

## 阶段 2 进展：修订上下文

新修订请求已经附带完整受影响源文、相邻源条目、关联冲突条目、旧候选判断、单元布局上下文和输入词表。
局部 shape 重试另外提供上一份被拒绝提交，与账本保留的候选分开。内容只经过既有 Agent-visible 投影，
不把底层位置或候选账本标识交给 Agent。缺少必要源文或旧判断时以 Harness 错误停止，不让新会话猜基线。

验证：runtime 合同组 59 项通过；新增上下文及边界组 14 项通过；新增真实调用点断言单独复测通过。
这些是 `logic/contract` / mock loop。真实原始正文候选生成了修订包，所有附带源文逐字与真实 inventory 一致，
旧候选判断完整存在，原 task 不变；证据为 `temp/harness-repair-20260923/phase2-context-replay/`。
这是 `real replay` 的上下文构造证明，没有调用新 Agent。相关 Ruff、mypy（117 源文件）通过。

上述上下文工作单独完成时，阶段 2 尚未完成；逐次提交、版本恢复、范围扩展、反馈和真实 Agent 闭环需分别留证。

## 阶段 2 进展：逐轮账本与恢复

增加 task-local `semantic-revisions` 事件账本，真实 prompt 在 query 前落盘，SDK 结构化结果和最终可见文本
在校验前落盘；局部拒绝、needs_input、全局反馈和运行失败留存。候选事件保存完整新版本、父版本和逐条差异，
提交必须与已记录响应重新计算的结果相同。事件链绑定输入 manifest；父版本使用内容摘要及事件序号，
即使内容相同也不能用旧请求覆盖新版本。文件锁和追加前检查阻止过期并发写入。

候选事件先写、账本投影后写；后者中断可从事件恢复，但原始响应不能直接成为候选。恢复局部拒绝时保留原提交
和实际反馈，并提供到新会话。恢复后全局检查重跑。旧非空候选缺少历史、事件缺失/损坏、映射分歧、持久化故障
均明确停止。无需修改 Skill 或增加 Agent 记账任务。诊断事件使用 replay mode，runtime 拒绝恢复为真实历史。

验证：

- 运行时与账本合同组 **76 passed**；其中真实 SDK 使用 mock，中断与磁盘失败使用注入，均为 `logic/contract`。
- 上下文、Agent 边界及文档组 **26 passed**；相关 Ruff、mypy（118 源文件）、diff check 通过。
- `temp/harness-repair-20260923/phase2-journal-replay-final/replay.json`：原正文 71 条真实判断按原有 10 批
  重放为 10 个候选版本、30 条事件，恢复结果逐字与原账本一致；原有 12 个分段错误仍保留。
  原任务输入/JSON hash 未改变，PKU 表格执行能力缺口仍准确停止。回放 prompt 是当前代码构造且未发送给 Agent，
  不是缺失的历史 prompt。未调用新 Agent，不是 E2E，也不是产品验收。

阶段 2 仍未完成：扩大修订范围的显式出口、故障原因保真和真实自然 Agent 修订闭环尚待推进。
预算与全部调度状态的持久化属于阶段 3，当前恢复不能宣称已满足阶段 3 的预算不重置要求。

## 阶段 2 进展：关联范围与反馈归责

新增 post-unit `expand_revision` 出口。Agent 只提供已有 source entries 和语义理由；Harness 核对范围、
补上下文并重新开放相关批次。请求不得夹带判断、未知条目或无效重复扩展；完成所有待修订范围前
不会进行全局接受。范围扩展及未完成工作随账本恢复；扩展请求计数跨恢复保留。
Schema 沿用 SDK 的 structured output，未实现第二套 runtime；实施前核对
[SDK 官方结构化输出说明](https://code.claude.com/docs/en/agent-sdk/structured-outputs)。

源文 review 新增明确的失败归责：分段/字段/输出合同错误可返回 Agent；Word 映射缺口、歧义、
输入词表缺失和未知检查失败归 Harness 并停止。App 保存完整失败证据，候选保留；反馈转换保留
具体原因和责任，不把内部定位问题改写成要求重判。反馈内源文、提交文字和条目摘要不再截断或去空白。

验证：相关 runtime / Harness / source-entry / revision / boundary / docs 合同组 **155 passed**；
Ruff、mypy（120 源文件）通过。包括跨批次重开、中断恢复、保留无关判断、非法扩展拒绝、
真实调用点的映射失败不重试测试；这些使用 mock / 故障注入，属于 `logic/contract`。
阶段 2 的自然真实 Agent 修订闭环仍未取得，本阶段未验收。阶段 3—5 尚未完成。

补充 real replay：`temp/harness-repair-20260923/phase2-feedback-replay/replay.json`，原有 12 条分段
blocker 均仍可返回修订，expected/submitted/uncovered text 在可见反馈中逐字保留。PKU 原真实整表判断
仍归执行能力阻塞，原任务输入和账本未变。回放没有新 Agent 调用。

阶段 2 真实运行已启动：`temp/harness-repair-20260923/phase2-live-20260923/`，
代码基线 `00267fe`，启动 manifest 保存全部 runtime Python、Skill 与输入摘要。
封面与正文均从隔离的真实最小单元输入重新运行至 `--until post-unit`，未复用旧判断或旧 checkpoint，
未读取 Gold，使用配置中的 MiniMax-M3 与锁定 OfficeCLI 1.0.143。Doctor base PASS；overall
仍 NOT_READY（既有 Agent smoke receipts 缺失），不记为整体环境验收通过。
当前运行结果待观察；不能提前记 E2E 通过。即使 post-unit 闭合，也不等于最终 DOCX 产品验收。


## 阶段 2：自然修订闭环证据

封面最小单元真实运行已结束，输出为 `checkpointed / post-unit`，28 条判断。真实运行的初稿出现
12 个字段缺失问题，后续全局检查发现 18 个文字分段问题；Agent 收到含源文与旧判断的修订包，
经过两个真实修订请求后，全局反馈为空并生成 post-unit checkpoint。全过程为 5 次请求、5 次响应、
4 次候选落档、1 次局部拒绝和 2 次全局检查，没有故障注入或 Gold 输入。

证据：`temp/harness-repair-20260923/phase2-live-20260923/cover-verification.json` 与同目录原始
`cover.log`、task-local 逐轮账本；冻结代码 `00267fe`。结束后核对 6 个输入、120 个 runtime 源文件、
11 个 Skill 文件的摘要均未变化。此项为 **E2E agent loop（到 post-unit）**，满足阶段 2 的自然修订
验收切片；不包含最终 DOCX、视觉复核或产品验收。正文任务仍在观察，不提前记录其结果。

## 阶段 3：局部检查与持久预算

在隔离 worktree 开发，避免改变阶段 2 真实任务的运行代码。每批候选入账前调用与整体检查相同的
空白解码及源文解析器，局部文字错误立即返回当前批次；完整集合仍进行全局检查。局部映射故障
保存反馈并停止，不进入语义重试。

修订预算按源条目与问题类别维护，默认每问题最多 7 次失败、连续 3 次相同错误停止；全文调用
上限为 max(32, 批次数 × 7)，查询时间上限沿用阶段配置。文字问题改用途、原因或错误码不会被认为
已取得文字修复进展。策略与请求、拒绝一起落盘，重启、范围扩大不清零。已记录响应或失败的等待
时间截止于该事件；进程直接崩溃而未记录结束时，保守计算未闭合等待区间，可能包含离线时间。
这会使长时间后恢复提前耗尽预算，当前明确作为保守停止限制，不静默重新分配完整额度。

验证：

- runtime、批次、上下文、范围扩展、账本及预算合同组 **128 passed**（含 mock SDK），属于
  `logic/contract`。三个独立批次分别三次拒绝后修正，累计九次局部错误仍可汇总；重复相同错误
  三次后停止，恢复不产生第四次调用。候选与被拒绝响应均保留。
- Ruff 与 mypy（122 个源文件）通过。
- 真实原始正文候选按原 10 批重放，局部/全局均发现同样 12 个问题；比较时仅换算批次内数组下标，
  源条目、分段位置和完整文字保持相同。原 task 输入/JSON 不变，PKU 不支持能力仍准确停止。
  证据：`temp/harness-repair-20260923/phase3-local-replay-v2/replay.json`，属于 `real replay`。
  首次诊断因直接比较局部/全局数组下标失败；修正的是回放比较器，没有放宽运行时检查。

阶段 3 的真实多批次新调度、预算及恢复 E2E 尚未完成；不能仅凭以上测试关闭阶段 3。
阶段 4 的最终视觉发布门和阶段 5 三校完整产物验收仍未完成。

阶段 3 新版真实正文任务已启动于独立目录
`temp/harness-repair-20260923/phase3-live-20260923/`，冻结运行代码 `f0bb5c4`，
从复制的原始正文单元输入新建 task 至 post-unit。runtime、Skill、输入摘要和观察句柄已保存；
没有沿用旧判断，也没有读取 Gold。运行中保持该 worktree 的 runtime 和 Skill 不变。

## 阶段 4 进展：最终逐页复核合同（尚未接入发布入口）

当前视觉工具生成图片证据，没有自动视觉判定者。新增宿主侧准备及复核验证模块：复用固定
LibreOffice 与 evidence store，先准备原稿及当前候选的全部 review 分辨率页面，生成待填复核请求；
由实际人工或外部视觉复核者记录观察结论。没有记录时明确待复核，不生成默认通过记录。
候选/源稿/渲染环境变化使用新请求路径，保留旧复核，不覆盖或借用旧结论。

每个最终页面绑定完整图片证据，逐项记录内容完整与分页、溢出遮挡、文字方向、表格公式、受保护布局
的检查结论及观察。复核者、时间、未解决问题均须显式记录。渲染成功、页码齐全及空 findings 本身
不能通过。此合同能证明材料齐备和版本一致，不能机械证明复核人的视觉判断正确；产品签收仍独立。

16 项 `logic/contract` 测试通过，使用合成图片/渲染 fixture；缺页、重复页、过期候选、缩略图、
损坏图片/渲染、无复核者、空观察、待确认和阻塞结论均被拒绝。Ruff、模块 mypy 通过。
尚未接入 App/publisher，尚未完成真实页面复核；不能宣称发布漏洞已修复。
下一步需要同步接入默认完成路径、直接发布路径和已完成任务恢复路径，并补对应拒绝测试。


阶段 4 发布入口现已接通：正常完成先准备并要求实际复核，再以 `all_final_pages` 调用客观 validation；
直接 publisher 独立检查同一复核合同；恢复已完成任务也检查保存的复核，旧的未请求状态不能复用。
等待复核时按已接受判断及输入绑定复用不可变物化候选，避免每次恢复重建 DOCX 使刚完成的复核失效。
候选文件改变/缺失明确停止，判断或输入变化则生成新候选、新复核请求。

相关 runtime、style/publication、字段合同及视觉合同 **145 passed**，属于 `logic/contract`。
风格/字段/SDK 合同测试显式隔离视觉依赖；25 项视觉合同测试单独验证实际接入的三个入口与证据存储，
图片/渲染仍为合成 fixture，没有冒充人工检查。Ruff 与 mypy（123 源文件）通过。
真实候选渲染、实际逐页观察与发布闭环尚未完成，本阶段仍未验收。
兼容性风险：过去没有有效视觉结论的已完成任务将被拒绝恢复；不会把历史未复核结果自动升级为通过。


## 真实验证补充：停止、恢复缺陷与视觉拦截

阶段 3 正文真实任务在两个有效批次后，于第三批自然产生文字遗漏。三次提交都遗漏同一条目的尾部
1 个 U+0020，并提交空 part；第 3 次后按 `semantic_revision_no_progress` 停止，没有发布。
冻结代码 `f0bb5c4`，总计 5 个真实语义请求、5 个响应、2 个候选落档、3 次局部拒绝；源文与候选留存。
这是实际无进展停止证据，不是正文完整成功。

随后用相同 CLI 但未写 `--from unit-boundary` 恢复，暴露 App 会重跑已有单元边界的问题：新边界与
已保存的投影不一致，停止于 `canonical_source_inventory_projection_stale`。语义请求未增加，
但发生了额外边界阶段调用，因此这次不能记为恢复验收通过。原始失败和副作用均保留在
`temp/harness-repair-20260923/phase3-live-20260923/verification.json`。
现已修正默认恢复入口：存在 checkpoint 时先验证并复用，只有显式重建入口才重新判断边界。
显式 `--from` 与默认恢复均有合同测试；修改后的真实恢复仍待后续完整运行验证。

阶段 4 已取得真实封面完成阶段证据：复制阶段 2 的真实 post-unit task（原任务不变）后物化，
实际渲染原稿 2 页、候选 1 页。缺少复核时准确停止于 `final_visual_review_required`。
通过 `view_image` 查看全部 3 张页面图，记录为外部视觉复核，发现纵向留白明显收缩、格式说明残留，
真实复核结论为 blocked。再次恢复复用同一候选，停止于 `final_visual_review_not_passed`，
没有 `final-template.docx` 或 `fill-contract.yaml` 发布。

初步归因有直接判断证据：4 个空行说明段被 Agent 明确判为整段 cleanup，物化器按既定类别删除整段；
姓名后的字体说明被明确包含在 fixed_label 中。不能把这些结果归为 Harness 自动扩大用途；
学校语义或其表达边界需要单独审查，当前不为通过发布而静默修改判断。
原稿第 2 页确为空白，因此仅凭候选减少 1 页不判定实质内容丢失。
证据：`temp/harness-repair-20260923/phase4-cover-completion/verification.json`，代码 `673a27c`。
这是 real replay + host completion，复用了真实 checkpoint，不是新的完整 E2E；无故障注入。
阶段 4 的正向发布和阶段 5 三校产品验收仍未完成，视觉发现的真实失败没有被抹去。

恢复入口修正及视觉接入后的完整 `tests/contract`：**821 passed in 30.73s**，属于
`logic/contract`；mypy 123 个源文件通过。首次全量有 1 项既有分区恢复测试缺少新视觉 fixture，
明确隔离该测试的视觉依赖后再全量通过；真实视觉门由独立 25 项合同测试覆盖，没有放宽运行代码。

阶段 5 三校完整输入验证已开始：
`temp/harness-repair-20260923/phase5-three-schools/manifest.json` 固定代码 `bcdc3d8`、
123 个 runtime 源文件、Skill 和三校输入摘要。HUNAU / NJAU 从完整模板新建 task 运行完整流程，
无旧 checkpoint、无旧判断、未读 Gold；PKU 已备好输入，等待前面的一个运行结束后启动。
这些运行结果尚未返回，不记为通过。阶段 2 的旧正文任务仍运行，故代码尚未移回主工作区；
阶段 3/4 改动分别在隔离 worktree 提交，主工作区已有无关修改保持不变。

阶段 5 首轮 HUNAU 在 unit-boundary 返回 `unit_checkpoint_result_invalid`，未进入 post-unit。
旧外层 trace 写入空计数，缺少真实 SDK subtype/停止信息，不能从该记录确认原因为模型、SDK 或服务端。
保留原任务和日志，不把这次失败改写成通过。NJAU 和 PKU 在冻结代码上继续运行。

为解决真实排障缺证据，单元边界阶段增加独立逐次执行诊断归档（安全 metadata，不记录隐藏推理或
原始错误文本），并在失败时把实际 query/tool/timing 计数传回外层 trace。复用既有 SDK 事件摘要，
没有增加新的 Agent runtime、重试机制或学校判断规则。原 HUNAU 缺失的信息无法补造；新运行才会产出。

直接发布入口补充拒绝显式失败的客观 validation：即使视觉复核通过，validation 非 ok、存在 failure、
检查项阻塞或检查结构非法也不进入 Word 发布。这避免调用底层 publisher 时绕过 App 的客观检查。
诊断与发布补充后的完整合同回归 **827 passed in 31.81s**；Ruff、mypy 123 源文件通过。
以上仍是 `logic/contract`；新增 SDK 错误案例、图片和判断均为显式合成 fixture，不算真实 E2E。

HUNAU 新诊断重试（`11acec7`）在 unit-boundary 的 180 秒无进展计时处停止，已记录 1 次真实 query
和 5 次工具调用，无 ResultMessage。代码检查确认：unit-boundary 未开启 partial messages，也未复用
post-unit 的生成进展识别；因此长时间生成可能被误判成停滞。这次记录未包含原始 stream delta，
不能倒推该次超时全部由此造成。原始失败保留在 `phase5-three-schools/hunau-retry-verification.json`。

按 [SDK 官方流式输出文档](https://code.claude.com/docs/en/agent-sdk/streaming-output)，
unit-boundary 现开启 `include_partial_messages` 并复用现有生成进展检测。非空 text/thinking/tool JSON
增量延续活动计时；空增量与心跳仍触发 180 秒停止；阶段总超时不变。不记录增量文本或隐藏推理，
只记录安全事件类型及是否存在生成进展。69 项 runtime 合同测试通过，包含两阶段的生成/心跳区分；
Ruff、mypy 123 源文件通过。真实修复后重试仍待验证。

阶段 2 的旧正文运行已在整体超时后结束：28 请求、27 响应、26 个候选版本、3 次全局拒绝；
最终仍有 20 个文字分段问题，没有 post-unit 完成或发布。结束后源代码、Skill、输入摘要全匹配启动
manifest，证据为 `phase2-live-20260923/body-verification.json`。它是保留的失败 E2E，不能记为成功。

## 三校终态、默认恢复与本轮合同修正

阶段 3/4 及诊断修复已带回主工作区，至 `bb836c8`；迁移前后 79 个既有无关修改保持不变，
证据为 `acceptance-evidence/port-verification.json`。原阶段记录中“运行中/未移回”是当时观察，
由下述终态更新，不删除历史失败。

三校完整任务均在发布前停止。2026-09-23 重新观察时原会话句柄已不存在，进程表无原任务，
终态日志及账本均记录失败；没有基于观察超时重启。各自结束后的输入、123 个 runtime 文件、
11 个 Skill 文件摘要与启动 manifest 一致，证据为
`phase5-three-schools/terminal-before-resume-verification.json`。

| 任务 | 真实结果 | 语义请求/响应 | 候选版本 |
| --- | --- | --- | --- |
| NJAU，`bcdc3d8` | 相同章节标题空格遗漏连续三次，按无进展停止 | 18 / 18 | 8 |
| PKU，`bcdc3d8` | 语义阶段时间预算耗尽 | 21 / 20 | 14 |
| HUNAU streaming，`bb836c8` | 单元划分通过；封面文本内空格遗漏重复，按无进展停止 | 4 / 4 | 0 |

HUNAU 单元阶段归档记录 3 次 query、2 次反馈和 7,112 个非空生成进展事件，耗时约 867 秒，
最终进入 post-unit。这是当前流式路径真实工作证据；不是与此前隔离 Skill 基线严格控制的 A/B，
不能据此断言此前所有超时只由流式设置引起。三校均无发布产物，产品验收未完成。

随后在各自冻结代码上用原 CLI 默认恢复。NJAU 和 HUNAU 保持原无进展停止，语义请求数没有增加；
旧 checkpoint、inventory、候选及历史事件内容摘要全部不变，仅新增失败观察事件。
`phase5-three-schools/no-progress-default-resume-verification.json` 是真实默认恢复证据，
不是成功生成证据。PKU 暴露另一缺陷：阶段总时限耗尽后，恢复按查询时间重新计算仍有约 261 秒，
因而再次发起请求。旧版此次恢复继续保留为失败证据，不能记预算恢复验收通过。

本轮据此修正三处工程合同，不改学校语义规则、不补写 Agent 判断：

- 时间预算：历史已明确记录时间耗尽时，恢复立即停止；不能用较短的查询耗时重新开放预算。
  一般中断仍可按保存的剩余额度恢复。两种情况均有独立回归。
- 修订反馈：明确提供本次提交的 source-entry 范围及整批/局部模式。局部检查拒绝的是尚未接受的
  整批提交时，要求返回完整批次；不能把错误定位列表误当成已经缩小的提交范围。PKU 曾因只返回
  3 个报错题注而遗漏其余 26 个条目，证明这不是纯粹的文案偏好。
- 空白 schema：说明显式 codepoint/count 可以位于可见文字之间，与既有解码能力及启动指令一致；
  不再仅指向 entry 首尾元数据。仍由 Agent 指定空白责任，仍逐字检查，未恢复自动补全。

工作区原有 Reference 修改把“彩色/括号文字”改成“彩色或括号”，导致旧静态路由 fixture 断言失败。
保留 Reference 和既有测试文件修改；仅将 fixture 改为核对未变化的实质规则“正式名称中的括号仍是名称”。
最新全量 `tests/contract` 为 **834 passed in 29.11s**，相关 Ruff 与 mypy 123 个源文件通过。
此处是 `logic/contract`，包含 mock SDK，不代表三校 E2E 或产品验收通过。修复后真实预算恢复和
新反馈下的真实 Agent 修订仍待验证。

修复 `3adad8f` 后在原 PKU task 上再次运行默认 CLI：准确停止于保存的时间预算耗尽，累计请求仍为
25 次，响应仍为 23 次；checkpoint、inventory、候选和原事件内容摘要均未变化，仅追加一条失败记录。
证据为 `phase5-three-schools/pku-fixed-budget-resume-verification.json`，属于真实 CLI 恢复，
没有 mock 或修改账本，不代表生成成功。旧版本第一次恢复额外发起了 4 次请求、增加 1 个候选版本，
保留在 `pku-old-budget-resume-verification.json`，不能抹去或记为修复后表现。

以 PKU 第 63 个历史事件的真实修订请求重建当前反馈，明确列出 3 个错误位置和整批 29 个提交条目。
`phase5-three-schools/revision-scope-replay/verification.json` 是 real replay 的 prompt 构造验证，
重建 prompt 没有发送给 Agent，也不是原始历史消息。

HUNAU、NJAU、PKU 现按 `3adad8f` 新建完整模板任务，目录为
`phase5-three-schools/<school>-revision-contract-task`；各自 `*-revision-contract-manifest.json`
固定输入、runtime 和 Skill，不复用原候选、不清除旧任务预算。运行期间主工作区 runtime/Skill 冻结。
这些新结果待观察，正向发布及最终产品验收仍未完成。

## 仓库回归与第二轮运行补充

主工作区扩大到全仓 pytest 回归：**1298 passed / 4 failed / 1 warning**，日志为
`acceptance-evidence/recovery-repository-tests.log`。该轮使用默认 PATH 的 OfficeCLI 1.0.144，
不是计划锁定的 1.0.143；不能作为锁定环境的整体验收。三项失败来自本轮改变的测试合同：
旧失败码预期未更新，以及两项只测源稿选择/Word 发布绑定的测试未隔离新增视觉门。
现同步预期并明确 mock 视觉复核依赖；没有放宽运行时发布条件，没有把 mock 当真实页面复核。
使用锁定 OfficeCLI 1.0.143 的相关组 **11 passed**，证据为
`acceptance-evidence/repository-repaired-tests.log`。这是 logic/contract 加确定性 Word 工具集成，
不是实际视觉验收。旧结构输出的测试还断言仅 3 次调用、3 次拒绝、0 个候选被接受。

剩余学生内容填写测试要求发布 PARTIAL，但其构造的 Fill Contract v2 缺少有效物化来源证明，
实际返回 `template_artifact_provenance_invalid`。在干净的旧阶段代码 `f0bb5c4` 上、使用锁定
OfficeCLI 单独复现相同失败：`acceptance-evidence/student-fill-baseline-f0bb5c4.log`。
本轮没有修改学生内容模块或该测试，不能把全仓回归记为全部通过，也不借此绕过跨模块来源检查。

第二轮 HUNAU（`3adad8f`）已终止：第一次单元划分得到有效结构化结果，机械边界反馈后，第二次
query 由 SDK 以 `is_error=true / terminal_reason=api_error` 结束，应用却归成
`unit_checkpoint_result_invalid`。输入/runtime/Skill 与启动摘要均一致，证据为
`phase5-three-schools/hunau-revision-contract-verification.json`。没有进入 post-unit，没有发布。
这次有明确 API 失败证据，不再推测为模型未按 schema 输出；也不能推断此前缺证据的失败同因。

在隔离 diagnostics worktree 修正该归责，主工作区仍为 NJAU/PKU 冻结。依据
[SDK ResultMessage 官方说明](https://code.claude.com/docs/en/agent-sdk/python#resultmessage)，
subtype=success 也可能伴随最终 API 请求失败。修复读取原生错误元数据，在单元与语义阶段均停止并
报告 environment/API 错误，不生成语义重判，也不将原始 API 错误文本写进反馈或候选响应账本。
原真实诊断元数据回放已正确分类：`phase5-three-schools/hunau-api-failure-classification-replay.json`。
这只验证归责，不修复外部 API，也不是新的成功 E2E；完整回归及隔离修复提交见后续记录。

隔离修复提交 `7a2a1ce`：完整 `tests/contract` **837 passed in 29.14s**，相关 Ruff 与
mypy 123 个源文件通过。单元与语义阶段均覆盖带 HTTP 状态的错误，以及实际观察到的
`subtype=success / terminal_reason=api_error`；语义阶段没有增加修订请求或候选版本。
主工作区已有两个真实任务运行，故此修复尚未合入主工作区，不能把后续旧代码运行行为当作已修复表现。

HUNAU API 失败之后，通过既有 `--from unit-boundary --resume-proof` 入口复用 streaming 轮的
已接受单元结果，继续当前 revision-contract task。源模板及 Registry 摘要相同，proof 摘要和
原失败 trace 单独保存于 `phase5-three-schools/hunau-accepted-proof-resume-manifest.json`。
该 task 尚无语义账本，未清除预算或覆盖候选。此运行是显式阶段恢复验证，不是本轮从头完整 E2E；
原 fresh run 的失败状态保持不变。恢复结果仍待观察。

## 第二轮收尾与字符传输合同修复

第二轮 NJAU、PKU 和 HUNAU 显式恢复均以 `semantic_revision_no_progress` 停止，没有发布产物。
NJAU 有 16 次请求/响应、9 个候选记录；PKU 为 8 次请求/响应、3 个候选记录；HUNAU 恢复为
3 次请求/响应、0 个接受候选。计数不是完整批次覆盖或产品通过率。
`njau-revision-contract-verification.json`、`pku-revision-contract-verification.json` 和
`hunau-accepted-proof-resume-verification.json` 保存终态；输入、runtime、Skill 摘要均与启动一致，
HUNAU 复用 proof 未变。原 HUNAU fresh run 的 API 失败仍单独保留。

两个 MiniMax 原生 SDK 合成探针用于判断字符问题所在，不属于学校 E2E：
`acceptance-evidence/whitespace-protocol-probe.json` 中公开 JSON 与随后结构化提交不一致；
`whitespace-parts-protocol-probe.json` 使用 post-unit schema，首尾空白保留，但纯空白 part
额外增加了 whitespace 元数据。因此不能推断 SDK 总会 trim，也不能直接把所有错误归给模型或传输层。

确定的工程缺口是：完整字符/空白传输说明仅存在于旧启动 prompt，实际分批入口没有引用。
隔离提交 `2c19aee` 将两处共用同一份规则，并在模拟 SDK 的实际 query 上断言初稿与修订都收到说明。
`fc1acca` 进一步在任务私有 response 账本保存公开 Assistant TextBlock，和最终 structured_output
分别留档；不读取隐藏推理、不将文字草稿当候选、不自动补字。Assistant 错误消息不收录，最终 API
失败时丢弃公开文本缓冲，避免错误内容进入语义证据。对应正反例共 6 项通过。

隔离全部 contract 为 **837 passed in 25.24s**；合入主工作区后 **837 passed in 24.59s**，
相关 Ruff 与 mypy 123 源文件通过。主提交依次为 `198d70a`（API 归责）、`81072c9`（实际调用合同）、
`ae1cb9f`（公开响应证据）；既有 79 个无关修改的完整 diff 保持一致，见
`acceptance-evidence/diagnostics-port-verification.json`。这些是 logic/contract，未证明真实生成成功。

现以 `ae1cb9f` 在新 task `hunau-shared-transport-task` 复用 streaming 轮已接受的 unit proof，
继续完整模板的 post-unit 至交付链；`hunau-shared-transport-manifest.json` 固定输入、proof、runtime
和 Skill。这是实际阶段复用验证，不是 fresh full-school E2E；原失败预算和账本未清除。
同时启动锁定 OfficeCLI 1.0.143 的全仓回归，结果待收取。运行期间主 runtime 与 Skill 保持冻结。

锁定环境全仓回归现已结束：**1304 passed / 1 failed / 1 warning，296.97s**。唯一失败仍是
`test_independent_student_content_app_publishes_partial_candidate`，手工构造的 v2 填写合同缺少
物化来源证明，返回 NEEDS_INPUT，而旧测试预期 PARTIAL。它已在 `f0bb5c4` 基线独立复现；
本次未更改该测试或消费者校验规则。日志为 `acceptance-evidence/locked-response-repository-tests.log`，
环境与结果摘要为 `locked-response-repository-verification.json`。不能宣称全仓全部通过，也不能用此
结果替代真实 Agent/视觉验收。运行后既有无关工作区 diff 仍保持一致。

HUNAU shared-transport 第一批实际返回 23 条判断，局部检查仅拒绝一条 source entry：中文弯引号
被改成 ASCII 直引号，导致该条有 3 项相关范围反馈。旧运行反复失败的姓名条目不再被本批检查拒绝，
模型已使用显式 whitespace part 表达空白。不能据单次样本宣称稳定通过率提升。实际第二次修订请求
已发送，尚未接受第一批。该响应没有公开 Assistant TextBlock，只有结构化提交，因此无法比较这次
草稿与最终提交。证据为 `hunau-shared-transport-request-verification.json` 与
`hunau-shared-transport-first-response-verification.json`，均为实际运行证据，不是产品验收。

## 修订反馈连带误报

HUNAU shared-transport 第二次响应仍将中文弯引号改为直引号，现已发出第三次请求，尚未闭合。
检查反馈另暴露工程缺陷：第一 part 不匹配后 cursor 未移动，后面正确的 5 个空格又被拿来与源文
开头比较，并把整条报告为遗漏。三条反馈中后两条由失去定位后的继续检查产生。

隔离 diagnostics 提交 `551430c`：在每个 source entry 的首次文字不匹配处停止后续分段定位，
保留原错误并拒绝候选；修订后重新检查所有分段，其他 entry 继续检查。没有跳过接受检查、补文字
或改变用途。全 contract（加入前三项回归后）**840 passed in 24.92s**；另补其他 entry 不漏检用例后，
source-span 组 **23 passed**。相关 Ruff、mypy 123 源文件通过。
`phase5-three-schools/noncascading-feedback-real-replay.json` 使用未改动的真实首轮候选及 inventory，
证明反馈从 3 条变为同一条原始引号错误，候选仍为 needs_input。属于 real replay；未发送新反馈给
运行中的 Agent，不能当作修订成功。主 runtime 仍冻结在 `ae1cb9f`，该隔离修复尚未合入。

HUNAU 随后自然闭合：第三次提交保留了正确弯引号，第一批被接受，第二批也被接受，继续第三批。
`hunau-shared-transport-natural-revision-verification.json` 固定两次接受事件和第三次真实输出摘要。
这是 `ae1cb9f` 上的自然 E2E post-unit 修订闭环，尚不是完整学校生成；没有使用隔离的反馈改进。
另一原生 SDK 合成探针 `acceptance-evidence/quote-protocol-probe.json` 完整保留四组中英文引号，
耗时 6.3s；它只否定“通道总会统一改写引号”的假设，不定位完整任务中错字的具体来源。

隔离提交 `03a3519` 补充可见的首个字符差异：期望字符、提交字符及 Unicode 码点，超出原文时明确
标记 end_of_text。反馈 sanitizer 保留该信息，不改变判断 schema、角色、字段或接受规则。
`character-feedback-real-replay.json` 证明实际引号错误以 U+201C / U+0022 出现在 Agent-visible
反馈中。完整 contract **844 passed in 26.48s**，相关 Ruff 和 mypy 123 源文件通过。

在 `03a3519` 隔离工作区启动 NJAU / PKU 新完整输入运行，task 为 `njau-precise-feedback-task` /
`pku-precise-feedback-task`，未复用单元 proof、判断或旧预算。对应 manifest 固定实际 worktree、源码
和 Skill；为保持输入一致，仅复制了主工作区已有 Reference 修改，全部模板 Skill 文件与主工作区
逐字一致，该既有修改未提交。主工作区 HUNAU 与隔离工作区两校的 runtime/Skill 均冻结至终态。
不得把两个版本的结果合称同一版本三校验收；最终仍需按最终交付代码核对验证范围。

## 空白表达的 Schema 约束

HUNAU 第三批一次提交同时包含 `text: "  "` 与 `whitespace: {codepoint: "U+0020", count: 3}`，
Harness 正确报告 `ordered_part_whitespace_transport_invalid`。这项机械互斥规则此前只写在描述和
后置校验中，结构化 schema 未表达。依据 [SDK structured-output 文档](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
的 draft-07 验证约定，在已空闲的 phase3 worktree 从 `03a3519` 开始做隔离修复，不修改任何 live runtime。
旧 `f0bb5c4` 保留为 `codex/harness-phase3-evidence`，旧失败回归证据仍对应原 commit。

隔离提交 `f41f470` 增加条件约束：出现 whitespace 时 text 必须为空。角色、字段和原有普通文字/
结构空条目表达不变，Harness 继续检查码点确属空白以及展开后精确匹配源文；没有自动选择空白责任。
新增 8 项 Draft7Validator 正反例，完整 contract **852 passed in 25.10s**，相关 Ruff、mypy
123 个源文件通过。`conditional-whitespace-real-replay.json` 对未修改的真实错误输出验证：仅在
第 3 条判断第 5 个 part 的 text 处报告 const 冲突。

`acceptance-evidence/conditional-whitespace-schema-probe.json` 是使用相同 schema 的原生 SDK
合成调用，7.61s 返回有效空白表达。它证明 SDK 接受该 schema 并能返回兼容结果，不单独证明一定由
SDK 内部重试完成修复，也不是学校 E2E。此提交尚未用于运行中的三校任务，也尚未合入主工作区。

最近观察：NJAU 已接受前三批；PKU 已完成单元划分并进入 post-unit；HUNAU 保留两批接受结果，
第三批的空白表示冲突已修正，后续精确文字检查继续发现引号、点连线数量和纯空白长度问题。
未产出最终交付物，当前状态不能用于产品签收。

## 新反馈的真实修订闭环与边界计数说明

NJAU `03a3519` 第四批将 25 条源文中的 tab 写成字面反斜杠转义。实际反馈逐条列出
U+0009 / U+005C；一次真实修订后该批被接受，已进入第五批。
`njau-precise-feedback-natural-revision-verification.json` 绑定拒绝、实际请求、响应和接受事件。
这是新字符反馈下的自然 E2E Agent loop 闭环，不是故障注入；完整学校任务仍在运行。

HUNAU 第三批目前只剩纯空白条目重复：原文 3 个空格，模型把原文、leading count 和 trailing
count 视为三份文字，提交 9 个空格或三个各含 3 空格的 part。`whitespace-count-overlap-replay.json`
从真实 inventory 重建 reading entry：text_length / leading / trailing 均为 3。前后计数描述的是
同一份文本，并非要附加的文字；该文件是 reading-packet replay，不冒充历史工具完整响应。

隔离 phase3 提交 `1a23d1d` 在共享输入合同明确：边界计数描述 text 内已有字符，纯空白时前后
计数重合，不能相加或再加到 text_length。没有修改 reading text、候选、自动补齐或用途判断。
实际初稿/修订 query 的相关 mock 验证组 **11 passed**；Ruff、mypy 123 源文件通过。
本次两句合同说明尚未用于 live 三校任务；852 项全 contract 结果对应此前 `f41f470`，不混称为
本提交完整回归。PKU 已接受前两批，后续仍在修订。三次运行仍无最终产物。

## PKU 终态与边缘空白表达探针

PKU `03a3519` 完整输入运行以 `semantic_revision_no_progress` 停止：8 次请求/响应、3 次候选接受，
无发布。`pku-precise-feedback-verification.json` 已核对输入/runtime/Skill 与启动摘要一致。
失败仍为导师英文姓名前 U+0020 缺失。三次实际提交均为两段无边缘空格的字符串；后两次 reason
声称包含空格，结构化 parts 实际没有。不能从 reason 反推空白责任并自动补字。仅配置了 MiniMax
后端，未假设有可用的其它模型或擅自添加凭据。

`acceptance-evidence/boundary-whitespace-encoding-probe.json` 测试用显式空白 part 代替字符串
边缘空白，合成原生 SDK 调用 3.63s 后逐字重构成功。但是模型给 fixed_label 添加额外 field_id，
并把一个 fill_slot part 拆为两个 fill_slot part，因此该结果不证明字段/填写位置保持，也不用于
生产代码。只记录字符表达可行性及其限制。后续若加强混合文本的边缘空白表达，应保持一个原判断
part 的边界和角色/字段身份，不能为传输空格而无意增加填写位置。当前没有部署该探针 schema。

HUNAU 与 NJAU 原进程继续运行；最近观测 NJAU 已接受 9 批，HUNAU 保留 2 批并继续修订。
不因观察等待而重启，也不将阶段接受数量视作完整产品验收。

## 同一语义片段的边界空白表达（6678851）

此前三次 live 运行现均已确认终止：HUNAU `ae1cb9f` 为问题预算耗尽（12 次请求、2 次候选接受），
NJAU `03a3519` 为无进展停止（15 次请求、9 次接受），PKU `03a3519` 为无进展停止（8 次请求、
3 次接受）。各自 verification.json 已核对冻结输入、源码和 Skill 无变化，均没有最终输出。
准确停止和局部自然修订证据仍有效，但没有任何一校因此完成产品验收。

相关隔离修复已在三次运行终止后合入主工作区：`ea77a44` 停止级联伪错误、`2a70e5e` 首字符差异、
`21b3a9d` 纯空白 schema 互斥、`3dc09b6` 边界计数解释。无关工作区修改保持原样。

`6678851` 在同一 part 上表达 leading/trailing 空白 runs，避免仅为传输空格而拆成多个填写位置。
边界编码与纯空白编码互斥；解码不推断角色、不从源文补字符，不改变 part 数量和 field_id。
实际分批输入、修订反馈、Schema 和边界文档同步，历史字面空白仍可回放。

验证层级：

- `logic/contract`：完整合同测试 **876 passed in 32.85s**；Ruff 通过；mypy 123 源文件通过。
  反例覆盖 literal edge、非法编码、组合冲突、错误计数，范围测试比较全部解析结果并确认单一 slot。
- 原生 SDK 合成探针：新增示例前，一次输出错误拆分填写位置，保存在
  `acceptance-evidence/part-boundary-pre-example-codec-probe.json`。补充同一 part 的显式示例后，
  `part-boundary-final-codec-probe.json` 在 4.27s 返回完全相同的两段责任，无 schema warning。
  不据此宣称模型稳定可靠，也不冒充学校 E2E。
- 历史兼容回放：`part-boundary-legacy-compatibility-replay.json` 对最新三校候选的 158 / 51 / 49
  条判断完成局部检查与逐段范围解析对照。没有任何混合文字 part 的边界空白被转换，所以该证据
  仅证明旧数据兼容，不能单独验证新增 codec 分支。

PKU 新完整输入任务 `pku-boundary-codec-task` 已启动，manifest 绑定 runtime `6678851` 与当前
输入、Skill；没有复用旧 proof、判断或预算。首次运行在 unit 阶段遇到 `template_agent_api_error`
终止，1 次 SDK 请求、没有最终输出，摘要无变化；它尚未验证新 codec。已保留失败证据并启动
独立新任务 `pku-boundary-codec-retry-task`，源码和 Skill 在重试期间冻结至终态。
完整三校生成、正向最终发布与产品验收仍未完成。

针对性 `real replay` 已补齐：`acceptance-evidence/part-boundary-real-replay.json` 从早期真实运行的
记录中选取带混合文字边界空白、且原文检查通过的 14 条判断，转换 15 个 part。PKU 完整输入切片、
body 切片、cover 切片分别为 6 / 3 / 5 条判断，解析出的 6 / 3 / 2 个填写位置及全部 Word 范围
在编码前后完全相同。未增加新判断或修正学校语义；完整未判区域不在此次回放范围内。
body 原候选另有 2 条边界文字错误，已在报告中保留排除原因，不能称整个历史候选通过。
这证明已有明确责任范围的传输保持性，不证明新 Agent 能为完整模板持续产出正确判断。

## 三校统一运行与修订上下文的配套修复

`6678851` 的 PKU 重试已通过单元划分（12 units，1 次 query，120376ms），进入 post-unit；
随后启动同一源码和 Skill 摘要的 NJAU / HUNAU 新完整输入任务（`*-boundary-codec-task`），
均不复用旧 proof、判断或预算，三校均已进入语义阶段。固定 OfficeCLI 1.0.143 二进制摘要写入
各自 manifest。实际 PKU 请求中的新边界规则已核对，见 `pku-boundary-codec-request-verification.json`。
PKU 首次局部反馈针对模板选框字符遗漏，此时尚无边界编码 part，不归因于新 codec。

当前 runtime 的物化集成回归 **50 passed in 136.27s**，日志为
`acceptance-evidence/boundary-codec-materialization-integration.log`。这些是确定性 fixture／构造判断
集成测试，不是学校自然 Agent E2E，也不是产品验收。

检查配套链路发现 `revision_context._visible_judgment` 的白名单尚未保留新增 leading/trailing
空白数组，会丢掉新候选中的显式边界文字。先在空闲 phase3 worktree 切到 `6678851` 复现：新增测试
因上一版投影丢字段而失败；修复后，候选基线和被拒绝输出保留完整编码，内部 object_ref 仍过滤，
嵌套数组修改不会反向污染原始候选。隔离提交 **fc41c9d**，相关合同组 **113 passed in 19.40s**，
Ruff 与该源文件 mypy 通过。它只修改修订上下文及回归测试，未改学校语义或 SDK runtime。

`fc41c9d` 尚未合入运行中的主工作区；不能把本轮三校运行写成已经验证该补丁。保持主源码和 Skill
冻结至终态，再决定合入及必要的修订闭环验证。完整三校生成和最终产品验收仍未完成。

运行中的 HUNAU 提供了上下文缺陷的直接证据：原始 response 有 5 个带 leading/trailing 编码的
part，随后实际发出的 revision context 中为 0；隔离 `fc41c9d` 对该未修改真实 response 的投影
回放完整保留 5 个 part 及全部原判断。见 `boundary-revision-context-real-replay.json`。
它不是已修复版本的自然 Agent 闭环，也没有把原判断中的其他错误当作正确结果。

HUNAU 同一次输出把可见方框 U+25A1 编成 whitespace（8 处）。原 Harness 正确拒绝；隔离提交
**4162e52** 将 schema 的 codepoint 限制为 Python Unicode 空白集合，覆盖纯空白和两类边界数组。
没有增加学校文字规则，也未赋予方框任何用途。未修改真实输出的 schema replay 精确拒绝这 8 处；
`whitespace-alphabet-real-replay.json` 保留输入摘要及错误位置。隔离完整合同 **890 passed in 28.91s**，
Ruff 和 mypy 123 源文件通过。原生 SDK 合成探针 34.85s 返回兼容结果且保留两段责任，无 schema warning；
仅验证该 schema 可用，不证明一定触发了内部纠错，也不证明学校 E2E。`fc41c9d` 和 `4162e52` 均尚未合入主工作区。

当前主 runtime `6678851` 的 HUNAU 已自然接受前两批，其中分别保留 5 / 2 个边界编码 part；
`hunau-boundary-codec-natural-acceptance.json` 绑定接受事件。这是 codec 的自然批次接受证据，
仍没有整校发布，也未使用上述两个隔离补丁。

PKU 重试现已终止（exit 2）：7 次请求、7 次局部拒绝、0 次候选接受，以
`semantic_problem_budget_exhausted` 停在学位类别选框条目。各轮都选择 `degree.type` fill_slot，但中间四轮拆成两个 part，首两轮和末轮为一个 part；
结构化 text 始终遗漏或改写了 U+F06F 选框字符。不能从 reason 补字符或擅自扩展用途。
`pku-boundary-codec-retry-verification.json` 核对冻结输入/源码/Skill 无变化、无发布，并保存各轮字符表现。
目前不能据此断言是 SDK 字符过滤；需继续区分生成问题与传输问题，以及整条用途声明是否必须逐字复述的合同负担。
HUNAU 随后因 `template_agent_api_error` 终止，已接受的两批仍保留，输入/源码/Skill 摘要
未变化、没有发布。NJAU 原进程仍运行，继续保持主 runtime 冻结。

## 显式整条用途声明（2026-09-24）

NJAU `6678851` 运行也已终止：5 次请求、1 批接受，随后 Agent 把日期标签的字符分段问题提为
needs_input，未发布。该请求不是已经确认缺少学校资料；原始修订上下文丢掉空白编码的问题已另行修复。
三校终态均已核对冻结摘要，之后合入 `fc41c9d → 33612b1` 与 `4162e52 → d2ddb9e`，
既有无关 diff 在合入前后逐字一致。

针对 PKU 私用区选框字符，进行了有界原生 SDK 诊断：简单的 ASCII 转义 part 复制曾成功，
但加 text_json 辅助字段、以及将完整阅读包改为 ASCII JSON 的两个探针仍失败。前者只证明一种
合成输入曾成功，不能据此归因 SDK 过滤或宣称输入转义可靠。未提交的 text_json 实现已撤回，
失败结果保留在 `private-character-*-probe.json`。没有把失败实验接入产品。

改为稳定的语义合同：Agent 明确判定整条原文承担一种责任时，可以提交唯一 part 的
`whole_entry: true`；混合用途仍须分段 text。只有显式声明才从绑定原文取得全文，不能与 text、
空白编码或其他 part 混用。缺少声明的部分文字依旧报告遗漏。展开后继续走原有 unit 切点、
范围、词表、执行与发布检查；Word 执行器只收到常规原文及 span/slot。
这是 Schema、Harness、修订上下文和稳定 Skill 指引的跨层合同变更，不是从旧 reason 推断用途。

隔离提交 `b05a50c` 合入为 **0c1ff83**；**6c72804** 明确空白编码指令仅适用于 text 分段，
**6eee0b1** 同步实际 query 的合同断言。主工作区 runtime/Skill 随后冻结。

验证：

- `logic/contract`：主工作区完整合同 **906 passed in 24.46s**，日志
  `whole-entry-main-verified-contract.log`。此前一次主回归进程消失且只有部分日志，不计通过；
  重查的两项失败是旧提示语断言，更新后完成全量回归。隔离源代码 mypy 123 文件、相关 Ruff 通过。
- 原生 SDK 协议探针 `whole-entry-private-character-probe.json` 在给定用途的前提下，返回正确
  source_entry_id 与唯一 whole_entry part；不算独立学校语义判断。
- `real replay`：该实际协议输出在真实 PKU inventory 中展开，精确保留原始选框字符并解析为
  一个 degree.type slot，见 `whole-entry-pku-real-replay.json`。不是完整模板发布。
- 构造 DOCX 集成（`logic/contract`）：逐字提交与整条声明两种输入均经过 Harness 接受和真实
  OOXML 物化，保留精确源文，产出一个绑定的填写位置；**2 passed in 0.82s**，日志
  `whole-entry-docx-integration-final.log`。不替代真实模板页面验收。

PKU 新完整输入任务 `pku-whole-entry-task` 在 `6eee0b1` 启动（runtime `6c72804`），
未复用旧 proof、判断或预算，固定 OfficeCLI 1.0.143；当前已通过单元划分，进入语义阶段。
入口 manifest 和精确进程句柄保存在 phase5-three-schools。三校完整交付、正向最终发布和产品验收仍未完成。


## 同版本三校验证续行

PKU `pku-whole-entry-task` 第一批 27 条判断通过局部检查并写入候选事件，
此前失败的 degree.type 选框字符这次由 Agent 原样逐字提交。该批 whole_entry 声明数为 0，
因此不归因于整条声明分支，也不把批次接受视作语义正确或整校完成。
证据为 `phase5-three-schools/pku-whole-entry-first-batch.json`，绑定原始响应、局部检查与候选事件摘要。
实际请求已包含 whole_entry 指令；未改变 Agent 输出或降低范围检查。

之后启动 HUNAU / NJAU 的 `*-whole-entry-task`，均为完整学校输入，无旧 proof、判断或预算复用。
新 manifest 的 runtime 123 文件与 Skill 11 文件先对照 PKU 启动摘要核验一致；OfficeCLI 固定 1.0.143。
运行入口 commit 为 `896b63f`，runtime 仍是 `6c72804`，两者之间只有测试和文档变更。
三条精确执行句柄均已写入 `observation-handles.json`，主 runtime / Skill 继续冻结至终态。
目前没有最终模板、正向发布或产品验收证据。


PKU 随后的第二批（版权单元）8 条判断全部自然使用 `whole_entry: true`，通过局部检查并写入
候选事件。`pku-whole-entry-natural-acceptance.json` 绑定请求、原始响应、检查和接受事件，
补齐新声明分支的自然 Agent 批次证据。此证据与第一批逐字提交的学位选框分开；不宣称第一批
依赖新声明，也不将局部接受等同于学校语义正确、最终 Word 物化或发布。当前已进入第三次请求。


## 当前合同的自然修订闭环

PKU 前三批自然接受快照保存在 `pku-whole-entry-three-batches.json`：49 条判断中共有 21 个
whole_entry part，第三批同时包含整条声明与关键词的混合用途分段。快照核对输入、runtime、Skill
摘要均与启动 manifest 一致。这仍只是局部接受，不是全文语义或产品验收。

NJAU `njau-whole-entry-task` 首批 23 条判断中，纯空白条目将原文 36 个 U+0020 提交为 72 个。
Harness 当批拒绝；实际修订请求的 previous_submission 与原始 23 条判断完整相等，包括 14 个
whole_entry part。反馈指出第 36 个字符后原文已结束，并保留允许重新判断用途和字段的指令。
下一轮将空白数量改为 36 后通过局部检查、落档并进入下一批。共 7 条判断有内容变化，不能说只
修改了这一条；原始前后差异和请求/响应/拒绝/接受摘要均保存在 `njau-whole-entry-revision-context.json`。

此项为当前 runtime `6c72804` 的 **E2E agent loop 自然局部修订闭环**，无故障注入、无人改写
提交、未放宽检查；不代表完整 NJAU 生成或产品验收。三校进程继续运行，runtime / Skill 保持冻结。


## 证据读取的重复验证开销（隔离修复，未合入运行中版本）

当前真实工具审计记录到 PKU 两次 unit_evidence_packet 分别耗时约 58s / 52s。
只读性能分析 `_persisted_unit_reading_packet` 发现：一次正文阅读包读取会验证两次单元 proof，
合计解析 1,050 个源范围；每个范围又重复解析整份 525 条原文清单并计算绑定摘要。
带 cProfile 的本次测量为 90.12s、约 4.02 亿次函数调用，主要耗时落在重复全文反序列化。
这属于 Harness / Tool 的检查实现开销，不归因于 Agent 语义判断，也不以放宽预算处理。

隔离提交 **524d82e** 仅修改 `unit_source.resolve_unit_partition` 和回归测试：每次调用先完整
验证一份 canonical snapshot，然后每个范围只解析其对应条目，并使用刚验证的源摘要与清单摘要。
保留现有范围解析器、空结构映射、边界、完整分区和 proof 对照；无跨调用缓存、无语义修改、无身份方案变化。

验证层级：

- `logic/contract`：新增 8 / 32 条清单的解析操作次数上限，旧源码均失败（32 条为 3,072 次解析），
  修复后通过；来源、清单摘要、文字被篡改后仍拒绝，并且每次调用重新校验。
  混合跨单元文本与空结构范围同原全文解析器对照一致。相关 61 项通过；完整合同 **912 passed in 21.38s**；
  相关 Ruff 与修改源文件 mypy 通过。
- `real replay`：当前三校真实初始清单（PKU 525、HUNAU 599、NJAU 211 条）重新计算全部
  12 / 13 / 13 个单元，结果与各自原 accepted proof 的 Word 范围完整相同；对应阅读包不变，监测输入文件摘要不变。
  证据为 `partition-linear-validation-real-replay.json`。
- 同一 PKU 阅读包函数的隔离 cProfile 测量为 **0.76s、约 157 万次函数调用**。这是单次函数级
  对照，存在 profiling 和并行运行影响，不宣称整轮 E2E 按同一比例提速。

主工作区 runtime `6c72804` / Skill 仍冻结，三校 live 任务未使用此补丁；应在全部终止并核对摘要后合入。
当前 PKU 8 批、HUNAU 2 批、NJAU 7 批已局部接受；PKU 正修订缺失 field_id 的判断。
完整生成、正向最终发布和产品验收仍未完成。


## 文字修订时允许自然用途变化的证据

NJAU 当前运行的第 8 批先漏交 9 条源条目，补交后又在混合用途正文示例中少提交两个重复占位字符。
第二次修订请求完整保留前一份判断与源文。Agent 后续将该条从 3 个 part 改为 5 个 part，并把末尾
句号从 body_structure 改为 fixed_label；重新通过原文范围/词表检查后成为接受候选，进入下一批。
记录为 `phase5-three-schools/njau-whole-entry-body-revision.json`，绑定事件 34—44 及前后实际判断。

这是 **E2E agent loop 的自然局部用途修订**：文字检查失败没有冻结旧用途，修订后仍须重检。
该证据只证明修订权限和检查流程生效，不证明上述句号用途或新的分段方式符合学校语义，也没有
最终 Word / 发布 / 产品验收结果。没有人工改写候选或故障注入；性能补丁仍未用于本轮 live 运行。


## NJAU 完整输入终态：执行检查阻塞

`njau-whole-entry-task` 已终止（exit 2）：17 次请求/响应，13 批候选接受，4 次局部拒绝，
随后在全局执行准备检查中返回 `template_materialization_execution_unsupported`。未生成最终模板或
fill-contract，未进入页面复核。输入、runtime、Skill 摘要与启动 manifest 一致，终态见
`phase5-three-schools/njau-whole-entry-verification.json`；精确句柄 6092 已标记终止。
PKU / HUNAU 仍在运行，主 runtime / Skill 继续冻结；隔离性能补丁未合入。

终态摘要只列前 5 个 code，不能据此称有 5 处问题。完整 materialization.json 的 blocker 分类为：

- 8 个正文条目的重复 body_structure 成员，加上对应的 8 项同载体冲突；这些不是 16 个独立原因。
  实际判断是同一 body.paragraph 在一个段落中被 cleanup 格式说明分隔，需要分析执行器对同字段
  多段范围的支持，不能强迫 Agent 改用途绕过。
- 2 项 fill_slot / body.paragraph 不兼容，以及 2 项 body_structure / appendix.body 缺少结构父级。
  当前输入词表已经声明这些字段允许的角色；局部 shape 检查却只检查字段是否存在，未检查角色组合。
  这是阶段 3 仍需补齐的局部词表合同检查，应使用词表本身的 affordance，不能用字段名猜测语义。
- 1 项 cleanup 载体冲突，需核对实际范围及受保护对象，当前不放宽执行门。

这是完整输入的 **E2E agent loop 失败终态**，已证明工程阻塞保留判断、停止执行且不触发语义降级。
它不等于整校生成或产品验收通过。后续先修局部词表角色检查，再单独处理可解释的执行能力缺口。


## 局部字段用途检查（隔离提交 9949ca8）

NJAU 暴露的字段用途检查延迟已在隔离 worktree 修复，尚未合入运行中的主工作区。
每批候选、整体校验、诊断输出及持久 review 复用都使用共享校验器读取词表
`usage_affordance.allowed_part_roles`。不兼容组合返回可修订反馈，允许同时重审字段和用途；
缺失、重复或损坏的词表角色元数据归 Harness 并停止。未改 Skill、Registry 规则或学校语义。

验证层级：

- `logic/contract`：完整合同 **927 passed in 18.72s**；相关 Ruff、7 个改动源文件的 mypy 和 diff check 通过。
  Mock SDK 验证 65 条源文分批请求顺序为 64 → 修订同批 64 → 下一批 1；不兼容候选未被接受，
  实际下一次请求保留原提交及允许用途。词表元数据损坏时仅请求一次，停止且无候选接受。
  持久 review 即使同步重算了判断摘要与映射也不能绕过用途检查。
- 旧测试修正：目录测试补齐原本缺失的 system_generated 字段来源；手写不兼容 accepted review 的
  断言改为更早拒绝。编译器的缺少结构父级负向测试继续保留，没有跳过或放宽运行时校验。
- `real replay`：真实 NJAU 211 条原判断检出 4 个不兼容 part，局部与整体反馈一致，原始 task 文件摘要不变。
  证据 `acceptance-evidence/field-role-affordance-real-replay.json`；没有调用新 Agent，不是修订 E2E。

本补丁仍需合入后验证真实 Agent 对新反馈的修订。重复 body_structure 同字段接口与文本框 cleanup
执行能力不在本提交内，仍保持阻塞；不把检查前移视作完整生成成功。

## PKU 本轮预算终态

`pku-whole-entry-task` 已由精确句柄 79102 取得 exit 2，终态为
`semantic_query_time_budget_exhausted`。17 次请求、16 次响应、13 次局部检查、13 批接受、
3 次局部拒绝，未完成全部 17 批；保存的阶段时间预算耗尽，未生成最终模板和填写合同。
输入、runtime、Skill 摘要核对一致，证据 `phase5-three-schools/pku-whole-entry-verification.json`。
不能通过恢复任务重置预算；隔离性能补丁未用于该次运行，不能将其速度改善归给此结果。

HUNAU 精确句柄 84081 本轮仍确认运行；主 runtime / Skill 保持冻结，待终态和摘要核验后再合入补丁。


## 精确文本框清理与三校下一轮

HUNAU 旧任务由句柄 84081 取得 exit 2，终态为 `semantic_query_time_budget_exhausted`：
15 次请求、14 次响应、13 次局部检查、11 批接受、3 次局部拒绝，未完成全部 17 批。
输入、runtime、Skill 摘要核验一致，证据 `phase5-three-schools/hunau-whole-entry-verification.json`。
至此旧 runtime 的本轮三校全部终止，没有最终交付；此后才合入隔离提交。

NJAU 的 cleanup 冲突由真实 Word 范围确定：Agent 清理的是 `/body/p[53]/r[1]/pict[1]/shape[1]`
说明文本框，同段空白 paragraph 被保留。旧执行器把 shape 扩成段落删除，冲突门正确阻止了该操作。
隔离提交 `a6eed40`（主提交 `4bde3e0`）增加精确 VML shape 删除：只消费原始已接受范围，要求完整
覆盖 shape 文字，保留所在段落和兄弟节点。删除父段落危及保留子对象、或同段另有字段/文字重写时仍阻塞。
没有根据学校名称或说明文字决定删除，也没有改变 Agent 判断。

验证：

- `logic/contract`：完整合同 **932 passed in 18.36s**；新增 5 个 shape 测试覆盖保留同文兄弟形状、
  同段文字、段落及 section 属性、部分文字不能扩大删除、父段落删除和同段字段重写冲突。
  相关 Ruff / 3 个改动源文件 mypy / diff check 通过。
- DOCX 集成：锁定 OfficeCLI 1.0.143，物化集成组 `-k '0820 or single_value'` **9 passed, 43 deselected**。
  包含已有真实最小单元回放与构造 DOCX，用例各自层级不变，不是新 Agent E2E。
- `real replay`：`shape_cleanup_replay.py` 使用 NJAU 原 task、完整 inventory、原判断和映射，
  仅执行指定 shape 的 Tool 切片；原 task 不变。输出与原 DOCX 对照只有该 XML 节点删除，
  其他 XML 和包部件不变。证据 `shape-cleanup-replay/replay.json`；诊断文件不是完整物化或可发布模板。
- 主工作区全部 123 个 runtime Python 文件与隔离已测试代码逐字一致；合入后的无关 tracked diff
  摘要仍为 `0c00f4cd6ff845a24ba4a08535f537a961bb5ed0af22816c66a5f2f840a677dc`。

剩余执行缺口：同一段落中多段相同 body_structure 字段仍阻塞。不能只删除重复字段限制，因为现有
执行器会逐段创建独立填写控件；需要先闭合连续接口与多段来源的表达、执行和交接证据，不擅自合并或改用途。

新完整输入运行 `pku/hunau/njau-field-role-shape-task` 均在 `4bde3e0` 启动，固定 OfficeCLI 1.0.143，
沿用相同输入和已有 Skill，不复用旧 proof/判断/预算。句柄分别为 9028、91742、93517，已写入
`phase5-three-schools/observation-handles.json`；manifest 保存全部输入、123 个 runtime、11 个 Skill 摘要。
本轮验证新字段反馈、性能和 shape 能力，仍不能提前记三校生成或产品验收成功。


## 连续正文接口合并（隔离提交 cbefb17，未合入 live runtime）

已闭合重复正文接口的执行及交接表达：当已接受的 cleanup/style_only 分隔删除后，同字段、同用途
片段在同一 source entry、同一顶层段落和同一已接受单元内相邻时，物化为一个接口。
保留文字、其他字段、缺失片段、乱序、跨单元切点和复合载体都阻止合并；条件不满足的重复接口仍阻塞。
不根据正文 wording、学校名称或字段名判断，不更改原 parts / resolved spans。

接口以首段原始 span 为锚点；执行记录保存所有贡献 span 和被删分隔 span。发布端从原判断重算分组，
核对物化操作及独立持久化 receipt；消费端重验源范围、删除用途、邻接关系及单元切点。
含合并接口的嵌套 materialization provenance 使用 v2 并明确列出 coalesced_body_slot_refs，普通
单 span 产物仍为 v1，Fill Contract 顶层继续为 v2。不能把合并记录丢掉后伪装成普通单段接口。
该变更涉及执行器和共享产物校验，未改产品 Agent schema、prompt 或 Skill，也未改变原始源对象身份。

验证层级：

- `logic/contract`：完整合同 **954 passed in 18.06s**。随后补充独立持久化 operation/receipt 篡改
  和降级/缺标记用例，聚焦发布组最终 **11 passed in 0.31s**；全量 954 的记录早于最后两个新增用例，
  不改写成已跑过 956 项全量。相关 Ruff、6 个改动源文件 mypy、diff check 通过。
- DOCX 集成：固定 OfficeCLI 1.0.143 的相关物化组 **9 passed, 43 deselected in 3.36s**。
  构造 DOCX 证明说明删除后只生成一个 body.paragraph 控件，固定标点仍保留；实际消费者校验接受
  完整来源记录，拒绝贡献范围/删除范围/锚点缺失或篡改，即使重新计算外层摘要也拒绝。
- `real replay`：NJAU 原 task 的 17 个真实 body_structure span 在 8 个段落中形成 **8 个物理接口**；
  每个原判断与贡献来源保留，其余 **167 个段落**及所有选中段落属性不变，原 task 和其他包部件不变。
  证据 `body-interface-replay/replay.json`，使用已提交的 `body_interface_replay.py` 可重复执行。
  这是 Tool 执行切片，不是完整物化或新 Agent E2E；原候选其他不兼容字段仍未替 Agent 修正。

主 runtime `4bde3e0` 的三校进程本轮均由原句柄确认仍在运行，输入/runtime/Skill 摘要与新 manifest
一致。主 runtime / Skill 继续冻结，不合入此提交；在全部终态核验后再移植并做完整生成验证。
分层证据摘要：`acceptance-evidence/body-interface-validation.json`。正向完整发布与产品验收仍未完成。


## 当前 runtime 的自然字段用途修订闭环

PKU `pku-field-role-shape-task` 的第 10 批在事件 41 当批拒绝 4 处不兼容用途：
3 个 body.figure.caption 和 1 个 body.table.caption 被提交为 fill_slot，而输入词表允许 body_structure。
实际请求 42 保留了完整上一份提交和原始反馈；响应 43 修订后，局部检查 44 无反馈，候选事件 45
接受，然后请求 46 才进入下一批。四个受影响条目均有变化，修订后字段与用途符合当前词表。
该证据不判定修订后的学校语义本身正确，也不要求 Agent 只能改变用途而不能重选字段。

证据 `phase5-three-schools/pku-field-role-natural-revision.json` 绑定原始事件 38—46 的摘要及
前后判断，实际 prompt 的 previous_submission 与原输出完整相等。输入/runtime/Skill 摘要仍与
启动 manifest 一致；无人工改写或故障注入。这是 **E2E agent loop 的自然局部修订闭环**，
补齐字段用途前移检查的新运行证据，不是 PKU 完整生成或产品验收。

## 连续正文接口的正式发布路径验证

隔离提交 `6afff71` 在 `cbefb17` 上增加两项构造 DOCX 集成检查：实际调用正式发布函数，
通过真实 OfficeCLI 读取最终控件并执行样式捕获，落盘 Word / Fill Contract 后重新消费验证；
一处合并接口保留两个贡献范围和删除说明范围。若独立执行回执丢失合并来源，正式发布被拒绝，
输出目录不留下 Word 或填写合同。成功包仍为 `candidate_pending_human_acceptance`。

固定 OfficeCLI 1.0.143，`tests/integration/test_body_interface_publication.py` **2 passed in 4.82s**，
该文件 Ruff / diff check 通过。视觉检查使用明确标注的 synthetic contract fixture，并经过真实
visual gate 校验；这只能证明发布和持久化交接的 `logic/contract`，不证明实际页面看过或学校交付成功。
测试没有 monkeypatch 发布、样式捕获或消费者。主运行代码仍为 `4bde3e0`，未移植隔离提交。
三校输入/runtime/Skill 再次核验与启动 manifest 一致；原句柄均确认运行，等待各自终态。

## PKU 本轮完成判断后的工程终态

`pku-field-role-shape-task` 由精确句柄 9028 取得 exit 2。全部 **20 批**候选接受，
25 次请求 / 25 次响应，5 次局部拒绝，随后全局检查以
`template_materialization_execution_unsupported` 停止，未生成输出。
输入、runtime、Skill 均与启动 manifest 一致，证据 `phase5-three-schools/pku-field-role-shape-verification.json`。

终态 message 只列前 5 个错误码，不代表只有 5 个问题。正式持久化回执保留全部 **89 条**：
85 个 `body_structure` 字段位于两张表内部（`/body/tbl[5]` 44 条、`/body/tbl[6]` 41 条），
另有 4 处段落同时承载 `body.paragraph` / `body.figure` 接口。原候选完整回放与 runtime 回执
blockers 逐项相等，证据 `pku-field-role-shape-blocker-replay.json`。这是复合载体的确定性执行边界，
不能用放宽门禁、改变原用途或当前连续正文接口合并来解决。学校语义正确性仍需独立验收。
按计划将复合表格/图文接口列为独立能力缺口；本轮只证明准确停止和保留判断，PKU 完整生成仍未完成。

证据读取性能已有真实工具记录：旧 PKU 23 次 unit packet 调用 48.05–58.29 秒，本轮 23 次
0.511–0.652 秒。HUNAU / NJAU 当前观察分别 0.256–0.303 / 0.163–0.176 秒；后两校尚未终止。
原始记录摘要和逐条数值保存在 `acceptance-evidence/live-evidence-tool-timing.json`。
这是工具调用耗时观察，不是相同分批、相同模型输出下的整次 E2E 对照，不能宣称整体提速比例。

HUNAU / NJAU 原句柄 91742 / 93517 仍在运行，主 runtime / Skill 继续冻结。

## 隔离版本的 NJAU 完整验证启动

在隔离工作区 `template-harness-phase3/template-extraction` 的 `6afff71` 启动
`njau-body-interface-task`（runtime 为 `cbefb17`，后续提交仅增加发布测试）。这是新版本的独立
完整学校输入验证，未中断或重启旧运行。使用相同学校输入和 Registry，11 个 Skill 文件与主运行
逐字相同；唯一有差异的已有用户 Reference 原样复制到隔离区，不作为新语义修改提交。

精确句柄 **52301**，124 个 runtime Python 文件、全部 Skill / 输入和固定 OfficeCLI 的摘要在
`phase5-three-schools/njau-body-interface-manifest.json`。未复用旧 proof、判断或预算，仍使用
已有 MiniMax-M3 后端和原阶段预算。隔离 runtime / Skill 自此同样冻结。
该次运行验证连续正文接口能力能否推进完整物化和发布，不能提前认定学校语义正确或产品验收成功。

## NJAU 当前原候选完整回放与混合清理修复

原版本 `njau-field-role-shape-task` 由句柄 93517 取得 exit 2：全部 14 批接受，20 次请求 / 响应，
6 次局部拒绝，无发布。启动时输入/runtime/Skill 摘要全部一致。完整执行回执为 18 处重复正文接口
分别产生 ambiguous / carrier conflict 两类报告，另有 1 处 `materialization_intent_unclassified`。
证据 `phase5-three-schools/njau-field-role-shape-verification.json`。

将其原样判断回放到 `cbefb17`，全部 18 处正文接口问题解除，只剩未分类项；没有改变任何 parts。
证据 `njau-field-role-shape-body-patch-replay.json`。剩余原文位于 p[149]，Agent 提交 cleanup / style_only /
cleanup，未绑定致谢填写字段。编译器单独支持两类用途，却缺少两者组合。Agent 是否遗漏字段是另一个
语义质量问题，执行层不能自行补出 acknowledgement.body。

为保持两个 live 工作区版本冻结，在第三隔离区 `harness-style-cleanup/template-extraction` 实施
`ffbc7c1`：包含 style_only 且只有 style_only / cleanup 的 entry 沿用精确清理文字分支，保留段落和属性，
不升级为整段删除、不修改 accepted parts、不补字段。仅涉及 compiler、合同与测试，未改 Agent / Skill。

- `logic/contract`：新增混合清理正例修复前以原错误失败，固定文字反例已通过；修复后相关编译/计划/物化
  **92 passed**，readiness/receipt **23 passed**，相关 Ruff、单源文件 mypy、diff check 通过。
- `real replay`：NJAU 此次原始完整 inventory / judgments 经完整 materializer 生成诊断 DOCX，
  **24 项操作、55 项清理、193 条回执**。四个原输入/判断文件摘要不变。输出在
  `njau-style-cleanup-full-replay/`，候选摘要 `48f08a294bb2c5cad73ef12fdefd06d5c1a1d0f5e369f759d7657f09af6c09e4`。
  这是完整物化回放，未调用 Agent，不是 fresh E2E 或已发布模板，语义质量和实际页面仍待复核。
- 初次视觉准备因 Docker daemon 不可连接返回 `visual_renderer_unavailable`；已启动 Docker Desktop 恢复
  固定渲染环境，未放宽门禁。`visual-preparation.json` 保留该次环境失败。

`ffbc7c1` 尚未移植；HUNAU 原句柄 91742 与隔离 NJAU 句柄 52301 仍确认运行。隔离 NJAU 正在使用
`cbefb17`，不包含后来发现的混合清理修复，不能将其未来结果归给 `ffbc7c1`。

## NJAU 完整回放候选的实际全页复核

启动 Docker Desktop 后固定渲染环境恢复，第二次视觉准备成功：源文件 13 页，候选 12 页。
本次实际用 `view_image` 查看源 1—13 页和候选 1—12 页，逐页写入 5 项检查；没有用渲染成功或
页面数量代替视觉判断，也没有读取 Gold 或修改原判断。四项阻塞发现：

1. 源第 5、6 页的中英文摘要合到候选第 5 页，独立英文摘要页及其罗马页码 II 消失；需归因分页载体。
2. 源正文至致谢页的阿拉伯页码 1—7 在候选对应第 6—12 页不再显示；需核对页脚字段和执行操作。
3. 候选第 9、11 页仍有参考文献/学术成果目录的红色编写说明；待结合原判断判定语义或执行责任。
4. 候选第 12 页致谢只余标题，无正文填写接口。原判断明确 cleanup/style_only 且无字段绑定，
   该项需要语义重审，不能让编译器按学校文字偷偷补字段。

真实 review 为 `blocked`，completion gate 返回 `final_visual_review_not_passed`，未发布。
证据 `njau-style-cleanup-full-replay/visual-verification.json` 绑定候选、实际复核记录与原始页面证据。
这补充了完整真实候选的视觉阻塞证据；仍不是 fresh E2E、正向发布或产品签收。
源中既有的空白第 2 页仍保留，没有把它错误报告为本轮新引入的空白页。未观察到可见表格/公式的页面
不算复杂表格/公式能力验收。页码、分页和残留说明的归因是后续工作，当前不以“只是渲染差异”放行。


## 显式分页丢失归因、修复与合入（2026-09-24）

原始 NJAU 全文回放的英文 TITLE 段落在首个文本 run 前有显式分页符，位于 Agent 已接受的文字范围之外。
填写槽、正文接口、固定内容三个重复的段落重写函数均删除除 pPr 外全部节点，导致断点被一并删除。
本次统一为共享文字重写原语：保留首尾显式换页/换栏/换行节点、节点属性与 run 属性；不保留渲染缓存断点。
内部/嵌套断点没有输出边界映射时，以及仅有断点的空载体被插入文字时，在写候选前以 Tool 能力缺口停止。
没有增加学校 wording 规则，没有把页码数字猜成 PAGE 域，没有改原始语义判断或 Skill。

验证与限制：

- `logic/contract`：最初 12 项实际物化路径回归均复现断点丢失或未停止。修复后的第一次全文回放又发现空
  分节载体插入歧义，补第 13 项失败回归后修复。相关执行/编译/精确范围组 **117 passed**。
- 主分支合入后 `tests/contract` **971 passed / 20.72s**，mypy **125 源文件通过**。
  固定 OfficeCLI 的正式交接集成测试 **2 passed / 4.31s**；该测试使用构造 DOCX 和合成视觉证据，
  不计作真实学校发布或产品验收。没有宣称全仓回归全部通过，既有 student-content fixture 失败未在本次处理。
- `real replay` 中间版本：`njau-layout-break-full-replay/` 不改旧 NJAU 判断，完整物化恢复 3 个显式分页符。
  实际检查全部 14 页，中文/英文摘要恢复分开、I/II 恢复；但空段落 `source-entry-5a7ee0fa29188ed4e6471c4f`
  被原判断绑定正文接口，增加一页。说明残留、静态页码缺失、致谢接口缺失仍在，实际发布门拒绝。
- `real replay` 最终版本：`njau-layout-break-final-replay/` 与 `njau-body-interface-current-replay/`
  分别使用旧、新两轮未经改动的 NJAU 判断，均因空断点载体的插入侧不明确停止，未写候选。
  新一轮对应 `source-entry-302f1a067a3158c7f59204fa`，原文 `/body/p[115]` 只有断点与分节属性。
- `real replay` 最终版本正向切片：`njau-layout-title-tool-slice/replay.json` 直接执行新 NJAU 原始 TITLE
  判断；分页符仍在文字之前，其他 **174 段**与其他包内文件未变化，源输入/判断摘要不变。
  这是实际 Tool 执行切片，不是完整物化或新 Agent E2E。
- 隔离提交 `0d6bdb0` 已合入为 `0e1f774`；依赖的正文合并、混合清理也已合入，运行冻结解除后才执行合入。

## 完整运行终态与实际视觉复核

- HUNAU 句柄 91742：exit 2，20 请求/20 响应、15 批候选、5 次局部拒绝。
  最后失败为 `template_materialization_execution_unsupported`；输入、123 个 runtime Python、Skill 摘要无变化，
  output 为空。证据 `phase5-three-schools/hunau-field-role-shape-verification.json`。
  错误摘要含 unresolved 判断及表格内部接口，需要继续拆分归因，不能只凭前五条错误码统计全部问题。
- 隔离 NJAU 句柄 52301：exit 2，20 请求/20 响应、13 批候选、7 次局部拒绝；完整物化后由发布门要求视觉复核。
  12 页候选已逐页实际查看，13 页源渲染与此前完整复核逐页图片摘要一致。旧 runtime 的摘要分页丢失仍复现，
  同时存在正文页码缺失、参考文献示例说明和成果说明残留；致谢这轮已有接口，不能沿用旧轮“接口缺失”结论。
  真实 review 为 blocked，实际调用发布复核返回 `final_visual_review_not_passed`，output 为空。
  证据 `phase5-three-schools/njau-body-interface-verification.json` 及 task 内 `final-visual-review`。

下一步：先补齐空分页/分节对象的 Agent 可读布局证据和可执行插入边界合同，核对是否为输入信息缺口，
再通过语义重审或明确布局映射解决。继续处理 HUNAU/PKU 表格执行能力与 unresolved 归责；随后重新验证真实
完整候选及最终发布。不得将当前准确阻塞或摘要正向切片计作整校成功，阶段 4—5 与总体目标继续保持未完成。

## 源布局事实进入判断与修订输入（2026-09-24）

归因：新 NJAU 的空条目 `source-entry-302f1a067a3158c7f59204fa` 实际承载显式分页和分节属性，
原 Agent 阅读行仅有空文字；旧布局提示没有明确绑定到该条目。该缺口属于中立 Word 事实提取与
Harness 阅读包投影，不能先归咎于 Agent 忽略事实，也不能让物化器自行改用途。

修复提交 `aa5f42d`：按现有来源定位读取与源摘要绑定的 Word 结构，将可读 `layout_facts` 提供给
document_map、post-unit 阅读包和修订上下文；描述所在段落的物理事实，不推断学校语义，不引入
新源对象或改变原文/分区。渲染缓存分页不当作显式分页，局部映射失败明确标注事实不可用。
内部增加布局证据版本；旧缓存不能静默混入新事实后继续沿用既有判断，须保留历史并重新准备语义阶段。
不改变 Agent 输出 schema 或 Skill，不放宽空分页载体插入的 Tool 能力门。

- `logic/contract`：核心新增回归先复现空条目缺少布局事实；修复后全合同组 **975 passed / 19.32s**。
  覆盖初始/单元/修订输入、旧缓存停止且不改文件、过期源拒绝、显式断点与缓存/关闭属性区分。
  有关测试原先使用无效 DOCX 字节，已替换为有效的最小 Word 包，未降低生产校验。
  相关 Ruff 通过，mypy **126 源文件通过**。没有重新宣称全仓测试通过。
- `real replay`：`source-layout-replay/{njau,pku,hunau}/replay.json` 使用真实 task root、源文件与
  原 checkpoint 重新构造证据，再比对实际 document_map 输出。NJAU **211 条 / 12 条含布局事实**，
  PKU **525 / 16**，HUNAU **599 / 0**，均无映射不可用条目。原始输入、inventory、判断摘要不变，
  原文、对象身份和分区完全一致。HUNAU 的 0 只表示本次提取范围未发现相应显式事实，不代表没有版式要求。
- `E2E agent loop`：本补充尚未运行新的 Agent 判断，不用取证回放推断 Agent 已改正用途。
- `product acceptance`：仍未完成，未新增可发布学校模板。需新语义上下文验证空载体判断；原执行能力
  缺口和已有语义质量问题仍须按责任层继续处理。

兼容性风险：旧 task 的 post-unit 缓存会明确拒绝恢复，需新准备，不重置旧预算或覆盖旧账本。
证据边界：这些是显式 Word 结构事实，不能替代实际页面复核，也没有实现任意断点的输出插入侧映射。

## 表格内正文文字接口执行能力（2026-09-24）

HUNAU 完整原判断只读回放得到 **77 项阻塞**：76 项表内正文成员执行不支持，1 项字段语义未解决。
后者是“指导教师及职称”一个位置只绑定 advisor.name.zh，Agent 仍保留未能覆盖职称的 open_question。
原先执行问题与语义问题并存时按 Tool 停止是正确的，并非 unresolved 被单独误归 Tool。
原始证据 `phase5-three-schools/hunau-full-blocker-replay.json`。

三个假设的检查结果：定位确实把表内段落扩大到了顶层表，正文物化器也只接受 w:body 直接子段落。
76 个原始成员分属三个单元格，内容类型是 text/rich_text，可以按原精确段落执行；PKU 的 85 项则
是单元格文字绑定 body.table，涉及复合结构能力，不能与普通文字接口一并放行。

提交 `9c211c1` 涉及 Tool 定位/物化、Harness readiness、来源交接合同与测试，未改 Agent schema、
Skill 或学校语义。按原段落和父容器分组执行文字成员，表格、行、单元格、段落属性不动；原段落内建立接口，
不新增包裹层或移动单元格段落。表内其他 entry 的已接受清理继续执行。整表与内部接口同时占用、
表内非文字接口等情况继续以工程能力问题停止。

回归还发现单一正文接口会吞掉同 entry 的 fixed_label，已先复现后修复为按完整 accepted parts 重写；
同时保留首尾文字、分页保护和来源回执。相同字段的连续片段仍受同来源/同段落/同单元与保留文字边界约束。

- `logic/contract`：新增多单元格、正文顶层混合执行、同段固定标签、独立清理、父表与子段落冲突回归；
  **979 passed / 22.47s**。相关 Ruff、mypy **126 源文件**、diff check 通过。
- 正式交接路径：合同与固定 OfficeCLI 发布集成组 **16 passed / 8.55s**（其中 4 项正式发布路径测试），
  包括单元格内合并接口与丢失来源回执的拒绝。使用构造 DOCX、合成视觉证据，不是学校页面验收或真实发布。
  两个同名测试文件一起收集时曾冲突，集成文件已改名 `test_body_interface_formal_publication.py`。
- `real replay`：`hunau-nested-body-replay/replay.json` 使用原始完整 inventory / review 编译，保留全部
  阻塞，只执行 76 个原始表内文字接口。**508 个其他段落**未改，表格/行/单元格拓扑、段落及表格属性、
  其他包部件和原始输入/判断摘要均不变。源与诊断候选的 OfficeCLI **1.0.143** 校验都通过，记录在
  `word-validation.json`。没有检查这份诊断候选的实际页面，不能把包校验表述为版式通过。
- 完整 readiness 回放仍保留那 **1 项导师字段问题**，恢复类别准确变为 Agent semantic_revision。
  未删除 open_question、未强行补职称字段、未执行完整物化或发布。

新的完整运行分别冻结在独立工作区：

- NJAU：`harness-layout-evidence/template-extraction`，runtime `aa5f42d` / HEAD `62780c4`，
  句柄 **51598**，任务 `phase5-three-schools/njau-layout-evidence-task`。
- HUNAU：`harness-cell-interfaces/template-extraction`，runtime / HEAD `9c211c1`，句柄 **1720**，
  任务 `phase5-three-schools/hunau-cell-interfaces-task`。

两者均使用原三校输入、相同 MiniMax-M3、原 3600 秒阶段预算，126 个 runtime 文件和 11 个 Skill 文件
分别留冻结摘要。用户原有 Reference 原样复制，不作为本轮新语义变更；没有复用旧 proof、判断或预算。
运行未终止前不得修改各自 runtime/Skill，也不因一次观察超时重启。下一步读取这两轮真实判断和终态，
核对分页空载体与导师字段修订；继续处理 PKU 复合结构接口及实际候选视觉问题。总体目标和阶段 4—5 未完成。

同轮后续观察：NJAU 句柄 **51598** 已取得 exit 2，3 次 SDK 查询/反馈尝试后以
`unit_boundary_checkpoint_failed` 终止，未进入 post-unit。终态 checkpoint 的 15 个单元中，相邻
单元把同一条目同时作为前一单元的 end/end 与后一单元的 start/start，存在重复覆盖；实际拒绝仅返回
`unit_source_partition_invalid` 的泛化原因，未指出具体相邻单元。记录在
`phase5-three-schools/njau-layout-evidence-verification.json`；冻结输入/runtime/Skill 摘要全部一致，output 为空。
这不能验证新增布局证据的语义效果，也不能解释成布局修复引入源身份变化。下一步用该原始候选复现并检查
单元边界反馈的定位缺口，不能由 Harness 静默修改 Agent 的边界。NJAU 运行冻结解除；HUNAU **1720**
仍确认运行，其冻结保持。旧失败不重启、不覆盖，后续新验证须有明确修复依据。

## 单元边界反馈准确定位（2026-09-24）

提交 `37c26bd` 修复校验与反馈之间的信息丢失。旧解析器遇到第一处不连续立即抛出泛化 ValueError，
Tool 进一步统一为 unit_source_partition_invalid；Agent 无法得到出错单元、重复原文及原端点。
先验证端点，再对可解析的相邻区间收集全部可确定问题；无效引用/错误 split 单独定位到 units[index] 的
start/end 字段。无效端点不猜位置，其相邻区间无法确定时不虚报重复，但仍检查其他可解析单元。
反馈保留单元名称、原边界、精确源文（包括空条目）；App sanitizer 只透传这些可读字段，底层定位与摘要不外泄。
入口同步说明 start 在条目前、end 在条目后，不由 Harness 自动把 Agent 的端点改为另一侧。

- `logic/contract`：6 项新增用例先复现缺少诊断，包括连续多处重叠、首尾遗漏、同一条目内部空格的
  重复/遗漏、空结构条目、无效 split；也覆盖无效引用与独立重叠同时报告，以及修订后的有效 proposal 接受。
  全合同组 **985 passed / 19.36s**，相关 Ruff、mypy **126 源文件**与 diff check 通过。
- `real replay`：`njau-boundary-diagnostic-replay-verified/replay.json` 将终态任务的原 proposal 经实际
  Tool 和 Agent-visible 投影回放，原候选、源、Registry 和 task JSON 摘要不变；准确报告 **11 处重叠 +
  2 处无效端点**。之前记录的“14 对共享 included entry”只是原提交中的关系计数；其中涉及两个单元的
  目录条目引用根本不存在，不能把相邻三对都当作已计算证明的重叠。新版没有擅自猜该引用的正确替代项。
- `E2E agent loop`：新完整 NJAU 任务 `phase5-three-schools/njau-boundary-diagnostics-task` 在隔离工作区
  `harness-boundary-diagnostics/template-extraction` 的 `37c26bd` 启动，句柄 **2782**。
  已实际取得 status=ok 的单元 proof 并进入 post-unit，仍在运行；不以一次通过归因全部效果，也不宣称最终质量。
  使用原输入、MiniMax-M3、原 3600 秒阶段预算；126 个 runtime/11 个 Skill 文件冻结，用户 Reference 原样保留。
  未复用旧失败 proposal、proof、预算或注入 Gold。
- HUNAU **1720** 仍使用冻结的 `9c211c1`，已过单元边界，候选账本已有一个批次；不能把后来的边界反馈
  修复归给这一轮。新的 NJAU 与 HUNAU 均无已验收交付，阶段 4—5 保持未完成。

后续：继续读取两轮 post-unit 判断与终态，再处理原有 PKU 复合结构和页面阻塞。另需故障注入核对
unit_coverage 对源清单损坏的责任路由：当前源码将 ValueError 与 ToolFailure 放在同一 catch 中，可能把
内部状态问题也要求 Agent 重分单元；这是待验证的工程风险，不能凭代码阅读宣称已修复或真实发生。

## 单元边界工程失败归属与自然修订证据（2026-09-24）

提交 `1995017` 完成上述工程风险的故障注入、修复和回归。合法 proposal 配上损坏的 mapping_digest，
旧实现会把清单故障包装成边界修订：两个配置后端各进行 3 次查询/反馈，最后覆盖为后端耗尽。
这证明存在错误路由，不表示已在真实学校运行中自然发生过该损坏。

三层原因均已核对：Tool 的宽泛 catch 丢失失败类型；App 反馈函数继续吞掉 ToolFailure；
后端循环对所有失败进行切换。现在先检查工程清单，再检查 proposal；工程异常穿透反馈层、结束检查计时，
停止当前阶段，不消耗语义次数。两个运行入口共用后端切换条件，只允许超时、后端 API 或可重试模型响应
失败切换；工具不支持、工程状态损坏、语义预算耗尽保留原失败。未改 SDK runtime、Agent schema 或 Skill。

- `logic/contract`：13 项新测试覆盖实际服务、模拟 SDK 响应后的真实反馈路径，以及两个后端选择入口；
  工程故障只产生一次查询、零次语义重试、无切换、无发布，原 proposal 不变，失败与计时正确留存。
  API 401、超时、模型无效响应仍能切换；可重试标志不能让 Tool/预算故障绕过归属。
  全合同组 **998 passed / 18.22s**，相关 Ruff、mypy **126 源文件**、diff check 通过。
  两项旧测试此前未建源清单而依赖泛化反馈，现分别提供有效清单测试语义反馈、验证缺清单异常仍只读。
- 真实输入故障注入：`njau-boundary-host-failure-replay/` 使用新 NJAU 已接受的 **15 个单元**及真实清单，
  仅在独立副本损坏映射。Tool 和 App feedback 都保留 initial_source_inventory_invalid / harness，
  恢复副本映射后相同 proposal 重新通过；原输入、清单、proof、Registry 摘要均不变。
  没有调用 Agent，不算自然 E2E 或产品验收；新修复尚未用于新的真实 Agent 运行。
- 自然 `E2E agent loop` 局部证据：HUNAU 冻结 runtime `9c211c1` 首批 23 条判断的第一条把 U+201C
  弯引号抄成 U+0022 直引号。事件 3—9 保存原响应、局部拒绝、实际修订请求、新响应、局部通过和候选版本。
  Agent 修正了原文，cleanup 用途未变。`hunau-cell-interfaces-natural-revision/verification.json`
  对事件 1—9 的副本运行实际 journal 恢复，核对事件链、候选父版本、提交与差异一致；原任务未改。
  仅证明局部反馈修订闭环，不能替代全部学校判断、物化或页面验收。

HUNAU **1720** 与 NJAU **2782** 均通过本轮实际句柄轮询确认仍运行，分别继续使用 `9c211c1` 和
`37c26bd`；各 126 个 runtime / 11 个 Skill 文件、输入和固定 OfficeCLI 摘要均复核不变。
HUNAU 已有 3 个记录候选批次；NJAU 已有 2 个记录候选批次，继续后续判断。没有因观察超时重启或修改运行版本。

剩余事项：单元边界阶段的 `_sdk_receive_event` 只记录结构化输出存在与状态，工程失败分支未保存完整
proposal，正常修订也没有完整逐轮请求/响应账本；只在次数耗尽时保存末版。这是已核对的记录缺口，
下一步需在该阶段补齐，不读取或保存隐藏推理。继续完成两校终态验证、PKU 复合结构能力及最终页面阻塞。
阶段 4—5 与总体目标保持未完成；已有无关 tracked diff 摘要仍为 `0c00f4cd6ff845a24ba4a08535f537a961bb5ed0af22816c66a5f2f840a677dc`。

## 单元边界逐轮记录（2026-09-24）

提交 `f7c9370` 补齐上一轮确认的记录缺口。三个实际 loop 测试先证明：拒绝后通过、请求中断、工程
检查失败都没有完整逐轮记录。原 `_sdk_receive_event` 只保留状态和长度；次数耗尽时仅存末版，正常
接受还会向提交对象增加 resolved_units，不能把检查后的对象冒充原提交。

新增 `UnitBoundaryJournal` 仅记录领域证据，不管理 SDK session 或生成循环。请求发送前保存实际 prompt
与反馈，收到 ResultMessage 后且检查前保存原结构化提交和可见正文，保存前后版本差异及检查结果。
每次执行有独立 UUID 目录；原文件不覆盖，原文深拷贝，hash 链绑定输入、初始清单和后端。隐藏推理不记录，
API 失败只保留安全元数据。普通日志/执行摘要引用该目录，不复制完整对话。日志写入失败归 Harness，
不得继续调用模型、检查或写入通过证明。失败记录本身写入失败时，执行摘要同时保留原故障和记录故障。

新分区 proof 的 revision_evidence 绑定接受 review；checkpoint 事件先持久化，再写 proof。恢复读取
校验事件顺序、摘要、差异、原提交和实际 proof 一致。缺失/损坏记录拒绝恢复，原始未通过提交不能自动接受。
旧 proof 没有该字段时仍按既有身份合同检查；历史缺失的逐轮消息保持缺证据，不伪造或静默升级。

- `logic/contract`：10 项新测试覆盖真实 Tool 检查配合模拟 SDK 响应、发送前/检查前实际落盘、拒绝到通过、
  needs_input 后中断、工程失败、5 处写入故障、独立执行不覆盖、损坏历史拒绝恢复、API 及隐藏推理边界。
  全合同组 **1008 passed / 18.48s**；相关 Ruff、mypy **127 源文件**、diff check 通过。
- `real replay`：`njau-boundary-journal-replay/verification.json` 使用 NJAU 旧边界失败 task 的末版原提交，
  与新 task 已接受的原单位边界；两者源文档和初始清单一致。通过实际 Tool/App feedback 和新 journal
  记录 6 个事件、15 个单元位置差异，重新读取验证成功；原任务、输入及清单摘要不变。
  这是两个历史候选构成的显式 replay 序列，prompt 为当前构造，未调用模型，不能当作历史逐轮对话或自然 E2E。
- `E2E agent loop`：新 journal 尚未用于新的真实 Agent 运行。现有 HUNAU **1720**（`9c211c1`）和
  NJAU **2782**（`37c26bd`）再次通过实际句柄确认仍在运行，已分别有 **6 / 7 个**候选批次。各自
  126 个 runtime / 11 个 Skill 文件、原输入和固定 OfficeCLI 摘要仍一致，未修改或重启冻结运行。
- `product acceptance`：仍未完成，无新增整校交付。下一步读取两轮终态、继续处理 PKU 复合结构与实际
  页面阻塞；后续有依据的新运行再验证新 journal 的实际持久化与恢复。总体目标保持进行中。


## 初始 Word 顺序与容器包含关系（2026-09-24）

提交 `7df1192` 修正首次 canonical 清单生成前的对象顺序。原 inspect 按文字、图片、表格类型分桶，
PKU 两张正文表的父条目排在全部文字之后，落入声明单元；子文字却在第二章。App 现在从绑定 Word 的实际
XML 位置排序，再生成初始身份。没有改 ID 生成协议，但位置是 ID 的组成部分，因此三校新任务共 1176 个 ID
与旧任务不同；不能复用旧 proof/判断。旧任务保持不变，产品恢复入口对缺少 source_order_version 明确拒绝。

- `logic/contract`：先复现实际 prepare 接缝的错序，再验证表格/图片与真实相邻段落顺序、对象事实不变、
  不可定位与输入不符拒绝、旧任务不静默重排。该提交全合同组 1011 passed / 18.89s，mypy 128 源文件通过。
- `real replay`：三校分别 525 / 599 / 211 条目；source-document-order-verified/{pku,hunau,njau}/
  对照旧对象只读重排与固定 OfficeCLI 1.0.143 的全新实际 prepare，canonical 结果完全一致。
  实际准备目录 source-document-order-prepare/ 未调用 Agent；不能称为整校 E2E。

提交 `aefe343` 继续修正“父条目自身文字为空”容易被理解成“整个容器为空”的输入缺口。
原 PKU tbl[5]/tbl[6] 分别有 45 / 43 个后代条目，其中 44 / 41 条有文字；原父阅读条目只显示空字符串。
实际 Word XML 证明这些后代全部位于父表格内部，排除源映射缺失。两个新增接缝测试先复现初始阅读包和
修订上下文缺少关系。现在从实际 XML 祖先关系投影 structure_context，列出祖先/后代的源 ID、类型和完整原文，
并说明关联内容仅为上下文，不属于当前条目的文字或可编辑范围，也不能由物理包含关系确定角色/字段。

修改层面：Tool 提供物理事实；Harness 构建初始/单元/修订输入并过滤底层引用；App 检查缓存证据版本；
Contract 与测试固定职责。未改变 Agent 输出 schema、Skill、语义角色或已接受判断，不扩大 materializer 能力。
旧阅读包缺少 structure_evidence_version 时保留历史并停止恢复，不能继续向 Agent 提供不完整输入。

- `logic/contract`：包含空子条目、嵌套表、同文无关段落、旧缓存拒绝、输入绑定、引用过滤、修订范围不扩大。
  全合同组 **1014 passed / 20.86s**；相关 Ruff、mypy **129 源文件**及 diff check 通过。
  首次全组 7 项失败均来自仍缺结构版本的旧合成阅读包工厂；工厂显式提供空结构上下文，未弱化产品门禁。
- `real replay`：source-structure-replay/{pku,hunau,njau}/verification.json 对实际源和已接受分区构建
  新上下文，核对 document_map 与单元视图一致。1335 条身份、文字和分区均不变；三校分别新增 213 / 356 / 26
  条物理包含关系，共 595 条，无不可解析条目。原 task 的输入、清单、proof、判断摘要不变。
- 风险：完整关联文字使三校上下文分别增加约 142 / 223 / 17 KB（含字段和说明），实际模型成本与语义改善
  未验证；不能因结构关系已送达，就宣称原有 body.table 判断或执行阻塞消失。

两项旧真实运行本轮已取得终态：HUNAU **1720** exit 2，9 次候选记录、14 次 request/13 次 response，
因 semantic_query_time_budget_exhausted 停止；NJAU **2782** exit 2，15 次候选记录、21 次 request/response，
因 5 项 materialization_body_structure_member_crosses_carriers 停止。数字是事件计数，不等于不同批次数。
各自 126 个 runtime / 11 个 Skill 文件与两个输入摘要复核一致，失败仍归正确责任层，无最终交付。
详细终态在 phase5-three-schools/ 下相应 observation.json；不要继续轮询这两个终止句柄。

新的真实 PKU 完整输入运行：**38646**，task 为 phase5-three-schools/pku-source-structure-task，独立工作区
/Users/xpw/.codex/worktrees/harness-source-structure/template-extraction，冻结 runtime **aefe343**。
129 个 Python / 11 个 Skill 文件留摘要；用户已有 Reference 原样复制，未增加语义修正规则；仍用 MiniMax-M3、
3600 秒阶段预算及原输入，不复用旧 proof/判断/预算，不读 Gold。本轮实际 write_stdin 确认仍运行。
该运行同时验证新边界 journal；结果未出，不能宣称新输入导致正确判断。运行期间不修改该隔离版本。

下一步：读取 PKU 新运行的实际判断和边界记录；诊断 NJAU 五项跨载体接口，完成实际 DOCX 全页复核和
三校产品验收。阶段 4—5 和总体目标保持未完成。主工作区 79 项原有无关修改保持不变，diff 摘要仍为
0c00f4cd6ff845a24ba4a08535f537a961bb5ed0af22816c66a5f2f840a677dc。


## 完整执行诊断与真实边界记录核验（2026-09-24）

提交 `04ff044`。继续读取 NJAU boundary-diagnostics 的完整 materialization.json 后，更正上轮“5 项
跨载体阻塞”的描述：真实反馈有 **9 项**，其中 **7 项**来自 footer 中的静态数字绑定 body.paragraph，
**2 项**是同一载体的删除/保留冲突。旧终态 message 只连接前 5 个 code，没有总数或截断提示。
readiness 又把 supported carrier 数为 0 和大于 1 合并报成 crosses_carriers，误导排障方向。

先验证 3 个假设：页脚事实没有进入阅读包、可见投影丢失区域线索、Agent 已知页脚仍选错字段。
原包 style_summary 含 footer，原 Agent reason 更明确写明页脚页码，却选择“最接近”的 body.paragraph，
并假设渲染器会把数字换成 PAGE 域。这支持第三项，不能通过新增页脚正文接口来实现这个无依据承诺。
输入词表中 body.paragraph 的含义是普通正文段落流，不能把 content_type 相同当成语义相同。
两个 cleanup 冲突还涉及表格内部保留内容、空段与图片载体，不能无检查地删除外层载体来消除阻塞。

工程修复只调整诊断：0 个支持载体明确报 carrier_unsupported；真正多个载体仍报 crosses_carriers，
附 supported_carrier_count。两者仍是 Tool 能力阻塞，不改 Agent 判断、不开放执行、不消耗语义重试。
终态摘要按所有类别汇总数量，明确总数，不再用前五条伪装完整列表。

- `logic/contract`：先复现零载体误报、摘要遗漏后续类别；正反例区分零载体与两个真实支持载体。
  全合同组 **1017 passed / 22.93s**，相关 Ruff、mypy **129 源文件**及 diff check 通过。
- `real replay`：njau-execution-diagnostics-replay/verification.json 将原 211 条真实判断与原映射重新校验，
  新反馈为 7 项无支持载体 + 2 项冲突，总数与受影响范围均不变。源、词表、清单、proof、判断及原终态摘要不变；
  没有调用 Agent、物化或发布。这只完成反馈修复，不证明 NJAU 产品可用，也没有宣称页脚语义已纠正。

PKU **38646** 仍在冻结 `aefe343` 上运行。已取得自然运行的 status=ok、**17 单元** proof：
1 次 SDK query、0 次边界反馈，事件 request/response/review/checkpoint 共 4 条；通过实际 journal 链和
_validate_unit_boundary_checkpoint 重新验证，无副作用，原摘要不变。证据在
pku-natural-boundary-journal/verification.json。这证明新 journal 在真实首版通过路径上工作，未验证
自然边界修订或故障恢复；不得与已完成的注入/回放测试混称。

新 PKU 两张父表已实际位于 unit-10-ch2，阅读包分别保留 45 / 43 个后代关系。该观察与新原文顺序一致，
不把一次模型结果视为可靠性统计。post-unit 已有 2 次候选记录并继续后续请求；完整学校、最终 DOCX 与
产品验收仍未完成。129 个运行 Python 文件、11 个 Skill 文件和原输入摘要再次核对未变。
主版本诊断修复不修改正在运行的隔离版本；当前唯一运行句柄是 38646。

下一步继续实际 PKU 判断与最终执行；页脚生成语义如何由现有合同正确表达、两项 cleanup 冲突的实际执行范围
需要单独归因。不能把诊断改善或准确停止统计为完整生成成功；总体目标仍进行中。
