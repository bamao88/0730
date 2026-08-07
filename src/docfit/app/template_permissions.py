"""Task-local Bash and Write permissions for template preparation."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

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


def make_docfit_schema_version_hook() -> Callable[
    [HookInput, str | None, HookContext], Awaitable[HookJSONOutput]
]:
    """Canonicalize one provider transport quirk before MCP schema validation."""

    async def canonicalize(
        hook_input: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookJSONOutput:
        if (
            hook_input["hook_event_name"] != "PreToolUse"
            or not hook_input["tool_name"].startswith("mcp__docfit__")
            or hook_input["tool_input"].get("schema_version") != "1"
        ):
            return {}
        updated_input = dict(hook_input["tool_input"])
        updated_input["schema_version"] = 1
        output: PreToolUseHookSpecificOutput = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": (
                "DocFit canonicalized the provider's string schema version to integer v1."
            ),
            "updatedInput": updated_input,
        }
        return {"hookSpecificOutput": output}

    return canonicalize


def _candidate_path(raw: object, *, cwd: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else cwd / candidate


def _new_direct_child(
    raw: object,
    *,
    cwd: Path,
    parent: Path,
    suffixes: set[str],
) -> Path | None:
    candidate = _candidate_path(raw, cwd=cwd)
    if candidate is None or candidate.exists() or candidate.is_symlink():
        return None
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved_parent != parent or candidate.suffix.casefold() not in suffixes:
        return None
    return resolved_parent / candidate.name


def _existing_direct_child(
    raw: object,
    *,
    cwd: Path,
    parent: Path,
    suffixes: set[str],
) -> Path | None:
    candidate = _candidate_path(raw, cwd=cwd)
    if candidate is None:
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if (
        resolved.is_symlink()
        or not resolved.is_file()
        or resolved.parent != parent
        or resolved.suffix.casefold() not in suffixes
    ):
        return None
    return resolved


def _compiler_command(
    tool_input: dict[str, object],
    *,
    task_root: Path,
) -> dict[str, object] | None:
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if tokens[-1:] == ["2>&1"]:
        tokens = tokens[:-1]
    if len(tokens) >= 3 and tokens[0] == "cd" and tokens[2] == "&&":
        requested_cwd = _candidate_path(tokens[1], cwd=task_root)
        if requested_cwd is None:
            return None
        try:
            resolved_cwd = requested_cwd.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if resolved_cwd != task_root:
            return None
        tokens = tokens[3:]
    if len(tokens) != 8 or tokens[2::2] != ["--task-root", "--input", "--output"]:
        return None

    python_tokens = {
        "$DOCFIT_PYTHON",
        "${DOCFIT_PYTHON}",
        sys.executable,
        str(Path(sys.executable).resolve()),
    }
    if tokens[0] not in python_tokens and tokens[0] not in {"python", "python3"}:
        return None

    skill_scripts = (
        task_root / ".claude/skills/docfit-school-extract/scripts"
    ).resolve(strict=True)
    script = _existing_direct_child(
        tokens[1],
        cwd=task_root,
        parent=skill_scripts,
        suffixes={".py"},
    )
    if script is None or script.name not in {
        "compile_mutation_plan.py",
        "compile_artifact_spec.py",
    }:
        return None

    root_argument = _candidate_path(tokens[3], cwd=task_root)
    if root_argument is None:
        return None
    try:
        resolved_root = root_argument.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved_root != task_root:
        return None

    decisions = (task_root / "work/decisions").resolve(strict=True)
    compiled = (task_root / "work/compiled").resolve(strict=True)
    input_path = _existing_direct_child(
        tokens[5],
        cwd=task_root,
        parent=decisions,
        suffixes={".yaml", ".yml", ".json"},
    )
    output_path = _new_direct_child(
        tokens[7],
        cwd=task_root,
        parent=compiled,
        suffixes={".json"},
    )
    if input_path is None or output_path is None:
        return None

    updated = dict(tool_input)
    updated["command"] = shlex.join(
        [
            sys.executable,
            str(script),
            "--task-root",
            str(task_root),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
    )
    return updated


def make_template_task_permission_callback(
    base_callback: CanUseTool,
    *,
    task_root: Path,
) -> CanUseTool:
    """Keep decision authoring open while preventing direct DOCX/output publication."""

    root = task_root.resolve(strict=True)
    decisions = (root / "work/decisions").resolve(strict=True)

    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, object],
        context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name == "Write":
            destination = _new_direct_child(
                tool_input.get("file_path"),
                cwd=root,
                parent=decisions,
                suffixes={".yaml", ".yml", ".json"},
            )
            if destination is None:
                return PermissionResultDeny(
                    message=(
                        "DocFit permits Write only to a new YAML or JSON file directly under "
                        "work/decisions. Use template_build for output publication."
                    ),
                    interrupt=False,
                )
            updated_input = dict(tool_input)
            updated_input["file_path"] = str(destination)
            return PermissionResultAllow(updated_input=updated_input)

        if tool_name == "Bash":
            compiler_input = _compiler_command(tool_input, task_root=root)
            if compiler_input is None:
                return PermissionResultDeny(
                    message=(
                        "DocFit permits Bash only for an exact invocation of one supplied "
                        "compiler script from work/decisions to a new work/compiled file. "
                        "Use template Tools for DOCX and output operations."
                    ),
                    interrupt=False,
                )
            return PermissionResultAllow(updated_input=compiler_input)

        return await base_callback(tool_name, tool_input, context)

    return can_use_tool
