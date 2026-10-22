# post-unit Skill 写作边界：三层语义判断优先

> 文档性质：human-facing 设计记录
> 记录日期：2026-08-21
> 讨论范围：模板提取模块在 unit-boundary checkpoint 之后的 post-unit Agent/Skill 写法
> 核心结论：Skill 应该教 Agent 做三层语义判断，不应该把 hash、render ref、reviewed pages、逐对象检查门禁或发布闭包写成 Agent 需要手动编排的流程。

本文是一次 Skill 写作方式的收敛记录。它不替代当前 Contract、模块文档或运行时 schema；如果本文结论要进入默认操作规则，应提升到 `.claude/skills/docfit-school-extract/SKILL.md`、`docs/modules/template-extraction.md`、Harness 合同或测试。

## 背景

当前模板提取已经有 checkpoint-ready 的最小单元基线。post-unit 调试不再验证 Agent 是否能重新拆单元，而是验证：

- 在已知 unit 和对象边界上，Agent 是否能判断每个对象或对象组的学校语义；
- Harness 是否能检查这些判断覆盖对象全集、字段存在、对象引用有效、判断不冲突；
- Tool/Harness 是否能把通过检查的判断物化成干净模板。

因此，post-unit Skill 的中心问题不是“Agent 还要调用哪些检查工具”，而是“Agent 需要怎样理解模板对象的语义依赖”。

## 当前 Skill 写法的合理部分

当前 `.claude/skills/docfit-school-extract/SKILL.md` 已经有几个正确方向：

- 明确 Agent 负责学校语义判断，运行环境负责路径、权限、hash、工具执行、结构化反馈和发布；
- 明确 post-unit 不要求每判断一个对象就手动调用检查 Tool，而是在阶段完成时返回 `semantic_judgments` 给 Harness 自动 review；
- 已经写出一个重要依赖：先判断责任，再绑定 Registry；先确认可填写接口或正文 member，再确认样式代表；
- Reference 拆分方向是对的：主 Skill 写流程和触发点，复杂案例放 Reference。

这些内容应该保留，但表达需要继续收束。

## 当前 Skill 写法仍不合理的地方

### 1. 判断框架过宽

当前 Skill 使用“七问判定壳”描述 Agent 每个范围要回答的内容。它比旧的多门槛写法更清楚，但仍然把几类不同层次的问题并列给 Agent：

- 语义问题：对象承担什么责任；
- 绑定问题：是否需要 Registry field；
- 转换问题：是否需要物化 slot、body structure、生成刷新；
- 证据账本问题：snapshot、render、evidence refs；
- 完成问题：是否还有 completion 缺口。

这些问题并不是同一层级。Agent 的主任务应该是语义判断；证据账本、阶段闭包和完成门禁应由 Harness/session/App 负责。Skill 可以提醒“证据不足要说明”，但不应该把 render、hash、completion 等机械概念放到语义判断框架的中心。

### 2. post-unit 和最终视觉复核混在同一条主轴

当前 Skill 的工作主轴从建立视野、切分单元、判定责任，一直写到最终复核；完成口径里也写了最终 render、visual evidence 覆盖、`candidate_render_ref`、`reviewed_pages`。

这容易让 Agent 在 post-unit 阶段提前关注后阶段发布验证，出现类似：

- 没完成语义判断覆盖前，就开始考虑 render/ref/page；
- 把 `render_snapshot`、`visual_page`、`reviewed_pages` 理解成当前语义判断必须手动闭合的任务；
- 因为缺视觉证据而返回 `needs_input`，但真正缺的是 post-unit 语义判断包能否被 Harness 接受。

更合理的边界是：post-unit Skill 核心只讲对象语义判断。视觉复核属于候选模板生成后的 Harness/App 阶段，最多作为完成阶段 Reference，不应成为 post-unit 主流程的一部分。

### 3. Tool 名称容易被写成流程义务

当前 Skill 的 Tool 表已经强调 Tool 是意图，不是语义裁决。但只要主流程频繁出现 `docfit_check`、`docfit_apply`、`render_snapshot`、`visual_page`，Agent 仍可能把它们当成必须按顺序手动调用的脚手架。

post-unit 的 Tool 说明应该更克制：

- `docfit_evidence`：用于缺证据时获取局部事实；
- Registry evidence：只在判断为字段槽或正文 member 后需要；
- style evidence：只在已确认最终承载对象会产生样式义务时需要；
- phase review、coverage、apply、render、completion gate：由 Harness/session/App 编排，不是 Agent 的常规手动步骤。

### 4. hash、render ref、reviewed pages 仍然污染 Agent 任务

Agent 不应该承担机械记账。`source_hash`、`candidate_hash`、`render_ref`、`reviewed_pages` 这些概念的正确归属是：

- Harness/session 绑定当前 source、candidate 和 checkpoint；
- Tool 内部检查 stale ref、当前候选、render 绑定；
- App 发布门禁检查最终产物证据。

Skill 可以说“使用当前 evidence packet，不要猜测对象或字段”，但不应该要求 Agent 确认或记忆多个 hash/ref。否则失败会表现为 Agent 参数传错，但根因是接口让 Agent 承担了非语义任务。

## 建议的 post-unit Skill 核心模型

post-unit Skill 应该围绕三层依赖写，而不是围绕多门槛或工具调用序列写。

```text
accepted unit + unit_evidence_packet
        |
        v
第一层：对象语义角色
        |
        v
第二层：干净模板处理方式
        |
        v
第三层：按需补充 Registry / style / object evidence
        |
        v
semantic_judgments
        |
        v
Harness phase review
```

### 第一层：对象语义角色

