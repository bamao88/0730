"""Mechanical approval of related source-entry revision requests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from docfit.template.judgment_shape import mechanical_feedback
from docfit.template.semantic_batches import (
    SemanticBatch,
    SemanticBatchCandidateError,
    SemanticBatchCandidateLedger,
    SemanticBatchManifest,
)

JsonObject = dict[str, Any]

REVISION_REQUEST_SCHEMA: JsonObject = {
    "type": "object",
    "description": "Related existing source entries that also need semantic reconsideration.",
    "properties": {
        "source_entry_ids": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "reason": {
            "type": "string",
            "minLength": 1,
            "description": "Explain the semantic dependency requiring these entries to change.",
        },
    },
    "required": ["source_entry_ids", "reason"],
    "additionalProperties": False,
}


def _reject(batch: SemanticBatch, message: str) -> SemanticBatchCandidateError:
    return SemanticBatchCandidateError(
        mechanical_feedback(
            feedback_type="semantic_revision_request",
            code="semantic_revision_request_invalid",
            message=message,
            blockers=[
                {
                    "code": "semantic_revision_request_invalid",
                    "source_entry_ids": list(batch.source_entry_ids),
                    "message": message,
                }
            ],
            suggested_actions=("Revise the request using existing source entries and a reason.",),
        )
    )


def expand_revision_scopes(
    *,
    manifest: SemanticBatchManifest,
    ledger: SemanticBatchCandidateLedger,
    batch: SemanticBatch,
    editable_source_entry_ids: tuple[str, ...] | None,
    output: JsonObject,
    pending: dict[str, JsonObject],
    current_feedback: JsonObject | None,
) -> dict[str, JsonObject]:
    """Reopen only requested existing judgments; never infer or change their roles."""
    if editable_source_entry_ids is None or current_feedback is None:
        raise _reject(
            batch, "Related revisions can be requested only while revising prior judgments."
        )
    request = output.get("revision_request")
    if (
        output.get("status") != "expand_revision"
        or output.get("semantic_judgments") != []
        or set(output) - {"status", "summary", "semantic_judgments", "revision_request"}
        or not isinstance(output.get("summary"), str)
        or not output["summary"].strip()
        or not isinstance(request, dict)
        or set(request) != {"source_entry_ids", "reason"}
    ):
        raise _reject(batch, "Return expand_revision with a revision_request and no judgments.")
    ids, reason = request["source_entry_ids"], request["reason"]
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(item, str) or not item.strip() for item in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise _reject(
            batch, "List unique existing source_entry_ids and a nonempty semantic reason."
        )
    known = {
        judgment["source_entry_id"]
        for candidate in ledger.candidates
        for judgment in candidate.semantic_judgments
    }
    if not set(ids).issubset(known & set(manifest.required_source_entry_ids)):
        raise _reject(batch, "Requested entries must belong to this task and have prior judgments.")
    active = set(editable_source_entry_ids)
    for revision in pending.values():
        active.update(revision["editable_source_entry_ids"])
    if not set(ids) - active:
        raise _reject(batch, "These entries are already open for revision; submit their judgments.")
    related = set(ids) | set(editable_source_entry_ids)
    revisions: dict[str, JsonObject] = {}
    for target in manifest.batches:
        requested = related & set(target.source_entry_ids)
        if not requested:
            continue
        prior = pending.get(target.batch_id)
        if prior is not None:
            requested.update(prior["editable_source_entry_ids"])
        base_feedback: JsonObject = (
            current_feedback
            if target.batch_id == batch.batch_id
            else (
                prior["feedback"]
                if prior is not None
                else {"status": "needs_input", "blockers": []}
            )
        )
        feedback = deepcopy(base_feedback)
        feedback.setdefault("blockers", []).append(
            {
                "code": "related_semantic_revision_requested",
                "source_entry_ids": [
                    key for key in manifest.required_source_entry_ids if key in related
                ],
                "message": "Related source entries have been opened for semantic reconsideration.",
                "revision_reason": reason,
            }
        )
        revisions[target.batch_id] = {
            "editable_source_entry_ids": [
                key for key in target.source_entry_ids if key in requested
            ],
            "feedback": feedback,
        }
    return revisions
