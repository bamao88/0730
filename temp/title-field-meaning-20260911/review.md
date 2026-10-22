# 英文题名字段定义修正：真实 post-unit 复测

本次修正已落实，但题名漏槽尚未解决，不能进入产品验收。两轮都成功产出 DOCX 与填写合同，一轮有完整中英文题名槽，另一轮同时遗漏两种题名。两次样本不足以证明成功率提升。

## 修改范围

- Registry 将 `thesis.title.en` 的含义从“英文摘要页顶部使用的完整英文题名。”改为“论文的完整英文题名。”，revision 更新为 `2026-09-11.1`。这是位置描述澄清；保留现有字段 ID、类型、语言、数量、角色及 `registry_version: 0.5.0`。
- 主 Skill 明确：先判定文本责任；词表缺字段时保留填写责任并返回 `needs_input`，不能反向改判为固定文字。
- Registry Reference 同步说明：视觉位置用于理解语义，不能仅凭页面名称决定字段匹配；缺字段不证明文本应保留或删除。
- 没有修改 schema、Harness、反馈或物化代码。历史 Registry 和旧任务输入副本保留；新任务使用新快照。

## 验证层级与结果

`logic/contract`：53 项通过；Skill quick_validate 及三文件 diff 检查通过。测试在后续无关工作区源码修改之前完成。

`E2E agent loop`：同一真实封面及学校要求，使用两处新 task root，从已验证的 unit-boundary proof 恢复并运行真实 post-unit Agent 判断、反馈和物化。没有重跑前置切单元阶段，因此不是整个 prepare 全流程重测。两轮实际输入 packet 均带有新的字段含义及 Registry SHA，不是旧缓存。

| 项目 | run-1 | run-2 |
| --- | --- | --- |
| 最终填写槽 | 9 | 7 |
| 中文题名 | 已绑定 | 缺失 |
| 英文题名 | 已绑定 | 缺失 |
| 学号、班级标签 | 保留，仅值绑定 | 保留，仅值绑定 |
| 导师姓名、职称 | 分别绑定 | 分别绑定 |
| post-unit Result | 2 | 1 |
| StructuredOutput 尝试 / SDK schema 错误 | 2 / 0 | 3 / 2 |
| 最终渲染页数 | 2 | 2 |

run-1 经一次宿主 span 反馈完成修订；题名在修订前后都有槽。run-2 的两次错误均是根对象含额外字段，由 SDK 在同一 query 内重试，不能算成三轮宿主语义修订。三次尝试都已将题名判为固定文字；唯一成功 Result 被宿主直接接受。

`product acceptance`：未通过。run-2 的合同与 DOCX 都没有题名槽，页面仍显示通用的中英文题名提示。两轮的姓名行格式说明仍残留，长占位文字换行，封面均跨两页。字段判断与呈现执行问题继续分别归因。

## 公开输出能够支持的归因

失败轮不再引用“英文摘要页限制”。它的公开理由却声称：

- 中文：“题名的实际填写位置在本段之外由 thesis.title.zh 字段承载。”
- 英文：“实际英文题名由 thesis.title.en 字段在填写期注入。”

这与其结构化输出及最终合同矛盾：两者均没有对应的 `fill_slot`。可观察的错误在于将已经承担填写责任的文字判为固定文字，并以未实际声明的后续填写位置为理由。这里是公开 `reason` 与产物的核对，不是读取或重建内部思维链；公开解释本身也不足以证明因果。

本次实验说明，旧字段定义确有歧义，但移除歧义不足以修复漏槽。后续应围绕“独立标签与占据填写位置的提示文字如何区分、声称另有承载位置是否有实际输出依据”做对照验证；不应继续把问题全部归咎于 Registry，也不应通过标题关键词规则替 Agent 补槽。

## 可复核证据

- [输入与验证清单](manifest.json)、[新词表](new-vocabulary.json)、[语义和最终合同审计](semantic-audit.json)。
- [run-1 公开事件](run-1/events.jsonl)、[run-2 公开事件](run-2/events.jsonl)。记录公开结构化判断和反馈，未采集隐藏 ThinkingBlock。
- [run-1 最终 DOCX](run-1/task/output/final-template.docx)、[run-2 最终 DOCX](run-2/task/output/final-template.docx)。
- [run-1 渲染记录](run-1/render.json)、[run-2 独立渲染记录](run-2/visual-audit/receipt.json)、[run-2 第 1 页](run-2/visual-audit/page-1.png)、[run-2 第 2 页](run-2/visual-audit/page-2.png)。

工作区同时有其它改动：Agent 运行结束后，常规 render CLI 因 `source_entries.py` 与调用方导入不一致而失败；本次直接调用现有 LibreOffice 渲染适配器完成第二份产物检查，没有改动该无关源码。最终检查时 `prepare_template.py` 也已与运行前记录不同，主 Skill、全部 References 和 Registry 仍匹配快照；不把当前整个 checkout 宣称为已测版本。

本次三文件修改提交：`f9881005007b890ebe8cb970da5c878a5bfd0fc0`。临时测试证据保存在上述目录，没有把其它任务的改动或产物纳入提交。
