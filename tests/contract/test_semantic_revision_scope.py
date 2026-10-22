from __future__ import annotations

import copy

import pytest

from docfit.template.revision_scope import expand_revision_scopes
from docfit.template.semantic_batches import (
    SemanticBatchCandidateError,
    SemanticBatchCandidateLedger,
    build_semantic_batch_manifest,
    record_semantic_batch_candidate,
)
from docfit.template.source_entries import build_canonical_source_inventory
from tests.support.source_identity import context_packets, source_partition


@pytest.fixture
def case():
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": f"/body/p[{index}]",
                "text": f"text-{index}",
                "object_ref": {"object_id": f"p{index}", "document_sha256": "a" * 64},
            }
            for index in range(1, 5)
        ],
    )
    inventory = {
        "document_sha256": "a" * 64,
        "canonical_source_inventory": canonical.to_json(),
        "field_vocabulary_digest": "b" * 64,
    }
    checkpoint = source_partition(inventory)
    inventory["unit_reading_packets"] = context_packets(inventory)
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    ledger = SemanticBatchCandidateLedger.empty(manifest)
    for batch in manifest.batches:
        ledger = record_semantic_batch_candidate(
            manifest=manifest,
            ledger=ledger,
            batch_id=batch.batch_id,
            allowed_field_ids=(),
            structured_output={
                "status": "complete",
                "summary": "prior",
                "semantic_judgments": [
                    {
                        "source_entry_id": key,
                        "parts": [{"text": "text", "role": "fixed_label"}],
                    }
                    for key in batch.source_entry_ids
                ],
            },
        )
    ids = manifest.required_source_entry_ids
    return dict(
        manifest=manifest,
        ledger=ledger,
        batch=manifest.batches[0],
        editable_source_entry_ids=(ids[0],),
        current_feedback={
            "blockers": [{"code": "ordered_part_text_mismatch", "source_entry_id": ids[0]}],
        },
        pending={},
        output={
            "status": "expand_revision",
            "summary": "related judgments",
            "semantic_judgments": [],
            "revision_request": {
                "source_entry_ids": [ids[1], ids[2]],
                "reason": "共同承担字段填写区",
            },
        },
    )


def test_expansion_preserves_evidence_and_opens_only_requested_existing_entries(case):
    before = copy.deepcopy(case["ledger"].to_json())
    scopes = expand_revision_scopes(**case)
    first, second = case["manifest"].batches
    assert scopes[first.batch_id]["editable_source_entry_ids"] == list(first.source_entry_ids)
    assert scopes[second.batch_id]["editable_source_entry_ids"] == [second.source_entry_ids[0]]
    assert (
        scopes[first.batch_id]["feedback"]["blockers"][0] == case["current_feedback"]["blockers"][0]
    )
    assert (
        scopes[second.batch_id]["feedback"]["blockers"][0]["revision_reason"]
        == "共同承担字段填写区"
    )
    assert case["ledger"].to_json() == before


@pytest.mark.parametrize(
    "damage", ["unknown", "duplicate", "no_reason", "mixed", "no_baseline", "no_change"]
)
def test_invalid_request_never_opens_scope_or_changes_candidates(case, damage):
    request = case["output"]["revision_request"]
    if damage == "unknown":
        request["source_entry_ids"] = ["outside-task"]
    elif damage == "duplicate":
        request["source_entry_ids"] *= 2
    elif damage == "no_reason":
        request["reason"] = " "
    elif damage == "mixed":
        case["output"]["semantic_judgments"] = [{"source_entry_id": "entry"}]
    elif damage == "no_baseline":
        case["editable_source_entry_ids"] = None
    elif damage == "no_change":
        request["source_entry_ids"] = list(case["editable_source_entry_ids"])
    before = copy.deepcopy(case["ledger"].to_json())
    with pytest.raises(SemanticBatchCandidateError):
        expand_revision_scopes(**case)
    assert case["ledger"].to_json() == before


def test_pending_related_revisions_keep_their_original_problem(case):
    second = case["manifest"].batches[1]
    prior = {
        "blockers": [
            {"code": "ordered_part_text_gap", "source_entry_id": second.source_entry_ids[1]}
        ]
    }
    case["pending"] = {
        second.batch_id: {
            "editable_source_entry_ids": [second.source_entry_ids[1]],
            "feedback": prior,
        }
    }
    revisions = expand_revision_scopes(**case)
    assert revisions[second.batch_id]["editable_source_entry_ids"] == list(second.source_entry_ids)
    assert revisions[second.batch_id]["feedback"]["blockers"][0] == prior["blockers"][0]
