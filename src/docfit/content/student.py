"""Hash-bound inventory of one read-only student document snapshot."""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import JsonObject, sha256_bytes, sha256_json

_TOP_LEVEL_PARAGRAPH = re.compile(r"/body/p\[@paraId=[0-9A-Fa-f]+\]")
_TOP_LEVEL_TABLE = re.compile(r"/body/tbl\[\d+\]")
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_CHAPTER_NUMBERING = re.compile(r"^第[一二三四五六七八九十百]+章(?:\s|$)")
_DECIMAL_NUMBERING = re.compile(r"^(\d+(?:\.\d+)*)(?:[.、]?\s*)")
_PARENTHESIZED_NUMBERING = re.compile(r"^[（(]\d+[）)]")
_CHINESE_ENUMERATION = re.compile(r"^[一二三四五六七八九十百]+[、.]")


def _is_transferable(kind: str, locator: str) -> bool:
    return bool(
        (kind == "paragraph" and _TOP_LEVEL_PARAGRAPH.fullmatch(locator))
        or (kind == "table" and _TOP_LEVEL_TABLE.fullmatch(locator))
    )


def build_student_inventory(
    inspection: Inspection,
    *,
    source_docx: Path | None = None,
) -> JsonObject:
    """Return a private task-local inventory; callers must not publish its text to logs."""

    body_objects = _top_level_body_objects(source_docx) if source_docx is not None else []
    body_facts = {str(value["locator"]): value for value in body_objects}
    body_order = {
        locator: int(value["body_sequence"])
        for locator, value in body_facts.items()
    }
    items: list[JsonObject] = []
    seen_ids: set[str] = set()
    transferable_count = 0
    for sequence, inspected in enumerate(inspection.objects, start=1):
        object_id = inspected.object_ref.get("object_id")
        if not isinstance(object_id, str) or object_id in seen_ids:
            raise ValueError("Inspection object IDs must be unique strings.")
        seen_ids.add(object_id)
        fallback_transferable = _is_transferable(inspected.kind, inspected.locator)
        body_sequence = body_order.get(inspected.locator)
        body_fact = body_facts.get(inspected.locator)
        transferable = (
            body_sequence is not None if source_docx is not None else fallback_transferable
        )
        if transferable:
            transferable_count += 1
            if body_sequence is None:
                body_sequence = transferable_count
        identity = {"document": inspection.document_sha256, "object_id": object_id}
        content_id = f"content-{sha256_json(identity)[:24]}"
        items.append(
            {
                "content_id": content_id,
                "sequence": sequence,
                "kind": inspected.kind,
                "content_type": _source_content_type(inspected, body_fact),
                "text": inspected.text,
                "text_sha256": sha256_bytes(inspected.text.encode("utf-8")),
                "style": inspected.style,
                "transferable": transferable,
                "body_sequence": body_sequence,
                "inline_sequence": (
                    list(body_fact.get("inline_sequence", []))
                    if body_fact is not None
                    else []
                ),
                "source_locator": inspected.locator,
                "source_object_ref": dict(inspected.object_ref),
            }
        )
    synthetic_count = 0
    represented_locators = {
        str(item["source_locator"]) for item in items if item.get("transferable") is True
    }
    for body_object in body_objects:
        locator = str(body_object["locator"])
        if locator in represented_locators:
            continue
        object_identity = {
            "document": inspection.document_sha256,
            "locator": locator,
            "element_sha256": body_object["element_sha256"],
        }
        object_id = f"student-ooxml-{sha256_json(object_identity)[:24]}"
        content_identity = {
            "document": inspection.document_sha256,
            "object_id": object_id,
        }
        content_id = f"content-{sha256_json(content_identity)[:24]}"
        text = str(body_object["text"])
        items.append(
            {
                "content_id": content_id,
                "sequence": len(items) + 1,
                "kind": body_object["kind"],
                "content_type": body_object["content_type"],
                "text": text,
                "text_sha256": sha256_bytes(text.encode("utf-8")),
                "style": body_object["style"],
                "inline_sequence": list(body_object.get("inline_sequence", [])),
                "transferable": True,
                "body_sequence": body_object["body_sequence"],
                "source_locator": locator,
                "source_object_ref": {
                    "document_sha256": inspection.document_sha256,
                    "object_id": object_id,
                    "expected_fingerprint": body_object["element_sha256"],
                },
                "inventory_origin": "ooxml_top_level_recovery",
            }
        )
        synthetic_count += 1
        transferable_count += 1
    content_items = _neutral_content_items(items, inspection.document_sha256)
    numbering_shapes = Counter(
        str(item.get("source_facts", {}).get("numbering_shape", "none"))
        for item in content_items
        if item.get("physical_type") == "text"
    )
    return {
        "schema_version": "docfit-student-source-inventory/v2",
        "source_sha256": inspection.document_sha256,
        "object_count": len(items),
        "content_item_count": len(content_items),
        "transferable_object_count": transferable_count,
        "synthetic_transferable_object_count": synthetic_count,
        "objects": items,
        "content_items": content_items,
        "semantic_neutral_profile": {
            "numbering_shape_counts": dict(sorted(numbering_shapes.items())),
        },
        "package_summary": dict(inspection.summary),
        "risks": [dict(value) for value in inspection.risks],
        "warnings": [dict(value) for value in inspection.warnings],
        "provider": dict(inspection.provider),
        "privacy": "task_local_contains_student_content",
    }


