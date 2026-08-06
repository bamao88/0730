# DocFit 学校模板提取 v2 执行胶囊

- Capsule status: `ACTIVE / IMPLEMENTATION`
- Source design: `docs/plans/docfit-school-extract-v2-candidate-skill/DESIGN.md`
- Source plan: `docs/plans/docfit-school-extract-v2-candidate-skill/PLAN.md`
- Approval source: 用户批准当前候选设计并要求先提交，再完成开发、生成实际提取模板；
  Word 模板内容效果由用户人工判断，其余实现与质量门由本工作包负责
- Baseline commit: `e0aee96`（`docs: simplify school extraction v2 contract`）
- Latest user constraint: 当前开发阶段不处理模板是否固定；何昌期材料与当前候选计划冲突时，
  以当前候选计划为准
- Completed slice: P1 零 mutation 纵向链路；observe create/query/candidate images、final compare、
  artifact decisions compiler 和四文件 build 已从公开 Tool/产品边界贯通
- Current slice: P2 首个安全 mutation；实现 `materialize_slot` 与独立 `remove_content`，证明只发生
  计划内 OOXML 变化，并让 mutation comparison/lineage 回到同一 build 门
- Next proof: 单一失败 mutation 测试 → compiler/handler 最小实现 → protected/marker/container/hash/
  原子发布拒绝回归 → P1 全链路复用
- Existing evidence: P1 template gate `8 passed`，新增产品代码定向 ruff 与 strict mypy 通过；生成的
  fill contract 通过现有 Eval Draft 2020-12 schema；既有 Skill/Tool 合同 `13 passed`；模板提取
  独立 Eval 基线 `98 passed`
- Delivery proof: 自动化合同、输入安全、原子性、SDK/Tool/CLI、静态质量门和项目回归均须通过；
  必须生成可交付的 `clean-template.docx`、`fill-contract.json`、`visual-review.json`、
  `build-report.json`，再交给用户做 Word 内容效果判断
- Architecture boundary: Claude Agent SDK 原生 Agent loop、MCP Tool、Skill、permissions、hooks、
  structured output 优先；Tool annotations 仅作提示，安全性必须由 handler 和文件合同强制执行
- Production-switch boundary: W0–W5 可在候选组合中独立完成；旧 `docx_*` 转换 Tool 仅在转换侧
  新 Tool 合同完成后按 W6 切换和删除，不在本工作包里静默制造长期兼容层
- No-touch scope: 工作区中现有未提交的全局文档、独立 Eval、LibreOffice 实验及用户临时资料；
  除非实现证明存在不可回避的直接依赖，不修改、不清理、不纳入本工作包提交
- Parked: Human Gold 正式签字、W6 转换生产切换、模板 fixed/frozen 生命周期问题
- Stop condition: 实际模板包与除 Word 内容人工判断外的全部自动化质量证据齐备，并形成语义提交；
  若发现必须改变全局架构、公开合同、W6 边界或不可逆外部状态，先提交用户决策
