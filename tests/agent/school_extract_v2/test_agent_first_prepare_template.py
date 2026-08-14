from __future__ import annotations

from pathlib import Path

import pytest

from docfit.app.agent import project_root
from docfit.app.prepare_template import (
    PREPARE_TEMPLATE_MAX_TURNS,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _validate_agent_completion,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
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


def test_task_contains_inputs_not_a_runtime_skill_copy_or_work_items(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    assert prepared.template_path.stat().st_mode & 0o222 == 0
    assert prepared.registry_source.is_relative_to(prepared.task_root / "input")
    assert prepared.registry_source.stat().st_mode & 0o222 == 0
    assert prepared.registry_sha256 == sha256_file(REGISTRY)
    assert not (prepared.task_root / ".claude").exists()
    manifest = (prepared.task_root / "work/.docfit/prepare-template-task.json").read_text(
        encoding="utf-8"
    )
    assert '"architecture": "main_agent_full_context/v1"' in manifest
    assert "work_item" not in manifest
    assert not any((prepared.task_root / "output").iterdir())


def test_prompt_gives_one_complete_task_and_no_application_semantic_cursor(
    tmp_path: Path,
) -> None:
    prompt = build_prepare_template_prompt(prepare_template_task(_request(tmp_path)))

    assert "complete task access boundary" in prompt
    assert "decide your own inspection order" in prompt
    assert "optional read-only delegation" in prompt
    assert "visually review every final page" in prompt
    assert "without a meaningless edit" in prompt
    assert "work item" not in prompt.casefold()
    assert "crop" not in prompt.casefold()
    assert "cursor" not in prompt.casefold()


def test_options_expose_one_canonical_skill_five_tools_and_native_subagent(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    config = tmp_path / "config"
    config.mkdir()

    options = build_prepare_template_options(prepared, _backend(), config)

    assert options.cwd == ROOT
    assert options.skills == ["docfit-school-extract"]
    assert options.max_turns == PREPARE_TEMPLATE_MAX_TURNS
    assert options.allowed_tools == []
    assert set(options.tools or ()) == {
        "Skill",
        "Read",
        "Glob",
        "Grep",
        "AskUserQuestion",
        "Agent",
    }
    assert {"Bash", "Write"} <= set(options.disallowed_tools or ())
    assert set(options.mcp_servers or ()) == {"docfit"}
    assert set(options.agents or ()) == {"docfit-unit-analyst"}
    assert "work items" in str(options.system_prompt)
    assert "application does not provide" in str(options.system_prompt)


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
    monkeypatch.setattr(
        "docfit.app.prepare_template.DocFitToolService.validate",
        lambda _service, _args: {"status": "ok", "checks": []},
    )
    execution = TemplateAgentExecution(
        structured_output={
            "status": "complete",
            "final_docx": str(prepared.template_path),
            "candidate_render_ref": "render:v2:" + "0" * 64,
            "reviewed_pages": [1],
            "findings": [],
            "summary": "The immutable source already satisfies the result.",
        },
        tool_uses=(
            "Skill",
            "mcp__docfit__docx_inspect",
            "mcp__docfit__docx_render",
            "mcp__docfit__docx_visual_review",
            "mcp__docfit__docx_validate",
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
