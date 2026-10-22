"""Plan-level validation for shadow materialization intents."""

from __future__ import annotations

from docfit.template.materialization.models import (
    MaterializationContext,
    MaterializationContextKind,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
    ScopeRef,
    UnsupportedMaterialization,
)
from docfit.tools.runtime import JsonObject


def validate_materialization_plan(
    *,
    plan: MaterializationPlan,
) -> tuple[UnsupportedMaterialization, ...]:
    contexts_by_intent_ref = _contexts_by_intent_ref(plan.contexts)
    unsupported: list[UnsupportedMaterialization] = []
    manual_block_ids = _manual_table_block_ids(plan.contexts)
    manual_scopes = {
        (scope.kind, scope.ref_id)
        for context in plan.contexts
        if context.kind == MaterializationContextKind.MANUAL_TABLE_CELL.value
        for scope in context.scope_refs
    }
    generated_units = _generated_content_unit_ids(plan.contexts)
    generated_scopes = {
        (scope.kind, scope.ref_id)
        for context in plan.contexts
        if context.kind == MaterializationContextKind.GENERATED_CONTENT.value
        for scope in context.scope_refs
    }
    body_structure_blocker = _ambiguous_body_structure_candidate_blocker(
        plan,
        contexts_by_intent_ref=contexts_by_intent_ref,
    )
    if body_structure_blocker is not None:
        unsupported.append(body_structure_blocker)
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
        if _slot_conflicts_with_manual_table(
            intent=intent,
            context=context,
            manual_block_ids=manual_block_ids,
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
            context=context,
            manual_block_ids=manual_block_ids,
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
            context=context,
            generated_units=generated_units,
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
                        "Delete intent is not limited to an instruction note and has no "
                        "explicit cleanup_reason."
                    ),
                    missing_requirements=("cleanup_reason",),
                )
            )
        if _style_only_requires_obligation(intent):
            unsupported.append(
                _unsupported(
                    position=position,
                    intent=intent,
                    reason_code="style_obligation_missing",
                    message="Style-only intent is missing explicit style_obligation.",
                    missing_requirements=("style_obligation",),
                )
            )
    return tuple(unsupported)


def _ambiguous_body_structure_candidate_blocker(
    plan: MaterializationPlan,
    *,
    contexts_by_intent_ref: dict[str, MaterializationContext],
) -> UnsupportedMaterialization | None:
    body_intents = [
        intent
        for intent in plan.intents
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
    ]
    if len(body_intents) <= 1:
        return _duplicate_body_structure_member_blocker(body_intents)
    duplicate_blocker = _duplicate_body_structure_member_blocker(body_intents)
    if duplicate_blocker is not None:
        return duplicate_blocker
    structure_refs = {
        structure_ref
        for intent in body_intents
        if (structure_ref := _payload_string(intent.payload.get("structure_ref")))
    }
    if len(structure_refs) != 1:
        return _body_structure_blocker(
            body_intents,
            reason_code="materialization_body_structure_field_group_ambiguous",
            message=(
                "Body-structure intents must all resolve to one Registry body structure "
                "field group. The materializer will not merge independent structure groups."
            ),
            missing_requirements=("single_body_structure_field_group",),
        )
    ordered_groups = _body_intent_order_groups(
        body_intents,
        contexts_by_intent_ref=contexts_by_intent_ref,
    )
    if ordered_groups is None or len(ordered_groups) <= 1:
        return None
    return _body_structure_blocker(
        body_intents,
        reason_code="materialization_body_structure_candidate_ambiguous",
        message=(
            "Body-structure intents span multiple non-contiguous reading-block groups. "
            "The Agent must select one executable representative body structure and "
            "classify alternate tracks or intervening non-body ranges separately."
        ),
        missing_requirements=("single_contiguous_body_structure_candidate",),
        payload={"body_structure_groups": ordered_groups},
    )


def _duplicate_body_structure_member_blocker(
    body_intents: list[MaterializationIntent],
) -> UnsupportedMaterialization | None:
    seen: dict[str, MaterializationIntent] = {}
    duplicate_blocks: list[str] = []
    duplicate_intents: list[MaterializationIntent] = []
    for intent in body_intents:
        for block_id in _body_member_block_ids(intent):
            if block_id not in seen:
                seen[block_id] = intent
                continue
            if block_id not in duplicate_blocks:
                duplicate_blocks.append(block_id)
            original_intent = seen[block_id]
            if original_intent not in duplicate_intents:
                duplicate_intents.append(original_intent)
            if intent not in duplicate_intents:
                duplicate_intents.append(intent)
    if not duplicate_blocks:
        return None
    if not duplicate_intents:
        duplicate_intents = body_intents
    return _body_structure_blocker(
        duplicate_intents,
        reason_code="materialization_body_structure_member_block_ambiguous",
        message=(
            "Each body_structure reading_block can produce only one executable body "
            "member slot. The Agent returned multiple body_structure parts for the "
            "same reading_block; merge the body member into one part or classify "
            "numbering, separators, style notes, and fixed text as non-body parts."
        ),
        missing_requirements=("one_body_structure_member_per_reading_block",),
        payload={"duplicate_reading_block_ids": duplicate_blocks},
    )


