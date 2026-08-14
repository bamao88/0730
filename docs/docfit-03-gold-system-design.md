# DocFit Eval 数据与 Gold（03）

> 状态：最终方案
> 日期：2026-08-12

本文是 M3 质量工作的长期设计。M0–M2 之后，用户已另行批准 Content Field Registry、
Student 001/002/003 Extraction Gold 及其离线 Eval；其余 Template/Placement/Filling、
授权/脱敏复杂样本和外部人工复核仍需按各自质量计划推进。

模板提取静态产物 Eval 的 Gold 形态由
`docs/plans/docfit-template-extraction-eval/DESIGN.md` 进一步收窄：每个 case 以人工确认的
Gold 模板和 Gold 填写契约作为 Expected，并与已经生成的 Actual 模板和 Actual 填写
契约比较。Gold 填写契约承载 `protected`、`slot`、`remove` 区域责任、稳定定位、字段
映射和槽值样式契约；完整 Gold 模板只作为这些结果事实的确定性参照，不规定上游
Agent 路径。该顶层设计和独立 Actual—Gold 静态评分 runner 已实现，并由合成 fixture
验证两套断言、双视角/八分项评分、报告和输入错误语义；三校最终 case 目录也已物化。
但三校数据仍为 candidate、预期 `INPUT_ERROR`，尚未成为 Human-accepted Gold，学校
自比较和单错误回归也尚未启用。

完整转换 case 还需要 Human-confirmed Student Content Truth 与 Placement Truth。接受后的
Student Content Truth 构成 Extraction Gold；接受后的 Placement Truth、Expected facts 和
必要的参考成品共同构成 Filling Gold。它们与 Template Truth 共同引用同一版 Content
Field Registry 快照，却各自保留来源 locator、
目标 locator 和放置动作。Registry 是跨阶段研发语义依赖，后三者才是业务 case 的
Human Prepared Truth；它们不构成多层运行 Gold、阶段胶囊或新的在线数据系统。当前
Extraction 侧 Registry v0.3/v0.4 与三份 Student Gold 已签署；三校模板定位与 Filling
候选仍须独立验收，不能因 Extraction Gold 已接受而直接改名为 Filling Gold。

用户内容相关 Gold 固定拆为两类独立业务 Oracle：**用户内容提取 Gold** 回答“从冻结的
用户源论文中正确提取出了什么”；**模板填写 Gold** 回答“已验收的用户内容应如何进入
指定模板，以及正确结果是什么”。二者不得用同一份混合 Word 代替。模板自身的
Template Gold 继续作为独立上游事实，不并入这两类用户内容 Gold。

## 1. Gold 的定位

Gold 是人工确认过的参考结果或关键事实，不是独立系统。

它用于：

- 防止已知正确结果回归；
- 给复杂断言提供人工确认的参照；
- 保存真实失败修复后的预期。

它不用于：

- 规定 Agent 必须走哪条完整路径；
- 规定是否必须委派、Subagent 数量、并行/串行选择或固定论文单元目录；
- 复制运行时状态；
- 重放自定义工作流阶段；
- 替代当前 V2 页面查看和必要的人工判断。

Tool tests 使用普通 fixture 和期望值；Skill eval 与端到端 Eval 只有在事实断言不足时才保存 Gold 产物。

当前 core Eval 只提交 JSON case 元数据、合成 fixture builder 和人工交付页面 checklist；
生成的 DOCX/PDF/PNG、运行报告与中间产物均被忽略。它们不是 Gold，不能替代经过授权
或脱敏的复杂真实样本与人工确认结果。

## 2. 最小形式

### 2.1 用户内容相关 Gold 的固定拆分

