# DocFit 领域上下文

## 模板工作区

- **模板源对象**：第一次 Agent 判断前归一化生成的 canonical source entry，持有绑定不可变原文件的 `source_entry_id`。它可以对应多个底层 Word 对象；分区、分页和重试只投影，不重新编号。
- **对象引用**：绑定到快照的结构身份，包括 `document_sha256`、对象 ID 和 fingerprint；旧引用只对旧的不可变版本有效，不能指向新版本里的对象。
- **文档引用**：由 SHA-256 标识的任务内不可变 Word 版本；内部版本用于反馈和恢复，不是用户交付物。
- **Field Registry**：跨阶段字段语义表；模板提取先提供允许选择的字段词表，字段详情按需查询。它不是整份模板应生成的槽位清单。
- **最终模板**：由已接受判断物化、通过 Harness/App 完成检查及当前版本视觉复核后，App 发布到 `output/final-template.docx` 的可填写 Word；产品人工签收另行完成。
- **Fill Contract**：发布到 `output/fill-contract.yaml` 的可人工审核、可机器读取填写指南；它绑定精确的最终模板 hash，并说明字段、位置、条件、样式和人工动作。
- **学校提取交付**：一个原子双文件产品单元：`final-template.docx` 加 `fill-contract.yaml`。报告、回执、渲染和 manifest 都是内部证据，不是额外交付主件。
- **阶段 proof**：模板提取内部 checkpoint 的机器可读验收产物，用于 replay、resume 和调试归因；它绑定当前输入 hash，不是 Gold，也不是最终产品交付。
- **UnitBoundaryProof**：模板提取单元拆分 checkpoint 的阶段 proof；记录初始完整源对象清单绑定、Agent 在已有源对象上选择的边界、Harness 解析的精确源范围和 coverage 结果。对象内部切分保持原 ID；旧文字/页码定位 proof 拒绝。单元阶段闭合后，后续字段、样式、Registry、apply 和发布调试应从该 proof 的 accepted units 继续。
- **Accepted units**：已通过 Harness 机械验收的模板顶层逻辑单元集合。它是模板提取后续阶段的内部上下文接口；Agent 不应重新拆分单元，除非 proof 校验失败或输入 hash 改变。
- **阶段 replay**：对同一真实输入和同一 checkpoint 重放 Agent-style payload、Tool resolver 和 Harness check 的开发反馈环；它不同于最终 Actual-vs-Gold Eval，不能把 Gold 或 accepted answer 注入 runtime。

## 架构边界

Claude Agent SDK 负责 Agent loop、上下文、Tool call、权限和生命周期。DocFit 提供聚焦的
Word、字段和视觉 Tool，以及机械反馈。DocFit 不需要 Agent 先写 mutation plan、compiler、
attempt path 或语义 checker。

模板提取的最高优先级责任层定义：Agent 只做学校语义判断，包括对象责任、填写接口、固定内容、
样例/说明、样式代表、生成机制和正文结构判断。Harness/session 负责 hash、checkpoint、
task root、stale ref、coverage 和 resume 账本。Tool 负责把已闭合判断转换成可验证 DOCX
操作并返回可修复 feedback。Schema 只保护真正跨层交换的合同；内部运行产物、provenance、
trace 和临时反馈不能平铺成 Agent-facing schema。

post-unit 的验收应是阶段级 Harness gate：Agent 判断完对象集合并声明进入下一阶段后，Harness 自动
校验对象目标、Registry field、覆盖、冲突和可执行性。不要把 `docfit_check(action_plan)` 这类
每对象手动检查当作 Agent 安全写入前置条件。发现语义错误，先检查输入事实、上下文和合同表达；
确认领域指引不足后再改 Skill/Reference。正确判断因映射或执行能力不足而失败，仍是工程层未完成的任务。

## 通用兜底样式产品记忆

- `docfit.general_thesis.zh@1.0.0` 已于 2026-08-11 经产品负责人接受，作为当前通用论文兜底基线。
- 已验证完整的学校角色永远原样优先；缺失或不完整的学校角色才使用完整的版本化兜底角色。一个角色内不能混用学校属性和兜底属性。
- 未来讨论或调整通用兜底样式时，必须同时给出面向人的产品复核表：全局兜底样式表、完整字段处理映射表、继承展开后的完整有效样式表。
- YAML 和工程产物不能替代这些产品复核表。任何影响取值、角色边界、参数、来源分类、字段覆盖或完整性状态的变更，都需要更新表格、重新闭包验证并再次产品确认。
- v1 产品定义被接受只表示可以进入工程实现，不证明 runtime 已实现、视觉正确或符合国标。

## Student content extraction product evidence

Student content extraction acceptance inspects the final `student-content.json`: values, fields,
order, grouping, relations and provenance. `run-report.json` is diagnostic evidence and does not
replace inspection of the content model.
