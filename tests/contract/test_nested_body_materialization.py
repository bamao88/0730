"""Cell-local body text interfaces must not replace or suppress the enclosing table."""

from xml.etree import ElementTree as ET

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.tools.runtime import ToolFailure
from tests.contract.test_template_materialization_readiness import _registry
from tests.contract.test_template_materialization_runtime import (
    W,
    _body_structure_judgment,
    _fixed_judgment,
    _judgment,
    _read_document,
    _write_body_registry,
    _write_docx_from_paragraph_xml,
    materialize_template_from_semantics,
)


def test_body_text_interfaces_stay_in_cells_and_other_cell_cleanup_executes(tmp_path):
    registry_path = tmp_path / "input/registry.yaml"
    _write_body_registry(registry_path)
    source, output = tmp_path / "input/template.docx", tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            "<w:p><w:r><w:t>Top</w:t></w:r></w:p>",
            '<w:tbl><w:tblPr><w:tblW w:w="8000" w:type="dxa"/></w:tblPr>'
            '<w:tblGrid><w:gridCol w:w="4000"/><w:gridCol w:w="4000"/></w:tblGrid>'
            '<w:tr><w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/></w:tcPr>'
            "<w:p><w:pPr><w:keepNext/></w:pPr><w:r><w:t>Label: Heading</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Body</w:t></w:r></w:p></w:tc>"
            '<w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/></w:tcPr>'
            "<w:p><w:r><w:t>Other</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Style note</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Keep</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
        ],
    )
    rows = [
        ("Top", "/body/p[1]", "body.heading.outline1"),
        ("Label: Heading", "/body/tbl[1]/tr[1]/tc[1]/p[1]", "body.heading.outline2"),
        ("Body", "/body/tbl[1]/tr[1]/tc[1]/p[2]", "body.paragraph"),
        ("Other", "/body/tbl[1]/tr[1]/tc[2]/p[1]", "body.paragraph"),
        ("Style note", "/body/tbl[1]/tr[1]/tc[2]/p[2]", None),
        ("Keep", "/body/tbl[1]/tr[1]/tc[2]/p[3]", None),
    ]
    inventory = {
        "objects": [
            {"object_id": f"obj-{i}", "type": "paragraph", "locator": loc}
            for i, (_, loc, _) in enumerate(rows)
        ],
        "reading_blocks": [
            {"block_id": f"b{i}", "covered_object_ids": [f"obj-{i}"], "text": text, "order": i}
            for i, (text, _, _) in enumerate(rows)
        ],
    }
    judgments = [
        _body_structure_judgment([(f"b{i}", text, field)])
        for i, (text, _, field) in enumerate(rows)
        if field is not None
    ]
    judgments[1] = _judgment(
        "b1",
        [
            {"text": "Label: ", "role": "fixed_label"},
            {"text": "Heading", "role": "body_structure", "field_id": "body.heading.outline2"},
        ],
    )
    judgments.extend(
        [
            _judgment(
                "b4",
                [{"text": "Style", "role": "style_only"}, {"text": " note", "role": "cleanup"}],
            ),
            _fixed_judgment("b5", "Keep"),
        ]
    )
    original = _read_document(source)
    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review={"semantic_judgments": judgments},
    )
    actual = _read_document(output)
    table = actual.find(f".//{W}tbl")
    old_table = original.find(f".//{W}tbl")
    for tag in ("tblPr", "tblGrid"):
        assert ET.tostring(table.find(W + tag)) == ET.tostring(old_table.find(W + tag))
    cells = table.findall(f"{W}tr/{W}tc")
    old_cells = old_table.findall(f"{W}tr/{W}tc")
    assert len(cells) == 2
    for cell, old_cell in zip(cells, old_cells, strict=True):
        assert ET.tostring(cell.find(W + "tcPr")) == ET.tostring(old_cell.find(W + "tcPr"))
        assert len(cell.findall(W + "p")) == len(old_cell.findall(W + "p"))
        assert list(cell)[-1].tag == W + "p"

    def aliases(node):
        return [a.get(W + "val") for a in node.iter(W + "alias")]

    assert "".join(t.text or "" for t in cells[0].find(W + "p").iter(W + "t")).startswith("Label: ")
    assert aliases(cells[0]) == ["body.heading.outline2", "body.paragraph"]
    assert aliases(cells[1]) == ["body.paragraph"]
    assert cells[0].find(f"{W}p/{W}pPr/{W}keepNext") is not None
    assert "".join(t.text or "" for t in cells[1].findall(W + "p")[1].iter(W + "t")) == ""
    assert ET.tostring(cells[1].findall(W + "p")[2]) == ET.tostring(
        old_cells[1].findall(W + "p")[2]
    )
    members = [m for operation in result["operations"] for m in operation.get("members", [])]
    assert len(members) == 4
    assert len({m["slot_ref"] for m in members}) == 4
    assert all(m["word_fragments"] for m in members)


def test_parent_table_and_cell_text_interfaces_conflict_before_write(tmp_path):
    registry = _registry(tmp_path / "registry.yaml")
    source, output = tmp_path / "input/template.docx", tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Text</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
        ],
    )
    inventory = {
        "objects": [
            {"object_id": "table", "type": "table", "locator": "/body/tbl[1]"},
            {
                "object_id": "cell-text",
                "type": "paragraph",
                "locator": "/body/tbl[1]/tr[1]/tc[1]/p[1]",
            },
        ],
        "reading_blocks": [
            {"block_id": name, "covered_object_ids": [name], "text": "Text"}
            for name in ("table", "cell-text")
        ],
    }
    review = {
        "semantic_judgments": [
            _body_structure_judgment([("table", "Text", "body.table")]),
            _body_structure_judgment([("cell-text", "Text", "body.paragraph")]),
        ]
    }
    with pytest.raises(ToolFailure) as error:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert error.value.code == "template_materialization_execution_unsupported"
    assert "materialization_body_structure_carrier_conflict" in str(error.value)
    assert not output.exists()
