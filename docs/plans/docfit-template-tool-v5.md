# DocFit Template Tool v5 Refactor

## Plan Ledger

- Status: `ACTIVE`
- Session scope: clean-break replacement of the school-template preparation Tool surface and its Word mutation semantics
- Source decision: user-approved 2026-08-09; no compatibility layer for the v4 template workspace contract
- Current slice: public Tool contract, operation planning, OOXML safety, focused knowledge cards, and real NJAU regression
- Next gate: focused contract tests, full relevant suite, original-template CLI run, then Microsoft Word update/save/reopen verification
- Blocker: none at implementation start

## Objective

Make the school-template Agent responsible for semantic decisions while the Tool reliably executes narrow, outcome-oriented Word operations and reports materialized facts. Eliminate the v4 failure modes proven by the NJAU r29 run: inherited TOC hyperlink color, parent/child batch-delete rejection, incomplete boundary preservation, wide navigation schema misuse, and Tool-enforced body semantics.

## Approved Contract

The public preparation surface becomes:

```text
template_open()
template_next(region_ref, outcome, reason?)
template_search(query)
template_focus(object_ref, scope?)
template_registry(queries)
template_edit(batch)
template_publish(document_ref)
```

- Navigation reads the latest checkpoint implicitly. Only publish confirms an exact `document_ref`.
- `template_edit` exposes action-partitioned lanes with narrow schemas; it does not expose a union of irrelevant properties.
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

## Parked

- Generalizing effective-format normalization beyond the approved color/underline outcomes.
- Turning boundary facts into a reusable cross-product Word editing framework.
- M3 Gold acceptance and multi-school quality scoring.
