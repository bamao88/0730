# 模板语义判断前缺少图片视觉证据 — 2026-10-02

状态：**图片证据缺口已修复；真实封面双文件已生成并完成图片专项验收。完整模板的人工产品签收仍待进行。**

模块：模板提取。首次偏离点：`unit-boundary` 已接受之后、post-unit `SemanticJudgmentSet` 提交之前的证据供给。

## 产品问题

真实学校 Word 封面含图片，产品 Agent 负责结合学校原件判断图片的用途、保留义务及其与周围版式的关系。但当前 post-unit 阅读材料只把图片呈现为 `entry_type: picture`、空文本和容器关系；本阶段既没有给出图像画面，也不允许 Agent 调用视觉取证。Agent 因而被要求对没有看见的图片作语义判断。机械角色/字段检查即使通过，也不能证明图片被正确识别或最终保留。

学校语义仍由 Agent 判断；Harness/Tool 负责把原始图片或可辨认的页面区域作为可访问、可定位的证据提供给它，不代替它判断“这是校徽”或预设应选的 role。

## 已确认的本轮证据

- 真实输入：`tests/manual-diagnostics/input/school-template-nannong-undergraduate.docx`，SHA-256 `e201f1fd80cc264b0aa58795fff3ce0b40cf42303df33ebffc461dda31fde92c`。本轮任务：`temp/template-diagnostic-20261002-njau-full/`。原件封面在 Microsoft Word 中能看到两张图；本轮尚未留存可复核的 Word 页面截图。
- 初始清单与封面阅读包中，两个图片源条目 `source-entry-05686695b50646cfb45c11ee`、`source-entry-be9bd13e6f9a0ffeb8dde62e` 的 `entry_type` 为 `picture`、`text` 为空。阅读包提供其表格/段落祖先和顺序，没有图片像素或内容描述。证据：本轮 `work/.docfit/initial-source-inventory.json`、`work/.docfit/harness/object-inventory.json`。
- `TEMPLATE_SEMANTIC_EVIDENCE_FOCUS` 仅开放 `document_map`、`unit_evidence_packet`（`src/docfit/tools/surface.py`）；post-unit Agent 配置与提示词明确禁止 render/visual review（`src/docfit/app/prepare_template.py`）。通用 Tool 虽实现 `render_snapshot`、`visual_page` 和图像 content blocks（`src/docfit/tools/service.py`），该阶段的 Agent 无权调用这些 focus。
- 本轮封面批次调用记录仅见 `unit_evidence_packet`，没有视觉取证。首轮提交把表格、图片和空白布局载体判为 `body_structure` 且未给 `field_id`，被机械检查退回；反馈后改为 `style_only` 并通过该批次的局部机械检查。证据：`work/.docfit/tool-call-audit.jsonl`、`work/.docfit/harness/semantic-revisions/00000002.json` 至 `00000008.json`。

这些证据证明**视觉输入缺口**和**首轮机械退回**，不能单独证明缺图是每一个错误 role 的唯一原因，也不能证明修订后的图片语义、DOCX 物化或产品产物正确。表格与空白载体有其他结构线索，应分别评估，不与图片问题合并归因。

## 责任层与边界

- **主要责任：Harness/App 的阶段证据路由与 Tool 的 Agent 可见视觉证据接口。** 现有 `unit_evidence_packet` 把图片保留为结构条目，却未提供内容；同一 Agent 阶段又限制视觉 Tool。需要在判断发生前补齐可用证据，而不是把 `picture` 映射成学校语义。
- **产品 Agent：** 看到图片及相邻学校上下文后自行判断内容用途、role、字段及保留义务；证据仍不足时表达 `needs_input`。不要求它管理图像文件、render ref、Word locator 或执行账本。
- **Harness 机械检查：** 可以检查提交形状、字段兼容与覆盖，但不能把 `body_structure → style_only` 的合规修订当作“已正确识别图片”。
- **与既有缺陷的关系：** `template-execution-scope-audit-20260924.md` 中的图片删除范围问题发生在判断后的 Tool 执行层。本缺陷发生在判断前；二者可同时存在，不能互相替代。

## 修改目标

