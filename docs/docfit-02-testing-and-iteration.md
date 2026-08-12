# DocFit 测试与迭代（02）

> 状态：最终方案
> 日期：2026-08-06
> 前提：测试与 Eval 是开发系统，不进入正常论文转换的运行路径。

本文件保留长期 Eval 设计。M0–M2 之后，用户已另行批准并完成 Content Field Registry、
Student 001/002/003 Extraction Gold 和独立 Student Content Extraction Eval 入口；这是一条
有界质量切片。Placement/Filling、完整 Skill/E2E Eval、真实样本资格验证和人工交付复核
仍未完成，因此不构成完整 M3 或当前产品运行门。

模板提取结果的静态 Actual—Gold 比较已经在
`docs/plans/docfit-template-extraction-eval/DESIGN.md` 中形成独立顶层设计。它把已经生成的
模板和填写契约作为 Actual，把人工确认的模板和填写契约作为 Gold，通过一套共享文档
事实分析分别评测模板保留与填写槽，并输出分项分数、总分和 `PASS/FAIL/UNKNOWN`。
该设计不运行或约束上游 Agent，只定义离线结果断言。当前独立工程已完成 schema/config、
合成 fixture、共享事实分析、断言、评分 runner 和报告，并物化三校 candidate case 的
最终目录；三校仍为 `INPUT_ERROR`，Human-accepted Gold 与学校回归尚未完成。这不改变
本文件对完整 M3、Student/Placement Eval 和真实样本资格门的判定。

完整质量闭环不能止于模板侧。当前 Student Content Extraction Actual 已可与其绑定的
Accepted Gold 独立比较；完整 M3 还必须继续评测显式 Placement Actual 和最终转换结果。
模板槽与学生内容共享
`field_id`，但模板目标 locator、学生 source locator 和 placement 动作分别比较；字段同名
本身不构成正确映射。Extraction Gold 当前分别绑定 accepted Registry v0.3/v0.4；三校
`field-alignment.yaml` 和 `template-spec.yaml` 仍是 candidate。这些都不是完整 M3 已通过的证据。

M2 之后的核心转换优化属于非 Eval 工程轨道。它继续运行普通单元、契约、集成、
doctor 和 live 产品门，并使用同一合成链路做前后测量；这些检查不会因为 M3 延期而
暂停，也不构成 Skill/E2E Eval、真实样本资格验证或 MVP 结论。

## 1. 目标

测试与 Eval 只解决三个问题：

1. 五个 DocFit Tool、OfficeCLI 与固定 LibreOffice V2 视觉链路各自承担的能力是否可靠；
2. 两个领域 Skill、模块化 Knowledge、可选只读 Subagent 和 Tools 的组合能否完成
   代表性模板提取与论文转换；
3. 一次修改是否修复目标问题，同时没有破坏已知正确行为。

DocFit 不建设通用评测平台。测试发现、并发、报告和 CI 使用现成测试框架；项目只维护论文领域的 fixture、样本和断言。

### 1.1 Evidence-gated development protocol

每个实现工作包在改代码前都必须声明当前证据 Gate。Gate 描述的是该工作包的合同与
证据成熟度，不是 DocFit 产品运行时状态，也不是 M0–M5 的别名；同一时刻，不同模块
可以处于不同 Gate。里程碑只消费已经通过的 Gate 证据，不能用计划、代码存在或口头
完成声明替代。

| Gate | 必须先回答 | PASS 证据 | 不能用来替代 |
|---|---|---|---|
| G0 Product contract | 用户价值、产品边界、所有者、公开面、输入输出、副作用、失败语义、非目标和延期 seam 是什么 | 用户批准的产品/架构合同，明确验收标准、未知项分类和停止门 | 候选计划、原型可运行、已有代码行为 |
| G1 Capability contract | 当前包支持哪些能力，哪些默认不支持，消费者如何调用和判断失败 | 版本化 schema/enum/fixture、稳定错误码、接口与所有权说明、可执行的合同自检或已定义的 acceptance contract，及用户要求时的合同批准 | 内部函数签名、未绑定 fixture 的示例、Agent prompt |
| G2 Component/Tool proof | 不依赖 Agent 时，组件与公开 Tool 是否按合同可靠工作 | 相关 unit、contract、integration 测试通过；真实 Provider 责任需要时有独立 live 证据；失败不发布伪成功或部分产物 | Agent 恰好成功一次、仅 mock 的端到端演示 |
| G3 Minimal vertical slice | 已证明的组件能否通过最窄真实入口形成完整产物与失败闭环 | 一个可重复入口、绑定输入与产物 hash/ref 的最小链路、独立完成检查、失败与回滚证据 | 分散的组件 PASS、人工拼接产物 |
| G4 Agent orchestration | Agent 是否正确选择、排序和消费已证明的能力 | Tool 选择与必要先后、ref/hash 传播、失败/追问处理、产物完成、报告与最终回复一致的 Agent/SDK 测试 | Tool 自测、内容质量主观判断、隐藏思维链 |
| G5 Quality Eval | 绑定精确产物的内容与交付质量是否达到已批准标准 | 独立 Eval 使用冻结 case/Truth/Gold 和 artifact hash，输出可归因结果；需要时包含授权样本与 Human review | 文件可打开、schema 合法、Agent 自评、未绑定产物的旧截图 |

