"""Versioned, privacy-safe projection of conversion reports."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from docfit.observability.models import (
    ObservationCoverageSummary,
    SDKTranscriptSummary,
    observation_coverage_summary_is_valid,
    sdk_transcript_summary_is_valid,
)

_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_RUN_ID = re.compile(r"^run_[0-9a-f]{32}$")
_TASK_REF = re.compile(r"^task_[0-9a-f]{32}$")
_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_COVERAGE_STATES = {"complete", "degraded", "unavailable"}
_TRANSCRIPT_STATES = {"active", "cleaned", "residual", "cleanup_failed", "unknown"}
_AGE_BUCKETS = {"under_1h", "1h_to_24h", "1d_to_7d", "over_7d"}


class ConversionReportError(ValueError):
    """Reject a report using a fixed safe code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _safe_string(value: object, *, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ConversionReportError(code)
    return value


def _identifier(value: object, *, code: str) -> str:
    text = _safe_string(value, code=code)
    if _SAFE_IDENTIFIER.fullmatch(text) is None:
        raise ConversionReportError(code)
    return text


def _hash(value: object, *, code: str) -> str:
    text = _safe_string(value, code=code)
    if not _HASH.fullmatch(text):
        raise ConversionReportError(code)
    return text


def _safe_codes(value: object, *, code: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 32:
        raise ConversionReportError(code)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or _SAFE_CODE.fullmatch(item) is None:
            raise ConversionReportError(code)
        result.append(item)
    return tuple(result)


def _optional_count(value: object, *, code: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConversionReportError(code)
    return value


def _optional_timestamp(value: object, *, code: str) -> str | None:
    if value is None:
        return None
    text = _safe_string(value, code=code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConversionReportError(code) from error
    if parsed.tzinfo is None:
        raise ConversionReportError(code)
    return text


def _coverage(payload: object) -> ObservationCoverageSummary:
    if not isinstance(payload, Mapping):
        raise ConversionReportError("report_observation_coverage_invalid")
    state = payload.get("state")
    if state not in _COVERAGE_STATES:
        raise ConversionReportError("report_observation_coverage_invalid")
    missing = _safe_codes(
        payload.get("missing_sources"), code="report_observation_coverage_invalid"
    )
    failures = _safe_codes(
        payload.get("failure_codes"), code="report_observation_coverage_invalid"
    )
    observed_at = _optional_timestamp(
        payload.get("last_observed_at"),
        code="report_observation_coverage_invalid",
    )
    summary = ObservationCoverageSummary(
        state=state,
        events_persisted=_optional_count(
            payload.get("events_persisted"), code="report_observation_coverage_invalid"
        ),
        events_dropped=_optional_count(
            payload.get("events_dropped"), code="report_observation_coverage_invalid"
        ),
        missing_sources=missing,
        last_observed_at=observed_at,
        failure_codes=failures,
    )
    if not observation_coverage_summary_is_valid(summary):
        raise ConversionReportError("report_observation_coverage_invalid")
    return summary


def _transcript(payload: object) -> SDKTranscriptSummary:
    if not isinstance(payload, Mapping):
        raise ConversionReportError("report_sdk_transcript_invalid")
    status = payload.get("status")
    if status not in _TRANSCRIPT_STATES:
        raise ConversionReportError("report_sdk_transcript_invalid")
    age = payload.get("oldest_age_bucket")
    if age is not None and age not in _AGE_BUCKETS:
        raise ConversionReportError("report_sdk_transcript_invalid")
    summary = SDKTranscriptSummary(
        status=status,
        residual_count=_optional_count(
            payload.get("residual_count"), code="report_sdk_transcript_invalid"
        ),
        oldest_age_bucket=age,
        failure_codes=_safe_codes(
            payload.get("failure_codes"), code="report_sdk_transcript_invalid"
        ),
    )
    if not sdk_transcript_summary_is_valid(summary):
        raise ConversionReportError("report_sdk_transcript_invalid")
    return summary


def load_conversion_report(source: Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and validate report v1/v2 without accepting future schemas."""

    if isinstance(source, Path):
        try:
            loaded = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConversionReportError("conversion_report_unreadable") from error
        if not isinstance(loaded, dict):
            raise ConversionReportError("conversion_report_shape_invalid")
        payload = cast(dict[str, Any], loaded)
    else:
        payload = dict(source)
    version = payload.get("schema_version")
    if isinstance(version, bool) or version not in {1, 2}:
        raise ConversionReportError("unsupported_report_schema")
    required_common = (
        "status",
        "source_sha256",
        "template_sha256",
        "requirements_sha256",
        "knowledge_version",
        "knowledge_digest",
        "tool_uses",
    )
    if any(key not in payload for key in required_common):
        raise ConversionReportError("conversion_report_fields_missing")
    for key in ("source_sha256", "template_sha256", "requirements_sha256"):
        _hash(payload.get(key), code="conversion_report_hash_invalid")
    if not isinstance(payload.get("tool_uses"), (list, tuple)):
        raise ConversionReportError("conversion_report_tool_uses_invalid")
    if version == 2:
        run_id = _safe_string(
            payload.get("run_id"), code="conversion_report_run_id_invalid"
        )
        task_ref = _safe_string(
            payload.get("task_ref"), code="conversion_report_task_ref_invalid"
        )
        if _RUN_ID.fullmatch(run_id) is None:
            raise ConversionReportError("conversion_report_run_id_invalid")
        if _TASK_REF.fullmatch(task_ref) is None:
            raise ConversionReportError("conversion_report_task_ref_invalid")
        final_hash = payload.get("final_sha256")
        if final_hash is not None:
            _hash(final_hash, code="conversion_report_final_hash_invalid")
        if payload.get("status") == "COMPLETED" and final_hash is None:
            raise ConversionReportError("conversion_report_final_hash_invalid")
        _coverage(payload.get("observation_coverage"))
        _transcript(payload.get("sdk_transcript"))
    return payload


def project_conversion_report(source: Path | Mapping[str, Any]) -> dict[str, Any]:
    """Return the allowlisted observer projection; paths and prose stay behind."""

    payload = load_conversion_report(source)
    version = payload["schema_version"]
    if version == 1:
        coverage = ObservationCoverageSummary(
            "unavailable", None, None, (), None, ("report_v1_observation_unavailable",)
        )
        transcript = SDKTranscriptSummary("unknown", None, None, ())
        run_id = None
        task_ref = None
        final_sha256 = None
        association = "partial"
    else:
        coverage = _coverage(payload["observation_coverage"])
        transcript = _transcript(payload["sdk_transcript"])
        run_id = payload["run_id"]
        task_ref = payload["task_ref"]
        final_sha256 = payload.get("final_sha256")
        association = "direct"
    tool_uses = payload.get("tool_uses", ())
    final_evidence_category = None
    if payload.get("status") == "COMPLETED" and all(
        isinstance(payload.get(key), str) and bool(payload.get(key))
        for key in (
            "candidate_render_ref",
            "candidate_pdf",
            "visual_review",
            "validation",
        )
    ):
        final_evidence_category = "adobe_candidate_full_page_validation_v1"
    return {
        "schema_version": version,
        "run_id": run_id,
        "task_ref": task_ref,
        "association": association,
        "status": _identifier(
            payload.get("status"), code="conversion_report_status_invalid"
        ),
        "source_sha256": payload["source_sha256"],
        "template_sha256": payload["template_sha256"],
        "requirements_sha256": payload["requirements_sha256"],
        "final_sha256": final_sha256,
        "final_evidence_category": final_evidence_category,
        "knowledge_version": _identifier(
            payload.get("knowledge_version"), code="conversion_report_knowledge_invalid"
        ),
        "knowledge_digest": _identifier(
            payload.get("knowledge_digest"), code="conversion_report_knowledge_invalid"
        ),
        "backend": (
            None
            if payload.get("backend") is None
            else _identifier(
                payload.get("backend"), code="conversion_report_backend_invalid"
            )
        ),
        "session_id": (
            None
            if payload.get("session_id") is None
            else _identifier(
                payload.get("session_id"), code="conversion_report_session_invalid"
            )
        ),
        "tool_use_count": len(tool_uses),
        "warning_count": (
            len(payload.get("warnings", ()))
            if isinstance(payload.get("warnings"), (list, tuple))
            else 0
        ),
        "observation_coverage": {
            "state": coverage.state,
            "events_persisted": coverage.events_persisted,
            "events_dropped": coverage.events_dropped,
            "missing_sources": coverage.missing_sources,
            "last_observed_at": coverage.last_observed_at,
            "failure_codes": coverage.failure_codes,
        },
        "sdk_transcript": {
            "status": transcript.status,
            "residual_count": transcript.residual_count,
            "oldest_age_bucket": transcript.oldest_age_bucket,
            "failure_codes": transcript.failure_codes,
        },
    }