def _body_member_block_ids(intent: MaterializationIntent) -> list[str]:
    raw_bindings = intent.payload.get("member_bindings")
    if not isinstance(raw_bindings, list):
        return []
    block_ids: list[str] = []
    for raw_binding in raw_bindings:
        if not isinstance(raw_binding, dict):
            continue
        block_id = raw_binding.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            block_ids.append(block_id.strip())
    return block_ids


def _body_structure_blocker(
    body_intents: list[MaterializationIntent],
    *,
    reason_code: str,
    message: str,
    missing_requirements: tuple[str, ...],
    payload: JsonObject | None = None,
) -> UnsupportedMaterialization:
    scopes: list[ScopeRef] = []
    seen_scopes: set[tuple[str, str]] = set()
    for intent in body_intents:
        for scope in intent.scope_refs:
            key = (scope.kind, scope.ref_id)
            if key in seen_scopes:
                continue
            seen_scopes.add(key)
            scopes.append(scope)
    source_refs = tuple(
        dict.fromkeys(
            ref
            for intent in body_intents
            for ref in intent.source_judgment_refs
        )
    )
    blocker_payload: JsonObject = {
        "intent_refs": [intent.intent_ref for intent in body_intents],
    }
    if payload is not None:
        blocker_payload.update(payload)
    return UnsupportedMaterialization(
        unsupported_ref="plan-unsupported-body-structure-candidate",
        source_judgment_refs=source_refs,
        scope_refs=tuple(scopes),
        reason_code=reason_code,
        message=message,
        missing_requirements=missing_requirements,
        payload=blocker_payload,
    )


def _body_intent_order_groups(
    body_intents: list[MaterializationIntent],
    *,
    contexts_by_intent_ref: dict[str, MaterializationContext],
) -> list[list[str]] | None:
    block_order, blocks_by_order = _body_context_block_order(
        body_intents,
        contexts_by_intent_ref=contexts_by_intent_ref,
    )
    if block_order is None:
        return None
    ordered_blocks: list[tuple[int, str]] = []
    seen_blocks: set[str] = set()
    for intent in body_intents:
        for block_id in _body_member_block_ids(intent):
            if block_id in seen_blocks:
                continue
            order = block_order.get(block_id)
            if order is None:
                return None
            seen_blocks.add(block_id)
            ordered_blocks.append((order, block_id))
    if not ordered_blocks:
        return None

    ordered_blocks.sort(key=lambda item: item[0])
    cleanup_blocks = _body_cleanup_block_ids(body_intents)
    groups: list[list[str]] = []
    previous_order: int | None = None
    for order, block_id in ordered_blocks:
        if previous_order is None or _body_member_orders_are_connected(
            previous_order=previous_order,
            current_order=order,
            blocks_by_order=blocks_by_order,
            cleanup_blocks=cleanup_blocks,
        ):
            if not groups:
                groups.append([])
            groups[-1].append(block_id)
        else:
            groups.append([block_id])
        previous_order = order
    return groups


def _body_context_block_order(
    body_intents: list[MaterializationIntent],
    *,
    contexts_by_intent_ref: dict[str, MaterializationContext],
) -> tuple[dict[str, int] | None, dict[int, set[str]]]:
    block_order: dict[str, int] = {}
    blocks_by_order: dict[int, set[str]] = {}
    for intent in body_intents:
        context = contexts_by_intent_ref.get(intent.intent_ref)
        if context is None:
            return None, {}
        raw_blocks = context.facts.get("reading_blocks")
        if not isinstance(raw_blocks, list):
            return None, {}
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                return None, {}
            order = raw_block.get("order")
            block_id = raw_block.get("block_id")
            if not isinstance(order, int):
                return None, {}
            if not isinstance(block_id, str) or not block_id.strip():
                return None, {}
            normalized_block_id = block_id.strip()
            block_order[normalized_block_id] = order
            blocks_by_order.setdefault(order, set()).add(normalized_block_id)
    return block_order, blocks_by_order


