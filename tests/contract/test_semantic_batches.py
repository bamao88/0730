from __future__ import annotations

from typing import Any

import pytest

from docfit.template.semantic_batches import (
    SemanticBatchCandidateError,
    SemanticBatchCandidateLedger,
    aggregate_semantic_batch_candidates,
    build_semantic_batch_manifest,
    invalidate_semantic_batch_candidates,
    record_semantic_batch_candidate,
    semantic_batch_ids_for_feedback,
    semantic_source_entry_ids_for_feedback,
    validate_persisted_semantic_batch_manifest,
)
from docfit.template.source_entries import build_canonical_source_inventory
from tests.support.source_identity import context_packets, source_partition

JsonObject = dict[str, Any]


def _inventory_and_checkpoint() -> tuple[JsonObject, JsonObject, tuple[str, ...]]:
    source_hash = "a" * 64
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": f"/body/p[{index}]",
                "text": f"entry-{index}",
                "object_ref": {
                    "object_id": f"p{index}",
                    "document_sha256": source_hash,
                },
            }
            for index in range(1, 5)
        ],
    )
    ids = tuple(item.source_entry_id for item in canonical.source_entries)
    inventory: JsonObject = {
        "document_sha256": source_hash,
        "canonical_source_inventory": canonical.to_json(),
        "field_vocabulary_digest": "b" * 64,
    }
    checkpoint = source_partition(
        inventory,
        units=[
            {
                "unit_id": "unit-1",
                "unit_name": "first",
                "start_boundary": {"source_entry_id": ids[0], "edge": "start"},
                "end_boundary": {"source_entry_id": ids[2], "edge": "start"},
            },
            {
                "unit_id": "unit-2",
                "unit_name": "second",
                "start_boundary": {"source_entry_id": ids[2], "edge": "start"},
                "end_boundary": {"source_entry_id": ids[-1], "edge": "end"},
            },
        ],
    )
    inventory["unit_reading_packets"] = context_packets(inventory)
    return inventory, checkpoint, ids


def test_semantic_batches_are_bounded_and_assign_overlap_to_specific_unit() -> None:
    inventory, checkpoint, ids = _inventory_and_checkpoint()

    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )

    assert manifest.required_source_entry_ids == ids
    assert [(batch.unit_id, batch.source_entry_ids) for batch in manifest.batches] == [
        ("unit-1", ids[:2]),
        ("unit-2", ids[2:]),
    ]
    assert all(len(batch.source_entry_ids) <= 2 for batch in manifest.batches)
    assert (
        len(
            {
                source_entry_id
                for batch in manifest.batches
                for source_entry_id in batch.source_entry_ids
            }
        )
        == 4
    )
    assert manifest.to_json()["manifest_digest"] == manifest.manifest_digest
    assert (
        build_semantic_batch_manifest(
            inventory=inventory,
            checkpoint=checkpoint,
            max_entries_per_batch=2,
        )
        == manifest
    )


def test_semantic_batches_do_not_split_one_word_carrier() -> None:
    source_hash = "c" * 64
    objects = [
        {
            "type": "paragraph",
            "locator": f"/body/p[{index}]",
            "text": f"entry-{index}",
            "object_ref": {
                "object_id": f"p{index}",
                "document_sha256": source_hash,
            },
        }
        for index in range(1, 5)
    ]
    objects.append(
        {
            "type": "picture",
            "locator": "/body/p[1]/r[1]",
            "text": "",
            "object_ref": {
                "object_id": "picture-1",
                "document_sha256": source_hash,
            },
        }
    )
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=source_hash,
        inspected_objects=objects,
    )
    paragraph_entry = next(
        item for item in canonical.source_entries if item.provenance[0].locator == "/body/p[1]"
    )
    picture_entry = next(
        item for item in canonical.source_entries if item.provenance[0].locator == "/body/p[1]/r[1]"
    )
    inventory: JsonObject = {
        "document_sha256": source_hash,
        "canonical_source_inventory": canonical.to_json(),
        "field_vocabulary_digest": "d" * 64,
    }

    checkpoint = source_partition(inventory, unit_id="unit-1")
    inventory["unit_reading_packets"] = context_packets(inventory)
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )

    containing_batches = [
        batch
        for batch in manifest.batches
        if paragraph_entry.source_entry_id in batch.source_entry_ids
        or picture_entry.source_entry_id in batch.source_entry_ids
    ]
    assert len(containing_batches) == 1
    assert containing_batches[0].source_entry_ids == (
        paragraph_entry.source_entry_id,
        picture_entry.source_entry_id,
    )
    assert all(len(batch.source_entry_ids) <= 2 for batch in manifest.batches)


