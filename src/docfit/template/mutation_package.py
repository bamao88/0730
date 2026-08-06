"""Bounded OOXML execution for compiled template mutation operations."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_W = f"{{{W_NS}}}"
_KNOWN_NAMESPACES = {
    "w": W_NS,
    "mc": MC_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}
for _prefix, _uri in _KNOWN_NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)


def _serialize(root: ET.Element) -> bytes:
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ignorable = root.get(f"{{{MC_NS}}}Ignorable", "").split()
    missing = [
        (prefix, _KNOWN_NAMESPACES[prefix])
        for prefix in ignorable
        if prefix in _KNOWN_NAMESPACES and f"xmlns:{prefix}=".encode() not in payload
    ]
    if missing:
        declaration_end = payload.find(b"?>")
        root_start = payload.find(b"<", declaration_end + 2)
        root_end = payload.find(b">", root_start)
        declarations = b"".join(
            f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing
        )
        payload = payload[:root_end] + declarations + payload[root_end:]
    return cast(bytes, payload)


def _target(
    roots: dict[str, ET.Element],
    objects: dict[str, JsonObject],
    locator: Any,
) -> tuple[ET.Element, ET.Element, JsonObject]:
    if not isinstance(locator, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target locator is invalid.",
        )
    object_id = locator.get("object_id")
    item = objects.get(object_id) if isinstance(object_id, str) else None
    if item is None or item.get("expected_fingerprint") != locator.get(
        "expected_fingerprint"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_fingerprint_mismatch",
            message="A mutation target no longer matches its snapshot fingerprint.",
        )
    part = item.get("part")
    paragraph_index = item.get("paragraph_index")
    root = roots.get(part) if isinstance(part, str) else None
    if root is None or not isinstance(paragraph_index, int):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target cannot be located in the DOCX package.",
        )
    paragraphs = list(root.iter(f"{_W}p"))
    if not 0 <= paragraph_index < len(paragraphs):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target paragraph no longer exists.",
        )
    paragraph = paragraphs[paragraph_index]
    if item.get("kind") == "paragraph":
        return paragraph, paragraph, item
    run_index = item.get("run_index")
    runs = list(paragraph.iter(f"{_W}r"))
    if item.get("kind") != "run" or not isinstance(run_index, int) or not 0 <= run_index < len(
        runs
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target run no longer exists.",
        )
    return paragraph, runs[run_index], item


def _parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    return next((item for item in root.iter() if target in list(item)), None)


def _inside_control(paragraph: ET.Element, target: ET.Element) -> bool:
    current = target
    while current is not paragraph:
        parent = _parent(paragraph, current)
        if parent is None:
            return False
        if parent.tag == f"{_W}sdt":
            return True
        current = parent
    return False


def _materialize(
    paragraph: ET.Element,
    target: ET.Element,
    operation: JsonObject,
) -> None:
    if (
        target is paragraph and paragraph.find(f".//{_W}sdt") is not None
    ) or _inside_control(paragraph, target):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="slot_id_not_unique",
            message="The materialize target already contains a content control.",
        )
    slot_id = operation["slot_id"]
    field_id = operation["field_id"]
    sdt = ET.Element(f"{_W}sdt")
    properties = ET.SubElement(sdt, f"{_W}sdtPr")
    ET.SubElement(properties, f"{_W}alias", {f"{_W}val": field_id})
    ET.SubElement(properties, f"{_W}tag", {f"{_W}val": slot_id})
    internal_id = int(sha256_json({"slot_id": slot_id})[:7], 16)
    ET.SubElement(properties, f"{_W}id", {f"{_W}val": str(internal_id)})
    ET.SubElement(properties, f"{_W}text")
    content = ET.SubElement(sdt, f"{_W}sdtContent")
    if target is paragraph:
        for child in list(paragraph):
            if child.tag == f"{_W}pPr":
                continue
            paragraph.remove(child)
            content.append(child)
        paragraph.append(sdt)
        return
    parent = _parent(paragraph, target)
    if parent is None:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="A mutation target run cannot be attached to its container.",
        )
    position = list(parent).index(target)
    parent.remove(target)
    content.append(target)
    parent.insert(position, sdt)


def _remove_content(
    paragraph: ET.Element,
    target_element: ET.Element,
    operation: JsonObject,
) -> None:
    targets = operation.get("migration_targets")
    slot_id = None
    if isinstance(targets, list) and targets and isinstance(targets[0], dict):
        slot_id = targets[0].get("slot_id")
    target = target_element
    if target_element is paragraph:
        candidates: list[ET.Element] = []
        for control in paragraph.iter(f"{_W}sdt"):
            tag = control.find(f"{_W}sdtPr/{_W}tag")
            if slot_id is None or (tag is not None and tag.get(f"{_W}val") == slot_id):
                candidates.append(control)
        if len(candidates) > 1:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="target_ambiguous",
                message="The remove target resolves to multiple content controls.",
            )
        target = candidates[0] if candidates else paragraph
    text_nodes = list(target.iter(f"{_W}t"))
    if not text_nodes:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_not_found",
            message="The remove target contains no visible text.",
        )
    for text in text_nodes:
        text.text = None


def _write_mutated_package(
    source: Path,
    temporary: Path,
    *,
    snapshot: JsonObject,
    operations: list[JsonObject],
) -> list[JsonObject]:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    object_list = snapshot.get("objects")
    if not isinstance(object_list, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="evidence_invalid",
            message="The mutation snapshot has no valid object inventory.",
        )
    objects: dict[str, JsonObject] = {}
    for item in object_list:
        if isinstance(item, dict) and isinstance(item.get("object_id"), str):
            objects[item["object_id"]] = item
    needed_parts: set[str] = set()
    for operation in operations:
        locator = operation.get("execution_locator")
        object_id = locator.get("object_id") if isinstance(locator, dict) else None
        item = objects.get(object_id) if isinstance(object_id, str) else None
        part = item.get("part") if isinstance(item, dict) else None
        if isinstance(part, str):
            needed_parts.add(part)
    try:
        roots: dict[str, ET.Element] = {
            part: ET.fromstring(parts[part]) for part in needed_parts
        }
    except (KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="document",
            code="target_not_found",
            message="A mutation target OOXML part cannot be parsed.",
        ) from error
    results: list[JsonObject] = []
    for index, operation in enumerate(operations):
        paragraph, target_element, _ = _target(
            roots,
            objects,
            operation.get("execution_locator"),
        )
        action = operation.get("operation")
        if action == "materialize_slot":
            _materialize(paragraph, target_element, operation)
        elif action == "remove_content":
            _remove_content(paragraph, target_element, operation)
        else:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="unsupported_operation",
                message="The mutation plan contains an unsupported operation.",
            )
        results.append(
            {
                "index": index,
                "operation_id": operation.get("operation_id"),
                "operation": action,
                "result": "applied",
            }
        )
    for part, root in roots.items():
        parts[part] = _serialize(root)
    with zipfile.ZipFile(temporary, "w") as output:
        for info in infos:
            output.writestr(info, parts[info.filename])
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    return results
