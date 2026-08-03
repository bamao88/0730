from __future__ import annotations

from dataclasses import fields
from typing import get_type_hints

from docfit.observability.events import (
    ALLOWED_OBSERVATION_ATTRIBUTE_KEYS,
    ObservationEvent,
    SanitizedEventSink,
)
from docfit.observability.privacy import (
    project_app_event,
    project_assistant_message,
    project_permission_decision,
    project_report_event,
    project_result_message,
    project_subagent_hook,
    project_tool_hook,
    project_tool_result_block,
    project_tool_use_block,
    project_user_question,
)
from docfit.observability.sdk_sources import FORBIDDEN_PERSISTED_SDK_FIELDS


def test_safe_event_schema_has_no_raw_payload_escape_hatch() -> None:
    field_names = {field.name for field in fields(ObservationEvent)}

    assert (FORBIDDEN_PERSISTED_SDK_FIELDS - {"error"}).isdisjoint(field_names)
    assert {
        "payload",
        "raw",
        "body",
        "text",
        "content",
        "path",
        "bytes",
        "exception",
    }.isdisjoint(field_names)
    assert {
        "prompt",
        "tool_input",
        "tool_response",
        "result",
        "body",
        "text",
        "content",
        "path",
        "cwd",
        "transcript_path",
        "agent_transcript_path",
        "raw",
        "bytes",
        "exception",
    }.isdisjoint(ALLOWED_OBSERVATION_ATTRIBUTE_KEYS)


def test_future_sink_accepts_only_sanitized_event_type() -> None:
    hints = get_type_hints(SanitizedEventSink.record)

    assert hints["event"] is ObservationEvent


def test_every_approved_source_family_has_a_dedicated_projector() -> None:
    assert all(
        callable(projector)
        for projector in (
            project_app_event,
            project_assistant_message,
            project_tool_use_block,
            project_tool_result_block,
            project_result_message,
            project_tool_hook,
            project_subagent_hook,
            project_permission_decision,
            project_user_question,
            project_report_event,
        )
    )
