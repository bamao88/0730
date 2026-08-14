"""Read and resolve an approved, versioned complete-role style preset."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import yaml

from docfit.styles.profiles import (
    DEFAULT_STYLE_PROPERTY_PROFILES,
    StylePropertyProfileRegistry,
)
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

PresetPropertyState = Literal["VALUE", "NONE", "N/A"]
_PARAMETER = re.compile(r"^\$\{([a-z][a-z0-9_]*)\}$")
_ROLE_ID = re.compile(r"^(style|layout)\.[a-z0-9][a-z0-9._-]*$")
_STYLE_COMPONENT_PRIORITY = (
    "content",
    "entry",
    "title",
    "generated_heading",
    "chapter_entry",
    "level1_entry",
    "level2_entry",
    "table_content",
    "header_cell",
    "body_cell",
)


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_style_preset",),
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    merged = {str(key): _thaw(value) for key, value in base.items()}
    for raw_key, value in update.items():
        key = str(raw_key)
        previous = merged.get(key)
        if isinstance(previous, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(previous, value)
        else:
            merged[key] = _thaw(value)
    return merged


def _nested_value(value: Mapping[str, Any], property_path: str) -> Any:
    current: Any = value
    for component in property_path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise KeyError(property_path)
        current = current[component]
    return current


def _substitute(value: Any, parameters: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        match = _PARAMETER.fullmatch(value)
        if match is None:
            return value
        name = match.group(1)
        if name not in parameters:
            raise _failure(
                "style_preset_parameter_missing",
                f"The preset references undeclared parameter {name}.",
            )
        return parameters[name]
    if isinstance(value, Mapping):
        return {str(key): _substitute(item, parameters) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_substitute(item, parameters) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class PresetProperty:
    """One typed, fully resolved preset property."""

    property_path: str
    state: PresetPropertyState
    value: Any = None

    def as_dict(self) -> JsonObject:
        result: JsonObject = {
            "property_path": self.property_path,
            "state": self.state,
        }
        if self.state == "VALUE":
            result["value"] = _thaw(self.value)
        return result


@dataclass(frozen=True, slots=True)
class PresetRole:
    """One complete semantic role after type and role inheritance resolution."""

    role_id: str
    role_type: str
    evidence_profile: str
    value_authority: str
    properties: tuple[PresetProperty, ...]

    def property_map(self) -> Mapping[str, PresetProperty]:
        return MappingProxyType({item.property_path: item for item in self.properties})

    def as_dict(self) -> JsonObject:
        return {
            "role_id": self.role_id,
            "role_type": self.role_type,
            "evidence_profile": self.evidence_profile,
            "value_authority": self.value_authority,
            "properties": [item.as_dict() for item in self.properties],
        }


@dataclass(frozen=True, slots=True)
class FieldStyleBinding:
    """Preset role references for one semantic content field."""

    field_id: str
    handling: str
    components: Mapping[str, str]

    @property
    def style_role_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                role_id for role_id in self.components.values() if role_id.startswith("style.")
            )
        )

    @property
    def primary_style_role_id(self) -> str | None:
        for component in _STYLE_COMPONENT_PRIORITY:
            role_id = self.components.get(component)
            if isinstance(role_id, str) and role_id.startswith("style."):
                return role_id
        return self.style_role_ids[0] if self.style_role_ids else None


class GeneralStylePreset:
    """Validated preset graph whose roles are complete before runtime selection."""

    def __init__(
        self,
        *,
        preset_id: str,
        preset_version: str,
        parameters: Mapping[str, Any],
        roles: Mapping[str, PresetRole],
        fields: Mapping[str, FieldStyleBinding],
        profile_registry_digest: str | None,
    ) -> None:
        self.preset_id = preset_id
        self.preset_version = preset_version
        self.parameters = MappingProxyType(dict(parameters))
        self._roles = MappingProxyType(dict(roles))
        self._fields = MappingProxyType(dict(fields))
        self.profile_registry_digest = profile_registry_digest
        self.digest = sha256_json(self.as_dict(include_digest=False))

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        registry: StylePropertyProfileRegistry = DEFAULT_STYLE_PROPERTY_PROFILES,
    ) -> GeneralStylePreset:
        source = path.expanduser().resolve(strict=True)
        try:
            value = yaml.safe_load(source.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise _failure("style_preset_unreadable", "The style preset cannot be read.") from error
        return cls.from_mapping(value, registry=registry)

    @classmethod
    def from_mapping(
        cls,
        value: object,
        *,
        registry: StylePropertyProfileRegistry | None = None,
    ) -> GeneralStylePreset:
        if not isinstance(value, Mapping):
            raise _failure("style_preset_invalid", "The style preset must be an object.")
        schema_version = value.get("schema_version")
        if schema_version != "docfit-general-style-preset/v1.0":
            raise _failure("style_preset_schema_unsupported", "Unsupported style preset schema.")
        if value.get("status") != "product_definition_accepted":
            raise _failure(
                "style_preset_not_accepted",
                "Only a human-accepted product preset may participate in runtime selection.",
            )
        preset_id = value.get("preset_id")
        preset_version = value.get("preset_version")
        if not isinstance(preset_id, str) or not preset_id:
            raise _failure("style_preset_invalid", "preset_id must be a non-empty string.")
        if not isinstance(preset_version, str) or not preset_version:
            raise _failure("style_preset_invalid", "preset_version must be a non-empty string.")
        parameters = _parameter_defaults(value.get("parameters"))
        required = _required_property_profiles(
            value.get("required_effective_properties"), registry=registry
        )
        type_profiles = value.get("complete_style_type_profiles")
        role_values = value.get("style_roles")
        if not isinstance(type_profiles, Mapping) or not isinstance(role_values, Mapping):
            raise _failure(
                "style_preset_invalid", "The preset requires type profiles and style roles."
            )
        roles = _resolve_roles(
            type_profiles=type_profiles,
            role_values=role_values,
            required=required,
            parameters=parameters,
        )
        fields = _field_bindings(value.get("field_handling"), roles)
        return cls(
            preset_id=preset_id,
            preset_version=preset_version,
            parameters=parameters,
            roles=roles,
            fields=fields,
            profile_registry_digest=(
                registry.registry_digest if registry is not None else None
            ),
        )

    def resolve_role(self, role_id: str) -> PresetRole:
        try:
            return self._roles[role_id]
        except KeyError as error:
            raise _failure(
                "style_preset_role_missing", f"The preset has no complete role {role_id}."
            ) from error

    def field_binding(self, field_id: str) -> FieldStyleBinding:
        try:
            return self._fields[field_id]
        except KeyError as error:
            raise _failure(
                "style_preset_field_missing", f"The preset has no field handling for {field_id}."
            ) from error

    def as_dict(self, *, include_digest: bool = True) -> JsonObject:
        result: JsonObject = {
            "schema_version": "docfit-general-style-preset-runtime/v1",
            "preset_id": self.preset_id,
            "preset_version": self.preset_version,
            "parameters": dict(self.parameters),
            "roles": [self._roles[key].as_dict() for key in sorted(self._roles)],
            "fields": [
                {
                    "field_id": binding.field_id,
                    "handling": binding.handling,
                    "components": dict(binding.components),
                }
                for _, binding in sorted(self._fields.items())
            ],
        }
        if self.profile_registry_digest is not None:
            result["profile_registry_digest"] = self.profile_registry_digest
        if include_digest:
            result["preset_digest"] = self.digest
        return result


def _parameter_defaults(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _failure("style_preset_invalid", "The preset requires parameter definitions.")
    defaults: dict[str, Any] = {}
    for raw_name, raw_definition in value.items():
        name = str(raw_name)
        if not isinstance(raw_definition, Mapping) or raw_definition.get("enabled") is not True:
            raise _failure(
                "style_preset_parameter_invalid", f"Parameter {name} is not enabled."
            )
        default = raw_definition.get("default")
        declared_type = raw_definition.get("type")
        if declared_type == "string" and (not isinstance(default, str) or not default):
            raise _failure(
                "style_preset_parameter_invalid", f"Parameter {name} needs a string default."
            )
        defaults[name] = default
    return defaults


def _required_property_profiles(
    value: object,
    *,
    registry: StylePropertyProfileRegistry | None,
) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        raise _failure("style_preset_invalid", "The preset requires property profiles.")
    profiles: dict[str, tuple[str, ...]] = {}
    for raw_role_type, raw_paths in value.items():
        role_type = str(raw_role_type)
        if not isinstance(raw_paths, Sequence) or isinstance(raw_paths, str | bytes):
            raise _failure(
                "style_preset_profile_invalid", f"Profile {role_type} must be an array."
            )
        paths = tuple(str(path) for path in raw_paths)
        if not paths or len(paths) != len(set(paths)) or any(not path for path in paths):
            raise _failure(
                "style_preset_profile_invalid",
                f"Profile {role_type} must contain unique non-empty properties.",
            )
        if registry is not None:
            expected = registry.for_role_type(role_type).property_paths
            if paths != expected:
                raise _failure(
                    "style_preset_profile_registry_mismatch",
                    f"Preset profile {role_type} does not match the accepted Registry list.",
                )
        profiles[role_type] = paths
    return profiles


def _resolve_roles(
    *,
    type_profiles: Mapping[Any, Any],
    role_values: Mapping[Any, Any],
    required: Mapping[str, tuple[str, ...]],
    parameters: Mapping[str, Any],
) -> dict[str, PresetRole]:
    resolved_payloads: dict[str, dict[str, Any]] = {}
    visiting: set[str] = set()

    def resolve_payload(role_id: str) -> dict[str, Any]:
        if role_id in resolved_payloads:
            return resolved_payloads[role_id]
        if role_id in visiting:
            raise _failure("style_preset_role_cycle", f"Role inheritance cycle at {role_id}.")
        raw = role_values.get(role_id)
        if not isinstance(raw, Mapping):
            raise _failure("style_preset_role_missing", f"Missing role {role_id}.")
        role_type = raw.get("role_type")
        if not isinstance(role_type, str) or role_type not in required:
            raise _failure(
                "style_preset_role_type_invalid", f"Role {role_id} has no known role type."
            )
        type_profile = type_profiles.get(role_type)
        if not isinstance(type_profile, Mapping):
            raise _failure(
                "style_preset_profile_missing", f"Role type {role_type} has no type profile."
            )
        visiting.add(role_id)
        merged = _deep_merge({}, type_profile)
        based_on = raw.get("based_on")
        if based_on is not None:
            if not isinstance(based_on, str) or not _ROLE_ID.fullmatch(based_on):
                raise _failure(
                    "style_preset_role_base_invalid", f"Role {role_id} has an invalid base."
                )
            base = resolve_payload(based_on)
            if base["role_type"] != role_type:
                raise _failure(
                    "style_preset_role_type_mismatch",
                    f"Role {role_id} cannot inherit a different role type.",
                )
            merged = _deep_merge(merged, base)
        direct = {
            str(key): item
            for key, item in raw.items()
            if key
            not in {
                "based_on",
                "complete",
                "evidence_profile",
                "kind",
                "rationale",
                "role_type",
                "value_authority",
                "overrides",
                "property_source_overrides",
            }
        }
        merged = _deep_merge(merged, direct)
        overrides = raw.get("overrides", {})
        if not isinstance(overrides, Mapping):
            raise _failure(
                "style_preset_role_invalid", f"Role {role_id} overrides must be an object."
            )
        merged = _deep_merge(merged, overrides)
        merged.update(
            {
                "role_type": role_type,
                "evidence_profile": raw.get("evidence_profile"),
                "value_authority": raw.get("value_authority"),
            }
        )
        substituted = _substitute(merged, parameters)
        assert isinstance(substituted, dict)
        visiting.remove(role_id)
        resolved_payloads[role_id] = substituted
        return substituted

    roles: dict[str, PresetRole] = {}
    for raw_role_id in role_values:
        role_id = str(raw_role_id)
        if not _ROLE_ID.fullmatch(role_id) or not role_id.startswith("style."):
            raise _failure("style_preset_role_invalid", f"Invalid style role id {role_id}.")
        payload = resolve_payload(role_id)
        role_type = str(payload["role_type"])
        properties: list[PresetProperty] = []
        for property_path in required[role_type]:
            try:
                property_value = _nested_value(payload, property_path)
            except KeyError as error:
                raise _failure(
                    "style_preset_role_incomplete",
                    f"Role {role_id} is missing {property_path}.",
                ) from error
            if property_value == "N/A":
                properties.append(PresetProperty(property_path, "N/A"))
            elif property_value == "none":
                properties.append(PresetProperty(property_path, "NONE"))
            elif property_value is None or property_value == "":
                raise _failure(
                    "style_preset_role_incomplete",
                    f"Role {role_id} has a blank value for {property_path}.",
                )
            else:
                properties.append(
                    PresetProperty(property_path, "VALUE", _freeze(property_value))
                )
        evidence_profile = payload.get("evidence_profile")
        value_authority = payload.get("value_authority")
        if not isinstance(evidence_profile, str) or not isinstance(value_authority, str):
            raise _failure(
                "style_preset_role_invalid",
                f"Role {role_id} requires evidence_profile and value_authority.",
            )
        roles[role_id] = PresetRole(
            role_id=role_id,
            role_type=role_type,
            evidence_profile=evidence_profile,
            value_authority=value_authority,
            properties=tuple(properties),
        )
    return roles


def _field_bindings(
    value: object, roles: Mapping[str, PresetRole]
) -> dict[str, FieldStyleBinding]:
    if not isinstance(value, Mapping):
        raise _failure("style_preset_invalid", "The preset requires field handling.")
    fields: dict[str, FieldStyleBinding] = {}
    for raw_field_id, raw in value.items():
        field_id = str(raw_field_id)
        if not isinstance(raw, Mapping) or not isinstance(raw.get("handling"), str):
            raise _failure(
                "style_preset_field_invalid", f"Field {field_id} has invalid handling."
            )
        raw_components = raw.get("components", {})
        if not isinstance(raw_components, Mapping):
            raise _failure(
                "style_preset_field_invalid", f"Field {field_id} components must be an object."
            )
        components = {
            str(key): str(item)
            for key, item in raw_components.items()
            if isinstance(item, str)
        }
        missing_roles = sorted(
            role_id
            for role_id in components.values()
            if role_id.startswith("style.") and role_id not in roles
        )
        if missing_roles:
            raise _failure(
                "style_preset_field_role_missing",
                f"Field {field_id} references missing roles: {', '.join(missing_roles)}.",
            )
        fields[field_id] = FieldStyleBinding(
            field_id=field_id,
            handling=str(raw["handling"]),
            components=MappingProxyType(components),
        )
    return fields


__all__ = [
    "FieldStyleBinding",
    "GeneralStylePreset",
    "PresetProperty",
    "PresetRole",
]
