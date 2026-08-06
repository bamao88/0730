# `docfit-school-extract` v2 分阶段 TDD 实施计划

> 状态：候选实施子计划，尚未开始代码开发。
>
> 上位权威依次是 `PLAN.md` 第 0 节、`DESIGN.md`、`PLAN.md` 其余章节、
> `TOOL-DESIGN.md` 与 `SCRIPT-DESIGN.md`。本文只安排纵向实施顺序、目标文件和测试驱动
> 循环，不新增产品能力、公开 Tool、工作流状态或测试 Gate。

## 1. 实施方法

开发严格使用小步纵向 TDD：

```text
选择一个已经批准的公开行为
  → RED：先通过公开 Tool/CLI/Agent 入口写一个失败测试，并确认失败原因正确
  → GREEN：只实现让当前测试通过的最小代码
  → RED：补该行为最重要的拒绝或失败不发布测试
  → GREEN：补最小保护
  → REFACTOR：仅在全绿时整理结构，再重跑当前 Gate
  → 进入下一个行为
```

不得先批量写完一个阶段的所有测试，再批量实现所有代码。每轮只增加一个可观察行为；测试
从公开入口断言结果，不 mock 自有领域模块，不断言私有函数、内部类、无关精确调用次数或
实现顺序。只允许在 OfficeCLI、Adobe、Agent SDK、文件系统故障、时间/随机数等系统边界使用
可注入 fake；fake 不能绕过真实 schema、hash、DOCX package、文件集合和原子发布逻辑。

Claude Agent SDK 自带的 loop、MCP transport、Skill discovery、permission resolution、session
和 structured-output validation 视为第三方边界，不在本模块复制实现。Tool Gate 直接调用
`@tool` 生成的 `SdkMcpTool.handler`；Agent Gate 经现有应用入口驱动真实 SDK contract。测试可
脚本化 SDK 边界返回原生 message/result 类型，但不得创建一套行为不同的模板专用 Agent
runtime。

当前仍只有两个产品 Gate：

- Tool / Code Gate：直接调用五个 Tool 和两个编译器 CLI；
- Agent Gate：只在所需 Tool / Code 能力全绿后，从候选 Agent 入口验证编排和最终产物。

内部测试可以帮助定位缺陷，但不能变成第三个完成门。Quality Eval 仍是后续独立计划。

## 2. 目标代码与测试目录

目标目录按“一个文件只有一个主要变化原因”拆分，同时避免大量只有转发逻辑的浅模块：

