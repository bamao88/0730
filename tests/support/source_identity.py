"""Factories for synthetic current-contract source identity fixtures (no legacy conversion)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.template.source_entries import (
    CanonicalSourceInventory,
    _source_inventory_digest,
    validate_canonical_source_entries,
)
from docfit.template.source_layout import LAYOUT_EVIDENCE_VERSION
from docfit.template.source_order import SOURCE_ORDER_VERSION
from docfit.template.source_structure import STRUCTURE_EVIDENCE_VERSION
from docfit.template.unit_source import (
    INITIAL_INVENTORY_PATH,
    INITIAL_INVENTORY_SCHEMA,
    UNIT_PROOF_SCHEMA,
    entry_unit_contexts,
    proof_binding,
    resolve_unit_partition,
)
from docfit.tools.runtime import atomic_write_json, sha256_json


def source_partition(
    inventory: dict[str, Any],
    *,
    units: list[dict[str, Any]] | None = None,
    unit_id: str = "u-all",
    unit_name: str = "source",
) -> dict[str, Any]:
    """Build a new exact partition for a synthetic inventory before semantic judgments."""
    raw = inventory.get("canonical_source_inventory")
    if raw is None:
        entries = validate_canonical_source_entries(inventory["source_entries"])
        source_hash = inventory["document_sha256"]
        canonical = CanonicalSourceInventory(
            source_hash,
            entries,
            _source_inventory_digest(
                source_snapshot_sha256=source_hash,
                source_entries=entries,
            ),
        )
    else:
        canonical = CanonicalSourceInventory.from_json(raw)
    inventory["canonical_source_inventory"] = canonical.to_json()
    inventory["source_entries"] = [entry.to_json() for entry in canonical.source_entries]
    if units is None:
        body_entries = [
            entry for entry in canonical.source_entries
            if all(item.locator.startswith("/body/") for item in entry.provenance)
        ]
        units = [
            {
                "unit_id": unit_id,
                "unit_name": unit_name,
                "start_boundary": {
                    "source_entry_id": body_entries[0].source_entry_id,
                    "edge": "start",
                },
                "end_boundary": {
                    "source_entry_id": body_entries[-1].source_entry_id,
                    "edge": "end",
                },
            }
        ] if body_entries else []
    resolved = resolve_unit_partition(canonical, units)
    proof = {
        "schema_version": UNIT_PROOF_SCHEMA,
        "status": "ok",
        "checkpoint": "unit-boundary",
        "source_hash": canonical.source_snapshot_sha256,
        "source_inventory_digest": canonical.inventory_digest,
        "unit_projection_digest": sha256_json(resolved),
        "units": units,
        "resolved_units": resolved,
        "resolved_body_units": [
            scope for scope in resolved if scope.get("scope_kind") != "auxiliary_story"
        ],
        "auxiliary_scopes": [
            scope for scope in resolved if scope.get("scope_kind") == "auxiliary_story"
        ],
    }
    inventory["unit_boundary_proof"] = proof_binding(proof)
    inventory["unit_projection_digest"] = proof["unit_projection_digest"]
    return proof


def review_binding(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_inventory_digest": inventory["canonical_source_inventory"]["inventory_digest"],
        "unit_projection_digest": inventory["unit_projection_digest"],
    }


def persist_source_identity(
    root: Path, inventory: dict[str, Any], *, objects: list[dict[str, Any]] | None = None
) -> None:
    """Persist an explicitly constructed new fixture, never upgrade an existing ledger."""
    source = root / "input/school-template.docx"
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"synthetic source")
    if objects is None:
        objects = inventory.get("objects", [])
    if not objects:
        objects = [
            {"object_id": item["object_id"], "locator": item["locator"]}
            for entry in inventory["source_entries"]
            for item in entry["provenance"]
        ]
    manifest_path = root / "work/.docfit/prepare-template-task.json"
    import json

    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest["source_inventory_digest"] = inventory["canonical_source_inventory"][
        "inventory_digest"
    ]
    atomic_write_json(manifest_path, manifest)
    atomic_write_json(
        root / INITIAL_INVENTORY_PATH,
        {
            "schema_version": INITIAL_INVENTORY_SCHEMA,
            "source_order_version": SOURCE_ORDER_VERSION,
            "canonical_source_inventory": inventory["canonical_source_inventory"],
            "objects": objects,
            "mapping_digest": sha256_json(objects),
        },
    )
    atomic_write_json(
        root / "work/.docfit/unit-boundary-checkpoint.json", inventory["unit_boundary_proof"]
    )


def context_packets(inventory: dict[str, Any]) -> dict[str, Any]:
    units = inventory["unit_boundary_proof"]["resolved_units"]
    packets = {}
    for unit in units:
        ids = {span["source_entry_id"] for span in unit["source_spans"]}
        packets[unit["unit_id"]] = {
            "layout_evidence_version": LAYOUT_EVIDENCE_VERSION,
            "structure_evidence_version": STRUCTURE_EVIDENCE_VERSION,
            "source_entries": [
                {**entry, "unit_contexts": entry_unit_contexts(units, entry["source_entry_id"])}
                for entry in inventory["source_entries"]
                if entry["source_entry_id"] in ids
            ]
        }
    return packets
