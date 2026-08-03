# DocFit M1–M2 产品开发与后续 M3 评测计划

> 状态：COMPLETED；M1/M2 与非评测产品支撑已完成，M3 评测延期
> 日期：2026-08-03
> 长期基线：`docs/docfit-00-index.md`–`docs/docfit-06-development-roadmap.md`

## Plan Ledger

- Plan status: COMPLETED
- Session scope: m1-m2-product
- Parent plan: `docs/plans/docfit-progressive-subagents.md`
- Child plans: `docs/plans/docfit-m1-tools-v1.md`（COMPLETED）
- Last updated: 2026-08-03
- Current slice: 当前非评测产品开发已完成；M3 Eval/Gold/真实样本资格验证/人工复核
  移出当前范围
- Completed implementation proof: 124 tests、严格 mypy/ruff、build/lock、base/provider/
  agent-smoke doctor、四条真实 SDK smoke、Adobe 合成与 15 页授权复杂样本
  baseline/candidate/cache hit、真实 SDK 合成 convert，以及 core Eval 7/7、41 assertions
- Next action: 当前计划无剩余开发项；如开始 M2 后核心转换优化，按 06 第 6.6 节另建
  可执行计划并先完成 O0 观测面；恢复 M3 时另建并批准评测计划
- Follow-on decision: 核心转换优化与 M3 Eval 分轨；先测量再减少重复 Tool 调用，
  不以恢复评测、真实样本或平台化为前提
- Blocked on: none
- Do not touch from this session: M4/M5、第三后端、通用 Provider 抽象、GUI/API/任务队列
- Unknown-unknown scout: 自动 `autoplan` 因当前宿主没有 AskUserQuestion 能力不可运行；已执行
  等价的本地人工 scout。OfficeCLI 1.0.143 的结构化读写、validate、原子 batch 与 HTML
  screenshot 合成 PoC 通过；其 `dump` 不携带 styles/numbering/theme 等兄弟依赖，因此
  `import_template_sections` 采用 DocFit 最小 OOXML 依赖闭包；Adobe service-principal
  bundle、SDK 4.2.0 与 Poppler 已发现，凭据已安全迁移到仓库外 0600 环境文件；两份
  授权样本已按 SHA-256 找到并完成只读真实链路；样本质量未通过，不能据此宣称 MVP。

## 0. 当前范围修订（2026-08-03）

用户明确将 M3 的评测部分移出当前开发范围。自本修订起：

- 当前计划的完成对象是 M0–M2 产品链路，以及其中必需的 Tool、Skill、Knowledge、
  SDK、权限、安全、证据、报告和回归测试；
- `docfit eval --suite core`、现有合成 fixture 和探索性真实样本证据可以保留，但不再
  构成当前完成门；
- M3 的 Skill/E2E Eval 扩展、Gold、授权/脱敏真实样本资格验证与外部人工复核整体
  延期，既不标记通过，也不作为当前 blocker；
- 未来恢复 M3 必须依据 06 第 7 节新建并批准计划；M4/M5 仍不在范围。

## 1. 当前结论

当前实现不是旧架构的错误落地，而是一个边界清楚、验证通过的早期切片：

- M0 已完成 Python 包、CLI、doctor、Claude Agent SDK、五个公开 Tool 名称和默认拒绝；
  当前 live receipt 状态以 active capsule 和 `doctor --require agent-smoke` 为准，不能沿用
  历史 PASS；
- Provider-independent 通用 Knowledge Package v1 已完成只读加载、hash/digest、通用性
  边界和构建发布检查；
- P1 已落地两个正式领域 Skill、最小 Knowledge 选择投影和
  `docfit-unit-analyst`；真实 DOCX Tool 与双固定后端从本计划的 M1 切片开始实现。

因此没有对 M0 或 Knowledge v1 做推倒重来。建计划时与最新长期文档不一致的是旧执行
状态，这些记录现已在 P0/P1 中纠正：

- `docs/status/active/docfit-m0.md` 仍把 M1 记为唯一下一步；
- `docs/status/active/docfit-knowledge-package-v1.md` 仍把 Knowledge 运行时组合全部推迟到
  M1/M2；
