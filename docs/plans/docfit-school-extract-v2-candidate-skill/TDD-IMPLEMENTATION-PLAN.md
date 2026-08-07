# `docfit-school-extract` v2 分阶段 TDD 实施计划

> 状态：候选实施子计划，尚未开始代码开发。
>
> 上位权威依次为 `PLAN.md` 第 0 节、`DESIGN.md`、`PLAN.md` 其余章节、
> `TOOL-DESIGN.md`、`SCRIPT-DESIGN.md`。本文只安排纵向 TDD 顺序、目标文件和测试。

## 1. TDD 方法

每轮只增加一个公开可观察行为：

```text
选择已批准行为
  → RED：从公开 Tool/CLI/Agent 边界写失败测试并确认失败原因
  → GREEN：实现通过当前行为的最小代码
  → RED：补最重要拒绝或失败不发布测试
  → GREEN：补最小保护
  → REFACTOR：全绿时整理结构
  → 进入下一行为
```

不得先批量写完整阶段测试再批量实现。测试不 mock 自有领域模块，不断言私有函数或无关精确
调用次数。只在 OfficeCLI、LibreOffice、Agent SDK、文件系统故障、时间/随机数等系统边界使用可注入
fake；fake 不能绕过 schema、hash、Registry、DOCX package、marker、locator 和原子发布。

SDK 的 loop、MCP transport、Skill discovery、permissions、session 和 structured-output validation
视为第三方边界，不复制实现。Tool Gate 直接调用 `SdkMcpTool.handler`；Agent Gate 通过现有 SDK
client 接缝运行。

当前只有：

- Tool / Code Gate：四个 Tool + 两个 compiler；
- Agent Gate：候选 Skill + `prepare-template` 编排。

现有独立模板 Eval 是下游兼容性目标，不变成第三个当前 Gate。

## 2. 目标目录

```text
src/docfit/template/
├── __init__.py
├── contracts/
│   ├── __init__.py
│   ├── common.py              # schema/hash/ref/result
│   ├── registry.py            # Registry ref 与 field lookup
│   ├── semantics.py           # protected/slot/remove/manual/gap/unresolved
│   ├── locator.py             # execution locator 与 artifact locator
│   ├── mutation.py
│   ├── review.py
│   ├── evidence.py
│   └── artifact.py            # fill contract + build report
├── runtime/
│   ├── __init__.py
│   ├── paths.py
│   ├── canonical.py
│   ├── atomic.py
│   └── store.py
├── ports.py
├── compile_mutation.py
├── compile_artifact.py
├── observation.py
├── mutation.py
├── mutation_modes.py
├── comparison.py
└── artifact_build.py

src/docfit/tools/
├── template_schemas/
│   ├── __init__.py
│   ├── common.py
│   ├── observe.py
│   ├── mutate.py
│   ├── compare.py
│   └── build.py
└── template_tools.py

docs/plans/docfit-school-extract-v2-candidate-skill/scripts/
├── compile_mutation_plan.py
└── compile_artifact_spec.py

tests/
├── fixtures/template_v1/
│   ├── clean/
│   ├── paragraph_placeholder/
│   ├── damaged/
│   ├── decisions/
│   └── modes/
├── support/template_v1/
│   ├── __init__.py
│   ├── docx_factory.py
│   ├── boundary_fakes.py
│   ├── sdk_boundary.py
│   └── artifact_assertions.py
├── contract/template_gate/
│   ├── conftest.py
│   ├── test_observe.py
│   ├── test_mutate.py
│   ├── test_compare.py
│   ├── test_build.py
│   ├── test_compile_mutation.py
│   └── test_compile_artifact.py
└── agent/school_extract_v2/
    ├── conftest.py
    ├── test_zero_mutation.py
    ├── test_mutation.py
    └── test_recovery.py
```

### 2.1 依赖方向

```text
contracts ← runtime
    ↑          ↑
    └── domain services ──→ ports
             ↑
        thin Tool handlers

app/CLI ──→ existing Agent SDK composition seam
tests ──→ public product boundaries
Eval ← files/schema/hash only → product
```

- contracts 不包含 resolver 或业务服务；
- runtime 不识别学校语义；
- domain 不 import `docfit.tools`、`tests` 或 Eval Python 包；
- Tool schema 不复制 domain model 的业务判断；
- Skill scripts 只调用产品 compiler 入口；
- test fake 与产品 port 同形，但只存在 tests。

### 2.2 文件规模

- 产品 `.py` 目标不超过 400 行；接近 350 行时检查拆分；
- Tool handler 只做 schema→domain→SDK result 转换；
- 不创建 `utils.py`、`helpers.py`、`models.py` 大杂物；
- 尚未开放的 mutation mode 不创建空文件；
- 拆分按变化原因，不按“每个类一个文件”。

规模约束是可维护性提示，不得为了行数制造浅转发层。

### 2.3 产品与测试隔离

产品代码不得 import `tests`、读取 fixtures、依赖 pytest 或 test-only env。W6 打包不得包含测试
builder/fake/harness。产品需要的 schema/model 必须拥有真实运行用途，不能借用 Eval schema 的
文件路径作为运行时依赖。

