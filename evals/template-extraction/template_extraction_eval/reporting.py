"""Build and publish stable machine- and human-readable Eval reports."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from .models import (
    AssertionResult,
    AssertionStatus,
    EvalReport,
    Issue,
    ScoringConfig,
    Severity,
    stable_data,
)
from .scoring import score_assertions

REPORT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "report.schema.json"


def issues_from_assertions(assertions: tuple[AssertionResult, ...]) -> tuple[Issue, ...]:
    candidates = sorted(
        (
            item
            for item in assertions
            if item.status in {AssertionStatus.FAIL, AssertionStatus.UNKNOWN}
        ),
        key=lambda item: (item.view.value, item.dimension, item.assertion_id),
    )
    return tuple(
        Issue(
            issue_id=f"ISS-{index:04d}",
            severity=(
                Severity.ERROR if item.status is AssertionStatus.FAIL else Severity.WARNING
            ),
            view=item.view,
            dimension=item.dimension,
            assertion_id=item.assertion_id,
            status=item.status,
            message=item.message,
            region_id=item.region_id,
            slot_id=item.slot_id,
            gold_locator=item.gold_locator,
            actual_locator=item.actual_locator,
            expected=item.expected,
            actual=item.actual,
        )
        for index, item in enumerate(candidates, start=1)
    )


def build_report(
    *,
    case_id: str,
    run_id: str,
    assertions: tuple[AssertionResult, ...],
    input_hashes: dict[str, str],
    report_config: dict[str, Any],
    scoring_config: ScoringConfig,
    responsibility_coverage: float = 1.0,
) -> EvalReport:
    scoring = score_assertions(assertions, scoring_config)
    return EvalReport(
        schema_version="docfit-template-extraction-eval-report/v1",
        case_id=case_id,
        run_id=run_id,
        status=scoring.verdict,
        total_score=scoring.total_score,
        provisional=scoring.provisional,
        analysis_coverage=scoring.analysis_coverage,
        responsibility_coverage=responsibility_coverage,
        views=scoring.views,
        dimensions=scoring.dimensions,
        issues=issues_from_assertions(assertions),
        inputs=dict(input_hashes),
        config=dict(report_config),
    )


def report_to_dict(report: EvalReport) -> dict[str, Any]:
    data = cast(dict[str, Any], stable_data(report))
    data["score"] = {
        "total": data.pop("total_score"),
        "provisional": data.pop("provisional"),
    }
    return data


def validate_report(report: EvalReport) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report_to_dict(report))


def report_markdown(report: EvalReport) -> str:
    lines = [
        f"# Template Extraction Eval: {report.case_id}",
        "",
        f"- Verdict: `{report.status.value}`",
        f"- Score: `{report.total_score:.4f}/100`",
        f"- Provisional: `{'yes' if report.provisional else 'no'}`",
        f"- Analysis coverage: `{report.analysis_coverage:.2%}`",
        f"- Responsibility coverage: `{report.responsibility_coverage:.2%}`",
        f"- Run ID: `{report.run_id}`",
        "",
        "## Dimension scores",
        "",
        "| Dimension | Score | Weight | PASS | FAIL | UNKNOWN | N/A |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for offset, view in enumerate(report.views):
        lines.insert(
            8 + offset,
            f"- {view.view.value.capitalize()} view: `{view.score:.4f}/{view.weight:.4f}`",
        )
    for item in report.dimensions:
        lines.append(
            f"| {item.dimension} | {item.score:.4f} | {item.weight:.4f} | "
            f"{item.passed} | {item.failed} | {item.unknown} | {item.not_applicable} |"
        )
    lines.extend(["", "## Issues", ""])
    if not report.issues:
        lines.append("No FAIL or UNKNOWN assertions.")
    else:
        for issue in report.issues:
            target = issue.region_id or issue.slot_id or "shared"
            lines.append(
                f"- `{issue.issue_id}` `{issue.status.value}` `{issue.dimension}` "
                f"`{target}` — {issue.message}"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_report(report: EvalReport, output_dir: Path) -> tuple[Path, Path]:
    validate_report(report)
    json_path = output_dir / "template-extraction-eval-report.json"
    markdown_path = output_dir / "template-extraction-eval-report.md"
    json_content = json.dumps(
        report_to_dict(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    _atomic_write(json_path, json_content + "\n")
    _atomic_write(markdown_path, report_markdown(report))
    return json_path, markdown_path


__all__ = [
    "build_report",
    "issues_from_assertions",
    "report_markdown",
    "report_to_dict",
    "validate_report",
    "write_report",
]
