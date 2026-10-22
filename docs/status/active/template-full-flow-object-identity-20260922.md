# 全流程源对象身份验证 — 2026-09-22

本文记录 2026-09-22 的身份专项验收基线；当前分区版本与正文/辅助 story 合同见 [模板提取 Contract](../../contracts/template-extraction.md)。

状态：**ACCEPTED，身份专项工程验收收口。** 验收以
[唯一计划](../../plans/template-field-id-vocabulary-boundary-refactor.md)的 2026-09-22 三步门为准。
只验收原对象及实际范围不被替换；学校语义和版式的全面产品验收不在本任务范围。

## 当前结论

首次功能区划分已经接入原始源对象清单，代码不再等分区结束后建立身份。Agent 负责理解可读文本、
视觉线索和分区语义，使用系统给出的 `source_entry_id` 指认对象；Harness/Tool 以同一初始清单
验证对象、计算范围并执行。Registry `field_id` 仍是填写内容种类，不是源对象身份。

统一合同已落到运行时代码；真实封面写入、声明页保留、发布/恢复已有证据。本次复核把样本生成
失败与身份缺陷拆开，并补齐同一对象跨功能区后的实际写入核验，未发现新增身份缺陷。
历史后半段 30/32 replay 和 261 槽不计为新成功；失败样本仍失败，未知阶段仍未知。

运行时提交：`9ad1d87 refactor(template): bind the full flow to immutable source identities`。

## 实现边界

- 首次 Agent query 前持久化 `docfit-initial-source-inventory/v1`，任务 manifest 绑定原始摘要。
- 功能区 `docfit-unit-boundary-proof/v2` 使用原对象 start/end/split；对象内 split 的前后原文
  必须精确拼接成原对象全文。Agent 不计算 offsets/hash，也不选择 Word locator。
- 后续 reading packet 和 batch 只投影初始清单；跨组对象保持原 ID、唯一批次归属及完整分区上下文。
- 恢复、语义审核、实际执行和发布消费均重核初始清单、分区范围、accepted span 及 Word fragments。
- 删除旧页码/文字锚点定位入口，拒绝旧 proof、缺初始绑定、独立 target 覆盖和自动转换。
- Word 包部件解析覆盖正文、页眉/页脚、脚注/尾注和批注，严格按实际部件关系及对象位置解析。
  不通过文件名编号猜测页眉，也不在其他部件搜索相同文本。

## 证据分层

| 层级 | 已取得证据 | 限制 |
| --- | --- | --- |
| 文档 / 合同 | `64d8948` 冻结完整合同与删除清单；`b866084` 对齐模块、Contract、ADR、测试入口；12 项文档检查通过 | 不代替运行时 |
| 真实输入准备 / Tool 投影 | HUNAU 599、NJAU 211、PKU 525 个源对象，共 1,335 个；每页 3/17/200 项读取 ID 和顺序一致，初始清单与输入字节不变 | 不代表 Agent 判断或实际写入 |
| 真实输入机械分区探针 | 三校均以原 ID 将一个对象分到两个相接区间，保持完整覆盖 | 边界由测试构造，不是 Agent 语义 replay |
| 真实原文映射 | 正式执行器映射逻辑解析三校共 3,318 个 Word 片段，全部定位和原文匹配 | 不代替实际写入 |
| real replay（拒绝链） | 新 PKU Agent 真实判断在执行前拒绝两个整表 fill_slot；未产生候选文件 | 证明失败安全，不算成功物化 |
| E2E agent loop / 保留链 | HUNAU 原始声明页：首次分区 → 35 对象/37 spans → 发布成功；公开恢复成功 | 0 填写槽、原文直接保留，不算实际写入成功 |
| E2E agent loop / 写入链 | NJAU 原始封面从初始清单分区，经真实反馈修订，完成 59 对象/67 spans/10 槽发布 | 该任务在切换工作树中启动；最终提交下重放与恢复另行核验，不冒充所有样本成功 |
| real replay / 产物身份核验 / 写入链 | 使用上述新真实判断从原始 DOCX 重新写入，所有 XML 部件与发布结果一致；35 个未选中段落、38 个未选中部件、8 个填写段落内的原文与槽顺序通过；最终代码的公开恢复通过 | 不包含学校语义和视觉质量签收 |
| 产物身份核验 / 保留链 | 声明页 source/final 字节完全一致；发布来源、原对象及范围、未选中 XML 和包部件检查通过 | 不是 Word UI / 视觉验收 |
| 本次 real replay / 产物身份补核 | NJAU 原判断重新物化后仍与发布文件相同；9 个普通槽、1 个整表结构槽及局部空格清理独立核验通过；48 个未选中段落、38 个包部件保持不变；声明页保留链复核通过 | 不表示新的 Agent 运行或产品验收 |
| 真实输入机械写入补证（logic/contract + actual DOCX mutation） | 原 NJAU 对象跨 2 个分区，原判断不改；正式 Harness 投影/接受/解析后两次实际写入与原发布包 39 个部件全部一致 | 分区切点由测试构造；不是原 Agent 分区 replay，也不是新 E2E |
| 失败逐项身份审计 | 5 次新失败、2 条历史记录按已到 checkpoint 分别核对；已接受链未发现换对象/错范围 | HUNAU 候选原文错误被拒；NJAU07 原快照缺失，不能认证历史实际写入 |

