"""Platform-neutral contracts for explicit local evidence directory grants."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from docfit.observability.events import ObservationEvent
from docfit.observability.report import (
    ConversionReportError,
    load_conversion_report,
)
from docfit.observability.storage import StoredObservationRun

DirectorySelectionStatus = Literal["selected", "cancelled", "unavailable", "invalid"]


@dataclass(frozen=True, slots=True)
class DirectorySelection:
    """An in-memory directory grant returned by an optional local shell adapter."""

    status: DirectorySelectionStatus
    path: Path | None = None
    failure_code: str | None = None


class DirectorySelector(Protocol):
    """Optional local-shell capability; core conversion never imports an implementation."""

    def select(self) -> DirectorySelection: ...


class ArtifactOpener(Protocol):
    """Optional local-shell action; the browser never receives a local path."""

    def open(self, path: Path) -> bool: ...


EvidenceMountStatus = Literal["verified", "partial", "conflict", "unavailable"]


@dataclass(frozen=True, slots=True)
class MountedEvidenceCapability:
    """Session-memory-only authority for one verified task directory."""

    run_id: str
    task_ref: str | None
    root: Path
    root_device: int
    root_inode: int
    report_sha256: str
    report_schema: int
    association: Literal["verified", "partial"]
    verified_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class EvidenceMountResult:
    status: EvidenceMountStatus
    failure_code: str | None = None
    capability: MountedEvidenceCapability | None = None


class EvidenceAccessError(ValueError):
    """Reject evidence access with a fixed code that never contains a path."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


