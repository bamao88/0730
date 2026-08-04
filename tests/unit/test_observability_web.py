from __future__ import annotations

import hashlib
import io
import json
import socket
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from docfit.observability.events import ProjectionContext
from docfit.observability.evidence import DirectorySelection
from docfit.observability.privacy import project_app_event, project_report_event
from docfit.observability.storage import (
    initialize_observation_store,
    list_observation_runs,
    load_observation_events,
    observation_writer,
    persist_observation_batch,
)
from docfit.observability.web import (
    CSRF_HEADER,
    CSRF_TOKEN_BYTES,
    LOGIN_HEADER,
    LOGIN_TOKEN_BYTES,
    SESSION_ABSOLUTE_SECONDS,
    SESSION_COOKIE,
    SESSION_IDLE_SECONDS,
    SESSION_TOKEN_BYTES,
    build_observer_server,
    create_observer_app,
    run_observer_server,
)

RUN_ID = "run_0123456789abcdef0123456789abcdef"
TASK_REF = "task_fedcba9876543210fedcba9876543210"
SESSION_ID = "synthetic-session"
PORT = 43123
ORIGIN = f"http://127.0.0.1:{PORT}"
LOGIN_CODE = "test-login-code-with-at-least-128-bits"


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ample_disk_space(_: Path) -> tuple[int, int]:
    return 100 * 1024**3, 80 * 1024**3


def _create_task(root: Path) -> dict[str, object]:
    values = {
        "source_sha256": b"source",
        "template_sha256": b"template",
        "requirements_sha256": b"requirements",
        "final_sha256": b"final",
    }
    input_root = root / "input"
    input_root.mkdir(parents=True, exist_ok=True)
    (input_root / "student.docx").write_bytes(values["source_sha256"])
    (input_root / "school-template.docx").write_bytes(values["template_sha256"])
    (input_root / "school-requirements.txt").write_bytes(
        values["requirements_sha256"]
    )
    (root / "final.docx").write_bytes(values["final_sha256"])
    report: dict[str, object] = {
        "schema_version": 2,
        "run_id": RUN_ID,
        "task_ref": TASK_REF,
        "session_id": SESSION_ID,
        "status": "COMPLETED",
        "source_sha256": _hash(values["source_sha256"]),
        "template_sha256": _hash(values["template_sha256"]),
        "requirements_sha256": _hash(values["requirements_sha256"]),
        "final_sha256": _hash(values["final_sha256"]),
        "knowledge_version": "v1",
        "knowledge_digest": f"sha256:{'a' * 64}",
        "backend": "synthetic-backend",
        "tool_uses": [],
        "warnings": [],
        "detail": "PRIVATE_REPORT_PROSE",
        "observation_coverage": {
            "state": "complete",
            "events_persisted": 3,
            "events_dropped": 0,
            "missing_sources": [],
            "last_observed_at": None,
            "failure_codes": [],
        },
        "sdk_transcript": {
            "status": "cleaned",
            "residual_count": 0,
            "oldest_age_bucket": None,
            "failure_codes": [],
        },
    }
    (root / "conversion-report.json").write_text(json.dumps(report), encoding="utf-8")
    return report


def _seed_database(state_root: Path, task_root: Path) -> Path:
    report = _create_task(task_root)
    now = datetime(2026, 8, 4, 8, 0, tzinfo=UTC).isoformat()
    hashes = {
        key: str(report[key])
        for key in ("source_sha256", "template_sha256", "requirements_sha256")
    }
    results = (
        project_app_event(
            ProjectionContext(RUN_ID, 1, now, 1.0),
            source_event_id="run-start",
            kind="run_started",
            status="started",
            task_ref=TASK_REF,
            hashes=hashes,
        ),
        project_app_event(
            ProjectionContext(RUN_ID, 2, now, 2.0),
            source_event_id="run-finish",
            kind="run_finished",
            status="completed",
            hashes={"final_sha256": str(report["final_sha256"])},
        ),
        project_report_event(report, ProjectionContext(RUN_ID, 3, now, 3.0)),
    )
    events = tuple(result.event for result in results if result.event is not None)
    assert len(events) == 3
    database = initialize_observation_store(state_root)
    with observation_writer(database) as writer:
        persisted = persist_observation_batch(
            writer,
            database,
            events,
            disk_space_probe=_ample_disk_space,
        )
    assert persisted.persisted_events == 3
    return database


