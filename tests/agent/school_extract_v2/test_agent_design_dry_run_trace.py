from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import project_root
from docfit.app.prepare_template import (
    PreparedTemplateTask,
    PrepareTemplateRequest,
    _ensure_post_unit_inventory,
    _run_backend,
    prepare_template_task,
)
from docfit.app.settings import AgentBackend
from docfit.template.unit_source import load_initial_inventory
from tests.support.source_identity import persist_source_identity, source_partition

ROOT = project_root()
TEMPLATE = ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
REGISTRY = ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.5.yaml"


def _request(tmp_path: Path) -> PrepareTemplateRequest:
    return PrepareTemplateRequest(
        school_template=TEMPLATE,
        output_directory=tmp_path / "prepared-task",
        field_registry=REGISTRY,
    )


def _backend() -> AgentBackend:
    return AgentBackend(
        name="test",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def _fixed_name_judgment(source_entry_id: str) -> dict[str, object]:
    return {
        "source_entry_id": source_entry_id,
        "parts": [{"text": "姓名：", "role": "fixed_label"}],
    }


def _name_slot_judgment(
    source_entry_id: str,
    field_id: str = "author.name.zh",
) -> dict[str, object]:
    return {
        "source_entry_id": source_entry_id,
        "parts": [{"text": "【姓名】", "role": "fill_slot", "field_id": field_id}],
    }


def _complete_name_judgments(
    fixed_source_entry_id: str,
    slot_source_entry_id: str,
    *,
    slot_field_id: str = "author.name.zh",
) -> list[dict[str, object]]:
    return [
        _fixed_name_judgment(fixed_source_entry_id),
        _name_slot_judgment(slot_source_entry_id, slot_field_id),
    ]


def _unit_checkpoint(prepared: PreparedTemplateTask) -> dict[str, object]:
    initial = load_initial_inventory(prepared.task_root, prepared.template_sha256)
    inventory = {
        "document_sha256": prepared.template_sha256,
        "canonical_source_inventory": initial["canonical_source_inventory"],
    }
    proof = source_partition(inventory)
    persist_source_identity(prepared.task_root, inventory, objects=initial["objects"])
    return proof


def _name_source_entry_ids(prepared: PreparedTemplateTask) -> tuple[str, str]:
    inventory = _ensure_post_unit_inventory(prepared, _unit_checkpoint(prepared))
    entries = inventory.get("source_entries")
    assert isinstance(entries, list)
    by_text = {
        str(entry["text"]): str(entry["source_entry_id"])
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("text"), str)
        and isinstance(entry.get("source_entry_id"), str)
    }
    return by_text["姓名："], by_text["【姓名】"]


def _feedback(source_entry_id: str) -> dict[str, object]:
    return {
        "status": "needs_input",
        "feedback": {
            "type": "semantic_completeness",
            "mechanical": True,
            "semantic_authority": False,
            "agent_action": "repair semantic scope only",
        },
        "blockers": [
            {
                "code": "missing_target",
                "field": "semantic_judgments",
                "source_entry_id": source_entry_id,
                "evidence_focus": "unit_evidence_packet",
            }
        ],
        "failure": {
            "suggested_actions": [
                "call docfit_evidence with focus=unit_evidence_packet",
                "return full structured result again",
            ]
        },
    }