def _neutral_content_items(
    objects: list[JsonObject],
    source_sha256: str,
) -> list[JsonObject]:
    """Project Word facts into ordered content instances without semantic labels."""

    top_level = [item for item in objects if item.get("transferable") is True]
    top_level.sort(key=_body_sequence)
    top_by_locator = {str(item["source_locator"]): item for item in top_level}
    descendants: dict[str, list[JsonObject]] = {locator: [] for locator in top_by_locator}
    for item in objects:
        if item.get("transferable") is True:
            continue
        locator = str(item.get("source_locator", ""))
        parent_locator = max(
            (
                candidate
                for candidate in top_by_locator
                if locator.startswith(f"{candidate}/")
            ),
            key=len,
            default=None,
        )
        if parent_locator is not None:
            descendants[parent_locator].append(item)

    content_items: list[JsonObject] = []
    for fallback_block, transport in enumerate(top_level, start=1):
        block = transport.get("body_sequence")
        block_order = (
            block
            if isinstance(block, int) and not isinstance(block, bool)
            else fallback_block
        )
        transport_ref = transport.get("source_object_ref")
        if not isinstance(transport_ref, dict) or not isinstance(
            transport_ref.get("object_id"), str
        ):
            continue
        transport_locator = str(transport.get("source_locator", ""))
        kind = str(transport.get("kind", ""))
        content_type = str(transport.get("content_type", ""))
        text = str(transport.get("text", ""))
        if kind == "table":
            content_items.append(
                _neutral_item(
                    source_sha256=source_sha256,
                    source_objects=(transport,),
                    transport=transport,
                    physical_type="table",
                    block_order=block_order,
                    inline_order=0,
                    observed_text=text,
                )
            )
        elif content_type == "equation":
            content_items.append(
                _neutral_item(
                    source_sha256=source_sha256,
                    source_objects=(transport,),
                    transport=transport,
                    physical_type="equation",
                    block_order=block_order,
                    inline_order=0,
                    observed_text=text,
                )
            )
        else:
            children = [
                child
                for child in sorted(
                    descendants.get(transport_locator, []), key=_inspection_sequence
                )
                if str(child.get("kind", "")) in {"picture", "shape"}
            ]
            components = _ordered_inline_components(
                transport=transport,
                text=text,
                children=children,
            )
            for inline, (component_type, source_object, observed_text) in enumerate(
                components
            ):
                component_kind = str(source_object.get("kind", ""))
                content_items.append(
                    _neutral_item(
                        source_sha256=source_sha256,
                        source_objects=(source_object,),
                        transport=transport,
                        physical_type=(
                            "text"
                            if component_type == "text"
                            else "image"
                            if component_kind == "picture"
                            else "structured_object"
                        ),
                        block_order=block_order,
                        inline_order=inline,
                        observed_text=observed_text,
                    )
                )
    return content_items


