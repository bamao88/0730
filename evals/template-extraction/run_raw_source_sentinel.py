from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from template_extraction_eval.sentinel import run_raw_source_sentinel

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / ".runs" / "raw-source-sentinel-v3"
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
        "# Raw source as Actual — sentinel result",
        "",
        "> Diagnostic only; candidate Gold is never promoted or accepted by this command.",
        "",
        (
            "| Case | Protected | Protected score | Protected atoms | Slot | "
            "Slot score | Total | Responsibility | Analysis | Verdict |"
        ),
        "|---|---|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for item in results:
        result = item["result"]
        protected = result["protected"]
        slot = result["slot"]
        protected_atoms = protected["responsibility_inventory"]["protected_atoms"]
        lines.append(
            f"| {item['case_id']} | {protected['status']} | "
            f"{protected['score']}/{protected['weight']} | {protected_atoms} | "
            f"{slot['status']} | "
            f"{slot['score']}/{slot['weight']} | {result['score']} | "
            f"{result['responsibility_coverage']:.0%} | "
            f"{result['analysis_coverage']:.0%} | {result['verdict']} |"
        )
    lines.extend(["", "## Warnings", ""])
    for item in results:
        for warning in item["warnings"]:
            lines.append(f"- `{item['case_id']}` — {warning}")
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
