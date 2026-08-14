---
name: convert-thesis
description: 当用户需要以学校目标模板为主干，把只读学生论文内容填入模板并验证可交付 DOCX 时使用。
---

# 论文转换与交付

以当前任务的干净目标模板为候选主干，把只读学生论文内容按绑定填入模板，检查页面和结构，并判断最终文档能否交付。

## 触发范围

在以下情况使用：

- 按学校格式证据重新排版论文 DOCX；
- 填写学校模板槽位或正文区域；
- 修复标题、目录、分页、页眉页脚或其他版式问题；
- 检查候选文档的视觉和结构结果；
- 生成经过验证的最终 DOCX。

## 输入与产物

必要输入包括：

- 只读的原始论文 DOCX，作为学生内容真值来源；
- 只读的干净、可填写目标模板，作为候选文档主干；
- 带来源引用的当前任务格式证据；
- 授权工作目录和输出目录。

产物包括最终 DOCX、候选渲染、视觉检查结果、确定性验证结果和未解决风险。格式证据不足时，停止受影响的修改并请求缺失证据，不自行补写学校规则。

## 不可违反的核心边界

1. 原始论文保持只读，修改只写入授权工作目录。
2. 第一个候选工作副本必须从目标模板产生；不得从学生论文副本构建候选后导入模板节。
3. 未经明确要求和证据支持，不改写、补造或删除论文内容。
4. 每项内容放置和版式修改都必须能够追溯到当前任务证据或必要的结构关系。
5. 所有 DOCX 修改只通过 `mcp__docfit__docx_edit` 完成。
6. 文档哈希或对象引用变化后，重新检查再继续修改。
7. 结构验证不能替代视觉检查；最终交付必须绑定当前候选文档的证据。

这些是转换行为和证据完成合同，不是文件系统权限声明。主 Agent 的 Bash/Write 已完全
开放且没有 DocFit 路径 gate；受信任主 Agent 仍应遵守上述规则，不能用 Bash/Write 绕过
`docx_edit` 的对象前置条件、提交状态、后置检查或最终源哈希校验。

## 根据证据选择下一步

| 当前情况 | 下一步 | 读取参考 |
| --- | --- | --- |
| 格式规则缺失、冲突或没有来源引用 | 暂停受影响操作并请求证据 | `.claude/skills/convert-thesis/references/task-evidence-and-conflicts.md` |
| 文档结构、哈希或对象引用不清楚 | 重新检查目标文档 | `.claude/skills/convert-thesis/references/tool-usage-and-error-recovery.md` |
| 需要判断分页、对齐或页面影响范围 | 查看当前视觉证据 | `.claude/skills/convert-thesis/references/evidence-and-visual-review.md` |
| 文档很大且存在互不重叠的只读分析范围 | 可选委派局部分析 | `.claude/skills/convert-thesis/references/delegation-task-packet.md` |
| 操作已有证据且引用有效 | 执行受控编辑 | `.claude/skills/convert-thesis/references/editing-validation-and-completion.md` |
| Tool 失败或结果不完整 | 按失败类型恢复 | `.claude/skills/convert-thesis/references/tool-usage-and-error-recovery.md` |
| 候选文档已经形成 | 完成视觉复核、验证和交付判断 | `.claude/skills/convert-thesis/references/editing-validation-and-completion.md` |
| 情形不在常规路径中 | 对照典型场景和反例 | `.claude/skills/convert-thesis/references/scenarios-and-edge-cases.md` |

## Tool 与 references 路由

| 目的 | Tool |
| --- | --- |
| 获取结构、哈希和对象引用 | `mcp__docfit__docx_inspect` |
| 执行原子修改 | `mcp__docfit__docx_edit` |
| 为当前 DOCX 建立 V2 LibreOffice 视觉快照和联系表 | `mcp__docfit__docx_render` |
| 查看已有渲染中的页面或局部图像 | `mcp__docfit__docx_visual_review` |
| 验证候选文档 | `mcp__docfit__docx_validate` |

Tool 的参数选择和错误恢复见 `.claude/skills/convert-thesis/references/tool-usage-and-error-recovery.md`。

## 完成检查清单

- [ ] 原始论文的哈希没有变化。
- [ ] 最终候选由目标模板工作副本构建，不是学生论文工作副本。
- [ ] 学生内容已按当前任务绑定进入模板槽位或区域。
- [ ] 每项修改都有证据和有效对象引用。
- [ ] 编辑结果为 `committed: true`，且后置条件成立。
- [ ] 修改期间的受影响页和相邻页已经检查。
- [ ] 最终候选文档的每一页都已经观察。
- [ ] 候选文档通过 `mcp__docfit__docx_validate`。
- [ ] 视觉证据、验证结果和最终 DOCX 对应同一哈希。
- [ ] 当前候选具有绑定最终哈希、固定 renderer/font identity 的 V2 LibreOffice render。
- [ ] 没有未解决的阻断性问题。

## 最终回复要求

先说明可交付、不可交付或缺少证据。随后列出最终文件、关键修改、验证摘要、已观察页面、候选渲染证据、警告和未执行事项。
