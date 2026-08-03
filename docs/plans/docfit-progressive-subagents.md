# DocFit 渐进 Knowledge 与原生 Subagent 计划

> 状态：APPROVED_ARCHITECTURE / P1_IMPLEMENTED / VERIFIED
> 日期：2026-08-01
> 范围：先锁定长期架构与实施契约，随后由批准的 P1 完成 SDK/Skill/Knowledge
> 运行时对齐；未进入 M1 Tool 实现。

## Plan Ledger

- Canonical plan: `docs/plans/docfit-progressive-subagents.md`
- Parent baseline: `docs/docfit-00-index.md`–`docs/docfit-06-development-roadmap.md`
- Current slice: 架构文档与批准的 P1 运行时对齐均已完成；P1 执行记录由
  `docs/plans/docfit-development-plan.md` 承接
- Next action: none automatically；M1 仍需单独批准
- Blocker: none
- No-touch: 五个 Tool 的真实 M1 行为、OfficeCLI/Adobe PDF Services adapter、公开 Tool schema、学校资产持久化、工作流引擎

## 1. 决策摘要

DocFit 继续只使用 Claude Agent SDK 作为 Agent runtime。产品领域能力收敛为：

```text
两个领域 Skill
├── docfit-school-extract
└── convert-thesis

一个模块化通用 Knowledge Package

五个 DocFit MCP Tool

一个 SDK 接线级通用只读 Subagent
└── docfit-unit-analyst
```

`docfit-unit-analyst` 不是第六类产品资产、领域专家目录或文档类型枚举。它只是薄应用壳
传给 Claude Agent SDK 的一个受限配置：独立上下文、固定只读 Tool 面、无持久记忆、
无继续委派能力。为什么委派、何时委派、如何拆分、选择哪些 Knowledge、传递哪些证据
以及期待什么返回，全部由当前领域 Skill 指导主 Agent 判断。

## 2. 顶层职责

### 2.1 两个领域 Skill

- `docfit-school-extract`：解释当前任务模板、要求和示例，形成带来源引用、仅对当前任务
  有效的模板事实、冲突、不确定性和候选参数。它不生成或发布学校 Knowledge 包。
- `convert-thesis`：使用通用 Knowledge 和当前任务证据保护学生内容、规划修改、统一写入、
  重新取证并完成验证。

两个 Skill 都可以选择直接分析，也可以调用同一个 `docfit-unit-analyst` 多次。Skill 只给
主 Agent 判断维度，不给出“发现某单元就必须委派”的规则表。

### 2.2 模块化 Knowledge Package

Knowledge 是 DocFit 的产品资产分类，不是 Claude Agent SDK 中与 Skill、Tool 并列的
Knowledge Base runtime。包内内容保持跨学校、跨任务通用，可以按 `core`、封面、摘要、
目录、正文、参考文献、附录或其他真实消费场景组织；这些模块是开放的知识边界，不是
论文结构枚举。

应用壳把当前产品 Knowledge 包交给主 Agent。当前 Skill 决定本次委派需要哪些模块，
主 Agent 将选中模块的内容、模块 ID、版本和 digest 作为受控任务载荷写入 `Agent` Tool
的 prompt。当前 Python SDK 的 `Agent` Tool 不支持在单次调用中覆盖
`AgentDefinition.skills`，因此本方案不把动态 Knowledge 选择伪装成该字段已有的能力。

### 2.3 SDK 接线

薄应用壳只落实安全边界：

- 对主 Agent 暴露 `Agent`，但不把裸 `Agent` 加入通用自动批准列表；
- 只配置一个具名 `docfit-unit-analyst`；技术上使用一个内联 `AgentDefinition`，但不把它
  升级为 DocFit 领域组件或独立专家注册表；
- SDK 原生 `PreToolUse` 权限钩子只允许
  `subagent_type == "docfit-unit-analyst"`；`can_use_tool` 不是 `Agent` 的可靠执行闸门，
  只保留防御性拒绝；
- 拒绝 SDK 内置 `general-purpose`、未知类型和其他未注册类型；
- Subagent 只看见 `mcp__docfit__docx_inspect` 与
  `mcp__docfit__docx_visual_review`；
- `docx_visual_review` 只读取主 Agent 已生成的有效 `render_ref`，不调用 Adobe PDF Services API 或
  CLI 渲染，也不产生新的文档 render；
- Subagent 不看见 `Agent`、`Skill`、`AskUserQuestion`、`docx_edit`、`docx_render` 或
  `docx_validate`，也不启用持久记忆。

