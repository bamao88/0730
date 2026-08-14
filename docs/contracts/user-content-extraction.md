# User Content Extraction Module Contract

Status: draft scaffold  
Branch: `codex/user-content-extraction`  
Base: `origin/main`

## Goal

Stabilize user content extraction as an independent module that produces
`student-content.json` from a student thesis and Field Registry.

This module reads only the student source document and registry. It does not read school
templates, Fill Contracts, or final generation outputs.

## Allowed Inputs

- `student.docx`
- `content-fields.yaml`

## Required Outputs

- `student-content.json`
- `student-inventory.json`
- `agent-evidence.json`
- `run-report.json`

## Forbidden Reads

- `school-template.docx`
- `final-template.docx`
- `fill-contract.yaml`
- School requirements files
- Template extraction workspaces
- Final generation workspaces

## Hash And Schema Gates

- `student-content.json.schema_version` must be `docfit-student-content-model/v2`.
- `student-content.json.source_sha256` must match `student.docx`.
- `student-content.json.registry` must match `content-fields.yaml` identity.
- The report must include `registry_sha256` matching `content-fields.yaml`.
- Source objects must have explicit accounted-for status, including unsupported or
  layout-only cases.
- `agent-evidence.json` must be metadata-only and must not persist document body text.

## Independent Acceptance Command

Current command to preserve and harden:

```bash
uv run docfit extract-student-content \
  --input student.docx \
  --field-registry content-fields.yaml \
  --output out/student-content
```

Scaffold verification for this PR:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

## Development Entry Prompt

Harden `docfit extract-student-content` as a standalone user content extraction module.
It must produce `student-content.json`, `student-inventory.json`, `agent-evidence.json`,
and `run-report.json`, with tests proving it cannot read `school-template.docx` or
`fill-contract.yaml`.
