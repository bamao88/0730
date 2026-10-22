from __future__ import annotations

import copy
import json

import pytest

from docfit.template.revision_journal import SemanticRevisionJournal
from docfit.template.semantic_batches import (
    SemanticBatchCandidateLedger,
    build_semantic_batch_manifest,
    record_semantic_batch_candidate,
)
from docfit.template.source_entries import build_canonical_source_inventory
from docfit.tools.runtime import ToolFailure, atomic_write_json
from tests.support.source_identity import context_packets, source_partition


@pytest.fixture
def case(tmp_path):
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "姓名：  ",
                "object_ref": {"object_id": "p1", "document_sha256": "a" * 64},
            }
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
    )
    kwargs = dict(
        directory=tmp_path / "revisions",
        ledger_path=tmp_path / "ledger.json",
        manifest=manifest,
        allowed_field_ids=("author.name.zh",),
    )
    output = {
        "status": "complete",
        "summary": "判断",
        "semantic_judgments": [
            {
                "source_entry_id": manifest.required_source_entry_ids[0],
                "parts": [{"text": "姓名：  ", "role": "fixed_label"}],
            }
        ],
    }
    return kwargs, output


def submit(journal, output):
    request = journal.request(
        batch_id=journal.manifest.batches[0].batch_id,
        prompt="原文：姓名：  \n实际请求",
        feedback=None,
        editable_source_entry_ids=None,
    )
    journal.record(
        "response",
        {
            "request_id": request,
            "session_id": "test-session",
            "is_error": False,
            "structured_output": output,
        },
    )
    return request


def candidate(journal, output):
    return record_semantic_batch_candidate(
        manifest=journal.manifest,
        ledger=journal.ledger,
        batch_id=journal.manifest.batches[0].batch_id,
        structured_output=output,
        allowed_field_ids=journal.allowed_field_ids,
    )


def test_rejected_output_feedback_and_exact_prompt_survive_reopening(case):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    rejected = copy.deepcopy(output)
    rejected["semantic_judgments"][0]["parts"][0]["role"] = "invalid-role"
    request = submit(journal, rejected)
    feedback = {"blockers": [{"message": "Invalid role", "source_entry_id": "entry"}]}
    journal.record(
        "local_rejected",
        {
            "request_id": request,
            "feedback": feedback,
            "output": rejected,
        },
    )
    recovered = SemanticRevisionJournal(**kwargs)
    assert not recovered.ledger.candidates
    assert recovered.events[0]["data"]["prompt"] == "原文：姓名：  \n实际请求"
    assert recovered.local_revision(journal.manifest.batches[0].batch_id) == {
        "feedback": feedback,
        "previous_submission": rejected,
        "editable_source_entry_ids": None,
    }
    # A successful revision closes the local rejection but does not claim global acceptance.
    request = submit(recovered, output)
    recovered.commit(candidate(recovered, output), request_id=request)
    assert (
        SemanticRevisionJournal(**kwargs).local_revision(journal.manifest.batches[0].batch_id)
        is None
    )


def test_versions_preserve_role_changes_and_full_diff(case):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = submit(journal, output)
    journal.commit(candidate(journal, output), request_id=request)
    revised = copy.deepcopy(output)
    revised["semantic_judgments"][0]["parts"][0]["role"] = "manual_region"
    request = submit(journal, revised)
    journal.commit(candidate(journal, revised), request_id=request)
    recovered = SemanticRevisionJournal(**kwargs)
    diff = recovered.events[-1]["data"]["diff"]
    assert diff[0]["before"] == output["semantic_judgments"][0]
    assert diff[0]["after"] == revised["semantic_judgments"][0]
    assert recovered.ledger == journal.ledger


