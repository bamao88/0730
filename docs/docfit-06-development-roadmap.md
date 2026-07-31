# DocFit 开发路线与阶段验收（06）

> 状态：开发执行基线
> 日期：2026-07-31
> 核心目标：先让第一条论文转换链路真实跑通，再用稳定契约、测试样本和清晰边界支持持续迭代。

## 1. 路线原则

开发阶段与产品运行时是两件事。本文的 M0–M5 只表示工程交付顺序，不进入 DocFit 在线运行逻辑，也不形成新的工作流状态机。

所有阶段遵守以下优先级：

1. **先有真实可运行结果**：每个阶段都必须增加一个可执行命令、可检查产物或可重复测试，不能只增加目录和抽象。
2. **先跑一条窄链路**：第一版只支持一个入口、一个学校包、一个主 Provider 和少量合成样本。
3. **先复用再重写**：现有 `convert-thesis`、学校提取 Skill、DOCX 检查与渲染脚本先做迁移评估，能满足新契约的能力优先复用。
4. **接口由当前消费者驱动**：五个 DocFit Tool 契约、Knowledge 包和 Eval case 是稳定边界；没有第二个真实消费者时，不增加通用框架。
5. **失败必须可见**：源文件覆盖、内容静默丢失、无法验证的 Provider 结果和未隔离的 SDK 工具权限都属于停止项。
6. **每个缺陷都留下回归资产**：Tool 缺陷进入单元或契约测试，Skill 缺陷进入 Skill eval，交付缺陷进入端到端 Eval。

## 2. 第一版技术基线

为缩短启动路径，首个垂直切片采用以下默认选择：

| 项目 | 第一版选择 | 重新评估条件 |
|---|---|---|
| 语言 | Python 3.12；`.python-version` 固定 3.12，`pyproject.toml` 声明 `>=3.12,<3.13` | 已选主 Provider 只能通过不可替代的 TypeScript 库安全使用 |
| 依赖与命令 | `uv`；提交 `uv.lock`，本地与 CI 均按锁文件安装 | 团队现有交付环境无法运行 `uv` |
| Agent runtime | Claude Agent SDK for Python | 产品部署目标改为托管 Managed Agents，且需求已经确认 |
| 用户入口 | 本地 CLI | CLI 已跑通，且真实用户需要 API 或 GUI |
| Skill 装载 | 仓库内 `.claude/skills/` | 需要跨项目安装或发布时再封装 Plugin |
| 测试 | `pytest` | 无 |
| 静态检查 | `ruff` + `mypy` | 无 |
| SDK 内置工具 | 只暴露 `Skill` 与 `AskUserQuestion` | 新增内置能力有经过批准的真实需求 |
| Tool 接入 | SDK in-process MCP server 只注册五个高层 Tool，其中视觉审查 Tool 返回图片 content block | 出现必须独立部署或跨进程复用的真实消费者 |
| 文档渲染 | 首选本地 Provider；记录版本、字体和运行环境 | 目标平台无法安装，或真实样本分页误差不可接受 |
| 数据 | 合成 fixture 优先；真实样本必须脱敏或授权 | 无 |

仓库骨架和 M0 实现按长期资产归属落盘。尚未进入实现阶段的目录只包含简短职责
说明，不放置假实现、空接口或可被误认为已支持的 schema：

```text
.python-version
pyproject.toml
uv.lock
src/docfit/
├── __main__.py             # python -m docfit 入口
├── app/                    # CLI、SDK 配置、doctor、环境与 live smoke
├── tools/                  # 五个 Tool 注册与 M0 图片传输 smoke
└── knowledge/              # Knowledge 加载与校验；M0 只有职责说明
.claude/skills/
└── convert-thesis/
tests/
├── unit/
├── contract/
└── integration/
evals/
├── fixtures/
├── skills/
└── e2e/
knowledge/schools/<first-school>/v1/
```

M0 的应用代码只归属 `src/docfit/app/`，Tool 注册和合成图片能力只归属
`src/docfit/tools/`；包根只保留版本与模块入口，不保留第二组兼容导入面。真实
DOCX 行为、Knowledge 加载和 Provider 适配仍由后续里程碑按验收证据加入。

`knowledge/common/` 同时作为跨学校通用领域知识的长期位置。`<first-school>` 和
`v1` 表示真实学校标识与版本结构，不创建同名字面目录；正式学校包在对应里程碑
具备来源、适用范围、digest 和人工确认后再加入。

