from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.agent import (
    BUILTIN_TOOLS,
    DIRECTORY_POLICY,
    FORBIDDEN_TOOLS,
    LOGGING_POLICY,
    SKILL_NAME,
    build_agent_options,
    make_permission_callback,
)
from docfit.tools import FULL_TOOL_NAMES


def test_options_expose_only_two_builtins_and_one_five_tool_server(tmp_path: Path) -> None:
    options = build_agent_options(
        cwd=tmp_path,
        agent_env={"ANTHROPIC_BASE_URL": "https://example.invalid/"},
        model="test-model",
    )

    assert tuple(options.tools or ()) == BUILTIN_TOOLS
    assert tuple(options.allowed_tools) == FULL_TOOL_NAMES
    assert set(options.disallowed_tools) == set(FORBIDDEN_TOOLS)
    assert isinstance(options.mcp_servers, dict)
    assert tuple(options.mcp_servers) == ("docfit",)
    assert options.strict_mcp_config is True
    assert options.permission_mode == "default"
    assert options.setting_sources == ["project"]
    assert options.skills == [SKILL_NAME]
    assert options.env == {"ANTHROPIC_BASE_URL": "https://example.invalid/"}
    assert options.model == "test-model"
    assert DIRECTORY_POLICY == (
        "input_read_only",
        "work_writable",
        "output_writable",
        "outside_task_denied",
    )
    assert LOGGING_POLICY == "metadata_only_no_document_body"


def test_skill_and_five_docfit_tools_are_approved_if_callback_is_consulted() -> None:
    async def ask_user(_: str) -> str:
        raise AssertionError("DocFit Tool approval must not ask the CLI")

    callback = make_permission_callback(ask_user)
    context = ToolPermissionContext()

    for tool_name in ("Skill", *FULL_TOOL_NAMES):
        result = asyncio.run(callback(tool_name, {}, context))
        assert isinstance(result, PermissionResultAllow)


def test_ask_user_question_is_forwarded_to_cli_input() -> None:
    prompts: list[str] = []

    async def ask_user(prompt: str) -> str:
        prompts.append(prompt)
        return "continue-m0"

    callback = make_permission_callback(ask_user)
    tool_input = {
        "questions": [
            {
                "header": "M0",
                "question": "Continue token?",
                "options": [{"label": "Yes", "description": "Continue the same session."}],
            }
        ]
    }

    result = asyncio.run(callback("AskUserQuestion", tool_input, ToolPermissionContext()))

    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input == {
        **tool_input,
        "answers": {"Continue token?": "continue-m0"},
    }
    assert prompts and "Continue token?" in prompts[0]


def test_unmatched_tools_are_denied() -> None:
    async def ask_user(_: str) -> str:
        return "unused"

    callback = make_permission_callback(ask_user)

    for tool_name in (
        "Bash",
        "Write",
        "Edit",
        "Web",
        "WebSearch",
        "WebFetch",
        "mcp__docfit__unknown",
    ):
        result = asyncio.run(callback(tool_name, {}, ToolPermissionContext()))
        assert isinstance(result, PermissionResultDeny)
        assert "denies unmatched tool" in result.message