def test_semantic_batches_reject_stale_unit_projection() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    inventory["unit_projection_digest"] = "c" * 64

    with pytest.raises(ValueError, match="unit binding is stale"):
        build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)


def test_semantic_batches_reject_unknown_projected_source_entry() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    packets = inventory["unit_reading_packets"]
    assert isinstance(packets, dict)
    packet = packets["unit-2"]
    assert isinstance(packet, dict)
    entries = packet["source_entries"]
    assert isinstance(entries, list)
    entries.append({"source_entry_id": "source-entry-unknown"})

    with pytest.raises(ValueError, match="unknown source entry"):
        build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)


def test_semantic_batches_reject_missing_unit_packet() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    packets = inventory["unit_reading_packets"]
    assert isinstance(packets, dict)
    del packets["unit-2"]

    with pytest.raises(ValueError, match="packet is missing for unit unit-2"):
        build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)


def test_semantic_batches_reject_stale_source_inventory() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    checkpoint["source_hash"] = "d" * 64

    with pytest.raises(ValueError, match="initial inventory binding"):
        build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)


@pytest.mark.parametrize("limit", [0, -1, True])
def test_semantic_batches_require_positive_integer_limit(limit: object) -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()

    with pytest.raises(ValueError, match="positive integer"):
        build_semantic_batch_manifest(
            inventory=inventory,
            checkpoint=checkpoint,
            max_entries_per_batch=limit,  # type: ignore[arg-type]
        )


def _complete_output(source_entry_ids: tuple[str, ...], *, summary: str) -> JsonObject:
    return {
        "status": "complete",
        "summary": summary,
        "semantic_judgments": [
            {
                "source_entry_id": source_entry_id,
                "parts": [{"text": "source", "role": "fixed_label"}],
            }
            for source_entry_id in source_entry_ids
        ],
    }


def test_candidate_ledger_aggregates_only_after_every_batch() -> None:
    inventory, checkpoint, ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    ledger = SemanticBatchCandidateLedger.empty(manifest)
    first, second = manifest.batches

    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=ledger,
        batch_id=first.batch_id,
        structured_output=_complete_output(first.source_entry_ids, summary="first"),
        allowed_field_ids=(),
    )
    with pytest.raises(ValueError, match="ledger is incomplete"):
        aggregate_semantic_batch_candidates(manifest=manifest, ledger=ledger)

    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=ledger,
        batch_id=second.batch_id,
        structured_output=_complete_output(second.source_entry_ids, summary="second"),
        allowed_field_ids=(),
    )
    aggregated = aggregate_semantic_batch_candidates(manifest=manifest, ledger=ledger)

    assert aggregated["status"] == "complete"
    assert aggregated["summary"] == "first | second"
    assert [judgment["source_entry_id"] for judgment in aggregated["semantic_judgments"]] == list(
        ids
    )
    assert ledger.to_json()["candidate_count"] == 2
    assert len(ledger.to_json()["ledger_digest"]) == 64


def test_global_feedback_invalidates_only_affected_candidate_batches() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
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
            structured_output=_complete_output(batch.source_entry_ids, summary=batch.batch_id),
            allowed_field_ids=(),
        )
    affected_entry_id = manifest.batches[1].source_entry_ids[0]

    batch_ids = semantic_batch_ids_for_feedback(
        manifest=manifest,
        feedback={
            "blockers": [
                {
                    "code": "ordered_semantic_parts_text_mismatch",
                    "source_entry_id": affected_entry_id,
                }
            ]
        },
    )
    revised = invalidate_semantic_batch_candidates(
        manifest=manifest,
        ledger=ledger,
        batch_ids=batch_ids,
    )

    assert batch_ids == (manifest.batches[1].batch_id,)
    assert [candidate.batch_id for candidate in revised.candidates] == [
        manifest.batches[0].batch_id
    ]