只有第二个 Skill 开始实现时，才创建 `.claude/skills/prepare-school-template/`。只有第二个 Provider 实际接入时，才抽取共享 Provider 接口或增加 Provider 选择机制。

测试目录的职责固定为：

- `tests/unit/`：不依赖 SDK 或真实 Provider 的纯逻辑测试；
- `tests/contract/`：五个公开 Tool 契约及各 Provider 对同一契约的一致性测试；
- `tests/integration/`：真实 SDK、真实 Provider、CLI 和端到端集成测试。

## 3. 首条链路

第一条可运行产品链路固定为：

```text
CLI
 └─ Claude Agent SDK（最小权限）
     └─ convert-thesis Skill
         ├─ docx_inspect
         ├─ docx_render
         ├─ docx_visual_review
         ├─ docx_edit
         └─ docx_validate
             └─ final.docx + preview + visual-review + validation
```

首版只要求：

- 一个经过人工确认的学校 Knowledge 包；
- 一份不含真实学生隐私的合成论文；
- 一个通过契约测试的主 Provider；
- 一条可重复运行的 CLI 命令；
- 一组能证明源文件不变、产物可打开、关键内容保留的自动断言；
- 一条能把页面图片真实送入当前 Agent、形成可追溯 visual findings 的审查链路。

首版不要求：

- 自动建设新学校；
- 第二个 Tool Provider；
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
  统一 Agent 环境文件、API key、Provider 或字体缺失可以报告为 NOT_READY，
  但不影响 CI 退出码。

docfit doctor --require agent-smoke
  缺少权限为 0600 的统一 Agent 环境文件、可用 API key、图片 Tool
  或 SDK live 能力时返回非零。

docfit doctor --require provider
  留给 M1；缺少受支持 Provider 或字体环境时返回非零。
