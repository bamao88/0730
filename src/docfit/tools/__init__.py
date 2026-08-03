"""The five versioned DocFit MCP Tool registrations."""

from __future__ import annotations

import base64
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from mcp.types import ToolAnnotations

from docfit.tools.image_smoke import make_smoke_png
from docfit.tools.runtime import ToolFailure
from docfit.tools.schemas import (
    EDIT_SCHEMA,
    INSPECT_SCHEMA,
    RENDER_SCHEMA,
    VALIDATE_SCHEMA,
    VISUAL_REVIEW_SCHEMA,
)
from docfit.tools.service import (
    DocFitToolService,
    failure_result,
    tool_result,
    unexpected_failure_result,
)

MCP_SERVER_NAME = "docfit"
AGENT_TOOL_RESULT_MAX_CHARS = 12 * 1024 * 1024
_READ_ONLY_ANNOTATIONS = ToolAnnotations.model_validate(
    {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
        "maxResultSizeChars": AGENT_TOOL_RESULT_MAX_CHARS,
    }
)
_WRITE_ANNOTATIONS = ToolAnnotations.model_validate(
    {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
        "maxResultSizeChars": AGENT_TOOL_RESULT_MAX_CHARS,
    }
)
LOGICAL_TOOL_NAMES = (
    "docx_inspect",
    "docx_edit",
    "docx_render",
    "docx_visual_review",
    "docx_validate",
)
FULL_TOOL_NAMES = tuple(f"mcp__{MCP_SERVER_NAME}__{name}" for name in LOGICAL_TOOL_NAMES)


@tool(
    "docx_inspect",
    "Inspect one authorized DOCX snapshot and return facts plus opaque object refs.",
    INSPECT_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_inspect(args: dict[str, Any]) -> dict[str, Any]:
    try:
        return tool_result(DocFitToolService().inspect(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


@tool(
    "docx_edit",
    "Atomically edit a work copy using snapshot refs; never overwrite the input DOCX.",
    EDIT_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docx_edit(args: dict[str, Any]) -> dict[str, Any]:
    try:
        return tool_result(DocFitToolService().edit(args))
    except ToolFailure as error:
        return failure_result(error, committed=False)
    except Exception:
        return unexpected_failure_result(committed=False)


@tool(
    "docx_render",
    "Render with the fixed intent route: OfficeCLI feedback or Adobe PDF Services evidence.",
    RENDER_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docx_render(args: dict[str, Any]) -> dict[str, Any]:
    try:
        return tool_result(DocFitToolService().render(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


@tool(
    "docx_visual_review",
    "Return images derived only from an existing render ref; includes the transport smoke mode.",
    VISUAL_REVIEW_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_visual_review(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("mode") == "m0_image_smoke":
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
    try:
        structured, images = DocFitToolService().visual_review(args)
        return tool_result(structured, image_paths=images)
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


@tool(
    "docx_validate",
    "Independently re-read source/final DOCX evidence and report checks without semantic judgment.",
    VALIDATE_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_validate(args: dict[str, Any]) -> dict[str, Any]:
    try:
        return tool_result(DocFitToolService().validate(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


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
        version="1.0.0",
        tools=list(DOCFIT_TOOLS),
    )
