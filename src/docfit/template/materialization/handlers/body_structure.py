"""Body structure materialization handler."""

from __future__ import annotations

from copy import deepcopy
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.body_interfaces import body_interfaces
from docfit.template.materialization.models import (
    AcceptedResolvedSpan,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
)
from docfit.template.materialization.paragraph_rewrite import (
    replace_paragraph_content as replace_paragraph_content,
)
from docfit.template.materialization.text_edits import TextEdits
from docfit.template.unit_source import source_unit_cut_points, validate_inventory_partition
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
    editor: TextEdits | None = None,
) -> tuple[list[JsonObject], list[JsonObject], set[str]]:
    body_intents = _body_structure_intents(plan)
    if not body_intents:
        return [], [], set()
    cut_points = (
        source_unit_cut_points(validate_inventory_partition(inventory))
        if "canonical_source_inventory" in inventory else None
    )
    selected_intents = _selected_body_intents(body_intents)
    if selected_intents is None:
        return [], [], set()
    selected_bindings = [
        binding
        for intent in selected_intents
        for binding in _member_bindings(intent, cut_points=cut_points)
    ]
    source_judgment_refs = list(
        dict.fromkeys(
            ref
            for intent in selected_intents
            for ref in intent.source_judgment_refs
        )
    )
    selected_blocks = [binding["block_id"] for binding in selected_bindings]
    members = [binding["member_field_id"] for binding in selected_bindings]
    structure_ref = _common_structure_ref(registry, members)
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

    if any(id(by_block[block_id]) in removed for block_id in selected_blocks):
        return [], [], set()
    grouped_bindings: list[tuple[ET.Element, list[JsonObject]]] = []
    for binding in selected_bindings:
        element = by_block[binding["block_id"]]
        if grouped_bindings and grouped_bindings[-1][0] is element:
            grouped_bindings[-1][1].append(binding)
        else:
            grouped_bindings.append((element, [binding]))
    if len({id(element) for element, _ in grouped_bindings}) != len(grouped_bindings):
        return [], [], set()
    selected_elements = [element for element, _ in grouped_bindings]
    parents = [_element_parent(document, element) for element in selected_elements]
    parent = parents[0]
    if parent is None or any(item is not parent for item in parents):
        return [], [], set()

    body = document.find(f"{W}body")
    if body is None or (parent is not body and parent.tag != W + "tc"):
        return [], [], set()

    cleanup_bindings = _cleanup_bindings(
        selected_intents,
        excluded_blocks=set(selected_blocks),
    )
    cleanup_targets: list[tuple[str, ET.Element, JsonObject]] = []
    for cleanup_binding in cleanup_bindings:
        block_id = cleanup_binding["block_id"]
        cleanup_element = by_block.get(block_id)
        if cleanup_element is None or id(cleanup_element) in removed:
            continue
        if _element_parent(document, cleanup_element) is not parent:
            continue
        cleanup_targets.append((block_id, cleanup_element, cleanup_binding))

    cleanup: list[JsonObject] = []
    for block_id, element, cleanup_binding in cleanup_targets:
        if element not in list(parent):
            continue
        parent.remove(element)
        removed.add(id(element))
        cleanup_item: JsonObject = {
            "block_id": block_id,
            "action": "remove_body_structure_cleanup",
            "judgment_refs": cleanup_binding.get("source_judgment_refs", []),
        }
        span_ref = cleanup_binding.get("span_ref")
        if isinstance(span_ref, str) and span_ref.strip():
            cleanup_item["span_ref"] = span_ref.strip()
        cleanup.append(cleanup_item)

    body_order = {id(element): index for index, element in enumerate(parent)}
    if any(id(element) not in body_order for element in selected_elements):
        return [], [], set()
    grouped_bindings.sort(key=lambda item: body_order[id(item[0])])
    selected_elements = [element for element, _ in grouped_bindings]
    selected_bindings = [
        binding for _, bindings in grouped_bindings for binding in bindings
    ]
    selected_blocks = [binding["block_id"] for binding in selected_bindings]
    members = [binding["member_field_id"] for binding in selected_bindings]
    anchor_span_ref = selected_bindings[0]["span_ref"]

    materialized_members: list[JsonObject] = []
    transformed_elements: dict[int, ET.Element] = {}
    intents_by_source_entry = {
        span.source_entry_id: intent
        for intent in selected_intents
        for span in intent.resolved_spans
        if span.role == "body_structure"
    }
    for element, element_bindings in grouped_bindings:
        if element.tag == f"{W}p":
            properties = first_run_properties(element)
            source_entry_ids = {
                binding.get("source_entry_id") for binding in element_bindings
            }
            if len(source_entry_ids) != 1:
                return [], [], set()
            source_entry_id = next(iter(source_entry_ids))
            if not isinstance(source_entry_id, str):
                return [], [], set()
            intent = intents_by_source_entry.get(source_entry_id)
            if intent is None:
                return [], [], set()
            children = _inline_composite_children(
                intent=intent, bindings=element_bindings,
                registry=registry, properties=properties,
            )
            if children is None:
                return [], [], set()
            if editor is None:
                replace_paragraph_content(element, children)
            else:
                bindings_by_part = {binding["part_index"]: binding for binding in element_bindings}
                for span in intent.resolved_spans:
                    part_binding = bindings_by_part.get(span.part_index)
                    if part_binding is not None:
                        editor.replace(span.to_json(), [sdt(
                            field_id=part_binding["member_field_id"],
                            label=field_label(registry, part_binding["member_field_id"]),
                            slot_ref=part_binding["slot_ref"],
                            properties=editor.properties(span.span_ref),
                        )])
                    elif span.role in {"body_structure", "cleanup", "style_only"} and span.text:
                        editor.replace(span.to_json(), [])
            transformed_elements[id(element)] = element
        elif element.tag == f"{W}tbl":
            if len(element_bindings) != 1:
                return [], [], set()
            binding = element_bindings[0]
            field_id = binding["member_field_id"]
            if binding.get("top_level_table") is not True:
                return [], [], set()
            transformed_elements[id(element)] = block_sdt(
                field_id=field_id,
                slot_ref=binding["slot_ref"],
                child=element,
            )
        else:
            return [], [], set()
        for binding in element_bindings:
            materialized_member: JsonObject = {
                "field_id": binding["member_field_id"],
                "block_id": binding["block_id"],
                "slot_ref": binding["slot_ref"],
            }
            source_entry_id = binding.get("source_entry_id")
            if isinstance(source_entry_id, str) and source_entry_id.strip():
                materialized_member["source_entry_id"] = source_entry_id.strip()
            span_ref = binding.get("span_ref")
            if isinstance(span_ref, str) and span_ref.strip():
                materialized_member["span_ref"] = span_ref.strip()
            if "coalescence" in binding:
                materialized_member["coalescence"] = binding["coalescence"]
            materialized_members.append(materialized_member)

    parent_children = list(parent)
    first_index = parent_children.index(selected_elements[0])
    last_index = parent_children.index(selected_elements[-1])
    range_children = parent_children[first_index : last_index + 1]
    moved_children = [
        transformed_elements.get(id(element), element) for element in range_children
    ]
    if parent is body:
        for element in range_children:
            parent.remove(element)
        for offset, element in enumerate(
            structure_range_children(
                group_ref=anchor_span_ref.strip(),
                children=moved_children,
            )
        ):
            parent.insert(first_index + offset, element)
    # Cell-local text interfaces remain inside their original paragraphs. Do not
    # move cells, replace the enclosing table or remove its trailing paragraph.

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
        and _member_bindings(intent)
    ]


