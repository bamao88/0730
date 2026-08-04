"""Fail-closed loopback Web security shell for local observation history."""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, cast

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from docfit.observability.evidence import (
    ARTIFACT_LOCATORS,
    ArtifactOpener,
    DirectorySelector,
    EvidenceAccessError,
    MountedEvidenceCapability,
    resolve_task_locator,
    verify_selected_task,
)
from docfit.observability.storage import (
    ObservationStorageError,
    clear_observation_history,
    delete_observation_run,
    get_observation_run,
    initialize_observation_store,
    list_observation_runs,
    load_observation_events,
    observation_state_root,
)

SESSION_COOKIE = "docfit_observer_session"
LOGIN_HEADER = "x-docfit-login-code"
CSRF_HEADER = "x-docfit-csrf"
LOGIN_LIFETIME_SECONDS = 5 * 60
LOGIN_MAX_FAILURES = 5
SESSION_IDLE_SECONDS = 30 * 60
SESSION_ABSOLUTE_SECONDS = 8 * 60 * 60
LOGIN_TOKEN_BYTES = 16
SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
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


class ObserverSecurityState:
    """In-memory login/session/mount authority; no secret or path is persisted."""

    def __init__(
        self,
        *,
        login_code: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._login_digest = _token_digest(login_code)
        self._login_created_at = clock()
        self._login_failures = 0
        self._login_consumed = False
        self._clock = clock
        self._sessions: dict[str, ObserverSession] = {}

    def exchange_login(self, candidate: str | None) -> tuple[str, ObserverSession] | None:
        now = self._clock()
        if (
            self._login_consumed
            or self._login_failures >= LOGIN_MAX_FAILURES
            or now - self._login_created_at >= LOGIN_LIFETIME_SECONDS
        ):
            return None
        if candidate is None or not secrets.compare_digest(
            _token_digest(candidate), self._login_digest
        ):
            self._login_failures += 1
            return None
        self._login_consumed = True
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
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


def _authenticated(request: Request, *, csrf: bool = False) -> ObserverSession | None:
    context = _context(request)
    session = context.security.session(request.cookies.get(SESSION_COOKIE))
    if session is None:
        return None
    if csrf and not secrets.compare_digest(
        request.headers.get(CSRF_HEADER, ""), session.csrf_token
    ):
        return None
    return session


async def _root(request: Request) -> Response:
    authenticated = _context(request).security.session(
        request.cookies.get(SESSION_COOKIE), touch=False
    ) is not None
    return JSONResponse({"status": "ready", "authenticated": authenticated})


async def _login(request: Request) -> Response:
    if request.url.query:
        return _error("observer_login_query_rejected", 400)
    exchange = _context(request).security.exchange_login(request.headers.get(LOGIN_HEADER))
    if exchange is None:
        return _error("observer_login_rejected", 401)
    token, session = exchange
    response = JSONResponse({"status": "ok", "csrf_token": session.csrf_token})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_ABSOLUTE_SECONDS,
        httponly=True,
        secure=_context(request).secure_cookie,
        samesite="strict",
        path="/",
    )
    return response


async def _runs(request: Request) -> Response:
    if _authenticated(request) is None:
        return _error("observer_session_required", 401)
    try:
        runs = list_observation_runs(_context(request).database, limit=500)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    return JSONResponse(
        {
            "status": "ok",
            "runs": [
                {
                    "run_id": run.run_id,
                    "task_ref": run.task_ref,
                    "session_id": run.session_id,
                    "status": run.status,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "last_observed_at": run.last_observed_at,
                    "event_count": run.event_count,
                    "event_bytes": run.event_bytes,
                }
                for run in runs
            ],
        }
    )


async def _mount(request: Request) -> Response:
    session = _authenticated(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    context = _context(request)
    if context.selector is None:
        return _error("picker_unavailable", 409)
    run_id = request.path_params["run_id"]
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
        return _error("picker_unavailable", 409)
    if result.capability is not None:
        session.mounts[run_id] = result.capability
    return JSONResponse(
        {"status": result.status, "failure_code": result.failure_code},
        status_code=200 if result.status in {"verified", "partial"} else 409,
    )


async def _delete_run(request: Request) -> Response:
    session = _authenticated(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    run_id = request.path_params["run_id"]
    try:
        deleted = delete_observation_run(_context(request).database, run_id)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    session.mounts.pop(run_id, None)
    return JSONResponse({"status": "ok", "deleted": deleted})


async def _clear_history(request: Request) -> Response:
    session = _authenticated(request, csrf=True)
    if session is None:
        return _error("observer_authorization_failed", 403)
    try:
        deleted = clear_observation_history(_context(request).database)
    except ObservationStorageError as error:
        return _error(error.code, 503)
    session.mounts.clear()
    return JSONResponse({"status": "ok", "deleted_runs": deleted})


async def _open_artifact(request: Request) -> Response:
    session = _authenticated(request, csrf=True)
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
        session.mounts.pop(run_id, None)
        return _error(error.code, 409)
    except Exception:
        return _error("artifact_opener_unavailable", 409)
    return JSONResponse({"status": "ok" if opened else "unavailable"})


def create_observer_app(
    database: Path,
    *,
    port: int,
    login_code: str,
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
        ObserverSecurityState(login_code=login_code, clock=clock),
        selector,
        opener,
        secure_cookie,
    )
    app = Starlette(
        debug=False,
        routes=[
            Route("/", _root, methods=["GET", "HEAD"]),
            Route("/login", _login, methods=["POST"]),
            Route("/api/runs", _runs, methods=["GET", "HEAD"]),
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
    input_stream: IO[str] | None = None,
    output_stream: IO[str] | None = None,
) -> int:
    """Start only with an interactive TTY; never move the login secret to a URL."""

    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stderr if output_stream is None else output_stream
    if not input_stream.isatty() or not output_stream.isatty():
        return _startup_error("observer_interactive_tty_required", stream=output_stream)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        listener.set_inheritable(False)
        actual_port = int(listener.getsockname()[1])
        database = initialize_observation_store(observation_state_root())
        login_code = secrets.token_urlsafe(LOGIN_TOKEN_BYTES)
        app = create_observer_app(
            database,
            port=actual_port,
            login_code=login_code,
            selector=_default_selector(),
            opener=_default_opener(),
        )
        print(f"DocFit observer: http://127.0.0.1:{actual_port}/", file=output_stream)
        print(f"One-time login code: {login_code}", file=output_stream)
        build_observer_server(app, listener).run(sockets=[listener])
        return 0
    except (OSError, ObservationStorageError, ValueError):
        return _startup_error("observer_startup_failed", stream=output_stream)
    finally:
        listener.close()
