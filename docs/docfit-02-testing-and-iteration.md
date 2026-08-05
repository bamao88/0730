# DocFit 测试与迭代（02）

> 状态：最终方案
> 日期：2026-08-05
> 前提：测试与 Eval 是开发系统，不进入正常论文转换的运行路径。

本文件保留长期 Eval 设计。当前开发范围只要求 M0–M2 的单元、契约、集成和 live
产品门；M3 Skill/E2E Eval 扩展、真实样本资格验证、Gold 与人工交付复核已延期，需
新的用户批准计划。已经存在的 core runner 和 fixture 可以继续作为可选开发资产，
但不作为当前产品开发完成门。

M2 之后的核心转换优化属于非 Eval 工程轨道。它继续运行普通单元、契约、集成、
doctor 和 live 产品门，并使用同一合成链路做前后测量；这些检查不会因为 M3 延期而
暂停，也不构成 Skill/E2E Eval、真实样本资格验证或 MVP 结论。

## 1. 目标

测试与 Eval 只解决三个问题：

1. 当前转换五个 `docx_*` Tool、目标学校模板五个 `template_*` Tool，以及各自底层能力是否可靠；
2. 两个领域 Skill、模块化 Knowledge、可选只读 Subagent 和 Tools 的组合能否完成
   代表性模板提取与论文转换；
3. 一次修改是否修复目标问题，同时没有破坏已知正确行为。

DocFit 不建设通用评测平台。测试发现、并发、报告和 CI 使用现成测试框架；项目只维护论文领域的 fixture、样本和断言。

代码测试目录固定为：

- `tests/unit/`：不依赖 SDK 或真实 Provider 的纯逻辑测试；
- `tests/contract/`：按任务域注册的公开 Tool 契约、当前转换固定路由、主 Agent直接读取路径权限与受信任
  Bash/Write 配置、SDK
  Subagent 权限/上下文边界，以及两个后端各自职责范围内的契约测试；
- `tests/integration/`：真实 OfficeCLI、CLI 与薄转换壳集成测试；真实 SDK 和 Adobe API
  使用仓库外凭据作为独立 live 产品门，不混入默认 pytest。

当前最小 Eval 实现位于 `src/docfit/evals/` 与 `evals/`：专用 Python builder 生成一个
普通合成案例和四个单风险 DOCX，JSON case 描述第五个 Provider 伪成功风险、三个
Skill 范围及一个合成端到端合同。`docfit eval --suite core` 只运行确定性 Tool、Skill
静态边界和薄应用合同回归，并把调用数、页数、耗时和失败归因写入忽略版本控制的
`.docfit/evals/core/latest.json`。它明确不运行真实 SDK、Adobe official-service conversion、
授权/脱敏真实样本或人工复核；这些门必须单独留下实际证据。

## 2. 三类验证

### 2.1 Tool tests

Tool tests 不调用 Agent。当前测试直接验证 `docx_inspect`、`docx_edit`、`docx_render`、
`docx_visual_review`、`docx_validate` 的公开契约，以及 OfficeCLI、Adobe PDF Services API
的薄适配；06 第 6.9 节实施后，另行验证五个 `template_*` Tool，不要求两组 Tool 共享 schema。

两个后端不需要通过一套假想的可互换 Provider 契约。OfficeCLI 只通过 inspect、
edit、validate 和高频截图的职责契约；Adobe PDF Services API 只通过分页基线与候选验证
PDF 导出的职责契约。共同稳定的是五个公开 Tool 及其证据、错误
与安全语义。

重点覆盖；其中冻结模板 Interface 与源内容覆盖条目是 06 第 6.9 节实施后的新增门，
不是当前 M2 已通过事实：

- DOCX 能正确打开、无操作另存和重新打开；
- 段落、表格、合并单元格、图片、公式、脚注尾注、文本框、域、内容控件、页眉页脚和编号能够被发现；
- 样式继承、直接格式和最终生效值能够正确解析；
- 原始 run 与逻辑文本之间的字符映射正确；
- 不支持的可见对象被明确报告；
- 对象引用绑定输入 hash，失效引用被安全拒绝；
- 冻结模板槽位索引绑定精确模板 hash；模板字节变化后旧 locator 被安全拒绝，不能用
  页码、坐标或近似文字匹配静默重绑；
- 每个自动槽位在冻结快照内唯一可定位，并声明内容种类与基数；人工区域和无法表达的
  gap 显式存在，不能被伪装成自动槽位；
