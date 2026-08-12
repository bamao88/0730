"""Claude Agent SDK Tool boundary for object-driven template preparation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
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
    TEMPLATE_FINAL_REVIEW_SCHEMA,
    TEMPLATE_FOCUS_SCHEMA,
    TEMPLATE_NEXT_SCHEMA,
    TEMPLATE_OPEN_SCHEMA,
    TEMPLATE_PUBLISH_SCHEMA,
    TEMPLATE_REGISTRY_SCHEMA,
    TEMPLATE_SEARCH_SCHEMA,
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
    "template_open",
    "template_next",
    "template_search",
    "template_focus",
    "template_registry",
    "template_edit",
    "template_final_review",
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
    "template_open",
    (
        "Open or resume the latest application checkpoint and return its current bounded visual "
        "region, compact materialization facts, and unresolved Agent-authored edit intents."
    ),
    TEMPLATE_OPEN_SCHEMA,
    annotations=_OBSERVE,
)
async def template_open(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_next",
    (
        "Advance from the exact region_ref returned by the latest checkpoint. Use handled only "
        "after a committed edit, or preserve with a short Agent reason for fixed school content."
    ),
    TEMPLATE_NEXT_SCHEMA,
    annotations=_OBSERVE,
)
async def template_next(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_search",
    (
        "Search visible text in the latest checkpoint and return at most five bounded object "
        "candidates needed to decide the current region. Search is physical, assigns no semantic "
        "meaning, and must not be used to inventory document landmarks."
    ),
    TEMPLATE_SEARCH_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_search(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_focus",
    (
        "Return a target-only or bounded-context crop for one current object_ref. The Tool "
        "never expands this into a full-page semantic review."
    ),
    TEMPLATE_FOCUS_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_focus(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_registry",
    (
        "For up to sixteen concrete objects from the latest checkpoint, look up exact Registry "
        "fields in the lookups lane or search at most five object-relevant candidates each in "
        "the searches lane. Each lane item is flat: object_id plus field_id/query. Never returns "
        "the full Registry."
    ),
    TEMPLATE_REGISTRY_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_registry(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_edit",
    (
        "Atomically execute one operations array against current object refs. Each array item is "
        "a direct action object such as {action:materialize_slot, "
        "object_ref:{object_id:...}, field_id:...}; do not add an item wrapper. The Agent "
        "uses materialize_slot for one independent value and materialize_structure with ordered "
        "members for a reusable multi-member body unit. The Agent chooses semantic fields, "
        "members, generated-content entries, and page-start intent; the "
        "Tool normalizes redundant operations, preserves Word boundaries, verifies effective "
        "results, checkpoints the immutable version, and returns changed-region feedback plus "
        "objective materialization/style/risk facts."
    ),
    TEMPLATE_EDIT_SCHEMA,
    annotations=_WRITE,
)
async def template_edit(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_final_review",
    (
        "After local object work and generated-content finalization are complete, return the "
        "next sequential batch of full-page PNGs for the exact current document_ref. Continue "
        "with its cursor until coverage_complete; this terminal visual QA never replaces local "
        "object reasoning."
    ),
    TEMPLATE_FINAL_REVIEW_SCHEMA,
    annotations=_OBSERVE,
)
async def template_final_review(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_publish",
    (
        "Publish exactly one validated final Word from the supplied immutable document_ref after "
        "the Agent has reviewed feedback for that exact version."
    ),
    TEMPLATE_PUBLISH_SCHEMA,
    annotations=_WRITE,
)
async def template_publish(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


TEMPLATE_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    template_open,
    template_next,
    template_search,
    template_focus,
    template_registry,
    template_edit,
    template_final_review,
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

    service = TemplateWorkspaceService(task_root=task_root, field_registry=field_registry)

    async def navigate(action: str, args: dict[str, Any]) -> dict[str, Any]:
        translated = {**args, "action": action}
        if action == "next":
            translated["region_outcome"] = translated.pop("outcome", None)
        if action == "focus":
            scope = translated.pop("scope", "target")
            translated.update(
                {
                    "quality": "detail" if scope == "target" else "review",
                    "padding": 32 if scope == "target" else 160,
                }
            )
        try:
            structured, images = service.view(translated)
            return tool_result(structured, image_paths=images)
        except ToolFailure as error:
            return failure_result(error)
        except Exception:
            return unexpected_failure_result()

    async def open_(args: dict[str, Any]) -> dict[str, Any]:
        return await navigate("open", args)

    async def next_(args: dict[str, Any]) -> dict[str, Any]:
        return await navigate("next", args)

    async def search(args: dict[str, Any]) -> dict[str, Any]:
        return await navigate("search", args)

    async def focus(args: dict[str, Any]) -> dict[str, Any]:
        return await navigate("focus", args)

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
            with suppress(ToolFailure):
                service.record_edit_failure(args, error)
            return failure_result(error, committed=False)
        except Exception:
            return unexpected_failure_result(committed=False)

    async def final_review(args: dict[str, Any]) -> dict[str, Any]:
        try:
            structured, images = service.final_review(args)
            return tool_result(structured, image_paths=images)
        except ToolFailure as error:
            return failure_result(error)
        except Exception:
            return unexpected_failure_result()

    async def publish(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return tool_result(service.publish(args))
        except ToolFailure as error:
            return failure_result(error, committed=False)
        except Exception:
            return unexpected_failure_result(committed=False)

    runners = (open_, next_, search, focus, registry, edit, final_review, publish)
    return create_sdk_mcp_server(
        name="docfit",
        version="6.0.0",
        tools=[
            _bind(registered, runner)
            for registered, runner in zip(TEMPLATE_TOOLS, runners, strict=True)
        ],
    )
