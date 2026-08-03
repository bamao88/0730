"""Platform-neutral contracts for explicit local evidence directory grants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

DirectorySelectionStatus = Literal["selected", "cancelled", "unavailable", "invalid"]


@dataclass(frozen=True, slots=True)
class DirectorySelection:
    """An in-memory directory grant returned by an optional local shell adapter."""

    status: DirectorySelectionStatus
    path: Path | None = None
    failure_code: str | None = None


class DirectorySelector(Protocol):
    """Optional local-shell capability; core conversion never imports an implementation."""

    def select(self) -> DirectorySelection: ...
