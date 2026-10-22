# DocFit 文档系统重组草案

状态: temp 草案，不是当前项目真相
日期: 2026-08-18
适用范围: DocFit 全仓库文档治理

本文用于先在 `temp/` 下完整梳理目标文档系统。正式文档在本草案确认前不应继续按当前
目录结构做局部索引修补；确认后再用一组有边界的提交替换当前正在使用的文档面。

## 依据

- 用户要求：`AGENTS.md` 保持薄，只写 Agent 启动、模块耦合、失败定位、human 边界和提交纪律。
- 用户要求：`docs/human/**` 是面向人的材料，不是 Agent 默认上下文。
- 用户要求：DocFit 三个模块并行开发，模块上下文不能混读。
- 本地参考文档：
  `/Users/xpw/Downloads/软件架构思维（持续编写版）/part-v/28-ai-coding-software-development/28-05-ai-coding-doc-system-lifecycle.md`
- 已确认原则：文档系统按权威性和生命周期分层，临时计划、讨论稿、日志和旧状态不能冒充当前真相。

## 当前痛点

1. 当前很多索引是在既有目录上做修补，容易把“现在有什么文件”误写成“未来应该怎么组织”。
2. `docs/human/**` 中有大量有价值讨论，但文档长、分散、状态混杂，Agent 默认读取会污染上下文。
3. `docs/plans/**` 和 `docs/status/active/**` 中有很多任务过程和阶段证据，完成后没有稳定退出机制。
4. `docs/docfit-00-index.md` 历史上同时承担索引、架构摘要、当前真相、清理规则，职责过重。
5. 三个产品模块需要不同上下文，但现有文档容易通过交叉链接把模板提取、用户内容提取和 final word 生成混在一起。
6. 长期有效结论没有稳定晋升路径，导致同一事实可能散落在 plan、human note、status capsule、Skill 和 AGENTS 中。

## 重组目标

- 让根目录文档回答最少问题，不承载长历史。
- 让 `docs/README.md` 成为文档生命周期和目录路由入口。
- 让 `docs/modules/**` 成为三模块上下文路由，不让 Agent 一次性加载所有模块资料。
- 让 `docs/contracts/**` 存放跨模块稳定交接合同。
- 让 `docs/plans/**`、`docs/status/active/**`、`docs/bugs/**` 明确降级为任务执行面和证据面。
- 让 `docs/human/**` 保持 human-facing，但结论一旦确认就提炼到正确文档面。
- 新增 `docs/runbooks/**` 和 `docs/agents/**`，承接操作手册和较长 Agent runbook，避免塞进 `AGENTS.md`。
- 更新文档合同测试，防止被删除的权威入口、旧工具数量约束和错误默认阅读路径重新出现。

## 目标文档面

| 文档面 | 目标位置 | 谁主要读 | 负责什么 | 生命周期 |
| --- | --- | --- | --- | --- |
| 项目入口 | `README.md` | 人和 AI | 项目是什么、怎么跑、当前主要入口 | 运行方式或入口变化时更新 |
| 架构地图 | `ARCHITECTURE.md` | 人和 AI | 模块边界、数据流、关键接口、扩展点、禁区 | 模块或合同变化时更新 |
| 当前状态 | `STATUS.md` | 人和 AI | 现在可用、正在做、已知问题、下一步 | 阶段结束或恢复项变化时更新 |
| Agent 操作 | `AGENTS.md`、`CLAUDE.md` | AI | 启动阅读路径、Agent 行为边界、提交纪律 | 稳定工作方式变化时更新 |
| 文档路由 | `docs/README.md` | 人和 AI | 文档面、生命周期、目录入口 | 文档系统结构变化时更新 |
| 模块路由 | `docs/modules/**` | AI 为主，人也可读 | 三模块职责、禁读边界、下一层上下文 | 模块边界变化时更新 |
| 稳定合同 | `docs/contracts/**` | 人和 AI | 跨模块产物、schema、失败语义、验收语义 | 合同版本变化时更新 |
| 操作手册 | `docs/runbooks/**` | 人和 AI | 真实命令、排障、发布、Gold review、本地观察 | 命令或环境变化时更新 |
| Agent runbook | `docs/agents/**` | AI | 较长 Agent 工作流、工具坑点、失败定位经验 | 稳定经验变化时更新 |
| 任务计划 | `docs/plans/**` | 当前协作者和 AI | 一次任务的目标、步骤、验收、风险 | 任务完成后归档或提炼 |
| 状态证据 | `docs/status/active/**` | 当前协作者和 AI | 阶段 capsule、阻塞、proof 指针 | 阶段完成后压缩或归档 |
| Bug 证据 | `docs/bugs/**` | 当前协作者和 AI | 复现、根因、修复证据 | bug 关闭后归档或提炼 |
| 决策记录 | `docs/adr/**` | 人和 AI | 重要取舍的背景、决策、后果、重看条件 | 低频新增，过期时 superseded |
| Human 背景 | `docs/human/**` | 人 | 学习笔记、讨论、产品评审、解释性材料 | 仅按需读取，确认结论要晋升 |
| Memory | `memory/**` | AI | 短、准、有日期的可复用经验 | 定期压缩、过期删除 |
| 证据输出 | `output/**`、`temp/**` | 当前任务或复盘 | 命令输出、截图、临时草案、实验材料 | 不直接代表当前事实 |

