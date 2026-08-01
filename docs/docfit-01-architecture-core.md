# DocFit 架构总览（01）

> 状态：架构基线
> 日期：2026-08-01
> 核心路线：**Claude Agent SDK runtime + Skill + Knowledge + Tools + Eval + thin app**

## 1. 核心定位

DocFit 是一个使用 Claude Agent SDK 运行的论文格式处理 Agent。

它的产品价值不在于重新实现 Agent 调度，而在于沉淀五类论文领域资产：

```text
Skill       告诉 Agent 如何处理论文
Knowledge   提供跨学校共享的论文格式概念、方法、原则和处理模式
Tools       可靠地读取、修改、渲染和检查文档
Eval        判断这些资产的组合是否在变好
App         用尽可能薄的方式把它们交给用户
```

最重要的架构决定是：

> Claude Agent SDK 是 DocFit 的运行时边界。DocFit 不在 SDK 之上再建设一套工作流系统。

## 2. 产品原则

### 2.1 Agent-first

不同学生论文和学校模板存在大量长尾差异。Agent 应根据当前文件、Skill 指引、Knowledge 和工具结果动态决定下一步，而不是执行一张预先固化的阶段图。

文档中的“先检查、再修改、最后验证”是领域建议，不是运行时状态机。

### 2.2 Domain assets over framework code

一次真实失败应优先沉淀为：

- Skill 中更清楚的判断规则；
- Knowledge 中更清楚、经过跨任务验证的通用概念、识别方法或处理模式；
- Tool 中更可靠的确定性能力；
- Eval 中一个可重复的失败样本和断言。

除非这些位置都无法表达，不增加新的框架层。

### 2.3 Deterministic operations, adaptive decisions

Agent 负责语义判断，工具负责精确执行：

```text
Agent：这段是一级标题，应该使用学校规则 A
Tool：定位该段，应用规则 A，另存并返回检查结果
```

Agent 不直接拼写 OOXML；工具不自主决定某段是不是标题。

### 2.4 Knowledge is a universal domain asset

Knowledge Package 是随产品发布、面向所有学校和任务共享的通用论文格式领域资产。
它提供统一概念、识别方法、解释原则和通用处理模式，帮助 Agent 从当前任务材料
中理解并推导具体规则。学校专属要求、模板、格式参数和任务结论不属于 Knowledge。

### 2.5 Eval is outside the product runtime

Eval 用于开发、回归和版本比较。用户运行一次论文转换时，不需要启动一个评测平台，也不需要生成复杂的 Gold、阶段胶囊或轨迹协议。

## 3. 总体架构

```mermaid
flowchart LR
    U["用户"] --> A["薄应用壳"]
    A --> SDK["Claude Agent SDK"]
    SDK --> S["Skills"]
    SDK --> K["Knowledge"]
    SDK --> T["Tools"]
    T --> F["DOCX / PDF / 图片 / 检查结果"]
    F --> SDK
    SDK --> A
    A --> U
    E["Eval<br/>离线"] -.运行样本并比较结果.-> SDK
```

运行时只有一条控制关系：应用壳配置并调用 Claude Agent SDK，SDK 驱动 Agent 使用 Skill、Knowledge 与 Tools。

Eval 是同一能力组合的离线消费者，不进入正常用户请求的控制路径。

## 4. 组件边界

### 4.1 Claude Agent SDK

Claude Agent SDK 负责通用 Agent runtime，包括：

- Agent loop 与模型交互；
- 会话上下文；
- 工具发现与调用；
- Skill 装载；
- SDK 原生支持的权限、hooks、流式输出与会话恢复；
- Agent 需要用户确认时的对话延续。

DocFit 可以配置和使用这些能力，但不复制它们。

如果某项能力必须依赖特定 SDK 版本，应在实现依赖和适配代码中声明，不在领域架构中抽象出第二套通用 runtime。

### 4.2 Skill

Skill 是 DocFit 的主要产品逻辑。它包含：

- 任务适用范围；
- 目标与完成条件；
- 推荐的观察顺序；
- 领域判断原则；
- 何时读取哪类 Knowledge；
- 何时调用哪类 Tool；
- 遇到不确定性时如何继续、回看或询问用户；
- 禁止行为和常见陷阱。

Skill 不是：

- BPMN 或 DAG；
- 阶段状态表；
- 可持久化的工作流实例；
- 一组必须逐项执行的系统任务；
- 学校具体格式数值的存放位置。

当前只维护一个用户目标型 Skill：

- `convert-thesis`：使用通用 Knowledge 和当前任务证据，把当前论文转换成目标格式。

学校材料的读取、解释和规则推导属于当前转换任务，不需要先运行另一个 Skill，
也不会产生可复用的学校 Knowledge 资产。

