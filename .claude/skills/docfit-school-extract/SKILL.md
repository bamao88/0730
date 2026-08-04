---
name: docfit-school-extract
description: 当用户需要解释当前任务的学校论文模板、书面格式要求或官方示例，并把规则、槽位、冲突和未知项整理成可追溯证据时使用。
---

# 学校材料证据提取

读取当前任务提供的学校材料，识别其中能够直接支持格式判断的事实，并输出带来源定位的任务证据。

## 触发范围

在以下情况使用：

- 解释学校论文模板或书面格式要求；
- 识别模板中的固定文字、条件文字、待填槽位和操作说明；
- 比较模板、书面要求和官方示例之间的差异；
- 整理格式规则、适用条件、冲突和未知项。

## 输入与产物

输入仅限当前任务提供的学校模板、书面要求、官方示例、适用性说明和用户确认。

产物是 `scope: current_task_only` 的证据集合，包括：

- 实际使用的来源及其哈希、对象引用或页码定位；
- 可直接观察的事实和有证据支持的格式规则；
- 模板文字分类、适用条件和候选 Tool 参数；
- 未解决冲突、未知项和最小证据请求。

字段说明见 `.claude/skills/docfit-school-extract/references/output-schema.md`。

## 不可违反的核心边界

1. 只分析当前任务提供的学校材料，不引入其他任务或历史学校结论。
2. 每项规则都必须引用具体来源；证据不足时保留未知，不凭经验补全。
3. 所有输入材料保持只读；此 Skill 不修改任何文档。
4. Knowledge 只提供通用识别方法，不能提供或覆盖学校的具体要求。
5. 来源冲突必须保留，除非当前材料或用户确认给出了明确的裁决依据。

输入只读是本 Skill 的行为合同，不是主 Agent 的文件系统 sandbox。Bash/Write 虽然对主
Agent 完全开放，本 Skill 仍不得用它们修改输入文档。

## 根据证据选择下一步

| 当前情况 | 下一步 | 读取参考 |
| --- | --- | --- |
| 来源身份、版本或适用范围不清楚 | 先建立来源清单 | `.claude/skills/docfit-school-extract/references/evidence-and-conflicts.md` |
| 需要判断一段模板文字的作用 | 执行模板文字分类 | `.claude/skills/docfit-school-extract/references/template-text-classification.md` |
| 两个来源给出不同要求 | 保留两条证据并判断能否裁决 | `.claude/skills/docfit-school-extract/references/evidence-and-conflicts.md` |
| 结构结果不能说明页面位置或视觉分组 | 建立基线渲染并查看相关页面 | `.claude/skills/docfit-school-extract/references/tool-usage-and-error-recovery.md` |
| 材料很大且存在互不重叠的分析范围 | 可选委派只读分析 | `.claude/skills/docfit-school-extract/references/delegation-task-packet.md` |
| 证据已经足够 | 按输出合同整理结果 | `.claude/skills/docfit-school-extract/references/output-schema.md` |
| 情形不在常规路径中 | 对照典型场景和反例 | `.claude/skills/docfit-school-extract/references/scenarios-and-edge-cases.md` |

## Tool 与 references 路由

| 目的 | Tool |
| --- | --- |
| 读取结构、样式、对象和来源哈希 | `mcp__docfit__docx_inspect` |
| 为视觉判断建立学校材料的基线渲染 | `mcp__docfit__docx_render`，使用 `baseline` intent |
| 查看已有渲染中的页面或局部图像 | `mcp__docfit__docx_visual_review` |

Tool 的选择和失败恢复见 `.claude/skills/docfit-school-extract/references/tool-usage-and-error-recovery.md`。

## 完成检查清单

- [ ] 所有使用过的来源都有哈希和具体定位。
- [ ] 可观察事实、解释后的规则和用户确认彼此分开。
- [ ] 每项规则都写明适用对象和适用条件。
- [ ] 必要的模板文字已经分类。
- [ ] 冲突和未知项没有被静默消解。
- [ ] Knowledge 没有被当作学校事实。
- [ ] 任何输入文档都没有被修改。
- [ ] 输出符合 `scope: current_task_only`。

## 最终回复要求

说明证据是否完整，并列出已确认规则、模板文字分类、冲突、未知项和来源定位。若证据不足，只提出能够改变结论的最小补充请求。
