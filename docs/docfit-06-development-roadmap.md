# DocFit 开发路线与阶段验收（06）

> 状态：开发执行基线
> 日期：2026-08-07
> 核心目标：先让第一条论文转换链路真实跑通，再用稳定契约、测试样本和清晰边界支持持续迭代。

当前执行证据：五个真实 Tool、固定适配、开发者 CLI、`docfit convert` 薄壳、合成
集成测试和可选 `docfit eval --suite core` 已实现。2026-08-07 已按 clean break 把视觉
证据替换为 V2：Docker LibreOffice 是唯一视觉来源，OfficeCLI 只负责结构、编辑、验证
和语义对象定位，Poppler 负责 PDF 索引与按需栅格化。旧视觉 intent、路径式 render ref、
OfficeCLI screenshot、远程转换路径和兼容层均不再属于产品。核心链路不依赖本地 Word、
AppleScript、GUI 会话或用户电脑。最新确定性与 live 结果只写入 active capsule。

M1、M2 的完成门现在以当前 V2 render、原生图片、全页视觉覆盖、独立验证与源 hash
不变为准。其后另行批准的 Registry、三份 Student Extraction Gold 和独立提取 Eval 已
完成；Placement/Filling、完整 M3、授权/脱敏真实样本资格验证和外部人工复核仍未完成，
不因该有界切片或三校 V2 链路 smoke 通过而自动完成。

用户随后批准把 M2 后 O0 细化为 DocFit 本地运行观测与问题定位界面；目标设计见
`docfit-local-observability-design.md`。它仍属于薄应用壳的只读能力，不恢复 M3，
不建立第二 Agent loop，也不属于面向最终转换用户的 GUI 产品化。当前已完成 O0.0–O0.7
的平台骨架、SDK runtime privacy/report v2、入队前安全 projector 与直接关联/覆盖/指标
投影，以及有界 SQLite 历史、保留/删除与非阻断降级、免登录 loopback 安全壳、自动短期会话与会话内
证据重新挂载、核心监控页面与跨运行比较；O0 总门已通过，O1 尚未开始。

随后批准的主 Agent 渐进式披露权限切片先增加路径受限 Read/Glob/Grep；2026-08-04 的
后续信任决策又把 Bash/Write 全部打开：两者对主 Agent 可见、自动批准且没有 DocFit
路径 gate，可访问 Agent 进程本来可访问的文件与环境。五个 DocFit Tool 继续承担
证据绑定、可验证的权威文档操作，`docfit-unit-analyst` 仍只拥有 inspect +
visual-review。当前合同、权限测试、`path-tools` live smoke 和两个 Skill references 结构
在第 6.7 节锁定。

## 1. 路线原则

开发阶段与产品运行时是两件事。本文的 M0–M5 只表示工程交付顺序，不进入 DocFit 在线运行逻辑，也不形成新的工作流状态机。

所有阶段遵守以下优先级：

1. **先有真实可运行结果**：每个阶段都必须增加一个可执行命令、可检查产物或可重复测试，不能只增加目录和抽象。
2. **先跑一条窄链路**：第一版只支持一个入口、一组当前任务学校材料、唯一产品
   Knowledge Package、OfficeCLI、固定 Docker LibreOffice，以及少量合成/授权测试样本。
3. **先复用再重写**：现有 `convert-thesis`、学校提取 Skill、DOCX 检查与渲染脚本先做迁移评估，能满足新契约的能力优先复用。
4. **接口由当前消费者驱动**：五个 DocFit Tool 契约、通用 Knowledge Package 和
   Eval case 是稳定边界；当前任务学校事实不升级为长期数据模型。
5. **失败必须可见**：源文件覆盖、内容静默丢失、无法验证的 renderer 结果和偏离已批准
   权限矩阵的 SDK 配置都属于停止项。
6. **每个缺陷都留下回归资产**：Tool 缺陷进入单元或契约测试，Skill 缺陷进入 Skill eval，交付缺陷进入端到端 Eval。

### 1.1 Gate 依赖与阶段推进

02 第 1.1 节定义的 G0–G5 是每个工作包的证据链；本文件的 M0–M5 是产品/工程里程碑。
二者正交，不能机械地把 `Gx` 解释成 `Mx`。里程碑可以由多个工作包组成，每个工作包
必须报告自己的 Gate；一个里程碑只有在其必需工作包的证据闭包全部 PASS 后才能通过。

典型依赖关系如下；“主要消费”表示该阶段最关注的证据，不表示可以跳过更早 Gate：

| 路线范围 | 主要消费的 Gate 证据 | 推进约束 |
|---|---|---|
| 新产品/架构切片 | G0 → G1 | 先批准边界、所有权、公开面和失败语义，再冻结能力合同 |
| M0 或基础设施切片 | G0–G3；涉及 Agent 权限/SDK 行为时还需 G4 | 真实 smoke 不能替代权限、组件或应用壳合同 |
| M1 Tool 能力 | G0–G2 | 五个 Tool 在无 Agent 条件下通过 unit/contract/integration 和 visual-renderer 门后，才可供 Agent 消费 |
| M2 最小转换链 | G3–G4，且依赖已通过的 M1 G2 | 先证明最窄入口和产物闭环，再证明 Agent 编排；不得用 Agent 成功倒推 Tool 正确 |
| M2 后候选/优化切片 | 按变更从受影响的最早 Gate 重新进入 | 观测或性能证据不降低安全、失败、产物与独立验证合同 |
| M3 质量资格 | G5，且绑定通过 G3/G4 产生的精确 artifact | Eval、授权样本和 Human review 按批准范围独立执行；机械有效不等于质量合格 |
| M4/M5 扩展 | 每个新能力重新走受影响的 G0–G5 子链 | 既有里程碑 PASS 不能自动覆盖新学校、新 renderer、新公开面或新质量声明 |

后续 Gate 只能引用前一 Gate Report 中批准、版本/hash/commit 可定位且仍有效的证据。
若实现或测试暴露早期合同缺口，停止当前 Gate，回到受影响 Gate 修订并对下游证据做
失效分析。候选计划不得覆盖已批准合同；需要改变产品边界、公开 Tool/CLI、架构或
里程碑范围时，先形成决策与影响，再由用户明确批准。

跨上述产品、公开合同、架构或里程碑 Gate 必须等待用户批准。已经批准的模块设计若已
明确实现范围、验收和停止门，则其中保持合同不变的实现与证据收集可自主推进；遇到
停止门、范围扩张或早期合同错误时必须停下。每个 Gate 的当前状态、baseline commit、
通过证据、blocker 与 `advance_requires` 只写入 `docs/status/active/**`，完整报告格式以
02 第 1.1 节为准。

## 2. 第一版技术基线

为缩短启动路径，首个垂直切片采用以下默认选择：

| 项目 | 第一版选择 | 重新评估条件 |
|---|---|---|
| 语言 | Python 3.12；`.python-version` 固定 3.12，`pyproject.toml` 声明 `>=3.12,<3.13` | 固定后端只能通过不可替代的 TypeScript 库安全使用 |
| 依赖与命令 | `uv`；提交 `uv.lock`，本地与 CI 均按锁文件安装 | 团队现有交付环境无法运行 `uv` |
| Agent runtime | Claude Agent SDK for Python | 产品部署目标改为托管 Managed Agents，且需求已经确认 |
| 用户入口 | 本地 CLI | CLI 已跑通，且真实用户需要 API 或 GUI |
| Skill 装载 | Provider-independent P1 已在仓库内实现 `docfit-school-extract` 与 `convert-thesis` 两个领域 Skill | 需要跨项目安装或发布时再封装 Plugin |
| 测试 | `pytest` | 无 |
| 静态检查 | `ruff` + `mypy` | 无 |
| SDK 内置工具 | 主 Agent 暴露 `Skill`、路径受限的 `Read/Glob/Grep`、无 DocFit 路径 gate 且自动批准的 `Bash/Write`、`AskUserQuestion` 与 `Agent`；`Agent` 按 `subagent_type` 精确白名单；Subagent 无 Bash/Write | 改变直接读取根、关闭/收紧 Bash/Write 或增加 Subagent 权限时重新审批 |
| Tool 接入 | SDK in-process MCP server 只注册五个高层 Tool；公开 schema 使用扁平兼容子集，结构化结果镜像为 Agent 可见 JSON text，视觉审查返回图片 content block；SDK buffer 为 16 MiB | 出现必须独立部署或跨进程复用的真实消费者 |
| 文档执行与渲染 | OfficeCLI 1.0.143 负责 inspect/edit/validate/对象定位；固定 Docker LibreOffice 25.2.3.2 负责唯一 DOCX→PDF；Poppler 按需派生图片 | 真实样本证明职责不可行，或批准更换唯一 renderer |
| 视觉环境 | 锁定基础镜像 digest、LibreOffice、locale、字体清单/digest 和 PDF 参数；运行时禁网、只读 root、只读 DOCX mount | 基础镜像或字体安全更新需要升级 render identity |
| 数据 | 合成 fixture 优先；真实样本必须脱敏或授权 | 无 |

