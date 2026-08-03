from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from docfit.observability.correlation import (
    AdapterHealthReceipt,
    correlate_observation_run,
)
from docfit.observability.events import (
    ObservationActor,
    ObservationAttribute,
    ObservationError,
    ObservationEvent,
    ObservationEvidenceRef,
    ObservationSource,
    SanitizationReceipt,
)

RUN_ID = "run_0123456789abcdef0123456789abcdef"
DOC_A = "a" * 64
DOC_B = "b" * 64
RENDER_A = "c" * 64
RENDER_B = "d" * 64
OBJECT_A = "obj-" + ("1" * 24)
BASE_TIME = datetime(2026, 8, 3, 8, 31, tzinfo=UTC)


def _event(
    sequence: int,
    *,
    source: str,
    kind: str,
    source_event_id: str,
    status: str | None = None,
    tool_name: str | None = None,
    tool_use_id: str | None = None,
    agent_id: str | None = None,
    agent_type: str | None = None,
    parent_tool_use_id: str | None = None,
    duration_ms: float | None = None,
    attributes: tuple[ObservationAttribute, ...] = (),
    evidence: tuple[ObservationEvidenceRef, ...] = (),
    error: ObservationError | None = None,
) -> ObservationEvent:
    actor = (
        ObservationActor("subagent", agent_id, agent_type)
        if agent_id is not None or parent_tool_use_id is not None
        else ObservationActor("app" if source in {"app", "report"} else "main")
    )
    return ObservationEvent(
        schema_version=1,
        run_id=RUN_ID,
        source_event_id=source_event_id,
        source_sequence=sequence,
        observed_at=(BASE_TIME + timedelta(milliseconds=sequence)).isoformat(),
        monotonic_offset_ms=float(sequence * 10),
        source=source,  # type: ignore[arg-type]
        kind=kind,
        priority="P0" if kind.endswith("finished") else "P1",
        actor=actor,
        summary_code=f"{kind}_observed",
        status=status,
        session_id="session-1" if source in {"sdk", "tool"} else None,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        agent_id=agent_id,
        agent_type=agent_type,
        parent_tool_use_id=parent_tool_use_id,
        duration_ms=duration_ms,
        attributes=attributes,
        evidence_refs=evidence,
        error=error,
    )


def _healthy_adapters() -> tuple[AdapterHealthReceipt, ...]:
    sources: tuple[ObservationSource, ...] = (
        "app",
        "sdk",
        "permission",
        "tool",
        "report",
    )
    return tuple(
        AdapterHealthReceipt(source, "available")
        for source in sources
    )


def _run_boundaries(*, status: str = "completed") -> list[ObservationEvent]:
    return [
        _event(
            1,
            source="app",
            kind="run_started",
            source_event_id="run-start",
            status="started",
        ),
        _event(
            90,
            source="report",
            kind="conversion_report",
            source_event_id="report-1",
            status=status,
            attributes=(
                ObservationAttribute("transcript_status", "cleaned"),
                ObservationAttribute("warning_count", 2),
            ),
            evidence=(ObservationEvidenceRef("document", DOC_A),),
        ),
        _event(
            91,
            source="app",
            kind="run_finished",
            source_event_id="run-finish",
            status=status,
            duration_ms=910.0,
        ),
    ]


def _tool_call(
    *,
    start_sequence: int,
    tool_use_id: str,
    tool_name: str,
    parent_tool_use_id: str | None = None,
    agent_id: str | None = None,
    agent_type: str | None = None,
    result_attributes: tuple[ObservationAttribute, ...] = (),
    evidence: tuple[ObservationEvidenceRef, ...] = (),
) -> list[ObservationEvent]:
    return [
        _event(
            start_sequence,
            source="sdk",
            kind=("subagent_use" if tool_name == "Agent" else "tool_use"),
            source_event_id=tool_use_id,
            status="started",
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            parent_tool_use_id=parent_tool_use_id,
        ),
        _event(
            start_sequence + 1,
            source="tool",
            kind="tool_pre",
            source_event_id=tool_use_id,
            status="started",
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            agent_id=agent_id,
            agent_type=agent_type,
        ),
        _event(
            start_sequence + 3,
            source="tool",
            kind="tool_post",
            source_event_id=tool_use_id,
            status="ok",
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            agent_id=agent_id,
            agent_type=agent_type,
            attributes=result_attributes,
            evidence=evidence,
        ),
        _event(
            start_sequence + 4,
            source="sdk",
            kind="tool_result",
            source_event_id=tool_use_id,
            status="ok",
            tool_use_id=tool_use_id,
            parent_tool_use_id=parent_tool_use_id,
        ),
    ]


