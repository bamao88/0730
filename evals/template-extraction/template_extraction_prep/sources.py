"""Load hash-bound candidate package source manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


@dataclass(frozen=True, slots=True)
class VersionedFileRef:
    path: Path
    id: str
    version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CandidateSource:
    case_id: str
    school_id: str
    school_name: str
    template_path: Path
    template_sha256: str
    contract_path: Path
    contract_sha256: str
    field_registry: VersionedFileRef
    eval_config: VersionedFileRef
    scoring_version: str
    expected_verdict: str
    case_status: str
    gold_review_status: str
    reviewer: str | None
    reviewed_at: str | None
    blockers: tuple[str, ...]
    permissions: dict[str, str]
    description: str | None


@dataclass(frozen=True, slots=True)
class CandidateSourceManifest:
    path: Path
    sources: tuple[CandidateSource, ...]

    def by_case_id(self) -> dict[str, CandidateSource]:
        return {source.case_id: source for source in self.sources}


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return cast(dict[str, Any], value)


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _file_ref(base: Path, value: dict[str, Any]) -> VersionedFileRef:
    return VersionedFileRef(
        path=_resolve(base, str(value["path"])),
        id=str(value["id"]),
        version=str(value["version"]),
        sha256=str(value["sha256"]),
    )


def _source(base: Path, value: dict[str, Any]) -> CandidateSource:
    template = cast(dict[str, Any], value["template"])
    contract = cast(dict[str, Any], value["contract"])
    review = cast(dict[str, Any], value.get("gold_review", {}))
    permissions = {
        "visibility": "internal_candidate",
        "student_personal_data": "none_known",
        "git_storage": "approved",
        "ci_use": "unresolved",
        "external_processing": "not_required",
    }
    permission_overrides = cast(dict[str, Any], value.get("permissions", {}))
    permissions.update({str(key): str(item) for key, item in permission_overrides.items()})
    return CandidateSource(
        case_id=str(value["case_id"]),
        school_id=str(value["school_id"]),
        school_name=str(value["school_name"]),
        template_path=_resolve(base, str(template["path"])),
        template_sha256=str(template["sha256"]),
        contract_path=_resolve(base, str(contract["path"])),
        contract_sha256=str(contract["sha256"]),
        field_registry=_file_ref(base, cast(dict[str, Any], value["field_registry_ref"])),
        eval_config=_file_ref(base, cast(dict[str, Any], value["eval_config"])),
        scoring_version=str(
            value.get("scoring_version", "docfit-template-extraction-scoring/v1")
        ),
        expected_verdict=str(value.get("expected_verdict", "INPUT_ERROR")),
        case_status=str(value.get("case_status", "candidate")),
        gold_review_status=str(review.get("status", value.get("case_status", "candidate"))),
        reviewer=None if review.get("reviewer") is None else str(review["reviewer"]),
        reviewed_at=None if review.get("reviewed_at") is None else str(review["reviewed_at"]),
        blockers=tuple(str(item) for item in review.get("blockers", [])),
        permissions=permissions,
        description=None if value.get("description") is None else str(value["description"]),
    )


def load_source_manifest(path: Path) -> CandidateSourceManifest:
    resolved = path.expanduser().resolve()
    value = _read_yaml(resolved)
    if value.get("schema_version") != "docfit-template-extraction-candidate-sources/v1":
        raise ValueError("unsupported candidate source manifest schema_version")
    sources = tuple(
        _source(resolved.parent, cast(dict[str, Any], item))
        for item in cast(list[Any], value.get("sources", []))
    )
    case_ids = [source.case_id for source in sources]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("candidate source manifest contains duplicate case_id")
    return CandidateSourceManifest(path=resolved, sources=sources)
