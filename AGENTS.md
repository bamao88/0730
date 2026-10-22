# DocFit Agent 指南

## 首要工作原则：主动负责与系统性思考

**以下要求约束参与项目开发的 AI Agent，必须贯穿判断、实现、验证和汇报全过程。**

### 1. 主动承担结果，保持独立判断

- 对项目目标、方案可行性、实现质量和最终交付主动负责。发现遗漏、矛盾或风险时，要主动指出、
  给出依据和建议；不能用户说什么就附和什么，也不能把工程判断和验证责任交回给用户。
- 影响产品行为或验收标准的要求存在实质歧义时，必须在依赖该要求的工作开始前明确询问，说明
  不同理解的影响。目标清楚后的常规工程取舍应自主完成；不能事后把失败归咎于用户没说清楚。
- 区分已证实的事实、待验证的判断和未知项。改变结论必须说明新证据，不能随用户表态改变归因；
  完成声明必须与验证范围一致，对错误判断、遗漏和过度承诺主动纠正并负责。

### 2. 先看根因和架构职责，再处理实现细节

- 每次修改前，先确认所属产品模块、当前阶段的完成条件、责任层及上下游合同；以
  `ARCHITECTURE.md` 和对应模块文档核对职责，不能在执行中只盯当前报错而忘记整体流程。
- 先判断这是局部实现 bug，还是事实表达、合同、职责分配或能力边界的系统性问题。沿输入、判断、
  执行、检查与反馈追溯原因，并检查同类路径；系统性问题应在共同责任层修复，局部 bug 则保持
  有边界的修复，不能靠特例、额外提示词或不断叠加门禁掩盖根因，也不能无依据扩大重构。
- 同类失败反复出现、修复范围不断扩大或需要跨层修改时，必须先重新审视归因和架构，再继续实现。
  不得让 Agent、Harness、Tool 或其他模块替不属于自己的职责兜底。
- 缺陷修复应验证原始失败场景及受影响的同类场景；其他修改按实际影响选择验证方式。按下文的
  验证层级说明结果，不能以局部测试通过代替用户流程和最终产物验收。

**写入原则不等于落实。Agent 必须在每次修改和交付前自查；违反后应主动纠正并承担责任，
不能再次要求用户提醒，也不能以本文不够具体为理由推卸执行责任。**

本文是 Agent 进入仓库时的启动说明，不是项目百科、计划清单或历史索引。只写每次进场都
有用的方向；细节从下一层文档按任务加载。

## 项目心智模型

DocFit 是基于 Claude Agent SDK 的论文 Word 格式处理项目。产品把学校模板、学校要求和
学生论文转换成可验证的 Word 产物。

Claude Agent SDK 负责 Agent loop、session、Tool call、permission、Skill、Subagent、
structured output 和 lifecycle。DocFit 负责论文领域合同、DOCX 能力、hash/schema、
证据、发布和质量门；不要把 DocFit 写成第二套 Agent runtime。

本文面向开发 Agent，由其负责工程方案、实现、验证和交付；产品运行中的 Agent 按所属模块合同
承担语义判断。以下 post-unit 职责与定位规则仅适用于模板提取，不代替其他模块的职责定义。

模板提取的产品 Agent 负责学校模板语义判断；hash、checkpoint、task root、stale ref、coverage、
DOCX 物化和发布账本由 Harness/session/Tool/App 负责。给产品 Agent 搭脚手架时，先明确并核对
post-unit 交互合同，再改 prompt、Skill 或 schema；不要把临时失败暴露成新的 Agent 记账任务。

post-unit 默认输入是产品 Agent 可读的 unit reading packet：可见文本、相邻语义块、布局线索和
初始源对象引用。判断、执行和检查的唯一主定位是初始清单中的 `source_entry_id + span`；Agent
引用原 `source_entry_id` 并表达语义分段，Harness 解析对应 span 并映射到底层 Word 对象。
reading packet 的 block/range 只作阅读视图，不能另建对象身份或让执行器重新选目标。底层 Word
inspect objects、locator、object_ref、target_ref、fingerprint 和 hash 只作为 Harness/Tool 的映射与
执行账本，不作为产品 Agent 默认判断输入。

post-unit 不采用“每个对象判断后让 Agent 手动调用检查工具过门禁”的脚手架。Agent 输出对象语义判断；
Harness 在阶段完成点自动检查目标仍存在、对象引用可解析、Registry field 存在、覆盖/冲突/可执行性闭合。
检查失败先判定责任：判断缺失、冲突或表达不完整等可通过补充语义判断解决的问题，返回产品 Agent
修订；事实、映射、执行能力或环境问题由对应工程层处理，不能要求 Agent 改变正确判断来绕过工程缺陷。
发现语义结果错误时，先核查输入事实、上下文和合同表达；确认领域指引不足后再修 Skill/Reference。

禁止用代码窄规则替 Agent 或 schema 补学校语义判断。凡是依赖学校名称、模板 wording、字段 label、
正文 track 名称、Registry field 猜测、模型输出 role/treatment 文本片段才能成立的逻辑，都应先归因：
如果是语义判断缺口，补 Agent-facing schema、Registry affordance、Skill/Reference 或 reading packet；
如果是确定性物化规则，必须基于已接受的 semantic judgment 和可解释的类别规则，而不是单个 fixture 字符串。

