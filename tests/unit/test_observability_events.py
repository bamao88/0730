from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime

from docfit.observability.events import (
    MAX_OBSERVATION_EVENT_BYTES,
    ObservationActor,
    ObservationAttribute,
    ObservationEvent,
    ObservationEvidenceRef,
    ProjectionContext,
    SanitizationReceipt,
    observation_event_bytes,
    project_safely,
    record_sanitized_event,
    validate_observation_event,
)
from docfit.observability.privacy import project_app_event

RUN_ID = "run_0123456789abcdef0123456789abcdef"


def _context(sequence: int = 1) -> ProjectionContext:
    return ProjectionContext(
        run_id=RUN_ID,
        source_sequence=sequence,
        observed_at=datetime.now(UTC).isoformat(),
        monotonic_offset_ms=1.25,
    )


def _event() -> ObservationEvent:
    result = project_app_event(
        _context(),
        source_event_id="app-run-start",
        kind="run_started",
        status="started",
        task_ref="task_fedcba9876543210fedcba9876543210",
        hashes={"source_sha256": "a" * 64},
    )
    assert result.event is not None
    return result.event


def test_valid_event_is_bounded_and_accepted() -> None:
    event = _event()

    assert validate_observation_event(event) is None
    assert observation_event_bytes(event) < MAX_OBSERVATION_EVENT_BYTES


def test_app_priorities_reserve_p0_for_run_terminal_and_failures() -> None:
    backend = project_app_event(
        _context(2),
        source_event_id="backend-start",
        kind="backend_started",
        status="started",
    )
    failed_backend = project_app_event(
        _context(3),
        source_event_id="backend-failed",
        kind="backend_finished",
        status="error",
        failure_code="backend_failed",
    )
    terminal = project_app_event(
        _context(4),
        source_event_id="run-finish",
        kind="run_finished",
        status="completed",
    )

    assert backend.event is not None and backend.event.priority == "P1"
    assert failed_backend.event is not None and failed_backend.event.priority == "P0"
    assert terminal.event is not None and terminal.event.priority == "P0"


def test_app_runtime_identity_keeps_only_safe_comparison_fields() -> None:
    result = project_app_event(
        _context(5),
        source_event_id="run-start",
        kind="run_started",
        status="started",
        runtime_identity={
            "app_version": "0.1.0",
            "sdk_version": "0.2.128",
            "routing_policy": "configured_backend_fallback_v1",
            "task_authorization": "task_root_capability_v1",
            "validation_requirement": "m2_delivery_gate_v1",
            "unknown_field": "PRIVATE_BODY_CANARY",
            "tool_version": "/private/PRIVATE_PATH_CANARY",
        },
    )

    assert result.event is not None
    attributes = {item.key: item.value for item in result.event.attributes}
    assert attributes == {
        "app_version": "0.1.0",
        "sdk_version": "0.2.128",
        "routing_policy": "configured_backend_fallback_v1",
        "task_authorization": "task_root_capability_v1",
        "validation_requirement": "m2_delivery_gate_v1",
    }


def test_future_sink_rejects_raw_payload_before_recording() -> None:
    class Sink:
        calls = 0

        def record(self, event: ObservationEvent) -> SanitizationReceipt:
            self.calls += 1
            return SanitizationReceipt("accepted", "observer_event_accepted", 0.0)

    sink = Sink()
    receipt = record_sanitized_event(  # type: ignore[arg-type]
        sink,
        {"prompt": "PRIVATE_PROMPT_CANARY"},
    )

    assert sink.calls == 0
    assert receipt.status == "dropped"
    assert receipt.reason_code == "observer_event_type_invalid"
    assert "PRIVATE_PROMPT_CANARY" not in str(receipt)


def test_projector_exception_returns_fixed_drop_without_raw_detail() -> None:
    def fail() -> ObservationEvent:
        raise RuntimeError("PRIVATE_EXCEPTION_CANARY")

    result = project_safely(fail)

    assert result.event is None
    assert result.receipt.reason_code == "observer_projector_failed"
    assert "PRIVATE_EXCEPTION_CANARY" not in str(result)


def test_projector_deadline_drops_event() -> None:
    event = _event()

    def slow() -> ObservationEvent:
        time.sleep(0.02)
        return event

    result = project_safely(slow)

    assert result.event is None
    assert result.receipt.reason_code == "observer_projector_deadline"
    assert result.receipt.elapsed_ms >= 10


def test_event_over_64_kib_is_dropped_without_payload_fallback() -> None:
    event = _event()
    oversized = replace(
        event,
        evidence_refs=tuple(
            ObservationEvidenceRef("evidence", f"e{i:03d}-" + ("a" * 240))
            for i in range(256)
        ),
    )

    assert observation_event_bytes(oversized) > MAX_OBSERVATION_EVENT_BYTES
    result = project_safely(lambda: oversized)

    assert result.event is None
    assert result.receipt.reason_code == "observer_event_too_large"


def test_invalid_identifiers_paths_and_negative_times_are_rejected() -> None:
    event = _event()

    assert (
        validate_observation_event(replace(event, source_event_id="/private/task"))
        == "observer_event_source_id_invalid"
    )
    assert (
        validate_observation_event(replace(event, monotonic_offset_ms=-1))
        == "observer_event_time_invalid"
    )
    assert (
        validate_observation_event(
            replace(event, actor=ObservationActor("main", agent_id="../escape"))
        )
        == "observer_event_identifier_invalid"
    )
    assert (
        validate_observation_event(
            replace(
                event,
                attributes=(
                    ObservationAttribute("prompt", "private_prompt_canary"),
                ),
            )
        )
        == "observer_event_attributes_invalid"
    )


def test_projector_latency_p95_and_p99_stay_within_contract() -> None:
    samples: list[float] = []
    for sequence in range(1, 2001):
        result = project_app_event(
            _context(sequence),
            source_event_id=f"app-{sequence}",
            kind="backend_started",
            status="started",
            backend="synthetic-backend",
            model="synthetic-model",
            attempt=sequence,
            hashes={"source_sha256": "a" * 64},
        )
        samples.append(result.receipt.elapsed_ms)
        if result.event is None:
            assert result.receipt.status == "dropped"
            assert result.receipt.reason_code == "observer_projector_deadline"
            assert result.receipt.elapsed_ms >= 10.0
        else:
            assert result.receipt.status == "accepted"

    ordered = sorted(samples)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    p99 = ordered[int(len(ordered) * 0.99) - 1]
    assert p95 <= 2.0
    assert p99 <= 5.0
