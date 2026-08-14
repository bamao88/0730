# 正文模板提取与 Gold 准备规范

> **Historical design input / runtime sections superseded (2026-08-13).** 本文仍可作为正文/Gold
> 语义讨论材料，但其中 application-selected crop/work-item、候选 Skill 路径和 Template Workspace
> 文件布局不再有效。当前运行时权威见 `docs/status/active/docfit-school-extract-v2.md` 和 canonical
> `.claude/skills/docfit-school-extract/**`。Eval/Gold 规则继续由独立 Eval 设计维护。

> 状态：实施输入（Draft）
> 日期：2026-08-07
> 适用范围：学校论文模板的正文区域分析、Clean Template 候选生成、填写契约生成与 Gold 准备
> 不适用范围：学生论文内容填充、填写后的运行时行为、Template Extraction Eval 的评分实现

## 1. 目标

本规范要解决的问题是：给定一份学校原始论文模板，如何完整识别正文及相邻正文单元中
“必须保留的模板内容”“学生需要填写的内容”和“应删除的说明或示例”，并将其转换为：

1. 一份不破坏学校固定内容、结构、样式和对象功能的 Clean Template 候选；
2. 一份能够准确描述槽位身份、位置、字段映射和槽值样式的填写契约；
3. 一组与每次直接 Tool 调用绑定的机械回读和局部视觉反馈；
4. 经人工验收后，可作为 Template Extraction Eval 输入的 Gold 模板与 Gold 填写契约。

正文提取不能只把整段正文压缩为一个不透明的 `body.main` 或 `body.chapters` 文本框。
它必须表达学校模板实际规定的正文内容类型及其格式，例如各级标题、普通段落、图、表、
公式、引文和结论。否则，即使后续能够填入文字，也无法判断标题层级、对象边界和各类内容
样式是否提取正确。

本规范遵守以下核心原则：

- 主 Agent 拥有完整任务认知与访问边界，自主选择当前需要的对象/页面，不把 Registry 展开成
  机械待办；
- 语义内容树与 Word 中的物理槽位分开建模；
- 固定内容保留和可填写内容提取分别验收；
- 可见占位只用 `【】` 标识，不建立独立灰色占位样式协议；
- Gold 与产品 Actual 可以遵守同一规范，但不能只依赖同一实现互相证明正确；
- Eval 保持只读、独立，只消费产物，不参与模板生成或修复。

## 2. 本阶段要做的事情

正文模板准备包含六项工作：

1. **全局建模与按需观察**：主 Agent 先取得整份 inventory，再自主选择页面、对象和局部证据；
2. **语义映射**：由 Agent 把当前对象映射为代码内置的标题、段落、列表、图表、公式、引文等类型；
3. **代表单元选择**：从学校样例中选择一个覆盖实际独特样式的连续正文单元；
4. **直接物化**：Tool 一次建立可重复正文结构和内部槽，保留学校对象的实际样式；
5. **样例清理**：删除其他重复章节、说明和示例，并返回修改区域的即时反馈；
6. **发布与独立验收**：原子发布一份可填写 Word 和一份填写契约；Eval 与人工审查在产品运行时之外独立验证质量。

本阶段不负责：

- 从学生论文中提取真实内容；
- 把学生内容放入槽位；
- 验证长文本、空值、重复字段同步、条件增删或保存重开后的填写行为；
- 修改独立 Eval 的权重、评分器或通过标准；
- 自动把候选产物标记为 Human-accepted Gold。

## 3. 最终输出

| 产物 | 内容 | 消费者 | 是否可直接作为 Gold |
|---|---|---|---|
| `final-template.docx` | 保留固定模板内容并物化填写槽的可填写 Word | 产品填写链路、人工审查、Eval | 否，先是 candidate |
| `fill-contract.yaml` | 指导填写的契约：槽/区域到字段的映射、定位、必填性、基数、条件、空值/占位策略、样式、逻辑页与手工动作 | 产品填写链路、人工审查、Eval | 否，必须与模板一起验收 |
| Tool receipt / manifest / render | 每次直接编辑、机械回读、hash 和视觉证据 | 产品内部、人工 reviewer | 否，仅是内部证据 |
| reviewer 记录 | 审查人、结论、时间、模板与契约 hash | Gold 资格门禁 | 是 Gold 接受条件之一 |

每个学校的模板提取结果固定为两份用户可见主交付物：`final-template.docx` 和
`fill-contract.yaml`。二者原子发布，契约绑定最终 Word hash；缺少任一文件或绑定不一致都不算
成功。Tool receipt、manifest、hash、reviewer 记录、PNG/PDF 和其他报告是内部证据，不构成第三份
主交付物。填写契约由应用根据最终快照、Registry、Agent 已接受决定与 Tool 回读生成，不要求
Agent 手写 YAML。

