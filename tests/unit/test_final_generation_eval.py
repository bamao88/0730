from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from docfit.evals import final_generation as fg
from docfit.evals.final_generation import run_final_generation_eval


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8")


def _prepare_case(repository: Path) -> None:
    package = repository / "temp/final-generation-e2e-inputs-20260816/student-001-njau-known-gap"
    (package / "style").mkdir(parents=True)
    (package / "student.docx").write_bytes(b"student-docx")
    (package / "final-template.docx").write_bytes(b"template-docx")

    registry = {
        "registry_id": "docfit.thesis.content_fields",
        "registry_version": "0.5.0",
        "fields": [],
    }
    _write_yaml(package / "content-fields.yaml", registry)
    registry_ref = {
        "registry_id": registry["registry_id"],
        "registry_version": registry["registry_version"],
        "sha256": _sha(package / "content-fields.yaml"),
    }
    student_content = {
        "schema_version": "docfit-student-content-model/v2",
        "source_sha256": _sha(package / "student.docx"),
        "registry": registry_ref,
        "items": [{"field_id": "body.paragraph"}],
        "field_results": [{"field_id": "body.paragraph"}],
        "source_coverage": {"unsupported_source_object_ids": []},
    }
    _write_json(package / "student-content.json", student_content)
    fill_contract = {
        "schema_version": "docfit-template-fill-contract/v2",
        "template_sha256": _sha(package / "final-template.docx"),
        "field_registry_ref": registry_ref,
        "slots": [{"slot_id": "body.paragraph.1"}],
        "styles": [{"style_contract_id": "style.body"}],
    }
    _write_yaml(package / "fill-contract.yaml", fill_contract)
    _write_json(package / "style/school_style_candidates.json", [])
    _write_json(
        package / "style/school_known_gaps.json",
        [{"style_role_id": "style.body", "property_paths": ["run.font_size_pt"]}],
    )
    style_manifest = {
        "schema_version": "docfit-final-generation-style-inputs/v1",
        "school_style_candidate_count": 0,
        "school_known_gap_count": 1,
        "school_observation_set_digest": "a" * 64,
    }
    _write_json(package / "style/manifest.json", style_manifest)
    files = {}
    for name in (
        "student.docx",
        "student-content.json",
        "final-template.docx",
        "fill-contract.yaml",
        "content-fields.yaml",
        "style/school_style_candidates.json",
        "style/school_known_gaps.json",
        "style/manifest.json",
    ):
        path = package / name
        files[name] = {"sha256": _sha(path), "bytes": path.stat().st_size}
    _write_json(
        package / "manifest.json",
        {
            "schema_version": "docfit-final-generation-input-package/v1",
            "package_id": "student-001-njau-known-gap",
            "files": files,
        },
    )
    _write_json(
        repository / "evals/final-generation/cases/student-001-njau-known-gap/case.json",
        {
            "schema_version": "docfit-final-generation-eval-case/v1",
            "case_id": "student-001-njau-known-gap",
            "input_package": (
                "temp/final-generation-e2e-inputs-20260816/student-001-njau-known-gap"
            ),
            "expected": {
                "school_style_candidate_count": 0,
                "school_known_gap_count": 1,
                "selection_case": "no_school_candidate_with_explicit_known_gaps",
            },
        },
    )


