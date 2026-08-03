"""Bounded private SQLite projection for sanitized observation events."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from docfit.observability.events import (
    ObservationActor,
    ObservationAttribute,
    ObservationError,
    ObservationEvent,
    ObservationEvidenceRef,
    validate_observation_event,
)

OBSERVATION_SCHEMA_VERSION = 2
OBSERVATION_BUSY_TIMEOUT_MS = 50
OBSERVATION_DATABASE_NAME = "observations.sqlite3"
OBSERVATION_WAL_RESERVE_BYTES = 16 * 1024 * 1024
OBSERVATION_BATCH_GROWTH_RESERVE_BYTES = 4 * 1024 * 1024
OBSERVATION_STORAGE_BATCH_MAX_EVENTS = 64
OBSERVATION_STORAGE_BATCH_MAX_BYTES = 1024 * 1024
OBSERVATION_DELETE_BATCH_EVENTS = 16


@dataclass(frozen=True, slots=True)
class ObservationStorageLimits:
    max_run_events: int = 10_000
    max_run_bytes: int = 64 * 1024 * 1024
    max_database_bytes: int = 512 * 1024 * 1024
    max_completed_runs: int = 500
    completed_retention_days: int = 30
    minimum_free_bytes: int = 1024 * 1024 * 1024
    minimum_free_ratio: float = 0.05


DEFAULT_STORAGE_LIMITS = ObservationStorageLimits()


@dataclass(frozen=True, slots=True)
class ObservationPersistResult:
    persisted_events: int
    duplicate_events: int
    dropped_events: int
    persisted_bytes: int
    last_observed_at: str | None
    failure_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoredObservationRun:
    run_id: str
    task_ref: str | None
    session_id: str | None
    status: str
    started_at: str | None
    completed_at: str | None
    last_observed_at: str | None
    event_count: int
    event_bytes: int


class ObservationStorageError(RuntimeError):
    """A privacy-safe, non-fatal observation storage failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


DiskSpaceProbe = Callable[[Path], tuple[int, int]]
StorageSizeProbe = Callable[[Path], int]


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


