# DocFit 稳定样式契约实施状态

- **Capsule status**：DONE（第一垂直切片）；通用兜底完整性门仍为 `BLOCKED_INCOMPLETE`
- **来源合同**：`docs/docfit-06-development-roadmap.md` §6.8；2026-08-10 用户批准按稳定样式架构实施并提交代码
- **当前目标**：让模板发布、Placement、Fill、Projection 与最终审计共享不可变的 Style Contract；同一 `style_contract_id + digest` 的全部实例具有一致的受管有效属性
- **当前切片**：建立产品 Style Contract Module、模板发布 artifact、下游引用/落地与 occurrence-level 验证
- **完成结果**：Fill Contract v2、Style Contract Set、有效样式 resolver、最终模板捕获、逐 occurrence 物化与重新打开校验已经贯通；代码提交为 `819fb50`
- **最后证据**：产品单元测试 `282 passed`；模板合同与全量 contract gate 通过；独立模板提取 Eval `159 passed`；Ruff 全量通过；Mypy `75 source files` 通过
- **集成环境说明**：学生填充集成执行已进入最终 style audit，`2/2 passed`、`0 failed`、`0 unresolved`；后续视觉阶段因固定 Docker LibreOffice renderer 不可用而中止，不属于 Style Contract 失败，但完整视觉 E2E 仍需在标准渲染环境复验
- **下一步**：关闭通用兜底的角色、来源、取值、实现和验收五类缺口；门禁通过前不得把候选 preset 接入后续产品阶段
- **下一证明**：完整 preset artifact、正式标准条款核验、全部角色 deterministic materialization、全量门禁测试和 Human acceptance
- **停止条件**：公开 Agent Tool schema 或 Agent runtime 需要改变；发现真实外部 fill-contract v1 消费者需要迁移决策；需要未授权标准数值来源
- **不修改范围**：Claude Agent SDK loop/session/permission/lifecycle；公开 Tool 名称；Field Registry 语义；visual renderer；真实学生内容与私有样本
- **已停放**：公共 CLI；M3 Human Gold 晋升

## Agent 架构边界依据

本切片只调整 DocFit 的领域合同与确定性 DOCX 写入链，没有新增公开 Tool，也没有改造 Claude Agent
SDK 的 tool-use loop、session、permission 或 lifecycle。Agent 层继续遵循官方 tool-use 合同：模型发出
`tool_use`，应用执行工具并返回匹配的 `tool_result`；样式稳定性由 Tool 之后的确定性领域层负责，而不由
模型自由生成。官方依据：
[How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)。

## 通用兜底的当前现状

当前结论是 `BLOCKED_INCOMPLETE`，不能进入后续产品阶段。现有成果只证明了两件事：

1. `docfit-general-style-preset-v0.1.sample.yaml` 已完成 54 个字段到 46 个候选样式/布局角色的结构闭包；
2. Style Contract 第一垂直切片可以对核心段落/Run 属性做 digest 绑定、物化和 occurrence-level 验证。

这不等于通用兜底已经完成。当前仍有以下阻塞：

- **角色不完整**：候选角色集合尚未 Human acceptance；编号、表格条件样式、Theme、完整页面/分节/container，以及 header、footer、footnote、textbox 等跨 story 行为尚未闭合；
- **来源不完整**：正式国标全文的条款映射尚未完成，现有 4 项国标规则仍基于公开草案证据；
- **取值不完整**：字体、字号、行距、段前后和题注等产品预设值仍是未批准候选值；
- **实现不完整**：稳定 Style Contract 尚未提供“学校完整角色优先，否则整角色选择版本化 preset”的运行时 registry/resolver，旧实验代码仍是属性级 fallback；
- **验收不完整**：尚未完成全角色合成回归、真实学校缺样式反例、重复 occurrence、最终 Word 视觉复核和 Human acceptance。

## 后续阶段硬门

通用兜底只有在以下五项**全部为 `PASSED`**时才可进入模板融合、正式 Student Fill 和 M3 产品阶段：

1. **角色完整**：本阶段支持的每个字段、内容对象、页面和容器行为，都绑定完整角色或被明确标记为非样式字段；
2. **来源完整**：每个受管属性只能来自正式国标明文、已批准产品预设或当前任务显式要求，并保留版本、条款/决策和 digest；
3. **取值完整**：每个 preset 角色的全部受管属性都有确定值，不存在依赖 Word `Normal`、学校历史样本或模型猜值的隐式缺省；
4. **实现完整**：代码按完整语义角色二选一，学校角色与 preset 角色不逐属性混合，并在学生内容写入前物化完整目标模板；
5. **验证完整**：schema、引用闭包、确定性、materialization、occurrence audit、集成回归、Word 渲染和 Human acceptance 全部通过。

门禁采用全有或全无语义：任一项为 `PARTIAL`、`UNKNOWN`、`UNRESOLVED`、`FAILED` 或未验收，
`next_stage_allowed` 必须为 `false`。内部研发和门禁测试可以继续，但不得把候选 preset 接入用户任务，
也不得以局部通过声称通用兜底已经可用。
