"""Shared repository-external configuration loading for DocFit runtimes."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigurationError(ValueError):
    """Raised when the shared local environment file is structurally invalid."""


def default_env_file() -> Path:
    return Path.home() / ".config" / "docfit" / "agent.env"


def resolve_env_file(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    configured = env.get("DOCFIT_ENV_FILE")
    return Path(configured).expanduser() if configured else default_env_file()


def read_env_file(path: Path) -> dict[str, str]:
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
            raise ConfigurationError(f"{path}:{line_number}: expected NAME=VALUE")
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not _ENV_NAME.fullmatch(name):
            raise ConfigurationError(
                f"{path}:{line_number}: invalid environment variable name"
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def merged_environment(
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
        selected_file = resolve_env_file(process_values)

    merged = read_env_file(selected_file) if selected_file is not None else {}
    merged.update(process_values)
    return merged, selected_file


def env_file_is_private(path: Path) -> bool:
    if not path.is_file():
        return False
    return stat.S_IMODE(path.stat().st_mode) == 0o600
