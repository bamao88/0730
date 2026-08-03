from __future__ import annotations

import subprocess
from pathlib import Path

from docfit.observability.evidence import NativeDirectoryPicker


def test_picker_is_unavailable_without_supported_gui_platform(tmp_path: Path) -> None:
    picker = NativeDirectoryPicker(platform_name="linux", executable=tmp_path / "missing")

    result = picker.select()

    assert result.status == "unavailable"
    assert result.failure_code == "picker_unavailable"
    assert result.path is None


def test_picker_returns_server_side_selected_directory(tmp_path: Path) -> None:
    executable = tmp_path / "osascript"
    executable.write_text("synthetic", encoding="utf-8")
    selected = tmp_path / "task"
    selected.mkdir()
    calls: list[tuple[list[str], str, float]] = []

    def run(
        arguments: object, script: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        normalized = [str(item) for item in arguments]  # type: ignore[union-attr]
        calls.append((normalized, script, timeout))
        return subprocess.CompletedProcess(normalized, 0, f"{selected}\n", "")

    picker = NativeDirectoryPicker(
        platform_name="darwin",
        runner=run,
        executable=executable,
    )

    result = picker.select()

    assert result.status == "selected"
    assert result.path == selected.resolve()
    assert calls == [
        (
            [str(executable), "-"],
            'POSIX path of (choose folder with prompt "Select a DocFit task directory")',
            120.0,
        )
    ]


def test_picker_cancellation_does_not_return_a_path(tmp_path: Path) -> None:
    executable = tmp_path / "osascript"
    executable.write_text("synthetic", encoding="utf-8")

    def cancel(
        arguments: object, script: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        del script, timeout
        return subprocess.CompletedProcess(arguments, 1, "", "execution error -128")

    result = NativeDirectoryPicker(
        platform_name="darwin",
        runner=cancel,
        executable=executable,
    ).select()

    assert result.status == "cancelled"
    assert result.path is None
    assert result.failure_code == "picker_cancelled"


def test_picker_api_accepts_no_browser_path_argument(tmp_path: Path) -> None:
    picker = NativeDirectoryPicker(platform_name="linux", executable=tmp_path / "missing")

    try:
        picker.select(tmp_path)  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        raise AssertionError("picker accepted a caller-supplied path")
