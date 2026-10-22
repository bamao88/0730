# Final Generation Module Contract

Status: implemented development contract
Integrated from: `codex/final-generation`

## Goal

Turn final document generation into a true file-contract module. This module consumes
previously produced student content and template artifacts, validates their identity
bindings, and publishes `final.docx` only when the candidate is complete.

`docfit fill-student-content` remains a transitional end-to-end development entry.
`docfit generate-final` is the durable file-contract entry for this module.

## Allowed Inputs

- `student.docx`
- `student-content.json`
- `final-template.docx`
- `fill-contract.yaml`
- `content-fields.yaml`
- Optional `quality-patches.yaml`

## Required Outputs

- `candidate.docx`
- `final.docx`, only when status is `COMPLETE`
- `content-partition.json`
- `validation.json`
- `content-audit.json`
- `style-audit.json`
- `run-report.json`
- Render evidence for the current candidate/final snapshot

## Forbidden Reads

- School requirements source files
- Raw school template files other than the already finalized `final-template.docx`
- Any template extraction workspace internals
- Any Agent-only prompt transcript that contains source text

This module must not call the user content extraction Agent and must not redo template
extraction.

## Hash And Schema Gates

- Missing `student-content.json` returns `NEEDS_INPUT`.
- `student-content.json.schema_version` must be `docfit-student-content-model/v2`.
- `student-content.json.source_sha256` must match `student.docx`.
- `student-content.json.registry` must match `content-fields.yaml` identity.
- `fill-contract.yaml.schema_version` must be `docfit-template-fill-contract/v2`.
- `fill-contract.yaml.template_sha256` must match `final-template.docx`.
- `fill-contract.yaml.field_registry_ref` must match `content-fields.yaml` identity.
- The template must carry current digest-bound materialization provenance; each slot uses
  its canonical source-span `slot_ref`. Historical `slot_id` debug packages are not current
  published templates.
- Required slot gaps return `PARTIAL` and must not publish `final.docx`.
- Complete content, style, OfficeCLI validation, and render checks return `COMPLETE` and
  publish `final.docx`.

## Content Partition

Before placement, final generation must deterministically compile a task-local partition from
`student-content.json`, `fill-contract.yaml`, and the bound Registry:

- `body_flow`: every classified `body.*` or `conclusion.*` item in immutable
  `source_order`; this stream is transported as one ordered body aggregate and then styled by
  template role contracts.
- `named_fields`: classified non-body, non-generated fields such as cover data, abstract,
  keywords, references, acknowledgement, and appendix; these fill named target slots.
- `generated_fields` and generated regions: system-produced structures such as TOC or figure/table
  lists; these are not copied from student source text.
- `retained_regions`: protected school template structures that final generation must preserve or
  explicitly mark, not silently delete.

The partition is deterministic application code, not Agent judgment. It is the handoff boundary
that lets final generation avoid reclassifying student content while still applying different
strategies to body flow and named fields.

## Independent Acceptance Command

Run the module directly when debugging final generation from one prepared input package:

```bash
uv run docfit generate-final \
  --source student.docx \
  --student-content out/student-content/student-content.json \
  --template out/template/final-template.docx \
  --fill-contract out/template/fill-contract.yaml \
  --field-registry content-fields.yaml \
  --output out/final
```

Run selectable eval cases when checking prepared debug/regression packages:

```bash
uv run docfit eval --suite final-generation --list-cases
uv run docfit eval --suite final-generation \
  --case student-001-njau-complete-debug \
  --checks input,style \
  --json
uv run docfit eval --suite final-generation \
  --case student-001-njau-complete-debug \
  --checks input,style,generate \
  --output temp/final-generation-e2e-verify-20260816/eval-complete-debug-001 \
  --json
uv run docfit eval --suite final-generation \
  --case student-001-njau-complete-debug \
  --checks input,style,generate,quality \
  --output temp/final-generation-quality-compare-20260818/eval-complete-debug-quality-001 \
  --json
```

Use `input,style` for the fast input gate. Add `generate` only when the run should publish a
candidate, render evidence, and compare the current expected status. For release-level cases with
a configured quality gold, run `input,style,generate,quality`; `generate` passing is not a release
decision. Eval reports separate `check_status`, `generate_status`, `quality_status`, and
`release_status`; only `release_status=PASS` with `releasable=true` may be described as publishable.
Use `student-001-njau-complete-debug` for the COMPLETE release path. Use
`student-001-njau-known-gap` only when checking intentional `PARTIAL` downgrade behavior.

Verification:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

## Implementation Notes

`docfit generate-final` is a deterministic file-contract consumer. It reuses the
placement, fill, projection, style materialization, validation, and render path without
calling `StudentExtractionRunner` or re-running Agent extraction. Agent work belongs
upstream in student content extraction and template extraction; this module consumes their
accepted artifacts and fails closed when identity, required content, style, or validation
gates are not satisfied.
