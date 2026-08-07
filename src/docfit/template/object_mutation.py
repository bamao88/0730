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
from copy import deepcopy
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
    clear_direct_format: tuple[str, ...] = ()
    structure_members: tuple[StructureMember, ...] = ()
    replaced_structure: InspectedObject | None = None
    toc_entries: tuple[TocEntry, ...] = ()


@dataclass(frozen=True)
class StructureMember:
    """One Agent-classified object inside a reusable body structure."""

    selected: InspectedObject
    field_id: str
    slot_id: str
    content_type: str
    placeholder_text: str
    clear_direct_format: tuple[str, ...] = ()


@dataclass(frozen=True)
class TocEntry:
    """One representative live-TOC cache entry chosen from the final title tree."""

    selected: InspectedObject
    level: int


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
    _parent: ET.Element,
    target: ET.Element,
    _selected: InspectedObject,
) -> None:
    """Clear visible text in a non-generated object while preserving its container."""

    _clear_visible_text(target)


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


def _remove_direct_format(target: ET.Element, properties: tuple[str, ...]) -> None:
    """Remove only Agent-selected direct formatting, leaving school styles intact."""

    unsupported = set(properties) - {"color"}
    if unsupported:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="direct_format_property_invalid",
            message="Only direct color normalization is currently supported.",
        )
    if "color" not in properties:
        return
    for parent in target.iter():
        for child in list(parent):
            if child.tag == f"{_W}color":
                parent.remove(child)


def _sdt(
    *,
    field_id: str,
    slot_id: str,
    content_type: str,
) -> tuple[ET.Element, ET.Element]:
    control = ET.Element(f"{_W}sdt")
    properties = ET.SubElement(control, f"{_W}sdtPr")
    ET.SubElement(properties, f"{_W}alias", {f"{_W}val": field_id})
    ET.SubElement(properties, f"{_W}tag", {f"{_W}val": slot_id})
    internal_id = int(sha256_json({"slot_id": slot_id})[:7], 16)
    ET.SubElement(properties, f"{_W}id", {f"{_W}val": str(internal_id)})
    # Brackets in visible content are the whole placeholder protocol.  In
    # particular, do not add w:showingPlcHdr or placeholder-specific shading.
    if content_type not in {"rich_text", "section"}:
        ET.SubElement(properties, f"{_W}text")
    return control, ET.SubElement(control, f"{_W}sdtContent")


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
    sdt, content = _sdt(
        field_id=field_id,
        slot_id=slot_id,
        content_type=content_type,
    )

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


