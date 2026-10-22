"""Plan-level validation for shadow materialization intents."""

from __future__ import annotations

from docfit.template.materialization.handlers.cleanup import exact_shape_cleanup_locator
from docfit.template.materialization.models import (
    MaterializationContext,
    MaterializationContextKind,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
    UnsupportedMaterialization,
)
from docfit.tools.runtime import JsonObject


def validate_materialization_plan(
    *,
    plan: MaterializationPlan,
) -> tuple[UnsupportedMaterialization, ...]:
    contexts_by_intent_ref = _contexts_by_intent_ref(plan.contexts)
    cleanup_conflicts = _cleanup_conflicts_by_carrier(plan.intents)
    unsupported: list[UnsupportedMaterialization] = []
    manual_scopes = {
        (scope.kind, scope.ref_id)
        for context in plan.contexts
        if context.kind == MaterializationContextKind.MANUAL_TABLE_CELL.value
        for scope in context.scope_refs
    }
    generated_scopes = {
        (scope.kind, scope.ref_id)
        for context in plan.contexts
        if context.kind == MaterializationContextKind.GENERATED_CONTENT.value
        for scope in context.scope_refs
    }
    for position, intent in enumerate(plan.intents, start=1):
        context = contexts_by_intent_ref.get(intent.intent_ref)
        if context is None:
            unsupported.append(
                _unsupported(
                    position=position,
                    intent=intent,
                    reason_code="materialization_context_missing",
                    message="Intent has no resolved execution context.",
                    missing_requirements=("resolved_context",),
                )
            )
            continue
        owned_cleanup_conflicts = [
            conflict_intents
            for conflict_intents in cleanup_conflicts.values()
            if conflict_intents[0].intent_ref == intent.intent_ref
        ]
        for conflict_index, conflict_intents in enumerate(
            owned_cleanup_conflicts,
            start=1,
        ):
            source_judgment_refs = tuple(
                dict.fromkeys(
                    source_judgment_ref
                    for conflict_intent in conflict_intents
                    for source_judgment_ref in conflict_intent.source_judgment_refs
                )
            )
            scope_refs = tuple(
                {
                    (scope.kind, scope.ref_id): scope
                    for conflict_intent in conflict_intents
                    for scope in conflict_intent.scope_refs
                }.values()
            )
            unsupported.append(
                UnsupportedMaterialization(
                    unsupported_ref=(
                        f"plan-unsupported-{position:04d}-cleanup-conflict-"
                        f"{conflict_index:02d}"
                    ),
                    source_judgment_refs=source_judgment_refs,
                    scope_refs=scope_refs,
                    reason_code="materialization_cleanup_carrier_conflict",
                    message=(
                        "The same Word carrier has both cleanup deletion and retained or "
                        "materialized semantic content. The current block deletion cannot "
                        "preserve the other accepted content; execution must stop without "
                        "changing the semantic judgments."
                    ),
                    missing_requirements=("one_treatment_per_word_carrier",),
                    payload={
                        "intent_refs": [
                            conflict_intent.intent_ref
                            for conflict_intent in conflict_intents
                        ]
                    },
                )
            )
        if _slot_conflicts_with_manual_table(
            intent=intent,
            manual_scopes=manual_scopes,
        ):
            unsupported.append(
                _unsupported(
                    position=position,
                    intent=intent,
                    reason_code="manual_table_cell_blocks_slot",
                    message=(
                        "A manual table context covers this slot scope. The plan must keep "
                        "the manual cell/table as a single carrier instead of splitting child "
                        "fields."
                    ),
                    missing_requirements=("manual_table_scope_resolution",),
                )
            )
        if _cleanup_conflicts_with_manual_table(
            intent=intent,
            manual_scopes=manual_scopes,
        ):
            unsupported.append(
                _unsupported(
                    position=position,
                    intent=intent,
                    reason_code="manual_table_cell_blocks_cleanup",
                    message=(
                        "A manual table context covers this cleanup scope. The plan must keep "
                        "the manual cell/table as a single carrier instead of deleting child "
                        "content."
                    ),
                    missing_requirements=("manual_table_scope_resolution",),
                )
            )
        if _slot_conflicts_with_generated_content(
            intent=intent,
            generated_scopes=generated_scopes,
        ):
            unsupported.append(
                _unsupported(
                    position=position,
                    intent=intent,
                    reason_code="generated_content_blocks_slot",
                    message=(
                        "A generated-content context covers this slot scope. Generated TOC/list "
                        "areas must be represented as refresh policy, not student field slots."
                    ),
                    missing_requirements=("generated_content_scope_resolution",),
                )
            )
        if _delete_requires_cleanup_safety(intent=intent, context=context):
            unsupported.append(
                _unsupported(
                    position=position,
                    intent=intent,
                    reason_code="cleanup_safety_missing",
                    message=(
                        "Delete intent is not limited to an instruction note or "
                        "cleanup-only ordered parts."
                    ),
                    missing_requirements=("cleanup_ordered_parts",),
                )
            )
    return tuple(unsupported)


