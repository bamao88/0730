"""Capture fixed-list school observations without reading or selecting presets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docfit.styles.contracts import StyleContractSet, style_contract_digest
from docfit.styles.materialization import SUPPORTED_MATERIALIZED_PROPERTIES
from docfit.styles.observation import (
    EffectiveState,
    FieldStyleObservation,
    FieldStyleObservationSet,
    PropertyObservation,
    SchoolEvidenceStatus,
    SchoolRoleEligibility,
    observe_effective_style,
)
from docfit.styles.profiles import (
    DEFAULT_STYLE_PROPERTY_PROFILES,
    StylePropertyProfile,
    StylePropertyProfileRegistry,
)
from docfit.styles.resolver import EffectiveStyleResolver
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

CAPTURE_SCHEMA_VERSION = "docfit-school-style-capture/v1"


@dataclass(frozen=True, slots=True)
class SchoolStyleCapture:
    observation_set: FieldStyleObservationSet
    school_candidates: tuple[JsonObject, ...]
    known_gaps: tuple[JsonObject, ...]
    failed_observations: tuple[JsonObject, ...]
    non_style_slots: tuple[str, ...]

    @property
    def school_observation_set_digest(self) -> str:
        return self.observation_set.school_observation_set_digest

    @property
    def status(self) -> str:
        if self.failed_observations:
            return "failed"
        if self.known_gaps:
            return "passed_with_known_gaps"
        return "passed"

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "status": self.status,
            "profile_registry_digest": self.observation_set.profile_registry_digest,
            "school_observation_set_digest": self.school_observation_set_digest,
            "observation_set": self.observation_set.as_dict(),
            "school_candidates": list(self.school_candidates),
            "known_gaps": list(self.known_gaps),
            "failed_observations": list(self.failed_observations),
            "non_style_slots": list(self.non_style_slots),
            "audit_counts": {
                "observation_count": len(self.observation_set.observations),
                "school_candidate_count": len(self.school_candidates),
                "known_gap_count": len(self.known_gaps),
                "failed_observation_count": len(self.failed_observations),
                "non_style_slot_count": len(self.non_style_slots),
            },
        }


def capture_template_style_observations(
    document: Path,
    slots: Sequence[Mapping[str, Any]],
    *,
    expected_roles: Sequence[Mapping[str, Any]] = (),
    registry: StylePropertyProfileRegistry = DEFAULT_STYLE_PROPERTY_PROFILES,
) -> SchoolStyleCapture:
    """Capture school facts for every fixed profile property; never consult a preset."""

    resolver = EffectiveStyleResolver(document)
    observations: list[FieldStyleObservation] = []
    non_style_slots: list[str] = []
    for slot in slots:
        slot_id = slot.get("slot_id")
        if slot.get("handling") == "non_style":
            if not isinstance(slot_id, str) or not slot_id:
                raise _failure(
                    "style_capture_slot_invalid", "A non-style slot still requires slot_id."
                )
            non_style_slots.append(slot_id)
            continue
        field_id = slot.get("field_id")
        style_role_id = slot.get("style_role_id")
        style_role_type = slot.get("style_role_type")
        profile_ref = slot.get("property_profile_ref")
        locator = slot.get("locator")
        if (
            not isinstance(slot_id, str)
            or not slot_id
            or not isinstance(field_id, str)
            or not field_id
            or not isinstance(style_role_id, str)
            or not style_role_id
            or not isinstance(style_role_type, str)
            or not isinstance(profile_ref, Mapping)
            or not isinstance(locator, str | Mapping)
        ):
            raise _failure(
                "style_capture_slot_invalid",
                "Every styled slot requires field, slot, role, profile ref, and locator.",
            )
        profile = registry.resolve(profile_ref)
        if profile.role_type != style_role_type:
            raise _failure(
                "style_capture_profile_role_mismatch",
                f"Slot {slot_id} role type does not match its profile.",
            )
        try:
            resolved = resolver.resolve(locator)
        except ToolFailure as error:
            observation = _failed_resolution_observation(
                field_id=field_id,
                slot_id=slot_id,
                style_role_id=style_role_id,
                profile=profile,
                reason=error.message,
            )
        else:
            observation = observe_effective_style(
                field_id=field_id,
                slot_id=slot_id,
                style_role_id=style_role_id,
                profile=profile,
                resolved=resolved,
            )
        observations.append(observation)

    observed_identities = {
        (item.slot_id, item.style_role_id) for item in observations
    }
    for expected in expected_roles:
        field_id = expected.get("field_id")
        slot_id = expected.get("slot_id")
        style_role_id = expected.get("style_role_id")
        style_role_type = expected.get("style_role_type")
        profile_ref = expected.get("property_profile_ref")
        if (
            not isinstance(field_id, str)
            or not field_id
            or not isinstance(slot_id, str)
            or not slot_id
            or not isinstance(style_role_id, str)
            or not style_role_id
            or not isinstance(style_role_type, str)
            or not isinstance(profile_ref, Mapping)
        ):
            raise _failure(
                "style_capture_expected_role_invalid",
                "Every expected role requires field, slot, role, role type, and profile ref.",
            )
        if (slot_id, style_role_id) in observed_identities:
            continue
        profile = registry.resolve(profile_ref)
        if profile.role_type != style_role_type:
            raise _failure(
                "style_capture_profile_role_mismatch",
                f"Expected role {style_role_id} does not match its profile.",
            )
        observations.append(
            _missing_role_observation(
                field_id=field_id,
                slot_id=slot_id,
                style_role_id=style_role_id,
                profile=profile,
            )
        )

    observation_set = FieldStyleObservationSet.build(
        template_sha256=sha256_file(document),
        profile_registry_digest=registry.registry_digest,
        observations=observations,
    )
    candidates, compiler_gaps, role_failures = _school_candidates(observation_set)
    known_gaps = [
        _gap_for_observation(item)
        for item in observation_set.observations
        if item.closure.school_role_eligibility
        == SchoolRoleEligibility.INCOMPLETE_KNOWN_GAPS
    ]
    known_gaps.extend(compiler_gaps)
    failed = [
        _failure_for_observation(item)
        for item in observation_set.observations
        if item.closure.school_role_eligibility == SchoolRoleEligibility.NOT_EVALUABLE
    ]
    failed.extend(role_failures)
    return SchoolStyleCapture(
        observation_set=observation_set,
        school_candidates=tuple(candidates),
        known_gaps=tuple(known_gaps),
        failed_observations=tuple(failed),
        non_style_slots=tuple(sorted(non_style_slots)),
    )


def compile_school_style_contracts(
    capture: SchoolStyleCapture,
    *,
    registry: StylePropertyProfileRegistry = DEFAULT_STYLE_PROPERTY_PROFILES,
) -> StyleContractSet | None:
    """Compile candidates that the current executable v2 seam can represent."""

    if capture.failed_observations or not capture.school_candidates:
        return None
    styles = [
        _legacy_contract_from_candidate(item, registry)
        for item in capture.school_candidates
    ]
    if any(item is None for item in styles):
        return None
    return StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": capture.observation_set.template_sha256,
            "styles": [item for item in styles if item is not None],
        }
    )


def _failed_resolution_observation(
    *,
    field_id: str,
    slot_id: str,
    style_role_id: str,
    profile: StylePropertyProfile,
    reason: str,
) -> FieldStyleObservation:
    properties = [
        PropertyObservation.build(
            profile=profile,
            property_path=definition.property_path,
            effective_state=(
                EffectiveState.NOT_APPLICABLE
                if definition.property_path in profile.n_a_properties
                else EffectiveState.UNRESOLVED
            ),
            school_evidence_status=(
                SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED
                if definition.property_path in profile.n_a_properties
                else SchoolEvidenceStatus.CONFLICT
            ),
            reason=(
                "profile_not_applicable"
                if definition.property_path in profile.n_a_properties
                else reason
            ),
        )
        for definition in profile.properties
    ]
    return FieldStyleObservation.build(
        field_id=field_id,
        slot_id=slot_id,
        style_role_id=style_role_id,
        profile=profile,
        properties=properties,
    )


def _missing_role_observation(
    *,
    field_id: str,
    slot_id: str,
    style_role_id: str,
    profile: StylePropertyProfile,
) -> FieldStyleObservation:
    properties = [
        PropertyObservation.build(
            profile=profile,
            property_path=definition.property_path,
            effective_state=(
                EffectiveState.NOT_APPLICABLE
                if definition.property_path in profile.n_a_properties
                else EffectiveState.UNRESOLVED
            ),
            school_evidence_status=(
                SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED
                if definition.property_path in profile.n_a_properties
                else SchoolEvidenceStatus.MISSING_SCHOOL_DECLARATION
            ),
            reason=(
                "profile_not_applicable"
                if definition.property_path in profile.n_a_properties
                else "school_role_representative_missing"
            ),
        )
        for definition in profile.properties
    ]
    return FieldStyleObservation.build(
        field_id=field_id,
        slot_id=slot_id,
        style_role_id=style_role_id,
        profile=profile,
        properties=properties,
    )


def _school_candidates(
    observation_set: FieldStyleObservationSet,
) -> tuple[list[JsonObject], list[JsonObject], list[JsonObject]]:
    by_role: dict[str, list[FieldStyleObservation]] = {}
    compiler_gaps: list[JsonObject] = []
    for observation in observation_set.observations:
        if observation.closure.school_role_eligibility == SchoolRoleEligibility.COMPLETE:
            by_role.setdefault(observation.style_role_id, []).append(observation)
    candidates: list[JsonObject] = []
    failures: list[JsonObject] = []
    for role_id, role_observations in sorted(by_role.items()):
        compiled = [_candidate_from_observation(item) for item in role_observations]
        if any(item is None for item in compiled):
            compiler_gaps.append(
                {
                    "style_role_id": role_id,
                    "reason": "current_style_contract_seam_cannot_encode_complete_observation",
                    "slot_ids": [item.slot_id for item in role_observations],
                }
            )
            continue
        concrete = [item for item in compiled if item is not None]
        digests = {str(item["candidate_digest"]) for item in concrete}
        if len(digests) != 1:
            failures.append(
                {
                    "style_role_id": role_id,
                    "reason": "conflicting_complete_school_observations",
                    "slot_ids": [item.slot_id for item in role_observations],
                    "candidate_digests": sorted(digests),
                }
            )
            continue
        selected = dict(concrete[0])
        selected["applies_to"] = sorted(
            {item.field_id for item in role_observations}
        )
        selected["evidence_refs"] = [
            {
                "type": "school_field_style_observation",
                "slot_id": item.slot_id,
                "observation_digest": item.observation_digest,
                "school_observation_set_digest": (
                    observation_set.school_observation_set_digest
                ),
            }
            for item in role_observations
        ]
        candidates.append(selected)
    return candidates, compiler_gaps, failures


def _candidate_from_observation(
    observation: FieldStyleObservation,
) -> JsonObject | None:
    executable = [
        item
        for item in observation.properties
        if item.effective_state != EffectiveState.NOT_APPLICABLE
    ]
    if any(
        item.effective_state not in {EffectiveState.VALUE, EffectiveState.NONE}
        for item in executable
    ):
        return None
    semantic_payload: JsonObject = {
        "schema_version": "docfit-school-style-role-candidate/v1",
        "style_role_id": observation.style_role_id,
        "style_role_type": observation.style_role_type,
        "property_profile_ref": dict(observation.profile_ref),
        "properties": [
            {
                "property_path": item.property_path,
                "effective_state": item.effective_state.value,
                **(
                    {"value": item.value}
                    if item.effective_state == EffectiveState.VALUE
                    else {}
                ),
            }
            for item in executable
        ],
    }
    return {
        **semantic_payload,
        "candidate_digest": sha256_json(semantic_payload),
    }


def _legacy_contract_from_candidate(
    candidate: Mapping[str, Any],
    registry: StylePropertyProfileRegistry,
) -> JsonObject | None:
    role_id = candidate.get("style_role_id")
    role_type = candidate.get("style_role_type")
    profile_ref = candidate.get("property_profile_ref")
    raw_properties = candidate.get("properties")
    if (
        not isinstance(role_id, str)
        or not isinstance(role_type, str)
        or not isinstance(profile_ref, Mapping)
        or not isinstance(raw_properties, Sequence)
        or isinstance(raw_properties, str | bytes)
    ):
        return None
    profile = registry.resolve(profile_ref)
    canonical: dict[str, Any] = {}
    for item in raw_properties:
        if (
            not isinstance(item, Mapping)
            or item.get("effective_state") != EffectiveState.VALUE.value
            or not isinstance(item.get("property_path"), str)
            or "value" not in item
        ):
            return None
        canonical[str(item["property_path"])] = item["value"]
    properties = _materializer_properties(profile, canonical)
    if properties is None or set(properties) - SUPPORTED_MATERIALIZED_PROPERTIES:
        return None
    style: JsonObject = {
        "style_contract_id": f"school.{role_id}",
        "label": f"School role {role_id}",
        "application_scope": _application_scope(role_type),
        "owned_properties": sorted(properties),
        "effective_properties": dict(sorted(properties.items())),
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": [],
        "applies_to": list(candidate.get("applies_to", [])),
        "evidence_refs": list(candidate.get("evidence_refs", [])),
    }
    style["contract_digest"] = style_contract_digest(style)
    return style


def _materializer_properties(
    profile: StylePropertyProfile,
    canonical: Mapping[str, Any],
) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    line_mode = canonical.get("paragraph.line_spacing.mode")
    for path, value in canonical.items():
        definition = profile.definition(path)
        if not definition.materializer_targets:
            return None
        if path == "run.color":
            result[definition.materializer_targets[0]] = (
                value.removeprefix("#") if isinstance(value, str) else value
            )
        elif path == "paragraph.line_spacing.mode":
            rule = {
                "single": "auto",
                "multiple": "auto",
                "exact_pt": "exact",
                "at_least_pt": "atLeast",
            }.get(value)
            if rule is None:
                return None
            result["paragraph.line_spacing_rule"] = rule
        elif path == "paragraph.line_spacing.value":
            target = (
                "paragraph.line_value"
                if line_mode in {"single", "multiple"}
                else "paragraph.line_spacing_pt"
            )
            result[target] = value
        else:
            for target in definition.materializer_targets:
                result[target] = value
    return result


def _gap_for_observation(observation: FieldStyleObservation) -> JsonObject:
    reasons = {
        item.reason
        for item in observation.properties
        if item.effective_state == EffectiveState.UNRESOLVED and item.reason is not None
    }
    return {
        "slot_id": observation.slot_id,
        "field_id": observation.field_id,
        "style_role_id": observation.style_role_id,
        "property_profile_ref": dict(observation.profile_ref),
        "property_paths": list(observation.closure.known_gap_properties),
        "unresolved_properties": list(observation.closure.unresolved_properties),
        "reason": (
            next(iter(reasons))
            if reasons == {"school_role_representative_missing"}
            else "incomplete_school_role_known_gaps"
        ),
    }


def _failure_for_observation(observation: FieldStyleObservation) -> JsonObject:
    return {
        "slot_id": observation.slot_id,
        "field_id": observation.field_id,
        "style_role_id": observation.style_role_id,
        "property_profile_ref": dict(observation.profile_ref),
        "failed_properties": list(observation.closure.failed_properties),
        "reason": "school_style_observation_not_evaluable",
    }


def _application_scope(role_type: str) -> str:
    if role_type == "character":
        return "run"
    if role_type in {"page_layout", "pagination", "section_start"}:
        return "section"
    if role_type in {"table_cell", "table_layout"}:
        return "table"
    return "paragraph"


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("inspect_template_again", "repair_template_style_role"),
    )
