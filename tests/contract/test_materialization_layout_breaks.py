"""Real mutation paths must not erase layout nodes outside accepted text spans."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.tools.runtime import ToolFailure, sha256_file
from docfit.tools.word_xml import visible_word_text
from tests.contract.test_template_materialization_runtime import (
    W,
    _inventory_with_paragraph_objects,
    _judgment,
    _part,
    _read_document,
    _write_body_registry,
    _write_docx_from_paragraph_xml,
    _write_registry,
    materialize_template_from_semantics,
)


def _materialize(root: Path, role: str, content: str):
    registry_path = root / "input/field-registry.yaml"
    (_write_body_registry if role == "body_structure" else _write_registry)(registry_path)
    source, output = root / "input/source.docx", root / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            '<w:p><w:pPr><w:keepNext/><w:spacing w:after="120"/></w:pPr>' + content + "</w:p>",
        ],
    )
    field = "body.paragraph" if role == "body_structure" else "thesis.title.en"
    inventory = _inventory_with_paragraph_objects(
        [
            {"block_id": "sample", "covered_object_ids": ["obj-1"], "text": "Value(note)"},
        ]
    )
    parts = (
        [_part("cleanup", "Value")]
        if role == "style_only"
        else [
            _part(role, "Value", field_id=field),
        ]
    )
    parts.append(_part("style_only", "(note)"))
    original_hash = sha256_file(source)
    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review={"semantic_judgments": [_judgment("sample", parts)]},
    )
    assert sha256_file(source) == original_hash
    return source, output, result


@pytest.mark.parametrize("role", ["fill_slot", "body_structure", "style_only"])
@pytest.mark.parametrize("break_kind", ["page", "column", "textWrapping"])
def test_text_rewrite_preserves_leading_and_trailing_layout_breaks(tmp_path, role, break_kind):
    source, output, _ = _materialize(
        tmp_path,
        role,
        f'<w:r><w:rPr><w:b/></w:rPr><w:br w:type="{break_kind}"/></w:r>'
        f'<w:r><w:t>Value(note)</w:t><w:br w:type="{break_kind}"/></w:r>',
    )
    before, after = _read_document(source), _read_document(output)
    paragraph = after.find(f".//{W}p")
    assert paragraph is not None
    breaks = list(paragraph.iter(W + "br"))
    assert [b.get(W + "type") for b in breaks] == [break_kind, break_kind]
    assert paragraph[1].find(W + "br") is not None
    assert paragraph[-1].find(W + "br") is not None
    assert paragraph[1].find(f"{W}rPr/{W}b") is not None
    for tag in ("keepNext", "spacing"):
        assert ET.tostring(paragraph.find(f"{W}pPr/{W}{tag}")) == ET.tostring(
            before.find(f"{W}body/{W}p/{W}pPr/{W}{tag}")
        )
    assert "(note)" not in visible_word_text(paragraph)


@pytest.mark.parametrize("role", ["fill_slot", "body_structure", "style_only"])
def test_internal_break_without_output_boundary_mapping_stops_before_output(tmp_path, role):
    with pytest.raises(ToolFailure) as caught:
        _materialize(
            tmp_path,
            role,
            '<w:r><w:t>Val</w:t><w:br w:type="page"/><w:t>ue(note)</w:t></w:r>',
        )
    assert caught.value.origin == "tool"
    assert caught.value.code == "materialization_layout_break_mapping_unsupported"
    assert not (tmp_path / "work/candidate.docx").exists()


def test_empty_section_break_carrier_cannot_guess_new_body_slot_side(tmp_path):
    registry_path = tmp_path / "input/registry.yaml"
    _write_body_registry(registry_path)
    source, output = tmp_path / "input/source.docx", tmp_path / "work/candidate.docx"
    _write_docx_from_paragraph_xml(
        source,
        [
            '<w:p><w:pPr><w:sectPr><w:pgNumType w:start="1"/></w:sectPr></w:pPr>'
            '<w:r><w:br w:type="page"/></w:r></w:p>',
        ],
    )
    from docfit.template.source_spans import resolve_semantic_judgments
    from docfit.tools.runtime import sha256_json
    from tests.contract.test_materialization_exact_span_execution import _accepted_inputs
    from tests.support.source_identity import review_binding, source_partition

    registry = FieldRegistrySnapshot.load(registry_path)
    inventory, review = _accepted_inputs(source=source, registry=registry, paragraph_index=1)
    entry = inventory["source_entries"][0]
    entry.update(text="", entry_type="structural")
    entry["provenance"][0].pop("text_span")
    entry["provenance"][0]["extent"] = {"kind": "whole_entry"}
    inventory["objects"][0]["text"] = ""
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    judgment = {
        "source_entry_id": entry["source_entry_id"],
        "parts": [_part("body_structure", "", field_id="body.paragraph")],
    }
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=[judgment])
    judgment["resolved_spans"] = resolved
    review.update(
        **review_binding(inventory),
        semantic_judgments=[judgment],
        semantic_judgments_sha256=sha256_json([judgment]),
        resolved_spans=resolved,
    )
    before = sha256_file(source)
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert caught.value.code == "materialization_layout_break_mapping_unsupported"
    assert caught.value.origin == "tool"
    assert sha256_file(source) == before
    assert not output.exists()
