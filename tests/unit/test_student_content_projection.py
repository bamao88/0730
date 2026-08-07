from __future__ import annotations

from xml.etree import ElementTree as ET

from docfit.content.projection import (
    _body_role,
    _high_risk_mixed_paragraph,
    _is_safe_layout_empty,
    _merge_adjacent_text_runs,
    _paragraph_text,
    _replace_across_text_nodes,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def test_body_role_projects_source_numbering_to_template_heading_levels() -> None:
    assert _body_role("第一章 文献综述") == "heading_1"
    assert _body_role("1材料与方法") == "heading_2"
    assert _body_role("1.2复合菌群种子液") == "heading_3"
    assert _body_role("（1）供试土壤") == "body"


def test_text_replacement_crosses_runs_without_flattening_them() -> None:
    paragraph = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>Mycobacterium</w:t></w:r>'
        "<w:r><w:t>sp.</w:t></w:r><w:r><w:t> remains</w:t></w:r></w:p>"
    )

    changed = _replace_across_text_nodes(paragraph, "Mycobacteriumsp.", "Mycobacterium sp.")

    assert changed == 1
    assert _paragraph_text(paragraph) == "Mycobacterium sp. remains"
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
