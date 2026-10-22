from __future__ import annotations

import inspect
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import docfit.content.projection as projection_module
from docfit.content.projection import TemplateStyleMap, project_student_content
from docfit.tools.runtime import sha256_file

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def _write_projection_fixture(path: Path, document_xml: str) -> None:
    styles_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{W_NS}">
 <w:style w:type="paragraph" w:default="1" w:styleId="Normal"/>
 <w:style w:type="paragraph" w:styleId="Body"/>
 <w:style w:type="paragraph" w:styleId="H1"><w:basedOn w:val="Body"/></w:style>
 <w:style w:type="paragraph" w:styleId="H2"><w:basedOn w:val="Body"/></w:style>
 <w:style w:type="paragraph" w:styleId="H3"><w:basedOn w:val="Body"/></w:style>
 <w:style w:type="paragraph" w:styleId="Ref"><w:basedOn w:val="Body"/></w:style>
 <w:style w:type="paragraph" w:styleId="Caption"><w:basedOn w:val="Body"/></w:style>
</w:styles>'''
    document_content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    )
    styles_content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
    )
    settings_content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"
    )
    content_types = f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Override PartName="/word/document.xml" ContentType="{document_content_type}"/>
 <Override PartName="/word/styles.xml" ContentType="{styles_content_type}"/>
 <Override PartName="/word/settings.xml" ContentType="{settings_content_type}"/>
</Types>'''
    office_document_relationship = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    )
    relationships = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="{office_document_relationship}" Target="word/document.xml"/>
</Relationships>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/settings.xml", f'<w:settings xmlns:w="{W_NS}"/>')


def test_projection_has_no_fallback_selection_surface() -> None:
    parameters = inspect.signature(project_student_content).parameters

    assert "standard_fallback" not in parameters
    assert not hasattr(projection_module, "StandardFallbackPolicy")
    assert not hasattr(projection_module, "GB_T_7713_1_2025_PUBLIC_DRAFT_FALLBACK")


def test_projection_reports_final_roles_and_persistent_paragraph_locators(
    tmp_path: Path,
) -> None:
    input_docx = tmp_path / "input.docx"
    template_docx = tmp_path / "template.docx"
    output_docx = tmp_path / "output.docx"
    document_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}" xmlns:m="{M_NS}">
 <w:body>
  <w:p w14:paraId="00000001"><w:r><w:t>第一章 绪论</w:t></w:r></w:p>
  <w:p w14:paraId="00000002"><w:r><w:t>1 材料与方法</w:t></w:r></w:p>
  <w:p w14:paraId="00000003"><w:r><w:t>1.2试验设计</w:t></w:r></w:p>
  <w:p w14:paraId="00000004"><w:r><w:t>正文内容</w:t></w:r></w:p>
  <w:p w14:paraId="00000005"><w:r><w:t>图 1 结构</w:t></w:r></w:p>
  <w:p w14:paraId="00000006"><w:r><w:t>表 数据</w:t></w:r></w:p>
  <w:p w14:paraId="00000007"><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p>
  <w:p w14:paraId="00000008"><w:r><w:drawing/></w:r></w:p>
  <w:p w14:paraId="00000009"><w:r><w:t>末段正文</w:t></w:r></w:p>
  <w:p w14:paraId="0000000A"><w:r><w:t>[1] 参考条目</w:t></w:r></w:p>
 </w:body>
