from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.content.projection import (
    _body_role,
    _CaptionNumberingState,
    _clear_imported_source_page_breaks,
    _clear_run_layout,
    _clear_section_gutters,
    _collapse_redundant_back_matter_breaks,
    _has_page_break,
    _high_risk_mixed_paragraph,
    _is_safe_layout_empty,
    _materialize_back_matter_generated_content,
    _materialize_body_inline_semantics,
    _materialize_heading_number,
    _materialize_object_references,
    _materialize_page_number_footers,
    _materialize_toc_cache,
    _merge_adjacent_text_runs,
    _normalize_body_run_style,
    _normalize_caption,
    _normalize_drawing_paragraph,
    _normalize_heading_paragraph,
    _normalize_reference,
    _normalize_table,
    _normalize_text_paragraph,
    _paragraph_text,
    _place_table_captions_before_tables,
    _replace_across_text_nodes,
    _replace_paragraph_text,
    _replace_semantic_paragraph_text,
    _request_toc_update,
    _resolve_semantic_evidence,
    _set_paragraph_flag,
    _strip_source_generated_prefix,
    _strip_source_list_marker,
    _toc_entries_for_document,
    _toc_key,
    _toc_paragraph,
    materialize_post_style_layout_closure,
    resolve_template_style_map,
)
from docfit.tools.ooxml import _apply_expected_value_run_style
from docfit.tools.runtime import ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def test_body_role_uses_extracted_field_ids_without_reading_text() -> None:
    assert _body_role({"body.heading.outline1"}) == "heading_1"
    assert _body_role({"body.heading.outline2"}) == "heading_2"
    assert _body_role({"body.heading.outline3"}) == "heading_3"
    assert _body_role({"body.paragraph"}) == "body"


def test_source_generated_numbering_is_not_user_content() -> None:
    assert _strip_source_generated_prefix("第一章文献综述", "heading") == "文献综述"
    assert _strip_source_generated_prefix("1.2PGPR促进植物生长", "heading") == ("PGPR促进植物生长")
    assert _strip_source_generated_prefix("图4-1 ΔtrpA突变株PCR验证结果", "figure_caption") == (
        "ΔtrpA突变株PCR验证结果"
    )
    assert _strip_source_generated_prefix(
        "Table 1-1 Antibiotic susceptibility", "table_caption"
    ) == ("Antibiotic susceptibility")
    assert _toc_key("1.1 PGPR促进植物生长") == _toc_key("PGPR促进植物生长")
    assert _toc_key("第一章文献综述") == _toc_key("文献综述")


def test_source_list_markers_are_not_user_content() -> None:
    assert _strip_source_list_marker("（1）LB液体培养基") == "LB液体培养基"
    assert _strip_source_list_marker("(2) Kanamycin") == "Kanamycin"
    assert _strip_source_list_marker("3、第三项") == "第三项"


def test_toc_pages_for_repeated_headings_are_consumed_in_order() -> None:
    body = ET.fromstring(f'<w:body xmlns:w="{W_NS}"/>')
    entries = _toc_entries_for_document(
        [
            {"role": "heading_3", "text": "1.1 实验材料"},
            {"role": "heading_3", "text": "2.1 实验材料"},
        ],
        body,
        [
            {"key": _toc_key("1.1 实验材料"), "page": "6"},
            {"key": _toc_key("2.1 实验材料"), "page": "8"},
        ],
    )

    assert entries[2]["page"] == "6"
    assert entries[3]["page"] == "8"


def test_toc_cache_lines_preserve_word_field_cache_shape() -> None:
    prototype = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:pPr><w:pStyle w:val="30"/>'
        '<w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9060"/></w:tabs>'
        '<w:spacing w:line="400" w:lineRule="exact"/>'
        '<w:rPr><w:sz w:val="28"/></w:rPr></w:pPr>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:rPr><w:rStyle w:val="a6"/><w:sz w:val="28"/></w:rPr>'
        "<w:t>1 旧条目</w:t><w:tab/><w:t>1</w:t></w:r></w:p>"
    )

    paragraph = _toc_paragraph(
        {"role": "heading_3", "text": "1.1 小节", "page": "2"},
        {"heading_3": prototype},
        available_style_ids={"10", "25", "30"},
        field_position="first",
    )

    style = paragraph.find(f"{_q('pPr')}/{_q('pStyle')}")
    assert style is not None
    assert style.get(_q("val")) == "30"
    assert paragraph.find(f"{_q('pPr')}/{_q('tabs')}") is None
    assert paragraph.find(f"{_q('pPr')}/{_q('spacing')}") is None
    assert _paragraph_text(paragraph) == "1.1 小节2"
    result_run = next(run for run in paragraph.findall(_q("r")) if run.find(_q("tab")) is not None)
    assert paragraph.find(f"{_q('r')}/{_q('fldChar')}").get(_q("fldCharType")) == "begin"
    result_style = result_run.find(f"{_q('rPr')}/{_q('rStyle')}")
    assert result_style is not None
    assert result_style.get(_q("val")) == "a6"
    assert result_run.find(f"{_q('rPr')}/{_q('sz')}") is None


def test_toc_materialization_preserves_template_boundary_paragraphs() -> None:
    document = ET.fromstring(
        f'''<w:document xmlns:w="{W_NS}">
        <w:body>
          <w:p><w:r><w:t>目  录</w:t></w:r></w:p>
          <w:p/>
          <w:p/>
          <w:p><w:pPr><w:pStyle w:val="10"/></w:pPr><w:r><w:t>旧章1</w:t></w:r></w:p>
          <w:p><w:pPr><w:pStyle w:val="25"/></w:pPr><w:r><w:t>1 旧节1</w:t></w:r></w:p>
          <w:p><w:pPr><w:sectPr/></w:pPr></w:p>
          <w:p><w:pPr><w:pageBreakBefore/></w:pPr><w:r><w:t>摘要标题</w:t></w:r></w:p>
        </w:body>
        </w:document>'''
    )
    body = document.find(_q("body"))
    assert body is not None
    parts = {
        "word/settings.xml": f'<w:settings xmlns:w="{W_NS}"/>'.encode(),
        "word/styles.xml": (
            f'<w:styles xmlns:w="{W_NS}">'
            '<w:style w:type="paragraph" w:styleId="10"><w:name w:val="toc 1"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="25"><w:name w:val="toc 2"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="30"><w:name w:val="toc 3"/></w:style>'
            "</w:styles>"
        ).encode(),
    }

    report = _materialize_toc_cache(
        parts=parts,
        document=document,
        body=body,
        body_entries=[{"role": "heading_1", "text": "第一章 新章"}],
        source_toc_entries=[],
    )

    assert report["static_toc_materialized"] is True
    assert report["static_toc_old_paragraphs_removed"] == 2
    assert report["static_toc_style_definitions_removed"] == 3
    paragraphs = body.findall(_q("p"))
    assert paragraphs[0].find(f"{_q('pPr')}/{_q('pStyle')}") is None
    assert _paragraph_text(paragraphs[1]) == ""
    assert _paragraph_text(paragraphs[2]) == ""
    assert _paragraph_text(paragraphs[3]) == "摘  要I"
    toc_style = paragraphs[3].find(f"{_q('pPr')}/{_q('pStyle')}")
    assert toc_style is not None
    assert toc_style.get(_q("val")) == "10"
    assert paragraphs[3].find(f".//{_q('tab')}") is not None
    assert paragraphs[3].find(f"{_q('r')}/{_q('fldChar')}").get(_q("fldCharType")) == "begin"
    assert _paragraph_text(paragraphs[4]) == "ABSTRACTII"
    assert _paragraph_text(paragraphs[5]) == "第一章 新章1"
    field_types = [
        field.get(_q("fldCharType")) for field in paragraphs[5].findall(f".//{_q('fldChar')}")
    ]
    assert field_types == ["end"]
    assert _paragraph_text(paragraphs[6]) == ""
    assert paragraphs[6].find(f"{_q('pPr')}/{_q('sectPr')}") is not None
    assert _paragraph_text(paragraphs[7]) == "摘要标题"
    assert paragraphs[7].find(f"{_q('pPr')}/{_q('pageBreakBefore')}") is not None
    styles = ET.fromstring(parts["word/styles.xml"])
    assert not any(style.get(_q("styleId")) == "10" for style in styles.findall(_q("style")))


