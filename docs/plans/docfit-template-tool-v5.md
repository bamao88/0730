# DocFit Template Tool v5 Refactor

## Plan Ledger

- Status: `COMPLETE`
- Session scope: clean-break replacement of the school-template preparation Tool surface and its Word mutation semantics
- Source decision: user-approved 2026-08-09; no compatibility layer for the v4 template workspace contract
- Delivered slice: public Tool contract, application orchestration, operation planning, OOXML safety, focused knowledge cards, and real NJAU regression
- Final gate: passed focused/full relevant tests, original-template CLI extraction, approximate LibreOffice review, and Microsoft Word update/save/reopen verification
- Blocker: none

## Objective

Make the school-template Agent responsible for semantic decisions while the Tool reliably executes narrow, outcome-oriented Word operations and reports materialized facts. Eliminate the v4 failure modes proven by the NJAU r29 run: inherited TOC hyperlink color, parent/child batch-delete rejection, incomplete boundary preservation, wide navigation schema misuse, and Tool-enforced body semantics.

## Delivered Contract

Implementation evidence showed that even seven navigation/edit Tools left deterministic traversal and retry responsibility with the model. The final clean-break surface is narrower:

```text
template_get_current_work_item()
template_request_current_context(request)
template_submit_current_decision(decision)
template_report_ambiguity(report)
template_get_review_batch()
```

- The application owns checkpoint traversal, bounded retry, repair, final-page batching, exact-version receipts, publication, and terminal status. The semantic Agent sees only the current work item; the visual Agent sees only the current review batch.
- Agent schemas expose no cursor, `document_ref`, `region_ref`, publish command, or built/blocked terminal control.
- A semantic decision carries one atomic `operations` array. Each item directly declares an action and the small superset of action parameters; action-specific requirements are validated by the Tool without `oneOf`/`anyOf` schema branches.
- Effective formatting is outcome-oriented: `normalize_effective_format` specifies the desired visible result and succeeds only when the effective value verifies after mutation.
- Parent removal absorbs redundant descendant removal/clear/format operations. Removal that conflicts with descendant materialization remains an error.
- `ensure_page_start(mode="new_page")` is idempotent and selects a stable Word representation inside the Tool.
- The Tool validates identity, object capability, ordering, package integrity, relationships, boundaries, and observed effects. It does not decide which thesis semantic objects a school requires.
- Feedback includes absorbed operations, boundary handling, materialized members, style signatures, structural risks, and non-prescriptive knowledge signals.

## Accepted Work

### P0

- Replace the wide `template_view` Tool with four focused navigation Tools.
- Replace direct-color clearing with effective color/underline normalization and effective postcondition checks, including TOC/Hyperlink inheritance.
- Normalize batch operations before execution so redundant parent/descendant deletes commit once.
- Preserve or safely migrate Word structural boundaries during object removal.

### P1

- Remove the fixed H1/H2/H3/body Tool gate and style-inferred fatal chapter-boundary gate.
- Add idempotent page-start execution.
- Return objective materialization/style/risk facts instead of semantic completion conclusions.
- Refactor the candidate Skill into short, linked, progressively loaded knowledge cards.
- Update architecture, roadmap, human-facing status, and regression coverage.

## Evidence Ladder

- L0: schema/reference/stale-surface searches; Skill links resolve.
- L1: unit tests for operation normalization, effective formatting, page start, and OOXML boundary preservation.
- L2: template workspace and prepare-template contract tests; DOCX reopen/OfficeCLI validation; relevant full pytest/ruff/mypy gates.
- L3: original NJAU template CLI run; LibreOffice approximate risk scan; Microsoft Word open, target TOC update, save, close, reopen, and visual/structural inspection.

## Completion Evidence

- Relevant regression suite: `124 passed` across prepare-template Agent tests, workspace contracts, and Tool v5 regressions.
- NJAU r66: `status=built`; 25 semantic slots, 94 removals, no manual intervention; 13/13 LibreOffice-rendered pages explicitly reviewed clean.
- Post-build package audit: 39 package parts, 11 sections, 26 content controls, balanced bookmark ranges, live `TOC \\o "1-3" \\h \\z \\u`, no sample markers.
- Microsoft Word native gate: opened the exact r66 file URL, updated all fields, saved, closed, reopened, and reported 12 native pages. The refreshed TOC retained levels 1–3, page numbers, dot leaders, indentation `0/420/840`, effective black, and no underline.
- The Word-rewritten DOCX passed the same package/Registry/TOC audit; Word intentionally removed `updateFieldsOnOpen` after fulfilling it.

## Acceptance

1. TOC normalization verifies effective black/no blue and no underline, not merely absence of direct `w:color`.
2. Updating the TOC field preserves levels 1–3, indentation, dot leaders, page numbers, and black styling.
3. Parent paragraph plus descendant run deletion is normalized into one commit with an absorption receipt.
4. Removal preserves section/page boundaries, bookmark/range markers, drawings/anchors, table wrapper paragraphs, and field/reference structures.
5. An abstract can be ensured onto a new page without duplicate blank pages.
6. No Tool gate requires fixed H1/H2/H3 membership; the Agent decides the representative body structure from current evidence.
7. Skill references are real relative Markdown links and only the relevant short card needs loading.
8. The final artifact passes the Microsoft Word update/save/reopen gate; LibreOffice remains approximate evidence only.

## Non-goals

- No change to the five general `docx_*` Tools.
- No M3, accepted Gold, school profile, provider/renderer abstraction, or new knowledge runtime.
- No Word automation dependency in the product core.
- No compatibility shim for `template_view`, `clear_direct_format`, or the v4 edit schema.
- No semantic checker outside the Agent.

## Execution Risks

- Word field refresh can recreate `Hyperlink` character styling; proof must observe the post-refresh effective result.
- Boundary preservation must fail closed when a range cannot be kept structurally valid without widening the deletion.
- The inherited worktree contains unrelated user changes and generated runs; commits must stage owned paths only.

## Discovery Note

The unknown-unknown scout is intentionally skipped. The preceding investigation already inspected current code, tests, git history, official Claude Agent SDK/Skills documentation, and the r29 live transcript, and identified the exact contract and OOXML seams. New P2 cleanup found during implementation is parked unless it is required to prevent a P0/P1 regression.

## Official SDK Basis

The architecture keeps the Agent loop, in-process MCP Tool hosting, structured output, and Skill lifecycle on the Claude Agent SDK's native surfaces. DocFit adds only thesis-domain Tools and checkpointed Word execution: [custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools), [Agent Skills](https://code.claude.com/docs/en/agent-sdk/skills), and [Skills overview](https://code.claude.com/docs/en/skills).

## Parked

- Generalizing effective-format normalization beyond the approved color/underline outcomes.
- Turning boundary facts into a reusable cross-product Word editing framework.
- M3 Gold acceptance and multi-school quality scoring.
- Provider latency/quota work: the application now bounds idle sessions, retries, and malformed decisions, but cannot remove upstream Kimi quota failures or MiniMax response latency.
