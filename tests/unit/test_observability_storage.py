from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from docfit.observability.events import ProjectionContext, observation_event_bytes
from docfit.observability.privacy import project_app_event
from docfit.observability.storage import (
    OBSERVATION_BUSY_TIMEOUT_MS,
    OBSERVATION_DATABASE_NAME,
    OBSERVATION_SCHEMA_VERSION,
    ObservationStorageError,
    ObservationStorageLimits,
    checkpoint_observation_store,
    clear_observation_history,
    delete_observation_run,
    immediate_transaction,
    initialize_observation_store,
    list_observation_runs,
    load_observation_events,
    observation_reader,
    observation_state_root,
    observation_storage_bytes,
    observation_writer,
    persist_observation_batch,
)

RUN_ID = "run_0123456789abcdef0123456789abcdef"
TASK_REF = "task_fedcba9876543210fedcba9876543210"
BASE_TIME = datetime(2026, 8, 3, 8, 31, tzinfo=UTC)


def _ample_disk_space(_: Path) -> tuple[int, int]:
    return 100 * 1024 * 1024 * 1024, 80 * 1024 * 1024 * 1024


def _run_id(index: int) -> str:
    return f"run_{index:032x}"


def _event(
    sequence: int,
    *,
    run_id: str = RUN_ID,
    kind: str = "backend_started",
    status: str = "started",
    observed_at: datetime | None = None,
):
    context = ProjectionContext(
        run_id,
        sequence,
        (observed_at or (BASE_TIME + timedelta(milliseconds=sequence))).isoformat(),
        float(sequence),
    )
    result = project_app_event(
        context,
        source_event_id=f"event-{sequence}",
        kind=kind,  # type: ignore[arg-type]
        status=status,
        task_ref=TASK_REF if kind == "run_started" else None,
        backend="synthetic-backend" if kind.startswith("backend_") else None,
        model="synthetic-model" if kind.startswith("backend_") else None,
        attempt=sequence if kind.startswith("backend_") else None,
        duration_ms=float(sequence) if kind.endswith("finished") else None,
    )
    assert result.event is not None, result.receipt
    return result.event


def _completed_run(
    index: int,
    *,
    completed_at: datetime | None = None,
) -> tuple:
    run_id = _run_id(index)
    finished = completed_at or (BASE_TIME + timedelta(seconds=index))
    return (
        _event(1, run_id=run_id, kind="run_started", observed_at=finished - timedelta(seconds=1)),
        _event(
            2,
            run_id=run_id,
            kind="run_finished",
            status="completed",
            observed_at=finished,
        ),
    )


