"""Deterministic local measurement helper for O0 enabled/disabled comparisons."""

from __future__ import annotations

import resource
import sys
import time
from collections.abc import Callable

from docfit.observability.models import ObservationBenchmark


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