def test_scoped_batch_revision_preserves_unaffected_accepted_judgments() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    batch = manifest.batches[0]
    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=SemanticBatchCandidateLedger.empty(manifest),
        batch_id=batch.batch_id,
        structured_output=_complete_output(batch.source_entry_ids, summary="accepted"),
        allowed_field_ids=(),
    )
    revised_output = _complete_output((batch.source_entry_ids[0],), summary="regenerated")
    revised_judgments = revised_output["semantic_judgments"]
    assert isinstance(revised_judgments, list)
    revised_judgments[0]["parts"] = [{"text": "source", "role": "cleanup"}]

    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=ledger,
        batch_id=batch.batch_id,
        structured_output=revised_output,
        allowed_field_ids=(),
        editable_source_entry_ids=(batch.source_entry_ids[0],),
    )

    candidate = ledger.candidates[0]
    assert candidate.summary == "accepted"
    assert candidate.semantic_judgments[0]["parts"][0]["role"] == "cleanup"
    assert candidate.semantic_judgments[1]["parts"][0]["role"] == "fixed_label"


def test_scoped_batch_revision_rejects_judgment_outside_revision_scope() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    batch = manifest.batches[0]
    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=SemanticBatchCandidateLedger.empty(manifest),
        batch_id=batch.batch_id,
        structured_output=_complete_output(batch.source_entry_ids, summary="accepted"),
        allowed_field_ids=(),
    )

    with pytest.raises(SemanticBatchCandidateError) as caught:
        record_semantic_batch_candidate(
            manifest=manifest,
            ledger=ledger,
            batch_id=batch.batch_id,
            structured_output=_complete_output(
                (batch.source_entry_ids[1],),
                summary="wrong scope",
            ),
            allowed_field_ids=(),
            editable_source_entry_ids=(batch.source_entry_ids[0],),
        )

    assert caught.value.feedback["failure"]["code"] == "semantic_batch_coverage_invalid"
    assert any(
        blocker["code"] == "semantic_batch_entries_unexpected"
        for blocker in caught.value.feedback["blockers"]
    )


@pytest.mark.parametrize(
    "part",
    [
        {"text": "source", "role": "cleanup"},
        {"text": "source", "role": "fill_slot", "field_id": "author.name.zh"},
    ],
)
def test_scoped_text_revision_can_rejudge_responsibility(part: JsonObject) -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    batch = manifest.batches[0]
    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=SemanticBatchCandidateLedger.empty(manifest),
        batch_id=batch.batch_id,
        structured_output=_complete_output(batch.source_entry_ids, summary="candidate"),
        allowed_field_ids=("author.name.zh",),
    )
    output = _complete_output((batch.source_entry_ids[0],), summary="rejudged")
    output["semantic_judgments"][0]["parts"] = [part]
    revised = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=ledger,
        batch_id=batch.batch_id,
        structured_output=output,
        allowed_field_ids=("author.name.zh",),
        editable_source_entry_ids=(batch.source_entry_ids[0],),
    )
    assert revised.candidates[0].semantic_judgments[0]["parts"] == [part]
    assert revised.candidates[0].semantic_judgments[1] == ledger.candidates[0].semantic_judgments[1]
    output["semantic_judgments"][0]["parts"] = [
        {"text": "source", "role": "fill_slot", "field_id": "invented.field"}
    ]
    with pytest.raises(SemanticBatchCandidateError):
        record_semantic_batch_candidate(
            manifest=manifest,
            ledger=ledger,
            batch_id=batch.batch_id,
            structured_output=output,
            allowed_field_ids=("author.name.zh",),
            editable_source_entry_ids=(batch.source_entry_ids[0],),
        )


def test_feedback_source_entries_keep_canonical_order() -> None:
    inventory, checkpoint, ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )

    affected = semantic_source_entry_ids_for_feedback(
        manifest=manifest,
        feedback={"blockers": [{"source_entry_ids": [ids[3], ids[0]]}]},
    )

    assert affected == (ids[0], ids[3])


@pytest.mark.parametrize(
    "feedback",
    [
        {"blockers": [{"code": "global_failure"}]},
        {"blockers": [{"source_entry_id": "source-entry-unknown"}]},
        {"blockers": []},
    ],
)
def test_global_feedback_fails_closed_when_batch_is_not_routable(
    feedback: JsonObject,
) -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )

    with pytest.raises(ValueError):
        semantic_batch_ids_for_feedback(manifest=manifest, feedback=feedback)


