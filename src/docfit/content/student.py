"""Hash-bound inventory of one read-only student document snapshot."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from docfit.tools.inspection import Inspection
from docfit.tools.runtime import JsonObject, sha256_bytes, sha256_json

_TOP_LEVEL_PARAGRAPH = re.compile(r"/body/p\[@paraId=[0-9A-Fa-f]+\]")
_TOP_LEVEL_TABLE = re.compile(r"/body/tbl\[\d+\]")
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


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
    body_order = {str(value["locator"]): int(value["body_sequence"]) for value in body_objects}
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
                "content_type": _content_type(inspected.kind, inspected.format),
                "text": inspected.text,
                "text_sha256": sha256_bytes(inspected.text.encode("utf-8")),
                "style": inspected.style,
                "transferable": transferable,
                "body_sequence": body_sequence,
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
    return {
        "schema_version": "docfit-student-inventory/v1",
        "source_sha256": inspection.document_sha256,
        "object_count": len(items),
        "transferable_object_count": transferable_count,
        "synthetic_transferable_object_count": synthetic_count,
        "objects": items,
        "package_summary": dict(inspection.summary),
        "risks": [dict(value) for value in inspection.risks],
        "warnings": [dict(value) for value in inspection.warnings],
        "provider": dict(inspection.provider),
        "privacy": "task_local_contains_student_content",
    }


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
                }
            )
    return objects


def _content_type(kind: str, format_value: dict[str, Any]) -> str:
    if kind == "picture":
        return "image"
    if kind == "table":
        return "table"
    if any(key.startswith("equation") or key.startswith("math") for key in format_value):
        return "equation"
    return "rich_text" if kind == "paragraph" else kind