```text
src/docfit/template/
├── __init__.py                 # 只导出稳定领域入口，不放业务逻辑
├── contracts/
│   ├── __init__.py             # 只导出跨模块稳定类型
│   ├── common.py               # schema version、hash、ref、result envelope 公共类型
│   ├── semantics.py            # responsibility、slot、fixed、manual、gap、unresolved
│   ├── mutation.py             # mutation decision、operation 与 canonical plan 类型
│   ├── review.py               # Agent disposition、ReviewRecord 与 lineage 类型
│   ├── evidence.py             # snapshot/render/mutation/comparison evidence 类型
│   ├── artifact_spec.py        # artifact decision 与 canonical spec 类型
│   └── artifact.py             # candidate/frozen manifest 与 build/freeze report 类型
├── runtime/
│   ├── __init__.py             # 不导出领域服务
│   ├── paths.py                # task-root、canonical path、symlink 与读写边界
│   ├── canonical.py            # canonical JSON、SHA-256 与 digest
│   ├── atomic.py               # 原子文件/目录发布、fsync、失败清理
│   └── store.py                # task-local immutable evidence store 与 opaque ref 解析
├── ports.py                    # OfficeCLI/Adobe/文件故障等系统边界 Protocol；无业务逻辑
├── compile_mutation.py         # mutation decisions → canonical mutation plan
├── compile_artifact.py         # artifact decisions → canonical artifact spec/review record
├── observation.py              # observe create/query/images 领域服务
├── comparison.py               # mutation/final review、diff 与 required images
├── mutation.py                 # mutation 事务、顺序、rollback、统一后置检查
├── mutation_modes.py           # 已开放 slot/removal 原语；达到拆分阈值后再变成子包
├── artifact_build.py           # final snapshot + artifact spec → candidate
└── artifact_freeze.py          # 独立重验 candidate → frozen + artifact_ref

src/docfit/tools/
├── __init__.py                 # 现有唯一 SDK MCP composition root；P5/W6 原子替换 DOCFIT_TOOLS
├── template_schemas/
│   ├── __init__.py             # 汇总导出五个 Tool schema，不放字段定义
│   ├── common.py               # schema_version、task_root、路径/ref 等共享字段
│   ├── observe.py              # observe create/query/images schema
│   ├── mutate.py               # mutate schema 与已开放 operation/mode 枚举
│   ├── compare.py              # compare create/images schema
│   └── artifact.py             # build/freeze schema
└── template_tools.py           # 5 个原生 @tool 定义/handler；无自建 dispatcher/server

docs/plans/docfit-school-extract-v2-candidate-skill/
└── scripts/
    ├── compile_mutation_plan.py # 候选 Skill 的薄 CLI
    └── compile_artifact_spec.py # 候选 Skill 的薄 CLI

tests/
├── fixtures/template_v1/
│   ├── clean/                  # 零 mutation tracer
│   ├── paragraph_placeholder/  # 首个 mutation tracer
│   ├── damaged/                # 非法/损坏 package
│   ├── decisions/              # 最小 YAML/JSON 与拒绝输入
│   └── modes/                  # 仅随获批 removal/slot slice 增加
├── support/template_v1/        # 仅测试使用；绝不进入产品 wheel/Skill
│   ├── __init__.py             # 测试辅助包；不从产品代码导入
│   ├── docx_factory.py         # 生成最小测试 DOCX/package
│   ├── boundary_fakes.py       # OfficeCLI/Adobe/故障注入 fake
│   ├── sdk_boundary.py         # 原生 SDK message/result fixture；不实现 Agent loop
│   └── artifact_assertions.py  # 文件集、schema、hash/ref 复算断言
├── contract/template_gate/     # 同一个 Tool / Code Gate，可拆文件但不拆责任
│   ├── conftest.py
│   ├── test_observe.py
│   ├── test_mutate.py
│   ├── test_compare.py
│   ├── test_artifact.py
│   ├── test_compile_mutation.py
│   └── test_compile_artifact.py
└── agent/school_extract_v2/    # 同一个 Agent Gate
    ├── conftest.py
    ├── test_zero_mutation.py
    ├── test_mutation.py
    └── test_recovery.py
```

`contracts/` 只保存跨模块领域模型，不放 resolver 或业务判断；`runtime/` 只提供路径、hash、
原子发布和 evidence store，不识别学校语义；`template_schemas/` 只定义传输 schema，
`template_tools.py` 不复制 schema 或领域逻辑；它导出的 `SdkMcpTool` 集合由现有
`build_docfit_server()` 汇总。现有 `src/docfit/app/agent.py::build_agent_options()` 和
`src/docfit/app/convert.py` 的 `ClaudeSDKClient`/structured-output 消费路径只复用、不承载新的
模板领域逻辑，也不新增模板专用 Agent runner。禁止新增
`utils.py`、`helpers.py` 或通用 `manager.py` 作为无边界代码堆积点。

### 2.1 文件规模约束

- 手写生产 Python 文件目标不超过 400 行；超过 400 行必须在当前 GREEN 后说明为何不能按
  责任拆分，超过 450 行不得进入阶段完成结果。
- 测试文件目标不超过 350 行；超过 350 行必须按公开能力评估拆分，超过 400 行不得进入
  阶段完成结果；拆文件后仍归属于原 Gate。
- `__init__.py`、Skill CLI 和 MCP handler 保持薄层；出现领域条件分支时立即下沉到 owner 模块。
- 拆分依据是责任和变化原因，不是机械平均行数；不得为了行数产生只有一两个转发函数的模块。
- `mutation_modes.py` 增长到三个以上已实现 mode 或接近 400 行时，按 `text`、`container`、
  `range` 三类拆为 `mutation_modes/` 子包；未实现的候选 mode 不提前建空文件。
- 每个 `template_schemas/*.py` 只负责表明的 Tool 或共享字段；不得把五个 schema 重新汇总成
  一个大字典文件。`template_schemas/__init__.py` 只汇总导出，公开名称仍由单一
  `template_tools.py` 声明，并由现有 `build_docfit_server()` 注册。
- `contracts/evidence.py` 接近 400 行时，按 observation、mutation、comparison evidence 拆为
  `contracts/evidence/` 子包；ref 绑定和 schema version 仍只来自 `contracts/common.py`。
- `observation.py` 或 `comparison.py` 接近 400 行时，优先把图片分批/manifest 逻辑拆到具名
  子模块；create/query/diff 的领域 owner 仍保持唯一，不能复制 store 或 render 规则。

