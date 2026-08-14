"""Score assertion results without weakening hard quality gates."""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    AssertionResult,
    AssertionStatus,
    DimensionScore,
    ScoringConfig,
    Verdict,
    View,
    ViewScore,
)


@dataclass(frozen=True)
class ScoringResult:
    verdict: Verdict
    total_score: float
    provisional: bool
    analysis_coverage: float
    views: tuple[ViewScore, ...]
    dimensions: tuple[DimensionScore, ...]


def _dimension_score(
    dimension: str,
    weight: float,
    assertions: tuple[AssertionResult, ...],
) -> DimensionScore:
    relevant = tuple(item for item in assertions if item.dimension == dimension)
    passed = sum(item.status is AssertionStatus.PASS for item in relevant)
    failed = sum(item.status is AssertionStatus.FAIL for item in relevant)
    unknown = sum(item.status is AssertionStatus.UNKNOWN for item in relevant)
    not_applicable = sum(
        item.status is AssertionStatus.NOT_APPLICABLE for item in relevant
    )
    comparable = passed + failed + unknown
    if comparable == 0:
        ratio = 1.0 if not_applicable > 0 else 0.0
    elif dimension == "slot.inventory":
        ratio = 2 * passed / (2 * passed + failed + 2 * unknown)
    else:
        ratio = passed / comparable
    return DimensionScore(
        dimension=dimension,
        weight=weight,
        score=round(weight * ratio, 4),
        passed=passed,
        failed=failed,
        unknown=unknown,
        not_applicable=not_applicable,
    )


def score_assertions(
    assertions: tuple[AssertionResult, ...],
    config: ScoringConfig,
) -> ScoringResult:
    dimensions = tuple(
        _dimension_score(dimension, weight, assertions)
        for dimension, weight in config.weights.items()
    )
    required = tuple(item for item in assertions if item.required)
    assertions_by_dimension = {
        dimension: tuple(item for item in assertions if item.dimension == dimension)
        for dimension in config.weights
    }
    has_unobserved_dimension = any(
        weight > 0 and not assertions_by_dimension[dimension]
        for dimension, weight in config.weights.items()
    )
    hard_failure = any(
        item.status is AssertionStatus.FAIL and item.failure_code in config.hard_failures
        for item in assertions
    )
    if hard_failure or any(item.status is AssertionStatus.FAIL for item in required):
        verdict = Verdict.FAIL
    elif has_unobserved_dimension or any(
        item.status is AssertionStatus.UNKNOWN for item in assertions
    ):
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.PASS

    observed_weight = 0.0
    for dimension, weight in config.weights.items():
        relevant = assertions_by_dimension[dimension]
        if not relevant:
            continue
        observed = sum(
            item.status
            in {
                AssertionStatus.PASS,
                AssertionStatus.FAIL,
                AssertionStatus.NOT_APPLICABLE,
            }
            for item in relevant
        )
        observed_weight += weight * observed / len(relevant)
    coverage = observed_weight / config.total_points
    provisional = has_unobserved_dimension or any(
        item.status is AssertionStatus.UNKNOWN for item in assertions
    )
    views = tuple(
        ViewScore(
            view=view,
            weight=sum(
                dimension.weight
                for dimension in dimensions
                if dimension.dimension.startswith(f"{view.value}.")
            ),
            score=sum(
                dimension.score
                for dimension in dimensions
                if dimension.dimension.startswith(f"{view.value}.")
            ),
        )
        for view in (View.PROTECTED, View.SLOT)
    )
    return ScoringResult(
        verdict=verdict,
        total_score=round(sum(item.score for item in dimensions), 4),
        provisional=provisional,
        analysis_coverage=round(coverage, 6),
        views=views,
        dimensions=dimensions,
    )


__all__ = ["ScoringResult", "score_assertions"]
