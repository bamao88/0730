"""Direct-open loopback Web shell for local observation history."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import socket
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import IO, Any, cast

import uvicorn
from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from docfit.observability.comparison import build_run_comparison
from docfit.observability.correlation import LocalEvidenceStatus
from docfit.observability.events import ObservationEvent
from docfit.observability.evidence import (
    ARTIFACT_LOCATORS,
    ArtifactOpener,
    DirectorySelector,
    EvidenceAccessError,
    MountedEvidenceCapability,
    resolve_task_locator,
    verify_selected_task,
)
from docfit.observability.presentation import (
    build_debug_context,
    build_run_presentation,
    history_revision,
    ordered_run_events,
    summarize_run,
)
from docfit.observability.storage import (
    ObservationStorageError,
    StoredObservationRun,
    clear_observation_history,
    delete_observation_run,
    get_observation_run,
    initialize_observation_store,
    list_observation_runs,
    load_observation_events,
    observation_state_root,
)

SESSION_COOKIE = "docfit_observer_session"
CSRF_HEADER = "x-docfit-csrf"
SESSION_IDLE_SECONDS = 30 * 60
SESSION_ABSOLUTE_SECONDS = 8 * 60 * 60
SESSION_MAX_COUNT = 64
SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32
WEB_RUN_LIMIT = 50
STREAM_POLL_SECONDS = 1.0
STREAM_HEARTBEAT_SECONDS = 15.0

_STATIC_ASSETS = frozenset({"observer.css", "observer.js"})
_TEMPLATES = Environment(
    loader=PackageLoader("docfit.observability", "templates"),
    autoescape=select_autoescape(("html", "xml")),
    enable_async=False,
)

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; img-src 'none'; "
        "font-src 'none'; object-src 'none'; script-src 'self'; "
        "style-src 'self'; media-src 'none'; manifest-src 'none'; "
        "worker-src 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _error(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"status": "error", "failure": {"code": code}},
        status_code=status_code,
    )


@dataclass(slots=True)
class ObserverSession:
    csrf_token: str
    created_at: float
    last_seen_at: float
    mounts: dict[str, MountedEvidenceCapability] = field(default_factory=dict)
    evidence_states: dict[str, LocalEvidenceStatus] = field(default_factory=dict)
    evidence_failures: dict[str, str] = field(default_factory=dict)


class ObserverSecurityState:
    """In-memory session/mount authority; no secret or path is persisted."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._sessions: dict[str, ObserverSession] = {}

    def create_session(self) -> tuple[str, ObserverSession]:
        now = self._clock()
        expired = tuple(
            digest
            for digest, session in self._sessions.items()
            if now - session.last_seen_at >= SESSION_IDLE_SECONDS
            or now - session.created_at >= SESSION_ABSOLUTE_SECONDS
        )
        for digest in expired:
            self._sessions.pop(digest, None)
        while len(self._sessions) >= SESSION_MAX_COUNT:
            oldest = min(
                self._sessions,
                key=lambda digest: self._sessions[digest].created_at,
            )
            self._sessions.pop(oldest, None)
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        session = ObserverSession(secrets.token_urlsafe(CSRF_TOKEN_BYTES), now, now)
        self._sessions[_token_digest(token)] = session
        return token, session

    def session(self, token: str | None, *, touch: bool = True) -> ObserverSession | None:
        if token is None:
            return None
        digest = _token_digest(token)
        session = self._sessions.get(digest)
        if session is None:
            return None
        now = self._clock()
        if (
            now - session.last_seen_at >= SESSION_IDLE_SECONDS
            or now - session.created_at >= SESSION_ABSOLUTE_SECONDS
        ):
            self._sessions.pop(digest, None)
            return None
        if touch:
            session.last_seen_at = now
        return session


@dataclass(slots=True)
class ObserverWebContext:
    database: Path
    expected_host: str
    expected_origin: str
    security: ObserverSecurityState
    selector: DirectorySelector | None = None
    opener: ArtifactOpener | None = None
    secure_cookie: bool = False


def _context(request: Request) -> ObserverWebContext:
    return cast(ObserverWebContext, request.app.state.observer_context)


def _has_request_body(request: Request) -> bool:
    value = request.headers.get("content-length")
    if value is None:
        return request.headers.get("transfer-encoding") is not None
    try:
        return int(value) > 0
    except ValueError:
        return True


class SecurityBoundaryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, context: ObserverWebContext) -> None:
        super().__init__(app)
        self._context = context

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.headers.get("host") != self._context.expected_host:
            response: Response = _error("observer_host_rejected", 400)
        elif request.method not in {"GET", "HEAD", "POST"}:
            response = _error("observer_method_rejected", 405)
        elif (
            request.method == "POST"
            and request.headers.get("origin") != self._context.expected_origin
        ):
            response = _error("observer_origin_rejected", 403)
        elif request.method == "POST" and _has_request_body(request):
            response = _error("observer_request_body_rejected", 400)
        else:
            token = request.cookies.get(SESSION_COOKIE)
            session = self._context.security.session(token)
            session_created = session is None
            if session_created:
                token, session = self._context.security.create_session()
            assert token is not None
            request.state.observer_session = session
            request.state.observer_session_token = token
            response = await call_next(request)
            if session_created:
                response.set_cookie(
                    SESSION_COOKIE,
                    token,
                    max_age=SESSION_ABSOLUTE_SECONDS,
                    httponly=True,
                    secure=self._context.secure_cookie,
                    samesite="strict",
                    path="/",
                )
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


def _request_session(request: Request, *, csrf: bool = False) -> ObserverSession | None:
    session = getattr(request.state, "observer_session", None)
    if not isinstance(session, ObserverSession):
        return None
    if session is None:
        return None
    if csrf and not secrets.compare_digest(
        request.headers.get(CSRF_HEADER, ""), session.csrf_token
    ):
        return None
    return session


def _render_template(
    name: str,
    *,
    status_code: int = 200,
    **context: object,
) -> HTMLResponse:
    return HTMLResponse(
        _TEMPLATES.get_template(name).render(**context),
        status_code=status_code,
    )


def _evidence_view(
    session: ObserverSession,
    run_id: str,
) -> tuple[LocalEvidenceStatus, str | None, str | None]:
    capability = session.mounts.get(run_id)
    if capability is not None:
        return (
            "available",
            capability.association,
            session.evidence_failures.get(run_id),
        )
    return (
        session.evidence_states.get(run_id, "unmounted"),
        None,
        session.evidence_failures.get(run_id),
    )


def _failure_evidence_state(code: str) -> LocalEvidenceStatus:
    if any(fragment in code for fragment in ("changed", "replaced")):
        return "stale"
    if any(
        fragment in code
        for fragment in ("symlink", "path_escape", "locator_invalid", "not_directory")
    ):
        return "unauthorized"
    if any(fragment in code for fragment in ("missing", "unavailable")) and not code.startswith(
        ("picker_", "artifact_opener_")
    ):
        return "missing"
    return "unmounted"


def _note_evidence_failure(
    session: ObserverSession,
    run_id: str,
    code: str,
    *,
    state: LocalEvidenceStatus | None = None,
) -> None:
    session.mounts.pop(run_id, None)
    session.evidence_states[run_id] = state or _failure_evidence_state(code)
    session.evidence_failures[run_id] = code


def _load_run_view(
    context: ObserverWebContext,
    session: ObserverSession,
    run_id: str,
) -> tuple[StoredObservationRun, tuple[ObservationEvent, ...], dict[str, object]] | None:
    run = get_observation_run(context.database, run_id)
    if run is None:
        return None
    events = load_observation_events(context.database, run_id)
    evidence_state, evidence_association, evidence_failure = _evidence_view(session, run_id)
    view = build_run_presentation(
        run,
        events,
        local_evidence=evidence_state,
        evidence_association=evidence_association,
        evidence_failure=evidence_failure,
    )
    return run, events, view


def _load_overview(
    context: ObserverWebContext,
    session: ObserverSession,
) -> tuple[tuple[dict[str, object], ...], str]:
    runs = list_observation_runs(context.database, limit=WEB_RUN_LIMIT)
    views: list[dict[str, object]] = []
    for run in runs:
        events = load_observation_events(context.database, run.run_id)
        evidence_state, evidence_association, evidence_failure = _evidence_view(session, run.run_id)
        presentation = build_run_presentation(
            run,
            events,
            local_evidence=evidence_state,
            evidence_association=evidence_association,
            evidence_failure=evidence_failure,
        )
        views.append(summarize_run(presentation))
    return tuple(views), history_revision(runs)


def _load_comparison(
    context: ObserverWebContext,
    left_run_id: str,
    right_run_id: str,
) -> dict[str, object] | None:
    left_run = get_observation_run(context.database, left_run_id)
    right_run = get_observation_run(context.database, right_run_id)
    if left_run is None or right_run is None:
        return None
    left_events = load_observation_events(context.database, left_run_id)
    right_events = load_observation_events(context.database, right_run_id)
    return build_run_comparison(left_run, left_events, right_run, right_events)


