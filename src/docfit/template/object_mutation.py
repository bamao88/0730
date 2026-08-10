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
import unicodedata
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from docfit.tools.inspection import InspectedObject
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

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
    effective_format: tuple[tuple[str, str], ...] = ()
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
    effective_format: tuple[tuple[str, str], ...] = ()


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
    if not candidates and _local_name(parent.tag) == "sdt":
        # OfficeCLI object locators deliberately flatten the OOXML-only
        # sdtContent container. Keep mutation resolution on that same public
        # abstraction so an Agent never has to manufacture hidden XML paths.
        content = parent.find(f"{_W}sdtContent")
        if content is not None:
            candidates = [child for child in content if _local_name(child.tag) == name]
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
        selected = _selected_child(current, segment)
        parent = next(
            (container for container in current.iter() if selected in list(container)),
            current,
        )
        current = selected
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


def _display_width_units(value: str) -> int:
    """Estimate the source run's East-Asian inline width without using len()."""

    return sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1 for character in value
    )


def _placeholder_preserving_underlined_fill(
    target: ET.Element,
    *,
    source_text: str,
    placeholder_text: str,
) -> str:
    """Keep an underlined blank run's source width budget after slot materialization.

    Many school covers draw fill lines by underlining preserved spaces. Replacing
    the complete run with a short placeholder keeps ``w:u`` but destroys that
    visible template geometry. Keep the unused source width as trailing spaces;
    the changed-region render remains the final authority for proportional fonts.
    """

    if source_text.strip() or target.find(f"{_W}rPr/{_W}u") is None:
        return placeholder_text
    remaining = max(
        0,
        _display_width_units(source_text) - _display_width_units(placeholder_text),
    )
    return f"{placeholder_text}{' ' * remaining}"


def _apply_run_outcomes(properties: ET.Element, outcomes: dict[str, str]) -> None:
    if outcomes.get("color") == "black":
        color = properties.find(f"{_W}color")
        if color is None:
            color = ET.SubElement(properties, f"{_W}color")
        color.attrib.clear()
        color.set(f"{_W}val", "000000")
    if outcomes.get("underline") == "none":
        underline = properties.find(f"{_W}u")
        if underline is None:
            underline = ET.SubElement(properties, f"{_W}u")
        underline.attrib.clear()
        underline.set(f"{_W}val", "none")
    properties[:] = _ordered_children(list(properties), _RPR_ORDER)


def _apply_effective_format(
    target: ET.Element,
    effective_format: tuple[tuple[str, str], ...],
) -> None:
    """Write the smallest direct override that guarantees the requested visible result."""

    outcomes = dict(effective_format)
    if not outcomes:
        return
    if set(outcomes) - {"color", "underline"}:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="effective_format_invalid",
            message="Only effective color and underline outcomes are currently supported.",
        )
    runs = [target] if _local_name(target.tag) == "r" else list(target.iter(f"{_W}r"))
    for run in runs:
        properties = run.find(f"{_W}rPr")
        if properties is None:
            properties = ET.Element(f"{_W}rPr")
            run.insert(0, properties)
        _apply_run_outcomes(properties, outcomes)
    if _local_name(target.tag) == "p":
        paragraph_properties = target.find(f"{_W}pPr")
        if paragraph_properties is None:
            paragraph_properties = ET.Element(f"{_W}pPr")
            target.insert(0, paragraph_properties)
        run_properties = paragraph_properties.find(f"{_W}rPr")
        if run_properties is None:
            run_properties = ET.SubElement(paragraph_properties, f"{_W}rPr")
        _apply_run_outcomes(run_properties, outcomes)
        paragraph_properties[:] = _ordered_children(list(paragraph_properties), _PPR_ORDER)


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
    visible_placeholder = _placeholder_preserving_underlined_fill(
        target,
        source_text=selected.text,
        placeholder_text=placeholder_text,
    )
    _set_visible_text(content, visible_placeholder)
    target_parent.insert(position, sdt)