仓库骨架和 M0 实现按长期资产归属落盘。以下代码块描述 M0 验收时的边界；
第 4.6 节批准的后续独立切片在同一归属下增加 Knowledge v1 静态实现：

```text
.python-version
pyproject.toml
uv.lock
src/docfit/
├── __main__.py             # python -m docfit 入口
├── app/                    # CLI、SDK 配置、doctor、环境与 live smoke
├── tools/                  # 五个 Tool 注册与 M0 图片传输 smoke
└── knowledge/              # 通用产品 Knowledge 的模型、加载器和内置只读数据
    └── package/v1/         # 随 wheel/sdist 发布，不含学校专属内容
.claude/skills/
└── convert-thesis/          # 当前 M0 discovery marker
tests/
├── unit/
├── contract/
└── integration/
evals/
├── fixtures/
├── skills/
└── e2e/
knowledge/README.md         # 人类入口；不保存学校包
```

M0 的应用代码只归属 `src/docfit/app/`，Tool 注册和合成图片能力只归属
`src/docfit/tools/`；包根只保留版本与模块入口，不保留第二组兼容导入面。
M0 结束时尚无真实 DOCX 行为或 Knowledge 加载；第 4.6 节独立切片补充唯一产品
Knowledge Package 的静态加载与完整性校验。真实 DOCX 行为和两个固定 adapter 的薄
适配仍由后续里程碑按验收证据加入。

学校模板、要求、示例和推导规则不进入仓库长期 Knowledge；它们只能作为当前
任务输入或授权 Eval fixture。P1 已实现 `docfit-school-extract` 与
`convert-thesis` 两个领域 Skill；模板提取只产生当前任务证据，不创建学校资产生产
入口。OfficeCLI 与 LibreOffice 职责不同，只在五个 Tool 内做薄适配，不抽取共享
Provider 接口；视觉路径没有动态选择或故障转移。

测试目录的职责固定为：

- `tests/unit/`：不依赖 SDK 或真实外部进程的纯逻辑测试；
- `tests/contract/`：五个公开 Tool、V2 ref、SDK Subagent 权限/上下文边界和原生图片契约；
- `tests/integration/`：真实 OfficeCLI、Docker LibreOffice、三校视觉链路、CLI 与薄转换壳；
  真实 SDK 由仓库外凭据驱动的独立 live 产品门验证。

## 3. 首条链路

第一条可运行产品链路固定为：

```text
CLI
 └─ Claude Agent SDK（最小权限）
     ├─ docfit-school-extract / convert-thesis Skill
     ├─ 可选 docfit-unit-analyst（SDK 原生、隔离、只读）
     └─ 主 Agent
         ├─ docx_inspect
         ├─ docx_render
         ├─ docx_visual_review
         ├─ docx_edit
         └─ docx_validate
             └─ final.docx + preview + visual-review + validation
```

首版只要求：

- 一份随产品发布的通用 Knowledge Package；
- 一组带来源 hash 的合成当前任务学校材料；
- 一份不含真实学生隐私的合成论文；
- OfficeCLI 与固定 Docker LibreOffice 两个通过各自职责契约测试的 adapter；
- 一条可重复运行的 CLI 命令；
- 一组能证明源文件不变、产物可打开、关键内容保留的自动断言；
- 一条能把页面图片真实送入当前 Agent、形成可追溯 visual findings 的审查链路。
- 两个领域 Skill 可以直接分析或按当前任务需要调用同一个通用只读 Subagent；不存在
  的单元不被强制创建，Subagent 不拥有写入、渲染或验证能力。

首版不要求：

- 自动建设新学校；
- 第三个执行引擎、动态后端选择或故障转移；
- API、GUI、多用户或任务队列；
- 完整学校目录和检索服务；
- 像素级分页自动判定；
- 通用工作流、状态机、checkpoint 或 replay。

## 4. M0：开发底座可执行

### 4.1 目标

从只有文档的仓库变成可安装、可测试、能连接 Claude Agent SDK 的最小 Python 项目。

### 4.2 范围

- 建立 `pyproject.toml`、`src/docfit/` 和测试目录；
- 使用 `.python-version` 固定 Python 3.12，在 `pyproject.toml` 声明支持范围并提交 `uv.lock`；
- 提供 `docfit` CLI 和 `doctor` 命令；
- 接入 Claude Agent SDK，完成一次不处理真实文档的 Agent smoke run；
- 用一个带明显文字和版式标记的合成页面图片验证 Tool image content block 能进入当前 Agent 上下文；
- 验证 Agent 能通过 `AskUserQuestion` 获取 CLI 输入并继续同一 SDK 会话；
- 验证 Agent 尝试调用 `Bash`、`Write`、`Edit`、`WebSearch`、`WebFetch` 或未注册 MCP Tool 时被拒绝；
- 明确 Skill 发现路径、五个 Tool 的逻辑名称和 `mcp__docfit__...` 实际名称；
- 固定 SDK 工具权限、工作目录、网络和日志基线，并区分工具可见性与自动批准；
- 盘点现有 Skill 与脚本，形成“直接迁移、适配复用、淘汰”清单；每项记录来源、版本或 hash、许可证、迁移结论、目标位置和能力缺口；
- 建立最小 CI：安装、静态检查、类型检查、单元测试。

### 4.3 SDK 权限基线

以下代码块记录 M0 当时的验收基线；当前运行合同已由第 4.7 节增加受限 Agent，并由
第 6.7 节增加路径受限 Read/Glob/Grep 及受信任 Bash/Write。M0 的 Bash/Write 拒绝是
历史事实，不是当前权限面；五个 DocFit Tool 的直接调用与未匹配工具默认拒绝仍保留。

```text
内置工具可见集合：Skill、AskUserQuestion
MCP server：只注册五个 DocFit Tool
实际 MCP 名称：
  mcp__docfit__docx_inspect
  mcp__docfit__docx_edit
  mcp__docfit__docx_render
  mcp__docfit__docx_visual_review
  mcp__docfit__docx_validate
自动批准：五个 DocFit Tool
用户交互：AskUserQuestion 通过 can_use_tool 回调转发给 CLI
默认策略：其他未匹配工具一律拒绝
```

Tool 返回 `needs_input` 后，由 Agent 根据现有证据决定重新 inspect 或调用 `AskUserQuestion`。应用壳不自行解释 `needs_input`，也不建设第二套问答协议。权限测试必须同时验证可见工具集合、自动批准集合和默认拒绝行为；只配置 `allowed_tools` 不能代替工具可见性限制。

### 4.4 验收标准

本节记录 M0 当时的历史验收门；当时主 Agent 尚未接入 Subagent 与路径受限文件工具。
当前累计的五项 live 产品门由第 4.7 节和第 6.7 节定义，不能把后续 case 混入本节后
仍把这里解释为当前完整权限面。

必需的确定性门：

```bash
uv sync --frozen
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
```

`doctor` 使用按能力收紧的退出语义：

```text
docfit doctor
  检查基础安装、Python、SDK、目录权限和配置结构。
  统一 Agent 环境文件、API key 或可选运行能力缺失可以报告为 NOT_READY，
  但不影响 CI 退出码。

docfit doctor --require agent-smoke
  缺少权限为 0600 的统一 Agent 环境文件、可用 API key、图片 Tool
  或 SDK live 能力时返回非零。

docfit doctor --require visual-renderer
  OfficeCLI、锁定 LibreOffice 镜像 identity 或必需的 Poppler 工具缺失时返回非零。
```

验收事实（以下均为 M0 当时的历史验收事实；当前权限面以第 6.7 节为准）：

- 全新 checkout 可以仅按 README 在本地完成安装；
- `.python-version`、`pyproject.toml` 和 `uv.lock` 对 Python 与依赖版本的声明一致；
- `docfit --help` 和 `docfit doctor` 正常运行；
- `doctor` 能明确报告 Python、SDK、API key、OfficeCLI、LibreOffice renderer identity、
  PDF 页面派生和工作目录状态，并按 `--require` 选择正确退出码；
