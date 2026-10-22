"""Conversion-owned bounded observation recorder lifecycle."""

from __future__ import annotations

import sqlite3
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Condition, Lock, Thread
from typing import Literal

from docfit.observability.events import (
    ObservationEvent,
    ProjectionContext,
    ProjectionResult,
    SanitizationReceipt,
    observation_event_bytes,
    record_sanitized_event,
    validate_observation_event,
)
from docfit.observability.models import (
    ObservationCoverageSummary,
    ObservationMode,
    ObservationRecorder,
    observation_coverage_summary_is_valid,
)
from docfit.observability.storage import (
    DEFAULT_STORAGE_LIMITS,
    DiskSpaceProbe,
    ObservationPersistResult,
    ObservationStorageError,
    ObservationStorageLimits,
    checkpoint_observation_store,
    initialize_observation_store,
    observation_state_root,
    observation_writer,
    persist_observation_batch,
)

OBSERVATION_QUEUE_MAX_EVENTS = 1024
OBSERVATION_QUEUE_MAX_BYTES = 16 * 1024 * 1024
OBSERVATION_QUEUE_P0_RESERVED_EVENTS = 128
OBSERVATION_WRITER_BATCH_EVENTS = 64
OBSERVATION_WRITER_BATCH_BYTES = 1024 * 1024
OBSERVATION_SUMMARY_FLUSH_SECONDS = 0.25
OBSERVATION_CLOSE_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class QueuePutResult:
    accepted: bool
    reason_code: str
    evicted_events: int = 0


@dataclass(frozen=True, slots=True)
class ObservationQueueSnapshot:
    queued_events: int
    queued_bytes: int
    unfinished_events: int
    high_water_events: int
    high_water_bytes: int
    closed: bool


@dataclass(frozen=True, slots=True)
class _QueuedEvent:
    event: ObservationEvent
    event_bytes: int


