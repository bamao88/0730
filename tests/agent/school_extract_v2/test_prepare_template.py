from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from claude_agent_sdk.types import ResultMessage

from docfit.app.cli import build_parser
from docfit.app.prepare_template import (
    PREPARE_TEMPLATE_OUTPUT_SCHEMA,
    PrepareTemplateRequest,
    TemplateAgentExecution,
    _validated_sdk_output,
    build_prepare_template_options,
    prepare_template_task,
    run_prepare_template,
    run_template_agent,
)
from docfit.app.settings import AgentBackend
from docfit.tools.runtime import ToolFailure, sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = (
    PROJECT_ROOT / "evals/template-extraction/fixtures/S00-minimal-pass/actual-template.docx"
)
REGISTRY = PROJECT_ROOT / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
COUNTS = {"slot": 1, "protected": 1, "remove": 0, "manual": 0, "gap": 0, "unresolved": 0}


def _request(tmp_path: Path) -> PrepareTemplateRequest:
    requirements = tmp_path / "requirements.md"
    requirements.write_text("保留学校名称，并提供姓名填写位置。", encoding="utf-8")
    return PrepareTemplateRequest(
        school_template=TEMPLATE,
        school_requirements=requirements,
        field_registry=REGISTRY,
        output_directory=tmp_path / "prepared-task",
    )


def test_prepare_task_mounts_read_only_inputs_and_candidate_skill(tmp_path: Path) -> None:
    prepared = prepare_template_task(_request(tmp_path))

    assert prepared.template_path.stat().st_mode & 0o222 == 0
    assert prepared.requirements_path.stat().st_mode & 0o222 == 0
    assert prepared.registry_path.stat().st_mode & 0o222 == 0
    assert prepared.template_sha256 == sha256_file(TEMPLATE)
    assert (
        prepared.task_root / ".claude/skills/docfit-school-extract/scripts/compile_artifact_spec.py"
    ).is_file()
    assert (prepared.task_root / "work/attempts").is_dir()
    assert (prepared.task_root / "output").is_dir()


def test_prepare_options_use_one_candidate_server_skill_and_structured_output(
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backend = AgentBackend(
        name="kimi",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )
    config_directory = tmp_path / "sdk-config"
    config_directory.mkdir()

    options = build_prepare_template_options(prepared, backend, config_directory)

    assert options.skills == ["docfit-school-extract"]
    assert set(options.mcp_servers or {}) == {"docfit"}
    assert options.allowed_tools == []
    assert "Agent" in (options.disallowed_tools or ())
    assert options.output_format == {
        "type": "json_schema",
        "schema": options.output_format["schema"],
    }
    assert options.max_turns == 80
    assert options.cwd == prepared.task_root


def test_prepare_output_schema_requires_the_canonical_relative_artifact_path() -> None:
    artifact_path = PREPARE_TEMPLATE_OUTPUT_SCHEMA["properties"]["artifact_path"]

    assert artifact_path == {
        "type": ["string", "null"],
        "enum": ["output/template-artifact", None],
    }


def test_sdk_api_error_preserves_safe_backend_diagnostics() -> None:
    backend = AgentBackend(
        name="minimax",
        base_url="https://example.invalid/",
        model="test-model",
        credential_variable="TEST_KEY",
        api_key="secret",
    )
    result = ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=90,
        is_error=True,
        num_turns=1,
        session_id="session-error",
        stop_reason="stop_sequence",
        structured_output=None,
        api_error_status=402,
        terminal_reason="api_error",
    )

    with pytest.raises(ToolFailure) as caught:
        _validated_sdk_output(result, backend=backend)

    assert caught.value.code == "template_agent_backend_api_error"
    assert caught.value.retryable is False
    assert caught.value.message == (
        "The minimax Agent backend returned HTTP 402 "
        "(terminal_reason=api_error, turns=1)."
    )


def test_prepare_cli_has_the_approved_public_arguments() -> None:
    parsed = build_parser().parse_args(
        [
            "prepare-template",
            "--school-template",
            "template.docx",
            "--school-requirements",
            "requirements.md",
            "--field-registry",
            "fields.yaml",
            "--output",
            "task",
        ]
    )
    assert parsed.command == "prepare-template"
    assert parsed.output_directory == "task"


