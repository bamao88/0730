# DocFit 测试与迭代（02）

> 状态：最终方案
> 日期：2026-08-03
> 前提：测试与 Eval 是开发系统，不进入正常论文转换的运行路径。

本文件保留长期 Eval 设计。当前开发范围只要求 M0–M2 的单元、契约、集成和 live
产品门；M3 Skill/E2E Eval 扩展、真实样本资格验证、Gold 与人工交付复核已延期，需
新的用户批准计划。已经存在的 core runner 和 fixture 可以继续作为可选开发资产，
但不作为当前产品开发完成门。

## 1. 目标

测试与 Eval 只解决三个问题：

1. 五个 DocFit Tool 及 OfficeCLI、Adobe PDF Services API 各自承担的能力是否可靠；
2. 两个领域 Skill、模块化 Knowledge、可选只读 Subagent 和 Tools 的组合能否完成
   代表性模板提取与论文转换；
3. 一次修改是否修复目标问题，同时没有破坏已知正确行为。

DocFit 不建设通用评测平台。测试发现、并发、报告和 CI 使用现成测试框架；项目只维护论文领域的 fixture、样本和断言。

代码测试目录固定为：

- `tests/unit/`：不依赖 SDK 或真实 Provider 的纯逻辑测试；
- `tests/contract/`：五个公开 Tool 契约、固定路由、SDK Subagent 权限/上下文边界，
  以及两个后端各自职责范围内的契约测试；
- `tests/integration/`：真实 OfficeCLI、CLI 与薄转换壳集成测试；真实 SDK 和 Adobe API
  使用仓库外凭据作为独立 live 产品门，不混入默认 pytest。

当前最小 Eval 实现位于 `src/docfit/evals/` 与 `evals/`：专用 Python builder 生成一个
普通合成案例和四个单风险 DOCX，JSON case 描述第五个 Provider 伪成功风险、三个
Skill 范围及一个合成端到端合同。`docfit eval --suite core` 只运行确定性 Tool、Skill
静态边界和薄应用合同回归，并把调用数、页数、耗时和失败归因写入忽略版本控制的
`.docfit/evals/core/latest.json`。它明确不运行真实 SDK、Adobe official-service conversion、
授权/脱敏真实样本或人工复核；这些门必须单独留下实际证据。

## 2. 三类验证

### 2.1 Tool tests

Tool tests 不调用 Agent，直接验证 `docx_inspect`、`docx_edit`、`docx_render`、`docx_visual_review`、`docx_validate` 的公开契约，以及 OfficeCLI、Adobe PDF Services API 的薄适配。

两个后端不需要通过一套假想的可互换 Provider 契约。OfficeCLI 只通过 inspect、
edit、validate 和高频截图的职责契约；Adobe PDF Services API 只通过分页基线与候选验证
PDF 导出的职责契约。共同稳定的是五个公开 Tool 及其证据、错误
与安全语义。

重点覆盖：

- DOCX 能正确打开、无操作另存和重新打开；
- 段落、表格、合并单元格、图片、公式、脚注尾注、文本框、域、内容控件、页眉页脚和编号能够被发现；
- 样式继承、直接格式和最终生效值能够正确解析；
- 原始 run 与逻辑文本之间的字符映射正确；
- 不支持的可见对象被明确报告；
- 对象引用绑定输入 hash，失效引用被安全拒绝；
- 跨 run 文本和占位符能被准确定位；
- 跨文档模板组合复制完整依赖闭包、重映射冲突 ID，并在任一操作失败时不发布部分结果；
- 一组编辑要么全部发布，要么全部不发布；
- 修改只影响目标对象，源文件保持不变；
- 可能漂移的多目标修改按安全顺序执行；
- Provider 报告成功但产物打不开或目标未变化时，Tool 返回失败；
- 编辑后从新文件重新取证，不相信 Provider 自报结果；
- 渲染缓存按输入 hash、Provider/SDK 版本、转换 profile、环境证据和参数正确命中与失效；
- `docx_render` 对 `baseline` / `edit_feedback` / `candidate_verification`、fidelity 和
  转换证据的声明符合 Provider 能力；
