"""Constructed DOCX contract tests; not real-school or Agent-loop evidence."""

from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.contract.test_template_materialization_readiness import _registry
from tests.contract.test_template_materialization_runtime import (
    W,
    _read_document,
    _write_docx_from_paragraph_xml,
)
from tests.support.source_identity import review_binding, source_partition

V = "{urn:schemas-microsoft-com:vml}"


def _case(tmp_path: Path, *, keep_text: bool = True, partial: bool = False):
    source = tmp_path / "source.docx"
    note = "same text"
    visible = note if keep_text else ""
    shape = (
        '<v:shape xmlns:v="urn:schemas-microsoft-com:vml" id="{}">'
        f'<v:textbox><w:txbxContent><w:p><w:r><w:t>{note}</w:t></w:r></w:p>'
        '</w:txbxContent></v:textbox></v:shape>'
    )
    _write_docx_from_paragraph_xml(source, [
        '<w:p><w:pPr><w:spacing w:after="120"/><w:sectPr/></w:pPr>'
        f'<w:r><w:t>{visible}</w:t></w:r><w:r><w:pict>'
        + shape.format("delete") + shape.format("keep") + '</w:pict></w:r></w:p>',
    ])
    source_hash = sha256_file(source)
    registry = _registry(tmp_path / "registry.yaml")
    vocabulary = registry.pre_input_vocabulary()
    entries, objects, judgments = [], [], []
    rows = [
        ("paragraph", "/body/p[1]", "", "style_only"),
        ("text", "/body/p[1]/r[1]", visible, "fixed_label"),
        ("shape", "/body/p[1]/r[2]/pict[1]/shape[1]", note[:4] if partial else note, "cleanup"),
        ("shape", "/body/p[1]/r[2]/pict[1]/shape[2]", note, "fixed_label"),
    ]
    for index, (kind, locator, text, role) in enumerate(rows):
        entry_id, object_id = f"source-entry-{index}", f"obj-{index}"
        fingerprint = sha256_json({"locator": locator, "text": text})
        reference = {"object_id": object_id, "document_sha256": source_hash,
                     "expected_fingerprint": fingerprint}
        objects.append({"object_id": object_id, "type": kind, "locator": locator,
                        "object_ref": reference, "source_entry_id": entry_id})
        provenance = {"locator": locator, "object_id": object_id,
                      "object_ref": reference, "fingerprint": fingerprint}
        if text:
            provenance["text_span"] = [0, len(text)]
        else:
            provenance["extent"] = {"kind": "whole_entry"}
        entries.append({"source_entry_id": entry_id, "entry_type": "text",
                        "text": text, "source_order": {"block": index + 1, "inline": 0},
                        "provenance": [provenance]})
        judgments.append({"source_entry_id": entry_id, "parts": [{"text": text, "role": role}]})
    inventory = {"document_sha256": source_hash, "source_entries": entries, "objects": objects,
                 "field_id_vocabulary": vocabulary, "field_vocabulary_digest": vocabulary["digest"]}
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [{**j, "resolved_spans": [s for s in resolved if s["judgment_index"] == i]}
                for i, j in enumerate(judgments)]
    review = {**review_binding(inventory), "document_sha256": source_hash,
              "field_id_vocabulary": vocabulary, "field_vocabulary_digest": vocabulary["digest"],
              "semantic_judgments": accepted, "semantic_judgments_sha256": sha256_json(accepted),
              "resolved_spans": resolved}
    return source, registry, inventory, review


@pytest.mark.parametrize("keep_text", [False, True])
def test_shape_cleanup_preserves_paragraph_properties_and_same_text_siblings(tmp_path, keep_text):
    source, registry, inventory, review = _case(tmp_path, keep_text=keep_text)
    before = deepcopy(review)
    before_root = _read_document(source)
    before_paragraph = before_root.find(f"{W}body/{W}p")
    output = tmp_path / "candidate.docx"
    result = materialize_template_from_semantics(
        source_docx=source, output_docx=output, registry=registry,
        inventory=inventory, review=review,
    )
    root = _read_document(output)
    paragraph = root.find(f"{W}body/{W}p")
    assert paragraph is not None
    assert ET.tostring(paragraph.find(f"{W}pPr")) == ET.tostring(before_paragraph.find(f"{W}pPr"))
    assert ET.tostring(paragraph.find(f"{W}r")) == ET.tostring(before_paragraph.find(f"{W}r"))
    assert [node.get("id") for node in root.iter(V + "shape")] == ["keep"]
    assert ET.tostring(next(root.iter(V + "shape"))) == ET.tostring(
        list(before_root.iter(V + "shape"))[1]
    )
    assert result["cleanup_count"] == 1
    assert result["cleanup"][0]["action"] == "remove_shape"
    assert result["cleanup"][0]["source_entry_id"] == "source-entry-2"
    assert review == before
    assert sha256_file(source) == inventory["document_sha256"]


def test_partial_shape_cleanup_cannot_delete_uncovered_text(tmp_path):
    source, registry, inventory, review = _case(tmp_path, partial=True)
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure) as error:
        materialize_template_from_semantics(
            source_docx=source, output_docx=output, registry=registry,
            inventory=inventory, review=review,
        )
    assert error.value.code == "cleanup_span_not_whole_shape"
    assert not output.exists()


def test_paragraph_cleanup_still_conflicts_with_retained_child_shape(tmp_path):
    _, registry, inventory, review = _case(tmp_path)
    judgment = review["semantic_judgments"][0]
    judgment["parts"][0]["role"] = "cleanup"
    judgment["resolved_spans"][0]["role"] = "cleanup"
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry,
    )
    assert feedback is not None
    assert "materialization_semantic_scope_conflict" in [b["code"] for b in feedback["blockers"]]


def test_shape_cleanup_coexists_with_sibling_body_text_slot(tmp_path):
    source, registry, inventory, review = _case(tmp_path)
    judgment = review["semantic_judgments"][1]
    judgment["parts"][0].update(role="body_structure", field_id="body.paragraph")
    judgments = [{key: value for key, value in j.items() if key != "resolved_spans"}
                 for j in review["semantic_judgments"]]
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [{**j, "resolved_spans": [s for s in resolved if s["judgment_index"] == i]}
                for i, j in enumerate(judgments)]
    review.update(semantic_judgments=accepted, resolved_spans=resolved,
                  semantic_judgments_sha256=sha256_json(accepted))
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry,
    )
    assert feedback is None
    output = tmp_path / "candidate.docx"
    materialize_template_from_semantics(
        source_docx=source, output_docx=output, registry=registry,
        inventory=inventory, review=review,
    )
    root = _read_document(output)
    assert [node.get("id") for node in root.iter(V + "shape")] == ["keep"]
    assert len(list(root.iter(W + "sdt"))) == 1