def test_complete_run_keeps_zero_counts_known_without_inventing_activity() -> None:
    correlation = correlate_observation_run(
        RUN_ID,
        _run_boundaries(),
        adapter_receipts=_healthy_adapters(),
    )

    assert correlation.association_status == "verified"
    assert correlation.dimensions.run_result == "COMPLETED"
    assert correlation.dimensions.observation.state == "complete"
    assert correlation.dimensions.observation.events_dropped == 0
    assert correlation.dimensions.local_evidence == "unmounted"
    assert correlation.dimensions.sdk_transcript == "cleaned"
    assert correlation.metrics.tool_calls.value == 0
    assert correlation.metrics.tool_calls.source == "estimated"
    assert correlation.metrics.subagents.value == 0
    assert correlation.metrics.warnings.value == 2
    assert correlation.metrics.warnings.source == "reported"


def test_tool_lifecycle_uses_direct_id_and_derives_safe_metrics() -> None:
    render_evidence = (
        ObservationEvidenceRef("document", DOC_A),
        ObservationEvidenceRef("render", RENDER_A, document_sha256=DOC_A),
    )
    events = [
        *_run_boundaries(),
        *_tool_call(
            start_sequence=10,
            tool_use_id="render-1",
            tool_name="mcp__docfit__docx_render",
            result_attributes=(
                ObservationAttribute("provider", "adobe_pdf_services"),
                ObservationAttribute("cache_hit", False),
            ),
            evidence=render_evidence,
        ),
        *_tool_call(
            start_sequence=20,
            tool_use_id="review-1",
            tool_name="mcp__docfit__docx_visual_review",
            result_attributes=(
                ObservationAttribute("image_count", 2),
                ObservationAttribute("image_bytes", 100),
            ),
            evidence=(
                ObservationEvidenceRef("document", DOC_A),
                ObservationEvidenceRef("render", RENDER_A, document_sha256=DOC_A),
                ObservationEvidenceRef(
                    "page",
                    1,
                    document_sha256=DOC_A,
                    render_sha256=RENDER_A,
                ),
            ),
        ),
        _event(
            80,
            source="sdk",
            kind="sdk_result",
            source_event_id="sdk-result-1",
            status="ok",
            attributes=(
                ObservationAttribute("num_turns", 3),
                ObservationAttribute("input_tokens", 200),
                ObservationAttribute("output_tokens", 50),
                ObservationAttribute("total_cost_usd", 0.25),
            ),
        ),
    ]

    correlation = correlate_observation_run(
        RUN_ID, events, adapter_receipts=_healthy_adapters()
    )

    assert correlation.dimensions.observation.state == "complete"
    assert {tool.tool_use_id for tool in correlation.tools} == {"render-1", "review-1"}
    assert all(tool.association_status == "verified" for tool in correlation.tools)
    assert all(
        relationship.proof_fields == ("tool_use_id",)
        for relationship in correlation.relationships
        if relationship.kind == "tool_result"
    )
    assert correlation.metrics.tool_calls.value == 2
    assert correlation.metrics.adobe_api_calls.value == 1
    assert correlation.metrics.cache_hits.value == 0
    assert correlation.metrics.pages_viewed.value == 1
    assert correlation.metrics.image_count.value == 2
    assert correlation.metrics.image_bytes.value == 100
    assert correlation.metrics.agent_turns.value == 3
    assert correlation.metrics.input_tokens.value == 200
    assert correlation.metrics.total_cost_usd.value == 0.25
    render_stats = next(
        item
        for item in correlation.metrics.tools
        if item.tool_name == "mcp__docfit__docx_render"
    )
    assert render_stats.calls.value == 1
    assert render_stats.average_duration_ms.value == 20.0
    assert render_stats.average_duration_ms.source == "estimated"