| Gold 类型 | 被验收责任 | 身份键 | 不负责 |
|---|---|---|---|
| Student Content Extraction Gold（用户内容提取 Gold） | 用户源中的字段事实、章节、段落、图、表、公式、引用、来源定位、父子关系、顺序、缺失与未决项 | `student_source_sha256 + registry_id/version/hash + gold_revision` | 目标学校、模板槽位、目标样式、placement、分页和最终 Word |
| Template Filling Gold（模板填写 Gold） | 已验收内容进入指定模板的目标位置、动作、顺序、条件、样式来源、固定内容保留、缺失处理和最终文档事实 | `template_truth_revision + extraction_gold_revision + task/supplement_revision + gold_revision` | 重新解释用户源、重新做内容提取或修改 Extraction Gold |

这两类 Gold 是两个产品责任边界的独立 Oracle，不是运行阶段、轨迹或“多层 Gold”。同一
用户源只需维护一份与学校无关的 Extraction Gold；每个学校模板与用户内容的有效组合可以
维护一份 Filling Gold。模板版本、内容 Gold 版本或任务补充信息发生变化时，必须创建新
revision，不能只凭相同的 `school_id + student_id` 复用旧结果。

#### 2.1.1 用户内容提取 Gold

逻辑文件合同如下；物理存储可以引用已冻结的用户源文件，避免复制真实学生数据：

```text
student-content-extraction/<student-id>/
├── manifest.yaml
├── student-source.docx            # 或 manifest 中的 accepted source ref
├── student-content.gold.json
├── content-assets/                # 可选，只保存必须独立比较/搬运的复杂对象
├── product-review.md               # Human 唯一评审界面
├── review-assets/                  # 可选，供产品核对的图片/页面证据
└── review.yaml                     # 签署后的机器可读记录
```

Human 核对必须通过面向产品决策的 `product-review.md` 完成，不能把 YAML、JSON、content ID
列表或机器检查日志直接当作评审界面。产品文档至少展示：当前建议、用户可见/评测影响、需
确认的原文内容、复杂对象预览、可选择的接受/修改/阻止结论和最终签署区。`review.yaml` 只
保存文档签署后的结构化结论、审核人、时间和 hash 引用，不能替代产品文档。
标题/列表、题注边界等依赖文档结构的人工判断不得只展示孤立片段；至少同时展示所属上级、
前一条和后一条可见内容。默认分类还应优先保留用户显式写出的编号、列表等表达特征，除非
完整上下文或排版证据足以支持覆盖该特征。

`student-content.gold.json` 至少包含：

- `student_document_sha256` 与完整 `field_registry_ref`；
- `field_results[]`，对所绑定 Registry 快照中的每个 `field_id` 恰有一条字段级结论，
  记录该字段对学生源的适用性、`present/missing/not_applicable/unresolved/unsupported`
  状态和对应 `content_ids`；
- `items[]`，每项包含稳定 `content_id`、Registry `field_id` 或未注册状态、
  `value/content_ref`、`source_locator`、唯一 `source_order.block + source_order.inline` 和
  `status`；`items` 数组本身必须按该顺序严格递增；
- 适用时的 `parent_content_id`、`language`、`asset_refs`、`source_span` 和共享事实
  `source_occurrences[]`；每个 occurrence 同样保存自己的物理 `source_order`；
- 对所有可见源对象的覆盖记账：`mapped`、`covered_dependency`、`excluded` 或
  `unresolved`，禁止静默丢弃；
- Human review 的 revision、结论、审核人、时间和证据引用。

Extraction Gold 的主语义目录是它所绑定的 Content Field Registry 快照，不得先建立一套
候选自有字段/类型体系，再把 Registry 当作可选标签。具体约束如下：

- 已注册内容项的 `field_id` 必须精确等于 Registry canonical `field_id`；
- `content_type`、语义 cardinality、`parent_field_id` 和字段级 language 继承 Registry，
  Gold 可以冗余保存以便校验，但不得给出不同定义；
- `content_id` 只标识某字段的一份事实或一次有序内容实例。同一 `field_id` 可以对应多个
  `content_id`，但不能因此合并正文段落、标题、图、表、公式或参考文献的顺序和父子关系；