def test_state_root_is_private_and_outside_task_and_repository(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    repository_root = tmp_path / "repository"
    state_home = tmp_path / "state"
    task_root.mkdir()
    repository_root.mkdir()

    root = observation_state_root(
        environment={"XDG_STATE_HOME": str(state_home)},
        task_root=task_root,
        repository_root=repository_root,
    )
    database = initialize_observation_store(root)

    assert root == state_home / "docfit" / "observability"
    assert database == root / OBSERVATION_DATABASE_NAME
    assert os.stat(root).st_mode & 0o777 == 0o700
    assert os.stat(database).st_mode & 0o777 == 0o600


@pytest.mark.parametrize("forbidden", ["task", "repository"])
def test_state_root_rejects_task_or_repository_storage(
    tmp_path: Path, forbidden: str
) -> None:
    task_root = tmp_path / "task"
    repository_root = tmp_path / "repository"
    task_root.mkdir()
    repository_root.mkdir()
    base = task_root if forbidden == "task" else repository_root

    with pytest.raises(ObservationStorageError) as failure:
        observation_state_root(
            environment={"XDG_STATE_HOME": str(base)},
            task_root=task_root,
            repository_root=repository_root,
        )

    assert failure.value.code == "observer_state_not_external"


def test_sqlite_schema_v2_wal_indexes_and_query_only_reader(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")

    with observation_writer(database) as writer:
        assert writer.execute("PRAGMA user_version").fetchone() == (
            OBSERVATION_SCHEMA_VERSION,
        )
        assert writer.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert writer.execute(
            "SELECT value FROM observation_meta WHERE key='schema'"
        ).fetchone() == ("docfit_observation_v2",)
        tables = {
            row[0]
            for row in writer.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"observation_runs", "observation_events"} <= tables

    with observation_reader(database) as reader:
        assert reader.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("CREATE TABLE forbidden(value TEXT)")


def test_valid_v1_store_migrates_to_v2(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    database = state / OBSERVATION_DATABASE_NAME
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE observation_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID"
        )
        connection.execute(
            "INSERT INTO observation_meta(key, value) VALUES ('schema', 'docfit_observation_v1')"
        )
        connection.execute("PRAGMA user_version=1")

    initialize_observation_store(state)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute(
            "SELECT value FROM observation_meta WHERE key='schema'"
        ).fetchone() == ("docfit_observation_v2",)


def test_newer_sqlite_schema_is_rejected(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=999")

    with pytest.raises(ObservationStorageError) as failure:
        initialize_observation_store(tmp_path / "state")

    assert failure.value.code == "observer_schema_unsupported"


def test_declared_v1_with_missing_structure_is_rejected(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    database = state / OBSERVATION_DATABASE_NAME
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=1")

    with pytest.raises(ObservationStorageError) as failure:
        initialize_observation_store(state)

    assert failure.value.code == "observer_schema_invalid"


def test_persist_query_and_checkpoint_round_trip_only_sanitized_events(
    tmp_path: Path,
) -> None:
    database = initialize_observation_store(tmp_path / "state")
    events = _completed_run(1)

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            events,
            disk_space_probe=_ample_disk_space,
        )

    assert result.persisted_events == 2
    assert result.dropped_events == 0
    assert result.failure_codes == ()
    assert load_observation_events(database, _run_id(1)) == events
    runs = list_observation_runs(database)
    assert len(runs) == 1
    assert runs[0].run_id == _run_id(1)
    assert runs[0].task_ref == TASK_REF
    assert runs[0].status == "completed"
    assert runs[0].event_count == 2
    assert runs[0].event_bytes == sum(observation_event_bytes(event) for event in events)
    checkpoint_observation_store(database)


def test_exact_duplicate_is_acknowledged_without_double_counting(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    event = _event(1, kind="run_started")

    with observation_writer(database) as writer:
        first = persist_observation_batch(
            writer,
            database,
            (event,),
            disk_space_probe=_ample_disk_space,
        )
        second = persist_observation_batch(
            writer,
            database,
            (event,),
            disk_space_probe=_ample_disk_space,
        )

    assert first.persisted_events == 1
    assert second.persisted_events == 0
    assert second.duplicate_events == 1
    assert len(load_observation_events(database, RUN_ID)) == 1


def test_run_quota_drops_excess_without_rolling_back_prior_events(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    limits = replace(
        ObservationStorageLimits(),
        max_run_events=2,
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )
    events = (
        _event(1, kind="run_started"),
        _event(2),
        _event(3, kind="run_finished", status="completed"),
    )

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            events,
            limits=limits,
            disk_space_probe=lambda _: (1, 1),
        )

    assert result.persisted_events == 2
    assert result.dropped_events == 1
    assert result.failure_codes == ("observer_run_quota_full",)
    stored = load_observation_events(database, RUN_ID)
    assert [event.kind for event in stored] == ["run_started", "run_finished"]


def test_terminal_event_replaces_lower_priority_event_from_prior_batch(
    tmp_path: Path,
) -> None:
    database = initialize_observation_store(tmp_path / "state")
    limits = replace(
        ObservationStorageLimits(),
        max_run_events=2,
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )
    started = _event(1, kind="run_started")
    progress = replace(_event(2), priority="P2")
    terminal = _event(3, kind="run_finished", status="completed")

    with observation_writer(database) as writer:
        first = persist_observation_batch(
            writer,
            database,
            (started, progress),
            limits=limits,
            disk_space_probe=_ample_disk_space,
        )
        second = persist_observation_batch(
            writer,
            database,
            (terminal,),
            limits=limits,
            disk_space_probe=_ample_disk_space,
        )

    assert first.persisted_events == 2
    assert second.persisted_events == 1
    assert second.dropped_events == 1
    assert second.failure_codes == ("observer_run_quota_full",)
    assert load_observation_events(database, RUN_ID) == (started, terminal)


def test_writer_batch_has_hard_event_limit(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    events = tuple(_event(sequence) for sequence in range(1, 66))

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            events,
            disk_space_probe=_ample_disk_space,
        )

    assert result.persisted_events == 64
    assert result.dropped_events == 1
    assert result.failure_codes == ("observer_writer_batch_full",)
    assert len(load_observation_events(database, RUN_ID)) == 64


def test_physical_storage_guard_counts_database_and_wal(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    limits = replace(
        ObservationStorageLimits(),
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            (_event(1, kind="run_started"),),
            limits=limits,
            disk_space_probe=_ample_disk_space,
            storage_size_probe=lambda _: limits.max_database_bytes,
        )

    assert result.persisted_events == 0
    assert result.dropped_events == 1
    assert result.failure_codes == ("observer_storage_quota_full",)
    assert observation_storage_bytes(database) <= limits.max_database_bytes


def test_actual_database_and_wal_never_cross_small_physical_cap(
    tmp_path: Path,
) -> None:
    limits = replace(
        ObservationStorageLimits(),
        max_database_bytes=1024 * 1024,
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )
    database = initialize_observation_store(tmp_path / "state", limits=limits)
    quota_seen = False

    with observation_writer(database, limits=limits) as writer:
        for batch_index in range(100):
            first_sequence = batch_index * 64 + 1
            events = tuple(
                _event(sequence)
                for sequence in range(first_sequence, first_sequence + 64)
            )
            result = persist_observation_batch(
                writer,
                database,
                events,
                limits=limits,
                disk_space_probe=_ample_disk_space,
            )
            if "observer_storage_quota_full" in result.failure_codes:
                quota_seen = True
                break

    assert quota_seen
    assert observation_storage_bytes(database) <= limits.max_database_bytes


def test_storage_size_probe_failure_is_safe_and_bounded(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")

    def unavailable(_: Path) -> int:
        raise OSError("PRIVATE_STORAGE_PROBE_CANARY")

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            (_event(1, kind="run_started"),),
            disk_space_probe=_ample_disk_space,
            storage_size_probe=unavailable,
        )

    assert result.persisted_events == 0
    assert result.dropped_events == 1
    assert result.failure_codes == ("observer_storage_probe_failed",)
    assert "PRIVATE_STORAGE_PROBE_CANARY" not in str(result)


def test_database_quota_evicts_only_oldest_completed_runs(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    first = _completed_run(1)
    active = (
        _event(1, run_id=_run_id(2), kind="run_started"),
        _event(2, run_id=_run_id(2)),
    )
    one_run_bytes = sum(observation_event_bytes(event) for event in first)
    limits = replace(
        ObservationStorageLimits(),
        max_database_bytes=one_run_bytes + observation_event_bytes(active[0]) + 32,
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )

    with observation_writer(database) as writer:
        persist_observation_batch(
            writer,
            database,
            first,
            limits=limits,
            disk_space_probe=lambda _: (1, 1),
            storage_size_probe=lambda _: 0,
        )
        result = persist_observation_batch(
            writer,
            database,
            active,
            limits=limits,
            disk_space_probe=lambda _: (1, 1),
            storage_size_probe=lambda _: 0,
        )

    assert result.persisted_events >= 1
    assert load_observation_events(database, _run_id(1)) == ()
    assert load_observation_events(database, _run_id(2))


def test_database_quota_never_evicts_active_run(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    first = _event(1, kind="run_started")
    second = _event(2)
    limits = replace(
        ObservationStorageLimits(),
        max_database_bytes=observation_event_bytes(first) + 8,
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            (first, second),
            limits=limits,
            disk_space_probe=lambda _: (1, 1),
            storage_size_probe=lambda _: 0,
        )

    assert result.persisted_events == 1
    assert result.dropped_events == 1
    assert result.failure_codes == ("observer_storage_quota_full",)
    assert load_observation_events(database, RUN_ID) == (first,)


def test_retention_prunes_expired_and_excess_completed_runs(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    now = BASE_TIME + timedelta(days=90)
    limits = replace(
        ObservationStorageLimits(),
        max_completed_runs=2,
        completed_retention_days=30,
        minimum_free_bytes=0,
        minimum_free_ratio=0,
    )
    with observation_writer(database) as writer:
        persist_observation_batch(
            writer,
            database,
            _completed_run(1, completed_at=BASE_TIME),
            limits=limits,
            disk_space_probe=lambda _: (1, 1),
            now=now,
        )
        for index in (2, 3, 4):
            persist_observation_batch(
                writer,
                database,
                _completed_run(index, completed_at=now + timedelta(seconds=index)),
                limits=limits,
                disk_space_probe=lambda _: (1, 1),
                now=now,
            )

    assert {run.run_id for run in list_observation_runs(database)} == {
        _run_id(3),
        _run_id(4),
    }


def test_low_disk_water_drops_batch_without_touching_task_files(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    task_file = tmp_path / "task" / "final.docx"
    task_file.parent.mkdir()
    task_file.write_bytes(b"task-artifact")

    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            (_event(1, kind="run_started"),),
            disk_space_probe=lambda _: (10_000, 1),
        )

    assert result.persisted_events == 0
    assert result.dropped_events == 1
    assert result.failure_codes == ("observer_storage_low_space",)
    assert task_file.read_bytes() == b"task-artifact"


def test_delete_and_clear_remove_only_observer_rows(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    task_file = tmp_path / "task" / "conversion-report.json"
    task_file.parent.mkdir()
    task_file.write_text("task-report", encoding="utf-8")
    with observation_writer(database) as writer:
        persist_observation_batch(
            writer,
            database,
            _completed_run(1),
            disk_space_probe=_ample_disk_space,
        )
        persist_observation_batch(
            writer,
            database,
            _completed_run(2),
            disk_space_probe=_ample_disk_space,
        )

    assert delete_observation_run(database, _run_id(1)) is True
    assert delete_observation_run(database, _run_id(1)) is False
    assert clear_observation_history(database) == 1
    assert list_observation_runs(database) == ()
    assert task_file.read_text(encoding="utf-8") == "task-report"


def test_large_run_delete_is_batched_and_checkpointed(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    run_id = _run_id(10)
    events = (
        _event(1, run_id=run_id, kind="run_started"),
        *tuple(_event(sequence, run_id=run_id) for sequence in range(2, 40)),
        _event(40, run_id=run_id, kind="run_finished", status="completed"),
    )
    with observation_writer(database) as writer:
        result = persist_observation_batch(
            writer,
            database,
            events,
            disk_space_probe=_ample_disk_space,
        )

    assert result.persisted_events == 40
    assert delete_observation_run(database, run_id) is True
    assert load_observation_events(database, run_id) == ()
    assert observation_storage_bytes(database) <= ObservationStorageLimits().max_database_bytes


def test_corrupt_stored_payload_is_rejected_with_fixed_code(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    with observation_writer(database) as writer:
        persist_observation_batch(
            writer,
            database,
            (_event(1, kind="run_started"),),
            disk_space_probe=_ample_disk_space,
        )
        writer.execute(
            "UPDATE observation_events SET payload_json='PRIVATE_BODY_CANARY'"
        )

    with pytest.raises(ObservationStorageError) as failure:
        load_observation_events(database, RUN_ID)

    assert failure.value.code == "observer_event_payload_invalid"
    assert "PRIVATE_BODY_CANARY" not in str(failure.value)


def test_busy_writer_fails_within_bounded_timeout(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    with observation_writer(database) as first, observation_writer(database) as second:
        first.execute("BEGIN IMMEDIATE")
        started = time.perf_counter()
        with (
            pytest.raises(ObservationStorageError) as failure,
            immediate_transaction(second),
        ):
            raise AssertionError("locked transaction unexpectedly opened")
        elapsed = time.perf_counter() - started
        first.execute("ROLLBACK")

    assert failure.value.code == "observer_database_busy"
    assert elapsed < max(0.5, OBSERVATION_BUSY_TIMEOUT_MS / 1000 * 5)
