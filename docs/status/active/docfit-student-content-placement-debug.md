# DocFit Student Content Placement Debug Active Capsule

- Capsule status: `PARTIAL` QUALITY CANDIDATE PRODUCED
- Source plan: `docs/plans/docfit-student-content-placement-debug.md`
- Dependency/blocker register: `docs/status/active/docfit-student-content-dependencies-and-blockers.md`
- Branch/baseline: `agent/refine-docfit-plan` / `592f7d26d15520c4f62ffeea9ba1f02aeeee741b`
- User boundary: 学生内容提取、识别和模板填写作为独立模块调试，不与当前模板提取流程联调
- Architecture: 一个 SDK 原生只读 Agent extraction；inventory、schema validation、Placement、
  OOXML fill、质量投影和审计均由确定性应用层负责
- Public surface: 未新增 CLI、公共 Tool、第三 Skill、第二 Agent loop 或正式产品 schema
- Style boundary: 当前只使用目标模板已有 style 和对象安全 direct formatting；学校样式缺失时的
  DocFit 内置兜底样式库不在本历史调试切片，但已经是进入后续正式阶段前必须完整通过的硬门；
  当前状态见 `docs/status/active/docfit-stable-style-contract.md`
- Privacy: 真实学生 DOCX、正文、Agent structured output 和质量修补 YAML 只在私有任务目录；
  Git 文档仅保存 hash、计数和结论
- Real inventory: 371 objects = 214 mapped + 92 dependency-covered + 65 unmapped；记账闭合
- Real placement: 8 text slots + 2 block slots；11 required missing；205 selected top-level objects
- Content evidence: selected text missing 0；6/6 drawings、4/4 equations、1/1 student table preserved
- Quality evidence: 29 safe empty paragraphs removed；heading counts 3/10/23；6/6 figures inline and
  caption-bound；1 student table normalized；9/9 task patches exact；no non-template styles
- Placeholder-format evidence: 8 filled scalar controls formatted；abstract/keywords no longer inherit
  gray placeholder direct color
- Candidate evidence: 47 product-render pages；SHA-256
  `67832e592043f9e5b368bdb40f6693ba8a90b51df720fe5ebd2bf1c097617cd3`
- Candidate artifacts: `temp/manual-gold-preparation/student-content-real-student-002-hunau-quality-candidate.docx`
  and sibling PDF/run report；均为私有未跟踪调试产物
- Verification: changed-file Ruff PASS；mypy 68 source files PASS；root unit `263 passed`、contract
  `102 passed`、integration `20 passed`；independent template-extraction Eval `151 passed`；real
  content/projection invariants all PASS
- Current blockers: candidate template/Human Gold pending；11 required missing；65 source objects
  unmapped；generated TOC not materialized；TOC cache needs Microsoft Word refresh；OfficeCLI rejects
  both unchanged template and candidate without diagnostics, so regression status is `UNKNOWN`
- Stop conditions: 猜测缺失个人信息、静默丢弃 source、把 candidate 冒充 accepted、硬编码真实学生
  修补进产品代码、创建模板不存在的样式、扩张公共接口或与模板提取 Agent 联调
- Next decision gate: 用户复核候选质量；随后分别关闭缺失字段输入、unmapped source 处置、目录
  Word 更新证据，并完成统一内置兜底样式的五维硬门
