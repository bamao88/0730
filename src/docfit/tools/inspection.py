"""Snapshot inspection and opaque object-ref generation."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
V_NS = "urn:schemas-microsoft-com:vml"

_FORMAT_ALIASES = {
    "align": "alignment",
    "keepLines": "keepTogether",
    "keepNext": "keepWithNext",
}
_PUBLIC_FORMAT_KEYS = {
    "alignment",
    "bold",
    "color",
    "font",
    "font.ascii",
    "font.eastAsia",
    "font.hAnsi",
    "font.ea",
    "font.latin",
    "height",
    "italic",
    "keepTogether",
    "keepWithNext",
    "lineRule",
    "lineSpacing",
    "pageBreakBefore",
    "size",
    "spaceAfter",
    "spaceBefore",
    "widowControl",
    "width",
}


@dataclass(frozen=True, slots=True)
class InspectedObject:
    locator: str
    kind: str
    text: str
    style: str | None
    format: JsonObject
    object_ref: JsonObject

    def public(self) -> JsonObject:
        result: JsonObject = {
            "type": self.kind,
            "text": self.text,
            "object_ref": self.object_ref,
        }
        if self.style:
            result["style"] = self.style
        if self.format:
            result["format"] = self.format
        return result


@dataclass(frozen=True, slots=True)
class Inspection:
    document_sha256: str
    objects: tuple[InspectedObject, ...]
    summary: JsonObject
    risks: tuple[JsonObject, ...]
    warnings: tuple[JsonObject, ...]
    provider: JsonObject

    def by_id(self) -> dict[str, InspectedObject]:
        return {str(item.object_ref["object_id"]): item for item in self.objects}


def _safe_format(value: Any) -> JsonObject:
    if not isinstance(value, dict):
        return {}
    allowed_prefixes = (
        "effective.",
        "border.",
        "margin",
        "rows",
        "cols",
        "spacing",
        "indent",
        "style",
    )
    result: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(
            item, (str, int, float, bool, type(None))
        ):
            continue
        public_key = _FORMAT_ALIASES.get(key, key)
        if public_key in _PUBLIC_FORMAT_KEYS or public_key.startswith(allowed_prefixes):
            result[public_key] = item
    return result


def _package_facts(document: Path) -> JsonObject:
    with zipfile.ZipFile(document) as archive:
        document_root = ET.fromstring(archive.read("word/document.xml"))
        names = archive.namelist()
    return {
        "package_parts": len(names),
        "sections": len(document_root.findall(f".//{{{W_NS}}}sectPr")),
        "images": sum(1 for name in names if name.startswith("word/media/")),
        "drawings": len(document_root.findall(f".//{{{W_NS}}}drawing")),
        "equations": len(
            document_root.findall(
                ".//{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
            )
        ),
        "text_boxes": len(document_root.findall(f".//{{{W_NS}}}txbxContent")),
        "vml_objects": len(document_root.findall(f".//{{{V_NS}}}shape")),
        "graphic_objects": len(document_root.findall(f".//{{{A_NS}}}graphic")),
        "footnotes": "word/footnotes.xml" in names,
        "endnotes": "word/endnotes.xml" in names,
        "comments": "word/comments.xml" in names,
        "headers": sum(
            1 for name in names if re.fullmatch(r"word/header\d+\.xml", name)
        ),
        "footers": sum(
            1 for name in names if re.fullmatch(r"word/footer\d+\.xml", name)
        ),
        "numbering_part": "word/numbering.xml" in names,
        "styles_part": "word/styles.xml" in names,
        "bookmarks": len(document_root.findall(f".//{{{W_NS}}}bookmarkStart")),
        "fields": len(document_root.findall(f".//{{{W_NS}}}fldSimple"))
        + len(
            document_root.findall(
                f".//{{{W_NS}}}fldChar[@{{{W_NS}}}fldCharType='begin']"
            )
        ),
        "content_controls": len(document_root.findall(f".//{{{W_NS}}}sdt")),
        "hyperlinks": len(document_root.findall(f".//{{{W_NS}}}hyperlink")),
        "merged_cells": len(document_root.findall(f".//{{{W_NS}}}gridSpan"))
        + len(document_root.findall(f".//{{{W_NS}}}vMerge")),
        "tracked_insertions": len(document_root.findall(f".//{{{W_NS}}}ins")),
        "tracked_deletions": len(document_root.findall(f".//{{{W_NS}}}del")),
    }


def inspect_document(document: Path, office: OfficeCliAdapter) -> Inspection:
    package_warnings = validate_docx_package(document)
    document_sha256 = sha256_file(document)
    raw_objects = office.query(document, "paragraph, table, picture")
    objects: list[InspectedObject] = []
    counts: dict[str, int] = {}
    for raw in raw_objects:
        locator = raw.get("path")
        kind = raw.get("type")
        if not isinstance(locator, str) or not isinstance(kind, str):
            continue
        raw_text = raw.get("text")
        text = raw_text if isinstance(raw_text, str) else ""
        raw_style = raw.get("style")
        style = raw_style if isinstance(raw_style, str) else None
        safe_format = _safe_format(raw.get("format"))
        fingerprint = sha256_json(
            {
                "type": kind,
                "text": text,
                "style": style,
                "format": safe_format,
            }
        )
        identity = {
            "document": document_sha256,
            "locator": locator,
            "type": kind,
        }
        object_id = f"obj-{sha256_json(identity)[:24]}"
        object_ref: JsonObject = {
            "schema_version": 1,
            "document_sha256": document_sha256,
            "object_id": object_id,
            "expected_fingerprint": fingerprint,
        }
        objects.append(InspectedObject(locator, kind, text, style, safe_format, object_ref))
        counts[kind] = counts.get(kind, 0) + 1
    facts = _package_facts(document)
    risks: list[JsonObject] = []
    for fact, kind in (
        ("text_boxes", "unsupported_text_box"),
        ("vml_objects", "unsupported_vml_object"),
        ("content_controls", "unsupported_content_control"),
    ):
        count = facts.get(fact)
        if isinstance(count, int) and count:
            risks.append({"kind": kind, "count": count, "blocking": False})
    summary: JsonObject = {
        "paragraphs": counts.get("paragraph", 0),
        "tables": counts.get("table", 0),
        **facts,
    }
    warnings = tuple(
        {
            "code": value,
            "kind": "package",
            "message": "The package contains a non-blocking relationship warning.",
        }
        for value in package_warnings
    )
    return Inspection(
        document_sha256,
        tuple(objects),
        summary,
        tuple(risks),
        warnings,
        office.evidence(),
    )


def resolve_object_ref(reference: Any, inspection: Inspection) -> InspectedObject:
    from docfit.tools.runtime import ToolFailure

    if not isinstance(reference, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_object_ref",
            message="An operation target must be an object_ref object.",
        )
    if reference.get("schema_version") != 1:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_object_ref_version",
            message="The object_ref schema version is unsupported.",
        )
    if reference.get("document_sha256") != inspection.document_sha256:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="stale_object_ref",
            message="The object_ref belongs to a different document snapshot; inspect again.",
            suggested_actions=("inspect_document_again",),
        )
    object_id = reference.get("object_id")
    item = inspection.by_id().get(object_id) if isinstance(object_id, str) else None
    if item is None or reference.get("expected_fingerprint") != item.object_ref.get(
        "expected_fingerprint"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="object_fingerprint_mismatch",
            message="The object_ref no longer matches the inspected object; inspect again.",
            suggested_actions=("inspect_document_again",),
        )
    return item
