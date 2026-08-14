# Student Content Extraction Eval 稳定入口执行胶囊

- Capsule status: DONE
- Latest user intent: 使用项目内真实学生论文过程文件完成端到端测试，确认稳定评测入口可用
- Current slice: Student 001/002/003 均已有正式 Eval 报告；Student 002 v4 直接 READY，Student 003
  v3 已在最终扁平 Schema + runtime normalization 的当前代码上直接生成可评测 Actual，并完成
  双报告确定性与隐私验证
- Blocker fingerprint: none
- Next proof: 将稳定入口接入统一 CI case inventory 后，由 CI 保留后续模型版本的趋势证据
- Stop condition: SATISFIED；当前代码可从真实提取任务目录自动发现 Actual 与过程证据，快速对比
  Accepted Gold，并稳定生成机器报告和产品可读报告
- Product objective: 每次用户内容提取后，用一个稳定入口快速比较 Accepted Extraction Gold，
  同时生成机器报告和产品可读报告
- Source contract: `docs/docfit-02-testing-and-iteration.md`、
  `docs/docfit-03-gold-system-design.md`、`docfit-student-content-extraction-gold/v2`、
  `docfit-source-order/v1`
- Stable entry: `docfit eval-student-content --actual <extraction-task-dir> --gold <gold-file-or-package> --output <report-dir>`
- Automatic Actual discovery: `student-content.json`、`work/student-inventory.json`、
  `work/agent-evidence.json`
- Outputs: `student-content-eval-report.json`、`student-content-eval-report.md`
- Verdict dimensions: provenance、source coverage、Registry field semantics、value fidelity、
  semantic grouping、content order、hierarchy/relations、live run evidence
- Privacy boundary: Gold 仅在 Agent 完成后作为 oracle 读取；报告不含学生正文或字段值
- Failure semantics: PASS exit 0；质量 FAIL 或 INPUT_ERROR exit 2；候选 Gold 和漂移输入 fail closed
- Verification: Ruff、strict mypy、CLI/contract pytest、Student 001/002/003 accepted Gold v2
  schema/order compatibility check、跨源/共享源 synthetic contract
- Saved-process E2E proof: 已用
  `temp/student-content-extraction-eval-20260812/student-002-actual-live-v2/` 的真实 API 过程产物
  通过正式 CLI 对 Student 002 accepted Gold r5 连续执行两次。两次均按质量合同返回
  `FAIL`/exit 2，并稳定生成相同字节的 JSON 与 Markdown 报告；JSON SHA-256 为
  `23aa022ab4f327f9a0f82fb0554a37f8bf5ac636cdfb6384160ed9670a69965c`，Markdown
  SHA-256 为 `734b14172c7009fea9bab05f5b1b682cdbb95fb133968567f3258c2d873596fa`。
  报告完成 188/188 Gold 源引用对齐，识别 12/12 batch 的真实 backend/session 证据，且
  Actual/Gold 长字段值反向泄漏扫描均为 0。质量 `FAIL` 来自 Actual 与 Gold 的真实差异，
  不是入口故障。
- Direct-live E2E proof: 已用冻结 Student 002 源文件与 Registry v0.3 全新运行
  `student-002-actual-live-v4/`，任务自身 `run-report.json` 与 `student-content.json` 均直接为
  `READY`，无需保存后恢复。运行包含 12/12 个带 backend/session 的真实批次，191 个内容项，
  371 个源对象全部覆盖。正式 Eval 对 Gold r5 完成 188/188 直接 ID 对齐：provenance、source
  coverage、value fidelity、live evidence 为 PASS，field semantics 178/188、semantic grouping、
  content order 和 hierarchy 为 FAIL，因此总 verdict/exit 为 `FAIL`/2。两次 Eval 报告字节级
  稳定，JSON SHA-256 `6df80d9901b9a7682889e646c598861209b6f8bf1f75acae791d870efed09513`，
  Markdown SHA-256 `842085bf308d8ac86bf0d9e9bd11ade29a0a26617523266f7d1cb81350422ebe`；
  Actual/Gold 长字段值泄漏扫描均为 0。
