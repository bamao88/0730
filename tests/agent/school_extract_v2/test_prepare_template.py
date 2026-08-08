from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk.types import ResultMessage

from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    PREPARE_TEMPLATE_CONTEXT_TURN_LIMIT,
    PREPARE_TEMPLATE_FINALIZATION_TURN_LIMIT,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _run_backend,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
    run_prepare_template,
)
from docfit.app.settings import AgentBackend
from docfit.tools.runtime import ToolFailure, sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = PROJECT_ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
COUNTS = {"slot": 0, "remove": 0, "manual": 0, "gap": 0, "unresolved": 0}


def _request(tmp_path: Path) -> PrepareTemplateRequest:
    return PrepareTemplateRequest(
        school_template=TEMPLATE,
        output_directory=tmp_path / "prepared-task",
    )


def _backend() -> AgentBackend:
    return AgentBackend(
        name="minimax",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )


def test_prepare_task_has_only_inputs_internal_work_and_one_output_boundary(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    assert prepared.template_path.stat().st_mode & 0o222 == 0
    assert prepared.requirements_path is None
    assert prepared.registry_source == REGISTRY.resolve()
    assert prepared.template_sha256 == sha256_file(TEMPLATE)
    skill = prepared.task_root / ".claude/skills/docfit-school-extract"
    assert (skill / "SKILL.md").is_file()
    assert not (skill / "scripts").exists()
    assert not (prepared.task_root / "work/decisions").exists()
    assert not (prepared.task_root / "work/compiled").exists()
    assert not (prepared.task_root / "work/attempts").exists()
    assert not any((prepared.task_root / "output").iterdir())


def test_prepare_task_resumes_an_unpublished_matching_checkpoint(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepared = prepare_template_task(request)
    progress = prepared.task_root / "work/.docfit/template-workspace-v1/task-progress.json"
    progress.parent.mkdir(parents=True)
    progress.write_text('{"region_index": 15}', encoding="utf-8")

    resumed = prepare_template_task(request)

    assert resumed == prepared
    assert progress.read_text(encoding="utf-8") == '{"region_index": 15}'


def test_prepare_task_rejects_resume_with_a_different_source(tmp_path: Path) -> None:
    request = _request(tmp_path)
    prepare_template_task(request)
    different = tmp_path / "different.docx"
    different.write_bytes(TEMPLATE.read_bytes() + b"different")

    with pytest.raises(ToolFailure) as caught:
        prepare_template_task(
            PrepareTemplateRequest(
                school_template=different,
                output_directory=request.output_directory,
            )
        )

    assert caught.value.code == "prepare_source_mismatch"


def test_prepare_options_remove_bash_write_compilers_and_checker(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()

    options = build_prepare_template_options(prepared, _backend(), config)

    assert options.skills == ["docfit-school-extract"]
    assert set(options.mcp_servers or {}) == {"docfit"}
    assert options.allowed_tools == []
    assert {"Bash", "Write", "Agent"} <= set(options.disallowed_tools or ())
    assert "Bash" not in (options.tools or ())
    assert "Write" not in (options.tools or ())
    assert options.max_turns == PREPARE_TEMPLATE_CONTEXT_TURN_LIMIT


def test_prepare_options_allow_one_longer_final_generated_content_session(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    workspace = prepared.task_root / "work/.docfit/template-workspace-v1"
    workspace.mkdir(parents=True)
    (workspace / "task-progress.json").write_text('{"region_index": 2}', encoding="utf-8")
    (workspace / "visual-regions.json").write_text('{"regions": [[], []]}', encoding="utf-8")
    config = tmp_path / "config"
    config.mkdir()

    options = build_prepare_template_options(prepared, _backend(), config)
    prompt = build_prepare_template_prompt(prepared)

    assert options.max_turns == PREPARE_TEMPLATE_FINALIZATION_TURN_LIMIT
    assert "checkpoint_summary as a capability inventory" in prompt
    assert "materialized_structures contains body.chapters" in prompt
    assert "standalone body.paragraph slots do not replace" in prompt
    assert "visible Chinese 摘要 body needs abstract.zh" in prompt
    assert "Search/focus only for a missing capability" in prompt


def test_pending_edit_intent_takes_priority_over_narrow_toc_finalization(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    workspace = prepared.task_root / "work/.docfit/template-workspace-v1"
    workspace.mkdir(parents=True)
    (workspace / "task-progress.json").write_text(
        json.dumps(
            {
                "region_index": 2,
                "pending_edit_intents": [
                    {
                        "action": "materialize_structure",
                        "field_id": "body.chapters",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (workspace / "visual-regions.json").write_text('{"regions": [[], []]}', encoding="utf-8")

    prompt = build_prepare_template_prompt(prepared)

    assert "resolve every returned pending_edit_intent" in prompt
    assert "Search/focus is allowed only to re-locate" in prompt
    assert "resolve only the returned pending_generated_content" not in prompt


def test_prompt_is_object_driven_and_publishes_one_word(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    prompt = build_prepare_template_prompt(prepared)

    assert "current target region" in prompt
    assert "template_view action=next" in prompt
    assert "region_outcome=handled" in prompt
    assert "region_outcome=preserve" in prompt
    assert "Never preserve writing instructions" in prompt
    assert "stop cleanup and navigation" in prompt
    assert "commit materialize_structure before clearing" in prompt
    assert "chapter itself as level 1" in prompt
    assert "Do not search for nonexistent `1.1.1`" in prompt
    assert "never use `第一章 文献综述`" in prompt
    assert "separate `第X章（正文标题）`" in prompt
    assert "compare the returned document_order values" in prompt
    assert "members must be in physical document order but need not be adjacent" in prompt
    assert "does not return the exact known-failed operation" in prompt
    assert "second visual location for thesis.title.zh" in prompt
    assert "such as `科技报告`" in prompt
    assert "one representative fillable entry slot is sufficient" in prompt
    assert "preserve the fixed `附录` label" in prompt
    assert "application checkpoint" in prompt
    assert "Registry is Tool-private" in prompt
    assert "not a task list" in prompt
    assert "batch" in prompt.casefold()
    assert "do not review every page" in prompt.casefold()
    assert "output/final-template.docx" in prompt
    assert "compiler" not in prompt.casefold()
    assert "attempt" not in prompt.casefold()


def test_context_boundary_starts_fresh_sdk_session_and_keeps_application_progress(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    results = [
        ResultMessage(
            subtype="error_max_turns",
            duration_ms=100,
            duration_api_ms=80,
            is_error=True,
            num_turns=PREPARE_TEMPLATE_CONTEXT_TURN_LIMIT,
            session_id="segment-one",
            terminal_reason="max_turns",
        ),
        ResultMessage(
            subtype="success",
            duration_ms=50,
            duration_api_ms=40,
            is_error=False,
            num_turns=2,
            session_id="segment-two",
            structured_output={
                "status": "blocked",
                "artifact_path": None,
                "template_sha256": None,
                "counts": {**COUNTS, "unresolved": 1},
            },
            terminal_reason="end_turn",
        ),
    ]
    options_seen: list[Any] = []
    prompts: list[str] = []

    class FakeClient:
        def __init__(self, *, options: Any) -> None:
            options_seen.append(options)
            self.result = results[len(options_seen) - 1]

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def query(self, prompt: str) -> None:
            prompts.append(prompt)

        async def receive_response(self) -> Any:
            yield self.result

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", FakeClient)

    execution = asyncio.run(_run_backend(prepared, _backend()))

    assert len(options_seen) == 2
    assert all(option.resume is None for option in options_seen)
    assert all(option.continue_conversation is False for option in options_seen)
    assert all("application checkpoint" in prompt for prompt in prompts)
    assert execution.session_id == "segment-two"
    assert execution.num_turns == PREPARE_TEMPLATE_CONTEXT_TURN_LIMIT + 2


def test_cli_requirements_and_registry_are_optional() -> None:
    parsed = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "school.docx",
            "--output",
            "task",
        ]
    )

    assert parsed.school_requirements is None
    assert parsed.field_registry is None


def test_run_prepare_template_accepts_exactly_one_published_word(tmp_path: Path) -> None:
    async def fake_agent(prepared: Any) -> TemplateAgentExecution:
        output = prepared.task_root / "output/final-template.docx"
        shutil.copyfile(prepared.template_path, output)
        return TemplateAgentExecution(
            structured_output={
                "status": "built",
                "artifact_path": "output/final-template.docx",
                "template_sha256": sha256_file(output),
                "counts": COUNTS,
            },
            tool_uses=(
                "Skill",
                "mcp__docfit__template_view",
                "mcp__docfit__template_publish",
            ),
            skills_loaded=("docfit-school-extract",),
            session_id="session-test",
            backend="minimax",
            num_turns=4,
            duration_ms=1200,
            duration_api_ms=900,
        )

    report = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert report.status == "built"
    assert report.artifact_path is not None
    assert Path(report.artifact_path).name == "final-template.docx"
    assert [item.name for item in (Path(report.task_root) / "output").iterdir()] == [
        "final-template.docx"
    ]
    trace = Path(report.task_root) / "work/.docfit/template-agent-execution.json"
    assert trace.is_file()
    assert report.num_turns == 4


def test_run_prepare_template_preserves_true_blocked_result(tmp_path: Path) -> None:
    async def fake_agent(_prepared: Any) -> TemplateAgentExecution:
        return TemplateAgentExecution(
            structured_output={
                "status": "blocked",
                "artifact_path": None,
                "template_sha256": None,
                "counts": {**COUNTS, "unresolved": 1},
            },
            tool_uses=("Skill", "mcp__docfit__template_view"),
            skills_loaded=("docfit-school-extract",),
            session_id="session-blocked",
            backend="minimax",
            num_turns=3,
            duration_ms=1000,
            duration_api_ms=800,
        )

    report = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert report.status == "blocked"
    assert report.artifact_path is None
    assert not any((Path(report.task_root) / "output").iterdir())
