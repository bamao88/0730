from copy import deepcopy

import pytest
from jsonschema import Draft7Validator

from docfit.app.prepare_template import _ORDERED_SEMANTIC_JUDGMENT_SCHEMA
from docfit.template.batch_review import batch_text_feedback
from docfit.template.harness import _decode_semantic_parts
from docfit.template.judgment_shape import validate_ordered_semantic_parts
from docfit.template.revision_context import _visible_judgment
from docfit.template.source_entries import build_canonical_source_inventory
from docfit.template.source_spans import resolve_semantic_judgments
from tests.support.source_identity import source_partition


def _case(text="\uf06f option\t\uf0fe other"):
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[{
            "type": "paragraph", "locator": "/body/p[1]", "text": text,
            "object_ref": {"document_sha256": "a" * 64, "object_id": "paragraph"},
        }],
    )
    inventory = {"document_sha256": "a" * 64,
                 "canonical_source_inventory": canonical.to_json()}
    source_partition(inventory)
    entry_id = canonical.source_entries[0].source_entry_id
    judgment = {"source_entry_id": entry_id, "parts": [{
        "whole_entry": True, "role": "fill_slot", "field_id": "degree.type",
    }]}
    return inventory, judgment


@pytest.mark.parametrize("text", ["\uf06f option\t\uf0fe other", "   ", "", "label：value"])
def test_explicit_whole_entry_matches_literal_text_and_single_slot(text):
    inventory, judgment = _case(text)
    before = deepcopy(judgment)
    Draft7Validator(_ORDERED_SEMANTIC_JUDGMENT_SCHEMA).validate(judgment)
    assert validate_ordered_semantic_parts(
        [judgment], allowed_field_ids=["degree.type"],
        source_entry_ids=[judgment["source_entry_id"]],
    )["status"] == "ok"
    decoded, feedback = _decode_semantic_parts(inventory, [judgment])
    assert feedback is None
    literal = {"source_entry_id": judgment["source_entry_id"], "parts": [{
        "text": text, "role": "fill_slot", "field_id": "degree.type",
    }]}
    assert decoded == [literal] and judgment == before
    expected = resolve_semantic_judgments(inventory=inventory, judgments=[literal])
    actual = resolve_semantic_judgments(inventory=inventory, judgments=decoded)
    assert actual == expected and len(actual) == 1 and "slot_ref" in actual[0]
    assert batch_text_feedback(inventory=inventory, judgments=[judgment],
                              required_source_entry_ids=(judgment["source_entry_id"],)) is None


@pytest.mark.parametrize("override", [
    {"whole_entry": False}, {"whole_entry": 1}, {"whole_entry": "true"},
    {"text": ""}, {"text": "partial"},
    {"whitespace": {"codepoint": "U+0020", "count": 1}},
    {"leading_whitespace": [{"codepoint": "U+0020", "count": 1}]},
    {"trailing_whitespace": [{"codepoint": "U+0020", "count": 1}]},
])
def test_whole_entry_cannot_override_a_partial_submission_or_mix_encodings(override):
    inventory, judgment = _case()
    judgment["parts"][0].update(override)
    assert not Draft7Validator(_ORDERED_SEMANTIC_JUDGMENT_SCHEMA).is_valid(judgment)
    assert validate_ordered_semantic_parts(
        [judgment], allowed_field_ids=["degree.type"],
        source_entry_ids=[judgment["source_entry_id"]],
    )["status"] == "needs_input"
    _, feedback = _decode_semantic_parts(inventory, [judgment])
    assert feedback and feedback["blockers"][0]["code"] == "ordered_whole_entry_declaration_invalid"


def test_whole_entry_cannot_overlap_another_part_or_name_unknown_source():
    inventory, judgment = _case()
    judgment["parts"].append({"text": "other", "role": "fixed_label"})
    assert not Draft7Validator(_ORDERED_SEMANTIC_JUDGMENT_SCHEMA).is_valid(judgment)
    assert _decode_semantic_parts(inventory, [judgment])[1] is not None
    judgment["parts"].pop()
    judgment["source_entry_id"] = "unknown"
    _, feedback = _decode_semantic_parts(inventory, [judgment])
    assert feedback["blockers"][0]["code"] == "ordered_semantic_source_entry_unknown"


def test_partial_single_role_is_never_implicitly_expanded():
    inventory, judgment = _case("label：value")
    judgment["parts"] = [{"text": "label：", "role": "fixed_label"}]
    decoded, feedback = _decode_semantic_parts(inventory, [judgment])
    assert feedback is None and decoded == [judgment]
    feedback = batch_text_feedback(inventory=inventory, judgments=[judgment],
                                   required_source_entry_ids=(judgment["source_entry_id"],))
    assert feedback and feedback["blockers"][0]["code"] == "ordered_part_text_gap"


def test_declared_scope_does_not_bypass_field_vocabulary_or_hide_revision_baseline():
    _, judgment = _case()
    assert validate_ordered_semantic_parts(
        [judgment], allowed_field_ids=[], source_entry_ids=[judgment["source_entry_id"]],
    )["status"] == "needs_input"
    assert _visible_judgment(judgment) == judgment
    literal = {"source_entry_id": judgment["source_entry_id"],
               "parts": [{"role": "fixed_label"}]}
    assert not Draft7Validator(_ORDERED_SEMANTIC_JUDGMENT_SCHEMA).is_valid(literal)


def test_whole_entry_still_respects_accepted_unit_cut():
    inventory, judgment = _case("alpha beta")
    entry_id = judgment["source_entry_id"]
    split = {"source_entry_id": entry_id, "edge": "split", "before": "alpha", "after": " beta"}
    source_partition(inventory, units=[
        {"unit_id": "a", "unit_name": "first",
         "start_boundary": {"source_entry_id": entry_id, "edge": "start"},
         "end_boundary": split},
        {"unit_id": "b", "unit_name": "second", "start_boundary": split,
         "end_boundary": {"source_entry_id": entry_id, "edge": "end"}},
    ])
    feedback = batch_text_feedback(inventory=inventory, judgments=[judgment],
                                   required_source_entry_ids=(entry_id,))
    assert feedback and feedback["blockers"][0]["code"] == "ordered_part_crosses_unit_cut"