def _remove_object_preserving_boundary(
    parent: ET.Element,
    target: ET.Element,
) -> list[str]:
    """Remove visible content while retaining any Word-owned structural boundary."""

    kinds: list[str] = []
    if target.find(f"{_W}pPr/{_W}sectPr") is not None:
        kinds.append("section_boundary")
    if target.find(f"{_W}pPr/{_W}pageBreakBefore") is not None:
        kinds.append("page_break_before")
    if any(node.get(f"{_W}type", "page") == "page" for node in target.iter(f"{_W}br")):
        kinds.append("explicit_page_break")
    for tag, kind in (
        ("bookmarkStart", "bookmark_range"),
        ("bookmarkEnd", "bookmark_range"),
        ("commentRangeStart", "comment_range"),
        ("commentRangeEnd", "comment_range"),
        ("commentReference", "comment_reference"),
        ("footnoteReference", "footnote_reference"),
        ("endnoteReference", "endnote_reference"),
        ("fldChar", "field_boundary"),
        ("instrText", "field_boundary"),
        ("drawing", "drawing_anchor"),
        ("object", "drawing_anchor"),
        ("pict", "drawing_anchor"),
    ):
        if next(target.iter(f"{_W}{tag}"), None) is not None:
            kinds.append(kind)
    if _local_name(target.tag) == "p":
        siblings = list(parent)
        position = siblings.index(target)
        if (position > 0 and _local_name(siblings[position - 1].tag) == "tbl") or (
            _local_name(parent.tag) == "tc" and position == len(siblings) - 1
        ):
            kinds.append("table_wrapper_paragraph")
    kinds = list(dict.fromkeys(kinds))
    if kinds:
        for node in target.iter():
            if _local_name(node.tag) in {"t", "delText"}:
                node.text = ""
        return kinds
    parent.remove(target)
    return []


def _ensure_page_start(parent: ET.Element, target: ET.Element) -> tuple[bool, str]:
    if _local_name(target.tag) != "p":
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="page_start_target_invalid",
            message="ensure_page_start requires a paragraph object.",
        )
    if target.find(f"{_W}pPr/{_W}pageBreakBefore") is not None:
        return False, "page_break_before"
    siblings = list(parent)
    position = siblings.index(target)
    for previous in reversed(siblings[:position]):
        if any(node.get(f"{_W}type", "page") == "page" for node in previous.iter(f"{_W}br")):
            return False, "preceding_explicit_page_break"
        section = previous.find(f"{_W}pPr/{_W}sectPr")
        section_type = section.find(f"{_W}type") if section is not None else None
        if section is not None and (
            section_type is None
            or section_type.get(f"{_W}val", "nextPage") in {"nextPage", "oddPage", "evenPage"}
        ):
            return False, "preceding_section_boundary"
        if any((node.text or "").strip() for node in previous.iter(f"{_W}t")):
            break
    properties = target.find(f"{_W}pPr")
    if properties is None:
        properties = ET.Element(f"{_W}pPr")
        target.insert(0, properties)
    page_break = ET.Element(f"{_W}pageBreakBefore")
    properties.append(page_break)
    properties[:] = _ordered_children(list(properties), _PPR_ORDER)
    return True, "page_break_before"


def _paragraph_style_id(target: ET.Element) -> str | None:
    style = target.find(f"{_W}pPr/{_W}pStyle")
    return style.get(f"{_W}val") if style is not None else None


