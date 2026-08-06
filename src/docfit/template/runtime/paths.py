"""Path authorization for template extraction tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.tools.runtime import ToolFailure, authorized_path, require_docx


def task_file(
    value: Any,
    *,
    task_root: Path,
    field: str,
    allowed_roots: tuple[str, ...] = ("input", "work"),
    suffix: str | None = None,
) -> Path:
    path = authorized_path(value, task_root=task_root, field=field)
    relative = path.relative_to(task_root)
    if not relative.parts or relative.parts[0] not in allowed_roots:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="input_path_outside_task_root",
            message=f"{field} must be inside an authorized task input or work directory.",
        )
    if path.is_symlink():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="symlink_input_denied",
            message=f"{field} cannot identify a symbolic link.",
        )
    if suffix == ".docx":
        require_docx(path, field=field)
    elif suffix is not None and path.suffix.casefold() != suffix.casefold():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="unsupported_file_type",
            message=f"{field} must be a {suffix} file.",
        )
    return path
