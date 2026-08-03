"""Conversion-owned observation bootstrap lifecycle."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from docfit.observability.events import (
    ObservationEvent,
    ProjectionContext,
    ProjectionResult,
    SanitizationReceipt,
    record_sanitized_event,
)
from docfit.observability.models import (
    ObservationCoverageSummary,
    ObservationMode,
    ObservationRecorder,
    observation_coverage_summary_is_valid,
)
from docfit.observability.storage import (
    ObservationStorageError,
    initialize_observation_store,
    observation_state_root,
)


@dataclass(slots=True)
class NullObservationRecorder:
    """No-op recorder used for the disabled path and safe setup fallback."""

    failure_code: str | None = None

    @property
    def enabled(self) -> bool:
        return False

    @property
    def state_root(self) -> Path | None:
        return None

    def summary(self) -> ObservationCoverageSummary:
        return unavailable_observation_summary(self.failure_code or "observation_disabled")

    def record(self, event: ObservationEvent) -> SanitizationReceipt:
        return SanitizationReceipt("dropped", "observation_disabled", 0.0)

    def close(self) -> None:
        return None


@dataclass(slots=True)
class BootstrapObservationRecorder:
    """O0.0 store bootstrap; event recording is intentionally not implemented."""

    root: Path
    database: Path
    failure_code: str | None = None

    @property
    def enabled(self) -> bool:
        return True

    @property
    def state_root(self) -> Path:
        return self.root

    def summary(self) -> ObservationCoverageSummary:
        return unavailable_observation_summary("observation_event_capture_not_started")

    def record(self, event: ObservationEvent) -> SanitizationReceipt:
        return SanitizationReceipt(
            "dropped",
            "observation_event_capture_not_started",
            0.0,
        )

    def close(self) -> None:
        return None


def unavailable_observation_summary(code: str) -> ObservationCoverageSummary:
    return ObservationCoverageSummary(
        state="unavailable",
        events_persisted=None,
        events_dropped=None,
        missing_sources=(),
        last_observed_at=None,
        failure_codes=(code,),
    )


def observation_summary_safely(
    recorder: ObservationRecorder,
) -> ObservationCoverageSummary:
    try:
        summary = recorder.summary()
    except Exception:
        return unavailable_observation_summary("observer_summary_failed")
    if not observation_coverage_summary_is_valid(summary):
        return unavailable_observation_summary("observer_summary_invalid")
    return summary


def create_observation_recorder(
    mode: ObservationMode,
    *,
    task_root: Path | None = None,
    repository_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> ObservationRecorder:
    """Create a recorder without allowing observer setup to fail conversion."""

    if mode == "off":
        return NullObservationRecorder()
    try:
        root = observation_state_root(
            environment=environment,
            task_root=task_root,
            repository_root=repository_root,
        )
        database = initialize_observation_store(root)
        return BootstrapObservationRecorder(root=root, database=database)
    except ObservationStorageError as error:
        return NullObservationRecorder(failure_code=error.code)
    except Exception:
        return NullObservationRecorder(failure_code="observer_setup_failed")


def close_observation_safely(recorder: ObservationRecorder) -> None:
    try:
        recorder.close()
    except Exception:
        return None


class ObservationRun:
    """Run-local clock/sequence seam that only accepts projected events."""

    def __init__(self, run_id: str, recorder: ObservationRecorder) -> None:
        self.run_id = run_id
        self._recorder = recorder
        self._started = time.monotonic()
        self._sequence = 0
        self._lock = Lock()

    def next_context(self) -> ProjectionContext:
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        return ProjectionContext(
            run_id=self.run_id,
            source_sequence=sequence,
            observed_at=datetime.now(UTC).isoformat(),
            monotonic_offset_ms=max(0.0, (time.monotonic() - self._started) * 1000),
        )

    def accept(self, result: ProjectionResult) -> SanitizationReceipt:
        if result.event is None:
            return result.receipt
        return record_sanitized_event(self._recorder, result.event)

    @property
    def enabled(self) -> bool:
        return self._recorder.enabled

    def project(
        self,
        projector: Callable[[ProjectionContext], ProjectionResult],
    ) -> SanitizationReceipt:
        if not self.enabled:
            return SanitizationReceipt("dropped", "observation_disabled", 0.0)
        try:
            return self.accept(projector(self.next_context()))
        except Exception:
            return SanitizationReceipt("dropped", "observer_projector_failed", 0.0)
