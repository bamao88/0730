# 字段 ID 闭环专项结论 — 2026-09-22

状态：**历史后半段审计。全流程对象身份任务 REOPEN，尚未完成。**

2026-09-22 更正：用户所说 ID 是 Agent/Harness/Tool 选择源对象的唯一身份，不只是字段词表。
下面证据从功能区划分后的 inventory 开始，不能证明最早分区也使用同一对象身份。
当前实施以[唯一计划的全流程合同](../../plans/template-field-id-vocabulary-boundary-refactor.md)为准。

用户本轮明确限定“目前只做 ID 任务闭环”。本结论不签收学校语义、字段识别完整率、版式、
样式合同或最终产品，也不将原合并计划的 Phase 8 标为 DONE。

## 可以依赖的能力

字段只能来自本轮输入词表；Agent 选择字段并引用源单元；Harness 解析准确范围；执行和发布
消费同一已接受判断。未知字段、旧字段别名、独立目标覆盖、错位范围和错接发布包被拒绝。
原审计未覆盖最早的功能区判断；新核查发现该阶段仍用文字/页码定位，属于本任务缺口。
原审计轮没有修改运行时代码、Skill、学校判断或历史产物。

这与 [Contract 的原有范围](../../contracts/template-extraction.md) 一致：
“核心字段 ID 合同闭环只证明字段 ID 来源和传播边界，不证明 Agent 在真实学校模板里语义选对。”

工程基线为 `ce8fe78`；开始时 `src/**` 与受测 contract/integration 测试无 tracked diff。
工作区已有其他文档、DOCX 和未跟踪文件，本轮不修改或提交它们。真实样本按本轮记录的字节 hash
取证，不能用 Git commit 代替样本身份。详细结果及输入/判断/产物 hash 见
[evidence.json](../../../tests/manual-diagnostics/template-id-closure/evidence.json)。

## ID 合同逐项核对

| 要求 | 当前实现与本轮证据 | 结论 |
| --- | --- | --- |
| 字段在 Agent 判断前进入输入，不能后置猜造 | `FieldRegistrySnapshot.pre_input_vocabulary` → App canonical inventory → unit packet；32 份真实 inventory/review 的词表和 Registry 绑定通过 | 通过 |
| 源单元只有一个生成入口，分页/重试不重造 ID | `source_entries.source_entry_id_for_entry` 单一 generator；生产 build 调用只有 App `_post_unit_inventory_from_checkpoint`；三校 inventory 投影/重试测试通过 | 通过 |
| Agent 只选择字段并提交源单元及有序 parts | `judgment_shape` allowlist、词表约束和旧别名拒绝；真实封面词表外字段、旧 alias、独立 target 负例均拒绝 | 通过 |
| 范围与原文一致，不能靠重算摘要换范围 | shared `source_spans` resolver 与 `semantic_review` 重读门；32 份真实 accepted review 重新验证；真实封面交换范围并重算引用/摘要仍拒绝 | 通过 |
| 编译、写入不另造字段或另选目标 | compiler typed field binding → context resolver → runtime exact Word fragments；30 份真实回放、261 个实际 Word 槽的字段/引用与 accepted spans 一致 | 通过，回放范围见下 |
| 发布和消费者能核对同一 ID 链 | persisted artifact validator 核对 Word controls、Fill Contract 和 accepted-span provenance；32 份合同的槽均对应原 accepted spans，29 份现存 Word/合同包通过，3 份版本漂移被拒绝 | ID 门通过；不等于全部旧包可用 |
| 旧协议无迁移/双读/fallback 成功入口 | source scan、App/Tool/shared review 与 compiler/readiness denylist；旧搜索接口显式 `registry_field_runtime_removed`；相关负向合同通过 | 通过 |

内部 object ID/locator/fingerprint 是 resolver/executor 映射材料；Registry parent 仅用于确定性容器
组织，不生成独立发布字段。共享读取与最终填写模块的领域字段不是模板 Agent 的字段来源。
本轮未改变这些边界，亦未给旧 payload 增加自动转换。

## 验证层级与结果

- **logic/contract**：指定 20 个测试文件共 `460 passed`。包含 schema、词表、引用、旧协议拒绝、
  实际写入、receipt、发布和恢复分支；其中合成/monkeypatch 用例不称为真实输入证明。