def _selected_body_intents(
    intents: list[MaterializationIntent],
) -> tuple[MaterializationIntent, ...] | None:
    # Compiler order is the accepted ordered-span order.  Re-sorting against a
    # reading view would re-introduce a second target-selection protocol.
    return tuple(intents)


def _common_structure_ref(
    registry: FieldRegistrySnapshot,
    member_field_ids: list[str],
) -> str | None:
    ancestor_chains = [_registry_parent_chain(registry, field_id) for field_id in member_field_ids]
    if not ancestor_chains or any(not chain for chain in ancestor_chains):
        return None
    return next(
        (
            ancestor
            for ancestor in ancestor_chains[0]
            if all(ancestor in chain for chain in ancestor_chains[1:])
        ),
        None,
    )


def _registry_parent_chain(
    registry: FieldRegistrySnapshot,
    field_id: str,
) -> list[str]:
    chain: list[str] = []
    seen = {field_id}
    current = field_id
    while True:
        parent = registry.lookup(current).get("parent_field_id")
        if not isinstance(parent, str) or not parent.strip():
            return chain
        current = parent.strip()
        if current in seen or not _registry_has(registry, current):
            return []
        seen.add(current)
        chain.append(current)


def _member_bindings(
    intent: MaterializationIntent, *, cut_points: dict[str, set[int]] | None = None,
) -> list[JsonObject]:
    spans_by_ref = {span.span_ref: span for span in intent.resolved_spans}
    bindings: list[JsonObject] = []
    for accepted in intent.field_bindings:
        span = spans_by_ref.get(accepted.span_ref)
        if accepted.role != "body_structure" or span is None:
            continue
        bindings.append(
            {
                "block_id": span.source_entry_id,
                "member_field_id": accepted.field_id,
                "slot_ref": accepted.slot_ref,
                "span_ref": accepted.span_ref,
                "source_entry_id": span.source_entry_id,
                "top_level_table": _span_is_top_level_table(span),
                "part_index": accepted.part_index,
            }
        )
    if cut_points is not None:
        by_ref = {binding["span_ref"]: binding for binding in bindings}
        grouped: list[JsonObject] = []
        for group in body_interfaces(intent.resolved_spans, cut_points=cut_points):
            binding = dict(by_ref[group.anchor.span_ref])
            if (coalescence := group.coalescence()) is not None:
                binding["coalescence"] = coalescence
            grouped.append(binding)
        return grouped
    return bindings


