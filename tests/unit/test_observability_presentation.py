from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jinja2 import Environment, PackageLoader, select_autoescape

from docfit.observability.events import (
    ObservationActor,
    ObservationAttribute,
    ObservationEvent,
)
from docfit.observability.presentation import build_run_presentation
from docfit.observability.storage import StoredObservationRun

RUN_ID = "run_0123456789abcdef0123456789abcdef"
BASE_TIME = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def _event(
    sequence: int,
    *,
    source: str,
    kind: str,
    source_event_id: str,
    status: str,
    tool_name: str | None = None,
    tool_use_id: str | None = None,
    parent_tool_use_id: str | None = None,
    agent_id: str | None = None,
    agent_type: str | None = None,
    attributes: tuple[ObservationAttribute, ...] = (),
) -> ObservationEvent:
    actor = (
        ObservationActor("subagent", agent_id, agent_type)
        if agent_id is not None
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
        priority="P0" if kind in {"run_started", "run_finished"} else "P1",
        actor=actor,
        summary_code=f"{kind}_observed",
        status=status,
        session_id="session-1" if source in {"sdk", "tool"} else None,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        parent_tool_use_id=parent_tool_use_id,
        agent_id=agent_id,
        agent_type=agent_type,
        duration_ms=10.0 if kind == "tool_post" else None,
        attributes=attributes,
    )


def test_presentation_keeps_direct_main_tool_and_subagent_relationships() -> None:
    events = (
        _event(
            1,
            source="app",
            kind="run_started",
            source_event_id="run-start",
            status="started",
        ),
        _event(
            10,
            source="sdk",
            kind="subagent_use",
            source_event_id="agent-call",
            status="started",
            tool_name="Agent",
            tool_use_id="agent-call",
        ),
        _event(
            11,
            source="tool",
            kind="tool_pre",
            source_event_id="agent-call",
            status="started",
            tool_name="Agent",
            tool_use_id="agent-call",
        ),
        _event(
            12,
            source="tool",
            kind="tool_post",
            source_event_id="agent-call",
            status="ok",
            tool_name="Agent",
            tool_use_id="agent-call",
        ),
        _event(
            13,
            source="sdk",
            kind="tool_result",
            source_event_id="agent-call",
            status="ok",
            tool_use_id="agent-call",
        ),
        _event(
            14,
            source="sdk",
            kind="subagent_started",
            source_event_id="agent-1",
            status="started",
            agent_id="agent-1",
            agent_type="docfit-unit-analyst",
        ),
        _event(
            15,
            source="sdk",
            kind="assistant_message",
            source_event_id="agent-message",
            status="ok",
            parent_tool_use_id="agent-call",
        ),
        _event(
            16,
            source="sdk",
            kind="tool_use",
            source_event_id="inspect-1",
            status="started",
            tool_name="mcp__docfit__docx_inspect",
            tool_use_id="inspect-1",
            parent_tool_use_id="agent-call",
        ),
        _event(
            17,
            source="tool",
            kind="tool_pre",
            source_event_id="inspect-1",
            status="started",
            tool_name="mcp__docfit__docx_inspect",
            tool_use_id="inspect-1",
            agent_id="agent-1",
            agent_type="docfit-unit-analyst",
        ),
        _event(
            18,
            source="tool",
            kind="tool_post",
            source_event_id="inspect-1",
            status="ok",
            tool_name="mcp__docfit__docx_inspect",
            tool_use_id="inspect-1",
            agent_id="agent-1",
            agent_type="docfit-unit-analyst",
            attributes=(ObservationAttribute("object_count", 4),),
        ),
        _event(
            19,
            source="sdk",
            kind="tool_result",
            source_event_id="inspect-1",
            status="ok",
            tool_use_id="inspect-1",
            parent_tool_use_id="agent-call",
        ),
        _event(
            20,
            source="sdk",
            kind="subagent_stopped",
            source_event_id="agent-1",
            status="finished",
            agent_id="agent-1",
            agent_type="docfit-unit-analyst",
        ),
        _event(
            90,
            source="report",
            kind="conversion_report",
            source_event_id="report",
            status="completed",
            attributes=(
                ObservationAttribute("coverage_state", "complete"),
                ObservationAttribute("events_dropped", 0),
                ObservationAttribute("transcript_status", "cleaned"),
            ),
        ),
        _event(
            91,
            source="app",
            kind="run_finished",
            source_event_id="run-finish",
            status="completed",
        ),
    )
    run = StoredObservationRun(
        RUN_ID,
        "task_0123456789abcdef0123456789abcdef",
        "session-1",
        "completed",
        events[0].observed_at,
        events[-1].observed_at,
        events[-1].observed_at,
        len(events),
        4096,
    )

    view = build_run_presentation(run, events)

    tools = {item["tool_use_id"]: item for item in view["tools"]}
    assert set(tools) == {"agent-call", "inspect-1"}
    assert tools["agent-call"]["caller"] == "main"
    assert tools["inspect-1"]["caller"] == "agent-1"
    assert tools["inspect-1"]["association_status"] == "verified"
    subagents = view["subagents"]
    assert len(subagents) == 1
    assert subagents[0]["agent_id"] == "agent-1"
    assert [item["tool_use_id"] for item in subagents[0]["tools"]] == ["inspect-1"]
    assert subagents[0]["association_status"] == "verified"
    assert any(
        item["kind"] == "subagent_parent"
        and item["proof_fields"] == ("parent_tool_use_id", "tool_use_id", "agent_id")
        for item in view["relationships"]
    )
    offsets = [item["monotonic_offset_ms"] for item in view["events"]]
    assert offsets == sorted(offsets)

    html = Environment(
        loader=PackageLoader("docfit.observability", "templates"),
        autoescape=select_autoescape(("html", "xml")),
    ).get_template("run.html").render(
        view=view,
        revision="revision",
        csrf_token="synthetic-csrf",
    )
    assert "docfit-unit-analyst" in html
    assert "mcp__docfit__docx_inspect" in html
    assert "agent-call" in html
    assert "inspect-1" in html
    assert "任务摘要" in html
    assert "不持久化原始任务正文" in html
    assert "parent_tool_use_id + tool_use_id + agent_id" in html

    incomplete_events = tuple(
        event
        for event in events
        if not (
            event.kind in {"tool_post", "tool_result"}
            and event.tool_use_id == "inspect-1"
        )
    )
    incomplete_view = build_run_presentation(run, incomplete_events)
    incomplete_html = Environment(
        loader=PackageLoader("docfit.observability", "templates"),
        autoescape=select_autoescape(("html", "xml")),
    ).get_template("run.html").render(
        view=incomplete_view,
        revision="revision",
        csrf_token="synthetic-csrf",
    )
    assert incomplete_view["dimensions"]["observation"]["state"] == "degraded"
    assert "关系缺口" in incomplete_html
    assert "tool_terminal_missing" in incomplete_html
