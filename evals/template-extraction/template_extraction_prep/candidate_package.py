"""Build one hash-bound candidate Eval case package."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator

from .docx_package import (
    declared_content_control_fields,
    managed_content_controls,
    sha256_file,
)
from .normalizers import normalize_fill_contract
from .sources import CandidateSource, load_source_manifest
from .writers import dump_yaml, write_bytes_atomic, write_json_atomic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PROJECT_ROOT / "schemas"
GOLD_TEMPLATE_NAME = "final-template.gold.docx"
GOLD_CONTRACT_NAME = "fill-contract.gold.yaml"
GOLD_TEMPLATE_PATH = f"gold/{GOLD_TEMPLATE_NAME}"
GOLD_CONTRACT_PATH = f"gold/{GOLD_CONTRACT_NAME}"


@dataclass(frozen=True, slots=True)
class CandidatePackageReceipt:
    case_id: str
    case_root: Path
    case_sha256: str
    template_sha256: str
    contract_sha256: str
    gold_review_status: str
    written: bool


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return cast(dict[str, Any], value)


def _schema(name: str) -> dict[str, Any]:
    value = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON schema mapping: {name}")
    return value


def _relative_from_case(case_root: Path, path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), case_root.resolve())).as_posix()


def _assert_hash(path: Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")
    return actual


def _assert_destination_not_accepted(case_root: Path) -> None:
    case_path = case_root / "case.yaml"
    contract_path = case_root / GOLD_CONTRACT_PATH
    if case_path.exists():
        case = _read_yaml(case_path)
        if case.get("gold_review", {}).get("status") == "accepted":
            raise ValueError(f"refusing to overwrite accepted case: {case_path}")
    if contract_path.exists():
        contract = _read_yaml(contract_path)
        if contract.get("status") == "accepted":
            raise ValueError(f"refusing to overwrite accepted contract: {contract_path}")


def _case(
    source: CandidateSource,
    *,
    case_root: Path,
    template_sha256: str,
    contract_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": "docfit-template-extraction-case/v1",
        "case_id": source.case_id,
        "description": source.description
        or f"{source.school_name} candidate package",
        "school_id": source.school_id,
        "school_name": source.school_name,
        "case_status": source.case_status,
        "gold": {
            "template": GOLD_TEMPLATE_PATH,
            "contract": GOLD_CONTRACT_PATH,
            "template_sha256": template_sha256,
            "contract_sha256": contract_sha256,
        },
        "field_registry_ref": {
            "path": _relative_from_case(case_root, source.field_registry.path),
            "id": source.field_registry.id,
            "version": source.field_registry.version,
            "sha256": source.field_registry.sha256,
        },
        "eval_config": {
            "path": _relative_from_case(case_root, source.eval_config.path),
            "id": source.eval_config.id,
            "version": source.eval_config.version,
            "sha256": source.eval_config.sha256,
        },
        "scoring_version": source.scoring_version,
        "marker_protocol": "docfit-content-control-marker/v1",
        "expected_verdict": source.expected_verdict,
        "gold_review": {
            "status": source.gold_review_status,
            "reviewer": source.reviewer,
            "reviewed_at": source.reviewed_at,
            "source_sha256": template_sha256,
            "source_path": _relative_from_case(case_root, source.template_path),
            "blockers": list(source.blockers),
        },
        "permissions": source.permissions,
    }


def _validate_marker_closure(template_path: Path, contract: dict[str, Any]) -> None:
    actual = managed_content_controls(template_path)
    declared = declared_content_control_fields(contract)
    if actual != declared:
        raise ValueError(
            "template/contract marker mismatch: "
            f"actual={actual}, declared={declared}"
        )


def _build_source(
    source: CandidateSource,
    output_root: Path,
    *,
    dry_run: bool,
    refuse_accepted: bool,
) -> CandidatePackageReceipt:
    template_sha256 = _assert_hash(
        source.template_path, source.template_sha256, "template source"
    )
    _assert_hash(source.contract_path, source.contract_sha256, "contract source")
    _assert_hash(source.field_registry.path, source.field_registry.sha256, "field registry")
    _assert_hash(source.eval_config.path, source.eval_config.sha256, "eval config")

    contract = normalize_fill_contract(
        _read_yaml(source.contract_path),
        template_sha256=template_sha256,
    )
    if contract.get("template_sha256") != template_sha256:
        raise ValueError("contract template_sha256 did not normalize")
    if contract.get("status") == "accepted" and source.gold_review_status != "accepted":
        raise ValueError("accepted contract cannot back a non-accepted case")
    _validate_marker_closure(source.template_path, contract)

    contract_validator = Draft202012Validator(_schema("fill-contract.schema.json"))
    case_validator = Draft202012Validator(_schema("case.schema.json"))
    contract_validator.validate(contract)
    contract_bytes = dump_yaml(contract)
    contract_sha256 = sha256_file_bytes(contract_bytes)
    case_root = output_root / source.case_id
    case = _case(
        source,
        case_root=case_root,
        template_sha256=template_sha256,
        contract_sha256=contract_sha256,
    )
    case_validator.validate(case)
    case_bytes = dump_yaml(case)

    if refuse_accepted:
        _assert_destination_not_accepted(case_root)
    if not dry_run:
        write_bytes_atomic(case_root / GOLD_TEMPLATE_PATH, source.template_path.read_bytes())
        write_bytes_atomic(case_root / GOLD_CONTRACT_PATH, contract_bytes)
        write_bytes_atomic(case_root / "case.yaml", case_bytes)
        write_json_atomic(
            case_root / "candidate-package-receipt.json",
            {
                "schema_version": "docfit-template-extraction-candidate-package-receipt/v1",
                "case_id": source.case_id,
                "template_sha256": template_sha256,
                "contract_sha256": contract_sha256,
                "case_sha256": sha256_file_bytes(case_bytes),
                "gold_review_status": source.gold_review_status,
            },
        )

    return CandidatePackageReceipt(
        case_id=source.case_id,
        case_root=case_root,
        case_sha256=sha256_file_bytes(case_bytes),
        template_sha256=template_sha256,
        contract_sha256=contract_sha256,
        gold_review_status=source.gold_review_status,
        written=not dry_run,
    )


def sha256_file_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def build_candidate_package(
    source_manifest: Path,
    case_id: str,
    output_root: Path,
    *,
    dry_run: bool = False,
    refuse_accepted: bool = True,
) -> CandidatePackageReceipt:
    return build_candidate_packages(
        source_manifest,
        output_root,
        case_ids=[case_id],
        dry_run=dry_run,
        refuse_accepted=refuse_accepted,
    )[0]


def build_candidate_packages(
    source_manifest: Path,
    output_root: Path,
    *,
    case_ids: Sequence[str] | None = None,
    dry_run: bool = False,
    refuse_accepted: bool = True,
) -> list[CandidatePackageReceipt]:
    manifest = load_source_manifest(source_manifest)
    sources_by_case_id = manifest.by_case_id()
    selected_case_ids = (
        tuple(case_ids)
        if case_ids is not None
        else tuple(source.case_id for source in manifest.sources)
    )
    missing_case_ids = [
        case_id for case_id in selected_case_ids if case_id not in sources_by_case_id
    ]
    if missing_case_ids:
        raise ValueError(
            "candidate source case not found: " + ", ".join(sorted(missing_case_ids))
        )

    resolved_output_root = output_root.expanduser().resolve()
    return [
        _build_source(
            sources_by_case_id[case_id],
            resolved_output_root,
            dry_run=dry_run,
            refuse_accepted=refuse_accepted,
        )
        for case_id in selected_case_ids
    ]
