# DocFit 项目总结构（06）

> 状态：开发结构参考
> 日期：2026-07-31
> 原则：目录表达资产归属，不定义第二套 runtime，也不锁定编程语言或应用入口。

## 1. 这份文档解决什么

本文件从仓库根目录说明 DocFit 的整体结构，回答：

- 每类资产放在哪里；
- 两个 Skill 如何共享模板提取能力；
- Tool 契约、第三方适配器和内部确定性代码如何分开；
- Knowledge、Eval、普通测试和运行时临时文件如何区分；
- 哪些目录是稳定归属，哪些实现位置可以随语言和框架调整。

当前仓库的实质项目资产只有 `docs/`；尚没有代码、Skill、Knowledge、Eval 或测试资产。下面的目标结构用于指导开发，不表示这些目录已经存在。

## 2. 目标逻辑目录

```text
<repo-root>/
├── docs/                              # 架构、设计说明和人类示例
│   ├── docfit-00-index.md
│   ├── docfit-01-architecture-core.md
│   ├── docfit-02-testing-and-iteration.md
│   ├── docfit-03-gold-system-design.md
│   ├── docfit-04-skills-design.md
│   ├── docfit-05-tools-and-data-design.md
│   ├── docfit-06-project-structure.md
│   └── human/
│
├── app/                               # 薄应用壳与 Claude Agent SDK 接入
│   ├── entrypoints/                   # CLI、API 或 GUI 入口；按实际产品选择
│   └── sdk/                           # SDK 配置、Skill/Knowledge/Tool 挂载
│
├── skills/                            # 仅包含用户目标型 Skill
│   ├── prepare-school-template/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   └── scripts/                   # 仅放本 Skill 特有的轻量辅助
│   └── convert-thesis/
│       ├── SKILL.md
│       ├── references/
│       └── scripts/
│
├── shared/                            # 两个 Skill 共用的 Agent 可读协议与 schema
│   ├── template-extraction-protocol.md
│   └── schemas/
│       └── school-knowledge-draft.schema.json
│
├── knowledge/                         # 可审阅、可版本化的领域资产
│   ├── common/
│   │   ├── thesis-structure.md
│   │   └── word-layout-pitfalls.md
│   └── schools/
│       └── <school-id>/
│           └── <version>/
│               ├── manifest.yaml
│               ├── school.md
│               ├── format-profile.yaml            # 需要精确参数时，可选
│               ├── template.docx                  # 需要套用模板时，可选
│               ├── sources/
│               └── examples/                      # 少量已确认示例，可选
│
├── tools/                             # DocFit Tool 契约与确定性实现
│   ├── contracts/                     # docx_inspect/edit/render/validate schema
│   ├── adapters/                      # OfficeCLI、Safe Docx、LibreOffice 等适配
│   └── internal/                      # 未暴露给 Agent 的确定性模块
│       ├── template-evidence-extractor/
│       ├── knowledge-draft-validator/
│       └── knowledge-digest-calculator/
│
├── evals/                             # 调用 Agent 的离线评测
│   ├── skills/                        # L3：Skill Eval
│   ├── e2e/                           # L4：端到端 Eval
│   ├── fixtures/                      # L3/L4 测试输入
│   └── gold/                          # L3/L4 期望结果与人工确认资产
│
└── tests/                             # 不调用 Agent 的确定性测试
    ├── unit/                          # L1：纯逻辑和内部模块
    │   ├── shared/
    │   ├── knowledge/
    │   └── tool-models/
    └── integration/                   # L2：Tool 契约与真实 Adapter
        ├── tool-contracts/
        └── adapters/
```

`app/` 和 `tools/` 是逻辑归属。选定实现语言后，可以放入该语言惯用的 source root，例如 `src/<package>/app` 和 `src/<package>/tools`；不要创建名为 `<repo-root>`、`<school-id>` 或 `<version>` 的字面目录。

目录按真实实现逐步创建，不为了让树看起来完整而提交空目录。

## 3. 各目录的权威职责

| 目录 | 负责 | 不负责 |
|---|---|---|
| `app/` | 收集输入、配置 SDK、挂载资产、展示回复和产物 | 论文语义、模板规则、工作流编排 |
| `skills/` | 两个业务目标的触发、判断边界、完成条件和最终回复要求 | 学校具体规则、共享解析代码、OOXML 实现 |
| `shared/` | 两个 Skill 共用的模板提取协议和 `SchoolKnowledgeDraft` schema | 正式学校事实、运行时服务、通用工具箱 |
| `knowledge/` | 学校正式 Knowledge、来源、版本、适用范围和通用领域资料 | 当前任务日志、未经审核的用户模板 Draft |
| `tools/contracts/` | Agent 可见的少量稳定 Tool schema 与错误语义 | 第三方项目的完整工具面 |
| `tools/adapters/` | 把第三方 MCP、CLI、库和渲染器转换成 DocFit 契约 | Agent 的领域判断 |
| `tools/internal/` | digest、schema 校验、证据提取等确定性内部能力 | 用户可发现的 Skill |
| `evals/` | L3/L4：Skill 行为、共享模板提取语义和端到端结果评测 | L1/L2 确定性测试、在线用户请求控制 |
| `tests/` | L1/L2：纯逻辑、Schema、Tool Contract 和真实 Adapter 测试 | 模型行为评测 |
| `docs/` | 稳定架构、实现参考、示例和决策说明 | 运行时配置或业务数据 |

