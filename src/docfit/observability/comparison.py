"""Privacy-safe, evidence-aware comparison of two observation runs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from docfit.observability.events import ObservationEvent
from docfit.observability.presentation import build_run_presentation
from docfit.observability.storage import StoredObservationRun

Comparability = Literal["strict", "conditional", "not_comparable"]

_CONDITIONS: tuple[tuple[str, str, str], ...] = (
    ("source_sha256", "Input document hash", "input"),
    ("template_sha256", "School template hash", "input"),
    ("requirements_sha256", "School requirements hash", "input"),
    ("backend", "Backend", "runtime"),
    ("model", "Model", "runtime"),
    ("sdk_version", "Claude Agent SDK version", "runtime"),
    ("app_version", "DocFit App version", "runtime"),
    ("skill_name", "Skill set", "runtime"),
    ("knowledge_version", "Knowledge version", "runtime"),
    ("knowledge_digest", "Knowledge digest", "runtime"),
    ("tool_version", "DocFit Tool version", "runtime"),
    ("officecli_version", "OfficeCLI version", "runtime"),
    ("adobe_sdk_version", "Adobe SDK version", "runtime"),
    ("route_fingerprint", "Selected route fingerprint", "runtime"),
    ("routing_policy", "Routing policy", "runtime"),
    ("task_authorization", "Task authorization", "runtime"),
    ("validation_requirement", "Final validation requirement", "validation"),
    ("final_evidence_category", "Final evidence category", "validation"),
)
_DIRECTLY_BLOCKING_GROUPS = frozenset({"input", "validation"})


def _attribute_values(events: Sequence[ObservationEvent], key: str) -> tuple[object, ...]:
    values: set[object] = set()
    for event in events:
        attributes = {attribute.key: attribute.value for attribute in event.attributes}
        value = attributes.get(key)
        if value is not None:
            values.add(value)
        provider = attributes.get("provider")
        provider_version = attributes.get("provider_version")
        if key == "officecli_version" and provider == "officecli" and provider_version:
            values.add(provider_version)
        if (
            key == "adobe_sdk_version"
            and isinstance(provider, str)
            and provider.startswith("adobe")
            and provider_version
        ):
            values.add(provider_version)
    return tuple(sorted(values, key=str))


def _display_values(values: tuple[object, ...]) -> object:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def _conditions(
    left_events: Sequence[ObservationEvent],
    right_events: Sequence[ObservationEvent],
) -> tuple[tuple[dict[str, object], ...], Comparability, bool]:
    rows: list[dict[str, object]] = []
    blocking_difference = False
    blocking_unknown = False
    all_match = True
    for key, label, group in _CONDITIONS:
        left = _attribute_values(left_events, key)
        right = _attribute_values(right_events, key)
        if not left or not right:
            state = "unknown"
            all_match = False
            blocking_unknown = blocking_unknown or group in _DIRECTLY_BLOCKING_GROUPS
        elif left == right:
            state = "match"
        else:
            state = "different"
            all_match = False
            blocking_difference = blocking_difference or group in _DIRECTLY_BLOCKING_GROUPS
        rows.append(
            {
                "key": key,
                "label": label,
                "group": group,
                "left": _display_values(left),
                "right": _display_values(right),
                "state": state,
            }
        )
    if blocking_difference:
        status: Comparability = "not_comparable"
    elif all_match:
        status = "strict"
    else:
        status = "conditional"
    return tuple(rows), status, blocking_unknown


def _metric_map(view: dict[str, object]) -> dict[str, dict[str, object]]:
    metrics = cast(Sequence[dict[str, object]], view["metrics"])
    return {cast(str, metric["key"]): metric for metric in metrics}


def _delta(left: object, right: object) -> int | float | None:
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return right - left
    return None


def _metric_rows(
    left_view: dict[str, object], right_view: dict[str, object]
) -> tuple[dict[str, object], ...]:
    left = _metric_map(left_view)
    right = _metric_map(right_view)
    rows: list[dict[str, object]] = []
    for key, left_metric in left.items():
        right_metric = right[key]
        left_value = left_metric["value"]
        right_value = right_metric["value"]
        rows.append(
            {
                "key": key,
                "label": left_metric["label"],
                "left": left_value,
                "right": right_value,
                "left_source": left_metric["source"],
                "right_source": right_metric["source"],
                "delta": _delta(left_value, right_value),
                "availability": (
                    "available"
                    if left_value is not None and right_value is not None
                    else "unknown"
                ),
            }
        )
    return tuple(rows)


def _tool_map(view: dict[str, object]) -> dict[str, dict[str, object]]:
    tools = cast(Sequence[dict[str, object]], view["tool_statistics"])
    return {cast(str, tool["tool_name"]): tool for tool in tools}


def _tool_rows(
    left_view: dict[str, object], right_view: dict[str, object]
) -> tuple[dict[str, object], ...]:
    left = _tool_map(left_view)
    right = _tool_map(right_view)
    rows: list[dict[str, object]] = []
    for tool_name in sorted(set(left) | set(right)):
        left_tool = left.get(tool_name, {})
        right_tool = right.get(tool_name, {})
        values: dict[str, object] = {}
        for metric in ("calls", "total_duration_ms", "average_duration_ms", "errors"):
            left_metric = cast(dict[str, object], left_tool.get(metric, {}))
            right_metric = cast(dict[str, object], right_tool.get(metric, {}))
            left_value = left_metric.get("value")
            right_value = right_metric.get("value")
            values[metric] = {
                "left": left_value,
                "right": right_value,
                "left_source": left_metric.get("source", "unknown"),
                "right_source": right_metric.get("source", "unknown"),
                "delta": _delta(left_value, right_value),
                "availability": (
                    "available"
                    if left_value is not None and right_value is not None
                    else "unknown"
                ),
            }
        rows.append({"tool_name": tool_name, **values})
    return tuple(rows)


def build_run_comparison(
    left_run: StoredObservationRun,
    left_events: Sequence[ObservationEvent],
    right_run: StoredObservationRun,
    right_events: Sequence[ObservationEvent],
) -> dict[str, object]:
    """Compare sanitized projections without treating missing values as zero."""

    left_view = build_run_presentation(left_run, left_events)
    right_view = build_run_presentation(right_run, right_events)
    conditions, status, blocking_unknown = _conditions(left_events, right_events)
    left_dimensions = cast(dict[str, object], left_view["dimensions"])
    right_dimensions = cast(dict[str, object], right_view["dimensions"])
    return {
        "comparability": {
            "status": status,
            "conditions": conditions,
            "performance_conclusion": (
                "not_allowed"
                if status == "not_comparable" or blocking_unknown
                else "differences_only"
            ),
            "reason": (
                "input_or_validation_gate_differs"
                if status == "not_comparable"
                else (
                    "input_or_validation_gate_unknown"
                    if blocking_unknown
                    else "conditions_recorded"
                )
            ),
        },
        "left": {
            "run": left_view["run"],
            "run_result": left_dimensions["run_result"],
            "artifacts": left_view["artifacts"],
        },
        "right": {
            "run": right_view["run"],
            "run_result": right_dimensions["run_result"],
            "artifacts": right_view["artifacts"],
        },
        "metrics": _metric_rows(left_view, right_view),
        "tools": _tool_rows(left_view, right_view),
        "agent_sequence_note": "investigation_clue_not_gold",
        "winner": None,
    }
