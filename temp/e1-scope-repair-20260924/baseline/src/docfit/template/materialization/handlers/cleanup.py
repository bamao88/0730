"""Cleanup intent helpers for accepted ordered semantic parts."""

from __future__ import annotations

from docfit.template.materialization.models import MaterializationIntent
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


def exact_shape_cleanup_locator(intent: MaterializationIntent) -> str | None:
    """A shape-only cleanup can remove that object without removing its paragraph.

    This selects only the accepted execution object, never an ancestor or a text
    match. Runtime additionally checks the shape's complete text before deletion.
    """
    if not intent.resolved_spans or any(span.role != "cleanup" for span in intent.resolved_spans):
        return None
    locators = []
    for span in intent.resolved_spans:
        if not span.word_fragments:
            return None
        for fragment in span.word_fragments:
            locator = fragment.get("locator")
            if not isinstance(locator, str) or not locator.rsplit("/", 1)[-1].startswith("shape["):
                return None
            locators.append(locator)
    return locators[0] if len(set(locators)) == 1 else None
