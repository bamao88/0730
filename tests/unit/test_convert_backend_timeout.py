from __future__ import annotations

import asyncio

import pytest

from docfit.app.convert import AgentExecution, run_conversion_agent
from docfit.app.settings import AgentBackend, BackendName


def _backend(name: BackendName, candidate: str = "primary") -> AgentBackend:
    return AgentBackend(
        name=name,
        base_url=f"https://{name}.example/",
        model=f"{name}-model",
        credential_variable=f"DOCFIT_{name.upper()}_API_KEY_{candidate.upper()}",
        api_key=f"{name}-{candidate}-secret",
    )


def test_conversion_timeout_moves_to_next_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = (_backend("kimi"), _backend("minimax"))

    async def fake_run_backend(
        prompt: str,
        prepared: object,
        backend: AgentBackend,
    ) -> AgentExecution:
        assert prompt == "prompt"
        if backend.name == "kimi":
            await asyncio.sleep(1)
        return AgentExecution(
            structured_output={},
            final_text="done",
            tool_uses=(),
            skills_loaded=(),
            session_id="session",
            backend=backend.name,
        )

    monkeypatch.setattr("docfit.app.convert.iter_agent_backends", lambda: iter(backends))
    monkeypatch.setattr("docfit.app.convert._run_backend", fake_run_backend)
    monkeypatch.setattr("docfit.app.convert.CONVERSION_BACKEND_TIMEOUT_SECONDS", 0.01)

    result = asyncio.run(run_conversion_agent("prompt", object()))  # type: ignore[arg-type]

    assert result.backend == "minimax"


def test_conversion_timeout_skips_duplicate_credentials_for_same_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = (
        _backend("kimi", "first"),
        _backend("kimi", "backup"),
        _backend("minimax"),
    )
    calls: list[str] = []

    async def fake_run_backend(
        prompt: str,
        prepared: object,
        backend: AgentBackend,
    ) -> AgentExecution:
        calls.append(backend.credential_variable)
        if backend.name == "kimi":
            await asyncio.sleep(1)
        return AgentExecution(
            structured_output={},
            final_text="done",
            tool_uses=(),
            skills_loaded=(),
            session_id="session",
            backend=backend.name,
        )

    monkeypatch.setattr("docfit.app.convert.iter_agent_backends", lambda: iter(backends))
    monkeypatch.setattr("docfit.app.convert._run_backend", fake_run_backend)
    monkeypatch.setattr("docfit.app.convert.CONVERSION_BACKEND_TIMEOUT_SECONDS", 0.01)

    result = asyncio.run(run_conversion_agent("prompt", object()))  # type: ignore[arg-type]

    assert result.backend == "minimax"
    assert calls == [
        "DOCFIT_KIMI_API_KEY_FIRST",
        "DOCFIT_MINIMAX_API_KEY_PRIMARY",
    ]