- 索引区分固定、填充、生成、重复、条件、人工和未决责任；生成区域不被压成缓存文字，
  重复区域不把示例数量冻结为实例基数；
- 跨 run 文本和占位符能被准确定位；
- 跨文档模板组合复制完整依赖闭包、重映射冲突 ID，并在任一操作失败时不发布部分结果；
- 一组编辑要么全部发布，要么全部不发布；
- 修改只影响目标对象，源文件保持不变；
- 可能漂移的多目标修改按安全顺序执行；
- Provider 报告成功但产物打不开或目标未变化时，Tool 返回失败；
- 编辑后从新文件重新取证，不相信 Provider 自报结果；
- 渲染缓存按输入 hash、Provider/SDK 版本、转换 profile、环境证据和参数正确命中与失效；
- `docx_render` 对 `baseline` / `edit_feedback` / `candidate_verification`、fidelity 和
  转换证据的声明符合 Provider 能力；
- Adobe baseline/candidate 固定为 `fidelity: official_service_conversion`，OfficeCLI
  feedback 固定为 `fidelity: approximate`；
- 固定路由矩阵生效：`edit_feedback` 只走 OfficeCLI，`baseline` 与
  `candidate_verification` 只走 Adobe PDF Services API；未知 intent 和任何后端选择参数被拒绝；
- Agent、Skill 或应用壳无法注入后端选择；任一固定后端失败时不会跨职责静默回退；
- Adobe 服务基线、CLI 编辑反馈和候选验证能够用稳定的 `render_intent` 区分；
- `baseline_render_ref` 被记录为新证据的 `parent_render_ref`，但旧页码和旧对象引用不会
  被当作当前文档事实；相同缓存键命中已有 render，不伪造新的 ref；
- `docx_render` 可以返回有大小限制的 contact sheet，让简单场景无需固定追加第二次
  Tool 调用即可开始观察；
- 页码只在对应 render ref 内有效，不同后端的同页码不会被自动关联；同一文档 hash 的页面元素可通过当前快照的 `object_ref`、节引用或文字锚点关联，文档 hash 变化后旧 ref 被拒绝；
- 页面元素映射的坐标系、页码、bbox、mapping quality 和 opaque `object_ref` 与当前 render 一致；
- `docx_visual_review` 只接受当前任务的有效 render ref，并返回与文档、页码和图片 hash 绑定的图片 content block；
- 五个公开 schema 不包含兼容 backend 会误解释的 `oneOf` / `anyOf` / `allOf`；动作
  专属必填关系由 Tool runtime 校验；
- SDK in-process MCP bridge 即使丢弃 `structuredContent`，Agent 可见的首个 text block
  仍是与完整结构化结果相同的 JSON；
- live smoke 的 CLI 集成测试只操作临时项目根；凭据或配置检查在任何 backend 可运行前
  返回 `NOT_READY` 时，不得删除此前真实 PASS 回执。只有确认存在可运行候选并开始新
  live 尝试后才先使旧回执失效；
- Tool 结果大小声明、SDK transport buffer 和视觉图片预算能够承载受控真实页面批次，
  不会在图片进入 Agent 前触发默认 1 MiB 消息截断；
- 主 Agent 可见 `Skill/Read/Glob/Grep/Bash/Write/AskUserQuestion/Agent`，五个 DocFit Tool
  仍可直接调用；`Read/Glob/Grep` 不自动批准且只接受 realpath 后位于批准根的路径；
  `Bash/Write` 自动批准且没有 DocFit 路径 hook；
- `~/.config/docfit/**`、`.env`、`.git/**`、凭据、其他任务、项目外路径、`..` 与 symlink
  逃逸均被拒绝；搜索根中的 symlink/敏感文件使整个搜索调用失败；
- 主 Agent 可调用 Bash/Write；Subagent 仍只看到 inspect + visual-review，不继承主
  Agent 的 Read/Glob/Grep/Bash/Write；
- 整页、裁剪、contact sheet 和 compare 模式的图片变换、页码、候选对象和元数据一致；
- `docx_visual_review` 不调用 Adobe PDF Services API 或 CLI，不产生新的 `render_ref`；派生视图只产生
  visual evidence/image hash，多次读取同一 ref 不构成新一轮；
- 修改后的文档不能继续使用旧 render ref 证明视觉结果；
- 单次图片页数和字节上限生效，Tool 不返回视觉 `pass` / `fail` 判断；
- 验证从源文件与最终文件重新读取事实；
- 验证重新生成或核对学生源内容清单，缺项、重复放置、无理由不放置和模板固定内容
  被改写均形成 blocking issue；每个源内容项必须有放置结果或显式原因；