让 post-unit Agent 在需要判断真实图片时，能按需查看与当前学校输入、当前 unit、原 `source_entry_id` 对应的**实际图像画面**，并结合相邻文字与页面布局作判断。证据可以是保真原图或足够辨认用途的页面/局部图像；具体接口方案待实现前比较，不能只添图片名称、猜测性 alt text 或学校专用规则。图像证据不可用时，应明确保持证据不足，不以机械检查通过推动盲判进入物化。阶段限制、Tool 返回、阅读包和反馈口径须一致，同时保留原 `source_entry_id + span` 的判断及执行定位。

## 验收条件

| 层级 | 必须证明 | 当前状态 |
| --- | --- | --- |
| `logic/contract` | 语义阶段可按授权范围取得真实图像像素及关联的源条目/页面上下文；不能跨任务或把底层 locator 交给 Agent；视觉证据缺失时返回可行动的不足反馈。 | 已通过：真实 NJAU 两图像素与源媒体一致，相关测试 170 passed；不可解析时 `source_picture_evidence_unavailable`。 |
| `real replay` | 使用上述 NJAU 真实 task root/原件与两张封面图片，回放证据接口并核对返回了真实图像像素、正确源条目绑定及周围版式，而非仅 `picture` 类型；再检查一个真实正文图片或图表及相邻文字/空白载体，避免只对封面特设。此层不证明 Agent 已观看。 | 已通过：NJAU 两图绑定原 source entry；PKU 真实正文图片与公式说明、图题同包。 |
| `E2E agent loop` | 新任务运行真实 `prepare-template`；调用记录证明 Agent 在相关判断前取得图像，判断理由可回溯到其看到的画面；必要反馈能促成修订。不能仅以角色/字段检查通过代替。 | 已通过封面 post-unit Agent loop：Agent 明确读到两图内容、作固定学校标识判断，语义批次接受。整份 12 页 NJAU 原件尚未完成 E2E。 |
| `product acceptance` | 同版本 `final-template.docx` 与 `fill-contract.yaml` 发布并可供下游填写；在 Microsoft Word 中对原件、候选和代表性填写结果逐页/逐单元核对图片、位置、固定文字、字段及版式。若学校图片应保留，必须在最终 Word 中实际可见。 | 图片专项通过：真实 NJAU 封面单元双文件、9 槽、Word 原件/候选/填写版对照均保留两图；完整模板人工签收及整份学校模板验收未做。填写时部分空白下划线收缩，属另一个填写版式问题，不能据此宣称完整产品验收通过。 |

验收不预先规定这两张图必须选 `fixed_label` 或 `style_only`；正确 role 应由 Agent 基于画面和学校上下文判断。环境渲染不可用、机械拒绝盲判或单元测试通过，都不等于合法输入已生成可用双文件。

## 2026-10-02 修复前产品验收链锁定

| 环节 | 预期与已知证据 | 尚缺证据及验证办法 |
| --- | --- | --- |
| 真实来源与目标范围 | 使用上文 SHA-256 绑定的 NJAU 学校原件，目标为封面两张图片及其相邻表格、标题和填写位置；初始清单中两张图分别是 `source-entry-05686695b50646cfb45c11ee` 与 `source-entry-be9bd13e6f9a0ffeb8dde62e`。 | 在 Microsoft Word 打开原件，留存封面页面画面，核对图片内容、位置、大小及邻近文字。另找含正文图或图表的真实学校 Word 作同类回归。 |
| 已有判断与保留义务 | 本轮封面首轮把图和布局载体判为 `body_structure`，缺字段被退回；修订为 `style_only` 后通过局部机械检查。图片画面未进入该阶段，因此两个 role 的语义依据尚未成立。固定封面内容、图片和可填写位置应按看过原件后的接受判断处理。 | 新任务中记录取图发生在判断提交前，以及 Agent 如何根据画面和相邻上下文判断；不能把旧候选理由当作已验证事实。 |
| 候选变化 | Agent 能按当前 unit 的原 source entry 获取实际图像像素及页面上下文；物化后的候选依已接受判断保留或处理图片，固定文字及授权范围外内容不退步。 | 用真实 task root 回放图像证据，再运行新 `prepare-template`，逐页对照原件和候选，检查视觉位置及内容。 |
| 代表性填写 | 封面姓名、题目等字段填入后，图片、固定文字与版式仍可见且位置正确。 | 用发布的同版本模板和合同作代表性填写，在 Microsoft Word 中核对实际填写页面。 |
| 双文件交接 | `output/final-template.docx` 与 `output/fill-contract.yaml` 同版本发布，合同中的字段接口可由下游消费。 | 新任务产出后核对模板 hash、合同绑定及字段消费；没有双文件或 Word 视觉结果时保持产品验收未完成。 |

