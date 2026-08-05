---
name: docfit-school-extract
description: Prepare a school thesis Word template as a frozen, safely fillable template artifact. Use when the user supplies a school template, formatting requirements, or official examples and wants a clean reusable template plus a hash-bound slot manifest.
---

# School Template Extraction

Turn the current task's school materials into exactly two deliverables:

1. a clean template DOCX that preserves required structure, fixed content, styles, and Word behavior;
2. a frozen artifact manifest bound to that exact template hash, with automatic slots, manual regions,
   gaps, sources, and review findings.

Do not fill student content. Do not promote school-specific conclusions into product Knowledge.

## Responsibility split

You decide meaning: which material is authoritative, what visible content is an instruction or example,
which responsibility must survive deletion, what a slot means, and whether a visual change is reasonable.

The bundled scripts validate and compile your completed semantic decisions into canonical Tool inputs.
The template Tools establish facts, execute explicit operations, compare actual changes, compile a
candidate, and independently freeze it. Neither a script nor a Tool result substitutes for semantic judgment.

## Recommended method

Adapt the following sequence to the evidence. It is a working method, not a fixed state machine.

1. Inventory every template, written requirement, and official example. Record provenance, conflicts,
   missing inputs, and files that must remain read-only.
2. Call `template_observe` to establish an immutable snapshot. Observe structure, visible objects,
   effective formatting, slot candidates, PDF pages, and unsupported content.
3. Classify template content as fixed, fill, generate, repeat, conditional, manual, remove, or unresolved.
4. Before deleting an instruction or example, migrate any surviving formatting, cardinality, generation,
   or placement responsibility into a slot or region decision.
5. Reconcile written requirements with the template's effective formatting. Preserve material conflicts;
   do not resolve them from style names, prior schools, or convention alone.
6. For each intended change, choose an exact target, expected fingerprint, removal mode, and any slot
   semantics. Ask the user when the ambiguity can materially change the reusable template.
7. Write `mutation-decisions.yaml`, then run `scripts/compile_mutation_plan.py`. Give the resulting
   `mutation-plan.json` to `template_mutate`. Never use page numbers or text alone as edit identity. If
   compilation or mutation rejects a stale or ambiguous target, observe again and reconsider the decision.
8. Call `template_compare`. Inspect its expected and unexpected changes and the native images it returns.
   Decide whether the result is reasonable, needs another edit, or requires user input.
9. Record your image judgments in `review-decisions.yaml` and run `scripts/compile_review_record.py`.
   After the final snapshot and all pages are reviewed, run `scripts/compile_artifact_spec.py` over the
   confirmed semantic inventory and review record. Give `artifact-spec.json` to `template_build` and treat
   its output only as a candidate.
10. Submit the candidate to `template_freeze`. Deliver it only when that independent Tool returns
    `status: frozen`.

## Core judgment rules

- Instruction text may carry requirements. Migrate the requirement before removing the text.
- A logical unit is not a physical page. Page numbers are visual evidence, not durable edit locators.
- A style name is not effective formatting. Include direct formatting, inheritance, section settings,
  and other applicable Word behavior.
- A generated object is not its cached display text. Preserve the generation responsibility when needed.
- The number of examples is not the cardinality of a repeating region.
- Fixed content stays fixed unless current-task evidence explicitly authorizes a change.
- Unknown or unsupported content stays preserved and unresolved; absence of evidence is not permission to
  delete it.
- Automatic slots must be uniquely locatable in the final template snapshot. Otherwise mark the region
  manual or unresolved.
- A successful mutation or build is not a frozen artifact. Only `template_freeze` can publish one.

## Compile decisions before Tool execution

Resolve `scripts/` relative to this `SKILL.md`; do not recreate the compilers ad hoc.

| Script | Agent-authored input | Canonical output | Consumer |
|---|---|---|---|
| `compile_mutation_plan.py` | `mutation-decisions.yaml` | `mutation-plan.json` | `template_mutate` |
| `compile_review_record.py` | compare result + `review-decisions.yaml` | `review-record.json` | artifact compilation and freeze evidence |
| `compile_artifact_spec.py` | final semantic inventory + review record | `artifact-spec.json` | `template_build` |

Write the semantic decision and its evidence first; the script only checks and serializes it. Treat compiler
errors as missing or inconsistent decisions, not as permission to weaken the schema. Scripts must produce
canonical output atomically and must not read or modify the DOCX, call a Tool, infer document meaning, or
claim that a review/freeze passed. Tools revalidate every compiled request.

Read [references/decision-compilation.md](references/decision-compilation.md) before preparing the three
decision files or interpreting compiler failures.

## Choose the removal mode deliberately

| Intent | Mode |
|---|---|
| Empty a placeholder while retaining its paragraph/run container and formatting | `clear_text_preserve_container` |
| Remove only a known inline phrase inside mixed content | `remove_inline_fragment` |
| Remove an entire paragraph, row, or other addressed container | `remove_container` |
| Remove a confirmed continuous logical block between stable boundaries | `remove_bounded_block` |
| Empty cell content while preserving table grid and cell properties | `clear_cell_preserve_grid` |
| Remove a content-control wrapper while retaining its approved content | `unwrap_control_preserve_content` |

Do not select a broader mode for convenience. If the intended unit cannot be expressed by one safe target
or bounded range, preserve it or split the operation after further observation.

## Define slot responsibility

For every automatic slot, determine:

- a stable `slot_id` and unique locator in the final snapshot;
- whether content is `scalar`, `paragraph_stream`, or `composite`;
- minimum and maximum cardinality without inferring it from examples;
- the physical container or boundaries that must remain;
- effective style observations and any separate written requirement;
- whether the responsibility is fill, generate, repeat, or conditional.

Use a manual region when downstream work requires human or semantic placement that cannot be uniquely and
safely automated. Record a gap when current evidence cannot define the responsibility at all.

## Interpret comparison evidence

`template_compare` reports facts and selects relevant images; it does not decide visual correctness.

Confirm that every expected change matches an operation, every unexpected change is explained or resolved,
fixed content and containers remain intact, pagination changes make sense, and visual crops agree with the
full-page context. Expand review when page count changes, object-to-page mapping fails, or section behavior is
affected. The final review must cover every page of the exact snapshot submitted for build.

## Use references when needed

- Read [references/template-semantics.md](references/template-semantics.md) for ownership,
  logical-unit, instruction-migration, generated-object, and source-conflict decisions.
- Read [references/deletion-and-slot-decisions.md](references/deletion-and-slot-decisions.md) when choosing
  a removal mode, slot content kind, cardinality, manual region, or gap.
- Read [references/style-reconciliation.md](references/style-reconciliation.md) when resolving effective
  formatting or comparing a written requirement with template evidence.
- Read [references/visual-regression.md](references/visual-regression.md) when interpreting structural or
  visual changes and deciding the review scope.

## Completion

Return the frozen artifact location, template hash, a concise summary of automatic slots and manual/gap
regions, and any non-blocking findings the downstream consumer must know. If freeze is blocked, report the
specific findings and do not present the candidate as deliverable.
