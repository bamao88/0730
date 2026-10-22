"""Concrete implementation of the five stable DocFit Tool contracts."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn

from docfit.fields import FieldRegistrySnapshot
from docfit.template.judgment_shape import (
    MECHANICAL_FEEDBACK_V1,
    mechanical_feedback,
)
from docfit.template.object_mutation import (
    ObjectMutation,
    StructureMember,
    TocEntry,
    mutate_objects,
)
from docfit.template.reading_packet import (
    READING_BLOCK_SHAPE,
    SOURCE_ENTRY_READING_SHAPE,
    agent_visible_unit_reading_packet,
    build_unit_reading_packet,
)
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_entries import (
    CanonicalSourceInventory,
    project_source_entries_onto_objects,
)
from docfit.template.source_layout import require_layout_evidence, source_layout_facts
from docfit.template.source_spans import parse_source_span_ref
from docfit.template.source_structure import require_structure_evidence, source_structure_context
from docfit.template.unit_source import (
    UnitPartitionError,
    entry_unit_contexts,
    load_initial_inventory,
    require_initial_binding,
    resolve_unit_partition,
    validate_unit_proof,
)
from docfit.tools.edit_actions import (
    DOMAIN_EDIT_MAX_BATCH_OPERATIONS,
    edit_action_spec,
    is_domain_edit_action,
    require_domain_edit_action,
)
from docfit.tools.images import verify_png
from docfit.tools.inspection import (
    Inspection,
    inspect_document,
    inspect_document_snapshot,
    resolve_object_ref,
)
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.ooxml import import_content_objects
from docfit.tools.package import normalize_docx_custom_properties, validate_docx_package
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    authorized_path,
    canonical_json,
    read_json,
    require_docx,
    sha256_file,
    sha256_json,
    task_root_from_args,
)
from docfit.visual.service import VisualEvidenceService

_SET_PROPERTY_ALLOWLIST = {
    "alignment",
    "bold",
    "color",
    "font",
    "font.ascii",
    "font.eastAsia",
    "font.hAnsi",
    "italic",
    "keepTogether",
    "keepWithNext",
    "lineSpacing",
    "pageBreakBefore",
    "size",
    "spaceAfter",
    "spaceBefore",
    "widowControl",
}
_DEFAULT_INSPECT_OBJECT_LIMIT = 80
_MAX_INSPECT_OBJECT_LIMIT = 200
_BOUNDARY_STRUCTURAL_BACKTRACK = 12
_UNTRUSTED_DOCX_SOURCE_DATA = "untrusted_docx_source_data"
_TARGET_REF_PREFIX = "object_ref:"
_DOCFIT_APPLY_RECEIPT_V1 = "docfit_apply_receipt_v1"
_TARGET_REF_REBUILD_ACTIONS = (
    (
        "Rebuild the action package against the current candidate document so "
        "Harness-selected target_ref values come from that candidate."
    ),
    "Do not reuse manually reconstructed object_ref JSON or a target_ref from another candidate.",
)
_UNIT_BOUNDARY_CHECKPOINT_REL = Path("work/.docfit/unit-boundary-checkpoint.json")
_INSPECT_EVIDENCE_FOCUS = {
    "document_map",
    "unit_evidence_packet",
    "object_detail",
    "style_evidence",
    "hash_binding",
}
_APPLY_ACTION_ALLOWED_CARRIERS = {
    "clear_content": {"paragraph", "run", "table", "picture", "sdt"},
    "remove_object": {"paragraph", "run", "table", "picture", "sdt"},
    "materialize_slot": {"paragraph", "run", "sdt"},
    "materialize_structure": {"paragraph", "run"},
    "normalize_effective_format": {"paragraph", "run", "table", "picture", "sdt"},
    "refresh_toc": {"paragraph", "sdt"},
    "ensure_page_start": {"paragraph"},
}
_POST_UNIT_SEMANTIC_JUDGMENTS_REL = Path("work/.docfit/harness/semantic-judgments.json")
_POST_UNIT_OBJECT_INVENTORY_REL = Path("work/.docfit/harness/object-inventory.json")
_KNOWN_TARGET_CARRIERS = frozenset(
    carrier for carriers in _APPLY_ACTION_ALLOWED_CARRIERS.values() for carrier in carriers
) | frozenset({"field", "shape", "text_box"})


def _inspect_selector(focus: list[str]) -> str:
    if any(item in {"styles", "template_rules", "thesis_content"} for item in focus):
        return "paragraph, table, picture, run, sdt, shape"
    return "paragraph, table, picture, sdt, shape"


def _object_window(result: JsonObject, *, offset: int, limit: int) -> JsonObject:
    raw_objects = result.get("objects", [])
    objects = raw_objects if isinstance(raw_objects, list) else []
    end = min(len(objects), offset + limit)
    window = objects[offset:end]
    return {
        "objects": window,
        "object_window": {
            "offset": offset,
            "limit": limit,
            "returned": len(window),
            "total": len(objects),
            "has_more": end < len(objects),
            "next_offset": end if end < len(objects) else None,
        },
    }


def _scoped_object_window(
    objects: list[Any],
    *,
    offset: int,
    limit: int,
) -> JsonObject:
    end = min(len(objects), offset + limit)
    window = objects[offset:end]
    return {
        "objects": window,
        "object_window": {
            "offset": offset,
            "limit": limit,
            "returned": len(window),
            "total": len(objects),
            "has_more": end < len(objects),
            "next_offset": end if end < len(objects) else None,
        },
    }


def _visual_render_page_count(visual_service: Any, render_ref: str) -> int | None:
    store = getattr(visual_service, "store", None)
    resolve_render = getattr(store, "resolve_render", None)
    if not callable(resolve_render):
        return None
    try:
        _render_path, manifest = resolve_render(render_ref)
    except Exception:
        return None
    page_count = manifest.get("page_count") if isinstance(manifest, dict) else None
    return page_count if isinstance(page_count, int) and page_count >= 1 else None


def _post_unit_checkpoint(root: Path, source_hash: str) -> JsonObject | None:
    checkpoint_path = root / _UNIT_BOUNDARY_CHECKPOINT_REL
    if not checkpoint_path.is_file():
        return None
    checkpoint = read_json(checkpoint_path)
    try:
        initial = load_initial_inventory(root, source_hash)
        validate_unit_proof(
            CanonicalSourceInventory.from_json(initial["canonical_source_inventory"]),
            checkpoint,
        )
    except ValueError as error:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="unit_boundary_proof_invalid",
            message="The checkpoint is not bound to the initial source inventory.",
        ) from error
    return checkpoint


def _post_unit_phase_review(
    root: Path,
    *,
    source_hash: str,
    candidate_hash: str,
) -> JsonObject | None:
    inventory_path = root / _POST_UNIT_OBJECT_INVENTORY_REL
    if not inventory_path.is_file():
        return None
    inventory = read_json(inventory_path)
    try:
        require_initial_binding(root, inventory)
    except (ValueError, ToolFailure):
        return None
    if inventory.get("document_sha256") != source_hash:
        return None

    review_path = root / _POST_UNIT_SEMANTIC_JUDGMENTS_REL
    if not review_path.is_file():
        return None
    review = read_json(review_path)
    if review.get("document_sha256") != source_hash:
        return None
    judgments = review.get("semantic_judgments")
    if not isinstance(judgments, list) or not judgments:
        return None
    if not _phase_review_uses_current_semantic_shape(root, inventory, review, judgments):
        return None
    return review


def _phase_review_uses_current_semantic_shape(
    root: Path,
    inventory: JsonObject,
    review: JsonObject,
    judgments: list[Any],
) -> bool:
    expected_vocabulary = _pre_input_field_vocabulary(root)
    if expected_vocabulary is None:
        return False
    return review_uses_current_semantic_shape(
        inventory=inventory,
        review={**review, "semantic_judgments": judgments},
        expected_vocabulary=expected_vocabulary,
    )


def _require_pre_input_field_registry(root: Path, supplied: Any) -> Path:
    expected = _default_field_registry(root, None)
    if supplied is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="field_registry_missing",
            message=(
                "Post-unit template write packages must explicitly carry the prepared "
                "input field Registry that produced the Agent-visible field_id_vocabulary."
            ),
            retryable=True,
            suggested_actions=(
                "Rebuild the write package from the accepted Harness phase review.",
            ),
        )
    candidate = authorized_path(supplied, task_root=root, field="field_registry")
    if candidate != expected:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="field_registry_not_pre_input",
            message=(
                "Post-unit template writes must use the prepared input field Registry "
                "that produced the Agent-visible field_id_vocabulary."
            ),
            retryable=True,
            suggested_actions=(
                "Rebuild the write package from the accepted Harness phase review.",
            ),
        )
    return expected


def _post_unit_phase_review_for_domain_edit(
    root: Path,
    *,
    input_candidate_hash: str,
) -> JsonObject | None:
    try:
        source_hash = _template_source_hash(root)
    except ToolFailure as error:
        if error.code in {"missing_path", "path_not_found", "wrong_path_kind"}:
            return None
        raise
    checkpoint = _post_unit_checkpoint(root, source_hash)
    if checkpoint is None:
        return None
    phase_review = _post_unit_phase_review(
        root,
        source_hash=source_hash,
        candidate_hash=input_candidate_hash,
    )
    if phase_review is None:
        _phase_review_required_failure(
            source_hash=source_hash,
            candidate_hash=input_candidate_hash,
        )
    return phase_review


def _phase_review_slot_provenance(review: JsonObject) -> dict[tuple[str, str], set[str]]:
    raw_judgments = review.get("semantic_judgments")
    judgments = raw_judgments if isinstance(raw_judgments, list) else []
    provenance: dict[tuple[str, str], set[str]] = {}
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        spans = judgment.get("resolved_spans")
        if not isinstance(spans, list):
            continue
        for span in spans:
            if not isinstance(span, dict):
                continue
            field_id = span.get("field_id")
            slot_ref = span.get("slot_ref")
            if not (
                isinstance(field_id, str)
                and field_id.strip()
                and isinstance(slot_ref, str)
                and slot_ref.strip()
            ):
                continue
            raw_object_ids = span.get("covered_object_ids")
            object_ids = (
                {item.strip() for item in raw_object_ids if isinstance(item, str) and item.strip()}
                if isinstance(raw_object_ids, list)
                else set()
            )
            provenance[(field_id.strip(), slot_ref.strip())] = object_ids
    return provenance


def _target_ref_object_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    object_ref = value.get("object_ref") if isinstance(value.get("object_ref"), dict) else value
    if not isinstance(object_ref, dict):
        return None
    object_id = object_ref.get("object_id")
    if isinstance(object_id, str) and object_id.strip():
        return object_id.strip()
    return None


def _phase_review_edit_operation_slots(
    edit_operation: JsonObject,
) -> list[tuple[str, str, str | None]]:
    slots: list[tuple[str, str, str | None]] = []
    action = edit_operation.get("action")
    if action == "materialize_slot":
        field_id = edit_operation.get("field_id")
        slot_ref = edit_operation.get("slot_ref")
        if (
            isinstance(field_id, str)
            and field_id.strip()
            and isinstance(slot_ref, str)
            and slot_ref.strip()
        ):
            slots.append(
                (
                    field_id.strip(),
                    slot_ref.strip(),
                    _target_ref_object_id(edit_operation.get("target_ref")),
                )
            )
    if action == "materialize_structure":
        members = edit_operation.get("members")
        if isinstance(members, list):
            for member in members:
                if not isinstance(member, dict):
                    continue
                field_id = member.get("field_id")
                slot_ref = member.get("slot_ref")
                if (
                    isinstance(field_id, str)
                    and field_id.strip()
                    and isinstance(slot_ref, str)
                    and slot_ref.strip()
                ):
                    slots.append(
                        (
                            field_id.strip(),
                            slot_ref.strip(),
                            _target_ref_object_id(member.get("target_ref")),
                        )
                    )
    return slots


def _require_phase_reviewed_edit_operation(
    *,
    review: JsonObject,
    edit_operation: JsonObject,
) -> None:
    accepted_slots = _phase_review_slot_provenance(review)
    for field_id, slot_ref, object_id in _phase_review_edit_operation_slots(edit_operation):
        covered_object_ids = accepted_slots.get((field_id, slot_ref))
        if covered_object_ids is None or (
            object_id is not None and covered_object_ids and object_id not in covered_object_ids
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="phase_review_action_package_unaccepted",
                message=(
                    "Post-unit write action packages must match the accepted Harness phase review."
                ),
                retryable=True,
                suggested_actions=(
                    (
                        "Revise the affected reading block/range semantics and let "
                        "Harness rebuild the write package."
                    ),
                ),
            )


def _reject_structure_parent_slot_identity(operation: JsonObject) -> None:
    if operation.get("field_id") is None and operation.get("slot_ref") is None:
        return
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="body_structure_parent_slot_ref_retired",
        message=(
            "materialize_structure uses structure_ref plus reviewed member slot_refs; "
            "the parent structure field is not a published slot identity."
        ),
        retryable=True,
        suggested_actions=(
            "Remove parent field_id/slot_ref from the structure package.",
            "Keep only structure_ref and members[].field_id/members[].slot_ref.",
        ),
    )


def _phase_review_required_failure(
    *,
    source_hash: str,
    candidate_hash: str,
) -> NoReturn:
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="phase_review_required",
        message=(
            "Post-unit materialization requires an accepted semantic judgment set "
            "from Harness phase review."
        ),
        retryable=True,
        suggested_actions=(
            "Return or revise semantic_judgments for the current post-unit object set.",
            "Let Harness phase review report affected unit/object scopes.",
            (
                "Run deterministic materialization only after the accepted semantic "
                "judgments are stored."
            ),
        ),
    )


def _resolved_units(checkpoint: JsonObject | None) -> list[JsonObject]:
    if checkpoint is None:
        return []
    raw_units = checkpoint.get("resolved_units")
    if not isinstance(raw_units, list) or not raw_units:
        return []
    units: list[JsonObject] = []
    for unit in raw_units:
        if not isinstance(unit, dict):
            continue
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id.strip():
            continue
        normalized_unit = dict(unit)
        normalized_unit["unit_id"] = unit_id.strip()
        units.append(normalized_unit)
    return units


def _unit_by_id(checkpoint: JsonObject | None, unit_id: Any) -> JsonObject | None:
    if not isinstance(unit_id, str) or not unit_id.strip():
        return None
    normalized = unit_id.strip()
    for unit in _resolved_units(checkpoint):
        if unit.get("unit_id") == normalized:
            return unit
    return None


def _unit_evidence_scope(
    root: Path,
    *,
    source_hash: str,
    args: dict[str, Any],
) -> JsonObject:
    checkpoint = _post_unit_checkpoint(root, source_hash)
    unit = _unit_by_id(checkpoint, args.get("unit_id"))
    if unit is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unit_evidence_packet_unit_missing",
            message=(
                "unit_evidence_packet requires a unit_id from the post-unit startup unit list."
            ),
            retryable=True,
            suggested_actions=("Use a unit_id from the post-unit startup unit list.",),
        )
    return unit


def _persisted_unit_reading_packet(
    root: Path,
    *,
    source_hash: str,
    unit_id: str,
) -> JsonObject:
    inventory_path = root / _POST_UNIT_OBJECT_INVENTORY_REL
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        if not isinstance(inventory, dict):
            raise ValueError("object inventory must be an object")
        canonical = CanonicalSourceInventory.from_json(inventory.get("canonical_source_inventory"))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_missing",
            message=(
                "unit_evidence_packet requires the persisted canonical source inventory "
                "built before post-unit projection."
            ),
            retryable=True,
            suggested_actions=("Restart post-unit preparation from the current source.",),
        ) from error
    if canonical.source_snapshot_sha256 != source_hash:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_stale",
            message="The persisted canonical source inventory belongs to another source.",
            retryable=True,
            suggested_actions=("Restart post-unit preparation from the current source.",),
        )
    require_initial_binding(root, inventory)
    checkpoint = _post_unit_checkpoint(root, source_hash)
    if inventory.get("unit_projection_digest") != sha256_json(_resolved_units(checkpoint)):
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_projection_stale",
            message="The persisted unit projections do not match the accepted units.",
            retryable=True,
            suggested_actions=("Restart post-unit preparation from the current source.",),
        )
    packets = inventory.get("unit_reading_packets")
    packet = packets.get(unit_id) if isinstance(packets, dict) else None
    if not isinstance(packet, dict):
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_projection_missing",
            message="The persisted canonical inventory has no projection for this unit.",
            retryable=True,
            suggested_actions=("Restart post-unit preparation from the current source.",),
        )
    canonical_by_id = {entry.source_entry_id: entry.to_json() for entry in canonical.source_entries}
    projected_entries = packet.get("source_entries")
    projection_matches = True
    if not isinstance(projected_entries, list):
        projection_matches = False
    else:
        for entry in projected_entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("source_entry_id"), str):
                projection_matches = False
                break
            canonical_entry = canonical_by_id.get(str(entry["source_entry_id"]))
            if canonical_entry is None or any(
                entry.get(key) != canonical_entry.get(key)
                for key in ("source_entry_id", "text", "entry_type", "source_order", "extent")
            ):
                projection_matches = False
                break
    if not projection_matches:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_projection_stale",
            message="The unit projection does not match the persisted canonical inventory.",
            retryable=True,
            suggested_actions=("Restart post-unit preparation from the current source.",),
        )
    unit = _unit_by_id(checkpoint, unit_id)
    if unit is None or [entry["source_entry_id"] for entry in packet["source_entries"]] != [
        span["source_entry_id"] for span in unit["source_spans"]
    ]:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="canonical_source_inventory_projection_stale",
            message="Unit packet entries differ from the accepted source range.",
        )
    assert checkpoint is not None
    for entry in packet["source_entries"]:
        if entry.get("unit_contexts") != entry_unit_contexts(
            checkpoint["resolved_units"], entry["source_entry_id"]
        ):
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="canonical_source_inventory_projection_stale",
                message="Unit packet cross-unit context is stale.",
            )
    require_layout_evidence(packet)
    require_structure_evidence(packet)
    return dict(packet)


def _required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="domain_edit_argument_invalid",
            message=f"{field} must be a non-empty string.",
        )
    return value


def _effective_format(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or set(value) - {"color", "underline"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message="effective_format supports only color=black and underline=none.",
        )
    if value.get("color", "black") != "black" or value.get("underline", "none") != "none":
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message="effective_format supports only color=black and underline=none.",
        )
    return tuple((key, str(value[key])) for key in ("color", "underline") if key in value)


def _slot_ref(field_id: str, supplied: Any) -> str:
    if supplied is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="slot_ref_missing",
            message=(
                "Slot materialization requires a Harness-resolved slot_ref supplied as slot_ref."
            ),
        )
    slot_ref = _required_string(supplied, field="slot_ref")
    marker = ";field_id="
    if marker not in slot_ref or slot_ref.rsplit(marker, 1)[1] != field_id:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="slot_ref_field_mismatch",
            message="slot_ref must be the Harness slot_ref for the selected field_id.",
        )
    span_ref = slot_ref.rsplit(marker, 1)[0]
    if parse_source_span_ref(span_ref) is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="slot_ref_invalid",
            message=("slot_ref must be the canonical Harness SourceSpan reference plus field_id."),
        )
    return slot_ref


def _registry_children(
    registry: FieldRegistrySnapshot,
    field_id: str,
) -> tuple[JsonObject, ...]:
    return tuple(
        dict(field) for field in registry.fields if field.get("parent_field_id") == field_id
    )


def _content_type(field: JsonObject) -> str:
    value = field.get("content_type")
    return value.strip().casefold() if isinstance(value, str) else ""


def _value_sources(field: JsonObject) -> set[str]:
    value = field.get("value_sources")
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _require_fillable_slot_field(
    registry: FieldRegistrySnapshot,
    field_id: str,
    field: JsonObject,
) -> None:
    if isinstance(field.get("parent_field_id"), str):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="structured_field_requires_structure",
            message=(
                "Fields with parent_field_id are structure members. Use "
                "materialize_structure with Harness-resolved member slot_refs."
            ),
        )
    content_type = _content_type(field)
    if content_type not in {"text", "rich_text", "section"} or (
        content_type == "section" and _registry_children(registry, field_id)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="field_not_fillable_slot",
            message=(
                f"{field_id} is not a fillable leaf field. Select a fill_slot "
                "field from the pre-input vocabulary or revise the ordered part role."
            ),
        )
    sources = _value_sources(field)
    if (
        "system_generated" in sources
        and "student_source" not in sources
        and "task_input" not in sources
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="generated_field_requires_generated_content",
            message=(
                f"{field_id} is system-generated content and cannot be materialized "
                "as a plain fillable slot."
            ),
        )


def _require_structure_field(
    registry: FieldRegistrySnapshot,
    field_id: str,
    field: JsonObject,
) -> None:
    if _content_type(field) != "section" or not _registry_children(registry, field_id):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_type_invalid",
            message=(
                "materialize_structure requires a reviewed Registry field whose "
                "snapshot metadata defines a section parent with child fields."
            ),
        )


def _require_structure_member_field(
    *,
    parent_field_id: str,
    field_id: str,
    field: JsonObject,
    word_kind: str,
) -> None:
    if field.get("parent_field_id") != parent_field_id:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_member_type_invalid",
            message=(
                "Each structure member field_id must be a direct child of the selected "
                "Registry structure field."
            ),
        )
    expected_kind = "table" if _content_type(field) == "table" else "paragraph"
    if word_kind != expected_kind:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_member_word_kind_invalid",
            message=(
                f"The selected {word_kind} object cannot represent Registry member "
                f"{field_id}. Select the matching school template object."
            ),
        )


def _placeholder(field: JsonObject, supplied: Any) -> str:
    if supplied is not None:
        return _required_string(supplied, field="placeholder_text")
    return f"【{field.get('label', field['field_id'])}】"


def _normalized_property_value(key: str, value: Any) -> str:
    normalized = str(value).strip().casefold()
    if key == "color":
        return normalized.removeprefix("#")
    if key == "lineSpacing":
        return normalized.removesuffix("x")
    return normalized


def _property_applied(item: Any, key: str, expected: str) -> bool:
    candidate_keys = [key, f"effective.{key}"]
    if key == "font":
        candidate_keys.extend(
            (
                "font.latin",
                "font.ea",
                "effective.font.ascii",
                "effective.font.eastAsia",
                "effective.font.hAnsi",
            )
        )
    elif key == "font.ascii":
        candidate_keys.extend(("font.latin", "effective.font.ascii"))
    elif key == "font.eastAsia":
        candidate_keys.extend(("font.ea", "effective.font.eastAsia"))
    elif key == "font.hAnsi":
        candidate_keys.extend(("font.latin", "effective.font.hAnsi"))
    return any(
        candidate in item.format
        and _normalized_property_value(key, item.format[candidate])
        == _normalized_property_value(key, expected)
        for candidate in candidate_keys
    )


def _locator_related(first: str, second: str) -> bool:
    return first == second or first.startswith(f"{second}/") or second.startswith(f"{first}/")


def _output_directory(value: Any, *, task_root: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="missing_output_directory",
            message=f"{field} must be a non-empty path string.",
        )
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else task_root / raw
    if candidate.exists():
        return authorized_path(
            str(candidate),
            task_root=task_root,
            field=field,
            expect_directory=True,
        )
    return authorized_path(
        str(candidate),
        task_root=task_root,
        field=field,
        must_exist=False,
    )


def _document_path(args: dict[str, Any], field: str, root: Path) -> Path:
    path = authorized_path(args.get(field), task_root=root, field=field)
    require_docx(path, field=field)
    return path


def _template_source_path(root: Path) -> Path:
    return _document_path({"input_docx": "input/school-template.docx"}, "input_docx", root)


def _template_source_hash(root: Path) -> str:
    return sha256_file(_template_source_path(root))


def _reject_retired_tool_arguments(
    args: dict[str, Any],
    *,
    tool_name: str,
    fields: tuple[str, ...],
) -> None:
    retired = tuple(field for field in fields if field in args)
    if not retired:
        return
    formatted = ", ".join(retired)
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="schema_envelope_invalid",
        message=f"{tool_name} no longer accepts retired input field(s): {formatted}.",
        retryable=True,
        suggested_actions=(
            f"Remove {formatted} from the request.",
            "Use the bound Tool session's prepared task root and current input files.",
        ),
    )


_RETIRED_TEMPLATE_SEMANTIC_LOOKUP_ARGUMENTS = (
    "semantic_field",
    "query",
    "registry_field",
    "field_id",
)
_RETIRED_TEMPLATE_SOURCE_OVERRIDE_ARGUMENTS = (
    "target_ref",
    "locator",
    "paragraph",
    "paragraph_index",
    "scope_ref",
    "source_entry_id",
    "span_ref",
    "slot_ref",
    "reading_block_id",
    "reading_range_id",
    "range_id",
)
_RETIRED_DIRECT_APPLY_ARGUMENTS = (
    "object_ref",
    "operation",
    "operations",
    "edit_operation",
    "target_refs",
    "replacement_text",
    "style_contract_ref",
    "evidence_ref",
    "field_registry",
)


def _evidence_card(
    *,
    source_hash: str,
    focus: str,
    refs: JsonObject,
    summary: JsonObject,
    risks: list[Any],
    candidate_hash: str | None = None,
    evidence: list[Any] | None = None,
) -> JsonObject:
    card: JsonObject = {
        "schema_version": "docfit_evidence_card_v1",
        "status": "ok",
        "source_hash": source_hash,
        "focus": focus,
        "refs": refs,
        "summary": summary,
        "risks": risks,
        "untrusted": {
            "marker": _UNTRUSTED_DOCX_SOURCE_DATA,
            "instruction_authority": False,
            "configuration_authority": False,
        },
        "failure": None,
    }
    if candidate_hash is not None:
        card["candidate_hash"] = candidate_hash
    if evidence is not None:
        card["evidence"] = [_agent_visible_evidence_item(item) for item in evidence]
    return card


def _agent_visible_evidence_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    result = dict(item)
    target_ref = _encode_target_ref(result)
    if target_ref is not None:
        result.setdefault("target_ref", target_ref)
    return result


def _semantic_evidence_item(item: Any) -> JsonObject:
    if not isinstance(item, dict):
        return {"type": type(item).__name__}
    result: JsonObject = {}
    object_ref = item.get("object_ref")
    if isinstance(object_ref, dict) and isinstance(object_ref.get("object_id"), str):
        result["object_id"] = object_ref["object_id"]
    for key in ("locator", "type", "text", "style"):
        value = item.get(key)
        if isinstance(value, str):
            result[key] = value[:500] if key == "text" else value
    format_value = item.get("format")
    if isinstance(format_value, dict):
        compact_format = {
            key: value
            for key, value in format_value.items()
            if key
            in {
                "alignment",
                "font.ea",
                "font.latin",
                "size",
                "bold",
                "italic",
            }
            and isinstance(value, str)
        }
        if compact_format:
            result["format_hint"] = compact_format
    return result


def _encode_target_ref(item: JsonObject) -> str | None:
    object_ref = item.get("object_ref")
    if not isinstance(object_ref, dict):
        return None
    payload = {
        "object_ref": object_ref,
        **({"type": item["type"]} if isinstance(item.get("type"), str) else {}),
        **({"text": item["text"]} if isinstance(item.get("text"), str) else {}),
        **({"locator": item["locator"]} if isinstance(item.get("locator"), str) else {}),
    }
    encoded = base64.urlsafe_b64encode(canonical_json(payload)).decode("ascii")
    return f"{_TARGET_REF_PREFIX}{encoded.rstrip('=')}"


def _check_feedback_metadata(source_hash: str) -> JsonObject:
    return {
        "type": "docfit_check",
        "mechanical": True,
        "semantic_authority": False,
        "source_hash": source_hash,
    }


def _check_ok(*, check: str, source_hash: str) -> JsonObject:
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": "ok",
        "check": check,
        "source_hash": source_hash,
        "feedback": _check_feedback_metadata(source_hash),
        "checks": [{"name": check, "result": "ok"}],
        "warnings": [],
        "failure": None,
    }


def _agent_facing_check_result(
    result: JsonObject,
    *,
    source_hash: str,
) -> JsonObject:
    normalized = dict(result)
    normalized.setdefault("source_hash", source_hash)
    feedback = normalized.get("feedback")
    if isinstance(feedback, dict):
        feedback = dict(feedback)
        feedback.setdefault("mechanical", True)
        feedback["semantic_authority"] = False
        feedback.setdefault("source_hash", source_hash)
        normalized["feedback"] = feedback
    else:
        normalized["feedback"] = _check_feedback_metadata(source_hash)
    return normalized


def _decode_target_ref_payload(value: Any) -> JsonObject:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="missing_target",
                message="Packaged operations[].target_ref must not be empty.",
            )
        if text.startswith(_TARGET_REF_PREFIX):
            encoded = text.removeprefix(_TARGET_REF_PREFIX)
            padded = encoded + "=" * (-len(encoded) % 4)
            try:
                decoded = json.loads(
                    base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
                )
            except (ValueError, UnicodeDecodeError) as error:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="target_ref_invalid",
                    message=(
                        "Packaged operations[].target_ref is not a valid DocFit object reference."
                    ),
                    retryable=True,
                    suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
                ) from error
            if not isinstance(decoded, dict):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="target_ref_invalid",
                    message="Packaged operations[].target_ref must decode to an object reference.",
                    retryable=True,
                    suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
                )
            value = decoded
        elif text.startswith("{"):
            try:
                decoded = json.loads(text)
            except ValueError as error:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="target_ref_invalid",
                    message="Packaged operations[].target_ref JSON cannot be decoded.",
                    retryable=True,
                    suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
                ) from error
            if not isinstance(decoded, dict):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="target_ref_invalid",
                    message="Packaged operations[].target_ref JSON must be an object.",
                    retryable=True,
                    suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
                )
            value = decoded
        else:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="target_ambiguity",
                message=(
                    "Packaged operations[].target_ref must be a fresh DocFit object_ref handle."
                ),
                retryable=True,
                suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
            )
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_object_ref",
            message="Packaged operations[].target_ref must identify one object.",
            retryable=True,
            suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
        )
    object_ref = value.get("object_ref") if isinstance(value.get("object_ref"), dict) else value
    if not isinstance(object_ref, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_object_ref",
            message="Packaged operations[].target_ref must contain an object_ref.",
            retryable=True,
            suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
        )
    return {
        "object_ref": dict(object_ref),
        **({"type": value["type"]} if isinstance(value.get("type"), str) else {}),
        **({"text": value["text"]} if isinstance(value.get("text"), str) else {}),
        **({"locator": value["locator"]} if isinstance(value.get("locator"), str) else {}),
        **(
            {"parent_object_id": value["parent_object_id"]}
            if isinstance(value.get("parent_object_id"), str)
            else {}
        ),
        **(
            {"ancestor_object_ids": value["ancestor_object_ids"]}
            if isinstance(value.get("ancestor_object_ids"), list)
            else {}
        ),
    }


def _decode_apply_target_ref(value: Any, *, candidate_hash: str) -> JsonObject:
    decoded = _decode_target_ref_payload(value)
    object_ref = decoded["object_ref"]
    if object_ref.get("document_sha256") != candidate_hash:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_object_ref",
            message="Packaged operations[].target_ref belongs to a different candidate snapshot.",
            retryable=True,
            suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
        )
    if not all(
        isinstance(object_ref.get(field), str) and object_ref[field]
        for field in ("object_id", "expected_fingerprint")
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_object_ref",
            message=(
                "Packaged operations[].target_ref is missing object_id or expected_fingerprint."
            ),
            retryable=True,
            suggested_actions=_TARGET_REF_REBUILD_ACTIONS,
        )
    return decoded


def _apply_source_path(root: Path, source_hash: str) -> Path:
    source = _template_source_path(root)
    if sha256_file(source) != source_hash:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_ref",
            message="template source no longer matches input/school-template.docx.",
            retryable=True,
            suggested_actions=("Refresh the bound Tool session after updating the input DOCX.",),
        )
    return source


def _apply_candidate_path(root: Path, *, source: Path, candidate_hash: str) -> Path:
    work = root / "work"
    matches: list[Path] = []
    if work.is_dir():
        matches.extend(
            path
            for path in sorted(work.rglob("*.docx"))
            if path.is_file() and sha256_file(path) == candidate_hash
        )
    if sha256_file(source) == candidate_hash:
        matches.append(source)
    work_matches = [path for path in matches if work in path.parents]
    if len(work_matches) == 1:
        return work_matches[0]
    if not work_matches and matches == [source]:
        return source
    if matches:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_ambiguity",
            message="candidate_hash matches multiple candidate paths.",
            suggested_actions=("Use a unique work/ candidate snapshot before applying.",),
        )
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="stale_ref",
        message="candidate_hash does not match the source or any work/ candidate DOCX.",
        retryable=True,
        suggested_actions=("Refresh candidate_hash or create a current work/ candidate.",),
    )


def _default_field_registry(root: Path, package: JsonObject | None) -> Path:
    if package is not None and isinstance(package.get("field_registry"), str):
        return authorized_path(package["field_registry"], task_root=root, field="field_registry")
    for name in (
        "input/field-registry.yaml",
        "input/field-registry.yml",
        "input/field-registry.json",
    ):
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="field_registry_missing",
        message="materialize_slot requires the prepared input field Registry.",
        suggested_actions=("Ensure input/field-registry.yaml is present.",),
    )


def _pre_input_field_vocabulary(root: Path) -> JsonObject | None:
    try:
        registry_path = _default_field_registry(root, None)
    except ToolFailure as error:
        if error.code == "field_registry_missing":
            return None
        raise
    return FieldRegistrySnapshot.load(registry_path).pre_input_vocabulary()


def _apply_action_package(root: Path, args: dict[str, Any]) -> JsonObject | None:
    batch_ref = args.get("batch_ref")
    if batch_ref is None:
        return None
    return read_json(authorized_path(batch_ref, task_root=root, field="batch_ref"))


def _apply_package_action(edit_operation: JsonObject) -> str:
    action = edit_operation.get("action")
    if not isinstance(action, str) or action not in _APPLY_ACTION_ALLOWED_CARRIERS:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="action_package_action_invalid",
            message=("docfit_apply action packages must contain one supported domain edit action."),
            suggested_actions=("Rebuild the action package from Harness/materializer output.",),
        )
    return action


def _check_apply_carrier(action: str, target: JsonObject) -> None:
    carrier = target.get("type")
    allowed = _APPLY_ACTION_ALLOWED_CARRIERS.get(action)
    if allowed is not None and isinstance(carrier, str) and carrier not in allowed:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_carrier",
            message=f"{action} does not support target carrier type {carrier}.",
            suggested_actions=("Select a supported carrier from fresh object evidence.",),
        )


def _package_edit_operation(package: JsonObject | None) -> JsonObject:
    if package is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="action_package_required",
            message="docfit_apply requires a reviewed batch_ref action package.",
            suggested_actions=("Use the Harness/materializer action package for this write.",),
        )
    if isinstance(package.get("target_refs"), list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="action_package_shape_retired",
            message=("Package-level target_refs are retired; use operations[].target_ref."),
            suggested_actions=("Rebuild the action package with operations[].target_ref.",),
        )
    edit_operation = package.get("edit_operation")
    if isinstance(edit_operation, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="action_package_shape_retired",
            message=("Singular edit_operation action packages are retired; use operations[]."),
            suggested_actions=("Rebuild the action package with operations[].",),
        )
    operations = package.get("operations")
    if (
        isinstance(operations, list)
        and len(operations) == 1
        and isinstance(operations[0], dict)
        and isinstance(operations[0].get("action"), str)
    ):
        return dict(operations[0])
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="action_package_invalid",
        message="docfit_apply requires exactly one packaged edit action in operations[].",
        suggested_actions=("Rebuild the action package with one operations[] item.",),
    )


def _apply_edit_operation(
    *,
    package: JsonObject | None,
    candidate_hash: str,
) -> tuple[JsonObject, JsonObject]:
    packaged = _package_edit_operation(package)
    if "target_ref" not in packaged:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="action_package_target_missing",
            message="Packaged edit actions must carry their Harness-selected target_ref.",
            suggested_actions=("Rebuild the action package with operations[].target_ref.",),
        )
    target = _decode_apply_target_ref(
        packaged["target_ref"],
        candidate_hash=candidate_hash,
    )
    packaged["target_ref"] = target["object_ref"]
    return packaged, target


def _field_registry_for_edit_operation(
    *,
    root: Path,
    package: JsonObject | None,
    edit_operation: JsonObject,
    require_pre_input_registry: bool = False,
) -> Path | None:
    spec = edit_action_spec(edit_operation.get("action"))
    if spec is None or not spec.requires_field_registry:
        return None
    field_registry = (
        _require_pre_input_field_registry(
            root,
            package.get("field_registry") if package is not None else None,
        )
        if require_pre_input_registry
        else _default_field_registry(root, package)
    )
    registry = FieldRegistrySnapshot.load(field_registry)
    action = edit_operation.get("action")
    if action == "materialize_slot":
        field_id = _required_string(edit_operation.get("field_id"), field="field_id")
        field = registry.lookup(field_id)
        _require_fillable_slot_field(registry, field_id, field)
        _slot_ref(field_id, edit_operation.get("slot_ref"))
    elif action == "materialize_structure":
        _reject_structure_parent_slot_identity(edit_operation)
        structure_ref = _required_string(
            edit_operation.get("structure_ref"),
            field="structure_ref",
        )
        field = registry.lookup(structure_ref)
        _require_structure_field(registry, structure_ref, field)
        members = edit_operation.get("members")
        if not isinstance(members, list) or not members:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="body_structure_members_invalid",
                message="materialize_structure requires packaged ordered members.",
            )
        for member in members:
            if not isinstance(member, dict):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="body_structure_members_invalid",
                    message="Every packaged structure member must be an object.",
                )
            member_field_id = _required_string(
                member.get("field_id"),
                field="members[].field_id",
            )
            member_field = registry.lookup(member_field_id)
            if member_field.get("parent_field_id") != structure_ref:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="body_member_type_invalid",
                    message=(
                        "Each packaged structure member field_id must be a direct child "
                        "of the selected Registry structure field."
                    ),
                )
            _slot_ref(member_field_id, member.get("slot_ref"))
    return field_registry


def _apply_receipt(
    *,
    args: dict[str, Any],
    input_docx: Path,
    output_docx: Path,
    source_hash: str,
    input_candidate_hash: str,
    target: JsonObject,
    edit_result: JsonObject,
    edit_operation: JsonObject,
) -> JsonObject:
    output_hash = edit_result.get("output_sha256")
    if not isinstance(output_hash, str) or len(output_hash) != 64:
        output_hash = sha256_file(output_docx)
    operation = _apply_package_action(edit_operation)
    return {
        "schema_version": _DOCFIT_APPLY_RECEIPT_V1,
        "status": "ok",
        "committed": True,
        "completion": False,
        "source_hash": source_hash,
        "input_candidate_hash": input_candidate_hash,
        "candidate_hash": output_hash,
        "output_docx": str(output_docx),
        "receipt": {
            "operation": operation,
            "edit_action": edit_operation.get("action"),
            "idempotency_key": args.get("idempotency_key"),
            "input_docx": str(input_docx),
            "output_docx": str(output_docx),
            "candidate_hash": output_hash,
            "target": _apply_target_summary(target),
        },
        "invalidated_evidence": [
            {
                "reason": "candidate_changed",
                "hash": input_candidate_hash,
                "refresh_with": ["docfit_evidence", "docfit_check"],
            }
        ],
        "checks": [
            {"name": "apply_preconditions", "result": "ok"},
            {"name": "edit_postconditions", "result": "ok"},
            {"name": "completion_gate", "result": "not_evaluated"},
        ],
        "warnings": list(edit_result.get("warnings", []))
        if isinstance(edit_result.get("warnings"), list)
        else [],
        "failure": None,
    }


def _apply_target_summary(target: JsonObject) -> JsonObject:
    object_ref: JsonObject = (
        target["object_ref"] if isinstance(target.get("object_ref"), dict) else {}
    )
    object_id = object_ref.get("object_id")
    return {
        **({"type": target["type"]} if isinstance(target.get("type"), str) else {}),
        **({"locator": target["locator"]} if isinstance(target.get("locator"), str) else {}),
        **({"object_id": object_id} if isinstance(object_id, str) else {}),
    }


def _apply_failure_suggested_actions(
    *,
    operation: str,
    target: JsonObject,
    base: list[Any],
) -> list[str]:
    suggestions = [
        "Return to seven-question item 5 and decide whether a write is still required.",
    ]
    target_type = target.get("type")
    if operation == "materialize_slot" and target_type == "paragraph":
        suggestions.extend(
            (
                "Refresh target_affordance and select the existing sdt target_ref if present.",
                (
                    "Do not repeat docfit_apply with the same hash, target, action, "
                    "and failure code."
                ),
            )
        )
    elif operation == "materialize_slot" and target_type == "sdt":
        suggestions.append(
            "If this is not already a DocFit slot, use the existing SDT adoption path."
        )
    suggestions.extend(str(item) for item in base)
    return list(dict.fromkeys(suggestions))


def _apply_edit_failure(
    *,
    args: dict[str, Any],
    source_hash: str,
    target: JsonObject,
    edit_operation: JsonObject,
    failure: JsonObject,
) -> JsonObject:
    operation = _apply_package_action(edit_operation)
    status = failure.get("status", "needs_input")
    normalized_status = status if status in {"needs_input", "error"} else "needs_input"
    raw_failure = failure.get("failure")
    detail = raw_failure if isinstance(raw_failure, dict) else failure
    code = str(detail.get("code", "apply_edit_failed"))
    message = str(detail.get("message", "The underlying edit did not commit."))
    target_summary = _apply_target_summary(target)
    target_text = ", ".join(f"{key}={value}" for key, value in target_summary.items())
    suggested = _apply_failure_suggested_actions(
        operation=operation,
        target=target,
        base=list(detail.get("suggested_actions", []))
        if isinstance(detail.get("suggested_actions"), list)
        else [],
    )
    return {
        "schema_version": _DOCFIT_APPLY_RECEIPT_V1,
        "status": normalized_status,
        "committed": False,
        "completion": False,
        "source_hash": source_hash,
        "input_candidate_hash": args.get("candidate_hash"),
        "candidate_hash": args.get("candidate_hash"),
        "receipt": {
            "operation": operation,
            "edit_action": edit_operation.get("action"),
            "idempotency_key": args.get("idempotency_key"),
            "target": target_summary,
            "result": code,
        },
        "invalidated_evidence": [],
        "checks": [{"name": "apply_preconditions", "result": "ok"}],
        "warnings": list(failure.get("warnings", []))
        if isinstance(failure.get("warnings"), list)
        else [],
        "failure": {
            "origin": "docfit_apply",
            "code": code,
            "retryable": bool(detail.get("retryable")),
            "message": f"docfit_apply {operation} failed for {target_text}: {message}",
            "suggested_actions": suggested,
        },
    }


def _wrap_apply_edit_failure(
    *,
    args: dict[str, Any],
    source_hash: str,
    target: JsonObject,
    edit_operation: JsonObject,
    error: ToolFailure,
) -> NoReturn:
    wrapped = _apply_edit_failure(
        args=args,
        source_hash=source_hash,
        target=target,
        edit_operation=edit_operation,
        failure=error.result(committed=False),
    )
    failure = wrapped["failure"]
    raise ToolFailure(
        status=error.status,
        origin="docfit_apply",
        code=str(failure["code"]),
        message=str(failure["message"]),
        retryable=error.retryable,
        suggested_actions=tuple(str(item) for item in failure["suggested_actions"]),
    ) from error


def _public_inspection(inspection: Inspection) -> JsonObject:
    return {
        "schema_version": 1,
        "status": "ok",
        "checks": [
            {"name": "docx_package", "result": "ok"},
            {"name": "officecli_parse", "result": "ok"},
        ],
        "warnings": list(inspection.warnings),
        "failure": None,
        "document": {
            "sha256": inspection.document_sha256,
            **inspection.summary,
        },
        "objects": [item.public() for item in inspection.objects],
        "risks": list(inspection.risks),
        "provider": inspection.provider,
    }


def _require_operations(value: Any) -> list[JsonObject]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, dict) for item in value)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_operations",
            message="docx_edit requires a non-empty array of operation objects.",
        )
    return value


def _scalar_properties(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_edit_properties",
            message="set_properties requires a non-empty properties object.",
        )
    unsupported = sorted(set(value) - _SET_PROPERTY_ALLOWLIST)
    if unsupported:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_edit_property",
            message="One or more requested formatting properties are not in the M1 allowlist.",
        )
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, (str, int, float, bool)):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_edit_property_value",
                message="Formatting property values must be scalar.",
            )
        result[key] = str(item).lower() if isinstance(item, bool) else str(item)
    return result


def _office_validation_status(document: Path, office: OfficeCliAdapter) -> JsonObject:
    try:
        validation = office.validate_snapshot(document)
    except ToolFailure as error:
        return {
            "passed": False,
            "code": error.code,
            "origin": error.origin,
            "detail": error.message,
        }
    return {
        "passed": True,
        "code": None,
        "origin": None,
        "detail": validation.get("detail", "OfficeCLI OpenXML validation passed."),
    }


class DocFitToolService:
    """One concrete service; it owns no Agent loop or workflow state."""

    def __init__(
        self,
        *,
        task_root: Path | None = None,
        office: OfficeCliAdapter | None = None,
        visual: VisualEvidenceService | None = None,
    ) -> None:
        self._task_root = (
            task_root.expanduser().resolve(strict=True) if task_root is not None else None
        )
        self._office = office
        self._visual = visual
        self._last_evidence_image_paths: list[Path] = []

    def _session_root(self, args: dict[str, Any]) -> Path:
        if self._task_root is None:
            return task_root_from_args(args)
        requested = args.get("task_root")
        if requested is not None:
            candidate = task_root_from_args({"task_root": requested})
            if candidate != self._task_root:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="task_root_mismatch",
                    message="task_root does not match the root bound to this application session.",
                )
        return self._task_root

    @property
    def office(self) -> OfficeCliAdapter:
        if self._office is None:
            self._office = OfficeCliAdapter()
        return self._office

    def visual(self) -> VisualEvidenceService:
        if self._visual is None:
            root = self._task_root or task_root_from_args({})
            self._visual = VisualEvidenceService(root, office=self._office)
        return self._visual

    def inspect(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
        document = _document_path(args, "input_docx", root)
        focus = args.get("focus", [])
        if focus and (
            not isinstance(focus, list) or not all(isinstance(item, str) for item in focus)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_inspect_focus",
                message="focus must be an array of inspection focus strings.",
            )
        focus_values = [str(item) for item in focus]
        inspection = inspect_document_snapshot(
            document,
            self.office,
            selector=_inspect_selector(focus_values),
        )
        result = _public_inspection(inspection)
        result["focus"] = focus
        output_value = args.get("output")
        offset_value = args.get("object_offset", 0)
        limit_value = args.get("object_limit")
        if not isinstance(offset_value, int) or isinstance(offset_value, bool) or offset_value < 0:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_inspect_window",
                message="object_offset must be a non-negative integer.",
            )
        if limit_value is None:
            limit = _DEFAULT_INSPECT_OBJECT_LIMIT if output_value is not None else 0
        elif (
            not isinstance(limit_value, int)
            or isinstance(limit_value, bool)
            or limit_value < 1
            or limit_value > _MAX_INSPECT_OBJECT_LIMIT
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_inspect_window",
                message="object_limit must be an integer from 1 to 200.",
            )
        else:
            limit = limit_value
        include_objects = args.get("include_objects")
        if include_objects is not None and not isinstance(include_objects, bool):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_inspect_window",
                message="include_objects must be a boolean when supplied.",
            )
        if output_value is not None:
            output = authorized_path(
                output_value,
                task_root=root,
                field="output",
                must_exist=False,
            )
            atomic_write_json(output, result)
        else:
            output = None
        full_object_count = len(result.get("objects", []))
        should_window = output is not None or limit_value is not None or include_objects is False
        if should_window:
            compact: JsonObject = {
                "schema_version": result["schema_version"],
                "status": result["status"],
                "checks": result["checks"],
                "warnings": result["warnings"],
                "failure": result["failure"],
                "document": result["document"],
                "risks": result["risks"],
                "provider": result["provider"],
                "focus": focus,
                "object_count": full_object_count,
            }
            if output is not None:
                compact["analysis_path"] = str(output)
            if include_objects is not False:
                compact.update(
                    _object_window(
                        result,
                        offset=offset_value,
                        limit=limit or _DEFAULT_INSPECT_OBJECT_LIMIT,
                    )
                )
            else:
                compact["objects"] = []
                compact["object_window"] = {
                    "offset": offset_value,
                    "limit": 0,
                    "returned": 0,
                    "total": full_object_count,
                    "has_more": full_object_count > 0,
                    "next_offset": 0 if full_object_count > 0 else None,
                }
            return compact
        return result

    def evidence(self, args: dict[str, Any]) -> JsonObject:
        self._last_evidence_image_paths = []
        root = self._session_root(args)
        focus = args.get("focus")
        if not isinstance(focus, str) or not focus.strip():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="evidence_focus_invalid",
                message="docfit_evidence requires a focus string.",
            )
        _reject_retired_tool_arguments(
            args,
            tool_name="docfit_evidence",
            fields=(
                "source_hash",
                *_RETIRED_TEMPLATE_SOURCE_OVERRIDE_ARGUMENTS,
                *(() if focus == "registry_field" else _RETIRED_TEMPLATE_SEMANTIC_LOOKUP_ARGUMENTS),
            ),
        )
        if focus == "registry_field":
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="registry_field_runtime_removed",
                message=(
                    "docfit_evidence no longer provides runtime Registry field lookup. "
                    "Post-unit Agents must select field IDs from the pre-input "
                    "field_id_vocabulary included in the unit packet."
                ),
                retryable=True,
                suggested_actions=(
                    "Use field_id_vocabulary.allowed_field_ids from unit_evidence_packet.",
                    "Return needs_input if the required field is absent from the input vocabulary.",
                ),
            )
        if focus == "unit_slice":
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unit_slice_runtime_removed",
                message=(
                    "docfit_evidence no longer provides unit_slice locator evidence. Use "
                    "document_map for boundary overview or unit_evidence_packet for post-unit "
                    "semantic judgment input."
                ),
                retryable=True,
                suggested_actions=(
                    "Use docfit_evidence with focus=document_map for unit-boundary overview.",
                    (
                        "Use docfit_evidence with focus=unit_evidence_packet and unit_id for "
                        "post-unit input."
                    ),
                ),
            )
        source_hash = _template_source_hash(root)
        source = _template_source_path(root)
        candidate_hash = args.get("candidate_hash")
        if isinstance(candidate_hash, str):
            if len(candidate_hash) != 64:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="candidate_hash_invalid",
                    message="docfit_evidence candidate_hash must be a SHA-256 digest.",
                )
            document = _apply_candidate_path(root, source=source, candidate_hash=candidate_hash)
        else:
            document = source

        if focus == "document_map":
            initial = load_initial_inventory(root, source_hash)
            canonical = CanonicalSourceInventory.from_json(initial["canonical_source_inventory"])
            projected = project_source_entries_onto_objects(
                initial["objects"],
                canonical.source_entries,
                source_sha256=source_hash,
            )
            packet = agent_visible_unit_reading_packet(
                build_unit_reading_packet(
                    unit={"unit_id": "source", "unit_name": "Document"},
                    scoped_objects=projected,
                    source_entries=canonical.source_entries,
                    layout_facts=source_layout_facts(source, canonical),
                    structure_context=source_structure_context(source, canonical),
                )
            )
            offset, limit = args.get("offset", 0), args.get("limit", 20)
            if (
                not isinstance(offset, int)
                or isinstance(offset, bool)
                or offset < 0
                or not isinstance(limit, int)
                or isinstance(limit, bool)
                or limit < 1
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="evidence_offset_invalid",
                    message="Use a nonnegative offset and positive limit.",
                )
            window = _scoped_object_window(packet["source_entries"], offset=offset, limit=limit)
            return _evidence_card(
                source_hash=source_hash,
                candidate_hash=None,
                focus=focus,
                refs={"document": "input/school-template.docx"},
                summary={
                    "source_entries": window["objects"],
                    "source_entry_count": len(canonical.source_entries),
                    "source_entry_window": window["object_window"],
                },
                evidence=window["objects"],
                risks=[],
            )

        if focus in _INSPECT_EVIDENCE_FOCUS:
            unit_summary: JsonObject | None = None
            scoped_objects: list[Any]
            if focus == "unit_evidence_packet":
                unit = _unit_evidence_scope(
                    root,
                    source_hash=source_hash,
                    args=args,
                )
                unit_summary = {key: unit[key] for key in ("unit_id", "unit_name") if key in unit}
                reading_packet = _persisted_unit_reading_packet(
                    root,
                    source_hash=source_hash,
                    unit_id=str(unit_summary["unit_id"]),
                )
                inspection: JsonObject = {"risks": []}
                objects: list[Any] = []
                scoped_objects = []
            else:
                inspection = self.inspect(
                    {
                        "input_docx": str(document),
                        "focus": ["structure", "styles", "visible_objects"],
                        "include_objects": True,
                    }
                )
                raw_objects = inspection.get("objects", [])
                objects = raw_objects if isinstance(raw_objects, list) else []
                scoped_objects = objects if isinstance(objects, list) else []
            default_limit = 20 if focus == "document_map" else _DEFAULT_INSPECT_OBJECT_LIMIT
            limit_value = args.get("limit", default_limit)
            limit = (
                limit_value
                if isinstance(limit_value, int)
                and not isinstance(limit_value, bool)
                and limit_value > 0
                else _DEFAULT_INSPECT_OBJECT_LIMIT
            )
            offset_value = args.get("offset", 0)
            if (
                not isinstance(offset_value, int)
                or isinstance(offset_value, bool)
                or offset_value < 0
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="evidence_offset_invalid",
                    message="docfit_evidence offset must be a non-negative integer.",
                    retryable=True,
                    suggested_actions=("Use object_window.next_offset from the previous card.",),
                )
            refs: JsonObject = {"document": str(document.relative_to(root))}
            if focus == "unit_evidence_packet":
                if unit_summary is not None and isinstance(unit_summary.get("unit_id"), str):
                    refs["reading_packet"] = f"unit_reading_packet:{unit_summary['unit_id']}"
                agent_packet = agent_visible_unit_reading_packet(reading_packet)
                if "field_id_vocabulary" not in agent_packet:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="field_registry_missing",
                        message=(
                            "unit_evidence_packet requires the prepared input field Registry "
                            "so the Agent-visible packet can include field_id_vocabulary."
                        ),
                        retryable=True,
                        suggested_actions=(
                            "Prepare the task input field Registry before post-unit projection.",
                        ),
                    )
                source_entry_window = _scoped_object_window(
                    agent_packet.get("source_entries", []),
                    offset=offset_value,
                    limit=limit,
                )
                unit_packet_summary: JsonObject = {
                    "source_entry_window": source_entry_window["object_window"],
                    "source_entry_count": len(agent_packet.get("source_entries", [])),
                    "reading_block_count": len(agent_packet["reading_blocks"]),
                    "reading_range_count": len(agent_packet.get("reading_ranges", [])),
                    "reading_ranges": agent_packet.get("reading_ranges", []),
                    "layout_context": agent_packet["layout_context"],
                    "unit": agent_packet["unit"],
                    "post_unit_flow": (
                        "agent source entry packet for semantic judgment before "
                        "Registry/style evidence"
                    ),
                    "evidence_shape": SOURCE_ENTRY_READING_SHAPE,
                    "view_shape": READING_BLOCK_SHAPE,
                }
                if "field_id_vocabulary" in agent_packet:
                    unit_packet_summary["field_id_vocabulary"] = agent_packet["field_id_vocabulary"]
                if "field_vocabulary_digest" in agent_packet:
                    unit_packet_summary["field_vocabulary_digest"] = agent_packet[
                        "field_vocabulary_digest"
                    ]
                return _evidence_card(
                    source_hash=source_hash,
                    candidate_hash=(candidate_hash if isinstance(candidate_hash, str) else None),
                    focus=focus,
                    refs=refs,
                    summary=unit_packet_summary,
                    risks=list(inspection.get("risks", []))
                    if isinstance(inspection.get("risks"), list)
                    else [],
                    evidence=source_entry_window["objects"],
                )

            scoped_window = _scoped_object_window(
                scoped_objects,
                offset=offset_value,
                limit=limit,
            )
            inspection_summary: JsonObject = {
                "document": inspection.get("document", {}),
                "object_window": scoped_window["object_window"],
                "object_count": inspection.get("object_count", len(objects)),
                "scoped_object_count": len(scoped_objects),
            }
            return _evidence_card(
                source_hash=source_hash,
                candidate_hash=candidate_hash if isinstance(candidate_hash, str) else None,
                focus=focus,
                refs=refs,
                summary=inspection_summary,
                risks=list(inspection.get("risks", []))
                if isinstance(inspection.get("risks"), list)
                else [],
                evidence=scoped_window["objects"],
            )

        if focus == "render_snapshot":
            rendered, images = self.render({"input_docx": str(document), "overview": True})
            self._last_evidence_image_paths = images
            return _evidence_card(
                source_hash=source_hash,
                candidate_hash=candidate_hash if isinstance(candidate_hash, str) else None,
                focus=focus,
                refs={
                    "document": str(document.relative_to(root)),
                    "render_ref": rendered.get("render_ref"),
                },
                summary={"render": rendered},
                risks=[],
            )

        if focus in {"visual_page", "visual_region"}:
            render_ref = args.get("render_ref")
            if not isinstance(render_ref, str):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="render_ref_missing",
                    message="visual evidence requires render_ref.",
                    suggested_actions=(
                        "render_snapshot",
                        "return_structural_units_if_visual_is_not_blocking",
                    ),
                )
            mode = "pages" if focus == "visual_page" else "regions"
            review_args: JsonObject = {"render_ref": render_ref, "mode": mode}
            page = args.get("page")
            if isinstance(page, int) and not isinstance(page, bool):
                review_args["pages"] = [page]
            review, images = self.visual_review(review_args)
            self._last_evidence_image_paths = images
            return _evidence_card(
                source_hash=source_hash,
                candidate_hash=candidate_hash if isinstance(candidate_hash, str) else None,
                focus=focus,
                refs={"document": str(document.relative_to(root)), "render_ref": render_ref},
                summary={"visual_review": review},
                risks=[],
            )

        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="evidence_focus_unsupported",
            message=f"Unsupported docfit_evidence focus: {focus}.",
        )

    def check(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
        check = args.get("check")
        if not isinstance(check, str) or not check.strip():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="check_kind_invalid",
                message="docfit_check requires a check string.",
            )
        _reject_retired_tool_arguments(
            args,
            tool_name="docfit_check",
            fields=(
                "source_hash",
                *_RETIRED_TEMPLATE_SOURCE_OVERRIDE_ARGUMENTS,
                *(
                    ()
                    if check == "registry_binding"
                    else _RETIRED_TEMPLATE_SEMANTIC_LOOKUP_ARGUMENTS
                ),
            ),
        )
        candidate_hash = args.get("candidate_hash")
        if check == "hash_binding":
            source_hash = _template_source_hash(root)
            return self._check_hash_binding(root, source_hash)
        source_hash = _template_source_hash(root)
        if check == "unit_coverage":
            return self._check_unit_boundaries(root, args, source_hash)
        if check == "coverage_closure":
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="check_kind_retired",
                message=(
                    "docfit_check(coverage_closure) is retired from the post-unit flow; "
                    "Harness validates semantic coverage when semantic_judgments are "
                    "submitted."
                ),
                source_hash=source_hash,
                candidate_hash=(
                    candidate_hash
                    if isinstance(candidate_hash, str) and len(candidate_hash) == 64
                    else None
                ),
                blockers=[
                    {
                        "code": "check_kind_retired",
                        "field": "check",
                        "evidence_focus": "unit_evidence_packet",
                        "message": ("Coverage is no longer checked through a separate Tool call."),
                    }
                ],
                suggested_actions=(
                    "Return semantic_judgments in the structured result.",
                    (
                        "Let the host Harness validate reading-block/range coverage, "
                        "overlap, span resolution, and executability."
                    ),
                ),
            )
        if check == "judgment_shape":
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="check_kind_retired",
                message=(
                    "docfit_check(judgment_shape) is retired from the post-unit flow; "
                    "Harness validates scope, ordered parts, field vocabulary, coverage, "
                    "conflicts, and resolved spans at semantic submission."
                ),
                source_hash=source_hash,
                candidate_hash=(
                    candidate_hash
                    if isinstance(candidate_hash, str) and len(candidate_hash) == 64
                    else None
                ),
                blockers=[
                    {
                        "code": "check_kind_retired",
                        "field": "check",
                        "evidence_focus": "unit_evidence_packet",
                        "message": (
                            "Legacy judgment shape checks are no longer an accepted Tool check."
                        ),
                    }
                ],
                suggested_actions=(
                    "Submit semantic_judgments to the Harness semantic coverage action.",
                    (
                        "Revise Agent output to use scope, ordered parts, and "
                        "field_id_vocabulary values."
                    ),
                ),
            )
        if check == "closure_aggregation":
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="check_kind_retired",
                message=(
                    "docfit_check(closure_aggregation) is retired from the template "
                    "extraction flow; Harness validates unit and semantic coverage at "
                    "phase submission."
                ),
                source_hash=source_hash,
                candidate_hash=(
                    candidate_hash
                    if isinstance(candidate_hash, str) and len(candidate_hash) == 64
                    else None
                ),
                blockers=[
                    {
                        "code": "check_kind_retired",
                        "field": "check",
                        "evidence_focus": "unit_evidence_packet",
                        "message": (
                            "Subagent scoped-closure payloads with object ids are no longer "
                            "accepted."
                        ),
                    }
                ],
                suggested_actions=(
                    "Return unit boundaries or semantic_judgments to the host Harness.",
                    "Use reading block/range scope and ordered semantic parts.",
                ),
            )
        if check == "action_plan":
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="check_kind_retired",
                message=(
                    "docfit_check(action_plan) is retired from the post-unit flow; "
                    "Agent returns semantic_judgments and Harness reviews the whole stage."
                ),
                source_hash=source_hash,
                candidate_hash=(
                    candidate_hash
                    if isinstance(candidate_hash, str) and len(candidate_hash) == 64
                    else None
                ),
                blockers=[
                    {
                        "code": "check_kind_retired",
                        "field": "check",
                        "evidence_focus": "phase_review",
                        "message": (
                            "Per-object action plans are no longer an accepted Tool check."
                        ),
                    }
                ],
                suggested_actions=(
                    "Return or revise semantic_judgments for the current object set.",
                    (
                        "Let Harness phase review report any target, Registry, coverage, "
                        "or conflict issues."
                    ),
                    "Use the execution-stage materializer only after phase review accepts the set.",
                ),
            )
        if check == "registry_binding":
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="check_kind_retired",
                message=(
                    "docfit_check(registry_binding) is retired from the post-unit flow; "
                    "runtime Registry lookups are not an accepted way to choose or "
                    "confirm template field IDs."
                ),
                source_hash=source_hash,
                candidate_hash=(
                    candidate_hash
                    if isinstance(candidate_hash, str) and len(candidate_hash) == 64
                    else None
                ),
                blockers=[
                    {
                        "code": "check_kind_retired",
                        "field": "check",
                        "evidence_focus": "field_id_vocabulary",
                        "message": (
                            "Field IDs must come from the pre-input field_id_vocabulary "
                            "and are validated by Harness semantic submission."
                        ),
                    }
                ],
                suggested_actions=(
                    "Use only field_id_vocabulary.allowed_field_ids from the unit packet.",
                    "Submit semantic_judgments with scope and ordered parts for Harness review.",
                    "Return needs_input if the required field is absent from the input vocabulary.",
                ),
            )
        if check == "style_evidence" and not isinstance(args.get("evidence_ref"), str):
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="style_evidence_insufficient",
                message="Style evidence check requires evidence_ref.",
                source_hash=source_hash,
                blockers=[
                    {
                        "code": "style_evidence_insufficient",
                        "field": "evidence_ref",
                        "evidence_focus": "style_evidence",
                        "message": "Provide style evidence before closing this obligation.",
                    }
                ],
                suggested_actions=("Call docfit_evidence with focus=style_evidence.",),
            )
        if (
            check == "candidate_validation"
            and isinstance(candidate_hash, str)
            and len(candidate_hash) == 64
        ):
            return self._check_candidate_validation(root, args, source_hash, candidate_hash)
        if (
            check in {"completion_gate", "visual_coverage"}
            and isinstance(candidate_hash, str)
            and len(candidate_hash) == 64
        ):
            return self._check_completion_gate(
                root,
                args,
                source_hash,
                candidate_hash,
                check=check,
            )
        if (
            check
            in {
                "visual_coverage",
                "completion_gate",
                "candidate_validation",
                "publication_readiness",
            }
            and "payload_ref" not in args
            and "payload" not in args
        ):
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="completion_gap",
                message=f"{check} requires inline payload or payload_ref to check mechanically.",
                source_hash=source_hash,
                candidate_hash=(
                    candidate_hash
                    if isinstance(candidate_hash, str) and len(candidate_hash) == 64
                    else None
                ),
                blockers=[
                    {
                        "code": "missing_target",
                        "field": "payload",
                        "evidence_focus": "schema_envelope",
                        "message": "Provide the structured payload to check.",
                    }
                ],
                suggested_actions=(
                    "Call docfit_check with inline payload when checking during the Agent turn.",
                    "Or return the structured result so the host Harness can validate it.",
                ),
            )
        return _check_ok(check=check, source_hash=source_hash)

    def _check_payload(self, root: Path, args: dict[str, Any]) -> JsonObject:
        inline_payload = args.get("payload")
        if inline_payload is not None:
            if not isinstance(inline_payload, dict):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="payload_invalid",
                    message="Inline payload must be an object.",
                )
            return inline_payload
        payload_ref = args.get("payload_ref")
        payload = read_json(authorized_path(payload_ref, task_root=root, field="payload_ref"))
        return payload

    def _check_candidate_paths(
        self,
        root: Path,
        source_hash: str,
        candidate_hash: str,
    ) -> tuple[Path, Path]:
        source = _apply_source_path(root, source_hash)
        candidate = _apply_candidate_path(
            root,
            source=source,
            candidate_hash=candidate_hash,
        )
        return source, candidate

    def _check_candidate_validation(
        self,
        root: Path,
        args: dict[str, Any],
        source_hash: str,
        candidate_hash: str,
    ) -> JsonObject:
        source, candidate = self._check_candidate_paths(root, source_hash, candidate_hash)
        validation_args: JsonObject = {
            "source_docx": source.relative_to(root).as_posix(),
            "source_sha256": source_hash,
            "final_docx": candidate.relative_to(root).as_posix(),
        }
        render_ref = args.get("render_ref")
        if isinstance(render_ref, str):
            validation_args["candidate_render_ref"] = render_ref
        validation = self.validate(validation_args)
        return self._validation_check_result(
            check="candidate_validation",
            source_hash=source_hash,
            candidate_hash=candidate_hash,
            validation=validation,
        )

    def _check_completion_gate(
        self,
        root: Path,
        args: dict[str, Any],
        source_hash: str,
        candidate_hash: str,
        *,
        check: str,
    ) -> JsonObject:
        source, candidate = self._check_candidate_paths(root, source_hash, candidate_hash)
        render_ref = args.get("render_ref")
        reviewed_pages = self._reviewed_pages(args.get("reviewed_pages"))
        missing_blockers: list[JsonObject] = []
        if not isinstance(render_ref, str) or not render_ref.startswith("render:v2:"):
            missing_blockers.append(
                {
                    "code": "completion_evidence_missing",
                    "field": "render_ref",
                    "evidence_focus": "render_snapshot",
                    "message": "Provide the render_ref for the current final candidate.",
                }
            )
        if not reviewed_pages:
            missing_blockers.append(
                {
                    "code": "completion_evidence_missing",
                    "field": "reviewed_pages",
                    "evidence_focus": "visual_page",
                    "message": "Provide the final pages that were visually reviewed.",
                }
            )
        if missing_blockers:
            suggested_actions = [
                "Call docfit_evidence with focus=render_snapshot for the current candidate.",
            ]
            if isinstance(render_ref, str):
                page_count = _visual_render_page_count(self.visual(), render_ref)
                if page_count is not None:
                    pages = list(range(1, page_count + 1))
                    suggested_actions.append(
                        "Render/review every final page; for this render_ref use "
                        f"reviewed_pages={pages} after those pages have been reviewed."
                    )
            suggested_actions.extend(
                [
                    (
                        f"Do not repeat docfit_check({check}) with the same "
                        "candidate_hash/render_ref until reviewed_pages is present."
                    ),
                    (
                        "Return the structured completion with final_docx, "
                        "candidate_render_ref, reviewed_pages, findings, and summary when "
                        "visual review is complete."
                    ),
                ]
            )
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="completion_evidence_missing",
                message=(
                    f"{check} requires candidate render evidence and explicit "
                    "reviewed_pages before it can close mechanically."
                ),
                source_hash=source_hash,
                candidate_hash=candidate_hash,
                blockers=missing_blockers,
                suggested_actions=tuple(suggested_actions),
            )
        visual_review: JsonObject = {
            "document_sha256": candidate_hash,
            "render_ref": render_ref,
            "reviewed_pages": reviewed_pages,
            "findings": args.get("findings") if isinstance(args.get("findings"), list) else [],
        }
        validation = self.validate(
            {
                "source_docx": source.relative_to(root).as_posix(),
                "source_sha256": source_hash,
                "final_docx": candidate.relative_to(root).as_posix(),
                "candidate_render_ref": render_ref,
                "visual_review": visual_review,
                "required_visual_coverage": "all_final_pages",
            }
        )
        return self._validation_check_result(
            check=check,
            source_hash=source_hash,
            candidate_hash=candidate_hash,
            validation=validation,
        )

    @staticmethod
    def _reviewed_pages(value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        pages = [
            item
            for item in value
            if isinstance(item, int) and not isinstance(item, bool) and item >= 1
        ]
        return sorted(set(pages))

    @staticmethod
    def _validation_check_result(
        *,
        check: str,
        source_hash: str,
        candidate_hash: str,
        validation: JsonObject,
    ) -> JsonObject:
        validation_checks = [
            item for item in validation.get("checks", []) if isinstance(item, dict)
        ]
        blockers = [item for item in validation_checks if item.get("blocking") is True]
        if blockers:
            return mechanical_feedback(
                feedback_type="docfit_check",
                code=f"{check}_blocked",
                message=f"{check} found blocking validation issues.",
                source_hash=source_hash,
                candidate_hash=candidate_hash,
                blockers=[
                    {
                        "code": str(item.get("name", "validation_blocker")),
                        "field": "final_docx",
                        "evidence_focus": "candidate_validation",
                        "message": str(
                            item.get("suggested_action")
                            or item.get("result")
                            or "Resolve the blocking validation issue."
                        ),
                    }
                    for item in blockers
                ],
                suggested_actions=(
                    "Use the validation evidence to repair the current candidate.",
                    "Re-run docfit_check after producing a new candidate_hash.",
                ),
            )
        warnings = validation.get("warnings")
        return {
            "schema_version": MECHANICAL_FEEDBACK_V1,
            "status": "ok",
            "check": check,
            "source_hash": source_hash,
            "candidate_hash": candidate_hash,
            "feedback": _check_feedback_metadata(source_hash) | {"candidate_hash": candidate_hash},
            "checks": [{"name": check, "result": "ok"}],
            "warnings": warnings if isinstance(warnings, list) else [],
            "failure": None,
            "validation": validation,
        }

    def _check_hash_binding(
        self,
        root: Path,
        source_hash: str,
    ) -> JsonObject:
        document = _document_path(
            {"input_docx": "input/school-template.docx"},
            "input_docx",
            root,
        )
        actual = sha256_file(document)
        if actual != source_hash:
            return mechanical_feedback(
                feedback_type="docfit_check",
                code="stale_ref",
                message="The bound template source changed while validating this document.",
                source_hash=actual,
                blockers=[
                    {
                        "code": "stale_ref",
                        "field": "input/school-template.docx",
                        "evidence_focus": "hash_binding",
                        "message": "Refresh the bound Tool session and evidence refs.",
                    }
                ],
                suggested_actions=("Call docfit_evidence with focus=hash_binding.",),
            )
        return _check_ok(check="hash_binding", source_hash=source_hash)

    def _check_unit_boundaries(
        self,
        root: Path,
        args: dict[str, Any],
        source_hash: str,
    ) -> JsonObject:
        # Host-owned source state must be valid before judging the proposal.
        # Its failure cannot be repaired by changing school boundaries.
        initial = load_initial_inventory(root, source_hash)
        canonical = CanonicalSourceInventory.from_json(initial["canonical_source_inventory"])
        try:
            payload = self._check_payload(root, args)
            if set(payload) != {"units"}:
                raise ValueError(
                    "Unit coverage accepts only units with exact source boundary points."
                )
            units = resolve_unit_partition(canonical, payload.get("units"))
        except ValueError as error:
            return mechanical_feedback(
                feedback_type="unit_coverage",
                code="unit_source_partition_invalid",
                message=str(error),
                source_hash=source_hash,
                blockers=error.blockers if isinstance(error, UnitPartitionError) else [
                    {"code": "unit_source_partition_invalid", "message": str(error)},
                ],
                suggested_actions=(
                    "Revise source-entry boundary points to partition all entries.",
                ),
            )
        return {
            **_check_ok(check="unit_coverage", source_hash=source_hash),
            "unit_count": len(units),
            "resolved_units": units,
            "source_inventory_digest": canonical.inventory_digest,
            "unit_projection_digest": sha256_json(units),
        }

    def apply(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
        candidate_hash = args.get("candidate_hash")
        _reject_retired_tool_arguments(
            args,
            tool_name="docfit_apply",
            fields=(
                "source_hash",
                *_RETIRED_TEMPLATE_SEMANTIC_LOOKUP_ARGUMENTS,
                *_RETIRED_TEMPLATE_SOURCE_OVERRIDE_ARGUMENTS,
                *_RETIRED_DIRECT_APPLY_ARGUMENTS,
            ),
        )
        source_hash = _template_source_hash(root)
        if not isinstance(candidate_hash, str) or len(candidate_hash) != 64:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="candidate_hash_invalid",
                message="docfit_apply requires candidate_hash.",
            )

        source = _apply_source_path(root, source_hash)
        input_docx = _apply_candidate_path(
            root,
            source=source,
            candidate_hash=candidate_hash,
        )
        output_docx = authorized_path(
            args.get("output_docx"),
            task_root=root,
            field="output_docx",
            must_exist=False,
        )
        require_docx(output_docx, field="output_docx")
        if root / "output" in output_docx.parents:
            raise ToolFailure(
                status="error",
                origin="invariant",
                code="publication_write_denied",
                message="docfit_apply writes candidates under work/; publishing belongs to O1.",
            )
        if input_docx == output_docx:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_overwrite_denied",
                message="docfit_apply never writes over its input candidate.",
            )

        package = _apply_action_package(root, args)
        edit_operation, target = _apply_edit_operation(
            package=package,
            candidate_hash=candidate_hash,
        )
        edit_action = _apply_package_action(edit_operation)
        _check_apply_carrier(edit_action, target)
        edit_spec = edit_action_spec(edit_action)
        requires_phase_review = _post_unit_checkpoint(root, source_hash) is not None or (
            edit_spec is not None and edit_spec.requires_field_registry
        )
        phase_review: JsonObject | None = None
        if requires_phase_review:
            phase_review = _post_unit_phase_review(
                root,
                source_hash=source_hash,
                candidate_hash=candidate_hash,
            )
            if phase_review is None:
                _phase_review_required_failure(
                    source_hash=source_hash,
                    candidate_hash=candidate_hash,
                )
        field_registry = _field_registry_for_edit_operation(
            root=root,
            package=package,
            edit_operation=edit_operation,
            require_pre_input_registry=phase_review is not None,
        )
        if phase_review is not None:
            _require_phase_reviewed_edit_operation(
                review=phase_review,
                edit_operation=edit_operation,
            )

        edit_args: JsonObject = {
            "input_docx": str(input_docx.relative_to(root)),
            "output_docx": str(output_docx.relative_to(root)),
            "operations": [edit_operation],
        }
        if field_registry is not None:
            edit_args["field_registry"] = str(field_registry.relative_to(root))
        try:
            edit_result = self.edit(edit_args)
        except ToolFailure as error:
            _wrap_apply_edit_failure(
                args=args,
                source_hash=source_hash,
                target=target,
                edit_operation=edit_operation,
                error=error,
            )
        if edit_result.get("status") != "ok" or edit_result.get("committed") is not True:
            return _apply_edit_failure(
                args=args,
                source_hash=source_hash,
                target=target,
                edit_operation=edit_operation,
                failure=dict(edit_result),
            )
        return _apply_receipt(
            args=args,
            input_docx=input_docx,
            output_docx=output_docx,
            source_hash=source_hash,
            input_candidate_hash=candidate_hash,
            target=target,
            edit_result=edit_result,
            edit_operation=edit_operation,
        )

    def _domain_mutations(
        self,
        *,
        args: dict[str, Any],
        root: Path,
        inspection: Inspection,
        operations: list[JsonObject],
        require_pre_input_registry: bool = False,
    ) -> tuple[list[ObjectMutation], list[JsonObject]]:
        if len(operations) > DOMAIN_EDIT_MAX_BATCH_OPERATIONS:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="too_many_domain_edit_operations",
                message="One atomic docx_edit batch supports at most 32 domain operations.",
            )
        registry: FieldRegistrySnapshot | None = None
        if any(
            (spec := edit_action_spec(item.get("action"))) is not None
            and spec.requires_field_registry
            for item in operations
        ):
            registry_path = (
                _require_pre_input_field_registry(root, args.get("field_registry"))
                if require_pre_input_registry
                else authorized_path(
                    args.get("field_registry"),
                    task_root=root,
                    field="field_registry",
                )
            )
            registry = FieldRegistrySnapshot.load(registry_path)

        mutations: list[ObjectMutation] = []
        public_operations: list[JsonObject] = []
        for operation in operations:
            action = require_domain_edit_action(operation.get("action"))
            selected = resolve_object_ref(operation.get("target_ref"), inspection)
            field: JsonObject | None = None
            field_id: str | None = None
            slot_ref: str | None = None
            structure_ref: str | None = None
            placeholder_text: str | None = None
            members: list[StructureMember] = []
            public_members: list[JsonObject] = []
            replaced_structure = None
            toc_entries: list[TocEntry] = []
            public_entries: list[JsonObject] = []
            effective_format = _effective_format(operation.get("effective_format"))

            if action == "materialize_slot":
                assert registry is not None
                field_id = _required_string(operation.get("field_id"), field="field_id")
                field = registry.lookup(field_id)
                _require_fillable_slot_field(registry, field_id, field)
                slot_ref = _slot_ref(field_id, operation.get("slot_ref"))
                placeholder_text = _placeholder(field, operation.get("placeholder_text"))
            elif action == "materialize_structure":
                assert registry is not None
                _reject_structure_parent_slot_identity(operation)
                structure_ref = _required_string(
                    operation.get("structure_ref"),
                    field="structure_ref",
                )
                field = registry.lookup(structure_ref)
                _require_structure_field(registry, structure_ref, field)
                raw_members = operation.get("members")
                if not isinstance(raw_members, list) or not raw_members:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="body_structure_members_invalid",
                        message="materialize_structure requires Harness-reviewed ordered members.",
                    )
                for raw_member in raw_members:
                    if not isinstance(raw_member, dict):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="body_structure_members_invalid",
                            message="Every structure member must be an object.",
                        )
                    member_selected = resolve_object_ref(raw_member.get("target_ref"), inspection)
                    member_field_id = _required_string(
                        raw_member.get("field_id"), field="members[].field_id"
                    )
                    member_field = registry.lookup(member_field_id)
                    _require_structure_member_field(
                        parent_field_id=structure_ref,
                        field_id=member_field_id,
                        field=member_field,
                        word_kind=member_selected.kind,
                    )
                    member_slot_ref = _slot_ref(member_field_id, raw_member.get("slot_ref"))
                    member_placeholder = _placeholder(
                        member_field, raw_member.get("placeholder_text")
                    )
                    members.append(
                        StructureMember(
                            selected=member_selected,
                            field_id=member_field_id,
                            slot_ref=member_slot_ref,
                            content_type=str(member_field.get("content_type", "text")),
                            placeholder_text=member_placeholder,
                            effective_format=_effective_format(raw_member.get("effective_format")),
                        )
                    )
                    public_members.append(
                        {
                            "field_id": member_field_id,
                            "slot_ref": member_slot_ref,
                            "target_ref": member_selected.object_ref,
                        }
                    )
                if str(selected.object_ref["object_id"]) != str(
                    members[0].selected.object_ref["object_id"]
                ):
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="body_structure_anchor_invalid",
                        message=(
                            "materialize_structure target_ref must be the first selected "
                            "member so the structure has one physical, snapshot-bound anchor."
                        ),
                    )
                raw_replaced = operation.get("replaced_structure_ref")
                if raw_replaced is not None:
                    replaced_structure = resolve_object_ref(raw_replaced, inspection)
            elif action == "refresh_toc":
                raw_entries = operation.get("toc_entries")
                if not isinstance(raw_entries, list) or not raw_entries:
                    raise ToolFailure(
                        status="needs_input",
                        origin="request",
                        code="toc_entries_invalid",
                        message="refresh_toc requires Harness-reviewed source titles and levels.",
                    )
                for raw_entry in raw_entries:
                    if not isinstance(raw_entry, dict):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entries_invalid",
                            message="Every TOC entry must be an object.",
                        )
                    entry_selected = resolve_object_ref(raw_entry.get("target_ref"), inspection)
                    level = raw_entry.get("level")
                    if (
                        not isinstance(level, int)
                        or isinstance(level, bool)
                        or level not in {1, 2, 3}
                    ):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="toc_entry_level_invalid",
                            message="Each TOC source title needs level 1, 2, or 3.",
                        )
                    toc_entries.append(TocEntry(entry_selected, level))
                    public_entries.append({"target_ref": entry_selected.object_ref, "level": level})
            elif action == "ensure_page_start" and operation.get("mode") != "new_page":
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="page_start_mode_invalid",
                    message="ensure_page_start requires mode=new_page.",
                )

            mutation = ObjectMutation(
                selected=selected,
                action=action,
                field_id=field_id,
                structure_ref=structure_ref,
                slot_ref=slot_ref,
                content_type=str(field.get("content_type", "text")) if field else "text",
                placeholder_text=placeholder_text,
                effective_format=effective_format,
                structure_members=tuple(members),
                replaced_structure=replaced_structure,
                toc_entries=tuple(toc_entries),
            )
            mutations.append(mutation)
            public_operations.append(
                {
                    "action": action,
                    "target_ref": selected.object_ref,
                    **({"field_id": field_id} if field_id else {}),
                    **({"structure_ref": structure_ref} if structure_ref else {}),
                    **({"slot_ref": slot_ref} if slot_ref else {}),
                    **({"members": public_members} if public_members else {}),
                    **({"toc_entries": public_entries} if public_entries else {}),
                }
            )
        return mutations, public_operations

    def _edit_domain(
        self,
        *,
        args: dict[str, Any],
        root: Path,
        input_docx: Path,
        output_docx: Path,
        inspection: Inspection,
        operations: list[JsonObject],
    ) -> JsonObject:
        source_hash = inspection.document_sha256
        phase_review = _post_unit_phase_review_for_domain_edit(
            root,
            input_candidate_hash=source_hash,
        )
        mutations, public_operations = self._domain_mutations(
            args=args,
            root=root,
            inspection=inspection,
            operations=operations,
            require_pre_input_registry=phase_review is not None,
        )
        if phase_review is not None:
            for operation in public_operations:
                _require_phase_reviewed_edit_operation(
                    review=phase_review,
                    edit_operation=operation,
                )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".docfit-domain-edit-",
            suffix=".docx",
            dir=output_docx.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            effects = mutate_objects(input_docx, temporary, mutations=mutations)
            package_warnings = list(normalize_docx_custom_properties(temporary))
            validate_docx_package(temporary)
            office_validation = self.office.validate(temporary)
            after = inspect_document(
                temporary,
                self.office,
                selector="paragraph, table, picture, run, sdt, shape",
            )
            if sha256_file(input_docx) != source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The immutable input changed; the edit was not published.",
                )
            output_hash = after.document_sha256
            os.replace(temporary, output_docx)
            return {
                "schema_version": 1,
                "status": "ok",
                "committed": True,
                "checks": [
                    {"name": "object_refs_bound", "result": "ok"},
                    {"name": "source_unchanged", "result": "ok", "sha256": source_hash},
                    {"name": "package_reopens", "result": "ok"},
                    {"name": "officecli_validate", "result": "ok", **office_validation},
                    {"name": "effects_re_read", "result": "ok"},
                ],
                "warnings": package_warnings,
                "failure": None,
                "input_sha256": source_hash,
                "output_sha256": output_hash,
                "output_docx": str(output_docx),
                "operations": [
                    {"index": index, **operation, "result": "applied"}
                    for index, operation in enumerate(public_operations)
                ],
                "effects": effects,
                "provider": self.office.evidence(),
            }
        finally:
            temporary.unlink(missing_ok=True)

    def edit(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
        input_docx = _document_path(args, "input_docx", root)
        output_docx = authorized_path(
            args.get("output_docx"),
            task_root=root,
            field="output_docx",
            must_exist=False,
        )
        require_docx(output_docx, field="output_docx")
        if input_docx == output_docx:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_overwrite_denied",
                message="docx_edit never writes over its input document.",
            )
        overwrite = args.get("overwrite", False)
        if not isinstance(overwrite, bool):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_overwrite_flag",
                message="overwrite must be a boolean.",
            )
        if output_docx.exists() and not overwrite:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="output_exists",
                message=(
                    "output_docx already exists; set overwrite only when replacement is intended."
                ),
            )
        operations = _require_operations(args.get("operations"))
        source_hash = sha256_file(input_docx)
        inspection = inspect_document_snapshot(
            input_docx,
            self.office,
            selector="paragraph, table, picture, run, sdt, shape",
        )
        domain_actions = [
            is_domain_edit_action(operation.get("action")) for operation in operations
        ]
        if any(domain_actions):
            if not all(domain_actions):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="mixed_edit_families",
                    message=(
                        "Keep direct template mutations and OfficeCLI/import edits in separate "
                        "atomic docx_edit calls so every snapshot has unambiguous refs."
                    ),
                )
            return self._edit_domain(
                args=args,
                root=root,
                input_docx=input_docx,
                output_docx=output_docx,
                inspection=inspection,
                operations=operations,
            )
        office_commands: list[JsonObject] = []
        import_plans: list[dict[str, Any]] = []
        effect_expectations: list[dict[str, Any]] = []
        changed_locators: set[str] = set()

        for operation in operations:
            action = operation.get("action")
            if action in {"replace_text", "apply_style", "set_properties"}:
                target = resolve_object_ref(operation.get("target_ref"), inspection)
                changed_locators.add(target.locator)
                if action == "replace_text":
                    expected = operation.get("expected_text")
                    replacement = operation.get("replacement")
                    if (
                        not isinstance(expected, str)
                        or not expected
                        or not isinstance(replacement, str)
                    ):
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="invalid_text_replacement",
                            message=(
                                "replace_text requires non-empty expected_text and string "
                                "replacement."
                            ),
                        )
                    if expected not in target.text:
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="expected_text_mismatch",
                            message="expected_text is absent from the referenced object.",
                        )
                    properties = {"find": expected, "replace": replacement}
                    effect_expectations.append(
                        {
                            "action": action,
                            "locator": target.locator,
                            "replacement": replacement,
                        }
                    )
                elif action == "apply_style":
                    style = operation.get("style")
                    if not isinstance(style, str) or not style:
                        raise ToolFailure(
                            status="needs_input",
                            origin="request",
                            code="invalid_style",
                            message="apply_style requires a non-empty style name.",
                        )
                    properties = {"style": style}
                    effect_expectations.append(
                        {"action": action, "locator": target.locator, "style": style}
                    )
                else:
                    properties = _scalar_properties(operation.get("properties"))
                    effect_expectations.append(
                        {"action": action, "locator": target.locator, "properties": properties}
                    )
                office_commands.append(
                    {"command": "set", "path": target.locator, "props": properties}
                )
                continue
            if action != "import_content_objects":
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="unsupported_edit_action",
                    message="An edit operation uses an unsupported M1 action.",
                )
            source_docx = _document_path(operation, "source_docx", root)
            if source_docx == input_docx:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="cross_document_source_required",
                    message=(
                        "Cross-document content import requires distinct source and target "
                        "documents."
                    ),
                )
            imported_source_hash = sha256_file(source_docx)
            if operation.get("source_sha256") != imported_source_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="content_source_hash_mismatch",
                    message="The source snapshot hash does not match source_sha256.",
                    suggested_actions=("inspect_source_again",),
                )
            source_inspection = inspect_document_snapshot(
                source_docx,
                self.office,
                selector="paragraph, table, picture, run, sdt, shape",
            )
            source_refs = operation.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_content_source_refs",
                    message="source_refs must be a non-empty array of source object refs.",
                )
            source_objects = [
                resolve_object_ref(reference, source_inspection) for reference in source_refs
            ]
            position = operation.get("position", "end")
            anchor_ref = operation.get("target_anchor_ref")
            anchor = resolve_object_ref(anchor_ref, inspection) if anchor_ref is not None else None
            include_section = operation.get("include_source_final_section_properties", False)
            if not isinstance(position, str) or not isinstance(include_section, bool):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="invalid_content_import_options",
                    message="Content import position or section option is invalid.",
                )
            import_plans.append(
                {
                    "action": action,
                    "source_docx": source_docx,
                    "source_sha256": imported_source_hash,
                    "source_locators": [item.locator for item in source_objects],
                    "source_texts": [item.text for item in source_objects if item.text],
                    "anchor_locator": anchor.locator if anchor else None,
                    "position": position,
                    "include_source_final_section_properties": include_section,
                }
            )

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".docfit-edit-",
            suffix=".docx",
            dir=output_docx.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        import_evidence: list[JsonObject] = []
        try:
            shutil.copyfile(input_docx, temporary)
            temporary.chmod(0o600)
            package_warnings = list(normalize_docx_custom_properties(temporary))
            if office_commands:
                self.office.batch(temporary, office_commands)
            for index, plan in enumerate(import_plans):
                imported = temporary.with_name(f"{temporary.stem}-import-{index}.docx")
                evidence = import_content_objects(
                    target_docx=temporary,
                    source_docx=plan["source_docx"],
                    source_locators=plan["source_locators"],
                    anchor_locator=plan["anchor_locator"],
                    position=plan["position"],
                    include_source_final_section_properties=plan[
                        "include_source_final_section_properties"
                    ],
                    output_docx=imported,
                )
                os.replace(imported, temporary)
                import_evidence.append(
                    {
                        **evidence,
                        "action": plan["action"],
                        "source_sha256": plan["source_sha256"],
                        "target_sha256_before": source_hash,
                    }
                )
            package_warnings.extend(normalize_docx_custom_properties(temporary))
            validate_docx_package(temporary)
            office_validation = self.office.validate(temporary)
            after = inspect_document(
                temporary,
                self.office,
                selector="paragraph, table, picture, run, sdt, shape",
            )
            after_by_locator = {item.locator: item for item in after.objects}
            for expectation in effect_expectations:
                actual = after_by_locator.get(expectation["locator"])
                if actual is None:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="edited_object_missing",
                        message="An edited object disappeared during the postcondition check.",
                    )
                if (
                    expectation["action"] == "replace_text"
                    and expectation["replacement"] not in actual.text
                ):
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="replacement_not_applied",
                        message="OfficeCLI reported success but the replacement is absent.",
                    )
                if expectation["action"] == "apply_style" and actual.style != expectation["style"]:
                    raise ToolFailure(
                        status="error",
                        origin="postcondition",
                        code="style_not_applied",
                        message="OfficeCLI reported success but the requested style is absent.",
                    )
                if expectation["action"] == "set_properties":
                    unapplied = [
                        key
                        for key, expected in expectation["properties"].items()
                        if not _property_applied(actual, key, expected)
                    ]
                    if unapplied:
                        raise ToolFailure(
                            status="error",
                            origin="postcondition",
                            code="properties_not_applied",
                            message=(
                                "OfficeCLI reported success but one or more requested "
                                "properties are absent."
                            ),
                        )
            protected_text = Counter(
                item.text
                for item in inspection.objects
                if item.text
                and not any(_locator_related(item.locator, changed) for changed in changed_locators)
            )
            resulting_text = Counter(item.text for item in after.objects if item.text)
            lost = protected_text - resulting_text
            if lost:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="non_target_content_changed",
                    message="A non-target text object was lost during editing.",
                )
            imported_text = Counter(text for plan in import_plans for text in plan["source_texts"])
            missing_imported = imported_text - resulting_text
            if missing_imported:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="imported_content_missing",
                    message="One or more selected source text objects are absent after import.",
                )
            if sha256_file(input_docx) != source_hash:
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="source_document_changed",
                    message="The source document changed during editing; output was not published.",
                )
            if any(
                sha256_file(plan["source_docx"]) != plan["source_sha256"] for plan in import_plans
            ):
                raise ToolFailure(
                    status="error",
                    origin="postcondition",
                    code="import_source_document_changed",
                    message=(
                        "A content source document changed during editing; output was not "
                        "published."
                    ),
                )
            output_hash = sha256_file(temporary)
            os.replace(temporary, output_docx)
            return {
                "schema_version": 1,
                "status": "ok",
                "committed": True,
                "checks": [
                    {"name": "request_preconditions", "result": "ok"},
                    {"name": "source_unchanged", "result": "ok", "sha256": source_hash},
                    {"name": "package_reopens", "result": "ok"},
                    {"name": "officecli_validate", "result": "ok", **office_validation},
                    {"name": "effects_re_read", "result": "ok"},
                    {"name": "non_target_text_preserved", "result": "ok"},
                ],
                "warnings": list(dict.fromkeys(package_warnings)),
                "failure": None,
                "input_sha256": source_hash,
                "output_sha256": output_hash,
                "output_docx": str(output_docx),
                "operations": [
                    {"index": index, "action": operation.get("action"), "result": "applied"}
                    for index, operation in enumerate(operations)
                ],
                "content_imports": import_evidence,
                "provider": self.office.evidence(),
            }
        finally:
            temporary.unlink(missing_ok=True)
            for leftover in output_docx.parent.glob(f"{temporary.stem}-import-*.docx"):
                leftover.unlink(missing_ok=True)

    def render(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        return self.visual().render(args)

    def visual_review(self, args: dict[str, Any]) -> tuple[JsonObject, list[Path]]:
        return self.visual().review(args)

    def validate(self, args: dict[str, Any]) -> JsonObject:
        root = self._session_root(args)
        source = _document_path(args, "source_docx", root)
        final = _document_path(args, "final_docx", root)
        source_hash = sha256_file(source)
        final_hash = sha256_file(final)
        expected_source = args.get("source_sha256")
        if expected_source is not None and expected_source != source_hash:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="source_hash_mismatch",
                message="The source document no longer matches source_sha256.",
            )
        validate_docx_package(final)
        source_office_validation = _office_validation_status(source, self.office)
        final_office_validation = _office_validation_status(final, self.office)
        if (
            source_office_validation["passed"] is True
            and final_office_validation["passed"] is not True
        ):
            raise ToolFailure(
                status="error",
                origin="engine",
                code=str(final_office_validation.get("code", "officecli_failed")),
                message="The final document introduced an OfficeCLI OpenXML regression.",
                retryable=False,
                suggested_actions=("inspect_request", "report_backend_failure"),
            )
        source_inspection = inspect_document_snapshot(source, self.office)
        final_inspection = inspect_document_snapshot(final, self.office)
        office_check: JsonObject = {
            "name": "officecli_openxml",
            "result": "ok" if final_office_validation["passed"] is True else "warning",
            "severity": "info" if final_office_validation["passed"] is True else "warning",
            "blocking": False,
            "evidence": final_office_validation["detail"],
            "suggested_action": None,
        }
        if final_office_validation["passed"] is not True:
            office_check["evidence"] = {
                "source": source_office_validation,
                "final": final_office_validation,
                "new_officecli_regression": "UNKNOWN",
            }
            office_check["suggested_action"] = (
                "Repair source-inherited OpenXML validation warnings when strict "
                "schema acceptance is required."
            )
        checks: list[JsonObject] = [
            {
                "name": "docx_opens",
                "result": "ok",
                "severity": "info",
                "blocking": False,
                "evidence": "Independent ZIP/XML reopen passed.",
                "suggested_action": None,
            },
            office_check,
            {
                "name": "source_unchanged",
                "result": "ok",
                "severity": "info",
                "blocking": False,
                "evidence": {"source_sha256": source_hash},
                "suggested_action": None,
            },
        ]
        source_text = [item.text for item in source_inspection.objects if item.text]
        final_text = [item.text for item in final_inspection.objects if item.text]
        missing_text = Counter(source_text) - Counter(final_text)
        if missing_text:
            checks.append(
                {
                    "name": "content_preservation",
                    "result": "issue",
                    "severity": "warning",
                    "blocking": False,
                    "evidence": {"missing_object_count": sum(missing_text.values())},
                    "suggested_action": "Review intended replacements against source content.",
                }
            )
        else:
            checks.append(
                {
                    "name": "content_preservation",
                    "result": "ok",
                    "severity": "info",
                    "blocking": False,
                    "evidence": {"source_text_objects_preserved": len(source_text)},
                    "suggested_action": None,
                }
            )
        placeholders = ("在此填写", "TODO", "{{", "XXXXX")
        placeholder_count = sum(
            text.count(marker) for text in final_text for marker in placeholders
        )
        checks.append(
            {
                "name": "placeholder_scan",
                "result": "issue" if placeholder_count else "ok",
                "severity": "error" if placeholder_count else "info",
                "blocking": bool(placeholder_count),
                "evidence": {"placeholder_occurrences": placeholder_count},
                "suggested_action": (
                    "Replace or explicitly waive every remaining placeholder."
                    if placeholder_count
                    else None
                ),
            }
        )
        warnings: list[JsonObject] = []
        visual_value = args.get("visual_review")
        candidate_value = args.get("candidate_render_ref")
        reviewed_pages: set[int] = set()
        blocking_findings = 0
        if visual_value is not None:
            if isinstance(visual_value, str):
                visual_path = authorized_path(
                    visual_value,
                    task_root=root,
                    field="visual_review",
                )
                visual = read_json(visual_path)
            elif isinstance(visual_value, dict):
                visual = dict(visual_value)
            else:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="visual_review_invalid",
                    message="visual_review must be a task-local JSON path or an evidence object.",
                )
            if visual.get("document_sha256") != final_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="visual_review_document_mismatch",
                    message="visual_review is not bound to the final document snapshot.",
                )
            raw_pages = visual.get("reviewed_pages", [])
            if isinstance(raw_pages, list):
                reviewed_pages = {item for item in raw_pages if isinstance(item, int)}
            findings = visual.get("findings", [])
            if isinstance(findings, list):
                blocking_findings = sum(
                    1
                    for finding in findings
                    if isinstance(finding, dict)
                    and (finding.get("blocking") is True or finding.get("severity") == "blocking")
                )
        candidate: JsonObject | None = None
        if candidate_value is not None:
            _, candidate = self.visual().store.resolve_render(candidate_value)
            if candidate.get("document_sha256") != final_hash:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="candidate_document_mismatch",
                    message="candidate_render_ref is not bound to the final document snapshot.",
                )
        page_count_value = candidate.get("page_count") if candidate is not None else None
        if isinstance(page_count_value, bool):
            page_count = 0
        elif isinstance(page_count_value, int):
            page_count = page_count_value
        elif isinstance(page_count_value, str) and page_count_value.isdecimal():
            page_count = int(page_count_value)
        else:
            page_count = 0
        expected_pages = set(range(1, page_count + 1)) if page_count > 0 else set()
        all_pages_covered = candidate is not None and reviewed_pages == expected_pages
        missing_pages = sorted(expected_pages - reviewed_pages)
        unexpected_pages = sorted(reviewed_pages - expected_pages)
        current_visual_snapshot = (
            candidate is not None
            and candidate.get("fidelity") == "approximate"
            and isinstance(candidate.get("renderer"), dict)
            and candidate["renderer"].get("name") == "libreoffice"
        )
        visual_ok = current_visual_snapshot and all_pages_covered and blocking_findings == 0
        visual_required = args.get("required_visual_coverage") == "all_final_pages"
        checks.append(
            {
                "name": "visual_review_coverage",
                "result": "ok" if visual_ok else ("issue" if visual_required else "warning"),
                "severity": (
                    "error"
                    if visual_required and not visual_ok
                    else "warning"
                    if not visual_ok
                    else "info"
                ),
                "blocking": visual_required and not visual_ok,
                "feedback": {
                    "type": "completion",
                    "mechanical": True,
                    "semantic_authority": False,
                    "agent_action": (
                        "Render the exact final candidate, review every final page, "
                        "repair blocking findings, and validate again."
                    ),
                },
                "evidence": {
                    "current_visual_snapshot": current_visual_snapshot,
                    "all_final_pages_reviewed": all_pages_covered,
                    "page_count": page_count if page_count > 0 else None,
                    "reviewed_pages": sorted(reviewed_pages),
                    "missing_pages": missing_pages,
                    "unexpected_pages": unexpected_pages,
                    "blocking_findings": blocking_findings,
                },
                "suggested_action": (
                    None
                    if visual_ok
                    else "Render the current final DOCX and review every final page."
                ),
            }
        )
        if not visual_ok:
            warnings.append(
                {
                    "code": "verification_gap",
                    "kind": "visual_review",
                    "message": (
                        "Current LibreOffice render evidence and complete Agent page coverage "
                        "are absent or incomplete."
                    ),
                }
            )
        issue_count = sum(check["result"] == "issue" for check in checks)
        warning_count = sum(check["result"] == "warning" for check in checks) + len(warnings)
        error_count = sum(check.get("blocking") is True for check in checks)
        return {
            "schema_version": 1,
            "status": "ok",
            "checks": checks,
            "warnings": warnings,
            "failure": None,
            "source_sha256": source_hash,
            "final_sha256": final_hash,
            "knowledge_version": args.get("knowledge_version"),
            "task_rule_evidence": args.get("task_rule_evidence", []),
            "summary": {
                "errors": error_count,
                "issues": issue_count,
                "warnings": warning_count,
            },
            "provider": self.office.evidence(),
        }


def image_content_blocks(paths: list[Path]) -> list[JsonObject]:
    blocks: list[JsonObject] = []
    for path in paths:
        verify_png(path)
        blocks.append(
            {
                "type": "image",
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                "mimeType": "image/png",
            }
        )
    return blocks


def tool_result(structured: JsonObject, *, image_paths: list[Path] | None = None) -> JsonObject:
    status = structured.get("status")
    content: list[JsonObject] = [
        {
            "type": "text",
            # claude-agent-sdk 0.2.128's in-process MCP bridge currently omits
            # structuredContent when it builds CallToolResult. Mirror the same
            # payload as compact text so the Agent can actually consume refs,
            # artifacts, and validation evidence without gaining file-read access.
            "text": json.dumps(
                structured,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
    ]
    if image_paths:
        content.extend(image_content_blocks(image_paths))
    result: JsonObject = {"content": content, "structuredContent": structured}
    if status == "error":
        result["is_error"] = True
    return result


def failure_result(error: ToolFailure, *, committed: bool | None = None) -> JsonObject:
    return tool_result(error.result(committed=committed))


def unexpected_failure_result(*, committed: bool | None = None) -> JsonObject:
    failure = ToolFailure(
        status="error",
        origin="adapter",
        code="unexpected_adapter_error",
        message=(
            "DocFit encountered an unexpected adapter error; no unverified output was published."
        ),
    )
    return failure_result(failure, committed=committed)
