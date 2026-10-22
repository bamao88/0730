from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from claude_agent_sdk.types import AssistantMessage, ResultMessage, ToolUseBlock

from docfit.app.agent import project_root
from docfit.app.prepare_template import (
    PreparedTemplateTask,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _run_backend,
    _select_host_candidate_for_accepted_semantics,
    _validate_agent_completion,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
    run_prepare_template,
)
from docfit.app.settings import AgentBackend
from docfit.tools.runtime import ToolFailure, sha256_file

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


def _semantic_judgments_for_source(prepared: PreparedTemplateTask) -> list[dict[str, object]]:
    block_id = "u-all:block-0001"
    return [
        {
            "scope": {"reading_block_id": block_id},
            "parts": [{"role": "manual_region", "text": "source already complete"}],
            "resolved_spans": [
                {
                    "span_ref": f"reading_block_id={block_id};part_index=0",
                    "scope": {"reading_block_id": block_id},
                    "reading_block_id": block_id,
                    "part_index": 0,
                    "role": "manual_region",
                    "text": "source already complete",
                    "covered_object_ids": ["obj-source"],
                }
            ],
        }
    ]


def _persist_accepted_source_noop_semantics(prepared: PreparedTemplateTask) -> None:
    harness = prepared.task_root / "work/.docfit/harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "object-inventory.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "document_sha256": prepared.template_sha256,
                "object_count": 1,
                "reading_block_count": 1,
                "objects": [
                    {
                        "object_id": "obj-source",
                        "type": "paragraph",
                        "locator": "/body/p[1]",
                    }
                ],
                "reading_blocks": [
                    {
                        "block_id": "u-all:block-0001",
                        "range_id": "u-all:range-0001",
                        "unit_id": "u-all",
                        "text": "source already complete",
                        "covered_object_ids": ["obj-source"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (harness / "semantic-judgments.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "semantic_judgments_sha256": "f" * 64,
                "document_sha256": prepared.template_sha256,
                "judgment_count": 1,
                "covered_object_count": 1,
                "semantic_judgments": _semantic_judgments_for_source(prepared),
            }
        ),
        encoding="utf-8",
    )


def _unit_checkpoint(prepared: PreparedTemplateTask) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ok",
        "checkpoint": "unit-boundary",
        "source_hash": prepared.template_sha256,
        "summary": "Accepted synthetic unit boundary checkpoint.",
        "unit_count": 1,
        "units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_boundary": {"page": 1, "seen_text": "start"},
                "end_boundary": {"page": 1, "seen_text": "end"},
            }
        ],
        "resolved_units": [
            {
                "unit_id": "u-all",
                "unit_name": "source",
                "start_locator": "/body/p[1]",
                "end_locator": "/body/p[1]",
            }
        ],
    }


