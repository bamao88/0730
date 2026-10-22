# 模板提取：按 Word story 表达功能区与辅助区域

状态：**表达模型已实现；NJAU、PKU 完成 `real replay`，NJAU 单元边界 `E2E agent loop` 通过；NJAU 整份 post-unit 真实运行因语义时间预算耗尽而失败，产品验收未完成。** 适用模块：模板提取的 `unit-boundary` 至 post-unit。本文是对 [document_map 诊断](../bugs/template-document-map-story-order-and-pagination-20261002.md) 的表达模型与实施依据，不把传输分页当作功能区。

## 产品目标与现有证据

用户应能依赖一份真实学校模板中的正文功能区、页眉页脚及注释内容都被看见、判断并落实到同一版本的 `final-template.docx` 与 `fill-contract.yaml`。`unit-boundary` 阶段先要给后续判断一个真实的阅读边界，不能把辅助区域强行解释成正文最后一个功能区。此阶段通过也不代表最终文件可用。

南京农业大学本科模板的原始 Word 检查得到 798 个底层对象，首次判断前归一成 211 个源条目。当前清单前 177 条为正文，后 34 条分别是页眉 7 条、页脚 23 条、脚注 2 条、尾注 2 条；传输窗口是 100 + 100 + 11。真实 `unit-boundary` proof 的第 15 个单元“致谢（含页面页脚页眉尾段）”覆盖条目 170–211，其中正文仅 8 条。该次 Agent 的总结已经识别页眉页脚；仅补 `word_format.story` 事实不足以解除以下合同冲突：

- 当前 [Skill](../../.claude/skills/docfit-school-extract/references/unit-boundary.md) 要求页眉页脚不建立同名功能区，却也要求全部条目进入一条连续分区。
- [边界解析器](../../src/docfit/template/unit_source.py) 要求首单元从整个 canonical 清单起点开始，末单元在清单末尾结束，且中间无空隙。
- [post-unit 投影](../../src/docfit/app/prepare_template.py) 与 [语义批次](../../src/docfit/template/semantic_batches.py) 只从 `resolved_units` 取得覆盖范围，因此直接跳过辅助条目会在下一阶段失去它们。

因此已确认的根因是**一条全局连续分区同时承担正文功能划分和全部 Word story 的覆盖记账**。story 可见性、分页重复和模型耗时是相关问题，但不解释上述强制归属。

## 表达模型的四个不同概念

| 概念 | 含义及责任 | 不能混同 |
| --- | --- | --- |
| canonical source inventory | Harness 在首次 Agent 判断前建立的不可变、完整来源账本；每条仍以原 `source_entry_id + span` 定位 | 不是页面顺序，也不是功能区列表 |
| `body_units` | Agent 对**正文阅读序列**提出的学校功能区名称与相邻边界；Harness 解析精确 span | 不包含无正文功能的页眉、页脚或注释；不负责字段用途 |
| `auxiliary_scopes` | Harness 按 Word story 类别组织的非正文源 span，用于取证、语义判断和覆盖；`story_regions` 保留各 story 实例归属 | 不是 Agent 猜出的学校功能区，也不是可略过的装饰 |
| `context_links` | Tool/Harness 从节关系、页眉页脚引用、脚注/尾注锚点等验证出的适用或锚定关系；可关联多个正文单元 | 不等于唯一语义所有权，不能按 `/header[3]` 推第 3 页 |

**单一身份、两条轴线。** 全部 211 条仍在同一初始清单中。正文轴线只排列正文 span，供 Agent 划功能区；story 轴线按页眉、页脚、脚注、尾注组织辅助 span，各 scope 内以 `story_regions` 区分原 Word story 实例。这避免将 NJAU 的 23 个 story 实例各变成一个语义批次。两条轴线引用相同的初始身份，不生成第二套 `source_entry_id`，也不改变原文、来源和源快照。正文单元的“连续”是相对正文轴线，不能再要求跨 story 的全局相邻。

### 建议的 Agent 输入与输出

