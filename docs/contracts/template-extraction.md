# Template Extraction Module Contract

Status: draft scaffold  
Branch: `codex/template-extraction`  
Base: `origin/main`

## Goal

Stabilize school template extraction as an independent module that produces a finalized
template document and Fill Contract that `docfit generate-final` can consume.

This module handles school template interpretation. It does not read a student thesis
and does not generate a final thesis.

## Allowed Inputs

- `school-template.docx`
- `school-requirements.md` or `school-requirements.txt`
- `content-fields.yaml`

## Required Outputs

- `final-template.docx`
- `fill-contract.yaml`
- `template-report.json`
- Style Contract evidence
- Render evidence for the finalized template snapshot

## Forbidden Reads

- `student.docx`
- `student-content.json`
- Final generation output directories
- User content extraction workspaces

## Hash And Schema Gates

- `final-template.docx` must pass OfficeCLI validation.
- `fill-contract.yaml.schema_version` must be `docfit-template-fill-contract/v2`.
- `fill-contract.yaml.template_sha256` must match `final-template.docx`.
- `fill-contract.yaml.field_registry_ref` must match `content-fields.yaml` identity.
- `style_contract_set_digest` must match the Style Contract Set in the contract.
- Required slots must include complete `slot_id`, `field_id`, `locator`, `required`, and
  `style_contract_ref` fields.
- Every required locator must resolve against `final-template.docx`.

## Independent Acceptance Command

Current command to preserve and harden:

```bash
uv run docfit prepare-template \
  --school-template school-template.docx \
  --school-requirements school-requirements.md \
  --field-registry content-fields.yaml \
  --output out/template
```

Scaffold verification for this PR:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

## Development Entry Prompt

Harden `docfit prepare-template` into a standalone template extraction module. It must
publish `final-template.docx`, `fill-contract.yaml`, `template-report.json`, style
evidence, and render evidence, with tests proving it cannot read `student.docx` or
`student-content.json`.
