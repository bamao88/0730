# Template Source Location Phase 7 Audit

Date: 2026-09-11

Branch: `codex/template-extraction-skill-harness-redesign`

Status: **ACCEPTED**

## Product conclusion

The executable source-location chain now accepts only canonical source entries and Harness-resolved
SourceSpans. Reading block/range IDs remain an Agent-readable view, but are rejected as judgment,
span, slot, Tool-write, publication, and fill-consumer identities.

Phase 7 is accepted at the `logic/contract` layer. The full template Eval now has one committed,
deterministically generated, hash-bound baseline. Its fill contracts, DOCX content-control tags,
schema, loader, candidate packages, Registry reference, and tests all use canonical SourceSpan slot
references. Retired reading block/range slot references are accepted only as negative-test inputs.

## Deletion checklist

| Reachable boundary | Current invariant | Evidence |
| --- | --- | --- |
| Agent judgment schema | `source_entry_id + ordered parts` only; legacy `scope` fails closed | `e70af64`, `e5bf7d4` |
| Harness coverage projection | Resolves coverage only from canonical `source_entry_id`; no legacy scope double-read | `27a4f07`, `6a7dcbd` |
| Span resolver | Generates canonical SourceSpan refs from immutable source snapshot, entry, and exact extent | `a7edf3d` |
| Plan validator | Uses typed intents, spans, and canonical scopes; no reading-view payload target selection | `375bb84` |
| Tool write boundary | Parses only canonical SourceSpan-based `slot_ref`; reading-view slot refs fail closed | `e3c58c4` |
| Materializer | Executes exact accepted Word fragments and does not search for a new target | `938958d` |
| Publication | Parses only canonical SourceSpan-based slot refs; old reading markers are rejection markers | `e88ed76` |
| Fill consumer | Requires every operation to carry a canonical SourceSpan slot ref; no tag fallback | `26e1458` |
| Long-term docs | Contract, module guide, and coding guardrails define source entry as the only judgment scope | `1ae652a` |
| Eval and Gold boundary | Eval v2 schema/loader, synthetic fixtures, candidate packages, and marker checks share canonical SourceSpan slot identity | `4fb04b9` |

Internal `object_ref`, locator, fingerprint, and target references remain only where needed to map an
accepted SourceSpan to Word and to prove snapshot freshness. Reading blocks/ranges remain only in the
unit reading packet, feedback context, and their internal projection/mapping code. Those uses do not
create or select a second semantic target.

## Verification evidence

- `logic/contract`: `706 passed` for `tests/contract`, template materialization replay, Agent school
  tests, and materialization readiness tests.
- `logic/contract`: focused Tool/publication tests `67 passed`; Harness projection tests `96 passed`;
  plan/compiler/context/readiness tests `63 passed`; fill/replay tests `60 passed, 1 skipped`.
- Static checks: Ruff passed for the touched source/test surfaces; mypy passed for `111 source files`;
  `git diff --check` passed.
- `logic/contract`: the committed Eval snapshot at `4fb04b9` passed `177 passed`; Eval Ruff passed;
  Eval mypy passed for `29 source files`. The snapshot was materialized in a detached worktree from
  the Git index so that verification consumed the exact committed DOCX blobs rather than local Word
  metadata variants.
- `real replay`: Phase 6 actual DOCX/publication/consumer replay remains at
  `temp/phase6-materialization-real-replay-20260911c/phase6-replay-evidence.json`.
- No new `E2E agent loop` or `product acceptance` was completed in this Phase 7 audit.

## Hash-bound Eval baseline resolution

Full Eval command:

```text
PYTHONPATH=evals/template-extraction UV_CACHE_DIR=/private/tmp/docfit-uv-cache \
  uv run pytest -q evals/template-extraction/tests
```

Authoritative result: `177 passed` from the detached staged/committed snapshot.

The synthetic builder was run into a temporary directory. Text contracts and manifests were
reviewed and synchronized; deterministic DOCX blobs were written directly to the Git index, without
overwriting local Word files. This prevents application-added `docProps/custom.xml` metadata from
being mistaken for a product-contract change. Formal case Registry references were bound to the
committed Registry hash, and old reading-view slot refs were rejected rather than grandfathered.

The main working directory still contains user-owned DOCX metadata variants, so running the hash-
bound Eval directly there can correctly report hash mismatches. That is a workspace-state warning,
not evidence against the committed baseline, and those local binary changes remain preserved and
unstaged. Phase 8 must use explicit immutable task roots and report its four evidence layers
separately; Phase 7 acceptance does not imply live Agent or product acceptance.