候选产物只有在字段语义、槽边界、预期样式、protected/remove Truth 和完整性检查均完成人工
确认后，才能进入 accepted Gold。生成成功不等于 Gold 合格。

## 4. 项目文件目录与职责

下面同时列出现有目录和建议实现位置。带 `[待实现]` 的文件只是本规范提出的实施切分，
不是当前代码已经具备的能力。

```text
docfit_agent_SDK/
├── docs/
│   └── plans/
│       ├── docfit-body-template-extraction-spec.md       # 本规范：正文提取和 Gold 准备规则
│       ├── docfit-content-field-registry/
│       │   ├── DESIGN.md                                 # 字段注册表边界与治理规则
│       │   └── content-fields-v0.5.yaml                  # 当前正文规范字段快照
│       ├── docfit-school-extract-v2-candidate-skill/
│       │   ├── SKILL.md                                  # 当前学校模板准备 Agent 操作规则
│       │   └── references/                               # 清理、填写和对象安全参考
│       └── docfit-template-extraction-eval/
│           └── DESIGN.md                                 # 独立静态 Eval 顶层设计
│
├── src/docfit/                                           # 产品代码边界
│   ├── app/
│   │   ├── cli.py                                        # 当前 `docfit prepare-template` CLI 入口
│   │   └── prepare_template.py                           # 当前模板准备 Agent 应用编排
│   ├── template/
│   │   ├── workspace.py                                  # 当前模板查看、编辑、发布工作区
│   │   ├── object_mutation.py                            # 当前对象编辑与槽物化能力
│   │   └── semantic_types.py                             # 代码内置正文语义对象类型体系
│   └── tools/template_tools.py                           # 当前 Agent 可调用的模板工具
│
├── tests/                                                # 产品测试边界
│   ├── unit/template/                                    # 正文语义类型和对象变异单元测试
│   ├── contract/template_gate/                           # 当前模板工作区合同测试
│   └── integration/                                      # [待扩展] 真实学校模板准备回归
│
└── evals/template-extraction/                            # 独立、只读的 Template Extraction Eval
    ├── run_eval.py                                       # accepted Gold 正式评分入口
    ├── run_raw_source_sentinel.py                        # 原始模板对 clean Gold 的诊断哨兵
    ├── cases/                                            # 三校 candidate / accepted Gold
    ├── template_extraction_eval/                         # Eval 自有事实分析与断言实现
    └── tests/                                            # Eval 自有测试，不 import 产品代码
```

### 4.1 必须保持的代码边界

```text
学校原始模板
    │
    ├── 产品/Gold 准备侧：分析、判断、槽化、生成契约
    │         │
    │         └── candidate template + contract + preparation report
    │                           │
    │                           └── 人工验收后成为 accepted Gold
    │
    └── 产品实际运行：生成 Actual template + contract

accepted Gold + Actual
    │
    └── 独立 Eval：只读分析、全量对比、评分和报告
```

- 正文分析、槽物化和契约生成属于 `src/docfit/**` 或离线 Gold 准备工具，不能放入 `evals/`；
- Eval 不 import 产品实现，不调用产品 Agent，不修改 Actual 或 Gold；
- 产品实现不能把 Eval 的内部事实对象当作运行时依赖；
- Gold 可以使用相同规范和通用 Office 工具准备，但必须有独立人工 Truth 审查；
- 不能用同一生成函数同时生成 Actual 和 Gold，再用两者相等证明产品正确。

## 5. 正文的统一内容模型

### 5.1 语义层是递归、有序的内容树

论文正文首先是一棵保持顺序的内容树，而不是字段平铺列表：

```text
body.chapters
├── body.section(level=1)
│   ├── heading
│   ├── paragraph
│   ├── figure + caption
│   ├── body.section(level=2)
│   │   ├── heading
│   │   ├── paragraph
│   │   ├── equation + equation-number relation
│   │   └── table + caption + note
│   └── paragraph
└── body.section(level=1)
    └── ...
```

内容树负责表达顺序、嵌套和复合对象关系。Content Field Registry 负责跨阶段共享语义 ID。
两者用途不同：Registry 中的扁平字段是映射表面，不应替代完整内容树。

### 5.2 当前 Registry 中与正文有关的规范字段

