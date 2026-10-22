"""Final-generation selectable E2E eval runner."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from docfit.app.student_content_fill import FinalGenerationRequest, run_final_generation
from docfit.evals.final_generation_quality import run_final_generation_quality_compare
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_file,
    sha256_json,
)
from docfit.visual.evidence import EvidenceStore

FINAL_GENERATION_EVAL_REPORT_SCHEMA_VERSION = "docfit-final-generation-eval-report/v1"
FINAL_GENERATION_MATRIX_REPORT_SCHEMA_VERSION = (
    "docfit-final-generation-combination-eval-report/v1"
)
FINAL_GENERATION_EVAL_CASE_SCHEMA_VERSION = "docfit-final-generation-eval-case/v1"
DEFAULT_FINAL_GENERATION_CHECKS = ("input", "style", "generate")
RELEASE_FINAL_GENERATION_CHECKS = ("input", "style", "generate", "quality")
ALLOWED_FINAL_GENERATION_CHECKS = frozenset((*DEFAULT_FINAL_GENERATION_CHECKS, "quality"))
DEFAULT_FINAL_GENERATION_BASE_ROOT = Path("temp/final-generation-base-packages-20260816")
DEFAULT_FINAL_GENERATION_STUDENT_IDS = ("student-001", "student-002", "student-003")
DEFAULT_FINAL_GENERATION_SCHOOL_IDS = (
    "hunau-undergraduate",
    "njau-undergraduate",
    "pku-graduate",
)
FINAL_GENERATION_SCHOOL_ALIASES = {
    "hunau": "hunau-undergraduate",
    "hunan": "hunau-undergraduate",
    "njau": "njau-undergraduate",
    "nanjing": "njau-undergraduate",
    "pku": "pku-graduate",
    "peking": "pku-graduate",
}
FINAL_GENERATION_QUALITY_GOLD_FOLDERS = {
    "hunau-undergraduate": "01-hunau-undergraduate",
    "njau-undergraduate": "02-njau-undergraduate",
    "pku-graduate": "03-pku-graduate",
}
DEFAULT_FINAL_GENERATION_QUALITY_THRESHOLDS: JsonObject = {
    "max_media_delta": 0,
    "max_page_count_delta_abs": 0,
    "max_placeholder_residue_count": 0,
    "max_visual_changed_pixel_ratio_mean": 0.02,
    "max_visual_changed_pixel_ratio_page": 0.08,
    "min_full_text_similarity": 0.99,
    "min_paragraph_sequence_similarity": 0.95,
}
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class FinalGenerationEvalInputError(Exception):
    """The requested final-generation eval cannot be selected or prepared."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _CheckFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        assertions: int = 0,
        metrics: JsonObject | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.assertions = assertions
        self.metrics = metrics or {}


def list_final_generation_cases(repository: Path) -> list[JsonObject]:
    """List selectable final-generation eval cases."""

    case_root = repository.resolve() / "evals/final-generation/cases"
    cases: list[JsonObject] = []
    for path in sorted(case_root.glob("*/case.json")):
        try:
            case = _read_json_object(path)
        except (OSError, json.JSONDecodeError, FinalGenerationEvalInputError):
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str):
            continue
        default_checks = _default_checks_for_case(case)
        release_case = _case_has_quality_gold(case)
        cases.append(
            {
                "case_id": case_id,
                "description": case.get("description"),
                "input_package": case.get("input_package"),
                "default_checks": list(default_checks),
                "release_case": release_case,
                "release_checks": list(RELEASE_FINAL_GENERATION_CHECKS)
                if release_case
                else None,
            }
        )
    return cases


def list_final_generation_combinations(
    repository: Path,
    *,
    base_root: Path | None = None,
) -> list[JsonObject]:
    """List selectable student x school base-package combinations."""

    repository = repository.resolve()
    base = _base_package_root(repository, base_root)
    students = _available_student_ids(base)
    schools = _available_school_ids(base)
    combinations: list[JsonObject] = []
    for student_id in students:
        for school_id in schools:
            case = _combination_case(
                repository=repository,
                input_package=base,
                student_id=student_id,
                school_id=school_id,
            )
            quality = _mapping(_mapping(case.get("expected")).get("quality"))
            combinations.append(
                {
                    "case_id": case["case_id"],
                    "student_id": student_id,
                    "school_id": school_id,
                    "input_package": _repo_rel(repository, base),
                    "quality_gold": quality.get("gold_docx"),
                    "release_case": _case_has_quality_gold(case),
                    "default_checks": list(_default_checks_for_case(case)),
                }
            )
    return combinations