### 4.3 Knowledge

Knowledge 是 Agent 按需读取的产品级通用参考，包括：

- 论文文档单元、语义角色和复合对象的统一概念；
- 从模板、文字要求和页面证据识别规则的方法；
- 处理来源冲突、适用条件、歧义和不确定性的解释原则；
- 检查、修改、渲染、视觉复核和验证的通用处理模式；
- 不包含学校值的合成示例和常见 Word 版式陷阱。

Knowledge Package 随产品版本发布并保持只读。所有任务使用同一份包，不按学校
选择或挂载不同版本。学校名称、要求、模板、参数、固定文案、槽位和人工确认只
存在于当前任务证据与任务产物中；任何学校专属结论都不会因为被 Agent 提取过而
自动升级为长期 Knowledge。

### 4.4 Tools

Tools 是 Agent 可调用的受控能力。当前只向 Agent 暴露五个稳定 Tool：

- `docx_inspect`：读取结构、有效样式、可见对象和风险；
- `docx_edit`：在工作副本上执行一组受控修改；
- `docx_render`：按迭代预览或交付复核目的生成 PDF、页面图片和渲染证据；
- `docx_visual_review`：把指定页面、裁剪图或前后对比图作为视觉证据送入当前 Agent 上下文；
- `docx_validate`：独立检查源文件、最终文件和适用规则。

Tool 的输入输出应小而清晰，使用 SDK 支持的工具 schema。工具内部可以有复杂 OOXML 代码，但复杂性不扩散到 Agent runtime。

`docx_render` 负责产生图片，`docx_visual_review` 负责选择、裁剪、对齐、比较并返回图片内容块；当前 Agent 直接观察这些图片并形成视觉判断。`docx_visual_review` 不调用另一个模型，不自行宣布页面合格，也不把图像差异阈值伪装成版式语义。

渲染契约区分两种角色，但不增加 Agent 可见 Tool：

- **迭代渲染**：OfficeCLI 提供低延迟、高频的编辑反馈；本地 Word API 在修改前提供低频的目标应用分页基线，并仅在基线明确失效时重新分页；
- **交付渲染**：本地 Word API 对候选最终 DOCX 一次性导出 PDF，作为 Microsoft Word 兼容性复核证据；逐页图片、contact sheet 和裁剪图由本地从该 PDF 生成。

第一版固定使用 OfficeCLI 与本地 Word API 两个具体后端。OfficeCLI 同时负责
`docx_inspect`、`docx_edit`、`docx_validate` 和高频截图；本地 Word API 只负责
初始分页基线、必要时重新分页和最终 PDF 导出。五个 Tool 内部只做薄适配和固定
路由，Agent、Skill 和应用壳都不接收后端选择权。当前不建设通用 Provider
接口、注册表、运行时选择或故障转移；Word 路径失败时也不得把 OfficeCLI 结果
静默升级为目标应用事实。

五个 Tool 与第一版底层能力的具体映射如下：

| DocFit Tool | 第一版底层来源 | DocFit 契约层增加的职责 |
|---|---|---|
| `docx_inspect` | OfficeCLI 的结构化读取与查询能力 | 事实归一化、文档快照 hash、opaque `object_ref` 与风险摘要 |
| `docx_edit` | OfficeCLI 的确定性编辑与批处理能力 | 引用和前置条件校验、工作副本、all-or-nothing 发布与后置重读 |
| `docx_render` | OfficeCLI 的 `edit_feedback` 高频截图；本地 Word API 的分页基线、重新分页和最终 PDF | 根据 purpose/reason 固定路由，并生成 fidelity、字体、版本和 render evidence |
| `docx_visual_review` | DocFit 对两个后端已有页面产物的本地证据组织 | 返回页面、裁剪图、contact sheet 或对比图片块，不调用第二个模型或 Agent |
| `docx_validate` | OfficeCLI OpenXML 检查与 DocFit 独立后置检查 | 从源文件和最终文件重新取证，核对内容、规则、产物和视觉覆盖 |

这是一层面向 Agent 的 DocFit 领域与安全契约，不是通用 Provider 抽象。它不复制
OfficeCLI 的完整 DOM、选择器或命令体系；OfficeCLI 的私有路径和命令只存在于
具体适配代码内，Agent 始终只看到上述五个高层 Tool。

页面图片可以附带同一渲染快照的元素映射：页码、页面坐标系、`object_ref`、元素类型、bbox 和映射可信度。Agent 用图片判断问题，用元素映射把问题定位回可编辑对象；映射缺失或不可靠时必须显式报告，不能根据像素位置猜测 OOXML 目标。