- 占位符、有效格式、内容对象、package 关系、视觉审查覆盖和渲染警告返回清晰结果；
- 超时、凭据缺失、额度耗尽、服务失败和不支持对象都有可行动的错误。
- Adobe 大文件上传使用固定且可测试的 connect/read timeout；真实上传超时仍返回
  安全 provider failure，不泄露 SDK 原始错误或凭据；
- 只读源文件权限不会被传播到临时编辑副本；同一 backend route 超时后不会仅因轮换
  credential 重复等待同一模型路由；Kimi Claude Code 环境显式保持官方 high-effort
  Tool 上下文并关闭 Tool Search，HTTP 400 请求格式拒绝映射为不含原始错误体的安全码，
  且不会轮换同一 name/base URL/model 的 credential 重放相同无效请求。

Tool test 的基本标准是确定性、可重复、源文件只读、失败不产生伪成功产物。

当 06 第 6.9 节实施时，学校模板 Tool 的普通 unit/contract/integration 门至少覆盖：

- `template_observe` 的 snapshot/hash 不可变、旧引用拒绝、同文查询返回全部候选，且
  命名样式、直接格式、继承链、最终有效值、作用范围、缺失与冲突可区分；
- `template_mutate` 的六种删除模式分别证明应保留容器/网格/内容和应删除范围，歧义、
  fingerprint 失效或后置重读失败时不发布；
- 自动槽位唯一定位，scalar/paragraph stream/composite、基数、fill/generate/repeat/
  conditional、manual/gap 可表达，示例数量不成为重复基数；
- `template_compare` 能发现固定内容、表格网格、分节、页眉页脚、分页和槽位容器误伤，
  正确区分 expected/unexpected changes，并按风险返回原生 crop/整页/contact sheet；
- compare 不输出视觉 pass/fail；图片与 before/after hash、页码和图片 hash 绑定；
- `template_build` 只输出 candidate，拒绝重复 slot、旧 ref 和字段不完整；
- `template_freeze` 独立重读，拒绝 package/hash 不一致、槽位多命中、固定指纹变化、来源
  变化、旧 snapshot、缺少最终逐页审查、blocking finding 和不完整 bundle；失败不发布；
- `compile_mutation_plan.py` 对 operation ID、mode、ref/fingerprint 和槽位字段做确定性编译，
  拒绝页码/bbox/裸文本 locator；
- `compile_review_record.py` 保留 blocking finding，拒绝跨 hash 图片和缺少必需审查；
- `compile_artifact_spec.py` 拒绝重复 slot、缺失责任/基数/来源、隐式 manual/gap 和旧 ref；
- 三个生产 Skill scripts 输出 canonical JSON、失败不写部分文件，且不读取/修改 DOCX、
  不调用 Tool；消费方 Tool 对输出重新验证；
- 开发原型/fixture/debug 脚本不冒充生产决策编译器或产品完成门。

这些门不依赖 M3 Eval，也不因 M3 延期而延后；本段不表示当前实现已经通过。

### 2.2 Skill eval

Skill eval 使用固定任务、产品内置 Knowledge、当前任务学校材料和受控 Tool 结果，观察 Agent 是否：

- 在学校提取目标下用 `docfit-school-extract` 产出原子 frozen artifact；不填学生内容、
  不生成学校 Knowledge，也不把 candidate 当作 frozen；
- 在论文转换目标下让 `convert-thesis` 消费合格的冻结模板产物与学生 DOCX；不要求
  同一运行先触发提取 Skill，不依赖生产者名称，也不重新解释学校原始要求；
- `SKILL.md` 本身提供推荐操作方法、删除/槽位/样式/视觉判断标准和真实高风险规则；
  references 按四类可复用判断问题组织，不按论文部件逐一绑定，也不强制额外 index；
- 读取随当前产品发布的通用 Knowledge 版本；
- 由主 Agent 决定是否委派、如何划定分析范围、选择哪些 Knowledge 模块以及传递哪些
  任务证据；
- 在委派有收益时可以调用 `docfit-unit-analyst`，在简单、未匹配或复合范围中也可以
  直接或合并分析；
- 不使用固定页数、对象数、单元类型或其他复杂度阈值强制委派；
- 只把选中 Knowledge 模块及其 ID、版本、digest 和当前任务证据放入 Subagent
  任务包，不把父对话或无关模块当作已传递事实；