Gate 依赖按工作包顺序成立：后层只能消费前层已经批准且可追溯的结果。G0/G1 发生变更
时，所有依赖该合同的 G2–G5 证据都必须做影响分析；接口、语义或 artifact identity 已失效
的证据必须重新运行，不能沿用旧 PASS。G2 通过前不得开始 G4；G3 不能用来绕过缺失的
组件合同；G4 成功不能证明 G5 质量。

未知项在进入实现前必须归入三类之一：`decide_now`、`bounded_experiment` 或
`defer_behind_interface`。有界实验必须预先写明问题、变量、预算、终止条件、可接受证据
和结果将更新哪个 Gate；实验结论在进入合同并获所需批准前仍不是稳定接口。延期项必须
有清晰 owner、接口边界和重新打开条件，不能变成下层的隐式假设。

实现发现前层合同缺失、错误或无法满足时，当前 Gate 结论为 FAIL，并返回受影响 Gate。
不得在下层静默扩大公开 schema、增加 alias/fallback、改变所有权或弱化失败语义。跨越
产品、公开合同、架构或里程碑边界必须获得用户明确批准；已经批准且保持合同不变的
实现包可以在 Gate 内自主推进，并按批准范围进入下一项证明。

每个 Gate 结束时，在对应 `docs/status/active/**` capsule 或其链接的耐久报告中记录
Gate Report，至少包含：

- Gate 与 PASS/FAIL 结论、合同基线（文档/版本/hash/commit）和批准来源；
- 实际改动范围与明确未改范围；
- acceptance criterion → test/evidence 的逐项映射；
- 执行命令、结果、未执行项及原因；
- 剩余 unknown、blocker、延期 seam 和下一 Gate 的进入条件；
- 00–06、模块设计、消费者、测试与 active capsule 的漂移检查。

`docs/status/active/**` 只保存当前 Gate、基线、证据、阻塞与下一步；它不定义 Gate 合同，
也不能覆盖已批准的 00–06 或模块设计。

代码测试目录固定为：

- `tests/unit/`：不依赖 SDK 或真实外部进程的纯逻辑测试；
- `tests/contract/`：五个公开 Tool/V2 ref 契约、主 Agent 直接读取路径权限与受信任
  Bash/Write 配置、SDK
  Subagent 权限/上下文边界，以及 OfficeCLI/LibreOffice 各自职责契约；
- `tests/integration/`：真实 OfficeCLI、Docker LibreOffice、三校视觉链路、CLI 与薄转换壳；
  真实 SDK 使用仓库外凭据作为独立 live 产品门，不混入默认 pytest。

当前最小 Eval 实现位于 `src/docfit/evals/` 与 `evals/`：专用 Python builder 生成一个
普通合成案例和四个单风险 DOCX，JSON case 描述第五个 renderer 伪成功风险、三个
Skill 范围及一个合成端到端合同。`docfit eval --suite core` 只运行确定性 Tool、Skill
静态边界和薄应用合同回归，并把调用数、页数、耗时和失败归因写入忽略版本控制的
`.docfit/evals/core/latest.json`。它明确不运行真实 SDK、Docker LibreOffice、
授权/脱敏真实样本或人工复核；这些门必须单独留下实际证据。

## 2. 三类验证

### 2.1 Tool tests

Tool tests 不调用 Agent，直接验证五个公开契约、OfficeCLI adapter、固定 Docker
LibreOffice renderer、Poppler 和 V2 Evidence Store。

至少覆盖：

- `docx_inspect` 的段落、表格、图片、节、页眉页脚、域、内容控件和 opaque ref；
- `docx_edit` 的前置条件、目标范围、复杂对象依赖闭包、原子发布和源文件只读；
- `docx_render` 只接受 `input_docx` / `overview`，应用注入 task root；旧 intent、
  provider、output directory、parent/focus 参数全部拒绝；
- render identity 绑定 DOCX hash、LibreOffice、container/font digest、locale 和 PDF 参数；
- 相同 identity cache hit，任何 identity 输入变化生成新 `render:v2:`；
- Docker 禁网、只读 root、cap drop、no-new-privileges、只读输入、独立 HOME/profile、
  timeout cleanup 和 PDF 完整性发布门；
- 页数/尺寸来自 LibreOffice PDF，文本 bbox 来自 Poppler，不依赖 OfficeCLI HTML；
- render 默认只派生联系表，不预生成全部高清页面；
- `docx_visual_review` 的 contact_sheet、pages、regions、compare、DPI、分页 cursor 和
  图片字节/数量预算；
- object selector 的 exact/contextual 映射，重复/无文字/不可映射对象返回候选完整页；
- text selector occurrence 与 image_bbox 反算 PDF 坐标；
- compare 只接受一致 renderer/font identity，分页变化按文字锚点对齐；
- 每个 `visual:v2:` 绑定 render、页码、selector/bbox、DPI、padding、变换和 image hash；
- MCP text JSON 与 structured result 一致，原生 image block 实际可见；
- `docx_validate` 核对当前最终 DOCX、V2 render、全部页面覆盖和 blocking findings；
- 旧 ref、越权路径、source hash 变化、renderer 失败和损坏 evidence 有稳定失败语义；
- 普通 Agent 与 `prepare-template` 共用同一视觉服务和 Evidence Store；
- 三校真实模板均完成“联系表 → 页面 → object_ref 局部图”，通用源码无学校分支。

