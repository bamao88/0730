from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest
from PIL import Image

from docfit.app.convert import (
    REQUIRED_CONVERSION_TOOLS,
    AgentExecution,
    ConversionRequest,
    PreparedConversion,
    prepare_conversion,
    run_conversion,
)
from docfit.observability.events import ObservationEvent, SanitizationReceipt
from docfit.observability.report import project_conversion_report
from docfit.observability.runtime import NullObservationRecorder, ObservationRun
from docfit.observability.transcript import SDKTranscriptManager
from docfit.tools.runtime import ToolFailure, atomic_write_json, sha256_file, sha256_json


def _officecli(*arguments: str) -> None:
    executable = shutil.which("officecli")
    if executable is None:
        pytest.skip("M2 integration requires the locked OfficeCLI executable")
    environment = dict(os.environ)
    environment["OFFICECLI_SKIP_UPDATE"] = "1"
    environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
    completed = subprocess.run(
        [executable, *arguments, "--json"],
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["success"] is True


def _make_docx(path: Path, text: str) -> None:
    _officecli("create", str(path), "--locale", "zh-CN")
    _officecli(
        "add",
        str(path),
        "/body",
        "--type",
        "paragraph",
        "--prop",
        f"text={text}",
    )


async def _fake_completed_agent(
    prompt: str,
    prepared: PreparedConversion,
    transcripts: SDKTranscriptManager,
    observation_run: ObservationRun,
) -> AgentExecution:
    assert prepared.source_sha256 in prompt
    assert prepared.template_sha256 in prompt
    assert prepared.requirements_sha256 in prompt
    assert prepared.knowledge_digest in prompt
    shutil.copy2(prepared.source_docx, prepared.final_docx)
    prepared.final_docx.chmod(0o644)
    final_hash = sha256_file(prepared.final_docx)
    candidate_directory = prepared.work_directory / "candidate-adobe"
    pages_directory = candidate_directory / "pages"
    pages_directory.mkdir(parents=True)
    page = pages_directory / "page-0001.png"
    image = Image.new("RGB", (240, 340), "white")
    image.save(page, format="PNG")
    pdf = candidate_directory / "document.pdf"
    image.save(pdf, format="PDF", resolution=144)
    page_entry = {
        "page": 1,
        "path": str(page),
        "sha256": sha256_file(page),
        "width": 240,
        "height": 340,
        "bytes": page.stat().st_size,
    }
    provider = {
        "name": "adobe_pdf_services",
        "version": "4.2.0",
        "operation": "create_pdf_from_docx",
    }
    font_environment = {
        "fingerprint": None,
        "font_file_count": None,
        "substitutions": None,
        "source": "adobe_managed_service",
        "visibility": "opaque",
    }
    render_sha256 = sha256_json(
        {"document": final_hash, "page": page_entry["sha256"], "provider": provider}
    )
    reference = {
        "schema_version": 1,
        "document_path": str(prepared.final_docx),
        "document_sha256": final_hash,
        "render_sha256": render_sha256,
        "render_intent": "candidate_verification",
        "fidelity": "official_service_conversion",
        "target_application": None,
        "target_application_version": None,
        "provider": provider,
        "font_environment": font_environment,
        "font_substitutions": None,
        "conversion_profile": "adobe_pdf_services_default",
        "revision_display": "document_default",
        "parent_render_ref": {
            "render_sha256": "synthetic-baseline",
            "document_sha256": prepared.source_sha256,
        },
        "page_count": 1,
        "dpi": 144,
        "cache_key": "synthetic-cache",
        "artifacts": {
            "pdf": str(pdf),
            "pages": [page_entry],
            "pages_directory": str(pages_directory),
            "contact_sheet": None,
            "layout_map": None,
        },
        "warnings": [
            {
                "code": "service_managed_render_environment",
                "message": "Synthetic provider detail.",
            }
        ],
    }
    render_ref = candidate_directory / "render-ref.json"
    atomic_write_json(render_ref, reference)
    visual_review = {
        "schema_version": 1,
        "document_sha256": final_hash,
        "render_sha256": render_sha256,
        "provider": provider,
        "font_environment": font_environment,
        "reviewed_pages": [1],
        "evidence_refs": ["visual-page-1"],
        "findings": [],
    }
    structured = {
        "schema_version": 1,
        "status": "completed",
        "final_docx": str(prepared.final_docx),
        "candidate_render_ref": str(render_ref),
        "visual_review": visual_review,
        "task_rule_evidence": [
            {
                "kind": "synthetic_rule",
                "source_sha256": prepared.requirements_sha256,
            }
        ],
        "summary": "Stale Agent summary claiming a verification gap.",
        "warnings": ["stale verification gap from an intermediate Tool call"],
        "needs_input": [],
    }
    return AgentExecution(
        structured_output=structured,
        final_text="completed",
        tool_uses=tuple(sorted(REQUIRED_CONVERSION_TOOLS)),
        skills_loaded=("docfit-school-extract", "convert-thesis"),
        session_id="synthetic-session",
        backend="synthetic-backend",
    )


def test_thin_convert_shell_mounts_evidence_and_publishes_verified_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.docx"
    template = tmp_path / "template.docx"
    requirements = tmp_path / "requirements.txt"
    output = tmp_path / "output"
    _make_docx(source, "学生正文")
    _make_docx(template, "学校模板")
    requirements.write_text(
        "标题使用模板标题样式。正文保留。模板固定文字必须保留。",
        encoding="utf-8",
    )
    original_source_hash = sha256_file(source)
    request = ConversionRequest(source, template, requirements, output)
    observation_state = tmp_path / "observation-state"
    monkeypatch.setenv("XDG_STATE_HOME", str(observation_state))

    class BrokenSummaryRecorder(NullObservationRecorder):
        def __init__(self) -> None:
            super().__init__()
            self.events: list[ObservationEvent] = []

        @property
        def enabled(self) -> bool:
            return True

        def record(self, event: ObservationEvent) -> SanitizationReceipt:
            self.events.append(event)
            return SanitizationReceipt("accepted", "observer_event_accepted", 0.0)

        def summary(self) -> object:
            raise RuntimeError("PRIVATE_OBSERVER_FAILURE_CANARY")

    recorder = BrokenSummaryRecorder()
    report = asyncio.run(
        run_conversion(
            request,
            runner=_fake_completed_agent,
            observation=recorder,
        )
    )

    assert report.status == "COMPLETED"
    assert Path(report.final_docx or "").is_file()
    assert Path(report.candidate_pdf or "").is_file()
    assert Path(report.visual_review or "").is_file()
    assert Path(report.validation or "").is_file()
    assert (output / "conversion-report.json").is_file()
    assert report.schema_version == 2
    assert report.run_id is not None and report.run_id.startswith("run_")
    assert report.task_ref is not None and report.task_ref.startswith("task_")
    assert report.final_sha256 == sha256_file(Path(report.final_docx or ""))
    assert report.observation_coverage is not None
    assert report.observation_coverage.state == "unavailable"
    assert report.observation_coverage.failure_codes == ("observer_summary_failed",)
    assert report.sdk_transcript is not None
    assert report.sdk_transcript.status == "unknown"
    projected = project_conversion_report(output / "conversion-report.json")
    assert projected["run_id"] == report.run_id
    assert str(output) not in json.dumps(projected)
    assert "PRIVATE_OBSERVER_FAILURE_CANARY" not in (
        output / "conversion-report.json"
    ).read_text(encoding="utf-8")
    assert [event.kind for event in recorder.events] == [
        "run_started",
        "conversion_report",
        "run_finished",
    ]
    assert all(event.run_id == report.run_id for event in recorder.events)
    serialized_events = json.dumps([asdict(event) for event in recorder.events])
    assert str(output) not in serialized_events
    assert report.detail not in serialized_events
    assert sha256_file(source) == original_source_hash
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    assert validation["summary"]["errors"] == 0
    assert not validation["warnings"]
    assert report.knowledge_version == "v1"
    assert REQUIRED_CONVERSION_TOOLS.issubset(report.tool_uses)
    assert report.warnings == ("candidate:service_managed_render_environment",)
    assert "stale" not in report.detail.casefold()
    assert "complete Agent visual coverage" in report.detail
    assert not observation_state.exists()

    (output / "input").chmod(0o755)
    for path in (output / "input").iterdir():
        path.chmod(0o644)


def test_prepare_conversion_failure_does_not_publish_partial_task(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    template = tmp_path / "template.docx"
    requirements = tmp_path / "requirements.txt"
    output = tmp_path / "output"
    source.write_bytes(b"synthetic-source")
    template.write_bytes(b"synthetic-template")
    requirements.write_text("", encoding="utf-8")

    with pytest.raises(ToolFailure) as failure:
        prepare_conversion(ConversionRequest(source, template, requirements, output))

    assert failure.value.code == "requirements_empty"
    assert not output.exists()
