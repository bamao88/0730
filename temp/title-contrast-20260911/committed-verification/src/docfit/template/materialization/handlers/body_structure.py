"""Body structure materialization handler."""

from __future__ import annotations

from copy import deepcopy
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.models import (
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
)
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def materialize_body_structure(
    *,
    document: ET.Element,
    by_block: dict[str, ET.Element],
    registry: FieldRegistrySnapshot,
    inventory: JsonObject,
    plan: MaterializationPlan,
    removed: set[int],
) -> tuple[list[JsonObject], list[JsonObject], set[str]]:
    body_intents = _body_structure_intents(plan)
    if not body_intents:
        return [], [], set()
    block_order = _reading_block_order(inventory)
    body_intents.sort(
        key=lambda intent: min(
            (
                block_order.get(block_id, 10**9)
                for block_id in _intent_block_ids(intent)
            ),
            default=10**9,
        )
    )
    selected_intents = _selected_body_intents(
        body_intents,
        block_order=block_order,
    )
    if selected_intents is None:
        return [], [], set()
    selected_bindings = [
        binding
        for intent in selected_intents
        for binding in _member_bindings(intent)
    ]
    if len(selected_bindings) != sum(
        _declared_member_count(intent) for intent in selected_intents
    ):
        return [], [], set()
    source_judgment_refs = list(
        dict.fromkeys(
            ref
            for intent in selected_intents
            for ref in intent.source_judgment_refs
        )
    )
    selected_blocks = [binding["block_id"] for binding in selected_bindings]
    members = [binding["member_field_id"] for binding in selected_bindings]
    structure_ref = _selected_structure_ref(selected_intents)
    if structure_ref is None or len(selected_blocks) != len(members):
        return [], [], set()
    anchor_span_ref = selected_bindings[0].get("span_ref")
    if not isinstance(anchor_span_ref, str) or not anchor_span_ref.strip():
        return [], [], set()
    selected_blocks = [block_id for block_id in selected_blocks if block_id in by_block]
    if len(selected_blocks) != len(members) or not _registry_has(registry, structure_ref):
        return [], [], set()
    if any(not _registry_has(registry, field_id) for field_id in members):
        return [], [], set()

    selected_paragraphs = [
        by_block[block_id]
        for block_id in selected_blocks
        if id(by_block[block_id]) not in removed
    ]
    if len(selected_paragraphs) != len(selected_blocks):
        return [], [], set()
    parents = [_paragraph_parent(document, paragraph) for paragraph in selected_paragraphs]
    parent = parents[0]
    if parent is None or any(item is not parent for item in parents):
        return [], [], set()

    body = document.find(f"{W}body")
    if body is None or parent is not body:
        return [], [], set()

    cleanup_bindings = _cleanup_bindings(
        selected_intents,
        excluded_blocks=set(selected_blocks),
    )
    cleanup_targets: list[tuple[str, ET.Element, JsonObject]] = []
    for cleanup_binding in cleanup_bindings:
        block_id = cleanup_binding["block_id"]
        paragraph = by_block.get(block_id)
        if paragraph is None or id(paragraph) in removed:
            continue
        if _paragraph_parent(document, paragraph) is not parent:
            continue
        cleanup_targets.append((block_id, paragraph, cleanup_binding))

    materialized_members: list[JsonObject] = []
    for binding, paragraph, field_id in zip(
        selected_bindings,
        selected_paragraphs,
        members,
        strict=True,
    ):
        block_id = binding["block_id"]
        properties = first_run_properties(paragraph)
        replace_paragraph_content(
            paragraph,
            [
                sdt(
                    field_id=field_id,
                    label=field_label(registry, field_id),
                    slot_ref=binding["slot_ref"],
                    properties=properties,
                )
            ],
        )
        materialized_member: JsonObject = {
            "field_id": field_id,
            "block_id": block_id,
            "slot_ref": binding["slot_ref"],
        }
        source_entry_id = binding.get("source_entry_id")
        if isinstance(source_entry_id, str) and source_entry_id.strip():
            materialized_member["source_entry_id"] = source_entry_id.strip()
        span_ref = binding.get("span_ref")
        if isinstance(span_ref, str) and span_ref.strip():
            materialized_member["span_ref"] = span_ref.strip()
        materialized_members.append(materialized_member)

    first_index = list(parent).index(selected_paragraphs[0])
    moved_paragraphs: list[ET.Element] = []
    for paragraph in selected_paragraphs:
        if paragraph in list(parent):
            parent.remove(paragraph)
            moved_paragraphs.append(paragraph)
    parent.insert(
        first_index,
        structure_sdt(
            group_ref=anchor_span_ref.strip(),
            children=moved_paragraphs,
        ),
    )

    cleanup: list[JsonObject] = []
    for block_id, paragraph, cleanup_binding in cleanup_targets:
        if paragraph not in list(parent):
            continue
        parent.remove(paragraph)
        removed.add(id(paragraph))
        cleanup_item: JsonObject = {
            "block_id": block_id,
            "action": "remove_body_structure_cleanup",
            "judgment_refs": cleanup_binding.get("source_judgment_refs", []),
        }
        span_ref = cleanup_binding.get("span_ref")
        if isinstance(span_ref, str) and span_ref.strip():
            cleanup_item["span_ref"] = span_ref.strip()
        cleanup.append(cleanup_item)

    selected_block_set = set(selected_blocks)
    operation: JsonObject = {
        "action": "materialize_structure",
        "structure_ref": structure_ref,
        "block_id": selected_blocks[0],
        "member_count": len(materialized_members),
        "members": materialized_members,
    }
    anchor_source_entry_id = selected_bindings[0].get("source_entry_id")
    if isinstance(anchor_source_entry_id, str) and anchor_source_entry_id.strip():
        operation["source_entry_id"] = anchor_source_entry_id.strip()
    if isinstance(anchor_span_ref, str) and anchor_span_ref.strip():
        operation["span_ref"] = anchor_span_ref.strip()
    operation["judgment_refs"] = source_judgment_refs
    return [operation], cleanup, selected_block_set


