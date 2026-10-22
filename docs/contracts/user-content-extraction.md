# 用户内容提取模块 Contract

Status: current black-box contract
Module: `user-content-extraction`
CLI: `docfit extract-student-content`

## Module Goal

用户内容提取模块把一个只读学生论文 DOCX 和一个 Content Field Registry 快照转换为
`docfit-student-content-model/v2`。它只负责学生源内容的忠实、无损、有序、可追溯表达，
不参与学校模板识别、目标槽位选择、样式选择或最终 Word 物化。

## Responsibilities

- 从学生 DOCX 生成一个绑定源 hash 的 Source Inventory。
- 按学生原始阅读顺序输出 Student Content Model `items[]`。
- 将可识别内容绑定到 Registry `field_id`，并显式记录未注册、布局、未决或不支持状态。
- 保留文本、图片、表格、公式等复杂对象的来源和运输引用。
- 生成提取运行报告、Agent 元数据证据和可供离线 Eval 比较的 Actual 目录。
- 只在同一 source/Registry 身份下恢复已有完整提取任务。

## Non-Responsibilities

- 不读取学校模板、学校要求、Fill Contract、模板生成 workspace 或最终生成目录。
- 不决定内容要写入哪个目标 slot/region。
- 不选择学校样式或通用兜底样式。
- 不补写、归一化、翻译、总结、改写或重排学生正文。
- 不把 Gold、参考答案或最终成品放入 Agent prompt；Gold 只允许在提取完成后由离线 Eval 读取。

## Allowed Inputs

CLI 入口：

```bash
uv run docfit extract-student-content \
  --input path/to/student.docx \
  --field-registry path/to/content-fields.yaml \
  --output path/to/extraction-task
```

Allowed inputs are:

- `student.docx`：学生原始论文，只读。
- `content-fields.yaml`：当前任务绑定的 Content Field Registry 快照，只读。
- `output`：缺失或可恢复的提取任务目录。

应用会在任务目录内创建只读快照：

- `input/student.docx`
- `input/content-fields.yaml`

## Forbidden Reads

本模块不得读取或依赖：

- 学校模板或学校要求文件。
- `final-template.docx`。
- `fill-contract.yaml` / `fill-contract.json`。
- Template extraction workspace。
- Final filling / final generation workspace。
- 已接受 Gold、人工 review、最终 Word 或 Placement/Filling 证据。

## Required Outputs

成功或可诊断运行至少产生：

- `student-content.json`：下游 handoff 的 Student Content Model；task-local，包含学生内容。
- `work/student-inventory.json`：Source Inventory；task-local，包含学生内容和源对象事实。
- `work/agent-evidence.json`：metadata-only Agent 证据，不保存学生正文。
- `run-report.json`：metadata-only 运行报告、状态、hash 和 timing。

`work/raw-agent-extraction.json`、batch checkpoint 和 transcript 是内部调试/恢复证据，不是下游
稳定合同。

## Student Content Model Contract

`student-content.json` must satisfy:

- `schema_version` is `docfit-student-content-model/v2`.
- `source_sha256` matches `input/student.docx`.
- `registry` matches `input/content-fields.yaml` identity and hash.
- `items[]` is the only order truth and preserves one unique ascending
  `source_order.block + source_order.inline` sequence.
- Each item has a stable `content_id`, source object IDs, source locators, transport source
  reference, physical type, classification status, confidence and provenance.
- Text values are copied from deterministic source facts. The Agent may classify and relate
  source items, but it must not generate replacement student content.
- Complex objects keep source/transport references so final filling can move the original
  Word object rather than reconstructing it from text.
- `parent_content_id` and `relations[]` cite existing `content_id` values only.
- `source_coverage` accounts for mapped objects, transport dependencies, layout-only objects
  and unsupported objects.

`items[]` is authoritative. `field_results[]` is a derived field index only:

- It answers which Registry fields were extracted and which `content_id` values belong to each.
- It does not define student content order.
- It must not manufacture ordering for fields absent from the source.
- Rebuilding `field_results[]` from `items[]` must not change the formal model.

## Status And CLI Semantics

Model statuses:

- `READY`: all classified/layout-only source items and source coverage are closed.
- `NEEDS_REVIEW`: unresolved, unregistered or conflicting content remains.
- `UNSUPPORTED`: unsupported content or unsupported source objects remain.

CLI semantics:

- `docfit extract-student-content` exits `0` only when `run-report.status == READY`.
- Any non-READY model status, input error or module failure exits `2`.
- On failure, `run-report.json` uses `ERROR` or `NEEDS_INPUT` with a fixed failure code/message.
- A non-empty output directory may be resumed only when it is a complete task bound to the same
  source and Registry hashes; stale or partial directories fail closed.

## Downstream Handoff

Final content filling may depend on:

- `items[]` as the sole student content sequence.
- `content_id -> field_id` bindings for semantic placement candidates.
- item `value`, source object IDs, source locators and transport references for faithful copy.
- `parent_content_id` and relations such as captions or shared facts.
- classification status and coverage for deciding whether the final task needs input or review.

Final content filling must not depend on:

- Agent batch shape, concurrency, prompt text, retry policy or checkpoint identity.
- `field_results[]` order.
- raw Agent output.
- Gold artifacts or Eval reports as runtime inputs.

Final content filling must not re-identify student headings, body paragraphs, figure captions,
table captions or equations from raw DOCX text. If a needed final value is absent or ambiguous in
the Student Content Model, final filling reports the appropriate missing-input state.

## Privacy Boundary

- `input/student.docx`, `student-content.json` and `work/student-inventory.json` are task-local
  and may contain student content.
- `work/agent-evidence.json`, `run-report.json` and Eval reports are metadata-only and must not
  copy student content or extracted field values.
- Real student sources, Gold packages, review images and product review documents stay in
  restricted local storage and must not enter public CI or repository logs.

## Acceptance Gates

Module acceptance is based on the module contract, not on final Word quality:

```bash
uv run docfit eval-student-content \
  --actual path/to/extraction-task \
  --gold path/to/accepted-extraction-gold-package \
  --output path/to/extraction-task/eval \
  --json
```

The Eval gate compares provenance, source coverage, Registry field semantics, value fidelity,
semantic grouping, content order, hierarchy/relations and live Agent evidence. `PASS` exits `0`;
quality `FAIL` and `INPUT_ERROR` exit `2`.

Current accepted module status:

- Student 002: quality and performance accepted against Gold r5.
- Student 001/003: Extraction Gold accepted; live quality closure remains trend-only until the
  current implementation reaches accepted Gold on those cases.
- CI case inventory exists as a restricted-local inventory and still needs CI wiring.
