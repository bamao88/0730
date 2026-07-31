"""The five M0 DocFit MCP Tool registrations."""

from __future__ import annotations

import base64
import json
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from docfit.image_smoke import make_smoke_png

MCP_SERVER_NAME = "docfit"
LOGICAL_TOOL_NAMES = (
    "docx_inspect",
    "docx_edit",
    "docx_render",
    "docx_visual_review",
    "docx_validate",
)
FULL_TOOL_NAMES = tuple(f"mcp__{MCP_SERVER_NAME}__{name}" for name in LOGICAL_TOOL_NAMES)

_EMPTY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
_VISUAL_SMOKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["m0_image_smoke"],
            "description": "M0-only image transport smoke mode.",
        }
    },
    "required": ["mode"],
    "additionalProperties": False,
}


def _m0_not_implemented(tool_name: str) -> dict[str, Any]:
    payload = {
        "status": "error",
        "failure": {
            "code": "m0_not_implemented",
            "message": f"{tool_name} has no real DOCX behavior in M0.",
        },
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "is_error": True,
    }


@tool("docx_inspect", "M0 registration only; real DOCX inspection begins in M1.", _EMPTY_SCHEMA)
async def docx_inspect(_: dict[str, Any]) -> dict[str, Any]:
    return _m0_not_implemented("docx_inspect")


@tool("docx_edit", "M0 registration only; real DOCX editing begins in M1.", _EMPTY_SCHEMA)
async def docx_edit(_: dict[str, Any]) -> dict[str, Any]:
    return _m0_not_implemented("docx_edit")


@tool("docx_render", "M0 registration only; real DOCX rendering begins after M0.", _EMPTY_SCHEMA)
async def docx_render(_: dict[str, Any]) -> dict[str, Any]:
    return _m0_not_implemented("docx_render")


@tool(
    "docx_visual_review",
    "Return the M0 synthetic PNG for a real multimodal transport smoke.",
    _VISUAL_SMOKE_SCHEMA,
)
async def docx_visual_review(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("mode") != "m0_image_smoke":
        return {
            "content": [{"type": "text", "text": "Unsupported M0 visual review mode."}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": "Read the marker and border color from the attached image.",
            },
            {
                "type": "image",
                "data": base64.b64encode(make_smoke_png()).decode("ascii"),
                "mimeType": "image/png",
            },
        ]
    }


@tool("docx_validate", "M0 registration only; real DOCX validation begins after M0.", _EMPTY_SCHEMA)
async def docx_validate(_: dict[str, Any]) -> dict[str, Any]:
    return _m0_not_implemented("docx_validate")


DOCFIT_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    docx_inspect,
    docx_edit,
    docx_render,
    docx_visual_review,
    docx_validate,
)


def build_docfit_server() -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version="0.1.0",
        tools=list(DOCFIT_TOOLS),
    )
