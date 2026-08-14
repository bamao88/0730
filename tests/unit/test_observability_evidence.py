from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from docfit.observability.events import ProjectionContext
from docfit.observability.evidence import (
    DirectorySelection,
    EvidenceAccessError,
    resolve_task_locator,
    verify_selected_task,
)
from docfit.observability.privacy import project_app_event
from docfit.observability.storage import StoredObservationRun

RUN_ID = "run_0123456789abcdef0123456789abcdef"
TASK_REF = "task_fedcba9876543210fedcba9876543210"
SESSION_ID = "synthetic-session"


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _task(root: Path, *, schema: int = 2) -> dict[str, object]:
    values = {
        "source_sha256": b"source",
        "template_sha256": b"template",
        "requirements_sha256": b"requirements",
        "final_sha256": b"final",
    }
    input_root = root / "input"
    input_root.mkdir(parents=True)
    (input_root / "student.docx").write_bytes(values["source_sha256"])
    (input_root / "school-template.docx").write_bytes(values["template_sha256"])
    (input_root / "school-requirements.txt").write_bytes(
        values["requirements_sha256"]
    )
    (root / "final.docx").write_bytes(values["final_sha256"])
    report: dict[str, object] = {
        "schema_version": schema,
        "status": "COMPLETED",
        "source_sha256": _hash(values["source_sha256"]),
        "template_sha256": _hash(values["template_sha256"]),
        "requirements_sha256": _hash(values["requirements_sha256"]),
        "knowledge_version": "v1",
        "knowledge_digest": f"sha256:{'a' * 64}",
        "backend": "synthetic-backend",
        "session_id": SESSION_ID,
        "tool_uses": [],
        "warnings": [],
        "detail": "PRIVATE_REPORT_PROSE",
    }
    if schema == 2:
        report.update(
            {
                "run_id": RUN_ID,
                "task_ref": TASK_REF,
                "final_sha256": _hash(values["final_sha256"]),
                "observation_coverage": {
                    "state": "complete",
                    "events_persisted": 2,
                    "events_dropped": 0,
                    "missing_sources": [],
                    "last_observed_at": None,
                    "failure_codes": [],
                },
                "sdk_transcript": {
                    "status": "cleaned",
                    "residual_count": 0,
                    "oldest_age_bucket": None,
                    "failure_codes": [],
                },
            }
        )
    (root / "conversion-report.json").write_text(json.dumps(report), encoding="utf-8")
    return report


def _events(report: dict[str, object]):
    hashes = {
        key: str(report[key])
        for key in ("source_sha256", "template_sha256", "requirements_sha256")
    }
    started = project_app_event(
        ProjectionContext(RUN_ID, 1, datetime.now(UTC).isoformat(), 1.0),
        source_event_id="run-start",
        kind="run_started",
        status="started",
        task_ref=TASK_REF,
        hashes=hashes,
    )
    finished = project_app_event(
        ProjectionContext(RUN_ID, 2, datetime.now(UTC).isoformat(), 2.0),
        source_event_id="run-finish",
        kind="run_finished",
        status="completed",
        hashes={"final_sha256": str(report.get("final_sha256", ""))},
    )
    assert started.event is not None
    if report["schema_version"] == 2:
        assert finished.event is not None
        return (started.event, finished.event)
    return (started.event,)


def _run() -> StoredObservationRun:
    return StoredObservationRun(
        RUN_ID,
        TASK_REF,
        SESSION_ID,
        "completed",
        None,
        None,
        None,
        2,
        1024,
    )


def test_v2_mount_verifies_ids_session_and_all_snapshot_hashes(tmp_path: Path) -> None:
    report = _task(tmp_path)

    result = verify_selected_task(
        _run(),
        _events(report),
        DirectorySelection("selected", tmp_path),
    )

    assert result.status == "verified"
    assert result.failure_code is None
    assert result.capability is not None
    assert result.capability.association == "verified"


def test_v1_mount_is_never_more_than_partial(tmp_path: Path) -> None:
    report = _task(tmp_path, schema=1)

    result = verify_selected_task(
        _run(),
        _events(report),
        DirectorySelection("selected", tmp_path),
    )

    assert result.status == "partial"
    assert result.failure_code == "evidence_report_v1_partial"
    assert result.capability is not None
    assert result.capability.association == "partial"


