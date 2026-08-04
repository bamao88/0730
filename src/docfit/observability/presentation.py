"""Privacy-safe view models for the local observation website."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import cast

from docfit.observability.correlation import (
    AdapterHealthReceipt,
    LocalEvidenceStatus,
    MetricValue,
    RunCorrelation,
    RunResultStatus,
    correlate_observation_run,
)
from docfit.observability.events import ObservationEvent, ObservationSource
from docfit.observability.storage import StoredObservationRun

_SOURCES: tuple[ObservationSource, ...] = (
    "app",
    "sdk",
    "permission",
    "tool",
    "report",
)
_HASH_KEYS = (
    "source_sha256",
    "template_sha256",
    "requirements_sha256",
    "final_sha256",
)
_VERSION_KEYS = (
    "app_version",
    "sdk_version",
    "backend",
    "model",
    "provider",
    "skill_name",
    "knowledge_version",
    "knowledge_digest",
    "tool_version",
    "officecli_version",
    "adobe_sdk_version",
    "provider_version",
    "routing_policy",
    "task_authorization",
    "validation_requirement",
    "final_evidence_category",
    "route_fingerprint",
)


def _attribute(event: ObservationEvent, key: str) -> object:
    for attribute in event.attributes:
        if attribute.key == key:
            return attribute.value
    return None


def _ordered_events(events: Sequence[ObservationEvent]) -> tuple[ObservationEvent, ...]:
    return tuple(
        sorted(
            events,
            key=lambda event: (
                event.monotonic_offset_ms,
                event.source_sequence,
                event.source,
                event.source_event_id,
                event.kind,
            ),
        )
    )


def _metric(value: MetricValue) -> dict[str, object]:
    return {"value": value.value, "source": value.source}


def _reported_coverage(events: Sequence[ObservationEvent]) -> dict[str, object] | None:
    reports = [event for event in events if event.kind == "conversion_report"]
    if not reports:
        return None
    report = max(reports, key=lambda event: event.monotonic_offset_ms)
    state = _attribute(report, "coverage_state")
    if state not in {"complete", "degraded", "unavailable"}:
        return None
    return {
        "state": state,
        "events_persisted": _attribute(report, "events_persisted"),
        "events_dropped": _attribute(report, "events_dropped"),
        "last_observed_at": report.observed_at,
        "missing_sources": (),
        "failure_codes": (),
        "source": "reported",
    }


def _adapter_receipts(events: Sequence[ObservationEvent]) -> tuple[AdapterHealthReceipt, ...]:
    coverage = _reported_coverage(events)
    if coverage is None or coverage["state"] != "complete":
        return ()
    if coverage["events_dropped"] != 0:
        return ()
    return tuple(AdapterHealthReceipt(source, "available") for source in _SOURCES)


def _event_view(index: int, event: ObservationEvent) -> dict[str, object]:
    attributes = tuple(
        {"key": attribute.key, "value": attribute.value} for attribute in event.attributes
    )
    evidence = tuple(asdict(reference) for reference in event.evidence_refs)
    actor_label = {
        "main": "Main Agent",
        "subagent": event.actor.agent_type or "Subagent",
        "app": "App",
        "tool": "Tool adapter",
        "unknown": "Unknown actor",
    }[event.actor.role]
    return {
        "index": index,
        "source": event.source,
        "source_event_id": event.source_event_id,
        "source_sequence": event.source_sequence,
        "observed_at": event.observed_at,
        "monotonic_offset_ms": event.monotonic_offset_ms,
        "kind": event.kind,
        "priority": event.priority,
        "actor": actor_label,
        "actor_role": event.actor.role,
        "agent_id": event.agent_id,
        "agent_type": event.agent_type,
        "summary_code": event.summary_code,
        "status": event.status or "unknown",
        "session_id": event.session_id,
        "tool_name": event.tool_name,
        "tool_use_id": event.tool_use_id,
        "parent_tool_use_id": event.parent_tool_use_id,
        "duration_ms": event.duration_ms,
        "attributes": attributes,
        "evidence": evidence,
        "error": None if event.error is None else asdict(event.error),
    }


def _tool_view(
    correlation: RunCorrelation,
    tool_use_id: str,
    event_views: Sequence[dict[str, object]],
) -> dict[str, object]:
    tool = next(item for item in correlation.tools if item.tool_use_id == tool_use_id)
    related = tuple(event for event in event_views if event["tool_use_id"] == tool_use_id)
    attributes = tuple(
        {
            "source": event["source"],
            "key": attribute["key"],
            "value": attribute["value"],
        }
        for event in related
        for attribute in cast(tuple[dict[str, object], ...], event["attributes"])
    )
    evidence = tuple(
        reference
        for event in related
        for reference in cast(tuple[dict[str, object], ...], event["evidence"])
    )
    errors = tuple(event["error"] for event in related if event["error"] is not None)
    return {
        "tool_use_id": tool.tool_use_id,
        "tool_name": tool.tool_name or "unknown",
        "caller": tool.agent_id or "main",
        "agent_id": tool.agent_id,
        "parent_tool_use_id": tool.parent_tool_use_id,
        "status": tool.status,
        "association_status": tool.association_status,
        "duration": _metric(tool.duration),
        "started_at": related[0]["observed_at"] if related else None,
        "completed_at": related[-1]["observed_at"] if related else None,
        "reason_codes": tool.reason_codes,
        "event_indices": tuple(event["index"] for event in related),
        "attributes": attributes,
        "evidence": evidence,
        "errors": errors,
    }


def _subagent_view(
    correlation: RunCorrelation,
    node_id: str,
    event_views: Sequence[dict[str, object]],
    tools: Sequence[dict[str, object]],
) -> dict[str, object]:
    node = next(item for item in correlation.subagents if item.node_id == node_id)
    if node.agent_id is not None:
        related = tuple(event for event in event_views if event["agent_id"] == node.agent_id)
    else:
        related = tuple(
            event for event in event_views if event["tool_use_id"] == node.parent_tool_use_id
        )
    offsets = tuple(cast(float, event["monotonic_offset_ms"]) for event in related)
    duration = (
        {"value": max(offsets) - min(offsets), "source": "estimated"}
        if len(offsets) >= 2
        else {"value": None, "source": "unknown"}
    )
    failures = tuple(event["error"] for event in related if event["error"] is not None)
    permission_decisions = tuple(
        event["status"] for event in related if event["kind"] == "permission_decision"
    )
    return {
        "node_id": node.node_id,
        "agent_id": node.agent_id,
        "agent_type": node.agent_type or "unknown",
        "parent_tool_use_id": node.parent_tool_use_id,
        "status": node.status,
        "association_status": node.association_status,
        "reason_codes": node.reason_codes,
        "duration": duration,
        "started_at": related[0]["observed_at"] if related else None,
        "completed_at": related[-1]["observed_at"] if related else None,
        "tokens": {"value": None, "source": "unknown"},
        "failures": failures,
        "permission_decisions": permission_decisions,
        "event_indices": tuple(event["index"] for event in related),
        "tools": tuple(tool for tool in tools if tool["tool_use_id"] in node.tool_use_ids),
        "parent_tool": next(
            (tool for tool in tools if tool["tool_use_id"] == node.parent_tool_use_id),
            None,
        ),
    }


def _metric_rows(correlation: RunCorrelation) -> tuple[dict[str, object], ...]:
    values = (
        ("total_duration_ms", "Total duration", correlation.metrics.total_duration_ms),
        ("agent_turns", "Agent turns", correlation.metrics.agent_turns),
        ("tool_calls", "Tool calls", correlation.metrics.tool_calls),
        ("subagents", "Subagents", correlation.metrics.subagents),
        ("input_tokens", "Input tokens", correlation.metrics.input_tokens),
        ("output_tokens", "Output tokens", correlation.metrics.output_tokens),
        (
            "cache_creation_input_tokens",
            "Cache creation input tokens",
            correlation.metrics.cache_creation_input_tokens,
        ),
        (
            "cache_read_input_tokens",
            "Cache read input tokens",
            correlation.metrics.cache_read_input_tokens,
        ),
        ("total_cost_usd", "Reported cost (USD)", correlation.metrics.total_cost_usd),
        ("cache_hits", "Cache hits", correlation.metrics.cache_hits),
        ("adobe_api_calls", "Adobe API calls", correlation.metrics.adobe_api_calls),
        ("pages_viewed", "Pages viewed", correlation.metrics.pages_viewed),
        ("image_count", "Image count", correlation.metrics.image_count),
        ("image_bytes", "Image bytes", correlation.metrics.image_bytes),
        (
            "permission_denials",
            "Permission denials",
            correlation.metrics.permission_denials,
        ),
        ("user_questions", "User questions", correlation.metrics.user_questions),
        ("retries", "Retries", correlation.metrics.retries),
        ("errors", "Errors", correlation.metrics.errors),
        ("warnings", "Warnings", correlation.metrics.warnings),
    )
    return tuple(
        {"key": key, "label": label, **_metric(metric)}
        for key, label, metric in values
    )


def _tool_statistics(correlation: RunCorrelation) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "tool_name": item.tool_name,
            "calls": _metric(item.calls),
            "ok": _metric(item.ok),
            "needs_input": _metric(item.needs_input),
            "errors": _metric(item.errors),
            "total_duration_ms": _metric(item.total_duration_ms),
            "average_duration_ms": _metric(item.average_duration_ms),
            "p95_duration_ms": _metric(item.p95_duration_ms),
        }
        for item in correlation.metrics.tools
    )


def _reported_values(
    events: Sequence[ObservationEvent], keys: Sequence[str]
) -> tuple[dict[str, object], ...]:
    values: dict[str, set[object]] = {key: set() for key in keys}
    for event in events:
        for attribute in event.attributes:
            if attribute.key in values and attribute.value is not None:
                values[attribute.key].add(attribute.value)
    return tuple(
        {
            "key": key,
            "values": tuple(sorted(values[key], key=str)),
            "availability": "available" if values[key] else "unavailable",
        }
        for key in keys
    )


def _artifact_rows(events: Sequence[ObservationEvent]) -> tuple[dict[str, object], ...]:
    report_observed = any(event.kind == "conversion_report" for event in events)
    final_observed = any(_attribute(event, "final_sha256") is not None for event in events)
    render_published = any(
        event.tool_name == "mcp__docfit__docx_render"
        and _attribute(event, "artifact_published") is True
        for event in events
    )
    validation_observed = any(
        event.tool_name == "mcp__docfit__docx_validate"
        and event.kind in {"tool_post", "tool_failure"}
        for event in events
    )
    return (
        {
            "key": "conversion_report",
            "status": "observed" if report_observed else "unknown",
        },
        {
            "key": "final_docx",
            "status": "published" if final_observed else "unknown",
        },
        {
            "key": "render_evidence",
            "status": "published" if render_published else "unknown",
        },
        {
            "key": "validation_result",
            "status": "observed" if validation_observed else "unknown",
        },
    )


def build_run_presentation(
    run: StoredObservationRun,
    events: Sequence[ObservationEvent],
    *,
    local_evidence: LocalEvidenceStatus = "unmounted",
    evidence_association: str | None = None,
    evidence_failure: str | None = None,
) -> dict[str, object]:
    """Project one stored run into HTML/JSON-safe values only."""

    correlation = correlate_observation_run(
        run.run_id,
        events,
        adapter_receipts=_adapter_receipts(events),
        local_evidence=local_evidence,
    )
    ordered = _ordered_events(correlation.events)
    event_views = tuple(_event_view(index, event) for index, event in enumerate(ordered))
    tools = tuple(
        _tool_view(correlation, tool.tool_use_id, event_views) for tool in correlation.tools
    )
    subagents = tuple(
        _subagent_view(correlation, node.node_id, event_views, tools)
        for node in correlation.subagents
    )
    reported_coverage = _reported_coverage(events)
    coverage = {
        **asdict(correlation.dimensions.observation),
        "source": "correlated_safe_events",
        "reported_state": (None if reported_coverage is None else reported_coverage["state"]),
    }
    if reported_coverage is not None:
        coverage["events_persisted"] = reported_coverage["events_persisted"]
        coverage["events_dropped"] = reported_coverage["events_dropped"]
    relationships = tuple(
        {
            "kind": relationship.kind,
            "status": relationship.status,
            "proof_fields": relationship.proof_fields,
            "reason_codes": relationship.reason_codes,
            "parent": (None if relationship.parent is None else asdict(relationship.parent)),
            "child": asdict(relationship.child),
        }
        for relationship in correlation.relationships
    )
    result_status: RunResultStatus = correlation.dimensions.run_result
    if result_status == "unknown":
        status_mapping: dict[str, RunResultStatus] = {
            "completed": "COMPLETED",
            "needs_input": "NEEDS_INPUT",
            "error": "ERROR",
        }
        result_status = status_mapping.get(run.status, "unknown")
    return {
        "run": {
            "run_id": run.run_id,
            "task_ref": run.task_ref,
            "session_id": run.session_id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "last_observed_at": run.last_observed_at,
            "event_count": run.event_count,
            "event_bytes": run.event_bytes,
        },
        "dimensions": {
            "run_result": result_status,
            "observation": coverage,
            "local_evidence": local_evidence,
            "evidence_association": evidence_association,
            "evidence_failure": evidence_failure,
            "sdk_transcript": correlation.dimensions.sdk_transcript,
        },
        "association_status": correlation.association_status,
        "metrics": _metric_rows(correlation),
        "tool_statistics": _tool_statistics(correlation),
        "events": event_views,
        "tools": tools,
        "subagents": subagents,
        "relationships": relationships,
        "versions": _reported_values(events, _VERSION_KEYS),
        "hashes": _reported_values(events, _HASH_KEYS),
        "artifacts": _artifact_rows(events),
        "duplicate_events": correlation.duplicate_events,
        "rejected_events": correlation.rejected_events,
    }


def summarize_run(presentation: dict[str, object]) -> dict[str, object]:
    run = presentation["run"]
    dimensions = presentation["dimensions"]
    metrics = presentation["metrics"]
    return {
        "run": run,
        "dimensions": dimensions,
        "association_status": presentation["association_status"],
        "metrics": metrics,
        "tool_statistics": presentation["tool_statistics"],
    }


def build_debug_context(
    run: StoredObservationRun,
    event: ObservationEvent,
    *,
    local_evidence: LocalEvidenceStatus = "unmounted",
) -> dict[str, object]:
    """Build the allowlisted investigation handoff for one safe event."""

    attributes = {attribute.key: attribute.value for attribute in event.attributes}
    evidence = tuple(asdict(reference) for reference in event.evidence_refs)
    return {
        "debug_context_schema_version": 1,
        "run_id": run.run_id,
        "task_ref": run.task_ref,
        "session_id": event.session_id or run.session_id,
        "actor": event.actor.role,
        "agent_id": event.agent_id,
        "agent_type": event.agent_type,
        "event_kind": event.kind,
        "source": event.source,
        "source_sequence": event.source_sequence,
        "tool_name": event.tool_name,
        "tool_use_id": event.tool_use_id,
        "parent_tool_use_id": event.parent_tool_use_id,
        "status": event.status,
        "duration_ms": event.duration_ms,
        "failure": None if event.error is None else asdict(event.error),
        "committed": attributes.get("committed"),
        "evidence_refs": evidence,
        "local_evidence": local_evidence,
        "summary_code": event.summary_code,
    }


def ordered_run_events(
    run_id: str,
    events: Sequence[ObservationEvent],
) -> tuple[ObservationEvent, ...]:
    """Expose the same deterministic display order for debug-context lookup."""

    correlation = correlate_observation_run(run_id, events)
    return _ordered_events(correlation.events)


def history_revision(runs: Sequence[StoredObservationRun]) -> str:
    """Return an opaque change token derived only from safe run metadata."""

    payload = tuple(asdict(run) for run in runs)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
