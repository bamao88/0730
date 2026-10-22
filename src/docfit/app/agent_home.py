"""Isolated working directory for product Agents.

The Claude Code CLI discovers ``CLAUDE.md`` and ``.claude/skills`` from the
working directory and every ancestor directory. Product Agents therefore must
not run inside the development repository: its ``CLAUDE.md`` imports the
developer ``AGENTS.md`` guide, and its ``.claude/skills`` contains development
Skills. The product Agent home lives outside the repository tree and holds
only a copy of the Skills that Agent is configured to use.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path

AGENT_HOME_BASE_ENV = "DOCFIT_AGENT_HOME_BASE"
AGENT_HOME_DIRECTORY = "docfit-agent-home"
_COMPLETE_MARKER = ".docfit-agent-home-complete"
# Names the CLI picks up from an ancestor directory as project context.
_ANCESTOR_CONTEXT_NAMES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", ".claude")


class AgentHomeIsolationError(RuntimeError):
    """The product Agent home could inherit development context."""


def prepare_agent_home(
    skill_names: Sequence[str],
    *,
    project: Path,
    base: Path | None = None,
) -> Path:
    """Return an isolated cwd containing only ``skill_names`` under ``.claude/skills``.

    The directory name carries a content hash of the copied Skills, so edits
    to a Skill produce a new home and concurrent runs never share a partial copy.
    """

    if not skill_names:
        raise ValueError("A product Agent home needs at least one Skill.")
    source_root = project.expanduser().resolve(strict=True) / ".claude" / "skills"
    sources = [_skill_source(source_root, name) for name in dict.fromkeys(skill_names)]
    digest = _skills_digest(sources)
    base_path = _agent_home_base(base)
    home = base_path / f"{'+'.join(path.name for path in sources)}-{digest[:16]}"
    assert_isolated_agent_home(home, project=project)
    if (home / _COMPLETE_MARKER).is_file():
        return home
    base_path.mkdir(parents=True, exist_ok=True)
    staging = base_path / f".staging-{uuid.uuid4().hex}"
    try:
        for source in sources:
            shutil.copytree(source, staging / ".claude" / "skills" / source.name)
        (staging / _COMPLETE_MARKER).write_text(digest + "\n", encoding="utf-8")
        try:
            staging.rename(home)
        except OSError:
            # Another run published the same content first.
            if not (home / _COMPLETE_MARKER).is_file():
                raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return home


def assert_isolated_agent_home(home: Path, *, project: Path) -> None:
    """Reject a home that the CLI would join to the repository or other project context."""

    home_path = home.expanduser().resolve(strict=False)
    project_path = project.expanduser().resolve(strict=False)
    if home_path == project_path or project_path in home_path.parents:
        raise AgentHomeIsolationError(
            f"Product Agent home {home_path} is inside the development repository "
            f"{project_path}; the CLI would load its CLAUDE.md and Skills."
        )
    for ancestor in home_path.parents:
        for name in _ANCESTOR_CONTEXT_NAMES:
            if (ancestor / name).exists():
                raise AgentHomeIsolationError(
                    f"Product Agent home {home_path} has project context in ancestor "
                    f"{ancestor / name}; choose another {AGENT_HOME_BASE_ENV}."
                )


def _agent_home_base(base: Path | None) -> Path:
    if base is not None:
        return base.expanduser().resolve(strict=False)
    configured = os.environ.get(AGENT_HOME_BASE_ENV)
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    return Path(tempfile.gettempdir()).resolve(strict=False) / AGENT_HOME_DIRECTORY


def _skill_source(source_root: Path, name: str) -> Path:
    source = source_root / name
    if source.is_symlink() or not (source / "SKILL.md").is_file():
        raise FileNotFoundError(f"Product Skill {name!r} is missing from {source_root}.")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Product Skill {name!r} must not contain symlinks: {path}.")
    return source


def _skills_digest(sources: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for source in sources:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source.parent).as_posix()
            digest.update(relative.encode("utf-8") + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()
