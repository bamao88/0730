from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from docfit.observability.storage import (
    OBSERVATION_BUSY_TIMEOUT_MS,
    OBSERVATION_DATABASE_NAME,
    ObservationStorageError,
    immediate_transaction,
    initialize_observation_store,
    observation_reader,
    observation_state_root,
    observation_writer,
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


def test_sqlite_schema_wal_and_query_only_reader(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")

    with observation_writer(database) as writer:
        assert writer.execute("PRAGMA user_version").fetchone() == (1,)
        assert writer.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert writer.execute(
            "SELECT value FROM observation_meta WHERE key='schema'"
        ).fetchone() == ("docfit_observation_v1",)

    with observation_reader(database) as reader:
        assert reader.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("CREATE TABLE forbidden(value TEXT)")


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