def _inline_composite_children(
    *,
    intent: MaterializationIntent,
    bindings: list[JsonObject],
    registry: FieldRegistrySnapshot,
    properties: ET.Element | None,
) -> list[ET.Element] | None:
    bindings_by_part = {binding.get("part_index"): binding for binding in bindings}
    if len(bindings_by_part) != len(bindings):
        return None
    coalesced_parts = {
        span["part_index"] for binding in bindings
        for span in binding.get("coalescence", {}).get("source_spans", [])[1:]
    }
    children: list[ET.Element] = []
    for span in sorted(intent.resolved_spans, key=lambda item: item.part_index):
        binding = bindings_by_part.get(span.part_index)
        if binding is not None:
            children.append(
                sdt(
                    field_id=binding["member_field_id"],
                    label=field_label(registry, binding["member_field_id"]),
                    slot_ref=binding["slot_ref"],
                    properties=properties,
                )
            )
        elif span.part_index in coalesced_parts:
            continue
        elif span.role not in {"style_only", "cleanup"} and span.text:
            children.append(run(span.text, properties))
    return children if len(bindings_by_part) == len(bindings) else None


def _span_is_top_level_table(span: AcceptedResolvedSpan) -> bool:
    if not span.word_fragments:
        return False
    for fragment in span.word_fragments:
        locator = fragment.get("locator")
        if not isinstance(locator, str):
            return False
        segments = [segment for segment in locator.split("/") if segment]
        if len(segments) != 2 or segments[0] != "body" or not segments[1].startswith(
            "tbl["
        ):
            return False
    return True


def _cleanup_bindings(
    intents: tuple[MaterializationIntent, ...],
    *,
    excluded_blocks: set[str],
) -> list[JsonObject]:
    bindings: list[JsonObject] = []
    seen_blocks: set[str] = set()
    for intent in intents:
        for span in intent.resolved_spans:
            if span.role != "cleanup":
                continue
            block_id = _span_block_id(span)
            if block_id is None or block_id in excluded_blocks or block_id in seen_blocks:
                continue
            seen_blocks.add(block_id)
            binding: JsonObject = {
                "block_id": block_id,
                "source_judgment_refs": list(intent.source_judgment_refs),
            }
            binding["span_ref"] = span.span_ref
            bindings.append(binding)
    return bindings


def _span_block_id(span: AcceptedResolvedSpan) -> str | None:
    return span.source_entry_id


def _element_parent(document: ET.Element, element: ET.Element) -> ET.Element | None:
    return next((item for item in document.iter() if element in list(item)), None)


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


def block_sdt(*, field_id: str, slot_ref: str, child: ET.Element) -> ET.Element:
    control = ET.Element(f"{W}sdt")
    sdt_pr = ET.SubElement(control, f"{W}sdtPr")
    ET.SubElement(sdt_pr, f"{W}alias", {f"{W}val": field_id})
    ET.SubElement(sdt_pr, f"{W}tag", {f"{W}val": slot_ref})
    internal_id = int(sha256_json({"slot_ref": slot_ref})[:7], 16)
    ET.SubElement(sdt_pr, f"{W}id", {f"{W}val": str(internal_id)})
    content = ET.SubElement(control, f"{W}sdtContent")
    content.append(child)
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


def structure_range_children(
    *,
    group_ref: str,
    children: list[ET.Element],
) -> list[ET.Element]:
    """Keep section-break paragraphs at body level while grouping structure members."""
    result: list[ET.Element] = []
    pending: list[ET.Element] = []
    group_index = 0

    def flush_pending() -> None:
        nonlocal group_index
        if not pending:
            return
        chunk_ref = group_ref if group_index == 0 else f"{group_ref};chunk={group_index}"
        result.append(structure_sdt(group_ref=chunk_ref, children=list(pending)))
        pending.clear()
        group_index += 1

    for child in children:
        section_properties = (
            child.find(f"{W}pPr/{W}sectPr") if child.tag == f"{W}p" else None
        )
        if section_properties is None:
            pending.append(child)
            continue
        flush_pending()
        result.append(child)
    flush_pending()
    return result
