from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from docfit.observability.events import (
    PROJECTOR_DEADLINE_MS,
    ProjectionContext,
    ProjectionResult,
    observation_event_bytes,
)
from docfit.observability.privacy import (
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

RUN_ID = "run_0123456789abcdef0123456789abcdef"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
PRIVATE_CANARIES = (
    "PRIVATE_PROMPT_CANARY",
    "PRIVATE_BODY_CANARY",
    "PRIVATE_ERROR_CANARY",
    "PRIVATE_PATH_CANARY",
    "PRIVATE_IMAGE_CANARY",
    "PRIVATE_ANSWER_CANARY",
    "PRIVATE_CREDENTIAL_CANARY",
)


def _context(sequence: int = 1) -> ProjectionContext:
    return ProjectionContext(
        run_id=RUN_ID,
        source_sequence=sequence,
        observed_at=datetime.now(UTC).isoformat(),
        monotonic_offset_ms=float(sequence),
    )


def _event_json(result: ProjectionResult) -> str:
    assert result.event is not None, result.receipt
    serialized = json.dumps(asdict(result.event), ensure_ascii=False, sort_keys=True)
    assert all(canary not in serialized for canary in PRIVATE_CANARIES)
    assert "/private/" not in serialized
    return serialized


def _attributes(result: ProjectionResult) -> dict[str, object]:
    assert result.event is not None
    return {item.key: item.value for item in result.event.attributes}


def test_sdk_message_projectors_never_copy_text_thinking_result_or_errors() -> None:
    assistant = AssistantMessage(
        content=[
            TextBlock("PRIVATE_BODY_CANARY"),
            ThinkingBlock("PRIVATE_PROMPT_CANARY", "PRIVATE_BODY_CANARY"),
        ],
        model="claude-synthetic",
        parent_tool_use_id=None,
        error=None,
        usage={
            "input_tokens": 12,
            "output_tokens": 5,
            "unknown": "PRIVATE_BODY_CANARY",
        },
        message_id="message-1",
        session_id="session-1",
    )
    assistant_result = project_assistant_message(assistant, _context())
    serialized = _event_json(assistant_result)
    assert "input_tokens" in serialized
    assert "block_count" in serialized

    final = ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=2,
        session_id="session-1",
        total_cost_usd=0.01,
        usage={"input_tokens": 12, "output_tokens": 5},
        result="PRIVATE_BODY_CANARY",
        structured_output={"body": "PRIVATE_PROMPT_CANARY"},
        errors=["PRIVATE_ERROR_CANARY"],
        uuid="result-1",
        terminal_reason="success",
    )
    final_result = project_result_message(final, _context(2))
    serialized = _event_json(final_result)
    assert "num_turns" in serialized
    assert "total_cost_usd" in serialized


