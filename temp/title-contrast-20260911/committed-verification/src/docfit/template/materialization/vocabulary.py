"""Accepted field-vocabulary provenance checks for materialization."""

from __future__ import annotations

from collections.abc import Iterable

from docfit.fields import FIELD_VOCABULARY_SCHEMA_VERSION, FieldRegistrySnapshot
from docfit.template.materialization.field_binding import explicit_materialization_field_ids
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json


def review_vocabulary_provenance_errors(
    *,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> list[JsonObject]:
    """Return fail-closed blockers when review lacks accepted input vocabulary."""

    vocabulary = review.get("field_id_vocabulary")
    digest = review.get("field_vocabulary_digest")
    return [
        *_vocabulary_errors(
            vocabulary=vocabulary,
            digest=digest,
            registry=registry,
            owner="review",
        ),
        *_selected_field_errors(
            vocabulary=vocabulary,
            field_ids=_review_field_ids(review),
        ),
    ]


def inventory_review_vocabulary_provenance_errors(
    *,
    inventory: JsonObject,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> list[JsonObject]:
    """Return blockers when inventory and review are not bound to one vocabulary."""

    inventory_vocabulary = inventory.get("field_id_vocabulary")
    inventory_digest = inventory.get("field_vocabulary_digest")
    review_vocabulary = review.get("field_id_vocabulary")
    review_digest = review.get("field_vocabulary_digest")
    errors = [
        *_vocabulary_errors(
            vocabulary=inventory_vocabulary,
            digest=inventory_digest,
            registry=registry,
            owner="inventory",
        ),
        *review_vocabulary_provenance_errors(review=review, registry=registry),
    ]
    if errors:
        return errors
    if inventory_vocabulary != review_vocabulary or inventory_digest != review_digest:
        return [
            _error(
                code="materialization_field_vocabulary_provenance_mismatch",
                missing_requirement="matching_inventory_review_field_id_vocabulary",
                message=(
                    "Materialization requires object inventory and accepted semantic "
                    "judgments to carry the same pre-input field_id_vocabulary."
                ),
            )
        ]
    return []


def _vocabulary_errors(
    *,
    vocabulary: object,
    digest: object,
    registry: FieldRegistrySnapshot,
    owner: str,
) -> list[JsonObject]:
    if not isinstance(vocabulary, dict):
        return [
            _error(
                code="materialization_field_vocabulary_provenance_missing",
                missing_requirement=f"{owner}.field_id_vocabulary",
                message=(
                    "Materialization requires accepted semantics to carry the "
                    "pre-input field_id_vocabulary; Registry lookup alone is not "
                    "accepted."
                ),
            )
        ]
    if vocabulary.get("schema_version") != FIELD_VOCABULARY_SCHEMA_VERSION:
        return [
            _error(
                code="materialization_field_vocabulary_provenance_invalid",
                missing_requirement=f"{owner}.field_id_vocabulary.schema_version",
                message="Accepted field_id_vocabulary has an unsupported schema version.",
            )
        ]
    actual_digest = _vocabulary_digest(vocabulary)
    if not isinstance(digest, str) or digest != vocabulary.get("digest") or digest != actual_digest:
        return [
            _error(
                code="materialization_field_vocabulary_digest_mismatch",
                missing_requirement=f"{owner}.field_vocabulary_digest",
                message="Accepted field_id_vocabulary digest does not match its payload.",
            )
        ]
    registry_identity = vocabulary.get("registry")
    if registry_identity != registry.identity():
        return [
            _error(
                code="materialization_field_vocabulary_registry_mismatch",
                missing_requirement=f"{owner}.field_id_vocabulary.registry",
                message=(
                    "Accepted field_id_vocabulary is not bound to the current "
                    "Registry snapshot."
                ),
            )
        ]
    allowed = _allowed_field_ids(vocabulary)
    if allowed is None:
        return [
            _error(
                code="materialization_field_vocabulary_provenance_invalid",
                missing_requirement=f"{owner}.field_id_vocabulary.allowed_field_ids",
                message="Accepted field_id_vocabulary must list allowed_field_ids.",
            )
        ]
    unknown_allowed: list[str] = []
    for field_id in allowed:
        try:
            registry.lookup(field_id)
        except ToolFailure:
            unknown_allowed.append(field_id)
    if unknown_allowed:
        return [
            _error(
                code="materialization_field_vocabulary_registry_mismatch",
                missing_requirement=f"{owner}.field_id_vocabulary.allowed_field_ids",
                message=(
                    "Accepted field_id_vocabulary contains IDs outside the current "
                    "Registry snapshot."
                ),
                payload={"unknown_field_ids": unknown_allowed},
            )
        ]
    return []


def _selected_field_errors(
    *,
    vocabulary: object,
    field_ids: Iterable[str],
) -> list[JsonObject]:
    allowed = _allowed_field_ids(vocabulary)
    if allowed is None:
        return []
    missing = [field_id for field_id in dict.fromkeys(field_ids) if field_id not in allowed]
    if not missing:
        return []
    return [
        _error(
            code="materialization_field_not_in_vocabulary",
            missing_requirement="parts[].field_id in field_id_vocabulary.allowed_field_ids",
            message=(
                "Materialization accepts only field_id values selected from the "
                "accepted pre-input field_id_vocabulary."
            ),
            payload={"field_ids": missing},
        )
    ]


def _review_field_ids(review: JsonObject) -> list[str]:
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list):
        return []
    field_ids: list[str] = []
    for judgment in raw_judgments:
        if isinstance(judgment, dict):
            field_ids.extend(explicit_materialization_field_ids(judgment))
    return field_ids


def _allowed_field_ids(vocabulary: object) -> set[str] | None:
    if not isinstance(vocabulary, dict):
        return None
    raw_allowed = vocabulary.get("allowed_field_ids")
    if not isinstance(raw_allowed, list):
        return None
    allowed: list[str] = []
    for item in raw_allowed:
        if not isinstance(item, str) or not item.strip():
            return None
        allowed.append(item.strip())
    if len(set(allowed)) != len(allowed):
        return None
    return set(allowed)


def _vocabulary_digest(vocabulary: JsonObject) -> str:
    payload = {key: value for key, value in vocabulary.items() if key != "digest"}
    return sha256_json(payload)


def _error(
    *,
    code: str,
    missing_requirement: str,
    message: str,
    payload: JsonObject | None = None,
) -> JsonObject:
    result: JsonObject = {
        "code": code,
        "missing_requirement": missing_requirement,
        "message": message,
        "needed_context": "field_id_vocabulary",
        "evidence_focus": "field_id_vocabulary",
    }
    if payload:
        result["payload"] = payload
    return result