外部 renderer 的退出码或“success”不能单独证明 Tool 成功；测试必须检查 PDF、页数、
hash inventory、当前文档绑定和原生图片。

### 2.2 Skill eval

Skill eval 使用固定任务、产品内置 Knowledge、当前任务学校材料和受控 Tool 结果，观察 Agent 是否：

- 在模板提取与论文转换目标下分别触发 `docfit-school-extract` 或 `convert-thesis`；
- `SKILL.md` 根据当前判断通过明确项目相对路径按需读取 references，不依赖 Skill 工具
  自动加载关联文件，也不使用 Bash 执行 references 或脚本；
- 读取随当前产品发布的通用 Knowledge 版本；
- 由当前 Skill 决定是否委派、如何划定分析范围、选择哪些 Knowledge 模块以及传递
  哪些任务证据；
- 在委派有收益时可以调用 `docfit-unit-analyst`，在简单、未匹配或复合范围中也可以
  直接或合并分析；
- 不使用固定页数、对象数、单元类型或其他复杂度阈值强制委派；
- 只把选中 Knowledge 模块及其 ID、版本、digest 和当前任务证据放入 Subagent
  任务包，不把父对话或无关模块当作已传递事实；
- 把 `status`、`confidence`、`evidence_requests`、`cross_unit_links` 和其他规定字段
  合并回主 Agent 判断；
- 在 Subagent 请求页面或其他证据时，由主 Agent 决定调用 render/inspect 并可选择
  再次委派，而不是让 Subagent 越权生成证据；
- 只从当前任务模板、要求、示例和用户确认中形成学校事实；
- 不把当前任务提取出的学校规则、模板或精确参数写入长期 Knowledge；
- 只把 Tool 观测到的模板样式绑定到语义角色，不从 Knowledge、历史任务或常识生成
  未观测的样式值；
- 样式属性仍缺失时，请求程序的确定性解析结果或显式保留未决，不在 prompt 中
  读取国家标准数值表后自行决定；
- 使用 Tool 提供的事实，不直接猜测文档结果或修改 OOXML；
- 修改前为输入与模板建立当前 V2 LibreOffice render；影响布局的修改后生成新 render，
  复核变化页、相邻页和必要局部区域；
- 把页面当作单个 render 内的视觉观察窗口，不用页码或 OfficeCLI HTML 坐标驱动
  `docx_edit`；
- 最终分批观察当前文档的全部页面，并把 visual finding 绑定到 evidence ref；
- 整页缩放不足以辨认小字、域结果或页边界细节时，继续读取绑定同一 render ref 的
  crop；可见应用错误标记、断裂域/交叉引用、未完成占位和截断内容必须作为 blocking
  finding 保留；
- 不把旧截图、旧 render 或结构检查当作当前页面已经视觉合格；
- 使用语义映射缩小编辑目标时仍验证 `object_ref` 前置条件，不把 bbox 当成 OOXML 定位器；
- 没有绑定当前最终文档、固定 renderer identity 且已被 Agent 覆盖全部页面的 V2 证据时
  保留 `verification_gap`；
- 不选择具体后端；LibreOffice 失败时不把 OfficeCLI 结构结果当成视觉证据；
- 保护学生内容，选择破坏最小的修改方式；
- 根据错误语义重新 inspect/render、缩小范围、修复固定 adapter 调用、询问或停止；
- 不消费 `committed: false` 或未通过后置检查的文件；
- 不在没有新证据时循环重试；
- 相同 render identity 不重复调用 LibreOffice，相同 view identity 不重复栅格化；
- 不把“第几轮”写入 Tool 状态或 Gold；只验证缓存、当前证据绑定和失败不回退；
- 在最终答复中如实说明产物、验证结果和未解决问题。

Skill eval 以可观察结果为主。除安全底线和必要先后关系外，不要求 Agent 复现固定工具调用序列。
也不把 Subagent 数量、调用顺序、并行/串行选择、论文单元枚举或“每个单元必须委派”
写成断言。复杂场景能够委派和简单场景允许不委派需要分别有代表性用例；二者都不能
升级成固定路线。

允许的行为断言只有：

```text
must       必须发生，例如读取产品内置 Knowledge 和当前任务学校材料
must_not   禁止发生，例如覆盖源文件
before     必要先后，例如修改前先检查输入
limit      成本或重复调用上限
```

不要保存或比较模型隐藏思维链。

### 2.3 End-to-end eval

端到端用例从用户任务开始，使用真实 Claude Agent SDK 配置和当前启用的 Tool Provider，验证：

- 最终 DOCX 存在、package 可独立解析且 OfficeCLI 可重新读取；
- 源文件未变化；
- 支持范围内的学生内容和对象仍存在且顺序正确；
- 目标学校关键格式断言满足；
- 对每个被确定的目标样式属性，可区分当前任务明确要求、模板观测、继承后
  有效值、适用国家级标准或未决，且未决属性没有被静默写入文档；
- 必填模板内容或槽位已处理；
- 不应出现的占位符和说明文字已清理；
- V2 LibreOffice PDF、联系表和按需页面/局部证据可生成；
- render ref 明确记录 fidelity、renderer/container/font identity、locale、PDF 参数与索引；
- OfficeCLI 对象通过当前语义锚点映射到 LibreOffice PDF；跨编辑快照先重新 inspect 和
  render，不假设相同页码表示相同内容范围；
