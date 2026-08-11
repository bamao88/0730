"""Read-only pre-write inventory of presentation roles in accepted student content."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docfit.styles.actual_roles import ActualStyleRoleSet
from docfit.styles.presets import GeneralStylePreset
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

HEADING_1_PATTERN = re.compile(r"^第[一二三四五六七八九十百]+章(?:\s|$)")
HEADING_2_PATTERN = re.compile(r"^\d+[.、]?\s*[^\d.]", re.DOTALL)
HEADING_3_PATTERN = re.compile(r"^\d+\.\d+(?!\.)")
FIGURE_CAPTION_PATTERN = re.compile(
    r"^(?:图\s*\d|Fig(?:ure)?\.?\s*\d)", re.IGNORECASE
)
TABLE_CAPTION_PATTERN = re.compile(r"^(?:表\s*\d|Table\s*\d)", re.IGNORECASE)


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_presentation_role_inventory",),
    )


def classify_body_text(text: str, *, word_style_id: str = "") -> str:
    """Return the semantic field used by both preflight and final Projection."""

    normalized_style = word_style_id.strip().casefold().replace("_", " ")
    style_level = re.search(r"(?:heading|标题)\s*([1-5])", normalized_style)
    if style_level is not None:
        return f"body.heading.level{style_level.group(1)}"
    value = text.strip()
    if FIGURE_CAPTION_PATTERN.match(value):
        return "body.figure.caption"
    if TABLE_CAPTION_PATTERN.match(value):
        return "body.table.caption"
    if HEADING_1_PATTERN.match(value):
        return "body.heading.level1"
    if len(value) <= 100 and HEADING_3_PATTERN.match(value):
        return "body.heading.level3"
    if len(value) <= 80 and HEADING_2_PATTERN.match(value):
        return "body.heading.level2"
    return "body.paragraph"


@dataclass(frozen=True, slots=True)
class PresentationRoleOccurrence:
    source_object_id: str
    field_id: str
    kind: str
    body_sequence: int

    def as_dict(self) -> JsonObject:
        return {
            "source_object_id": self.source_object_id,
            "field_id": self.field_id,
            "kind": self.kind,
            "body_sequence": self.body_sequence,
        }


@dataclass(frozen=True, slots=True)
class PresentationRoleInventory:
    source_sha256: str
    occurrences: tuple[PresentationRoleOccurrence, ...]
    field_ids: tuple[str, ...]
    inventory_digest: str

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": "docfit-presentation-role-inventory/v1",
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
    """Classify only the already accepted body range; extraction remains untouched."""

    source_sha256 = student_inventory.get("source_sha256")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        raise _failure(
            "presentation_role_source_invalid",
            "Student inventory requires a source SHA-256.",
        )
    segments = student_content.get("segments")
    if not isinstance(segments, Sequence) or isinstance(segments, str | bytes):
        raise _failure(
            "presentation_role_body_segment_missing",
            "Accepted Student Content has no normalized segment list.",
        )
    body = next(
        (
            item
            for item in segments
            if isinstance(item, Mapping) and item.get("field_id") == "body.chapters"
        ),
        None,
    )
    if body is None or body.get("status") != "extracted":
        return _build_inventory(source_sha256, ())
    source_ids = body.get("source_object_ids")
    if not isinstance(source_ids, Sequence) or isinstance(source_ids, str | bytes):
        raise _failure(
            "presentation_role_body_segment_invalid",
            "The accepted body segment has no ordered source object IDs.",
        )
    raw_objects = student_inventory.get("objects")
    if not isinstance(raw_objects, Sequence) or isinstance(raw_objects, str | bytes):
        raise _failure(
            "presentation_role_inventory_invalid",
            "Student inventory has no object list.",
        )
    by_id = {
        str(reference.get("object_id")): item
        for item in raw_objects
        if isinstance(item, Mapping)
        and isinstance((reference := item.get("source_object_ref")), Mapping)
        and isinstance(reference.get("object_id"), str)
    }
    occurrences: list[PresentationRoleOccurrence] = []
    for index, source_id in enumerate(source_ids, start=1):
        if not isinstance(source_id, str) or source_id not in by_id:
            raise _failure(
                "presentation_role_source_object_missing",
                "The accepted body range references an object absent from the inventory.",
            )
        item = by_id[source_id]
        kind = item.get("kind")
        content_type = item.get("content_type")
        text = item.get("text")
        style = item.get("style", "")
        body_sequence = item.get("body_sequence", index)
        if not isinstance(kind, str) or not isinstance(text, str):
            raise _failure(
                "presentation_role_source_object_invalid",
                "A body object lacks kind or exact visible text.",
            )
        if kind == "table":
            field_id = "body.table"
        elif content_type == "equation":
            field_id = "body.equation"
        else:
            field_id = classify_body_text(
                text,
                word_style_id=style if isinstance(style, str) else "",
            )
        occurrences.append(
            PresentationRoleOccurrence(
                source_object_id=source_id,
                field_id=field_id,
                kind=kind,
                body_sequence=(body_sequence if isinstance(body_sequence, int) else index),
            )
        )
    return _build_inventory(source_sha256, occurrences)


def _build_inventory(
    source_sha256: str,
    occurrences: Sequence[PresentationRoleOccurrence],
) -> PresentationRoleInventory:
    normalized = tuple(sorted(occurrences, key=lambda item: item.body_sequence))
    field_ids = tuple(sorted({item.field_id for item in normalized}))
    payload: JsonObject = {
        "schema_version": "docfit-presentation-role-inventory/v1",
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
    """Union scalar/segment content and pre-write body roles with retained/global needs."""

    student_fields: set[str] = set(presentation_roles.field_ids)
    for collection_name in ("fields", "segments"):
        collection = student_content.get(collection_name)
        if not isinstance(collection, Sequence) or isinstance(collection, str | bytes):
            raise _failure(
                "presentation_role_student_content_invalid",
                f"Student Content {collection_name} must be a normalized array.",
            )
        for item in collection:
            if (
                isinstance(item, Mapping)
                and item.get("status") == "extracted"
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
    "FIGURE_CAPTION_PATTERN",
    "HEADING_1_PATTERN",
    "HEADING_2_PATTERN",
    "HEADING_3_PATTERN",
    "PresentationRoleInventory",
    "PresentationRoleOccurrence",
    "TABLE_CAPTION_PATTERN",
    "classify_body_text",
    "compile_actual_roles_from_student",
    "compile_presentation_role_inventory",
]