def _configure(
    connection: sqlite3.Connection,
    *,
    query_only: bool,
    limits: ObservationStorageLimits = DEFAULT_STORAGE_LIMITS,
) -> None:
    connection.execute(f"PRAGMA busy_timeout={OBSERVATION_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    if query_only:
        connection.execute("PRAGMA query_only=ON")
        return
    page_size_row = connection.execute("PRAGMA page_size").fetchone()
    page_size = int(page_size_row[0]) if page_size_row else 4096
    wal_reserve = min(
        OBSERVATION_WAL_RESERVE_BYTES,
        max(page_size, limits.max_database_bytes // 16),
    )
    main_database_budget = max(page_size, limits.max_database_bytes - wal_reserve)
    max_pages = max(1, main_database_budget // page_size)
    connection.execute(f"PRAGMA max_page_count={max_pages}")
    connection.execute("PRAGMA wal_autocheckpoint=64")
    journal_limit = min(8 * 1024 * 1024, max(page_size, wal_reserve // 2))
    connection.execute(f"PRAGMA journal_size_limit={journal_limit}")


def _normalize_database_error(error: BaseException) -> ObservationStorageError:
    message = str(error).casefold()
    if "locked" in message or "busy" in message:
        return ObservationStorageError("observer_database_busy")
    if "readonly" in message or "read-only" in message:
        return ObservationStorageError("observer_database_readonly")
    if "full" in message:
        return ObservationStorageError("observer_database_full")
    if "malformed" in message or "not a database" in message or "corrupt" in message:
        return ObservationStorageError("observer_database_corrupt")
    return ObservationStorageError("observer_database_write_failed")


def _connect_writer(
    database: Path,
    *,
    limits: ObservationStorageLimits = DEFAULT_STORAGE_LIMITS,
) -> sqlite3.Connection:
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
        _configure(connection, query_only=False, limits=limits)
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
        raise _normalize_database_error(error) from error


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
        raise _normalize_database_error(error) from error


def _create_v1(connection: sqlite3.Connection) -> None:
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
        connection.execute("PRAGMA user_version=1")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _validate_v1(connection: sqlite3.Connection) -> None:
    try:
        schema = connection.execute(
            "SELECT value FROM observation_meta WHERE key='schema'"
        ).fetchone()
    except sqlite3.DatabaseError as error:
        raise ObservationStorageError("observer_schema_invalid") from error
    if schema != ("docfit_observation_v1",):
        raise ObservationStorageError("observer_schema_invalid")


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    _validate_v1(connection)
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """
            CREATE TABLE observation_runs (
                run_id TEXT PRIMARY KEY,
                task_ref TEXT,
                session_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                started_at TEXT,
                completed_at TEXT,
                last_observed_at TEXT,
                event_count INTEGER NOT NULL DEFAULT 0 CHECK(event_count >= 0),
                event_bytes INTEGER NOT NULL DEFAULT 0 CHECK(event_bytes >= 0),
                created_at TEXT NOT NULL
            ) WITHOUT ROWID
            """
        )
        connection.execute(
            """
            CREATE TABLE observation_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES observation_runs(run_id) ON DELETE CASCADE,
                event_hash TEXT NOT NULL,
                source TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                priority TEXT NOT NULL,
                source_sequence INTEGER NOT NULL CHECK(source_sequence >= 0),
                observed_at TEXT NOT NULL,
                monotonic_offset_ms REAL NOT NULL CHECK(monotonic_offset_ms >= 0),
                session_id TEXT,
                tool_use_id TEXT,
                agent_id TEXT,
                parent_tool_use_id TEXT,
                event_bytes INTEGER NOT NULL CHECK(event_bytes > 0),
                payload_json TEXT NOT NULL,
                UNIQUE(run_id, event_hash)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX observation_events_run_sequence
            ON observation_events(run_id, source_sequence, event_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX observation_events_tool
            ON observation_events(run_id, tool_use_id)
            WHERE tool_use_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX observation_events_agent
            ON observation_events(run_id, agent_id)
            WHERE agent_id IS NOT NULL
            """
        )
        connection.execute(
            "CREATE INDEX observation_runs_completed ON observation_runs(status, completed_at)"
        )
        connection.execute(
            "UPDATE observation_meta SET value=? WHERE key='schema'",
            ("docfit_observation_v2",),
        )
        connection.execute("PRAGMA user_version=2")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _validate_v2(connection: sqlite3.Connection) -> None:
    try:
        schema = connection.execute(
            "SELECT value FROM observation_meta WHERE key='schema'"
        ).fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    except sqlite3.DatabaseError as error:
        raise ObservationStorageError("observer_schema_invalid") from error
    if schema != ("docfit_observation_v2",) or not {
        "observation_meta",
        "observation_runs",
        "observation_events",
    } <= tables:
        raise ObservationStorageError("observer_schema_invalid")


def _migrate(connection: sqlite3.Connection) -> None:
    try:
        row = connection.execute("PRAGMA user_version").fetchone()
        version = int(row[0]) if row else 0
        if version > OBSERVATION_SCHEMA_VERSION:
            raise ObservationStorageError("observer_schema_unsupported")
        if version == 0:
            _create_v1(connection)
            version = 1
        if version == 1:
            _migrate_v1_to_v2(connection)
            version = 2
        if version == 2:
            _validate_v2(connection)
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise _normalize_database_error(error) from error


def initialize_observation_store(
    state_root: Path,
    *,
    limits: ObservationStorageLimits = DEFAULT_STORAGE_LIMITS,
) -> Path:
    root = ensure_private_state_root(state_root)
    database = root / OBSERVATION_DATABASE_NAME
    connection = _connect_writer(database, limits=limits)
    try:
        _migrate(connection)
    finally:
        connection.close()
    return database


@contextmanager
def observation_writer(
    database: Path,
    *,
    limits: ObservationStorageLimits = DEFAULT_STORAGE_LIMITS,
) -> Iterator[sqlite3.Connection]:
    connection = _connect_writer(database, limits=limits)
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
        raise _normalize_database_error(error) from error
    try:
        yield
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _event_payload(event: ObservationEvent) -> str:
    return json.dumps(
        asdict(event),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _event_from_payload(payload_json: str) -> ObservationEvent:
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise TypeError
        actor_payload = cast(dict[str, Any], payload["actor"])
        attributes_payload = cast(list[dict[str, Any]], payload["attributes"])
        evidence_payload = cast(list[dict[str, Any]], payload["evidence_refs"])
        error_payload = payload.get("error")
        attributes = tuple(
            ObservationAttribute(
                item["key"],
                tuple(item["value"])
                if isinstance(item.get("value"), list)
                else item.get("value"),
            )
            for item in attributes_payload
        )
        evidence = tuple(
            ObservationEvidenceRef(
                item["kind"],
                item["value"],
                item.get("document_sha256"),
                item.get("render_sha256"),
            )
            for item in evidence_payload
        )
        error = (
            ObservationError(
                error_payload["code"],
                error_payload["origin"],
                error_payload.get("retryable"),
                error_payload.get("interrupt"),
            )
            if isinstance(error_payload, dict)
            else None
        )
        event = ObservationEvent(
            schema_version=payload["schema_version"],
            run_id=payload["run_id"],
            source_event_id=payload["source_event_id"],
            source_sequence=payload["source_sequence"],
            observed_at=payload["observed_at"],
            monotonic_offset_ms=payload["monotonic_offset_ms"],
            source=payload["source"],
            kind=payload["kind"],
            priority=payload["priority"],
            actor=ObservationActor(
                actor_payload["role"],
                actor_payload.get("agent_id"),
                actor_payload.get("agent_type"),
            ),
            summary_code=payload["summary_code"],
            status=payload.get("status"),
            session_id=payload.get("session_id"),
            tool_name=payload.get("tool_name"),
            tool_use_id=payload.get("tool_use_id"),
            agent_id=payload.get("agent_id"),
            agent_type=payload.get("agent_type"),
            parent_tool_use_id=payload.get("parent_tool_use_id"),
            duration_ms=payload.get("duration_ms"),
            attributes=attributes,
            evidence_refs=evidence,
            error=error,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ObservationStorageError("observer_event_payload_invalid") from error
    if validate_observation_event(event) is not None:
        raise ObservationStorageError("observer_event_payload_invalid")
    return event


def _attribute(event: ObservationEvent, key: str) -> object:
    for attribute in event.attributes:
        if attribute.key == key:
            return attribute.value
    return None


def _ensure_run(connection: sqlite3.Connection, event: ObservationEvent) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO observation_runs(
            run_id, status, started_at, last_observed_at, created_at
        ) VALUES (?, 'active', ?, ?, ?)
        """,
        (event.run_id, event.observed_at, event.observed_at, event.observed_at),
    )


def _update_run_after_insert(
    connection: sqlite3.Connection,
    event: ObservationEvent,
    event_bytes: int,
) -> None:
    task_ref = _attribute(event, "task_ref")
    task_ref_value = task_ref if isinstance(task_ref, str) else None
    status: str | None = None
    completed_at: str | None = None
    started_at: str | None = None
    if event.kind == "run_started":
        status = "active"
        started_at = event.observed_at
    elif event.kind in {"run_finished", "conversion_report"}:
        status = event.status or "unknown"
        completed_at = event.observed_at
    connection.execute(
        """
        UPDATE observation_runs
        SET task_ref=COALESCE(?, task_ref),
            session_id=COALESCE(?, session_id),
            status=COALESCE(?, status),
            started_at=COALESCE(?, started_at),
            completed_at=COALESCE(?, completed_at),
            last_observed_at=?,
            event_count=event_count + 1,
            event_bytes=event_bytes + ?
        WHERE run_id=?
        """,
        (
            task_ref_value,
            event.session_id,
            status,
            started_at,
            completed_at,
            event.observed_at,
            event_bytes,
            event.run_id,
        ),
    )


def _evict_lower_priority_for_run(
    connection: sqlite3.Connection,
    event: ObservationEvent,
    *,
    required_bytes: int,
    limits: ObservationStorageLimits,
    run_count: int,
    run_bytes: int,
) -> tuple[int, int, int, int]:
    lower_priorities: tuple[str, ...]
    if event.priority == "P0":
        lower_priorities = ("P2", "P1")
    elif event.priority == "P1":
        lower_priorities = ("P2",)
    else:
        lower_priorities = ()
    if not lower_priorities:
        return run_count, run_bytes, 0, 0
    placeholders = ",".join("?" for _ in lower_priorities)
    rows = connection.execute(
        f"""
        SELECT event_id, event_bytes FROM observation_events
        WHERE run_id=? AND priority IN ({placeholders})
        ORDER BY CASE priority WHEN 'P2' THEN 0 ELSE 1 END, event_id ASC
        """,
        (event.run_id, *lower_priorities),
    ).fetchall()
    removed_events = 0
    removed_bytes = 0
    for event_id, event_bytes in rows:
        if run_count < limits.max_run_events and (
            run_bytes + required_bytes <= limits.max_run_bytes
        ):
            break
        connection.execute(
            "DELETE FROM observation_events WHERE event_id=?",
            (event_id,),
        )
        run_count -= 1
        run_bytes -= int(event_bytes)
        removed_events += 1
        removed_bytes += int(event_bytes)
    if removed_events:
        connection.execute(
            """
            UPDATE observation_runs
            SET event_count=event_count - ?, event_bytes=event_bytes - ?
            WHERE run_id=?
            """,
            (removed_events, removed_bytes, event.run_id),
        )
    return run_count, run_bytes, removed_events, removed_bytes


def _delete_run_bounded(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    allow_active: bool = False,
) -> bool:
    status_row = connection.execute(
        "SELECT status FROM observation_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if status_row is None or (status_row[0] == "active" and not allow_active):
        return False
    while True:
        removed = 0
        removed_bytes = 0
        deleted_run = False
        with immediate_transaction(connection):
            rows = connection.execute(
                """
                SELECT event_id, event_bytes FROM observation_events
                WHERE run_id=? ORDER BY event_id LIMIT ?
                """,
                (run_id, OBSERVATION_DELETE_BATCH_EVENTS),
            ).fetchall()
            if rows:
                connection.executemany(
                    "DELETE FROM observation_events WHERE event_id=?",
                    ((row[0],) for row in rows),
                )
                removed = len(rows)
                removed_bytes = sum(int(row[1]) for row in rows)
                connection.execute(
                    """
                    UPDATE observation_runs
                    SET event_count=event_count - ?, event_bytes=event_bytes - ?
                    WHERE run_id=?
                    """,
                    (removed, removed_bytes, run_id),
                )
            else:
                condition = "run_id=?" if allow_active else "run_id=? AND status != 'active'"
                cursor = connection.execute(
                    f"DELETE FROM observation_runs WHERE {condition}",
                    (run_id,),
                )
                deleted_run = cursor.rowcount == 1
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        if deleted_run:
            return True
        if removed == 0:
            return False


def _apply_retention(
    connection: sqlite3.Connection,
    limits: ObservationStorageLimits,
    *,
    now: datetime,
) -> int:
    cutoff = (now - timedelta(days=limits.completed_retention_days)).isoformat()
    expired = [
        row[0]
        for row in connection.execute(
            """
            SELECT run_id FROM observation_runs
            WHERE status != 'active' AND completed_at IS NOT NULL AND completed_at < ?
            ORDER BY completed_at ASC
            """,
            (cutoff,),
        ).fetchall()
    ]
    removed = sum(_delete_run_bounded(connection, run_id) for run_id in expired)
    excess = [
        row[0]
        for row in connection.execute(
            """
            SELECT run_id FROM observation_runs
            WHERE status != 'active'
            ORDER BY completed_at DESC, run_id DESC
            LIMIT -1 OFFSET ?
            """,
            (limits.max_completed_runs,),
        ).fetchall()
    ]
    removed += sum(_delete_run_bounded(connection, run_id) for run_id in excess)
    return removed


def _logical_event_bytes(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(SUM(event_bytes), 0) FROM observation_runs"
    ).fetchone()
    return int(row[0]) if row else 0


def _prune_for_bytes(
    connection: sqlite3.Connection,
    limits: ObservationStorageLimits,
    *,
    required_bytes: int,
    current_run_ids: set[str],
) -> int:
    total = _logical_event_bytes(connection)
    if total + required_bytes <= limits.max_database_bytes:
        return total
    rows = connection.execute(
        """
        SELECT run_id, event_bytes FROM observation_runs
        WHERE status != 'active'
        ORDER BY completed_at ASC, run_id ASC
        """
    ).fetchall()
    for run_id, event_bytes in rows:
        if run_id in current_run_ids:
            continue
        if _delete_run_bounded(connection, run_id):
            total -= int(event_bytes)
        if total + required_bytes <= limits.max_database_bytes:
            break
    return total


def _default_disk_space(path: Path) -> tuple[int, int]:
    usage = shutil.disk_usage(path)
    return usage.total, usage.free


def observation_storage_bytes(database: Path) -> int:
    """Return bytes owned by the SQLite database and its WAL projection."""

    total = 0
    for candidate in (database, Path(f"{database}-wal")):
        try:
            total += candidate.stat().st_size
        except FileNotFoundError:
            continue
    return total


def _default_storage_size(database: Path) -> int:
    return observation_storage_bytes(database)


def _disk_low(
    database: Path,
    limits: ObservationStorageLimits,
    probe: DiskSpaceProbe,
) -> bool:
    try:
        total, free = probe(database.parent)
    except OSError:
        return True
    low_water = max(
        limits.minimum_free_bytes,
        int(total * limits.minimum_free_ratio),
    )
    return free < low_water


def _physical_capacity_available(
    connection: sqlite3.Connection,
    database: Path,
    limits: ObservationStorageLimits,
    probe: StorageSizeProbe,
) -> bool:
    physical_bytes = probe(database)
    page_size_row = connection.execute("PRAGMA page_size").fetchone()
    freelist_row = connection.execute("PRAGMA freelist_count").fetchone()
    page_count_row = connection.execute("PRAGMA page_count").fetchone()
    page_size = int(page_size_row[0]) if page_size_row else 4096
    freelist_pages = int(freelist_row[0]) if freelist_row else 0
    page_count = int(page_count_row[0]) if page_count_row else 0
    reusable_bytes = freelist_pages * page_size
    effective_bytes = max(0, physical_bytes - reusable_bytes)
    growth_reserve = min(
        OBSERVATION_BATCH_GROWTH_RESERVE_BYTES,
        max(1, limits.max_database_bytes // 16),
    )
    wal_reserve = min(
        OBSERVATION_WAL_RESERVE_BYTES,
        max(page_size, limits.max_database_bytes // 16),
    )
    main_database_budget = max(page_size, limits.max_database_bytes - wal_reserve)
    main_file_bytes = min(physical_bytes, page_count * page_size)
    effective_main_bytes = max(0, main_file_bytes - reusable_bytes)
    return (
        effective_bytes + growth_reserve <= limits.max_database_bytes
        and effective_main_bytes + growth_reserve <= main_database_budget
    )


def _ensure_physical_capacity(
    connection: sqlite3.Connection,
    database: Path,
    limits: ObservationStorageLimits,
    probe: StorageSizeProbe,
    *,
    current_run_ids: set[str],
) -> bool:
    if _physical_capacity_available(connection, database, limits, probe):
        return True
    connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    if _physical_capacity_available(connection, database, limits, probe):
        return True
    completed = [
        row[0]
        for row in connection.execute(
            """
            SELECT run_id FROM observation_runs
            WHERE status != 'active'
            ORDER BY completed_at ASC, run_id ASC
            """
        ).fetchall()
        if row[0] not in current_run_ids
    ]
    for run_id in completed:
        _delete_run_bounded(connection, run_id)
        if _physical_capacity_available(connection, database, limits, probe):
            return True
    return False


def persist_observation_batch(
    connection: sqlite3.Connection,
    database: Path,
    events: Sequence[ObservationEvent],
    *,
    limits: ObservationStorageLimits = DEFAULT_STORAGE_LIMITS,
    disk_space_probe: DiskSpaceProbe = _default_disk_space,
    storage_size_probe: StorageSizeProbe = _default_storage_size,
    now: datetime | None = None,
) -> ObservationPersistResult:
    """Persist one bounded batch; quota failures drop only observer events."""

    if not events:
        return ObservationPersistResult(0, 0, 0, 0, None, ())
    if _disk_low(database, limits, disk_space_probe):
        return ObservationPersistResult(
            0,
            0,
            len(events),
            0,
            None,
            ("observer_storage_low_space",),
        )
    prepared: list[tuple[ObservationEvent, str, int, str]] = []
    prepared_bytes = 0
    invalid = 0
    batch_overflow = 0
    for event in events:
        if validate_observation_event(event) is not None:
            invalid += 1
            continue
        payload = _event_payload(event)
        payload_bytes = len(payload.encode("utf-8"))
        if (
            len(prepared) >= OBSERVATION_STORAGE_BATCH_MAX_EVENTS
            or prepared_bytes + payload_bytes > OBSERVATION_STORAGE_BATCH_MAX_BYTES
        ):
            batch_overflow += 1
            continue
        event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        prepared.append((event, payload, payload_bytes, event_hash))
        prepared_bytes += payload_bytes
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    prepared.sort(key=lambda item: priority_order[item[0].priority])
    current_run_ids = {item[0].run_id for item in prepared}
    persisted = 0
    duplicates = 0
    dropped = invalid + batch_overflow
    persisted_bytes = 0
    last_observed_at: str | None = None
    failures: set[str] = set()
    if invalid:
        failures.add("observer_event_payload_invalid")
    if batch_overflow:
        failures.add("observer_writer_batch_full")
    current_time = now or datetime.now(UTC)
    try:
        _apply_retention(connection, limits, now=current_time)
        total_bytes = _prune_for_bytes(
            connection,
            limits,
            required_bytes=prepared_bytes,
            current_run_ids=current_run_ids,
        )
        physical_capacity = _ensure_physical_capacity(
            connection,
            database,
            limits,
            storage_size_probe,
            current_run_ids=current_run_ids,
        )
    except (OSError, sqlite3.DatabaseError):
        return ObservationPersistResult(
            0,
            0,
            len(events),
            0,
            None,
            tuple(sorted({*failures, "observer_storage_probe_failed"})),
        )
    if not physical_capacity:
        return ObservationPersistResult(
            0,
            0,
            len(events),
            0,
            None,
            tuple(sorted({*failures, "observer_storage_quota_full"})),
        )
    try:
        with immediate_transaction(connection):
            for event, payload, payload_bytes, event_hash in prepared:
                _ensure_run(connection, event)
                existing = connection.execute(
                    "SELECT 1 FROM observation_events WHERE run_id=? AND event_hash=?",
                    (event.run_id, event_hash),
                ).fetchone()
                if existing is not None:
                    duplicates += 1
                    continue
                run_row = connection.execute(
                    "SELECT event_count, event_bytes FROM observation_runs WHERE run_id=?",
                    (event.run_id,),
                ).fetchone()
                run_count = int(run_row[0]) if run_row else 0
                run_bytes = int(run_row[1]) if run_row else 0
                if (
                    run_count >= limits.max_run_events
                    or run_bytes + payload_bytes > limits.max_run_bytes
                ):
                    (
                        run_count,
                        run_bytes,
                        evicted_events,
                        evicted_bytes,
                    ) = _evict_lower_priority_for_run(
                        connection,
                        event,
                        required_bytes=payload_bytes,
                        limits=limits,
                        run_count=run_count,
                        run_bytes=run_bytes,
                    )
                    if evicted_events:
                        dropped += evicted_events
                        total_bytes -= evicted_bytes
                        failures.add("observer_run_quota_full")
                if (
                    run_count >= limits.max_run_events
                    or run_bytes + payload_bytes > limits.max_run_bytes
                ):
                    dropped += 1
                    failures.add("observer_run_quota_full")
                    continue
                if total_bytes + payload_bytes > limits.max_database_bytes:
                    dropped += 1
                    failures.add("observer_storage_quota_full")
                    continue
                cursor = connection.execute(
                    """
                    INSERT INTO observation_events(
                        run_id, event_hash, source, source_event_id, kind, priority,
                        source_sequence, observed_at, monotonic_offset_ms, session_id,
                        tool_use_id, agent_id, parent_tool_use_id, event_bytes, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.run_id,
                        event_hash,
                        event.source,
                        event.source_event_id,
                        event.kind,
                        event.priority,
                        event.source_sequence,
                        event.observed_at,
                        event.monotonic_offset_ms,
                        event.session_id,
                        event.tool_use_id,
                        event.agent_id,
                        event.parent_tool_use_id,
                        payload_bytes,
                        payload,
                    ),
                )
                if cursor.rowcount != 1:
                    duplicates += 1
                    continue
                _update_run_after_insert(connection, event, payload_bytes)
                persisted += 1
                persisted_bytes += payload_bytes
                total_bytes += payload_bytes
                last_observed_at = event.observed_at
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        _apply_retention(connection, limits, now=current_time)
    except ObservationStorageError:
        raise
    except (OSError, sqlite3.DatabaseError) as error:
        raise _normalize_database_error(error) from error
    return ObservationPersistResult(
        persisted,
        duplicates,
        dropped,
        persisted_bytes,
        last_observed_at,
        tuple(sorted(failures)),
    )


def list_observation_runs(
    database: Path,
    *,
    limit: int = 100,
) -> tuple[StoredObservationRun, ...]:
    if limit < 1 or limit > 500:
        raise ObservationStorageError("observer_query_limit_invalid")
    try:
        with observation_reader(database) as connection:
            rows = connection.execute(
                """
                SELECT run_id, task_ref, session_id, status, started_at, completed_at,
                       last_observed_at, event_count, event_bytes
                FROM observation_runs
                ORDER BY COALESCE(completed_at, last_observed_at, created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise _normalize_database_error(error) from error
    return tuple(StoredObservationRun(*row) for row in rows)


def load_observation_events(
    database: Path,
    run_id: str,
) -> tuple[ObservationEvent, ...]:
    try:
        with observation_reader(database) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM observation_events
                WHERE run_id=?
                ORDER BY source_sequence ASC, event_id ASC
                """,
                (run_id,),
            ).fetchall()
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise _normalize_database_error(error) from error
    return tuple(_event_from_payload(row[0]) for row in rows)


def delete_observation_run(database: Path, run_id: str) -> bool:
    try:
        with observation_writer(database) as connection:
            return _delete_run_bounded(connection, run_id, allow_active=True)
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise _normalize_database_error(error) from error


def clear_observation_history(database: Path) -> int:
    try:
        with observation_writer(database) as connection:
            run_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM observation_runs"
                ).fetchall()
            ]
            return sum(
                _delete_run_bounded(connection, run_id, allow_active=True)
                for run_id in run_ids
            )
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise _normalize_database_error(error) from error


def checkpoint_observation_store(database: Path) -> None:
    try:
        with observation_writer(database) as connection:
            connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    except ObservationStorageError:
        raise
    except sqlite3.DatabaseError as error:
        raise _normalize_database_error(error) from error
