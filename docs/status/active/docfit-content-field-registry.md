# DocFit Content Field Registry 执行胶囊

- Capsule status: EXPANSION_ACCEPTED
- Source plan: `docs/plans/docfit-content-field-registry/DESIGN.md`
- Latest user intent: Student 002 可作为 Extraction Gold 标准；按同一 Registry 原则准备
  Student 001/003，通用内容先升级 Registry，禁止猜字段或长期留 unregistered
- Current development gate: G1 capability contract；G0 产品边界、责任、非目标和停止门已由
  用户批准并固定在 Source plan
- Baseline commit: `3def71e7b210864c9220f845d107f983f04efcc1`；当前未提交工作树包含用户的
  既有候选设计与文档改动，不作为本 capsule 的 G1 PASS 证据
- Current slice: accepted Student 002/v0.3 不变；Student 001/003 已绑定 accepted v0.4
  完成可复现 Gold 物化。v0.4 保留 54 个字段，新增多资产图、可选源编号题注、结构配对、Word
  自动列表编号和 final-visible 修订/批注来源政策
- Approved scope: Registry 研发期所有权、v0.1/v0.2 历史快照、v0.3 Student 002 pilot 策略、
  消费者最小引用合同、未注册阻断/升级规则、Extraction/Placement 同步与版本/hash 绑定
- Last proven evidence: accepted v0.3 Registry SHA-256
  `a6df179b7a4112672b275289df2e43870ca9a363cb3e46b74a77e9921cff570b`；54 个 field ID
  唯一且命名合法，父字段无断链/环，alignment ID 集合一致，三校 locator 可在
  spec 中闭包；Accepted v0.4 Registry SHA-256
  `8b335cc86b60ed2f391ac696155525841b585be09affcd406042e5ad5e1c3dbb`；Accepted Student 002
  Extraction revision `2026-08-12.r5` SHA-256
  `19c7344b3e67749cabe39a93b5d2f18e95560cfe1f124a5457cb734308bd8c0b`；待独立评审的
  Placement SHA-256 `5d26c7ffc7a0bd07216a9518bc6e89e4877395473637750bace00d875913f425`；顶层和
  logical-unit hash bindings 全部通过
- Completed slices: 责任与非目标、未注册字段、命名/语言/版本政策、v0.1/v0.2 快照、v0.3 pilot、
  Student 002 Accepted Extraction/Placement 候选、产品核对表与图像证据、图像—题注反向配对修正、
  显式编号项列表分类与相邻上下文证据、图表题注去自动编号规范值、Eval 消费者迁移、
  00–06 与专项设计漂移同步；Student 001/003 源对象盘点、v0.4、Extraction Gold、审阅图片、
  产品验收记录和内容顺序合同已物化
- Next slice: 以 accepted Extraction Gold 独立准备 Student 001/003 Filling
- Next proof: Filling 的模板绑定、placement、预期事实和独立 Human 结论
- Gate conclusion: Registry v0.3/v0.4 与 Student 001/002/003 Extraction Gold 均 HUMAN
  ACCEPTED；Student 002 Filling 仍独立 `NEEDS_INPUT`
- Advance requires: Filling 工作包单独授权与验收
- Stop condition: 生产位置、公开 API、M3 或 Human 字段晋升需要新批准
- No-touch scope: 学校提取 v2 设计、不相关代码/文档、用户现有工作区修改
- Parked work: 生产包装与 M3 实施
