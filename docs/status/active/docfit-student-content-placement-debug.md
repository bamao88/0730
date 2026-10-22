# DocFit 用户内容 Placement Debug Active Capsule

- Capsule 状态: `PARTIAL` QUALITY CANDIDATE PRODUCED
- 范围: 一次性 placement/fill debug 状态；历史实现计划已从当前计划清单移除
- 依赖/阻塞登记: `docs/status/active/docfit-student-content-dependencies-and-blockers.md`
- 分支/baseline: `agent/refine-docfit-plan` / `592f7d26d15520c4f62ffeea9ba1f02aeeee741b`
- 用户边界: 学生内容提取、识别和模板填写作为独立模块调试，不与当前模板提取流程联调
- 架构: 一个 SDK 原生只读 Agent extraction；inventory、schema validation、Placement、
  OOXML fill、质量投影和审计均由确定性应用层负责
- 公开能力面: 未新增 CLI、公共 Tool、第三 Skill、第二 Agent loop 或正式产品 schema
- 样式边界: 当前只使用目标模板已有 style 和对象安全 direct formatting；学校样式缺失时的
  DocFit 内置兜底样式库不在本历史调试切片，但已经是进入后续正式阶段前必须完整通过的硬门；
  当前状态见 `docs/status/active/docfit-stable-style-contract.md`
- 隐私: 真实学生 DOCX、正文、Agent structured output 和质量修补 YAML 只在私有任务目录；
  Git 文档仅保存 hash、计数和结论
- 真实 inventory: 371 objects = 214 mapped + 92 dependency-covered + 65 unmapped；记账闭合
- 真实 placement: 8 text slots + 2 block slots；11 required missing；205 selected top-level objects
- 内容证据: selected text missing 0；6/6 drawings、4/4 equations、1/1 student table preserved
- 质量证据: 已删除 29 个安全空段；heading counts 3/10/23；6/6 figures inline 且绑定 caption；
  1 个 student table 已归一化；9/9 task patches 精确匹配；没有 non-template styles
- 占位符格式证据: 8 个已填写 scalar control 已格式化；abstract/keywords 不再继承
  gray placeholder direct color
- 候选证据: 47 product-render pages；SHA-256
  `67832e592043f9e5b368bdb40f6693ba8a90b51df720fe5ebd2bf1c097617cd3`
- 候选产物: `temp/manual-gold-preparation/student-content-real-student-002-hunau-quality-candidate.docx`
  及同级 PDF/run report；均为私有未跟踪调试产物
- 验证: changed-file Ruff PASS；mypy 68 source files PASS；root unit `263 passed`、contract
  `102 passed`、integration `20 passed`；independent template-extraction Eval `151 passed`；real
  content/projection invariants all PASS
- 当前阻塞: candidate template/Human Gold pending；11 个 required missing；65 个 source object
  未映射；generated TOC 尚未物化；TOC cache 需要 Microsoft Word refresh；OfficeCLI 同时拒绝
  unchanged template 和 candidate 且没有 diagnostics，因此 regression status 是 `UNKNOWN`
- 停止条件: 猜测缺失个人信息、静默丢弃 source、把 candidate 冒充 accepted、硬编码真实学生
  修补进产品代码、创建模板不存在的样式、扩张公共接口或与模板提取 Agent 联调
- 下一决策门: 用户复核候选质量；随后分别关闭缺失字段输入、unmapped source 处置、目录
  Word 更新证据，并完成统一内置兜底样式的五维硬门
