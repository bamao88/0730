# 用户内容提取模块状态索引

Status: `STUDENT_002_QUALITY_AND_PERFORMANCE_PASSED`
Current module contract: `docs/contracts/user-content-extraction.md`
Current Eval entry: `evals/student-content-extraction/README.md`

本文只记录用户内容提取模块的当前状态、证据入口、blocker 和下一步 proof。实现编排、batch、
并发、prompt、checkpoint identity、历史 timing table 和旧失败过程不在本状态文档中维护。

## Current Summary

```text
Status: Student 002 quality/performance passed.
Proof: Student 002 accepted Gold r5, 188/188 source-bound semantic instances, 8/8 Eval dimensions PASS.
Pending: Student 001/003 live quality closure.
Not this module: template generation failure, final filling failure, final Word product failure.
Next proof: wire accepted cases into the restricted CI case inventory and close Student 001/003 live quality.
```

## Module Boundary

| This module owns | This module does not own |
|---|---|
| Read-only student DOCX snapshot | School template or school requirements |
| Content Field Registry semantic dictionary | Fill Contract or target slot/region choice |
| Source Inventory and Student Content Model | Target style selection or fallback style materialization |
| `items[]` source order, source tracing and classification status | Final Word pagination, TOC, visual acceptance or delivery |
| Offline Actual-vs-Gold extraction Eval | Placement/Filling quality gate |

Final content filling consumes Student Content Model; it must not re-identify student headings,
body paragraphs, figure captions, table captions or equations from raw DOCX text.

## Current Evidence

| Evidence | Status | Location |
|---|---|---|
| Module Contract | current black-box contract | `docs/contracts/user-content-extraction.md` |
| Extraction Gold | Student 001/002/003 accepted Gold v2 | `docs/status/active/docfit-student-content-extraction-gold.md` |
| Eval entry | stable CLI and report contract | `docs/status/active/docfit-student-content-extraction-eval.md` |
| Case inventory | restricted-local inventory, CI wiring pending | `evals/student-content-extraction/case-inventory.yaml` |
| Student 002 live proof | quality/performance accepted against Gold r5 | restricted local `temp/student-content-extraction-eval-20260812/student-002-actual-live-optimized-v1/eval-gold-r5/` |

The restricted proof directories under `temp/...` are local evidence paths, not repository assets.
If absent in a worktree, rerun the case from the accepted Gold package rather than treating the path
as a public fixture.

## Current Blockers

- Student 001 live Actual still needs quality closure against accepted Gold r2.
- Student 003 live Actual still needs quality closure against accepted Gold r2.
- The restricted-local case inventory still needs CI/regression wiring.

These are not user-content-extraction blockers:

- Template generation structure, slot or style-fact failures.
- Final filling placement, style, pagination, TOC or final Word failures.
- Historical Template Workspace contract drift that has already been closed.
- Observability projector latency or other local observer performance work.

## Acceptance Gate

The module is accepted for a case only when:

1. `docfit extract-student-content` exits `0` with `run-report.status == READY`.
2. `docfit eval-student-content` exits `0` against the case's accepted Extraction Gold.
3. Eval dimensions pass for provenance, source coverage, Registry field semantics, value fidelity,
   semantic grouping, content order, hierarchy/relations and live Agent evidence.
4. Reports remain metadata-only and do not copy student content or extracted field values.

Student 002 currently satisfies this gate. Student 001/003 do not become required gates until their
live quality closure is accepted.

## Next Actions

- Keep `docs/contracts/user-content-extraction.md` as the black-box module boundary.
- Keep `evals/student-content-extraction/case-inventory.yaml` as the case/gate source of truth.
- Close Student 001/003 live quality without changing the module's forbidden-read boundary.
- Wire required/trend-only case semantics into the intended CI lane.