ARTIFACT_LOCATORS = {
    "conversion_report": "conversion-report.json",
    "final_docx": "final.docx",
    "validation": "validation.json",
    "visual_review": "visual-review.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(root: Path, locator: str) -> Path:
    relative = PurePosixPath(locator)
    if (
        not locator
        or len(locator) > 512
        or "\\" in locator
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise EvidenceAccessError("evidence_locator_invalid")
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise EvidenceAccessError("evidence_locator_missing") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise EvidenceAccessError("evidence_symlink_rejected")
        if index < len(relative.parts) - 1:
            if not stat.S_ISDIR(metadata.st_mode):
                raise EvidenceAccessError("evidence_locator_invalid")
        elif not stat.S_ISREG(metadata.st_mode):
            raise EvidenceAccessError("evidence_locator_invalid")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise EvidenceAccessError("evidence_path_escape") from error
    return resolved


def _snapshot_files(root: Path) -> dict[str, Path]:
    input_root = root / "input"
    try:
        input_metadata = input_root.lstat()
    except OSError as error:
        raise EvidenceAccessError("evidence_input_unavailable") from error
    if stat.S_ISLNK(input_metadata.st_mode):
        raise EvidenceAccessError("evidence_symlink_rejected")
    if not stat.S_ISDIR(input_metadata.st_mode):
        raise EvidenceAccessError("evidence_input_unavailable")
    source = _regular_file(root, "input/student.docx")
    template = _regular_file(root, "input/school-template.docx")
    try:
        requirements = [
            path
            for path in input_root.iterdir()
            if path.name in {
                "school-requirements.pdf",
                "school-requirements.txt",
                "school-requirements.md",
            }
        ]
    except OSError as error:
        raise EvidenceAccessError("evidence_input_unavailable") from error
    if len(requirements) != 1:
        raise EvidenceAccessError("evidence_requirements_ambiguous")
    requirement = _regular_file(root, f"input/{requirements[0].name}")
    return {
        "source_sha256": source,
        "template_sha256": template,
        "requirements_sha256": requirement,
    }


def _observed_hashes(events: tuple[ObservationEvent, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for event in events:
        for attribute in event.attributes:
            if attribute.key in {
                "source_sha256",
                "template_sha256",
                "requirements_sha256",
                "final_sha256",
            } and isinstance(attribute.value, str):
                previous = result.get(attribute.key)
                if previous is not None and previous != attribute.value:
                    raise EvidenceAccessError("evidence_observed_hash_conflict")
                result[attribute.key] = attribute.value.removeprefix("sha256:")
    return result


def _verified_hashes(
    root: Path,
    snapshots: dict[str, Path],
    expected_hashes: dict[str, str],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (str(path.relative_to(root)), expected_hashes[key])
            for key, path in snapshots.items()
        )
    )


def verify_selected_task(
    run: StoredObservationRun,
    events: tuple[ObservationEvent, ...],
    selection: DirectorySelection,
) -> EvidenceMountResult:
    """Verify one selector grant without persisting or returning its path."""

    if selection.status != "selected" or selection.path is None:
        return EvidenceMountResult(
            "unavailable",
            selection.failure_code or f"picker_{selection.status}",
        )
    try:
        selected = selection.path.expanduser()
        if selected.is_symlink():
            raise EvidenceAccessError("evidence_mount_symlink_rejected")
        root = selected.resolve(strict=True)
        root_metadata = root.stat()
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise EvidenceAccessError("evidence_mount_not_directory")
        report_path = _regular_file(root, "conversion-report.json")
        report = load_conversion_report(report_path)
        report_hash = _sha256(report_path)
        observed = _observed_hashes(events)
        snapshots = _snapshot_files(root)
        expected_hashes = {
            key: str(report[key]).removeprefix("sha256:") for key in snapshots
        }
        final_hash = report.get("final_sha256")
        if final_hash is not None:
            expected_hashes["final_sha256"] = str(final_hash).removeprefix("sha256:")
            snapshots["final_sha256"] = _regular_file(root, "final.docx")
        if any(_sha256(snapshots[key]) != value for key, value in expected_hashes.items()):
            return EvidenceMountResult("conflict", "evidence_file_hash_mismatch")
        for key, value in observed.items():
            if key in expected_hashes and expected_hashes[key] != value:
                return EvidenceMountResult("conflict", "evidence_observed_hash_mismatch")
        if report["schema_version"] == 1:
            report_session = report.get("session_id")
            if run.session_id is None or report_session is None:
                return EvidenceMountResult(
                    "unavailable", "evidence_v1_identity_incomplete"
                )
            if report_session != run.session_id:
                return EvidenceMountResult("conflict", "evidence_session_mismatch")
            if any(observed.get(key) != value for key, value in expected_hashes.items()):
                return EvidenceMountResult(
                    "unavailable", "evidence_observation_incomplete"
                )
            capability = MountedEvidenceCapability(
                run.run_id,
                run.task_ref,
                root,
                root_metadata.st_dev,
                root_metadata.st_ino,
                report_hash,
                1,
                "partial",
                _verified_hashes(root, snapshots, expected_hashes),
            )
            return EvidenceMountResult("partial", "evidence_report_v1_partial", capability)
        if report.get("run_id") != run.run_id or report.get("task_ref") != run.task_ref:
            return EvidenceMountResult("conflict", "evidence_identity_mismatch")
        if (
            run.session_id is None
            or report.get("session_id") is None
            or report.get("session_id") != run.session_id
        ):
            return EvidenceMountResult("conflict", "evidence_session_mismatch")
        if any(observed.get(key) != value for key, value in expected_hashes.items()):
            return EvidenceMountResult("partial", "evidence_observation_incomplete")
        capability = MountedEvidenceCapability(
            run.run_id,
            run.task_ref,
            root,
            root_metadata.st_dev,
            root_metadata.st_ino,
            report_hash,
            2,
            "verified",
            _verified_hashes(root, snapshots, expected_hashes),
        )
        return EvidenceMountResult("verified", capability=capability)
    except (OSError, ConversionReportError, EvidenceAccessError) as error:
        code = (
            error.code
            if isinstance(error, (ConversionReportError, EvidenceAccessError))
            else "evidence_mount_unavailable"
        )
        return EvidenceMountResult("unavailable", code)


def resolve_task_locator(
    capability: MountedEvidenceCapability,
    locator: str,
) -> Path:
    """Revalidate a mounted root and relative locator immediately before use."""

    try:
        root_metadata = capability.root.stat()
    except OSError as error:
        raise EvidenceAccessError("evidence_mount_unavailable") from error
    if (
        root_metadata.st_dev != capability.root_device
        or root_metadata.st_ino != capability.root_inode
        or capability.root.is_symlink()
    ):
        raise EvidenceAccessError("evidence_mount_replaced")
    report_path = _regular_file(capability.root, "conversion-report.json")
    try:
        report_hash = _sha256(report_path)
    except OSError as error:
        raise EvidenceAccessError("evidence_report_unavailable") from error
    if report_hash != capability.report_sha256:
        raise EvidenceAccessError("evidence_report_changed")
    resolved = _regular_file(capability.root, locator)
    expected_hash = dict(capability.verified_hashes).get(locator)
    if expected_hash is not None:
        try:
            actual_hash = _sha256(resolved)
        except OSError as error:
            raise EvidenceAccessError("evidence_artifact_unavailable") from error
        if actual_hash != expected_hash:
            raise EvidenceAccessError("evidence_artifact_changed")
    return resolved
