# DocFit 测试与迭代（02）

> 状态：最小 Eval 设计
> 日期：2026-07-30
> 前提：Eval 是开发系统，不进入正常论文转换的运行路径。

## 1. 目标

测试与 Eval 只解决三个问题：

1. 确定性模块、Tool Contract 和实际 Adapter 是否正确；
2. 当前 Skill、Knowledge 和 Tools 的组合能否完成代表性论文转换；
3. 一次修改是否修复了目标问题，同时没有破坏已知正确行为。

DocFit 不建设通用评测平台。测试发现、并发、报告和 CI 优先使用现成测试框架；DocFit 只维护论文领域的样本与断言。

## 2. 四层质量验证

四个层级按执行边界划分，不按文件类型划分：

| 层级 | 验证对象 | 是否调用 Agent | 主要位置 | 基本通过标准 |
|---|---|---:|---|---|
| L1 单元测试 | 纯函数、Schema、内部确定性模块 | 否 | `tests/unit/` | 全部确定性断言通过 |
| L2 Tool 契约与集成测试 | Tool Contract、Adapter、真实文档引擎 | 否 | `tests/integration/` | 契约、后置条件和失败语义全部通过 |
| L3 Skill Eval | Agent 是否按 Skill 完成业务目标 | 是 | `evals/skills/` | 关键 `must` / `must_not` 全部满足 |
| L4 端到端 Eval | 用户输入到最终可交付文件的完整链路 | 是 | `evals/e2e/` | 自动审计通过，规定的人工验收完成 |

L1 和 L2 判断确定性代码及工具是否正确；L3 和 L4 判断 Agent 产品是否正确。低层失败必须先修复，不能靠高层重试掩盖。

### 2.1 L1：单元测试

#### 边界

L1 不启动 Claude Agent SDK，不调用外部 Office 进程，也不依赖网络。它验证可以快速、稳定运行的纯逻辑和内部模块：

- `SchoolKnowledgeDraft` / `SchoolKnowledgePackage` Schema；
- digest 计算和规范化；
- `source_ref` 格式与引用完整性；
- `DocumentObjectRef` 指纹和过期判断；
- 格式值归一化；
- 冲突、不确定项和 provenance 的保留；
- Tool 错误包的构造与分类；
- Knowledge manifest 的适用范围与版本校验。

#### 通过标准

- 相同输入必须得到相同结果；
- 不依赖测试执行顺序；
- 不读取开发者机器上的隐式状态；
- 每个失败都能定位到一个确定性模块；
- 全部测试通过，不接受随机失败；
- 单个用例使用最小 fixture，能够在本地快速重复执行。

#### 首批用例

| 用例 ID | 输入或场景 | 核心断言 |
|---|---|---|
| `l1-digest-001` | 内容相同、文件路径不同的来源集合 | `source_digest` 相同 |
| `l1-source-ref-001` | 指向不存在对象的规则 | Draft 校验失败，不能静默接受 |
| `l1-draft-conflict-001` | 两份来源给出冲突字号 | 两条证据都保留，冲突进入 `conflicts` |
| `l1-object-ref-001` | 文档修改后复用旧指纹 | 识别为 stale reference |
| `l1-package-scope-001` | 缺少年份或适用范围的 Package | 发布校验失败 |

### 2.2 L2：Tool 契约与集成测试

#### 边界

L2 不启动 Agent，但通过公开 `Tool Contract` 调用真实 Adapter 和文档引擎。它验证 `docx_inspect`、`docx_edit`、`docx_render`、`docx_validate`，以及它们依赖的开源或自研 Provider。

同一个 `Tool Contract` 可以对应多个实现。每个 Adapter 必须通过同一套 conformance tests，这样可以替换底层实现，而不修改 Skill、Knowledge 或 Eval 断言。

#### 通过标准

