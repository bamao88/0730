"""Optional macOS directory picker for the local debugging shell."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from docfit.observability.evidence import DirectorySelection

PickerRunner = Callable[[Sequence[str], str, float], subprocess.CompletedProcess[str]]
OpenerRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[bytes]]


def _run_picker(
    arguments: Sequence[str], script: str, timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(arguments),
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _run_opener(
    arguments: Sequence[str], timeout: float
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


class MacOSDirectoryPicker:
    """Invoke the macOS picker without accepting a browser-supplied path."""

    def __init__(
        self,
        *,
        platform_name: str = sys.platform,
        runner: PickerRunner = _run_picker,
        executable: Path = Path("/usr/bin/osascript"),
    ) -> None:
        self._platform_name = platform_name
        self._runner = runner
        self._executable = executable

    def select(self) -> DirectorySelection:
        if self._platform_name != "darwin" or not self._executable.is_file():
            return DirectorySelection(
                status="unavailable",
                failure_code="picker_unavailable",
            )
        script = 'POSIX path of (choose folder with prompt "Select a DocFit task directory")'
        try:
            completed = self._runner([str(self._executable), "-"], script, 120.0)
        except (OSError, subprocess.SubprocessError):
            return DirectorySelection(
                status="unavailable",
                failure_code="picker_unavailable",
            )
        if completed.returncode != 0:
            return DirectorySelection(
                status="cancelled" if "-128" in completed.stderr else "unavailable",
                failure_code=(
                    "picker_cancelled" if "-128" in completed.stderr else "picker_unavailable"
                ),
            )
        raw_path = completed.stdout.strip()
        try:
            selected = Path(raw_path).expanduser().resolve(strict=True)
        except (FileNotFoundError, OSError):
            return DirectorySelection(status="invalid", failure_code="picker_invalid_selection")
        if not selected.is_dir():
            return DirectorySelection(status="invalid", failure_code="picker_invalid_selection")
        return DirectorySelection(status="selected", path=selected)


class MacOSArtifactOpener:
    """Reveal a pre-verified artifact without returning its path to the browser."""

    def __init__(
        self,
        *,
        platform_name: str = sys.platform,
        runner: OpenerRunner = _run_opener,
        executable: Path = Path("/usr/bin/open"),
    ) -> None:
        self._platform_name = platform_name
        self._runner = runner
        self._executable = executable

    def open(self, path: Path) -> bool:
        if (
            self._platform_name != "darwin"
            or not self._executable.is_file()
            or not path.is_file()
            or path.is_symlink()
        ):
            return False
        try:
            completed = self._runner(
                [str(self._executable), "-R", str(path)],
                10.0,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0
