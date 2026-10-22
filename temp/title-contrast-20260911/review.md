# 题名漏槽：控制变量诊断与运行修复

2026-09-11。模块：模板提取；阶段：post-unit 学校模板语义判断。

## 结论与采用的修复

模型具备把这两个题名识别为填写槽、并正确拆分标签与值的能力。当前证据最强的可干预因素是：产品原来对 post-unit **硬编码关闭推理**。保持当前 Skill、输入和 low effort 不变，仅改为官方 adaptive 模式，5 次完成的单轮对照均保住了 9 个字段以及本次检查的题名、学号、班级范围；另有 1 次未返回结果，不能计为成功。

加入流式活动检测与原生机械反馈后，另做的 2 次真实 SDK 同会话修订均在第 2 轮通过原生 span/coverage 检查，9 个字段仍在，中英文题名和学号、班级的值范围正确。未向 Agent 提供预设字段数量或正确答案。

本次采用运行层修复：post-unit 开启 adaptive；接收内容增量，把真实生成视为活动，防止仍在生成时被 180 秒无进展看门狗中止。保留总时限、空闲时限、轮数及原生检查。日志只记录事件类型，不保存增量内容。当前 Skill 保持不变，实验性 Skill 改写不进入产品。

提交：`97c880d`（`Enable post-unit reasoning without timing out active generation`），仅包含本次运行配置、活动检测及相关测试。并行任务的 source-entry schema、prompt 与映射修改保留在工作区，没有混入该提交。

这证明了一个可执行的改进方向，不能证明关闭推理是唯一原因，也不能把少量同一封面样本推广为稳定成功率。完整 prepare-template 本次仍在 Agent 前被独立的来源映射问题阻断，尚未完成 E2E agent loop 或 product acceptance。

## 实验条件与结果

使用 MiniMax-M3、Claude Agent SDK 0.2.128、CLI 2.1.220。冻结源码、Skill、Reference、Registry 和同一个真实 cover reading packet。初始提示沿用真实记录（7174 字符，仅任务路径替换），每次使用新的 SDK client 与配置目录。模型仍通过原生 Skill/Read/MCP 接口获取材料；MCP 回放保存的完整 packet，不提供未捕获证据。这属于**真实输入 SDK 消融**，不是完整产品 E2E。

表中“关键范围正确”同时检查中文题名、英文题名、学号值、班级值，不能代替整个模板语义验收。“题名存在”只检查两个 field_id 均为 fill_slot，并不保证范围正确。

| 组 | 单独改变的条件 | 完成/启动 | 两个题名存在 | 关键范围正确 | 观察 |
| --- | --- | --- | --- | --- | --- |
| A | 原 Skill、原项目指引、关闭推理 | 3/3 | 2/3 | 2/3 | 一次两个题名都固定化，学号、班级整行绑定 |
| B | A 仅移除 CLAUDE.md / AGENTS.md | 3/3 | 1/3 | 1/3 | 去掉开发上下文仍有漏槽 |
| C | B 仅按最终填写用途重写角色定义 | 3/3 | 3/3 | 2/3 | 一次虽然字段存在，但范围仍错 |
| D | B 仅将自检扩大到所有 part 的最终用途 | 3/3 | 3/3 | 2/3 | 一次学号范围仍错 |
| E | B 仅缩短初始 brief | 1/1 | 0/1 | 0/1 | 两个题名仍漏 |
| F | B 合并 C、D 的 Skill 修改 | 2/2 | 2/2 | 0/2 | 出现虚构空白槽或说明与槽重复覆盖 |
| G | B 改 enabled/budget 8000 + high effort | 1/1 | 1/1 | 1/1 | 探索性组，同时改变两个因素，不作为单变量结论 |
| H | B 仅 disabled → adaptive，low 不变 | 3/3 | 3/3 | 3/3 | 9 个字段均存在；原文引号改写需机械反馈修复 |
| I | A 仅 disabled → adaptive，low 不变 | 2/3 | 2/2 完成项 | 2/2 完成项 | 放回开发上下文后两次仍正确；一次超过 18 分钟未完成，人工终止 |
| J | A 开 adaptive + 流式活动 + 原生同会话反馈 | 2/2 | 2/2 | 2/2 | 两次第 2 轮原生机械检查接受，字段未回退 |

H/I 中的姓名示例有两种拆法：整段“×××（或×□×）”作为姓名槽，或姓名“×××”与备选格式说明拆开。离线脚本的 `matches_single_span_reference` 只表示是否匹配一种示例拆法，不是语义通过标准。空白分隔也由原生 resolver 判断，不把所有逐字拼接差异都当成失败。

证据：逐次输出在 `sdk-*/events.jsonl` 与 `result.json`；离线观察在 [audit.json](audit.json)。中止样本保存在 [termination.json](sdk-i_project_adaptive-3/termination.json)，未删掉或计入成功。冻结文件摘要、变体及参数在 [manifest.json](manifest.json)；[frozen-inputs.tar.gz](frozen-inputs.tar.gz) 保存被清理前可复查的源码与指引快照。

## 能从记录定位到哪里

