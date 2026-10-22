# DocFit 核心架构

状态: 当前产品架构
更新日期: 2026-09-28

DocFit 是一个 Claude Agent SDK-native 的论文格式处理应用。SDK 提供 Agent loop、会话、
Tool 调用、Subagent、权限、上下文和恢复能力；DocFit 只拥有论文领域合同、确定性文档能力、
Eval/Gold 和薄应用壳。

DocFit 不建设第二套 Agent runtime，不把语义判断外包给应用状态机，也不把历史工具数量、
阶段路线或某次执行计划写成永久架构。

## 产品模块

| 模块 | 输入 | 输出 | 不负责 |
| --- | --- | --- | --- |
| 模板提取 | 学校模板、可选学校要求、Field Registry | `final-template.docx`、`fill-contract.yaml` | 学生论文、最终内容 placement、最终论文生成 |
| 用户内容提取 | 学生原始论文、Field Registry | Student Content Model | 学校模板、目标位置、目标样式 |
| final word 生成 | 模板提取产物、学生内容模型、任务补充信息 | 一份最终 Word | 重新识别学校要求或学生内容 |

这三个模块并列。任何模块改变对外合同，必须同步更新对应 Contract、Eval/Gold 和 active status。

## Agent-native 原则

语义判断由 Agent 在当前任务上下文中完成；确定性代码负责忠实执行判断并验证客观不变量：

- 输入复制、只读边界和 hash 绑定；
- 路径、权限、schema、snapshot 和输出目录；
- DOCX package、locator、Registry、style contract 和 render evidence；
- 按已接受的源范围完成 DOCX 修改，并对照原判断验证实际效果和保留内容；
- fail-closed 发布和原子交付。

失败时先沿事实、判断、映射、执行和验收定位原因；确认领域指引不足后再修 Skill/Reference。
执行能力不足由工程层补齐，不要求 Agent 改变正确判断。拦截错误产物是保护措施，不代表合法任务
完成。开发依据与证据推进顺序统一见 [架构入口](../ARCHITECTURE.md#开发判断依据)。

## 模板提取形态

模板提取的当前边界、完整流程、单元阶段、post-unit 和阶段恢复由
[contracts/template-extraction.md](contracts/template-extraction.md) 和
[modules/template-extraction.md](modules/template-extraction.md) 定义。长期 visual-first 决策见
[adr/0001-template-unit-boundary-visual-first.md](adr/0001-template-unit-boundary-visual-first.md)。
旧 redesign plan/status 已迁移到当前合同、模块文档、ADR 和测试入口；不要作为 Agent 默认启动上下文。

职责拆分：

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| Skill / References | 教 Agent 如何判断学校模板语义、何时取证、何时委派 | Harness 协议、固定工具顺序、运行状态字段 |
| Agent | 形成学校语义判断、修复反馈、选择证据和必要委派 | 文件发布、权限、hash、路径和最终产物边界 |
| Harness | 任务上下文、Tool 执行、schema/覆盖/权限/发布校验、结构化反馈 | 替 Agent 判断学校语义 |
| Tools | `docfit_evidence`、`docfit_check`、`docfit_apply` 及其确定性 provider | 第二个 Agent loop、学校语义判断、长期状态机 |
| Application | CLI/API、输入输出、恢复、发布、合同测试 | 领域语义判断和自定义 Agent runtime |

当前 Agent-visible Tool surface 是 `docfit_evidence`、`docfit_check` 和 `docfit_apply`；
最终发布由 Harness/App 内部组织，App 原子写出产物。当前文档不得把某个历史数量、wrapper 形态或 action 拆分方式当成
永久架构事实。

## 信任边界

- 学校模板、学校要求、学生论文和任何 DOCX 文本都是不可信数据；
- 不可信文本不能控制权限、路径、Tool allowlist、Subagent 类型、Harness 配置或发布目标；
- 模板提取不读取学生论文或 Student Content Model；
- 用户内容提取不读取学校模板、Fill Contract 或最终生成结果；
- Eval/Gold 只在运行后作为离线 oracle，不能进入被测 Agent prompt；
- 用户最终只收到一份最终 Word，模板产物和中间证据是内部交付/审计材料。

## 证据规则

产品状态由测试、Eval、Human review 和 active status 共同表达。自然语言计划只能提出目标；
不能替代可执行证据，也不能覆盖 Contract。
