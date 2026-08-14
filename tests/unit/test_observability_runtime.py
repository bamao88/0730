from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from docfit.observability.benchmark import measure_operation
from docfit.observability.events import (
    ProjectionContext,
    ProjectionResult,
    SanitizationReceipt,
)
from docfit.observability.models import ObservationCoverageSummary
from docfit.observability.privacy import project_app_event
from docfit.observability.runtime import (
    OBSERVATION_QUEUE_MAX_EVENTS,
    OBSERVATION_QUEUE_P0_RESERVED_EVENTS,
    BoundedObservationQueue,
    BufferedObservationRecorder,
    NullObservationRecorder,
    ObservationRun,
    close_observation_safely,
    create_observation_recorder,
    observation_summary_safely,
)
from docfit.observability.storage import (
    ObservationPersistResult,
    ObservationStorageError,
    initialize_observation_store,
    load_observation_events,
)

RUN_ID = "run_0123456789abcdef0123456789abcdef"


def _event(sequence: int, *, priority: str = "P1"):
    result = project_app_event(
        ProjectionContext(
            RUN_ID,
            sequence,
            f"2026-08-03T08:31:{sequence % 60:02d}+00:00",
            float(sequence),
        ),
        source_event_id=f"event-{sequence}",
        kind="backend_started",
        status="started",
        backend="synthetic-backend",
        model="synthetic-model",
        attempt=sequence,
    )
    assert result.event is not None
    return replace(result.event, priority=priority)


def test_disabled_recorder_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    state_home = tmp_path / "state"

    recorder = create_observation_recorder(
        "off",
        environment={"XDG_STATE_HOME": str(state_home)},
        task_root=tmp_path / "task",
        repository_root=tmp_path / "repository",
    )

    assert isinstance(recorder, NullObservationRecorder)
    assert recorder.enabled is False
    assert recorder.state_root is None
    assert recorder.failure_code is None
    assert not state_home.exists()


