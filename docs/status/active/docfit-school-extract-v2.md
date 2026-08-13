# DocFit 学校模板提取 v2 执行胶囊

- Capsule status: `COMPLETE / CLEAN-BREAK AND REAL E2E VERIFIED`
- Latest user decision: 先提交当前代码，再按 clean break 完整重构；确定性流程控制归应用代码，
  Agent 只提出当前语义判断或页面视觉结论；不保留旧协议兼容。
- Baseline commit: `5b9e491 feat(content): checkpoint extraction and field contracts` 保存本轮开始前
  已有的 Student Content / Registry / style 工作，聚焦 51 tests、Ruff、Mypy 通过。

## 失败证据与根因

- 南农原始模板上一轮 E2E 运行耗时 `79m47s`，产生 661 个事件、10 次
  `error_max_turns`、53 次 final-review 调用、46 次无效 cursor、65 次 edit；最终没有发布 Word。
- 旧实现把区域推进、跨 session 续跑、cursor、最终页面覆盖、publish 和 built/blocked 终态交给
  同一个 Agent 做语义控制；`while True` 在 `max_turns` 后自动开新 session，缺少硬进度上限。
- PNG 被 Tool 返回时就写入 reviewed coverage，没有独立的逐页 clean/defect 判断，导致“证据已
  提供”和“证据已审查”混为一件事。旧 Agent 还需要复制 document/region ref 和 cursor，直接
  造成高频无效调用。

## 当前 clean-break 合同

- 应用拥有当前工作项、checkpoint 推进、有界重试、终止状态、内部页面 batching、视觉证据失效
  和自动 publication；没有 Agent 控制的流程循环。
- 语义 Agent 只开放四个工作项 Tool：取得当前项、请求有界上下文、提交一次 typed decision、
  报告具体歧义。字段 ID 必须来自当前工作项已提供的 Registry 候选；最多两次 bounded attempt。
- 最终视觉审查使用独立 SDK session，只开放一个“取得当前页批次”Tool。Agent 为绑定批次的每页
  返回 typed clean/defect；应用验证页码精确覆盖后才记录 verdict。
- Agent schemas 中不存在 cursor、document_ref、region_ref、publish 或 built/blocked。内部
  Template Workspace 和 VisualEvidenceService 仍使用 content-addressed ref/cursor 完成确定性
  绑定，但不把它们暴露给模型。
- 任一页面 defect 生成有界单页修复工作项；修改产生新 hash，旧视觉 receipt 自动失效，并从
  第一页重查。最多三轮修复；无新版本或超限返回稳定错误，不继续猜测。
- 全部页面显式 clean 后，应用内部执行 package/OfficeCLI/style/Registry 检查并原子发布；用户
  output 仍只允许 `final-template.docx`，PNG/PDF/evidence 只作内部质检。
- Skill 已减为领域手册：局部对象责任、填写接口、正文结构、按需 references 和最终视觉不变量。
  遍历、cursor/ref、重试、终态、发布 API 和 structured output 示例均已移除；新增独立
  `references/final-visual-review.md`，只在视觉角色使用。

## SDK 基础与边界

- 继续使用 Claude Agent SDK 原生 query/Tool loop、custom in-process MCP Tool、permissions/
  hooks、Skill 和 structured output；语义与视觉使用独立短 session，避免旧图片长期滞留上下文。
- 应用编排只表达模板准备已批准的确定性产品不变量，不复制 SDK 的通用 Agent runtime、session
  store 或 transcript replay。
- Official basis: [Agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop),
  [Custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools),
  [Structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs),
  [Sessions](https://code.claude.com/docs/en/agent-sdk/sessions).

## 最终门禁

- Code/static: role-scoped schemas、应用 orchestrator、typed visual receipt、Skill 和 Tool v5 已落地；
  Ruff 与 strict Mypy 对本次源文件通过。
- Automated: 最终相关门禁 124 tests 全部通过；覆盖应用推进、内部 cursor、idle/max-turn 硬上限、
  精确版本视觉 receipt、有效格式、父子删除归一化、边界保护、幂等分页和增量正文结构。
- Real E2E: 南农 r66 从原始模板生成 `final-template.docx`，最终 13/13 LibreOffice 页面显式 clean；
  机械审计确认 26 个内容控件、11 个节、书签平衡、实时目录、固定标题和零示例标记。
- Word native: 对精确 r66 副本执行打开、全域更新、保存、关闭、重开；Word 原生为 12 页，目录
  保持黑色、无下划线、1–3 级缩进、点引导线和更新后的页码。Word 重写后的 DOCX 再审计通过。
- Product boundary: 应用拥有确定性流程；Tool 负责可执行性和事实反馈；Agent 根据当前学校证据决定
  语义完整性。旧 v4 Tool 合同不保留兼容层。
