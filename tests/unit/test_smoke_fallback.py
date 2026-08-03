from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docfit.app.settings import AgentBackend, BackendName
from docfit.app.smoke import (
    SmokeCase,
    SmokeReport,
    _invalidate_receipt,
    _write_receipt,
    receipt_directory,
    run_smoke_with_fallback,
)


def _backend(name: BackendName, key: str) -> AgentBackend:
    return AgentBackend(
        name=name,
        base_url=f"https://{name}.example/",
        model=f"{name}-model",
        credential_variable=f"DOCFIT_{name.upper()}_API_KEY",
        api_key=key,
    )


def test_smoke_tries_all_kimi_candidates_before_minimax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = (
        _backend("kimi", "kimi-one"),
        _backend("kimi", "kimi-two"),
        _backend("minimax", "minimax-one"),
    )
    calls: list[tuple[str, str]] = []

    async def fake_run_smoke(
        case_name: SmokeCase,
        backend: AgentBackend,
    ) -> SmokeReport:
        calls.append((case_name, backend.name))
        passed = backend.name == "minimax"
        return SmokeReport(
            case="image",
            status="PASS" if passed else "FAIL",
            backend=backend.name,
            session_id="session" if passed else None,
            tool_uses=(),
            detail=(
                "candidate passed"
                if passed
                else "failed candidate containing model or document content"
            ),
        )

    monkeypatch.setattr("docfit.app.smoke.run_smoke", fake_run_smoke)

    report = asyncio.run(run_smoke_with_fallback("image", backends))

    assert calls == [
        ("image", "kimi"),
        ("image", "kimi"),
        ("image", "minimax"),
    ]
    assert report.status == "PASS"
    assert report.backend == "minimax"
    assert "Earlier candidates failed" in report.detail
    assert "failed candidate" not in report.detail


def test_smoke_timeout_moves_to_next_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = (
        _backend("kimi", "kimi-one"),
        _backend("minimax", "minimax-one"),
    )

    async def fake_run_smoke(
        case_name: SmokeCase,
        backend: AgentBackend,
    ) -> SmokeReport:
        if backend.name == "kimi":
            await asyncio.sleep(1)
        return SmokeReport(
            case=case_name,
            status="PASS",
            backend=backend.name,
            session_id="session",
            tool_uses=(),
            detail="candidate passed",
        )

    monkeypatch.setattr("docfit.app.smoke.run_smoke", fake_run_smoke)
    monkeypatch.setattr("docfit.app.smoke.SMOKE_BACKEND_TIMEOUT_SECONDS", 0.01)

    report = asyncio.run(run_smoke_with_fallback("image", backends))

    assert report.status == "PASS"
    assert report.backend == "minimax"
    assert "timed out" in report.detail


def test_new_live_attempt_invalidates_stale_pass_receipt(tmp_path: Path) -> None:
    report = SmokeReport(
        case="image",
        status="PASS",
        backend="kimi",
        session_id="old-session",
        tool_uses=("mcp__docfit__docx_visual_review",),
        detail="old pass",
    )
    _write_receipt(report, root=tmp_path)
    receipt = receipt_directory(tmp_path) / "image.json"
    assert receipt.is_file()

    _invalidate_receipt("image", root=tmp_path)

    assert not receipt.exists()