自动验证：相关 contract/Agent/计时复测共 **768 passed**；确定性集成 **56 passed**；最终 Skill/发布/回执组 **95 passed**；
严格 mypy 检查 115 个源文件通过，相关 Ruff 检查通过。完整普通测试一轮为
**1,194 passed / 1 failed / 1 deselected**：未修改的可观测性计时测试在负载下超过 20ms 门限，
随后与上述专项一起重跑通过；另一个学生内容测试因原有缺发布来源的 fixture 失败，已在原 HEAD
归档副本复现，因此该轮明确排除。不能把这轮表述为全仓零失败。
NJAU 有实际填写槽的样本已验证。本轮 7 次新 Agent 运行中，2 次完成（1 条填写链、1 条原文保留链），5 次未完成；重复尝试单列，不能当作 7 个不同输入或全矩阵通过。

证据目录：`temp/full-flow-id-20260922/`。脚本已保存在
`tests/manual-diagnostics/template-full-flow-identity/`，说明每项证明范围。

机器记录：`initial-read-proof.json`、`unit-projection-proof.json`、`word-mapping-current.json`、
`initial-binding-negative-probe-fixed.json`、`pku-replay-fail-closed.json`、`integrity-identity.json`、
`njau-cover-identity.json`、`njau-cover-resume.log`、`published-target-negative.json`、`live-run-matrix.json`、`independent-prepare-proof.json`（声明页在锁定 OfficeCLI 下独立准备，35 个对象身份及清单相同）。初版 `word-mapping-prototype.json` 仅为历史原型探针；正式映射以 current 文件为准。

## 集成审查与修复

1. 初始清单删项后重算自身摘要曾可绕过原任务摘要；manifest 缺失时也曾放行。
   已强制读取和比对原任务绑定，缺 manifest 直接拒绝；合成拒绝测试和真实任务副本探针覆盖。
2. 完整清单包含页眉，而旧执行器只读正文；新 PKU 实跑首次在此失败。
   已接通包部件映射；真实 3,318 片段检查通过，自动测试验证同文重复、关系顺序和只改选中部件。
3. 发布包中的两份 provenance 曾可能一同改 locator 并重算摘要。
   已从初始清单重新解析每个已发布 span，核对 Word fragments，并拒绝跨已接受分区切点。
   NJAU 实际发布包的独立篡改探针同样拒绝，见 `published-target-negative.json`。
4. 新 PKU 判断将整表作为段落填写槽，执行时不能获得唯一段落。
   已改为 readiness 阶段返回 `materialization_slot_carrier_unsupported`，不得另选子段落；
   真实判断 replay 确认在写入前拒绝。尚不表示 Agent 已完成修订并成功发布该样本。

## 失败与保留记录

- HUNAU 封面、正文新运行：首次分区均收到反馈并修订通过，分别为 1 区/28 对象、10 区/71 对象。
  后续模型修订连续两次耗尽约 32,000 输出 token 而无可用文本。监督停止对应 SDK 子进程，
  runtime 返回 `semantic_batch_result_invalid`。两次运行均未完成，不计成功；见
  `cover-provider-limits.json`、`body-provider-limits.json` 和各自 trace。
- PKU 封面新运行：5 区/58 对象，新真实判断完整返回，但旧包部件解析失败。
  修复后 replay 进一步暴露整表填写承载不支持；现在提前拒绝，仍不计成功。
- PKU 英文摘要首次新运行在 180 秒无进展门限中止，尚未产生 accepted 分区。保留失败；
  仅一次新任务放宽到 600 秒等待，默认 runtime 配置未修改。重试接受 5 个分区，
  经过 13 次 SDK query、7 次反馈仍未收敛，最终 `semantic_batch_global_feedback_failed`。
  最后明确阻塞：`source-entry-71f352c9ee7a9854dd06e08e` 是 `/header[7]` 中的文字，
  Agent 将其判断为 `body.heading.outline1`。Harness 以真实源身份拒绝将页眉当作正文承载，
  未寻找其他正文对象替代，也未发布；见 `pku-abstract-final-readiness.json`。这是语义责任/执行
  承载未收敛，不是 ID 被换成另一对象；仍不计成功。
- 组合最小输入的构建脚本产生未声明的 Markup Compatibility 前缀，输入准备拒绝；不弱化校验。
  原始六个最小输入和三校原始模板均通过 package 校验，后续使用原始输入。
- 旧 PKU 任务缺初始清单，旧发布包缺 `source_partition`，新读取/消费明确拒绝，无自动升级。
- 历史 NJAU 03 执行冲突、NJAU 07 原快照缺失仍保留；不计入新成功矩阵。

