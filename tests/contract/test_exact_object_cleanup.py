"""Constructed Word execution contracts, not real-school or Agent-loop evidence."""

from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.contract.test_shape_cleanup_materialization import _registry
from tests.contract.test_template_materialization_runtime import (
    W,
    _read_document,
    _write_docx_from_paragraph_xml,
)
from tests.support.source_identity import review_binding, source_partition


def drawing(identity):
    return (
        '<w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/'
        f'drawingml/2006/wordprocessingDrawing"><wp:docPr id="{identity}" name="same"/>'
        "</wp:inline></w:drawing>"
    )


def case(tmp_path, xml, rows):
    source = tmp_path / "source.docx"
    _write_docx_from_paragraph_xml(source, [xml])
    source_hash = sha256_file(source)
    registry = _registry(tmp_path / "registry.yaml")
    vocabulary = registry.pre_input_vocabulary()
    entries, objects, judgments = [], [], []
    for index, (kind, locator, text, parts) in enumerate(rows):
        entry_id, object_id = f"source-entry-{index}", f"obj-{index}"
        fingerprint = sha256_json({"locator": locator, "text": text})
        reference = {
            "object_id": object_id,
            "document_sha256": source_hash,
            "expected_fingerprint": fingerprint,
        }
        provenance = {
            "object_id": object_id,
            "locator": locator,
            "fingerprint": fingerprint,
            "object_ref": reference,
        }
        provenance.update(
            {"text_span": [0, len(text)]} if text else {"extent": {"kind": "whole_entry"}}
        )
        entries.append(
            {
                "source_entry_id": entry_id,
                "entry_type": kind,
                "text": text,
                "provenance": [provenance],
                "source_order": {"block": index + 1, "inline": 0},
            }
        )
        objects.append(
            {
                "object_id": object_id,
                "type": kind,
                "locator": locator,
                "object_ref": reference,
                "source_entry_id": entry_id,
            }
        )
        judgments.append({"source_entry_id": entry_id, "parts": parts})
    inventory = {
        "document_sha256": source_hash,
        "source_entries": entries,
        "objects": objects,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    source_partition(inventory)
    spans = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [
        {**j, "resolved_spans": [s for s in spans if s["judgment_index"] == i]}
        for i, j in enumerate(judgments)
    ]
    review = {
        **review_binding(inventory),
        "document_sha256": source_hash,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": spans,
    }
    return source, registry, inventory, review


def part(role, text="", **extra):
    return {"role": role, "text": text, **extra}


@pytest.mark.parametrize("text_role", ["fixed_label", "fill_slot", "cleanup"])
def test_picture_cleanup_preserves_shared_run_text_layout_and_other_picture(tmp_path, text_role):
    xml = (
        '<w:p><w:pPr><w:spacing w:after="120"/><w:keepNext/></w:pPr>'
        "<w:r><w:rPr><w:b/></w:rPr><w:t>same</w:t>" + drawing(1) + "</w:r>"
        '<w:bookmarkStart w:id="1" w:name="keep"/>'
        "<w:r>" + drawing(2) + '</w:r><w:bookmarkEnd w:id="1"/></w:p>'
    )
    source, registry, inventory, review = case(
        tmp_path,
        xml,
        [
            ("paragraph", "/body/p[1]", "", [part("style_only")]),
            (
                "text",
                "/body/p[1]/r[1]",
                "same",
                [
                    part(
                        text_role,
                        "same",
                        **({"field_id": "thesis.title.zh"} if text_role == "fill_slot" else {}),
                    )
                ],
            ),
            ("picture", "/body/p[1]/r[1]", "", [part("cleanup")]),
            ("picture", "/body/p[1]/r[2]", "", [part("fixed_label")]),
        ],
    )
    original_review = deepcopy(review)
    before = _read_document(source)
    output = tmp_path / "candidate.docx"
    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    after = _read_document(output)
    assert [ET.tostring(n) for n in after.iter(W + "drawing")] == [
        ET.tostring(list(before.iter(W + "drawing"))[1])
    ]
    for tag in ("pPr", "bookmarkStart", "bookmarkEnd"):
        assert [ET.tostring(n) for n in before.iter(W + tag)] == [
            ET.tostring(n) for n in after.iter(W + tag)
        ]
    assert after.find(f"{W}body/{W}p/{W}r/{W}rPr/{W}b") is not None
    if text_role == "fixed_label":
        assert after.find(f"{W}body/{W}p/{W}r/{W}t").text == "same"
    elif text_role == "fill_slot":
        assert len(list(after.iter(W + "sdt"))) == 1
    else:
        assert not any(n.text == "same" for n in after.iter(W + "t"))
    assert any(c["action"] == "remove_drawing" for c in result["cleanup"])
    assert review == original_review
    assert sha256_file(source) == inventory["document_sha256"]


def test_picture_mapping_with_two_drawings_stops_without_choosing_one(tmp_path):
    source, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r>" + drawing(1) + drawing(2) + "</w:r></w:p>",
        [("picture", "/body/p[1]/r[1]", "", [part("cleanup")])],
    )
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert caught.value.origin == "tool"
    assert caught.value.code == "materialization_cleanup_target_unsupported"
    assert not output.exists()


