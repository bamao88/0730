"""Load and validate versioned Eval inputs before document analysis."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast

import yaml
from jsonschema import Draft202012Validator

from .models import (
    CaseDefinition,
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
    ScoringConfig,
    SlotContract,
)

SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schemas"


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


def load_fill_contract(path: Path) -> FillContract:
    contract_path = _require_file(path)
    value = _load_yaml(contract_path)
    _validate_schema(value, "fill-contract.schema.json", contract_path)
    registry_ref = cast(dict[str, Any], value["field_registry_ref"])
    regions = tuple(
        RegionContract(
            region_id=str(item["region_id"]),
            owner=Owner(str(item["owner"])),
            required=bool(item["required"]),
            locator=_locator(cast(dict[str, Any], item["locator"])),
            text=_optional_str(item, "text"),
            forbidden_text=_optional_str(item, "forbidden_text"),
            object_kind=_optional_str(item, "object_kind"),
            object_sha256=_optional_str(item, "object_sha256"),
            expected_style=_style(cast(dict[str, Any] | None, item.get("expected_style"))),
        )
        for item in cast(list[dict[str, Any]], value["regions"])
    )
    slots = tuple(
        SlotContract(
            slot_id=str(item["slot_id"]),
            field_id=str(item["field_id"]),
            content_type=str(item["content_type"]),
            required=bool(item["required"]),
            cardinality=str(item.get("cardinality", "one")),
            locator=_locator(cast(dict[str, Any], item["locator"])),
            component_locators=tuple(
                _locator(component)
                for component in cast(list[dict[str, Any]], item.get("component_locators", []))
            ),
            expected_value_style=cast(
                EffectiveStyle,
                _style(cast(dict[str, Any], item["expected_value_style"])),
            ),
        )
        for item in cast(list[dict[str, Any]], value["slots"])
    )
    _require_unique([region.region_id for region in regions], "region_id", contract_path)
    _require_unique([slot.slot_id for slot in slots], "slot_id", contract_path)
    _require_unique(
        [slot.locator.value for slot in slots if slot.locator.value is not None],
        "slot locator value",
        contract_path,
    )
    return FillContract(
        schema_version=str(value["schema_version"]),
        contract_id=str(value["contract_id"]),
        template_sha256=str(value["template_sha256"]),
        registry_id=str(registry_ref["registry_id"]),
        registry_version=str(registry_ref["registry_version"]),
        registry_sha256=str(registry_ref["sha256"]),
        marker_protocol=str(value["marker_protocol"]),
        regions=regions,
        slots=slots,
        status=_optional_str(value, "status"),
    )


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