```

验收事实：

- 全新 checkout 可以仅按 README 在本地完成安装；
- `.python-version`、`pyproject.toml` 和 `uv.lock` 对 Python 与依赖版本的声明一致；
- `docfit --help` 和 `docfit doctor` 正常运行；
- `doctor` 能明确报告 Python、SDK、API key、Provider、迭代/交付渲染能力、字体和工作目录状态，并按 `--require` 选择正确退出码；
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
`ClaudeAgentOptions.env` 只向 SDK 子进程注入当前候选配置。LibreOffice 或其他
DOCX Provider 的缺失、预发布版本或字体问题属于 M1 Provider 选型证据，不阻塞
M0。

### 4.5 停止门

- 无法证明 SDK 的可见工具集合受限；
- `AskUserQuestion` 无法通过 CLI 回调继续同一会话；
- 未匹配工具可以绕过默认拒绝策略；
- Agent 可以访问任务目录之外的敏感文件；
- 产品必须依赖未经许可的 Claude 登录方式；
- 技术栈变更会导致现有 Python 资产全部重写。

## 5. M1：五个 DocFit Tool 跑通

### 5.1 目标

不调用 Agent，先让一份合成 DOCX 能被可靠检查、受控修改、渲染、作为图片证据返回，并被独立验证。

### 5.2 范围

- 固化五个 Tool 的版本化 JSON Schema；
- 统一 `status`、`checks`、`warnings`、`failure`、`committed` 和 Provider 证据；
- 明确 `object_ref` 的输入 hash、对象 ID、指纹和失效规则；
- 在 `docx_edit` 中实现一个最小跨文档模板组合操作，例如 `import_template_sections`；它仍属于 `docx_edit`，不新增第六个 Tool；
- 在 `docx_render` 契约中固定 `iteration` / `release`、fidelity claim、目标应用和可选 layout map，首版只要求实现 `iteration`；
- 用同一组 fixture 对候选 Provider 做短期能力验证；
- 选择并锁定一个主 Provider；
- 复用或迁移现有 DOCX 脚本，放到 Tool 内部；
- 提供面向开发者的 Tool CLI，便于脱离 Agent 调试。

当前只稳定五个 Agent 可见 Tool。Provider 的私有命令、XPath、段落索引和内部对象路径不得进入 Skill 或 Knowledge。`docx_visual_review` 只传递和组织视觉证据，不在 Tool 内启动另一个模型或生成版式结论。

`import_template_sections` 的详细字段在 Provider PoC 后锁定。M1 契约至少覆盖来源模板 hash 与来源对象引用、目标文档 hash 与插入锚点、样式/编号/媒体/relationships/页眉页脚/节属性的依赖闭包、ID 冲突重映射、all-or-nothing 发布，以及合并后重新打开、内容保留和非目标内容检查。

### 5.3 Provider 验证矩阵

至少用同一组 fixture 验证：

- 无操作另存后 Word 不要求修复；
- 段落、样式、表格、图片、公式、节、页眉页脚和编号能被发现；
- 跨 run 文字和占位符可以定位；
- 修改只影响目标对象；
- 跨文档模板组合能够复制完整依赖闭包、重映射冲突 ID，并保持非目标内容不变；
- 失效引用被拒绝；
- 一组修改满足 all-or-nothing；
- 输出能重新打开并通过 package 检查；
- PDF 和逐页图片可生成；
- render ref 能准确声明 purpose、fidelity claim、目标应用、页面尺寸、DPI、字体文件/版本指纹、替代关系和 Provider；不支持的 `release` 请求不会静默降级；
- Provider 支持时可生成绑定当前 render 的页面元素 bbox 映射；不支持时以能力缺口呈现，不阻塞首版；
- 指定页面、裁剪图、contact sheet 和前后对比图可以作为图片 content block 返回；
- 版本、字体、环境和已知渲染差异可报告；
- 能在开发机和 CI 中锁定版本、重复安装。

候选均无法满足内容安全底线时，不继续封装假成功接口；应缩小首版支持范围或选择最小自研补丁。

### 5.4 验收标准

必需的确定性门：

```bash
uv run pytest tests/unit tests/contract -q
uv run docfit tools inspect evals/fixtures/smoke/student.docx
uv run docfit tools edit evals/fixtures/smoke/student.docx --plan evals/fixtures/smoke/edit-plan.json
uv run docfit tools render .tmp/smoke/edited.docx --output .tmp/smoke/render
uv run docfit tools visual-review .tmp/smoke/render --pages 1,2
uv run docfit tools validate evals/fixtures/smoke/student.docx .tmp/smoke/edited.docx
```

验收事实：

- 源文件 hash 在成功、失败和超时路径都不变化；
- `docx_inspect` 返回输入 hash、摘要、风险和可复用的 opaque refs；
- `docx_edit` 至少完成一个格式修改和一个跨 run 占位符替换；
- `docx_edit` 至少完成一次 `import_template_sections`，并证明来源/目标 hash、插入锚点、依赖闭包、冲突重映射和原子发布符合契约；
- 错误 ref、错误前置文本和输出路径等于输入路径都安全失败；
- 多操作中任一项失败时没有可被误认成成功的输出；
- `docx_render` 生成 PDF、逐页图片和 purpose/fidelity/Provider/字体证据，首版 `iteration` 结果明确标记为近似；
- `docx_render` 的 layout map 在可用时包含坐标系、bbox、mapping quality 和当前快照的 opaque `object_ref`；
- `docx_visual_review` 返回实际图片块，以及绑定文档 hash、render hash、purpose、fidelity、Provider、字体、页码、图片 hash 和候选对象的 structured content；
- 旧 render ref、越权路径、超出页数/字节上限和不可比较的 compare 请求安全失败或返回明确 warning；
- `docx_visual_review` 不返回页面是否合格的语义结论；
- `docx_validate` 从最终文件重新取证，不复用编辑器的成功声明；
- 验证结果对每项问题包含 `severity`、`blocking`、`evidence` 和可行动建议；
- Provider 声称成功但产物打不开或修改未发生时，结果为 `error` 且 `committed: false`；
- 主 Provider 版本和许可证已记录并锁定。

### 5.5 停止门

- 可见对象可能丢失但 Tool 无法发现或报告；
- 无法独立验证 Provider 的写入结果；
- 渲染结果无法说明 Provider、版本和字体环境；
- 近似 Provider 可以把结果标成 Microsoft Word 目标应用事实，或 `release` 请求被静默降级；
- 页面图片不能通过受控 Tool 结果进入 Agent 上下文，或无法绑定到当前文档快照；
- 为接入第一个 Provider 就需要建设通用 Provider 平台。

## 6. M2：第一条 Agent 端到端链路

### 6.1 目标

用户通过一条 CLI 命令，实际获得最终 DOCX、预览和验证结果。这是“整个项目已经跑起来”的判定点。

### 6.2 范围

- 实现薄 CLI 应用壳；
- 加载 `.claude/skills/convert-thesis/SKILL.md`；
- 挂载一个已确认学校 Knowledge 包；
- 只向 Agent 暴露五个 DocFit Tool；
- 把 Tool 错误、用户追问和最终回复转发到 CLI；
- 定义 Agent visual findings 的结构化输出 schema；
- 应用壳收集 Agent 的结构化 visual findings，并保存为 `visual-review.json`；
- 使用首个 `iteration` 渲染 Provider 跑通图片闭环；M2 不要求自动化 Microsoft Word 交付渲染；
- 产物写入独立输出目录；
- 建立一个真实 SDK 端到端 smoke case。

第一版不实现 `prepare-school-template`。第一个学校包可以由现有学校提取资产和人工整理产生，但必须满足来源、版本、digest 和适用范围要求。

### 6.3 公共产品命令

目标命令：

```bash
uv run docfit convert \
  --input evals/fixtures/smoke/student.docx \
  --knowledge knowledge/schools/<first-school>/v1 \
  --output .tmp/smoke-output
