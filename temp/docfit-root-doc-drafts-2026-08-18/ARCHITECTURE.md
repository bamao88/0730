# DocFit 架构

状态: temp 候选稿，未替换根目录 `ARCHITECTURE.md`
更新日期: 2026-08-18

本文负责说明系统结构、模块边界、数据流、关键接口、扩展点和不能随意改变的架构边界。
本文不记录函数细节、任务计划、历史 proof 或一次 bug 的修复过程。

## 底层心智模型

DocFit 围绕 Claude Agent SDK 构建。Claude Agent SDK 负责 Agent loop、session、
Tool call、permission、Skill、Subagent、structured output、context management 和 lifecycle。

DocFit 负责论文领域合同、确定性 DOCX 能力、hash/schema 绑定、视觉证据、Eval/Gold、
本地可观测性和薄应用适配层。

架构原则是 SDK-native first：Agent 语义判断留在 SDK Agent loop 内，确定性代码保护客观不变量。
不要因为一次模型失败就把语义判断沉淀成 DocFit 自有状态机、固定工作流或第二套 Agent runtime。

## 产品模块

| 模块 | 输入 | 输出 | 不负责 |
| --- | --- | --- | --- |
| 模板提取 | 学校模板、可选学校要求、Field Registry | `final-template.docx`、`fill-contract.yaml` | 学生内容提取、最终论文生成 |
| 用户内容提取 | 学生源 DOCX、Field Registry | Student Content Model | 学校模板识别、目标位置、目标样式 |
| final word 生成 | 模板产物、Student Content Model、任务补充信息 | 最终 Word、evidence/report | 重新识别学校要求或重新提取学生内容 |

三个模块是并行同级模块。它们共享 Claude Agent SDK 接入、中立 Word 事实层、Registry/contract
概念和基础证据能力，但不共享业务 Agent 配置、prompt、session、私有上下文或模块内部状态。

## 数据流

```text
学校模板 + 可选学校要求 + Field Registry
        -> 模板提取
        -> final-template.docx + fill-contract.yaml

学生源 DOCX + Field Registry
        -> 用户内容提取
        -> Student Content Model

final-template.docx + fill-contract.yaml + Student Content Model
        -> final word 生成
        -> 最终 Word + evidence/report
```

Eval/Gold 只在运行完成后读取 Actual 产物。Gold 不能进入正在被评测的 Agent prompt、
Tool 输入或运行时上下文。

## 共享层

| 层 | 职责 |
| --- | --- |
| Claude Agent SDK 接入 | 管理 SDK options、session、Tool、Skill、Subagent 和 lifecycle |
| Word 事实层 | 对 DOCX 做只读 inspection、结构定位、渲染和 package validation |
| Field Registry | 提供跨模块共享的 field identity 和 semantic lexicon |
| Contract / schema | 约束跨模块交接产物、hash、locator、digest 和失败语义 |
| Eval / Gold | 对完成后的 Actual 产物做离线评分和人工审查 |
| Observability | 记录脱敏后的 SDK/App/Tool 事件，帮助定位运行失败 |

共享层必须保持中立。它们可以提供事实、验证和证据，不能替某个业务模块做语义决策。

## 关键接口

CLI 入口：

- `uv run docfit doctor`
- `uv run docfit prepare-template`
- `uv run docfit extract-student-content`
- `uv run docfit eval-student-content`
- `uv run docfit tools ...`
- `uv run docfit observe`
- `uv run docfit convert`，legacy 端到端路由

文档接口：

- 三模块路由：`docs/modules/README.md`
- 模板提取合同：`docs/contracts/template-extraction.md`
- 测试与 Eval 路由：`tests/README.md`
- 文档生命周期：`docs/README.md`

主要产物接口：

- 模板提取发布：`output/final-template.docx`、`output/fill-contract.yaml`
- 用户内容提取发布：`student-content.json`、`run-report.json`
- final word 生成发布：最终 Word 和 evidence/report

## 可扩展点

可以扩展：

- 新增或修订 Skill / Reference，改善 Agent 的领域判断。
- 在稳定 Tool 边界后增加 evidence、check、apply、render、validate 的能力变体。
- 增加 Field Registry revision，并明确兼容性和 Gold 影响。
- 增加 Contract 版本，但必须保留迁移语义和下游影响说明。
- 增加 Eval case、Gold revision、人工 review evidence 和观测报告。
- 扩展样式属性、编号、caption、表格、section 和 document-level 物化能力。

不能随意改变：

- 三模块读取边界和稳定产物交接方式。
- DOCX、学校要求、学生论文、批注、字段、隐藏文本和 alt text 都是不可信输入这一规则。
- Gold 不能反向注入 runtime prompt 或 Tool 输入这一规则。
- 源文件只读复制、hash 绑定、locator 绑定、Registry hash 和 style digest 不变量。
- 模板提取成功发布只对下游暴露 `final-template.docx` 和 `fill-contract.yaml`。
- 用户最终交付是一份最终 Word 文档；除非产品明确改变，不把内部模板和证据作为用户交付物。

## 失败定位

复杂失败先按层归因：

- Agent / Skill：语义判断、领域概念、任务理解。
- Harness：上下文包、coverage feedback、loop 退出、权限前置检查。
- Tool：确定性 DOCX 操作、渲染、validation、错误可行动性。
- Schema / Contract：跨模块产物结构、版本、hash、locator、digest。
- App：CLI、任务目录、发布、源副本、fail-closed 后置条件。
- Test / Eval：生成测试、离线评分、Gold review、人工验收。
- Docs：入口、状态、边界或历史证据是否误导。

如果一次修改需要同时触碰多个层，先说明为什么问题确实跨层，而不是由某一层反馈不足造成。
