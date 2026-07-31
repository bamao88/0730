# DocFit Knowledge 与 Tools 设计（05）

> 状态：设计说明
> 日期：2026-07-30
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

### 1.6 `SchoolKnowledgeDraft`

模板解析的共享输出统一为 `SchoolKnowledgeDraft`。它连接模板证据与两个业务 Skill，但本身不是正式 School Knowledge Package。

最小结构：

```yaml
schema_version: 1
school: 某大学
source_digest: sha256:...
sources:
  - path: template.docx
    sha256: ...
    kind: template
applicability:
  degree_level: ...
  program_scope: ...
  language: ...
  academic_year: ...
rules:
  - field: title.font_size
    value: 小二
    source_ref: template.docx#paragraph-12
    evidence_kind: template_observation
    confidence: high
template_asset: template.docx
conflicts: []
uncertainties: []
```

字段语义：

- `source_digest` 标识本次输入来源集合，用于发现完全相同的模板和要求文件；
- `source_ref` 必须指向可复核的原始证据；
- `evidence_kind` 区分官方文字明示、模板客观表现和 Agent 推断；
- `confidence` 是受限枚举，不是模型自报概率；只有来源明确且证据一致时才能标为 `high`；
- `conflicts` 保存来源之间的不一致；
- `uncertainties` 保存无法从现有证据确认的规则和适用范围。

`source_digest` 按来源文件内容计算，不依赖本机绝对路径或上传时的文件名：先计算每个来源文件的 SHA-256，再按 `kind + sha256` 排序并对规范化列表计算总 SHA-256。具体序列化形式由 schema 固定并用 fixture 测试。

共享模板提取能力只做三件事：

1. `docx_inspect` 等 Tool 确定性提取模板结构、样式、文字、槽位和来源 hash；
2. Agent 按一份共享模板提取协议解释证据并形成 `SchoolKnowledgeDraft`；
3. schema validator、source-ref checker 和 digest calculator 检查草稿的结构与可追溯性。

共享协议、Draft schema 和确定性校验只维护一份。它们不是新的用户可见 Skill；确定性内部模块只有在 Agent 需要直接调用时才暴露成 Tool。

`SchoolKnowledgeDraft` 有两种消费方式：

- `prepare-school-template` 补充完整适用范围、版本、来源检查和人工确认，再形成长期 School Knowledge Package；
- `convert-thesis` 把它作为本次任务的临时规则证据，任务结束后不自动登记为长期学校资产。

计算用户模板 digest 后，只有在来源集合与已有 Knowledge 的 source hashes 完全匹配，且适用范围也匹配时，才能直接复用已有 School Knowledge Package。digest 不匹配或适用范围不明时，生成新的任务级 Draft，不用文件名或相似文本猜测复用。

`source_digest` 与正式包的 `content_digest` 不同：前者标识输入来源集合，后者标识最终会影响 Agent 或 Tool 行为的 Knowledge 内容。

### 1.7 加载与积累

Skill 告诉 Agent 何时读取哪类 Knowledge，应用壳只把适用的 Knowledge 暴露给 SDK。Knowledge 可以从文件、受控资产存储或其他普通数据源加载，但 Agent 和 Skill 不依赖具体存储实现。

新学校资料通过真实任务逐步积累：用户明确要求建设长期学校资产时，`prepare-school-template` 将官方材料整理为候选 Knowledge，经过来源检查、必要 Eval 和人工确认后供后续任务复用。这是领域资产维护方式，不是在线工作流。

用户只要求转换当前论文时，`convert-thesis` 可以从本次提供的模板和要求文件中生成任务级 `SchoolKnowledgeDraft`。Draft 保留来源与 hash，但不自动写入长期学校 Knowledge。

只有资料规模和查询需求真实超过普通读取能力后，才评估索引或检索；不预先增加 `KnowledgeService` 或向量数据库。

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

### 2.2 实现与复用策略

下面定义的四个 Tool 是 DocFit 面向 Agent 的稳定契约，不表示底层 DOCX 能力必须由 DocFit 从零实现。

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

- 四个 Tool 的输入输出、错误语义和版本兼容；
- `DocumentObjectRef`、输入 hash、操作前置条件和过期检测；
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
| LibreOffice 或 Microsoft Word | PDF 与分页渲染证据 |
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

底层引擎返回的段落索引、XPath、bookmark 或其他 locator 必须在适配层转换为 `DocumentObjectRef`。不能把第三方定位格式直接写入 Skill 或 Knowledge。

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
- 修改后重新读取文件并做基础结构检查。

Tool 应先验证全部 operation，再写入临时文件；临时文件能够重新打开并通过基础结构检查后，才发布到 `output_docx`。任一操作失败时，不留下可被误认成成功的输出文件。

具体 OOXML 操作、跨 run 文本、节属性、表格单元格和书签处理可以由一个或多个底层引擎完成。DocFit adapter 负责把统一 operation 转换为引擎调用，并把引擎错误、警告和实际修改结果规范化；这些细节不进入 Skill。

### 2.6 `docx_render`

统一入口负责：

- DOCX → PDF；
- PDF → 逐页图片；
- 返回 provider、页面数、字体和转换警告；
- 基于输入 hash 与 provider 配置复用缓存。

