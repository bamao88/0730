"""Shared Word object locator and visible-text facts."""

from __future__ import annotations

import re
from typing import cast
from xml.etree import ElementTree as ET

from docfit.tools.runtime import ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W16SE_NS = "http://schemas.microsoft.com/office/word/2015/wordml/symex"
_W = f"{{{W_NS}}}"
_MC = f"{{{MC_NS}}}"
_W16SE = f"{{{W16SE_NS}}}"
_SEGMENT = re.compile(r"^(?P<name>[A-Za-z]+)(?:\[(?P<selector>.+)])?$")
_ATTRIBUTE = re.compile(r"^@(?P<name>[A-Za-z0-9]+)=(?P<value>.+)$")

# ElementTree preserves namespace URIs but not the source prefixes.  Most OOXML
# attributes are URI-valued and survive that rewrite.  Markup Compatibility is
# the important exception: values such as ``mc:Choice/@Requires`` and
# ``mc:Ignorable`` contain prefixes as plain text.  Word rejects a package when
# those values no longer name a declared prefix, so every Word-writing path
# must share this stable vocabulary.
WORD_XML_NAMESPACES: dict[str, str] = {
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "cx1": "http://schemas.microsoft.com/office/drawing/2015/9/8/chartex",
    "cx2": "http://schemas.microsoft.com/office/drawing/2015/10/21/chartex",
    "cx3": "http://schemas.microsoft.com/office/drawing/2016/5/9/chartex",
    "cx4": "http://schemas.microsoft.com/office/drawing/2016/5/10/chartex",
    "cx5": "http://schemas.microsoft.com/office/drawing/2016/5/11/chartex",
    "cx6": "http://schemas.microsoft.com/office/drawing/2016/5/12/chartex",
    "cx7": "http://schemas.microsoft.com/office/drawing/2016/5/13/chartex",
    "cx8": "http://schemas.microsoft.com/office/drawing/2016/5/14/chartex",
    "mc": MC_NS,
    "aink": "http://schemas.microsoft.com/office/drawing/2016/ink",
    "am3d": "http://schemas.microsoft.com/office/drawing/2017/model3d",
    "o": "urn:schemas-microsoft-com:office:office",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "v": "urn:schemas-microsoft-com:vml",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w": W_NS,
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}

for _prefix, _uri in WORD_XML_NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)

_PREFIX_LIST_ATTRIBUTES = {
    f"{{{MC_NS}}}Ignorable",
    f"{{{MC_NS}}}MustUnderstand",
    f"{{{MC_NS}}}PreserveAttributes",
    f"{{{MC_NS}}}PreserveElements",
    f"{{{MC_NS}}}ProcessContent",
}


def _referenced_compatibility_prefixes(root: ET.Element) -> set[str]:
    prefixes: set[str] = set()
    for element in root.iter():
        for name, value in element.attrib.items():
            is_choice_requires = (
                element.tag == f"{{{MC_NS}}}Choice" and name == "Requires"
            )
            if name not in _PREFIX_LIST_ATTRIBUTES and not is_choice_requires:
                continue
            for token in value.split():
                prefix = token.split(":", 1)[0]
                if prefix in WORD_XML_NAMESPACES:
                    prefixes.add(prefix)
    return prefixes


def serialize_word_xml(root: ET.Element) -> bytes:
    """Serialize one Word XML tree without breaking prefix-valued MC contracts."""

    payload = cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    missing = [
        (prefix, WORD_XML_NAMESPACES[prefix])
        for prefix in sorted(_referenced_compatibility_prefixes(root))
        if f"xmlns:{prefix}=".encode() not in payload
    ]
    if not missing:
        return payload
    declaration_end = payload.find(b"?>")
    root_start = payload.find(b"<", declaration_end + 2)
    root_end = payload.find(b">", root_start)
    declarations = b"".join(f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing)
    return payload[:root_end] + declarations + payload[root_end:]


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


def _locator_children(parent: ET.Element, name: str) -> list[ET.Element]:
    if name != "r" or _local_name(parent.tag) != "p":
        return [child for child in parent if _local_name(child.tag) == name]

    runs: list[ET.Element] = []
    for child in parent:
        child_name = _local_name(child.tag)
        if child_name == "r":
            runs.append(child)
        elif child_name in {"hyperlink", "fldSimple"}:
            runs.extend(grandchild for grandchild in child if _local_name(grandchild.tag) == "r")
    return runs


def _target_not_found() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="document",
        code="target_not_found",
        message="The selected object can no longer be resolved in the current Word document.",
        suggested_actions=("view_current_object_again",),
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
    candidates = _locator_children(parent, name)
    if not candidates and _local_name(parent.tag) == "sdt":
        content = parent.find(f"{_W}sdtContent")
        if content is not None:
            candidates = [child for child in content if _local_name(child.tag) == name]
    selector = match.group("selector")
    if selector is None:
        if len(candidates) == 1:
            return candidates[0]
        raise _target_not_found()
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


def resolve_word_locator_pair(
    root: ET.Element,
    locator: str,
) -> tuple[ET.Element, ET.Element]:
    """Resolve one accepted OfficeCLI locator and return its parent and target."""

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


def resolve_word_locator(root: ET.Element, locator: str) -> ET.Element | None:
    """Resolve one accepted OfficeCLI locator using the shared Word contract."""

    try:
        return resolve_word_locator_pair(root, locator)[1]
    except ToolFailure:
        return None


def _symbol_text(element: ET.Element) -> str:
    raw = _attribute_value(element, "char")
    if raw is None:
        return ""
    try:
        return chr(int(raw, 16))
    except (ValueError, OverflowError):
        return ""


def visible_word_text(element: ET.Element) -> str:
    """Return visible Word text, selecting one Markup Compatibility branch."""

    def collect(node: ET.Element, *, parent_is_run: bool = False) -> str:
        if node.tag == f"{_W}t":
            return node.text or ""
        if node.tag == f"{_W}tab" and parent_is_run:
            return "\t"
        if node.tag in {f"{_W}sym", f"{_W16SE}symEx"}:
            return _symbol_text(node)
        if node.tag == f"{_MC}AlternateContent":
            choices = [child for child in node if child.tag == f"{_MC}Choice"]
            for choice in choices:
                text = collect(choice)
                if text:
                    return text
            fallback = next(
                (child for child in node if child.tag == f"{_MC}Fallback"),
                None,
            )
            return collect(fallback) if fallback is not None else ""
        is_run = node.tag == f"{_W}r"
        return "".join(collect(child, parent_is_run=is_run) for child in node)

    return collect(element)
