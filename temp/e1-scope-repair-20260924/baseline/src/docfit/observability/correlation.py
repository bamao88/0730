"""Direct-ID correlation and run metrics for sanitized observation events.

This module is deliberately a pure projection.  It does not read transcripts,
task files, images, or raw SDK/Tool payloads, and it does not persist anything.
Relationships are emitted only when the already-sanitized events contain the
direct IDs required by the O0 contract.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from docfit.observability.events import (
    ObservationEvent,
    ObservationEvidenceRef,
    ObservationSource,
    SanitizationReceipt,
    validate_observation_event,
)
from docfit.observability.models import (
    ObservationCoverageSummary,
    SDKTranscriptStatus,
)

AssociationStatus = Literal["verified", "partial", "broken", "conflict"]
MetricSource = Literal["reported", "estimated", "unknown"]
RunResultStatus = Literal["COMPLETED", "NEEDS_INPUT", "ERROR", "unknown"]
LocalEvidenceStatus = Literal[
    "unmounted",
    "available",
    "stale",
    "missing",
    "unauthorized",
    "conflict",
]
AdapterHealthState = Literal["available", "degraded", "unavailable"]
RelationshipKind = Literal[
    "tool_result",
    "parent_child",
    "tool_actor",
    "subagent_parent",
]

_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_RUN_ID = re.compile(r"^run_[0-9a-f]{32}$")
_SOURCES: tuple[ObservationSource, ...] = (
    "app",
    "sdk",
    "permission",
    "tool",
    "report",
)
_SDK_USE_KINDS = {
    "tool_use",
    "skill_use",
    "subagent_use",
    "user_question_started",
}
_TOOL_TERMINAL_KINDS = {"tool_result", "tool_post", "tool_failure"}
_STATUS_RANK: Mapping[AssociationStatus, int] = {
    "verified": 0,
    "partial": 1,
    "broken": 2,
    "conflict": 3,
}


@dataclass(frozen=True, slots=True)
class AdapterHealthReceipt:
    source: ObservationSource
    state: AdapterHealthState
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.source not in _SOURCES or self.state not in {
            "available",
            "degraded",
            "unavailable",
        }:
            raise ValueError("observer_adapter_receipt_invalid")
        if self.failure_code is not None and _SAFE_CODE.fullmatch(
            self.failure_code
        ) is None:
            raise ValueError("observer_adapter_receipt_invalid")


@dataclass(frozen=True, slots=True)
class MetricValue:
    value: int | float | None
    source: MetricSource

    def __post_init__(self) -> None:
        if self.source == "unknown":
            if self.value is not None:
                raise ValueError("observer_metric_invalid")
            return
        if (
            self.value is None
            or isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or self.value < 0
            or not math.isfinite(float(self.value))
        ):
            raise ValueError("observer_metric_invalid")


@dataclass(frozen=True, slots=True)
class EventIdentity:
    source: ObservationSource
    source_event_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class EventReference:
    identity: EventIdentity
    source_sequence: int
    variant: int = 0


@dataclass(frozen=True, slots=True)
class SourceEventStream:
    source: ObservationSource
    events: tuple[EventReference, ...]


@dataclass(frozen=True, slots=True)
class EventConflict:
    identity: EventIdentity
    events: tuple[EventReference, ...]
    reason_code: str = "observer_event_identity_conflict"


@dataclass(frozen=True, slots=True)
class DirectRelationship:
    kind: RelationshipKind
    parent: EventReference | None
    child: EventReference
    status: AssociationStatus
    proof_fields: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolLifecycle:
    tool_use_id: str
    tool_name: str | None
    agent_id: str | None
    parent_tool_use_id: str | None
    status: str
    association_status: AssociationStatus
    duration: MetricValue
    events: tuple[EventReference, ...]
    use_events: tuple[EventReference, ...]
    terminal_events: tuple[EventReference, ...]
    permission_events: tuple[EventReference, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubagentNode:
    node_id: str
    agent_id: str | None
    agent_type: str | None
    parent_tool_use_id: str | None
    status: str
    association_status: AssociationStatus
    tool_use_ids: tuple[str, ...]
    events: tuple[EventReference, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceAssociation:
    event: EventReference
    reference: ObservationEvidenceRef
    parent: ObservationEvidenceRef | None
    status: AssociationStatus
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CoverageDimensions:
    run_result: RunResultStatus
    observation: ObservationCoverageSummary
    local_evidence: LocalEvidenceStatus
    sdk_transcript: SDKTranscriptStatus


@dataclass(frozen=True, slots=True)
class ToolStatistics:
    tool_name: str
    calls: MetricValue
    ok: MetricValue
    needs_input: MetricValue
    errors: MetricValue
    total_duration_ms: MetricValue
    average_duration_ms: MetricValue
    p95_duration_ms: MetricValue


@dataclass(frozen=True, slots=True)
class RunMetrics:
    total_duration_ms: MetricValue
    agent_turns: MetricValue
    input_tokens: MetricValue
    output_tokens: MetricValue
    cache_creation_input_tokens: MetricValue
    cache_read_input_tokens: MetricValue
    total_cost_usd: MetricValue
    tool_calls: MetricValue
    subagents: MetricValue
    cache_hits: MetricValue
    render_executions: MetricValue
    pages_viewed: MetricValue
    image_count: MetricValue
    image_bytes: MetricValue
    permission_denials: MetricValue
    user_questions: MetricValue
    errors: MetricValue
    warnings: MetricValue
    retries: MetricValue
    tools: tuple[ToolStatistics, ...]


@dataclass(frozen=True, slots=True)
class RunCorrelation:
    run_id: str
    events: tuple[ObservationEvent, ...]
    streams: tuple[SourceEventStream, ...]
    event_conflicts: tuple[EventConflict, ...]
    relationships: tuple[DirectRelationship, ...]
    tools: tuple[ToolLifecycle, ...]
    subagents: tuple[SubagentNode, ...]
    evidence: tuple[EvidenceAssociation, ...]
    association_status: AssociationStatus
    dimensions: CoverageDimensions
    metrics: RunMetrics
    duplicate_events: int
    rejected_events: int


@dataclass(frozen=True, slots=True)
class _IndexedEvent:
    event: ObservationEvent
    ref: EventReference


def _fingerprint(event: ObservationEvent) -> str:
    return json.dumps(
        asdict(event),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _semantic_fingerprint(event: ObservationEvent) -> str:
    payload = asdict(event)
    payload.pop("source_sequence", None)
    payload.pop("observed_at", None)
    payload.pop("monotonic_offset_ms", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _identity(event: ObservationEvent) -> EventIdentity:
    return EventIdentity(event.source, event.source_event_id, event.kind)


def _worst(statuses: Iterable[AssociationStatus]) -> AssociationStatus:
    result: AssociationStatus = "verified"
    for status in statuses:
        if _STATUS_RANK[status] > _STATUS_RANK[result]:
            result = status
    return result


def _unknown() -> MetricValue:
    return MetricValue(None, "unknown")


def _reported(value: int | float) -> MetricValue:
    return MetricValue(value, "reported")


def _estimated(value: int | float) -> MetricValue:
    return MetricValue(value, "estimated")


def _attribute(event: ObservationEvent, key: str) -> object:
    for attribute in event.attributes:
        if attribute.key == key:
            return attribute.value
    return None


def _number_attribute(event: ObservationEvent, key: str) -> int | float | None:
    value = _attribute(event, key)
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
        and math.isfinite(float(value))
    ):
        return value
    return None


def _string_attribute(event: ObservationEvent, key: str) -> str | None:
    value = _attribute(event, key)
    return value if isinstance(value, str) else None


def _bool_attribute(event: ObservationEvent, key: str) -> bool | None:
    value = _attribute(event, key)
    return value if isinstance(value, bool) else None


def _index_events(
    run_id: str,
    events: Sequence[ObservationEvent],
) -> tuple[
    tuple[_IndexedEvent, ...],
    tuple[EventConflict, ...],
    tuple[SourceEventStream, ...],
    int,
    int,
]:
    accepted: list[ObservationEvent] = []
    rejected = 0
    duplicate_count = 0
    seen: set[ObservationEvent] = set()
    for candidate in events:
        if validate_observation_event(candidate) is not None or candidate.run_id != run_id:
            rejected += 1
            continue
        if candidate in seen:
            duplicate_count += 1
            continue
        seen.add(candidate)
        accepted.append(candidate)

    grouped: dict[EventIdentity, list[ObservationEvent]] = defaultdict(list)
    for event in accepted:
        grouped[_identity(event)].append(event)

    indexed: list[_IndexedEvent] = []
    conflicts: list[EventConflict] = []
    for identity in sorted(
        grouped,
        key=lambda item: (item.source, item.source_event_id, item.kind),
    ):
        semantic_groups: dict[str, list[ObservationEvent]] = defaultdict(list)
        for event in grouped[identity]:
            semantic_groups[_semantic_fingerprint(event)].append(event)
        variants: list[ObservationEvent] = []
        for semantic_key in sorted(semantic_groups):
            equivalent = sorted(semantic_groups[semantic_key], key=_fingerprint)
            variants.append(equivalent[0])
            duplicate_count += len(equivalent) - 1
        refs: list[EventReference] = []
        for variant, event in enumerate(variants):
            ref = EventReference(identity, event.source_sequence, variant)
            refs.append(ref)
            indexed.append(_IndexedEvent(event, ref))
        if len(variants) > 1:
            conflicts.append(EventConflict(identity, tuple(refs)))

    indexed.sort(
        key=lambda item: (
            item.event.source,
            item.event.source_sequence,
            item.event.monotonic_offset_ms,
            item.event.source_event_id,
            item.event.kind,
            item.ref.variant,
        )
    )
    streams = tuple(
        SourceEventStream(
            source,
            tuple(item.ref for item in indexed if item.event.source == source),
        )
        for source in _SOURCES
        if any(item.event.source == source for item in indexed)
    )
    return tuple(indexed), tuple(conflicts), streams, duplicate_count, rejected


def _refs(items: Iterable[_IndexedEvent]) -> tuple[EventReference, ...]:
    return tuple(
        item.ref
        for item in sorted(
            items,
            key=lambda item: (
                item.event.source_sequence,
                item.event.source,
                item.event.kind,
                item.ref.variant,
            ),
        )
    )


def _tool_duration(items: Sequence[_IndexedEvent]) -> MetricValue:
    reported = [
        item.event.duration_ms
        for item in items
        if item.event.kind in _TOOL_TERMINAL_KINDS
        and item.event.duration_ms is not None
    ]
    if reported:
        if len({round(value, 9) for value in reported}) == 1:
            return _reported(reported[0])
        return _unknown()
    hook_starts = [
        item.event.monotonic_offset_ms
        for item in items
        if item.event.kind == "tool_pre"
    ]
    sdk_starts = [
        item.event.monotonic_offset_ms
        for item in items
        if item.event.kind in _SDK_USE_KINDS
    ]
    starts = hook_starts or sdk_starts
    hook_finishes = [
        item.event.monotonic_offset_ms
        for item in items
        if item.event.kind in {"tool_post", "tool_failure"}
        or (
            item.event.kind == "permission_decision"
            and item.event.status == "deny"
        )
    ]
    sdk_finishes = [
        item.event.monotonic_offset_ms
        for item in items
        if item.event.kind == "tool_result"
    ]
    finishes = hook_finishes or sdk_finishes
    if starts and finishes:
        return _estimated(max(0.0, max(finishes) - min(starts)))
    return _unknown()


def _tool_status(items: Sequence[_IndexedEvent]) -> tuple[str, bool]:
    detailed = {
        item.event.status
        for item in items
        if item.event.kind in {"tool_post", "tool_failure"}
        and item.event.status is not None
    }
    denied = any(
        item.event.kind == "permission_decision" and item.event.status == "deny"
        for item in items
    )
    if denied:
        detailed.add("denied")
    if len(detailed) > 1:
        return "conflict", True
    if detailed:
        return next(iter(detailed)), False
    result_statuses = {
        item.event.status
        for item in items
        if item.event.kind == "tool_result" and item.event.status is not None
    }
    if len(result_statuses) > 1:
        return "conflict", True
    if result_statuses:
        return next(iter(result_statuses)), False
    if any(item.event.kind in _SDK_USE_KINDS for item in items):
        return "started", False
    return "unknown", False


def _build_tools(
    indexed: Sequence[_IndexedEvent],
    conflict_identities: set[EventIdentity],
) -> tuple[ToolLifecycle, ...]:
    groups: dict[str, list[_IndexedEvent]] = defaultdict(list)
    for item in indexed:
        if item.event.tool_use_id is not None:
            groups[item.event.tool_use_id].append(item)

    result: list[ToolLifecycle] = []
    for tool_use_id in sorted(groups):
        items = groups[tool_use_id]
        sdk_uses = [
            item
            for item in items
            if item.event.source == "sdk" and item.event.kind in _SDK_USE_KINDS
        ]
        terminals = [
            item
            for item in items
            if item.event.kind in _TOOL_TERMINAL_KINDS
            or (
                item.event.kind == "permission_decision"
                and item.event.status == "deny"
            )
        ]
        permissions = [
            item for item in items if item.event.kind == "permission_decision"
        ]
        names = {item.event.tool_name for item in items if item.event.tool_name}
        agents = {item.event.agent_id for item in items if item.event.agent_id}
        parents = {
            item.event.parent_tool_use_id
            for item in items
            if item.event.parent_tool_use_id
        }
        sessions = {item.event.session_id for item in items if item.event.session_id}
        reasons: set[str] = set()
        status: AssociationStatus = "verified"
        if not sdk_uses:
            status = "broken" if terminals else "partial"
            reasons.add("tool_use_missing")
        elif not terminals:
            status = "partial"
            reasons.add("tool_terminal_missing")
        if len(names) > 1:
            status = "conflict"
            reasons.add("tool_name_conflict")
        if len(agents) > 1:
            status = "conflict"
            reasons.add("tool_actor_conflict")
        if len(parents) > 1:
            status = "conflict"
            reasons.add("tool_parent_conflict")
        if len(sessions) > 1:
            status = "conflict"
            reasons.add("tool_session_conflict")
        if any(_identity(item.event) in conflict_identities for item in items):
            status = "conflict"
            reasons.add("tool_event_conflict")
        tool_status, status_conflict = _tool_status(items)
        if status_conflict:
            status = "conflict"
            reasons.add("tool_status_conflict")
        result.append(
            ToolLifecycle(
                tool_use_id=tool_use_id,
                tool_name=next(iter(names)) if len(names) == 1 else None,
                agent_id=next(iter(agents)) if len(agents) == 1 else None,
                parent_tool_use_id=(
                    next(iter(parents)) if len(parents) == 1 else None
                ),
                status=tool_status,
                association_status=status,
                duration=_tool_duration(items),
                events=_refs(items),
                use_events=_refs(sdk_uses),
                terminal_events=_refs(terminals),
                permission_events=_refs(permissions),
                reason_codes=tuple(sorted(reasons)),
            )
        )
    return tuple(result)


def _event_lookup(indexed: Sequence[_IndexedEvent]) -> dict[EventReference, ObservationEvent]:
    return {item.ref: item.event for item in indexed}


def _representative(refs: Sequence[EventReference]) -> EventReference | None:
    return refs[0] if refs else None


def _build_relationships(
    indexed: Sequence[_IndexedEvent],
    tools: Sequence[ToolLifecycle],
) -> tuple[DirectRelationship, ...]:
    lookup = _event_lookup(indexed)
    relationships: list[DirectRelationship] = []

    for tool in tools:
        use_ref = _representative(tool.use_events)
        for terminal_ref in tool.terminal_events:
            relationships.append(
                DirectRelationship(
                    "tool_result",
                    use_ref,
                    terminal_ref,
                    (
                        tool.association_status
                        if use_ref is not None
                        else "broken"
                    ),
                    ("tool_use_id",),
                    (() if use_ref is not None else ("tool_use_missing",)),
                )
            )

    agent_uses = {
        tool.tool_use_id: tool
        for tool in tools
        if tool.tool_name == "Agent" and tool.use_events
    }
    for item in indexed:
        parent_id = item.event.parent_tool_use_id
        if parent_id is None:
            continue
        parent_tool = agent_uses.get(parent_id)
        parent_ref = (
            _representative(parent_tool.use_events)
            if parent_tool is not None
            else None
        )
        relationships.append(
            DirectRelationship(
                "parent_child",
                parent_ref,
                item.ref,
                "verified" if parent_ref is not None else "broken",
                ("parent_tool_use_id", "tool_use_id"),
                (() if parent_ref is not None else ("parent_agent_missing",)),
            )
        )

    agent_events: dict[str, list[_IndexedEvent]] = defaultdict(list)
    for item in indexed:
        if item.event.agent_id is not None and item.event.kind in {
            "subagent_started",
            "subagent_stopped",
        }:
            agent_events[item.event.agent_id].append(item)
    for tool in tools:
        if tool.agent_id is None:
            continue
        target = _representative(_refs(agent_events.get(tool.agent_id, ())))
        for event_ref in tool.events:
            event = lookup[event_ref]
            if event.agent_id != tool.agent_id or event.kind not in {
                "tool_pre",
                "tool_post",
                "tool_failure",
                "permission_decision",
            }:
                continue
            relationships.append(
                DirectRelationship(
                    "tool_actor",
                    target,
                    event_ref,
                    "verified" if target is not None else "broken",
                    ("agent_id", "tool_use_id"),
                    (() if target is not None else ("subagent_actor_missing",)),
                )
            )
    return tuple(relationships)


def _build_subagents(
    indexed: Sequence[_IndexedEvent],
    tools: Sequence[ToolLifecycle],
) -> tuple[SubagentNode, ...]:
    lookup = _event_lookup(indexed)
    lifecycle_events: dict[str, list[_IndexedEvent]] = defaultdict(list)
    tool_events: dict[str, list[EventReference]] = defaultdict(list)
    for item in indexed:
        if item.event.agent_id is None:
            continue
        if item.event.kind in {"subagent_started", "subagent_stopped"}:
            lifecycle_events[item.event.agent_id].append(item)
        if item.event.tool_use_id is not None:
            tool_events[item.event.agent_id].append(item.ref)

    agent_invocations = {
        tool.tool_use_id: tool for tool in tools if tool.tool_name == "Agent"
    }
    matched_invocations: set[str] = set()
    nodes: list[SubagentNode] = []
    all_agent_ids = sorted(set(lifecycle_events) | set(tool_events))
    for agent_id in all_agent_ids:
        items = lifecycle_events.get(agent_id, [])
        refs = list(_refs(items)) + tool_events.get(agent_id, [])
        refs = list(dict.fromkeys(refs))
        starts = [item for item in items if item.event.kind == "subagent_started"]
        stops = [item for item in items if item.event.kind == "subagent_stopped"]
        related_events = [lookup[ref] for ref in refs]
        types = {
            event.agent_type
            for event in related_events
            if event.agent_type is not None
        }
        parents = {
            tool.parent_tool_use_id
            for tool in tools
            if tool.agent_id == agent_id and tool.parent_tool_use_id is not None
        }
        child_tool_ids = tuple(
            sorted(tool.tool_use_id for tool in tools if tool.agent_id == agent_id)
        )
        reasons: set[str] = set()
        status: AssociationStatus = "verified"
        if not starts and not stops:
            status = "broken"
            reasons.add("subagent_lifecycle_missing")
        elif not starts:
            status = "partial"
            reasons.add("subagent_start_missing")
        elif not stops:
            status = "partial"
            reasons.add("subagent_stop_missing")
        if len(types) > 1:
            status = "conflict"
            reasons.add("subagent_type_conflict")
        if len(parents) > 1:
            status = "conflict"
            reasons.add("subagent_parent_conflict")
        parent_id = next(iter(parents)) if len(parents) == 1 else None
        if parent_id is None:
            if status != "conflict":
                status = _worst((status, "partial"))
            reasons.add("subagent_parent_bridge_missing")
        elif parent_id not in agent_invocations:
            if status != "conflict":
                status = _worst((status, "broken"))
            reasons.add("parent_agent_missing")
        else:
            matched_invocations.add(parent_id)
        node_status = "finished" if stops else "started" if starts else "unknown"
        nodes.append(
            SubagentNode(
                node_id=f"agent:{agent_id}",
                agent_id=agent_id,
                agent_type=next(iter(types)) if len(types) == 1 else None,
                parent_tool_use_id=parent_id,
                status=node_status,
                association_status=status,
                tool_use_ids=child_tool_ids,
                events=tuple(refs),
                reason_codes=tuple(sorted(reasons)),
            )
        )

    for tool_use_id, tool in sorted(agent_invocations.items()):
        if tool_use_id in matched_invocations:
            continue
        events = [lookup[ref] for ref in tool.events]
        denied = any(
            event.kind == "permission_decision" and event.status == "deny"
            for event in events
        )
        types = {
            value
            for event in events
            if (value := _string_attribute(event, "subagent_type")) is not None
        }
        if denied and tool.use_events:
            invocation_status: AssociationStatus = (
                "conflict"
                if tool.association_status == "conflict"
                else "verified"
            )
            invocation_reasons = ("subagent_permission_denied",)
            node_status = "denied"
        else:
            invocation_status = _worst((tool.association_status, "partial"))
            invocation_reasons = ("subagent_actor_bridge_missing",)
            node_status = "unknown"
        nodes.append(
            SubagentNode(
                node_id=f"invocation:{tool_use_id}",
                agent_id=None,
                agent_type=next(iter(types)) if len(types) == 1 else None,
                parent_tool_use_id=tool_use_id,
                status=node_status,
                association_status=invocation_status,
                tool_use_ids=(),
                events=tool.events,
                reason_codes=invocation_reasons,
            )
        )
    return tuple(sorted(nodes, key=lambda node: node.node_id))


def _add_subagent_parent_relationships(
    relationships: Sequence[DirectRelationship],
    tools: Sequence[ToolLifecycle],
    subagents: Sequence[SubagentNode],
) -> tuple[DirectRelationship, ...]:
    tool_by_id = {tool.tool_use_id: tool for tool in tools}
    result = list(relationships)
    for node in subagents:
        child_ref = node.events[0] if node.events else None
        if child_ref is None:
            continue
        parent_tool = (
            tool_by_id.get(node.parent_tool_use_id)
            if node.parent_tool_use_id is not None
            else None
        )
        parent_ref = (
            _representative(parent_tool.use_events)
            if parent_tool is not None
            else None
        )
        if node.status == "denied":
            continue
        result.append(
            DirectRelationship(
                "subagent_parent",
                parent_ref,
                child_ref,
                node.association_status,
                ("parent_tool_use_id", "tool_use_id", "agent_id"),
                node.reason_codes,
            )
        )
    return tuple(result)


def _build_evidence(indexed: Sequence[_IndexedEvent]) -> tuple[EvidenceAssociation, ...]:
    occurrences: list[tuple[_IndexedEvent, ObservationEvidenceRef]] = []
    for item in indexed:
        occurrences.extend((item, reference) for reference in item.event.evidence_refs)
    documents = {
        reference.value
        for _, reference in occurrences
        if reference.kind == "document" and isinstance(reference.value, str)
    }
    renders = {
        reference.value
        for _, reference in occurrences
        if reference.kind == "render" and isinstance(reference.value, str)
    }
    scopes: dict[tuple[str, str], set[tuple[str | None, str | None]]] = defaultdict(set)
    for _, reference in occurrences:
        if reference.kind in {"object", "render", "evidence"} and isinstance(
            reference.value, str
        ):
            scopes[(reference.kind, reference.value)].add(
                (reference.document_sha256, reference.render_sha256)
            )

    result: list[EvidenceAssociation] = []
    for item, reference in occurrences:
        status: AssociationStatus = "verified"
        reasons: set[str] = set()
        parent: ObservationEvidenceRef | None = None
        if (
            reference.kind in {"object", "render", "evidence"}
            and isinstance(reference.value, str)
            and len(scopes[(reference.kind, reference.value)]) > 1
        ):
            status = "conflict"
            reasons.add("evidence_scope_conflict")
        elif reference.kind == "document":
            status = "verified"
        elif reference.kind in {"object", "render"}:
            if reference.document_sha256 is None:
                status = "partial"
                reasons.add("document_scope_missing")
            else:
                parent = ObservationEvidenceRef(
                    "document", reference.document_sha256
                )
                if reference.document_sha256 not in documents:
                    status = "broken"
                    reasons.add("document_target_missing")
        elif reference.kind == "evidence":
            if reference.render_sha256 is None:
                status = "partial"
                reasons.add("render_scope_missing")
            else:
                parent = ObservationEvidenceRef(
                    "render",
                    reference.render_sha256,
                    document_sha256=reference.document_sha256,
                )
                if reference.render_sha256 not in renders:
                    status = "broken"
                    reasons.add("render_target_missing")
        elif reference.kind == "page":
            if reference.render_sha256 is None:
                status = "partial"
                reasons.add("page_render_scope_missing")
            else:
                parent = ObservationEvidenceRef(
                    "render",
                    reference.render_sha256,
                    document_sha256=reference.document_sha256,
                )
                if reference.render_sha256 not in renders:
                    status = "broken"
                    reasons.add("render_target_missing")
        result.append(
            EvidenceAssociation(
                item.ref,
                reference,
                parent,
                status,
                tuple(sorted(reasons)),
            )
        )
    return tuple(result)


def _run_result(indexed: Sequence[_IndexedEvent]) -> tuple[RunResultStatus, bool]:
    values: set[RunResultStatus] = set()
    mapping: Mapping[str, RunResultStatus] = {
        "completed": "COMPLETED",
        "needs_input": "NEEDS_INPUT",
        "error": "ERROR",
    }
    for item in indexed:
        if item.event.kind not in {"run_finished", "conversion_report"}:
            continue
        event_status = item.event.status
        if event_status is not None and event_status in mapping:
            values.add(mapping[event_status])
    if len(values) == 1:
        return next(iter(values)), False
    if len(values) > 1:
        return "unknown", True
    return "unknown", False


def _transcript_status(
    indexed: Sequence[_IndexedEvent],
) -> tuple[SDKTranscriptStatus, bool]:
    allowed: set[SDKTranscriptStatus] = {
        "active",
        "cleaned",
        "residual",
        "cleanup_failed",
        "unknown",
    }
    values: set[SDKTranscriptStatus] = set()
    for item in indexed:
        value = _string_attribute(item.event, "transcript_status")
        if value in allowed:
            values.add(value)  # type: ignore[arg-type]
    if len(values) == 1:
        return next(iter(values)), False
    return "unknown", len(values) > 1


def _latest_observed_at(indexed: Sequence[_IndexedEvent]) -> str | None:
    if not indexed:
        return None
    return max(
        (item.event.observed_at for item in indexed),
        key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )


def _coverage(
    indexed: Sequence[_IndexedEvent],
    tools: Sequence[ToolLifecycle],
    subagents: Sequence[SubagentNode],
    conflicts: Sequence[EventConflict],
    evidence: Sequence[EvidenceAssociation],
    *,
    adapter_receipts: Sequence[AdapterHealthReceipt],
    sanitization_receipts: Sequence[SanitizationReceipt],
    rejected_events: int,
    terminal_conflict: bool,
    transcript_conflict: bool,
) -> ObservationCoverageSummary:
    missing: set[str] = set()
    failures: set[str] = set()
    receipt_groups: dict[ObservationSource, set[AdapterHealthState]] = defaultdict(set)
    for receipt in adapter_receipts:
        receipt_groups[receipt.source].add(receipt.state)
        if receipt.failure_code is not None:
            failures.add(receipt.failure_code)
    for source in _SOURCES:
        states = receipt_groups.get(source, set())
        if not states:
            missing.add(f"{source}_adapter_receipt")
        elif states != {"available"}:
            missing.add(f"{source}_adapter")
            if len(states) > 1:
                failures.add("observer_adapter_receipt_conflict")

    drops = [
        receipt for receipt in sanitization_receipts if receipt.status == "dropped"
    ]
    failures.update(receipt.reason_code for receipt in drops)
    starts = [item for item in indexed if item.event.kind == "run_started"]
    finishes = [item for item in indexed if item.event.kind == "run_finished"]
    reports = [item for item in indexed if item.event.kind == "conversion_report"]
    if not starts:
        missing.add("app_run_start")
    if not finishes:
        missing.add("app_run_terminal")
    if not reports:
        missing.add("report_event")
    for tool in tools:
        if tool.association_status != "verified":
            missing.update(
                reason for reason in tool.reason_codes if reason.endswith("_missing")
            )
            if tool.association_status == "conflict":
                failures.add("observer_association_conflict")
    for subagent in subagents:
        if subagent.status != "denied" and subagent.association_status != "verified":
            missing.update(
                reason
                for reason in subagent.reason_codes
                if reason.endswith("_missing")
            )
            if subagent.association_status == "conflict":
                failures.add("observer_association_conflict")
    if conflicts or terminal_conflict or transcript_conflict:
        failures.add("observer_association_conflict")
    if rejected_events:
        failures.add("observer_event_rejected")
    if any(item.status in {"broken", "conflict"} for item in evidence):
        failures.add("observer_evidence_association_failed")

    granular = any(item.event.kind != "conversion_report" for item in indexed)
    if not indexed or not granular:
        state: Literal["complete", "degraded", "unavailable"] = "unavailable"
    elif missing or failures or drops:
        state = "degraded"
    else:
        state = "complete"
    drop_count = len(drops) if adapter_receipts else None
    return ObservationCoverageSummary(
        state=state,
        events_persisted=None,
        events_dropped=drop_count,
        missing_sources=tuple(sorted(missing)),
        last_observed_at=_latest_observed_at(indexed),
        failure_codes=tuple(sorted(failures)),
    )


def _sum_reported(
    indexed: Sequence[_IndexedEvent],
    *,
    kind: str,
    attribute: str,
) -> MetricValue:
    values = [
        value
        for item in indexed
        if item.event.kind == kind
        and (value := _number_attribute(item.event, attribute)) is not None
    ]
    return _reported(sum(values)) if values else _unknown()


def _single_reported_duration(indexed: Sequence[_IndexedEvent]) -> MetricValue:
    values = [
        item.event.duration_ms
        for item in indexed
        if item.event.kind == "run_finished" and item.event.duration_ms is not None
    ]
    if not values:
        return _unknown()
    if len({round(value, 9) for value in values}) > 1:
        return _unknown()
    return _reported(values[0])


def _tool_statistics(
    tools: Sequence[ToolLifecycle],
    *,
    complete: bool,
) -> tuple[ToolStatistics, ...]:
    groups: dict[str, list[ToolLifecycle]] = defaultdict(list)
    for tool in tools:
        if tool.tool_name is not None:
            groups[tool.tool_name].append(tool)
    result: list[ToolStatistics] = []
    for name in sorted(groups):
        items = groups[name]
        if complete:
            calls = _estimated(len(items))
            ok = _estimated(sum(item.status == "ok" for item in items))
            needs_input = _estimated(
                sum(item.status == "needs_input" for item in items)
            )
            errors = _estimated(
                sum(item.status in {"error", "denied", "conflict"} for item in items)
            )
        else:
            calls = ok = needs_input = errors = _unknown()
        durations = sorted(
            float(item.duration.value)
            for item in items
            if item.duration.value is not None
        )
        if complete and len(durations) == len(items) and durations:
            total = sum(durations)
            p95_index = max(0, math.ceil(len(durations) * 0.95) - 1)
            total_duration = _estimated(total)
            average_duration = _estimated(total / len(durations))
            p95_duration = _estimated(durations[p95_index])
        else:
            total_duration = average_duration = p95_duration = _unknown()
        result.append(
            ToolStatistics(
                name,
                calls,
                ok,
                needs_input,
                errors,
                total_duration,
                average_duration,
                p95_duration,
            )
        )
    return tuple(result)


def _reported_warning_count(indexed: Sequence[_IndexedEvent]) -> MetricValue:
    values = [
        value
        for item in indexed
        if item.event.kind == "conversion_report"
        and (value := _number_attribute(item.event, "warning_count")) is not None
    ]
    if not values:
        return _unknown()
    if len(set(values)) > 1:
        return _unknown()
    return _reported(values[0])


def _metrics(
    indexed: Sequence[_IndexedEvent],
    tools: Sequence[ToolLifecycle],
    subagents: Sequence[SubagentNode],
    coverage: ObservationCoverageSummary,
) -> RunMetrics:
    complete = coverage.state == "complete"
    tool_events = [item.event for item in indexed if item.event.kind == "tool_post"]
    render_events = [
        event
        for event in tool_events
        if event.tool_name == "mcp__docfit__docx_render"
    ]
    render_cache_values = [
        cache_value
        for event in render_events
        if (cache_value := _bool_attribute(event, "cache_hit")) is not None
    ]
    render_execution_known = all(
        _bool_attribute(event, "cache_hit") is not None for event in render_events
    )
    render_executions = sum(
        _bool_attribute(event, "cache_hit") is False for event in render_events
    )
    page_refs = {
        (reference.render_sha256, reference.value)
        for item in indexed
        for reference in item.event.evidence_refs
        if reference.kind == "page" and reference.render_sha256 is not None
    }
    unscoped_pages = any(
        reference.kind == "page" and reference.render_sha256 is None
        for item in indexed
        for reference in item.event.evidence_refs
    )
    visual_events = [
        event
        for event in tool_events
        if event.tool_name == "mcp__docfit__docx_visual_review"
    ]
    image_counts = [
        image_count
        for event in visual_events
        if (image_count := _number_attribute(event, "image_count")) is not None
    ]
    image_bytes = [
        byte_count
        for event in visual_events
        if (byte_count := _number_attribute(event, "image_bytes")) is not None
    ]
    permission_denials = sum(
        item.event.kind == "permission_decision" and item.event.status == "deny"
        for item in indexed
    )
    user_questions = sum(tool.tool_name == "AskUserQuestion" for tool in tools)
    errors = sum(tool.status in {"error", "denied", "conflict"} for tool in tools)
    backend_attempts = sum(item.event.kind == "backend_started" for item in indexed)
    if not complete:
        derived_tool_calls = derived_subagents = derived_cache_hits = _unknown()
        derived_permissions = derived_questions = derived_errors = _unknown()
        derived_retries = _unknown()
        derived_renders = derived_pages = derived_image_count = derived_image_bytes = _unknown()
    else:
        derived_tool_calls = _estimated(len(tools))
        derived_subagents = _estimated(len(subagents))
        derived_cache_hits = (
            _estimated(sum(render_cache_values))
            if len(render_cache_values) == len(render_events)
            else _unknown()
        )
        derived_permissions = _estimated(permission_denials)
        derived_questions = _estimated(user_questions)
        derived_errors = _estimated(errors)
        derived_retries = _estimated(max(0, backend_attempts - 1))
        derived_renders = (
            _estimated(render_executions) if render_execution_known else _unknown()
        )
        if page_refs:
            derived_pages = _estimated(len(page_refs))
        elif unscoped_pages:
            derived_pages = _unknown()
        else:
            derived_pages = _estimated(0)
        derived_image_count = (
            _estimated(sum(image_counts))
            if len(image_counts) == len(visual_events)
            else _unknown()
        )
        derived_image_bytes = (
            _estimated(sum(image_bytes))
            if len(image_bytes) == len(visual_events)
            else _unknown()
        )
    return RunMetrics(
        total_duration_ms=_single_reported_duration(indexed),
        agent_turns=_sum_reported(indexed, kind="sdk_result", attribute="num_turns"),
        input_tokens=_sum_reported(indexed, kind="sdk_result", attribute="input_tokens"),
        output_tokens=_sum_reported(indexed, kind="sdk_result", attribute="output_tokens"),
        cache_creation_input_tokens=_sum_reported(
            indexed,
            kind="sdk_result",
            attribute="cache_creation_input_tokens",
        ),
        cache_read_input_tokens=_sum_reported(
            indexed,
            kind="sdk_result",
            attribute="cache_read_input_tokens",
        ),
        total_cost_usd=_sum_reported(
            indexed, kind="sdk_result", attribute="total_cost_usd"
        ),
        tool_calls=derived_tool_calls,
        subagents=derived_subagents,
        cache_hits=derived_cache_hits,
        render_executions=derived_renders,
        pages_viewed=derived_pages,
        image_count=derived_image_count,
        image_bytes=derived_image_bytes,
        permission_denials=derived_permissions,
        user_questions=derived_questions,
        errors=derived_errors,
        warnings=_reported_warning_count(indexed),
        retries=derived_retries,
        tools=_tool_statistics(tools, complete=complete),
    )


def correlate_observation_run(
    run_id: str,
    events: Sequence[ObservationEvent],
    *,
    adapter_receipts: Sequence[AdapterHealthReceipt] = (),
    sanitization_receipts: Sequence[SanitizationReceipt] = (),
    local_evidence: LocalEvidenceStatus = "unmounted",
) -> RunCorrelation:
    """Build a deterministic run projection using direct IDs and refs only."""

    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("observer_run_id_invalid")
    if local_evidence not in {
        "unmounted",
        "available",
        "stale",
        "missing",
        "unauthorized",
        "conflict",
    }:
        raise ValueError("observer_evidence_state_invalid")
    indexed, conflicts, streams, duplicates, rejected = _index_events(run_id, events)
    conflict_identities = {conflict.identity for conflict in conflicts}
    tools = _build_tools(indexed, conflict_identities)
    relationships = _build_relationships(indexed, tools)
    subagents = _build_subagents(indexed, tools)
    relationships = _add_subagent_parent_relationships(relationships, tools, subagents)
    evidence = _build_evidence(indexed)
    run_result, terminal_conflict = _run_result(indexed)
    transcript, transcript_conflict = _transcript_status(indexed)
    coverage = _coverage(
        indexed,
        tools,
        subagents,
        conflicts,
        evidence,
        adapter_receipts=adapter_receipts,
        sanitization_receipts=sanitization_receipts,
        rejected_events=rejected,
        terminal_conflict=terminal_conflict,
        transcript_conflict=transcript_conflict,
    )
    relationship_statuses = [relationship.status for relationship in relationships]
    association_inputs: list[AssociationStatus] = [
        *(tool.association_status for tool in tools),
        *(subagent.association_status for subagent in subagents),
        *(item.status for item in evidence if item.reference.kind != "document"),
        *relationship_statuses,
    ]
    association_inputs.extend("conflict" for _ in conflicts)
    association_inputs.extend("conflict" for _ in range(rejected))
    if terminal_conflict or transcript_conflict:
        association_inputs.append("conflict")
    association = _worst(association_inputs)
    return RunCorrelation(
        run_id=run_id,
        events=tuple(item.event for item in indexed),
        streams=streams,
        event_conflicts=conflicts,
        relationships=relationships,
        tools=tools,
        subagents=subagents,
        evidence=evidence,
        association_status=association,
        dimensions=CoverageDimensions(
            run_result,
            coverage,
            local_evidence,
            transcript,
        ),
        metrics=_metrics(indexed, tools, subagents, coverage),
        duplicate_events=duplicates,
        rejected_events=rejected,
    )