| 内容类型 | 当前规范字段 | 说明 |
|---|---|---|
| 正文聚合容器 | `body.chapters` | 可承载完整递归正文；不能成为静态格式验证的唯一不透明槽 |
| 章标题至四级节标题 | `body.heading.outline1` … `outline5` | 每级独立识别，有各自槽值样式 |
| 普通正文段落 | `body.paragraph` | 保留正文内超链接、书签、批注、脚注、域、控件等对象语义 |
| 编号列表项 | `body.numbered_list_item` | 同时保留编号定义与段落格式 |
| 行内强调、行内引文 | `body.inline_emphasis`、`body.inline_quote` | 通常是段落内部范围，不应粗暴槽化整段 |
| 块引用 | `body.block_quote` | 与普通正文段落样式不同，应单独建模 |
| 图片与题注 | `body.figure`、`body.figure.caption` | 图片关系和题注是相关但独立的对象 |
| 表格、题注和表注 | `body.table`、`body.table.caption`、`body.table.note` | 保留合并关系、边框、底纹和容器样式 |
| 公式 | `body.equation` | 公式编号作为结构关系处理，不能混入公式语义文本 |
| 横向内容块 | `body.landscape_block` | 同时涉及节和页面属性 |
| 参考文献 | `references.entries` | 属于正文后的独立逻辑单元，但必须纳入模板完整性盘点 |
| 致谢 | `acknowledgement.body` | 同上 |
| 附录 | `appendix.title`、`appendix.body` | 标题和内容分别建模 |

当前 Registry 没有独立的 `conclusion.title` / `conclusion.body` 字段。结论与展望等具名章节复用
`body.heading.outline1` 和 `body.paragraph` 的同一套正文能力，不为它建立独立物理槽。若学校要求
必须包含该章节，应在 requirements/验证规则中表达；若未来确需跨阶段独立内容语义，再通过
Registry 治理新增字段。

### 5.3 聚合容器与物理槽的关系

长期填写链路可以把 `body.chapters` 作为递归结构化内容的容器。但当前静态 Eval 按物理槽检查
位置、字段和槽值样式，因此正文 Gold 至少需要为模板明确规定的不同内容类型提供可验证的
代表性物理槽，或未来扩展一种可表达子类型样式映射的结构化区域契约。

当前选择是：**一个 `body.chapters` 结构内使用细粒度代表成员**。最小完整集为章标题、一级节
标题、二级节标题和正文段落各一个；结构化区域保留成员类型与样式映射，不能退回单一不透明
正文槽，也不能为每个具名样例章复制一套槽。

## 6. 区域责任划分规则

责任划分必须细到段落内文本范围或完整结构化对象，不能只给整段贴一个标签。

| 责任 | 定义 | 常见内容 | 处理方式 |
|---|---|---|---|
| `protected` | 学校固定内容或维持文档功能所需对象 | 固定标签、标题、域、书签、页眉页脚、节属性、表格骨架 | 原样保留并全量比较 |
| `slot` | 学生未来需要提供或系统需要放置的内容 | 示例姓名、摘要正文、正文标题、正文段落、图表与公式 | 替换为稳定填写槽并声明契约 |
| `remove` | 明确不应进入最终论文的说明或冗余示例 | 括号说明、红色提示、重复演示段、操作指引 | 责任迁移完成后删除 |

例如原始模板中出现：

```text
摘 要：[这里填写中文摘要]（五号宋体，300—500字）{隐藏 TC 域}
```

责任应划分为：

```text
“摘 要：”                         -> protected
“[这里填写中文摘要]”              -> slot
“（五号宋体，300—500字）”         -> remove，但样式/长度规则先迁入契约或知识
“{隐藏 TC 域}”                    -> protected object
```

如果直接把整个段落槽化，会误删固定标签和隐藏域；如果直接删除整段示例，会同时丢失槽值样式
和内容类型证据。

### 6.1 分类优先规则

1. 能证明是学校固定内容或文档功能对象时，标为 `protected`；
2. 能证明是学生应提供的示例、空白或占位时，标为 `slot`；
3. 能证明是纯说明且其承载的规则已经迁移时，标为 `remove`；
4. 无法确认时先保留并记录 `unresolved`，不能为了“清理干净”而静默删除；
5. Registry 中没有合适字段时，保留原内容并记录未注册候选，不能映射到语义相近但错误的字段。

## 7. 到底需要提取哪些正文内容

正文提取的目标不是复制原模板中的每一个示例，也不是只留下一个大正文占位符，而是为学校
模板规定的每一种可填写内容能力保留至少一个可验证代表。

### 7.1 代表性槽的等价判断

两个示例只有同时满足以下条件，才可以合并为同一个 `cardinality: many` 的代表性槽：

- 规范 `field_id` 相同；
- 标题层级或逻辑角色相同；
- 有效字符、段落、容器和页面样式相同；
- 所处结构容器相同，例如都在普通段落或都在同类表格单元格；
- 对象家族相同，例如都是正文段落，而不是一个段落和一个公式；
- 填写和删除行为相同；
- 条件性、必填性和重复性相同。

