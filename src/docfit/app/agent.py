"""Claude Agent SDK configuration and permission boundary."""

from __future__ import annotations

import asyncio
import os
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
    PreToolUseHookSpecificOutput,
    ToolPermissionContext,
)

from docfit.tools import FULL_TOOL_NAMES, MCP_SERVER_NAME, build_docfit_server

READ_ONLY_BUILTIN_TOOLS = ("Read", "Glob", "Grep")
TRUSTED_BASIC_TOOLS = ("Bash", "Write")
BUILTIN_TOOLS = (
    "Skill",
    *READ_ONLY_BUILTIN_TOOLS,
    *TRUSTED_BASIC_TOOLS,
    "AskUserQuestion",
    "Agent",
)
FORBIDDEN_TOOLS = (
    "Edit",
    "Web",
    "WebSearch",
    "WebFetch",
)
AUTO_APPROVED_TOOL_NAMES = (*FULL_TOOL_NAMES, *TRUSTED_BASIC_TOOLS)
SKILL_NAMES = ("docfit-school-extract", "convert-thesis")
SUBAGENT_NAME = "docfit-unit-analyst"
READ_ONLY_SUBAGENT_TOOLS = (
    "mcp__docfit__docx_inspect",
    "mcp__docfit__docx_visual_review",
)
MAIN_AGENT_READ_POLICY = (
    "project_skill_references_read_only",
    "product_knowledge_package_read_only",
    "current_task_input_read_only",
    "current_task_work_read_only",
    "current_task_output_read_only",
    "realpath_before_authorization",
    "sensitive_outside_and_symlink_escape_denied",
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

_SENSITIVE_DIRECTORY_NAMES = {".git", ".config"}
_SENSITIVE_FILE_NAMES = {
    ".env",
    "agent.env",
    "credentials",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "secret",
    "secret.json",
    "secrets",
    "secrets.json",
}


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


@dataclass(frozen=True, slots=True)
class ReadPathRoot:
    label: str
    path: Path


@dataclass(frozen=True, slots=True)
class ReadPathDecision:
    allowed: bool
    reason_code: str
    updated_input: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ReadPathPolicy:
    cwd: Path
    roots: tuple[ReadPathRoot, ...]

    def authorize(self, tool_name: str, tool_input: Mapping[str, Any]) -> ReadPathDecision:
        if tool_name not in READ_ONLY_BUILTIN_TOOLS:
            return ReadPathDecision(False, "read_tool_not_supported")

        path_key = "file_path" if tool_name == "Read" else "path"
        raw_path = tool_input.get(path_key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            return ReadPathDecision(False, "read_path_missing")

        if _path_value_is_sensitive(raw_path):
            return ReadPathDecision(False, "read_sensitive_path_denied")
        if tool_name in {"Glob", "Grep"}:
            pattern = tool_input.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                return ReadPathDecision(False, "read_pattern_missing")
            path_pattern = pattern if tool_name == "Glob" else tool_input.get("glob")
            if path_pattern is not None and (
                not isinstance(path_pattern, str)
                or not _search_pattern_is_safe(path_pattern)
            ):
                return ReadPathDecision(False, "read_pattern_escape_denied")

        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            return ReadPathDecision(False, "read_path_unavailable")

        if _path_is_sensitive(resolved):
            return ReadPathDecision(False, "read_sensitive_path_denied")
        root = next(
            (
                allowed_root
                for allowed_root in self.roots
                if resolved == allowed_root.path or allowed_root.path in resolved.parents
            ),
            None,
        )
        if root is None:
            return ReadPathDecision(False, "read_path_outside_allowed_roots")

        if tool_name == "Read":
            if not resolved.is_file() or resolved.is_symlink():
                return ReadPathDecision(False, "read_file_not_regular")
        elif tool_name == "Glob":
            if not resolved.is_dir():
                return ReadPathDecision(False, "read_search_root_not_directory")
            tree_reason = _unsafe_search_tree_reason(resolved)
            if tree_reason is not None:
                return ReadPathDecision(False, tree_reason)
        elif not (resolved.is_file() or resolved.is_dir()):
            return ReadPathDecision(False, "read_search_root_invalid")
        elif resolved.is_dir():
            tree_reason = _unsafe_search_tree_reason(resolved)
            if tree_reason is not None:
                return ReadPathDecision(False, tree_reason)

        updated_input = dict(tool_input)
        updated_input[path_key] = str(resolved)
        return ReadPathDecision(True, f"{root.label}_allowed", updated_input)


def _path_value_is_sensitive(raw_path: str) -> bool:
    normalized = raw_path.replace("\\", "/")
    return any(_name_is_sensitive(part) for part in normalized.split("/") if part)


def _name_is_sensitive(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered in _SENSITIVE_DIRECTORY_NAMES
        or lowered in _SENSITIVE_FILE_NAMES
        or lowered.startswith(".env.")
        or lowered.endswith(".env")
    )


def _path_is_sensitive(path: Path) -> bool:
    return any(_name_is_sensitive(part) for part in path.parts)


def _search_pattern_is_safe(pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    if normalized.startswith(("/", "~")) or "\x00" in normalized:
        return False
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if not parts or ".." in parts:
        return False
    return not any(_name_is_sensitive(part) for part in parts)


def _unsafe_search_tree_reason(root: Path) -> str | None:
    try:
        for current_root, directory_names, file_names in os.walk(root, followlinks=False):
            current = Path(current_root)
            for name in (*directory_names, *file_names):
                candidate = current / name
                if candidate.is_symlink():
                    return "read_search_symlink_denied"
                if _name_is_sensitive(name):
                    return "read_sensitive_path_denied"
    except OSError:
        return "read_search_root_unavailable"
    return None


def _project_root_without_symlinks(project: Path, *parts: str) -> Path | None:
    candidate = project
    for part in parts:
        candidate /= part
        if candidate.is_symlink():
            return None
    return candidate.resolve(strict=False)


def build_read_path_policy(
    *,
    project: Path,
    cwd: Path,
    task_root: Path | None = None,
) -> ReadPathPolicy:
    project_path = project.expanduser().resolve(strict=False)
    roots: list[ReadPathRoot] = []
    project_roots = (
        (
            "project_skill_references",
            _project_root_without_symlinks(project_path, ".claude", "skills"),
        ),
        (
            "product_knowledge_package",
            _project_root_without_symlinks(
                project_path,
                "src",
                "docfit",
                "knowledge",
                "package",
            ),
        ),
    )
    roots.extend(
        ReadPathRoot(label, path) for label, path in project_roots if path is not None
    )
    if task_root is not None:
        task_path = task_root.expanduser().resolve(strict=False)
        roots.extend(
            (
                ReadPathRoot("current_task_input", task_path / "input"),
                ReadPathRoot("current_task_work", task_path / "work"),
                ReadPathRoot("current_task_output", task_path),
            )
        )
    return ReadPathPolicy(cwd.expanduser().resolve(strict=False), tuple(roots))


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
            *FORBIDDEN_TOOLS,
            *READ_ONLY_BUILTIN_TOOLS,
            *TRUSTED_BASIC_TOOLS,
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


def make_read_path_gate_hook(
    policy: ReadPathPolicy,
    audit: PermissionAudit | None = None,
) -> Callable[[HookInput, str | None, HookContext], Awaitable[HookJSONOutput]]:
    async def gate_read_path(
        hook_input: HookInput,
        tool_use_id: str | None,
        _context: HookContext,
    ) -> HookJSONOutput:
        if hook_input["hook_event_name"] != "PreToolUse":
            return {}
        tool_name = hook_input["tool_name"]
        if tool_name not in READ_ONLY_BUILTIN_TOOLS:
            return {}

        decision = policy.authorize(tool_name, hook_input["tool_input"])
        if audit is not None:
            audit(
                PermissionAuditEvent(
                    tool_name,
                    "allow" if decision.allowed else "deny",
                    tool_use_id=tool_use_id,
                    agent_id=hook_input.get("agent_id"),
                    reason_code=decision.reason_code,
                )
            )
        output: PreToolUseHookSpecificOutput = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if decision.allowed else "deny",
            "permissionDecisionReason": (
                "DocFit permits this read-only operation within an authorized canonical root."
                if decision.allowed
                else "DocFit denied this read-only operation outside its authorized path policy."
            ),
        }
        if decision.allowed and decision.updated_input is not None:
            output["updatedInput"] = decision.updated_input
        return {"hookSpecificOutput": output}

    return gate_read_path


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
    read_path_policy: ReadPathPolicy | None = None,
    audit: PermissionAudit | None = None,
    registered_tool_names: tuple[str, ...] = FULL_TOOL_NAMES,
) -> CanUseTool:
    def record(event: PermissionAuditEvent) -> None:
        if audit is not None:
            audit(event)

    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name in READ_ONLY_BUILTIN_TOOLS:
            decision = (
                read_path_policy.authorize(tool_name, tool_input)
                if read_path_policy is not None
                else ReadPathDecision(False, "read_path_policy_missing")
            )
            record(
                PermissionAuditEvent(
                    tool_name,
                    "allow" if decision.allowed else "deny",
                    tool_use_id=context.tool_use_id,
                    agent_id=context.agent_id,
                    reason_code=decision.reason_code,
                )
            )
            if decision.allowed:
                return PermissionResultAllow(updated_input=decision.updated_input)
            return PermissionResultDeny(
                message=(
                    "DocFit denied this read-only operation outside its authorized path policy."
                ),
                interrupt=False,
            )
        if tool_name in TRUSTED_BASIC_TOOLS:
            record(
                PermissionAuditEvent(
                    tool_name,
                    "allow",
                    tool_use_id=context.tool_use_id,
                    agent_id=context.agent_id,
                    reason_code="trusted_basic_tool_allowed",
                )
            )
            return PermissionResultAllow()
        if tool_name == "Skill" or tool_name in registered_tool_names:
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
    task_root: Path | None = None,
    agent_env: Mapping[str, str] | None = None,
    model: str | None = None,
    permission_audit: PermissionAudit | None = None,
    observation_hook: ObservationHook | None = None,
    system_prompt: str | None = None,
    output_format: dict[str, Any] | None = None,
    max_turns: int = 12,
) -> ClaudeAgentOptions:
    root = cwd or project_root()
    read_path_policy = build_read_path_policy(
        project=root,
        cwd=root,
        task_root=task_root,
    )
    configured_hooks: dict[str, list[HookMatcher]] = {
        "PreToolUse": [
            HookMatcher(
                matcher="Read|Glob|Grep",
                hooks=[make_read_path_gate_hook(read_path_policy, permission_audit)],
            ),
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
        allowed_tools=list(AUTO_APPROVED_TOOL_NAMES),
        disallowed_tools=list(FORBIDDEN_TOOLS),
        mcp_servers={MCP_SERVER_NAME: build_docfit_server()},
        strict_mcp_config=True,
        permission_mode="default",
        can_use_tool=make_permission_callback(
            ask_user,
            read_path_policy=read_path_policy,
            audit=permission_audit,
        ),
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
            "and independent validation. Use the two enabled domain Skills; path-bounded "
            "Read, Glob, and Grep for project Skill references, product Knowledge, and the "
            "current task; trusted, auto-approved Bash and Write; the five registered "
            "DocFit MCP tools; and the type-gated read-only docfit-unit-analyst. Bash and "
            "Write have no DocFit path gate and can access any resource available to this "
            "process, so use them deliberately and never expose credentials or document "
            "content in logs. "
            "Interpret Tool results yourself; the application shell does not choose Knowledge, "
            "delegate scopes, or interpret needs_input. Never treat approximate OfficeCLI "
            "rendering as Adobe delivery conversion evidence, and never consume an error or "
            "committed=false "
            "output."
        ),
    )
