"""Cleanup intent helpers for accepted ordered semantic parts."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject


def is_delete_treatment(judgment: JsonObject) -> bool:
    parts = _parts(judgment)
    return bool(parts) and all(_part_role(part) == "cleanup" for part in parts)


def should_remove_paragraph(judgment: JsonObject) -> bool:
    return is_delete_treatment(judgment)


def _parts(judgment: JsonObject) -> list[JsonObject]:
    raw_parts = judgment.get("parts")
    if not isinstance(raw_parts, list):
        return []
    return [part for part in raw_parts if isinstance(part, dict)]


def _part_role(part: JsonObject) -> str:
    role = part.get("role")
    return role.strip() if isinstance(role, str) else ""
