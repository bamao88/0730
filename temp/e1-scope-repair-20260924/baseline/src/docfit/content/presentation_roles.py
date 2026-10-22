"""Compile presentation needs from accepted Student Content Model semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docfit.styles.actual_roles import ActualStyleRoleSet
from docfit.styles.presets import GeneralStylePreset
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_student_content_model",),
    )


@dataclass(frozen=True, slots=True)
class PresentationRoleOccurrence:
    content_id: str
    source_content_id: str
    transport_source_object_id: str
    field_id: str
    physical_type: str
    source_order: tuple[int, int]

    def as_dict(self) -> JsonObject:
        return {
            "content_id": self.content_id,
            "source_content_id": self.source_content_id,
            "transport_source_object_id": self.transport_source_object_id,
            "field_id": self.field_id,
            "physical_type": self.physical_type,
            "source_order": {
                "block": self.source_order[0],
                "inline": self.source_order[1],
            },
        }


@dataclass(frozen=True, slots=True)
class PresentationRoleInventory:
    source_sha256: str
    occurrences: tuple[PresentationRoleOccurrence, ...]
    field_ids: tuple[str, ...]
    inventory_digest: str

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": "docfit-presentation-role-inventory/v2",
            "source_sha256": self.source_sha256,
            "occurrences": [item.as_dict() for item in self.occurrences],
            "field_ids": list(self.field_ids),
            "presentation_role_inventory_digest": self.inventory_digest,
        }


def compile_presentation_role_inventory(
    *,
    student_content: Mapping[str, Any],
    student_inventory: Mapping[str, Any],
) -> PresentationRoleInventory:
    """Read body role labels from items; never infer roles from text or Word styles."""

    source_sha256 = student_content.get("source_sha256")
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or student_inventory.get("source_sha256") != source_sha256
    ):
        raise _failure(
            "presentation_role_source_invalid",
            "Student Content and its source inventory must bind the same SHA-256.",
        )
    raw_items = student_content.get("items")
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, str | bytes):
        raise _failure(
            "presentation_role_student_items_invalid",
            "Student Content has no ordered item list.",
        )
    occurrences: list[PresentationRoleOccurrence] = []
    previous_order: tuple[int, int] | None = None
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise _failure(
                "presentation_role_student_item_invalid",
                "A Student Content item has an invalid shape.",
            )
        order = _source_order(raw)
        if previous_order is not None and order <= previous_order:
            raise _failure(
                "presentation_role_order_invalid",
                "Student Content items are not in strict source order.",
            )
        previous_order = order
        field_id = raw.get("field_id")
        if (
            raw.get("classification_status") != "classified"
            or not isinstance(field_id, str)
            or not _is_body_field(field_id)
        ):
            continue
        content_id = raw.get("content_id")
        source_content_id = raw.get("source_content_id")
        transport_source_object_id = raw.get("transport_source_object_id")
        physical_type = raw.get("physical_type")
        if not all(
            isinstance(value, str)
            for value in (
                content_id,
                source_content_id,
                transport_source_object_id,
                physical_type,
            )
        ):
            raise _failure(
                "presentation_role_student_item_invalid",
                "A classified body item lacks stable identity or source evidence.",
            )
        occurrences.append(
            PresentationRoleOccurrence(
                content_id=str(content_id),
                source_content_id=str(source_content_id),
                transport_source_object_id=str(transport_source_object_id),
                field_id=field_id,
                physical_type=str(physical_type),
                source_order=order,
            )
        )
    return _build_inventory(source_sha256, occurrences)


def _source_order(item: Mapping[str, Any]) -> tuple[int, int]:
    value = item.get("source_order")
    if not isinstance(value, Mapping):
        raise _failure(
            "presentation_role_order_invalid",
            "A Student Content item has no source order.",
        )
    block = value.get("block")
    inline = value.get("inline")
    if (
        not isinstance(block, int)
        or isinstance(block, bool)
        or not isinstance(inline, int)
        or isinstance(inline, bool)
    ):
        raise _failure(
            "presentation_role_order_invalid",
            "A Student Content item has an invalid source order.",
        )
    return block, inline


def _is_body_field(field_id: str) -> bool:
    return field_id.startswith("body.") or field_id.startswith("conclusion.")


def _build_inventory(
    source_sha256: str,
    occurrences: Sequence[PresentationRoleOccurrence],
) -> PresentationRoleInventory:
    normalized = tuple(occurrences)
    field_ids = tuple(sorted({item.field_id for item in normalized}))
    payload: JsonObject = {
        "schema_version": "docfit-presentation-role-inventory/v2",
        "source_sha256": source_sha256,
        "occurrences": [item.as_dict() for item in normalized],
        "field_ids": list(field_ids),
    }
    return PresentationRoleInventory(
        source_sha256=source_sha256,
        occurrences=normalized,
        field_ids=field_ids,
        inventory_digest=sha256_json(payload),
    )


def compile_actual_roles_from_student(
    *,
    preset: GeneralStylePreset,
    student_content: Mapping[str, Any],
    presentation_roles: PresentationRoleInventory,
    retained_field_ids: Sequence[str] = (),
    global_field_ids: Sequence[str] = (),
) -> ActualStyleRoleSet:
    """Union actual item field IDs with retained and document-global style needs."""

    student_fields: set[str] = set(presentation_roles.field_ids)
    raw_items = student_content.get("items")
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, str | bytes):
        raise _failure(
            "presentation_role_student_items_invalid",
            "Student Content items must be a normalized array.",
        )
    for item in raw_items:
        if (
            isinstance(item, Mapping)
            and item.get("classification_status") == "classified"
            and isinstance(item.get("field_id"), str)
        ):
            student_fields.add(str(item["field_id"]))
    return ActualStyleRoleSet.compile(
        preset=preset,
        student_field_ids=student_fields,
        retained_field_ids=retained_field_ids,
        global_field_ids=global_field_ids,
    )


__all__ = [
    "PresentationRoleInventory",
    "PresentationRoleOccurrence",
    "compile_actual_roles_from_student",
    "compile_presentation_role_inventory",
]