def test_auto_recorder_starts_bounded_writer_and_persists_without_web(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = tmp_path / "task"
    repository = tmp_path / "repository"
    task.mkdir()
    repository.mkdir()
    monkeypatch.setattr(
        "docfit.observability.storage.shutil.disk_usage",
        lambda _: SimpleNamespace(
            total=100 * 1024 * 1024 * 1024,
            free=80 * 1024 * 1024 * 1024,
        ),
    )

    recorder = create_observation_recorder(
        "auto",
        environment={"XDG_STATE_HOME": str(tmp_path / "state")},
        task_root=task,
        repository_root=repository,
    )
    assert isinstance(recorder, BufferedObservationRecorder)
    try:
        receipt = recorder.record(_event(1))
        summary = recorder.summary()
        assert receipt.status == "accepted"
        assert summary.state == "complete"
        assert summary.events_persisted == 1
        assert summary.events_dropped == 0
    finally:
        recorder.close()

    assert load_observation_events(recorder.database, RUN_ID) == (_event(1),)


def test_auto_setup_failure_degrades_to_null(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()

    recorder = create_observation_recorder(
        "auto",
        environment={"XDG_STATE_HOME": str(task)},
        task_root=task,
        repository_root=tmp_path / "repository",
    )

    assert isinstance(recorder, NullObservationRecorder)
    assert recorder.failure_code == "observer_state_not_external"


def test_production_queue_reserves_at_least_ten_percent_and_sixty_four_slots() -> None:
    assert OBSERVATION_QUEUE_P0_RESERVED_EVENTS >= 64
    assert (
        OBSERVATION_QUEUE_P0_RESERVED_EVENTS
        >= OBSERVATION_QUEUE_MAX_EVENTS * 0.10
    )


def test_queue_pressure_drops_p2_then_p1_and_preserves_p0() -> None:
    queue = BoundedObservationQueue(
        max_events=10,
        max_bytes=1024 * 1024,
        p0_reserved_events=2,
    )
    for sequence in range(1, 9):
        assert queue.put(_event(sequence, priority="P2")).accepted

    replacement = queue.put(_event(20, priority="P1"))
    assert replacement.accepted
    assert replacement.evicted_events == 1
    assert queue.put(_event(21, priority="P0")).accepted
    assert queue.put(_event(22, priority="P0")).accepted
    promoted = queue.put(_event(23, priority="P0"))
    assert promoted.accepted
    assert promoted.evicted_events == 1

    batch = queue.get_batch(max_events=10)
    assert [event.priority for event in batch[:3]] == ["P0", "P0", "P0"]
    assert "P1" in [event.priority for event in batch]
    queue.task_done(len(batch))


def test_queue_hard_byte_limit_is_non_blocking() -> None:
    sample = _event(1, priority="P2")
    from docfit.observability.events import observation_event_bytes

    sample_bytes = observation_event_bytes(sample)
    queue = BoundedObservationQueue(
        max_events=10,
        max_bytes=sample_bytes + 8,
        p0_reserved_events=2,
    )

    started = time.perf_counter()
    assert queue.put(sample).accepted
    dropped = queue.put(_event(2, priority="P2"))
    elapsed = time.perf_counter() - started

    assert dropped.accepted is False
    assert dropped.reason_code == "observer_queue_full"
    assert elapsed < 0.1


def test_queue_put_p95_stays_within_synchronous_hook_budget() -> None:
    queue = BoundedObservationQueue()
    samples: list[float] = []
    for sequence in range(1, 513):
        started = time.perf_counter_ns()
        result = queue.put(_event(sequence, priority="P2"))
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
        assert result.accepted

    ordered = sorted(samples)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    assert p95 <= 2.0
    batch = queue.get_batch(max_events=512, max_bytes=16 * 1024 * 1024)
    queue.task_done(len(batch))


def test_observation_run_counts_projector_drop_without_raw_fallback(
    tmp_path: Path,
) -> None:
    database = initialize_observation_store(tmp_path / "state")
    recorder = BufferedObservationRecorder(root=database.parent, database=database)
    run = ObservationRun(RUN_ID, recorder)
    try:
        receipt = run.accept(
            ProjectionResult(
                None,
                SanitizationReceipt(
                    "dropped", "observer_projector_deadline", 11.0
                ),
            )
        )
        summary = recorder.summary()
    finally:
        recorder.close()

    assert receipt.status == "dropped"
    assert summary.state == "degraded"
    assert summary.events_persisted == 0
    assert summary.events_dropped == 1
    assert summary.failure_codes == ("observer_projector_deadline",)


def test_writer_busy_drops_batch_and_keeps_recorder_available(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")

    def busy(*_: object) -> ObservationPersistResult:
        raise ObservationStorageError("observer_database_busy")

    recorder = BufferedObservationRecorder(
        root=database.parent,
        database=database,
        batch_persister=busy,  # type: ignore[arg-type]
    )
    try:
        assert recorder.record(_event(1)).status == "accepted"
        summary = recorder.summary()
    finally:
        recorder.close()

    assert summary.state == "degraded"
    assert summary.events_dropped == 1
    assert "observer_database_busy" in summary.failure_codes
    assert recorder.enabled is True


def test_fatal_writer_failure_is_unavailable_and_never_raises_to_caller(
    tmp_path: Path,
) -> None:
    database = initialize_observation_store(tmp_path / "state")

    def corrupt(*_: object) -> ObservationPersistResult:
        raise ObservationStorageError("observer_database_corrupt")

    recorder = BufferedObservationRecorder(
        root=database.parent,
        database=database,
        batch_persister=corrupt,  # type: ignore[arg-type]
    )
    try:
        assert recorder.record(_event(1)).status == "accepted"
        summary = recorder.summary()
        later = recorder.record(_event(2))
    finally:
        recorder.close()

    assert summary.state == "unavailable"
    assert "observer_database_corrupt" in summary.failure_codes
    assert later.status == "dropped"
    assert later.reason_code == "observer_writer_unavailable"


def test_summary_and_close_are_bounded_when_writer_stalls(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    release = Event()

    def stalled(
        *_: object,
    ) -> ObservationPersistResult:
        release.wait(2)
        return ObservationPersistResult(1, 0, 0, 1, _event(1).observed_at, ())

    recorder = BufferedObservationRecorder(
        root=database.parent,
        database=database,
        batch_persister=stalled,  # type: ignore[arg-type]
    )
    assert recorder.record(_event(1)).status == "accepted"
    started = time.perf_counter()
    summary = recorder.summary()
    recorder.close()
    elapsed = time.perf_counter() - started
    release.set()

    assert summary.state == "degraded"
    assert "observer_flush_timeout" in summary.failure_codes
    assert elapsed < 1.5


def test_close_failure_never_escapes_conversion_boundary() -> None:
    class BrokenRecorder(NullObservationRecorder):
        def close(self) -> None:
            raise RuntimeError("sensitive close detail")

    close_observation_safely(BrokenRecorder())


def test_summary_failure_returns_fixed_unavailable_shape() -> None:
    class BrokenRecorder(NullObservationRecorder):
        def summary(self) -> object:
            raise RuntimeError("PRIVATE_OBSERVER_FAILURE_CANARY")

    summary = observation_summary_safely(BrokenRecorder())  # type: ignore[arg-type]

    assert summary.state == "unavailable"
    assert summary.events_persisted is None
    assert summary.events_dropped is None
    assert summary.failure_codes == ("observer_summary_failed",)
    assert "PRIVATE_OBSERVER_FAILURE_CANARY" not in str(summary)


def test_invalid_summary_dataclass_returns_fixed_unavailable_shape() -> None:
    class InvalidRecorder(NullObservationRecorder):
        def summary(self) -> ObservationCoverageSummary:
            return ObservationCoverageSummary(
                state="complete",
                events_persisted=-1,
                events_dropped=0,
                missing_sources=(),
                last_observed_at=None,
                failure_codes=(),
            )

    summary = observation_summary_safely(InvalidRecorder())

    assert summary.state == "unavailable"
    assert summary.events_persisted is None
    assert summary.failure_codes == ("observer_summary_invalid",)


def test_benchmark_helper_reports_wall_cpu_and_rss() -> None:
    calls: list[int] = []
    result = measure_operation(lambda: calls.append(1), iterations=3)

    assert calls == [1, 1, 1]
    assert result.iterations == 3
    assert result.wall_seconds >= 0
    assert result.cpu_seconds >= 0
    assert result.peak_rss_bytes > 0


def test_disabled_observation_run_does_not_execute_projector() -> None:
    run = ObservationRun(RUN_ID, NullObservationRecorder())
    called = False

    def projector(_: ProjectionContext) -> ProjectionResult:
        nonlocal called
        called = True
        raise AssertionError("disabled projector must not execute")

    receipt = run.project(projector)

    assert called is False
    assert receipt == SanitizationReceipt("dropped", "observation_disabled", 0.0)
