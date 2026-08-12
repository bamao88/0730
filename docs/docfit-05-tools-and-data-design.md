# DocFit Knowledge 与 Tools 设计（05）

> 状态：最终方案
> 日期：2026-08-06
> 原则：Knowledge 保持可读，Tools 保持确定性，复杂性不进入 Agent runtime。

## 1. Knowledge

### 1.1 定位

Knowledge Package 是 DocFit 随产品发布、面向所有学校和任务共享的通用论文格式
领域知识包。它为 Agent 提供统一概念、识别方法、解释原则和通用处理模式，帮助
Agent 从当前任务提供的学校材料中理解并推导具体规则。

Knowledge 必须通用。它不保存任何学校的专属要求、模板、格式参数、固定文案、
适用范围或人工确认。学校事实必须来自当前任务证据；任何学校专属结论都不能因为
被 Agent 提取过，就自动升级为长期 Knowledge。
可直接决定字体、字号、行距、边距、标题顺序等结果的样式经验值、国家标准数值表和
默认补全表也不属于 Agent Knowledge。

### 1.2 组织示例

Knowledge 作为 Python package 内的只读数据随 wheel/sdist 一起发布。当前已实现 v1
仍按概念、识别方法、解释原则和处理模式组织：

```text
src/docfit/knowledge/package/v1/
├── manifest.yaml
├── knowledge.md
└── references/
    ├── concepts.md
    ├── recognition-methods.md
    ├── interpretation-principles.md
    └── processing-patterns.md
```

`examples/` 可以保存少量跨学校合成示例。学校材料和真实/脱敏学校回归样本分别
属于当前任务目录与 `evals/`，都不进入产品 Knowledge。

Provider-independent P1 已把每个 manifest 声明的通用 document 投影为可选择的逻辑
模块：模块 ID 复用 document ID，版本复用 package version，内容 digest 复用该
document SHA-256，同时携带 package ID 与 package digest。这个最小投影不修改
`schema_version`、package 版本、manifest 字段或物理目录。以后只有真实消费证据出现
时，才把内容拆成 `core`、封面、摘要、目录、正文、参考文献、附录或其他开放范围；
这些范围不构成论文结构枚举。

### 1.3 最小 manifest

```yaml
schema_version: 1
package_id: docfit-thesis-format
version: v1
scope: universal_thesis_formatting
title: DocFit 通用论文格式领域知识
content_digest: "sha256:<64 lowercase hex>"
documents:
  - id: concepts
    kind: concepts
    path: references/concepts.md
    description: 通用论文格式概念和语义角色
    sha256: "<64 lowercase hex>"
review:
  reviewed_by: docfit-maintainers
  reviewed_at: "2026-08-01"
notes: null
```

v1 只接受 `schema_version: 1` 和 `scope: universal_thesis_formatting`，拒绝重复
YAML mapping key 与未声明字段。`version` 必须匹配包目录名；document ID 和路径
各自唯一，路径只能是 `references/` 或 `examples/` 下的安全 POSIX `.md` 相对路径。
`kind` 只接受 `concepts`、`recognition_method`、`interpretation_principle`、
`processing_pattern` 和 `example`；前四类各至少一项，`example` 可选。每个文档
保存自身 hash，`content_digest` 覆盖 manifest、`knowledge.md` 和全部声明文档。

### 1.4 Knowledge 内容边界

`knowledge.md` 说明包的使用方式和禁止项；`references/` 以自然语言分别保存：

- 论文文档单元、语义角色和复合对象等统一概念；
- 从结构、文字、样式、页面和上下文识别规则的方法；
- 处理来源优先级、冲突、条件、歧义和不确定性的解释原则；
- 检查、修改、渲染、视觉复核与验证的通用处理模式。

Knowledge 不保存学校数值，也不提供默认学校格式。通用示例必须使用合成占位值，
不能让 Agent 将示例字号、页边距、固定文案或对象顺序当作学校事实。
Knowledge 可以定义“观测值”“目标值”“有效继承值”“覆盖”“缺失”“冲突”和
“未决”等通用概念，但不携带任何供 Agent 套用的目标属性值。

模块化改变的是上下文选择粒度，不改变 Knowledge 的语义边界。一个复合前置结构可以
同时使用多个模块；未匹配范围也可以只使用 `core` 或由主 Agent 直接分析。

### 1.5 当前任务证据

- 学校模板、要求文件、官方示例和用户确认只放在授权任务目录；
- `prepare-template` 的 Registry 源由 task-bound Tool 私下持有；Agent 可针对同一版本中最多十六个
  当前对象批量做精确 lookup 或每对象最多五条 search，不能读取或枚举全 Registry；
- 每个学校专属结论必须能引用当前任务材料 hash 或当前用户确认；
- 精确格式值可以被规范化为本次 Tool 调用参数，但不写入长期 profile；
- 来源冲突或适用范围不明时，Agent 保留证据并询问，不用 Knowledge 补齐；
- 模板未观测到的样式属性保持为缺口；Agent 只能请求程序确定性解析或保留未决，
  不自行补值；
- 任务结束后，材料和推导结论按任务数据策略处理，不复制到产品 Knowledge；
- Eval 可以保存合成、脱敏或授权的学校场景，但 Eval fixture 不是运行时 Knowledge。

模板准备使用七个聚焦 Tool：`template_open` / `template_next` 从最新 checkpoint 推进当前有界
对象区域，`template_search` / `template_focus` 只补充当前决定所需事实，`template_registry` 按
对象惰性批量确认字段；`template_edit` 接受同一版本最多 32 个直接 action operation，物化时由
Tool 生成可见填写占位，并在一次原子提交中归一化重复操作、保护 Word 边界、回读有效结果、返回
修改区域的新证据与引用；`template_publish` 只要求 Agent 已看到最终版本的局部反馈，不设全页
覆盖门，只发布 `output/final-template.docx`。它们复用
OfficeCLI、V2 visual evidence 与包验证，不建立第二套 Agent loop；Agent 不提交 plan path、
compiler 输出或 Word output path。

### 1.6 加载与使用

应用壳加载当前产品唯一内置 Knowledge Package，并把它与两个领域 Skill、当前任务
材料和 Tools 一起交给主 Agent。`load_knowledge()` 不接收学校名、任务路径或版本
选择参数，也不决定一次委派使用哪些模块。

主 Agent 也可以通过路径受限的 Read/Glob/Grep 按需读取产品 Knowledge 文档；允许根
固定为产品 Knowledge Package，不能读取历史学校资产、项目其他文件或仓库外目录。
这只是渐进式上下文选择，不新增 Knowledge runtime，也不改变 `load_knowledge()` 的
完整性校验和唯一产品包事实。

Agent 使用 Knowledge 的方法理解当前任务证据；Tool 只消费当前任务已经确认的
操作参数和证据引用。没有学校包发现、模糊匹配、历史学校规则回退或自动积累。
当前规模不建设 `KnowledgeService`、向量数据库或学校资产发布系统。

Claude Agent SDK 没有单独的 DocFit Knowledge Base runtime。当前领域 Skill 指导主
Agent 为一次可选委派选择模块；主 Agent 把模块内容、ID、版本和 digest 连同任务证据
写入 `Agent` Tool prompt。当前 SDK 单次 Agent 输入不支持动态覆盖
`AgentDefinition.skills`，因此不使用虚构的 per-call Skill preload 契约。

### 1.7 v1 完整性边界

加载结果使用不可变类型化模型。加载器拒绝学校字段、未知根目录内容、未声明
文档、非 Markdown 资产、非 UTF-8、空文档、不安全路径、symlink、document hash
和包 digest 不一致，并且不修改包内容。

`content_digest` 的输入是去掉该字段后的 canonical JSON manifest、`knowledge.md`
和全部声明文档。审核日期先规范化为 `YYYY-MM-DD`；条目按 POSIX 相对路径排序，
每项依次写入 8 字节无符号大端路径长度、UTF-8 路径、8 字节无符号大端内容长度
和原始内容，再计算 SHA-256。Loader 能证明结构完整，不能单靠代码判断自然语言
是否真正通用；内容评审和跨学校测试负责语义边界。

### 1.8 与 Knowledge 分离的 Content Field Registry