- `docx_visual_review` 返回的图片实际进入当前 Agent 上下文；
- 如果使用 Subagent，`Agent` Tool 只启动 `docfit-unit-analyst`，其任务包只包含
  选中 Knowledge 与显式证据，返回结果可追溯到当前文档；
- `general-purpose`、未知 Subagent、Subagent 写入/渲染/验证/继续委派均被权限边界
  拒绝；
- live `path-tools` smoke 证明主 Agent 的直接 Read/Glob/Grep 仍按授权根执行，并在临时
  scope 中实际用 Bash/Write 访问 input 与任务外路径；任务外 canary 只证明直接 Read 被
  拒绝，不声称 Bash 无法读取。`denied-tools` 继续证明 Edit/Web 与未注册 Tool 不可执行；
- 主 Agent 仍是跨范围依赖、证据生成、`docx_edit` 和最终发布的唯一所有者；
- 修改前、布局变化后和最终交付前的视觉审查证据绑定正确文档版本；
- 最终全部页面已经分批视觉审查，高风险页面完成规定的 Agent 与人工检查；
- `visual-review.json` 的 finding、页码和 evidence refs 与当前 render 一致；
- 没有被忽略的 blocking visual finding；
- validation 没有被忽略的严重错误；
- Agent 最终回复与实际产物一致。

端到端 Eval 不生成阶段状态、调用轨迹 Gold、运行胶囊或 replay 协议。

### 2.3.1 字段、双侧提取与 Placement Eval

未来 M3 的一个完整业务 case 使用同一份、版本/hash 固定的 Registry 快照连接四类互补断言。
它们可以共享 fixture 和文档事实分析器，但失败必须归到发生问题的责任层。

**Registry 快照检查**验证：

- `field_id` 唯一且在同一 schema 版本中不改义复用；别名或拆分有显式版本迁移；
- `content_type`、语义 cardinality、`parent_field_id` 和 language 自洽，父字段不存在环；
- 值 schema/规范化规则只定义语义值，不混入某校显示样式；可选性与
  `one/many` 数量上限分开表达，不把 `optional` 当作唯一 cardinality 模型；
- 每个字段声明允许的值来源，以及学生提取是 `required`、`optional` 还是
  `not_applicable`；学生源、任务输入、系统生成和外部/人工资产不会混算；
- 模板、学生内容和 placement 引用完全相同的 Registry ID、版本和 hash；只比较路径名不算绑定；
- Registry 不含学校 locator、样式值或学生正文，也不被当作产品 Knowledge 或 Eval Gold；
- Registry 对未注册内容保持开放；伪造正式 `field_id`、静默丢弃未知项或使用
  `proposed_canonical_id` 自动 placement 是硬失败。

**模板提取 Eval**继续按专项设计比较 Template Actual 与 Template Gold，并补充以下
连接断言：

- 每个 slot/region 的 `field_id`、类型、基数、required/condition、fill/empty/placeholder
  policy 和目标显示/投影合同与 Gold 一致；
- locator 绑定模板 hash，包含 locator kind/value、part/scope、预期命中数和必要的
  Human fallback；复合槽保存 component locators，连续区域保存 start/end 边界；
- locator 唯一、边界不吞入 `protected` 内容，模板 hash 变化后旧 locator 被拒绝；
- 同一字段可对应多个明确 slot，三行标题等物理组件不能误计成三份语义字段；
- 跨模板 `field-alignment` 只能由各自 `template-spec` 派生和审计，不能反向覆盖某个
  模板的 target locator 真值。

**学生内容提取 Eval**把实际学生内容投影与 Human-confirmed Student Content Truth
比较，至少断言：

- 每个 in-scope 内容项的 `content_id`、`field_id`/未注册状态、类型、规范值/原始观测值
  或复杂对象引用、
  source locator、父项和顺序正确；source locator 绑定学生源 hash，页码只能作辅助证据；
- 简单文本比较规范化值；图、表、公式、脚注、文本框等比较源对象引用、结构事实和
  必要资产 hash，不能只比较转成的纯文本；
- 论文级共享事实与它在封面、摘要等位置的多个 occurrence 分开比较；多处观察冲突时
  必须保留各 occurrence 与冲突状态，不能任选一处生成伪 Gold；
- 章节、段落、图表等局部有序内容保持父子关系和顺序，不能因 `field_id` 相同而合并；
- Registry 中未注册、没有目标槽或不支持的可见内容分别进入
  `unregistered/unmapped/unsupported` 覆盖，而不是
  静默消失；Accepted Truth 必须给出确认字段、显式排除或 Human 责任；
- `generated.*`、评审/参考文献配置和二维码整页资产只按字段的 value-source policy
  评测，不要求从学生 DOCX 中虚构提取。

学生提取可以报告字段级 precision/recall/F1 和内容覆盖率，但以下情况是硬失败：必需
内容缺失、内容被截断或错序、复杂对象降成不可恢复文本、错误字段归属会导致错误放置，
或 source locator 与绑定 hash 不一致。能力不足且没有明确错误时为 `UNKNOWN`，不进入
通过率分子。