这层配置不选择论文单元、不加载学校规则、不拆任务，也不合并分析结果。

## 3. 自适应委派契约

主 Agent 可以不委派、委派一次、多次调用同一 Subagent、合并多个单元后委派、并行或
串行委派，也可以取得新证据后再次委派。判断维度包括：

- 当前分析对象是否实际存在；
- 证据量是否会显著挤占主上下文；
- 是否需要某类专门通用 Knowledge；
- 是否存在高风险版式或内容保护问题；
- 是否能够与其他分析独立并行；
- 委派收益是否高于额外上下文、调用和合并成本。

这些维度没有固定阈值。致谢、符号表、图表目录、声明页、复合前置结构或学校特有结构
不必被塞进预设类型；主 Agent 可以直接分析，或把一个复合范围连同相关 Knowledge 模块
交给通用 Subagent。

## 4. 委派任务包

主 Agent 传入的是当前任务事实，不是长期 Knowledge 的新副本：

```yaml
document_sha256: ...
analysis_scope:
  id: ...
  description: ...
  object_refs: [...]
  page_evidence_refs: [...]
knowledge_modules:
  - id: ...
    version: ...
    content_digest: ...
    content: ...
task_evidence:
  requirements_refs: [...]
  template_refs: [...]
known_rules: [...]
dependencies: [...]
requested_output: unit_analysis_v1
```

Subagent 不继承父对话和父 Tool 结果；需要的事实必须显式出现在任务包中。模块内容只能
来自当前产品内置 Knowledge 包，学校值只能来自 `task_evidence` 或用户确认。

## 5. 结构化返回

```yaml
status: complete | needs_more_evidence | blocked
findings: [...]
confirmed_rules: [...]
uncertainties: [...]
dependencies: [...]
cross_unit_links: [...]
evidence_requests: [...]
proposed_operations: [...]
confidence: high | medium | low
```

- `complete` 只表示本轮局部分析完成，不表示全文完成。
- `needs_more_evidence` 通过 `evidence_requests` 请求结构、页面、规则或跨单元证据；
  Subagent 不自行调用 `docx_render`。
- `blocked` 表示当前冲突、能力缺口或内容保护风险使局部结论无法安全继续。
- `proposed_operations` 只是候选操作；只有主 Agent 可以决定并串行调用 `docx_edit`。
- `confidence` 不替代证据引用、依赖声明或主 Agent 复核。

## 6. 单一写入与跨单元合并

Subagent 只分析。主 Agent 负责：

- 合并两个 Skill 或多次委派得到的任务级结论；
- 处理目录与正文标题、参考文献与正文引用、前置内容与节、页眉页脚与多个范围之间的依赖；
- 决定是否补充 inspect、render 或视觉证据；
- 重新委派或直接处理未解决范围；
- 只使用当前快照的有效 `object_ref`，串行调用 `docx_edit`；
- 修改后重新 inspect、render、visual review 和 validate。

这不是固定调用顺序。统一写入是权限与内容安全不变量，不是工作流阶段。

## 7. 验收与测试边界

测试不固定 Subagent 调用次数、调用顺序、并行度、论文单元枚举或“每个单元必须委派”。

P1 实现切片已经证明：

- 复杂、证据密集场景能够委派；简单场景允许不委派；
- 不存在的单元不会被强制创建；未匹配和复合范围可以直接或合并处理；
- 并行与串行都是合法行为；
- `PreToolUse` 权限钩子只允许 `docfit-unit-analyst`，确定性测试拒绝
  `general-purpose` 与未知类型；
- Subagent 始终只有 inspect 与 visual-review 两个只读 Tool；
- Subagent 只收到选中 Knowledge 模块和显式任务证据；
- 缺少页面时返回 `needs_more_evidence`，主 Agent 补证后可以重新委派；
- `docx_edit`、render 成本控制、跨单元合并和最终发布始终由主 Agent 掌握；
- 无论采用哪条合法分析路径，源文件只读、Knowledge 通用性、证据绑定和内容保护不变量成立。

## 8. 非目标

- 六个或更多单元专家目录、AgentDefinition 注册表或固定论文类型枚举；
- 固定复杂度阈值、单元到 Agent 的强制映射、阶段 DAG 或任务队列；
- 自定义 Workflow Tool、领域工作流 Hook 编排、第二 Agent runtime 或应用壳领域调度；
  P1 只使用一个 SDK `PreToolUse` 安全钩子落实已批准的类型白名单；
