# DocFit 开发路线与阶段验收（06）

> 状态：开发执行基线
> 日期：2026-08-04
> 核心目标：先让第一条论文转换链路真实跑通，再用稳定契约、测试样本和清晰边界支持持续迭代。

当前执行证据：五个真实 Tool、固定适配、开发者 CLI、`docfit convert` 薄壳、合成
集成测试和一个可选 `docfit eval --suite core` 已实现；
原实现曾错误依赖本地 Word/AppleScript；该路径已废止，固定转换后端改为 Adobe PDF
Services API。核心转换和云端运行链路不依赖本地 Word、AppleScript、GUI 会话或用户
电脑；本地调试壳可以提供可选平台适配器，但核心代码不得导入，且不作为核心完成门。
仓库外凭据、SDK 4.2.0、路由、测试、Eval 和文档必须作为同一修正验证。
最新确定性与 live 结果只写入 active capsule；本节不以旧的 Word 证据判定 M1–M3。

截至 2026-08-03，M1、M2 各自分配的 deterministic、live Adobe 与合成转换门均已
通过，当前非评测产品开发范围已经完成。用户随后明确把 M3 Eval、Gold、授权/脱敏
真实样本资格验证和外部人工复核移出当前范围；M3 作为后续里程碑未纳入当前执行、
也未通过，
但不再是当前计划 blocker。仓库外授权复杂论文曾完成 Adobe baseline/candidate、15 页
全页 Agent 审查、同快照 Adobe/OfficeCLI 私有文字锚点映射与独立高风险目视检查；该
检查准确保留了可见域错误、未完成占位、跨页表格和空白末页等 blocking/warning，
结果为 `FAIL`，且外部 human signoff 尚未执行。因此这份证据证明真实链路能运行并能
拒绝错误交付，不构成 M3 完成声明，也不要求在本轮继续修正样本或取得人工签字。
真实样本暴露的 Adobe 上传 timeout、SDK 默认
1 MiB 图片消息上限、结构化结果不可见、只读 mode 传播、同路由超时重复轮换和测试
污染 live smoke 回执，以及成功报告重放中间 Agent 旧 warning 等问题均已进入对应
回归；最终判定仍以 active capsule 和本节完成门为准。

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
   Knowledge Package、OfficeCLI 与 Adobe PDF Services API 两个固定后端，以及少量合成样本。
3. **先复用再重写**：现有 `convert-thesis`、学校提取 Skill、DOCX 检查与渲染脚本先做迁移评估，能满足新契约的能力优先复用。
4. **接口由当前消费者驱动**：五个 DocFit Tool 契约、通用 Knowledge Package 和
   Eval case 是稳定边界；当前任务学校事实不升级为长期数据模型。
5. **失败必须可见**：源文件覆盖、内容静默丢失、无法验证的 Provider 结果和偏离已批准
   权限矩阵的 SDK 配置都属于停止项。
6. **每个缺陷都留下回归资产**：Tool 缺陷进入单元或契约测试，Skill 缺陷进入 Skill eval，交付缺陷进入端到端 Eval。

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
| 文档执行与渲染 | OfficeCLI 1.0.143 负责 inspect/edit/validate/`edit_feedback`；Adobe PDF Services API（`pdfservices-sdk==4.2.0`）负责 `baseline` 与 `candidate_verification` DOCX→PDF | 服务 API 不可用，或真实样本证明固定职责不可行 |
| Adobe 凭据与额度 | 凭据只放仓库外 `~/.config/docfit/agent.env` 且 mode 0600；缓存未命中的转换按一个 Document Transaction 计，开发免费额度按每月 500 次规划 | Adobe 官方套餐或凭据格式变化 |
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
Knowledge Package 的静态加载与完整性校验。真实 DOCX 行为和两个固定后端的薄
适配仍由后续里程碑按验收证据加入。

学校模板、要求、示例和推导规则不进入仓库长期 Knowledge；它们只能作为当前
任务输入或授权 Eval fixture。P1 已实现 `docfit-school-extract` 与
`convert-thesis` 两个领域 Skill；模板提取只产生当前任务证据，不创建学校资产生产
入口。当前两个
后端职责不同，只在五个 Tool 内做薄适配，不抽取共享 Provider 接口。只有
未来真实接入第三个引擎，并且确实需要动态选择或故障转移时，才重新评估该接口。