每个阶段退出前执行一次文件规模检查；它是代码评审约束，不新增产品 Gate：

```bash
find src/docfit/template \
  src/docfit/tools/template_schemas \
  tests/contract/template_gate tests/agent/school_extract_v2 tests/support/template_v1 \
  -name '*.py' -type f -print0 | xargs -0 wc -l
wc -l src/docfit/tools/template_tools.py
```

### 2.2 依赖方向

代码依赖必须保持单向，避免 `template` 领域包与 MCP/现有工具适配器互相导入：

```text
contracts
   ↑
runtime + ports
   ↑
compiler / observation / mutation / comparison / artifact services
   ↑
template_tools（SDK @tool handler）或 Skill compiler CLI
   ↑
现有 build_docfit_server（唯一 SDK MCP composition root）
```

- `contracts/` 不导入 runtime、服务或 `docfit.tools`；`runtime/` 最多依赖 common contract。
- `ports.py` 只声明当前 tracer 实际需要的外部边界协议；领域服务接收协议实例，不直接导入
  `docfit.tools.officecli`、`docfit.tools.adobe` 或 Agent SDK。
- `template_tools.py` 使用 SDK `@tool` 声明 schema/annotations 并调用领域服务；现有
  `src/docfit/tools/__init__.py::build_docfit_server()` 是唯一 composition root，使用
  `create_sdk_mcp_server()` 汇总 Tool 并注入现有 OfficeCLI/Adobe 实现。现有适配器不反向
  导入 `docfit.template`。
- 两个 Skill CLI 只组合对应 compiler，不导入 MCP handler；compiler 不导入 Tool 或 Agent。
- `src/docfit/app/agent.py` 与 `convert.py` 继续拥有 SDK client/options/permissions/hooks/
  structured-output 边界；领域包和 `template_tools.py` 不包装 `ClaudeSDKClient`。
- 如果实现需要打破该方向，必须先拆出明确 owner，不能用局部 import、全局 registry 或
  `utils.py` 掩盖循环依赖。

### 2.3 产品代码与测试代码隔离

目录和依赖规则固定如下：

| 类型 | 唯一允许位置 | 可以依赖 | 禁止依赖/进入 |
|---|---|---|---|
| 产品领域与 runtime | `src/docfit/template/` | 产品 contracts、ports、现有产品适配器的注入实例 | `tests/`、pytest、fixture、fake、test-only env |
| 产品 Tool transport | `src/docfit/tools/__init__.py`、`src/docfit/tools/template_*` | Claude Agent SDK 原生 `@tool`/server、产品 schema、领域入口、现有 OfficeCLI/Adobe adapter | 自建 MCP transport/dispatcher、测试 helper、测试数据路径 |
| 产品 Agent 接缝 | 现有 `src/docfit/app/agent.py`、`src/docfit/app/convert.py` | SDK client/options、permissions/hooks、Skill 与 structured output | 模板专用 Agent loop/session registry/transcript parser、测试 harness |
| 候选产品 Skill 脚本 | 当前候选 `<skill-root>/scripts/` | 对应产品 compiler | pytest、测试 harness、`tests/support` |
| 测试代码 | `tests/contract/`、`tests/agent/`、`tests/support/` | 产品公开入口、测试 fixture/fake/helper | 被产品包反向导入、进入产品 wheel/Skill |
| 测试数据与生成物 | `tests/fixtures/`、pytest `tmp_path` | 测试代码 | `src/`、候选/生产 Skill、正式 output |

实施时还必须遵守：

- `tests/support/template_v1/` 是测试辅助层，不得通过修改 `sys.path` 伪装成产品模块；
- product `ports.py` 只表达真实外部能力，test fake 在 `tests/support/` 实现这些协议；
- 产品代码不得包含只在测试时走到的业务分支；失败注入通过 port 实例完成；
- pytest 及测试数据生成/断言库只能进入开发测试依赖组，不能成为产品 runtime dependency；
- fixture 和 golden 不得成为产品默认值、fallback 或运行时资源；确需随产品发布的 schema/
  资源必须移动到具名产品目录并有独立产品合同；
- 测试产物一律写 `tmp_path`/测试 task root，不在源码树中创建 `work/` 或 `output/`；
- P5 必须从构建后的 wheel 与生产 Skill 包复查，不包含 `tests/`、fixture、fake、harness 或
  测试依赖。

每阶段关闭前做一次静态边界检查；它属于代码评审，不新增测试 Gate：

