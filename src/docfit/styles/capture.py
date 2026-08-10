"""Capture final template representatives as immutable Style Contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from docfit.styles.contracts import StyleContractSet, style_contract_digest
from docfit.styles.materialization import SUPPORTED_MATERIALIZED_PROPERTIES
from docfit.styles.resolver import EffectiveStyleResolver
from docfit.styles.validator import StyleContractValidator
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file

_PARAGRAPH_ONLY_CONTENT_TYPES = frozenset(
    {"image", "asset", "formula", "equation", "table"}
)


def capture_template_style_contracts(
    document: Path,
    slots: Sequence[Mapping[str, Any]],
) -> tuple[StyleContractSet, JsonObject]:
    """Capture and immediately validate every final slot representative."""

    resolver = EffectiveStyleResolver(document)
    styles: list[JsonObject] = []
    occurrences: list[JsonObject] = []
    for slot in slots:
        slot_id = slot.get("slot_id")
        field_id = slot.get("field_id")
        content_type = slot.get("content_type")
        locator = slot.get("locator")
        if (
            not isinstance(slot_id, str)
            or not isinstance(field_id, str)
            or not isinstance(content_type, str)
            or not isinstance(locator, Mapping)
        ):
            raise _failure(
                "style_capture_slot_invalid",
                "Every published slot requires identity, content type, and locator.",
            )
        resolved = resolver.resolve(locator)
        properties = {
            path: value
            for path, value in resolved.properties.items()
            if path in SUPPORTED_MATERIALIZED_PROPERTIES and value is not None
        }
        if content_type in _PARAGRAPH_ONLY_CONTENT_TYPES:
            properties = {
                path: value
                for path, value in properties.items()
                if path.startswith("paragraph.")
            }
        if not properties:
            raise _failure(
                "style_capture_empty",
                f"Slot {slot_id} exposes no materializable effective style properties.",
            )
        style: JsonObject = {
            "style_contract_id": f"style.slot.{slot_id}",
            "label": f"{field_id} @ {slot_id}",
            "application_scope": _application_scope(content_type),
            "owned_properties": sorted(properties),
            "effective_properties": dict(sorted(properties.items())),
            "override_policy": {
                "managed_direct_formatting": "clear_conflicts",
                "unmanaged_properties": "preserve",
            },
            "dependencies": [],
            "evidence_refs": [
                {
                    "type": "template_slot_representative",
                    "slot_id": slot_id,
                    "field_id": field_id,
                    "locator": dict(locator),
                }
            ],
        }
        style["contract_digest"] = style_contract_digest(style)
        styles.append(style)
        occurrences.append(
            {
                "occurrence_id": f"template-slot:{slot_id}",
                "locator": dict(locator),
                "style_contract_ref": {
                    "style_contract_id": style["style_contract_id"],
                    "contract_digest": style["contract_digest"],
                },
            }
        )
    contracts = StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": sha256_file(document),
            "styles": styles,
        }
    )
    manifest: JsonObject = {
        "schema_version": "docfit-style-occurrence-manifest/v2",
        "style_contract_set_digest": contracts.digest,
        "occurrences": occurrences,
    }
    validation = StyleContractValidator(contracts).validate(document, manifest)
    if validation.status != "passed":
        counts = validation.as_dict()["counts"]
        raise ToolFailure(
            status="error",
            origin="postcondition",
            code="template_style_contract_validation_failed",
            message=(
                "Final template representatives do not satisfy their captured Style Contracts: "
                f"{counts['failed']} failed, {counts['unresolved']} unresolved."
            ),
            suggested_actions=("inspect_template_style_provenance", "repair_template_styles"),
        )
    return contracts, {
        "schema_version": "docfit-template-style-capture/v2",
        "status": "passed",
        "style_contract_set_digest": contracts.digest,
        "occurrence_manifest": manifest,
        "validation": validation.as_dict(),
    }


def _application_scope(content_type: str) -> str:
    return {
        "text": "text",
        "rich_text": "block",
        "section": "section",
        "table": "table",
    }.get(content_type, "block")


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("inspect_template_again", "repair_template_slot"),
    )
