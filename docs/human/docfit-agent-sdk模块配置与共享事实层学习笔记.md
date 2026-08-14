# DocFit Agent SDK 模块配置与共享事实层学习笔记

> 文档定位：这是面向个人学习的解释性文档，用于理解当前 DocFit 代码中的 Agent 配置、运行实例和共享底层能力。它不是产品合同、架构决策记录或状态文档，不能覆盖 `docs/docfit-00-index.md` 至 `docs/docfit-06-development-roadmap.md` 中的正式约束。
>
> 当前代码观察时间：2026-08-12。

## 一句话结论

模板提取和用户内容提取使用的是同一套 Claude Agent SDK，也应复用同一套中立的 Word 文档事实层；但二者是两个并列的业务 Agent，应该分别拥有自己的 `ClaudeAgentOptions` 配置，而不是让用户内容提取继承完整 DocFit Agent 的配置后再逐项删减。

可以把两个核心 SDK 对象理解为：

- `ClaudeAgentOptions`：描述“这次 Agent 以什么身份、权限和环境运行”。
- `ClaudeSDKClient`：真正建立和控制一次运行会话，把上述配置交给 Claude Agent SDK 执行。

因此，这不是“两层 Agent SDK 封装”，而是“共享 SDK 基础设施之上的两个并列模块适配器”。

## 1. 当前具体需求是什么

DocFit 当前主路径只有三个产品模块：

1. 模板生成模块：识别学校提供了什么结构和样式、缺少什么结构和样式。
2. 用户内容提取模块：把学生原始论文忠实提取成有层级、有顺序、可追溯的 Student Content Model，并为内容实例绑定 Registry 中的 `field_id`。
3. 最终内容填写模块：连接学校模板与学生内容，选择和物化学校样式或通用兜底样式，对最终 Word 效果负责。

当前讨论聚焦第二个模块。它在调用 Agent 前，已经由确定性程序生成了学生文档事实和有序内容清单。Agent 的任务不是重新读取 Word、操作文件或搜索项目，而是：

1. 消费已准备好的事实 JSON；
2. 对既有内容对象做语义识别；
3. 绑定合法的 `field_id`；
4. 返回符合 JSON Schema 的 structured output。

这是一项输入和输出边界都很窄的语义识别任务。

## 2. 当前问题究竟是什么

当前用户内容提取实现位于：

```text
src/docfit/app/student_content_fill.py
```

它先调用通用的 `build_agent_options()`：

```text
src/docfit/app/agent.py
```

这个函数原本服务于能力更完整的 DocFit Agent，因此会统一装配：

- DocFit MCP Server；
- Claude Code 内置工具及 DocFit 工具；
- Subagent 定义；
- Skills；
- hooks；
- permission callback；
- `setting_sources=["project"]`；
- 项目根目录 `cwd`；
- 模型、环境变量、system prompt、structured output 等通用配置。

用户内容提取随后使用 `dataclasses.replace()` 清空 `tools`、`allowed_tools`、`agents` 和 `skills`，并禁止一组工具。但是，配置中仍保留了 MCP Server、project setting sources、hooks、permission callback 和项目根目录等通用运行时能力。

所以，问题不是 Agent 在运行过程中“调用错了某个工具”，而是程序在启动 Agent 之前就为它选择了一个过重的运行配置。

两种问题的区别是：

| 问题类型 | 发生时间 | 典型原因 | 当前是否属于此类 |
| --- | --- | --- | --- |
| Agent 错误调用工具 | Agent 已运行并做决策时 | 工具描述、Skill 指令或 system prompt 不清楚 | 不是当前核心问题 |
| 程序装配了错误能力 | Agent 启动之前 | 复用了不匹配任务边界的 options builder | 是当前问题 |

即使把 MCP 工具描述和 Skill 写得非常准确，也不能解决“本来不需要 MCP，却仍把 MCP 装进运行配置”的问题。

## 3. 模板提取 Agent 和用户内容提取 Agent 的关系

它们是同级关系，不是调用关系。

```text
                              ┌─> 模板事实视图 ─> 模板提取 Agent ─> 学校模板模型
学生或学校 Word ─> 中立事实层 ┤
                              └─> 学生内容清单 ─> 内容提取 Agent ─> Student Content Model

学校模板模型 + Student Content Model ─> 最终内容填写模块 ─> 最终论文
```

