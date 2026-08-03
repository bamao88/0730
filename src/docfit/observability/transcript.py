"""Private lifecycle for Claude Agent SDK session transcripts.

The SDK owns the transcript format.  DocFit only gives each SDK attempt an
isolated configuration directory and removes that directory without reading
its contents.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from docfit.observability.models import (
    SDKTranscriptAgeBucket,
    SDKTranscriptStatus,
    SDKTranscriptSummary,
    sdk_transcript_summary_is_valid,
)

_ATTEMPT_PREFIX = "attempt-"
_OWNER_MARKER = ".owner.json"
_ACTIVE_LOCK = ".active.lock"
_UNCERTAIN_RETENTION_SECONDS = 24 * 60 * 60
_MAX_OWNER_MARKER_BYTES = 4096


class SDKTranscriptRuntimeError(RuntimeError):
    """Safe transcript-isolation failure with no filesystem detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SDKTranscriptSummaryProvider(Protocol):
    def summary(self) -> SDKTranscriptSummary: ...


@dataclass(frozen=True, slots=True)
class _AttemptState:
    path: Path
    lock_fd: int


def default_transcript_parent(
    *, environment: Mapping[str, str] | None = None
) -> Path:
    """Return DocFit's single private runtime root without scanning elsewhere."""

    env = os.environ if environment is None else environment
    runtime_root = env.get("XDG_RUNTIME_DIR")
    if runtime_root:
        return Path(runtime_root) / "docfit" / "sdk-transcripts"
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return Path(tempfile.gettempdir()) / f"docfit-sdk-transcripts-{uid}"


def isolated_sdk_environment(
    environment: Mapping[str, str], config_directory: Path
) -> dict[str, str]:
    """Override any inherited SDK config location for exactly one attempt."""

    isolated = dict(environment)
    isolated["CLAUDE_CONFIG_DIR"] = str(config_directory)
    return isolated


