from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.template.object_mutation import (
    ObjectMutation,
    StructureMember,
    mutate_objects,
    resolve_word_locator,
)
from docfit.tools.inspection import InspectedObject
from docfit.tools.runtime import ToolFailure

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W16SDTFL_NS = "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
W = f"{{{W_NS}}}"
SLOT_REF = (
    "reading_block_id=u-cover:block-0001;part_index=0;field_id=thesis.title.zh"
)


def _write_docx(path: Path, body_xml: str) -> None:
    document = f'<w:document xmlns:w="{W_NS}"><w:body>{body_xml}</w:body></w:document>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)


def _write_document_xml(path: Path, document_xml: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


def _selected(
    *,
    locator: str,
    kind: str,
    text: str = "School value",
) -> InspectedObject:
    return InspectedObject(
        locator=locator,
        kind=kind,
        text=text,
        style=None,
        format={},
        object_ref={
            "document_sha256": "a" * 64,
            "object_id": "obj-existing-control",
            "expected_fingerprint": "b" * 64,
        },
    )


def _slot_mutation(selected: InspectedObject) -> ObjectMutation:
    return ObjectMutation(
        selected=selected,
        action="materialize_slot",
        field_id="thesis.title.zh",
        slot_ref=SLOT_REF,
        content_type="text",
        placeholder_text="Title",
    )


def test_resolve_word_locator_flattens_hyperlink_runs_in_paragraph_order() -> None:
    document = ET.fromstring(
        f"""
        <w:document xmlns:w="{W_NS}">
          <w:body>
            <w:p>
              <w:r><w:t>direct-1</w:t></w:r>
              <w:r><w:t>direct-2</w:t></w:r>
              <w:r><w:t>direct-3</w:t></w:r>
              <w:hyperlink>
                <w:r><w:t>linked-4</w:t></w:r>
                <w:r><w:t>linked-5</w:t></w:r>
              </w:hyperlink>
            </w:p>
          </w:body>
        </w:document>
        """
    )

    fourth = resolve_word_locator(document, "/body/p[1]/r[4]")
    fifth = resolve_word_locator(document, "/body/p[1]/r[5]")

    assert fourth is not None
    assert fourth.find(f"{W}t").text == "linked-4"
    assert fifth is not None
    assert fifth.find(f"{W}t").text == "linked-5"
    assert resolve_word_locator(document, "/body/p[1]/r[6]") is None


def test_materialize_slot_adopts_existing_sdt_without_nested_control(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _write_docx(
        source,
        """
        <w:sdt>
          <w:sdtPr>
            <w:id w:val="1001"/>
            <w:alias w:val="SchoolTitle"/>
            <w:tag w:val="school.title"/>
          </w:sdtPr>
          <w:sdtContent>
            <w:p><w:r><w:t>School value</w:t></w:r></w:p>
          </w:sdtContent>
        </w:sdt>
        """,
    )

    result = mutate_objects(
        source,
        output,
        mutations=[
            _slot_mutation(
                _selected(locator="/body/sdt[@sdtId=1001]", kind="sdt")
            )
        ],
    )

    assert output.is_file()
    assert result["relocated_boundaries"] == []
    assert "migrated_boundaries" not in result
    with zipfile.ZipFile(output) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    controls = list(document.iter(f"{W}sdt"))
    assert len(controls) == 1
    control = controls[0]
    assert control.find(f"{W}sdtPr/{W}alias").get(f"{W}val") == "thesis.title.zh"
    assert control.find(f"{W}sdtPr/{W}tag").get(f"{W}val") == SLOT_REF
    assert "".join(node.text or "" for node in control.iter(f"{W}t")) == "School value"


def test_materialize_slot_fails_closed_for_paragraph_containing_existing_sdt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _write_docx(
        source,
        """
        <w:p>
          <w:r><w:t>Title: </w:t></w:r>
          <w:sdt>
            <w:sdtPr><w:id w:val="1001"/><w:tag w:val="school.title"/></w:sdtPr>
            <w:sdtContent><w:r><w:t>School value</w:t></w:r></w:sdtContent>
          </w:sdt>
        </w:p>
        """,
    )

    with pytest.raises(ToolFailure) as failure:
        mutate_objects(
            source,
            output,
            mutations=[_slot_mutation(_selected(locator="/body/p[1]", kind="paragraph"))],
        )

    assert failure.value.code == "existing_content_control_boundary"
    assert "target_affordance" in " ".join(failure.value.suggested_actions)


def test_materialize_structure_parent_control_has_no_field_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    member_slot_ref = (
        "reading_block_id=u-body:block-0001;part_index=0;"
        "field_id=body.heading.outline1"
    )
    _write_docx(
        source,
        "<w:p><w:r><w:t>一级标题</w:t></w:r></w:p>",
    )

    selected = _selected(locator="/body/p[1]", kind="paragraph", text="一级标题")
    mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(
                selected=selected,
                action="materialize_structure",
                structure_ref="body.chapters",
                content_type="section",
                structure_members=(
                    StructureMember(
                        selected=selected,
                        field_id="body.heading.outline1",
                        slot_ref=member_slot_ref,
                        content_type="text",
                        placeholder_text="一级标题",
                    ),
                ),
            )
        ],
    )

    with zipfile.ZipFile(output) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    body = document.find(f"{W}body")
    assert body is not None
    outer_controls = [child for child in list(body) if child.tag == f"{W}sdt"]
    assert len(outer_controls) == 1

    outer = outer_controls[0]
    outer_properties = outer.find(f"{W}sdtPr")
    assert outer_properties is not None
    assert outer_properties.find(f"{W}alias") is None
    assert outer_properties.find(f"{W}tag") is None

    member_controls = [
        control for control in outer.iter(f"{W}sdt") if control is not outer
    ]
    assert len(member_controls) == 1
    member_properties = member_controls[0].find(f"{W}sdtPr")
    assert member_properties is not None
    assert member_properties.find(f"{W}alias").get(f"{W}val") == "body.heading.outline1"
    assert member_properties.find(f"{W}tag").get(f"{W}val") == member_slot_ref