- Student 001 evidence: `student-001-actual-live-v1/` 以 relation out-of-scope 阻断；修复后
  `student-001-actual-live-v2/` 完成 20/20 真实 batch，随后暴露并修复 table→`appendix.body`
  (`section`) 的类型兼容缺口。保存 raw/evidence 离线恢复得到 319-item `UNSUPPORTED` Actual，
  正式 Eval 完成 248/248 locator crosswalk、value fidelity 240/240 和 live evidence PASS；总
  verdict 因 actual not ready、coverage/field/grouping/order/hierarchy 差异为 FAIL
- Student 003 evidence: `student-003-actual-live-v1/` 的 8/8 batch 暴露非 classified annotation
  携带 field_id 的扁平 Schema 不变量；`student-003-actual-live-v2/` 验证过中间 composition
  Schema，但该设计被架构不变量拒绝，只保留作诊断证据。最终代码上的
  `student-003-actual-live-v3/` 直接生成 124-item `UNSUPPORTED` Actual：114 classified、2
  layout_only、8 unregistered、18 relations，370 个源对象全部守恒，8/8 batch 均带独立
  backend/session。真实返回中有 1 条无本批 primary endpoint 的关系被安全丢弃并写入 batch
  evidence，任务未被中止。正式 Eval 完成 126/126 locator crosswalk；provenance、hierarchy、
  live evidence PASS，field semantics 107/110、value fidelity 104/107、semantic grouping 99/110；
  总 verdict 因 actual not ready、coverage/field/value/grouping/order 差异为 `FAIL`/exit 2。两次
  报告字节级稳定，JSON SHA-256
  `699b2dd8a0a9ec0606fbd581f4f727cb2b6807a0e140533d30b438dee69924dd`，Markdown
  SHA-256 `d49560fc1c9ee60a47ddd1aede39801ab65d13bda7b99a5d97d9daadb6a6574e`；
  Actual 91 个、Gold 85 个长字段值在双报告中的反向泄漏命中均为 0
- Runtime fixes from real E2E: 保持兼容 backend 的扁平 structured-output schema；无本批
  primary endpoint 的关系由应用丢弃并计入 batch evidence/uncertainty；非 classified annotation
  的 field_id 由后处理清空并留 note；物理 table/image/equation/structured object 可承载 Registry
  `section` 语义容器。官方 Claude structured-output 文档确认 JSON Schema 只保证 schema 内
  约束，应用仍需对业务不变量负责：`https://platform.claude.com/docs/en/build-with-claude/structured-outputs`
- Verification note: 本轮 37 个定向 contract/unit/integration tests 通过，Ruff、5 个源文件的
  strict mypy、`git diff --check` 与扁平 Schema 不变量检查通过；Student 001/002/003 Accepted
  Gold 物化检查均未漂移。旧 `docfit-student-content-actual/v1` 过程产物被入口以
  `unsupported_actual_schema`/exit 2 明确拒绝。额外尝试的 `docfit eval --suite core` 在进入
  case 前被当前 OfficeCLI 拒绝创建合成 fixture，属于既有 core-suite 环境门，不影响本入口
  的确定性比较证明，但仍需在该环境恢复后重跑
- No-touch scope: extraction Agent prompt/backend routing、Content Field Registry、Extraction
  Gold 内容、Template Filling Eval
- Process-evidence note: Student 002 `actual-live-v2` 与 Student 001 `actual-live-v2` 均保留为
  “原在线终态 + 后续确定性恢复”的过程证据，不冒充在线直接成功；Student 002
  `actual-live-v4` 已提供直接 READY 发布证明。Student 003 `actual-live-v2` 使用后来撤销的
  中间 Schema，只作诊断证据；`actual-live-v3` 才是当前最终代码的直接在线证明。Student 003
  v3 的 `UNSUPPORTED` 能证明入口和证据链工作，但不代表提取质量已达 Gold
- Parked work: 将该命令接入后续统一 CI case inventory；单独优化 Student 001/003 的
  unregistered/unsupported、跨源共享事实合并、coverage、字段和值差异，不与入口验收混为一项
