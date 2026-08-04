"""Deterministic local measurement helper for O0 enabled/disabled comparisons."""

from __future__ import annotations

import hashlib
import math
import resource
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from docfit.observability.models import ObservationBenchmark, ObservationMode


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def measure_operation[T](
    operation: Callable[[], T], *, iterations: int = 1
) -> ObservationBenchmark:
    if iterations < 1:
        raise ValueError("iterations must be at least one")
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    for _ in range(iterations):
        operation()
    return ObservationBenchmark(
        iterations=iterations,
        wall_seconds=time.perf_counter() - wall_started,
        cpu_seconds=time.process_time() - cpu_started,
        peak_rss_bytes=_peak_rss_bytes(),
    )


@dataclass(frozen=True, slots=True)
class ObservationOverheadAssessment:
    samples: int
    baseline_wall_p95_seconds: float
    wall_p95_increment_seconds: float
    wall_budget_seconds: float
    cpu_p95_increment_ratio: float
    cpu_budget_ratio: float
    peak_rss_increment_bytes: int
    peak_rss_budget_bytes: int
    passed: bool


def _p95(values: list[float]) -> float:
    if not values:
        raise ValueError("observation_benchmark_samples_missing")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def assess_observation_overhead(
    disabled: list[ObservationBenchmark],
    enabled: list[ObservationBenchmark],
) -> ObservationOverheadAssessment:
    """Apply the O0 hard wall/CPU/RSS budget without hiding unknown baselines."""

    if not disabled or len(disabled) != len(enabled):
        raise ValueError("observation_benchmark_samples_invalid")
    baseline_wall_p95 = _p95([sample.wall_seconds for sample in disabled])
    wall_increment = _p95(
        [
            max(0.0, observed.wall_seconds - baseline.wall_seconds)
            for baseline, observed in zip(disabled, enabled, strict=True)
        ]
    )
    cpu_ratios = [
        (
            max(0.0, observed.cpu_seconds - baseline.cpu_seconds)
            / baseline.cpu_seconds
            if baseline.cpu_seconds > 0
            else math.inf
        )
        for baseline, observed in zip(disabled, enabled, strict=True)
    ]
    cpu_increment_ratio = _p95(cpu_ratios)
    peak_rss_increment = max(
        0,
        max(sample.peak_rss_bytes for sample in enabled)
        - max(sample.peak_rss_bytes for sample in disabled),
    )
    wall_budget = max(baseline_wall_p95 * 0.03, 0.250)
    cpu_budget = 0.05
    rss_budget = 64 * 1024 * 1024
    return ObservationOverheadAssessment(
        samples=len(disabled),
        baseline_wall_p95_seconds=baseline_wall_p95,
        wall_p95_increment_seconds=wall_increment,
        wall_budget_seconds=wall_budget,
        cpu_p95_increment_ratio=cpu_increment_ratio,
        cpu_budget_ratio=cpu_budget,
        peak_rss_increment_bytes=peak_rss_increment,
        peak_rss_budget_bytes=rss_budget,
        passed=(
            wall_increment <= wall_budget
            and cpu_increment_ratio <= cpu_budget
            and peak_rss_increment <= rss_budget
        ),
    )


def synthetic_conversion_probe(
    mode: ObservationMode,
    *,
    work_iterations: int = 40_000,
    observation_events: int = 64,
) -> ObservationBenchmark:
    """Measure fixed local work plus a conversion-sized metadata event stream."""

    from docfit.observability.privacy import project_app_event
    from docfit.observability.runtime import (
        ObservationRun,
        close_observation_safely,
        create_observation_recorder,
    )

    payload = b"docfit-observation-benchmark" * 2048
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    with tempfile.TemporaryDirectory(prefix="docfit-observation-benchmark-") as temporary:
        root = Path(temporary)
        recorder = create_observation_recorder(
            mode,
            task_root=root / "task",
            repository_root=Path.cwd(),
            environment={"XDG_STATE_HOME": str(root / "state")},
        )
        run = ObservationRun("run_0123456789abcdef0123456789abcdef", recorder)
        for _ in range(work_iterations):
            hashlib.sha256(payload).digest()
        for sequence in range(observation_events):
            run.project(
                partial(
                    project_app_event,
                    source_event_id=f"benchmark-{sequence}",
                    kind="backend_started",
                    status="started",
                    backend="synthetic",
                    model="synthetic",
                    attempt=sequence + 1,
                )
            )
        close_observation_safely(recorder)
    return ObservationBenchmark(
        iterations=1,
        wall_seconds=time.perf_counter() - wall_started,
        cpu_seconds=time.process_time() - cpu_started,
        peak_rss_bytes=_peak_rss_bytes(),
    )