- `parent_field_id` 表达 Registry 中的语义关系，`parent_content_id` 表达 Student 002 等
  具体文档中的实例关系，二者不得混用；
- Registry 保持开放：工作候选中发现未注册语义时使用 `field_id: null` 与
  `classification_status: unregistered` 阻断物化，不得猜造正式 ID 或因对齐要求而丢弃；
  若属于通用内容，必须先升级 Registry，再同步 Extraction Gold、Template Projection 和
  Placement；Gold 候选验收时不得长期保留 `unregistered`；
- `missing` 只用于 Registry 明确声明学生源可提取的字段。`generated.*`、任务配置、外部
  资产或其他非学生源字段，必须按 Registry 的 value-source/student-extraction policy
  记为 `not_applicable`，不能误报成提取遗漏。

因此，Registry 不只是 Extraction Gold 的版本依赖，也是字段级覆盖率的分母和类型/基数/
关系校验权威；Gold 自有的 `field_results[]` 是 Registry 在当前学生源上的逐字段投影，
`items[]` 是这些字段在文档中的事实与 occurrence。两者缺一不可。

顺序是 Extraction Gold 的独立真值维度，不属于 Registry，也不能从字段分组推断：

- `items[]` 是内容实例及其顺序的唯一权威；`field_results[]` 只是可删除、可重建的字段索引，
  不得承担或覆盖顺序；
- `source_order.block` 绑定冻结 Word 主故事中首个来源 occurrence 的顶层 block，
  `source_order.inline` 表示同一 block 内已识别语义内容实例的稳定先后；两者共同构成完整、
  唯一、严格递增的总序；
- 标题、段落、图、题注、表、公式、列表和参考文献不能因 `field_id` 相同而按类型聚合后重排；
  分类、父子组装与 Agent 返回数组顺序都无权修改 `items`；
- 同一论文级共享事实在多处出现时只保留一份事实 `content_id`，该 item 使用最早 occurrence
  的顺序；所有原始位置与观察值继续按物理顺序保存在 `source_occurrences[]`，不能因事实合并
  丢失后续出现位置；
- `body.chapters` 等结构 span 只表达包含范围，在首个子项前打开并保存 `source_span`，不得被
  Filling 当成第二份可运输正文；
- Gold 验收必须机器证明 `items` 顺序完整、唯一、递增，逐 occurrence 顺序可回查冻结源，且
  删除后重建 `field_results` 不改变任何 item 或顺序。

Extraction Gold 必须忠实描述冻结用户源。人工批准的拼写、空格或内容修订应作为独立
authorized patch/evidence 记录；除非 Gold 合同明确区分 `observed_value` 与
`normalized_value`，否则不得把后续质量修订静默写回用户内容真值。

Extraction Gold 的最低验收门为：源 hash 和 Registry 固定；Registry 每个字段都有唯一
字段级结论，且类型、基数和关系闭包通过；普通字段与连续内容区域完成
Human 确认；图片、表格、公式、题注、引用等复杂对象的数量、顺序、父子关系和引用可
追溯；适用但源中不存在的字段明确为 `missing`，非学生源字段明确为 `not_applicable`；
全部 `unresolved` 有显式结论；隐私、存储、
CI 和外部处理权限已记录；manifest、review 与资产 hash 相互一致。
人工验收材料必须同时具备可读的产品核对表；仅有上述机器闭包或 `review.yaml` 不通过
Human acceptance 门。

Registry v0.1 已明确记录“value-source 和 student-extraction policy 未补齐”，继续仅供
已绑定的历史 case 使用。v0.2 在相同 54 个字段上补齐这两项政策；Student 002 当前绑定的
不可变 v0.3 进一步明确图表题注的规范值排除源类型标签和编号，Placement 由目标模板
重新生成编号。全文审计未发现需要新增的通用字段。v0.3 和 Student 002 的 Human 签署门
已于 2026-08-12 关闭：两者均已接受。该结论不晋升模板或 Filling Gold；
不得在任何 Gold 中私自按字段名前缀补造政策。

