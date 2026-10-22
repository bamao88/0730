"""Plan-level validation for shadow materialization intents."""

from __future__ import annotations

from docfit.template.materialization.handlers.cleanup import cleanup_kind, cleanup_object_locator
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
        if (intent.intent_type == MaterializationIntentType.DELETE_BLOCK
            and cleanup_kind(intent) == "unsupported"):
            unsupported.append(_unsupported(
                position=position, intent=intent,
                reason_code="materialization_cleanup_target_unsupported",
                message="Accepted cleanup has no supported exact object or text range.",
                missing_requirements=("exact_cleanup_target",),
            ))
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
                    reason_code="materialization_semantic_scope_conflict",
                    message=(
                        "The selected content is assigned incompatible purposes: removal "
                        "overlaps content to retain or fill, or filling ranges overlap. "
                        "Revise the related source entries so each affected range has "
                        "one consistent purpose. Removing a whole container also removes "
                        "its contents."
                    ),
                    missing_requirements=("consistent_source_scope_purposes",),
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


def _cleanup_conflicts_by_carrier(
    intents: tuple[MaterializationIntent, ...],
) -> dict[str, tuple[MaterializationIntent, ...]]:
    """Compare accepted object subtrees and text intervals, never paragraph guesses."""
    conflicts: dict[str, list[MaterializationIntent]] = {}

    def record(key: str, left: MaterializationIntent, right: MaterializationIntent) -> None:
        group = conflicts.setdefault(key, [])
        for item in (left, right):
            if item not in group:
                group.append(item)

    for deletion in intents:
        if deletion.intent_type != MaterializationIntentType.DELETE_BLOCK:
            continue
        carrier = cleanup_object_locator(deletion)
        if carrier is None:
            continue
        for other in intents:
            if other.intent_type == MaterializationIntentType.DELETE_BLOCK:
                continue
            for span in other.resolved_spans:
                if span.role == "cleanup" and span.text:
                    continue
                for fragment in span.word_fragments:
                    locator = str(fragment["locator"])
                    whole = fragment.get("extent") == {"kind": "whole_entry"}
                    picture = whole and locator.rsplit("/", 1)[-1].startswith("r[")
                    selected = locator + "/drawing[1]" if picture else locator
                    below = selected == carrier or selected.startswith(carrier + "/")
                    # Manual/fixed whole objects retain contents. Layout and
                    # body-table interfaces retain shells, allowing child cleanup.
                    contains = (whole and span.role in {"fixed_label", "manual_region"}
                                and carrier.startswith(selected + "/"))
                    if below or contains:
                        record(carrier, deletion, other)
    text_fragments = [
        (intent, span, fragment)
        for intent in intents for span in intent.resolved_spans for fragment in span.word_fragments
        if isinstance(fragment.get("object_text_start"), int)
    ]
    mutations = {"cleanup", "style_only", "fill_slot", "body_structure"}
    deletions = {"cleanup", "style_only"}
    for intent in intents:
        for span in intent.resolved_spans:
            if span.role not in {"fixed_label", "manual_region"}:
                continue
            for fragment in span.word_fragments:
                if fragment.get("extent") != {"kind": "whole_entry"}:
                    continue
                locator = str(fragment["locator"])
                if locator.rsplit("/", 1)[-1].startswith("r["):
                    locator += "/drawing[1]"
                for other, changed_span, changed in text_fragments:
                    if (other is not intent and changed_span.role in mutations
                        and (changed["locator"] == locator
                             or changed["locator"].startswith(locator + "/"))):
                        record(locator, intent, other)
    for index, (left, left_span, a) in enumerate(text_fragments):
        for right, right_span, b in text_fragments[index + 1:]:
            if left is right or a["locator"] != b["locator"]:
                continue
            if not ({left_span.role, right_span.role} & mutations):
                continue
            if {left_span.role, right_span.role} <= deletions:
                continue
            if max(a["object_text_start"], b["object_text_start"]) < min(
                a["object_text_end"], b["object_text_end"]
            ):
                record(str(a["locator"]), left, right)
    order = {intent.intent_ref: index for index, intent in enumerate(intents)}
    return {carrier: tuple(sorted(group, key=lambda intent: order[intent.intent_ref]))
            for carrier, group in conflicts.items()}


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
