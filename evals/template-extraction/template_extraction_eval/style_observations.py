"""Independent contract checks for fixed-list school style observations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from .contracts import InputContractError, InputErrorCode

OBSERVATION_SCHEMA_VERSION = "docfit-field-style-observation/v1"
OBSERVATION_SET_SCHEMA_VERSION = "docfit-school-style-observation-set/v1"
EFFECTIVE_STATES = frozenset({"VALUE", "NONE", "N/A", "UNRESOLVED"})
EVIDENCE_STATUSES = frozenset(
    {
        "EXPLICIT_OR_VERIFIED",
        "IMPLICIT_WORD_DEFAULT_ONLY",
        "MISSING_SCHOOL_DECLARATION",
        "CONFLICT",
        "RESOLVER_UNSUPPORTED",
    }
)
_UNRESOLVED_EVIDENCE = frozenset(
    {"MISSING_SCHOOL_DECLARATION", "CONFLICT", "RESOLVER_UNSUPPORTED"}
)
_FAILED_EVIDENCE = frozenset({"CONFLICT", "RESOLVER_UNSUPPORTED"})


def _raise(
    code: InputErrorCode,
    message: str,
    path: Path | None,
) -> NoReturn:
    raise InputContractError(code, message, path=path)


def _digest(value: Any, *, path: Path | None) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"style observation contains non-canonical JSON: {error}",
            path,
        )
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, *, name: str, path: Path | None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise(InputErrorCode.CONTRACT_MISMATCH, f"{name} must be an object", path)
    return value


def _array(value: object, *, name: str, path: Path | None) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        _raise(InputErrorCode.CONTRACT_MISMATCH, f"{name} must be an array", path)
    return value


def _string(value: object, *, name: str, path: Path | None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{name} must be a canonical non-empty string",
            path,
        )
    return value


def _sha256(value: object, *, name: str, path: Path | None) -> str:
    result = _string(value, name=name, path=path)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{name} must be a lowercase SHA-256",
            path,
        )
    return result


def validate_school_style_observation_set(
    value: Mapping[str, Any],
    *,
    expected_property_paths: Mapping[str, Sequence[str]],
    expected_profile_registry_digest: str | None = None,
    path: Path | None = None,
) -> None:
    """Validate closure without importing any product style implementation.

    ``expected_property_paths`` is Eval-owned Gold keyed by ``style_role_type``.
    Its ordered paths are intentionally external to the product registry so a
    changed product list cannot make its own output pass automatically.
    """

    if value.get("schema_version") != OBSERVATION_SET_SCHEMA_VERSION:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "unsupported school style observation set schema",
            path,
        )
    template_sha256 = _sha256(
        value.get("template_sha256"), name="template_sha256", path=path
    )
    registry_digest = _sha256(
        value.get("profile_registry_digest"),
        name="profile_registry_digest",
        path=path,
    )
    if (
        expected_profile_registry_digest is not None
        and registry_digest != expected_profile_registry_digest
    ):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "school observation set uses an unexpected profile registry digest",
            path,
        )
    observations = _array(value.get("observations"), name="observations", path=path)
    identities: set[tuple[str, str]] = set()
    observation_refs: list[dict[str, str]] = []
    for index, raw_observation in enumerate(observations):
        observation = _mapping(
            raw_observation,
            name=f"observations[{index}]",
            path=path,
        )
        reference = _validate_observation(
            observation,
            expected_property_paths=expected_property_paths,
            path=path,
        )
        identity = (reference["slot_id"], reference["style_role_id"])
        if identity in identities:
            _raise(
                InputErrorCode.DUPLICATE_ID,
                f"duplicate school style observation {identity[0]} / {identity[1]}",
                path,
            )
        identities.add(identity)
        observation_refs.append(reference)
    canonical_refs = sorted(
        observation_refs,
        key=lambda item: (item["slot_id"], item["style_role_id"]),
    )
    if observation_refs != canonical_refs:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "school style observations are not in canonical slot/role order",
            path,
        )
    expected_set_digest = _digest(
        {
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
            "template_sha256": template_sha256,
            "profile_registry_digest": registry_digest,
            "observations": canonical_refs,
        },
        path=path,
    )
    supplied_set_digest = _sha256(
        value.get("school_observation_set_digest"),
        name="school_observation_set_digest",
        path=path,
    )
    if supplied_set_digest != expected_set_digest:
        _raise(
            InputErrorCode.HASH_MISMATCH,
            "school observation set digest mismatch",
            path,
        )


def _validate_observation(
    observation: Mapping[str, Any],
    *,
    expected_property_paths: Mapping[str, Sequence[str]],
    path: Path | None,
) -> dict[str, str]:
    if observation.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "unsupported field style observation schema",
            path,
        )
    slot_id = _string(observation.get("slot_id"), name="slot_id", path=path)
    style_role_id = _string(
        observation.get("style_role_id"), name="style_role_id", path=path
    )
    role_type = _string(
        observation.get("style_role_type"), name="style_role_type", path=path
    )
    _string(observation.get("field_id"), name="field_id", path=path)
    if role_type not in expected_property_paths:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"no independent Eval property profile for role type {role_type}",
            path,
        )
    profile_ref = _mapping(
        observation.get("property_profile_ref"),
        name="property_profile_ref",
        path=path,
    )
    if set(profile_ref) != {"profile_id", "profile_version", "profile_digest"}:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "property_profile_ref must contain exactly id, version, and digest",
            path,
        )
    for key in ("profile_id", "profile_version"):
        _string(profile_ref.get(key), name=f"property_profile_ref.{key}", path=path)
    _sha256(
        profile_ref.get("profile_digest"),
        name="property_profile_ref.profile_digest",
        path=path,
    )
    properties = _array(
        observation.get("properties"),
        name=f"{slot_id}.properties",
        path=path,
    )
    expected_paths = tuple(expected_property_paths[role_type])
    actual_paths: list[str] = []
    states: list[str] = []
    evidence_statuses: list[str] = []
    for index, raw_property in enumerate(properties):
        item = _mapping(
            raw_property,
            name=f"{slot_id}.properties[{index}]",
            path=path,
        )
        property_path, state, evidence = _validate_property(item, path=path)
        actual_paths.append(property_path)
        states.append(state)
        evidence_statuses.append(evidence)
    if tuple(actual_paths) != expected_paths:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{slot_id} does not equal the independent fixed property list; "
            f"expected={list(expected_paths)}, actual={actual_paths}",
            path,
        )
    closure = _mapping(observation.get("closure"), name=f"{slot_id}.closure", path=path)
    _validate_closure(
        closure,
        property_paths=actual_paths,
        states=states,
        evidence_statuses=evidence_statuses,
        path=path,
    )
    semantic_payload = {
        key: item
        for key, item in observation.items()
        if key != "observation_digest"
    }
    supplied_digest = _sha256(
        observation.get("observation_digest"),
        name=f"{slot_id}.observation_digest",
        path=path,
    )
    if supplied_digest != _digest(semantic_payload, path=path):
        _raise(
            InputErrorCode.HASH_MISMATCH,
            f"field style observation digest mismatch for {slot_id}",
            path,
        )
    return {
        "slot_id": slot_id,
        "style_role_id": style_role_id,
        "observation_digest": supplied_digest,
    }


def _validate_property(
    item: Mapping[str, Any],
    *,
    path: Path | None,
) -> tuple[str, str, str]:
    property_path = _string(
        item.get("property_path"), name="property_path", path=path
    )
    state = _string(item.get("effective_state"), name="effective_state", path=path)
    evidence = _string(
        item.get("school_evidence_status"),
        name="school_evidence_status",
        path=path,
    )
    if state not in EFFECTIVE_STATES or evidence not in EVIDENCE_STATUSES:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{property_path} has an unknown style observation state",
            path,
        )
    has_value = "value" in item
    if state == "VALUE":
        if not has_value or item.get("value") is None:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"{property_path} VALUE requires a non-null value",
                path,
            )
        _digest(item.get("value"), path=path)
    elif has_value:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{property_path} {state} cannot carry a value",
            path,
        )
    provenance = _array(
        item.get("provenance"), name=f"{property_path}.provenance", path=path
    )
    if any(not isinstance(entry, Mapping) for entry in provenance):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{property_path} provenance entries must be objects",
            path,
        )
    if evidence == "IMPLICIT_WORD_DEFAULT_ONLY" and state not in {"VALUE", "NONE"}:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{property_path} implicit Word default must be VALUE or NONE",
            path,
        )
    if (evidence in _UNRESOLVED_EVIDENCE) != (state == "UNRESOLVED"):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{property_path} has an illegal effective/evidence axis combination",
            path,
        )
    if state == "N/A" and evidence != "EXPLICIT_OR_VERIFIED":
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{property_path} N/A must be an explicit profile classification",
            path,
        )
    return property_path, state, evidence


def _validate_closure(
    closure: Mapping[str, Any],
    *,
    property_paths: Sequence[str],
    states: Sequence[str],
    evidence_statuses: Sequence[str],
    path: Path | None,
) -> None:
    unresolved = tuple(
        property_path
        for property_path, state in zip(property_paths, states, strict=True)
        if state == "UNRESOLVED"
    )
    failed = tuple(
        property_path
        for property_path, evidence in zip(
            property_paths, evidence_statuses, strict=True
        )
        if evidence in _FAILED_EVIDENCE
    )
    known_gaps = tuple(
        _string(item, name="known_gap_properties[]", path=path)
        for item in _array(
            closure.get("known_gap_properties"),
            name="known_gap_properties",
            path=path,
        )
    )
    if len(set(known_gaps)) != len(known_gaps) or set(known_gaps) - set(property_paths):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "known_gap_properties must be unique profile paths",
            path,
        )
    missing_school = {
        property_path
        for property_path, evidence in zip(
            property_paths, evidence_statuses, strict=True
        )
        if evidence == "MISSING_SCHOOL_DECLARATION"
    }
    if not missing_school.issubset(known_gaps):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "missing school declarations must be explicit known gaps",
            path,
        )
    declared_unresolved = tuple(
        _string(item, name="unresolved_properties[]", path=path)
        for item in _array(
            closure.get("unresolved_properties"),
            name="unresolved_properties",
            path=path,
        )
    )
    declared_failed = tuple(
        _string(item, name="failed_properties[]", path=path)
        for item in _array(
            closure.get("failed_properties"),
            name="failed_properties",
            path=path,
        )
    )
    if declared_unresolved != unresolved or declared_failed != failed:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "style observation closure property lists do not match the dual-axis facts",
            path,
        )
    expected_closure = "FAILED" if failed else "COMPLETE"
    if closure.get("observation_closure") != expected_closure:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "observation_closure does not match failed property evidence",
            path,
        )
    if failed:
        expected_eligibility = "NOT_EVALUABLE"
    elif unresolved or known_gaps:
        expected_eligibility = "INCOMPLETE_KNOWN_GAPS"
    else:
        expected_eligibility = "COMPLETE"
    if closure.get("school_role_eligibility") != expected_eligibility:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "school_role_eligibility does not match gaps and failures",
            path,
        )
    if closure.get("effective_state_counts") != dict(sorted(Counter(states).items())):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "effective_state_counts do not match properties",
            path,
        )
    if closure.get("school_evidence_counts") != dict(
        sorted(Counter(evidence_statuses).items())
    ):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "school_evidence_counts do not match properties",
            path,
        )


__all__ = ["validate_school_style_observation_set"]