Agent 首先收到包含正文顺序、各辅助 story 概览和可验证关系的阅读视图。正文条目保留原文、顺序、源身份、视觉和格式线索；辅助条目可按需展开，逐条明确 story 类别和必要上下文。story 实例的显示名可以是“页眉 A”，但主定位仍是 `source_entry_id + span`；内部 OOXML part、locator、object_ref 不进入默认 Agent 输出。没有实证的节或页面关系显示为 `unknown`。

Agent 的 `unit-boundary` 提交只给正文单元的 `unit_id`、`unit_name`、`start_boundary`、`end_boundary`。这些字段沿用现有边界点表达，仍允许一个正文条目在内部切开。辅助范围由 Harness 根据首次清单与 Word 事实投影，不要求 Agent 猜它属于哪个学校功能区，也不允许 Agent 通过缩短最后一个单元丢掉它。

proof 的关键结构如下；省略了 hash、原始边界及 Word 映射的部分字段：

```yaml
schema_version: docfit-unit-boundary-proof/v3
source_inventory_digest: "..."
units:                      # 保存 Agent 原始正文边界提交
  - unit_id: unit-15
    unit_name: 致谢
    start_boundary: "原 source_entry_id 上的边界点"
    end_boundary: "正文条目 177 上的边界点"
resolved_body_units:        # Harness 重解所得，保留原 source_entry_id
  - unit_id: unit-15
    source_spans: ["原 source_entry_id + 精确 span，止于正文条目 177"]
auxiliary_scopes:           # Harness 从原件事实投影
  - unit_id: auxiliary-header
    story_kind: header
    story_regions: [{region_id: "不透明区域标识", source_entry_ids: ["原 source_entry_id"]}]
    source_spans: ["原 source_entry_id + 精确 span"]
# context_links 尚未实现；未知关联不造边
```

`auxiliary_scopes` 不是 Agent 输出，也不能凭 story 字符串或清单相邻位置拼出 `context_links`。当前实现由原 locator 的 story 根判定类别与实例，Agent 只见不透明 `region_id`；[格式事实](../../src/docfit/template/source_word_format.py) 尚无节适用范围、脚注锚点等关系证据，故当前不生成 `context_links`。关联缺失仍是后续取证能力缺口，不得当作已核实关系。任何源条目若混合多个 story 且无法把来源精确分成独立 span，当前会拒绝分区；不能在接受 proof 后暗中重建 ID。

## 覆盖、判断与取证的不变量

1. 正文单元在**正文轴线**上按序、无缺口、无重叠覆盖全部正文 span；原有精确切点校验保留。辅助 scope 在各自 story 实例内按序覆盖全部非正文 span。两者的并集恰好覆盖完整 canonical 清单，包括空文本结构对象；不能因为辅助区域没有正文功能名而漏账。
2. 每个原源条目的语义判断只提交一次。一个正文条目若跨两个单元，所属语义批次需带齐两个精确单元上下文；辅助条目也各有一个权威判断批次。`context_links` 可以让一个辅助条目作为多个正文单元的**只读上下文**出现，但不得复制其判断或物化操作。
3. 未知关联不能被自动改成“属于最后一个正文单元”。没有节或锚点证据时，辅助 scope 仍作为独立语义工作范围进入 post-unit；Agent 依据原文、视觉和学校规则判断保留、删除、字段、生成及样式义务，Harness 检查落实。事实关系缺失若阻碍正确判断，应作为事实/取证问题反馈，不要求 Agent 编造关联。
4. 所有范围、关系与判断均绑定相同的源 hash、初始 inventory digest 和 proof。恢复时重解正文与辅助覆盖、校验 relation 的证据与投影摘要；不接受旧 v2 proof 静默当作新模型。发布的 `source_partition` 也保留两轴覆盖证明。
5. `story_instance_id` 是取证分组键，不能升级成目标定位。正文和辅助范围的编辑都仍按已接受的 `source_entry_id + span` 解析到底层 Word 对象。

## 后续消费者必须同步演进