- 输入、成功输出和失败输出都符合 Schema；
- 原文件保持不变，成功产物发布到新位置；
- 写入采用临时文件和原子发布，失败不残留伪成功产物；
- 成功返回前必须重新打开输出并验证预期效果；
- 非目标内容没有被修改、丢失、重复或错序；
- 第三方 locator 能映射到 `DocumentObjectRef`，过期引用会被拒绝；
- `origin`、`stage`、`code`、`retryable`、`committed` 准确；
- Provider 报告成功但后置条件失败时，Tool 必须返回失败；
- 超时、崩溃、字体缺失和不支持对象都有结构化错误；
- 记录实际 `provider` 和 `provider_version`；
- 测试固定 Provider 版本、超时和临时工作目录。

#### 首批用例

| 用例 ID | 输入或场景 | 核心断言 |
|---|---|---|
| `l2-inspect-structure-001` | 含正文、表格、图片、公式、页眉的 DOCX | 返回稳定对象引用和完整能力声明 |
| `l2-edit-atomic-001` | 修改一个标题样式 | 原文件不变，输出可重开，只改变目标对象 |
| `l2-edit-stale-ref-001` | 使用过期 `DocumentObjectRef` | 安全失败，`committed=false` |
| `l2-edit-false-success-001` | Provider 返回成功但输出损坏 | 后置条件捕获并返回 `origin=postcondition` |
| `l2-render-font-001` | 渲染环境缺少必要字体 | 返回可诊断错误，不伪造预览成功 |
| `l2-validate-findings-001` | 文档存在占位符和错误标题级别 | Tool 调用成功，问题进入 `findings` 而非 Tool error |

### 2.3 L3：Skill Eval

#### 边界

L3 启动 Claude Agent SDK，给 Agent 固定的任务、Skill、Knowledge 和受控 Tool 环境，验证它是否按业务目标工作。Tool 可以使用固定 fixture 或故障注入，以稳定验证 Agent 的选择和恢复行为；真实引擎正确性由 L2 负责，完整交付效果由 L4 负责。这里不比较隐藏思考过程，只检查可观察行为、最终结果和关键约束。

共享模板提取协议的语义验证也属于 L3：确定性解析由 L1/L2 保证，Agent 如何从证据形成 `SchoolKnowledgeDraft` 由 L3 保证。

允许的行为断言只有：

```text
must       必须发生，例如读取学校 Knowledge
must_not   禁止发生，例如覆盖源文件
before     必要先后，例如修改前先检查输入
limit      成本或重复调用上限
```

#### 通过标准

- 正确区分并触发 `prepare-school-template` 与 `convert-thesis`；
- 两个 Skill 复用同一套模板提取协议和 Draft Schema；
- 有正式 Knowledge 时优先复用，摘要不匹配时不误用；
- 学生临时上传的模板只形成任务级 Draft，不自动发布；
- 必要时调用 Tool 或询问用户；
- Tool 失败后按错误语义重试、换 Provider、降级或停止；
- 不使用 `committed=false` 的产物，也不无变化地循环重试；
- 不把 validation findings 误报成 Tool 崩溃；
- 最终回复如实描述产物、未解决问题和失败状态；
- 所有关键 `must` / `must_not` 断言通过。

两个 Skill 的结果重点不同：

| Skill | 主要断言 |
|---|---|
| `prepare-school-template` | 正确消费 Draft，补全适用范围、版本、来源检查和人工确认信息，形成可复用正式 Knowledge |
| `convert-thesis` | 正确复用已有 Knowledge 或把 Draft 限定在当前任务，最终 DOCX 可打开、学生内容保留，最终回复引用真实产物与验证结果 |

#### 首批用例

| 用例 ID | 输入或场景 | 核心断言 |
|---|---|---|
| `l3-prepare-conflict-001` | 官方模板与要求文件存在冲突 | 生成带来源、冲突和不确定项的 Draft，等待审核后才发布 |
| `l3-convert-package-001` | 学生论文 + 学校标识，已有正式 Package | 只加载 `convert-thesis` 并复用匹配 Knowledge |
| `l3-convert-temp-template-001` | 学生论文 + 用户模板 | 使用共享协议生成临时 Draft，不注册长期资产 |
| `l3-tool-retry-001` | 首选 Provider 返回 retryable 错误 | 在预算内重试或切换 Provider，并记录恢复结果 |
| `l3-tool-stop-001` | 编辑后置条件失败 | 拒绝使用失败产物，停止或请求处理，不宣称完成 |

