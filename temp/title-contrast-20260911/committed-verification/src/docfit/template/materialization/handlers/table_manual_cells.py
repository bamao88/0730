"""Manual table/cell materialization policy handler."""

from __future__ import annotations

from docfit.template.materialization.models import (
    MaterializationContext,
    MaterializationContextKind,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
)
from docfit.tools.runtime import JsonObject


def manual_table_cell_policy_receipts(plan: MaterializationPlan) -> list[JsonObject]:
    contexts_by_intent = _contexts_by_intent_ref(plan.contexts)
    receipts: list[JsonObject] = []
    for intent in plan.intents:
        if intent.intent_type != MaterializationIntentType.KEEP_MANUAL_TABLE_CELL:
            continue
        context = contexts_by_intent.get(intent.intent_ref)
        if context is None or context.kind != MaterializationContextKind.MANUAL_TABLE_CELL.value:
            continue
        receipts.append(_manual_table_receipt(intent=intent, context=context))
    return receipts


def _manual_table_receipt(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
) -> JsonObject:
    return {
        "action": "keep_manual_table_cell",
        "handler": "table_manual_cells",
        "intent_ref": intent.intent_ref,
        "source_judgment_refs": list(intent.source_judgment_refs),
        "scope_refs": [scope.to_json() for scope in intent.scope_refs],
        "mutation": "none",
        "policy": "keep_as_single_manual_carrier",
        "reason": "Manual table/cell scope is preserved as one school form area.",
        "reading_blocks": _reading_blocks(context),
    }


def _contexts_by_intent_ref(
    contexts: tuple[MaterializationContext, ...],
) -> dict[str, MaterializationContext]:
    result: dict[str, MaterializationContext] = {}
    for context in contexts:
        intent_ref = context.facts.get("intent_ref")
        if isinstance(intent_ref, str) and intent_ref.strip():
            result[intent_ref] = context
    return result


def _reading_blocks(context: MaterializationContext) -> list[JsonObject]:
    raw_blocks = context.facts.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return []
    return [dict(item) for item in raw_blocks if isinstance(item, dict)]
