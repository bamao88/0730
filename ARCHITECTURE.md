# DocFit 架构

状态: 当前架构入口
更新日期: 2026-09-28

DocFit 围绕 Claude Agent SDK 构建。SDK 负责 Agent loop、session、Tool 调用、
权限、Skill、Subagent、上下文管理和 lifecycle。DocFit 负责论文领域合同、
确定性 DOCX 操作、Eval/Gold、视觉证据和薄应用适配层。

DocFit 不应长出第二套 Agent runtime。行为失败时，沿输入事实、语义判断、映射、执行、
验收追查偏离发生的位置，在对应责任层修复。只有确认是领域指引不足，才改 Skill/Reference；
不能用提示词弥补执行能力缺口，也不能把一次模型错误固化成应用自有语义流程。

## 开发判断依据

架构说明规定应当成立的关系，不证明实现已经成立。每次开发需把以下依据对齐；不另建一份重复的架构或规则清单。

| 必须明确的内容 | 权威位置 | 用来回答的问题 |
| --- | --- | --- |
| 产品目标、模块输入输出与禁读边界 | 本文、对应模块 Contract | 用户最终得到什么，本次工作负责到哪里？ |
| 完整流程、各层职责、阶段出口 | 对应模块文档 | 谁判断、谁执行、谁验收，什么成立后才能进入下一阶段？ |
| 跨层传递的语义与范围不变量 | 对应 Contract，术语见 `CONTEXT.md` | 转换前后必须保持什么，哪些只是内部表示？ |
| 现有能力、未完成范围和验证层级 | `STATUS.md` 及其当前证据链接 | 哪些只是设计要求，哪些已经实现并验证？ |
| 本次现象、已证实原因、待验证假设及修复边界 | 本次任务的现有 bug / plan | 证据支持修哪一层、哪一类问题，什么结果会推翻当前方案？ |

推进顺序是：确认交付目标与合同 → 用失败和成功对照确认原因及影响范围 → 验证共同修复路径
能正向完成任务 → 接入并回归关联路径 → 真实回放、Agent 闭环及产物验收。每一步按证据决定下一步，
不能从个例直接推出全系统根因，也不能把“阻止错误产物”当作“合法任务已完成”。
计划记录如何推进；Contract 与模块文档定义应当如何工作；状态与证据说明现在做到了哪里。

## 模块

| 模块 | 输入 | 输出 | 禁止事项 |
| --- | --- | --- | --- |
| 模板提取 | 学校模板、可选学校要求、Field Registry | `final-template.docx`、`fill-contract.yaml` | 读取学生论文、注入学生内容、生成最终论文 |
| 用户内容提取 | 学生源文档、Field Registry | Student Content Model | 读取学校模板、选择目标位置或目标样式 |
| final word 生成 / Final Content Fill | 模板产物、Student Content Model、任务补充信息 | 一份最终 Word 文档 | 重新识别学校要求或学生内容 |

这三个模块是并行同级模块。它们通过稳定产物和合同交接，不读取彼此的私有运行状态。

模块工作可以并行推进，但模块上下文必须分开。使用 `docs/modules/README.md` 选择当前任务所属模块的
Contract、状态、Skill 和 Eval 入口。

## 数据流

```text
学校模板 + 可选学校要求 + Field Registry
        -> 模板提取
        -> final-template.docx + fill-contract.yaml

学生源文档 + Field Registry
        -> 用户内容提取
        -> Student Content Model

模板产物 + 学生内容 + 任务补充信息
        -> final word 生成 / Final Content Fill
        -> 最终 Word
```

Eval/Gold 只在运行完成后读取产物。Gold 不得注入正在被评测的 Agent prompt 或 Tool 输入。

## Runtime 形态

模板提取采用 Agent-native、Harness-controlled 的 loop：

```text
Agent 确定学校语义、字段及对应源范围
Harness 解析范围，自动检查覆盖、字段、冲突及可执行性，并按责任归属反馈
Tool 忠实完成对应范围的 DOCX 操作，提供证据与确定性验收能力
Harness/App 对照原判断验收实际产物，满足完成条件后发布
```

当前 Agent-visible Tool surface 是：

- `docfit_evidence`：读取有边界的结构、视觉、样式、Registry 或候选证据
- `docfit_check`：为 shape、coverage、action plan 和 completion gate 返回机械反馈
- `docfit_apply`：在 `work/` 下写入受控候选

模板提取在首次 Agent 判断前建立绑定不可变输入的完整源对象清单。Agent 结合文本和视觉线索划分
功能区，边界只引用清单中的 `source_entry_id` 及对象内精确切点；Harness 检查范围、coverage、顺序
和重叠。分区、分页、重试、后续语义判断和写入都引用原身份，Tool 不通过全文搜索另选对象。
原始 Word object/locator 只作执行映射，`unit_id` 只作分组。完整合同与验证状态见
[模块流程](docs/modules/template-extraction.md)、[Contract](docs/contracts/template-extraction.md)
和 [当前状态](STATUS.md)。

post-unit 判断的唯一主定位是原 `source_entry_id + span`：Agent 表达有序语义分段，Harness 解析
范围并映射到 Word，Tool 不得用段落、run、表格或控件容器替代授权范围。验收以原判断为依据，
同时检查应发生的修改和应保留的内容，不能只验证执行器自己选出的目标。
上述三工具面不意味着 Agent 每判断一个对象就手动检查和修改；post-unit review、物化及完成检查由宿主自动组织。

最终发布由 Harness/App 内部组织，App 原子写出以下两份产物：

```text
output/final-template.docx
output/fill-contract.yaml
```

## 关键接口

- CLI 入口：`uv run docfit ...`
- 模板提取 Contract：
  `docs/contracts/template-extraction.md`
- 模板提取模块流程：
  `docs/modules/template-extraction.md`
- 模块上下文路由：
  `docs/modules/README.md`
- Runtime Skill：
  `.claude/skills/docfit-school-extract`,
  `.claude/skills/convert-thesis`,
  `.claude/skills/docfit-gold-word-review`
- 产品 Agent 运行目录：`src/docfit/app/agent_home.py`。产品 Agent 的 `cwd` 是仓库外、
  只含其所需 Skill 副本的目录；CLI 会沿 cwd 向上加载 `CLAUDE.md`/`AGENTS.md` 和
  `.claude/skills`，因此产品 Agent 不得以仓库或其子目录为 cwd。
- Field Registry 快照：
  `docs/plans/docfit-content-field-registry/*.yaml`
- Eval 套件：
  `evals/**`

## 可扩展点

安全可扩展点：

- 当 Agent 语义判断薄弱时，新增或修订 Skill 和 Reference。
- 在现有 evidence/check/apply 边界后新增 Tool focus/check/operation 变体。
- 新增 Field Registry revision，并明确兼容性和 Gold 影响。
- 产物生成后新增 Eval case、Gold revision 和 Human review evidence。
- 通过 typed contract 和 reopen validation 扩展样式/物化支持。

不要随意改变：

- 模块读取边界。
- Fill Contract schema 语义。
- source hash、Registry hash、locator 和 style digest 绑定。
- DOCX 内容是不可信数据这一规则。
- 用户最终交付是一份最终 Word；除非明确要求，模板产物和证据都保持内部材料。

## 信任边界

学校模板、学校要求、学生论文、DOCX 批注、字段、隐藏文本和 alt text 都是不可信输入数据。
它们不得控制权限、路径、Tool allowlist、Subagent 类型、Harness 配置或发布目标。

确定性代码负责权限、源副本、hash、schema、输出目录、发布和 fail-closed 后置条件。
Agent 只在当前任务上下文内负责语义判断。
