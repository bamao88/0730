"""Failure ownership for source-annotation review, before Agent feedback projection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

JsonObject = dict[str, Any]

# These are output-contract defects that can actually be repaired by changing judgments.
# All other review failures stop for engineering diagnosis; wording never decides ownership.
REVISABLE_SEMANTIC_CODES = frozenset(
    {
        "ordered_semantic_parts_invalid",
        "ordered_semantic_judgment_invalid",
        "agent_authored_legacy_or_internal_id",
        "legacy_reading_scope_unsupported",
        "ordered_semantic_source_entry_invalid",
        "ordered_semantic_source_entry_unknown",
        "ordered_semantic_source_entry_missing",
        "ordered_semantic_parts_missing",
        "ordered_semantic_part_invalid",
        "ordered_semantic_part_role_invalid",
        "ordered_semantic_part_text_missing",
        "fill_slot_includes_label_delimiter",
        "ordered_semantic_part_field_missing",
        "field_id_not_in_input_vocabulary",
        "field_role_not_in_input_vocabulary",
        "ordered_semantic_part_field_forbidden",
        "ordered_part_source_entry_unknown",
        "source_span_duplicate_entry_judgment",
        "source_span_missing_entry_judgment",
        "whole_entry_part_invalid",
        "ordered_part_empty_for_text_entry",
        "ordered_part_text_mismatch",
        "ordered_part_text_gap",
        "ordered_part_text_not_found",
        "ordered_part_crosses_unit_cut",
        "ordered_part_whitespace_transport_invalid",
        "missing_source_entry_semantic_judgments",
        "unknown_source_entry_semantic_judgments",
        "overlapping_source_entry_semantic_judgments",
        "missing_semantic_judgments",
        "semantic_judgments_missing",
        "empty_semantic_judgments",
        "semantic_batch_status_incomplete",
        "semantic_batch_entries_missing",
        "semantic_batch_entries_unexpected",
        "semantic_batch_entries_duplicate",
        "semantic_batch_entries_out_of_order",
        "semantic_revision_request_invalid",
        "semantic_revision_request_mixed",
        "related_semantic_revision_requested",
    }
)

SYSTEM_REVIEW_MESSAGES = {
    "source_span_fragment_gap": (
        "Some source text has no usable document position; source mapping needs repair."
    ),
    "source_span_fragment_ambiguous": (
        "Some source text maps to multiple document positions; source mapping needs repair."
    ),
    "source_span_entry_unknown": "The source entry disappeared from the prepared document mapping.",
    "source_span_out_of_bounds": (
        "The prepared document mapping describes a range outside the source text."
    ),
    "source_span_extent_kind_mismatch": (
        "The prepared document mapping disagrees with the source entry type."
    ),
    "semantic_spans_without_source_entry_coverage": (
        "The system could not map the resolved text back to its source entries."
    ),
    "field_id_vocabulary_missing": (
        "The field choices required for this task were not supplied during preparation."
    ),
}


def classify_semantic_feedback(feedback: JsonObject) -> JsonObject:
    result = deepcopy(feedback)
    blockers = result.get("blockers")
    revisable = (
        isinstance(blockers, list)
        and bool(blockers)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("code"), str)
            and item["code"] in REVISABLE_SEMANTIC_CODES
            for item in blockers
        )
    )
    result["recovery"] = {
        "kind": "semantic_revision" if revisable else "system_state_invalid",
        "owner": "agent" if revisable else "harness",
        "action": "revise" if revisable else "stop",
    }
    if not revisable:
        result["status"] = "error"
        metadata = result.get("feedback")
        if isinstance(metadata, dict):
            metadata["agent_action"] = None
        failure = result.get("failure")
        if not isinstance(failure, dict):
            failure = {}
            result["failure"] = failure
        failure.update(
            {
                "origin": "harness",
                "retryable": False,
                "suggested_actions": [
                    "Repair the source review system before resuming semantic work."
                ],
            }
        )
    return result