def _materialize_structure(
    document_root: ET.Element,
    members: list[tuple[ET.Element, ET.Element, StructureMember]],
    *,
    field_id: str,
    slot_id: str,
    replaced_structure: tuple[ET.Element, ET.Element] | None = None,
) -> None:
    """Extract ordered representative school objects into a reusable structure.

    When the Agent later discovers a better representative block, replace the
    earlier structure atomically.  The Tool only performs the requested
    replacement; deciding that the newer block is semantically better remains
    the Agent's responsibility.  Representative objects may have instruction or
    redundant sample objects between them: those unselected objects stay in the
    document for the Agent's later cleanup instead of becoming structure members.
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
    if len({id(target) for target in targets}) != len(targets):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_member_duplicate",
            message="Each representative body structure member must select a distinct object.",
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

    siblings = list(parent)
    indices = [siblings.index(target) for target in targets]
    if indices != sorted(indices):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="body_structure_not_in_document_order",
            message=(
                "Body structure members must be supplied in document order. They do not need "
                "to be adjacent; select the representative objects from one school block in "
                "their physical order."
            ),
        )
    first_position = indices[0]
    selected_ids = {id(target) for target in targets}
    layout_blocks = [
        block
        for block in siblings[indices[0] : indices[-1] + 1]
        if id(block) in selected_ids
        or (
            not "".join(node.text or "" for node in block.iter(f"{_W}t")).strip()
            and block.find(f"{_W}pPr/{_W}sectPr") is None
        )
    ]
    outer, content = _sdt(field_id=field_id, slot_id=slot_id, content_type="section")
    for block in layout_blocks:
        parent.remove(block)
        content.append(block)
    for _, target, member in members:
        _apply_effective_format(target, member.effective_format)
        if member.selected.kind == "paragraph":
            _materialize(
                document_root,
                content,
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
            control, member_content = _sdt(
                field_id=member.field_id,
                slot_id=member.slot_id,
                content_type=member.content_type,
            )
            outer_content = outer.find(f"{_W}sdtContent")
            assert outer_content is not None
            position = list(outer_content).index(target)
            outer_content.remove(target)
            member_content.append(target)
            outer_content.insert(position, control)
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


_PPR_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "pStyle",
            "keepNext",
            "keepLines",
            "pageBreakBefore",
            "framePr",
            "widowControl",
            "numPr",
            "suppressLineNumbers",
            "pBdr",
            "shd",
            "tabs",
            "suppressAutoHyphens",
            "kinsoku",
            "wordWrap",
            "overflowPunct",
            "topLinePunct",
            "autoSpaceDE",
            "autoSpaceDN",
            "bidi",
            "adjustRightInd",
            "snapToGrid",
            "spacing",
            "ind",
            "contextualSpacing",
            "mirrorIndents",
            "suppressOverlap",
            "jc",
            "textDirection",
            "textAlignment",
            "textboxTightWrap",
            "outlineLvl",
            "divId",
            "cnfStyle",
            "rPr",
            "sectPr",
            "pPrChange",
        )
    )
}
_RPR_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "rStyle",
            "rFonts",
            "b",
            "bCs",
            "i",
            "iCs",
            "caps",
            "smallCaps",
            "strike",
            "dstrike",
            "outline",
            "shadow",
            "emboss",
            "imprint",
            "noProof",
            "snapToGrid",
            "vanish",
            "webHidden",
            "color",
            "spacing",
            "w",
            "kern",
            "position",
            "sz",
            "szCs",
            "highlight",
            "u",
            "bdr",
            "shd",
            "fitText",
            "vertAlign",
            "rtl",
            "cs",
            "lang",
            "eastAsianLayout",
            "specVanish",
            "oMath",
        )
    )
}


def _ordered_children(
    values: list[ET.Element],
    order: dict[str, int],
) -> list[ET.Element]:
    return sorted(values, key=lambda item: order.get(_local_name(item.tag), len(order)))


def _style_chain(styles: ET.Element, style_id: str) -> list[ET.Element]:
    by_id = {style.get(f"{_W}styleId", ""): style for style in styles.findall(f"{_W}style")}
    result: list[ET.Element] = []
    seen: set[str] = set()

    def visit(current_id: str) -> None:
        if not current_id or current_id in seen:
            return
        seen.add(current_id)
        current = by_id.get(current_id)
        if current is None:
            return
        based_on = current.find(f"{_W}basedOn")
        if based_on is not None:
            visit(based_on.get(f"{_W}val", ""))
        result.append(current)

    visit(style_id)
    return result


def _first_visible_run_properties(paragraph: ET.Element) -> ET.Element | None:
    return next(
        (
            properties
            for run in paragraph.iter(f"{_W}r")
            if any((node.text or "").strip() for node in run.iter(f"{_W}t"))
            and (properties := run.find(f"{_W}rPr")) is not None
        ),
        None,
    )


def _stabilize_toc_styles(
    parts: dict[str, bytes],
    templates: dict[int, ET.Element],
    style_ids: dict[int, str],
    effective_format: tuple[tuple[str, str], ...],
) -> list[JsonObject]:
    """Flatten observed TOC result formatting into styles used on field update."""

    raw = parts.get("word/styles.xml")
    if raw is None:
        return []
    try:
        styles = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ToolFailure(
            status="error",
            origin="document",
            code="styles_xml_invalid",
            message="The Word styles part cannot be parsed.",
        ) from error
    default_run = styles.find(f"{_W}docDefaults/{_W}rPrDefault/{_W}rPr")
    by_id = {style.get(f"{_W}styleId", ""): style for style in styles.findall(f"{_W}style")}
    for level, style_id in style_ids.items():
        style = by_id.get(style_id)
        template = templates.get(level)
        if style is None or template is None:
            continue

        paragraph_properties = style.find(f"{_W}pPr")
        if paragraph_properties is None:
            paragraph_properties = ET.Element(f"{_W}pPr")
            run_properties_position = next(
                (index for index, child in enumerate(style) if child.tag == f"{_W}rPr"),
                len(style),
            )
            style.insert(run_properties_position, paragraph_properties)
        template_paragraph_properties = template.find(f"{_W}pPr")
        if template_paragraph_properties is not None:
            for name in ("tabs", "spacing", "ind"):
                if paragraph_properties.find(f"{_W}{name}") is not None:
                    continue
                source = template_paragraph_properties.find(f"{_W}{name}")
                if source is not None:
                    paragraph_properties.append(deepcopy(source))
        spacing = paragraph_properties.find(f"{_W}spacing")
        if spacing is not None:
            spacing.attrib.setdefault(f"{_W}before", "0")
            spacing.attrib.setdefault(f"{_W}after", "0")
        alignment = paragraph_properties.find(f"{_W}jc")
        if alignment is None:
            alignment = ET.SubElement(paragraph_properties, f"{_W}jc")
        alignment.set(f"{_W}val", "left")
        children = _ordered_children(list(paragraph_properties), _PPR_ORDER)
        paragraph_properties[:] = children

        merged: dict[str, ET.Element] = {}
        sources: list[ET.Element] = []
        if default_run is not None:
            sources.append(default_run)
        sources.extend(
            properties
            for item in _style_chain(styles, style_id)
            if (properties := item.find(f"{_W}rPr")) is not None
        )
        template_run = _first_visible_run_properties(template)
        if template_run is not None:
            sources.append(template_run)
        for source in sources:
            for child in source:
                name = _local_name(child.tag)
                if name not in {"rStyle", "rPrChange"}:
                    merged[name] = deepcopy(child)
        outcomes = dict(effective_format)
        if outcomes.get("color") == "black":
            merged["color"] = ET.Element(f"{_W}color", {f"{_W}val": "000000"})
        if outcomes.get("underline") == "none":
            merged["u"] = ET.Element(f"{_W}u", {f"{_W}val": "none"})
        for name in ("b", "bCs"):
            if name not in merged:
                merged[name] = ET.Element(f"{_W}{name}", {f"{_W}val": "0"})
        run_properties = style.find(f"{_W}rPr")
        if run_properties is None:
            run_properties = ET.SubElement(style, f"{_W}rPr")
        run_properties[:] = _ordered_children(list(merged.values()), _RPR_ORDER)

    # Word can recreate the Hyperlink character style when a TOC with the \h
    # switch is updated. If the current TOC cache already uses a character
    # style, normalize that exact style as the durable field-update fallback.
    character_style_ids = {
        value
        for template in templates.values()
        for run_properties in template.iter(f"{_W}rPr")
        if (run_style := run_properties.find(f"{_W}rStyle")) is not None
        and (value := run_style.get(f"{_W}val"))
    }
    style_scope_changes: list[JsonObject] = []
    for character_style_id in character_style_ids:
        character_style = by_id.get(character_style_id)
        if character_style is None:
            continue
        run_properties = character_style.find(f"{_W}rPr")
        if run_properties is None:
            run_properties = ET.SubElement(character_style, f"{_W}rPr")
        _apply_run_outcomes(run_properties, dict(effective_format))
        style_scope_changes.append(
            {
                "style_id": character_style_id,
                "scope": "document_character_style",
                "reason": "preserve_toc_effective_format_after_field_update",
            }
        )
    parts["word/styles.xml"] = _serialize(styles)
    return style_scope_changes


def _field_interval(
    siblings: list[ET.Element],
    selected_index: int,
) -> tuple[int, int]:
    """Resolve a live TOC from one cache row or its immediately preceding title."""

    def interval_from(start: int) -> tuple[int, int] | None:
        depth = 0
        for index in range(start, len(siblings)):
            for node in siblings[index].iter(f"{_W}fldChar"):
                kind = node.get(f"{_W}fldCharType")
                if kind == "begin":
                    depth += 1
                elif kind == "end" and depth:
                    depth -= 1
                    if depth == 0:
                        return start, index
        return None

    candidates = [
        index
        for index, paragraph in enumerate(siblings[: selected_index + 1])
        if "TOC" in "".join(node.text or "" for node in paragraph.iter(f"{_W}instrText")).upper()
        and any(node.get(f"{_W}fldCharType") == "begin" for node in paragraph.iter(f"{_W}fldChar"))
    ]
    for start in reversed(candidates):
        interval = interval_from(start)
        if interval is not None and selected_index <= interval[1]:
            return interval

    # The visible region is commonly anchored on the fixed “目录” title, while
    # the live field begins in the next non-empty paragraph. Resolve only that
    # structurally adjacent field; stop at any intervening visible content.
    for start in range(selected_index + 1, len(siblings)):
        paragraph = siblings[start]
        is_toc_start = "TOC" in "".join(
            node.text or "" for node in paragraph.iter(f"{_W}instrText")
        ).upper() and any(
            node.get(f"{_W}fldCharType") == "begin" for node in paragraph.iter(f"{_W}fldChar")
        )
        if is_toc_start:
            interval = interval_from(start)
            if interval is not None:
                return interval
            break
        if "".join(node.text or "" for node in paragraph.iter(f"{_W}t")).strip():
            break
    raise ToolFailure(
        status="needs_input",
        origin="document",
        code="toc_field_boundary_missing",
        message="The selected TOC cache row is not inside a complete live TOC field.",
    )


def _contains_toc_preserved_payload(node: ET.Element) -> bool:
    protected = {
        "bookmarkStart",
        "bookmarkEnd",
        "commentRangeStart",
        "commentRangeEnd",
        "commentReference",
        "footnoteReference",
        "endnoteReference",
        "drawing",
        "object",
        "pict",
    }
    return any(_local_name(item.tag) in protected for item in node.iter()) or any(
        _local_name(item.tag) == "br" and item.get(f"{_W}type", "page") == "page"
        for item in node.iter()
    )


def _toc_residual_paragraph(
    paragraph: ET.Element,
    *,
    start_paragraph: ET.Element,
    end_paragraph: ET.Element,
) -> ET.Element | None:
    """Keep non-field anchors and ranges sharing a TOC boundary paragraph."""

    children = list(paragraph)
    begin_index = next(
        (
            index
            for index, child in enumerate(children)
            if any(node.get(f"{_W}fldCharType") == "begin" for node in child.iter(f"{_W}fldChar"))
        ),
        None,
    )
    end_index = next(
        (
            index
            for index, child in enumerate(children)
            if any(node.get(f"{_W}fldCharType") == "end" for node in child.iter(f"{_W}fldChar"))
        ),
        None,
    )
    keep: list[ET.Element] = []
    for index, child in enumerate(children):
        if child.tag == f"{_W}pPr":
            continue
        outside_field = (
            paragraph is start_paragraph and begin_index is not None and index < begin_index
        ) or (paragraph is end_paragraph and end_index is not None and index > end_index)
        if outside_field or _contains_toc_preserved_payload(child):
            keep.append(deepcopy(child))
    properties = paragraph.find(f"{_W}pPr")
    preserve_properties = (
        paragraph is not start_paragraph
        and properties is not None
        and (
            properties.find(f"{_W}sectPr") is not None
            or properties.find(f"{_W}pageBreakBefore") is not None
            or bool(keep)
        )
    )
    if not keep and not preserve_properties:
        return None
    residual = ET.Element(f"{_W}p")
    if preserve_properties:
        assert properties is not None
        residual.append(deepcopy(properties))
    residual.extend(keep)
    return residual


def _toc_paragraph(
    template: ET.Element,
    text: str,
    *,
    level: int,
    style_id: str,
    instruction_text: str,
    effective_format: tuple[tuple[str, str], ...],
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
    _apply_effective_format(text_run, effective_format)
    ET.SubElement(text_run, f"{_W}t").text = text
    ET.SubElement(text_run, f"{_W}tab")
    ET.SubElement(text_run, f"{_W}t").text = "1"
    if last:
        end_run = ET.SubElement(paragraph, f"{_W}r")
        ET.SubElement(end_run, f"{_W}fldChar", {f"{_W}fldCharType": "end"})
    return paragraph


def _refresh_toc(
    parts: dict[str, bytes],
    parent: ET.Element,
    target: ET.Element,
    entries: tuple[TocEntry, ...],
    style_ids: dict[int, str],
    effective_format: tuple[tuple[str, str], ...],
) -> list[JsonObject]:
    """Rebuild a representative cache while keeping a live, dirty TOC field."""

    if not entries:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="toc_entries_missing",
            message="refresh_toc requires representative entries from the final title tree.",
        )
    siblings = list(parent)
    start, end = _field_interval(siblings, siblings.index(target))
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
    style_scope_changes = _stabilize_toc_styles(
        parts,
        templates,
        style_ids,
        effective_format,
    )
    replacements = [
        _toc_paragraph(
            templates.get(entry.level, fallback),
            entry.selected.text,
            level=entry.level,
            style_id=style_ids.get(entry.level, f"TOC{entry.level}"),
            instruction_text=instruction_text,
            effective_format=effective_format,
            first=index == 0,
            last=index == len(entries) - 1,
        )
        for index, entry in enumerate(entries)
    ]
    residuals = [
        residual
        for paragraph in siblings[start : end + 1]
        if (
            residual := _toc_residual_paragraph(
                paragraph,
                start_paragraph=siblings[start],
                end_paragraph=siblings[end],
            )
        )
        is not None
    ]
    for paragraph in siblings[start : end + 1]:
        parent.remove(paragraph)
    for offset, paragraph in enumerate([*replacements, *residuals]):
        parent.insert(start + offset, paragraph)
    return style_scope_changes


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
) -> JsonObject:
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
    mutable_operations: list[tuple[ET.Element, str]] = []
    for index, (_, target, mutation) in enumerate(resolved):
        if mutation.action == "materialize_structure":
            mutable_operations.extend(
                (item, mutation.action) for _, item, _ in structure_resolved[index]
            )
            replacement = replaced_structures.get(index)
            if replacement is not None:
                mutable_operations.append((replacement[1], mutation.action))
        else:
            mutable_operations.append((target, mutation.action))
    for index, (target, action) in enumerate(mutable_operations):
        conflicts = [
            other_action
            for other, other_action in mutable_operations[index + 1 :]
            if _overlap(target, other)
            and frozenset({action, other_action})
            not in {
                frozenset({"normalize_effective_format", "ensure_page_start"}),
                frozenset({"normalize_effective_format", "clear_content"}),
                frozenset({"normalize_effective_format", "remove_object"}),
            }
        ]
        if conflicts:
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
    preserved_boundaries: list[JsonObject] = []
    migrated_boundaries: list[JsonObject] = []
    page_start_results: list[JsonObject] = []
    style_scope_changes: list[JsonObject] = []
    toc_style_ids = _toc_style_ids(parts)
    for index, (parent, target, mutation) in enumerate(resolved):
        if mutation.action == "materialize_slot":
            if mutation.field_id is None or mutation.slot_id is None:
                raise AssertionError("materialize_slot requires field and slot identifiers")
            _apply_effective_format(target, mutation.effective_format)
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
        elif mutation.action == "normalize_effective_format":
            _apply_effective_format(target, mutation.effective_format)
        elif mutation.action == "refresh_toc":
            element_order = {id(element): rank for rank, element in enumerate(document_root.iter())}
            toc_entries = tuple(
                sorted(
                    mutation.toc_entries,
                    key=lambda entry: element_order[
                        id(_resolve(document_root, entry.selected.locator)[1])
                    ],
                )
            )
            style_scope_changes.extend(
                _refresh_toc(
                    parts,
                    parent,
                    target,
                    toc_entries,
                    toc_style_ids,
                    mutation.effective_format,
                )
            )
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
            for kind in _remove_object_preserving_boundary(parent, target):
                preserved_boundaries.append(
                    {
                        "kind": kind,
                        "object_id": str(
                            mutation.selected.object_ref.get("object_id", mutation.selected.locator)
                        ),
                    }
                )
        elif mutation.action == "ensure_page_start":
            changed, representation = _ensure_page_start(parent, target)
            page_start_results.append(
                {
                    "object_id": str(
                        mutation.selected.object_ref.get("object_id", mutation.selected.locator)
                    ),
                    "mode": "new_page",
                    "representation": representation,
                    "changed": changed,
                }
            )
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
    return {
        "preserved_boundaries": preserved_boundaries,
        "migrated_boundaries": migrated_boundaries,
        "page_start_results": page_start_results,
        "style_scope_changes": style_scope_changes,
    }