本次先修判断前的证据供给。若真实回放证明图像已可见而 Agent 仍判断错误，应重新归因到输入上下文或领域判断；若判断正确但 Word 中图片缺失，应转查物化和发布层，而不是继续增加语义阶段提示。

## 2026-10-02 当前实施与验证记录

- Microsoft Word 直接打开上述 NJAU 原件：12 页，封面第 1 页上方可见圆形校徽与“南京农业大学”字样图片，下面是“本科生毕业论文（设计）”标题和题目、姓名等填写行。本次 UI 观察尚未留存独立页面截图。嵌入的字样原始 PNG 为绿色，而 Word 页面显示为黑色；原始媒体像素可用于辨认内容，不能替代 Word 的最终颜色和版式验收。
- `unit_evidence_packet` 现按当前已接受 unit 的 source entries，从不可变原件解析图片 relationship，返回原图转换的 PNG content block，以及每张图的原 `source_entry_id` 与内容块序号。即使文字窗口未翻到图片，该 unit 的图片也随包可见。无法唯一解析或读取图像时，该包返回 `source_picture_evidence_unavailable`，不交付缺图的语义材料。
- `logic/contract`：真实 NJAU 原件的两张封面图在测试中分别与 DOCX 内 `image1.jpeg`、`image2.png` 像素一致；相关 Tool、Agent 边界与 prompt 测试 `170 passed`。这只证明证据交付，不证明 Agent 已观看或最终模板可用。
- `real replay`：旧 NJAU 真实 task root 的 `unit-1` 阅读包返回两张图片，绑定上述两个原 source entry；另以真实 PKU 正文 Word 单元建立当前格式的 task-local inventory，正文图片 `source-entry-f1463cdae452a8ff6ca5de2c` 与前后公式说明、`图 2.3` 图题在同一阅读窗口返回。PKU 旧运行账本本身缺当前格式的 immutable initial inventory，不能直接冒充已从旧任务恢复成功。
- `E2E agent loop` 与 `product acceptance` 仍以新运行及产物结果为准；本段不作通过声明。

## 2026-10-02 新运行、发布与验收结果

- **Agent 实际看图并判断。** 真实 NJAU 封面单元的新运行位于 `temp/template-image-evidence-cover-acceptance-20261002/`。`semantic-revisions/00000004.json` 中，Agent 将圆形校徽识别为含“南京农业大学”和“1902”的学校标识，将另一图识别为“南京农业大学”书法字样，分别对原 `source_entry_id` `source-entry-0c457f0c1e4ffc984d522b36`、`source-entry-0d33eb077547af0393d268b8` 提交 `fixed_label`。其理由引用了图片画面，而非仅据 `picture` 类型猜测。两批语义判断最终被接受；这是封面 post-unit 的真实 Agent loop，不代表整份 12 页原件已全部运行。
- **双文件发布。** 同一任务经最终页面复核后，`prepare-template --from unit-boundary` 返回 `status: built`，发布 `output/final-template.docx` 与 `output/fill-contract.yaml`。模板 SHA-256 为 `fbb507e27fc499d069a80eb2c88b21b86b732a8f3102fa9c472b2a661c735a49`，合同绑定该 hash，`validate_published_template_artifact` 通过，包含 9 个可定位填写槽。合同自身状态为 `candidate_pending_human_acceptance`；此处不伪称已有人类签收。
- **逐页视觉复核。** 在 Microsoft Word 中打开真实封面原件与候选：校徽、书法字样、固定论文标题和封面标签均可见且位置一致；Word 均为 1 页。LibreOffice 近似渲染对两份文件都产生第 2 张空白图，Word 无对应第 2 页；复核记录明确写明差异，位于任务根的 `work/.docfit/final-visual-review/55323c06b37df2b17f56f9b94bb6375228fb3756f4eb7044f18a5ec8f1e42dce/review.json`。该记录为 Codex 实际观察的 external visual review，不是人类产品签收。
- **代表性填写。** 用发布的合同定位 9 个控件，填写标题、姓名、学号、学院、专业、导师、职称和日期，生成 `temp/template-image-evidence-cover-filled-20261002.docx`。`docfit tools inspect` 报 `docx_package`、`officecli_parse` 均 `ok`，仍有 2 张图片与 9 个控件；两张嵌入媒体的 hash 在发布模板与填写版一致。Microsoft Word 可见两图、标题及所有填写值，仍为 1 页，没有图片缺失、越界或重叠。
- **独立限制。** 简单控件替换后，原空白下划线长度随填写值收缩，导师姓名和“职称”相邻文字显得拥挤。这不是图片证据供给的首次偏离，但说明本次代表性填写不能证明所有封面字段的版式质量；完整模板产品验收与人工签收保持未完成。整份 NJAU 原件的首次完整运行在 `temp/template-image-evidence-e2e-20261002/` 的边界阶段长时间无结果后中断，未冒充整份 E2E 通过。

