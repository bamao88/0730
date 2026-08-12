# Student Content Extraction Gold 与 Eval

本目录只保存可复现脚本；真实学生源、Gold JSON、产品核对文档和图片证据继续保存在
受限的 `temp/manual-gold-preparation/gold/20-student-assets/`，不得进入公开 CI 或日志。

## 当前状态

- `materialize_student_002_gold.py`：重放已验收的 Student 002 Extraction Gold r5；固定绑定
  accepted Content Field Registry v0.3，不因后续扩样自动迁移。
- `materialize_student_001_003_gold.py`：从 Student 001/003 冻结源 Word 直接物化已验收的
  Extraction Gold、全源 inventory、产品验收记录和审阅图片；固定绑定 accepted Registry v0.4。

v0.4 没有新增 canonical 字段；它在同一 54 字段上补齐多资产语义图、可选源编号题注、
源结构优先的题注配对、Word 自动列表编号和 final-visible 修订/批注来源合同。

三个 Gold 均使用 `docfit-student-content-extraction-gold/v2`：`items[]` 按唯一
`source_order.block + source_order.inline` 严格递增；共享事实的所有原始位置保存在有序
`source_occurrences[]`；`field_results` 仅为派生字段索引，不能改变内容顺序。

## 复现与校验

```bash
uv run python evals/student-content-extraction/materialize_student_001_003_gold.py
uv run python evals/student-content-extraction/materialize_student_001_003_gold.py --check
uv run ruff check evals/student-content-extraction/materialize_student_001_003_gold.py
```

当前实现验收必须先调用真实 API 生成 Actual，再通过正式 CLI 做只读 Gold 对比；Gold 不得
进入 Agent 提示词或作为回放结果。CLI 只接收一次提取的任务目录，会自动读取
`student-content.json`、`work/student-inventory.json` 和 `work/agent-evidence.json`：

```bash
uv run docfit extract-student-content \
  --input temp/manual-gold-preparation/student-content-real-student-002.docx \
  --field-registry docs/plans/docfit-content-field-registry/content-fields-v0.3.yaml \
  --output temp/student-002-actual-live

uv run docfit eval-student-content \
  --actual temp/student-002-actual-live \
  --gold temp/manual-gold-preparation/gold/20-student-assets/student-002 \
  --output temp/student-002-actual-live/eval \
  --json
```

稳定输出为 `student-content-eval-report.json` 和 `student-content-eval-report.md`。报告分别
检查来源/Registry 绑定、源覆盖、字段语义、原文值、跨源语义实例拆分/合并、`items[]`
内容顺序、父子/题注关系和真实 API 证据；只保存 hash、计数、field_id、源对象 ID 和
session 元数据，不复制学生正文。`PASS` 返回 0；`FAIL` 或输入错误返回 2，适合本地回归
和 CI gate。Student 001/003 只需替换 `--actual` 与 `--gold`，不再维护按学生写死的脚本。
Gold-local object ID 与当前 runtime inventory ID 不一致时，runner 会在学生源 hash 已一致的
前提下通过稳定 source locator 建立显式 crosswalk；图片采用顶层 paragraph/table host 内的
图片序号别名。crosswalk 不完整或有歧义时 fail closed，不用文本相似度猜配。

`--check` 会在任何 Registry、inventory、Gold、review、manifest 或 review asset 缺失/
漂移时失败。顶层资产 hash 另由 `temp/manual-gold-preparation/gold/hash-bindings.sha256`
校验。既有跨模板转换稿不得作为 Extraction 值的回填来源。

## Human 验收

人工验收已经通过各包的 `product-review.md` 记录，不需要编辑 YAML：

- `student-001/product-review.md`
- `student-003/product-review.md`

Registry v0.4 与 Student 001/003 D1–D9 已于 2026-08-12 接受，Gold revision、
`review.yaml`/manifest/hash 已同步。后续 Filling 仍是独立责任和独立验收。