### 2.4 L4：端到端 Eval

#### 边界

L4 从真实用户输入开始，经过 Claude Agent SDK、Skill、Knowledge、实际 Tool Provider、渲染和验证，直到生成最终可交付文件和用户回复。

#### 通过标准

- 最终 DOCX 存在、可打开，原文件保持不变；
- 支持范围内的文字、图片、表格和公式不丢失、不重复、不错序；
- 学校格式要求和内容零丢失要求通过自动审计；
- 不存在模板占位符或未解释的高严重度 findings；
- 预览产物存在，关键页面完成视觉检查；
- Tool 错误没有被隐藏或误报为成功；
- 最终回复与真实产物和验证报告一致；
- 封面、目录、目录页码、分页、页眉页脚等规定项目完成人工验收。

端到端 Eval 不要求在线产品生成 delivery state、Verifier verdict 或 Run Bundle。

#### 首批用例

| 用例 ID | 输入或场景 | 核心断言 |
|---|---|---|
| `l4-public-basic-001` | 公开基础论文 + 已验收学校 Package | 生成可交付 DOCX、预览和验证报告 |
| `l4-complex-doc-001` | 含复杂表格、图片、公式和分节的论文 | 内容完整，特殊对象与分页未被破坏 |
| `l4-temp-template-001` | 学生论文 + 临时用户模板 | 完成本次转换，不污染正式 Knowledge |
| `l4-package-digest-001` | 上传模板与已有 Package digest 匹配 | 正确复用资产，输出满足同一规则 |
| `l4-adversarial-001` | 已知高风险真实文档 | 不崩溃、不静默丢内容，失败时如实给出证据 |

### 2.5 用例归层原则

- 一个问题优先放到能够稳定复现它的最低层；
- 纯逻辑错误不通过 L3/L4 间接验证；
- Agent 决策错误不塞进 Tool test；
- 对内容丢失、源文件覆盖等交付级高风险问题，可以同时保留低层根因测试和一个 L4 回归用例；
- 不要求同一个场景机械复制到四层。

## 3. 用例格式

L1/L2 使用项目测试框架直接编写，至少包含：

- 用例 ID；
- fixture 或输入构造；
- 前置条件；
- 操作；
- 精确断言；
- 预期错误和副作用；
- 所属风险。

L3/L4 使用声明式 Eval case，便于固定输入、版本和结果断言。一个用例保持小而自包含：

```yaml
id: l4-hunannongye-basic-001
level: L4
skill: convert-thesis
task: 将学生论文转换为湖南农业大学格式
inputs:
  document: input/student.docx
  school_knowledge:
    id: hunannongye
    version: v1
    content_digest: sha256:...
assertions:
  - final_docx_opens
  - source_file_unchanged
  - required_text_preserved
  - no_template_instruction_text
  - required_styles_match
manual_review:
  - cover_page
  - toc_pagination
```

每个 Eval case 固定：

- 质量层级；
- 输入文件；
- 目标 Skill；
- Knowledge 版本；
- Knowledge content digest；
- 结构化期望；
- 少量人工确认的参考产物；
- 失败说明。

每次 Eval 运行只记录用于复现和归因的最小版本元数据：

```yaml
model: ...
sdk_version: ...
skill_revision: ...
tool_revision: ...
tool_engines:
  inspect_edit: officecli@...
  render: libreoffice@...
knowledge_digest: sha256:...
code_revision: ...
```

这些字段不是完整环境胶囊或运行时指纹，不记录固定 Agent 轨迹，也不支持 replay。

## 4. 样本组合

第一阶段只维护能够推动实现的最小集合：

- 1 个可公开的正常学生样本；
- 1 个真实结构复杂样本；
- 3–5 个由真实失败提炼的对抗样本；
- 1 个目标学校 Knowledge 包。

优先覆盖：

