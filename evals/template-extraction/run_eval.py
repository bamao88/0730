#!/usr/bin/env python3
"""Run the independent template-extraction Actual-Gold evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from template_extraction_eval.runner import RunResult, run_evaluation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path, help="Path to case.yaml")
    parser.add_argument(
        "--actual-template",
        required=True,
        type=Path,
        help="Generated template DOCX to evaluate",
    )
    parser.add_argument(
        "--actual-contract",
        required=True,
        type=Path,
        help="Generated fill-contract YAML to evaluate",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional report directory; defaults below this Eval project",
    )
    return parser


def _summary(result: RunResult) -> dict[str, object]:
    return {
        "status": result.status,
        "run_id": result.run_id,
        "score": result.score,
        "report_json": (
            None if result.report_json is None else result.report_json.as_posix()
        ),
        "report_markdown": (
            None if result.report_markdown is None else result.report_markdown.as_posix()
        ),
        "input_error": result.input_error,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_evaluation(
        args.case,
        args.actual_template,
        args.actual_contract,
        output_dir=args.output_dir,
    )
    stream = sys.stderr if result.status == "INPUT_ERROR" else sys.stdout
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True), file=stream)
    if result.status == "PASS":
        return 0
    if result.status in {"FAIL", "UNKNOWN"}:
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
