# DocFit Knowledge Package v1 通用领域知识包实施计划

> 状态：DONE — 产品通用包重构已实现并验收
> 日期：2026-08-01
> 执行授权：用户明确要求同步顶层设计与当前实现。

## Plan Ledger

- Plan status: DONE
- Session scope: knowledge-package-v1-universal-refactor
- Parent plan: none
- Child plans: none
- Last updated: 2026-08-01
- Current slice: 已删除长期 School Knowledge 边界，并完成随产品发布的通用
  Knowledge Package、只读加载器、内容、合成测试和长期文档同步。
- Completed proof: Knowledge 定向测试 69 个、全仓测试 90 个、ruff、mypy、
  `uv sync --frozen`、lock check、build、wheel/sdist 归档检查和基础 doctor 全部通过。
- Next action: 不自动继续；`docs/plans/docfit-development-plan.md` 已完成 P1 的选择性
  Knowledge 与只读 Subagent 组合，M1/M2 仍分别等待后续批准。
- Blocked on: none
- Do not touch from this session: 五个 Tool 的公开名称和 schema、OfficeCLI/Adobe PDF Services
  adapter、真实 DOCX 行为、M1 实现、Agent runtime 权限。
- Unknown-unknown scout: skipped；用户已经锁定产品定义和禁止项，未知学校差异通过
  “当前任务证据”边界隔离，不需要扩展长期数据模型。

## 1. 权威定义

Knowledge Package 是 DocFit 随产品发布、面向所有学校和任务共享的通用论文格式
领域知识包。它为 Agent 提供统一概念、识别方法、解释原则和通用处理模式，帮助
Agent 从当前任务提供的学校材料中理解并推导具体规则。它不保存任何学校的专属
要求、模板或格式参数。

Knowledge 必须通用；学校事实必须来自当前任务证据；任何学校专属结论都不能因为
被 Agent 提取过，就自动升级为长期 Knowledge。

## 2. 架构结论

- DocFit 只有一个产品级 Knowledge Package，不再存在 School Knowledge Package。
- Knowledge 随代码/产品版本发布，所有任务读取同一份只读通用内容。
- 当前任务的学校模板、要求文件、示例、人工确认和推导结果只存在于授权任务目录、
  SDK 会话及任务产物中。
- Agent 可以从任务证据推导当前转换规则，但这些规则的生命周期不超过当前任务，
  除非用户把原始材料再次作为另一个任务的输入。
- Eval 可以保存合成、脱敏或授权的学校场景 fixture 与期望事实，但 Eval 数据不是
  Knowledge，也不会被运行时自动加载为学校事实。
- Tool 接收当前任务已经确认的操作参数或规则证据，不从长期 Knowledge 读取学校
  字号、页边距、模板槽位或固定文案。
- 不建设学校包目录、学校版本选择、学校资产发布、学校检索或自动晋升机制。

## 3. 数据归属

| 内容 | 归属 | 生命周期 |
|---|---|---|
| 论文结构概念、语义角色和常见对象组成 | Knowledge | 随产品版本发布 |
| 从模板和要求文件识别规则的方法 | Knowledge | 随产品版本发布 |
| 证据冲突、歧义和不确定性的解释原则 | Knowledge | 随产品版本发布 |
| 检查、修改、渲染和复核的通用模式 | Knowledge | 随产品版本发布 |
| 某校名称、适用学年、学历或专业范围 | 当前任务证据 | 单次任务 |
| 某校模板、官方要求、示例和人工确认 | 当前任务证据 | 单次任务 |
| 某校字号、行距、页边距、固定文字和槽位 | 当前任务推导规则 | 单次任务 |
| 真实/脱敏学校回归样本与期望事实 | Eval | 离线测试，不进入运行时 Knowledge |

## 4. v1 包结构

产品内置包位于 Python package 内，确保 wheel/sdist 发布时与代码一起交付：

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

允许增加 `examples/`，但只能包含跨学校的合成示例。以下内容禁止出现在包中：

- 学校目录、学校 ID、学年、学历或专业适用范围；
- 学校模板、DOCX、PDF、图片或原始学校要求文件；
- `school.md`、`structure-profile.yaml`、`format-profile.yaml`；
- 学校特定字号、页边距、固定文案、槽位和确认结论；
- 任务文件、学生论文、缓存、运行日志或 Tool/Provider 私有定位信息。

仓库根 `knowledge/` 只作为人类入口，说明内置包位置和作者边界；不再包含
`common/` / `schools/` 两套长期资产。

## 5. `manifest.yaml` v1

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

约束：

- `schema_version` 只接受整数 `1`；未知字段和重复 YAML mapping key 失败。
- `package_id`、`version` 使用小写 slug；`version` 必须与包目录名一致。
- `scope` 只接受 `universal_thesis_formatting`。
- `documents` 必须覆盖 concepts、recognition method、interpretation principle 和
  processing pattern 四类通用内容，ID 和路径各自唯一；example 可选。
- `kind` 只接受 `concepts`、`recognition_method`、
  `interpretation_principle`、`processing_pattern` 和 `example`。
- document 路径必须是 `references/` 或 `examples/` 下的安全 POSIX 相对路径，
  扩展名必须为 `.md`。
- 每个文档必须是非空 UTF-8 Markdown，且 hash 与 manifest 一致。
- `references/` 必需并至少有一个已声明文档；`examples/` 可选。
- `references/`、`examples/` 下的普通文件必须全部在 manifest 声明；包根目录也
  拒绝未声明文件或目录，避免隐藏学校资产绕过 digest。

