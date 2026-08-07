from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    PrepareTemplateRequest,
    TemplateAgentExecution,
    build_prepare_template_options,
    build_prepare_template_prompt,
    prepare_template_task,
    run_prepare_template,
)
from docfit.app.settings import AgentBackend
from docfit.tools.runtime import sha256_file

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
    assert options.max_turns is None


def test_prompt_is_object_driven_and_publishes_one_word(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    prompt = build_prepare_template_prompt(prepared)

    assert "current page/object context" in prompt
    assert "Registry is Tool-private" in prompt
    assert "not a task list" in prompt
    assert "batch" in prompt.casefold()
    assert "do not review every page" in prompt.casefold()
    assert "output/final-template.docx" in prompt
    assert "compiler" not in prompt.casefold()
    assert "attempt" not in prompt.casefold()


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
