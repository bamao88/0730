# Student Content Extraction Gold Status

Status: accepted Gold set complete
Gold schema: `docfit-student-content-extraction-gold/v2`
Ordering contract: `docfit-source-order/v1`

## Accepted Baselines

| Case | Revision | Registry | Status |
|---|---|---|---|
| Student 002 | `2026-08-12.r5` | v0.3 | accepted |
| Student 001 | `2026-08-12.r2` | v0.4 | accepted |
| Student 003 | `2026-08-12.r2` | v0.4 | accepted |

All three Gold packages preserve ordered `items[]`, source-bound occurrences, Registry projection,
coverage audit, product review evidence and manifest/hash bindings. `field_results` remains a
derived field index and cannot define content order.

## Proof Summary

- Student 001: 244 content instances, 414 source objects, 12 figures/source images, 6 body tables,
  45 references, 0 unresolved/unregistered.
- Student 002: accepted Gold r5 remains the required live quality/performance gate for the module.
- Student 003: 111 content instances, 249 source objects, 6 multi-asset semantic figures, 1 body
  table, 29 references, accepted revision/annotation coverage, 0 unresolved/unregistered.

## Verification

- Deterministic materializer `--check`.
- Registry/coverage/order invariants.
- Top-level restricted Gold hash bindings.
- Product review documents in the restricted Gold packages.

## Boundary

Extraction Gold describes student-source truth only. It excludes school template facts, target
slots, target styles, Placement/Filling decisions, pagination and final Word quality.