当前研发期 Content Field Registry 是模板提取、学生内容投影、placement 与 Eval 的
跨阶段共享语义合同，不是本节 1.1 定义的产品 Knowledge，也不是 Eval Truth。
它必须开放、版本化并由 Registry ID/version/内容 hash 绑定，至少定义：`field_id`、Human 可读
label、明确 meaning、`content_type`、语义 cardinality、可选 `parent_field_id` 和
language，以及值 schema/规范化规则和值来源/学生提取策略。数量上下限、
该值是否期望从学生源出现，以及某个模板槽是否 required 是三个不同维度；
正式 schema 不能继续用单个 `optional` 值同时代表数量和可选性。

值来源至少要区分：学生文档可提取内容、任务/用户输入、系统生成内容、外部或人工
资产。一个字段可以允许多个来源，但必须说明学生内容提取对它是 required、optional
还是 not applicable。模板的 `required` 属于具体 slot/region；字段 cardinality 表示一份
论文语义值的数量约束；两者不能混成一个“必填”字段。`generated.toc`、
`review.mode`、`references.style_system`、二维码整页等内容若没有该分类，会造成错误的
学生提取漏项和 placement 断言。

字段 Registry 不保存学校 locator、模板样式、具体学生值或历史任务结论。字段 meaning
也不应命名 PKU 等学校字符样式或固定显示短语，这些只属于具体 Template
Truth。图表注、复合封面值等不是简单单父树时，合同必须显式建模允许的对象
关系或组合关系，不能为了迁就一个 `parent_field_id` 丢掉语义。`field_id` 只在其
Registry ID/version/hash 作用域内稳定；改义、拆分、合并或别名变化必须升级版本并提供迁移
说明，不能在同一 ID 下静默改变含义。当前研发权威为
`docs/plans/docfit-content-field-registry/DESIGN.md` 与固定的
`content-fields-v0.1.yaml`。v0.1 保留 54 个字段作为可复现开发基线，但尚未补齐所有值来源、
Human signoff 和复合关系，不构成公共运行协议、完整 Registry 或 Accepted Gold。

Registry 的一个字段不等于一个 Word 样式。字段只定义内容语义；独立的模板/兜底绑定
根据实际展示结构为它声明零个、一个或多个组件角色。配置字段可以不绑定展示角色，
叶子文本通常绑定一个角色，目录、表格或复合章节可以绑定多个角色。字段覆盖检查负责
证明每个字段都有明确处理；角色完整性检查必须另外按角色类型展开继承，并证明全部适用
有效属性都有具体值、`0`、`none` 或 `N/A`，不能把字段已绑定或最小 schema 通过误报为
完整兜底。

Registry 中没有的内容不得丢弃，也不得临时伪造永久 `field_id`。Template/Student
产物必须使用 `field_id: null`、`classification_status: unregistered`、产物内唯一
`local_field_key`、可读含义、内容类型和绑定快照的来源证据。`proposed_canonical_id` 只是
审查提议，不得用于自动 placement、已注册字段覆盖率或得分；Human 审查后才能在
新 Registry 快照中晋升。

## 2. Tools

当前实现注册五个公开 Tool。OfficeCLI 1.0.143 负责 inspect、edit、validate 和语义对象
定位；固定 Docker LibreOffice 25.2.3.2 是唯一视觉渲染器；Poppler 负责 PDF 页数、文字
bbox 和按需栅格化，Pillow 负责受控图片组合。公开 schema 不接受 Provider selector，
视觉后端失败时不回退。核心转换不依赖本地 Word、AppleScript、图形会话或用户电脑。

### 2.1 定位

Tools 把 DOCX 操作与转换服务的确定性复杂性封装在 Agent 之外。

Tool 应满足：

- 输入输出结构清楚；
- 修改前验证输入；
- 永不覆盖源文件；
- 错误时不留下被误认成成功的结果；
- 返回 Agent 决策真正需要的信息；
- 可以脱离 Agent 独立测试；
- 不擅自做论文语义判断。

### 2.2 最终工具方案与复用策略

下面定义的五个 Tool 是 DocFit 面向 Agent 的稳定契约，不表示底层 DOCX 能力必须由 DocFit 从零实现。

```text
Claude Agent SDK 中的主 Agent / 受限只读 Subagent
        ↓ 选择规则与下一步
五个 DocFit Tool
        ↓ 确定性适配
MCP / CLI / library / fixed local renderer
```

预处理发生在 `docx_inspect` 内部，后处理发生在 `docx_edit` 的后置检查、`docx_render`、`docx_visual_review` 和 `docx_validate` 内部。它们不是独立服务，也不拥有任务状态。底层后端不调用另一个模型或 Agent 来解释论文；语义与视觉判断可以由主 Agent 直接完成，或由主 Agent 通过 SDK 原生 `docfit-unit-analyst` 完成局部只读分析。恢复、跨范围合并、写入和发布选择始终由主 Agent 完成。

| 论文转换需要的能力 | 在 DocFit 中的归属 |
|---|---|
| 模板和论文的结构化预处理 | `docx_inspect` 内部 |
| 当前任务对模板证据的解释 | Claude Agent SDK 主会话；必要时使用受限 `docfit-unit-analyst` |
| 通用格式概念、识别方法与处理模式 | 产品内置 Knowledge Package |
| 学校规则、模板证据与精确参数 | 当前任务材料、Agent 当前会话与 Tool 调用参数 |
| 模板样式的属性级观测 | `docx_inspect` 内部 |
| 缺失样式属性的国家级标准解析 | 现有 Tool/adapter 内部的版本化确定性规则；不向 Agent 加载数值表 |
| 批量、安全、原子写回 | `docx_edit` 内部 |
| 分页和页面证据 | `docx_render` 内部 |
| 把指定页面图片送入调用它的当前 Agent 并建立前后对比 | `docx_visual_review` |
| 内容、格式和产物复核 | `docx_validate` 内部 |

实现时遵循以下顺序：

1. 优先复用维护活跃、许可证兼容的开源 MCP、CLI 或库；
2. 如果同一项目同时提供 MCP 与可嵌入的库或 CLI，产品实现优先通过薄适配层调用库或 CLI，避免在 Tool 内再嵌套一层 Agent 协议；
3. 只有现有实现无法满足真实样本、内容安全或可审计要求时，才补充最小自研代码；
4. 只有需要长期修改上游核心且无法通过适配器解决时，才考虑 fork。

推荐边界：

```text
Claude Agent SDK
        ↓
DocFit Tool schema
        ↓
DocFit adapter
        ↓
开源 MCP / CLI / library / native renderer
```

第一版不在这些实现之上再抽取通用 Provider 层，而是在五个 Tool 内固定两个明确 adapter：

| 具体后端 | 固定职责 | 不负责 |
|---|---|---|
| OfficeCLI | `docx_inspect`、`docx_edit`、`docx_validate` 的底层执行与语义对象定位 | 页面截图、视觉坐标、DOCX→PDF |
| Docker LibreOffice | 唯一 DOCX→PDF 视觉快照 | 文档语义分析、编辑、验证和对象身份 |

两个 adapter 承担不同职责，不实现可互换接口。Agent、Skill 和应用壳都不传入后端
选择。视觉证据记录 renderer、容器、字体、locale 和 PDF 参数，不存在 Provider 注册表、
动态选择、自动回退或故障转移平台。

DocFit 自己负责：

- 五个 Tool 的输入输出、错误语义和版本兼容；
- Tool 间 opaque `object_ref`、输入 hash、操作前置条件和过期检测；
- 分析与渲染缓存的正确失效；
- 源文件只读、原子发布和非目标内容保护；
- 当前任务证据到确定性 Tool 参数的受控映射；
- 第三方依赖的版本锁定、适配测试和 Eval。

第三方实现可以负责：

- OOXML 读取、写回和 package 关系维护；
- 常规文本、样式、表格、节、页眉页脚等底层操作；
- OpenXML 结构校验；
- DOCX 到 PDF 或页面图片的转换；
- 文档比较、修订和批注等成熟能力。

其他实现只保留为未来能力调研，不参与运行时选择：

