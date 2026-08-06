from __future__ import annotations

from pathlib import Path

import pytest

from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_ROOT = REPO_ROOT / "temp/manual-gold-preparation/gold/00-inputs/schools"


@pytest.mark.parametrize(
    ("case_id", "source_name", "slot_count"),
    [
        (
            "01-hunau-undergraduate",
            "hunau-undergraduate__source-template.docx",
            24,
        ),
        (
            "02-njau-undergraduate",
            "njau-undergraduate__source-template.docx",
            32,
        ),
        (
            "03-pku-graduate",
            "pku-graduate__source-template.docx",
            28,
        ),
    ],
)
def test_sentinel_01_through_03_raw_source_exposes_both_view_outcomes(
    case_id: str,
    source_name: str,
    slot_count: int,
) -> None:
    result = run_raw_source_sentinel(
        PROJECT_ROOT / "cases" / case_id / "case.yaml",
        SOURCE_ROOT / source_name,
    )
    outcome = result["result"]
    assert result["diagnostic_only"] is True
    assert outcome["verdict"] == "FAIL"
    assert outcome["score"] == 50
    assert outcome["analysis_coverage"] == 1
    assert outcome["responsibility_coverage"] == 1
    assert outcome["protected"]["scope"] == "exhaustive"
    assert outcome["protected"]["status"] == "PASS"
    assert outcome["protected"]["score"] == 50
    inventory = outcome["protected"]["responsibility_inventory"]
    assert inventory["coverage"] == 1
    assert inventory["unclassified_atoms"] == 0
    assert inventory["protected_atoms"] > 3
    assert outcome["slot"]["status"] == "FAIL"
    assert outcome["slot"]["score"] == 0
    assert outcome["slot"]["counts"]["FAIL"] == slot_count * 4
    assert outcome["protected"]["issues"] == []
