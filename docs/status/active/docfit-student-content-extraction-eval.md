# Student Content Extraction Eval 稳定入口执行胶囊

- Capsule status: ACTIVE
- Latest user intent: 继续补齐真实过程端到端证明
- Current slice: 用冻结 Student 002 源文件和 Registry v0.3 执行一次全新在线提取；只有任务
  自身 `run-report.json` 与 `student-content.json` 同时为 `READY`，才进入 accepted Gold 对比
- Next proof: `student-002-actual-live-v4/` 的 extraction run report、Actual/evidence hash 和
  `eval-entry-e2e/` 双报告
- Stop condition: 新运行直接 READY 且 Eval 双报告可重复生成，或遇到凭据/外部模型服务阻断
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
- Verification note: 本轮 32 个定向 contract/unit/integration tests 通过，Ruff 与 strict mypy
  通过。旧 `docfit-student-content-actual/v1` 过程产物被入口以
  `unsupported_actual_schema`/exit 2 明确拒绝。额外尝试的 `docfit eval --suite core` 在进入
  case 前被当前 OfficeCLI 拒绝创建合成 fixture，属于既有 core-suite 环境门，不影响本入口
  的确定性比较证明，但仍需在该环境恢复后重跑
- No-touch scope: extraction Agent prompt/loop、Content Field Registry、Extraction Gold 内容、
  Template Filling Eval
- Process-evidence note: 上述保存目录的 `run-report.json` 记录原始在线收口为
  `NEEDS_INPUT/student_content_value_untraceable`，而其 `student-content.json` 是稍后从已保存
  raw/evidence 确定性恢复得到的 `READY`。因此它足以证明比较入口可用，但不能冒充“一次在线
  提取直接成功”的发布证据；后续应保留恢复动作的独立审计记录，或用一次全新 READY 运行替换。
- Parked work: 将该命令接入后续统一 CI case inventory；Student 002 全新 READY 证明完成后，
  为 Student 001/003 生成当前 v2 Actual
