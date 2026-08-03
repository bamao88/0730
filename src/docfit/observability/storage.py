"""Private SQLite bootstrap for the local observation index."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

OBSERVATION_SCHEMA_VERSION = 1
OBSERVATION_BUSY_TIMEOUT_MS = 50
OBSERVATION_DATABASE_NAME = "observations.sqlite3"


class ObservationStorageError(RuntimeError):
    """A privacy-safe, non-fatal observation storage failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def observation_state_root(
    *,
    environment: Mapping[str, str] | None = None,
    task_root: Path | None = None,
    repository_root: Path | None = None,
) -> Path:
    """Resolve a repository- and task-external application state directory."""

    values = os.environ if environment is None else environment
    state_home = values.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    candidate = (base / "docfit" / "observability").resolve(strict=False)
    for forbidden in (task_root, repository_root):
        if forbidden is None:
            continue
        resolved_forbidden = forbidden.expanduser().resolve(strict=False)
        if _within(candidate, resolved_forbidden):
            raise ObservationStorageError("observer_state_not_external")
    return candidate


def ensure_private_state_root(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    if resolved.exists() and resolved.is_symlink():
        raise ObservationStorageError("observer_state_symlink")
    try:
        resolved.mkdir(parents=True, mode=0o700, exist_ok=True)
        resolved.chmod(0o700)
    except OSError as error:
        raise ObservationStorageError("observer_state_unavailable") from error
    if not resolved.is_dir():
        raise ObservationStorageError("observer_state_unavailable")
    return resolved


def _configure(connection: sqlite3.Connection, *, query_only: bool) -> None:
    connection.execute(f"PRAGMA busy_timeout={OBSERVATION_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    if query_only:
        connection.execute("PRAGMA query_only=ON")


def _connect_writer(database: Path) -> sqlite3.Connection:
    if database.exists() and database.is_symlink():
        raise ObservationStorageError("observer_database_symlink")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            database,
            timeout=OBSERVATION_BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        database.chmod(0o600)
        _configure(connection, query_only=False)
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).casefold() != "wal":
            raise ObservationStorageError("observer_wal_unavailable")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection
    except ObservationStorageError:
        if connection is not None:
            connection.close()
        raise
    except (OSError, sqlite3.DatabaseError) as error:
        if connection is not None:
            connection.close()
        raise ObservationStorageError("observer_database_unavailable") from error


def _connect_reader(database: Path) -> sqlite3.Connection:
    if not database.is_file() or database.is_symlink():
        raise ObservationStorageError("observer_database_unavailable")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            database.as_uri() + "?mode=ro",
            uri=True,
            timeout=OBSERVATION_BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        _configure(connection, query_only=True)
        return connection
    except sqlite3.DatabaseError as error:
        if connection is not None:
            connection.close()
        raise ObservationStorageError("observer_database_unavailable") from error


def _migrate(connection: sqlite3.Connection) -> None:
    try:
        row = connection.execute("PRAGMA user_version").fetchone()
        version = int(row[0]) if row else 0
        if version > OBSERVATION_SCHEMA_VERSION:
            raise ObservationStorageError("observer_schema_unsupported")
        if version == 0:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE observation_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    ) WITHOUT ROWID
                    """
                )
                connection.execute(
                    "INSERT INTO observation_meta(key, value) VALUES (?, ?)",
                    ("schema", "docfit_observation_v1"),
                )
                connection.execute(f"PRAGMA user_version={OBSERVATION_SCHEMA_VERSION}")
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        elif version == OBSERVATION_SCHEMA_VERSION:
            try:
                schema = connection.execute(
                    "SELECT value FROM observation_meta WHERE key='schema'"
                ).fetchone()
            except sqlite3.DatabaseError as error:
                raise ObservationStorageError("observer_schema_invalid") from error
            if schema != ("docfit_observation_v1",):
                raise ObservationStorageError("observer_schema_invalid")
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise ObservationStorageError("observer_schema_migration_failed") from error


def initialize_observation_store(state_root: Path) -> Path:
    root = ensure_private_state_root(state_root)
    database = root / OBSERVATION_DATABASE_NAME
    connection = _connect_writer(database)
    try:
        _migrate(connection)
    finally:
        connection.close()
    return database


@contextmanager
def observation_writer(database: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect_writer(database)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def observation_reader(database: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect_reader(database)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Open a bounded writer transaction and normalize lock failures."""

    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as error:
        raise ObservationStorageError("observer_database_busy") from error
    try:
        yield
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
