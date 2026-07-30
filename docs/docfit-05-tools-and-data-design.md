# DocFit Knowledge 与 Tools 设计（05）v1.0

> 状态：现在实施
> 日期：2026-07-30
> 原则：Knowledge 保持可读，Tools 保持确定性，复杂性不进入 Agent runtime。

## 1. Knowledge

### 1.1 定位

Knowledge 是 Claude Agent 按需读取的论文领域资料。它分为两类：

- 通用 Knowledge：论文结构、Word 常见陷阱、处理示例；
- 学校 Knowledge：某学校某版本的官方来源、要求、模板和示例。

Knowledge 是文件资产，不是数据库或服务。当前阶段使用版本控制、目录版本和人工评审就足够。

### 1.2 目录

建议结构：

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
applies_to: 中文本科毕业论文
sources:
  - path: sources/official-template.docx
    description: 学校官方模板
review:
  reviewed_by: ...
  reviewed_at: ...
notes: ...
```

manifest 只说明这个包是什么、来自哪里、适用于什么。它不承载发布状态机、运行状态或交付结论。

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

### 1.6 加载

Skill 告诉 Agent 在什么情况下读取学校 Knowledge。应用壳只把 Knowledge 根目录或相关文件暴露给 SDK。

如果 SDK 的文件读取和 Skill progressive disclosure 已够用，不增加 `KnowledgeService`、检索层或向量数据库。只有学校和资料规模真实超过普通文件读取能力后，再评估检索。

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

### 2.2 最小工具面

优先提供少量、能力清楚的工具，避免 Agent 在大量细粒度工具中选择：

```text
docx_inspect    分析结构、样式、可见对象和风险
docx_edit       在工作副本上执行一组受控编辑操作
docx_render     生成 PDF、逐页图片和渲染摘要
docx_validate   对源文件、最终文件和学校要求做确定性检查
```

新工具只有在职责明显独立、参数和失败语义更清楚时才增加。否则给现有工具增加明确的 `action` 或 `focus` 参数。

### 2.3 `docx_inspect`

输入示例：

```yaml
input_docx: /path/student.docx
focus: [structure, styles, visible_objects]
```

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

### 2.4 `docx_edit`

输入示例：

```yaml
input_docx: /path/work-v1.docx
output_docx: /path/work-v2.docx
operations:
  - action: apply_style
    target_ref: obj-...
    style: heading_1
  - action: replace_text
    target_ref: obj-...
    expected_text: "在此填写"
    replacement: "..."
```

要求：

- 输出路径不得等于输入路径；
- 执行前验证全部 operation；
- 目标定位或前置文本不一致时安全失败；
- 对一次调用尽可能原子执行；
- 返回实际执行项、跳过项和警告；
- 修改后重新读取文件并做基础结构检查。

具体 OOXML 操作、跨 run 文本、节属性、表格单元格和书签处理都是 Tool 内部实现，不进入 Skill。

### 2.5 `docx_render`

统一入口负责：

- DOCX → PDF；
- PDF → 逐页图片；
- 返回 provider、页面数、字体和转换警告；
- 基于输入 hash 与 provider 配置复用缓存。

LibreOffice 与 Microsoft Word 兼容渲染可能产生分页差异。Tool 应报告证据来源，Skill 应把高风险分页交给人工查看，不把近似渲染说成最终真值。

### 2.6 `docx_validate`

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
status: needs_attention
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

`docx_validate` 是普通 Tool，不是 Delivery Preflight、Verifier 或交付状态机。Agent 读取结果并在最终回复中如实表达。

## 3. 内容安全的实现边界

“内容不得静默丢失”是产品不变量，但不要求先建设全局内容身份平台。

当前实现采用以下最小策略：

1. `docx_inspect` 对一个文档快照生成稳定的 opaque object refs；
2. `docx_edit` 只接受这些 refs 和明确前置条件；
3. 修改后重新 inspect；
4. `docx_validate` 比较支持对象的文本、类型、数量和必要顺序；
5. 发现不支持对象时返回给 Agent，不静默忽略。

如果工具内部需要 `content_id`、`source_ref` 或血缘关系，可以在 `tools/docx/` 内定义并测试。只有出现第二个独立消费者并需要跨工具交换时，才提升为共享契约。

当前不建设：

- 全局 Content Ledger；
- 跨运行 ArtifactRef 系统；
- canonical object identity 标准；
- 事件溯源；
- 全仓库 schema registry。

## 4. 工具错误语义

所有 Tool 使用简单、可行动的结果：

```text
ok               调用完成，可继续
needs_input      目标或事实不足，需要 Agent 补充、重新 inspect 或询问用户
error            工具未正常完成，不应消费其输出
```

具体问题放在 `issues` / `warnings` 中，不为每个领域动作创建新的全局状态枚举。

Agent 可以根据 Tool 描述和 Skill 指引决定：

- 重试；
- 重新分析；
- 使用更小范围的操作；
- 改用其他工具；
- 询问用户；
- 停止并报告。

## 5. 工作文件

一次任务的目录保持可理解：

```text
output/<task-id>/
├── source-info.json
├── work/
│   ├── working.docx
│   └── analysis.json
├── final.docx
├── preview.pdf
├── pages/
└── validation.json
```

只有最终交付和调试实际需要的文件长期保留。临时 OOXML、渲染缓存和中间副本可由工具管理。

这不是 Run Bundle 协议；应用或测试不应依赖每个中间文件都存在。

## 6. 代码结构

```text
src/docfit/
├── app/
│   ├── cli.py
│   └── api.py
├── tools/
│   ├── inspect.py
│   ├── edit.py
│   ├── render.py
│   ├── validate.py
│   └── docx/
│       ├── package.py
│       ├── locator.py
│       └── mutator.py
└── sdk/
    └── agent.py

skills/
knowledge/
evals/
tests/
```

`src/docfit/sdk/agent.py` 只做 Claude Agent SDK 配置与启动，不演进为 orchestration package。

## 7. 何时增加抽象

只有出现以下证据时才考虑扩展：

| 真实问题 | 最小扩展 |
|---|---|
| 学校包经常缺文件或格式错误 | 一个 `knowledge_validate` 脚本 |
| 文件数量大到普通读取明显不足 | Knowledge 索引或检索 |
| 多个 Tool 需要共享对象引用 | 提取最小共享 ref schema |
| 同一 Tool 操作反复出现定位歧义 | 强化 Tool 内部 locator |
| Eval case 多到串行运行太慢 | 接入现成并发 runner |
| 产品需要多人权限和正式发布 | 在产品需求明确后设计对应服务 |

扩展应从已经发生的问题出发，不从“以后可能平台化”出发。