```bash
rg -n --glob '*.py' '(^|[[:space:]])(from|import)[[:space:]]+tests([.]|[[:space:]]|$)' \
  src/docfit docs/plans/docfit-school-extract-v2-candidate-skill/scripts
rg -n --glob '*.py' 'tests/(fixtures|support)|pytest|test_mode' \
  src/docfit docs/plans/docfit-school-extract-v2-candidate-skill/scripts
```

两条命令都必须无输出；同时检查本阶段新增测试文件全部位于 `tests/`，新增产品文件全部位于上述
产品目录。P5 再以 wheel/Skill 实际文件集合证明打包隔离。

## 3. 阶段总览

| 阶段 | 五阶段产品链位置 | 对应工作包 | 阶段目标 | 是否在当前批准范围 |
|---|---|---|---|---|
| P1 零 mutation Tool tracer | 能力合同 → Tool 证明 | W0、W1 部分、W2 observe、W3 final review、W4 | 不启动 Agent，产出第一个可复算 frozen | 候选实现获批后执行 |
| P2 首个安全 mutation tracer | Tool 证明 | W0/W1/W2/W3/W4 增量 | 用一个批准 removal mode 跑通 slot→remove→compare→freeze | mode 获产品决定后执行 |
| P3 mutation 能力递增 | Tool 证明 | W1–W4 增量 | 一次只开放一个真实场景所需 mode/target/content kind | 按需逐项批准，不要求一次完成 |
| P4 Agent 编排 | Agent 编排 | W5 | Agent 只使用已证明能力完成正常与可恢复失败场景 | P1/P2 所需 Tool Gate 全绿后执行 |
| P5 原子生产切换 | 发布动作 | W6 | 一次替换生产 Tool/Skill/消费者/文档并移除旧合同 | 需要单独批准 |
| F1 Quality Eval | Quality Eval | 后续独立计划 | 独立评价 frozen 的语义、覆盖和视觉质量 | 当前不实施 |

W0 不是一个“先把所有模型和 runtime 写完”的水平阶段。共享类型和 runtime 只能被 P1/P2
的第一个公开行为按需拉入；当两个最小 tracer 所需公共合同全绿后，W0 才视为完成。

## 4. P1：零 mutation Tool tracer

### 4.1 阶段目标

对一份已干净模板，在不调用 `template_mutate` 和 Agent 的情况下，通过公开 Tool/CLI 形成：

```text
observe → final_review/images → compile_artifact_spec → build → freeze
```

阶段结果必须是完整 frozen 五文件目录，源 DOCX 不变，hash/ref/`artifact_ref` 可复算。P1
只证明机械合同和发布安全，不评价模板内容是否优秀。

### 4.2 TDD 纵向循环

按下列顺序一次完成一个 RED→GREEN→REFACTOR 循环：

1. `template_observe.create`：有效 clean DOCX 返回 snapshot/hash；源 bytes 不变。
2. `template_observe.create` 拒绝损坏 package、越界路径和观察中 source drift，且不发布 evidence。
3. `template_observe.query`：重复文字返回全部稳定候选，零匹配仍成功；旧/跨任务 ref 拒绝。
4. `template_observe.images`：已存在 render 按 page/cursor 无重复无缺页返回；批次超限拒绝。
5. `template_compare.create(final_review)`：为精确最终 hash 登记 authoritative 全页清单。
6. `template_compare.images`：只返回 comparison manifest 已登记图片，不临时重渲染。
7. `compile_artifact_spec.py`：零 mutation + 完整 final review 生成逐字节稳定 spec；缺页、旧 ref、
   machine blocker 或已存在不同 output 时失败且不覆盖。
8. `template_build`：只发布 candidate 四文件；hash/spec/slot/review 错误时目录不存在。
9. `template_freeze`：独立重读后发布 frozen 五文件和可复算 `artifact_ref`；candidate 被篡改或
   source drift 时返回 blocked/失败且无 frozen。
10. 通过公开入口跑完整零 mutation 链，证明各阶段 ref/hash 和文件集合可连续消费。

每个 Tool 首次 GREEN 同时证明它确实是 SDK `SdkMcpTool`、名称/schema/annotations 正确，
handler 返回原生 content/`structuredContent`/`is_error` 形态；这仍是直接 Tool contract，不
增加 SDK transport 集成 Gate。

### 4.3 主要文件

