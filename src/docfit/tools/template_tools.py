"""Claude Agent SDK Tool boundary for template extraction v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from mcp.types import ToolAnnotations

from docfit.template.artifact_build import TemplateArtifactBuilder
from docfit.template.comparison import TemplateComparisonService
from docfit.template.mutation import TemplateMutationService
from docfit.template.observation import TemplateObservationService
from docfit.tools import build_docfit_tools
from docfit.tools.runtime import JsonObject, ToolFailure, task_root_from_args
from docfit.tools.template_schemas import (
    TEMPLATE_BUILD_SCHEMA,
    TEMPLATE_COMPARE_SCHEMA,
    TEMPLATE_MUTATE_SCHEMA,
    TEMPLATE_OBSERVE_SCHEMA,
)

_OBSERVE_ANNOTATIONS = ToolAnnotations.model_validate(
    {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
_WRITE_ANNOTATIONS = ToolAnnotations.model_validate(
    {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)


def _result(structured: JsonObject) -> JsonObject:
    content: list[JsonObject] = [
            {
                "type": "text",
                "text": json.dumps(
                    structured,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        ]
    return {
        "content": content,
        "structuredContent": structured,
        "isError": structured.get("call_status") != "ok",
    }


def _failure(error: ToolFailure) -> JsonObject:
    return _result(
        {
            "schema_version": 1,
            "call_status": error.status,
            "result_state": None,
            "checks": [],
            "warnings": [],
            "failure": {
                "origin": error.origin,
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        }
    )


@tool(
    "template_observe",
    "Create or query immutable structural DOCX evidence without rendering or mutation.",
    TEMPLATE_OBSERVE_SCHEMA,
    annotations=_OBSERVE_ANNOTATIONS,
)
async def template_observe(args: dict[str, Any]) -> dict[str, Any]:
    try:
        task_root = task_root_from_args(args)
        action = args.get("action")
        if action == "create":
            structured = TemplateObservationService().create(args, task_root=task_root)
        elif action == "query":
            structured = TemplateObservationService().query(args, task_root=task_root)
        else:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unsupported_observe_action",
                message="This implementation slice currently supports create and query.",
            )
        return _result(structured)
    except ToolFailure as error:
        return _failure(error)
    except Exception:
        return _result(
            {
                "schema_version": 1,
                "call_status": "error",
                "result_state": None,
                "checks": [],
                "warnings": [],
                "failure": {
                    "origin": "internal",
                    "code": "unexpected_internal_error",
                    "message": "The template observation failed unexpectedly.",
                    "retryable": False,
                },
            }
        )


@tool(
    "template_compare",
    "Bind structural comparison to images already reviewed through docx_visual_review.",
    TEMPLATE_COMPARE_SCHEMA,
    annotations=_OBSERVE_ANNOTATIONS,
)
async def template_compare(args: dict[str, Any]) -> dict[str, Any]:
    try:
        task_root = task_root_from_args(args)
        action = args.get("action")
        common = {"schema_version", "task_root", "action"}
        if action == "create":
            allowed = common | {
                "review_mode",
                "before_snapshot_ref",
                "after_snapshot_ref",
                "mutation_ref",
                "final_snapshot_ref",
                "render_ref",
                "reviewed_pages",
                "evidence_refs",
                "findings",
            }
            if set(args) - allowed:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_compare_request",
                    message="The comparison request contains unsupported fields.",
                )
            return _result(TemplateComparisonService().review(args, task_root=task_root))
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_compare_action",
            message="template_compare requires action=create.",
        )
    except ToolFailure as error:
        return _failure(error)
    except Exception:
        return _result(
            {
                "schema_version": 1,
                "call_status": "error",
                "result_state": None,
                "checks": [],
                "warnings": [],
                "failure": {
                    "origin": "internal",
                    "code": "unexpected_internal_error",
                    "message": "The template comparison failed unexpectedly.",
                    "retryable": False,
                },
            }
        )


@tool(
    "template_mutate",
    "Execute only a compiled mutation plan and atomically publish a new DOCX plus evidence.",
    TEMPLATE_MUTATE_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def template_mutate(args: dict[str, Any]) -> dict[str, Any]:
    try:
        task_root = task_root_from_args(args)
        allowed = {"schema_version", "task_root", "mutation_plan_path", "output_docx"}
        if set(args) != allowed:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_mutate_request",
                message="template_mutate accepts only a compiled plan path and new output path.",
            )
        return _result(TemplateMutationService().mutate(args, task_root=task_root))
    except ToolFailure as error:
        return _failure(error)
    except Exception:
        return _result(
            {
                "schema_version": 1,
                "call_status": "error",
                "result_state": None,
                "checks": [],
                "warnings": [],
                "failure": {
                    "origin": "internal",
                    "code": "unexpected_internal_error",
                    "message": "The template mutation failed unexpectedly.",
                    "retryable": False,
                },
            }
        )


@tool(
    "template_build",
    "Revalidate and atomically publish the four-file template artifact.",
    TEMPLATE_BUILD_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def template_build(args: dict[str, Any]) -> dict[str, Any]:
    try:
        task_root = task_root_from_args(args)
        allowed = {
            "schema_version",
            "task_root",
            "final_snapshot_ref",
            "artifact_spec_path",
            "output_dir",
        }
        if set(args) != allowed:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_build_request",
                message="The build request does not match the v1 contract.",
            )
        return _result(TemplateArtifactBuilder().build(args, task_root=task_root))
    except ToolFailure as error:
        return _failure(error)
    except Exception:
        return _result(
            {
                "schema_version": 1,
                "call_status": "error",
                "result_state": None,
                "checks": [],
                "warnings": [],
                "failure": {
                    "origin": "internal",
                    "code": "unexpected_internal_error",
                    "message": "The template build failed unexpectedly.",
                    "retryable": False,
                },
            }
        )


TEMPLATE_LOGICAL_TOOL_NAMES = (
    "template_observe",
    "template_mutate",
    "template_compare",
    "template_build",
)
TEMPLATE_FULL_TOOL_NAMES = tuple(
    f"mcp__docfit__{name}" for name in TEMPLATE_LOGICAL_TOOL_NAMES
) + ("mcp__docfit__docx_render", "mcp__docfit__docx_visual_review")
TEMPLATE_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    template_observe,
    template_mutate,
    template_compare,
    template_build,
)


def build_template_tool_server(task_root: Path | None = None) -> McpSdkServerConfig:
    """Build the one DocFit server composition used by prepare-template sessions."""
    shared = {tool.name: tool for tool in build_docfit_tools(task_root)}
    return create_sdk_mcp_server(
        name="docfit",
        version="2.0.0",
        tools=[
            *TEMPLATE_TOOLS,
            shared["docx_render"],
            shared["docx_visual_review"],
        ],
    )
