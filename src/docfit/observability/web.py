"""Fail-closed O0.0 CLI placeholder for the future authenticated Web shell."""

from __future__ import annotations

import json
import sys


def run_observer_server(*, port: int) -> int:
    """Refuse to expose an unauthenticated management surface before O0.5."""

    payload = {
        "schema_version": 1,
        "status": "error",
        "failure": {
            "origin": "app",
            "code": "observer_web_not_ready",
            "retryable": False,
        },
        "port": port,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 2