- 把 `status`、`confidence`、`evidence_requests`、`cross_unit_links` 和其他规定字段
  合并回主 Agent 判断；
- 在 Subagent 请求页面或其他证据时，由主 Agent 决定调用 render/inspect 并可选择
  再次委派，而不是让 Subagent 越权生成证据；
- 学校提取端只从当前任务模板、要求、示例和用户确认中形成学校事实；
- 不把当前任务提取出的学校规则、模板或精确参数写入长期 Knowledge；
- 只把 Tool 观测到的模板样式绑定到语义角色，不从 Knowledge、历史任务或常识生成
  未观测的样式值；
- 样式属性仍缺失或文字要求与有效格式冲突时，显式保留来源与未决/冲突；不从国家标准
  数值表、样式名、历史任务或常识自行补值；
- 使用 Tool 提供的事实，不直接猜测文档结果或修改 OOXML；
- 面对多个同文候选时读取全部候选、上下文、有效格式和视觉位置，不以首个文字匹配
  决定语义目标；
- 删除说明前迁移其中有效的格式、基数、生成或放置责任，并选择最小安全删除模式；
- 为槽位明确内容种类、基数、物理边界和 fill/generate/repeat/conditional 责任；不能
  唯一自动化时使用 manual/gap；
- 把语义判断写入可审阅 decision file，并通过 Skill scripts 编译 canonical Tool input；
  编译失败时补齐决定或证据，不手写 JSON 绕过结构校验；
- 调用 `template_compare` 后读取 expected/unexpected changes 和它直接返回的原生图片，
  由 Agent 解释视觉合理性；分节、页数或映射异常未解决时不继续冻结；
- 只在最终 hash 全页审查后 build，并只以 `template_freeze status: frozen` 作为发布依据；
- 修改前观察输入与模板页面图片，影响布局的修改后复核变化页和相邻页；
- 分页敏感且 Adobe 服务可用时，修改前建立输入与模板的服务转换分页基线；不可用时保留明确的能力缺口；
- 把 Adobe 页面当作视觉观察窗口而不是编辑身份，不用 Adobe 第 N 页直接定位近似 Provider 第 N 页或驱动 `docx_edit`；
- 修改过程中使用低延迟 CLI `edit_feedback` 观察受影响对象及邻近页面；当当前候选
  值得进行 Adobe 交付检查时请求 `candidate_verification`；
- 最终分批观察当前文档的全部页面，并把 visual finding 绑定到 evidence ref；
- 整页缩放不足以辨认小字、域结果或页边界细节时，继续读取绑定同一 render ref 的
  crop；可见应用错误标记、断裂域/交叉引用、未完成占位和截断内容必须作为 blocking
  finding 保留；
- 不把旧截图、近似渲染或结构检查当作当前页面已经视觉合格；
- 使用元素映射缩小编辑目标时仍验证 `object_ref` 前置条件，不把 bbox 当成 OOXML 定位器；
- 区分近似 `edit_feedback` 和 Adobe 官方服务转换；没有绑定当前文档且已被
  Agent 查看过的 candidate 证据时保留 `verification_gap`；
- 只提交 render intent，不选择具体后端；Adobe PDF Services API 失败时不把 OfficeCLI 预览
  当作最终真实性证据；
- 保护学生内容，选择破坏最小的修改方式；
- 根据错误语义重新 inspect、缩小范围、修复固定后端调用、询问或停止，不把后端切换当作首版恢复策略；
- 不消费 `committed: false` 或未通过后置检查的文件；
- 不在没有新证据时循环重试；
- 相同文档 hash 与相同渲染策略不重复调用 Adobe 转换；首次建立一次 baseline，上一
  candidate 可以作为下一 candidate 的 baseline ref，不额外调用 Adobe PDF Services API 制造轮次；
- 不把“第几轮”写入 Tool 状态或 Gold，也不把 baseline/candidate 的确切调用次数作为
  通用行为断言；只验证缓存、parent ref、后端路由和当前证据绑定；
- 在最终答复中如实说明产物、验证结果和未解决问题；
- `SKILL.md` 保留任务、输入输出、推荐方法、必要判断和真实高风险规则；可以说明稳定
  Tool 的职责和结果解释边界，但字段级 schema、错误码和机器实现不进入 Skill。

Skill eval 以可观察结果为主。除安全底线和必要先后关系外，不要求 Agent 复现固定工具调用序列。
也不把 Subagent 数量、调用顺序、并行/串行选择、论文单元枚举或“每个单元必须委派”
写成断言。复杂场景能够委派和简单场景允许不委派需要分别有代表性用例；二者都不能
升级成固定路线。

