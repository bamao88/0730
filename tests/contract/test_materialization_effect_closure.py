"""Constructed DOCX execution contracts; not school replay or Agent E2E."""

from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from docfit.template.materialization import materialize_template_from_semantics
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json
from tests.contract.test_shape_cleanup_materialization import V, W, _case, _read_document


def mixed_case(tmp_path, mode):
    source, registry, inventory, review = _case(tmp_path)
    judgments = [
        {k: deepcopy(v) for k, v in j.items() if k != "resolved_spans"}
        for j in review["semantic_judgments"]
    ]
    judgments[1]["parts"] = [
        {"text": "same", "role": "manual_region" if mode == "manual" else "fixed_label"},
        {"text": " text", "role": "cleanup"},
    ]
    if mode == "slot":
        judgments[1]["parts"][1] = {
            "text": " text",
            "role": "fill_slot",
            "field_id": "thesis.title.zh",
        }
    judgments[2]["parts"][0]["role"] = "fixed_label"
    spans = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [
        {**j, "resolved_spans": [s for s in spans if s["judgment_index"] == i]}
        for i, j in enumerate(judgments)
    ]
    review.update(
        semantic_judgments=accepted,
        resolved_spans=spans,
        semantic_judgments_sha256=sha256_json(accepted),
    )
    return source, registry, inventory, review


@pytest.mark.parametrize("mode", ["fixed", "slot", "manual"])
def test_mixed_entry_executes_only_its_parts_and_preserves_independent_shapes(tmp_path, mode):
    source, registry, inventory, review = mixed_case(tmp_path, mode)
    source_hash, original_review = sha256_file(source), deepcopy(review)
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
    assert [ET.tostring(n) for n in after.iter(V + "shape")] == [
        ET.tostring(n) for n in before.iter(V + "shape")
    ]
    paragraph = after.find(f"{W}body/{W}p")
    assert paragraph is not None
    assert paragraph.find(f"{W}r/{W}t").text == "same"
    assert ET.tostring(paragraph.find(W + "pPr")) == ET.tostring(
        before.find(f"{W}body/{W}p/{W}pPr")
    )
    if mode == "slot":
        assert len(list(paragraph.iter(W + "sdt"))) == 1
    else:
        assert result["cleanup_count"] == 1
    assert sha256_file(source) == source_hash
    assert review == original_review
    assert result["effect_verification"]["reopened_package"] is True


@pytest.mark.parametrize(
    "fault", ["skip_handler", "skip_edits", "erase_sibling", "corrupt_write", "move_slot"]
)
def test_actual_effect_failure_prevents_candidate_even_with_success_receipts(
    tmp_path, monkeypatch, fault
):
    import docfit.template.materialization.runtime as runtime
    from docfit.template.materialization.text_edits import TextEdits

    source, registry, inventory, review = mixed_case(
        tmp_path, "slot" if fault == "move_slot" else "fixed"
    )
    before_hash = sha256_file(source)
    if fault == "skip_handler":
        monkeypatch.setattr(
            runtime,
            "_rewrite_non_slot_intent",
            lambda **_: {
                "action": "remove_exact_fragments",
                "judgment_refs": ["semantic_judgments[1]"],
            },
        )
    elif fault == "skip_edits":
        monkeypatch.setattr(TextEdits, "apply", lambda self: None)
    elif fault in {"erase_sibling", "move_slot"}:
        original_apply = TextEdits.apply

        def erase(self):
            original_apply(self)
            paragraph = next(iter(self.original_paragraphs))
            if fault == "erase_sibling":
                pict = paragraph.find(f"{W}r/{W}pict")
                pict.remove(next(pict.iter(V + "shape")))
            else:
                slot = paragraph.find(W + "sdt")
                paragraph.remove(slot)
                paragraph.append(slot)

        monkeypatch.setattr(TextEdits, "apply", erase)
    else:
        serialize = runtime._serialize

        def corrupt(root):
            first = root.find(f"{W}body/{W}p/{W}r/{W}t")
            if first is not None and first.text == "same":
                root = deepcopy(root)
                root.find(f"{W}body/{W}p/{W}r/{W}t").text = "WRONG"
            return serialize(root)

        monkeypatch.setattr(runtime, "_serialize", corrupt)
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
    assert not list(tmp_path.glob(".candidate.docx.*.tmp"))
    assert sha256_file(source) == before_hash


@pytest.mark.parametrize("role", ["fixed_label", "manual_region", "fill_slot", "body_structure"])
def test_cross_run_edits_preserve_styles_bookmarks_fields_and_duplicate_text(tmp_path, role):
    from docfit.fields import FieldRegistrySnapshot
    from tests.contract.test_template_materialization_runtime import (
        _inventory_with_paragraph_objects,
        _judgment,
        _part,
        _write_body_registry,
        _write_docx_from_paragraph_xml,
        _write_registry,
    )
    from tests.contract.test_template_materialization_runtime import (
        materialize_template_from_semantics as run_case,
    )

    source, output = tmp_path / "source.docx", tmp_path / "candidate.docx"
    registry_path = tmp_path / "registry.yaml"
    (_write_body_registry if role == "body_structure" else _write_registry)(registry_path)
    _write_docx_from_paragraph_xml(
        source,
        [
            "<w:p><w:pPr><w:keepNext/></w:pPr>"
            "<w:r><w:rPr><w:b/></w:rPr><w:t>AB(no</w:t></w:r>"
            "<w:r><w:rPr><w:i/></w:rPr><w:t>te)</w:t></w:r>"
            '<w:bookmarkStart w:id="7" w:name="keep"/>'
            '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>AB</w:t></w:r>'
            '<w:bookmarkEnd w:id="7"/>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            "<w:r><w:instrText> PAGE </w:instrText></w:r>"
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            "<w:r><w:t>7</w:t></w:r>"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>',
        ],
    )
    field = "body.paragraph" if role == "body_structure" else "author.name.zh"
    first = _part(
        role, "AB", **({"field_id": field} if role in {"fill_slot", "body_structure"} else {})
    )
    inventory = _inventory_with_paragraph_objects(
        [
            {"block_id": "sample", "covered_object_ids": ["obj-1"], "text": "AB(note)AB7"},
        ]
    )
    before = _read_document(source)
    run_case(
        source_docx=source,
        output_docx=output,
        registry=FieldRegistrySnapshot.load(registry_path),
        inventory=inventory,
        review={
            "semantic_judgments": [
                _judgment(
                    "sample",
                    [
                        first,
                        _part("cleanup", "(note)"),
                        _part("fixed_label", "AB7"),
                    ],
                )
            ]
        },
    )
    after = _read_document(output)
    for tag in ("bookmarkStart", "bookmarkEnd", "fldChar", "instrText", "pPr"):
        assert [ET.tostring(n) for n in before.iter(W + tag)] == [
            ET.tostring(n) for n in after.iter(W + tag)
        ]
    kept_run = next(r for r in after.iter(W + "r") if r.find(f"{W}rPr/{W}u") is not None)
    assert kept_run.find(W + "t").text == "AB"
    if role in {"fixed_label", "manual_region"}:
        assert next(after.iter(W + "r")).find(W + "t").text == "AB"
        assert next(after.iter(W + "r")).find(f"{W}rPr/{W}b") is not None
    assert "(note)" not in "".join(n.text or "" for n in after.iter(W + "t"))
