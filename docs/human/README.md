# DocFit human 文档

状态: 背景索引
更新日期: 2026-08-18

`docs/human/**` 包含面向人的指南、评审包、学习笔记和设计讨论。它不是默认 Agent 启动上下文。

只有当前任务需要某份背景材料时，才读取这里的具体文件。项目真相优先来自根目录
`README.md`、`STATUS.md`、`ARCHITECTURE.md`、`AGENTS.md`、当前 Contract、模块边界和 Eval 入口。

## 治理与用户指南

| 文件 | 用途 |
| --- | --- |
| [docfit-module-documentation-guidance.md](docfit-module-documentation-guidance.md) | 详细文档治理参考；只在文档清理或评审时读取 |
| [non-technical-development-guide.md](non-technical-development-guide.md) | 面向人的开发指南 |
| [docfit-local-observer-user-guide.md](docfit-local-observer-user-guide.md) | 本地 observer 用户指南 |
| [thesis-content-tree-reading-guide.md](thesis-content-tree-reading-guide.md) | 论文 content tree 阅读指南 |
| [template-extraction-testing-entrypoints-note.md](template-extraction-testing-entrypoints-note.md) | 模板提取测试总入口、阶段 replay 与 final Eval 入口区分 |
| [ai-collaboration-completion-levels-and-evidence.md](ai-collaboration-completion-levels-and-evidence.md) | AI 协作中的完成层级、证据边界和验收沟通方法 |
| [ai-collaboration-complexity-judgment.md](ai-collaboration-complexity-judgment.md) | AI 协作中判断目录约定、index、schema、validator、wrapper 是否必要的参考 |
| [ai-coding-documentation-system.md](ai-coding-documentation-system.md) | AI Coding 文档体系构建调研、推荐分层和参考文献 |
| [agent-testing-task-input-guide.md](agent-testing-task-input-guide.md) | 给 Agent 输入测试任务时定义验证合同、测试矩阵和完成层级的学习笔记 |

## 产品评审与背景

| 文件 | 用途 |
| --- | --- |
| [docfit-general-style-preset-v1-product-review.md](docfit-general-style-preset-v1-product-review.md) | general style preset 产品评审背景 |
| [thesis-conversion-example-optimization-log.md](thesis-conversion-example-optimization-log.md) | conversion example 优化记录 |
| [content-id-and-template-workflow-examples.md](content-id-and-template-workflow-examples.md) | content identity 与模板 workflow 示例 |
| [学校论文模板整理中的六类通用问题.md](学校论文模板整理中的六类通用问题.md) | 学校模板整理常见问题分类 |

## Agent 与系统讨论

这些文件是讨论或学习记录。除非内容被提升到 `AGENTS.md`、Contract、`ARCHITECTURE.md` 或 ADR，
否则它们不是当前操作规则。

| 文件 | 用途 |
| --- | --- |
| [AGENTS.zh-CN.md](AGENTS.zh-CN.md) | Agent 指引的中文草稿/背景 |
| [agent-skill与代码tool的职责边界经验.md](agent-skill与代码tool的职责边界经验.md) | Skill 与 Tool 责任边界经验 |
| [post-unit-skill-writing-boundary.md](post-unit-skill-writing-boundary.md) | post-unit Skill 写作边界与三层语义判断收敛记录 |
| [agent-semantic-boundary-engineering-guardrails.md](agent-semantic-boundary-engineering-guardrails.md) | Agent 只输出语义判断、视觉证据边界与工程护栏讨论 |
| [docfit-agent-sdk模块配置与共享事实层学习笔记.md](docfit-agent-sdk模块配置与共享事实层学习笔记.md) | SDK 模块配置与共享事实学习笔记 |
| [agent-visual-rendering-and-structural-location.md](agent-visual-rendering-and-structural-location.md) | 视觉渲染与结构定位设计讨论 |
| [template-extraction-stage-acceptance-and-resume-handoff.md](template-extraction-stage-acceptance-and-resume-handoff.md) | 模板提取分阶段验收、unit proof、replay 和 resume 交接材料 |
| [kimi-claude-agent-sdk-controlled-test.md](kimi-claude-agent-sdk-controlled-test.md) | SDK backend controlled test 记录 |
| [eval-data-system-and-pipeline-discussion.md](eval-data-system-and-pipeline-discussion.md) | Eval 数据与 pipeline 长讨论；只在处理该主题时读取 |
