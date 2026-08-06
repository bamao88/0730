# Template Extraction Eval

Independent, read-only static evaluator for comparing a generated DOCX template and fill
contract with a versioned Gold template and Gold fill contract.

This project is intentionally isolated from the `docfit` product package. It has its own Python
environment, dependencies, tests, entry point, fixtures, and run outputs. Runtime communication is
limited to versioned files, schemas, and SHA-256 bindings.

Implementation is in progress. The current G1 slice freezes schemas, scoring rules, and synthetic
fixtures. The three school directories now use the final case layout, but their manifests and fill
contracts remain `candidate` / `candidate_pending_human_acceptance`; a path under `gold/` is not an
acceptance signal and the cases intentionally expect `INPUT_ERROR` until Human readiness passes.

The case data layout is:

```text
cases/<case-id>/
├── case.yaml
└── gold/
    ├── template.docx
    └── fill-contract.yaml
```

`case.yaml` binds the template, contract, Registry snapshot, Eval config, marker protocol, review
state, and SHA-256 values. `fill-contract.yaml` keeps each physical `w:tag` locator separate from
its canonical Registry `field_id`; the DOCX must use `w:alias == field_id`, while `w:id` remains a
Word-internal identity.

The current candidate packages can be reproduced without changing any accepted case:

```bash
uv run --project evals/template-extraction \
  python evals/template-extraction/materialize_candidate_cases.py
```

The materializer refuses to overwrite a case or fill contract whose status is `accepted`. It does
not perform Human acceptance, repair OfficeCLI schema findings, or claim M3 completion.