- Adobe baseline/candidate 固定为 `fidelity: official_service_conversion`，OfficeCLI
  feedback 固定为 `fidelity: approximate`；
- 固定路由矩阵生效：`edit_feedback` 只走 OfficeCLI，`baseline` 与
  `candidate_verification` 只走 Adobe PDF Services API；未知 intent 和任何后端选择参数被拒绝；
- Agent、Skill 或应用壳无法注入后端选择；任一固定后端失败时不会跨职责静默回退；
- Adobe 服务基线、CLI 编辑反馈和候选验证能够用稳定的 `render_intent` 区分；
- `baseline_render_ref` 被记录为新证据的 `parent_render_ref`，但旧页码和旧对象引用不会
  被当作当前文档事实；相同缓存键命中已有 render，不伪造新的 ref；
- `docx_render` 可以返回有大小限制的 contact sheet，让简单场景无需固定追加第二次
  Tool 调用即可开始观察；
- 页码只在对应 render ref 内有效，不同后端的同页码不会被自动关联；同一文档 hash 的页面元素可通过当前快照的 `object_ref`、节引用或文字锚点关联，文档 hash 变化后旧 ref 被拒绝；
- 页面元素映射的坐标系、页码、bbox、mapping quality 和 opaque `object_ref` 与当前 render 一致；
- `docx_visual_review` 只接受当前任务的有效 render ref，并返回与文档、页码和图片 hash 绑定的图片 content block；
- 五个公开 schema 不包含兼容 backend 会误解释的 `oneOf` / `anyOf` / `allOf`；动作
  专属必填关系由 Tool runtime 校验；
- SDK in-process MCP bridge 即使丢弃 `structuredContent`，Agent 可见的首个 text block
  仍是与完整结构化结果相同的 JSON；
- live smoke 的 CLI 集成测试只操作临时项目根；凭据或配置检查在任何 backend 可运行前
  返回 `NOT_READY` 时，不得删除此前真实 PASS 回执。只有确认存在可运行候选并开始新
  live 尝试后才先使旧回执失效；
- Tool 结果大小声明、SDK transport buffer 和视觉图片预算能够承载受控真实页面批次，
  不会在图片进入 Agent 前触发默认 1 MiB 消息截断；
- 整页、裁剪、contact sheet 和 compare 模式的图片变换、页码、候选对象和元数据一致；
- `docx_visual_review` 不调用 Adobe PDF Services API 或 CLI，不产生新的 `render_ref`；派生视图只产生
  visual evidence/image hash，多次读取同一 ref 不构成新一轮；
- 修改后的文档不能继续使用旧 render ref 证明视觉结果；
- 单次图片页数和字节上限生效，Tool 不返回视觉 `pass` / `fail` 判断；
- 验证从源文件与最终文件重新读取事实；
- 占位符、有效格式、内容对象、package 关系、视觉审查覆盖和渲染警告返回清晰结果；
- 超时、凭据缺失、额度耗尽、服务失败和不支持对象都有可行动的错误。
- Adobe 大文件上传使用固定且可测试的 connect/read timeout；真实上传超时仍返回
  安全 provider failure，不泄露 SDK 原始错误或凭据；
- 只读源文件权限不会被传播到临时编辑副本；同一 backend route 超时后不会仅因轮换
  credential 重复等待同一模型路由。

Tool test 的基本标准是确定性、可重复、源文件只读、失败不产生伪成功产物。

### 2.2 Skill eval

Skill eval 使用固定任务、产品内置 Knowledge、当前任务学校材料和受控 Tool 结果，观察 Agent 是否：

- 在模板提取与论文转换目标下分别触发 `docfit-school-extract` 或 `convert-thesis`；
- 读取随当前产品发布的通用 Knowledge 版本；
- 由当前 Skill 决定是否委派、如何划定分析范围、选择哪些 Knowledge 模块以及传递
  哪些任务证据；
- 在委派有收益时可以调用 `docfit-unit-analyst`，在简单、未匹配或复合范围中也可以
  直接或合并分析；
