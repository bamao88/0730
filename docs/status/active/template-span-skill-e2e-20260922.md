# 模板 Span Skill 的真实 Agent loop 验证（2026-09-22）

## 产品结论

本轮使用修改后的 Skill 运行真实 `prepare-template`，验证 Agent 能否从真实学校模板出发，
完成范围判断、接收 Harness 反馈、修订判断并生成可填写模板。

两个用例的 E2E 均未通过，都没有得到被接受的全量语义结果，也没有生成
`final-template.docx` 或 `fill-contract.yaml`。正文真实反馈曾修复 3 条原文范围问题，
但最终因精确文本修订改变了已锁定的语义责任而退出。
本轮证实了反馈能够触发候选修改，尚不能证明 Skill 已解决 Span 准确性问题，
也不能进入产品验收。

## 验证范围与复现身份

- 代码基线：`e32e76e5c12ab902950d80f3bb5a4e5264ead6e3`。
- 输入：HUNAU 真实最小单元 `01-cover`、`04-paper-body` 的 DOCX、学校要求 PDF 与 Registry；
  通过现有 `build_input_package.py` 构建，只向产品 Agent 提供输入包，不提供 Gold 或本次观察结论。
- 实际产品 Agent：配置中的 `MiniMax-M3`，adaptive thinking、low effort；
  **这不是 GPT 模型的 E2E 结果**。
- 运行依赖：Claude Agent SDK `0.2.128`、锁定的 OfficeCLI `1.0.143`、
  LibreOffice `25.2.3.2`。Doctor base gate PASS；overall NOT_READY，原因是既有 Agent smoke
  receipts 缺失，不能把 Doctor 报成整体通过。
- 使用既有运行预算：阶段 timeout 3600 秒、no-progress timeout 180 秒、单批候选最多 7 次尝试。
  未修改运行时代码、模型配置或判断结果来帮助通过。
- 工作区不是干净 checkout：与实验相关的已存在改动为 classification Reference 的一个等义措辞
  和两个静态合同测试；`src` 相对基线无改动。实验以启动时的文件 hash 为身份，
  不声称是完全等同于 commit 的独立构建。
- 结束时全部 Skill/Reference 与输入包 hash 均与启动 manifest 一致；`src` 相对基线仍无改动。

本地证据根目录：

`temp/span-skill-e2e-20260922-87710163/`

其中 `manifest.json` 保存输入和全部 Skill/Reference 的 SHA-256、模型及工具信息；
`skill-snapshot/` 保存启动时 Skill，位于产品 Agent 的 task root 之外。
`observed-ledgers/` 仅观察、复制候选与公开执行元数据，不回写 live task。

两个初始运行均从原始输入开始，不复用历史判断或历史 checkpoint。
正文因首次运行超时，使用本次运行已接受的 unit-boundary checkpoint 恢复；详细尝试保留如下。

输入构建命令分别使用 `--units 01-cover` 和 `--units 04-paper-body`，
输出到证据根目录的 `cover-package`、`body-package`：

```sh
uv run --frozen python evals/fixtures/template-extraction/minimal-units-0820/build_input_package.py \
  --units 01-cover --output <evidence-root>/cover-package --print-command
```

完整运行命令如下（正文使用对应的 `body-package` / `body-task`）：

```sh
PATH="$PWD/temp/id-closure-20260911/bin:$PATH" uv run --frozen docfit prepare-template \
  --school-template <evidence-root>/cover-package/input/school-template.docx \
  --school-requirements <evidence-root>/cover-package/input/school-requirements.pdf \
  --field-registry <evidence-root>/cover-package/input/field-registry.yaml \
  --output <evidence-root>/cover-task
```

builder 打印的命令带有 `--until unit-boundary`，本轮完整运行没有使用这个停止条件。
正文恢复命令在完整命令上增加 `--from unit-boundary`，输出仍指向本次 `body-task`。
复现时使用新的证据目录，避免覆盖本轮记录；上方 `<evidence-root>` 是须替换的路径占位符。

## 执行结果