def test_tool_result_block_ignores_content_even_when_it_looks_structured() -> None:
    block = ToolResultBlock(
        "tool-1",
        content='{"result":"PRIVATE_BODY_CANARY","path":"/private/task"}',
        is_error=True,
    )

    result = project_tool_result_block(block, _context())

    serialized = _event_json(result)
    assert result.event is not None and result.event.status == "error"
    assert "content" not in serialized


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected_keys"),
    [
        (
            "mcp__docfit__docx_inspect",
            {
                "task_root": "/private/PRIVATE_PATH_CANARY",
                "input_docx": "PRIVATE_BODY_CANARY.docx",
                "focus": ["structure", "styles"],
                "unknown": "PRIVATE_BODY_CANARY",
            },
            {"focus", "focus_count", "side_effect_possible"},
        ),
        (
            "mcp__docfit__docx_edit",
            {
                "input_docx": "/private/PRIVATE_PATH_CANARY.docx",
                "output_docx": "/private/output.docx",
                "operations": [
                    {
                        "action": "replace_text",
                        "target_ref": {
                            "document_sha256": HASH_A,
                            "object_id": "obj-" + ("1" * 24),
                        },
                        "expected_text": "PRIVATE_BODY_CANARY",
                        "replacement": "PRIVATE_PROMPT_CANARY",
                    },
                    {"action": "apply_style", "style": "PRIVATE_BODY_CANARY"},
                ],
            },
            {"operation_count", "operation_types", "side_effect_possible"},
        ),
        (
            "mcp__docfit__docx_render",
            {
                "input_docx": "/private/PRIVATE_PATH_CANARY.docx",
                "overview": True,
            },
            {"overview", "side_effect_possible"},
        ),
        (
            "mcp__docfit__docx_visual_review",
            {
                "render_ref": "/private/PRIVATE_PATH_CANARY",
                "mode": "pages",
                "pages": [1, 2],
                "regions": [],
            },
            {"mode", "page_count", "region_count", "side_effect_possible"},
        ),
        (
            "mcp__docfit__docx_validate",
            {
                "source_docx": "/private/PRIVATE_PATH_CANARY.docx",
                "final_docx": "/private/final.docx",
                "source_sha256": HASH_A,
                "task_rule_evidence": [{"text": "PRIVATE_BODY_CANARY"}],
                "visual_review": "/private/visual.json",
                "required_visual_coverage": "all_final_pages",
            },
            {
                "task_rule_count",
                "required_visual_coverage",
                "side_effect_possible",
            },
        ),
    ],
)
def test_each_docfit_tool_input_uses_a_field_allowlist(
    tool_name: str,
    tool_input: dict[str, object],
    expected_keys: set[str],
) -> None:
    block = ToolUseBlock("tool-1", tool_name, tool_input)

    result = project_tool_use_block(block, _context())

    _event_json(result)
    assert set(_attributes(result)) == expected_keys


def test_skill_agent_and_user_question_inputs_keep_counts_not_prompts() -> None:
    skill = project_tool_use_block(
        ToolUseBlock("skill-1", "Skill", {"skill": "convert-thesis"}),
        _context(),
    )
    assert _attributes(skill) == {"skill_name": "convert-thesis"}

    agent = project_tool_use_block(
        ToolUseBlock(
            "agent-1",
            "Agent",
            {
                "subagent_type": "docfit-unit-analyst",
                "prompt": "PRIVATE_PROMPT_CANARY",
                "description": "PRIVATE_BODY_CANARY",
            },
        ),
        _context(2),
    )
    _event_json(agent)
    assert set(_attributes(agent)) == {"subagent_type", "payload_bytes"}

    question_input = {
        "questions": [
            {
                "question": "PRIVATE_PROMPT_CANARY",
                "header": "PRIVATE_BODY_CANARY",
                "options": [
                    {"label": "PRIVATE_BODY_CANARY", "description": "PRIVATE_BODY_CANARY"},
                    {"label": "safe", "description": "PRIVATE_BODY_CANARY"},
                ],
            }
        ],
        "answers": {"PRIVATE_PROMPT_CANARY": "PRIVATE_ANSWER_CANARY"},
    }
    question = project_user_question(
        _context(3),
        tool_use_id="question-1",
        tool_input=question_input,
        answered=True,
        duration_ms=5,
    )
    _event_json(question)
    assert _attributes(question) == {
        "question_count": 1,
        "option_count": 2,
        "answered": True,
    }


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    (
        (
            "Write",
            {
                "file_path": "/private/PRIVATE_PATH_CANARY.md",
                "content": "PRIVATE_BODY_CANARY",
            },
        ),
        ("Bash", {"command": "echo PRIVATE_BODY_CANARY > /private/PRIVATE_PATH_CANARY"}),
    ),
)
def test_trusted_basic_tool_lifecycle_is_observed_without_arguments(
    tool_name: str,
    tool_input: dict[str, str],
) -> None:
    block = project_tool_use_block(
        ToolUseBlock("trusted-1", tool_name, tool_input),
        _context(),
    )
    hook = project_tool_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "transcript_path": "/private/PRIVATE_PATH_CANARY",
            "cwd": "/private/PRIVATE_PATH_CANARY",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": "trusted-1",
        },
        _context(2),
    )

    _event_json(block)
    _event_json(hook)
    assert _attributes(block) == {}
    assert _attributes(hook) == {}