- 不使用固定页数、对象数、单元类型或其他复杂度阈值强制委派；
- 只把选中 Knowledge 模块及其 ID、版本、digest 和当前任务证据放入 Subagent
  任务包，不把父对话或无关模块当作已传递事实；
- 把 `status`、`confidence`、`evidence_requests`、`cross_unit_links` 和其他规定字段
  合并回主 Agent 判断；
- 在 Subagent 请求页面或其他证据时，由主 Agent 决定调用 render/inspect 并可选择
  再次委派，而不是让 Subagent 越权生成证据；
- 只从当前任务模板、要求、示例和用户确认中形成学校事实；
- 不把当前任务提取出的学校规则、模板或精确参数写入长期 Knowledge；
- 使用 Tool 提供的事实，不直接猜测文档结果或修改 OOXML；
- 修改前观察输入与模板页面图片，影响布局的修改后复核变化页和相邻页；
- 分页敏感且 Adobe 服务可用时，修改前建立输入与模板的服务转换分页基线；不可用时保留明确的能力缺口；
- 把 Adobe 页面当作视觉观察窗口而不是编辑身份，不用 Adobe 第 N 页直接定位近似 Provider 第 N 页或驱动 `docx_edit`；
- 修改过程中使用低延迟 CLI `edit_feedback` 观察受影响对象及邻近页面；当当前候选
  值得进行 Adobe 交付检查时请求 `candidate_verification`；
- 最终分批观察当前文档的全部页面，并把 visual finding 绑定到 evidence ref；
- 整页缩放不足以辨认小字、域结果或页边界细节时，继续读取绑定同一 render ref 的
  crop；可见应用错误标记、断裂域/交叉引用、未完成占位和截断内容必须作为 blocking
  finding 保留；
- 不把旧截图、近似渲染或结构检查当作当前页面已经视觉合格；
- 使用元素映射缩小编辑目标时仍验证 `object_ref` 前置条件，不把 bbox 当成 OOXML 定位器；
- 区分近似 `edit_feedback` 和 Adobe 官方服务转换；没有绑定当前文档且已被
  Agent 查看过的 candidate 证据时保留 `verification_gap`；
- 只提交 render intent，不选择具体后端；Adobe PDF Services API 失败时不把 OfficeCLI 预览
  当作最终真实性证据；
- 保护学生内容，选择破坏最小的修改方式；
- 根据错误语义重新 inspect、缩小范围、修复固定后端调用、询问或停止，不把后端切换当作首版恢复策略；
- 不消费 `committed: false` 或未通过后置检查的文件；
- 不在没有新证据时循环重试；
- 相同文档 hash 与相同渲染策略不重复调用 Adobe 转换；首次建立一次 baseline，上一
  candidate 可以作为下一 candidate 的 baseline ref，不额外调用 Adobe PDF Services API 制造轮次；
- 不把“第几轮”写入 Tool 状态或 Gold，也不把 baseline/candidate 的确切调用次数作为
  通用行为断言；只验证缓存、parent ref、后端路由和当前证据绑定；
- 在最终答复中如实说明产物、验证结果和未解决问题。

Skill eval 以可观察结果为主。除安全底线和必要先后关系外，不要求 Agent 复现固定工具调用序列。
也不把 Subagent 数量、调用顺序、并行/串行选择、论文单元枚举或“每个单元必须委派”
写成断言。复杂场景能够委派和简单场景允许不委派需要分别有代表性用例；二者都不能
升级成固定路线。

允许的行为断言只有：

```text
must       必须发生，例如读取产品内置 Knowledge 和当前任务学校材料
must_not   禁止发生，例如覆盖源文件
before     必要先后，例如修改前先检查输入
limit      成本或重复调用上限
```

不要保存或比较模型隐藏思维链。

### 2.3 End-to-end eval

端到端用例从用户任务开始，使用真实 Claude Agent SDK 配置和当前启用的 Tool Provider，验证：

