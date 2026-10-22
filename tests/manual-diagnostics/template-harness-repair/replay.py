"""Read-only current-contract replay; never modifies the supplied real task roots."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from docfit.app.prepare_template import (
    _agent_visible_feedback_packet,
    build_semantic_batch_prompt,
)
from docfit.fields import FieldRegistrySnapshot
from docfit.template.batch_review import batch_text_feedback
from docfit.template.harness import _decode_whitespace_parts
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.materialization.runtime import materialize_template_from_semantics
from docfit.template.revision_context import build_revision_context
from docfit.template.revision_journal import SemanticRevisionJournal
from docfit.template.semantic_batches import (
    SemanticBatchCandidateLedger,
    aggregate_semantic_batch_candidates,
    build_semantic_batch_manifest,
    record_semantic_batch_candidate,
)
from docfit.template.semantic_recovery import classify_semantic_feedback
from docfit.template.source_spans import SourceSpanResolutionError, resolve_semantic_judgments
from docfit.template.unit_source import load_initial_inventory
from docfit.tools.runtime import ToolFailure, sha256_file


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def task_inputs(root: Path) -> tuple[dict, dict, FieldRegistrySnapshot]:
    source_hash = sha256_file(root / "input/school-template.docx")
    initial = load_initial_inventory(root, source_hash)
    inventory = read(root / "work/.docfit/harness/object-inventory.json")
    assert inventory["document_sha256"] == source_hash
    assert inventory["canonical_source_inventory"] == initial["canonical_source_inventory"]
    checkpoint = read(root / "work/.docfit/unit-boundary-checkpoint.json")
    registry = FieldRegistrySnapshot.load(root / "input/field-registry.yaml")
    assert inventory["field_id_vocabulary"] == registry.pre_input_vocabulary()
    return inventory, checkpoint, registry


def range_errors(inventory: dict, judgments: list[dict]) -> list[dict]:
    decoded, feedback = _decode_whitespace_parts(judgments)
    assert feedback is None
    try:
        resolve_semantic_judgments(inventory=inventory, judgments=decoded)
    except SourceSpanResolutionError as error:
        return error.blockers
    return []


def journal_replay(output: Path, manifest, ledger, allowed: tuple[str, ...]) -> dict:
    # New replay evidence only: these are NOT the lost historical prompts or new Agent outputs.
    kwargs = dict(
        directory=output / "journal-replay",
        ledger_path=output / "replayed-ledger.json",
        manifest=manifest,
        allowed_field_ids=allowed,
        evidence_mode="replay",
    )
    assert not kwargs["directory"].exists(), "Use a fresh diagnostic output directory."
    journal = SemanticRevisionJournal(**kwargs)
    for batch in manifest.batches:
        historical = next(row for row in ledger.candidates if row.batch_id == batch.batch_id)
        submitted = {
            "status": "complete",
            "summary": historical.summary,
            "semantic_judgments": list(historical.semantic_judgments),
        }
        request_id = journal.request(
            batch_id=batch.batch_id,
            prompt=build_semantic_batch_prompt(manifest=manifest, batch=batch),
            feedback=None,
            editable_source_entry_ids=None,
        )
        journal.record(
            "response",
            {
                "request_id": request_id,
                "is_error": False,
                "structured_output": submitted,
                "historical_source": "frozen candidate ledger",
            },
        )
        merged = record_semantic_batch_candidate(
            manifest=manifest,
            ledger=journal.ledger,
            batch_id=batch.batch_id,
            structured_output=submitted,
            allowed_field_ids=allowed,
        )
        journal.commit(merged, request_id=request_id)
    recovered = SemanticRevisionJournal(**kwargs)
    assert recovered.ledger == ledger
    # A diagnostic history must never masquerade as a runtime recovery record.
    try:
        SemanticRevisionJournal(**{**kwargs, "evidence_mode": "runtime"})
    except ToolFailure as error:
        assert error.code == "semantic_revision_journal_invalid"
    else:
        raise AssertionError("Replay evidence was accepted as runtime history.")
    return {
        "historical_outputs_replayed_without_changes": True,
        "candidate_versions": len(ledger.candidates),
        "event_count": len(recovered.events),
        "restored_ledger_exact": True,
        "runtime_recovery_rejected": True,
        "prompts_generated_for_replay_not_sent_to_agent": True,
        "original_missing_history_not_reconstructed": True,
    }


def run(body_task: Path, table_task: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    watched = [
        path
        for root in (body_task, table_task)
        for path in [*(root / "input").glob("*"), *(root / "work/.docfit").rglob("*.json")]
        if path.is_file()
    ]
    hashes = {str(path): sha256_file(path) for path in watched}
    inventory, proof, registry = task_inputs(body_task)
    manifest = build_semantic_batch_manifest(inventory=inventory, checkpoint=proof)
    raw_ledger = read(body_task / "work/.docfit/harness/semantic-batch-candidates.json")
    allowed = tuple(registry.pre_input_vocabulary()["allowed_field_ids"])
    ledger = SemanticBatchCandidateLedger.from_json(
        raw_ledger,
        manifest=manifest,
        allowed_field_ids=allowed,
    )
    journal_report = journal_replay(output, manifest, ledger, allowed)
    aggregated = aggregate_semantic_batch_candidates(manifest=manifest, ledger=ledger)
    errors = range_errors(inventory, aggregated["semantic_judgments"])
    assert errors, "This diagnostic expects the original rejected real candidate."
    local_errors = []
    for batch in manifest.batches:
        candidate = next(row for row in ledger.candidates if row.batch_id == batch.batch_id)
        feedback = batch_text_feedback(
            inventory=inventory,
            judgments=list(candidate.semantic_judgments),
            required_source_entry_ids=batch.source_entry_ids,
        )
        if feedback is not None:
            assert feedback["recovery"]["action"] == "revise"
            for blocker in feedback["blockers"]:
                normalized = dict(blocker)
                field = blocker.get("field", "")
                match = re.match(r"semantic_judgments\[(\d+)\]", field)
                if match:
                    entry_id = candidate.semantic_judgments[int(match[1])]["source_entry_id"]
                    assert entry_id == blocker["source_entry_id"]
                    global_index = next(
                        i
                        for i, row in enumerate(aggregated["semantic_judgments"])
                        if row["source_entry_id"] == entry_id
                    )
                    normalized["field"] = (
                        f"semantic_judgments[{global_index}]" + field[match.end() :]
                    )
                local_errors.append(normalized)
    # Only the array offset changes between batch and aggregate; part positions,
    # source identities, error categories and full text must stay exactly equal.
    assert sorted(json.dumps(row, sort_keys=True) for row in local_errors) == sorted(
        json.dumps(row, sort_keys=True) for row in errors
    )
    classified = classify_semantic_feedback({"status": "needs_input", "blockers": errors})
    assert classified["recovery"]["action"] == "revise"
    visible = _agent_visible_feedback_packet(
        classified, next_step="Revise affected source entries."
    )
    for original_blocker, displayed in zip(errors, visible["affected"], strict=True):
        for key in ("expected_text", "submitted_text", "uncovered_text"):
            if key in original_blocker:
                assert displayed[key] == original_blocker[key]
    (output / "visible-feedback.json").write_text(json.dumps(visible, ensure_ascii=False, indent=2))
    assert ledger.to_json() == raw_ledger

    # Deliberate test revision; no claim this new classification came from the Agent.
    entry_id = errors[0]["source_entry_id"]
    batch = next(batch for batch in manifest.batches if entry_id in batch.source_entry_ids)
    original = next(j for j in aggregated["semantic_judgments"] if j["source_entry_id"] == entry_id)
    revision = copy.deepcopy(original)
    part = revision["parts"][0]
    part["role"] = "fixed_label" if part["role"] == "cleanup" else "cleanup"
    part.pop("field_id", None)
    updated = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=ledger,
        batch_id=batch.batch_id,
        structured_output={
            "status": "complete",
            "summary": "injected role revision",
            "semantic_judgments": [revision],
        },
        allowed_field_ids=allowed,
        editable_source_entry_ids=(entry_id,),
    )
    updated_output = aggregate_semantic_batch_candidates(manifest=manifest, ledger=updated)
    updated_errors = range_errors(inventory, updated_output["semantic_judgments"])
    assert len(updated_errors) == len(errors), "Rejudging roles must not bypass text closure."
    assert ledger.to_json() == raw_ledger

    revision_context = build_revision_context(
        inventory=inventory,
        batch=batch,
        ledger=ledger,
        feedback={"blockers": errors},
        editable_source_entry_ids=(entry_id,),
    )
    source_by_id = {
        entry["source_entry_id"]: entry["text"] for entry in inventory["source_entries"]
    }
    assert all(
        entry["text"] == source_by_id[entry["source_entry_id"]]
        for entry in revision_context["source_entries"]
    )
    assert original in revision_context["previous_judgments"]
    (output / "revision-context.json").write_text(
        json.dumps(revision_context, ensure_ascii=False, indent=2) + "\n"
    )

    table_inventory, table_proof, table_registry = task_inputs(table_task)
    build_semantic_batch_manifest(inventory=table_inventory, checkpoint=table_proof)
    review = read(table_task / "work/.docfit/harness/semantic-judgments.json")
    before = copy.deepcopy(review)
    feedback = materialization_readiness_feedback(
        inventory=table_inventory,
        review=review,
        registry=table_registry,
    )
    assert feedback is not None and feedback["recovery"]["kind"] == "execution_unsupported"
    candidate = output / "must-not-be-created.docx"
    assert not candidate.exists()
    try:
        materialize_template_from_semantics(
            source_docx=table_task / "input/school-template.docx",
            output_docx=candidate,
            registry=table_registry,
            inventory=table_inventory,
            review=review,
        )
    except ToolFailure as error:
        assert error.origin == "tool" and not error.retryable and error.status == "error"
        failure = error.result()["failure"]
    else:
        raise AssertionError("Unsupported real table execution must stop.")
    assert review == before and not candidate.exists()
    assert hashes == {path: sha256_file(Path(path)) for path in hashes}
    report = {
        "real_replay": {
            "body_task": str(body_task),
            "table_task": str(table_task),
            "original_body_judgments": len(aggregated["semantic_judgments"]),
            "original_range_blockers": errors,
            "body_candidate_unchanged": True,
            "local_review_matches_aggregate_blockers": True,
            "local_review_batch_count": len(manifest.batches),
            "revision_journal": journal_report,
            "semantic_feedback_text_exact": True,
            "semantic_feedback_recovery": classified["recovery"],
            "revision_context": {
                "source_entry_count": len(revision_context["source_entries"]),
                "previous_judgment_count": len(revision_context["previous_judgments"]),
                "source_text_exact": True,
                "previous_judgment_present": True,
            },
            "table_feedback": feedback,
            "table_failure": failure,
            "table_judgments_unchanged": True,
            "candidate_written": False,
            "input_and_task_hashes": hashes,
        },
        "injected_revision_contract_check": {
            "not_agent_generated": True,
            "entry_id": entry_id,
            "before": original,
            "after": revision,
            "candidate_revision_accepted": True,
            "remaining_range_blockers": len(updated_errors),
        },
        "e2e_agent_loop": False,
        "product_acceptance": False,
    }
    (output / "replay.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "original_body_blockers": len(errors),
                "table_route": feedback["recovery"],
                "original_tasks_unchanged": True,
                "candidate_written": False,
                "report": str(output / "replay.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-task", type=Path, required=True)
    parser.add_argument("--table-task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.body_task.resolve(), args.table_task.resolve(), args.output.resolve())