def _post_hook(tool_name: str, response: object) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "session-1",
        "transcript_path": "/private/PRIVATE_PATH_CANARY",
        "cwd": "/private/PRIVATE_PATH_CANARY",
        "tool_name": tool_name,
        "tool_input": {"raw": "PRIVATE_PROMPT_CANARY"},
        "tool_response": response,
        "tool_use_id": "tool-1",
        "agent_id": "agent-1",
        "agent_type": "docfit-unit-analyst",
    }


@pytest.mark.parametrize(
    ("tool_name", "structured", "expected_keys"),
    [
        (
            "mcp__docfit__docx_inspect",
            {
                "status": "ok",
                "checks": [{"body": "PRIVATE_BODY_CANARY"}],
                "warnings": [{"message": "PRIVATE_BODY_CANARY"}],
                "document": {"sha256": HASH_A, "title": "PRIVATE_BODY_CANARY"},
                "objects": [
                    {
                        "text": "PRIVATE_BODY_CANARY",
                        "object_ref": {
                            "document_sha256": HASH_A,
                            "object_id": "obj-" + ("1" * 24),
                        },
                    }
                ],
                "risks": [{"text": "PRIVATE_BODY_CANARY"}],
            },
            {
                "warning_count",
                "check_count",
                "object_count",
                "risk_count",
                "object_ref_count",
                "side_effect_possible",
                "artifact_published",
            },
        ),
        (
            "mcp__docfit__docx_edit",
            {
                "status": "ok",
                "committed": True,
                "input_sha256": HASH_A,
                "output_sha256": HASH_B,
                "output_docx": "/private/PRIVATE_PATH_CANARY.docx",
                "operations": [
                    {"action": "replace_text", "text": "PRIVATE_BODY_CANARY"}
                ],
                "warnings": [],
                "checks": [],
            },
            {
                "committed",
                "warning_count",
                "check_count",
                "operation_count",
                "operation_types",
                "side_effect_possible",
                "artifact_published",
            },
        ),
        (
            "mcp__docfit__docx_render",
            {
                "schema_version": 2,
                "status": "ok",
                "cache_hit": False,
                "checks": [],
                "warnings": [],
                "render_ref": "render:v2:" + HASH_B,
                "document_sha256": HASH_A,
                "page_count": 2,
                "fidelity": "approximate",
                "renderer": {
                    "name": "libreoffice",
                    "version": "libreoffice-25.2.3.2",
                    "raw": "PRIVATE_ERROR_CANARY",
                },
            },
            {
                "warning_count",
                "check_count",
                "renderer",
                "renderer_version",
                "cache_hit",
                "page_count",
                "pdf_available",
                "side_effect_possible",
                "artifact_published",
            },
        ),
        (
            "mcp__docfit__docx_visual_review",
            {
                "status": "ok",
                "checks": [],
                "warnings": [],
                "document_sha256": HASH_A,
                "render_ref": "render:v2:" + HASH_B,
                "mode": "pages",
                "evidence": [
                    {
                        "evidence_ref": "visual:v2:" + HASH_C,
                        "page": 1,
                        "observation": "PRIVATE_BODY_CANARY",
                    }
                ],
            },
            {
                "warning_count",
                "check_count",
                "mode",
                "page_count",
                "evidence_count",
                "image_count",
                "image_bytes",
                "side_effect_possible",
                "artifact_published",
            },
        ),
        (
            "mcp__docfit__docx_validate",
            {
                "status": "ok",
                "checks": [{"evidence": "PRIVATE_BODY_CANARY"}],
                "warnings": [{"message": "PRIVATE_BODY_CANARY"}],
                "source_sha256": HASH_A,
                "final_sha256": HASH_B,
                "summary": {"errors": 0, "issues": 1, "warnings": 2},
            },
            {
                "warning_count",
                "check_count",
                "errors",
                "issues",
                "warnings",
                "side_effect_possible",
                "artifact_published",
            },
        ),
    ],
)
def test_each_docfit_tool_result_uses_a_field_allowlist(
    tool_name: str,
    structured: dict[str, object],
    expected_keys: set[str],
) -> None:
    response: dict[str, object] = {
        "structuredContent": structured,
        "content": [
            {"type": "text", "text": "PRIVATE_BODY_CANARY"},
        ],
    }
    if tool_name.endswith("visual_review"):
        response["content"] = [
            {"type": "text", "text": "PRIVATE_BODY_CANARY"},
            {"type": "image", "data": "PRIVATE_IMAGE_CANARY", "mimeType": "image/png"},
        ]

    result = project_tool_hook(_post_hook(tool_name, response), _context())

    _event_json(result)
    assert set(_attributes(result)) == expected_keys


