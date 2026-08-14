from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / ".runs" / "source-clean-audit-v2"
CASES = (
    (
        "01-hunau-undergraduate",
        "hunau-undergraduate__source-template.docx",
    ),
    (
        "02-njau-undergraduate",
        "njau-undergraduate__source-template.docx",
    ),
    (
        "03-pku-graduate",
        "pku-graduate__source-template.docx",
    ),
)


def _source_root() -> Path:
    return REPO_ROOT / "temp/manual-gold-preparation/gold/00-inputs/schools"


def _markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Original source → clean Gold audit",
        "",
        (
            "> Diagnostic only. The original DOCX is Actual; the clean template and "
            "fill contract are Gold."
        ),
        "",
        (
            "| Case | Verdict | Gold coverage | Aligned paragraphs | Missing Gold paragraphs | "
            "Protected FAIL | Protected UNKNOWN | Slot FAIL | Score |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        result = item["result"]
        protected = result["protected"]
        slot = result["slot"]
        audit = protected["audit"]
        lines.append(
            f"| {item['case_id']} | {result['verdict']} | "
            f"{result['responsibility_coverage']:.2%} | "
            f"{audit['matched_paragraphs']} | {audit['missing_gold_paragraphs']} | "
            f"{protected['counts']['FAIL']} | {protected['counts']['UNKNOWN']} | "
            f"{slot['counts']['FAIL']} | {result['score']} |"
        )
    lines.extend(["", "## Warnings", ""])
    for item in results:
        for warning in item["warnings"]:
            lines.append(f"- `{item['case_id']}` — {warning}")
    lines.extend(["", "## Failed/unknown protected cases", ""])
    for item in results:
        lines.append(f"### {item['case_id']}")
        lines.append("")
        issues = item["result"]["protected"]["issues"]
        if not issues:
            lines.append("- None")
        for issue in issues:
            lines.append(
                f"- `{issue['assertion_id']}` `{issue['status']}` "
                f"`{issue['dimension']}` — {issue['message']}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = [
        run_raw_source_sentinel(
            PROJECT_ROOT / "cases" / case_id / "case.yaml",
            _source_root() / source_name,
        )
        for case_id, source_name in CASES
    ]
    (output / "sentinel-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "sentinel-results.md").write_text(_markdown(results), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
