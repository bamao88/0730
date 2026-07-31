from __future__ import annotations

from pathlib import Path

from docfit.cli import main


def test_doctor_is_a_credential_free_ci_gate(capsys: object) -> None:
    assert main(["doctor"]) == 0


def test_live_smoke_fails_closed_without_agent_backend(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
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

    assert main(["agent-smoke", "--case", "image"]) == 2