</w:document>'''
    _write_projection_fixture(input_docx, document_xml)
    _write_projection_fixture(template_docx, document_xml)

    report = project_student_content(
        input_docx=input_docx,
        template_docx=template_docx,
        fill_result={
            "output_sha256": sha256_file(input_docx),
            "template_sha256": sha256_file(template_docx),
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "source_object_ids": [f"p{index}" for index in range(1, 10)],
                    "inserted_body_refs": [
                        {"target_locator": f"/body/p[@paraId={index:08X}]"}
                        for index in range(1, 10)
                    ],
                    "source_content_items": [
                        {
                            "content_id": f"c{index}",
                            "source_content_id": f"sc{index}",
                            "transport_source_object_id": f"p{index}",
                            "field_id": field_id,
                            "classification_status": "classified",
                            "physical_type": physical_type,
                            "source_order": {"block": index, "inline": 0},
                        }
                        for index, (field_id, physical_type) in enumerate(
                            (
                                ("body.heading.outline1", "text"),
                                ("body.heading.outline2", "text"),
                                ("body.heading.outline3", "text"),
                                ("body.paragraph", "text"),
                                ("body.figure.caption", "text"),
                                ("body.table.caption", "text"),
                                ("body.equation", "equation"),
                                ("body.figure", "image"),
                                ("body.paragraph", "text"),
                            ),
                            start=1,
                        )
                    ],
                    "relations": [],
                },
                {
                    "field_id": "references.entries",
                    "source_object_ids": ["r1"],
                    "inserted_body_refs": [{"target_locator": "/body/p[@paraId=0000000A]"}],
                    "source_content_items": [
                        {
                            "content_id": "c10",
                            "source_content_id": "sc10",
                            "transport_source_object_id": "r1",
                            "field_id": "references.entries",
                            "classification_status": "classified",
                            "physical_type": "text",
                            "source_order": {"block": 10, "inline": 0},
                        }
                    ],
                },
            ],
        },
        output_docx=output_docx,
        styles=TemplateStyleMap(
            normal="Normal",
            body="Body",
            heading_1="H1",
            heading_2="H2",
            heading_3="H3",
            reference="Ref",
            caption="Caption",
        ),
    )

    occurrences = report["style_occurrences"]
    assert report["scope"] == "template_styles_only_no_builtin_fallback_styles"
    assert "standard_fallback" not in report
    assert "fallback_style_ids" not in report
    assert [item["presentation_role"] for item in occurrences] == [
        "chapter_title",
        "section_title",
        "subsection_title",
        "body",
        "figure_caption",
        "table_caption",
        "formula",
        "drawing",
        "body",
        "reference",
    ]
    assert [item["word_style_id"] for item in occurrences] == [
        "H1",
        "H2",
        "H3",
        "direct",
        "direct",
        "direct",
        "Body",
        "Normal",
        "direct",
        "direct",
    ]
    assert report["heading_numbering_materialized"] == 1
    assert report["caption_numbering_materialized"] == 2
    assert all(
        re.fullmatch(r"/body/p\[@paraId=[0-9A-F]{8}\]", item["target_locator"])
        for item in occurrences
    )

    with zipfile.ZipFile(output_docx) as archive:
        output_document = ET.fromstring(archive.read("word/document.xml"))
    output_body = output_document.find(_q("body"))
    assert output_body is not None
    output_by_para_id = {
        paragraph.get(f"{{{W14_NS}}}paraId"): paragraph
        for paragraph in output_body.findall(_q("p"))
    }
    for occurrence in occurrences:
        match = re.fullmatch(
            r"/body/p\[@paraId=([0-9A-F]{8})\]",
            occurrence["target_locator"],
        )
        assert match is not None
        paragraph = output_by_para_id[match.group(1)]
        style = paragraph.find(f"{_q('pPr')}/{_q('pStyle')}")
        if occurrence["word_style_id"] == "direct":
            assert style is None
        else:
            assert style is not None
            assert style.get(_q("val")) == occurrence["word_style_id"]
    output_text = [_text(paragraph) for paragraph in output_body.findall(_q("p"))]
    assert output_text[:6] == [
        "第一章 绪论",
        "1 材料与方法",
        "1.1 试验设计",
        "正文内容",
        "图 1-1 结构",
        "表 1-1 数据",
    ]


def test_projection_removes_split_image_carrier_residue_without_losing_drawing(
    tmp_path: Path,
) -> None:
    input_docx = tmp_path / "input.docx"
    template_docx = tmp_path / "template.docx"
    output_docx = tmp_path / "output.docx"
    document_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
 <w:body>
  <w:p w14:paraId="00000001"><w:r><w:t>第一章 绪论</w:t></w:r></w:p>
  <w:p w14:paraId="00000002">
   <w:r><w:drawing/></w:r>
   <w:r><w:t>Figure 3-6 PCR validation of mutants</w:t></w:r>
  </w:p>
  <w:p w14:paraId="00000003">
   <w:r><w:drawing/></w:r>
   <w:r><w:t>Figure 3-6 PCR validation of mutants</w:t></w:r>
  </w:p>
 </w:body>
</w:document>'''
    _write_projection_fixture(input_docx, document_xml)
    _write_projection_fixture(template_docx, document_xml)

    report = project_student_content(
        input_docx=input_docx,
        template_docx=template_docx,
        fill_result={
            "output_sha256": sha256_file(input_docx),
            "template_sha256": sha256_file(template_docx),
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "source_object_ids": ["heading", "image-carrier", "caption-text"],
                    "inserted_body_refs": [
                        {"target_locator": "/body/p[@paraId=00000001]"},
                        {"target_locator": "/body/p[@paraId=00000002]"},
                        {"target_locator": "/body/p[@paraId=00000003]"},
                    ],
                    "source_content_items": [
                        {
                            "content_id": "heading",
                            "source_content_id": "heading-source",
                            "transport_source_object_id": "heading",
                            "field_id": "body.heading.outline1",
                            "classification_status": "classified",
                            "physical_type": "text",
                            "source_order": {"block": 1, "inline": 0},
                        },
                        {
                            "content_id": "figure",
                            "source_content_id": "figure-source",
                            "transport_source_object_id": "image-carrier",
                            "field_id": "body.figure",
                            "classification_status": "classified",
                            "physical_type": "image",
                            "source_order": {"block": 2, "inline": 0},
                        },
                        {
                            "content_id": "caption",
                            "source_content_id": "caption-source",
                            "transport_source_object_id": "image-carrier",
                            "source_object_ids": ["caption-text"],
                            "field_id": "body.figure.caption",
                            "classification_status": "classified",
                            "physical_type": "text",
                            "value": "PCR validation of mutants",
                            "source_order": {"block": 2, "inline": 1},
                        },
                    ],
                    "relations": [],
                }
            ],
        },
        output_docx=output_docx,
        styles=TemplateStyleMap(
            normal="Normal",
            body="Body",
            heading_1="H1",
            heading_2="H2",
            heading_3="H3",
            reference="Ref",
            caption="Caption",
        ),
    )

    assert report["drawing_paragraphs_split"] == 1
    assert report["image_carrier_residue_paragraphs_removed"] == 1
    assert report["semantic_drawing_residue_elements_removed"] == 1
    assert [item["presentation_role"] for item in report["style_occurrences"]] == [
        "chapter_title",
        "drawing",
        "figure_caption",
    ]

    with zipfile.ZipFile(output_docx) as archive:
        output_document = ET.fromstring(archive.read("word/document.xml"))
    output_body = output_document.find(_q("body"))
    assert output_body is not None
    output_text = [_text(paragraph) for paragraph in output_body.findall(_q("p"))]
    assert output_text == ["第一章 绪论", "", "Fig. 1-1 PCR validation of mutants"]


