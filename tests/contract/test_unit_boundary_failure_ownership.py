"""Host state faults must not become boundary revisions or model failovers."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from claude_agent_sdk.types import ResultMessage

from docfit.app.prepare_template import run_template_agent, run_unit_boundary_checkpoint
from docfit.template.unit_source import INITIAL_INVENTORY_PATH
from docfit.tools.runtime import ToolFailure, atomic_write_json
from docfit.tools.service import DocFitToolService
from tests.contract.test_prepare_template_runtime import _backend, _prepared, _unit_checkpoint


def _corrupt_mapping(root):
    path = root / INITIAL_INVENTORY_PATH
    initial = json.loads(path.read_text())
    initial["mapping_digest"] = "0" * 64
    atomic_write_json(path, initial)


def test_corrupt_source_mapping_retains_host_failure_at_service_boundary(tmp_path):
    prepared = _prepared(tmp_path)
    units = _unit_checkpoint(prepared)["units"]
    service = DocFitToolService(task_root=tmp_path)
    args = {"check": "unit_coverage", "payload": {"units": units}}
    assert service.check(args)["status"] == "ok"
    _corrupt_mapping(tmp_path)

    with pytest.raises(ToolFailure) as caught:
        service.check(args)

    assert caught.value.code == "initial_source_inventory_invalid"
    assert caught.value.origin == "harness"
    assert caught.value.retryable is False


@pytest.mark.parametrize("run", [run_unit_boundary_checkpoint, run_template_agent])
def test_mapping_fault_after_response_stops_without_revision_or_backend_switch(
    tmp_path, monkeypatch, run,
):
    prepared = _prepared(tmp_path)
    proposal = {"status": "complete", "units": _unit_checkpoint(prepared)["units"]}
    original = deepcopy(proposal)
    queries = []
    clients = []

    class Client:
        def __init__(self, *, options):
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def query(self, prompt):
            queries.append(prompt)

        async def receive_response(self):
            # Fail after prompt construction, at the actual host feedback seam.
            _corrupt_mapping(tmp_path)
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1,
                is_error=False, num_turns=1, session_id="unit-test",
                result="{}", structured_output=proposal,
            )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", Client)
    monkeypatch.setattr(
        "docfit.app.prepare_template.iter_agent_backends",
        lambda: iter((_backend(), replace(_backend(), name="second"))),
    )
    with pytest.raises(ToolFailure) as caught:
        asyncio.run(run(prepared))

    assert caught.value.code == "initial_source_inventory_invalid"
    assert caught.value.origin == "harness"
    assert len(queries) == len(clients) == 1
    assert proposal == original
    executions = list((tmp_path / "work/.docfit/unit-boundary-executions").glob("*.json"))
    assert len(executions) == 1
    record = json.loads(executions[0].read_text())
    assert record["sdk_query_count"] == 1
    assert record["harness_feedback_attempts"] == 0
    assert record["failure"]["origin"] == "harness"
    assert record["failure"]["code"] == "initial_source_inventory_invalid"
    assert record["timing_events"][-1]["status"] == "failed"
    assert not (tmp_path / "output/final-template.docx").exists()


@pytest.mark.parametrize("run,seam", [
    (run_unit_boundary_checkpoint, "_run_unit_boundary_checkpoint"),
    (run_template_agent, "_run_backend"),
])
@pytest.mark.parametrize("kind", ["timeout", "api_auth", "invalid_response", "tool", "budget"])
def test_backend_switch_is_limited_to_backend_failures(tmp_path, monkeypatch, run, seam, kind):
    prepared = _prepared(tmp_path)
    failures = {
        "timeout": TimeoutError(),
        "api_auth": ToolFailure(status="error", origin="environment",
                                code="template_agent_api_error", message="HTTP 401"),
        "invalid_response": ToolFailure(status="error", origin="agent",
                                        code="unit_checkpoint_result_invalid",
                                        message="Invalid model output", retryable=True),
        "tool": ToolFailure(status="error", origin="tool", code="operation_unsupported",
                            message="Unsupported structure", retryable=True),
        "budget": ToolFailure(status="needs_input", origin="harness",
                              code="unit_boundary_checkpoint_failed",
                              message="Semantic revision budget exhausted", retryable=True),
    }
    failure = failures[kind]
    calls = []
    accepted = object()

    async def attempt(_prepared, backend, _config, **kwargs):
        calls.append(backend.name)
        if len(calls) == 1:
            raise failure
        return accepted

    monkeypatch.setattr(f"docfit.app.prepare_template.{seam}", attempt)
    monkeypatch.setattr(
        "docfit.app.prepare_template.iter_agent_backends",
        lambda: iter((_backend(), replace(_backend(), name="second"))),
    )
    if kind in {"tool", "budget"}:
        with pytest.raises(ToolFailure) as caught:
            asyncio.run(run(prepared))
        assert caught.value is failure
        assert calls == ["test"]
    else:
        assert asyncio.run(run(prepared)) is accepted
        assert calls == ["test", "second"]