def _paragraph_carrier_locator(locator: str) -> str:
    paragraph_marker = "/p["
    paragraph_start = locator.rfind(paragraph_marker)
    if paragraph_start < 0:
        return locator
    paragraph_end = locator.find("]", paragraph_start)
    return locator if paragraph_end < 0 else locator[: paragraph_end + 1]


def _intent_carriers(intent: MaterializationIntent) -> set[str]:
    carriers: set[str] = set()
    for span in intent.resolved_spans:
        for fragment in span.word_fragments:
            locator = fragment.get("locator")
            if isinstance(locator, str) and locator.strip():
                carriers.add(_paragraph_carrier_locator(locator.strip()))
    return carriers


def _cleanup_conflicts_by_carrier(
    intents: tuple[MaterializationIntent, ...],
) -> dict[str, tuple[MaterializationIntent, ...]]:
    conflicts: dict[str, list[MaterializationIntent]] = {}
    for deletion in intents:
        if deletion.intent_type != MaterializationIntentType.DELETE_BLOCK:
            continue
        shape_locator = exact_shape_cleanup_locator(deletion)
        carriers = {shape_locator} if shape_locator is not None else _intent_carriers(deletion)
        for carrier in carriers:
            retained = []
            for other in intents:
                if other.intent_type == MaterializationIntentType.DELETE_BLOCK:
                    continue
                locators = [
                    fragment.get("locator")
                    for span in other.resolved_spans for fragment in span.word_fragments
                ]
                rewrites_paragraph = other.intent_type in {
                    MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
                    MaterializationIntentType.MATERIALIZE_SLOT,
                } or any(
                    span.role in {"cleanup", "style_only"} and span.text
                    for span in other.resolved_spans
                )
                if any(
                    isinstance(locator, str)
                    and (locator == carrier or locator.startswith(carrier + "/"))
                    for locator in locators
                ) or (shape_locator is None and carrier in _intent_carriers(other)) or (
                    shape_locator is not None and rewrites_paragraph
                    and _paragraph_carrier_locator(shape_locator) in _intent_carriers(other)
                ):
                    retained.append(other)
            if retained:
                group = conflicts.setdefault(carrier, [])
                for intent in [deletion, *retained]:
                    if intent not in group:
                        group.append(intent)
    order = {intent.intent_ref: index for index, intent in enumerate(intents)}
    return {
        carrier: tuple(sorted(group, key=lambda intent: order[intent.intent_ref]))
        for carrier, group in conflicts.items()
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


def _slot_conflicts_with_manual_table(
    *,
    intent: MaterializationIntent,
    manual_scopes: set[tuple[str, str]],
) -> bool:
    if intent.intent_type != MaterializationIntentType.MATERIALIZE_SLOT:
        return False
    return any((scope.kind, scope.ref_id) in manual_scopes for scope in intent.scope_refs)


def _cleanup_conflicts_with_manual_table(
    *,
    intent: MaterializationIntent,
    manual_scopes: set[tuple[str, str]],
) -> bool:
    if intent.intent_type != MaterializationIntentType.DELETE_BLOCK:
        return False
    return any((scope.kind, scope.ref_id) in manual_scopes for scope in intent.scope_refs)


def _slot_conflicts_with_generated_content(
    *,
    intent: MaterializationIntent,
    generated_scopes: set[tuple[str, str]],
) -> bool:
    if intent.intent_type != MaterializationIntentType.MATERIALIZE_SLOT:
        return False
    return any((scope.kind, scope.ref_id) in generated_scopes for scope in intent.scope_refs)


def _delete_requires_cleanup_safety(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
) -> bool:
    if intent.intent_type != MaterializationIntentType.DELETE_BLOCK:
        return False
    if intent.resolved_spans and all(span.role == "cleanup" for span in intent.resolved_spans):
        return False
    return context.kind != MaterializationContextKind.INSTRUCTION_NOTE.value


def _unsupported(
    *,
    position: int,
    intent: MaterializationIntent,
    reason_code: str,
    message: str,
    missing_requirements: tuple[str, ...],
    payload: JsonObject | None = None,
) -> UnsupportedMaterialization:
    return UnsupportedMaterialization(
        unsupported_ref=f"plan-unsupported-{position:04d}",
        source_judgment_refs=intent.source_judgment_refs,
        scope_refs=intent.scope_refs,
        reason_code=reason_code,
        message=message,
        missing_requirements=missing_requirements,
        payload=payload or {"intent_ref": intent.intent_ref},
    )