def test_hook_failure_and_subagent_lifecycle_drop_paths_and_raw_errors() -> None:
    failure = project_tool_hook(
        {
            **_post_hook("mcp__docfit__docx_edit", {}),
            "hook_event_name": "PostToolUseFailure",
            "error": "PRIVATE_ERROR_CANARY /private/PRIVATE_PATH_CANARY",
            "is_interrupt": True,
        },
        _context(),
    )
    serialized = _event_json(failure)
    assert failure.event is not None
    assert failure.event.error is not None
    assert failure.event.error.code == "sdk_tool_failure"
    assert "is_interrupt" not in serialized

    for sequence, phase in enumerate(("SubagentStart", "SubagentStop"), start=2):
        lifecycle = project_subagent_hook(
            {
                "hook_event_name": phase,
                "session_id": "session-1",
                "transcript_path": "/private/PRIVATE_PATH_CANARY",
                "agent_transcript_path": "/private/PRIVATE_PATH_CANARY",
                "cwd": "/private/PRIVATE_PATH_CANARY",
                "agent_id": "agent-1",
                "agent_type": "docfit-unit-analyst",
                "stop_hook_active": False,
            },
            _context(sequence),
        )
        _event_json(lifecycle)


def test_structured_tool_failure_keeps_only_safe_code_and_committed_state() -> None:
    response = {
        "structuredContent": {
            "status": "needs_input",
            "committed": False,
            "checks": [],
            "warnings": [],
            "failure": {
                "origin": "postcondition",
                "code": "postcondition_failed",
                "retryable": False,
                "message": "PRIVATE_ERROR_CANARY /private/PRIVATE_PATH_CANARY",
                "suggested_actions": ["PRIVATE_BODY_CANARY"],
            },
        },
        "content": [{"type": "text", "text": "PRIVATE_BODY_CANARY"}],
    }

    result = project_tool_hook(
        _post_hook("mcp__docfit__docx_edit", response),
        _context(),
    )

    _event_json(result)
    assert result.event is not None
    assert result.event.status == "needs_input"
    assert result.event.error is not None
    assert result.event.error.code == "postcondition_failed"
    assert result.event.error.origin == "postcondition"
    assert _attributes(result)["committed"] is False
    assert _attributes(result)["artifact_published"] is False


def test_permission_projector_keeps_decision_and_counts_only() -> None:
    result = project_permission_decision(
        _context(),
        tool_name="AskUserQuestion",
        decision="allow",
        tool_use_id="question-1",
        agent_id="agent-1",
        reason_code="ask_user_answered",
        question_count=1,
        option_count=3,
        answered=True,
        duration_ms=10,
    )

    _event_json(result)
    assert result.event is not None
    assert result.event.status == "allow"
    assert _attributes(result) == {
        "reason_code": "ask_user_answered",
        "question_count": 1,
        "option_count": 3,
        "answered": True,
    }


