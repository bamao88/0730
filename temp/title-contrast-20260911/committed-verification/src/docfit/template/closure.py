"""Mechanical scoped-closure aggregation for template extraction subagents."""

from __future__ import annotations

from collections import Counter
from typing import Any

from docfit.template.judgment_shape import (
    CLOSURE_REVIEW_CONTEXT_V1,
    SCOPED_CLOSURE_V1,
    JsonObject,
    mechanical_feedback,
    validate_scoped_closure_v1,
)
from docfit.tools.surface import DOCFIT_CHECK_TOOL, DOCFIT_EVIDENCE_TOOL

READ_ONLY_CLOSURE_TOOLS = (DOCFIT_EVIDENCE_TOOL, DOCFIT_CHECK_TOOL)


def build_closure_task_packet(
    *,
    source_hash: str,
    context_profile: str,
    assigned_scope: JsonObject,
    assigned_target: str,
    reference_hints: tuple[str, ...] = (),
    max_depth: int = 1,
    timeout_seconds: int = 120,
    token_budget: int = 8000,
) -> JsonObject:
    return {
        "schema_version": SCOPED_CLOSURE_V1,
        "source_hash": source_hash,
        "context_profile": context_profile,
        "assigned_scope": assigned_scope,
        "assigned_target": assigned_target,
        "reference_hints": list(reference_hints),
        "allowed_tools": list(READ_ONLY_CLOSURE_TOOLS),
        "limits": {
            "max_depth": max_depth,
            "max_concurrency": 1,
            "timeout_seconds": timeout_seconds,
            "token_budget": token_budget,
        },
        "requested_output": SCOPED_CLOSURE_V1,
    }


def can_consume_closure_review_context(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == CLOSURE_REVIEW_CONTEXT_V1
        and payload.get("status") == "ok"
        and isinstance(payload.get("closures"), list)
    )


def aggregate_scoped_closures(
    closures: Any,
    *,
    source_hash: str,
    context_profile: str,
    expected_scope_ids: tuple[str, ...] = (),
) -> JsonObject:
    if not isinstance(closures, list):
        return mechanical_feedback(
            feedback_type="subagent_closure",
            code="subagent_closure_shape_invalid",
            message="Subagent closures must be structured objects, not natural language.",
            blockers=[
                {
                    "code": "subagent_closure_shape_invalid",
                    "field": "closures",
                    "message": "closures must be an array of scoped_closure_v1 objects.",
                }
            ],
        )

    blockers: list[JsonObject] = []
    normalized: list[JsonObject] = []
    closure_ids: list[str] = []
    scope_ids: list[str] = []
    scope_object_ids: dict[str, set[str]] = {}

    for index, closure in enumerate(closures):
        envelope = validate_scoped_closure_v1(closure)
        if envelope.get("status") != "ok":
            blockers.append(
                {
                    "code": "scoped_closure_envelope_invalid",
                    "field": f"closures[{index}]",
                    "message": "Closure must include schema_version and source_hash.",
                    "feedback": envelope.get("failure"),
                }
            )
            continue
        assert isinstance(closure, dict)
        if closure.get("source_hash") != source_hash:
            blockers.append(
                {
                    "code": "stale_scoped_closure",
                    "field": f"closures[{index}].source_hash",
                    "message": "Closure source_hash does not match the current source.",
                }
            )
        if closure.get("context_profile") != context_profile:
            blockers.append(
                {
                    "code": "closure_profile_mismatch",
                    "field": f"closures[{index}].context_profile",
                    "message": "Closure context_profile does not match the assigned profile.",
                }
            )
        closure_id = closure.get("closure_id")
        if not isinstance(closure_id, str) or not closure_id.strip():
            blockers.append(
                {
                    "code": "closure_id_missing",
                    "field": f"closures[{index}].closure_id",
                    "message": "Closure must include a stable closure_id.",
                }
            )
        else:
            closure_ids.append(closure_id)
        assigned_scope = closure.get("assigned_scope")
        if not isinstance(assigned_scope, dict):
            blockers.append(
                {
                    "code": "assigned_scope_missing",
                    "field": f"closures[{index}].assigned_scope",
                    "message": "Closure must include its assigned scope.",
                }
            )
            continue
        scope_id = assigned_scope.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id.strip():
            blockers.append(
                {
                    "code": "assigned_scope_id_missing",
                    "field": f"closures[{index}].assigned_scope.scope_id",
                    "message": "assigned_scope must include scope_id.",
                }
            )
            continue
        scope_ids.append(scope_id)
        object_ids = assigned_scope.get("object_ids")
        if isinstance(object_ids, list):
            scope_object_ids[scope_id] = {str(item) for item in object_ids}
        if closure.get("status") != "complete":
            blockers.append(
                {
                    "code": "scoped_closure_not_complete",
                    "field": f"closures[{index}].status",
                    "scope": scope_id,
                    "message": "Only complete scoped closures can enter review context.",
                }
            )
        normalized.append(closure)

    duplicate_closure_ids = sorted(
        closure_id for closure_id, count in Counter(closure_ids).items() if count > 1
    )
    duplicate_scope_ids = sorted(
        scope_id for scope_id, count in Counter(scope_ids).items() if count > 1
    )
    if duplicate_closure_ids:
        blockers.append(
            {
                "code": "duplicate_scoped_closure",
                "closure_ids": duplicate_closure_ids,
                "message": "Each scoped closure may be submitted only once.",
            }
        )
    if duplicate_scope_ids:
        blockers.append(
            {
                "code": "duplicate_assigned_scope",
                "scope_ids": duplicate_scope_ids,
                "message": "Each assigned scope may be closed by only one subagent output.",
            }
        )
    if expected_scope_ids:
        missing = sorted(set(expected_scope_ids) - set(scope_ids))
        if missing:
            blockers.append(
                {
                    "code": "missing_assigned_scope",
                    "scope_ids": missing,
                    "message": "Expected assigned scopes have no scoped closure output.",
                }
            )
    overlaps: list[JsonObject] = []
    seen: dict[str, str] = {}
    for scope_id, object_ids in scope_object_ids.items():
        for object_id in sorted(object_ids):
            previous = seen.get(object_id)
            if previous is not None and previous != scope_id:
                overlaps.append(
                    {
                        "object_id": object_id,
                        "scope_ids": sorted((previous, scope_id)),
                    }
                )
            seen[object_id] = scope_id
    if overlaps:
        blockers.append(
            {
                "code": "overlapping_assigned_scope",
                "overlaps": overlaps,
                "message": "Assigned scopes overlap on source object ids.",
            }
        )

    if blockers:
        return mechanical_feedback(
            feedback_type="subagent_closure",
            code="subagent_closure_incomplete",
            message="Subagent closure outputs are not mechanically ready for review.",
            source_hash=source_hash,
            blockers=blockers,
            suggested_actions=("Refresh, deduplicate, or rescope subagent closures.",),
        )
    return {
        "schema_version": CLOSURE_REVIEW_CONTEXT_V1,
        "status": "ok",
        "source_hash": source_hash,
        "context_profile": context_profile,
        "closure_count": len(normalized),
        "closures": normalized,
        "checks": [{"name": "subagent_closure_aggregation", "result": "ok"}],
        "warnings": [],
        "failure": None,
    }