def test_imported_source_page_breaks_do_not_control_front_matter_layout() -> None:
    document = ET.fromstring(
        f'''<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
        <w:body>
          <w:p w14:paraId="00000001">
            <w:pPr><w:pageBreakBefore/></w:pPr>
            <w:r><w:t>摘要第一段</w:t><w:br w:type="page"/><w:t>续写</w:t></w:r>
          </w:p>
        </w:body>
        </w:document>'''
    )

    cleared = _clear_imported_source_page_breaks(
        document,
        {
            "block_operations": [
                {
                    "field_id": "abstract.zh",
                    "inserted_body_refs": [
                        {"target_locator": "/body/p[@paraId=00000001]"},
                    ],
                }
            ]
        },
    )

    paragraph = next(document.iter(_q("p")))
    assert cleared == 2
    assert paragraph.find(f"{_q('pPr')}/{_q('pageBreakBefore')}") is None
    assert paragraph.find(f".//{_q('br')}") is None


def test_static_numeric_footers_are_target_page_fields() -> None:
    parts = {
        "word/footer1.xml": (
            f'<w:ftr xmlns:w="{W_NS}"><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
            '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
            "</w:p></w:ftr>"
        ).encode(),
        "word/footer2.xml": (
            f'<w:ftr xmlns:w="{W_NS}"><w:p><w:r>'
            '<w:instrText xml:space="preserve"> PAGE </w:instrText>'
            "</w:r></w:p></w:ftr>"
        ).encode(),
    }

    assert _materialize_page_number_footers(parts) == 1
    footer = ET.fromstring(parts["word/footer1.xml"])
    assert "PAGE" in "".join(t.text or "" for t in footer.iter(_q("instrText")))
    assert [item.get(_q("fldCharType")) for item in footer.iter(_q("fldChar"))] == [
        "begin",
        "separate",
        "end",
    ]
    assert _paragraph_text(next(footer.iter(_q("p")))) == "1"


def test_redundant_back_matter_breaks_do_not_create_blank_pages() -> None:
    body = ET.fromstring(
        f'''<w:body xmlns:w="{W_NS}">
        <w:p><w:r><w:t>正文结尾</w:t></w:r></w:p>
        <w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:br w:type="page"/></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="23"/></w:pPr></w:p>
        <w:p><w:pPr><w:sectPr/></w:pPr></w:p>
        <w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:br w:type="page"/></w:r></w:p>
        <w:p><w:r><w:t>参考文献</w:t></w:r></w:p>
        </w:body>'''
    )

    assert _collapse_redundant_back_matter_breaks(body) == 1
    paragraphs = body.findall(_q("p"))
    assert [_paragraph_text(paragraph) for paragraph in paragraphs] == [
        "正文结尾",
        "",
        "",
        "",
        "参考文献",
    ]
    assert paragraphs[1].find(f"{_q('pPr')}/{_q('sectPr')}") is not None
    assert paragraphs[2].find(f"{_q('pPr')}/{_q('sectPr')}") is None
    assert paragraphs[3].find(f"{_q('pPr')}/{_q('sectPr')}") is not None


def test_back_matter_generated_content_removes_placeholder_residue_at_region_layer() -> None:
    body = ET.fromstring(
        f'''<w:body xmlns:w="{W_NS}">
        <w:p><w:r><w:t>附录附录</w:t></w:r></w:p>
        <w:p><w:r><w:t>表 5-1【请填写中文表名】</w:t></w:r></w:p>
        <w:p><w:r><w:t>Table 5-1 [Please fill in the English table title]</w:t></w:r></w:p>
        <w:tbl>
          <w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/></w:tblGrid>
          <w:tr>
            <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
        <w:p><w:r><w:t>相关的学术成果目录</w:t></w:r></w:p>
        <w:p><w:r><w:t>【此处为选填部分；有学术成果请补充，无内容可删除本页。】</w:t></w:r></w:p>
        <w:p><w:r><w:t>致谢</w:t></w:r></w:p>
        </w:body>'''  # noqa: E501
    )

    report = _materialize_back_matter_generated_content(
        body=body,
        body_style_id="body",
        caption_style_id="caption",
        appendix_table_chapter=5,
    )

    assert report == {"cleaned": 4, "inserted": 0}
    texts = [_paragraph_text(paragraph) for paragraph in body.findall(_q("p"))]
    assert texts == [
        "附  录",
        "相关的学术成果目录",
        "致谢",
    ]


def test_section_gutters_are_not_final_generation_content_width() -> None:
    document = ET.fromstring(
        f'''<w:document xmlns:w="{W_NS}">
        <w:body>
          <w:p><w:pPr><w:sectPr><w:pgMar w:left="1134" w:right="1134" w:gutter="284"/></w:sectPr></w:pPr></w:p>
          <w:sectPr><w:pgMar w:left="1134" w:right="1134" w:gutter="0"/></w:sectPr>
        </w:body>
        </w:document>'''  # noqa: E501
    )

    assert _clear_section_gutters(document) == 1
    margins = document.find(f".//{_q('pgMar')}")
    assert margins is not None
    assert margins.get(_q("gutter")) == "0"