def _prepare_base_package(repository: Path) -> Path:
    base = repository / "base"
    student_root = base / "students/student-001"
    school_root = base / "schools/njau-undergraduate"
    student_root.mkdir(parents=True)
    school_root.mkdir(parents=True)
    (student_root / "student.docx").write_bytes(b"student-docx")
    (school_root / "final-template.docx").write_bytes(b"template-docx")
    registry = {
        "registry_id": "docfit.thesis.content_fields",
        "registry_version": "0.5.0",
        "fields": [],
    }
    _write_yaml(student_root / "content-fields.yaml", registry)
    _write_yaml(school_root / "content-fields.yaml", registry)
    registry_ref = {
        "registry_id": registry["registry_id"],
        "registry_version": registry["registry_version"],
        "sha256": _sha(school_root / "content-fields.yaml"),
    }
    _write_json(
        student_root / "student-content.json",
        {
            "schema_version": "docfit-student-content-model/v2",
            "status": "READY",
            "source_sha256": _sha(student_root / "student.docx"),
            "registry": registry_ref,
            "items": [{"field_id": "body.paragraph"}],
            "field_results": [{"field_id": "body.paragraph"}],
            "source_coverage": {"unsupported_source_object_ids": []},
        },
    )
    _write_yaml(
        school_root / "fill-contract.yaml",
        {
            "schema_version": "docfit-template-fill-contract/v2",
            "status": "candidate_pending_human_acceptance",
            "template_sha256": _sha(school_root / "final-template.docx"),
            "field_registry_ref": registry_ref,
            "slots": [{"slot_id": "body.paragraph.1"}],
            "styles": [{"style_contract_id": "style.body"}],
            "regions": [],
            "provenance": {
                "profile_registry_digest": "b" * 64,
                "school_observation_set_digest": "c" * 64,
                "school_style_candidates": [],
                "known_school_style_gaps": [
                    {
                        "style_role_id": "style.body",
                        "property_paths": ["run.font_size_pt"],
                    }
                ],
            },
        },
    )
    return base


def test_final_generation_eval_runs_selected_input_and_style_checks(tmp_path: Path) -> None:
    _prepare_case(tmp_path)

    report = run_final_generation_eval(
        repository=tmp_path,
        case_id="student-001-njau-known-gap",
        checks=("input", "style"),
        output_directory=tmp_path / "out",
    )

    assert report["status"] == "PASS"
    assert report["checks_requested"] == ["input", "style"]
    assert report["check_status"] == "PASS"
    assert report["release_status"] == "NOT_EVALUATED"
    assert report["releasable"] is False
    assert [item["name"] for item in report["checks"]] == ["input", "style"]
    assert report["checks"][0]["metrics"]["bindings"] == {
        "fill_contract_binds_final_template_docx": True,
        "fill_contract_binds_registry": True,
        "student_content_binds_registry": True,
        "student_content_binds_student_docx": True,
    }
    assert report["checks"][1]["metrics"]["school_known_gap_count"] == 1
    assert (tmp_path / "out/eval-report.json").is_file()


def _mark_case_as_release(repository: Path) -> None:
    gold = repository / "gold.docx"
    gold.write_bytes(b"gold-docx")
    case_path = (
        repository / "evals/final-generation/cases/student-001-njau-known-gap/case.json"
    )
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["default_checks"] = ["input", "style", "generate"]
    case["expected"]["current_generate_status"] = "COMPLETE"
    case["expected"]["quality"] = {
        "gold_docx": "gold.docx",
        "thresholds": {"min_full_text_similarity": 0.99},
    }
    _write_json(case_path, case)


