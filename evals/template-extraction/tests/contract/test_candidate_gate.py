from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from template_extraction_eval.contracts import (
    InputContractError,
    InputErrorCode,
    load_eval_inputs,
    sha256_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES = PROJECT_ROOT / "cases"


@pytest.mark.parametrize(
    "case_id",
    [
        "01-hunau-undergraduate",
        "02-njau-undergraduate",
        "03-pku-graduate",
    ],
)
def test_gold_01_through_03_candidate_school_cases_cannot_be_scored(
    case_id: str,
) -> None:
    case_root = CASES / case_id
    with pytest.raises(InputContractError) as captured:
        load_eval_inputs(
            case_root / "case.yaml",
            case_root / "gold" / "template.docx",
            case_root / "gold" / "fill-contract.yaml",
        )
    assert captured.value.code is InputErrorCode.GOLD_NOT_ACCEPTED
    assert "Human Gold acceptance" in str(captured.value)


def test_gold_04_top_level_acceptance_cannot_bypass_candidate_contract(
    tmp_path: Path,
) -> None:
    fixture_root = PROJECT_ROOT / "fixtures"
    sample = tmp_path / "S00-minimal-pass"
    shutil.copytree(fixture_root / "S00-minimal-pass", sample)
    shutil.copy(fixture_root / "field-registry.yaml", tmp_path / "field-registry.yaml")
    shutil.copy(fixture_root / "eval-config.yaml", tmp_path / "eval-config.yaml")
    (tmp_path / "config").mkdir()
    shutil.copy(
        PROJECT_ROOT / "config" / "scoring-v1.yaml",
        tmp_path / "config" / "scoring-v1.yaml",
    )
    eval_config_path = tmp_path / "eval-config.yaml"
    eval_config = yaml.safe_load(eval_config_path.read_text(encoding="utf-8"))
    eval_config["scoring_ref"]["path"] = "config/scoring-v1.yaml"
    eval_config_path.write_text(
        yaml.safe_dump(eval_config, sort_keys=False),
        encoding="utf-8",
    )

    case_path = sample / "case.yaml"
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    case["case_status"] = "accepted"
    case["gold_review"] = {
        "status": "accepted",
        "reviewer": "synthetic-reviewer",
        "reviewed_at": "2026-08-06T00:00:00Z",
    }
    case["eval_config"]["sha256"] = sha256_file(eval_config_path)
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    gold_contract_path = sample / "gold-contract.yaml"
    gold_contract = yaml.safe_load(gold_contract_path.read_text(encoding="utf-8"))
    gold_contract["status"] = "candidate_pending_human_acceptance"
    gold_contract["review"] = {
        "status": "machine_checked_pending_human_signoff",
        "reviewer": None,
        "reviewed_at": None,
        "conclusion": "pending",
        "blockers": ["Human signoff missing"],
    }
    gold_contract_path.write_text(
        yaml.safe_dump(gold_contract, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(InputContractError) as captured:
        load_eval_inputs(
            case_path,
            sample / "actual-template.docx",
            sample / "actual-contract.yaml",
        )
    assert captured.value.code is InputErrorCode.GOLD_NOT_ACCEPTED
    assert "must all be accepted" in str(captured.value)
