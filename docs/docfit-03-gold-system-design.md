# DocFit Eval 数据与 Gold（03）

> 状态：最终方案
> 日期：2026-08-06

本文是后续 M3 质量工作的长期设计，不属于当前已完成的 M0–M2 产品开发范围。现有
合成 case 元数据可以保留；新增或确认 Gold、授权/脱敏复杂样本和人工复核结果，必须
在新的 M3 计划获批后进行。

模板提取静态产物 Eval 的 Gold 形态由
`docs/plans/docfit-template-extraction-eval/DESIGN.md` 进一步收窄：每个 case 以人工确认的
Gold 模板和 Gold 填写契约作为 Expected，并与已经生成的 Actual 模板和 Actual 填写
契约比较。Gold 填写契约承载 `protected`、`slot`、`remove` 区域责任、稳定定位、字段
映射和槽值样式契约；完整 Gold 模板只作为这些结果事实的确定性参照，不规定上游
Agent 路径。该顶层设计和独立 Actual—Gold 静态评分 runner 已实现，并由合成 fixture
验证两套断言、双视角/八分项评分、报告和输入错误语义；三校最终 case 目录也已物化。
但三校数据仍为 candidate、预期 `INPUT_ERROR`，尚未成为 Human-accepted Gold，学校
自比较和单错误回归也尚未启用。

完整转换 case 还需要 Human-confirmed Student Content Truth 与 Placement Truth。它们与
Template Truth 共同引用同一版 Content Field Registry 快照，却各自保留来源 locator、
目标 locator 和放置动作。Registry 是跨阶段研发语义依赖，后三者才是业务 case 的
Human Prepared Truth；它们不构成多层运行 Gold、阶段胶囊或新的在线数据系统。当前
Registry v0.1 与三校 candidate 定位文件尚待字段级 Human signoff，不能直接改名为 Gold。

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

对需要同时评测模板提取、学生内容提取、placement 与最终转换的完整业务 case，
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
则必须来自实际运行并经 Human 确认：

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

禁止模型仅凭自己的新输出自动更新 Gold。
国家级标准的样式值补全表不作为 Agent Knowledge 或 Gold 正文复制；Gold 只保存必要的
标识、版本、条款引用、digest 和人工确认事实。

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

- 多层 Gold 体系；
- Stage Harness；
- 阶段输入胶囊；
- exact/comparative replay；
- trajectory Gold；
- Subagent 数量、调用顺序、并行方式或单元到 Agent 映射 Gold；
- 自动 Gold 晋升；
- Gold catalog 服务。

如果需要单工具隔离复现，直接在 Tool test 中保存输入 fixture 和期望输出，不把它升级为 Agent runtime 协议。