def test_two_interleaved_subagents_keep_exact_parent_and_actor_bridges() -> None:
    events = _run_boundaries()
    for offset, parent, child, agent in (
        (10, "agent-call-1", "inspect-1", "agent-1"),
        (30, "agent-call-2", "inspect-2", "agent-2"),
    ):
        events.extend(
            _tool_call(
                start_sequence=offset,
                tool_use_id=parent,
                tool_name="Agent",
            )
        )
        events.extend(
            [
                _event(
                    offset + 5,
                    source="sdk",
                    kind="subagent_started",
                    source_event_id=agent,
                    status="started",
                    agent_id=agent,
                    agent_type="docfit-unit-analyst",
                ),
                _event(
                    offset + 6,
                    source="sdk",
                    kind="assistant_message",
                    source_event_id=f"message-{agent}",
                    status="ok",
                    parent_tool_use_id=parent,
                ),
                *_tool_call(
                    start_sequence=offset + 7,
                    tool_use_id=child,
                    tool_name="mcp__docfit__docx_inspect",
                    parent_tool_use_id=parent,
                    agent_id=agent,
                    agent_type="docfit-unit-analyst",
                ),
                _event(
                    offset + 20,
                    source="sdk",
                    kind="subagent_stopped",
                    source_event_id=agent,
                    status="finished",
                    agent_id=agent,
                    agent_type="docfit-unit-analyst",
                ),
            ]
        )

    correlation = correlate_observation_run(
        RUN_ID, events, adapter_receipts=_healthy_adapters()
    )

    assert correlation.dimensions.observation.state == "complete"
    assert len(correlation.subagents) == 2
    assert {
        (node.agent_id, node.parent_tool_use_id, node.tool_use_ids)
        for node in correlation.subagents
    } == {
        ("agent-1", "agent-call-1", ("inspect-1",)),
        ("agent-2", "agent-call-2", ("inspect-2",)),
    }
    assert all(node.association_status == "verified" for node in correlation.subagents)
    parent_edges = [
        edge for edge in correlation.relationships if edge.kind == "subagent_parent"
    ]
    assert len(parent_edges) == 2
    assert all(edge.status == "verified" for edge in parent_edges)
    assert correlation.metrics.subagents.value == 2


def test_duplicates_are_idempotent_and_cross_source_order_does_not_create_edges() -> None:
    boundaries = _run_boundaries()
    semantic_duplicate = replace(
        boundaries[0],
        source_sequence=2,
        observed_at=(BASE_TIME + timedelta(milliseconds=2)).isoformat(),
        monotonic_offset_ms=20.0,
    )
    first = correlate_observation_run(
        RUN_ID,
        [*boundaries, boundaries[0], semantic_duplicate],
        adapter_receipts=_healthy_adapters(),
    )
    second = correlate_observation_run(
        RUN_ID,
        list(reversed([*boundaries, boundaries[0], semantic_duplicate])),
        adapter_receipts=tuple(reversed(_healthy_adapters())),
    )

    assert first == second
    assert first.duplicate_events == 2
    assert first.relationships == ()
    assert all(
        tuple(ref.source_sequence for ref in stream.events)
        == tuple(sorted(ref.source_sequence for ref in stream.events))
        for stream in first.streams
    )


def test_conflicting_direct_sources_are_retained_and_never_silently_merged() -> None:
    use = _tool_call(
        start_sequence=10,
        tool_use_id="tool-conflict",
        tool_name="mcp__docfit__docx_inspect",
    )[0]
    post = _tool_call(
        start_sequence=10,
        tool_use_id="tool-conflict",
        tool_name="mcp__docfit__docx_inspect",
    )[2]
    conflicting_post = replace(
        post,
        status="error",
        error=ObservationError("postcondition_failed", "tool"),
    )
    conflicting_name = replace(
        use,
        tool_name="mcp__docfit__docx_validate",
        source_sequence=12,
    )
    events = [*_run_boundaries(), use, conflicting_name, post, conflicting_post]

    correlation = correlate_observation_run(
        RUN_ID, events, adapter_receipts=_healthy_adapters()
    )

    tool = correlation.tools[0]
    assert tool.association_status == "conflict"
    assert tool.tool_name is None
    assert {"tool_name_conflict", "tool_status_conflict"}.issubset(tool.reason_codes)
    assert correlation.event_conflicts
    assert correlation.association_status == "conflict"
    assert correlation.dimensions.observation.state == "degraded"
    assert "tool_name_conflict" not in (
        correlation.dimensions.observation.missing_sources
    )
    assert "observer_association_conflict" in (
        correlation.dimensions.observation.failure_codes
    )
    assert correlation.metrics.tool_calls.value is None
    assert correlation.metrics.tool_calls.source == "unknown"


