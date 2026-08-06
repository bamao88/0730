"""Independent validation gates for a compiled template artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from docfit.template.runtime.paths import task_file
from docfit.template.runtime.store import EvidenceStore
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json


def _verify_review_digest(review: JsonObject) -> None:
    digest = review.get("review_digest")
    body = {key: value for key, value in review.items() if key != "review_digest"}
    if digest != sha256_json(body):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The embedded review digest is invalid.",
        )

def _verify_registry_and_markers(
    spec: JsonObject,
    snapshot: JsonObject,
    *,
    task_root: Path,
) -> None:
    reference = spec.get("field_registry_ref")
    if not isinstance(reference, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The artifact spec has no valid Registry binding.",
        )
    registry_path = task_file(
        reference.get("path"),
        task_root=task_root,
        field="field_registry_ref.path",
        allowed_roots=("input",),
    )
    try:
        registry: Any = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry cannot be revalidated.",
        ) from error
    if (
        not isinstance(registry, dict)
        or reference.get("sha256") != sha256_file(registry_path)
        or reference.get("registry_id") != registry.get("registry_id")
        or reference.get("registry_version") != registry.get("registry_version")
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry changed after artifact compilation.",
        )
    raw_fields = registry.get("fields")
    if not isinstance(raw_fields, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry inventory is invalid.",
        )
    field_ids = {
        item.get("field_id")
        for item in raw_fields
        if isinstance(item, dict) and isinstance(item.get("field_id"), str)
    }
    controls = snapshot.get("content_controls")
    slots = spec.get("slots")
    fill_contract = spec.get("fill_contract")
    if (
        spec.get("marker_protocol") != "docfit-content-control-marker/v1"
        or not isinstance(controls, list)
        or not isinstance(slots, list)
        or not isinstance(fill_contract, dict)
        or not isinstance(fill_contract.get("slots"), list)
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="marker_protocol_mismatch",
            message="The artifact spec marker contract is invalid.",
        )
    contract_slots = {
        item.get("slot_id"): item
        for item in fill_contract["slots"]
        if isinstance(item, dict)
    }
    seen: set[str] = set()
    for raw_slot in slots:
        if not isinstance(raw_slot, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="marker_protocol_mismatch",
                message="A slot record is invalid.",
            )
        slot_id = raw_slot.get("slot_id")
        field_id = raw_slot.get("field_id")
        marker = raw_slot.get("marker")
        locator = raw_slot.get("artifact_locator")
        contract_slot = contract_slots.get(slot_id)
        if (
            not isinstance(slot_id, str)
            or slot_id in seen
            or field_id not in field_ids
            or marker != {"alias": field_id, "tag": slot_id}
            or not isinstance(locator, dict)
            or locator.get("type") != "content_control_tag"
            or locator.get("value") != slot_id
            or not isinstance(contract_slot, dict)
            or contract_slot.get("field_id") != field_id
            or contract_slot.get("locator") != locator
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="marker_protocol_mismatch",
                message="A slot marker or fill-contract mapping is inconsistent.",
            )
        matches = [
            item
            for item in controls
            if isinstance(item, dict)
            and item.get("alias") == field_id
            and item.get("tag") == slot_id
        ]
        if len(matches) != 1:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="slot_locator_not_unique",
                message="A content-control marker does not resolve exactly once.",
            )
        seen.add(slot_id)


def _verify_regions(spec: JsonObject, snapshot: JsonObject) -> None:
    objects = snapshot.get("objects")
    if not isinstance(objects, list):
        raise ToolFailure(
            status="error",
            origin="evidence",
            code="evidence_invalid",
            message="The final snapshot has no object inventory.",
        )
    by_id = {
        item.get("object_id"): item
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }
    protected = spec.get("protected_regions")
    remove = spec.get("remove_regions")
    if not isinstance(protected, list) or not isinstance(remove, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The region inventory is invalid.",
        )
    for item in protected:
        if not isinstance(item, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="protected_fingerprint_mismatch",
                message="A protected region is invalid.",
            )
        execution = item.get("execution_locator")
        locator = item.get("artifact_locator")
        if not isinstance(execution, dict) or not isinstance(locator, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="protected_fingerprint_mismatch",
                message="A protected region lacks valid locators.",
            )
        object_id = execution.get("object_id")
        target = by_id.get(object_id) if isinstance(object_id, str) else None
        anchor = locator.get("left_anchor")
        occurrences = sum(
            1
            for candidate in objects
            if isinstance(candidate, dict)
            and candidate.get("kind") == "paragraph"
            and isinstance(candidate.get("text"), str)
            and isinstance(anchor, str)
            and anchor in candidate["text"]
        )
        if (
            not isinstance(target, dict)
            or target.get("expected_fingerprint") != execution.get("expected_fingerprint")
            or item.get("expected_fingerprint") != execution.get("expected_fingerprint")
            or occurrences != locator.get("expected_match_count")
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="protected_fingerprint_mismatch",
                message="A protected region no longer resolves to its expected fingerprint.",
            )
    all_text = "\n".join(
        item.get("text", "") for item in objects if isinstance(item, dict)
    )
    for item in remove:
        if (
            isinstance(item, dict)
            and isinstance(item.get("forbidden_text"), str)
            and item["forbidden_text"] in all_text
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="remove_residue_present",
                message="A forbidden remove-region residue remains in the final template.",
            )


def _verify_mutation_lineage(
    spec: JsonObject,
    *,
    store: EvidenceStore,
    final_snapshot_ref: str,
) -> None:
    lineage = spec.get("mutation_lineage")
    if not isinstance(lineage, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_spec",
            message="The mutation lineage has an invalid shape.",
        )
    previous_after: str | None = None
    for index, item in enumerate(lineage, start=1):
        if not isinstance(item, dict) or item.get("sequence") != index:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="mutation_lineage_gap",
                message="Mutation lineage sequence numbers are invalid.",
            )
        mutation = store.resolve(item.get("mutation_ref"), expected_kind="mutation")
        comparison = store.resolve(item.get("comparison_ref"), expected_kind="comparison")
        before_ref = item.get("before_snapshot_ref")
        after_ref = item.get("after_snapshot_ref")
        if (
            mutation.get("before_snapshot_ref") != before_ref
            or mutation.get("after_snapshot_ref") != after_ref
            or comparison.get("mutation_ref") != item.get("mutation_ref")
            or comparison.get("before_snapshot_ref") != before_ref
            or comparison.get("after_snapshot_ref") != after_ref
            or comparison.get("machine_blockers") != []
            or comparison.get("unexpected_changes") != []
            or (previous_after is not None and previous_after != before_ref)
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="mutation_lineage_gap",
                message="Mutation lineage failed independent evidence validation.",
            )
        previous_after = after_ref if isinstance(after_ref, str) else None
    if lineage and previous_after != final_snapshot_ref:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="mutation_lineage_gap",
            message="Mutation lineage does not reach the final snapshot.",
        )
