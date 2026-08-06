# `docfit-school-extract` v2 候选实施与验收计划

> 状态：W0–W5 候选实现与验收已完成；已生成真实学校候选产物，尚未执行 W6 生产切换。
>
> 当前已有开发入口 `docfit prepare-template` 和候选 Skill/Tool 组合。生产 Skill、转换链与长期
> 架构基线仍保持现状；只有 W6 获得单独批准后才执行原子生产切换。

## 0. 用户已确认的控制原则

本节是候选目录的最高约束。下层文档或实现与本节冲突时，必须修改下层内容，不能反向解释
本节。

### 0.1 权威与阶段

- 与长期文档不一致时，以本候选计划为准；W6 再一次同步受影响的长期合同。
- 当前仍是研发阶段，只实现直接保护模板产物正确性的最小能力。
- 当前不建立模板 `candidate/frozen` 生命周期，不判断模板是否“定版”，不实现
  `template_freeze`、`freeze-report.json` 或 freeze 专用 `artifact_ref`。
- 当前成功状态是 `artifact_status: built`：只表示四文件产物机械有效并已原子发布，不表示
  Human accepted、质量合格或 M3 完成。
- 现有独立模板 Eval 已实现并有 129 个测试通过；三校 Human Gold 仍未完成。Eval 是实际下游
  消费者，但不成为当前 Tool/Agent Gate。

### 0.2 产品尺度与分阶段落地

1. **设计整理**：统一四 Tool、两个 compiler、一次 build、Registry/Eval 和测试责任。
2. **零 mutation tracer**：从已干净模板跑通 observe、final compare、artifact compile、build。
3. **安全 mutation tracer**：按真实场景逐项开放 `materialize_slot` 和删除 mode。
4. **Agent/CLI tracer**：通过真实 SDK 接缝跑通 `docfit prepare-template`。
5. **生产切换**：W6 单独批准后，一次切换注册、Skill、CLI、消费者、测试和长期文档。

不为假设中的规模、长文档、第三方消费者、动态 Provider、跨任务缓存或复杂工作流提前建设
扩展系统。详细字段和错误码可以在不改变产品责任、公开 Tool/脚本边界、产物文件集和失败
发布语义的前提下小步调整。

### 0.3 当前只有两个产品 Gate

**Tool / Code Gate** 直接调用四个 Tool 和两个 compiler，证明输入/拒绝、源只读、DOCX、
Registry、marker、locator、hash/ref、视觉证据、文件集合与原子发布。

**Agent Gate** 使用 SDK 入口，证明 Agent 传递有效 ref/hash、处理失败、形成完整 built 产物，
并让 `ResultMessage.structured_output` 与磁盘一致。

现有 Quality Eval 独立判断模板质量。它不重新证明 Tool 原子性或 Agent 编排，也不能用分数
覆盖前两个 Gate 的失败。

### 0.4 Claude Agent SDK 原生优先

- 使用锁定的 `claude-agent-sdk==0.2.128` 提供 Agent loop、in-process MCP、Skill、权限、hooks、
  AskUserQuestion、structured output、session 和 compaction。
- DocFit 只实现模板领域合同、task-local evidence、确定性 compiler 和安全副作用。
- 禁止新增第二 Agent loop、Tool dispatcher、MCP transport、Skill loader、权限引擎、提问协议、
  session/attempt registry、transcript workflow、通用 retry engine 或最终文本 JSON parser。
- 四个 Tool 使用 SDK `@tool` 与 `create_sdk_mcp_server()`；最终机器结果使用
  `output_format`/`ResultMessage.structured_output`。

## 1. 候选目录内部裁决顺序

1. 本 Plan 第 0 节；
2. `DESIGN.md`；
3. 本 Plan 其余章节；
4. `TOOL-DESIGN.md` 与 `SCRIPT-DESIGN.md`；
5. `TDD-IMPLEMENTATION-PLAN.md`；
6. `SKILL.md`；
7. `references/*.md`。

如候选文件互相冲突，先统一合同再实现。现有生产代码用于确认迁移事实，不能反向削弱新
合同。

