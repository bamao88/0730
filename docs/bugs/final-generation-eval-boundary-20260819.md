# Bug/RFC：final-generation 与 eval/visual evidence 职责边界混入

- Status: `OPEN`
- Severity: `P0`
- Bug type: `architecture-boundary / code-logic`
- Discovered: `2026-08-19`
- Subsystem: `final-generation runtime / eval / quality / visual evidence`
- Related documents:
  - [final-generation E2E 成稿视觉与结构质量回归](./final-generation-e2e-visual-regressions-20260818.md)
  - [final-generation 非代码生成逻辑配套设施问题](./final-generation-supporting-facilities-20260818.md)

## 1. 摘要

`generate-final` 阶段按产品职责应该只负责从学生内容包、学校模板和 Fill Contract 生成 Word 成稿，并完成必要的确定性结构、内容和样式校验。

当前实现虽然文件层面把 `final-generation`、`eval` 和 `quality compare` 分开了，但执行职责已经混入：

```text
Word 生成流程 -> 无条件 LibreOffice render -> TOC/PDF evidence -> validation/report
```

结果是：Docker LibreOffice renderer 不可用时，`generate-final` 会直接失败，哪怕 Word 生成本身并不应该依赖视觉渲染能力。这说明问题不是 AI 在验证阶段主动调用了 render，而是当前 final-generation 核心代码把 eval/visual evidence 的职责硬编码进了生成路径。

目标边界：

```text
final-generation core 只生产和校验 Word。
eval / quality / release gate 才生产 PDF、视觉 diff、gold 对比和发布证据。
```

## 2. 当前代码证据

### 2.1 `generate-final` 没有 Agent 参与

CLI `generate-final` 直接调用 deterministic implementation：

- `src/docfit/app/cli.py:419-435`
- `src/docfit/app/student_content_fill.py:1538-1552`

`run_final_generation()` 的 docstring 明确写着：

```python
"""Run final-generation from hash-bound upstream artifacts without an Agent."""
```

所以这条路径不是 AI 自己调用 render 做验证。

### 2.2 生成核心无条件调用 render

`finalize_saved_final_generation()` 进入共享的 `_finalize_student_content_model()` 后，当前会无条件创建 `DocFitToolService` 并调用：

```python
render, _ = service.render({"input_docx": str(candidate), "overview": False})
```

对应位置：

- `src/docfit/app/student_content_fill.py:1758-1767`

随后报告把 render 结果作为生成报告的一部分输出：

- `candidate_pdf`
- `render_ref`
- `page_count`

对应位置：

- `src/docfit/app/student_content_fill.py:1827-1829`

这让 LibreOffice/Docker 从 eval evidence 依赖变成了 `generate-final` 必需依赖。

### 2.3 eval 层又在 generate check 中要求 PDF

`final_generation` eval 的 generate check 当前也要求 `candidate_pdf` 必须存在：

- `src/docfit/evals/final_generation.py:1233-1238`

这会进一步固化错误边界：即使用户只想检查 Word 生成流程，eval 也会把 PDF evidence 当成 generate 阶段产物。

### 2.4 quality compare 本身也会 render

真正应该需要 LibreOffice 的地方是 quality/visual compare：

- `src/docfit/evals/final_generation_quality.py:74-79`
- `src/docfit/evals/final_generation_quality.py:202-219`

这里需要生成 actual/gold PDF、做 page count 和 visual diff，属于 eval/quality evidence 层，而不是 Word 生成核心。

## 3. 受影响行为

当前混入会导致这些问题：

| 场景 | 当前行为 | 正确行为 |
| --- | --- | --- |
| Docker daemon 未启动或 renderer 镜像不可用 | `generate-final` 返回 `ERROR` | Word 生成仍应完成；只有 visual/quality check 标记为不可执行或失败 |
| 只想验证 Word 内容/样式生成 | 被迫依赖 LibreOffice render | 不需要 PDF renderer |
| eval 跑 `generate` check | 强制要求 `candidate_pdf` | 只检查生成产物和确定性 audit |
| eval 跑 `quality` check | 使用生成报告里的 PDF 或重新 render | quality 层显式负责 PDF evidence，并绑定 actual/gold snapshot |
| TOC 页码需要 PDF text 辅助刷新 | 隐式藏在 generate core 里 | 作为显式 layout materialization / quality evidence step |

核心风险：

```text
生成是否成功、视觉证据是否可用、质量是否达标、是否可发布，被压进了一条执行链路。
```

