from __future__ import annotations

from pathlib import Path

from docfit.app.cli import main
from docfit.app.smoke import SmokeReport, _write_receipt, receipt_directory


def test_doctor_is_a_credential_free_ci_gate(capsys: object) -> None:
    assert main(["doctor"]) == 0


def test_live_smoke_fails_closed_without_agent_backend(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "docfit.app.smoke.project_root",
        lambda: project,
    )
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DOCFIT_ENV_FILE",
        str(tmp_path / "missing-agent.env"),
    )
    for name in (
        "DOCFIT_KIMI_API_KEY",
        "DOCFIT_KIMI_API_KEY_2",
        "DOCFIT_KIMI_API_KEY_BACKUP",
        "DOCFIT_MINIMAX_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)  # type: ignore[attr-defined]

    _write_receipt(
        SmokeReport(
            case="image",
            status="PASS",
            backend="test",
            model="test-model",
            session_id="previous-live-session",
            tool_uses=("mcp__docfit__docx_visual_review",),
            detail="previous live proof",
        ),
        root=project,
    )

    assert main(["agent-smoke", "--case", "image"]) == 2
    assert (receipt_directory(project) / "image.json").is_file()
