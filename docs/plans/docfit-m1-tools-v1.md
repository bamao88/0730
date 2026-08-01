# DocFit M1 五个 Tool 与双固定后端 Preflight

> 状态：DRAFT，等待用户审批
> 日期：2026-08-01
> 上位契约：`docs/docfit-00-index.md`–`docs/docfit-06-development-roadmap.md`

## 已确认的本机证据

- 当前实现仍是五个稳定 Tool 名称加 M0 stub；M1 将替换 stub，不增加第六个 Tool。
- OfficeCLI 可执行文件版本为 `1.0.143`，当前 SHA-256 为
  `2f158d46f9b6c5eb0dfe4eb02038114001e17acc47b67347417c56dcf9659096`；
  [官方仓库](https://github.com/iOfficeAI/OfficeCLI)声明 Apache-2.0。
- OfficeCLI 在当前 macOS 上提供结构化 get/query、默认原子 batch、OpenXML
  validate 和 HTML screenshot；其 native Word render 和 Word page-count 帮助文本
  明确为 Windows + Word 路径。当前没有安装 PDF exporter plugin，因此 M1 只要求
  OfficeCLI 页面截图并将其标为 `approximate`，不把 OfficeCLI PDF 设为完成门。
- 本地 Microsoft Word 版本为 `16.111.2`；应用脚本字典明确提供 read-only open、
  `repaginate`、`save as` 和 `format PDF`。
- 本机存在 `pdftoppm` / `pdfinfo` 26.04.0，可用于 M1 本地 Word PDF 的逐页派生；
  不在 M1 中分发或 vendoring Poppler。
- 用户授权的学生论文与学校模板当前可读，SHA-256 分别为
  `cf49d90832c44d2f28e7fe6940217f4afe7c637f179b3610c75801b900e7d290` 和
  `776649b4af9cfef3a50e859490dd75f1061bfcc2ca2aac20181f73e2bb0361a6`。
  文件与绝对路径只用于本地验证，不复制到仓库、测试日志或提交产物。
- Provider-independent 通用 Knowledge Package v1 已完成；M1 不引入学校资产、
  profile 或任务证据持久化。

## 执行顺序与硬停止门

1. 先在只读输入和隔离工作副本上完成两个具体后端的 PoC，并锁定五个 Tool schema、
   错误语义、固定路由和证据字段；PoC 未通过前不迁移旧脚本。
2. OfficeCLI adapter 负责 inspect/edit/validate/`edit_feedback`；每次调用设置
   `OFFICECLI_SKIP_UPDATE=1`，使用 argv 而不是 shell 拼接，并记录路径、版本和 hash。
3. Word adapter 只负责 `baseline_pagination`、`pagination_recheck` 和
   `final_verification`：静态 AppleScript 通过 argv 接收已授权路径，read-only 打开，
   只关闭自己打开的文档且不保存源文件，不退出整个 Word 应用。
4. `docx_edit` 必须支持最小 `import_template_sections`。若 OfficeCLI 无法复制样式、
   编号、媒体、relationships、页眉页脚和节属性的依赖闭包，可在具体 OfficeCLI
   adapter 内增加最小 OOXML 补丁；若需要 fork、第三个引擎、通用 Provider 接口或
   部分发布，停止为 `BLOCKED_NEEDS_DECISION`。
5. Word 自动化权限、完整 PDF 导出、逐页派生或真实性证据任一无法本机验证时，停止为
   `BLOCKED_NEEDS_LOCAL_VALIDATION`；不得以 OfficeCLI 结果替代。
6. 实现完成后同步 00–06、README、迁移清单和 active capsule；M0 图片 smoke 与默认拒绝
   权限边界必须继续通过。

## Preflight contract

```text
Preflight status: DRAFT
Task source: 用户批准的双固定后端决策 + docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md + 当前 M0/Knowledge 实现证据
Canonical source: docs/plans/docfit-m1-tools-v1.md
Route: durable $intuitive-flow
Goal: 在不运行 Agent 转换链路的前提下，让五个 DocFit Tool 通过 OfficeCLI 与本地 Word API 的固定薄适配安全、可审计、可独立运行。

Scope:
- 固化五个 Tool 的版本化 JSON Schema，以及 status/checks/warnings/failure/committed/render_ref/object_ref 语义。
- 用当前文档 hash、opaque object_id 和 fingerprint 实现快照级 object_ref；跨 hash 拒绝旧 ref 并要求重新 inspect。
- 实现 OfficeCLI inspect/edit/validate/edit_feedback，所有写入使用工作副本、默认原子 batch、后置重读和原子发布。
- 实现 import_template_sections 的最小安全依赖闭包、ID/relationship 冲突重映射与 all-or-nothing 证明。
- 实现 Word baseline_pagination/pagination_recheck/final_verification：完整 DOCX 一次导出 PDF，本地派生 PNG，固定 revision_display 并记录 Word/字体/缓存证据。
- 实现封闭 render 路由矩阵；公开输入不提供 provider/backend selector，固定后端失败不跨职责回退。
- 将 docx_visual_review 扩展为 pages/crops/contact_sheet/compare 图片 content blocks，同时保留 M0 image smoke 健康检查。
- 让 docx_validate 通过 OfficeCLI、独立 package/内容/当前任务规则/视觉覆盖后置检查重新取证，不信任编辑器自报成功。
- 实现任务根路径授权、源文件 hash 保护、超时、资源上限、临时文件清理、缓存失效和脱敏诊断。
- 实现 docfit tools inspect/edit/render/visual-review/validate 开发者命令，并让 doctor --require provider 检查两个固定后端、字体与本地 PDF 工具。
- 增加合成 fixture、unit/contract/integration 测试和两个用户授权文件的本地只读 PoC。
- 在能力证据改变现有声明时，同步长期文档、README、迁移清单与 active capsule。

Non-goals: M2 docfit convert、真实 Agent 论文转换、重写 convert-thesis Skill、当前任务学校证据持久化、学校资产/选择/profile、第三个引擎、LibreOffice/Aspose 回退、通用 Provider 接口/注册表/动态选择/故障转移、Word 编辑或常规验证、API/GUI/任务队列、并发 Word 作业、M3 真实论文交付质量声明。

Entity budget: reuse=五个 Tool 名称、M0 权限/图片 smoke、现有 app/tools/knowledge 归属、OfficeCLI CLI、本地 Word scripting dictionary、标准库 zip/hash/subprocess、现有授权样本；remove/merge=用真实 schema/handlers 替换 M0 stub，不保留第二套 Tool 注册或兼容导入面，旧脚本只迁移经证据证明的最小逻辑；new=两个按名称明确的具体 adapter、Tool schema/result models、快照 ref 与任务内 render/cache helpers、一个锁版本与许可证的 Pillow 图片处理依赖（用于 crops/contact-sheet/compare）、开发者 tools CLI、合成 fixtures 和分层测试；expansion triggers=需要第三个引擎且需要动态选择/故障转移、需要 fork OfficeCLI、需要分发 Poppler、需要并发 Word 自动化、或需要第六个公开 Tool 时重新审批。

Context: must-read=AGENTS.md, docs/docfit-00-index.md–docs/docfit-06-development-roadmap.md, docs/plans/docfit-m1-tools-v1.md, docs/status/active/docfit-m0.md, docs/status/active/docfit-knowledge-package-v1.md, docs/migration-asset-inventory.md, src/docfit/tools/, src/docfit/app/doctor.py, src/docfit/app/cli.py, tests/contract/; useful=docs/plans/docfit-knowledge-package-v1.md, current OfficeCLI help/schema, Microsoft Word Word.sdef, user-authorized local sample hashes, legacy conversion references after re-hash/license check; avoid-unless-needed=Provider candidates outside the two fixed backends, M2–M5 implementation, historical workflow/runtime designs, unlicensed legacy source bodies before reuse approval.

Acceptance:
- SUCCESS: 五个 Tool 可脱离 Agent 独立运行；OfficeCLI 与 Word 各自通过职责契约；封闭路由、source hash、opaque refs、atomic edit、independent validation、真实图片 blocks 和 provider evidence 均有自动断言。
- SUCCESS: import_template_sections 在合成模板/论文上复制完整依赖闭包、重映射冲突并保持非目标内容；任一操作失败时无 committed 输出。
- SUCCESS: docfit doctor --require provider 在本机对 OfficeCLI、Word、字体、pdftoppm/pdfinfo 返回 PASS，并报告实际版本/hash而不打印文档内容。
- SUCCESS: 用户授权的学生论文和模板完成 Word 初始基线、OfficeCLI 高频预览、一次有明确理由的 Word recheck fixture 和最终 Word PDF 本地证明；两个源文件 hash 保持不变，输出可打开且证据绑定正确。
- BLOCKED_NEEDS_DECISION: import_template_sections 需要 fork/第三个引擎/通用 Provider 抽象，OfficeCLI 官方二进制无法证明来源或许可证，或必须新增第六个 Tool；否则 none。
- BLOCKED_NEEDS_LOCAL_VALIDATION: Word Apple Events 权限、Word 16.111.2 导出、字体环境、Poppler 派生、用户授权样本或真实 OfficeCLI 1.0.143 任一 required gate 无法运行。
- INTERMEDIATE_ONLY: none；除非用户另行批准，不把只有 mock/近似渲染的分支称为 M1 完成。
- No regressions: 五个 mcp__docfit__ 名称、默认拒绝权限、M0 三个 live smoke、通用 Knowledge v1 单元测试、源文件只读、无正文日志、base doctor/CI 行为保持。

Verification: deterministic=uv sync --frozen; uv lock --check; uv build; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run docfit doctor; git diff --check；integration=真实 OfficeCLI contract/integration suite + Word adapter 的受控 fake/fixture contract + 路由/缓存/ref/atomic publication tests；product-run=docs/docfit-06-development-roadmap.md M1 的五条 docfit tools 命令及 baseline/recheck/final 三条 render 命令；local-live-manual=officecli 1.0.143/hash proof、Word 16.111.2 read-only repaginate/save-as-PDF、pdftoppm/pdfinfo、用户授权两文件 hash 前后对比、页面/contact-sheet 视觉抽查、uv run docfit doctor --require provider；optional=OfficeCLI MCP 仅用于对照 PoC，不进入产品路径。
Execution: main=主会话持有根 goal，按 PoC→schema→实现→contract/integration→local Word proof→doc-keeper 顺序监督并在停止门处停止；worker=none；worker-goal=none。
To execute: /goal execute docs/plans/docfit-m1-tools-v1.md with intuitive-flow
Optional tracking: none
Approval: LGTM/approve/go ahead approves; edits request revision.
```