这不是只改 `document_map` 的展示。实施时需把当前“所有条目都属于某个 `resolved_unit`”的假设改为“所有条目都属于一个可判断的 work scope，只有正文 scope 是学校功能区”。需要同步检查以下接口：

| 消费者 | 必需改变 |
| --- | --- |
| `unit_source` / checkpoint / resume | 分别证明正文连续和辅助覆盖，记录两个投影与关系的绑定；旧 proof fail closed |
| post-unit inventory / reading packet | 为正文单元与辅助 scope 都生成可持久化的取证包；辅助上下文若重复显示，标明只读引用与权威判断范围 |
| `unit_evidence_packet` Tool | 能按 scope 读取辅助来源，且不把辅助 scope 伪装成正文 `unit_id` |
| semantic batch manifest / judgment review | 对全部 canonical 条目建立唯一判断所有权；跨单元同源条目保留全部切点上下文；coverage 不依赖旧 `resolved_units` 完整覆盖假设 |
| materialization / provenance / publish | 从接受的原 span 执行，并验证页眉页脚等义务与双文件绑定；发布证明能回溯完整初始清单 |
| Agent Skill 与模块 Contract | 先在运行合同可执行后改写“所有对象进入一条连续分区”的旧规则；明确辅助区域的阅读、判断和反馈责任 |

接口内部可用统一 `work_scope` 抽象承载取证与批次，但 `body_unit` 与 `auxiliary_story` 必须保留类型区别；不把辅助 scope 的机器名呈现为学校功能区。当前对外的最终 Word 与填写契约目标不变，内部 proof 版本需显式升级。

## 取舍与性能边界

- **仅补 `story` 标注并保留全局连续分区：不成立。** Agent 即使正确看出页眉，也仍被覆盖检查迫使放进末单元；NJAU 的真实提交已证明这一点。
- **把每个页眉页脚当作顶层功能区：不成立。** 机械覆盖可过，但把 Word 辅助 story 错当学校内容功能，后续字段与样式判断会失真。
- **正文分区 + 辅助 story 覆盖 + 事实关联：采用。** 既维持所有源条目可判断，也让功能区仅表示学校正文内容；代价是 proof 与 post-unit 消费者需要一起迁移。

本设计可能减少边界 Agent 要同时组织的无关条目。同一 NJAU 模板的一次新运行把边界首次查询从旧运行的 9 分 54 秒降到 4 分 19 秒，但模型输出有波动，**这只是一组观察，不能证明因果提速**。三次 `document_map` 传输重复、分页尺寸、长上下文、输出/推理 token、功能区拆分粒度、图片证据与语义阶段超时是独立优化主题。它们不能靠本模型自动解决；也不应通过省略辅助内容来换时间。

## 实施前核验与完成标准

| 验证层级 | 应取得的证据；当前状态 |
| --- | --- |
| `logic/contract` | 新 proof 对正文与辅助 span 的完整覆盖；同源跨单元只判断一次；混合/未知 story 拒绝；v2 恢复被拒绝。**相关合同测试已通过。** |
| `real replay` | NJAU 原始 task root 对照：原条目 170–177 留在致谢正文单元、178–211 进入 4 个辅助 scope，全文 211 条闭合；该回放中的正文单元划分产生 19 个取证包与语义批次，34 个辅助条目均被分配。PKU 整份真实模板从原件重新建 525 条初始清单，用一个人工指定的正文范围验证 497 条正文和 28 条辅助条目全部进入阅读包及 12 个语义批次。**NJAU、PKU 的分区与下游投影回放通过；PKU 功能区语义与 HUNAU 尚未验证。** |
| `E2E agent loop` | NJAU 整份 DOCX 两次跑 `--until unit-boundary`：第一轮 Agent 首次将终点写在页眉 `start`，收到反馈后改为正文第 177 条 `end`；13 个正文单元、4 个辅助 scope，墙钟 357.7 秒（SDK 327.0 + 29.8 秒）。明确终点写法后的第二轮一次提交即接受，同为 13 个正文单元、4 个辅助 scope，211 条闭合，墙钟 260.1 秒（SDK 259.3 秒），post-unit 投影为 17 个批次且 34 个辅助条目均分配。两次模型输出并非固定，时差不能单独证明提示的因果提速。**单元边界 E2E 通过；整份 post-unit E2E 失败，见下节。** |
| `product acceptance` | 在 Word 中核对原页眉页脚、脚注/尾注、正文内容及代表性填写；同版本 `final-template.docx` 与 `fill-contract.yaml` 可交接。**未执行。** |