允许的行为断言只有：

```text
must       必须发生，例如按需读取产品内置 Knowledge 和本 Skill 所需的当前任务证据
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
  有效值、冲突或未决，且未决属性没有被静默写入文档；
- 必填模板内容或槽位已处理；
- 冻结模板 hash 与槽位索引绑定有效，自动槽位唯一，manual/gap 没有被隐式越过；
- 生成、重复、条件和未决区域保持各自责任，没有被降级为有限普通槽位；
- 模板固定内容未被未经证据修改，学生源内容清单中的每一项已放置或有明确不放置原因；
- 不应出现的占位符和说明文字已清理；
- PDF 或页面预览可生成；
- render ref 明确记录 intent、fidelity、Provider/SDK、转换 profile、环境可见性、parent ref 和可选元素映射；
- 同一文档 hash 的 Adobe 与 OfficeCLI 页面证据通过当前对象引用或锚点关联；跨编辑快照先重新 inspect，再通过新旧节、文字锚点或显式内容指纹对照，不假设相同页码表示相同内容范围；
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
- Adobe baseline/candidate 的真实 API 调用与缓存命中；
- 实际渲染页数、Agent 读取页数、重复读取页数和图片输入字节数；
- Token、成本来源、权限拒绝、用户追问和重试次数；
- 失败首先来自哪里，并能按 App/SDK、main Agent、Subagent、Skill、Tool、OfficeCLI、
  Adobe 聚合错误，定位相关文档 hash、`object_ref`、`render_ref`、evidence ref 与页码；
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
  wall time、CPU 与 RSS 都满足目标设计预算，不能用网络或 Adobe 延迟掩盖开销；
- 观测开关、失败注入和页面刷新都不能增加 OfficeCLI/Adobe Tool 调用；已有 Adobe cache
  命中路径不得因 O0 多消耗 Document Transaction。

上述测试锁定数据可信度与非干扰性，不要求 Agent 复现固定调用轨迹，也不属于延期的
M3 Eval。

每项优化只选择一个主要可量化目标，并在同一输入、同一固定路由和同一验证要求下
比较前后结果。首轮顺序固定为：先减少没有新增证据的重复 Tool 调用，再复用单次运行
内的解析与渲染结果，然后优化页面批次、crop/contact sheet 和图片载荷，最后处理
同一失败条件下的无效重试。任何优化都必须保持五个公开 Tool 路线与源 hash 完成门、固定
OfficeCLI/Adobe 职责、独立最终验证、当前 candidate 证据和错误语义。

这条轨道的回归门包括全量 pytest、ruff、mypy、build/lock、基础/provider/agent-smoke
doctor，以及受影响的真实合成产品 smoke。只有改动确实可能产生新的 Adobe cache miss
时才消费 live Document Transaction；已有缓存证据足以验证的路径不得为了测量重复调用
服务。测试失败表示优化不能合入，但不把普通测试重新命名为 M3 Eval。

## 3. 首批场景

第一批样本应来自真实论文风险，而不是按内部模块凑数量。

| 场景 | Tool test | Skill eval | 端到端 |
|---|---:|---:|---:|
| 学生内容正确放入模板槽位或正文区域，候选保持模板主干 | 是 | 是 | 是 |
| 冻结模板被修改后继续使用旧槽位索引或快照 locator | 是 | 是 | 是 |
| 槽位只有页码/坐标或多个近似命中，Agent 仍猜测性写入 | 是 | 是 | 是 |
| 人工区域或无法表达的区域被伪装成自动槽位 | 是 | 是 | 是 |
| 学生源内容缺章、缺对象或重复放置，但最终报告仍声称内容完整 | 是 | 是 | 是 |
| 学生内容不放置没有理由，或模板固定内容被转换过程改写 | 是 | 是 | 是 |
| 模板旧目录不被当作学生正文 |  | 是 | 是 |
| 空附录标题不会吞掉相邻内容 |  | 是 | 是 |
| 中英文图题及图片关系保持 | 是 | 是 | 是 |
| 表格、合并单元格和跨页表格保持 | 是 |  | 是 |
| 跨 run 占位符和格式说明被清理 | 是 | 是 | 是 |
| 域、内容控件、脚注、文本框和图片不静默丢失 | 是 |  | 是 |
| 页眉页脚、编号和节属性正确保留或修改 | 是 |  | 是 |
| 对象引用因前次修改失效 | 是 | 是 |  |
| Provider 伪成功被后置检查拦截 | 是 | 是 |  |
| 渲染器或字体差异影响分页 | 是 | 是 | 是 |
| Adobe 与 OfficeCLI 页数或分页边界不同，相同页码不能直接对应 | 是 | 是 | 是 |
| 近似渲染被错误标成 Adobe 交付转换证据，或 candidate 路由被静默降级 | 是 | 是 | 是 |
| render intent 被路由到错误后端，或固定后端失败后发生静默跨职责回退 | 是 | 是 | 是 |
| 页面元素 bbox 能定位到当前快照对象，失效或低可信映射不会驱动错误修改 | 是 | 是 | 是 |
| 大范围版式修改后 Agent 生成新 candidate，并只把旧 baseline/candidate 用作显式 parent 对照 | 是 | 是 | 是 |
| 封面溢出、意外空白页、孤行和图表错位能被视觉审查发现 | 是 | 是 | 是 |
| 修改后错误复用旧截图或漏审相邻页 | 是 | 是 | 是 |
| 学校文字要求与模板表现冲突 |  | 是 | 是 |
| 说明文字被删除，但其承载的格式、顺序或必填规则没有迁移 | 是 | 是 | 是 |
| 多个同构示例被误冻结为固定实例数量 | 是 | 是 | 是 |
| 源结构无遗漏无重复，但边界对象被分配给错误逻辑单元 | 是 | 是 | 是 |
| 目录等生成对象当前缓存正常，重新生成后样式或关系失真 | 是 | 是 | 是 |
| 复杂模板或论文范围可由通用只读 Subagent 分析 |  | 是 | 是 |
| 简单或不存在的单元不会被强制委派 |  | 是 | 是 |
| 复合前置结构可由主 Agent 直接或合并委派，不被塞入固定类型 |  | 是 | 是 |
| Subagent 缺少页面时请求证据，主 Agent 补证后可重新委派 |  | 是 | 是 |
| general-purpose、未知类型或 Subagent 写入尝试被拒绝 |  | 是 | 是 |

这些场景可以拆成最小合成 fixture，也可以组合进少量脱敏真实样本。

转换方向必须有独立回归：候选以目标模板为输入快照，学生源保持只读；最终文件保留目标
模板的固定结构与内容，同时把学生内容按已确认映射放入目标槽位或区域。仅证明“学生
副本中出现了模板内容”不能通过该断言。

## 4. Eval case

一个用例保持小而自包含：

```yaml
id: hunannongye-basic-001
skill: convert-thesis
task: 将学生论文转换为湖南农业大学格式
inputs:
  student_document: input/student.docx
  knowledge_version: v1
  template_artifact:
    clean_template: input/clean-template.docx
    template_sha256: ...
    slot_index: input/slot-index.yaml
