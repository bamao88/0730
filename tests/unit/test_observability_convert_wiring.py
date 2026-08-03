from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
)

from docfit.app.convert import _run_backend
from docfit.app.settings import AgentBackend
from docfit.observability.correlation import (
    AdapterHealthReceipt,
    correlate_observation_run,
)
from docfit.observability.events import ObservationEvent, SanitizationReceipt
from docfit.observability.runtime import NullObservationRecorder, ObservationRun


class RecordingRecorder(NullObservationRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[ObservationEvent] = []

    @property
    def enabled(self) -> bool:
        return True

    def record(self, event: ObservationEvent) -> SanitizationReceipt:
        self.events.append(event)
        return SanitizationReceipt("accepted", "observer_event_accepted", 0.0)


def test_backend_wires_sdk_messages_and_hooks_only_after_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_options: list[Any] = []

    class FakeClient:
        def __init__(self, *, options: Any) -> None:
            captured_options.append(options)

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            assert prompt == "PRIVATE_PROMPT_CANARY"

        async def receive_response(self) -> Any:
            yield AssistantMessage(
                content=[
                    ToolUseBlock(
                        "tool-1",
                        "Skill",
                        {
                            "skill": "convert-thesis",
                            "raw": "PRIVATE_BODY_CANARY",
                        },
                    ),
                    ToolResultBlock("tool-1", "PRIVATE_BODY_CANARY", False),
                ],
                model="synthetic-model",
                message_id="message-1",
                session_id="session-1",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="session-1",
                result="PRIVATE_BODY_CANARY",
                structured_output={},
                uuid="result-1",
            )

    monkeypatch.setattr("docfit.app.convert.ClaudeSDKClient", FakeClient)
    recorder = RecordingRecorder()
    observation_run = ObservationRun(
        "run_0123456789abcdef0123456789abcdef",
        recorder,
    )
    backend = AgentBackend(
        name="kimi",
        base_url="https://example.invalid",
        model="synthetic-model",
        credential_variable="DOCFIT_KIMI_API_KEY",
        api_key="secret",
    )
    prepared = SimpleNamespace(task_root=tmp_path)
    config = tmp_path / "config"
    config.mkdir()

    execution = asyncio.run(
        _run_backend(
            "PRIVATE_PROMPT_CANARY",
            prepared,  # type: ignore[arg-type]
            backend,
            config,
            observation_run,
        )
    )

    assert execution.session_id == "session-1"
    assert [event.kind for event in recorder.events] == [
        "assistant_message",
        "skill_use",
        "tool_result",
        "sdk_result",
    ]
    serialized = json.dumps([asdict(event) for event in recorder.events])
    assert "PRIVATE_PROMPT_CANARY" not in serialized
    assert "PRIVATE_BODY_CANARY" not in serialized
    options = captured_options[0]
    assert options.env["CLAUDE_CONFIG_DIR"] == str(config)
    assert options.hooks is not None
    assert set(options.hooks) == {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SubagentStart",
        "SubagentStop",
    }
    correlation = correlate_observation_run(
        observation_run.run_id,
        recorder.events,
        adapter_receipts=(
            AdapterHealthReceipt("app", "available"),
            AdapterHealthReceipt("sdk", "available"),
            AdapterHealthReceipt("permission", "available"),
            AdapterHealthReceipt("tool", "available"),
            AdapterHealthReceipt("report", "available"),
        ),
    )
    assert correlation.dimensions.observation.state == "degraded"
    assert correlation.dimensions.run_result == "unknown"
    assert correlation.tools[0].tool_use_id == "tool-1"
    assert correlation.tools[0].association_status == "verified"
    assert correlation.metrics.agent_turns.value == 1
