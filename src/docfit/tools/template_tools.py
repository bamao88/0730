"""Role-scoped Claude Agent SDK tools for template preparation.

The application owns navigation, retries, visual batching, publication, and every
terminal transition.  The semantic Agent can only inspect one bound work item and
submit one typed decision.  The visual reviewer can only inspect one bound page
batch.  Internal checkpoint references never cross this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from mcp.types import ToolAnnotations

from docfit.template.workspace import TemplateWorkspaceService
from docfit.tools.runtime import JsonObject, ToolFailure
from docfit.tools.service import failure_result, tool_result, unexpected_failure_result
from docfit.tools.template_schemas import (
    TEMPLATE_GET_CURRENT_WORK_ITEM_SCHEMA,
    TEMPLATE_GET_REVIEW_BATCH_SCHEMA,
    TEMPLATE_REPORT_AMBIGUITY_SCHEMA,
    TEMPLATE_REQUEST_CURRENT_CONTEXT_SCHEMA,
    TEMPLATE_SUBMIT_CURRENT_DECISION_SCHEMA,
)

_READ_ONLY = ToolAnnotations.model_validate(
    {
        "readOnlyHint": True,
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

TEMPLATE_SEMANTIC_LOGICAL_TOOL_NAMES = (
    "template_get_current_work_item",
    "template_request_current_context",
    "template_submit_current_decision",
    "template_report_ambiguity",
)
TEMPLATE_REVIEW_LOGICAL_TOOL_NAMES = ("template_get_review_batch",)
TEMPLATE_LOGICAL_TOOL_NAMES = (
    *TEMPLATE_SEMANTIC_LOGICAL_TOOL_NAMES,
    *TEMPLATE_REVIEW_LOGICAL_TOOL_NAMES,
)
TEMPLATE_FULL_TOOL_NAMES = tuple(f"mcp__docfit__{name}" for name in TEMPLATE_LOGICAL_TOOL_NAMES)
TEMPLATE_SEMANTIC_FULL_TOOL_NAMES = tuple(
    f"mcp__docfit__{name}" for name in TEMPLATE_SEMANTIC_LOGICAL_TOOL_NAMES
)
TEMPLATE_REVIEW_FULL_TOOL_NAMES = tuple(
    f"mcp__docfit__{name}" for name in TEMPLATE_REVIEW_LOGICAL_TOOL_NAMES
)

_HIDDEN_KEYS = {
    "cursor",
    "document_ref",
    "document_sha256",
    "next_cursor",
    "previous_document_ref",
    "region_ref",
    "render_ref",
}


def _agent_payload(value: Any) -> Any:
    """Remove application-only identities and flatten short object IDs."""

    if isinstance(value, list):
        return [_agent_payload(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: JsonObject = {}
    for key, item in value.items():
        if key in _HIDDEN_KEYS or key == "guidance":
            continue
        if key == "object_ref" and isinstance(item, dict):
            object_id = item.get("object_id")
            if isinstance(object_id, str):
                result["object_id"] = object_id
            continue
        result[key] = _agent_payload(item)
    return result


def _objects(value: Any) -> tuple[tuple[str, str], ...]:
    found: dict[str, str] = {}

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        object_id = item.get("object_id")
        if not isinstance(object_id, str):
            reference = item.get("object_ref")
            object_id = reference.get("object_id") if isinstance(reference, dict) else None
        text = item.get("text")
        if isinstance(object_id, str):
            found.setdefault(object_id, text if isinstance(text, str) else "")
        for child in item.values():
            visit(child)

    visit(value)
    return tuple(found.items())


def _operation_field_ids(operation: JsonObject) -> set[str]:
    values = {operation.get("field_id")}
    values.update(
        member.get("field_id")
        for member in operation.get("members", [])
        if isinstance(member, dict)
    )
    return {value for value in values if isinstance(value, str)}


def _translate_operation(operation: JsonObject) -> JsonObject:
    translated = {
        key: value
        for key, value in operation.items()
        if key not in {"object_id", "members", "entries"}
    }
    translated["object_ref"] = {"object_id": operation.get("object_id")}
    if "members" in operation:
        translated["members"] = [
            {
                **{key: value for key, value in member.items() if key != "object_id"},
                "object_ref": {"object_id": member.get("object_id")},
            }
            for member in operation.get("members", [])
            if isinstance(member, dict)
        ]
    if "entries" in operation:
        translated["entries"] = [
            {
                **{key: value for key, value in entry.items() if key != "object_id"},
                "object_ref": {"object_id": entry.get("object_id")},
            }
            for entry in operation.get("entries", [])
            if isinstance(entry, dict)
        ]
    return translated


@dataclass(slots=True)
class SemanticWorkItemState:
    """Mutable evidence captured by one bounded semantic SDK session."""

    service: TemplateWorkspaceService
    work_item: JsonObject
    images: list[Path]
    internal_region_ref: str | None
    allow_preserve: bool
    start_progress: JsonObject
    offered_field_ids: set[str] = field(default_factory=set)
    allowed_object_ids: set[str] = field(default_factory=set)
    submission: JsonObject | None = None
    ambiguity: JsonObject | None = None
    post_region_ref: str | None = None
    mutated: bool = False

    def __post_init__(self) -> None:
        for object_id, _ in _objects(self.work_item):
            self.allowed_object_ids.add(object_id)
        generated_field = self.work_item.get("field_id")
        if isinstance(generated_field, str):
            self.offered_field_ids.add(generated_field)

    def rollback(self) -> None:
        if self.mutated:
            self.service.restore_workflow_progress(self.start_progress)
            self.mutated = False

    def initial_candidates(self) -> list[JsonObject]:
        results: list[JsonObject] = []
        for object_id, text in _objects(self.work_item)[:12]:
            if not text.strip():
                continue
            try:
                matches = self.service.registry.search(text, limit=5)
            except ToolFailure:
                continue
            if not matches:
                continue
            self.offered_field_ids.update(
                str(item["field_id"])
                for item in matches
                if isinstance(item.get("field_id"), str)
            )
            results.append(
                {
                    "object_id": object_id,
                    "matches": [_agent_payload(item) for item in matches],
                }
            )
        return results


@dataclass(frozen=True, slots=True)
class ReviewBatchState:
    payload: JsonObject
    images: list[Path]


async def _unbound(_args: dict[str, Any]) -> dict[str, Any]:
    return failure_result(
        ToolFailure(
            status="error",
            origin="environment",
            code="template_task_not_bound",
            message="Template tools require an application-bound work item.",
        )
    )


@tool(
    "template_get_current_work_item",
    "Return the one local semantic work item selected by the application, plus its image.",
    TEMPLATE_GET_CURRENT_WORK_ITEM_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_get_current_work_item(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_request_current_context",
    (
        "Request only the extra local crop, bounded text match, or Registry candidates needed "
        "to decide the current work item."
    ),
    TEMPLATE_REQUEST_CURRENT_CONTEXT_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_request_current_context(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_submit_current_decision",
    (
        "Submit one semantic decision for the current work item. Field IDs must come from "
        "candidates returned in this work item; the application performs and verifies the edit."
    ),
    TEMPLATE_SUBMIT_CURRENT_DECISION_SCHEMA,
    annotations=_WRITE,
)
async def template_submit_current_decision(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_report_ambiguity",
    (
        "Report concrete missing evidence for the current work item. The application decides "
        "whether to retry, request input, or terminate; this call does not control the workflow."
    ),
    TEMPLATE_REPORT_AMBIGUITY_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_report_ambiguity(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


@tool(
    "template_get_review_batch",
    "Return the exact full-page PNG batch selected by the application for visual QA.",
    TEMPLATE_GET_REVIEW_BATCH_SCHEMA,
    annotations=_READ_ONLY,
)
async def template_get_review_batch(args: dict[str, Any]) -> dict[str, Any]:
    return await _unbound(args)


TEMPLATE_TOOLS: tuple[SdkMcpTool[Any], ...] = (
    template_get_current_work_item,
    template_request_current_context,
    template_submit_current_decision,
    template_report_ambiguity,
    template_get_review_batch,
)


def _bind(registered: SdkMcpTool[Any], runner: Any) -> SdkMcpTool[Any]:
    return SdkMcpTool(
        name=registered.name,
        description=registered.description,
        input_schema=registered.input_schema,
        handler=runner,
        annotations=registered.annotations,
    )


def build_template_semantic_tool_server(
    state: SemanticWorkItemState,
) -> McpSdkServerConfig:
    """Build a server bound to exactly one semantic work item."""

    async def get_current(_args: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "status": "ok",
            "work_item": _agent_payload(state.work_item),
            "field_candidates": state.initial_candidates(),
        }
        return tool_result(payload, image_paths=state.images)

    async def request_context(args: dict[str, Any]) -> dict[str, Any]:
        try:
            if not any(
                isinstance(args.get(key), str)
                for key in ("visual_scope", "field_query", "text_query")
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="current_context_request_empty",
                    message="Request one bounded visual, field, or text context operation.",
                )
            result: JsonObject = {"schema_version": 1, "status": "ok"}
            images: list[Path] = []
            text_query = args.get("text_query")
            object_id = args.get("object_id")
            if (
                isinstance(args.get("visual_scope"), str)
                or isinstance(args.get("field_query"), str)
            ) and not isinstance(object_id, str):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="current_context_object_missing",
                    message="Visual and field context require one offered object ID.",
                )
            if isinstance(text_query, str):
                searched, _ = state.service.view({"action": "search", "query": text_query})
                public_search = _agent_payload(searched)
                result["text_search"] = public_search
                for candidate_id, _ in _objects(public_search):
                    state.allowed_object_ids.add(candidate_id)
            if isinstance(object_id, str):
                if object_id not in state.allowed_object_ids:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="object_not_offered",
                        message="Request context only for an object returned in this work item.",
                    )
                visual_scope = args.get("visual_scope")
                if isinstance(visual_scope, str):
                    focused, images = state.service.view(
                        {
                            "action": "focus",
                            "object_ref": {"object_id": object_id},
                            "scope": visual_scope,
                        }
                    )
                    result["visual_context"] = _agent_payload(focused)
                field_query = args.get("field_query")
                if isinstance(field_query, str):
                    registry = state.service.registry_query(
                        {
                            "searches": [
                                {"object_id": object_id, "query": field_query}
                            ]
                        }
                    )
                    public_registry = _agent_payload(registry)
                    result["field_candidates"] = public_registry
                    for item in registry.get("results", []):
                        if not isinstance(item, dict):
                            continue
                        state.offered_field_ids.update(
                            str(match["field_id"])
                            for match in item.get("matches", [])
                            if isinstance(match, dict)
                            and isinstance(match.get("field_id"), str)
                        )
            return tool_result(result, image_paths=images)
        except ToolFailure as error:
            return failure_result(error)
        except Exception:
            return unexpected_failure_result()

    async def submit(args: dict[str, Any]) -> dict[str, Any]:
        try:
            if state.submission is not None:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="decision_already_submitted",
                    message="Only one decision may be submitted in a semantic work-item session.",
                )
            outcome = args.get("outcome")
            reason = args.get("reason")
            operations = args.get("operations")
            if outcome == "preserve":
                if not state.allow_preserve:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="repair_requires_edit",
                        message="A confirmed final-page defect requires a concrete repair edit.",
                    )
                if operations is not None:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="preserve_operations_invalid",
                        message="A preserve decision cannot include edit operations.",
                    )
                state.submission = {"outcome": "preserve", "reason": reason}
                state.post_region_ref = state.internal_region_ref
                return tool_result(
                    {
                        "schema_version": 1,
                        "status": "ok",
                        "decision_received": True,
                        "changed": False,
                    }
                )
            if outcome != "apply" or not isinstance(operations, list) or not operations:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="apply_operations_missing",
                    message="An apply decision requires at least one operation.",
                )
            direct_operations = [dict(item) for item in operations if isinstance(item, dict)]
            operation_objects = {
                object_id
                for item in direct_operations
                for object_id, _ in _objects(item)
            }
            if operation_objects - state.allowed_object_ids:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="object_not_offered",
                    message="Every edited object must come from the current bounded context.",
                )
            requested_fields = {
                field_id
                for item in direct_operations
                for field_id in _operation_field_ids(item)
            }
            if requested_fields - state.offered_field_ids:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="field_not_offered",
                    message="Every field ID must come from candidates returned in this work item.",
                    suggested_actions=("request_current_field_candidates",),
                )
            translated = {
                "operations": [_translate_operation(item) for item in direct_operations]
            }
            structured, images = state.service.edit(translated)
            state.submission = {
                "outcome": "handled",
                "reason": reason,
                "operations": direct_operations,
            }
            state.mutated = True
            current_region = structured.get("current_region")
            state.post_region_ref = (
                current_region.get("region_ref")
                if isinstance(current_region, dict)
                and isinstance(current_region.get("region_ref"), str)
                else None
            )
            return tool_result(_agent_payload(structured), image_paths=images)
        except ToolFailure as error:
            return failure_result(error, committed=False)
        except Exception:
            return unexpected_failure_result(committed=False)

    async def ambiguity(args: dict[str, Any]) -> dict[str, Any]:
        state.ambiguity = dict(args)
        return tool_result(
            {
                "schema_version": 1,
                "status": "ok",
                "ambiguity_recorded": True,
                "workflow_transition": "application_owned",
            }
        )

    runners = (get_current, request_context, submit, ambiguity)
    return create_sdk_mcp_server(
        name="docfit",
        version="7.0.0",
        tools=[
            _bind(registered, runner)
            for registered, runner in zip(TEMPLATE_TOOLS[:4], runners, strict=True)
        ],
    )


def build_template_review_tool_server(state: ReviewBatchState) -> McpSdkServerConfig:
    """Build a server bound to one application-selected full-page PNG batch."""

    async def get_batch(_args: dict[str, Any]) -> dict[str, Any]:
        return tool_result(_agent_payload(state.payload), image_paths=state.images)

    return create_sdk_mcp_server(
        name="docfit",
        version="7.0.0",
        tools=[_bind(TEMPLATE_TOOLS[4], get_batch)],
    )
