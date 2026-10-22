"""Fixed-content cleanup handler."""

from __future__ import annotations

from copy import deepcopy
from xml.etree import ElementTree as ET

from docfit.template.materialization.instruction_notes import strip_instruction_parentheticals
from docfit.template.materialization.layout_placeholders import normalize_square_placeholders
from docfit.template.materialization.models import MaterializationContextKind

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_FIXED_CONTENT_CONTEXTS = {
    MaterializationContextKind.FIXED_CONTENT.value,
    MaterializationContextKind.FIXED_HEADING.value,
    MaterializationContextKind.STYLE_ONLY.value,
}


def apply_fixed_content_cleanup(
    paragraph: ET.Element,
    *,
    context_kind: str | None,
) -> bool:
    if context_kind not in _FIXED_CONTENT_CONTEXTS:
        return False
    text = paragraph_text(paragraph)
    cleaned = strip_instruction_parentheticals(text).rstrip()
    cleaned = normalize_square_placeholders(cleaned, context_kind=context_kind)
    if cleaned == text:
        return False
    properties = first_run_properties(paragraph)
    replace_paragraph_content(paragraph, [run(cleaned, properties)])
    return True


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{W}t"))


def first_run_properties(paragraph: ET.Element) -> ET.Element | None:
    first_run = paragraph.find(f"{W}r")
    properties = first_run.find(f"{W}rPr") if first_run is not None else None
    return deepcopy(properties) if properties is not None else None


def run(text: str, properties: ET.Element | None = None) -> ET.Element:
    element = ET.Element(f"{W}r")
    if properties is not None:
        element.append(deepcopy(properties))
    text_node = ET.Element(f"{W}t")
    if text.startswith(" ") or text.endswith(" ") or "　" in text:
        text_node.set(XML_SPACE, "preserve")
    text_node.text = text
    element.append(text_node)
    return element


def replace_paragraph_content(paragraph: ET.Element, children: list[ET.Element]) -> None:
    properties = paragraph.find(f"{W}pPr")
    for child in list(paragraph):
        if child is properties:
            continue
        paragraph.remove(child)
    for child in children:
        paragraph.append(child)