- Subagent 写入、渲染、验证、询问用户、持久记忆或嵌套委派；
- 第六个 DocFit MCP Tool；
- 学校模板、规则、数值、固定文案或历史结论进入产品 Knowledge；
- 复制许可证未确认的旧 `docfit-school-extract` 内容。新 Skill 只复用名称和经过重新
  设计、重新测试的任务级目标。

## 9. 分阶段实施

### A. 文档架构切片（已完成）

- 协调更新 00–06；
- 更新 README 与边界说明；
- 在该切片完成时如实记录代码仍是 M0 + Knowledge v1；
- 运行长期文档一致性与漂移检查。

### B. Provider-independent SDK/Skill/Knowledge 切片（P1 已批准并完成）

- 重写两个领域 Skill；
- 复用现有 manifest document ID/hash，形成最小可选择 Knowledge 投影，不改变包结构
  或 schema 版本；
- 在应用壳中配置一个内联 `docfit-unit-analyst`；
- 使用 `PreToolUse` 类型闸门并更新 doctor、smoke 和分层测试；
- 不实现真实 DOCX Tool，也不进入 M1。

### C. M2 组合与真实 Eval（依赖 M1）

- 使用真实五 Tool 结果形成任务包；
- 证明选择性 Knowledge 载荷、证据请求、重新委派和主 Agent 单一写入；
- 不把一次具体委派轨迹保存成 Gold。

## 10. 文档切片 Preflight

```text
Preflight status: APPROVED_DOCS_ONLY
Task source: 用户架构决策 + docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md
Canonical source: docs/plans/docfit-progressive-subagents.md
Route: durable $intuitive-flow
Goal: 只落地长期文档和实施契约，不修改运行时代码。
Scope: 新计划、00–06、README 与必要边界说明。
Non-goals: 所有 Python、Skill、Knowledge package 数据和测试修改；M1 Tool 实现。
Unknown-unknown scout: skipped；用户已明确收敛架构，且当前 SDK 的 AgentDefinition 与 Agent Tool 输入契约已用本机 0.2.128 类型和官方文档核对。
Acceptance: 文档对两个 Skill、模块化 Knowledge、五 Tool、一个 SDK 接线级只读 Subagent、动态 prompt 载荷、默认拒绝和单一写入表述一致；不出现固定工作流或六专家目录。
Verification: 精确搜索旧断言、跨文档术语核对、git diff 检查与 doc-keeper audit。
Execution: main session direct；worker none。
Stop: 文档验收后停止，不自动开始 SDK/Skill/Knowledge 实现。
```

## 11. 文档切片验收证据

- `docs/docfit-00-index.md`–`docs/docfit-06-development-roadmap.md` 已协调对齐；README
  与 app/Knowledge 边界说明同步更新。
- Doc Keeper 审计以当前代码反向核对：M0 仍只开放 `Skill` 与 `AskUserQuestion`、只
  装载 `convert-thesis` discovery marker，Knowledge loader 仍执行 v1 完整性契约；
  所有新能力均明确标记为批准目标或后续切片，没有冒充当前实现。
- 五个公开 Tool 名称、默认拒绝、学校事实只属于当前任务、源文件只读和主 Agent
  单一写入边界未被改写。
- 固定单元枚举、固定复杂度阈值、强制委派、六专家目录和 per-call 动态
  `AgentDefinition.skills` 均被明确排除。
- `git diff --check` 通过；`uv run pytest -q` 为 `90 passed`；`uv run docfit doctor`
  的 M0 base gate 为 `PASS`，Provider `NOT_READY` 仍是 M1 预期边界。

## 12. P1 实施结果

- `.claude/skills/docfit-school-extract/SKILL.md` 与
  `.claude/skills/convert-thesis/SKILL.md` 已按当前任务证据、五 Tool 和可选只读委派
  契约实现；未复制许可证未确认的旧 Skill 正文。
- Knowledge loader 可按既有文档 ID 选择模块，并返回包 ID、包 digest、模块 digest 与
  内容；未选择文档不会进入返回值，包的完整性和通用性契约保持不变。
- 应用壳只配置一个 `docfit-unit-analyst`。真实 SDK 运行揭示 `can_use_tool` 不会可靠
  拦截 `Agent`，因此最终实现用 `PreToolUse` 拒绝非具名类型，并用确定性测试覆盖
  `general-purpose`、未知类型和缺失类型。
- Subagent live smoke 已观察到具名 `Agent` 仅调用 inspect + visual-review，接收显式
  任务包与所选 Knowledge，并返回完整 `unit_analysis_v1`；在该 P1 验收时五个 Tool
  仍为 M0 stub。后续 M1–M3 状态由统一开发计划记录。
