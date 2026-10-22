"""Exercise boundary revision evidence at the actual host/SDK seam."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ThinkingBlock

from docfit.app.prepare_template import (
    _run_unit_boundary_checkpoint,
    _unit_boundary_feedback,
    _validate_unit_boundary_checkpoint,
)
from docfit.template.unit_boundary_journal import read_unit_boundary_journal
from docfit.tools.runtime import ToolFailure
from tests.contract.test_prepare_template_runtime import _backend, _prepared, _unit_checkpoint


def _events(root):
    return [json.loads(p.read_text()) for p in sorted(
        (root / "work/.docfit/unit-boundary-revisions").glob("*/*.json")
    )]


def _client(
    monkeypatch, outputs, prompts, *, interrupted=False, on_query=None, api_failure=False,
):
    class Client:
        def __init__(self, *, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def query(self, prompt):
            if on_query:
                on_query(prompt)
            prompts.append(prompt)
            if interrupted and len(prompts) == 2:
                raise asyncio.CancelledError()

        async def receive_response(self):
            yield AssistantMessage(
                model="test", content=[
                    TextBlock("visible output"), ThinkingBlock("secret-thinking-body", "sig"),
                ],
            )
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1,
                is_error=api_failure, num_turns=1, session_id="test-session",
                terminal_reason="api_error" if api_failure else None,
                structured_output=deepcopy(outputs[len(prompts) - 1]),
                result="private-provider-detail" if api_failure else "visible result",
            )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", Client)


def test_rejected_and_accepted_boundary_rounds_keep_prompts_proposals_reviews_and_diff(
    tmp_path, monkeypatch,
):
    prepared = _prepared(tmp_path)
    accepted = {"status": "complete", "units": _unit_checkpoint(prepared)["units"]}
    rejected = deepcopy(accepted)
    rejected["units"][0]["start_boundary"]["source_entry_id"] = "unknown"
    prompts = []
    def before_send(prompt):
        assert _events(tmp_path)[-1]["data"]["prompt"] == prompt

    def before_review(prepared, proposal):
        response = _events(tmp_path)[-1]
        assert response["kind"] == "response"
        assert response["data"]["structured_output"] == proposal
        return _unit_boundary_feedback(prepared, proposal)

    _client(monkeypatch, [rejected, accepted], prompts, on_query=before_send)
    monkeypatch.setattr("docfit.app.prepare_template._unit_boundary_feedback", before_review)
    checkpoint = asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    events = _events(tmp_path)
    assert [e["kind"] for e in events] == [
        "request", "response", "review", "request", "response", "review", "checkpoint",
    ]
    assert [e["data"]["prompt"] for e in events if e["kind"] == "request"] == prompts
    responses = [e["data"] for e in events if e["kind"] == "response"]
    assert [e["structured_output"] for e in responses] == [rejected, accepted]
    assert all(e["assistant_text"] == ["visible output"] for e in responses)
    assert all(e["result_text"] == "visible result" for e in responses)
    assert "secret-thinking-body" not in json.dumps(events)
    assert events[2]["data"]["feedback"]["blockers"][0]["code"] == "unit_boundary_point_invalid"
    assert events[5]["data"]["feedback"] is None
    assert responses[1]["previous_response_sequence"] == 2
    assert responses[1]["diff"]["units"] == [{
        "index": 0, "before": rejected["units"][0], "after": accepted["units"][0],
    }]
    assert checkpoint["revision_evidence"]["review_event_digest"] == events[5]["event_digest"]
    assert _validate_unit_boundary_checkpoint(prepared, checkpoint) == checkpoint
    history = next((tmp_path / "work/.docfit/unit-boundary-revisions").iterdir())
    assert read_unit_boundary_journal(history, binding=events[0]["binding"]) == events
    (history / "00000002.json").unlink()
    with pytest.raises(ToolFailure, match="history"):
        _validate_unit_boundary_checkpoint(prepared, checkpoint)


def test_boundary_interruption_keeps_rejected_response_and_pending_request(tmp_path, monkeypatch):
    prepared = _prepared(tmp_path)
    checkpoint_path = tmp_path / "work/.docfit/unit-boundary-checkpoint.json"
    checkpoint_path.unlink()
    proposal = {"status": "needs_input", "needs_input": ["Missing school evidence"]}
    prompts = []
    _client(monkeypatch, [proposal], prompts, interrupted=True)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    events = _events(tmp_path)
    assert [e["kind"] for e in events] == ["request", "response", "review", "request", "failed"]
    assert events[1]["data"]["structured_output"] == proposal
    assert events[-2]["data"]["prompt"] == prompts[-1]
    assert not (tmp_path / "work/.docfit/unit-boundary-checkpoint.json").exists()


def test_boundary_host_failure_keeps_proposal_and_failed_review(tmp_path, monkeypatch):
    prepared = _prepared(tmp_path)
    proposal = {"status": "complete", "units": _unit_checkpoint(prepared)["units"]}
    _client(monkeypatch, [proposal], [])

    def fail(*_):
        raise ToolFailure(
            status="error", origin="harness", code="source_state_invalid", message="Bad",
        )

    monkeypatch.setattr("docfit.app.prepare_template._unit_boundary_feedback", fail)
    with pytest.raises(ToolFailure, match="Bad"):
        asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    events = _events(tmp_path)
    assert [e["kind"] for e in events] == ["request", "response", "review_failed", "failed"]
    assert events[1]["data"]["structured_output"] == proposal
    assert events[2]["data"]["failure"]["origin"] == "harness"


@pytest.mark.parametrize("kind", ["request", "response", "review", "checkpoint", "failed"])
def test_journal_write_failure_stops_before_next_action(tmp_path, monkeypatch, kind):
    prepared = _prepared(tmp_path)
    proposal = {"status": "complete", "units": _unit_checkpoint(prepared)["units"]}
    checkpoint = tmp_path / "work/.docfit/unit-boundary-checkpoint.json"
    checkpoint.unlink()
    prompts, reviews = [], []
    _client(monkeypatch, [proposal], prompts)
    from docfit.template import unit_boundary_journal as journal
    write = journal.atomic_write_json

    def fail_write(path, value):
        if value["kind"] == kind:
            raise OSError("Injected evidence write failure")
        write(path, value)

    def review(*args):
        reviews.append(True)
        if kind == "failed":
            raise ToolFailure(status="error", origin="tool", code="broken", message="Broken")
        return _unit_boundary_feedback(*args)

    monkeypatch.setattr(journal, "atomic_write_json", fail_write)
    monkeypatch.setattr("docfit.app.prepare_template._unit_boundary_feedback", review)
    with pytest.raises(ToolFailure) as caught:
        asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    assert caught.value.code == "unit_boundary_journal_invalid"
    assert caught.value.origin == "harness" and not caught.value.retryable
    assert len(prompts) == (0 if kind == "request" else 1)
    assert len(reviews) == (0 if kind in {"request", "response"} else 1)
    assert not checkpoint.exists()
    archive = next((tmp_path / "work/.docfit/unit-boundary-executions").glob("*.json"))
    evidence = json.loads(archive.read_text())
    assert evidence["failure"]["code"] == "unit_boundary_journal_invalid"
    if kind == "failed":
        assert evidence["original_failure"]["code"] == "broken"


def test_separate_executions_do_not_overwrite_boundary_history(tmp_path, monkeypatch):
    prepared = _prepared(tmp_path)
    proposal = {"status": "complete", "units": _unit_checkpoint(prepared)["units"]}
    roots = tmp_path / "work/.docfit/unit-boundary-revisions"
    _client(monkeypatch, [proposal], [])
    first = asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    original = {str(p): p.read_bytes() for p in roots.rglob("*.json")}
    _client(monkeypatch, [proposal], [])
    second = asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    assert first["revision_evidence"]["run_id"] != second["revision_evidence"]["run_id"]
    assert original == {p: Path(p).read_bytes() for p in original}
    assert len(list(roots.iterdir())) == 2
    assert _validate_unit_boundary_checkpoint(prepared, first) == first
    assert _validate_unit_boundary_checkpoint(prepared, second) == second


def test_api_failure_retains_metadata_without_provider_content(tmp_path, monkeypatch):
    prepared = _prepared(tmp_path)
    _client(monkeypatch, [{"error": "private-provider-detail"}], [], api_failure=True)
    with pytest.raises(ToolFailure) as caught:
        asyncio.run(_run_unit_boundary_checkpoint(prepared, _backend(), tmp_path / "cfg"))
    assert caught.value.code == "template_agent_api_error"
    events = _events(tmp_path)
    assert [e["kind"] for e in events] == ["request", "response", "failed"]
    response = events[1]["data"]
    assert response["structured_output"] is None
    assert response["result_text"] is None and response["assistant_text"] == []
    assert response["sdk_metadata"]["terminal_reason"] == "api_error"
    assert "private-provider-detail" not in json.dumps(events)
    assert "secret-thinking-body" not in json.dumps(events)