## 6. Agent 使用契约

```text
产品启动 / 构建验证
        ↓
加载唯一内置 Knowledge Package
        ↓
Agent 获得通用概念、方法、原则和处理模式
        ↓
当前任务提供学校模板 / 要求 / 示例 / 用户确认
        ↓
Agent + Tools 读取当前任务证据并推导本次规则
        ↓
Tool 按本次规则执行；结果留在任务工作区
```

- `load_knowledge()` 是运行时入口，不接收学校名、版本选择或任务路径。
- `validate_knowledge_package(path)` 只用于构建、测试和维护内置通用包，不表示
  运行时可以挂载学校自定义包。
- Loader 只证明包结构、内容和 digest 完整，不能仅靠代码判断自然语言是否真的
  通用；内容审查和测试继续承担语义边界。
- 应用壳不得把当前任务学校材料复制进内置包；Agent/Tool 也没有 Knowledge 写入
  能力。

## 7. Python 模型与加载器

稳定读取模型：

```text
KnowledgePackage
├── root: Path
├── manifest: KnowledgeManifest
├── overview_markdown: str
└── documents: tuple[KnowledgeDocument, ...]

KnowledgeManifest
├── package_id / version / scope / title
├── document_specs: tuple[KnowledgeDocumentSpec, ...]
├── review: KnowledgeReview
└── content_digest

KnowledgeDocument
├── spec: KnowledgeDocumentSpec
└── markdown: str
```

删除以下旧公共面，不保留兼容别名：

- `SchoolKnowledgePackage`
- `KnowledgeSource` / `KnowledgeSourceKind`
- `KnowledgeAsset`
- `load_school_knowledge()`
- school identity、applicability、template/profile 字段和 source 文件语义

## 8. Digest 与安全

`content_digest` 保持确定性 framing：

1. 安全解析并校验 manifest；
2. 移除 `content_digest`；
3. 将审核日期规范化为 `YYYY-MM-DD`；
4. 编码为 UTF-8、键排序、无多余空白且禁止 NaN 的 canonical JSON；
5. 加入虚拟条目 `manifest.yaml`、`knowledge.md` 和全部声明的 Markdown；
6. 按 POSIX 相对路径排序；
7. 每项写入 8 字节无符号大端路径长度、路径、8 字节无符号大端内容长度和内容；
8. 计算 SHA-256，输出 `sha256:<hex>`。

加载器还必须拒绝绝对路径、`..`、反斜杠、NUL、越界路径、symlink、非普通文件、
非 UTF-8、空 Markdown、未声明文件和 hash/digest 篡改；异常不包含文档正文。

## 9. 验收与证据

### Accepted severities

- P0：长期 Knowledge 仍可保存学校事实、模板或参数。
- P1：文档、公共 API、fixture 或打包产物仍暴露 School Knowledge 语义。
- P2：支持新边界所需的命名、说明与测试清理。

### Accepted cleanup checklist

- [x] 00–06 对 Knowledge、Skill、Eval、任务证据和路线图的定义一致。
- [x] README、`docs/human/**`、migration inventory 和代码边界说明无旧语义。
- [x] 根 `knowledge/` 不再包含 `schools/` 或学校包 authoring 入口。
- [x] Python 公共模型和入口只表达通用内置包。
- [x] 内置 v1 包包含四类通用内容并随构建产物发布。
- [x] fixture/test 证明学校字段、模板/profile、隐藏文件和篡改被拒绝。
- [x] 全仓 stale-reference 搜索、构建、lint、typecheck、pytest 和 doctor 通过。

### Evidence ladder

- L0：全仓引用搜索、目录/构建归档检查、`git diff --check`。
- L1：Knowledge loader 单元测试。
- L2：全仓测试、wheel/sdist 构建和导入面检查。
- L3：不需要；本切片不改变真实 DOCX、Provider 或 Agent live 行为。

### Stop condition

上述 checklist 全部满足且 L0–L2 通过后停止。不得顺带实现当前任务学校证据模型、
Tool schema、`convert` 或 M1 后端。

## 10. 后续状态

- M1 Tool contract 已固定当前任务证据、任务根路径、opaque ref 与 render ref 输入边界；
  学校事实仍不进入 Knowledge。
- M2 薄应用壳已把当前任务学校材料、完整通用 Knowledge 和两个 Skill 挂入同一个 SDK
  runtime；真实 SDK + Adobe 产品门仍由统一 M1–M3 计划跟踪。
- 任务输入复制到只读 `input/`，工作副本和最终产物分别进入授权 `work/` 与输出根；
  不新增学校 package 或跨任务清理系统。
- 通用 Knowledge 内容的后续扩展：只允许从多个任务中反复出现且已去学校化的
  概念、方法、原则或处理模式进入，并经产品评审和回归测试发布。

## 11. Refactor gate

```text
Refactor scope: Knowledge Package v1 universal boundary
Discovery source: user definition + 00–06 + current School Knowledge implementation
Target: docs, public Python API, bundled data, fixtures, tests, stale school-package surfaces
Accepted severities: P0/P1 and supporting P2
Parked cross-seam / future ideas: P1 selective Knowledge/task-evidence transport, Tool mappings, convert runtime, M1/M2
Evidence ladder: L0 stale search + L1 unit + L2 full repo/build
Stop condition: one bundled universal package, no persistent school Knowledge, all gates green
Execution risks: inherited dirty docs contain unrelated OfficeCLI/Adobe PDF Services edits; preserve them
Low-value stop signal: changes no longer remove a school-specific persistence surface or prove the new boundary
```
