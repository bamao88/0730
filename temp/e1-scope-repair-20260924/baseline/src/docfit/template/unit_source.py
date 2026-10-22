"""Immutable pre-query inventory and exact, half-open source unit partitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.template.source_entries import CanonicalSourceInventory
from docfit.template.source_spans import (
    SourceSpan,
    TextSourceExtent,
    WholeEntrySourceExtent,
    resolve_source_span,
)
from docfit.tools.runtime import JsonObject, ToolFailure, read_json, sha256_file, sha256_json

INITIAL_INVENTORY_PATH = Path("work/.docfit/initial-source-inventory.json")
UNIT_PROOF_SCHEMA = "docfit-unit-boundary-proof/v2"
INITIAL_INVENTORY_SCHEMA = "docfit-initial-source-inventory/v1"
BOUNDARY_POINT_SCHEMA: JsonObject = {
    "anyOf": [
        {
            "type": "object",
            "properties": {
                "source_entry_id": {"type": "string", "minLength": 1},
                "edge": {"type": "string", "enum": ["start", "end"]},
            },
            "required": ["source_entry_id", "edge"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "source_entry_id": {"type": "string", "minLength": 1},
                "edge": {"type": "string", "enum": ["split"]},
                "before": {"type": "string", "minLength": 1},
                "after": {"type": "string", "minLength": 1},
            },
            "required": ["source_entry_id", "edge", "before", "after"],
            "additionalProperties": False,
        },
    ],
}
_UNIT_KEYS = {"unit_id", "unit_name", "start_boundary", "end_boundary"}


class UnitPartitionError(ValueError):
    """Readable source-boundary diagnostics without changing the submitted proposal."""

    def __init__(self, blockers: list[JsonObject]) -> None:
        super().__init__(f"The unit proposal has {len(blockers)} boundary problem(s).")
        self.blockers = blockers


def _boundary_unit_view(unit: JsonObject) -> JsonObject:
    result = {key: unit[key] for key in ("unit_id", "unit_name")}
    for key in ("start_boundary", "end_boundary"):
        value = unit.get(key)
        if isinstance(value, dict):
            result[key] = {k: v for k, v in value.items()
                           if k in {"source_entry_id", "edge", "before", "after"}
                           and isinstance(v, str)}
    return result


def _boundary_range_text(
    canonical: CanonicalSourceInventory, start: tuple[int, int], end: tuple[int, int],
) -> list[JsonObject]:
    rows = []
    for index in range(start[0], min(end[0] + 1, len(canonical.source_entries))):
        if index == end[0] and end[1] == 0:
            break
        entry = canonical.source_entries[index]
        left = start[1] if index == start[0] else 0
        right = end[1] if index == end[0] else len(entry.text)
        rows.append({"source_entry_id": entry.source_entry_id, "entry_type": entry.entry_type,
                     "text": entry.text[left:right]})
    return rows


def _partition_bounds(
    canonical: CanonicalSourceInventory, units: list[JsonObject],
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    seen: set[str] = set()
    bounds: list[tuple[tuple[int, int] | None, tuple[int, int] | None]] = []
    blockers: list[JsonObject] = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict) or set(unit) != _UNIT_KEYS:
            raise ValueError("Units accept only unit_id, unit_name and source boundary points.")
        unit_id, name = unit["unit_id"], unit["unit_name"]
        if (
            not isinstance(unit_id, str) or not unit_id.strip()
            or unit_id != unit_id.strip() or unit_id in seen
        ):
            raise ValueError("Unit IDs must be nonempty and unique.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Unit names must be nonempty.")
        seen.add(unit_id)
        points: list[tuple[int, int] | None] = []
        for key in ("start_boundary", "end_boundary"):
            try:
                points.append(_point(unit[key], canonical))
            except ValueError as error:
                points.append(None)
                value = unit[key]
                entry_id = value.get("source_entry_id") if isinstance(value, dict) else None
                blockers.append({
                    "code": "unit_boundary_point_invalid", "unit_id": unit_id,
                    "field": f"units[{index}].{key}", "message": str(error),
                    "evidence_focus": "document_map",
                    "unit_boundaries": [_boundary_unit_view(unit)],
                    "source_entries": [
                        {"source_entry_id": e.source_entry_id, "entry_type": e.entry_type,
                         "text": e.text} for e in canonical.source_entries
                        if e.source_entry_id == entry_id
                    ],
                })
        bounds.append((points[0], points[1]))

    def issue(
        code: str, message: str, indexes: list[int],
        start: tuple[int, int] | None = None, end: tuple[int, int] | None = None,
    ) -> None:
        selected = [units[i] for i in indexes]
        blockers.append({
            "code": code, "message": message,
            "unit_ids": [u["unit_id"] for u in selected],
            "unit_boundaries": [_boundary_unit_view(u) for u in selected],
            "source_entries": _boundary_range_text(canonical, start, end)
            if start is not None and end is not None else [],
        })

    for index, (start, end) in enumerate(bounds):
        if start is None or end is None:
            continue
        if end <= start:
            issue("unit_boundary_empty_or_reversed",
                  f"Unit {index + 1} must end after it starts, including for empty source entries.",
                  [index])
        if index == 0:
            if start != (0, 0):
                issue("unit_boundary_gap", "The first unit starts after the listed source content.",
                      [index], (0, 0), start)
            continue
        previous_start, previous_end = bounds[index - 1]
        if previous_start is None or previous_end is None:
            continue
        if start < previous_start:
            issue("unit_boundary_order", f"Unit {index + 1} starts before unit {index}.",
                  [index - 1, index])
        elif start < previous_end and end > start:
            issue("unit_boundary_overlap",
                  f"Units {index} and {index + 1} overlap on the listed source content. "
                  "Decide which unit it belongs to and revise their boundaries to meet.",
                  [index - 1, index], start, min(previous_end, end))
        elif start > previous_end:
            issue("unit_boundary_gap",
                  f"There is a gap between units {index} and {index + 1} at the listed content. "
                  "Decide its unit and revise their boundaries to meet.",
                  [index - 1, index], previous_end, start)
    final = (len(canonical.source_entries), 0)
    if bounds[-1][1] is not None and bounds[-1][1] != final:
        issue("unit_boundary_gap", "The last unit ends before the listed source content.",
              [len(units) - 1], bounds[-1][1], final)
    if blockers:
        raise UnitPartitionError(blockers)
    return [(start, end) for start, end in bounds if start is not None and end is not None]


def load_initial_inventory(root: Path, source_hash: str) -> JsonObject:
    try:
        value = read_json(root / INITIAL_INVENTORY_PATH)
        if value.get("schema_version") != INITIAL_INVENTORY_SCHEMA:
            raise ValueError("Initial inventory version is unsupported.")
        canonical = CanonicalSourceInventory.from_json(value.get("canonical_source_inventory"))
        if canonical.source_snapshot_sha256 != source_hash:
            raise ValueError("Initial inventory belongs to another source.")
        if sha256_file(root / "input/school-template.docx") != source_hash:
            raise ValueError("The immutable source snapshot changed.")
        manifest_path = root / "work/.docfit/prepare-template-task.json"
        manifest = read_json(manifest_path)
        if manifest.get("source_inventory_digest") != canonical.inventory_digest:
            raise ValueError("Initial inventory differs from the pre-query task binding.")
        if not isinstance(value.get("objects"), list) or not value["objects"]:
            raise ValueError("Initial inventory has no Word mapping.")
        if value.get("mapping_digest") != sha256_json(value["objects"]):
            raise ValueError("Initial Word mapping changed.")
        return value
    except (OSError, ValueError, KeyError, ToolFailure) as error:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="initial_source_inventory_invalid",
            message="The immutable initial source inventory is missing, stale or unsupported.",
            suggested_actions=("Start a fresh preparation task from the source document.",),
        ) from error


def _point(value: Any, canonical: CanonicalSourceInventory) -> tuple[int, int]:
    if not isinstance(value, dict):
        raise ValueError("A boundary must name a source entry and an edge.")
    edge = value.get("edge")
    keys = (
        {"source_entry_id", "edge", "before", "after"}
        if edge == "split"
        else {"source_entry_id", "edge"}
    )
    if set(value) != keys or not isinstance(edge, str) or edge not in {"start", "end", "split"}:
        raise ValueError("Use only source_entry_id and edge; split also requires before/after.")
    for index, entry in enumerate(canonical.source_entries):
        if entry.source_entry_id != value.get("source_entry_id"):
            continue
        if edge == "start":
            return index, 0
        if edge == "end":
            return index + 1, 0
        before, after = value["before"], value["after"]
        if not isinstance(before, str) or not isinstance(after, str) or not before or not after:
            raise ValueError("An internal split requires two nonempty original text pieces.")
        if before + after != entry.text:
            raise ValueError("Split before + after must equal the named entry's complete text.")
        return index, len(before)
    raise ValueError("The boundary names a source_entry_id absent from the current document_map.")


def resolve_unit_partition(canonical: CanonicalSourceInventory, units: Any) -> list[JsonObject]:
    """Resolve only Agent source points; independent locators/offsets are never accepted."""
    if not isinstance(units, list) or not units or not canonical.source_entries:
        raise ValueError("A nonempty source inventory and units are required.")
    # Validate the complete snapshot once per partition check. Each span below
    # then resolves against its one already-bound entry, without reparsing and
    # hashing every other entry for every span. Nothing is cached across calls.
    canonical = CanonicalSourceInventory.from_json(canonical.to_json())
    bounds = _partition_bounds(canonical, units)
    resolved: list[JsonObject] = []
    for unit, (start, end) in zip(units, bounds, strict=True):
        spans: list[JsonObject] = []
        for index in range(start[0], min(end[0] + 1, len(canonical.source_entries))):
            entry = canonical.source_entries[index]
            left = start[1] if index == start[0] else 0
            right = end[1] if index == end[0] else len(entry.text)
            if index == end[0] and right == 0:
                break
            extent = TextSourceExtent(left, right) if entry.text else WholeEntrySourceExtent()
            exact = resolve_source_span(
                inventory={
                    "document_sha256": canonical.source_snapshot_sha256,
                    "source_entries": [entry.to_json()],
                },
                source_span=SourceSpan(entry.source_entry_id, extent),
                source_snapshot_sha256=canonical.source_snapshot_sha256,
                inventory_digest=canonical.inventory_digest,
            )
            spans.append(
                {
                    "source_entry_id": entry.source_entry_id,
                    "extent": {"kind": "text", "start": left, "end": right}
                    if entry.text
                    else {"kind": "whole_entry"},
                    "text": exact.expected_source_content,
                    "word_fragments": [fragment.to_json() for fragment in exact.word_fragments],
                }
            )
        if not spans:
            raise ValueError("A unit must include source content or a structural entry.")
        fragments = [fragment for span in spans for fragment in span["word_fragments"]]
        resolved.append(
            {
                **unit,
                "source_spans": spans,
                "covered_object_ids": list(dict.fromkeys(item["object_id"] for item in fragments)),
                "start_locator": fragments[0]["locator"],
                "end_locator": fragments[-1]["locator"],
            }
        )
    return resolved


def validate_unit_proof(canonical: CanonicalSourceInventory, proof: JsonObject) -> list[JsonObject]:
    if (
        proof.get("schema_version") != UNIT_PROOF_SCHEMA
        or proof.get("status") != "ok"
        or proof.get("checkpoint") != "unit-boundary"
        or proof.get("source_hash") != canonical.source_snapshot_sha256
        or proof.get("source_inventory_digest") != canonical.inventory_digest
    ):
        raise ValueError("Unit proof lacks the current initial inventory binding.")
    if not isinstance(proof.get("resolved_units"), list) or not proof["resolved_units"]:
        raise ValueError("Unit proof requires nonempty resolved_units.")
    resolved = resolve_unit_partition(canonical, proof.get("units"))
    if proof.get("resolved_units") != resolved:
        raise ValueError("Unit proof ranges differ from their exact source boundary points.")
    if proof.get("unit_projection_digest") != sha256_json(resolved):
        raise ValueError("Unit proof projection binding is stale.")
    return resolved


def validate_inventory_partition(inventory: JsonObject) -> list[JsonObject]:
    canonical = CanonicalSourceInventory.from_json(inventory.get("canonical_source_inventory"))
    if inventory.get("document_sha256") != canonical.source_snapshot_sha256:
        raise ValueError("Post-unit source hash differs from its canonical inventory.")
    proof = inventory.get("unit_boundary_proof")
    if not isinstance(proof, dict):
        raise ValueError("Post-unit inventory requires the initial source unit proof.")
    units = validate_unit_proof(canonical, proof)
    if inventory.get("unit_projection_digest") != sha256_json(units):
        raise ValueError("Post-unit inventory unit binding is stale.")
    if inventory.get("source_entries") != [entry.to_json() for entry in canonical.source_entries]:
        raise ValueError("Post-unit inventory must preserve every complete canonical entry.")
    return units


def require_initial_binding(root: Path, inventory: JsonObject) -> None:
    try:
        initial = load_initial_inventory(root, str(inventory.get("document_sha256", "")))
        if inventory.get("canonical_source_inventory") != initial["canonical_source_inventory"]:
            raise ValueError("Post-unit inventory differs from the immutable initial inventory.")
        validate_inventory_partition(inventory)
        persisted = read_json(root / "work/.docfit/unit-boundary-checkpoint.json")
        if inventory.get("unit_boundary_proof") != proof_binding(persisted):
            raise ValueError("Post-unit inventory differs from the accepted checkpoint.")
    except (ValueError, ToolFailure) as error:
        raise ToolFailure(
            status="needs_input",
            origin="harness",
            code="initial_source_binding_invalid",
            message=str(error),
        ) from error


def proof_binding(proof: JsonObject) -> JsonObject:
    return {
        key: proof.get(key)
        for key in (
            "schema_version",
            "status",
            "checkpoint",
            "source_hash",
            "source_inventory_digest",
            "unit_projection_digest",
            "units",
            "resolved_units",
        )
    }


def entry_unit_contexts(units: list[JsonObject], source_entry_id: str) -> list[JsonObject]:
    """Complete semantic context, with exact texts rather than Agent offset bookkeeping."""
    return [
        {
            "unit_id": unit["unit_id"],
            "unit_name": unit["unit_name"],
            "text": span["text"],
            "start_boundary": unit["start_boundary"],
            "end_boundary": unit["end_boundary"],
        }
        for unit in units
        for span in unit["source_spans"]
        if span["source_entry_id"] == source_entry_id
    ]


def source_unit_cut_points(units: list[JsonObject]) -> dict[str, set[int]]:
    """Return accepted text cuts for exact semantic and published spans."""
    points: dict[str, set[int]] = {}
    for unit in units:
        for span in unit["source_spans"]:
            extent = span["extent"]
            if extent["kind"] == "text":
                points.setdefault(span["source_entry_id"], set()).update(
                    (extent["start"], extent["end"])
                )
    return points
