# DocFit 测试与迭代（02）

> 状态：最终方案
> 日期：2026-08-01
> 前提：测试与 Eval 是开发系统，不进入正常论文转换的运行路径。

## 1. 目标

测试与 Eval 只解决三个问题：

1. 五个 DocFit Tool 及 OfficeCLI、本地 Word API 各自承担的能力是否可靠；
2. Skill、Knowledge 和 Tools 的组合能否完成代表性论文转换；
3. 一次修改是否修复目标问题，同时没有破坏已知正确行为。

DocFit 不建设通用评测平台。测试发现、并发、报告和 CI 使用现成测试框架；项目只维护论文领域的 fixture、样本和断言。

代码测试目录固定为：

- `tests/unit/`：不依赖 SDK 或真实 Provider 的纯逻辑测试；
- `tests/contract/`：五个公开 Tool 契约、固定路由，以及两个后端各自职责范围内的契约测试；
- `tests/integration/`：真实 SDK、OfficeCLI、本地 Word API、CLI 和端到端集成测试。

## 2. 三类验证

### 2.1 Tool tests

Tool tests 不调用 Agent，直接验证 `docx_inspect`、`docx_edit`、`docx_render`、`docx_visual_review`、`docx_validate` 的公开契约，以及 OfficeCLI、本地 Word API 的薄适配。

两个后端不需要通过一套假想的可互换 Provider 契约。OfficeCLI 只通过 inspect、
edit、validate 和高频截图的职责契约；本地 Word API 只通过分页基线、必要时
重新分页和最终 PDF 导出的职责契约。共同稳定的是五个公开 Tool 及其证据、错误
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
- 渲染缓存按输入 hash、Provider 版本、字体和参数正确命中与失效；
- `docx_render` 对 `iteration` / `release`、fidelity claim 和目标应用的声明符合 Provider 能力，暂不支持的 `release` 请求不会静默降级；
- 固定路由矩阵生效：`edit_feedback` 只走 OfficeCLI，`baseline_pagination` / `pagination_recheck` / `final_verification` 只走本地 Word API；非法 purpose/reason 组合被拒绝；
- Agent、Skill 或应用壳无法注入后端选择；任一固定后端失败时不会跨职责静默回退；
- target-application 初始分页基线、CLI 编辑反馈和最终复核能够用稳定的 render reason 区分，而不增加第三种 `render_purpose`；
- 页码只在对应 render ref 内有效，不同后端的同页码不会被自动关联；同一文档 hash 的页面元素可通过当前快照的 `object_ref`、节引用或文字锚点关联，文档 hash 变化后旧 ref 被拒绝；
- 页面元素映射的坐标系、页码、bbox、mapping quality 和 opaque `object_ref` 与当前 render 一致；
- `docx_visual_review` 只接受当前任务的有效 render ref，并返回与文档、页码和图片 hash 绑定的图片 content block；
- 整页、裁剪、contact sheet 和 compare 模式的图片变换、页码、候选对象和元数据一致；
- 修改后的文档不能继续使用旧 render ref 证明视觉结果；
- 单次图片页数和字节上限生效，Tool 不返回视觉 `pass` / `fail` 判断；
- 验证从源文件与最终文件重新读取事实；
- 占位符、有效格式、内容对象、package 关系、视觉审查覆盖和渲染警告返回清晰结果；
- 超时、字体缺失、文件锁定和不支持对象都有可行动的错误。

Tool test 的基本标准是确定性、可重复、源文件只读、失败不产生伪成功产物。

### 2.2 Skill eval

Skill eval 使用固定任务、产品内置 Knowledge、当前任务学校材料和受控 Tool 结果，观察 Agent 是否：

