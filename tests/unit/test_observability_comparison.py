from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from docfit.observability.comparison import build_run_comparison
from docfit.observability.events import (
    ObservationActor,
    ObservationAttribute,
    ObservationEvent,
)
from docfit.observability.storage import StoredObservationRun

LEFT_RUN_ID = "run_0123456789abcdef0123456789abcdef"
RIGHT_RUN_ID = "run_fedcba9876543210fedcba9876543210"
BASE_TIME = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)

CONDITIONS = (
    ObservationAttribute("source_sha256", "a" * 64),
    ObservationAttribute("template_sha256", "b" * 64),
    ObservationAttribute("requirements_sha256", "c" * 64),
    ObservationAttribute("backend", "synthetic-backend"),
    ObservationAttribute("model", "synthetic-model"),
    ObservationAttribute("sdk_version", "0.2.128"),
    ObservationAttribute("app_version", "0.1.0"),
    ObservationAttribute("skill_name", "convert-thesis"),
    ObservationAttribute("knowledge_version", "v1"),
    ObservationAttribute("knowledge_digest", "sha256:" + "d" * 64),
    ObservationAttribute("tool_version", "0.1.0"),
    ObservationAttribute("officecli_version", "1.0.143"),
    ObservationAttribute("renderer", "libreoffice"),
    ObservationAttribute("renderer_version", "libreoffice-25.2.3.2"),
    ObservationAttribute("route_fingerprint", "f" * 64),
    ObservationAttribute("routing_policy", "configured_backend_fallback_v1"),
    ObservationAttribute("task_authorization", "task_root_capability_v1"),
    ObservationAttribute("validation_requirement", "m2_delivery_gate_v1"),
    ObservationAttribute(
        "final_evidence_category", "libreoffice_full_page_validation_v2"
    ),
)


def _event(
    run_id: str,
    sequence: int,
    kind: str,
    *,
    duration_ms: float | None = None,
    attributes: tuple[ObservationAttribute, ...] = (),
) -> ObservationEvent:
    return ObservationEvent(
        schema_version=1,
        run_id=run_id,
        source_event_id=f"{kind}-{sequence}",
        source_sequence=sequence,
        observed_at=(BASE_TIME + timedelta(milliseconds=sequence)).isoformat(),
        monotonic_offset_ms=float(sequence),
        source="report" if kind == "conversion_report" else "app",
        kind=kind,
        priority="P0",
        actor=ObservationActor("app"),
        summary_code=f"{kind}_observed",
        status="completed" if kind != "run_started" else "started",
        duration_ms=duration_ms,
        attributes=attributes,
    )


def _run(
    run_id: str, *, duration_ms: float = 100.0
) -> tuple[StoredObservationRun, tuple[ObservationEvent, ...]]:
    coverage = (
        ObservationAttribute("coverage_state", "complete"),
        ObservationAttribute("events_persisted", 3),
        ObservationAttribute("events_dropped", 0),
        ObservationAttribute("transcript_status", "cleaned"),
    )
    events = (
        _event(run_id, 1, "run_started", attributes=CONDITIONS),
        _event(run_id, 2, "conversion_report", attributes=coverage),
        _event(run_id, 3, "run_finished", duration_ms=duration_ms),
    )
    run = StoredObservationRun(
        run_id,
        "task_0123456789abcdef0123456789abcdef",
        "synthetic-session",
        "completed",
        events[0].observed_at,
        events[-1].observed_at,
        events[-1].observed_at,
        len(events),
        2048,
    )
    return run, events


def _change(
    events: tuple[ObservationEvent, ...], key: str, value: str
) -> tuple[ObservationEvent, ...]:
    attributes = tuple(
        ObservationAttribute(item.key, value if item.key == key else item.value)
        for item in events[0].attributes
    )
    return (replace(events[0], attributes=attributes), *events[1:])


def test_strict_comparison_reports_deltas_without_declaring_a_winner() -> None:
    left_run, left_events = _run(LEFT_RUN_ID, duration_ms=100.0)
    right_run, right_events = _run(RIGHT_RUN_ID, duration_ms=125.0)

    comparison = build_run_comparison(
        left_run, left_events, right_run, right_events
    )

    assert comparison["comparability"]["status"] == "strict"
    assert comparison["comparability"]["performance_conclusion"] == "differences_only"
    duration = next(
        item for item in comparison["metrics"] if item["key"] == "total_duration_ms"
    )
    assert duration["left"] == 100.0
    assert duration["right"] == 125.0
    assert duration["delta"] == 25.0
    tokens = next(item for item in comparison["metrics"] if item["key"] == "input_tokens")
    assert tokens["left"] is None
    assert tokens["right"] is None
    assert tokens["delta"] is None
    assert comparison["winner"] is None


def test_runtime_difference_is_conditional_and_is_listed() -> None:
    left_run, left_events = _run(LEFT_RUN_ID)
    right_run, right_events = _run(RIGHT_RUN_ID)
    right_events = _change(right_events, "app_version", "0.2.0")

    comparison = build_run_comparison(
        left_run, left_events, right_run, right_events
    )

    assert comparison["comparability"]["status"] == "conditional"
    app_version = next(
        item
        for item in comparison["comparability"]["conditions"]
        if item["key"] == "app_version"
    )
    assert app_version["state"] == "different"
    assert app_version["left"] == "0.1.0"
    assert app_version["right"] == "0.2.0"


def test_input_or_validation_difference_is_not_comparable() -> None:
    left_run, left_events = _run(LEFT_RUN_ID)
    right_run, right_events = _run(RIGHT_RUN_ID)
    right_events = _change(right_events, "source_sha256", "e" * 64)

    comparison = build_run_comparison(
        left_run, left_events, right_run, right_events
    )

    assert comparison["comparability"]["status"] == "not_comparable"
    assert comparison["comparability"]["performance_conclusion"] == "not_allowed"
    assert comparison["comparability"]["reason"] == "input_or_validation_gate_differs"


def test_missing_required_condition_stays_unknown_and_blocks_conclusion() -> None:
    left_run, left_events = _run(LEFT_RUN_ID)
    right_run, right_events = _run(RIGHT_RUN_ID)
    right_events = (
        replace(
            right_events[0],
            attributes=tuple(
                item for item in right_events[0].attributes if item.key != "validation_requirement"
            ),
        ),
        *right_events[1:],
    )

    comparison = build_run_comparison(
        left_run, left_events, right_run, right_events
    )

    assert comparison["comparability"]["status"] == "conditional"
    assert comparison["comparability"]["performance_conclusion"] == "not_allowed"
    validation = next(
        item
        for item in comparison["comparability"]["conditions"]
        if item["key"] == "validation_requirement"
    )
    assert validation["right"] is None
    assert validation["state"] == "unknown"
