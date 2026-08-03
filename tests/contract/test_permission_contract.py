from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.app.agent import (
    AGENT_SDK_MAX_BUFFER_BYTES,
    BUILTIN_TOOLS,
    DIRECTORY_POLICY,
    FORBIDDEN_TOOLS,
    LOGGING_POLICY,
    READ_ONLY_SUBAGENT_TOOLS,
    SKILL_NAMES,
    SUBAGENT_NAME,
    PermissionAuditEvent,
    build_agent_options,
    build_unit_analyst_definition,
    make_agent_gate_hook,
    make_permission_callback,
)
from docfit.tools import FULL_TOOL_NAMES


def test_options_expose_three_builtins_and_one_five_tool_server(tmp_path: Path) -> None:
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
    assert options.skills == list(SKILL_NAMES)
    assert options.agents is not None
    assert tuple(options.agents) == (SUBAGENT_NAME,)
    assert options.agents[SUBAGENT_NAME] == build_unit_analyst_definition()
    assert options.hooks is not None
    assert tuple(options.hooks) == ("PreToolUse",)
    assert len(options.hooks["PreToolUse"]) == 1
    assert options.hooks["PreToolUse"][0].matcher == "Agent"
    assert options.env == {"ANTHROPIC_BASE_URL": "https://example.invalid/"}
    assert options.model == "test-model"
    assert options.max_buffer_size == AGENT_SDK_MAX_BUFFER_BYTES
    assert options.max_buffer_size >= 16 * 1024 * 1024
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


def test_only_named_read_only_subagent_is_approved() -> None:
    async def ask_user(_: str) -> str:
        raise AssertionError("Agent approval must not ask the CLI")

    events: list[PermissionAuditEvent] = []
    callback = make_permission_callback(ask_user, audit=events.append)
    context = ToolPermissionContext()

    allowed = asyncio.run(
        callback("Agent", {"subagent_type": SUBAGENT_NAME, "prompt": "bounded"}, context)
    )
    assert isinstance(allowed, PermissionResultAllow)

    for subagent_type in ("general-purpose", "unknown-agent", None):
        denied = asyncio.run(
            callback("Agent", {"subagent_type": subagent_type}, context)
        )
        assert isinstance(denied, PermissionResultDeny)
        assert SUBAGENT_NAME in denied.message

    assert events == [
        PermissionAuditEvent("Agent", "allow", SUBAGENT_NAME),
        PermissionAuditEvent("Agent", "deny", "general-purpose"),
        PermissionAuditEvent("Agent", "deny", "unknown-agent"),
        PermissionAuditEvent("Agent", "deny", None),
    ]


def test_unit_analyst_definition_has_only_two_read_only_tools() -> None:
    definition = build_unit_analyst_definition()

    assert tuple(definition.tools or ()) == READ_ONLY_SUBAGENT_TOOLS
    assert definition.skills == []
    assert definition.memory is None
    assert definition.mcpServers == ["docfit"]
    assert definition.permissionMode == "dontAsk"
    assert set(definition.disallowedTools or ()) >= {
        "Agent",
        "Skill",
        "AskUserQuestion",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_validate",
    }


def test_agent_pre_tool_hook_allows_only_named_subagent() -> None:
    events: list[PermissionAuditEvent] = []
    hook = make_agent_gate_hook(events.append)
    context = {"signal": None}

    allowed = asyncio.run(
        hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session",
                "transcript_path": "/tmp/transcript",
                "cwd": "/tmp",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": SUBAGENT_NAME},
                "tool_use_id": "allowed",
            },
            "allowed",
            context,
        )
    )
    assert allowed["hookSpecificOutput"]["permissionDecision"] == "allow"

    for subagent_type in ("general-purpose", "unknown-agent", None):
        denied = asyncio.run(
            hook(
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session",
                    "transcript_path": "/tmp/transcript",
                    "cwd": "/tmp",
                    "tool_name": "Agent",
                    "tool_input": {"subagent_type": subagent_type},
                    "tool_use_id": "denied",
                },
                "denied",
                context,
            )
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    assert events == [
        PermissionAuditEvent("Agent", "allow", SUBAGENT_NAME),
        PermissionAuditEvent("Agent", "deny", "general-purpose"),
        PermissionAuditEvent("Agent", "deny", "unknown-agent"),
        PermissionAuditEvent("Agent", "deny", None),
    ]


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