这会让排障方向错位：环境问题会被误判成生成失败，生成缺陷也可能被隐藏在 evidence 产物里。

## 4. 目标职责边界

### 4.1 final-generation core

负责：

- 校验输入快照身份：
  - source DOCX；
  - student-content JSON；
  - template DOCX；
  - fill-contract；
  - field-registry；
  - quality patches，如有。
- 生成 deterministic Word 产物：
  - `content-partition.json`；
  - `placement.json`；
  - `fill-result.json`；
  - `candidate.docx`；
  - `final.docx`，仅当生成状态可完成。
- 执行非视觉的确定性校验：
  - content audit；
  - style occurrence audit；
  - document/package structural validation；
  - placeholder residue 的 DOCX 结构检查；
  - media relationship/object count 的 DOCX 结构检查；
  - source-selected content coverage。
- 输出明确的 Word 生成状态：
  - `COMPLETE`；
  - `PARTIAL`；
  - `NEEDS_INPUT`；
  - `ERROR`。

不负责：

- LibreOffice render；
- PDF 生成；
- visual review；
- gold visual diff；
- release gate；
- 把 `candidate_pdf` 当成必需产物。

### 4.2 layout materialization / render evidence

如果确实存在必须依赖渲染结果才能完成的任务，比如静态 TOC 页码回填，应拆成显式步骤，而不是藏在 final-generation core 里。

建议命名为独立阶段：

```text
materialize-layout
```

或作为 eval 内部步骤：

```text
generate -> render evidence -> optional layout refresh -> rerender -> quality
```

该阶段负责：

- 调用 LibreOffice；
- 生成 PDF；
- 从 PDF text/index 中读取页码或布局信息；
- 如需修改 DOCX，产出新的布局物化快照；
- 记录输入 DOCX sha256、输出 DOCX sha256、renderer identity、PDF sha256 和 render ref。

重要约束：

```text
layout materialization 是显式后处理，不是 generate-final 默认必需路径。
```

如果没有 renderer，结果应该是：

- Word 生成报告仍存在；
- layout/visual/quality evidence 标记为 `SKIPPED`、`UNAVAILABLE` 或 `FAIL`；
- release gate 不通过；
- 但不能把它伪装成 Word 生成失败。

### 4.3 eval / quality / release gate

负责：

- 按 case 选择 check 组合；
- 对有 gold 的 case 执行 text/structure/media/visual quality compare；
- 调用 LibreOffice 生成 actual/gold PDF；
- 做 page count、visual diff、placeholder residue、media delta 等门槛检查；
- 绑定 evidence：
  - DOCX sha256；
  - PDF sha256；
  - renderer identity；
  - render ref；
  - quality report；
  - release snapshot。
- 输出发布语义：
  - `quality_status`；
  - `release_status`；
  - `releasable`。

不负责：

- 修正文档生成逻辑；
- 在 `generate` check 中强制要求 PDF；
- 把 `generate PASS` 解释成 `quality PASS` 或可发布。

## 5. 建议产物契约

### 5.1 `generate-final` 报告

生成报告应保留这些 Word 层字段：

```json
{
  "schema_version": "docfit-final-generation-report/v1",
  "status": "COMPLETE | PARTIAL | NEEDS_INPUT | ERROR",
  "candidate_docx": ".../candidate.docx",
  "candidate_sha256": "...",
  "final_docx": ".../final.docx or null",
  "final_sha256": "... or null",
  "student_content": ".../student-content.json",
  "content_partition": ".../content-partition.json",
  "placement": ".../placement.json",
  "fill_result": ".../fill-result.json",
  "quality_projection": ".../quality-projection.json",
  "style_audit": ".../style-audit.json",
  "content_audit": ".../content-audit.json",
  "style_occurrence_counts": {
    "failed": 0,
    "unresolved": 0
  },
  "missing_required_count": 0,
  "partial_reasons": []
}
```

这些字段不应是必需字段：

```json
{
  "candidate_pdf": null,
  "render_ref": null,
  "page_count": null
}
```

如果为了兼容旧消费者暂时保留，也必须标成 optional evidence，不得决定 `generate-final` 是否成功。

### 5.2 eval generate check

`generate` check 应检查：

- `candidate_docx` 存在且 hash 匹配；
- `final_docx` 在 `COMPLETE` 时存在且 hash 匹配；
- `style_occurrence_counts.failed == 0`；
- `style_occurrence_counts.unresolved == 0`；
- content audit 无 selected source content 丢失；
- Word package/Office structural validation 没有新增确定性错误。