def test_table_caption_block_order_is_target_materialization() -> None:
    body = ET.fromstring(
        f'''<w:body xmlns:w="{W_NS}">
        <w:p><w:r><w:t>before</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:p><w:r><w:t>表 1-1 数据</w:t></w:r></w:p>
        <w:p><w:r><w:t>Table 1-1 Data</w:t></w:r></w:p>
        <w:p><w:r><w:t>after</w:t></w:r></w:p>
        </w:body>'''
    )
    children = list(body)
    table = children[1]
    caption_cn = children[2]
    caption_en = children[3]

    moved = _place_table_captions_before_tables(
        body,
        [
            {
                "relation_type": "caption_of",
                "source_content_id": "caption-cn",
                "target_content_id": "table",
            },
            {
                "relation_type": "caption_of",
                "source_content_id": "caption-en",
                "target_content_id": "table",
            },
        ],
        {
            "table": table,
            "caption-cn": caption_cn,
            "caption-en": caption_en,
        },
        {
            "table": {"field_id": "body.table"},
            "caption-cn": {"field_id": "body.table.caption"},
            "caption-en": {"field_id": "body.table.caption"},
        },
    )

    assert moved == 1
    assert list(body)[1:4] == [caption_cn, caption_en, table]


def test_body_object_references_consume_materialized_caption_numbers() -> None:
    paragraph = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>结果见图4-1、图 4.2和表1-1。</w:t></w:r></w:p>'
    )
    state = _CaptionNumberingState([])
    state.record_source_number(
        kind="figure",
        source_number="4-1",
        target_number=(3, 4),
    )
    state.record_source_number(
        kind="figure",
        source_number="4-2",
        target_number=(3, 5),
    )
    state.record_source_number(
        kind="table",
        source_number="1-1",
        target_number=(3, 1),
    )

    changed = _materialize_object_references([paragraph], state)

    assert changed == 3
    assert _paragraph_text(paragraph) == "结果见图3-4、图 3-5和表3-1。"


def test_body_object_reference_rewrite_does_not_cascade_target_numbers() -> None:
    paragraph = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>结果见表1-1，目标引用已是表3-1。</w:t></w:r></w:p>'
    )
    state = _CaptionNumberingState([])
    state.target_numbers_by_kind = {"table": {"3-1", "3-3"}}
    state.record_source_number(
        kind="table",
        source_number="1-1",
        target_number=(3, 1),
    )
    state.record_source_number(
        kind="table",
        source_number="3-1",
        target_number=(3, 3),
    )

    changed = _materialize_object_references([paragraph], state)

    assert changed == 1
    assert _paragraph_text(paragraph) == "结果见表3-1，目标引用已是表3-1。"


def test_body_object_reference_rewrite_does_not_match_target_prefix() -> None:
    paragraph = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>结果见图1，目标引用已是图3-1。</w:t></w:r></w:p>'
    )
    state = _CaptionNumberingState([])
    state.target_numbers_by_kind = {"figure": {"3-1", "3-3"}}
    state.record_source_number(
        kind="figure",
        source_number="1",
        target_number=(3, 1),
    )
    state.record_source_number(
        kind="figure",
        source_number="3",
        target_number=(3, 3),
    )

    changed = _materialize_object_references([paragraph], state)

    assert changed == 1
    assert _paragraph_text(paragraph) == "结果见图3-1，目标引用已是图3-1。"


def test_text_replacement_crosses_runs_without_flattening_them() -> None:
    paragraph = ET.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:r><w:t>AlphaBeta</w:t></w:r>'
        "<w:r><w:t>sp.</w:t></w:r><w:r><w:t> remains</w:t></w:r></w:p>"
    )

    changed = _replace_across_text_nodes(paragraph, "AlphaBetasp.", "AlphaBeta sp.")

    assert changed == 1
    assert _paragraph_text(paragraph) == "AlphaBeta sp. remains"
    assert len(paragraph.findall(_q("r"))) == 3


def test_semantic_paragraph_replacement_removes_field_residue() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:jc w:val="both"/></w:pPr>
        <w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>Visible citation [1]</w:t></w:r>
        <w:r><w:fldChar w:fldCharType="begin"/></w:r>
        <w:r><w:instrText> REF docfit_ref_1 </w:instrText></w:r>
        <w:r><w:fldChar w:fldCharType="end"/></w:r>
        </w:p>'''
    )

    removed = _replace_semantic_paragraph_text(paragraph, "Visible citation [1]")

    assert removed == 3
    assert _paragraph_text(paragraph) == "Visible citation [1]"
    assert not list(paragraph.iter(_q("fldChar")))
    assert not list(paragraph.iter(_q("instrText")))
    assert paragraph.find(_q("pPr")) is not None
    assert paragraph.find(f"{_q('r')}/{_q('rPr')}/{_q('vertAlign')}") is None


def test_projection_text_writers_remove_invalid_xml_control_characters() -> None:
    paragraph = ET.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:t>old</w:t></w:r></w:p>')

    _replace_paragraph_text(paragraph, "表题\x0b英文表题")

    assert _paragraph_text(paragraph) == "表题英文表题"


def test_body_inline_semantics_are_target_materialized() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="body"/></w:pPr>
        <w:r><w:t>PGPR[1]与Pantoea dispersa和trpA有关</w:t></w:r>
        </w:p>'''
    )

    materialized = _materialize_body_inline_semantics(paragraph)

    assert materialized == 3
    assert _paragraph_text(paragraph) == "PGPR[1]与Pantoea dispersa和trpA有关"
    citation_run = next(run for run in paragraph.findall(_q("r")) if _paragraph_text(run) == "[1]")
    citation_properties = citation_run.find(_q("rPr"))
    assert citation_properties is not None
    assert citation_properties.find(_q("sz")).get(_q("val")) == "24"  # type: ignore[union-attr]
    assert citation_properties.find(_q("szCs")) is None
    assert citation_properties.find(_q("vertAlign")).get(_q("val")) == "superscript"  # type: ignore[union-attr]
    taxa_run = next(
        run for run in paragraph.findall(_q("r")) if _paragraph_text(run) == "Pantoea dispersa"
    )
    taxa_properties = taxa_run.find(_q("rPr"))
    assert taxa_properties is not None
    assert [child.tag.rsplit("}", 1)[-1] for child in taxa_properties] == [
        "i",
        "iCs",
        "color",
        "sz",
    ]
    assert taxa_properties.find(_q("sz")).get(_q("val")) == "24"  # type: ignore[union-attr]
    assert taxa_properties.find(_q("szCs")) is None
    assert taxa_properties.find(_q("i")) is not None
    assert taxa_properties.find(_q("iCs")) is not None
    gene_run = next(run for run in paragraph.findall(_q("r")) if _paragraph_text(run) == "trpA")
    gene_properties = gene_run.find(_q("rPr"))
    assert gene_properties is not None
    assert gene_properties.find(_q("i")) is not None
    assert gene_properties.find(_q("iCs")) is not None


