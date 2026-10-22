from __future__ import annotations

import pytest

from docfit.observability.benchmark import (
    assess_observation_overhead,
    synthetic_conversion_probe,
)
from docfit.observability.models import ObservationBenchmark


def test_fixed_synthetic_observation_overhead_stays_within_o0_budget() -> None:
    disabled = []
    enabled = []
    for _ in range(3):
        disabled.append(synthetic_conversion_probe("off"))
        enabled.append(synthetic_conversion_probe("auto"))

    assessment = assess_observation_overhead(disabled, enabled)

    assert assessment.samples == 3
    assert assessment.wall_p95_increment_seconds <= assessment.wall_budget_seconds
    assert assessment.cpu_p95_increment_ratio <= assessment.cpu_budget_ratio
    assert assessment.peak_rss_increment_bytes <= assessment.peak_rss_budget_bytes
    assert assessment.passed is True


def test_observation_overhead_assessment_uses_group_p95_not_sample_pairing() -> None:
    disabled = [
        ObservationBenchmark(1, 10.0, 10.0, 100),
        ObservationBenchmark(1, 12.0, 12.0, 100),
        ObservationBenchmark(1, 14.0, 14.0, 100),
    ]
    enabled = [
        ObservationBenchmark(1, 14.2, 14.2, 100),
        ObservationBenchmark(1, 10.2, 10.2, 100),
        ObservationBenchmark(1, 12.2, 12.2, 100),
    ]

    assessment = assess_observation_overhead(disabled, enabled)

    assert assessment.wall_p95_increment_seconds == pytest.approx(0.2)
    assert assessment.cpu_p95_increment_ratio == pytest.approx(0.2 / 14.0)
