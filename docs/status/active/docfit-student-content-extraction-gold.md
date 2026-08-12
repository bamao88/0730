# Student Content Extraction Gold 扩样执行胶囊

- Capsule status: COMPLETE
- Source contract: `docs/docfit-03-gold-system-design.md`、accepted Registry v0.3/v0.4、
  `docfit-source-order/v1`
- Latest user intent: 接受 Student 001/003 识别结果，并要求 Gold 显式保存识别内容顺序
- Current slice: Student 001/002/003 均已物化为 `docfit-student-content-extraction-gold/v2`；
  001/003 已由 candidate 晋升 Gold，v0.4 已接受
- Accepted baselines: Student 002 revision `2026-08-12.r5` 绑定 Registry v0.3；Student 001/003
  revision `2026-08-12.r2` 绑定 Registry v0.4
- Proven outcomes: 每个学生都有 Registry 全字段投影、唯一递增 `source_order`、有序
  `source_occurrences`、全源覆盖、0 unresolved、
  0 unregistered、产品核对文档、机器 review、manifest 和可重复 hash；若发现通用新语义先升级 Registry
- Student 001 proof: 244 内容实例、414 源对象、12 图/12 源图片、6 正文表、45 参考文献，
  0 unresolved/unregistered；另有附录表和完整致谢
- Student 003 proof: 111 内容实例、249 源对象、6 个双资产语义图/12 源图片、1 正文表、
  29 参考文献，0 unresolved/unregistered；14 插入修订、10 删除修订、9 条批注均纳入覆盖审计
- Verification: deterministic materializer `--check`、Registry/coverage/order invariants、Ruff、
  定向 tests、top-level Gold hash bindings
- Stop condition: 已达到；三个 Extraction Gold 的字段语义与内容顺序均可机器验收
- No-touch scope: 学校模板提取、Filling placement 语义、原始学生 DOCX
- Parked work: Student 001/003 到具体学校模板的独立 Filling Gold
