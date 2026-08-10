from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from docfit.styles import (
    EffectiveStyleResolver,
    StyleContractSet,
    StyleContractValidator,
    style_contract_digest,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_docx(path: Path) -> None:
    styles = f'''<w:styles xmlns:w="{W_NS}">
      <w:docDefaults>
        <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>
          <w:sz w:val="22"/><w:color w:val="000000"/></w:rPr></w:rPrDefault>
        <w:pPrDefault><w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrDefault>
      </w:docDefaults>
      <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
        <w:name w:val="Normal"/><w:pPr><w:jc w:val="left"/></w:pPr><w:rPr><w:b/></w:rPr>
      </w:style>
      <w:style w:type="paragraph" w:styleId="HeadingStable">
        <w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/>
          <w:spacing w:before="240"/><w:pageBreakBefore/></w:pPr>
        <w:rPr><w:rFonts w:eastAsia="黑体"/><w:sz w:val="32"/><w:b/><w:i/></w:rPr>
      </w:style>
      <w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"/>
      <w:style w:type="character" w:styleId="Emphasis">
        <w:basedOn w:val="DefaultParagraphFont"/><w:rPr><w:b/><w:i/></w:rPr>
      </w:style>
    </w:styles>'''
    document = f'''<w:document xmlns:w="{W_NS}">
      <w:body>
        <w:p><w:r><w:t>Default paragraph</w:t></w:r></w:p>
        <w:sdt><w:sdtPr><w:tag w:val="docfit.title"/></w:sdtPr><w:sdtContent>
          <w:p><w:pPr><w:pStyle w:val="HeadingStable"/><w:jc w:val="right"/>
            <w:spacing w:after="360"/></w:pPr>
            <w:r><w:rPr><w:rStyle w:val="Emphasis"/><w:rFonts w:ascii="Arial"/>
              <w:b w:val="0"/><w:color w:val="FF0000"/></w:rPr><w:t>Stable title</w:t></w:r>
          </w:p>
        </w:sdtContent></w:sdt>
      </w:body>
    </w:document>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)


def _contract(properties: dict[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "style_contract_id": "style.title",
        "application_scope": "paragraph",
        "owned_properties": list(properties),
        "effective_properties": properties,
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": [],
    }
    value["contract_digest"] = style_contract_digest(value)
    return value


def _contracts(style: dict[str, Any]) -> StyleContractSet:
    return StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": "a" * 64,
            "styles": [style],
        }
    )


def test_resolver_applies_defaults_inheritance_toggles_and_direct_formatting(
    tmp_path: Path,
) -> None:
    document = tmp_path / "styles.docx"
    _write_docx(document)
    resolver = EffectiveStyleResolver(document)

    default = resolver.resolve("/body/p[1]")
    assert default.properties["run.font_ascii"] == "Calibri"
    assert default.properties["run.font_size_pt"] == 11.0
    assert default.properties["run.bold"] is True
    assert default.properties["paragraph.alignment"] == "left"
    assert default.properties["paragraph.space_after_pt"] == 6.0

    title = resolver.resolve(
        {"type": "content_control_tag", "value": "docfit.title", "part": "word/document.xml"}
    )
    assert title.properties["run.font_ascii"] == "Arial"
    assert title.properties["run.font_hansi"] == "Calibri"
    assert title.properties["run.font_east_asia"] == "黑体"
    assert title.properties["run.font_size_pt"] == 16.0
    assert title.properties["run.bold"] is False
    assert title.properties["run.italic"] is False
    assert title.properties["run.color"] == "FF0000"
    assert title.properties["paragraph.alignment"] == "right"
    assert title.properties["paragraph.space_before_pt"] == 12.0
    assert title.properties["paragraph.space_after_pt"] == 18.0
    assert title.properties["paragraph.page_break_before"] is True
    assert title.coverage == frozenset(title.properties)
    assert [item.action for item in title.provenance["run.bold"]] == [
        "toggle",
        "toggle",
        "toggle",
        "set",
    ]


def test_validator_classifies_passed_failed_and_unresolved_occurrences(tmp_path: Path) -> None:
    document = tmp_path / "styles.docx"
    _write_docx(document)
    expected = {
        "run.font_ascii": "Arial",
        "run.font_size_pt": 16.0,
        "run.bold": False,
        "run.color": "FF0000",
        "paragraph.alignment": "right",
        "paragraph.page_break_before": True,
    }
    style = _contract(expected)
    validator = StyleContractValidator(_contracts(style))
    style_ref = {
        "style_contract_id": style["style_contract_id"],
        "contract_digest": style["contract_digest"],
    }

    report = validator.validate(
        document,
        {
            "occurrences": [
                {
                    "occurrence_id": "title-good",
                    "locator": {"type": "content_control_tag", "value": "docfit.title"},
                    "style_contract_ref": style_ref,
                },
                {
                    "occurrence_id": "title-wrong",
                    "locator": "/body/p[1]",
                    "style_contract_ref": style_ref,
                },
                {
                    "occurrence_id": "title-missing",
                    "locator": "/body/p[99]",
                    "style_contract_ref": style_ref,
                },
            ]
        },
    )

    assert report.status == "failed"
    assert [item.occurrence_id for item in report.passed] == ["title-good"]
    assert [item.occurrence_id for item in report.failed] == ["title-wrong"]
    assert [item.occurrence_id for item in report.unresolved] == ["title-missing"]
    assert {item.property_path for item in report.failed[0].differences} >= {
        "run.font_ascii",
        "run.font_size_pt",
        "paragraph.alignment",
    }
    assert report.as_dict()["counts"] == {"passed": 1, "failed": 1, "unresolved": 1}


def test_run_locator_selects_the_requested_run(tmp_path: Path) -> None:
    document = tmp_path / "runs.docx"
    xml = f'''<w:document xmlns:w="{W_NS}"><w:body><w:p>
      <w:r><w:rPr><w:color w:val="FF0000"/></w:rPr><w:t>Red</w:t></w:r>
      <w:r><w:rPr><w:color w:val="0000FF"/></w:rPr><w:t>Blue</w:t></w:r>
    </w:p></w:body></w:document>'''
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/document.xml", xml)

    resolver = EffectiveStyleResolver(document)

    assert resolver.resolve("/body/p[1]/r[1]").properties["run.color"] == "FF0000"
    assert resolver.resolve("/body/p[1]/r[2]").properties["run.color"] == "0000FF"
