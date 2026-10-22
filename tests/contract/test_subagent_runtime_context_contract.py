from __future__ import annotations

import asyncio

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from docfit.app.agent import (
    READ_ONLY_SUBAGENT_TOOLS,
    SUBAGENT_NAME,
    build_unit_analyst_definition,
    make_permission_callback,
)
from docfit.tools.surface import (
    DOCFIT_GENERAL_SUBAGENT_FULL_TOOL_NAMES,
    DOCFIT_GENERAL_WRITE_FULL_TOOL_NAMES,
)


def test_subagent_definition_uses_canonical_p2_tools_and_no_runtime_skill() -> None:
    definition = build_unit_analyst_definition()
    prompt = definition.prompt or ""

    assert tuple(definition.tools or ()) == DOCFIT_GENERAL_SUBAGENT_FULL_TOOL_NAMES
    assert tuple(definition.tools or ()) == READ_ONLY_SUBAGENT_TOOLS
    assert "docfit_evidence" in prompt
    assert "docfit_check" in prompt
    assert "docx_inspect" not in prompt
    assert "docx_visual_review" not in prompt
    assert definition.skills == []
    assert definition.memory is None
    assert definition.permissionMode == "dontAsk"
    assert set(definition.disallowedTools or ()) >= {
        "Bash",
        "Write",
        "Read",
        "Glob",
        "Grep",
        "Agent",
        "Skill",
        "AskUserQuestion",
        *DOCFIT_GENERAL_WRITE_FULL_TOOL_NAMES,
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_edit",
        "mcp__docfit__docx_render",
        "mcp__docfit__docx_visual_review",
        "mcp__docfit__docx_validate",
    }

def test_subagent_permission_allows_canonical_read_only_and_denies_legacy_tools() -> None:
    async def ask_user(_: str) -> str:
        raise AssertionError("Subagent permissions must not ask the user")

    callback = make_permission_callback(ask_user)

    for tool_name in DOCFIT_GENERAL_SUBAGENT_FULL_TOOL_NAMES:
        allowed = asyncio.run(
            callback(
                tool_name,
                {},
                ToolPermissionContext(agent_id=SUBAGENT_NAME, tool_use_id="tool-1"),
            )
        )
        assert isinstance(allowed, PermissionResultAllow)

    for tool_name in (
        "mcp__docfit__docx_inspect",
        "mcp__docfit__docx_visual_review",
        *DOCFIT_GENERAL_WRITE_FULL_TOOL_NAMES,
    ):
        denied = asyncio.run(
            callback(
                tool_name,
                {},
                ToolPermissionContext(agent_id=SUBAGENT_NAME, tool_use_id="tool-2"),
            )
        )
        assert isinstance(denied, PermissionResultDeny)
        assert "read-only tools" in denied.message