- `docs/migration-asset-inventory.md` 仍要求在 M1 后才重写 `convert-thesis` marker；
- 最新 06 已批准一个独立的 Provider-independent 实现切片；为先校正既有运行面，
  本计划明确把它排在 M1 之前。

本计划先纠正执行顺序，再以独立验收门推进产品里程碑。00–06 继续作为架构和阶段
验收的唯一长期基线；本计划不覆盖或重写其职责。初始目标曾批准推进 M1–M3，随后
用户将 M3 评测移出当前范围。因此本计划以 M1/M2 完成收口；M3 的长期定义和完成门
保持不变，但等待未来独立计划。

## 2. 统一 Preflight contract

```text
Preflight status: COMPLETED
Task source: 用户“制定到 M3 的开发计划，并且完成开发” + docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md + 当前 M0/Knowledge/P1 实现
Canonical source: docs/plans/docfit-development-plan.md
Route: durable $intuitive-flow
Goal: 以 P1 已验证基础为起点，完成 M1 五 Tool 和 M2 第一条 Agent 端到端转换链路；M3 评测按 2026-08-03 用户修订延期。

Scope:
- M1：五个稳定公开 Tool、固定 OfficeCLI/Adobe PDF Services 后端、快照 ref、原子编辑、独立验证、三种 render intent、图片证据与开发者 tools CLI。
- M2：公开 docfit convert；真实 Claude Agent SDK + 两个领域 Skill + 通用 Knowledge + 只读 Subagent + 五 Tool；产出 final.docx、candidate PDF/pages、visual-review.json、validation.json。
- M3（当前范围外）：Skill/端到端 Eval 扩展、Gold、普通/风险 fixture 扩充、授权或脱敏复杂真实样本资格验证和高风险人工复核。
- 每个阶段同步受影响的 00–06、README、迁移清单、active capsule；M0/P1 权限和 live smoke 不回归。

Non-goals: M4/M5 产品化、第三 Provider、动态 Provider 注册/故障转移、GUI/API/任务队列、并发转换作业、学校规则持久化或进入产品 Knowledge、把近似渲染当成 Adobe 完成证据。
Entity budget: reuse=五个 Tool 名称、现有 SDK Agent loop、两个 Skill、通用 Knowledge manifest、唯一只读 Subagent、OfficeCLI、Adobe PDF Services、Poppler；remove/merge=删除本地 Word/AppleScript adapter，以真实 Adobe handler 替换，不保留第二套 Tool/runtime/转换循环；new=M1 两个具名 adapter 与最小 runtime/schema/OOXML/image helper、M2 薄 convert 应用服务；already-present optional assets=最小 core eval runner 和风险 fixtures，不继续扩展；expansion triggers=恢复 M3、第六 Tool、第三引擎、通用 Provider 抽象、第二 Agent loop、学校持久化、OfficeCLI fork 或新增对外服务时重新审批。
Context: must-read=AGENTS.md、docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md、本计划、M1 子计划和当前 app/knowledge/tools/skills/tests；useful=本机 OfficeCLI/Adobe PDF Services/Poppler 能力帮助与授权样本 hash；avoid-unless-needed=M4/M5、未授权旧实现正文和其它 Provider。

Acceptance:
- SUCCESS_M1: 满足 06 第 5 节及 M1 子计划全部 deterministic/integration/product/live Adobe 完成门。
- SUCCESS_M2: 满足 06 第 6 节，公开 convert 在合成案例上生成全部规定产物，源文件只读，Adobe baseline/candidate 与独立 validate/全页视觉覆盖可核对。
- M3 后续门：满足 06 第 7 节后才称 MVP；该门不属于当前计划。
- BLOCKED_NEEDS_DECISION: 必须突破 entity budget、修改五个 Tool 名称/默认拒绝、引入新引擎/循环或长期合同互相冲突。
- BLOCKED_NEEDS_LOCAL_VALIDATION: M1/M2 所需 Adobe 或真实 SDK 门暂时不可运行时，不得宣称对应产品里程碑完成；M3 样本与人工门不属于当前计划。
- No regressions: M0/P1 四个 live smoke、Knowledge digest、具名 Subagent 闸门、源只读、无正文日志和构建发布合同保持。

Verification: deterministic=uv sync --frozen; uv lock --check; uv build; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run docfit doctor; git diff --check；integration=M1 Tool/adapter/ref/atomic/route + M2 SDK orchestration/artifacts；product-run=06 中 M1 tools 与 M2 convert；live=真实 OfficeCLI、Adobe PDF Services、Poppler、Claude SDK 与合成转换；optional=core Eval、探索性授权样本以及 Microsoft Word 桌面兼容性观察。
Execution: main=主会话按 M1→M2 执行并持有最终判断；M3 另行计划；worker=none；worker-goal=none。
To execute: /goal execute docs/plans/docfit-development-plan.md with intuitive-flow
Optional tracking: none
Approval: 用户于 2026-08-03 明确将 M3 评测移出当前范围；M1/M2 完成，恢复 M3 或触发 expansion 时重新请求决定。
```

