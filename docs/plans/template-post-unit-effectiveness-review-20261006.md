# 模板提取 post-unit 效果改进建议（外部评审）

日期：2026-10-06
依据：`temp/template-story-boundary-e2e-20261006-njau-prompt/` 整份 NJAU 真实运行（17 批，3605 秒超时，7/17 接受）、
`prepare_template.py` 中的 post-unit prompt / options、`reading_packet.py`、Skill 与近期 bug/plan 文档。
原则：不再加层、不再加门禁；把“给 Agent 的输入、Agent 的输出协议、Harness 反馈、Tool 执行”每一步做简单、做对。
可以推翻现有实现，只要最终 `final-template.docx + fill-contract.yaml` 更好。

---

## 一、实跑数据说明了什么

| 观察 | 数据 | 含义 |
| --- | --- | --- |
| 输出很小 | 每批 Agent 结构化输出 4–10 KB（约 1–3k token），文本字段合计常 < 300 字 | 慢不是因为输出多 |
| 时间集中在少数批次的“思考” | 第 10 次查询 1208 秒、流事件 44,797 条；其余批次 148–13,728 条 | 模型在长时间推理。推理内容没有保存，token usage 也没记录，无法知道它在纠结什么 |
| 所有返工都是协议/转写错误 | 封面 13 条“空容器选了 body_structure 却缺 field_id”；目录 25 条把制表符写成字面 `\t`；第 7 批 15 条 role×field 组合不合法 | 没有一次退回是学校语义判断错。Harness 主要在考模型能否遵守传输协议 |
| prompt 结构失衡 | 每批 prompt 约 6 KB，其中语义任务一两句，其余是空白 codepoint/count 传输、leading/trailing 数组、render_sensitive_codepoints、whole_entry 规则 | 模型的注意力被转写规则占满 |
| 36% 条目是空对象 | 211 条中 76 条空文本段落、1 个空表格（不含 2 张图片） | 这些条目被强制逐条判断、写理由，是噪声，也是错误来源 |
| 每批 5 轮 | Skill → evidence(unit_evidence_packet) → (Read reference) → StructuredOutput | 宿主早已知道要给哪个包，却让 Agent 去取；每轮都重新处理全部上下文 |
| 串行 + 全批重交 | 17 批串行共用 3600 秒；任一错误要求整批重交；修订 prompt 达 73 KB（回显上次全部输出） | 一个长尾就拖垮整份模板 |

结论：**瓶颈不是模型智力，而是我们给它的任务形态**——要它在思考语义的同时充当逐字符转写器，
然后用机械错误反复退回。先把这部分拿掉，再谈语义质量。

---

## 二、已确认的优化项（2026-10-07 与产品负责人对齐）

按优先级：

### P0. 可观测：不再丢弃已采集的 usage 与 thinking

**先做这一项，且只做观测，不改调度。** 只有能看到 thinking，才能知道 1208 秒那类长尾到底卡在哪条规则、哪个条目。

现状核对（2026-10-07，对照代码与 NJAU 10-06 运行证据）：

- **usage 和 thinking 已经采集到，但被截断丢掉了。** `_sdk_receive_event` 已从 `ResultMessage` 提取 usage /
  model_usage，但 `sdk_events` 只保留最后 200 条（`del sdk_events[:-200]`）。NJAU 那次 13 次查询的
  `ResultMessage` 全部被截掉，证据里一条 usage 都没有。MiniMax 确实返回 thinking：仅剩的 200 条事件里
  就有 86 条 `thinking_delta`、2 个 `ThinkingBlock`，以及 `thinking_tokens` 系统消息。
  所以 P0 的主体是“落盘、不截断”，不是新增采集能力。
- **`effort="low"` 很可能没生效。** post-unit 配置为 `thinking={"type": "adaptive"}, effort="low"`，
  但单批仍思考 1208 秒。MiniMax 的 Anthropic 兼容端点是否接受 effort / adaptive thinking 尚未验证。

要做的：

- 每次 SDK 查询的完整事件流写入独立 jsonl（如 `work/.docfit/agent-transcripts/<stage>/<batch>/<attempt>.jsonl`），
  流式追加，不经过会被截断的内存列表：
  - 完整 thinking 文本、assistant 文本、tool_use 输入、tool_result 摘要（大包只记 hash 与字节数）；
  - 每轮开始/结束时间、轮次序号、批次 ID、修订序号。
  - 只是内部证据，不进 Agent 上下文，不进交付物。
- 每次查询的 `usage`（input / output / cache read / cache creation）和 thinking token 直接写进该查询的
  `timing_events` 记录，不依赖 `sdk_events`。
- 同时记录**实际发出的** thinking / effort 参数，与实际 thinking token 并列，用来判断 MiniMax 是否理会了 effort。
  若 MiniMax 支持 thinking token 上限（如 `budget_tokens`），这是比超时更直接的长尾控制手段——验证后再决定是否启用。
- 汇总表：每批一行（条目数、轮数、各类 token、墙钟、首轮是否通过、退回码），追加到 timing_summary。

