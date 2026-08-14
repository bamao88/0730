from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"
ENTRYPOINT = PROJECT_ROOT / "run_eval.py"


def _run(sample: str, output: Path) -> subprocess.CompletedProcess[str]:
    root = FIXTURES / sample
    return subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--case",
            str(root / "case.yaml"),
            "--actual-template",
            str(root / "actual-template.docx"),
            "--actual-contract",
            str(root / "actual-contract.yaml"),
            "--output-dir",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_01_pass_exits_zero_and_prints_json(tmp_path: Path) -> None:
    result = _run("S00-minimal-pass", tmp_path / "pass")
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PASS"


@pytest.mark.parametrize(
    ("sample", "status"),
    [
        ("S01-protected-text-changed", "FAIL"),
        ("S10-unsupported-object", "UNKNOWN"),
    ],
    ids=["fail", "unknown"],
)
def test_cli_02_and_03_quality_nonpass_exits_two(
    sample: str,
    status: str,
    tmp_path: Path,
) -> None:
    result = _run(sample, tmp_path / sample)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == status


def test_cli_04_input_error_exits_three_and_uses_stderr(tmp_path: Path) -> None:
    result = _run("S11-invalid-input", tmp_path / "invalid")
    assert result.returncode == 3
    assert result.stdout == ""
    diagnostic = json.loads(result.stderr)
    assert diagnostic["status"] == "INPUT_ERROR"
    assert diagnostic["report_json"] is None