## 2. 本轮文档完成定义

候选文档只有同时满足以下条件才可进入实现：

- 四个公开 Tool 和两个 compiler 的责任、输入、输出、拒绝与非职责一致；
- 产物文件集唯一且固定为四个文件；
- `fill-contract.json` 与现有 `docfit-template-fill-contract/v1` 对齐；
- Registry `field_id`、content-control marker 和持久 locator 合同完整；
- execution locator 与 artifact locator 明确分离；
- `docfit prepare-template` 用户入口、task root 和 structured output 已定义；
- W0–W6 顺序、两个 Gate 和转换端硬依赖明确；
- 文档不声称当前实现、Human Gold、M3 或正式模板质量已经完成。

## 3. 系统不变量

### 3.1 责任边界

- Agent 负责材料语义、字段映射、删除意图、来源冲突、视觉判断、返工和最终任务结果。
- Tool 负责可信 DOCX 事实、受控副作用、hash/ref、结构/视觉证据和原子发布。
- compiler 只把 Agent 决定规范化成 Tool 可重验的输入。
- Skill 提供领域工作方法；它不实现 DOCX 操作或发布边界。
- Eval 独立评价输出质量；它不读取 transcript 替代 Actual，也不修改产品产物。

### 3.2 数据与副作用

- 原始模板、要求、示例和 Registry 输入均保持只读并记录 SHA-256。
- snapshot/render/mutation/comparison evidence 是 task-local、不可变并绑定精确文档 hash。
- execution locator 只在当前 task snapshot 有效；artifact locator 写入 `fill-contract.json` 并由
  最终 `template_sha256` 约束。
- 所有写入目标必须不存在；写临时项、fsync、重读校验后原子 rename。
- stale/ambiguous/cross-task ref、source drift 或 post-check 失败时不发布新 DOCX/产物。
- 运行日志只记录 refs、hashes、counts、codes、durations 和 cache 状态，不记录文档正文、
  decision body、OOXML 或凭据。

### 3.3 Registry 与 marker

- `fill-contract.json` 绑定 Registry ID/version/hash。
- 每个自动 slot 必须有已注册 `field_id`、稳定 `slot_id`、内容类型、required、cardinality、
  artifact locator 和 expected value style。
- `w:alias = field_id`，`w:tag = slot_id`，`w:id` 不承担业务身份。
- 未注册字段不得猜测；必须进入 manual/gap/unresolved。必需自动槽位未注册时阻止 build。
- protected/slot/remove 沿用现有 Eval 的区域 owner；manual/gap/unresolved 写入 build report。

## 4. 公共入口与结果合同

### 4.1 产品 CLI

```text
docfit prepare-template \
  --school-template <template.docx> \
  --school-requirements <requirements-file> \
  --field-registry <content-fields.yaml> \
  --output <task-output-directory>
```

CLI 创建新的 task root，把输入放入只读 `input/`，中间决定/evidence 写入 `work/`，成功产物
发布到 `output/template-artifact/`。输入或目标路径非法返回退出码 2；运行完成但业务阻断也
返回退出码 2；成功 built 返回 0。stdout 输出 structured result 的 JSON，stderr 只输出无敏感
载荷的诊断。

### 4.2 Agent structured output

```yaml
status: built | blocked
artifact_path: output/template-artifact | null
template_sha256: <sha256> | null
fill_contract_sha256: <sha256> | null
counts:
  slot: 0
  protected: 0
  remove: 0
  manual: 0
  gap: 0
  unresolved: 0
```

`status: blocked` 且没有完整可验证产物时，三个交付字段必须为 `null`。应用和测试只读取
`structured_output`；自然语言回复不得作为机器真源。

### 4.3 Tool 结果状态

所有 Tool 使用统一 envelope：

```yaml
schema_version: 1
call_status: ok | needs_input | error
result_state: observed | mutated | compared | built | blocked | null
checks: []
warnings: []
failure: null | {...}
```

- `needs_input`：请求、路径、ref、schema 或用户授权不足；没有副作用。
- `error`：后端、IO 或内部运行失败；没有已发布副作用。
- `ok/blocked`：完整检查已执行但存在业务阻断；没有最终产物。
- `ok/built`：四文件目录已原子发布。