- SDK 的内置工具可见集合只有 `Skill` 和 `AskUserQuestion`，in-process MCP server 只注册五个 `mcp__docfit__...` Tool；
- 五个 DocFit Tool 自动批准，`AskUserQuestion` 进入 CLI 的 `can_use_tool` 回调，其他未匹配工具默认拒绝；
- Agent 尝试调用 `Bash`、`Write`、`Edit`、`WebSearch`、`WebFetch` 或未注册 MCP Tool 时被拒绝，且不能借此访问任务目录之外的文件或网络；
- 输入目录只读，工作目录和输出目录可写，日志默认不包含论文正文；
- 迁移清单覆盖现有 `convert-thesis`、学校提取 Skill 及 DOCX 检查、内容检查、占位符检查、渲染与分页脚本，并记录来源、版本/hash、许可证、迁移结论、目标位置和能力缺口；
- CI 不需要真实学生文件或 API key。

必需的本地产品门：

```bash
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit doctor --require agent-smoke
```

这些命令必须使用真实 Claude Agent SDK 和开发者提供的 API key 完成受限会话，并证明：

- 受控 Tool 返回的合成页面图片实际进入当前 Agent 上下文，Agent 能正确报告其中的测试标记；
- Agent 通过 `AskUserQuestion` 获取 CLI 输入后继续同一会话；
- Agent 请求被禁止或未注册的工具时，调用被拒绝且会话不获得对应能力。

没有 API key 时可以完成 M0 代码工作，但不能宣称本地产品门通过。M0 的本地
Agent 配置统一放在仓库外 `~/.config/docfit/agent.env`，文件权限必须为 `0600`；
当前 runtime 按 MiniMax、Kimi 的顺序选择 Anthropic 兼容 backend，默认使用支持原生
image/video 内容块的 `MiniMax-M3`，Kimi 仅作回退，并通过
`ClaudeAgentOptions.env` 只向 SDK 子进程注入当前候选配置。Kimi 配置显式保持官方
high-effort Tool 上下文并关闭 Tool Search；HTTP 400 请求格式拒绝被视为同一
name/base URL/model route 的不可重放失败，不再轮换 credential 重复请求，而是转到下一个
不同 route。OfficeCLI、固定 LibreOffice 镜像或 Poppler 的缺失与版本问题属于 M1
视觉接入证据，不阻塞 M0。

### 4.5 停止门

- 无法证明 SDK 的可见工具集合受限；
- `AskUserQuestion` 无法通过 CLI 回调继续同一会话；
- 未匹配工具可以绕过默认拒绝策略；
- Agent 可以访问任务目录之外的敏感文件；
- 产品必须依赖未经许可的 Claude 登录方式；
- 技术栈变更会导致现有 Python 资产全部重写。

### 4.6 M0 后独立切片：通用 Knowledge Package v1

M0 已验收后，可以按单独批准的 Preflight、在不进入 M1 DOCX Tool 实现的前提下，
落地不依赖 Provider 的产品通用 Knowledge 静态边界。该切片提供随 wheel/sdist
发布的唯一内置包，固定 `manifest.yaml`、非空 `knowledge.md`、通用 Markdown
documents、document hash、canonical digest、不可变读取模型和合成单元测试。

加载器拒绝学校 ID、适用学年、模板、DOCX/PDF、`school.md`、structure/format
profile、隐藏文件和不安全路径。包只包含统一概念、识别方法、解释原则和通用
处理模式；当前任务学校材料的 Tool 映射与运行时组合仍分别属于 M1/M2。

独立切片的验收门为 `uv sync --frozen`、`uv lock --check`、`uv build`、全仓库
ruff、mypy、pytest 和基础 `docfit doctor`。它不得新增 Agent 可见 Tool、CLI、
Provider 抽象、学校资产/检索/自动晋升、发布状态机或真实学校/学生资料，也不改变 M0 已通过的
权限与 live smoke 结论。

### 4.7 M0 后独立切片：两个领域 Skill、模块化 Knowledge 与原生只读 Subagent（已完成）

架构决策由 `docs/plans/docfit-progressive-subagents.md` 锁定，执行契约与证据由
`docs/plans/docfit-development-plan.md` 记录。当前 P1 已完成运行时代码接线；这不表示
五个 Tool 已具备真实 DOCX 行为，也不进入 M1。

该 Provider-independent 实现切片已按单独批准的边界完成：

- 从 M0 marker 重写 `convert-thesis`，新增从零设计的 `docfit-school-extract`；
- 复用现有 Knowledge document ID/hash 形成开放、可组合的最小逻辑模块投影，不创建
  新 schema、学校包或单元专家目录；
- 在薄应用壳中内联配置一个 `docfit-unit-analyst`，固定为 inspect + visual-review
  只读权限；
- 让 `Agent` 对主 Agent 可见但不裸批准；SDK live 证据证明 `can_use_tool` 不是
  `Agent` 的可靠必经路径，因此改由 SDK 原生 `PreToolUse` 权限钩子只批准该
  `subagent_type`，拒绝 `general-purpose` 和未知类型；
- 由领域 Skill 指导主 Agent 把选中 Knowledge 模块和当前任务证据写入 `Agent`
  prompt；不虚构单次调用可动态覆盖 `AgentDefinition.skills`；
- 增加权限、上下文隔离、结构化返回、Knowledge 选择和 P1 原有四项 live smoke 证据；
  第 6.7 节后续增加独立 `path-tools` 第五项。

该切片不实现真实 DOCX Tool，不改变五个公开 Tool 名称，也不进入 M1。测试不得固定
委派次数、单元枚举、并行度或调用顺序；必须分别证明复杂场景能够委派、简单场景允许
不委派，以及 P1 当时的 Subagent 无写权限和未匹配工具默认拒绝成立。主 Agent 的后续
Bash/Write 信任权限以本节 6.7 为准。

P1 的确定性与本地产品门为：

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit agent-smoke --case path-tools
uv run docfit agent-smoke --case subagent
uv run docfit doctor --require agent-smoke
```

`subagent` live smoke 必须观察到主 Agent 加载领域 Skill、唯一具名 Subagent 通过
`PreToolUse` 类型白名单、Subagent 只调用 inspect + visual-review、图片真实进入其
隔离上下文，并返回完整 `unit_analysis_v1`。`general-purpose`、未知类型和写入 Tool
由同一权限钩子与契约测试拒绝。当前五项 live 回执只记录 SDK 版本、backend、工具名和
通过摘要，不保存 Knowledge 内容、任务证据或文档正文。凭据和配置已确认存在可运行
backend 后，每次新 live 尝试开始前必须使该 case 的旧 PASS 回执失效，只有本次 PASS
才发布新回执；失败、超时或中断后 `doctor --require agent-smoke` 必须保持
`NOT_READY`。尚未启动任何 backend 就返回的 `NOT_READY` 不删除先前 live 证据，测试
必须使用临时项目根，不能污染真实回执。

## 5. M1：五个 DocFit Tool 跑通

### 5.1 目标

在没有 Agent 的条件下证明五个公开 Tool 能独立完成结构观察、受控编辑、固定
LibreOffice 视觉取证、原生图片返回和独立验证。

### 5.2 范围

- `docx_inspect`、`docx_edit`、`docx_render`、`docx_visual_review`、`docx_validate`；
- OfficeCLI 1.0.143 只负责结构、对象定位、编辑和验证；
- Docker LibreOffice 25.2.3.2 是唯一视觉 renderer；
- Poppler 建立页数/文字 bbox 并按需栅格化，Pillow 组合视图；
- 统一任务内 V2 Evidence Store，opaque `render:v2:` / `visual:v2:` ref；
- 普通 Agent 与 `prepare-template` 共用同一五 Tool 与视觉服务；
- `prepare-template` 用一次完整任务启动主 Agent，不创建语义 work item、crop 状态、区域推进或
  第二套 session loop；主 Agent 自行选择上下文、重试、视觉批次和可选只读委派；
- 模板机械能力收敛为 `docx_edit` 原子 action；Registry/object/hash/Word 边界由 Tool 校验，学校
  语义与目录/正文/集合选择由 Agent 决定；
- 最终精确版本必须取得全部原生全页 PNG 的逐页结论并通过 `docx_validate`，图片返回不等于已
  审查；修改会失效旧 hash 的页面证据；
- 不保留旧八 Tool、五个 work-item Tool、Template Workspace、候选 Skill 副本或
  YAML/compiler/attempt 兼容路线，也不建立替代 Claude Agent SDK 的通用 workflow runtime。

### 5.3 视觉验证矩阵

| 能力 | 必须证明 |
| --- | --- |
| render identity | DOCX hash、LibreOffice、image digest、font digest、locale、PDF 参数共同决定 ref |
| 安全执行 | 禁网、只读 root、cap drop、no-new-privileges、只读输入、独立 HOME/profile、timeout cleanup |
| PDF 事实 | 页数和页面尺寸来自 LibreOffice PDF，不来自 OfficeCLI HTML |
| 按需视图 | render 不批量生成高清页；contact sheet/pages/regions/compare 各自缓存 |
| object mapping | OfficeCLI 语义锚点在 PDF 中重新定位；歧义/失败返回候选完整页 |
| transport | MCP 结果含完整 JSON text 与原生 image blocks |
| clean break | 无旧 intent、路径式 ref、OfficeCLI screenshot、第二 renderer 或兼容层 |

### 5.4 验收标准

- 五个 Tool 的 unit、contract 和 integration 测试通过；
- `docfit doctor --require visual-renderer` 验证 OfficeCLI、镜像 identity、字体与 Poppler；
- CI 构建锁定镜像并执行真实 DOCX→PDF smoke；
- 相同 DOCX/环境 cache hit，任一 identity 输入变化生成新 ref；
- LibreOffice 失败、PDF 不完整或 DOCX 中途变化时不发布半成品；
- contact sheet、完整页、object/text/image_bbox region 和 compare 均有确定性测试；
- 三个学校样本都完成“联系表 → 页面 → object_ref 局部图”；
- 通用源码无学校名称、学校路径或学校条件分支；
- `ruff`、`mypy`、全量 `pytest` 通过。

### 5.5 停止门

以下任一情况不允许宣称 M1 视觉切片完成：

- 运行时代码仍可选择旧视觉路径或接受旧 render ref；
- OfficeCLI 页面/HTML 坐标被当成 LibreOffice 视觉坐标；
- 映射歧义时自动选择并生成伪精确裁图；
- renderer identity 或文件 hash 未进入证据；
- Agent 只能收到路径/文本，收不到原生图片；
- 任一三校样本只能通过学校专用规则或路径判断。

## 6. M2：第一条 Agent 端到端链路

### 6.1 目标

通过一条 `docfit convert` 命令证明 Claude Agent SDK 能组合五个 Tool 和两个领域
Skill，生成最终 DOCX、当前 V2 LibreOffice PDF、全页 visual review、独立 validation 与
隐私安全的完成报告。

### 6.2 范围

- 薄应用壳准备只读输入、任务根、Skill/Knowledge 和 SDK 会话；
- 主 Agent 决定 inspect/edit/render/review/validate 顺序与重试；
- 应用会话注入视觉 Tool 的 `task_root`；
- `docx_render` 默认联系表，Agent 分批请求异常页与局部证据；
- 完成声明绑定最终 DOCX hash、V2 render、renderer identity、全部页面覆盖和无 blocking finding；
- 应用最后独立重跑 validate，不信任中间 Agent summary；
- 只读 Subagent 仍只有 inspect + visual-review，不拥有 render、write 或 publish。

### 6.3 公共产品命令

```bash
uv run docfit convert \
  --input student.docx \
  --school-template school-template.docx \
  --school-requirements school-requirements.pdf \
  --output output-dir
