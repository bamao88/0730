from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docfit.template.judgment_shape import (
    mechanical_feedback,
    validate_ordered_semantic_parts,
)
from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.unit_source import (
    entry_unit_contexts,
    validate_inventory_partition,
    validate_unit_proof,
)
from docfit.tools.runtime import sha256_json

JsonObject = dict[str, Any]

SEMANTIC_BATCH_MANIFEST_SCHEMA = "docfit-semantic-batch-manifest/v1"
SEMANTIC_BATCH_LEDGER_SCHEMA = "docfit-semantic-batch-candidate-ledger/v1"
DEFAULT_SEMANTIC_BATCH_ENTRY_LIMIT = 64


@dataclass(frozen=True, slots=True)
class SemanticBatch:
    batch_id: str
    batch_index: int
    unit_id: str
    unit_name: str
    source_entry_ids: tuple[str, ...]

    def to_json(self) -> JsonObject:
        return {
            "batch_id": self.batch_id,
            "batch_index": self.batch_index,
            "unit_id": self.unit_id,
            "unit_name": self.unit_name,
            "source_entry_ids": list(self.source_entry_ids),
            "source_entry_count": len(self.source_entry_ids),
        }


@dataclass(frozen=True, slots=True)
class SemanticBatchManifest:
    source_sha256: str
    source_inventory_digest: str
    unit_projection_digest: str
    field_vocabulary_digest: str
    max_entries_per_batch: int
    required_source_entry_ids: tuple[str, ...]
    batches: tuple[SemanticBatch, ...]
    manifest_digest: str

    def to_json(self) -> JsonObject:
        return {
            "schema_version": SEMANTIC_BATCH_MANIFEST_SCHEMA,
            "source_sha256": self.source_sha256,
            "source_inventory_digest": self.source_inventory_digest,
            "unit_projection_digest": self.unit_projection_digest,
            "field_vocabulary_digest": self.field_vocabulary_digest,
            "max_entries_per_batch": self.max_entries_per_batch,
            "required_source_entry_ids": list(self.required_source_entry_ids),
            "required_source_entry_count": len(self.required_source_entry_ids),
            "batches": [batch.to_json() for batch in self.batches],
            "batch_count": len(self.batches),
            "manifest_digest": self.manifest_digest,
        }


@dataclass(frozen=True, slots=True)
class SemanticBatchCandidate:
    batch_id: str
    summary: str
    semantic_judgments: tuple[JsonObject, ...]
    candidate_digest: str

    def to_json(self) -> JsonObject:
        return {
            "batch_id": self.batch_id,
            "summary": self.summary,
            "semantic_judgments": [dict(judgment) for judgment in self.semantic_judgments],
            "candidate_digest": self.candidate_digest,
        }


