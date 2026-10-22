# M0 迁移资产清单

快照日期: 2026-08-02

本文是清单，不是迁移批准。M0 不复制 legacy runtime 代码。任何源代码被 vendored
或改写前，都必须先解决许可证状态。

| 资产 | 来源与版本 | SHA-256 | 许可证 | M0 处置 | 候选目标 | 能力缺口 |
|---|---|---|---|---|---|---|
| `convert-thesis` 编排 Skill | `/Users/fl/.codex/skills/convert-thesis/SKILL.md`；本地快照 2026-07-31 | `e97ac2ec9c75cd474eadb59eea7e853e2e81e025d1c551937e65726e2d83482a` | 未声明；需要许可清理 | P1 已在不复制该 source 的前提下独立重写产品 Skill；许可清理前只保留为参考 | `.claude/skills/convert-thesis/SKILL.md` | 替代实现现在消费五个真实 Tool、可选只读 `docfit-unit-analyst`、已选择的通用 Knowledge 和 Agent-owned `needs_input`；Adobe/live 完成证据仍在该 legacy 资产之外 |
| 转换参考 contract（`anchors.md`、`library-contract.md`、`ooxml-recipes.md`、`pitfalls.md`） | `/Users/fl/.codex/skills/convert-thesis/references/`；本地快照 2026-07-31 | Manifest `a669af104274c832cb4f27c4498b24eb616ede092bbe2e83e9bc1080f71166a5` | 未声明；需要许可清理 | 复核并选择性重写；M0 不复制 | 未来 Tool contract tests、具体 backend notes，以及去学校化后的通用 Knowledge 候选 | Recipes 尚未归一化到公开 Tool contract 或 all-or-nothing 发布模型；学校特定值必须继续留在任务证据中 |
| DOCX 分析与审计脚本（`_docx_utils.py`、`dump_docx.py`、`check_content.py`、`check_placeholders.py`） | `/Users/fl/.codex/skills/convert-thesis/scripts/`；本地快照 2026-07-31 | Manifest `d5b7e595369a5eb0b3e931a614da96937663c64f4d234527f8518d08e183c55f`；`_docx_utils.py` `0b0a0912b5b89e5116baa102c902ed5bbfb8bee8e9bf23e339b87497a39dfcbf`；`dump_docx.py` `01f1cc42385e9de0f01ffc3ea99921438427b6cbb84ab3e0c9b2cbfc54d624a7`；`check_content.py` `3491c1de76987298a2bb08ffe59856b6f791f2f78cffbd512edc48479416df2f`；`check_placeholders.py` `cfc04adce722ce89651fe36b56bb9606480b1af77acdce3b8c3c5688d2816b41` | 未声明；需要许可清理 | 未复制 source；M1 已按批准 contract 重新实现最小行为 | `src/docfit/tools/` 加 `tests/contract` 和 `tests/integration` | stable schema、task-root enforcement、atomic publication 和 postcondition checks 已具备；unsupported OOXML 对象仍作为显式风险，而不是静默成功 |
| 渲染和页面测量脚本（`render_pages.py`、`measure_pages.py`） | `/Users/fl/.codex/skills/convert-thesis/scripts/`；本地快照 2026-07-31 | Manifest `b661fcc6092e469e0147cb2c1b6c71e82a9fb6e03eb254f951df089c9b34f049`；`render_pages.py` `df2a9b5bcb620bb507fc5054a4189011a41f384a1fa72a60f33ae1d513b2691e`；`measure_pages.py` `e5efecfb8b47370a7d175e1a0c5521870f70200d194f5af945e227896adb43f2` | 未声明；需要许可清理 | 未复制 source；固定 OfficeCLI/Adobe PDF Services 路由和本地图像派生已独立实现 | M1 `docx_render`、`docx_visual_review`、layout mapping 和 integration fixtures | legacy render 代码未使用；OfficeCLI feedback/bbox 与 Adobe service conversion 有独立 adapter 和测试 |
| Adobe PDF Services SDK sample bundle 与 service-principal 配置 | `/Users/fl/Downloads/PDFServicesSDK-PythonSamples.zip`；本地 bundle 2026-07-30 | `b261ea803b4cc0923fbd058d356d3852ca63cad723c527c5507855eb93af50c8` | 示例代码 MIT；API 使用仍受 Adobe service terms 和账号 quota 约束 | 只参考 SDK version/API shape 来实现命名 adapter；仓库未复制 credential 或 sample body。三个 credential 值已迁移到仓库外 `~/.config/docfit/agent.env`，权限 `0600`；源 ZIP 保留为 `0600` | `src/docfit/tools/adobe.py`、`pyproject.toml`、`uv.lock`、provider doctor 和 tests | Adobe 提供托管 conversion，但不提供 server font inventory/substitution；证据把该环境记录为 opaque。cache miss 会消耗 Document Transactions |
| `docfit-school-extract` Skill 与 evidence template | `/Users/fl/.codex/skills/docfit-school-extract/`；本地快照 2026-07-31 | Package manifest `785bcca8197aa593846f91b6517704d2b0e0e0c50c8adc6c4ac30d8e17ffbe44`；Skill `acb264c2828f4d5b8baf52b11427e1a6c667819fc56816f590c176421966786c`；template `628d2db061aa6702b47249f8887a8d22ace27cb6d0f0872ddba5e7701117e403` | 未声明；需要许可清理 | P1 已按批准 contract 创建新的 task-scoped Skill，未复制 legacy school-package output model | `.claude/skills/docfit-school-extract/SKILL.md` 加 task-scoped extraction evals | 实现输出仍是 current-task evidence；学校结论永远不进入产品 Knowledge |

## Hash 方法

完整 hash 是标准 SHA-256。package manifest hash 是所含文件 SHA-256 行排序后的
SHA-256。由于这些本地 Skill 可独立变更，迁移前必须重新 hash 来源快照。

## M0 结论

- 两个本地 Skill 是有用参考输入，但没有声明许可证。
- 直接迁移: 无。Product Skill 和 Tool 行为已基于批准 contract 独立重写；未授权 legacy source
  只作为参考，不是 runtime 所需内容。
- M0 阶段没有任何资产可以安全复制进产品 runtime。
- P1 已替换 discovery marker 并创建第二个 Skill，没有复制未授权 source body，也没有引入学校持久化。
  M1 锁定 OfficeCLI 1.0.143 和 Adobe PDF Services SDK 4.2.0，在没有 Provider selector/interface
  的前提下实现固定路由，并且没有复制 legacy source。未来任何 source reuse 仍需要独立许可清理
  和已记录的目标 hash。
