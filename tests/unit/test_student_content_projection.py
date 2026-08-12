from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.content.projection import (
    _body_role,
    _high_risk_mixed_paragraph,
    _is_safe_layout_empty,
    _merge_adjacent_text_runs,
    _paragraph_text,
    _replace_across_text_nodes,
    resolve_template_style_map,
)
from docfit.tools.ooxml import _apply_expected_value_run_style

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def test_body_role_uses_extracted_field_ids_without_reading_text() -> None:
    assert _body_role({"body.heading.level1"}) == "heading_1"
    assert _body_role({"body.heading.level2"}) == "heading_2"
    assert _body_role({"body.heading.level3"}) == "heading_3"
    assert _body_role({"body.paragraph"}) == "body"


def test_text_replacement_crosses_runs_without_flattening_them() -> None:
    paragraph = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>AlphaBeta</w:t></w:r>'
        "<w:r><w:t>sp.</w:t></w:r><w:r><w:t> remains</w:t></w:r></w:p>"
    )

    changed = _replace_across_text_nodes(paragraph, "AlphaBetasp.", "AlphaBeta sp.")

    assert changed == 1
    assert _paragraph_text(paragraph) == "AlphaBeta sp. remains"
    assert len(paragraph.findall(_q("r"))) == 3


def test_empty_cleanup_preserves_break_payload() -> None:
    empty = ET.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r/></w:p>')
    break_paragraph = ET.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:br/></w:r></w:p>')

    assert _is_safe_layout_empty(empty) is True
    assert _is_safe_layout_empty(break_paragraph) is False


def test_fragmented_formula_explanation_avoids_distributed_spacing() -> None:
    runs = "".join(
        f"<w:r><w:t>{value}</w:t></w:r>"
        for value in ("式中", "，", "C", "0", "为", "初始", "浓度", "mg", "/", "kg")
    )
    paragraph = ET.fromstring(f'<w:p xmlns:w="{W_NS}">{runs}</w:p>')

    assert _high_risk_mixed_paragraph(paragraph, _paragraph_text(paragraph)) is True
    assert _merge_adjacent_text_runs(paragraph) == 9
    assert len(paragraph.findall(_q("r"))) == 1


def test_style_roles_resolve_only_to_bound_template_styles(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    styles = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{W_NS}">
 <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
  <w:name w:val="Normal"/>
 </w:style>
 <w:style w:type="paragraph" w:styleId="Body"><w:name w:val="正文"/></w:style>
 <w:style w:type="paragraph" w:styleId="H1"><w:name w:val="一级标题"/></w:style>
 <w:style w:type="paragraph" w:styleId="caption"><w:name w:val="题注"/></w:style>
</w:styles>"""
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("word/styles.xml", styles)

    resolved = resolve_template_style_map(
        template_docx=template,
        contract={
            "schema_version": "docfit-template-fill-contract/v2",
            "styles": [
                {
                    "style_contract_id": "style.body.chapter_body",
                    "word_style_id": "Body",
                },
                {
                    "style_contract_id": "style.body.chapter_title",
                    "word_style_id": "H1",
                },
            ]
        },
    )

    assert resolved.normal == "Normal"
    assert resolved.body == "Body"
    assert resolved.heading_1 == "H1"
    assert resolved.heading_2 == "Body"
    assert resolved.reference == "Body"
    assert resolved.caption == "caption"


def test_v2_style_roles_do_not_read_the_frozen_v1_style_id_alias(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    styles = f'''<w:styles xmlns:w="{W_NS}">
    <w:style w:type="paragraph" w:default="1" w:styleId="Normal"/>
    <w:style w:type="paragraph" w:styleId="H1"/>
    </w:styles>'''
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("word/styles.xml", styles)

    v2 = resolve_template_style_map(
        template_docx=template,
        contract={
            "schema_version": "docfit-template-fill-contract/v2",
            "styles": [
                {"style_id": "style.body.chapter_title", "word_style_id": "H1"}
            ],
        },
    )
    frozen_v1 = resolve_template_style_map(
        template_docx=template,
        contract={
            "schema_version": "docfit-template-fill-contract/v1",
            "styles": [
                {"style_id": "style.body.chapter_title", "word_style_id": "H1"}
            ],
        },
    )

    assert v2.heading_1 == "Normal"
    assert frozen_v1.heading_1 == "H1"


def test_expected_value_style_removes_gray_placeholder_color() -> None:
    content = ET.fromstring(
        f'<w:sdtContent xmlns:w="{W_NS}"><w:p><w:r><w:rPr>'
        '<w:color w:val="7F7F7F"/></w:rPr><w:t>Actual value</w:t>'
        "</w:r></w:p></w:sdtContent>"
    )

    changed = _apply_expected_value_run_style(
        content,
        {
            "font": {
                "east_asia": "宋体;SimSun",
                "latin": "Times New Roman",
                "size_pt": 10.5,
            }
        },
    )

    properties = content.find(f".//{_q('rPr')}")
    assert changed is True
    assert properties is not None
    assert properties.find(_q("color")) is None
    assert properties.find(_q("rFonts")).get(_q("eastAsia")) == "宋体"
    assert properties.find(_q("sz")).get(_q("val")) == "21"