def test_run_prepare_template_accepts_only_disk_consistent_built_result(tmp_path: Path) -> None:
    async def fake_agent(prepared) -> TemplateAgentExecution:
        artifact = prepared.task_root / "output/template-artifact"
        artifact.mkdir()
        shutil.copyfile(prepared.template_path, artifact / "clean-template.docx")
        (artifact / "fill-contract.json").write_text("{}\n", encoding="utf-8")
        (artifact / "visual-review.json").write_text("{}\n", encoding="utf-8")
        (artifact / "build-report.json").write_text(
            json.dumps({"artifact_status": "built", "counts": COUNTS}),
            encoding="utf-8",
        )
        return TemplateAgentExecution(
            structured_output={
                "status": "built",
                "artifact_path": "output/template-artifact",
                "template_sha256": sha256_file(artifact / "clean-template.docx"),
                "fill_contract_sha256": sha256_file(artifact / "fill-contract.json"),
                "counts": COUNTS,
            },
            tool_uses=(
                "Skill",
                "mcp__docfit__template_observe",
                "mcp__docfit__template_compare",
                "mcp__docfit__template_build",
            ),
            skills_loaded=("docfit-school-extract",),
            session_id="session-1",
            backend="fake",
        )

    report = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert report.status == "built"
    assert report.artifact_path is not None
    assert Path(report.artifact_path).is_dir()
    assert report.counts == COUNTS


def test_run_prepare_template_preserves_true_blocked_result(tmp_path: Path) -> None:
    async def fake_agent(_prepared) -> TemplateAgentExecution:
        return TemplateAgentExecution(
            structured_output={
                "status": "blocked",
                "artifact_path": None,
                "template_sha256": None,
                "fill_contract_sha256": None,
                "counts": {
                    "slot": 0,
                    "protected": 0,
                    "remove": 0,
                    "manual": 0,
                    "gap": 0,
                    "unresolved": 1,
                },
            },
            tool_uses=("Skill", "mcp__docfit__template_observe"),
            skills_loaded=("docfit-school-extract",),
            session_id="session-blocked",
            backend="fake",
        )

    report = asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert report.status == "blocked"
    assert report.artifact_path is None
    assert not (Path(report.task_root) / "output/template-artifact").exists()


@pytest.mark.parametrize(
    ("tool_uses", "skills_loaded"),
    [
        (
            (
                "mcp__docfit__template_observe",
                "mcp__docfit__template_compare",
                "mcp__docfit__template_build",
            ),
            (),
        ),
        (
            ("Skill", "mcp__docfit__template_observe", "mcp__docfit__template_build"),
            ("docfit-school-extract",),
        ),
    ],
)
def test_built_result_requires_skill_and_core_tool_evidence(
    tmp_path: Path,
    tool_uses: tuple[str, ...],
    skills_loaded: tuple[str, ...],
) -> None:
    async def fake_agent(prepared) -> TemplateAgentExecution:
        artifact = prepared.task_root / "output/template-artifact"
        artifact.mkdir()
        shutil.copyfile(prepared.template_path, artifact / "clean-template.docx")
        (artifact / "fill-contract.json").write_text("{}\n", encoding="utf-8")
        (artifact / "visual-review.json").write_text("{}\n", encoding="utf-8")
        (artifact / "build-report.json").write_text(
            json.dumps({"artifact_status": "built", "counts": COUNTS}),
            encoding="utf-8",
        )
        return TemplateAgentExecution(
            structured_output={
                "status": "built",
                "artifact_path": "output/template-artifact",
                "template_sha256": sha256_file(artifact / "clean-template.docx"),
                "fill_contract_sha256": sha256_file(artifact / "fill-contract.json"),
                "counts": COUNTS,
            },
            tool_uses=tool_uses,
            skills_loaded=skills_loaded,
            session_id="session-incomplete",
            backend="fake",
        )

    with pytest.raises(ToolFailure, match="required Skill/Tool evidence") as caught:
        asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert caught.value.code == "template_agent_evidence_incomplete"