## 失败归因与验收范围纠正

本次只读审计核对初始绑定、已接受分区、候选原文、最终语义范围及实际源 Word 片段。
机器记录：`temp/full-flow-id-20260922/identity-closure/failure-audit-verified.json`。

| 记录 | 已核到的身份链 | 未完成原因 / 未知阶段 | ID 阻塞处理 |
| --- | --- | --- | --- |
| HUNAU 封面 | 28 ID / 28 分区范围 / 124 Word 片段一致 | 8 个候选对象改引号或漏原文，严格拒绝；后续模型无可用输出，未 accepted、未写入 | 移出；保留 Agent 原文表达与 provider 修订失败 |
| HUNAU 正文 | 71 ID / 71 分区范围 / 260 Word 片段一致 | 12 个候选对象遗漏原文或提交空 part，严格拒绝；未形成最终 review、未写入 | 移出；不能说候选范围全正确 |
| PKU 封面 | 58 最终范围 / 72 Word 片段与原清单一致 | 原两个整表被要求当普通填写槽，readiness 拒绝，未改选子段落 | 旧部件解析问题已修；当前操作不支持移出 ID 阻塞 |
| PKU 摘要首次 | 42 初始对象绑定一致 | 无进展超时，没有 accepted 分区，后续阶段未知 | 移出；不计写入成功 |
| PKU 摘要重试 | 42 ID / 45 最终范围 / 61 Word 片段一致 | 原页眉被要求当正文标题，写入前拒绝 | 移出；不是对象替换 |
| 旧 NJAU03 | 30 后半段范围 / 146 Word 片段一致 | 清理与保留的承载冲突；语义选择还是检查过严仍未确定 | 移出；旧记录不计新全流程证据 |
| 旧 NJAU07 | 20 后半段范围与持久化原文自洽 | 当前源 SHA 不等于旧账本，原始快照缺失；实际源/写入未知 | 作为历史缺证据移出；不计成功，不猜测 ID 漂移 |

PKU 摘要重试的唯一最终 blocker 仍是 `source-entry-71f352c9ee7a9854dd06e08e`、
`text[0:10]`、原文 `第三章\t其他注意事项`，位置 `/header[7]/p[@paraId=49237ED9]` 及其 runs。
其 `body.heading.outline1` 操作不可执行，不影响已核实的对象身份一致性。

## 收口补证与限制

补证复用 NJAU 的真实初始清单和原 Agent 判断。在
`source-entry-d9616f4db3dd070938de96e3` 的既有 part 边界 22 处构造分区，得到同 ID 的
`[0:22]` / `[22:39]`；原两个填写范围仍为 `[5:22]`、`[24:39]`。正式 Harness 接收原候选后，
accepted judgments 和全部 resolved spans 与原证据逐字段相等，共享对象只有一个 batch owner。
两次从磁盘重读再实际写入，两个槽仍在原 `tbl[1]/tr[1]/tc[1]/p[14]`，输出包与原发布一致。
原任务全部 18 个证据文件 hash 未变。

产物核验同时补查原表格槽的位置与表格结构、原非槽段落的一字符清理；原来因整表被选中而
跳过的 13 个未修改子段落也加入保护检查。故未选中段落核验由 35 个增加为 48 个。
故意改错表格槽引用、恢复应清理空格的两个产物探针均被独立核验拒绝。

本次不改运行时代码，不手改学校语义，不弱化 readiness。对应缺口在测试/验收证据层，
已用实际 Word 写入补齐。现有 fresh E2E 证明真实 Agent/反馈/发布/恢复接线；跨区机械补证证明
其确定性身份不变量。二者组合支持 **ID 专项工程 ACCEPTED**，不要求每个学校样本都生成成功。

明确限制：跨区切点尚无 Agent 自主产生的完整 E2E；页眉/页脚尚无本轮 fresh 实际写入成功，
其映射、合成写入合同和不换对象拒绝链各自取证；NJAU07 历史写入无法认证。以上均不转成新的
学校语义成功门槛。学校字段判断、所有操作类别及视觉版式的 product acceptance 仍未完成。

新增证据根：`temp/full-flow-id-20260922/identity-closure/`；可重跑脚本与精简证据摘要位于
`tests/manual-diagnostics/template-full-flow-identity/`。本次专项 contract **31 passed**、文档合同 **12 passed**；
诊断脚本 Ruff 通过；原文保留、真实判断 replay、跨区实际写入及失败审计分别记录，互不替代。

NJAU 新封面源 SHA：`8b2e3b15d9d85ef81e4d1e84dae1764b6eca636c5992932b465299ce68bd8268`；
发布与当前代码 replay SHA：`c777a96d0730ac6b37d634f17507007c77205dd515da176e4a1260f1991c9d60`。
不能以字段名变化、测试数量或单次生成文件代替证据。