若任一项不同，就应拆成不同槽或不同结构化子类型。典型必须拆分的情况包括：

- 章标题与一级节标题；
- 标题与标题后的正文；
- 普通正文与块引用；
- 图片、图片题注和图片说明；
- 表格、表题和表注；
- 公式与公式编号；
- 标题与正文；
- 同一字段在封面、声明页和正文中的不同物理实例。

### 7.2 一个代表格式，多次填充

模板中若连续放置多个仅内容不同、其余完全等价的示例，可以：

1. 保留一个代表性结构；
2. 将其物化为 `cardinality: many` 的槽；
3. 删除其余纯示例；
4. 在准备报告中记录被合并示例和等价证据。

“保留一个代表、删除其余示例”只适用于已经证明等价的重复块，不能跨标题层级、样式或对象
类型合并。

### 7.3 模板没有示例时

- 用户选定的规则材料明确要求、但 DOCX 没有示例时，可以基于有来源的要求补充候选槽，并记录来源；
- 只有常识推断、没有模板或学校规则证据时，不应悄悄创造 Gold Truth；
- 当前模板未出现的图、表、公式等类型，要在准备报告中明确写成“模板未提供”，不能把“没发现”
  当成“确认不需要”。

当前测试阶段以准确度为第一目标：来源是否官方只作为 provenance 和冲突判断信息，不作为
candidate/Gold 资格门或评分项。官方材料、历史模板、社区样本、用户指定文件和受控合成材料，
只要本次目标与适用范围明确并以 hash 冻结，都可以进入 Human 验收。未来若需要对外宣称符合
学校当前官方要求，应另设时效性和官方来源门，不能把该声明混入当前准确度结论。

## 8. 识别证据与稳定定位

正文判断应综合使用多类证据，推荐优先级如下：

1. 已有内容控件、书签、域和明确对象关系；
2. 大纲级别、命名样式、编号定义和节结构；
3. 继承计算后的有效字符、段落、容器和页面样式；
4. 固定前后锚点、章节上下文和对象邻接关系；
5. 标题编号、题注、公式号等文本模式；
6. 绝对段落序号、表格序号或页面号。

绝对序号只能作为辅助证据。模板一旦删除说明段或增减示例，序号就会整体漂移。

稳定定位器至少应能够表达：

```yaml
locator:
  story: document
  section_index: 3
  table_index: null
  paragraph_style: "标题 2"
  outline_level: 1
  left_anchor: "1.1"
  right_anchor: null
  occurrence: 1
```

对于行内槽，还必须记录或由物理内容控件准确表达起止边界。定位到正确段落但吞入冒号、单位、
括号说明或隐藏域，仍然属于边界错误。

## 9. 槽位身份与填写契约

Word 内容控件和填写契约必须形成双向闭包：模板中每个槽都能在契约中找到，契约中每个槽也
必须在模板中存在。

当前约定：

- `w:alias`：规范 `field_id`，表示这个槽承载什么语义；
- `w:tag`：在绑定 DOCX 内唯一的物理 marker 身份，通过 locator 与契约槽或区域一一对应；
- `slot_id`：填写契约中的稳定逻辑槽身份；它不要求与 `w:tag` 使用相同字符串；
- `w:id`：Word 内部标识，不作为跨保存或跨文档稳定身份；
- `cardinality`：表达 `one` 或 `many`，不能靠复制多个匿名控件表达重复性；
- `expected_value_style`：表达未来真实内容应采用的有效样式；
- locator：提供位置和边界的独立验证证据，不能只靠 `slot_id` 自证位置正确。

概念示例：

```yaml
slot_id: slot.body.section_body
field_id: body.paragraph
cardinality: many
marker:
  alias: body.paragraph
  tag: docfit.body.section_body
locator:
  story: document
  left_anchor: "1.1 二级节标题"
expected_value_style:
  font:
    east_asia: 宋体
    latin: Times New Roman
    size_pt: 10.5
    color: "000000"
  paragraph:
    alignment: justified
    first_line_indent_chars: 2
```

以上只说明必须表达的语义，不替代当前填写契约 schema；实施时应对齐已有 schema，而不是
平行创建第二套公共合同。

## 10. 样式规则：括号占位与学校实际样式

### 10.1 统一有效样式

正文分析和 Eval 都需要计算有效样式，而不是只读当前 Run 的直接格式。取值链至少包括：

```text
文档默认值
  -> 命名样式及其继承
  -> 段落和 Run 直接格式
  -> 表格/单元格容器格式
  -> 节和页面格式
```