def test_missing_targets_are_broken_while_open_lifecycles_are_partial() -> None:
    orphan_result = _event(
        10,
        source="sdk",
        kind="tool_result",
        source_event_id="orphan-tool",
        status="ok",
        tool_use_id="orphan-tool",
    )
    child_without_parent = _event(
        11,
        source="sdk",
        kind="assistant_message",
        source_event_id="child-message",
        status="ok",
        parent_tool_use_id="missing-agent-call",
    )
    open_subagent = _event(
        12,
        source="sdk",
        kind="subagent_started",
        source_event_id="agent-open",
        status="started",
        agent_id="agent-open",
        agent_type="docfit-unit-analyst",
    )

    correlation = correlate_observation_run(
        RUN_ID,
        [*_run_boundaries(), orphan_result, child_without_parent, open_subagent],
        adapter_receipts=_healthy_adapters(),
    )

    assert correlation.tools[0].association_status == "broken"
    parent_edge = next(
        edge for edge in correlation.relationships if edge.kind == "parent_child"
    )
    assert parent_edge.status == "broken"
    assert parent_edge.parent is None
    assert correlation.subagents[0].association_status == "partial"
    assert "subagent_stop_missing" in correlation.subagents[0].reason_codes
    assert correlation.association_status == "broken"
    assert correlation.dimensions.observation.state == "degraded"


def test_evidence_uses_hash_scope_and_same_page_number_never_creates_a_cross_render_link() -> None:
    evidence_event = _event(
        10,
        source="tool",
        kind="tool_post",
        source_event_id="evidence-tool",
        status="ok",
        tool_name="mcp__docfit__docx_visual_review",
        tool_use_id="evidence-tool",
        evidence=(
            ObservationEvidenceRef("document", DOC_A),
            ObservationEvidenceRef("document", DOC_B),
            ObservationEvidenceRef("object", OBJECT_A, document_sha256=DOC_A),
            ObservationEvidenceRef("object", OBJECT_A, document_sha256=DOC_B),
            ObservationEvidenceRef("render", RENDER_A, document_sha256=DOC_A),
            ObservationEvidenceRef("render", RENDER_B, document_sha256=DOC_A),
            ObservationEvidenceRef(
                "page", 1, document_sha256=DOC_A, render_sha256=RENDER_A
            ),
            ObservationEvidenceRef(
                "page", 1, document_sha256=DOC_A, render_sha256=RENDER_B
            ),
            ObservationEvidenceRef(
                "evidence",
                "evidence-missing",
                document_sha256=DOC_A,
                render_sha256="e" * 64,
            ),
        ),
    )

    correlation = correlate_observation_run(
        RUN_ID,
        [*_run_boundaries(), evidence_event],
        adapter_receipts=_healthy_adapters(),
    )

    object_links = [
        item for item in correlation.evidence if item.reference.kind == "object"
    ]
    page_links = [
        item for item in correlation.evidence if item.reference.kind == "page"
    ]
    missing_link = next(
        item
        for item in correlation.evidence
        if item.reference.kind == "evidence"
    )
    assert all(item.status == "conflict" for item in object_links)
    assert all(item.status == "verified" for item in page_links)
    assert {item.parent.value for item in page_links if item.parent} == {
        RENDER_A,
        RENDER_B,
    }
    assert missing_link.status == "broken"
    assert correlation.association_status == "conflict"