def test_task_contains_inputs_not_a_runtime_skill_copy_or_work_items(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    assert prepared.template_path.stat().st_mode & 0o222 == 0
    assert prepared.registry_source.is_relative_to(prepared.task_root / "input")
    assert prepared.registry_source.stat().st_mode & 0o222 == 0
    assert prepared.registry_sha256 == sha256_file(REGISTRY)
    assert not (prepared.task_root / ".claude").exists()
    manifest = json.loads(
        (prepared.task_root / "work/.docfit/prepare-template-task.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["architecture"] == "main_agent_full_context/v1"
    assert manifest["output_boundary"] == [
        "output/final-template.docx",
        "output/fill-contract.yaml",
    ]
    assert "work_item" not in json.dumps(manifest)
    assert manifest["harness"]["agent_visible_tool"] is False
    assert "asset_directory" not in manifest["harness"]
    assert not any((prepared.task_root / "output").iterdir())


def test_prompt_gives_one_complete_task_and_no_application_semantic_cursor(
    tmp_path: Path,
) -> None:
    prompt = build_prepare_template_prompt(prepare_template_task(_request(tmp_path)))

    assert "startup brief v1" in prompt
    assert "trust=untrusted_docx_source_data" in prompt
    assert "handles only, not raw OOXML or a full inventory dump" in prompt
    assert "docfit_evidence" in prompt
    assert "docfit_check" not in prompt
    assert "Return semantic_judgments" in prompt
    assert "host runtime maps semantic ranges" in prompt
    assert "scope reading_block_id or reading_range_id" in prompt
    assert "ordered parts array over visible text" in prompt
    assert "Do not invent low-level document positions, spans, slots" in prompt
    assert "Optional subagents" not in prompt
    assert "same SDK session" in prompt
    assert "do not select or name final candidate documents" in prompt
    assert "docx_inspect" not in prompt
    assert "docx_edit" not in prompt
    assert "call docx_validate" not in prompt
    assert "template_harness" not in prompt
    assert "work item" not in prompt.casefold()
    assert "crop" not in prompt.casefold()
    assert "cursor" not in prompt.casefold()


def test_full_options_are_bounded_post_unit_semantic_transaction(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()

    options = build_prepare_template_options(prepared, _backend(), config)

    assert options.cwd == ROOT
    assert options.skills == ["docfit-school-extract"]
    assert options.allowed_tools == []
    assert set(options.tools or ()) == {"Skill", "Read"}
    assert {"Agent", "AskUserQuestion", "Glob", "Grep", "Bash", "Write"} <= set(
        options.disallowed_tools or ()
    )
    assert set(options.mcp_servers or ()) == {"docfit"}
    assert not options.agents
    assert options.max_turns <= 20
    assert options.effort == "low"
    assert options.thinking == {"type": "adaptive"}
    assert options.include_partial_messages is True
    assert "post-unit school-template semantic judgment Agent" in str(
        options.system_prompt
    )
    assert "bounded semantic-output stage" in str(options.system_prompt)
    assert "Do not delegate" in str(options.system_prompt)
    assert "docx_*" not in str(options.system_prompt)


def test_post_unit_options_are_bounded_semantic_transaction(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()

    options = build_prepare_template_options(
        prepared,
        _backend(),
        config,
        stop_after_post_unit=True,
    )

    assert options.cwd == ROOT
    assert options.skills == ["docfit-school-extract"]
    assert options.allowed_tools == []
    assert set(options.tools or ()) == {"Skill", "Read"}
    assert {"Agent", "AskUserQuestion", "Glob", "Grep", "Bash", "Write"} <= set(
        options.disallowed_tools or ()
    )
    assert not options.agents
    assert options.max_turns <= 20
    assert options.effort == "low"
    assert options.thinking == {"type": "adaptive"}
    assert options.include_partial_messages is True
    assert set(options.mcp_servers or ()) == {"docfit"}
    assert "post-unit school-template semantic judgment Agent" in str(
        options.system_prompt
    )


def test_resume_rejects_legacy_checkpoint_instead_of_migrating_it(tmp_path: Path) -> None:
    output = tmp_path / "legacy"
    (output / "input").mkdir(parents=True)
    (output / "work").mkdir()
    (output / "output").mkdir()

    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(
            PrepareTemplateRequest(
                school_template=TEMPLATE,
                output_directory=output,
                field_registry=REGISTRY,
            )
        )

    assert caught.value.code == "prepare_checkpoint_invalid"


def test_legacy_application_workflow_surface_is_deleted() -> None:
    for relative in (
        "src/docfit/template/workspace.py",
        "src/docfit/tools/template_tools.py",
        "src/docfit/tools/template_schemas/workspace.py",
        "docs/plans/docfit-school-extract-v2-candidate-skill/SKILL.md",
    ):
        assert not (ROOT / relative).exists()


def test_clean_source_may_be_selected_without_forcing_docx_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    _persist_accepted_source_noop_semantics(prepared)
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda _service, _args: {"status": "ok", "checks": []},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "ok", "failure": None},
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._semantic_coverage_feedback",
        lambda _prepared, _output: None,
    )
    execution = TemplateAgentExecution(
        structured_output={
            "status": "complete",
            "summary": "The immutable source already satisfies the result.",
            "semantic_judgments": _semantic_judgments_for_source(prepared),
        },
        tool_uses=(
            "Skill",
            "mcp__docfit__docfit_evidence",
        ),
        skills_loaded=("docfit-school-extract",),
        session_id="session-test",
        backend="test",
        num_turns=1,
        duration_ms=1,
        duration_api_ms=1,
    )

    candidate, _review, validation = _validate_agent_completion(prepared, execution)

    assert candidate == prepared.template_path
    assert validation["status"] == "ok"


def test_publishable_source_still_requires_accepted_source_noop_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    harness = prepared.task_root / "work/.docfit/harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "object-inventory.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "document_sha256": prepared.template_sha256,
                "object_count": 0,
                "reading_block_count": 0,
                "objects": [],
                "reading_blocks": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "docfit.app.prepare_template._source_noop_publishability",
        lambda _prepared: {"status": "ok", "failure": None},
    )

    with pytest.raises(ToolFailure) as caught:
        _select_host_candidate_for_accepted_semantics(prepared)

    assert caught.value.code == "template_materialization_semantics_missing"


def test_same_session_feedback_loop_requeries_existing_sdk_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backend = _backend()
    config = tmp_path / "config"
    config.mkdir()
    queries: list[str] = []
    client_count = 0
    feedbacks: list[dict[str, object] | None] = [
        {
            "status": "needs_input",
            "feedback": {
                "type": "semantic_completeness",
                "mechanical": True,
                "semantic_authority": False,
            },
            "blockers": [{"code": "missing_semantic_judgments"}],
            "failure": {"suggested_actions": ["repair semantic_judgments"]},
        },
        None,
    ]

    class FakeClient:
        def __init__(self, *, options: object) -> None:
            nonlocal client_count
            client_count += 1
            self.options = options

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            queries.append(prompt)

        async def receive_response(self):
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
                message_id=f"message-{len(queries)}",
                session_id="session-r1",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=len(queries),
                session_id="session-r1",
                result="{}",
                structured_output={
                    "status": "complete",
                    "summary": "semantic judgments complete",
                    "semantic_judgments": [{"judgment": "fixed_content"}],
                },
                uuid=f"result-{len(queries)}",
            )

    def fake_feedback(
        _prepared: PreparedTemplateTask,
        _structured_output: dict[str, object],
    ) -> dict[str, object] | None:
        return feedbacks.pop(0)

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", FakeClient)
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

    assert execution.session_id == "session-r1"
    assert client_count == 1
    assert execution.sdk_query_count == 2
    assert execution.harness_feedback_attempts == 1
    assert execution.semantic_feedback_attempts == 1
    assert len(queries) == 2
    assert "startup brief v1" in queries[0]
    assert "Runtime Harness feedback" in queries[1]
    assert feedbacks == []


def test_agent_needs_input_writes_judgable_failure_trace(tmp_path: Path) -> None:
    async def agent_runner(_prepared: object) -> TemplateAgentExecution:
        return TemplateAgentExecution(
            structured_output={
                "status": "needs_input",
                "needs_input": ["school requirement text needed for title handling"],
                "summary": "Stopped before a semantic decision.",
                "semantic_judgments": [],
            },
            tool_uses=("Skill", "mcp__docfit__docfit_evidence"),
            skills_loaded=("docfit-school-extract",),
            session_id="session-test",
            backend="test",
            num_turns=3,
            duration_ms=100,
            duration_api_ms=90,
            wall_duration_ms=110,
        )

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=agent_runner))

    trace = json.loads(
        (
            tmp_path
            / "prepared-task/work/.docfit/template-agent-execution.json"
        ).read_text(encoding="utf-8")
    )
    assert caught.value.code == "template_agent_needs_input"
    assert trace["status"] == "failed"
    assert trace["failure"]["code"] == "template_agent_needs_input"
    assert trace["agent_completion"]["status"] == "needs_input"
    assert trace["agent_completion"]["needs_input"] == [
        "school requirement text needed for title handling"
    ]
    assert trace["tool_uses"] == ["Skill", "mcp__docfit__docfit_evidence"]