统一事实至少应覆盖：

- 字符：中英文字体、字号、粗体、斜体、颜色、上下标、字距；
- 段落：对齐、缩进、行距、段前段后、分页控制、编号；
- 容器：单元格边距、边框、底纹、垂直对齐、合并关系；
- 页面：纸张、方向、页边距、分节、页眉页脚距离。

### 10.2 两种样式责任与一种文本标识

| 对象 | 比较目标 | 颜色约定 |
|---|---|---|
| protected 固定内容 | 原模板与 Clean Template 的同一受保护事实 | 必须保留原有效样式 |
| 槽及未来槽值 | 保留当前学校对象的字体、字号、段落和容器样式 | 颜色是否保留由 Agent 根据当前对象含义判断 |
| 可见占位文字 | 人工查看模板时能清楚识别槽位 | 只用 `【字段标签】` 文本边界，不附加颜色协议 |

槽占位符不使用 `w:showingPlcHdr`、灰色或底纹。若原模板的红/蓝颜色只标示说明或样例，Agent 在
当前物化操作中明确要求移除直接 `w:color`；Tool 仍保留字体、字号、段落和容器等实际学校样式。
若颜色是学校正式版式的一部分则保留。不能把“彩色”写成全文自动清理规则。

## 11. 结构化对象与边界安全

以下对象必须按复合单元分析，不能只处理表面可见文字：

- 图片、图片关系、题注和交叉引用；
- 表格、表题、表注、合并关系、边框和单元格样式；
- 公式语义、公式编号和二者的布局关系；
- 域、书签、目录收集标记、超链接和交叉引用；
- 页眉页脚、节属性、横向页面和分页控制；
- 条件区域、重复区域和嵌套内容控件。

安全规则：

1. 先完成结构化对象及其关系闭包识别，再编辑内部文字；
2. 域或书签不是“看不见的垃圾”，除非有明确证据，否则属于 protected；
3. 无法安全物化为槽的复合对象先保留并上报，不允许降级成纯文本；
4. 删除示例前，先把它承载的样式、定位、对象类型和填写责任迁移到代表性槽；
5. 清理前后必须检查 DOCX relationship、content type、bookmark pair 和字段边界闭包。

湖南农业大学中文摘要和中文关键词后的隐藏 `TC` 域就是典型 protected 对象。摘要或关键词
槽边界不得吞入或替换这些域。

## 12. 当前代码能力与待补能力

### 12.1 已有能力

当前产品代码已经提供：

- `docfit prepare-template` / `app/prepare_template.py`：当前模板准备入口和 Agent 编排；
- `template_view`：打开/恢复当前目标区域、导航到下一个物理区域，或按需搜索/聚焦对象；
- `template_registry`：按需查询规范字段；
- `template_edit` / `object_mutation.py`：编辑对象并物化槽；
- `template_publish`：发布最终模板产物；
- 学校模板提取 Skill：指导 Agent 对对象做 fixed / fillable / remove 判断；
- Content Field Registry：提供正文规范字段；
- 独立 Template Extraction Eval：对 Actual 和 accepted Gold 做 protected / slot 全量评分。

### 12.2 当前缺口

当前缺口不是再增加一个全文语义检查器，而是让现有直接 Tool 更适合 Agent 调用：

- 当前目标、父对象和必要邻接对象必须暴露判断需要的有效样式和直接颜色事实；
- 代码内置正文语义对象类型，Registry 查询当前对象时返回类型说明；
- Agent 只用 `register_body_member` 登记当前对象的正文角色；应用按文档顺序合并同一次决定中的
  多个登记，并在内部建立或扩展唯一 `body.chapters`，结构容器和成员数组不进入 Agent 合同；
- 应用从不可变原始视觉区域蓝图建立正文模块范围：具名样例区域由代码批量清理，只有通用
  `第 X 章（正文标题）` 区域可提供正文角色候选；
- Tool 保留每个学校对象实际样式，并按 Agent 的显式决定只清理直接颜色；
- 修改后立即回读结构和修改区域，让 Agent 判断是否继续，而不是依赖独立语义 checker。
- 文档版本、视觉游标和待复核区域作为应用 checkpoint 持久化；上下文分段或 backend 切换时启动
  新的 SDK 会话并恢复任务状态，不恢复包含旧图片的 transcript。

### 12.3 需要的脚本/模块及其定位

产品侧已经有 `docfit prepare-template`，因此不建立第二个 CLI，也不增加 Body Preparation Auditor。
产品运行时保持 Claude Agent SDK 原生循环，DocFit 只提供领域语义类型和直接文档工具。建议拆分：

