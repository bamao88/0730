"""Concrete OfficeCLI adapter; this is intentionally not a Provider abstraction."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docfit.tools.runtime import JsonObject, ToolFailure, provider_evidence

OFFICECLI_EXPECTED_VERSION = "1.0.143"
OFFICECLI_EXPECTED_SHA256 = "2f158d46f9b6c5eb0dfe4eb02038114001e17acc47b67347417c56dcf9659096"


@dataclass(frozen=True, slots=True)
class OfficeCliResult:
    data: Any
    message: str | None = None


class OfficeCliAdapter:
    """Safe argv-only access to the fixed OfficeCLI backend."""

    def __init__(self, executable: Path | None = None, *, timeout_seconds: int = 60) -> None:
        resolved = executable
        if resolved is None:
            found = shutil.which("officecli")
            if found is None:
                raise ToolFailure(
                    status="error",
                    origin="environment",
                    code="officecli_not_found",
                    message="OfficeCLI is not installed in the current environment.",
                    suggested_actions=("install_locked_officecli",),
                )
            resolved = Path(found)
        self.executable = resolved.resolve()
        self.timeout_seconds = timeout_seconds
        self.version = self._read_version()

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["OFFICECLI_SKIP_UPDATE"] = "1"
        environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
        return environment

    def _run_raw(
        self,
        arguments: list[str],
        *,
        stdin: str | None = None,
        timeout_seconds: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                [str(self.executable), *arguments],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._environment(),
                timeout=timeout_seconds or self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolFailure(
                status="error",
                origin="engine",
                code="officecli_timeout",
                message="OfficeCLI did not finish within the configured timeout.",
                retryable=True,
                suggested_actions=("retry_smaller_batch", "report_backend_failure"),
            ) from error
        except OSError as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="officecli_launch_failed",
                message="OfficeCLI could not be started.",
                retryable=False,
                suggested_actions=("repair_officecli_installation",),
            ) from error
        if completed.returncode != 0:
            raise ToolFailure(
                status="error",
                origin="engine",
                code="officecli_failed",
                message="OfficeCLI rejected the operation or returned a backend error.",
                retryable=False,
                suggested_actions=("inspect_request", "report_backend_failure"),
            )
        return completed

    def _read_version(self) -> str:
        completed = self._run_raw(["--version"])
        version = completed.stdout.strip()
        if not version:
            raise ToolFailure(
                status="error",
                origin="adapter",
                code="officecli_version_missing",
                message="OfficeCLI returned no version evidence.",
            )
        return version

    def _run_json(
        self,
        arguments: list[str],
        *,
        stdin: str | None = None,
        timeout_seconds: int | None = None,
    ) -> OfficeCliResult:
        completed = self._run_raw(
            [*arguments, "--json"],
            stdin=stdin,
            timeout_seconds=timeout_seconds,
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ToolFailure(
                status="error",
                origin="adapter",
                code="officecli_malformed_json",
                message="OfficeCLI returned malformed structured output.",
            ) from error
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ToolFailure(
                status="error",
                origin="engine",
                code="officecli_unsuccessful",
                message="OfficeCLI did not confirm the requested operation.",
            )
        message = payload.get("message")
        return OfficeCliResult(
            payload.get("data"),
            message if isinstance(message, str) else None,
        )

    def evidence(self) -> JsonObject:
        evidence = provider_evidence("officecli", self.version, self.executable)
        evidence["expected_version"] = OFFICECLI_EXPECTED_VERSION
        evidence["version_locked"] = self.version == OFFICECLI_EXPECTED_VERSION
        evidence["license"] = "Apache-2.0"
        return evidence

    def query(self, document: Path, selector: str) -> tuple[JsonObject, ...]:
        result = self._run_json(["query", str(document), selector])
        if not isinstance(result.data, dict):
            raise ToolFailure(
                status="error",
                origin="adapter",
                code="officecli_query_shape",
                message="OfficeCLI query output has an unsupported shape.",
            )
        values = result.data.get("results")
        if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
            raise ToolFailure(
                status="error",
                origin="adapter",
                code="officecli_query_results_missing",
                message="OfficeCLI query output contains no structured results.",
            )
        return tuple(values)

    def get_document(self, document: Path) -> JsonObject:
        result = self._run_json(["get", str(document), "/", "--depth", "4"])
        if not isinstance(result.data, dict):
            raise ToolFailure(
                status="error",
                origin="adapter",
                code="officecli_document_shape",
                message="OfficeCLI document metadata has an unsupported shape.",
            )
        values = result.data.get("results")
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise ToolFailure(
                status="error",
                origin="adapter",
                code="officecli_document_missing",
                message="OfficeCLI did not return one document root.",
            )
        return values[0]

    def batch(self, document: Path, commands: list[JsonObject]) -> JsonObject:
        result = self._run_json(
            ["batch", str(document), "--stop-on-error"],
            stdin=json.dumps(commands, ensure_ascii=False),
        )
        return result.data if isinstance(result.data, dict) else {"result": result.data}

    def validate(self, document: Path) -> JsonObject:
        result = self._run_json(["validate", str(document)])
        return {
            "passed": True,
            "detail": result.message or "OfficeCLI OpenXML validation passed.",
        }
