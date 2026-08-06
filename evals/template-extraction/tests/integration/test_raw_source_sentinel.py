from __future__ import annotations

from pathlib import Path

import pytest

from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_ROOT = REPO_ROOT / "temp/manual-gold-preparation/gold/00-inputs/schools"


@pytest.mark.parametrize(
    ("case_id", "source_name", "slot_count", "protected_status", "total_score"),
    [
        (
            "01-hunau-undergraduate",
            "hunau-undergraduate__source-template.docx",
            24,
            "FAIL",
            35,
        ),
        (
            "02-njau-undergraduate",
            "njau-undergraduate__source-template.docx",
            32,
            "PASS",
            50,
        ),
        (
            "03-pku-graduate",
            "pku-graduate__source-template.docx",
            28,
            "PASS",
            50,
        ),
    ],
)
def test_sentinel_01_through_03_raw_source_exposes_both_view_outcomes(
    case_id: str,
    source_name: str,
    slot_count: int,
    protected_status: str,
    total_score: int,
) -> None:
    result = run_raw_source_sentinel(
        PROJECT_ROOT / "cases" / case_id / "case.yaml",
        SOURCE_ROOT / source_name,
    )
    outcome = result["result"]
    assert result["diagnostic_only"] is True
    assert outcome["verdict"] == "FAIL"
    assert outcome["score"] == total_score
    assert outcome["analysis_coverage"] == 1
    assert outcome["protected"]["status"] == protected_status
    assert outcome["protected"]["score"] == total_score
    assert outcome["slot"]["status"] == "FAIL"
    assert outcome["slot"]["score"] == 0
    assert outcome["slot"]["counts"]["FAIL"] == slot_count * 4
    if case_id == "01-hunau-undergraduate":
        assert len(outcome["protected"]["issues"]) == 3
        assert all(
            "page.margin" in issue["message"]
            for issue in outcome["protected"]["issues"]
        )
    else:
        assert outcome["protected"]["issues"] == []