def test_body_inline_semantics_do_not_preserve_source_italic_as_target_semantics() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="old"/></w:pPr>
        <w:r><w:rPr><w:i/></w:rPr><w:t>普通中文不继承源斜体</w:t></w:r>
        </w:p>'''
    )

    _normalize_text_paragraph(paragraph, "body")
    materialized = _materialize_body_inline_semantics(paragraph)

    assert materialized == 0
    run_properties = paragraph.find(f"{_q('r')}/{_q('rPr')}")
    assert run_properties is not None
    assert run_properties.find(_q("i")) is None
    assert run_properties.find(_q("iCs")) is None


def test_body_inline_semantics_preserve_vertical_semantics_after_style_reset() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="old"/></w:pPr>
        <w:r><w:rPr><w:rFonts w:ascii="Calibri"/><w:sz w:val="21"/></w:rPr><w:t>大气氮气（N</w:t></w:r>
        <w:r><w:rPr><w:vertAlign w:val="subscript"/><w:sz w:val="21"/></w:rPr><w:t>2</w:t></w:r>
        <w:r><w:rPr><w:rFonts w:ascii="Calibri"/><w:sz w:val="21"/></w:rPr><w:t>）和铵态氮（NH</w:t></w:r>
        <w:r><w:rPr><w:vertAlign w:val="superscript"/><w:sz w:val="21"/></w:rPr><w:t>4+</w:t></w:r>
        <w:r><w:t>）相关[3]。</w:t></w:r>
        </w:p>'''  # noqa: E501
    )

    _normalize_text_paragraph(paragraph, "body")
    materialized = _materialize_body_inline_semantics(paragraph)

    assert materialized >= 3
    assert _paragraph_text(paragraph) == "大气氮气（N2）和铵态氮（NH4+）相关[3]。"
    by_text = {_paragraph_text(run): run.find(_q("rPr")) for run in paragraph.findall(_q("r"))}
    assert by_text["2"] is not None
    assert by_text["2"].find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]
    assert by_text["4+"] is not None
    assert by_text["4+"].find(_q("vertAlign")).get(_q("val")) == "superscript"  # type: ignore[union-attr]
    assert by_text["[3]"] is not None
    assert by_text["[3]"].find(_q("vertAlign")).get(_q("val")) == "superscript"  # type: ignore[union-attr]
    for properties in by_text.values():
        assert properties is not None
        assert properties.find(_q("sz")).get(_q("val")) == "24"  # type: ignore[union-attr]
        assert properties.find(_q("szCs")) is None


def test_body_inline_semantics_recover_formula_semantics_from_flat_text() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="body"/></w:pPr>
        <w:r><w:t>大气氮气（N2）和铵态氮（NH4+），Fe3+、FeCl3、OD600与ddH2O均出现。</w:t></w:r>
        </w:p>'''
    )

    materialized = _materialize_body_inline_semantics(paragraph)

    assert materialized == 6
    assert (
        _paragraph_text(paragraph)
        == "大气氮气（N2）和铵态氮（NH4+），Fe3+、FeCl3、OD600与ddH2O均出现。"
    )
    runs = [(_paragraph_text(run), run.find(_q("rPr"))) for run in paragraph.findall(_q("r"))]
    by_text = {text: properties for text, properties in runs}
    for _, properties in [item for item in runs if item[0] == "2"]:
        assert properties is not None
        assert properties.find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]
    assert by_text["2"].find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]
    assert by_text["4+"].find(_q("vertAlign")).get(_q("val")) == "superscript"  # type: ignore[union-attr]
    assert by_text["3+"].find(_q("vertAlign")).get(_q("val")) == "superscript"  # type: ignore[union-attr]
    assert by_text["3"].find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]
    assert by_text["600"].find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]


def test_plain_paragraph_replacement_preserves_inline_content_controls() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:sdt><w:sdtPr><w:tag w:val="keywords.zh.1"/></w:sdtPr>
          <w:sdtContent><w:r><w:t>旧关键词</w:t></w:r></w:sdtContent>
        </w:sdt>
        </w:p>'''
    )

    _replace_paragraph_text(paragraph, "关键词：PGPR")

    tag = paragraph.find(f".//{_q('tag')}")
    assert tag is not None
    assert tag.get(_q("val")) == "keywords.zh.1"
    assert _paragraph_text(paragraph) == "关键词：PGPR"


def test_body_paragraph_projection_writes_target_body_layout() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr>
          <w:pStyle w:val="old"/>
          <w:spacing w:after="240"/>
          <w:ind w:firstLineChars="225"/>
          <w:jc w:val="both"/>
        </w:pPr>
        <w:r><w:t>正文</w:t></w:r>
        </w:p>'''
    )

    _normalize_text_paragraph(paragraph, "a")

    p_pr = paragraph.find(_q("pPr"))
    assert p_pr is not None
    style = p_pr.find(_q("pStyle"))
    spacing = p_pr.find(_q("spacing"))
    indent = p_pr.find(_q("ind"))
    jc = p_pr.find(_q("jc"))
    paragraph_run_defaults = p_pr.find(_q("rPr"))
    auto_space_de = p_pr.find(_q("autoSpaceDE"))
    auto_space_dn = p_pr.find(_q("autoSpaceDN"))
    assert style is None
    assert auto_space_de is not None
    assert auto_space_de.get(_q("val")) == "0"
    assert auto_space_dn is not None
    assert auto_space_dn.get(_q("val")) == "0"
    assert spacing is not None
    assert spacing.get(_q("before")) is None
    assert spacing.get(_q("after")) is None
    assert spacing.get(_q("line")) == "400"
    assert spacing.get(_q("lineRule")) == "exact"
    assert indent is not None
    assert indent.get(_q("firstLineChars")) == "200"
    assert indent.get(_q("firstLine")) == "480"
    assert jc is not None
    assert jc.get(_q("val")) == "left"
    assert paragraph_run_defaults is not None
    assert paragraph_run_defaults.find(_q("rFonts")).get(_q("ascii")) == "宋体"  # type: ignore[union-attr]
    assert paragraph_run_defaults.find(_q("rFonts")).get(_q("hAnsi")) == "宋体"  # type: ignore[union-attr]
    assert paragraph_run_defaults.find(_q("sz")).get(_q("val")) == "24"  # type: ignore[union-attr]
    run_pr = paragraph.find(f"{_q('r')}/{_q('rPr')}")
    assert run_pr is not None
    color = run_pr.find(_q("color"))
    size = run_pr.find(_q("sz"))
    assert color is not None
    assert color.get(_q("val")) == "000000"
    assert size is not None
    assert size.get(_q("val")) == "24"
    assert run_pr.find(_q("szCs")) is None


def test_body_run_style_is_reapplied_after_source_layout_cleanup() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:t>正文</w:t></w:r>
        </w:p>'''
    )

    _normalize_text_paragraph(paragraph, "a")
    _clear_run_layout(paragraph)
    _normalize_body_run_style(paragraph)

    run_pr = paragraph.find(f"{_q('r')}/{_q('rPr')}")
    assert run_pr is not None
    assert run_pr.find(_q("color")).get(_q("val")) == "000000"  # type: ignore[union-attr]
    assert run_pr.find(_q("sz")).get(_q("val")) == "24"  # type: ignore[union-attr]
    assert run_pr.find(_q("szCs")) is None


