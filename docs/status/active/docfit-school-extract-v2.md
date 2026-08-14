# DocFit 学校模板提取：Agent-first 重构状态

- Status: `IMPLEMENTED / REAL PROVIDER RE-VERIFICATION PENDING`
- Architecture: `main_agent_full_context/v1`
- Scope: 模板运行时、Skill/reference、稳定 Tool 面、确定性发布；Eval/Gold 由独立工作流维护。

## 根因结论

上一代实现把 Agent 当作应用状态机里的局部分类器：应用选择 work item、裁剪上下文、绑定候选、
推进 cursor、组织重试和决定完成。它把模型失败转化为更多 schema/gate/session，导致 79m47s 的
NJAU 运行仍未发布。问题不是“协议数量”本身，而是应用通过协议取代了 Agent 的上下文理解、任务
分解、Tool 选择、重试和完成判断。

## 当前运行合同

```text
模板 + 要求 + Registry + 目标/输出边界
                    ↓
        一个主 Agent / 一次 SDK query
                    ↓
  自主 inspect / render / review / edit / delegate
                    ↓
        Agent 选择最终候选并 validate
                    ↓
  应用检查客观后置条件并生成绑定产物
```

- canonical Skill 只有 `.claude/skills/docfit-school-extract/**`；旧 candidate Skill 已删除。
- 主 Agent 知道全部输入角色并可取得整份可查询 inventory；渐进披露路径由 Agent 选择。
- 主 Agent 可使用 SDK 原生 `docfit-unit-analyst` 做自包含只读分析，保留全局合并和写入权。
- 公开能力保持五个稳定 Tool；模板操作是 `docx_edit` 内无状态 action。
- 五个 Tool 是可选能力，不是固定调用清单：源模板已合格时可直接选择只读 source snapshot；只有
  候选发生修改时才要求 `docx_edit` 证据。
- `TemplateWorkspaceService`、`template_*` work-item Tool/schema 和应用区域状态机已删除。
- 应用只创建不可变任务副本，配置权限/预算/观测，验证输入、hash、package、Registry、最终全页
  证据和 Fill Contract/Word 一致性。
- 旧 checkpoint 不迁移；clean-break 直接拒绝上一代任务目录。

## Skill/reference

Skill 教主 Agent 如何建立全局结构/视觉认识、分类文字、选择正文代表、处理 TOC/集合/可选区、
形成 Subagent task packet、合并冲突和判定完成。七个 references 是方法与反例，不是应用语义 gate：

- `template-text-classification.md`
- `body-structure.md`
- `generated-content-and-toc.md`
- `collections-and-optional-sections.md`
- `delegation-strategy.md`
- `evidence-and-conflicts.md`
- `completion-and-visual-review.md`

## SDK 官方依据

- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)：SDK 提供完整 Agent loop、
  context、Tool、Subagent、permission、session 和 Skill 能力。
- [Agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)：Claude 评估、选择 Tool、接收结果并
  重复，直至任务完成；`max_turns`/budget 是生产上限，不是应用语义步骤。
- [Custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)：DocFit 以 in-process MCP 提供
  领域能力，Tool 由 name/description/schema/handler 构成，不需要工作流 RPC。
- [Subagents](https://code.claude.com/docs/en/agent-sdk/subagents)：主 Agent 可按任务选择隔离上下文、
  受限 Tool 的 Subagent。
- [Sessions](https://code.claude.com/docs/en/agent-sdk/sessions)：一次 `query()` 已可执行完成任务所需的
  多个 turn；client 多 prompt 用于真正需要共享会话的多轮交互，不用于应用切分一个任务。
- [Permissions](https://code.claude.com/docs/en/agent-sdk/permissions)：权限策略由 hooks/deny/ask/mode/
  allow/callback 组合，DocFit 不需借工作项协议实现权限。

## 当前证据（2026-08-13）

- Ruff、strict mypy 与 diff whitespace 检查通过新的 runtime surface。
- 392 个 contract/unit/Agent-first 测试通过；证明唯一 Skill、一次完整任务、五 Tool 注册、原生
  Subagent、无 legacy workspace/tool 文件，以及“无修改不强制 edit”的合同。
- `tests/integration/test_m1_tools.py` 五项全部通过；固定镜像
  `docfit-libreoffice-visual:25.2.3.2` 已完成真实 inspect/edit/import/render/review/validate 与无状态
  publication 回归。
- 真实 provider 小模板探针已验证主 Agent 自主选择 inventory、contact sheet 和 detail page，应用未
  生成 work item。但 MiniMax 两次在视觉回合后响应超过 6 分钟而未终结；Kimi 三个已配置 key 均因
  billing-cycle quota 返回 403。真实 provider publication 因外部 provider 状态尚未闭合，不能据此
  宣称成功率或性能目标已通过。

## 下一门禁

1. Kimi quota 恢复或确定 MiniMax 视觉响应预算后，用真实 provider 对小模板完成 publication。
2. 再跑 NJAU 大模板，比较 wall time、turn/tool 数、成功率与最终人工/Word 原生证据。
3. Eval/Gold 只消费产物评分，不反向控制运行时语义。