页面是绑定某次 `render_ref` 的视觉观察窗口，不是 DOCX 中稳定存在的编辑对象。
Microsoft Word 第 N 页与近似 Provider 第 N 页没有天然对应关系；Provider、字体、
字段状态、修订显示策略或文档内容变化后，页码及页面元素映射都可能变化。Agent
可以按页面组织视觉复核，但必须根据当前文档的 `object_ref`、节引用或文字锚点
选择编辑目标，不能把另一次渲染的页码直接当作 `docx_edit` 定位器。

解析缓存、对象定位、临时文件、批量操作、视觉证据和后置校验都属于这五个 Tool 的内部实现，不是新的架构层。底层可以复用 MCP、CLI、库或本地渲染器，但它们不能拥有第二个 Agent loop；语义决策和下一步选择始终由 Claude Agent SDK 中的 Agent 完成。

### 4.5 Eval

Eval 使用样本、断言和必要的人工参考结果判断能力组合是否可靠。它不拥有在线交付状态，也不控制 Agent 下一步。

### 4.6 薄应用壳

应用壳只负责：

- 接收用户输入和文件；
- 挂载产品内置 Knowledge、必要 Skill 与 Tools，并把当前任务材料交给 SDK；
- 配置 Claude Agent SDK；
- 把用户任务交给 SDK；
- 转发需要用户回答的问题；
- 展示最终回复和产物链接；
- 记录必要的产品级用量与错误。

应用壳不负责：

- 解析论文语义；
- 决定处理阶段；
- 维护工作流状态；
- 为每一步设计内部任务；
- 复制 SDK 会话；
- 判断论文是否符合某校要求。

命令行、API 或图形界面都只是应用壳的可替换入口，不改变上述边界。

## 5. 一次任务如何运行

应用壳把产品内置通用 Knowledge、用户任务和当前任务文件交给 Claude Agent SDK。
Agent 使用 Knowledge 中的方法解释当前学校材料，并根据 Skill、任务证据和 Tool
返回的结构化事实与页面图片动态决定行为，必要时回看、修改、重新渲染、视觉
复核、重试或询问用户，最后返回产物和仍需注意的事项。这是一条数据流，不是阶段流程。

一次转换通常形成以下证据闭环：

```text
DOCX
  → docx_inspect（结构事实）
  → docx_render（迭代或交付渲染、页面图片、可选元素映射）
  → docx_visual_review（图片进入当前 Agent 上下文）
  → Agent 判断与 docx_edit
  → 重新 render + visual_review（修改后视觉验证）
  → docx_validate（独立确定性验证）
```

这不是固定调用顺序。Agent 可以根据风险缩小页面范围或重复其中部分，但涉及分页、溢出、空白页、图表位置、页眉页脚和模板外观的判断，必须有当前文档快照对应的图片证据。页面用于限定观察范围；修改仍以当前快照的对象引用和前置条件为边界。

## 6. 必须保留的不变量

架构可以简单，但以下底线不能被简化掉。

### 6.1 源文件只读

所有修改写入新的工作文件或最终文件，不覆盖学生原始 DOCX。

### 6.2 学生内容不得静默丢失

工具应提供足以比较关键内容对象的分析与验证能力。无法识别或无法安全处理的可见对象必须向 Agent 明示，由 Agent解释、询问或停止。

这里不强制全系统共享一套 Content Ledger 协议。对象身份、定位与血缘可以先作为 DOCX 工具内部设计，在确有第二个消费者前不升级为架构组件。

### 6.3 学校事实只来自当前任务证据

每个学校专属结论必须能指向当前任务中的模板、要求文件、官方示例或用户确认。
没有来源或未经确认的猜测不能伪装成学校要求。任务结束后，这些结论不会自动
写入产品 Knowledge；跨任务复用必须由下一任务重新提供并核对证据。

### 6.4 精确修改只通过 Tool

Skill 可以指导 Agent 做语义选择，但不得指导 Agent 绕过工具直接修改 OOXML。

### 6.5 不确定性必须显式呈现

如果 Tool 报告不支持对象、渲染不可信或 Agent 无法确定内容边界，最终回复必须说明影响和建议，不得用“已完成”掩盖未知项。

### 6.6 视觉判断必须绑定证据

Agent 的视觉结论必须引用当前文档 hash、渲染 Provider、版本、字体环境、页码和图片 hash。修改前的旧图片不能证明修改后的结果；近似渲染不能伪装成 Microsoft Word 的最终分页真值。

Tool 负责保证图片与文档快照、页面和渲染环境的绑定关系。Agent 负责判断溢出、遮挡、空白页、断页、图表布局、页眉页脚和整体版式。确定性验证与视觉判断必须分别保留，不能互相替代。

