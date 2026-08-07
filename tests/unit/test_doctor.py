from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

from docfit.app.doctor import run_doctor
from docfit.app.smoke import SMOKE_CASE_VERSIONS, SMOKE_CASES, receipt_directory


def _make_project(root: Path) -> None:
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        (root / name).write_text("m0\n", encoding="utf-8")
    for skill_name in ("docfit-school-extract", "convert-thesis"):
        skill = root / ".claude" / "skills" / skill_name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {skill_name}\n---\n", encoding="utf-8")


def test_base_gate_ignores_optional_credentials_and_receipts(tmp_path: Path) -> None:
    _make_project(tmp_path)

    report = run_doctor(root=tmp_path, environment={}, python_version=(3, 12))

    assert report.gate == "PASS"
    assert report.exit_code == 0
    assert report.overall_status == "NOT_READY"
    assert (
        next(check for check in report.checks if check.name == "agent_backend_credentials").status
        == "NOT_READY"
    )


def test_agent_smoke_gate_requires_backend_and_current_receipts(tmp_path: Path) -> None:
    _make_project(tmp_path)

    missing = run_doctor(
        "agent-smoke",
        root=tmp_path,
        environment={},
        python_version=(3, 12),
    )

    assert missing.gate == "NOT_READY"
    directory = receipt_directory(tmp_path)
    directory.mkdir(parents=True)
    for case_name in SMOKE_CASES:
        (directory / f"{case_name}.json").write_text(
            json.dumps(
                {
                    "case": case_name,
                    "status": "PASS",
                    "case_version": SMOKE_CASE_VERSIONS[case_name],
                    "sdk_version": version("claude-agent-sdk"),
                }
            ),
            encoding="utf-8",
        )

    ready = run_doctor(
        "agent-smoke",
        root=tmp_path,
        environment={
            "DOCFIT_AGENT_BACKEND_ORDER": "kimi,minimax",
            "DOCFIT_KIMI_API_KEY": "test-only",
        },
        python_version=(3, 12),
    )

    assert ready.gate == "PASS"
    assert ready.exit_code == 0


def test_visual_renderer_gate_checks_the_fixed_pipeline(tmp_path: Path) -> None:
    _make_project(tmp_path)

    report = run_doctor(
        "visual-renderer",
        root=tmp_path,
        environment={},
        python_version=(3, 12),
    )

    assert {
        check.name for check in report.checks if "visual-renderer" in check.required_for
    } >= {
        "officecli_backend",
        "libreoffice_visual_renderer",
        "pdf_visual_derivation",
    }
    assert report.gate in {"PASS", "NOT_READY"}
    assert report.exit_code == (0 if report.gate == "PASS" else 1)


def test_base_gate_fails_for_wrong_python_or_missing_files(tmp_path: Path) -> None:
    report = run_doctor(root=tmp_path, environment={}, python_version=(3, 13))

    assert report.gate == "NOT_READY"
    assert report.exit_code == 1
    assert report.overall_status == "FAIL"