**从 P0 移出、等 P0 数据后再定的两项：**

- **每批超时：不在 P0 设 300 秒。** NJAU 8 批首轮查询中有 5 批超过 300 秒（585 / 304 / 342 / 361 / 1208 秒）；
  按 300 秒 + 重试一次，大部分批次会被判超时，成本还翻倍。超时是止损，不是提速。
  如需先止损，只设一个拦截极端长尾的上限（约 900 秒），根据 thinking 证据再收紧。
- **批次并行：不是“各批本就独立”。** 一批的退回可以通过 `scope_expanded` 重开其他批次的条目，
  而 ledger 与 revision journal 当前按串行写入设计。并行前需要：journal/ledger 写入串行化；
  跨批重开推迟到所有批次首轮结束后统一处理；并发度受 MiniMax 速率限制。
  另外，看到 thinking 后单批耗时可能大幅下降，并行的收益要重新评估。

### P1. 宿主直接注入阅读视图，一轮出结果

- 批次 prompt 直接带该批阅读包与图片 content block，不再要求 Agent 先加载 Skill、再调 `unit_evidence_packet`；
  `docfit_evidence` 保留，供 Agent 主动查看相邻单元或更多页面。
- 阅读包去重：同一原文目前在 `reading_blocks.text`、`source_entries.text`、`unit_contexts` 出现三次；
  `text_length`、`leading_whitespace_count`、`source_order` 等机器字段留在 Harness 内部。
- Skill 核心规则放进固定 system prompt（可缓存）；references 按批次特征预附 1–2 篇，Agent 仍可 Read 其他。
- ~~核实 AGENTS.md 是否被加载进产品 Agent。~~ 已解决：产品 Agent 改用 `prepare_agent_home` 生成的独立 cwd（e4c30b4）。

### P2. 执行层只用一个原语 + 以差异验收

- 对每个源条目：在已接受 span 边界处拆 run → 每个 span 只做 `保留 / 删除文字 / 替换为字段控件`；不重建段落；
  drawing、shape、书签、域等非文字对象只在其自身条目被判 cleanup 时才动（图片清理 = 删该 drawing 所在 run，不是所在段落）。
- 物化后重读产物，与原始清单逐对象比较：未授权改变的对象规范化 XML 必须一致；授权的操作必须看到效果。
  回执从差异生成，而不是按 intent 类型自报 `preserved`。覆盖执行范围审计 F1–F4 及同类问题。

### P3. 反馈与止损

- **逐条接受。** 合格条目立即记入候选，只把出错条目发回（scoped revision 作为机械错误的默认路径），不整批重交；
  修订 prompt 只带出错条目及其上次判断，不回显整批输出。
- **反馈按条目说话，而不是按输出数组下标。** 现在的定位是 `semantic_judgments[3].parts[0].field_id`——
  模型要回到自己的输出里数“第 4 个判断的第 1 个 part”，条目多时容易数错、改错。改为直接给出条目 ID、该条原文、
  错在哪、可选的改法。例如：

  现在：
  ```json
  {"code":"ordered_semantic_part_field_missing","field":"semantic_judgments[3].parts[0].field_id",
   "message":"This part role requires a field_id selected from the pre-input field vocabulary."}
  ```
  改为：
  ```json
  {"source_entry_id":"source-entry-ec0b8d…","entry_text":"(空段落，承载校名图片)",
   "your_judgment":"body_structure，未给 field_id",
   "problem":"body_structure 必须绑定正文字段",
   "options":["若是正文代表结构，从词表选 body.* 字段","若只承担版式/留白，改为 style_only"]}
  ```
- **止损。** 同一条目两次修订仍不合法 → 标为 `unresolved`，继续后续批次，最后统一呈现。

## 三、暂缓或修正的建议

- **Harness 预切片 + 片号标注：暂缓。** 切分点由 Harness 猜，可能不准；切得过细时 Agent 要拼接很多片，标注反而更复杂。
  替代方向（待 P0 的 thinking 证据确认转写规则确实是负担后再做）：Agent 仍按可见文字写 parts，
  但 Harness 负责对齐——空白串按位置宽松匹配、字面 `\t` 等转义在原文对应位置是真实字符时直接认可、
  parts 拼起来等于整条原文时视为整条判断。这样可去掉大部分空白传输规则，又不需要预切分。
- **空对象默认保留、不再问：撤回。** 空段落、空表格可能承担特殊语义（填写留白、签名区、分节/分页载体、
  被删除后影响版式的锚点），不能由 Harness 默认决定。保留逐条判断，只降低成本：阅读视图紧凑显示，
  允许对连续同类条目一次给出相同判断，`reason` 可简写。
- **role 与 field 合并成一个选择：保留为候选。** 第 7 批 15 条退回全是 role×field 组合错误；
  可先在 output schema 中直接约束合法组合，再看是否需要合并。

## 四、P0 实测结果（2026-10-07，real replay）

