"""Direct object-level DOCX mutations used by the template workspace.

The Agent never sees an OOXML locator or an intermediate mutation plan.  This
module resolves the already-validated OfficeCLI object selected by the Agent
and performs the one package operation that OfficeCLI cannot express today:
wrapping an existing run/paragraph in a content control while preserving its
formatting.
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from docfit.tools.inspection import InspectedObject
from docfit.tools.runtime import ToolFailure, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
_W = f"{{{W_NS}}}"
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
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}
for _prefix, _uri in _KNOWN_NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)

_SEGMENT = re.compile(r"^(?P<name>[A-Za-z]+)\[(?P<selector>.+)]$")
_ATTRIBUTE = re.compile(r"^@(?P<name>[A-Za-z0-9]+)=(?P<value>.+)$")


@dataclass(frozen=True)
class ObjectMutation:
    """One already-resolved operation in an atomic page-sized edit batch."""

    selected: InspectedObject
    action: str
    field_id: str | None = None
    slot_id: str | None = None
    content_type: str = "text"
    placeholder_text: str | None = None


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
        declarations = b"".join(f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing)
        payload = payload[:root_end] + declarations + payload[root_end:]
    return cast(bytes, payload)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attribute_value(element: ET.Element, name: str) -> str | None:
    return next(
        (
            value
            for key, value in element.attrib.items()
            if _local_name(key).casefold() == name.casefold()
        ),
        None,
    )


def _selected_child(parent: ET.Element, segment: str) -> ET.Element:
    if segment == "body":
        values = [child for child in parent if _local_name(child.tag) == "body"]
        if len(values) == 1:
            return values[0]
        raise _target_not_found()
    match = _SEGMENT.fullmatch(segment)
    if match is None:
        raise _target_not_found()
    name = match.group("name")
    candidates = [child for child in parent if _local_name(child.tag) == name]
    selector = match.group("selector")
    if selector.isdigit():
        index = int(selector) - 1
        if 0 <= index < len(candidates):
            return candidates[index]
        raise _target_not_found()
    attribute = _ATTRIBUTE.fullmatch(selector)
    if attribute is not None:
        attribute_name = attribute.group("name")
        attribute_value = attribute.group("value")

        def matches_attribute(child: ET.Element) -> bool:
            if _attribute_value(child, attribute_name) == attribute_value:
                return True
            if name == "sdt" and attribute_name.casefold() == "sdtid":
                identifier = child.find(f"{_W}sdtPr/{_W}id")
                return (
                    identifier is not None
                    and _attribute_value(identifier, "val") == attribute_value
                )
            return False

        found = [child for child in candidates if matches_attribute(child)]
        if len(found) == 1:
            return found[0]
    raise _target_not_found()


def _resolve(root: ET.Element, locator: str) -> tuple[ET.Element, ET.Element]:
    current = root
    parent = root
    for segment in (value for value in locator.split("/") if value):
        parent = current
        current = _selected_child(current, segment)
    return parent, current


def _target_not_found() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="document",
        code="target_not_found",
        message="The selected object can no longer be resolved in the current Word document.",
        suggested_actions=("view_current_object_again",),
    )


def _inside_content_control(root: ET.Element, target: ET.Element) -> bool:
    current = target
    while current is not root:
        parent = next((item for item in root.iter() if current in list(item)), None)
        if parent is None:
            return False
        if _local_name(parent.tag) == "sdt":
            return True
        current = parent
    return False


def _clear_visible_text(target: ET.Element) -> None:
    for node in target.iter(f"{_W}t"):
        node.text = None


def _clear_content(
    parent: ET.Element,
    target: ET.Element,
    selected: InspectedObject,
) -> None:
    """Clear one object while preserving a generated field's control structure.

    TOC result rows are cached display content.  Clearing only ``w:t`` leaves
    their leader tabs and one empty paragraph per historical row, so the page
    still looks populated.  Rows without a field boundary can be removed in
    full; boundary rows retain their field characters/instruction while tabs
    and visible text are cleared.
    """

    is_toc_result = bool(
        selected.kind == "paragraph"
        and selected.style
        and selected.style.casefold().startswith("toc")
    )
    if not is_toc_result:
        _clear_visible_text(target)
        return
    field_nodes = list(target.iter(f"{_W}fldChar")) + list(
        target.iter(f"{_W}instrText")
    )
    if not field_nodes:
        parent.remove(target)
        return
    _clear_visible_text(target)
    for container in target.iter():
        for child in list(container):
            if child.tag in {f"{_W}tab", f"{_W}ptab"}:
                container.remove(child)


def _set_visible_text(target: ET.Element, value: str) -> None:
    """Replace visible text while retaining the selected object's run formatting."""

    text_nodes = list(target.iter(f"{_W}t"))
    if text_nodes:
        text_nodes[0].text = value
        text_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for node in text_nodes[1:]:
            node.text = None
        return
    run = next(target.iter(f"{_W}r"), None)
    if run is None:
        run = ET.SubElement(target, f"{_W}r")
    text = ET.SubElement(run, f"{_W}t")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value


