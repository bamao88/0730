# Student Content Extraction Eval Status

Status: stable entry available; CI wiring pending
Module: `user-content-extraction`
Latest accepted module proof: Student 002 Gold r5 quality/performance PASS

## Stable Entry

```bash
uv run docfit eval-student-content \
  --actual <extraction-task-dir> \
  --gold <accepted-extraction-gold-file-or-package> \
  --output <report-dir> \
  --json
```

The command reads one completed extraction task directory:

- `student-content.json`
- `work/student-inventory.json`
- `work/agent-evidence.json`

It writes:

- `student-content-eval-report.json`
- `student-content-eval-report.md`

Gold is oracle-only and is read only after extraction. It must not enter the extraction Agent
prompt, checkpoint, runtime recovery path or Student Content Model.

## Verdict Contract

The report uses `docfit-student-content-extraction-eval-report/v1` and checks:

- provenance
- source coverage
- Registry field semantics
- value fidelity
- semantic grouping
- content order
- hierarchy/relations
- live Agent evidence

CLI exit semantics:

- `PASS`: exit `0`.
- quality `FAIL`: exit `2`.
- input/schema/path error: `INPUT_ERROR`, exit `2`.

Reports are metadata-only: hash, counts, `field_id`, source object IDs, source locator alignment
and session metadata. They must not copy student content or extracted field values.

## Current Case Status

| Case | Gold | Registry | Gate | Current status |
|---|---|---|---|---|
| Student 002 | `2026-08-12.r5` | v0.3 | required restricted | Quality and performance accepted |
| Student 001 | `2026-08-12.r2` | v0.4 | trend only | Gold accepted; live quality closure pending |
| Student 003 | `2026-08-12.r2` | v0.4 | trend only | Gold accepted; live quality closure pending |

The executable case inventory is
`evals/student-content-extraction/case-inventory.yaml`. It is a restricted-local inventory and
is not yet wired into public CI.

## Next Proof

- Wire the restricted-local case inventory into the intended CI/regression lane.
- Keep Student 002 as the required module gate.
- Promote Student 001/003 from trend-only to required only after their live Actual directories
  reach accepted Gold quality without changing the module boundary.