测试目录的职责固定为：

- `tests/unit/`：不依赖 SDK 或真实 Provider 的纯逻辑测试；
- `tests/contract/`：五个公开 Tool、固定路由、SDK Subagent 权限/上下文边界，以及
  两个后端各自职责范围内的契约测试；
- `tests/integration/`：真实 OfficeCLI、CLI 与薄转换壳集成测试；真实 SDK 与 Adobe API
  由仓库外凭据驱动的独立 live 产品门验证。

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
- OfficeCLI 与 Adobe PDF Services API 两个通过各自职责契约测试的固定后端；
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

docfit doctor --require provider
  留给 M1；OfficeCLI、Adobe PDF Services SDK/凭据或必需的 Poppler 工具缺失时返回非零。
```

验收事实（以下均为 M0 当时的历史验收事实；当前权限面以第 6.7 节为准）：

- 全新 checkout 可以仅按 README 在本地完成安装；
- `.python-version`、`pyproject.toml` 和 `uv.lock` 对 Python 与依赖版本的声明一致；
- `docfit --help` 和 `docfit doctor` 正常运行；
- `doctor` 能明确报告 Python、SDK、API key、Provider、三个 render intent 的后端能力、
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
当前 runtime 按 Kimi、MiniMax 的顺序选择 Anthropic 兼容 backend，并通过
`ClaudeAgentOptions.env` 只向 SDK 子进程注入当前候选配置。Kimi 配置显式保持官方
high-effort Tool 上下文并关闭 Tool Search；HTTP 400 请求格式拒绝被视为同一
name/base URL/model route 的不可重放失败，不再轮换 credential 重复请求，而是转到下一个
不同 route。LibreOffice 或其他
DOCX 引擎不再是第一版候选；OfficeCLI、Adobe PDF Services SDK/凭据或 Poppler 的缺失与
版本问题属于 M1 双后端接入证据，不阻塞 M0。

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

不调用 Agent，先让一份合成 DOCX 能被可靠检查、受控修改、渲染、作为图片证据返回，并被独立验证。

### 5.2 范围

- 固化五个 Tool 的版本化 JSON Schema；
- schema 不使用兼容 backend 会误解释的 `oneOf` / `anyOf` / `allOf`；不同 action 的
  专属字段由 runtime 校验；
- 统一 `status`、`checks`、`warnings`、`failure`、`committed` 和 Provider 证据；
- 明确 `object_ref` 的输入 hash、对象 ID、指纹和失效规则；
- 在 `docx_edit` 中实现一个最小跨文档模板组合操作，例如 `import_template_sections`；它仍属于 `docx_edit`，不新增第六个 Tool；
- 在 `docx_render` 契约中固定 `baseline` / `edit_feedback` /
  `candidate_verification` 三个 intent、fidelity、parent ref、转换 profile 和可选 layout map；
- 明确页码只在单个 render ref 内有效；同一文档 hash 的跨后端页面可通过当前快照的 opaque `object_ref`、节引用或文字锚点关联，文档 hash 变化后必须重新 inspect；不得把页面升级为编辑身份；
- 接入并锁定 OfficeCLI：负责 inspect、edit、validate 和 `edit_feedback` 高频截图；
- 接入并锁定Adobe PDF Services API：负责 `baseline` 与 `candidate_verification` 完整 PDF 导出；
- 固定路由由五个 Tool 内部完成，公开 schema 不提供后端选择参数，后端失败时不跨职责静默回退；
- 用同一组 fixture 分别验证两个后端的职责契约，不要求它们实现一套可互换能力；
- 复用或迁移现有 DOCX 脚本，放到 Tool 内部；
- 提供面向开发者的 Tool CLI，便于脱离 Agent 调试。

当前只稳定五个 Agent 可见 Tool。OfficeCLI 与 Adobe PDF Services API 的私有命令、XPath、段落
索引和内部对象路径不得进入 Skill 或 Knowledge。`docx_visual_review` 只读取有效
render ref 的已有页面产物并传递、组织视觉证据；它不调用任何渲染后端、不产生新的
render ref，也不在 Tool 内启动另一个模型或生成版式结论。

`import_template_sections` 的详细字段在 OfficeCLI PoC 后锁定。M1 契约至少覆盖来源模板 hash 与来源对象引用、目标文档 hash 与插入锚点、样式/编号/媒体/relationships/页眉页脚/节属性的依赖闭包、ID 冲突重映射、all-or-nothing 发布，以及合并后重新打开、内容保留和非目标内容检查。

### 5.3 双后端验证矩阵

至少用同一组 fixture 验证：

- 无操作另存后 package 可重新解析，OfficeCLI 可重新检查；
- 段落、样式、表格、图片、公式、节、页眉页脚和编号能被发现；
- 跨 run 文字和占位符可以定位；
- 修改只影响目标对象；
- 跨文档模板组合能够复制完整依赖闭包、重映射冲突 ID，并保持非目标内容不变；
- 失效引用被拒绝；
- 一组修改满足 all-or-nothing；
- 输出能重新打开并通过 package 检查；
- OfficeCLI 可生成高频页面截图；Adobe PDF Services API 可生成完整 PDF，并由本地派生逐页图片；
- render ref 能准确声明 intent、fidelity、页面尺寸、DPI、Provider、SDK 版本、转换
  profile、服务管理且不透明的字体环境和 parent ref；
- render ref 能区分 `baseline`、`edit_feedback` 和 `candidate_verification`，并把 SDK
  版本、转换 profile 和环境证据纳入缓存与失效证据；
- Adobe 与 CLI 页数或分页边界不同的 fixture 能证明相同页码不会被直接关联；同一文档 hash 的页面只能通过当前对象引用、节引用、文字锚点和 mapping quality 对应，文档 hash 变化后旧 ref 被拒绝；
- OfficeCLI 支持时可生成绑定当前 render 的页面元素 bbox 映射；不支持时以能力缺口呈现，不阻塞首版；
- `edit_feedback` 只路由到 OfficeCLI，`baseline` 与 `candidate_verification` 只路由到
  Adobe PDF Services API；未知 intent 和任何后端选择参数都被拒绝；
- Adobe PDF Services API 不可用、额度耗尽或转换失败时不会用 OfficeCLI 结果伪造
  `official_service_conversion` candidate 证据；
- `docx_render` 可以附带有大小限制的 contact sheet；`docx_visual_review` 可以把已有
  render 的指定页面、裁剪图、contact sheet 和前后对比图作为图片 content block
  返回，但不调用渲染后端或产生新的 render ref；
- 版本、字体、环境和已知渲染差异可报告；
- 能在开发机和 CI 中锁定版本、重复安装。

任一固定后端无法满足其职责内的内容安全或真实性底线时，不继续封装假成功接口；
应停止里程碑、记录证据，并重新评估最小补丁或已批准的技术决策。

### 5.4 验收标准

必需的确定性门：

```bash
uv run pytest tests/unit tests/contract -q
uv run docfit tools inspect evals/fixtures/smoke/student.docx
uv run docfit tools edit evals/fixtures/smoke/student.docx --plan evals/fixtures/smoke/edit-plan.json
uv run docfit tools render .tmp/smoke/edited.docx --intent edit_feedback --output .tmp/smoke/render-cli
uv run docfit tools visual-review .tmp/smoke/render-cli --pages 1,2
uv run docfit tools validate evals/fixtures/smoke/student.docx .tmp/smoke/edited.docx
```

必需的Adobe PDF Services 后端门：

```bash
uv run docfit doctor --require provider
uv run docfit tools render evals/fixtures/smoke/student.docx --intent baseline --output .tmp/smoke/render-adobe-baseline
uv run docfit tools render .tmp/smoke/edited.docx --intent candidate_verification --baseline-ref .tmp/smoke/render-adobe-baseline/render-ref.json --output .tmp/smoke/render-adobe-candidate
```

验收事实：

- 源文件 hash 在成功、失败和超时路径都不变化；
- `docx_inspect` 返回输入 hash、摘要、风险和可复用的 opaque refs；
- `docx_edit` 至少完成一个格式修改和一个跨 run 占位符替换；
- `docx_edit` 至少完成一次 `import_template_sections`，并证明来源/目标 hash、插入锚点、依赖闭包、冲突重映射和原子发布符合契约；
- 错误 ref、错误前置文本和输出路径等于输入路径都安全失败；
- 多操作中任一项失败时没有可被误认成成功的输出；
- OfficeCLI `edit_feedback` 生成逐页截图和 intent/fidelity/Provider/字体证据，并明确
  标记为近似；该路由的 PDF 不是完成门；
- Adobe PDF Services API 成功生成 `baseline` 与 `candidate_verification` 的完整 PDF；逐页
  图片由本地 PDF 派生，并形成 `official_service_conversion` render refs；缓存命中不
  重复上传或消耗 Document Transaction；
- candidate 的 `parent_render_ref` 正确绑定输入 baseline；缓存命中不产生新的
  `render_sha256`；
- `docx_render` 的页码只在当前 render ref 内有效；契约测试证明跨 Provider 同页码不会自动对应或成为 `docx_edit` 目标；
- `docx_render` 的 layout map 在可用时包含坐标系、bbox、mapping quality 和当前快照的 opaque `object_ref`；
- `docx_render` 可以返回一张有大小限制的 contact sheet；`docx_visual_review` 返回
  已有 render 的实际图片块，以及绑定文档 hash、render hash、intent、fidelity、
  Provider、字体、页码、图片 hash 和候选对象的 structured content；
- `docx_visual_review` 的 pages/crops/contact_sheet/compare 均不触发 Adobe PDF Services API 或
  OfficeCLI、不产生新的 render ref，也不返回 `pass` / `fail`；
- 旧 render ref、越权路径、超出页数/字节上限和不可比较的 compare 请求安全失败或返回明确 warning；
- `docx_visual_review` 不返回页面是否合格的语义结论；
- `docx_validate` 从最终文件重新取证，不复用编辑器的成功声明；
- 验证结果对每项问题包含 `severity`、`blocking`、`evidence` 和可行动建议；
- Provider 声称成功但产物打不开或修改未发生时，结果为 `error` 且 `committed: false`；
- OfficeCLI 版本与许可证、Adobe PDF Services 版本与自动化接口信息均已记录并锁定。

### 5.5 停止门

- 可见对象可能丢失但 Tool 无法发现或报告；
- 无法独立验证 Provider 的写入结果；
- 渲染结果无法说明 Provider、版本、转换 profile 和环境可见性；
- 近似 Provider 可以把结果标成 Adobe 官方服务转换事实，或 Adobe intent 被静默
  降级；
- 页面图片不能通过受控 Tool 结果进入 Agent 上下文，或无法绑定到当前文档快照；
- 为接入这两个职责固定的后端就需要建设通用 Provider 平台、注册表或动态选择器。

## 6. M2：第一条 Agent 端到端链路

### 6.1 目标

用户通过一条 CLI 命令，实际获得最终 DOCX、预览和验证结果。这是“整个项目已经跑起来”的判定点。

### 6.2 范围

- 实现薄 CLI 应用壳；
- 加载 `.claude/skills/docfit-school-extract/SKILL.md` 与
  `.claude/skills/convert-thesis/SKILL.md`；
- 自动加载随当前产品发布的唯一模块化通用 Knowledge Package；
- 接收一组当前任务学校模板、要求文件、官方示例或用户确认；
- 向主 Agent 暴露五个 DocFit Tool，并配置一个可选的 SDK 原生
  `docfit-unit-analyst`；
- 复用 P1 已完成的 `Agent` 可见性与 SDK `PreToolUse` 类型白名单；只允许
  `subagent_type == "docfit-unit-analyst"`；
- 把该 Subagent 限制为 inspect + visual-review，禁止 Skill、Agent、用户询问、
  render、edit、validate 和持久记忆；
- 由当前领域 Skill 指导主 Agent 选择 Knowledge 模块，并把模块内容/digest 与当前
  任务证据写入 Agent prompt；
- 把 Tool 错误、用户追问和最终回复转发到 CLI；
- 定义 Agent visual findings 的结构化输出 schema；
- 应用壳收集 Agent 的结构化 visual findings，并保存为 `visual-review.json`；
- 证明主 Agent 可以组合 Adobe `baseline`、按需 OfficeCLI `edit_feedback`、Adobe
  `candidate_verification` 和已有证据读取；具体次数与顺序由当前任务判断；
- 产物写入独立输出目录；
- 建立一个真实 SDK 端到端 smoke case。

`docfit-school-extract` 只生成当前任务证据，不生成学校包。合成学校材料由现有学校
提取资产和人工经验重新设计而来，必须保留来源 hash 和任务适用范围，但只服务该次
运行与对应 Eval；不得复制许可证未确认的旧 Skill 内容。

### 6.3 公共产品命令

目标命令：

```bash
uv run docfit convert \
  --input evals/fixtures/smoke/student.docx \
  --school-template evals/fixtures/smoke/school-template.docx \
  --school-requirements evals/fixtures/smoke/school-requirements.pdf \
  --output .tmp/smoke-output
