# DocFit 模块化文档管理模板

状态: 当前文档管理规则
范围: 后续所有 DocFit 文档变更
更新日期: 2026-08-18

本文是 DocFit 后续文档整理、创建和评审的默认模板。目标不是写更多实现说明，而是让文档保持
稳定、分层、可维护，并避免 Agent 启动时被长历史文档污染上下文。

核心原则：

> 文档约束方向和边界，评测和测试约束行为，代码表达实现。

## 1. 默认规则

后续所有文档变更先判断文档层级，再决定写入位置。不要把产品目标、模块责任、实现流水账、
性能诊断、测试结果和临时状态混在同一份文档里。

每次新增或更新文档前，先回答：

1. 这段内容是在约束产品目标、模块边界、交接合同，还是在复述当前实现？
2. 如果实现重构但外部行为不变，这段文档是否仍然应该保持不变？
3. 这段内容能否由测试、Eval 或 case inventory 更准确地表达？
4. 这段内容是否混入了其他模块的责任？
5. 这段内容是否包含真实学生正文、私有样本细节或不该公开的路径？
6. 这段内容是否会让未来 Agent 把历史方案误认为当前必须遵守的架构？
7. 下游模块真正需要知道的是实现细节，还是稳定输出合同？

判断规则：

- 实现重构后也必须保持的行为，写入 Contract、Handoff Contract 或 ADR。
- 只有当前代码这样做的细节，留在代码、测试或必要注释中。
- 只说明现在进展如何的内容，写入短状态。
- 用来判断通过失败的内容，写入 Eval、测试或 CI/case inventory。
- 其他模块不应该依赖的内容，不写入跨模块文档。

### AGENTS.md 链接新鲜度门

`AGENTS.md` 和 `CLAUDE.md` 是启动指针，不是文档索引。它们引用的每一份仓库文档都会成为
Agent 的高优先级上下文入口，因此修改根 Agent 文件时必须同步治理被引用文档。

任何新增、保留或移动 `AGENTS.md` / `CLAUDE.md` 中的仓库文档链接，都必须在同一次变更中完成：

1. 列出根 Agent 文件中保留的所有仓库内文档链接；
2. 检查每个目标是否仍是当前层级的真相，或是否已经明确标记为 evidence/history/superseded；
3. 若目标文档内容过期、与代码或当前 Contract 冲突、或继续指向已取代计划，先更新目标文档；
4. 若目标只是历史计划、调试记录、讨论稿或临时状态，不要从根 Agent 文件直接链接；
5. 若必须链接状态文件，状态文件必须短，并包含当前 proof、pending/blocker 和上次刷新日期；
6. 修改完成后用 `rg` 检查旧路径、旧状态词和被移除的 current-truth 链接没有继续作为当前入口出现。

默认策略：根 Agent 文件只指向 `README.md`、`ARCHITECTURE.md`、`STATUS.md`、必要的当前
Contract/模块边界和任务 Skill。计划、active status 记录、human discussion、bug、temp evidence 只能
作为按需证据入口，不能成为默认启动阅读链路。

三模块并行推进时，必须先选择当前模块，再加载该模块自己的 Contract、状态、Skill 和 Eval。
不要为了模板提取任务读取用户内容提取 Gold，也不要为了用户内容提取任务读取学校模板或 Fill
Contract。跨模块工作也只能通过稳定交接产物连接，而不是共享私有运行上下文。

## 2. 文档层级

### README.md

用途：只回答三件事：这个项目是什么、怎么跑、当前主要入口在哪里。

应该写：

- 一句话项目定义；
- 当前最小安装和验证命令；
- 主要 CLI 示例；
- 当前状态、架构、Agent 规则、合同和计划索引入口。

不应该写：

- 开发历史；
- 长计划；
- 复杂架构；
- 实现流水账；
- 人类讨论结论全文。

### ARCHITECTURE.md

用途：写系统结构，不写函数细节。

应该写：

- 模块边界；
- 数据流；
- 关键接口和交接产物；
- 可扩展点；
- 不能乱动的边界和信任模型。

不应该写：

- 函数名、类名和行号；
- 某次任务的执行步骤；
- 某个历史方案的完整论证；
- 仅由测试或代码表达更准确的实现细节。

