"""Load and validate versioned Eval inputs before document analysis."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast

import yaml
from jsonschema import Draft202012Validator

from .models import (
    CaseDefinition,
    ComponentLocator,
    EffectiveStyle,
    EvalConfig,
    EvalInputs,
    FieldRegistry,
    FileReference,
    FillContract,
    Locator,
    Owner,
    RegionContract,
    RegistryField,
    ResponsibilityPolicy,
    ScoringConfig,
    SlotContract,
    StyleContract,
    StyleContractRef,
    StyleOverridePolicy,
)

SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schemas"
FILL_CONTRACT_V1 = "docfit-template-fill-contract/v1"
FILL_CONTRACT_V2 = "docfit-template-fill-contract/v2"


class InputErrorCode(StrEnum):
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    YAML_INVALID = "YAML_INVALID"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    HASH_MISMATCH = "HASH_MISMATCH"
    DUPLICATE_ID = "DUPLICATE_ID"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    SCORING_INVALID = "SCORING_INVALID"
    GOLD_NOT_ACCEPTED = "GOLD_NOT_ACCEPTED"
    DOCX_INVALID = "DOCX_INVALID"


class InputContractError(ValueError):
    """Structured preflight failure that must not produce a quality score."""

    def __init__(self, code: InputErrorCode, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code.value,
            "message": str(self),
            "path": None if self.path is None else self.path.as_posix(),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raise(code: InputErrorCode, message: str, path: Path | None = None) -> NoReturn:
    raise InputContractError(code, message, path=path)


def _require_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        _raise(InputErrorCode.FILE_NOT_FOUND, "required input file does not exist", resolved)
    return resolved


def _load_yaml(path: Path) -> dict[str, Any]:
    path = _require_file(path)
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        _raise(InputErrorCode.YAML_INVALID, f"cannot parse YAML: {error}", path)
    if not isinstance(value, dict):
        _raise(InputErrorCode.YAML_INVALID, "YAML root must be a mapping", path)
    return cast(dict[str, Any], value)


def _schema(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8")),
    )


def _validate_schema(value: dict[str, Any], schema_name: str, path: Path) -> None:
    errors = sorted(
        Draft202012Validator(_schema(schema_name)).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        _raise(
            InputErrorCode.SCHEMA_INVALID,
            f"{schema_name} validation failed at {location}: {error.message}",
            path,
        )


def _resolve(base: Path, reference: str) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return _require_file(candidate)
    return _require_file(base / candidate)


def _reference(base: Path, value: dict[str, Any]) -> FileReference:
    return FileReference(
        path=_resolve(base, str(value["path"])),
        id=str(value["id"]),
        version=str(value["version"]),
        sha256=str(value["sha256"]),
    )


def load_case(path: Path) -> CaseDefinition:
    case_path = _require_file(path)
    value = _load_yaml(case_path)
    _validate_schema(value, "case.schema.json", case_path)
    base = case_path.parent
    gold = cast(dict[str, Any], value["gold"])
    gold_review = cast(dict[str, Any], value.get("gold_review", {}))
    return CaseDefinition(
        schema_version=str(value["schema_version"]),
        case_id=str(value["case_id"]),
        case_path=case_path,
        gold_template_path=_resolve(base, str(gold["template"])),
        gold_contract_path=_resolve(base, str(gold["contract"])),
        registry_ref=_reference(base, cast(dict[str, Any], value["field_registry_ref"])),
        eval_config_ref=_reference(base, cast(dict[str, Any], value["eval_config"])),
        scoring_version=str(value["scoring_version"]),
        expected_verdict=(
            None if value.get("expected_verdict") is None else str(value["expected_verdict"])
        ),
        case_status=_optional_str(value, "case_status"),
        gold_review_status=_optional_str(gold_review, "status"),
    )


def _locator(value: dict[str, Any]) -> Locator:
    return Locator(
        type=str(value["type"]),
        story=str(value["story"]),
        part=str(value["part"]),
        expected_match_count=int(value["expected_match_count"]),
        value=None if value.get("value") is None else str(value["value"]),
        section_index=_optional_int(value, "section_index"),
        paragraph_index=_optional_int(value, "paragraph_index"),
        table_index=_optional_int(value, "table_index"),
        row=_optional_int(value, "row"),
        cell=_optional_int(value, "cell"),
        left_anchor=_optional_str(value, "left_anchor"),
        right_anchor=_optional_str(value, "right_anchor"),
        occurrence=_optional_int(value, "occurrence"),
        start=_optional_int(value, "start"),
        end=_optional_int(value, "end"),
    )


def _optional_locator(value: dict[str, Any], key: str) -> Locator | None:
    item = value.get(key)
    return None if item is None else _locator(cast(dict[str, Any], item))


def _component_locator(value: dict[str, Any]) -> ComponentLocator:
    wrapped = value.get("locator")
    locator_value = value if wrapped is None else cast(dict[str, Any], wrapped)
    return ComponentLocator(
        locator=_locator(locator_value),
        role=None if wrapped is None else _optional_str(value, "role"),
    )


def _marker_protocol_version(value: Any) -> str:
    if isinstance(value, dict):
        return str(value["version"])
    return str(value)


def _optional_int(value: dict[str, Any], key: str) -> int | None:
    item = value.get(key)
    return None if item is None else int(item)


def _optional_str(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    return None if item is None else str(item)


def _style(value: dict[str, Any] | None) -> EffectiveStyle | None:
    if value is None:
        return None
    return EffectiveStyle(
        font=dict(cast(dict[str, Any], value.get("font", {}))),
        paragraph=dict(cast(dict[str, Any], value.get("paragraph", {}))),
        container=dict(cast(dict[str, Any], value.get("container", {}))),
        page=dict(cast(dict[str, Any], value.get("page", {}))),
    )


def _style_contract_ref(value: Mapping[str, Any]) -> StyleContractRef:
    return StyleContractRef(
        style_contract_id=str(value["style_contract_id"]),
        contract_digest=str(value["contract_digest"]),
    )


def _canonical_style_contract_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    dependencies = sorted(
        (
            {
                "style_contract_id": str(item["style_contract_id"]),
                "contract_digest": str(item["contract_digest"]),
            }
            for item in cast(list[dict[str, Any]], value["dependencies"])
        ),
        key=lambda item: (item["style_contract_id"], item["contract_digest"]),
    )
    return {
        "style_contract_id": str(value["style_contract_id"]),
        "application_scope": str(value["application_scope"]),
        "owned_properties": sorted(str(item) for item in value["owned_properties"]),
        "effective_properties": cast(dict[str, Any], value["effective_properties"]),
        "override_policy": cast(dict[str, Any], value["override_policy"]),
        "dependencies": dependencies,
    }


def _canonical_json_digest(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError(f"style contract contains non-canonical JSON: {error}") from error
    return hashlib.sha256(payload).hexdigest()


def compute_style_contract_digest(value: Mapping[str, Any]) -> str:
    """Return the v2 semantic digest, excluding materialization hints and evidence."""

    return _canonical_json_digest(_canonical_style_contract_payload(value))


def compute_style_contract_set_digest(
    *,
    schema_version: str,
    template_sha256: str,
    styles: list[Mapping[str, Any]],
) -> str:
    """Bind the ordered style identity set to one template snapshot."""

    style_refs = sorted(
        (
            {
                "style_contract_id": str(style["style_contract_id"]),
                "contract_digest": str(style["contract_digest"]),
            }
            for style in styles
        ),
        key=lambda item: (item["style_contract_id"], item["contract_digest"]),
    )
    return _canonical_json_digest(
        {
            "schema_version": schema_version,
            "template_sha256": template_sha256,
            "styles": style_refs,
        }
    )


def _require_owned_properties(
    style: StyleContract,
    *,
    path: Path,
) -> None:
    for property_path in style.owned_properties:
        if property_path not in style.effective_properties:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"style {style.style_contract_id} owns missing effective property "
                f"{property_path}",
                path,
            )


def _require_style_reference_closure(
    styles: tuple[StyleContract, ...],
    slots: tuple[SlotContract, ...],
    *,
    path: Path,
) -> None:
    styles_by_id = {style.style_contract_id: style for style in styles}

    def require_reference(reference: StyleContractRef, owner: str) -> None:
        target = styles_by_id.get(reference.style_contract_id)
        if target is None:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"{owner} references missing style {reference.style_contract_id}",
                path,
            )
        if target.contract_digest != reference.contract_digest:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"{owner} style digest does not match {reference.style_contract_id}",
                path,
            )

    for slot in slots:
        if slot.style_contract_ref is None:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"v2 slot {slot.slot_id} has no style contract reference",
                path,
            )
        require_reference(slot.style_contract_ref, f"slot {slot.slot_id}")
    for style in styles:
        for dependency in style.dependencies:
            require_reference(dependency, f"style {style.style_contract_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(style_id: str) -> None:
        if style_id in visiting:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"style dependency cycle includes {style_id}",
                path,
            )
        if style_id in visited:
            return
        visiting.add(style_id)
        for dependency in styles_by_id[style_id].dependencies:
            visit(dependency.style_contract_id)
        visiting.remove(style_id)
        visited.add(style_id)

    for style_id in styles_by_id:
        visit(style_id)


def _legacy_slot_style(
    value: dict[str, Any],
    legacy_styles: Mapping[str, EffectiveStyle],
    *,
    path: Path,
) -> EffectiveStyle:
    inline = cast(dict[str, Any] | None, value.get("expected_value_style"))
    if inline is not None:
        return cast(EffectiveStyle, _style(inline))
    style_id = _optional_str(value, "style_id")
    if style_id is not None and style_id in legacy_styles:
        return legacy_styles[style_id]
    _raise(
        InputErrorCode.CONTRACT_MISMATCH,
        f"legacy slot {value['slot_id']} cannot resolve style {style_id}",
        path,
    )


def _load_fill_contract_value(value: dict[str, Any], contract_path: Path) -> FillContract:
    registry_ref = cast(dict[str, Any], value["field_registry_ref"])
    schema_version = str(value["schema_version"])
    regions = tuple(
        RegionContract(
            region_id=str(item["region_id"]),
            owner=Owner(str(item["owner"])),
            required=bool(item["required"]),
            locator=_optional_locator(item, "locator"),
            start_locator=_optional_locator(item, "start_locator"),
            end_locator=_optional_locator(item, "end_locator"),
            field_ids=tuple(str(field_id) for field_id in item.get("field_ids", [])),
            placement_mode=_optional_str(item, "placement_mode"),
            text=_optional_str(item, "text"),
            forbidden_text=_optional_str(item, "forbidden_text"),
            object_kind=_optional_str(item, "object_kind"),
            object_sha256=_optional_str(item, "object_sha256"),
            expected_style=_style(cast(dict[str, Any] | None, item.get("expected_style"))),
        )
        for item in cast(list[dict[str, Any]], value["regions"])
    )
    styles: tuple[StyleContract, ...] = ()
    styles_by_id: dict[str, StyleContract] = {}
    legacy_styles: dict[str, EffectiveStyle] = {}
    if schema_version == FILL_CONTRACT_V1:
        legacy_style_values = cast(list[dict[str, Any]], value.get("styles", []))
        _require_unique(
            [str(item["style_id"]) for item in legacy_style_values],
            "legacy style_id",
            contract_path,
        )
        legacy_styles = {
            str(item["style_id"]): cast(
                EffectiveStyle,
                _style(cast(dict[str, Any], item["effective_properties"])),
            )
            for item in legacy_style_values
        }
    if schema_version == FILL_CONTRACT_V2:
        style_values = cast(list[dict[str, Any]], value["styles"])
        styles = tuple(
            StyleContract(
                style_contract_id=str(item["style_contract_id"]),
                contract_digest=str(item["contract_digest"]),
                owned_properties=tuple(str(path) for path in item["owned_properties"]),
                effective_properties=dict(
                    cast(dict[str, Any], item["effective_properties"])
                ),
                application_scope=str(item["application_scope"]),
                override_policy=StyleOverridePolicy(
                    managed_direct_formatting=str(
                        cast(dict[str, Any], item["override_policy"])[
                            "managed_direct_formatting"
                        ]
                    ),
                    unmanaged_properties=str(
                        cast(dict[str, Any], item["override_policy"])[
                            "unmanaged_properties"
                        ]
                    ),
                ),
                dependencies=tuple(
                    _style_contract_ref(dependency)
                    for dependency in cast(list[dict[str, Any]], item["dependencies"])
                ),
                word_style_id=_optional_str(item, "word_style_id"),
                word_style_name=_optional_str(item, "word_style_name"),
            )
            for item in style_values
        )
        _require_unique(
            [style.style_contract_id for style in styles],
            "style_contract_id",
            contract_path,
        )
        for raw_style, style in zip(style_values, styles, strict=True):
            try:
                expected_digest = compute_style_contract_digest(raw_style)
            except ValueError as error:
                _raise(InputErrorCode.CONTRACT_MISMATCH, str(error), contract_path)
            if style.contract_digest != expected_digest:
                _raise(
                    InputErrorCode.HASH_MISMATCH,
                    f"style {style.style_contract_id} digest mismatch: expected "
                    f"{expected_digest}, got {style.contract_digest}",
                    contract_path,
                )
            _require_owned_properties(style, path=contract_path)
        expected_set_digest = compute_style_contract_set_digest(
            schema_version=schema_version,
            template_sha256=str(value["template_sha256"]),
            styles=cast(list[Mapping[str, Any]], style_values),
        )
        actual_set_digest = str(value["style_contract_set_digest"])
        if actual_set_digest != expected_set_digest:
            _raise(
                InputErrorCode.HASH_MISMATCH,
                f"style contract set digest mismatch: expected {expected_set_digest}, "
                f"got {actual_set_digest}",
                contract_path,
            )
        styles_by_id = {style.style_contract_id: style for style in styles}
    slots = tuple(
        SlotContract(
            slot_id=str(item["slot_id"]),
            field_id=str(item["field_id"]),
            content_type=str(item["content_type"]),
            required=bool(item["required"]),
            cardinality=str(item.get("cardinality", "one")),
            locator=_locator(cast(dict[str, Any], item["locator"])),
            component_locators=tuple(
                _component_locator(component)
                for component in cast(list[dict[str, Any]], item.get("component_locators", []))
            ),
            expected_value_style=(
                _legacy_slot_style(item, legacy_styles, path=contract_path)
                if schema_version == FILL_CONTRACT_V1
                else styles_by_id[
                    str(cast(dict[str, Any], item["style_contract_ref"])["style_contract_id"])
                ].effective_style
                if str(
                    cast(dict[str, Any], item["style_contract_ref"])["style_contract_id"]
                )
                in styles_by_id
                else EffectiveStyle(font={}, paragraph={}, container={}, page={})
            ),
            style_contract_ref=(
                None
                if schema_version == FILL_CONTRACT_V1
                else _style_contract_ref(
                    cast(dict[str, Any], item["style_contract_ref"])
                )
            ),
        )
        for item in cast(list[dict[str, Any]], value["slots"])
    )
    policy_value = cast(dict[str, Any] | None, value.get("responsibility_policy"))
    responsibility_policy = (
        None
        if policy_value is None
        else ResponsibilityPolicy(
            mode=str(policy_value["mode"]),
            analysis_universe=str(policy_value["analysis_universe"]),
            protected_basis=str(policy_value["protected_basis"]),
            slot_basis=str(policy_value["slot_basis"]),
            remove_basis=str(policy_value["remove_basis"]),
        )
    )
    _require_unique([region.region_id for region in regions], "region_id", contract_path)
    _require_unique([slot.slot_id for slot in slots], "slot_id", contract_path)
    _require_unique(
        [slot.locator.value for slot in slots if slot.locator.value is not None],
        "slot locator value",
        contract_path,
    )
    if schema_version == FILL_CONTRACT_V2:
        _require_style_reference_closure(styles, slots, path=contract_path)
    return FillContract(
        schema_version=schema_version,
        contract_id=str(value["contract_id"]),
        template_sha256=str(value["template_sha256"]),
        registry_id=str(registry_ref["registry_id"]),
        registry_version=str(registry_ref["registry_version"]),
        registry_sha256=str(registry_ref["sha256"]),
        marker_protocol=_marker_protocol_version(value["marker_protocol"]),
        regions=regions,
        slots=slots,
        styles=styles,
        style_contract_set_digest=_optional_str(value, "style_contract_set_digest"),
        status=_optional_str(value, "status"),
        responsibility_policy=responsibility_policy,
    )


def load_legacy_fill_contract(path: Path) -> FillContract:
    """Read immutable v1 Gold without pretending it satisfies the v2 style contract."""

    contract_path = _require_file(path)
    value = _load_yaml(contract_path)
    _validate_schema(value, "fill-contract.schema.json", contract_path)
    if value.get("schema_version") != FILL_CONTRACT_V1:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "legacy fill contract reader only accepts docfit-template-fill-contract/v1",
            contract_path,
        )
    return _load_fill_contract_value(value, contract_path)


def load_fill_contract(path: Path) -> FillContract:
    """Read v2 contracts, dispatching frozen v1 fixtures to the explicit legacy reader."""

    contract_path = _require_file(path)
    value = _load_yaml(contract_path)
    _validate_schema(value, "fill-contract.schema.json", contract_path)
    if value.get("schema_version") == FILL_CONTRACT_V1:
        return _load_fill_contract_value(value, contract_path)
    return _load_fill_contract_value(value, contract_path)


def _require_unique(values: list[str], label: str, path: Path) -> None:
    if len(values) != len(set(values)):
        _raise(InputErrorCode.DUPLICATE_ID, f"duplicate {label}", path)


def load_field_registry(path: Path) -> FieldRegistry:
    registry_path = _require_file(path)
    value = _load_yaml(registry_path)
    _validate_schema(value, "field-catalog.schema.json", registry_path)
    fields = tuple(
        RegistryField(
            field_id=str(item["field_id"]),
            label=str(item["label"]),
            meaning=str(item["meaning"]),
            content_type=str(item["content_type"]),
            cardinality=str(item["cardinality"]),
            parent_field_id=_optional_str(item, "parent_field_id"),
            language=_optional_str(item, "language"),
        )
        for item in cast(list[dict[str, Any]], value["fields"])
    )
    _require_unique([field.field_id for field in fields], "field_id", registry_path)
    field_ids = {field.field_id for field in fields}
    for field in fields:
        if field.parent_field_id is not None and field.parent_field_id not in field_ids:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"field {field.field_id} references missing parent {field.parent_field_id}",
                registry_path,
            )
    return FieldRegistry(
        schema_version=str(value["schema_version"]),
        registry_id=str(value["registry_id"]),
        registry_version=str(value["registry_version"]),
        status=str(value["status"]),
        open_world=bool(value["open_world"]),
        fields=fields,
        sha256=sha256_file(registry_path),
    )


def load_eval_config(path: Path) -> EvalConfig:
    config_path = _require_file(path)
    value = _load_yaml(config_path)
    _validate_schema(value, "eval-config.schema.json", config_path)
    marker = cast(dict[str, Any], value["marker_protocol"])
    scoring_ref = cast(dict[str, Any], value["scoring_ref"])
    tolerances = {
        str(key): float(number)
        for key, number in cast(dict[str, Any], value["tolerances"]).items()
    }
    return EvalConfig(
        schema_version=str(value["schema_version"]),
        config_id=str(value["config_id"]),
        marker_protocol=str(marker["version"]),
        field_identity_property=str(marker["field_identity_property"]),
        slot_identity_property=str(marker["slot_identity_property"]),
        internal_id_property=str(marker["internal_id_property"]),
        tolerances=tolerances,
        normalization=tuple(str(item) for item in value.get("normalization", [])),
        scoring_path=_resolve(config_path.parent, str(scoring_ref["path"])),
        scoring_version=str(scoring_ref["version"]),
        scoring_sha256=str(scoring_ref["sha256"]),
        sha256=sha256_file(config_path),
    )


def load_scoring_config(path: Path) -> ScoringConfig:
    scoring_path = _require_file(path)
    value = _load_yaml(scoring_path)
    try:
        views = cast(dict[str, dict[str, Any]], value["views"])
        weights = {
            str(dimension): float(weight)
            for view in views.values()
            for dimension, weight in cast(dict[str, Any], view["dimensions"]).items()
        }
        total_points = float(value["total_points"])
        scoring_version = str(value["scoring_version"])
        hard_failures = tuple(str(item) for item in value["hard_failures"])
    except (KeyError, TypeError, ValueError) as error:
        _raise(InputErrorCode.SCORING_INVALID, f"invalid scoring config: {error}", scoring_path)
    if len(weights) != 8 or any(weight < 0 for weight in weights.values()):
        _raise(
            InputErrorCode.SCORING_INVALID,
            "scoring config must contain eight non-negative dimensions",
            scoring_path,
        )
    if abs(sum(weights.values()) - total_points) > 1e-9 or total_points != 100:
        _raise(InputErrorCode.SCORING_INVALID, "scoring weights must sum to 100", scoring_path)
    return ScoringConfig(
        schema_version=str(value["schema_version"]),
        scoring_version=scoring_version,
        total_points=total_points,
        weights=weights,
        hard_failures=hard_failures,
        sha256=sha256_file(scoring_path),
    )


def _assert_hash(path: Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        _raise(
            InputErrorCode.HASH_MISMATCH,
            f"{label} SHA-256 mismatch: expected {expected}, got {actual}",
            path,
        )
    return actual


def _assert_contract_bindings(
    contract: FillContract,
    *,
    contract_path: Path,
    template_path: Path,
    registry: FieldRegistry,
    marker_protocol: str,
) -> None:
    _assert_hash(template_path, contract.template_sha256, "contract template")
    expected_registry = (registry.registry_id, registry.registry_version, registry.sha256)
    actual_registry = (
        contract.registry_id,
        contract.registry_version,
        contract.registry_sha256,
    )
    if actual_registry != expected_registry:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "fill contract Registry binding does not match the case Registry",
            contract_path,
        )
    if contract.marker_protocol != marker_protocol:
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "fill contract marker protocol does not match Eval configuration",
            contract_path,
        )
    for slot in contract.slots:
        field = registry.by_id.get(slot.field_id)
        if field is None:
            _raise(
                InputErrorCode.UNKNOWN_FIELD,
                f"slot {slot.slot_id} references unknown field {slot.field_id}",
                contract_path,
            )
        if field.content_type != slot.content_type:
            _raise(
                InputErrorCode.CONTRACT_MISMATCH,
                f"slot {slot.slot_id} content_type does not match Registry field",
                contract_path,
            )


def validate_gold_truth_ready(contract: FillContract, *, path: Path) -> None:
    """Reject an incomplete Gold before it can produce a vacuous quality score."""

    policy = contract.responsibility_policy
    if policy is None or (
        policy.mode != "exhaustive"
        or policy.analysis_universe != "semantic_document_facts/v1"
        or policy.protected_basis != "complement_of_slot_and_remove"
        or policy.slot_basis != "managed_content_controls_and_fill_contract"
        or policy.remove_basis != "declared_remove_regions"
    ):
        _raise(
            InputErrorCode.GOLD_NOT_ACCEPTED,
            "accepted Gold must bind the exhaustive semantic-document-facts "
            "responsibility policy",
            path,
        )
    if not contract.slots:
        _raise(
            InputErrorCode.GOLD_NOT_ACCEPTED,
            "accepted Gold must declare non-empty slot Truth",
            path,
        )


def load_eval_inputs(
    case_path: Path,
    actual_template_path: Path,
    actual_contract_path: Path,
) -> EvalInputs:
    case = load_case(case_path)
    if case.case_status == "candidate" or case.gold_review_status == "candidate":
        _raise(
            InputErrorCode.GOLD_NOT_ACCEPTED,
            "candidate case has not completed Human Gold acceptance",
            case.case_path,
        )
    actual_template = _require_file(actual_template_path)
    actual_contract_file = _require_file(actual_contract_path)
    _assert_hash(case.registry_ref.path, case.registry_ref.sha256, "case Registry")
    _assert_hash(case.eval_config_ref.path, case.eval_config_ref.sha256, "case Eval config")

    registry = load_field_registry(case.registry_ref.path)
    eval_config = load_eval_config(case.eval_config_ref.path)
    scoring = load_scoring_config(eval_config.scoring_path)
    _assert_hash(eval_config.scoring_path, eval_config.scoring_sha256, "Eval scoring config")
    if (
        case.registry_ref.id != registry.registry_id
        or case.registry_ref.version != registry.registry_version
    ):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "case Registry ID/version does not match loaded Registry",
            case.registry_ref.path,
        )
    if (
        case.eval_config_ref.id != eval_config.config_id
        or case.eval_config_ref.version != eval_config.schema_version
    ):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "case Eval config ID/version does not match loaded config",
            case.eval_config_ref.path,
        )
    if not (
        case.scoring_version == eval_config.scoring_version == scoring.scoring_version
    ):
        _raise(
            InputErrorCode.CONTRACT_MISMATCH,
            "case, Eval config, and scoring version must match",
            eval_config.scoring_path,
        )

    actual_contract = load_fill_contract(actual_contract_file)
    gold_contract = load_fill_contract(case.gold_contract_path)
    accepted_claimed = (
        case.case_status == "accepted" or case.gold_review_status == "accepted"
    )
    accepted_closed = (
        case.case_status == "accepted"
        and case.gold_review_status == "accepted"
        and gold_contract.status == "accepted"
    )
    if accepted_claimed and not accepted_closed:
        _raise(
            InputErrorCode.GOLD_NOT_ACCEPTED,
            "case, Gold review, and Gold fill contract must all be accepted",
            case.gold_contract_path,
        )
    if accepted_closed:
        validate_gold_truth_ready(gold_contract, path=case.gold_contract_path)
    _assert_contract_bindings(
        actual_contract,
        contract_path=actual_contract_file,
        template_path=actual_template,
        registry=registry,
        marker_protocol=eval_config.marker_protocol,
    )
    _assert_contract_bindings(
        gold_contract,
        contract_path=case.gold_contract_path,
        template_path=case.gold_template_path,
        registry=registry,
        marker_protocol=eval_config.marker_protocol,
    )
    input_hashes = {
        "case_manifest": sha256_file(case.case_path),
        "actual_template": sha256_file(actual_template),
        "actual_contract": sha256_file(actual_contract_file),
        "gold_template": sha256_file(case.gold_template_path),
        "gold_contract": sha256_file(case.gold_contract_path),
        "field_registry": registry.sha256,
        "eval_config": eval_config.sha256,
        "scoring_config": scoring.sha256,
    }
    return EvalInputs(
        case=case,
        actual_template_path=actual_template,
        actual_contract_path=actual_contract_file,
        actual_contract=actual_contract,
        gold_contract=gold_contract,
        field_registry=registry,
        eval_config=eval_config,
        scoring_config=scoring,
        input_hashes=input_hashes,
    )


__all__ = [
    "compute_style_contract_digest",
    "compute_style_contract_set_digest",
    "InputContractError",
    "InputErrorCode",
    "load_case",
    "load_eval_config",
    "load_eval_inputs",
    "load_field_registry",
    "load_fill_contract",
    "load_legacy_fill_contract",
    "load_scoring_config",
    "sha256_file",
    "validate_gold_truth_ready",
]
