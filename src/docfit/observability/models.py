"""Internal O0 observation bootstrap contracts.

O0.0 deliberately has no event payload model yet.  Later phases may extend this
module only with already-sanitized values; raw SDK or Tool objects never belong
on the recorder boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from docfit.observability.events import (
    ObservationEvent,
    SanitizationReceipt,
)

ObservationMode = Literal["auto", "off"]
ObservationCoverageState = Literal["complete", "degraded", "unavailable"]
SDKTranscriptStatus = Literal[
    "active",
    "cleaned",
    "residual",
    "cleanup_failed",
    "unknown",
]
SDKTranscriptAgeBucket = Literal["under_1h", "1h_to_24h", "1d_to_7d", "over_7d"]
_SAFE_SUMMARY_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class ObservationCoverageSummary:
    state: ObservationCoverageState
    events_persisted: int | None
    events_dropped: int | None
    missing_sources: tuple[str, ...]
    last_observed_at: str | None
    failure_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SDKTranscriptSummary:
    status: SDKTranscriptStatus
    residual_count: int | None
    oldest_age_bucket: SDKTranscriptAgeBucket | None
    failure_codes: tuple[str, ...]


def _summary_codes_are_valid(values: object) -> bool:
    return bool(
        isinstance(values, tuple)
        and len(values) <= 32
        and all(
            isinstance(value, str) and _SAFE_SUMMARY_CODE.fullmatch(value) is not None
            for value in values
        )
    )


def _summary_count_is_valid(value: object) -> bool:
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
    )


def observation_coverage_summary_is_valid(summary: object) -> bool:
    if not isinstance(summary, ObservationCoverageSummary):
        return False
    if summary.state not in {"complete", "degraded", "unavailable"}:
        return False
    if not _summary_count_is_valid(summary.events_persisted):
        return False
    if not _summary_count_is_valid(summary.events_dropped):
        return False
    if not _summary_codes_are_valid(summary.missing_sources):
        return False
    if not _summary_codes_are_valid(summary.failure_codes):
        return False
    if summary.last_observed_at is None:
        return True
    if not isinstance(summary.last_observed_at, str) or len(summary.last_observed_at) > 256:
        return False
    try:
        observed_at = datetime.fromisoformat(
            summary.last_observed_at.replace("Z", "+00:00")
        )
    except ValueError:
        return False
    return observed_at.tzinfo is not None


def sdk_transcript_summary_is_valid(summary: object) -> bool:
    return bool(
        isinstance(summary, SDKTranscriptSummary)
        and summary.status
        in {"active", "cleaned", "residual", "cleanup_failed", "unknown"}
        and _summary_count_is_valid(summary.residual_count)
        and (
            summary.oldest_age_bucket is None
            or summary.oldest_age_bucket
            in {"under_1h", "1h_to_24h", "1d_to_7d", "over_7d"}
        )
        and _summary_codes_are_valid(summary.failure_codes)
    )


class ObservationRecorder(Protocol):
    """Small lifecycle seam owned by the conversion shell."""

    @property
    def enabled(self) -> bool: ...

    @property
    def state_root(self) -> Path | None: ...

    @property
    def failure_code(self) -> str | None: ...

    def summary(self) -> ObservationCoverageSummary: ...

    def record(self, event: ObservationEvent) -> SanitizationReceipt: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ObservationBenchmark:
    iterations: int
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int