## 目标目录结构

```text
README.md                 # 项目入口：项目是什么、怎么跑、当前主要入口
ARCHITECTURE.md           # 全局架构：模块边界、数据流、关键接口、扩展点和禁区
STATUS.md                 # 当前状态：可用能力、正在做什么、已知问题和下一步
AGENTS.md                 # Agent 启动规则：默认阅读路径、行为边界、失败定位、提交纪律
CLAUDE.md                 # Claude Code 兼容入口：只转发到 AGENTS.md

docs/
  README.md               # docs 目录入口：文档面、生命周期、目录路由

  modules/                # 三个产品模块的上下文路由，不放跨模块长历史
    README.md             # 选择当前任务属于哪个模块，以及下一层读什么
    template-extraction/  # 模板提取：学校模板/要求 -> 模板产物
      README.md           # 模块职责、禁读边界、主要入口
      context.md          # 该模块的上下文加载规则和当前可读材料
      eval.md             # 该模块的 Eval/Gold/验证入口
    student-content-extraction/  # 用户内容提取：学生源论文 -> Student Content Model
      README.md           # 模块职责、禁读边界、主要入口
      context.md          # 该模块的上下文加载规则和当前可读材料
      eval.md             # 该模块的 Eval/Gold/验证入口
    final-word-generation/  # final word 生成：模板产物 + 学生内容 -> 最终 Word
      README.md           # 模块职责、禁读边界、主要入口
      context.md          # 该模块的上下文加载规则和当前可读材料
      eval.md             # 该模块的 Eval/Gold/验证入口

  contracts/              # 稳定交接合同；跨模块消费时只认这里的合同语义
    template-extraction.md # 模板提取输入、输出、失败语义和发布不变量
    student-content-model.md # 学生内容模型结构、顺序、来源追踪和 field 绑定
    fill-contract.md      # 模板提取到 final word 生成的填充合同
    style-contract.md     # 样式观察、选择、物化和 fallback 的稳定语义
    gold-system.md        # Student、Template、Filling Truth 的 Gold 体系

  runbooks/               # 人和 AI 都可用的真实操作手册，必须贴近可运行命令
    local-development.md  # 安装、doctor、lint、type-check、pytest、本地依赖
    observability.md      # observer、渲染证据、本地问题定位操作
    gold-review.md        # Gold 文件人工评审和 Word-native comment 工作流
    template-extraction-live-run.md # 真实学校模板提取的运行与排障步骤

  agents/                 # 较长 AI 工作流和经验，按需读取，不进入 AGENTS.md
    failure-diagnosis.md  # 复杂失败先按模块、checkpoint、责任层归因
    sdk-boundaries.md     # Claude Agent SDK-native 边界和不要自建 runtime 的经验
    docx-tool-hazards.md  # DOCX、OfficeCLI、LibreOffice、hash/schema 的常见坑

  adr/                    # 长期重要决策；不记录普通实现步骤
    README.md             # ADR 格式、状态和索引

  plans/                  # 一次任务的执行计划；任务完成后归档或提炼
    README.md             # plan 写法、active/archive 规则
    active/               # 当前仍在执行的计划
    archive/              # 已完成或被取代的计划

  status/                 # 阶段状态 capsule；不替代 STATUS.md
    active/               # 当前仍有恢复价值的阶段状态
    archive/              # 已完成或失效的阶段状态

  bugs/                   # 具体 bug 的复现、归因、修复证据
    active/               # 当前仍打开的 bug
    archive/              # 已关闭 bug；长期经验应提炼到 memory 或 docs/agents

  human/                  # 面向人的材料；Agent 不默认读取
    README.md             # human 文档索引和边界说明
    product/              # 产品意图、用户场景、成功标准
    learning-notes/       # 学习笔记和外部材料消化
    discussions/          # 设计讨论和未晋升结论
    reviews/              # 产品评审、Gold review、人工反馈
    guides/               # 面向人的解释性指南

  retrospectives/         # 复盘与历史证据；只证明当时发生过
```