class StaticSelector:
    def __init__(self, selection: DirectorySelection) -> None:
        self.selection = selection
        self.calls = 0

    def select(self) -> DirectorySelection:
        self.calls += 1
        return self.selection


class RecordingOpener:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def open(self, path: Path) -> bool:
        self.paths.append(path)
        return True


class FailingSelector:
    def select(self) -> DirectorySelection:
        raise RuntimeError("PRIVATE_ADAPTER_ERROR")


class FailingOpener:
    def open(self, path: Path) -> bool:
        del path
        raise RuntimeError("PRIVATE_OPENER_ERROR")


def _client(
    database: Path,
    *,
    selector: StaticSelector | None = None,
    opener: RecordingOpener | None = None,
    clock: Callable[[], float] | None = None,
    login_code: str = LOGIN_CODE,
) -> TestClient:
    options = {} if clock is None else {"clock": clock}
    app = create_observer_app(
        database,
        port=PORT,
        login_code=login_code,
        selector=selector,
        opener=opener,
        **options,
    )
    return TestClient(app, base_url=ORIGIN)


def _login(client: TestClient, *, code: str = LOGIN_CODE) -> str:
    response = client.post(
        "/login",
        headers={"origin": ORIGIN, LOGIN_HEADER: code},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def _post_headers(csrf: str) -> dict[str, str]:
    return {"origin": ORIGIN, CSRF_HEADER: csrf}


def test_login_is_one_time_cookie_bound_and_not_reflected(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    client = _client(database)

    response = client.post(
        "/login",
        headers={"origin": ORIGIN, LOGIN_HEADER: LOGIN_CODE},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert "Domain=" not in cookie
    assert LOGIN_CODE not in response.text
    assert "access-control-allow-origin" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    csrf = str(response.json()["csrf_token"])
    session_token = client.cookies.get(SESSION_COOKIE)
    assert session_token is not None
    database_bytes = database.read_bytes()
    assert LOGIN_CODE.encode() not in database_bytes
    assert csrf.encode() not in database_bytes
    assert session_token.encode() not in database_bytes

    replay = TestClient(client.app, base_url=ORIGIN)
    rejected = replay.post(
        "/login", headers={"origin": ORIGIN, LOGIN_HEADER: LOGIN_CODE}
    )
    assert rejected.status_code == 401


def test_comparison_page_and_api_keep_unknown_values_explicit(tmp_path: Path) -> None:
    database = _seed_database(tmp_path / "state", tmp_path / "task")
    first_events = load_observation_events(database, RUN_ID)
    second_run_id = "run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    second_events = tuple(
        replace(
            event,
            run_id=second_run_id,
            source_event_id=f"second-{event.source_event_id}",
        )
        for event in first_events
    )
    with observation_writer(database) as writer:
        persisted = persist_observation_batch(
            writer,
            database,
            second_events,
            disk_space_probe=_ample_disk_space,
        )
    assert persisted.persisted_events == len(second_events)
    client = _client(database)
    _login(client)

    query = f"?left={RUN_ID}&right={second_run_id}"
    page = client.get(f"/compare{query}")
    payload = client.get(f"/api/compare{query}")

    assert page.status_code == 200
    assert "跨运行差异" in page.text
    assert "unknown" in page.text
    assert payload.status_code == 200
    comparison = payload.json()["comparison"]
    assert comparison["comparability"]["status"] == "conditional"
    assert comparison["comparability"]["performance_conclusion"] == "not_allowed"
    assert comparison["winner"] is None
    assert client.get("/compare").status_code == 400
    assert client.get(f"/api/compare?left={RUN_ID}&right=run_missing").status_code == 404


def test_host_origin_query_body_and_failure_limit_are_fail_closed(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    client = _client(database)

    assert client.get("/", headers={"host": "localhost:43123"}).status_code == 400
    assert client.post("/login", headers={LOGIN_HEADER: LOGIN_CODE}).status_code == 403
    assert (
        client.post(
            "/login",
            headers={"origin": "null", LOGIN_HEADER: LOGIN_CODE},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/login?code={LOGIN_CODE}",
            headers={"origin": ORIGIN, LOGIN_HEADER: LOGIN_CODE},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/login",
            headers={"origin": ORIGIN, LOGIN_HEADER: LOGIN_CODE},
            content=b"unexpected",
        ).status_code
        == 400
    )
    for index in range(5):
        rejected = client.post(
            "/login",
            headers={"origin": ORIGIN, LOGIN_HEADER: f"wrong-{index}"},
        )
        assert rejected.status_code == 401
    assert (
        client.post(
            "/login", headers={"origin": ORIGIN, LOGIN_HEADER: LOGIN_CODE}
        ).status_code
        == 401
    )


def test_session_idle_and_absolute_expiry_are_enforced(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    now = [0.0]
    idle_client = _client(database, clock=lambda: now[0])
    _login(idle_client)
    now[0] = float(SESSION_IDLE_SECONDS)
    assert idle_client.get("/api/runs").status_code == 401

    now[0] = 0.0
    absolute_client = _client(database, clock=lambda: now[0])
    _login(absolute_client)
    for moment in range(1700, SESSION_ABSOLUTE_SECONDS, 1700):
        now[0] = float(moment)
        assert absolute_client.get("/api/runs").status_code == 200
    now[0] = float(SESSION_ABSOLUTE_SECONDS)
    assert absolute_client.get("/api/runs").status_code == 401


def test_get_and_missing_csrf_cannot_mutate_or_open(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    selector = StaticSelector(DirectorySelection("selected", task_root))
    opener = RecordingOpener()
    client = _client(database, selector=selector, opener=opener)
    csrf = _login(client)
    initial = list_observation_runs(database)

    for path in (
        f"/api/runs/{RUN_ID}/mount",
        f"/api/runs/{RUN_ID}/delete",
        "/api/history/clear",
        f"/api/runs/{RUN_ID}/open/final_docx",
    ):
        assert client.get(path).status_code == 405
    assert (
        client.post(
            f"/api/runs/{RUN_ID}/mount",
            headers={"origin": ORIGIN},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/runs/{RUN_ID}/delete",
            headers={"origin": ORIGIN, CSRF_HEADER: "wrong"},
        ).status_code
        == 403
    )
    assert client.delete(f"/api/runs/{RUN_ID}/delete").status_code == 405
    assert list_observation_runs(database) == initial
    assert selector.calls == 0
    assert opener.paths == []
    assert client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(csrf)
    ).status_code == 200


def test_verified_mount_and_open_never_return_local_paths(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    selector = StaticSelector(DirectorySelection("selected", task_root))
    opener = RecordingOpener()
    client = _client(database, selector=selector, opener=opener)
    csrf = _login(client)

    runs = client.get("/api/runs")
    mounted = client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(csrf)
    )
    opened = client.post(
        f"/api/runs/{RUN_ID}/open/final_docx", headers=_post_headers(csrf)
    )
    run_page = client.get(f"/runs/{RUN_ID}")

    assert runs.status_code == 200
    assert mounted.json() == {"status": "verified", "failure_code": None}
    assert opened.json() == {"status": "ok"}
    assert "打开 final.docx" in run_page.text
    assert "选择并重新授权任务目录" not in run_page.text
    assert opener.paths == [(task_root / "final.docx").resolve()]
    combined = runs.text + mounted.text + opened.text
    assert str(task_root) not in combined
    assert "PRIVATE_REPORT_PROSE" not in combined


def test_mount_capability_is_lost_on_restart_and_picker_failure_is_safe(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    opener = RecordingOpener()
    first = _client(
        database,
        selector=StaticSelector(DirectorySelection("selected", task_root)),
        opener=opener,
        login_code="first-login-code",
    )
    csrf = _login(first, code="first-login-code")
    assert first.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(csrf)
    ).status_code == 200

    restarted = _client(
        database,
        selector=StaticSelector(
            DirectorySelection("unavailable", None, "picker_unavailable")
        ),
        opener=opener,
        login_code="second-login-code",
    )
    restarted_csrf = _login(restarted, code="second-login-code")
    open_response = restarted.post(
        f"/api/runs/{RUN_ID}/open/final_docx",
        headers=_post_headers(restarted_csrf),
    )
    mount_response = restarted.post(
        f"/api/runs/{RUN_ID}/mount",
        headers=_post_headers(restarted_csrf),
    )

    assert open_response.status_code == 409
    assert open_response.json()["failure"]["code"] == "evidence_mount_required"
    assert mount_response.status_code == 409
    assert mount_response.json() == {
        "status": "unavailable",
        "failure_code": "picker_unavailable",
    }
    assert str(task_root) not in mount_response.text


def test_adapter_failures_return_only_fixed_safe_codes(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    failed_picker = create_observer_app(
        database,
        port=PORT,
        login_code="picker-login",
        selector=FailingSelector(),
    )
    picker_client = TestClient(failed_picker, base_url=ORIGIN)
    picker_csrf = _login(picker_client, code="picker-login")

    picker_response = picker_client.post(
        f"/api/runs/{RUN_ID}/mount",
        headers=_post_headers(picker_csrf),
    )

    assert picker_response.status_code == 409
    assert picker_response.json()["failure"]["code"] == "picker_unavailable"
    assert "PRIVATE_ADAPTER_ERROR" not in picker_response.text

    opener_app = create_observer_app(
        database,
        port=PORT,
        login_code="opener-login",
        selector=StaticSelector(DirectorySelection("selected", task_root)),
        opener=FailingOpener(),
    )
    opener_client = TestClient(opener_app, base_url=ORIGIN)
    opener_csrf = _login(opener_client, code="opener-login")
    assert opener_client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(opener_csrf)
    ).status_code == 200

    opener_response = opener_client.post(
        f"/api/runs/{RUN_ID}/open/final_docx",
        headers=_post_headers(opener_csrf),
    )

    assert opener_response.status_code == 409
    assert opener_response.json()["failure"]["code"] == "artifact_opener_unavailable"
    assert "PRIVATE_OPENER_ERROR" not in opener_response.text


def test_delete_and_clear_remove_only_observer_history(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    client = _client(database)
    csrf = _login(client)

    deleted = client.post(
        f"/api/runs/{RUN_ID}/delete", headers=_post_headers(csrf)
    )
    assert deleted.json() == {"status": "ok", "deleted": True}
    assert list_observation_runs(database) == ()
    assert (task_root / "final.docx").read_bytes() == b"final"
    assert (task_root / "conversion-report.json").is_file()

    _seed_database(tmp_path / "state", task_root)
    cleared = client.post("/api/history/clear", headers=_post_headers(csrf))
    assert cleared.json() == {"status": "ok", "deleted_runs": 1}
    assert list_observation_runs(database) == ()
    assert (task_root / "final.docx").is_file()


def test_uvicorn_configuration_is_loopback_and_proxy_free(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    app = create_observer_app(database, port=PORT, login_code=LOGIN_CODE)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        server = build_observer_server(app, listener)
    finally:
        listener.close()

    assert server.config.host == "127.0.0.1"
    assert server.config.access_log is False
    assert server.config.proxy_headers is False
    assert server.config.forwarded_allow_ips == ""
    assert server.config.server_header is False
    assert server.config.date_header is False
    assert server.config.ws == "none"
    assert server.config.workers == 1


def test_non_loopback_listener_is_rejected(tmp_path: Path) -> None:
    database = initialize_observation_store(tmp_path / "state")
    app = create_observer_app(database, port=PORT, login_code=LOGIN_CODE)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("0.0.0.0", 0))
        with pytest.raises(ValueError, match="observer_non_loopback_socket"):
            build_observer_server(app, listener)
    finally:
        listener.close()


def test_production_secret_entropy_floors_are_explicit() -> None:
    assert LOGIN_TOKEN_BYTES >= 16
    assert SESSION_TOKEN_BYTES >= 32
    assert CSRF_TOKEN_BYTES >= 32


def test_observer_without_protected_tty_fails_before_issuing_secret() -> None:
    output = io.StringIO()

    result = run_observer_server(
        port=0,
        input_stream=io.StringIO(),
        output_stream=output,
    )

    assert result == 2
    assert "observer_interactive_tty_required" in output.getvalue()
    assert "One-time login code" not in output.getvalue()


def test_observer_keyboard_interrupt_exits_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InteractiveStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    class InterruptingServer:
        def run(self, *, sockets: list[socket.socket]) -> None:
            assert len(sockets) == 1
            raise KeyboardInterrupt

    monkeypatch.setattr(
        "docfit.observability.web.observation_state_root",
        lambda: tmp_path / "state",
    )
    monkeypatch.setattr(
        "docfit.observability.web.build_observer_server",
        lambda app, listener: InterruptingServer(),
    )
    output = InteractiveStream()

    result = run_observer_server(
        port=0,
        input_stream=InteractiveStream(),
        output_stream=output,
    )

    assert result == 0
    assert "DocFit observer: http://127.0.0.1:" in output.getvalue()


def test_html_json_static_and_debug_views_are_privacy_safe(tmp_path: Path) -> None:
    task_root = tmp_path / "PRIVATE_TASK_DIRECTORY"
    database = _seed_database(tmp_path / "state", task_root)
    client = _client(database)

    login_page = client.get("/")
    stylesheet = client.get("/static/observer.css")
    script = client.get("/static/observer.js")
    missing_asset = client.get("/static/private.txt")

    assert login_page.status_code == 200
    assert login_page.headers["content-type"].startswith("text/html")
    assert "一次性登录码" in login_page.text
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.headers["content-type"].startswith("application/javascript")
    assert missing_asset.status_code == 404
    assert "script-src 'self'" in login_page.headers["content-security-policy"]
    assert "style-src 'self'" in login_page.headers["content-security-policy"]

    _login(client)
    overview = client.get("/")
    run_page = client.get(f"/runs/{RUN_ID}")
    detail = client.get(f"/api/runs/{RUN_ID}")
    debug = client.get(f"/api/runs/{RUN_ID}/debug/0")
    revision = client.get("/api/revision").json()["revision"]

    assert overview.status_code == 200
    assert "最近运行" in overview.text
    assert RUN_ID in overview.text
    assert run_page.status_code == 200
    assert "Transcript / 时间线" in run_page.text
    assert "Agent / Subagent 树" in run_page.text
    assert "Tool 调用" in run_page.text
    assert "四个独立状态维度" in run_page.text
    assert "选择并重新授权任务目录" in run_page.text
    assert "打开 final.docx" not in run_page.text
    assert f'data-revision="{revision}"' in run_page.text
    assert detail.status_code == 200
    metrics = detail.json()["view"]["metrics"]
    input_tokens = next(item for item in metrics if item["label"] == "Input tokens")
    assert input_tokens == {
        "key": "input_tokens",
        "label": "Input tokens",
        "value": None,
        "source": "unknown",
    }
    assert debug.status_code == 200
    assert debug.json()["debug_context_schema_version"] == 1
    assert debug.json()["run_id"] == RUN_ID
    assert debug.json()["local_evidence"] == "unmounted"

    combined = "\n".join(
        (overview.text, run_page.text, detail.text, debug.text, stylesheet.text, script.text)
    )
    assert str(task_root) not in combined
    assert "PRIVATE_REPORT_PROSE" not in combined
    assert LOGIN_CODE not in combined


def test_debug_context_index_matches_deduplicated_display_order(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    events = load_observation_events(database, RUN_ID)
    duplicate = replace(
        events[0],
        source_sequence=4,
        monotonic_offset_ms=1.5,
    )
    with observation_writer(database) as writer:
        persisted = persist_observation_batch(
            writer,
            database,
            (duplicate,),
            disk_space_probe=_ample_disk_space,
        )
    assert persisted.persisted_events == 1
    client = _client(database)
    _login(client)

    displayed = client.get(f"/api/runs/{RUN_ID}").json()["view"]["events"]
    debug_kinds = [
        client.get(f"/api/runs/{RUN_ID}/debug/{index}").json()["event_kind"]
        for index in range(len(displayed))
    ]

    assert debug_kinds == [event["kind"] for event in displayed]
    assert len(displayed) == 3


def test_sse_emits_only_an_opaque_history_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _seed_database(tmp_path / "state", tmp_path / "PRIVATE_TASK_DIRECTORY")
    moments = iter((0.0, 0.0, 0.0, 0.0, float(SESSION_IDLE_SECONDS)))

    def clock() -> float:
        return next(moments, float(SESSION_IDLE_SECONDS))

    client = _client(database, clock=clock)
    _login(client)
    monkeypatch.setattr("docfit.observability.web.STREAM_POLL_SECONDS", 0.0)

    response = client.get("/api/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: history" in response.text
    assert 'data: {"revision":"' in response.text
    assert RUN_ID not in response.text
    assert str(tmp_path) not in response.text
    assert "PRIVATE_REPORT_PROSE" not in response.text


def test_evidence_states_are_session_local_and_distinct(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    database = _seed_database(tmp_path / "state", task_root)
    selector = StaticSelector(DirectorySelection("selected", task_root))
    opener = RecordingOpener()
    client = _client(database, selector=selector, opener=opener)
    csrf = _login(client)

    initial = client.get(f"/api/runs/{RUN_ID}").json()["view"]["dimensions"]
    assert initial["local_evidence"] == "unmounted"

    assert client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(csrf)
    ).status_code == 200
    available = client.get(f"/api/runs/{RUN_ID}").json()["view"]["dimensions"]
    assert available["local_evidence"] == "available"
    assert available["evidence_association"] == "verified"

    report_path = task_root / "conversion-report.json"
    report_path.write_text(report_path.read_text() + " ", encoding="utf-8")
    stale = client.post(
        f"/api/runs/{RUN_ID}/open/final_docx", headers=_post_headers(csrf)
    )
    assert stale.status_code == 409
    stale_dimensions = client.get(f"/api/runs/{RUN_ID}").json()["view"][
        "dimensions"
    ]
    assert stale_dimensions["local_evidence"] == "stale"
    assert stale_dimensions["evidence_failure"] == "evidence_report_changed"

    missing_root = tmp_path / "missing-task"
    missing_database = _seed_database(tmp_path / "missing-state", missing_root)
    missing_client = _client(
        missing_database,
        selector=StaticSelector(DirectorySelection("selected", missing_root)),
        opener=RecordingOpener(),
        login_code="missing-login",
    )
    missing_csrf = _login(missing_client, code="missing-login")
    assert missing_client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(missing_csrf)
    ).status_code == 200
    assert missing_client.post(
        f"/api/runs/{RUN_ID}/open/validation", headers=_post_headers(missing_csrf)
    ).status_code == 409
    missing_dimensions = missing_client.get(f"/api/runs/{RUN_ID}").json()["view"][
        "dimensions"
    ]
    assert missing_dimensions["local_evidence"] == "missing"

    unauthorized_root = tmp_path / "unauthorized-task"
    unauthorized_database = _seed_database(
        tmp_path / "unauthorized-state", unauthorized_root
    )
    unauthorized_client = _client(
        unauthorized_database,
        selector=StaticSelector(DirectorySelection("selected", unauthorized_root)),
        opener=RecordingOpener(),
        login_code="unauthorized-login",
    )
    unauthorized_csrf = _login(unauthorized_client, code="unauthorized-login")
    assert unauthorized_client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(unauthorized_csrf)
    ).status_code == 200
    (unauthorized_root / "validation.json").symlink_to(unauthorized_root / "final.docx")
    assert unauthorized_client.post(
        f"/api/runs/{RUN_ID}/open/validation",
        headers=_post_headers(unauthorized_csrf),
    ).status_code == 409
    unauthorized_dimensions = unauthorized_client.get(
        f"/api/runs/{RUN_ID}"
    ).json()["view"]["dimensions"]
    assert unauthorized_dimensions["local_evidence"] == "unauthorized"

    conflict_root = tmp_path / "conflict-task"
    conflict_database = _seed_database(tmp_path / "conflict-state", conflict_root)
    (conflict_root / "final.docx").write_bytes(b"changed")
    conflict_client = _client(
        conflict_database,
        selector=StaticSelector(DirectorySelection("selected", conflict_root)),
        login_code="conflict-login",
    )
    conflict_csrf = _login(conflict_client, code="conflict-login")
    assert conflict_client.post(
        f"/api/runs/{RUN_ID}/mount", headers=_post_headers(conflict_csrf)
    ).status_code == 409
    conflict_dimensions = conflict_client.get(f"/api/runs/{RUN_ID}").json()[
        "view"
    ]["dimensions"]
    assert conflict_dimensions["local_evidence"] == "conflict"
