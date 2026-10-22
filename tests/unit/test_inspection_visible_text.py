from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from docfit.template.source_entries import build_canonical_source_inventory
from docfit.tools.inspection import inspect_document
from docfit.tools.runtime import JsonObject
from docfit.tools.word_xml import visible_word_text

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W16SE_NS = "http://schemas.microsoft.com/office/word/2015/wordml/symex"


class _OfficeMissingAlternateContentText:
    @staticmethod
    def evidence() -> JsonObject:
        return {"name": "officecli", "version": "fixture"}

    @staticmethod
    def query(document: Path, selector: str) -> tuple[JsonObject, ...]:
        assert document.is_file()
        assert selector == "paragraph"
        paragraph = "/body/p[@paraId=7549EC38]"
        return (
            {"path": paragraph, "type": "paragraph", "text": "欢迎提交pull request"},
            {"path": f"{paragraph}/r[1]", "type": "run", "text": "欢迎提交"},
            {"path": f"{paragraph}/r[2]", "type": "run", "text": "pull"},
            {"path": f"{paragraph}/r[3]", "type": "run", "text": " "},
            {"path": f"{paragraph}/r[4]", "type": "run", "text": "request"},
            {"path": f"{paragraph}/r[5]", "type": "run", "text": ""},
        )


def _write_docx_with_symex_fallback(path: Path) -> None:
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}" xmlns:mc="{MC_NS}"
                xmlns:w16se="{W16SE_NS}" mc:Ignorable="w14 w16se">
      <w:body>
        <w:p w14:paraId="7549EC38">
          <w:r><w:t>欢迎提交</w:t></w:r>
          <w:r><w:t>pull</w:t></w:r>
          <w:r><w:t xml:space="preserve"> </w:t></w:r>
          <w:r><w:t>request</w:t></w:r>
          <w:r>
            <mc:AlternateContent>
              <mc:Choice Requires="w16se">
                <w16se:symEx w16se:font="Segoe UI Emoji" w16se:char="1F60A"/>
              </mc:Choice>
              <mc:Fallback><w:t>😊</w:t></mc:Fallback>
            </mc:AlternateContent>
          </w:r>
        </w:p>
      </w:body>
    </w:document>
    """
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)


def test_inspection_recovers_markup_compatibility_visible_text(
    tmp_path: Path,
) -> None:
    document = tmp_path / "symex.docx"
    _write_docx_with_symex_fallback(document)

    inspection = inspect_document(
        document,
        _OfficeMissingAlternateContentText(),  # type: ignore[arg-type]
        selector="paragraph",
    )
    objects = [item.public() for item in inspection.objects]

    assert objects[0]["text"] == "欢迎提交pull request😊"
    assert objects[-1]["text"] == "😊"

    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=inspection.document_sha256,
        inspected_objects=objects,
    )
    assert len(canonical.source_entries) == 1
    assert canonical.source_entries[0].text == "欢迎提交pull request😊"
    assert canonical.source_entries[0].provenance[-1].text_span == (16, 17)


def test_shared_visible_text_recovers_legacy_word_symbol() -> None:
    run = ET.fromstring(
        f'<w:r xmlns:w="{W_NS}"><w:sym w:font="Wingdings" w:char="F06F"/></w:r>'
    )

    assert visible_word_text(run) == "\uf06f"