## 第二个真实学校测试用例：PKU 封面与正文图

在扩充测试前锁定本例的验收链。输入是从真实 PKU 研究生学校模板拆出的封面单元 `temp/phase8-v05-20260912/pku-01-cover-v4/input/school-template.docx`（SHA-256 `93b1956f6552d423a63e2a352b787dca88b7f25bc3315c4acfd388eef716a0a5`），以及同校完整真实模板的正文图片。PKU 单元沿用原模板 Word 媒体和相邻结构，不使用手写简化 DOCX。

Microsoft Word 中的封面原件显示一张深红色的“北京大学”校徽与校名字样合成图片，其下是“博士研究生学位论文”、题目三行、姓名/学号/院系/专业/研究方向/导师姓名填写线、学位类型选择和日期。预期 Agent 先看到这张图片，再判断学校固定标识的保留义务；候选和实际填写后，图片及固定标题应在相同封面位置可见，填写槽与合同绑定且 Word 页面不能出现图片缺失或错误分页。现有历史运行不证明本次新代码下的 Agent 已看到图像，须另跑新任务、核对语义 trace 和双文件/Word 结果。

同时新增确定性的 PKU 正文图片回归：以真实完整 PKU 模板中的“图 2.3 复制公式时应选择的范围”为目标，要求该图原 `source_entry_id` 的实际像素、前方公式复制说明和后方图题进入同一 `unit_evidence_packet` 阅读窗口；分页不应使图片块消失。这只验收 `logic/contract` 与 `real replay`，不能冒充正文 Agent E2E 或正文最终 Word 产品验收。

### 新增用例的实际结果

- **固定回归通过。** `tests/fixtures/template_extraction/pku-graduate-real-source.docx` 是从仓库已有真实 PKU 完整模板复制的稳定测试输入；测试固定其 `word/document.xml` 摘要，并动态寻找正文中的实际图片及“图 2.3”图题。`tests/contract/test_docfit_evidence_tool.py::test_unit_packet_keeps_real_pku_formula_figure_with_its_caption` 验证图片像素匹配 DOCX 原媒体、源条目绑定、前后文字同窗口、文字窗口翻页后图片仍可见，以及 Agent 返回不暴露底层定位。单文件 `34 passed`，连同边界/启动上下文测试 `48 passed`。这些是 `logic/contract` 与真实输入证据接口 `real replay`，不是正文 Agent 或产物验收。
- **PKU 封面 Agent loop 揭示并修正图片角色歧义。** 首次新运行 `temp/template-image-evidence-pku-cover-newcase-20261002/` 的 Agent 已调用 `unit_evidence_packet` 并在理由中认出“北京大学”学校固定标识，但把图片本体标为 `style_only`。这表明图片可见仍不足以保证角色正确：既有领域指引没有明确区分固定图片本体和承载它的布局。于是只在学校语义 Skill/Reference 补充通用分类规则，没有把学校名称写入代码或机械门禁。第二次新运行 `temp/template-image-evidence-pku-cover-role-recheck-20261002/` 的首批 Agent 判断，将同一图片 `source-entry-9d2193770d8116ab931419fe` 标为 `fixed_label`，理由引用“PEKING UNIVERSITY 1898”与“北京大学”画面；本批次机械复核已接受。第二次运行在首批通过后主动中断，故只证明图片相关的 `E2E agent loop`，不是整个封面完成。
- **封面产物未通过。** 首次运行的四批语义判断完成后，物化前因三个 `materialization_body_structure_carrier_unsupported` 阻塞，没有发布双文件。对应源条目属于旧提取单元保留下来的页眉及空段落，其中页眉“第三章 其他注意事项”被另分为单元并判断成正文标题。这是图片证据之外的页眉/单元上下文与物化问题；本次没有让 Agent 改正确的图片判断或伪造 PKU 产物。PKU 封面的 `product acceptance` 仍未完成，南京农业大学封面图片专项通过的结论不因此扩大或撤销。

