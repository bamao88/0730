"""Claude Agent SDK configuration and permission boundary."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, HookMatcher
from claude_agent_sdk.types import (
    CanUseTool,
    HookContext,
    HookInput,
    HookJSONOutput,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.tools import FULL_TOOL_NAMES, MCP_SERVER_NAME, build_docfit_server

BUILTIN_TOOLS = ("Skill", "AskUserQuestion", "Agent")
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
SKILL_NAMES = ("docfit-school-extract", "convert-thesis")
SUBAGENT_NAME = "docfit-unit-analyst"
READ_ONLY_SUBAGENT_TOOLS = (
    "mcp__docfit__docx_inspect",
    "mcp__docfit__docx_visual_review",
)
UNIT_ANALYSIS_REQUIRED_FIELDS = (
    "status",
    "confidence",
    "findings",
    "confirmed_rules",
    "uncertainties",
    "dependencies",
    "cross_unit_links",
    "evidence_requests",
    "proposed_operations",
)
DIRECTORY_POLICY = (
    "input_read_only",
    "work_writable",
    "output_writable",
    "outside_task_denied",
)
LOGGING_POLICY = "metadata_only_no_document_body"
AGENT_SDK_MAX_BUFFER_BYTES = 16 * 1024 * 1024
AskUser = Callable[[str], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class PermissionAuditEvent:
    tool_name: str
    decision: str
    subagent_type: str | None = None
    tool_use_id: str | None = None
    agent_id: str | None = None
    reason_code: str = "permission_policy"
    question_count: int | None = None
    option_count: int | None = None
    answered: bool | None = None
    duration_ms: float | None = None


PermissionAudit = Callable[[PermissionAuditEvent], None]
ObservationHook = Callable[
    [HookInput, str | None, HookContext],
    Awaitable[HookJSONOutput],
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def build_unit_analyst_definition() -> AgentDefinition:
    return AgentDefinition(
        description=("Read-only DocFit analyst for one explicitly bounded thesis evidence scope."),
        prompt=(
            "Analyze only the explicit scope, selected universal Knowledge modules, and "
            "task evidence in the parent prompt. You do not inherit other parent context. "
            "Use only docx_inspect and docx_visual_review. Never render, edit, validate, "
            "ask the user, call another Agent, or persist memory. If evidence is missing, "
            "return needs_more_evidence with evidence_requests. Return unit_analysis_v1 "
            "with status, confidence, findings, confirmed_rules, uncertainties, "
            "dependencies, cross_unit_links, evidence_requests, and proposed_operations. "
            "Proposed operations are analysis only and never authorize a write."
        ),
        tools=list(READ_ONLY_SUBAGENT_TOOLS),
        disallowedTools=[
            "Agent",
            "Skill",
            "AskUserQuestion",
            "mcp__docfit__docx_edit",
            "mcp__docfit__docx_render",
            "mcp__docfit__docx_validate",
        ],
        model="inherit",
        skills=[],
        memory=None,
        mcpServers=[MCP_SERVER_NAME],
        maxTurns=6,
        background=False,
        permissionMode="dontAsk",
    )


def make_agent_gate_hook(
    audit: PermissionAudit | None = None,
) -> Callable[[HookInput, str | None, HookContext], Awaitable[HookJSONOutput]]:
    async def gate_agent(
        hook_input: HookInput,
        tool_use_id: str | None,
        _context: HookContext,
    ) -> HookJSONOutput:
        if hook_input["hook_event_name"] != "PreToolUse":
            return {}
        pre_tool_input = hook_input
        if pre_tool_input["tool_name"] != "Agent":
            return {}

        subagent_type = pre_tool_input["tool_input"].get("subagent_type")
        normalized_type = subagent_type if isinstance(subagent_type, str) else None
        allowed = normalized_type == SUBAGENT_NAME
        if audit is not None:
            audit(
                PermissionAuditEvent(
                    "Agent",
                    "allow" if allowed else "deny",
                    normalized_type,
                    tool_use_id,
                    hook_input.get("agent_id"),
                    "subagent_type_allowed" if allowed else "subagent_type_denied",
                )
            )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if allowed else "deny",
                "permissionDecisionReason": (
                    "DocFit permits only the read-only docfit-unit-analyst subagent type."
                ),
            }
        }

    return gate_agent


def make_permission_callback(
    ask_user: AskUser,
    *,
    audit: PermissionAudit | None = None,
) -> CanUseTool:
    def record(event: PermissionAuditEvent) -> None:
        if audit is not None:
            audit(event)

    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name == "Skill" or tool_name in FULL_TOOL_NAMES:
            record(
                PermissionAuditEvent(
                    tool_name,
                    "allow",
                    tool_use_id=context.tool_use_id,
                    agent_id=context.agent_id,
                    reason_code="registered_tool_allowed",
                )
            )
            return PermissionResultAllow()
        if tool_name == "Agent":
            subagent_type = tool_input.get("subagent_type")
            if subagent_type == SUBAGENT_NAME:
                record(
                    PermissionAuditEvent(
                        tool_name,
                        "allow",
                        SUBAGENT_NAME,
                        context.tool_use_id,
                        context.agent_id,
                        "subagent_type_allowed",
                    )
                )
                return PermissionResultAllow()
            normalized_type = subagent_type if isinstance(subagent_type, str) else None
            record(
                PermissionAuditEvent(
                    tool_name,
                    "deny",
                    normalized_type,
                    context.tool_use_id,
                    context.agent_id,
                    "subagent_type_denied",
                )
            )
            return PermissionResultDeny(
                message=("DocFit permits only the read-only docfit-unit-analyst subagent type."),
                interrupt=False,
            )
        if tool_name != "AskUserQuestion":
            record(
                PermissionAuditEvent(
                    tool_name,
                    "deny",
                    tool_use_id=context.tool_use_id,
                    agent_id=context.agent_id,
                    reason_code="unmatched_tool_denied",
                )
            )
            return PermissionResultDeny(
                message=f"DocFit denies unmatched tool: {tool_name}",
                interrupt=False,
            )

        questions = tool_input.get("questions")
        if not isinstance(questions, list) or not questions:
            record(
                PermissionAuditEvent(
                    tool_name,
                    "deny",
                    tool_use_id=context.tool_use_id,
                    agent_id=context.agent_id,
                    reason_code="question_shape_invalid",
                )
            )
            return PermissionResultDeny(
                message="AskUserQuestion requires a non-empty questions list.",
                interrupt=False,
            )
        answers: dict[str, str] = {}
        option_count = sum(
            len(question.get("options", ()))
            for question in questions
            if isinstance(question, dict) and isinstance(question.get("options"), list)
        )
        started = time.perf_counter()
        for question in questions:
            if not isinstance(question, dict):
                record(
                    PermissionAuditEvent(
                        tool_name,
                        "deny",
                        tool_use_id=context.tool_use_id,
                        agent_id=context.agent_id,
                        reason_code="question_shape_invalid",
                        question_count=len(questions),
                        option_count=option_count,
                        answered=False,
                    )
                )
                return PermissionResultDeny(
                    message="AskUserQuestion contains an invalid question.",
                    interrupt=False,
                )
            question_text = question.get("question")
            if not isinstance(question_text, str) or not question_text:
                record(
                    PermissionAuditEvent(
                        tool_name,
                        "deny",
                        tool_use_id=context.tool_use_id,
                        agent_id=context.agent_id,
                        reason_code="question_text_missing",
                        question_count=len(questions),
                        option_count=option_count,
                        answered=False,
                    )
                )
                return PermissionResultDeny(
                    message="AskUserQuestion question text is missing.",
                    interrupt=False,
                )
            answers[question_text] = await ask_user(_question_prompt(question))
        updated_input = dict(tool_input)
        updated_input["answers"] = answers
        record(
            PermissionAuditEvent(
                tool_name,
                "allow",
                tool_use_id=context.tool_use_id,
                agent_id=context.agent_id,
                reason_code="ask_user_answered",
                question_count=len(questions),
                option_count=option_count,
                answered=True,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        )
        return PermissionResultAllow(updated_input=updated_input)

    return can_use_tool


def build_agent_options(
    ask_user: AskUser = terminal_ask_user,
    *,
    cwd: Path | None = None,
    agent_env: Mapping[str, str] | None = None,
    model: str | None = None,
    permission_audit: PermissionAudit | None = None,
    observation_hook: ObservationHook | None = None,
    system_prompt: str | None = None,
    output_format: dict[str, Any] | None = None,
    max_turns: int = 12,
) -> ClaudeAgentOptions:
    root = cwd or project_root()
    configured_hooks: dict[str, list[HookMatcher]] = {
        "PreToolUse": [
            HookMatcher(
                matcher="Agent",
                hooks=[make_agent_gate_hook(permission_audit)],
            )
        ]
    }
    if observation_hook is not None:
        configured_hooks["PreToolUse"].insert(
            0,
            HookMatcher(matcher=None, hooks=[observation_hook]),
        )
        for event_name in (
            "PostToolUse",
            "PostToolUseFailure",
            "SubagentStart",
            "SubagentStop",
        ):
            configured_hooks[event_name] = [
                HookMatcher(matcher=None, hooks=[observation_hook])
            ]
    return ClaudeAgentOptions(
        tools=list(BUILTIN_TOOLS),
        allowed_tools=list(FULL_TOOL_NAMES),
        disallowed_tools=list(FORBIDDEN_TOOLS),
        mcp_servers={MCP_SERVER_NAME: build_docfit_server()},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(ask_user, audit=permission_audit),
        hooks=configured_hooks,  # type: ignore[arg-type]
        agents={SUBAGENT_NAME: build_unit_analyst_definition()},
        setting_sources=["project"],
        skills=list(SKILL_NAMES),
        cwd=root,
        env=dict(agent_env or {}),
        model=model,
        max_turns=max_turns,
        max_buffer_size=AGENT_SDK_MAX_BUFFER_BYTES,
        output_format=output_format,
        system_prompt=system_prompt
        or (
            "You are running the DocFit M1 Tool harness. The five DocFit Tools provide "
            "real, permission-bounded DOCX inspection, editing, rendering, visual evidence, "
            "and independent validation. Use only the two enabled domain Skills, the five "
            "registered DocFit MCP tools, and the type-gated read-only docfit-unit-analyst. "
            "Interpret Tool results yourself; the application shell does not choose Knowledge, "
            "delegate scopes, or interpret needs_input. Never treat approximate OfficeCLI "
            "rendering as Adobe delivery conversion evidence, and never consume an error or "
            "committed=false "
            "output."
        ),
    )