def test_changed_built_template_requires_mutation_tool_evidence(tmp_path: Path) -> None:
    async def fake_agent(prepared) -> TemplateAgentExecution:
        artifact = prepared.task_root / "output/template-artifact"
        artifact.mkdir()
        changed = bytearray(prepared.template_path.read_bytes())
        changed[-1] ^= 1
        (artifact / "clean-template.docx").write_bytes(changed)
        (artifact / "fill-contract.json").write_text("{}\n", encoding="utf-8")
        (artifact / "visual-review.json").write_text("{}\n", encoding="utf-8")
        (artifact / "build-report.json").write_text(
            json.dumps({"artifact_status": "built", "counts": COUNTS}),
            encoding="utf-8",
        )
        return TemplateAgentExecution(
            structured_output={
                "status": "built",
                "artifact_path": "output/template-artifact",
                "template_sha256": sha256_file(artifact / "clean-template.docx"),
                "fill_contract_sha256": sha256_file(artifact / "fill-contract.json"),
                "counts": COUNTS,
            },
            tool_uses=(
                "Skill",
                "mcp__docfit__template_observe",
                "mcp__docfit__template_compare",
                "mcp__docfit__template_build",
            ),
            skills_loaded=("docfit-school-extract",),
            session_id="session-no-mutation",
            backend="fake",
        )

    with pytest.raises(ToolFailure, match="mutation Tool evidence") as caught:
        asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert caught.value.code == "template_agent_evidence_incomplete"


def test_template_agent_timeout_moves_to_the_next_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backends = (
        AgentBackend("kimi", "https://kimi.invalid/", "kimi", "KIMI_KEY", "secret-1"),
        AgentBackend(
            "minimax",
            "https://minimax.invalid/",
            "minimax",
            "MINIMAX_KEY",
            "secret-2",
        ),
    )

    async def fake_run_backend(_prepared, backend: AgentBackend) -> TemplateAgentExecution:
        if backend.name == "kimi":
            await asyncio.sleep(1)
        return TemplateAgentExecution(
            structured_output={},
            tool_uses=(),
            skills_loaded=(),
            session_id="session-fallback",
            backend=backend.name,
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.iter_agent_backends", lambda: iter(backends)
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_backend", fake_run_backend)
    monkeypatch.setattr(
        "docfit.app.prepare_template.PREPARE_TEMPLATE_BACKEND_TIMEOUT_SECONDS", 0.01
    )

    execution = asyncio.run(run_template_agent(prepared))

    assert execution.backend == "minimax"


def test_template_agent_reports_all_backend_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepared = prepare_template_task(_request(tmp_path))
    backends = (
        AgentBackend("kimi", "https://kimi.invalid/", "kimi", "KIMI_KEY", "secret-1"),
        AgentBackend(
            "minimax",
            "https://minimax.invalid/",
            "minimax",
            "MINIMAX_KEY",
            "secret-2",
        ),
    )

    async def fake_run_backend(_prepared, backend: AgentBackend) -> TemplateAgentExecution:
        status = 403 if backend.name == "kimi" else 402
        raise ToolFailure(
            status="error",
            origin="agent",
            code="template_agent_backend_api_error",
            message=f"The {backend.name} Agent backend returned HTTP {status}.",
        )

    monkeypatch.setattr(
        "docfit.app.prepare_template.iter_agent_backends", lambda: iter(backends)
    )
    monkeypatch.setattr("docfit.app.prepare_template._run_backend", fake_run_backend)

    with pytest.raises(ToolFailure) as caught:
        asyncio.run(run_template_agent(prepared))

    assert caught.value.code == "template_agent_backends_failed"
    assert "kimi: The kimi Agent backend returned HTTP 403." in caught.value.message
    assert "minimax: The minimax Agent backend returned HTTP 402." in caught.value.message


def test_prepare_rejects_agent_that_changes_a_read_only_input(tmp_path: Path) -> None:
    async def fake_agent(prepared) -> TemplateAgentExecution:
        prepared.requirements_path.chmod(0o600)
        prepared.requirements_path.write_text("changed", encoding="utf-8")
        return TemplateAgentExecution(
            structured_output={
                "status": "blocked",
                "artifact_path": None,
                "template_sha256": None,
                "fill_contract_sha256": None,
                "counts": {
                    "slot": 0,
                    "protected": 0,
                    "remove": 0,
                    "manual": 0,
                    "gap": 0,
                    "unresolved": 1,
                },
            },
            tool_uses=("Skill",),
            skills_loaded=("docfit-school-extract",),
            session_id="session-mutated-input",
            backend="fake",
        )

    with pytest.raises(ToolFailure, match="read-only task input changed") as caught:
        asyncio.run(run_prepare_template(_request(tmp_path), agent_runner=fake_agent))

    assert caught.value.code == "prepare_input_changed"