Tool transport success/error 与领域状态分开。即使 MCP 调用成功，也不能把 `blocked` 当作产品
成功。

## 5. 四个 Tool 的可实施接口

| Tool | 公开 action/mode | 关键输入 | 成功结果 |
|---|---|---|---|
| `template_observe` | `create`、`query`、`images` | task root、DOCX/snapshot/render、focus、visual level | 不可变 snapshot/render 或匹配/图片批次 |
| `template_mutate` | plan 内 `materialize_slot`、`remove_content` | mutation plan、新 DOCX 路径 | 新 DOCX、after snapshot、mutation ref |
| `template_compare` | `create` 的 `mutation_review`/`final_review`，及 `images` | before/after/final snapshot、mutation ref | comparison ref、diff、required images |
| `template_build` | 单一 build | final snapshot、artifact spec、新 output dir | 四文件 template artifact |

visual level 固定为 `none | quick | candidate_verification`。`candidate_verification` 使用 Adobe
固定路由并覆盖最终 hash 全页，但不表示 Word/WPS 质量认证。

四个 Tool 的字段、错误码、原子性和 algorithm 见 `TOOL-DESIGN.md`。未列出的 action/mode
默认不支持。

## 6. 两个 compiler

统一 CLI：

```text
uv run python <skill-root>/scripts/<script>.py \
  --task-root <task-root> \
  --input work/decisions/<decision>.yaml \
  --output work/compiled/<canonical>.json
```

只支持 `--task-root`、`--input`、`--output`、`--help`、`--version`。不提供 overwrite、
best-effort、backend/provider、skip-validation 或工作流 mode。

共同要求：

- 输入/输出位于 task root `work/`；输出必须不存在；
- YAML/JSON 拒绝 duplicate key、unknown key、alias/tag、自定义类型、NaN/Infinity；
- canonical JSON 使用 UTF-8、稳定键序和稳定数字/换行规则；
- success stdout 只输出机器摘要，failure stderr 只输出 code/field/path，不回显 decision 内容；
- 脚本 success 不表示 mutate/build success。

详细模型见 `SCRIPT-DESIGN.md`。

## 7. 唯一模板产物合同

```text
template-artifact/
├── clean-template.docx
├── fill-contract.json
├── visual-review.json
└── build-report.json
```

- `clean-template.docx`：最终 snapshot 的逐字节副本。
- `fill-contract.json`：`docfit-template-fill-contract/v1`，包含 Registry、marker、
  protected/slot/remove、持久 locator、value style 和来源证据。
- `visual-review.json`：绑定最终 template hash 的 required images、Agent dispositions 和 findings。
- `build-report.json`：输入/来源 hash、spec/review digest、另外三个 payload 文件的 hashes、checks、
  warnings、manual/gap/unresolved/unregistered fields 和 `artifact_status: built`；它不嵌入自身 hash。

构建失败或 blocked 时整个目录不存在。成功目录只能包含上述四个文件，不创建隐藏状态文件。

### 7.1 与现有 Eval 的映射

现有独立 Eval 直接把：

- `clean-template.docx` 作为 Actual template；
- `fill-contract.json` 作为 Actual fill contract；
- contract 中的 Registry ref 作为字段目录绑定。

Tool / Code Gate 至少用一个合成 build 产物通过现有 Eval 的输入加载合同。产品和 Eval 不互相
import Python 包，只通过文件、schema 和 hash 交互。

## 8. 实施工作包

### W0：共享模型、schema 与 fixture

范围：task paths、canonical JSON、hash/ref、evidence store、Registry、marker、execution/artifact
locator、artifact models，以及最小合成 DOCX/decision fixture。

完成条件：

- 零 mutation fixture 表达一个 protected 标签和一个已注册 content-control slot；
- product-side model 能生成符合 `docfit-template-fill-contract/v1` 的 JSON；
- source/read/write/ref/atomic 边界的代表性拒绝全绿；
- 不提前实现后续 mutation mode 或测试专用产品分支。