class BoundedObservationQueue:
    """Non-blocking P0/P1/P2 queue with a fixed P0 slot reserve."""

    def __init__(
        self,
        *,
        max_events: int = OBSERVATION_QUEUE_MAX_EVENTS,
        max_bytes: int = OBSERVATION_QUEUE_MAX_BYTES,
        p0_reserved_events: int = OBSERVATION_QUEUE_P0_RESERVED_EVENTS,
    ) -> None:
        if (
            max_events < 1
            or max_bytes < 1
            or p0_reserved_events < 1
            or p0_reserved_events > max_events
        ):
            raise ValueError("observer_queue_limits_invalid")
        self.max_events = max_events
        self.max_bytes = max_bytes
        self.p0_reserved_events = p0_reserved_events
        self._queues: dict[str, deque[_QueuedEvent]] = {
            "P0": deque(),
            "P1": deque(),
            "P2": deque(),
        }
        self._queued_events = 0
        self._queued_bytes = 0
        self._unfinished_events = 0
        self._high_water_events = 0
        self._high_water_bytes = 0
        self._closed = False
        self._condition = Condition(Lock())

    def _evict_one(self, priorities: Sequence[str]) -> bool:
        for priority in priorities:
            queue = self._queues[priority]
            if not queue:
                continue
            item = queue.popleft()
            self._queued_events -= 1
            self._queued_bytes -= item.event_bytes
            self._unfinished_events -= 1
            return True
        return False

    def put(self, event: ObservationEvent) -> QueuePutResult:
        if validate_observation_event(event) is not None:
            return QueuePutResult(False, "observer_event_payload_invalid")
        event_bytes = observation_event_bytes(event)
        if event_bytes > self.max_bytes:
            return QueuePutResult(False, "observer_queue_event_too_large")
        priority = event.priority
        evicted = 0
        with self._condition:
            if self._closed:
                return QueuePutResult(False, "observer_queue_closed")
            non_p0_limit = self.max_events - self.p0_reserved_events
            non_p0_count = len(self._queues["P1"]) + len(self._queues["P2"])
            if priority == "P2" and non_p0_count >= non_p0_limit:
                return QueuePutResult(False, "observer_queue_full")
            if priority == "P1" and non_p0_count >= non_p0_limit:
                if self._evict_one(("P2",)):
                    evicted += 1
                else:
                    return QueuePutResult(False, "observer_queue_full")
            eviction_order: tuple[str, ...]
            if priority == "P0":
                eviction_order = ("P2", "P1")
            elif priority == "P1":
                eviction_order = ("P2",)
            else:
                eviction_order = ()
            while (
                self._queued_events >= self.max_events
                or self._queued_bytes + event_bytes > self.max_bytes
            ):
                if not self._evict_one(eviction_order):
                    return QueuePutResult(False, "observer_queue_full", evicted)
                evicted += 1
            self._queues[priority].append(_QueuedEvent(event, event_bytes))
            self._queued_events += 1
            self._queued_bytes += event_bytes
            self._unfinished_events += 1
            self._high_water_events = max(
                self._high_water_events, self._queued_events
            )
            self._high_water_bytes = max(self._high_water_bytes, self._queued_bytes)
            self._condition.notify()
        return QueuePutResult(True, "observer_event_queued", evicted)

    def get_batch(
        self,
        *,
        max_events: int = OBSERVATION_WRITER_BATCH_EVENTS,
        max_bytes: int = OBSERVATION_WRITER_BATCH_BYTES,
        wait_seconds: float = 0.05,
    ) -> tuple[ObservationEvent, ...]:
        deadline = time.monotonic() + max(0.0, wait_seconds)
        with self._condition:
            while self._queued_events == 0 and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ()
                self._condition.wait(remaining)
            if self._queued_events == 0:
                return ()
            result: list[ObservationEvent] = []
            result_bytes = 0
            for priority in ("P0", "P1", "P2"):
                queue = self._queues[priority]
                while queue and len(result) < max_events:
                    next_item = queue[0]
                    if result and result_bytes + next_item.event_bytes > max_bytes:
                        break
                    item = queue.popleft()
                    self._queued_events -= 1
                    self._queued_bytes -= item.event_bytes
                    result.append(item.event)
                    result_bytes += item.event_bytes
                if len(result) >= max_events or (
                    result and result_bytes >= max_bytes
                ):
                    break
            return tuple(result)

    def task_done(self, count: int) -> None:
        if count < 0:
            raise ValueError("observer_queue_task_count_invalid")
        with self._condition:
            self._unfinished_events = max(0, self._unfinished_events - count)
            self._condition.notify_all()

    def drop_queued(self) -> int:
        with self._condition:
            count = self._queued_events
            for queue in self._queues.values():
                queue.clear()
            self._unfinished_events = max(0, self._unfinished_events - count)
            self._queued_events = 0
            self._queued_bytes = 0
            self._condition.notify_all()
            return count

    def flush(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        with self._condition:
            while self._unfinished_events:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def closed_and_empty(self) -> bool:
        with self._condition:
            return self._closed and self._queued_events == 0

    def snapshot(self) -> ObservationQueueSnapshot:
        with self._condition:
            return ObservationQueueSnapshot(
                self._queued_events,
                self._queued_bytes,
                self._unfinished_events,
                self._high_water_events,
                self._high_water_bytes,
                self._closed,
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

    def note_drop(self, receipt: SanitizationReceipt) -> None:
        return None

    def close(self) -> None:
        return None


BatchPersister = Callable[
    [sqlite3.Connection, Path, Sequence[ObservationEvent]],
    ObservationPersistResult,
]


class BufferedObservationRecorder:
    """Bounded queue plus one background SQLite writer."""

    def __init__(
        self,
        *,
        root: Path,
        database: Path,
        queue: BoundedObservationQueue | None = None,
        storage_limits: ObservationStorageLimits = DEFAULT_STORAGE_LIMITS,
        disk_space_probe: DiskSpaceProbe | None = None,
        batch_persister: BatchPersister | None = None,
    ) -> None:
        self.root = root
        self.database = database
        self.queue = queue or BoundedObservationQueue()
        self.storage_limits = storage_limits
        self._disk_space_probe = disk_space_probe
        self._batch_persister = batch_persister
        self._lock = Lock()
        self._events_persisted = 0
        self._events_dropped = 0
        self._last_observed_at: str | None = None
        self._failure_codes: set[str] = set()
        self._missing_sources: set[str] = set()
        self._writer_failed = False
        self._closed = False
        self._thread = Thread(
            target=self._writer_main,
            name="docfit-observation-writer",
            daemon=True,
        )
        self._thread.start()

    @property
    def enabled(self) -> bool:
        return True

    @property
    def state_root(self) -> Path:
        return self.root

    @property
    def failure_code(self) -> str | None:
        with self._lock:
            return min(self._failure_codes) if self._failure_codes else None

    def _record_failure(
        self,
        code: str,
        *,
        dropped: int = 0,
        missing_source: str | None = None,
    ) -> None:
        with self._lock:
            if len(self._failure_codes) < 32:
                self._failure_codes.add(code)
            self._events_dropped += max(0, dropped)
            if missing_source is not None and len(self._missing_sources) < 32:
                self._missing_sources.add(missing_source)

    def _accept_persist_result(self, result: ObservationPersistResult) -> None:
        with self._lock:
            self._events_persisted += result.persisted_events
            self._events_dropped += result.dropped_events
            if result.last_observed_at is not None:
                self._last_observed_at = result.last_observed_at
            for code in result.failure_codes:
                if len(self._failure_codes) < 32:
                    self._failure_codes.add(code)
            if result.dropped_events and len(self._missing_sources) < 32:
                self._missing_sources.add("collector")

    def _persist(
        self,
        connection: sqlite3.Connection,
        events: Sequence[ObservationEvent],
    ) -> ObservationPersistResult:
        if self._batch_persister is not None:
            return self._batch_persister(connection, self.database, events)
        kwargs: dict[str, object] = {"limits": self.storage_limits}
        if self._disk_space_probe is not None:
            kwargs["disk_space_probe"] = self._disk_space_probe
        return persist_observation_batch(
            connection,
            self.database,
            events,
            **kwargs,  # type: ignore[arg-type]
        )

    def _fail_writer(self, code: str) -> None:
        with self._lock:
            self._writer_failed = True
        dropped = self.queue.drop_queued()
        self._record_failure(code, dropped=dropped, missing_source="collector")

    def _writer_main(self) -> None:
        try:
            with observation_writer(
                self.database,
                limits=self.storage_limits,
            ) as connection:
                while True:
                    batch = self.queue.get_batch()
                    if not batch:
                        if self.queue.closed_and_empty:
                            break
                        continue
                    try:
                        result = self._persist(connection, batch)
                    except ObservationStorageError as error:
                        self._record_failure(
                            error.code,
                            dropped=len(batch),
                            missing_source="collector",
                        )
                        self.queue.task_done(len(batch))
                        if error.code != "observer_database_busy":
                            self._fail_writer(error.code)
                            break
                        continue
                    except Exception:
                        self._record_failure(
                            "observer_writer_failed",
                            dropped=len(batch),
                            missing_source="collector",
                        )
                        self.queue.task_done(len(batch))
                        self._fail_writer("observer_writer_failed")
                        break
                    self._accept_persist_result(result)
                    self.queue.task_done(len(batch))
        except ObservationStorageError as error:
            self._fail_writer(error.code)
        except Exception:
            self._fail_writer("observer_writer_failed")

    def record(self, event: ObservationEvent) -> SanitizationReceipt:
        started = time.perf_counter_ns()
        with self._lock:
            unavailable = self._writer_failed or self._closed
        if unavailable:
            self._record_failure(
                "observer_writer_unavailable",
                dropped=1,
                missing_source="collector",
            )
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            return SanitizationReceipt(
                "dropped", "observer_writer_unavailable", elapsed
            )
        result = self.queue.put(event)
        if result.evicted_events:
            self._record_failure(
                "observer_queue_full",
                dropped=result.evicted_events,
                missing_source="queue",
            )
        if not result.accepted:
            self._record_failure(
                result.reason_code,
                dropped=1,
                missing_source="queue",
            )
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        return SanitizationReceipt(
            "accepted" if result.accepted else "dropped",
            result.reason_code,
            elapsed,
        )

    def note_drop(self, receipt: SanitizationReceipt) -> None:
        if receipt.status == "dropped":
            self._record_failure(receipt.reason_code, dropped=1)

    def summary(self) -> ObservationCoverageSummary:
        if not self.queue.flush(OBSERVATION_SUMMARY_FLUSH_SECONDS):
            self._record_failure(
                "observer_flush_timeout",
                missing_source="collector",
            )
        with self._lock:
            persisted = self._events_persisted
            dropped = self._events_dropped
            failures = tuple(sorted(self._failure_codes))
            missing = tuple(sorted(self._missing_sources))
            observed_at = self._last_observed_at
            writer_failed = self._writer_failed
        state: Literal["complete", "degraded", "unavailable"]
        if writer_failed and persisted == 0:
            state = "unavailable"
        elif failures or missing or dropped:
            state = "degraded"
        else:
            state = "complete"
        return ObservationCoverageSummary(
            state=state,
            events_persisted=persisted,
            events_dropped=dropped,
            missing_sources=missing,
            last_observed_at=observed_at,
            failure_codes=failures,
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.queue.close()
        if not self.queue.flush(OBSERVATION_CLOSE_SECONDS):
            self._record_failure(
                "observer_flush_timeout",
                missing_source="collector",
            )
        self._thread.join(OBSERVATION_CLOSE_SECONDS)
        if self._thread.is_alive():
            self._record_failure(
                "observer_writer_shutdown_timeout",
                missing_source="collector",
            )
            return
        try:
            checkpoint_observation_store(self.database)
        except ObservationStorageError as error:
            self._record_failure(error.code, missing_source="collector")


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
        return BufferedObservationRecorder(root=root, database=database)
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

    def _note_drop(self, receipt: SanitizationReceipt) -> SanitizationReceipt:
        self._recorder.note_drop(receipt)
        return receipt

    def accept(self, result: ProjectionResult) -> SanitizationReceipt:
        if result.event is None:
            return self._note_drop(result.receipt)
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
            return self._note_drop(
                SanitizationReceipt(
                    "dropped",
                    "observer_projector_failed",
                    0.0,
                )
            )