`generate` check 不应检查：

- `candidate_pdf` 是否存在；
- `render_ref` 是否存在；
- visual changed ratio；
- page count delta；
- gold text similarity。

### 5.3 eval quality check

`quality` check 应显式检查：

- actual/gold DOCX snapshot；
- actual/gold PDF render；
- page count delta；
- text similarity；
- paragraph sequence similarity；
- media delta；
- placeholder residue；
- visual mean/max changed ratio。

这层可以强依赖 LibreOffice，因为它的职责就是视觉和 gold 质量证据。

## 6. 迁移方案

### Phase 1：拆出 render 硬依赖

目标：`generate-final` 在 Docker/LibreOffice 不可用时仍能完成 Word 生成报告。

建议改动：

1. 给 `_finalize_student_content_model()` 增加显式参数，例如：

   ```python
   render_evidence: bool = False
   ```

2. `run_final_generation()` 默认传 `render_evidence=False`。
3. 旧的 student-content fill 或需要兼容的路径，如仍需 PDF，可以显式传 `True`，但应逐步迁移。
4. 当 `render_evidence=False` 时：
   - 不调用 `DocFitToolService.render()`；
   - 不执行依赖 PDF text 的 TOC 页码物化；
   - report 中 `candidate_pdf/render_ref/page_count` 为 `None` 或不出现；
   - `validation` 只保留非视觉结构校验。

### Phase 2：调整 eval generate check

目标：`generate` check 不再强制要求 PDF。

建议改动：

1. 删除或迁移 `final_generation_candidate_pdf_missing` 断言。
2. `generate` check 的 `final_snapshot` 只绑定 DOCX。
3. 如果存在 render evidence，只作为 optional evidence 记录。

### Phase 3：把 render evidence 放到 quality/layout 层

目标：所有 PDF、renderer 和 visual diff 归 eval/quality。

建议改动：

1. `quality` check 调用 `run_final_generation_quality_compare()` 时负责 render actual/gold。
2. 如果 generation report 没有 actual PDF，quality compare 自己 render actual DOCX。
3. gold PDF 永远由 quality compare 或固定 evidence 生成并绑定。
4. 如 TOC 页码需要物化，新增显式 `materialize-layout` 步骤，并在 quality report 中记录它消费和产出的 snapshot。

### Phase 4：更新报告和文档语义

目标：避免后续再把 generate、quality 和 release 混为一个 PASS。

建议改动：

1. README/CLI 输出明确：
   - `generate_status`；
   - `quality_status`；
   - `release_status`；
   - `releasable`。
2. 有 gold 的 release case 默认跑 `input,style,generate,quality`。
3. 没有 quality 或 renderer unavailable 时，release gate 必须不通过，但 generate report 仍可用于排查 Word 产物。

## 7. 验收标准

| 验收项 | 标准 |
| --- | --- |
| Docker 不可用时运行 `generate-final` | 能产出 `candidate.docx` 和 run report；状态由 Word 生成结果决定，不因 renderer unavailable 直接 `ERROR` |
| `generate` check | 不要求 `candidate_pdf`；只检查 Word 生成产物、内容、样式和结构 audit |
| `quality` check | 需要 PDF/visual 时由 quality 层显式 render；renderer unavailable 时 quality/release fail 或 unavailable，不污染 generate 状态 |
| 报告字段 | `candidate_pdf/render_ref/page_count` 是 optional evidence，不是 final-generation 必需产物 |
| TOC/layout | 依赖 PDF text 的页码物化必须是显式 layout/eval 步骤，并绑定输入输出 snapshot |
| 沟通语义 | `generate PASS` 不能被描述为 `quality PASS` 或 `releasable=true` |

## 8. 需要避免的错误修复

不要用这些方式修：

- 在测试里跳过 LibreOffice 错误，然后继续让 `generate-final` 核心无条件调用 render。
- 把 Docker daemon 启动作为 `generate-final` 的前置要求。
- 在 eval generate check 里继续要求 `candidate_pdf`，只是在错误消息里解释得更清楚。
- 为了让测试通过，把 visual/quality 门槛降级到 generate 层。
- 把 TOC 页码刷新继续隐藏在生成核心里。

正确方向是拆边界：

```text
Word generation is deterministic production.
Visual rendering is evidence.
Gold comparison is eval.
Release is a gate.
```
