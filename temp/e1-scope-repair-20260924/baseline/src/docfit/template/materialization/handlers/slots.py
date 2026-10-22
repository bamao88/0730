"""Field slot materialization handler."""

from __future__ import annotations

from copy import deepcopy
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.field_binding import (
    explicit_field_ids_from_source,
    semantic_part_is_slot,
)
from docfit.template.materialization.paragraph_rewrite import (
    replace_paragraph_content as replace_paragraph_content,
)
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
type IndexedSemanticPart = tuple[int, JsonObject]

CENTERED_TITLE_SLOT_LAYOUT = "centered_title"


def materialize_slot_paragraph(
    *,
    paragraph: ET.Element,
    block_id: str,
    registry: FieldRegistrySnapshot,
    indexed_ordered_parts: list[IndexedSemanticPart],
    resolved_spans: list[JsonObject],
    compact_placeholders: bool = False,
) -> list[JsonObject]:
    properties = first_run_properties(paragraph)
    return materialize_slot_paragraph_parts(
        paragraph=paragraph,
        block_id=block_id,
        indexed_ordered_parts=indexed_ordered_parts,
        resolved_spans=resolved_spans,
        registry=registry,
        properties=properties,
        compact_placeholders=compact_placeholders,
    )


def materialize_slot_paragraph_parts(
    *,
    paragraph: ET.Element,
    block_id: str,
    indexed_ordered_parts: list[IndexedSemanticPart],
    resolved_spans: list[JsonObject],
    registry: FieldRegistrySnapshot,
    properties: ET.Element | None,
    compact_placeholders: bool = False,
) -> list[JsonObject]:
    children: list[ET.Element] = []
    operations: list[JsonObject] = []
    materialized_field_ids: list[str] = []
    spans_by_part = _spans_by_part_index(resolved_spans)
    ordered_parts = [part for _part_index, part in indexed_ordered_parts]
    has_visible_fixed_label = any(
        part.get("role") == "fixed_label"
        and isinstance(part.get("text"), str)
        and bool(part["text"].strip())
        for part in ordered_parts
    )
    properties_by_part = _run_properties_by_ordered_part(
        paragraph,
        ordered_parts,
        default_properties=properties,
    )
    for local_part_index, (part_index, part) in enumerate(indexed_ordered_parts):
        _reject_retired_semantic_part_index(part)
        text = part.get("text")
        part_text = text if isinstance(text, str) else ""
        part_properties = properties_by_part.get(local_part_index, properties)
        if semantic_part_is_slot(part):
            part_field_ids = explicit_field_ids_from_source(part)
            if not part_field_ids:
                raise _slot_ref_missing(part_index=part_index)
            for field_id in part_field_ids:
                span = _span_for_part(
                    spans_by_part=spans_by_part,
                    part_index=part_index,
                    field_id=field_id,
                )
                children.append(
                    sdt(
                        field_id=field_id,
                        label=field_label(registry, field_id),
                        slot_ref=str(span["slot_ref"]),
                        properties=part_properties,
                        compact_placeholder=(
                            (has_visible_fixed_label or compact_placeholders)
                            and not _uses_centered_title_slot_layout(registry, field_id)
                        ),
                    )
                )
                operations.append(
                    {
                        "action": "materialize_slot",
                        "field_id": field_id,
                        "block_id": block_id,
                        "part_index": part_index,
                        "span_ref": span["span_ref"],
                        "slot_ref": span["slot_ref"],
                        **_source_entry_operation_fields(span),
                    }
                )
                materialized_field_ids.append(field_id)
            continue
        if part_should_delete(part):
            continue
        if part_text:
            children.append(run(part_text, part_properties))
    replace_paragraph_content(paragraph, children)
    if any(
        _uses_centered_title_slot_layout(registry, field_id)
        for field_id in materialized_field_ids
    ):
        normalize_centered_title_slot_layout(paragraph)
    return operations


def _slot_ref_missing(*, part_index: int) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="postcondition",
        code="materialization_slot_ref_missing",
        message=(
            "fill_slot materialization requires a Harness-resolved slot_ref for "
            f"ordered part {part_index}."
        ),
    )


def _spans_by_part_index(resolved_spans: list[JsonObject]) -> dict[int, list[JsonObject]]:
    spans: dict[int, list[JsonObject]] = {}
    for span in resolved_spans:
        part_index = span.get("part_index")
        if isinstance(part_index, int) and not isinstance(part_index, bool):
            spans.setdefault(part_index, []).append(span)
    return spans


def _reject_retired_semantic_part_index(part: JsonObject) -> None:
    if "semantic_part_index" not in part:
        return
    raise ToolFailure(
        status="needs_input",
        origin="postcondition",
        code="materialization_legacy_semantic_part_index",
        message=(
            "Slot materialization consumes ordered parts by explicit original index; "
            "semantic_part_index is not an accepted input field."
        ),
    )