async def _root(request: Request) -> Response:
    session = _request_session(request)
    if session is None:
        return _error("observer_session_unavailable", 503)
    try:
        runs, revision = await run_in_threadpool(_load_overview, _context(request), session)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    return _render_template(
        "overview.html",
        runs=runs,
        revision=revision,
        csrf_token=session.csrf_token,
    )


async def _static_asset(request: Request) -> Response:
    asset = request.path_params["asset"]
    if asset not in _STATIC_ASSETS:
        return _error("observer_asset_not_found", 404)
    try:
        body = files("docfit.observability").joinpath("static", asset).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return _error("observer_asset_unavailable", 503)
    media_type = "text/css" if asset.endswith(".css") else "application/javascript"
    return Response(body, media_type=media_type)


async def _runs(request: Request) -> Response:
    session = _request_session(request)
    if session is None:
        return _error("observer_session_required", 401)
    try:
        runs, revision = await run_in_threadpool(_load_overview, _context(request), session)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    return JSONResponse({"status": "ok", "revision": revision, "runs": runs})


async def _run_page(request: Request) -> Response:
    session = _request_session(request)
    if session is None:
        return _error("observer_session_required", 401)
    try:
        loaded = await run_in_threadpool(
            _load_run_view,
            _context(request),
            session,
            request.path_params["run_id"],
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    if loaded is None:
        return _error("observer_run_not_found", 404)
    _, _, view = loaded
    try:
        runs = await run_in_threadpool(
            list_observation_runs,
            _context(request).database,
            limit=WEB_RUN_LIMIT,
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    return _render_template(
        "run.html",
        view=view,
        revision=history_revision(runs),
        csrf_token=session.csrf_token,
    )


async def _run_detail(request: Request) -> Response:
    session = _request_session(request)
    if session is None:
        return _error("observer_session_required", 401)
    try:
        loaded = await run_in_threadpool(
            _load_run_view,
            _context(request),
            session,
            request.path_params["run_id"],
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    if loaded is None:
        return _error("observer_run_not_found", 404)
    _, _, view = loaded
    return JSONResponse({"status": "ok", "view": view})


def _comparison_ids(request: Request) -> tuple[str, str] | None:
    left = request.query_params.get("left")
    right = request.query_params.get("right")
    if left is None or right is None or len(left) > 64 or len(right) > 64:
        return None
    return left, right


async def _comparison_page(request: Request) -> Response:
    session = _request_session(request)
    if session is None:
        return _error("observer_session_required", 401)
    run_ids = _comparison_ids(request)
    if run_ids is None:
        return _error("observer_comparison_selection_invalid", 400)
    try:
        comparison = await run_in_threadpool(
            _load_comparison, _context(request), *run_ids
        )
        runs = await run_in_threadpool(
            list_observation_runs,
            _context(request).database,
            limit=WEB_RUN_LIMIT,
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    if comparison is None:
        return _error("observer_run_not_found", 404)
    return _render_template(
        "comparison.html",
        comparison=comparison,
        revision=history_revision(runs),
        csrf_token=session.csrf_token,
    )


async def _comparison_detail(request: Request) -> Response:
    if _request_session(request) is None:
        return _error("observer_session_required", 401)
    run_ids = _comparison_ids(request)
    if run_ids is None:
        return _error("observer_comparison_selection_invalid", 400)
    try:
        comparison = await run_in_threadpool(
            _load_comparison, _context(request), *run_ids
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    if comparison is None:
        return _error("observer_run_not_found", 404)
    return JSONResponse({"status": "ok", "comparison": comparison})


async def _debug_context(request: Request) -> Response:
    session = _request_session(request)
    if session is None:
        return _error("observer_session_required", 401)
    try:
        loaded = await run_in_threadpool(
            _load_run_view,
            _context(request),
            session,
            request.path_params["run_id"],
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    if loaded is None:
        return _error("observer_run_not_found", 404)
    run, events, _ = loaded
    ordered = ordered_run_events(run.run_id, events)
    event_index = request.path_params["event_index"]
    if event_index < 0 or event_index >= len(ordered):
        return _error("observer_event_not_found", 404)
    evidence_state, _, _ = _evidence_view(session, run.run_id)
    return JSONResponse(
        build_debug_context(
            run,
            ordered[event_index],
            local_evidence=evidence_state,
        )
    )


async def _revision(request: Request) -> Response:
    if _request_session(request) is None:
        return _error("observer_session_required", 401)
    try:
        runs = await run_in_threadpool(
            list_observation_runs,
            _context(request).database,
            limit=WEB_RUN_LIMIT,
        )
    except ObservationStorageError as error:
        return _error(error.code, 503)
    return JSONResponse({"status": "ok", "revision": history_revision(runs)})


async def _stream(request: Request) -> Response:
    context = _context(request)
    session = _request_session(request)
    token = getattr(request.state, "observer_session_token", None)
    if session is None or not isinstance(token, str):
        return _error("observer_session_required", 401)

    async def events() -> AsyncIterator[str]:
        last_revision: str | None = None
        last_heartbeat = time.monotonic()
        yield "retry: 5000\n\n"
        while context.security.session(token, touch=False) is not None:
            if await request.is_disconnected():
                return
            try:
                runs = await run_in_threadpool(
                    list_observation_runs,
                    context.database,
                    limit=WEB_RUN_LIMIT,
                )
                revision = history_revision(runs)
                if revision != last_revision:
                    payload = json.dumps({"revision": revision}, separators=(",", ":"))
                    yield f"event: history\ndata: {payload}\n\n"
                    last_revision = revision
            except ObservationStorageError as error:
                payload = json.dumps({"failure": {"code": error.code}}, separators=(",", ":"))
                yield f"event: observer_error\ndata: {payload}\n\n"
            now = time.monotonic()
            if now - last_heartbeat >= STREAM_HEARTBEAT_SECONDS:
                yield ": keepalive\n\n"
                last_heartbeat = now
            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


async def _mount(request: Request) -> Response:
    session = _request_session(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    context = _context(request)
    run_id = request.path_params["run_id"]
    if context.selector is None:
        _note_evidence_failure(session, run_id, "picker_unavailable")
        return _error("picker_unavailable", 409)
    try:
        run = get_observation_run(context.database, run_id)
        if run is None:
            return _error("observer_run_not_found", 404)
        events = load_observation_events(context.database, run_id)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    try:
        selection = await run_in_threadpool(context.selector.select)
        result = await run_in_threadpool(verify_selected_task, run, events, selection)
    except Exception:
        _note_evidence_failure(session, run_id, "picker_unavailable")
        return _error("picker_unavailable", 409)
    if result.capability is not None:
        session.mounts[run_id] = result.capability
        session.evidence_states[run_id] = "available"
        if result.failure_code is None:
            session.evidence_failures.pop(run_id, None)
        else:
            session.evidence_failures[run_id] = result.failure_code
    else:
        failure_code = result.failure_code or "evidence_mount_unavailable"
        _note_evidence_failure(
            session,
            run_id,
            failure_code,
            state="conflict" if result.status == "conflict" else None,
        )
    return JSONResponse(
        {"status": result.status, "failure_code": result.failure_code},
        status_code=200 if result.status in {"verified", "partial"} else 409,
    )


async def _delete_run(request: Request) -> Response:
    session = _request_session(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    run_id = request.path_params["run_id"]
    try:
        deleted = delete_observation_run(_context(request).database, run_id)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    session.mounts.pop(run_id, None)
    session.evidence_states.pop(run_id, None)
    session.evidence_failures.pop(run_id, None)
    return JSONResponse({"status": "ok", "deleted": deleted})


async def _clear_history(request: Request) -> Response:
    session = _request_session(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    try:
        deleted = clear_observation_history(_context(request).database)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    session.mounts.clear()
    session.evidence_states.clear()
    session.evidence_failures.clear()
    return JSONResponse({"status": "ok", "deleted_runs": deleted})


async def _open_artifact(request: Request) -> Response:
    session = _request_session(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    context = _context(request)
    if context.opener is None:
        return _error("artifact_opener_unavailable", 409)
    run_id = request.path_params["run_id"]
    capability = session.mounts.get(run_id)
    if capability is None:
        return _error("evidence_mount_required", 409)
    locator = ARTIFACT_LOCATORS.get(request.path_params["artifact"])
    if locator is None:
        return _error("evidence_artifact_unknown", 404)
    try:
        path = resolve_task_locator(capability, locator)
        opened = await run_in_threadpool(context.opener.open, path)
    except EvidenceAccessError as error:
        _note_evidence_failure(session, run_id, error.code)
        return _error(error.code, 409)
    except Exception:
        return _error("artifact_opener_unavailable", 409)
    return JSONResponse({"status": "ok" if opened else "unavailable"})


def create_observer_app(
    database: Path,
    *,
    port: int,
    selector: DirectorySelector | None = None,
    opener: ArtifactOpener | None = None,
    clock: Callable[[], float] = time.monotonic,
    secure_cookie: bool = False,
) -> Starlette:
    """Build the testable Web core without importing a platform adapter."""

    expected_host = f"127.0.0.1:{port}"
    context = ObserverWebContext(
        database,
        expected_host,
        f"http://{expected_host}",
        ObserverSecurityState(clock=clock),
        selector,
        opener,
        secure_cookie,
    )
    app = Starlette(
        debug=False,
        routes=[
            Route("/", _root, methods=["GET", "HEAD"]),
            Route("/static/{asset:str}", _static_asset, methods=["GET", "HEAD"]),
            Route("/runs/{run_id:str}", _run_page, methods=["GET", "HEAD"]),
            Route("/compare", _comparison_page, methods=["GET", "HEAD"]),
            Route("/api/runs", _runs, methods=["GET", "HEAD"]),
            Route("/api/compare", _comparison_detail, methods=["GET", "HEAD"]),
            Route(
                "/api/runs/{run_id:str}",
                _run_detail,
                methods=["GET", "HEAD"],
            ),
            Route(
                "/api/runs/{run_id:str}/debug/{event_index:int}",
                _debug_context,
                methods=["GET", "HEAD"],
            ),
            Route("/api/revision", _revision, methods=["GET", "HEAD"]),
            Route("/api/stream", _stream, methods=["GET"]),
            Route("/api/runs/{run_id:str}/mount", _mount, methods=["POST"]),
            Route("/api/runs/{run_id:str}/delete", _delete_run, methods=["POST"]),
            Route("/api/history/clear", _clear_history, methods=["POST"]),
            Route(
                "/api/runs/{run_id:str}/open/{artifact:str}",
                _open_artifact,
                methods=["POST"],
            ),
        ],
    )
    app.state.observer_context = context

    app.add_middleware(SecurityBoundaryMiddleware, context=context)

    return app


def build_observer_server(
    app: Starlette,
    listener: socket.socket,
) -> uvicorn.Server:
    """Return a locked-down Uvicorn server for one pre-bound loopback socket."""

    host, port = listener.getsockname()[:2]
    if host != "127.0.0.1":
        raise ValueError("observer_non_loopback_socket")
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        access_log=False,
        proxy_headers=False,
        forwarded_allow_ips="",
        server_header=False,
        date_header=False,
        ws="none",
        workers=1,
        lifespan="off",
        log_level="warning",
    )
    return uvicorn.Server(config)


def _default_selector() -> DirectorySelector | None:
    if sys.platform != "darwin":
        return None
    try:
        from docfit.observability.local_debug.macos import MacOSDirectoryPicker
    except ImportError:
        return None
    return MacOSDirectoryPicker()


def _default_opener() -> ArtifactOpener | None:
    if sys.platform != "darwin":
        return None
    try:
        from docfit.observability.local_debug.macos import MacOSArtifactOpener
    except ImportError:
        return None
    return MacOSArtifactOpener()


def _startup_error(code: str, *, stream: IO[str]) -> int:
    print(
        json.dumps(
            {
                "schema_version": 1,
                "status": "error",
                "failure": {"origin": "app", "code": code, "retryable": False},
            },
            sort_keys=True,
        ),
        file=stream,
    )
    return 2


def run_observer_server(
    *,
    port: int,
    output_stream: IO[str] | None = None,
) -> int:
    """Start a loopback-only observer that opens directly without a login step."""

    output_stream = sys.stderr if output_stream is None else output_stream
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        listener.set_inheritable(False)
        actual_port = int(listener.getsockname()[1])
        database = initialize_observation_store(observation_state_root())
        app = create_observer_app(
            database,
            port=actual_port,
            selector=_default_selector(),
            opener=_default_opener(),
        )
        print(f"DocFit observer: http://127.0.0.1:{actual_port}/", file=output_stream)
        try:
            build_observer_server(app, listener).run(sockets=[listener])
        except KeyboardInterrupt:
            return 0
        return 0
    except (OSError, ObservationStorageError, ValueError):
        return _startup_error("observer_startup_failed", stream=output_stream)
    finally:
        listener.close()
