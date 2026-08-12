"""DocFit command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docfit")
    parser.add_argument("--version", action="version", version="docfit 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="check the local DocFit environment")
    doctor_parser.add_argument(
        "--require",
        choices=("agent-smoke", "visual-renderer"),
        dest="requirement",
    )
    doctor_parser.add_argument("--json", action="store_true", dest="as_json")

    smoke_parser = subparsers.add_parser(
        "agent-smoke",
        help="run one live Claude Agent SDK smoke case",
    )
    smoke_parser.add_argument(
        "--case",
        required=True,
        choices=("image", "ask-user", "denied-tools", "path-tools", "subagent"),
        dest="case_name",
    )

    tools_parser = subparsers.add_parser(
        "tools",
        help="run one deterministic DocFit Tool without an Agent",
    )
    tools_parser.add_argument("--task-root", default=".")
    tool_subparsers = tools_parser.add_subparsers(dest="tool_command", required=True)

    inspect_parser = tool_subparsers.add_parser("inspect")
    inspect_parser.add_argument("input_docx")
    inspect_parser.add_argument("--focus", action="append", default=[])
    inspect_parser.add_argument("--output")

    edit_parser = tool_subparsers.add_parser("edit")
    edit_parser.add_argument("input_docx")
    edit_parser.add_argument("--plan", required=True)
    edit_parser.add_argument("--output")
    edit_parser.add_argument("--overwrite", action="store_true")

    render_parser = tool_subparsers.add_parser("render")
    render_parser.add_argument("input_docx")
    render_parser.add_argument("--no-overview", action="store_true")

    visual_parser = tool_subparsers.add_parser("visual-review")
    visual_parser.add_argument("render_ref")
    visual_parser.add_argument(
        "--mode",
        choices=("contact_sheet", "pages", "regions", "compare"),
        default="pages",
    )
    visual_parser.add_argument(
        "--quality", choices=("thumbnail", "review", "detail"), default="review"
    )
    visual_parser.add_argument("--pages")
    visual_parser.add_argument("--regions")
    visual_parser.add_argument("--compare-ref")
    visual_parser.add_argument("--cursor")

    validate_parser = tool_subparsers.add_parser("validate")
    validate_parser.add_argument("source_docx")
    validate_parser.add_argument("final_docx")
    validate_parser.add_argument("--source-sha256")
    validate_parser.add_argument("--visual-review")
    validate_parser.add_argument("--candidate-ref")

    convert_parser = subparsers.add_parser(
        "convert",
        help="run one complete DocFit Agent conversion",
    )
    convert_parser.add_argument("--input", required=True, dest="input_docx")
    convert_parser.add_argument("--school-template", required=True)
    convert_parser.add_argument("--school-requirements", required=True)
    convert_parser.add_argument("--output", required=True, dest="output_directory")
    convert_parser.add_argument(
        "--observation",
        choices=("auto", "off"),
        default="auto",
        help=(
            "local metadata-only observation (default: auto; use off for the no-observer baseline)"
        ),
    )

    prepare_parser = subparsers.add_parser(
        "prepare-template",
        help="run one development-stage school template preparation Agent",
    )
    prepare_parser.add_argument("--school-template", required=True)
    prepare_parser.add_argument("--school-requirements")
    prepare_parser.add_argument("--field-registry")
    prepare_parser.add_argument("--output", required=True, dest="output_directory")

    extraction_parser = subparsers.add_parser(
        "extract-student-content",
        help="run the independent read-only student content extraction module",
    )
    extraction_parser.add_argument("--input", required=True, dest="input_docx")
    extraction_parser.add_argument("--field-registry", required=True)
    extraction_parser.add_argument("--output", required=True, dest="output_directory")

    student_eval_parser = subparsers.add_parser(
        "eval-student-content",
        help="compare one saved student extraction with accepted Extraction Gold",
    )
    student_eval_parser.add_argument(
        "--actual",
        required=True,
        dest="actual_directory",
        help="extraction output directory containing student-content.json and work artifacts",
    )
    student_eval_parser.add_argument(
        "--gold",
        required=True,
        help="accepted student-content.gold.json or its package directory",
    )
    student_eval_parser.add_argument(
        "--output",
        required=True,
        dest="output_directory",
        help="directory for JSON and Markdown evaluation reports",
    )
    student_eval_parser.add_argument("--json", action="store_true", dest="as_json")

    observe_parser = subparsers.add_parser(
        "observe",
        help="start the local DocFit observation website",
    )
    observe_parser.add_argument("--port", type=_port_number, default=0)

    eval_parser = subparsers.add_parser(
        "eval",
        help="run a bounded offline DocFit evaluation suite",
    )
    eval_parser.add_argument("--suite", required=True, choices=("core",))
    eval_parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _load_json_object(path_value: str, *, task_root: Path) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    path = path if path.is_absolute() else task_root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("The requested JSON file cannot be read.") from error
    if not isinstance(value, dict):
        raise ValueError("The requested JSON file must contain one object.")
    return value


def _comma_ints(value: str | None) -> list[int]:
    if value is None or not value.strip():
        return []
    try:
        return [int(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise ValueError("Page lists must be comma-separated integers.") from error


def _tools_main(args: argparse.Namespace) -> int:
    from docfit.tools.runtime import ToolFailure
    from docfit.tools.service import DocFitToolService

    task_root = Path(args.task_root).expanduser().resolve()
    service = DocFitToolService(task_root=task_root)
    payload: dict[str, Any] = {"task_root": str(task_root)}
    try:
        if args.tool_command == "inspect":
            payload.update(
                {
                    "input_docx": args.input_docx,
                    "focus": args.focus,
                }
            )
            if args.output:
                payload["output"] = args.output
            result = service.inspect(payload)
        elif args.tool_command == "edit":
            plan = _load_json_object(args.plan, task_root=task_root)
            operations = plan.get("operations")
            output_docx = args.output or plan.get("output_docx")
            payload.update(
                {
                    "input_docx": args.input_docx,
                    "output_docx": output_docx,
                    "operations": operations,
                    "overwrite": args.overwrite or plan.get("overwrite", False),
                }
            )
            result = service.edit(payload)
        elif args.tool_command == "render":
            result, images = service.render(
                {"input_docx": args.input_docx, "overview": not args.no_overview}
            )
            result["image_paths"] = [str(path) for path in images]
        elif args.tool_command == "visual-review":
            visual_payload: dict[str, Any] = {
                "render_ref": args.render_ref,
                "mode": args.mode,
                "quality": args.quality,
            }
            if args.pages:
                visual_payload["pages"] = _comma_ints(args.pages)
            if args.regions:
                region_payload = _load_json_object(args.regions, task_root=task_root)
                visual_payload["regions"] = region_payload.get("regions")
            if args.compare_ref:
                visual_payload["compare_render_ref"] = args.compare_ref
            if args.cursor:
                visual_payload["cursor"] = args.cursor
            result, images = service.visual_review(visual_payload)
            result["image_paths"] = [str(path) for path in images]
        elif args.tool_command == "validate":
            payload.update(
                {
                    "source_docx": args.source_docx,
                    "final_docx": args.final_docx,
                    "required_visual_coverage": "all_final_pages",
                }
            )
            if args.source_sha256:
                payload["source_sha256"] = args.source_sha256
            if args.visual_review:
                payload["visual_review"] = args.visual_review
            if args.candidate_ref:
                payload["candidate_render_ref"] = args.candidate_ref
            result = service.validate(payload)
        else:
            raise AssertionError(f"unhandled Tool command: {args.tool_command}")
    except (ToolFailure, ValueError) as error:
        if isinstance(error, ToolFailure):
            result = error.result(committed=False if args.tool_command == "edit" else None)
        else:
            result = {
                "schema_version": 1,
                "status": "needs_input",
                "checks": [],
                "warnings": [],
                "failure": {
                    "origin": "request",
                    "code": "invalid_cli_json",
                    "retryable": False,
                    "message": str(error),
                    "suggested_actions": [],
                },
            }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        from docfit.app.doctor import doctor_main

        return doctor_main(requirement=args.requirement, as_json=args.as_json)
    if args.command == "agent-smoke":
        from docfit.app.smoke import smoke_main

        return smoke_main(args.case_name)
    if args.command == "tools":
        return _tools_main(args)
    if args.command == "observe":
        from docfit.observability.web import run_observer_server

        return run_observer_server(port=args.port)
    if args.command == "convert":
        from dataclasses import asdict

        from docfit.app.agent import project_root
        from docfit.app.convert import ConversionRequest, run_conversion
        from docfit.observability.runtime import create_observation_recorder
        from docfit.tools.runtime import ToolFailure

        request = ConversionRequest(
            input_docx=Path(args.input_docx),
            school_template=Path(args.school_template),
            school_requirements=Path(args.school_requirements),
            output_directory=Path(args.output_directory),
        )
        observation = create_observation_recorder(
            args.observation,
            task_root=Path(args.output_directory),
            repository_root=project_root(),
        )
        try:
            conversion_report = asyncio.run(run_conversion(request, observation=observation))
        except ToolFailure as error:
            print(json.dumps(error.result(), ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        print(json.dumps(asdict(conversion_report), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if conversion_report.status == "COMPLETED" else 2
    if args.command == "prepare-template":
        from dataclasses import asdict

        from docfit.app.prepare_template import PrepareTemplateRequest, run_prepare_template
        from docfit.tools.runtime import ToolFailure

        prepare_request = PrepareTemplateRequest(
            school_template=Path(args.school_template),
            output_directory=Path(args.output_directory),
            school_requirements=(
                Path(args.school_requirements) if args.school_requirements else None
            ),
            field_registry=Path(args.field_registry) if args.field_registry else None,
        )
        try:
            report = asyncio.run(run_prepare_template(prepare_request))
        except (OSError, ToolFailure) as error:
            payload = (
                error.result()
                if isinstance(error, ToolFailure)
                else {
                    "schema_version": 1,
                    "status": "error",
                    "failure": {
                        "code": "prepare_template_io_failed",
                        "message": "Template task files could not be prepared.",
                    },
                }
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report.status == "built" else 2
    if args.command == "extract-student-content":
        from docfit.app.student_content_fill import (
            StudentContentExtractionRequest,
            run_student_content_extraction,
        )

        extraction_report = asyncio.run(
            run_student_content_extraction(
                StudentContentExtractionRequest(
                    source_docx=Path(args.input_docx),
                    field_registry=Path(args.field_registry),
                    output_directory=Path(args.output_directory),
                )
            )
        )
        stream = sys.stdout if extraction_report.get("status") == "READY" else sys.stderr
        print(
            json.dumps(extraction_report, ensure_ascii=False, indent=2, sort_keys=True),
            file=stream,
        )
        return 0 if extraction_report.get("status") == "READY" else 2
    if args.command == "eval-student-content":
        from docfit.evals.student_content import (
            StudentContentEvalInputError,
            run_student_content_eval,
        )

        try:
            eval_result = run_student_content_eval(
                actual_directory=Path(args.actual_directory),
                gold=Path(args.gold),
                output_directory=Path(args.output_directory),
            )
        except StudentContentEvalInputError as error:
            payload = {
                "schema_version": "docfit-student-content-extraction-eval-cli/v1",
                "status": "INPUT_ERROR",
                "failure": {"code": error.code, "message": error.message},
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        summary = {
            "schema_version": "docfit-student-content-extraction-eval-cli/v1",
            "status": eval_result.report["status"],
            "gold_id": eval_result.report["gold_id"],
            "gold_revision": eval_result.report["gold_revision"],
            "blockers": eval_result.report["blockers"],
            "json_report": str(eval_result.json_report),
            "markdown_report": str(eval_result.markdown_report),
        }
        if args.as_json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                "Student Content Extraction Eval "
                f"{summary['status']}: {summary['gold_id']} @ {summary['gold_revision']}"
            )
            print(f"JSON report: {summary['json_report']}")
            print(f"Markdown report: {summary['markdown_report']}")
            if summary["blockers"]:
                print(f"Blockers: {', '.join(summary['blockers'])}")
        return 0 if eval_result.passed else 2
    if args.command == "eval":
        from dataclasses import asdict

        from docfit.app.agent import project_root
        from docfit.evals.runner import run_core_eval

        eval_report = run_core_eval(project_root())
        payload = asdict(eval_report)
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            metrics = eval_report.metrics
            print(
                "Core Eval "
                f"{eval_report.deterministic_status}: "
                f"{metrics['passed']}/{metrics['case_count']} cases, "
                f"{metrics['assertions']} assertions, "
                f"{metrics['rendered_pages']} rendered pages"
            )
            print(f"Report: {eval_report.report_path}")
            print("Live SDK/LibreOffice/real-sample and manual review gates remain separate.")
        return 0 if eval_report.passed else 2
    raise AssertionError(f"unhandled command: {args.command}")