## 3. 阶段总览

| 阶段 | 纵向结果 | 覆盖工作包 |
|---|---|---|
| P1 | 零 mutation 模板从 observe 到一次 build | W0、W1、W2、W3、W4 的最小子集 |
| P2 | 首个安全 slot + 删除 mutation | W1–W4 增量 |
| P3 | 真实场景驱动的 mutation mode 递增 | W2–W4 增量 |
| P4 | Agent + `docfit prepare-template` | W5 |
| P5 | 原子生产切换 | W6；单独批准且依赖转换端设计 |

每阶段只使用已经在 Tool / Code Gate 证明的能力。

## 4. P1：零 mutation Tool tracer

### 4.1 场景

输入是一份已经干净的合成模板，包含：

- 一个 protected 标签；
- 一个已存在的 content control；
- `w:alias` 指向 Registry `field_id`；
- `w:tag` 保存稳定 `slot_id`；
- 一页可完整验证的内容。

不执行 mutate，但必须完成：observe → final compare → artifact decisions/spec → build。

### 4.2 TDD 循环

1. RED→GREEN：Registry ref/hash、field lookup 和 marker model。
2. RED→GREEN：task path、canonical/hash、atomic write 和 task-local store。
3. RED→GREEN：`template_observe.create` 建立 snapshot，无视觉转换。
4. RED→GREEN：observe query 返回全部/零匹配，重复不静默选择。
5. RED→GREEN：quick/candidate-verification render 与 images cursor。
6. RED→GREEN：`template_compare.final_review` 生成最终全页 required images。
7. RED→GREEN：Agent dispositions 编译成 `ReviewRecordV1`。
8. RED→GREEN：artifact compiler 生成带 Registry、field、marker、持久 locator 的 spec。
9. RED→GREEN：`template_build` 发布四文件目录。
10. RED→GREEN：生成的 `fill-contract.json` 通过现有 Eval schema/input loader。
11. 逐项补 source drift、Registry drift、marker mismatch、locator ambiguity、review 缺页、output
    exists、atomic failure 不发布。

### 4.3 主要文件

P1 只创建本 tracer 实际需要的 contracts/runtime/observe/compare/build/compiler/tool schema 文件；
不创建 mutation mode 实现。

### 4.4 通过标准

- source 和 Registry 字节不变；
- snapshot/render/comparison 绑定精确 hash；
- final review 覆盖全部页面；
- artifact locator 不包含 snapshot ref 或临时 object ID；
- 成功目录只有 `clean-template.docx`、`fill-contract.json`、`visual-review.json`、
  `build-report.json`；
- DOCX 可打开，contract schema 合法，file hashes 可重算；
- blocked/error 不创建输出目录；
- 结果和文件只表达当前 built/blocked 合同。

定向命令：

```bash
uv run pytest -q \
  tests/contract/template_gate/test_observe.py \
  tests/contract/template_gate/test_compare.py \
  tests/contract/template_gate/test_compile_artifact.py \
  tests/contract/template_gate/test_build.py
```

## 5. P2：首个安全 mutation tracer

### 5.1 产品场景

使用一个含可见示例文字的合成段落：

1. 把明确位置物化为 content control slot；
2. 使用独立 `remove_content` 清理已授权示例文字；
3. 保留 paragraph/container/style；
4. compare 证明只有预期变化；
5. final review 后一次 build。

初始删除 mode 推荐 `clear_text_preserve_container`，因为它最贴近“保留版式、清理示例”的用户
价值，边界也最小。开始 P2 前在 Plan 决策记录中确认该 mode。

### 5.2 TDD 循环

1. RED→GREEN：mutation decisions/plan 的 Registry、field、marker 和 target。
2. RED→GREEN：slot operation 创建 `w:alias=field_id`、`w:tag=slot_id`，不插入占位文字。
3. RED→GREEN：删除 operation 要求责任迁移或当前任务精确授权。
4. RED→GREEN：两个 operation 按顺序在临时副本执行并生成 after snapshot/mutation evidence。
5. RED→GREEN：after snapshot/mutation evidence 只在 commit 后发布。
6. RED→GREEN：mutation compare 报告 expected/unexpected diff 和 required images。
7. RED→GREEN：最终 artifact spec/build 使用新的当前 ref/hash。
8. 逐项补 duplicate target、stale ref、source changed、missing authority、protected change、
   package validation failure 和 output exists。

### 5.3 通过标准

- source 不变，mutation output 是新文件；
- alias/tag/slot/field 在 DOCX 与 fill contract 一致；
- 示例文字删除但 container/style 保留；
- 任何失败没有 output、after snapshot 或 committed mutation ref；
- compare 能区分预期变化与计划外误伤；
- 最终四文件产物通过 P1 全部门。

## 6. P3：mutation 能力逐项递增

只在真实模板场景要求时，从现有合同中逐项开放：

```text
remove_paragraph
remove_table_row
remove_table
remove_bounded_block
remove_shape
```