说明：

- `docs/docfit-00-index.md` 不应长期保留为主入口。正式替换时优先用 `docs/README.md`
  接管索引职责；旧路径可以先保留为兼容跳转，待引用清理后删除。
- `docs/modules/*.md` 可以先保持文件形式，等内容稳定后再 folderize。最终建议使用模块目录，
  因为每个模块会有 context、eval、contract 指针和状态边界。
- `docs/runbooks/**` 和 `docs/agents/**` 目前不存在，应在迁移时新建；它们不是 `AGENTS.md`
  的替代品，而是承接长操作说明。

## 默认阅读链路

Agent 默认链路：

```text
AGENTS.md
  -> README.md
  -> STATUS.md
  -> ARCHITECTURE.md
  -> docs/modules/README.md
  -> 当前任务对应模块目录
```

Human 默认链路：

```text
README.md
  -> STATUS.md
  -> ARCHITECTURE.md
  -> docs/README.md
  -> docs/human/README.md
```

测试/Eval 链路：

```text
tests/README.md
  -> 当前模块 Eval README
  -> Gold/Contract
  -> Actual-vs-Gold evidence
```

禁止默认链路：

- Agent 不默认进入 `docs/human/**`。
- Agent 不默认进入所有 `docs/status/active/**`。
- Agent 不从 `docs/plans/**` 反推当前架构。
- Agent 不从 `temp/**`、`output/**` 或旧 proof 判断当前产品状态。

## 三模块文档组织

### 模板提取

目标入口：

- `docs/modules/template-extraction/README.md`
- `docs/contracts/template-extraction.md`
- `docs/runbooks/template-extraction-live-run.md`
- `evals/template-extraction/README.md`

负责：

- 学校模板和学校要求到 `final-template.docx`、`fill-contract.yaml`。
- Skill、Harness、Tool、Eval 的职责边界。
- 模板提取运行失败时的定位入口。

不负责：

- 学生论文内容提取。
- final word 填充和最终交付质量。
- 读取学生源 DOCX 或 Student Content Model 私有状态。

### 用户内容提取

目标入口：

- `docs/modules/student-content-extraction/README.md`
- `docs/contracts/student-content-model.md`
- `evals/student-content-extraction/README.md`

负责：

- 学生源论文到 Student Content Model。
- 内容顺序、层级、来源追踪和 Field Registry 绑定。
- Student Content Extraction Gold 和 Eval 路由。

不负责：

- 学校模板识别。
- 目标位置选择。
- 目标样式物化。

### final word 生成

目标入口：

- `docs/modules/final-word-generation/README.md`
- `docs/contracts/fill-contract.md`
- `docs/contracts/style-contract.md`
- `evals/e2e/README.md`

负责：

- 消费模板提取产物和 Student Content Model，生成最终 Word。
- placement、style materialization、final evidence/report。

不负责：

- 重新识别学校模板。
- 重新提取学生内容。
- 覆盖上游合同中的 source hash、registry hash 或 locator 绑定。

## 现有文件迁移清单

### 根目录

| 当前文件 | 目标处理 |
| --- | --- |
| `README.md` | 保留。只回答项目是什么、怎么跑、当前入口。 |
| `ARCHITECTURE.md` | 保留。承接全局架构，不展开函数细节。 |
| `STATUS.md` | 保留。作为恢复点，定期压缩 active status。 |
| `AGENTS.md` | 保持当前薄版本。不要塞长文档治理和模块细节。 |
| `CLAUDE.md` | 保留为 `@AGENTS.md` 转发。 |

