from __future__ import annotations

import os
from pathlib import Path

import pytest

from docfit.app.settings import (
    AgentConfigurationError,
    agent_env_file_is_private,
    iter_agent_backends,
    read_agent_env_file,
)


def test_shared_env_parser_and_backend_priority(tmp_path: Path) -> None:
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join(
            (
                "# one shared local secret surface",
                "DOCFIT_AGENT_BACKEND_ORDER=kimi,minimax",
                "DOCFIT_KIMI_API_KEY=kimi-primary",
                "DOCFIT_KIMI_API_KEY_2=kimi-secondary",
                "DOCFIT_KIMI_API_KEY_BACKUP=kimi-primary",
                "DOCFIT_MINIMAX_API_KEY=minimax-primary",
                "FUTURE_PROVIDER_API_KEY=future-secret",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    backends = tuple(iter_agent_backends({}, env_file=env_file))

    assert [(backend.name, backend.credential_variable) for backend in backends] == [
        ("kimi", "DOCFIT_KIMI_API_KEY"),
        ("kimi", "DOCFIT_KIMI_API_KEY_2"),
        ("minimax", "DOCFIT_MINIMAX_API_KEY"),
    ]
    assert backends[0].base_url == "https://api.kimi.com/coding/"
    assert backends[0].model == "kimi-for-coding"
    assert backends[-1].model == "MiniMax-M3"
    assert agent_env_file_is_private(env_file)
    assert "FUTURE_PROVIDER_API_KEY" in read_agent_env_file(env_file)


def test_process_values_override_the_shared_file(tmp_path: Path) -> None:
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "DOCFIT_KIMI_API_KEY=file-key\nDOCFIT_KIMI_MODEL=file-model\n",
        encoding="utf-8",
    )

    backend = next(
        iter_agent_backends(
            {
                "DOCFIT_KIMI_API_KEY": "process-key",
                "DOCFIT_KIMI_MODEL": "process-model",
            },
            env_file=env_file,
        )
    )

    assert backend.api_key == "process-key"
    assert backend.model == "process-model"


def test_sdk_environment_uses_anthropic_compatible_variables_without_repr_leak() -> None:
    backend = next(
        iter_agent_backends(
            {
                "DOCFIT_AGENT_BACKEND_ORDER": "minimax",
                "DOCFIT_MINIMAX_API_KEY": "secret-value",
            }
        )
    )

    sdk_env = backend.sdk_environment()

    assert sdk_env["ANTHROPIC_API_KEY"] == "secret-value"
    assert sdk_env["ANTHROPIC_BASE_URL"] == "https://api.minimaxi.com/anthropic/"
    assert sdk_env["ANTHROPIC_MODEL"] == "MiniMax-M3"
    assert sdk_env["ENABLE_TOOL_SEARCH"] == "false"
    assert "secret-value" not in repr(backend)


def test_invalid_backend_order_is_rejected() -> None:
    with pytest.raises(AgentConfigurationError, match="unsupported"):
        tuple(
            iter_agent_backends(
                {
                    "DOCFIT_AGENT_BACKEND_ORDER": "kimi,unknown",
                    "DOCFIT_KIMI_API_KEY": "test",
                }
            )
        )


def test_invalid_context_window_is_a_configuration_error() -> None:
    with pytest.raises(AgentConfigurationError, match="must be an integer"):
        tuple(
            iter_agent_backends(
                {
                    "DOCFIT_KIMI_API_KEY": "test",
                    "DOCFIT_KIMI_CONTEXT_TOKENS": "many",
                }
            )
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are required")
def test_env_file_must_be_exactly_mode_0600(tmp_path: Path) -> None:
    env_file = tmp_path / "agent.env"
    env_file.write_text("DOCFIT_KIMI_API_KEY=test\n", encoding="utf-8")
    env_file.chmod(0o644)

    assert not agent_env_file_is_private(env_file)

    env_file.chmod(0o600)
    assert agent_env_file_is_private(env_file)
