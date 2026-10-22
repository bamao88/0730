"""Materialize immutable Style Contracts onto final DOCX occurrences."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

from docfit.styles.contracts import StyleContract, StyleContractSet
from docfit.styles.resolver import EffectiveStyleResolver
from docfit.tools.runtime import JsonObject, ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W = f"{{{W_NS}}}"
W14 = f"{{{W14_NS}}}"
_IGNORABLE_NAMESPACES = {
    "w14": W14_NS,
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}

for prefix, uri in (
    ("w", W_NS),
    ("w14", W14_NS),
    ("mc", MC_NS),
    *_IGNORABLE_NAMESPACES.items(),
):
    ET.register_namespace(prefix, uri)

SUPPORTED_MATERIALIZED_PROPERTIES = frozenset(
    {
        "run.font_ascii",
        "run.font_hansi",
        "run.font_east_asia",
        "run.font_complex_script",
        "run.font_ascii_theme",
        "run.font_hansi_theme",
        "run.font_east_asia_theme",
        "run.font_complex_script_theme",
        "run.font_size_pt",
        "run.bold",
        "run.italic",
        "run.color",
        "run.color_theme",
        "run.underline",
        "run.strikethrough",
        "run.vertical_position",
        "run.character_spacing_pt",
        "paragraph.alignment",
        "paragraph.first_line_indent_chars",
        "paragraph.left_indent_chars",
        "paragraph.right_indent_chars",
        "paragraph.hanging_indent_chars",
        "paragraph.space_before_pt",
        "paragraph.space_after_pt",
        "paragraph.line_spacing_rule",
        "paragraph.line_spacing_pt",
        "paragraph.line_value",
        "paragraph.page_break_before",
        "paragraph.keep_with_next",
        "paragraph.keep_together",
        "paragraph.widow_control",
        "paragraph.outline_level",
        "paragraph.numbering",
        "paragraph.tab_stops",
        "cell.vertical_alignment",
        "cell.padding_mm.top",
        "cell.padding_mm.bottom",
        "cell.padding_mm.left",
        "cell.padding_mm.right",
        "cell.text_wrap",
    }
)
_PARAGRAPH_PATH = re.compile(r"/body/p\[@paraId=([0-9A-Fa-f]{8})\]")
_TABLE_PATH = re.compile(r"/body/tbl\[(\d+)\]")
_RUN_PROPERTY_ORDER = {
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
            "effect",
            "bdr",
            "shd",
            "fitText",
            "vertAlign",
            "rtl",
            "cs",
            "em",
            "lang",
            "eastAsianLayout",
            "specVanish",
            "oMath",
        )
    )
}
_PARAGRAPH_PROPERTY_ORDER = {
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
_NUMBERING_PROPERTY_ORDER = {
    name: index for index, name in enumerate(("ilvl", "numId", "numberingChange", "ins"))
}
_TABLE_CELL_PROPERTY_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "cnfStyle",
            "tcW",
            "gridSpan",
            "hMerge",
            "vMerge",
            "tcBorders",
            "shd",
            "noWrap",
            "tcMar",
            "textDirection",
            "tcFitText",
            "vAlign",
            "hideMark",
            "headers",
            "cellIns",
            "cellDel",
            "cellMerge",
            "tcPrChange",
        )
    )
}
_TABLE_CELL_MARGIN_ORDER = {
    name: index for index, name in enumerate(("top", "left", "bottom", "right"))
}
_ORDER_BY_PARENT = {
    f"{W}rPr": _RUN_PROPERTY_ORDER,
    f"{W}pPr": _PARAGRAPH_PROPERTY_ORDER,
    f"{W}numPr": _NUMBERING_PROPERTY_ORDER,
    f"{W}tcPr": _TABLE_CELL_PROPERTY_ORDER,
    f"{W}tcMar": _TABLE_CELL_MARGIN_ORDER,
}


def materialize_style_contracts(
    *,
    input_docx: Path,
    output_docx: Path,
    contracts: StyleContractSet,
    occurrence_manifest: Mapping[str, Any],
) -> JsonObject:
    """Apply managed effective properties without mutating shared named styles."""

    if output_docx.exists():
        raise _failure(
            "style_materialization_output_exists",
            "Style materialization never overwrites an existing output snapshot.",
        )
    raw_occurrences = occurrence_manifest.get("occurrences")
    if not isinstance(raw_occurrences, Sequence) or isinstance(raw_occurrences, str | bytes):
        raise _failure(
            "style_occurrence_manifest_invalid",
            "Occurrence manifest requires an occurrences array.",
        )
    parts = _read_package(input_docx)
    effective_before = EffectiveStyleResolver(input_docx)
    roots: dict[str, ET.Element] = {}
    seen_ids: set[str] = set()
    seen_locators: set[str] = set()
    applied: list[JsonObject] = []
    for index, raw_occurrence in enumerate(raw_occurrences, start=1):
        if not isinstance(raw_occurrence, Mapping):
            raise _failure(
                "style_occurrence_manifest_invalid", "Every occurrence must be an object."
            )
        occurrence_id = raw_occurrence.get("occurrence_id")
        locator = raw_occurrence.get("locator")
        style_ref = raw_occurrence.get("style_contract_ref")
        if not isinstance(occurrence_id, str) or not occurrence_id:
            raise _failure(
                "style_occurrence_manifest_invalid",
                f"Occurrence {index} requires a non-empty occurrence_id.",
            )
        if occurrence_id in seen_ids:
            raise _failure(
                "style_occurrence_duplicate", f"Duplicate occurrence_id: {occurrence_id}."
            )
        if not isinstance(locator, str | Mapping) or not isinstance(style_ref, Mapping):
            raise _failure(
                "style_occurrence_manifest_invalid",
                f"{occurrence_id} requires locator and style_contract_ref.",
            )
        contract = contracts.resolve(style_ref)
        unsupported = sorted(set(contract.owned_properties) - SUPPORTED_MATERIALIZED_PROPERTIES)
        if unsupported:
            raise _failure(
                "style_property_unsupported",
                f"{contract.style_contract_id} owns unsupported properties: "
                + ", ".join(unsupported),
            )
        part, selected, locator_key = _resolve_locator(parts, roots, locator)
        if locator_key in seen_locators:
            raise _failure(
                "style_occurrence_duplicate",
                f"More than one Style Contract targets {locator_key}.",
            )
        seen_ids.add(occurrence_id)
        seen_locators.add(locator_key)
        root = _root(parts, roots, part)
        parents = {child: parent for parent in root.iter() for child in list(parent)}
        paragraphs = _target_paragraphs(selected, parents)
        if not paragraphs:
            raise _failure(
                "style_occurrence_paragraph_not_unique",
                f"{occurrence_id} resolved to 0 paragraphs; expected at least one.",
            )
        resolved_before = effective_before.resolve(locator)
        counts = _apply_contract(
            selected,
            parents,
            contract,
            resolved_before.properties,
        )
        roots[part] = roots[part]
        applied.append(
            {
                "occurrence_id": occurrence_id,
                "locator": dict(locator) if isinstance(locator, Mapping) else locator,
                "style_contract_ref": {
                    "style_contract_id": contract.style_contract_id,
                    "contract_digest": contract.contract_digest,
                },
                "managed_property_count": len(contract.owned_properties),
                **counts,
            }
        )

    for part, root in roots.items():
        parts[part] = _serialize(root)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    _write_package(output_docx, parts)
    return {
        "schema_version": "docfit-style-materialization/v2",
        "style_contract_set_digest": contracts.digest,
        "occurrence_count": len(applied),
        "occurrences": applied,
    }


def _apply_contract(
    selected: ET.Element,
    parents: Mapping[ET.Element, ET.Element],
    contract: StyleContract,
    effective_before: Mapping[str, Any],
) -> JsonObject:
    paragraph_paths = tuple(
        path for path in contract.owned_properties if path.startswith("paragraph.")
    )
    run_paths = tuple(path for path in contract.owned_properties if path.startswith("run."))
    cell_paths = tuple(path for path in contract.owned_properties if path.startswith("cell."))
    paragraphs = _target_paragraphs(selected, parents)
    for paragraph in paragraphs:
        if paragraph_paths:
            paragraph_properties = _properties(paragraph, "pPr")
            _apply_paragraph_properties(
                paragraph_properties,
                paragraph_paths,
                contract.effective_properties,
                effective_before,
            )
    runs = [run for paragraph in paragraphs for run in paragraph.iter(f"{W}r")]
    if run_paths and not runs:
        raise _failure(
            "style_occurrence_run_missing",
            f"{contract.style_contract_id} owns run properties but the occurrence has no Word run.",
        )
    for run in runs:
        _apply_run_properties(
            _properties(run, "rPr"),
            run_paths,
            contract.effective_properties,
        )
    cells = _target_cells(selected, parents)
    if cell_paths and not cells:
        raise _failure(
            "style_occurrence_cell_missing",
            f"{contract.style_contract_id} owns cell properties "
            "but the occurrence has no Word cell.",
        )
    for cell in cells:
        _apply_cell_properties(_properties(cell, "tcPr"), cell_paths, contract.effective_properties)
    return {
        "paragraph_count": len(paragraphs),
        "run_count": len(runs),
        "cell_count": len(cells),
    }


def _apply_run_properties(
    properties: ET.Element,
    owned: Sequence[str],
    effective: Mapping[str, Any],
) -> None:
    font_attributes = {
        "run.font_ascii": "ascii",
        "run.font_hansi": "hAnsi",
        "run.font_east_asia": "eastAsia",
        "run.font_complex_script": "cs",
        "run.font_ascii_theme": "asciiTheme",
        "run.font_hansi_theme": "hAnsiTheme",
        "run.font_east_asia_theme": "eastAsiaTheme",
        "run.font_complex_script_theme": "cstheme",
    }
    for path, attribute in font_attributes.items():
        if path in owned:
            _set_attribute(properties, "rFonts", attribute, _text(effective[path], path))
    if "run.font_size_pt" in owned:
        size = _positive_number(effective["run.font_size_pt"], "run.font_size_pt")
        half_points = str(round(size * 2))
        _set_value(properties, "sz", half_points)
        _set_value(properties, "szCs", half_points)
    for path, tag, complex_tag in (
        ("run.bold", "b", "bCs"),
        ("run.italic", "i", "iCs"),
    ):
        if path in owned:
            encoded = "1" if _boolean(effective[path], path) else "0"
            _set_value(properties, tag, encoded)
            _set_value(properties, complex_tag, encoded)
    if "run.color" in owned:
        color = _text(effective["run.color"], "run.color")
        if color.casefold() != "auto" and re.fullmatch(r"[0-9A-Fa-f]{6}", color) is None:
            raise _failure("style_property_invalid", "run.color must be auto or six hex digits.")
        _set_attribute(properties, "color", "val", color.upper())
    if "run.color_theme" in owned:
        _set_attribute(
            properties,
            "color",
            "themeColor",
            _text(effective["run.color_theme"], "run.color_theme"),
        )
    if "run.underline" in owned:
        value = effective["run.underline"]
        encoded = "none" if value is None else _text(value, "run.underline")
        _set_value(properties, "u", encoded)
    if "run.strikethrough" in owned:
        encoded = "1" if _boolean(effective["run.strikethrough"], "run.strikethrough") else "0"
        _set_value(properties, "strike", encoded)
    if "run.vertical_position" in owned:
        _set_value(
            properties,
            "vertAlign",
            _text(effective["run.vertical_position"], "run.vertical_position"),
        )
    if "run.character_spacing_pt" in owned:
        spacing = _number(effective["run.character_spacing_pt"], "run.character_spacing_pt")
        _set_value(properties, "spacing", str(round(spacing * 20)))


def _apply_paragraph_properties(
    properties: ET.Element,
    owned: Sequence[str],
    effective: Mapping[str, Any],
    effective_before: Mapping[str, Any],
) -> None:
    if "paragraph.alignment" in owned:
        _set_value(
            properties,
            "jc",
            _text(effective["paragraph.alignment"], "paragraph.alignment"),
        )
    for path, attribute in (
        ("paragraph.first_line_indent_chars", "firstLineChars"),
        ("paragraph.left_indent_chars", "leftChars"),
        ("paragraph.right_indent_chars", "rightChars"),
        ("paragraph.hanging_indent_chars", "hangingChars"),
    ):
        if path in owned:
            value = _nonnegative_number(effective[path], path)
            _set_attribute(properties, "ind", attribute, str(round(value * 100)))
    for path, attribute in (
        ("paragraph.space_before_pt", "before"),
        ("paragraph.space_after_pt", "after"),
    ):
        if path in owned:
            twips = str(round(_nonnegative_number(effective[path], path) * 20))
            _set_attribute(properties, "spacing", attribute, twips)
    line_pt = "paragraph.line_spacing_pt" in owned
    line_value = "paragraph.line_value" in owned
    if line_pt and line_value:
        raise _failure(
            "style_property_conflict",
            "A contract cannot own both paragraph.line_spacing_pt and paragraph.line_value.",
        )
    if line_pt:
        spacing = _positive_number(
            effective["paragraph.line_spacing_pt"], "paragraph.line_spacing_pt"
        )
        line = str(round(spacing * 20))
        _set_attribute(properties, "spacing", "line", line)
        if "paragraph.line_spacing_rule" not in owned:
            _set_attribute(properties, "spacing", "lineRule", "exact")
    if line_value:
        spacing = _positive_number(effective["paragraph.line_value"], "paragraph.line_value")
        line = str(round(spacing * 240))
        _set_attribute(properties, "spacing", "line", line)
        if "paragraph.line_spacing_rule" not in owned:
            _set_attribute(properties, "spacing", "lineRule", "auto")
    if "paragraph.line_spacing_rule" in owned:
        _set_attribute(
            properties,
            "spacing",
            "lineRule",
            _text(effective["paragraph.line_spacing_rule"], "paragraph.line_spacing_rule"),
        )
    if "paragraph.page_break_before" in owned:
        encoded = (
            "1"
            if _boolean(effective["paragraph.page_break_before"], "paragraph.page_break_before")
            else "0"
        )
        _set_value(properties, "pageBreakBefore", encoded)
    for path, tag in (
        ("paragraph.keep_with_next", "keepNext"),
        ("paragraph.keep_together", "keepLines"),
        ("paragraph.widow_control", "widowControl"),
    ):
        if path in owned:
            encoded = "1" if _boolean(effective[path], path) else "0"
            _set_value(properties, tag, encoded)
    if "paragraph.outline_level" in owned:
        level = effective["paragraph.outline_level"]
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 9:
            raise _failure(
                "style_property_invalid",
                "paragraph.outline_level must be an integer from 0 through 9.",
            )
        _set_value(properties, "outlineLvl", str(level))
    if "paragraph.numbering" in owned:
        _apply_numbering(properties, effective["paragraph.numbering"])
    if "paragraph.tab_stops" in owned:
        _apply_tab_stops(
            properties,
            effective["paragraph.tab_stops"],
            effective_before.get("paragraph.tab_stops"),
        )


def _apply_cell_properties(
    properties: ET.Element,
    owned: Sequence[str],
    effective: Mapping[str, Any],
) -> None:
    if "cell.vertical_alignment" in owned:
        _set_value(
            properties,
            "vAlign",
            _text(effective["cell.vertical_alignment"], "cell.vertical_alignment"),
        )
    margin_paths = {
        "cell.padding_mm.top": "top",
        "cell.padding_mm.bottom": "bottom",
        "cell.padding_mm.left": "left",
        "cell.padding_mm.right": "right",
    }
    for path, tag in margin_paths.items():
        if path not in owned:
            continue
        twips = str(round(_nonnegative_number(effective[path], path) * 56.6929133858))
        margins = properties.find(f"{W}tcMar")
        if margins is None:
            margins = ET.Element(f"{W}tcMar")
            _insert_ordered(properties, margins)
        else:
            _move_ordered(properties, margins)
        margin = margins.find(f"{W}{tag}")
        if margin is None:
            margin = ET.Element(f"{W}{tag}")
            _insert_ordered(margins, margin)
        else:
            _move_ordered(margins, margin)
        margin.set(f"{W}type", "dxa")
        margin.set(f"{W}w", twips)
    if "cell.text_wrap" in owned:
        no_wrap = properties.find(f"{W}noWrap")
        if _boolean(effective["cell.text_wrap"], "cell.text_wrap"):
            if no_wrap is not None:
                properties.remove(no_wrap)
        elif no_wrap is None:
            _insert_ordered(properties, ET.Element(f"{W}noWrap"))


def _apply_numbering(properties: ET.Element, value: Any) -> None:
    numbering = properties.find(f"{W}numPr")
    if numbering is None:
        numbering = ET.Element(f"{W}numPr")
        _insert_ordered(properties, numbering)
    else:
        _move_ordered(properties, numbering)
    for child in list(numbering):
        if child.tag in {f"{W}ilvl", f"{W}numId"}:
            numbering.remove(child)
    if value is None:
        _set_value(numbering, "numId", "0")
        return
    if not isinstance(value, Mapping):
        raise _failure(
            "style_property_invalid",
            "paragraph.numbering must be NONE or a numbering definition.",
        )
    num_id = value.get("num_id")
    level = value.get("level", 0)
    if not isinstance(num_id, str | int) or isinstance(num_id, bool):
        raise _failure("style_property_invalid", "paragraph.numbering needs num_id.")
    if not isinstance(level, int) or isinstance(level, bool) or level < 0:
        raise _failure("style_property_invalid", "paragraph.numbering level must be nonnegative.")
    _set_value(numbering, "ilvl", str(level))
    _set_value(numbering, "numId", str(num_id))


def _apply_tab_stops(properties: ET.Element, value: Any, existing: Any) -> None:
    tabs = properties.find(f"{W}tabs")
    if tabs is None:
        tabs = ET.Element(f"{W}tabs")
        _insert_ordered(properties, tabs)
    else:
        _move_ordered(properties, tabs)
    for child in list(tabs):
        tabs.remove(child)
    if value is None:
        values = existing if isinstance(existing, Sequence) else ()
        for item in values:
            if not isinstance(item, Mapping):
                continue
            position = item.get("position_twips")
            if not isinstance(position, int):
                continue
            tab = ET.SubElement(tabs, f"{W}tab")
            tab.set(f"{W}val", "clear")
            tab.set(f"{W}pos", str(position))
        return
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise _failure(
            "style_property_invalid",
            "paragraph.tab_stops must be NONE or an array of tab definitions.",
        )
    for item in value:
        if not isinstance(item, Mapping):
            raise _failure("style_property_invalid", "Every tab stop must be an object.")
        position = item.get("position_twips")
        alignment = item.get("alignment")
        leader = item.get("leader", "none")
        if (
            not isinstance(position, int)
            or not isinstance(alignment, str)
            or not isinstance(leader, str)
        ):
            raise _failure(
                "style_property_invalid",
                "Tab stops require position_twips, alignment, and optional leader.",
            )
        tab = ET.SubElement(tabs, f"{W}tab")
        tab.set(f"{W}val", alignment)
        tab.set(f"{W}leader", leader)
        tab.set(f"{W}pos", str(position))


def _properties(owner: ET.Element, tag: str) -> ET.Element:
    found = owner.find(f"{W}{tag}")
    if found is not None:
        return found
    created = ET.Element(f"{W}{tag}")
    if owner.tag == f"{W}tc":
        owner.insert(0, created)
    else:
        owner.insert(0, created)
    return created


def _set_value(parent: ET.Element, tag: str, value: str) -> None:
    _set_attribute(parent, tag, "val", value)


def _set_attribute(parent: ET.Element, tag: str, attribute: str, value: str) -> None:
    element = parent.find(f"{W}{tag}")
    if element is None:
        element = ET.Element(f"{W}{tag}")
        _insert_ordered(parent, element)
    else:
        _move_ordered(parent, element)
    element.set(f"{W}{attribute}", value)


def _move_ordered(parent: ET.Element, child: ET.Element) -> None:
    order = _ORDER_BY_PARENT.get(parent.tag)
    if order is None:
        return
    parent.remove(child)
    _insert_ordered(parent, child)


def _insert_ordered(parent: ET.Element, child: ET.Element) -> None:
    order = _ORDER_BY_PARENT.get(parent.tag)
    if order is None:
        parent.append(child)
        return
    child_rank = order.get(_local_name(child), len(order))
    for index, existing in enumerate(list(parent)):
        if order.get(_local_name(existing), len(order)) > child_rank:
            parent.insert(index, child)
            return
    parent.append(child)


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _resolve_locator(
    parts: Mapping[str, bytes],
    roots: dict[str, ET.Element],
    locator: str | Mapping[str, Any],
) -> tuple[str, ET.Element, str]:
    if isinstance(locator, Mapping):
        if locator.get("type") != "content_control_tag":
            raise _failure(
                "style_locator_unsupported", "Object locators require type=content_control_tag."
            )
        tag = locator.get("value")
        part = locator.get("part", "word/document.xml")
        if not isinstance(tag, str) or not tag or not isinstance(part, str):
            raise _failure(
                "style_locator_invalid", "Content-control locators require value and part."
            )
        root = _root(parts, roots, part)
        matches = []
        for control in root.iter(f"{W}sdt"):
            tag_element = control.find(f"{W}sdtPr/{W}tag")
            if tag_element is not None and tag_element.get(f"{W}val") == tag:
                matches.append(control)
        if len(matches) != 1:
            raise _failure(
                "style_locator_not_unique",
                f"Content-control tag {tag} matched {len(matches)} occurrences; expected one.",
            )
        return part, matches[0], f"{part}#content_control_tag:{tag}"
    match = _PARAGRAPH_PATH.fullmatch(locator)
    if match is not None:
        part = "word/document.xml"
        root = _root(parts, roots, part)
        para_id = match.group(1).upper()
        matches = [
            paragraph
            for paragraph in root.iter(f"{W}p")
            if (paragraph.get(f"{W14}paraId") or "").upper() == para_id
        ]
        if len(matches) != 1:
            raise _failure(
                "style_locator_not_unique",
                f"Paragraph paraId {para_id} matched {len(matches)} occurrences; expected one.",
            )
        return part, matches[0], f"{part}#/body/p[@paraId={para_id}]"
    table_match = _TABLE_PATH.fullmatch(locator)
    if table_match is not None:
        part = "word/document.xml"
        root = _root(parts, roots, part)
        body = root.find(f"{W}body")
        tables = [] if body is None else body.findall(f"{W}tbl")
        index = int(table_match.group(1)) - 1
        if index < 0 or index >= len(tables):
            raise _failure(
                "style_locator_not_unique",
                f"Table locator {locator} matched 0 occurrences; expected one.",
            )
        return part, tables[index], f"{part}#/body/tbl[{index + 1}]"
    if match is None:
        raise _failure(
            "style_locator_unsupported",
            "Style materialization currently requires a paraId paragraph or body table locator.",
        )


def _target_paragraphs(
    selected: ET.Element,
    parents: Mapping[ET.Element, ET.Element],
) -> list[ET.Element]:
    if selected.tag == f"{W}p":
        return [selected]
    if selected.tag == f"{W}tbl":
        return list(selected.iter(f"{W}p"))
    current: ET.Element | None = selected
    while current is not None:
        if current.tag == f"{W}p":
            return [current]
        current = parents.get(current)
    return list(selected.iter(f"{W}p"))


def _target_cells(
    selected: ET.Element,
    parents: Mapping[ET.Element, ET.Element],
) -> list[ET.Element]:
    if selected.tag == f"{W}tbl":
        return list(selected.iter(f"{W}tc"))
    if selected.tag == f"{W}tc":
        return [selected]
    current: ET.Element | None = selected
    while current is not None:
        if current.tag == f"{W}tc":
            return [current]
        current = parents.get(current)
    return list(selected.iter(f"{W}tc"))


def _root(parts: Mapping[str, bytes], roots: dict[str, ET.Element], part: str) -> ET.Element:
    if part in roots:
        return roots[part]
    try:
        root = ET.fromstring(parts[part])
    except (KeyError, ET.ParseError) as error:
        raise _failure("style_part_unreadable", f"The DOCX part {part} cannot be read.") from error
    roots[part] = root
    return root


def _read_package(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path.expanduser().resolve(strict=True)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile) as error:
        raise _failure("style_package_unreadable", "The DOCX package cannot be read.") from error


def _serialize(root: ET.Element) -> bytes:
    payload = cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    ignorable = root.get(f"{{{MC_NS}}}Ignorable", "").split()
    missing = [
        (prefix, _IGNORABLE_NAMESPACES[prefix])
        for prefix in ignorable
        if prefix in _IGNORABLE_NAMESPACES and f"xmlns:{prefix}=".encode() not in payload
    ]
    if missing:
        declaration_end = payload.find(b"?>")
        root_start = payload.find(b"<", declaration_end + 2)
        root_end = payload.find(b">", root_start)
        declarations = b"".join(f' xmlns:{prefix}="{uri}"'.encode() for prefix, uri in missing)
        payload = payload[:root_end] + declarations + payload[root_end:]
    return payload


def _write_package(path: Path, parts: Mapping[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, parts[name])


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise _failure("style_property_invalid", f"{path} must be a non-empty string.")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise _failure("style_property_invalid", f"{path} must be a boolean.")
    return value


def _positive_number(value: object, path: str) -> float:
    number = _number(value, path)
    if number <= 0:
        raise _failure("style_property_invalid", f"{path} must be positive.")
    return number


def _nonnegative_number(value: object, path: str) -> float:
    number = _number(value, path)
    if number < 0:
        raise _failure("style_property_invalid", f"{path} cannot be negative.")
    return number


def _number(value: object, path: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise _failure("style_property_invalid", f"{path} must be numeric.")
    return float(value)


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_style_contract_set", "inspect_document_again"),
    )
