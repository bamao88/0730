# 模板提取分阶段验收与恢复调试交接

本文应该回答：

- 为什么当前工作不是新增一个独立产品模块，而是完善模板提取模块的分阶段验收和迭代流程；
- 五个关键文档分别叫什么、各自回答什么问题、如何互相引用；
- 后续 AI 应如何从单元阶段 proof 继续调试字段、样式、Registry、apply 和发布；
- `tests/README.md`、模块文档、replay/eval 文档和 runtime 实现之间的边界是什么；
- 下一轮实现时必须遵守哪些分层纪律和验收标准。

状态: human 交接材料
适用范围: 模板提取模块的阶段验收、unit-boundary replay、runtime resume 设计与后续实现

## 闭环状态

本文是 human-facing 交接材料，不是 Agent 默认操作规则。本文中已经确认的长期结论应提升到
Codex 默认记忆或模块文档中；后续 Agent 不应只依赖本文件恢复规则。

已提升或应保持同步的默认记忆位置：

- `CONTEXT.md`：沉淀阶段 proof、`UnitBoundaryProof`、accepted units、阶段 replay 等长期领域词；
- `AGENTS.md`：确认 human 文档结论需要提升到 `CONTEXT.md`、Contract、module doc、Skill、test 或 ADR；
- `docs/modules/README.md`：路由模板提取任务到模块文档、单元 checkpoint、runtime resume、测试入口和 stage replay；
- `docs/modules/template-extraction.md`：承接模板提取模块边界、阶段 proof 与最终双文件交付的关系；
- `docs/modules/template-extraction-unit-boundary-checkpoint.md`：承接单元阶段 Agent/Tool/Harness 分层纪律；
- `docs/modules/template-extraction-runtime-resume.md`：承接 `--until`、`--from`、`--resume-proof` 和 proof validation 设计；
- `tests/README.md`：承接生成测试、阶段 replay 和离线 Eval 的边界；
- `evals/template-extraction/README.md` 与 `evals/template-extraction/stage-replay.md`：承接 final Eval 与中间阶段 replay 的分离。

仍属于后续实现任务、不是文档闭环缺口：

- CLI 参数 `--until`、`--from`、`--resume-proof` 和 proof validation 已有最小 runtime 实现；
- `unit_slice` evidence 尚需代码实现；
- HUNAU、PKU、NJAU 三校 replay fixture/reference proof 尚需稳定化进入长期测试资产；
- 后续字段、样式、Registry、apply 阶段仍需改造成消费 compact accepted units。

## 核心判断

当前目标不是把 `UnitBoundaryProof` 提升为新的跨模块产品合同，也不是新建一个叫
UnitBoundary 的产品模块。

正确目标是：

```text
让模板提取模块具备分阶段验收和从中间阶段恢复调试的能力。
```

模板提取模块对外最终交付仍然只有：

```text
output/final-template.docx
output/fill-contract.yaml
```

`UnitBoundaryProof` 是模板提取模块内部的阶段验收产物、replay artifact 和 debug resume
接口。它的价值是：单元阶段一旦闭合，后续调试就可以从 `accepted_units` 继续，而不是每次让
Agent 重新看完整 PDF、重新拆单元。

## 五个文档

这次确定的五个关键文档如下。

| 文档 | 角色 | 应回答的问题 |
| --- | --- | --- |
| `docs/modules/template-extraction.md` | 模板提取模块流程地图 | 模板提取负责什么、不负责什么；有哪些阶段；阶段之间如何交接；最终交付物是什么；失败如何先做大层归因 |
| `docs/modules/template-extraction-unit-boundary-checkpoint.md` | 单元阶段 checkpoint 操作规程 | Agent 返回什么视觉边界；Tool 如何解析 locator/span；Harness 如何验收 coverage；单元阶段失败如何归因 |
| `docs/modules/template-extraction-runtime-resume.md` | 阶段恢复 runtime 设计 | `--until`、`--from`、`--resume-proof` 的语义；proof validation；从 accepted units 继续后续阶段 |
| `tests/README.md` | 测试总入口 | 怎么区分生成测试、阶段 replay、离线 Eval；上一阶段 proof 没闭合时为什么不能继续下一阶段 |
| `evals/template-extraction/stage-replay.md` | 模板提取阶段 replay 说明 | 三校真实输入如何做 unit-boundary replay；reference proof 与 final Gold Eval 的区别；CI gate 如何归因 |

额外路由文档：

- `docs/modules/README.md` 负责告诉 Agent 进入模板提取任务时应该继续读哪些模块文档；
- `evals/template-extraction/README.md` 仍然只负责 final Actual-vs-Gold 离线评分，并链接到
  `stage-replay.md`。

## 文档边界

`docs/modules/template-extraction.md` 是上层模块文档。它不应该写成单元阶段细节手册，也不应该
塞测试命令大全。它只定义模板提取模块的产品职责、阶段地图、最终交付、分层归因。

`docs/modules/template-extraction-unit-boundary-checkpoint.md` 是单元阶段下钻文档。它只回答
单元边界如何产生、解析、验收和归因。它不负责字段槽、样式、Registry、apply 或最终发布。