def _span_for_part(
    *,
    spans_by_part: dict[int, list[JsonObject]],
    part_index: int,
    field_id: str,
) -> JsonObject:
    for span in spans_by_part.get(part_index, []):
        span_ref = span.get("span_ref")
        slot_ref = span.get("slot_ref")
        if (
            span.get("field_id") == field_id
            and isinstance(span_ref, str)
            and span_ref.strip()
            and slot_ref == f"{span_ref};field_id={field_id}"
        ):
            return span
    raise _slot_ref_missing(part_index=part_index)


def _source_entry_operation_fields(span: JsonObject) -> JsonObject:
    source_entry_id = span.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        return {"source_entry_id": source_entry_id.strip()}
    raw_spans = span.get("source_entry_spans")
    if not isinstance(raw_spans, list):
        return {}
    source_entry_ids = [
        item["source_entry_id"].strip()
        for item in raw_spans
        if isinstance(item, dict)
        and isinstance(item.get("source_entry_id"), str)
        and item["source_entry_id"].strip()
    ]
    unique = list(dict.fromkeys(source_entry_ids))
    if len(unique) == 1:
        return {"source_entry_id": unique[0]}
    if unique:
        return {"source_entry_ids": unique}
    return {}


def part_should_delete(part: JsonObject) -> bool:
    role = part.get("role")
    return role.strip() in {"cleanup", "style_only"} if isinstance(role, str) else False


def field_label(registry: FieldRegistrySnapshot, field_id: str) -> str:
    field = registry.lookup(field_id)
    label = field.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else field_id


def _uses_centered_title_slot_layout(
    registry: FieldRegistrySnapshot, field_id: str
) -> bool:
    field = registry.lookup(field_id)
    materialization = field.get("materialization")
    if not isinstance(materialization, dict):
        return False
    return materialization.get("slot_layout") == CENTERED_TITLE_SLOT_LAYOUT


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{W}t"))


def first_run_properties(paragraph: ET.Element) -> ET.Element | None:
    first_run = paragraph.find(f"{W}r")
    properties = first_run.find(f"{W}rPr") if first_run is not None else None
    return deepcopy(properties) if properties is not None else None


def _run_properties_by_ordered_part(
    paragraph: ET.Element,
    ordered_parts: list[JsonObject],
    *,
    default_properties: ET.Element | None,
) -> dict[int, ET.Element | None]:
    runs = [
        (run_element, "".join(node.text or "" for node in run_element.iter(f"{W}t")))
        for run_element in paragraph.findall(f"{W}r")
    ]
    result: dict[int, ET.Element | None] = {}
    run_index = 0
    offset = 0
    for part_index, part in enumerate(ordered_parts):
        text = part.get("text")
        remaining = len(text) if isinstance(text, str) else 0
        selected: ET.Element | None = None
        while remaining > 0 and run_index < len(runs):
            run_element, run_text = runs[run_index]
            available = len(run_text) - offset
            if available <= 0:
                run_index += 1
                offset = 0
                continue
            if selected is None:
                selected = run_element.find(f"{W}rPr")
            consumed = min(remaining, available)
            remaining -= consumed
            offset += consumed
            if offset >= len(run_text):
                run_index += 1
                offset = 0
        result[part_index] = deepcopy(selected) if selected is not None else default_properties
    return result


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
    compact_placeholder: bool = False,
) -> ET.Element:
    control = ET.Element(f"{W}sdt")
    sdt_pr = ET.SubElement(control, f"{W}sdtPr")
    ET.SubElement(sdt_pr, f"{W}alias", {f"{W}val": field_id})
    ET.SubElement(sdt_pr, f"{W}tag", {f"{W}val": slot_ref})
    internal_id = int(sha256_json({"slot_ref": slot_ref})[:7], 16)
    ET.SubElement(sdt_pr, f"{W}id", {f"{W}val": str(internal_id)})
    ET.SubElement(sdt_pr, f"{W}text")
    content = ET.SubElement(control, f"{W}sdtContent")
    # A surrounding fixed label already tells the reader what an inline field
    # means. Repeating the full Registry label can be much wider than the
    # school's sample value and can push a cover row onto another page. Keep a
    # visible, renderer-independent marker while the SDT alias/tag and Fill
    # Contract retain the exact field identity.
    placeholder = "【填】" if compact_placeholder else f"【{label}】"
    content.append(run(placeholder, properties))
    return control


def normalize_centered_title_slot_layout(paragraph: ET.Element) -> None:
    properties = paragraph.find(f"{W}pPr")
    if properties is None:
        properties = ET.Element(f"{W}pPr")
        paragraph.insert(0, properties)
    for child in list(properties):
        if child.tag in {f"{W}ind", f"{W}jc"}:
            properties.remove(child)
    alignment = ET.Element(f"{W}jc", {f"{W}val": "center"})
    run_properties = properties.find(f"{W}rPr")
    if run_properties is None:
        properties.append(alignment)
    else:
        properties.insert(list(properties).index(run_properties), alignment)
