from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest

from docfit.template.revision_budget import RevisionBudget
from docfit.template.revision_journal import SemanticRevisionJournal
from docfit.template.semantic_batches import build_semantic_batch_manifest
from docfit.template.source_entries import build_canonical_source_inventory
from docfit.tools.runtime import ToolFailure
from tests.support.source_identity import context_packets, source_partition


@pytest.fixture
def case(tmp_path):
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[
            {
                "type": "paragraph",
                "locator": f"/body/p[{i}]",
                "text": f"entry-{i}",
                "object_ref": {"object_id": f"p{i}", "document_sha256": "a" * 64},
            }
            for i in range(1, 4)
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
        inventory=inventory, checkpoint=checkpoint, max_entries_per_batch=1
    )
    kwargs = dict(
        directory=tmp_path / "revisions",
        ledger_path=tmp_path / "ledger.json",
        manifest=manifest,
        allowed_field_ids=("author.name.zh",),
    )
    return kwargs


def reject(
    journal,
    index=0,
    text="wrong",
    role="fixed_label",
    code="ordered_part_text_gap",
    output_override=None,
    blocker_override=None,
):
    batch = journal.manifest.batches[index]
    output = (
        output_override
        if output_override is not None
        else {
            "status": "complete",
            "summary": role,
            "semantic_judgments": [
                {
                    "source_entry_id": batch.source_entry_ids[0],
                    "parts": [{"text": text, "role": role, "reason": role}],
                }
            ],
        }
    )
    request = journal.request(
        batch_id=batch.batch_id, prompt="request", feedback=None, editable_source_entry_ids=None
    )
    journal.record(
        "response",
        {
            "request_id": request,
            "session_id": "test",
            "is_error": False,
            "structured_output": output,
        },
    )
    blocker = (
        blocker_override
        if blocker_override is not None
        else {"code": code, "source_entry_id": batch.source_entry_ids[0]}
    )
    journal.record(
        "local_rejected",
        {"request_id": request, "output": output, "feedback": {"blockers": [blocker]}},
    )


def check(budget, journal, index=0):
    budget.check_request(journal, source_entry_ids=journal.manifest.batches[index].source_entry_ids)


def test_independent_failures_have_separate_limits_but_share_query_cap(case):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=6, max_problem_failures=3)
    budget.bind(journal)
    for index in range(3):
        for attempt in range(2):
            check(budget, journal, index)
            reject(journal, index=index, text=f"wrong-{attempt}")
    recovered = SemanticRevisionJournal(**case)
    with pytest.raises(ToolFailure) as caught:
        check(budget, recovered, 2)
    assert caught.value.code == "semantic_query_budget_exhausted"
    assert caught.value.status == "error"
    assert caught.value.origin == "harness"


def test_no_progress_persists_and_ignores_role_reason_and_error_code_changes(case):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=32)
    budget.bind(journal)
    for role, code in zip(
        ("fixed_label", "cleanup", "manual_region"),
        ("ordered_part_text_gap", "ordered_part_text_mismatch", "ordered_part_text_gap"),
        strict=True,
    ):
        check(budget, journal)
        reject(journal, role=role, code=code)
    recovered = SemanticRevisionJournal(**case)
    budget.bind(recovered)
    with pytest.raises(ToolFailure) as caught:
        check(budget, recovered)
    assert caught.value.code == "semantic_revision_no_progress"
    check(budget, recovered, 1)
    # Expanding to a larger scope cannot hide the exhausted original entry.
    with pytest.raises(ToolFailure):
        budget.check_request(
            recovered, source_entry_ids=recovered.manifest.required_source_entry_ids
        )


def test_changing_invalid_text_does_not_reset_problem_limit(case):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=32, max_problem_failures=3)
    budget.bind(journal)
    for attempt in range(3):
        reject(journal, text=f"wrong-{attempt}")
    with pytest.raises(ToolFailure) as caught:
        check(budget, journal)
    assert caught.value.code == "semantic_problem_budget_exhausted"


@pytest.mark.parametrize(
    "judgments",
    [None, 42, {}, [{"source_entry_id": []}], [{"source_entry_id": "invented", "parts": []}]],
)
def test_malformed_submission_and_invented_ids_cannot_reset_limits(case, judgments):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=32)
    budget.bind(journal)
    for _ in range(3):
        reject(
            journal,
            output_override={"semantic_judgments": judgments},
            blocker_override={
                "code": "invalid",
                "field": "semantic_judgments[0]",
                "source_entry_id": "invented",
            },
        )
    with pytest.raises(ToolFailure) as caught:
        check(budget, journal)
    assert caught.value.code == "semantic_revision_no_progress"


def test_saved_policy_and_outstanding_query_survive_resume(case):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=1)
    budget.bind(journal)
    journal.request(
        batch_id=journal.manifest.batches[0].batch_id,
        prompt="request",
        feedback=None,
        editable_source_entry_ids=None,
    )
    recovered = SemanticRevisionJournal(**case)
    budget.bind(recovered)
    with pytest.raises(ToolFailure) as caught:
        check(budget, recovered)
    assert caught.value.code == "semantic_query_budget_exhausted"
    with pytest.raises(ToolFailure) as changed:
        RevisionBudget(max_queries=2).bind(recovered)
    assert changed.value.code == "semantic_budget_policy_changed"


def test_query_time_stops_at_response_or_failure_and_charges_unclosed_crash(case):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=32, max_query_seconds=20)
    budget.bind(journal)
    reject(journal)
    journal.request(
        batch_id=journal.manifest.batches[1].batch_id,
        prompt="request",
        feedback=None,
        editable_source_entry_ids=None,
    )
    journal.record(
        "run_failed",
        {
            "ledger_digest": journal.ledger.to_json()["ledger_digest"],
            "failure": {"code": "interrupted"},
        },
    )
    # Deterministic clock fixture: use a copy so hashed on-disk evidence stays intact.
    journal.events = copy.deepcopy(journal.events)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    offsets = [0, 0, 4, 5, 10, 16]
    for event, seconds in zip(journal.events, offsets, strict=True):
        event["created_at"] = (start + timedelta(seconds=seconds)).isoformat()
    assert budget.query_seconds(journal, now=start + timedelta(days=1)) == 10
    journal.events.pop()  # Simulate a crash before the terminal event was persisted.
    assert budget.query_seconds(journal, now=start + timedelta(seconds=40)) == 34
    with pytest.raises(ToolFailure) as caught:
        budget.remaining_seconds(journal)
    assert caught.value.code == "semantic_query_time_budget_exhausted"


@pytest.mark.parametrize("failure_code", ["semantic_query_time_budget_exhausted", "interrupted"])
def test_saved_phase_timeout_cannot_reopen_shorter_query_clock_on_resume(case, failure_code):
    journal = SemanticRevisionJournal(**case)
    budget = RevisionBudget(max_queries=32)
    budget.bind(journal)
    reject(journal)
    journal.record(
        "run_failed",
        {
            "ledger_digest": journal.ledger.to_json()["ledger_digest"],
            "failure": {"code": failure_code},
        },
    )
    recovered = SemanticRevisionJournal(**case)
    assert budget.query_seconds(recovered) < budget.max_query_seconds
    before = len(recovered.events)
    if failure_code == "interrupted":
        check(budget, recovered)
    else:
        with pytest.raises(ToolFailure) as caught:
            check(budget, recovered)
        assert caught.value.code == "semantic_query_time_budget_exhausted"
    assert len(recovered.events) == before