模板提取 Agent 不应调用用户内容提取 Agent，用户内容提取 Agent 也不应调用模板提取 Agent。它们不需要共享会话或互相继承 prompt。二者的结果只在最终内容填写模块汇合。

当前代码里，模板提取已经有专用的配置函数：

```text
src/docfit/app/prepare_template.py
build_prepare_template_options(...)
```

这个配置根据模板提取任务明确启用了 `Skill`、`Read`、专用 MCP、角色化 system prompt、hooks 和 structured output。它说明项目已经采用了“模块专用 Agent 配置”的模式。

用户内容提取缺少的是与它并列的专用配置，而不是模板提取 Agent 的下级配置。

推荐的形态是：

```text
build_prepare_template_options(...)       build_student_extraction_options(...)
              │                                          │
              └────────────── ClaudeAgentOptions ─────────┘
                                      │
                               ClaudeSDKClient
                                      │
                              Claude Agent SDK / CLI
                                      │
                                  Claude API
```

两个 builder 都产生 SDK 官方的 `ClaudeAgentOptions`，两个模块也都可以使用 SDK 官方的 `ClaudeSDKClient`。差别只在任务配置，不需要再造一套 Agent Runtime。

## 4. 哪些底层逻辑应该共用

模板提取和用户内容提取都从 Word 文档开始，所以确实存在大量可复用能力。但应复用的是中立事实和技术基础设施，而不是完整业务 Agent。

### 4.1 中立的 Word 文档事实层

当前共享入口是：

```text
src/docfit/tools/inspection.py
inspect_document(...)
```

它负责提取与业务判断无关的文档事实，例如：

- 段落、表格、图片和公式等对象；
- Word 样式及有效样式；
- XML/包级事实；
- 对象 ID、指纹、位置和来源；
- 后续模块需要的可追溯信息。

这类能力应该共享，因为“Word 里客观存在什么”不因模板或学生文档而改变。

在共享事实之上，各模块再生成自己的业务视图：

- 模板提取关心学校结构、槽位、样式和规则；
- 用户内容提取关心学生原始阅读顺序、父子关系、具体内容和语义字段。

当前学生侧的确定性投影位于：

```text
src/docfit/content/student.py
build_student_inventory(...)
```

它把文档事实变成保持源顺序的学生内容清单。Agent 可以标注这些既有对象，但不应重新创造内容或因为分类而重排正文。

### 4.2 SDK 接入基础设施

以下技术能力也适合共享：

- API 凭证和后端环境变量装配；
- SDK 错误映射和超时处理；
- `ResultMessage`、session ID、token、费用和耗时采集；
- structured output 的读取和确定性校验；
- 日志与 trace 的公共字段。

这些是“如何可靠调用 SDK”的问题，不决定某个业务 Agent 能做什么。

### 4.3 不应该直接共用的内容

以下内容决定模块的业务责任，应分别配置：

| 配置 | 模板提取 | 用户内容提取 |
| --- | --- | --- |
| system prompt | 学校模板结构、槽位、样式识别 | 学生内容语义识别与 `field_id` 绑定 |
| 输入视图 | 模板事实和角色任务 | 有序 Student Inventory 与 Registry |
| output schema | 模板相关结构化产物 | Student Content Model 的标注结果 |
| tools / MCP | 仅保留模板任务确实需要的能力 | 当前目标下不需要 |
| Skills | 模板提取 Skill | 当前目标下不需要 |
| hooks / permissions | 与启用工具配套 | 无工具时通常不需要 |
| `cwd` / settings | 按模板任务边界选择 | 应隔离到任务目录，不加载项目设置 |
| 会话生命周期 | 由模板工作流决定 | 由内容批次与 schema 设计决定 |

## 5. `ClaudeAgentOptions` 是什么

Anthropic 官方将 `ClaudeAgentOptions` 定义为 Claude Code 查询的配置 dataclass。它本身不执行请求，也不是一个正在运行的 Agent；它是一份启动和执行规格。

其中可以配置：