def test_mutate_objects_preserves_ignorable_w16sdtfl_namespace(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _write_document_xml(
        source,
        (
            f'<w:document xmlns:w="{W_NS}" xmlns:mc="{MC_NS}" '
            f'xmlns:w16sdtfl="{W16SDTFL_NS}" mc:Ignorable="w16sdtfl">'
            "<w:body><w:p><w:r><w:t>Instruction</w:t></w:r></w:p></w:body>"
            "</w:document>"
        ),
    )

    mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(
                selected=_selected(locator="/body/p[1]", kind="paragraph"),
                action="clear_content",
            )
        ],
    )

    with zipfile.ZipFile(output) as archive:
        document_xml = archive.read("word/document.xml")
    assert b'mc:Ignorable="w16sdtfl"' in document_xml
    assert f'xmlns:w16sdtfl="{W16SDTFL_NS}"'.encode() in document_xml


def test_mutate_objects_preserves_standard_drawingml_prefixes(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    _write_document_xml(
        source,
        (
            f'<w:document xmlns:w="{W_NS}" xmlns:a="{A_NS}" '
            f'xmlns:a14="{A14_NS}" xmlns:pic="{PIC_NS}">'
            "<w:body><w:p><w:r><w:drawing><a:graphic><a:graphicData>"
            "<pic:pic><pic:blipFill><a:blip a14:useLocalDpi=\"0\"/>"
            "</pic:blipFill></pic:pic></a:graphicData></a:graphic>"
            "</w:drawing></w:r></w:p></w:body></w:document>"
        ),
    )

    mutate_objects(
        source,
        output,
        mutations=[
            ObjectMutation(
                selected=_selected(locator="/body/p[1]", kind="paragraph"),
                action="normalize_effective_format",
            )
        ],
    )

    with zipfile.ZipFile(output) as archive:
        document_xml = archive.read("word/document.xml")
    assert b"<a:graphic>" in document_xml
    assert b"<pic:pic>" in document_xml
    assert b"a14:useLocalDpi=" in document_xml
    assert b"<ns" not in document_xml
