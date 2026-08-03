"""Bounded, metadata-only observation event contract.

Only values represented by these frozen types may cross the future queue
boundary.  Raw SDK messages, Tool dictionaries, paths, bytes, and exceptions
are deliberately absent from the sink protocol.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal, Protocol

MAX_OBSERVATION_EVENT_BYTES = 64 * 1024
PROJECTOR_DEADLINE_MS = 10.0

ObservationSource = Literal["app", "sdk", "permission", "tool", "report"]
ObservationPriority = Literal["P0", "P1", "P2"]
ActorRole = Literal["main", "subagent", "app", "tool", "unknown"]
type SafeAttributeValue = (
    str | int | float | bool | None | tuple[str, ...] | tuple[int, ...]
)

_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_RUN_ID = re.compile(r"^run_[0-9a-f]{32}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_ID = re.compile(r"^obj-[0-9a-f]{24}$")
_EVIDENCE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,255}$")
ALLOWED_OBSERVATION_ATTRIBUTE_KEYS = frozenset(
    {
        "answered",
        "api_error_status",
        "artifact_published",
        "association",
        "attempt",
        "backend",
        "block_count",
        "cache_creation_input_tokens",
        "cache_hit",
        "cache_read_input_tokens",
        "check_count",
        "committed",
        "coverage_state",
        "crop_count",
        "dpi",
        "duration_api_ms",
        "errors",
        "events_dropped",
        "events_persisted",
        "evidence_count",
        "final_sha256",
        "focus",
        "focus_count",
        "focus_ref_count",
        "image_bytes",
        "image_count",
        "input_tokens",
        "issues",
        "knowledge_digest",
        "knowledge_version",
        "mode",
        "model",
        "num_turns",
        "object_count",
        "object_ref_count",
        "operation_count",
        "operation_types",
        "option_count",
        "output_tokens",
        "page_count",
        "pages_available",
        "payload_bytes",
        "pdf_available",
        "provider",
        "question_count",
        "reason_code",
        "render_intent",
        "report_run_id",
        "report_schema",
        "required_visual_coverage",
        "requirements_sha256",
        "risk_count",
        "side_effect_possible",
        "skill_name",
        "source_sha256",
        "stop_hook_active",
        "stop_reason",
        "subagent_type",
        "subtype",
        "task_rule_count",
        "task_ref",
        "template_sha256",
        "terminal_reason",
        "tool_use_count",
        "total_cost_usd",
        "transcript_residual_count",
        "transcript_status",
        "warning_count",
        "warnings",
    }
)


@dataclass(frozen=True, slots=True)
class ObservationActor:
    role: ActorRole
    agent_id: str | None = None
    agent_type: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationAttribute:
    key: str
    value: SafeAttributeValue


@dataclass(frozen=True, slots=True)
class ObservationError:
    code: str
    origin: str
    retryable: bool | None = None
    interrupt: bool | None = None


@dataclass(frozen=True, slots=True)
class ObservationEvidenceRef:
    kind: Literal["document", "object", "render", "evidence", "page"]
    value: str | int
    document_sha256: str | None = None
    render_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationEvent:
    schema_version: int
    run_id: str
    source_event_id: str
    source_sequence: int
    observed_at: str
    monotonic_offset_ms: float
    source: ObservationSource
    kind: str
    priority: ObservationPriority
    actor: ObservationActor
    summary_code: str
    status: str | None = None
    session_id: str | None = None
    tool_name: str | None = None
    tool_use_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    parent_tool_use_id: str | None = None
    duration_ms: float | None = None
    attributes: tuple[ObservationAttribute, ...] = ()
    evidence_refs: tuple[ObservationEvidenceRef, ...] = ()
    error: ObservationError | None = None


@dataclass(frozen=True, slots=True)
class ProjectionContext:
    run_id: str
    source_sequence: int
    observed_at: str
    monotonic_offset_ms: float


@dataclass(frozen=True, slots=True)
class SanitizationReceipt:
    status: Literal["accepted", "dropped"]
    reason_code: str
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    event: ObservationEvent | None
    receipt: SanitizationReceipt


class SanitizedEventSink(Protocol):
    """Future queue boundary; raw source types cannot satisfy this signature."""

    def record(self, event: ObservationEvent) -> SanitizationReceipt: ...


class ProjectionRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _code(value: object) -> bool:
    return isinstance(value, str) and _SAFE_CODE.fullmatch(value) is not None


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
        and math.isfinite(float(value))
    )


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _attribute_value(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return value >= 0 and math.isfinite(value)
    if isinstance(value, str):
        return _identifier(value)
    if isinstance(value, tuple):
        if len(value) > 256:
            return False
        if not value:
            return True
        if all(
            isinstance(item, int) and not isinstance(item, bool) and item >= 0
            for item in value
        ):
            return True
        return all(_identifier(item) for item in value)
    return False


def observation_event_bytes(event: ObservationEvent) -> int:
    return len(
        json.dumps(
            asdict(event),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def validate_observation_event(event: object) -> str | None:
    if not isinstance(event, ObservationEvent):
        return "observer_event_type_invalid"
    if event.schema_version != 1 or isinstance(event.schema_version, bool):
        return "observer_event_schema_invalid"
    if _RUN_ID.fullmatch(event.run_id) is None:
        return "observer_event_run_id_invalid"
    if not _identifier(event.source_event_id):
        return "observer_event_source_id_invalid"
    if not _count(event.source_sequence):
        return "observer_event_sequence_invalid"
    if not _timestamp(event.observed_at) or not _number(event.monotonic_offset_ms):
        return "observer_event_time_invalid"
    if event.source not in {"app", "sdk", "permission", "tool", "report"}:
        return "observer_event_source_invalid"
    if event.priority not in {"P0", "P1", "P2"}:
        return "observer_event_priority_invalid"
    if not _code(event.kind) or not _code(event.summary_code):
        return "observer_event_kind_invalid"
    if event.status is not None and not _code(event.status):
        return "observer_event_status_invalid"
    if event.actor.role not in {"main", "subagent", "app", "tool", "unknown"}:
        return "observer_event_actor_invalid"
    for value in (
        event.actor.agent_id,
        event.actor.agent_type,
        event.session_id,
        event.tool_name,
        event.tool_use_id,
        event.agent_id,
        event.agent_type,
        event.parent_tool_use_id,
    ):
        if value is not None and not _identifier(value):
            return "observer_event_identifier_invalid"
    if event.duration_ms is not None and not _number(event.duration_ms):
        return "observer_event_duration_invalid"
    if len(event.attributes) > 128 or any(
        item.key not in ALLOWED_OBSERVATION_ATTRIBUTE_KEYS
        or not _attribute_value(item.value)
        for item in event.attributes
    ):
        return "observer_event_attributes_invalid"
    if len({item.key for item in event.attributes}) != len(event.attributes):
        return "observer_event_attributes_invalid"
    if len(event.evidence_refs) > 256:
        return "observer_event_evidence_invalid"
    for reference in event.evidence_refs:
        if reference.document_sha256 is not None and _HASH.fullmatch(
            reference.document_sha256
        ) is None:
            return "observer_event_evidence_invalid"
        if reference.render_sha256 is not None and _HASH.fullmatch(
            reference.render_sha256
        ) is None:
            return "observer_event_evidence_invalid"
        if reference.kind == "document" and not (
            isinstance(reference.value, str) and _HASH.fullmatch(reference.value)
        ):
            return "observer_event_evidence_invalid"
        if reference.kind == "render" and not (
            isinstance(reference.value, str) and _HASH.fullmatch(reference.value)
        ):
            return "observer_event_evidence_invalid"
        if reference.kind == "object" and not (
            isinstance(reference.value, str) and _OBJECT_ID.fullmatch(reference.value)
        ):
            return "observer_event_evidence_invalid"
        if reference.kind == "evidence" and not (
            isinstance(reference.value, str) and _EVIDENCE_ID.fullmatch(reference.value)
        ):
            return "observer_event_evidence_invalid"
        if reference.kind == "page" and not (
            isinstance(reference.value, int)
            and not isinstance(reference.value, bool)
            and reference.value >= 1
        ):
            return "observer_event_evidence_invalid"
    if event.error is not None and not (
        _code(event.error.code)
        and _code(event.error.origin)
        and (event.error.retryable is None or isinstance(event.error.retryable, bool))
        and (event.error.interrupt is None or isinstance(event.error.interrupt, bool))
    ):
        return "observer_event_error_invalid"
    if observation_event_bytes(event) > MAX_OBSERVATION_EVENT_BYTES:
        return "observer_event_too_large"
    return None


def project_safely(projector: Callable[[], ObservationEvent]) -> ProjectionResult:
    started = time.perf_counter_ns()
    try:
        event = projector()
    except ProjectionRejected as error:
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        return ProjectionResult(None, SanitizationReceipt("dropped", error.code, elapsed))
    except Exception:
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        return ProjectionResult(
            None,
            SanitizationReceipt("dropped", "observer_projector_failed", elapsed),
        )
    failure = validate_observation_event(event)
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    if elapsed >= PROJECTOR_DEADLINE_MS:
        return ProjectionResult(
            None,
            SanitizationReceipt("dropped", "observer_projector_deadline", elapsed),
        )
    if failure is not None:
        return ProjectionResult(None, SanitizationReceipt("dropped", failure, elapsed))
    return ProjectionResult(
        event,
        SanitizationReceipt("accepted", "observer_event_accepted", elapsed),
    )


def record_sanitized_event(
    sink: SanitizedEventSink,
    event: ObservationEvent,
) -> SanitizationReceipt:
    failure = validate_observation_event(event)
    if failure is not None:
        return SanitizationReceipt("dropped", failure, 0.0)
    try:
        return sink.record(event)
    except Exception:
        return SanitizationReceipt("dropped", "observer_sink_failed", 0.0)