- `model`、`system_prompt` 和推理相关参数；
- `tools`、`allowed_tools`、`disallowed_tools`；
- `mcp_servers` 和 `strict_mcp_config`；
- `agents`、`skills`；
- `can_use_tool` 和 `hooks`；
- `setting_sources`、`cwd`、`env`；
- `output_format`、`max_turns` 和预算；
- session resume、sandbox 等运行属性。

因此，`ClaudeAgentOptions` 不是无害的参数集合。它共同决定：

1. 模型看得到哪些能力；
2. SDK 要初始化哪些运行组件；
3. 会加载哪些项目级上下文；
4. Agent 对文件系统和工具拥有什么权限；
5. 最终输出必须符合什么结构。

针对当前需求，专用 `build_student_extraction_options()` 应从最小能力集合正向构建，而不是从完整 Agent 配置中做减法。最低限度应包含：

- 内容提取专用 system prompt；
- 本批次对应的 JSON Schema `output_format`；
- 模型、超时/turn 上限和后端环境；
- 隔离的任务目录 `cwd`。

默认不应加载 MCP、tools、Subagents、Skills、project settings、工具 hooks 或 permission callback。将来只有在产品合同证明某项能力必要时，再显式加入。

## 6. `ClaudeSDKClient` 是什么

`ClaudeSDKClient` 是一个有生命周期的运行客户端。代码通常这样使用：

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt)
    async for message in client.receive_response():
        ...
```

它负责：

- 建立和关闭 SDK 连接；
- 向运行会话发送 query；
- 持续接收 assistant、tool 和 result 等消息；
- 在同一个 client 中保留会话上下文；
- 支持 interrupt 等会话控制。

官方文档说明，Agent SDK 会启动并管理一个 `claude` CLI 子进程，通过标准输入输出通信；一个 Agent session 对应一个子进程。CLI 子进程再通过 HTTPS 调用 Claude API。

因此真实链路是：

```text
DocFit 业务代码
   │
   ├─ ClaudeAgentOptions：定义运行规格
   │
   └─ ClaudeSDKClient：管理运行会话
            │
       claude CLI 子进程
            │
         Claude API
```

`ClaudeAgentOptions` 和 `ClaudeSDKClient` 不是二选一：前者是配置，后者是执行者。通常是把前者传给后者。

## 7. 这算不算做了两个封装层

不应设计成两个相互嵌套的 SDK 替代层：

```text
不推荐：DocFit Runtime -> Content Runtime -> Claude Agent SDK
```

推荐的是两类薄适配器：

```text
模板模块 runner ─┐
                 ├─> 共享 SDK 调用/观测基础设施 ─> Claude Agent SDK
内容模块 runner ─┘

模板 Agent profile ─┐
                    ├─> ClaudeAgentOptions
内容 Agent profile ─┘
```

- profile/builder 负责声明模块能力边界；
- runner 负责模块输入、调用顺序、结果校验和失败处理；
- 共享基础设施负责 SDK 接入、凭证、观测和公共错误；
- Agent loop、session、tool call、structured output 和 subprocess 生命周期仍由官方 SDK 管理。

这符合 DocFit 的 SDK-native first 原则：DocFit 只增加论文领域合同和必要的薄适配，不实现第二套 Agent Runtime。

## 8. structured output 在这里扮演什么角色

用户内容提取的目标不是让模型返回一段“看起来像 JSON”的文本，而是使用 SDK 原生 structured output：

1. 在 `ClaudeAgentOptions.output_format` 中提供 JSON Schema；
2. SDK 要求模型生成符合 schema 的结果；
3. 最终从 `ResultMessage.structured_output` 读取经过 schema 约束的数据；
4. DocFit 再执行领域级确定性校验，例如对象 ID 必须来自输入、不能修改源顺序、`field_id` 必须来自 Registry。

这里要区分两层校验：

- SDK schema 校验：回答“数据形状是否合法”。
- DocFit 领域校验：回答“内容是否忠实、引用是否合法、顺序是否被改变”。

第二层不能由 JSON Schema 完全代替。

## 9. 对当前性能问题意味着什么

去掉不需要的 MCP、project settings、hooks、permission callback 和项目上下文，可以减少初始化工作、上下文污染和未来维护风险，因此值得修复。

但在没有分段测量证据之前，不能把长耗时全部归因于通用 Agent 外壳。用户内容提取当前还存在批次串行执行、每批建立会话、模型生成时间和 structured output 重试等可能的耗时来源。专用 options 是架构边界修复，也是性能优化的一个组成部分，但不自动证明它是总耗时的主因。

另外，`ClaudeSDKClient` 会在同一 client 中保留会话上下文。是否让多个提取批次复用同一 client，必须结合批次 schema、上下文累积、错误隔离和质量回归做有界实验，不能仅因为“少启动一次”就直接合并会话。

## 10. 当前需求下的推荐落点

从代码结构看，清晰的目标形态是：

```text
src/docfit/tools/inspection.py
  └─ 共享：中立 Word 文档事实