已实现的稳定研发入口是 `docfit eval-student-content`。它在提取 Agent 完成后读取一个
Actual 任务目录，并把 Accepted `student-content.gold.json` 作为独立 `oracle_only` 输入；
Gold 不进入 Agent prompt。入口自动发现 Actual 模型、全源 inventory 和 Agent evidence，
输出隐私安全的 `student-content-eval-report.json` 与面向研发/产品判断的 Markdown 报告。
Verdict 分开保留来源/Registry、源覆盖、字段语义、值忠实度、语义实例拆分/合并、内容
顺序、父子/题注关系和真实运行证据，任何硬失败维度都不能被总分掩盖。顺序唯一以 Gold
v2 的 `items[]` / `docfit-source-order/v1` 为权威，`field_results[]` 不参与排序。

**Placement Eval**比较当前任务 placement Actual 与 Placement Truth：

- 每条边引用有效的 source `content_id` 集合、共享 `field_id`、具体 target
  `slot_id/region_id`、action、projection/formatter、order、condition、status 和证据；
- 一对一、一对多、多对一、复合槽、连续正文、条件页、retain/exclude、generated 和
  external/manual 等模式均有代表性用例；
- 只有字段、类型、基数、目标唯一性和条件同时兼容时，系统才可自动确认候选；
  相同 `field_id` 遇到多个目标或多个来源时不得按文字相似或位置接近静默选边；
- 目标 locator 必须仍匹配当前模板 hash，source locator 必须仍匹配学生源 hash；写入前
  重新解析，不能把 placement ID 或字段 ID 当作 `docx_edit` 的物理定位器；
- 日期拆分、复合值组装、枚举到学校显示文字等 projection 保存输入、规则、
  输出和来源；没有证据的补值、不可逆丢失或错误组合均为硬失败；
- 每个 in-scope 学生内容都被 placed、retain、exclude 或 unresolved 覆盖，每个 required
  target 都被满足或有 blocking 原因；无声未映射、错误目标、错误顺序或越过 protected
  边界均为硬失败；`unresolved` 使必需结论为 `UNKNOWN`，不能自动晋升为通过。

最终转换 Eval 在上述三层真值之上，从最终 DOCX 重新取证：正确内容进入正确目标、重复
事实按确认规则同步、连续内容顺序和对象关系保持、条件/生成/外部资产行为正确、目标
有效样式满足模板合同，且没有额外或遗漏内容。高分不能掩盖字段映射错误、必需 placement
缺失、内容静默丢失或 stale locator。

Truth 文件默认是 `oracle_only`。只有专门评测“给定结构化合同后的执行能力”时，case
才能把其中一部分声明为 `subject_input`；否则模板规范、学生内容答案或 placement 泄漏
给被测对象会使结果失真。

### 2.4 非 Eval 的核心转换优化验证

核心转换优化不以扩大 Eval 集合为前提，也不能用性能改善替代质量验收。开始改变
调用策略、缓存、图片批次或重试行为之前，先按
`docfit-local-observability-design.md` 建立隐私安全的任务级事件与指标观测面，并把
稳定汇总写入扩展后的 `conversion-report.json`。至少能够回答：

- 当前运行和终态，以及真实 Agent turn、Skill、Tool 与 Subagent 的时间顺序；
- 整体耗时，以及每种公开 Tool 的调用数、结果状态、单次与累计耗时；
- Tool 的脱敏输入/输出摘要、`tool_use_id`、committed、错误码和相关证据 ref；
- Subagent 的父子关系、安全任务元数据、Tool、耗时、Token、返回状态和证据请求计数；
- OfficeCLI 解析次数与单次运行缓存命中；
- 真实 LibreOffice render execution 与缓存命中；
- 实际渲染页数、Agent 读取页数、重复读取页数和图片输入字节数；
- Token、成本来源、权限拒绝、用户追问和重试次数；
- 失败首先来自哪里，并能按 App/SDK、main Agent、Subagent、Skill、Tool、OfficeCLI、
  LibreOffice/Poppler 聚合错误，定位相关文档 hash、`object_ref`、`render_ref`、evidence ref 与页码；
- 指标中不包含论文正文、学校材料正文、完整页面图片、完整模型请求/响应、隐藏思维链、
  凭据值或未经授权的绝对路径。

观测页面只是薄应用壳的本地只读投影。它不启动或重试 Agent/Tool，不改变转换结果，
也不把内部事件记录升级为 Eval 轨迹 Gold、公共 replay 协议或新的运行时状态机。SDK
没有暴露的事件和 usage 必须显示 unknown，不能由最终文本反推。

O0 在页面开发前先建立以下非 Eval 产品合同测试：

- 用合成 SDK message/hook fixture 证明 Tool block `id` 与至少一个
  ToolResultBlock/hook `tool_use_id` 相等，多个来源出现时必须全部一致，并验证正常、
  失败、权限和追问事件；
- 用两个交错执行的 Subagent fixture 证明 `parent_tool_use_id`、子 Tool `tool_use_id` 与
  lifecycle `agent_id` 的桥接，不允许按 Tool 名或时间邻近归属 actor；
- 覆盖直接 ID 缺失、目标缺失、ID/hash 矛盾、重复和跨来源乱序，分别得到
  `partial/broken/conflict`、幂等去重和保留并行，而不是错误连线；
- 修改、删除或撤权本地证据，验证 document/object/render/evidence/page 的 hash/ref 检查
  会使证据变为 stale/missing/unauthorized/conflict；
