"""Read-only real-task diagnosis plus explicitly constructed DOCX execution probes.

Never calls an Agent, edits the original task, bypasses readiness, or publishes.
The constructed probes reuse an existing contract fixture, not school judgments.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from copy import deepcopy
from pathlib import Path

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.materialization.runtime import (
    _cleanup_carrier_for_intent,
    _resolve_all_span_targets,
)
from docfit.template.materialization.validators import _cleanup_conflicts_by_carrier
from docfit.template.source_spans import resolve_semantic_judgments, review_resolved_spans_match
from docfit.template.unit_source import load_initial_inventory, validate_inventory_partition
from docfit.tools.runtime import sha256_file, sha256_json
from docfit.tools.word_parts import read_word_stories, resolve_story_locator
from docfit.tools.word_xml import visible_word_text


def real_task_audit(task: Path) -> dict:
    names = [
        "input/school-template.docx", "input/field-registry.yaml",
        "work/.docfit/initial-source-inventory.json",
        "work/.docfit/unit-boundary-checkpoint.json",
        "work/.docfit/harness/object-inventory.json",
        "work/.docfit/harness/semantic-judgments.json",
        "work/.docfit/post-unit-materialization/materialization.json",
    ]
    before = {name: sha256_file(task / name) for name in names}
    source = task / names[0]
    registry = FieldRegistrySnapshot.load(task / names[1])
    inventory = json.loads((task / names[4]).read_text())
    review = json.loads((task / names[5]).read_text())
    initial = load_initial_inventory(task, sha256_file(source))
    assert inventory["canonical_source_inventory"] == initial["canonical_source_inventory"]
    validate_inventory_partition(inventory)
    assert inventory["field_id_vocabulary"] == registry.pre_input_vocabulary()
    assert review["semantic_judgments_sha256"] == sha256_json(review["semantic_judgments"])
    assert review_resolved_spans_match(
        inventory=inventory, semantic_judgments=review["semantic_judgments"],
    )
    assert inventory["document_sha256"] == review["document_sha256"] == sha256_file(source)
    compiled = build_shadow_materialization_plan(
        inventory=inventory, review=review, registry=registry,
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry,
    )
    with zipfile.ZipFile(source) as archive:
        stories = read_word_stories(archive)
    targets = _resolve_all_span_targets(stories=stories, plan=compiled.plan, inventory=inventory)
    judgments = {j["source_entry_id"]: j for j in review["semantic_judgments"]}
    conflicts = []
    for carrier, intents in _cleanup_conflicts_by_carrier(compiled.intents).items():
        rows = []
        for intent in intents:
            source_id = intent.resolved_spans[0].source_entry_id
            row = {
                "source_entry_id": source_id, "intent_type": intent.intent_type.value,
                "judgment_refs": list(intent.source_judgment_refs),
                "parts": judgments[source_id]["parts"],
                "reason": judgments[source_id].get("reason"),
                "fragments": [
                    {k: f[k] for k in ("locator", "extent", "text") if k in f}
                    for span in intent.resolved_spans for f in span.word_fragments
                ],
            }
            if intent.intent_type.value == "delete_block":
                selected, kind = _cleanup_carrier_for_intent(intent, targets)
                row["execution_carrier_kind"] = kind
                row["exact_targets_are_execution_target"] = all(
                    resolve_story_locator(stories, f["locator"])[1] is selected
                    for span in intent.resolved_spans for f in span.word_fragments
                )
                row["carrier_visible_text"] = visible_word_text(selected)
            rows.append(row)
        conflicts.append({"carrier": carrier, "intents": rows})
    relevant = {row["source_entry_id"] for group in conflicts for row in group["intents"]}
    packet_rows = [
        {"unit_id": unit_id, **row}
        for unit_id, packet in inventory["unit_reading_packets"].items()
        for row in packet.get("source_entries", [])
        if row.get("source_entry_id") in relevant
    ]
    plan_conflicts = [u.to_json() for u in compiled.unsupported
                      if u.reason_code in {
                          "materialization_cleanup_carrier_conflict",
                          "materialization_semantic_scope_conflict",
                      }]
    assert feedback is not None
    emitted_conflicts = [b for b in feedback["blockers"]
                         if b["code"] in {
                          "materialization_cleanup_carrier_conflict",
                          "materialization_semantic_scope_conflict",
                      }]
    emitted_ids = {entry for b in emitted_conflicts for entry in b.get("source_entry_ids", [])}
    plan_ids = {s["ref_id"] for c in plan_conflicts for s in c["scope_refs"]}
    fields = inventory["field_id_vocabulary"]
    result = {
        "level": "real replay: original judgments through planning/readiness/target resolution",
        "source_task": str(task), "input_hashes": before,
        "judgment_count": len(judgments),
        "conflicts": conflicts, "plan_conflicts": plan_conflicts,
        "feedback": feedback,
        "plan_conflict_count": len(plan_conflicts),
        "emitted_conflict_count": len(emitted_conflicts),
        "omitted_conflict_source_entries": sorted(plan_ids - emitted_ids),
        "emitted_blocker_counts": dict(Counter(b["code"] for b in feedback["blockers"])),
        "original_packet_rows": packet_rows,
        "generated_field_ids": [field for field in fields["allowed_field_ids"]
                                if field.startswith("generated.")],
        "original_task_unchanged": before == {name: sha256_file(task / name) for name in names},
        "materialization_run": False, "agent_called": False, "published": False,
    }
    assert result["original_task_unchanged"]
    return result


def constructed_probe(output: Path, mode: str) -> dict:
    # The fixture deliberately includes independent retained text and shapes in
    # one paragraph. No monkeypatching or skipped validation is used.
    from tests.contract.test_shape_cleanup_materialization import V, _case, _read_document

    output.mkdir()
    source, registry, inventory, review = _case(output)
    original_hash = sha256_file(source)
    judgments = [
        {key: deepcopy(value) for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in review["semantic_judgments"]
    ]
    judgments[1]["parts"] = [
        {"text": "same", "role": "manual_region" if mode == "manual" else "fixed_label"},
        {"text": " text", "role": "cleanup"},
    ]
    if mode == "slot":
        judgments[1]["parts"][1] = {
            "text": " text", "role": "fill_slot", "field_id": "thesis.title.zh",
        }
    judgments[2]["parts"][0]["role"] = "fixed_label"
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [{**j, "resolved_spans": [s for s in resolved if s["judgment_index"] == i]}
                for i, j in enumerate(judgments)]
    review.update(semantic_judgments=accepted, resolved_spans=resolved,
                  semantic_judgments_sha256=sha256_json(accepted))
    before_review = deepcopy(review)
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry,
    )
    result = materialize_template_from_semantics(
        source_docx=source, output_docx=output / "diagnostic.docx", registry=registry,
        inventory=inventory, review=review,
    )
    before = _read_document(source)
    after = _read_document(output / "diagnostic.docx")
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    summary = {
        "level": "logic/contract: constructed DOCX, authored judgments, real materializer",
        "mode": mode, "readiness_feedback": feedback, "result_status": result["status"],
        "shapes_before": len(list(before.iter(V + "shape"))),
        "shapes_after": len(list(after.iter(V + "shape"))),
        "first_run_text_after": after.find(f"{w}body/{w}p/{w}r/{w}t").text,
        "cleanup_count": result["cleanup_count"],
        "policy_receipts": result["policy_receipts"],
        "package_validation": result["write"]["package_validation"],
        "source_unchanged": original_hash == sha256_file(source),
        "judgments_unchanged": before_review == review,
        "candidate": str(output / "diagnostic.docx"),
        "agent_called": False, "published": False, "product_acceptance": False,
    }
    (output / "input-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2))
    (output / "materialization.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task, output = args.task.resolve(), args.output.resolve()
    assert not output.is_relative_to(task), "Never write to the source task."
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "real_task": real_task_audit(task),
        "constructed_probes": [constructed_probe(output / mode, mode)
                               for mode in ("fixed", "manual", "slot")],
        "product_acceptance": False,
    }
    (output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "report": str(output / "audit.json"),
        "plan_conflicts": report["real_task"]["plan_conflict_count"],
        "feedback_conflicts": report["real_task"]["emitted_conflict_count"],
        "original_task_unchanged": report["real_task"]["original_task_unchanged"],
        "constructed_probes": [{k: probe[k] for k in (
            "mode", "result_status", "shapes_before", "shapes_after",
            "first_run_text_after", "cleanup_count",
        )} for probe in report["constructed_probes"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