`docs/modules/template-extraction-runtime-resume.md` 是 runtime 能力设计。它说明代码/Harness 应
如何支持只跑到某阶段、从 proof 恢复、校验 proof、把后续上下文限制到 accepted units。它不是
Skill 文档，也不是测试文档。

`tests/README.md` 是测试体系入口。它告诉人和 Agent 应该跑哪类验证、哪些输入可以读、哪些 Gold
不能读。它不实现 `--until` 或 `--from`。

`evals/template-extraction/stage-replay.md` 是阶段 replay 说明。它允许 reference proof 和三校真实
输入作为可复现验证资产，但不能把 final Gold 答案注入 Agent runtime。

## README 应补的内容

`tests/README.md` 需要明确新增这段语义，避免后续 Agent 把生成测试、阶段 replay 和 Eval 混在一起：

```text
模板提取调试应先确定当前 checkpoint，再选择验证入口。单元边界、字段/槽位、样式/结构、
apply/生成和发布验收是不同层；上一层 proof 没闭合时，不继续验证下一层。

单元阶段的目标是产出可复用的 UnitBoundaryProof 或等价 replay artifact，证明：
- 使用的是标准学校输入和当前 source_hash；
- Agent 返回的是视觉边界证据，而不是手写 DOCX locator；
- Tool 已把视觉边界解析成稳定 Word locator/span；
- Harness unit_coverage 对 accepted units 返回 ok，或返回可行动缺口。
```

`evals/template-extraction/README.md` 需要明确补这段语义：

```text
本 README 只用于已生成 Actual 产物与 accepted Gold 的离线评分。
如果任务是中间阶段 replay，例如只验证 unit-boundary checkpoint，读 stage-replay.md。
不要把 Gold Word、Gold contract 或 accepted answer 注入 Agent runtime。
```

`docs/modules/README.md` 的模板提取路由需要包含：

```text
template-extraction.md
template-extraction-unit-boundary-checkpoint.md
template-extraction-runtime-resume.md
tests/README.md
evals/template-extraction/stage-replay.md
```

这样 Agent 进入模板提取调试时，不会只读一个 README 就误把阶段 proof、final Eval 和 runtime
实现混成一个东西。

## 后续实现顺序

建议下一轮按这个顺序实现，不要跳步：

1. 固化 `UnitBoundaryProof` schema。它是内部阶段 proof，不是跨模块最终合同。
2. 加 `prepare-template --until unit-boundary`，只跑到单元阶段并写 proof。
3. 加 proof validation：hash、schema、unit id、locator、coverage 必须全部可校验。
4. 加 `--from unit-boundary` 或 `--resume-proof`，后续阶段从 accepted units 继续。
5. 加 `docfit_evidence(unit_slice, unit_id=...)`，后续字段/样式阶段按 unit 读取上下文。
6. 加三校真实输入 replay：HUNAU、PKU、NJAU 只跑到 unit-boundary。
7. 再把字段、样式、Registry、apply 的调试入口改成消费 compact accepted units。

如果第 1 到第 4 步没有闭合，不要继续调字段、样式或最终模板质量。

## 分层纪律

后续 AI 必须坚持这条链路：

```text
正确输入 -> 当前 checkpoint -> Agent 视觉语义 -> Tool 证据/locator 解析 -> Harness 机械验收 -> 后续阶段
```

具体责任：

- Agent 负责看视觉页/区域，判断“封面、声明、目录、正文开始”等学校语义边界；
- Agent 返回 page、region、seen_text、unit_name 等视觉证据；
- Agent 不直接承担从图片推 DOCX locator，也不理解 flat object index；
- Tool 负责把视觉区域、OCR/文字锚点、Word tree 和 layout 映射成 locator/span；
- Harness 负责 coverage、顺序、重叠、schema、hash 和 checkpoint gate；
- Skill 负责稳定领域判断方法，不负责写 Harness 触发顺序；
- Test/Eval 负责可复现证明，不作为 runtime oracle；
- App/runtime 负责 `--until`、`--from`、proof validation、resume 和 fail-closed。

## 常见错误

不要再做这些事：

- 用 synthetic/smoke 输入代替用户要求的真实学校输入；
- 单元阶段没闭合就继续看字段、Schema、Tool apply 或最终模板；
- 把姓名槽、删除提醒、图片、局部表格字段拆成顶层 unit；
- 让 Agent 根据 JSON flat order 判断正文标题和目录项冲突；
- 让 Agent 手写 DOCX locator 当作正式责任；
- 把 Gold 或 accepted answer 放进 Agent runtime；
- Harness 只返回内部 object id，而不给页码、区域、可见文本或 locator；
- proof hash 不匹配还继续 resume；
- 旧 render/ref/cache 没校验就当成本轮证据。

## 验收标准

这项工作完成时，应该能回答：

- 任意一次模板提取调试当前卡在哪个 checkpoint；
- 单元阶段是否有 proof，proof 对应哪个 source hash；
- 后续阶段是否真的从 accepted units 开始，而不是重新拆单元；
- 三校真实输入的 unit-boundary replay 是否可复现；
- 失败反馈能否明确指向 Agent、Skill、Tool、Harness、Schema、App、Test/Eval 中的一层；
- final Actual-vs-Gold Eval 是否只在产物生成后运行，没有污染 runtime。

如果这些问题回答不清楚，说明文档和 runtime 还没有真正形成分阶段验收能力。