Student 002 的 18 个显式括号编号项按 2026-08-12 产品结论统一使用 Registry 既有的
`body.numbered_list_item`，不再依据文本长短拆成四级标题；该变化不需要升级 Registry，
Extraction revision、产品核对文档和模板 Placement 已同步更新并重新绑定 hash。

Student 001/003 扩样继续保持 Student 002/v0.3 的 accepted 事实不可变，并绑定已验收的
Registry v0.4。v0.4 不新增字段，只补齐同一语义图的一对多图片资产、只承载图片的
布局表、题注可缺失源编号、邻接优先的题注配对、Word 自动列表编号和 final-visible 修订/批注
来源合同。2026-08-12 产品负责人接受两份提取识别结果，并补充要求 Gold 显式保存识别内容
顺序；Student 001/002/003 均已升级为 Extraction Gold v2 顺序合同，要求 54 字段投影、全源
覆盖、0 unresolved、0 unregistered、完整唯一 `source_order` 和产品验收记录。

#### 2.1.2 模板填写 Gold

逻辑文件合同如下：

```text
template-filling/<school-id>__<student-id>/
├── manifest.yaml
├── template-truth.ref.yaml
├── student-content-extraction-gold.ref.yaml
├── task-and-supplements.yaml
├── placement-map.gold.yaml
├── expected-facts.yaml
├── expected-final.docx            # COMPLETE 实际交付基线必需；其他状态按 case 声明
├── evidence/                       # 可选，保存必要的页面/结构证据
├── product-review.md               # Human 唯一评审界面
└── review.yaml                     # 签署后的机器可读记录
```

Filling Gold 必须显式引用已验收的 Template Truth 和 Extraction Gold，不得从参考成品
反向覆盖用户内容真值。用户在原论文之外提供的姓名、日期等值属于
`task-and-supplements.yaml`，不能伪装成从用户源提取所得。任何内容合并、格式化、授权
改写、故意排除或一对多放置，都必须在 `placement-map.gold.yaml` 中有可审计动作。

`expected-final.docx` 是人工查看和复杂结构的强参考，但评分不得依赖 DOCX 字节完全相等；
稳定判断应提取到 `expected-facts.yaml`，至少覆盖内容守恒、placement、学校固定内容、
必填/选填处理、样式来源、复杂对象、目录、页码、分页、占位符和高风险页面。

每个 Filling Gold 必须声明预期业务状态：

- `COMPLETE`：存在经过目标 Word 环境与 Human 验收的可交付 `expected-final.docx`；
- `NEEDS_INPUT`：正确结果是请求缺失输入，不得把含必填占位符的候选冒充 final；
- `REVIEW_DRAFT`：仅用于保留已确认的历史或专项诊断基线，必须列出未关闭项，不能用于
  宣称产品完成。

#### 2.1.3 独立 Eval 与端到端 Eval

| Eval | `subject_input` | `oracle_only` | 主要 verdict |
|---|---|---|---|
| 用户内容提取 | 冻结的 `student-source.docx`、任务说明、允许的 Registry 语义 | `student-content.gold.json`、必要 `content-assets/*` | Extraction verdict |
| 模板填写 | 已验收模板/填写契约、**已验收 Extraction Gold**、任务补充信息 | `placement-map.gold.yaml`、`expected-facts.yaml`、`expected-final.docx` | Filling verdict |
| 完整端到端 | 用户原始输入、目标模板和任务输入 | Extraction Gold、Filling Gold 及其 Expected | Extraction、Filling、Final document 三个独立 verdict |

独立填写 Eval 不重新运行内容提取；这样失败可以准确归因到填写责任。端到端 Eval 可以运行
完整链路，但报告不得用最终总分掩盖某个上游失败，也不得因最终 Word 看似正确就跳过
Extraction verdict。