def test_caption_projection_writes_target_pagination_layout() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="old"/></w:pPr>
        <w:r><w:t>图 1-1 示例</w:t></w:r>
        </w:p>'''
    )

    _normalize_caption(paragraph, "caption")

    p_pr = paragraph.find(_q("pPr"))
    assert p_pr is not None
    assert p_pr.find(_q("pStyle")) is None
    assert p_pr.find(_q("autoSpaceDE")).get(_q("val")) == "0"  # type: ignore[union-attr]
    assert p_pr.find(_q("autoSpaceDN")).get(_q("val")) == "0"  # type: ignore[union-attr]
    spacing = p_pr.find(_q("spacing"))
    assert spacing is not None
    assert spacing.get(_q("line")) == "400"
    assert spacing.get(_q("lineRule")) == "exact"
    assert p_pr.find(_q("keepLines")) is not None
    assert p_pr.find(_q("jc")).get(_q("val")) == "center"  # type: ignore[union-attr]
    assert p_pr.find(_q("rPr")) is not None


def test_drawing_projection_writes_keep_lines() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="old"/></w:pPr>
        <w:r><w:drawing/></w:r>
        </w:p>'''
    )

    _normalize_drawing_paragraph(paragraph, "normal", None)

    p_pr = paragraph.find(_q("pPr"))
    assert p_pr is not None
    assert p_pr.find(_q("keepLines")) is not None
    assert p_pr.find(_q("jc")).get(_q("val")) == "center"  # type: ignore[union-attr]


def test_heading_materialization_rebuilds_target_minimal_formatting() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr><w:pStyle w:val="old"/><w:jc w:val="both"/></w:pPr>
        <w:r><w:rPr><w:rFonts w:eastAsia="宋体"/><w:b w:val="0"/><w:sz w:val="24"/>
          <w:vertAlign w:val="baseline"/></w:rPr><w:t>1.2 源标题</w:t></w:r>
        </w:p>'''
    )
    heading_state = [1, 0, 0]

    changed = _materialize_heading_number(paragraph, "heading_2", heading_state)
    _normalize_heading_paragraph(paragraph, "23", role="heading_2")

    assert changed is True
    assert _paragraph_text(paragraph) == "1 源标题"
    paragraph_properties = paragraph.find(_q("pPr"))
    assert paragraph_properties is not None
    assert paragraph_properties.find(_q("pStyle")).get(_q("val")) == "23"  # type: ignore[union-attr]
    assert paragraph_properties.find(_q("autoSpaceDE")).get(_q("val")) == "0"  # type: ignore[union-attr]
    assert paragraph_properties.find(_q("spacing")).get(_q("line")) == "400"  # type: ignore[union-attr]
    assert paragraph_properties.find(_q("outlineLvl")).get(_q("val")) == "1"  # type: ignore[union-attr]
    paragraph_run_defaults = paragraph_properties.find(_q("rPr"))
    assert paragraph_run_defaults is not None
    assert paragraph_run_defaults.find(_q("rFonts")).get(_q("ascii")) == "黑体"  # type: ignore[union-attr]
    assert paragraph_run_defaults.find(_q("rFonts")).get(_q("hAnsi")) == "黑体"  # type: ignore[union-attr]
    assert paragraph_run_defaults.find(_q("szCs")).get(_q("val")) == "28"  # type: ignore[union-attr]
    run_properties = paragraph.find(f"{_q('r')}/{_q('rPr')}")
    assert run_properties is not None
    assert [child.tag.rsplit("}", 1)[-1] for child in run_properties] == [
        "rFonts",
        "color",
        "szCs",
    ]
    assert run_properties.find(_q("rFonts")).get(_q("ascii")) == "黑体"  # type: ignore[union-attr]
    assert run_properties.find(_q("color")).get(_q("val")) == "000000"  # type: ignore[union-attr]
    assert run_properties.find(_q("szCs")).get(_q("val")) == "28"  # type: ignore[union-attr]
    assert run_properties.find(_q("b")) is None
    assert run_properties.find(_q("vertAlign")) is None


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


def test_chapter_boundary_materializes_later_chapter_page_breaks() -> None:
    early = ET.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:t>第二章 材料与方法</w:t></w:r></w:p>')
    later = ET.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:t>第三章 结果与分析</w:t></w:r></w:p>')

    _normalize_heading_paragraph(early, "H1", role="heading_1", chapter_index=2)
    _normalize_heading_paragraph(later, "H1", role="heading_1", chapter_index=3)

    early_properties = early.find(_q("pPr"))
    later_properties = later.find(_q("pPr"))
    assert early_properties is not None
    assert later_properties is not None
    assert early_properties.find(_q("pageBreakBefore")) is None
    assert later_properties.find(_q("pageBreakBefore")) is not None
    assert later_properties.find(_q("autoSpaceDE")).get(_q("val")) == "0"  # type: ignore[union-attr]
    assert later_properties.find(_q("autoSpaceDN")).get(_q("val")) == "0"  # type: ignore[union-attr]


def test_post_style_layout_closure_owns_front_toc_reference_and_appendix_layers(
    tmp_path: Path,
) -> None:
    docx = tmp_path / "candidate.docx"
    document_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}">
  <w:body>
    <w:p><w:pPr><w:jc w:val="left"/></w:pPr><w:r><w:t>目  录</w:t></w:r></w:p>
    <w:p><w:r><w:t>植物促生菌PGP6生长素合成基因的鉴定与功能验证</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="1"/><w:outlineLvl w:val="0"/></w:pPr><w:r><w:t>摘  要</w:t></w:r></w:p>
    <w:p><w:pPr><w:pageBreakBefore w:val="0"/><w:jc w:val="both"/></w:pPr><w:r><w:t>植物根际促生菌PGP6以trpA和patB为对象。</w:t></w:r></w:p>
    <w:p><w:r><w:t>关键词：植物根际促生菌；PGP6</w:t></w:r></w:p>
    <w:p><w:r><w:t>Identification and Functional Characterization of Indole-3-Acetic Acid Biosynthesis-Related Genes</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="1"/><w:outlineLvl w:val="0"/></w:pPr><w:r><w:t>ABSTRACT</w:t></w:r></w:p>
    <w:p/>
    <w:p><w:r><w:t>Plant growth-promoting rhizobacteria are beneficial microorganisms.</w:t></w:r></w:p>
    <w:p><w:r><w:t>KEY WORDS：PGPR</w:t></w:r></w:p>
    <w:p><w:r><w:t>第一章 文献综述</w:t></w:r></w:p>
    <w:p><w:r><w:br w:type="page"/></w:r></w:p>
    <w:p/>
    <w:p><w:r><w:br w:type="page"/></w:r></w:p>
    <w:p><w:r><w:t>参考文献</w:t></w:r></w:p>
    <w:p/>
    <w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>Kloepper J W reference.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="1"/></w:pPr><w:r><w:t>附  录</w:t></w:r></w:p>
    <w:tbl>
      <w:tblPr><w:tblBorders><w:insideH w:val="single"/></w:tblBorders></w:tblPr>
      <w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/></w:tblGrid>
      <w:tr><w:tblPrEx/><w:tc><w:p><w:r><w:t>序号</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>引物名称</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1-PatB-B1-F</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>'''  # noqa: E501
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    report = materialize_post_style_layout_closure(docx=docx)

    with zipfile.ZipFile(docx) as archive:
        body = ET.fromstring(archive.read("word/document.xml")).find(_q("body"))
    assert body is not None
    paragraphs = body.findall(_q("p"))
    toc_heading = paragraphs[0]
    assert _paragraph_text(toc_heading) == "目  录"
    assert toc_heading.find(f"{_q('pPr')}/{_q('jc')}").get(_q("val")) == "center"  # type: ignore[union-attr]
    abstract_index = next(i for i, p in enumerate(paragraphs) if _paragraph_text(p) == "ABSTRACT")
    assert _paragraph_text(paragraphs[abstract_index + 1]).startswith("Plant growth-promoting")
    zh_abstract = next(p for p in paragraphs if "trpA" in _paragraph_text(p))
    assert any(
        _paragraph_text(run) == "trpA" and run.find(f"{_q('rPr')}/{_q('i')}") is not None
        for run in zh_abstract.findall(_q("r"))
    )
    english = next(p for p in paragraphs if _paragraph_text(p).startswith("Plant growth-promoting"))
    english_fonts = english.find(f"{_q('r')}/{_q('rPr')}/{_q('rFonts')}")
    assert english_fonts is not None
    assert english_fonts.get(_q("eastAsia")) == "Times New Roman"
    reference = next(p for p in paragraphs if _paragraph_text(p) == "参考文献")
    reference_index = paragraphs.index(reference)
    assert _paragraph_text(paragraphs[reference_index + 1]).startswith("Kloepper")
    preceding_blanks = []
    scan = reference_index - 1
    while scan >= 0 and not _paragraph_text(paragraphs[scan]).strip():
        preceding_blanks.append(paragraphs[scan])
        scan -= 1
    assert sum(1 for paragraph in preceding_blanks if _has_page_break(paragraph)) == 1
    reference_entry = paragraphs[reference_index + 1]
    assert reference_entry.find(f"{_q('pPr')}/{_q('autoSpaceDE')}").get(_q("val")) == "0"  # type: ignore[union-attr]
    table = body.find(_q("tbl"))
    assert table is not None
    table_index = list(body).index(table)
    assert all(
        item.tag == _q("p") and not _paragraph_text(item).strip()
        for item in list(body)[table_index - 2 : table_index]
    )
    assert table.find(f"{_q('tblPr')}/{_q('tblBorders')}/{_q('insideH')}").get(_q("val")) == "nil"  # type: ignore[union-attr]
    assert table.find(f"{_q('tr')}/{_q('tblPrEx')}") is None
    assert report["references"]["pre_heading_breaks_removed"] == 2
    assert report["appendix"]["caption_height_placeholders_inserted"] == 2