def test_whole_table_delete_with_retained_child_is_semantic_conflict(tmp_path):
    _, registry, inventory, review = case(
        tmp_path,
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Keep</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
        [
            ("table", "/body/tbl[1]", "", [part("cleanup")]),
            ("text", "/body/tbl[1]/tr[1]/tc[1]/p[1]/r[1]", "Keep", [part("fixed_label", "Keep")]),
        ],
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    assert feedback["recovery"] == {
        "kind": "semantic_revision",
        "owner": "agent",
        "action": "revise",
    }
    blocker = next(
        b for b in feedback["blockers"] if b["code"] == "materialization_semantic_scope_conflict"
    )
    assert set(blocker["source_entry_ids"]) == {"source-entry-0", "source-entry-1"}
    assert any(e["text"] == "Keep" for e in blocker["source_entries"])
    from docfit.app.prepare_template import _agent_visible_blocker

    visible = _agent_visible_blocker(blocker)
    assert set(visible["source_entry_ids"]) == {"source-entry-0", "source-entry-1"}
    assert "Keep" in str(visible)
    assert not any(word in str(visible) for word in ("locator", "object_ref", "span_ref"))


@pytest.mark.parametrize("role", ["fixed_label", "fill_slot"])
def test_overlapping_text_cleanup_and_retention_or_slot_requires_revision(tmp_path, role):
    _, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r><w:t>same</w:t></w:r></w:p>",
        [
            ("text", "/body/p[1]/r[1]", "same", [part("cleanup", "same")]),
            (
                "text",
                "/body/p[1]/r[1]",
                "same",
                [
                    part(
                        role,
                        "same",
                        **({"field_id": "thesis.title.zh"} if role == "fill_slot" else {}),
                    )
                ],
            ),
        ],
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    assert feedback["recovery"]["owner"] == "agent"
    assert feedback["blockers"][0]["code"] == "materialization_semantic_scope_conflict"


def test_whole_paragraph_and_nested_picture_cleanup_share_deletion_without_widening(tmp_path):
    source, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r>" + drawing(1) + "</w:r></w:p><w:p><w:r><w:t>Keep</w:t></w:r></w:p>",
        [
            ("paragraph", "/body/p[1]", "", [part("cleanup")]),
            ("picture", "/body/p[1]/r[1]", "", [part("cleanup")]),
            ("text", "/body/p[2]/r[1]", "Keep", [part("fixed_label", "Keep")]),
        ],
    )
    output = tmp_path / "candidate.docx"
    result = materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    after = _read_document(output)
    assert len(list(after.iter(W + "p"))) == 1
    assert next(after.iter(W + "t")).text == "Keep"
    assert result["cleanup"][0]["action"] == "remove_paragraph"
    assert result["cleanup"][1]["shared_carrier_already_removed"] is True