### W1：两个 compiler 与候选 Skill 脚本

依赖 W0。实现两份决定到 canonical plan/spec；覆盖 schema、Registry/field、locator、授权、
lineage、review digest、原子写和稳定错误码。

完成条件：相同输入产生逐字节相同输出；无效输入不创建/覆盖输出；脚本能从候选 Skill 根运行。

### W2：observe 与 mutate

依赖 W0，可在共享模型稳定后与 W1 并行。

先实现 observe create/query/images；再按真实 tracer 开放 `materialize_slot` 和首个删除 mode。
每增加一个 mode，compiler、Tool schema、直接测试和后置保护必须在同一微切片完成。

完成条件：源文件不变；重复匹配不被偷偷选中；stale/cross-task ref 拒绝；任何前置/后置失败
不发布新 DOCX；content control 的 alias/tag 符合合同。

### W3：compare 与 review evidence

依赖 W2。实现 mutation/final review、结构 diff、required images、cursor 和 render cache。

完成条件：预期变化可对账，计划外 protected/grid/section/header/footer 变化形成 blocker；最终
`candidate_verification` 精确覆盖当前 hash 全页；旧图片/ref 不能满足新 hash。

### W4：一次原子 build

依赖 W0–W3。实现 artifact spec 重验、Registry/marker/artifact locator、protected/remove、
review、四文件生成和原子发布。

完成条件：

- 任一 source/hash/ref/marker/locator/review/blocker 错误都不创建输出目录；
- 成功目录只有四个文件，hash 可重算，DOCX 可打开；
- `fill-contract.json` 通过现有 Eval schema/input boundary；
- build 只返回 `built | blocked`。

### W5：Agent Skill、公共 CLI 与 Agent Gate

依赖 W1–W4。实现候选 `SKILL.md`/references、`docfit prepare-template` 应用入口和轻量 Agent
Gate。

完成条件：

- 每个 backend attempt 使用现有 `ClaudeSDKClient` 的一个 query/session；超时或可重试的无效结果
  可以切到下一个已配置 backend，但不建立自定义 resume/runtime；
- Agent 只使用已经通过 Tool / Code Gate 的能力；
- 正常、可恢复 Tool 失败和不可恢复阻断至少各有一个场景；
- 返工使用新路径和当前 ref/hash，不混用旧 attempt；
- structured output 与磁盘产物一致；blocked 不伪造交付字段；
- 需要用户裁决时使用 SDK AskUserQuestion/can_use_tool；
- Agent 不输出质量分数，也不声称模板已定版、Human accepted 或 M3 通过。

### W6：原子生产切换与长期文档对齐

依赖 W0–W5 全绿，并需要用户单独批准。

硬前置：转换端新 Tool 合同已经另行设计、实现并证明所有 `convert-thesis` 消费能力可迁移。
在此前不得删除当前转换仍依赖的旧 `docx_*` Tool。

W6 在一个原子变更中：

- 接入 `docfit prepare-template`；
- 替换生产 Skill 和 Tool 注册；
- 更新 permissions、hooks、observability、doctor/smoke；
- 迁移 `convert-thesis` 与全部下游消费者；
- 更新 package、README、测试和 00–06；
- 删除旧 Tool/Skill/schema 及只服务旧合同的测试；
- 运行全量确定性门和真实 SDK/provider smoke。

不保留旧别名、双 schema 或长期双轨，除非届时存在另行批准的真实外部迁移要求。

## 9. 依赖与执行顺序

```text
W0 shared contracts
├── W1 compilers
└── W2 observe/mutate
      └── W3 compare
W1 + W3
  └── W4 build
       └── W5 Agent + CLI
            └── W6 production switch
                 └── requires conversion-side redesign
```

P1 先跨 W0–W4 跑通零 mutation tracer；P2 再补首个安全 mutation；后续 mode 逐项递增。不要
按水平层一次写完所有 models/tests/implementation。

## 10. 测试落点