assertions:
  - final_docx_opens
  - source_file_unchanged
  - required_text_preserved
  - source_inventory_closed
  - frozen_fixed_content_preserved
  - no_template_instruction_text
  - required_styles_match
manual_review:
  - cover_page
  - toc_pagination
```

学校提取用例可以附带原始学校材料；转换用例附带符合合同的冻结模板产物。两类用例
还可以包含产品 Knowledge 版本、结构化期望、少量人工确认的参考产物和失败说明。
学校材料和冻结模板产物都是 Eval fixture，不是运行时 Knowledge。

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
| 页面视觉 | 人工复核，必要时加图像差异辅助 |
| 非 Eval 运行性能 | 同输入/材料 hash、同版本与同验证门下比较 Tool/Agent/缓存/载荷指标 |

避免整份 DOCX 逐字节比较，也避免把一条完整 Agent 路径当成 Gold。

运行性能比较必须先报告可比性：输入、模板、要求、model/backend、SDK、App、Skill、
Knowledge、Tool 和 Provider 版本不一致时，标记为条件可比或不可直接比较。调用更少、
Token 更低或耗时更短本身不能替代最终证据和质量断言。

## 7. 失败归因

| 归因 | 典型问题 | 修复位置 |
|---|---|---|
| Skill | 任务边界、稳定产物、推荐方法、判断标准或高风险规则错误 | `.claude/skills/` |
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
- Adobe 转换调用数、缓存命中数、baseline/candidate intent 分布和 parent ref 复用；
- 重试次数、首个失败来源，以及按 App/SDK、main Agent、Subagent、Skill、Tool、
  OfficeCLI、Adobe 聚合的错误；
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
