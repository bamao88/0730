# DocFit 状态

状态: 当前项目状态入口
更新日期: 2026-09-28

本文用于回答“项目现在在哪”。它概括当前可用能力，并只在必要时指向详细证据。

## 工作区整合（2026-10-22）

模板提取、用户内容提取与最终 Word 生成线已汇入当前项目，独立模块 CLI 与本地用例入口可共同使用。
本次验证、保留范围及环境限制见 [worktree 合并记录](docs/status/active/worktree-integration-20261022.md)。
代码整合不改变下述模块产品验收状态，也不替代新的真实 Agent E2E 或最终 Word 验收。

## 当前交付缺口

模板提取的“原 source ID/span 判断能够忠实执行并交付可用模板”尚未完成。身份接入与
原范围保护已有证据；控件内局部文字修改、超链接内文字修改现已在构造 DOCX 的正式物化入口
正向写出并重读，执行前检查在这组覆盖场景与实际结果一致。真实学校任务中尚未找到同类
已接受判断，因此该新增能力的真实回放、Agent 闭环及产品验收尚未完成。

2026-09-27 的结构对照及 2026-09-28 的修复验证属于 `logic/contract`；已有特定真实输入回放
只证明既有路径未退步，不证明本次新增承载结构能力的完整 `real replay`、`E2E agent loop` 或
`product acceptance` 已通过。
已确认原因与推进顺序见 [当前任务计划](docs/plans/template-harness-repair-20260923.md#2026-09-27当前归因修复边界与推进顺序)，
范围与历史证据见 [执行范围审计](docs/bugs/template-execution-scope-audit-20260924.md)。

## 现在可用

- **全流程对象身份专项工程验收 ACCEPTED**：运行时代码已把源对象清单提前到首次 Agent 判断前，
  功能区边界、内部判断、实际执行、发布和恢复使用同一初始身份；旧协议明确拒绝。
  三校 1,335 个源对象的分页稳定性和 3,318 个原 Word 片段映射已验证；新的真实 Agent
  写入、保留与恢复链已有证据；7 项失败/历史缺证据记录复核未发现新增身份缺陷。
  已补同一对象跨分区后的两侧实际写入与重试核验；切点由测试构造，不冒充新 Agent E2E。
  [当前专项证据](docs/status/active/template-full-flow-object-identity-20260922.md)与
  [唯一计划](docs/plans/template-field-id-vocabulary-boundary-refactor.md)记录收口依据。
  该记录证明身份接入及已列明写入场景，不代表所有操作已忠实执行语义范围；后续范围缺陷及修复以
  [执行范围审计](docs/bugs/template-execution-scope-audit-20260924.md)为准。
  不扩展到学校语义/版式验收；历史 30/32 后半段回放不替代新证据。
- Python 3.12 / uv 环境，以及确定性的 `doctor`、lint、type-check 和 pytest 门禁。
- 固定 Docker LibreOffice V2 视觉渲染路径，用于页面证据。
- 模板提取的架构、合同、Harness loop、三工具面、Subagent closure、发布交接和可观测性已有确定性模块 proof。
- 模板提取已具备单元阶段 checkpoint 的最小分阶段运行与恢复入口：
  `prepare-template --until unit-boundary`、`--from unit-boundary`、`--resume-proof`。
- 模板提取 static Eval 已可比较完成后的 Actual 模板产物与 Gold 模板产物。
- 用户内容提取已有 accepted 学生内容基线对应的 Gold 和 Eval 路径。
- Fill Contract v2 和 Style Contract Set 是模板提取与 final word 生成之间的共享 handoff。
- 2026-09-13 历史记录：模板提取 Registry 0.5.0 canonical source-entry/span 合同已完成 HUNAU/NJAU/PKU
  `10/10 + 10/10 + 12/12` logical-unit live E2E 与 actual DOCX/Fill Contract publication 矩阵。
  post-unit 分批候选可按受影响 source entries 局部修订；纯 exact-text 修订不能改变既有 role/field_id
  responsibility，单一责任条目的字符闭合由 Harness 使用 canonical source text 确定性完成。
  HUNAU 10 成绩评定表已发布学院、姓名、学号、年级班级、导师、题目、中文摘要和关键词 8 个字段，
  三条签名日期保持人工区。固定 Docker LibreOffice 25.2.3.2 已完成三校 32/32 source/final 渲染和
  全页复核。跨 section 的正文外层内容控件回归已修复：NJAU 06 恢复三章三页，PKU 08 第五章标题
  不再与页眉叠排。PKU 04/08 已完成锁定 OfficeCLI 1.0.143 和 Microsoft Word 实机复核：PKU 04 在
  Word 中为 1 页，确认 LibreOffice 尾部空白页是近似渲染差异；PKU 08 的两个确定性 OOXML 缺陷
  （Markup Compatibility 前缀漂移、清理后空表格单元格）已修复并重新发布，Word 无恢复提示打开为
  10 页；对实际 Word 第 5、9、10 页的补充复核确认公式、自动编号、宽表格与末章分页均保持正常横向
  版式，未复现 LibreOffice 的竖排近似显示。全仓回归为 `1178 passed / 5 skipped / 1 warning`。Phase 8 的内部工程门已关闭，但最终
  human product acceptance 仍未签收，Agent 不代签。

## 并行模块线

| 模块 | 当前状态 | 只在处理该模块时继续读取 |
| --- | --- | --- |
| 模板提取 | 全流程对象身份专项工程验收 ACCEPTED；部分样本语义/执行仍未完成，产品验收未签收 | `docs/status/active/template-full-flow-object-identity-20260922.md`、`docs/modules/template-extraction.md`、`docs/contracts/template-extraction.md` |
| 用户内容提取 | Gold 和 Eval 入口已存在；Student 002 有直接 READY proof，更广泛的质量/泛化仍单独跟踪 | `docs/modules/student-content-extraction.md`、`evals/student-content-extraction/README.md` |
| final word 生成 / Final Content Fill | 活跃工程线；style-property closure 和 final-fill readiness 尚未形成完整 accepted E2E | `docs/modules/final-word-generation.md`、`docs/status/active/docfit-field-style-property-closure.md` |

## 当前主要工作

- 三个模块并行推进时，保持各自上下文分离。
- 用具体 bug evidence、确定性测试和更新后的 Skill/Tool/Harness feedback 关闭模板提取 live-run blocker。
- 完成 style-property closure 和 final-fill readiness；段落/run 样式覆盖已可用，编号、caption scope、表格、section 和 document-level 样式物化仍是扩展区。
- 在声明任意真实学校/真实学生的产品就绪前，先证明 final word 生成的端到端链路。

## 已知问题

- `docs/status/active/**` 包含较长 capsule 记录。它们是详细证据，不是启动上下文。
- `docs/human/**` 包含讨论、学习笔记和产品评审包。AI 启动时不要默认读取。
- `docs/plans/**` 下的计划描述任务或历史设计。已完成计划不定义当前项目真相。
- `docs/bugs/**` 下的当前 bug 记录可能覆盖相关切片的乐观状态摘要。
- legacy `docfit convert` 路由和 `convert-thesis` Skill 仍存在，但它们不定义模板提取或用户内容提取边界。

## 下一步

1. 保持 `README.md`、`ARCHITECTURE.md`、`STATUS.md` 和 `AGENTS.md` 短且最新。
2. 基于 live code 和当前测试完成或刷新 active style/fill 工作。
3. 用具体 bug evidence、确定性测试和更新后的 Skill/Tool/Harness feedback 关闭模板提取 live-run blocker。
4. 模块边界被外部消费前，补齐或刷新缺失的模块 Contract。
5. 只有长期有效的决策才晋升到 ADR 或 Contract；任务执行细节留在计划或状态证据中。

## 详细证据

- 模板提取短状态：
  `docs/status/active/docfit-school-extract-v2.md`
- 模板提取模块边界、单元 checkpoint、post-unit 和阶段恢复：
  `docs/modules/template-extraction.md`
- 模板提取阶段 replay：
  `evals/template-extraction/stage-replay.md`
- 视觉渲染状态：
  `docs/status/active/docfit-libreoffice-visual-evidence-v2.md`
- 样式合同状态：
  `docs/status/active/docfit-stable-style-contract.md`
- style-property closure 状态：
  `docs/status/active/docfit-field-style-property-closure.md`
- 用户内容提取 Gold/Eval 状态：
  `docs/status/active/docfit-student-content-extraction-gold.md`,
  `docs/status/active/docfit-student-content-extraction-eval.md`