### STATUS.md

用途：写当前状态，让下一次 AI 进入项目时知道项目在哪。

应该写：

- 现在能用什么；
- 正在做什么；
- 已知问题；
- 下一步；
- 必要的详细证据入口。

不应该写：

- 长 proof 日志；
- 完整计划；
- 历史失败复盘；
- 会被 `docs/status/active/**` 或 Eval 更准确表达的细节。

### AGENTS.md / CLAUDE.md / Cursor Rules

用途：写给 AI 的操作规则。

应该写：

- 优先读哪些短入口；
- 优先用什么命令；
- 哪些目录或输入不要改；
- 测试怎么跑；
- 代码和数据边界；
- 提交前检查；
- 遇到不确定时怎么处理。

不应该写：

- 产品需求；
- 项目路线图；
- 长篇背景；
- 人类讨论稿；
- 详细执行计划。

### 全局产品架构补充

用途：让人和 Agent 理解 DocFit 的产品模块、责任边界和共同原则。

应该写：

- 三个模块是什么；
- 每个模块负责什么、不负责什么；
- 用户最终只收到一份 Word；
- 学校模板是最终 Word 主干，学生论文是只读内容来源；
- 不能静默丢失学生内容；
- 模块之间只通过稳定产物交接。

不应该写：

- 某个模块内部怎么分 batch；
- Agent prompt 的具体措辞；
- checkpoint hash 细节；
- 某次真实运行的完整性能拆解；
- 某个历史调试分支的失败过程。

### 模块 Contract

用途：定义一个模块的黑盒边界。Contract 是调用方、下游模块、测试和 PR 审查共同依赖的稳定协议。

每个模块 Contract 应保留：

- allowed inputs；
- forbidden inputs / forbidden reads；
- required outputs；
- 状态语义；
- 隐私边界；
- CLI 或 API 成功/失败语义；
- 下游可以依赖什么；
- 验收门引用哪些 Eval 或测试。

Contract 不应保留：

- 当前并发数、batch size、retry 次数；
- prompt 长文本；
- checkpoint 内部 identity 字段；
- 某个函数名或实现文件细节；
- 某次历史运行耗时。

### 交接 Contract

用途：定义模块之间的交接物，而不是模块内部实现。

至少明确：

- 模板生成 -> 最终内容填写：`final-template.docx`、Fill Contract、样式合同、目标 slot/region；
- 用户内容提取 -> 最终内容填写：Student Content Model、`items` 顺序、内容身份、字段语义和源追溯；
- 共享语义：Content Field Registry 的 identity/hash/version。

交接 Contract 的重点是“下游能相信什么”。例如：

- `items` 是学生内容顺序真相；
- `field_results` 是派生索引，不能作为顺序来源；
- 模板生成不读取学生论文；
- 用户内容提取不读取学校模板；
- 最终内容填写不能重新识别学生标题、正文、图题、表题和公式。

### Eval / CI case 清单

用途：让评测成为机器可执行的行为真相。

它应该回答：

- CI 或本地回归跑哪些 case；
- 每个 case 使用哪个 source、Registry、Gold revision；
- 运行哪个命令或 test target；
- 预期结果是什么；
- 是 hard gate、trend only，还是暂时跳过；
- 是否包含真实受限学生内容；
- 公开 CI 和受限本地 CI 分别跑什么。

推荐形态是 YAML/JSON 加一份短 README。自然语言状态文档不承担 case inventory 的职责。

### 当前状态

用途：记录当前真实状态和证据入口。状态可以变，但必须短。

应该写：

- 当前状态；
- 最新已接受 proof；
- 当前 blocker；
- 下一步 proof；
- 证据路径；
- 哪些失败不属于本模块。

不应该写：

- 长篇实现设计；
- 完整调试日志；
- 已被当前实现取代的历史方案；
- 可以由测试表达的内部行为。

推荐格式：

```text
状态: <当前状态>
Proof: <最新 accepted proof>
Pending: <下一项 proof 或 blocker>
Not this module: <非本模块 failure>
```

### ADR / 决策记录

用途：记录长期架构决策。只有未来不能随便推翻的决定才写 ADR。