用户内容提取的正式离线比较入口为 `docfit eval-student-content`。它只在提取完成后读取
Actual 任务目录和单独提供的 Accepted Extraction Gold，自动绑定 Actual、inventory、
Agent evidence 与 Gold hash，并生成机器 JSON 与产品可读 Markdown。报告不得复制学生
正文；内容顺序、字段语义、值、覆盖、跨源实例分组和关系分别给出 verdict。候选/未签署
Gold、错误 schema、源或 Registry 漂移必须 fail closed，不能降级为宽松对比。

#### 2.1.4 现有手工资产的过渡映射与首个 pilot

在正式 Gold 存储位置确定前，现有手工准备目录按以下语义解释：

- `temp/manual-gold-preparation/gold/20-student-assets/` 对应 Extraction Gold；Student 002
  绑定 Registry v0.3，Student 001/003 绑定 Registry v0.4；三份包均为 Human-accepted
  `gold`，并使用 `source_order` v1 顺序合同；
- `temp/manual-gold-preparation/gold/30-cross-conversions/` 对应 Filling Gold；其中历史
  `REVIEW_DRAFT` 或已复核转换 Word 只证明该模板—内容组合的填写参考，不反向产生
  Extraction Gold；
- `temp/manual-gold-preparation/gold/10-school-assets/` 继续承载独立 Template Truth/Gold。

首个 pilot 固定使用 `student-002`。当前已完成历史提取结果的 Registry v0.3 规范化、全源
对象覆盖和填写映射同步；Extraction 已通过产品验收，Filling 仍是独立候选。下一门是以
Accepted Extraction Gold 为输入评审 Filling。湖南农大当前模板仍是诊断候选，因此填写候选的预期业务
状态保持 `NEEDS_INPUT`，不执行自动 Gold 晋升。

Student 001/003 扩样只以各自冻结源 Word 为内容真值，不使用历史转换稿补字段；Extraction 与
Registry 增量现已验收。后续仍需单独准备 Filling，不因已有跨模板转换 Word 而跳过 Filling
责任边界与验收。

### 2.2 完整业务 case 的组合形式

一个 Eval case 至少需要输入和断言。只有断言无法清楚表达时，才附参考产物。

```text
evals/e2e/hunannongye-basic-001/
├── case.yaml
├── input/
│   └── student.docx
├── expected/
│   ├── facts.yaml
│   ├── visual-findings.yaml # 可选，人工确认的页面视觉问题与 evidence 定位
│   ├── pages/               # 可选，只保存确有比较价值的参考页面
│   └── final.docx           # 可选
└── notes.md                 # 可选
```

`case.yaml` 示例：

```yaml
id: hunannongye-basic-001
skill: convert-thesis
knowledge:
  package_id: docfit-thesis-format
  version: v1
  content_digest: sha256:...
school_materials:
  - path: input/official-template.docx
    sha256: ...
  - path: input/official-requirements.pdf
    sha256: ...
task: 按目标学校要求转换论文
assertions:
  - type: docx_opens
    path: output/final.docx
  - type: text_preserved
    expected_from: expected/facts.yaml
  - type: style_fact
    target: heading_level_1
    expected: school_profile.heading_1
  - type: text_absent
    values: ["小二黑体加粗", "在此填写"]
  - type: visual_review_coverage
    expected: all_final_pages
  - type: no_blocking_visual_findings
manual_review: [cover_page, toc_pagination]
```

对需要同时评测模板提取、用户内容提取、模板填写与最终文档的完整业务 case，
`case.yaml` 固定外部 Registry 引用，并可在同一 case 下附一组 Human Prepared Truth：

```yaml
field_registry_ref:
  registry_id: docfit.thesis.content_fields
  registry_version: 0.1.0
  sha256: <fixed snapshot sha256>
  visibility: subject_input
```

```text
truth/
├── template/
│   ├── fillable-template.docx
│   └── template-spec.yaml
├── student/
│   ├── student-source.docx
│   ├── student-content.json
│   └── content-assets/        # 可选，只保存必要复杂对象资产
├── placement-map.yaml
└── reference-final.docx       # 可选；事实断言不足时使用
```

