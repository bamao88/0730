"""Summarize fresh-run evidence without counting running/failed tasks as success."""

import json
from pathlib import Path

base = Path("temp/full-flow-id-20260922")
rows = []
for name in (
    "cover-live",
    "body-live",
    "pku-cover-live",
    "integrity-live",
    "njau-cover-live",
    "pku-abstract-live",
    "pku-abstract-retry",
):
    root = base / name
    row = {"task": name, "status": "incomplete"}
    initial = root / "work/.docfit/initial-source-inventory.json"
    if initial.exists():
        canonical = json.loads(initial.read_text())["canonical_source_inventory"]
        row.update(
            source_sha256=canonical["source_snapshot_sha256"],
            source_inventory_digest=canonical["inventory_digest"],
            source_entry_count=len(canonical["source_entries"]),
        )
    proof = root / "work/.docfit/unit-boundary-checkpoint.json"
    if proof.exists():
        data = json.loads(proof.read_text())
        row.update(
            unit_count=data["unit_count"],
            unit_feedback_attempts=data.get("harness_feedback_attempts"),
            unit_sdk_query_count=data.get("sdk_query_count"),
        )
    trace = root / "work/.docfit/template-agent-execution.json"
    if trace.exists():
        data = json.loads(trace.read_text())
        row.update(
            status=data.get("status"),
            failure=data.get("failure"),
            sdk_query_count=data.get("sdk_query_count"),
            feedback_attempts=data.get("harness_feedback_attempts"),
        )
    row["published_file_exists"] = (root / "output/final-template.docx").is_file()
    rows.append(row)
(base / "live-run-matrix.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
for row in rows:
    print(row["task"], row["status"], "published:", row["published_file_exists"])
