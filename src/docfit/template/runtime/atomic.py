"""No-replace atomic publication helpers."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from docfit.tools.runtime import ToolFailure, canonical_json


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json_file(path: Path, payload: Any) -> None:
    """Write canonical JSON to a new path and durably flush it."""
    if path.exists():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="output_exists",
            message="The requested publication target already exists.",
        )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(payload))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def publish_json_directory(
    target: Path,
    files: dict[str, Any],
) -> None:
    """Publish a complete directory without replacing an existing target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        for name, payload in files.items():
            write_json_file(temporary / name, payload)
        _fsync_directory(temporary)
        try:
            os.rename(temporary, target)
        except FileExistsError as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="output_exists",
                message="The requested publication target already exists.",
            ) from error
        _fsync_directory(target.parent)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
