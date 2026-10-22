# 原文分段语义诊断与 Skill 实跑复核

结论：最终候选在两次真实运行中都改善了中文题名、导师职称以及姓名标签内格式说明的判断，但整体质量尚未证明稳定提升。第二次仍把学号、班级的固定标签一起纳入填写值，实际 Word 丢失了这两行标签。两份最终渲染均有说明残留、长占位文字及两页封面，产品验收不通过。

## 验证范围

- 模板提取模块，post-unit 语义判断 checkpoint。使用与上次相同的真实学校模板、要求文件和 Registry。
- 从同一份已通过的 unit-boundary proof 进入真实 MiniMax Agent loop，继续实际 DOCX 物化及发布；本轮没有重新跑功能区识别。
- 后端保持 minimax，当前配置为 MiniMax-M3。输入及各版本文件 hash 见 [manifest.json](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/manifest.json)。早期历史运行没有记录准确模型名，不能宣称与所有历史运行模型完全相同。
- `tap.py` 只在原函数调用前后记录显式工具输入、结构化结果和反馈，保留原返回值；没有注入答案、改变返回结果、保存模型隐藏思考或替代 SDK loop。日志位于各运行 task 的输入目录之外。
- [comparison.json](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/comparison.json) 保存五次运行的逐轮字段范围与最终 DOCX 文本；[compare_runs.py](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/compare_runs.py) 是仅用于此封面样本的离线核查脚本，不参与 runtime。
- 前一轮仅简化主 Skill 的完整流程曾返回 needs_input，本轮同版本的诊断复跑却产出文档。这种波动也保留在证据里，不以单次 built 代表修好。

## 归因修正

不能再将“不能漏字被理解成不能拆分”直接归咎于反馈。捕获的首轮输出在收到反馈前已经出错：

1. 校名 part 同时输出原文整段与去掉注释后的文本，将原文标注写成了前后改写对照。
2. 中英文题名被判固定标签，又虚构原文不存在的 `□` 作为填写槽。
3. 多个字段只把冒号当填写值；导师职称从首轮就绑到间隔 `□`。

首轮反馈指出冒号范围错误；下一轮指出重复、虚构、错序和漏字。连续且无分隔符的文本可以被现有 Harness 拆成相邻片段，前轮真实 inventory 的局部探针也确认了这一点。探针只属于本地诊断，不是完整 real replay。

修改前第三轮虽然修出了中英文题名槽，却把漏掉的“教授”补成 style_only，以满足字面覆盖而保留错误字段范围。这里是 Agent 语义修订错误，不是执行器把正确的指令执行错。

五次被记录的 post-unit 阶段均调用 Skill，但没有 Reference 的 Read 调用。不能假设改了 Reference 就一定会影响本次判断。因此最终候选把基础上下文示例放进主 Skill，Reference 只保留链接和更细的领域说明。

## 本轮修改

- 主 Skill：明确输出是在原文上分段标注；用同样的“项目名称”在标签位置与实际值位置的两个通用例子说明角色差异。没有写入本校答案、字段 ID 或 source entry 操作教程。
- 三个 Reference：移除“对象安全可编辑才允许语义拆分”和“先写 source_entry_id”的步骤；区分示例值、间隔、格式说明及正式名称括号。
- 输出 schema：给 parts/text/role/field_id 增加语义说明，明确连续原文片段、字段替换范围与上下文判断。没有新增字段、角色或机械门禁，也没有把学校词汇判定写进代码。
- 测试：保留词表、路由及边界检查，移除绑定旧 Reference 例句的文本快照断言；新增 schema 描述不得泄漏内部账本概念的检查。静态检查不证明语义判断正确。

这次触及 Skill 与 schema 是因为它们分别承担领域判断和输出字段含义。Harness 校验、反馈逻辑和 DOCX 执行器均未修改。SDK 的结构化输出配置以[官方文档](https://code.claude.com/docs/en/agent-sdk/structured-outputs)为依据；结构合法不代表学校语义正确，本次实跑直接显示了这一差别。

## 五次真实运行

以下均是各次最终输出；反馈次数只统计本次记录的 post-unit 阶段，不包含复用 proof 的历史事件。

| 运行 | 中文题名 | 导师职称范围 | 姓名标签内格式说明 | 学号/班级标签 | 修订次数 |
| --- | --- | --- | --- | --- | --- |
| before：修改前诊断 | 修订后有槽 | 错绑 `□` | 仍属固定文字 | 保留 | 2 |
| after：schema 与 Reference 初版 | 有槽 | `教授` | 独立 style_only | 保留 | 1 |
| after-final：审查两句措辞后，仍属中间版 | 又漏槽 | `□教授` | 又属固定文字 | 保留 | 2 |
| example：最终主 Skill 示例版 | 有槽 | `教授` | 独立 style_only | 保留 | 0 |
| example-repeat：最终版本不改内容复测 | 有槽 | `教授` | 独立 style_only | **两行标签均被替换掉** | 1 |

中间版的变化不能归因于两句措辞本身；样本与次数不足以分离随机波动。最终两个 run 的 Skill/schema hash 相同。三项原有重点语义问题在两次中都改善，但第二次出现的字段范围错误阻止我们宣称整体已修复，也不能据此推断跨学校或跨模型效果。

## 最终 DOCX 中仍有的问题

1. **Agent：学号与班级填写范围。** example-repeat 的 part 把整行原文绑定到字段，XML 与渲染均确认“学号”“年级专业及班级”标签消失。执行符合该错误判断。
2. **执行：style_only 文字残留。** 题名、姓名的说明虽已分开，仍写回 Word。`compiler.py::_intent_type_from_parts` 将含 fill_slot 的判断交给 slot handler；`slots.py::part_should_delete` 只删除 cleanup。固定标题另走 fixed-content 的括号说明清理路径。这解释了不同位置清理结果不一致。
3. **执行：占位文案与布局。** 班级使用 Registry label `【年级、专业及班级复合信息】`，包括姓名/导师长占位与残留说明在内的布局仍发生换行；两份最终结果都是两页。`□` 所表达的间距也仍以方框显示。

后续样式处理应修执行层对已接受说明义务的承接，不能为了让当前删除路径生效，要求 Agent 把所有 style_only 改成 cleanup。字段范围稳定性仍属语义判断问题；不能用按学校标签猜字段的代码替代。

## 证据入口

- [修改前逐轮原始证据](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/before/events.jsonl)
- [最终版本第一次逐轮原始证据](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/example/events.jsonl)
- [最终版本重复运行逐轮原始证据](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/example-repeat/events.jsonl)
- [最终版本第一次 Word](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/example/task/output/final-template.docx) / [Fill Contract](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/example/task/output/fill-contract.yaml)
- [最终版本重复运行 Word](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/example-repeat/task/output/final-template.docx) / [Fill Contract](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/semantic-split-diagnosis-20260911/example-repeat/task/output/fill-contract.yaml)

验证层级：logic/contract 123 项通过；相关 Ruff 与 Skill 校验通过。真实 post-unit E2E agent loop 已执行并核查产物，最终版本的两次产物已渲染并目视检查；product acceptance 不通过。没有用静态测试充当语义正确性的证明。

本轮提交：`969a96574d6ff2e877f8fa17c4501cc4e1567632`。仅包含主 Skill、三个 Reference、schema 说明和相关测试；原有无关修改及本地运行产物未纳入提交。
