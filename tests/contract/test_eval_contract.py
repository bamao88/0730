from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docfit.app.agent import project_root
from docfit.app.cli import build_parser


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_core_eval_cli_and_case_inventory() -> None:
    args = build_parser().parse_args(["eval", "--suite", "core", "--json"])
    assert args.command == "eval"
    assert args.suite == "core"
    assert args.as_json is True

    root = project_root()
    risk_cases = sorted((root / "evals/fixtures/risks").glob("*.json"))
    skill_cases = sorted((root / "evals/skills").glob("*.json"))
    assert len(risk_cases) == 5
    assert len(skill_cases) == 3
    assert {str(_read_object(path)["fixture"]) for path in risk_cases} == {
        "synthetic",
        "test-double",
    }
    assert {str(_read_object(path)["scope"]) for path in skill_cases} == {
        "simple",
        "complex",
        "mixed",
    }


def test_final_generation_eval_cli_and_case_inventory() -> None:
    args = build_parser().parse_args(
        [
            "eval",
            "--suite",
            "final-generation",
            "--case",
            "student-001-njau-known-gap",
            "--checks",
            "input,style",
            "--output",
            "temp/final-generation-e2e-verify-20260816/eval-run-001",
            "--json",
        ]
    )
    assert args.command == "eval"
    assert args.suite == "final-generation"
    assert args.case_id == "student-001-njau-known-gap"
    assert args.checks == "input,style"
    assert args.output_directory == "temp/final-generation-e2e-verify-20260816/eval-run-001"
    assert args.as_json is True

    root = project_root()
    case = _read_object(
        root / "evals/final-generation/cases/student-001-njau-known-gap/case.json"
    )
    assert case["schema_version"] == "docfit-final-generation-eval-case/v1"
    assert case["input_package"] == (
        "temp/final-generation-e2e-inputs-20260816/student-001-njau-known-gap"
    )
    assert case["expected"]["selection_case"] == (
        "no_school_candidate_with_explicit_known_gaps"
    )


def test_final_generation_eval_cli_accepts_base_package_combination_selectors() -> None:
    args = build_parser().parse_args(
        [
            "eval",
            "--suite",
            "final-generation",
            "--student",
            "001,002",
            "--school",
            "njau",
            "--checks",
            "input,style",
            "--base-root",
            "temp/final-generation-base-packages-20260816",
            "--output",
            "temp/final-generation-regression/selector-run-001",
            "--json",
        ]
    )

    assert args.command == "eval"
    assert args.suite == "final-generation"
    assert args.students == ["001,002"]
    assert args.schools == ["njau"]
    assert args.checks == "input,style"
    assert args.base_root == "temp/final-generation-base-packages-20260816"
    assert args.output_directory == "temp/final-generation-regression/selector-run-001"
    assert args.as_json is True


def test_manual_delivery_gate_preserves_unknown() -> None:
    checklist = (
        project_root() / "evals/manual/delivery-high-risk-checklist.md"
    ).read_text(encoding="utf-8")
    assert "PASS" in checklist
    assert "FAIL" in checklist
    assert "UNKNOWN" in checklist
    assert "不得写成 `PASS`" in checklist
