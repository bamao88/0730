# DocFit Knowledge 与 Tools 设计（05）

> 状态：最终方案
> 日期：2026-08-05
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
- 每个学校专属结论必须能引用当前任务材料 hash 或当前用户确认；
- 精确格式值可以被规范化为本次 Tool 调用参数，但不写入长期 profile；
- 来源冲突或适用范围不明时，Agent 保留证据并询问，不用 Knowledge 补齐；
- 模板未观测到的样式属性保持为缺口；Agent 只能请求程序确定性解析或保留未决，
  不自行补值；
- 任务结束后，材料和推导结论按任务数据策略处理，不复制到产品 Knowledge；
- Eval 可以保存合成、脱敏或授权的学校场景，但 Eval fixture 不是运行时 Knowledge。

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

## 2. Tools

Tool 面按任务域注册。当前实现已注册且只注册论文转换链的五个 `docx_*` Tool；学校模板
提取的目标运行将改为五个 `template_*` Tool，当前尚未实现。OfficeCLI 1.0.143 负责 inspect、edit、
validate 与 `edit_feedback`，Adobe PDF Services SDK 4.2.0 adapter 负责 `baseline` 和
`candidate_verification`；Pillow 与 Poppler 只派生受控图片证据。公开 schema 不接受
Provider selector，固定后端失败时不回退。Adobe 路由使用
`pdfservices-sdk==4.2.0`、服务主体凭据和远程 API；核心转换与云端运行不依赖本地 Word、
AppleScript、图形会话、用户电脑或本地字体库存。每个未命中缓存的转换消耗一个
Document Transaction。本地调试壳的可选平台适配器不属于 Tool 或核心依赖。

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

### 2.2 领域 Tool 面与复用策略

#### 学校模板目标面

`docfit-school-extract` 的绿地生产合同只暴露：

```text
template_observe  → 不可变事实和原生页面证据
template_mutate   → Agent 已决定操作的原子执行
template_compare  → 计划与实际变化对账并返回原生图片
template_build    → 编译 candidate artifact
template_freeze   → 独立验证并原子发布 frozen artifact
```

Tool 不自动判断说明、示例、论文标题、来源优先级或视觉合理性。Agent 是任务结果 owner，
负责语义决定、检查 Tool 实际结果、根据 error/finding 修正决定或文档并重新执行；Tool
负责确定性事实、单次执行和机器门。五项合同如下。

`template_observe` 接受新 DOCX 或已有 `snapshot_ref` 查询。新观察可以选择
`visual_level: quick | authoritative | none` 和 structure/visible objects/styles/slots focus；
输出文档 hash、不可变 snapshot、稳定对象引用、命名/直接/继承/最终有效格式、表格/
文本框/内容控件、域/书签/分节/页眉页脚、PDF/逐页图片/contact sheet、对象页面映射和
不支持内容。查询文字时返回全部候选、上下文、格式解析和视觉位置，不做语义选择。

`template_mutate` 接受当前 snapshot 与显式 operation plan。删除操作只允许六种模式：

- `clear_text_preserve_container`；
- `remove_inline_fragment`；
- `remove_container`；
- `remove_bounded_block`；
- `clear_cell_preserve_grid`；
- `unwrap_control_preserve_content`。

槽位操作可以在既有段落、表格单元格、段落流边界或受支持物理锚点 materialize slot，
也可以登记 manual 区域。Tool 校验 snapshot 所属、目标 ref、expected text/fingerprint，
全部操作原子执行，重开输出并检查需保留容器和非目标内容；成功返回新 hash、after
snapshot 与 `mutation_ref`，失败不发布。Tool 不选择 target、mode 或 slot 语义。

`template_compare` 接受 before/after snapshot 与 mutation ref，同时比较对象增删改、固定
文字、样式签名、表格网格、节、页眉页脚、分页边界、槽位容器、页数和视觉布局。输出
`expected_changes`、`unexpected_changes` 和 `visual_review`。图片直接作为原生 image
content 返回：短文字清空包含 crop 与修改后整页；容器删除包含目标/相邻页；连续块或
表格包含 contact sheet 与边界页；分节、页眉页脚、页数变化或映射失败扩大检查；最终
候选覆盖全部页面。Tool 不输出视觉 pass/fail，Agent 解释图片是否合理。

`template_build` 接受最终 snapshot 以及 Agent 确认的 sources、fixed regions、slots、
manual regions、gaps 和 visual findings。它绑定最终模板 hash，检查 `slot_id`、字段完整性、
引用时效和样式来源，输出 `clean-template.docx`、`template-artifact.json`、
`visual-review.json`、`build-report.json`。状态只能是 `candidate`。