P1 只创建/实现当前循环需要的 `contracts/common.py`、`contracts/semantics.py`、
`contracts/review.py`、`contracts/evidence.py`、`contracts/artifact_spec.py`、
`contracts/artifact.py`、`runtime/paths.py`、
`runtime/canonical.py`、`runtime/atomic.py`、`runtime/store.py`、`ports.py`、`observation.py`、
`comparison.py`、`compile_artifact.py`、`artifact_build.py`、`artifact_freeze.py`、两份 Tool
transport 层（`template_tools.py` 与 P1 所需 schema 文件）和 artifact compiler CLI。不得为
mutation mode 提前写空实现或 schema。P1 不新建 MCP server；只让候选 `template_tools.py`
导出 Tool 对象，生产 `build_docfit_server()` 的注册替换留到 P5/W6。

### 4.4 通过标准

- 上述每个已开放行为至少有一个成功断言和一个代表性拒绝/不发布断言；
- 测试只通过公开 Tool 注册边界或真实 compiler CLI，不直接调用私有 validator；
- deterministic 测试只在 Adobe/OfficeCLI 外部适配边界使用 fake，DOCX package、schema、
  canonical bytes、hash、ref、文件集合和 rename 使用真实实现；
- candidate 永不含 `freeze-report.json`，frozen 恰好包含五个文件；
- phase 结束时所有目标文件满足第 2.1 节规模约束。

阶段定向命令：

```bash
uv run pytest -q tests/contract/template_gate/test_observe.py
uv run pytest -q tests/contract/template_gate/test_compare.py
uv run pytest -q tests/contract/template_gate/test_compile_artifact.py
uv run pytest -q tests/contract/template_gate/test_artifact.py
```

退出前再运行：

```bash
uv run ruff check src/docfit/template src/docfit/tools tests/contract/template_gate
uv run mypy src
uv run pytest -q tests/contract/template_gate
uv run docfit doctor
```

## 5. P2：首个安全 mutation tracer

### 5.1 产品决策与阶段目标

推荐首个 mutation slice 为：

```text
现有段落上的 scalar slot
  + materialize_slot
  + clear_text_preserve_container
```

原因是它覆盖最常见的标题/姓名类示例清理，并以保留容器的最小删除范围验证 slot、责任迁移、
原子修改和 compare 主链。该推荐必须在 P2 开始前由用户确认为本次开放 mode；若选择其他
真实场景，先同步本文的 P2 fixture/行为，不得同时开放多个 mode。

阶段目标是直接通过 Tool/CLI 跑通：

```text
observe
  → compile_mutation_plan
  → mutate(materialize_slot + clear_text_preserve_container)
  → mutation_review/images
  → final_review
  → compile_artifact_spec
  → build
  → freeze
```

### 5.2 TDD 纵向循环

1. `compile_mutation_plan.py` 先证明零 operation 计划可稳定编译，再编译一个合法“先建槽、
   后删除”的 plan，输出 canonical digest。
2. 编译器拒绝未来依赖、责任未迁移、manual 冒充 automatic、未授权 fixed 删除和 mode/object
   mismatch，失败不覆盖 output。
3. `materialize_slot` 在现有段落写不可见且唯一的 `slot_id` anchor，重开 DOCX 后可重解，
   可见内容、容器和样式不变。
4. `clear_text_preserve_container` 清除获准文字，保留段落属性、slot anchor 和邻近对象；input
   DOCX bytes 不变，output 是新文件。
5. 多 operation 中第二步故障时整次 mutation 回滚，output 不存在且无 after/mutation evidence。
6. `mutation_review` 将两个计划 operation 与实际变化对应；计划外 fixed/section/page 变化形成
   machine blocker。
7. 首个 mutation 完整链最终生成 frozen；所有 lineage 指向当前 after/final hash。

### 5.3 主要文件

在 P1 基础上按需增加 `contracts/mutation.py`、`compile_mutation.py`、`mutation.py`、
`mutation_modes.py`、mutation compiler CLI，以及
mutate/compiler contract tests。comparison、artifact 和 runtime 只扩展当前行为，不复制
第二套模型/store。

### 5.4 通过标准

- `materialize_slot` 与 `clear_text_preserve_container` 的成功、object mismatch、stale ref、
  postcondition failure 和中途 rollback 均从公开 Tool/CLI 可观察；
- 源文件 hash/bytes 不变，成功 output 可重新打开；失败 output 不存在；
- slot anchor 唯一、不可见，删除 action 不吞掉 container/style/anchor；
- compare 能区分 expected/unexpected，最终 frozen 的 mutation evidence chain 连续；
- 其余五种候选 removal mode 仍返回稳定 unsupported，不得静默映射到当前 mode；
- 所有 P1 测试继续全绿，文件规模满足第 2.1 节。

