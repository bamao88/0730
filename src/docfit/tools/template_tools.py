"""Role-scoped Claude Agent SDK tools for template preparation.

The application owns navigation, retries, visual batching, publication, and every
terminal transition.  The semantic Agent can only inspect one bound work item and
submit one typed decision.  The visual reviewer can only inspect one bound page
batch.  Internal checkpoint references never cross this boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from mcp.types import ToolAnnotations

from docfit.template.semantic_types import semantic_object_type
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
_MAX_SIBLING_CHILD_OBJECTS = 24
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
    """Expose one bounded crop with children for every visible top-level object."""

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
        selected_siblings = siblings[:_MAX_SIBLING_OBJECTS]
        sibling_ids = {
            item.get("object_id")
            for item in selected_siblings
            if isinstance(item.get("object_id"), str)
        }
        sibling_children = [
            raw
            for raw in adjacent
            if isinstance(raw, dict)
            and raw.get("type") == "run"
            and isinstance((parent := raw.get("parent_context")), dict)
            and parent.get("object_id") in sibling_ids
        ][:_MAX_SIBLING_CHILD_OBJECTS]
        selected_ids = {
            item.get("object_id")
            for item in [
                *target_children[:_MAX_TARGET_CHILD_OBJECTS],
                *selected_siblings,
                *sibling_children,
            ]
            if isinstance(item.get("object_id"), str)
        }
        selected = [
            raw
            for raw in adjacent
            if isinstance(raw, dict) and raw.get("object_id") in selected_ids
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


def _operation_field_assignments(operation: JsonObject) -> set[tuple[str, str]]:
    """Return concrete object/field pairs chosen by one semantic operation."""

    assignments: set[tuple[str, str]] = set()
    object_id = operation.get("object_id")
    field_id = operation.get("field_id")
    if (
        operation.get("action") not in {"materialize_structure", "refresh_toc"}
        and isinstance(object_id, str)
        and isinstance(field_id, str)
    ):
        assignments.add((object_id, field_id))
    for member in operation.get("members", []):
        if not isinstance(member, dict):
            continue
        member_object = member.get("object_id")
        member_field = member.get("field_id")
        if isinstance(member_object, str) and isinstance(member_field, str):
            assignments.add((member_object, member_field))
    return assignments


def _target_and_descendant_ids(value: Any, target_id: str) -> set[str]:
    """Select one queried object and descendants, excluding visible peer objects."""

    relationships: list[tuple[str, str | None]] = []

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        object_id = item.get("object_id")
        parent = item.get("parent_context")
        parent_id = parent.get("object_id") if isinstance(parent, dict) else None
        if isinstance(object_id, str):
            relationships.append((object_id, parent_id if isinstance(parent_id, str) else None))
        for child in item.values():
            visit(child)

    visit(value)
    selected = {target_id}
    changed = True
    while changed:
        changed = False
        for object_id, parent_id in relationships:
            if parent_id in selected and object_id not in selected:
                selected.add(object_id)
                changed = True
    return selected


def _object_structure(value: Any) -> dict[str, tuple[str | None, str | None]]:
    """Return each visible object's structural parent and physical object type."""

    found: dict[str, tuple[str | None, str | None]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        object_id = item.get("object_id")
        parent = item.get("parent_context")
        parent_id = parent.get("object_id") if isinstance(parent, dict) else None
        object_type = item.get("type")
        if isinstance(object_id, str):
            found[object_id] = (
                parent_id if isinstance(parent_id, str) else None,
                object_type if isinstance(object_type, str) else None,
            )
        for child in item.values():
            visit(child)

    visit(value)
    return found


def _translate_operation(operation: JsonObject) -> JsonObject:
    if operation.get("action") == "register_body_member":
        return {
            "action": "materialize_structure",
            "object_ref": {"object_id": operation.get("object_id")},
            "field_id": "body.chapters",
            "members": [
                {
                    "object_ref": {"object_id": operation.get("object_id")},
                    "field_id": operation.get("field_id"),
                    **(
                        {"effective_format": operation["effective_format"]}
                        if isinstance(operation.get("effective_format"), dict)
                        else {}
                    ),
                }
            ],
        }
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
                "object_ref": {"object_id": entry.get("object_id")},
                "level": entry.get("level"),
            }
            for entry in operation.get("entries", [])
            if isinstance(entry, dict)
        ]
    return translated