页码的作用域是单个 `render_ref`。同一文档 hash 的 OfficeCLI 与 Word 页面可以
通过该快照的 `object_ref`、节引用、文字锚点和明确的 mapping quality 关联，不能
根据页码相等自动关联。文档 hash 变化后，旧 `object_ref` 立即失效；必须重新
inspect 取得新引用，只能通过新旧快照的节、文字锚点或显式内容指纹建立历史
对照。旧页面证据可以作为历史参考，但不能继续定义当前内容位于哪一页。

### 6.7 渲染可信度不得被静默升级

DOCX / OOXML 是内容与结构事实；迭代渲染是页面外观的高效近似；目标 Microsoft Word 环境的渲染才是最终 Word 兼容性证据。实际后端、字体替代、DPI 或页面尺寸变化都必须形成新的 render ref。

本地 Word API 暂时不可用时，系统仍可运行 OfficeCLI 编辑迭代，但必须保留
`verification_gap`，不能静默回退或通过第一版端到端交付门，也不能声称已通过
Microsoft Word 最终视觉门。

## 7. 最小运行产物

一次转换通常返回最终 DOCX、预览、结构化视觉审查结果，以及简短的确定性验证结果和未解决事项。具体目录、文件名和调试产物由应用与 Tool 设计决定，不属于稳定架构。

只有当一个新产物被真实调试或 Eval 反复消费时，才把它提升为稳定接口。

## 8. 人工介入与恢复

人工介入使用普通 Agent 对话：

- Agent 说明无法判断的对象；
- 给出证据或页面；
- 提出最小问题；
- 用户回答后继续同一 Claude Agent SDK 会话。

恢复优先使用 SDK 原生会话能力。DocFit 不维护自定义 checkpoint 图，也不在架构文档中规定 SDK 会话的持久化方式。

如果工具调用中途失败：

- Tool 返回明确错误且不覆盖源文件；
- Agent 决定重试、换工具、缩小范围或询问用户；
- 需要跨进程恢复时，使用 SDK 会话能力和已经落盘的工作文件。

## 9. 架构验收问题

每次设计评审只需回答：

1. Claude Agent SDK 是否仍是唯一 Agent runtime？
2. 领域行为是否主要沉淀在 Skill？
3. Knowledge 是否仍完全通用，学校差异是否只来自当前任务证据？
4. 精确操作是否由 Tool 完成？
5. 涉及页面外观的判断是否基于当前文档的图片证据？
6. 视觉审查 Tool 是否只提供证据，而没有启动第二个 Agent？
7. 渲染结果是否明确区分迭代近似与目标 Word 交付证据？
8. 质量问题是否能通过 Eval 重现？
9. 应用壳是否仍然不包含领域编排？
10. 新增组件是否解决了已经发生的问题？

如果第 1、第 6 或第 9 个问题答案是否定的，DocFit 很可能又开始复制 Agent runtime 或变成工作流系统。

## 10. 已定决策

1. 运行时采用 Claude Agent SDK，不自建 Agent runtime。
2. DocFit 的稳定产品资产只有 Skill、Knowledge、Tools、Eval 和薄应用壳。
3. Skill 提供领域指导，不定义固定阶段状态机。
4. Knowledge 是随产品发布、版本化、只读且按需读取的通用领域资产；不保存学校专属事实或任务结论。
5. Tools 封装确定性文档能力和受控视觉证据传递，源文件只读；视觉判断仍由当前 Agent 完成。
6. Eval 在运行时之外执行，以结果断言为主。
7. 人工确认通过正常 Agent 会话完成。
8. SDK 已提供的会话、工具循环、恢复和日志能力不在 DocFit 内重建。
9. 新抽象必须由当前真实需求证明，不为假设中的平台化提前建设。
10. 页面图片是 Agent 判断与验证的一等输入；修改前、布局变化后和最终交付前都必须使用与当前文档绑定的视觉证据。
11. 第一版在同一 `docx_render` 契约下固定使用 OfficeCLI 与本地 Word API：前者负责高频近似反馈，后者负责低频 Word 分页基线、必要时重新分页和最终 PDF 导出。
12. 页面元素 bbox 映射是渲染证据的可选增强产物，不新增 Tool；有映射时帮助 Agent 从视觉问题定位回 opaque `object_ref`。
13. 页码是单个 render 内的视觉证据，不是跨后端稳定身份；同一文档 hash 的高频 CLI 预览与目标 Word 渲染通过当前快照的对象引用和锚点关联。
14. 两个具体后端只在五个 Tool 内做职责固定的薄适配；不建设通用 Provider 平台。只有未来真实接入第三个引擎，并且需要动态选择或故障转移时，才考虑抽取通用 Provider 接口。
