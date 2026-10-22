from __future__ import annotations

import pytest

from docfit.template.judgment_shape import (
    EXCHANGE_SCHEMA_VERSIONS,
    HOST_COMPLETION_RECEIPT_V1,
    HOST_RECEIPT_SCHEMA_VERSIONS,
    MECHANICAL_FEEDBACK_V1,
    SEMANTIC_JUDGMENT_V1,
    mechanical_feedback,
    validate_hash_binding,
    validate_host_completion_receipt_v1,
    validate_semantic_judgment_v1,
)

SOURCE_HASH = "a" * 64
CANDIDATE_HASH = "b" * 64


def _assert_mechanical_failure(result: dict[str, object], *, code: str) -> None:
    assert result["schema_version"] == MECHANICAL_FEEDBACK_V1
    assert result["status"] in {"needs_input", "error"}
    feedback = result["feedback"]
    assert isinstance(feedback, dict)
    assert feedback["mechanical"] is True
    assert feedback["semantic_authority"] is False
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["code"] == code


@pytest.mark.parametrize(
    ("validator", "schema_version", "payload"),
    (
        (
            validate_semantic_judgment_v1,
            SEMANTIC_JUDGMENT_V1,
            {
                "schema_version": SEMANTIC_JUDGMENT_V1,
                "source_hash": SOURCE_HASH,
                "judgment_id": "j-cover",
            },
        ),
    ),
)
def test_p0_exchange_payloads_have_independent_ok_contracts(
    validator: object,
    schema_version: str,
    payload: dict[str, object],
) -> None:
    assert schema_version in EXCHANGE_SCHEMA_VERSIONS

    result = validator(payload)  # type: ignore[operator]

    assert result["status"] == "ok"
    assert result["failure"] is None


def test_p0_host_completion_receipt_is_not_agent_exchange_contract() -> None:
    assert "completion_payload_v1" not in EXCHANGE_SCHEMA_VERSIONS
    assert "scoped_closure_v1" not in EXCHANGE_SCHEMA_VERSIONS
    assert "closure_review_context_v1" not in EXCHANGE_SCHEMA_VERSIONS
    assert HOST_RECEIPT_SCHEMA_VERSIONS == (HOST_COMPLETION_RECEIPT_V1,)

    result = validate_host_completion_receipt_v1(
        {
            "schema_version": HOST_COMPLETION_RECEIPT_V1,
            "source_hash": SOURCE_HASH,
            "candidate_hash": CANDIDATE_HASH,
            "status": "complete",
            "final_docx": "work/final.docx",
            "render_ref": "render:v1:final",
            "reviewed_pages": [1],
            "validation": {"status": "ok"},
        }
    )

    assert result["status"] == "ok"
    assert result["checks"] == [{"name": "host_completion_receipt", "result": "ok"}]

    retired = validate_host_completion_receipt_v1(
        {
            "schema_version": "completion_payload_v1",
            "source_hash": SOURCE_HASH,
            "candidate_hash": CANDIDATE_HASH,
        }
    )
    _assert_mechanical_failure(retired, code="host_receipt_envelope_invalid")


@pytest.mark.parametrize(
    ("validator", "payload"),
    (
        (validate_semantic_judgment_v1, {"source_hash": SOURCE_HASH}),
    ),
)
def test_p0_every_payload_requires_schema_version(
    validator: object,
    payload: dict[str, object],
) -> None:
    result = validator(payload)  # type: ignore[operator]

    _assert_mechanical_failure(result, code="exchange_envelope_invalid")
    assert any(
        isinstance(blocker, dict)
        and blocker["code"] == "schema_version_invalid"
        and blocker["field"] == "schema_version"
        for blocker in result["blockers"]  # type: ignore[index]
    )


@pytest.mark.parametrize(
    ("validator", "payload", "missing_field"),
    (
        (validate_semantic_judgment_v1, {"schema_version": SEMANTIC_JUDGMENT_V1}, "source_hash"),
    ),
)
def test_p0_every_payload_requires_hash(
    validator: object,
    payload: dict[str, object],
    missing_field: str,
) -> None:
    result = validator(payload)  # type: ignore[operator]

    _assert_mechanical_failure(result, code="exchange_envelope_invalid")
    assert any(
        isinstance(blocker, dict) and blocker["field"] == missing_field
        for blocker in result["blockers"]  # type: ignore[index]
    )


def test_p0_stale_hash_binding_returns_repair_feedback() -> None:
    result = validate_hash_binding(
        {
            "schema_version": SEMANTIC_JUDGMENT_V1,
            "source_hash": "c" * 64,
        },
        expected_source_hash=SOURCE_HASH,
    )

    _assert_mechanical_failure(result, code="stale_ref")
    assert result["status"] == "needs_input"
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["retryable"] is True
    assert any(
        isinstance(blocker, dict) and blocker["code"] == "stale_source_ref"
        for blocker in result["blockers"]  # type: ignore[index]
    )


def test_p0_hard_failure_feedback_is_not_retryable_repair_feedback() -> None:
    result = mechanical_feedback(
        feedback_type="publication",
        code="published_hash_mismatch",
        message="Published Word and Fill Contract hashes disagree.",
        hard_failure=True,
    )

    _assert_mechanical_failure(result, code="published_hash_mismatch")
    assert result["status"] == "error"
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["origin"] == "invariant"
    assert failure["retryable"] is False


def test_p0_host_completion_receipt_must_be_mechanically_closed() -> None:
    result = validate_host_completion_receipt_v1(
        {
            "schema_version": HOST_COMPLETION_RECEIPT_V1,
            "source_hash": SOURCE_HASH,
            "candidate_hash": CANDIDATE_HASH,
            "status": "complete",
            "validation": {"status": "error"},
        }
    )

    _assert_mechanical_failure(result, code="host_completion_receipt_incomplete")
    blocker_codes = {
        str(blocker["code"])
        for blocker in result["blockers"]  # type: ignore[index]
        if isinstance(blocker, dict)
    }
    assert {
        "final_docx_missing",
        "render_ref_missing",
        "reviewed_pages_missing",
        "validation_not_ok",
    } <= blocker_codes
