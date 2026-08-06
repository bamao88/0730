from __future__ import annotations

import json
from pathlib import Path

from template_extraction_eval.contracts import load_scoring_config
from template_extraction_eval.models import (
    AssertionResult,
    AssertionStatus,
    View,
)
from template_extraction_eval.reporting import (
    build_report,
    issues_from_assertions,
    report_markdown,
    report_to_dict,
    validate_report,
    write_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_scoring_config(PROJECT_ROOT / "config" / "scoring-v1.yaml")
HASH = "a" * 64


def _assertions() -> tuple[AssertionResult, ...]:
    return (
        AssertionResult(
            "z-pass",
            View.SLOT,
            "slot.inventory",
            AssertionStatus.PASS,
            True,
            message="pass",
        ),
        AssertionResult(
            "b-unknown",
            View.PROTECTED,
            "protected.object",
            AssertionStatus.UNKNOWN,
            True,
            message="unsupported",
        ),
        AssertionResult(
            "a-fail",
            View.PROTECTED,
            "protected.content",
            AssertionStatus.FAIL,
            True,
            message="changed",
        ),
    )


def _report():  # type: ignore[no-untyped-def]
    return build_report(
        case_id="report-test",
        run_id="fixed-run",
        assertions=_assertions(),
        input_hashes={
            "actual_template": HASH,
            "actual_contract": HASH,
            "gold_template": HASH,
            "gold_contract": HASH,
        },
        report_config={
            "scoring_version": CONFIG.scoring_version,
            "scoring_config_sha256": HASH,
            "eval_config_id": "synthetic-v1",
            "eval_config_version": "docfit-template-extraction-eval-config/v1",
            "eval_config_sha256": HASH,
            "marker_protocol": "docfit-content-control-marker/v1",
            "tolerances": {"distance_pt": 0.05},
            "normalization": ("ignore_zip_timestamps",),
            "registry_id": "registry",
            "registry_version": "1",
            "registry_sha256": HASH,
            "schemas": {
                "case": "docfit-template-extraction-case/v1",
                "actual_contract": "docfit-template-fill-contract/v1",
                "gold_contract": "docfit-template-fill-contract/v1",
            },
        },
        scoring_config=CONFIG,
    )


def test_rep_01_issues_are_stable_and_only_fail_or_unknown() -> None:
    issues = issues_from_assertions(_assertions())
    assert [item.issue_id for item in issues] == ["ISS-0001", "ISS-0002"]
    assert [item.assertion_id for item in issues] == ["a-fail", "b-unknown"]


def test_rep_02_report_dict_validates_against_public_schema() -> None:
    report = _report()
    validate_report(report)
    data = report_to_dict(report)
    assert data["status"] == "FAIL"
    assert data["score"]["provisional"] is True
    assert "total_score" not in data


def test_rep_03_json_and_markdown_share_score_and_issue_count(tmp_path: Path) -> None:
    report = _report()
    json_path, markdown_path = write_report(report, tmp_path / "result")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert f"{data['score']['total']:.4f}/100" in markdown
    assert markdown.count("- `ISS-") == len(data["issues"])


def test_rep_04_markdown_contains_no_full_input_document() -> None:
    markdown = report_markdown(_report())
    assert "Dimension scores" in markdown
    assert "actual_template" not in markdown
