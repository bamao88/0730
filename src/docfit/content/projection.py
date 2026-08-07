"""Template-bound quality projection for imported student thesis content.

This module deliberately does not invent missing school styles.  It projects imported
objects onto style IDs that the caller has verified in the bound template, then applies
only object-safe direct formatting needed for figures, tables, formulae, and references.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

from docfit.tools.ooxml import (
    W_NS,
    WP_NS,
    _q,
    _read_package,
    _serialize,
    _write_package,
    _xml,
)
from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("m", M_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("w14", W14_NS)

_HEADING_1 = re.compile(r"^第[一二三四五六七八九十百]+章(?:\s|$)")
_HEADING_2 = re.compile(r"^\d+[.、]?\s*[^\d.]", re.DOTALL)
_HEADING_3 = re.compile(r"^\d+\.\d+(?!\.)")
_MINOR_HEADING = re.compile(r"^[（(]\d+[）)]")
_FIGURE_CAPTION = re.compile(r"^(?:图\s*\d|Fig(?:ure)?\.?\s*\d)", re.IGNORECASE)
_TABLE_CAPTION = re.compile(r"^(?:表\s*\d|Table\s*\d)", re.IGNORECASE)
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{7,}")
_CJK = re.compile(r"[\u3400-\u9fff]")


@dataclass(frozen=True, slots=True)
class TemplateStyleMap:
    normal: str
    body: str
    heading_1: str
    heading_2: str
    heading_3: str
    reference: str
    caption: str


@dataclass(frozen=True, slots=True)
class TextReplacement:
    old: str
    new: str
    expected_count: int = 1


def project_student_content(
    *,
    input_docx: Path,
    template_docx: Path,
    fill_result: JsonObject,
    output_docx: Path,
    styles: TemplateStyleMap,
    text_replacements: tuple[TextReplacement, ...] = (),
) -> JsonObject:
    """Write a new quality-projected candidate using only bound-template styles."""

    if output_docx.exists():
        raise _invalid("projection_output_exists", "Projection output must not already exist.")
    if fill_result.get("output_sha256") != sha256_file(input_docx):
        raise _invalid("projection_input_stale", "Fill evidence is bound to another candidate.")
    if fill_result.get("template_sha256") != sha256_file(template_docx):
        raise _invalid("projection_template_stale", "Fill evidence is bound to another template.")

    parts = _read_package(input_docx)
    document = _xml(parts, "word/document.xml")
    body = document.find(_q(W_NS, "body"))
    if body is None:
        raise _document_error("projection_body_missing", "Candidate document body is missing.")
    template_parts = _read_package(template_docx)
    template_style_ids = _style_ids(_xml(template_parts, "word/styles.xml"))
    requested_style_ids = {
        styles.normal,
        styles.body,
        styles.heading_1,
        styles.heading_2,
        styles.heading_3,
        styles.reference,
        styles.caption,
    }
    missing_styles = sorted(requested_style_ids - template_style_ids)
    if missing_styles:
        raise _invalid(
            "projection_template_style_missing",
            "A requested projection style is not present in the bound template: "
            + ", ".join(missing_styles),
        )

    imported = _resolve_imported_elements(document, fill_result)
    body_elements = imported.get("body.chapters", [])
    reference_elements = imported.get("references.entries", [])
    if not body_elements:
        raise _invalid("projection_body_evidence_missing", "No imported body evidence was found.")

    text_before = _visible_text(document)
    drawings_before = _count(document, W_NS, "drawing")
    equations_before = _count(document, M_NS, "oMath")
    tables_before = _count(document, W_NS, "tbl")
    report: JsonObject = {
        "schema_version": "docfit-student-quality-projection/v1",
        "scope": "template_styles_only_no_builtin_fallback_styles",
        "style_ids": sorted(requested_style_ids),
        "heading_counts": {"level_1": 0, "level_2": 0, "level_3": 0},
        "body_paragraphs": 0,
        "reference_paragraphs": 0,
        "minor_headings": 0,
        "high_risk_mixed_paragraphs_left_aligned": 0,
        "empty_layout_paragraphs_removed": 0,
        "drawing_paragraphs_split": 0,
        "floating_drawings_converted_inline": 0,
        "figure_caption_chains_bound": 0,
        "caption_paragraphs": 0,
        "formula_paragraphs": 0,
        "tables_normalized": 0,
        "table_caption_chains_bound": 0,
        "run_spacing_properties_removed": 0,
        "adjacent_text_runs_merged": 0,
    }

    replacement_report = _apply_replacements(
        [*body_elements, *reference_elements], text_replacements
    )
    report["text_replacements"] = replacement_report

    body_paragraphs = [item for item in body_elements if item.tag == _q(W_NS, "p")]
    for paragraph in body_paragraphs:
        if paragraph not in list(body):
            continue
        if _is_safe_layout_empty(paragraph):
            body.remove(paragraph)
            report["empty_layout_paragraphs_removed"] = (
                int(report["empty_layout_paragraphs_removed"]) + 1
            )

    for paragraph in [item for item in body_elements if item.tag == _q(W_NS, "p")]:
        if paragraph not in list(body):
            continue
        drawings = list(paragraph.iter(_q(W_NS, "drawing")))
        if drawings:
            report["drawing_paragraphs_split"] = int(report["drawing_paragraphs_split"]) + 1
            _split_drawing_paragraph(body, paragraph, styles.normal)

    current_body_elements = _elements_between_imported_boundaries(body, body_elements)
    usable_width = _usable_width_dxa(body, current_body_elements)
    for paragraph in [item for item in current_body_elements if item.tag == _q(W_NS, "p")]:
        if list(paragraph.iter(_q(W_NS, "drawing"))):
            report["floating_drawings_converted_inline"] = int(
                report["floating_drawings_converted_inline"]
            ) + _normalize_drawing_paragraph(paragraph, styles.normal, usable_width)
            continue
        if list(paragraph.iter(_q(M_NS, "oMath"))):
            _normalize_formula(paragraph, styles.body)
            report["formula_paragraphs"] = int(report["formula_paragraphs"]) + 1
            report["run_spacing_properties_removed"] = int(
                report["run_spacing_properties_removed"]
            ) + _clear_run_layout(paragraph)
            continue
        text = _paragraph_text(paragraph).strip()
        if _FIGURE_CAPTION.match(text) or _TABLE_CAPTION.match(text):
            _normalize_caption(paragraph, styles.caption)
            report["caption_paragraphs"] = int(report["caption_paragraphs"]) + 1
        else:
            role = _body_role(text)
            style_id = {
                "heading_1": styles.heading_1,
                "heading_2": styles.heading_2,
                "heading_3": styles.heading_3,
            }.get(role, styles.body)
            _normalize_text_paragraph(paragraph, style_id)
            if role.startswith("heading_"):
                level_key = f"level_{role[-1]}"
                headings = cast(dict[str, int], report["heading_counts"])
                headings[level_key] += 1
            else:
                report["body_paragraphs"] = int(report["body_paragraphs"]) + 1
            if _MINOR_HEADING.match(text):
                _set_paragraph_flag(paragraph, "keepNext", True)
                _set_paragraph_value(paragraph, "jc", "left")
                _clear_indent(paragraph)
                report["minor_headings"] = int(report["minor_headings"]) + 1
            elif _high_risk_mixed_paragraph(paragraph, text):
                _set_paragraph_value(paragraph, "jc", "left")
                report["high_risk_mixed_paragraphs_left_aligned"] = (
                    int(report["high_risk_mixed_paragraphs_left_aligned"]) + 1
                )
        report["run_spacing_properties_removed"] = int(
            report["run_spacing_properties_removed"]
        ) + _clear_run_layout(paragraph)

    for paragraph in [item for item in reference_elements if item.tag == _q(W_NS, "p")]:
        _normalize_reference(paragraph, styles.reference)
        report["reference_paragraphs"] = int(report["reference_paragraphs"]) + 1
        report["run_spacing_properties_removed"] = int(
            report["run_spacing_properties_removed"]
        ) + _clear_run_layout(paragraph)

    for table in [item for item in current_body_elements if item.tag == _q(W_NS, "tbl")]:
        _normalize_table(table, usable_width)
        report["tables_normalized"] = int(report["tables_normalized"]) + 1

    merge_scope = [
        *[item for item in current_body_elements if item.tag == _q(W_NS, "p")],
        *[item for item in reference_elements if item.tag == _q(W_NS, "p")],
    ]
    seen_merge_elements: set[int] = set()
    for paragraph in merge_scope:
        if id(paragraph) in seen_merge_elements:
            continue
        seen_merge_elements.add(id(paragraph))
        report["adjacent_text_runs_merged"] = int(
            report["adjacent_text_runs_merged"]
        ) + _merge_adjacent_text_runs(paragraph)

    report["figure_caption_chains_bound"] = _bind_figure_captions(body)
    report["table_caption_chains_bound"] = _bind_table_captions(body, current_body_elements)
    report["toc"] = _request_toc_update(parts, document)

    parts["word/document.xml"] = _serialize(document)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    _write_package(output_docx, parts)
    warnings = validate_docx_package(output_docx)

    projected = _xml(_read_package(output_docx), "word/document.xml")
    expected_text = text_before
    for replacement in text_replacements:
        expected_text = expected_text.replace(replacement.old, replacement.new)
    invariants = {
        "visible_text_preserved_with_approved_replacements": (
            _visible_text(projected) == expected_text
        ),
        "drawings_preserved": _count(projected, W_NS, "drawing") == drawings_before,
        "equations_preserved": _count(projected, M_NS, "oMath") == equations_before,
        "tables_preserved": _count(projected, W_NS, "tbl") == tables_before,
    }
    if not all(invariants.values()):
        output_docx.unlink(missing_ok=True)
        raise _document_error(
            "projection_content_invariant_failed",
            "Quality projection changed protected document content.",
        )
    output_style_ids = _style_ids(_xml(_read_package(output_docx), "word/styles.xml"))
    report.update(
        {
            "input_sha256": sha256_file(input_docx),
            "template_sha256": sha256_file(template_docx),
            "output_docx": str(output_docx.resolve()),
            "output_sha256": sha256_file(output_docx),
            "usable_width_dxa": usable_width,
            "content_invariants": invariants,
            "package_warnings": list(warnings),
            "non_template_style_ids": sorted(output_style_ids - template_style_ids),
        }
    )
    return report


def _resolve_imported_elements(
    document: ET.Element, fill_result: JsonObject
) -> dict[str, list[ET.Element]]:
    resolved: dict[str, list[ET.Element]] = {}
    for block in fill_result.get("block_operations", []):
        if not isinstance(block, dict) or not isinstance(block.get("field_id"), str):
            continue
        elements: list[ET.Element] = []
        for ref in block.get("inserted_body_refs", []):
            if not isinstance(ref, dict):
                continue
            locator = ref.get("target_locator")
            if not isinstance(locator, str):
                raise _invalid(
                    "projection_target_ref_missing", "An imported object has no target locator."
                )
            elements.append(_find_body_element(document, locator))
        resolved.setdefault(str(block["field_id"]), []).extend(elements)
    return resolved


def _find_body_element(document: ET.Element, locator: str) -> ET.Element:
    body = document.find(_q(W_NS, "body"))
    assert body is not None
    paragraph_match = re.fullmatch(r"/body/p\[@paraId=([0-9A-Fa-f]+)\]", locator)
    if paragraph_match:
        wanted = paragraph_match.group(1).upper()
        for paragraph in body.findall(_q(W_NS, "p")):
            if any(
                key.endswith("}paraId") and value.upper() == wanted
                for key, value in paragraph.attrib.items()
            ):
                return paragraph
    table_match = re.fullmatch(r"/body/tbl\[(\d+)\]", locator)
    if table_match:
        tables = body.findall(_q(W_NS, "tbl"))
        index = int(table_match.group(1)) - 1
        if 0 <= index < len(tables):
            return tables[index]
    raise _invalid("projection_target_ref_stale", "An imported target locator is stale.")


def _elements_between_imported_boundaries(
    body: ET.Element, original: list[ET.Element]
) -> list[ET.Element]:
    existing = list(body)
    survivors = [item for item in original if item in existing]
    if not survivors:
        return []
    start = existing.index(survivors[0])
    end = existing.index(survivors[-1])
    return existing[start : end + 1]


def _body_role(text: str) -> str:
    if _HEADING_1.match(text):
        return "heading_1"
    if len(text) <= 100 and _HEADING_3.match(text):
        return "heading_3"
    if len(text) <= 80 and _HEADING_2.match(text):
        return "heading_2"
    return "body"


def _normalize_text_paragraph(paragraph: ET.Element, style_id: str) -> None:
    num_pr = _preserved_num_pr(paragraph)
    p_pr = _reset_p_pr(paragraph, style_id)
    if num_pr is not None:
        p_pr.append(num_pr)


def _normalize_reference(paragraph: ET.Element, style_id: str) -> None:
    num_pr = _preserved_num_pr(paragraph)
    p_pr = _reset_p_pr(paragraph, style_id)
    if num_pr is not None:
        p_pr.append(num_pr)
    indent = ET.SubElement(p_pr, _q(W_NS, "ind"))
    indent.set(_q(W_NS, "left"), "420")
    indent.set(_q(W_NS, "hanging"), "420")


def _normalize_formula(paragraph: ET.Element, style_id: str) -> None:
    p_pr = _reset_p_pr(paragraph, style_id)
    _set_child_value(p_pr, "jc", "center")
    spacing = ET.SubElement(p_pr, _q(W_NS, "spacing"))
    spacing.set(_q(W_NS, "before"), "120")
    spacing.set(_q(W_NS, "after"), "120")
    spacing.set(_q(W_NS, "line"), "360")
    spacing.set(_q(W_NS, "lineRule"), "auto")
    ET.SubElement(p_pr, _q(W_NS, "keepLines"))


def _normalize_caption(paragraph: ET.Element, style_id: str) -> None:
    p_pr = _reset_p_pr(paragraph, style_id)
    _set_child_value(p_pr, "jc", "center")
    ET.SubElement(p_pr, _q(W_NS, "keepLines"))


def _normalize_drawing_paragraph(
    paragraph: ET.Element, normal_style: str, usable_width_dxa: int | None
) -> int:
    p_pr = _reset_p_pr(paragraph, normal_style)
    _set_child_value(p_pr, "jc", "center")
    spacing = ET.SubElement(p_pr, _q(W_NS, "spacing"))
    spacing.set(_q(W_NS, "before"), "0")
    spacing.set(_q(W_NS, "after"), "0")
    spacing.set(_q(W_NS, "line"), "240")
    spacing.set(_q(W_NS, "lineRule"), "auto")
    converted = 0
    for drawing in paragraph.iter(_q(W_NS, "drawing")):
        for parent in drawing.iter():
            for anchor in list(parent):
                if anchor.tag == _q(WP_NS, "anchor"):
                    index = list(parent).index(anchor)
                    parent.remove(anchor)
                    parent.insert(index, _anchor_to_inline(anchor))
                    converted += 1
        if usable_width_dxa is not None:
            _clamp_drawing(drawing, usable_width_dxa * 635)
    return converted


def _split_drawing_paragraph(body: ET.Element, paragraph: ET.Element, normal_style: str) -> None:
    drawings = list(paragraph.iter(_q(W_NS, "drawing")))
    original_text = _paragraph_text(paragraph).strip()
    image_paragraphs: list[ET.Element] = []
    for drawing in drawings:
        parent = _parent(paragraph, drawing)
        if parent is None:
            continue
        parent.remove(drawing)
        image_paragraph = ET.Element(_q(W_NS, "p"))
        _assign_new_para_id(body, image_paragraph)
        _reset_p_pr(image_paragraph, normal_style)
        run = ET.SubElement(image_paragraph, _q(W_NS, "r"))
        run.append(drawing)
        image_paragraphs.append(image_paragraph)
        if parent.tag == _q(W_NS, "r") and not list(parent) and not (parent.text or ""):
            run_parent = _parent(paragraph, parent)
            if run_parent is not None:
                run_parent.remove(parent)
    index = list(body).index(paragraph)
    insert_at = index if _FIGURE_CAPTION.match(original_text) else index + 1
    for offset, image_paragraph in enumerate(image_paragraphs):
        body.insert(insert_at + offset, image_paragraph)


def _anchor_to_inline(anchor: ET.Element) -> ET.Element:
    inline = ET.Element(_q(WP_NS, "inline"))
    for name in ("distT", "distB", "distL", "distR"):
        inline.set(name, "0")
    retained = {"extent", "effectExtent", "docPr", "cNvGraphicFramePr"}
    for child in anchor:
        local = child.tag.rsplit("}", 1)[-1]
        if child.tag == _q(A_NS, "graphic") or local in retained:
            inline.append(copy.deepcopy(child))
    return inline


def _clamp_drawing(drawing: ET.Element, max_width_emu: int) -> None:
    inline = next(drawing.iter(_q(WP_NS, "inline")), None)
    if inline is None:
        return
    extent = inline.find(_q(WP_NS, "extent"))
    if extent is None:
        return
    try:
        width = int(extent.get("cx", "0"))
        height = int(extent.get("cy", "0"))
    except ValueError:
        return
    if width <= 0 or height <= 0 or width <= max_width_emu:
        return
    new_width = max_width_emu
    new_height = round(height * new_width / width)
    extent.set("cx", str(new_width))
    extent.set("cy", str(new_height))
    for transform_extent in drawing.iter(_q(A_NS, "ext")):
        if transform_extent.get("cx") is not None:
            transform_extent.set("cx", str(new_width))
            transform_extent.set("cy", str(new_height))


def _bind_figure_captions(body: ET.Element) -> int:
    children = list(body)
    bound = 0
    for index, item in enumerate(children):
        if item.tag != _q(W_NS, "p") or not list(item.iter(_q(W_NS, "drawing"))):
            continue
        captions: list[ET.Element] = []
        for candidate in children[index + 1 :]:
            if candidate.tag != _q(W_NS, "p"):
                break
            text = _paragraph_text(candidate).strip()
            if not text:
                continue
            if _FIGURE_CAPTION.match(text):
                captions.append(candidate)
                continue
            break
        if not captions:
            continue
        _set_paragraph_flag(item, "keepNext", True)
        for caption_index, caption in enumerate(captions):
            _set_paragraph_flag(caption, "keepLines", True)
            _set_paragraph_flag(caption, "keepNext", caption_index < len(captions) - 1)
        bound += 1
    return bound


def _normalize_table(table: ET.Element, usable_width_dxa: int | None) -> None:
    tbl_pr = table.find(_q(W_NS, "tblPr"))
    if tbl_pr is None:
        tbl_pr = ET.Element(_q(W_NS, "tblPr"))
        table.insert(0, tbl_pr)
    _remove_children(tbl_pr, {"tblW", "tblLayout", "jc"})
    if usable_width_dxa is not None:
        width = ET.SubElement(tbl_pr, _q(W_NS, "tblW"))
        width.set(_q(W_NS, "type"), "dxa")
        width.set(_q(W_NS, "w"), str(usable_width_dxa))
    layout = ET.SubElement(tbl_pr, _q(W_NS, "tblLayout"))
    layout.set(_q(W_NS, "type"), "fixed")
    _set_child_value(tbl_pr, "jc", "center")
    grid = table.find(_q(W_NS, "tblGrid"))
    if usable_width_dxa is not None and grid is not None:
        columns = grid.findall(_q(W_NS, "gridCol"))
        source_widths = [int(item.get(_q(W_NS, "w"), "0")) for item in columns]
        total = sum(source_widths)
        if total > 0:
            scaled = [round(value * usable_width_dxa / total) for value in source_widths]
            if scaled:
                scaled[-1] += usable_width_dxa - sum(scaled)
            for item, value in zip(columns, scaled, strict=True):
                item.set(_q(W_NS, "w"), str(value))
            for row in table.findall(_q(W_NS, "tr")):
                cells = row.findall(_q(W_NS, "tc"))
                for cell, value in zip(cells, scaled, strict=False):
                    tc_pr = cell.find(_q(W_NS, "tcPr"))
                    if tc_pr is None:
                        tc_pr = ET.Element(_q(W_NS, "tcPr"))
                        cell.insert(0, tc_pr)
                    tc_w = tc_pr.find(_q(W_NS, "tcW"))
                    if tc_w is None:
                        tc_w = ET.SubElement(tc_pr, _q(W_NS, "tcW"))
                    tc_w.set(_q(W_NS, "type"), "dxa")
                    tc_w.set(_q(W_NS, "w"), str(value))
    for row in table.findall(_q(W_NS, "tr")):
        tr_pr = row.find(_q(W_NS, "trPr"))
        if tr_pr is None:
            tr_pr = ET.Element(_q(W_NS, "trPr"))
            row.insert(0, tr_pr)
        if tr_pr.find(_q(W_NS, "cantSplit")) is None:
            ET.SubElement(tr_pr, _q(W_NS, "cantSplit"))


def _bind_table_captions(body: ET.Element, imported: list[ET.Element]) -> int:
    imported_tables = {id(item) for item in imported if item.tag == _q(W_NS, "tbl")}
    children = list(body)
    bound = 0
    for index, table in enumerate(children):
        if id(table) not in imported_tables:
            continue
        previous = _nearest_paragraph(children, index, -1)
        following = _nearest_paragraph(children, index, 1)
        if previous is not None and _TABLE_CAPTION.match(_paragraph_text(previous).strip()):
            _set_paragraph_flag(previous, "keepNext", True)
            bound += 1
        elif following is not None and _TABLE_CAPTION.match(_paragraph_text(following).strip()):
            last_paragraph = next(reversed(list(table.iter(_q(W_NS, "p")))), None)
            if last_paragraph is not None:
                _set_paragraph_flag(last_paragraph, "keepNext", True)
                bound += 1
    return bound


def _nearest_paragraph(children: list[ET.Element], index: int, direction: int) -> ET.Element | None:
    position = index + direction
    while 0 <= position < len(children):
        item = children[position]
        if item.tag == _q(W_NS, "p"):
            if _paragraph_text(item).strip():
                return item
        elif item.tag != _q(W_NS, "bookmarkEnd"):
            return None
        position += direction
    return None


def _request_toc_update(parts: dict[str, bytes], document: ET.Element) -> JsonObject:
    fields = 0
    for instruction in document.iter(_q(W_NS, "instrText")):
        if "TOC" not in (instruction.text or "").upper():
            continue
        fields += 1
        paragraph = _ancestor(document, instruction, _q(W_NS, "p"))
        if paragraph is None:
            continue
        for field_char in paragraph.iter(_q(W_NS, "fldChar")):
            if field_char.get(_q(W_NS, "fldCharType")) == "begin":
                field_char.set(_q(W_NS, "dirty"), "true")
                field_char.attrib.pop(_q(W_NS, "fldLock"), None)
    settings = _xml(parts, "word/settings.xml")
    update = settings.find(_q(W_NS, "updateFields"))
    if update is None:
        update = ET.SubElement(settings, _q(W_NS, "updateFields"))
    update.set(_q(W_NS, "val"), "true")
    parts["word/settings.xml"] = _serialize(settings)
    return {
        "toc_fields_marked_dirty": fields,
        "update_fields_on_open": True,
        "word_refresh_still_requires_canonical_word_verification": True,
    }


def _apply_replacements(
    elements: list[ET.Element], replacements: tuple[TextReplacement, ...]
) -> list[JsonObject]:
    result: list[JsonObject] = []
    for replacement in replacements:
        actual = sum(_paragraph_text(item).count(replacement.old) for item in elements)
        if actual != replacement.expected_count:
            raise _invalid(
                "projection_text_replacement_count",
                "Approved replacement expected "
                f"{replacement.expected_count} match(es), got {actual}.",
            )
        changed = 0
        for element in elements:
            changed += _replace_across_text_nodes(element, replacement.old, replacement.new)
        result.append(
            {
                "old_sha256": _short_text_hash(replacement.old),
                "new_sha256": _short_text_hash(replacement.new),
                "count": changed,
            }
        )
    return result


def _replace_across_text_nodes(element: ET.Element, old: str, new: str) -> int:
    nodes = list(element.iter(_q(W_NS, "t")))
    combined = "".join(node.text or "" for node in nodes)
    starts = [match.start() for match in re.finditer(re.escape(old), combined)]
    for start in reversed(starts):
        end = start + len(old)
        offsets: list[tuple[int, int]] = []
        cursor = 0
        for index, node in enumerate(nodes):
            node_end = cursor + len(node.text or "")
            if cursor <= start < node_end or (start == cursor == node_end and index == 0):
                offsets.append((index, start - cursor))
            if cursor < end <= node_end:
                offsets.append((index, end - cursor))
                break
            cursor = node_end
        if len(offsets) != 2:
            continue
        start_index, start_offset = offsets[0]
        end_index, end_offset = offsets[1]
        start_text = nodes[start_index].text or ""
        end_text = nodes[end_index].text or ""
        if start_index == end_index:
            nodes[start_index].text = start_text[:start_offset] + new + start_text[end_offset:]
            _preserve_space(nodes[start_index])
        else:
            nodes[start_index].text = start_text[:start_offset] + new
            _preserve_space(nodes[start_index])
            for node in nodes[start_index + 1 : end_index]:
                node.text = ""
            nodes[end_index].text = end_text[end_offset:]
            _preserve_space(nodes[end_index])
    return len(starts)


def _clear_run_layout(element: ET.Element) -> int:
    names = {"rFonts", "sz", "szCs", "spacing", "w", "position", "fitText", "kern"}
    removed = 0
    for r_pr in element.iter(_q(W_NS, "rPr")):
        for child in list(r_pr):
            if child.tag.rsplit("}", 1)[-1] in names:
                r_pr.remove(child)
                removed += 1
    return removed


def _merge_adjacent_text_runs(element: ET.Element) -> int:
    """Coalesce semantically identical text runs to avoid renderer spacing artifacts."""

    merged = 0
    for parent in element.iter():
        index = 0
        while index + 1 < len(parent):
            first = parent[index]
            second = parent[index + 1]
            first_text = _mergeable_text_run(first)
            second_text = _mergeable_text_run(second)
            if (
                first_text is None
                or second_text is None
                or _run_properties_key(first) != _run_properties_key(second)
            ):
                index += 1
                continue
            first_text.text = (first_text.text or "") + (second_text.text or "")
            _preserve_space(first_text)
            parent.remove(second)
            merged += 1
    return merged


def _mergeable_text_run(run: ET.Element) -> ET.Element | None:
    if run.tag != _q(W_NS, "r"):
        return None
    content = [child for child in run if child.tag != _q(W_NS, "rPr")]
    if len(content) != 1 or content[0].tag != _q(W_NS, "t"):
        return None
    return content[0]


def _run_properties_key(run: ET.Element) -> bytes:
    properties = run.find(_q(W_NS, "rPr"))
    if properties is None or (not properties.attrib and not list(properties)):
        return b""
    return cast(bytes, ET.tostring(properties, encoding="utf-8"))


def _is_safe_layout_empty(paragraph: ET.Element) -> bool:
    if _paragraph_text(paragraph).strip():
        return False
    protected = {
        "sectPr",
        "br",
        "lastRenderedPageBreak",
        "drawing",
        "object",
        "pict",
        "fldChar",
        "instrText",
        "hyperlink",
        "bookmarkStart",
        "bookmarkEnd",
        "commentRangeStart",
        "commentRangeEnd",
        "footnoteReference",
        "endnoteReference",
        "sym",
        "tab",
        "oMath",
        "oMathPara",
    }
    return not any(item.tag.rsplit("}", 1)[-1] in protected for item in paragraph.iter())


def _usable_width_dxa(body: ET.Element, imported: list[ET.Element]) -> int | None:
    if not imported:
        return None
    children = list(body)
    start = children.index(imported[0])
    for item in children[start:]:
        sect_pr = (
            item.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'sectPr')}")
            if item.tag == _q(W_NS, "p")
            else item
            if item.tag == _q(W_NS, "sectPr")
            else None
        )
        if sect_pr is None:
            continue
        page_size = sect_pr.find(_q(W_NS, "pgSz"))
        margins = sect_pr.find(_q(W_NS, "pgMar"))
        if page_size is None or margins is None:
            continue
        try:
            return (
                int(page_size.get(_q(W_NS, "w"), "0"))
                - int(margins.get(_q(W_NS, "left"), "0"))
                - int(margins.get(_q(W_NS, "right"), "0"))
                - int(margins.get(_q(W_NS, "gutter"), "0"))
            )
        except ValueError:
            return None
    return None


def _reset_p_pr(paragraph: ET.Element, style_id: str) -> ET.Element:
    old = paragraph.find(_q(W_NS, "pPr"))
    if old is not None:
        paragraph.remove(old)
    p_pr = ET.Element(_q(W_NS, "pPr"))
    paragraph.insert(0, p_pr)
    style = ET.SubElement(p_pr, _q(W_NS, "pStyle"))
    style.set(_q(W_NS, "val"), style_id)
    return p_pr


def _preserved_num_pr(paragraph: ET.Element) -> ET.Element | None:
    value = paragraph.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'numPr')}")
    return copy.deepcopy(value) if value is not None else None


def _set_paragraph_flag(paragraph: ET.Element, name: str, enabled: bool) -> None:
    p_pr = _ensure_p_pr(paragraph)
    existing = p_pr.find(_q(W_NS, name))
    if enabled and existing is None:
        ET.SubElement(p_pr, _q(W_NS, name))
    elif not enabled and existing is not None:
        p_pr.remove(existing)


def _set_paragraph_value(paragraph: ET.Element, name: str, value: str) -> None:
    _set_child_value(_ensure_p_pr(paragraph), name, value)


def _set_child_value(parent: ET.Element, name: str, value: str) -> None:
    child = parent.find(_q(W_NS, name))
    if child is None:
        child = ET.SubElement(parent, _q(W_NS, name))
    child.set(_q(W_NS, "val"), value)


def _ensure_p_pr(paragraph: ET.Element) -> ET.Element:
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    if p_pr is None:
        p_pr = ET.Element(_q(W_NS, "pPr"))
        paragraph.insert(0, p_pr)
    return p_pr


def _clear_indent(paragraph: ET.Element) -> None:
    p_pr = _ensure_p_pr(paragraph)
    indent = p_pr.find(_q(W_NS, "ind"))
    if indent is not None:
        p_pr.remove(indent)
    indent = ET.SubElement(p_pr, _q(W_NS, "ind"))
    indent.set(_q(W_NS, "left"), "0")
    indent.set(_q(W_NS, "right"), "0")
    indent.set(_q(W_NS, "firstLine"), "0")


def _remove_children(parent: ET.Element, local_names: set[str]) -> None:
    for child in list(parent):
        if child.tag.rsplit("}", 1)[-1] in local_names:
            parent.remove(child)


def _assign_new_para_id(body: ET.Element, paragraph: ET.Element) -> None:
    used = [
        int(value, 16)
        for item in body.iter(_q(W_NS, "p"))
        for key, value in item.attrib.items()
        if key.endswith("}paraId") and re.fullmatch(r"[0-9A-Fa-f]{8}", value)
    ]
    paragraph.set(_q(W14_NS, "paraId"), f"{max(used, default=0x100000) + 1:08X}")


def _parent(root: ET.Element, child: ET.Element) -> ET.Element | None:
    return next((item for item in root.iter() if child in list(item)), None)


def _ancestor(root: ET.Element, child: ET.Element, tag: str) -> ET.Element | None:
    parent_map = {descendant: parent for parent in root.iter() for descendant in parent}
    current = child
    while current in parent_map:
        current = parent_map[current]
        if current.tag == tag:
            return current
    return None


def _paragraph_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(_q(W_NS, "t")))


def _visible_text(document: ET.Element) -> str:
    visible_tags = {_q(W_NS, "t"), _q(M_NS, "t")}
    return "".join(node.text or "" for node in document.iter() if node.tag in visible_tags)


def _high_risk_mixed_paragraph(paragraph: ET.Element, text: str) -> bool:
    if not (_CJK.search(text) and re.search(r"[A-Za-z0-9]", text)):
        return False
    if len(_LATIN_TOKEN.findall(text)) >= 3:
        return True
    nonempty_runs = sum(1 for run in paragraph.iter(_q(W_NS, "r")) if _paragraph_text(run))
    vertical_runs = _count(paragraph, W_NS, "vertAlign")
    formula_explanation = text.lstrip().startswith("式中") and nonempty_runs >= 10
    fragmented_chemical_list = len(text) <= 350 and nonempty_runs >= 20 and vertical_runs >= 20
    return formula_explanation or fragmented_chemical_list


def _count(root: ET.Element, namespace: str, local: str) -> int:
    return sum(1 for _ in root.iter(_q(namespace, local)))


def _style_ids(styles: ET.Element) -> set[str]:
    return {
        value
        for item in styles.findall(_q(W_NS, "style"))
        if (value := item.get(_q(W_NS, "styleId"))) is not None
    }


def _preserve_space(node: ET.Element) -> None:
    text = node.text or ""
    if text.startswith(" ") or text.endswith(" "):
        node.set(_q(XML_NS, "space"), "preserve")


def _short_text_hash(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()[:16]


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="request", code=code, message=message)


def _document_error(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="error", origin="document", code=code, message=message)