阶段定向命令：

```bash
uv run pytest -q tests/contract/template_gate/test_compile_mutation.py
uv run pytest -q tests/contract/template_gate/test_mutate.py
uv run pytest -q tests/contract/template_gate/test_compare.py -k mutation
uv run pytest -q tests/contract/template_gate
```

## 6. P3：mutation 能力逐项递增

### 6.1 阶段目标与选择规则

P3 不是一次实现剩余全集。只有真实产品场景出现并明确选择后，才为一个 mode、slot target
或 content kind 启动一个微切片。建议优先顺序如下，但未获选择的条目保持 unsupported：

| 微切片 | 新增能力 | 最小 fixture | 关键保护 |
|---|---|---|---|
| P3-A | table-cell scalar slot + `clear_cell_preserve_grid` | 含 merge/grid/row height 的单元格示例 | grid、merge、cell/row properties、相邻单元格 |
| P3-B | `remove_inline_fragment` | 跨 run 的混合文字/标点/域 | 周边 run、空格、标点、域、顺序 |
| P3-C | paragraph-stream slot + `remove_bounded_block` | 显式起止边界的连续段落块 | 两端边界、范围外 fingerprints、分页/分节 |
| P3-D | `unwrap_control_preserve_content` | 内容控件含获准内部内容 | 内部内容、顺序、格式、anchor |
| P3-E | `remove_container` | 无存续责任的完整段落/容器 | 邻接结构、编号、分页、分节 |
| P3-F | `composite` responsibility 合同 | 已存在表格/域/生成机制 | 只登记/定位受支持结构，不提前生成复杂对象 |

阶段目标不是“完成表中所有能力”，而是让当前获批真实场景所需的一个新能力通过完整
Tool / Code Gate，并继续产出可复算 frozen；没有场景和产品决定时，P3 可以停在任意已通过
的微切片，不形成阶段债务。

### 6.2 单个微切片的 TDD 循环

每个微切片都重复同一 TDD 模板：

1. RED：合法公开输入当前返回 unsupported；确认失败来自能力未开放。
2. GREEN：实现该 mode/target 的最小成功路径并验证精确物理后置条件。
3. RED：加入最重要的 object-kind mismatch 或保护项被破坏反例。
4. GREEN：实现拒绝/rollback；失败不得发布 output/evidence。
5. RED→GREEN：让 mutation comparison 能准确对账该新变化和图片范围。
6. 全绿后 refactor；如果 `mutation_modes.py` 达到阈值，按第 2.1 节责任拆包。
7. 用该 fixture 跑到 frozen，证明新能力没有破坏 build/freeze 和旧 mode。

### 6.3 单个微切片通过标准

- 当前 mode 的合法对象正例、错误对象反例、stale ref、保护项、rollback 和 compare 全绿；
- compiler 与 Tool 同时开放同一 mode，不允许一端先宣称支持；
- 未选择 mode 仍稳定拒绝；
- 全量 `tests/contract/template_gate` 通过；
- 不因为增加一个 mode 扩大公开 Tool 数量、脚本数量或 Agent loop。

每个微切片至少运行：

```bash
uv run pytest -q tests/contract/template_gate/test_compile_mutation.py -k '<mode-or-target>'
uv run pytest -q tests/contract/template_gate/test_mutate.py -k '<mode-or-target>'
uv run pytest -q tests/contract/template_gate/test_compare.py -k '<mode-or-target>'
uv run pytest -q tests/contract/template_gate
```

## 7. P4：Agent 编排与 Agent Gate

### 7.1 阶段目标

在 P1 与 P2 所需 Tool / Code 行为全绿后，让候选 Skill 通过真实应用/Agent 入口完成零 mutation
和一个已支持 mutation 场景。Agent Gate 证明必要调用依赖、有效 ref/hash、失败返工、完整
frozen 及最终回复一致性；不评价槽位语义或视觉判断质量。

### 7.2 TDD 纵向循环

1. RED→GREEN：在现有 `ClaudeSDKClient` 的一个 query/session 内，零 mutation 输入最终产生
   完整 frozen；`ResultMessage.subtype` 成功，`structured_output` 的路径/hash/status/
   `artifact_ref`/结构化数量与磁盘 manifest 一致。