def _ordered_inline_components(
    *,
    transport: JsonObject,
    text: str,
    children: list[JsonObject],
) -> list[tuple[str, JsonObject, str]]:
    """Project one Word anchor block into its stable human reading order."""

    raw_sequence = transport.get("inline_sequence")
    sequence = (
        [str(value) for value in raw_sequence]
        if isinstance(raw_sequence, list)
        else []
    )
    if not sequence:
        sequence = (["text"] if text.strip() else []) + ["structured"] * len(children)
    # Word commonly serializes a floating drawing after the host paragraph text even
    # when the drawing is the principal visible object above that text.  Keep the raw
    # package sequence as a fact, but use the stable reading policy expected by content
    # extraction: complex object first, then its host paragraph text.
    if children:
        sequence = ["structured"] * len(children) + (["text"] if text.strip() else [])
    components: list[tuple[str, JsonObject, str]] = []
    text_emitted = False
    child_index = 0
    for value in sequence:
        if value == "text" and text.strip() and not text_emitted:
            components.append(("text", transport, text))
            text_emitted = True
        elif value == "structured" and child_index < len(children):
            child = children[child_index]
            components.append(("structured", child, str(child.get("text", ""))))
            child_index += 1
    if text.strip() and not text_emitted:
        components.append(("text", transport, text))
    for child in children[child_index:]:
        components.append(("structured", child, str(child.get("text", ""))))
    return components


def _neutral_item(
    *,
    source_sha256: str,
    source_objects: tuple[JsonObject, ...],
    transport: JsonObject,
    physical_type: str,
    block_order: int,
    inline_order: int,
    observed_text: str,
) -> JsonObject:
    object_ids = [str(item["source_object_ref"]["object_id"]) for item in source_objects]
    locators = [str(item["source_locator"]) for item in source_objects]
    transport_object_id = str(transport["source_object_ref"]["object_id"])
    identity = {
        "document": source_sha256,
        "source_object_ids": object_ids,
        "physical_type": physical_type,
        "source_order": [block_order, inline_order],
    }
    return {
        "source_content_id": f"source-content-{sha256_json(identity)[:24]}",
        "physical_type": physical_type,
        "observed_text": observed_text,
        "observed_text_sha256": sha256_bytes(observed_text.encode("utf-8")),
        "source_order": {"block": block_order, "inline": inline_order},
        "source_object_ids": object_ids,
        "source_locators": locators,
        "transport_source_object_id": transport_object_id,
        "transport_source_locator": str(transport["source_locator"]),
        "content_ref": {
            "student_document_sha256": source_sha256,
            "source_object_ids": object_ids,
            "source_locators": locators,
        },
        "source_facts": {
            "paragraph_style": str(transport.get("style", "")),
            "text_length": len(observed_text),
            "numbering_shape": (
                _numbering_shape(observed_text)
                if physical_type == "text"
                else "not_text"
            ),
            "xml_inline_sequence": list(transport.get("inline_sequence", [])),
            "reading_order_policy": (
                "complex_object_before_host_text"
                if source_objects[0] is not transport
                or transport.get("inline_sequence", []).count("structured")
                else "main_story"
            ),
        },
    }


def _numbering_shape(value: str) -> str:
    stripped = value.strip()
    if _CHAPTER_NUMBERING.match(stripped):
        return "chinese_chapter"
    if _PARENTHESIZED_NUMBERING.match(stripped):
        return "parenthesized_integer"
    if _CHINESE_ENUMERATION.match(stripped):
        return "chinese_enumeration"
    decimal = _DECIMAL_NUMBERING.match(stripped)
    if decimal is not None:
        components = decimal.group(1).count(".") + 1
        return f"decimal_{min(components, 4)}_component"
    return "none"


