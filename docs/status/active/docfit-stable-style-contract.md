# DocFit 稳定样式契约实施状态

- **Capsule status**：DONE（第一垂直切片）；通用兜底 v1 已通过声明范围属性闭包和产品验收，产品定义门为 `PASSED`
- **来源合同**：`docs/docfit-06-development-roadmap.md` §6.8；2026-08-10 用户批准按稳定样式架构实施并提交代码
- **当前目标**：让模板发布、Placement、Fill、Projection 与最终审计共享不可变的 Style Contract；同一 `style_contract_id + digest` 的全部实例具有一致的受管有效属性
- **当前切片**：建立产品 Style Contract Module、模板发布 artifact、下游引用/落地与 occurrence-level 验证
- **完成结果**：Fill Contract v2、Style Contract Set、有效样式 resolver、最终模板捕获、逐 occurrence 物化与重新打开校验已经贯通；代码提交为 `819fb50`
- **最后证据**：产品单元测试 `282 passed`；模板合同与全量 contract gate 通过；独立模板提取 Eval `159 passed`；Ruff 全量通过；Mypy `75 source files` 通过
- **集成环境说明**：学生填充集成执行已进入最终 style audit，`2/2 passed`、`0 failed`、`0 unresolved`；后续视觉阶段因固定 Docker LibreOffice renderer 不可用而中止，不属于 Style Contract 失败，但完整视觉 E2E 仍需在标准渲染环境复验
- **下一步**：可按已验收 v1 开始整角色模板融合的工程实现；正式标准条款完成授权复核前不得作国家标准符合性声明，运行时与视觉证据通过前不得声称产品能力完成
- **下一证明**：完整学校角色/完整 v1 角色二选一、填充前完整目标模板、全角色回归、真实学校反例和最终 Word 人工验收
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

当前产品结论是 `PRODUCT_DEFINITION_ACCEPTED`。产品负责人已于2026-08-11接受三张评审表、
六组产品决策、参数边界和来源分类，通用兜底 v1 成为当前有效产品基线；这仍不能据此声称
运行时或国家标准符合性已经完成：

1. `docs/plans/docfit-general-style-preset-v1.review.yaml` 覆盖注册表全部 54 个字段，其中 50 个字段绑定样式/版面候选角色，4 个字段具有明确非样式处理；
2. 文件定义 44 个样式角色、13 个全局/版面角色和 8 项来源记录，并分别建立 9 类样式类型、11 类全局/版面类型的完整属性集合；
3. 类型基线、角色继承和角色覆写已经展开验证；全部要求属性具有具体值、明确 `0`、`none` 或 `N/A`，不存在空白、未说明的 Word 默认值或依赖学校 `Normal` 补齐关键属性；
4. 三张产品评审表已经生成：全局兜底样式表、54 字段处理映射表和 44 角色完整有效样式表；
5. 已填写的值区分国家标准元数据/公开稿暂定规则、高校官方材料形成的产品预设值和 DocFit 明示产品决策；
6. Style Contract 第一垂直切片可以对核心段落/Run 属性做绑定和验证，但尚不代表 v1 的全部版面、编号、表格和对象规则已经实现。

这表示“声明范围内的产品属性闭包”和“通用兜底产品定义”已经交付。当前剩余阻塞均属于
工程实现、验证或符合性声明，不再属于产品取值待定：

- **范围持续开放**：注册表 v0.1 的 54 行处理和 44 个样式角色已验收；注册表仍是 open-world，新增字段必须重新触发三张产品表更新和闭包检查；
- **正式标准待复核**：国标身份、状态和实施日期已由官方平台确认，但正式全文受版权限制未完成授权条款映射；现有 4 项结构规则仍明确标记为官方公开稿暂定证据；
- **实现不完整**：稳定 Style Contract 尚未提供“学校完整角色优先，否则整角色选择版本化 preset”的运行时 registry/resolver，旧实验代码仍是属性级 fallback；
- **验收不完整**：尚未完成全角色合成回归、真实学校缺样式反例、重复 occurrence、最终 Word 视觉复核和 Human acceptance。

## 后续阶段硬门

通用兜底采用两层硬门。第一层产品定义门已于2026-08-11通过：三张产品表、六组产品决策、
参数边界和来源分类均已接受，`product_definition_complete=true`。正式标准全文复核保留为
国家标准符合性声明前置条件，不阻塞采用当前 DocFit 产品预设。第二层是后续工程/产品化门；
只有以下五项**全部为 `PASSED`**时才可进入正式 Student Fill 和 M3 产品阶段：

1. **角色完整**：本阶段支持的每个字段、内容对象、页面和容器行为，都绑定完整角色或被明确标记为非样式字段；
2. **来源完整**：每个受管属性只能来自正式国标明文、已批准产品预设或当前任务显式要求，并保留版本、条款/决策和 digest；
3. **取值完整**：每个 preset 角色按类型展开继承后的全部适用属性都有确定值；明确为零写 `0`、无编号写 `none`、不适用写 `N/A`，不存在空白、隐式 Word 默认、依赖学校 `Normal`、学校历史样本或模型猜值；
4. **实现完整**：代码按完整语义角色二选一，学校角色与 preset 角色不逐属性混合，并在学生内容写入前物化完整目标模板；
5. **验证完整**：schema、引用闭包、确定性、materialization、occurrence audit、集成回归、Word 渲染和 Human acceptance 全部通过。

工程/产品化门采用全有或全无语义：任一项为 `PARTIAL`、`UNKNOWN`、`UNRESOLVED`、`FAILED`
或未验收，`production_fill_allowed` 必须为 `false`。`next_stage_allowed=true` 只表示产品定义已经
允许开始工程实现；在工程门通过前，不得把 v1 接入用户生产任务，也不得以局部通过声称运行时能力完成。