@dataclass(frozen=True, slots=True)
class SemanticBatchCandidateLedger:
    manifest_digest: str
    source_sha256: str
    source_inventory_digest: str
    unit_projection_digest: str
    field_vocabulary_digest: str
    candidates: tuple[SemanticBatchCandidate, ...] = ()

    @classmethod
    def empty(cls, manifest: SemanticBatchManifest) -> SemanticBatchCandidateLedger:
        return cls(
            manifest_digest=manifest.manifest_digest,
            source_sha256=manifest.source_sha256,
            source_inventory_digest=manifest.source_inventory_digest,
            unit_projection_digest=manifest.unit_projection_digest,
            field_vocabulary_digest=manifest.field_vocabulary_digest,
        )

    def to_json(self) -> JsonObject:
        payload: JsonObject = {
            "schema_version": SEMANTIC_BATCH_LEDGER_SCHEMA,
            "manifest_digest": self.manifest_digest,
            "source_sha256": self.source_sha256,
            "source_inventory_digest": self.source_inventory_digest,
            "unit_projection_digest": self.unit_projection_digest,
            "field_vocabulary_digest": self.field_vocabulary_digest,
            "candidates": [candidate.to_json() for candidate in self.candidates],
            "candidate_count": len(self.candidates),
        }
        payload["ledger_digest"] = sha256_json(payload)
        return payload

    @classmethod
    def from_json(
        cls,
        value: object,
        *,
        manifest: SemanticBatchManifest,
        allowed_field_ids: tuple[str, ...],
    ) -> SemanticBatchCandidateLedger:
        if not isinstance(value, dict):
            raise ValueError("semantic batch candidate ledger must be an object.")
        expected_keys = {
            "schema_version",
            "manifest_digest",
            "source_sha256",
            "source_inventory_digest",
            "unit_projection_digest",
            "field_vocabulary_digest",
            "candidates",
            "candidate_count",
            "ledger_digest",
        }
        if set(value) != expected_keys:
            raise ValueError("semantic batch candidate ledger shape is unsupported.")
        if value.get("schema_version") != SEMANTIC_BATCH_LEDGER_SCHEMA:
            raise ValueError("semantic batch candidate ledger schema is unsupported.")
        raw_ledger_digest = _non_empty_string(value.get("ledger_digest"), "ledger_digest")
        unsigned_payload = {key: item for key, item in value.items() if key != "ledger_digest"}
        if raw_ledger_digest != sha256_json(unsigned_payload):
            raise ValueError("semantic batch candidate ledger digest is invalid.")
        bindings = {
            "manifest_digest": manifest.manifest_digest,
            "source_sha256": manifest.source_sha256,
            "source_inventory_digest": manifest.source_inventory_digest,
            "unit_projection_digest": manifest.unit_projection_digest,
            "field_vocabulary_digest": manifest.field_vocabulary_digest,
        }
        if any(value.get(key) != expected for key, expected in bindings.items()):
            raise ValueError("semantic batch candidate ledger is stale.")
        raw_candidates = value.get("candidates")
        if not isinstance(raw_candidates, list):
            raise ValueError("semantic batch candidate ledger candidates must be an array.")
        if value.get("candidate_count") != len(raw_candidates):
            raise ValueError("semantic batch candidate ledger count is invalid.")
        ledger = cls.empty(manifest)
        serialized_batch_ids: list[str] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict) or set(raw_candidate) != {
                "batch_id",
                "summary",
                "semantic_judgments",
                "candidate_digest",
            }:
                raise ValueError("semantic batch candidate shape is unsupported.")
            batch_id = _non_empty_string(raw_candidate.get("batch_id"), "batch_id")
            if batch_id in serialized_batch_ids:
                raise ValueError("semantic batch candidate batch_id values must be unique.")
            serialized_batch_ids.append(batch_id)
            ledger = record_semantic_batch_candidate(
                manifest=manifest,
                ledger=ledger,
                batch_id=batch_id,
                structured_output={
                    "status": "complete",
                    "summary": raw_candidate.get("summary"),
                    "semantic_judgments": raw_candidate.get("semantic_judgments"),
                },
                allowed_field_ids=allowed_field_ids,
            )
            restored = next(item for item in ledger.candidates if item.batch_id == batch_id)
            if raw_candidate.get("candidate_digest") != restored.candidate_digest:
                raise ValueError("semantic batch candidate digest is invalid.")
        if [candidate.batch_id for candidate in ledger.candidates] != serialized_batch_ids:
            raise ValueError("semantic batch candidates are not in manifest order.")
        if ledger.to_json() != value:
            raise ValueError("semantic batch candidate ledger does not match current bindings.")
        return ledger


class SemanticBatchCandidateError(ValueError):
    def __init__(self, feedback: JsonObject) -> None:
        self.feedback = feedback
        failure = feedback.get("failure")
        message = (
            failure.get("message")
            if isinstance(failure, dict) and isinstance(failure.get("message"), str)
            else "Semantic batch candidate is invalid."
        )
        super().__init__(message)


def validate_persisted_semantic_batch_manifest(
    value: object,
    *,
    expected: SemanticBatchManifest,
) -> SemanticBatchManifest:
    if value != expected.to_json():
        raise ValueError("persisted semantic batch manifest is stale or unsupported.")
    return expected


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip()


