"""Product Agents must not inherit the development repository's CLAUDE.md, AGENTS.md or Skills."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from docfit.app.agent import build_agent_options, project_root
from docfit.app.agent_home import (
    AgentHomeIsolationError,
    assert_isolated_agent_home,
    prepare_agent_home,
)

ROOT = project_root()


def _project_with_skills(root: Path) -> Path:
    for name in ("docfit-school-extract", "docfit-dev-only"):
        skill = root / ".claude" / "skills" / name
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        (skill / "references" / "note.md").write_text("note\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    return root


def test_home_holds_only_requested_skills_and_is_content_addressed(tmp_path: Path) -> None:
    project = _project_with_skills(tmp_path / "repo")
    base = tmp_path / "homes"

    home = prepare_agent_home(("docfit-school-extract",), project=project, base=base)

    assert sorted(path.name for path in (home / ".claude" / "skills").iterdir()) == [
        "docfit-school-extract"
    ]
    assert (home / ".claude/skills/docfit-school-extract/references/note.md").is_file()
    assert not (home / "CLAUDE.md").exists()
    assert prepare_agent_home(("docfit-school-extract",), project=project, base=base) == home

    (project / ".claude/skills/docfit-school-extract/SKILL.md").write_text("# v2\n")
    updated = prepare_agent_home(("docfit-school-extract",), project=project, base=base)
    assert updated != home
    assert (updated / ".claude/skills/docfit-school-extract/SKILL.md").read_text() == "# v2\n"


def test_home_inside_repository_is_rejected(tmp_path: Path) -> None:
    project = _project_with_skills(tmp_path / "repo")

    with pytest.raises(AgentHomeIsolationError, match="inside the development repository"):
        prepare_agent_home(("docfit-school-extract",), project=project, base=project / "temp")


def test_home_below_other_project_context_is_rejected(tmp_path: Path) -> None:
    project = _project_with_skills(tmp_path / "repo")
    other = tmp_path / "other"
    other.mkdir()
    (other / "CLAUDE.md").write_text("developer notes\n", encoding="utf-8")

    with pytest.raises(AgentHomeIsolationError, match="ancestor"):
        prepare_agent_home(("docfit-school-extract",), project=project, base=other / "homes")


def test_product_agent_options_run_outside_the_repository() -> None:
    options = build_agent_options()

    cwd = Path(str(options.cwd))
    assert_isolated_agent_home(cwd, project=ROOT)
    assert sorted(path.name for path in (cwd / ".claude" / "skills").iterdir()) == [
        "convert-thesis"
    ]
    assert options.setting_sources == ["project"]


def test_cli_loads_no_repository_memory_files_in_agent_home() -> None:
    """Ask the bundled CLI what it actually loaded; no model request is sent."""

    home = prepare_agent_home(("docfit-school-extract",), project=ROOT)

    async def loaded_context() -> tuple[list[str], list[str]]:
        options = ClaudeAgentOptions(
            setting_sources=["project"],
            skills=["docfit-school-extract"],
            cwd=home,
            tools=[],
            max_turns=1,
        )
        async with ClaudeSDKClient(options=options) as client:
            usage = await client.get_context_usage()
            info = await client.get_server_info() or {}
        memory = [str(item.get("path")) for item in usage.get("memoryFiles", [])]
        commands = [str(item.get("name")) for item in info.get("commands", [])]
        return memory, commands

    memory, commands = asyncio.run(loaded_context())

    assert memory == []
    assert "docfit-school-extract" in commands
    assert "docfit-gold-word-review" not in commands
    assert "convert-thesis" not in commands
