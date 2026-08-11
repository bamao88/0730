from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import pytest

from template_extraction_eval.contracts import InputContractError, InputErrorCode
from template_extraction_eval.style_observations import (
    validate_school_style_observation_set,
)

PROFILE_PATHS = {"caption": ("run.bold", "run.underline", "numbering")}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _observation() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "docfit-field-style-observation/v1",
        "field_id": "body.table.caption",
        "slot_id": "body.table.caption.missing",
        "style_role_id": "style.caption.table",
        "style_role_type": "caption",
        "property_profile_ref": {
            "profile_id": "docfit.style.caption",
            "profile_version": "1.0.0",
            "profile_digest": "c" * 64,
        },
        "properties": [
            {
                "property_path": property_path,
                "effective_state": "UNRESOLVED",
                "school_evidence_status": "MISSING_SCHOOL_DECLARATION",
                "provenance": [],
                "reason": "school_role_representative_missing",
            }
            for property_path in PROFILE_PATHS["caption"]
        ],
        "closure": {
            "observation_closure": "COMPLETE",
            "school_role_eligibility": "INCOMPLETE_KNOWN_GAPS",
            "known_gap_properties": list(PROFILE_PATHS["caption"]),
            "unresolved_properties": list(PROFILE_PATHS["caption"]),
            "failed_properties": [],
            "effective_state_counts": {"UNRESOLVED": 3},
            "school_evidence_counts": {"MISSING_SCHOOL_DECLARATION": 3},
        },
    }
    value["observation_digest"] = _digest(value)
    return value


def _observation_set() -> dict[str, Any]:
    observation = _observation()
    value: dict[str, Any] = {
        "schema_version": "docfit-school-style-observation-set/v1",
        "template_sha256": "a" * 64,
        "profile_registry_digest": "b" * 64,
        "observations": [observation],
    }
    value["school_observation_set_digest"] = _digest(
        {
            "schema_version": value["schema_version"],
            "template_sha256": value["template_sha256"],
            "profile_registry_digest": value["profile_registry_digest"],
            "observations": [
                {
                    "slot_id": observation["slot_id"],
                    "style_role_id": observation["style_role_id"],
                    "observation_digest": observation["observation_digest"],
                }
            ],
        }
    )
    return value


def _validate(value: dict[str, Any]) -> None:
    validate_school_style_observation_set(
        value,
        expected_property_paths=PROFILE_PATHS,
        expected_profile_registry_digest="b" * 64,
    )


def test_independent_eval_accepts_fixed_list_known_school_gap() -> None:
    _validate(_observation_set())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_property", "fixed property list"),
        ("illegal_axes", "illegal effective/evidence axis"),
        ("generic_null", "VALUE requires a non-null value"),
        ("stale_observation_digest", "observation digest mismatch"),
        ("stale_set_digest", "observation set digest mismatch"),
    ],
)
def test_independent_eval_rejects_non_closed_observations(
    mutation: str,
    message: str,
) -> None:
    value = _observation_set()
    observation = value["observations"][0]
    if mutation == "missing_property":
        observation["properties"].pop()
    elif mutation == "illegal_axes":
        observation["properties"][0]["effective_state"] = "NONE"
    elif mutation == "generic_null":
        observation["properties"][0].update(
            {
                "effective_state": "VALUE",
                "school_evidence_status": "EXPLICIT_OR_VERIFIED",
                "value": None,
            }
        )
    elif mutation == "stale_observation_digest":
        observation["observation_digest"] = "d" * 64
        value["school_observation_set_digest"] = _digest(
            {
                "schema_version": value["schema_version"],
                "template_sha256": value["template_sha256"],
                "profile_registry_digest": value["profile_registry_digest"],
                "observations": [
                    {
                        "slot_id": observation["slot_id"],
                        "style_role_id": observation["style_role_id"],
                        "observation_digest": observation["observation_digest"],
                    }
                ],
            }
        )
    elif mutation == "stale_set_digest":
        value["school_observation_set_digest"] = "e" * 64
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(mutation)

    with pytest.raises(InputContractError, match=message) as captured:
        _validate(deepcopy(value))

    assert captured.value.code in {
        InputErrorCode.CONTRACT_MISMATCH,
        InputErrorCode.HASH_MISMATCH,
    }