## 3. 执行顺序

### P0：执行记录对齐（本计划建立时完成）

- 更新 M0、Knowledge active capsule 的下一步；
- 更新迁移清单中两个 Skill 的目标切片；
- 保留当前代码、测试和 public Tool 名称不变；
- 不把“尚未实现”误报成“实现冲突”。

### P1：Provider-independent 架构对齐（已完成）

目标是把已经开发的 M0 + Knowledge v1 运行面调整到最新批准架构，但仍不实现真实
DOCX 行为，也不进入 M1。

1. 重写 `.claude/skills/convert-thesis/SKILL.md`，移除 M0 discovery marker 角色；
2. 从零实现 `.claude/skills/docfit-school-extract/SKILL.md`，只产生当前任务证据；
3. 直接复用现有 Knowledge manifest/document ID，把每个已声明通用文档作为可选择的
   逻辑模块；选择结果携带 document ID、包版本、文档 SHA-256 和内容，不新增第二份
   manifest、学校包、向量库或模块目录枚举；
4. 在薄应用壳中内联配置唯一 `docfit-unit-analyst`；主 Agent 可见 `Agent` Tool，
   但裸 `Agent` 不进入自动批准列表；
5. 用 SDK 原生 `PreToolUse` 权限钩子只批准
   `subagent_type == "docfit-unit-analyst"`，拒绝 `general-purpose` 和未知类型；
   `can_use_tool` 保留为用户追问和防御性拒绝边界；
6. Subagent 只看见 `mcp__docfit__docx_inspect` 与
   `mcp__docfit__docx_visual_review`，不看见 Skill、Agent、AskUserQuestion、render、
   edit、validate 或持久记忆；
7. 两个领域 Skill 决定是否委派、分析范围、Knowledge 选择和显式任务证据；应用壳只
   配置权限和隔离，不识别论文单元、不解析学校规则；
8. 固化 `unit_analysis_v1` 的任务包示例、结构化返回校验和 live smoke 证据；
9. 保留三个既有 M0 live smoke 命令；图片 smoke 不再依赖 Skill 内的 M0 专用说明，
   并新增一个受限 Subagent live smoke；
10. 根据实现事实同步所有受影响的 00–06、README、目录说明、迁移清单和 active
    capsule，然后停止，不自动进入 M1。

P1 不改变五个 public Tool 名称或 M0 stub 的真实 DOCX 能力。Knowledge 的最小模块投影
复用现有 `KnowledgeDocumentSpec.id` 和 `sha256`；在真实消费证据出现前，不增加
`schema_version`、新 package 版本或 `cover/toc/body` 固定分类。

### P2：M1 五 Tool 与双固定后端

P1 通过后，执行现有 `docs/plans/docfit-m1-tools-v1.md`，并在开始前重新核对其本机
OfficeCLI、Adobe PDF Services、Poppler 和授权样本证据。M1 只实现五个 Tool 的确定性能力和
开发者 CLI，不调用 Agent 完成论文转换。

