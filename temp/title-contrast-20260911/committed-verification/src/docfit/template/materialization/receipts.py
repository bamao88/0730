"""Receipt builders for post-unit template materialization."""

from __future__ import annotations

from collections.abc import Iterable

from docfit.template.materialization.models import MaterializationPlan
from docfit.tools.runtime import JsonObject


def build_materialization_receipts(
    *,
    plan: MaterializationPlan,
    operations: list[JsonObject],
    cleanup: list[JsonObject],
    policy_receipts: list[JsonObject],
    before_text_by_block: dict[str, str],
    after_text_by_block: dict[str, str],
) -> list[JsonObject]:
    intent_index = _IntentReceiptIndex.from_plan(plan)
    receipts: list[JsonObject] = []
    receipts.extend(
        _operation_receipt(
            operation=operation,
            intent_index=intent_index,
            before_text_by_block=before_text_by_block,
            after_text_by_block=after_text_by_block,
        )
        for operation in operations
    )
    receipts.extend(
        _cleanup_receipt(
            cleanup_item=item,
            intent_index=intent_index,
            before_text_by_block=before_text_by_block,
            after_text_by_block=after_text_by_block,
        )
        for item in cleanup
    )
    receipts.extend(_policy_receipt(item) for item in policy_receipts)
    return receipts


class _IntentReceiptIndex:
    def __init__(
        self,
        *,
        intent_refs_by_judgment_ref: dict[str, list[str]],
        scope_refs_by_judgment_ref: dict[str, list[JsonObject]],
    ) -> None:
        self.intent_refs_by_judgment_ref = intent_refs_by_judgment_ref
        self.scope_refs_by_judgment_ref = scope_refs_by_judgment_ref

    @classmethod
    def from_plan(cls, plan: MaterializationPlan) -> _IntentReceiptIndex:
        intent_refs_by_judgment_ref: dict[str, list[str]] = {}
        scope_refs_by_judgment_ref: dict[str, list[JsonObject]] = {}
        for intent in plan.intents:
            for judgment_ref in intent.source_judgment_refs:
                intent_refs_by_judgment_ref.setdefault(judgment_ref, []).append(
                    intent.intent_ref
                )
                scope_refs_by_judgment_ref.setdefault(judgment_ref, []).extend(
                    scope.to_json() for scope in intent.scope_refs
                )
        return cls(
            intent_refs_by_judgment_ref=intent_refs_by_judgment_ref,
            scope_refs_by_judgment_ref=scope_refs_by_judgment_ref,
        )

    def intent_refs(self, judgment_refs: list[str]) -> list[str]:
        return _dedupe(
            intent_ref
            for judgment_ref in judgment_refs
            for intent_ref in self.intent_refs_by_judgment_ref.get(judgment_ref, [])
        )

    def scope_refs(self, judgment_refs: list[str]) -> list[JsonObject]:
        return _dedupe_json(
            scope
            for judgment_ref in judgment_refs
            for scope in self.scope_refs_by_judgment_ref.get(judgment_ref, [])
        )


def _operation_receipt(
    *,
    operation: JsonObject,
    intent_index: _IntentReceiptIndex,
    before_text_by_block: dict[str, str],
    after_text_by_block: dict[str, str],
) -> JsonObject:
    judgment_refs = _string_list(operation.get("judgment_refs"))
    affected_blocks = _operation_blocks(operation)
    action = _operation_action(operation)
    return {
        "receipt_type": "mutation",
        "action": action,
        "handler": _handler_for_operation(action),
        "intent_refs": intent_index.intent_refs(judgment_refs),
        "source_judgment_refs": judgment_refs,
        "scope_refs": intent_index.scope_refs(judgment_refs),
        "field_ids": _operation_field_ids(operation),
        "span_refs": _operation_ref_values(operation, "span_ref"),
        "slot_refs": _operation_ref_values(operation, "slot_ref"),
        "affected_blocks": affected_blocks,
        "before_text_by_block": _texts_for_blocks(before_text_by_block, affected_blocks),
        "after_text_by_block": _texts_for_blocks(after_text_by_block, affected_blocks),
        "operation": dict(operation),
    }