def test_projection_table_edits_preserve_ooxml_child_order() -> None:
    table = ET.fromstring(
        f'''<w:tbl xmlns:w="{W_NS}">
        <w:tblPr><w:tblInd w:w="120" w:type="dxa"/><w:tblBorders/><w:tblCellMar/></w:tblPr>
        <w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="2000"/></w:tblGrid>
        <w:tr>
          <w:tblPrEx/>
          <w:tc>
            <w:tcPr><w:gridSpan w:val="1"/></w:tcPr>
            <w:p><w:pPr><w:spacing/><w:ind/><w:jc/></w:pPr><w:r><w:t>A</w:t></w:r></w:p>
          </w:tc>
          <w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc>
        </w:tr>
        </w:tbl>'''
    )
    row = table.find(_q("tr"))
    assert row is not None
    paragraph = table.find(f".//{_q('p')}")
    assert paragraph is not None

    removed = _normalize_table(table, 3000)
    _set_paragraph_flag(paragraph, "keepNext", True)

    table_properties = table.find(_q("tblPr"))
    assert table_properties is not None
    table_names = [child.tag.rsplit("}", 1)[-1] for child in list(table_properties)]
    row_names = [child.tag.rsplit("}", 1)[-1] for child in list(row)]
    cell_properties = table.find(f".//{_q('tcPr')}")
    assert cell_properties is not None
    cell_names = [child.tag.rsplit("}", 1)[-1] for child in list(cell_properties)]
    paragraph_properties = paragraph.find(_q("pPr"))
    assert paragraph_properties is not None
    paragraph_names = [child.tag.rsplit("}", 1)[-1] for child in list(paragraph_properties)]
    assert table_names.index("tblW") < table_names.index("tblBorders")
    assert table_names.index("jc") < table_names.index("tblBorders")
    assert "tblInd" not in table_names
    assert "tblCellMar" not in table_names
    assert removed == 1
    assert "tblPrEx" not in row_names
    assert row_names.index("trPr") < row_names.index("tc")
    assert cell_names.index("tcW") < cell_names.index("gridSpan")
    assert paragraph_names.index("keepNext") < paragraph_names.index("spacing")