def test_mixed_semantic_and_engineering_blockers_keep_individual_ownership(tmp_path):
    _, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r><w:t>Keep</w:t></w:r></w:p><w:p><w:hyperlink/></w:p>",
        [
            ("paragraph", "/body/p[1]", "", [part("cleanup")]),
            ("text", "/body/p[1]/r[1]", "Keep", [part("fixed_label", "Keep")]),
            ("object", "/body/p[2]/hyperlink[1]", "", [part("cleanup")]),
        ],
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    assert feedback["recovery"] == {
        "kind": "execution_unsupported",
        "owner": "tool",
        "action": "stop",
    }
    assert {b["code"]: b["recovery"]["owner"] for b in feedback["blockers"]} == {
        "materialization_semantic_scope_conflict": "agent",
        "materialization_cleanup_target_unsupported": "tool",
    }


def test_table_and_child_text_cleanup_are_compatible_without_reediting_deleted_text(tmp_path):
    source, registry, inventory, review = case(
        tmp_path,
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Remove</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "<w:p><w:r><w:t>Keep</w:t></w:r></w:p>",
        [
            ("table", "/body/tbl[1]", "", [part("cleanup")]),
            ("text", "/body/tbl[1]/tr[1]/tc[1]/p[1]/r[1]", "Remove", [part("cleanup", "Remove")]),
            ("text", "/body/p[1]/r[1]", "Keep", [part("fixed_label", "Keep")]),
        ],
    )
    output = tmp_path / "candidate.docx"
    materialize_template_from_semantics(
        source_docx=source,
        output_docx=output,
        registry=registry,
        inventory=inventory,
        review=review,
    )
    after = _read_document(output)
    assert not list(after.iter(W + "tbl"))
    assert next(after.iter(W + "t")).text == "Keep"


def test_faulty_picture_handler_cannot_delete_the_parent_and_report_success(tmp_path, monkeypatch):
    import docfit.template.materialization.runtime as runtime

    source, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:pPr><w:keepNext/></w:pPr><w:r>" + drawing(1) + "</w:r></w:p>",
        [
            ("paragraph", "/body/p[1]", "", [part("style_only")]),
            ("picture", "/body/p[1]/r[1]", "", [part("cleanup")]),
        ],
    )
    original = runtime._remove_exact_cleanup_intent

    def wrong(**kwargs):
        receipt = original(**kwargs)
        body = kwargs["document"].find(W + "body")
        body.remove(body.find(W + "p"))
        return receipt

    monkeypatch.setattr(runtime, "_remove_exact_cleanup_intent", wrong)
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert caught.value.code == "materialization_effect_mismatch"
    assert not output.exists()


@pytest.mark.parametrize("role", ["fixed_label", "manual_region"])
def test_whole_retained_table_conflicts_with_child_text_removal(tmp_path, role):
    _, registry, inventory, review = case(
        tmp_path,
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Keep</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
        [
            ("table", "/body/tbl[1]", "", [part(role)]),
            ("text", "/body/tbl[1]/tr[1]/tc[1]/p[1]/r[1]", "Keep", [part("cleanup", "Keep")]),
        ],
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory, review=review, registry=registry
    )
    assert feedback["recovery"]["owner"] == "agent"
    assert feedback["blockers"][0]["code"] == "materialization_semantic_scope_conflict"


def test_actual_node_check_rejects_overlapping_text_hidden_by_locator_aliases(tmp_path):
    source, registry, inventory, review = case(
        tmp_path,
        '<w:p w14:paraId="ABCDEF12"><w:r><w:t>Keep</w:t></w:r></w:p>',
        [
            ("text", "/body/p[1]/r[1]", "Keep", [part("cleanup", "Keep")]),
            ("text", "/body/p[@paraId=ABCDEF12]/r[1]", "Keep", [part("fixed_label", "Keep")]),
        ],
    )
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert caught.value.code == "materialization_effect_mismatch"
    assert caught.value.origin == "tool"
    assert not output.exists()


def test_unknown_whole_run_is_not_reinterpreted_as_a_picture(tmp_path):
    source, registry, inventory, review = case(
        tmp_path,
        "<w:p><w:r>" + drawing(1) + "</w:r></w:p>",
        [("object", "/body/p[1]/r[1]", "", [part("cleanup")])],
    )
    output = tmp_path / "candidate.docx"
    with pytest.raises(ToolFailure) as caught:
        materialize_template_from_semantics(
            source_docx=source,
            output_docx=output,
            registry=registry,
            inventory=inventory,
            review=review,
        )
    assert caught.value.code == "materialization_cleanup_target_unsupported"
    assert not output.exists()
