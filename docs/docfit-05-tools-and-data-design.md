# DocFit Knowledge 与 Tools 设计（05）

> 状态：最终方案
> 日期：2026-07-31
> 原则：Knowledge 保持可读，Tools 保持确定性，复杂性不进入 Agent runtime。

## 1. Knowledge

### 1.1 定位

Knowledge 是 Claude Agent 按需读取、由产品持续积累的论文领域资产。它分为两类：

- 通用 Knowledge：论文结构、Word 常见陷阱、处理示例；
- 学校 Knowledge：某学校在特定学历、专业范围、语言、学年或模板版本下的官方来源、要求、模板和示例。

Knowledge 不要求团队预先穷举所有学校。学校资料按版本和适用范围组织；具体持久化与检索方式是可替换实现。

### 1.2 组织示例

一种简单的文件组织方式如下：

```text
knowledge/
├── common/
│   ├── thesis-structure.md
│   └── word-layout-pitfalls.md
└── schools/
    └── hunannongye/
        └── v1/
            ├── manifest.yaml
            ├── school.md
            ├── sources/
            │   └── <official files>
            ├── template.docx          # 需要套用模板时
            ├── format-profile.yaml    # Tool 需要精确参数时
            └── examples/              # 少量已确认示例，可选
```

除 `manifest.yaml`、`school.md` 和来源材料外，其他文件按真实需要添加。

### 1.3 最小 manifest

```yaml
school_id: hunannongye
version: v1
title: 湖南农业大学学位论文格式
degree_level: undergraduate
program_scope: general
language: zh
academic_year: 2026
applies_to: 中文本科毕业论文
content_digest: sha256:...
sources:
  - path: sources/official-template.docx
    description: 学校官方模板
    sha256: ...
review:
  reviewed_by: ...
  reviewed_at: ...
notes: ...
```

同一学校可以拥有多个 Knowledge 包，选择时需要结合学历层次、专业范围、语言、学年和显式版本。

manifest 只说明这个包是什么、来自哪里、适用于什么。`content_digest` 覆盖该版本中会影响 Agent 或 Tool 行为的 Knowledge 文件，来源文件同时记录自身 hash。它们用于发现同名版本被静默修改，不承载发布状态机、运行状态或交付结论。

### 1.4 `school.md`

`school.md` 面向 Agent，优先使用清楚的自然语言：

- 适用范围；
- 文档组成；
- 前置页面和固定结构；
- 标题、正文、摘要、目录、参考文献等要求；
- 条件规则；
- 已知冲突与人工确认结论；
- Tool 配置文件的读取说明；
- 需要人工最终查看的事项。

如果精确参数需要被 Tool 消费，再放入 `format-profile.yaml`。不要为了“机器可读”把所有知识提前拆成大量 schema。

### 1.5 来源与版本

- 学校事实必须能追溯到 `sources/` 中的材料或明确的人工确认记录；
- 修改学校要求时创建新版本目录；
- 已用于 Eval 的旧版本保留；
- 通用 Skill 不复制学校具体要求；
- Knowledge 包是否可用由人工评审和对应 Eval case 共同证明，不需要额外发布服务。

### 1.6 加载、临时证据与积累

Skill 告诉 Agent 何时读取哪类 Knowledge，应用壳只把适用的 Knowledge 暴露给 SDK。Knowledge 可以从文件、受控资产存储或其他普通数据源加载，但 Agent 和 Skill 不依赖具体存储实现。

已经建设过的学校直接加载匹配版本的 Knowledge。匹配必须同时考虑学历、专业范围、语言、学年和模板版本，不能只凭学校名、文件名或相似文本猜测。

用户只要求转换当前论文，并临时提供模板或要求文件时：

- `docx_inspect` 提取结构、有效样式、文字、槽位、来源 hash 和不确定对象；
- Agent 在当前 SDK 会话中根据这些证据判断适用规则；
- 这些证据只服务当前任务，不自动写入长期 Knowledge，也不定义新的中间资产或 schema；
- 需要复用已有学校包时，来源 hash 与适用范围都必须匹配。

用户明确要求建设可复用学校资产时，`prepare-school-template` 才把官方材料整理为新的 Knowledge 版本，保留来源、适用范围、冲突和人工确认记录，并通过对应 Eval 验证。