def test_body_table_materialization_uses_target_table_contract() -> None:
    table = ET.fromstring(
        f'''<w:tbl xmlns:w="{W_NS}">
        <w:tblPr>
          <w:tblW w:w="0" w:type="auto"/>
          <w:tblInd w:w="120" w:type="dxa"/>
          <w:tblBorders>
            <w:top w:val="single" w:color="auto" w:sz="4" w:space="0"/>
            <w:left w:val="single" w:color="auto" w:sz="4" w:space="0"/>
            <w:bottom w:val="single" w:color="auto" w:sz="4" w:space="0"/>
            <w:right w:val="single" w:color="auto" w:sz="4" w:space="0"/>
            <w:insideH w:val="single" w:color="auto" w:sz="4" w:space="0"/>
            <w:insideV w:val="single" w:color="auto" w:sz="4" w:space="0"/>
          </w:tblBorders>
          <w:tblCellMar>
            <w:top w:w="80" w:type="dxa"/>
            <w:bottom w:w="80" w:type="dxa"/>
          </w:tblCellMar>
        </w:tblPr>
        <w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="2000"/></w:tblGrid>
        <w:tr>
          <w:tblPrEx>
            <w:tblBorders>
              <w:top w:val="single"/>
              <w:insideH w:val="single"/>
              <w:insideV w:val="single"/>
            </w:tblBorders>
          </w:tblPrEx>
          <w:tc><w:tcPr><w:tcW w:w="1000" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>
            <w:p><w:pPr><w:spacing w:line="280" w:lineRule="exact"/></w:pPr>
              <w:r><w:rPr><w:b/><w:sz w:val="24"/></w:rPr><w:t>表头</w:t></w:r></w:p>
          </w:tc>
          <w:tc><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:tc>
        </w:tr>
        <w:tr>
          <w:tblPrEx>
            <w:tblCellMar><w:left w:w="108" w:type="dxa"/></w:tblCellMar>
          </w:tblPrEx>
          <w:tc><w:tcPr><w:tcBorders><w:top w:val="single"/></w:tcBorders><w:vAlign w:val="center"/></w:tcPr>
            <w:p><w:r><w:rPr><w:sz w:val="24"/></w:rPr><w:t>正文</w:t></w:r></w:p>
          </w:tc>
          <w:tc><w:p><w:r><w:t>Body</w:t></w:r></w:p></w:tc>
        </w:tr>
        </w:tbl>'''  # noqa: E501
    )

    removed = _normalize_table(table, 9638, target_width_dxa=9085)

    table_properties = table.find(_q("tblPr"))
    assert table_properties is not None
    width = table_properties.find(_q("tblW"))
    assert width is not None
    assert width.get(_q("type")) == "dxa"
    assert width.get(_q("w")) == "9085"
    assert table_properties.find(_q("tblInd")) is None
    assert table_properties.find(_q("tblCellMar")) is None
    borders = table_properties.find(_q("tblBorders"))
    assert borders is not None
    assert [(child.tag.rsplit("}", 1)[-1], child.get(_q("val"))) for child in borders] == [
        ("top", "single"),
        ("left", "nil"),
        ("bottom", "single"),
        ("right", "nil"),
        ("insideH", "nil"),
        ("insideV", "nil"),
    ]
    assert borders.find(_q("top")).get(_q("sz")) == "8"  # type: ignore[union-attr]
    look = table_properties.find(_q("tblLook"))
    assert look is not None
    assert look.get(_q("firstRow")) == "1"
    assert look.get(_q("noVBand")) == "1"
    assert [
        column.get(_q("w")) for column in table.findall(f"{_q('tblGrid')}/{_q('gridCol')}")
    ] == [
        "3028",
        "6057",
    ]

    rows = table.findall(_q("tr"))
    header_properties = rows[0].find(_q("trPr"))
    body_properties = rows[1].find(_q("trPr"))
    assert header_properties is not None
    assert body_properties is not None
    assert removed == 2
    assert all(row.find(_q("tblPrEx")) is None for row in rows)
    assert header_properties.find(_q("tblHeader")) is not None
    assert body_properties.find(_q("tblHeader")) is None
    header_cell_properties = rows[0].find(f"{_q('tc')}/{_q('tcPr')}")
    body_cell_properties = rows[1].find(f"{_q('tc')}/{_q('tcPr')}")
    assert header_cell_properties is not None
    assert body_cell_properties is not None
    assert header_cell_properties.find(_q("vAlign")).get(_q("val")) == "center"  # type: ignore[union-attr]
    assert body_cell_properties.find(_q("vAlign")).get(_q("val")) == "center"  # type: ignore[union-attr]
    header_cell_borders = header_cell_properties.find(_q("tcBorders"))
    assert header_cell_borders is not None
    assert [
        (child.tag.rsplit("}", 1)[-1], child.get(_q("val"))) for child in header_cell_borders
    ] == [
        ("bottom", "single"),
    ]
    assert body_cell_properties.find(_q("tcBorders")) is None

    header_paragraph = rows[0].find(f"{_q('tc')}/{_q('p')}")
    assert header_paragraph is not None
    paragraph_properties = header_paragraph.find(_q("pPr"))
    assert paragraph_properties is not None
    assert [child.tag.rsplit("}", 1)[-1] for child in paragraph_properties] == [
        "autoSpaceDE",
        "autoSpaceDN",
        "spacing",
        "jc",
        "rPr",
    ]
    assert paragraph_properties.find(_q("autoSpaceDE")).get(_q("val")) == "0"  # type: ignore[union-attr]
    assert paragraph_properties.find(_q("autoSpaceDN")).get(_q("val")) == "0"  # type: ignore[union-attr]
    assert paragraph_properties.find(_q("spacing")).get(_q("line")) == "300"  # type: ignore[union-attr]
    assert paragraph_properties.find(_q("jc")).get(_q("val")) == "center"  # type: ignore[union-attr]
    run_properties = header_paragraph.find(f"{_q('r')}/{_q('rPr')}")
    assert run_properties is not None
    assert [child.tag.rsplit("}", 1)[-1] for child in run_properties] == [
        "color",
        "szCs",
    ]
    assert run_properties.find(_q("color")).get(_q("val")) == "000000"  # type: ignore[union-attr]
    assert run_properties.find(_q("szCs")).get(_q("val")) == "21"  # type: ignore[union-attr]


def test_body_table_cell_materialization_preserves_inline_semantics() -> None:
    table = ET.fromstring(
        f'''<w:tbl xmlns:w="{W_NS}">
        <w:tblPr/>
        <w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/></w:tblGrid>
        <w:tr>
          <w:tc><w:p><w:r><w:t>试剂</w:t></w:r></w:p></w:tc>
          <w:tc><w:p><w:r><w:t>浓度</w:t></w:r></w:p></w:tc>
        </w:tr>
        <w:tr>
          <w:tc><w:p><w:r><w:t>ddH2O</w:t></w:r></w:p></w:tc>
          <w:tc><w:p>
            <w:r><w:t>m</w:t></w:r>
            <w:r><w:rPr><w:vertAlign w:val="subscript"/><w:sz w:val="24"/></w:rPr><w:t>2</w:t></w:r>
            <w:r><w:t> value</w:t></w:r>
          </w:p></w:tc>
        </w:tr>
        </w:tbl>'''
    )

    _normalize_table(table, 2000, target_width_dxa=2000)

    body_cells = table.findall(_q("tr"))[1].findall(_q("tc"))
    flat_formula = body_cells[0].find(_q("p"))
    source_semantic = body_cells[1].find(_q("p"))
    assert flat_formula is not None
    assert source_semantic is not None
    flat_runs = [
        (_paragraph_text(run), run.find(_q("rPr"))) for run in flat_formula.findall(_q("r"))
    ]
    source_runs = [
        (_paragraph_text(run), run.find(_q("rPr"))) for run in source_semantic.findall(_q("r"))
    ]
    assert _paragraph_text(flat_formula) == "ddH2O"
    assert _paragraph_text(source_semantic) == "m2 value"
    assert any(
        text == "2"
        and properties is not None
        and properties.find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]
        and properties.find(_q("szCs")).get(_q("val")) == "21"  # type: ignore[union-attr]
        for text, properties in flat_runs
    )
    assert any(
        text == "2"
        and properties is not None
        and properties.find(_q("vertAlign")).get(_q("val")) == "subscript"  # type: ignore[union-attr]
        and properties.find(_q("szCs")).get(_q("val")) == "21"  # type: ignore[union-attr]
        for text, properties in source_runs
    )


