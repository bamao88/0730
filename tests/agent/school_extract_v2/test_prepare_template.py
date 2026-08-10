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
    references = sorted(item.name for item in (skill / "references").iterdir())
    assert references == [
        "body-structure.md",
        "collection-and-optional-sections.md",
        "effective-style.md",
        "generated-content.md",
        "logical-page-starts.md",
        "object-safety.md",
    ]
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for reference in references:
        assert f"](references/{reference})" in skill_text
        assert f"`references/{reference}`" not in skill_text
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
    assert {"Bash", "Write", "Agent", "Glob", "Grep"} <= set(
        options.disallowed_tools or ()
    )
    assert "Bash" not in (options.tools or ())
    assert "Write" not in (options.tools or ())
    assert "Glob" not in (options.tools or ())
    assert "Grep" not in (options.tools or ())
    assert options.tools == ["Skill", "Read", "AskUserQuestion"]
    assert options.hooks["PreToolUse"][1].matcher == "Read"
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
    assert "materialized_members, style_signatures, and structural_risks" in prompt
    assert "facts rather than a semantic completion verdict" in prompt
    assert "template_search/template_focus only for a concrete missing capability" in prompt
    assert "materialized_structures contains body.chapters" not in prompt
    assert "visible Chinese 摘要 body needs abstract.zh" not in prompt


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
    assert "template_search or template_focus only to re-locate" in prompt
    assert "resolve only the returned pending_generated_content" not in prompt


def test_prompt_is_object_driven_and_publishes_one_word(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    prompt = build_prepare_template_prompt(prepared)

    assert "Start with template_open" in prompt
    assert "template_next using outcome=handled" in prompt
    assert "outcome=preserve" in prompt
    assert "Never preserve writing instructions" in prompt
    assert "one template_edit operations array" in prompt
    assert "does not require a global H1/H2/H3 grammar" in prompt
    assert "effective_format={color:black, underline:none}" in prompt
    assert "ensure_page_start" in prompt
    assert "knowledge_signals" in prompt
    assert "Read only the matching relative reference" in prompt
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


def test_backend_timeout_is_scoped_to_one_sdk_segment(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    class StalledClient:
        def __init__(self, *, options: Any) -> None:
            self.options = options

        async def __aenter__(self) -> StalledClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def query(self, _prompt: str) -> None:
            return None

        async def receive_response(self) -> Any:
            await asyncio.Event().wait()
            yield None

    monkeypatch.setattr("docfit.app.prepare_template.ClaudeSDKClient", StalledClient)
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_SEGMENT_TIMEOUT_SECONDS", 0.01
    )

    with pytest.raises(TimeoutError):
        asyncio.run(_run_backend(prepared, _backend()))


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
                "mcp__docfit__template_open",
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
            tool_uses=("Skill", "mcp__docfit__template_open"),
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
