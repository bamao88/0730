from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from docfit.app.convert import (
    AgentExecution,
    BackendAttemptFailure,
    run_conversion_agent,
)
from docfit.app.settings import AgentBackend, BackendName
from docfit.observability.runtime import ObservationRun
from docfit.observability.transcript import SDKTranscriptManager


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
    tmp_path: Path,
) -> None:
    backends = (_backend("kimi"), _backend("minimax"))

    async def fake_run_backend(
        prompt: str,
        prepared: object,
        backend: AgentBackend,
        config_directory: Path,
        observation_run: ObservationRun,
    ) -> AgentExecution:
        assert prompt == "prompt"
        assert config_directory.is_dir()
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

    result = asyncio.run(
        run_conversion_agent(
            "prompt",
            object(),  # type: ignore[arg-type]
            SDKTranscriptManager(parent=tmp_path / "transcripts"),
        )
    )

    assert result.backend == "minimax"


def test_conversion_timeout_skips_duplicate_credentials_for_same_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
        config_directory: Path,
        observation_run: ObservationRun,
    ) -> AgentExecution:
        assert config_directory.is_dir()
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

    result = asyncio.run(
        run_conversion_agent(
            "prompt",
            object(),  # type: ignore[arg-type]
            SDKTranscriptManager(parent=tmp_path / "transcripts"),
        )
    )

    assert result.backend == "minimax"
    assert calls == [
        "DOCFIT_KIMI_API_KEY_FIRST",
        "DOCFIT_MINIMAX_API_KEY_PRIMARY",
    ]


def test_conversion_request_rejection_skips_duplicate_credentials_for_same_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
        config_directory: Path,
        observation_run: ObservationRun,
    ) -> AgentExecution:
        assert config_directory.is_dir()
        calls.append(backend.credential_variable)
        if backend.name == "kimi":
            raise BackendAttemptFailure(
                "backend_request_rejected",
                retry_same_route=False,
            )
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

    result = asyncio.run(
        run_conversion_agent(
            "prompt",
            object(),  # type: ignore[arg-type]
            SDKTranscriptManager(parent=tmp_path / "transcripts"),
        )
    )

    assert result.backend == "minimax"
    assert calls == [
        "DOCFIT_KIMI_API_KEY_FIRST",
        "DOCFIT_MINIMAX_API_KEY_PRIMARY",
    ]
