"""Evidence-bound review and mutation-lineage checks for artifact compilation."""

from __future__ import annotations

from docfit.template.decision_contracts import decision_objects
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json


def validate_review(
    decisions: JsonObject,
    *,
    snapshot: JsonObject,
    store: EvidenceStore,
) -> JsonObject:
    review = decisions.get("final_review")
    if not isinstance(review, dict):
        raise ToolFailure(
            status="needs_input", origin="request", code="review_page_missing",
            message="A final candidate review is required.",
        )
    comparison = store.resolve(review.get("comparison_ref"), expected_kind="comparison")
    if (
        review.get("final_snapshot_ref") != decisions.get("final_snapshot_ref")
        or comparison.get("final_snapshot_ref") != decisions.get("final_snapshot_ref")
        or comparison.get("document_sha256") != snapshot.get("document_sha256")
        or comparison.get("visual_level") != "candidate_verification"
        or review.get("visual_level") != "candidate_verification"
    ):
        raise ToolFailure(
            status="needs_input", origin="request",
            code="final_comparison_not_candidate_verification",
            message="The final comparison does not bind the exact candidate snapshot.",
        )
    required = decision_objects(comparison.get("required_images"), "required_images")
    dispositions = decision_objects(review.get("image_dispositions"), "image_dispositions")
    by_id = {item.get("required_image_id"): item for item in dispositions}
    missing = [
        item.get("required_image_id")
        for item in required
        if item.get("required_image_id") not in by_id
    ]
    if missing or review.get("page_count") != len(required):
        raise ToolFailure(
            status="needs_input", origin="request",
            code="required_image_without_disposition",
            message="Every final page requires an explicit Agent disposition.",
        )
    if any(
        by_id[item.get("required_image_id")].get("disposition") != "accepted"
        for item in required
    ):
        raise ToolFailure(
            status="needs_input", origin="request", code="blocking_finding_present",
            message="A required image was rejected by the final review.",
        )
    blockers = comparison.get("machine_blockers")
    if not isinstance(blockers, list) or blockers:
        raise ToolFailure(
            status="needs_input", origin="request", code="blocking_finding_present",
            message="The final comparison contains an unresolved machine blocker.",
        )
    record: JsonObject = {
        "schema_version": 1,
        "final_snapshot_ref": decisions.get("final_snapshot_ref"),
        "comparison_ref": review.get("comparison_ref"),
        "render_ref": comparison.get("render_ref"),
        "document_sha256": snapshot.get("document_sha256"),
        "visual_level": "candidate_verification",
        "page_count": len(required),
        "required_images": [
            {key: value for key, value in item.items() if key != "render_page_path"}
            for item in required
        ],
        "image_dispositions": dispositions,
        "finding_dispositions": review.get("finding_dispositions", []),
        "machine_blockers": [],
    }
    record["review_digest"] = sha256_json(record)
    return record


def validate_mutation_lineage(
    decisions: JsonObject,
    *,
    store: EvidenceStore,
) -> list[JsonObject]:
    chain = decision_objects(
        decisions.get("mutation_evidence_chain"), "mutation_evidence_chain"
    )
    if not chain:
        return []
    previous_after: str | None = None
    normalized: list[JsonObject] = []
    for index, item in enumerate(chain, start=1):
        if item.get("sequence") != index:
            raise ToolFailure(
                status="needs_input", origin="request", code="mutation_lineage_gap",
                message="Mutation lineage sequence numbers must be contiguous.",
            )
        mutation = store.resolve(item.get("mutation_ref"), expected_kind="mutation")
        comparison = store.resolve(item.get("comparison_ref"), expected_kind="comparison")
        before_ref = item.get("before_snapshot_ref")
        after_ref = item.get("after_snapshot_ref")
        if (
            mutation.get("before_snapshot_ref") != before_ref
            or mutation.get("after_snapshot_ref") != after_ref
            or comparison.get("review_mode") != "mutation_review"
            or comparison.get("mutation_ref") != item.get("mutation_ref")
            or comparison.get("before_snapshot_ref") != before_ref
            or comparison.get("after_snapshot_ref") != after_ref
            or comparison.get("machine_blockers") != []
            or comparison.get("unexpected_changes") != []
            or (previous_after is not None and previous_after != before_ref)
        ):
            raise ToolFailure(
                status="needs_input", origin="request", code="mutation_lineage_gap",
                message="Mutation lineage evidence is discontinuous or contains blockers.",
            )
        previous_after = after_ref if isinstance(after_ref, str) else None
        normalized.append(item)
    if previous_after != decisions.get("final_snapshot_ref"):
        raise ToolFailure(
            status="needs_input", origin="request", code="mutation_lineage_gap",
            message="Mutation lineage does not reach the final snapshot.",
        )
    return normalized