```

模板提取可以作为独立用户目标；其公共 CLI 命令名与参数在 M2 实现 Preflight 中锁定，
本文只固定 `docfit-school-extract` Skill 名和任务级输出边界。

### 6.4 验收标准

必需的集成门：

```bash
uv run pytest tests/integration -q
```

必需的本地产品门：

- 上述 `docfit convert` 使用真实 Claude Agent SDK、OfficeCLI 和 Adobe PDF Services API 成功完成；
- 输出目录至少包含 `final.docx`、与当前最终文档 hash 相同的 Adobe candidate PDF、由
  该 PDF 生成的逐页图片、`visual-review.json`、`validation.json`；OfficeCLI 支持时
  包含 `layout-map.json`；
- `final.docx` 能通过独立 package 检查并由 OfficeCLI 重新读取；在 Microsoft Word
  桌面版中的人工打开只能是可选兼容性观察，不是产品运行依赖或完成前提；
- 源文件 hash 不变；
- 合成论文中的关键文本、表格、图片和必要对象未丢失、重复或错序；
- 目标学校的一个标题规则、一个正文规则和一个模板/占位符规则真实生效；
- Agent 修改前通过图片观察输入与模板，影响布局的修改后通过图片复核变化页和相邻页；
- Agent 以当前文档的对象引用和锚点选择修改范围，不把初始页面编号直接复用于修改后的 render 或其他 Provider；
- Agent 最终分批观察当前 final.docx 的全部页面，每个 visual finding 都引用有效 evidence ref；
- 整页缩放不足以辨认域结果、小字或页边界时，Agent 使用同一 render ref 的 crop
  补证；可见应用错误标记、断裂域/交叉引用和未完成占位不能被结构成功或 Adobe
  转换成功掩盖；
- `visual-review.json` 绑定最终文档 hash、render hash、Provider、服务管理环境和已审查页面，没有未解释的 blocking finding；
- validation 与最终回复引用有效的 Adobe `baseline` 和已经由 Agent 覆盖必查页面、
  后续没有再修改文档的 `candidate_verification` 证据；缺少当前 Adobe candidate 证据时
  M2 不通过；
- Agent 声称完成时必须具有五个 DocFit Tool 的当前证据、未变化的源 hash、当前 Adobe
  candidate 与独立验证；第 6.7 节受信任 Bash/Write 不能替代这些完成证据；
- 复杂、证据密集场景能够使用 `docfit-unit-analyst`，简单场景允许主 Agent 不委派；
- 不存在的单元不被强制创建，未匹配或复合范围可由主 Agent 直接或合并处理；
- SDK `PreToolUse` 权限钩子拒绝 `general-purpose` 和未知 Subagent；通用 Subagent
  只使用 inspect 与 visual-review；
- Subagent 只收到选中 Knowledge 模块和显式任务证据；缺少页面时返回
  `needs_more_evidence`，由主 Agent 补证并自行决定是否再次委派；
- 并行和串行委派都合法，测试不固定调用数量或顺序；
- 跨范围依赖、render 成本、`docx_edit` 和最终发布始终由主 Agent 控制；
- Tool 返回 `needs_input` 时，Agent 能根据证据重新 inspect；确需用户补充时调用 `AskUserQuestion`，由 CLI 的 `can_use_tool` 回调展示问题并继续同一 SDK 会话；
- Tool 返回 `error` 或 `committed: false` 时，Agent 不交付该产物；
- 最终回复中的产物、产品 Knowledge 版本、当前任务学校材料 hash、验证摘要和 warning 与磁盘事实一致；
- 相同错误在输入、调用方式和固定后端环境均未变化时不会无限重试。

M2 通过后，可以对外说明“DocFit 第一条混合渲染论文转换链路已在合成 smoke
case 上跑通，并取得 Adobe 交付转换证据”，但不能说明已经达到真实论文交付质量
或覆盖复杂真实样本。

### 6.5 停止门

- Agent 能绕过 Tool 直接修改 DOCX；
- 页面图片只落盘但没有真正进入 Agent 上下文；
- 修改后继续使用旧截图，或没有复核受影响的相邻页面；
- 最终回复声称完成，但验证仍有未解释的 blocking issue；
- CLI 依赖开发者手工修改中间文件才能完成；
- Adobe PDF Services API 缺失、失败或被 OfficeCLI 静默替代，但链路仍被报告为 M2 通过；
- 为了完成单个用例而把学校规则写进通用 Skill。
- 应用壳开始判断论文单元、选择 Knowledge、强制委派或维护 Subagent 工作流状态。

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
   总耗时、各 Tool 调用数/状态/耗时、解析与渲染缓存命中、Adobe API 调用与缓存命中、
   渲染/审查页数、图片输入字节、Token/成本来源、重试、首个失败来源和本地证据引用；
   稳定且无正文的 run/task ID、最终文档 hash 与任务级覆盖/privacy 汇总进入 schema v2
   `conversion-report.json`；
3. 保留全量 pytest、ruff、mypy、build/lock、基础/provider/agent-smoke doctor 和受影响
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
3. **O2 单次运行复用**：优先复用已绑定相同文档 hash、Provider/SDK、profile 与参数的
   解析和渲染产物；Adobe cache hit 不产生新 Document Transaction；
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
权限结果或 Adobe 调用次数；任务文件系统耗尽则必须如实报告 App storage failure；重启后
只能从用户显式挂载且验证通过的最终报告做无时间线 summary-only 对账。上述合同测试
未通过时不得开始 O1，也不得把页面截图视为 O0 完成。

该切片的每次合入都必须证明：源文件不变；五个公开 Tool 和未匹配工具默认拒绝不变；OfficeCLI/
Adobe 固定职责、官方 candidate 真实性、独立验证、blocking/warning 语义与最终报告一致性
不退化；主要目标有前后测量；Adobe live 调用没有因重复验证无故增加。性能数据只能
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
OfficeCLI/Adobe，不消耗 Adobe Document Transaction。

### 6.8 M2 后候选切片：样式观测与确定性补全（仅长期合同，未实现）

该候选切片用属性级合同稳定模板提取、Agent 语义判断与下游写入之间的耦合。
它不要求 Agent 服从固定内容树或样式模型，也不把可直接套用的样式值交给 Agent。
目标范围只包括：

- 扩展现有 Tool 内部观测，完整报告命名样式、直接格式、继承链、有效值、覆盖、
  缺失和冲突；
- Agent/Skill 只完成语义角色识别、观测绑定、冲突解释和未决项暴露，不生成
  缺失样式值；
- 缺失属性只由程序使用经明确选定、版本化且适用性可验证的国家级标准明文解析；
- 每个属性保留当前任务要求、模板观测、继承后有效值、国家级标准或未决的来源，
  以及标准版本、条款、适用性和规则集 digest；
- 无明文、不适用或来源冲突时保持未决，不增加通用默认样式、学校 profile、第六个 Tool
  或 Agent 可读的国家标准数值表。

开始实现前必须另行批准计划，并先确认标准来源的授权/维护方式、精确标识与版本、
适用性输入、条款映射、冲突语义、属性级来源和合成契约测试。任何公开 Tool schema
调整都必须单独审批并保持五个 Tool 名称。本节不启动 O1、M3 或 M4，不改变 M2 已完成
状态，也不声称当前代码已具备该能力。

## 7. M3：达到可试用 MVP

> 当前范围说明：M3 的 Eval、Gold、授权/脱敏真实样本资格验证和外部人工复核不在
> 本轮开发范围；以下长期范围与完成门保持不变，恢复时必须新建并批准计划。

### 7.1 目标

把“单个 smoke case 能跑”提升到“对代表性风险可重复、可回归，并允许受控真实试用”。

### 7.2 范围

- 建立 Tool test、Skill eval 和端到端 Eval 三层验证；
- 增加 1 个普通合成样本和 3–5 个单风险 fixture；
- 在授权或脱敏前提下引入 1 个结构复杂的真实样本；
- 把所有已发现缺陷变成自动断言；
- 建立人工交付高风险页面复核清单；
- 把 M1/M2 已接入的 Adobe PDF Services candidate 链路扩展到授权或脱敏真实样本，并建立高风险
  页面人工复核；不在 M3 才首次接入 Adobe 后端；
- 对分页敏感的授权或脱敏真实样本，证明首次 Adobe baseline、按需 CLI feedback 和
  一个或多个 Adobe candidate 能由 Agent 自适应组合；上一 candidate 可以作为下一
  candidate 的 baseline ref，不额外导出“轮次基线”；
- 对当前任务模板按模板 hash、SDK 版本、转换 profile 和环境证据复用 baseline；同一
  文档和相同策略不重复调用 Adobe API；
- 验证 OfficeCLI 页面元素 bbox 映射对视觉问题定位和编辑目标选择的帮助；
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
- 模板提取与转换 Skill eval 覆盖“复杂场景可委派、简单场景可直接处理、未匹配/复合
  范围可合并处理”，且不把具体委派轨迹作为 Gold；
- `docfit-unit-analyst` 的类型白名单、最小 Tool、Knowledge 选择性载荷、证据请求和
  Subagent 无写权限、主 Agent 统一合并/发布边界均有回归用例；
- 使用不同当前任务学校材料的端到端样本全部通过；
- 没有内容静默丢失、结构破坏或源文件覆盖；
- Provider 伪成功、失效引用、跨 run 占位符、复杂对象、字体/渲染差异和视觉审查旧证据误用都有回归用例；
- Agent 能在 Eval 中发现封面溢出、意外空白页、孤行和图表错位等代表性视觉问题；
- Agent 能把可见应用错误标记、断裂域/交叉引用、未完成占位和截断必需内容保留为
  blocking finding；整页不足以辨认时以同一 render ref 的 crop 补证；
- 至少一份授权或脱敏真实论文完成 Adobe PDF Services 转换、全部页面 Agent 视觉审查与高风险页面人工检查；
- 该真实论文的同快照 Adobe / OfficeCLI 页面通过当前对象引用或文字锚点关联；跨编辑快照先重新 inspect，再通过新旧节、文字锚点或显式内容指纹对照；Eval 证明 Agent 没有把相同页码当成稳定内容身份；
- 同一份可变论文首次只建立一个 baseline；每个需要 Adobe 交付判断的新候选产生一个
  candidate，上一 candidate 通过 parent ref 作为下一候选 baseline，当前任务模板
  baseline 按模板 hash 独立缓存；
- 最终采用的 candidate render ref 声明 `fidelity: official_service_conversion`，与最终
  文档、Adobe provider/SDK/转换 profile、服务管理环境和页面图片正确绑定，并有 Agent
  实际覆盖页面的视觉证据；
- 至少一个包含表格或图片错位的 fixture 能通过 layout map 找到正确候选 `object_ref`，低可信或失效映射不会触发错误修改；
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
- 自动化、可扩展的 Adobe 服务转换和人工交付复核工作台。

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
| M2 | 一条 `docfit convert` 命令 | 合成样本上的 OfficeCLI + Adobe 混合链路及交付转换门已跑通 | 已达到复杂真实论文交付质量 |
| M2 后权限/Skill 渐进披露切片 | 主 Agent 可按需直接读取 Skill references、产品 Knowledge 与当前任务证据，并使用受信任 Bash/Write | realpath 受限的直接 Read/Glob/Grep、无路径 gate 的自动批准 Bash/Write、五 Tool 直调和不等权 Subagent 权限已验证 | Bash/Write 是 sandbox、所有 Agent 等权或 M3 已通过 |
| M2 后观测/优化切片 | 本地只读运行观测页，以及同一转换链路在既有安全门下减少可测量的重复工作 | 已观测的实际轨迹、有效本地证据定位，以及已证明的单项耗时、调用或载荷改善 | 精确 replay、M3、MVP 或真实论文质量已通过 |
| M2 后样式观测/补全候选切片 | 属性级模板观测、缺口和可追溯的确定性解析 | 仅在独立计划实施并通过契约门后，可声称已覆盖的属性可追溯解析 | Agent 可以杜撰样式、已覆盖任意国家标准，或当前能力已实现 |
| M3 | 核心 Eval 与真实样本复核 | 可受控试用 MVP | 已覆盖所有学校和长尾情况 |
| M4 | 新版通用 Knowledge + 跨学校回归 | 通用知识可以从多任务证据中受控演进 | 可以持久化学校事实或自动晋升任务结论 |
| M5 | 按需求增加的产品能力 | 对应能力已产品化 | 可以跳过证据直接扩平台 |

## 11. 可迭代性的最低保证

项目达到 M2 时，必须已经具备以下扩展接口，而不是等以后重构：

- **Tool 契约稳定**：Agent 只依赖五个版本化 Tool schema，不依赖 Provider 私有接口；
- **视觉证据可追溯**：每张送入 Agent 的图片都绑定文档、render、Provider、字体、页码和图片 hash；
- **页面身份受限**：页码只在对应 render ref 内有效；同一文档 hash 的跨后端页面可通过当前 opaque `object_ref`、节引用或文字锚点关联；文档 hash 变化后重新 inspect，并用新旧快照的节、文字锚点或显式内容指纹对照；
- **渲染意图可扩展**：同一个 Tool 契约区分 `baseline`、`edit_feedback` 与
  `candidate_verification`，近似结果不能升级成 Adobe 交付转换事实；
- **视觉定位可增强**：layout map 作为可选渲染产物绑定 opaque `object_ref`，后续增加 bbox 能力不修改 Skill 或 Tool 名称；
- **固定后端被封装**：Tool 结果包含实际后端与环境证据，但 Skill 和 Agent 不依赖 OfficeCLI / Adobe SDK 私有接口；第一版不建设通用 Provider 平台；
- **Knowledge 可版本化**：通用包随产品发布并具有 manifest、文档 hash 和 digest；学校事实只在当前任务证据中；
- **Knowledge 可选择投影**：当前领域 Skill 选择委派所需模块，主 Agent 把模块内容、
  版本/digest 和任务证据写入通用 Subagent prompt；
- **样式来源可扩展**：未来可在不向 Agent Knowledge 增加样式值的前提下，在现有 Tool
  内部增加属性级观测、标准解析、来源和未决状态；这是扩展点，不是 M2 已实现声明；
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
- **公共命令稳定**：Provider 或内部解析器替换后，`docfit convert` 的用户契约保持不变。

如果为了“以后可能需要”新增基类、服务、状态表、事件总线、数据库或发布系统，
应拒绝该抽象。OfficeCLI 与 Adobe PDF Services API 的职责不相同，本身不构成通用 Provider
接口的两个消费者；只有真实接入第三个引擎且需要动态选择或故障转移时才重评。

## 12. 总体验收与执行契约

### 12.1 “项目已经跑起来”

只有 M0、M1、M2 全部通过，且公共 `docfit convert` 命令在真实 SDK、OfficeCLI
与Adobe PDF Services API 下完成合成 smoke case，才满足当前最主要目标。

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
