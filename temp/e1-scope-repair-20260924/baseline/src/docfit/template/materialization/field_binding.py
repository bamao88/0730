"""Accepted ordered-part Registry field bindings for materialization intents."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

FIELD_CARRYING_PART_ROLES = frozenset(
    {
        "fill_slot",
        "body_structure",
        "generated_content",
    }
)


def _part_role(part: JsonObject) -> str:
    role = part.get("role")
    return role.strip() if isinstance(role, str) else ""


def explicit_field_ids_from_source(source: JsonObject) -> list[str]:
    field_id = source.get("field_id")
    if not isinstance(field_id, str) or not field_id.strip():
        return []
    return [field_id.strip()]


def ordered_parts(judgment: JsonObject) -> list[JsonObject]:
    raw_parts = judgment.get("parts")
    if not isinstance(raw_parts, list):
        return []
    return [part for part in raw_parts if isinstance(part, dict)]


def semantic_part_is_slot(part: JsonObject) -> bool:
    return _part_role(part) == "fill_slot"


def semantic_part_carries_field(part: JsonObject) -> bool:
    return _part_role(part) in FIELD_CARRYING_PART_ROLES


def explicit_materialization_field_ids(judgment: JsonObject) -> list[str]:
    field_ids: list[str] = []
    for part in ordered_parts(judgment):
        if semantic_part_carries_field(part):
            field_ids.extend(explicit_field_ids_from_source(part))
    return list(dict.fromkeys(field_ids))
