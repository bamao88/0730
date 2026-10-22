"""Internal failure ownership for the materialization readiness checkpoint.

Only failures of the submitted semantic contract can be repaired by the Agent.
An unknown execution failure stops at the host, rather than asking the Agent to
change school semantics until an implementation happens to accept them.
"""

from __future__ import annotations

from collections import Counter

from docfit.tools.runtime import JsonObject, ToolFailure

_SEMANTIC_REVISION_CODES = frozenset(
    {
        "materialization_part_field_missing",
        "materialization_slot_field_missing",
        "materialization_slot_field_incompatible",
        "materialization_field_not_in_vocabulary",
        "materialization_body_structure_semantics_missing",
        "materialization_body_structure_parent_missing",
        "materialization_generated_content_field_missing",
        "materialization_semantic_judgment_unresolved",
        "materialization_semantic_scope_conflict",
    }
)

_EXECUTION_CAPABILITY_CODES = frozenset(
    {
        "materialization_slot_carrier_unsupported",
        "materialization_body_structure_member_ambiguous",
        "materialization_body_structure_member_crosses_carriers",
        "materialization_body_structure_carrier_unsupported",
        "materialization_body_structure_nested_composite_member",
        "materialization_body_structure_carrier_conflict",
        "materialization_cleanup_carrier_conflict",
        "materialization_cleanup_target_unsupported",
        "materialization_intent_unclassified",
        "manual_table_cell_blocks_slot",
        "manual_table_cell_blocks_cleanup",
        "generated_content_blocks_slot",
        "cleanup_safety_missing",
    }
)


def readiness_recovery(blockers: object) -> JsonObject:
    """Classify the whole check; any host-owned failure preempts Agent revision."""
    codes = (
        [blocker.get("code") for blocker in blockers if isinstance(blocker, dict)]
        if isinstance(blockers, list)
        else []
    )
    if (
        not codes
        or not isinstance(blockers, list)
        or len(codes) != len(blockers)
        or any(
            not isinstance(code, str)
            or code not in _SEMANTIC_REVISION_CODES | _EXECUTION_CAPABILITY_CODES
            for code in codes
        )
    ):
        return {"kind": "system_state_invalid", "owner": "harness", "action": "stop"}
    if any(code in _EXECUTION_CAPABILITY_CODES for code in codes):
        return {"kind": "execution_unsupported", "owner": "tool", "action": "stop"}
    return {"kind": "semantic_revision", "owner": "agent", "action": "revise"}


def readiness_failure(feedback: JsonObject) -> ToolFailure:
    """Use the same failure contract at App and direct Tool execution boundaries."""
    blockers = feedback.get("blockers")
    recovery = readiness_recovery(blockers)
    revisable = recovery["action"] == "revise"
    codes = (
        [str(item.get("code", "unknown")) for item in blockers if isinstance(item, dict)]
        if isinstance(blockers, list)
        else []
    )
    return ToolFailure(
        status="needs_input" if revisable else "error",
        origin="harness" if revisable else str(recovery["owner"]),
        code=(
            "template_materialization_readiness_incomplete"
            if revisable
            else f"template_materialization_{recovery['kind']}"
        ),
        message=(
            f"Accepted semantic review is not materializable ({len(codes)} blockers): "
            + ", ".join(f"{code} ({count})" for code, count in Counter(codes).items())
            + "."
        ),
        retryable=revisable,
        suggested_actions=(
            ("Return the agent_revision_packet to the Agent.",)
            if revisable
            else (
                "Preserve the semantic judgments; repair the reported execution or system issue.",
                "Do not retry semantic judgment or run materialization handlers for this failure.",
            )
        ),
    )