def _translate_operations(
    operations: list[JsonObject],
    visible_context: JsonObject,
) -> list[JsonObject]:
    """Collapse body-role declarations into one application-owned structure edit."""

    document_order: dict[str, int] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if not isinstance(value, dict):
            return
        object_id = value.get("object_id")
        order = value.get("document_order")
        if isinstance(object_id, str) and isinstance(order, int):
            document_order.setdefault(object_id, order)
        for child in value.values():
            visit(child)

    visit(visible_context)
    registrations = [
        (index, item)
        for index, item in enumerate(operations)
        if item.get("action") == "register_body_member"
    ]
    if not registrations:
        return [_translate_operation(item) for item in operations]
    registrations.sort(
        key=lambda pair: (
            document_order.get(str(pair[1].get("object_id", "")), 10**9),
            pair[0],
        )
    )
    members = [
        {
            "object_ref": {"object_id": item.get("object_id")},
            "field_id": item.get("field_id"),
            **(
                {"effective_format": item["effective_format"]}
                if isinstance(item.get("effective_format"), dict)
                else {}
            ),
        }
        for _, item in registrations
    ]
    first_registration_index = min(index for index, _ in registrations)
    translated: list[JsonObject] = []
    for index, item in enumerate(operations):
        if index == first_registration_index:
            translated.append(
                {
                    "action": "materialize_structure",
                    "object_ref": members[0]["object_ref"],
                    "field_id": "body.chapters",
                    "members": members,
                }
            )
        if item.get("action") != "register_body_member":
            translated.append(_translate_operation(item))
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
    if "materialize_structure" in actions:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_operation_application_owned",
            message=(
                "The application owns body.chapters creation, lookup, merge, ordering, and "
                "expansion. Submit register_body_member for one visible semantic role."
            ),
            suggested_actions=("register_body_member",),
        )
    standalone_body_members = [
        item
        for item in direct
        if item.get("action") == "materialize_slot"
        and (semantic := semantic_object_type(str(item.get("field_id", "")))) is not None
        and semantic.parent_type == "body.chapters"
    ]
    if standalone_body_members:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_heading_requires_structure",
            message=(
                "A reusable body member declares body.chapters as its parent and cannot be "
                "materialized as a standalone slot. Register the visible semantic role with "
                "register_body_member; the application creates or expands the one structure."
            ),
            suggested_actions=("register_body_member",),
        )
    registrations = [
        item for item in direct if item.get("action") == "register_body_member"
    ]
    for item in registrations:
        field_id = item.get("field_id")
        semantic = semantic_object_type(str(field_id or ""))
        if semantic is None or semantic.parent_type != "body.chapters":
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="body_member_registration_invalid",
                message="register_body_member requires one offered body member field ID.",
            )
        checkpoint = work_item.get("checkpoint_summary")
        gate = checkpoint.get("body_structure_gate") if isinstance(checkpoint, dict) else None
        counts = gate.get("member_field_counts") if isinstance(gate, dict) else None
        if isinstance(counts, dict) and int(counts.get(str(field_id), 0) or 0) > 0:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="body_member_already_registered",
                message=(
                    f"{field_id} already has its one reusable representative. Preserve fixed "
                    "content or remove this redundant sample; do not locate or edit a structure."
                ),
                suggested_actions=("remove_redundant_sample_or_preserve_fixed_content",),
            )
    if kind == "generated_content" and actions != {"refresh_toc"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="generated_content_action_invalid",
            message="The generated-content work item accepts exactly one refresh_toc action.",
        )
    if kind == "generated_content" and any(
        not set(item).issubset({"action", "object_id", "entries"}) for item in direct
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="generated_content_parameters_application_owned",
            message=(
                "refresh_toc accepts action, the supplied target object_id, and Agent-selected "
                "entries with levels. Field IDs and formatting remain application-owned."
            ),
        )
    if kind == "generated_content":
        operation = direct[0]
        entries = operation.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="generated_content_entries_missing",
                message="refresh_toc requires Agent-selected title entries and levels.",
            )
        selected_ids = {
            entry.get("object_id")
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("object_id"), str)
        }
        required_ids = {
            candidate.get("object_id")
            for candidate in work_item.get("required_body_heading_candidates", [])
            if isinstance(candidate, dict)
            and isinstance(candidate.get("object_id"), str)
        }
        if not required_ids.issubset(selected_ids):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="generated_content_required_entries_missing",
                message=(
                    "Every required body-heading candidate reflects an earlier Agent semantic "
                    "decision and must remain in the refreshed TOC."
                ),
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
    offered_fields_by_object: dict[str, set[str]] = field(default_factory=dict)
    allowed_object_ids: set[str] = field(default_factory=set)
    visible_object_structure: dict[str, tuple[str | None, str | None]] = field(
        default_factory=dict
    )
    protected_slot_object_ids: set[str] = field(default_factory=set)
    declared_apply_fields: set[tuple[str, str]] | None = None
    submission: JsonObject | None = None
    ambiguity: JsonObject | None = None
    post_region_ref: str | None = None
    mutated: bool = False
    navigation_done: bool = False
    agent_work_item: JsonObject = field(init=False)

    def __post_init__(self) -> None:
        self.agent_work_item = _bounded_work_item_payload(self.work_item)
        self.register_object_payload(self.agent_work_item)
        for object_id, _ in _objects(self.agent_work_item):
            self.allowed_object_ids.add(object_id)
        generated_field = self.work_item.get("field_id")
        if isinstance(generated_field, str):
            self.offered_field_ids.add(generated_field)

    def offer_fields(
        self,
        object_id: str,
        field_ids: set[str],
        *,
        descendants: Any = None,
    ) -> None:
        """Bind Registry candidates to their queried object and visible descendants only."""

        if not field_ids:
            return
        self.offered_field_ids.update(field_ids)
        eligible = _target_and_descendant_ids(descendants, object_id)
        for candidate_id in eligible:
            self.offered_fields_by_object.setdefault(candidate_id, set()).update(field_ids)

    def register_object_payload(self, value: Any) -> None:
        """Remember visible interfaces that a semantic Agent may inspect but not mutate."""

        self.visible_object_structure.update(_object_structure(value))

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
            parent = item.get("parent_context")
            if isinstance(object_id, str) and (
                isinstance(item.get("slot"), dict)
                or (isinstance(parent, dict) and isinstance(parent.get("slot"), dict))
            ):
                self.protected_slot_object_ids.add(object_id)
            for child in item.values():
                visit(child)

        visit(value)

    def validate_agent_mutation_targets(self, operations: list[JsonObject]) -> None:
        for operation in operations:
            if operation.get("action") in {"materialize_structure", "refresh_toc"}:
                continue
            object_id = operation.get("object_id")
            if isinstance(object_id, str) and object_id in self.protected_slot_object_ids:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="materialized_slot_read_only",
                    message=(
                        "An already materialized fill interface and its descendants are "
                        "read-only to later Agent decisions. Preserve its visible placeholder; "
                        "only application-owned cleanup or structure promotion may replace it."
                    ),
                )

    def validate_parent_materialization_contract(
        self,
        operations: list[JsonObject],
    ) -> None:
        """Reject a parent slot that would erase unlisted fixed child content."""

        removed_ids = {
            operation.get("object_id")
            for operation in operations
            if operation.get("action") == "remove_object"
            and isinstance(operation.get("object_id"), str)
        }
        for operation in operations:
            parent_id = operation.get("object_id")
            if operation.get("action") != "materialize_slot" or not isinstance(
                parent_id, str
            ):
                continue
            _, object_type = self.visible_object_structure.get(parent_id, (None, None))
            if object_type in {"run", "sdt"}:
                continue
            child_ids = {
                object_id
                for object_id, (candidate_parent, _candidate_type) in (
                    self.visible_object_structure.items()
                )
                if candidate_parent == parent_id
            }
            explicitly_removed_children = child_ids & removed_ids
            if explicitly_removed_children and explicitly_removed_children != child_ids:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="parent_materialization_discards_unlisted_children",
                    message=(
                        "Materializing a parent replaces all of its child content. This batch "
                        "removes only some visible children, so executing it would also erase "
                        "unlisted fixed content. Materialize the exact variable child run(s); "
                        "when one field is split across sibling runs, submit that field on the "
                        "variable runs and the Tool will collapse them into one interface."
                    ),
                    suggested_actions=("materialize_exact_variable_child_runs",),
                )

    def validate_field_assignments(self, operations: list[JsonObject]) -> None:
        requested_assignments = {
            assignment
            for item in operations
            for assignment in _operation_field_assignments(item)
        }
        mismatched_assignments = {
            (object_id, field_id)
            for object_id, field_id in requested_assignments
            if field_id not in self.offered_fields_by_object.get(object_id, set())
        }
        if mismatched_assignments:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="field_not_offered_for_object",
                message=(
                    "Each field candidate is bound to the object queried for it and that "
                    "object's visible descendants. Request candidates for the exact target "
                    "object; a candidate returned for a sibling cannot be reused here."
                ),
                suggested_actions=("request_exact_object_field_candidates",),
            )

    def validate_retry_field_contract(self, operations: list[JsonObject]) -> None:
        declared: set[tuple[str, str]] = set()
        for operation in operations:
            for object_id, field_id in _operation_field_assignments(operation):
                parent_id, object_type = self.visible_object_structure.get(
                    object_id,
                    (None, None),
                )
                anchor_id = parent_id if object_type == "run" and parent_id else object_id
                declared.add((field_id, anchor_id))
        if self.declared_apply_fields is None:
            self.declared_apply_fields = declared
            return
        if not self.declared_apply_fields.issubset(declared):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="retry_dropped_declared_fields",
                message=(
                    "A corrected retry must preserve every logical field responsibility "
                    "declared in earlier field-valid apply attempts. Multiple sibling runs "
                    "carrying one field count as one responsibility. Correct object targets "
                    "or operation shape, and add newly required responsibilities, without "
                    "dropping any responsibility already declared."
                ),
                suggested_actions=("resubmit_all_declared_field_responsibilities",),
            )
        self.declared_apply_fields = declared

    def prepare_apply_operations(
        self,
        operations: list[JsonObject],
    ) -> tuple[list[JsonObject], list[JsonObject], set[tuple[str, str]] | None]:
        """Validate one retry transaction without retaining failed declarations."""

        prior_declared_fields = (
            set(self.declared_apply_fields)
            if self.declared_apply_fields is not None
            else None
        )
        try:
            self.validate_retry_field_contract(operations)
            self.validate_field_assignments(operations)
            normalized, absorptions = self.normalize_split_run_slots(operations)
        except ToolFailure:
            self.declared_apply_fields = prior_declared_fields
            raise
        return normalized, absorptions, prior_declared_fields

    def normalize_split_run_slots(
        self,
        operations: list[JsonObject],
    ) -> tuple[list[JsonObject], list[JsonObject]]:
        """Collapse one field split across sibling runs into one fill interface."""

        retained_by_group: dict[tuple[str, str], str] = {}
        normalized: list[JsonObject] = []
        absorbed: list[JsonObject] = []
        for operation in operations:
            object_id = operation.get("object_id")
            field_id = operation.get("field_id")
            parent_id, object_type = self.visible_object_structure.get(
                object_id if isinstance(object_id, str) else "",
                (None, None),
            )
            if not (
                operation.get("action") == "materialize_slot"
                and isinstance(object_id, str)
                and isinstance(field_id, str)
                and isinstance(parent_id, str)
                and object_type == "run"
            ):
                normalized.append(operation)
                continue
            group = (parent_id, field_id)
            retained_object_id = retained_by_group.get(group)
            if retained_object_id is None:
                retained_by_group[group] = object_id
                normalized.append(operation)
                continue
            normalized.append({"action": "remove_object", "object_id": object_id})
            absorbed.append(
                {
                    "action": "materialize_slot",
                    "field_id": field_id,
                    "object_id": object_id,
                    "absorbed_into_object_id": retained_object_id,
                    "reason": "same_field_split_across_sibling_runs",
                }
            )
        return normalized, absorbed

    def rollback(self) -> None:
        if self.mutated:
            self.service.restore_workflow_progress(self.start_progress)
            self.mutated = False

    def initial_candidates(self) -> list[JsonObject]:
        """Prefetch Registry candidates for every visible top-level object."""

        region = self.agent_work_item.get("region")
        target = region.get("target") if isinstance(region, dict) else None
        if not isinstance(target, dict):
            return []
        adjacent = region.get("adjacent_objects")
        visible = [target]
        if isinstance(adjacent, list):
            visible.extend(
                item
                for item in adjacent
                if isinstance(item, dict) and item.get("type") != "run"
            )
        candidates: list[JsonObject] = []
        seen: set[str] = set()
        candidate_provider = getattr(
            self.service,
            "registry_candidates_for_text",
            None,
        )
        for item in visible:
            object_id = item.get("object_ref", item.get("object_id"))
            if isinstance(object_id, dict):
                object_id = object_id.get("object_id")
            text = item.get("text")
            if (
                not isinstance(object_id, str)
                or object_id in seen
            ):
                continue
            seen.add(object_id)
            if not isinstance(text, str) or not text.strip():
                candidates.append({"object_id": object_id, "matches": []})
                continue
            try:
                if callable(candidate_provider):
                    matches = candidate_provider(
                        text,
                        f"{text} {''.join(text.split())}",
                        limit=5,
                    )
                else:
                    matches = self.service.registry.search(
                        f"{text} {''.join(text.split())}",
                        limit=5,
                    )
            except ToolFailure:
                matches = []
            matches, already_registered = self._filter_registered_body_candidates(
                matches,
                object_id=object_id,
            )
            field_ids = {
                str(match["field_id"])
                for match in matches
                if isinstance(match.get("field_id"), str)
            }
            self.offer_fields(
                object_id,
                field_ids,
                descendants=self.agent_work_item,
            )
            candidates.append(
                {
                    "object_id": object_id,
                    "matches": [_agent_payload(match) for match in matches],
                    **(
                        {
                            "already_registered_body_roles": already_registered,
                            "guidance": (
                                "These body roles already have their single representative. "
                                "Remove this object only if it is a redundant sample; otherwise "
                                "preserve it. Do not search for or edit the structure container."
                            ),
                        }
                        if already_registered
                        else {}
                    ),
                }
            )
        return candidates

    def _filter_registered_body_candidates(
        self,
        matches: Any,
        *,
        object_id: str | None = None,
    ) -> tuple[list[JsonObject], list[str]]:
        checkpoint = self.work_item.get("checkpoint_summary")
        gate = checkpoint.get("body_structure_gate") if isinstance(checkpoint, dict) else None
        counts = gate.get("member_field_counts") if isinstance(gate, dict) else None
        registered = {
            str(field_id)
            for field_id, count in (counts.items() if isinstance(counts, dict) else [])
            if isinstance(count, int) and count > 0
        }
        values = [
            dict(item)
            for item in matches
            if isinstance(item, dict) and item.get("field_id") != "body.chapters"
        ]
        duplicates = sorted(
            {
                str(item["field_id"])
                for item in values
                if isinstance(item.get("field_id"), str)
                and item["field_id"] in registered
                and (semantic := semantic_object_type(str(item["field_id"]))) is not None
                and semantic.parent_type == "body.chapters"
            }
        )
        return (
            [item for item in values if item.get("field_id") not in set(duplicates)],
            duplicates,
        )


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
    (
        "Return the local semantic crop selected by the application, its image, child runs, "
        "and Registry candidates for every visible top-level object."
    ),
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
        "from candidates returned for the exact edited object or its supplied child run. For a "
        "body role, use register_body_member with only that "
        "object and field; the application owns the unique body.chapters structure. For "
        "generated_content, submit exactly one "
        "refresh_toc operation with the supplied target object_id and Agent-selected entries "
        "at levels 1-3; include every required body-heading candidate. The "
        "application performs and verifies edits."
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
    state_or_provider: SemanticWorkItemState | Callable[[], SemanticWorkItemState],
) -> McpSdkServerConfig:
    """Build a server whose application-owned binding may advance between SDK queries."""

    def current_state() -> SemanticWorkItemState:
        state = state_or_provider() if callable(state_or_provider) else state_or_provider
        if not isinstance(state, SemanticWorkItemState):
            raise ToolFailure(
                status="error",
                origin="environment",
                code="template_task_not_bound",
                message="Template tools require a current application-bound work item.",
            )
        return state

    async def get_current(_args: dict[str, Any]) -> dict[str, Any]:
        state = current_state()
        payload = {
            "schema_version": 1,
            "status": "ok",
            "work_item": state.agent_work_item,
            "field_candidates": state.initial_candidates(),
            "candidate_protocol": {
                "initial_scope": "all_visible_top_level_objects",
                "sibling_rule": (
                    "Every visible top-level object has an explicit candidate result, including "
                    "an empty matches list. Use request_current_context only for evidence beyond "
                    "the supplied crop, not as a required candidate-discovery ceremony."
                ),
            },
        }
        return tool_result(payload, image_paths=state.images)

    async def request_context(args: dict[str, Any]) -> dict[str, Any]:
        try:
            state = current_state()
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
                state.register_object_payload(public_search)
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
                    state.register_object_payload(public_focus)
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
                    for item in public_registry.get("results", []):
                        if not isinstance(item, dict):
                            continue
                        filtered, duplicates = state._filter_registered_body_candidates(
                            item.get("matches", []),
                            object_id=object_id,
                        )
                        item["matches"] = filtered
                        if duplicates:
                            item["already_registered_body_roles"] = duplicates
                            item["guidance"] = (
                                "Each listed role already has its one representative. Remove "
                                "this object only when it is a redundant sample; otherwise "
                                "preserve it. Do not search for a structure container."
                            )
                    result["field_candidates"] = public_registry
                    for item in public_registry.get("results", []):
                        if not isinstance(item, dict):
                            continue
                        field_ids = {
                            str(match["field_id"])
                            for match in item.get("matches", [])
                            if isinstance(match, dict)
                            and isinstance(match.get("field_id"), str)
                        }
                        state.offer_fields(
                            object_id,
                            field_ids,
                            descendants=(
                                result.get("visual_context")
                                if isinstance(result.get("visual_context"), dict)
                                else None
                            ),
                        )
            return tool_result(result, image_paths=images)
        except ToolFailure as error:
            return failure_result(error)
        except Exception:
            return unexpected_failure_result()

    async def submit(args: dict[str, Any]) -> dict[str, Any]:
        try:
            state = current_state()
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
            state.validate_agent_mutation_targets(direct_operations)
            state.validate_parent_materialization_contract(direct_operations)
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
            direct_operations, split_run_absorptions, prior_declared_fields = (
                state.prepare_apply_operations(
                direct_operations
                )
            )
            translated = {
                "operations": _translate_operations(
                    direct_operations,
                    state.agent_work_item,
                )
            }
            try:
                structured, images = state.service.edit(translated)
            except ToolFailure:
                state.declared_apply_fields = prior_declared_fields
                raise
            if split_run_absorptions:
                effects = structured.get("effects")
                if isinstance(effects, dict):
                    existing = effects.get("absorbed_operations")
                    effects["absorbed_operations"] = [
                        *(existing if isinstance(existing, list) else []),
                        *split_run_absorptions,
                    ]
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
        state = current_state()
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
