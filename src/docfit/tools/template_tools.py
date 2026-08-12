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
_MAX_TARGET_CHILD_OBJECTS = 8
_MAX_SIBLING_OBJECTS = 12
_MIN_MEANINGFUL_BLANK_CHARACTERS = 4


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


def _bounded_work_item_payload(work_item: JsonObject) -> JsonObject:
    """Expose only the local context needed for the bound semantic decision."""

    public = _agent_payload(work_item)
    if not isinstance(public, dict):
        return {}
    region = public.get("region")
    if not isinstance(region, dict):
        return public
    adjacent = region.get("adjacent_objects")
    if isinstance(adjacent, list):
        target = region.get("target")
        target_id = target.get("object_id") if isinstance(target, dict) else None
        target_children: list[JsonObject] = []
        siblings: list[JsonObject] = []
        for raw in adjacent:
            if not isinstance(raw, dict):
                continue
            parent = raw.get("parent_context")
            parent_id = parent.get("object_id") if isinstance(parent, dict) else None
            if isinstance(target_id, str) and parent_id == target_id:
                target_children.append(raw)
            elif raw.get("type") != "run":
                siblings.append(raw)
        selected = [
            *target_children[:_MAX_TARGET_CHILD_OBJECTS],
            *siblings[:_MAX_SIBLING_OBJECTS],
        ]
        region["adjacent_objects"] = selected
        region["visible_adjacent_count"] = len(selected)
        region["total_adjacent_count"] = len(adjacent)
        blank_segments = _mechanical_blank_segments(selected)
        if blank_segments:
            region["mechanical_blank_segments"] = blank_segments
    return public


def _mechanical_blank_segments(objects: list[Any]) -> list[JsonObject]:
    """Describe physical whitespace groups without assigning field semantics."""

    runs_by_parent: dict[str, list[JsonObject]] = {}
    for raw in objects:
        if not isinstance(raw, dict) or raw.get("type") != "run":
            continue
        parent = raw.get("parent_context")
        parent_id = parent.get("object_id") if isinstance(parent, dict) else None
        if isinstance(parent_id, str):
            runs_by_parent.setdefault(parent_id, []).append(raw)

    segments: list[JsonObject] = []
    for parent_id, runs in runs_by_parent.items():
        index = 0
        while index < len(runs):
            text = runs[index].get("text")
            if not isinstance(text, str) or not text or not text.isspace():
                index += 1
                continue
            start = index
            character_count = 0
            object_ids: list[str] = []
            while index < len(runs):
                candidate_text = runs[index].get("text")
                if (
                    not isinstance(candidate_text, str)
                    or not candidate_text
                    or not candidate_text.isspace()
                ):
                    break
                character_count += len(candidate_text)
                candidate_id = runs[index].get("object_id")
                if isinstance(candidate_id, str):
                    object_ids.append(candidate_id)
                index += 1
            if character_count < _MIN_MEANINGFUL_BLANK_CHARACTERS or not object_ids:
                continue
            before = runs[start - 1].get("text") if start > 0 else None
            after = runs[index].get("text") if index < len(runs) else None
            segments.append(
                {
                    "parent_object_id": parent_id,
                    "object_ids": object_ids,
                    "character_count": character_count,
                    "before_text": before if isinstance(before, str) and before.strip() else None,
                    "after_text": after if isinstance(after, str) and after.strip() else None,
                }
            )
    return segments


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


def _validated_decision_operations(outcome: Any, operations: Any) -> list[JsonObject]:
    """Enforce the cross-field decision contract outside provider JSON Schema."""

    if outcome == "preserve":
        if operations not in (None, []):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="preserve_operations_invalid",
                message="A preserve decision cannot include edit operations.",
            )
        return []
    if outcome != "apply" or not isinstance(operations, list) or not operations:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="apply_operations_missing",
            message="An apply decision requires at least one operation.",
        )
    return [dict(item) for item in operations if isinstance(item, dict)]


