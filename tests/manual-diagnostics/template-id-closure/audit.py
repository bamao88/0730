"""Read-only ID audit of the explicitly selected historical real task roots.

Run from the repository root. Does not accept, migrate, or republish artifacts.
"""

import json
from collections import Counter
from pathlib import Path

import yaml

from docfit.content.placement import load_fill_contract
from docfit.fields import FieldRegistrySnapshot
from docfit.template.artifact import validate_published_template_artifact
from docfit.template.materialization.vocabulary import inventory_review_vocabulary_provenance_errors
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.tools.runtime import ToolFailure, sha256_file

Path("temp/id-closure-audit-20260922").mkdir(parents=True, exist_ok=True)
BASE = Path("temp/phase8-v05-20260912")
NAMES = """hunau-01-cover-v5
hunau-02-integrity-v1
hunau-03-toc-v5-fixed-publication
hunau-04-paper-body-v1
hunau-05-design-task-v5-m3-checkbox
hunau-06-proposal-v1
hunau-07-proposal-record-v7-m3
hunau-08-defense-record-v1
hunau-09-topic-change-approval-v4-m3
hunau-10-grade-form-v7-m3-semantic-lock
njau-01-cover-v6
njau-02-declarations-v1
njau-03-toc-v6
njau-04-abstract-cn-v3
njau-05-abstract-en-v3
njau-06-body-v4
njau-07-references-v5
njau-08-appendix-v5
njau-09-academic-achievements-v1
njau-10-acknowledgement-v2
pku-01-cover-v4
pku-02-copyright-v1
pku-03-abstract-cn-v2
pku-04-abstract-en-v1
pku-05-toc-v5
pku-06-list-of-figures-v1
pku-07-list-of-tables-v1
pku-08-body-v12
pku-09-references-v1
pku-10-appendix-achievements-v1
pku-11-acknowledgement-v3
pku-12-declarations-v1""".splitlines()
rows = []
for name in NAMES:
    root = BASE / name
    h = root / "work/.docfit/harness"
    inv = json.loads((h / "object-inventory.json").read_text())
    review = json.loads((h / "semantic-judgments.json").read_text())
    registry = FieldRegistrySnapshot.load(root / "input/field-registry.yaml")
    source = root / "input/school-template.docx"
    contract = yaml.safe_load((root / "output/fill-contract.yaml").read_text())
    contract["contract_sha256"] = sha256_file(root / "output/fill-contract.yaml")
    try:
        load_fill_contract(root / "output/fill-contract.yaml")
        consumer = "ok"
    except ToolFailure as e:
        consumer = e.code
    vocabulary = registry.pre_input_vocabulary()
    current_hash = sha256_file(source)
    row = {
        "root": str(root),
        "consumer_load": consumer,
        "source_sha256": current_hash,
        "ledger_source_sha256": review["document_sha256"],
        "source_current": current_hash == review["document_sha256"],
        "registry_sha256": sha256_file(registry.path),
        "review_sha256": sha256_file(h / "semantic-judgments.json"),
        "inventory_sha256": sha256_file(h / "object-inventory.json"),
        "vocabulary_errors": inventory_review_vocabulary_provenance_errors(
            inventory=inv, review=review, registry=registry
        ),
        "accepted_review_valid": review_uses_current_semantic_shape(
            inventory=inv,
            review=review,
            expected_vocabulary=vocabulary,
            expected_document_sha256=review["document_sha256"],
        ),
        "slot_count": len(contract["slots"]),
        "template_sha256": sha256_file(root / "output/final-template.docx"),
        "contract_template_sha256": contract["template_sha256"],
        "contract_sha256": contract["contract_sha256"],
    }
    spans = {s["span_ref"]: s for s in review["resolved_spans"]}
    row["published_slots_equal_accepted_spans"] = all(
        s["provenance"]["accepted_span"] == spans.get(s["span_ref"]) for s in contract["slots"]
    )
    try:
        validate_published_template_artifact(
            template_docx=root / "output/final-template.docx", fill_contract=contract
        )
        row["artifact_validation"] = "ok"
    except ToolFailure as e:
        row["artifact_validation"] = e.code
    ep = root / "work/.docfit/template-agent-execution.json"
    if ep.exists():
        ex = json.loads(ep.read_text())
        row["historical_execution"] = {
            k: ex.get(k)
            for k in [
                "status",
                "session_id",
                "num_turns",
                "sdk_query_count",
                "semantic_feedback_attempts",
                "harness_feedback_attempts",
            ]
        }
    rows.append(row)
    print(
        name,
        row["source_current"],
        row["accepted_review_valid"],
        row["artifact_validation"],
        row["published_slots_equal_accepted_spans"],
        flush=True,
    )
summary = {
    "rows": len(rows),
    "source_current": sum(r["source_current"] for r in rows),
    "review_valid": sum(r["accepted_review_valid"] for r in rows),
    "vocabulary_valid": sum(not r["vocabulary_errors"] for r in rows),
    "slots_match": sum(r["published_slots_equal_accepted_spans"] for r in rows),
    "artifacts": dict(Counter(r["artifact_validation"] for r in rows)),
}
Path("temp/id-closure-audit-20260922/artifact-audit.json").write_text(
    json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n"
)
print(summary)