该依赖与这些 Truth 的最小责任是：

| 依赖 / Truth | 必须回答 | 不回答 |
|---|---|---|
| Content Field Registry snapshot | `field_id` 含义、类型、语义数量约束、父子/对象关系、语言、值 schema 和值来源/学生提取策略 | 学校 locator、样式、具体学生值或 case 评分答案 |
| Template Truth | `slot_id/region_id → field_id`、模板 hash、target locator、责任边界、fill/condition/style 和目标显示 policy | 学生内容来源和本次 placement |
| Student Content Truth | `content_id → field_id`/未注册状态、规范值/原始观测值或对象引用、学生源 hash、source locator、父子/顺序、共享事实 occurrence | 目标模板物理位置 |
| Placement Truth | source content 集合到具体 slot/region 的 action、projection/formatter、order、condition、status 和证据 | Tool 的 OOXML 私有 locator 或 Agent 路径 |

同一共享事实可以有多个 source occurrence，也可以填入多个模板槽；Gold 必须区分“一份
事实的多次出现”和“多个有序内容实例”。观察冲突时保留每个 occurrence 及冲突状态，
不得先任选一处成为唯一值。一对多、多对一、复合槽、连续区域、条件内容、生成字段、
任务输入和外部资产均由 Placement Truth 显式表达，不能只靠 `field_id` 相等猜测。

每份 Truth 保存 schema/version、内容 hash、互相引用的 digest、状态和 Human review；
同时记录完整 `field_registry_ref`，不在 case 内复制或改写 Registry。
路径相同但 hash 不同视为不同输入版本。Student Content Truth 及其资产包含学生内容，
继承源 DOCX 的隐私、存储、CI 和外部处理限制；不能当普通元数据写入公开仓库或日志。

每个 case 对 Registry 和 Truth 分别声明 `subject_input` 或 `oracle_only`。Registry
通常是可供被测对象读取的语义输入；默认 Template Spec、Student Content 和
Placement 答案只供比较器/Human 使用。若某个受控能力 Eval 允许被测
对象读取其中一部分，必须逐文件声明，且仍保留独立 Expected，避免 oracle 泄漏。

模板提取的 Agent 行为 Eval 仍只保存带来源引用的当前任务事实、冲突与不确定性；
模板提取的静态产物 Eval 则按上述专项设计保存 Gold 模板和 Gold 填写契约，比较最终
产物而不比较行为路径。同时提供模板和论文并要求交付转换的用例属于
`convert-thesis`。两类测试都可以断言 Agent 使用了当前模板证据且没有把它写入长期
Knowledge，但不保存固定调用轨迹、Subagent transcript、委派图或命名的中间阶段资产。

## 3. 断言优先

优先保存稳定事实：

- 转换候选以目标模板为主干，学生 DOCX 只作为只读内容来源；
- placement 明确学生内容进入的模板槽位或区域；“学生副本导入了模板节”不是等价结果；
- 模板与学生内容引用同一 Registry ID/version/hash，`field_id` 没有被改义或用作物理 locator；
- 每个模板 slot/region 的 target locator 与模板 hash 绑定，每个 student content 的 source
  locator 与学生源 hash 绑定，任一 stale/ambiguous locator 不会被静默采用；
- 学生内容的字段归属、值/对象引用、父子关系、顺序和共享事实 occurrence；
- 每个 in-scope 内容都有 placed、retain、exclude 或 unresolved 处置，每个 required
  target 都有内容或 blocking 原因；
- 生成字段、任务输入、外部/人工资产与学生源可提取字段按 source policy 分开评测；
- 标题和章节层级；
- 学生正文关键文本；
- 表格、图片、公式及其他支持对象的数量和必要顺序；
- 目标有效样式；
- 目标样式的属性级来源：当前任务明确要求、模板观测、继承后有效值、
  适用的版本化国家级标准或未决；