每个微切片必须同时完成：

1. 记录为什么现有 mode 不能正确表达；
2. compiler schema/领域校验 RED→GREEN；
3. Tool schema/执行 RED→GREEN；
4. source readonly 与 rollback；
5. Agent 通过 comparison/render 反馈核对 protected/container/relationship/section；
6. compare expected/unexpected 与 required images；
7. build/fill-contract/remove residue 回归；
8. 一个正例、一个代表性拒绝、一个失败不发布。

不得把所有 mode 一次实现，也不得用一个宽泛 `delete_anything` 模式绕过责任。

## 7. P4：Agent 编排与公共 CLI

### 7.1 目标

在四个 Tool 和两个 compiler 全绿后，通过现有 SDK composition seam 建立候选 Agent Gate，并
实现 `docfit prepare-template` 的应用壳。

### 7.2 TDD 循环

1. RED→GREEN：CLI 参数、输入复制/挂载、task root 和退出码。
2. RED→GREEN：候选 options 使用一个 `ClaudeSDKClient` query/session、filesystem Skill、四个
   candidate Tool、permissions/hooks 和 structured output。
3. RED→GREEN：零 mutation 任务完成并返回 built structured output。
4. RED→GREEN：首个 mutation 任务完成。
5. RED→GREEN：一个 Tool 可恢复错误后使用新路径/ref 重试成功。
6. RED→GREEN：缺用户裁决走 AskUserQuestion/can_use_tool；拒绝或无答案形成 blocked。
7. RED→GREEN：不可恢复错误不发布半成品且交付字段为 null。
8. RED→GREEN：自然语言摘要与 structured output 同源，但机器断言不解析文本。

Agent Gate 可在测试 composition 中把候选四个 `SdkMcpTool` 交给 SDK；不得实现模板专用 Agent
loop、session registry 或 transport。

### 7.3 通过标准

- Tool / Code Gate 全绿；
- 零 mutation、一个 mutation、可恢复失败、不可恢复阻断全部通过；
- structured output 与磁盘路径/hash/counts 一致；
- blocked 不伪造 artifact/template/contract hash；
- Agent 不输出质量分数，不声称模板定版、Human accepted 或 M3 完成；
- source/Registry/input 不变，最终 artifact 只有四文件。

```bash
uv run pytest -q tests/agent/school_extract_v2
uv run pytest -q tests/contract/template_gate tests/agent/school_extract_v2
```

## 8. P5：W6 原子生产切换

### 8.1 准入

P5 必须同时满足：

- P1–P4 全绿；
- 用户单独批准 W6；
- 转换端新 Tool 合同已经设计、实现并证明 `convert-thesis` 可以完成迁移。

如果转换仍依赖旧 `docx_*`，P5 不可开始。

### 8.2 TDD 顺序

1. 生产 Tool contract 先期望四个新 Tool，确认旧注册 RED；原子替换唯一 composition root。
2. Skill contract 先期望新 scripts/references/四 Tool，确认旧 Skill RED；再替换生产 Skill。
3. CLI contract 先期望 `prepare-template`，接入应用壳、structured output 和 observability。
4. 转换/权限/观测 contract 先期望新调用和状态，再迁移所有消费者与映射。
5. packaging/doctor/smoke 证明安装包内容和真实 SDK/provider 路径。
6. 更新 00–06、README、状态文档，删除只服务旧合同的实现/测试。
7. 全绿后清理重复 adapter/schema；不保留别名或双轨。

### 8.3 通过标准

- 安装包只包含一份生产 school-extract Skill 和两个可运行脚本；
- 生产 Agent 只注册批准后的新 Tool 面；
- `prepare-template`、`convert-thesis`、permissions、observability、doctor/smoke 全部同合同；
- 只有当前 built/blocked 生命周期；
- 全仓库 lock/build/ruff/mypy/pytest/doctor/provider/真实 Agent smoke 全绿；
- 长期文档与实现状态同步。

## 9. 与现有 Quality Eval 的关系

独立模板 Eval 的 W0–W5 已实现并有 98 个测试通过。当前只要求产品产物能作为其 Actual 输入：

```text
clean-template.docx → Actual template
fill-contract.json  → Actual fill contract
```

P1/W4 的 cross-contract test 只证明 schema/input compatibility，不评分真实学校质量。三校 Human
Gold 仍为独立工作，不加入 P1–P5 完成门。未来 Eval 报告可以绑定 template/contract hash；不能
把 Agent disposition 直接当作质量结论。

## 10. 每阶段关闭清单

- 每个行为有先 RED 后 GREEN 的记录；
- 当前定向测试及更早回归全绿；
- 断言来自公开 Tool/CLI/Agent 边界；
- 成功产物、代表性拒绝和失败不发布有证据；
- 未实现未批准 mode、兼容层或第二 runtime；
- 产品不 import tests/Eval，测试产物不写产品目录；
- 只在全绿时 refactor；
- `git diff --check` 通过；
- 未执行阶段明确标为未开始，不用计划文本冒充完成。
