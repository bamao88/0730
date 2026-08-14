from __future__ import annotations

import json
from pathlib import Path

import pytest

from template_extraction_eval.runner import run_evaluation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"


def _run(sample: str, output: Path):  # type: ignore[no-untyped-def]
    root = FIXTURES / sample
    return run_evaluation(
        root / "case.yaml",
        root / "actual-template.docx",
        root / "actual-contract.yaml",
        output_dir=output,
    )


def test_run_01_pass_writes_two_valid_reports(tmp_path: Path) -> None:
    result = _run("S00-minimal-pass", tmp_path / "pass")
    assert (result.status, result.score) == ("PASS", 100)
    assert result.report_json is not None and result.report_json.is_file()
    assert result.report_markdown is not None and result.report_markdown.is_file()


@pytest.mark.parametrize(
    ("sample", "expected_status"),
    [
        ("S01-protected-text-changed", "FAIL"),
        ("S10-unsupported-object", "UNKNOWN"),
    ],
    ids=["fail", "unknown"],
)
def test_run_02_and_03_quality_statuses_publish_reports(
    sample: str,
    expected_status: str,
    tmp_path: Path,
) -> None:
    result = _run(sample, tmp_path / sample)
    assert result.status == expected_status
    assert result.report_json is not None
    report = json.loads(result.report_json.read_text(encoding="utf-8"))
    assert report["status"] == expected_status


def test_run_04_input_error_publishes_no_quality_report(tmp_path: Path) -> None:
    output = tmp_path / "invalid"
    result = _run("S11-invalid-input", output)
    assert result.status == "INPUT_ERROR"
    assert result.score is None
    assert result.input_error is not None
    assert not output.exists()


def test_run_05_repeated_run_is_business_deterministic(tmp_path: Path) -> None:
    first = _run("S00-minimal-pass", tmp_path / "first")
    second = _run("S00-minimal-pass", tmp_path / "second")
    assert first.run_id == second.run_id
    assert first.report_json is not None and second.report_json is not None
    assert first.report_json.read_bytes() == second.report_json.read_bytes()