def test_crash_after_commit_event_recovers_projection(case, monkeypatch):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = submit(journal, output)
    expected = candidate(journal, output)

    def fail_projection(path, payload):
        if path == kwargs["ledger_path"]:
            raise OSError("simulated projection write failure")
        atomic_write_json(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr("docfit.template.revision_journal.atomic_write_json", fail_projection)
        with pytest.raises(ToolFailure, match="projection write failure"):
            journal.commit(expected, request_id=request)
    disk_before = json.loads(kwargs["ledger_path"].read_text())
    assert disk_before["candidate_count"] == 0
    recovered = SemanticRevisionJournal(**kwargs)
    assert recovered.ledger == expected
    assert json.loads(kwargs["ledger_path"].read_text()) == expected.to_json()


def test_failed_event_write_does_not_change_candidate_or_record_success(case, monkeypatch):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = submit(journal, output)
    original = kwargs["ledger_path"].read_bytes()

    def fail_event(*args, **kw):
        raise OSError("simulated full disk")

    with monkeypatch.context() as patch:
        patch.setattr("docfit.template.revision_journal.atomic_write_json", fail_event)
        with pytest.raises(ToolFailure, match="full disk"):
            journal.commit(candidate(journal, output), request_id=request)
    assert kwargs["ledger_path"].read_bytes() == original
    assert not SemanticRevisionJournal(**kwargs).ledger.candidates


def test_unrecorded_or_changed_submission_cannot_be_committed(case):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = journal.request(
        batch_id=journal.manifest.batches[0].batch_id,
        prompt="request",
        feedback=None,
        editable_source_entry_ids=None,
    )
    with pytest.raises(ToolFailure, match="successful structured response"):
        journal.commit(candidate(journal, output), request_id=request)
    request = submit(journal, output)
    different = copy.deepcopy(output)
    different["semantic_judgments"][0]["parts"][0]["role"] = "manual_region"
    with pytest.raises(ToolFailure, match="differs from the submitted"):
        journal.commit(candidate(journal, different), request_id=request)


def test_stale_submission_and_second_writer_cannot_overwrite_candidates(case):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    other = SemanticRevisionJournal(**kwargs)
    old_request = submit(journal, output)
    request = submit(journal, output)
    journal.commit(candidate(journal, output), request_id=request)
    with pytest.raises(ToolFailure, match="stale candidate baseline"):
        journal.commit(journal.ledger, request_id=old_request)
    with pytest.raises(ToolFailure, match="Another writer"):
        submit(other, output)


@pytest.mark.parametrize("damage", ["digest", "gap", "manifest", "legacy"])
def test_invalid_history_is_rejected_without_overwriting_evidence(case, damage):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = submit(journal, output)
    journal.commit(candidate(journal, output), request_id=request)
    files = sorted(kwargs["directory"].glob("*.json"))
    if damage == "legacy":
        for path in files:
            path.unlink()
    elif damage == "gap":
        files[0].unlink()
    else:
        event = json.loads(files[0].read_text())
        event["manifest_digest" if damage == "manifest" else "event_digest"] = "corrupt"
        files[0].write_text(json.dumps(event))
    before = kwargs["ledger_path"].read_bytes()
    with pytest.raises(ToolFailure) as error:
        SemanticRevisionJournal(**kwargs)
    assert error.value.origin == "harness"
    assert not error.value.retryable
    assert kwargs["ledger_path"].read_bytes() == before


def test_response_alone_never_becomes_candidate(case):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    submit(journal, output)
    recovered = SemanticRevisionJournal(**kwargs)
    assert recovered.ledger == SemanticBatchCandidateLedger.empty(journal.manifest)


@pytest.mark.parametrize("status,is_error", [("needs_input", False), ("complete", True)])
def test_noncommittable_responses_remain_evidence_only(case, status, is_error):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = journal.request(
        batch_id=journal.manifest.batches[0].batch_id,
        prompt="question",
        feedback=None,
        editable_source_entry_ids=None,
    )
    output["status"] = status
    journal.record(
        "response",
        {
            "request_id": request,
            "is_error": is_error,
            "structured_output": output,
            "result_text": "缺少学校说明" if status == "needs_input" else "SDK error",
        },
    )
    if status == "needs_input":
        journal.record("needs_input", {"request_id": request})
    recovered = SemanticRevisionJournal(**kwargs)
    assert recovered.events[1]["data"]["structured_output"] == output
    assert not recovered.ledger.candidates


def test_replay_events_cannot_be_resumed_as_runtime(case):
    kwargs, output = case
    replay = SemanticRevisionJournal(**kwargs, evidence_mode="replay")
    request = submit(replay, output)
    replay.commit(candidate(replay, output), request_id=request)
    with pytest.raises(ToolFailure, match="binding or digest"):
        SemanticRevisionJournal(**kwargs)


def test_malformed_event_is_a_harness_failure(case):
    kwargs, _ = case
    journal = SemanticRevisionJournal(**kwargs)
    path = journal.directory / "00000001.json"
    path.write_text("[]")
    with pytest.raises(ToolFailure, match="event must be an object"):
        SemanticRevisionJournal(**kwargs)


def test_identical_candidate_content_does_not_reset_version_identity(case):
    kwargs, output = case
    journal = SemanticRevisionJournal(**kwargs)
    request = submit(journal, output)
    journal.commit(candidate(journal, output), request_id=request)
    old_request = submit(journal, output)
    newer_request = submit(journal, output)
    journal.commit(journal.ledger, request_id=newer_request)
    # The content digest is identical, but an earlier request still has an old parent version.
    with pytest.raises(ToolFailure, match="stale candidate baseline"):
        journal.commit(journal.ledger, request_id=old_request)