def test_scripted_sdk_run_routes_feedback_to_a_fresh_scoped_batch_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backend = _backend()
    config = tmp_path / "config"
    config.mkdir()
    queries: list[str] = []
    client_count = 0
    fixed_source_entry_id, slot_source_entry_id = _name_source_entry_ids(prepared)
    feedbacks: list[dict[str, object] | None] = [
        _feedback(slot_source_entry_id),
        None,
    ]

    class ScriptedClient:
        def __init__(self, *, options: object) -> None:
            nonlocal client_count
            client_count += 1
            self.options = options

        async def __aenter__(self) -> ScriptedClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            call_index = len(queries)
            yield AssistantMessage(
                content=[
                    ToolUseBlock("skill-1", "Skill", {"skill": "docfit-school-extract"}),
                    ToolUseBlock(
                        "evidence-1",
                        "mcp__docfit__docfit_evidence",
                        {
                            "schema_version": "docfit_evidence_input_v1",
                            "focus": "unit_evidence_packet",
                            "unit_id": "u-all",
                        },
                    ),
                ],
                model="synthetic-model",
                message_id=f"message-{call_index}",
                session_id="session-design-dry-run",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=call_index,
                session_id="session-design-dry-run",
                result="{}",
                structured_output={
                    "status": "complete",
                    "summary": "synthetic completion",
                    "semantic_judgments": (
                        _complete_name_judgments(
                            fixed_source_entry_id,
                            slot_source_entry_id,
                        )
                        if call_index == 1
                        else [_name_slot_judgment(slot_source_entry_id)]
                    ),
                },
                uuid=f"result-{call_index}",
            )

    def fake_feedback(
        _prepared: PreparedTemplateTask,
        _structured_output: dict[str, object],
    ) -> dict[str, object] | None:
        return feedbacks.pop(0)

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", ScriptedClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "ok", "failure": None},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        fake_feedback,
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )

    execution = asyncio.run(
        _run_backend(
            prepared,
            backend,
            config,
            existing_unit_boundary_checkpoint=_unit_checkpoint(prepared),
        )
    )

    assert client_count == 2
    assert execution.session_id == "session-design-dry-run"
    assert execution.sdk_query_count == 2
    assert execution.harness_feedback_attempts == 1
    assert execution.semantic_feedback_attempts == 1
    assert queries[0].startswith("DocFit bounded post-unit semantic batch.")
    assert queries[1].startswith("DocFit bounded post-unit semantic batch.")
    assert "Harness candidate feedback:" in queries[1]
    assert "Harness revision scope" in queries[1]
    assert "semantic_authority" in queries[1]
    assert "unit_evidence_packet" in queries[1]
    assert execution.skills_loaded == ("docfit-school-extract",)
    assert set(execution.tool_uses) == {
        "Skill",
        "mcp__docfit__docfit_evidence",
    }
    assert [event["operation"] for event in execution.timing_events] == [
        "sdk_query",
        "sdk_query",
    ]
    sdk_query_events = [
        event for event in execution.timing_events if event["operation"] == "sdk_query"
    ]
    assert [event["stage_query_index"] for event in sdk_query_events] == [1, 2]
    assert all(isinstance(event["duration_ms"], int) for event in execution.timing_events)
    assert sdk_query_events[0]["message_count"] == 2
    assert sdk_query_events[0]["tool_use_count"] == 2


def test_scripted_sdk_run_repairs_scoped_semantic_feedback_with_fresh_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backend = _backend()
    config = tmp_path / "config"
    config.mkdir()
    queries: list[str] = []
    fixed_source_entry_id, slot_source_entry_id = _name_source_entry_ids(prepared)
    feedbacks: list[dict[str, object] | None] = [
        {
            "status": "needs_input",
            "feedback": {
                "type": "semantic_completeness",
                "mechanical": True,
                "semantic_authority": False,
            },
            "blockers": [
                {
                    "code": "missing_semantic_scope_1",
                    "source_entry_id": slot_source_entry_id,
                }
            ],
            "failure": {"suggested_actions": ["cover accepted unit u-all"]},
        },
        {
            "status": "needs_input",
            "feedback": {
                "type": "semantic_completeness",
                "mechanical": True,
                "semantic_authority": False,
            },
            "blockers": [
                {
                    "code": "missing_semantic_scope_2",
                    "source_entry_id": slot_source_entry_id,
                }
            ],
            "failure": {"suggested_actions": ["cover reading block u-all:block-0001"]},
        },
        None,
    ]

    class ScriptedClient:
        def __init__(self, *, options: object) -> None:
            self.options = options

        async def __aenter__(self) -> ScriptedClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            tool_blocks = [
                ToolUseBlock("skill-1", "Skill", {"skill": "docfit-school-extract"}),
                ToolUseBlock(
                    "evidence-1",
                    "mcp__docfit__docfit_evidence",
                    {
                        "schema_version": "docfit_evidence_input_v1",
                        "focus": "unit_evidence_packet",
                    },
                ),
            ]
            yield AssistantMessage(
                content=tool_blocks,
                model="synthetic-model",
                message_id=f"message-{len(queries)}",
                session_id="session-design-dry-run",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=len(queries),
                session_id="session-design-dry-run",
                result="{}",
                structured_output={
                    "status": "complete",
                    "summary": "synthetic completion",
                    "semantic_judgments": (
                        _complete_name_judgments(
                            fixed_source_entry_id,
                            slot_source_entry_id,
                        )
                        if len(queries) == 1
                        else [_name_slot_judgment(slot_source_entry_id)]
                    ),
                },
                uuid=f"result-{len(queries)}",
            )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", ScriptedClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        lambda _prepared, _structured_output: feedbacks.pop(0),
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._materialization_readiness_feedback_for_complete_output",
        lambda _prepared: None,
    )

    execution = asyncio.run(
        _run_backend(
            prepared,
            backend,
            config,
            existing_unit_boundary_checkpoint=_unit_checkpoint(prepared),
        )
    )

    assert execution.sdk_query_count == 3
    assert execution.harness_feedback_attempts == 2
    assert execution.semantic_feedback_attempts == 2
    sdk_query_events = [
        event for event in execution.timing_events if event["operation"] == "sdk_query"
    ]
    assert len(sdk_query_events) == 3
    assert [event["stage_query_index"] for event in sdk_query_events] == [1, 2, 3]
    assert all(query.startswith("DocFit bounded post-unit semantic batch.") for query in queries)
    assert "Harness candidate feedback:" in queries[1]
    assert "Harness revision scope" in queries[1]
    assert "Harness candidate feedback:" in queries[2]
    assert feedbacks == []


