# DocFit 学校模板提取 v2 执行胶囊

- Capsule status: `COMPLETE / W0-W5 CANDIDATE`
- Source design: `docs/plans/docfit-school-extract-v2-candidate-skill/DESIGN.md`
- Source plan: `docs/plans/docfit-school-extract-v2-candidate-skill/PLAN.md`
- Approval source: 用户批准当前候选设计并要求先提交，再完成开发、生成实际提取模板；
  Word 模板内容效果由用户人工判断，其余实现与质量门由本工作包负责
- Baseline commit: `e0aee96`（`docs: simplify school extraction v2 contract`）
- Implementation commits: `7f36c21`（zero-mutation tracer）、`ff475ee`（transactional mutation）、
  `db65d48`（SDK Agent/CLI）、`169f207`（真实运行发现的 lineage/style 合同加固）
- Latest user constraint: 当前开发阶段不处理模板是否固定；何昌期材料与当前候选计划冲突时，
  以当前候选计划为准
- Completed slice: W0–W4 的 observe/query/images、安全 materialize/clear、mutation/final compare、
  两个 compiler 和独立原子 build 已从公开 Tool 边界贯通；paragraph/run locator 均有合同保护
- Completed slice: W5 候选 Agent 与 `docfit prepare-template` 已接通 SDK 原生 MCP Tool、filesystem
  Skill、permissions、structured output、backend timeout/failover 和应用层磁盘重验
- Real SDK proof: 合成输入由 Kimi 在一个 query/session 中加载 Skill，并经 observe/compare/build
  生成严格四文件产物
- Real school proof: 南农候选位于
  `temp/docfit-school-extract-v2-njau-real-r2/output/template-artifact/`；最终模板 SHA-256 为
  `f6646ccc3beeb74b77ed51568a1f9d45b6ae91a02d4a1f1d494d4ef9f8c4186e`，18 slot、4 manual、
  3 gap、0 unresolved，12 页 candidate verification 完整
- Contract repair: 真实运行发现“变更模板可携带空 mutation lineage”和“扁平观测样式可泄漏进
  公开 fill contract”两个缺口；compiler 与 builder 现均 fail closed，最终候选已用 18 项预期变化、
  0 项意外变化的完整 lineage 和规范化 `font/paragraph` 样式重新构建；旧版保留为
  `output/template-artifact-pre-lineage/` 与 `output/template-artifact-pre-style-contract/`，不作为交付
- Quality evidence: 根项目全量 `348 passed`，最终受影响 Tool/Agent/CLI 合同 `42 passed`；root
  lock/build、ruff、strict mypy、doctor 通过；真实 fill contract 通过独立 Eval schema；独立 Eval
  lock/build/ruff/mypy 与 `129 passed` 通过
- Delivery proof: 自动化合同、输入安全、原子性、SDK/Tool/CLI、静态质量门和项目回归均须通过；
  必须生成可交付的 `clean-template.docx`、`fill-contract.json`、`visual-review.json`、
  `build-report.json`，再交给用户做 Word 内容效果判断
- Architecture boundary: Claude Agent SDK 原生 Agent loop、MCP Tool、Skill、permissions、hooks、
  structured output 优先；Tool annotations 仅作提示，安全性必须由 handler 和文件合同强制执行
- Production-switch boundary: W0–W5 可在候选组合中独立完成；旧 `docx_*` 转换 Tool 仅在转换侧
  新 Tool 合同完成后按 W6 切换和删除，不在本工作包里静默制造长期兼容层
- No-touch scope: 工作区中现有未提交的全局文档、独立 Eval、LibreOffice 实验及用户临时资料；
  除非实现证明存在不可回避的直接依赖，不修改、不清理、不纳入本工作包提交
- User-owned next step: 打开实际 `clean-template.docx` 判断 Word 内容效果；当前已如实声明槽内示例/
  说明文字清理、说明段落删除和封面复合日期等 4 manual / 3 gap，不把机械 built 表述成内容验收
- Parked: Human Gold 正式签字、W6 转换生产切换、模板 fixed/frozen 生命周期问题；内容反馈若要求
  新删除 mode，再作为下一微切片扩展 compiler、Tool、后置保护与测试
- Stop condition: 最终回归通过并形成语义提交后，本 W0–W5 候选工作包关闭；W6 或全局合同变化
  仍须返回对应决策层