`template_freeze` 独立重读 candidate，不信任前序 Tool 或 Agent 自报。它验证 DOCX package、
模板/manifest hash、自动槽位唯一定位、内容种类与基数、固定内容指纹、manual/gap、绑定
最终 hash 的全部页面审查、blocking findings、来源未变化、无旧 snapshot 引用和 bundle
完整性。成功才返回 `status: frozen` 与 `artifact_ref`；失败返回 `published: false` 和
findings。它是唯一 frozen 发布边界。

Tool 的 `ok`、`error` 或 `blocked` 都是单次调用结果，不是对整个任务的终态裁决。
`template_mutate` 成功但 compare 显示误伤时，Agent 必须继续修改；build/freeze 拒绝时，
Agent 必须依据 finding 回到相应决定、审查或文档操作点修正并重新提交。只有确实缺少
必要用户裁决、授权输入或不可替代外部能力时，Agent 才把任务作为阻塞交回用户。

这五项不是一个隐藏语义工作流。`template_compare` 只报告事实，`template_build` 只编译，
`template_freeze` 只验证；Agent 仍在 observe/mutate/compare 之间做开放式判断。

#### Skill 决策编译层

Agent 的语义判断不能直接停留在自然语言中，也不能由 Tool 猜回去。生产 Skill 携带三个
确定性脚本：

| 脚本 | 输入 | 输出 | Tool 消费方 |
|---|---|---|---|
| `compile_mutation_plan.py` | Agent 的目标、前置指纹、删除模式和槽位决定 | `mutation-plan.json` | `template_mutate` |
| `compile_review_record.py` | compare metadata 与 Agent 对 finding/图片的判断 | `review-record.json` | build/freeze 证据 |
| `compile_artifact_spec.py` | 最终来源、责任、槽位、样式、manual/gap 和 review record | `artifact-spec.json` | `template_build` |

脚本与 Tool 共享版本化类型模型，负责字段完整性、ID/ref/hash 一致性、canonical 序列化和
失败时不写部分输出。它们只读取当前任务中的决策 YAML/JSON 和 Tool 已返回的结构化
metadata；不读取或修改 DOCX、不调用 Tool、不生成语义决定、不解释图片、不发布产物。
消费方 Tool 必须重新校验，不能把“脚本执行成功”当作权威文档事实。

Tool 内部实现可以拆成 `observation.py`、`mutation.py`、`comparison.py`、`artifact.py` 和
`validation.py`。另有开发脚本仅用于原型、fixture 和人工调试，不与生产 Skill scripts
混用。

#### 当前论文转换实现

下面定义的五个 `docx_*` Tool 是当前论文转换链面向 Agent 的稳定契约，不表示底层 DOCX 能力必须由 DocFit 从零实现，也不构成学校模板目标面的兼容约束。

```text
Claude Agent SDK 中的主 Agent / 受限只读 Subagent
        ↓ 选择规则与下一步
五个 DocFit Tool
        ↓ 确定性适配
MCP / CLI / library / cloud API
```

预处理发生在 `docx_inspect` 内部，后处理发生在 `docx_edit` 的后置检查、`docx_render`、`docx_visual_review` 和 `docx_validate` 内部。它们不是独立服务，也不拥有任务状态。底层后端不调用另一个模型或 Agent 来解释论文；语义与视觉判断可以由主 Agent 直接完成，或由主 Agent 通过 SDK 原生 `docfit-unit-analyst` 完成局部只读分析。恢复、跨范围合并、写入和发布选择始终由主 Agent 完成。

| 论文转换需要的能力 | 在 DocFit 中的归属 |
|---|---|
| 模板和论文的结构化预处理 | `docx_inspect` 内部 |
| 当前任务对模板证据的解释 | Claude Agent SDK 主会话；必要时使用受限 `docfit-unit-analyst` |
| 通用格式概念、识别方法与处理模式 | 产品内置 Knowledge Package |
| 学校规则、模板证据与精确参数 | 当前任务材料、Agent 当前会话与 Tool 调用参数 |
| 模板样式的属性级观测 | `docx_inspect` 内部 |
| 文字要求与有效样式的逐属性交叉验证 | Agent 解释当前任务来源；Tool 返回可追溯观测事实和作用范围 |
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

第一版不在这些实现之上再抽取通用 Provider 层，而是在五个 Tool 内固定适配两个
具体后端：

| 具体后端 | 固定职责 | 不负责 |
|---|---|---|
| OfficeCLI | `docx_inspect`、`docx_edit`、`docx_validate` 的底层执行，以及 `edit_feedback` 高频截图 | Adobe 服务分页真实性和候选验证转换 |
| Adobe PDF Services API | `baseline` 与 `candidate_verification` 的完整 PDF 导出 | 文档语义分析、编辑、常规验证和高频逐页截图 |