M1 的完成门、停止门和 Adobe PDF Services 真实性证明继续以 06 第 5 节及 M1 Preflight 为准。
如果 PoC 证明必须引入第三个引擎、通用 Provider 抽象、OfficeCLI fork、第六个公开
Tool 或部分发布，停止并重新审批。

### P3：M2 第一条 Agent 端到端链路

依赖 P1 与 M1 都通过。把两个 Skill、模块化 Knowledge 投影、只读 Subagent 和五个真实
Tool 组合为 `docfit convert`。用合成任务材料证明源文件只读、主 Agent 单一写入、
Adobe baseline / OfficeCLI edit feedback / Adobe candidate verification、全部最终页面视觉
覆盖和独立 validate。

P3 只达到合成 smoke case 的完整链路，不宣称真实论文交付质量。

### P4：M3 可试用 MVP（当前范围外，后续独立计划）

按 06 第 7 节增加 Tool test、Skill eval、端到端 Eval、3–5 个单风险 fixture 和一份
授权或脱敏复杂样本。每个真实缺陷必须落到 Skill、Knowledge、Tool、Eval 或 App 中的
明确责任面，并留下对应回归资产。

### P5：M4/M5 按证据演进

先以跨学校任务验证通用 Knowledge，再按真实使用数据决定产品化能力。学校事实、模板、
精确格式值和任务结论始终不进入产品 Knowledge；第三个引擎和 Provider 抽象只有在
真实动态选择或故障转移需求出现后才评估。

## 4. P1 文件与责任边界

| 责任 | 允许修改 | 必须保持 |
|---|---|---|
| 领域 Skill | `.claude/skills/docfit-school-extract/`、`.claude/skills/convert-thesis/` | 无固定 DAG、无学校值、无 OOXML 直写 |
| Knowledge 选择 | `src/docfit/knowledge/` 与对应 unit tests | 单一产品包、现有完整性校验、无学校持久化 |
| SDK 接线 | `src/docfit/app/agent.py`、doctor/smoke 的最小配套 | 应用壳不做领域判断；默认拒绝 |
| Tool smoke | 现有 M0 stub 和图片 smoke 的最小兼容调整 | 五个名称不变；不增加真实 DOCX 行为 |
| 验证 | `tests/unit/`、`tests/contract/`、`tests/integration/` | 不固定委派次数、顺序、并行度或单元枚举 |
| 文档 | 受实现事实影响的 00–06、README、active capsule | 长期文档与代码同批更新 |

## 5. P1 验收与停止门

P1 成功必须同时证明：

- 两个领域 Skill 可发现，且学校专属结论只存在于显式当前任务证据；
- 现有 Knowledge 文档可按 ID 选择，返回包版本、内容和可核对 digest，未选择内容不
  进入合成 Subagent 任务包；
- 主 Agent 可见 Agent Tool，但只有 `docfit-unit-analyst` 被 SDK `PreToolUse` 权限
  钩子批准；
- `general-purpose`、未知 Subagent、Subagent 写入/渲染/验证/继续委派均被拒绝；
- Subagent 的实际 Tool 面只有 inspect + visual-review，缺证据时返回
  `needs_more_evidence`；
- `unit_analysis_v1` 包含 status、confidence、findings、confirmed_rules、
  uncertainties、dependencies、cross_unit_links、evidence_requests 和
  proposed_operations；
- 复杂合成场景可以委派，简单场景允许主 Agent 直接处理；测试不锁定具体轨迹；
- M0 三个 live smoke、五 Tool 名称、base doctor、Knowledge v1 完整性和默认拒绝全部
  无回归；
- 00–06 对“当前已实现”与“后续目标”的描述已经随代码同步。

遇到以下任一情况停止并请求决定：

- 需要第二个 Subagent 类型、AgentDefinition 注册表或固定文档单元枚举；
- 需要把学校规则写入 Skill、Knowledge 或持久 profile；
- 需要新公开 Tool、真实 DOCX 行为或 M1 Provider；
- 当前 SDK 无法可靠限制 Subagent Tool 面或无法拒绝未知 `subagent_type`；
- 模块选择必须破坏现有 Knowledge 完整性契约才能实现，且无法通过现有 document ID
  投影满足。

