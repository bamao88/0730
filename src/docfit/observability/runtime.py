"""Conversion-owned observation bootstrap lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from docfit.observability.models import ObservationMode, ObservationRecorder
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

    def close(self) -> None:
        return None


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
