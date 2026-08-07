# DocFit 模板提取静态 E2E Eval 执行胶囊

- Capsule status: `IMPLEMENTATION_PASS / HUMAN_GOLD_GATE_PENDING`
- Source design: `docs/plans/docfit-template-extraction-eval/DESIGN.md`
  (`ff57efcf78144a7528a5149ecae9901fdeda5656bb5dc12a37f78df14a7021b0`，文档收尾 hash)
- Source plan: `docs/plans/docfit-template-extraction-eval/PLAN.md`
  (`8212c1305916eae5c533f615e71c11dfeebb95b6f90f3a7341179db013191f99`，文档收尾 hash)
- Approval source: 用户批准顶层设计、逐代码至少 3 个简单测试、Eval 与产品代码解耦，随后
  明确要求“开始实施”
- Current development gate: G3 minimal vertical slice `PASS`；W0/G1 和 W1–W4/G2 证据已通过；
  三校 Human Gold 与正式质量资格仍属于后续 G5，不作 M3 PASS 声明
- Completed slice: W0–W5；三校 candidate 目录与拒绝评分门已完成
- Pending slice: W6 Human acceptance、每校自比较/文字反例/字段反例共 9 条正式回归
- Isolation contract: 所有新增运行代码、依赖、测试和输出位于
  `evals/template-extraction/**`；没有修改或 import `src/docfit/**`

## 已交付能力

1. 独立 `pyproject.toml`、`uv.lock`、wheel/sdist、`run_eval.py` 和 `.runs/**`。
2. case、fill contract、Registry、Eval config、report 五类 schema 与 scoring-v1。
3. S00–S13 确定性合成 DOCX/YAML fixture。
4. Actual/Gold 共用的只读 DOCX facts：内容、story/结构、有效样式、关系和结构化对象。
5. ID/locator/tag/anchor 对齐，重复候选显式 `AMBIGUOUS`。
6. protected 四分项、slot 四分项和 Gold 声明的 remove 残留断言。
7. 双 50 分视角、八个分项、slot inventory F1、coverage、provisional 与硬失败结论。
8. 同一 report model 原子发布 `template-extraction-eval-report.json/.md`。
9. candidate Gold 状态硬门：三校均返回 `GOLD_NOT_ACCEPTED`，不得形成质量分数。

## G3 Gate Report

- Gate conclusion: **PASS（独立合成纵向链路）**
- Formal school Gold conclusion: **NOT_READY / HUMAN_GATE_PENDING**
- Contract baseline:
  - Actual 模板、Actual 填写契约、Gold 模板、Gold 填写契约；
  - Registry ID/version/hash、marker protocol、Eval config 和 scoring version/hash；
  - 输入错误无分数；质量 `PASS/FAIL/UNKNOWN` 与数值分数分离。
- Acceptance-to-test mapping:
  - S00 → `PASS`、100、protected 50/50、slot 50/50、coverage 1；
  - S01–S06、S08、S09 → 单变量 `FAIL`，issue 归因到预期维度；
  - S07、S10 → `UNKNOWN`、provisional，未静默判为 PASS；
  - S11 → `INPUT_ERROR`、退出码 3、不创建报告目录；
  - S12/S13 → 表格合并和公式/域/书签 facts 正例；
  - 三校 candidate → 3/3 `GOLD_NOT_ACCEPTED`。
- Module verification:
  - `uv lock --check` → PASS；
  - `uv build` → PASS，独立 wheel/sdist；
  - `uv run ruff check .` → PASS；
  - strict mypy（20 个生产 Python 文件）→ PASS；
  - `uv run pytest -q` → **99 passed**；
  - dependency tree → 仅标准运行依赖 `PyYAML`、`jsonschema`，无产品、Claude 或 renderer；
  - static import scan → 无 `import docfit` / `from docfit`；
  - `git diff -- src/docfit pyproject.toml uv.lock` → 空，产品源码和根依赖未改。
- Project regression:
  - root `uv lock --check` / `uv build` → PASS；
  - root mypy → **46 source files PASS**；
  - root pytest → **323 passed, 1 existing deprecation warning**；
  - `docfit doctor` → overall PASS；
  - `docfit eval --suite core` → **7/7 cases, 58 assertions, 2 rendered pages PASS**；
  - scoped `ruff check src tests evals/template-extraction` → PASS；
  - full-root `ruff check .` → BLOCKED only by pre-existing import ordering in
    `test/build_clean_plan.py` and `test/run_officecli_diagnostic_candidate.py`; this work package
    did not modify those user files.
- Input safety: runner rechecks all eight bound input hashes before report publication；输入只读；
  报告默认不复制整篇正文。
- Product boundary: 产品 `docfit --help` 仍使用既有命令集合；新 Eval 没有产品子命令。

## 剩余 Human Gold 门

- 三校逐槽 field semantics、required/cardinality、value style、protected/remove Truth 未签字；
- HUNAU/NJAU validation findings 未修复或人工裁决；
- PKU 当前 snapshot 不自动继承历史 r02 Human signoff；
- Git/CI/data permission 需形成明确 accepted 记录；
- 通过后才可把 case/contract/review 三层状态原地改为 accepted，并运行每校 3 条正式回归；
- 在此之前不得计算三校通过率，也不得宣称 G5 或 M3 完成。

## Documentation drift

- 专项 DESIGN、PLAN、Eval README 和本 capsule 已与 W0–W5 实现同步；
- `doc-keeper` focused audit 已检查 00/01/02/03/06：01 无漂移；00/02/03/06 已只更新
  “独立静态 runner 已有合成证据”的事实，没有把 candidate 写成 accepted Gold，也没有把
  静态 Eval 写成完整 M3 已完成。
