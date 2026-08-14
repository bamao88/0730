"""The five versioned DocFit MCP Tool registrations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from mcp.types import ToolAnnotations

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

ToolRunner = Callable[
    [DocFitToolService, dict[str, Any]], Awaitable[dict[str, Any]]
]


async def _run_inspect(
    service: DocFitToolService, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        return tool_result(service.inspect(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_edit(
    service: DocFitToolService, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        return tool_result(service.edit(args))
    except ToolFailure as error:
        return failure_result(error, committed=False)
    except Exception:
        return unexpected_failure_result(committed=False)


async def _run_render(
    service: DocFitToolService, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        structured, images = service.render(args)
        return tool_result(structured, image_paths=images)
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_visual_review(
    service: DocFitToolService, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        structured, images = service.visual_review(args)
        return tool_result(structured, image_paths=images)
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_validate(
    service: DocFitToolService, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        return tool_result(service.validate(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


@tool(
    "docx_inspect",
    "Inspect one authorized DOCX snapshot and return facts plus opaque object refs.",
    INSPECT_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_inspect(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_inspect(DocFitToolService(), args)


@tool(
    "docx_edit",
    "Atomically edit a work copy using snapshot refs; never overwrite the input DOCX.",
    EDIT_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docx_edit(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_edit(DocFitToolService(), args)


@tool(
    "docx_render",
    "Create one content-addressed visual snapshot with the fixed Docker LibreOffice renderer.",
    RENDER_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docx_render(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_render(DocFitToolService(), args)


@tool(
    "docx_visual_review",
    "Return on-demand page, region, contact-sheet, or comparison images from a render ref.",
    VISUAL_REVIEW_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_visual_review(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_visual_review(DocFitToolService(), args)


@tool(
    "docx_validate",
    "Independently re-read source/final DOCX evidence and report checks without semantic judgment.",
    VALIDATE_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_validate(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_validate(DocFitToolService(), args)


DOCFIT_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    docx_inspect,
    docx_edit,
    docx_render,
    docx_visual_review,
    docx_validate,
)


def build_docfit_tools(task_root: Path | None = None) -> tuple[SdkMcpTool[Any], ...]:
    """Return the stable Tools, optionally bound to one application-session root."""
    if task_root is None:
        return DOCFIT_TOOLS
    service = DocFitToolService(task_root=task_root)
    runners: tuple[ToolRunner, ...] = (
        _run_inspect,
        _run_edit,
        _run_render,
        _run_visual_review,
        _run_validate,
    )

    def bind(
        registered: SdkMcpTool[Any], runner: ToolRunner
    ) -> SdkMcpTool[Any]:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return await runner(service, args)

        return SdkMcpTool(
            name=registered.name,
            description=registered.description,
            input_schema=registered.input_schema,
            handler=handler,
            annotations=registered.annotations,
        )

    return tuple(
        bind(registered, runner)
        for registered, runner in zip(DOCFIT_TOOLS, runners, strict=True)
    )


def build_docfit_server(task_root: Path | None = None) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version="2.0.0",
        tools=list(build_docfit_tools(task_root)),
    )
