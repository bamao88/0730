"""Normalize source Fill Contracts before package writing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

RESPONSIBILITY_POLICY: dict[str, str] = {
    "mode": "exhaustive",
    "analysis_universe": "semantic_document_facts/v1",
    "protected_basis": "complement_of_slot_and_remove",
    "slot_basis": "managed_content_controls_and_fill_contract",
    "remove_basis": "declared_remove_regions",
}


def _canonical_json_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _style_contract_set_digest(
    *,
    schema_version: str,
    template_sha256: str,
    styles: list[Mapping[str, Any]],
) -> str:
    style_refs = sorted(
        (
            {
                "style_contract_id": str(style["style_contract_id"]),
                "contract_digest": str(style["contract_digest"]),
            }
            for style in styles
        ),
        key=lambda item: (item["style_contract_id"], item["contract_digest"]),
    )
    return _canonical_json_digest(
        {
            "schema_version": schema_version,
            "template_sha256": template_sha256,
            "styles": style_refs,
        }
    )


def _replace_style_contract_set_digest(value: Any, digest: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "style_contract_set_digest":
                value[key] = digest
            else:
                _replace_style_contract_set_digest(item, digest)
    elif isinstance(value, list):
        for item in value:
            _replace_style_contract_set_digest(item, digest)


def _normalize_style_contract_set_digest(
    contract: dict[str, Any],
    *,
    template_sha256: str,
) -> None:
    styles = contract.get("styles")
    if not isinstance(styles, list) or "style_contract_set_digest" not in contract:
        return
    style_mappings = [
        style for style in styles if isinstance(style, Mapping)
    ]
    if len(style_mappings) != len(styles):
        raise ValueError("style contracts must be mappings")
    digest = _style_contract_set_digest(
        schema_version=str(contract["schema_version"]),
        template_sha256=template_sha256,
        styles=style_mappings,
    )
    _replace_style_contract_set_digest(contract, digest)


def normalize_fill_contract(
    value: dict[str, Any],
    *,
    template_sha256: str,
) -> dict[str, Any]:
    """Return a copy with package-level invariants closed.

    The function deliberately does not convert v1 contracts into v2 contracts.
    It normalizes only facts owned by candidate packaging: snapshot hash,
    responsibility policy, and missing owner defaults.
    """

    contract = deepcopy(value)
    contract["template_sha256"] = template_sha256
    _normalize_style_contract_set_digest(contract, template_sha256=template_sha256)
    contract.setdefault("responsibility_policy", deepcopy(RESPONSIBILITY_POLICY))
    regions = contract.get("regions", [])
    if isinstance(regions, list):
        for region in regions:
            if isinstance(region, dict):
                region.setdefault("owner", "slot" if "field_ids" in region else "protected")
    slots = contract.get("slots", [])
    if isinstance(slots, list):
        for slot in slots:
            if isinstance(slot, dict):
                slot.setdefault("owner", "slot")
    return contract