| 用例 / 尝试 | 实际达到的阶段 | 结果 |
| --- | --- | --- |
| 封面首次运行 | 单元划分完成；2/2 批候选；进入反馈修订 | 失败，`semantic_batch_result_invalid` |
| 正文首次运行 | 单元划分完成；3/10 批候选 | 第 4 批请求无进展 180 秒，`template_agent_no_progress_timeout` |
| 正文一次误用普通重跑的尝试 | 未产生新的已接受边界 | 主动中止；边界 proof 字节未变，不作为成功尝试 |
| 正文显式 `--from unit-boundary` 恢复 | 10/10 批候选；真实反馈后 3 条范围得到修复 | 失败，`semantic_batch_candidate_failed`；精确文本修订改变了已锁定的语义责任 |

封面公开 trace 记录了 10 次 SDK query、7 次语义反馈尝试，末次 ResultMessage
没有 structured output，`is_error=true`、`terminal_reason=api_error`。
因此可以确认真实反馈和再次请求路径被执行，不能声称修订成功或通过 E2E。
公开元数据没有 API 错误正文，不能进一步推断其服务端原因。
候选观察器只保存了两份内容不同的封面账本：第 1 批首次保存，以及第 2 批首次加入；
最终账本与第二份快照逐字节相同。反馈期间未观察到既有候选的 field、span 或 role 变更。
所以“7 次反馈尝试”不等于“7 次成功保存修订”；快照也不能统计同内容重写或瞬时未捕获变化。

正文恢复运行耗时约 50.9 分钟，最终 SDK ResultMessage 本身成功返回 structured output，
随后被 Harness 拒绝；本次终止不是 API 错误或超时。
恢复 trace 的 `sdk_query_count=18` 含复用的边界阶段记录，
不能与首次运行计数简单相加；语义反馈计数为 9。
最后英文摘要批次的 7 次请求均返回了 structured output，未形成新的持久候选。
公开记录没有保留这些被拒绝输出的完整 parts，不能断言究竟修改了哪个 role / field。

### 封面：最终保存的候选仍有范围及语义错误

对真实 inventory 与保存的候选做只读原生回放，batch 身份、schema、role/field 词表检查通过，
但精确范围解析失败：7 个 source entry 合计漏掉 23 个 U+0020 空格，产生 14 项
`ordered_part_text_mismatch` / `ordered_part_text_gap`。此处是 **real replay 的失败证据**，
不是新的 Agent loop，也没有继续宣称 coverage、物化或发布通过。

候选层面还观察到以下学校语义问题：

- 格式说明整体被判为 `fixed_label`，理由混淆了“应遵守要求”与“应保留说明文字”。
- `学生姓名（三号黑体加粗）：` 整段保留为固定标签，格式批注未分离。
- `学□□号：`、`学□□院：` 中明确用于空格示意的 `□` 被保留为标签文字；
  `advisor.title` 的值范围是 `□教授`，还吞入了值前的排版占位符。
- 中英文题目和姓名字段候选存在，但本轮没有同模型、同配置的旧 Skill 对照实验，
  不能据此宣称准确率提升。

这些都是未接受候选的问题；没有最终 Word，不能描述为“最终 Word 已残留上述文本”。

### 正文：首轮观察与最终保存候选

进入整体校验反馈前的 10 批首轮全量候选已全部冻结并做原生只读回放，
共 71 条判断、142 个 parts；“首轮全量”不排除单个批次内已重试输出。
batch 绑定、空白传输解码、schema 与字段词表检查通过；第一个失败层是精确范围解析，
19 个 blockers 影响 9 条 entry：8 条累计缺少 30 个 U+0020 空格，
英文 Abstract 另重复尾部格式说明及其前导空格，共多 31 个字符。
此处是初始候选的 real replay，不是最终恢复结果。

正文随后出现了真实候选修订：中文摘要 entry 将 `摘□要` 拆为固定的“摘”“要”与
独立的排版占位符 `□`，并把原来空字符串的空白 part 改为 U+0020 × 13 的显式传输。
英文封面的题目和学生姓名两条 entry 也分别补回 1、2 个空格。
因此，正文已有“反馈后候选变化”的公开证据，但最终没有通过全量检查或发布。

