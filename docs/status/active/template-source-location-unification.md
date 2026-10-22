---
task: template-source-location-unification
status: active
canonical_plan: docs/plans/template-field-id-vocabulary-boundary-refactor.md
current_phase: 8
updated: 2026-09-12
---

# Template source-location unification resume capsule

- Current state: Phase 0–7 are **ACCEPTED**. Phase 8 is active. Runtime, Eval, publication,
  resume and fill consumers share canonical `source_entry_id + extent + source snapshot` identity;
  reading block/range IDs remain Agent-readable views only.
- Last proven contract evidence: full repository regression is `1157 passed / 5 skipped / 1 deprecation
  warning`; Ruff and mypy pass after the current compiler/materializer fixes. Phase 7 deletion evidence
  remains recorded in `docs/plans/template-source-location-phase7-audit.md`.
- Verification level: Phase 7 remains `logic/contract`. Under Registry 0.5.0 and current vocabulary digest
  `861eccc3…`, Phase 8 has `27/32` successful E2E/publication rows: HUNAU `5/10` (`01/02/04/06/08`),
  NJAU `10/10`, PKU `12/12`. This is not the full matrix or final product acceptance.
- Current Phase 8 result: HUNAU `08-defense-record-v1` under
  `temp/phase8-v05-20260912/` accepted 46/46 source entries and 64 exact spans after 6 Agent turns.
  Its school-authored instruction requires records and signatures to be filled by hand, so accepted
  no-slot provenance and 0 generated slots are the intended result rather than a missing-field fallback.
  Build checks and ZIP reopen are `ok`; LibreOffice independently rendered 2 A4 pages with no obvious
  clipping, overlap or instruction leakage. The fill contract remains `candidate_pending_human_acceptance`.
- Current runtime gaps: HUNAU `04-paper-body-v2` changed a previously correct split during candidate-ledger
  re-aggregation and is not counted; `05-design-task-v1` has a complete five-batch ledger but its only
  whitespace/colon revision repeatedly waits without structured output; `07-proposal-record-v1` likewise
  has one exact-prefix feedback item, but a clean single-process resume produced no new candidate in five
  minutes and stopped in Claude Agent SDK `receive_response`. `09-topic-change-approval-v1` now has all
  3/3 candidates for 28 entries, but U2 omitted one leading U+0020 in each of two signature/date lines;
  Harness returned 8 exact-text mismatches and 2 gaps, then its scoped revision waited without output.
  `10-grade-form-v1` has 5/5 candidates for 79 entries; one scoped revision reduced whitespace failures
  from 8 entries / 14 blockers to 5 / 10, but NBSP normalization and two expanded single-space entries
  remain and the next revision did not return. HUNAU `03/05/07/09/10` remain non-passes.
- Current recovery result: HUNAU `04-paper-body-v1` keeps its original accepted digest `65ec3809…` after
  current Harness re-validation, then publishes 42 unique slots through a 0-new-turn deterministic resume.
  Both inline outline4/body pairs retain exact non-overlapping spans. This combines prior live Agent evidence
  with current real replay/publication; it is not a fresh one-command Agent loop or human acceptance.
- Fresh HUNAU `03-toc-v3` produced no Tool call or structured result during the 180-second unit-boundary
  no-progress window, so it has no checkpoint or candidate. Its older current-digest v1 remains a product
  false-green because visible spacing instructions survive, and v2 did not restore 20/22 generated TOC rows.
- Next command/artifact: do not repeat the same backend attempts without a decision-changing comparison;
  remaining gates are HUNAU `03/05/07/09/10`, fixed-render coverage and human acceptance.
- Stop condition: do not mark the goal complete until the full hash-bound matrix has current real
  replay, live Agent, final DOCX/fill-contract provenance, and required product/visual acceptance;
  environment failures and `needs_input` remain explicit non-passes.
- No-touch scope: unrelated dirty source, documents, DOCX metadata variants and prior temp artifacts.
