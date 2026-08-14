"""Bind, materialize, and validate Style Contracts on a final candidate."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docfit.styles import StyleContractSet, StyleContractValidator
from docfit.styles.materialization import materialize_style_contracts
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file

_PRESENTATION_ROLE_FIELDS = {
    "chapter_title": "body.heading.outline1",
    "section_title": "body.heading.outline2",
    "subsection_title": "body.heading.outline3",
    "body": "body.paragraph",
    "reference": "references.entries",
    "figure_caption": "body.figure.caption",
    "table_caption": "body.table.caption",
    "formula": "body.equation",
    "drawing": "body.figure",
}


def apply_and_validate_candidate_styles(
    *,
    candidate_docx: Path,
    contract: JsonObject,
    fill_result: JsonObject,
    projection: JsonObject,
) -> JsonObject:
    """Atomically publish a candidate only after every occurrence passes."""

    contracts = StyleContractSet.from_fill_contract(contract)
    if fill_result.get("style_contract_set_digest") != contracts.digest:
        raise _failure(
            "style_application_set_stale",
            "Fill evidence is not bound to the current Style Contract Set.",
        )
    input_hash = sha256_file(candidate_docx)
    manifest = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result=fill_result,
        projection=projection,
    )
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix=f".{candidate_docx.name}-styles-", dir=candidate_docx.parent
        )
    )
    styled_candidate = temporary_root / "candidate.docx"
    try:
        materialization = materialize_style_contracts(
            input_docx=candidate_docx,
            output_docx=styled_candidate,
            contracts=contracts,
            occurrence_manifest=manifest,
        )
        validation = StyleContractValidator(contracts).validate(styled_candidate, manifest)
        if validation.status != "passed":
            report = validation.as_dict()
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="style_contract_validation_failed",
                message=(
                    "Final candidate Style Contract validation failed: "
                    f"{report['counts']['failed']} failed, "
                    f"{report['counts']['unresolved']} unresolved."
                ),
                suggested_actions=(
                    "inspect_style_audit",
                    "repair_style_contract_or_occurrence_binding",
                ),
            )
        os.replace(styled_candidate, candidate_docx)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    validation_payload = validation.as_dict()
    return {
        "schema_version": "docfit-final-style-audit/v2",
        "status": "passed",
        "input_sha256": input_hash,
        "output_sha256": sha256_file(candidate_docx),
        "style_contract_set_digest": contracts.digest,
        "occurrence_manifest": manifest,
        "materialization": materialization,
        "validation": validation_payload,
    }


def build_style_occurrence_manifest(
    *,
    contracts: StyleContractSet,
    fill_result: JsonObject,
    projection: JsonObject,
) -> JsonObject:
    """Compile fill and projection evidence into one occurrence/ref manifest."""

    occurrences: list[JsonObject] = []
    raw_fill_manifest = fill_result.get("style_occurrence_manifest")
    if not isinstance(raw_fill_manifest, Mapping):
        raise _failure(
            "style_fill_manifest_missing", "Fill result has no Style Contract occurrences."
        )
    raw_fill_occurrences = raw_fill_manifest.get("occurrences")
    if not isinstance(raw_fill_occurrences, list):
        raise _failure(
            "style_fill_manifest_invalid", "Fill occurrence manifest must be an array."
        )
    for occurrence in raw_fill_occurrences:
        if not isinstance(occurrence, Mapping):
            raise _failure(
                "style_fill_manifest_invalid", "Every fill occurrence must be an object."
            )
        occurrence_id = occurrence.get("occurrence_id")
        if not isinstance(occurrence_id, str):
            raise _failure(
                "style_fill_manifest_invalid", "Every fill occurrence requires occurrence_id."
            )
        if occurrence_id.startswith("block:references.entries:"):
            continue
        occurrences.append(_normalized_occurrence(contracts, occurrence))

    role_refs: dict[str, Mapping[str, Any]] = {}
    for block in fill_result.get("block_operations", []):
        if not isinstance(block, Mapping):
            continue
        field_id = block.get("field_id")
        style_ref = block.get("style_contract_ref")
        if isinstance(field_id, str) and isinstance(style_ref, Mapping):
            role_refs[field_id] = style_ref
        if field_id == "body.ordered_items":
            body_refs = block.get("style_role_refs")
            if not isinstance(body_refs, Mapping):
                raise _failure(
                    "style_body_role_refs_missing",
                    "Body fill evidence has no role-level Style Contract references.",
                )
            for role_field, reference in body_refs.items():
                if isinstance(role_field, str) and isinstance(reference, Mapping):
                    role_refs[role_field] = reference

    raw_projection_occurrences = projection.get("style_occurrences")
    if not isinstance(raw_projection_occurrences, list):
        raise _failure(
            "style_projection_manifest_missing",
            "Projection result has no final style occurrence evidence.",
        )
    role_counts: dict[str, int] = {}
    for raw in raw_projection_occurrences:
        if not isinstance(raw, Mapping):
            raise _failure(
                "style_projection_manifest_invalid",
                "Every projection style occurrence must be an object.",
            )
        locator = raw.get("target_locator")
        presentation_role = raw.get("presentation_role")
        if not isinstance(locator, str) or not isinstance(presentation_role, str):
            raise _failure(
                "style_projection_manifest_invalid",
                "Projection occurrences require target_locator and presentation_role.",
            )
        field_id = _PRESENTATION_ROLE_FIELDS.get(presentation_role)
        if field_id is None:
            raise _failure(
                "style_presentation_role_unsupported",
                f"No Style Contract binding exists for role {presentation_role}.",
            )
        style_ref = role_refs.get(field_id)
        if style_ref is None:
            raise _failure(
                "style_presentation_role_unbound",
                f"Final role {presentation_role} requires a {field_id} Style Contract slot.",
            )
        role_counts[presentation_role] = role_counts.get(presentation_role, 0) + 1
        occurrences.append(
            _normalized_occurrence(
                contracts,
                {
                    "occurrence_id": (
                        f"projection:{presentation_role}:{role_counts[presentation_role]}"
                    ),
                    "locator": locator,
                    "style_contract_ref": style_ref,
                },
            )
        )
    if not occurrences:
        raise _failure(
            "style_occurrence_manifest_empty",
            "A final candidate must expose at least one styled occurrence.",
        )
    return {
        "schema_version": "docfit-style-occurrence-manifest/v2",
        "style_contract_set_digest": contracts.digest,
        "occurrences": occurrences,
    }


def _normalized_occurrence(
    contracts: StyleContractSet, occurrence: Mapping[str, Any]
) -> JsonObject:
    occurrence_id = occurrence.get("occurrence_id")
    locator = occurrence.get("locator")
    style_ref = occurrence.get("style_contract_ref")
    if (
        not isinstance(occurrence_id, str)
        or not isinstance(locator, str | Mapping)
        or not isinstance(style_ref, Mapping)
    ):
        raise _failure(
            "style_occurrence_manifest_invalid",
            "Every occurrence requires occurrence_id, locator, and style_contract_ref.",
        )
    contract = contracts.resolve(style_ref)
    return {
        "occurrence_id": occurrence_id,
        "locator": dict(locator) if isinstance(locator, Mapping) else locator,
        "style_contract_ref": {
            "style_contract_id": contract.style_contract_id,
            "contract_digest": contract.contract_digest,
        },
    }


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_fill_contract", "inspect_style_occurrences"),
    )
