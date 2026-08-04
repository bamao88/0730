from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from pathlib import Path

from docfit.observability.storage import initialize_observation_store
from docfit.observability.web import (
    LOGIN_HEADER,
    build_observer_server,
    create_observer_app,
)


def test_real_loopback_server_exchanges_login_and_reads_empty_history(
    tmp_path: Path,
) -> None:
    database = initialize_observation_store(tmp_path / "state")
    login_code = "synthetic-one-time-login"
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = int(listener.getsockname()[1])
    origin = f"http://127.0.0.1:{port}"
    app = create_observer_app(
        database,
        port=port,
        login_code=login_code,
    )
    server = build_observer_server(app, listener)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5.0
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
    try:
        connection.request(
            "POST",
            "/login",
            headers={
                "Host": f"127.0.0.1:{port}",
                "Origin": origin,
                LOGIN_HEADER: login_code,
                "Content-Length": "0",
            },
        )
        login = connection.getresponse()
        login_payload = json.loads(login.read())
        cookie = login.getheader("Set-Cookie")
        assert login.status == 200
        assert cookie is not None
        assert login.getheader("Server") is None
        assert login.getheader("Date") is None
        assert login.getheader("Access-Control-Allow-Origin") is None
        assert login_code not in json.dumps(login_payload)

        connection.request(
            "GET",
            "/api/runs",
            headers={
                "Host": f"127.0.0.1:{port}",
                "Cookie": cookie.split(";", 1)[0],
            },
        )
        history = connection.getresponse()
        history_payload = json.loads(history.read())

        assert history.status == 200
        assert history_payload == {"status": "ok", "runs": []}
    finally:
        connection.close()
        server.should_exit = True
        thread.join(timeout=5.0)
        listener.close()

    assert not thread.is_alive()