学校要求中的精确值只规范化一次：准备 Knowledge 时，将字体、字号、行距、页边距、编号和节属性等确定参数写入 `format-profile.yaml`。转换时 Tool 直接消费这些有类型的参数，不反复从自然语言中用正则推断。解释性规则、条件和冲突继续保留在 `school.md`。

只有资料规模和查询需求真实超过普通读取能力后，才评估索引或检索；不预先增加 `KnowledgeService`、向量数据库或学校资产发布系统。

## 2. Tools

### 2.1 定位

Tools 把 Word 的确定性复杂性封装在 Agent 之外。

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
Claude Agent SDK 中的 Agent
        ↓ 选择规则与下一步
五个 DocFit Tool
        ↓ 确定性适配
MCP / CLI / library / Word 或 LibreOffice
```

预处理发生在 `docx_inspect` 内部，后处理发生在 `docx_edit` 的后置检查、`docx_render`、`docx_visual_review` 和 `docx_validate` 内部。它们不是独立服务，也不拥有任务状态。底层 Provider 不调用另一个模型或 Agent 来解释论文；所有语义判断、视觉判断和恢复选择仍由 Claude Agent SDK 中的当前 Agent 完成。

| 论文转换需要的能力 | 在 DocFit 中的归属 |
|---|---|
| 模板和论文的结构化预处理 | `docx_inspect` 内部 |
| 当前任务对模板证据的解释 | Claude Agent SDK 当前会话 |
| 可复用学校规则与精确参数 | School Knowledge Package |
| 批量、安全、原子写回 | `docx_edit` 内部 |
| 分页和页面证据 | `docx_render` 内部 |
| 把指定页面图片送入当前 Agent 并建立前后对比 | `docx_visual_review` |
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

DocFit 自己负责：

- 五个 Tool 的输入输出、错误语义和版本兼容；
- Tool 间 opaque `object_ref`、输入 hash、操作前置条件和过期检测；
- 分析与渲染缓存的正确失效；
- 源文件只读、原子发布和非目标内容保护；
- Knowledge 到确定性参数的映射；
- 第三方依赖的版本锁定、适配测试和 Eval。

第三方实现可以负责：

- OOXML 读取、写回和 package 关系维护；
- 常规文本、样式、表格、节、页眉页脚等底层操作；
- OpenXML 结构校验；
- DOCX 到 PDF 或页面图片的转换；
- 文档比较、修订和批注等成熟能力。

首轮候选包括但不限于：

| 候选 | 优先验证的能力 |
|---|---|
| [OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) | 结构化读取、路径查询、批量原子编辑、OpenXML 校验和预览 |
| [Safe Docx](https://github.com/UseJunior/safe-docx) / `docx-core` | 对既有 DOCX 的局部编辑、格式保留、稳定定位和文档比较 |
| [SecurityRonin/docx-mcp](https://github.com/SecurityRonin/docx-mcp) | OOXML 局部操作、修订、批注和结构审计 |
| Aspose.Words | 服务端快速迭代渲染、逐页图片和页面布局信息；需要验证授权、字体与目标样本保真度 |
| LibreOffice | 低成本预览和基础可读性检查；不能作为 Microsoft Word 最终视觉标准 |
| Microsoft Graph / Office API / 受控 Word | 面向最终 Microsoft Word 兼容性的交付渲染证据 |
| 其他 DOCX MCP | 作为能力来源或对照实现，不默认把完整工具面暴露给 Agent |

候选列表是实现调研入口，不是长期架构约束。选型必须用相同 fixture 和 Tool 契约测试比较，至少验证：

- 目标学校样本中的段落、表格、图片、公式、目录、节和页眉页脚；
- 无操作另存和受控修改后，Word 打开时不要求修复；
- 修改只影响目标对象，源文件保持不变；
- 错误能够转成 DocFit 的 `ok`、`needs_input` 或 `error`；
- 在开发机和 CI 环境中可安装、可锁定版本、可重复运行；
- 渲染结果能够报告 provider、版本、字体和已知兼容差异。

PoC 阶段可以把候选 MCP 直接接入 SDK 以验证能力；产品路径默认只向 Agent 暴露 DocFit 的少量高层 Tool，避免 Skill 绑定第三方的几十个细粒度工具。替换底层实现不应要求修改 Skill 或 Knowledge。

### 2.3 最小工具面

优先提供少量、能力清楚的工具，避免 Agent 在大量细粒度工具中选择：

```text
docx_inspect    分析结构、样式、可见对象和风险
docx_edit       在工作副本上执行一组受控编辑操作
docx_render     生成 PDF、逐页图片和渲染摘要
docx_visual_review  将指定页面、裁剪图或对比图作为图片证据返回给当前 Agent
docx_validate   对源文件、最终文件和学校要求做确定性检查
```

新工具只有在职责明显独立、参数和失败语义更清楚时才增加。否则给现有工具增加明确的 `action` 或 `focus` 参数。

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

具体 OOXML 操作、跨 run 文本、节属性、表格单元格和书签处理可以由一个或多个底层引擎完成。DocFit adapter 负责把统一 operation 转换为引擎调用，并把引擎错误、警告和实际修改结果规范化；这些细节不进入 Skill。

为了降低定位漂移风险，Tool 在真正写入前重新核对输入 hash、对象指纹和预期文本；同一容器内会影响位置的操作由 Tool 内部按安全顺序执行，通常从后向前。写入结束后从新文件重新解析，而不是相信 Provider 的修改清单。

M1 必须在 `docx_edit` 中支持一个最小跨文档模板组合操作，例如 `import_template_sections`。它仍属于 `docx_edit`，不新增第六个 Tool。详细字段在 Provider PoC 后再锁定，当前契约只固定必须证明的安全边界：

- 来源模板 hash 与来源对象引用；
- 目标文档 hash 与插入锚点；
- 样式、编号、媒体、relationships、页眉页脚和节属性的依赖闭包；
- 内部 ID 与关系 ID 的冲突重映射；
- all-or-nothing 发布；
- 合并后重新打开、内容保留和非目标内容检查。

Provider 只支持简单段落复制、无法复制完整依赖闭包时，必须把能力缺口报告为不支持或 `verification_gap`，不能把部分合并发布为成功结果。

### 2.6 `docx_render`

统一入口同时承载快速迭代和最终交付两种渲染角色，不为不同引擎增加新的 Agent 可见 Tool。

输入示例：

```yaml
input_docx: /path/work-v2.docx
render_purpose: iteration
pages: all
emit_layout_map: auto
output_dir: /path/render-v2
```

`render_purpose` 只有两个稳定值：

```text
iteration  高频、低延迟的页面观察与修改后复核
release    面向最终 Microsoft Word 兼容性的交付复核
```

Tool 负责：

- DOCX → PDF；
- PDF → 逐页图片；
- 返回 render purpose、provider、版本、页面数、页面尺寸、DPI、字体和转换警告；
- 声明 `fidelity_claim`：`approximate`、`target_application` 或 `unknown`；
- 可选生成对象与页码、页面区域的绑定，供 Agent 定位高风险页面；
- 基于输入 hash、provider、版本、字体和渲染参数复用缓存。

只有 Microsoft 官方转换链路或受控 Microsoft Word 环境可以把 `target_application: microsoft_word` 与 `fidelity_claim: target_application` 同时写入 render ref。Aspose.Words、LibreOffice 和其他第三方引擎即使在样本中表现良好，也只能声明 `approximate`，除非未来存在单独批准的兼容性政策。

首版为快速跑通可以只实现 `iteration`，但 schema 从一开始保留 `release`。收到暂不支持的 `release` 请求时应返回明确的 `needs_input` 或 `verification_gap`，不能静默降级成迭代渲染。

输出示例：

```yaml
status: ok
render_ref:
  document_sha256: ...
  render_sha256: ...
  render_purpose: iteration
  fidelity_claim: approximate
  target_application: microsoft_word
  provider: ...
  provider_version: ...
  font_fingerprint: ...
  font_substitutions: []
  page_count: 42
  dpi: 144