def _materialize_structure(
    document_root: ET.Element,
    members: list[tuple[ET.Element, ET.Element, StructureMember]],
    *,
    field_id: str,
    slot_id: str,
    replaced_structure: tuple[ET.Element, ET.Element] | None = None,
) -> None:
    """Turn one representative contiguous school section into a reusable structure.

    When the Agent later discovers a better representative block, replace the
    earlier structure atomically.  The Tool only performs the requested
    replacement; deciding that the newer block is semantically better remains
    the Agent's responsibility.
    """

    if not members:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_members_missing",
            message="A body structure requires at least one representative member.",
        )
    parents = {id(parent): parent for parent, _, _ in members}
    if len(parents) != 1:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_not_one_block",
            message="Body structure members must be sibling objects from one school section.",
        )
    parent = next(iter(parents.values()))
    targets = [target for _, target, _ in members]
    indices = [list(parent).index(target) for target in targets]
    if indices != sorted(indices) or indices != list(range(indices[0], indices[0] + len(indices))):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_not_contiguous",
            message=(
                "Body structure members must be supplied in document order without gaps; "
                "include every school object that belongs to this representative block."
            ),
        )
    if any(member.selected.kind not in {"paragraph", "table"} for _, _, member in members):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_member_not_block",
            message="Select paragraph or table containers for a reusable body structure.",
        )
    if any(_inside_content_control(document_root, target) for target in targets):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="target_already_fillable",
            message="A selected body member is already inside a content control.",
        )

    if replaced_structure is not None:
        replaced_parent, replaced_target = replaced_structure
        replaced_parent.remove(replaced_target)

    for _, target, member in members:
        _remove_direct_format(target, member.clear_direct_format)
        if member.selected.kind == "paragraph":
            _materialize(
                document_root,
                parent,
                target,
                selected=member.selected,
                field_id=member.field_id,
                slot_id=member.slot_id,
                content_type=member.content_type,
                placeholder_text=member.placeholder_text,
            )
        else:
            # Tables remain structurally intact; the outer and member controls
            # make the sample addressable without inventing a replacement table.
            control, content = _sdt(
                field_id=member.field_id,
                slot_id=member.slot_id,
                content_type=member.content_type,
            )
            position = list(parent).index(target)
            parent.remove(target)
            content.append(target)
            parent.insert(position, control)
            targets[targets.index(target)] = control

    # Paragraph materialization nests its member control inside the paragraph;
    # table materialization replaces the table with a member control.
    current_blocks: list[ET.Element] = []
    for original, (_, _, member) in zip(targets, members, strict=True):
        if member.selected.kind == "table" and _local_name(original.tag) == "sdt":
            current_blocks.append(original)
        else:
            current_blocks.append(original)
    outer, content = _sdt(field_id=field_id, slot_id=slot_id, content_type="section")
    first_position = min(list(parent).index(block) for block in current_blocks)
    for block in current_blocks:
        parent.remove(block)
        content.append(block)
    parent.insert(first_position, outer)


def _toc_style_ids(parts: dict[str, bytes]) -> dict[int, str]:
    raw = parts.get("word/styles.xml")
    if raw is None:
        return {}
    try:
        styles = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="styles_xml_invalid",
            message="The Word styles part cannot be parsed.",
        ) from error
    result: dict[int, str] = {}
    for style in styles.findall(f"{_W}style"):
        style_id = style.get(f"{_W}styleId")
        name = style.find(f"{_W}name")
        style_name = name.get(f"{_W}val", "") if name is not None else ""
        match = re.fullmatch(r"toc\s*([1-3])", style_name, re.IGNORECASE)
        if match is not None and style_id:
            result[int(match.group(1))] = style_id
    return result


def _toc_level(
    paragraph: ET.Element,
    style_levels: dict[str, int],
) -> int | None:
    style = paragraph.find(f"{_W}pPr/{_W}pStyle")
    value = style.get(f"{_W}val", "") if style is not None else ""
    if value in style_levels:
        return style_levels[value]
    match = re.search(r"([1-9])$", value)
    return int(match.group(1)) if match else None


def _toc_paragraph(
    template: ET.Element,
    text: str,
    *,
    level: int,
    style_id: str,
    instruction_text: str,
    first: bool,
    last: bool,
) -> ET.Element:
    paragraph = ET.Element(f"{_W}p")
    properties = template.find(f"{_W}pPr")
    if properties is not None:
        properties = deepcopy(properties)
        paragraph.append(properties)
    else:
        properties = ET.SubElement(paragraph, f"{_W}pPr")
    paragraph_style = properties.find(f"{_W}pStyle")
    if paragraph_style is None:
        paragraph_style = ET.Element(f"{_W}pStyle")
        properties.insert(0, paragraph_style)
    paragraph_style.set(f"{_W}val", style_id)
    if first:
        begin_run = ET.SubElement(paragraph, f"{_W}r")
        ET.SubElement(
            begin_run,
            f"{_W}fldChar",
            {f"{_W}fldCharType": "begin", f"{_W}dirty": "true"},
        )
        instruction_run = ET.SubElement(paragraph, f"{_W}r")
        instruction = ET.SubElement(instruction_run, f"{_W}instrText")
        instruction.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instruction.text = instruction_text
        separate_run = ET.SubElement(paragraph, f"{_W}r")
        ET.SubElement(
            separate_run,
            f"{_W}fldChar",
            {f"{_W}fldCharType": "separate"},
        )
    text_run = ET.SubElement(paragraph, f"{_W}r")
    template_run_properties = next(
        (
            properties
            for run in template.iter(f"{_W}r")
            if run.find(f"{_W}t") is not None and (properties := run.find(f"{_W}rPr")) is not None
        ),
        None,
    )
    if template_run_properties is not None:
        text_run.append(deepcopy(template_run_properties))
    ET.SubElement(text_run, f"{_W}t").text = text
    ET.SubElement(text_run, f"{_W}tab")
    ET.SubElement(text_run, f"{_W}t").text = "1"
    if last:
        end_run = ET.SubElement(paragraph, f"{_W}r")
        ET.SubElement(end_run, f"{_W}fldChar", {f"{_W}fldCharType": "end"})
    return paragraph