```

成功输出至少包含 `final.docx`、当前 `document.pdf`、`visual-review.json`、
`validation.json` 和 `conversion-report.json`。报告只使用当前 V2 证据与独立验证，
不重放中间 warning 或旧 summary。

### 6.4 验收标准

- 真实 SDK 会话实际调用五个 Tool 并加载两个 Skill；
- 源 DOCX 与模板 hash 保持不变，最终 DOCX 可重新打开；
- 最终 report 的 candidate render ref 可在任务内 Evidence Store 完整解析；
- manifest 的 document hash 等于最终 DOCX，fidelity 为 `approximate`，renderer 为 LibreOffice；
- reviewed pages 精确覆盖 `1..page_count`，findings 引用有效 V2 evidence ref；
- blocking finding、旧 render、缺页、renderer mismatch 或验证错误都阻止 COMPLETED；
- 完成报告携带当前 PDF，不依赖路径式旧 render-ref JSON；
- Agent 图片 smoke 与 Subagent 图片 smoke 均通过；
- 观察器使用 `render_executions`、renderer/version 和
  `libreoffice_full_page_validation_v2`，不生成视觉调用副作用。

### 6.5 停止门

- 任何完成路径可在没有当前 V2 render 或全页覆盖时通过；
- 应用壳复制 Agent 的语义规划或建立第二 Agent loop；
- 视觉 Tool 通过 programmatic tool calling 返回图片；
- 旧快照、旧对象引用或旧 visual evidence 被当成最终文档事实；
- Docker/Poppler/OfficeCLI 不可用时静默换后端；
- 源文件被修改，或失败后发布不完整 DOCX/PDF。

### 6.6 M2 后独立切片：本地观测与核心转换优化（O0.0–O0.7 已完成）

这是一条位于 M2 完成之后的工程优化轨道，不重开 M2，也不恢复或替代 M3。当前只
批准本地观测界面的目标设计、数据边界与优化顺序，并已按独立可执行计划完成 O0.0–O0.7
的平台骨架、runtime privacy/report v2、安全 projector、直接 ID 关联/覆盖/指标投影，
以及有界 queue、后台 SQLite writer、保留/删除和非阻断降级、Web 安全壳、证据重新挂载
和 Agent loop 核心页面、跨运行比较与 O0 总门。O1 调用降重尚未开始。
M2 完成提交作为不可变比较基线，具体提交与历史运行
数字记录在 active capsule，不写成长期行为合同。

开始条件全部必需：

1. 冻结并记录已经通过全量确定性门、doctor 与真实合成产品门的 M2 基线；
2. 先按 `docfit-local-observability-design.md` 锁定并实现来源矩阵、直接 ID/hash/ref 关联
   证明、字段留存矩阵、SDK 原生 transcript 生命周期、历史目录显式重新挂载、本地 Web
   安全、report v1/v2 迁移、资源预算和 `complete/degraded/unavailable` 采集覆盖合同，再
   建立隐私安全的本地观测：SDK 实际 Agent/Skill/Tool/Subagent/权限事件、脱敏输入输出、
   总耗时、各 Tool 调用数/状态/耗时、解析与渲染缓存命中、实际 render execution、
   渲染/审查页数、图片输入字节、Token/成本来源、重试、首个失败来源和本地证据引用；
   稳定且无正文的 run/task ID、最终文档 hash 与任务级覆盖/privacy 汇总进入 schema v2
   `conversion-report.json`；
3. 保留全量 pytest、ruff、mypy、build/lock、基础/visual-renderer/agent-smoke doctor 和受影响
   的真实合成产品 smoke；这些是产品回归门，不属于延期的 M3 Eval；
4. 每项优化只声明一个主要可量化目标，使用同一输入、固定路由和同一安全/验证要求
   比较前后结果；
5. 公开报告、Tool/CLI 合同或架构事实变化时，在同一变更中同步受影响的 00–06、README
   和 active capsule。

O0 核心实现与自动化完成门必须可在无头/云端环境运行。历史证据挂载依赖平台无关的
内存 capability 与 hash/ref 验证；本地调试壳可以按需加载 OS 目录选择器或打开文件管理器
适配器，但适配器缺失时只使这些本地便利功能 unavailable，不阻塞 O0，也不能被转换核心
或云端运行代码导入。任何适配器都不得退化为浏览器提交任意绝对路径。

实现顺序固定为：

1. **O0 本地观测面**：在现有 SDK 消息流、hooks/telemetry、Tool adapter 和最终报告上
   增加非阻断脱敏采集，提供运行总览、单次任务、Transcript、Agent/Subagent 树、
   时间线、Tool 详情、调试上下文、本地证据有效性和可比运行差异；不记录正文、学校
   材料正文、完整页面图片、完整模型请求/响应、隐藏思维链、凭据或未经授权的绝对
   路径；页面只读，不启动、重试或调度 Agent/Tool；原始载荷不得进入观测队列，父子
   关系只由直接 ID 证明，不能证明时显示 partial/conflict；每次 SDK 运行使用临时
   `CLAUDE_CONFIG_DIR` 并清理 transcript；CLI 结束后证据默认 unmounted，用户重新选择且
   report/hash 验证后才可打开；Web 直接打开且具备自动短期 session、同源/CSRF/路径安全
   和硬资源上限；
2. **O1 调用降重**：减少没有产生新文档快照或新视觉证据的重复 inspect、render、
   visual-review 和 validate，同时保留 Agent 自主判断，不引入固定工作流；
3. **O2 单次运行复用**：优先复用已绑定相同文档 hash、renderer、字体、locale 与参数的
   解析和渲染产物；cache hit 不启动新容器；
4. **O3 证据载荷**：根据已知页面范围组合 page batch、contact sheet 与 crop，减少重复
   图片字节，但最终仍覆盖所有必查页面并保留细节补证；
5. **O4 失败与重试**：根据明确失败来源阻止同一输入、调用方式和固定后端环境下的
   无效重试，不增加跨职责 fallback。

已知 Kimi Claude Code HTTP 400 请求格式缺陷的窄兼容修复属于运行正确性 hotfix：显式
high effort、关闭 Tool Search、400 安全分类和同 route credential 去重已提前落地；这不表示
O4 的完整失败分类、测量和验收已经启动或完成。

O0 完成门是后续 O1 的硬前置：合成消息/hook fixture 必须精确证明 Tool use/result 与
交错 Subagent 的 actor/parent 关联；缺失、冲突、重复和乱序必须安全降级；prompt、用户
回答、Tool 原始载荷、错误、图片和路径中的隐私 canary 必须在数据库、导出、日志和最终
报告中全部缺席；真实 SDK 正常/强制终止 smoke 必须证明 transcript 隔离与清理；v1/v2
report、平台无关的 capability 挂载验证、免登录自动 session、Host/Origin/CORS/CSRF、路径/symlink
和资源预算必须通过；真实 OS/GUI 目录选择器只属于可选本地调试兼容性 smoke，不是此门；
projector、队列、观测存储、collector 与 UI 故障注入不得改变转换终态、产物 hash、Tool/
权限结果或 render execution 次数；任务文件系统耗尽则必须如实报告 App storage failure；重启后
只能从用户显式挂载且验证通过的最终报告做无时间线 summary-only 对账。上述合同测试
未通过时不得开始 O1，也不得把页面截图视为 O0 完成。

该切片的每次合入都必须证明：源文件不变；五个公开 Tool 和未匹配工具默认拒绝不变；
OfficeCLI/LibreOffice 固定职责、V2 render 完整性、独立验证、blocking/warning 语义与
最终报告一致性不退化；主要目标有前后测量；新 render execution 没有因重复验证无故
增加。性能数据只能
支持对应工程改进，不能支持复杂真实论文质量、受控试用 MVP 或 M3 已通过的结论。

当前明确延期：M3 Skill/E2E Eval 扩展、Gold、授权/脱敏真实样本资格验证和外部人工
复核；M4/M5；第三引擎和通用 Provider 抽象；更多 Subagent 或第二 Agent loop；并发
任务、跨任务持久缓存、集中式 trace/实验服务和正式性能平台；OCR/更多输入格式；
精确版式模型或像素级自动判定；高级 Word 对象编辑、Word 桌面兼容性；Eval 平台、
replay 和学校数据库。这里延期的是平台化能力，不包括已经批准设计的本地只读 O0。

### 6.7 M2 后独立切片：主 Agent 直接读取边界与受信任 Bash/Write

该切片扩大主 Agent 的判断与执行面，但不恢复 M3。直接 Read/Glob/Grep 仍受 canonical
路径策略约束；Bash/Write 按“先信任主 Agent”的明确决策可见、自动批准且无 DocFit
路径 gate。五个公开 DocFit Tool 继续由主 Agent 直接调用，并承担 DOCX
inspect/render/edit/visual-review/validate 的权威证据合同；它们不再被描述为阻止主
Agent 直接文件写入的 sandbox。

截至 2026-08-04，该切片实现、全量确定性门和五项真实 SDK smoke 已通过；最新紧凑证据
记录在 `docs/status/active/docfit-main-agent-read-permissions.md`。这不是 M3 或 O0.7
完成声明。

当前权限矩阵固定为：

| 能力 | 主 Agent | `docfit-unit-analyst` |
|---|---:|---:|
| Skill | 是 | 否 |
| Read/Glob/Grep：项目 Skill references | 是，限批准根 | 否 |
| Read/Glob/Grep：产品 Knowledge | 是，限批准根 | 否 |
| Read/Glob/Grep：当前任务 | 是，限 input/work/output | 否；只消费显式任务包 |
| Write | 是，自动批准，无 DocFit 路径 gate | 否 |
| Bash | 是，自动批准，无 DocFit 路径 gate | 否 |
| 五个 DocFit Tool | 全部直接调用 | 仅 inspect + visual-review |
| Agent | 只能调用 `docfit-unit-analyst` | 否 |
| AskUserQuestion | 是 | 否 |
| render/edit/validate | 是 | 否 |
| Edit/Web | 否 | 否 |

路径权限合同：

1. `Read/Glob/Grep` 对主 Agent 可见但不加入自动批准集合；SDK `PreToolUse` 与
   `can_use_tool` 采用同一判定；
2. 调用路径先相对项目 cwd 展开，再解析为真实绝对路径；允许根仅为项目
   `.claude/skills/**`、`src/docfit/knowledge/package/**`、当前任务 `input/**`、
   `work/**` 和 output 根；
3. 搜索必须提供显式根；Glob pattern 与 Grep 的可选 glob filter 不得是绝对路径、`~`
   或包含 `..`，Grep 正则本身只匹配内容；
4. `~/.config/docfit/**`、`.env`、`.git/**`、常见凭据名、其他任务、项目外路径、
   非普通文件和 symlink 逃逸拒绝；搜索树含 symlink 或敏感文件时整次搜索拒绝；
5. 允许调用将 canonical path 写回 SDK Tool input；权限事件只保存 tool/decision/
   固定 reason code，不保存路径、pattern 或正文。
6. `Bash/Write` 对主 Agent 可见并加入自动批准集合，不安装 DocFit 路径 hook；它们可
   访问 Agent SDK 子进程本来可访问的路径和环境，包括直接 Read allowlist 外的文件、
   input、文档产物与后端凭据。系统提示要求不输出凭据/正文，观测 projector 不保留
   命令、路径或内容，但这不是文件系统 sandbox；Subagent 不继承 Bash/Write。

两个领域 Skill 把详细方法拆入同目录 `references/`。`SKILL.md` 必须逐一使用明确项目
相对路径说明何时读取，不能依赖 Skill 工具自动加载关联文件。学校提取 Skill 的首批
references 为 evidence/conflicts、template text classification、Tool recovery、scenarios、
本地委派说明与 output schema；转换 Skill 的首批 references 为 task evidence/conflicts、
Tool recovery、evidence/visual review、scenarios、本地委派说明与
editing/validation/completion。共同的 Subagent 字段和权限由架构合同定义；
两棵 Skill 不跨目录引用共享操作手册或彼此的 references，契约测试验证本地引用完整性和
领域隔离；当前不提供 scripts 目录。

确定性门新增：权限契约逐项覆盖直接读取允许根、input/其他任务、`.env`、`.git`、
凭据、`..`、缺失路径、搜索树敏感文件与 symlink 逃逸，并证明主 Agent Bash/Write
自动批准、无路径 hook、Subagent 明确拒绝二者；Skill
契约证明每个 reference 都被 `SKILL.md`
显式引用；doctor 检查主 Agent 可见面、直接读取/Agent 两类权限 hook、Bash/Write
自动批准和 Subagent 最小面。live `path-tools` smoke 必须实际调用 Read/Glob/Grep 读取
授权 canary，在临时 scope 中用 Write 写入 work/input/任务外 canary，并用 Bash 读取任务
外 Write 产物；任务外 secret 只验证直接 Read 拒绝，不声称 Bash 无法读取。原 image、
ask-user、denied-tools、subagent smoke 继续通过，其中 denied-tools 只验证 Edit/Web 与
未注册 Tool 拒绝。该切片不调用
OfficeCLI/LibreOffice，不启动视觉容器。

### 6.8 M2 后切片：稳定 Style Contract 与 occurrence 门禁（第一垂直切片已实现）

2026-08-10 经用户批准后，第一垂直切片已经把样式从临时观测升级为模板发布与学生填写
共享的不可变合同。稳定性不变量是：同一 `style_contract_id + contract_digest` 的全部
最终 occurrence，其受管有效属性必须一致。样式归属于展示 slot/role，而不是
`field_id`；同一字段在封面、摘要或正文可以合法引用不同合同。

已实现边界：

- Fill Contract v2 的 `styles[]` 是唯一真源，slot 只携带完整 `style_contract_ref`；
  `expected_value_style` 与旧 `style_id` 在 v2 中被拒绝，v1 只保留冻结的只读解析路径，
  不参与新合同写入；
- 产品 resolver 解析 `docDefaults`、默认段落/字符样式、`basedOn`、toggle、段落/字符样式
  和直接格式，并输出属性级 provenance、coverage 与 unresolved；
- 模板 publish 从最终 DOCX 快照捕获每个 slot 的有效属性，生成 template-bound Style
  Contract Set，并在发布前重新打开代表 occurrence 验证；目标用户可见主交付物为原子绑定的
  `final-template.docx + fill-contract.json`，报告、回执和审计仍留在任务内部；
- Placement、Fill 与 Projection 共用 digest-bound 引用。正文、参考文献、题注、公式和
  drawing 的最终段落都生成稳定 paraId occurrence；写入层不修改共享学校命名样式，而是
  只对每个 occurrence 显式写入合同拥有的属性；
- 最终候选在内容审计和渲染前执行 occurrence-level style audit；任何 failed 或 unresolved
  都是阻断错误，不能被 `PARTIAL` 状态掩盖；同一合同重复 1、10、100 次的回归已经覆盖；
- 独立模板提取 Eval 已升级 v2 schema/model/loader/digest/引用闭包验证，并保持不 import
  产品 resolver；现有 v1 Gold 无需迁移。

当前切片只承诺段落/Run 的核心字体、字号、粗斜体、颜色、对齐、段前后/行距和段前分页。
Theme token 的最终求值、编号合同、表格条件样式、复杂 section/page/container 依赖、
跨 header/footer/footnote/textbox story 的完整物化，以及国家标准缺失值补全仍未实现；
遇到这些范围时必须明确 unresolved 或拒绝发布，不得回退到经验默认值。国家标准来源的
授权、版本、条款映射和适用性仍需独立批准。五个公开 Tool、Claude Agent SDK runtime、
Field Registry 语义和 renderer 均未改变；未来若要扩展公开 Tool schema，仍需单独审批。

通用兜底是后续阶段硬门，不采用“已有部分样式即可继续”的渐进放行。产品定义通过后可以进入
模板融合工程实现；只有角色覆盖、属性来源、稳定取值、整角色二选一实现和全链路验收全部通过，
才能进入正式 Student Fill 与 M3 产品阶段。任一工程维度为 `PARTIAL`、`UNKNOWN`、
`UNRESOLVED`、`FAILED` 或未验收时均保持 `production_fill_allowed=false`。完整性必须使用按角色类型定义的属性规范，并在继承展开后检查最终
有效属性；适用属性必须是具体值（包括明确的 `0`），无编号为 `none`，不适用为 `N/A`，
空白、隐式 Word 默认值或依赖学校 `Normal` 补齐关键属性均为阻塞。

当前 `docfit-general-style-preset-v1.review.yaml` v1 已完成注册表 v0.1 的 54 字段处理映射，
并为 9 类样式类型、11 类全局/版面类型建立完整属性集合，覆盖 44 个样式角色和 13 个全局/版面角色。44 个样式角色展开继承后，声明范围内
的全部适用属性均具有具体值、明确 `0`、`none` 或 `N/A`，产品属性闭包已通过。三张人评表已经
形成，产品负责人已于2026-08-11接受全部产品值、角色边界、参数边界和三张评审表。因此当前状态为
`PRODUCT_DEFINITION_ACCEPTED`，`product_definition_complete=true`，`next_stage_allowed=true`，
允许开始整角色运行时融合的工程实现。正式标准全文仍待授权复核，故不得作国家标准符合性声明；
Word 写入和全链路视觉验收尚未完成，`production_fill_allowed=false`。

### 6.9 M2 后候选切片：字段槽定位、学生内容投影与 Placement

该候选切片补齐模板提取输出、学生内容提取输出和最终转换之间的数据连接，并为未来
M3 的分层 Eval 提供同一事实基础。它不是恢复 M3 的执行批准，也不新增第三个领域 Skill、
第六个 Tool、全局 Content Ledger、学校数据库或固定 Agent 流程。

当前已建立研发设计基线
`docs/plans/docfit-content-field-registry/DESIGN.md` 和 accepted v0.4；Student 002 的
不可变历史 Extraction Gold 绑定 accepted v0.3。Registry 的责任边界、未注册字段和版本
规则，以及模板提取 Eval 的 candidate fill-contract/case schema 已完成。Student
Content Model v2、Student 001/002/003 Human-accepted Extraction Gold v2 和正式
`docfit eval-student-content` 离线比较入口已经实现；入口自动读取 Actual、inventory 与
Agent evidence，输出 JSON/Markdown，并独立评测字段、值、覆盖、跨源实例、顺序和关系。
Placement/Filling Truth、学校级 Filling 回归和完整 M3 仍未实现。内部 Student Content →
Placement → template-fill 调试切片不因 Extraction Eval 完成而升级为正式 Filling 能力。

目标范围包括：

- 使用开放、版本化且由 Registry ID/version/hash 绑定的 Content Field Registry，
  至少包含 `field_id` 含义、
  类型、语义基数、父字段/语言和值来源/学生提取策略；
- Template Actual/Truth 使用 `slot_id/region_id → field_id`、模板 hash、稳定 target
  locator/区域边界、责任、条件、fill/empty/placeholder 和样式合同；复合槽与连续区域
  保留各自 locator 形态；
- Student Content Actual/Truth 使用任务内 `content_id → field_id`/未注册状态、学生源
  hash、值或复杂对象引用、source occurrence/locator、父子关系、顺序和冲突状态；
- 区分一份论文级共享事实与它在源文档中的多次 occurrence；局部章节、段落、图表和
  公式保持独立有序内容实例；
- Placement Actual/Truth 显式连接 source content 集合与具体 `slot_id/region_id`，保存
  action、projection/formatter、order、condition、status 和证据，并覆盖一对多、多对一、复合、连续、条件、
  retain/exclude、generated、任务输入、外部/manual 与 unresolved；
- template/student locator 各自绑定自己的文档 hash；`field_id` 只生成候选，不作为
  `docx_edit` locator 或自动写入授权；
- 默认把 Human Truth 标为 `oracle_only`，只有受控执行能力 Eval 才逐文件暴露为
  `subject_input`；Student Content 文件继承源 DOCX 的隐私和授权边界。

本轮内部调试切片的批准范围和证据记录在
`docs/plans/docfit-student-content-placement-debug.md` 与对应 active status。任何正式
Template/Placement/Filling schema、产品运行时消费或 Gold 晋升仍必须另行批准。当前
Extraction 侧已以 Registry v0.4、Student Content Model v2、Gold v2 和
`docfit-source-order/v1` 关闭字段、来源、共享 occurrence、顺序、未注册政策、Truth
可见性与隐私；后续字段语义变化仍必须先升级 Registry，再同步 Gold 与 Filling 映射。

该切片的普通 schema/契约门必须验证字段引用闭包、locator 唯一与 stale 拒绝、Template—Registry
双向一致、学生内容覆盖、placement 双向覆盖和确定性候选条件。实际 Template/Student/
Placement Actual—Gold 评分、授权/脱敏真实样本和 Filling Gold 晋升仍属于第 7 节 M3，
不得用 Extraction PASS 冒充已通过。当前批准的 `eval-student-content` 是运行时之外的
研发 CLI，不增加公开 Tool、不改变五个 Tool 名称，也不改变 M2、O0 或 O1 状态。

## 7. M3：达到可试用 MVP

> 当前范围说明：另行批准的 Registry、Student 001/002/003 Extraction Gold 与 Student
> Content Extraction Eval 已完成；其余 Placement/Filling/端到端 Eval、授权/脱敏真实样本
> 资格验证和外部人工复核仍未完成。以下完整 M3 完成门保持不变。

模板提取静态产物 Eval 已先完成独立顶层设计，见
`docs/plans/docfit-template-extraction-eval/DESIGN.md`。它定义 Actual 模板/填写契约与 Gold
模板/填写契约的只读比较、两套业务断言和评分报告。当前独立工程的 schema/config、
合成 fixture、共享事实分析、评分 runner 和报告已通过 G3 合成纵向证据，三校 candidate
case 目录也已物化；但 Human-accepted Gold 与学校回归尚未完成。这些合成证据和
candidate 数据不等于恢复完整 M3，也不满足本节任何完成门。

完整 M3 还必须实现第 6.9 节的 Placement/Filling 与端到端 Eval，并用真实 Actual 运行
Student Content Extraction 回归。模板静态高分不能
证明学生内容已正确提取或放到正确目标；相同 `field_id` 也不能替代 source/target
locator、动作、顺序、条件和未解决状态的独立比较。

### 7.1 目标

把“单个 smoke case 能跑”提升到“对代表性风险可重复、可回归，并允许受控真实试用”。

### 7.2 范围

- 建立 Tool test、Skill eval 和端到端 Eval 三层验证；
- 建立经过 Human Readiness Gate 的 Registry 快照、Template Truth、Student Content Truth 与
  Placement Truth；Registry 记录 ID/version/hash，三类 Truth 分别记录 schema/hash、review、
  权限和 subject/oracle 可见性；
- 分别实现 Registry 自洽检查、模板提取静态 Eval、学生内容提取 Eval 和 Placement Eval，
  再由端到端 Eval 从最终 DOCX 重新验证内容、目标和样式；
- 增加 1 个普通合成样本和 3–5 个单风险 fixture；
- 在授权或脱敏前提下引入 1 个结构复杂的真实样本；
- 把所有已发现缺陷变成自动断言；
- 建立人工交付高风险页面复核清单；
- 把 M1/M2 已接入的 V2 LibreOffice 视觉链路扩展到授权或脱敏真实样本，并建立高风险
  页面人工复核；
- 对分页敏感样本验证 contact sheet、按需页面、object/text region 和修改后 compare 能由
  Agent 自适应组合，同一 render/view identity 不重复生成；
- 验证 OfficeCLI 语义锚点到 LibreOffice PDF bbox 的映射对视觉问题定位和编辑目标选择
  的帮助，歧义对象只返回候选页；
- 使用第 6.6 节已经建立的运行指标观察质量用例成本，但不把性能数字当作 M3 质量
  结论，也不要求在 M3 中重建第二套观测协议。

### 7.3 验收标准

必需的确定性门：

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit eval --suite core
```

必需的本地与人工门：

- 五个 Tool、固定路由及两个后端各自职责范围内的契约测试全部通过；
- 核心 Skill eval 全部通过；
- Content Field Registry 的 ID/type/cardinality/parent/value-source/student-extraction
  policy 自洽，模板、学生内容和 placement 引用同一 Registry ID/version/hash；
- 每个 Template Actual/Gold 的 slot/region、target locator/边界、字段、条件、fill/style
  policy 可比较，locator 在绑定模板 hash 内唯一且 stale 时拒绝；
- Student Content Eval 覆盖字段归属、值/复杂对象、source locator、父子/顺序、共享
  occurrence 冲突、未注册/不支持内容和隐私；generated/任务输入/外部字段不误计漏项；
- Placement Eval 覆盖一对一、一对多、多对一、复合槽、连续区域、条件、retain/exclude、
  generated/external/manual 和 unresolved；每个 in-scope source 和 required target 都有
  明确覆盖，字段同名不会在歧义时静默自动配对；
- 模板提取与转换 Skill eval 覆盖“复杂场景可委派、简单场景可直接处理、未匹配/复合
  范围可合并处理”，且不把具体委派轨迹作为 Gold；
- `docfit-unit-analyst` 的类型白名单、最小 Tool、Knowledge 选择性载荷、证据请求和
  Subagent 无写权限、主 Agent 统一合并/发布边界均有回归用例；
- 使用不同当前任务学校材料的端到端样本全部通过；
- 没有内容静默丢失、结构破坏或源文件覆盖；
- 最终 DOCX 重新取证证明正确 `content_id` 进入正确 slot/region，顺序、对象关系、
  条件和目标有效样式正确；stale/ambiguous locator、字段错配、未映射必需内容或
  required target 缺失均不能被总分掩盖；
- renderer 伪成功、失效引用、跨 run 占位符、复杂对象、字体/渲染差异和视觉审查旧证据误用都有回归用例；
- Agent 能在 Eval 中发现封面溢出、意外空白页、孤行和图表错位等代表性视觉问题；
- Agent 能把可见应用错误标记、断裂域/交叉引用、未完成占位和截断必需内容保留为
  blocking finding；整页不足以辨认时以同一 render ref 的 crop 补证；
- 至少一份授权或脱敏真实论文完成 V2 LibreOffice 转换、全部页面 Agent 视觉审查与高风险页面人工检查；
- 该真实论文的 OfficeCLI 对象通过当前文字/上下文锚点映射到同快照 LibreOffice PDF；
  跨编辑快照先重新 inspect 和 render，Eval 证明 Agent 没有把相同页码当成稳定内容身份；
- 最终采用的 render ref 声明 `fidelity: approximate`，与最终文档、renderer/container/font
  identity、页面和图片正确绑定，并有 Agent 实际覆盖页面的视觉证据；
- 至少一个包含表格或图片错位的 fixture 能通过 semantic anchor 找到正确候选
  `object_ref`，低可信或失效映射不会触发错误修改；
- 所有 `FAIL`、`UNKNOWN`、`verification_gap` 和 blocking issue 都被准确保留并呈现；
- CI 使用合成/授权 fixture，不包含真实学生隐私；
- README 能让新开发者在不理解内部实现的情况下运行核心测试和 smoke case。

M3 通过后，DocFit 才达到“可受控试用 MVP”。

### 7.4 停止门

- 真实样本只能靠逐案硬编码学校名或段落序号通过；
- 缺陷修复没有对应回归资产；
- 为追求通过率而弱化内容安全或把 `UNKNOWN` 当作成功；
- 性能优化改变了验证独立性或错误语义。

## 8. M4：跨学校验证与通用 Knowledge 演进

### 8.1 目标

在转换链路稳定后，用多个学校任务验证通用概念和方法，只把去除学校名称、数值、
模板和固定文案后仍跨学校成立的知识随新产品版本发布。

### 8.2 范围

- 用 `docx_inspect`、`docx_render` 和 `docx_visual_review` 在各自任务中分析学校材料；
- 为不同学校材料建立合成、脱敏或授权的代表性 Eval；
- 归纳多任务重复出现的领域概念、识别方法、解释原则和通用处理模式；
- 把新增通用内容放入最小合适的 Knowledge 模块；新消费范围不自动产生新的
  Subagent 类型；
- 删除候选内容中的学校名称、精确数值、固定文案、模板对象和 Provider 私有字段；
- 通过跨学校回归与人工评审后提升产品 Knowledge 版本和 digest；
- 保留 Agent 判断、当前任务证据与确定性 Tool 的边界。

### 8.3 验收标准

- 当前任务学校材料及推导规则没有被复制进产品 Knowledge；
- 每项新增 Knowledge 都能说明其跨任务重复证据和去学校化过程；
- 候选内容不包含学校名称、精确格式值、模板或固定文案；
- 新产品 Knowledge 包通过 schema、document hash、digest 和构建检查；
- `convert-thesis` 使用新版本后，不同学校材料的核心回归全部通过；
- 未确认推断、单校特例和 Eval 期望不会被写成通用事实。

### 8.4 停止门

- 新学校任务只能通过修改通用 Skill 或产品 Knowledge 才能接入；
- 单个任务的学校结论未经跨学校证据和去学校化审查就升级为产品 Knowledge；
- 为积累学校事实建设学校目录、检索服务、发布平台或数据库。

## 9. M5：按真实需求产品化与优化

M5 不是首个 MVP 的前置条件。只有真实使用数据证明需要时，才按独立需求进入：

- 打包和发布 CLI；
- API、GUI 或多用户入口；
- 第三个执行引擎，以及有实证需求时的动态选择与故障转移；
- 容器化、任务隔离、资源配额和正式密钥管理；
- 通用 Knowledge 的按需索引（只有内容规模证明需要时）；
- 并发 Eval、跨任务持久缓存、正式性能基线和性能平台；
- 自动化、可扩展的视觉证据与人工交付复核工作台。

每项新增能力必须单独说明：

1. 当前痛点和测量证据；
2. 为什么现有 Skill、Knowledge、Tool、Eval 或应用壳无法解决；
3. 最小实现和删除成本；
4. 新增自动化与产品运行验收；
5. 是否产生第二个真实消费者。

## 10. 阶段总览

| 阶段 | 对用户可见的结果 | 阶段通过后可以声称 | 不能声称 |
|---|---|---|---|
| M0 | CLI、doctor、SDK smoke | 开发环境和 Agent runtime 已接通 | 能处理论文 |
| M1 | 五个 Tool 可独立运行 | 合成 DOCX 可安全检查、修改、渲染、返回图片证据并验证 | Agent 已能完成转换 |
| M2 | 一条 `docfit convert` 命令 | 合成样本上的 OfficeCLI + V2 LibreOffice 链路及交付转换门已跑通 | 已达到复杂真实论文交付质量 |
| M2 后权限/Skill 渐进披露切片 | 主 Agent 可按需直接读取 Skill references、产品 Knowledge 与当前任务证据，并使用受信任 Bash/Write | realpath 受限的直接 Read/Glob/Grep、无路径 gate 的自动批准 Bash/Write、五 Tool 直调和不等权 Subagent 权限已验证 | Bash/Write 是 sandbox、所有 Agent 等权或 M3 已通过 |
| M2 后观测/优化切片 | 本地只读运行观测页，以及同一转换链路在既有安全门下减少可测量的重复工作 | 已观测的实际轨迹、有效本地证据定位，以及已证明的单项耗时、调用或载荷改善 | 精确 replay、M3、MVP 或真实论文质量已通过 |
| M2 后样式观测/补全候选切片 | 属性级模板观测、缺口和可追溯的确定性解析 | 仅在独立计划实施并通过契约门后，可声称已覆盖的属性可追溯解析 | Agent 可以杜撰样式、已覆盖任意国家标准，或当前能力已实现 |
| M2 后字段槽/Placement 候选切片 | 固定 Registry 快照、模板 target、学生 source 与显式 placement 的数据连接 | Registry v0.4、Student Model/Extraction Gold v2 和独立 Extraction Eval 已实现；Placement/Filling 仍按各自门推进 | 字段同名可自动写入、Placement/Filling 已通过或完整 M3 已通过 |
| M3 | 核心 Eval 与真实样本复核 | 可受控试用 MVP | 已覆盖所有学校和长尾情况 |
| M4 | 新版通用 Knowledge + 跨学校回归 | 通用知识可以从多任务证据中受控演进 | 可以持久化学校事实或自动晋升任务结论 |
| M5 | 按需求增加的产品能力 | 对应能力已产品化 | 可以跳过证据直接扩平台 |

## 11. 可迭代性的最低保证

项目达到 M2 时，必须已经具备以下扩展接口，而不是等以后重构：

- **Tool 契约稳定**：Agent 只依赖五个版本化 Tool schema，不依赖 Provider 私有接口；
- **视觉证据可追溯**：每张送入 Agent 的图片都绑定文档、render、renderer/font identity、
  页码、变换参数和图片 hash；
- **页面身份受限**：页码只在对应 render ref 内有效；OfficeCLI 对象只能经当前快照的
  语义锚点映射到 LibreOffice PDF；文档 hash 变化后重新 inspect 和 render；
- **按需视图可扩展**：contact sheet、pages、regions、compare 共用 V2 Evidence Store，
  增加 selector 不修改 Tool 名称；
- **固定 adapter 被封装**：Skill 和 Agent 不依赖 OfficeCLI / LibreOffice 私有接口；
  不建设通用 Provider 平台或自动回退；
- **Knowledge 可版本化**：通用包随产品发布并具有 manifest、文档 hash 和 digest；学校事实只在当前任务证据中；
- **Knowledge 可选择投影**：当前领域 Skill 选择委派所需模块，主 Agent 把模块内容、
  版本/digest 和任务证据写入通用 Subagent prompt；
- **样式来源可扩展**：未来可在不向 Agent Knowledge 增加样式值的前提下，在现有 Tool
  内部增加属性级观测、标准解析、来源和未决状态；这是扩展点，不是 M2 已实现声明；
- **字段语义与 locator 分离**：当前固定 Registry 快照可让 Template/Student/Placement/Eval 共享
  `field_id`，同时让学生 `content_id + source locator`、模板 `slot_id/region_id + target
  locator` 和 placement 各自保留作用域；当前只确立研发数据边界和 Eval 候选引用，
  不是产品运行时或 M2 已实现声明；
- **双侧覆盖可验证**：未来 placement 能同时证明每个 in-scope source 的处置和每个
  required target 的满足状态，未注册、generated、external 和 unresolved 不会被静默
  当作成功；该覆盖不升级为全局 Ledger 或固定工作流；
- **Skill 可独立迭代**：`docfit-school-extract` 与 `convert-thesis` 可以在不修改 Tool
  实现的情况下演进；
- **Skill 可渐进披露**：`SKILL.md` 以明确项目相对路径按需读取 references；主 Agent
  的直接 Read/Glob/Grep 只进入项目 Skill、产品 Knowledge 和当前任务批准根；受信任
  Bash/Write 可绕过这项直接读取边界，文档必须如实说明；
- **Subagent 配置最小**：只有一个 SDK 接线级 `docfit-unit-analyst`，类型白名单和
  inspect + visual-review Tool 面可验证；它不继承主 Agent 的 Skill/Read/Glob/Grep/Write；
  委派逻辑不进入应用壳；
- **Shell 只信任主 Agent**：主 Agent Bash 自动批准且无 DocFit 路径 gate；Subagent 没有
  Bash/Write。命令、路径、环境值和正文不得进入隐私安全观测投影；
- **失败可回归**：每个重要缺陷都有 fixture 和对应层级的断言；
- **应用壳保持薄**：CLI 只配置 SDK、输入、权限和输出，不包含论文语义；
- **本地观测只读**：O0 只投影 SDK 实际事件、Tool 脱敏摘要和本地证据 ref；观测失败
  不影响转换，证据删除/hash 变化后不猜测或精确回放；
- **真实数据可隔离**：任务工作目录、输出、缓存与日志有明确权限和生命周期；
- **公共命令稳定**：内部解析器或 renderer 的批准升级不改变 `docfit convert` 用户入口。

如果为了“以后可能需要”新增基类、服务、状态表、事件总线、数据库或发布系统，
应拒绝该抽象。OfficeCLI 与 LibreOffice 的职责不同，不构成通用 Provider 接口的两个
消费者；当前视觉合同明确只有一个 renderer。

## 12. 总体验收与执行契约

### 12.1 “项目已经跑起来”

只有 M0、M1、M2 全部通过，且公共 `docfit convert` 命令在真实 SDK、OfficeCLI 与固定
Docker LibreOffice 下完成合成 smoke case，才满足当前最主要目标。

### 12.2 “项目易于后续迭代”

同时满足以下条件：

- Tool、Knowledge、Skill 和应用壳边界与 01 一致；
- 固定后端的薄适配变化不要求修改 Skill；
- 新学校任务只需提供当前材料，不要求修改通用 Knowledge、Skill 或 Tool 协议；
- 新缺陷可以被放入明确的测试或 Eval 层；
- 新开发者可以从 README 找到安装、测试、smoke 和常见失败处理；
- 首个垂直切片没有引入当前不需要的 runtime 组件；
- 后续核心优化能从隐私安全的任务级指标得到前后证据，并在不降低独立验证和错误
  语义的前提下通过同一组产品回归门；
- 本地观测界面只展示实际事件和有效引用，不保存正文、完整页面图片、完整模型历史或
  隐藏思维链，也不控制 Agent、Subagent 或 Tool。

### 12.3 Preflight contract

```text
Preflight status: EXECUTED_M0_VERIFIED
Task source: docs/docfit-00-index.md + docs/docfit-01-architecture-core.md + user goal
Canonical source: docs/docfit-06-development-roadmap.md
Route: durable $intuitive-flow
Goal: 只完成 M0，建立可安装、可测试、权限受限并能完成真实 SDK 图片 smoke 的开发底座。
Scope: .python-version、pyproject、uv.lock、CLI、doctor、SDK 接入、仓库外统一 Agent 环境文件、Kimi→MiniMax backend 顺序、Skill 发现、五个 Tool 名称、图片 smoke、权限测试、最小 CI、迁移资产清单。
Non-goals: 所有真实 DOCX Tool 实现、Provider 选型、通用 Knowledge 实现、当前任务学校材料处理、convert 端到端链路，以及 M1–M5。
Entity budget: reuse=现有 Skills、DOCX 脚本和 Claude Agent SDK 原生 Skill/MCP/图片/用户输入能力；new=Python 包、CLI、权限配置、M0 smoke、最小测试与 CI；remove/merge=不复制 SDK 会话或问答协议，不创建 Provider 抽象和真实 DOCX 实现。
Context: must-read=docs/docfit-01-architecture-core.md, docs/docfit-06-development-roadmap.md; useful=docs/docfit-04-skills-design.md, docs/docfit-05-tools-and-data-design.md, 现有 convert-thesis 与学校提取资产；avoid-unless-needed=M1–M5 实现细节、旧工作流设计与未验证平台化方案。
Unknown-unknown scout: skipped；M0 是边界明确的 SDK/CLI 开发底座，未知项通过官方 SDK 契约、确定性测试和三个 live smoke 直接暴露，不需要在实现前扩展产品范围。
Success: M0 的确定性门和本地产品门全部通过。
Result: DONE；2026-07-31 目录归属收口后，Kimi 已完成图片、
AskUserQuestion 与拒绝工具 smoke；三个回执均匹配 claude-agent-sdk 0.2.128，
docfit doctor --require agent-smoke 返回 0。
No regressions（M0 历史）: 当时未匹配工具默认拒绝且 Agent 不能访问任务目录外文件或
网络；当前第 6.7 节已明确用受信任 Bash/Write 取代该文件隔离声明。应用壳仍不解释
needs_input，隐私安全观测仍不写入论文正文。
Verification: deterministic=uv sync --frozen + ruff + mypy + pytest + docfit doctor；local-live=三个 agent-smoke case + docfit doctor --require agent-smoke。
Execution: main=主会话实现并监督 M0 阶段门、范围与最终判定；worker=none；worker-goal=none。
Execution stop: M0 验收后停止，不自动进入 M1；根据 M0 证据生成并审批 M1 Preflight。
To execute: /goal execute docs/docfit-06-development-roadmap.md with intuitive-flow
Optional tracking: none
Approval: LGTM/approve/go ahead 只批准 M0；edits request revision。
```