- 触发正确 Skill；
- 读取随当前产品发布的通用 Knowledge 版本；
- 只从当前任务模板、要求、示例和用户确认中形成学校事实；
- 不把当前任务提取出的学校规则、模板或精确参数写入长期 Knowledge；
- 使用 Tool 提供的事实，不直接猜测文档结果或修改 OOXML；
- 修改前观察输入与模板页面图片，影响布局的修改后复核变化页和相邻页；
- 分页敏感且目标应用渲染可用时，修改前建立输入与模板的目标应用分页基线；不可用时保留明确的能力缺口；
- 把目标应用页面当作视觉观察窗口而不是编辑身份，不用 Word 第 N 页直接定位近似 Provider 第 N 页或驱动 `docx_edit`；
- 修改过程中使用低延迟 CLI 渲染观察受影响对象及邻近页面，只有分页基线明确失效时才请求目标应用重新分页；
- 最终分批观察当前文档的全部页面，并把 visual finding 绑定到 evidence ref；
- 不把旧截图、近似渲染或结构检查当作当前页面已经视觉合格；
- 使用元素映射缩小编辑目标时仍验证 `object_ref` 前置条件，不把 bbox 当成 OOXML 定位器；
- 区分迭代近似渲染和 Microsoft Word 目标应用渲染，没有 release 证据时保留 `verification_gap`；
- 只提交 render purpose 与 reason，不选择具体后端；本地 Word API 失败时不把 OfficeCLI 预览当作最终真实性证据；
- 保护学生内容，选择破坏最小的修改方式；
- 根据错误语义重新 inspect、缩小范围、修复固定后端调用、询问或停止，不把后端切换当作首版恢复策略；
- 不消费 `committed: false` 或未通过后置检查的文件；
- 不在没有新证据时循环重试；
- 相同文档 hash 与相同渲染策略不重复调用目标应用渲染；同一份可变论文通常只建立一次初始基线并执行一次最终复核，只有分页基线失效时允许额外重新基线；学校模板基线按模板 hash 独立缓存；
- 在最终答复中如实说明产物、验证结果和未解决问题。

Skill eval 以可观察结果为主。除安全底线和必要先后关系外，不要求 Agent 复现固定工具调用序列。

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

- 最终 DOCX 存在、能打开且不要求 Word 修复；
- 源文件未变化；
- 支持范围内的学生内容和对象仍存在且顺序正确；
- 目标学校关键格式断言满足；
- 必填模板内容或槽位已处理；
- 不应出现的占位符和说明文字已清理；
- PDF 或页面预览可生成；
- render ref 明确记录 purpose、fidelity claim、Provider、字体和可选元素映射；
- 同一文档 hash 的目标应用与 OfficeCLI 页面证据通过当前对象引用或锚点关联；跨编辑快照先重新 inspect，再通过新旧节、文字锚点或显式内容指纹对照，不假设相同页码表示相同内容范围；
- `docx_visual_review` 返回的图片实际进入当前 Agent 上下文；
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
| Word 与 CLI 页数或分页边界不同，相同页码不能直接对应 | 是 | 是 | 是 |
| 近似渲染被错误标成 Microsoft Word 最终事实，或 release 请求被静默降级 | 是 | 是 | 是 |
| render reason 被路由到错误后端，或固定后端失败后发生静默跨职责回退 | 是 | 是 | 是 |
| 页面元素 bbox 能定位到当前快照对象，失效或低可信映射不会驱动错误修改 | 是 | 是 | 是 |
| 大范围版式修改使初始 Word 分页基线失效，Agent 重新取证而不沿用旧页码 | 是 | 是 | 是 |
| 封面溢出、意外空白页、孤行和图表错位能被视觉审查发现 | 是 | 是 | 是 |
| 修改后错误复用旧截图或漏审相邻页 | 是 | 是 | 是 |
| 学校文字要求与模板表现冲突 |  | 是 | 是 |

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

- 1 个可公开的正常学生样本；
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
| App/SDK integration | 输入、权限、路径或 SDK 配置错误 | 薄应用壳 |

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
2. 核心 Skill eval 通过；
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
- 目标应用渲染调用数、缓存命中数、初始基线/重新基线/最终复核的原因分布；
- 按 Skill、Knowledge、Tool、Eval、App 的失败分布。

指标用于发现趋势，不成为新的运行时状态体系。
