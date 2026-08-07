# DocFit 学校模板提取 v2 执行胶囊

- Capsule status: `BLOCKED / AGENT SEMANTIC-LOCATION CONVERGENCE`
- Source design: `docs/plans/docfit-school-extract-v2-candidate-skill/DESIGN.md`
- Source plan: `docs/plans/docfit-school-extract-v2-candidate-skill/PLAN.md`
- Latest user decision: 当前开发阶段充分信任 Agent 的语义判断；产品提供可执行 Tool、任务上下文、
  before/after、全页渲染反馈、常见错误和领域知识，不使用 mutate 内置语义检查器否决 Agent 已
  编译的决定。当前不考虑模板是否固定。
- Credential/API status: Token Plan credential 已安装到仓库外配置；对 MiniMax M2.7 官方接口的
  最小请求返回 HTTP 200，真实 Claude Agent SDK 调用、MCP Tool 与 filesystem Skill 均已进入
  有效执行。此前 HTTP 402 的根因是误用了与 Token Plan 资源池分离的普通按量 key，已排除。
- Runtime repairs: 该次历史执行的 selected credential 使用 `ANTHROPIC_AUTH_TOKEN`，模型为
  `MiniMax-M2.7`；当前全局默认已切换为 MiniMax 优先的 `MiniMax-M3`；
  Agent turn 上限提高到 160；MiniMax 把 JSON Schema 常量 `1` 发送成字符串 `"1"` 的传输差异
  由 `PreToolUse` hook 规范化，不把 provider 兼容问题下沉到领域 Tool。
- Capability/safety repairs: template task 的 `Write` 只能新增 decisions YAML/JSON，`Bash` 只能
  调用两个既有 compiler 并写入 task-local compiled 输出；禁止绕过 `template_mutate`、直接复制
  DOCX 或人工伪造最终产物。机械边界保留，语义决定仍由 Agent 负责。
- Observation repair: snapshot 保留完整对象 inventory；在响应上下文过大时，南农模板的 210 个
  paragraph object 直接内联，run/table 等对象可继续通过 `template_observe.query` 按需取得，避免
  早期运行把“上下文省略”误当成“模板没有对象”。
- Full CLI evidence: `temp/docfit-school-extract-v2-njau-minimax-token-plan-r6/` 已完成真实结构观察、
  全页 render/visual review、两轮 mutate 尝试和 Agent 自检。第一轮 13 个 materialize 操作把标题、
  专业、导师等槽位放到错误段落，Agent 根据 after/视觉反馈主动否决并从原模板重试；第二轮仅能
  高置信定位 7 个槽位，保留 7 个 gap，`remove_content` 仍为 0，最终诚实返回 blocked。
- Publication result: 没有调用成功的 final compare/build，没有四文件 template artifact，也没有把
  `mutated-template-001.docx` 或 `mutated-template-004.docx` 接受为候选交付。当前反馈与发布边界能
  阻止错误模板被误报为成功。
- Confirmed non-blockers: Token Plan key/额度、M2.7 endpoint、基础 SDK Agent loop、Skill 装载、
  MCP transport、render/visual review 和 mutation 执行能力。
- Current blocker: Agent 能发现明显错误，但现有观察界面不便于稳定表达“标签旁边的空白填写区”
  与“标题后的空正文区域”；它需要大量逐对象查询，仍无法在一次运行内为 32 个需求槽位形成可靠
  locator，内容清理也没有发生。问题位于语义定位与反馈效率，不是隐藏 checker 或 API 额度。
- Architecture boundary: 保持 Claude Agent SDK 原生 Agent loop、permissions、hooks、Skill、MCP
  Tool 和 structured output；不新增语义检查器。下一步建议给观察能力增加确定性的相邻对象/空白
  区域候选查询，Tool 只返回事实和 object ref，由 Agent 选择、mutate、渲染并自检。该公开能力
  需要先作为产品/Tool 合同决策确认，不能在本轮静默加入。
- Parked: 旧 Agent smoke harness 的 provider 兼容问题、Human Gold、W6 生产切换、模板
  fixed/frozen 生命周期，以及未被真实运行证明需要的新 mutation operation。
- Resume condition: 用户确认是否增加“相邻对象/空白区域候选”观察能力；确认后实现最小合同、
  通过 bounded test，再用新的空 task root 重跑完整 CLI。不得续用 r1–r6 的半成品 task root，也
  不得人工补齐产物。
- Stop condition: API 与 transport 问题已修复，真实 Agent 反馈回路已验证，但 W5 Agent Gate 未
  通过；当前没有合格学校模板产物，W6 保持不可执行。