class SDKTranscriptManager:
    """Create, isolate, and delete SDK-owned config directories per attempt."""

    def __init__(
        self,
        *,
        parent: Path | None = None,
        environment: Mapping[str, str] | None = None,
        forbidden_roots: tuple[Path, ...] = (),
        now: Callable[[], float] | None = None,
    ) -> None:
        self._parent = parent or default_transcript_parent(environment=environment)
        self._forbidden_roots = forbidden_roots
        self._now = now or time.time
        self._active_attempts = 0
        self._attempted = False
        self._cleanup_failed = False
        self._failure_codes: set[str] = set()
        self._setup_error: str | None = None
        try:
            self._ensure_private_parent()
            self.preflight()
        except SDKTranscriptRuntimeError as error:
            self._setup_error = error.code
            self._failure_codes.add(error.code)
        except Exception:
            self._setup_error = "sdk_transcript_setup_failed"
            self._failure_codes.add(self._setup_error)

    @property
    def parent(self) -> Path:
        """Internal composition path; callers must never persist or log it."""

        return self._parent

    def _ensure_private_parent(self) -> None:
        try:
            if self._parent.is_symlink():
                raise SDKTranscriptRuntimeError("sdk_transcript_parent_unsafe")
            resolved_parent = self._parent.expanduser().resolve(strict=False)
            resolved_forbidden = tuple(
                root.expanduser().resolve(strict=False) for root in self._forbidden_roots
            )
        except OSError as error:
            raise SDKTranscriptRuntimeError("sdk_transcript_parent_unavailable") from error
        if any(
            resolved_parent == root or root in resolved_parent.parents
            for root in resolved_forbidden
        ):
            raise SDKTranscriptRuntimeError("sdk_transcript_parent_forbidden")
        self._parent = resolved_parent
        try:
            self._parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            metadata = self._parent.lstat()
        except OSError as error:
            raise SDKTranscriptRuntimeError("sdk_transcript_parent_unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SDKTranscriptRuntimeError("sdk_transcript_parent_unsafe")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise SDKTranscriptRuntimeError("sdk_transcript_parent_owner_mismatch")
        try:
            self._parent.chmod(0o700)
        except OSError as error:
            raise SDKTranscriptRuntimeError("sdk_transcript_parent_permissions_failed") from error

    def _write_owner_marker(self, attempt: Path, nonce: str) -> None:
        marker = attempt / _OWNER_MARKER
        payload = {
            "schema_version": 1,
            "owner_pid": os.getpid(),
            "created_at_epoch": int(self._now()),
            "nonce": nonce,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(marker, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, separators=(",", ":"), sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise SDKTranscriptRuntimeError("sdk_transcript_owner_marker_failed") from error

    def _create_attempt(self) -> _AttemptState:
        if self._setup_error is not None:
            raise SDKTranscriptRuntimeError(self._setup_error)
        nonce = secrets.token_hex(16)
        attempt = self._parent / f"{_ATTEMPT_PREFIX}{nonce}"
        lock_fd: int | None = None
        try:
            attempt.mkdir(mode=0o700)
            attempt.chmod(0o700)
            self._write_owner_marker(attempt, nonce)
            lock_path = attempt / _ACTIVE_LOCK
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            lock_fd = os.open(lock_path, flags, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception as error:
            if lock_fd is not None:
                os.close(lock_fd)
            try:
                shutil.rmtree(attempt)
            except OSError:
                self._failure_codes.add("sdk_transcript_partial_setup_residual")
            if isinstance(error, SDKTranscriptRuntimeError):
                raise
            raise SDKTranscriptRuntimeError("sdk_transcript_attempt_setup_failed") from error
        if lock_fd is None:  # pragma: no cover - guarded by the setup operations above
            raise SDKTranscriptRuntimeError("sdk_transcript_attempt_setup_failed")
        return _AttemptState(path=attempt, lock_fd=lock_fd)

    @contextmanager
    def attempt(self) -> Iterator[Path]:
        """Yield an isolated ``CLAUDE_CONFIG_DIR`` and delete it on disconnect."""

        state = self._create_attempt()
        self._attempted = True
        self._active_attempts += 1
        try:
            yield state.path
        finally:
            self._active_attempts -= 1
            try:
                shutil.rmtree(state.path)
            except OSError:
                self._cleanup_failed = True
                self._failure_codes.add("sdk_transcript_cleanup_failed")
            finally:
                try:
                    fcntl.flock(state.lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(state.lock_fd)

    def _owner_pid(self, path: Path) -> int | None:
        try:
            metadata = path.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return None
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            return None
        marker = path / _OWNER_MARKER
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(marker, flags)
            marker_metadata = os.fstat(descriptor)
            if not stat.S_ISREG(marker_metadata.st_mode):
                return None
            if marker_metadata.st_size > _MAX_OWNER_MARKER_BYTES:
                return None
            if hasattr(os, "getuid") and marker_metadata.st_uid != os.getuid():
                return None
            raw = os.read(descriptor, _MAX_OWNER_MARKER_BYTES + 1)
            if len(raw) > _MAX_OWNER_MARKER_BYTES:
                return None
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        finally:
            if descriptor is not None:
                os.close(descriptor)
        owner_pid = payload.get("owner_pid") if isinstance(payload, dict) else None
        valid = bool(
            isinstance(payload, dict)
            and isinstance(payload.get("schema_version"), int)
            and not isinstance(payload.get("schema_version"), bool)
            and payload["schema_version"] == 1
            and isinstance(owner_pid, int)
            and not isinstance(owner_pid, bool)
            and owner_pid > 0
            and isinstance(payload.get("created_at_epoch"), int)
            and not isinstance(payload.get("created_at_epoch"), bool)
            and isinstance(payload.get("nonce"), str)
            and path.name == f"{_ATTEMPT_PREFIX}{payload['nonce']}"
        )
        return owner_pid if valid and isinstance(owner_pid, int) else None

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _path_owner_is_current_user(self, path: Path) -> bool:
        try:
            metadata = path.lstat()
        except OSError:
            return False
        return not hasattr(os, "getuid") or metadata.st_uid == os.getuid()

    def _try_lock(self, path: Path) -> tuple[Literal["active", "dead", "uncertain"], int | None]:
        lock_path = path / _ACTIVE_LOCK
        flags = os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags)
        except OSError:
            return "uncertain", None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                os.close(descriptor)
                return "uncertain", None
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(descriptor)
                return "active", None
            return "dead", descriptor
        except Exception:
            os.close(descriptor)
            return "uncertain", None

    def _old_enough(self, path: Path) -> bool:
        try:
            age = self._now() - path.lstat().st_mtime
        except OSError:
            return False
        return age >= _UNCERTAIN_RETENTION_SECONDS

    def preflight(self) -> None:
        """Remove only dead DocFit-owned attempts from the fixed private parent."""

        if self._setup_error is not None:
            raise SDKTranscriptRuntimeError(self._setup_error)
        try:
            candidates = tuple(self._parent.iterdir())
        except OSError as error:
            raise SDKTranscriptRuntimeError("sdk_transcript_preflight_failed") from error
        for candidate in candidates:
            if not candidate.name.startswith(_ATTEMPT_PREFIX):
                continue
            try:
                metadata = candidate.lstat()
            except OSError:
                self._failure_codes.add("sdk_transcript_residual_unreadable")
                continue
            if stat.S_ISLNK(metadata.st_mode):
                self._failure_codes.add("sdk_transcript_residual_symlink")
                continue
            owner_pid = self._owner_pid(candidate)
            owned = owner_pid is not None
            state, descriptor = self._try_lock(candidate)
            remove = owned and state == "dead"
            if (
                owned
                and state == "uncertain"
                and owner_pid is not None
                and not self._pid_is_alive(owner_pid)
            ):
                remove = True
            if (
                self._path_owner_is_current_user(candidate)
                and state != "active"
                and self._old_enough(candidate)
            ):
                remove = True
            if remove:
                try:
                    shutil.rmtree(candidate)
                except OSError:
                    self._failure_codes.add("sdk_transcript_residual_cleanup_failed")
                finally:
                    if descriptor is not None:
                        try:
                            fcntl.flock(descriptor, fcntl.LOCK_UN)
                        finally:
                            os.close(descriptor)
            elif descriptor is not None:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)

    def _residual_metadata(self) -> tuple[int | None, SDKTranscriptAgeBucket | None]:
        try:
            candidates = [
                item
                for item in self._parent.iterdir()
                if item.name.startswith(_ATTEMPT_PREFIX) and not item.is_symlink()
            ]
        except OSError:
            self._failure_codes.add("sdk_transcript_summary_failed")
            return None, None
        ages: list[float] = []
        for candidate in candidates:
            try:
                ages.append(max(0.0, self._now() - candidate.lstat().st_mtime))
            except OSError:
                continue
        if not candidates:
            return 0, None
        oldest = max(ages, default=0.0)
        if oldest < 60 * 60:
            bucket: SDKTranscriptAgeBucket = "under_1h"
        elif oldest < 24 * 60 * 60:
            bucket = "1h_to_24h"
        elif oldest < 7 * 24 * 60 * 60:
            bucket = "1d_to_7d"
        else:
            bucket = "over_7d"
        return len(candidates), bucket

    def summary(self) -> SDKTranscriptSummary:
        """Return fixed-shape metadata without paths or transcript payloads."""

        if self._setup_error is not None:
            return SDKTranscriptSummary(
                status="unknown",
                residual_count=None,
                oldest_age_bucket=None,
                failure_codes=tuple(sorted(self._failure_codes)),
            )
        residual_count, oldest_age = self._residual_metadata()
        if self._active_attempts:
            status: SDKTranscriptStatus = "active"
        elif self._cleanup_failed:
            status = "cleanup_failed"
        elif residual_count:
            status = "residual"
        elif self._attempted:
            status = "cleaned"
        else:
            status = "unknown"
        return SDKTranscriptSummary(
            status=status,
            residual_count=residual_count,
            oldest_age_bucket=oldest_age,
            failure_codes=tuple(sorted(self._failure_codes)),
        )


def transcript_summary_safely(manager: SDKTranscriptSummaryProvider) -> SDKTranscriptSummary:
    try:
        summary = manager.summary()
    except Exception:
        return SDKTranscriptSummary("unknown", None, None, ("sdk_transcript_summary_failed",))
    if not sdk_transcript_summary_is_valid(summary):
        return SDKTranscriptSummary("unknown", None, None, ("sdk_transcript_summary_invalid",))
    return summary