2. RED→GREEN：首个 mutation fixture 使用已经证明的 plan/mode，并得到连续 lineage 的 frozen；
   只从 SDK `ToolUseBlock` 断言必要依赖和输入 ref/hash，不固定完整 transcript。
3. RED→GREEN：让一次 Tool handler 返回原生 `is_error`（stale ref 或目标已存在）；SDK 保持同一
   loop，Agent 重新观察/编译并使用新 attempt 路径，最终成功，旧证据未混入。不得由 harness
   自动替 Agent 重试。
4. RED→GREEN：缺用户授权/裁决走原生 `AskUserQuestion` + `can_use_tool`；若无答案则不发布
   candidate/frozen，并返回结构化 blocked 结果，不创建 pause/question 文件。
5. RED→GREEN：最终 structured output 不输出质量分数、不声称 M3/Eval 通过，也不把 candidate
   当交付物；自然语言摘要不作为机器字段来源。

每个测试任务只启动一次 SDK query，不自建 turn loop、session registry、Skill loader、权限
resolver、重试 workflow 或 structured-output parser。确定性 Gate 可在 `tests/support/` 脚本化
Agent SDK 系统边界并使用原生 message/result 类型，但只能断言影响正确性的依赖顺序和传递值，
不固定内部推理、无关调用次数或逐字回复。至少保留一个真实 SDK smoke 供 P5 切换前验证，
不在每个 RED/GREEN 循环中消耗外部调用。

### 7.3 主要文件

本阶段主要修改候选 `SKILL.md`/references，并最小更新现有应用 Agent options/query 的可注入
接缝；测试驱动与 fake 只放在 `tests/agent/`、`tests/support/`，产品侧不创建 Agent harness。
领域行为缺陷必须回到 P1–P3 owner 修复，不能写进 prompt 绕过。Skill/reference 在本阶段只把
已经通过 Tool / Code Gate 的 mode/target/content kind 标为可调用；合同中其余候选能力继续
明确为 unsupported。

### 7.4 通过标准

- Tool / Code Gate 继续全绿，Agent 测试不绕过公开 Tool 或自行伪造 evidence；
- 零 mutation、一个获批 mutation、可恢复失败和不可恢复失败四类场景均从候选 Agent 入口
  得到约定结果；
- 成功场景的最终五文件集合完整，structured output 与用户回复中的路径、hash、状态和
  结构化数量都与磁盘一致；
- `output_format` 是显式 JSON Schema，Agent Gate 直接读取
  `ResultMessage.structured_output`，不从最终文本抽取 JSON；
- 失败场景不发布半成品，重试不混用旧 attempt 的 ref/hash/evidence；
- Agent 不输出语义/视觉质量分数，不声称 Quality Eval 或 M3 已通过；
- Agent 测试文件满足第 2.1 节规模约束。

```bash
uv run pytest -q tests/agent/school_extract_v2/test_zero_mutation.py
uv run pytest -q tests/agent/school_extract_v2/test_mutation.py
uv run pytest -q tests/agent/school_extract_v2/test_recovery.py
uv run pytest -q tests/contract/template_gate tests/agent/school_extract_v2
```

## 8. P5：W6 原子生产切换

### 8.1 阶段目标

P5 需要用户单独批准。TDD 先修改生产合同测试，使当前旧 Tool/Skill 路径因不符合新合同而
RED；随后在同一变更中替换注册、权限/观测映射、生产 Skill、两个脚本、下游消费者和 00–06，
最后删除旧路径及只服务旧合同的测试，不保留别名或双 schema。

阶段目标是让候选实现一次性成为唯一生产实现，并让代码、安装包、消费者、长期文档与测试
重新处于同一个合同版本；本阶段不增加产品能力，也不把切换拆成长期双轨运行。

### 8.2 TDD 纵向循环

主要 RED→GREEN 顺序：

1. 生产 Tool contract 先期望五个新 SDK `SdkMcpTool` 名称、schema/annotations 和原生结果形态，
   确认旧注册导致 RED；再在现有 `build_docfit_server()` 中原子替换 `DOCFIT_TOOLS`，不增加
   第二个 MCP server。
2. 生产 Skill contract 先期望新脚本、references 和五 Tool 能力，确认旧只读 Skill 导致 RED；
   再原子替换候选 Skill。
3. 下游/权限/观测 contract 先期望新名称与状态，再在现有 `build_agent_options()`、hooks、
   allowlist 和 structured-output 消费路径中替换映射；不创建新权限/Agent/session 层。