src/docfit/content/student.py
  └─ 用户内容提取专用：有序 Student Inventory

src/docfit/app/prepare_template.py
  └─ build_prepare_template_options：模板提取 Agent profile

用户内容提取相关模块
  └─ build_student_extraction_options：内容提取 Agent profile

共享 SDK 支撑代码
  └─ 环境、调用、结果、错误、耗时和成本观测
```

推荐验收标准不是“CLI 命令里少了几个参数”这么简单，而是：

1. 用户内容提取的配置由专用 builder 正向构建；
2. options 中没有 MCP、tools、Skills、Subagents 和 project setting sources；
3. `cwd` 指向隔离的任务目录；
4. 仍通过真实 Claude Agent SDK 和真实 API 获得 structured output；
5. 输出通过 SDK schema 校验和 DocFit 领域校验；
6. Student 002 等真实样本与 gold 对比后，内容忠实性、顺序和语义绑定不退化；
7. 记录初始化、API、各批次和后处理耗时，验证优化的真实贡献。

## 11. 容易混淆的几个判断

### “是不是 MCP 或 Skill 描述不准确？”

当前主要不是。描述不准确会影响 Agent 在拥有工具后的选择；当前问题是这个任务本来就不该拥有这些工具和项目能力。

### “是不是 Agent 调用了错误工具？”

不是。当前实现已经禁用了工具调用，但保留了与任务无关的 MCP、settings、hooks 等运行配置。这是启动前的装配问题。

### “模板提取和用户内容提取不能共享代码吗？”

可以，而且应该共享中立 Word 事实层与 SDK 接入基础设施；不应共享完整业务 prompt、能力边界和 output schema。

### “专用内容提取配置是不是新增了第四个产品模块？”

不是。它只是让现有用户内容提取模块拥有与其责任相匹配的运行 profile。

### “两个模块都用 `ClaudeSDKClient`，是不是同一个 Agent？”

不是。同一个客户端类可以创建多个独立实例和 session。Agent 的业务身份由输入、system prompt、工具、schema、权限和工作流共同决定，不由 Python 类名决定。

## 12. 以后判断 Agent 配置是否合理的检查表

面对一个新的 Agent 任务，可以依次问：

1. Agent 的输入是否已经由确定性程序准备好？
2. Agent 是否真的需要读取文件或调用工具？
3. 每个 MCP、Skill、hook 和 permission callback 分别服务哪个产品责任？
4. 不提供某项能力，产品合同是否仍然能够完成？
5. `cwd` 和 project settings 会不会引入任务外上下文？
6. output schema 只约束形状，还是还需要领域级确定性校验？
7. 这是一次性任务还是需要连续会话？
8. 共享的是事实/基础设施，还是不小心共享了业务边界？

如果某项能力无法对应到明确的产品责任，默认不应该进入该模块的 Agent profile。

## 参考资料

- [Claude Agent SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python)：`ClaudeAgentOptions`、`ClaudeSDKClient`、session 和 Python API 的官方定义。
- [Hosting the Agent SDK](https://code.claude.com/docs/en/agent-sdk/hosting)：CLI 子进程、session、工作目录和运行架构的官方说明。
- [Get structured output from agents](https://code.claude.com/docs/en/agent-sdk/structured-outputs)：`output_format`、JSON Schema 和 `ResultMessage.structured_output` 的官方说明。
