"""Shared materialization intent classification helpers."""

from __future__ import annotations

from docfit.template.materialization.models import MaterializationIntentType
from docfit.tools.runtime import JsonObject

DIRECT_INTENT_KEYS = ("materialization_intent", "intent_type")


def direct_intent_type(judgment: JsonObject) -> MaterializationIntentType | None:
    for value in direct_intent_values(judgment):
        for intent_type in MaterializationIntentType:
            if value == intent_type.value:
                return intent_type
    return None


def direct_intent_values(judgment: JsonObject) -> tuple[str, ...]:
    values: list[str] = []
    for key in DIRECT_INTENT_KEYS:
        raw = _normalized_text(judgment.get(key))
        if raw:
            values.append(raw)
    return tuple(values)


def invalid_direct_intent_values(judgment: JsonObject) -> tuple[str, ...]:
    allowed = {intent_type.value for intent_type in MaterializationIntentType}
    return tuple(value for value in direct_intent_values(judgment) if value not in allowed)


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().casefold()