def _body_cleanup_block_ids(
    body_intents: list[MaterializationIntent],
) -> set[str]:
    cleanup_blocks: set[str] = set()
    for intent in body_intents:
        raw_spans = intent.payload.get("resolved_spans")
        if not isinstance(raw_spans, list):
            continue
        for raw_span in raw_spans:
            if not isinstance(raw_span, dict) or raw_span.get("role") != "cleanup":
                continue
            block_id = raw_span.get("reading_block_id")
            if isinstance(block_id, str) and block_id.strip():
                cleanup_blocks.add(block_id.strip())
    return cleanup_blocks


def _body_member_orders_are_connected(
    *,
    previous_order: int,
    current_order: int,
    blocks_by_order: dict[int, set[str]],
    cleanup_blocks: set[str],
) -> bool:
    if current_order == previous_order + 1:
        return True
    if current_order <= previous_order:
        return False
    for gap_order in range(previous_order + 1, current_order):
        gap_blocks = blocks_by_order.get(gap_order, set())
        if not gap_blocks or not gap_blocks <= cleanup_blocks:
            return False
    return True


def _contexts_by_intent_ref(
    contexts: tuple[MaterializationContext, ...],
) -> dict[str, MaterializationContext]:
    result: dict[str, MaterializationContext] = {}
    for context in contexts:
        intent_ref = context.facts.get("intent_ref")
        if isinstance(intent_ref, str) and intent_ref.strip():
            result[intent_ref] = context
    return result


def _manual_table_block_ids(contexts: tuple[MaterializationContext, ...]) -> set[str]:
    block_ids: set[str] = set()
    for context in contexts:
        if context.kind != MaterializationContextKind.MANUAL_TABLE_CELL.value:
            continue
        block_ids.update(_context_reading_block_ids(context))
    return block_ids


def _generated_content_unit_ids(contexts: tuple[MaterializationContext, ...]) -> set[str]:
    unit_ids: set[str] = set()
    for context in contexts:
        if context.kind != MaterializationContextKind.GENERATED_CONTENT.value:
            continue
        unit_ids.update(_context_unit_ids(context))
    return unit_ids


def _slot_conflicts_with_manual_table(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
    manual_block_ids: set[str],
    manual_scopes: set[tuple[str, str]],
) -> bool:
    if intent.intent_type != MaterializationIntentType.MATERIALIZE_SLOT:
        return False
    if any((scope.kind, scope.ref_id) in manual_scopes for scope in intent.scope_refs):
        return True
    return bool(manual_block_ids.intersection(_context_reading_block_ids(context)))


def _cleanup_conflicts_with_manual_table(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
    manual_block_ids: set[str],
    manual_scopes: set[tuple[str, str]],
) -> bool:
    if intent.intent_type != MaterializationIntentType.DELETE_BLOCK:
        return False
    if any((scope.kind, scope.ref_id) in manual_scopes for scope in intent.scope_refs):
        return True
    return bool(manual_block_ids.intersection(_context_reading_block_ids(context)))


def _slot_conflicts_with_generated_content(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
    generated_units: set[str],
    generated_scopes: set[tuple[str, str]],
) -> bool:
    if intent.intent_type != MaterializationIntentType.MATERIALIZE_SLOT:
        return False
    if any((scope.kind, scope.ref_id) in generated_scopes for scope in intent.scope_refs):
        return True
    return bool(generated_units.intersection(_context_unit_ids(context)))


def _delete_requires_cleanup_safety(
    *,
    intent: MaterializationIntent,
    context: MaterializationContext,
) -> bool:
    if intent.intent_type != MaterializationIntentType.DELETE_BLOCK:
        return False
    parts = intent.payload.get("parts")
    if isinstance(parts, list) and all(
        isinstance(part, dict) and part.get("role") == "cleanup" for part in parts
    ):
        return False
    return context.kind != MaterializationContextKind.INSTRUCTION_NOTE.value


def _style_only_requires_obligation(intent: MaterializationIntent) -> bool:
    return False


def _payload_string(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) and value.strip() else ""


def _context_unit_ids(context: MaterializationContext) -> set[str]:
    return {
        unit_id.strip()
        for raw_block in _context_reading_blocks(context)
        if isinstance((unit_id := raw_block.get("unit_id")), str) and unit_id.strip()
    }


def _context_reading_block_ids(context: MaterializationContext) -> set[str]:
    return {
        block_id.strip()
        for raw_block in _context_reading_blocks(context)
        if isinstance((block_id := raw_block.get("block_id")), str) and block_id.strip()
    }


def _context_reading_blocks(context: MaterializationContext) -> list[JsonObject]:
    raw_blocks = context.facts.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return []
    return [raw_block for raw_block in raw_blocks if isinstance(raw_block, dict)]


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
