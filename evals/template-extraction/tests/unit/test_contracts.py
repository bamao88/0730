from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from template_extraction_eval.contracts import (
    InputContractError,
    InputErrorCode,
    load_eval_inputs,
    load_field_registry,
    load_fill_contract,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"
CASES = PROJECT_ROOT / "cases"
OFFICIAL_REGISTRY = (
    PROJECT_ROOT.parents[1]
    / "docs/plans/docfit-content-field-registry/content-fields-v0.1.yaml"
)


def _inputs(sample: str) -> tuple[Path, Path, Path]:
    root = FIXTURES / sample
    return root / "case.yaml", root / "actual-template.docx", root / "actual-contract.yaml"


def test_con_01_s00_loads_complete_bound_inputs() -> None:
    inputs = load_eval_inputs(*_inputs("S00-minimal-pass"))
    assert inputs.case.case_id == "s00-minimal-pass"
    assert inputs.actual_contract.slots[0].field_id == "author.name.zh"
    assert inputs.gold_contract.template_sha256 == inputs.input_hashes["gold_template"]
    assert inputs.field_registry.by_id["author.name.zh"].content_type == "text"


def test_con_02_s11_invalid_contract_is_rejected_without_score() -> None:
    with pytest.raises(InputContractError) as captured:
        load_eval_inputs(*_inputs("S11-invalid-input"))
    assert captured.value.code in {InputErrorCode.HASH_MISMATCH, InputErrorCode.SCHEMA_INVALID}
    assert "score" not in captured.value.to_dict()


def test_con_03_registry_hash_or_unknown_field_is_rejected(tmp_path: Path) -> None:
    source = FIXTURES / "S00-minimal-pass"
    sample = tmp_path / "sample"
    shutil.copytree(source, sample)
    shutil.copy(FIXTURES / "field-registry.yaml", tmp_path / "field-registry.yaml")
    shutil.copy(FIXTURES / "eval-config.yaml", tmp_path / "eval-config.yaml")
    case = yaml.safe_load((sample / "case.yaml").read_text())
    case["field_registry_ref"]["sha256"] = "f" * 64
    (sample / "case.yaml").write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    with pytest.raises(InputContractError) as captured:
        load_eval_inputs(
            sample / "case.yaml",
            sample / "actual-template.docx",
            sample / "actual-contract.yaml",
        )
    assert captured.value.code is InputErrorCode.HASH_MISMATCH


@pytest.mark.parametrize(
    ("case_id", "region_count", "component_count"),
    [
        ("01-hunau-undergraduate", 1, 0),
        ("02-njau-undergraduate", 2, 0),
        ("03-pku-graduate", 5, 0),
    ],
)
def test_con_04_through_06_school_contracts_close_over_runtime_model(
    case_id: str,
    region_count: int,
    component_count: int,
) -> None:
    contract = load_fill_contract(CASES / case_id / "gold" / "fill-contract.yaml")
    assert len(contract.regions) == region_count
    assert sum(len(slot.component_locators) for slot in contract.slots) == component_count
    assert contract.marker_protocol == "docfit-content-control-marker/v1"
    assert contract.responsibility_policy is not None
    assert contract.responsibility_policy.mode == "exhaustive"


def test_con_07_official_registry_equation_type_is_loadable() -> None:
    registry = load_field_registry(OFFICIAL_REGISTRY)
    assert registry.by_id["body.equation"].content_type == "equation"