def _materialize(
    document_root: ET.Element,
    target_parent: ET.Element,
    target: ET.Element,
    *,
    selected: InspectedObject,
    field_id: str,
    slot_id: str,
    content_type: str,
    placeholder_text: str,
) -> None:
    if selected.kind not in {"paragraph", "run"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="slot_target_not_text_container",
            message="A fillable slot target must be a paragraph or run object.",
        )
    if _inside_content_control(document_root, target):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_already_fillable",
            message="The selected object is already inside a content control.",
        )
    sdt = ET.Element(f"{_W}sdt")
    properties = ET.SubElement(sdt, f"{_W}sdtPr")
    ET.SubElement(properties, f"{_W}alias", {f"{_W}val": field_id})
    ET.SubElement(properties, f"{_W}tag", {f"{_W}val": slot_id})
    internal_id = int(sha256_json({"slot_id": slot_id})[:7], 16)
    ET.SubElement(properties, f"{_W}id", {f"{_W}val": str(internal_id)})
    # Rich-text controls are represented by the absence of w:text in OOXML;
    # plain-text controls opt in explicitly.
    if content_type not in {"rich_text", "section"}:
        ET.SubElement(properties, f"{_W}text")
    content = ET.SubElement(sdt, f"{_W}sdtContent")

    if selected.kind == "paragraph":
        for child in list(target):
            if child.tag == f"{_W}pPr":
                continue
            target.remove(child)
            content.append(child)
        _set_visible_text(content, placeholder_text)
        target.append(sdt)
        return

    position = list(target_parent).index(target)
    target_parent.remove(target)
    content.append(target)
    _set_visible_text(content, placeholder_text)
    target_parent.insert(position, sdt)


def _overlap(first: ET.Element, second: ET.Element) -> bool:
    return first is second or second in set(first.iter()) or first in set(second.iter())


def mutate_objects(
    source: Path,
    output: Path,
    *,
    mutations: list[ObjectMutation],
) -> None:
    """Apply one atomic batch against object refs from the same immutable version."""

    if not mutations:
        raise AssertionError("at least one object mutation is required")

    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    try:
        document_root = ET.fromstring(parts["word/document.xml"])
    except (KeyError, ET.ParseError) as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="document_xml_invalid",
            message="The Word document main part cannot be parsed.",
        ) from error
    resolved = [
        (*_resolve(document_root, mutation.selected.locator), mutation)
        for mutation in mutations
    ]
    for index, (_, target, _) in enumerate(resolved):
        if any(_overlap(target, other) for _, other, _ in resolved[index + 1 :]):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="batch_targets_overlap",
                message=(
                    "A batch cannot modify both an object and one of its descendants; "
                    "choose the smallest intended targets."
                ),
            )
    for parent, target, mutation in resolved:
        if mutation.action == "materialize_slot":
            if mutation.field_id is None or mutation.slot_id is None:
                raise AssertionError("materialize_slot requires field and slot identifiers")
            _materialize(
                document_root,
                parent,
                target,
                selected=mutation.selected,
                field_id=mutation.field_id,
                slot_id=mutation.slot_id,
                content_type=mutation.content_type,
                placeholder_text=mutation.placeholder_text
                or f"【{mutation.field_id}】",
            )
        elif mutation.action == "clear_content":
            if not mutation.selected.text:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="object_has_no_visible_content",
                    message="The selected object has no visible content to clear.",
                )
            _clear_content(parent, target, mutation.selected)
        elif mutation.action == "remove_object":
            parent.remove(target)
        else:
            raise AssertionError(f"unsupported direct object action: {mutation.action}")
    parts["word/document.xml"] = _serialize(document_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as result:
        for info in infos:
            result.writestr(info, parts[info.filename])
    with output.open("rb") as handle:
        os.fsync(handle.fileno())
