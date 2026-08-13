# DocFit 模板提取静态 E2E Eval 执行胶囊

- Capsule status: `IMPLEMENTATION_PASS / HUMAN_GOLD_GATE_PENDING`
- Source design: `docs/plans/docfit-template-extraction-eval/DESIGN.md`
  (`0dc6e80eea0c79f236cbfde64ffc64353c52f27363d95fd6796c1c791feb29b1`，文档收尾 hash)
- Source plan: `docs/plans/docfit-template-extraction-eval/PLAN.md`
  (`7524b7f9461cd6f9571d09192c768511c8524097bc008feb9a9a71597c71b269`，文档收尾 hash)
- Approval source: 用户批准顶层设计、逐代码至少 3 个简单测试、Eval 与产品代码解耦，随后
  明确要求“开始实施”
- Latest product decision: 2026-08-13 用户接受规则组签署、湖南农大复合字段、
  南京农大章节角色、三校逻辑页缺失策略和严格 schema 例外门；并明确当前测试阶段以准确度
  为 Gold 核心、来源是否官方只记录，以及每校必须原子交付“可填写 Word + 填写契约”两份
  主文件。这些是重建 v0.5 candidate 的产品输入，不是对当前 v0.1 case 或未生成 hash 的 Gold 签署。
- Current development gate: G3 minimal vertical slice `PASS`；W0/G1 和 W1–W4/G2 证据已通过；
  三校 Human Gold 与正式质量资格仍属于后续 G5，不作 M3 PASS 声明
- Completed slice: W0–W5；三校 candidate 目录与拒绝评分门已完成
- Pending slice: 按 Registry v0.5 重建三校 candidate，完成绑定精确 hash 的样式/
  protected/remove/全页 Word 审查和 W6 Human acceptance，再运行每校自比较/文字反例/
  字段反例共 9 条正式回归
- Packaging hygiene: 三校 `gold/` 均已有 `template.docx + fill-contract.yaml` 核心文件，但 HUNAU
  目录另有未跟踪 Word 锁文件，NJAU 目录另有未跟踪 PDF 与原始参考 DOCX；在不删除用户材料的
  前提下，正式冻结前须将非核心材料移出 `gold/`，保证每校 Gold 目录恰好两份 Truth 文件。
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

- 跨校产品规则已完成 Human 确认；当前三校 case 仍绑定历史 Registry v0.1 和旧槽形态，
  必须按 accepted v0.5 clean break 重建，不得原地只改状态晋升；
- 重建时每校只形成 `final-template.docx + fill-contract.yaml` 两份原子绑定的产品主文件；Eval
  内部的 `case.yaml`、Registry 引用、reviewer 和报告只作元数据/证据；
- 将当前 HUNAU/NJAU `gold/` 中的未跟踪锁文件、PDF 和原始参考 DOCX 安全迁出核心 Truth 目录；
- 当前准确度测试不以来源是否官方作为门；记录来源分类、目标 hash 和冲突裁决即可；
- 重建后的精确槽/区域清单、value style、protected/remove Truth 和物理边界仍需以
  产品可读规则组 + 例外表签署，机器附件须证明逐槽/区域覆盖；
- HUNAU/NJAU validation findings 必须修复；只有证明为 validator false positive 时才可按
  严格证据门形成书面 exception；
- PKU 当前 snapshot 不自动继承历史 r02 Human signoff；
- Git/CI/data permission 需形成明确 accepted 记录；
- 通过后才可把 case/contract/review 三层状态原地改为 accepted，并运行每校 3 条正式回归；
- 在此之前不得计算三校通过率，也不得宣称 G5 或 M3 完成。

## Documentation drift

- 专项 DESIGN、PLAN、Eval README 和本 capsule 已与 W0–W5 实现同步；
- `doc-keeper` focused audit 已检查 00/01/02/03/06：01 无漂移；00/02/03/06 已只更新
  “独立静态 runner 已有合成证据”的事实，没有把 candidate 写成 accepted Gold，也没有把
  静态 Eval 写成完整 M3 已完成。
