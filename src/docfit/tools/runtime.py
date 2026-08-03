"""Shared safety and evidence helpers for the five DocFit Tools."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

JsonObject = dict[str, Any]
ToolStatus = Literal["ok", "needs_input", "error"]


class ToolFailure(Exception):
    """An expected, normalized Tool failure."""

    def __init__(
        self,
        *,
        status: Literal["needs_input", "error"],
        origin: str,
        code: str,
        message: str,
        retryable: bool = False,
        suggested_actions: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.status = status
        self.origin = origin
        self.code = code
        self.message = message
        self.retryable = retryable
        self.suggested_actions = tuple(suggested_actions)

    def result(self, *, committed: bool | None = None) -> JsonObject:
        result: JsonObject = {
            "schema_version": 1,
            "status": self.status,
            "checks": [],
            "warnings": [],
            "failure": {
                "origin": self.origin,
                "code": self.code,
                "retryable": self.retryable,
                "message": self.message,
                "suggested_actions": list(self.suggested_actions),
            },
        }
        if committed is not None:
            result["committed"] = committed
        return result


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def task_root_from_args(args: Mapping[str, Any]) -> Path:
    candidate = args.get("task_root") or os.environ.get("DOCFIT_TASK_ROOT") or os.getcwd()
    if not isinstance(candidate, str):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_task_root",
            message="task_root must be a path string.",
        )
    root = Path(candidate).expanduser().resolve()
    if not root.is_dir():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="task_root_not_found",
            message="The authorized task root does not exist or is not a directory.",
        )
    return root


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def authorized_path(
    value: Any,
    *,
    task_root: Path,
    field: str,
    must_exist: bool = True,
    expect_directory: bool = False,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="missing_path",
            message=f"{field} must be a non-empty path string.",
        )
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else task_root / raw
    if must_exist:
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="path_not_found",
                message=f"{field} does not exist inside the authorized task root.",
            ) from error
    else:
        try:
            parent = candidate.parent.resolve(strict=True)
        except FileNotFoundError as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="parent_not_found",
                message=f"The parent directory for {field} does not exist.",
            ) from error
        resolved = parent / candidate.name
    if not _within(resolved, task_root):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="path_not_authorized",
            message=f"{field} is outside the authorized task root.",
        )
    read_only_input = task_root / "input"
    if not must_exist and read_only_input.is_dir() and _within(resolved, read_only_input):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="input_directory_read_only",
            message=f"{field} cannot publish into the task input directory.",
        )
    if must_exist:
        correct_kind = resolved.is_dir() if expect_directory else resolved.is_file()
        if not correct_kind:
            expected = "directory" if expect_directory else "file"
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="wrong_path_kind",
                message=f"{field} must identify a {expected}.",
            )
    return resolved


def require_docx(path: Path, *, field: str) -> None:
    if path.suffix.casefold() != ".docx":
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_document_type",
            message=f"{field} must be a .docx file.",
        )


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_json",
            message="The referenced JSON evidence file cannot be read.",
        ) from error
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_json_shape",
            message="The referenced JSON evidence must be an object.",
        )
    return value


def provider_evidence(name: str, version: str, executable: Path) -> JsonObject:
    return {
        "name": name,
        "version": version,
        "executable_sha256": sha256_file(executable),
        "environment": {
            "platform": os.uname().sysname,
            "architecture": os.uname().machine,
        },
    }