- **real replay**：本轮从三校 32 份真实 task root 读取未改写的 inventory 和 accepted judgments。
  32/32 通过词表及 shared review 重读校验；30 份在隔离目录实际物化并重新打开 Word，
  261 个槽的 `field_id + slot_ref` 与原 accepted span、原填写合同一致。其余 2 份未计成功。
- **负向 real replay**：真实封面判断的 7 类受控损坏副本全部拒绝：词表外字段、旧 alias、
  独立目标覆盖、交换 extent 后重算摘要、旧版填写合同、孤立字段、错配 Word。
  前 4 类均在写入前拒绝且未生成候选。另有 3 份实际漂移 source 被 materializer 以 `stale_ref` 拒绝。
- **E2E agent loop**：本轮未启动新 Agent。重新读取 PKU 封面 `pku-01-cover-v4` 的历史真实执行记录：
  query 2 → `needs_feedback` → query 3（`harness_feedback`）→ `accepted` → host write → publication。
  Agent completion 的源单元/role/field 选择与当前保存的 accepted review 一致；同一 root 的字段链
  本轮已完成真实回放。此为历史 E2E 证据复核，不能表述成本轮新跑 E2E 或重跑全部学校矩阵。
- **product acceptance**：本轮不开展，未代签，也未修改任何 Fill Contract 的人工接受状态。

当前成功回放是 **30/32，不是 32/32**。专项 ACCEPTED 表示已验证的 ID 来源/传播/拒错合同闭合，
并不把不成功的历史样本计为可交付产品。

## 未成功样本与范围外发现

| 项目 | 本轮事实 | 对 ID 结论的影响与后续归属 |
| --- | --- | --- |
| NJAU 03 目录 | current readiness 拒绝同一 Word carrier 同时 cleanup 与 retain/generated；没有重新写入 | 词表/范围重读通过，执行安全阻断；后续处理物化可执行性，不能放宽 ID 门来运行旧判断 |
| NJAU 07 参考文献 | 原 source 已改变，未找到 ledger hash 对应的原始副本；旧 source 与输出包被拒绝 | 原快照回放证据缺口；不得重算历史 hash 冒充同一输入，不计成功 |
| NJAU 06 正文、10 致谢 | 原运行目录 source 已漂移；找到 hash 完全相同的留存副本，用于本轮隔离回放并通过 | 这是显式选择相同快照的诊断输入，不是 runtime fallback；不覆盖旧 root，也不重新发布历史产品 |
| 3 份现存输出包 | NJAU 06/07/10 的 Word 与原合同绑定不一致，artifact validator 全部拒绝 | 说明不能沿用“当前所有旧包已通过”说法；不是新增 ID 推断/双读入口 |
| 通用样式消费者 | 32 份旧合同中 19 份可由 `load_fill_contract` 读取；11 份 style set 无效、2 份缺 style ref | 属于样式合同/旧产物可消费性，不在本轮修复。不能宣称全部下游消费成功 |

对 NJAU 03，本轮只定位到现有互斥处理门，未判定是历史语义冲突还是过严的 carrier 检查；不以
“ID 已闭环”为理由把这个可执行性问题标成已解决。关于学校字段含义、格式说明清理、人工区取舍、
Word 视觉差异的历史问题也没有因本结论被签收。

## 重现入口

从仓库根目录运行；脚本只读指定历史 roots，写入 `temp/id-closure-audit-20260922/`。
历史输入不随诊断脚本提交，缺失时不得造替代语义。脚本输出诊断清单，不以退出码代替逐行验收。

```bash
xargs uv run pytest -q < tests/manual-diagnostics/template-id-closure/contract-checks.txt
uv run python tests/manual-diagnostics/template-id-closure/audit.py
uv run python tests/manual-diagnostics/template-id-closure/replay.py
uv run python tests/manual-diagnostics/template-id-closure/negative_replay.py
uv run ruff check tests/manual-diagnostics/template-id-closure
```

`snapshot-copies.json` 显式记录原 ledger hash 和两份同 hash 留存 source 的路径；回放前再次比较完整
SHA-256，不修改 source inventory、accepted judgments 或任何历史 hash。隔离目录中的候选 DOCX
只用于 ID 执行核对，未作为产品发布、人工签收或视觉验收结果。

原后半段审计记录保留，但全流程已因最早分区缺口重新打开。其它重开条件：出现词表外字段被接受、字段被后置补造、范围替换仍可写入、
错接产物被接受或旧协议重新进入成功路径。范围外发现保留记录，不自动扩展为下一轮工作。
