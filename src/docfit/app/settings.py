"""Local Agent backend configuration without leaking credentials into the repo."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

BackendName = Literal["kimi", "minimax"]

DEFAULT_BACKEND_ORDER = ("kimi", "minimax")
DEFAULT_KIMI_BASE_URL = "https://api.kimi.com/coding/"
DEFAULT_KIMI_MODEL = "kimi-for-coding"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MINIMAX_MODEL = "MiniMax-M3"

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BACKEND_KEY_NAMES: dict[BackendName, tuple[str, ...]] = {
    "kimi": (
        "DOCFIT_KIMI_API_KEY",
        "DOCFIT_KIMI_API_KEY_2",
        "DOCFIT_KIMI_API_KEY_BACKUP",
    ),
    "minimax": ("DOCFIT_MINIMAX_API_KEY",),
}


class AgentConfigurationError(ValueError):
    """Raised when the local Agent environment file is structurally invalid."""


@dataclass(frozen=True)
class AgentBackend:
    """One concrete backend credential candidate for a live SDK session."""

    name: BackendName
    base_url: str
    model: str
    credential_variable: str
    api_key: str = field(repr=False)
    context_tokens: int = 262_144

    def sdk_environment(self) -> dict[str, str]:
        """Map the selected backend to Claude Code's Anthropic-compatible env."""
        model = self.model
        return {
            "ANTHROPIC_BASE_URL": self.base_url,
            "ANTHROPIC_API_KEY": self.api_key,
            "ANTHROPIC_AUTH_TOKEN": "",
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_DEFAULT_FABLE_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "CLAUDE_CODE_SUBAGENT_MODEL": model,
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(self.context_tokens),
            "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(self.context_tokens),
            "ENABLE_TOOL_SEARCH": "false",
            "CLAUDE_AGENT_SDK_CLIENT_APP": "docfit/0.1.0",
        }


def default_agent_env_file() -> Path:
    return Path.home() / ".config" / "docfit" / "agent.env"


def resolve_agent_env_file(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    configured = env.get("DOCFIT_ENV_FILE")
    return Path(configured).expanduser() if configured else default_agent_env_file()


def read_agent_env_file(path: Path) -> dict[str, str]:
    """Parse a small dotenv-compatible file without shell evaluation or expansion."""
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise AgentConfigurationError(
                f"{path}:{line_number}: expected NAME=VALUE"
            )
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not _ENV_NAME.fullmatch(name):
            raise AgentConfigurationError(
                f"{path}:{line_number}: invalid environment variable name"
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def merged_agent_environment(
    environment: Mapping[str, str] | None = None,
    *,
    env_file: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
    """Load the shared file, then apply process overrides without mutating os.environ."""
    explicit_environment = environment is not None
    process_values = dict(os.environ if environment is None else environment)
    selected_file = env_file
    if selected_file is None and (
        not explicit_environment or process_values.get("DOCFIT_ENV_FILE")
    ):
        selected_file = resolve_agent_env_file(process_values)

    merged = read_agent_env_file(selected_file) if selected_file is not None else {}
    merged.update(process_values)
    return merged, selected_file


def backend_order(values: Mapping[str, str]) -> tuple[BackendName, ...]:
    raw_order = values.get("DOCFIT_AGENT_BACKEND_ORDER", ",".join(DEFAULT_BACKEND_ORDER))
    names = tuple(part.strip().casefold() for part in raw_order.split(",") if part.strip())
    if not names:
        raise AgentConfigurationError("DOCFIT_AGENT_BACKEND_ORDER cannot be empty")
    unknown = tuple(name for name in names if name not in DEFAULT_BACKEND_ORDER)
    if unknown:
        raise AgentConfigurationError(
            "DOCFIT_AGENT_BACKEND_ORDER contains unsupported names: "
            + ", ".join(unknown)
        )
    if len(set(names)) != len(names):
        raise AgentConfigurationError("DOCFIT_AGENT_BACKEND_ORDER contains duplicates")
    return cast(tuple[BackendName, ...], names)


def _backend_metadata(
    name: BackendName,
    values: Mapping[str, str],
) -> tuple[str, str, int]:
    variable = f"DOCFIT_{name.upper()}_CONTEXT_TOKENS"
    raw_context_tokens = values.get(variable, "262144")
    try:
        context_tokens = int(raw_context_tokens)
    except ValueError as error:
        raise AgentConfigurationError(f"{variable} must be an integer") from error
    if name == "kimi":
        return (
            values.get("DOCFIT_KIMI_BASE_URL", DEFAULT_KIMI_BASE_URL),
            values.get("DOCFIT_KIMI_MODEL", DEFAULT_KIMI_MODEL),
            context_tokens,
        )
    return (
        values.get("DOCFIT_MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL),
        values.get("DOCFIT_MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL),
        context_tokens,
    )


def iter_agent_backends(
    environment: Mapping[str, str] | None = None,
    *,
    env_file: Path | None = None,
) -> Iterator[AgentBackend]:
    """Yield configured credentials in backend priority and key-rotation order."""
    values, _ = merged_agent_environment(environment, env_file=env_file)
    seen_secrets: set[str] = set()
    for name in backend_order(values):
        base_url, model, context_tokens = _backend_metadata(name, values)
        if context_tokens <= 0:
            raise AgentConfigurationError(
                f"DOCFIT_{name.upper()}_CONTEXT_TOKENS must be positive"
            )
        for key_name in _BACKEND_KEY_NAMES[name]:
            api_key = values.get(key_name, "").strip()
            if not api_key or api_key in seen_secrets:
                continue
            seen_secrets.add(api_key)
            yield AgentBackend(
                name=name,
                base_url=base_url.rstrip("/") + "/",
                model=model,
                credential_variable=key_name,
                api_key=api_key,
                context_tokens=context_tokens,
            )


def configured_backend_names(
    environment: Mapping[str, str] | None = None,
    *,
    env_file: Path | None = None,
) -> tuple[BackendName, ...]:
    return tuple(dict.fromkeys(backend.name for backend in iter_agent_backends(
        environment,
        env_file=env_file,
    )))


def agent_env_file_is_private(path: Path) -> bool:
    if not path.is_file():
        return False
    return stat.S_IMODE(path.stat().st_mode) == 0o600


def redact_secrets(message: str, backends: tuple[AgentBackend, ...]) -> str:
    redacted = message
    for backend in backends:
        redacted = redacted.replace(backend.api_key, "<redacted>")
    return redacted