### docs 根部文件

| 当前文件 | 目标处理 |
| --- | --- |
| `docs/README.md` | 保留并扩展为文档系统入口。 |
| `docs/docfit-00-index.md` | 替换为兼容跳转或删除。不要继续作为权威索引。 |
| `docs/docfit-01-architecture-core.md` | 拆分。长期架构进入 `ARCHITECTURE.md`，细节进入 `docs/architecture/core.md` 或模块文档。 |
| `docs/docfit-02-testing-and-iteration.md` | 降级或删除。测试入口以 `tests/README.md` 为准，操作步骤进入 `docs/runbooks/**`。 |
| `docs/docfit-03-gold-system-design.md` | 移入 `docs/contracts/gold-system.md`。 |
| `docs/docfit-local-observability-design.md` | 拆分为 `docs/runbooks/observability.md` 和必要架构补充。 |
| `docs/migration-asset-inventory.md` | 移入 `docs/retrospectives/**` 或 `docs/status/archive/**`。 |

### contracts 与 modules

| 当前文件 | 目标处理 |
| --- | --- |
| `docs/contracts/template-extraction.md` | 保留，作为模板提取稳定合同。 |
| `docs/modules/README.md` | 保留并改为纯三模块路由。 |
| `docs/modules/template-extraction.md` | 迁移到 `docs/modules/template-extraction/README.md`。 |
| `docs/modules/student-content-extraction.md` | 迁移到 `docs/modules/student-content-extraction/README.md`。 |
| `docs/modules/final-word-generation.md` | 迁移到 `docs/modules/final-word-generation/README.md`。 |

### plans

| 当前文件 | 目标处理 |
| --- | --- |
| `docs/plans/README.md` | 保留，增加 active/archive 规则。 |
| `docs/plans/docfit-field-style-property-closure.md` | 当前活跃。保留在 active 或拆为 plan + status。 |
| `docs/plans/docfit-content-field-registry/DESIGN.md` | 若已成为长期合同，提炼到 `docs/contracts/field-registry.md`。YAML 快照保留在稳定路径。 |
| `docs/plans/docfit-template-extraction-eval/DESIGN.md` | 提炼到 Eval README 或 `docs/contracts/template-extraction-eval.md`。 |
| `docs/plans/docfit-template-extraction-eval/PLAN.md` | 任务 ledger，完成后归档。 |
| `docs/plans/docfit-libreoffice-visual-evidence-v2.md` | 提炼到 observability runbook 或视觉证据合同；原计划归档。 |
| `docs/plans/docfit-template-extraction-skill-harness-redesign.md` | 已完成，归档。长期结论已进入 Contract、模块文档、架构或 Agent runbook。 |
| `docs/plans/docfit-template-extraction-skill-harness-redesign/**` | 已完成 proof，整体归档到 `docs/status/archive/**` 或 `docs/retrospectives/**`。 |

### status

| 当前文件 | 目标处理 |
| --- | --- |
| `docs/status/active/docfit-school-extract-v2.md` | 压缩成模板提取模块状态或并入 `STATUS.md`，详细 proof 归档。 |
| `docs/status/active/docfit-field-style-property-closure.md` | 当前活跃。保留直到 final word style closure 完成。 |
| `docs/status/active/docfit-stable-style-contract.md` | 提炼到 `docs/contracts/style-contract.md`。 |
| `docs/status/active/docfit-content-field-registry.md` | 提炼到 `docs/contracts/field-registry.md`。 |
| `docs/status/active/docfit-libreoffice-visual-evidence-v2.md` | 提炼到 observability runbook 或视觉证据合同。 |
| `docs/status/active/docfit-o0-local-observability.md` | 若仍需操作，进入 runbook；否则归档。 |
| `docs/status/active/docfit-main-agent-read-permissions.md` | 提炼到 `docs/agents/sdk-boundaries.md` 或安全合同。 |
| `docs/status/active/docfit-student-content-dependencies-and-blockers.md` | 压缩进 student-content 模块状态或 `STATUS.md`。 |
| `docs/status/active/docfit-student-content-extraction-eval.md` | 提炼到 `evals/student-content-extraction/README.md`。 |
| `docs/status/active/docfit-student-content-extraction-gold.md` | 提炼到 Gold contract。 |
| `docs/status/active/docfit-student-content-placement-debug.md` | 转为 bug 记录或归档。 |
| `docs/status/active/docfit-template-extraction-eval.md` | 提炼到 `evals/template-extraction/README.md`。 |
| `docs/status/active/docfit-template-extraction-skill-harness-redesign-modules.md` | redesign proof，归档。 |