`shared/` 是物理复用目录，不是第六类架构资产。其中的 Agent 指引属于 Skill 实现资产，schema 属于 Knowledge/Tool 之间的共享契约。

## 4. 共享模板提取能力放在哪里

模板理解不在两个 Skill 中各写一套：

```text
skills/prepare-school-template/SKILL.md ─┐
                                         ├─ shared/template-extraction-protocol.md
skills/convert-thesis/SKILL.md ──────────┤
                                         ├─ shared/schemas/...
                                         └─ tools/internal/... + docx_inspect
```

职责分配如下：

- `shared/template-extraction-protocol.md`：Agent 如何把客观证据解释成学校规则；
- `school-knowledge-draft.schema.json`：统一 `SchoolKnowledgeDraft` 的字段；
- `docx_inspect`：读取模板结构、样式、槽位和可见文字；
- `tools/internal/`：计算 digest、检查 source refs、验证 Draft schema；
- `prepare-school-template`：把 Draft 补充为经过适用范围、版本和人工确认的正式 Knowledge；
- `convert-thesis`：把 Draft 限定在本次任务，用于生成最终论文。

共享能力是一个领域实现边界，不是第三个 Skill、第五个 Tool 或新的运行时服务。

## 5. 依赖方向

允许的主要依赖方向：

```text
App
 └─ Claude Agent SDK
     ├─ Skills
     │   ├─ Shared protocol/schema
     │   ├─ Knowledge
     │   └─ Tool contracts
     └─ Tools
         └─ Adapters
             └─ 第三方引擎

Eval
 └─ 离线使用同一组 Skills + Knowledge + Tools
```

约束：

- `Tool` 不读取 `SKILL.md`，也不自主解释学校规则；
- `Skill` 不依赖某个第三方引擎的私有 Tool 名称；
- `Knowledge` 不依赖应用入口或 SDK 会话；
- `shared/` 不反向演进成 orchestration package；
- `evals/` 可以依赖产品资产，产品运行时不能依赖 Eval；
- `app/` 不吸收本应属于 Skill、Knowledge 或 Tool 的领域逻辑。

## 6. 正式资产与任务级文件

以下内容进入版本控制：

- 架构与设计文档；
- 两个 Skill；
- 共享模板提取协议和 schema；
- 确认后的 Knowledge；
- Tool 契约、adapter 和内部确定性代码；
- 合成或获授权的 Eval、fixture 和测试。

用户任务生成的文件放在仓库外的工作目录，或者放在已被版本控制忽略的位置：

```text
<task-work>/
├── source/                             # 输入副本或只读引用
├── work/
│   ├── SchoolKnowledgeDraft
│   ├── thesis-analysis
│   └── working.docx
├── output/
│   ├── final.docx
│   ├── preview.pdf
│   └── validation.json
└── logs/                               # 仅保留脱敏诊断信息
```

任务级 `SchoolKnowledgeDraft`、学生论文分析、中间 DOCX、渲染缓存和真实学生内容不进入长期 `knowledge/`，也不进入公开仓库。

## 7. 第一条开发链路需要的最小目录

开始第一条垂直切片时，只创建有真实文件的目录：

```text
app/
skills/prepare-school-template/
skills/convert-thesis/
shared/schemas/
knowledge/schools/<first-school>/<version>/
tools/contracts/
tools/adapters/
tools/internal/
evals/skills/
evals/e2e/
evals/fixtures/
tests/unit/
tests/integration/tool-contracts/
tests/integration/adapters/
```

依赖清单、source root、构建目录和入口文件遵循最终选定的语言与 Claude Agent SDK 集成方式，再补入本结构；它们不改变这里的资产边界。

## 8. 不应出现的顶层目录

没有真实需求和 ADR 前，不增加：

```text
workflow/
stages/
orchestrator/
checkpoint/
replay/
delivery-state/
knowledge-service/
artifact-platform/
```

第三方适配器不是架构中的新 Adapter Layer；它只是 `tools/` 内部对开源实现的普通封装。

## 9. 相关文档

- [架构总览](./docfit-01-architecture-core.md)
- [测试与迭代](./docfit-02-testing-and-iteration.md)
- [Eval 数据与 Gold](./docfit-03-gold-system-design.md)
- [Skill 设计](./docfit-04-skills-design.md)
- [Knowledge 与 Tools 设计](./docfit-05-tools-and-data-design.md)