```

### 6.4 验收标准

必需的集成门：

```bash
uv run pytest tests/integration -q
```

必需的本地产品门：

- 上述 `docfit convert` 使用真实 Claude Agent SDK 和真实主 Provider 成功完成；
- 输出目录至少包含 `final.docx`、预览 PDF、逐页图片、`visual-review.json`、`validation.json`；Provider 支持时包含 `layout-map.json`；
- `final.docx` 能由 Word 或 LibreOffice 重新打开且不要求修复；这只证明基础可打开性，不作为版式真值；
- 源文件 hash 不变；
- 合成论文中的关键文本、表格、图片和必要对象未丢失、重复或错序；
- 目标学校的一个标题规则、一个正文规则和一个模板/占位符规则真实生效；
- Agent 修改前通过图片观察输入与模板，影响布局的修改后通过图片复核变化页和相邻页；
- Agent 最终分批观察当前 final.docx 的全部页面，每个 visual finding 都引用有效 evidence ref；
- `visual-review.json` 绑定最终文档 hash、render hash、Provider、字体和已审查页面，没有未解释的 blocking finding；
- 若只有 `iteration` 近似渲染，validation 和最终回复明确说明尚未通过 Microsoft Word 目标应用渲染门；
- Agent 没有调用五个 DocFit Tool 之外的写入能力；
- Tool 返回 `needs_input` 时，Agent 能根据证据重新 inspect；确需用户补充时调用 `AskUserQuestion`，由 CLI 的 `can_use_tool` 回调展示问题并继续同一 SDK 会话；
- Tool 返回 `error` 或 `committed: false` 时，Agent 不交付该产物；
- 最终回复中的产物、Knowledge 版本、验证摘要和 warning 与磁盘事实一致；
- 相同错误在输入、调用方式和 Provider 均未变化时不会无限重试。

M2 通过后，可以对外说明“DocFit 第一条论文转换链路已经跑通”，但不能说明已经达到真实论文交付质量或通过 Microsoft Word 最终兼容性门。

### 6.5 停止门

- Agent 能绕过 Tool 直接修改 DOCX；
- 页面图片只落盘但没有真正进入 Agent 上下文；
- 修改后继续使用旧截图，或没有复核受影响的相邻页面；
- 最终回复声称完成，但验证仍有未解释的 blocking issue；
- CLI 依赖开发者手工修改中间文件才能完成；
- 为了完成单个用例而把学校规则写进通用 Skill。

## 7. M3：达到可试用 MVP

### 7.1 目标

把“单个 smoke case 能跑”提升到“对代表性风险可重复、可回归，并允许受控真实试用”。

### 7.2 范围

- 建立 Tool test、Skill eval 和端到端 Eval 三层验证；
- 增加 1 个普通合成样本和 3–5 个单风险 fixture；
- 在授权或脱敏前提下引入 1 个结构复杂的真实样本；
- 把所有已发现缺陷变成自动断言；
- 建立人工 Word 高风险页面复核清单；
- 接入或通过受控流程调用一次面向 Microsoft Word 的 `release` 渲染链路；暂时无法自动化时，允许人工操作受控 Word 环境导出 PDF/逐页图片，但产物仍须形成可追溯的 release render ref；
- 在至少一个 Provider 上验证页面元素 bbox 映射对视觉问题定位和编辑目标选择的帮助；
- 记录调用数、解析缓存、渲染页数、耗时和失败归因；
- 只根据测量结果优化重复解析、重复渲染和低信息 Tool 返回。

### 7.3 验收标准

必需的确定性门：

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit eval --suite core
```