运行生命周期遵循 Claude Agent SDK 官方边界：官方 Sessions 文档说明 session 会保存 prompt、Tool
调用、Tool 结果和响应，`resume` 会恢复完整上下文；同一文档也明确建议跨执行环境时，把所需结果
保存为应用状态并传给 fresh session，而不是搬运 transcript。因此模板任务持久化不可变 Word 版本、
视觉游标和待复核区域；每个有界上下文段仍使用 SDK 原生 Agent loop，但不 `resume` 含旧图片的会话。

- [Claude Agent SDK: Work with sessions](https://code.claude.com/docs/en/agent-sdk/sessions)
- [Claude Agent SDK: The agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)

| 模块 | 必需能力 | 不负责 |
|---|---|---|
| `semantic_types.py` | 定义 `body.*` 对象类型、允许的 Word 容器和重复关系 | 判断当前对象语义 |
| `workspace.py` | 提供当前对象事实、接收 Agent 映射、返回局部反馈 | 展开全文 Registry 待办 |
| `object_mutation.py` | 一次物化代表结构、保留样式、执行显式格式清理 | 全文是否漏项判断 |
| 独立 Eval / 人工审查 | 对最终候选做离线质量反馈和 Gold 验收 | 参与产品 Agent 运行时 |

建议逻辑接口：

```text
输入
├── 当前不可变 document_ref 与 object_ref
├── 当前对象图片、文字和必要样式事实
├── 固定版本的 Content Field Registry 快照
└── Agent 对当前对象的语义类型与编辑决定

输出
├── 一个新的不可变 Word 版本
├── 结构化 Tool receipt 与修改区域反馈
└── 最终原子发布
    ├── final-template.docx
    └── fill-contract.yaml（绑定 final-template.docx hash）
```

失败策略：

- 产品 Agent 不设置“全文责任覆盖率”发布门；Gold 晋升仍由独立 Eval 和人工审查决定；
- 存在未注册字段或不安全对象：保留原对象，报告阻塞项；
- marker 与契约不能双向闭合：禁止发布；
- 删除项没有规则迁移或证据：禁止删除；
- 只缺人工语义确认：可以生成候选，但不能变成 accepted Gold。

## 13. 验收维度与测试用例

### 13.1 产物验收维度

正文准备完成后，至少检查：

| 维度 | 核心问题 | 完成标准 |
|---|---|---|
| 当前修改范围 | Agent 选择的每个对象是否得到预期处理 | Tool 全部回读，非目标内容不变 |
| protected 内容 | 固定文字和对象是否仍在 | Gold 声明范围全量一致 |
| protected 结构 | 固定内容是否仍处于正确 story、节、段落、单元格 | 全量一致或有已批准迁移 |
| protected 样式 | 字符、段落、容器和页面有效样式是否改变 | 全量一致或有明确修复记录 |
| protected 对象 | 图片、公式、域、书签、表格关系是否完整 | 关系闭包完整，无降级 |
| 槽集合 | 模板规定的正文内容类型是否都被覆盖 | 无漏槽、无多槽、重复性正确 |
| 槽位置边界 | 槽是否位于正确结构且不吞固定内容 | 每个槽可稳定定位，边界精确 |
| 字段映射 | 每个物理槽是否选择正确规范字段 | 全部对齐 Registry 或显式 unresolved |
| 槽值样式 | 未来填入值的有效样式是否正确 | 每个槽都有可验证契约 |
| 占位显示 | 人工能否区分槽与固定内容 | `【字段标签】` 清晰且无额外灰色协议 |
| 渲染稳定性 | 页面、表格、分页和节是否被意外改变 | 关键页视觉复核通过 |

### 13.2 每个新增代码模块的最低测试规则

每一个新增模块或独立能力至少准备三个简单测试用例：

1. **正常样本**：最小合法输入能够得到正确结果；
2. **缺失/空输入样本**：关键事实缺失时得到明确失败或 unresolved，不能静默成功；
3. **局部变异样本**：只修改一个边界、字段、样式或对象关系，失败必须精确落在对应维度。

这三类是最低线，不替代复杂对象和真实学校样本测试。

### 13.3 建议的简单样本矩阵

| 能力 | Case 1：正常 | Case 2：缺失/歧义 | Case 3：局部变异 |
|---|---|---|---|
| 正文事实分析 | 章标题 + 正文段落 + 图片 | 空正文区域 | 删除图片 relationship |
| 责任分类 | 标签 + 示例值 + 括号说明 | 无法确认的彩色提示 | 槽边界多吞一个冒号 |
| 代表槽分组 | 两个完全等价段落合为 `many` | 无代表样式 | 同字段但字号不同，必须拆分 |
| 标题层级 | 章/一级节/二级节各一例 | 缺一级节标题证据 | 把二级节标题误映射为一级节 |
| 槽物化 | 一个块级段落槽 | object_ref 不存在 | 重复 `w:tag` |
| 契约闭包 | 模板槽与契约一一对应 | 契约缺一个槽 | `w:alias` 与 `field_id` 不同 |
| 样式契约 | 括号占位 + 学校实际槽样式 | 缺 expected style | 行距只改变 1 个属性 |
| 对象安全 | 保留成对书签和隐藏域 | 孤立书签 | 槽吞入 `TC` 域 |

### 13.4 至少三个端到端样本

1. **完全一致样本**：Actual 等于 accepted Gold，protected 和 slot 均应通过；
2. **原始模板哨兵**：把原始模板当 Actual 与 clean Gold 比较，protected 应覆盖全部保留事实，
   原始模板没有 Gold 槽标记时，Gold 中每个槽的集合、位置边界、字段映射和样式断言都应失败；
3. **单点破坏样本**：只修改一个 protected 字号并错映射一个槽字段，报告只能在对应 protected
   样式和 slot 字段维度失败，其他维度保持通过。

原始模板哨兵不是质量分数基准，而是验证 Eval 方向是否正确：保留层失败通常暴露 Gold 准备、
合法清理声明或 protected 对齐问题；槽层全失败证明 Eval 没有把“未提取的原始内容”误当成槽。

### 13.5 Human 产品核对面

Human 以产品可读核对表签署，不直接审核 YAML、OOXML 或重复的字体属性。核对面可按
相同字段语义、required/cardinality、fill/empty behavior 和样式来源归并规则组；机器附件
仍须逐槽/区域枚举覆盖，并将不同物理样式、复合字段、条件页、证据冲突和 unresolved
单独列为例外。

同一语义事实在封面、摘要或正文的多个物理实例可共享字段决定，但每个实例的物理定位、
学校样式和页面责任仍独立验证。规则组签署只降低 Human 重复工作，不降低 Gold 覆盖率。

## 14. 三校已确认的产品规则

> 产品确认：2026-08-13，产品负责人（当前用户）接受本节复合字段、学校章节角色、
> 逻辑页缺失策略和 schema 例外门。该签署是 candidate 重建的产品输入，不等于对尚未生成的
> v0.5 精确模板 hash、样式事实或全页 Word 证据已验收。

### 14.1 湖南农业大学

当前湖南农业大学 candidate Gold 的正文应收敛为一个 `body.chapters`，其中最小代表成员为：

| 结构成员 | 规范字段 | 结构内数量 |
|---|---|---|
| `member.body.chapter_title` | `body.heading.outline1` | 1 |
| `member.body.section_title` | `body.heading.outline2` | 1 |
| `member.body.subsection_title` | `body.heading.outline3` | 1 |
| `member.body.paragraph` | `body.paragraph` | 1 |

这 4 个成员表达章标题、一级节标题、二级节标题和正文样式，是**最低完整骨架**。它不代表图、
表、公式、引用、参考文献或附录已经自动完成覆盖。在 Gold 被接受前，仍需对原始模板做全量
盘点：原模板出现或学校规则明确要求的每一种不同内容类型，都必须有结构内代表成员、独立
结构化区域或明确的“模板未提供/不适用”结论。

显式编号深度由应用代码统一映射：`第X章` → `outline1`、`1 …` → `outline2`、
`1.1 …` → `outline3`。该映射同时约束 Registry 候选、结构门禁和目录层级，不依赖学校是否
复用同一个 Word 样式，也不交给 Agent 做三次独立语义猜测。

当前处理经验应固化为以下规则：

- 正文标题和标题后的正文必须拆为不同结构成员；
- 不同标题层级必须拆为不同结构成员；
- 结论等具名样例复用正文成员样式，不保留独立物理接口；其强制性由 requirements/验证规则表达；
- 中文摘要和中文关键词的内容槽不能吞入后面的隐藏 `TC` 域；
- 所有占位文字只用 `【】` 标识；槽继续保存学校要求的真实字体、字号和段落样式，颜色由 Agent
  根据当前对象语义显式保留或移除；
- 页面上下边距按原模板 56.7pt 保留，不能因清理正文示例而改变页面级样式；
- 当前 case 仍是 candidate，不能因控件数量和哨兵流程正确就自动视为 accepted Gold。

封面“年级、专业及班级”使用 `author.cohort_class` 复合显示值，不在来源不足时强拆。封面
“指导老师及职称”是一个复合物理区域，内部成员为 `advisor.name.zh` 和 `advisor.title`，
显示时保留模板规定的一个汉字宽空格；任一缺失都阻止最终交付。正文“指导老师”只
消费 `advisor.name.zh`，复用同一导师事实，不附加职称。

结论和致谢为必填；附录为选填。任务书、开题报告、开题论证记录、答辩记录、题目变更审批和
成绩表均为 `manual_only`：Template Gold 验收表单壳和顺序，不要求已完成手工填写；实际论文交付
仍必须提示未完成的手工动作。

### 14.2 南京农业大学

“第一章 文献综述”是必需的首章角色，“结论与展望”是必需的末章角色。两者都使用通用
`body.chapters` 及 `body.heading.outline*` / `body.paragraph` 成员；学校 `requirements`
验证首章/末章角色和内容存在性，不保留 `literature_review.*` 或 `conclusion.*` 专用字段、
槽或平行公共合同。

文献综述、结论与展望和致谢为必填；附录和相关学术成果为选填。选填页在 review draft 中保留
可见待确认提示，用户确认不适用后从 final 删除；必填页缺失阻止最终交付。

### 14.3 北京大学

实名评审专家名单是受 `review.mode` 控制的条件页。带二维码的版权声明和原创性/授权页是
正式提交阶段的外部必需资产；缺少时返回 `NEEDS_INPUT`，不得伪造或从普通文字生成。图目录和
表目录仅在存在对应图表时生成；无对应对象时 final 不保留空目录页。

附录/成果为选填，缺失时经用户确认从 final 删除；致谢为必填，缺失阻止最终交付。当前三校 Eval
snapshot 不自动继承历史 PKU 模板的 Human signoff，仍需对重建后的精确 hash 独立验收。

## 15. 完成定义（Definition of Done）

一所学校的正文模板准备只有同时满足以下条件才算完成：

1. Agent 从一个代表单元识别并物化当前学校实际出现的独特正文对象类型；
2. 当前修改范围内的 protected 内容未被误伤，合法变化有明确 Tool receipt；
3. 学校模板所需的正文标题、正文及已观察到的独特复合对象都有代表槽或结构化区域；
4. 每个槽都有唯一物理身份、正确规范字段、稳定位置边界、重复性和槽值样式；
5. 占位只用 `【】` 标识，未引入灰色、底纹或 `w:showingPlcHdr`；
6. 所有域、书签、图片、公式、表格、节和关系对象闭包完整；
7. 所有 remove 项都已完成内容、样式或规则责任迁移；
8. 模板与契约 hash、marker 和 locator 双向闭合；
9. 每个新增代码能力至少有三个简单测试，并通过真实学校端到端回归；
10. candidate 的产品可读核对面按规则组和例外完成字段、样式来源、边界和对象审查，机器附件证明逐槽/区域覆盖，reviewer 明确签署为 accepted Gold。
11. 已知 schema finding 已修复，或按《DocFit Eval 数据与 Gold》的证据要求证明为 validator false positive 并形成书面 exception。

## 16. 后续实施顺序

在不改变当前 Agent 和 Eval 边界的前提下，建议按以下顺序实施：

1. 在 `semantic_types.py` 固化最小正文语义对象类型体系；
2. 让当前页对象暴露 Agent 判断所需的紧凑样式事实；
3. 在 Agent Tool 合同增加单对象 `register_body_member`，由现有 `template_edit` /
   `object_mutation` 在应用内部一次性执行 `materialize_structure`，不公开结构流程控制参数；
4. 让发布 fill contract 记录外层结构、成员槽和学校实际样式；
5. 用合成样本完成每项至少三个测试；
6. 用湖南农业大学原始模板重新跑 candidate 准备和 raw-source sentinel；
7. 完成人工审查后，再把 candidate 状态提升为 accepted Gold；
8. 最后扩展南京农业大学、北京大学，验证规则不是湖南农业大学特例。

## 17. 关联文档

- `docs/plans/docfit-content-field-registry/DESIGN.md`：正文规范字段与跨阶段语义合同；
- `docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml`：当前 clean-break Registry 快照；v0.1–v0.4 仅用于历史证据重放；
- `docs/plans/docfit-school-extract-v2-candidate-skill/SKILL.md`：当前模板准备 Agent 行为；
- `docs/plans/docfit-school-extract-v2-candidate-skill/references/cleaning-and-fill-interfaces.md`：
  protected / slot / remove 和填写接口规则；
- `docs/plans/docfit-school-extract-v2-candidate-skill/references/boundaries-and-object-safety.md`：
  复合对象和编辑边界安全；
- `docs/plans/docfit-template-extraction-eval/DESIGN.md`：独立静态 Eval 的目标、指标和边界；
- `evals/template-extraction/README.md`：当前 Eval 目录、运行方式和三校状态。