def test_v1_mount_requires_matching_session_and_observed_input_hashes(
    tmp_path: Path,
) -> None:
    report = _task(tmp_path, schema=1)
    mismatched_run = _run()
    mismatched_run = StoredObservationRun(
        mismatched_run.run_id,
        mismatched_run.task_ref,
        "different-session",
        mismatched_run.status,
        mismatched_run.started_at,
        mismatched_run.completed_at,
        mismatched_run.last_observed_at,
        mismatched_run.event_count,
        mismatched_run.event_bytes,
    )

    mismatch = verify_selected_task(
        mismatched_run,
        _events(report),
        DirectorySelection("selected", tmp_path),
    )
    incomplete = verify_selected_task(
        _run(),
        (),
        DirectorySelection("selected", tmp_path),
    )

    assert mismatch.status == "conflict"
    assert mismatch.failure_code == "evidence_session_mismatch"
    assert mismatch.capability is None
    assert incomplete.status == "unavailable"
    assert incomplete.failure_code == "evidence_observation_incomplete"
    assert incomplete.capability is None


def test_wrong_identity_or_changed_file_is_conflict(tmp_path: Path) -> None:
    report = _task(tmp_path)
    report["task_ref"] = "task_00000000000000000000000000000000"
    (tmp_path / "conversion-report.json").write_text(json.dumps(report), encoding="utf-8")

    identity = verify_selected_task(
        _run(), _events(report), DirectorySelection("selected", tmp_path)
    )
    report["task_ref"] = TASK_REF
    (tmp_path / "conversion-report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "final.docx").write_bytes(b"changed")
    changed = verify_selected_task(
        _run(), _events(report), DirectorySelection("selected", tmp_path)
    )

    assert identity.status == "conflict"
    assert identity.failure_code == "evidence_identity_mismatch"
    assert changed.status == "conflict"
    assert changed.failure_code == "evidence_file_hash_mismatch"


def test_locator_rejects_absolute_traversal_symlink_and_directory(tmp_path: Path) -> None:
    report = _task(tmp_path)
    result = verify_selected_task(
        _run(), _events(report), DirectorySelection("selected", tmp_path)
    )
    assert result.capability is not None
    (tmp_path / "linked.docx").symlink_to(tmp_path / "final.docx")

    for locator, code in (
        ("/etc/passwd", "evidence_locator_invalid"),
        ("../outside", "evidence_locator_invalid"),
        ("linked.docx", "evidence_symlink_rejected"),
        ("input", "evidence_locator_invalid"),
    ):
        with pytest.raises(EvidenceAccessError) as failure:
            resolve_task_locator(result.capability, locator)
        assert failure.value.code == code
        assert str(tmp_path) not in str(failure.value)


def test_report_replacement_invalidates_session_capability(tmp_path: Path) -> None:
    report = _task(tmp_path)
    result = verify_selected_task(
        _run(), _events(report), DirectorySelection("selected", tmp_path)
    )
    assert result.capability is not None
    (tmp_path / "conversion-report.json").write_text("{}", encoding="utf-8")

    with pytest.raises(EvidenceAccessError) as failure:
        resolve_task_locator(result.capability, "final.docx")

    assert failure.value.code == "evidence_report_changed"


def test_artifact_replacement_invalidates_session_capability(tmp_path: Path) -> None:
    report = _task(tmp_path)
    result = verify_selected_task(
        _run(), _events(report), DirectorySelection("selected", tmp_path)
    )
    assert result.capability is not None
    (tmp_path / "final.docx").write_bytes(b"replacement")

    with pytest.raises(EvidenceAccessError) as failure:
        resolve_task_locator(result.capability, "final.docx")

    assert failure.value.code == "evidence_artifact_changed"


def test_unavailable_selector_never_exposes_path(tmp_path: Path) -> None:
    report = _task(tmp_path)
    result = verify_selected_task(
        _run(),
        _events(report),
        DirectorySelection("unavailable", tmp_path, "picker_unavailable"),
    )

    assert result.status == "unavailable"
    assert result.capability is None
    assert str(tmp_path) not in str(result)
