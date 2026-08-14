# DocFit Domain Context

## Template workspace

- **Template object**: one OfficeCLI-addressable Word object plus bounded parent/child/adjacent context. It is the Agent's unit of judgment and action.
- **Object ref**: snapshot-bound structural identity (`document_sha256`, object ID, fingerprint) shared by structure, visual location, and mutation. A prior ref remains valid only for its immutable prior version and never addresses objects in a newer version.
- **Document ref**: immutable task-local Word version addressed by its SHA-256. Internal versions support feedback and recovery; they are not user deliverables.
- **Field Registry**: cross-stage field semantics queried lazily for one current object. It is never a template-wide slot checklist.
- **Final template**: the fillable Word published at `output/final-template.docx` after the Agent reviews the exact final version.
- **Fill contract**: the human-reviewable, machine-readable filling guide published at `output/fill-contract.yaml`; it is bound to the exact final-template hash and explains fields, locations, conditions, styles, and manual actions.
- **School extraction delivery**: one atomic two-file product unit: `final-template.docx` plus `fill-contract.yaml`. Reports, receipts, renders, and manifests are internal evidence rather than additional primary deliverables.

## Architecture boundary

The Claude Agent SDK owns the Agent loop, context, Tool calls, permissions, and lifecycle. DocFit supplies focused Word/field/visual Tools and mechanical feedback. It does not require Agent-authored mutation plans, compilers, attempt paths, or a semantic checker.

## General fallback style product memory

- `docfit.general_thesis.zh@1.0.0` was accepted by the product owner on 2026-08-11 as the current general thesis fallback baseline.
- A verified complete school role always wins unchanged. A missing or incomplete school role uses the complete versioned fallback role. School and fallback properties are never mixed inside one role.
- Every future discussion or adjustment of the general fallback style must provide updated human-facing product review tables: the global fallback style table, the complete field-handling mapping table, and the inheritance-expanded complete effective style table.
- YAML and engineering artifacts cannot replace those product review tables. Any change affecting values, role boundaries, parameters, source classification, field coverage, or completeness status requires updated tables, renewed closure validation, and product confirmation.
- Acceptance of the v1 product definition allows engineering implementation to begin, but does not by itself prove runtime implementation, visual correctness, or national-standard conformance.
