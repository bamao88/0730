# Student Content → Placement → Template Fill 独立调试计划

> 状态：批准范围内实施中  
> 日期：2026-08-07  
> 基线：`0c3f292c2005722a8019c3bb32864829258f8da9`  
> 分支：`codex/student-content-placement`

## 1. 目标

用一份只读真实学生 DOCX 和一份用户指定的冻结目标模板，建立可独立调试的最窄纵向链：

1. 全量盘点学生源中的顶层正文对象与复杂对象事实；
2. 由现有 `convert-thesis` Agent 只从学生源证据提取共享字段和连续内容区间；
3. 形成 hash 绑定的 Student Content Actual 与 Placement Actual；
4. 从目标模板副本生成候选 Word，填入有可靠来源的字段和连续内容；
5. 对缺失、冲突、不支持和未映射内容保持显式状态，不猜测、不静默丢弃。

本切片是路线图 6.9 的独立调试实现，不调用 `prepare-template`，不等待学校模板提取 r2，
也不修改模板提取 Eval。目标模板虽然位于 `gold/` 路径，但 case 状态仍是
`candidate_pending_human_acceptance`，因此本切片只能发布调试候选，不能宣称学校格式转换完成。

## 2. 固定输入

- 学生源：`student-content-real-student-002.docx`
  - SHA-256：`fc39ac02efd152ddf609199615256393e3077b49629e1cca48e1f437b2e44a9b`
  - 始终只读，不进入 Git、CI、日志或普通测试 fixture。
- 目标模板：HUNAU candidate `template.docx`
  - SHA-256：`70b13aecf084816a5ff5abc879c00d26c63552c0c36623060b17cbae3d775f50`
- 填写契约：`docfit-template-fill-contract/v1`
  - 31 个槽、1 个生成目录区域、28 个 required 槽；状态为 candidate。
- Registry：`docfit.thesis.content_fields@0.1.0`
  - SHA-256：`9779d0272fc395245002184d43e8356b0722a6821e8ca0a36ced0db6d26d522d`。

## 3. 模块边界

```text
read-only student.docx
        │
        ▼
Student inventory ──► Agent semantic extraction
        │                         │
        └──────────────┬──────────┘
                       ▼
             student-content.json
                       │
candidate template + fill-contract + Registry
                       │
                       ▼
                 placement.json
                       │
                       ▼
            deterministic template fill
                       │
                       ▼
        candidate.docx + validation evidence
```

- Inventory 为每个顶层 paragraph/table/picture 生成任务内 `content_id`、顺序、源
  `object_ref`、内容类型、原文和文本 hash，并保留 package/object 风险摘要。
- Agent 只负责字段含义、共享事实 occurrence、冲突和连续内容边界；不直接写 DOCX。
- Placement 使用 `field_id` 连接 source content 与具体 slot/region；`field_id` 本身不是 locator。
- 填充只消费模板 hash 绑定的 `content_control_tag` locator。普通文本槽保留模板 run 样式；
  block-level rich content 使用现有 OOXML dependency closure 复制学生对象。
- 所有保存写新文件；源学生文件、目标模板和 fill contract 均不覆盖。

## 4. SDK 官方边界

当前仓库继续使用锁定的 Claude Agent SDK 0.2.128。官方迁移文档仍把
`ClaudeSDKClient`、`ClaudeAgentOptions` 和 `create_sdk_mcp_server` 描述为自托管 Agent SDK
的原生 Agent/tool/session 模型；本切片复用该运行时，不另建 Agent loop：
<https://platform.claude.com/docs/en/managed-agents/migration>。

领域方法继续放在现有 Skill 中。官方 Agent Skills 文档把 Skill 定义为按需加载的领域说明、
脚本和资源，并支持渐进披露：
<https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>。

Agent 最终提取结果使用 JSON schema structured output；官方文档明确其用途包括从文本/图片提取
可验证结构化结果：
<https://platform.claude.com/docs/en/build-with-claude/structured-outputs>。

Managed Agents 迁移不属于本切片；若未来执行，必须作为独立架构决策。

## 5. 状态与失败语义

- `COMPLETE`：所有 required target 有可靠来源，全部 in-scope source 有处置，内容/占位符/
  package/视觉检查均通过，且模板状态已获 Human acceptance。
- `PARTIAL`：已安全生成候选，但存在缺失 required、candidate 模板资格、未支持对象、未决 placement
  或需要人工视觉确认。
- `NEEDS_INPUT`：没有足够证据形成安全写入，例如同一必填字段存在冲突或目标 locator 不唯一。
- `ERROR`：输入 hash 变化、DOCX/package 无法重开、写入后置条件失败或 Agent/runtime 异常。

本次真实样本由于模板仍为 candidate，最高只能达到 `PARTIAL`。

## 6. 验收

1. 学生源、模板、契约和 Registry hash 在运行前后不变。
2. Student inventory 对全部顶层 source object 恰好覆盖一次；复杂对象事实不被文本覆盖冒充。
3. Agent 抽取值必须能回指源 object；缺失和冲突不允许变成写入值。
4. Placement 覆盖所有 extracted source、所有 required target 和所有未解决项。
5. 文本槽 tag 唯一；block slot 必须是 body-level content control；stale hash 一律拒绝。
6. 复制图片、公式、编号、样式和关系后 package 可重开，源媒体 hash 不变。
7. 输出候选可渲染；逐页结论与确定性内容检查分开报告。
8. 普通单元/契约/集成测试不读取真实学生正文；真实文件只用于忽略目录下的手工调试证据。

## 7. 首轮真实调试结果

2026-08-07 的首轮真实调试达到 `PARTIAL`，没有达到 `COMPLETE`：

- Agent 权限收敛为 `Skill`、path-bounded read 和 `docx_inspect`；`PreToolUse` 会移除
  `docx_inspect.output`，因此 Agent 不持久化检查正文。SDK structured output 原始结果只保存到任务私有目录，
  后置规则修复可 deterministic resume，不需要重跑模型。
- Student inventory 使用 `word/document.xml` 的 body 子节点顺序作为 paragraph/table 混排顺序，
  不再把 OfficeCLI 复合 selector 的返回顺序误当成文档顺序。
- 真实 Agent 提取并验证了 6 类共享字段值、正文连续区间和参考文献区间；11 个 required target
  保持 missing，没有猜测姓名、学号、班级、导师、院系或日期。
- OOXML fill 在没有 `word/numbering.xml` 的目标模板中可创建标准 numbering part、relationship 和
  content type；正文的 6 个 media relationship、1 个表和已选择的 1 个公式均进入候选。
- 确定性 audit 对已选择的 202 个顶层对象、文本值和复杂对象未发现丢失；源文档仍有 65 个 object
  与 3 个 equation 未被 Placement 选择，作为显式 `PARTIAL` 原因保留。
- canonical LibreOffice 25.2.3.2 渲染 47 页并完成逐页检查。非 canonical LibreOfficeDev 26.8
  渲染为 38 页，说明分页对 renderer 版本敏感，产品证据继续只认固定 renderer。
- 固定 OfficeCLI 同时拒绝未修改的 candidate template 和输出 candidate，且不给诊断；因此只能记录
  `new_officecli_regression=UNKNOWN`，不能把 ZIP/XML reopen 和 LibreOffice 可打开替代为结构验证通过。

当前结果证明独立模块边界和数据链可运行，也证明下一轮重点不是继续增强一次性转换逻辑，而是确定
未映射内容处置、缺失字段交互、可选空槽清理、TOC 生成和 Human Gold/validator 基线。