失败发生在 Agent 输出语义角色时：题名原文被归为 fixed_label，后续字段绑定就没有可绑定的 fill_slot。某些公开 `reason` 声称会在别处填写，但结构化输出没有相应槽。这是可观察的输出矛盾，不是我们读取了隐藏思维链。

移除项目指引仍复现，缩短 brief 也未解决，因此“开发上下文污染”不足以解释全部现象。SDK 的每次运行也没有恢复上一次 session。实际调用了哪些 Skill/Reference 以 Tool 调用记录为准；初始化列出的技能名称并不表示这些内容全部载入。

角色定义和自检确有改进空间，C/D 的题名识别有所改善；但合并规则仍产生错误范围，不能认定多加说明就是稳定修复。保持原 Skill 而改变推理模式，更直接改善了这次语义任务。

历史上 `8df0457`（2026-08-28）首次在受限 post-unit 事务加入 disabled/low；`adb18bc`（2026-09-03）将其扩大到全部 post-unit。相关记录未提供关闭推理的质量实验或兼容依据。

MiniMax 官方将 `adaptive` 列为 M3 在 Anthropic 接口启用推理的方式；SDK 支持该选项及 partial messages。因此采用明确支持的模式，不沿用探索组 G 的 budget 参数。[MiniMax Anthropic API](https://platform.minimax.io/docs/api-reference/text-anthropic-api)、[SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python)。

## 原生修订与超时证据

J 使用保存的真实 inventory，先核对来源 hash、16 条原文及完整字段词表，再调用产品原生 ordered parts / span / coverage 校验。不物化 DOCX，不写接受账本。旧的 7 字段错误结果也能通过这些机械检查，说明该校验没有暗中加入“必须 9 字段”的语义答案。

| 运行 | 第一轮 | 第二轮 | 流式活动 |
| --- | --- | --- | --- |
| J1 | 307.7 秒，说明段来源覆盖未闭合 | 累计 468.1 秒，原生检查接受，9 字段保留 | 两轮 2994 / 1418 个内容增量 |
| J2 | 280.0 秒，中文弯引号被改成直引号 | 累计 349.5 秒，原生检查接受，9 字段保留 | 两轮 7854 / 1252 个内容增量 |

旧看门狗只把完整工具调用或 Result 视为进展。开启推理后，持续生成可能超过 180 秒，所以仅改 thinking 会带来误中止；需要同步接收并识别有效内容增量。J 的 180 秒活动看门狗使用与产品相同的 `_sdk_has_generation_progress`，原始增量内容没有写入诊断日志。

## 验证层级与未解决事项

- **logic/contract**：本次 6 项配置、真实 receive loop 的模拟时钟测试通过；连续生成 720 秒不会误停，只有心跳/签名/空增量时仍在 180 秒中止；事件投影不保存内容。Ruff 通过。
- **边界回归**：提交态 `ad8b6a1` 的 guardrail 加当前 Skill contract，共 29 项通过。工作区另一任务正在把 schema 迁移为 source_entry_id only，一度出现测试先移除 scope、实现尚保留 scope 的 1 项不一致；本次未改该测试或 schema。隔离用的提交态测试副本为 `test_agent_boundary_guardrails_at_head.py`。
- **纯提交快照验证限制**：额外从 Git 导出 `97c880d` 的源码与本次 6 项测试，结果为 1 通过、5 项在创建 MCP server 时失败：`build_docfit_server() got an unexpected keyword argument 'include_docx_tools'`。回到父提交 `ad8b6a1`，原来的两项配置测试也同样失败，证明这是提交态已有的 server 调用与签名不一致；工作区已有另一项未提交 server 修改，前述 6 项通过依赖该工作区状态。因此不能把工作区通过说成本提交可独立完整运行。完整记录在 `committed-verification.json`、`parent-verification.json`，本次没有顺带提交他人的 server 修改。
- **真实输入 SDK 消融 / 原生校验回放**：上表各组；J 两次同会话修订接受。未执行 DOCX 物化。
- **E2E agent loop**：未完成。冻结源码的 A/B/C 三次 CLI 均在 Agent 前失败；最新工作区加修复后再次复测，仍报 `reading_blocks[0].object_text_spans is required for text reading blocks with covered_object_ids`，见 [product-current-absolute.log](product-current-absolute.log)。另一次相对 proof 路径调用失败已保留，但不计为模型实验。
- **产品验收**：未完成。已有格式说明残留、长占位文案换行等执行问题未被这些语义实验解决。

当前完整流程阻塞的具体来源：首段末尾 run 含 5 个空格，旧 unit coverage 排除纯空白 run，而新的 reading packet 保留完整段落文字；严格文本映射因此不闭合并返回空 spans。应在来源映射层让完整原文与 provenance 一致，不能裁剪原文、篡改旧 proof 或加学校文本特判。这属于正在进行的来源模型迁移，独立于本次 Skill/推理结论。

后续验收顺序：来源映射修复后，用相同封面运行完整 prepare-template，检查语义修订、DOCX、fill-contract 与可见版式，再扩展模板样本。当前先落地已有对照证据支持的运行配置修复。