def test_candidate_ledger_rejects_missing_batch_entries() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    first = manifest.batches[0]
    incomplete_ids = first.source_entry_ids[:-1]

    with pytest.raises(SemanticBatchCandidateError) as caught:
        record_semantic_batch_candidate(
            manifest=manifest,
            ledger=SemanticBatchCandidateLedger.empty(manifest),
            batch_id=first.batch_id,
            structured_output=_complete_output(incomplete_ids, summary="incomplete"),
            allowed_field_ids=(),
        )

    assert caught.value.feedback["failure"]["code"] == "semantic_batch_coverage_invalid"
    assert caught.value.feedback["blockers"][0]["code"] == "semantic_batch_entries_missing"


def test_candidate_ledger_rejects_source_entry_owned_by_another_batch() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    first, second = manifest.batches

    with pytest.raises(SemanticBatchCandidateError) as caught:
        record_semantic_batch_candidate(
            manifest=manifest,
            ledger=SemanticBatchCandidateLedger.empty(manifest),
            batch_id=first.batch_id,
            structured_output=_complete_output(
                (*first.source_entry_ids, second.source_entry_ids[0]),
                summary="cross-batch",
            ),
            allowed_field_ids=(),
        )

    assert any(
        blocker["code"] == "ordered_semantic_source_entry_unknown"
        for blocker in caught.value.feedback["blockers"]
    )


def test_candidate_ledger_rejects_stale_manifest_binding() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)
    ledger = SemanticBatchCandidateLedger.empty(manifest)
    stale = SemanticBatchCandidateLedger(
        manifest_digest="f" * 64,
        source_sha256=ledger.source_sha256,
        source_inventory_digest=ledger.source_inventory_digest,
        unit_projection_digest=ledger.unit_projection_digest,
        field_vocabulary_digest=ledger.field_vocabulary_digest,
    )

    with pytest.raises(ValueError, match="ledger is stale"):
        record_semantic_batch_candidate(
            manifest=manifest,
            ledger=stale,
            batch_id=manifest.batches[0].batch_id,
            structured_output=_complete_output(
                manifest.batches[0].source_entry_ids,
                summary="stale",
            ),
            allowed_field_ids=(),
        )


def test_candidate_ledger_round_trips_incomplete_resume_state() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(
        inventory=inventory,
        checkpoint=checkpoint,
        max_entries_per_batch=2,
    )
    first = manifest.batches[0]
    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=SemanticBatchCandidateLedger.empty(manifest),
        batch_id=first.batch_id,
        structured_output=_complete_output(first.source_entry_ids, summary="resume"),
        allowed_field_ids=(),
    )

    restored = SemanticBatchCandidateLedger.from_json(
        ledger.to_json(),
        manifest=manifest,
        allowed_field_ids=(),
    )

    assert restored == ledger
    with pytest.raises(ValueError, match="ledger is incomplete"):
        aggregate_semantic_batch_candidates(manifest=manifest, ledger=restored)


def test_candidate_ledger_rejects_tampered_candidate() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)
    batch = manifest.batches[0]
    ledger = record_semantic_batch_candidate(
        manifest=manifest,
        ledger=SemanticBatchCandidateLedger.empty(manifest),
        batch_id=batch.batch_id,
        structured_output=_complete_output(batch.source_entry_ids, summary="original"),
        allowed_field_ids=(),
    )
    payload = ledger.to_json()
    candidates = payload["candidates"]
    assert isinstance(candidates, list)
    candidates[0]["summary"] = "tampered"

    with pytest.raises(ValueError, match="ledger digest is invalid"):
        SemanticBatchCandidateLedger.from_json(
            payload,
            manifest=manifest,
            allowed_field_ids=(),
        )


def test_persisted_manifest_must_exactly_match_current_manifest() -> None:
    inventory, checkpoint, _ids = _inventory_and_checkpoint()
    manifest = build_semantic_batch_manifest(inventory=inventory, checkpoint=checkpoint)

    assert (
        validate_persisted_semantic_batch_manifest(
            manifest.to_json(),
            expected=manifest,
        )
        == manifest
    )
    stale = manifest.to_json()
    stale["max_entries_per_batch"] = 1
    with pytest.raises(ValueError, match="manifest is stale or unsupported"):
        validate_persisted_semantic_batch_manifest(stale, expected=manifest)
