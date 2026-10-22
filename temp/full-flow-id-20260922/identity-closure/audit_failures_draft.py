"""Read-only identity audit of failed runs; never repairs source, judgment, or proof.

Run from repository root with uv run python <this file>.
Only writes failure-audit.json beside this script. Original evidence is read only.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.materialization.runtime import _fragment_text_is_current
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.source_spans import SourceSpanResolutionError, resolve_semantic_judgments
from docfit.template.unit_source import load_initial_inventory, require_initial_binding, validate_unit_proof
from docfit.tools.runtime import sha256_file
from docfit.tools.word_parts import read_word_stories, resolve_story_locator

BASE = Path("temp/full-flow-id-20260922")


def read(path):
    return json.loads(path.read_text())


def word_check(stories, spans):
    errors = []
    count = 0
    for span in spans:
        for fragment in span["word_fragments"]:
            count += 1
            target = resolve_story_locator(stories, fragment["locator"])
            if target is None or not _fragment_text_is_current(target[1], fragment):
                errors.append({"source_entry_id": span["source_entry_id"], "locator": fragment["locator"]})
    return {"fragments_checked": count, "errors": errors}


def fresh(name):
    root = BASE / name
    docfit = root / "work/.docfit"
    source = root / "input/school-template.docx"
    source_sha = sha256_file(source)
    initial = load_initial_inventory(root, source_sha)
    canonical = CanonicalSourceInventory.from_json(initial["canonical_source_inventory"])
    entry_ids = {entry.source_entry_id for entry in canonical.source_entries}
    trace = read(docfit / "template-agent-execution.json")
    row = {
        "task": name,
        "root": str(root),
        "level": "read-only actual task evidence and exact source Word XML; no new Agent run or write",
        "initial": {"entry_count": len(entry_ids), "source_sha256": source_sha, "binding": "ok"},
        "run_failure": trace.get("failure"),
        "published": (root / "output/final-template.docx").exists(),
        "other_docx_files": [str(p.relative_to(root)) for p in root.rglob("*.docx") if p != source],
        "identity_pipeline_defects": [],
        "evidence_paths": [str(docfit / "initial-source-inventory.json"), str(docfit / "template-agent-execution.json")],
    }
    with ZipFile(source) as archive:
        stories = read_word_stories(archive)
    proof_path = docfit / "unit-boundary-checkpoint.json"
    if not proof_path.exists():
        row.update(farthest_checkpoint="initial inventory / first Agent attempt", accepted_partition="not reached", accepted_semantic_review="not reached", materialization="not reached", responsibility="Agent/provider no-progress timeout; downstream identity unknown", id_blocker=False)
        return row
    proof = read(proof_path)
    validate_unit_proof(canonical, proof)
    unit_spans = [span for unit in proof["resolved_units"] for span in unit["source_spans"]]
    assert entry_ids == {span["source_entry_id"] for span in unit_spans}
    unit_word = word_check(stories, unit_spans)
    assert not unit_word["errors"]
    inventory = read(docfit / "harness/object-inventory.json")
    require_initial_binding(root, inventory)
    row["accepted_partition"] = {"unit_count": len(proof["resolved_units"]), "span_count": len(unit_spans), "ids_ranges_and_projection": "ok", "word_mapping": unit_word}
    row["evidence_paths"].extend([str(proof_path), str(docfit / "harness/object-inventory.json")])
    ledger_path = docfit / "harness/semantic-batch-candidates.json"
    ledger = read(ledger_path)
    judgments = [j for candidate in ledger["candidates"] for j in candidate["semantic_judgments"]]
    assert all(j["source_entry_id"] in entry_ids for j in judgments)
    errors = []
    try:
        resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    except SourceSpanResolutionError as exc:
        errors.extend(exc.blockers)
    row["candidate_ledger"] = {
        "batch_count": len(ledger["candidates"]),
        "judgment_count": len(judgments),
        "all_ids_from_initial_inventory": True,
        "exact_source_parts": "rejected" if errors else "ok",
        "invalid_entry_count": len({e["source_entry_id"] for e in errors if "source_entry_id" in e}),
        "error_counts": dict(Counter(e["code"] for e in errors)),
        "first_error": errors[0] if errors else None,
        "note": "Candidate ledger is proposed Agent content; it is not necessarily the final reviewed revision.",
    }
    row["evidence_paths"].append(str(ledger_path))
    review_path = docfit / "harness/semantic-judgments.json"
    if not review_path.exists():
        row.update(farthest_checkpoint="accepted unit partition; semantic revision incomplete", accepted_semantic_review="not reached", materialization="not reached", responsibility="Agent proposed parts omit/change exact original text; Harness rejects; provider revision returned no usable text", id_blocker=False)
        return row
    review = read(review_path)
    assert review_uses_current_semantic_shape(inventory=inventory, review=review, expected_vocabulary=inventory["field_id_vocabulary"], expected_document_sha256=source_sha)
    reviewed_spans = review["resolved_spans"]
    assert entry_ids == {span["source_entry_id"] for span in reviewed_spans}
    reviewed_word = word_check(stories, reviewed_spans)
    assert not reviewed_word["errors"]
    row["accepted_semantic_review"] = {"judgment_count": len(review["semantic_judgments"]), "span_count": len(reviewed_spans), "ids_and_ranges_match_initial": True, "word_mapping": reviewed_word}
    row["evidence_paths"].append(str(review_path))
    readiness = materialization_readiness_feedback(inventory=inventory, review=review, registry=FieldRegistrySnapshot.load(root / "input/field-registry.yaml"))
    blockers = readiness["blockers"] if readiness else []
    row["readiness"] = {"status": readiness["status"] if readiness else "ok", "blockers": [{key: blocker.get(key) for key in ("code", "source_entry_id", "field_id")} for blocker in blockers]}
    row["blocked_source_ranges"] = []
    for blocker in blockers:
        for span in reviewed_spans:
            if span["source_entry_id"] == blocker.get("source_entry_id"):
                row["blocked_source_ranges"].append({"source_entry_id": span["source_entry_id"], "extent": span["extent"], "text": span["text"], "role": span["role"], "field_id": span.get("field_id"), "locators": [f["locator"] for f in span["word_fragments"]]})
    row.update(farthest_checkpoint="reviewed semantic ranges; materialization readiness rejected", materialization="not reached; no candidate DOCX", responsibility="Agent requested an unsupported operation on the same original object; Harness refuses without replacement", id_blocker=False)
    if name == "pku-cover-live":
        row["historical_mapping_failure"] = {"source_entry_id": "source-entry-3c2637c9cd402df2261d038e", "old_failure": "materialization_word_fragment_stale", "current_word_mapping": "all selected original fragments resolve; prior package-story resolver defect no longer reproduces"}
    return row


def historical(name):
    root = Path("temp/phase8-v05-20260912") / name
    docfit = root / "work/.docfit"
    inventory = read(docfit / "harness/object-inventory.json")
    review = read(docfit / "harness/semantic-judgments.json")
    entries = {e["source_entry_id"]: e for e in inventory["source_entries"]}
    errors = []
    for span in review["resolved_spans"]:
        entry = entries[span["source_entry_id"]]
        extent = span["extent"]
        expected = entry["text"][extent["start"]:extent["end"]] if extent["kind"] == "text" else entry["text"]
        if span["text"] != expected or span["expected_source_content"] != expected:
            errors.append(span["source_entry_id"])
        assert span["source_snapshot_sha256"] == inventory["document_sha256"]
        assert span["source_inventory_digest"] == inventory["canonical_source_inventory"]["inventory_digest"]
        judgment = review["semantic_judgments"][span["judgment_index"]]
        assert judgment["source_entry_id"] == span["source_entry_id"]
        assert judgment["parts"][span["part_index"]]["text"] == expected
    assert not errors
    source = root / "input/school-template.docx"
    source_sha = sha256_file(source)
    source_current = source_sha == inventory["document_sha256"]
    old_evidence = read(Path("tests/manual-diagnostics/template-id-closure/evidence.json"))
    old_row = next(row for row in old_evidence["rows"] if row["root"] == str(root))
    row = {"task": name, "root": str(root), "level": "historical post-unit identity only; cannot upgrade to initial-inventory full-flow evidence", "initial_inventory": "missing in legacy run", "entry_count": len(entries), "review_span_count": len(review["resolved_spans"]), "persisted_judgments_and_resolved_ranges": "all IDs/text/ranges agree with persisted post-unit inventory", "source_sha256": source_sha, "ledger_source_sha256": inventory["document_sha256"], "source_current": source_current, "prior_replay_record": old_row["current_replay"], "new_materialization": "not performed", "identity_pipeline_defects": [], "evidence_paths": [str(docfit / "harness/object-inventory.json"), str(docfit / "harness/semantic-judgments.json"), "tests/manual-diagnostics/template-id-closure/evidence.json"]}
    if source_current:
        with ZipFile(source) as archive:
            stories = read_word_stories(archive)
        row["word_mapping"] = word_check(stories, review["resolved_spans"])
        assert not row["word_mapping"]["errors"]
        row.update(responsibility="Materialization cleanup/retain carrier conflict; whether semantic choice or overly strict carrier gate is unresolved; no observed object/range substitution", id_blocker=False)
    else:
        row.update(word_mapping="unknown: exact original Word snapshot unavailable; never remap into changed source", responsibility="Historical fixture/source snapshot unavailable; stale-source rejection is expected identity protection", id_blocker=False, evidence_gap="Cannot certify historical original-source write identity without its exact snapshot; do not count this run as a successful replay")
    return row


def main():
    rows = [fresh(name) for name in ("cover-live", "body-live", "pku-cover-live", "pku-abstract-live", "pku-abstract-retry")]
    rows.extend(historical(name) for name in ("njau-03-toc-v6", "njau-07-references-v5"))
    result = {"schema_version": 1, "scope": "Failure classification by original object identity, exact source range, and actual reached checkpoint; semantic completion is not identity acceptance", "verification_level": "read-only audit of real run evidence and exact source Word XML; not new E2E or product acceptance", "rows": rows, "new_runtime_identity_defects": [], "remaining_unknown": ["No writes occurred in the five failed fresh runs, so they prove no successful write identity", "Legacy NJAU07 exact original snapshot is absent; its real source/write identity remains uncertified"]}
    output = Path(__file__).with_name("failure-audit.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "rows": len(rows), "identity_defects": 0, "classification": [{"task": r["task"], "id_blocker": r["id_blocker"], "responsibility": r["responsibility"]} for r in rows]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
