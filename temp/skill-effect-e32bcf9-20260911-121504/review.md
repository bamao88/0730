# 主 Skill e32bcf9 同输入真实重跑

结论：本次没有观察到整体提升。导师姓名与职称的字段范围改善，但中文题目仍缺槽，英文题目由填写槽退化为固定文字；任务返回 needs_input，未生成新的 Word 或填写合同。不能据此宣布新 Skill 已修复封面问题。

## 可比性

- 旧任务：`../id-closure-20260911/cover-e2e/`。
- 新任务：`cover-e2e/`；全新目录、会话，完整运行 prepare-template，没有注入旧判断、修正答案或 Gold。
- 模板、要求 PDF、Registry 三份输入逐字节哈希一致，详见 `run-manifest.json`。
- 相对旧任务 `runtime-baseline.json` 保存的源码、Skill/Reference、依赖文件哈希，唯一变化是主 SKILL.md；本次运行期间这些文件未变化。运行来自工作目录，不等于仅 checkout HEAD 即可复现。
- 当前 HEAD：e32bcf9；MiniMax-M3，SDK 0.2.128，OfficeCLI 1.0.143，LibreOffice 25.2.3.2。旧执行记录仅保存 minimax 后端，未保存实际模型名，无法严格证明模型版本相同。
- 一次新运行与一次历史运行的比较；这是观察到的变化，不是稳定改善或因果收益的统计证明。

## 实际判断对比

| 项目 | 旧输出 | 新输出 | 结论 |
| --- | --- | --- | --- |
| 中文题目 | fixed_label，无中文填写槽 | parts 完全相同；另报填写区缺少原文 | 未改善 |
| 英文题目 | thesis.title.en 填写槽，吞入格式说明 | 整段 fixed_label，无英文填写槽 | 退步 |
| 导师姓名与职称 | ×××□教授 全部绑定 advisor.name.zh | ××× 绑定 advisor.name.zh；教授绑定 advisor.title；□ 单独 style_only | 两个字段及其文本范围改善；间隔呈现未验证 |
| 姓名格式说明 | 标签含三号黑体说明；行末单独 style_only | parts 完全相同 | 未改善 |
| 学校名、论文类型、地点格式说明 | 随固定文字整体 fixed_label | parts 完全相同 | 未改善 |
| 学院全称说明 | cleanup | style_only | 发生变化，无法证明效果更好 |
| 班级 | 复合字段正确；长占位文案换行 | 字段及范围相同，没有进入物化 | 本轮无法验证呈现 |

16 条判断中，13 条的 parts 完全相同。part 数量 24 → 26，字段 part 数量仍为 7；数量不反映质量，新结果是新增 advisor.title 同时丢失 thesis.title.en。新输出明确报告题名未绑定，报告一致性比旧总结虚称中文题名已绑定有所改善，但填写能力没有因此改善。

## 失败归因

所属模块：模板提取；checkpoint：post-unit 语义判断；CLI exit 2，Agent 最终 needs_input，未进入物化和发布。

Agent 把题名提示文字视为固定标签，推断真实值必须位于相邻空白，又以空白没有可关联原文为由阻断。它还声称学校名与括号说明相连，因此覆盖规则禁止拆分。这些是 Agent 的解释，不能视为真实接口限制或学校材料确实不足。

离线诊断使用本轮真实 object-inventory，人工将学校名、中文题名、英文题名分别拆为内容与格式说明，调用当前原文片段解析器；三组均完整还原原文、解析出两个范围且没有反馈错误。详见 `split-support-probe.json`。这证明局部相连文本映射支持拆分；不证明整体语义验收、样式交接、DOCX 物化或最终呈现通过。

从最终输出可以确认 Agent 把“原文不能遗漏”误解成了“相连文本不能拆分”。当前只保存最终完成输出与事件摘要，无法据此确定是哪条早期反馈、Reference 或 prompt 引发误解；不应武断归因于某一句主 Skill 文案。下一步应针对文本提示与真实填写位置的判断、原文完整性反馈的理解检查交互合同，而不是增加某所学校的字符串规则。

## 验证层级

- **E2E agent loop：实际运行，失败。** 单元边界通过；post-unit 经 2 次语义反馈后返回 needs_input。新 run 总墙钟 315712 ms，旧 run 148891 ms；总 SDK query 数 5 对 3。
- **局部诊断：真实 inventory + 人工构造 parts 的定位检查通过。** 不是 Agent 成功输出，也不是完整 real replay。
- **real replay：未单独完成完整回放。**
- **product acceptance：未通过。** 新任务没有 final-template.docx / fill-contract.yaml，无法复验说明残留、职称显示及长占位换行。

本轮没有修改 Skill、Reference、源码或执行策略，也没有将人工诊断结果注入 Agent 重试。

## 证据

- [运行命令](command.txt)
- [环境与输入记录](run-manifest.json)
- [CLI 输出](cover-e2e.log)
- [实际 Agent 完成输出](cover-e2e/work/.docfit/template-agent-execution.json)
- [逐项对比](comparison.json)
- [局部拆分支持诊断](split-support-probe.json)
