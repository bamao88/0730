"""DocFit MCP Tool registrations."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

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
from docfit.tools.surface import (
    CANONICAL_AGENT_TOOL_NAMES as CANONICAL_AGENT_TOOL_NAMES,
)
from docfit.tools.surface import (
    DOCFIT_APPLY_SCHEMA as DOCFIT_APPLY_SCHEMA,
)
from docfit.tools.surface import (
    DOCFIT_APPLY_TOOL as DOCFIT_APPLY_TOOL,
)
from docfit.tools.surface import (
    DOCFIT_CHECK_SCHEMA as DOCFIT_CHECK_SCHEMA,
)
from docfit.tools.surface import (
    DOCFIT_CHECK_TOOL as DOCFIT_CHECK_TOOL,
)
from docfit.tools.surface import (
    DOCFIT_EVIDENCE_SCHEMA as DOCFIT_EVIDENCE_SCHEMA,
)
from docfit.tools.surface import (
    DOCFIT_EVIDENCE_TOOL as DOCFIT_EVIDENCE_TOOL,
)
from docfit.tools.surface import (
    DOCFIT_GENERAL_READ_ONLY_TOOL_NAMES as DOCFIT_GENERAL_READ_ONLY_TOOL_NAMES,
)
from docfit.tools.surface import (
    DOCFIT_GENERAL_SUBAGENT_TOOL_NAMES as DOCFIT_GENERAL_SUBAGENT_TOOL_NAMES,
)
from docfit.tools.surface import (
    DOCFIT_GENERAL_TOOL_NAMES as DOCFIT_GENERAL_TOOL_NAMES,
)
from docfit.tools.surface import (
    DOCFIT_GENERAL_WRITE_TOOL_NAMES as DOCFIT_GENERAL_WRITE_TOOL_NAMES,
)
from docfit.tools.surface import (
    DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA as DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA,
)
from docfit.tools.surface import (
    DOCFIT_TOOL_SURFACE as DOCFIT_TOOL_SURFACE,
)
from docfit.tools.surface import (
    LEGACY_DOCX_TOOL_ADAPTERS as LEGACY_DOCX_TOOL_ADAPTERS,
)
from docfit.tools.surface import (
    READ_ONLY_AGENT_TOOL_NAMES as READ_ONLY_AGENT_TOOL_NAMES,
)
from docfit.tools.surface import (
    SUBAGENT_AGENT_TOOL_NAMES as SUBAGENT_AGENT_TOOL_NAMES,
)
from docfit.tools.surface import (
    TEMPLATE_RUNTIME_AGENT_TOOL_NAMES as TEMPLATE_RUNTIME_AGENT_TOOL_NAMES,
)
from docfit.tools.surface import (
    TEMPLATE_RUNTIME_FULL_AGENT_TOOL_NAMES as TEMPLATE_RUNTIME_FULL_AGENT_TOOL_NAMES,
)
from docfit.tools.surface import (
    TEMPLATE_SEMANTIC_EVIDENCE_FOCUS as TEMPLATE_SEMANTIC_EVIDENCE_FOCUS,
)
from docfit.tools.surface import (
    TOOL_FAILURE_CODES as TOOL_FAILURE_CODES,
)
from docfit.tools.surface import (
    TOOL_SURFACE_VERSION as TOOL_SURFACE_VERSION,
)
from docfit.tools.surface import (
    WRITE_AGENT_TOOL_NAMES as WRITE_AGENT_TOOL_NAMES,
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
    DOCFIT_EVIDENCE_TOOL,
    DOCFIT_CHECK_TOOL,
    DOCFIT_APPLY_TOOL,
    "docx_inspect",
    "docx_edit",
    "docx_render",
    "docx_visual_review",
    "docx_validate",
)
FULL_TOOL_NAMES = tuple(f"mcp__{MCP_SERVER_NAME}__{name}" for name in LOGICAL_TOOL_NAMES)
FULL_AGENT_TOOL_NAMES = FULL_TOOL_NAMES

ToolRunner = Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]
ToolResultBuilder = Callable[..., dict[str, Any]]


def _audit_object_ref(value: Any) -> dict[str, Any]:
    raw = value
    if isinstance(raw, str):
        payload = raw.removeprefix("object_ref:")
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            return {"kind": "string", "length": len(value)}
    if not isinstance(raw, dict):
        return {"kind": type(value).__name__}
    nested_ref = raw.get("object_ref")
    object_ref = nested_ref if isinstance(nested_ref, dict) else raw
    summary: dict[str, Any] = {"kind": "object"}
    for key in ("document_sha256", "expected_fingerprint", "object_id", "locator", "type"):
        value = object_ref.get(key)
        if isinstance(value, str):
            summary[key] = value
    text = raw.get("text")
    if isinstance(text, str):
        summary["text_present"] = True
        summary["text_length"] = len(text)
    return summary


def _audit_input(args: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "schema_version",
        "source_hash",
        "candidate_hash",
        "focus",
        "check",
        "operation",
        "field_id",
        "scope_ref",
        "unit_id",
        "output_docx",
        "idempotency_key",
        "page",
        "offset",
        "limit",
        "render_ref",
    ):
        value = args.get(key)
        if isinstance(value, str | int):
            summary[key] = value
    if "target_ref" in args:
        summary["target_ref"] = _audit_object_ref(args["target_ref"])
    if "object_ref" in args:
        summary["object_ref"] = _audit_object_ref(args["object_ref"])
    batch_ref = args.get("batch_ref")
    if isinstance(batch_ref, str):
        summary["batch_ref"] = batch_ref
    payload = args.get("payload")
    if isinstance(payload, dict):
        judgments = payload.get("semantic_judgments", payload.get("judgments"))
        if isinstance(judgments, list):
            summary["payload_judgment_count"] = len(judgments)
    elif "payload" in args:
        summary["payload_kind"] = type(payload).__name__
        if isinstance(payload, list):
            summary["payload_item_count"] = len(payload)
    replacement = args.get("replacement_text")
    if isinstance(replacement, str):
        summary["replacement_text_length"] = len(replacement)
    return summary


def _audit_result(result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        return {"status": "missing_structured_content"}
    summary: dict[str, Any] = {
        "status": structured.get("status"),
        "committed": structured.get("committed"),
        "completion": structured.get("completion"),
        "output_docx": structured.get("output_docx"),
        "output_sha256": structured.get("output_sha256"),
        "candidate_hash": structured.get("candidate_hash"),
        "render_ref": structured.get("render_ref"),
        "focus": structured.get("focus"),
        "check": structured.get("check"),
    }
    failure = structured.get("failure")
    if isinstance(failure, dict):
        summary["failure"] = {
            key: failure.get(key)
            for key in ("origin", "code", "retryable", "message")
            if key in failure
        }
    blockers = structured.get("blockers")
    if isinstance(blockers, list) and blockers:
        summary["blockers"] = [
            {
                key: blocker.get(key)
                for key in ("code", "field")
                if isinstance(blocker, dict) and key in blocker
            }
            for blocker in blockers[:12]
            if isinstance(blocker, dict)
        ]
    operations = structured.get("operations")
    if isinstance(operations, list):
        summary["operation_count"] = len(operations)
        failed = [
            item.get("failure", {}).get("code")
            for item in operations
            if isinstance(item, dict) and isinstance(item.get("failure"), dict)
        ]
        if failed:
            summary["operation_failure_codes"] = failed
    return {key: value for key, value in summary.items() if value is not None}


def _record_tool_call_audit(
    service: Any,
    *,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    duration_ms: int,
) -> None:
    root = getattr(service, "_task_root", None)
    if not isinstance(root, Path):
        return
    payload = {
        "tool": tool_name,
        "duration_ms": duration_ms,
        "input": _audit_input(args),
        "result": _audit_result(result),
    }
    try:
        path = root / "work/.docfit/tool-call-audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def __getattr__(name: str) -> Any:
    if name in {
        "DocFitToolService",
        "failure_result",
        "tool_result",
        "unexpected_failure_result",
    }:
        from docfit.tools import service

        value = getattr(service, name)
        globals()[name] = value
        return value
    raise AttributeError(name)


def _service_class() -> type[Any]:
    existing = globals().get("DocFitToolService")
    if existing is not None:
        return cast(type[Any], existing)
    from docfit.tools.service import DocFitToolService

    return DocFitToolService


def _result_helpers() -> tuple[ToolResultBuilder, ToolResultBuilder, ToolResultBuilder]:
    from docfit.tools.service import failure_result, tool_result, unexpected_failure_result

    return (
        cast(ToolResultBuilder, failure_result),
        cast(ToolResultBuilder, tool_result),
        cast(ToolResultBuilder, unexpected_failure_result),
    )


async def _run_inspect(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        return tool_result(service.inspect(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_evidence(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        structured = service.evidence(args)
        image_paths = getattr(service, "_last_evidence_image_paths", [])
        return tool_result(
            structured,
            image_paths=image_paths if isinstance(image_paths, list) else None,
        )
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_check(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        return tool_result(service.check(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_apply(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        return tool_result(service.apply(args))
    except ToolFailure as error:
        return failure_result(error, committed=False)
    except Exception:
        return unexpected_failure_result(committed=False)


async def _run_edit(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        return tool_result(service.edit(args))
    except ToolFailure as error:
        return failure_result(error, committed=False)
    except Exception:
        return unexpected_failure_result(committed=False)


async def _run_render(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        structured, images = service.render(args)
        return tool_result(structured, image_paths=images)
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_visual_review(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        structured, images = service.visual_review(args)
        return tool_result(structured, image_paths=images)
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


async def _run_validate(
    service: Any, args: dict[str, Any]
) -> dict[str, Any]:
    failure_result, tool_result, unexpected_failure_result = _result_helpers()
    try:
        return tool_result(service.validate(args))
    except ToolFailure as error:
        return failure_result(error)
    except Exception:
        return unexpected_failure_result()


@tool(
    DOCFIT_EVIDENCE_TOOL,
    "Collect bounded hash-bound evidence cards for template semantic judgment.",
    DOCFIT_EVIDENCE_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docfit_evidence(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_evidence(_service_class()(), args)


@tool(
    DOCFIT_CHECK_TOOL,
    "Check mechanical template contracts without school semantic authority.",
    DOCFIT_CHECK_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docfit_check(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_check(_service_class()(), args)


@tool(
    DOCFIT_APPLY_TOOL,
    "Apply one reviewed template mutation to a hash-bound candidate.",
    DOCFIT_APPLY_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docfit_apply(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_apply(_service_class()(), args)


@tool(
    "docx_inspect",
    "Inspect one authorized DOCX snapshot and return facts plus opaque object refs.",
    INSPECT_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_inspect(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_inspect(_service_class()(), args)


@tool(
    "docx_edit",
    "Atomically edit a work copy using snapshot refs; never overwrite the input DOCX.",
    EDIT_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docx_edit(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_edit(_service_class()(), args)


@tool(
    "docx_render",
    "Create one content-addressed visual snapshot with the fixed Docker LibreOffice renderer.",
    RENDER_SCHEMA,
    annotations=_WRITE_ANNOTATIONS,
)
async def docx_render(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_render(_service_class()(), args)


@tool(
    "docx_visual_review",
    "Return on-demand page, region, contact-sheet, or comparison images from a render ref.",
    VISUAL_REVIEW_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_visual_review(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_visual_review(_service_class()(), args)


@tool(
    "docx_validate",
    "Independently re-read source/final DOCX evidence and report checks without semantic judgment.",
    VALIDATE_SCHEMA,
    annotations=_READ_ONLY_ANNOTATIONS,
)
async def docx_validate(args: dict[str, Any]) -> dict[str, Any]:
    return await _run_validate(_service_class()(), args)


DOCFIT_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    docfit_evidence,
    docfit_check,
    docfit_apply,
    docx_inspect,
    docx_edit,
    docx_render,
    docx_visual_review,
    docx_validate,
)


def build_docfit_tools(
    task_root: Path | None = None,
    *,
    include_legacy_tools: bool = True,
    template_semantic_only: bool = False,
) -> tuple[SdkMcpTool[Any], ...]:
    """Return the stable Tools, optionally bound to one application-session root."""
    if task_root is None and include_legacy_tools:
        return DOCFIT_TOOLS
    service = _service_class()(task_root=task_root)
    runners: tuple[ToolRunner, ...] = (
        _run_evidence,
        _run_check,
        _run_apply,
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
            started = time.perf_counter()
            result = await runner(service, args)
            _record_tool_call_audit(
                service,
                tool_name=registered.name,
                args=args,
                result=result,
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            return result

        input_schema = registered.input_schema
        description = registered.description
        if template_semantic_only and registered.name == DOCFIT_EVIDENCE_TOOL:
            input_schema = DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA
            description = "Read bounded school-template context for semantic judgment."

        return SdkMcpTool(
            name=registered.name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            annotations=registered.annotations,
        )

    tool_pairs = tuple(zip(DOCFIT_TOOLS, runners, strict=True))
    if template_semantic_only:
        tool_pairs = tuple(
            pair
            for pair in tool_pairs
            if pair[0].name in TEMPLATE_RUNTIME_AGENT_TOOL_NAMES
        )
    elif not include_legacy_tools:
        tool_pairs = tool_pairs[: len(CANONICAL_AGENT_TOOL_NAMES)]

    docx_tools = tuple(
        bind(registered, runner)
        for registered, runner in tool_pairs
    )

    return docx_tools


def build_docfit_server(
    task_root: Path | None = None,
    *,
    include_legacy_tools: bool = True,
    template_semantic_only: bool = False,
) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name=MCP_SERVER_NAME,
        version="2.0.0",
        tools=list(
            build_docfit_tools(
                task_root,
                include_legacy_tools=include_legacy_tools,
                template_semantic_only=template_semantic_only,
            )
        ),
    )