- 最终 DOCX 存在、package 可独立解析且 OfficeCLI 可重新读取；
- 源文件未变化；
- 支持范围内的学生内容和对象仍存在且顺序正确；
- 目标学校关键格式断言满足；
- 必填模板内容或槽位已处理；
- 不应出现的占位符和说明文字已清理；
- PDF 或页面预览可生成；
- render ref 明确记录 intent、fidelity、Provider/SDK、转换 profile、环境可见性、parent ref 和可选元素映射；
- 同一文档 hash 的 Adobe 与 OfficeCLI 页面证据通过当前对象引用或锚点关联；跨编辑快照先重新 inspect，再通过新旧节、文字锚点或显式内容指纹对照，不假设相同页码表示相同内容范围；
- `docx_visual_review` 返回的图片实际进入当前 Agent 上下文；
- 如果使用 Subagent，`Agent` Tool 只启动 `docfit-unit-analyst`，其任务包只包含
  选中 Knowledge 与显式证据，返回结果可追溯到当前文档；
- `general-purpose`、未知 Subagent、Subagent 写入/渲染/验证/继续委派均被权限边界
  拒绝；
- 主 Agent 仍是跨范围依赖、证据生成、`docx_edit` 和最终发布的唯一所有者；
- 修改前、布局变化后和最终交付前的视觉审查证据绑定正确文档版本；
- 最终全部页面已经分批视觉审查，高风险页面完成规定的 Agent 与人工检查；
- `visual-review.json` 的 finding、页码和 evidence refs 与当前 render 一致；
- 没有被忽略的 blocking visual finding；
- validation 没有被忽略的严重错误；
- Agent 最终回复与实际产物一致。

端到端 Eval 不生成阶段状态、调用轨迹 Gold、运行胶囊或 replay 协议。

## 3. 首批场景

第一批样本应来自真实论文风险，而不是按内部模块凑数量。

| 场景 | Tool test | Skill eval | 端到端 |
|---|---:|---:|---:|
| 学校前置页与学生正文正确嫁接 | 是 | 是 | 是 |
| 模板旧目录不被当作学生正文 |  | 是 | 是 |
| 空附录标题不会吞掉相邻内容 |  | 是 | 是 |
| 中英文图题及图片关系保持 | 是 | 是 | 是 |
| 表格、合并单元格和跨页表格保持 | 是 |  | 是 |
| 跨 run 占位符和格式说明被清理 | 是 | 是 | 是 |
| 域、内容控件、脚注、文本框和图片不静默丢失 | 是 |  | 是 |
| 页眉页脚、编号和节属性正确保留或修改 | 是 |  | 是 |
| 对象引用因前次修改失效 | 是 | 是 |  |
| Provider 伪成功被后置检查拦截 | 是 | 是 |  |
| 渲染器或字体差异影响分页 | 是 | 是 | 是 |
| Adobe 与 OfficeCLI 页数或分页边界不同，相同页码不能直接对应 | 是 | 是 | 是 |
| 近似渲染被错误标成 Adobe 交付转换证据，或 candidate 路由被静默降级 | 是 | 是 | 是 |
| render intent 被路由到错误后端，或固定后端失败后发生静默跨职责回退 | 是 | 是 | 是 |
| 页面元素 bbox 能定位到当前快照对象，失效或低可信映射不会驱动错误修改 | 是 | 是 | 是 |
| 大范围版式修改后 Agent 生成新 candidate，并只把旧 baseline/candidate 用作显式 parent 对照 | 是 | 是 | 是 |
| 封面溢出、意外空白页、孤行和图表错位能被视觉审查发现 | 是 | 是 | 是 |
| 修改后错误复用旧截图或漏审相邻页 | 是 | 是 | 是 |
| 学校文字要求与模板表现冲突 |  | 是 | 是 |
| 复杂模板或论文范围可由通用只读 Subagent 分析 |  | 是 | 是 |
| 简单或不存在的单元不会被强制委派 |  | 是 | 是 |
| 复合前置结构可由主 Agent 直接或合并委派，不被塞入固定类型 |  | 是 | 是 |
| Subagent 缺少页面时请求证据，主 Agent 补证后可重新委派 |  | 是 | 是 |
| general-purpose、未知类型或 Subagent 写入尝试被拒绝 |  | 是 | 是 |