def _body_sequence(value: JsonObject) -> int:
    body_sequence = value.get("body_sequence")
    if isinstance(body_sequence, int) and not isinstance(body_sequence, bool):
        return body_sequence
    return 0


def _inspection_sequence(value: JsonObject) -> int:
    sequence = value.get("sequence")
    return sequence if isinstance(sequence, int) and not isinstance(sequence, bool) else 0


def _body_locator_order(source_docx: Path) -> dict[str, int]:
    return {
        str(value["locator"]): int(value["body_sequence"])
        for value in _top_level_body_objects(source_docx)
    }


def _top_level_body_objects(source_docx: Path) -> list[JsonObject]:
    with zipfile.ZipFile(source_docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{{{_W_NS}}}body")
    if body is None:
        raise ValueError("The student document body is missing.")
    objects: list[JsonObject] = []
    table_index = 0
    body_sequence = 0
    for child in body:
        locator: str | None = None
        if child.tag == f"{{{_W_NS}}}p":
            para_id = next(
                (value for key, value in child.attrib.items() if key.endswith("}paraId")),
                None,
            )
            if para_id:
                locator = f"/body/p[@paraId={para_id}]"
        elif child.tag == f"{{{_W_NS}}}tbl":
            table_index += 1
            locator = f"/body/tbl[{table_index}]"
        if locator is not None:
            body_sequence += 1
            p_style = child.find(f"{{{_W_NS}}}pPr/{{{_W_NS}}}pStyle")
            style = p_style.get(f"{{{_W_NS}}}val", "") if p_style is not None else ""
            text = "".join(
                value.text or ""
                for value in child.iter()
                if value.tag in {f"{{{_W_NS}}}t", f"{{{_M_NS}}}t"}
            )
            has_equation = any(
                value.tag in {f"{{{_M_NS}}}oMath", f"{{{_M_NS}}}oMathPara"}
                for value in child.iter()
            )
            payload = ET.tostring(child, encoding="utf-8")
            objects.append(
                {
                    "locator": locator,
                    "body_sequence": body_sequence,
                    "kind": "table" if child.tag == f"{{{_W_NS}}}tbl" else "paragraph",
                    "content_type": (
                        "table"
                        if child.tag == f"{{{_W_NS}}}tbl"
                        else "equation"
                        if has_equation
                        else "rich_text"
                    ),
                    "text": text,
                    "style": style,
                    "element_sha256": sha256_bytes(payload),
                    "inline_sequence": _inline_sequence(child),
                }
            )
    return objects


def _inline_sequence(element: ET.Element) -> list[str]:
    sequence: list[str] = []
    text_emitted = False

    def visit(node: ET.Element) -> None:
        nonlocal text_emitted
        if node.tag in {f"{{{_W_NS}}}drawing", f"{{{_W_NS}}}pict"}:
            sequence.append("structured")
            return
        if node.tag in {f"{{{_W_NS}}}t", f"{{{_M_NS}}}t"}:
            if (node.text or "").strip() and not text_emitted:
                sequence.append("text")
                text_emitted = True
            return
        for child in node:
            visit(child)

    visit(element)
    return sequence


def _content_type(kind: str, format_value: dict[str, Any]) -> str:
    if kind == "picture":
        return "image"
    if kind == "table":
        return "table"
    if any(key.startswith("equation") or key.startswith("math") for key in format_value):
        return "equation"
    return "rich_text" if kind == "paragraph" else kind


def _source_content_type(
    inspected: InspectedObject,
    body_fact: JsonObject | None,
) -> str:
    """Prefer explicit package structure over a provider's generic paragraph type."""

    if body_fact is not None and body_fact.get("content_type") in {"equation", "table"}:
        return str(body_fact["content_type"])
    return _content_type(str(inspected.kind), inspected.format)
