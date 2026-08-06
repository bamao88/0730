"""Claude Agent SDK Tool boundary for template extraction v2."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool
from mcp.types import ToolAnnotations

from docfit.template.artifact_build import TemplateArtifactBuilder
from docfit.template.comparison import TemplateComparisonService
from docfit.template.observation import TemplateObservationService
from docfit.tools.runtime import JsonObject, ToolFailure, task_root_from_args
from docfit.tools.template_schemas import (
    TEMPLATE_BUILD_SCHEMA,
    TEMPLATE_COMPARE_SCHEMA,
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


def _result(structured: JsonObject, image_paths: list[Path] | None = None) -> JsonObject:
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
    for path in image_paths or []:
        content.append(
            {
                "type": "image",
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                "mimeType": "image/png",
            }
        )
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
    "Create/query immutable DOCX evidence or read images without mutating the source document.",
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
        elif action == "images":
            structured, images = TemplateObservationService().images(args, task_root=task_root)
            return _result(structured, images)
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
    "Create deterministic template comparisons or read only their required images.",
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
                "visual_level",
            }
            if set(args) - allowed:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_compare_request",
                    message="The comparison request contains unsupported fields.",
                )
            return _result(TemplateComparisonService().final_review(args, task_root=task_root))
        if action == "images":
            allowed = common | {
                "comparison_ref",
                "required_image_ids",
                "cursor",
                "max_images",
            }
            if set(args) - allowed:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_compare_request",
                    message="The comparison request contains unsupported fields.",
                )
            structured, images = TemplateComparisonService().images(args, task_root=task_root)
            return _result(structured, images)
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_compare_action",
            message="template_compare requires action=create or action=images.",
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
