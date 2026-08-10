from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

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
  <w:p><w:r><w:t>1 材料与方法</w:t></w:r></w:p>
  <w:p w14:paraId="00000003"><w:r><w:t>1.2试验设计</w:t></w:r></w:p>
  <w:p w14:paraId="00000004"><w:r><w:t>正文内容</w:t></w:r></w:p>
  <w:p w14:paraId="00000005"><w:r><w:t>图 1 结构</w:t></w:r></w:p>
  <w:p w14:paraId="00000006"><w:r><w:t>表 1 数据</w:t></w:r></w:p>
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
                    "field_id": "body.chapters",
                    "inserted_body_refs": [
                        {"target_locator": "/body/p[@paraId=00000001]"},
                        {"target_locator": "/body/p[@paraId=00000009]"},
                    ],
                },
                {
                    "field_id": "references.entries",
                    "inserted_body_refs": [{"target_locator": "/body/p[@paraId=0000000A]"}],
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
        "Body",
        "Caption",
        "Caption",
        "Body",
        "Normal",
        "Body",
        "Ref",
    ]
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
        assert style is not None
        assert style.get(_q("val")) == occurrence["word_style_id"]
