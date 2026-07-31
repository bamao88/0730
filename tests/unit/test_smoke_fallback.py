from __future__ import annotations

import asyncio

import pytest

from docfit.app.settings import AgentBackend, BackendName
from docfit.app.smoke import SmokeCase, SmokeReport, run_smoke_with_fallback


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
            detail="candidate result",
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