```text
tests/
├── fixtures/template_v1/
├── support/template_v1/
├── contract/template_gate/
│   ├── test_observe.py
│   ├── test_mutate.py
│   ├── test_compare.py
│   ├── test_build.py
│   ├── test_compile_mutation.py
│   └── test_compile_artifact.py
└── agent/school_extract_v2/
    ├── test_zero_mutation.py
    ├── test_mutation.py
    └── test_recovery.py
```

测试 helper/fake/fixture 只位于 `tests/`，产品代码不得 import 或读取它们。Agent Gate 可用测试
composition 把四个候选 `SdkMcpTool` 交给真实 SDK；这不是第二个产品 server 或 Agent runtime。

定向门：

```bash
uv run pytest -q tests/contract/template_gate tests/agent/school_extract_v2
```

W6 还必须运行 lock/build、ruff、mypy、全量 pytest、doctor、provider 和真实 Agent smoke。

## 11. 关键失败路径

```text
decision 编译失败      → 无 canonical 输出      → 修正决定/证据
stale/ambiguous ref    → 无新 DOCX             → 重新 observe/编译
mutation post-check 失败 → 无新 DOCX            → 缩小 operation
unexpected diff       → comparison evidence     → 返工并使用新 attempt
final review 缺页/跨 hash → 无 artifact spec     → 补精确 hash 审查
Registry/field/marker 错误 → 无 template artifact → 修正字段或槽标记
build blocker         → 无 template artifact     → 回到对应环节
缺用户授权/裁决        → structured blocked      → 不发布产物
```

任何“无输出”都必须断言目标路径不存在或原有目标未变化，不能只检查错误码。

## 12. 当前不在范围

- W0–W5 候选实现已完成；W6 生产切换仍需用户另行明确批准；
- 模板定版、质量认证、Human Gold 或 M3；
- 学生内容提取、Placement 和转换端 Tool 新设计；
- 旧 Tool 兼容层、跨任务缓存、第二 Agent runtime、动态 Provider；
- 在产品模块中实现或 import Eval；
- 将当前任务学校材料写入通用 Knowledge。

## 13. W0–W5 完成状态与证据

- 四个公开 Tool、两个 compiler、task-local evidence、Registry/marker、原子四文件 build 已实现；
- 零 mutation、安全 mutation、Agent/CLI、blocked/recovery 和 changed-template lineage 均有合同测试；
- 真实 SDK 最小任务已通过一个 query/session 生成四文件产物；
- 真实南农输入已生成 `temp/docfit-school-extract-v2-njau-real-r2/output/template-artifact/`：
  18 个 slot、4 个 manual、3 个 gap、0 个 unresolved，12 页最终候选证据均有 disposition；
- 产物 hash、来源 hash、Registry/marker、locator、mutation lineage、最终视觉覆盖和四文件集合
  均由 compiler/build 独立重验，真实 `fill-contract.json` 通过独立 Eval schema；Word 内容效果仍
  按用户约定由人工判断；
- 根项目全量回归 348 项通过，最终受影响的 Tool/Agent/CLI 合同 42 项通过；root 的
  lock/build、ruff、strict mypy、doctor 以及独立 Eval 的 lock/build/ruff/mypy/129 项测试均通过；
- W6 的转换端硬依赖尚未满足，保持不可执行。

真实学校运行暴露并已修正两个合同缺口：只要最终模板 hash 与学校源模板不同，artifact spec 和
builder 都强制要求非空、连续且比较无 blocker 的 mutation lineage；观测侧扁平样式事实必须由
compiler 规范化为公开 `font/paragraph` 结构，并由 builder 独立重验。旧的无 lineage/旧样式合同
构建结果均已归档，不作为交付产物。

## 14. Claude Agent SDK 官方依据

- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- [Custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)
- [Permissions](https://code.claude.com/docs/en/agent-sdk/permissions)
- [Hooks](https://code.claude.com/docs/en/agent-sdk/hooks)
- [Skills](https://code.claude.com/docs/en/agent-sdk/skills)
- [User input](https://code.claude.com/docs/en/agent-sdk/user-input)
- [Structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
- [Sessions](https://code.claude.com/docs/en/agent-sdk/sessions)
- [Python reference](https://code.claude.com/docs/en/agent-sdk/python)