涉及 SDK 能力设计或修复时，先查官方文档：
[overview](https://code.claude.com/docs/en/agent-sdk/overview)、
[Python reference](https://code.claude.com/docs/en/agent-sdk/python)、
[structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)。

## 三模块与耦合

DocFit 当前按三个并列模块开发：

| 模块 | 职责 | 稳定交接 |
| --- | --- | --- |
| 模板提取 | 从学校模板/要求生成可填写模板资产 | `final-template.docx`、`fill-contract.yaml` |
| 用户内容提取 | 从学生源论文生成忠实、有序、可追溯的内容模型 | Student Content Model |
| final word 生成 | 消费前两个模块输出，生成最终 Word | final Word、evidence/report |

三个模块共享 Claude Agent SDK 接入和中立 Word 事实层；不共享业务 Agent 配置、prompt、
schema、session 或私有上下文。模块职责、禁读边界和下一层入口从 `docs/modules/README.md`
继续进入。

## 默认阅读路径

1. 先读 `README.md`、`STATUS.md`、`ARCHITECTURE.md`。
2. 再读 `docs/modules/README.md`，只选择当前任务对应模块。
3. 测试或 Eval 任务读 `tests/README.md`，先区分生成测试和 Actual-vs-Gold 评分。

不要在 `AGENTS.md` 里继续展开模块内部文档；下一层文档负责继续路由。

涉及 Agent-facing prompt、Skill、schema、Tool feedback、Harness checkpoint 或 failure ownership 的修改时，
先读 `docs/agents/ai-coding-boundary-guardrails.md`，并把边界规则落到合同、lint、feedback sanitizer 或测试，
不要只改提示词。

## 失败处理

遇到复杂 bug、E2E 失败或跨层修改前，先做短归因，再改代码：

- 属于哪个产品模块？
- 当前 checkpoint 是什么，完成条件是什么？
- 责任层是 Agent、Skill、Harness、Tool、Schema、App、Test、Eval 还是 Docs？
- 哪些问题只是后续阶段的 `open_questions`，不能升级成当前 checkpoint 失败？
- 解决已证实根因的最小完整改动是什么，影响哪些同类路径，哪些验证能证明修在正确层且覆盖该类问题？

如果一次修改需要同时碰 Skill、Harness、Tool、Schema、App，先说明为什么非跨层不可。

## 汇报口径

向用户汇报时先给产品层结论，再给工程证据。优先说明当前能力站在哪个完成层级
（文档、代码、测试、runtime、Eval 或产品验收）、用户现在能依赖什么、还没完成什么、
不能宣称什么；随后再列命令、文件、proof、report 和失败归责。

调试或失败汇报不要先堆工具日志。先说明用户会看到的结果、所属模块和 checkpoint、责任层，
再说明 Tool 成功/失败、Agent 输出、Harness 反馈或环境问题。技术细节只服务于决策和下一步最小动作。

涉及 Agent + DOCX + 真实模板链路时，汇报验证结果必须明确完成层级：

- `logic/contract`：只证明代码分支、schema、异常、receipt shape 正确。
- `real replay`：使用真实 task root、真实 inventory、真实 semantic judgments 回放。
- `E2E agent loop`：运行真实 prepare-template，确认 feedback 能回到 Agent 并触发 revision。
- `product acceptance`：最终 DOCX、fill-contract、evidence/report 可用。

各层分别报告已完成、失败和尚未验证的范围。只有 `logic/contract` 证据时，不能宣称真实输入验证通过；
`real replay` 通过可报告对应真实输入回放通过，但不等于 `E2E agent loop` 通过；E2E 通过也不等于
`product acceptance`。明确尚未验证的层级，保留已完成验证的准确结论，不用“完整跑通”掩盖验证范围。

## Skill 修改纪律

Skill 是模型领域指引和阶段路由，不是 Harness、Tool、Schema 或运行时 bug 的补丁区。调试发现问题时，
先按责任层归因并修对应层；只有稳定的学校语义规则、阶段入口、Reference 路由或失败恢复口径才能进入
Skill/Reference。

不要把临时失败码、Tool schema 字段清单、operation 枚举、内部 state field、timeout 策略、trace path
或单次调试 workaround 写进 `SKILL.md`。模板提取当前边界以 `docs/modules/template-extraction.md`
为准；旧 plan、status 或 Skill 内容冲突时先当历史材料。

## Human 文档边界

`docs/human/**` 是 human-facing 的讨论、学习、复盘和评审材料，不是 Agent 默认上下文。
只有用户明确要求读取 human 材料时，才先读 `docs/human/README.md` 并选择具体文件；
不要全量读取 human 文档。

human 文档里的结论被确认后，应按性质提升到 `CONTEXT.md`、Contract、module doc、Skill、test 或 ADR；
不要让讨论稿直接变成默认操作规则。

## 提交纪律

完成一组有内聚性的代码、测试、Skill、配置或文档改动后，及时 git commit。

提交只 stage 本次相关文件；不要把已有无关源码、DOCX、临时产物或其它会话改动混进去。
提交前优先跑最小相关验证，并在最终回复说明测试结果和 commit hash。
