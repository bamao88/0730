"""Rewrite accepted paragraph text without consuming independent layout breaks."""

from copy import deepcopy
from xml.etree import ElementTree as ET

from docfit.tools.runtime import ToolFailure
from docfit.tools.word_xml import W_NS, visible_word_text

W = f"{{{W_NS}}}"


def _unmapped_break() -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="tool",
        code="materialization_layout_break_mapping_unsupported",
        message="Text replacement has no unambiguous output position for a layout break.",
        suggested_actions=("extend_materialization_layout_mapping",),
    )


def replace_paragraph_content(paragraph: ET.Element, children: list[ET.Element]) -> None:
    """Keep paragraph properties and unambiguous leading/trailing explicit breaks.

    Breaks are absent from the source-entry visible text, so accepting a text
    judgment does not authorize removing them. Interior breaks require an output
    boundary map; stop before mutation when that map is unavailable. Cached
    lastRenderedPageBreak nodes are not explicit author-controlled breaks.
    """
    # Whole-paragraph callers must not silently consume independent objects.
    # Source-bound runtime edits use TextEdits instead of this restricted helper.
    if any(child.tag not in {W + "pPr", W + "r"} for child in paragraph) or any(
        node.tag not in {W + "rPr", W + "t", W + "tab", W + "br", W + "lastRenderedPageBreak"}
        for run in paragraph.findall(W + "r") for node in run
    ):
        raise ToolFailure(status="error", origin="tool",
                          code="materialization_text_mapping_unsupported",
                          message="Whole-paragraph replacement would consume independent objects.",
                          retryable=False)
    leading: list[ET.Element] = []
    trailing: list[ET.Element] = []
    total = len(visible_word_text(paragraph))
    if (
        total == 0
        and next(paragraph.iter(W + "br"), None) is not None
        and any(visible_word_text(child) for child in children)
    ):
        # With no source text, neither side of the break anchors inserted text.
        raise _unmapped_break()
    offset = 0
    for child in paragraph:
        if child.tag != W + "r":
            if next(child.iter(W + "br"), None) is not None:
                raise _unmapped_break()
            offset += len(visible_word_text(child))
            continue
        properties = child.find(W + "rPr")
        for node in child:
            if node.tag != W + "br":
                if next(node.iter(W + "br"), None) is not None:
                    raise _unmapped_break()
                offset += 1 if node.tag == W + "tab" else len(visible_word_text(node))
                continue
            if offset not in (0, total):
                raise _unmapped_break()
            carrier = ET.Element(W + "r", dict(child.attrib))
            if properties is not None:
                carrier.append(deepcopy(properties))
            carrier.append(deepcopy(node))
            (leading if offset == 0 else trailing).append(carrier)
    properties = paragraph.find(W + "pPr")
    paragraph[:] = ([properties] if properties is not None else []) + leading + children + trailing