def test_report_projector_reuses_allowlisted_v2_projection() -> None:
    report = {
        "schema_version": 2,
        "status": "COMPLETED",
        "output_directory": "/private/PRIVATE_PATH_CANARY",
        "final_docx": "/private/PRIVATE_PATH_CANARY.docx",
        "source_sha256": HASH_A,
        "template_sha256": HASH_B,
        "requirements_sha256": HASH_C,
        "final_sha256": HASH_D,
        "knowledge_version": "v1",
        "knowledge_digest": f"sha256:{HASH_D}",
        "backend": "synthetic-backend",
        "session_id": "session-1",
        "tool_uses": ["PRIVATE_BODY_CANARY"],
        "warnings": ["PRIVATE_BODY_CANARY"],
        "detail": "PRIVATE_BODY_CANARY",
        "run_id": RUN_ID,
        "task_ref": "task_fedcba9876543210fedcba9876543210",
        "observation_coverage": {
            "state": "degraded",
            "events_persisted": 4,
            "events_dropped": 1,
            "missing_sources": ["post_tool_use"],
            "last_observed_at": datetime.now(UTC).isoformat(),
            "failure_codes": ["observer_queue_full"],
        },
        "sdk_transcript": {
            "status": "cleaned",
            "residual_count": 0,
            "oldest_age_bucket": None,
            "failure_codes": [],
        },
    }

    result = project_report_event(report, _context())

    _event_json(result)
    assert result.event is not None
    assert result.event.status == "completed"
    assert _attributes(result)["events_persisted"] == 4
    assert len(result.event.evidence_refs) == 4


def test_unknown_tool_and_unknown_hook_type_are_dropped_without_raw_fallback() -> None:
    tool = project_tool_use_block(
        ToolUseBlock("tool-1", "UnknownTool", {"body": "PRIVATE_BODY_CANARY"}),
        _context(),
    )
    hook = project_tool_hook(
        {
            "hook_event_name": "UnknownHook",
            "error": "PRIVATE_ERROR_CANARY",
            "transcript_path": "/private/PRIVATE_PATH_CANARY",
        },
        _context(2),
    )

    assert tool.event is None
    assert hook.event is None
    assert tool.receipt.reason_code == "observer_source_type_unsupported"
    assert hook.receipt.reason_code == "observer_source_type_unsupported"
    assert all(canary not in str((tool, hook)) for canary in PRIVATE_CANARIES)


def test_maximum_legal_tool_event_meets_projector_latency_and_drop_contract() -> None:
    operations = [
        {
            "action": "replace_text",
            "target_ref": {
                "document_sha256": HASH_A,
                "object_id": f"obj-{index:024x}",
            },
            "expected_text": "PRIVATE_BODY_CANARY" * 100,
            "replacement": "PRIVATE_CREDENTIAL_CANARY" * 100,
        }
        for index in range(128)
    ]
    block = ToolUseBlock(
        "tool-max",
        "mcp__docfit__docx_edit",
        {"operations": operations},
    )
    samples: list[float] = []
    event_size = 0
    for sequence in range(1, 1001):
        result = project_tool_use_block(block, _context(sequence))
        samples.append(result.receipt.elapsed_ms)
        if result.event is None:
            assert result.receipt.reason_code == "observer_projector_deadline"
            assert result.receipt.elapsed_ms >= PROJECTOR_DEADLINE_MS
            continue
        event_size = observation_event_bytes(result.event)

    ordered = sorted(samples)
    assert 32 * 1024 < event_size < 64 * 1024
    assert ordered[949] <= 2.0
    assert ordered[989] <= 5.0


def test_projectors_write_no_logs_or_temporary_files(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = project_tool_use_block(
        ToolUseBlock(
            "tool-1",
            "Agent",
            {
                "subagent_type": "docfit-unit-analyst",
                "prompt": "PRIVATE_PROMPT_CANARY",
                "credential": "PRIVATE_CREDENTIAL_CANARY",
            },
        ),
        _context(),
    )

    _event_json(result)
    assert not caplog.records
    assert not tuple(tmp_path.iterdir())