P0 已实现：`src/docfit/app/agent_transcript.py` 为每次 SDK 查询写
`work/.docfit/agent-transcripts/<stage>/<batch>/<query>.jsonl`（完整 thinking、tool 输入、tool_result 摘要、
result usage、实际请求参数、块级耗时、中断时仍在流式输出的 thinking）；`timing_events` 每次查询带
`usage` / `model_usage` / `thinking_streamed_ms`，`timing_summary.by_stage` 汇总 token。

回放：复制 NJAU 10-06 任务根、清掉 post-unit 旧状态，`--from unit-boundary --resume-proof ... --until post-unit`。
任务根：`temp/post-unit-observability-replay-20261007-njau/`（未入库）。完成层级：**real replay**，未到 E2E / 产品验收。

| 指标 | 10-06 | 10-07 回放 |
| --- | --- | --- |
| 接受批次 | 7 / 17 | 12 / 17（第 13 批时阶段 3600 秒预算耗尽） |
| 修订查询 | 5 次，单批最多 15 条退回 | 2 次，各 1–2 条，均为 `ordered_semantic_part_field_missing` |
| 单次查询耗时 | 42–1208 秒 | 78–607 秒，中位约 230 秒 |
| post-unit token | 未留存 | 输入 333k（另缓存读 294k），输出 253k |

两次运行之间除记录器外还有其他改动（如 e4c30b4 Agent home 隔离），加上模型本身的随机性，
**通过率的提升不能归因于 P0**；P0 只提供了下面的诊断证据。

**1. 时间几乎全在思考。** 14 次完成的查询中，thinking 流式时间合计 3066 秒，占查询时间 86%；
输出 token 绝大部分是 thinking，结构化输出本身只有几 KB。一批常是一个连续几万到十几万字符的 thinking 块。
`effort="low"` 下仍如此，MiniMax 很可能没有执行 effort；thinking 上限是否可用仍待验证。

**2. 慢的原因分两类，按批次不同：**

- **转写协议（封面、表单类）。** 批次 1（封面 24 条，思考 301 秒）约一半篇幅在数空格、换算 `U+0020 × N`、
  判断 leading / trailing、要不要在空白处拆 part；整段出现 104 次 “Wait / Actually”。
  全空白条目同时给出 leading=36、trailing=36，模型多次怀疑数据矛盾。学校语义本身（标签 vs 填写位）很快就判断对了。
  → 证实第三节“Harness 负责空白对齐”方向，可提前做；阅读包对全空白条目不应同时给两个计数。
- **语义合同不清（说明文字、正文示例）。** 批次 6（英文摘要，464 秒）在 `TITLE（论文英文题目，三号…）`、
  `×××（300 个实词左右…）××××××` 上反复摇摆：填写位、清理还是保留样式，并担心清理说明会丢掉格式要求。
  批次 8（正文章节 22 条，568 秒、273 次推翻）在 `第X章 （正文标题）（三号黑体，居中）`、`1 材料与方法`
  这类正文示例上分不清 fill_slot / body_structure / fixed_label，以及 body_structure 是否意味着字段值。
  → 不是转写问题，是 role 合同与 Skill/Reference 对“占位符 + 格式括注”和“正文代表结构”的指引缺口；
  应先在合同层讲清 role 的产物含义（格式由保留样式承载、说明文字可清理），再补 Reference。

**3. 调度参数。** 若每批 300 秒超时，14 次查询中 4 次（337 / 304 / 500 / 607 秒）会被判超时，且都是首轮正常通过的批次。
在解决上面两类原因前不设 300 秒。17 批串行 × 中位约 230 秒 ≈ 3900 秒，仍略超 3600 秒预算。

**4. 产品 Agent 上下文附带了无关 Skill。** SDK init 显示可用 Skill 除 `docfit-school-extract` 外还有
`deep-research`、`dataviz`、`simplify`、`loop` 等 CLI 自带 Skill，它们的描述进入上下文；待确认能否在 Agent home 中关闭。

## 五、落地顺序（按 P0 证据调整）

1. ~~P0：完整事件流落盘、按查询记录 usage 与实际 thinking 参数，回放 NJAU 读长尾 thinking。~~ 已完成。
2. 转写负担：Harness 负责空白对齐、去掉空白传输规则；阅读包对全空白条目只给一个计数。
3. 语义合同：澄清 fill_slot / body_structure / fixed_label / cleanup 的产物含义，补“占位符 + 格式括注”和正文示例的 Reference。
4. P1：阅读视图注入与去重；关闭无关 Skill。
5. P3：逐条接受、按条目反馈、止损。
6. P2：执行原语 + 差异验收（可另一条线并行）。
7. 调度：验证 MiniMax thinking 上限；完成 2–3 后重测单批耗时，再定每批超时与是否并行。

每一步后在固定基准上（NJAU/PKU/HUNAU，从已接受的 unit-boundary checkpoint 回放 post-unit）记录：
各批首轮通过率、修订次数、错误码分布、token、墙钟、与 Gold 的一致率。