- 必填字段内容；
- 页面数量或允许范围；
- 不应残留的占位符和说明文字；
- 人工确认的溢出、遮挡、空白页、孤行、图表错位和页眉页脚异常；
- 视觉 finding 所对应的文档 hash、页码、render intent、fidelity、Provider、字体环境、
  parent render ref、evidence ref，以及可用的 `object_ref`、节引用或文字锚点；
- 需要人工检查的高风险页面。
- 可选 Subagent 返回中的事实、依赖、证据请求和最终被主 Agent 接受/拒绝的结论；
  不保存隐藏思维、完整 Subagent 历史或“正确调用了几次 Agent”的轨迹 Gold。

只有以下情况保存完整 `final.docx` 或少量参考页面图片：

- 需要人工查看复杂页面；
- 结构化断言暂时覆盖不了关键差异；
- 它是已经确认的真实交付基线。

完整文件和页面图片是辅助参照，不能自动覆盖事实断言。像素差异也不能单独证明版式
语义正确。页码只在对应 render ref 内有意义；OfficeCLI 对象页码或 HTML 坐标不能直接
认定为 LibreOffice 页面范围。renderer/font identity、DPI 或页面尺寸不同的页面不得直接
做像素 Gold 比较。比较两个 V2 render 时使用当前快照的 `object_ref`、节引用或文字锚点
对齐；文档 hash 变化后必须重新 inspect 和 render，并通过新旧快照的节、文字锚点或
显式内容指纹建立对照。Gold 同时保存 renderer identity、页数、bbox、
问题类别和人工结论等稳定事实。

## 4. 比较方式

| 模式 | 用途 |
|---|---|
| `exact` | 不应变化的源文件或 Knowledge 资产 |
| `normalized` | 忽略时间戳、随机 ID 后的结构化结果 |
| `set` | 标题、对象或问题集合 |
| `tolerance` | 尺寸、位置、页数等允许小范围变化的数据 |
| `fact` | Agent 结果和最终文档的关键事实 |
| `visual_fact` | 人工确认的视觉问题类别、页码、严重度和页面证据 |
| `manual` | 当前无法稳定自动判断的页面视觉 |

每条断言说明期望、实际值和证据位置。普通测试代码足够时，不设计新的断言语言。

## 5. Gold 的产生

Human Prepared Truth 和 Gold 都只能来自可核对的材料与 Human 确认，模型的
新输出不能自己成为真值。Registry 快照只能经 Human 字段审查后晋升；Template、
Student Content 和 Placement Truth 可以由 Human 直接对受控输入和格式书评审后冻结；
参考 `final.docx`、页面图片与运行结果 Gold
则必须来自实际运行并经 Human 确认。

当前测试阶段，来源是否“学校官方”只作为 provenance 记录，不是 Template Gold 的资格门或
评分维度。官方材料、历史模板、社区样本、用户指定文件和受控合成材料，只要目标文件及适用
范围被明确选择并以 hash 冻结，都可以用于准确度测试；Human 验收的核心是产物是否准确、完整、
可复现地对应这个选定目标。若多个材料冲突，仍记录来源权威性并由用户明确目标，不允许模型
自行拼接。未来若产品需要对外声称“符合学校当前官方要求”，再增加独立的时效性与官方来源门，
不反向污染当前准确度 Gold。

具体步骤：

1. 选定并固定 Content Field Registry ID/version/hash，对本 case 所用字段确认
   含义、类型、语义基数、父子关系和值来源/学生提取策略；
2. 冻结 Template Truth，逐槽/区域确认模板 hash、target locator、字段、边界和样式；
3. 冻结 Student Content Truth，逐项确认学生源 hash、source locator、内容/对象、顺序、
   occurrence 冲突和未注册项；
4. 确认 Placement Truth；字段相同只能生成候选，所有多目标、复合、条件、投影、生成、外部、
   retain/exclude 和 unresolved 情形由 Human 裁决；