两个后端承担不同职责，不实现同一套可互换接口。Agent、Skill 和应用壳都不传入
后端选择；固定路由只存在于五个 Tool 的薄适配代码中。当前 schema 中已有的
`provider` 字段仅记录实际执行后端、版本与环境，供证据审计使用，不表示存在
Provider 注册表、动态选择、自动回退或故障转移平台。

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

第一版后端已经固定为 OfficeCLI 与 Adobe PDF Services API。以下实现只保留为未来能力
调研或对照入口，不参与第一版运行时选择：

| 候选 | 优先验证的能力 |
|---|---|
| [Safe Docx](https://github.com/UseJunior/safe-docx) / `docx-core` | 对既有 DOCX 的局部编辑、格式保留、稳定定位和文档比较 |
| [SecurityRonin/docx-mcp](https://github.com/SecurityRonin/docx-mcp) | OOXML 局部操作、修订、批注和结构审计 |
| Aspose.Words | 服务端快速迭代渲染、逐页图片和页面布局信息；需要验证授权、字体与目标样本保真度 |
| LibreOffice | 低成本预览和基础可读性检查；不能作为 Adobe 交付转换证据 |
| 其他 DOCX MCP | 作为能力来源或对照实现，不默认把完整工具面暴露给 Agent |

OfficeCLI 与 Adobe PDF Services API 分别按自己的固定职责用相同 fixture 取证；不要求二者
通过一套假想的可互换能力测试。至少验证：

- 目标学校样本中的段落、表格、图片、公式、目录、节和页眉页脚；
- 无操作另存和受控修改后，package 可独立解析且 OfficeCLI 可重新读取；
- 修改只影响目标对象，源文件保持不变；
- 错误能够转成 DocFit 的 `ok`、`needs_input` 或 `error`；
- 在开发机和 CI 环境中可安装、可锁定版本、可重复运行；
- 渲染结果能够报告实际后端、版本、转换 profile、环境可见性和已知兼容差异。

PoC 阶段可以直接调用底层命令验证能力；产品路径只向 Agent 暴露 DocFit 的五个
高层 Tool，避免 Skill 绑定 OfficeCLI 或 Adobe PDF Services API 的私有命令。固定后端的薄适配
发生变化时不应要求修改 Skill 或 Knowledge。

### 2.3 当前论文转换最小工具面

优先提供少量、能力清楚的工具，避免 Agent 在大量细粒度工具中选择：

```text
docx_inspect    分析结构、样式、可见对象和风险
docx_edit       在工作副本上执行一组受控编辑操作
docx_render     按固定路由生成页面图片、必要的 Adobe PDF 和渲染摘要
docx_visual_review  将指定页面、裁剪图或对比图作为图片证据返回给当前 Agent
docx_validate   对源文件、最终文件和学校要求做确定性检查
```

本段只约束当前论文转换面。它不要求学校模板目标能力塞进现有 Tool 的 `action` 或
`focus` 参数；学校模板采用 2.2 已确定的绿地五 Tool 合同。

公开 schema 使用兼容 backend 已验证的扁平 JSON Schema 子集：对象、数组、枚举、
`required` 和 `additionalProperties` 可以使用，但不使用 `oneOf`、`anyOf` 或 `allOf`。
不同 action 的专属必填字段由 Tool runtime 在执行前校验，错误仍归一为 DocFit
`needs_input` / `error`。这避免兼容模型把 composition 关键字误生成为普通参数，同时
保留当前转换五个 Tool 名称和语义，不为每种 conversion operation 拆新 Tool。

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

冻结模板 Interface 实施后，`docx_inspect` 还必须为产物校验提供客观事实：冻结模板
hash、固定内容指纹、候选区域 locator 的唯一命中数、内容种类/基数约束，以及生成、
重复、条件、manual、unresolved 和 gap 的结构证据。它不自行决定区域责任或某段学生
内容应进入哪个槽位；也不能用页码、bbox
或单个近似文字命中冒充唯一 locator。本段是目标合同，当前 schema 与实现状态以 06
第 6.9 节为准。

#### 2.4.1 样式观测与来源交叉验证合同

当前 `docx_inspect` 保留转换侧已有观测能力；学校模板目标实现由 `template_observe`
承担完整合同。程序对每个相关属性输出：

- 可绑定对象、语义候选和作用范围；
- 命名样式、直接格式、继承链、文档默认值和最终有效值；
- `observed`、`missing`、`conflict` 或 `unresolved` 状态；
- 来源 hash/ref 和与页面/对象的绑定。

Agent 将当前任务文字要求、用户确认与这些观测逐属性交叉验证，并记录
`current_task_requirement`、`template_observation`、`inherited`、`conflict` 或
`unresolved`。字体、字号、行距、边距等标量，以及附着关系、相对顺序和有限编排字段，
都必须带明确作用范围。

Word 继承和文档默认值只解释模板当前如何生效，不是目标值补全来源。要求与观测冲突时
不静默排序；缺少当前任务明文、适用范围不明或多来源冲突时保持 `unresolved`，不使用
产品经验、历史学校、样式名或内置国家标准值。Tool 返回事实，Agent 判断语义角色并在
高影响冲突时询问用户。

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

统一入口按 intent 生产新的快速反馈或 Adobe 交付候选证据，不为不同引擎增加新的 Agent
可见 Tool，也不在图片被 Agent 查看前把候选称为最终交付证据。

输入示例：

```yaml
input_docx: /path/work-v2.docx
render_intent: edit_feedback
baseline_render_ref: null
focus_object_refs: []
```

`render_intent` 只有三个稳定值：

```text
baseline               首次建立 Adobe 服务转换分页基线
edit_feedback          当前修改过程中的低成本页面反馈
candidate_verification 为当前候选文档生成可供 Agent 判断是否继续修改的 Adobe 交付证据
```

第一版路由是封闭矩阵：

| `render_intent` | `fidelity` | 固定后端 |
|---|---|---|
| `baseline` | `official_service_conversion` | Adobe PDF Services API |
| `edit_feedback` | `approximate` | OfficeCLI |
| `candidate_verification` | `official_service_conversion` | Adobe PDF Services API |

公开输入不提供 `provider`、`backend` 或“自动选择”参数；适配器不能根据可用性静默
改走另一后端。`candidate_verification` 表示“这份候选文档值得进行 Adobe 交付检查”，
不表示图片已经被 Agent 查看，也不能在 Tool 返回时称为 final。

Tool 不维护“第几轮”的状态。它只根据 `document_sha256`、输入 intent、
`baseline_render_ref`、后端/转换配置/环境证据和缓存键生成或复用证据；是否继续修改、
何时把 candidate 视为下一次比较的 baseline，均由 Agent 判断。

对同一份持续修改的论文，常见成本形态是首次使用一次 `baseline` 和一次
`candidate_verification`，后续修改则复用上一 candidate 作为 baseline，只为新候选
调用一次 Adobe PDF Services API。这只是成本预期，不是 Tool 调用顺序、次数上限或工作流规则。

Tool 负责：

- OfficeCLI `edit_feedback` 直接生成高频页面截图；该路由的 PDF 是可选产物，不是 M1 完成门；
- Adobe PDF Services API 对 `baseline` 或 `candidate_verification` 的完整 DOCX 一次性导出
  PDF，再在本地把 PDF 转成逐页图片；
- 返回 render intent、provider、SDK 版本、页面数、页面尺寸、DPI、服务管理环境和转换警告；
- 声明 `fidelity`：`approximate`、`official_service_conversion` 或 `unknown`；
- 可选接受 `baseline_render_ref`，并在新证据中记录为 `parent_render_ref`；该引用只
  建立证据关系，不把旧页码或旧 `object_ref` 升级为当前文档事实；
- 可以随结果返回一张有页数和字节上限的 contact sheet image content block，让简单
  场景立即开始观察；
- 可选生成对象与页码、页面区域的绑定，供 Agent 定位高风险页面；
- 接受可选 `focus_object_refs`；OfficeCLI 能力允许时返回这些对象所在页面及相邻页面，Adobe 路由无法可靠映射时返回 warning，并允许 Agent 改用 contact sheet 或全篇预览；
- 基于输入 hash、provider、SDK 版本、转换 profile、环境证据和渲染参数复用缓存。

Adobe 路由写入 `provider.name: adobe_pdf_services`、
`fidelity: official_service_conversion`、`conversion_profile: adobe_pdf_services_default`
和 `target_application: null`。这是 Adobe 官方服务 API 的转换证据，不是 Microsoft
Word 桌面应用真值。服务未公开的字体库存、字体替代和渲染主机细节统一标记为
`service-managed` / `opaque`，不得使用本机 Word 版本或本地字体指纹填充。

第一版同时实现上述三条固定路由。任何 Adobe 路由暂不可用时，`docx_render`
应返回明确的 `error` 或 `needs_input`，不能静默降级成 OfficeCLI 迭代渲染；
下游验证在缺少所需 Adobe 证据时返回 `ok` 加 `verification_gap` warning。没有
当前 Adobe candidate 证据的产物不能通过第一版端到端交付门。

输出示例：

```yaml
status: ok
cache_hit: false
render_ref:
  document_sha256: ...
  render_sha256: ...
  render_intent: candidate_verification
  fidelity: official_service_conversion
  target_application: null
  provider:
    name: adobe_pdf_services
    version: 4.2.0
    operation: create_pdf_from_docx
  conversion_profile: adobe_pdf_services_default
  font_environment:
    source: adobe_managed_service
    visibility: opaque
    fingerprint: null
  font_substitutions: null
  revision_display: document_default
  parent_render_ref: ...
  page_count: 80
  dpi: 144
artifacts:
  pdf: /path/render-v2/document.pdf
  pages: /path/render-v2/pages
  contact_sheet: /path/render-v2/contact-sheet.png
  layout_map: /path/render-v2/layout-map.json
warnings: []
```

上例是 Adobe `candidate_verification`，因此必须包含完整 PDF；缺失时该调用失败，
不能只用截图伪造交付转换证据。OfficeCLI `edit_feedback` 可以不包含
`artifacts.pdf`。缓存命中时返回同一证据并设置 `cache_hit: true`，不伪造新的
`render_sha256`。

当 OfficeCLI 支持页面布局信息时，`layout-map.json` 使用明确坐标系并绑定同一个 render ref：

```yaml
schema_version: 1
render_sha256: ...
pages:
  - page: 3
    first_object_ref: { ... }
    last_object_ref: { ... }
    section_refs: [{ ... }]
    text_anchors:
      first: "2 材料与方法"
      last: "2.1 试验设计"
    coordinate_space:
      unit: px
      origin: top_left
      width: 1190
      height: 1684
      dpi: 144
    elements:
      - object_ref: { ... }
        type: table
        bbox: [88, 302, 1070, 1290]
        mapping_quality: exact
```

元素映射只能引用同一文档快照的 opaque `object_ref`。OfficeCLI 只能估算时使用 `mapping_quality: approximate`；无法可靠映射时省略该元素并返回 warning。bbox 用来把视觉发现定位回候选对象，不是内容或语义事实，也不能由 Agent 直接转换为 OOXML 路径。

页码、首尾对象、节引用、文字锚点和 bbox 都只在对应 `render_sha256` 内有效。
Adobe 转换第 N 页与 OfficeCLI 第 N 页没有隐含等价关系。同一文档 hash 的
跨后端页面只能使用当前快照的 `object_ref`、节引用、文字锚点和 mapping quality
关联；不能因为页码相同就自动关联，也不能把页面升级为新的编辑身份或全局 Page
Model。文档 hash 变化后必须重新 inspect，旧 `object_ref` 不得用于新快照。

OfficeCLI 反馈路由可以记录本地字体库存指纹和已知替代关系。Adobe 路由不能观察
服务端字体细节，只能记录服务管理且不透明；若当前任务明确要求不可替代字体，最终
验证必须保留这一不可观测风险或转人工确认，不能伪造精确字体证据。

OfficeCLI 与 Adobe PDF Services 可能产生分页差异。Tool adapter 应报告实际后端、
版本、可见环境证据和 fidelity；Skill 应把高风险分页交给 Adobe candidate 和人工查看，
不把近似渲染说成交付真值。

Adobe 路由对完整 DOCX 一次上传并转换成 PDF，逐页 PNG、contact sheet 和裁剪图在
本地从该 PDF 产生，不按页重复调用 API。每个缓存未命中的转换消耗一个 Adobe
Document Transaction；缓存命中不得重复上传。转换 profile 或 SDK 版本变化必须形成
新的缓存键和 render ref。服务不暴露桌面应用的修订显示开关，因此证据记录
`revision_display: document_default`，可见修订标记由页面复核和 OOXML 检查承担。

Adobe SDK 4.2.0 的默认网络 timeout 对真实复杂 DOCX 上传过短。第一版 adapter 固定
使用 30 秒 connect timeout 与 120 秒 read timeout；后者也覆盖 SDK 上传写入等待。
这些值写入 Provider evidence 便于复现，但不是公开 Tool 参数，也不引入动态 Provider
配置。超时仍映射为可行动且不泄露原始 SDK 错误体的 provider failure；只有调用条件
实际变化时才重试。

`docx_render` 的文件路径或“渲染成功”不等于 Agent 已经看过全部图片。Tool 可以随
结果返回一张有大小限制的 contact sheet，让简单场景直接开始观察；需要更多页面、
裁剪或比较时，Agent 再调用 `docx_visual_review`。这不是固定的两步流程。

### 2.7 `docx_visual_review`

这个 Tool 解决的不是“再做一次渲染”，而是把已有 `render_ref` 指向的页面图片作为
受控视觉输入送回当前 Agent。[Claude Agent SDK 的 in-process MCP Tool](https://code.claude.com/docs/en/agent-sdk/custom-tools)
支持在结果中返回 `image` content block；DocFit 使用这一原生能力，不调用 Adobe PDF Services API、
CLI 渲染、第二个模型或另一个 Agent。

输入示例：

```yaml
render_ref: ...
mode: pages
pages: [1, 2, 3]
focus: [overflow, blank_page, header_footer, figure_table_layout]
baseline_render_ref: null
```

支持的最小模式：

```text
pages          返回指定整页图片
crops          返回指定页的矩形裁剪图
contact_sheet  把多页缩略图组合成有页码标识的总览
compare        返回基线与当前版本的并排图或差异辅助图
```

Tool 返回三项彼此一致的内容：

1. `content` 的首个 text block 是完整结构化结果的紧凑 JSON 镜像；
2. `content` 中的一个或多个图片块，供当前 Agent 直接观察；
3. `structuredContent` 中的文档 hash、渲染 hash、render intent、fidelity、Provider、
   字体、页码、裁剪坐标、图片 hash、变换方式、元素映射和 evidence ref。

之所以保留 JSON text 镜像，是因为当前 `claude-agent-sdk==0.2.128` 的 in-process MCP
bridge 会构造 content blocks，却不会把 MCP `structuredContent` 传入 Agent 可见结果。
DocFit 不据此创建第二套返回协议；两处 JSON 必须语义一致，测试直接比较解析后的
对象。五个 Tool 都声明足以避免 CLI 把正常结果转成不可读 spill 文件的结果上限。

结构化结果示例：

```yaml
status: ok
document_sha256: ...
render_sha256: ...
mode: compare
evidence:
  - evidence_ref: visual-...
    page: 12
    image_sha256: ...
    view: side_by_side
    baseline_image_sha256: ...
    current_image_sha256: ...
    layout_map_ref: layout-...
    candidate_object_refs: [obj-...]
warnings: []
```

约束：

- Tool 不修改 DOCX、已有渲染文件或 Agent finding；裁剪、contact sheet 和 compare
  是已有页面图片的派生视图，可以产生新的 visual evidence/image hash，但不产生新的
  `render_ref`；
- Tool 不调用 Adobe PDF Services API、OfficeCLI 或任何其他渲染后端；
- Tool 不输出 `pass`、`fail` 或“版式正确”等语义判断；
- Tool 只读取本次任务授权目录内、由有效 `render_ref` 指向的图片；
- 图片必须绑定当前文档 hash、渲染配置、Provider、版本、字体和页码；
- `pages` 参数中的页码只解释为所提供 render ref 的页码；不得拿其他 Provider 或旧 render 的页码直接索引当前图片；
- 存在元素映射时，Tool 返回当前视图覆盖的候选 `object_ref`、bbox 和 mapping quality；不存在时不猜测；
- 文档修改后，旧 `render_ref` 不能用于证明新文档结果；
- `compare` 只在页面尺寸、DPI、Provider、版本、字体环境、render intent 和 fidelity
  可比较时生成差异辅助图，否则返回 warning；
- 裁剪、缩放、拼接、压缩和差异着色都必须在元数据中声明，不能把变换后的图片伪装成原始页面；
- 单次返回页数和图片字节数必须有限制，Agent 通过分批调用完成整篇复核；应用壳把
  Claude Agent SDK subprocess buffer 固定为 16 MiB，以承载 Tool 当前最多 8 MiB 原始
  图片经 base64 编码后的消息；不能依赖 SDK 默认 1 MiB buffer；
- 整页缩放后无法可靠辨认的小字、域结果、图题或页边界必须用同一 render ref 的
  `crops` 模式补证。可见应用错误标记、断裂域/交叉引用、未完成占位或截断必需内容由
  Agent 记录为 blocking finding，Tool 本身仍不做语义判断；
- 对同一 `render_ref` 的多次调用只是读取不同视图，不产生新文档渲染，也不表示进入
  新一轮；
- `focus` 只是给 Agent 的检查提示，不改变图片，也不由 Tool 生成结论。

Agent 观察图片后生成结构化 visual findings，至少包含：

```yaml
document_sha256: ...
findings:
  - evidence_ref: visual-...
    page: 12
    category: overflow
    severity: blocking
    observation: ...
    suggested_action: ...
reviewed_pages: [1, 2, 3]
```

应用壳负责把当前 Agent 的结构化 findings 保存为 `visual-review.json`。`docx_validate` 可以确定性检查 report 是否绑定当前文档、是否覆盖要求页面、是否存在 blocking finding，但不得把 Agent 的视觉判断改写为确定性 Tool 事实。

当调用者是 `docfit-unit-analyst` 时，它只能形成局部 finding、依赖、证据请求和候选
操作。它没有 `docx_render`；缺少页面时返回 `needs_more_evidence`，由主 Agent 决定
是否生成新 render、是否再次委派以及如何把局部结论合并进最终审查报告。

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
- 渲染成功，字体和 provider 警告已呈现；
- 视觉审查报告绑定当前文档与当前 render，要求页面已经覆盖；
- 没有被忽略的 blocking visual finding；
- 要求 Adobe 交付转换证据时，存在绑定当前文档、已由 Agent 覆盖必查页面且
  没有后续文档修改的 `render_intent: candidate_verification`、
  `fidelity: official_service_conversion` 视觉证据；否则保留 `verification_gap`。

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
内容，也不根据 `render_intent` 自行宣布候选已经 final。

“两个固定后端各自在 Tool 层通过职责契约”和“第一条端到端链路已经跑通”是两个
不同结论。M1 必须分别验证 OfficeCLI 的高频能力和 Adobe PDF Services API 的低频真实性
能力；M2 再把二者组合为 `baseline`、`edit_feedback` 和
`candidate_verification` 的完整链路。
如果缺少绑定当前文档且已完成必要视觉覆盖的 Adobe candidate 证据，只能报告部分开发
能力可用，不能通过 M2 交付门。

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

学校模板生产端的 package/hash/槽位/固定内容/逐页审查和来源检查由
`template_freeze` 独立完成，`docx_validate` 不能替代 frozen 发布。转换端消费 frozen
artifact 后，`docx_validate` 仍需核对输入 artifact ref/hash，固定、填充、生成、重复、
条件、人工和未决责任没有被越过，固定内容未被未经证据改写；学生源内容清单中每个任务级 `source_item_id` 恰有一个
明确 disposition（已放置到槽位，或有明确不放置原因）；不存在缺项、重复放置、无理由
消失或越过 manual/gap 的自动处理。覆盖未闭合是 blocking issue，而不是普通 warning。
这是当前转换验证职责，不改变学校模板五 Tool 合同。

## 3. 内容安全的实现边界

“内容不得静默丢失”是产品不变量，但不要求先建设全局内容身份平台。

### 3.1 冻结模板产物 Interface

学校提取端与转换端通过任务级产物合同耦合，而不是通过 Skill 名称、调用轨迹或共享
内存耦合。稳定交付是一个原子目录：

```text
frozen-template-artifact/
├── clean-template.docx
├── template-artifact.json
├── visual-review.json
└── freeze-report.json
```

这些文件共同组成一个 artifact；消费者不能把 manifest、视觉审查或 freeze report 与另
一个模板任意组合。`template-artifact.json` 绑定 DOCX 精确 SHA-256 和来源 hash，表达固定、
填充、生成、重复、条件、人工与未决责任。自动区域至少具有任务内唯一 `slot_id`、冻结
快照唯一 locator、期望内容种类和基数；内容种类为 scalar、paragraph stream 或 composite，
manual 是区域责任而不是伪内容类型。生成区域保留生成关系，重复区域不从示例数量推导
基数，条件区域保留适用条件。locator 由 snapshot-bound 结构引用及前置指纹/上下文支持；
页码、bbox 或近似文字只能作为视觉辅助。索引不承诺跨模板修改、跨任务或跨运行稳定。

manifest 还记录固定内容指纹、manual/gap、来源与冲突、样式观测值与要求值、适用范围、
未决项以及 visual findings。`visual-review.json` 记录绑定最终 template hash 的逐页审查；
`freeze-report.json` 记录独立冻结检查与最终 artifact ref。

`template_build` 先输出相同形状的 candidate bundle，但 `build-report.json` 不能替代
`freeze-report.json`，candidate 不能作为冻结输入交付。`template_freeze` 必须独立重读
bundle、模板 package 与来源，验证 hash、槽位、固定内容、逐页审查、blocking finding、
旧 snapshot 引用和目录完整性，然后原子发布上述 frozen 目录。失败时不发布。

转换以冻结模板的字节副本开始。若多个放置操作会改变文档 hash，Tool 必须先验证并
原子提交同一快照上的整组操作，或为后续操作显式重新 inspect 并产生经过验证的新引用；
不得把旧槽位 locator 静默套到新快照。模板固定内容与可填区域必须可确定性区分，
未经当前证据不得改写固定内容。

转换端还为只读学生快照生成任务级源内容清单。每项使用绑定学生 source hash 的 opaque
`source_item_id`、类型、顺序和指纹参与覆盖验证；最终 disposition 只能是放置到明确
槽位，或附明确理由的不放置。它不要求公开完整正文，也不形成跨任务 Content Ledger。

产物可以由 `docfit-school-extract`、人工或其他受控适配器准备 candidate，但只有同一
`template_freeze` 合同能发布 frozen。应用壳只验证 artifact ref、shape、hash、授权路径
和合同版本，不解释学校语义。字段级 typed schema 必须在 06 第 6.9 节实施前用消费者和
fixture 锁定；当前 M2 代码尚未实现本合同。

### 3.2 Tool 间的对象引用

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

### 3.3 最小策略

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

### 3.4 文档操作权威路线与 Subagent 写入边界

当前转换薄应用壳对主 Agent 暴露五个 `docx_*` Tool，并另外暴露只读的 Skill/Knowledge/任务证据发现面
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

### 3.5 主 Agent 直接读取权限与受信任 Bash/Write

主 Agent 的内置工具面固定为 `Skill`、`Read`、`Glob`、`Grep`、`Bash`、`Write`、
`AskUserQuestion` 与类型受限的 `Agent`；当前任务域的 `mcp__docfit__...` Tool 直接调用。
Read/Glob/Grep 不加入自动批准集合；SDK `PreToolUse` hook 与 `can_use_tool` 使用同一策略：

1. 把相对路径按项目 cwd 解析并 canonicalize 为真实绝对路径；
2. 只允许项目 `.claude/skills/**`、产品 Knowledge Package、当前任务 `input/**`、
   `work/**` 与 output 根；
3. `Glob/Grep` 必须提供显式搜索根；Glob pattern 和 Grep 的可选 glob filter 不允许
   绝对路径、`~` 或 `..`，Grep 正则只作为内容模式；
4. 拒绝 `~/.config/docfit/**`、`.env`、`.git/**`、常见凭据文件、其他任务、项目外路径、
   非普通文件和 symlink 逃逸；搜索树含 symlink 或敏感文件时整次搜索失败；
5. 允许时把 canonical path 写回 Tool input，拒绝时只返回固定安全原因，不记录路径或正文。

Bash/Write 与当前任务域 Tool 加入自动批准集合；Bash/Write 不安装 DocFit 路径 hook，
可访问 Agent SDK 子进程本来可访问的路径和环境，包括直接 Read allowlist 之外的文件与
后端凭据。系统提示要求不输出凭据或文档正文，观测 projector 丢弃命令、路径和内容，
但这是一项显式信任决策，不是 sandbox。Edit 与网络工具继续默认拒绝。

Read/Glob/Grep 本身不能修改文件；Bash/Write 的存在不改变任务域 Tool 契约或完成门。
Bash/Write 的参数与结果只记录
无载荷生命周期元数据，不进入权限事件或观测索引。

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
原始 OOXML、Adobe PDF Services 页面证据或人工页面复核验证的高风险结论，Tool 必须返回
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
| `engine` | OfficeCLI 或 Adobe PDF Services API 失败或返回畸形结果 | 仅在 `retryable: true` 且调用方式或范围有实际变化时重试固定后端 |
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
| 高风险分页只有 OfficeCLI 近似渲染结果 | `ok` + `verification_gap` warning | Adobe PDF Services API 证据缺失，需要恢复固定后端或人工复核 |

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
- 渲染缓存由输入 hash、实际后端版本、转换 profile、可见环境证据和参数共同决定，任何一项变化都自动失效；
- 可以使用 `docx_render` 附带的有限 contact sheet 开始全局扫描，再按风险通过
  `docx_visual_review` 分批读取整页或裁剪图；单次图片数量和字节数受限；
- OfficeCLI 能生成元素映射时，视觉证据同时返回视图覆盖的候选 `object_ref`，减少 Agent 从截图问题到编辑目标的往返；
- Adobe 服务可用时，首次修改前建立一次 `baseline`，之后每个真正需要判断的候选只
  生成一次 `candidate_verification`；上一候选可作为下一候选的
  `baseline_render_ref`，不额外调用 Adobe PDF Services API 制造“新一轮基线”；
- 对同一 `render_ref` 的页面、裁剪和 compare 查看复用
  `docx_visual_review`，不重复调用渲染后端；
- 相同文档 hash 和相同 Adobe 转换策略直接复用 PDF 与逐页图片，不重复上传或消耗额度；
- 修改过程中优先复核变化页及相邻页，最终交付前仍需覆盖全部当前页面；
- `docx_validate` 复用解析代码，但必须对最终文件重新取证，不能复用旧结论；
- Agent 只决定重试、重新取证、缩小范围、换公开 Tool 或询问用户；具体后端由 Tool
  根据固定职责路由，Tool 内部不启动隐藏的 Agent loop，也不执行自动故障转移。
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
证据、源 hash、当前 Adobe candidate 与独立验证完成门。

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
| 转换反复出现漏章、重复放置或固定模板内容漂移 | 实施 3.1 的任务级冻结模板/覆盖合同；不建设全局 ArtifactRef 或 Content Ledger |
| 模板样式缺口或来源冲突反复出现 | 强化 `template_observe` 的有效格式与作用范围事实，以及 artifact 中的来源/冲突表达；不增加 Knowledge 默认值 |
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
耗时、Token/成本、cache/Adobe、页面、图片字节、权限和错误指标标记为
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