def _validated_work_item_operations(
    work_item: JsonObject,
    outcome: Any,
    operations: Any,
) -> list[JsonObject]:
    """Keep phase-owned compound edits inside their application-bound work item."""

    direct = _validated_decision_operations(outcome, operations)
    actions = {str(item.get("action")) for item in direct}
    kind = work_item.get("kind")
    region = work_item.get("region")
    knowledge_signals = (
        region.get("knowledge_signals") if isinstance(region, dict) else None
    )
    if (
        kind == "local_region"
        and isinstance(knowledge_signals, list)
        and "generated-content" in knowledge_signals
        and direct
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="local_generated_content_read_only",
            message=(
                "Preserve this local generated-content cache without clearing, deleting, "
                "formatting, or refreshing any row or child run. The application will provide "
                "one generated-content work item after all title sources are finalized; mutate "
                "the live TOC only from that dedicated item."
            ),
        )
    if "refresh_toc" in actions and kind != "generated_content":
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="refresh_toc_wrong_work_item",
            message="Refresh the live TOC only from the generated-content work item.",
        )
    if kind == "generated_content" and actions != {"refresh_toc"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="generated_content_action_invalid",
            message="The generated-content work item accepts exactly one refresh_toc action.",
        )
    return direct


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
    navigation_done: bool = False
    agent_work_item: JsonObject = field(init=False)

    def __post_init__(self) -> None:
        self.agent_work_item = _bounded_work_item_payload(self.work_item)
        for object_id, _ in _objects(self.agent_work_item):
            self.allowed_object_ids.add(object_id)
        generated_field = self.work_item.get("field_id")
        if isinstance(generated_field, str):
            self.offered_field_ids.add(generated_field)

    def rollback(self) -> None:
        if self.mutated:
            self.service.restore_workflow_progress(self.start_progress)
            self.mutated = False

    def initial_candidates(self) -> list[JsonObject]:
        region = self.agent_work_item.get("region")
        target = region.get("target") if isinstance(region, dict) else None
        if not isinstance(target, dict):
            return []
        object_id = target.get("object_ref", target.get("object_id"))
        if isinstance(object_id, dict):
            object_id = object_id.get("object_id")
        text = target.get("text")
        if not isinstance(object_id, str) or not isinstance(text, str) or not text.strip():
            return []
        try:
            matches = self.service.registry.search(
                f"{text} {''.join(text.split())}",
                limit=5,
            )
        except ToolFailure:
            return []
        self.offered_field_ids.update(
            str(item["field_id"])
            for item in matches
            if isinstance(item.get("field_id"), str)
        )
        if not matches:
            return []
        return [
            {
                "object_id": object_id,
                "matches": [_agent_payload(item) for item in matches],
            }
        ]


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
        "Submit one semantic decision for the current work item. For preserve, omit operations "
        "or pass an empty array. For apply, pass at least one operation; field IDs must come "
        "from candidates returned in this work item. The application performs and verifies edits."
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
            "work_item": state.agent_work_item,
            "field_candidates": state.initial_candidates(),
            "candidate_protocol": {
                "initial_scope": "target_only",
                "sibling_rule": (
                    "For every adjacent object you judge fillable, request that exact "
                    "object_id with field_query before deciding it has no Registry candidate."
                ),
            },
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
                    public_focus = _agent_payload(focused)
                    result["visual_context"] = public_focus
                    local_context = public_focus.get("local_context")
                    adjacent = (
                        local_context.get("adjacent_objects")
                        if isinstance(local_context, dict)
                        else None
                    )
                    if isinstance(adjacent, list):
                        blank_segments = _mechanical_blank_segments(adjacent)
                        if blank_segments:
                            result["mechanical_blank_segments"] = blank_segments
                    for candidate_id, _ in _objects(public_focus):
                        state.allowed_object_ids.add(candidate_id)
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
                _validated_work_item_operations(state.work_item, outcome, operations)
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
            direct_operations = _validated_work_item_operations(
                state.work_item,
                outcome,
                operations,
            )
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
            navigation = structured.get("navigation")
            state.navigation_done = bool(
                isinstance(navigation, dict) and navigation.get("done") is True
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