def _manifest_payload(
    *,
    source_sha256: str,
    source_inventory_digest: str,
    unit_projection_digest: str,
    field_vocabulary_digest: str,
    max_entries_per_batch: int,
    required_source_entry_ids: tuple[str, ...],
    batches: tuple[SemanticBatch, ...],
) -> JsonObject:
    return {
        "schema_version": SEMANTIC_BATCH_MANIFEST_SCHEMA,
        "source_sha256": source_sha256,
        "source_inventory_digest": source_inventory_digest,
        "unit_projection_digest": unit_projection_digest,
        "field_vocabulary_digest": field_vocabulary_digest,
        "max_entries_per_batch": max_entries_per_batch,
        "required_source_entry_ids": list(required_source_entry_ids),
        "required_source_entry_count": len(required_source_entry_ids),
        "batches": [batch.to_json() for batch in batches],
        "batch_count": len(batches),
    }


def _paragraph_carrier(locator: str) -> str:
    paragraph_start = locator.rfind("/p[")
    if paragraph_start < 0:
        return locator
    paragraph_end = locator.find("]", paragraph_start)
    return locator if paragraph_end < 0 else locator[: paragraph_end + 1]


def _carrier_connected_groups(
    source_entry_ids: tuple[str, ...],
    *,
    entry_locators: dict[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    """Keep source entries sharing one Word carrier in the same semantic batch."""
    parent = list(range(len(source_entry_ids)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    owner_by_carrier: dict[str, int] = {}
    for index, source_entry_id in enumerate(source_entry_ids):
        carriers = {_paragraph_carrier(locator) for locator in entry_locators[source_entry_id]}
        for carrier in carriers:
            owner = owner_by_carrier.setdefault(carrier, index)
            union(owner, index)

    groups_by_root: dict[int, list[str]] = {}
    for index, source_entry_id in enumerate(source_entry_ids):
        groups_by_root.setdefault(find(index), []).append(source_entry_id)
    return tuple(tuple(group) for group in groups_by_root.values())


def _pack_carrier_groups(
    groups: tuple[tuple[str, ...], ...],
    *,
    max_entries_per_batch: int,
) -> tuple[tuple[str, ...], ...]:
    batches: list[tuple[str, ...]] = []
    current: list[str] = []
    for group in groups:
        if len(group) > max_entries_per_batch:
            raise ValueError("one Word carrier exceeds the semantic batch entry limit.")
        if current and len(current) + len(group) > max_entries_per_batch:
            batches.append(tuple(current))
            current = []
        current.extend(group)
    if current:
        batches.append(tuple(current))
    return tuple(batches)


def build_semantic_batch_manifest(
    *,
    inventory: JsonObject,
    checkpoint: JsonObject,
    max_entries_per_batch: int = DEFAULT_SEMANTIC_BATCH_ENTRY_LIMIT,
) -> SemanticBatchManifest:
    """Assign every accepted-unit source entry to one bounded semantic batch."""
    if (
        not isinstance(max_entries_per_batch, int)
        or isinstance(max_entries_per_batch, bool)
        or max_entries_per_batch < 1
    ):
        raise ValueError("max_entries_per_batch must be a positive integer.")

    validate_inventory_partition(inventory)
    if inventory["unit_boundary_proof"]["resolved_units"] != checkpoint.get("resolved_units"):
        raise ValueError("Semantic batch checkpoint differs from the accepted partition.")
    canonical = CanonicalSourceInventory.from_json(inventory.get("canonical_source_inventory"))
    validate_unit_proof(canonical, checkpoint)
    source_sha256 = _non_empty_string(checkpoint.get("source_hash"), "source_hash")
    if canonical.source_snapshot_sha256 != source_sha256:
        raise ValueError("semantic batch inventory is bound to another source.")
    if inventory.get("document_sha256") != source_sha256:
        raise ValueError("semantic batch object inventory document hash is stale.")

    raw_units = checkpoint.get("resolved_units")
    if not isinstance(raw_units, list) or not raw_units:
        raise ValueError("semantic batches require non-empty resolved_units.")
    units = [unit for unit in raw_units if isinstance(unit, dict)]
    if len(units) != len(raw_units):
        raise ValueError("resolved_units must contain only unit objects.")
    unit_projection_digest = sha256_json(units)
    if inventory.get("unit_projection_digest") != unit_projection_digest:
        raise ValueError("semantic batch unit projections are stale.")

    field_vocabulary_digest = _non_empty_string(
        inventory.get("field_vocabulary_digest"), "field_vocabulary_digest"
    )
    packets = inventory.get("unit_reading_packets")
    if not isinstance(packets, dict):
        raise ValueError("semantic batches require persisted unit_reading_packets.")

    canonical_ids = tuple(entry.source_entry_id for entry in canonical.source_entries)
    canonical_id_set = set(canonical_ids)
    entry_locators = {
        entry.source_entry_id: {item.locator for item in entry.provenance}
        for entry in canonical.source_entries
    }
    unit_packets: list[tuple[str, str, str | None, tuple[str, ...]]] = []
    seen_unit_ids: set[str] = set()
    for unit in units:
        unit_id = _non_empty_string(unit.get("unit_id"), "resolved_units[].unit_id")
        if unit_id in seen_unit_ids:
            raise ValueError("resolved_units must keep unique unit_id values.")
        seen_unit_ids.add(unit_id)
        unit_name = _non_empty_string(unit.get("unit_name", unit_id), "resolved_units[].unit_name")
        packet = packets.get(unit_id)
        if not isinstance(packet, dict):
            raise ValueError(f"semantic batch packet is missing for unit {unit_id}.")
        raw_entries = packet.get("source_entries")
        if not isinstance(raw_entries, list):
            raise ValueError(f"semantic batch packet {unit_id} lacks source_entries.")
        packet_ids: list[str] = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                raise ValueError(f"semantic batch packet {unit_id} contains an invalid entry.")
            source_entry_id = _non_empty_string(
                entry.get("source_entry_id"), "source_entries[].source_entry_id"
            )
            if source_entry_id not in canonical_id_set:
                raise ValueError(
                    f"semantic batch packet {unit_id} references an unknown source entry."
                )
            if source_entry_id not in packet_ids:
                packet_ids.append(source_entry_id)
        expected_ids = [span["source_entry_id"] for span in unit["source_spans"]]
        if packet_ids != expected_ids:
            raise ValueError("Semantic packet entries do not match the accepted unit range.")
        canonical_by_id = {entry.source_entry_id: entry for entry in canonical.source_entries}
        for entry in raw_entries:
            entry_id = entry["source_entry_id"]
            if entry.get("text") != canonical_by_id[entry_id].text:
                raise ValueError("Semantic packets must retain complete source entry text.")
            if entry.get("unit_contexts") != entry_unit_contexts(units, entry_id):
                raise ValueError("Semantic packets must include all cross-unit contexts.")
        unit_packets.append(
            (
                unit_id,
                unit_name,
                unit.get("start_locator") if isinstance(unit.get("start_locator"), str) else None,
                tuple(packet_ids),
            )
        )

    memberships: dict[str, list[int]] = {source_entry_id: [] for source_entry_id in canonical_ids}
    for unit_index, (_unit_id, _unit_name, _start_locator, projected_ids) in enumerate(
        unit_packets
    ):
        for source_entry_id in projected_ids:
            memberships[source_entry_id].append(unit_index)

    owner_by_source_entry_id: dict[str, int] = {}
    for source_entry_id, candidate_indexes in memberships.items():
        if not candidate_indexes:
            raise ValueError("Semantic packets omitted a canonical source entry.")
        owner_by_source_entry_id[source_entry_id] = min(
            candidate_indexes,
            key=lambda unit_index: (
                0 if unit_packets[unit_index][2] in entry_locators[source_entry_id] else 1,
                len(unit_packets[unit_index][3]),
                unit_index,
            ),
        )

    raw_batches: list[tuple[str, str, tuple[str, ...]]] = []
    for unit_index, (unit_id, unit_name, _start_locator, _packet_ids) in enumerate(unit_packets):
        unit_owned_ids = tuple(
            source_entry_id
            for source_entry_id in canonical_ids
            if owner_by_source_entry_id.get(source_entry_id) == unit_index
        )
        carrier_groups = _carrier_connected_groups(
            unit_owned_ids,
            entry_locators=entry_locators,
        )
        for source_entry_ids in _pack_carrier_groups(
            carrier_groups,
            max_entries_per_batch=max_entries_per_batch,
        ):
            raw_batches.append(
                (
                    unit_id,
                    unit_name,
                    source_entry_ids,
                )
            )

    required_source_entry_ids = tuple(
        source_entry_id
        for source_entry_id in canonical_ids
        if source_entry_id in owner_by_source_entry_id
    )
    if not required_source_entry_ids:
        raise ValueError("semantic batch manifest has no accepted-unit source entries.")

    batches = tuple(
        SemanticBatch(
            batch_id=(
                f"semantic-batch-{index:04d}-"
                f"{sha256_json({'unit_id': unit_id, 'source_entry_ids': source_entry_ids})[:8]}"
            ),
            batch_index=index,
            unit_id=unit_id,
            unit_name=unit_name,
            source_entry_ids=source_entry_ids,
        )
        for index, (unit_id, unit_name, source_entry_ids) in enumerate(raw_batches, start=1)
    )
    payload = _manifest_payload(
        source_sha256=source_sha256,
        source_inventory_digest=canonical.inventory_digest,
        unit_projection_digest=unit_projection_digest,
        field_vocabulary_digest=field_vocabulary_digest,
        max_entries_per_batch=max_entries_per_batch,
        required_source_entry_ids=required_source_entry_ids,
        batches=batches,
    )
    return SemanticBatchManifest(
        source_sha256=source_sha256,
        source_inventory_digest=canonical.inventory_digest,
        unit_projection_digest=unit_projection_digest,
        field_vocabulary_digest=field_vocabulary_digest,
        max_entries_per_batch=max_entries_per_batch,
        required_source_entry_ids=required_source_entry_ids,
        batches=batches,
        manifest_digest=sha256_json(payload),
    )


def _batch_by_id(
    manifest: SemanticBatchManifest,
    batch_id: str,
) -> SemanticBatch:
    for batch in manifest.batches:
        if batch.batch_id == batch_id:
            return batch
    raise ValueError("semantic batch candidate references an unknown batch_id.")


def semantic_batch_candidate_feedback(
    *,
    batch: SemanticBatch,
    structured_output: object,
    allowed_field_ids: tuple[str, ...],
    expected_source_entry_ids: tuple[str, ...] | None = None,
) -> JsonObject | None:
    if not isinstance(structured_output, dict) or structured_output.get("status") != "complete":
        return mechanical_feedback(
            feedback_type="semantic_batch_candidate",
            code="semantic_batch_status_incomplete",
            message="A semantic batch candidate must return status=complete.",
            blockers=[
                {
                    "code": "semantic_batch_status_incomplete",
                    "field": "status",
                    "batch_id": batch.batch_id,
                    "unit_id": batch.unit_id,
                    "message": "Return status=complete or stop the whole stage as needs_input.",
                }
            ],
            suggested_actions=("Return one complete semantic batch candidate.",),
        )
    if "revision_request" in structured_output:
        return mechanical_feedback(
            feedback_type="semantic_batch_candidate",
            code="semantic_revision_request_mixed",
            message="Submit either judgments or a related revision request, not both.",
            blockers=[
                {
                    "code": "semantic_revision_request_mixed",
                    "source_entry_ids": list(batch.source_entry_ids),
                    "message": "Use expand_revision with no judgments for related changes.",
                }
            ],
            suggested_actions=("Choose complete judgments or an expand_revision request.",),
        )
    judgments = structured_output.get("semantic_judgments")
    shape_feedback = validate_ordered_semantic_parts(
        judgments,
        allowed_field_ids=allowed_field_ids,
        source_entry_ids=batch.source_entry_ids,
    )
    if shape_feedback.get("status") != "ok":
        return shape_feedback
    assert isinstance(judgments, list)
    required_source_entry_ids = (
        batch.source_entry_ids if expected_source_entry_ids is None else expected_source_entry_ids
    )
    submitted_id_values: list[str] = []
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        source_entry_id = judgment.get("source_entry_id")
        if isinstance(source_entry_id, str):
            submitted_id_values.append(source_entry_id)
    submitted_ids = tuple(submitted_id_values)
    if submitted_ids == required_source_entry_ids:
        return None
    submitted_set = set(submitted_ids)
    required_set = set(required_source_entry_ids)
    missing = [item for item in required_source_entry_ids if item not in submitted_set]
    unexpected = [item for item in submitted_ids if item not in required_set]
    duplicate = sorted({item for item in submitted_ids if submitted_ids.count(item) > 1})
    blockers: list[JsonObject] = []
    if missing:
        blockers.append(
            {
                "code": "semantic_batch_entries_missing",
                "batch_id": batch.batch_id,
                "unit_id": batch.unit_id,
                "source_entry_ids": missing,
                "message": "The batch omitted required source entries.",
            }
        )
    if unexpected:
        blockers.append(
            {
                "code": "semantic_batch_entries_unexpected",
                "batch_id": batch.batch_id,
                "unit_id": batch.unit_id,
                "source_entry_ids": unexpected,
                "message": "The batch included source entries owned by another batch.",
            }
        )
    if duplicate:
        blockers.append(
            {
                "code": "semantic_batch_entries_duplicate",
                "batch_id": batch.batch_id,
                "unit_id": batch.unit_id,
                "source_entry_ids": duplicate,
                "message": "The batch submitted the same source entry more than once.",
            }
        )
    if not blockers:
        blockers.append(
            {
                "code": "semantic_batch_entries_out_of_order",
                "batch_id": batch.batch_id,
                "unit_id": batch.unit_id,
                "source_entry_ids": list(submitted_ids),
                "message": "The batch must keep its manifest source-entry order.",
            }
        )
    return mechanical_feedback(
        feedback_type="semantic_batch_candidate",
        code="semantic_batch_coverage_invalid",
        message="Semantic batch coverage must exactly match its manifest entry list.",
        blockers=blockers,
        suggested_actions=(
            "Return exactly the listed source_entry_id judgments in manifest order.",
        ),
    )


def record_semantic_batch_candidate(
    *,
    manifest: SemanticBatchManifest,
    ledger: SemanticBatchCandidateLedger,
    batch_id: str,
    structured_output: object,
    allowed_field_ids: tuple[str, ...],
    editable_source_entry_ids: tuple[str, ...] | None = None,
) -> SemanticBatchCandidateLedger:
    if (
        ledger.manifest_digest != manifest.manifest_digest
        or ledger.source_sha256 != manifest.source_sha256
        or ledger.source_inventory_digest != manifest.source_inventory_digest
        or ledger.unit_projection_digest != manifest.unit_projection_digest
        or ledger.field_vocabulary_digest != manifest.field_vocabulary_digest
    ):
        raise ValueError("semantic batch candidate ledger is stale.")
    batch = _batch_by_id(manifest, batch_id)
    previous_candidates = {candidate.batch_id: candidate for candidate in ledger.candidates}
    previous_candidate = previous_candidates.get(batch.batch_id)
    expected_source_entry_ids: tuple[str, ...] | None = None
    if editable_source_entry_ids is not None:
        editable_ids = set(editable_source_entry_ids)
        if (
            previous_candidate is None
            or not editable_ids
            or len(editable_ids) != len(editable_source_entry_ids)
            or not editable_ids.issubset(batch.source_entry_ids)
        ):
            raise ValueError("semantic batch revision scope is invalid.")
        expected_source_entry_ids = tuple(
            source_entry_id
            for source_entry_id in batch.source_entry_ids
            if source_entry_id in editable_ids
        )
    feedback = semantic_batch_candidate_feedback(
        batch=batch,
        structured_output=structured_output,
        allowed_field_ids=allowed_field_ids,
        expected_source_entry_ids=expected_source_entry_ids,
    )
    if feedback is not None:
        raise SemanticBatchCandidateError(feedback)
    assert isinstance(structured_output, dict)
    summary = _non_empty_string(structured_output.get("summary"), "summary")
    raw_judgments = structured_output.get("semantic_judgments")
    assert isinstance(raw_judgments, list)
    judgments = tuple(dict(judgment) for judgment in raw_judgments if isinstance(judgment, dict))
    if editable_source_entry_ids is not None:
        assert previous_candidate is not None
        assert expected_source_entry_ids is not None
        previous_by_id = {
            str(judgment["source_entry_id"]): judgment
            for judgment in previous_candidate.semantic_judgments
        }
        revised_by_id = {str(judgment["source_entry_id"]): judgment for judgment in judgments}
        judgments = tuple(
            dict(revised_by_id[source_entry_id])
            if source_entry_id in revised_by_id
            else dict(previous_by_id[source_entry_id])
            for source_entry_id in batch.source_entry_ids
        )
        summary = previous_candidate.summary
    candidate_payload = {
        "batch_id": batch.batch_id,
        "manifest_digest": manifest.manifest_digest,
        "source_entry_ids": list(batch.source_entry_ids),
        "summary": summary,
        "semantic_judgments": list(judgments),
    }
    candidate = SemanticBatchCandidate(
        batch_id=batch.batch_id,
        summary=summary,
        semantic_judgments=judgments,
        candidate_digest=sha256_json(candidate_payload),
    )
    by_id = previous_candidates
    by_id[batch.batch_id] = candidate
    ordered_candidates = tuple(
        by_id[batch_item.batch_id]
        for batch_item in manifest.batches
        if batch_item.batch_id in by_id
    )
    return SemanticBatchCandidateLedger(
        manifest_digest=ledger.manifest_digest,
        source_sha256=ledger.source_sha256,
        source_inventory_digest=ledger.source_inventory_digest,
        unit_projection_digest=ledger.unit_projection_digest,
        field_vocabulary_digest=ledger.field_vocabulary_digest,
        candidates=ordered_candidates,
    )


def aggregate_semantic_batch_candidates(
    *,
    manifest: SemanticBatchManifest,
    ledger: SemanticBatchCandidateLedger,
) -> JsonObject:
    if ledger.manifest_digest != manifest.manifest_digest:
        raise ValueError("semantic batch candidate ledger is stale.")
    candidates = {candidate.batch_id: candidate for candidate in ledger.candidates}
    missing_batches = [
        batch.batch_id for batch in manifest.batches if batch.batch_id not in candidates
    ]
    if missing_batches:
        raise ValueError("semantic batch candidate ledger is incomplete.")
    judgment_by_source_entry_id: dict[str, JsonObject] = {}
    summaries: list[str] = []
    for batch in manifest.batches:
        candidate = candidates[batch.batch_id]
        summaries.append(candidate.summary)
        for judgment in candidate.semantic_judgments:
            source_entry_id = judgment.get("source_entry_id")
            if not isinstance(source_entry_id, str):
                raise ValueError("semantic batch candidate lost its source_entry_id.")
            if source_entry_id in judgment_by_source_entry_id:
                raise ValueError("semantic batch candidates overlap.")
            judgment_by_source_entry_id[source_entry_id] = dict(judgment)
    if set(judgment_by_source_entry_id) != set(manifest.required_source_entry_ids):
        raise ValueError("semantic batch candidate coverage is incomplete.")
    return {
        "status": "complete",
        "summary": " | ".join(summaries),
        "semantic_judgments": [
            judgment_by_source_entry_id[source_entry_id]
            for source_entry_id in manifest.required_source_entry_ids
        ],
    }


def semantic_batch_ids_for_feedback(
    *,
    manifest: SemanticBatchManifest,
    feedback: object,
) -> tuple[str, ...]:
    """Map global Harness blockers to candidate batches, or reject ambiguous feedback."""
    if not isinstance(feedback, dict):
        raise ValueError("semantic batch feedback must be an object.")
    raw_blockers = feedback.get("blockers")
    if not isinstance(raw_blockers, list) or not raw_blockers:
        raise ValueError("semantic batch feedback has no routable blockers.")
    affected_source_entry_ids = set(
        semantic_source_entry_ids_for_feedback(manifest=manifest, feedback=feedback)
    )
    affected_batch_ids = {
        batch.batch_id
        for batch in manifest.batches
        if affected_source_entry_ids.intersection(batch.source_entry_ids)
    }
    if not affected_batch_ids:
        raise ValueError("semantic batch feedback cannot be mapped to a batch.")
    return tuple(
        batch.batch_id for batch in manifest.batches if batch.batch_id in affected_batch_ids
    )


def semantic_source_entry_ids_for_feedback(
    *,
    manifest: SemanticBatchManifest,
    feedback: object,
) -> tuple[str, ...]:
    """Return canonical source entries named by routable global feedback."""
    if not isinstance(feedback, dict):
        raise ValueError("semantic batch feedback must be an object.")
    raw_blockers = feedback.get("blockers")
    if not isinstance(raw_blockers, list) or not raw_blockers:
        raise ValueError("semantic batch feedback has no routable blockers.")
    required_ids = set(manifest.required_source_entry_ids)
    affected_source_entry_ids: set[str] = set()
    for blocker in raw_blockers:
        if not isinstance(blocker, dict):
            raise ValueError("semantic batch feedback contains an invalid blocker.")
        source_entry_id = blocker.get("source_entry_id")
        if isinstance(source_entry_id, str) and source_entry_id.strip():
            affected_source_entry_ids.add(source_entry_id.strip())
        source_entry_ids = blocker.get("source_entry_ids")
        if isinstance(source_entry_ids, list):
            affected_source_entry_ids.update(
                item.strip() for item in source_entry_ids if isinstance(item, str) and item.strip()
            )
    if not affected_source_entry_ids:
        raise ValueError("semantic batch feedback cannot be mapped to source entries.")
    unknown_ids = affected_source_entry_ids - required_ids
    if unknown_ids:
        raise ValueError("semantic batch feedback references unknown source entries.")
    return tuple(
        source_entry_id
        for source_entry_id in manifest.required_source_entry_ids
        if source_entry_id in affected_source_entry_ids
    )


def invalidate_semantic_batch_candidates(
    *,
    manifest: SemanticBatchManifest,
    ledger: SemanticBatchCandidateLedger,
    batch_ids: tuple[str, ...],
) -> SemanticBatchCandidateLedger:
    if ledger.manifest_digest != manifest.manifest_digest:
        raise ValueError("semantic batch candidate ledger is stale.")
    known_batch_ids = {batch.batch_id for batch in manifest.batches}
    invalidated_ids = set(batch_ids)
    if not invalidated_ids or not invalidated_ids.issubset(known_batch_ids):
        raise ValueError("semantic batch invalidation references unknown batches.")
    return SemanticBatchCandidateLedger(
        manifest_digest=ledger.manifest_digest,
        source_sha256=ledger.source_sha256,
        source_inventory_digest=ledger.source_inventory_digest,
        unit_projection_digest=ledger.unit_projection_digest,
        field_vocabulary_digest=ledger.field_vocabulary_digest,
        candidates=tuple(
            candidate
            for candidate in ledger.candidates
            if candidate.batch_id not in invalidated_ids
        ),
    )
