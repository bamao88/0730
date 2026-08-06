# DocFit 模板提取静态 E2E Eval 执行胶囊

- Capsule status: IN_PROGRESS
- Source design: `docs/plans/docfit-template-extraction-eval/DESIGN.md`
  (`cbed177e4bc63477eae4a9007d3fdc3bae6e8564989b21261c5b8e7508e58a7e`)
- Source plan: `docs/plans/docfit-template-extraction-eval/PLAN.md`
  (`8d3c44edb4e620f0681d7bc845a702b54a4a51f219f9b5c07e46da9ed28c89fa`)
- Latest user intent: 实施三校 `case.yaml + gold/template.docx + gold/fill-contract.yaml`
  结构，并让 Word 槽语义名称与 canonical YAML `field_id` 一致
- Approval source: 用户先批准实施思路，随后给出目标目录并明确要求“实施”
- Baseline commit: `dc159eb01ebb1bc0d4c5446e7c59f34567969b26`
- Current development gate: G2 component proof；G1 schema/config/fixture 能力合同已通过；
  本次只对 candidate case 物化组件形成 G2 PASS，不构成 G5 或 M3 PASS
- Current slice: W0/G1 已完成；W6 candidate 目录预物化已完成；W1–W5 的模型、事实分析、
  evaluator、评分、报告和独立 CLI 尚未实现
- Approved scope: `evals/template-extraction/**` 的独立数据、schema、配置、fixture、测试与
  准备脚本；只读消费 Temp candidate 和 Registry 的版本/hash
- No-touch scope: `src/docfit/**`、产品 CLI/根依赖、Agent/Provider/Adobe/OfficeCLI 运行链、
  Student/Placement Eval、用户其他未提交改动
- Isolation contract: Eval 不 import `docfit`、不启动产品 CLI、不把 Temp 放入运行依赖；
  正式 case 只通过路径、schema、状态和 SHA-256 引用外部准备来源

## Gate Report：candidate case materialization

- Gate conclusion: **PASS（仅 G2 物化组件）**
- G5/Human readiness conclusion: **FAIL / NOT_READY**；三校均保持 candidate，
  `expected_verdict: INPUT_ERROR`，不得进入 Gold 通过率
- Changed scope:
  - 新增正式 `cases/01-*`、`02-*`、`03-*` 目录和各自三件数据资产；
  - 新增正式 Eval config、candidate 物化器和 3 个物化器测试；
  - 扩展 case/fill-contract schema，使复合槽、连续 region、样式引用与 candidate 状态可执行；
  - 更新专项 DESIGN/PLAN 和 Eval README，区分目录位置与 Human acceptance。
- Explicitly unchanged: 产品源码/依赖/CLI、Temp 候选源、原 Gold 资产、两校 OfficeCLI
  schema finding、M3 状态和任何 accepted Gold 状态
- Acceptance mapping:
  - 目标目录完整 → `CASES-01`；三个 case 均存在 manifest/template/contract；
  - 槽名与 YAML 一致 → `CASES-02`；91 个内容控件满足 `w:alias == field_id`，`w:tag`
    与 slot/region locator 闭包；
  - hash/Registry 绑定 → materializer 预检 + case/contract schema；三校 template/contract、
    Registry `9779d0…522d`、Eval config `d734e5…88b6` 均绑定；
  - 不自动晋升 → case schema 强制 candidate → `INPUT_ERROR`，`CASES-03` 拒绝覆盖 accepted。
- Artifact summary:
  - HUNAU: 24 slots + 1 generated region；template
    `c118e574db83aeaa057e35db5eff98121ce7dee6592f4046cacd0b7fcf30d3b0`；OfficeCLI FAIL
    （16 个既有 schema-order findings）；
  - NJAU: 32 slots + 1 generated region；template
    `284038cdcb25a9f4ac0734790776d905c6b592c1eeb2251ebd1107ec03ec9eef`；OfficeCLI FAIL
    （1 个既有 styles schema-order finding）；
  - PKU: 28 slots + 3 generated regions；template
    `3bbe394c3b6f63cc3126fd92134c8042cf5da8f48128f7ee97c34741206b88a3`；OfficeCLI PASS，
    但该 snapshot 不继承既有 r02 Gold 的 Human signoff。
- Verification commands/results:
  - 独立 Eval：`uv lock --project evals/template-extraction --check`、frozen sync、build、
    task-scope Ruff 和 strict mypy 均 PASS；W0 + materializer/schema 定向测试 `29 passed`；
  - 数据包：三份正式 DOCX 均通过 ZIP integrity，且与规范化 candidate source byte-identical；
    schema/hash/path/`alias == field_id`/tag-locator 闭包检查均 PASS；
  - 产品仓回归：root lock/build/mypy、`323 passed` 和 `docfit doctor` 均 PASS；
  - root `ruff check .` 的剩余 finding 只位于未纳入本工作包的并行 W3/临时测试文件；
    `docfit eval --suite core` 两次稳定失败于既有 OfficeCLI synthetic fixture 的
    `fixture_officecli_rejected`，本次 case 数据与产品 fixture 生成链无调用关系。
- Remaining unknowns/blockers:
  - 三校逐槽字段语义、必填性、样式与 protected/remove Truth 尚未 Human signoff；
  - HUNAU/NJAU validation findings 尚未修复或 Human 裁决；
  - fill/update/save/reopen 的空值/长值往返和 Word 全页视觉复核尚未完成；
  - CI 使用授权尚未确认；静态 Eval 不需要 Adobe 外部处理；
  - W1–W5 未实现，因此还不能运行 Actual—Gold 评分。
- Documentation drift: 专项 DESIGN/PLAN、Eval README、本 capsule 与 00/02/03/06 的状态
  声明已同步；`doc-keeper` focused audit 已清除“schema/case 尚未实现”的过期表述；candidate
  物化不作为 production cutover，也不改变 M3 未开始的全局结论
- Advance requires: 继续 W1–W5 G2/G3；三校只有在 Human readiness、validation、hash 和
  protected/remove Truth 全部满足后，才可把三层状态原地改为 accepted 并进入 G5
