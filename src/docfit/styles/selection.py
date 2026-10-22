"""Select one complete school or preset role for every task-local actual role."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from docfit.styles.actual_roles import ActualStyleRoleSet
from docfit.styles.contracts import StyleContractSet, style_contract_digest
from docfit.styles.materialization import SUPPORTED_MATERIALIZED_PROPERTIES
from docfit.styles.presets import GeneralStylePreset, PresetProperty
from docfit.styles.profiles import StylePropertyProfile, StylePropertyProfileRegistry
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

SelectionSource = Literal["school", "preset"]
SelectedPropertyState = Literal["VALUE", "NONE", "N/A"]


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_style_role_selection_inputs",),
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class SelectedStyleProperty:
    property_path: str
    effective_state: SelectedPropertyState
    value: Any = None

    def as_dict(self) -> JsonObject:
        result: JsonObject = {
            "property_path": self.property_path,
            "effective_state": self.effective_state,
        }
        if self.effective_state == "VALUE":
            result["value"] = _json_value(self.value)
        return result


@dataclass(frozen=True, slots=True)
class SelectedStyleRole:
    style_role_id: str
    style_role_type: str
    source: SelectionSource
    source_digest: str
    property_profile_ref: JsonObject
    properties: tuple[SelectedStyleProperty, ...]
    school_gap_refs: tuple[JsonObject, ...] = ()

    def contract_semantics(self) -> JsonObject:
        return {
            "style_role_id": self.style_role_id,
            "style_role_type": self.style_role_type,
            "property_profile_ref": dict(self.property_profile_ref),
            "properties": [item.as_dict() for item in self.properties],
        }

    def as_dict(self) -> JsonObject:
        result: JsonObject = {
            **self.contract_semantics(),
            "source": self.source,
            "source_digest": self.source_digest,
        }
        if self.school_gap_refs:
            result["school_gap_refs"] = [dict(item) for item in self.school_gap_refs]
        return result


@dataclass(frozen=True, slots=True)
class StyleRoleSelectionReceipt:
    profile_registry_digest: str
    school_observation_set_digest: str
    actual_role_set_digest: str
    preset_id: str
    preset_version: str
    preset_digest: str
    selections: tuple[SelectedStyleRole, ...]
    selected_style_contract_set_digest: str
    selection_receipt_digest: str

    def as_dict(self) -> JsonObject:
        counts = Counter(item.source for item in self.selections)
        return {
            "schema_version": "docfit-style-role-selection-receipt/v1",
            "profile_registry_digest": self.profile_registry_digest,
            "school_observation_set_digest": self.school_observation_set_digest,
            "actual_role_set_digest": self.actual_role_set_digest,
            "preset_ref": {
                "preset_id": self.preset_id,
                "preset_version": self.preset_version,
                "preset_digest": self.preset_digest,
            },
            "selections": [item.as_dict() for item in self.selections],
            "selection_counts": {
                "school": counts.get("school", 0),
                "preset": counts.get("preset", 0),
            },
            "selected_style_contract_set_digest": (
                self.selected_style_contract_set_digest
            ),
            "selection_receipt_digest": self.selection_receipt_digest,
        }


def select_complete_style_roles(
    *,
    actual_roles: ActualStyleRoleSet,
    school_candidates: Sequence[Mapping[str, Any]],
    school_known_gaps: Sequence[Mapping[str, Any]],
    school_observation_set_digest: str,
    preset: GeneralStylePreset,
    registry: StylePropertyProfileRegistry,
) -> StyleRoleSelectionReceipt:
    """Choose roles atomically; candidate corruption never degrades into preset fallback."""

    if preset.profile_registry_digest != registry.registry_digest:
        raise _failure(
            "style_selection_profile_registry_mismatch",
            "The accepted preset is not bound to the current Style Property Profile Registry.",
        )
    if actual_roles.preset_digest != preset.digest:
        raise _failure(
            "style_selection_actual_roles_stale",
            "The actual role set was compiled from a different preset identity.",
        )
    if len(school_observation_set_digest) != 64:
        raise _failure(
            "style_selection_observation_digest_invalid",
            "school_observation_set_digest must be a SHA-256 identity.",
        )
    candidates: dict[str, Mapping[str, Any]] = {}
    for candidate in school_candidates:
        role_id = candidate.get("style_role_id")
        if not isinstance(role_id, str) or not role_id:
            raise _failure(
                "style_selection_school_candidate_invalid",
                "Every school candidate requires a semantic style_role_id.",
            )
        if role_id in candidates:
            raise _failure(
                "style_selection_school_candidate_duplicate",
                f"More than one complete school candidate exists for {role_id}.",
            )
        candidates[role_id] = candidate
    gaps_by_role = _raw_known_gaps_by_role(school_known_gaps)

    selections: list[SelectedStyleRole] = []
    for actual in actual_roles.roles:
        profile = registry.for_role_type(actual.role_type)
        school = candidates.get(actual.style_role_id)
        if school is not None:
            selection = _school_selection(
                school,
                style_role_id=actual.style_role_id,
                profile=profile,
                school_observation_set_digest=school_observation_set_digest,
            )
        else:
            school_gap_refs = _validated_known_gaps_for_role(
                gaps_by_role.get(actual.style_role_id, ()),
                style_role_id=actual.style_role_id,
                profile=profile,
            )
            if not school_gap_refs:
                raise _failure(
                    "style_selection_school_known_gap_missing",
                    (
                        f"Preset fallback for {actual.style_role_id} requires an "
                        "explicit known school style gap from the template package."
                    ),
                )
            role = preset.resolve_role(actual.style_role_id)
            if role.role_type != actual.role_type:
                raise _failure(
                    "style_selection_preset_role_type_mismatch",
                    f"Preset role {actual.style_role_id} has the wrong role type.",
                )
            selection = _preset_selection(
                role.properties,
                role.role_id,
                profile,
                preset,
                school_gap_refs=school_gap_refs,
            )
        selections.append(selection)
    normalized = tuple(sorted(selections, key=lambda item: item.style_role_id))
    contract_payload: JsonObject = {
        "schema_version": "docfit-selected-style-contract-set/v1",
        "profile_registry_digest": registry.registry_digest,
        "roles": [item.contract_semantics() for item in normalized],
    }
    selected_digest = sha256_json(contract_payload)
    receipt_payload: JsonObject = {
        "schema_version": "docfit-style-role-selection-receipt/v1",
        "profile_registry_digest": registry.registry_digest,
        "school_observation_set_digest": school_observation_set_digest,
        "actual_role_set_digest": actual_roles.actual_role_set_digest,
        "preset_ref": {
            "preset_id": preset.preset_id,
            "preset_version": preset.preset_version,
            "preset_digest": preset.digest,
        },
        "selections": [item.as_dict() for item in normalized],
        "selected_style_contract_set_digest": selected_digest,
    }
    return StyleRoleSelectionReceipt(
        profile_registry_digest=registry.registry_digest,
        school_observation_set_digest=school_observation_set_digest,
        actual_role_set_digest=actual_roles.actual_role_set_digest,
        preset_id=preset.preset_id,
        preset_version=preset.preset_version,
        preset_digest=preset.digest,
        selections=normalized,
        selected_style_contract_set_digest=selected_digest,
        selection_receipt_digest=sha256_json(receipt_payload),
    )


def compile_selected_style_contracts(
    *,
    receipt: StyleRoleSelectionReceipt,
    template_sha256: str,
    registry: StylePropertyProfileRegistry,
) -> StyleContractSet:
    """Compile typed selected roles only when every property has an executable codec."""

    if receipt.profile_registry_digest != registry.registry_digest:
        raise _failure(
            "style_selection_profile_registry_mismatch",
            "The selection receipt is bound to another Style Property Profile Registry.",
        )
    styles: list[JsonObject] = []
    for selection in receipt.selections:
        profile = registry.for_role_type(selection.style_role_type)
        if selection.property_profile_ref != profile.ref().as_dict():
            raise _failure(
                "style_selection_profile_registry_mismatch",
                f"Selected role {selection.style_role_id} has a stale profile ref.",
            )
        effective = _execution_properties(selection.properties, profile)
        evidence_refs: list[JsonObject] = [
            {
                "type": "style_role_selection",
                "source": selection.source,
                "source_digest": selection.source_digest,
                "selected_style_contract_set_digest": (
                    receipt.selected_style_contract_set_digest
                ),
            }
        ]
        evidence_refs.extend(
            {
                "type": "school_style_known_gap",
                **dict(gap_ref),
            }
            for gap_ref in selection.school_gap_refs
        )
        style: JsonObject = {
            "style_contract_id": f"selected.{selection.style_role_id}",
            "label": f"Selected role {selection.style_role_id}",
            "application_scope": _application_scope(selection.style_role_type),
            "owned_properties": sorted(effective),
            "effective_properties": dict(sorted(effective.items())),
            "override_policy": {
                "managed_direct_formatting": "clear_conflicts",
                "unmanaged_properties": "preserve",
            },
            "dependencies": [],
            "evidence_refs": evidence_refs,
        }
        style["contract_digest"] = style_contract_digest(style)
        styles.append(style)
    return StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": template_sha256,
            "styles": styles,
        }
    )


def _execution_properties(
    properties: Sequence[SelectedStyleProperty],
    profile: StylePropertyProfile,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    values = {item.property_path: item for item in properties}
    line_mode = values.get("paragraph.line_spacing.mode")
    for item in properties:
        if item.effective_state == "N/A":
            continue
        definition = profile.definition(item.property_path)
        targets = definition.materializer_targets
        if not targets or any(
            target not in SUPPORTED_MATERIALIZED_PROPERTIES for target in targets
        ):
            raise _failure(
                "style_selection_property_codec_missing",
                f"{item.property_path} has no complete materializer/reopen codec.",
            )
        if item.effective_state == "NONE":
            for target in targets:
                result[target] = None
            continue
        value = item.value
        if item.property_path == "run.color":
            value = value.removeprefix("#") if isinstance(value, str) else value
            result[targets[0]] = value
        elif item.property_path == "paragraph.line_spacing.mode":
            rule = {
                "single": "auto",
                "multiple": "auto",
                "exact_pt": "exact",
                "at_least_pt": "atLeast",
            }.get(value)
            if rule is None:
                raise _failure(
                    "style_selection_property_value_invalid",
                    "paragraph.line_spacing.mode has an unsupported value.",
                )
            result["paragraph.line_spacing_rule"] = rule
        elif item.property_path == "paragraph.line_spacing.value":
            if line_mode is None or line_mode.effective_state != "VALUE":
                raise _failure(
                    "style_selection_property_value_invalid",
                    "Line-spacing value requires a selected line-spacing mode.",
                )
            target = (
                "paragraph.line_value"
                if line_mode.value in {"single", "multiple"}
                else "paragraph.line_spacing_pt"
            )
            result[target] = value
        elif item.property_path == "numbering":
            if not isinstance(value, Mapping) or "num_id" not in value:
                raise _failure(
                    "style_selection_property_codec_missing",
                    "numbering VALUE requires a compiled Word numbering definition.",
                )
            result[targets[0]] = value
        elif item.property_path == "tab_stops":
            if not isinstance(value, Sequence) or isinstance(value, str | bytes) or any(
                not isinstance(tab, Mapping)
                or not isinstance(tab.get("position_twips"), int)
                for tab in value
            ):
                raise _failure(
                    "style_selection_property_codec_missing",
                    "tab_stops VALUE requires layout-resolved Word positions.",
                )
            result[targets[0]] = list(value)
        else:
            for target in targets:
                result[target] = value
    return result


def _application_scope(role_type: str) -> str:
    if role_type == "character":
        return "run"
    if role_type == "table_cell":
        return "table"
    return "paragraph"


def _school_selection(
    candidate: Mapping[str, Any],
    *,
    style_role_id: str,
    profile: StylePropertyProfile,
    school_observation_set_digest: str,
) -> SelectedStyleRole:
    if candidate.get("schema_version") != "docfit-school-style-role-candidate/v1":
        raise _failure(
            "style_selection_school_candidate_invalid",
            f"School candidate {style_role_id} has an unsupported schema.",
        )
    if candidate.get("style_role_type") != profile.role_type:
        raise _failure(
            "style_selection_school_candidate_role_type_mismatch",
            f"School candidate {style_role_id} has the wrong role type.",
        )
    profile_ref = candidate.get("property_profile_ref")
    if not isinstance(profile_ref, Mapping):
        raise _failure(
            "style_selection_school_candidate_invalid",
            f"School candidate {style_role_id} has no profile ref.",
        )
    if dict(profile_ref) != profile.ref().as_dict():
        raise _failure(
            "style_selection_school_candidate_profile_mismatch",
            f"School candidate {style_role_id} is bound to another profile.",
        )
    evidence_refs = candidate.get("evidence_refs")
    if not isinstance(evidence_refs, Sequence) or isinstance(evidence_refs, str | bytes):
        raise _failure(
            "style_selection_school_candidate_invalid",
            f"School candidate {style_role_id} has no observation evidence.",
        )
    if not evidence_refs or any(
        not isinstance(item, Mapping)
        or item.get("school_observation_set_digest") != school_observation_set_digest
        for item in evidence_refs
    ):
        raise _failure(
            "style_selection_school_candidate_observation_stale",
            f"School candidate {style_role_id} is not bound to the current observation set.",
        )
    properties = _selected_properties(candidate.get("properties"), profile)
    semantic_payload: JsonObject = {
        "schema_version": "docfit-school-style-role-candidate/v1",
        "style_role_id": style_role_id,
        "style_role_type": profile.role_type,
        "property_profile_ref": profile.ref().as_dict(),
        "properties": [item.as_dict() for item in properties],
    }
    candidate_digest = candidate.get("candidate_digest")
    if candidate_digest != sha256_json(semantic_payload):
        raise _failure(
            "style_selection_school_candidate_digest_mismatch",
            f"School candidate {style_role_id} has a stale digest.",
        )
    return SelectedStyleRole(
        style_role_id=style_role_id,
        style_role_type=profile.role_type,
        source="school",
        source_digest=str(candidate_digest),
        property_profile_ref=profile.ref().as_dict(),
        properties=properties,
    )


def _preset_selection(
    raw_properties: Sequence[PresetProperty],
    style_role_id: str,
    profile: StylePropertyProfile,
    preset: GeneralStylePreset,
    *,
    school_gap_refs: Sequence[Mapping[str, Any]],
) -> SelectedStyleRole:
    properties = tuple(
        SelectedStyleProperty(
            property_path=item.property_path,
            effective_state=item.state,
            value=item.value,
        )
        for item in raw_properties
    )
    _validate_property_closure(properties, profile)
    role_payload: JsonObject = {
        "preset_digest": preset.digest,
        "style_role_id": style_role_id,
        "properties": [item.as_dict() for item in properties],
    }
    return SelectedStyleRole(
        style_role_id=style_role_id,
        style_role_type=profile.role_type,
        source="preset",
        source_digest=sha256_json(role_payload),
        property_profile_ref=profile.ref().as_dict(),
        properties=properties,
        school_gap_refs=tuple(dict(item) for item in school_gap_refs),
    )


def _raw_known_gaps_by_role(
    known_gaps: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    if isinstance(known_gaps, str | bytes):
        raise _failure(
            "style_selection_known_gap_invalid",
            "Known school style gaps must be an array.",
        )
    for gap in known_gaps:
        if not isinstance(gap, Mapping):
            raise _failure(
                "style_selection_known_gap_invalid",
                "Every known school style gap must be an object.",
            )
        role_id = gap.get("style_role_id")
        if not isinstance(role_id, str) or not role_id:
            raise _failure(
                "style_selection_known_gap_invalid",
                "Every known school style gap requires style_role_id.",
            )
        result.setdefault(role_id, []).append(gap)
    return {
        role_id: tuple(items)
        for role_id, items in sorted(result.items())
    }


def _validated_known_gaps_for_role(
    raw_gaps: Sequence[Mapping[str, Any]],
    *,
    style_role_id: str,
    profile: StylePropertyProfile,
) -> tuple[JsonObject, ...]:
    refs: list[JsonObject] = []
    profile_paths = set(profile.property_paths)
    for raw in raw_gaps:
        profile_ref = raw.get("property_profile_ref")
        if not isinstance(profile_ref, Mapping) or dict(profile_ref) != profile.ref().as_dict():
            raise _failure(
                "style_selection_known_gap_profile_mismatch",
                f"Known gap for {style_role_id} is not bound to the current style profile.",
            )
        reason = raw.get("reason")
        property_paths = raw.get("property_paths")
        if (
            not isinstance(reason, str)
            or not reason
            or not isinstance(property_paths, Sequence)
            or isinstance(property_paths, str | bytes)
            or not property_paths
            or any(not isinstance(path, str) for path in property_paths)
        ):
            raise _failure(
                "style_selection_known_gap_invalid",
                f"Known gap for {style_role_id} has no typed gap properties.",
            )
        property_tuple = tuple(str(path) for path in property_paths)
        unknown = sorted(set(property_tuple) - profile_paths)
        if unknown:
            raise _failure(
                "style_selection_known_gap_property_mismatch",
                (
                    f"Known gap for {style_role_id} cites properties outside its "
                    "style profile: " + ", ".join(unknown)
                ),
            )
        ref: JsonObject = {
            "style_role_id": style_role_id,
            "property_profile_ref": profile.ref().as_dict(),
            "reason": reason,
            "property_paths": list(property_tuple),
        }
        for optional_key in ("field_id", "slot_id"):
            value = raw.get(optional_key)
            if isinstance(value, str) and value:
                ref[optional_key] = value
        for optional_key in ("slot_ids", "unresolved_properties"):
            value = raw.get(optional_key)
            if (
                isinstance(value, Sequence)
                and not isinstance(value, str | bytes)
                and all(isinstance(item, str) for item in value)
            ):
                ref[optional_key] = list(value)
        ref["known_gap_digest"] = sha256_json(
            {
                "schema_version": "docfit-school-style-known-gap-ref/v1",
                **ref,
            }
        )
        refs.append(ref)
    return tuple(
        sorted(
            refs,
            key=lambda item: (
                str(item.get("reason", "")),
                str(item.get("field_id", "")),
                str(item.get("slot_id", "")),
                str(item["known_gap_digest"]),
            ),
        )
    )


def _selected_properties(
    value: object,
    profile: StylePropertyProfile,
) -> tuple[SelectedStyleProperty, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise _failure(
            "style_selection_property_closure_invalid",
            f"Role {profile.role_type} has no fixed property list.",
        )
    properties: list[SelectedStyleProperty] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise _failure(
                "style_selection_property_closure_invalid",
                "Every selected style property must be an object.",
            )
        path = item.get("property_path")
        state = item.get("effective_state")
        if not isinstance(path, str) or state not in {"VALUE", "NONE", "N/A"}:
            raise _failure(
                "style_selection_property_closure_invalid",
                "Selected style properties require a path and typed effective state.",
            )
        if state == "VALUE" and "value" not in item:
            raise _failure(
                "style_selection_property_closure_invalid",
                f"{path} VALUE requires a value.",
            )
        if state != "VALUE" and "value" in item:
            raise _failure(
                "style_selection_property_closure_invalid",
                f"{path} {state} cannot carry a value.",
            )
        properties.append(
            SelectedStyleProperty(
                property_path=path,
                effective_state=state,
                value=item.get("value"),
            )
        )
    result = tuple(properties)
    _validate_property_closure(result, profile)
    return result


def _validate_property_closure(
    properties: Sequence[SelectedStyleProperty],
    profile: StylePropertyProfile,
) -> None:
    paths = tuple(item.property_path for item in properties)
    if paths != profile.property_paths:
        raise _failure(
            "style_selection_property_closure_invalid",
            f"Selected role {profile.role_type} does not match its fixed property profile.",
        )
    for item in properties:
        definition = profile.definition(item.property_path)
        if item.effective_state == "NONE" and not definition.allows_none:
            raise _failure(
                "style_selection_property_state_invalid",
                f"{item.property_path} has no NONE semantics.",
            )
        if item.effective_state == "N/A" and item.property_path not in profile.n_a_properties:
            raise _failure(
                "style_selection_property_state_invalid",
                f"{item.property_path} cannot be N/A for {profile.role_type}.",
            )
        if (
            item.property_path in profile.n_a_properties
            and item.effective_state != "N/A"
        ):
            raise _failure(
                "style_selection_property_state_invalid",
                f"{item.property_path} must be N/A for {profile.role_type}.",
            )


__all__ = [
    "SelectedStyleProperty",
    "SelectedStyleRole",
    "StyleRoleSelectionReceipt",
    "compile_selected_style_contracts",
    "select_complete_style_roles",
]