### bugs

| 当前文件 | 目标处理 |
| --- | --- |
| `docs/bugs/docfit-apply-noop-recovery-feedback-loop.md` | 若仍打开，放 `docs/bugs/active/`；关闭后提炼经验并归档。 |
| `docs/bugs/docfit-template-paragraph-cleanup-descendant-verification.md` | 若仍打开，放 `docs/bugs/active/`；关闭后归档。 |

### human

| 当前文件 | 目标处理 |
| --- | --- |
| `docs/human/README.md` | 保留，按 product、learning-notes、discussions、reviews、guides 重新索引。 |
| `docs/human/AGENTS.zh-CN.md` | 归档或删除。当前 Agent 权威是根目录 `AGENTS.md`。 |
| `docs/human/agent-development-control-system-discussion.md` | 留在 `docs/human/discussions/`，确认结论提炼到 `docs/agents/**` 或 ADR。 |
| `docs/human/agent-development-failure-attribution-and-boundary-governance.md` | 提炼到 `docs/agents/failure-diagnosis.md`；原文归入 human discussions。 |
| `docs/human/agent-facing-style-evidence.md` | 提炼到 style contract、final word 模块或 Agent runbook。 |
| `docs/human/agent-layer-boundary-drift-and-directory-guards.md` | 提炼到 `docs/agents/failure-diagnosis.md` 和 `docs/README.md`；原文归档。 |
| `docs/human/agent-skill与代码tool的职责边界经验.md` | 提炼到 `docs/agents/sdk-boundaries.md` 或 memory。 |
| `docs/human/agent-visual-rendering-and-structural-location.md` | 提炼到 observability runbook 或视觉证据合同；原文留 human discussions。 |
| `docs/human/architecture-document-boundaries-and-development-governance.md` | 提炼到 `docs/README.md`；原文归入 human discussions。 |
| `docs/human/content-id-and-template-workflow-examples.md` | 若是长期例子，移到 `docs/contracts/**` 示例或 `knowledge/**`。 |
| `docs/human/docfit-agent-sdk模块配置与共享事实层学习笔记.md` | 提炼到 `docs/agents/sdk-boundaries.md`；原文留 learning-notes。 |
| `docs/human/docfit-general-style-preset-v1-product-review.md` | 留在 `docs/human/reviews/`；确认结论提炼到 style contract。 |
| `docs/human/docfit-local-observer-user-guide.md` | 移到 `docs/runbooks/observability.md` 或 `docs/human/guides/`，按读者决定。 |
| `docs/human/docfit-module-documentation-guidance.md` | 被本草案和 `docs/README.md` 替代后归档。 |
| `docs/human/eval-data-system-and-pipeline-discussion.md` | 留在 discussions；已确认 Gold 结论提炼到 Gold contract。 |
| `docs/human/kimi-claude-agent-sdk-controlled-test.md` | 作为实验证据归档。 |
| `docs/human/non-technical-development-guide.md` | 保留在 `docs/human/guides/`。 |
| `docs/human/thesis-content-tree-reading-guide.md` | 若是操作指南，移到 runbook；若是解释材料，放 human guides。 |
| `docs/human/thesis-conversion-example-optimization-log.md` | 归入 retrospectives 或 human reviews。 |
| `docs/human/学校论文模板整理中的六类通用问题.md` | 提炼到 `knowledge/**` 或模板提取 Reference。 |
| `docs/human/assets/**` | 跟随引用它们的 human 文档迁移。 |

### memory

| 当前文件 | 目标处理 |
| --- | --- |
| `memory/README.md` | 保留。 |
| `memory/2026-08-18-agent-md-context-hygiene.md` | 保留。若内容膨胀，压缩成一条经验并链接本草案或 HumanLayer 来源。 |

## 替换顺序