def test_dropped_event_degrades_coverage_but_reported_usage_remains_reported() -> None:
    sdk_result = _event(
        50,
        source="sdk",
        kind="sdk_result",
        source_event_id="sdk-result",
        status="ok",
        attributes=(
            ObservationAttribute("num_turns", 4),
            ObservationAttribute("input_tokens", 300),
        ),
    )
    correlation = correlate_observation_run(
        RUN_ID,
        [*_run_boundaries(), sdk_result],
        adapter_receipts=_healthy_adapters(),
        sanitization_receipts=(
            SanitizationReceipt(
                "dropped", "observer_projector_deadline", 10.5
            ),
        ),
    )

    assert correlation.dimensions.observation.state == "degraded"
    assert correlation.dimensions.observation.events_dropped == 1
    assert "observer_projector_deadline" in (
        correlation.dimensions.observation.failure_codes
    )
    assert correlation.metrics.agent_turns.value == 4
    assert correlation.metrics.agent_turns.source == "reported"
    assert correlation.metrics.input_tokens.value == 300
    assert correlation.metrics.tool_calls.value is None
    assert correlation.metrics.subagents.value is None


def test_incomplete_metric_fields_stay_unknown_while_scoped_pages_remain_countable() -> None:
    render_call = _tool_call(
        start_sequence=10,
        tool_use_id="render-incomplete",
        tool_name="mcp__docfit__docx_render",
        result_attributes=(
            ObservationAttribute("provider", "adobe_pdf_services"),
        ),
    )
    review_call = _tool_call(
        start_sequence=20,
        tool_use_id="review-scoped",
        tool_name="mcp__docfit__docx_visual_review",
        result_attributes=(
            ObservationAttribute("image_count", 1),
            ObservationAttribute("image_bytes", 10),
        ),
        evidence=(
            ObservationEvidenceRef("document", DOC_A),
            ObservationEvidenceRef("render", RENDER_A, document_sha256=DOC_A),
            ObservationEvidenceRef(
                "page", 1, document_sha256=DOC_A, render_sha256=RENDER_A
            ),
        ),
    )
    review_call[0] = replace(
        review_call[0],
        evidence_refs=(ObservationEvidenceRef("page", 1),),
    )

    correlation = correlate_observation_run(
        RUN_ID,
        [*_run_boundaries(), *render_call, *review_call],
        adapter_receipts=_healthy_adapters(),
    )

    assert correlation.dimensions.observation.state == "complete"
    assert correlation.metrics.cache_hits.value is None
    assert correlation.metrics.cache_hits.source == "unknown"
    assert correlation.metrics.adobe_api_calls.value is None
    assert correlation.metrics.pages_viewed.value == 1


def test_denied_unknown_subagent_is_located_by_tool_use_id_without_fake_actor() -> None:
    agent_use = _event(
        10,
        source="sdk",
        kind="subagent_use",
        source_event_id="agent-denied",
        status="started",
        tool_name="Agent",
        tool_use_id="agent-denied",
    )
    denial = _event(
        11,
        source="permission",
        kind="permission_decision",
        source_event_id="agent-denied",
        status="deny",
        tool_name="Agent",
        tool_use_id="agent-denied",
        attributes=(
            ObservationAttribute("reason_code", "subagent_type_denied"),
        ),
    )

    correlation = correlate_observation_run(
        RUN_ID,
        [*_run_boundaries(), agent_use, denial],
        adapter_receipts=_healthy_adapters(),
    )

    assert correlation.dimensions.observation.state == "complete"
    assert correlation.tools[0].status == "denied"
    assert correlation.tools[0].association_status == "verified"
    assert len(correlation.subagents) == 1
    assert correlation.subagents[0].node_id == "invocation:agent-denied"
    assert correlation.subagents[0].agent_id is None
    assert correlation.subagents[0].status == "denied"
    assert correlation.subagents[0].association_status == "verified"
    assert correlation.metrics.permission_denials.value == 1
    assert correlation.metrics.errors.value == 1


def test_missing_adapter_receipts_make_counts_unknown_not_zero() -> None:
    correlation = correlate_observation_run(RUN_ID, _run_boundaries())

    assert correlation.dimensions.observation.state == "degraded"
    assert correlation.dimensions.observation.events_dropped is None
    assert "tool_adapter_receipt" in correlation.dimensions.observation.missing_sources
    assert correlation.metrics.tool_calls.value is None
    assert correlation.metrics.subagents.value is None
