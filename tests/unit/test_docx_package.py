from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.tools.package import normalize_docx_custom_properties

VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"


def test_normalize_docx_custom_properties_repairs_namespace_less_value_nodes(
    tmp_path: Path,
) -> None:
    document = tmp_path / "document.docx"
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/document.xml", "<w:document xmlns:w='w'/>")
        archive.writestr(
            "docProps/custom.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<op:Properties xmlns:op="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties">
  <op:property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="CWM">
    <lpwstr>value</lpwstr>
  </op:property>
</op:Properties>
""",
        )

    warnings = normalize_docx_custom_properties(document)

    assert warnings == ("normalized_custom_property_value_namespaces",)
    with zipfile.ZipFile(document) as archive:
        root = ET.fromstring(archive.read("docProps/custom.xml"))
    assert root.find(f".//{{{VT_NS}}}lpwstr") is not None
    assert root.find(".//lpwstr") is None
