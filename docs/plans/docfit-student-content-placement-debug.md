# Student Content → Placement → Template Fill 独立调试计划

> 状态：批准范围内的内部切片已实现，真实样本结果为 `PARTIAL`
> 日期：2026-08-09
> 实现基线：`592f7d26d15520c4f62ffeea9ba1f02aeeee741b`
> 分支：`agent/refine-docfit-plan`

## 1. 目标

把学生论文内容提取和模板填写作为独立模块调试，不与当前学校模板提取流程联调：

1. 完整盘点只读学生 DOCX 的顶层正文对象和复杂对象；
2. 使用现有 `convert-thesis` 领域方法做一次只读语义提取；
3. 物化绑定源文件和模板 hash 的 Student Content 与 Placement 候选；
4. 以目标模板为候选主干，确定性填入有证据的标量和连续内容；
5. 只使用目标模板已提供的样式完成质量投影，并输出内容、结构和视觉证据；
6. 对缺失、冲突、未映射、未支持和需要 Word 刷新的事项保持显式状态。

本切片不调用学校模板提取 Agent，不新增公共 CLI、第六个 Tool、第三个领域 Skill 或第二套
Agent runtime。它是路线图 6.9 的内部调试证据，不是正式 Student/Placement schema、产品
运行时完成或 M3 恢复。

## 2. 固定输入和资格

- 学生源 SHA-256：
  `fc39ac02efd152ddf609199615256393e3077b49629e1cca48e1f437b2e44a9b`；始终只读，
  不进入 Git、CI、普通 fixture、Agent transcript 或公开日志。
- HUNAU 目标模板 SHA-256：
  `70b13aecf084816a5ff5abc879c00d26c63552c0c36623060b17cbae3d775f50`。
- Registry：`docfit.thesis.content_fields@0.1.0`，SHA-256：
  `9779d0272fc395245002184d43e8356b0722a6821e8ca0a36ced0db6d26d522d`。
- 填写契约状态仍是 `candidate_pending_human_acceptance`，含 31 个槽和 1 个生成目录区域。

因此，即使所有安全填充后置条件通过，本次结果最高也只能是 `PARTIAL`，不能宣称学校格式
已验收或对外可交付。

## 3. 内部流水线

```text
read-only student.docx
        │
        ├── deterministic full inventory ───────────┐
        │                                            │
        └── one read-only SDK Agent extraction ─────┤
                                                     ▼
                                           student-content.json
                                                     │
template + fill contract + Registry ─────────────────┤
                                                     ▼
                                               placement.json
                                                     │
                                                     ▼
                                      deterministic OOXML fill
                                                     │
                                                     ▼
                                      template-bound projection
                                                     │
                                                     ▼
                                  candidate + audit + render evidence
```

### 3.1 确定性 inventory

- 保存每个顶层 paragraph/table 的文档顺序、源对象引用、可见文本 hash 和依赖对象摘要；
- 使用 `word/document.xml` 顶层对象作为顺序和完整性后备，补齐 OfficeCLI 未报告的纯 OMML
  公式段落；
- 对每个 source object 恰好记账为 mapped、dependency-covered 或 unmapped，不用正文文本
  掩盖图片、公式和表格事实。

### 3.2 Agent 提取

- 只运行一个 Claude Agent SDK session，复用现有 `convert-thesis` Skill；
- 只允许 Skill、只读文件工具、structured output 和 `docx_inspect`，不写文件、不委派；
- Agent 只判断字段语义、共享事实 occurrence、冲突和连续内容边界；应用层验证 exact source
  evidence、对象覆盖和 schema 后才接受结果；
- Agent 原始结构化结果只保存在任务私有目录，后续填写和质量修复可确定性恢复，无需重跑模型。

### 3.3 Placement、填写与投影

- `field_id` 只连接语义，source locator、target locator 和写入授权分别绑定学生源/模板 hash；
- 标量只填唯一 content-control tag；连续正文和参考文献用有序 source object 集合替换模板
  block control；
- 复制学生对象时闭包复制媒体、编号、公式和关系，但不复制学生源 style ID；
- 质量投影只作用于已导入对象：标题、正文、参考文献和题注使用目标模板已有 style；图片、
  题注分页链、表格版心和公式使用对象安全 direct formatting；
