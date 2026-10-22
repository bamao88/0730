# 主 Skill span few-shot 修改与复测

本轮只修改主 Skill。两次同版本、同输入的真实复测中，学号与班级都只绑定值片段，最终 Word 的固定标签均保留。这个具体的整行绑定错误没有再次出现；但一次运行仍漏英文题名槽，并把导师职称前的间距纳入字段，因此整体语义稳定性尚未证明，产品验收仍不通过。

## 修改内容

在 [主 Skill](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/.claude/skills/docfit-school-extract/SKILL.md:39) 中，将原来的两行角色示例改为三组 few-shot，统一使用“输入原文 → 各 part 的角色与字段含义 → 假设填写后的效果”：

1. 编号行、年级与班别复合值：字段只替换值，固定标签保留。明确展示整行绑定会连标签与间距一起替换掉。
2. 标签内格式说明与紧邻的姓名、职称：说明独立表达；两个字段即使没有空格也按各自原文范围拆分。
3. 提示文字本身占据实际值位置：没有额外空白、下划线或示例值也可以是填写位置；同样的文字若处于栏标题则保留。

开头将完成标准明确为每个片段的语义责任正确，组合后的模板含义完整。提交前用正常字段值作概念上的替换检查，确认应保留的内容仍在、值各归其位、格式要求得到承接。这是具体语义复核，不增加工具调用或额外输出。

示例采用虚构场景和字段含义，没有放入当前学校标准答案或可直接照抄的字段 ID。假设填写结果明确不属于 parts，避免再把原文与改写结果同时返回。模型仍须按当前输入词表与上下文判断。

## 两次真实结果

输入、模型后端、已通过的功能区边界与前轮相同；从该边界进入真实 post-unit Agent loop 并继续实际 DOCX 物化。两次运行期间主 Skill、schema 与 Reference hash 一致。改动前基线为 `969a965`，本轮未修改 schema、Harness、反馈、执行器或 Reference。

| 检查项 | run-1 | run-2 |
| --- | --- | --- |
| 学号值范围 | `20××××××××××` | 相同 |
| 班级值范围 | `20××级×××（×）班` | 相同 |
| 学号、班级固定标签 | 均保留在填写槽外 | 均保留在填写槽外 |
| 中文题名 | 正确 | 正确 |
| 英文题名 | 漏槽，仍是固定文字 | 正确 |
| 导师姓名 | 首轮重叠，最终修正 | 正确 |
| 导师职称 | `□教授`，吞并间距 | `教授`，间距独立 |
| 姓名两处格式说明 | 最终均为 style_only | 首轮即为 style_only |
| 最终槽数 | 8 | 9 |
| post-unit 宿主反馈修订 | 2 次 | 1 次 |
| 渲染页数 | 2 | 2 |

两次都没有重现用户指出的学号/班级整行绑定错误，支持这组 few-shot 对该模式有帮助。单个学校样本与两次运行不能证明普遍或稳定提升；其他字段的回退也一并保留，没有只取成功运行。

## 最终产物限制

两份 DOCX 均已完成 XML、填写合同和渲染检查。固定标签实际保留；已判断为 style_only 的格式说明仍显示，长占位文案仍导致换行，封面为两页。该呈现问题属于已知执行层承接缺口，本轮没有把 style_only 全部改成 cleanup 来绕过它。

- **logic/contract**：29 项 Skill/Agent 边界测试通过，Skill 校验及 diff 检查通过。
- **E2E agent loop**：完成两次从同一已通过边界继续的真实语义判断及物化，没有重新执行 unit-boundary 阶段。
- **product acceptance**：不通过。局部字段范围改善不能代表完整模板已可验收。

## 证据

- [版本与输入 hash](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/manifest.json)
- [独立语义核查，含逐轮范围及最终 DOCX 文字](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/semantic-audit.json)
- [run-1 逐轮证据](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-1/events.jsonl) / [Word](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-1/task/output/final-template.docx) / [填写合同](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-1/task/output/fill-contract.yaml) / [渲染信息](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-1/render.json)
- [run-2 逐轮证据](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-2/events.jsonl) / [Word](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-2/task/output/final-template.docx) / [填写合同](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-2/task/output/fill-contract.yaml) / [渲染信息](/Volumes/ExtSSD2601/Docfit-worktrees/template-extraction/temp/span-fewshot-20260911/run-2/render.json)

本轮提交：`8a346edceeddddbb478bb7809eb3dd580bdac279`，只包含主 Skill 修改。