## 2026-10-02 更正：原 Word 格式事实缺口

上述“页眉被判断成正文标题”的表述只描述结果，不能归因为 Agent 忽略了页眉：该条目的 Agent 阅读包仅有 `style_summary.style: header`，未明确说明它位于 Word 页眉 story。正文标题层级、列表级别与编号类型也没有稳定的源 Word 事实投影。首次偏离在判断前的事实供给，页眉载体物化是否另有独立缺陷仍需在事实补齐后验证。

本次新增验收链：输入沿用真实 PKU 封面单元和同校完整模板；Word 原件中封面应有红色校徽、固定标题、填写线，完整模板还应有页眉、标题和列表。Agent 在 `document_map`、`unit_evidence_packet` 与修订上下文中应见到所属 story、原段落样式、Word 大纲级别、列表级别与编号格式等可辨认事实，并仍以原 `source_entry_id + span` 判断。事实不得包含底层 locator、编号内部 ID 或直接替 Agent 指定 role。新运行需核对原页眉条目不再仅凭正文文字被当作正文标题；候选与填写版在 Microsoft Word 中核对原有图片、固定标题、页眉、标题/列表结构和版式；同一版本双文件可供下游消费。

本轮结果：真实完整 PKU 模板的回归证明页眉条目 `第三章\t其他注意事项` 得到 `story: header`，正文“研究背景”得到 `outline_level: 1` 和中文计数编号，正文列表“另一个数字编号”得到列表一级及十进制编号；两种 Agent 阅读入口均返回这些事实，且不含底层定位。相关 186 项合同/运行测试通过，另有旧缓存缺版本时拒绝继续的测试。新 PKU 封面任务 `temp/template-word-format-pku-cover-20261002/output/` 的真实 unit-boundary Agent 将页眉/脚注作为辅助内容，仅建立封面单元；post-unit Agent 把该页眉判断为 `fixed_label`，把空页眉/页脚段落判断为 `style_only`，全局语义审查已接受。

本次 E2E 初次到视觉阶段时遇到 `visual_renderer_unavailable`；启动本机 Docker Desktop 后，从同一任务恢复，候选进入逐页复核并最终返回 `built`。`output/final-template.docx` SHA-256 为 `95c90405d3c848c561c6254fc7bde38a92ddcca5f61a0fca2d4b08b162a5d45a`，同版 `output/fill-contract.yaml` 绑定该 hash，发布合同验证通过，含 11 个填写槽。在 Microsoft Word 中直接打开原件与候选，均为 1 页；红色北大校徽/校名字样、固定“博士研究生学位论文”标题、各表格标签及下划线可见，候选把题目、个人信息、学位类型和提交年月按接受判断改成填写控件。LibreOffice 近似渲染把两份均分成 2 页，与 Word 的实际分页不同；复核记录保留了这一差异。

以发布合同定位 11 个控件并填入题目三行、姓名、学号、院系、专业、研究方向、导师、学位类型和年月，得到 `temp/template-word-format-pku-cover-filled-20261002.docx`。Word 打开后仍为 1 页；上述值、图片和固定标题可见，没有溢出或重叠。DOCX 包校验通过，源稿、候选和填写版的 15 个媒体 part 及 8 个 header part 摘要完全相同。此例完成 PKU 封面单元的 `product acceptance` 技术复核；合同状态仍为 `candidate_pending_human_acceptance`，不等于人工签收或完整 PKU 模板验收。目录、正文等其它单元的最终产物还未做本轮 E2E/Word 验收。