最早的区分性验证应同时保留两份对照：旧 v2 proof 的末单元 42 个条目，以及新模型在同一不可变源清单上得到的正文与辅助覆盖。若新增 `story` 标注后仍出现末单元吞并辅助条目，则证实表达模型未真正切换；若辅助条目在 post-unit 消失，则证明只修了边界外观而未修消费者。

## 2026-10-06 整份 NJAU 真实 post-unit 复测

在同一真实 NJAU 原件上，从已通过的 v3 边界 checkpoint 运行：

```text
.venv/bin/docfit prepare-template \
  --school-template tests/manual-diagnostics/input/school-template-nannong-undergraduate.docx \
  --output temp/template-story-boundary-e2e-20261006-njau-prompt \
  --from unit-boundary --until post-unit
```

运行证据位于该任务根的 `work/.docfit/template-agent-execution.json`、`harness/semantic-batch-manifest.json`、`harness/semantic-batch-candidates.json` 和 `harness/semantic-revisions/`；对照是旧任务根 `temp/template-diagnostic-20261002-njau-full/`。两次源文档相同，新任务的 211 条源条目被分为 13 个正文批次和 4 个辅助 story 批次；页眉 7 条、页脚 23 条、尾注 2 条、脚注 2 条均保留原身份并有唯一批次。新“致谢”正文只有 7 条，旧 proof 的最后单元则有 42 条，其中 34 条为辅助 story。这确认了原来的强制归属错误在真实边界 Agent loop 中消失。

默认配置的 post-unit 运行 **失败**：`semantic_query_time_budget_exhausted`，墙钟 3605.5 秒，只接受 7/17 个语义批次；第 8 批中断，4 个辅助批次（第 14–17 批）均未进入 Agent 判断，`output/` 没有双文件。旧运行同样因 3600 秒语义预算耗尽而失败，当时接受 10/15 批。新运行不能宣称整份 `E2E agent loop` 或 `product acceptance` 通过，辅助区域的后续正确判断与 DOCX 物化仍无实测证据。

耗时需要按阶段比较。旧边界首次 SDK 查询 593.9 秒、两次查询合计 685.5 秒；新边界一次查询 259.3 秒，整段墙钟 260.1 秒。新旧两次运行的语义阶段都耗尽约 3600 秒，新运行前 6 批查询累计约 37 分钟，旧运行前 6 批约 25 分 15 秒；单次模型运行波动不能据此证明设计变更导致语义变慢，更不能把边界提速当作整份模板提速。新运行第 7 批首次查询单独耗时 1208.3 秒，随后为一个缺 `field_id` 的条目修订两次（67.1 秒与 55.8 秒），是本次最大的可定位长尾。

新运行还记录了两个与 story 分区不同的往返：封面批次的空白/表格载体被首次标成缺字段的 `body_structure`，一次反馈后改为 `style_only` 并接受；目录批次把原文制表符写成字面 `\\t`，25 个条目因 `ordered_part_text_mismatch` 退回，一次修订后接受。第 7 批第一次修订又引入多个 `field_role_not_in_input_vocabulary` 冲突，第二次才通过。封面两张图片在 Agent 首次提交中被识别为学校固定图，封面批次最终接受；由于没有最终 DOCX，本轮不证明图片在整份发布文件中保留。

因此本轮能确认的提升是**正文功能区不再吞并辅助 story，且辅助条目不会在下游批次清单中丢失**；尚未解决的是语义阶段串行长尾、修订收敛和完整产物交付。`document_map` 的重复传输与分页成本未在本次表达模型修改中处理，也不能由上述边界时间差推定已优化。
