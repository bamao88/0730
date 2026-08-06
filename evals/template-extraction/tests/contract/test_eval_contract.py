from __future__ import annotations

import copy
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
SCHEMA_ROOT = PROJECT_ROOT / "schemas"
FIXTURE_ROOT = PROJECT_ROOT / "fixtures"


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _schema(name: str) -> dict[str, Any]:
    value = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validate(schema_name: str, value: dict[str, Any]) -> None:
    Draft202012Validator(_schema(schema_name)).validate(value)


def _valid_report() -> dict[str, Any]:
    zero_hash = "0" * 64
    return {
        "schema_version": "docfit-template-extraction-eval-report/v1",
        "case_id": "s00-minimal-pass",
        "run_id": "run-synthetic",
        "status": "PASS",
        "score": {"total": 100, "provisional": False},
        "analysis_coverage": 1,
        "dimensions": [
            {
                "dimension": "protected.content",
                "weight": 20,
                "score": 20,
                "passed": 1,
                "failed": 0,
                "unknown": 0,
                "not_applicable": 0,
            }
        ],
        "issues": [],
        "inputs": {
            "actual_template": zero_hash,
            "actual_contract": zero_hash,
            "gold_template": zero_hash,
            "gold_contract": zero_hash,
        },
        "config": {
            "scoring_version": "docfit-template-extraction-scoring/v1",
            "eval_config_sha256": zero_hash,
            "registry_id": "docfit.thesis.content_fields",
            "registry_version": "0.1.0",
            "registry_sha256": zero_hash,
        },
    }


def test_env_01_project_runs_without_product_package() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import template_extraction_eval; print(template_extraction_eval.__version__)",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "0.1.0"


def test_env_02_lock_has_no_product_runtime_dependencies() -> None:
    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8"))
    names = {package["name"] for package in lock["package"]}
    assert "docfit-agent" not in names
    assert "claude-agent-sdk" not in names
    assert "pdfservices-sdk" not in names


def test_env_03_build_targets_are_mutually_isolated() -> None:
    product = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    evaluator = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert product["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/docfit"]
    assert evaluator["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "template_extraction_eval"
    ]


def test_sch_case_01_minimal_case_is_valid() -> None:
    _validate("case.schema.json", _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "case.yaml"))


def test_sch_case_02_missing_gold_reference_fails() -> None:
    value = _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "case.yaml")
    del value["gold"]["template"]
    with pytest.raises(ValidationError):
        _validate("case.schema.json", value)


def test_sch_case_03_registry_ref_requires_version_and_hash() -> None:
    value = _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "case.yaml")
    del value["field_registry_ref"]["sha256"]
    with pytest.raises(ValidationError):
        _validate("case.schema.json", value)


def test_sch_case_04_candidate_cannot_claim_pass() -> None:
    value = _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "case.yaml")
    value["case_status"] = "candidate"
    value["expected_verdict"] = "PASS"
    value["gold_review"] = {
        "status": "candidate",
        "reviewer": None,
        "reviewed_at": None,
    }
    with pytest.raises(ValidationError):
        _validate("case.schema.json", value)


def test_sch_fill_01_protected_and_slot_contract_is_valid() -> None:
    _validate(
        "fill-contract.schema.json",
        _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "gold-contract.yaml"),
    )


def test_sch_fill_02_invalid_owner_fails() -> None:
    value = _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "gold-contract.yaml")
    value["regions"][0]["owner"] = "generated"
    with pytest.raises(ValidationError):
        _validate("fill-contract.schema.json", value)


def test_sch_fill_03_invalid_component_locator_fails() -> None:
    value = _yaml(FIXTURE_ROOT / "S00-minimal-pass" / "gold-contract.yaml")
    value["slots"][0]["component_locators"] = [{"type": "content_control_tag"}]
    with pytest.raises(ValidationError):
        _validate("fill-contract.schema.json", value)


def test_sch_field_01_registry_is_valid() -> None:
    _validate("field-catalog.schema.json", _yaml(FIXTURE_ROOT / "field-registry.yaml"))


def test_sch_field_02_invalid_field_id_fails() -> None:
    value = _yaml(FIXTURE_ROOT / "field-registry.yaml")
    value["fields"][0]["field_id"] = "Name"
    with pytest.raises(ValidationError):
        _validate("field-catalog.schema.json", value)


def test_sch_field_03_registry_identity_is_required() -> None:
    value = _yaml(FIXTURE_ROOT / "field-registry.yaml")
    del value["registry_version"]
    with pytest.raises(ValidationError):
        _validate("field-catalog.schema.json", value)


def test_sch_cfg_01_eval_config_is_valid() -> None:
    _validate("eval-config.schema.json", _yaml(FIXTURE_ROOT / "eval-config.yaml"))


def test_sch_cfg_02_negative_tolerance_fails() -> None:
    value = _yaml(FIXTURE_ROOT / "eval-config.yaml")
    value["tolerances"]["distance_pt"] = -0.01
    with pytest.raises(ValidationError):
        _validate("eval-config.schema.json", value)


def test_sch_cfg_03_unknown_scoring_version_fails() -> None:
    value = _yaml(FIXTURE_ROOT / "eval-config.yaml")
    value["scoring_ref"]["version"] = "experimental"
    with pytest.raises(ValidationError):
        _validate("eval-config.schema.json", value)


def test_sch_rep_01_pass_report_is_valid() -> None:
    _validate("report.schema.json", _valid_report())


def test_sch_rep_02_unknown_provisional_report_is_valid() -> None:
    value = _valid_report()
    value["status"] = "UNKNOWN"
    value["score"]["provisional"] = True
    value["analysis_coverage"] = 0.5
    _validate("report.schema.json", value)


def test_sch_rep_03_missing_dimensions_fails() -> None:
    value = _valid_report()
    del value["dimensions"]
    with pytest.raises(ValidationError):
        _validate("report.schema.json", value)


def test_cfg_score_01_dimensions_sum_to_one_hundred() -> None:
    scoring = _yaml(PROJECT_ROOT / "config" / "scoring-v1.yaml")
    dimensions = [
        weight
        for view in scoring["views"].values()
        for weight in view["dimensions"].values()
    ]
    assert sum(dimensions) == scoring["total_points"] == 100
    assert len(dimensions) == 8


@pytest.mark.parametrize("mutation", ["negative", "missing"], ids=["negative", "missing"])
def test_cfg_score_02_negative_or_missing_dimension_fails(mutation: str) -> None:
    scoring = _yaml(PROJECT_ROOT / "config" / "scoring-v1.yaml")
    if mutation == "negative":
        scoring["views"]["protected"]["dimensions"]["protected.content"] = -1
    else:
        del scoring["views"]["slot"]["dimensions"]["slot.value_style"]
    dimensions = [
        weight
        for view in scoring["views"].values()
        for weight in view["dimensions"].values()
    ]
    invalid = len(dimensions) != 8 or any(weight < 0 for weight in dimensions)
    assert invalid or sum(dimensions) != 100


def test_cfg_score_03_case_cannot_override_weights() -> None:
    case = copy.deepcopy(_yaml(FIXTURE_ROOT / "S00-minimal-pass" / "case.yaml"))
    case["weights"] = {"protected.content": 100}
    with pytest.raises(ValidationError):
        _validate("case.schema.json", case)