def run_final_generation_combinations(
    *,
    repository: Path,
    base_root: Path | None = None,
    students: Sequence[str] | str | None = None,
    schools: Sequence[str] | str | None = None,
    checks: Sequence[str] | str | None = None,
    output_directory: Path | None = None,
) -> JsonObject:
    """Run final-generation eval checks for selected base-package combinations."""

    repository = repository.resolve()
    base = _base_package_root(repository, base_root)
    selected_students = _select_student_ids(
        students,
        available=_available_student_ids(base),
    )
    selected_schools = _select_school_ids(
        schools,
        available=_available_school_ids(base),
    )
    if not output_directory:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_directory = repository / ".tmp/final-generation-evals" / f"combinations-{stamp}"
    output = _prepare_output_directory(repository, output_directory)
    started_wall = datetime.now(UTC)
    started = time.monotonic()

    run_reports: list[JsonObject] = []
    for student_id in selected_students:
        for school_id in selected_schools:
            case_id = _combination_case_id(student_id, school_id)
            input_package = output / "_inputs" / case_id
            _materialize_combination_input_package(
                repository=repository,
                base_root=base,
                student_id=student_id,
                school_id=school_id,
                output_directory=input_package,
            )
            case = _combination_case(
                repository=repository,
                input_package=input_package,
                student_id=student_id,
                school_id=school_id,
            )
            run_report = _run_final_generation_eval_case(
                repository=repository,
                case=case,
                case_id=case_id,
                checks=checks,
                output_directory=output / "runs" / case_id,
            )
            run_report["student_id"] = student_id
            run_report["school_id"] = school_id
            run_reports.append(run_report)

    failed = [item for item in run_reports if item.get("check_status") != "PASS"]
    release_passed = [item for item in run_reports if item.get("release_status") == "PASS"]
    release_failed = [
        item
        for item in run_reports
        if item.get("release_gate", {}).get("release_case") is True
        and item.get("release_status") != "PASS"
    ]
    matrix_report: JsonObject = {
        "schema_version": FINAL_GENERATION_MATRIX_REPORT_SCHEMA_VERSION,
        "suite": "final-generation",
        "selection": {
            "base_root": str(base),
            "students": list(selected_students),
            "schools": list(selected_schools),
            "combination_count": len(run_reports),
        },
        "status": "PASS" if not failed else "FAIL",
        "check_status": "PASS" if not failed else "FAIL",
        "release_summary": {
            "release_case_count": len(release_passed) + len(release_failed),
            "release_passed_count": len(release_passed),
            "release_failed_count": len(release_failed),
            "releasable_count": sum(1 for item in run_reports if item.get("releasable") is True),
        },
        "started_at": started_wall.isoformat(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "runs": run_reports,
        "output_directory": str(output),
        "report_path": str(output / "eval-combinations-report.json"),
    }
    atomic_write_json(output / "eval-combinations-report.json", matrix_report)
    return matrix_report


def parse_final_generation_checks(value: str | None) -> tuple[str, ...]:
    """Parse comma-separated final-generation eval check names."""

    if value is None or not value.strip():
        return DEFAULT_FINAL_GENERATION_CHECKS
    checks = tuple(item.strip() for item in value.split(",") if item.strip())
    if not checks:
        raise FinalGenerationEvalInputError(
            "final_generation_eval_checks_empty",
            "At least one final-generation eval check must be selected.",
        )
    unknown = sorted(set(checks) - ALLOWED_FINAL_GENERATION_CHECKS)
    if unknown:
        raise FinalGenerationEvalInputError(
            "final_generation_eval_check_unknown",
            "Unsupported final-generation eval checks: " + ", ".join(unknown),
        )
    return checks


def run_final_generation_eval(
    *,
    repository: Path,
    case_id: str,
    checks: Sequence[str] | str | None = None,
    output_directory: Path | None = None,
) -> JsonObject:
    """Run selected final-generation eval checks against one case."""

    repository = repository.resolve()
    case = _load_case(repository, case_id)
    return _run_final_generation_eval_case(
        repository=repository,
        case=case,
        case_id=case_id,
        checks=checks,
        output_directory=output_directory,
    )


def _run_final_generation_eval_case(
    *,
    repository: Path,
    case: JsonObject,
    case_id: str,
    checks: Sequence[str] | str | None = None,
    output_directory: Path | None = None,
) -> JsonObject:
    """Run selected final-generation eval checks against a loaded case object."""

    if checks is None:
        selected_checks = _default_checks_for_case(case)
    else:
        selected_checks = (
            parse_final_generation_checks(checks)
            if isinstance(checks, str)
            else _validate_checks_tuple(checks)
        )
    if not output_directory:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_directory = (
            repository / ".tmp/final-generation-evals" / f"{case_id}-{stamp}"
        )
    output = _prepare_output_directory(repository, output_directory)
    started_wall = datetime.now(UTC)
    started = time.monotonic()

    check_results: list[JsonObject] = []
    context: _InputContext | None = None
    if "input" in selected_checks:
        result, context = _run_check(
            "input",
            lambda: _check_input_package(repository=repository, case=case),
        )
        check_results.append(result)
    else:
        context = _load_input_context(repository=repository, case=case)

    if "style" in selected_checks:
        if _has_failed(check_results):
            check_results.append(_skipped("style", "input_check_failed"))
        else:
            loaded_context = context or _load_input_context(repository=repository, case=case)
            result, context = _run_check(
                "style",
                lambda: _check_style_inputs(loaded_context),
            )
            check_results.append(result)

    generation_report: JsonObject | None = None
    if "generate" in selected_checks:
        if _has_failed(check_results):
            check_results.append(_skipped("generate", "earlier_check_failed"))
        else:
            result, generated = _run_check(
                "generate",
                lambda: _check_generate(
                    context or _load_input_context(repository=repository, case=case),
                    output / "generate-final",
                ),
            )
            check_results.append(result)
            if isinstance(generated, dict):
                generation_report = generated

    if "quality" in selected_checks:
        if _has_failed(check_results):
            check_results.append(_skipped("quality", "earlier_check_failed"))
        elif generation_report is None:
            result, _ = _run_check(
                "quality",
                lambda: _quality_requires_generate(),
            )
            check_results.append(result)
        else:
            result, _ = _run_check(
                "quality",
                lambda: _check_quality(
                    repository=repository,
                    context=context or _load_input_context(repository=repository, case=case),
                    generation_report=generation_report,
                    output_directory=output / "quality",
                ),
            )
            check_results.append(result)

    check_status = _aggregate_check_status(check_results)
    release_gate = _release_gate(
        case=case,
        selected_checks=selected_checks,
        check_results=check_results,
        generation_report=generation_report,
    )
    report: JsonObject = {
        "schema_version": FINAL_GENERATION_EVAL_REPORT_SCHEMA_VERSION,
        "suite": "final-generation",
        "case_id": case_id,
        "status": check_status,
        "check_status": check_status,
        "generate_status": release_gate["generate_status"],
        "quality_status": release_gate["quality_status"],
        "release_status": release_gate["status"],
        "releasable": release_gate["releasable"],
        "started_at": started_wall.isoformat(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks_requested": list(selected_checks),
        "checks": check_results,
        "release_gate": release_gate,
        "input_package": str(
            context.input_package if context else _input_package_path(repository, case)
        ),
        "output_directory": str(output),
        "report_path": str(output / "eval-report.json"),
    }
    atomic_write_json(output / "eval-report.json", report)
    return report


def _default_checks_for_case(case: Mapping[str, Any]) -> tuple[str, ...]:
    if _case_has_quality_gold(case):
        return RELEASE_FINAL_GENERATION_CHECKS
    raw_default_checks = case.get("default_checks")
    default_checks = (
        raw_default_checks
        if isinstance(raw_default_checks, Sequence)
        and not isinstance(raw_default_checks, str | bytes)
        else DEFAULT_FINAL_GENERATION_CHECKS
    )
    return _validate_checks_tuple(tuple(str(item) for item in default_checks))


def _validate_checks_tuple(checks: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(str(item) for item in checks)
    unknown = sorted(set(selected) - ALLOWED_FINAL_GENERATION_CHECKS)
    if not selected:
        raise FinalGenerationEvalInputError(
            "final_generation_eval_checks_empty",
            "At least one final-generation eval check must be selected.",
        )
    if unknown:
        raise FinalGenerationEvalInputError(
            "final_generation_eval_check_unknown",
            "Unsupported final-generation eval checks: " + ", ".join(unknown),
        )
    return selected


def _base_package_root(repository: Path, base_root: Path | None) -> Path:
    raw = base_root or DEFAULT_FINAL_GENERATION_BASE_ROOT
    root = raw.resolve() if raw.is_absolute() else (repository / raw).resolve()
    if not root.is_relative_to(repository):
        raise FinalGenerationEvalInputError(
            "final_generation_base_root_outside_repo",
            "Final-generation base package root must stay inside the repository.",
        )
    if not root.is_dir():
        raise FinalGenerationEvalInputError(
            "final_generation_base_root_missing",
            f"Final-generation base package root does not exist: {raw}",
        )
    return root


def _available_student_ids(base_root: Path) -> tuple[str, ...]:
    students_root = base_root / "students"
    values = tuple(
        path.name
        for path in sorted(students_root.iterdir() if students_root.is_dir() else ())
        if path.is_dir()
    )
    return values or DEFAULT_FINAL_GENERATION_STUDENT_IDS


def _available_school_ids(base_root: Path) -> tuple[str, ...]:
    schools_root = base_root / "schools"
    values = tuple(
        path.name
        for path in sorted(schools_root.iterdir() if schools_root.is_dir() else ())
        if path.is_dir()
    )
    return values or DEFAULT_FINAL_GENERATION_SCHOOL_IDS


def _selector_tokens(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    raw_values = (values,) if isinstance(values, str) else values
    tokens: list[str] = []
    for value in raw_values:
        tokens.extend(item.strip() for item in str(value).split(",") if item.strip())
    return tuple(tokens)


def _select_student_ids(
    values: Sequence[str] | str | None,
    *,
    available: Sequence[str],
) -> tuple[str, ...]:
    tokens = _selector_tokens(values)
    if not tokens or any(token.casefold() in {"all", "*"} for token in tokens):
        return tuple(available)
    normalized = tuple(dict.fromkeys(_normalize_student_id(token) for token in tokens))
    unknown = [item for item in normalized if item not in available]
    if unknown:
        raise FinalGenerationEvalInputError(
            "final_generation_student_unknown",
            "Unknown final-generation student id(s): " + ", ".join(unknown),
        )
    return normalized


def _select_school_ids(
    values: Sequence[str] | str | None,
    *,
    available: Sequence[str],
) -> tuple[str, ...]:
    tokens = _selector_tokens(values)
    if not tokens or any(token.casefold() in {"all", "*"} for token in tokens):
        return tuple(available)
    normalized = tuple(dict.fromkeys(_normalize_school_id(token) for token in tokens))
    unknown = [item for item in normalized if item not in available]
    if unknown:
        raise FinalGenerationEvalInputError(
            "final_generation_school_unknown",
            "Unknown final-generation school id(s): " + ", ".join(unknown),
        )
    return normalized


def _normalize_student_id(value: str) -> str:
    token = value.strip().casefold()
    if re.fullmatch(r"\d{1,3}", token):
        return f"student-{int(token):03d}"
    match = re.fullmatch(r"student-(\d{1,3})", token)
    if match:
        return f"student-{int(match.group(1)):03d}"
    return token


def _normalize_school_id(value: str) -> str:
    token = value.strip().casefold()
    return FINAL_GENERATION_SCHOOL_ALIASES.get(token, token)


def _materialize_combination_input_package(
    *,
    repository: Path,
    base_root: Path,
    student_id: str,
    school_id: str,
    output_directory: Path,
) -> None:
    if output_directory.exists() and (
        not output_directory.is_dir() or any(output_directory.iterdir())
    ):
        raise FinalGenerationEvalInputError(
            "final_generation_combination_input_not_empty",
            "Generated final-generation combination input package must be absent or empty.",
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    student_root = base_root / "students" / student_id
    school_root = base_root / "schools" / school_id
    sources = {
        "student.docx": student_root / "student.docx",
        "student-content.json": student_root / "student-content.json",
        "final-template.docx": school_root / "final-template.docx",
        "fill-contract.yaml": school_root / "fill-contract.yaml",
        "content-fields.yaml": school_root / "content-fields.yaml",
    }
    for name, source in sources.items():
        if not source.is_file():
            raise FinalGenerationEvalInputError(
                "final_generation_base_package_file_missing",
                f"Base package file missing for {student_id} x {school_id}: {name}",
            )
        shutil.copy2(source, output_directory / name)

    contract = _read_yaml_object(output_directory / "fill-contract.yaml")
    style_candidates, style_gaps, style_manifest = _style_inputs_from_contract(contract)
    atomic_write_json(output_directory / "style" / "school_style_candidates.json", style_candidates)
    atomic_write_json(output_directory / "style" / "school_known_gaps.json", style_gaps)
    atomic_write_json(output_directory / "style" / "manifest.json", style_manifest)
    (output_directory / "README.md").write_text(
        (
            "# final-generation combination input\n\n"
            f"- student: `{student_id}`\n"
            f"- school: `{school_id}`\n"
            f"- base_root: `{_repo_rel(repository, base_root)}`\n"
        ),
        encoding="utf-8",
    )
    student_content = _read_json_object(output_directory / "student-content.json")
    registry = _read_yaml_object(output_directory / "content-fields.yaml")
    registry_identity = {
        "registry_id": registry.get("registry_id"),
        "registry_version": registry.get("registry_version"),
        "sha256": sha256_file(output_directory / "content-fields.yaml"),
    }
    files = {
        name: _file_meta(output_directory / name)
        for name in (
            "README.md",
            "student.docx",
            "student-content.json",
            "final-template.docx",
            "fill-contract.yaml",
            "content-fields.yaml",
            "style/school_style_candidates.json",
            "style/school_known_gaps.json",
            "style/manifest.json",
        )
    }
    contract_registry_ref = _mapping(contract.get("field_registry_ref"))
    student_registry_ref = _mapping(student_content.get("registry"))
    manifest: JsonObject = {
        "schema_version": "docfit-final-generation-input-package/v1",
        "package_id": _combination_case_id(student_id, school_id),
        "created_for": "final-generation selectable base-package combination",
        "stage": "generated_from_base_packages",
        "base_root": _repo_rel(repository, base_root),
        "student": {
            "student_id": student_id,
            "source_sha256": student_content.get("source_sha256"),
        },
        "school": {
            "school_id": school_id,
            "template_sha256": contract.get("template_sha256"),
        },
        "student_content": {
            "schema_version": student_content.get("schema_version"),
            "status": student_content.get("status"),
            "item_count": len(student_content.get("items") or []),
            "field_result_count": len(student_content.get("field_results") or []),
        },
        "template_contract": {
            "schema_version": contract.get("schema_version"),
            "status": contract.get("status"),
            "slot_count": len(contract.get("slots") or []),
            "style_count": len(contract.get("styles") or []),
            "region_count": len(contract.get("regions") or []),
            "style_contract_set_digest": contract.get("style_contract_set_digest"),
        },
        "style_inputs": style_manifest,
        "bindings": {
            "student_content_binds_student_docx": (
                student_content.get("source_sha256")
                == sha256_file(output_directory / "student.docx")
            ),
            "fill_contract_binds_final_template_docx": (
                contract.get("template_sha256")
                == sha256_file(output_directory / "final-template.docx")
            ),
            "fill_contract_binds_registry": all(
                contract_registry_ref.get(key) == registry_identity.get(key)
                for key in ("registry_id", "registry_version", "sha256")
            ),
            "student_content_binds_registry": all(
                student_registry_ref.get(key) == registry_identity.get(key)
                for key in ("registry_id", "registry_version", "sha256")
            ),
        },
        "files": files,
    }
    atomic_write_json(output_directory / "manifest.json", manifest)


def _style_inputs_from_contract(
    contract: Mapping[str, Any],
) -> tuple[list[Any], list[Any], JsonObject]:
    provenance = _mapping(contract.get("provenance"))
    raw_candidates = provenance.get("school_style_candidates")
    raw_gaps = provenance.get("known_school_style_gaps")
    candidates = list(raw_candidates) if isinstance(raw_candidates, list) else []
    gaps = list(raw_gaps) if isinstance(raw_gaps, list) else []
    profile_registry_digest = provenance.get("profile_registry_digest")
    if not isinstance(profile_registry_digest, str) or not profile_registry_digest:
        profile_registry_digest = sha256_json(
            {
                "source": "missing_profile_registry_digest",
                "template_sha256": contract.get("template_sha256"),
            }
        )
    school_observation_set_digest = provenance.get("school_observation_set_digest")
    if not isinstance(school_observation_set_digest, str) or not school_observation_set_digest:
        school_observation_set_digest = sha256_json(
            {
                "source": "materialized_combination_style_inputs",
                "template_sha256": contract.get("template_sha256"),
                "school_style_candidates": candidates,
                "known_school_style_gaps": gaps,
            }
        )
    selection_case = "school_candidate_available"
    if not candidates and gaps:
        selection_case = "no_school_candidate_with_explicit_known_gaps"
    elif not candidates:
        selection_case = "no_school_candidate_or_known_gaps_published"
    manifest: JsonObject = {
        "schema_version": "docfit-final-generation-style-inputs/v1",
        "profile_registry_digest": profile_registry_digest,
        "school_observation_set_digest": school_observation_set_digest,
        "school_style_candidate_count": len(candidates),
        "school_known_gap_count": len(gaps),
        "school_style_candidates_digest": sha256_json(candidates),
        "school_known_gaps_digest": sha256_json(gaps),
        "selection_case": selection_case,
        "source": {
            "fill_contract_path": "fill-contract.yaml",
            "school_style_candidates_json_pointer": "/provenance/school_style_candidates",
            "school_known_gaps_json_pointer": "/provenance/known_school_style_gaps",
        },
    }
    return candidates, gaps, manifest


def _combination_case(
    *,
    repository: Path,
    input_package: Path,
    student_id: str,
    school_id: str,
) -> JsonObject:
    expected: JsonObject = {}
    gold_docx = _quality_gold_docx(repository, student_id=student_id, school_id=school_id)
    if gold_docx is not None:
        expected["quality"] = {
            "gold_docx": gold_docx,
            "thresholds": dict(DEFAULT_FINAL_GENERATION_QUALITY_THRESHOLDS),
        }
    return {
        "schema_version": FINAL_GENERATION_EVAL_CASE_SCHEMA_VERSION,
        "case_id": _combination_case_id(student_id, school_id),
        "description": f"{student_id} content applied to {school_id} from base packages.",
        "input_package": _repo_rel(repository, input_package),
        "default_checks": list(DEFAULT_FINAL_GENERATION_CHECKS),
        "expected": expected,
    }


def _combination_case_id(student_id: str, school_id: str) -> str:
    return f"{student_id}__{school_id}"


def _quality_gold_docx(
    repository: Path,
    *,
    student_id: str,
    school_id: str,
) -> str | None:
    folder = FINAL_GENERATION_QUALITY_GOLD_FOLDERS.get(school_id)
    if folder is None:
        return None
    candidate = (
        repository
        / "temp/manual-gold-preparation/gold/30-cross-conversions"
        / folder
        / f"{school_id}__{student_id}__converted.docx"
    )
    if not candidate.is_file():
        return None
    return _repo_rel(repository, candidate)


def _repo_rel(repository: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(repository):
        raise FinalGenerationEvalInputError(
            "final_generation_path_outside_repo",
            "Final-generation eval paths must stay inside the repository.",
        )
    return str(resolved.relative_to(repository))


def _file_meta(path: Path) -> JsonObject:
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def _aggregate_check_status(check_results: Sequence[Mapping[str, Any]]) -> str:
    status = (
        "PASS"
        if check_results
        and all(item["status"] in {"PASS", "SKIPPED"} for item in check_results)
        and not any(item["status"] == "FAIL" for item in check_results)
        else "FAIL"
    )
    if not any(item["status"] == "PASS" for item in check_results):
        return "FAIL"
    return status


def _case_has_quality_gold(case: Mapping[str, Any]) -> bool:
    expected = _mapping(case.get("expected"))
    quality = _mapping(expected.get("quality"))
    gold_docx = quality.get("gold_docx")
    return isinstance(gold_docx, str) and bool(gold_docx.strip())


def _check_result_status(
    check_results: Sequence[Mapping[str, Any]],
    name: str,
) -> str:
    for item in check_results:
        if item.get("name") == name:
            status = item.get("status")
            return status if isinstance(status, str) else "FAIL"
    return "NOT_RUN"


def _check_metric(
    check_results: Sequence[Mapping[str, Any]],
    check_name: str,
    metric_name: str,
) -> Any:
    for item in check_results:
        if item.get("name") != check_name:
            continue
        metrics = item.get("metrics")
        if isinstance(metrics, Mapping):
            return metrics.get(metric_name)
    return None


def _semantic_generate_status(check_results: Sequence[Mapping[str, Any]]) -> str:
    value = _check_metric(check_results, "generate", "generate_status")
    if isinstance(value, str) and value:
        return value
    return _check_result_status(check_results, "generate")


def _semantic_quality_status(check_results: Sequence[Mapping[str, Any]]) -> str:
    value = _check_metric(check_results, "quality", "quality_status")
    if isinstance(value, str) and value:
        return value
    return _check_result_status(check_results, "quality")


def _release_gate(
    *,
    case: Mapping[str, Any],
    selected_checks: Sequence[str],
    check_results: Sequence[Mapping[str, Any]],
    generation_report: JsonObject | None,
) -> JsonObject:
    release_case = _case_has_quality_gold(case)
    selected = set(selected_checks)
    required_checks = list(RELEASE_FINAL_GENERATION_CHECKS) if release_case else []
    missing_checks = [name for name in required_checks if name not in selected]
    failed_checks = [
        name
        for name in required_checks
        if name in selected and _check_result_status(check_results, name) != "PASS"
    ]
    generate_status = _semantic_generate_status(check_results)
    quality_status = _semantic_quality_status(check_results)
    gate: JsonObject = {
        "status": "NOT_EVALUATED",
        "releasable": False,
        "release_case": release_case,
        "required_checks": required_checks,
        "checks_requested": list(selected_checks),
        "missing_checks": missing_checks,
        "failed_checks": failed_checks,
        "generate_status": generate_status,
        "generate_check_status": _check_result_status(check_results, "generate"),
        "quality_status": quality_status,
        "quality_check_status": _check_result_status(check_results, "quality"),
        "final_snapshot": _safe_final_snapshot(generation_report),
        "reasons": [],
    }
    reasons: list[str] = []
    if not release_case:
        reasons.append("case_has_no_quality_gold")
    if missing_checks:
        reasons.append("release_checks_not_selected")
    if reasons:
        gate["reasons"] = reasons
        return gate
    if failed_checks:
        reasons.append("release_required_check_failed")
    if generate_status != "COMPLETE":
        reasons.append("generate_status_not_complete")
    if quality_status != "PASS":
        reasons.append("quality_status_not_pass")
    snapshot = gate["final_snapshot"]
    if not isinstance(snapshot, dict) or snapshot.get("render_bound_to_docx") is not True:
        reasons.append("final_snapshot_not_bound_to_render")
    if reasons:
        gate["status"] = "FAIL"
        gate["reasons"] = list(dict.fromkeys(reasons))
        return gate
    gate["status"] = "PASS"
    gate["releasable"] = True
    gate["reasons"] = []
    return gate


def _run_check(
    name: str,
    operation: Any,
) -> tuple[JsonObject, Any]:
    started = time.monotonic()
    try:
        metrics, context = operation()
    except _CheckFailure as error:
        return (
            {
                "name": name,
                "status": "FAIL",
                "duration_seconds": round(time.monotonic() - started, 3),
                "assertions": error.assertions,
                "metrics": error.metrics,
                "failure": {"code": error.code, "message": error.message},
            },
            None,
        )
    except (
        FinalGenerationEvalInputError,
        OSError,
        json.JSONDecodeError,
        yaml.YAMLError,
        ToolFailure,
    ) as error:
        code = getattr(error, "code", "final_generation_eval_check_failed")
        message = getattr(error, "message", str(error))
        return (
            {
                "name": name,
                "status": "FAIL",
                "duration_seconds": round(time.monotonic() - started, 3),
                "assertions": 0,
                "metrics": {},
                "failure": {"code": code, "message": message},
            },
            None,
        )
    result = {
        "name": name,
        "status": "PASS",
        "duration_seconds": round(time.monotonic() - started, 3),
        "assertions": int(metrics.pop("assertions", 0)),
        "metrics": metrics,
        "failure": None,
    }
    return result, context


def _skipped(name: str, reason: str) -> JsonObject:
    return {
        "name": name,
        "status": "SKIPPED",
        "duration_seconds": 0.0,
        "assertions": 0,
        "metrics": {},
        "failure": {"code": reason, "message": "Skipped because a required prior check failed."},
    }


def _has_failed(results: Sequence[Mapping[str, Any]]) -> bool:
    return any(item.get("status") == "FAIL" for item in results)


class _InputContext:
    def __init__(
        self,
        *,
        case: JsonObject,
        input_package: Path,
        manifest: JsonObject,
        student_content: JsonObject,
        fill_contract: JsonObject,
        registry: JsonObject,
        school_style_candidates: list[Any],
        school_known_gaps: list[Any],
        style_manifest: JsonObject,
    ) -> None:
        self.case = case
        self.input_package = input_package
        self.manifest = manifest
        self.student_content = student_content
        self.fill_contract = fill_contract
        self.registry = registry
        self.school_style_candidates = school_style_candidates
        self.school_known_gaps = school_known_gaps
        self.style_manifest = style_manifest


def _check_input_package(
    *,
    repository: Path,
    case: JsonObject,
) -> tuple[JsonObject, _InputContext]:
    context = _load_input_context(repository=repository, case=case)
    root = context.input_package
    assertions = 0

    def check(condition: bool, code: str, message: str) -> None:
        nonlocal assertions
        if not condition:
            raise _CheckFailure(code, message)
        assertions += 1

    required = (
        "student.docx",
        "student-content.json",
        "final-template.docx",
        "fill-contract.yaml",
        "content-fields.yaml",
        "style/school_style_candidates.json",
        "style/school_known_gaps.json",
        "style/manifest.json",
        "manifest.json",
    )
    for name in required:
        check((root / name).is_file(), "final_generation_input_missing", f"{name} is missing.")

    raw_files = context.manifest.get("files")
    check(
        isinstance(raw_files, dict),
        "final_generation_manifest_invalid",
        "manifest.files is missing.",
    )
    files = cast(Mapping[str, Any], raw_files)
    for name, meta in sorted(files.items()):
        check(
            isinstance(meta, dict),
            "final_generation_manifest_invalid",
            f"{name} metadata is invalid.",
        )
        path = root / str(name)
        check(path.is_file(), "final_generation_manifest_file_missing", f"{name} is missing.")
        check(
            sha256_file(path) == meta.get("sha256"),
            "final_generation_manifest_sha_mismatch",
            f"{name} sha256 does not match manifest.",
        )
        check(
            path.stat().st_size == meta.get("bytes"),
            "final_generation_manifest_size_mismatch",
            f"{name} byte size does not match manifest.",
        )

    check(
        context.student_content.get("schema_version") == "docfit-student-content-model/v2",
        "final_generation_student_content_schema_invalid",
        "student-content.json must use docfit-student-content-model/v2.",
    )
    check(
        context.fill_contract.get("schema_version") == "docfit-template-fill-contract/v2",
        "final_generation_fill_contract_schema_invalid",
        "fill-contract.yaml must use docfit-template-fill-contract/v2.",
    )
    check(
        context.manifest.get("schema_version") == "docfit-final-generation-input-package/v1",
        "final_generation_input_manifest_schema_invalid",
        "manifest.json must use docfit-final-generation-input-package/v1.",
    )
    check(
        context.style_manifest.get("schema_version") == "docfit-final-generation-style-inputs/v1",
        "final_generation_style_manifest_schema_invalid",
        "style/manifest.json must use docfit-final-generation-style-inputs/v1.",
    )

    registry_identity = {
        "registry_id": context.registry.get("registry_id"),
        "registry_version": context.registry.get("registry_version"),
        "sha256": sha256_file(root / "content-fields.yaml"),
    }
    contract_registry_ref = _mapping(context.fill_contract.get("field_registry_ref"))
    student_registry_ref = _mapping(context.student_content.get("registry"))
    bindings = {
        "student_content_binds_student_docx": (
            context.student_content.get("source_sha256") == sha256_file(root / "student.docx")
        ),
        "fill_contract_binds_final_template_docx": (
            context.fill_contract.get("template_sha256")
            == sha256_file(root / "final-template.docx")
        ),
        "fill_contract_binds_registry": all(
            contract_registry_ref.get(key) == registry_identity.get(key)
            for key in ("registry_id", "registry_version", "sha256")
        ),
        "student_content_binds_registry": all(
            student_registry_ref.get(key) == registry_identity.get(key)
            for key in ("registry_id", "registry_version", "sha256")
        ),
    }
    for key, value in bindings.items():
        check(value, "final_generation_input_binding_failed", f"{key} is false.")

    metrics: JsonObject = {
        "assertions": assertions,
        "bindings": bindings,
        "student_item_count": len(context.student_content.get("items") or []),
        "student_field_result_count": len(context.student_content.get("field_results") or []),
        "slot_count": len(context.fill_contract.get("slots") or []),
        "style_count": len(context.fill_contract.get("styles") or []),
    }
    return metrics, context


def _check_style_inputs(context: _InputContext) -> tuple[JsonObject, _InputContext]:
    assertions = 0

    def check(condition: bool, code: str, message: str) -> None:
        nonlocal assertions
        if not condition:
            raise _CheckFailure(code, message)
        assertions += 1

    expected = _mapping(context.case.get("expected"))
    check(
        len(context.school_style_candidates)
        == context.style_manifest.get("school_style_candidate_count"),
        "final_generation_style_candidate_count_mismatch",
        "school_style_candidates count does not match style manifest.",
    )
    check(
        len(context.school_known_gaps) == context.style_manifest.get("school_known_gap_count"),
        "final_generation_style_known_gap_count_mismatch",
        "school_known_gaps count does not match style manifest.",
    )
    if "school_style_candidate_count" in expected:
        check(
            len(context.school_style_candidates) == expected.get("school_style_candidate_count"),
            "final_generation_style_candidate_count_unexpected",
            "school_style_candidate_count does not match case expectation.",
        )
    if "school_known_gap_count" in expected:
        check(
            len(context.school_known_gaps) == expected.get("school_known_gap_count"),
            "final_generation_style_known_gap_count_unexpected",
            "school_known_gap_count does not match case expectation.",
        )
    if expected.get("selection_case") == "no_school_candidate_with_explicit_known_gaps":
        check(
            len(context.school_style_candidates) == 0 and len(context.school_known_gaps) > 0,
            "final_generation_style_known_gap_case_invalid",
            "Known-gap fallback case requires zero school candidates and at least one known gap.",
        )
    return (
        {
            "assertions": assertions,
            "school_style_candidate_count": len(context.school_style_candidates),
            "school_known_gap_count": len(context.school_known_gaps),
            "school_observation_set_digest": context.style_manifest.get(
                "school_observation_set_digest"
            ),
        },
        context,
    )


def _check_generate(
    context: _InputContext,
    output_directory: Path,
) -> tuple[JsonObject, JsonObject]:
    expected = _mapping(context.case.get("expected"))
    report = run_final_generation(
        FinalGenerationRequest(
            source_docx=context.input_package / "student.docx",
            student_content=context.input_package / "student-content.json",
            template_docx=context.input_package / "final-template.docx",
            fill_contract=context.input_package / "fill-contract.yaml",
            field_registry=context.input_package / "content-fields.yaml",
            output_directory=output_directory,
        )
    )
    assertions = 0

    def check(condition: bool, code: str, message: str) -> None:
        nonlocal assertions
        if not condition:
            raise _CheckFailure(code, message)
        assertions += 1

    report_status = report.get("status")
    if report_status in {"ERROR", "NEEDS_INPUT"}:
        failure = _mapping(report.get("failure"))
        code = failure.get("code")
        message = failure.get("message")
        raise _CheckFailure(
            str(code) if isinstance(code, str) and code else "final_generation_generate_failed",
            (
                str(message)
                if isinstance(message, str) and message
                else "generate-final did not produce a usable candidate."
            ),
            metrics={
                "generate_status": report_status,
                "failure": dict(failure),
                "run_report": str(output_directory / "run-report.json"),
            },
        )

    expected_status = expected.get("current_generate_status")
    if expected_status:
        check(
            report.get("status") == expected_status,
            "final_generation_generate_status_unexpected",
            "generate-final status does not match case expectation.",
        )
    candidate = Path(str(report.get("candidate_docx", "")))
    check(
        candidate.is_file(),
        "final_generation_candidate_missing",
        "candidate.docx was not generated.",
    )
    candidate_sha256 = report.get("candidate_sha256")
    check(
        isinstance(candidate_sha256, str) and sha256_file(candidate) == candidate_sha256,
        "final_generation_candidate_sha_mismatch",
        "candidate_docx sha256 does not match the run report.",
    )
    if expected.get("candidate_sha256"):
        check(
            candidate_sha256 == expected.get("candidate_sha256"),
            "final_generation_candidate_sha_unexpected",
            "candidate sha256 does not match case expectation.",
        )
    if expected.get("page_count") is not None:
        check(
            report.get("page_count") == expected.get("page_count"),
            "final_generation_page_count_unexpected",
            "candidate page count does not match case expectation.",
        )
    if expected.get("partial_reasons") is not None:
        check(
            report.get("partial_reasons") == expected.get("partial_reasons"),
            "final_generation_partial_reasons_unexpected",
            "partial reasons do not match case expectation.",
        )
    final_docx = Path(str(report.get("final_docx", "")))
    final_sha256 = report.get("final_sha256")
    if expected_status == "COMPLETE":
        check(
            final_docx.is_file(),
            "final_generation_final_docx_missing",
            "final.docx was not generated for a COMPLETE run.",
        )
        check(
            isinstance(final_sha256, str) and sha256_file(final_docx) == final_sha256,
            "final_generation_final_sha_mismatch",
            "final_docx sha256 does not match the run report.",
        )
    candidate_pdf = Path(str(report.get("candidate_pdf", "")))
    check(
        candidate_pdf.is_file(),
        "final_generation_candidate_pdf_missing",
        "candidate PDF render evidence was not generated.",
    )
    final_snapshot = _final_snapshot_from_generation_report(report)
    style_counts = _mapping(report.get("style_occurrence_counts"))
    check(
        style_counts.get("failed") == 0 and style_counts.get("unresolved") == 0,
        "final_generation_style_occurrence_failed",
        "style audit has failed or unresolved occurrences.",
    )
    return (
        {
            "assertions": assertions,
            "generate_status": report.get("status"),
            "candidate_docx": report.get("candidate_docx"),
            "candidate_sha256": candidate_sha256,
            "final_docx": report.get("final_docx"),
            "final_sha256": final_sha256,
            "candidate_pdf": report.get("candidate_pdf"),
            "render_ref": report.get("render_ref"),
            "page_count": report.get("page_count"),
            "partial_reasons": report.get("partial_reasons"),
            "style_occurrence_counts": report.get("style_occurrence_counts"),
            "final_snapshot": final_snapshot,
            "run_report": str(output_directory / "run-report.json"),
        },
        report,
    )


def _quality_requires_generate() -> tuple[JsonObject, None]:
    raise _CheckFailure(
        "final_generation_quality_requires_generate",
        "The quality check requires generate in the same --checks selection.",
    )


def _check_quality(
    *,
    repository: Path,
    context: _InputContext,
    generation_report: JsonObject,
    output_directory: Path,
) -> tuple[JsonObject, _InputContext]:
    expected = _mapping(context.case.get("expected"))
    quality = _mapping(expected.get("quality"))
    gold_value = quality.get("gold_docx")
    if not isinstance(gold_value, str) or not gold_value.strip():
        raise _CheckFailure(
            "final_generation_quality_gold_missing",
            "A quality check requires expected.quality.gold_docx in the selected case.",
        )
    gold_docx = (repository / gold_value).resolve()
    if not gold_docx.is_relative_to(repository) or not gold_docx.is_file():
        raise _CheckFailure(
            "final_generation_quality_gold_invalid",
            "The configured quality gold_docx must be a file inside the repository.",
        )
    final_snapshot = _final_snapshot_from_generation_report(generation_report)
    actual_docx = Path(str(final_snapshot["docx"]))
    actual_pdf_value = final_snapshot.get("pdf")
    actual_pdf = Path(actual_pdf_value) if isinstance(actual_pdf_value, str) else None
    thresholds = _mapping(quality.get("thresholds"))
    report = run_final_generation_quality_compare(
        actual_docx=actual_docx,
        gold_docx=gold_docx,
        output_directory=output_directory,
        thresholds=thresholds,
        actual_pdf=actual_pdf,
    )
    metrics: JsonObject = {
        "quality_status": report.get("status"),
        "gold_docx": str(gold_docx),
        "actual_docx": str(actual_docx),
        "json_report": report.get("json_report"),
        "markdown_report": report.get("markdown_report"),
        "text": report.get("text"),
        "structure": report.get("structure"),
        "media": report.get("media"),
        "visual": report.get("visual"),
        "threshold_failures": report.get("threshold_failures"),
        "final_snapshot": final_snapshot,
    }
    if report.get("status") != "PASS":
        failures = report.get("threshold_failures")
        count = len(failures) if isinstance(failures, list) else 0
        raise _CheckFailure(
            "final_generation_quality_gate_failed",
            f"Gold quality comparison failed {count} threshold(s).",
            assertions=1,
            metrics=metrics,
        )
    metrics["assertions"] = 1
    return metrics, context


def _safe_final_snapshot(generation_report: JsonObject | None) -> JsonObject | None:
    if generation_report is None:
        return None
    try:
        return _final_snapshot_from_generation_report(generation_report)
    except _CheckFailure as error:
        return {
            "render_bound_to_docx": False,
            "failure": {"code": error.code, "message": error.message},
        }


def _final_snapshot_from_generation_report(generation_report: Mapping[str, Any]) -> JsonObject:
    final_value = generation_report.get("final_docx")
    candidate_value = generation_report.get("candidate_docx")
    if isinstance(final_value, str) and final_value.strip():
        docx_kind = "final"
        docx = Path(final_value)
        reported_docx_sha256 = generation_report.get("final_sha256")
    elif isinstance(candidate_value, str) and candidate_value.strip():
        docx_kind = "candidate"
        docx = Path(candidate_value)
        reported_docx_sha256 = generation_report.get("candidate_sha256")
    else:
        raise _CheckFailure(
            "final_generation_quality_actual_missing",
            "The generate report has no DOCX to compare.",
        )
    if not docx.is_file():
        raise _CheckFailure(
            "final_generation_quality_actual_missing",
            "The generated DOCX for quality comparison is missing.",
        )
    docx_sha256 = sha256_file(docx)
    if isinstance(reported_docx_sha256, str) and reported_docx_sha256 != docx_sha256:
        raise _CheckFailure(
            "final_generation_snapshot_sha_mismatch",
            "The generated DOCX sha256 does not match the run report.",
        )
    render_ref = generation_report.get("render_ref")
    pdf_value = generation_report.get("candidate_pdf")
    if not isinstance(render_ref, str) or not render_ref.strip():
        raise _CheckFailure(
            "final_generation_snapshot_render_missing",
            "The generate report has no render_ref bound to the DOCX snapshot.",
        )
    if not isinstance(pdf_value, str) or not pdf_value.strip():
        raise _CheckFailure(
            "final_generation_snapshot_pdf_missing",
            "The generate report has no PDF bound to the DOCX snapshot.",
        )
    pdf = Path(pdf_value)
    if not pdf.is_file():
        raise _CheckFailure(
            "final_generation_snapshot_pdf_missing",
            "The generated PDF evidence for quality comparison is missing.",
        )
    try:
        render_path, manifest = EvidenceStore(docx.parent).resolve_render(render_ref)
    except ToolFailure as error:
        raise _CheckFailure(
            "final_generation_snapshot_render_unbound",
            "The generate report render_ref cannot be resolved from the final snapshot.",
        ) from error
    bound_pdf = (render_path / "document.pdf").resolve()
    if pdf.resolve() != bound_pdf:
        raise _CheckFailure(
            "final_generation_snapshot_pdf_mismatch",
            "The generate report PDF path does not match the render_ref evidence.",
        )
    render_document_sha256 = manifest.get("document_sha256")
    if render_document_sha256 != docx_sha256:
        raise _CheckFailure(
            "final_generation_snapshot_render_mismatch",
            "The generate report PDF is not bound to the selected DOCX snapshot.",
        )
    return {
        "kind": docx_kind,
        "docx": str(docx),
        "docx_sha256": docx_sha256,
        "reported_docx_sha256": reported_docx_sha256,
        "pdf": str(bound_pdf),
        "pdf_sha256": sha256_file(bound_pdf),
        "render_ref": render_ref,
        "render_document_sha256": render_document_sha256,
        "render_bound_to_docx": True,
        "renderer": manifest.get("renderer"),
        "page_count": manifest.get("page_count"),
    }


def _load_input_context(*, repository: Path, case: JsonObject) -> _InputContext:
    root = _input_package_path(repository, case)
    return _InputContext(
        case=case,
        input_package=root,
        manifest=_read_json_object(root / "manifest.json"),
        student_content=_read_json_object(root / "student-content.json"),
        fill_contract=_read_yaml_object(root / "fill-contract.yaml"),
        registry=_read_yaml_object(root / "content-fields.yaml"),
        school_style_candidates=_read_json_array(root / "style/school_style_candidates.json"),
        school_known_gaps=_read_json_array(root / "style/school_known_gaps.json"),
        style_manifest=_read_json_object(root / "style/manifest.json"),
    )


def _load_case(repository: Path, case_id: str) -> JsonObject:
    if not _CASE_ID.fullmatch(case_id):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_case_id_invalid",
            "Final-generation eval case ids must use lowercase letters, digits, dots, "
            "underscores, or hyphens.",
        )
    path = repository / "evals/final-generation/cases" / case_id / "case.json"
    if not path.is_file():
        raise FinalGenerationEvalInputError(
            "final_generation_eval_case_missing",
            f"Final-generation eval case does not exist: {case_id}",
        )
    case = _read_json_object(path)
    if case.get("schema_version") != FINAL_GENERATION_EVAL_CASE_SCHEMA_VERSION:
        raise FinalGenerationEvalInputError(
            "final_generation_eval_case_schema_invalid",
            "Final-generation eval case has an unsupported schema_version.",
        )
    if case.get("case_id") != case_id:
        raise FinalGenerationEvalInputError(
            "final_generation_eval_case_id_mismatch",
            "Final-generation eval case_id does not match its selected directory.",
        )
    return case


def _input_package_path(repository: Path, case: Mapping[str, Any]) -> Path:
    value = case.get("input_package")
    if not isinstance(value, str) or not value.strip():
        raise FinalGenerationEvalInputError(
            "final_generation_eval_input_package_missing",
            "Final-generation eval case requires input_package.",
        )
    path = (repository / value).resolve()
    if not path.is_relative_to(repository):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_input_package_outside_repo",
            "Final-generation eval input_package must stay inside the repository.",
        )
    if not path.is_dir():
        raise FinalGenerationEvalInputError(
            "final_generation_eval_input_package_not_found",
            f"Final-generation eval input_package does not exist: {value}",
        )
    return path


def _prepare_output_directory(repository: Path, output_directory: Path) -> Path:
    output = (
        output_directory.resolve()
        if output_directory.is_absolute()
        else (repository / output_directory).resolve()
    )
    if not output.is_relative_to(repository):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_output_outside_repo",
            "Final-generation eval output must stay inside the repository.",
        )
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_output_not_empty",
            "Final-generation eval output directory must be absent or empty.",
        )
    output.mkdir(parents=True, exist_ok=True)
    return output


def _read_json_object(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_json_invalid",
            f"{path} must contain one JSON object.",
        )
    return value


def _read_json_array(path: Path) -> list[Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_json_invalid",
            f"{path} must contain one JSON array.",
        )
    return value


def _read_yaml_object(path: Path) -> JsonObject:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FinalGenerationEvalInputError(
            "final_generation_eval_yaml_invalid",
            f"{path} must contain one YAML object.",
        )
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "ALLOWED_FINAL_GENERATION_CHECKS",
    "DEFAULT_FINAL_GENERATION_BASE_ROOT",
    "DEFAULT_FINAL_GENERATION_CHECKS",
    "DEFAULT_FINAL_GENERATION_SCHOOL_IDS",
    "DEFAULT_FINAL_GENERATION_STUDENT_IDS",
    "FinalGenerationEvalInputError",
    "RELEASE_FINAL_GENERATION_CHECKS",
    "list_final_generation_cases",
    "list_final_generation_combinations",
    "parse_final_generation_checks",
    "run_final_generation_combinations",
    "run_final_generation_eval",
]