def _cleanup_receipt(
    *,
    cleanup_item: JsonObject,
    intent_index: _IntentReceiptIndex,
    before_text_by_block: dict[str, str],
    after_text_by_block: dict[str, str],
) -> JsonObject:
    judgment_refs = _string_list(cleanup_item.get("judgment_refs"))
    block_id = cleanup_item.get("block_id")
    affected_blocks = [block_id] if isinstance(block_id, str) and block_id.strip() else []
    action = cleanup_item.get("action")
    action = action if isinstance(action, str) and action.strip() else "cleanup"
    return {
        "receipt_type": "mutation",
        "action": action,
        "handler": _handler_for_cleanup(action),
        "intent_refs": intent_index.intent_refs(judgment_refs),
        "source_judgment_refs": judgment_refs,
        "scope_refs": intent_index.scope_refs(judgment_refs),
        "field_ids": [],
        "affected_blocks": affected_blocks,
        "before_text_by_block": _texts_for_blocks(before_text_by_block, affected_blocks),
        "after_text_by_block": _texts_for_blocks(after_text_by_block, affected_blocks),
        "safety_checks": _cleanup_safety_checks(action),
        "operation": dict(cleanup_item),
    }


def _policy_receipt(policy: JsonObject) -> JsonObject:
    result = dict(policy)
    result.setdefault("receipt_type", "policy")
    return result


def _operation_blocks(operation: JsonObject) -> list[str]:
    block_ids: list[str] = []
    block_id = operation.get("block_id")
    if isinstance(block_id, str) and block_id.strip():
        block_ids.append(block_id.strip())
    members = operation.get("members")
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict):
                continue
            member_block_id = member.get("block_id")
            if isinstance(member_block_id, str) and member_block_id.strip():
                block_ids.append(member_block_id.strip())
    return _dedupe(block_ids)


def _operation_action(operation: JsonObject) -> str:
    action = operation.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip()
    if isinstance(operation.get("field_id"), str):
        return "materialize_slot"
    return "materialize"


def _handler_for_operation(action: str) -> str:
    if action == "materialize_structure":
        return "body_structure"
    if action == "materialize_slot":
        return "slots"
    return "unknown"


def _handler_for_cleanup(action: str) -> str:
    if action == "remove_body_structure_cleanup":
        return "body_structure"
    if action == "remove_hint":
        return "slots"
    if action == "strip_instruction_text":
        return "fixed_content"
    return "cleanup"


def _cleanup_safety_checks(action: str) -> list[str]:
    if action == "remove_body_structure_cleanup":
        return ["accepted_cleanup_part_in_body_structure_range"]
    if action in {"clear_text", "remove_paragraph", "strip_instruction_text"}:
        return ["plan_validator_checked_cleanup_scope"]
    if action == "remove_hint":
        return ["slot_handler_checked_hint_without_field"]
    return []


def _operation_field_ids(operation: JsonObject) -> list[str]:
    field_ids: list[str] = []
    field_id = operation.get("field_id")
    if isinstance(field_id, str) and field_id.strip():
        field_ids.append(field_id.strip())
    members = operation.get("members")
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict):
                continue
            member_field_id = member.get("field_id")
            if isinstance(member_field_id, str) and member_field_id.strip():
                field_ids.append(member_field_id.strip())
    return _dedupe(field_ids)


def _operation_ref_values(operation: JsonObject, key: str) -> list[str]:
    values: list[str] = []
    value = operation.get(key)
    if isinstance(value, str) and value.strip():
        values.append(value.strip())
    members = operation.get("members")
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict):
                continue
            member_value = member.get(key)
            if isinstance(member_value, str) and member_value.strip():
                values.append(member_value.strip())
    return _dedupe(values)


def _texts_for_blocks(text_by_block: dict[str, str], block_ids: list[str]) -> JsonObject:
    return {block_id: text_by_block.get(block_id, "") for block_id in block_ids}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_json(values: Iterable[JsonObject]) -> list[JsonObject]:
    result: list[JsonObject] = []
    seen: set[tuple[tuple[str, object], ...]] = set()
    for value in values:
        identity = tuple(sorted(value.items()))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(dict(value))
    return result