必需的本地与人工门：

- 五个 Tool 及主 Provider 的契约测试全部通过；
- 核心 Skill eval 全部通过；
- 当前学校端到端样本全部通过；
- 没有内容静默丢失、结构破坏或源文件覆盖；
- Provider 伪成功、失效引用、跨 run 占位符、复杂对象、字体/渲染差异和视觉审查旧证据误用都有回归用例；
- Agent 能在 Eval 中发现封面溢出、意外空白页、孤行和图表错位等代表性视觉问题；
- 至少一份授权或脱敏真实论文完成 Microsoft Word 目标环境渲染、全部页面 Agent 视觉审查与高风险页面人工检查；
- release render ref 声明 `fidelity_claim: target_application`，并与最终文档、字体和页面图片正确绑定；
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

## 8. M4：学校 Knowledge 建设闭环

### 8.1 目标

在转换链路稳定后，实现 `prepare-school-template`，让新学校资料能够形成可复用、可追溯、可验证的 Knowledge 包。

### 8.2 范围

- 实现 `.claude/skills/prepare-school-template/SKILL.md`；
- 复用 `docx_inspect` 和现有学校提取经验；
- 使用 `docx_render` 与 `docx_visual_review` 检查模板页面、槽位、固定内容和说明文字；
- 固化 `manifest.yaml` 和 `format-profile.yaml` schema；
- 保存来源、hash、适用范围、冲突和人工确认记录；
- 为新学校生成代表性 Eval；
- 保留 Agent 判断与确定性 Tool 的边界。

### 8.3 验收标准

- 一组官方材料可以生成结构完整的候选 Knowledge 包；
- 每条重要规则能够追溯到来源或人工确认；
- 精确格式值具有明确单位、类型和适用范围；
- 文字要求与模板表现冲突时，两份证据都被保留；
- 未确认推断不会被写成确定规则；
- Knowledge 包能通过 schema、digest、来源和模板结构检查；
- 该包能够被 `convert-thesis` 消费并通过至少一个端到端 Eval；
- 新学校加入后，首个学校的核心回归仍通过；
- Skill 之间没有复制模板提取规则或直接互相调用。

### 8.4 停止门

- 新学校只能通过修改通用 Skill 代码接入；
- 自动提取结果未经来源检查或人工确认就升级为正式 Knowledge；
- 为管理少量学校提前建设检索服务、发布平台或数据库。

## 9. M5：按真实需求产品化与优化

M5 不是首个 MVP 的前置条件。只有真实使用数据证明需要时，才按独立需求进入：

- 打包和发布 CLI；
- API、GUI 或多用户入口；
- 第二 Provider 与回退策略；
- 容器化、任务隔离、资源配额和正式密钥管理；
- Knowledge 检索或学校资产管理；
- 并发 Eval、性能基线和缓存优化；
- 自动化、可扩展的 Microsoft Word 交付渲染和人工复核工作台。

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
| M2 | 一条 `docfit convert` 命令 | 第一条论文转换链路已跑通 | 已达到真实交付质量或通过 Word 最终兼容性门 |
| M3 | 核心 Eval 与真实样本复核 | 可受控试用 MVP | 已覆盖所有学校和长尾情况 |
| M4 | 新学校 Knowledge 包 | 学校资产建设和转换形成闭环 | 已需要平台化学校管理 |
| M5 | 按需求增加的产品能力 | 对应能力已产品化 | 可以跳过证据直接扩平台 |

## 11. 可迭代性的最低保证

项目达到 M2 时，必须已经具备以下扩展接口，而不是等以后重构：