5. 用当前 Skill、Knowledge 和 Tools 处理样本；
6. 运行确定性断言；
7. 查看 `docx_render` 随结果返回的有限预览，或通过 `docx_visual_review` 按需读取与
   当前文档绑定的已有页面图片；
8. 人工检查断言覆盖不到的关键页面，并确认或修正 Agent 的 visual findings；
9. 提取最少、稳定的事实到 `facts.yaml` 和可选 `visual-findings.yaml`；
10. 必要时保存参考 `final.docx` 或少量页面图片；
11. 记录确认人、日期、产品 Knowledge 版本与 content digest、Registry ID/version/hash、
   三类 Truth 的 schema/hash、当前任务学校材料
   hash、render intent、fidelity、Provider、字体环境、parent render ref、页面锚点和原因；
   若使用确定性样式补全，还记录每个属性的标准标识、版本、条款、适用性与规则集 digest。

Human 签署使用产品可读核对面，不要求审核人直接签署 YAML、OOXML 或重复的
字体属性。Template Truth 允许按“相同字段语义 + required/cardinality + fill/empty
behavior + 样式来源”归并为规则组签署，但机器核对表仍必须逐槽/区域枚举覆盖。
不同物理样式、复合字段、条件页、证据冲突和未决项必须单独列为例外；规则组签署
不允许隐藏未覆盖的物理槽。

已知 DOCX schema finding 默认必须修复。只有在能证明为 validator false positive 时才允许
人工例外：证据至少包含精确节点和规则解释、标准或独立工具依据、绑定当前 hash 的
Microsoft Word 打开—更新—保存—重开证据及书面 exception。“Word 能打开”本身不足以
豁免真实 schema 错误。

禁止模型仅凭自己的新输出自动更新 Gold。
国家级标准的样式值补全表不作为 Agent Knowledge 或 Gold 正文复制；Gold 只保存必要的
标识、版本、条款引用、digest 和人工确认事实。

用户内容相关 Gold 按责任顺序晋升：先冻结 Extraction Gold，再以其 revision 作为输入
制作 Filling Gold。已有人工确认的 `reference-final.docx` 可以通过“用户源—模板—成品”
三方对齐生成两类候选和 Human review queue，但不得一次签署后同时隐式晋升两类 Gold；
Extraction 与 Filling 必须各自拥有 review 结论、manifest 和 hash 绑定。

## 6. Gold 的更新

回归失败时先判断：

- 实现退化：修复 Skill、Knowledge 或 Tool；
- Gold 过时：人工确认新结果后更新断言或参考产物；
- 比较方式过脆：把逐字节比较收缩为事实断言；
- 输入、当前任务学校材料或产品 Knowledge 变更：创建新 case 或提升 case 版本。

更新时保留变更原因。版本控制历史足以满足当前阶段，不增加发布服务。

## 7. 合成样本与真实样本

合成样本适合验证单一风险：

- 重复或丢失段落；
- 跨 run 的说明文字；
- 表格、合并单元格、图片、公式；
- 域、内容控件、脚注和文本框；
- 旧目录、空附录标题和双语图题；
- 缺少摘要或参考文献；
- 占位符未清理；
- 对象引用失效和 Provider 伪成功。

真实样本适合验证组合效果和页面观感。

两者都应尽量脱敏。含真实学生内容的样本不得进入公开仓库；公开 CI 使用人工构造或获得授权的文件。

## 8. 明确不采用

当前架构不采用：

- 多层运行/轨迹 Gold 体系；用户内容 Extraction Gold 与 Template Filling Gold 是两个
  产品责任边界的业务 Oracle，不属于本条所禁止的多层 Gold；
- Stage Harness；
- 阶段输入胶囊；
- exact/comparative replay；
- trajectory Gold；
- Subagent 数量、调用顺序、并行方式或单元到 Agent 映射 Gold；
- 自动 Gold 晋升；
- Gold catalog 服务。

如果需要单工具隔离复现，直接在 Tool test 中保存输入 fixture 和期望输出，不把它升级为 Agent runtime 协议。