1. 冻结正式文档入口，不再在 `docs/docfit-00-index.md` 上追加未来结构。
2. 在 `temp/` 确认本草案，包括目标目录、文件去向和保留/删除策略。
3. 新建正式目录骨架：`docs/runbooks/**`、`docs/agents/**`、必要的 `docs/contracts/**`。
4. 先迁移入口层：`docs/README.md`、`docs/modules/README.md`、`README.md` 的文档入口。
5. 再迁移三模块：模板提取、用户内容提取、final word 生成各自形成独立模块目录。
6. 再迁移合同：Gold、Field Registry、Fill Contract、Style Contract 等稳定交接材料进入 `docs/contracts/**`。
7. 再迁移长操作说明和 Agent 经验：分别进入 `docs/runbooks/**` 和 `docs/agents/**`。
8. 压缩 `docs/status/active/**`，只保留真正活跃项；完成项进入 archive 或 retrospectives。
9. 整理 `docs/human/**`，按 product、learning-notes、discussions、reviews、guides 重建索引。
10. 清理旧路径引用，用 `rg` 验证没有文档仍把旧索引当权威。
11. 更新 `tests/contract/test_documentation_contract.py`，把新的入口和禁止回归规则写进测试。
12. 每个阶段单独 commit，避免一次提交混入代码、DOCX、临时产物或无关会话改动。

## 验收标准

- `AGENTS.md` 保持薄，不超过当前职责范围。
- 根 `README.md` 仍只回答项目是什么、怎么跑、当前主要入口。
- `ARCHITECTURE.md` 只写系统结构，不写函数细节或执行计划。
- `STATUS.md` 能让下一个 AI 直接知道项目当前在哪里。
- `docs/README.md` 明确文档面、生命周期和入口。
- `docs/modules/README.md` 能按三个模块路由上下文。
- `docs/human/**` 不在 Agent 默认阅读链路里。
- `docs/plans/**`、`docs/status/active/**`、`docs/bugs/**` 不再被默认当作当前真相。
- `docs/docfit-00-index.md` 不再作为长期权威入口；保留时也只做兼容跳转。
- 所有长期文档默认中文。
- 运行 `uv run pytest -q tests/contract/test_documentation_contract.py` 通过。
- 运行 `rg` 检查旧权威路径、旧工具数量约束、旧启动链路，不应出现误导性引用。

## 风险与处理

| 风险 | 处理 |
| --- | --- |
| 一次性大搬迁导致链接断裂 | 分阶段迁移，每阶段跑 `rg` 和文档合同测试。 |
| 旧 human 讨论里的有效结论被丢掉 | 先提炼结论，再移动或归档原文。 |
| active status 被过度删除，丢失恢复点 | 先把当前项目恢复信息压缩进 `STATUS.md`。 |
| Agent runbook 又变成第二个 AGENTS.md | `AGENTS.md` 只放启动规则；`docs/agents/**` 只在具体任务需要时读。 |
| 合同和模块文档重复 | Contract 写交接和失败语义；module doc 写职责边界和上下文路由。 |
| temp 草案被误读为当前真相 | 本文开头明确状态，正式替换前不从入口文档链接本文。 |

## 待确认问题

1. 是否删除 `docs/docfit-00-index.md`，还是保留一个短兼容跳转文件一段时间。
2. `docs/human/product-brief.md` 是否需要新建；如果新建，是否允许 Agent 在产品方向任务中按需读取。
3. `docs/modules/*.md` 是否立即 folderize，还是先保留文件形式，等内容稳定后迁移。
4. `docs/status/archive/**` 和 `docs/retrospectives/**` 是否都需要，还是只保留一个归档面。
5. `knowledge/**` 是否作为模板提取/论文领域 Reference 的正式位置，或并入 `docs/agents/**`。
6. Field Registry 的 YAML 快照最终放在 `docs/contracts/**`、`knowledge/**` 还是继续留在 `docs/plans/**`。

## 下一步建议

先只评审本草案，不替换正式文档。确认后第一批正式改动建议是：

1. 新建 `docs/agents/README.md` 和 `docs/runbooks/README.md`。
2. 将 `docs/docfit-00-index.md` 改成兼容跳转，实际入口改为 `docs/README.md`。
3. 将三份 `docs/modules/*.md` 迁移为三个模块目录。
4. 更新文档合同测试，禁止 `docs/docfit-00-index.md` 再被描述为上位契约或当前权威。