- 在 prompt、用户问题/答案、Tool input/output、raw error、图片字节与路径中分别放入唯一
  隐私 canary，并扫描观测数据库、导出、应用日志和 `conversion-report.json`；任何 canary
  出现都使测试失败；
- 真实 SDK smoke 必须证明每次运行使用独立 `0700` `CLAUDE_CONFIG_DIR`、没有
  `SessionStore` mirror、正常退出立即清理；强制终止后只能由下一次 preflight 在固定私有
  父目录内发现/清理 owned 残留，不能记录 transcript path 或正文；
- 注入 projector/schema 失败、队列/观测配额满、观测库锁/写入失败、collector 未启动和
  UI 断开，
  验证转换最终状态、产物 hash、五个 Tool 结果和权限行为与禁用观测的基线一致，同时
  coverage/drop reason 可见；
- 单独让任务文件系统或共享卷耗尽，验证最终 DOCX/report 可以按原 storage failure 失败，
  不错误断言“采集失败不影响转换”；观测 writer 必须在设计低水位先停止；
- CLI 结束后历史证据为 unmounted。用户显式挂载时，v2 目录通过
  `run_id/task_ref/session/hash` 验证，错误目录为 conflict；v1 因缺少 run/task ID 最多为
  partial，Web 重启后不保留路径；
- 核心转换、云端运行和 O0 自动化完成门必须可在无头环境执行。证据挂载核心只测试
  注入的内存目录 capability、hash/ref 验证和无适配器时的 `unmounted` 降级；macOS 等
  原生目录选择器属于本地调试壳的可选 platform adapter，可有独立合成测试和手工 smoke，
  但真实 GUI 可用性不阻塞 O0，也不得使核心模块导入 AppleScript/GUI 实现；
- 对免登录直接打开、自动短期 session、Host、Origin、CORS、CSRF、GET 管理副作用、
  未授权 `task_ref`、path traversal、symlink 和挂载后替换建立安全测试；session/CSRF
  secret 不得进入 URL、日志、数据库或导出；idle/absolute expiry 后自动轮换会话并丢失
  会话内挂载，旧 CSRF 必须失效，服务端会话数保持有界；`/login` 不存在，非交互/无头
  环境可以启动 loopback 页面；
- schema v2 的随机 run/task ID、最终文档 hash 与 coverage/privacy 字段、v1 读取、v1
  unavailable/null、无效 v2、未知版本和 observation summary provider 异常必须有契约
  测试；summary 失败时基础 v2 conversion report 仍可写出；
- collector 恢复后只允许从用户显式挂载且验证通过的最终报告进行 summary-only 对账；
  缺少最终报告时终态保持 unknown，不生成虚构时间线；
- 用确定性 synthetic runner 验证同步 projector、事件/queue/run、数据库/保留、低水位、
  wall time、CPU 与 RSS 都满足目标设计预算，不能用外部进程延迟掩盖开销；
- 观测开关、失败注入和页面刷新都不能增加 OfficeCLI 调用或 LibreOffice render execution；
  cache-hit 路径不得因 O0 启动新容器。

上述测试锁定数据可信度与非干扰性，不要求 Agent 复现固定调用轨迹，也不属于延期的
M3 Eval。

每项优化只选择一个主要可量化目标，并在同一输入、同一固定路由和同一验证要求下
比较前后结果。首轮顺序固定为：先减少没有新增证据的重复 Tool 调用，再复用单次运行
内的解析与渲染结果，然后优化页面批次、crop/contact sheet 和图片载荷，最后处理
同一失败条件下的无效重试。任何优化都必须保持五个公开 Tool 路线与源 hash 完成门、固定
OfficeCLI/LibreOffice 职责、独立最终验证、当前 V2 证据和错误语义。

这条轨道的回归门包括全量 pytest、ruff、mypy、build/lock、基础/visual-renderer/
agent-smoke doctor，以及受影响的真实合成产品 smoke。已有缓存证据足以验证的路径不得
为了测量重复启动 renderer。测试失败表示优化不能合入，但不把普通测试重新命名为 M3 Eval。

## 3. 首批场景

第一批样本应来自真实论文风险，而不是按内部模块凑数量。

