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


def test_manual_delivery_gate_preserves_unknown() -> None:
    checklist = (
        project_root() / "evals/manual/delivery-high-risk-checklist.md"
    ).read_text(encoding="utf-8")
    assert "PASS" in checklist
    assert "FAIL" in checklist
    assert "UNKNOWN" in checklist
    assert "never `PASS`" in checklist
