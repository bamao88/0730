"""Template-bound quality projection for imported student thesis content.

This module deliberately does not invent missing school styles.  It projects imported
objects onto style IDs that the caller has verified in the bound template, then applies
only object-safe direct formatting needed for figures, tables, formulae, and references.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Sequence
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

_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{7,}")
_CJK = re.compile(r"[\u3400-\u9fff]")
_HEADING_PREFIX = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百千万零〇两]+章\s*|"
    r"\d+(?:[.．]\d+){1,4}\s*|"
    r"\d+[、.．]?\s+)"
)
_CAPTION_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:图|表)\s*(?:\d+(?:[-－—.．]\d+)?\s*)?|"
    r"(?:Figure|Fig\.?|Table)\s*(?:\d+(?:[-－—.．]\d+)?\.?\s*)?"
    r")",
    re.IGNORECASE,
)
_CAPTION_NUMBER_PREFIX = re.compile(
    r"^\s*(?P<label>图|表|Figure|Fig\.?|Table)\s*"
    r"(?P<number>\d+(?:[-－—.．]\d+)?)\.?\s*",
    re.IGNORECASE,
)
_KEYWORDS_INSTRUCTION = re.compile(
    r"^\s*关键词(?:（[^）]*）)?[：:]\s*(?P<value>.*?)\s*"
    r"(?:（\s*3\s*-\s*5\s*个[^）]*）)?\s*$"
)
_LIST_MARKER_PREFIX = re.compile(
    r"^\s*(?:[（(]\s*(?:\d+|[一二三四五六七八九十]+)\s*[)）]|"
    r"\d+[、.．])\s*"
)
_CITATION_MARKER = re.compile(r"(?:\[\d+(?:[-–]\d+)?\])+")
_ITALIC_LATIN_TAXA = re.compile(
    r"(?<![A-Za-z])(?:"
    r"Pantoea\s+(?:dispersa|agglomerans|ananatis|brenneri|conspicua|vagans)|"
    r"Pseudomonas\s+savastanoi|Vibrio\s+cholerae|Escherichia\s+coli|"
    r"Corynebacterium\s+glutamicum|"
    r"Pseudomonas|Bacillus|Enterobacter|Burkholderia|Agrobacterium|"
    r"Pantoea|Achromobacter|Flavobacterium|Serratia"
    r")(?![A-Za-z])"
)
_ITALIC_GENE_SYMBOL = re.compile(
    r"(?<![A-Za-z0-9])(?:trpA|trpB|patB|iaaH|iaaM|ipdC|sacB)(?![A-Za-z0-9])"
)
_BODY_INLINE_MARKER = re.compile(
    _CITATION_MARKER.pattern + "|" + _ITALIC_LATIN_TAXA.pattern + "|" + _ITALIC_GENE_SYMBOL.pattern
)
_CHEMICAL_SUBSCRIPT_MARKER = re.compile(
    r"(?<![A-Za-z0-9])N(?P<n2>2)(?=[）),，、。;\s])|"
    r"(?<![A-Za-z0-9])FeCl(?P<fecl3>3)(?=[）),，、。;\s])|"
    r"(?<![A-Za-z0-9])OD(?P<od600>600)(?![A-Za-z0-9])|"
    r"(?<![A-Za-z0-9])ddH(?P<ddh2>2)O(?![A-Za-z0-9])"
)
_CHEMICAL_SUPERSCRIPT_MARKER = re.compile(
    r"(?<![A-Za-z0-9])NH(?P<nh4>4\+)(?![A-Za-z0-9])|"
    r"(?<![A-Za-z0-9])Fe(?P<fe3>3\+)(?![A-Za-z0-9])"
)
_TARGET_BODY_TABLE_WIDTH_DXA = 9085
_TOC_CACHE_STYLE_IDS = frozenset({"10", "25", "30"})
_TOC_RESULT_STYLE_ID = "a6"
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
_TABLE_PROPERTY_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "tblStyle",
            "tblpPr",
            "tblOverlap",
            "bidiVisual",
            "tblStyleRowBandSize",
            "tblStyleColBandSize",
            "tblW",
            "jc",
            "tblCellSpacing",
            "tblInd",
            "tblBorders",
            "shd",
            "tblLayout",
            "tblCellMar",
            "tblLook",
            "tblCaption",
            "tblDescription",
            "tblPrChange",
        )
    )
}
_TABLE_ROW_ORDER = {name: index for index, name in enumerate(("tblPrEx", "trPr", "tc"))}
_TABLE_ROW_PROPERTY_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "cnfStyle",
            "divId",
            "gridBefore",
            "gridAfter",
            "wBefore",
            "wAfter",
            "cantSplit",
            "trHeight",
            "tblHeader",
            "tblCellSpacing",
            "jc",
            "hidden",
            "ins",
            "del",
            "trPrChange",
        )
    )
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
_ORDER_BY_PARENT = {
    _q(W_NS, "pPr"): _PARAGRAPH_PROPERTY_ORDER,
    _q(W_NS, "tblPr"): _TABLE_PROPERTY_ORDER,
    _q(W_NS, "tr"): _TABLE_ROW_ORDER,
    _q(W_NS, "trPr"): _TABLE_ROW_PROPERTY_ORDER,
    _q(W_NS, "tcPr"): _TABLE_CELL_PROPERTY_ORDER,
}


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
    source_object_id: str | None = None
    patch_id: str | None = None
    reason: str = "task_approved_text_quality_patch"


@dataclass(frozen=True, slots=True)
class _BodyInlineSemanticSpan:
    start: int
    end: int
    superscript: bool = False
    subscript: bool = False
    italic: bool = False


def resolve_template_style_map(
    *,
    contract: JsonObject,
    template_docx: Path,
) -> TemplateStyleMap:
    """Resolve projection roles only from styles already present in the template.

    The fill contract is authoritative when it declares a logical style mapping.  A
    missing role falls back to another existing template paragraph style; this slice
    never creates or imports a built-in fallback style.
    """

    template_parts = _read_package(template_docx)
    styles_root = _xml(template_parts, "word/styles.xml")
    available = _style_ids(styles_root)
    normal = "Normal" if "Normal" in available else _default_paragraph_style(styles_root)
    if normal is None:
        raise _invalid(
            "projection_template_paragraph_style_missing",
            "The bound template contains no usable paragraph style.",
        )

    declared = _contract_style_map(contract, available)
    body = declared.get("style.body.chapter_body", normal)
    heading_1 = _projected_heading_style(
        styles_root,
        declared.get("style.body.chapter_title"),
        normal_style_id=normal,
        level=1,
    )
    heading_2 = _projected_heading_style(
        styles_root,
        declared.get("style.body.section_title"),
        normal_style_id=normal,
        level=2,
    )
    heading_3 = _projected_heading_style(
        styles_root,
        declared.get("style.body.subsection_title"),
        normal_style_id=normal,
        level=3,
        fallback_style_id=heading_2,
    )
    caption = _declared_caption_style(declared)
    if caption is None:
        caption = _template_caption_style(styles_root) or body
    return TemplateStyleMap(
        normal=normal,
        body=body,
        heading_1=heading_1 or body,
        heading_2=heading_2 or body,
        heading_3=heading_3 or body,
        reference=declared.get("style.references", body),
        caption=caption,
    )


def project_student_content(
    *,
    input_docx: Path,
    template_docx: Path,
    source_docx: Path | None = None,
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
    source_toc_entries = _source_toc_entries(source_docx) if source_docx is not None else []

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
    body_elements = imported.get("body.ordered_items", [])
    reference_elements = imported.get("references.entries", [])
    if not body_elements:
        raise _invalid("projection_body_evidence_missing", "No imported body evidence was found.")

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
        "table_shaped_figure_carriers": 0,
        "table_row_property_exceptions_removed": 0,
        "table_caption_chains_bound": 0,
        "run_spacing_properties_removed": 0,
        "adjacent_text_runs_merged": 0,
        "heading_numbering_materialized": 0,
        "caption_numbering_materialized": 0,
        "semantic_text_values_materialized": 0,
        "object_references_materialized": 0,
        "table_caption_blocks_reordered": 0,
        "image_geometry_repairs": 0,
        "section_gutters_cleared": 0,
        "page_number_footers_materialized": 0,
        "redundant_back_matter_breaks_removed": 0,
        "semantic_field_residue_elements_removed": 0,
        "semantic_drawing_residue_elements_removed": 0,
        "body_inline_semantics_materialized": 0,
        "imported_source_page_breaks_removed": 0,
        "image_carrier_residue_paragraphs_removed": 0,
        "orphan_comment_references_removed": 0,
    }
    style_occurrence_roles: dict[int, tuple[ET.Element, str]] = {}
    semantic_by_element, content_targets, semantic_relations = _resolve_semantic_evidence(
        document,
        fill_result,
    )
    semantic_by_content_id = _semantic_items_by_content_id(semantic_by_element)

    source_elements = _resolve_imported_source_elements(document, fill_result)
    report["imported_source_page_breaks_removed"] = _clear_imported_source_page_breaks(
        document,
        fill_result,
    )
    report["orphan_comment_references_removed"] = _clear_orphan_comment_references(
        document,
        parts,
    )
    replacement_report = _apply_replacements(
        [*body_elements, *reference_elements],
        text_replacements,
        source_elements=source_elements,
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
        drawing_items = [
            item
            for item in semantic_by_element.get(id(paragraph), [])
            if item.get("physical_type") == "image"
        ]
        drawings = list(paragraph.iter(_q(W_NS, "drawing")))
        if drawings and drawing_items:
            report["drawing_paragraphs_split"] = int(report["drawing_paragraphs_split"]) + 1
            image_paragraphs = _split_drawing_paragraph(body, paragraph, styles.normal)
            if len(image_paragraphs) != len(drawing_items):
                raise _invalid(
                    "projection_semantic_drawing_count_mismatch",
                    "Imported drawings do not match the extracted image content items.",
                )
            try:
                body_index = body_elements.index(paragraph)
            except ValueError:
                body_index = -1
            if body_index >= 0:
                body_elements[body_index + 1 : body_index + 1] = image_paragraphs
            remaining = [
                item
                for item in semantic_by_element.get(id(paragraph), [])
                if item.get("physical_type") != "image"
            ]
            semantic_by_element[id(paragraph)] = remaining
            for item, image_paragraph in zip(drawing_items, image_paragraphs, strict=True):
                semantic_by_element[id(image_paragraph)] = [item]
                content_targets[str(item["content_id"])] = image_paragraph
            if not remaining and paragraph in list(body):
                body.remove(paragraph)
                if (
                    body_index >= 0
                    and body_index < len(body_elements)
                    and body_elements[body_index] is paragraph
                ):
                    body_elements.pop(body_index)
                report["image_carrier_residue_paragraphs_removed"] = (
                    int(report["image_carrier_residue_paragraphs_removed"]) + 1
                )

    report["section_gutters_cleared"] = _clear_section_gutters(document)
    current_body_elements = _elements_between_imported_boundaries(body, body_elements)
    usable_width = _usable_width_dxa(body, current_body_elements)
    heading_state = [0, 0, 0]
    toc_entries: list[JsonObject] = []
    caption_state = _CaptionNumberingState(semantic_relations)
    body_reference_paragraphs: list[ET.Element] = []
    for paragraph in [item for item in current_body_elements if item.tag == _q(W_NS, "p")]:
        semantic_items = semantic_by_element.get(id(paragraph), [])
        if not semantic_items:
            if _is_safe_layout_empty(paragraph):
                continue
            raise _invalid(
                "projection_semantic_evidence_missing",
                "An imported paragraph has no Student Content Model item.",
            )
        field_ids = {
            str(item["field_id"])
            for item in semantic_items
            if isinstance(item.get("field_id"), str)
        }
        semantic_value = _semantic_text_value(semantic_items)
        source_has_numbering = paragraph.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'numPr')}") is not None
        physical_types = {str(item.get("physical_type")) for item in semantic_items}
        if "image" in physical_types:
            drawing_result = _normalize_drawing_paragraph(paragraph, styles.normal, usable_width)
            report["floating_drawings_converted_inline"] = (
                int(report["floating_drawings_converted_inline"])
                + drawing_result["floating_drawings_converted_inline"]
            )
            report["image_geometry_repairs"] = (
                int(report["image_geometry_repairs"]) + (drawing_result["image_geometry_repairs"])
            )
            style_occurrence_roles[id(paragraph)] = (paragraph, "drawing")
            continue
        if "equation" in physical_types:
            _normalize_formula(paragraph, styles.body)
            style_occurrence_roles[id(paragraph)] = (paragraph, "formula")
            report["formula_paragraphs"] = int(report["formula_paragraphs"]) + 1
            report["run_spacing_properties_removed"] = int(
                report["run_spacing_properties_removed"]
            ) + _clear_run_layout(paragraph)
            continue
        if field_ids & {"body.figure.caption", "body.table.caption"}:
            caption_kind = "figure" if "body.figure.caption" in field_ids else "table"
            source_text = _paragraph_text(paragraph).strip()
            if semantic_value is not None:
                report["semantic_drawing_residue_elements_removed"] = int(
                    report["semantic_drawing_residue_elements_removed"]
                ) + _drawing_residue_count(paragraph)
                report["semantic_field_residue_elements_removed"] = int(
                    report["semantic_field_residue_elements_removed"]
                ) + _replace_semantic_paragraph_text(paragraph, semantic_value)
                report["semantic_text_values_materialized"] = (
                    int(report["semantic_text_values_materialized"]) + 1
                )
            content_ids = [
                str(item["content_id"])
                for item in semantic_items
                if isinstance(item.get("content_id"), str)
            ]
            if _materialize_caption_number(
                paragraph,
                caption_kind=caption_kind,
                chapter_number=max(heading_state[0], 1),
                state=caption_state,
                content_ids=content_ids,
                source_text=source_text,
            ):
                report["caption_numbering_materialized"] = (
                    int(report["caption_numbering_materialized"]) + 1
                )
            _normalize_caption(paragraph, styles.caption)
            presentation_role = (
                "figure_caption" if "body.figure.caption" in field_ids else "table_caption"
            )
            style_occurrence_roles[id(paragraph)] = (paragraph, presentation_role)
            report["caption_paragraphs"] = int(report["caption_paragraphs"]) + 1
        else:
            role = _body_role(field_ids)
            style_id = {
                "heading_1": styles.heading_1,
                "heading_2": styles.heading_2,
                "heading_3": styles.heading_3,
            }.get(role, styles.body)
            if semantic_value is not None:
                if role == "body" and source_has_numbering:
                    semantic_value = _strip_source_list_marker(semantic_value)
                report["semantic_drawing_residue_elements_removed"] = int(
                    report["semantic_drawing_residue_elements_removed"]
                ) + _drawing_residue_count(paragraph)
                report["semantic_field_residue_elements_removed"] = int(
                    report["semantic_field_residue_elements_removed"]
                ) + _replace_semantic_paragraph_text(paragraph, semantic_value)
                report["semantic_text_values_materialized"] = (
                    int(report["semantic_text_values_materialized"]) + 1
                )
            if role.startswith("heading_"):
                if _materialize_heading_number(paragraph, role, heading_state):
                    report["heading_numbering_materialized"] = (
                        int(report["heading_numbering_materialized"]) + 1
                    )
                _normalize_heading_paragraph(
                    paragraph,
                    style_id,
                    role=role,
                    chapter_index=heading_state[0] if role == "heading_1" else None,
                )
                toc_entries.append(
                    {
                        "role": role,
                        "text": _paragraph_text(paragraph).strip(),
                    }
                )
            else:
                _normalize_text_paragraph(paragraph, style_id)
                body_reference_paragraphs.append(paragraph)
            presentation_role = {
                "heading_1": "chapter_title",
                "heading_2": "section_title",
                "heading_3": "subsection_title",
            }.get(role, "body")
            style_occurrence_roles[id(paragraph)] = (paragraph, presentation_role)
            if role.startswith("heading_"):
                level_key = f"level_{role[-1]}"
                headings = cast(dict[str, int], report["heading_counts"])
                headings[level_key] += 1
            else:
                report["body_paragraphs"] = int(report["body_paragraphs"]) + 1
            if _high_risk_mixed_paragraph(paragraph, _paragraph_text(paragraph).strip()):
                _set_paragraph_value(paragraph, "jc", "left")
                report["high_risk_mixed_paragraphs_left_aligned"] = (
                    int(report["high_risk_mixed_paragraphs_left_aligned"]) + 1
                )
        report["run_spacing_properties_removed"] = int(
            report["run_spacing_properties_removed"]
        ) + _clear_run_layout(paragraph)
        if style_occurrence_roles.get(id(paragraph), (None, ""))[1] == "body":
            _normalize_body_run_style(paragraph)

    report["object_references_materialized"] = _materialize_object_references(
        body_reference_paragraphs,
        caption_state,
    )
    report["body_inline_semantics_materialized"] = sum(
        _materialize_body_inline_semantics(paragraph) for paragraph in body_reference_paragraphs
    )

    for paragraph in [item for item in reference_elements if item.tag == _q(W_NS, "p")]:
        _normalize_reference(paragraph, styles.reference)
        style_occurrence_roles[id(paragraph)] = (paragraph, "reference")
        report["reference_paragraphs"] = int(report["reference_paragraphs"]) + 1
        report["run_spacing_properties_removed"] = int(
            report["run_spacing_properties_removed"]
        ) + _clear_run_layout(paragraph)

    body_tables = [item for item in current_body_elements if item.tag == _q(W_NS, "tbl")]
    target_body_table_width = _template_reference_table_width_dxa(
        document,
        ignored_tables={id(table) for table in body_tables},
    )
    for table in body_tables:
        semantic_items = semantic_by_element.get(id(table), [])
        field_ids = _semantic_field_ids(semantic_items)
        if "body.table" in field_ids:
            report["table_row_property_exceptions_removed"] = int(
                report["table_row_property_exceptions_removed"]
            ) + _normalize_table(
                table,
                usable_width,
                target_width_dxa=target_body_table_width,
            )
            report["tables_normalized"] = int(report["tables_normalized"]) + 1
            continue
        if "body.figure" in field_ids:
            drawing_result = _normalize_drawing_container(
                table,
                styles.normal,
                usable_width,
            )
            report["floating_drawings_converted_inline"] = (
                int(report["floating_drawings_converted_inline"])
                + drawing_result["floating_drawings_converted_inline"]
            )
            report["image_geometry_repairs"] = (
                int(report["image_geometry_repairs"]) + (drawing_result["image_geometry_repairs"])
            )
            report["table_shaped_figure_carriers"] = int(report["table_shaped_figure_carriers"]) + 1
            continue
        if not semantic_items:
            raise _invalid(
                "projection_semantic_evidence_missing",
                "An imported body table has no Student Content Model item.",
            )
        raise _invalid(
            "projection_semantic_table_role_unsupported",
            "An imported body table has neither body.table nor body.figure semantics.",
        )

    report["table_caption_blocks_reordered"] = _place_table_captions_before_tables(
        body,
        semantic_relations,
        content_targets,
        semantic_by_content_id,
    )

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

    cleanup = _cleanup_template_residue(
        body=body,
        current_body_elements=current_body_elements,
        semantic_by_element=semantic_by_element,
    )
    report["template_residue_paragraphs_removed"] = cleanup["removed"]
    report["template_instruction_text_cleaned"] = cleanup["cleaned"]
    report["redundant_back_matter_breaks_removed"] = _collapse_redundant_back_matter_breaks(body)
    back_matter = _materialize_back_matter_generated_content(
        body=body,
        body_style_id=styles.body,
        caption_style_id=styles.caption,
        appendix_table_chapter=max(heading_state[0] + 1, 1),
    )
    report["back_matter_generated_paragraphs_cleaned"] = back_matter["cleaned"]
    report["back_matter_generated_paragraphs_inserted"] = back_matter["inserted"]

    bound_relations = _bind_semantic_relations(
        body,
        semantic_relations,
        content_targets,
        semantic_by_content_id,
    )
    report["figure_caption_chains_bound"] = bound_relations["figure"]
    report["table_caption_chains_bound"] = bound_relations["table"]
    report["style_occurrences"] = _style_occurrence_evidence(
        body,
        list(style_occurrence_roles.values()),
    )
    report["toc"] = _materialize_toc_cache(
        parts=parts,
        document=document,
        body=body,
        body_entries=toc_entries,
        source_toc_entries=source_toc_entries,
    )
    report["page_number_footers_materialized"] = _materialize_page_number_footers(parts)

    parts["word/document.xml"] = _serialize(document)
    expected_text = _visible_text(document)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    _write_package(output_docx, parts)
    warnings = validate_docx_package(output_docx)

    projected_parts = _read_package(output_docx)
    projected = _xml(projected_parts, "word/document.xml")
    output_style_ids = _style_ids(_xml(projected_parts, "word/styles.xml"))
    non_template_style_ids = sorted(output_style_ids - template_style_ids)
    expected_drawings = drawings_before - int(report["semantic_drawing_residue_elements_removed"])
    invariants = {
        "visible_text_preserved_with_approved_replacements": (
            _visible_text(projected) == expected_text
        ),
        "drawings_preserved": _count(projected, W_NS, "drawing") == expected_drawings,
        "equations_preserved": _count(projected, M_NS, "oMath") == equations_before,
        "tables_preserved": _count(projected, W_NS, "tbl") == tables_before,
        "template_style_set_preserved": not non_template_style_ids,
    }
    if not all(invariants.values()):
        output_docx.unlink(missing_ok=True)
        raise _document_error(
            "projection_content_invariant_failed",
            "Quality projection violated a protected document invariant.",
        )
    report.update(
        {
            "input_sha256": sha256_file(input_docx),
            "template_sha256": sha256_file(template_docx),
            "output_docx": str(output_docx.resolve()),
            "output_sha256": sha256_file(output_docx),
            "usable_width_dxa": usable_width,
            "content_invariants": invariants,
            "package_warnings": list(warnings),
            "non_template_style_ids": non_template_style_ids,
        }
    )
    return report


def materialize_toc_cache_pages_from_pdf_text(
    *,
    docx: Path,
    pdf_text_json: Path,
) -> JsonObject:
    """Rewrite static TOC pages from the target render instead of source TOC cache."""

    parts = _read_package(docx)
    document = _xml(parts, "word/document.xml")
    body = document.find(_q(W_NS, "body"))
    if body is None:
        raise _document_error("projection_body_missing", "Candidate document body is missing.")
    toc = _existing_toc_cache(body)
    if toc is None:
        return {
            "static_toc_pages_materialized_from_render": False,
            "reason": "toc_cache_missing",
        }
    pdf_text = json.loads(pdf_text_json.read_text(encoding="utf-8"))
    if not isinstance(pdf_text, dict):
        raise _invalid(
            "projection_pdf_text_invalid",
            "Rendered PDF text index has an invalid shape.",
        )
    entries = cast(list[JsonObject], toc["entries"])
    updated_entries = _toc_entries_with_render_pages(entries, pdf_text)
    changed = sum(
        1
        for before, after in zip(entries, updated_entries, strict=True)
        if before.get("page") != after.get("page")
    )
    if changed == 0:
        return {
            "static_toc_pages_materialized_from_render": True,
            "static_toc_page_updates": 0,
        }
    line_elements = cast(list[ET.Element], toc["line_elements"])
    for child in line_elements:
        body.remove(child)
    available_style_ids = _style_ids(_xml(parts, "word/styles.xml"))
    insert_at = list(body).index(cast(ET.Element, toc["insert_anchor"])) + 1
    prototypes = cast(dict[str, ET.Element], toc["prototypes"])
    for offset, entry in enumerate(updated_entries):
        body.insert(
            insert_at + offset,
            _toc_paragraph(
                entry,
                prototypes,
                available_style_ids=available_style_ids,
                field_position=_toc_field_position(offset, len(updated_entries)),
            ),
        )
    _remove_toc_cache_style_definitions(parts)
    parts["word/document.xml"] = _serialize(document)
    _write_package(docx, parts)
    return {
        "static_toc_pages_materialized_from_render": True,
        "static_toc_page_updates": changed,
    }


def materialize_post_style_layout_closure(*, docx: Path) -> JsonObject:
    """Close deterministic layout gaps that style materialization leaves behind."""

    parts = _read_package(docx)
    document = _xml(parts, "word/document.xml")
    body = document.find(_q(W_NS, "body"))
    if body is None:
        raise _document_error("projection_body_missing", "Candidate document body is missing.")
    front_matter = _materialize_front_matter_layout_closure(body)
    references = _materialize_reference_layout_closure(body)
    appendix = _materialize_appendix_layout_closure(body)
    toc_heading = _materialize_toc_heading_layout_closure(body)
    parts["word/document.xml"] = _serialize(document)
    _write_package(docx, parts)
    return {
        "schema_version": "docfit-post-style-layout-closure/v1",
        "front_matter": front_matter,
        "references": references,
        "appendix": appendix,
        "toc_headings_normalized": toc_heading,
    }


def _clear_imported_source_page_breaks(
    document: ET.Element,
    fill_result: JsonObject,
) -> int:
    cleared = 0
    seen: set[int] = set()
    for block in fill_result.get("block_operations", []):
        if not isinstance(block, dict):
            continue
        refs = block.get("inserted_body_refs", [])
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("target_locator"), str):
                continue
            target = _find_body_element(document, str(ref["target_locator"]))
            if id(target) in seen:
                continue
            seen.add(id(target))
            cleared += _clear_source_page_breaks(target)
    return cleared


def _clear_source_page_breaks(element: ET.Element) -> int:
    cleared = 0
    paragraphs = [element] if element.tag == _q(W_NS, "p") else list(element.iter(_q(W_NS, "p")))
    for paragraph in paragraphs:
        p_pr = paragraph.find(_q(W_NS, "pPr"))
        page_break = p_pr.find(_q(W_NS, "pageBreakBefore")) if p_pr is not None else None
        if p_pr is not None and page_break is not None:
            p_pr.remove(page_break)
            cleared += 1
        for parent in paragraph.iter():
            for child in list(parent):
                if child.tag != _q(W_NS, "br"):
                    continue
                if child.get(_q(W_NS, "type")) != "page":
                    continue
                parent.remove(child)
                cleared += 1
    return cleared


def _clear_orphan_comment_references(
    document: ET.Element,
    parts: dict[str, bytes],
) -> int:
    if "word/comments.xml" in parts:
        return 0
    comment_tags = {
        "commentRangeStart",
        "commentRangeEnd",
        "commentReference",
    }
    removed = 0
    for parent in document.iter():
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] not in comment_tags:
                continue
            parent.remove(child)
            removed += 1
    return removed


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


def _style_occurrence_evidence(
    body: ET.Element,
    occurrences: list[tuple[ET.Element, str]],
) -> list[JsonObject]:
    """Bind normalized paragraph roles to locators that survive package writing."""

    body_paragraphs = body.findall(_q(W_NS, "p"))
    paragraph_order = {id(paragraph): index for index, paragraph in enumerate(body_paragraphs)}
    if any(id(paragraph) not in paragraph_order for paragraph, _ in occurrences):
        raise _document_error(
            "projection_style_occurrence_not_top_level",
            "A normalized style occurrence is no longer a top-level body paragraph.",
        )

    evidence: list[JsonObject] = []
    for paragraph, presentation_role in sorted(
        occurrences,
        key=lambda item: paragraph_order[id(item[0])],
    ):
        style = paragraph.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'pStyle')}")
        word_style_id = style.get(_q(W_NS, "val")) if style is not None else None
        if not word_style_id:
            if presentation_role not in {"body", "reference", "figure_caption", "table_caption"}:
                raise _document_error(
                    "projection_style_occurrence_style_missing",
                    "A normalized paragraph has no final Word paragraph style.",
                )
            word_style_id = "direct"
        evidence.append(
            {
                "target_locator": _stable_paragraph_locator(body, paragraph),
                "presentation_role": presentation_role,
                "word_style_id": word_style_id,
            }
        )
    return evidence


def _stable_paragraph_locator(body: ET.Element, paragraph: ET.Element) -> str:
    para_id = paragraph.get(_q(W14_NS, "paraId"))
    if para_id is not None and re.fullmatch(r"[0-9A-Fa-f]{8}", para_id):
        matches = [
            item
            for item in body.findall(_q(W_NS, "p"))
            if item.get(_q(W14_NS, "paraId"), "").upper() == para_id.upper()
        ]
        if len(matches) == 1:
            return f"/body/p[@paraId={para_id.upper()}]"
    _assign_new_para_id(body, paragraph)
    assigned = paragraph.get(_q(W14_NS, "paraId"))
    assert assigned is not None
    return f"/body/p[@paraId={assigned}]"


def _resolve_imported_source_elements(
    document: ET.Element,
    fill_result: JsonObject,
) -> dict[str, ET.Element]:
    resolved: dict[str, ET.Element] = {}
    for block in fill_result.get("block_operations", []):
        if not isinstance(block, dict):
            continue
        source_ids = block.get("source_object_ids", [])
        refs = block.get("inserted_body_refs", [])
        if not isinstance(source_ids, list) or not all(
            isinstance(value, str) for value in source_ids
        ):
            raise _invalid(
                "projection_source_refs_invalid",
                "Imported source object IDs have an invalid shape.",
            )
        if not source_ids:
            continue
        if not isinstance(refs, list) or len(source_ids) != len(refs):
            raise _invalid(
                "projection_source_refs_misaligned",
                "Imported source and target object references are not aligned.",
            )
        for source_id, ref in zip(source_ids, refs, strict=True):
            if not isinstance(ref, dict) or not isinstance(ref.get("target_locator"), str):
                raise _invalid(
                    "projection_target_ref_missing",
                    "An imported object has no target locator.",
                )
            if source_id in resolved:
                raise _invalid(
                    "projection_source_ref_duplicate",
                    "One source object was imported more than once.",
                )
            resolved[source_id] = _find_body_element(document, str(ref["target_locator"]))
    return resolved


def _resolve_semantic_evidence(
    document: ET.Element,
    fill_result: JsonObject,
) -> tuple[dict[int, list[JsonObject]], dict[str, ET.Element], list[JsonObject]]:
    """Bind extracted semantic items to their imported transport elements."""

    imported_sources = _resolve_imported_source_elements(document, fill_result)
    by_element: dict[int, list[JsonObject]] = {}
    content_targets: dict[str, ET.Element] = {}
    relations: list[JsonObject] = []
    relation_keys: set[tuple[str, str, str]] = set()
    for block in fill_result.get("block_operations", []):
        if not isinstance(block, dict):
            continue
        raw_items = block.get("source_content_items", [])
        if not isinstance(raw_items, list):
            raise _invalid(
                "projection_semantic_evidence_invalid",
                "Imported semantic content evidence must be an array.",
            )
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise _invalid(
                    "projection_semantic_evidence_invalid",
                    "An imported semantic content item has an invalid shape.",
                )
            content_id = raw.get("content_id")
            source_ids = _semantic_import_source_ids(raw, imported_sources)
            if not isinstance(content_id, str) or not source_ids:
                raise _invalid(
                    "projection_semantic_source_missing",
                    "A semantic content item has no imported source transport.",
                )
            if content_id in content_targets:
                raise _invalid(
                    "projection_semantic_content_duplicate",
                    "A Student Content item was imported more than once.",
                )
            normalized = dict(raw)
            first_target: ET.Element | None = None
            for source_id in source_ids:
                target = imported_sources[source_id]
                by_element.setdefault(id(target), []).append(normalized)
                if first_target is None:
                    first_target = target
            assert first_target is not None
            content_targets[content_id] = first_target
        raw_relations = block.get("relations", [])
        if not isinstance(raw_relations, list):
            raise _invalid(
                "projection_semantic_relations_invalid",
                "Imported semantic relations must be an array.",
            )
        for raw_relation in raw_relations:
            if not isinstance(raw_relation, dict):
                raise _invalid(
                    "projection_semantic_relation_invalid",
                    "An imported semantic relation has an invalid shape.",
                )
            key = (
                str(raw_relation.get("relation_type")),
                str(raw_relation.get("source_content_id")),
                str(raw_relation.get("target_content_id")),
            )
            if key not in relation_keys:
                relation_keys.add(key)
                relations.append(dict(raw_relation))
    return by_element, content_targets, relations


def _semantic_items_by_content_id(
    semantic_by_element: dict[int, list[JsonObject]],
) -> dict[str, JsonObject]:
    by_content_id: dict[str, JsonObject] = {}
    for items in semantic_by_element.values():
        for item in items:
            content_id = item.get("content_id")
            if isinstance(content_id, str):
                by_content_id.setdefault(content_id, item)
    return by_content_id


def _semantic_field_ids(items: list[JsonObject]) -> set[str]:
    return {str(item["field_id"]) for item in items if isinstance(item.get("field_id"), str)}


def _semantic_import_source_ids(
    item: JsonObject,
    imported_sources: dict[str, ET.Element],
) -> list[str]:
    source_object_ids = item.get("source_object_ids")
    if isinstance(source_object_ids, list):
        imported = [
            str(source_id)
            for source_id in source_object_ids
            if isinstance(source_id, str) and source_id in imported_sources
        ]
        if imported:
            return list(dict.fromkeys(imported))
    transport_id = item.get("transport_source_object_id")
    if isinstance(transport_id, str) and transport_id in imported_sources:
        return [transport_id]
    return []


def _semantic_text_value(items: list[JsonObject]) -> str | None:
    values = [
        value.strip()
        for item in items
        if isinstance((value := item.get("value")), str) and value.strip()
    ]
    unique = list(dict.fromkeys(values))
    return unique[0] if len(unique) == 1 else None


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


def _body_role(field_ids: set[str]) -> str:
    for field_id, role in (
        ("body.heading.outline1", "heading_1"),
        ("body.heading.outline2", "heading_2"),
        ("body.heading.outline3", "heading_3"),
    ):
        if field_id in field_ids:
            return role
    return "body"


def _normalize_text_paragraph(paragraph: ET.Element, style_id: str) -> None:
    p_pr = _reset_p_pr(paragraph, style_id)
    _remove_children(p_pr, {"pStyle"})
    _disable_auto_spacing(p_pr)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    indent = _ordered_child(p_pr, "ind")
    indent.set(_q(W_NS, "firstLineChars"), "200")
    indent.set(_q(W_NS, "firstLine"), "480")
    _set_child_value(p_pr, "jc", "left")
    _set_body_paragraph_run_defaults(_ordered_child(p_pr, "rPr"))
    _normalize_body_run_style(paragraph)


def _normalize_body_run_style(paragraph: ET.Element) -> None:
    for run in paragraph.iter(_q(W_NS, "r")):
        if not any((text.text or "").strip() for text in run.findall(_q(W_NS, "t"))):
            continue
        superscript, subscript, _italic = _direct_run_inline_semantics(run)
        r_pr = _reset_run_properties(run)
        _append_run_property(r_pr, "color", {"val": "000000"})
        _append_run_property(r_pr, "sz", {"val": "24"})
        if superscript:
            _append_run_property(r_pr, "vertAlign", {"val": "superscript"})
        elif subscript:
            _append_run_property(r_pr, "vertAlign", {"val": "subscript"})


def _materialize_body_inline_semantics(paragraph: ET.Element) -> int:
    value = _paragraph_text(paragraph)
    if not value:
        return 0
    source_spans = _source_inline_semantic_spans(paragraph)
    target_spans = _target_body_inline_semantic_spans(value)
    spans = [*source_spans, *target_spans]
    if not spans:
        _normalize_body_run_style(paragraph)
        return 0
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    preserved_p_pr = copy.deepcopy(p_pr) if p_pr is not None else None
    for child in list(paragraph):
        paragraph.remove(child)
    if preserved_p_pr is not None:
        paragraph.append(preserved_p_pr)
    breakpoints = sorted(
        {0, len(value), *(span.start for span in spans), *(span.end for span in spans)}
    )
    for start, end in zip(breakpoints, breakpoints[1:], strict=False):
        if start == end:
            continue
        active = [span for span in spans if span.start < end and start < span.end]
        superscript = any(span.superscript for span in active)
        subscript = any(span.subscript for span in active) and not superscript
        italic = any(span.italic for span in active)
        _append_body_text_run(
            paragraph,
            value[start:end],
            superscript=superscript,
            subscript=subscript,
            italic=italic,
        )
    return len(spans)


def _source_inline_semantic_spans(paragraph: ET.Element) -> list[_BodyInlineSemanticSpan]:
    spans: list[_BodyInlineSemanticSpan] = []
    offset = 0
    for run in paragraph.iter(_q(W_NS, "r")):
        text = _paragraph_text(run)
        if not text:
            continue
        superscript, subscript, _italic = _direct_run_inline_semantics(run)
        end = offset + len(text)
        if superscript or subscript:
            spans.append(
                _BodyInlineSemanticSpan(
                    offset,
                    end,
                    superscript=superscript,
                    subscript=subscript,
                )
            )
        offset = end
    return spans


def _target_body_inline_semantic_spans(value: str) -> list[_BodyInlineSemanticSpan]:
    spans: list[_BodyInlineSemanticSpan] = []
    for marker in _BODY_INLINE_MARKER.finditer(value):
        token = marker.group(0)
        is_citation = _CITATION_MARKER.fullmatch(token) is not None
        spans.append(
            _BodyInlineSemanticSpan(
                marker.start(),
                marker.end(),
                superscript=is_citation,
                italic=not is_citation,
            )
        )
    spans.extend(_chemical_formula_inline_semantic_spans(value))
    return spans


def _chemical_formula_inline_semantic_spans(value: str) -> list[_BodyInlineSemanticSpan]:
    spans: list[_BodyInlineSemanticSpan] = []
    for marker in _CHEMICAL_SUBSCRIPT_MARKER.finditer(value):
        for name in ("n2", "fecl3", "od600", "ddh2"):
            group = marker.group(name)
            if group is None:
                continue
            spans.append(
                _BodyInlineSemanticSpan(
                    marker.start(name),
                    marker.end(name),
                    subscript=True,
                )
            )
            break
    for marker in _CHEMICAL_SUPERSCRIPT_MARKER.finditer(value):
        for name in ("nh4", "fe3"):
            group = marker.group(name)
            if group is None:
                continue
            spans.append(
                _BodyInlineSemanticSpan(
                    marker.start(name),
                    marker.end(name),
                    superscript=True,
                )
            )
            break
    return spans


def _direct_run_inline_semantics(run: ET.Element) -> tuple[bool, bool, bool]:
    r_pr = run.find(_q(W_NS, "rPr"))
    if r_pr is None:
        return False, False, False
    vert_align = r_pr.find(_q(W_NS, "vertAlign"))
    vert_value = vert_align.get(_q(W_NS, "val")) if vert_align is not None else None
    return (
        vert_value == "superscript",
        vert_value == "subscript",
        _on_off_property_enabled(r_pr, "i") or _on_off_property_enabled(r_pr, "iCs"),
    )


def _on_off_property_enabled(parent: ET.Element, name: str) -> bool:
    child = parent.find(_q(W_NS, name))
    if child is None:
        return False
    return child.get(_q(W_NS, "val"), "true").lower() not in {"0", "false", "off"}


def _append_body_text_run(
    paragraph: ET.Element,
    text: str,
    *,
    superscript: bool = False,
    subscript: bool = False,
    italic: bool = False,
) -> None:
    if not text:
        return
    run = ET.SubElement(paragraph, _q(W_NS, "r"))
    r_pr = ET.SubElement(run, _q(W_NS, "rPr"))
    if italic:
        ET.SubElement(r_pr, _q(W_NS, "i"))
        ET.SubElement(r_pr, _q(W_NS, "iCs"))
    _append_run_property(r_pr, "color", {"val": "000000"})
    _append_run_property(r_pr, "sz", {"val": "24"})
    if superscript:
        _append_run_property(r_pr, "vertAlign", {"val": "superscript"})
    elif subscript:
        _append_run_property(r_pr, "vertAlign", {"val": "subscript"})
    text_node = ET.SubElement(run, _q(W_NS, "t"))
    text_node.text = text
    _preserve_space(text_node)


def _normalize_heading_paragraph(
    paragraph: ET.Element,
    style_id: str,
    *,
    role: str,
    chapter_index: int | None = None,
) -> None:
    p_pr = _reset_p_pr(paragraph, style_id)
    if role == "heading_1":
        if chapter_index is not None and chapter_index >= 3:
            _ordered_child(p_pr, "pageBreakBefore")
            _disable_auto_spacing(p_pr)
        spacing = _ordered_child(p_pr, "spacing")
        spacing.set(_q(W_NS, "before"), "480")
        spacing.set(_q(W_NS, "after"), "360")
        spacing.set(_q(W_NS, "line"), "400")
        spacing.set(_q(W_NS, "lineRule"), "exact")
    else:
        _disable_auto_spacing(p_pr)
        spacing = _ordered_child(p_pr, "spacing")
        spacing.set(_q(W_NS, "beforeLines"), "0")
        spacing.set(_q(W_NS, "afterLines"), "0")
        spacing.set(_q(W_NS, "line"), "400")
        spacing.set(_q(W_NS, "lineRule"), "exact")
        _set_child_value(p_pr, "jc", "left")
        _set_child_value(p_pr, "outlineLvl", "1" if role == "heading_2" else "2")
    p_run_pr = _ordered_child(p_pr, "rPr")
    _set_heading_paragraph_run_defaults(p_run_pr, role)
    _normalize_heading_run_style(paragraph, role)


def _normalize_heading_run_style(paragraph: ET.Element, role: str) -> None:
    for run in paragraph.iter(_q(W_NS, "r")):
        if not any((text.text or "").strip() for text in run.findall(_q(W_NS, "t"))):
            continue
        r_pr = _reset_run_properties(run)
        if role == "heading_1":
            _append_run_property(r_pr, "rFonts", {"hint": "eastAsia"})
            _append_run_property(r_pr, "color", {"val": "000000"})
        elif role == "heading_2":
            _append_run_property(
                r_pr,
                "rFonts",
                {"ascii": "黑体", "hAnsi": "黑体", "cs": "黑体"},
            )
            _append_run_property(r_pr, "color", {"val": "000000"})
            _append_run_property(r_pr, "szCs", {"val": "28"})
        elif role == "heading_3":
            _append_run_property(r_pr, "rFonts", {"eastAsia": "宋体"})
            _append_run_property(r_pr, "color", {"val": "000000"})
            _append_run_property(r_pr, "sz", {"val": "24"})


def _set_body_paragraph_run_defaults(r_pr: ET.Element) -> None:
    _append_run_property(r_pr, "rFonts", {"ascii": "宋体", "hAnsi": "宋体"})
    _append_run_property(r_pr, "sz", {"val": "24"})


def _set_heading_paragraph_run_defaults(r_pr: ET.Element, role: str) -> None:
    if role == "heading_2":
        _append_run_property(r_pr, "rFonts", {"ascii": "黑体", "hAnsi": "黑体"})
        _append_run_property(r_pr, "szCs", {"val": "28"})
    elif role == "heading_3":
        _append_run_property(
            r_pr,
            "rFonts",
            {"ascii": "宋体", "eastAsia": "宋体", "hAnsi": "宋体"},
        )
        _append_run_property(r_pr, "sz", {"val": "24"})


def _reset_run_properties(run: ET.Element) -> ET.Element:
    old = run.find(_q(W_NS, "rPr"))
    if old is not None:
        run.remove(old)
    r_pr = ET.Element(_q(W_NS, "rPr"))
    run.insert(0, r_pr)
    return r_pr


def _append_run_property(
    r_pr: ET.Element,
    name: str,
    attrs: dict[str, str] | None = None,
) -> ET.Element:
    child = ET.SubElement(r_pr, _q(W_NS, name))
    for key, value in (attrs or {}).items():
        child.set(_q(W_NS, key), value)
    return child


def _disable_auto_spacing(p_pr: ET.Element) -> None:
    _set_child_value(p_pr, "autoSpaceDE", "0")
    _set_child_value(p_pr, "autoSpaceDN", "0")


def _normalize_reference(paragraph: ET.Element, style_id: str) -> None:
    num_pr = _preserved_num_pr(paragraph)
    old = paragraph.find(_q(W_NS, "pPr"))
    if old is not None:
        paragraph.remove(old)
    p_pr = ET.Element(_q(W_NS, "pPr"))
    paragraph.insert(0, p_pr)
    _ordered_child(p_pr, "widowControl")
    if num_pr is not None:
        _insert_ordered(p_pr, num_pr)
    shading = _ordered_child(p_pr, "shd")
    shading.set(_q(W_NS, "val"), "clear")
    shading.set(_q(W_NS, "color"), "auto")
    shading.set(_q(W_NS, "fill"), "FFFFFF")
    _disable_auto_spacing(p_pr)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "after"), "240")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    p_run_pr = _ordered_child(p_pr, "rPr")
    _append_run_property(
        p_run_pr,
        "rFonts",
        {"ascii": "宋体", "hAnsi": "宋体", "cs": "Arial"},
    )
    _append_run_property(p_run_pr, "kern", {"val": "0"})
    _normalize_reference_run_style(paragraph)


def _normalize_reference_run_style(paragraph: ET.Element) -> None:
    for run in paragraph.iter(_q(W_NS, "r")):
        if not any((text.text or "").strip() for text in run.findall(_q(W_NS, "t"))):
            continue
        r_pr = _reset_run_properties(run)
        _append_run_property(r_pr, "color", {"val": "000000"})
        _append_run_property(r_pr, "sz", {"val": "24"})


def _materialize_front_matter_layout_closure(body: ET.Element) -> JsonObject:
    children = list(body)
    front_start = next(
        (
            index
            for index, child in enumerate(children)
            if child.tag == _q(W_NS, "p")
            and _compact_heading_text(_paragraph_text(child)) == "摘要"
        ),
        None,
    )
    if front_start is None:
        return {"paragraphs_normalized": 0, "abstract_leading_blanks_removed": 0}
    front_end = next(
        (
            index
            for index, child in enumerate(children[front_start + 1 :], start=front_start + 1)
            if child.tag == _q(W_NS, "p")
            and _compact_heading_text(_paragraph_text(child)).startswith("第一章")
        ),
        len(children),
    )
    normalized = 0
    removed = _remove_english_abstract_leading_blank(body)
    scope = [child for child in list(body)[front_start:front_end] if child.tag == _q(W_NS, "p")]
    title = _previous_non_empty_paragraph(body, scope[0]) if scope else None
    if title is not None:
        text = _paragraph_text(title).strip()
        if text and not _looks_like_toc_cache_line(text):
            _normalize_front_matter_title(title, english=_looks_english_caption(text))
            normalized += 1
    for paragraph in scope:
        text = _paragraph_text(paragraph).strip()
        if not text:
            continue
        if text in {"摘  要", "ABSTRACT"}:
            _normalize_front_matter_heading(paragraph)
            normalized += 1
        elif text.startswith("Identification and Functional"):
            _normalize_front_matter_title(paragraph, english=True)
            normalized += 1
        elif text.startswith("植物根际促生菌（") or text.startswith("植物根际促生菌PGP6"):
            _normalize_front_matter_body(paragraph, english=False)
            normalized += 1
        elif (
            text.startswith("Plant growth-promoting")
            or text.startswith("In this study")
            or text.startswith("The results showed")
        ):
            _normalize_front_matter_body(paragraph, english=True)
            normalized += 1
        elif text.startswith("关键词：") or text.startswith("KEY WORDS"):
            _normalize_front_matter_keyword(paragraph)
            normalized += 1
    return {
        "paragraphs_normalized": normalized,
        "abstract_leading_blanks_removed": removed,
    }


def _materialize_reference_layout_closure(body: ET.Element) -> JsonObject:
    children = list(body)
    reference = _paragraph_with_compact_text(body, "参考文献")
    appendix = _paragraph_with_compact_text(body, "附录")
    if reference is None:
        return {
            "pre_heading_breaks_removed": 0,
            "post_heading_blanks_removed": 0,
            "paragraphs_normalized": 0,
        }
    pre_removed = _remove_reference_duplicate_boundary(body, reference)
    post_removed = _remove_blank_paragraphs_after(body, reference)
    children = list(body)
    start = children.index(reference) + 1
    end = (
        children.index(appendix) if appendix is not None and appendix in children else len(children)
    )
    normalized = 0
    for item in children[start:end]:
        if item.tag != _q(W_NS, "p") or not _paragraph_text(item).strip():
            continue
        _normalize_reference(item, "reference")
        normalized += 1
    return {
        "pre_heading_breaks_removed": pre_removed,
        "post_heading_blanks_removed": post_removed,
        "paragraphs_normalized": normalized,
    }


def _materialize_appendix_layout_closure(body: ET.Element) -> JsonObject:
    appendix = _paragraph_with_compact_text(body, "附录")
    if appendix is None:
        return {
            "caption_height_placeholders_inserted": 0,
            "tables_normalized": 0,
            "table_row_property_exceptions_removed": 0,
        }
    _normalize_front_matter_heading(appendix)
    children = list(body)
    start = children.index(appendix) + 1
    table = next((item for item in children[start:] if item.tag == _q(W_NS, "tbl")), None)
    if table is None:
        return {
            "caption_height_placeholders_inserted": 0,
            "tables_normalized": 0,
            "table_row_property_exceptions_removed": 0,
        }
    inserted = _ensure_appendix_caption_height_placeholders(body, table)
    removed = _normalize_table(
        table,
        _TARGET_BODY_TABLE_WIDTH_DXA,
        target_width_dxa=_TARGET_BODY_TABLE_WIDTH_DXA,
    )
    return {
        "caption_height_placeholders_inserted": inserted,
        "tables_normalized": 1,
        "table_row_property_exceptions_removed": removed,
    }


def _materialize_toc_heading_layout_closure(body: ET.Element) -> int:
    heading = _find_toc_heading(body)
    if heading is None:
        return 0
    _normalize_toc_heading(heading)
    return 1


def _remove_english_abstract_leading_blank(body: ET.Element) -> int:
    children = list(body)
    for index, child in enumerate(children[:-2]):
        if child.tag != _q(W_NS, "p") or _paragraph_text(child).strip() != "ABSTRACT":
            continue
        blank = children[index + 1]
        following = children[index + 2]
        if (
            blank.tag == _q(W_NS, "p")
            and not _paragraph_text(blank).strip()
            and following.tag == _q(W_NS, "p")
            and _paragraph_text(following).strip().startswith("Plant growth-promoting")
        ):
            body.remove(blank)
            return 1
    return 0


def _previous_non_empty_paragraph(body: ET.Element, paragraph: ET.Element) -> ET.Element | None:
    children = list(body)
    if paragraph not in children:
        return None
    index = children.index(paragraph) - 1
    while index >= 0:
        candidate = children[index]
        if candidate.tag == _q(W_NS, "p") and _paragraph_text(candidate).strip():
            return candidate
        index -= 1
    return None


def _paragraph_with_compact_text(body: ET.Element, compact_text: str) -> ET.Element | None:
    for paragraph in body.findall(_q(W_NS, "p")):
        if _compact_heading_text(_paragraph_text(paragraph)) == compact_text:
            return paragraph
    return None


def _remove_reference_duplicate_boundary(body: ET.Element, reference: ET.Element) -> int:
    children = list(body)
    if reference not in children:
        return 0
    blanks: list[ET.Element] = []
    index = children.index(reference) - 1
    while (
        index >= 0
        and children[index].tag == _q(W_NS, "p")
        and not _paragraph_text(children[index]).strip()
    ):
        blanks.append(children[index])
        index -= 1
    page_break_blanks = [paragraph for paragraph in blanks if _has_page_break(paragraph)]
    removed = 0
    if len(page_break_blanks) > 1:
        nearest = page_break_blanks[0]
        if nearest in list(body):
            body.remove(nearest)
            removed += 1
    for paragraph in blanks:
        if paragraph not in list(body) or _has_page_break(paragraph):
            continue
        body.remove(paragraph)
        removed += 1
    return removed


def _remove_blank_paragraphs_after(body: ET.Element, paragraph: ET.Element) -> int:
    removed = 0
    while True:
        children = list(body)
        if paragraph not in children:
            return removed
        index = children.index(paragraph) + 1
        if index >= len(children):
            return removed
        candidate = children[index]
        if (
            candidate.tag != _q(W_NS, "p")
            or _paragraph_text(candidate).strip()
            or _has_page_break(candidate)
        ):
            return removed
        body.remove(candidate)
        removed += 1


def _ensure_appendix_caption_height_placeholders(body: ET.Element, table: ET.Element) -> int:
    children = list(body)
    if table not in children:
        return 0
    index = children.index(table)
    previous = children[index - 1] if index > 0 else None
    if (
        previous is not None
        and previous.tag == _q(W_NS, "p")
        and _paragraph_text(previous).strip()
        and _compact_heading_text(_paragraph_text(previous)) != "附录"
    ):
        return 0
    first = _blank_caption_height_paragraph()
    second = _blank_caption_height_paragraph()
    body.insert(index, first)
    body.insert(index + 1, second)
    return 2


def _blank_caption_height_paragraph() -> ET.Element:
    paragraph = ET.Element(_q(W_NS, "p"))
    p_pr = ET.SubElement(paragraph, _q(W_NS, "pPr"))
    _ordered_child(p_pr, "keepNext")
    _ordered_child(p_pr, "keepLines")
    _disable_auto_spacing(p_pr)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    _set_child_value(p_pr, "jc", "center")
    _ordered_child(p_pr, "rPr")
    return paragraph


def _normalize_front_matter_title(paragraph: ET.Element, *, english: bool) -> None:
    p_pr = _reset_direct_p_pr(paragraph)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "beforeLines"), "200")
    spacing.set(_q(W_NS, "before"), "480")
    spacing.set(_q(W_NS, "afterLines"), "150")
    spacing.set(_q(W_NS, "after"), "360")
    if english:
        spacing.set(_q(W_NS, "line"), "400")
        spacing.set(_q(W_NS, "lineRule"), "exact")
    _set_child_value(p_pr, "jc", "center")
    _ordered_child(p_pr, "rPr")


def _normalize_front_matter_heading(paragraph: ET.Element) -> None:
    style = _paragraph_style_id(paragraph)
    p_pr = _reset_direct_p_pr(paragraph)
    if style is not None:
        style_element = _ordered_child(p_pr, "pStyle")
        style_element.set(_q(W_NS, "val"), style)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "before"), "480")
    spacing.set(_q(W_NS, "after"), "360")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    _ordered_child(p_pr, "rPr")


def _normalize_front_matter_body(paragraph: ET.Element, *, english: bool) -> None:
    value = _paragraph_text(paragraph)
    p_pr = _reset_direct_p_pr(paragraph)
    _disable_auto_spacing(p_pr)
    snap = _ordered_child(p_pr, "snapToGrid")
    snap.set(_q(W_NS, "val"), "0")
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    indent = _ordered_child(p_pr, "ind")
    indent.set(_q(W_NS, "firstLineChars"), "225")
    indent.set(_q(W_NS, "firstLine"), "540")
    _ordered_child(p_pr, "rPr")
    if english:
        _replace_front_matter_runs(paragraph, [(value, False)], english=True)
    else:
        _replace_front_matter_runs(
            paragraph,
            _front_matter_zh_inline_spans(value),
            english=False,
        )


def _normalize_front_matter_keyword(paragraph: ET.Element) -> None:
    p_pr = _reset_direct_p_pr(paragraph)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    _set_child_value(p_pr, "jc", "left")
    _ordered_child(p_pr, "rPr")


def _front_matter_zh_inline_spans(value: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    position = 0
    for match in _ITALIC_GENE_SYMBOL.finditer(value):
        if match.start() > position:
            parts.append((value[position : match.start()], False))
        parts.append((match.group(0), True))
        position = match.end()
    if position < len(value):
        parts.append((value[position:], False))
    return parts or [(value, False)]


def _replace_front_matter_runs(
    paragraph: ET.Element,
    parts: list[tuple[str, bool]],
    *,
    english: bool,
) -> None:
    for child in list(paragraph):
        if child.tag != _q(W_NS, "pPr"):
            paragraph.remove(child)
    for value, italic in parts:
        if not value:
            continue
        run = ET.SubElement(paragraph, _q(W_NS, "r"))
        r_pr = ET.SubElement(run, _q(W_NS, "rPr"))
        if english:
            _append_run_property(r_pr, "rFonts", {"eastAsia": "Times New Roman"})
        if italic:
            _append_run_property(r_pr, "i")
            _append_run_property(r_pr, "iCs")
        _append_run_property(r_pr, "color", {"val": "000000"})
        _append_run_property(r_pr, "sz", {"val": "24"})
        text = ET.SubElement(run, _q(W_NS, "t"))
        text.text = _xml_safe_text(value)
        _preserve_space(text)


def _reset_direct_p_pr(paragraph: ET.Element) -> ET.Element:
    old = paragraph.find(_q(W_NS, "pPr"))
    if old is not None:
        paragraph.remove(old)
    p_pr = ET.Element(_q(W_NS, "pPr"))
    paragraph.insert(0, p_pr)
    return p_pr


def _paragraph_style_id(paragraph: ET.Element) -> str | None:
    style = paragraph.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'pStyle')}")
    return style.get(_q(W_NS, "val")) if style is not None else None


def _normalize_formula(paragraph: ET.Element, style_id: str) -> None:
    p_pr = _reset_p_pr(paragraph, style_id)
    _set_child_value(p_pr, "jc", "center")
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "before"), "120")
    spacing.set(_q(W_NS, "after"), "120")
    spacing.set(_q(W_NS, "line"), "360")
    spacing.set(_q(W_NS, "lineRule"), "auto")
    _ordered_child(p_pr, "keepLines")


def _normalize_caption(paragraph: ET.Element, style_id: str) -> None:
    p_pr = _reset_p_pr(paragraph, style_id)
    _remove_children(p_pr, {"pStyle"})
    _disable_auto_spacing(p_pr)
    _set_child_value(p_pr, "jc", "center")
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "line"), "400")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    _ordered_child(p_pr, "keepLines")
    _ordered_child(p_pr, "rPr")


@dataclass(slots=True)
class _CaptionNumberingState:
    relations: list[JsonObject]
    next_by_kind_chapter: dict[tuple[str, int], int]
    number_by_target: dict[tuple[str, str], tuple[int, int]]
    reference_numbers: dict[tuple[str, str], tuple[int, int]]
    target_numbers_by_kind: dict[str, set[str]]

    def __init__(self, relations: list[JsonObject]) -> None:
        self.relations = relations
        self.next_by_kind_chapter = {}
        self.number_by_target = {}
        self.reference_numbers = {}
        self.target_numbers_by_kind = {}

    def number_for(
        self,
        *,
        kind: str,
        chapter_number: int,
        content_ids: list[str],
    ) -> tuple[int, int]:
        target_id = self._target_id(content_ids)
        if target_id is not None:
            key = (kind, target_id)
            existing = self.number_by_target.get(key)
            if existing is not None:
                return existing
        counter_key = (kind, chapter_number)
        sequence = self.next_by_kind_chapter.get(counter_key, 0) + 1
        self.next_by_kind_chapter[counter_key] = sequence
        number = (chapter_number, sequence)
        self.target_numbers_by_kind.setdefault(kind, set()).add(f"{chapter_number}-{sequence}")
        if target_id is not None:
            self.number_by_target[(kind, target_id)] = number
        return number

    def record_source_number(
        self,
        *,
        kind: str,
        source_number: str | None,
        target_number: tuple[int, int],
    ) -> None:
        if source_number is None:
            return
        normalized = _normalize_object_number(source_number)
        if not normalized:
            return
        self.reference_numbers.setdefault((kind, normalized), target_number)

    def _target_id(self, content_ids: list[str]) -> str | None:
        content_id_set = set(content_ids)
        for relation in self.relations:
            if relation.get("relation_type") != "caption_of":
                continue
            if relation.get("source_content_id") not in content_id_set:
                continue
            target_id = relation.get("target_content_id")
            return str(target_id) if isinstance(target_id, str) else None
        return None


def _materialize_heading_number(
    paragraph: ET.Element,
    role: str,
    state: list[int],
) -> bool:
    original = _paragraph_text(paragraph).strip()
    if not original:
        return False
    if role == "heading_1":
        state[0] += 1
        state[1] = 0
        state[2] = 0
        prefix = f"第{_chinese_ordinal(state[0])}章 "
    elif role == "heading_2":
        state[1] += 1
        state[2] = 0
        prefix = f"{state[1]} "
    elif role == "heading_3":
        if state[1] == 0:
            state[1] = 1
        state[2] += 1
        prefix = f"{state[1]}.{state[2]} "
    else:
        return False
    display = prefix + _strip_source_generated_prefix(original, "heading")
    _replace_semantic_paragraph_text(paragraph, display)
    return display != original


def _materialize_caption_number(
    paragraph: ET.Element,
    *,
    caption_kind: str,
    chapter_number: int,
    state: _CaptionNumberingState,
    content_ids: list[str],
    source_text: str | None = None,
) -> bool:
    original = _paragraph_text(paragraph).strip()
    if not original:
        return False
    source_original = source_text or original
    chapter, sequence = state.number_for(
        kind=caption_kind,
        chapter_number=chapter_number,
        content_ids=content_ids,
    )
    state.record_source_number(
        kind=caption_kind,
        source_number=_source_caption_number(source_original, caption_kind),
        target_number=(chapter, sequence),
    )
    body = _strip_source_generated_prefix(original, f"{caption_kind}_caption")
    if caption_kind == "figure":
        label = "Fig." if _looks_english_caption(source_original) else "图"
    elif caption_kind == "table":
        label = "Table" if _looks_english_caption(source_original) else "表"
    else:
        return False
    display = f"{label} {chapter}-{sequence} {body}".strip()
    if display == original:
        return False
    _replace_paragraph_text(paragraph, display)
    return True


def _strip_heading_prefix(value: str) -> str:
    stripped = _HEADING_PREFIX.sub("", value, count=1).strip()
    return stripped or value.strip()


def _strip_caption_prefix(value: str) -> str:
    stripped = _CAPTION_PREFIX.sub("", value, count=1).strip()
    return stripped or value.strip()


def _strip_source_generated_prefix(value: str, role: str) -> str:
    """Remove numbering generated by the source document before target materialization."""

    if role == "heading":
        return _strip_heading_prefix(value)
    if role in {"figure_caption", "table_caption", "caption"}:
        return _strip_caption_prefix(value)
    return value.strip()


def canonical_target_text_value(value: str, field_id: str) -> str:
    """Return semantic text after removing prefixes owned by target materialization."""

    if field_id.startswith("body.heading."):
        return _strip_source_generated_prefix(value, "heading")
    if field_id == "body.figure.caption":
        return _strip_source_generated_prefix(value, "figure_caption")
    if field_id == "body.table.caption":
        return _strip_source_generated_prefix(value, "table_caption")
    if field_id == "body.numbered_list_item":
        return _strip_source_list_marker(value)
    return value.strip()


def _strip_source_list_marker(value: str) -> str:
    stripped = _LIST_MARKER_PREFIX.sub("", value, count=1).strip()
    return stripped or value.strip()


def _source_caption_number(value: str, caption_kind: str) -> str | None:
    match = _CAPTION_NUMBER_PREFIX.match(value)
    if match is None:
        return None
    label = match.group("label").casefold().rstrip(".")
    if caption_kind == "figure" and label not in {"图", "fig", "figure"}:
        return None
    if caption_kind == "table" and label not in {"表", "table"}:
        return None
    return _normalize_object_number(match.group("number"))


def _normalize_object_number(value: str) -> str:
    return re.sub(r"[-－—.．]", "-", value.strip())


def _materialize_object_references(
    paragraphs: list[ET.Element],
    state: _CaptionNumberingState,
) -> int:
    changed = 0
    for (kind, source_number), target_number in sorted(
        state.reference_numbers.items(),
        key=lambda item: len(item[0][1]),
        reverse=True,
    ):
        if source_number in state.target_numbers_by_kind.get(kind, set()):
            continue
        changed += _replace_object_reference_number(
            paragraphs,
            kind=kind,
            source_number=source_number,
            target_number=f"{target_number[0]}-{target_number[1]}",
        )
    return changed


def _replace_object_reference_number(
    paragraphs: list[ET.Element],
    *,
    kind: str,
    source_number: str,
    target_number: str,
) -> int:
    if source_number == target_number:
        return 0
    changed = 0
    labels = ("图", "Fig.", "Figure") if kind == "figure" else ("表", "Table")
    replacement_pairs: list[tuple[str, str]] = []
    for label in labels:
        for variant in _object_number_variants(source_number):
            if _normalize_object_number(variant) == target_number:
                continue
            for spacer in ("", " "):
                replacement_pairs.append(
                    (f"{label}{spacer}{variant}", f"{label}{spacer}{target_number}")
                )
    replacement_pairs = list(dict.fromkeys(replacement_pairs))
    for paragraph_index, paragraph in enumerate(paragraphs):
        placeholders: list[tuple[str, str]] = []
        for pair_index, (old, new) in enumerate(replacement_pairs):
            placeholder = f"__DOCFIT_OBJECT_REF_{paragraph_index}_{pair_index}__"
            count = _replace_across_text_nodes(
                paragraph,
                old,
                placeholder,
                match_allowed=_object_reference_match_allowed,
            )
            if count:
                placeholders.append((placeholder, new))
                changed += count
        for placeholder, new in placeholders:
            _replace_across_text_nodes(paragraph, placeholder, new)
    return changed


def _object_reference_match_allowed(text: str, start: int, end: int) -> bool:
    del start
    return re.match(r"\s*(?:[-－—.．]\s*)?\d", text[end:]) is None


def _object_number_variants(number: str) -> tuple[str, ...]:
    normalized = _normalize_object_number(number)
    if "-" not in normalized:
        return (normalized,)
    parts = normalized.split("-")
    variants = ["-".join(parts)]
    variants.extend(separator.join(parts) for separator in ("－", "—", ".", "．"))
    return tuple(dict.fromkeys(variants))


def _cleanup_template_residue(
    *,
    body: ET.Element,
    current_body_elements: list[ET.Element],
    semantic_by_element: dict[int, list[JsonObject]],
) -> dict[str, int]:
    removed = _remove_duplicate_template_body_heading(
        body=body,
        current_body_elements=current_body_elements,
        semantic_by_element=semantic_by_element,
    )
    cleaned = 0
    for paragraph in list(body.findall(_q(W_NS, "p"))):
        if semantic_by_element.get(id(paragraph)):
            continue
        text = _paragraph_text(paragraph).strip()
        if _is_template_residue_paragraph(text):
            body.remove(paragraph)
            removed += 1
            continue
        if _clean_keywords_instruction(paragraph):
            cleaned += 1
    return {"removed": removed, "cleaned": cleaned}


def _collapse_redundant_back_matter_breaks(body: ET.Element) -> int:
    removed = 0
    paragraphs = body.findall(_q(W_NS, "p"))
    for index, paragraph in enumerate(paragraphs):
        compact = _compact_heading_text(_paragraph_text(paragraph))
        if compact != "参考文献":
            continue
        blanks: list[ET.Element] = []
        scan = index - 1
        while scan >= 0 and not _paragraph_text(paragraphs[scan]).strip():
            blanks.append(paragraphs[scan])
            scan -= 1
        for blank in blanks:
            if not _is_redundant_middle_section_break(blank, blanks):
                continue
            if blank not in list(body):
                continue
            body.remove(blank)
            removed += 1
    return removed


def _is_redundant_middle_section_break(
    paragraph: ET.Element,
    blank_run: list[ET.Element],
) -> bool:
    if paragraph.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'sectPr')}") is None:
        return False
    if _has_page_break(paragraph):
        return False
    index = blank_run.index(paragraph)
    return any(_has_page_break(item) for item in blank_run[:index]) and any(
        _has_page_break(item) for item in blank_run[index + 1 :]
    )


def _has_page_break(paragraph: ET.Element) -> bool:
    return any(br.get(_q(W_NS, "type")) == "page" for br in paragraph.iter(_q(W_NS, "br")))


def _remove_duplicate_template_body_heading(
    *,
    body: ET.Element,
    current_body_elements: list[ET.Element],
    semantic_by_element: dict[int, list[JsonObject]],
) -> int:
    first_body = next(
        (
            item
            for item in current_body_elements
            if item.tag == _q(W_NS, "p") and semantic_by_element.get(id(item))
        ),
        None,
    )
    if first_body is None:
        return 0
    children = list(body)
    if first_body not in children:
        return 0
    first_index = children.index(first_body)
    if first_index == 0:
        return 0
    previous = children[first_index - 1]
    if previous.tag != _q(W_NS, "p") or semantic_by_element.get(id(previous)):
        return 0
    if _compact_heading_text(_paragraph_text(previous)) != _compact_heading_text(
        _paragraph_text(first_body)
    ):
        return 0
    body.remove(previous)
    return 1


def _compact_heading_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _is_template_residue_paragraph(text: str) -> bool:
    compact = _compact_heading_text(text)
    return bool(compact and ("【未细分的相关学术成果】" in text or compact == "第X章结论与展望"))


def _clean_keywords_instruction(paragraph: ET.Element) -> bool:
    original = _paragraph_text(paragraph).strip()
    match = _KEYWORDS_INSTRUCTION.match(original)
    if match is None:
        return False
    value = match.group("value").strip()
    cleaned = f"关键词：{value}"
    if cleaned == original:
        return False
    _replace_paragraph_text(paragraph, cleaned)
    return True


def _materialize_back_matter_generated_content(
    *,
    body: ET.Element,
    body_style_id: str,
    caption_style_id: str,
    appendix_table_chapter: int,
) -> dict[str, int]:
    cleaned = _clean_appendix_heading(body)
    cleaned += _remove_back_matter_placeholder_residue(body)
    _ = (body_style_id, caption_style_id, appendix_table_chapter)
    return {"cleaned": cleaned, "inserted": 0}


def _clean_appendix_heading(body: ET.Element) -> int:
    cleaned = 0
    for paragraph in body.findall(_q(W_NS, "p")):
        compact = _compact_heading_text(_paragraph_text(paragraph))
        if compact != "附录附录":
            continue
        _replace_paragraph_text(paragraph, "附  录")
        cleaned += 1
    return cleaned


def _remove_back_matter_placeholder_residue(body: ET.Element) -> int:
    markers = (
        "【请填写中文表名】",
        "[Please fill in the English table title]",
        "【此处为选填部分；有学术成果请补充，无内容可删除本页。】",
    )
    removed = 0
    for paragraph in list(body.findall(_q(W_NS, "p"))):
        text = _paragraph_text(paragraph).strip()
        if not any(marker in text for marker in markers):
            continue
        body.remove(paragraph)
        removed += 1
    return removed


def _clear_section_gutters(document: ET.Element) -> int:
    cleared = 0
    for section_properties in document.iter(_q(W_NS, "sectPr")):
        margins = section_properties.find(_q(W_NS, "pgMar"))
        if margins is None:
            continue
        current = margins.get(_q(W_NS, "gutter"))
        if current in {None, "", "0"}:
            continue
        margins.set(_q(W_NS, "gutter"), "0")
        cleared += 1
    return cleared


def _ensure_appendix_table_caption_placeholders(
    body: ET.Element,
    *,
    caption_style_id: str,
    appendix_table_chapter: int,
) -> int:
    children = list(body)
    appendix_index = next(
        (
            index
            for index, child in enumerate(children)
            if child.tag == _q(W_NS, "p")
            and _compact_heading_text(_paragraph_text(child)) == "附录"
        ),
        None,
    )
    if appendix_index is None:
        return 0
    table_index = next(
        (
            index
            for index, child in enumerate(children[appendix_index + 1 :], start=appendix_index + 1)
            if child.tag == _q(W_NS, "tbl")
        ),
        None,
    )
    if table_index is None:
        return 0
    previous_text = [
        _paragraph_text(child).strip()
        for child in children[max(appendix_index + 1, table_index - 2) : table_index]
        if child.tag == _q(W_NS, "p") and _paragraph_text(child).strip()
    ]
    if any(text.startswith(("表 ", "Table ")) for text in previous_text):
        return 0
    captions = (
        f"表 {appendix_table_chapter}-1【请填写中文表名】",
        f"Table {appendix_table_chapter}-1 [Please fill in the English table title]",
    )
    for offset, text in enumerate(captions):
        paragraph = _generated_paragraph(body, text)
        _normalize_caption(paragraph, caption_style_id)
        body.insert(table_index + offset, paragraph)
    return len(captions)


def _ensure_academic_achievements_placeholder(body: ET.Element, body_style_id: str) -> int:
    children = list(body)
    heading_index = next(
        (
            index
            for index, child in enumerate(children)
            if child.tag == _q(W_NS, "p")
            and _compact_heading_text(_paragraph_text(child)) == "相关的学术成果目录"
        ),
        None,
    )
    if heading_index is None:
        return 0
    next_nonempty = next(
        (
            child
            for child in children[heading_index + 1 :]
            if child.tag == _q(W_NS, "p") and _paragraph_text(child).strip()
        ),
        None,
    )
    if (
        next_nonempty is not None
        and _compact_heading_text(_paragraph_text(next_nonempty)) != "致谢"
    ):
        return 0
    paragraph = _generated_paragraph(
        body,
        "【此处为选填部分；有学术成果请补充，无内容可删除本页。】",
    )
    _normalize_text_paragraph(paragraph, body_style_id)
    body.insert(heading_index + 1, paragraph)
    return 1


def _generated_paragraph(body: ET.Element, text: str) -> ET.Element:
    paragraph = ET.Element(_q(W_NS, "p"))
    _assign_new_para_id(body, paragraph)
    run = ET.SubElement(paragraph, _q(W_NS, "r"))
    text_node = ET.SubElement(run, _q(W_NS, "t"))
    text_node.text = text
    _preserve_space(text_node)
    return paragraph


def _looks_english_caption(value: str) -> bool:
    stripped = value.lstrip()
    if stripped.startswith(("图", "表")):
        return False
    if re.match(r"(?i)(?:fig\.?|figure|table)\b", stripped):
        return True
    ascii_letters = sum(1 for char in stripped if char.isascii() and char.isalpha())
    cjk_chars = len(_CJK.findall(stripped))
    return ascii_letters > cjk_chars * 2 and ascii_letters >= 4


def _chinese_ordinal(number: int) -> str:
    if number <= 0:
        return str(number)
    digits = "零一二三四五六七八九"
    if number < 10:
        return digits[number]
    if number == 10:
        return "十"
    if number < 20:
        return "十" + digits[number % 10]
    if number < 100:
        tens, ones = divmod(number, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    return str(number)


def _replace_paragraph_text(paragraph: ET.Element, value: str) -> None:
    safe_value = _xml_safe_text(value)
    nodes = list(paragraph.iter(_q(W_NS, "t")))
    if not nodes:
        run = ET.SubElement(paragraph, _q(W_NS, "r"))
        text = ET.SubElement(run, _q(W_NS, "t"))
        text.text = safe_value
        _preserve_space(text)
        return
    nodes[0].text = safe_value
    _preserve_space(nodes[0])
    for node in nodes[1:]:
        node.text = ""


def _replace_semantic_paragraph_text(paragraph: ET.Element, value: str) -> int:
    field_residue_count = sum(
        1
        for element in paragraph.iter()
        if element.tag.rsplit("}", 1)[-1] in {"fldChar", "fldSimple", "instrText"}
    )
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    for child in list(paragraph):
        if child is not p_pr:
            paragraph.remove(child)
    run = ET.SubElement(paragraph, _q(W_NS, "r"))
    text = ET.SubElement(run, _q(W_NS, "t"))
    text.text = _xml_safe_text(value)
    _preserve_space(text)
    return field_residue_count


_XML10_INVALID_TEXT = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _xml_safe_text(value: str) -> str:
    return _XML10_INVALID_TEXT.sub("", value)


def _drawing_residue_count(paragraph: ET.Element) -> int:
    return sum(1 for _ in paragraph.iter(_q(W_NS, "drawing"))) + sum(
        1 for _ in paragraph.iter(_q(W_NS, "pict"))
    )


def _normalize_drawing_paragraph(
    paragraph: ET.Element, normal_style: str, usable_width_dxa: int | None
) -> dict[str, int]:
    p_pr = _reset_p_pr(paragraph, normal_style)
    _ordered_child(p_pr, "keepLines")
    _set_child_value(p_pr, "jc", "center")
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "before"), "0")
    spacing.set(_q(W_NS, "after"), "0")
    spacing.set(_q(W_NS, "line"), "240")
    spacing.set(_q(W_NS, "lineRule"), "auto")
    converted = 0
    repaired = 0
    for drawing in paragraph.iter(_q(W_NS, "drawing")):
        for parent in drawing.iter():
            for anchor in list(parent):
                if anchor.tag == _q(WP_NS, "anchor"):
                    index = list(parent).index(anchor)
                    parent.remove(anchor)
                    parent.insert(index, _anchor_to_inline(anchor))
                    converted += 1
        if usable_width_dxa is not None:
            repaired += _clamp_drawing(drawing, usable_width_dxa * 635)
    return {
        "floating_drawings_converted_inline": converted,
        "image_geometry_repairs": repaired,
    }


def _normalize_drawing_container(
    element: ET.Element,
    normal_style: str,
    usable_width_dxa: int | None,
) -> dict[str, int]:
    result = {
        "floating_drawings_converted_inline": 0,
        "image_geometry_repairs": 0,
    }
    for paragraph in element.iter(_q(W_NS, "p")):
        if not list(paragraph.iter(_q(W_NS, "drawing"))):
            continue
        drawing_result = _normalize_drawing_paragraph(
            paragraph,
            normal_style,
            usable_width_dxa,
        )
        result["floating_drawings_converted_inline"] += drawing_result[
            "floating_drawings_converted_inline"
        ]
        result["image_geometry_repairs"] += drawing_result["image_geometry_repairs"]
    return result


def _split_drawing_paragraph(
    body: ET.Element,
    paragraph: ET.Element,
    normal_style: str,
) -> list[ET.Element]:
    drawings = list(paragraph.iter(_q(W_NS, "drawing")))
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
    insert_at = index + 1
    for offset, image_paragraph in enumerate(image_paragraphs):
        body.insert(insert_at + offset, image_paragraph)
    return image_paragraphs


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


def _clamp_drawing(drawing: ET.Element, max_width_emu: int) -> int:
    inline = next(drawing.iter(_q(WP_NS, "inline")), None)
    if inline is None:
        return 0
    extent = inline.find(_q(WP_NS, "extent"))
    if extent is None:
        return 0
    try:
        width = int(extent.get("cx", "0"))
        height = int(extent.get("cy", "0"))
    except ValueError:
        return 0
    if width <= 0:
        width = max_width_emu
    if height <= 0:
        height = round(width * 0.5625)
    new_width = min(width, max_width_emu)
    new_height = round(height * new_width / width) if width else height
    min_height = round(new_width / 20)
    if new_height < min_height:
        new_height = round(new_width * 0.5625)
    if new_width == width and new_height == height:
        return 0
    extent.set("cx", str(new_width))
    extent.set("cy", str(new_height))
    for transform_extent in drawing.iter(_q(A_NS, "ext")):
        if transform_extent.get("cx") is not None:
            transform_extent.set("cx", str(new_width))
            transform_extent.set("cy", str(new_height))
    return 1


def _normalize_table(
    table: ET.Element,
    usable_width_dxa: int | None,
    *,
    target_width_dxa: int | None = None,
) -> int:
    row_property_exceptions_removed = 0
    materialized_width = _materialized_table_width_dxa(
        usable_width_dxa,
        target_width_dxa,
    )
    tbl_pr = table.find(_q(W_NS, "tblPr"))
    if tbl_pr is None:
        tbl_pr = ET.Element(_q(W_NS, "tblPr"))
        table.insert(0, tbl_pr)
    _remove_children(tbl_pr, {"tblW", "tblLayout", "jc", "tblInd", "tblCellMar"})
    if materialized_width is not None:
        width = _ordered_child(tbl_pr, "tblW")
        width.set(_q(W_NS, "type"), "dxa")
        width.set(_q(W_NS, "w"), str(materialized_width))
    layout = _ordered_child(tbl_pr, "tblLayout")
    layout.set(_q(W_NS, "type"), "fixed")
    _set_child_value(tbl_pr, "jc", "center")
    _materialize_three_line_table_properties(tbl_pr)
    grid = table.find(_q(W_NS, "tblGrid"))
    if materialized_width is not None and grid is not None:
        columns = grid.findall(_q(W_NS, "gridCol"))
        source_widths = [int(item.get(_q(W_NS, "w"), "0")) for item in columns]
        total = sum(source_widths)
        if total > 0:
            scaled = [round(value * materialized_width / total) for value in source_widths]
            if scaled:
                scaled[-1] += materialized_width - sum(scaled)
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
                        tc_w = _ordered_child(tc_pr, "tcW")
                    else:
                        _move_ordered(tc_pr, tc_w)
                    tc_w.set(_q(W_NS, "type"), "dxa")
                    tc_w.set(_q(W_NS, "w"), str(value))
    rows = table.findall(_q(W_NS, "tr"))
    for row_index, row in enumerate(rows):
        for child in list(row):
            if child.tag == _q(W_NS, "tblPrEx"):
                row.remove(child)
                row_property_exceptions_removed += 1
        tr_pr = row.find(_q(W_NS, "trPr"))
        if tr_pr is None:
            tr_pr = ET.Element(_q(W_NS, "trPr"))
            _insert_ordered(row, tr_pr)
        else:
            _move_ordered(row, tr_pr)
        if tr_pr.find(_q(W_NS, "cantSplit")) is None:
            _ordered_child(tr_pr, "cantSplit")
        if row_index == 0:
            _ordered_child(tr_pr, "tblHeader")
        else:
            _remove_children(tr_pr, {"tblHeader"})
        _set_child_value(tr_pr, "jc", "center")
        for cell in row.findall(_q(W_NS, "tc")):
            _materialize_body_table_cell(cell, is_header=row_index == 0)
    return row_property_exceptions_removed


def _template_reference_table_width_dxa(
    document: ET.Element,
    *,
    ignored_tables: set[int],
) -> int | None:
    for table in document.iter(_q(W_NS, "tbl")):
        if id(table) in ignored_tables:
            continue
        width = table.find(f"{_q(W_NS, 'tblPr')}/{_q(W_NS, 'tblW')}")
        if width is None or width.get(_q(W_NS, "type")) != "dxa":
            continue
        try:
            value = int(width.get(_q(W_NS, "w"), "0"))
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def _materialized_table_width_dxa(
    usable_width_dxa: int | None,
    target_width_dxa: int | None,
) -> int | None:
    candidates = [
        value
        for value in (usable_width_dxa, target_width_dxa, _TARGET_BODY_TABLE_WIDTH_DXA)
        if value is not None and value > 0
    ]
    return min(candidates) if candidates else None


def _materialize_three_line_table_properties(tbl_pr: ET.Element) -> None:
    borders = _ordered_child(tbl_pr, "tblBorders")
    _remove_children(
        borders,
        {"top", "left", "bottom", "right", "insideH", "insideV", "tl2br", "tr2bl"},
    )
    for name, attrs in (
        ("top", {"val": "single", "sz": "8", "space": "0", "color": "000000"}),
        ("left", {"val": "nil"}),
        ("bottom", {"val": "single", "sz": "8", "space": "0", "color": "000000"}),
        ("right", {"val": "nil"}),
        ("insideH", {"val": "nil"}),
        ("insideV", {"val": "nil"}),
    ):
        border = ET.SubElement(borders, _q(W_NS, name))
        for key, value in attrs.items():
            border.set(_q(W_NS, key), value)

    look = _ordered_child(tbl_pr, "tblLook")
    for key, value in {
        "val": "04A0",
        "firstRow": "1",
        "lastRow": "0",
        "firstColumn": "1",
        "lastColumn": "0",
        "noHBand": "0",
        "noVBand": "1",
    }.items():
        look.set(_q(W_NS, key), value)


def _materialize_body_table_cell(cell: ET.Element, *, is_header: bool) -> None:
    tc_pr = cell.find(_q(W_NS, "tcPr"))
    if tc_pr is None:
        tc_pr = ET.Element(_q(W_NS, "tcPr"))
        cell.insert(0, tc_pr)
    _set_child_value(tc_pr, "vAlign", "center")
    if is_header:
        borders = _ordered_child(tc_pr, "tcBorders")
        _remove_children(
            borders,
            {"top", "left", "bottom", "right", "insideH", "insideV", "tl2br", "tr2bl"},
        )
        bottom = ET.SubElement(borders, _q(W_NS, "bottom"))
        for key, value in {
            "val": "single",
            "sz": "4",
            "space": "0",
            "color": "000000",
        }.items():
            bottom.set(_q(W_NS, key), value)
    else:
        _remove_children(tc_pr, {"tcBorders"})
    for paragraph in cell.findall(_q(W_NS, "p")):
        _normalize_table_cell_paragraph(paragraph)


def _normalize_table_cell_paragraph(paragraph: ET.Element) -> None:
    p_pr = _ensure_p_pr(paragraph)
    for child in list(p_pr):
        p_pr.remove(child)
    _disable_auto_spacing(p_pr)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "line"), "300")
    spacing.set(_q(W_NS, "lineRule"), "exact")
    _set_child_value(p_pr, "jc", "center")
    _ordered_child(p_pr, "rPr")

    for run in paragraph.findall(_q(W_NS, "r")):
        superscript, subscript, italic = _direct_run_inline_semantics(run)
        r_pr = run.find(_q(W_NS, "rPr"))
        if r_pr is None:
            r_pr = ET.Element(_q(W_NS, "rPr"))
            run.insert(0, r_pr)
        else:
            for child in list(r_pr):
                r_pr.remove(child)
        if italic:
            ET.SubElement(r_pr, _q(W_NS, "i"))
            ET.SubElement(r_pr, _q(W_NS, "iCs"))
        color = ET.SubElement(r_pr, _q(W_NS, "color"))
        color.set(_q(W_NS, "val"), "000000")
        size = ET.SubElement(r_pr, _q(W_NS, "szCs"))
        size.set(_q(W_NS, "val"), "21")
        if superscript:
            _append_run_property(r_pr, "vertAlign", {"val": "superscript"})
        elif subscript:
            _append_run_property(r_pr, "vertAlign", {"val": "subscript"})
    _materialize_table_cell_inline_semantics(paragraph)


def _materialize_table_cell_inline_semantics(paragraph: ET.Element) -> int:
    value = _paragraph_text(paragraph)
    if not value:
        return 0
    spans = [*_source_inline_semantic_spans(paragraph), *_target_body_inline_semantic_spans(value)]
    if not spans:
        return 0
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    preserved_p_pr = copy.deepcopy(p_pr) if p_pr is not None else None
    for child in list(paragraph):
        paragraph.remove(child)
    if preserved_p_pr is not None:
        paragraph.append(preserved_p_pr)
    breakpoints = sorted(
        {0, len(value), *(span.start for span in spans), *(span.end for span in spans)}
    )
    for start, end in zip(breakpoints, breakpoints[1:], strict=False):
        if start == end:
            continue
        active = [span for span in spans if span.start < end and start < span.end]
        superscript = any(span.superscript for span in active)
        subscript = any(span.subscript for span in active) and not superscript
        italic = any(span.italic for span in active)
        _append_table_cell_text_run(
            paragraph,
            value[start:end],
            superscript=superscript,
            subscript=subscript,
            italic=italic,
        )
    return len(spans)


def _append_table_cell_text_run(
    paragraph: ET.Element,
    text: str,
    *,
    superscript: bool = False,
    subscript: bool = False,
    italic: bool = False,
) -> None:
    if not text:
        return
    run = ET.SubElement(paragraph, _q(W_NS, "r"))
    r_pr = ET.SubElement(run, _q(W_NS, "rPr"))
    if italic:
        ET.SubElement(r_pr, _q(W_NS, "i"))
        ET.SubElement(r_pr, _q(W_NS, "iCs"))
    _append_run_property(r_pr, "color", {"val": "000000"})
    _append_run_property(r_pr, "szCs", {"val": "21"})
    if superscript:
        _append_run_property(r_pr, "vertAlign", {"val": "superscript"})
    elif subscript:
        _append_run_property(r_pr, "vertAlign", {"val": "subscript"})
    text_node = ET.SubElement(run, _q(W_NS, "t"))
    text_node.text = text
    _preserve_space(text_node)


def _place_table_captions_before_tables(
    body: ET.Element,
    relations: list[JsonObject],
    content_targets: dict[str, ET.Element],
    semantic_by_content_id: dict[str, JsonObject],
) -> int:
    captions_by_target: dict[str, list[ET.Element]] = {}
    for relation in relations:
        if relation.get("relation_type") != "caption_of":
            continue
        if _caption_relation_kind(relation, semantic_by_content_id) != "table":
            continue
        source_id = relation.get("source_content_id")
        target_id = relation.get("target_content_id")
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            continue
        caption = content_targets.get(source_id)
        target = content_targets.get(target_id)
        if caption is None or target is None or target.tag != _q(W_NS, "tbl"):
            continue
        captions_by_target.setdefault(target_id, []).append(caption)

    moved = 0
    for target_id, captions in captions_by_target.items():
        target = content_targets.get(target_id)
        if target is None:
            continue
        children = list(body)
        if target not in children or any(caption not in children for caption in captions):
            continue
        target_index = children.index(target)
        expected = children[target_index - len(captions) : target_index]
        if len(expected) == len(captions) and expected == captions:
            continue
        for caption in captions:
            body.remove(caption)
        insert_at = list(body).index(target)
        for offset, caption in enumerate(captions):
            body.insert(insert_at + offset, caption)
        moved += 1
    return moved


def _bind_semantic_relations(
    body: ET.Element,
    relations: list[JsonObject],
    content_targets: dict[str, ET.Element],
    semantic_by_content_id: dict[str, JsonObject],
) -> dict[str, int]:
    """Apply pagination bonds from explicit semantic relations without text guessing."""

    counts = {"figure": 0, "table": 0}
    children = list(body)
    captions_by_target: dict[str, list[ET.Element]] = {}
    for relation in relations:
        if relation.get("relation_type") != "caption_of":
            continue
        source_id = relation.get("source_content_id")
        target_id = relation.get("target_content_id")
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            raise _invalid(
                "projection_semantic_relation_invalid",
                "A caption relation lacks content identities.",
            )
        caption = content_targets.get(source_id)
        target = content_targets.get(target_id)
        if caption is None or target is None or caption not in children or target not in children:
            raise _invalid(
                "projection_semantic_relation_stale",
                "A caption relation does not resolve to imported content.",
            )
        caption_index = children.index(caption)
        target_index = children.index(target)
        kind = _caption_relation_kind(relation, semantic_by_content_id)
        if kind is None:
            raise _invalid(
                "projection_semantic_caption_target_invalid",
                "A caption relation must target a figure or table content item.",
            )
        if kind == "table" and target.tag != _q(W_NS, "tbl"):
            raise _invalid(
                "projection_semantic_caption_target_invalid",
                "A table caption relation must target a table content item.",
            )
        if kind == "figure" and not list(target.iter(_q(W_NS, "drawing"))):
            raise _invalid(
                "projection_semantic_caption_target_invalid",
                "A figure caption relation must target a drawing content item.",
            )
        if caption_index < target_index:
            if caption.tag != _q(W_NS, "p"):
                raise _invalid(
                    "projection_semantic_caption_invalid",
                    "A caption content item must resolve to a paragraph.",
                )
            _set_paragraph_flag(caption, "keepNext", True)
        elif target.tag == _q(W_NS, "p"):
            _set_paragraph_flag(target, "keepNext", True)
        else:
            last_paragraph = next(reversed(list(target.iter(_q(W_NS, "p")))), None)
            if last_paragraph is not None:
                _set_paragraph_flag(last_paragraph, "keepNext", True)
        captions_by_target.setdefault(target_id, []).append(caption)
        counts[kind] += 1
    for captions in captions_by_target.values():
        ordered = sorted(captions, key=children.index)
        for caption in ordered[:-1]:
            _set_paragraph_flag(caption, "keepNext", True)
    return counts


def _caption_relation_kind(
    relation: JsonObject,
    semantic_by_content_id: dict[str, JsonObject],
) -> str | None:
    target_id = relation.get("target_content_id")
    source_id = relation.get("source_content_id")
    target_field_id = (
        semantic_by_content_id.get(target_id, {}).get("field_id")
        if isinstance(target_id, str)
        else None
    )
    if target_field_id == "body.figure":
        return "figure"
    if target_field_id == "body.table":
        return "table"
    source_field_id = (
        semantic_by_content_id.get(source_id, {}).get("field_id")
        if isinstance(source_id, str)
        else None
    )
    if source_field_id == "body.figure.caption":
        return "figure"
    if source_field_id == "body.table.caption":
        return "table"
    return None


def _materialize_toc_cache(
    *,
    parts: dict[str, bytes],
    document: ET.Element,
    body: ET.Element,
    body_entries: list[JsonObject],
    source_toc_entries: list[JsonObject],
) -> JsonObject:
    update = _request_toc_update(parts, document)
    available_style_ids = _style_ids(_xml(parts, "word/styles.xml"))
    toc_heading = _find_toc_heading(body)
    if toc_heading is None:
        return {
            **update,
            "static_toc_materialized": False,
            "static_toc_entries": 0,
        }
    toc_cache = _toc_cache_scan(body, toc_heading)
    if toc_cache is None:
        return {
            **update,
            "static_toc_materialized": False,
            "static_toc_entries": 0,
        }
    _normalize_toc_heading(toc_heading)
    entries = _toc_entries_for_document(body_entries, body, source_toc_entries)
    line_elements = cast(list[ET.Element], toc_cache["line_elements"])
    for child in line_elements:
        body.remove(child)
    insert_at = list(body).index(cast(ET.Element, toc_cache["insert_anchor"])) + 1
    prototypes = cast(dict[str, ET.Element], toc_cache["prototypes"])
    for offset, entry in enumerate(entries):
        paragraph = _toc_paragraph(
            entry,
            prototypes,
            available_style_ids=available_style_ids,
            field_position=_toc_field_position(offset, len(entries)),
        )
        body.insert(insert_at + offset, paragraph)
    removed_style_definitions = _remove_toc_cache_style_definitions(parts)
    return {
        **update,
        "static_toc_materialized": True,
        "static_toc_entries": len(entries),
        "static_toc_old_paragraphs_removed": len(line_elements),
        "static_toc_style_definitions_removed": removed_style_definitions,
        "word_refresh_still_requires_canonical_word_verification": False,
    }


def _existing_toc_cache(body: ET.Element) -> JsonObject | None:
    toc_heading = _find_toc_heading(body)
    if toc_heading is None:
        return None
    return _toc_cache_scan(body, toc_heading, parse_entries=True)


def _toc_cache_scan(
    body: ET.Element,
    toc_heading: ET.Element,
    *,
    parse_entries: bool = False,
) -> JsonObject | None:
    children = list(body)
    start = children.index(toc_heading) + 1
    cursor = start
    prototypes: dict[str, ET.Element] = {}
    line_elements: list[ET.Element] = []
    entries: list[JsonObject] = []
    insert_anchor = toc_heading
    while cursor < len(children):
        child = children[cursor]
        if child.tag != _q(W_NS, "p"):
            break
        text = _paragraph_text(child).strip()
        if not text:
            if not line_elements:
                insert_anchor = child
            cursor += 1
            continue
        if not _looks_like_toc_cache_line(text):
            break
        role = _toc_cache_role(child, text)
        prototypes.setdefault(role, child)
        line_elements.append(child)
        if parse_entries:
            split = _split_toc_text_and_page(text)
            if split is not None:
                label, page = split
                entries.append(
                    {
                        "role": role,
                        "text": _normalize_toc_label(label),
                        "page": page,
                    }
                )
        cursor += 1
    if not line_elements or (parse_entries and not entries):
        return None
    result: JsonObject = {
        "heading": toc_heading,
        "start": start,
        "end": cursor,
        "insert_anchor": insert_anchor,
        "line_elements": line_elements,
        "prototypes": prototypes,
    }
    if parse_entries:
        result["entries"] = entries
    return result


def _toc_entries_with_render_pages(
    entries: list[JsonObject],
    pdf_text: JsonObject,
) -> list[JsonObject]:
    pages = pdf_text.get("pages")
    if not isinstance(pages, list):
        raise _invalid(
            "projection_pdf_text_pages_invalid",
            "Rendered PDF text index has no pages array.",
        )
    body_start = _render_body_start_page(entries, pages)
    result: list[JsonObject] = []
    for entry in entries:
        text = str(entry.get("text", "")).strip()
        role = str(entry.get("role", "heading_1"))
        page = str(entry.get("page", ""))
        if _toc_key(text) not in {_toc_key("摘  要"), _toc_key("ABSTRACT")}:
            rendered = _rendered_page_for_toc_label(text, pages, body_start=body_start)
            if rendered is not None:
                page = rendered
        result.append({**entry, "role": role, "text": text, "page": page})
    return result


def _render_body_start_page(entries: list[JsonObject], pages: list[object]) -> int:
    body_labels = [
        str(entry.get("text", ""))
        for entry in entries
        if str(entry.get("role")) == "heading_1"
        and _toc_key(str(entry.get("text", ""))) not in {_toc_key("摘  要"), _toc_key("ABSTRACT")}
    ]
    for label in body_labels:
        compact = _compact_heading_text(label)
        if not compact:
            continue
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_number = page.get("page")
            text = page.get("text")
            if not isinstance(page_number, int) or not isinstance(text, str):
                continue
            if page_number <= 5 or _compact_heading_text("目录") in _compact_heading_text(text):
                continue
            if compact in _compact_heading_text(text):
                return page_number
    return 1


def _rendered_page_for_toc_label(
    label: str,
    pages: list[object],
    *,
    body_start: int,
) -> str | None:
    compact = _compact_heading_text(label)
    if not compact:
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_number = page.get("page")
        text = page.get("text")
        if not isinstance(page_number, int) or not isinstance(text, str):
            continue
        if page_number < body_start:
            continue
        if compact not in _compact_heading_text(text):
            continue
        return _rendered_footer_page_label(page) or str(page_number - body_start + 1)
    return None


def _rendered_footer_page_label(page: JsonObject) -> str | None:
    words = page.get("words")
    if not isinstance(words, list):
        return None
    try:
        width = float(page.get("width_pt", 0))
        height = float(page.get("height_pt", 0))
    except (TypeError, ValueError):
        return None
    candidates: list[tuple[float, str]] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        text = word.get("text")
        bbox = word.get("bbox_pdf")
        if not isinstance(text, str) or not isinstance(bbox, list) or len(bbox) != 4:
            continue
        if re.fullmatch(r"(?:\d+|[IVXLCDM]+)", text.strip()) is None:
            continue
        try:
            x0, y0, x1, y1 = (float(value) for value in bbox)
        except (TypeError, ValueError):
            continue
        center_x = (x0 + x1) / 2
        if y0 < height - 80 or abs(center_x - width / 2) > 80:
            continue
        candidates.append((y1, text.strip()))
    if not candidates:
        return None
    return max(candidates)[1]


def _source_toc_entries(source_docx: Path | None) -> list[JsonObject]:
    if source_docx is None:
        return []
    try:
        parts = _read_package(source_docx)
        document = _xml(parts, "word/document.xml")
    except (OSError, KeyError, ET.ParseError, ToolFailure):
        return []
    body = document.find(_q(W_NS, "body"))
    if body is None:
        return []
    paragraphs = [item for item in body.findall(_q(W_NS, "p"))]
    start = next(
        (
            index
            for index, paragraph in enumerate(paragraphs)
            if _compact_heading_text(_paragraph_text(paragraph)) == "目录"
        ),
        None,
    )
    if start is None:
        return []
    entries: list[JsonObject] = []
    for paragraph in paragraphs[start + 1 :]:
        text = _paragraph_text(paragraph).strip()
        if not text:
            continue
        split = _split_toc_text_and_page(text)
        if split is None:
            if entries:
                break
            continue
        label, page = split
        normalized = _normalize_toc_label(label)
        entries.append({"label": normalized, "key": _toc_key(normalized), "page": page})
        if _toc_key(_normalize_toc_label(label)) == _toc_key("致  谢"):
            break
    return entries


def _source_toc_page_map(source_docx: Path | None) -> dict[str, str]:
    pages: dict[str, str] = {}
    for entry in _source_toc_entries(source_docx):
        key = entry.get("key")
        page = entry.get("page")
        if isinstance(key, str) and isinstance(page, str):
            pages.setdefault(key, page)
    return pages


def _find_toc_heading(body: ET.Element) -> ET.Element | None:
    for paragraph in body.findall(_q(W_NS, "p")):
        if _compact_heading_text(_paragraph_text(paragraph)) == "目录":
            return paragraph
    return None


def _looks_like_toc_cache_line(text: str) -> bool:
    if "【" in text or "第X章" in text:
        return True
    return _split_toc_text_and_page(text) is not None


def _toc_cache_role(paragraph: ET.Element, text: str) -> str:
    style = paragraph.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'pStyle')}")
    style_id = style.get(_q(W_NS, "val")) if style is not None else ""
    style_id = style_id or ""
    if style_id == "30" or style_id.endswith("3") or re.match(r"\s*\d+\.\d+", text):
        return "heading_3"
    if style_id == "25" or style_id.endswith("2") or re.match(r"\s*\d+\s+", text):
        return "heading_2"
    return "heading_1"


def _toc_entries_for_document(
    body_entries: list[JsonObject],
    body: ET.Element,
    source_toc_entries: list[JsonObject],
) -> list[JsonObject]:
    source_pages = _TocPageCursor(source_toc_entries)
    entries: list[JsonObject] = [
        {
            "role": "heading_1",
            "text": "摘  要",
            "page": source_pages.consume("摘  要", "I"),
        },
        {
            "role": "heading_1",
            "text": "ABSTRACT",
            "page": source_pages.consume("ABSTRACT", "II"),
        },
    ]
    last_page = "1"
    for entry in body_entries:
        text = _normalize_toc_label(str(entry.get("text", "")).strip())
        if not text:
            continue
        page = source_pages.consume(text, last_page)
        last_page = page
        entries.append({"role": str(entry.get("role", "heading_1")), "text": text, "page": page})
    for label in _back_matter_toc_labels(body):
        page = source_pages.consume(label, last_page)
        last_page = page
        entries.append({"role": "heading_1", "text": label, "page": page})
    return entries


class _TocPageCursor:
    def __init__(self, entries: list[JsonObject]) -> None:
        self._entries = list(entries)

    def consume(self, label: str, fallback: str) -> str:
        key = _toc_key(label)
        for index, entry in enumerate(self._entries):
            if entry.get("key") != key:
                continue
            page = entry.get("page")
            del self._entries[index]
            return page if isinstance(page, str) else fallback
        return fallback


def _back_matter_toc_labels(body: ET.Element) -> list[str]:
    wanted = (
        ("参考文献", "参考文献"),
        ("附录", "附  录"),
        ("相关的学术成果目录", "相关的学术成果目录"),
        ("致谢", "致  谢"),
    )
    labels: list[str] = []
    paragraphs = body.findall(_q(W_NS, "p"))
    for compact, label in wanted:
        if any(
            _compact_heading_text(_paragraph_text(paragraph)) == compact for paragraph in paragraphs
        ):
            labels.append(label)
    return labels


def _toc_paragraph(
    entry: JsonObject,
    prototypes: dict[str, ET.Element],
    *,
    available_style_ids: set[str] | None = None,
    field_position: str = "middle",
) -> ET.Element:
    role = str(entry.get("role", "heading_1"))
    prototype = prototypes.get(role)
    if prototype is None:
        prototype = prototypes.get("heading_1")
    paragraph = copy.deepcopy(prototype) if prototype is not None else ET.Element(_q(W_NS, "p"))
    _set_toc_paragraph_style(
        paragraph,
        role,
        prototype_has_style=prototype is not None
        and prototype.find(f"{_q(W_NS, 'pPr')}/{_q(W_NS, 'pStyle')}") is not None,
        available_style_ids=available_style_ids or set(),
    )
    _normalize_toc_cache_paragraph_properties(paragraph)
    result_run_pr = _toc_result_run_properties(paragraph)
    prefix_runs, suffix_runs = _toc_field_boundary_runs(paragraph)
    include_prefix = field_position in {"first", "only"}
    include_suffix = field_position in {"last", "only"}
    if include_prefix and not _runs_have_field_char(prefix_runs, "begin"):
        prefix_runs = _default_toc_field_prefix_runs()
    if include_suffix and not _runs_have_field_char(suffix_runs, "end"):
        suffix_runs = [_toc_field_char_run("end")]

    preserved_p_pr = copy.deepcopy(paragraph.find(_q(W_NS, "pPr")))
    paragraph.clear()
    if preserved_p_pr is not None:
        paragraph.append(preserved_p_pr)
    if include_prefix:
        paragraph.extend(prefix_runs)
    run = ET.SubElement(paragraph, _q(W_NS, "r"))
    run.append(result_run_pr)
    label = ET.SubElement(run, _q(W_NS, "t"))
    label.text = str(entry.get("text", ""))
    _preserve_space(label)
    ET.SubElement(run, _q(W_NS, "tab"))
    page = ET.SubElement(run, _q(W_NS, "t"))
    page.text = str(entry.get("page", ""))
    _preserve_space(page)
    if include_suffix:
        paragraph.extend(suffix_runs)
    return paragraph


def _normalize_toc_heading(paragraph: ET.Element) -> None:
    p_pr = _reset_direct_p_pr(paragraph)
    spacing = _ordered_child(p_pr, "spacing")
    spacing.set(_q(W_NS, "beforeLines"), "150")
    spacing.set(_q(W_NS, "before"), "360")
    spacing.set(_q(W_NS, "afterLines"), "100")
    spacing.set(_q(W_NS, "after"), "240")
    _set_child_value(p_pr, "jc", "center")
    _ordered_child(p_pr, "rPr")
    for child in list(paragraph):
        if child.tag != _q(W_NS, "pPr"):
            paragraph.remove(child)
    run = ET.SubElement(paragraph, _q(W_NS, "r"))
    r_pr = ET.SubElement(run, _q(W_NS, "rPr"))
    _append_run_property(
        r_pr,
        "rFonts",
        {"ascii": "黑体", "eastAsia": "黑体", "hAnsi": "黑体"},
    )
    _append_run_property(r_pr, "bCs")
    _append_run_property(r_pr, "color", {"val": "000000"})
    _append_run_property(r_pr, "sz", {"val": "32"})
    _append_run_property(r_pr, "szCs", {"val": "28"})
    text = ET.SubElement(run, _q(W_NS, "t"))
    text.text = "目  录"
    _preserve_space(text)


def _toc_style_id_for_role(role: str, available_style_ids: set[str] | frozenset[str]) -> str | None:
    preferred = {
        "heading_1": "10",
        "heading_2": "25",
        "heading_3": "30",
    }.get(role)
    return preferred if preferred in available_style_ids else None


def _toc_field_position(offset: int, total: int) -> str:
    if total <= 1:
        return "only"
    if offset == 0:
        return "first"
    if offset == total - 1:
        return "last"
    return "middle"


def _set_toc_paragraph_style(
    paragraph: ET.Element,
    role: str,
    *,
    prototype_has_style: bool,
    available_style_ids: set[str],
) -> None:
    style_id = _toc_style_id_for_role(role, _TOC_CACHE_STYLE_IDS)
    if style_id is None:
        return
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    if p_pr is None:
        p_pr = ET.Element(_q(W_NS, "pPr"))
        paragraph.insert(0, p_pr)
    p_style = p_pr.find(_q(W_NS, "pStyle"))
    if p_style is None and not prototype_has_style and style_id not in available_style_ids:
        return
    if p_style is None:
        p_style = ET.Element(_q(W_NS, "pStyle"))
        p_pr.insert(0, p_style)
    p_style.set(_q(W_NS, "val"), style_id)


def _normalize_toc_cache_paragraph_properties(paragraph: ET.Element) -> None:
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    if p_pr is None:
        return
    _remove_children(p_pr, {"tabs", "spacing", "ind", "jc", "outlineLvl"})
    run_properties = p_pr.find(_q(W_NS, "rPr"))
    if run_properties is not None:
        _remove_children(run_properties, {"b", "bCs", "color", "u", "sz", "szCs"})


def _toc_result_run_properties(paragraph: ET.Element) -> ET.Element:
    source_run_pr: ET.Element | None = None
    for run in paragraph.findall(_q(W_NS, "r")):
        if run.find(_q(W_NS, "t")) is None and run.find(_q(W_NS, "tab")) is None:
            continue
        source_run_pr = run.find(_q(W_NS, "rPr"))
        if source_run_pr is not None:
            break
    run_pr = (
        copy.deepcopy(source_run_pr) if source_run_pr is not None else ET.Element(_q(W_NS, "rPr"))
    )
    _remove_children(run_pr, {"b", "bCs", "color", "u", "sz", "szCs"})
    style = run_pr.find(_q(W_NS, "rStyle"))
    if style is None:
        style = ET.Element(_q(W_NS, "rStyle"))
        run_pr.insert(0, style)
    style.set(_q(W_NS, "val"), _TOC_RESULT_STYLE_ID)
    if run_pr.find(_q(W_NS, "noProof")) is None:
        ET.SubElement(run_pr, _q(W_NS, "noProof"))
    return run_pr


def _toc_field_boundary_runs(paragraph: ET.Element) -> tuple[list[ET.Element], list[ET.Element]]:
    prefix: list[ET.Element] = []
    suffix: list[ET.Element] = []
    before_result = True
    for child in paragraph:
        if child.tag == _q(W_NS, "pPr"):
            continue
        fld_char = child.find(_q(W_NS, "fldChar"))
        fld_type = fld_char.get(_q(W_NS, "fldCharType")) if fld_char is not None else None
        if fld_type == "end":
            suffix.append(copy.deepcopy(child))
            continue
        if before_result and (
            fld_type in {"begin", "separate"} or child.find(_q(W_NS, "instrText")) is not None
        ):
            prefix.append(copy.deepcopy(child))
            if fld_type == "separate":
                before_result = False
            continue
        before_result = False
    return prefix, suffix


def _runs_have_field_char(runs: Sequence[ET.Element], field_type: str) -> bool:
    return any(
        (field_char := run.find(_q(W_NS, "fldChar"))) is not None
        and field_char.get(_q(W_NS, "fldCharType")) == field_type
        for run in runs
    )


def _default_toc_field_prefix_runs() -> list[ET.Element]:
    begin = _toc_field_char_run("begin")
    fld_char = begin.find(_q(W_NS, "fldChar"))
    if fld_char is not None:
        fld_char.set(_q(W_NS, "dirty"), "true")

    instruction_run = ET.Element(_q(W_NS, "r"))
    instruction = ET.SubElement(instruction_run, _q(W_NS, "instrText"))
    instruction.set(_q(XML_NS, "space"), "preserve")
    instruction.text = ' TOC \\o "1-3" \\h \\z \\u '

    separate = _toc_field_char_run("separate")
    return [begin, instruction_run, separate]


def _toc_field_char_run(field_type: str) -> ET.Element:
    run = ET.Element(_q(W_NS, "r"))
    fld_char = ET.SubElement(run, _q(W_NS, "fldChar"))
    fld_char.set(_q(W_NS, "fldCharType"), field_type)
    return run


def _remove_toc_cache_style_definitions(parts: dict[str, bytes]) -> int:
    try:
        styles = _xml(parts, "word/styles.xml")
    except (KeyError, ET.ParseError, ToolFailure):
        return 0
    removed = 0
    for style in list(styles.findall(_q(W_NS, "style"))):
        style_id = style.get(_q(W_NS, "styleId"))
        if style_id not in _TOC_CACHE_STYLE_IDS:
            continue
        style_type = style.get(_q(W_NS, "type"))
        name = style.find(_q(W_NS, "name"))
        style_name = (name.get(_q(W_NS, "val")) if name is not None else "") or ""
        if style_type != "paragraph" or not style_name.casefold().startswith("toc"):
            continue
        styles.remove(style)
        removed += 1
    if removed:
        parts["word/styles.xml"] = _serialize(styles)
    return removed


def _split_toc_text_and_page(text: str) -> tuple[str, str] | None:
    match = re.match(r"^(?P<label>.+?)[\s\u00a0]*(?P<page>[IVXLCDMivxlcdm]+|\d+)\s*$", text)
    if match is None:
        return None
    label = match.group("label").strip(".·… \t")
    page = match.group("page").upper()
    if not label:
        return None
    return label, page


def _normalize_toc_label(label: str) -> str:
    value = re.sub(r"\s+", " ", label).strip()
    compact = _compact_heading_text(value)
    if compact in {"摘要", "摘篇"}:
        return "摘  要"
    if compact == "附录":
        return "附  录"
    if compact == "致谢":
        return "致  谢"
    return value


def _toc_key(label: str) -> str:
    normalized = _normalize_toc_label(label)
    logical = _strip_source_generated_prefix(normalized, "heading")
    return _compact_heading_text(logical).casefold()


def _materialize_page_number_footers(parts: dict[str, bytes]) -> int:
    materialized = 0
    for name in sorted(parts):
        if not re.fullmatch(r"word/footer\d+\.xml", name):
            continue
        footer = _xml(parts, name)
        if any(
            "PAGE" in (instruction.text or "").upper()
            for instruction in footer.iter(_q(W_NS, "instrText"))
        ):
            continue
        paragraphs = footer.findall(_q(W_NS, "p"))
        text_paragraphs = [
            paragraph for paragraph in paragraphs if _paragraph_text(paragraph).strip()
        ]
        if len(text_paragraphs) != 1:
            continue
        text = _paragraph_text(text_paragraphs[0]).strip()
        if not re.fullmatch(r"\d+", text):
            continue
        _replace_footer_static_number_with_page_field(text_paragraphs[0], text)
        parts[name] = _serialize(footer)
        materialized += 1
    return materialized


def _replace_footer_static_number_with_page_field(paragraph: ET.Element, cache: str) -> None:
    p_pr = paragraph.find(_q(W_NS, "pPr"))
    preserved_p_pr = copy.deepcopy(p_pr) if p_pr is not None else None
    run_pr = None
    for run in paragraph.findall(_q(W_NS, "r")):
        candidate = run.find(_q(W_NS, "rPr"))
        if candidate is not None:
            run_pr = copy.deepcopy(candidate)
            break
    paragraph.clear()
    if preserved_p_pr is not None:
        paragraph.append(preserved_p_pr)

    begin = ET.SubElement(ET.SubElement(paragraph, _q(W_NS, "r")), _q(W_NS, "fldChar"))
    begin.set(_q(W_NS, "fldCharType"), "begin")

    instruction_run = ET.SubElement(paragraph, _q(W_NS, "r"))
    instruction = ET.SubElement(instruction_run, _q(W_NS, "instrText"))
    instruction.set(_q(XML_NS, "space"), "preserve")
    instruction.text = " PAGE   \\* MERGEFORMAT "

    separate = ET.SubElement(ET.SubElement(paragraph, _q(W_NS, "r")), _q(W_NS, "fldChar"))
    separate.set(_q(W_NS, "fldCharType"), "separate")

    value_run = ET.SubElement(paragraph, _q(W_NS, "r"))
    if run_pr is not None:
        value_run.append(run_pr)
    value = ET.SubElement(value_run, _q(W_NS, "t"))
    value.text = cache

    end = ET.SubElement(ET.SubElement(paragraph, _q(W_NS, "r")), _q(W_NS, "fldChar"))
    end.set(_q(W_NS, "fldCharType"), "end")


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
        update = ET.Element(_q(W_NS, "updateFields"))
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
                if _local_name(child) in following_settings
            ),
            len(settings),
        )
        settings.insert(insertion, update)
    update.set(_q(W_NS, "val"), "true")
    layout_compat_settings = _ensure_word2013_track_bottom_hyphenation(settings)
    parts["word/settings.xml"] = _serialize(settings)
    return {
        "toc_fields_marked_dirty": fields,
        "update_fields_on_open": True,
        "layout_compat_settings_materialized": layout_compat_settings,
        "word_refresh_still_requires_canonical_word_verification": True,
    }


def _ensure_word2013_track_bottom_hyphenation(settings: ET.Element) -> int:
    compat = settings.find(_q(W_NS, "compat"))
    if compat is None:
        compat = ET.Element(_q(W_NS, "compat"))
        following_settings = {
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
                if _local_name(child) in following_settings
            ),
            len(settings),
        )
        settings.insert(insertion, compat)
    for child in compat.findall(_q(W_NS, "compatSetting")):
        if child.get(_q(W_NS, "name")) == "useWord2013TrackBottomHyphenation":
            child.set(_q(W_NS, "val"), "1")
            return 0
    child = ET.SubElement(compat, _q(W_NS, "compatSetting"))
    child.set(_q(W_NS, "name"), "useWord2013TrackBottomHyphenation")
    child.set(_q(W_NS, "uri"), "http://schemas.microsoft.com/office/word")
    child.set(_q(W_NS, "val"), "1")
    return 1


def _apply_replacements(
    elements: list[ET.Element],
    replacements: tuple[TextReplacement, ...],
    *,
    source_elements: dict[str, ET.Element],
) -> list[JsonObject]:
    result: list[JsonObject] = []
    for replacement in replacements:
        scoped_elements = elements
        if replacement.source_object_id is not None:
            source_element = source_elements.get(replacement.source_object_id)
            if source_element is None:
                raise _invalid(
                    "projection_text_replacement_source_missing",
                    "An approved text patch does not resolve to an imported source object.",
                )
            scoped_elements = [source_element]
        actual = sum(_paragraph_text(item).count(replacement.old) for item in scoped_elements)
        if actual != replacement.expected_count:
            raise _invalid(
                "projection_text_replacement_count",
                "Approved replacement expected "
                f"{replacement.expected_count} match(es), got {actual}.",
            )
        changed = 0
        for element in scoped_elements:
            changed += _replace_across_text_nodes(element, replacement.old, replacement.new)
        result.append(
            {
                "patch_id": replacement.patch_id,
                "source_object_id": replacement.source_object_id,
                "reason": replacement.reason,
                "old_sha256": _short_text_hash(replacement.old),
                "new_sha256": _short_text_hash(replacement.new),
                "count": changed,
            }
        )
    return result


def _replace_across_text_nodes(
    element: ET.Element,
    old: str,
    new: str,
    *,
    match_allowed: Callable[[str, int, int], bool] | None = None,
) -> int:
    nodes = list(element.iter(_q(W_NS, "t")))
    combined = "".join(node.text or "" for node in nodes)
    starts = [
        match.start()
        for match in re.finditer(re.escape(old), combined)
        if match_allowed is None or match_allowed(combined, match.start(), match.end())
    ]
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
    names = {"spacing", "w", "position", "fitText", "kern"}
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
        _ordered_child(p_pr, name)
    elif enabled:
        assert existing is not None
        _move_ordered(p_pr, existing)
    elif not enabled and existing is not None:
        p_pr.remove(existing)


def _set_paragraph_value(paragraph: ET.Element, name: str, value: str) -> None:
    _set_child_value(_ensure_p_pr(paragraph), name, value)


def _set_child_value(parent: ET.Element, name: str, value: str) -> None:
    child = parent.find(_q(W_NS, name))
    if child is None:
        child = _ordered_child(parent, name)
    else:
        _move_ordered(parent, child)
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
    indent = _ordered_child(p_pr, "ind")
    indent.set(_q(W_NS, "left"), "0")
    indent.set(_q(W_NS, "right"), "0")
    indent.set(_q(W_NS, "firstLine"), "0")


def _remove_children(parent: ET.Element, local_names: set[str]) -> None:
    for child in list(parent):
        if child.tag.rsplit("}", 1)[-1] in local_names:
            parent.remove(child)


def _ordered_child(parent: ET.Element, name: str) -> ET.Element:
    child = parent.find(_q(W_NS, name))
    if child is None:
        child = ET.Element(_q(W_NS, name))
        _insert_ordered(parent, child)
    else:
        _move_ordered(parent, child)
    return child


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


def _contract_style_map(contract: JsonObject, available: set[str]) -> dict[str, str]:
    if contract.get("schema_version") != "docfit-template-fill-contract/v2":
        raise _invalid(
            "projection_fill_contract_version_retired",
            "Student content projection requires a current fill-contract/v2 contract.",
        )
    raw_styles = contract.get("styles", [])
    if raw_styles is None:
        return {}
    if not isinstance(raw_styles, list):
        raise _invalid(
            "projection_contract_styles_invalid",
            "The fill contract styles collection must be a list.",
        )
    resolved: dict[str, str] = {}
    projection_roles = {
        "style.body.chapter_body",
        "style.body.chapter_title",
        "style.body.section_title",
        "style.body.subsection_title",
        "style.references",
        "style.body.figure.caption",
        "style.body.table.caption",
    }
    for item in raw_styles:
        if not isinstance(item, dict):
            raise _invalid(
                "projection_contract_style_invalid",
                "A fill-contract style entry has an invalid shape.",
            )
        logical_id = item.get("style_contract_id")
        if not isinstance(logical_id, str) and isinstance(item.get("style_id"), str):
            raise _invalid(
                "projection_contract_retired_style_id",
                "Fill-contract styles must use style_contract_id; style_id is retired.",
            )
        word_style_id = item.get("word_style_id")
        if not isinstance(logical_id, str) or not isinstance(word_style_id, str):
            continue
        if logical_id not in projection_roles:
            continue
        if word_style_id not in available:
            raise _invalid(
                "projection_contract_style_missing",
                f"The fill contract references a style absent from the template: {logical_id}.",
            )
        existing = resolved.get(logical_id)
        if existing is not None and existing != word_style_id:
            raise _invalid(
                "projection_contract_style_conflict",
                f"The fill contract maps one logical style more than once: {logical_id}.",
            )
        resolved[logical_id] = word_style_id
    return resolved


def _declared_caption_style(declared: dict[str, str]) -> str | None:
    candidates = {
        declared[logical_id]
        for logical_id in ("style.body.figure.caption", "style.body.table.caption")
        if logical_id in declared
    }
    if len(candidates) > 1:
        raise _invalid(
            "projection_caption_style_conflict",
            "Figure and table captions require different styles, but this projection uses "
            "one role.",
        )
    return next(iter(candidates), None)


def _default_paragraph_style(styles: ET.Element) -> str | None:
    for style in styles.findall(_q(W_NS, "style")):
        if style.get(_q(W_NS, "type")) == "paragraph" and style.get(_q(W_NS, "default")) in {
            "1",
            "true",
            "on",
        }:
            return style.get(_q(W_NS, "styleId"))
    return next(
        (
            style_id
            for style in styles.findall(_q(W_NS, "style"))
            if style.get(_q(W_NS, "type")) == "paragraph"
            and (style_id := style.get(_q(W_NS, "styleId"))) is not None
        ),
        None,
    )


def _template_caption_style(styles: ET.Element) -> str | None:
    candidates: list[tuple[str, str]] = []
    for style in styles.findall(_q(W_NS, "style")):
        if style.get(_q(W_NS, "type")) != "paragraph":
            continue
        style_id = style.get(_q(W_NS, "styleId"))
        if style_id is None:
            continue
        name = style.find(_q(W_NS, "name"))
        style_name = name.get(_q(W_NS, "val"), "") if name is not None else ""
        candidates.append((style_id, style_name))
    for style_id, _ in candidates:
        if style_id.casefold() == "caption":
            return style_id
    caption_candidates = [
        style_id
        for style_id, style_name in candidates
        if "caption" in style_name.casefold() or "题注" in style_name
    ]
    return caption_candidates[0] if len(caption_candidates) == 1 else None


def _projected_heading_style(
    styles: ET.Element,
    declared_style_id: str | None,
    *,
    normal_style_id: str,
    level: int,
    fallback_style_id: str | None = None,
) -> str | None:
    if declared_style_id is not None and declared_style_id != normal_style_id:
        return declared_style_id
    return _template_heading_style(styles, level) or fallback_style_id


def _template_heading_style(styles: ET.Element, level: int) -> str | None:
    candidates: list[tuple[str, str]] = []
    for style in styles.findall(_q(W_NS, "style")):
        if style.get(_q(W_NS, "type")) != "paragraph":
            continue
        style_id = style.get(_q(W_NS, "styleId"))
        name = style.find(_q(W_NS, "name"))
        if style_id is None or name is None:
            continue
        style_name = re.sub(r"\s+", "", name.get(_q(W_NS, "val"), "")).casefold()
        candidates.append((style_id, style_name))

    if level == 1:
        for style_id, style_name in candidates:
            if style_name in {"heading1", "标题1"}:
                return style_id
        return "1" if any(style_id == "1" for style_id, _ in candidates) else None

    for style_id, style_name in candidates:
        if style_name == f"标题{level}":
            return style_id
    if level == 3:
        for style_id, style_name in candidates:
            if style_name == "标题2":
                return style_id
    for style_id, style_name in candidates:
        if style_name == f"heading{level}":
            return style_id
    return str(level) if any(style_id == str(level) for style_id, _ in candidates) else None


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