artifacts:
  pdf: /path/render-v2/preview.pdf
  pages: /path/render-v2/pages
  layout_map: /path/render-v2/layout-map.json
warnings: []
```

当 Provider 支持页面布局信息时，`layout-map.json` 使用明确坐标系并绑定同一个 render ref：

```yaml
schema_version: 1
render_sha256: ...
pages:
  - page: 3
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

元素映射只能引用同一文档快照的 opaque `object_ref`。Provider 只能估算时使用 `mapping_quality: approximate`；无法可靠映射时省略该元素并返回 warning。bbox 用来把视觉发现定位回候选对象，不是内容或语义事实，也不能由 Agent 直接转换为 OOXML 路径。

渲染前应解析文档实际请求的字体，记录字体文件/版本指纹和全部替代关系。学校 Knowledge 标记为必需且不允许替代的字体缺失时，Tool 返回环境错误；允许降级预览时可以继续生成 `iteration` 图片，但必须带 `font_substitution` warning，且不能声明目标应用 fidelity。

LibreOffice、Microsoft Word 和第三方渲染器可能产生分页差异。Tool adapter 应报告 provider、版本、运行环境、字体证据和 fidelity claim；Skill 应把高风险分页交给目标应用渲染或人工查看，不把近似渲染说成最终真值。

