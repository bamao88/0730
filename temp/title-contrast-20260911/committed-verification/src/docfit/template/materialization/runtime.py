"""Deterministic post-unit template materialization runtime.

This compiler consumes Harness-accepted semantic judgments and rewrites the
school template into a first usable fillable DOCX.  It deliberately does not
ask the Agent to choose OOXML spans: the Agent decides school semantics; this
module owns the mechanical Word mutation.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.executor import write_materialized_docx
from docfit.template.materialization.field_binding import (
    explicit_field_ids_from_source,
    ordered_parts,
    semantic_part_is_slot,
)
from docfit.template.materialization.handlers.body_structure import materialize_body_structure
from docfit.template.materialization.handlers.cleanup import (
    is_delete_treatment,
    should_remove_paragraph,
)
from docfit.template.materialization.handlers.fixed_content import apply_fixed_content_cleanup
from docfit.template.materialization.handlers.generated_content import (
    generated_content_policy_receipts,
)
from docfit.template.materialization.handlers.slots import (
    IndexedSemanticPart,
    materialize_slot_paragraph,
    part_should_delete,
)
from docfit.template.materialization.handlers.table_manual_cells import (
    manual_table_cell_policy_receipts,
)
from docfit.template.materialization.models import (
    MaterializationIntentType,
    MaterializationPlan,
)
from docfit.template.materialization.plan import build_shadow_materialization_plan
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.materialization.receipts import build_materialization_receipts
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
_W = f"{{{W_NS}}}"
_W14 = f"{{{W14_NS}}}"
_LOCATOR_SEGMENT = re.compile(r"^(?P<name>[A-Za-z]+)(?:\[(?P<selector>.+)])?$")
_LOCATOR_ATTRIBUTE = re.compile(r"^@(?P<name>[A-Za-z0-9]+)=(?P<value>.+)$")

_KNOWN_NAMESPACES = {
    "w": W_NS,
    "mc": MC_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w14": W14_NS,
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}

for prefix, uri in _KNOWN_NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def _paragraphs(document: ET.Element) -> list[ET.Element]:
    body = document.find(f"{_W}body")
    if body is None:
        return []
    return list(body.iter(f"{_W}p"))


def _paragraph_parent(document: ET.Element, paragraph: ET.Element) -> ET.Element | None:
    return next((item for item in document.iter() if paragraph in list(item)), None)


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{_W}t"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _attribute_value(element: ET.Element, name: str) -> str | None:
    return next(
        (
            value
            for key, value in element.attrib.items()
            if _local_name(key).casefold() == name.casefold()
        ),
        None,
    )


def _children_named(parent: ET.Element, name: str) -> list[ET.Element]:
    candidates = [child for child in list(parent) if _local_name(child.tag) == name]
    if candidates or _local_name(parent.tag) != "sdt":
        return candidates
    content = parent.find(f"{_W}sdtContent")
    if content is None:
        return []
    return [child for child in list(content) if _local_name(child.tag) == name]


def _segment_child(parent: ET.Element, segment: str) -> ET.Element | None:
    if segment == "body":
        values = [child for child in list(parent) if _local_name(child.tag) == "body"]
        return values[0] if len(values) == 1 else None
    match = _LOCATOR_SEGMENT.fullmatch(segment)
    if match is None:
        return None
    name = match.group("name")
    candidates = _children_named(parent, name)
    selector = match.group("selector")
    if selector is None:
        return candidates[0] if len(candidates) == 1 else None
    if selector.isdigit():
        index = int(selector) - 1
        return candidates[index] if 0 <= index < len(candidates) else None
    attribute = _LOCATOR_ATTRIBUTE.fullmatch(selector)
    if attribute is None:
        return None
    attribute_name = attribute.group("name")
    attribute_value = attribute.group("value")
    for child in candidates:
        if _attribute_value(child, attribute_name) == attribute_value:
            return child
        if name == "sdt" and attribute_name.casefold() == "sdtid":
            identifier = child.find(f"{_W}sdtPr/{_W}id")
            if (
                identifier is not None
                and _attribute_value(identifier, "val") == attribute_value
            ):
                return child
    return None


def _resolve_locator(document: ET.Element, locator: str) -> ET.Element | None:
    current = document
    for segment in (value for value in locator.split("/") if value):
        child = _segment_child(current, segment)
        if child is None:
            return None
        current = child
    return current


def _parent_map(document: ET.Element) -> dict[int, ET.Element]:
    return {id(child): parent for parent in document.iter() for child in list(parent)}


def _ancestor_paragraph(
    target: ET.Element,
    parents: dict[int, ET.Element],
) -> ET.Element | None:
    current: ET.Element | None = target
    while current is not None:
        if current.tag == f"{_W}p":
            return current
        current = parents.get(id(current))
    return None


def _reading_block_texts(inventory: JsonObject) -> dict[str, str]:
    result: dict[str, str] = {}
    for block in inventory.get("reading_blocks", []):
        if not isinstance(block, dict) or not isinstance(block.get("block_id"), str):
            continue
        for key in ("text", "visible_text", "text_preview"):
            value = block.get(key)
            if isinstance(value, str):
                result[str(block["block_id"])] = value
                break
    for entry in _source_entries(inventory):
        source_entry_id = _string(entry.get("source_entry_id"))
        text = entry.get("text")
        if source_entry_id is not None and isinstance(text, str):
            result[source_entry_id] = text
    return result


def _paragraph_para_id(paragraph: ET.Element) -> str | None:
    value = paragraph.get(f"{_W14}paraId")
    return value if isinstance(value, str) and value.strip() else None


def _para_id_from_locator(locator: str) -> str | None:
    marker = "@paraId="
    if marker not in locator:
        return None
    tail = locator.split(marker, 1)[1]
    quote = tail[0] if tail and tail[0] in {"'", '"'} else None
    if quote is not None:
        return tail[1:].split(quote, 1)[0]
    match = re.match(r"([A-Za-z0-9]+)", tail)
    return match.group(1) if match else None


def _paragraph_by_block(
    *,
    document: ET.Element,
    inventory: JsonObject,
) -> dict[str, ET.Element]:
    paragraphs = _paragraphs(document)
    parents = _parent_map(document)
    by_para_id = {
        para_id: paragraph
        for paragraph in paragraphs
        if (para_id := _paragraph_para_id(paragraph)) is not None
    }
    objects_by_id = {
        str(item["object_id"]): item
        for item in inventory.get("objects", [])
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }
    result: dict[str, ET.Element] = {}
    reading_blocks = [
        item
        for item in inventory.get("reading_blocks", [])
        if isinstance(item, dict) and isinstance(item.get("block_id"), str)
    ]
    for block in reading_blocks:
        paragraph: ET.Element | None = None
        raw_ids = block.get("covered_object_ids", [])
        if isinstance(raw_ids, list):
            for raw_id in raw_ids:
                if not isinstance(raw_id, str):
                    continue
                obj = objects_by_id.get(raw_id)
                locator = obj.get("locator") if isinstance(obj, dict) else None
                if not isinstance(locator, str):
                    continue
                target = _resolve_locator(document, locator)
                if target is not None:
                    paragraph = _ancestor_paragraph(target, parents)
                    if paragraph is not None:
                        break
                para_id = _para_id_from_locator(locator)
                if para_id is not None and para_id in by_para_id:
                    paragraph = by_para_id[para_id]
                    break
        if paragraph is not None:
            result[str(block["block_id"])] = paragraph
    result.update(
        {
            source_entry_id: paragraph
            for source_entry_id, paragraph in _paragraph_by_source_entry(
                document=document,
                inventory=inventory,
            ).items()
            if source_entry_id not in result
        }
    )
    return result


def _objects_by_id(inventory: JsonObject) -> dict[str, JsonObject]:
    return {
        str(item["object_id"]): item
        for item in inventory.get("objects", [])
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }


def _expected_document_hash(*, inventory: JsonObject, review: JsonObject) -> str | None:
    inventory_hash = _string(inventory.get("document_sha256"))
    review_hash = _string(review.get("document_sha256"))
    if inventory_hash is not None and review_hash is not None and inventory_hash != review_hash:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_ref",
            message=(
                "Materialization inventory and semantic review belong to different "
                "source document snapshots."
            ),
            retryable=True,
            suggested_actions=("Refresh inventory and semantic judgments for the same source.",),
        )
    return inventory_hash or review_hash


def _ensure_source_document_hash_current(
    *,
    source_docx: Path,
    inventory: JsonObject,
    review: JsonObject,
) -> str:
    current_hash = sha256_file(source_docx)
    expected_hash = _expected_document_hash(inventory=inventory, review=review)
    if expected_hash is not None and expected_hash != current_hash:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_ref",
            message=(
                "Materialization source DOCX has changed since the source-entry "
                "inventory and semantic review were accepted."
            ),
            retryable=True,
            suggested_actions=(
                "Refresh source inventory, reading packet, and semantic judgments.",
            ),
        )
    return current_hash


def _ensure_source_entry_provenance_fresh(
    *,
    document: ET.Element,
    inventory: JsonObject,
    current_document_sha256: str,
) -> None:
    entries = _source_entries(inventory)
    if not entries:
        return
    objects_by_id = _objects_by_id(inventory)
    for entry in entries:
        source_entry_id = _string(entry.get("source_entry_id")) or "unknown"
        provenance_items = _source_entry_provenance(entry)
        if not provenance_items:
            raise _source_entry_provenance_failure(
                code="source_entry_provenance_missing",
                source_entry_id=source_entry_id,
                message="Canonical source entry has no executable provenance.",
            )
        for provenance in provenance_items:
            _ensure_provenance_item_fresh(
                document=document,
                source_entry_id=source_entry_id,
                provenance=provenance,
                objects_by_id=objects_by_id,
                current_document_sha256=current_document_sha256,
            )


def _ensure_provenance_item_fresh(
    *,
    document: ET.Element,
    source_entry_id: str,
    provenance: JsonObject,
    objects_by_id: dict[str, JsonObject],
    current_document_sha256: str,
) -> None:
    object_id = _string(provenance.get("object_id"))
    if object_id is None:
        raise _source_entry_provenance_failure(
            code="source_entry_provenance_missing_object",
            source_entry_id=source_entry_id,
            message="Source entry provenance is missing object_id.",
        )
    obj = objects_by_id.get(object_id)
    if obj is None:
        raise _source_entry_provenance_failure(
            code="source_entry_provenance_object_unknown",
            source_entry_id=source_entry_id,
            object_id=object_id,
            message="Source entry provenance points to an object outside inventory.",
        )
    locator = _string(provenance.get("locator"))
    object_locator = _string(obj.get("locator"))
    if locator is None:
        locator = object_locator
    if locator is None:
        raise _source_entry_provenance_failure(
            code="source_entry_provenance_locator_missing",
            source_entry_id=source_entry_id,
            object_id=object_id,
            message="Source entry provenance has no raw object locator.",
        )
    if object_locator is not None and object_locator != locator:
        raise _source_entry_provenance_failure(
            code="source_entry_provenance_locator_mismatch",
            source_entry_id=source_entry_id,
            object_id=object_id,
            message="Source entry provenance locator does not match the inventory object.",
        )
    _ensure_object_ref_current(
        source_entry_id=source_entry_id,
        object_id=object_id,
        obj=obj,
        provenance=provenance,
        current_document_sha256=current_document_sha256,
    )
    if _resolve_locator(document, locator) is None:
        raise _source_entry_provenance_failure(
            code="stale_object_ref",
            source_entry_id=source_entry_id,
            object_id=object_id,
            message="Source entry raw object locator no longer resolves in the DOCX.",
        )


def _ensure_object_ref_current(
    *,
    source_entry_id: str,
    object_id: str,
    obj: JsonObject,
    provenance: JsonObject,
    current_document_sha256: str,
) -> None:
    object_ref = obj.get("object_ref")
    provenance_ref = provenance.get("object_ref")
    refs = [
        ref
        for ref in (object_ref, provenance_ref)
        if isinstance(ref, dict)
    ]
    for ref in refs:
        ref_hash = _string(ref.get("document_sha256"))
        if ref_hash is not None and ref_hash != current_document_sha256:
            raise _source_entry_provenance_failure(
                code="stale_ref",
                source_entry_id=source_entry_id,
                object_id=object_id,
                message="Source entry raw object_ref belongs to a stale DOCX snapshot.",
            )
        ref_object_id = _string(ref.get("object_id"))
        if ref_object_id is not None and ref_object_id != object_id:
            raise _source_entry_provenance_failure(
                code="source_entry_provenance_object_mismatch",
                source_entry_id=source_entry_id,
                object_id=object_id,
                message="Source entry raw object_ref object_id does not match provenance.",
            )
    expected_fingerprints = [
        fingerprint
        for fingerprint in (
            _string(provenance.get("fingerprint")),
            *(
                _string(ref.get("expected_fingerprint"))
                for ref in refs
            ),
        )
        if fingerprint is not None
    ]
    if len(set(expected_fingerprints)) > 1:
        raise _source_entry_provenance_failure(
            code="object_fingerprint_mismatch",
            source_entry_id=source_entry_id,
            object_id=object_id,
            message="Source entry provenance fingerprint disagrees with inventory object_ref.",
        )


def _source_entry_provenance_failure(
    *,
    code: str,
    source_entry_id: str,
    message: str,
    object_id: str | None = None,
) -> ToolFailure:
    payload = f"source_entry_id={source_entry_id}"
    if object_id is not None:
        payload += f", object_id={object_id}"
    return ToolFailure(
        status="needs_input",
        origin="harness",
        code=code,
        message=message,
        retryable=True,
        suggested_actions=(
            "Refresh source-entry inventory before deterministic materialization.",
            payload,
        ),
    )


def _source_entries(inventory: JsonObject) -> list[JsonObject]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return []
    return [entry for entry in raw_entries if isinstance(entry, dict)]


def _source_entry_provenance(entry: JsonObject) -> list[JsonObject]:
    raw_provenance = entry.get("provenance")
    if not isinstance(raw_provenance, list):
        return []
    return [item for item in raw_provenance if isinstance(item, dict)]


def _source_entry_object_ids(entry: JsonObject) -> list[str]:
    object_ids: list[str] = []
    for item in _source_entry_provenance(entry):
        object_id = _string(item.get("object_id"))
        if object_id is not None:
            object_ids.append(object_id)
    return list(dict.fromkeys(object_ids))


def _paragraph_by_source_entry(
    *,
    document: ET.Element,
    inventory: JsonObject,
) -> dict[str, ET.Element]:
    parents = _parent_map(document)
    objects_by_id = _objects_by_id(inventory)
    result: dict[str, ET.Element] = {}
    for entry in _source_entries(inventory):
        source_entry_id = _string(entry.get("source_entry_id"))
        if source_entry_id is None:
            continue
        paragraphs: list[ET.Element] = []
        seen: set[int] = set()
        for provenance in _source_entry_provenance(entry):
            object_id = _string(provenance.get("object_id"))
            obj = objects_by_id.get(object_id) if object_id is not None else None
            locator = _string(provenance.get("locator"))
            if locator is None and obj is not None:
                locator = _string(obj.get("locator"))
            if locator is None:
                continue
            target = _resolve_locator(document, locator)
            if target is None:
                continue
            paragraph = _ancestor_paragraph(target, parents)
            if paragraph is not None and id(paragraph) not in seen:
                seen.add(id(paragraph))
                paragraphs.append(paragraph)
        if len(paragraphs) == 1:
            result[source_entry_id] = paragraphs[0]
    return result


def _elements_by_object_id(
    *,
    document: ET.Element,
    inventory: JsonObject,
) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for object_id, obj in _objects_by_id(inventory).items():
        locator = obj.get("locator")
        if not isinstance(locator, str):
            continue
        target = _resolve_locator(document, locator)
        if target is not None:
            result[object_id] = target
    return result


def _sdt_by_block(
    *,
    document: ET.Element,
    inventory: JsonObject,
) -> dict[str, ET.Element]:
    objects_by_id = _objects_by_id(inventory)
    elements_by_id = _elements_by_object_id(document=document, inventory=inventory)
    result: dict[str, ET.Element] = {}
    for block in inventory.get("reading_blocks", []):
        if not isinstance(block, dict) or not isinstance(block.get("block_id"), str):
            continue
        raw_ids = block.get("covered_object_ids")
        if not isinstance(raw_ids, list):
            continue
        for raw_id in raw_ids:
            if not isinstance(raw_id, str):
                continue
            obj = objects_by_id.get(raw_id)
            if obj is None or obj.get("type") != "sdt":
                continue
            target = elements_by_id.get(raw_id)
            if target is not None and _local_name(target.tag) == "sdt":
                result[str(block["block_id"])] = target
                break
    for entry in _source_entries(inventory):
        source_entry_id = _string(entry.get("source_entry_id"))
        if source_entry_id is None:
            continue
        for object_id in _source_entry_object_ids(entry):
            obj = objects_by_id.get(object_id)
            if obj is None or obj.get("type") != "sdt":
                continue
            target = elements_by_id.get(object_id)
            if target is not None and _local_name(target.tag) == "sdt":
                result[source_entry_id] = target
                break
    return result


def _clear_paragraph_text(paragraph: ET.Element) -> None:
    for node in paragraph.iter(f"{_W}t"):
        node.text = None


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


def _span_for_slot_part(
    *,
    resolved_spans: list[JsonObject],
    part_index: int,
    field_id: str,
) -> JsonObject:
    for span in resolved_spans:
        if span.get("part_index") != part_index:
            continue
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


def _field_content_type(registry: FieldRegistrySnapshot, field_id: str) -> str:
    field = registry.lookup(field_id)
    content_type = field.get("content_type")
    if isinstance(content_type, str) and content_type.strip():
        return content_type.strip()
    return "text"


def _set_sdt_property(
    properties: ET.Element,
    name: str,
    *,
    value: str | None = None,
) -> None:
    selected = properties.find(f"{_W}{name}")
    if selected is None:
        selected = ET.SubElement(properties, f"{_W}{name}")
    if value is not None:
        selected.set(f"{_W}val", value)


def _adopt_existing_sdt(
    control: ET.Element,
    *,
    field_id: str,
    slot_ref: str,
    content_type: str,
) -> None:
    properties = control.find(f"{_W}sdtPr")
    if properties is None:
        properties = ET.Element(f"{_W}sdtPr")
        control.insert(0, properties)
    _set_sdt_property(properties, "alias", value=field_id)
    _set_sdt_property(properties, "tag", value=slot_ref)
    _set_sdt_property(
        properties,
        "id",
        value=str(int(sha256_json({"slot_ref": slot_ref})[:7], 16)),
    )
    if content_type not in {"rich_text", "section"}:
        _set_sdt_property(properties, "text")


def _adopt_existing_sdt_slots(
    *,
    control: ET.Element,
    block_id: str,
    registry: FieldRegistrySnapshot,
    indexed_ordered_parts_for_block: list[IndexedSemanticPart],
    resolved_spans: list[JsonObject],
) -> list[JsonObject]:
    operations: list[JsonObject] = []
    for part_index, part in indexed_ordered_parts_for_block:
        _reject_retired_semantic_part_index(part)
        if not semantic_part_is_slot(part):
            continue
        field_ids = explicit_field_ids_from_source(part)
        if len(field_ids) != 1:
            raise _slot_ref_missing(part_index=part_index)
        field_id = field_ids[0]
        span = _span_for_slot_part(
            resolved_spans=resolved_spans,
            part_index=part_index,
            field_id=field_id,
        )
        _adopt_existing_sdt(
            control,
            field_id=field_id,
            slot_ref=str(span["slot_ref"]),
            content_type=_field_content_type(registry, field_id),
        )
        operations.append(
            {
                "action": "materialize_slot",
                "target": "existing_sdt",
                "field_id": field_id,
                "block_id": block_id,
                "part_index": part_index,
                "span_ref": span["span_ref"],
                "slot_ref": span["slot_ref"],
            }
        )
    if len(operations) > 1:
        raise ToolFailure(
            status="needs_input",
            origin="postcondition",
            code="materialization_existing_sdt_slot_ambiguous",
            message="One existing content control cannot be adopted for multiple fill slots.",
        )
    return operations


def _materializable_slot_judgment(judgment: JsonObject) -> bool:
    return any(semantic_part_is_slot(part) for part in ordered_parts(judgment))


def _reject_retired_semantic_part_index(part: JsonObject) -> None:
    if "semantic_part_index" not in part:
        return
    raise ToolFailure(
        status="needs_input",
        origin="postcondition",
        code="materialization_legacy_semantic_part_index",
        message=(
            "Materialization consumes ordered parts by resolved span part_index; "
            "semantic_part_index is not an accepted input field."
        ),
    )


def _covered_blocks(judgment: JsonObject) -> list[str]:
    source_entry_id = _string(judgment.get("source_entry_id"))
    if source_entry_id is not None:
        return [source_entry_id]
    scope = judgment.get("scope")
    if isinstance(scope, dict):
        block_id = scope.get("reading_block_id")
        if isinstance(block_id, str) and block_id.strip():
            return [block_id.strip()]
    span_blocks: list[str] = []
    raw_spans = judgment.get("resolved_spans")
    if isinstance(raw_spans, list):
        for span in raw_spans:
            if not isinstance(span, dict):
                continue
            source_entry_id = _span_source_entry_id(span)
            if source_entry_id is not None:
                span_blocks.append(source_entry_id)
                continue
            raw_source_entry_spans = span.get("source_entry_spans")
            if isinstance(raw_source_entry_spans, list):
                source_span_ids = [
                    source_span_id
                    for item in raw_source_entry_spans
                    if isinstance(item, dict)
                    and (source_span_id := _string(item.get("source_entry_id")))
                    is not None
                ]
                span_blocks.extend(source_span_ids)
                if source_span_ids:
                    continue
            block_id = span.get("reading_block_id")
            if isinstance(block_id, str) and block_id.strip():
                span_blocks.append(block_id.strip())
    if span_blocks:
        return list(dict.fromkeys(span_blocks))
    return []


def _source_refs_by_judgment_object(judgments: list[JsonObject]) -> dict[int, tuple[str, ...]]:
    result: dict[int, tuple[str, ...]] = {}
    for index, judgment in enumerate(judgments):
        judgment_ref = judgment.get("judgment_ref")
        if isinstance(judgment_ref, str) and judgment_ref.strip():
            result[id(judgment)] = (judgment_ref.strip(),)
        else:
            result[id(judgment)] = (f"semantic_judgments[{index}]",)
    return result


def _source_refs_for_judgment(
    judgment_source_refs: dict[int, tuple[str, ...]],
    judgment: JsonObject,
) -> list[str]:
    return list(judgment_source_refs.get(id(judgment), ()))


def _resolved_spans(judgment: JsonObject) -> list[JsonObject]:
    raw_spans = judgment.get("resolved_spans")
    if not isinstance(raw_spans, list):
        return []
    return [span for span in raw_spans if isinstance(span, dict)]


def _resolved_spans_for_block(judgment: JsonObject, block_id: str) -> list[JsonObject]:
    spans: list[JsonObject] = []
    for span in _resolved_spans(judgment):
        if _span_matches_execution_scope(span, block_id):
            spans.append(span)
            continue
        span_block = span.get("reading_block_id")
        if span_block == block_id:
            spans.append(span)
            continue
        scope = span.get("scope")
        if isinstance(scope, dict) and scope.get("reading_block_id") == block_id:
            spans.append(span)
    return spans


def _span_matches_execution_scope(span: JsonObject, scope_id: str) -> bool:
    source_entry_id = _span_source_entry_id(span)
    if source_entry_id == scope_id:
        return True
    source_entry_spans = span.get("source_entry_spans")
    if isinstance(source_entry_spans, list):
        return any(
            isinstance(item, dict)
            and _string(item.get("source_entry_id")) == scope_id
            for item in source_entry_spans
        )
    return False


def _span_source_entry_id(span: JsonObject) -> str | None:
    source_entry_id = _string(span.get("source_entry_id"))
    if source_entry_id is not None:
        return source_entry_id
    scope = span.get("scope")
    if isinstance(scope, dict):
        source_entry_id = _string(scope.get("source_entry_id"))
        if source_entry_id is not None:
            return source_entry_id
    return None


def _span_refs_for_block(
    judgment: JsonObject,
    block_id: str,
    *,
    role: str | None = None,
) -> list[str]:
    refs: list[str] = []
    for span in _resolved_spans_for_block(judgment, block_id):
        if role is not None and span.get("role") != role:
            continue
        span_ref = span.get("span_ref")
        if isinstance(span_ref, str) and span_ref.strip():
            refs.append(span_ref.strip())
    return list(dict.fromkeys(refs))


def _indexed_ordered_parts_for_block(
    judgment: JsonObject,
    block_id: str,
) -> list[IndexedSemanticPart]:
    parts = ordered_parts(judgment)
    by_part_index: dict[int, JsonObject] = {}
    for span in _resolved_spans_for_block(judgment, block_id):
        part_index = span.get("part_index")
        if (
            not isinstance(part_index, int)
            or isinstance(part_index, bool)
            or part_index < 0
            or part_index >= len(parts)
            or part_index in by_part_index
        ):
            continue
        part = parts[part_index]
        _reject_retired_semantic_part_index(part)
        by_part_index[part_index] = part
    return [(index, by_part_index[index]) for index in sorted(by_part_index)]


def _block_is_cleanup_only_part(judgment: JsonObject, block_id: str) -> bool:
    block_parts = _indexed_ordered_parts_for_block(judgment, block_id)
    return bool(block_parts) and all(part_should_delete(part) for _index, part in block_parts)


def _shadow_context_kinds_by_judgment_block(
    plan: MaterializationPlan,
) -> dict[tuple[str, str], str]:
    contexts_by_intent_ref = {
        intent_ref: context
        for context in plan.contexts
        if isinstance((intent_ref := context.facts.get("intent_ref")), str)
    }
    result: dict[tuple[str, str], str] = {}
    for intent in plan.intents:
        context = contexts_by_intent_ref.get(intent.intent_ref)
        if context is None:
            continue
        raw_blocks = context.facts.get("reading_blocks")
        if not isinstance(raw_blocks, list):
            continue
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                continue
            block_id = raw_block.get("block_id")
            if not isinstance(block_id, str) or not block_id.strip():
                continue
            for judgment_ref in intent.source_judgment_refs:
                result[(judgment_ref, block_id.strip())] = context.kind
    return result


def _context_kind_for_judgment_block(
    *,
    context_kinds: dict[tuple[str, str], str],
    judgment_source_refs: tuple[str, ...],
    block_id: str,
) -> str | None:
    for source_ref in judgment_source_refs:
        context_kind = context_kinds.get((source_ref, block_id))
        if context_kind is not None:
            return context_kind
    return None


def _serialize(root: ET.Element) -> bytes:
    payload = cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    ignorable = root.get(f"{{{MC_NS}}}Ignorable", "").split()
    missing = [
        (prefix, _KNOWN_NAMESPACES[prefix])
        for prefix in ignorable
        if prefix in _KNOWN_NAMESPACES and f"xmlns:{prefix}=".encode() not in payload
    ]
    if not missing:
        return payload
    declaration_end = payload.find(b"?>")
    root_start = payload.find(b"<", declaration_end + 2)
    root_end = payload.find(b">", root_start)
    declarations = b"".join(f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing)
    return payload[:root_end] + declarations + payload[root_end:]


def _text_by_block(
    *,
    by_block: dict[str, ET.Element],
    removed: set[int],
) -> dict[str, str]:
    return {
        block_id: "" if id(paragraph) in removed else _paragraph_text(paragraph)
        for block_id, paragraph in by_block.items()
    }


def _ensure_body_structure_execution_closed(
    *,
    plan: MaterializationPlan,
    operations: list[JsonObject],
) -> None:
    expects_body_structure = any(
        intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
        for intent in plan.intents
    )
    if not expects_body_structure:
        return
    if any(operation.get("action") == "materialize_structure" for operation in operations):
        return
    raise ToolFailure(
        status="needs_input",
        origin="harness",
        code="body_structure_materialization_unexecutable",
        message=(
            "Accepted body_structure semantic_judgments compiled to a ready plan, but "
            "the body-structure handler produced no executable Word structure operation."
        ),
        retryable=True,
        suggested_actions=(
            "Return materialization feedback before publishing a candidate.",
            "Revise body_structure ordered parts or extend the Harness materializer.",
        ),
    )


def _expected_slot_refs(plan: MaterializationPlan) -> set[str]:
    refs: set[str] = set()
    for intent in plan.intents:
        if intent.intent_type != MaterializationIntentType.MATERIALIZE_SLOT:
            continue
        raw_spans = intent.payload.get("resolved_spans")
        if not isinstance(raw_spans, list):
            continue
        for span in raw_spans:
            if not isinstance(span, dict) or span.get("role") != "fill_slot":
                continue
            slot_ref = span.get("slot_ref")
            if isinstance(slot_ref, str) and slot_ref.strip():
                refs.add(slot_ref.strip())
    return refs


def _materialized_slot_refs(operations: list[JsonObject]) -> set[str]:
    refs: set[str] = set()
    for operation in operations:
        if operation.get("action") != "materialize_slot":
            continue
        slot_ref = operation.get("slot_ref")
        if isinstance(slot_ref, str) and slot_ref.strip():
            refs.add(slot_ref.strip())
    return refs


def _ensure_slot_execution_closed(
    *,
    plan: MaterializationPlan,
    operations: list[JsonObject],
) -> None:
    missing = sorted(_expected_slot_refs(plan) - _materialized_slot_refs(operations))
    if not missing:
        return
    raise ToolFailure(
        status="needs_input",
        origin="harness",
        code="slot_materialization_unexecutable",
        message=(
            "Accepted fill_slot semantic_judgments compiled to a ready plan, but "
            "one or more Harness slot_refs did not resolve to executable Word ranges."
        ),
        retryable=True,
        suggested_actions=(
            "Return materialization feedback before publishing a candidate.",
            "Rebuild the Harness inventory and source-entry spans before writing.",
        ),
    )


def materialize_template_from_semantics(
    *,
    source_docx: Path,
    output_docx: Path,
    registry: FieldRegistrySnapshot,
    inventory: JsonObject,
    review: JsonObject,
) -> JsonObject:
    current_document_sha256 = _ensure_source_document_hash_current(
        source_docx=source_docx,
        inventory=inventory,
        review=review,
    )
    readiness_feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    if readiness_feedback is not None:
        blockers = readiness_feedback.get("blockers")
        unsupported_codes = [
            str(blocker["code"])
            for blocker in blockers[:5]
            if isinstance(blocker, dict)
            and isinstance(blocker.get("code"), str)
            and blocker["code"].strip()
        ] if isinstance(blockers, list) else []
        summary = ", ".join(unsupported_codes) if unsupported_codes else "unsupported"
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="template_materialization_readiness_incomplete",
            message=(
                "Accepted semantic_judgments are not ready for deterministic "
                f"materialization: {summary}."
            ),
            retryable=True,
            suggested_actions=(
                "Return materialization readiness feedback to the Agent.",
                "Revise semantic_judgments before writing a materialized DOCX candidate.",
            ),
        )
    shadow_result = build_shadow_materialization_plan(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    shadow_intent_plan = shadow_result.to_json()
    if not shadow_result.ready:
        unsupported_codes = [
            item.reason_code
            for item in shadow_result.unsupported[:5]
            if item.reason_code.strip()
        ]
        summary = ", ".join(unsupported_codes) if unsupported_codes else "unsupported"
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="template_materialization_readiness_incomplete",
            message=(
                "Accepted semantic_judgments are not ready for deterministic "
                f"materialization: {summary}."
            ),
            retryable=True,
            suggested_actions=(
                "Return materialization readiness feedback to the Agent.",
                "Revise semantic_judgments before writing a materialized DOCX candidate.",
            ),
        )
    policy_receipts = [
        *manual_table_cell_policy_receipts(shadow_result.plan),
        *generated_content_policy_receipts(shadow_result.plan),
    ]
    with zipfile.ZipFile(source_docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    _ensure_source_entry_provenance_fresh(
        document=document,
        inventory=inventory,
        current_document_sha256=current_document_sha256,
    )
    by_block = _paragraph_by_block(document=document, inventory=inventory)
    sdt_by_block = _sdt_by_block(document=document, inventory=inventory)
    block_texts = _reading_block_texts(inventory)
    before_text_by_block = dict(block_texts)
    operations: list[JsonObject] = []
    cleanup: list[JsonObject] = []

    raw_judgments = review.get("semantic_judgments", [])
    judgments = [item for item in raw_judgments if isinstance(item, dict)]
    judgment_source_refs = _source_refs_by_judgment_object(judgments)
    context_kinds = _shadow_context_kinds_by_judgment_block(shadow_result.plan)
    removed: set[int] = set()
    body_operations, body_cleanup, body_structure_blocks = materialize_body_structure(
        document=document,
        by_block=by_block,
        registry=registry,
        inventory=inventory,
        plan=shadow_result.plan,
        removed=removed,
    )
    _ensure_body_structure_execution_closed(
        plan=shadow_result.plan,
        operations=body_operations,
    )
    operations.extend(body_operations)
    cleanup.extend(body_cleanup)

    for judgment in judgments:
        blocks = _covered_blocks(judgment)
        if not blocks:
            continue
        if is_delete_treatment(judgment):
            for block_id in blocks:
                if block_id in body_structure_blocks:
                    continue
                paragraph = by_block.get(block_id)
                if paragraph is None:
                    continue
                if should_remove_paragraph(judgment):
                    parent = _paragraph_parent(document, paragraph)
                    if parent is not None and id(paragraph) not in removed:
                        parent.remove(paragraph)
                        removed.add(id(paragraph))
                        cleanup.append(
                            {
                                "block_id": block_id,
                                "action": "remove_paragraph",
                                "judgment_refs": _source_refs_for_judgment(
                                    judgment_source_refs,
                                    judgment,
                                ),
                                "span_refs": _span_refs_for_block(
                                    judgment,
                                    block_id,
                                    role="cleanup",
                                ),
                            }
                        )
                else:
                    _clear_paragraph_text(paragraph)
                    cleanup.append(
                        {
                            "block_id": block_id,
                            "action": "clear_text",
                            "judgment_refs": _source_refs_for_judgment(
                                judgment_source_refs,
                                judgment,
                            ),
                            "span_refs": _span_refs_for_block(
                                judgment,
                                block_id,
                                role="cleanup",
                            ),
                        }
                    )

    slot_judgments_by_block: dict[str, list[str]] = {}
    slot_parts_by_block: dict[str, list[IndexedSemanticPart]] = {}
    slot_spans_by_block: dict[str, list[JsonObject]] = {}
    for judgment in judgments:
        blocks = _covered_blocks(judgment)
        if not blocks:
            continue
        if _materializable_slot_judgment(judgment):
            for block_id in blocks:
                if block_id in body_structure_blocks:
                    continue
                resolved_spans = _resolved_spans_for_block(judgment, block_id)
                judgment_parts = _indexed_ordered_parts_for_block(judgment, block_id)
                if judgment_parts and all(
                    part_should_delete(part) for _index, part in judgment_parts
                ):
                    paragraph = by_block.get(block_id)
                    if paragraph is None or id(paragraph) in removed:
                        continue
                    parent = _paragraph_parent(document, paragraph)
                    if parent is not None:
                        parent.remove(paragraph)
                        removed.add(id(paragraph))
                        cleanup.append(
                            {
                                "block_id": block_id,
                                "action": "remove_paragraph",
                                "judgment_refs": _source_refs_for_judgment(
                                    judgment_source_refs,
                                    judgment,
                                ),
                                "span_refs": _span_refs_for_block(
                                    judgment,
                                    block_id,
                                    role="cleanup",
                                ),
                            }
                        )
                    continue
                if not any(semantic_part_is_slot(part) for _index, part in judgment_parts):
                    continue
                existing_sdt = sdt_by_block.get(block_id)
                if existing_sdt is not None:
                    operations.extend(
                        {
                            "judgment_refs": _source_refs_for_judgment(
                                judgment_source_refs,
                                judgment,
                            ),
                            **operation,
                        }
                        for operation in _adopt_existing_sdt_slots(
                            control=existing_sdt,
                            block_id=block_id,
                            registry=registry,
                            indexed_ordered_parts_for_block=judgment_parts,
                            resolved_spans=resolved_spans,
                        )
                    )
                    continue
                slot_judgments_by_block.setdefault(block_id, []).extend(
                    _source_refs_for_judgment(
                        judgment_source_refs,
                        judgment,
                    )
                )
                slot_parts_by_block[block_id] = judgment_parts
                slot_spans_by_block[block_id] = resolved_spans
        else:
            for block_id in blocks:
                if block_id in body_structure_blocks:
                    continue
                paragraph = by_block.get(block_id)
                if paragraph is None or id(paragraph) in removed:
                    continue
                if _block_is_cleanup_only_part(judgment, block_id):
                    parent = _paragraph_parent(document, paragraph)
                    if parent is not None:
                        parent.remove(paragraph)
                        removed.add(id(paragraph))
                        cleanup.append(
                            {
                                "block_id": block_id,
                                "action": "remove_paragraph",
                                "judgment_refs": _source_refs_for_judgment(
                                    judgment_source_refs,
                                    judgment,
                                ),
                                "span_refs": _span_refs_for_block(
                                    judgment,
                                    block_id,
                                    role="cleanup",
                                ),
                            }
                        )
                    continue
                context_kind = _context_kind_for_judgment_block(
                    context_kinds=context_kinds,
                    judgment_source_refs=judgment_source_refs.get(id(judgment), ()),
                    block_id=block_id,
                )
                if apply_fixed_content_cleanup(paragraph, context_kind=context_kind):
                    cleanup.append(
                        {
                            "block_id": block_id,
                            "action": "strip_instruction_text",
                            "judgment_refs": _source_refs_for_judgment(
                                judgment_source_refs,
                                judgment,
                            ),
                        }
                    )

    for block_id, indexed_ordered_parts_for_block in slot_parts_by_block.items():
        paragraph = by_block.get(block_id)
        if paragraph is None or id(paragraph) in removed:
            continue
        operations.extend(
            {
                "judgment_refs": slot_judgments_by_block.get(block_id, []),
                **operation,
            }
            for operation in materialize_slot_paragraph(
                paragraph=paragraph,
                block_id=block_id,
                registry=registry,
                indexed_ordered_parts=indexed_ordered_parts_for_block,
                resolved_spans=slot_spans_by_block.get(block_id, []),
            )
        )

    _ensure_slot_execution_closed(plan=shadow_result.plan, operations=operations)

    after_text_by_block = _text_by_block(by_block=by_block, removed=removed)
    mutation_receipts = build_materialization_receipts(
        plan=shadow_result.plan,
        operations=operations,
        cleanup=cleanup,
        policy_receipts=policy_receipts,
        before_text_by_block=before_text_by_block,
        after_text_by_block=after_text_by_block,
    )
    write_result = write_materialized_docx(
        source_docx=source_docx,
        output_docx=output_docx,
        document_xml=_serialize(document),
    )
    field_registry_ref = registry.identity()
    return {
        "schema_version": 1,
        "document_sha256": review.get("document_sha256"),
        "semantic_judgments_sha256": review.get("semantic_judgments_sha256"),
        "field_vocabulary_digest": review.get("field_vocabulary_digest"),
        "field_registry_ref": field_registry_ref,
        "operation_count": len(operations),
        "cleanup_count": len(cleanup),
        "operations": operations,
        "cleanup": cleanup,
        "policy_receipts": policy_receipts,
        "mutation_receipts": mutation_receipts,
        "receipt_count": len(mutation_receipts),
        "write": write_result,
        "shadow_intent_plan": shadow_intent_plan,
    }
