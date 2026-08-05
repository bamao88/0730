---
name: docfit-school-extract
description: 当用户需要清理、冻结或解释学校论文模板，识别固定内容、可填槽位、说明文字、冲突和人工区域，或为后续转换准备当前任务的冻结模板产物时使用；不要用于填入待转换论文内容或生成最终论文。
---

# 生成冻结学校模板产物

把当前任务的学校模板、书面要求和可选官方示例整理成可安全填写的冻结模板产物。
保留不确定性比猜测性清理更重要，因为下游会把这份产物当作固定主干。

## 输入与产物

输入是当前任务授权的学校模板 DOCX、正式要求，以及可选的官方示例、适用性说明和
用户确认。来源文件保持只读；所有修改只发生在新的工作副本和输出文件。

完整产物包括：

- 可独立打开的冻结干净模板 DOCX；
- 绑定该模板精确 hash 的槽位索引；
- 固定内容边界、来源证据、冲突和未决项；
- manual 区域与无法安全表达的 gap；
- 绑定冻结模板 hash 的全页视觉检查与确定性验证摘要。

槽位的语义合同见
`.claude/skills/docfit-school-extract/references/artifact-interface.md`。

## 边界

- 只使用当前任务来源，不从历史任务、文件名或常见学校格式补事实。
- 不接收或填入待转换论文内容，不生成最终论文。
- 不创建学校 profile、学校目录、跨任务模板包或 Knowledge 写入请求。
- 不用 Knowledge、经验或国家标准数值表补造材料中没有依据的学校样式。
- 不覆盖来源文件，不直接修改 OOXML，不把工作副本冒充冻结产物。
- 冲突、manual 区域、gap 和能力缺口必须留在产物中，不能用“已完成”掩盖。

## 两个判断

### 目标足够唯一才行动

编辑、清理或建立槽位前，要求至少两个相互独立的信号共同指向当前快照中的唯一目标。
结构引用、前置指纹、相邻语义和来源说明可以相互印证；页码、bbox、颜色或单个近似
文字命中只能缩小候选范围。零命中、多命中或快照失效时重新取证或保留 gap。

### 内容消失需要更强证据

删除说明文字、示例值或其他可见内容，需要比保留它更强的证据。只有当前材料能够
支持其功能、适用范围和唯一目标时才清理；否则保留原状并标记 unknown、manual 或 gap。

详细分类方法见
`.claude/skills/docfit-school-extract/references/template-cleaning-and-slots.md`。

## 根据证据选择参考

| 当前判断 | 行动 | 读取参考 |
|---|---|---|
| 来源身份、版本、适用范围或优先关系不清 | 建立来源清单并保留冲突 | `.claude/skills/docfit-school-extract/references/evidence-and-conflicts.md` |
| 需要分类固定文字、条件文字、槽位或说明文字 | 判断功能与删除证据 | `.claude/skills/docfit-school-extract/references/template-cleaning-and-slots.md` |
| 需要建立槽位、固定区域、manual 或 gap | 按产物 Interface 组织 | `.claude/skills/docfit-school-extract/references/artifact-interface.md` |
| 需要选择 Tool、重新取证或处理失败 | 根据当前快照和错误语义恢复 | `.claude/skills/docfit-school-extract/references/tool-usage-and-error-recovery.md` |
| 材料量大且局部范围可独立分析 | 可选委派只读分析 | `.claude/skills/docfit-school-extract/references/delegation-task-packet.md` |
| 遇到重复占位符、签名区、文本框或其他长尾 | 对照风险场景 | `.claude/skills/docfit-school-extract/references/scenarios-and-edge-cases.md` |

## Tool 路由

| 目的 | Tool |
|---|---|
| 读取来源与工作副本的结构、样式、对象和 hash | `mcp__docfit__docx_inspect` |
| 在新工作副本上原子清理或建立安全锚点 | `mcp__docfit__docx_edit` |
| 建立基线、按需取得编辑反馈或冻结候选页面证据 | `mcp__docfit__docx_render` |
| 查看已有 render 的整页、裁剪或对比图片 | `mcp__docfit__docx_visual_review` |
| 从来源和冻结候选重新核对 package、固定内容和产物合同 | `mcp__docfit__docx_validate` |

这些是能力路由，不是固定调用序列。具体 intent、前置条件、失败恢复和能力缺口见
`.claude/skills/docfit-school-extract/references/tool-usage-and-error-recovery.md`。

## 冻结与完成

最后一次写入后重新 inspect 工作副本，只在最终 hash 上建立槽位和固定区域 locator。
随后查看该 hash 的全部页面，并要求程序核对模板可打开、索引绑定、唯一定位、固定内容
和 gap。任何后续写入都会使索引、视觉证据和验证结论失效。

只有应用壳或 Tool 已实际验证这些硬条件时，状态才是 `complete`。证据不足时返回
`needs_input`；现有 Tool 不能验证 hash、唯一性、固定内容或发布原子性时返回 `blocked`
并列出 capability gap。不要用 Agent 自报结果代替程序完成门。

## 最终回复

说明状态、冻结模板与 manifest 的位置和 hash、槽位/manual/gap 数量、使用过的来源、
视觉与确定性验证摘要，以及仍需确认或当前能力无法证明的事项。不要复制材料正文或
把任务产物描述成可跨任务复用的学校资产。
