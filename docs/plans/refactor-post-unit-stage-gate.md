---
refactor_scope: post-unit-stage-gate
status: DONE
accepted_severities:
  - P0
  - P1
  - P2
last_verified: 2026-08-20
---

# Refactor Scope: Post-Unit Stage Gate

## Status

DONE

## Target

Template extraction post-unit flow after accepted unit boundaries.

## Accepted Severities

P0/P1/P2 inside the post-unit Tool/Harness/Skill contract.

## Accepted Cleanup Checklist

- [x] Remove Agent-facing `docfit_check(action_plan)` as an executable check path.
- [x] Remove `action_requirement` as a post-unit `docfit_apply` precondition or audit surface.
- [x] Gate post-unit deterministic writes on accepted Harness semantic judgments, not on Agent-built per-object payloads.
- [x] Keep Agent responsibility limited to semantic judgments over the object universe.
- [x] Update contract tests and docs so stale per-object gates cannot look green.

## Parked Cross-Seam / Future Ideas

- Deterministic compiler from accepted `semantic_judgments` to a full materialization batch is a follow-up execution-stage feature if not already covered by existing apply paths.
- Registry/executability checks can be deepened inside Harness review without creating new Agent-facing schemas.

## Evidence Ladder

- L2 contract tests for Tool surface, check/apply service behavior, runtime prompt, and Skill contract.
- L0 ruff on changed files.

## Stop Condition

Stop when the accepted checklist is complete, direct `action_plan` checks are retired, post-unit writes require accepted Harness semantic judgments, no public schema exposes `action_requirement`, and the L2/L0 evidence ladder is green.

## Execution Log

- 2026-08-20: Gate created for full migration from per-object action gates to phase-level Harness review.
- 2026-08-20: Removed the old action-plan check implementation, removed the action-requirement apply gate, and made post-unit writes require accepted `work/.docfit/harness/semantic-judgments.json`.
- 2026-08-20: Verified target contracts with `uv run pytest -q tests/contract/test_tool_surface.py tests/contract/test_docfit_check_tool.py tests/contract/test_docfit_apply_tool.py tests/contract/test_prepare_template_runtime.py tests/contract/test_skill_contract.py` (79 passed).
- 2026-08-20: Verified static gate with `uv run ruff check src/docfit/tools/service.py src/docfit/tools/__init__.py src/docfit/tools/surface.py src/docfit/app/prepare_template.py tests/contract/test_docfit_apply_tool.py tests/contract/test_docfit_check_tool.py tests/contract/test_tool_surface.py tests/contract/test_prepare_template_runtime.py` (passed).
- 2026-08-20: Full `uv run pytest -q tests/contract` currently has one unrelated failure in `tests/contract/test_eval_contract.py::test_manual_delivery_gate_preserves_unknown`; the checklist text lacks the exact `never \`PASS\`` phrase expected by that eval contract.
- 2026-08-20: Real `01-cover` post-unit resume smoke reached post-unit evidence collection but did not build final output. It exposed that the runtime did not route Agent `needs_input` phase-review requests into Harness feedback. Added a feedback-loop guard so `semantic_judgments` plus Harness review missing evidence triggers Harness semantic coverage review and returns affected scopes.