| 候选 | 优先验证的能力 |
|---|---|
| [Safe Docx](https://github.com/UseJunior/safe-docx) / `docx-core` | 对既有 DOCX 的局部编辑、格式保留、稳定定位和文档比较 |
| [SecurityRonin/docx-mcp](https://github.com/SecurityRonin/docx-mcp) | OOXML 局部操作、修订、批注和结构审计 |
| Aspose.Words | 服务端快速迭代渲染、逐页图片和页面布局信息；需要验证授权、字体与目标样本保真度 |
| 其他 DOCX MCP | 作为能力来源或对照实现，不默认把完整工具面暴露给 Agent |

OfficeCLI 与 LibreOffice 分别按自己的固定职责用相同 fixture 取证；不要求二者通过一套
假想的可互换能力测试。至少验证：

- 目标学校样本中的段落、表格、图片、公式、目录、节和页眉页脚；
- 无操作另存和受控修改后，package 可独立解析且 OfficeCLI 可重新读取；
- 修改只影响目标对象，源文件保持不变；
- 错误能够转成 DocFit 的 `ok`、`needs_input` 或 `error`；
- 在开发机和 CI 环境中可安装、可锁定版本、可重复运行；
- render identity 能报告 LibreOffice、容器、字体、locale、导出参数和已知近似边界。

PoC 阶段可以直接调用底层命令验证能力；产品路径只向 Agent 暴露 DocFit 的五个
高层 Tool，避免 Skill 绑定 OfficeCLI 或 LibreOffice 的私有命令。固定 adapter 的薄适配
发生变化时不应要求修改 Skill 或 Knowledge。

### 2.3 最小工具面

优先提供少量、能力清楚的工具，避免 Agent 在大量细粒度工具中选择：

```text
docx_inspect    分析结构、样式、可见对象和风险
docx_edit       在工作副本上执行一组受控编辑操作
docx_render     用固定 LibreOffice 生成内容寻址 PDF、索引和默认联系表
docx_visual_review  将指定页面、裁剪图或对比图作为图片证据返回给当前 Agent
docx_validate   对源文件、最终文件和学校要求做确定性检查
```

新工具只有在职责明显独立、参数和失败语义更清楚时才增加。否则给现有工具增加明确的 `action` 或 `focus` 参数。

公开 schema 使用兼容 backend 已验证的扁平 JSON Schema 子集：对象、数组、枚举、
`required` 和 `additionalProperties` 可以使用，但不使用 `oneOf`、`anyOf` 或 `allOf`。
不同 action 的专属必填字段由 Tool runtime 在执行前校验，错误仍归一为 DocFit
`needs_input` / `error`。这避免兼容模型把 composition 关键字误生成为普通参数，同时
保留五个 Tool 名称和语义，不为每种 operation 拆新 Tool。

### 2.4 `docx_inspect`

输入示例：

```yaml
input_docx: /path/student.docx
focus: [structure, styles, visible_objects]
```

同一个 Tool 可以通过 `focus` 服务不同 Skill，例如：

```text
template_rules    分析学校模板结构、格式参数、槽位和说明文字
thesis_content    分析学生论文章节、字段、对象顺序和内容保护风险
```

它们是 `docx_inspect` 的不同分析重点，不新增 `template_inspect` 或 `thesis_inspect` Tool。
Tool 只返回绑定输入 hash 的结构、对象和 locator 事实；`field_id` 归属仍由 Agent 根据
当前任务证据判断，并可由 Human 确认。未来物化 Template/Student Actual 时也不新增
公共 Tool。

输出应是高信号摘要，可附完整分析文件路径：

```yaml
status: ok
document:
  pages_estimated: 42
  paragraphs: 318
  tables: 12
  images: 8
sections:
  - kind: possible_abstract
    object_refs: [...]
risks:
  - kind: unsupported_visible_object
    object_ref: ...
analysis_path: /path/analysis.json
```

对象引用由 Tool 生成并保持 opaque。Agent 用它选择目标，不解析内部 OOXML 路径。

底层引擎返回的段落索引、XPath、bookmark 或其他 locator 必须在适配层转换为 DocFit 的 opaque `object_ref`。不能把第三方定位格式直接写入 Skill 或 Knowledge。

一次底层解析应尽量完整收集后续需要的客观事实，包括：

- 正文段落、表格、合并单元格、节、页眉页脚；
- 图片、公式、脚注尾注、文本框、书签、域、内容控件和编号；
- 原始 run、合并后的逻辑文本及两者的字符位置映射；
- 直接格式、样式继承和最终生效的格式值；
- package parts、relationships、输入 hash 和不支持的可见对象。

Tool 将完整结果保存在任务临时目录，只向 Agent 返回摘要、风险和按需查询入口。相同输入 hash 的后续 `focus` 查询可以复用解析结果；这只是 Tool 内部缓存，不是新的运行时对象。Tool 只报告事实，不自行判定“这是一级标题”或“这是学生正文”。

#### 2.4.1 样式观测与确定性补全合同

这个合同用来稳定上游识别与下游写入的耦合点，不是要求 Agent 按一张固定内容树或
一套固定样式执行。当该能力按 06 的独立候选切片实现后，程序应对每个样式属性输出：

- 语义对象或可绑定范围；
- 观测值、直接格式、命名样式、继承链和最终有效值；
- `observed`、`missing`、`conflict` 或 `unresolved` 覆盖状态；
- 解析值及其属性级来源：`current_task_requirement`、`template_observation`、
  `inherited`、`national_standard` 或 `unresolved`；
- 来源 hash/ref，以及适用时的标准标识、版本、条款、适用性与规则集 digest。

这里的“属性”既可以是字体、字号、行距、边距等标量样式，也可以是图、表、
中英文题名、题注与注释的附着关系、上下位置和相对顺序等有限编排字段。建模只声明这些
字段可被观测、绑定、解析和追溯，不预先指定它们必须取什么值或出现在哪里。

解析顺序固定为：

1. 保留当前任务文字要求、用户确认和模板观测的原始事实；它们冲突时不静默排序，
   而是返回 `conflict` 交给 Agent 询问或保留未决；
2. 对仍缺失的单个属性，只有当调用上下文已给出经批准的国家级标准标识、版本和
   适用性证据，且对应条款有明文规定时，才应用该值；
3. 标准无明文、不适用、条款冲突或规则数据不可验证时，保持 `unresolved`，不使用产品经验默认值。

Word 的样式继承和文档默认值是“源文档最终如何生效”的观测事实，不是对目标要求
的补全根据。国家级标准规则作为现有 Tool/adapter 内部的版本化确定性数据维护：它不进入
Agent prompt，不形成学校 profile，不新增第六个 Tool。本节定义目标合同；当前五个 Tool
的公开 schema 和 M2 完成状态不因本节改变。

### 2.5 `docx_edit`

输入示例：

```yaml
input_docx: /path/work-v1.docx
output_docx: /path/work-v2.docx
operations:
  - action: apply_style
    target_ref:
      schema_version: 1
      document_sha256: ...
      object_id: obj-...
      expected_fingerprint: ...
    style: heading_1
  - action: replace_text
    target_ref:
      schema_version: 1
      document_sha256: ...
      object_id: obj-...
      expected_fingerprint: ...
    expected_text: "在此填写"
    replacement: "..."
```

要求：

- 输出路径不得等于输入路径；
- 执行前验证全部 operation；
- 目标定位或前置文本不一致时安全失败；
- 单次调用按 all-or-nothing 执行；
- 成功时返回全部实际执行项和警告；
- 修改后重新读取文件并检查目标效果、非目标内容和 package 完整性。

Tool 应先验证全部 operation，再写入临时文件；临时文件能够重新打开并通过基础结构检查后，才发布到 `output_docx`。任一操作失败时，不留下可被误认成成功的输出文件。

普通 allowlist operation、跨 run 文本和格式属性由 OfficeCLI 完成。跨文档内容放置
所需的样式、编号、relationship、媒体、页眉页脚与节属性依赖闭包由 DocFit 的最小
OOXML helper 在同一 `docx_edit` 临时副本内完成。adapter 统一执行前置检查、引擎错误、
重读效果和原子发布；这些细节不进入 Skill。

为了降低定位漂移风险，Tool 在真正写入前重新核对输入 hash、对象指纹和预期文本；同一容器内会影响位置的操作由 Tool 内部按安全顺序执行，通常从后向前。写入结束后从新文件重新解析，而不是相信 OfficeCLI 的修改清单。

B 路线使用 `import_content_objects` 把学生源对象放入以目标模板为输入的工作副本；它仍
属于 `docx_edit`，不新增第六个 Tool。输入字段为：

```yaml
action: import_content_objects
source_docx: /authorized/task/student.docx
source_sha256: <64 lowercase hex>
source_refs: [<student object_ref>, ...]
target_anchor_ref: <template-work-copy object_ref> # position 为 before/after 时提供
position: before | after | end
include_source_final_section_properties: false
```

`source_docx`、`source_sha256` 与至少一个 `source_ref` 必填；`position` 缺省为 `end`，
节属性开关缺省为 `false`。每个 ref 只绑定自己的文档快照。`input_docx` 是目标模板
工作副本，来源学生 DOCX 与目标模板都必须保持不变。实现继续证明：

- 来源学生文档 hash 与来源对象引用；
- 目标模板工作副本 hash 与放置锚点；
- 样式、编号、媒体、relationships、页眉页脚和节属性的依赖闭包；
- 内部 ID 与关系 ID 的冲突重映射；
- all-or-nothing 发布；
- 合并后重新打开、内容保留和非目标内容检查。

旧的 `import_template_sections` action 为既有调用保留兼容性，只能用于明确的模板资产组装
任务；它不是 `convert-thesis` 的默认路线，也不能用于把模板节导入学生论文副本后声称完成
B 路线。OfficeCLI 只支持简单段落复制、无法复制完整依赖闭包时，必须把能力缺口报告为
不支持或 `verification_gap`，不能把部分合并发布为成功结果。

### 2.6 `docx_render`

`docx_render` 只负责把当前 DOCX 建成稳定的 V2 LibreOffice 视觉快照。公开输入是：

```yaml
input_docx: work/current.docx
overview: true
```

`task_root` 由应用会话注入；公开输入拒绝 intent、output directory、provider、backend、
engine、父 render 和对象 focus。固定 Docker LibreOffice 只生成一次 PDF；Poppler 建立
页数、页面尺寸和 `pdftotext -bbox-layout` 文字索引。默认 overview 只派生第一页段联系表，
不会在 render 时生成全部页面 PNG。

`render_ref` 为 `render:v2:<sha256>`，身份由以下事实共同决定：

- DOCX SHA-256；
- LibreOffice 版本与容器 image digest；
- 字体环境 digest；
- locale 与 PDF 导出参数。

任务内 Evidence Store 位于 `<task-root>/.docfit/evidence/renders/<render-hash>/`，包含
`manifest.json`、`document.pdf` 和索引；文件 inventory 保存相对路径、hash 与字节数。
相同身份直接 cache hit。DOCX 在渲染期间变化、LibreOffice 超时/失败、PDF 不完整或索引
不可读时不发布 render ref，并清理临时结果。

输出核心字段：

```yaml
schema_version: 2
status: ok
cache_hit: false
render_ref: render:v2:...
document_sha256: ...
page_count: 79
fidelity: approximate
renderer:
  name: libreoffice
  version: LibreOffice 25.2.3.2 ...
  container_image_digest: sha256:...
  font_environment_digest: ...
  locale: zh_CN.UTF-8
overview:
  evidence_ref: visual:v2:...
  covered_pages: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
  has_more: true
```

所有结果固定为 `approximate`；它们是 Agent 可复核的当前视觉证据，不是 Microsoft Word
像素真值。正式路径只有 LibreOffice，失败时不退回 OfficeCLI 截图、远程服务或其他
renderer。

### 2.7 `docx_visual_review`

该 Tool 从一个有效 V2 render 按需生成视觉视图并通过普通客户端 Tool result 返回原生
image block。它支持：

```text
contact_sheet  指定页段的缩略图总览
pages          指定完整页面
regions        object_ref、文字或已有图片 bbox 的局部高清图
compare        两个同环境 LibreOffice render 的对比图
```

质量档位为 `thumbnail=72 DPI`、`review=144 DPI`、`detail=220 DPI`。单次最多返回
有界数量图片；更多结果使用与 render/mode/请求绑定的 cursor 分批取得。每张图片使用
`visual:v2:<sha256>`，其身份包含 render ref、模式、页面/selector、PDF bbox、DPI、
padding 和 compare 参数。相同请求复用同一图片和 sidecar hash。

`regions` 不消费 OfficeCLI 页面坐标或 HTML bbox。对象选择器先核验 `object_ref` 的
文档 hash，再把 OfficeCLI 的主文本、前后文本和结构上下文映射到 LibreOffice PDF 文字
坐标：

1. 完全文本匹配；
2. 归一化文本匹配；
3. 前后锚点消除重复；
4. 结构顺序和相邻锚点限定；
5. 仍不唯一时返回候选完整页与 `mapping_unavailable` warning。

文字 selector 可指定 occurrence。Agent 看过整页后还可用 `image_bbox` selector 引用原
evidence ref 和像素 bbox；Tool 根据原视图 DPI/变换反算 PDF 坐标，避免坐标脱离来源。
无文字对象且缺少可靠上下文时绝不生成看似精确的裁图。

结构化结果、紧凑 JSON text block 与原生图片块必须语义一致。结果保存 renderer、
document hash、render ref、页码、变换参数、image hash 和 evidence ref。Tool 不修改
DOCX，不输出“版式正确”之类判断。compare 只接受 renderer 与字体环境一致的两个 render；
分页不同时使用文字锚点对齐，无法对齐则拒绝。

应用壳把 Agent 的最终 findings 保存为 `visual-review.json`，至少绑定当前
`document_sha256`、`render_ref`、renderer、`reviewed_pages`、evidence refs 和
findings。文档修改后必须重新 render；旧 evidence 只能作历史参考。

普通客户端 Tool 可以返回原生图片，因此视觉工具保持 direct MCP client Tool。
programmatic tool calling 目前只接受文本工具结果，不用于调用该工具。

### 2.8 `docx_validate`

验证工具按四类证据组织结果，但仍然只是一个 Tool：

1. **Package / OOXML 合法性**：压缩包、关系、样式、编号、书签、内容控件及图片引用是否完整；
2. **内容与学校规则**：源文件是否未变、关键内容是否保留、占位符和固定规则是否满足；
3. **布局指标**：页数、空白页、溢出候选、跨页表格、页边界与字体/渲染 warning；
4. **视觉审查**：当前 Agent 的报告是否绑定当前 render、覆盖要求页面且没有未处理的 blocking finding。

验证工具只做能够稳定、低误判地判断的事实：

- 源文件 hash 未变化；
- 最终 DOCX 可重新打开；
- 关键 package 关系可解析；
- 支持范围内的关键文本和对象没有明显丢失或重复；
- 必填内容存在；
- 占位符和模板说明文字没有残留；
- 目标样式的关键参数符合当前任务已确认规则；
- 渲染成功，renderer 与字体环境警告已呈现；
- 视觉审查报告绑定当前文档与当前 render，要求页面已经覆盖；
- 没有被忽略的 blocking visual finding；
- 存在绑定当前文档、固定 LibreOffice 环境、已由 Agent 覆盖全部必查页面且此后没有
  文档修改的 V2 视觉证据；否则保留 `verification_gap`。

最终交付验证的输入应显式包含视觉审查报告：

```yaml
source_docx: /path/source.docx
final_docx: /path/final.docx
knowledge_version: v1
task_rule_evidence: <由 M1 Tool contract 定义的当前任务规则与证据引用>
visual_review: /path/visual-review.json
required_visual_coverage: all_final_pages
```

修改过程中可以只要求变化页和相邻页；最终交付必须要求当前 `final_docx` 的全部页面
覆盖。`docx_validate` 只校验覆盖、引用、版本绑定和 blocking finding，不重新解释图片
内容，也不自行宣布候选已经 final。M1 必须分别验证 OfficeCLI 的结构/编辑职责与
LibreOffice V2 视觉职责；M2 再把当前 render、全部页面覆盖和独立验证组合为完成门。
缺少绑定最终文档的当前 V2 render 时不能通过 M2 交付门。

输出示例：

```yaml
status: ok
checks:
  - name: docx_opens
    result: ok
  - name: source_unchanged
    result: ok
  - name: placeholder_scan
    result: issue
    evidence: "第 2 页仍包含“在此填写”"
summary:
  errors: 0
  issues: 1
  warnings: 0
```

`status` 表示 Tool 调用是否正常完成；文档中发现的问题放在 `checks` 和 `summary` 中。因此，成功完成验证但发现占位符时仍返回 `ok`。只有缺少必要输入时返回 `needs_input`，验证过程本身失败时返回 `error`。

`docx_validate` 是普通 Tool，不是 Delivery Preflight、Verifier 或交付状态机。它组合
OfficeCLI 的 OpenXML 校验、DocFit 独立后置检查、当前任务已确认规则和视觉审查
覆盖检查；Agent 读取规范化结果并在最终回复中如实表达。

验证必须从源文件和最终文件重新读取事实，不能把 `docx_edit` 的成功返回、旧分析缓存或旧截图当成验证结论。内容与对象保留、有效样式、package 关系、占位符、视觉审查覆盖和高风险页面分别检查；任何无法独立确认的事项明确返回 warning 或人工复核要求。

## 3. 内容安全的实现边界

“内容不得静默丢失”是产品不变量，但不要求先建设全局内容身份平台。

### 3.1 Tool 间的对象引用

`docx_inspect` 返回、`docx_edit` 消费的 `object_ref` 至少包含：

```yaml
schema_version: 1
document_sha256: ...
object_id: obj-...
expected_fingerprint: ...
```

- `document_sha256` 防止把其他文档快照的引用用于当前文档；
- `object_id` 只在该文档快照内标识对象；
- `expected_fingerprint` 用于发现目标内容或关键结构已经变化；
- Tool 消费 ref 时必须验证这些前置条件，不匹配则返回 `needs_input`。

这个小型 Tool 契约只服务指定 DOCX 快照的安全定位。跨文档模板组合可以同时携带分别绑定来源模板与目标文档 hash 的引用，但每个引用仍只在自己的文档快照内有效；它不定义跨文件类型、跨任务或跨运行的全局对象身份。

### 3.2 最小策略

当前实现采用以下最小策略：

1. `docx_inspect` 对一个文档快照生成稳定的 opaque object refs；
2. `docx_edit` 只接受这些 refs 和明确前置条件；
3. 修改后重新 inspect；
4. `docx_validate` 比较支持对象的文本、类型、数量和必要顺序；
5. 发现不支持对象时返回给 Agent，不静默忽略。

更细的 OOXML locator、第三方对象路径、`content_id` 或血缘关系继续留在 Tool adapter 内部，不把 `object_ref` 泛化为全系统 ArtifactRef。

当前不建设：

- 全局 Content Ledger；
- 跨运行 ArtifactRef 系统；
- canonical object identity 标准；
- 事件溯源；
- 全仓库 schema registry。

### 3.3 文档操作权威路线与 Subagent 写入边界

薄应用壳对主 Agent 暴露五个 Tool，并另外暴露只读的 Skill/Knowledge/任务证据发现面
与受信任的 Bash/Write；
`docfit-unit-analyst` 的 SDK Tool allowlist 仍只包含 `docx_inspect` 和
`docx_visual_review`。`docx_edit`、`docx_render` 与 `docx_validate` 不出现在 Subagent
上下文中；`Agent`、`Skill`、`Read/Glob/Grep/Write`、`AskUserQuestion` 和 Bash 也不可见。
主 Agent 合并跨范围约束后串行调用 `docx_edit` 写文档，文档 hash 变化后重新 inspect
并丢弃旧 ref。`docx_edit` 是产生对象前置条件、提交状态和后置证据的权威文档编辑路线；
Bash/Write 没有 DocFit 路径 gate，因而不能再声称它们在文件系统层无法修改文档。

`Agent` 对主 Agent 可见但不以裸工具名通用自动批准。SDK 0.2.128 的 live 证据表明
`Agent` 调用不是 `can_use_tool` 的可靠必经路径，因此薄应用壳用 SDK 原生
`PreToolUse` 权限钩子检查 `subagent_type`，只允许 `docfit-unit-analyst`，拒绝 SDK
内置 `general-purpose` 与未知类型。`can_use_tool` 继续处理用户追问与防御性拒绝。

### 3.4 主 Agent 直接读取权限与受信任 Bash/Write

主 Agent 的内置工具面固定为 `Skill`、`Read`、`Glob`、`Grep`、`Bash`、`Write`、
`AskUserQuestion` 与类型受限的 `Agent`；五个 `mcp__docfit__...` Tool 继续直接调用。
Read/Glob/Grep 不加入自动批准集合；SDK `PreToolUse` hook 与 `can_use_tool` 使用同一策略：

1. 把相对路径按项目 cwd 解析并 canonicalize 为真实绝对路径；
2. 只允许项目 `.claude/skills/**`、产品 Knowledge Package、当前任务 `input/**`、
   `work/**` 与 output 根；
3. `Glob/Grep` 必须提供显式搜索根；Glob pattern 和 Grep 的可选 glob filter 不允许
   绝对路径、`~` 或 `..`，Grep 正则只作为内容模式；
4. 拒绝 `~/.config/docfit/**`、`.env`、`.git/**`、常见凭据文件、其他任务、项目外路径、
   非普通文件和 symlink 逃逸；搜索树含 symlink 或敏感文件时整次搜索失败；
5. 允许时把 canonical path 写回 Tool input，拒绝时只返回固定安全原因，不记录路径或正文。

Bash/Write 与五个 DocFit Tool 加入自动批准集合；Bash/Write 不安装 DocFit 路径 hook，
可访问 Agent SDK 子进程本来可访问的路径和环境，包括直接 Read allowlist 之外的文件与
后端凭据。系统提示要求不输出凭据或文档正文，观测 projector 丢弃命令、路径和内容，
但这是一项显式信任决策，不是 sandbox。Edit 与网络工具继续默认拒绝。

Read/Glob/Grep 本身不能修改文件；Bash/Write 的存在不改变五个 DocFit Tool 的
inspect/render/edit/visual-review/validate 契约或完成门。Bash/Write 的参数与结果只记录
无载荷生命周期元数据，不进入权限事件或观测索引。

### 3.5 双侧提取与 Placement 数据连接合同

本节定义未来 M3 和需要显式调试证据的任务如何连接模板与学生内容。当前已有一个经
单独批准的内部调试切片，物化了受限 Student Content、Placement、模板填写和质量投影
候选，见 `docs/plans/docfit-student-content-placement-debug.md`；该切片不等于正式产品
schema 或运行时合同，也不新增 Skill、公共 Tool、产品 Knowledge 类型或固定工作流。

四种身份必须分离：

| 身份 | 作用域 | 回答的问题 | 不能替代 |
|---|---|---|---|
| `field_id` | Registry ID/version/hash | 语义上是什么 | source/target locator、写入授权 |
| `content_id` | 当前学生内容包/任务谱系 | 哪一份事实或有序内容实例 | Tool `object_ref`、跨任务全局身份 |
| `slot_id` / `region_id` | 当前模板 revision/hash | 模板允许写到哪个目标 | 学生内容身份、页码 |
| `placement_id` | 当前任务与双方固定版本 | 哪些 source 以什么动作进入哪个 target | DOCX 物理 locator、Agent 阶段状态 |

Tool 的 opaque `object_ref` 和其他 snapshot locator 继续绑定单个文档 hash；它们可以作为
source/target locator 的执行证据，但不能直接充当上述逻辑 ID。模板或学生文件 hash
变化后旧 locator 失效，逻辑映射只有在重新 inspect 并证明同一内容/目标后才能续接。

#### 3.5.1 Template Actual / Truth

模板提取结果在需要物化时至少保存：Registry ID/version/hash、模板 hash、
`slot_id/region_id → field_id`、内容类型、slot required 状态、字段语义基数、条件、
fill/empty/placeholder policy、目标显示/投影合同、样式、区域责任和来源证据。

每个自动 locator 必须声明 kind/value、part/scope、预期命中数和必要的 Human fallback，
并由 `template_sha256` 约束。复合物理位置属于一个语义槽时使用 component locators；
不能把三行标题误建成三份题名字段。连续正文、参考文献等使用有边界的 region，不能用
单一页码或段落序号代替 start/end。`protected/slot/remove` 责任要细到段内范围或对象
范围，槽边界不能吞入固定标签。

跨模板 `field-alignment` 是从每个 Template Truth 派生的审计/覆盖索引：它可以显示某个
`field_id` 在各模板对应哪些 locator，也可以显示 `semantic_only`，但不是 Registry 本身，
不能反向成为任一模板的 locator 权威来源。

#### 3.5.2 Student Content Actual / Truth

学生内容结果绑定只读源文件并保留内容覆盖。根级至少保存学生源 hash、Registry
ID/version/hash、items、unregistered items、review 和来源证据。每项至少保存任务内
`content_id`、`field_id` 或未注册状态、`content_type`、规范值和原始观测值或复杂对象引用、一个或多个
source occurrence/locator、父项、唯一 `source_order.block + source_order.inline` 和冲突/确认状态。

简单标量可以保存规范化 `value`；rich text、图片、表格、公式、脚注、文本框和其他复杂
对象保存绑定学生源 hash 的 `content_ref`、结构摘要和必要资产 hash，不能只保存提取
文字。source locator 可以是 opaque object ref，或带 occurrence 的唯一文字/结构锚点；
页码只作为 Human 证据，不能单独定义来源身份。

论文级共享事实与 source occurrence 分离：题名、作者等一份内容事实可以由多个页面
位置观察支持；观察一致时共同指向一个 `content_id`，冲突时保留各 occurrence、观察值
hash 和 conflict 状态，等待证据/Human 裁决。章节、段落、图、表、公式等局部有序内容
各自拥有 `content_id`、`parent_content_id` 和唯一 `source_order`，不能因 `field_id` 相同而
合并或按类型重排。`items` 数组是顺序唯一权威，`field_results` 只允许作为派生字段索引。

Actual extraction 必须保留未注册、不支持和没有目标字段的可见内容。未注册项使用
`field_id: null`、`classification_status: unregistered` 和产物内 `local_field_key`，不能丢弃。
Accepted Truth 中每个 in-scope 项最终要么有确认字段，要么有明确
placed/retain/exclude/manual/unresolved 处置。Student Content 文件及其资产包含
学生数据，继承源 DOCX 的仓库存储、CI、日志和外部处理限制。

#### 3.5.3 Placement Actual / Truth

placement 使用显式边连接双方。每条边至少保存任务内 `placement_id`、一个或多个
`source_content_ids`、共享 `field_id`、具体 target `slot_id/region_id`、action、order、
condition、status 和证据。需要拆分、组合、排序或目标显示转换时，边还必须保存
`projection/formatter` 标识、输入、规则/版本、输出和来源证据。一个 source 到多个 target
使用多条或显式多目标边；多个
source 合并到一个 target 时记录完整 source 集合与确定顺序。连续内容目标使用
`region_id`，生成字段使用 generated source kind；任务输入、外部资产、retain、exclude、
manual 和 unresolved 都必须显式表达，不能通过缺少映射暗示。

只有同时满足字段相同、类型/基数兼容、目标唯一、condition 已解析、双方 locator 有效且
没有来源冲突时，程序才可把候选标为 deterministic。多目标、多来源、复合槽、连续区域、
条件页、重复事实或相似文字只能生成待确认候选。projection 也只有在所有输入齐全且
规则确定性时才能自动执行；它不能猜姓名译法、导师职称、专业拆分或其他缺失值。
真正编辑时，adapter 仍消费当前快照的
source refs 与 target refs，执行前验证所有前置条件并 all-or-nothing 发布。

placement coverage 至少回答：每个 in-scope source 是否 placed/retain/exclude/unresolved，
每个 required target 是否 satisfied/blocking，是否存在多余目标内容、字段错误、顺序错误
或 protected 越界。该覆盖可以成为 Eval/validation 事实，但不升级为全局 Content Ledger
或在线交付状态机。

## 4. 工具错误语义

所有 Tool 使用简单、可行动的结果：

```text
ok               调用正常完成，结果可以消费；不等于论文已经合格
needs_input      目标或事实不足，需要 Agent 补充、重新 inspect 或询问用户
error            工具未正常完成，不应消费其输出
```

文档质量、格式偏差和非阻断风险放在 `checks`、`issues` / `warnings` 中，与调用状态分开。不为每个领域动作创建新的全局状态枚举。

### 4.1 不信任第三方的成功声明

DocFit adapter 不直接转发第三方引擎的 `success`、退出码或自然语言结论。按不同 Tool 的能力，一次调用适用以下四项独立检查：

1. **请求检查**：输入符合 DocFit schema，引用和前置条件仍然有效；
2. **执行检查**：MCP、进程或库调用正常返回，没有超时、崩溃或结构异常；
3. **产物检查**：预期文件确实存在、能够重新打开，源文件没有被覆盖；
4. **效果检查**：目标修改已经发生，支持范围内的非目标内容没有意外变化。

第三方报告成功但任一后置检查失败时，DocFit 必须返回 `error`，把失败来源标记为 `postcondition`，并且不发布或继续消费该产物。第三方没有主动报告错误，不代表 Tool 成功。

并非所有质量结论都有便宜、完全独立的 oracle。对无法通过重新打开、结构比较、
原始 OOXML、当前 V2 页面证据或人工页面复核验证的高风险结论，Tool 必须返回
`verification_gap` warning，并说明当前证据来源；不能把底层后端的自我声明
改写成已验证事实。

对可能产生副作用的 Tool，结果应包含最小诊断信息：

```yaml
status: error
committed: false
failure:
  origin: engine
  code: engine_timeout
  retryable: true
  message: 第三方引擎在限定时间内未返回
  suggested_actions:
    - retry_smaller_batch
    - report_backend_failure
engine:
  name: ...
  version: ...
evidence:
  exit_code: ...
  output_created: false
```

`committed` 只表示经过 DocFit 后置检查的副作用是否已经发布。临时文件存在不等于 `committed: true`。日志只保留诊断所需的脱敏摘要，不写入整篇论文内容。

### 4.2 失败来源与可恢复性

`failure.origin` 使用少量稳定分类：

| origin | 含义 | Agent 的默认处理 |
|---|---|---|
| `request` | 调用参数、引用或前置条件不合法 | 根据 schema 修正，或重新 inspect |
| `document` | 文档损坏、受保护、定位歧义或对象不受支持 | 缩小范围、重新 inspect，必要时询问用户 |
| `engine` | OfficeCLI 或 LibreOffice 失败或返回畸形结果 | 仅在 `retryable: true` 且调用方式或范围有实际变化时重试固定 adapter |
| `environment` | 文件锁、依赖、字体、权限或渲染环境问题 | 修复环境或稍后重试固定后端；不跨职责回退 |
| `adapter` | DocFit 映射、协议或适配代码失败 | 不重复相同调用，保留证据并报告为 Tool 问题 |
| `postcondition` | 引擎声称成功，但产物或修改效果未通过独立验证 | 隔离产物并停止，不用另一职责的后端掩盖失败 |

`code` 用于测试和聚合，`message` 面向 Agent，`suggested_actions` 只能给出安全且可执行的恢复选项。

典型结果应这样区分：

| 事实 | Tool 结果 | 主要归因 |
|---|---|---|
| Agent 传入失效引用 | `needs_input` + `origin: request` | Agent 应重新 inspect |
| 引擎崩溃或超时 | `error` + `origin: engine` | 第三方 Tool |
| 引擎返回成功但输出打不开 | `error` + `origin: postcondition` | 第三方 Tool 或 adapter |
| 编辑正确执行，但最终格式仍不符合当前任务要求 | `ok` + validation issue | Agent 对任务证据的解释、参数映射或覆盖不足，需结合证据归因 |
| 当前最终 DOCX 没有完整 V2 页面覆盖 | `ok` + `verification_gap` warning | 需要恢复固定 LibreOffice renderer、补看页面或人工复核 |

Agent 可以根据 Tool 描述、`retryable`、证据和 Skill 指引决定：

- 重试；
- 重新分析；
- 使用更小范围的操作；
- 改用其他工具；
- 询问用户；
- 停止并报告。

Agent 不应：

- 仅凭输出文件存在就宣布成功；
- 消费 `committed: false` 或未通过后置检查的写入产物；
- 在输入、环境和调用方式均未变化时重复同一失败调用；
- 把 `engine`、`adapter` 或 `postcondition` 失败解释成论文内容问题；
- 让 Agent、Skill 或应用壳选择具体后端，或在固定后端失败后跨职责静默回退；
- 隐藏失败并用未经验证的备用文件交付。

## 5. 如何做得更快

速度优化优先减少重复解析、重复渲染和低信息量的 Agent 往返：

- `docx_inspect` 一次解析尽可能覆盖全部客观对象，后续通过 `focus` 读取同一份缓存；
- Tool 返回高信号摘要和完整证据路径，不把整份 OOXML 塞进 Agent 上下文；
- `docx_edit` 接受一组有前置条件的操作，避免每个段落一次 Tool 调用；
- 修改后先做便宜的结构和内容检查，只渲染发生变化或风险较高的页面；
- 渲染缓存由输入 hash、LibreOffice/容器版本、字体 digest、locale 和 PDF 参数共同决定，任何一项变化都自动失效；
- 可以使用 `docx_render` 附带的有限 contact sheet 开始全局扫描，再按风险通过
  `docx_visual_review` 分批读取整页或裁剪图；单次图片数量和字节数受限；
- OfficeCLI 提供语义对象时，视觉服务在 LibreOffice PDF 中重新定位并返回候选
  `object_ref` 与 mapping quality，减少 Agent 从截图问题到编辑目标的往返；
- 对同一 `render_ref` 的页面、裁剪和 compare 查看复用
  `docx_visual_review`，不重复调用渲染后端；
- 相同 render identity 直接复用 PDF；相同 view identity 复用按需页面与局部图片；
- 修改过程中优先复核变化页及相邻页，最终交付前仍需覆盖全部当前页面；
- `docx_validate` 复用解析代码，但必须对最终文件重新取证，不能复用旧结论；
- Agent 只决定重试、重新取证、缩小范围、换公开 Tool 或询问用户；具体后端由 Tool
  使用固定 adapter，Tool 内部不启动隐藏的 Agent loop，也不执行自动故障转移。
- 主 Agent 只在局部分析收益超过上下文、调用和合并成本时使用通用只读 Subagent；
  Subagent 只接收选中 Knowledge 模块和显式任务证据，不靠父会话历史补齐事实。

这些优化改变调用成本，不改变 Claude Agent SDK 的控制关系，也不产生可持久化流程状态。

## 6. 工作文件

Tool 可以使用工作副本和输出目录，但不规定全局任务目录协议。例如：

```text
task-work/
├── source.docx
├── work/
│   └── working.docx
└── output/
    ├── final.docx
    ├── preview.pdf
    ├── pages/
    ├── layout-map.json
    ├── visual-review.json
    └── validation.json
```

只有最终交付和调试实际需要的文件长期保留。临时 OOXML、渲染缓存和中间副本可由工具管理。

第三方引擎只能访问本次调用明确授权的输入、临时目录和输出路径。若其自带网络、脚本执行或任意文件访问能力，适配层应关闭这些非必要能力；运行时不得自动下载未锁定版本。

主 Agent 的直接 Read/Glob/Grep 只搜索上述任务目录中的文本证据、Tool 已发布摘要、
Skill references 和产品 Knowledge。受信任 Bash/Write 可绕过这项直接读取限制，并访问
进程可访问的其他任务文件、凭据、input 或 Tool/App 管理产物；这项能力不会被描述成
强制文件隔离。Agent 仍被明确要求不打印凭据或文档正文，最终交付仍必须满足五 Tool
证据、源 hash、当前 V2 LibreOffice render 与独立验证完成门。

这不是 Run Bundle 协议；应用或测试不应依赖每个中间文件都存在。

## 7. 何时增加抽象

只有出现以下证据时才考虑扩展：

| 真实问题 | 最小扩展 |
|---|---|
| 通用 Knowledge 文档经常缺失或 digest 错误 | 强化现有 package validator；不增加学校包服务 |
| 通用 Knowledge 大到普通按需读取明显不足 | 增加最小索引；没有测量证据时不引入向量数据库 |
| 新的通用消费范围反复需要独立知识 | 增加 Knowledge 模块；不因此增加 Agent 类型或固定文档分类 |
| DOCX 之外的多个工具确实需要共享对象引用 | 评估最小跨格式 ref；没有真实消费者时不泛化 |
| 同一 Tool 操作反复出现定位歧义 | 强化 Tool 内部 locator |
| 模板样式缺口反复出现，且已明确选定可授权维护的国家级标准 | 按 2.4.1 扩展现有 Tool 内部观测/解析器与属性级来源；不增加 Knowledge 默认值或第六个 Tool |
| Eval case 多到串行运行太慢 | 接入现成并发 runner |
| 产品需要多人权限和正式发布 | 在产品需求明确后设计对应服务 |
| 已真实接入第三个引擎，并且同一职责需要动态选择或故障转移 | 再评估最小通用 Provider 接口；两个职责不同的现有后端本身不构成抽象证据 |

扩展应从已经发生的问题出发，不从“以后可能平台化”出发。

## 8. 本地运行观测的数据边界

M2 后批准的本地观测界面只在薄应用壳中建立隐私安全的运行投影，详细产品设计见
`docfit-local-observability-design.md`。本节只锁定它与 Tool、任务目录和证据引用之间的
数据边界；当前已完成 O0.0–O0.7 的平台骨架、runtime privacy/report v2、字段级安全
projector、直接 ID/hash/ref 关联、覆盖/指标投影，以及有界 SQLite 历史、保留/删除和
非阻断降级、免登录 loopback 安全壳、自动短期会话、会话内证据重新挂载、核心监控页面和跨运行比较；
O0 总门已通过。

### 8.1 任务目录是事实来源

本地任务目录继续保存授权 DOCX、工作副本、PDF/页面、render evidence、
`visual-review.json`、`validation.json` 与 `conversion-report.json`。观测索引不复制这些
文件，只保存明确允许的投影：

- 本地 `run_id`、opaque `task_ref`、SDK `session_id`、message ID/UUID、`tool_use_id`、
  `agent_id/type` 与 `parent_tool_use_id`；
- 来源序号、接收序号、墙钟时间、本地单调 offset、状态、耗时、计数、版本、
  Token/成本来源和错误码；
- `document_sha256`、`object_ref`、`render_ref`、visual evidence ref 与页码；
- 经过每种 Tool 字段 allowlist 生成的脱敏摘要；
- `verified/partial/broken/conflict` 关联质量、观测覆盖与本地证据可用性。

`run_id` 和 `task_ref` 只是应用壳内部索引，不加入五个公开 Tool schema，不泛化为跨任务
ArtifactRef，也不要求 Skill、Knowledge 或 Eval 消费。`tool_use_id` 与 `session_id` 继续
来自 Claude Agent SDK；网站不生成替代标识来冒充 SDK 事实。

`task_ref` 由薄应用壳在当前授权上下文中签发，不编码或 hash 绝对路径。观测索引不保存
句柄到绝对路径的映射。`docfit convert` 退出后历史运行默认 unmounted；用户可以在 Web
会话中通过同源 POST + CSRF 请求本地调试壳的可选平台适配器生成仅存于内存的目录 capability，
核心证据验证再按 v2 `run_id/task_ref/session/hash` 校验，成功后才可打开 task-relative
locator。核心转换、云端运行和平台无关观测模块不导入 AppleScript/GUI 实现；无适配器或
无图形会话时挂载能力保持 unavailable，历史摘要仍可查看，且不得退化为浏览器提交任意
绝对路径。平台适配器的真实 GUI smoke 不是 O0 核心完成门。挂载路径只在当前会话内存中
存在；v1 因缺少 run/task ID 最多标为 partial。O0 不建立全局任务注册表，也不扫描任意
目录恢复关联。

### 8.2 观测来源与原始载荷边界

权威来源只包括 Claude Agent SDK 公开消息与 lifecycle hooks、权限回调、薄应用壳的
run/backend 边界、五个 Tool 的既有结构化结果、`conversion-report.json` 和授权任务目录。
当前锁定的 `claude-agent-sdk==0.2.128` 能直接提供 ToolUseBlock `id`、
ToolResultBlock/hook `tool_use_id`、子消息
`parent_tool_use_id`、Tool hook `agent_id/type` 与 Subagent lifecycle `agent_id/type`。
OpenTelemetry 只能补充耗时/usage，不能覆盖这些直接 ID。

SDK 升级必须先用合成 message/hook fixture 重验字段和关联链；不能以私有 transcript
格式作为兼容层。

每种来源使用独立 allowlist projector。脱敏必须在原始事件进入异步队列、数据库、日志、
浏览器或导出之前完成；不得先完整序列化再遮盖。`prompt`、Assistant/Result 正文、
`ThinkingBlock`、`transcript_path`、`cwd`、raw Tool input/response/error、DOCX/PDF/图片载荷和
Provider 原始错误都不能进入观测通道。未知事件和未知字段默认丢弃。

O0.2 的内部 safe event 使用冻结的固定字段、固定 attribute-key allowlist 和强类型
hash/ref/error；单事件序列化上限为 64 KiB，projector 异常、schema/大小失败或单次达到
10 ms 时只返回固定 drop receipt，不保存 raw fallback。`--observation off` 时不安装额外
lifecycle hook/audit，也不执行 projector；`auto` 在有界队列/持久化完成前仍如实报告
event capture unavailable。

### 8.3 SDK 原生 transcript 生命周期

观测索引的 allowlist 不会阻止 SDK 子进程把完整 session transcript 写入本地磁盘。O0
实现必须为每次运行创建 mode `0700` 的私有临时 `CLAUDE_CONFIG_DIR`，不配置
`SessionStore`，在 client disconnect 后主动清理。hook 中的 transcript path 不进入索引，
也不能被 collector 用来补事件。

正常退出保留期为 0。崩溃残留只能在固定 DocFit 私有临时父目录中，通过无正文 owner
marker、进程身份、年龄和活跃 lock 检查后，于下一次 preflight 清理；owner 明确退出时可
立即清理，状态不确定时须超过 24 小时且无活跃 lock。不跟随 symlink，不扫描用户全局
config 或任意临时目录。清理失败只记录安全状态/数量/年龄区间，不记录路径。没有下一次
DocFit invocation 时，崩溃残留可能持续到操作系统清理，产品不得宣称 hard TTL。

### 8.4 关联证明

观测索引只根据直接键建立关系：

1. Tool use/result：Tool block `id` 至少与一个 ToolResultBlock/hook `tool_use_id` 相等；
   多个来源同时存在时，所有已观测 ID 必须一致；
2. 子 Tool/actor：子 Tool block `id = hook.tool_use_id`，且 hook 的 `agent_id` 与
   `SubagentStart/Stop.agent_id` 相等；
3. 父 `Agent` 调用/子消息：`Agent` Tool block `id = child.parent_tool_use_id`；
4. 当子消息 Tool ID 和 Tool hook 的 `tool_use_id` 相等时，才可把上述父调用桥接到具体
   `agent_id`；桥缺失时标为 `partial`；
5. hash/ref 关联只有在第 8.5 节的检查通过后才是 `verified`。

引用目标缺失或失效是 `broken`，两个直接来源矛盾是 `conflict`。Tool 名、相邻时间、
文件名或相同页码都不是关联证据。重复事件仅按 `source + source_event_id + kind/phase`
幂等合并；跨来源顺序保留各自 sequence 和本地单调时间，不伪造全局串行轨迹。

O0.3 的纯关联投影只接收已经通过 O0.2 schema/隐私门的安全事件和固定回执。语义相同而
接收时间不同的重复事件幂等合并；同一来源 identity 的事实矛盾保留全部变体并标为
`conflict`。Tool lifecycle、父 `Agent` 调用、子消息、具体 Subagent actor 和证据 scope
分别保留直接证明字段；缺桥、目标缺失和直接事实矛盾稳定映射为
`partial/broken/conflict`，不以时间、名称或预期调用顺序补边。

运行结果、观测覆盖、本地证据和 SDK transcript 保持四个独立维度。Tool/Subagent 数量、
耗时、Token/成本、cache/render execution、页面、图片字节、权限和错误指标标记为
`reported/estimated/unknown`；来源缺失或 coverage 降级时不能把未知总量补成 0。

### 8.5 引用检查

网站打开或定位本地证据前必须重新核对：

1. 用户已显式挂载目录，且 `task_ref` 在当前 Web 授权会话中解析到该根；
2. 文件仍存在且没有越出授权目录；
3. `document_sha256` 与文件内容一致；
4. `object_ref` 仍只用于其绑定的文档快照；
5. `render_ref`、Provider、profile、render hash 与证据文件一致；
6. 页码只在该 `render_ref` 内解释；
7. visual evidence ref 指向的派生视图仍可验证。

任一检查失败时，界面只显示“本地证据不可用”及安全原因分类。旧状态、计数和错误摘要
可以保留，但不能据此猜测正文、对象位置、当前页码或可恢复产物。

### 8.6 字段留存与 Tool 摘要

观测代码必须先选择允许字段，再持久化摘要；不得先把完整 Tool JSON 写入数据库或日志
后再尝试遮盖。首版 allowlist 是：

- inspect：文档 hash、focus、对象/风险/ref 数量；
- edit：输入/输出 hash、operation 类型/数量、opaque ref、committed 与 failure；
- render：intent、Provider、cache、render ref、页数、DPI、产物存在性；
- visual-review：render/evidence ref、mode、页码、图片数量与字节；
- validate：检查数、errors/issues/warnings、failure 与证据 ref。

禁止持久化论文/学校材料文本、expected/replacement 文本、对象完整文本、PDF/图片内容、
完整 validation evidence、Provider 原始错误体、完整 Agent prompt/response、隐藏思维链与
任何凭据。Agent/用户事件摘要必须由允许元数据生成固定模板，不把原始文本交给另一个
模型摘要。安全失败消息只能来自固定模板/allowlist；task artifact locator 只能保存相对
授权任务的 opaque 值，不能保存绝对路径。

脱敏、schema 或大小校验失败时丢弃整个可变载荷，只保存固定的 drop reason 和计数；
禁止 raw fallback、异常 `repr`、截断原文、base64 前缀或携带原值的死信队列。未知字段
默认不记录；增加 allowlist 字段必须先验证它不会泄露正文、身份、路径或凭据。

### 8.7 采集失败与可删除投影

观测投影必须支持按运行删除、全部清除和保留上限。删除投影不删除任务产物；删除任务
产物也不会由投影恢复。观测写入、索引损坏或页面未启动都不能改变 Tool 调用、原子
发布、权限判断、最终验证或 `docfit convert` 的返回结果。

页面分别展示运行结果、`complete/degraded/unavailable` 观测覆盖和本地证据可用性。
脱敏失败、观测队列/配额满、观测库锁/写入失败或 collector/UI 不可用时采用有界非阻断
drop，记录安全原因和数量，不把观测失败冒充转换失败。任务文件系统或整个共享卷耗尽
可能阻止 DOCX、证据和 report 写出，继续按 App/Tool storage failure 处理；不属于 O0
“转换继续”保证。进程没有最终结果时终态为 unknown。
覆盖状态依据来源 adapter 健康回执、drop/error 计数和已打开生命周期的配对完整性，
不能把本次未调用某 Tool 或未启动 Subagent 当成 source 缺失。
collector 重启后历史证据保持 unmounted；只有用户显式选择并验证目录后，才可通过
`conversion-report.json` 对账任务级状态和 hash，并标记来源。不得扫描任意目录、读取
SDK transcript 或反造逐事件时间线。

### 8.8 Conversion report v2

O0 把 `conversion-report.json` 从 schema v1 升级到 additive v2：保留全部 v1 转换字段，
新增 `run_id`、opaque `task_ref`、成功产物的 `final_sha256`、固定 shape 的
`observation_coverage` 和 `sdk_transcript` privacy 摘要。App 先构造不依赖 observer 的基础
报告；summary provider 异常时填入 `unavailable/unknown` 与安全错误码，仍原子写出 v2。
任务目录本身写入失败继续是 App storage failure。

reader 必须显式区分 v1/v2。v1 只在用户选择目录后作为临时 legacy summary 读取，不自动
导入历史或生成时间线；其观测覆盖为 unavailable、transcript 为 unknown、缺失计数为
null，且挂载关联最多 partial。未知更高版本拒绝猜测解析。观测 projector 不复制
v1/v2 报告中的绝对 artifact path、warning/detail 文本或未知字段，只保留状态、安全 code、
hash、计数、版本和 task-relative opaque locator。

### 8.9 Web 授权与资源硬上限

本地 Web 固定 loopback 并直接打开，不设置登录页、登录路由或一次性登录码；首次通过
Host 检查的合法请求自动建立服务端内存短期 session。Web 仍必须验证 Host、Origin 和
CSRF，禁用宽松 CORS；GET/HEAD 除建立/轮换短期安全会话外不得产生观测或任务管理副作用，
删除、挂载和打开本地证据只接受当前会话的同源 POST + CSRF。session/CSRF secret 不进入
URL、日志、数据库或导出；session 数量有硬上限，非交互/无头环境允许启动。候选目录和 artifact locator 必须
canonicalize，并拒绝 `..`、绝对路径、symlink/设备文件和挂载后逃逸。

首版硬上限与专题设计一致：单事件 64 KiB；队列 1024 事件或 16 MiB；单 run 10,000 事件
或 64 MiB；数据库/索引/WAL 合计 512 MiB；历史最多 30 天且 500 个已完成 run；可用空间
低于 1 GiB 或 5% 中较大者时停止观测写入。至少 10% 且 64 个 queue slot 保留给终态、
coverage、privacy、deny/error 和 Tool/Subagent terminal。资源压力先丢可重算指标，再丢
普通 start/allow；任何情况下不阻塞 SDK hook。