def test_projection_treats_table_shaped_figure_carrier_as_figure(
    tmp_path: Path,
) -> None:
    input_docx = tmp_path / "input.docx"
    template_docx = tmp_path / "template.docx"
    output_docx = tmp_path / "output.docx"
    document_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
 <w:body>
  <w:tbl>
   <w:tblPr><w:tblW w:type="dxa" w:w="4000"/></w:tblPr>
   <w:tblGrid><w:gridCol w:w="4000"/></w:tblGrid>
   <w:tr><w:tc><w:p><w:r><w:drawing/></w:r></w:p></w:tc></w:tr>
  </w:tbl>
  <w:p w14:paraId="00000001"><w:r><w:t>Fig. 1 carrier</w:t></w:r></w:p>
  <w:p w14:paraId="00000002"><w:r><w:t>Table 1 data</w:t></w:r></w:p>
  <w:tbl>
   <w:tblPr><w:tblW w:type="dxa" w:w="4000"/></w:tblPr>
   <w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>
   <w:tr><w:tc><w:p><w:r><w:t>处理</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>数值</w:t></w:r></w:p></w:tc></w:tr>
   <w:tr><w:tc><w:p><w:r><w:t>P0</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc></w:tr>
  </w:tbl>
 </w:body>
</w:document>'''
    _write_projection_fixture(input_docx, document_xml)
    _write_projection_fixture(template_docx, document_xml)

    report = project_student_content(
        input_docx=input_docx,
        template_docx=template_docx,
        fill_result={
            "output_sha256": sha256_file(input_docx),
            "template_sha256": sha256_file(template_docx),
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "source_object_ids": [
                        "figure-carrier",
                        "figure-caption",
                        "table-caption",
                        "data-table",
                    ],
                    "inserted_body_refs": [
                        {"target_locator": "/body/tbl[1]"},
                        {"target_locator": "/body/p[@paraId=00000001]"},
                        {"target_locator": "/body/p[@paraId=00000002]"},
                        {"target_locator": "/body/tbl[2]"},
                    ],
                    "source_content_items": [
                        {
                            "content_id": "figure",
                            "source_content_id": "figure-source",
                            "transport_source_object_id": "figure-carrier",
                            "field_id": "body.figure",
                            "classification_status": "classified",
                            "physical_type": "image",
                            "source_order": {"block": 1, "inline": 0},
                        },
                        {
                            "content_id": "figure-caption",
                            "source_content_id": "figure-caption-source",
                            "transport_source_object_id": "figure-caption",
                            "field_id": "body.figure.caption",
                            "classification_status": "classified",
                            "physical_type": "text",
                            "value": "carrier",
                            "source_order": {"block": 2, "inline": 0},
                        },
                        {
                            "content_id": "table-caption",
                            "source_content_id": "table-caption-source",
                            "transport_source_object_id": "table-caption",
                            "field_id": "body.table.caption",
                            "classification_status": "classified",
                            "physical_type": "text",
                            "value": "data",
                            "source_order": {"block": 3, "inline": 0},
                        },
                        {
                            "content_id": "data-table",
                            "source_content_id": "data-table-source",
                            "transport_source_object_id": "data-table",
                            "field_id": "body.table",
                            "classification_status": "classified",
                            "physical_type": "table",
                            "source_order": {"block": 4, "inline": 0},
                        },
                    ],
                    "relations": [
                        {
                            "relation_type": "caption_of",
                            "source_content_id": "figure-caption",
                            "target_content_id": "figure",
                            "confidence": 1.0,
                        },
                        {
                            "relation_type": "caption_of",
                            "source_content_id": "table-caption",
                            "target_content_id": "data-table",
                            "confidence": 1.0,
                        },
                    ],
                }
            ],
        },
        output_docx=output_docx,
        styles=TemplateStyleMap(
            normal="Normal",
            body="Body",
            heading_1="H1",
            heading_2="H2",
            heading_3="H3",
            reference="Ref",
            caption="Caption",
        ),
    )

    assert report["table_shaped_figure_carriers"] == 1
    assert report["tables_normalized"] == 1
    assert report["figure_caption_chains_bound"] == 1
    assert report["table_caption_chains_bound"] == 1
    assert report["table_caption_blocks_reordered"] == 0

    with zipfile.ZipFile(output_docx) as archive:
        output_document = ET.fromstring(archive.read("word/document.xml"))
    output_body = output_document.find(_q("body"))
    assert output_body is not None
    child_tags = [child.tag.rsplit("}", 1)[-1] for child in list(output_body)]
    assert child_tags[:4] == ["tbl", "p", "p", "tbl"]
    output_text = [_text(paragraph) for paragraph in output_body.findall(_q("p"))]
    assert output_text == ["Fig. 1-1 carrier", "Table 1-1 data"]


def test_projection_removes_orphan_comment_references_without_comments_part(
    tmp_path: Path,
) -> None:
    input_docx = tmp_path / "input.docx"
    template_docx = tmp_path / "template.docx"
    output_docx = tmp_path / "output.docx"
    document_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
 <w:body>
  <w:p w14:paraId="00000001">
   <w:commentRangeStart w:id="1"/>
   <w:r><w:t>正文内容</w:t></w:r>
   <w:r><w:commentReference w:id="1"/></w:r>
   <w:commentRangeEnd w:id="1"/>
  </w:p>
 </w:body>
</w:document>'''
    _write_projection_fixture(input_docx, document_xml)
    _write_projection_fixture(template_docx, document_xml)

    report = project_student_content(
        input_docx=input_docx,
        template_docx=template_docx,
        fill_result={
            "output_sha256": sha256_file(input_docx),
            "template_sha256": sha256_file(template_docx),
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "source_object_ids": ["body"],
                    "inserted_body_refs": [
                        {"target_locator": "/body/p[@paraId=00000001]"},
                    ],
                    "source_content_items": [
                        {
                            "content_id": "body",
                            "source_content_id": "body-source",
                            "transport_source_object_id": "body",
                            "field_id": "body.paragraph",
                            "classification_status": "classified",
                            "physical_type": "text",
                            "source_order": {"block": 1, "inline": 0},
                        }
                    ],
                    "relations": [],
                }
            ],
        },
        output_docx=output_docx,
        styles=TemplateStyleMap(
            normal="Normal",
            body="Body",
            heading_1="H1",
            heading_2="H2",
            heading_3="H3",
            reference="Ref",
            caption="Caption",
        ),
    )

    assert report["orphan_comment_references_removed"] == 3
    with zipfile.ZipFile(output_docx) as archive:
        output_document = ET.fromstring(archive.read("word/document.xml"))
    assert not list(output_document.iter(_q("commentRangeStart")))
    assert not list(output_document.iter(_q("commentRangeEnd")))
    assert not list(output_document.iter(_q("commentReference")))


def _text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(_q("t")))
