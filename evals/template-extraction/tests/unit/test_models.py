from __future__ import annotations

import pytest

from template_extraction_eval.models import (
    AssertionResult,
    AssertionStatus,
    DimensionScore,
    EvalReport,
    Issue,
    Locator,
    Severity,
    Verdict,
    View,
    ViewScore,
    stable_data,
)


def test_mod_01_pass_assertion_and_score_are_constructible() -> None:
    assertion = AssertionResult(
        assertion_id="protected.label.content",
        view=View.PROTECTED,
        dimension="protected.content",
        status=AssertionStatus.PASS,
        required=True,
    )
    score = DimensionScore("protected.content", 20, 20, 1, 0, 0, 0)
    assert assertion.status is AssertionStatus.PASS
    assert score.score == score.weight == 20


def test_mod_02_issue_serialization_contains_actionable_evidence() -> None:
    locator = Locator(
        type="text_anchor",
        story="document",
        part="word/document.xml",
        expected_match_count=1,
        left_anchor="姓名：",
        occurrence=1,
    )
    issue = Issue(
        issue_id="ISS-0001",
        severity=Severity.ERROR,
        view=View.SLOT,
        dimension="slot.field_mapping",
        assertion_id="slot.cover.student_name.field_id",
        status=AssertionStatus.FAIL,
        message="field mismatch",
        slot_id="slot.cover.student_name",
        gold_locator=locator,
        expected="author.name.zh",
        actual="author.student_id",
    )
    serialized = stable_data(issue)
    assert serialized["gold_locator"]["left_anchor"] == "姓名："
    assert serialized["expected"] == "author.name.zh"
    assert serialized["actual"] == "author.student_id"


def test_mod_03_unknown_report_is_provisional_and_invalid_status_is_rejected() -> None:
    report = EvalReport(
        schema_version="docfit-template-extraction-eval-report/v1",
        case_id="s10-unsupported-object",
        run_id="run-test",
        status=Verdict.UNKNOWN,
        total_score=100,
        provisional=True,
        analysis_coverage=0.5,
        views=(ViewScore(View.PROTECTED, 50, 50), ViewScore(View.SLOT, 50, 50)),
        dimensions=(),
        issues=(),
        inputs={},
        config={},
    )
    assert report.provisional is True
    assert stable_data(report)["status"] == "UNKNOWN"
    with pytest.raises(ValueError):
        AssertionStatus("INVALID")