LibreOffice、Microsoft Word 和第三方渲染器可能产生分页差异。Tool adapter 应报告 provider、版本、运行环境和字体证据；Skill 应把高风险分页交给人工查看，不把近似渲染说成最终真值。

### 2.7 `docx_validate`

验证工具只做能够稳定、低误判地判断的事实：

- 源文件 hash 未变化；
- 最终 DOCX 可重新打开；
- 关键 package 关系可解析；
- 支持范围内的关键文本和对象没有明显丢失或重复；
- 必填内容存在；
- 占位符和模板说明文字没有残留；
- 目标样式的关键参数符合 Knowledge；
- 渲染成功，字体和 provider 警告已呈现。

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

`docx_validate` 是普通 Tool，不是 Delivery Preflight、Verifier 或交付状态机。它可以组合第三方 OpenXML 校验与 DocFit 的 Knowledge 规则；Agent 读取规范化结果并在最终回复中如实表达。

## 3. 内容安全的实现边界

“内容不得静默丢失”是产品不变量，但不要求先建设全局内容身份平台。

### 3.1 最小 `DocumentObjectRef`

`docx_inspect` 与 `docx_edit` 之间共享一个版本化、对 Agent opaque 的值对象：

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

该契约只服务 DOCX 工具间的安全交换，不定义跨文件类型、跨任务或跨运行的全局对象身份。

### 3.2 最小策略

当前实现采用以下最小策略：

1. `docx_inspect` 对一个文档快照生成稳定的 opaque object refs；
2. `docx_edit` 只接受这些 refs 和明确前置条件；
3. 修改后重新 inspect；
4. `docx_validate` 比较支持对象的文本、类型、数量和必要顺序；
5. 发现不支持对象时返回给 Agent，不静默忽略。

更细的 OOXML locator、第三方对象路径、`content_id` 或血缘关系继续留在 Tool adapter 内部。除非出现 DOCX 之外的第二类真实消费者，不把 `DocumentObjectRef` 泛化为全系统 ArtifactRef。

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

DocFit adapter 不直接转发第三方引擎的 `success`、退出码或自然语言结论。按不同 Tool 的能力，一次调用适用以下四层独立检查：

1. **请求检查**：输入符合 DocFit schema，引用和前置条件仍然有效；
2. **执行检查**：MCP、进程或库调用正常返回，没有超时、崩溃或结构异常；
3. **产物检查**：预期文件确实存在、能够重新打开，源文件没有被覆盖；
4. **效果检查**：目标修改已经发生，支持范围内的非目标内容没有意外变化。

第三方报告成功但任一后置检查失败时，DocFit 必须返回 `error`，把失败来源标记为 `postcondition`，并且不发布或继续消费该产物。第三方没有主动报告错误，不代表 Tool 成功。

并非所有质量结论都有便宜、完全独立的 oracle。对无法通过重新打开、结构比较、原始 OOXML、第二 provider 或人工页面复核验证的高风险结论，Tool 必须返回 `verification_gap` warning，并说明当前证据来源；不能把第三方的自我声明改写成已验证事实。

对可能产生副作用的 Tool，结果应包含最小诊断信息：

```yaml
status: error
operation_id: op-...
committed: false
failure:
  origin: engine
  stage: execute
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
  log_ref: /path/sanitized-log.json
```

`committed` 只表示经过 DocFit 后置检查的副作用是否已经发布。临时文件存在不等于 `committed: true`。日志只保留诊断所需的脱敏摘要，不写入整篇论文内容。

`operation_id` 只用于关联单次 Tool 调用及其脱敏诊断证据，不是任务状态、工作流实例或 replay 协议。

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

`stage` 进一步说明失败发生在 `validate_input`、`locate`、`execute`、`save`、`reopen`、`verify_effects` 或 `render`。`code` 用于测试和聚合，`message` 面向 Agent，`suggested_actions` 只能给出安全且可执行的恢复选项。

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

## 5. 工作文件

Tool 可以使用工作副本和输出目录，但不规定全局任务目录协议。例如：

```text
task-work/
├── source.docx
├── work/
│   └── working.docx
└── output/
    ├── final.docx
    └── validation.json
```

只有最终交付和调试实际需要的文件长期保留。临时 OOXML、渲染缓存和中间副本可由工具管理。

第三方引擎只能访问本次调用明确授权的输入、临时目录和输出路径。若其自带网络、脚本执行或任意文件访问能力，适配层应关闭这些非必要能力；运行时不得自动下载未锁定版本。

这不是 Run Bundle 协议；应用或测试不应依赖每个中间文件都存在。

## 6. 何时增加抽象

只有出现以下证据时才考虑扩展：

| 真实问题 | 最小扩展 |
|---|---|
| 学校包经常缺文件或格式错误 | 一个 `knowledge_validate` 脚本 |
| 学校资料数量大到普通读取明显不足 | 增加最小索引或检索；没有测量证据时不引入向量数据库 |
| DOCX 之外的工具也需要共享对象引用 | 在已有 `DocumentObjectRef` 之外评估跨格式 ref；没有真实消费者时不泛化 |
| 同一 Tool 操作反复出现定位歧义 | 强化 Tool 内部 locator |
| Eval case 多到串行运行太慢 | 接入现成并发 runner |
| 产品需要多人权限和正式发布 | 在产品需求明确后设计对应服务 |

扩展应从已经发生的问题出发，不从“以后可能平台化”出发。