4. packaging/doctor 先证明 wheel 缺少或多带路径，再修正包内容并移除旧实现。
5. 全绿后清理重复 adapter/schema/测试；每次清理后重跑相关公开 contract。

### 8.3 通过标准

- 安装包只包含一份生产 `docfit-school-extract`，两个脚本能从安装后的 Skill 根运行；
- 只注册五个新 Tool，旧 `docx_*` 公共合同及兼容别名不存在；
- Agent 仍由现有 `ClaudeSDKClient`、SDK Skill discovery、permissions/hooks、AskUserQuestion 和
  `ResultMessage.structured_output` 运行，没有新增模板专用 loop/loader/parser；
- candidate/frozen、权限、隐私、observability、convert 消费方和长期文档一次对齐；
- Tool / Code Gate、Agent Gate、既有全量回归、provider 与真实 Agent smoke 全绿；
- 所有新增/重构 Python 文件满足第 2.1 节规模约束。

完成命令：

```bash
uv sync --frozen
uv lock --check
uv build
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run docfit doctor
uv run docfit doctor --require provider
uv run docfit agent-smoke --case image
uv run docfit agent-smoke --case ask-user
uv run docfit agent-smoke --case denied-tools
uv run docfit agent-smoke --case path-tools
uv run docfit agent-smoke --case subagent
uv run docfit doctor --require agent-smoke
```

真实 Adobe 验证优先复用合法 cache；不得为了测试循环制造无意义 Document Transaction。

## 9. F1：后续 Quality Eval（当前不实施）

### 9.1 阶段目标

阶段目标是独立回答“这个 frozen 对象做得好不好”，覆盖语义正确性、学校要求覆盖度、视觉
质量与 blocking findings；它不得重新承担 Tool 机械正确性或 Agent 编排证明。

### 9.2 TDD 纵向循环

F1 需另行批准并先对齐 `docfit-template-extraction-eval` 设计。其 TDD tracer 必须从一个已经通过
前两 Gate 的 frozen 五文件目录开始，而不是从 Agent transcript 或 work evidence 开始：

1. RED→GREEN：读取 frozen，验证 `artifact_ref`/template hash，输出绑定同一身份的报告。
2. 逐项 RED→GREEN：slot、fixed、manual、gap、unresolved 的 Actual–Gold 语义断言。
3. RED→GREEN：学校要求覆盖度及缺失要求形成结构化 finding。
4. RED→GREEN：独立视觉规则/Gold 判断，不把 Agent `accepted` disposition 当作质量结论。
5. RED→GREEN：blocking finding 不能被总分掩盖；报告稳定生成机器 JSON 与人工摘要。

### 9.3 通过标准（未来计划的退出条件）

- Eval 只读取冻结五文件和另行批准的 Eval/Gold 输入，不读取 Agent transcript 形成质量结论；
- slot、fixed、manual、gap、unresolved、学校覆盖、视觉与 blocking findings 都有独立可定位断言；
- 报告中的对象身份与输入 `artifact_ref`/template hash 一致，机器 JSON 与人工摘要结论不冲突；
- blocking finding 不得被平均分、总分或 Agent disposition 覆盖；
- Eval 测试全绿且不改变既有 Tool / Code Gate 与 Agent Gate 的责任或通过结果。

F1 的测试、Gold、评分器和 runner 属于未来 Quality Eval 模块，不加入当前
`tests/contract/template_gate` 或 `tests/agent/school_extract_v2`，也不成为 P1–P5 的完成门。

## 10. 每阶段统一关闭清单

每个 P1–P5 阶段只有同时满足以下条件才可关闭：

- 本阶段每个行为都留下“先 RED 且失败原因正确、后 GREEN”的执行记录；
- 当前阶段定向测试全绿，所有更早阶段测试无回归；
- 断言来自公开 Tool/CLI/Agent 入口，内部重构不会无意义破坏测试；
- 成功产物、代表性拒绝和失败不发布均有证据；
- 没有实现未批准 action/mode、兼容层、第二 Agent loop 或额外测试 Gate；
- 仅在全绿时 refactor，refactor 后重新运行当前 Gate；
- 文件责任清楚、无重复 owner、无大文件和通用杂物模块；
- 产品文件与测试文件物理分离，产品代码不反向导入或读取测试代码/fixture，测试产物未写入
  产品目录；
- `git diff --check` 通过，文档与当前实现状态一致；
- 尚未执行的后续阶段仍明确标为未开始，不能用计划文本冒充实现完成。