- TOC field 只标记 dirty 并设置 `updateFields=true`，未经过 Microsoft Word 刷新的 cache 不得
  冒充目录已更新。

### 3.4 任务绑定的文本质量修补

通用流程不自动猜测或规范化学生正文。经当前任务明确确认的有限修补通过私有 YAML 输入：

- 文件绑定 exact student SHA-256；
- 每项绑定唯一 `patch_id` 和 exact `source_object_id`；
- 保存 before/after、原因和 expected count；
- inventory、导入对象或命中次数变化时拒绝执行；
- 运行报告只暴露修补文件 hash、数量和文本 hash，不记录正文。

该机制解决已知学生源排版噪声，不是通用论文润色器，也不授权改写未确认内容。

## 4. 样式政策

已确认的长期产品背景是：学校模板通常不会覆盖学生论文所需的全部语义样式。未来需要一套
版本化的 DocFit 内置兜底样式库，并明确“学校样式优先、学校缺失时才使用内置样式”的规则、
升级兼容和审计证据。

该能力不属于当前切片。当前实现必须：

1. 只引用绑定模板中已经存在的 paragraph style；
2. 不创建、复制或偷偷补齐公式、题注、标题等新 style；
3. 模板没有专用公式样式时，以模板已有正文样式为基底；
4. 填入真实字段值时应用契约已有的字体属性，并移除灰色 placeholder direct color，让未显式
   声明的颜色继承模板样式；
5. 把缺失专用样式继续报告为产品能力空缺，而不是在本任务内形成隐式标准。

## 5. Claude Agent SDK 官方边界

本切片复用仓库锁定的 Claude Agent SDK 原生 session、Tool allowlist、hook 和 structured
output，不自建 Agent loop：
<https://code.claude.com/docs/en/agent-sdk/python>。

领域方法继续由现有 Skill 按需加载：
<https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>。

提取结果使用 JSON Schema structured output：
<https://platform.claude.com/docs/en/build-with-claude/structured-outputs>。

## 6. 状态和完成门

- `COMPLETE`：模板已 Human accepted，required target 全部有可靠来源，in-scope source 全部有
  明确处置，内容/package/视觉/Word-only 检查通过；
- `PARTIAL`：已生成安全候选，但存在 candidate 模板、缺失输入、未映射对象、生成区域未物化、
  validator 基线未知或 Word-only 待验证；
- `NEEDS_INPUT`：证据不足以安全写入，例如字段冲突、目标不唯一或质量修补已 stale；
- `ERROR`：输入变化、包损坏、内容守恒失败或运行环境错误。

验收至少证明：输入 hash 不变、source 全量记账、标量 evidence 可回指、Placement 无静默丢弃、
目标 tag 唯一、图片/公式/表/编号依赖闭包完整、输出只含模板 style、批准修补精确计数、逐页视觉
审计与确定性内容审计分开报告。

## 7. 当前真实样本结果

2026-08-09 确定性重放达到 `PARTIAL`：

- inventory 共 371 个对象：214 mapped、92 dependency-covered、65 unmapped；全量记账通过；
- 8 个标量槽和 2 个 block slot 被填入，11 个 required 槽保持 missing；
- 205 个已选顶层对象、6/6 图片、4/4 公式和 1/1 学生表进入候选，内容缺失计数为 0；
- 29 个安全空排版段移除，标题投影为 3/10/23，6 张浮动图转 inline 并绑定中英文题注，
  1 个学生表按版心归一；输出没有非模板 style；
- 9 项任务绑定质量修补各精确命中一次，正文之外没有隐式替换；
- 模板字段值格式化 8 个，摘要和关键词不再继承灰色 placeholder color；
- 固定产品渲染器输出 47 页，候选 SHA-256：
  `67832e592043f9e5b368bdb40f6693ba8a90b51df720fe5ebd2bf1c097617cd3`。

剩余门槛：模板/Human Gold 未验收、11 个 required 输入缺失、65 个 source object 仍显式
unmapped、生成目录尚未物化、TOC 需要 Microsoft Word 真实刷新、固定 OfficeCLI 同时拒绝原始
模板和候选且无诊断，因此新增回归只能是 `UNKNOWN`。
