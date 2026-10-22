"""Context resolution for typed materialization intents."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from docfit.template.materialization.models import (
    MaterializationContext,
    MaterializationContextKind,
    MaterializationContextResolution,
    MaterializationIntent,
    MaterializationIntentType,
    ScopeRef,
    UnsupportedMaterialization,
)
from docfit.tools.runtime import JsonObject, sha256_json


def resolve_materialization_contexts(
    *,
    inventory: JsonObject,
    intents: tuple[MaterializationIntent, ...],
) -> MaterializationContextResolution:
    index = _InventoryIndex.from_inventory(inventory)
    contexts: list[MaterializationContext] = []
    unsupported: list[UnsupportedMaterialization] = []
    for position, intent in enumerate(intents, start=1):
        blocks = index.blocks_for_scope_refs(intent.scope_refs)
        if not blocks:
            unsupported.append(
                UnsupportedMaterialization(
                    unsupported_ref=f"context-unsupported-{position:04d}",
                    source_judgment_refs=intent.source_judgment_refs,
                    scope_refs=intent.scope_refs,
                    reason_code="materialization_context_scope_unresolved",
                    message=(
                        "Intent scope did not resolve to any reading block in the current "
                        "object inventory."
                    ),
                    missing_requirements=("resolvable_reading_scope",),
                )
            )
            continue
        kind = _context_kind(intent, blocks)
        contexts.append(
            MaterializationContext(
                context_ref=_context_ref(position, intent.intent_ref),
                kind=kind.value,
                scope_refs=intent.scope_refs,
                facts={
                    **index.context_facts(blocks),
                    "intent_ref": intent.intent_ref,
                    "intent_type": intent.intent_type.value,
                },
            )
        )
    return MaterializationContextResolution(
        contexts=tuple(contexts),
        unsupported=tuple(unsupported),
    )


@dataclass(frozen=True)
class _InventoryIndex:
    blocks_by_id: dict[str, JsonObject]
    blocks_by_range_id: dict[str, tuple[JsonObject, ...]]
    blocks_by_unit_id: dict[str, tuple[JsonObject, ...]]
    source_entries_by_id: dict[str, JsonObject]
    object_types_by_id: dict[str, str]

    @classmethod
    def from_inventory(cls, inventory: JsonObject) -> _InventoryIndex:
        blocks_by_id: dict[str, JsonObject] = {}
        by_range: dict[str, list[JsonObject]] = {}
        by_unit: dict[str, list[JsonObject]] = {}
        raw_blocks = inventory.get("reading_blocks")
        if isinstance(raw_blocks, list):
            for index, raw_block in enumerate(raw_blocks):
                if not isinstance(raw_block, dict):
                    continue
                block_id = _string(raw_block.get("block_id"))
                if block_id is None:
                    continue
                block = dict(raw_block)
                if not isinstance(block.get("order"), int):
                    block["order"] = index + 1
                blocks_by_id[block_id] = block
                for range_id in _range_ids_for_block(block):
                    by_range.setdefault(range_id, []).append(block)
                unit_id = _string(block.get("unit_id"))
                if unit_id is not None:
                    by_unit.setdefault(unit_id, []).append(block)

        object_types: dict[str, str] = {}
        objects_by_id: dict[str, JsonObject] = {}
        raw_objects = inventory.get("objects")
        if isinstance(raw_objects, list):
            for raw_object in raw_objects:
                if not isinstance(raw_object, dict):
                    continue
                object_id = _string(raw_object.get("object_id"))
                object_type = _string(raw_object.get("type"))
                if object_id is not None and object_type is not None:
                    object_types[object_id] = object_type
                if object_id is not None:
                    objects_by_id[object_id] = dict(raw_object)

        source_entries_by_id: dict[str, JsonObject] = {}
        raw_source_entries = inventory.get("source_entries")
        if isinstance(raw_source_entries, list):
            for index, raw_entry in enumerate(raw_source_entries):
                if not isinstance(raw_entry, dict):
                    continue
                source_entry_id = _string(raw_entry.get("source_entry_id"))
                text = raw_entry.get("text")
                if source_entry_id is None or not isinstance(text, str):
                    continue
                source_entries_by_id[source_entry_id] = _source_entry_scope_block(
                    raw_entry,
                    index=index,
                    objects_by_id=objects_by_id,
                )

        return cls(
            blocks_by_id=blocks_by_id,
            blocks_by_range_id={key: tuple(value) for key, value in by_range.items()},
            blocks_by_unit_id={key: tuple(value) for key, value in by_unit.items()},
            source_entries_by_id=source_entries_by_id,
            object_types_by_id=object_types,
        )

    def blocks_for_scope_refs(self, scope_refs: tuple[ScopeRef, ...]) -> tuple[JsonObject, ...]:
        blocks: list[JsonObject] = []
        seen: set[str] = set()
        for scope in scope_refs:
            for block in self._blocks_for_scope_ref(scope):
                block_id = _string(block.get("block_id"))
                if block_id is None or block_id in seen:
                    continue
                seen.add(block_id)
                blocks.append(block)
        return tuple(blocks)

    def context_facts(self, blocks: tuple[JsonObject, ...]) -> JsonObject:
        block_summaries: list[JsonObject] = []
        object_type_counter: Counter[str] = Counter()
        for block in blocks:
            block_summaries.append(_block_summary(block))
            raw_object_ids = block.get("covered_object_ids")
            if not isinstance(raw_object_ids, list):
                continue
            for object_id in raw_object_ids:
                if not isinstance(object_id, str):
                    continue
                object_type = self.object_types_by_id.get(object_id)
                if object_type is not None:
                    object_type_counter[object_type] += 1
        facts: JsonObject = {"reading_blocks": block_summaries}
        source_entry_summaries = [
            _source_entry_summary(block)
            for block in blocks
            if isinstance(block.get("source_entry_id"), str)
        ]
        if source_entry_summaries:
            facts["source_entries"] = source_entry_summaries
        if object_type_counter:
            facts["object_type_counts"] = dict(sorted(object_type_counter.items()))
        return facts

    def _blocks_for_scope_ref(self, scope: ScopeRef) -> tuple[JsonObject, ...]:
        if scope.kind == "reading_block":
            block = self.blocks_by_id.get(scope.ref_id)
            return (block,) if block is not None else ()
        if scope.kind == "reading_range":
            return self.blocks_by_range_id.get(scope.ref_id, ())
        if scope.kind == "unit":
            return self.blocks_by_unit_id.get(scope.ref_id, ())
        if scope.kind == "source_entry":
            entry = self.source_entries_by_id.get(scope.ref_id)
            return (entry,) if entry is not None else ()
        return ()


def _source_entry_scope_block(
    entry: JsonObject,
    *,
    index: int,
    objects_by_id: dict[str, JsonObject],
) -> JsonObject:
    source_entry_id = _string(entry.get("source_entry_id"))
    text = entry.get("text")
    block: JsonObject = {
        "block_id": source_entry_id or f"source-entry-missing-{index + 1:04d}",
        "source_entry_id": source_entry_id,
        "text": text if isinstance(text, str) else "",
        "covered_object_ids": _source_entry_object_ids(entry),
    }
    entry_type = _string(entry.get("entry_type"))
    if entry_type is not None:
        block["entry_type"] = entry_type
    source_order = entry.get("source_order")
    if isinstance(source_order, dict):
        block["source_order"] = dict(source_order)
        order = source_order.get("block")
        if isinstance(order, int) and not isinstance(order, bool):
            block["order"] = order
    unit_id = _source_entry_unit_id(entry, objects_by_id=objects_by_id)
    if unit_id is not None:
        block["unit_id"] = unit_id
    return block


def _source_entry_object_ids(entry: JsonObject) -> list[str]:
    raw_provenance = entry.get("provenance")
    if not isinstance(raw_provenance, list):
        return []
    object_ids: list[str] = []
    for item in raw_provenance:
        if not isinstance(item, dict):
            continue
        object_id = _string(item.get("object_id"))
        if object_id is not None:
            object_ids.append(object_id)
    return list(dict.fromkeys(object_ids))


def _source_entry_unit_id(
    entry: JsonObject,
    *,
    objects_by_id: dict[str, JsonObject],
) -> str | None:
    for object_id in _source_entry_object_ids(entry):
        item = objects_by_id.get(object_id)
        if item is None:
            continue
        unit_id = _string(item.get("unit_id"))
        if unit_id is not None:
            return unit_id
    return None


def _context_kind(
    intent: MaterializationIntent,
    blocks: tuple[JsonObject, ...],
) -> MaterializationContextKind:
    if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE:
        return MaterializationContextKind.BODY_STRUCTURE
    if intent.intent_type == MaterializationIntentType.KEEP_MANUAL_TABLE_CELL:
        return MaterializationContextKind.MANUAL_TABLE_CELL
    if intent.intent_type == MaterializationIntentType.REFRESH_GENERATED_CONTENT:
        return MaterializationContextKind.GENERATED_CONTENT
    if intent.intent_type == MaterializationIntentType.TRANSFER_STYLE_ONLY:
        return MaterializationContextKind.STYLE_ONLY
    if intent.intent_type == MaterializationIntentType.DELETE_BLOCK:
        return _delete_context_kind(intent)
    if intent.intent_type == MaterializationIntentType.KEEP_FIXED_CONTENT:
        return _fixed_context_kind(blocks)
    if intent.intent_type == MaterializationIntentType.MATERIALIZE_SLOT:
        return _slot_context_kind(blocks)
    if intent.intent_type == MaterializationIntentType.NO_OP:
        return MaterializationContextKind.UNIT_SCOPE
    return MaterializationContextKind.UNKNOWN


def _delete_context_kind(intent: MaterializationIntent) -> MaterializationContextKind:
    text = _payload_text(intent)
    if "note" in text or "instruction" in text or "format_hint" in text:
        return MaterializationContextKind.INSTRUCTION_NOTE
    return MaterializationContextKind.CLEANUP_BLOCK


def _fixed_context_kind(blocks: tuple[JsonObject, ...]) -> MaterializationContextKind:
    visible_text = "\n".join(_block_text(block) for block in blocks)
    stripped = visible_text.strip()
    title_text = _strip_parenthetical_suffix(stripped)
    if (
        title_text in {"参考文献", "致□□谢", "致谢", "附录"}
        or ("□" in title_text and not title_text.startswith("□") and len(title_text) <= 12)
    ):
        return MaterializationContextKind.FIXED_HEADING
    return MaterializationContextKind.FIXED_CONTENT


def _slot_context_kind(blocks: tuple[JsonObject, ...]) -> MaterializationContextKind:
    visible_text = "\n".join(_block_text(block) for block in blocks).strip()
    if visible_text.startswith("□"):
        return MaterializationContextKind.PARAGRAPH_INDENT
    if "×" in visible_text or "……" in visible_text:
        return MaterializationContextKind.SAMPLE_VALUE
    return MaterializationContextKind.FIELD_SLOT


def _payload_text(intent: MaterializationIntent) -> str:
    values = [
        value.casefold()
        for value in intent.payload.values()
        if isinstance(value, str) and value.strip()
    ]
    return " ".join(values)


def _block_summary(block: JsonObject) -> JsonObject:
    summary: JsonObject = {}
    for key in ("block_id", "range_id", "unit_range_id", "unit_id", "source_entry_id"):
        value = _string(block.get(key))
        if value is not None:
            summary[key] = value
    order = block.get("order")
    if isinstance(order, int):
        summary["order"] = order
    text = _block_text(block)
    if text:
        summary["text"] = text[:500]
    return summary


def _source_entry_summary(block: JsonObject) -> JsonObject:
    summary: JsonObject = {}
    for key in ("source_entry_id", "entry_type"):
        value = _string(block.get(key))
        if value is not None:
            summary[key] = value
    source_order = block.get("source_order")
    if isinstance(source_order, dict):
        summary["source_order"] = dict(source_order)
    text = _block_text(block)
    if text:
        summary["text"] = text[:500]
    return summary


def _context_ref(position: int, intent_ref: str) -> str:
    return f"context-{position:04d}-{sha256_json({'intent_ref': intent_ref})[:8]}"


def _strip_parenthetical_suffix(text: str) -> str:
    for marker in ("（", "("):
        index = text.find(marker)
        if index > 0:
            return text[:index].strip()
    return text


def _block_text(block: JsonObject) -> str:
    value = block.get("text")
    return value.strip() if isinstance(value, str) else ""


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _range_ids_for_block(block: JsonObject) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value
            for key in ("range_id", "unit_range_id")
            if (value := _string(block.get(key))) is not None
        )
    )