| 场景 | Tool test | Skill eval | 端到端 |
|---|---:|---:|---:|
| 学生内容正确放入模板槽位或正文区域，候选保持模板主干 | 是 | 是 | 是 |
| 模板槽与学生内容引用同一 Registry ID/version/hash，但各自 locator 分别绑定模板/学生源 hash | 是 | 是 | 是 |
| 同一字段有多个来源 occurrence 或多个目标槽时保留冲突/显式 placement，不静默配对 |  | 是 | 是 |
| 一对多、多对一、复合槽、连续正文和条件内容 placement 正确 | 是 | 是 | 是 |
| generated、任务输入和外部资产字段没有被误计为学生内容提取漏项 |  | 是 | 是 |
| 未注册或未映射的可见学生内容不会静默丢失 | 是 | 是 | 是 |
| 模板旧目录不被当作学生正文 |  | 是 | 是 |
| 空附录标题不会吞掉相邻内容 |  | 是 | 是 |
| 中英文图题及图片关系保持 | 是 | 是 | 是 |
| 表格、合并单元格和跨页表格保持 | 是 |  | 是 |
| 跨 run 占位符和格式说明被清理 | 是 | 是 | 是 |
| 域、内容控件、脚注、文本框和图片不静默丢失 | 是 |  | 是 |
| 页眉页脚、编号和节属性正确保留或修改 | 是 |  | 是 |
| 对象引用因前次修改失效 | 是 | 是 |  |
| renderer 伪成功被后置检查拦截 | 是 | 是 |  |
| 渲染器或字体差异影响分页 | 是 | 是 | 是 |
| OfficeCLI 页码/HTML 坐标被错误当成 LibreOffice 视觉坐标 | 是 | 是 | 是 |
| renderer/font identity 变化后错误复用旧 render | 是 | 是 | 是 |
| 固定 LibreOffice 失败后发生静默视觉回退 | 是 | 是 | 是 |
| semantic anchor 能定位当前对象，歧义/失效映射只返回候选页 | 是 | 是 | 是 |
| 大范围版式修改后 Agent 生成新 render，旧 evidence 只作历史对照 | 是 | 是 | 是 |
| 封面溢出、意外空白页、孤行和图表错位能被视觉审查发现 | 是 | 是 | 是 |
| 修改后错误复用旧截图或漏审相邻页 | 是 | 是 | 是 |
| 学校文字要求与模板表现冲突 |  | 是 | 是 |
| 复杂模板或论文范围可由通用只读 Subagent 分析 |  | 是 | 是 |
| 简单或不存在的单元不会被强制委派 |  | 是 | 是 |
| 复合前置结构可由主 Agent 直接或合并委派，不被塞入固定类型 |  | 是 | 是 |
| Subagent 缺少页面时请求证据，主 Agent 补证后可重新委派 |  | 是 | 是 |
| general-purpose、未知类型或 Subagent 写入尝试被拒绝 |  | 是 | 是 |

这些场景可以拆成最小合成 fixture，也可以组合进少量脱敏真实样本。

转换方向必须有独立回归：候选以目标模板为输入快照，学生源保持只读；最终文件保留目标
模板的固定结构与内容，同时把学生内容按已确认映射放入目标槽位或区域。仅证明“学生
副本中出现了模板内容”不能通过该断言。

用户内容相关 Eval 使用两类独立 Gold，详细合同见 `docs/docfit-03-gold-system-design.md`：

- 用户内容提取 Eval 以用户源 DOCX 为 `subject_input`，以 Human-accepted
  `student-content.gold.json` 为 `oracle_only`，只判断提取事实、结构、复杂对象、顺序、
  缺失和未决项；
- 模板填写 Eval 以已验收模板/填写契约和已验收 Extraction Gold 为 `subject_input`，以
  Placement Gold、Expected facts 和参考成品为 `oracle_only`，不重新运行内容提取；
- 完整端到端 Eval 才从用户源运行两段链路，并分别输出 Extraction、Filling 和 Final
  document verdict，不能用最终总分掩盖任一责任边界失败。

## 4. Eval case

一个用例保持小而自包含。以下示例是完整端到端 Case，因此 Student Content Truth 默认
仍为 `oracle_only`；独立模板填写 Case 必须改为引用 accepted Extraction Gold，并将其
声明为 `subject_input`：

```yaml
id: hunannongye-basic-001
skill: convert-thesis
task: 将学生论文转换为湖南农业大学格式
inputs:
  document: input/student.docx
  knowledge_version: v1
  school_materials:
    - input/official-template.docx
    - input/official-requirements.pdf
field_registry_ref:
  registry_id: docfit.thesis.content_fields
  registry_version: 0.1.0
  sha256: 9779d0272fc395245002184d43e8356b0722a6821e8ca0a36ced0db6d26d522d
  visibility: subject_input
truth:
  template:
    path: oracle/template-spec.yaml
    visibility: oracle_only
  student_content:
    path: oracle/student-content.json
    visibility: oracle_only
  placement:
    path: oracle/placement-map.yaml
    visibility: oracle_only
assertions:
  - final_docx_opens
  - source_file_unchanged
  - required_text_preserved
  - no_template_instruction_text
  - required_styles_match
manual_review:
  - cover_page
  - toc_pagination
```

用例可以附带输入、产品 Knowledge 版本、当前任务学校材料、结构化期望、少量人工
确认的参考产物和失败说明。学校材料是 Eval fixture，不是运行时 Knowledge。
Registry 是本例的固定语义输入；模板、学生内容和 placement Truth 的可见性
必须逐项声明为 `subject_input` 或 `oracle_only`；默认 Truth 为 oracle，且报告记录
Registry 及每个 truth 文件的 hash 与 schema 版本。

## 5. 样本组合

第一阶段只维护能够推动实现的最小集合：

- 1 个可公开的合成正常论文样本；
- 1 个结构复杂的脱敏或授权样本；
- 3–5 个由真实失败提炼的单风险样本；
- 1 份随产品发布的通用 Knowledge Package；
- 1 组合成的当前任务学校材料；
- 1 组五个 Tool 的公共契约 fixture。

第二所学校加入后，增加跨学校回归，检查通用 Skill 是否混入首校知识。

## 6. 结果比较

