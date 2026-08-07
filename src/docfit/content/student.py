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

    body_order = _body_locator_order(source_docx) if source_docx is not None else {}
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
    return {
        "schema_version": "docfit-student-inventory/v1",
        "source_sha256": inspection.document_sha256,
        "object_count": len(items),
        "transferable_object_count": transferable_count,
        "objects": items,
        "package_summary": dict(inspection.summary),
        "risks": [dict(value) for value in inspection.risks],
        "warnings": [dict(value) for value in inspection.warnings],
        "provider": dict(inspection.provider),
        "privacy": "task_local_contains_student_content",
    }


def _body_locator_order(source_docx: Path) -> dict[str, int]:
    with zipfile.ZipFile(source_docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{{{_W_NS}}}body")
    if body is None:
        raise ValueError("The student document body is missing.")
    locators: dict[str, int] = {}
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
            locators[locator] = body_sequence
    return locators


def _content_type(kind: str, format_value: dict[str, Any]) -> str:
    if kind == "picture":
        return "image"
    if kind == "table":
        return "table"
    if any(key.startswith("equation") or key.startswith("math") for key in format_value):
        return "equation"
    return "rich_text" if kind == "paragraph" else kind