第 5 批英文摘要的 reason/summary 声称绑定 `abstract.en`，实际 parts 没有该 field；
摘要正文示例被归入 cleanup，并重复覆盖尾部格式说明。必须以实际结构化输出判断，
不能以 Agent 的完成说明作为字段存在证据。

第 6 批农理工正文将 1/2/5、2.1、2.1.1 后的标题文字分别映射到
章、一级节、二级节（outline1/2/3），编号本身判为 style_only，
未把正文内的“（1）”误判为独立标题。但两条 source entry 各少 2 个原文空格；
另有理由根据字段词表推断自动编号存在，源段落实际未提供 `pStyle`/`numPr` 证据。
第 7 批文法经管正文则把 `（1）` 编号本身绑定为 `body.heading.outline4`，
又在同一 entry 把 `……[1]。` 绑定为 `body.paragraph`，出现一个 source entry
两个带字段的 `body_structure` 成员，混淆了编号与标题正文。
另将 `（导入语）` 视为固定保留文字，缺乏来源依据，存在提示文字残留风险。
此批 11 条的字面拼接全部一致，说明字符闭合与语义正确是不同维度。
最后保存候选与最新只读回放快照的 SHA-256 完全一致：
`a534bce5ad37f6bb5a729a1e9360d12841ea4c5403ec2b3d3e4fc65116877ec6`。
对照回放确认 3 条范围问题修复，blockers 从 19 降到 12，仍影响 6 条 entry：
5 条累计还缺 14 个 U+0020 空格，英文 Abstract 的 31 字符重复仍在。
`abstract.en` 绑定数量仍为 0；两个正文分支前述候选问题也仍在。
最终候选没有被接受，不能作为可填写模板交接。

## 责任层与结论边界

### Reference 内容存在，但真实批次没有可靠加载

本轮 snapshot 的主 Skill 第 22、76 行已经要求先读对应专题。公开工具元数据表明：
封面全部 post-unit query、正文首次运行的三个已完成批次没有调用 Read。
真实 `build_semantic_batch_prompt` 只明确提示 Skill 与 evidence，未内联 Reference；
每批又新建 SDK client，不能依赖其他批次读取过的内容。
这是已写明的路由未被遵循，以及 App 的必需上下文装载可靠性问题；
不能从元数据推断模型内部为什么没有读取。

恢复运行的公开 trace 补充了重要反例：英文摘要首轮候选前有 2 次 Reference 目录读取，
中文摘要修订过程中有 4 次；具体专题文件名未被权限日志保留。
因此不能说“正文完全没有读取 Reference”，也不能把所有错误归因于未读 Reference。
多数其他批次仍未调用 Read，装载可靠性问题与读取后仍有语义错误同时存在。

主 Skill 已明确保留所有空白、分离格式说明、reason 不得代替 parts；
因此，空格遗漏和输出自相矛盾也不能完全归因于未加载 Reference。
旧 startup prompt 的详细纯空白传输说明没有进入真正的 batch prompt，
但 structured output schema 仍有该说明，应表述为有效上下文不一致。

正文两处纯空白 part 在持久候选中已经是 `text=""` 且没有 `whitespace` 信息。
从 SDK `structured_output` 到 `record_semantic_batch_candidate`、ledger 序列化、
`_decode_whitespace_parts` 的 DocFit 路径没有将 text strip 为空串的步骤。
但公开记录不含 SDK 处理前的原始返回，不能区分模型最初输出与上游结构化输出通道的影响；
这里只定位“持久候选已缺字”，不将根因直接归给模型。

最小后续动作是先让必需阶段指引和已有正反例进入**真实 batch 上下文**，
验证实际 builder，并为错误语义提供明确的重审入口，再以同一输入运行 Agent loop。
无需增加逐对象手动 Read 门禁，
也不应将解析 reason、按学校措辞补字段、删除括号内容写入确定性代码。
详见 `loading-audit.json` 的代码行号与输入 hash。

### 分层归责