## 6. P1 Preflight contract

```text
Preflight status: APPROVED_P1
Task source: 用户目标 + docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md + 当前 M0/Knowledge v1 实现
Canonical source: docs/plans/docfit-development-plan.md
Route: durable $intuitive-flow
Goal: 在不实现真实 DOCX Tool 的前提下，把现有 M0 + Knowledge v1 调整为两个领域 Skill、可选择通用 Knowledge、一个 SDK 原生只读 docfit-unit-analyst 的最新批准运行边界。

Scope:
- 重写 convert-thesis marker，并从零增加 task-scoped docfit-school-extract。
- 复用现有 Knowledge document ID/hash 形成最小可选择模块投影，不改变学校事实边界。
- 让 Agent 对主 Agent 可见，内联配置唯一 docfit-unit-analyst，并通过 SDK PreToolUse 权限钩子落实精确 subagent_type 白名单。
- 将 Subagent 限制为 inspect + visual-review，验证无写入、无渲染、无验证、无用户追问、无继续委派和无持久记忆。
- 固化显式任务包与 unit_analysis_v1 返回校验；证明选择性 Knowledge、上下文隔离、证据请求和主 Agent 单一写入边界。
- 更新 doctor、既有 smoke、一个新 Subagent live smoke、unit/contract/integration 测试及所有受影响文档。

Non-goals: 真实 DOCX inspect/edit/render/visual-review/validate、OfficeCLI/Adobe PDF Services adapter、M1 Tool schema、docfit convert、学校包/profile/数据库、固定委派图、多个专家、Provider 抽象、M2–M5。
Entity budget: reuse=现有两个目标名称、Knowledge manifest/document ID/hash、Claude Agent SDK AgentDefinition/Agent Tool、五 Tool 名称与 M0 smoke；remove/merge=移除 convert-thesis 的 M0 marker 角色，不保留第二套 Skill 或 Knowledge manifest；new=一个新的 docfit-school-extract Skill 文件、一个内联 AgentDefinition、最小 Knowledge 选择函数/类型、unit_analysis_v1 校验和一个 Subagent live smoke；expansion triggers=第二个 Subagent、新 schema version、新 Knowledge package 版本、新公开 Tool 或真实 Provider 均需重新审批。
Context: must-read=AGENTS.md, docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md, docs/plans/docfit-progressive-subagents.md, docs/plans/docfit-development-plan.md, current src/docfit/app/, src/docfit/knowledge/, src/docfit/tools/, .claude/skills/, tests/contract/; useful=docs/migration-asset-inventory.md and installed claude-agent-sdk 0.2.128 type definitions; avoid-unless-needed=M1 backend implementation, unlicensed legacy Skill bodies, M2–M5 details.

Acceptance:
- SUCCESS: 两个 Skill、选择性 Knowledge、唯一只读 Subagent、精确权限白名单、结构化返回和 live smoke 全部可观察通过，且长期文档与实现同步。
- BLOCKED_NEEDS_DECISION: SDK 无法落实精确类型/Tool 隔离，或最小 document-ID 模块投影无法满足任务包证据；否则 none。
- BLOCKED_NEEDS_LOCAL_VALIDATION: 新 Subagent live smoke 或现有三个 M0 live smoke 未在真实 SDK/backend 下通过；否则 none。
- INTERMEDIATE_ONLY: none。
- No regressions: 五个 mcp__docfit__ 名称、默认拒绝、AskUserQuestion 同会话、图片 content block、Knowledge v1 digest、源文件只读边界和 base doctor 保持。

Verification: deterministic=uv sync --frozen; uv lock --check; uv build; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run docfit doctor; git diff --check；integration=两个 Skill discovery + Knowledge selection/omission + AgentDefinition/permission/context/result contract；product-run=uv run docfit agent-smoke --case image + ask-user + denied-tools + 新 subagent case；local-live-manual=真实 Claude Agent SDK/backend 下四个 smoke + uv run docfit doctor --require agent-smoke；optional=none。
Execution: main=主会话按 Knowledge 最小投影→Skill→SDK 权限接线→确定性测试→live smoke→doc-keeper 顺序执行并持有最终判断；worker=none；worker-goal=none。
To execute: /goal execute docs/plans/docfit-development-plan.md with intuitive-flow
Optional tracking: none
Approval: 用户已于当前会话回复“继续”批准 P1；P1 完成后停止，M1 仍需单独批准。
```