| 类型 | 比较方式 |
|---|---|
| 原始输入、Knowledge 文件 | hash 或 exact |
| 结构化分析结果 | 忽略时间戳后的 normalized compare |
| 对象集合 | set compare |
| 字号、页边距、坐标 | tolerance |
| Agent 判断与最终论文 | 关键事实断言 |
| Content Field Registry snapshot | registry/schema version/hash、ID/type/cardinality/source policy 的 normalized compare |
| 模板槽与学生内容 | 分别比较 target/source locator，再按 `field_id` 比较语义归属 |
| Placement | source content 集合、具体 target、action/order/condition/status 的 fact/set compare |
| 页面视觉 | 人工复核，必要时加图像差异辅助 |
| 非 Eval 运行性能 | 同输入/材料 hash、同版本与同验证门下比较 Tool/Agent/缓存/载荷指标 |

避免整份 DOCX 逐字节比较，也避免把一条完整 Agent 路径当成 Gold。

运行性能比较必须先报告可比性：输入、模板、要求、model/backend、SDK、App、Skill、
Knowledge、Tool 和 Provider 版本不一致时，标记为条件可比或不可直接比较。调用更少、
Token 更低或耗时更短本身不能替代最终证据和质量断言。

## 7. 失败归因

| 归因 | 典型问题 | 修复位置 |
|---|---|---|
| Skill | 领域判断、询问或工具使用指引错误 | `.claude/skills/` |
| Knowledge | 通用概念、识别方法、解释原则或处理模式错误 | 产品内置 Knowledge Package |
| 当前任务证据 | 学校材料缺失、来源冲突、适用范围或确认不足 | 当前任务输入、任务 fixture 或用户确认 |
| Tool | 解析、修改、渲染、图片证据传递、缓存或验证错误 | Tool 实现与 Adapter |
| Eval | 断言错误、样本失效或漏测 | `evals/` 或测试 fixture |
| App/SDK integration | 输入、路径、Subagent 类型白名单、工具隔离或 SDK 配置错误 | 薄应用壳 |

一次失败可以涉及多个资产，但不要用新的工作流层吸收定位困难。

## 8. 迭代闭环

```text
真实任务或 Eval 失败
  → 保存最小复现
  → 归因到 Skill / Knowledge / Tool / Eval / App
  → 修复对应资产
  → 为该问题增加断言
  → 运行相关用例和核心回归
  → 合入
```

每个重要修复至少留下一项自动化资产：

- Tool bug：单元或契约测试；
- Skill bug：Skill eval；
- Knowledge bug：通用方法单元测试或跨学校 Skill eval；
- 端到端漏检：结果断言或人工复核清单。

## 9. 发布门槛

早期版本只设四个门槛：

1. 五个 Tool 及当前启用 Adapter 的测试通过；
2. 两个核心 Skill 的结果与可选委派 eval 通过；
3. 使用当前任务学校材料的端到端样本通过且无内容静默丢失；
4. 人工打开最终 DOCX 并检查规定的高风险页面。

M2 后已批准先建设本地只读运行观测界面，当前已完成 O0.0–O0.7 的平台无关骨架、SDK
runtime privacy/report v2、字段级安全 projector、直接 ID 关联、覆盖维度和带来源指标，
以及有界 SQLite 历史、保留/删除与非阻断降级、Web 安全合同、会话内证据重挂载和核心
监控页面，并完成跨运行比较与 O0 总门。它服务核心转换问题定位和性能比较，不是 M3 Eval 平台。并发 runner、
实验平台、集中式
trace 服务和正式性能平台仍等真实规模与成本增长后再选择。

## 10. 最小指标

本节定义长期目标指标，不表示当前 M2 报告已经实现全部字段。M2 后优化切片先按
`docfit-local-observability-design.md` 落地逐事件本地观测和任务级汇总；M3 恢复后再
在其独立计划中记录 Eval 结果。

非 Eval 核心转换任务只记录：

- 当前/最终状态、总耗时、Agent turn、Skill、Tool 和 Subagent 数；
- 每个 Tool 的调用者、调用数、结果状态、单次/累计耗时、错误码和 committed；
- 主 Agent/Subagent 的层级、耗时、Token、成本来源、权限拒绝和证据请求；
- 解析次数、单次运行缓存命中、渲染页数、Agent 实际审查页数和图片输入字节数；
- LibreOffice render execution、cache hit、派生 view 数与复用；
- 重试次数、首个失败来源，以及按 App/SDK、main Agent、Subagent、Skill、Tool、
  OfficeCLI、LibreOffice/Poppler 聚合的错误；
- 相关 task/session/tool ID、文档 hash、opaque object/render/evidence ref、页码和本地
  证据可用性；
- O0 自身的 coverage、drop/queue high-water、projector P95/P99、事件/数据库字节、CPU、
  peak RSS、增量 wall time，以及 SDK transcript cleanup 状态；
- 同一可比样本在不同版本间的耗时、调用、缓存、页面、图片字节、Token、成本和错误差异。

未来 M3 Eval 轮次只记录：

- Tool 测试通过数与失败用例；
- Skill eval 与端到端用例通过数；
- 严重内容丢失或结构破坏次数；
- 需要人工澄清的任务比例；
- 按 Skill、Knowledge、Tool、Eval、App 的失败分布。

两类指标都只用于发现趋势和验证单项改动，不成为新的运行时状态体系，也不保存正文、
完整页面图片、完整模型请求/响应、隐藏思维链或凭据。监控历史不能作为 exact replay
或 Agent 路径 Gold。