- **Tool 契约稳定**：Agent 只依赖五个版本化 Tool schema，不依赖 Provider 私有接口；
- **视觉证据可追溯**：每张送入 Agent 的图片都绑定文档、render、Provider、字体、页码和图片 hash；
- **渲染角色可扩展**：同一个 Tool 契约区分 `iteration` 与 `release`，近似结果不能升级成目标应用事实；
- **视觉定位可增强**：layout map 作为可选渲染产物绑定 opaque `object_ref`，后续增加 bbox 能力不修改 Skill 或 Tool 名称；
- **Provider 可替换**：Tool 结果包含 Provider 与环境证据，但第一版不提前建设多 Provider 平台；
- **Knowledge 可版本化**：学校事实与 Skill 分离，包具有来源、适用范围和 digest；
- **Skill 可独立迭代**：Skill 文件和 references 可以在不修改 Tool 实现的情况下演进；
- **失败可回归**：每个重要缺陷都有 fixture 和对应层级的断言；
- **应用壳保持薄**：CLI 只配置 SDK、输入、权限和输出，不包含论文语义；
- **真实数据可隔离**：任务工作目录、输出、缓存与日志有明确权限和生命周期；
- **公共命令稳定**：Provider 或内部解析器替换后，`docfit convert` 的用户契约保持不变。

如果为了“以后可能需要”新增基类、服务、状态表、事件总线、数据库或发布系统，而当前只有一个消费者，应拒绝该抽象。

## 12. 总体验收与执行契约

### 12.1 “项目已经跑起来”

只有 M0、M1、M2 全部通过，且公共 `docfit convert` 命令在真实 SDK 与主 Provider 下完成合成 smoke case，才满足当前最主要目标。

### 12.2 “项目易于后续迭代”

同时满足以下条件：

- Tool、Knowledge、Skill 和应用壳边界与 01 一致；
- 新 Provider 不要求修改 Skill；
- 新学校不要求修改通用 Tool 协议；
- 新缺陷可以被放入明确的测试或 Eval 层；
- 新开发者可以从 README 找到安装、测试、smoke 和常见失败处理；
- 首个垂直切片没有引入当前不需要的 runtime 组件。

### 12.3 Preflight contract

```text
Preflight status: EXECUTED_M0_VERIFIED
Task source: docs/docfit-00-index.md + docs/docfit-01-architecture-core.md + user goal
Canonical source: docs/docfit-06-development-roadmap.md
Route: durable $intuitive-flow
Goal: 只完成 M0，建立可安装、可测试、权限受限并能完成真实 SDK 图片 smoke 的开发底座。
Scope: .python-version、pyproject、uv.lock、CLI、doctor、SDK 接入、仓库外统一 Agent 环境文件、Kimi→MiniMax backend 顺序、Skill 发现、五个 Tool 名称、图片 smoke、权限测试、最小 CI、迁移资产清单。
Non-goals: 所有真实 DOCX Tool 实现、Provider 选型、学校 Knowledge、convert 端到端链路，以及 M1–M5。
Entity budget: reuse=现有 Skills、DOCX 脚本和 Claude Agent SDK 原生 Skill/MCP/图片/用户输入能力；new=Python 包、CLI、权限配置、M0 smoke、最小测试与 CI；remove/merge=不复制 SDK 会话或问答协议，不创建 Provider 抽象和真实 DOCX 实现。
Context: must-read=docs/docfit-01-architecture-core.md, docs/docfit-06-development-roadmap.md; useful=docs/docfit-04-skills-design.md, docs/docfit-05-tools-and-data-design.md, 现有 convert-thesis 与学校提取资产；avoid-unless-needed=M1–M5 实现细节、旧工作流设计与未验证平台化方案。
Unknown-unknown scout: skipped；M0 是边界明确的 SDK/CLI 开发底座，未知项通过官方 SDK 契约、确定性测试和三个 live smoke 直接暴露，不需要在实现前扩展产品范围。
Success: M0 的确定性门和本地产品门全部通过。
Result: DONE；2026-07-31 目录归属收口后，Kimi 已完成图片、
AskUserQuestion 与拒绝工具 smoke；三个回执均匹配 claude-agent-sdk 0.2.128，
docfit doctor --require agent-smoke 返回 0。
No regressions: 未匹配工具默认拒绝，Agent 不能访问任务目录外文件或网络，应用壳不解释 needs_input，日志不写入论文正文。
Verification: deterministic=uv sync --frozen + ruff + mypy + pytest + docfit doctor；local-live=三个 agent-smoke case + docfit doctor --require agent-smoke。
Execution: main=主会话实现并监督 M0 阶段门、范围与最终判定；worker=none；worker-goal=none。
Execution stop: M0 验收后停止，不自动进入 M1；根据 M0 证据生成并审批 M1 Preflight。
To execute: /goal execute docs/docfit-06-development-roadmap.md with intuitive-flow
Optional tracking: none
Approval: LGTM/approve/go ahead 只批准 M0；edits request revision。
```
