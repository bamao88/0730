"""Generated-content materialization policy handler."""

from __future__ import annotations

from docfit.template.materialization.models import (
    MaterializationContext,
    MaterializationContextKind,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
)
from docfit.tools.runtime import JsonObject


def generated_content_policy_receipts(plan: MaterializationPlan) -> list[JsonObject]:
    contexts_by_intent = _contexts_by_intent_ref(plan.contexts)
    receipts: list[JsonObject] = []
    for intent in plan.intents:
        if intent.intent_type != MaterializationIntentType.REFRESH_GENERATED_CONTENT:
            continue
        context = contexts_by_intent.get(intent.intent_ref)
        if context is None or context.kind != MaterializationContextKind.GENERATED_CONTENT.value:
            continue
        receipts.append(_generated_content_receipt(intent=intent, context=context))
    return receipts


def _generated_content_receipt(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
) -> JsonObject:
    return {
        "action": "refresh_generated_content",
        "handler": "generated_content",
        "intent_ref": intent.intent_ref,
        "source_judgment_refs": list(intent.source_judgment_refs),
        "scope_refs": [scope.to_json() for scope in intent.scope_refs],
        "field_ids": list(intent.field_ids),
        "span_refs": _span_refs(intent),
        "mutation": "none",
        "policy": "refresh_from_word_fields_after_fill",
        "reason": "Generated content is preserved as a Word-generated area, not a student slot.",
        "resolved_spans": [span.to_json() for span in intent.resolved_spans],
        "word_fragments": [
            dict(fragment)
            for span in intent.resolved_spans
            for fragment in span.word_fragments
        ],
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


def _span_refs(intent: MaterializationIntent) -> list[str]:
    return list(dict.fromkeys(span.span_ref for span in intent.resolved_spans))