`docx_render` 的文件路径或“渲染成功”不等于 Agent 已经看过图片。需要视觉判断时，Agent 必须继续调用 `docx_visual_review`。

### 2.7 `docx_visual_review`

这个 Tool 解决的不是“再做一次渲染”，而是把已渲染图片作为受控的视觉输入送回当前 Agent。[Claude Agent SDK 的 in-process MCP Tool](https://code.claude.com/docs/en/agent-sdk/custom-tools) 支持在结果中返回 `image` content block；DocFit 使用这一原生能力，不为视觉审查启动第二个模型或 Agent。

输入示例：

```yaml
render_ref:
  document_sha256: ...
  render_sha256: ...
  render_purpose: iteration
  fidelity_claim: approximate
  provider: ...
  provider_version: ...
  font_fingerprint: ...
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

Tool 返回两类内容：

1. `content` 中的一个或多个图片块，供当前 Agent 直接观察；
2. `structuredContent` 中的文档 hash、渲染 hash、render purpose、fidelity claim、Provider、字体、页码、裁剪坐标、图片 hash、变换方式、元素映射和 evidence ref。

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

- Tool 是只读的，不修改 DOCX、渲染文件或 Agent finding；
- Tool 不输出 `pass`、`fail` 或“版式正确”等语义判断；
- Tool 只读取本次任务授权目录内、由有效 `render_ref` 指向的图片；
- 图片必须绑定当前文档 hash、渲染配置、Provider、版本、字体和页码；
- 存在元素映射时，Tool 返回当前视图覆盖的候选 `object_ref`、bbox 和 mapping quality；不存在时不猜测；
- 文档修改后，旧 `render_ref` 不能用于证明新文档结果；
- `compare` 只在页面尺寸、DPI、Provider、版本、字体环境、render purpose 和 fidelity claim 可比较时生成差异辅助图，否则返回 warning；
- 裁剪、缩放、拼接、压缩和差异着色都必须在元数据中声明，不能把变换后的图片伪装成原始页面；
- 单次返回页数和图片字节数必须有限制，Agent 通过分批调用完成整篇复核；
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
- 目标样式的关键参数符合 Knowledge；
- 渲染成功，字体和 provider 警告已呈现；
- 视觉审查报告绑定当前文档与当前 render，要求页面已经覆盖；
- 没有被忽略的 blocking visual finding；
- 要求 Microsoft Word 最终兼容性时，存在 `render_purpose: release` 且 `fidelity_claim: target_application` 的视觉证据；否则保留 `verification_gap`。

最终交付验证的输入应显式包含视觉审查报告：

```yaml
source_docx: /path/source.docx
final_docx: /path/final.docx
knowledge: /path/knowledge-package
visual_review: /path/visual-review.json
required_visual_coverage: all_final_pages
```

中间编辑轮次可以只要求变化页和相邻页；最终交付必须要求当前 `final_docx` 的全部页面覆盖。`docx_validate` 只校验覆盖、引用、版本绑定和 blocking finding，不重新解释图片内容。

“首条链路已经跑通”和“已经通过 Microsoft Word 最终兼容性门”是两个不同结论。M2 可以使用 `iteration` 近似渲染完成开发闭环；如果没有 `release` 目标应用证据，验证报告和 Agent 最终回复必须明确保留该缺口。

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

`docx_validate` 是普通 Tool，不是 Delivery Preflight、Verifier 或交付状态机。它可以组合第三方 OpenXML 校验、DocFit 的 Knowledge 规则和视觉审查覆盖检查；Agent 读取规范化结果并在最终回复中如实表达。

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

并非所有质量结论都有便宜、完全独立的 oracle。对无法通过重新打开、结构比较、原始 OOXML、第二 provider 或人工页面复核验证的高风险结论，Tool 必须返回 `verification_gap` warning，并说明当前证据来源；不能把第三方的自我声明改写成已验证事实。

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
    - use_alternate_provider
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
| `engine` | 第三方 MCP、CLI 或库失败或返回畸形结果 | 仅在 `retryable: true` 时调整后重试，或切换 provider |
| `environment` | 文件锁、依赖、字体、权限或渲染环境问题 | 修复环境、稍后重试或切换 provider |
| `adapter` | DocFit 映射、协议或适配代码失败 | 不重复相同调用，保留证据并报告为 Tool 问题 |
| `postcondition` | 引擎声称成功，但产物或修改效果未通过独立验证 | 隔离产物，切换 provider 或停止 |

`code` 用于测试和聚合，`message` 面向 Agent，`suggested_actions` 只能给出安全且可执行的恢复选项。

典型结果应这样区分：

| 事实 | Tool 结果 | 主要归因 |
|---|---|---|
| Agent 传入失效引用 | `needs_input` + `origin: request` | Agent 应重新 inspect |
| 引擎崩溃或超时 | `error` + `origin: engine` | 第三方 Tool |
| 引擎返回成功但输出打不开 | `error` + `origin: postcondition` | 第三方 Tool 或 adapter |
| 编辑正确执行，但最终格式仍不符合 Knowledge | `ok` + validation issue | Agent 决策、Knowledge 或覆盖不足，需结合证据归因 |
| 高风险分页只有近似渲染结果 | `ok` + `verification_gap` warning | 能力限制，需要其他 provider 或人工复核 |

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
- 隐藏失败并用未经验证的备用文件交付。

## 5. 如何做得更快

速度优化优先减少重复解析、重复渲染和低信息量的 Agent 往返：

- `docx_inspect` 一次解析尽可能覆盖全部客观对象，后续通过 `focus` 读取同一份缓存；
- Tool 返回高信号摘要和完整证据路径，不把整份 OOXML 塞进 Agent 上下文；
- `docx_edit` 接受一组有前置条件的操作，避免每个段落一次 Tool 调用；
- 每轮编辑后先做便宜的结构和内容检查，只渲染发生变化或风险较高的页面；
- 渲染缓存由输入 hash、Provider 版本、字体和参数共同决定，任何一项变化都自动失效；
- `docx_visual_review` 使用 contact sheet 先做全局扫描，再按风险分批返回整页或裁剪图；单次图片数量和字节数受限；
- Provider 能生成元素映射时，视觉证据同时返回视图覆盖的候选 `object_ref`，减少 Agent 从截图问题到编辑目标的往返；
- 修改过程中优先复核变化页及相邻页，最终交付前仍需覆盖全部当前页面；
- `docx_validate` 复用解析代码，但必须对最终文件重新取证，不能复用旧结论；
- Provider 的选择、重试、换工具或询问用户由 Agent 决定，Tool 内部不启动隐藏的 Agent loop。

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

这不是 Run Bundle 协议；应用或测试不应依赖每个中间文件都存在。

## 7. 何时增加抽象

只有出现以下证据时才考虑扩展：

| 真实问题 | 最小扩展 |
|---|---|
| 学校包经常缺文件或格式错误 | 一个 `knowledge_validate` 脚本 |
| 学校资料数量大到普通读取明显不足 | 增加最小索引或检索；没有测量证据时不引入向量数据库 |
| DOCX 之外的多个工具确实需要共享对象引用 | 评估最小跨格式 ref；没有真实消费者时不泛化 |
| 同一 Tool 操作反复出现定位歧义 | 强化 Tool 内部 locator |
| Eval case 多到串行运行太慢 | 接入现成并发 runner |
| 产品需要多人权限和正式发布 | 在产品需求明确后设计对应服务 |

扩展应从已经发生的问题出发，不从“以后可能平台化”出发。
