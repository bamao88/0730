"""Object-driven template preparation without Agent-authored plans.

Every document version is immutable and addressed by its SHA-256.  The Agent
works on one opaque OfficeCLI object reference at a time; direct edits create a
new version and deliberately stale every reference from the prior version.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from docfit.fields import FieldRegistrySnapshot
from docfit.styles.capture import (
    capture_template_style_contracts,
    capture_template_style_observations,
)
from docfit.styles.profiles import DEFAULT_STYLE_PROPERTY_PROFILES
from docfit.template.object_mutation import (
    ObjectMutation,
    StructureMember,
    TocEntry,
    mutate_objects,
)
from docfit.template.semantic_types import (
    require_body_member_type,
    require_body_structure_type,
    semantic_object_type,
)
from docfit.tools.inspection import (
    InspectedObject,
    Inspection,
    inspect_document,
    resolve_object_ref,
)
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_file,
)
from docfit.visual.service import VisualEvidenceService

_DOCUMENT_REF = re.compile(r"^document:v1:([0-9a-f]{64})$")
_REGION_REF = re.compile(r"^region:v1:([0-9a-f]{64}):(\d+):(obj-[0-9a-f]{24})$")
_TEMPLATE_SELECTOR = "paragraph, table, picture, run, sdt, shape"
_EDITABLE_KINDS = {"paragraph", "run", "table", "picture", "sdt", "shape"}
_MAX_SEARCH_RESULTS = 5
_MAX_BATCH_OPERATIONS = 32
_MAX_TOC_TITLE_CANDIDATES = 24
_REGION_SOURCE_OBJECTS = 6
_REGION_LAYOUT_STRATEGY = "page-proximity-v1"
_REGION_MAX_HEIGHT_POINTS = 300.0
_REGION_MAX_VERTICAL_GAP_POINTS = 120.0
_REGION_ADJACENT_OBJECTS = 32
_REGION_PADDING = 160
_TOC_SAMPLE_MARKER = re.compile(r"(?:X{2,}|×{2,})", re.IGNORECASE)
_DURABLE_EDIT_INTENT_ACTIONS = {
    "materialize_slot",
    "materialize_structure",
    "refresh_toc",
}
_MAX_PENDING_EDIT_INTENTS = 8

_FIELD_STYLE_ROLES: dict[str, tuple[str, str]] = {
    "body.heading.level1": ("style.body.heading.1", "heading"),
    "body.heading.level2": ("style.body.heading.2", "heading"),
    "body.heading.level3": ("style.body.heading.3", "heading"),
    "body.heading.level4": ("style.body.heading.4", "heading"),
    "body.heading.level5": ("style.body.heading.5", "heading"),
    "body.paragraph": ("style.body.paragraph", "paragraph"),
    "body.numbered_list_item": ("style.body.numbered_list_item", "paragraph"),
    "body.inline_emphasis": ("style.inline.emphasis", "character"),
    "body.inline_quote": ("style.inline.quote", "character"),
    "body.block_quote": ("style.body.block_quote", "paragraph"),
    "body.figure.caption": ("style.caption.figure", "caption"),
    "body.equation": ("style.equation.block", "equation"),
    "body.table.caption": ("style.caption.table", "caption"),
    "body.table.note": ("style.table.note", "paragraph"),
}
_BODY_COMPONENT_STYLE_ROLES: tuple[tuple[str, str, str], ...] = (
    ("body.table", "style.table.header", "table_cell"),
    ("body.table", "style.table.body", "table_cell"),
)


def _normalize(value: str) -> str:
    return "".join(value.split()).casefold()


def _document_ref(document_hash: str) -> str:
    return f"document:v1:{document_hash}"


def _parent_paragraph_locator(locator: str) -> str | None:
    match = re.match(r"^(.*?/p(?:\[@paraId=[^]]+]|\[\d+]))(?:/.*)?$", locator)
    return match.group(1) if match else None


def _placeholder_text(field: JsonObject) -> str:
    label = str(field.get("label", field["field_id"]))
    return f"【{label}】"


def _agent_object_ref(item: InspectedObject) -> JsonObject:
    return {"object_id": str(item.object_ref["object_id"])}


def _agent_object(inspection: Inspection, item: InspectedObject) -> JsonObject:
    value = VisualEvidenceService._compact_page_object(item)
    value["object_ref"] = _agent_object_ref(item)
    value["document_order"] = next(
        index for index, candidate in enumerate(inspection.objects) if candidate is item
    )
    return value


def _context_parent(
    inspection: Inspection,
    item: InspectedObject,
) -> InspectedObject | None:
    """Return the closest useful Word container for one locally exposed object."""

    candidates = [
        candidate
        for candidate in inspection.objects
        if candidate is not item
        and item.locator.startswith(f"{candidate.locator}/")
        and candidate.kind in {"paragraph", "table", "sdt", "shape"}
    ]
    return max(candidates, key=lambda candidate: len(candidate.locator), default=None)


def _agent_context_object(
    inspection: Inspection,
    item: InspectedObject,
) -> JsonObject:
    """Expose one object plus only the immediate context needed to interpret it."""

    value = _agent_object(inspection, item)
    parent = _context_parent(inspection, item)
    if parent is not None:
        value["parent_context"] = _agent_object(inspection, parent)
    return value


def _with_semantic_type(field: JsonObject) -> JsonObject:
    value = dict(field)
    semantic = semantic_object_type(str(field.get("field_id", "")))
    if semantic is not None:
        value["semantic_object_type"] = semantic.public()
    return value


def _school_style_slot_metadata(
    *,
    field_id: str,
    slot_id: str,
    content_type: str,
) -> JsonObject:
    binding = _FIELD_STYLE_ROLES.get(field_id)
    if binding is None:
        if content_type not in {"text", "rich_text"}:
            return {"handling": "non_style"}
        binding = (f"style.slot.{slot_id}", "paragraph")
    style_role_id, style_role_type = binding
    profile = DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type(style_role_type)
    return {
        "handling": "styled",
        "style_role_id": style_role_id,
        "style_role_type": style_role_type,
        "property_profile_ref": profile.ref().as_dict(),
    }


def _expected_body_style_roles(published_slots: list[JsonObject]) -> list[JsonObject]:
    observed_role_ids = {
        str(item["style_role_id"])
        for item in published_slots
        if isinstance(item.get("style_role_id"), str)
    }
    expected: list[JsonObject] = []
    for field_id, (style_role_id, style_role_type) in _FIELD_STYLE_ROLES.items():
        if not field_id.startswith("body.") or style_role_id in observed_role_ids:
            continue
        profile = DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type(style_role_type)
        expected.append(
            {
                "field_id": field_id,
                "slot_id": f"expected.{field_id}",
                "style_role_id": style_role_id,
                "style_role_type": style_role_type,
                "property_profile_ref": profile.ref().as_dict(),
            }
        )
    for field_id, style_role_id, style_role_type in _BODY_COMPONENT_STYLE_ROLES:
        if style_role_id in observed_role_ids:
            continue
        profile = DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type(style_role_type)
        expected.append(
            {
                "field_id": field_id,
                "slot_id": f"expected.{style_role_id}",
                "style_role_id": style_role_id,
                "style_role_type": style_role_type,
                "property_profile_ref": profile.ref().as_dict(),
            }
        )
    return expected


def _effective_format(value: Any, *, required: bool = False) -> JsonObject:
    if value is None and not required:
        return {}
    if not isinstance(value, dict) or (required and not value):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message="An effective-format operation requires at least one supported outcome.",
        )
    unknown = set(value) - {"color", "underline"}
    if (
        unknown
        or value.get("color", "black") != "black"
        or value.get("underline", "none") != "none"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message=(
                "Template Tool v5 currently supports effective color=black and "
                "underline=none outcomes."
            ),
        )
    return {key: str(value[key]) for key in ("color", "underline") if key in value}


def _edit_operations(args: dict[str, Any]) -> list[JsonObject]:
    """Validate the public atomic operation list before resolving Word objects."""

    if set(args) != {"operations"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_edit_batch_invalid",
            message="template_edit accepts exactly one operations array.",
        )
    raw_operations = args.get("operations")
    if not isinstance(raw_operations, list) or any(
        not isinstance(item, dict) for item in raw_operations
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_edit_batch_invalid",
            message="operations must be an array of direct action objects.",
        )
    operations = [dict(item) for item in raw_operations]
    if not 1 <= len(operations) <= _MAX_BATCH_OPERATIONS:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_edit_operations_invalid",
            message="template_edit requires one through thirty-two total operations.",
        )
    return operations


def _normalize_prepared_operations(
    prepared: list[JsonObject],
    mutations: list[ObjectMutation],
) -> tuple[list[JsonObject], list[ObjectMutation], list[JsonObject]]:
    """Absorb redundant nested edits and reject only contradictory intent."""

    absorbed: dict[int, JsonObject] = {}

    def absorb(index: int, owner: int, reason: str) -> None:
        if index in absorbed:
            return
        absorbed[index] = {
            "action": prepared[index]["action"],
            "target": prepared[index]["target"],
            "absorbed_by": {
                "action": prepared[owner]["action"],
                "target": prepared[owner]["target"],
            },
            "reason": reason,
        }

    def conflict(parent_index: int, child_index: int) -> None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="batch_operations_conflict",
            message=(
                "The batch removes or replaces an ancestor while also requiring a descendant "
                "to survive as materialized/generated content. Split or revise those semantic "
                "decisions; redundant descendant cleanup is absorbed automatically. "
                f"Conflict: {prepared[parent_index]['action']} ancestor and "
                f"{prepared[child_index]['action']} descendant."
            ),
        )

    def merge_effective_format(format_index: int, owner_index: int) -> None:
        outcomes = dict(prepared[format_index].get("effective_format", {}))
        owner_outcomes = dict(prepared[owner_index].get("effective_format", {}))
        owner_outcomes.update(outcomes)
        prepared[owner_index]["effective_format"] = owner_outcomes
        mutations[owner_index] = replace(
            mutations[owner_index],
            effective_format=tuple(owner_outcomes.items()),
        )
        absorb(format_index, owner_index, "effective_format_merged_into_compound_action")

    harmless_under_removal = {
        "remove_object",
        "clear_content",
        "normalize_effective_format",
        "ensure_page_start",
    }
    materializing = {"materialize_slot", "materialize_structure", "refresh_toc"}

    # A structure already materializes each declared member as a slot. Agents may
    # still state the same member decisions explicitly in the surrounding batch;
    # preserve the explicit slot id/format and absorb the redundant operation.
    for structure_index, structure in enumerate(prepared):
        if structure.get("action") != "materialize_structure":
            continue
        members = [item for item in structure.get("members", []) if isinstance(item, dict)]
        structure_mutation = mutations[structure_index]
        updated_members = list(structure_mutation.structure_members)
        for slot_index, slot in enumerate(prepared):
            if slot_index == structure_index or slot_index in absorbed:
                continue
            if slot.get("action") != "materialize_slot":
                continue
            slot_locator = str(slot.get("target_locator", ""))
            member_index = next(
                (
                    index
                    for index, member in enumerate(members)
                    if slot_locator == str(member.get("target_locator", ""))
                    or slot_locator.startswith(f"{member.get('target_locator', '')}/")
                ),
                None,
            )
            if member_index is None:
                continue
            member = members[member_index]
            slot_field = slot.get("field")
            member_field = member.get("field")
            if (
                not isinstance(slot_field, dict)
                or not isinstance(member_field, dict)
                or slot_field.get("field_id") != member_field.get("field_id")
            ):
                conflict(structure_index, slot_index)
            merged_format = dict(member.get("effective_format", {}))
            merged_format.update(slot.get("effective_format", {}))
            member["effective_format"] = merged_format
            member["slot_id"] = slot.get("slot_id")
            member["effective_before"] = dict(slot.get("effective_before", {}))
            member_mutation = updated_members[member_index]
            updated_members[member_index] = replace(
                member_mutation,
                slot_id=str(slot.get("slot_id")),
                effective_format=tuple(merged_format.items()),
            )
            absorb(slot_index, structure_index, "materialization_absorbed_by_structure_member")
        mutations[structure_index] = replace(
            structure_mutation,
            structure_members=tuple(updated_members),
        )

    for first_index, first in enumerate(prepared):
        if first_index in absorbed:
            continue
        first_locator = str(first.get("target_locator", ""))
        for second_index in range(first_index + 1, len(prepared)):
            if second_index in absorbed:
                continue
            second = prepared[second_index]
            second_locator = str(second.get("target_locator", ""))
            if first_locator == second_locator:
                first_action = str(first["action"])
                second_action = str(second["action"])
                if first_action == second_action:
                    absorb(second_index, first_index, "duplicate_operation")
                elif first_action == "remove_object" and second_action in harmless_under_removal:
                    absorb(second_index, first_index, "ancestor_removal")
                elif second_action == "remove_object" and first_action in harmless_under_removal:
                    absorb(first_index, second_index, "ancestor_removal")
                    break
                elif (
                    first_action in materializing and second_action == "clear_content"
                ) or (
                    second_action in materializing and first_action == "clear_content"
                ):
                    owner_index = (
                        first_index if first_action in materializing else second_index
                    )
                    cleanup_index = (
                        second_index if first_action in materializing else first_index
                    )
                    absorb(
                        cleanup_index,
                        owner_index,
                        "materialized_target_replaces_content",
                    )
                    if cleanup_index == first_index:
                        break
                elif (
                    first_action in materializing and second_action == "remove_object"
                ) or (
                    second_action in materializing and first_action == "remove_object"
                ):
                    conflict(first_index, second_index)
                elif {first_action, second_action} == {
                    "normalize_effective_format",
                    "ensure_page_start",
                }:
                    continue
                elif "normalize_effective_format" in {first_action, second_action}:
                    owner_index = (
                        second_index
                        if first_action == "normalize_effective_format"
                        else first_index
                    )
                    format_index = (
                        first_index
                        if first_action == "normalize_effective_format"
                        else second_index
                    )
                    if prepared[owner_index]["action"] in {
                        "materialize_slot",
                        "refresh_toc",
                    }:
                        merge_effective_format(format_index, owner_index)
                    else:
                        conflict(first_index, second_index)
                else:
                    conflict(first_index, second_index)
                continue
            if second_locator.startswith(f"{first_locator}/"):
                parent_index, child_index = first_index, second_index
            elif first_locator.startswith(f"{second_locator}/"):
                parent_index, child_index = second_index, first_index
            else:
                continue
            parent_action = str(prepared[parent_index]["action"])
            child_action = str(prepared[child_index]["action"])
            if parent_action == "remove_object":
                if child_action in harmless_under_removal:
                    absorb(child_index, parent_index, "ancestor_removal")
                else:
                    conflict(parent_index, child_index)
            elif parent_action in materializing and child_action in {
                "remove_object",
                "clear_content",
            }:
                absorb(child_index, parent_index, "materialized_parent_replaces_content")
            elif child_action == "normalize_effective_format" and parent_action in {
                "materialize_slot",
                "refresh_toc",
            }:
                merge_effective_format(child_index, parent_index)

    for index, item in enumerate(prepared):
        if index in absorbed or item.get("action") not in {"remove_object", "clear_content"}:
            continue
        locator = str(item.get("target_locator", ""))
        owner = next(
            (
                owner_index
                for owner_index, owner in enumerate(prepared)
                if owner.get("action") in {"materialize_slot", "materialize_structure"}
                and any(
                    locator == materialized or locator.startswith(f"{materialized}/")
                    for materialized in (
                        [str(owner.get("target_locator", ""))]
                        if owner.get("action") == "materialize_slot"
                        else [
                            str(member.get("target_locator", ""))
                            for member in owner.get("members", [])
                            if isinstance(member, dict)
                        ]
                    )
                )
            ),
            None,
        )
        if owner is not None and owner != index:
            absorb(index, owner, "materialized_parent_replaces_content")

    retained = [
        (item, mutation)
        for index, (item, mutation) in enumerate(zip(prepared, mutations, strict=True))
        if index not in absorbed
    ]
    return (
        [item for item, _ in retained],
        [mutation for _, mutation in retained],
        [absorbed[index] for index in sorted(absorbed)],
    )


def _knowledge_signals(operations: list[JsonObject]) -> list[str]:
    signals: set[str] = set()
    actions = {str(item.get("action")) for item in operations}
    if actions & {"normalize_effective_format"} or any(
        item.get("effective_format") for item in operations
    ):
        signals.add("effective-style")
    if "ensure_page_start" in actions:
        signals.add("logical-page-starts")
    if "materialize_structure" in actions:
        signals.add("body-structure")
    if "refresh_toc" in actions:
        signals.add("generated-content")
    if actions & {"remove_object", "clear_content"}:
        signals.add("object-safety")
    return sorted(signals)


def _context_knowledge_signals(objects: list[InspectedObject]) -> list[str]:
    """Route at most one objective mechanism card for the current local decision."""

    if any(
        item.style and item.style.casefold().replace(" ", "").startswith("toc") for item in objects
    ):
        return ["generated-content"]
    collection_markers = (
        "参考文献",
        "附录",
        "致谢",
        "攻读学位期间",
        "在学期间发表",
        "科研成果",
    )

    def is_collection_landmark(item: InspectedObject) -> bool:
        if item.kind != "paragraph":
            return False
        text = item.text.replace(" ", "")
        marker_match = any(text.startswith(marker) for marker in collection_markers)
        if not marker_match:
            return False
        style = (item.style or "").casefold().replace(" ", "")
        return style.startswith("heading") or style.startswith("标题") or len(text) <= 32

    if any(
        is_collection_landmark(item)
        for item in objects
    ):
        return ["collection-and-optional-sections"]
    if any(
        item.kind == "paragraph"
        and item.style
        and (
            item.style.casefold().replace(" ", "").startswith("heading")
            or item.style.replace(" ", "").startswith("标题")
        )
        for item in objects
    ):
        return ["body-structure"]
    if any(
        (
            str(item.format.get("effective.color", "")).casefold()
            not in {"", "#000000", "000000", "black", "auto"}
        )
        or (
            str(item.format.get("effective.underline", "")).casefold()
            not in {"", "none", "false", "0"}
        )
        for item in objects
    ):
        return ["effective-style"]
    if any(
        item.format.get("pageBreakBefore")
        or item.format.get("page_break_before")
        or item.format.get("section")
        for item in objects
    ):
        return ["logical-page-starts"]
    if any(item.kind in {"picture", "shape"} for item in objects):
        return ["object-safety"]
    return []


def _style_signatures(operations: list[JsonObject]) -> list[JsonObject]:
    signatures: list[JsonObject] = []
    for operation in operations:
        candidates = [operation] + [
            member for member in operation.get("members", []) if isinstance(member, dict)
        ]
        for candidate in candidates:
            field = candidate.get("field")
            if not isinstance(field, dict):
                continue
            target = candidate.get("target", {})
            if not isinstance(target, dict):
                continue
            format_value = target.get("format", {})
            signatures.append(
                {
                    "field_id": field.get("field_id"),
                    "object_type": target.get("type"),
                    "style": target.get("style"),
                    "effective_format": {
                        key: value
                        for key, value in format_value.items()
                        if isinstance(key, str) and key.startswith("effective.")
                    }
                    if isinstance(format_value, dict)
                    else {},
                }
            )
    return signatures


def _structural_risks(
    inspection: Inspection,
    operations: list[JsonObject],
) -> list[JsonObject]:
    """Return style/order observations without converting them into semantic gates."""

    risks: list[JsonObject] = []
    order = {item.locator: index for index, item in enumerate(inspection.objects)}
    for operation in operations:
        if operation.get("action") != "materialize_structure":
            continue
        members = [item for item in operation.get("members", []) if isinstance(item, dict)]
        positions = [
            order[locator]
            for member in members
            if isinstance((locator := member.get("target_locator")), str) and locator in order
        ]
        selected_locators = {
            str(member.get("target_locator")) for member in members if member.get("target_locator")
        }
        heading_styles = {
            target.get("style")
            for member in members
            if str(member.get("field", {}).get("field_id", "")).startswith("body.heading.")
            and isinstance((target := member.get("target")), dict)
            and target.get("style")
        }
        if positions and heading_styles:
            between = inspection.objects[min(positions) : max(positions) + 1]
            repeated = [
                item
                for item in between
                if item.locator not in selected_locators
                and item.kind == "paragraph"
                and item.style in heading_styles
                and item.text.strip()
            ]
            if repeated:
                risks.append(
                    {
                        "code": "similar_heading_style_inside_member_span",
                        "severity": "warning",
                        "count": len(repeated),
                        "examples": [item.text[:120] for item in repeated[:3]],
                        "guidance": (
                            "The selected member span contains other visible paragraphs with a "
                            "similar heading style. This is a structural observation; the Agent "
                            "decides whether the representative block is semantically complete."
                        ),
                    }
                )
    return risks


def _semantic_intent_key(operation: JsonObject) -> tuple[str, str] | None:
    action = operation.get("action")
    if action not in _DURABLE_EDIT_INTENT_ACTIONS:
        return None
    field_id = operation.get("field_id")
    if not isinstance(field_id, str) and isinstance(operation.get("field"), dict):
        field_id = operation["field"].get("field_id")
    if action == "refresh_toc" and not isinstance(field_id, str):
        field_id = "generated.toc"
    if not isinstance(field_id, str) or not field_id:
        return None
    return str(action), field_id


def _semantic_intent_richness(intent: JsonObject) -> tuple[int, int]:
    """Prefer the most informative failed attempt for fresh-session recovery."""

    member_types = [
        str(value) for value in intent.get("member_field_ids", []) if isinstance(value, str)
    ]
    retry = intent.get("retry_operation")
    entries = retry.get("entries", []) if isinstance(retry, dict) else []
    return len(set(member_types)), max(len(member_types), len(entries))


def _can_regenerate_pending_content(intents: list[JsonObject]) -> bool:
    """Return whether fresh generated-content refs can resolve every pending intent."""

    return not intents or all(intent.get("action") == "refresh_toc" for intent in intents)


class TemplateWorkspaceService:
    """Thin domain service over shared OfficeCLI and visual evidence."""

    def __init__(
        self,
        *,
        task_root: Path,
        field_registry: Path,
        office: OfficeCliAdapter | None = None,
        visual: VisualEvidenceService | None = None,
    ) -> None:
        self.task_root = task_root.expanduser().resolve(strict=True)
        self.source = (self.task_root / "input" / "school-template.docx").resolve(strict=True)
        self.registry = FieldRegistrySnapshot.load(field_registry)
        self.office = office or OfficeCliAdapter()
        self._visual = visual
        self._source_region_cache: list[list[JsonObject]] | None = None

    @property
    def root(self) -> Path:
        return self.task_root / "work" / ".docfit" / "template-workspace-v1"

    @property
    def versions(self) -> Path:
        return self.root / "versions"

    @property
    def receipts(self) -> Path:
        return self.root / "receipts"

    @property
    def reviews(self) -> Path:
        return self.root / "reviews"

    @property
    def progress_path(self) -> Path:
        return self.root / "task-progress.json"

    @property
    def region_blueprint_path(self) -> Path:
        return self.root / "visual-regions.json"

    @property
    def visual(self) -> VisualEvidenceService:
        if self._visual is None:
            self._visual = VisualEvidenceService(
                self.task_root,
                office=self.office,
                semantic_selector=_TEMPLATE_SELECTOR,
            )
        return self._visual

    def _inspection(self, document: Path) -> Inspection:
        return inspect_document(document, self.office, selector=_TEMPLATE_SELECTOR)

    def _register_source(self) -> tuple[str, Path]:
        source_hash = sha256_file(self.source)
        self.versions.mkdir(parents=True, exist_ok=True)
        target = self.versions / f"{source_hash}.docx"
        if not target.exists():
            temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            shutil.copyfile(self.source, temporary)
            temporary.chmod(0o600)
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            finally:
                temporary.unlink(missing_ok=True)
        if sha256_file(target) != source_hash:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="document_version_hash_mismatch",
                message="An internal template version failed its integrity check.",
            )
        return _document_ref(source_hash), target

    def _read_progress(self, source_hash: str) -> JsonObject:
        if not self.progress_path.exists():
            progress: JsonObject = {
                "schema_version": 1,
                "source_sha256": source_hash,
                "document_sha256": source_hash,
                "region_index": 0,
                "pending_object_ref": None,
                "pending_edit_intents": [],
                "current_region_edited": False,
            }
            self._write_progress(progress)
            return progress
        try:
            value: Any = json.loads(self.progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="template_progress_invalid",
                message="The saved template task progress is unreadable.",
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("source_sha256") != source_hash
            or not isinstance(value.get("document_sha256"), str)
            or not isinstance(value.get("region_index"), int)
            or value["region_index"] < 0
            or (
                value.get("pending_object_ref") is not None
                and not isinstance(value.get("pending_object_ref"), dict)
            )
            or not isinstance(value.get("pending_edit_intents", []), list)
            or any(not isinstance(item, dict) for item in value.get("pending_edit_intents", []))
            or not isinstance(value.get("current_region_edited", False), bool)
        ):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="template_progress_invalid",
                message="The saved template task progress failed its integrity checks.",
            )
        self._resolve_document(_document_ref(str(value["document_sha256"])))
        value.setdefault("pending_edit_intents", [])
        value.setdefault("current_region_edited", False)
        return value

    def _write_progress(self, progress: JsonObject) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.progress_path, progress)

    @staticmethod
    def _intent_already_satisfied(intent: JsonObject, summary: JsonObject) -> bool:
        action = intent.get("action")
        field_id = intent.get("field_id")
        if not isinstance(field_id, str):
            return False
        materialized_fields = summary.get("materialized_fields", {})
        field_ids = set(materialized_fields) if isinstance(materialized_fields, dict) else set()
        if action == "materialize_slot":
            return field_id in field_ids
        if action == "materialize_structure":
            if field_id in field_ids:
                return True
            structures = summary.get("materialized_structures", [])
            requested_members = {
                str(value) for value in intent.get("member_field_ids", []) if isinstance(value, str)
            }
            return (
                isinstance(structures, list)
                and field_id in structures
                and requested_members <= field_ids
            )
        if action == "refresh_toc":
            toc = summary.get("toc")
            return isinstance(toc, dict) and not toc.get("refresh_needed", True)
        return False

    def _reconcile_satisfied_intents(
        self,
        progress: JsonObject,
        inspection: Inspection,
    ) -> JsonObject:
        pending = [
            dict(item)
            for item in progress.get("pending_edit_intents", [])
            if isinstance(item, dict)
        ]
        summary = self._checkpoint_summary(inspection)
        unresolved = [
            intent
            for intent in pending
            if self._intent_field_registered(intent)
            and not self._intent_already_satisfied(intent, summary)
        ]
        if len(unresolved) == len(pending):
            return progress
        reconciled = {**progress, "pending_edit_intents": unresolved}
        self._write_progress(reconciled)
        return reconciled

    def _remaining_pending_intents(
        self,
        progress: JsonObject,
        inspection: Inspection,
        completed_operations: list[JsonObject],
    ) -> list[JsonObject]:
        completed_keys = {
            key for item in completed_operations if (key := _semantic_intent_key(item)) is not None
        }
        summary = self._checkpoint_summary(inspection)
        return [
            {
                key: value
                for key, value in intent.items()
                if key not in {"retry_operation", "document_sha256"}
            }
            for intent in progress.get("pending_edit_intents", [])
            if isinstance(intent, dict)
            and self._intent_field_registered(intent)
            and (intent.get("action"), intent.get("field_id")) not in completed_keys
            and not self._intent_already_satisfied(intent, summary)
        ]

    def _intent_field_registered(self, intent: JsonObject) -> bool:
        field_id = intent.get("field_id")
        if not isinstance(field_id, str):
            return False
        try:
            self.registry.lookup(field_id)
        except ToolFailure:
            return False
        return True

    @staticmethod
    def _pending_intents_for_current_document(
        progress: JsonObject,
        _inspection: Inspection,
    ) -> list[JsonObject]:
        """Expose semantic recovery context without replaying a known-failed tool call."""

        result: list[JsonObject] = []
        for raw in progress.get("pending_edit_intents", []):
            if not isinstance(raw, dict):
                continue
            intent = {
                key: value
                for key, value in raw.items()
                if key not in {"document_sha256", "retry_operation"}
            }
            intent["recovery"] = "re_locate_and_improve"
            result.append(intent)
        return result

    def record_edit_failure(self, args: JsonObject, error: ToolFailure) -> None:
        """Persist unresolved Agent-authored semantic edit intent across fresh sessions."""

        try:
            raw_operations = _edit_operations(args)
        except ToolFailure:
            return
        source_hash = sha256_file(self.source)
        progress = self._read_progress(source_hash)
        _, current_document = self._resolve_document(
            _document_ref(str(progress["document_sha256"]))
        )
        current_summary = self._checkpoint_summary(self._inspection(current_document))
        pending = [
            dict(item)
            for item in progress.get("pending_edit_intents", [])
            if isinstance(item, dict)
        ]
        changed = False
        for raw in raw_operations:
            if not isinstance(raw, dict) or (key := _semantic_intent_key(raw)) is None:
                continue
            try:
                self.registry.lookup(key[1])
            except ToolFailure:
                continue
            target: JsonObject | None = None
            retry_operation: JsonObject | None = None
            try:
                _, _, selected = self._resolve_object(raw.get("object_ref"))
                target = {
                    "type": selected.kind,
                    "text": selected.text[:240],
                }
                references = (
                    [raw.get("object_ref")]
                    + [
                        member.get("object_ref")
                        for member in raw.get("members", [])
                        if isinstance(member, dict)
                    ]
                    + [
                        entry.get("object_ref")
                        for entry in raw.get("entries", [])
                        if isinstance(entry, dict)
                    ]
                )
                for reference in references:
                    self._resolve_object(reference)
                retry_operation = json.loads(json.dumps(raw))
            except ToolFailure:
                pass
            last_failure = {
                "code": error.code,
                "message": error.message,
            }
            if error.code == "field_not_registered":
                last_failure = {
                    "code": "batch_rejected_by_invalid_sibling",
                    "message": (
                        "This registered semantic operation did not commit because another "
                        "operation in the same atomic batch used an unregistered field."
                    ),
                }
            intent: JsonObject = {
                "action": key[0],
                "field_id": key[1],
                "member_field_ids": [
                    str(member["field_id"])
                    for member in raw.get("members", [])
                    if isinstance(member, dict) and isinstance(member.get("field_id"), str)
                ],
                "target": target,
                "document_sha256": progress["document_sha256"],
                "retry_operation": retry_operation,
                "last_failure": last_failure,
                "guidance": (
                    "This is an Agent-requested edit that never committed. Re-locate the "
                    "current objects, retry or improve the same semantic edit, and confirm its "
                    "changed-region feedback before generated-content finalization."
                ),
            }
            if self._intent_already_satisfied(intent, current_summary):
                continue
            existing = next(
                (item for item in pending if (item.get("action"), item.get("field_id")) == key),
                None,
            )
            if existing is not None and _semantic_intent_richness(existing) > (
                _semantic_intent_richness(intent)
            ):
                intent = {
                    **existing,
                    "last_failure": intent["last_failure"],
                    "guidance": intent["guidance"],
                }
            pending = [
                item for item in pending if (item.get("action"), item.get("field_id")) != key
            ]
            pending.append(intent)
            changed = True
        if changed:
            self._write_progress(
                {
                    **progress,
                    "pending_edit_intents": pending[-_MAX_PENDING_EDIT_INTENTS:],
                }
            )

    @staticmethod
    def _checkpoint_summary(inspection: Inspection) -> JsonObject:
        aliases = Counter(
            str(item.format["alias"])
            for item in inspection.objects
            if item.kind == "sdt" and item.format.get("alias")
        )
        structures = sorted(
            alias
            for alias in aliases
            if (semantic := semantic_object_type(alias)) is not None
            and semantic.parent_type is None
        )
        toc_objects = [
            item
            for item in inspection.objects
            if item.kind == "paragraph"
            and item.style
            and item.style.casefold().startswith("toc")
            and item.text.strip()
        ]
        toc_entries = [item.text for item in toc_objects]
        toc_sample_entries = [text for text in toc_entries if _TOC_SAMPLE_MARKER.search(text)]
        body_heading_values = {
            str(item.format["alias"]): item.text
            for item in inspection.objects
            if item.kind == "sdt"
            and isinstance(item.format.get("alias"), str)
            and str(item.format["alias"]).startswith("body.heading.")
            and item.text.strip()
        }
        missing_body_heading_types = sorted(
            alias
            for alias, text in body_heading_values.items()
            if not any(
                text in item.text
                and (match := re.search(r"([1-3])$", item.style or "")) is not None
                and int(match.group(1)) == int(alias.rsplit("level", 1)[-1])
                for item in toc_objects
            )
        )
        return {
            "slot_count": sum(aliases.values()),
            "materialized_fields": dict(sorted(aliases.items())),
            "materialized_structures": structures,
            "toc": {
                "entry_count": len(toc_entries),
                "sample_marker_count": len(toc_sample_entries),
                "sample_marker_examples": toc_sample_entries[:5],
                "missing_body_heading_types": missing_body_heading_types,
                "refresh_needed": bool(toc_sample_entries or missing_body_heading_types),
            },
        }

    def _resolve_document(self, reference: Any) -> tuple[str, Path]:
        if not isinstance(reference, str):
            raise _document_ref_error()
        match = _DOCUMENT_REF.fullmatch(reference)
        if match is None:
            raise _document_ref_error()
        document_hash = match.group(1)
        path = self.versions / f"{document_hash}.docx"
        if not path.is_file() or path.is_symlink() or sha256_file(path) != document_hash:
            raise _document_ref_error()
        return document_hash, path

    def _resolve_object(self, reference: Any) -> tuple[Path, Inspection, InspectedObject]:
        if not isinstance(reference, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_object_ref",
                message="A current object_ref from template_open/search/focus is required.",
            )
        source_hash = sha256_file(self.source)
        progress = self._read_progress(source_hash)
        _, document = self._resolve_document(_document_ref(str(progress["document_sha256"])))
        inspection = self._inspection(document)
        object_id = reference.get("object_id")
        selected = inspection.by_id().get(object_id) if isinstance(object_id, str) else None
        if selected is None:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_object_ref",
                message="The object_id is unavailable in this immutable Word version.",
            )
        return document, inspection, selected

    def _local_context(
        self,
        inspection: Inspection,
        selected: InspectedObject,
        *,
        region_objects: list[InspectedObject] | None = None,
        adjacent_radius: int = 2,
    ) -> JsonObject:
        paragraph_locator = _parent_paragraph_locator(selected.locator)
        descendant_paragraph = next(
            (
                item
                for item in inspection.objects
                if item.kind == "paragraph" and item.locator.startswith(f"{selected.locator}/")
            ),
            None,
        )
        parent = _context_parent(inspection, selected)
        candidates = self._navigation_candidates(inspection)
        selected_index = next(
            (
                index
                for index, item in enumerate(candidates)
                if item.object_ref == selected.object_ref
                or (paragraph_locator is not None and item.locator == paragraph_locator)
                or (
                    descendant_paragraph is not None
                    and item.object_ref == descendant_paragraph.object_ref
                )
            ),
            None,
        )
        adjacent: list[JsonObject] = []
        context_paragraph = (
            selected
            if selected.kind == "paragraph"
            else descendant_paragraph
            or next(
                (
                    item
                    for item in inspection.objects
                    if item.kind == "paragraph" and item.locator == paragraph_locator
                ),
                None,
            )
        )
        if context_paragraph is not None:
            adjacent.extend(
                _agent_context_object(inspection, item)
                for item in inspection.objects
                if item.kind in {"run", "sdt", "picture", "shape"}
                and item.locator.startswith(f"{context_paragraph.locator}/")
                and item.object_ref != selected.object_ref
            )
        if region_objects is not None:
            for item in region_objects:
                if item.object_ref != selected.object_ref:
                    adjacent.append(_agent_context_object(inspection, item))
                if item.kind != "paragraph" or item.object_ref == selected.object_ref:
                    continue
                adjacent.extend(
                    _agent_context_object(inspection, child)
                    for child in inspection.objects
                    if child.kind in {"run", "sdt", "picture", "shape"}
                    and child.locator.startswith(f"{item.locator}/")
                )
        elif selected_index is not None:
            start = max(0, selected_index - adjacent_radius)
            stop = min(len(candidates), selected_index + adjacent_radius + 1)
            adjacent.extend(
                _agent_context_object(inspection, item)
                for index, item in enumerate(candidates[start:stop], start=start)
                if index != selected_index
            )
        unique: list[JsonObject] = []
        seen_refs: set[str] = set()
        for adjacent_object in adjacent:
            reference = adjacent_object.get("object_ref")
            object_id = reference.get("object_id") if isinstance(reference, dict) else None
            if not isinstance(object_id, str) or object_id in seen_refs:
                continue
            seen_refs.add(object_id)
            unique.append(adjacent_object)
        adjacent = unique[:_REGION_ADJACENT_OBJECTS]
        visible_ids = {
            str(reference["object_id"])
            for item in adjacent
            if isinstance((reference := item.get("object_ref")), dict)
            and isinstance(reference.get("object_id"), str)
        }
        signal_objects = [selected] + [
            item
            for item in inspection.objects
            if str(item.object_ref.get("object_id", "")) in visible_ids
        ]
        return {
            "target": _agent_context_object(inspection, selected),
            "parent_object": (_agent_object(inspection, parent) if parent is not None else None),
            "adjacent_objects": adjacent,
            "knowledge_signals": _context_knowledge_signals(signal_objects),
        }

    @staticmethod
    def _navigation_candidates(inspection: Inspection) -> list[InspectedObject]:
        return [
            item
            for item in inspection.objects
            if item.locator.startswith("/body/")
            and (
                (item.kind == "paragraph" and bool(item.text.strip()))
                or item.kind in {"picture", "shape"}
            )
        ]

    def _source_regions(self) -> list[list[JsonObject]]:
        if self._source_region_cache is not None:
            return self._source_region_cache
        source_hash = sha256_file(self.source)
        if self.region_blueprint_path.exists():
            try:
                value: Any = json.loads(self.region_blueprint_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value = None
            raw_regions = value.get("regions") if isinstance(value, dict) else None
            if (
                isinstance(value, dict)
                and value.get("source_sha256") == source_hash
                and value.get("layout_strategy") == _REGION_LAYOUT_STRATEGY
                and value.get("max_objects_per_region") == _REGION_SOURCE_OBJECTS
                and value.get("max_height_points") == _REGION_MAX_HEIGHT_POINTS
                and value.get("max_vertical_gap_points") == _REGION_MAX_VERTICAL_GAP_POINTS
                and isinstance(raw_regions, list)
                and all(
                    isinstance(region, list) and all(isinstance(anchor, dict) for anchor in region)
                    for region in raw_regions
                )
            ):
                self._source_region_cache = raw_regions
                return raw_regions
        source = self.versions / f"{sha256_file(self.source)}.docx"
        inspection = self._inspection(source)
        candidates = self._navigation_candidates(inspection)
        rendered, _ = self.visual.render({"input_docx": str(source), "overview": False})
        locations = self.visual.physical_locations(
            str(rendered["render_ref"]),
            inspection,
            [item.object_ref for item in candidates],
        )
        locations_by_id = {
            str(location["object_ref"]["object_id"]): location for location in locations
        }
        occurrences: Counter[str] = Counter()
        anchors: list[JsonObject] = []
        for item in candidates:
            fingerprint = str(item.object_ref["expected_fingerprint"])
            occurrence = occurrences[fingerprint]
            occurrences[fingerprint] += 1
            location = locations_by_id.get(str(item.object_ref["object_id"]), {})
            anchor: JsonObject = {
                "fingerprint": fingerprint,
                "occurrence": occurrence,
                "type": item.kind,
                "text": item.text,
                "page": location.get("page"),
                "mapping_quality": location.get("mapping_quality", "mapping_unavailable"),
            }
            bbox = location.get("bbox_pdf")
            if isinstance(bbox, list) and len(bbox) == 4:
                anchor["bbox_pdf"] = bbox
            anchors.append(anchor)
        regions = self._cluster_physical_regions(anchors)
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.region_blueprint_path,
            {
                "schema_version": 2,
                "source_sha256": source_hash,
                "layout_strategy": _REGION_LAYOUT_STRATEGY,
                "max_objects_per_region": _REGION_SOURCE_OBJECTS,
                "max_height_points": _REGION_MAX_HEIGHT_POINTS,
                "max_vertical_gap_points": _REGION_MAX_VERTICAL_GAP_POINTS,
                "regions": regions,
            },
        )
        self._source_region_cache = regions
        return regions

    @staticmethod
    def _cluster_physical_regions(anchors: list[JsonObject]) -> list[list[JsonObject]]:
        regions: list[list[JsonObject]] = []
        current: list[JsonObject] = []
        current_page: int | None = None
        current_top: float | None = None
        current_bottom: float | None = None

        def flush() -> None:
            nonlocal current, current_page, current_top, current_bottom
            if current:
                regions.append(current)
            current = []
            current_page = None
            current_top = None
            current_bottom = None

        for anchor in anchors:
            page = anchor.get("page")
            bbox = anchor.get("bbox_pdf")
            box = (
                [float(coordinate) for coordinate in bbox]
                if isinstance(bbox, list) and len(bbox) == 4
                else None
            )
            if not isinstance(page, int):
                flush()
                regions.append([anchor])
                continue
            if not current:
                current = [anchor]
                current_page = page
                if box is not None:
                    current_top = box[1]
                    current_bottom = box[3]
                continue
            if current_page != page or len(current) >= _REGION_SOURCE_OBJECTS:
                flush()
                current = [anchor]
                current_page = page
                if box is not None:
                    current_top = box[1]
                    current_bottom = box[3]
                continue
            if box is None or current_top is None or current_bottom is None:
                current.append(anchor)
                continue
            top = box[1]
            bottom = box[3]
            union_top = min(current_top, top)
            union_bottom = max(current_bottom, bottom)
            vertical_gap = max(0.0, top - current_bottom, current_top - bottom)
            if (
                union_bottom - union_top > _REGION_MAX_HEIGHT_POINTS
                or vertical_gap > _REGION_MAX_VERTICAL_GAP_POINTS
            ):
                flush()
                current = [anchor]
                current_page = page
                current_top = top
                current_bottom = bottom
                continue
            current.append(anchor)
            current_top = union_top
            current_bottom = union_bottom
        flush()
        return regions

    def _resolve_region_objects(
        self,
        inspection: Inspection,
        anchors: list[JsonObject],
    ) -> list[InspectedObject]:
        candidates = self._navigation_candidates(inspection)
        by_fingerprint: dict[str, list[InspectedObject]] = {}
        for item in candidates:
            fingerprint = str(item.object_ref["expected_fingerprint"])
            by_fingerprint.setdefault(fingerprint, []).append(item)
        resolved: list[InspectedObject] = []
        for anchor in anchors:
            matches = by_fingerprint.get(str(anchor["fingerprint"]), [])
            occurrence = anchor.get("occurrence")
            if isinstance(occurrence, int) and occurrence < len(matches):
                resolved.append(matches[occurrence])
                continue
            text = anchor.get("text")
            kind = anchor.get("type")
            fallback = next(
                (
                    item
                    for item in candidates
                    if item.kind == kind and item.text == text and item not in resolved
                ),
                None,
            )
            if fallback is not None:
                resolved.append(fallback)
        return resolved

    def _region_selection(
        self,
        inspection: Inspection,
        progress: JsonObject,
    ) -> tuple[int, int, InspectedObject | None, list[InspectedObject]]:
        regions = self._source_regions()
        cursor = int(progress["region_index"])
        pending = progress.get("pending_object_ref")
        if isinstance(pending, dict):
            try:
                target = resolve_object_ref(pending, inspection)
                peers = (
                    self._resolve_region_objects(inspection, regions[cursor])
                    if cursor < len(regions)
                    else []
                )
                return cursor, len(regions), target, peers
            except ToolFailure:
                pass
        while cursor < len(regions):
            resolved = self._resolve_region_objects(inspection, regions[cursor])
            if resolved:
                mapped_positions = [
                    position
                    for position, anchor in enumerate(regions[cursor])
                    if isinstance(anchor.get("bbox_pdf"), list)
                ]
                mapped_index = (
                    mapped_positions[min(1, len(mapped_positions) - 1)]
                    if mapped_positions
                    else min(1, len(resolved) - 1)
                )
                target = resolved[min(mapped_index, len(resolved) - 1)]
                return cursor, len(regions), target, resolved
            cursor += 1
        return cursor, len(regions), None, []

    @staticmethod
    def _region_ref(document_hash: str, index: int, selected: InspectedObject) -> str:
        return f"region:v1:{document_hash}:{index}:{selected.object_ref['object_id']}"

    def _region_view(
        self,
        document_hash: str,
        inspection: Inspection,
        progress: JsonObject,
        *,
        selected: InspectedObject | None = None,
    ) -> tuple[JsonObject | None, list[Path], JsonObject]:
        index, count, target, region_objects = self._region_selection(inspection, progress)
        if selected is not None:
            target = selected
        if index != progress["region_index"]:
            progress = {
                **progress,
                "region_index": index,
                "current_region_edited": False,
            }
            self._write_progress(progress)
        if target is None:
            return None, [], progress
        reviewed, images = self._review(
            {
                "document_ref": _document_ref(document_hash),
                "mode": "object",
                "object_ref": target.object_ref,
                "related_object_refs": [
                    item.object_ref
                    for item in region_objects
                    if item.object_ref != target.object_ref
                ],
                "quality": "review",
                "padding": 48,
            }
        )
        if not images:
            paragraph_locator = _parent_paragraph_locator(target.locator)
            candidates = [
                item
                for item in inspection.objects
                if item.kind == "paragraph"
                and (
                    item.locator == paragraph_locator
                    or item.locator.startswith(f"{target.locator}/")
                )
                and item.object_ref != target.object_ref
            ]
            for candidate in candidates:
                candidate_review, candidate_images = self._review(
                    {
                        "document_ref": _document_ref(document_hash),
                        "mode": "object",
                        "object_ref": candidate.object_ref,
                        "quality": "review",
                        "padding": _REGION_PADDING,
                    }
                )
                if candidate_images:
                    target = candidate
                    reviewed = candidate_review
                    images = candidate_images
                    break
        if (
            selected is not None or isinstance(progress.get("pending_object_ref"), dict)
        ) and progress.get("pending_object_ref") != target.object_ref:
            progress = {**progress, "pending_object_ref": target.object_ref}
            self._write_progress(progress)
        context = self._local_context(
            inspection,
            target,
            region_objects=region_objects,
        )
        return (
            {
                "region_ref": self._region_ref(document_hash, index, target),
                "index": index + 1,
                "count": count,
                "target": context["target"],
                "parent_object": context["parent_object"],
                "adjacent_objects": context["adjacent_objects"],
                "knowledge_signals": context["knowledge_signals"],
                "evidence": reviewed["visual_review"].get("evidence", []),
            },
            images,
            progress,
        )

    def _pending_generated_content(
        self,
        document_hash: str,
        inspection: Inspection,
    ) -> tuple[JsonObject | None, list[Path]]:
        summary = self._checkpoint_summary(inspection)
        toc = summary.get("toc")
        if not isinstance(toc, dict) or not toc.get("refresh_needed"):
            return None, []
        toc_root = next(
            (
                item
                for item in inspection.objects
                if item.kind == "paragraph"
                and item.style
                and item.style.casefold().startswith("toc")
            ),
            None,
        )
        if toc_root is None:
            return None, []
        fixed_titles = {
            "摘要",
            "中文摘要",
            "英文摘要",
            "abstract",
            "一级章标题",
            "二级标题",
            "三级标题",
            "参考文献",
            "附录",
            "附录标题",
            "相关的学术成果目录",
            "致谢",
        }
        required_body_headings = [
            item
            for item in inspection.objects
            if item.kind == "sdt"
            and isinstance(item.format.get("alias"), str)
            and item.format["alias"] in toc.get("missing_body_heading_types", [])
        ]
        candidates: list[InspectedObject] = list(required_body_headings)
        seen: set[str] = set()
        seen_titles: set[str] = set()
        for item in candidates:
            object_id = str(item.object_ref.get("object_id", ""))
            if object_id:
                seen.add(object_id)
            seen_titles.add(_normalize(item.text))
        eligible: list[tuple[InspectedObject, bool]] = []
        for item in inspection.objects:
            if not item.text.strip() or (item.style and item.style.casefold().startswith("toc")):
                continue
            alias = item.format.get("alias") if item.kind == "sdt" else None
            style = item.style.casefold() if item.style else ""
            normalized = _normalize(item.text)
            normalized_label = normalized.strip("【】")
            named_chapter_landmark = normalized_label.startswith("第") and (
                "文献综述" in normalized_label or "结论与展望" in normalized_label
            )
            is_candidate = (
                (isinstance(alias, str) and alias.startswith("body.heading."))
                or style.startswith("heading")
                or style.startswith("标题")
                or normalized_label in fixed_titles
                or named_chapter_landmark
            )
            if is_candidate:
                eligible.append(
                    (
                        item,
                        normalized_label in fixed_titles or named_chapter_landmark,
                    )
                )
        prioritized = [pair for pair in eligible if pair[1]] + [
            pair for pair in eligible if not pair[1]
        ]
        for item, _ in prioritized:
            object_id = str(item.object_ref.get("object_id", ""))
            title_key = _normalize(item.text)
            if not object_id or object_id in seen or title_key in seen_titles:
                continue
            seen.add(object_id)
            seen_titles.add(title_key)
            candidates.append(item)
            if len(candidates) >= _MAX_TOC_TITLE_CANDIDATES:
                break
        reviewed, images = self._review(
            {
                "document_ref": _document_ref(document_hash),
                "mode": "object",
                "object_ref": toc_root.object_ref,
                "quality": "review",
                "padding": _REGION_PADDING,
            }
        )
        return (
            {
                "field_id": "generated.toc",
                "target": _agent_object(inspection, toc_root),
                "required_body_heading_candidates": [
                    _agent_object(inspection, item) for item in required_body_headings
                ],
                "title_candidates": [_agent_object(inspection, item) for item in candidates],
                "evidence": reviewed["visual_review"].get("evidence", []),
                "guidance": (
                    "The live TOC needs refresh because its cache contains sample markers "
                    "or omits already materialized body heading types. Required body heading "
                    "candidates preserve the Agent's prior semantic classifications; all "
                    "other candidates remain non-semantic suggestions. Choose the entries, "
                    "assign levels 1-3, decide whether sample-only direct color should be "
                    "cleared, and call template_edit refresh_toc once."
                ),
            },
            images,
        )

    def view(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        action = args.get("action")
        if action == "open":
            source_reference, _ = self._register_source()
            source_hash = source_reference.rsplit(":", 1)[-1]
            progress = self._read_progress(source_hash)
            document_hash, document = self._resolve_document(
                _document_ref(str(progress["document_sha256"]))
            )
            inspection = self._inspection(document)
            progress = self._reconcile_satisfied_intents(progress, inspection)
            current_region, images, progress = self._region_view(
                document_hash,
                inspection,
                progress,
            )
            pending_edit_intents = self._pending_intents_for_current_document(
                progress,
                inspection,
            )
            pending_generated_content: JsonObject | None = None
            if current_region is None and _can_regenerate_pending_content(pending_edit_intents):
                pending_generated_content, images = self._pending_generated_content(
                    document_hash,
                    inspection,
                )
            resumed = document_hash != source_hash or int(progress["region_index"]) > 0
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(document_hash),
                    "document": {
                        "sha256": inspection.document_sha256,
                        "paragraphs": inspection.summary.get("paragraphs", 0),
                        "tables": inspection.summary.get("tables", 0),
                        "sections": inspection.summary.get("sections", 0),
                    },
                    "registry": self.registry.identity(),
                    "resume": {
                        "resumed": resumed,
                        "source": "application_checkpoint",
                        "prior_transcript_loaded": False,
                    },
                    "checkpoint_summary": self._checkpoint_summary(inspection),
                    "current_region": current_region,
                    "pending_edit_intents": pending_edit_intents,
                    "pending_generated_content": pending_generated_content,
                    "navigation": {
                        "completed_regions": int(progress["region_index"]),
                        "done": current_region is None,
                    },
                    "visual": {
                        "scope": "target_region",
                        "full_page_returned": False,
                    },
                    "guidance": (
                        (
                            "Resolve pending_edit_intents first. They are semantic edits you "
                            "previously requested but that never committed; re-locate current "
                            "objects and improve the request before TOC finalization or publish. "
                            "The Tool deliberately does not replay the known-failed operation. "
                            "For refresh_toc, use pending_generated_content's regenerated fresh "
                            "target and title candidates directly instead of searching again."
                        )
                        if pending_edit_intents
                        else (
                            "Judge only this target, its parent, and necessary adjacent objects. "
                            "Batch decisions visible in this crop, then call template_next with "
                            "its region_ref. The Tool navigates physical regions but never "
                            "assigns their semantic meaning."
                        )
                    ),
                },
                images,
            )

        if action == "next":
            region_outcome = args.get("region_outcome")
            if region_outcome not in {"handled", "preserve"}:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="region_outcome_missing",
                    message=(
                        "State whether this region was handled by a committed edit or should be "
                        "preserved as fixed school content."
                    ),
                )
            reason = args.get("reason")
            if region_outcome == "preserve" and (not isinstance(reason, str) or not reason.strip()):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="region_preserve_reason_missing",
                    message="Preserving an unchanged region requires the Agent's short reason.",
                )
            supplied = args.get("region_ref")
            region_match = _REGION_REF.fullmatch(supplied) if isinstance(supplied, str) else None
            if region_match is None:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="region_ref_stale",
                    message="Use the region_ref returned with the latest target crop.",
                )
            encoded_document_hash = region_match.group(1)
            requested_document = args.get("document_ref")
            document_hash, document = self._resolve_document(
                requested_document
                if requested_document is not None
                else _document_ref(encoded_document_hash)
            )
            if document_hash != encoded_document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="region_ref_stale",
                    message="The region_ref and document_ref refer to different Word versions.",
                )
            source_hash = sha256_file(self.source)
            progress = self._read_progress(source_hash)
            if progress["document_sha256"] != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="navigation_document_stale",
                    message="Navigation must continue from the latest checkpointed Word version.",
                )
            inspection = self._inspection(document)
            progress = self._reconcile_satisfied_intents(progress, inspection)
            current_index, _, selected, _ = self._region_selection(inspection, progress)
            expected = (
                self._region_ref(document_hash, current_index, selected)
                if selected is not None
                else None
            )
            if supplied != expected:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="region_ref_stale",
                    message="Use the region_ref returned with the latest target crop.",
                )
            if region_outcome == "handled" and not progress["current_region_edited"]:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="region_edit_not_committed",
                    message=(
                        "This region has only been viewed. Commit the Agent's cleanup/fillable "
                        "edit first, or explicitly preserve fixed school content with a reason."
                    ),
                )
            progress = {
                **progress,
                "region_index": current_index + 1,
                "pending_object_ref": None,
                "current_region_edited": False,
            }
            self._write_progress(progress)
            current_region, images, progress = self._region_view(
                document_hash,
                inspection,
                progress,
            )
            pending_edit_intents = self._pending_intents_for_current_document(
                progress,
                inspection,
            )
            pending_generated_content = None
            if current_region is None and _can_regenerate_pending_content(pending_edit_intents):
                pending_generated_content, images = self._pending_generated_content(
                    document_hash,
                    inspection,
                )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(document_hash),
                    "checkpoint_summary": self._checkpoint_summary(inspection),
                    "current_region": current_region,
                    "pending_edit_intents": pending_edit_intents,
                    "pending_generated_content": pending_generated_content,
                    "navigation": {
                        "completed_regions": int(progress["region_index"]),
                        "done": current_region is None,
                    },
                    "guidance": (
                        "Resolve pending_edit_intents before generated-content finalization."
                        if pending_edit_intents
                        else "Make semantic decisions only from this local visual region."
                    ),
                },
                images,
            )

        if action == "focus":
            _, inspection, selected = self._resolve_object(args.get("object_ref"))
            padding = args.get("padding", 32)
            radius = max(2, min(12, int(padding) // 32 if isinstance(padding, int) else 2))
            reviewed, images = self._review(
                {
                    "document_ref": _document_ref(inspection.document_sha256),
                    "mode": "object",
                    "object_ref": selected.object_ref,
                    "quality": args.get("quality", "review"),
                    "padding": args.get("padding", 32),
                }
            )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(inspection.document_sha256),
                    "local_context": self._local_context(
                        inspection,
                        selected,
                        adjacent_radius=radius,
                    ),
                    "visual_review": reviewed["visual_review"],
                },
                images,
            )

        if action == "search":
            source_reference, _ = self._register_source()
            source_hash = source_reference.rsplit(":", 1)[-1]
            progress = self._read_progress(source_hash)
            _, document = self._resolve_document(_document_ref(str(progress["document_sha256"])))
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="object_query_empty",
                    message="Object search requires non-empty text from the current task.",
                )
            inspection = self._inspection(document)
            normalized = _normalize(query)
            matches = [item for item in inspection.objects if normalized in _normalize(item.text)]
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "document_ref": _document_ref(inspection.document_sha256),
                    "query": query,
                    "matches": [
                        _agent_context_object(inspection, item)
                        for item in matches[:_MAX_SEARCH_RESULTS]
                    ],
                    "match_count": len(matches),
                    "truncated": len(matches) > _MAX_SEARCH_RESULTS,
                    "guidance": (
                        "Focus one candidate before editing; refine the query when candidates "
                        "are ambiguous."
                    ),
                },
                [],
            )

        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_navigation_action_invalid",
            message="The internal template navigation action is invalid.",
        )

    def registry_query(self, args: dict[str, Any]) -> JsonObject:
        if set(args) - {"lookups", "searches"}:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="registry_queries_invalid",
                message="template_registry accepts only lookups and searches lanes.",
            )
        raw_queries: list[tuple[str, JsonObject]] = []
        for lane, operation in (("lookups", "lookup"), ("searches", "search")):
            values = args.get(lane, [])
            if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="registry_queries_invalid",
                    message=f"{lane} must be an array of object-specific requests.",
                )
            raw_queries.extend((operation, item) for item in values)
        if not 1 <= len(raw_queries) <= 16:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="registry_queries_invalid",
                message="Provide one through sixteen total Registry lookups/searches.",
            )
        document_hash: str | None = None
        results: list[JsonObject] = []
        for request_type, raw in raw_queries:
            _, inspection, selected = self._resolve_object({"object_id": raw.get("object_id")})
            if document_hash is None:
                document_hash = inspection.document_sha256
            elif inspection.document_sha256 != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="batch_document_mismatch",
                    message="Every Registry query in a batch must use refs from one Word version.",
                )
            query = raw.get("query")
            field_id = raw.get("field_id")
            if request_type == "lookup" and isinstance(field_id, str) and field_id:
                try:
                    matches = [_with_semantic_type(self.registry.lookup(field_id))]
                    operation = "lookup"
                except ToolFailure as error:
                    if error.code != "field_not_registered":
                        raise
                    matches = [
                        _with_semantic_type(item)
                        for item in self.registry.search(
                            field_id,
                            limit=_MAX_SEARCH_RESULTS,
                        )
                    ]
                    operation = "suggest"
            elif request_type == "search" and isinstance(query, str) and query.strip():
                matches = [
                    _with_semantic_type(item)
                    for item in self.registry.search(query, limit=_MAX_SEARCH_RESULTS)
                ]
                operation = "search"
            else:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="registry_query_missing",
                    message=(
                        "Each lookup needs field_id beside object_ref; each search needs query "
                        "beside object_ref."
                    ),
                )
            results.append(
                {
                    "current_object": {
                        "object_ref": _agent_object_ref(selected),
                        "type": selected.kind,
                        "text": selected.text,
                    },
                    "operation": operation,
                    **({"requested_field_id": field_id} if operation == "suggest" else {}),
                    "matches": matches,
                    "truncated": len(matches) == _MAX_SEARCH_RESULTS,
                }
            )
        assert document_hash is not None
        return {
            "schema_version": 1,
            "status": "ok",
            "document_ref": _document_ref(document_hash),
            "results": results,
            "registry": self.registry.identity(),
        }

    def _feedback_object(
        self,
        inspection: Inspection,
        operations: list[JsonObject],
        progress: JsonObject,
    ) -> InspectedObject | None:
        preferred_slots = [
            member.get("slot_id")
            for operation in operations
            for member in operation.get("members", [])
            if isinstance(member, dict)
        ] + [operation.get("slot_id") for operation in operations]
        for slot_id in preferred_slots:
            if not isinstance(slot_id, str):
                continue
            matched = next(
                (
                    item
                    for item in inspection.objects
                    if item.kind == "sdt" and item.format.get("tag") == slot_id
                ),
                None,
            )
            if matched is not None:
                return matched
        if any(operation.get("action") == "refresh_toc" for operation in operations):
            matched = next(
                (
                    item
                    for item in inspection.objects
                    if item.kind == "paragraph"
                    and item.style
                    and item.style.casefold().startswith("toc")
                ),
                None,
            )
            if matched is not None:
                return matched
        for operation in operations:
            locator = operation.get("target_locator")
            matched = next(
                (item for item in inspection.objects if item.locator == locator),
                None,
            )
            if matched is not None:
                return matched
        _, _, target, _ = self._region_selection(inspection, progress)
        return target

    def edit(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        raw_operations = _edit_operations(args)

        document: Path | None = None
        before: Inspection | None = None
        existing_tags: set[str] = set()
        prepared: list[JsonObject] = []
        mutations: list[ObjectMutation] = []

        def allocate_slot(field_id: str) -> str:
            ordinal = 1
            while f"{field_id}.{ordinal}" in existing_tags:
                ordinal += 1
            value = f"{field_id}.{ordinal}"
            existing_tags.add(value)
            return value

        def require_same_document(inspection: Inspection) -> None:
            assert before is not None
            if inspection.document_sha256 != before.document_sha256:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="batch_document_mismatch",
                    message="Every operation in a batch must use refs from one Word version.",
                )

        for raw in raw_operations:
            action = raw.get("action")
            if action not in {
                "materialize_slot",
                "materialize_structure",
                "normalize_effective_format",
                "refresh_toc",
                "clear_content",
                "remove_object",
                "ensure_page_start",
            }:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_edit_action_invalid",
                    message=(
                        "Each operation must use one direct template_edit action from its schema."
                    ),
                )
            candidate_document, candidate_before, selected = self._resolve_object(
                raw.get("object_ref")
            )
            if before is None:
                document = candidate_document
                before = candidate_before
                existing_tags = {
                    str(item.format["tag"])
                    for item in before.objects
                    if item.kind == "sdt" and item.format.get("tag")
                }
            elif candidate_before.document_sha256 != before.document_sha256:
                require_same_document(candidate_before)
            if selected.kind not in _EDITABLE_KINDS:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="object_kind_not_editable",
                    message="A selected object kind is not editable by template_edit.",
                )
            field: JsonObject | None = None
            slot_id: str | None = None
            placeholder: str | None = None
            effective_format = _effective_format(
                raw.get("effective_format"),
                required=action == "normalize_effective_format",
            )
            structure_members: list[StructureMember] = []
            replaced_structure: InspectedObject | None = None
            prepared_members: list[JsonObject] = []
            toc_entries: list[TocEntry] = []
            prepared_entries: list[JsonObject] = []
            target_adjustment: JsonObject | None = None
            if action == "materialize_slot":
                if selected.kind == "paragraph":
                    child_runs = [
                        item
                        for item in candidate_before.objects
                        if item.kind == "run" and item.locator.startswith(f"{selected.locator}/")
                    ]
                    visible_runs = [item for item in child_runs if item.text.strip()]
                    blank_runs = [item for item in child_runs if not item.text.strip()]
                    if visible_runs and blank_runs:
                        widest = max(len(item.text) for item in blank_runs)
                        writable_runs = [
                            item for item in blank_runs if len(item.text) == widest and widest > 1
                        ]
                        if len(writable_runs) == 1:
                            requested = selected
                            selected = writable_runs[0]
                            target_adjustment = {
                                "action": "materialize_slot",
                                "reason": "unique_widest_blank_value_run",
                                "requested_object_id": str(
                                    requested.object_ref.get("object_id", requested.locator)
                                ),
                                "effective_object_id": str(
                                    selected.object_ref.get("object_id", selected.locator)
                                ),
                            }
                raw_field_id = raw.get("field_id")
                if not isinstance(raw_field_id, str):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="field_id_missing",
                        message="materialize_slot requires one Registry field_id.",
                    )
                field = self.registry.lookup(raw_field_id)
                slot_id = allocate_slot(raw_field_id)
                placeholder = _placeholder_text(field)
            elif action == "materialize_structure":
                raw_field_id = raw.get("field_id", "body.chapters")
                if not isinstance(raw_field_id, str):
                    raw_field_id = "body.chapters"
                require_body_structure_type(raw_field_id)
                replaced_structure = next(
                    (
                        item
                        for item in candidate_before.objects
                        if item.kind == "sdt" and item.format.get("alias") == raw_field_id
                    ),
                    None,
                )
                if replaced_structure is None:
                    slot_id = allocate_slot(raw_field_id)
                else:
                    prior_slot = replaced_structure.format.get("tag")
                    slot_id = (
                        str(prior_slot)
                        if isinstance(prior_slot, str) and prior_slot
                        else allocate_slot(raw_field_id)
                    )
                field = self.registry.lookup(raw_field_id)
                raw_members = raw.get("members")
                if (
                    not isinstance(raw_members, list)
                    or not 1 <= len(raw_members) <= _MAX_BATCH_OPERATIONS
                    or not all(isinstance(item, dict) for item in raw_members)
                ):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="body_structure_members_invalid",
                        message="materialize_structure requires ordered representative members.",
                    )
                member_object_ids = {
                    reference.get("object_id")
                    for item in raw_members
                    if isinstance((reference := item.get("object_ref")), dict)
                }
                if selected.object_ref.get("object_id") not in member_object_ids:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="body_structure_anchor_missing",
                        message="The structure object_ref must be one of its member objects.",
                    )
                for raw_member in raw_members:
                    _, member_inspection, member_object = self._resolve_object(
                        raw_member.get("object_ref")
                    )
                    require_same_document(member_inspection)
                    member_field_id = raw_member.get("field_id")
                    if not isinstance(member_field_id, str):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="body_member_field_missing",
                            message="Each body member requires a semantic field_id.",
                        )
                    semantic = require_body_member_type(member_field_id, member_object.kind)
                    member_field = self.registry.lookup(member_field_id)
                    member_slot = allocate_slot(member_field_id)
                    member_placeholder = _placeholder_text(member_field)
                    member_format = _effective_format(raw_member.get("effective_format"))
                    structure_members.append(
                        StructureMember(
                            selected=member_object,
                            field_id=member_field_id,
                            slot_id=member_slot,
                            content_type=str(member_field.get("content_type", "text")),
                            placeholder_text=member_placeholder,
                            effective_format=tuple(member_format.items()),
                        )
                    )
                    prepared_members.append(
                        {
                            "target": member_object.public(),
                            "target_locator": member_object.locator,
                            "field": _with_semantic_type(member_field),
                            "semantic_type": semantic.public(),
                            "slot_id": member_slot,
                            "placeholder": member_placeholder,
                            "effective_format": member_format,
                            "effective_before": {
                                key: value
                                for key, value in member_object.format.items()
                                if isinstance(key, str)
                                and any(
                                    key == outcome or key.startswith(f"effective.{outcome}")
                                    for outcome in member_format
                                )
                            },
                        }
                    )
                member_orders = [
                    next(
                        index
                        for index, candidate in enumerate(candidate_before.objects)
                        if candidate.locator == member.selected.locator
                    )
                    for member in structure_members
                ]
                if member_orders != sorted(member_orders):
                    order_facts = ", ".join(
                        f"{member.field_id}@{document_order}"
                        for member, document_order in zip(
                            structure_members, member_orders, strict=True
                        )
                    )
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="body_structure_not_in_document_order",
                        message=(
                            "Body structure members are not in forward document order "
                            f"({order_facts}). Do not repair a cross-block selection by only "
                            "reordering its array. Re-select one coherent forward school block "
                            "whose physical order already matches the intended repeat unit."
                        ),
                        suggested_actions=(
                            "reselect_members_from_one_forward_document_block",
                            "do_not_only_reorder_cross_block_members",
                        ),
                    )
            elif action == "refresh_toc":
                raw_field_id = raw.get("field_id", "generated.toc")
                if raw_field_id != "generated.toc":
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="toc_field_id_invalid",
                        message="refresh_toc operates on the generated.toc field.",
                    )
                field = self.registry.lookup("generated.toc")
                raw_entries = raw.get("entries")
                if (
                    not isinstance(raw_entries, list)
                    or not 1 <= len(raw_entries) <= 64
                    or not all(isinstance(item, dict) for item in raw_entries)
                ):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="toc_entries_invalid",
                        message="refresh_toc requires representative final-title entries.",
                    )
                entry_object_ids: set[str] = set()
                for raw_entry in raw_entries:
                    _, entry_inspection, entry_object = self._resolve_object(
                        raw_entry.get("object_ref")
                    )
                    require_same_document(entry_inspection)
                    entry_object_id = str(entry_object.object_ref.get("object_id", ""))
                    if entry_object_id in entry_object_ids:
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entry_duplicate",
                            message=(
                                "Each representative TOC entry must select a distinct title object."
                            ),
                        )
                    entry_object_ids.add(entry_object_id)
                    level = raw_entry.get("level")
                    if not isinstance(level, int) or not 1 <= level <= 3:
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entry_level_invalid",
                            message="Each TOC entry needs a level from 1 through 3.",
                        )
                    if not entry_object.text.strip():
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entry_text_empty",
                            message="A representative TOC entry must point to a visible title.",
                        )
                    toc_entries.append(TocEntry(selected=entry_object, level=level))
                    prepared_entries.append(
                        {
                            "target": entry_object.public(),
                            "level": level,
                        }
                    )
            elif action == "ensure_page_start" and raw.get("mode") != "new_page":
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="page_start_mode_invalid",
                    message="ensure_page_start currently supports mode=new_page.",
                )
            prepared.append(
                {
                    "action": action,
                    "target": selected.public(),
                    "target_locator": selected.locator,
                    "field": field,
                    "slot_id": slot_id,
                    "placeholder": placeholder,
                    "effective_format": effective_format,
                    "effective_before": {
                        key: value
                        for key, value in selected.format.items()
                        if isinstance(key, str)
                        and any(
                            key == outcome or key.startswith(f"effective.{outcome}")
                            for outcome in effective_format
                        )
                    },
                    "page_start_mode": raw.get("mode"),
                    "members": prepared_members,
                    "replaced_structure": (
                        {
                            "target": replaced_structure.public(),
                            "target_locator": replaced_structure.locator,
                        }
                        if replaced_structure is not None
                        else None
                    ),
                    "entries": prepared_entries,
                    "target_adjustment": target_adjustment,
                }
            )
            mutations.append(
                ObjectMutation(
                    selected=selected,
                    action=str(action),
                    field_id=str(field["field_id"]) if field else None,
                    slot_id=slot_id,
                    content_type=(str(field.get("content_type", "text")) if field else "text"),
                    placeholder_text=placeholder,
                    effective_format=tuple(effective_format.items()),
                    structure_members=tuple(structure_members),
                    replaced_structure=replaced_structure,
                    toc_entries=tuple(toc_entries),
                )
            )

        assert document is not None and before is not None
        prepared, mutations, absorbed_operations = _normalize_prepared_operations(
            prepared,
            mutations,
        )
        structural_risks = _structural_risks(before, prepared)
        style_signatures = _style_signatures(prepared)
        materialized_members = sorted(
            {
                str(member["field"]["field_id"])
                for item in prepared
                if item.get("action") == "materialize_structure"
                for member in item.get("members", [])
                if isinstance(member, dict) and isinstance(member.get("field"), dict)
            }
        )
        knowledge_signals = _knowledge_signals(prepared)
        target_adjustments = [
            adjustment
            for item in prepared
            if isinstance((adjustment := item.get("target_adjustment")), dict)
        ]
        source_hash = before.document_sha256
        self.versions.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".template-edit-", suffix=".docx", dir=self.versions
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            mutation_effects = mutate_objects(document, temporary, mutations=mutations)
            for change in mutation_effects.get("style_scope_changes", []):
                if not isinstance(change, dict):
                    continue
                structural_risks.append(
                    {
                        "code": "shared_character_style_override",
                        "severity": "warning",
                        "style_id": change.get("style_id"),
                        "scope": change.get("scope"),
                        "reason": change.get("reason"),
                    }
                )
            validate_docx_package(temporary)
            office_validation = self.office.validate(temporary)
            output_hash = sha256_file(temporary)
            if output_hash == source_hash:
                format_changes = self._verify_edit_effects(
                    before,
                    before,
                    prepared,
                    mutation_effects=mutation_effects,
                )
                task_source_hash = sha256_file(self.source)
                progress = self._read_progress(task_source_hash)
                feedback_object = self._feedback_object(before, prepared, progress)
                progress = {
                    **progress,
                    "pending_edit_intents": self._remaining_pending_intents(
                        progress,
                        before,
                        prepared,
                    ),
                    "current_region_edited": True,
                }
                self._write_progress(progress)
                current_region, images, progress = self._region_view(
                    source_hash,
                    before,
                    progress,
                    selected=feedback_object,
                )
                return (
                    {
                        "schema_version": 1,
                        "status": "ok",
                        "committed": False,
                        "already_satisfied": True,
                        "document_ref": _document_ref(source_hash),
                        "document_sha256": source_hash,
                        "effects": {
                            "operations": len(prepared),
                            "absorbed_operations": absorbed_operations,
                            "target_adjustments": target_adjustments,
                            "effective_format_changes": format_changes,
                            **mutation_effects,
                        },
                        "materialized_members": materialized_members,
                        "style_signatures": style_signatures,
                        "structural_risks": structural_risks,
                        "knowledge_signals": knowledge_signals,
                        "current_region": current_region,
                        "navigation": {
                            "completed_regions": int(progress["region_index"]),
                            "done": current_region is None,
                        },
                        "checks": [
                            {"name": "requested_outcome_already_satisfied", "result": "ok"},
                            {"name": "source_unchanged", "result": "ok"},
                            {"name": "package_reopens", "result": "ok"},
                            {"name": "officecli_validate", "result": "ok"},
                        ],
                        "guidance": (
                            "The requested outcome was already true; no duplicate Word boundary "
                            "or formatting override was added. Judge the returned region and "
                            "continue with template_next."
                        ),
                    },
                    images,
                )
            if sha256_file(document) != source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The immutable input version changed during editing.",
                )
            output = self.versions / f"{output_hash}.docx"
            if output.exists():
                if sha256_file(output) != output_hash:
                    raise ToolFailure(
                        status="error",
                        origin="evidence",
                        code="document_version_hash_mismatch",
                        message="An internal template version failed its integrity check.",
                    )
            else:
                os.link(temporary, output)
            after = self._inspection(output)
            format_changes = self._verify_edit_effects(
                before,
                after,
                prepared,
                mutation_effects=mutation_effects,
            )
            receipt: JsonObject = {
                "schema_version": 1,
                "input_sha256": source_hash,
                "output_sha256": output_hash,
                "operations": prepared,
                "mutation_effects": mutation_effects,
                "effective_format_changes": format_changes,
                "officecli_validation": office_validation,
            }
            self.receipts.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.receipts / f"{output_hash}.json", receipt)
            task_source_hash = sha256_file(self.source)
            progress = self._read_progress(task_source_hash)
            feedback_object = self._feedback_object(after, prepared, progress)
            progress = {
                **progress,
                "document_sha256": output_hash,
                "pending_object_ref": (
                    feedback_object.object_ref if feedback_object is not None else None
                ),
                "pending_edit_intents": self._remaining_pending_intents(
                    progress,
                    after,
                    prepared,
                ),
                "current_region_edited": True,
            }
            self._write_progress(progress)
            current_region, images, progress = self._region_view(
                output_hash,
                after,
                progress,
                selected=feedback_object,
            )
            materialized_count = sum(
                item["action"] in {"materialize_slot", "materialize_structure"} for item in prepared
            )
            removed_count = sum(
                item["action"] in {"remove_object", "clear_content"} for item in prepared
            )
            action_counts = Counter(str(item["action"]) for item in prepared)
            created_slots = sum(
                item["field"] is not None and item["slot_id"] is not None for item in prepared
            ) + sum(len(item["members"]) for item in prepared)
            guidance = (
                "Judge the returned changed region now. If it is correct, call "
                "template_next with its region_ref; no separate review is needed."
            )
            if removed_count >= 5 and materialized_count == 0:
                guidance = (
                    f"This batch removed or cleared {removed_count} objects and created no "
                    "fillable slot. Judge the returned region before continuing. If these were "
                    "student-authored examples, do not accept a blank content page: branch "
                    "from previous_document_ref and reissue the batch with one representative "
                    "object materialized as its fill interface."
                )
            return (
                {
                    "schema_version": 1,
                    "status": "ok",
                    "committed": True,
                    "previous_document_ref": _document_ref(source_hash),
                    "document_ref": _document_ref(output_hash),
                    "document_sha256": output_hash,
                    "prior_refs_do_not_address_new_version": True,
                    "effects": {
                        "operations": len(prepared),
                        "actions": dict(sorted(action_counts.items())),
                        "slots_created": created_slots,
                        "absorbed_operations": absorbed_operations,
                        "target_adjustments": target_adjustments,
                        "preserved_boundaries": mutation_effects["preserved_boundaries"],
                        "migrated_boundaries": mutation_effects["migrated_boundaries"],
                        "page_start_results": mutation_effects["page_start_results"],
                        "style_scope_changes": mutation_effects["style_scope_changes"],
                        "toc_source_levels": mutation_effects["toc_source_levels"],
                        "toc_suppressed_sources": mutation_effects[
                            "toc_suppressed_sources"
                        ],
                        "effective_format_changes": format_changes,
                    },
                    "structures": [
                        {
                            "field_id": item["field"]["field_id"],
                            "slot_id": item["slot_id"],
                            "member_count": len(item["members"]),
                        }
                        for item in prepared
                        if item["action"] == "materialize_structure"
                    ],
                    "materialized_members": materialized_members,
                    "style_signatures": style_signatures,
                    "structural_risks": structural_risks,
                    "knowledge_signals": knowledge_signals,
                    "generated_content": [
                        {
                            "field_id": item["field"]["field_id"],
                            "entry_count": len(item["entries"]),
                            "live_field": True,
                            "update_on_open": True,
                        }
                        for item in prepared
                        if item["action"] == "refresh_toc"
                    ],
                    "current_region": current_region,
                    "navigation": {
                        "completed_regions": int(progress["region_index"]),
                        "done": current_region is None,
                    },
                    "checks": [
                        {"name": "source_unchanged", "result": "ok"},
                        {"name": "package_reopens", "result": "ok"},
                        {"name": "officecli_validate", "result": "ok"},
                        {"name": "all_requested_effects_re_read", "result": "ok"},
                        {"name": "non_target_text_preserved", "result": "ok"},
                        {"name": "changed_region_returned", "result": "ok"},
                    ],
                    "guidance": guidance,
                },
                images,
            )
        finally:
            temporary.unlink(missing_ok=True)

    def _verify_edit_effects(
        self,
        before: Inspection,
        after: Inspection,
        operations: list[JsonObject],
        *,
        mutation_effects: JsonObject,
    ) -> list[JsonObject]:
        toc_roots = {
            item.locator
            for item in before.objects
            if item.kind == "paragraph" and item.style and item.style.casefold().startswith("toc")
        }

        def in_target_closure(item: InspectedObject) -> bool:
            for operation in operations:
                if operation.get("action") == "refresh_toc" and any(
                    item.locator == root or item.locator.startswith(f"{root}/")
                    for root in toc_roots
                ):
                    return True
                targets = [operation] + [
                    member for member in operation.get("members", []) if isinstance(member, dict)
                ]
                replaced = operation.get("replaced_structure")
                if isinstance(replaced, dict):
                    targets.append(replaced)
                for candidate in targets:
                    target = candidate.get("target", {})
                    locator = candidate.get("target_locator")
                    kind = target.get("type") if isinstance(target, dict) else None
                    if not isinstance(locator, str):
                        continue
                    paragraph_locator = _parent_paragraph_locator(locator)
                    if item.locator == locator:
                        return True
                    if kind in {"paragraph", "table", "sdt", "shape"} and item.locator.startswith(
                        f"{locator}/"
                    ):
                        return True
                    if kind != "paragraph" and paragraph_locator == item.locator:
                        return True
            return False

        protected = Counter(
            item.text for item in before.objects if item.text and not in_target_closure(item)
        )
        resulting = Counter(item.text for item in after.objects if item.text)
        lost = protected - resulting
        if lost:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="non_target_content_changed",
                message="Text outside the selected object changed during the edit.",
            )
        preserved_removals = {
            item.get("object_id")
            for item in mutation_effects.get("preserved_boundaries", [])
            if isinstance(item, dict)
        }
        removed_by_kind = Counter(
            item["target"].get("type")
            for item in operations
            if item.get("action") == "remove_object"
            and item["target"].get("object_ref", {}).get("object_id") not in preserved_removals
            and (item["target"].get("type") != "paragraph" or not item["target"].get("text"))
        )
        for kind, count in removed_by_kind.items():
            kind_before = sum(1 for item in before.objects if item.kind == kind)
            kind_after = sum(1 for item in after.objects if item.kind == kind)
            if kind_after > kind_before - count:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="object_not_removed",
                    message="At least one selected object is still present after batch removal.",
                )
        before_text = Counter(item.text for item in before.objects if item.text)
        after_text = Counter(item.text for item in after.objects if item.text)
        format_changes: list[JsonObject] = []

        def effective_objects(operation: JsonObject) -> list[InspectedObject]:
            locator = operation.get("target_locator")
            slot_id = operation.get("slot_id")
            if isinstance(slot_id, str):
                controls = [
                    item
                    for item in after.objects
                    if item.kind == "sdt" and item.format.get("tag") == slot_id
                ]
                return [
                    item
                    for control in controls
                    for item in after.objects
                    if item.locator == control.locator
                    or item.locator.startswith(f"{control.locator}/")
                ]
            if operation.get("action") == "refresh_toc":
                toc_locators = [
                    item.locator
                    for item in after.objects
                    if item.kind == "paragraph"
                    and item.style
                    and item.style.casefold().startswith("toc")
                ]
                return [
                    item
                    for item in after.objects
                    if item.kind in {"paragraph", "run"}
                    and any(
                        item.locator == locator or item.locator.startswith(f"{locator}/")
                        for locator in toc_locators
                    )
                ]
            if not isinstance(locator, str):
                return []
            return [
                item
                for item in after.objects
                if item.locator == locator or item.locator.startswith(f"{locator}/")
            ]

        def is_black(value: Any) -> bool:
            if value is None:
                return True
            normalized = str(value).strip().lstrip("#").casefold()
            return normalized in {"000", "000000", "black", "auto"}

        def is_no_underline(value: Any) -> bool:
            if value is None:
                return True
            return str(value).strip().casefold() in {"0", "false", "none", "nil", "off"}

        def verify_effective_format(candidate: JsonObject, action: Any) -> None:
            requested = candidate.get("effective_format", {})
            if not isinstance(requested, dict) or not requested:
                return
            observed = effective_objects(candidate)
            if not observed:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="effective_format_target_missing",
                    message="The edited object's effective formatting could not be re-read.",
                )
            if requested.get("color") == "black" and any(
                not is_black(item.format.get("effective.color")) for item in observed
            ):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="effective_color_not_normalized",
                    message=(
                        "The requested effective black color is still overridden by a run, "
                        "paragraph, character style, or theme source."
                    ),
                )
            if requested.get("underline") == "none" and any(
                not is_no_underline(item.format.get("effective.underline")) for item in observed
            ):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="effective_underline_not_normalized",
                    message="The requested effective no-underline outcome did not materialize.",
                )
            after_sources = {
                key: value
                for item in observed
                for key, value in item.format.items()
                if isinstance(key, str)
                and any(
                    key == f"effective.{outcome}" or key.startswith(f"effective.{outcome}.")
                    for outcome in requested
                )
            }
            format_changes.append(
                {
                    "action": action,
                    "target": candidate["target"],
                    "requested": requested,
                    "before": candidate.get("effective_before", {}),
                    "after": after_sources,
                }
            )

        for operation in operations:
            action = operation.get("action")
            field = operation.get("field")
            slot_id = operation.get("slot_id")
            target = operation["target"]
            if action == "materialize_slot":
                assert isinstance(field, dict)
                matches = [
                    item
                    for item in after.objects
                    if item.kind == "sdt"
                    and item.format.get("tag") == slot_id
                    and item.format.get("alias") == field.get("field_id")
                ]
                if len(matches) != 1:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="content_control_not_materialized",
                        message="A requested content control is not uniquely present after edit.",
                    )
            elif action == "materialize_structure":
                assert isinstance(field, dict)
                groups = [
                    item
                    for item in after.objects
                    if item.kind == "sdt"
                    and item.format.get("tag") == slot_id
                    and item.format.get("alias") == field.get("field_id")
                ]
                if len(groups) != 1:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="body_structure_not_materialized",
                        message="The reusable body structure is not uniquely present after edit.",
                    )
                for member in operation.get("members", []):
                    member_field = member.get("field", {})
                    member_matches = [
                        item
                        for item in after.objects
                        if item.kind == "sdt"
                        and item.format.get("tag") == member.get("slot_id")
                        and item.format.get("alias") == member_field.get("field_id")
                    ]
                    if len(member_matches) != 1:
                        raise ToolFailure(
                            status="error",
                            origin="postcondition",
                            code="body_structure_member_not_materialized",
                            message=(
                                "A body semantic member is missing after structure materialization."
                            ),
                        )
            verify_effective_format(operation, action)
            for member in operation.get("members", []):
                if isinstance(member, dict):
                    verify_effective_format(member, action)
            if action == "refresh_toc":
                expected = [
                    entry["target"].get("text")
                    for entry in operation.get("entries", [])
                    if isinstance(entry.get("target"), dict)
                ]
                toc_text = [
                    item.text
                    for item in after.objects
                    if item.kind == "paragraph"
                    and item.style
                    and item.style.casefold().startswith("toc")
                ]
                if any(not any(text in value for value in toc_text) for text in expected):
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="toc_cache_not_refreshed",
                        message="The live TOC cache is missing a requested representative entry.",
                    )
            elif action == "clear_content":
                text = target.get("text")
                if isinstance(text, str) and text and after_text[text] >= before_text[text]:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="content_not_cleared",
                        message="At least one selected object's content was not cleared.",
                    )
            elif action == "remove_object":
                object_id = target.get("object_ref", {}).get("object_id")
                if object_id in preserved_removals:
                    continue
                text = target.get("text")
                if isinstance(text, str) and text and after_text[text] >= before_text[text]:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="object_not_removed",
                        message="The selected object's visible content is still present.",
                    )
            elif action == "ensure_page_start":
                result = next(
                    (
                        item
                        for item in mutation_effects.get("page_start_results", [])
                        if isinstance(item, dict)
                        and item.get("object_id") == target.get("object_ref", {}).get("object_id")
                    ),
                    None,
                )
                if result is None:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="page_start_not_ensured",
                        message="The requested logical new-page boundary was not verified.",
                    )
        return format_changes

    def _review(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        document_hash, document = self._resolve_document(args.get("document_ref"))
        mode = args.get("mode", "pages")
        render, _ = self.visual.render({"input_docx": str(document), "overview": False})
        visual_args: JsonObject = {
            "render_ref": render["render_ref"],
            "quality": args.get("quality", "review"),
        }
        if mode == "pages":
            visual_args["mode"] = "pages"
            if "pages" in args:
                visual_args["pages"] = args["pages"]
        elif mode == "object":
            object_ref = args.get("object_ref")
            document_ref_hash = (
                object_ref.get("document_sha256") if isinstance(object_ref, dict) else None
            )
            if document_ref_hash != document_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="stale_object_ref",
                    message="The review object_ref does not belong to this document version.",
                )
            related = args.get("related_object_refs", [])
            if not isinstance(related, list) or any(
                not isinstance(item, dict) or item.get("document_sha256") != document_hash
                for item in related
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="stale_object_ref",
                    message="Every related review object must belong to this document version.",
                )
            object_refs = [object_ref, *related]
            selector = (
                {
                    "selector": "object_refs",
                    "object_refs": object_refs,
                    "padding": args.get("padding", 32),
                    "fallback": "metadata_only",
                }
                if len(object_refs) > 1
                else {
                    "selector": "object_ref",
                    "object_ref": object_ref,
                    "padding": args.get("padding", 32),
                    "fallback": "metadata_only",
                }
            )
            visual_args.update(
                {
                    "mode": "regions",
                    "regions": [selector],
                }
            )
        else:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_review_mode_invalid",
                message="Review mode must be pages or object.",
            )
        review, images = self.visual.review(visual_args)
        pages: set[int] = set()
        for evidence in review.get("evidence", []):
            pages.update(self._evidence_pages(evidence))
        self._record_review(
            document_hash,
            render_ref=str(render["render_ref"]),
            page_count=int(render["page_count"]),
            pages=pages,
        )
        return (
            {
                "schema_version": 1,
                "status": "ok",
                "document_ref": _document_ref(document_hash),
                "document_sha256": document_hash,
                "page_count": render["page_count"],
                "mode": mode,
                "visual_review": review,
                "next_cursor": review.get("next_cursor"),
            },
            images,
        )

    @staticmethod
    def _evidence_pages(value: Any) -> set[int]:
        if not isinstance(value, dict):
            return set()
        raw_pages = value.get("covered_pages", value.get("pages"))
        if isinstance(raw_pages, list):
            return {page for page in raw_pages if isinstance(page, int)}
        page = value.get("page")
        return {page} if isinstance(page, int) else set()

    def _record_review(
        self,
        document_hash: str,
        *,
        render_ref: str,
        page_count: int,
        pages: set[int],
    ) -> None:
        self.reviews.mkdir(parents=True, exist_ok=True)
        path = self.reviews / f"{document_hash}.json"
        existing: JsonObject = {}
        if path.exists():
            try:
                value: Any = json.loads(path.read_text(encoding="utf-8"))
                existing = value if isinstance(value, dict) else {}
            except (OSError, json.JSONDecodeError):
                existing = {}
        accumulated = {page for page in existing.get("reviewed_pages", []) if isinstance(page, int)}
        accumulated.update(pages)
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "document_sha256": document_hash,
                "render_ref": render_ref,
                "page_count": page_count,
                "reviewed_pages": sorted(accumulated),
            },
        )

    def publish(self, args: dict[str, Any]) -> JsonObject:
        document_hash, document = self._resolve_document(args.get("document_ref"))
        if sha256_file(self.registry.path) != self.registry.sha256:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="field_registry_changed",
                message="The field Registry changed during template preparation.",
            )
        source_hash = sha256_file(self.source)
        registered_source = self.versions / f"{source_hash}.docx"
        if not registered_source.exists() or sha256_file(registered_source) != source_hash:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="source_document_changed",
                message="The source template changed during preparation.",
            )
        progress = self._read_progress(source_hash)
        progress = self._reconcile_satisfied_intents(progress, self._inspection(document))
        pending_edit_intents = progress.get("pending_edit_intents", [])
        if pending_edit_intents:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="agent_edit_intent_unresolved",
                message=(
                    "At least one semantic edit requested by the Agent never committed. Open "
                    "the current checkpoint, resolve pending_edit_intents with fresh object "
                    "references, inspect the changed region, then publish."
                ),
                suggested_actions=("resolve_pending_edit_intents",),
            )
        validate_docx_package(document)
        office_validation = self.office.validate(document)
        review = self._read_review(document_hash)
        reviewed_pages = {page for page in review["reviewed_pages"] if isinstance(page, int)}
        if not reviewed_pages:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_visual_review_missing",
                message="Review the changed local region of the current Word before publishing.",
                suggested_actions=("review_the_changed_region",),
            )
        lineage = self._lineage(document_hash, source_hash)
        operations = [
            operation
            for receipt in lineage
            for operation in receipt.get("operations", [])
            if isinstance(operation, dict)
        ]
        structure_history = [
            item for item in operations if item.get("action") == "materialize_structure"
        ]
        latest_structures: dict[str, JsonObject] = {}
        for item in structure_history:
            field = item.get("field")
            field_id = field.get("field_id") if isinstance(field, dict) else None
            if isinstance(field_id, str):
                latest_structures[field_id] = item
        structures = list(latest_structures.values())
        slots = [item for item in operations if item.get("action") == "materialize_slot"] + [
            member
            for item in structures
            for member in item.get("members", [])
            if isinstance(member, dict)
        ]
        generated_content = [item for item in operations if item.get("action") == "refresh_toc"]
        removes = [
            item for item in operations if item.get("action") in {"remove_object", "clear_content"}
        ]
        inspection = self._inspection(document)
        controls = [item for item in inspection.objects if item.kind == "sdt"]
        published_slots: list[JsonObject] = []
        for item in slots:
            slot_id = item.get("slot_id")
            field = item.get("field")
            field_id = field.get("field_id") if isinstance(field, dict) else None
            content_type = field.get("content_type") if isinstance(field, dict) else None
            control = next(
                (
                    candidate
                    for candidate in controls
                    if candidate.format.get("tag") == slot_id
                ),
                None,
            )
            if (
                not isinstance(slot_id, str)
                or not isinstance(field_id, str)
                or not isinstance(content_type, str)
                or control is None
            ):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="created_slot_missing",
                    message=(
                        "A content control created during this task is absent from the final "
                        "Word or lacks Registry identity."
                    ),
                )
            assert isinstance(field, dict)
            published_slot: JsonObject = {
                "slot_id": slot_id,
                "field_id": field_id,
                "content_type": content_type,
                "required": True,
                "locator": {
                    "type": "content_control_tag",
                    "value": slot_id,
                    "story": "document",
                    "part": "word/document.xml",
                    "expected_match_count": 1,
                },
            }
            published_slot.update(
                _school_style_slot_metadata(
                    field_id=field_id,
                    slot_id=slot_id,
                    content_type=content_type,
                )
            )
            label = field.get("label")
            if isinstance(label, str) and label:
                published_slot["label"] = label
            published_slots.append(published_slot)
        missing_structures = [
            item.get("slot_id")
            for item in structures
            if not any(
                control.format.get("tag") == item.get("slot_id") for control in controls
            )
        ]
        if missing_structures:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="created_slot_missing",
                message="A materialized structure is absent from the final Word.",
            )
        style_contracts, style_capture = capture_template_style_contracts(
            document, published_slots
        )
        expected_style_roles = (
            _expected_body_style_roles(published_slots) if structures else []
        )
        school_style_capture = capture_template_style_observations(
            document,
            published_slots,
            expected_roles=expected_style_roles,
        )
        audit_dir = self.root / "publication"
        audit_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            audit_dir / "school-style-observations.json",
            school_style_capture.as_dict(),
        )
        if school_style_capture.failed_observations:
            failure_counts = school_style_capture.as_dict()["audit_counts"]
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="school_style_observation_failed",
                message=(
                    "School style observation could not classify the full fixed profile: "
                    f"{failure_counts['failed_observation_count']} observations failed."
                ),
                suggested_actions=(
                    "inspect_school_style_observation_artifact",
                    "extend_effective_style_resolver",
                ),
            )
        style_refs = {
            style.style_contract_id.removeprefix("style.slot."): {
                "style_contract_id": style.style_contract_id,
                "contract_digest": style.contract_digest,
            }
            for style in style_contracts.styles
        }
        for slot in published_slots:
            slot["style_contract_ref"] = style_refs[str(slot["slot_id"])]
        fill_contract: JsonObject = {
            "schema_version": "docfit-template-fill-contract/v2",
            "contract_id": f"docfit.template.{document_hash[:16]}",
            "artifact_role": "template_fill_contract",
            "status": "candidate_pending_human_acceptance",
            "revision": "1",
            "template_sha256": document_hash,
            "field_registry_ref": self.registry.identity(),
            "marker_protocol": "docfit-content-control-marker/v1",
            "profile_registry_digest": (
                school_style_capture.observation_set.profile_registry_digest
            ),
            "school_observation_set_digest": (
                school_style_capture.school_observation_set_digest
            ),
            "school_style_candidates": list(school_style_capture.school_candidates),
            "known_school_style_gaps": list(school_style_capture.known_gaps),
            "regions": [],
            "slots": published_slots,
            "styles": [style.as_dict() for style in style_contracts.styles],
            "style_contract_set_digest": style_contracts.digest,
            "provenance": {
                "structure_count": len(structures),
                "structure_slots": [
                    {
                        "slot_id": item.get("slot_id"),
                        "field_id": (
                            item.get("field", {}).get("field_id")
                            if isinstance(item.get("field"), dict)
                            else None
                        ),
                        "member_slot_ids": [
                            member.get("slot_id")
                            for member in item.get("members", [])
                            if isinstance(member, dict)
                        ],
                    }
                    for item in structures
                ],
                "generated_content_count": len(generated_content),
            },
            "review": {
                "status": "machine_checked_pending_human_signoff",
                "reviewer": None,
                "reviewed_at": None,
                "conclusion": "pending",
                "blockers": [],
                "prepared_by": "docfit-template-workspace",
            },
            "validation": {
                "style_capture": style_capture,
                "school_style_observation": {
                    "status": school_style_capture.status,
                    "profile_registry_digest": (
                        school_style_capture.observation_set.profile_registry_digest
                    ),
                    "school_observation_set_digest": (
                        school_style_capture.school_observation_set_digest
                    ),
                    "audit_counts": school_style_capture.as_dict()["audit_counts"],
                    "artifact_path": "publication/school-style-observations.json",
                },
                "officecli_validation": office_validation,
            },
        }
        atomic_write_json(audit_dir / "fill-contract.json", fill_contract)
        counts: JsonObject = {
            "slot": len(slots),
            "remove": len(removes),
            "manual": 0,
            "gap": len(school_style_capture.known_gaps),
            "unresolved": sum(
                len(item.get("unresolved_properties", []))
                for item in school_style_capture.known_gaps
                if isinstance(item, dict)
            ),
        }
        atomic_write_json(
            audit_dir / "build-report.json",
            {
                "schema_version": 1,
                "status": "built",
                "source_sha256": source_hash,
                "template_sha256": document_hash,
                "counts": counts,
                "review": review,
                "officecli_validation": office_validation,
                "style_contract_set_digest": style_contracts.digest,
                "style_occurrence_counts": style_capture["validation"]["counts"],
                "profile_registry_digest": (
                    school_style_capture.observation_set.profile_registry_digest
                ),
                "school_observation_set_digest": (
                    school_style_capture.school_observation_set_digest
                ),
                "school_style_audit_counts": school_style_capture.as_dict()[
                    "audit_counts"
                ],
            },
        )
        output = self.task_root / "output" / "final-template.docx"
        if output.exists():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_template_exists",
                message="The final Word already exists; publication never overwrites it.",
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".final-template-", suffix=".docx", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(document, temporary)
            temporary.chmod(0o600)
            os.link(temporary, output)
        except FileExistsError as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_template_exists",
                message="The final Word already exists; publication never overwrites it.",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)
        if sha256_file(output) != document_hash:
            output.unlink(missing_ok=True)
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="published_template_hash_mismatch",
                message="The published Word does not match the validated document version.",
            )
        return {
            "schema_version": 1,
            "status": "ok",
            "published": True,
            "artifact_path": "output/final-template.docx",
            "template_sha256": document_hash,
            "counts": counts,
            "school_style": {
                "profile_registry_digest": (
                    school_style_capture.observation_set.profile_registry_digest
                ),
                "school_observation_set_digest": (
                    school_style_capture.school_observation_set_digest
                ),
                "school_candidate_count": len(school_style_capture.school_candidates),
                "known_gap_count": len(school_style_capture.known_gaps),
                "failed_observation_count": 0,
            },
            "checks": [
                {"name": "source_unchanged", "result": "ok"},
                {"name": "registry_unchanged", "result": "ok"},
                {"name": "package_reopens", "result": "ok"},
                {"name": "officecli_validate", "result": "ok"},
                {"name": "current_version_local_feedback_returned", "result": "ok"},
                {"name": "style_contract_occurrences_validated", "result": "ok"},
                {"name": "single_word_published", "result": "ok"},
            ],
        }

    def _read_review(self, document_hash: str) -> JsonObject:
        path = self.reviews / f"{document_hash}.json"
        try:
            value: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="final_visual_review_missing",
                message="Review the changed local region of the current Word before publishing.",
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("document_sha256") != document_hash
            or not isinstance(value.get("page_count"), int)
            or not isinstance(value.get("reviewed_pages"), list)
        ):
            raise ToolFailure(
                status="error",
                origin="evidence",
                code="final_visual_review_invalid",
                message="The final visual review receipt is invalid.",
            )
        return value

    def _lineage(self, document_hash: str, source_hash: str) -> list[JsonObject]:
        current = document_hash
        reverse: list[JsonObject] = []
        visited: set[str] = set()
        while current != source_hash:
            if current in visited:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_cycle",
                    message="The internal template edit lineage contains a cycle.",
                )
            visited.add(current)
            path = self.receipts / f"{current}.json"
            try:
                value: Any = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_missing",
                    message="The current document is not connected to the source template.",
                ) from error
            if not isinstance(value, dict) or value.get("output_sha256") != current:
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_invalid",
                    message="An internal edit receipt is invalid.",
                )
            reverse.append(value)
            parent = value.get("input_sha256")
            if not isinstance(parent, str):
                raise ToolFailure(
                    status="error",
                    origin="evidence",
                    code="template_lineage_invalid",
                    message="An internal edit receipt has no valid parent version.",
                )
            current = parent
        return list(reversed(reverse))


def _document_ref_error() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code="document_ref_not_found",
        message="The document_ref is invalid or unavailable in this template task.",
        suggested_actions=("open_the_template_or_use_the_latest_edit_result",),
    )