def _body_structure_intents(plan: MaterializationPlan) -> list[MaterializationIntent]:
    return [
        intent
        for intent in plan.intents
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
        and _structure_ref(intent) is not None
        and _member_bindings(intent)
    ]


def _selected_body_intents(
    intents: list[MaterializationIntent],
    *,
    block_order: dict[str, int],
) -> tuple[MaterializationIntent, ...] | None:
    if len(intents) == 1:
        return (intents[0],)
    structure_refs = {_structure_ref(intent) for intent in intents}
    if len(structure_refs) != 1 or None in structure_refs:
        return None
    ranges: list[tuple[int, MaterializationIntent]] = []
    for intent in intents:
        intent_orders: list[int] = []
        for block_id in _intent_block_ids(intent):
            order = block_order.get(block_id)
            if order is not None:
                intent_orders.append(order)
        if not intent_orders:
            return None
        ranges.append((min(intent_orders), intent))
    ranges.sort(key=lambda item: item[0])
    ordered_intents = tuple(intent for _, intent in ranges)
    ordered_blocks = [
        block_id
        for intent in ordered_intents
        for block_id in _intent_block_ids(intent)
    ]
    ordered_indices = [block_order.get(block_id) for block_id in ordered_blocks]
    if any(index is None for index in ordered_indices):
        return None
    normalized_indices = [index for index in ordered_indices if index is not None]
    if normalized_indices != sorted(normalized_indices):
        return None
    if not _body_member_gaps_are_cleanup(
        ordered_intents,
        normalized_indices=normalized_indices,
        block_order=block_order,
    ):
        return None
    return ordered_intents


def _selected_structure_ref(
    intents: tuple[MaterializationIntent, ...],
) -> str | None:
    values = {_structure_ref(intent) for intent in intents}
    return next(iter(values)) if len(values) == 1 else None