## 7. P1 实施结果

- 两个领域 Skill 已替换 discovery marker，并把学校规则严格限制在当前任务证据；
- Knowledge 选择复用现有 manifest document ID/hash，未增加 schema、包版本或第二份
  manifest；
- 薄应用壳只配置一个具名只读 `docfit-unit-analyst`。真实 SDK 证明
  `can_use_tool` 不是 `Agent` 的可靠必经路径，最终用 `PreToolUse` 落实精确类型闸门；
- 四条 live smoke 在 Kimi 上通过；Subagent 实际只调用 inspect + visual-review，收到
  显式任务包并返回完整 `unit_analysis_v1`；
- P1 验收当时五个公开 Tool 仍是 M0 stub；后续实现状态见下节，不改写这条历史证据。

## 8. M1–M3 当前实施结果

- M1（完成）：五个公开名称不变；真实 inspect/edit/render/visual-review/validate、版本化 schema、
  快照 ref、原子编辑、独立 package/效果后置检查、最小模板依赖闭包、OfficeCLI
  `edit_feedback`、Adobe-only baseline/candidate、图片派生和开发者 CLI 已实现。真实
  OfficeCLI integration、Provider 伪成功、失效 ref、跨 run 文字、bbox 和六条 CLI 门
  已通过；Adobe 合成和授权复杂样本 baseline/candidate、cache/parent ref、30 秒连接/
  120 秒读写超时及 provider doctor 已通过。M1 的完成不替代 M3 质量验收。
- M2（完成）：`docfit convert` 以同一 SDK runtime 挂载只读输入、完整通用 Knowledge、两个
  Skill、唯一只读 Subagent 和五个 Tool；结构化 finalizer 要求六种 SDK Tool use、当前
  Adobe candidate PDF、全页 review、无 blocking finding、源 hash 不变和独立 validate。
  fake-Agent 集成与真实 SDK + Adobe 两页合成产品门均通过，规定产物完整发布。
- M3（延期，当前范围外）：已增加一个普通合成案例、四个生成式单风险 DOCX、Provider 伪成功风险、三个
  Skill case、一个端到端合同、人工交付页面 checklist 和最小 core runner。确定性 core Eval
  为 7/7、41 assertions。15 页授权复杂样本已经完成 Adobe baseline/candidate/cache、
  全页 Agent review、局部 crop、同快照 OfficeCLI/Adobe anchor 对照和独立高风险复核；
  结果正确拒绝交付：6 个 blocking finding，外部人工签字为 NOT_PERFORMED。因此真实链路
  可工作，但这些只是已存在的探索资产。当前不继续 M3 完成门，也不能称为 MVP。
- 隐私边界：授权样本源 SHA-256 前后不变；正文、绝对私有路径和凭据不进入提交、计划、
  日志摘要或 Eval fixture。私有运行证据只保留在被忽略的授权任务目录。

## 9. 后续核心转换优化决策（不重开本计划）

M1–M2 的完成状态不因后续性能工作改变。用户已批准把下一步边界写入文档，但尚未
批准或执行新的实现计划。后续计划必须以 06 第 6.6 节为准：

- 先把总耗时、各 Tool 调用/耗时、解析与渲染缓存、Adobe 调用/cache hit、页面与图片
  字节、重试和首个失败来源写入隐私安全的 `conversion-report.json`；
- 再依次减少无新增证据的重复 Tool 调用、复用单次运行解析/渲染结果、优化页面批次与
  图片载荷、收紧同条件无效重试；
- 每次只优化一个主要指标，并保持全部普通产品回归门；普通测试和 live smoke 不属于
  M3 Eval，不因 M3 延期而取消；
- M3 Eval/Gold/真实样本/人工复核，以及平台化、第三引擎、跨任务持久缓存等延期项不
  随该优化计划自动进入范围。
