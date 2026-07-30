# DocFit 测试与迭代（02）v1.0

> 状态：最小 Eval 设计
> 日期：2026-07-30
> 前提：Eval 是开发系统，不进入正常论文转换的运行路径。

## 1. 目标

Eval 只解决两个问题：

1. 当前 Skill、Knowledge 和 Tools 的组合，能否完成代表性论文转换；
2. 一次修改是否修复了目标问题，同时没有破坏已知正确行为。

DocFit 不建设通用评测平台。测试发现、并发、报告和 CI 优先使用现成测试框架；DocFit 只维护论文领域的样本与断言。

## 2. 三层测试

### 2.1 Tool tests

确定性工具用普通单元测试和契约测试覆盖：

- DOCX 能否正确打开与另存；
- 段落、表格、图片、公式、页眉页脚等对象能否被发现；
- 修改是否只影响目标对象；
- 源文件是否保持不变；
- 修改后文件能否重新读取；
- 占位符、字体、渲染和结构检查是否返回明确结果；
- 工具遇到不支持或歧义对象时是否安全失败。

Tool test 追求确定性，不调用 Agent。

### 2.2 Skill eval

Skill eval 使用固定任务、输入文件和 Knowledge，观察 Agent 是否：

- 触发正确 Skill；
- 在修改前读取目标学校 Knowledge；
- 使用 Tool 而不是直接猜测文档结果；
- 遇到关键信息不足时提出清楚的问题；
- 保留学生内容；
- 对工具错误做合理恢复；
- 在最终答复中如实说明未解决问题。

Skill eval 以结果为主。除安全底线和必要先后关系外，不要求 Agent 复现固定工具调用序列。

允许的行为断言只有：

```text
must       必须发生，例如读取学校 Knowledge
must_not   禁止发生，例如覆盖源文件
before     必要先后，例如修改前先检查输入
limit      成本或重复调用上限
```

不要保存或比较模型隐藏思维链。

### 2.3 End-to-end eval

端到端用例从用户任务开始，验证最终产物：

- `final.docx` 存在且可打开；
- 关键学生内容仍存在；
- 目标学校的关键格式断言满足；
- 必填模板内容或槽位已处理；
- 不应出现的占位符和说明文字已清理；
- PDF 或页面预览可生成；
- validation 没有被忽略的严重错误；
- Agent 的最终回复与实际产物一致。

端到端 Eval 不要求在线产品生成 delivery state、Verifier verdict 或 Run Bundle。

## 3. Eval case

一个用例保持小而自包含：

```yaml
id: hunannongye-basic-001
task: 将学生论文转换为湖南农业大学格式
inputs:
  document: input/student.docx
  school_knowledge: hunannongye/v1
assertions:
  - final_docx_opens
  - source_file_unchanged
  - required_text_preserved
  - no_template_instruction_text
  - required_styles_match
manual_review:
  - cover_page
  - toc_pagination
```

用例可以附带：

- 输入文件；
- Knowledge 版本；
- 结构化期望；
- 少量人工确认的参考产物；
- 失败说明。

不需要阶段 Gold、输入胶囊、运行时指纹或 replay 协议。

## 4. 样本组合

第一阶段只维护能够推动实现的最小集合：

- 1 个可公开的正常学生样本；
- 1 个真实结构复杂样本；
- 3–5 个由真实失败提炼的对抗样本；
- 1 个目标学校 Knowledge 包。

优先覆盖：

- 删除一段并重复另一段；
- 表格内图片或公式；
- 模板说明文字跨多个 Word run；
- 目录被误当正文；
- 缺失必要字段；
- 字体缺失或渲染失败；
- 学校要求与模板表现冲突。

第二所学校加入后，增加跨学校回归，用来发现通用 Skill 是否混入首校知识。

## 5. 结果比较

按数据类型选择最简单的比较方式：

| 类型 | 比较方式 |
|---|---|
| 原始输入、Knowledge 文件 | hash 或 exact |
| 结构化分析结果 | 忽略时间戳后的 normalized compare |
| 对象集合 | set compare |
| 字号、页边距、坐标 | tolerance |
| Agent 判断与最终论文 | 关键事实断言 |
| 页面视觉 | 人工复核，必要时加图像差异辅助 |

避免整份 DOCX 逐字节比较，也避免把一条完整 Agent 路径当成 Gold。

## 6. 失败归因

失败后只定位到可行动的资产：

| 归因 | 典型问题 | 修复位置 |
|---|---|---|
| Skill | 领域判断或工具使用指引错误/缺失 | `skills/` |
| Knowledge | 学校事实、模板或示例错误 | `knowledge/` |
| Tool | 解析、修改、渲染或检查实现错误 | `tools/` |
| Eval | 断言错误、样本失效或漏测 | `evals/` |
| App/SDK integration | 输入、权限、路径或 SDK 配置错误 | `app/` |

一次失败可以涉及多个问题，但修复时应分别落到对应资产。不要用新的工作流层来吸收定位困难。

## 7. 迭代闭环

```text
真实任务或 Eval 失败
  → 保存最小复现
  → 判断属于 Skill / Knowledge / Tool / Eval / App
  → 修复对应资产
  → 为该问题增加断言
  → 运行相关用例和核心回归
  → 合入
```

每个重要修复至少留下一项自动化资产：

- Tool bug：单元或契约测试；
- Skill bug：Skill eval；
- Knowledge bug：学校用例；
- 端到端漏检：结果断言或人工复核清单。

## 8. 发布门槛

早期版本只设四个门槛：

1. Tool tests 通过；
2. 核心 Skill eval 通过；
3. 当前学校端到端样本通过；
4. 人工打开最终 DOCX 和关键页面确认可接受。

基线尚小时，逐例看失败比建立统计平台更有价值。等用例数量和运行成本真实增长后，再选择并发 runner、实验平台或 trace UI。

## 9. 最小指标

每轮只记录：

- 端到端用例通过数 / 总数；
- 严重内容丢失或结构破坏次数；
- 需要人工澄清的任务比例；
- 平均每个任务的工具调用数和耗时；
- 按 Skill / Knowledge / Tool / Eval / App 的失败分布。

指标用于发现趋势，不成为新的运行时状态体系。