def _structure_ref(intent: MaterializationIntent) -> str | None:
    value = intent.payload.get("structure_ref")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _member_bindings(intent: MaterializationIntent) -> list[JsonObject]:
    raw = intent.payload.get("member_bindings")
    if not isinstance(raw, list):
        return []
    bindings: list[JsonObject] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        block_id = item.get("block_id")
        member_field_id = item.get("member_field_id")
        slot_ref = item.get("slot_ref")
        span_ref = item.get("span_ref")
        if (
            isinstance(block_id, str)
            and block_id.strip()
            and isinstance(member_field_id, str)
            and member_field_id.strip()
            and isinstance(slot_ref, str)
            and slot_ref.strip()
            and isinstance(span_ref, str)
            and span_ref.strip()
        ):
            member_field_id = member_field_id.strip()
            span_ref = span_ref.strip()
            slot_ref = slot_ref.strip()
            if slot_ref != f"{span_ref};field_id={member_field_id}":
                continue
            binding: JsonObject = {
                "block_id": block_id.strip(),
                "member_field_id": member_field_id,
                "slot_ref": slot_ref,
                "span_ref": span_ref,
            }
            source_entry_id = item.get("source_entry_id")
            if isinstance(source_entry_id, str) and source_entry_id.strip():
                binding["source_entry_id"] = source_entry_id.strip()
            covered_object_ids = item.get("covered_object_ids")
            if isinstance(covered_object_ids, list):
                binding["covered_object_ids"] = [
                    value.strip()
                    for value in covered_object_ids
                    if isinstance(value, str) and value.strip()
                ]
            bindings.append(binding)
    return bindings


def _declared_member_count(intent: MaterializationIntent) -> int:
    raw_members = intent.payload.get("members")
    return len(raw_members) if isinstance(raw_members, list) else 0


def _cleanup_bindings(
    intents: tuple[MaterializationIntent, ...],
    *,
    excluded_blocks: set[str],
) -> list[JsonObject]:
    bindings: list[JsonObject] = []
    seen_blocks: set[str] = set()
    for intent in intents:
        raw_spans = intent.payload.get("resolved_spans")
        if not isinstance(raw_spans, list):
            continue
        for span in raw_spans:
            if not isinstance(span, dict):
                continue
            if span.get("role") != "cleanup":
                continue
            block_id = _span_block_id(span)
            if block_id is None or block_id in excluded_blocks or block_id in seen_blocks:
                continue
            seen_blocks.add(block_id)
            binding: JsonObject = {
                "block_id": block_id,
                "source_judgment_refs": list(intent.source_judgment_refs),
            }
            span_ref = span.get("span_ref")
            if isinstance(span_ref, str) and span_ref.strip():
                binding["span_ref"] = span_ref.strip()
            bindings.append(binding)
    return bindings


def _body_member_gaps_are_cleanup(
    intents: tuple[MaterializationIntent, ...],
    *,
    normalized_indices: list[int],
    block_order: dict[str, int],
) -> bool:
    if not normalized_indices:
        return False
    cleanup_blocks = {
        binding["block_id"]
        for binding in _cleanup_bindings(intents, excluded_blocks=set())
        if isinstance(binding.get("block_id"), str)
    }
    if not cleanup_blocks:
        return all(
            current == previous + 1
            for previous, current in zip(
                normalized_indices,
                normalized_indices[1:],
                strict=False,
            )
        )
    blocks_by_order: dict[int, set[str]] = {}
    for block_id, order in block_order.items():
        blocks_by_order.setdefault(order, set()).add(block_id)
    for previous, current in zip(
        normalized_indices,
        normalized_indices[1:],
        strict=False,
    ):
        for gap_order in range(previous + 1, current):
            gap_blocks = blocks_by_order.get(gap_order, set())
            if not gap_blocks or not gap_blocks <= cleanup_blocks:
                return False
    return True


def _span_block_id(span: JsonObject) -> str | None:
    source_entry_id = span.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        return source_entry_id.strip()
    block_id = span.get("reading_block_id")
    if isinstance(block_id, str) and block_id.strip():
        return block_id.strip()
    scope = span.get("scope")
    if isinstance(scope, dict):
        scope_block = scope.get("reading_block_id")
        if isinstance(scope_block, str) and scope_block.strip():
            return scope_block.strip()
    return None