- 删除一段并重复另一段；
- 表格内图片或公式；
- 模板说明文字跨多个 Word run；
- 目录被误当正文；
- 缺失必要字段；
- 字体缺失或渲染失败；
- 学校要求与模板表现冲突。

第二所学校加入后，增加跨学校回归，用来发现通用 Skill 是否混入首校知识。

L1/L2 确定性测试单次运行即可。对于内容丢失、模板误删等高风险 L3/L4 Agent 用例，可在基线建立或行为波动时重复运行并记录稳定性；具体次数由 Eval 配置决定。

## 5. 结果比较

按数据类型选择最简单的比较方式：

| 类型 | 比较方式 |
|---|---|
| 原始输入、Knowledge 文件 | hash 或 exact |
| 结构化分析结果 | 忽略时间戳后的 normalized compare |
| 对象集合 | set compare |
| 字号、页边距、坐标 | tolerance |
| Agent 判断与最终论文 | 关键事实断言 |
| 页面视觉 | 人工复核，必要时加图像差异辅助 |

避免整份 DOCX 逐字节比较，也避免把一条完整 Agent 路径当成 Gold。

## 6. 失败归因

失败后只定位到可行动的资产：

| 归因 | 典型问题 | 修复位置 |
|---|---|---|
| Agent / Skill | 选择错误目标或动作、忽略 Tool 证据、重复不可重试调用 | Skill 资产或 Skill eval |
| Knowledge | 学校事实、模板或示例错误 | `knowledge/` |
| Tool contract / adapter | 错误分类、映射、后置检查或原子发布实现错误 | Tool adapter |
| Third-party engine | MCP、CLI、库或渲染器崩溃、误报成功或版本退化 | 依赖配置、provider 选择或上游修复 |
| Environment | 文件锁、字体、权限、依赖或渲染环境问题 | App 配置或运行环境 |
| Eval | 断言错误、样本失效或漏测 | `evals/` |
| App/SDK integration | 输入、权限、路径或 SDK 配置错误 | `app/` |

归因以 adapter 记录的请求校验、引擎结果和独立后置检查为证据，不能只相信第三方的成功声明，也不能只根据 Agent 最终回复推断。

一次失败可以涉及多个问题，但修复时应分别落到对应资产。不要用新的工作流层来吸收定位困难。

## 7. 迭代闭环

```text
真实任务或 Eval 失败
  → 保存最小复现
  → 判断属于 Skill / Knowledge / Tool / Eval / App
  → 修复对应资产
  → 为该问题增加断言
  → 运行相关用例和核心回归
  → 合入
```

每个重要修复至少留下一项自动化资产：

- Tool bug：单元、适配器契约或第三方版本回归测试；
- Skill bug：Skill eval；
- Knowledge bug：学校用例；
- 端到端漏检：结果断言或人工复核清单。

## 8. 发布门槛

早期版本按四个质量层级设置门槛：

1. L1：纯逻辑、Schema、引用、digest 和错误分类测试全部通过；
2. L2：四个核心 Tool 及当前启用 Adapter 的契约、后置条件和失败语义测试全部通过；
3. L3：核心 Skill Eval 的 `must` / `must_not` 全部通过，错误恢复结果与实际状态一致；
4. L4：当前学校端到端样本通过且无内容丢失，高风险样例完成人工 Word 关键页面检查。

人工检查是 L4 的组成部分，不是独立的第五层。

基线尚小时，逐例看失败比建立统计平台更有价值。等用例数量和运行成本真实增长后，再选择并发 runner、实验平台或 trace UI。

## 9. 最小指标

每轮只记录：

- L1 / L2 测试通过数与失败用例；
- L3 Skill Eval 通过数 / 总数；
- 端到端用例通过数 / 总数；
- 严重内容丢失或结构破坏次数；
- 需要人工澄清的任务比例；
- 平均每个任务的工具调用数和耗时；
- 高风险 Agent 用例的重复运行通过数；
- 按 Skill / Knowledge / Tool / Eval / App 的失败分布。

指标用于发现趋势，不成为新的运行时状态体系。
