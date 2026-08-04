from __future__ import annotations

from docfit.observability.benchmark import (
    assess_observation_overhead,
    synthetic_conversion_probe,
)


def test_fixed_synthetic_observation_overhead_stays_within_o0_budget() -> None:
    disabled = [synthetic_conversion_probe("off") for _ in range(3)]
    enabled = [synthetic_conversion_probe("auto") for _ in range(3)]

    assessment = assess_observation_overhead(disabled, enabled)

    assert assessment.samples == 3
    assert assessment.wall_p95_increment_seconds <= assessment.wall_budget_seconds
    assert assessment.cpu_p95_increment_ratio <= assessment.cpu_budget_ratio
    assert assessment.peak_rss_increment_bytes <= assessment.peak_rss_budget_bytes
    assert assessment.passed is True
