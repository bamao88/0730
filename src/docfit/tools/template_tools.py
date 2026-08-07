"""Claude Agent SDK Tool boundary for object-driven template preparation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from mcp.types import ToolAnnotations

from docfit.template.workspace import TemplateWorkspaceService
from docfit.tools.runtime import ToolFailure
from docfit.tools.service import failure_result, tool_result, unexpected_failure_result
from docfit.tools.template_schemas import (
    TEMPLATE_EDIT_SCHEMA,
    TEMPLATE_PUBLISH_SCHEMA,
    TEMPLATE_REGISTRY_SCHEMA,
    TEMPLATE_VIEW_SCHEMA,
)

_READ_ONLY = ToolAnnotations.model_validate(
    {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
_OBSERVE = ToolAnnotations.model_validate(
    {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
_WRITE = ToolAnnotations.model_validate(
    {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)

TEMPLATE_LOGICAL_TOOL_NAMES = (
    "template_view",
    "template_registry",
    "template_edit",
    "template_publish",
)
TEMPLATE_FULL_TOOL_NAMES = tuple(f"mcp__docfit__{name}" for name in TEMPLATE_LOGICAL_TOOL_NAMES)


async def _unbound(_args: dict[str, Any]) -> dict[str, Any]:
    return failure_result(
        ToolFailure(
            status="error",
            origin="environment",
            code="template_task_not_bound",
            message="Template Tools must be created by a bound prepare-template session.",
        )
    )


@tool(
    "template_view",
    (
        "Open one template version on its current page, request one needed page, or find/focus "
        "one concrete object with bounded local visual context. This Tool never forces an "
        "all-page review. Returned object_ref values are accepted unchanged by template_edit."
    ),
    TEMPLATE_VIEW_SCHEMA,
    annotations=_OBSERVE,
)
async def template_view(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_registry",
    (
        "For up to sixteen concrete objects from one version, look up exact Registry fields or "
        "search at most five object-relevant candidates each. This Tool never returns the full "
        "Registry."
    ),
    TEMPLATE_REGISTRY_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_registry(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_edit",
    (
        "Atomically apply up to thirty-two materialize, clear, or remove decisions made from one "
        "page context. No plan file or output path is needed. The Tool creates one immutable "
        "version, checks every effect, and returns the changed page image plus fresh refs."
    ),
    TEMPLATE_EDIT_SCHEMA,
    annotations=_WRITE,
)
async def template_edit(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_publish",
    (
        "Publish exactly one validated final Word from an immutable document_ref after the "
        "Agent has seen local visual feedback for that exact version. No all-page coverage gate "
        "is imposed. Never publishes or overwrites an intermediate Word."
    ),
    TEMPLATE_PUBLISH_SCHEMA,
    annotations=_WRITE,
)
async def template_publish(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


TEMPLATE_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    template_view,
    template_registry,
    template_edit,
    template_publish,
)

Runner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _bind(registered: SdkMcpTool[Any], runner: Runner) -> SdkMcpTool[Any]:
    return SdkMcpTool(
        name=registered.name,
        description=registered.description,
        input_schema=registered.input_schema,
        handler=runner,
        annotations=registered.annotations,
    )


def build_template_tool_server(
    task_root: Path,
    field_registry: Path,
) -> McpSdkServerConfig:
    """Build the one task-bound Tool server used by prepare-template."""

    service = TemplateWorkspaceService(
        task_root=task_root,
        field_registry=field_registry,
    )

    async def view(args: dict[str, Any]) -> dict[str, Any]:
        try:
            structured, images = service.view(args)
            return tool_result(structured, image_paths=images)
        except ToolFailure as error:
            return failure_result(error)
        except Exception:
            return unexpected_failure_result()

    async def registry(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return tool_result(service.registry_query(args))
        except ToolFailure as error:
            return failure_result(error)
        except Exception:
            return unexpected_failure_result()

    async def edit(args: dict[str, Any]) -> dict[str, Any]:
        try:
            structured, images = service.edit(args)
            return tool_result(structured, image_paths=images)
        except ToolFailure as error:
            return failure_result(error, committed=False)
        except Exception:
            return unexpected_failure_result(committed=False)

    async def publish(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return tool_result(service.publish(args))
        except ToolFailure as error:
            return failure_result(error, committed=False)
        except Exception:
            return unexpected_failure_result(committed=False)

    runners = (view, registry, edit, publish)
    return create_sdk_mcp_server(
        name="docfit",
        version="3.0.0",
        tools=[
            _bind(registered, runner)
            for registered, runner in zip(TEMPLATE_TOOLS, runners, strict=True)
        ],
    )