def _refresh_toc(
    parent: ET.Element,
    target: ET.Element,
    entries: tuple[TocEntry, ...],
    style_ids: dict[int, str],
) -> None:
    """Rebuild a representative cache while keeping a live, dirty TOC field."""

    if not entries:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="toc_entries_missing",
            message="refresh_toc requires representative entries from the final title tree.",
        )
    siblings = list(parent)
    start = siblings.index(target)
    end = next(
        (
            index
            for index in range(start, len(siblings))
            if any(
                node.get(f"{_W}fldCharType") == "end"
                for node in siblings[index].iter(f"{_W}fldChar")
            )
        ),
        None,
    )
    if end is None:
        raise ToolFailure(
            status="needs_input",
            origin="document",
            code="toc_field_boundary_missing",
            message="The selected object does not begin a complete TOC field result.",
        )
    templates: dict[int, ET.Element] = {}
    style_levels = {style_id: level for level, style_id in style_ids.items()}
    for paragraph in siblings[start : end + 1]:
        level = _toc_level(paragraph, style_levels)
        if level is not None:
            templates.setdefault(level, paragraph)
    fallback = siblings[start]
    instruction_text = "".join(
        node.text or ""
        for paragraph in siblings[start : end + 1]
        for node in paragraph.iter(f"{_W}instrText")
    )
    if "TOC" not in instruction_text.upper():
        instruction_text = ' TOC \\o "1-3" \\h \\z \\u '
    replacements = [
        _toc_paragraph(
            templates.get(entry.level, fallback),
            entry.selected.text,
            level=entry.level,
            style_id=style_ids.get(entry.level, f"TOC{entry.level}"),
            instruction_text=instruction_text,
            first=index == 0,
            last=index == len(entries) - 1,
        )
        for index, entry in enumerate(entries)
    ]
    following_content = next(
        (
            paragraph
            for paragraph in siblings[end + 1 :]
            if _local_name(paragraph.tag) == "p"
            and any((node.text or "").strip() for node in paragraph.iter(f"{_W}t"))
        ),
        None,
    )
    if following_content is not None:
        properties = following_content.find(f"{_W}pPr")
        if properties is None:
            properties = ET.Element(f"{_W}pPr")
            following_content.insert(0, properties)
        page_break = properties.find(f"{_W}pageBreakBefore")
        if page_break is None:
            page_break = ET.Element(f"{_W}pageBreakBefore")
            preceding = {"pStyle", "keepNext", "keepLines"}
            insertion = next(
                (
                    index
                    for index, child in enumerate(properties)
                    if _local_name(child.tag) not in preceding
                ),
                len(properties),
            )
            properties.insert(insertion, page_break)
    for paragraph in siblings[start : end + 1]:
        parent.remove(paragraph)
    for offset, paragraph in enumerate(replacements):
        parent.insert(start + offset, paragraph)