Agent 首先判断当前对象或对象组是什么。典型角色包括：

- 学校固定内容：最终模板应保留的学校名称、标题、表单标签、固定说明；
- 填写槽：后续应由学生内容、任务输入或人工填写的字段位置；
- 正文代表结构：正文标题层级、摘要、关键词、题注、参考文献等结构代表；
- 示例值或占位提示：`×××`、`20××年××月`、示例姓名、示例编号；
- 模板作者说明：字体、字号、行距、删除/选择提示、操作说明；
- 样式说明：只描述外观的括号注释或邻近说明；
- 布局对象：空段落、分页、分节、表格外壳、图片锚点；
- 条件/人工区：评审模式、签名、成绩表、任务书等依赖人工或任务条件的内容；
- 未解决对象：当前证据不足以确定语义的范围。

这一层只回答“它是什么”。如果答案是固定内容或纯删除说明，通常不需要继续查 Registry。

### 第二层：干净模板处理方式

在语义角色确定之后，Agent 才判断干净模板应该怎么处理：

- 保留固定内容；
- 删除模板作者说明、纯格式说明或冗余空段；
- 从同一段中剥离格式注释，但保留真实内容；
- 把填写槽绑定为 Registry field；
- 把正文代表绑定为 body member 或生成机制；
- 保留示例值作为 slot hint，或删除示例值；
- 保留人工/条件区并标明条件；
- 对证据不足的范围输出 unresolved / needs_input。

这一层仍然是语义输出，不是 Tool operation schema。Agent 不应该在 Skill 层学习 `docfit_apply` 的具体 operation 枚举、参数结构或每步检查方式。

### 第三层：按需补充依赖证据

第三层不是每个对象都要走。它只在前两层判断触发依赖时发生：

- 判断为填写槽或正文 member：需要 Registry 候选或具体 field evidence；
- 判断为最终承载对象会产生样式义务：需要 style evidence；
- 对象边界不清：需要 object detail、局部上下文或 target affordance；
- 生成内容或目录来源不清：需要 generated context；
- 删除可能影响唯一规则、唯一样式证据、唯一填写位置、表格/图片/section 边界：需要局部安全证据。

如果对象只是普通固定内容，Agent 说清楚保留即可。不要为了“完整”强迫它查询 Registry、style 或 visual evidence。

## Skill 应该写到什么层次

主 `SKILL.md` 应该写到以下层次：

- 当前阶段的 Agent 责任是什么；
- Agent 能看到什么输入：accepted unit、unit evidence packet、可见文本、对象引用、必要的 Registry/style evidence；
- Agent 输出什么：覆盖当前对象 universe 的 `semantic_judgments`；
- 三层判断依赖：角色判断、处理方式、按需证据；
- 什么时候读哪个 Reference；
- Tool 的意图，而不是参数编排；
- Harness feedback 返回后，Agent 应如何重判 affected scopes。

主 `SKILL.md` 不应该写到以下层次：

- hash、candidate、render ref、cursor、reviewed pages 的生命周期；
- 每个 Tool 的完整参数 schema；
- `docfit_apply` operation 枚举和 action payload；
- 每个对象判断后的手动检查门禁；
- completion gate、publish ledger、output hash 绑定；
- 一次 smoke run 里出现过的失败码或 workaround；
- 把 Harness 可以自动检查的 coverage、overlap、stale ref 写成 Agent 要自己判断的步骤。

Reference 可以展开领域例子，例如封面槽位、正文标题、目录、题注、说明文字、条件页、人工表单。Reference 也不应该变成 Tool schema 手册。

## Harness feedback 应该给 Agent 什么

如果 Harness 在阶段 review 发现问题，它应该返回可修复的语义上下文，而不是下一步工具脚本。最小有用反馈包括：

- affected unit、object 或 locator range；
- 原 judgment 摘要和冲突 judgment 摘要；
- 问题类型：missing coverage、unknown object、overlap、field not registered、style obligation missing、delete safety risk；
- 相关可见文本、邻近对象和 evidence ref；
- Registry 候选或缺失原因；
- 需要重判的目标，例如“这个范围必须归入某个 judgment”或“这个 slot 需要绑定已存在字段”。

Agent 收到 feedback 后应回到三层判断模型重判 affected scopes，而不是手动追加新的检查门禁。

## 建议改写方向

后续改 `.claude/skills/docfit-school-extract/SKILL.md` 时，可以按这个结构收敛：

1. 保留顶部职责边界：Agent 只做学校语义判断，Harness/session/Tool/App 负责机械账本和执行。
2. 把“七问判定壳”改成“三层语义判断”。
3. 把 post-unit 作为主流程中心：`unit_evidence_packet -> semantic_judgments -> Harness phase review`。
4. 把 unit-boundary 和最终视觉复核降级为独立阶段说明或 Reference，不要压在 post-unit 主流程里。
5. Tool 表只保留意图和触发条件，不复述 Tool schema，不把 `docfit_check` 写成常规每对象门禁。
6. 从主 Skill 中移除或弱化 `render_ref`、`reviewed_pages`、completion gate 等后阶段机械字段。
7. 用封面最小单元作为第一个 Reference 示例：固定内容、填写槽、示例值、格式说明、样式义务和 Registry 绑定如何按三层依赖判断。

## 一句话原则

post-unit Skill 的好坏，不取决于它列了多少门槛或工具步骤，而取决于它是否让 Agent 稳定回答：

```text
这个对象是什么？
干净模板里应该怎么处理？
只有在需要时，它依赖哪个 Registry 字段或样式代表？
```

剩下的覆盖、hash、stale ref、apply、render、reviewed pages 和发布闭包，都应该回到 Harness/session/Tool/App。
