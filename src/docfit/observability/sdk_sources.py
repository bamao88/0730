"""Installed Claude Agent SDK source-field inventory for O0 projectors."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from claude_agent_sdk import types as sdk_types


@dataclass(frozen=True, slots=True)
class SDKSourceContract:
    symbol: str
    direct_fields: tuple[str, ...]


SDK_SOURCE_CONTRACTS = (
    SDKSourceContract(
        "AssistantMessage",
        ("message_id", "uuid", "session_id", "parent_tool_use_id", "usage"),
    ),
    SDKSourceContract("ToolUseBlock", ("id", "name")),
    SDKSourceContract("ToolResultBlock", ("tool_use_id", "is_error")),
    SDKSourceContract("ResultMessage", ("session_id", "uuid", "num_turns", "usage")),
    SDKSourceContract("PreToolUseHookInput", ("tool_use_id", "agent_id", "agent_type")),
    SDKSourceContract("PostToolUseHookInput", ("tool_use_id", "agent_id", "agent_type")),
    SDKSourceContract(
        "PostToolUseFailureHookInput",
        ("tool_use_id", "agent_id", "agent_type", "is_interrupt"),
    ),
    SDKSourceContract("SubagentStartHookInput", ("agent_id", "agent_type")),
    SDKSourceContract("SubagentStopHookInput", ("agent_id", "agent_type")),
    SDKSourceContract("ToolPermissionContext", ("tool_use_id", "agent_id")),
)

FORBIDDEN_PERSISTED_SDK_FIELDS = frozenset(
    {
        "prompt",
        "tool_input",
        "tool_response",
        "error",
        "result",
        "transcript_path",
        "agent_transcript_path",
        "cwd",
    }
)


def _field_names(symbol: Any) -> frozenset[str]:
    if is_dataclass(symbol):
        return frozenset(field.name for field in fields(symbol))
    annotations = getattr(symbol, "__annotations__", {})
    names = set(annotations)
    for base in getattr(symbol, "__mro__", ())[1:]:
        names.update(getattr(base, "__annotations__", {}))
    return frozenset(names)


def installed_sdk_contract_gaps() -> tuple[str, ...]:
    gaps: list[str] = []
    for contract in SDK_SOURCE_CONTRACTS:
        symbol = getattr(sdk_types, contract.symbol, None)
        if symbol is None:
            gaps.append(f"{contract.symbol}:missing_symbol")
            continue
        available = _field_names(symbol)
        for field_name in contract.direct_fields:
            if field_name not in available:
                gaps.append(f"{contract.symbol}:{field_name}")
    return tuple(gaps)
