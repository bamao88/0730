"""Fixed-list, dual-axis school style observations and closure aggregation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from docfit.styles.profiles import PropertyDefinition, StylePropertyProfile
from docfit.styles.resolver import EffectiveStyleResult, PropertyProvenance
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

OBSERVATION_SCHEMA_VERSION = "docfit-field-style-observation/v1"
OBSERVATION_SET_SCHEMA_VERSION = "docfit-school-style-observation-set/v1"


class EffectiveState(StrEnum):
    VALUE = "VALUE"
    NONE = "NONE"
    NOT_APPLICABLE = "N/A"
    UNRESOLVED = "UNRESOLVED"


class SchoolEvidenceStatus(StrEnum):
    EXPLICIT_OR_VERIFIED = "EXPLICIT_OR_VERIFIED"
    IMPLICIT_WORD_DEFAULT_ONLY = "IMPLICIT_WORD_DEFAULT_ONLY"
    MISSING_SCHOOL_DECLARATION = "MISSING_SCHOOL_DECLARATION"
    CONFLICT = "CONFLICT"
    RESOLVER_UNSUPPORTED = "RESOLVER_UNSUPPORTED"


class ObservationClosure(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class SchoolRoleEligibility(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_KNOWN_GAPS = "INCOMPLETE_KNOWN_GAPS"
    NOT_EVALUABLE = "NOT_EVALUABLE"


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_school_style_observation",),
    )


@dataclass(frozen=True, slots=True)
class PropertyObservation:
    property_path: str
    effective_state: EffectiveState
    school_evidence_status: SchoolEvidenceStatus
    value: Any = None
    provenance: tuple[PropertyProvenance, ...] = ()
    reason: str | None = None

    @classmethod
    def build(
        cls,
        *,
        profile: StylePropertyProfile,
        property_path: str,
        effective_state: EffectiveState,
        school_evidence_status: SchoolEvidenceStatus,
        value: Any = None,
        provenance: Sequence[PropertyProvenance] = (),
        reason: str | None = None,
    ) -> PropertyObservation:
        definition = profile.definition(property_path)
        if effective_state == EffectiveState.VALUE:
            if value is None:
                raise _failure(
                    "style_observation_value_missing",
                    f"{property_path} VALUE requires a non-null value.",
                )
        elif value is not None:
            raise _failure(
                "style_observation_value_forbidden",
                f"{property_path} {effective_state.value} cannot carry a value.",
            )
        if effective_state == EffectiveState.NONE and not definition.allows_none:
            raise _failure(
                "style_observation_none_forbidden",
                f"{property_path} has no defined NONE semantics.",
            )
        if effective_state == EffectiveState.NOT_APPLICABLE and not definition.allows_n_a:
            raise _failure(
                "style_observation_n_a_forbidden",
                f"{property_path} cannot be N/A in this profile.",
            )
        _validate_axes(property_path, effective_state, school_evidence_status)
        return cls(
            property_path=property_path,
            effective_state=effective_state,
            school_evidence_status=school_evidence_status,
            value=value,
            provenance=tuple(provenance),
            reason=reason,
        )

    def as_dict(self) -> JsonObject:
        result: JsonObject = {
            "property_path": self.property_path,
            "effective_state": self.effective_state.value,
            "school_evidence_status": self.school_evidence_status.value,
            "provenance": [item.as_dict() for item in self.provenance],
        }
        if self.effective_state == EffectiveState.VALUE:
            result["value"] = self.value
        if self.reason is not None:
            result["reason"] = self.reason
        return result


def _validate_axes(
    property_path: str,
    state: EffectiveState,
    evidence: SchoolEvidenceStatus,
) -> None:
    if evidence == SchoolEvidenceStatus.IMPLICIT_WORD_DEFAULT_ONLY and state not in {
        EffectiveState.VALUE,
        EffectiveState.NONE,
    }:
        raise _failure(
            "style_observation_axes_invalid",
            f"{property_path} implicit Word default must have a determined effective state.",
        )
    if evidence in {
        SchoolEvidenceStatus.MISSING_SCHOOL_DECLARATION,
        SchoolEvidenceStatus.CONFLICT,
        SchoolEvidenceStatus.RESOLVER_UNSUPPORTED,
    } and state != EffectiveState.UNRESOLVED:
        raise _failure(
            "style_observation_axes_invalid",
            f"{property_path} {evidence.value} requires UNRESOLVED.",
        )
    if state == EffectiveState.UNRESOLVED and evidence not in {
        SchoolEvidenceStatus.MISSING_SCHOOL_DECLARATION,
        SchoolEvidenceStatus.CONFLICT,
        SchoolEvidenceStatus.RESOLVER_UNSUPPORTED,
    }:
        raise _failure(
            "style_observation_axes_invalid",
            f"{property_path} UNRESOLVED requires a gap, conflict, or unsupported status.",
        )
    if state == EffectiveState.NOT_APPLICABLE and evidence != (
        SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED
    ):
        raise _failure(
            "style_observation_axes_invalid",
            f"{property_path} N/A must be an explicit profile classification.",
        )


@dataclass(frozen=True, slots=True)
class ObservationClosureSummary:
    observation_closure: ObservationClosure
    school_role_eligibility: SchoolRoleEligibility
    known_gap_properties: tuple[str, ...]
    unresolved_properties: tuple[str, ...]
    failed_properties: tuple[str, ...]
    effective_state_counts: Mapping[str, int]
    school_evidence_counts: Mapping[str, int]

    def as_dict(self) -> JsonObject:
        return {
            "observation_closure": self.observation_closure.value,
            "school_role_eligibility": self.school_role_eligibility.value,
            "known_gap_properties": list(self.known_gap_properties),
            "unresolved_properties": list(self.unresolved_properties),
            "failed_properties": list(self.failed_properties),
            "effective_state_counts": dict(self.effective_state_counts),
            "school_evidence_counts": dict(self.school_evidence_counts),
        }


@dataclass(frozen=True, slots=True)
class FieldStyleObservation:
    field_id: str
    slot_id: str
    style_role_id: str
    style_role_type: str
    profile_ref: JsonObject
    properties: tuple[PropertyObservation, ...]
    closure: ObservationClosureSummary
    observation_digest: str

    @classmethod
    def build(
        cls,
        *,
        field_id: str,
        slot_id: str,
        style_role_id: str,
        profile: StylePropertyProfile,
        properties: Sequence[PropertyObservation],
    ) -> FieldStyleObservation:
        paths = tuple(item.property_path for item in properties)
        if paths != profile.property_paths:
            missing = sorted(set(profile.property_paths) - set(paths))
            extra = sorted(set(paths) - set(profile.property_paths))
            raise _failure(
                "style_observation_property_closure_invalid",
                f"{slot_id} does not match its fixed profile property list; "
                f"missing={missing}, extra={extra}.",
            )
        closure = aggregate_observation_closure(profile, properties)
        profile_ref = profile.ref().as_dict()
        payload: JsonObject = {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "field_id": field_id,
            "slot_id": slot_id,
            "style_role_id": style_role_id,
            "style_role_type": profile.role_type,
            "property_profile_ref": profile_ref,
            "properties": [item.as_dict() for item in properties],
            "closure": closure.as_dict(),
        }
        return cls(
            field_id=field_id,
            slot_id=slot_id,
            style_role_id=style_role_id,
            style_role_type=profile.role_type,
            profile_ref=profile_ref,
            properties=tuple(properties),
            closure=closure,
            observation_digest=sha256_json(payload),
        )

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "field_id": self.field_id,
            "slot_id": self.slot_id,
            "style_role_id": self.style_role_id,
            "style_role_type": self.style_role_type,
            "property_profile_ref": dict(self.profile_ref),
            "properties": [item.as_dict() for item in self.properties],
            "closure": self.closure.as_dict(),
            "observation_digest": self.observation_digest,
        }


def aggregate_observation_closure(
    profile: StylePropertyProfile,
    properties: Sequence[PropertyObservation],
) -> ObservationClosureSummary:
    failed = tuple(
        item.property_path
        for item in properties
        if item.school_evidence_status
        in {SchoolEvidenceStatus.CONFLICT, SchoolEvidenceStatus.RESOLVER_UNSUPPORTED}
    )
    unresolved = tuple(
        item.property_path
        for item in properties
        if item.effective_state == EffectiveState.UNRESOLVED
    )
    known_gaps: list[str] = []
    for item in properties:
        definition = profile.definition(item.property_path)
        is_known_gap = (
            item.school_evidence_status
            == SchoolEvidenceStatus.MISSING_SCHOOL_DECLARATION
            or (
            item.school_evidence_status
            == SchoolEvidenceStatus.IMPLICIT_WORD_DEFAULT_ONLY
            and not definition.implicit_default_is_candidate_eligible
            )
            or (
                item.effective_state
                in {EffectiveState.VALUE, EffectiveState.NONE}
                and not (
                    definition.explicitly_materializable
                    and definition.reopen_validatable
                )
            )
        )
        if is_known_gap:
            known_gaps.append(item.property_path)
    observation_closure = (
        ObservationClosure.FAILED if failed else ObservationClosure.COMPLETE
    )
    if observation_closure == ObservationClosure.FAILED:
        eligibility = SchoolRoleEligibility.NOT_EVALUABLE
    elif known_gaps or unresolved:
        eligibility = SchoolRoleEligibility.INCOMPLETE_KNOWN_GAPS
    else:
        eligibility = SchoolRoleEligibility.COMPLETE
    effective_counts = Counter(item.effective_state.value for item in properties)
    evidence_counts = Counter(item.school_evidence_status.value for item in properties)
    return ObservationClosureSummary(
        observation_closure=observation_closure,
        school_role_eligibility=eligibility,
        known_gap_properties=tuple(dict.fromkeys(known_gaps)),
        unresolved_properties=unresolved,
        failed_properties=failed,
        effective_state_counts=dict(sorted(effective_counts.items())),
        school_evidence_counts=dict(sorted(evidence_counts.items())),
    )


def observe_effective_style(
    *,
    field_id: str,
    slot_id: str,
    style_role_id: str,
    profile: StylePropertyProfile,
    resolved: EffectiveStyleResult,
) -> FieldStyleObservation:
    """Project one resolver result onto every fixed profile property path."""

    observations: list[PropertyObservation] = []
    resolver_conflict = "; ".join(resolved.unresolved) if resolved.unresolved else None
    for definition in profile.properties:
        path = definition.property_path
        if path in profile.n_a_properties:
            observations.append(
                PropertyObservation.build(
                    profile=profile,
                    property_path=path,
                    effective_state=EffectiveState.NOT_APPLICABLE,
                    school_evidence_status=SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED,
                    reason="profile_not_applicable",
                )
            )
            continue
        if resolver_conflict is not None:
            observations.append(
                PropertyObservation.build(
                    profile=profile,
                    property_path=path,
                    effective_state=EffectiveState.UNRESOLVED,
                    school_evidence_status=SchoolEvidenceStatus.CONFLICT,
                    reason=resolver_conflict,
                )
            )
            continue
        if not definition.resolver_supported:
            observations.append(
                PropertyObservation.build(
                    profile=profile,
                    property_path=path,
                    effective_state=EffectiveState.UNRESOLVED,
                    school_evidence_status=SchoolEvidenceStatus.RESOLVER_UNSUPPORTED,
                    reason=f"{definition.resolution_strategy}:{path}",
                )
            )
            continue
        resolution, value, provenance, reason = _canonical_resolved_property(
            definition, resolved
        )
        if resolution == "conflict":
            observations.append(
                PropertyObservation.build(
                    profile=profile,
                    property_path=path,
                    effective_state=EffectiveState.UNRESOLVED,
                    school_evidence_status=SchoolEvidenceStatus.CONFLICT,
                    reason=reason,
                )
            )
            continue
        if resolution == "missing":
            observations.append(
                PropertyObservation.build(
                    profile=profile,
                    property_path=path,
                    effective_state=EffectiveState.UNRESOLVED,
                    school_evidence_status=(
                        SchoolEvidenceStatus.MISSING_SCHOOL_DECLARATION
                    ),
                    reason="no_school_value_or_portable_implicit_default",
                )
            )
            continue
        implicit_only = bool(provenance) and all(
            item.source_kind == "word_implicit_default" for item in provenance
        )
        state = EffectiveState.NONE if value is None else EffectiveState.VALUE
        evidence = (
            SchoolEvidenceStatus.IMPLICIT_WORD_DEFAULT_ONLY
            if implicit_only
            else SchoolEvidenceStatus.EXPLICIT_OR_VERIFIED
        )
        observations.append(
            PropertyObservation.build(
                profile=profile,
                property_path=path,
                effective_state=state,
                school_evidence_status=evidence,
                value=value if state == EffectiveState.VALUE else None,
                provenance=provenance,
            )
        )
    return FieldStyleObservation.build(
        field_id=field_id,
        slot_id=slot_id,
        style_role_id=style_role_id,
        profile=profile,
        properties=observations,
    )


def _canonical_resolved_property(
    definition: PropertyDefinition,
    resolved: EffectiveStyleResult,
) -> tuple[str, Any, tuple[PropertyProvenance, ...], str | None]:
    sources = definition.resolver_sources
    available = [path for path in sources if path in resolved.coverage]
    provenance = tuple(
        item
        for path in available
        for item in resolved.provenance.get(path, ())
    )
    strategy = definition.canonicalization
    if strategy == "identity":
        if not available:
            return "missing", None, (), "resolver_source_absent"
        source = sources[0]
        if source not in resolved.coverage:
            return "missing", None, provenance, "resolver_source_absent"
        return "value", resolved.properties[source], provenance, None
    if strategy == "equal_word_font_pair":
        if any(path not in resolved.coverage for path in sources):
            return "missing", None, provenance, "latin_font_source_absent"
        values = {resolved.properties[path] for path in sources}
        if len(values) != 1:
            return "conflict", None, provenance, "ascii_and_hansi_fonts_conflict"
        return "value", next(iter(values)), provenance, None
    if strategy == "word_hex_color_v1":
        if not available:
            return "missing", None, (), "color_source_absent"
        raw = resolved.properties[sources[0]]
        value = f"#{raw}" if isinstance(raw, str) and raw != "auto" else raw
        return "value", value, provenance, None
    if strategy in {"word_line_spacing_mode_v1", "word_line_spacing_value_v1"}:
        rule = resolved.properties.get("paragraph.line_spacing_rule")
        if rule is None:
            return "missing", None, provenance, "line_spacing_rule_absent"
        if strategy == "word_line_spacing_mode_v1":
            if rule == "auto":
                multiple = resolved.properties.get("paragraph.line_value")
                value = "single" if multiple == 1 else "multiple"
            elif rule == "exact":
                value = "exact_pt"
            elif rule == "atLeast":
                value = "at_least_pt"
            else:
                return "conflict", None, provenance, f"unknown_line_spacing_rule:{rule}"
            return "value", value, provenance, None
        source = (
            "paragraph.line_value"
            if rule == "auto"
            else "paragraph.line_spacing_pt"
        )
        if source not in resolved.coverage:
            return "missing", None, provenance, f"{source}_absent"
        return "value", resolved.properties[source], provenance, None
    return "missing", None, provenance, "canonicalization_not_implemented"


@dataclass(frozen=True, slots=True)
class FieldStyleObservationSet:
    template_sha256: str
    profile_registry_digest: str
    observations: tuple[FieldStyleObservation, ...]
    school_observation_set_digest: str

    @classmethod
    def build(
        cls,
        *,
        template_sha256: str,
        profile_registry_digest: str,
        observations: Sequence[FieldStyleObservation],
    ) -> FieldStyleObservationSet:
        normalized = tuple(
            sorted(observations, key=lambda item: (item.slot_id, item.style_role_id))
        )
        identities = {(item.slot_id, item.style_role_id) for item in normalized}
        if len(identities) != len(normalized):
            raise _failure(
                "style_observation_duplicate",
                "Observation slot/style-role identities must be unique.",
            )
        payload: JsonObject = {
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
            "template_sha256": template_sha256,
            "profile_registry_digest": profile_registry_digest,
            "observations": [
                {
                    "slot_id": item.slot_id,
                    "style_role_id": item.style_role_id,
                    "observation_digest": item.observation_digest,
                }
                for item in normalized
            ],
        }
        return cls(
            template_sha256=template_sha256,
            profile_registry_digest=profile_registry_digest,
            observations=normalized,
            school_observation_set_digest=sha256_json(payload),
        )

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
            "template_sha256": self.template_sha256,
            "profile_registry_digest": self.profile_registry_digest,
            "observations": [item.as_dict() for item in self.observations],
            "school_observation_set_digest": self.school_observation_set_digest,
        }