def test_release_case_defaults_to_quality_gate_and_fails_release(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _prepare_case(tmp_path)
    _mark_case_as_release(tmp_path)

    def fake_generate(
        context: object,
        output_directory: Path,
    ) -> tuple[dict[str, object], dict[str, object]]:
        return {"assertions": 1, "generate_status": "COMPLETE"}, {"status": "COMPLETE"}

    def fake_quality(**_: object) -> tuple[dict[str, object], object]:
        raise fg._CheckFailure(
            "final_generation_quality_gate_failed",
            "Gold quality comparison failed 1 threshold(s).",
            assertions=1,
            metrics={
                "quality_status": "FAIL",
                "threshold_failures": [{"metric": "min_full_text_similarity"}],
            },
        )

    monkeypatch.setattr(fg, "_check_generate", fake_generate)
    monkeypatch.setattr(fg, "_check_quality", fake_quality)

    report = run_final_generation_eval(
        repository=tmp_path,
        case_id="student-001-njau-known-gap",
        output_directory=tmp_path / "release-out",
    )

    assert report["checks_requested"] == list(fg.RELEASE_FINAL_GENERATION_CHECKS)
    assert [item["name"] for item in report["checks"]] == [
        "input",
        "style",
        "generate",
        "quality",
    ]
    assert report["check_status"] == "FAIL"
    assert report["generate_status"] == "COMPLETE"
    assert report["quality_status"] == "FAIL"
    assert report["release_status"] == "FAIL"
    assert report["releasable"] is False
    assert "quality_status_not_pass" in report["release_gate"]["reasons"]

    listed = fg.list_final_generation_cases(tmp_path)
    assert listed[0]["default_checks"] == list(fg.RELEASE_FINAL_GENERATION_CHECKS)
    assert listed[0]["release_case"] is True


def test_generate_only_release_case_is_not_releasable(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _prepare_case(tmp_path)
    _mark_case_as_release(tmp_path)

    def fake_generate(
        context: object,
        output_directory: Path,
    ) -> tuple[dict[str, object], dict[str, object]]:
        return {"assertions": 1, "generate_status": "COMPLETE"}, {"status": "COMPLETE"}

    monkeypatch.setattr(fg, "_check_generate", fake_generate)

    report = run_final_generation_eval(
        repository=tmp_path,
        case_id="student-001-njau-known-gap",
        checks=("input", "style", "generate"),
        output_directory=tmp_path / "generate-out",
    )

    assert report["check_status"] == "PASS"
    assert report["generate_status"] == "COMPLETE"
    assert report["quality_status"] == "NOT_RUN"
    assert report["release_status"] == "NOT_EVALUATED"
    assert report["releasable"] is False
    assert report["release_gate"]["missing_checks"] == ["quality"]
    assert report["release_gate"]["reasons"] == ["release_checks_not_selected"]


def test_quality_uses_pdf_bound_to_same_final_snapshot(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    run_root = tmp_path / "generate-final"
    render_hash = "a" * 64
    render_root = run_root / ".docfit/evidence/renders" / render_hash
    render_root.mkdir(parents=True)
    final_docx = run_root / "final.docx"
    candidate_docx = run_root / "candidate.docx"
    gold_docx = tmp_path / "gold.docx"
    final_docx.write_bytes(b"same-docx")
    candidate_docx.write_bytes(b"same-docx")
    gold_docx.write_bytes(b"gold-docx")
    pdf = render_root / "document.pdf"
    pdf.write_bytes(b"pdf")
    render_ref = f"render:v2:{render_hash}"
    _write_json(
        render_root / "manifest.json",
        {
            "schema_version": 2,
            "render_ref": render_ref,
            "document_sha256": _sha(final_docx),
            "page_count": 1,
            "renderer": {"name": "libreoffice"},
            "files": [
                {
                    "path": "document.pdf",
                    "sha256": _sha(pdf),
                    "bytes": pdf.stat().st_size,
                }
            ],
        },
    )
    context = fg._InputContext(
        case={
            "expected": {
                "quality": {
                    "gold_docx": "gold.docx",
                    "thresholds": {"min_full_text_similarity": 0.99},
                }
            }
        },
        input_package=tmp_path,
        manifest={},
        student_content={},
        fill_contract={},
        registry={},
        school_style_candidates=[],
        school_known_gaps=[],
        style_manifest={},
    )
    captured: dict[str, Path | None] = {}

    def fake_compare(
        *,
        actual_docx: Path,
        gold_docx: Path,
        output_directory: Path,
        thresholds: object,
        actual_pdf: Path | None,
    ) -> dict[str, object]:
        captured["actual_docx"] = actual_docx
        captured["gold_docx"] = gold_docx
        captured["actual_pdf"] = actual_pdf
        return {
            "status": "PASS",
            "json_report": str(output_directory / "quality-report.json"),
            "markdown_report": str(output_directory / "quality-report.md"),
            "text": {},
            "structure": {},
            "media": {},
            "visual": {},
            "threshold_failures": [],
        }

    monkeypatch.setattr(fg, "run_final_generation_quality_compare", fake_compare)

    metrics, returned_context = fg._check_quality(
        repository=tmp_path,
        context=context,
        generation_report={
            "status": "COMPLETE",
            "candidate_docx": str(candidate_docx),
            "candidate_sha256": _sha(candidate_docx),
            "final_docx": str(final_docx),
            "final_sha256": _sha(final_docx),
            "candidate_pdf": str(pdf),
            "render_ref": render_ref,
        },
        output_directory=tmp_path / "quality",
    )

    assert returned_context is context
    assert captured["actual_docx"] == final_docx
    assert captured["gold_docx"] == gold_docx
    assert captured["actual_pdf"] == pdf.resolve()
    assert metrics["quality_status"] == "PASS"
    assert metrics["final_snapshot"]["docx_sha256"] == _sha(final_docx)
    assert metrics["final_snapshot"]["render_document_sha256"] == _sha(final_docx)
    assert metrics["final_snapshot"]["render_bound_to_docx"] is True


def test_generate_check_surfaces_underlying_run_report_failure(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    context = fg._InputContext(
        case={},
        input_package=tmp_path,
        manifest={},
        student_content={},
        fill_contract={},
        registry={},
        school_style_candidates=[],
        school_known_gaps=[],
        style_manifest={},
    )

    def fake_generate(request: object) -> dict[str, object]:
        return {
            "status": "ERROR",
            "failure": {
                "code": "student_fill_content_missing",
                "message": "The candidate is missing selected source text.",
            },
        }

    monkeypatch.setattr(fg, "run_final_generation", fake_generate)

    with pytest.raises(fg._CheckFailure) as error:
        fg._check_generate(context, tmp_path / "generate")

    assert error.value.code == "student_fill_content_missing"
    assert error.value.metrics["generate_status"] == "ERROR"
    assert error.value.metrics["run_report"] == str(tmp_path / "generate/run-report.json")


def test_final_generation_combinations_materialize_input_package_and_run_style_checks(
    tmp_path: Path,
) -> None:
    base = _prepare_base_package(tmp_path)

    report = fg.run_final_generation_combinations(
        repository=tmp_path,
        base_root=base,
        students="001",
        schools="njau",
        checks=("input", "style"),
        output_directory=tmp_path / "combo-out",
    )

    assert report["check_status"] == "PASS"
    assert report["selection"] == {
        "base_root": str(base),
        "students": ["student-001"],
        "schools": ["njau-undergraduate"],
        "combination_count": 1,
    }
    run = report["runs"][0]
    assert run["case_id"] == "student-001__njau-undergraduate"
    assert run["checks_requested"] == ["input", "style"]
    assert run["checks"][1]["metrics"]["school_known_gap_count"] == 1
    input_package = Path(run["input_package"])
    assert (input_package / "manifest.json").is_file()
    assert (input_package / "style/school_known_gaps.json").is_file()
    assert (tmp_path / "combo-out/eval-combinations-report.json").is_file()


def test_final_generation_combinations_list_quality_gold_when_available(
    tmp_path: Path,
) -> None:
    base = _prepare_base_package(tmp_path)
    gold = (
        tmp_path
        / "temp/manual-gold-preparation/gold/30-cross-conversions/02-njau-undergraduate/"
        "njau-undergraduate__student-001__converted.docx"
    )
    gold.parent.mkdir(parents=True)
    gold.write_bytes(b"gold-docx")

    combinations = fg.list_final_generation_combinations(tmp_path, base_root=base)

    assert combinations == [
        {
            "case_id": "student-001__njau-undergraduate",
            "student_id": "student-001",
            "school_id": "njau-undergraduate",
            "input_package": "base",
            "quality_gold": (
                "temp/manual-gold-preparation/gold/30-cross-conversions/"
                "02-njau-undergraduate/njau-undergraduate__student-001__converted.docx"
            ),
            "release_case": True,
            "default_checks": list(fg.RELEASE_FINAL_GENERATION_CHECKS),
        }
    ]
