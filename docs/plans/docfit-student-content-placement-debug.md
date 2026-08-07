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
               candidate.docx
                       │
                       ▼
      template-bound quality projection
                       │
                       ▼
  quality candidate + structural/visual evidence
```

- Inventory 为每个顶层 paragraph/table/picture 生成任务内 `content_id`、顺序、源
  `object_ref`、内容类型、原文和文本 hash，并保留 package/object 风险摘要。
- Agent 只负责字段含义、共享事实 occurrence、冲突和连续内容边界；不直接写 DOCX。
- Placement 使用 `field_id` 连接 source content 与具体 slot/region；`field_id` 本身不是 locator。
- 填充只消费模板 hash 绑定的 `content_control_tag` locator。普通文本槽保留模板 run 样式；
  block-level rich content 使用现有 OOXML dependency closure 复制学生对象，但不把学生源 style ID
  带入目标包。
- 独立 quality projection 只处理本次导入对象：语义标题投影到目标模板 heading style，正文和参考文献
  投影到目标模板 style；图、题注、表和公式采用目标模板已有 style 作为基底，并添加可审计的对象安全
  direct formatting。模板表单和未授权区域不进入投影范围。
- 所有保存写新文件；源学生文件、目标模板和 fill contract 均不覆盖。

### 3.1 当前样式政策与未来产品边界

已确认的产品背景是：学校交付的 Word 模板通常不会覆盖学生论文需要的全部语义样式。长期产品需要一套
版本化、学校样式缺失时才启用的 DocFit 内置兜底样式库，并明确学校样式与内置样式的优先级、审计证据
和升级兼容规则。

该能力**不属于当前切片**。本轮不得创建、复制或偷偷补齐新的 formula/caption/heading style，也不得把
南京农业大学历史复核稿中的样式带入湖南农业大学模板。当前候选只能：

1. 使用绑定模板中已经存在的 `DocFitHeading1/2/3`、`DocFitBody`、`DocFitReference`、`caption`
   和 `Normal`；
2. 对图片居中、图题分页绑定、表格版心宽度、公式不裁切等对象级要求使用可审计 direct formatting；
3. 对模板没有提供专用样式的公式，使用模板已有 `DocFitBody` 作为基底，不新增公式样式；
4. 把缺失的专用样式和 Word-only 更新验证继续报告为限制，而不是伪造完成状态。

## 4. SDK 官方边界

当前仓库继续使用锁定的 Claude Agent SDK 0.2.128。官方 Python SDK reference 定义了
`ClaudeSDKClient`、`ClaudeAgentOptions.output_format`、Tool allowlist 和 Skill 名称等原生
Agent/session 机制；本切片复用该运行时，不另建 Agent loop：
<https://code.claude.com/docs/en/agent-sdk/python>。

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
9. 质量投影后公式、图片、表格、正文可见文本和编号事实不丢失；批准的 9 组文本空格修复逐组精确
   计数，其他正文不得被改写。
10. 所有导入图转换为独立 inline 图段；图、中英文图题通过 `keepNext/keepLines` 形成分页链；表格
    归一到所在节版心宽度并禁止单行跨页拆分。
11. TOC 必须保留真实 field、标为 dirty 并设置 `updateFields=true`；LibreOffice 缓存未更新不能冒充
    Microsoft Word 已完成目录刷新。

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

## 8. 历史错误复核后的质量投影结果

2026-08-07 对 `temp/` 中南京农业大学三份修复报告、逻辑单元/分页说明、Word 对象保全说明和同源
学生稿人工复核版完成交叉复核。复现并修复了当前候选的五类根因：

- OfficeCLI 检查结果漏掉 3 个纯 OMML 顶层段落；inventory 现在以 `word/document.xml` 顶层对象
  反向补齐，真实正文由 166 个对象增至 169 个，候选恢复为 4/4 公式。
- 6 个浮动图原本与正文或题注同段；现在全部拆为独立 inline 图段，6/6 图都有连续题注分页链。
- 学生源 style 和大量 direct run 排版污染目标模板；填充阶段不再复制源 style，质量候选 style 集合
  与模板完全一致，清除 run 级字符间距/缩放/位置/字号字体冲突，并合并 2491 个等价相邻文本 run。
- 正文中的 29 个无文本、无受保护 payload 的空排版段被移除；3 级标题分别投影 3/10/23 个，
  目录 field 标 dirty 且 `updateFields=true`。
- 1 个学生表格按目标节 8958 dxa 版心归一、17/17 行禁止跨页拆分；6 张图均未超出版心。

质量候选 SHA-256 为
`39caaaffddf55d4749957e25610cd743a529fbe3b17c5f30093599ce8cf5d3f0`。确定性审计确认 174 个
已选有文本对象零丢失、6 图/4 公式/1 学生表零丢失，9 组批准文本修复各命中一次，输出没有非模板
style。固定 LibreOffice 25.2.3.2 渲染 47 页并逐页复核；图表与题注链、正文分页和参考文献页面未见
新的阻断性视觉错误。

结果仍为 `PARTIAL`：11 个 required 元数据缺失，致谢/附录无学生来源，模板 fill contract 尚未人工
验收，目录 cache 在 LibreOffice 中仍显示占位内容并需要 Microsoft Word 真实刷新，且模板本身和候选
均被固定 OfficeCLI 无诊断拒绝。以上限制不能由本轮样式投影消除。
