"""Internal O0 observation bootstrap contracts.

O0.0 deliberately has no event payload model yet.  Later phases may extend this
module only with already-sanitized values; raw SDK or Tool objects never belong
on the recorder boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

ObservationMode = Literal["auto", "off"]


class ObservationRecorder(Protocol):
    """Small lifecycle seam owned by the conversion shell."""

    @property
    def enabled(self) -> bool: ...

    @property
    def state_root(self) -> Path | None: ...

    @property
    def failure_code(self) -> str | None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ObservationBenchmark:
    iterations: int
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int
