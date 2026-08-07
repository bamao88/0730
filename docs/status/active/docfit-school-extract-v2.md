# DocFit 学校模板提取 v2 执行胶囊

- Capsule status: `BLOCKED / TOKEN PLAN KEY NOT INSTALLED`
- Source design: `docs/plans/docfit-school-extract-v2-candidate-skill/DESIGN.md`
- Source plan: `docs/plans/docfit-school-extract-v2-candidate-skill/PLAN.md`
- Latest user decision: 当前开发阶段充分信任 Agent 的语义判断；产品应提供可执行 Tool、任务上下文、
  before/after 与全页渲染反馈、常见错误和领域知识，不使用 mutate 内置语义检查器否决 Agent 已
  编译的清理决定。模板是否固定不在当前阶段考虑。
- Current implementation: `f1ac575` 移除 `template_mutate` 的 protected content/style/section/
  marker 语义 post-check；保留 canonical plan、Registry/marker 输入、snapshot/hash、目标定位、
  DOCX package、源文件不变和原子发布等机械边界。
- Runtime diagnostics: `88956a4` 保留每个 Agent backend 的安全失败证据，CLI 会报告 HTTP status、
  terminal reason 和 turn 数，并汇总所有候选，而不再压成 `template_agent_result_invalid`。
- MiniMax contract repair: `26eae45` 按官方 Claude Code 合同把 selected credential 映射到
  `ANTHROPIC_AUTH_TOKEN`，关闭 Anthropic 非必要后台流量，并把默认/本机覆盖模型改为
  `MiniMax-M2.7`。
- Agent feedback contract: mutate 返回 operation results、after snapshot、mutation evidence 和
  `agent_semantic_review_required`；Agent 必须继续执行 mutation diff、最终全页 render 和实际
  图片检查，Tool 成功不等于结果正确。
- Regression proof: 旧实现会把 Agent 明确授权的 paragraph 清理误判为
  `protected_content_changed`；新公开 Tool 回归用例证明同一计划可提交且源模板保持不变。
- Automated proof: 受影响的 Tool/Agent/CLI 合同 `30 passed`，根项目全量 `353 passed`；scoped
  ruff、strict mypy、lock 和 build 通过。全仓 ruff 只被两个既有未跟踪 `test/` 诊断脚本的
  import 顺序阻断，本切片未修改这些用户文件。
- Rejected prior artifact: `temp/docfit-school-extract-v2-njau-real-r2/` 仅保留诊断证据。它没有完成
  内容清理，required 槽位覆盖不足，且原运行没有干净结束，不再作为有效交付。
- Live run: `temp/docfit-school-extract-v2-njau-agent-trust-r1/` 使用同一份南农模板、requirements
  与 Registry 从空 task root 运行。MiniMax 完成结构 snapshot 和 14 页初始渲染，并写入模板
  段落观察材料；在 mutation decisions 之前后端失效，因此没有 mutation plan、新 DOCX 或产物。
- Confirmed blocker: 三个 Kimi credential 均在 turn 1 返回 HTTP 403；MiniMax 外部配置实际
  使用普通按量 `sk-...` key，而不是 Token Plan `sk-cp-...` key。对官方 M2.7 endpoint 的最小
  请求返回 HTTP 402 / `insufficient_balance_error`，证明请求进入了无余额的按量资源池；截图中的
  Token Plan 额度不会供该 key 使用。
- Architecture boundary: Claude Agent SDK 原生 Agent loop、filesystem Skill、MCP Tool、
  permissions、AskUserQuestion 和 structured output 保持不变；应用只定义能力与安全边界，Agent
  负责语义决定和自我修正。
- No-touch scope: 工作区中现有未提交的全局文档、独立 Eval、LibreOffice 实验及用户临时资料；
  不修改、不清理、不纳入本切片提交。
- Parked: Human Gold、W6 转换生产切换、模板 fixed/frozen 生命周期，以及尚未由真实运行证明
  必需的新 mutation operation。
- Resume condition: 把完整、有效的 Token Plan `sk-cp-...` key 写入仓库外
  `DOCFIT_MINIMAX_API_KEY`，先通过 MiniMax Agent smoke，再使用新的 output task root 原样重跑
  完整 CLI；不得续用半成品 task root 或人工补产物。
- Stop condition: 产品认证/模型映射修复已完成；正确 Token Plan credential 尚未安装，因此没有
  重跑真实模板候选，也未声称 built 或内容验收。
