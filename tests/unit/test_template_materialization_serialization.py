from __future__ import annotations

from xml.etree import ElementTree as ET

from docfit.template.materialization.runtime import (
    _paragraph_is_in_vertically_centered_table_cell,
    _serialize,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"


def test_materialization_preserves_standard_drawingml_prefixes() -> None:
    document = ET.fromstring(
        f"""
        <w:document xmlns:w="{W_NS}" xmlns:a="{A_NS}"
          xmlns:a14="{A14_NS}" xmlns:pic="{PIC_NS}">
          <w:body><w:p><w:r><w:drawing><a:graphic><a:graphicData>
            <pic:pic><pic:blipFill><a:blip a14:useLocalDpi="0"/>
            </pic:blipFill></pic:pic>
          </a:graphicData></a:graphic></w:drawing></w:r></w:p></w:body>
        </w:document>
        """
    )

    payload = _serialize(document)

    assert b"<a:graphic>" in payload
    assert b"<pic:pic>" in payload
    assert b"a14:useLocalDpi=" in payload
    assert b"<ns" not in payload


def test_detects_paragraph_in_vertically_centered_table_cell() -> None:
    document = ET.fromstring(
        f"""
        <w:document xmlns:w="{W_NS}"><w:body><w:tbl><w:tr><w:tc>
          <w:tcPr><w:vAlign w:val="center"/></w:tcPr>
          <w:p><w:r><w:t>value</w:t></w:r></w:p>
        </w:tc></w:tr></w:tbl></w:body></w:document>
        """
    )
    paragraph = document.find(f".//{{{W_NS}}}p")

    assert paragraph is not None
    assert _paragraph_is_in_vertically_centered_table_cell(document, paragraph)
