from __future__ import annotations

from pathlib import Path

from template_extraction_eval.contracts import load_scoring_config
from template_extraction_eval.models import (
    AssertionResult,
    AssertionStatus,
    View,
)
from template_extraction_eval.scoring import score_assertions

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_scoring_config(PROJECT_ROOT / "config" / "scoring-v1.yaml")


def _assertion(
    assertion_id: str,
    dimension: str,
    status: AssertionStatus,
    *,
    required: bool = True,
    failure_code: str | None = None,
) -> AssertionResult:
    return AssertionResult(
        assertion_id=assertion_id,
        view=View.SLOT if dimension.startswith("slot.") else View.PROTECTED,
        dimension=dimension,
        status=status,
        required=required,
        message=assertion_id,
        failure_code=failure_code,
    )


def test_scr_01_all_pass_is_one_hundred_and_final() -> None:
    assertions = tuple(
        _assertion(dimension, dimension, AssertionStatus.PASS)
        for dimension in CONFIG.weights
    )
    result = score_assertions(assertions, CONFIG)
    assert result.verdict.value == "PASS"
    assert result.total_score == 100
    assert [(item.view.value, item.score) for item in result.views] == [
        ("protected", 50),
        ("slot", 50),
    ]
    assert result.provisional is False
    assert result.analysis_coverage == 1


def test_scr_02_inventory_uses_f1_and_hard_failure_wins() -> None:
    assertions = (
        _assertion("gold-slot", "slot.inventory", AssertionStatus.PASS),
        _assertion(
            "extra-slot",
            "slot.inventory",
            AssertionStatus.FAIL,
            failure_code="extra_slot",
        ),
    )
    result = score_assertions(assertions, CONFIG)
    inventory = next(item for item in result.dimensions if item.dimension == "slot.inventory")
    assert inventory.score == 10
    assert result.total_score == 10
    assert result.verdict.value == "FAIL"


def test_scr_03_unknown_is_excluded_but_marks_provisional_and_coverage() -> None:
    assertions = (
        _assertion("known", "protected.content", AssertionStatus.PASS),
        _assertion("unknown", "protected.object", AssertionStatus.UNKNOWN),
    )
    result = score_assertions(assertions, CONFIG)
    assert result.verdict.value == "UNKNOWN"
    assert result.total_score == 20
    assert result.provisional is True
    assert result.analysis_coverage == 0.2


def test_scr_04_not_applicable_dimension_keeps_full_weight() -> None:
    assertions = (
        _assertion(
            "no-object",
            "protected.object",
            AssertionStatus.NOT_APPLICABLE,
            required=False,
        ),
    )
    result = score_assertions(assertions, CONFIG)
    object_score = next(item for item in result.dimensions if item.dimension == "protected.object")
    assert object_score.score == object_score.weight == 5
    assert result.analysis_coverage == 0.05
    assert result.verdict.value == "UNKNOWN"


def test_scr_05_empty_assertions_are_unobserved_not_a_vacuous_pass() -> None:
    result = score_assertions((), CONFIG)
    assert result.total_score == 0
    assert result.analysis_coverage == 0
    assert result.verdict.value == "UNKNOWN"


def test_scr_06_unknown_only_dimension_scores_zero() -> None:
    result = score_assertions(
        (_assertion("unknown", "protected.content", AssertionStatus.UNKNOWN),),
        CONFIG,
    )
    dimension = next(
        item for item in result.dimensions if item.dimension == "protected.content"
    )
    assert dimension.score == 0
    assert result.analysis_coverage == 0


def test_scr_07_explicit_not_applicable_is_observed_but_missing_dimensions_are_not() -> None:
    result = score_assertions(
        (
            _assertion(
                "no-object",
                "protected.object",
                AssertionStatus.NOT_APPLICABLE,
                required=False,
            ),
            _assertion("slot", "slot.inventory", AssertionStatus.PASS),
        ),
        CONFIG,
    )
    assert result.total_score == 20
    assert result.analysis_coverage == 0.2
    assert result.verdict.value == "UNKNOWN"
