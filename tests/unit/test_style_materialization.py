from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest

from docfit.styles import StyleContractSet, StyleContractValidator, style_contract_digest
from docfit.styles.materialization import materialize_style_contracts

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W = f"{{{W_NS}}}"


def _write_occurrences(path: Path, count: int) -> None:
    paragraphs = "".join(
        f'''<w:p w14:paraId="{index:08X}">
          <w:pPr><w:jc w:val="right"/><w:keepNext/>
            <w:tabs><w:tab w:val="right" w:leader="dot" w:pos="720"/></w:tabs>
          </w:pPr>
          <w:r><w:rPr><w:rFonts w:ascii="Courier New"/>
            <w:sz w:val="18"/><w:b/><w:i/><w:color w:val="FF0000"/>
            <w:caps/></w:rPr><w:t>Occurrence {index}</w:t></w:r>
        </w:p>'''
        for index in range(1, count + 1)
    )
    document = f'''<w:document xmlns:w="{W_NS}" xmlns:w14="{W14_NS}">
      <w:body>{paragraphs}<w:sectPr/></w:body>
    </w:document>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def _style() -> dict[str, Any]:
    properties = {
        "paragraph.alignment": "center",
        "paragraph.first_line_indent_chars": 2.0,
        "paragraph.left_indent_chars": 0.0,
        "paragraph.right_indent_chars": 0.0,
        "paragraph.hanging_indent_chars": 0.0,
        "paragraph.space_before_pt": 12.0,
        "paragraph.space_after_pt": 6.0,
        "paragraph.keep_with_next": False,
        "paragraph.keep_together": True,
        "paragraph.widow_control": False,
        "paragraph.outline_level": 9,
        "paragraph.numbering": None,
        "paragraph.tab_stops": None,
        "run.font_ascii": "Times New Roman",
        "run.font_hansi": "Times New Roman",
        "run.font_east_asia": "宋体",
        "run.font_size_pt": 12.0,
        "run.bold": False,
        "run.italic": False,
        "run.color": "000000",
        "run.underline": None,
        "run.strikethrough": False,
        "run.vertical_position": "baseline",
        "run.character_spacing_pt": 0.0,
    }
    value: dict[str, Any] = {
        "style_contract_id": "style.body.paragraph",
        "application_scope": "paragraph",
        "owned_properties": sorted(properties),
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


@pytest.mark.parametrize("count", [1, 10, 100])
def test_same_contract_is_stable_for_every_repeated_occurrence(
    tmp_path: Path, count: int
) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _write_occurrences(source, count)
    style = _style()
    contracts = _contracts(style)
    style_ref = {
        "style_contract_id": style["style_contract_id"],
        "contract_digest": style["contract_digest"],
    }
    manifest = {
        "occurrences": [
            {
                "occurrence_id": f"body-{index}",
                "locator": f"/body/p[@paraId={index:08X}]",
                "style_contract_ref": style_ref,
            }
            for index in range(1, count + 1)
        ]
    }

    result = materialize_style_contracts(
        input_docx=source,
        output_docx=output,
        contracts=contracts,
        occurrence_manifest=manifest,
    )
    validation = StyleContractValidator(contracts).validate(output, manifest)

    assert result["occurrence_count"] == count
    assert validation.status == "passed"
    assert len(validation.passed) == count
    with zipfile.ZipFile(output) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    assert len(document.findall(f".//{W}caps")) == count


def test_materialization_rejects_two_contracts_for_one_occurrence(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _write_occurrences(source, 1)
    style = _style()
    contracts = _contracts(style)
    style_ref = {
        "style_contract_id": style["style_contract_id"],
        "contract_digest": style["contract_digest"],
    }
    manifest = {
        "occurrences": [
            {
                "occurrence_id": "first",
                "locator": "/body/p[@paraId=00000001]",
                "style_contract_ref": style_ref,
            },
            {
                "occurrence_id": "second",
                "locator": "/body/p[@paraId=00000001]",
                "style_contract_ref": style_ref,
            },
        ]
    }

    with pytest.raises(Exception, match="More than one Style Contract"):
        materialize_style_contracts(
            input_docx=source,
            output_docx=output,
            contracts=contracts,
            occurrence_manifest=manifest,
        )