def test_reference_projection_owns_final_direct_layout() -> None:
    paragraph = ET.fromstring(
        f'''<w:p xmlns:w="{W_NS}">
        <w:pPr>
          <w:pStyle w:val="old"/>
          <w:numPr><w:ilvl w:val="0"/><w:numId w:val="3"/></w:numPr>
          <w:ind w:left="420" w:hanging="420"/>
        </w:pPr>
        <w:r><w:rPr><w:b/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr>
          <w:t>Kloepper J W reference</w:t></w:r>
        </w:p>'''
    )

    _normalize_reference(paragraph, "reference-style")

    p_pr = paragraph.find(_q("pPr"))
    assert p_pr is not None
    assert p_pr.find(_q("pStyle")) is None
    assert p_pr.find(_q("numPr")) is not None
    assert p_pr.find(_q("ind")) is None
    spacing = p_pr.find(_q("spacing"))
    assert spacing is not None
    assert spacing.get(_q("after")) == "240"
    assert spacing.get(_q("line")) == "400"
    assert spacing.get(_q("lineRule")) == "exact"
    paragraph_run_defaults = p_pr.find(_q("rPr"))
    assert paragraph_run_defaults is not None
    assert paragraph_run_defaults.find(_q("rFonts")).get(_q("cs")) == "Arial"  # type: ignore[union-attr]
    assert paragraph_run_defaults.find(_q("kern")).get(_q("val")) == "0"  # type: ignore[union-attr]
    run_properties = paragraph.find(f"{_q('r')}/{_q('rPr')}")
    assert run_properties is not None
    assert [child.tag.rsplit("}", 1)[-1] for child in run_properties] == [
        "color",
        "sz",
    ]
    assert run_properties.find(_q("color")).get(_q("val")) == "000000"  # type: ignore[union-attr]
    assert run_properties.find(_q("sz")).get(_q("val")) == "24"  # type: ignore[union-attr]


def test_projection_inserts_update_fields_in_settings_schema_order() -> None:
    document = ET.fromstring(
        f'''<w:document xmlns:w="{W_NS}">
        <w:body>
          <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>
          <w:r><w:instrText>TOC \\o "1-3"</w:instrText></w:r></w:p>
        </w:body>
        </w:document>'''
    )
    parts = {
        "word/settings.xml": (
            f'<w:settings xmlns:w="{W_NS}"><w:zoom/><w:compat/><w:rsids/></w:settings>'
        ).encode()
    }

    _request_toc_update(parts, document)

    settings = ET.fromstring(parts["word/settings.xml"])
    names = [child.tag.rsplit("}", 1)[-1] for child in list(settings)]
    update = settings.find(_q("updateFields"))
    assert update is not None
    assert update.get(_q("val")) == "true"
    assert names.index("updateFields") < names.index("compat")
    compat_setting = settings.find(f"{_q('compat')}/{_q('compatSetting')}")
    assert compat_setting is not None
    assert compat_setting.get(_q("name")) == "useWord2013TrackBottomHyphenation"
    assert compat_setting.get(_q("uri")) == "http://schemas.microsoft.com/office/word"
    assert compat_setting.get(_q("val")) == "1"


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
            ],
        },
    )

    assert resolved.normal == "Normal"
    assert resolved.body == "Body"
    assert resolved.heading_1 == "H1"
    assert resolved.heading_2 == "Body"
    assert resolved.reference == "Body"
    assert resolved.caption == "caption"


def test_slot_style_contract_headings_resolve_to_template_heading_styles(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    styles = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{W_NS}">
 <w:style w:type="paragraph" w:default="1" w:styleId="a">
  <w:name w:val="Normal"/>
 </w:style>
 <w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/></w:style>
 <w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/></w:style>
 <w:style w:type="paragraph" w:styleId="23"><w:name w:val="标题2"/></w:style>
</w:styles>"""
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("word/styles.xml", styles)

    resolved = resolve_template_style_map(
        template_docx=template,
        contract={
            "schema_version": "docfit-template-fill-contract/v2",
            "styles": [
                {
                    "style_contract_id": "style.slot.body.heading.level1.1",
                    "effective_properties": {"paragraph.outline_level": 0},
                },
                {
                    "style_contract_id": "style.slot.body.heading.level2.1",
                    "effective_properties": {"paragraph.outline_level": 1},
                },
                {
                    "style_contract_id": "style.slot.body.heading.level3.1",
                    "effective_properties": {"paragraph.outline_level": 2},
                },
            ],
        },
    )

    assert resolved.normal == "a"
    assert resolved.heading_1 == "1"
    assert resolved.heading_2 == "23"
    assert resolved.heading_3 == "23"


def test_style_roles_fail_closed_on_retired_v1_style_id_alias(tmp_path: Path) -> None:

    template = tmp_path / "template.docx"
    styles = f'''<w:styles xmlns:w="{W_NS}">
    <w:style w:type="paragraph" w:default="1" w:styleId="Normal"/>
    <w:style w:type="paragraph" w:styleId="H1"/>
    </w:styles>'''
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("word/styles.xml", styles)

    with pytest.raises(ToolFailure) as retired_field:
        resolve_template_style_map(
            template_docx=template,
            contract={
                "schema_version": "docfit-template-fill-contract/v2",
                "styles": [{"style_id": "style.body.chapter_title", "word_style_id": "H1"}],
            },
        )
    assert retired_field.value.code == "projection_contract_retired_style_id"

    with pytest.raises(ToolFailure) as retired_contract:
        resolve_template_style_map(
            template_docx=template,
            contract={
                "schema_version": "docfit-template-fill-contract/v1",
                "styles": [
                    {
                        "style_contract_id": "style.body.chapter_title",
                        "word_style_id": "H1",
                    }
                ],
            },
        )
    assert retired_contract.value.code == "projection_fill_contract_version_retired"


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


def test_projection_binds_multiblock_rich_text_item_to_each_imported_source() -> None:
    document = ET.fromstring(
        f'''<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
        <w:body>
          <w:p w14:paraId="00000001"><w:r><w:t>First abstract paragraph</w:t></w:r></w:p>
          <w:p w14:paraId="00000002"><w:r><w:t>Second abstract paragraph</w:t></w:r></w:p>
        </w:body>
        </w:document>'''
    )
    fill_result = {
        "block_operations": [
            {
                "field_id": "abstract.zh",
                "source_object_ids": ["obj-abstract-1", "obj-abstract-2"],
                "inserted_body_refs": [
                    {"target_locator": "/body/p[@paraId=00000001]"},
                    {"target_locator": "/body/p[@paraId=00000002]"},
                ],
                "source_content_items": [
                    {
                        "content_id": "content-abstract",
                        "field_id": "abstract.zh",
                        "physical_type": "text",
                        "transport_source_object_id": "obj-abstract-1",
                        "source_object_ids": ["obj-abstract-1", "obj-abstract-2"],
                    }
                ],
            }
        ]
    }

    semantic_by_element, content_targets, _ = _resolve_semantic_evidence(
        document,
        fill_result,
    )
    first, second = document.findall(f".//{_q('p')}")

    assert semantic_by_element[id(first)][0]["content_id"] == "content-abstract"
    assert semantic_by_element[id(second)][0]["content_id"] == "content-abstract"
    assert content_targets["content-abstract"] is first
