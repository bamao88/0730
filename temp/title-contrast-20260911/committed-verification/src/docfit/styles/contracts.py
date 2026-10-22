"""Immutable Style Contract v2 domain model and loader."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

STYLE_CONTRACT_SCHEMA_VERSION = "docfit-style-contract-set/v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STYLE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PROPERTY_PATH = re.compile(r"^(run|paragraph|container|page)\.[a-z][a-z0-9_]*$")
_SCOPES = ("text", "run", "paragraph", "block", "table", "section")
_FILL_CONTRACT_SCHEMA_VERSION = "docfit-template-fill-contract/v2"


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_style_contract_set",),
    )


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze(item) for key, item in value.items()})


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _frozen_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _failure("style_contract_invalid", f"{field} must be a non-empty string.")
    if value != value.strip():
        raise _failure("style_contract_not_canonical", f"{field} cannot contain outer whitespace.")
    return value


def _optional_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field=field)


def _normalized_value(value: object, *, field: str) -> Any:
    if value is None or isinstance(value, bool | str):
        result: Any = value
    elif isinstance(value, int | float):
        result = value
    elif isinstance(value, Mapping):
        result = {
            _required_string(key, field=f"{field} key"): _normalized_value(
                item, field=f"{field}.{key}"
            )
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        result = [
            _normalized_value(item, field=f"{field}[]") for item in value
        ]
    else:
        raise _failure(
            "style_contract_invalid",
            f"{field} must be a deterministic JSON value.",
        )
    if isinstance(result, str):
        if result != result.strip():
            raise _failure(
                "style_contract_not_canonical", f"{field} cannot contain outer whitespace."
            )
        if field.endswith(".color") and re.fullmatch(r"[0-9a-fA-F]{6}", result):
            result = result.upper()
    return result


@dataclass(frozen=True, slots=True)
class OverridePolicy:
    """How owned and unowned formatting behaves during materialization."""

    managed_direct_formatting: str
    unmanaged_properties: str

    @classmethod
    def from_mapping(cls, value: object) -> OverridePolicy:
        if not isinstance(value, Mapping):
            raise _failure("style_contract_invalid", "override_policy must be an object.")
        if set(value) != {"managed_direct_formatting", "unmanaged_properties"}:
            raise _failure(
                "style_contract_invalid",
                "override_policy must declare exactly managed_direct_formatting and "
                "unmanaged_properties.",
            )
        managed = value.get("managed_direct_formatting")
        unmanaged = value.get("unmanaged_properties")
        if managed != "clear_conflicts" or unmanaged != "preserve":
            raise _failure(
                "style_contract_policy_unsupported",
                "Style Contract v2 requires clear_conflicts for managed direct formatting and "
                "preserve for unmanaged properties.",
            )
        return cls(managed_direct_formatting=managed, unmanaged_properties=unmanaged)

    def as_dict(self) -> JsonObject:
        return {
            "managed_direct_formatting": self.managed_direct_formatting,
            "unmanaged_properties": self.unmanaged_properties,
        }


@dataclass(frozen=True, slots=True)
class StyleContractRef:
    """Digest-bound reference to another style contract."""

    style_contract_id: str
    contract_digest: str

    @classmethod
    def from_mapping(cls, value: object) -> StyleContractRef:
        if not isinstance(value, Mapping) or set(value) != {
            "style_contract_id",
            "contract_digest",
        }:
            raise _failure(
                "style_contract_ref_invalid",
                "A style reference requires exactly style_contract_id and contract_digest.",
            )
        style_contract_id = _required_string(
            value.get("style_contract_id"), field="style_contract_id"
        )
        if not _STYLE_ID.fullmatch(style_contract_id):
            raise _failure(
                "style_contract_invalid",
                "style_contract_id must use lowercase letters, digits, dots, underscores, or "
                "hyphens.",
            )
        contract_digest = value.get("contract_digest")
        if not isinstance(contract_digest, str) or not _SHA256.fullmatch(contract_digest):
            raise _failure(
                "style_contract_ref_invalid",
                "A style reference contract_digest must be a lowercase SHA-256.",
            )
        return cls(style_contract_id, contract_digest)

    def as_dict(self) -> JsonObject:
        return {
            "style_contract_id": self.style_contract_id,
            "contract_digest": self.contract_digest,
        }


@dataclass(frozen=True, slots=True)
class StyleContract:
    """One stable, reusable effective-formatting contract."""

    style_contract_id: str
    contract_digest: str
    application_scope: str
    owned_properties: tuple[str, ...]
    effective_properties: Mapping[str, Any]
    override_policy: OverridePolicy
    dependencies: tuple[StyleContractRef, ...]
    word_style_id: str | None = None
    word_style_name: str | None = None
    label: str | None = None
    applies_to: tuple[str, ...] = ()
    evidence_refs: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, value: object) -> StyleContract:
        if not isinstance(value, Mapping):
            raise _failure("style_contract_invalid", "Each styles item must be an object.")
        allowed_keys = {
            "style_contract_id",
            "contract_digest",
            "application_scope",
            "owned_properties",
            "effective_properties",
            "override_policy",
            "dependencies",
            "word_style_id",
            "word_style_name",
            "label",
            "applies_to",
            "evidence_refs",
        }
        unknown = sorted(str(key) for key in set(value) - allowed_keys)
        if unknown:
            raise _failure(
                "style_contract_invalid",
                "Style Contract contains unsupported properties: " + ", ".join(unknown),
            )
        style_contract_id = _required_string(
            value.get("style_contract_id"), field="style_contract_id"
        )
        if not _STYLE_ID.fullmatch(style_contract_id):
            raise _failure(
                "style_contract_invalid",
                "style_contract_id must use lowercase letters, digits, dots, underscores, or "
                "hyphens.",
            )
        scope = _required_string(value.get("application_scope"), field="application_scope")
        if scope not in _SCOPES:
            raise _failure(
                "style_contract_scope_unsupported",
                f"application_scope must be one of {', '.join(_SCOPES)}.",
            )

        raw_owned = value.get("owned_properties")
        if not isinstance(raw_owned, Sequence) or isinstance(raw_owned, str | bytes):
            raise _failure("style_contract_invalid", "owned_properties must be a non-empty array.")
        owned_values = [
            _required_string(item, field="owned_properties[]") for item in raw_owned
        ]
        if len(set(owned_values)) != len(owned_values):
            raise _failure(
                "style_contract_invalid", "owned_properties cannot contain duplicates."
            )
        owned = tuple(sorted(owned_values))
        if not owned:
            raise _failure("style_contract_invalid", "owned_properties cannot be empty.")
        invalid_owned = [item for item in owned if not _PROPERTY_PATH.fullmatch(item)]
        if invalid_owned:
            raise _failure(
                "style_contract_invalid",
                "Unsupported owned property path: " + ", ".join(invalid_owned),
            )

        raw_effective = value.get("effective_properties")
        if not isinstance(raw_effective, Mapping):
            raise _failure("style_contract_invalid", "effective_properties must be an object.")
        effective: dict[str, Any] = {}
        for raw_key, item in raw_effective.items():
            key = _required_string(raw_key, field="effective_properties key")
            if not _PROPERTY_PATH.fullmatch(key):
                raise _failure(
                    "style_contract_invalid", f"Unsupported effective property path: {key}."
                )
            effective[key] = _normalized_value(item, field=key)
        missing = sorted(set(owned) - set(effective))
        if missing:
            raise _failure(
                "style_contract_owned_property_missing",
                "Every owned property must have an effective value; missing: " + ", ".join(missing),
            )

        raw_dependencies = value.get("dependencies")
        if not isinstance(raw_dependencies, Sequence) or isinstance(
            raw_dependencies, str | bytes
        ):
            raise _failure("style_contract_invalid", "dependencies must be an array.")
        dependencies = tuple(
            sorted(
                (StyleContractRef.from_mapping(item) for item in raw_dependencies),
                key=lambda item: item.style_contract_id,
            )
        )
        if len({item.style_contract_id for item in dependencies}) != len(dependencies):
            raise _failure(
                "style_contract_dependency_duplicate",
                f"{style_contract_id} contains duplicate dependency references.",
            )
        if style_contract_id in {item.style_contract_id for item in dependencies}:
            raise _failure(
                "style_contract_dependency_cycle",
                f"{style_contract_id} cannot depend on itself.",
            )
        policy = OverridePolicy.from_mapping(value.get("override_policy"))
        semantic_payload: JsonObject = {
            "style_contract_id": style_contract_id,
            "application_scope": scope,
            "owned_properties": list(owned),
            "effective_properties": dict(sorted(effective.items())),
            "override_policy": policy.as_dict(),
            "dependencies": [item.as_dict() for item in dependencies],
        }
        calculated = sha256_json(semantic_payload)
        contract_digest = value.get("contract_digest")
        if not isinstance(contract_digest, str) or not _SHA256.fullmatch(contract_digest):
            raise _failure(
                "style_contract_digest_invalid",
                "contract_digest must be a lowercase SHA-256.",
            )
        if contract_digest != calculated:
            raise _failure(
                "style_contract_digest_mismatch",
                f"The digest for {style_contract_id} does not match its normalized semantics.",
            )

        raw_evidence = value.get("evidence_refs", [])
        if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, str | bytes):
            raise _failure("style_contract_invalid", "evidence_refs must be an array.")
        evidence: list[Mapping[str, Any]] = []
        for item in raw_evidence:
            if not isinstance(item, Mapping):
                raise _failure("style_contract_invalid", "Every evidence_ref must be an object.")
            evidence.append(_frozen_mapping(item))
        raw_applies_to = value.get("applies_to", [])
        if not isinstance(raw_applies_to, Sequence) or isinstance(
            raw_applies_to, str | bytes
        ):
            raise _failure("style_contract_invalid", "applies_to must be an array.")
        applies_to = tuple(
            _required_string(item, field="applies_to[]") for item in raw_applies_to
        )
        if len(set(applies_to)) != len(applies_to):
            raise _failure("style_contract_invalid", "applies_to cannot contain duplicates.")
        return cls(
            style_contract_id=style_contract_id,
            contract_digest=contract_digest,
            application_scope=scope,
            owned_properties=owned,
            effective_properties=MappingProxyType(dict(sorted(effective.items()))),
            override_policy=policy,
            dependencies=dependencies,
            word_style_id=_optional_string(value.get("word_style_id"), field="word_style_id"),
            word_style_name=_optional_string(
                value.get("word_style_name"), field="word_style_name"
            ),
            label=_optional_string(value.get("label"), field="label"),
            applies_to=applies_to,
            evidence_refs=tuple(evidence),
        )

    def semantic_payload(self) -> JsonObject:
        return {
            "style_contract_id": self.style_contract_id,
            "application_scope": self.application_scope,
            "owned_properties": list(self.owned_properties),
            "effective_properties": dict(self.effective_properties),
            "override_policy": self.override_policy.as_dict(),
            "dependencies": [item.as_dict() for item in self.dependencies],
        }

    @property
    def digest(self) -> str:
        """Convenience accessor; serialized v2 contracts use contract_digest only."""

        return self.contract_digest

    def as_dict(self) -> JsonObject:
        result = self.semantic_payload()
        result["contract_digest"] = self.contract_digest
        for key, item in (
            ("word_style_id", self.word_style_id),
            ("word_style_name", self.word_style_name),
            ("label", self.label),
        ):
            if item is not None:
                result[key] = item
        if self.evidence_refs:
            result["evidence_refs"] = [_thaw(item) for item in self.evidence_refs]
        if self.applies_to:
            result["applies_to"] = list(self.applies_to)
        return result


def style_contract_digest(value: Mapping[str, Any]) -> str:
    """Return the semantic digest, excluding identity-neutral materialization hints."""

    semantic_keys = {
        "style_contract_id",
        "application_scope",
        "owned_properties",
        "effective_properties",
        "override_policy",
        "dependencies",
    }
    payload = {key: item for key, item in value.items() if key in semantic_keys}
    for key in ("owned_properties",):
        raw = payload.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, str | bytes):
            payload[key] = sorted(set(raw))
    effective = payload.get("effective_properties")
    if isinstance(effective, Mapping):
        payload["effective_properties"] = {
            str(key): _normalized_value(item, field=str(key))
            for key, item in sorted(effective.items(), key=lambda pair: str(pair[0]))
        }
    dependencies = payload.get("dependencies")
    if isinstance(dependencies, Sequence) and not isinstance(dependencies, str | bytes):
        normalized_dependencies: list[JsonObject] = []
        for item in dependencies:
            if not isinstance(item, Mapping):
                raise _failure(
                    "style_contract_invalid", "Every dependency must be a style reference object."
                )
            normalized_dependencies.append(StyleContractRef.from_mapping(item).as_dict())
        payload["dependencies"] = sorted(
            normalized_dependencies, key=lambda item: str(item["style_contract_id"])
        )
    return sha256_json(payload)


@dataclass(frozen=True, slots=True)
class StyleContractSet:
    """A template-bound immutable set with one source of style truth."""

    schema_version: str
    template_sha256: str
    styles: tuple[StyleContract, ...]
    digest: str

    @classmethod
    def load(cls, path: Path) -> StyleContractSet:
        try:
            value = json.loads(path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise _failure(
                "style_contract_set_unreadable", "The Style Contract Set JSON cannot be read."
            ) from error
        return cls.from_mapping(value)

    @classmethod
    def from_fill_contract(cls, value: Mapping[str, Any]) -> StyleContractSet:
        if value.get("schema_version") != _FILL_CONTRACT_SCHEMA_VERSION:
            raise _failure(
                "style_contract_fill_schema_unsupported",
                f"Style contracts require {_FILL_CONTRACT_SCHEMA_VERSION} fill contracts.",
            )
        template_sha256 = value.get("template_sha256")
        payload: JsonObject = {
            "schema_version": STYLE_CONTRACT_SCHEMA_VERSION,
            "template_sha256": template_sha256,
            "styles": value.get("styles"),
        }
        raw_digest = value.get("style_contract_set_digest")
        if raw_digest is not None:
            payload["style_contract_set_digest"] = raw_digest
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, value: object) -> StyleContractSet:
        if not isinstance(value, Mapping):
            raise _failure("style_contract_set_invalid", "Style Contract Set must be an object.")
        allowed_keys = {
            "schema_version",
            "template_sha256",
            "styles",
            "style_contract_set_digest",
        }
        unknown = sorted(str(key) for key in set(value) - allowed_keys)
        if unknown:
            raise _failure(
                "style_contract_set_invalid",
                "Style Contract Set contains unsupported properties: " + ", ".join(unknown),
            )
        if value.get("schema_version") != STYLE_CONTRACT_SCHEMA_VERSION:
            raise _failure(
                "style_contract_schema_unsupported",
                f"Only {STYLE_CONTRACT_SCHEMA_VERSION} is supported.",
            )
        template_sha256 = value.get("template_sha256")
        if not isinstance(template_sha256, str) or not _SHA256.fullmatch(template_sha256):
            raise _failure(
                "style_contract_template_digest_invalid",
                "template_sha256 must be a lowercase SHA-256.",
            )
        raw_styles = value.get("styles")
        if not isinstance(raw_styles, Sequence) or isinstance(raw_styles, str | bytes):
            raise _failure("style_contract_set_invalid", "styles must be an array.")
        styles = tuple(StyleContract.from_mapping(item) for item in raw_styles)
        by_id = {item.style_contract_id: item for item in styles}
        if len(by_id) != len(styles):
            raise _failure(
                "style_contract_id_duplicate", "style_contract_id values must be unique."
            )
        for item in styles:
            missing = sorted(
                dependency.style_contract_id
                for dependency in item.dependencies
                if dependency.style_contract_id not in by_id
            )
            if missing:
                raise _failure(
                    "style_contract_dependency_missing",
                    f"{item.style_contract_id} has unknown dependencies: {', '.join(missing)}.",
                )
            stale = [
                dependency.style_contract_id
                for dependency in item.dependencies
                if dependency.style_contract_id in by_id
                and dependency.contract_digest
                != by_id[dependency.style_contract_id].contract_digest
            ]
            if stale:
                raise _failure(
                    "style_contract_dependency_stale",
                    f"{item.style_contract_id} has stale dependencies: {', '.join(stale)}.",
                )
        _reject_dependency_cycles(by_id)
        normalized = tuple(sorted(styles, key=lambda item: item.style_contract_id))
        set_payload: JsonObject = {
            "schema_version": _FILL_CONTRACT_SCHEMA_VERSION,
            "template_sha256": template_sha256,
            "styles": [
                {
                    "style_contract_id": item.style_contract_id,
                    "contract_digest": item.contract_digest,
                }
                for item in normalized
            ],
        }
        calculated = sha256_json(set_payload)
        supplied = value.get("style_contract_set_digest")
        if supplied is not None and supplied != calculated:
            raise _failure(
                "style_contract_set_digest_mismatch",
                "The Style Contract Set digest does not match its normalized contents.",
            )
        return cls(
            schema_version=STYLE_CONTRACT_SCHEMA_VERSION,
            template_sha256=template_sha256,
            styles=normalized,
            digest=calculated,
        )

    def resolve(self, reference: Mapping[str, Any]) -> StyleContract:
        ref = StyleContractRef.from_mapping(reference)
        item = next(
            (
                style
                for style in self.styles
                if style.style_contract_id == ref.style_contract_id
            ),
            None,
        )
        if item is None:
            raise _failure(
                "style_contract_not_found",
                f"The Style Contract Set does not contain {ref.style_contract_id}.",
            )
        if ref.contract_digest != item.contract_digest:
            raise _failure(
                "style_contract_ref_stale",
                f"The reference digest for {ref.style_contract_id} is stale.",
            )
        return item

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": self.schema_version,
            "template_sha256": self.template_sha256,
            "styles": [item.as_dict() for item in self.styles],
            "style_contract_set_digest": self.digest,
        }


def _reject_dependency_cycles(styles: Mapping[str, StyleContract]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(style_id: str) -> None:
        if style_id in visiting:
            raise _failure(
                "style_contract_dependency_cycle",
                f"Style Contract dependency cycle detected at {style_id}.",
            )
        if style_id in visited:
            return
        visiting.add(style_id)
        for dependency in styles[style_id].dependencies:
            visit(dependency.style_contract_id)
        visiting.remove(style_id)
        visited.add(style_id)

    for style_id in styles:
        visit(style_id)
