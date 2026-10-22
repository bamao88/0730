from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.tools.package import validate_docx_package
from docfit.tools.runtime import ToolFailure
from docfit.tools.word_xml import serialize_word_xml

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def test_serialize_word_xml_preserves_prefix_referenced_by_mc_choice() -> None:
    root = ET.fromstring(
        f'<w:document xmlns:w="{W_NS}" xmlns:mc="{MC_NS}" '
        f'xmlns:wps="{WPS_NS}">'
        '<mc:AlternateContent><mc:Choice Requires="wps">'
        '<wps:wsp />'
        '</mc:Choice></mc:AlternateContent>'
        '</w:document>'
    )

    payload = serialize_word_xml(root)

    assert f'xmlns:wps="{WPS_NS}"'.encode() in payload
    assert b'<wps:wsp' in payload
    assert b'Requires="wps"' in payload
    assert b'xmlns:ns' not in payload


def test_serialize_word_xml_declares_ignorable_prefix_without_live_elements() -> None:
    root = ET.fromstring(
        f'<w:document xmlns:w="{W_NS}" xmlns:mc="{MC_NS}" '
        f'xmlns:wps="{WPS_NS}" mc:Ignorable="wps">'
        '<w:body />'
        '</w:document>'
    )

    payload = serialize_word_xml(root)

    assert f'xmlns:wps="{WPS_NS}"'.encode() in payload
    assert b'mc:Ignorable="wps"' in payload


def _write_package(path: Path, document_xml: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/document.xml", document_xml)


def test_package_validation_rejects_an_undeclared_mc_prefix(tmp_path: Path) -> None:
    document = tmp_path / "invalid-prefix.docx"
    _write_package(
        document,
        (
            f'<w:document xmlns:w="{W_NS}" xmlns:mc="{MC_NS}">'
            '<mc:AlternateContent><mc:Choice Requires="wps" />'
            '</mc:AlternateContent></w:document>'
        ),
    )

    with pytest.raises(ToolFailure) as caught:
        validate_docx_package(document)

    assert caught.value.code == "invalid_word_xml_contract"


def test_package_validation_rejects_a_table_cell_without_content(tmp_path: Path) -> None:
    document = tmp_path / "empty-cell.docx"
    _write_package(
        document,
        (
            f'<w:document xmlns:w="{W_NS}"><w:body><w:tbl><w:tr>'
            '<w:tc><w:tcPr /></w:tc>'
            '</w:tr></w:tbl></w:body></w:document>'
        ),
    )

    with pytest.raises(ToolFailure) as caught:
        validate_docx_package(document)

    assert caught.value.code == "invalid_word_xml_contract"