这些场景可以拆成最小合成 fixture，也可以组合进少量脱敏真实样本。

## 4. Eval case

一个用例保持小而自包含：

```yaml
id: hunannongye-basic-001
skill: convert-thesis
task: 将学生论文转换为湖南农业大学格式
inputs:
  document: input/student.docx
  knowledge_version: v1
  school_materials:
    - input/official-template.docx
    - input/official-requirements.pdf
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

用例可以附带输入、产品 Knowledge 版本、当前任务学校材料、结构化期望、少量人工
确认的参考产物和失败说明。学校材料是 Eval fixture，不是运行时 Knowledge。

## 5. 样本组合

第一阶段只维护能够推动实现的最小集合：

- 1 个可公开的合成正常论文样本；
- 1 个结构复杂的脱敏或授权样本；
- 3–5 个由真实失败提炼的单风险样本；
- 1 份随产品发布的通用 Knowledge Package；
- 1 组合成的当前任务学校材料；
- 1 组五个 Tool 的公共契约 fixture。

第二所学校加入后，增加跨学校回归，检查通用 Skill 是否混入首校知识。

## 6. 结果比较

| 类型 | 比较方式 |
|---|---|
| 原始输入、Knowledge 文件 | hash 或 exact |
| 结构化分析结果 | 忽略时间戳后的 normalized compare |
| 对象集合 | set compare |
| 字号、页边距、坐标 | tolerance |
| Agent 判断与最终论文 | 关键事实断言 |
| 页面视觉 | 人工复核，必要时加图像差异辅助 |

避免整份 DOCX 逐字节比较，也避免把一条完整 Agent 路径当成 Gold。

## 7. 失败归因

| 归因 | 典型问题 | 修复位置 |
|---|---|---|
| Skill | 领域判断、询问或工具使用指引错误 | `.claude/skills/` |
| Knowledge | 通用概念、识别方法、解释原则或处理模式错误 | 产品内置 Knowledge Package |
| 当前任务证据 | 学校材料缺失、来源冲突、适用范围或确认不足 | 当前任务输入、任务 fixture 或用户确认 |
| Tool | 解析、修改、渲染、图片证据传递、缓存或验证错误 | Tool 实现与 Adapter |
| Eval | 断言错误、样本失效或漏测 | `evals/` 或测试 fixture |
| App/SDK integration | 输入、路径、Subagent 类型白名单、工具隔离或 SDK 配置错误 | 薄应用壳 |

一次失败可以涉及多个资产，但不要用新的工作流层吸收定位困难。

## 8. 迭代闭环

```text
真实任务或 Eval 失败
  → 保存最小复现
  → 归因到 Skill / Knowledge / Tool / Eval / App
  → 修复对应资产
  → 为该问题增加断言
  → 运行相关用例和核心回归
  → 合入
```

每个重要修复至少留下一项自动化资产：

- Tool bug：单元或契约测试；
- Skill bug：Skill eval；
- Knowledge bug：通用方法单元测试或跨学校 Skill eval；
- 端到端漏检：结果断言或人工复核清单。

## 9. 发布门槛

早期版本只设四个门槛：

1. 五个 Tool 及当前启用 Adapter 的测试通过；
2. 两个核心 Skill 的结果与可选委派 eval 通过；
3. 使用当前任务学校材料的端到端样本通过且无内容静默丢失；
4. 人工打开最终 DOCX 并检查规定的高风险页面。

等用例数量和运行成本真实增长后，再选择并发 runner、实验平台或 trace UI。

## 10. 最小指标

每轮只记录：

- Tool 测试通过数与失败用例；
- Skill eval 与端到端用例通过数；
- 严重内容丢失或结构破坏次数；
- 需要人工澄清的任务比例；
- 每个任务的 Tool 调用数、解析缓存命中率、渲染页数、Agent 实际审查页数、图片输入字节数和耗时；
- Adobe 转换调用数、缓存命中数、baseline/candidate intent 分布和 parent ref 复用；
- 按 Skill、Knowledge、Tool、Eval、App 的失败分布。

指标用于发现趋势，不成为新的运行时状态体系。