适合写 ADR 的内容：

- 三模块并列，不互相调用；
- Registry 是语义词典，不保存学生内容，也不决定目标位置；
- Gold 不能进入 Agent prompt，只能在提取后离线比较；
- 最终内容填写负责样式选择和物化，而不是用户内容提取或模板生成提前承担。

不适合写 ADR 的内容：

- 当前函数怎么实现；
- 某个临时性能优化；
- 某个模型的具体错误；
- 某次失败运行的完整细节。

## 3. 模块责任摘要

### 模板提取

负责：

- 输入学校模板、可选学校要求和 Field Registry；
- 忠实保留学校模板结构；
- 识别学校提供的槽位、固定内容、规则、样式事实和缺口；
- 输出最终内容填写可消费的 `final-template.docx` 和 Fill Contract；
- 不读取学生论文；
- 不注入本次学生内容；
- 不提前选择最终填写的通用兜底样式。

### 用户内容提取

负责：

- 输入学生原始论文和 Field Registry；
- 输出忠实、无损、有序、可追溯的 Student Content Model；
- 不读取学校模板、学校要求、Fill Contract 或最终生成结果；
- 不决定目标位置和目标样式；
- 不修改、归一化、补写或重排学生正文。

### final word 生成

负责：

- 消费模板提取和学生内容提取两个模块的输出；
- 选择并物化学校样式或通用兜底样式；
- 按稳定 handoff 进行内容放置和机械复制；
- 处理必填缺失、非必填不适用、目录、分页、对象运输和最终质量验收；
- 输出唯一最终 Word；
- 不重新识别学校要求；
- 不重新识别学生内容。

## 4. 放置规则

默认放置位置：

- 项目入口：`README.md`；
- 全局产品架构：`ARCHITECTURE.md`，更详细补充可放 `docs/docfit-01-architecture-core.md`；
- 当前状态：`STATUS.md`，长 proof 和胶囊状态放 `docs/status/active/**`；
- Agent 操作规则：`AGENTS.md` / `CLAUDE.md` / Cursor Rules；
- 模块 Contract：`docs/contracts/<module>.md`；
- Handoff Contract：`docs/contracts/` 中独立文件，或由相关模块 Contract 明确引用；
- Eval 入口：对应 `evals/**/README.md` 和 case inventory；
- 任务计划：`docs/plans/<task>.md`，包含目标、非目标、涉及文件、实现步骤、验收标准、测试方法和风险；
- 重要决策：`docs/adr/<decision>.md`，只记录背景、决策、备选方案、后果和重看条件；
- 未来 AI 经验：`memory/**`，短、准、有日期，不写流水账；
- 模块上下文路由：`docs/modules/README.md`，说明三条并行模块线各自应加载的 Contract、状态、Skill 和 Eval；
- 历史计划和执行证据：`docs/plans/**`、`docs/status/active/**`、`temp/**` 或其他明确过程目录；
- 面向人类的用户说明、评审包和背景讨论：`docs/human/**`，必须通过 `docs/human/README.md` 索引，不作为默认 Agent 上下文。

`AGENTS.md` 不应指向长 human 文档作为默认阅读材料。需要规则时，把短操作规则写进
`AGENTS.md`；需要背景时，再按任务读取 `docs/human/README.md` 中的具体条目。

## 5. 清理规则

当发现历史长文档与当前实现冲突时：

- 仍有长期架构价值：提炼成 Contract、Handoff Contract 或 ADR；
- 只是一次性诊断证据：归档为 evidence/status，或保留在计划历史中；
- 已被测试覆盖：删除自然语言实现描述，保留测试；
- 会误导后续 Agent：从当前人类入口移走或明确标记为 superseded，并提供当前入口链接。

完成后的理想状态：

- 新 Agent 先读 `README.md`、`STATUS.md`、`ARCHITECTURE.md` 和 `AGENTS.md`；
- 负责某模块的 Agent 读本模块 Contract，知道自己能改什么、不能改什么；
- 集成 Agent 读 Handoff Contract，知道模块之间如何交接；
- CI/Eval 决定行为是否达标；
- 代码和测试表达具体实现。
