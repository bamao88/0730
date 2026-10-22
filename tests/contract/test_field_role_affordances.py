from copy import deepcopy

import pytest

from docfit.app.prepare_template import _agent_visible_feedback_packet
from docfit.template.batch_review import batch_text_feedback
from docfit.template.harness import _ordered_semantic_parts_feedback
from docfit.template.source_entries import build_canonical_source_inventory
from tests.support.source_identity import source_partition


def _case(allowed_roles, role):
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64,
        inspected_objects=[{
            "type": "paragraph", "locator": "/body/p[1]", "text": "sample",
            "object_ref": {"object_id": "p1", "document_sha256": "a" * 64},
        }],
    )
    inventory = {
        "document_sha256": "a" * 64, "canonical_source_inventory": canonical.to_json(),
        "field_id_vocabulary": {
            "allowed_field_ids": ["custom.value"],
            "fields": [{"field_id": "custom.value", "usage_affordance": {
                "allowed_part_roles": allowed_roles,
            }}],
        },
    }
    source_partition(inventory)
    judgment = {"source_entry_id": canonical.source_entries[0].source_entry_id,
                "parts": [{"whole_entry": True, "role": role, "field_id": "custom.value"}]}
    return inventory, judgment


@pytest.mark.parametrize("allowed_roles,role", [
    (["body_structure"], "fill_slot"),
    (["fill_slot"], "body_structure"),
    (["generated_content"], "fill_slot"),
    ([], "fill_slot"),
])
def test_batch_rejects_incompatible_roles_from_declared_vocabulary_before_mapping(
    allowed_roles, role, monkeypatch,
):
    inventory, judgment = _case(allowed_roles, role)
    before = deepcopy(judgment)

    def unexpected_mapping(*args, **kwargs):
        raise AssertionError("Incompatible role must be reported before source mapping")

    monkeypatch.setattr(
        "docfit.template.batch_review._resolve_ordered_span_refs", unexpected_mapping,
    )
    local = batch_text_feedback(
        inventory=inventory, judgments=[judgment],
        required_source_entry_ids=(judgment["source_entry_id"],),
    )
    global_feedback = _ordered_semantic_parts_feedback(inventory, [judgment])
    assert local["blockers"] == global_feedback["blockers"]
    assert local["recovery"] == {"kind": "semantic_revision", "owner": "agent", "action": "revise"}
    assert judgment == before
    issue = local["blockers"][0]
    assert issue["code"] == "field_role_not_in_input_vocabulary"
    assert issue["allowed_part_roles"] == allowed_roles
    visible = _agent_visible_feedback_packet(local, next_step="Reconsider the field and role.")
    visible_issue = visible["affected"][0]
    assert visible_issue["source_entry_id"] == judgment["source_entry_id"]
    assert visible_issue["submitted_role"] == role
    assert visible_issue["allowed_part_roles"] == allowed_roles


@pytest.mark.parametrize("role", ["fill_slot", "body_structure", "generated_content"])
def test_arbitrary_field_name_uses_its_declared_role_without_name_heuristics(role):
    inventory, judgment = _case([role], role)
    assert batch_text_feedback(
        inventory=inventory, judgments=[judgment],
        required_source_entry_ids=(judgment["source_entry_id"],),
    ) is None


@pytest.mark.parametrize("mutation", [
    lambda v: v.pop("fields"),
    lambda v: v["fields"].append(deepcopy(v["fields"][0])),
    lambda v: v["fields"][0].pop("usage_affordance"),
    lambda v: v["fields"][0]["usage_affordance"].update(allowed_part_roles="fill_slot"),
    lambda v: v["fields"][0]["usage_affordance"].update(allowed_part_roles=["unknown"]),
])
def test_missing_or_invalid_role_affordance_stops_for_harness_repair(mutation):
    inventory, judgment = _case(["fill_slot"], "fill_slot")
    mutation(inventory["field_id_vocabulary"])
    feedback = batch_text_feedback(
        inventory=inventory, judgments=[judgment],
        required_source_entry_ids=(judgment["source_entry_id"],),
    )
    assert feedback["blockers"][0]["code"] == "field_role_affordance_invalid"
    assert feedback["recovery"] == {
        "kind": "system_state_invalid", "owner": "harness", "action": "stop",
    }
    assert feedback["feedback"]["agent_action"] is None