@pytest.mark.parametrize(
    ("initial_field_id", "repaired_field_id", "expected_feedback_text"),
    [
        (
            "body.chapters",
            "author.name.zh",
            "not permitted by the input vocabulary",
        ),
        (
            "generated.toc",
            "author.name.zh",
            "not permitted by the input vocabulary",
        ),
    ],
)
def test_scripted_sdk_run_repairs_field_role_affordance_in_scoped_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_field_id: str,
    repaired_field_id: str,
    expected_feedback_text: str,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backend = _backend()
    config = tmp_path / "config"
    config.mkdir()
    queries: list[str] = []
    client_count = 0
    fixed_source_entry_id, slot_source_entry_id = _name_source_entry_ids(prepared)
    initial_judgment = _name_slot_judgment(slot_source_entry_id, initial_field_id)
    repaired_judgment = _name_slot_judgment(slot_source_entry_id, repaired_field_id)

    class ScriptedClient:
        def __init__(self, *, options: object) -> None:
            nonlocal client_count
            client_count += 1
            self.options = options

        async def __aenter__(self) -> ScriptedClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self) -> Any:
            query_count = len(queries)
            yield AssistantMessage(
                content=[
                    ToolUseBlock("skill-1", "Skill", {"skill": "docfit-school-extract"}),
                    ToolUseBlock(
                        "evidence-1",
                        "mcp__docfit__docfit_evidence",
                        {
                            "schema_version": "docfit_evidence_input_v1",
                            "focus": "unit_evidence_packet",
                            "unit_id": "u-all",
                        },
                    ),
                ],
                model="synthetic-model",
                message_id=f"message-{query_count}",
                session_id="session-readiness",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=query_count,
                session_id="session-readiness",
                result="{}",
                structured_output={
                    "status": "complete",
                    "summary": "synthetic completion",
                    "semantic_judgments": (
                        [
                            _fixed_name_judgment(fixed_source_entry_id),
                            initial_judgment,
                        ]
                        if query_count == 1
                        else [_fixed_name_judgment(fixed_source_entry_id), repaired_judgment]
                    ),
                },
                uuid=f"result-{query_count}",
            )

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", ScriptedClient)

    execution = asyncio.run(
        _run_backend(
            prepared,
            backend,
            config,
            existing_unit_boundary_checkpoint=_unit_checkpoint(prepared),
        )
    )

    assert client_count == 1
    assert execution.sdk_query_count == 2
    assert execution.harness_feedback_attempts == 1
    assert execution.semantic_feedback_attempts == 1
    assert len(queries) == 2
    assert queries[1].startswith("DocFit bounded post-unit semantic batch.")
    assert "Harness candidate feedback:" in queries[1]
    assert fixed_source_entry_id in queries[1]
    assert slot_source_entry_id in queries[1]
    assert expected_feedback_text in queries[1]
    assert execution.structured_output["semantic_judgments"] == [
        _fixed_name_judgment(fixed_source_entry_id),
        repaired_judgment,
    ]
