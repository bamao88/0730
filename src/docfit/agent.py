"""Claude Agent SDK configuration and permission boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import (
    CanUseTool,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.tools import FULL_TOOL_NAMES, MCP_SERVER_NAME, build_docfit_server

BUILTIN_TOOLS = ("Skill", "AskUserQuestion")
FORBIDDEN_TOOLS = (
    "Bash",
    "Write",
    "Edit",
    "Read",
    "Glob",
    "Grep",
    "Web",
    "WebSearch",
    "WebFetch",
)
SKILL_NAME = "convert-thesis"
DIRECTORY_POLICY = (
    "input_read_only",
    "work_writable",
    "output_writable",
    "outside_task_denied",
)
LOGGING_POLICY = "metadata_only_no_document_body"
AskUser = Callable[[str], Awaitable[str]]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


async def terminal_ask_user(prompt: str) -> str:
    return await asyncio.to_thread(input, f"{prompt}\n> ")


def _question_prompt(question: dict[str, Any]) -> str:
    header = question.get("header")
    text = question.get("question")
    options = question.get("options")
    lines = [str(value) for value in (header, text) if value]
    if isinstance(options, list):
        for index, option in enumerate(options, start=1):
            if isinstance(option, dict):
                label = option.get("label", "")
                description = option.get("description", "")
                lines.append(f"{index}. {label} — {description}".rstrip(" —"))
    return "\n".join(lines) or "Agent needs input"


def make_permission_callback(ask_user: AskUser) -> CanUseTool:
    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        _context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name == "Skill" or tool_name in FULL_TOOL_NAMES:
            return PermissionResultAllow()
        if tool_name != "AskUserQuestion":
            return PermissionResultDeny(
                message=f"DocFit M0 denies unmatched tool: {tool_name}",
                interrupt=False,
            )

        questions = tool_input.get("questions")
        if not isinstance(questions, list) or not questions:
            return PermissionResultDeny(
                message="AskUserQuestion requires a non-empty questions list.",
                interrupt=False,
            )
        answers: dict[str, str] = {}
        for question in questions:
            if not isinstance(question, dict):
                return PermissionResultDeny(
                    message="AskUserQuestion contains an invalid question.",
                    interrupt=False,
                )
            question_text = question.get("question")
            if not isinstance(question_text, str) or not question_text:
                return PermissionResultDeny(
                    message="AskUserQuestion question text is missing.",
                    interrupt=False,
                )
            answers[question_text] = await ask_user(_question_prompt(question))
        updated_input = dict(tool_input)
        updated_input["answers"] = answers
        return PermissionResultAllow(updated_input=updated_input)

    return can_use_tool


def build_agent_options(
    ask_user: AskUser = terminal_ask_user,
    *,
    cwd: Path | None = None,
    agent_env: Mapping[str, str] | None = None,
    model: str | None = None,
) -> ClaudeAgentOptions:
    root = cwd or project_root()
    return ClaudeAgentOptions(
        tools=list(BUILTIN_TOOLS),
        allowed_tools=list(FULL_TOOL_NAMES),
        disallowed_tools=list(FORBIDDEN_TOOLS),
        mcp_servers={MCP_SERVER_NAME: build_docfit_server()},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(ask_user),
        setting_sources=["project"],
        skills=[SKILL_NAME],
        cwd=root,
        env=dict(agent_env or {}),
        model=model,
        max_turns=8,
        system_prompt=(
            "You are running the DocFit M0 smoke harness. Never claim that real DOCX "
            "inspection, editing, rendering, review, or validation exists. Use only the "
            "visible built-ins and the five registered DocFit MCP tools. Interpret Tool "
            "results yourself; the application shell does not interpret needs_input."
        ),
    )