def _intent_block_ids(intent: MaterializationIntent) -> list[str]:
    return [binding["block_id"] for binding in _member_bindings(intent)]


def _reading_block_order(inventory: JsonObject) -> dict[str, int]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return {}
    result: dict[str, int] = {}
    for index, block in enumerate(raw_blocks):
        if not isinstance(block, dict):
            continue
        block_id = block.get("block_id")
        if isinstance(block_id, str):
            order = block.get("order")
            result[block_id] = order if isinstance(order, int) else index + 1
    raw_source_entries = inventory.get("source_entries")
    if isinstance(raw_source_entries, list):
        for index, entry in enumerate(raw_source_entries):
            if not isinstance(entry, dict):
                continue
            source_entry_id = entry.get("source_entry_id")
            if not isinstance(source_entry_id, str) or not source_entry_id.strip():
                continue
            source_order = entry.get("source_order")
            source_block_order = (
                source_order.get("block")
                if isinstance(source_order, dict)
                else None
            )
            result[source_entry_id.strip()] = (
                source_block_order
                if isinstance(source_block_order, int)
                and not isinstance(source_block_order, bool)
                else index + 1
            )
    return result


def _paragraph_parent(document: ET.Element, paragraph: ET.Element) -> ET.Element | None:
    return next((item for item in document.iter() if paragraph in list(item)), None)


def _registry_has(registry: FieldRegistrySnapshot, field_id: str) -> bool:
    try:
        registry.lookup(field_id)
    except ToolFailure:
        return False
    return True


def field_label(registry: FieldRegistrySnapshot, field_id: str) -> str:
    field = registry.lookup(field_id)
    label = field.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else field_id


def first_run_properties(paragraph: ET.Element) -> ET.Element | None:
    first_run = paragraph.find(f"{W}r")
    properties = first_run.find(f"{W}rPr") if first_run is not None else None
    return deepcopy(properties) if properties is not None else None


def run(text: str, properties: ET.Element | None = None) -> ET.Element:
    element = ET.Element(f"{W}r")
    if properties is not None:
        element.append(deepcopy(properties))
    node = ET.SubElement(element, f"{W}t")
    node.set(XML_SPACE, "preserve")
    node.text = text
    return element


def sdt(
    *,
    field_id: str,
    label: str,
    slot_ref: str,
    properties: ET.Element | None,
) -> ET.Element:
    control = ET.Element(f"{W}sdt")
    sdt_pr = ET.SubElement(control, f"{W}sdtPr")
    ET.SubElement(sdt_pr, f"{W}alias", {f"{W}val": field_id})
    ET.SubElement(sdt_pr, f"{W}tag", {f"{W}val": slot_ref})
    internal_id = int(sha256_json({"slot_ref": slot_ref})[:7], 16)
    ET.SubElement(sdt_pr, f"{W}id", {f"{W}val": str(internal_id)})
    ET.SubElement(sdt_pr, f"{W}text")
    content = ET.SubElement(control, f"{W}sdtContent")
    content.append(run(f"【{label}】", properties))
    return control


def structure_sdt(
    *,
    group_ref: str,
    children: list[ET.Element],
) -> ET.Element:
    control = ET.Element(f"{W}sdt")
    sdt_pr = ET.SubElement(control, f"{W}sdtPr")
    internal_id = int(sha256_json({"body_structure_group_ref": group_ref})[:7], 16)
    ET.SubElement(sdt_pr, f"{W}id", {f"{W}val": str(internal_id)})
    content = ET.SubElement(control, f"{W}sdtContent")
    content.extend(children)
    return control


def replace_paragraph_content(paragraph: ET.Element, children: list[ET.Element]) -> None:
    properties = paragraph.find(f"{W}pPr")
    for child in list(paragraph):
        paragraph.remove(child)
    if properties is not None:
        paragraph.append(properties)
    paragraph.extend(children)