def _mark_word_fields_for_update(parts: dict[str, bytes]) -> None:
    raw = parts.get("word/settings.xml")
    if raw is None:
        return
    try:
        settings = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="settings_xml_invalid",
            message="The Word settings part cannot be parsed.",
        ) from error
    update = settings.find(f"{_W}updateFields")
    if update is None:
        update = ET.Element(f"{_W}updateFields")
        following_settings = {
            "hdrShapeDefaults",
            "footnotePr",
            "endnotePr",
            "compat",
            "docVars",
            "rsids",
            "mathPr",
            "themeFontLang",
            "clrSchemeMapping",
            "doNotIncludeSubdocsInStats",
            "shapeDefaults",
            "decimalSymbol",
            "listSeparator",
            "docId",
        }
        insertion = next(
            (
                index
                for index, child in enumerate(settings)
                if _local_name(child.tag) in following_settings
            ),
            len(settings),
        )
        settings.insert(insertion, update)
    update.set(f"{_W}val", "true")
    parts["word/settings.xml"] = _serialize(settings)


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
        (*_resolve(document_root, mutation.selected.locator), mutation) for mutation in mutations
    ]
    structure_resolved: dict[int, list[tuple[ET.Element, ET.Element, StructureMember]]] = {
        index: [
            (*_resolve(document_root, member.selected.locator), member)
            for member in mutation.structure_members
        ]
        for index, mutation in enumerate(mutations)
        if mutation.action == "materialize_structure"
    }
    replaced_structures: dict[int, tuple[ET.Element, ET.Element]] = {
        index: _resolve(document_root, mutation.replaced_structure.locator)
        for index, mutation in enumerate(mutations)
        if mutation.action == "materialize_structure" and mutation.replaced_structure is not None
    }
    mutable_targets: list[ET.Element] = []
    for index, (_, target, mutation) in enumerate(resolved):
        if mutation.action == "materialize_structure":
            mutable_targets.extend(item for _, item, _ in structure_resolved[index])
            replacement = replaced_structures.get(index)
            if replacement is not None:
                mutable_targets.append(replacement[1])
        else:
            mutable_targets.append(target)
    for index, target in enumerate(mutable_targets):
        if any(_overlap(target, other) for other in mutable_targets[index + 1 :]):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="batch_targets_overlap",
                message=(
                    "A batch cannot modify both an object and one of its descendants; "
                    "choose the smallest intended targets."
                ),
            )
    refreshed_toc = False
    toc_style_ids = _toc_style_ids(parts)
    for index, (parent, target, mutation) in enumerate(resolved):
        if mutation.action == "materialize_slot":
            if mutation.field_id is None or mutation.slot_id is None:
                raise AssertionError("materialize_slot requires field and slot identifiers")
            _remove_direct_format(target, mutation.clear_direct_format)
            _materialize(
                document_root,
                parent,
                target,
                selected=mutation.selected,
                field_id=mutation.field_id,
                slot_id=mutation.slot_id,
                content_type=mutation.content_type,
                placeholder_text=mutation.placeholder_text or f"【{mutation.field_id}】",
            )
        elif mutation.action == "materialize_structure":
            if mutation.field_id is None or mutation.slot_id is None:
                raise AssertionError("materialize_structure requires field and slot identifiers")
            _materialize_structure(
                document_root,
                structure_resolved[index],
                field_id=mutation.field_id,
                slot_id=mutation.slot_id,
                replaced_structure=replaced_structures.get(index),
            )
        elif mutation.action == "normalize_format":
            _remove_direct_format(target, mutation.clear_direct_format)
        elif mutation.action == "refresh_toc":
            _refresh_toc(parent, target, mutation.toc_entries, toc_style_ids)
            refreshed_toc = True
        elif mutation.action == "clear_content":
            if mutation.selected.style and mutation.selected.style.casefold().startswith("toc"):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="toc_requires_refresh",
                    message=(
                        "Do not clear TOC cache rows individually. Refresh the live TOC "
                        "with representative final-title entries."
                    ),
                )
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
    if refreshed_toc:
        _mark_word_fields_for_update(parts)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as result:
        for info in infos:
            result.writestr(info, parts[info.filename])
    with output.open("rb") as handle:
        os.fsync(handle.fileno())
