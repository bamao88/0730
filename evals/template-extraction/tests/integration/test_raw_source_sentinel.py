from __future__ import annotations

from pathlib import Path

import pytest

from template_extraction_eval.aligned_protected import (
    evaluate_aligned_exhaustive_protected,
)
from template_extraction_eval.contracts import (
    load_case,
    load_eval_config,
    load_fill_contract,
)
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus
from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_ROOT = REPO_ROOT / "temp/manual-gold-preparation/gold/00-inputs/schools"


@pytest.mark.parametrize(
    (
        "case_id",
        "source_name",
        "slot_count",
        "gold_protected_atoms",
        "matched_paragraphs",
        "missing_paragraphs",
        "protected_failures",
        "protected_unknown",
    ),
    [
        (
            "01-hunau-undergraduate",
            "hunau-undergraduate__source-template.docx",
            24,
            1692,
            487,
            13,
            647,
            9,
        ),
        (
            "02-njau-undergraduate",
            "njau-undergraduate__source-template.docx",
            32,
            659,
            127,
            18,
            230,
            12,
        ),
        (
            "03-pku-graduate",
            "pku-graduate__source-template.docx",
            28,
            486,
            138,
            0,
            9,
            9,
        ),
    ],
)
def test_sentinel_01_through_03_raw_source_exposes_both_view_outcomes(
    case_id: str,
    source_name: str,
    slot_count: int,
    gold_protected_atoms: int,
    matched_paragraphs: int,
    missing_paragraphs: int,
    protected_failures: int,
    protected_unknown: int,
) -> None:
    result = run_raw_source_sentinel(
        PROJECT_ROOT / "cases" / case_id / "case.yaml",
        SOURCE_ROOT / source_name,
    )
    outcome = result["result"]
    assert result["diagnostic_only"] is True
    assert outcome["verdict"] == "FAIL"
    assert outcome["score"] == outcome["protected"]["score"]
    assert outcome["analysis_coverage"] > 0.99
    assert outcome["responsibility_coverage"] == 1
    assert outcome["protected"]["scope"] == "all_clean_gold_protected_facts"
    assert outcome["protected"]["status"] == "FAIL"
    audit = outcome["protected"]["audit"]
    assert audit["responsibility_coverage"] == 1
    assert audit["expected_gold_protected_atoms"] == gold_protected_atoms
    assert audit["asserted_gold_protected_atoms"] == gold_protected_atoms
    assert audit["matched_paragraphs"] == matched_paragraphs
    assert audit["missing_gold_paragraphs"] == missing_paragraphs
    assert outcome["protected"]["counts"]["FAIL"] == protected_failures
    assert outcome["protected"]["counts"]["UNKNOWN"] == protected_unknown
    assert outcome["slot"]["status"] == "FAIL"
    assert outcome["slot"]["score"] == 0
    assert outcome["slot"]["counts"]["FAIL"] == slot_count * 4
    assert len(result["paragraph_alignment"]) >= matched_paragraphs


@pytest.mark.parametrize(
    "case_id",
    [
        "01-hunau-undergraduate",
        "02-njau-undergraduate",
        "03-pku-graduate",
    ],
)
def test_sentinel_04_through_06_real_gold_self_comparison_is_exact(
    case_id: str,
) -> None:
    case = load_case(PROJECT_ROOT / "cases" / case_id / "case.yaml")
    contract = load_fill_contract(case.gold_contract_path)
    config = load_eval_config(case.eval_config_ref.path)
    facts = analyze_docx(case.gold_template_path)

    audit = evaluate_aligned_exhaustive_protected(
        facts,
        facts,
        contract,
        contract,
        config,
    )

    assert audit.responsibility_coverage == 1
    assert len(audit.assertions) == audit.gold_inventory.protected
    assert all(item.status is AssertionStatus.PASS for item in audit.assertions)
