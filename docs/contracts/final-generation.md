# Final Generation Module Contract

Status: draft scaffold
Branch: `codex/final-generation`
Base: `origin/main`

## Goal

Turn final document generation into a true file-contract module. This module consumes
previously produced student content and template artifacts, validates their identity
bindings, and publishes `final.docx` only when the candidate is complete.

`docfit fill-student-content` remains a transitional end-to-end development entry. The
target durable entry is `docfit generate-final`.

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
- Required slot gaps return `PARTIAL` and must not publish `final.docx`.
- Complete content, style, OfficeCLI validation, and render checks return `COMPLETE` and
  publish `final.docx`.

## Independent Acceptance Command

Planned command:

```bash
uv run docfit generate-final \
  --source student.docx \
  --student-content out/student-content/student-content.json \
  --template out/template/final-template.docx \
  --fill-contract out/template/fill-contract.yaml \
  --field-registry content-fields.yaml \
  --output out/final
```

Scaffold verification for this PR:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

## Development Entry Prompt

Implement `docfit generate-final` as a deterministic file-contract consumer. It must
reuse the existing placement/fill/projection/style/validation path, accept
`student-content.json` as an input artifact, and include tests proving
`StudentExtractionRunner` and the Agent extraction path are never invoked.