1. 标签、格式批注、值边界与摘要字段遗漏属于 Agent 语义判断问题，需核对主 Skill 规则是否遵循、
   对应 Reference 是否实际加载。不能将所有失败归为“缺少一条提示词”。
2. 原文空格闭合属于确定性的范围映射与反馈合同；需检查 reading packet、范围表达和恢复反馈。
   不应把计数、hash 或内部状态记账责任继续塞进 Skill。
3. API terminal error 和请求无进展 timeout 属于执行/服务可用性问题，不能靠学校语义规则修补。
4. 本轮没有修改 Harness，也没有人工补齐候选后宣称 Agent 通过。

当前范围修复还有一条明确边界：英文 Abstract entry 因原文重复触发机械反馈时，
已有 `style_only → fixed_label → cleanup → style_only` 的角色/字段责任会被锁定。
该轮可以修文本和空白，但将 cleanup 改成 fill_slot 或新增 `abstract.en` 会被
`semantic_batch_revision_responsibility_changed` 拒绝。
后续 readiness / publication 校验已声明语义的可执行性与产物来源，
没有从“英文摘要单元”推断缺少英文摘要字段的保证。
因此，即使未来范围闭合，也必须单独评估摘要接口的语义正确性。
最终 CLI 证实本轮以责任变更拒绝退出，但没有保存被拒绝输出的 parts，
不能进一步断言最后请求具体尝试补哪个字段。也不能用学校措辞的代码规则填补缺失字段。
详见 `body-diagnostic/repair-contract-audit.json`。

| 验证层级 | 本轮能声称的结论 |
| --- | --- |
| logic/contract | 上一轮 Skill 修改已有 49 项相关检查通过；本轮没有把它作为真实链路证据 |
| real replay | 封面最后候选、正文首轮与最终保存候选均完成原生只读回放，精确范围解析失败 |
| E2E agent loop | 已实际执行，正文有可见反馈修订；封面、正文均未通过 |
| product acceptance | 未进入；没有可交付的最终 Word 与 fill-contract |

## 证据索引

- `manifest.json`、`doctor.log`、`skill-snapshot/`：输入、依赖与 Skill 身份。
- `final-verification.json`：退出后的结果、最终文件存在性及 Skill/输入 hash 一致性。
- `run-history.json`：实际命令、各次尝试与恢复方式。
- `loading-audit.json`：主 Skill、Reference、真实 batch builder 和公开工具调用的独立审计。
- `cover-attempt-1/`：封面失败日志、公开 trace、最后候选和 tool audit。
- `cover-diagnostic/last-candidate-real-replay.json`：原生回放检查、精确范围反馈、输入未改动证明。
- `cover-diagnostic/candidate-history.json`：初始候选和反馈尝试后的可见变化轨迹。
- `body-attempt-1/`：首次正文请求无进展失败的完整证据。
- `body-interrupted-retry/`：普通重跑被中止的记录。
- `body-resume-from-boundary.log`、`body-task/`：显式恢复运行。
- `body-resume-final/`：恢复运行的最终冻结日志、trace、候选、inventory 与 checkpoint。
- `final-trace-audit.json`：恢复运行逐 query 的工具和 Reference 目录读取记录。
- `body-diagnostic/body-tracks-candidate-review.md`、同名 JSON：两种正文分支的候选语义与原文字面核对。
- `body-diagnostic/initial-all-batches-real-replay.json`：10 批初始候选的冻结 hash 与原生只读回放。
- `body-diagnostic/latest-observed-real-replay.json`、`final-candidate-hash-confirmation.json`：
  最新回放与最终保存候选身份一致性，以及 3 条修复、6 条仍失败的证据。
- `body-diagnostic/repair-contract-audit.json`：机械范围修复的角色/字段锁定，以及后续检查的语义边界。
- `observed-ledgers/events.jsonl`：候选与 trace 的变化时间、内容 hash、观察快照。
  `observed-ledgers/final-window/` 保留末段补充观察；两个观察进程均已停止。

证据目录是本机实验产物，不随本报告提交入库；复核时必须使用上述 manifest 对应的文件，
不要拿其他任务的最终产物补齐本轮结果。
