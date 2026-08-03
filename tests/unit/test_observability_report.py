from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfit.observability.models import SDKTranscriptSummary
from docfit.observability.report import (
    ConversionReportError,
    load_conversion_report,
    project_conversion_report,
)
from docfit.observability.transcript import transcript_summary_safely

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def _v1() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "COMPLETED",
        "output_directory": "/private/task/PAPER_CANARY",
        "final_docx": "/private/task/PAPER_CANARY.docx",
        "source_sha256": HASH_A,
        "template_sha256": HASH_B,
        "requirements_sha256": HASH_C,
        "knowledge_version": "v1",
        "knowledge_digest": f"sha256:{HASH_D}",
        "backend": "synthetic-backend",
        "session_id": "session-123",
        "tool_uses": ["mcp__docfit__docx_inspect"],
        "warnings": ["PAPER_CANARY"],
        "detail": "PAPER_CANARY complete prose",
    }


def _v2() -> dict[str, object]:
    return {
        **_v1(),
        "schema_version": 2,
        "run_id": "run_0123456789abcdef0123456789abcdef",
        "task_ref": "task_fedcba9876543210fedcba9876543210",
        "final_sha256": HASH_D,
        "observation_coverage": {
            "state": "unavailable",
            "events_persisted": None,
            "events_dropped": None,
            "missing_sources": [],
            "last_observed_at": None,
            "failure_codes": ["observation_disabled"],
        },
        "sdk_transcript": {
            "status": "cleaned",
            "residual_count": 0,
            "oldest_age_bucket": None,
            "failure_codes": [],
        },
    }


def test_v1_projects_missing_observation_values_as_unknown_not_zero() -> None:
    projected = project_conversion_report(_v1())

    assert projected["association"] == "partial"
    assert projected["run_id"] is None
    assert projected["observation_coverage"]["state"] == "unavailable"
    assert projected["observation_coverage"]["events_persisted"] is None
    assert projected["sdk_transcript"]["status"] == "unknown"
    assert projected["sdk_transcript"]["residual_count"] is None


def test_v2_projection_is_direct_and_excludes_paths_and_prose() -> None:
    projected = project_conversion_report(_v2())
    serialized = json.dumps(projected, ensure_ascii=False)

    assert projected["association"] == "direct"
    assert projected["final_sha256"] == HASH_D
    assert projected["tool_use_count"] == 1
    assert projected["warning_count"] == 1
    assert "/private/task" not in serialized
    assert "PAPER_CANARY" not in serialized
    assert "warnings" not in projected
    assert "detail" not in projected


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"schema_version": 3}, "unsupported_report_schema"),
        ({"schema_version": True}, "unsupported_report_schema"),
        ({"run_id": "run_/private/task"}, "conversion_report_run_id_invalid"),
        ({"observation_coverage": {}}, "report_observation_coverage_invalid"),
        ({"sdk_transcript": {"status": "maybe"}}, "report_sdk_transcript_invalid"),
    ],
)
def test_invalid_or_unknown_v2_is_rejected(
    mutation: dict[str, object], code: str
) -> None:
    payload = {**_v2(), **mutation}

    with pytest.raises(ConversionReportError) as failure:
        load_conversion_report(payload)

    assert failure.value.code == code


def test_report_reader_accepts_v2_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "conversion-report.json"
    path.write_text(json.dumps(_v2()), encoding="utf-8")

    assert load_conversion_report(path)["schema_version"] == 2


def test_transcript_summary_failure_returns_fixed_unknown_shape() -> None:
    class BrokenSummary:
        def summary(self) -> object:
            raise RuntimeError("PRIVATE_TRANSCRIPT_FAILURE_CANARY")

    summary = transcript_summary_safely(BrokenSummary())

    assert summary.status == "unknown"
    assert summary.residual_count is None
    assert summary.failure_codes == ("sdk_transcript_summary_failed",)
    assert "PRIVATE_TRANSCRIPT_FAILURE_CANARY" not in str(summary)


def test_invalid_transcript_summary_dataclass_returns_fixed_unknown_shape() -> None:
    class InvalidSummary:
        def summary(self) -> SDKTranscriptSummary:
            return SDKTranscriptSummary(
                status="cleaned",
                residual_count=-1,
                oldest_age_bucket=None,
                failure_codes=(),
            )

    summary = transcript_summary_safely(InvalidSummary())

    assert summary.status == "unknown"
    assert summary.residual_count is None
    assert summary.failure_codes == ("sdk_transcript_summary_invalid",)
