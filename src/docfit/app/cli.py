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
    prepare_parser.add_argument(
        "--until",
        choices=("unit-boundary", "post-unit"),
        dest="until_stage",
    )
    prepare_parser.add_argument("--from", choices=("unit-boundary",), dest="from_stage")
    prepare_parser.add_argument("--resume-proof")
    prepare_parser.add_argument(
        "--force-rebuild-checkpoint",
        choices=("unit-boundary",),
        dest="force_rebuild_checkpoint",
    )

    agent_output_parser = subparsers.add_parser(
        "agent-output-contract",
        help="run the live post-unit Agent and validate only its raw output contract",
    )
    agent_output_parser.add_argument("--school-template", required=True)
    agent_output_parser.add_argument("--school-requirements")
    agent_output_parser.add_argument("--field-registry")
    agent_output_parser.add_argument("--output", required=True, dest="output_directory")
    agent_output_parser.add_argument("--resume-proof")

    extraction_parser = subparsers.add_parser(
        "extract-student-content",
        help="run the independent read-only student content extraction module",
    )
    extraction_parser.add_argument("--input", required=True, dest="input_docx")
    extraction_parser.add_argument("--field-registry", required=True)
    extraction_parser.add_argument("--output", required=True, dest="output_directory")

    student_e2e_parser = subparsers.add_parser(
        "student-content-e2e",
        help="run one inventory-backed student content extraction case",
    )
    student_e2e_parser.add_argument("--case", dest="case_id")
    student_e2e_parser.add_argument(
        "--list-cases",
        action="store_true",
        help="emit machine-readable case inventory metadata and exit",
    )
    student_e2e_parser.add_argument(
        "--validate-inputs-only",
        action="store_true",
        help="validate the selected case input package without running extraction",
    )
    student_e2e_parser.add_argument(
        "--inventory",
        default="evals/student-content-extraction/case-inventory.yaml",
        help="case inventory YAML with source, registry, and optional Gold paths",
    )
    student_e2e_parser.add_argument(
        "--output",
        dest="output_directory",
        help="directory for the extraction task output",
    )
    student_e2e_parser.add_argument(
        "--eval",
        choices=("off", "on"),
        default="off",
        dest="eval_mode",
        help="optionally run eval-student-content after extraction",
    )
    student_e2e_parser.add_argument(
        "--eval-output",
        dest="eval_output_directory",
        help="directory for evaluation reports; defaults to <output>/eval",
    )
    student_e2e_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="accepted for compatibility; student-content-e2e always emits JSON",
    )

    final_parser = subparsers.add_parser(
        "generate-final",
        help="generate the final thesis candidate from extracted student content",
    )
    final_parser.add_argument("--source", required=True, dest="source_docx")
    final_parser.add_argument("--student-content", required=True)
    final_parser.add_argument("--template", required=True, dest="template_docx")
    final_parser.add_argument("--fill-contract", required=True)
    final_parser.add_argument("--field-registry", required=True)
    final_parser.add_argument("--output", required=True, dest="output_directory")
    final_parser.add_argument("--quality-patches")

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
    eval_parser.add_argument("--suite", required=True, choices=("core", "final-generation"))
    eval_parser.add_argument("--case", dest="case_id")
    eval_parser.add_argument(
        "--student",
        action="append",
        dest="students",
        help="final-generation base package student id or alias; repeat or comma-separate",
    )
    eval_parser.add_argument(
        "--school",
        action="append",
        dest="schools",
        help="final-generation base package school id or alias; repeat or comma-separate",
    )
    eval_parser.add_argument(
        "--base-root",
        dest="base_root",
        default="temp/final-generation-base-packages-20260816",
        help="final-generation base package root for --student/--school selection",
    )
    eval_parser.add_argument("--checks")
    eval_parser.add_argument("--output", dest="output_directory")
    eval_parser.add_argument("--list-cases", action="store_true", dest="list_cases")
    eval_parser.add_argument(
        "--list-combinations",
        action="store_true",
        dest="list_combinations",
        help="list selectable final-generation student x school combinations",
    )
    eval_parser.add_argument(
        "--matrix",
        action="store_true",
        help="run all selected students x selected schools from the base package root",
    )
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


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_case_path(value: Any, *, inventory_path: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case path values must be non-empty strings.")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    repository_candidate = _repository_root() / path
    if repository_candidate.exists():
        return repository_candidate
    inventory_candidate = inventory_path.parent / path
    if inventory_candidate.exists():
        return inventory_candidate
    return repository_candidate


def _load_student_content_e2e_inventory(
    inventory_value: str,
) -> tuple[Path, list[dict[str, Any]]]:
    import yaml

    inventory_path = Path(inventory_value).expanduser()
    if not inventory_path.is_absolute():
        inventory_path = Path.cwd() / inventory_path
    try:
        inventory_path = inventory_path.resolve(strict=True)
        inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError("The student content case inventory cannot be read.") from error
    if not isinstance(inventory, dict):
        raise ValueError("The student content case inventory must be a YAML object.")
    cases = inventory.get("cases")
    if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
        raise ValueError("The student content case inventory must contain cases[].")
    return inventory_path, [dict(case) for case in cases]


def _student_content_e2e_case(
    cases: list[dict[str, Any]],
    *,
    case_id: str | None,
) -> dict[str, Any]:
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("student-content-e2e requires --case unless --list-cases is set.")
    matches = [dict(case) for case in cases if case.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError(f"Student content case is not unique or missing: {case_id}")
    return matches[0]


def _student_content_e2e_case_metadata(
    case: dict[str, Any],
    *,
    inventory_path: Path,
    require_gold: bool,
    gold_filename: str,
) -> dict[str, Any]:
    source_docx = _resolve_case_path(case.get("source"), inventory_path=inventory_path)
    field_registry = _resolve_case_path(case.get("registry"), inventory_path=inventory_path)
    raw_gold = case.get("gold")
    gold = (
        _resolve_case_path(raw_gold, inventory_path=inventory_path)
        if isinstance(raw_gold, str) and raw_gold.strip()
        else None
    )
    gold_json = gold / gold_filename if gold is not None and gold.is_dir() else gold
    source_exists = source_docx.is_file()
    registry_exists = field_registry.is_file()
    gold_json_exists = gold_json.is_file() if gold_json is not None else False
    missing = []
    if not source_exists:
        missing.append({"kind": "source", "path": str(source_docx)})
    if not registry_exists:
        missing.append({"kind": "registry", "path": str(field_registry)})
    if require_gold and not gold_json_exists:
        missing.append(
            {
                "kind": "gold",
                "path": str(gold_json) if gold_json is not None else "<missing case.gold>",
            }
        )
    return {
        "case_id": case.get("id"),
        "expected": case.get("expected"),
        "gate": case.get("gate"),
        "status": case.get("status"),
        "gold_revision": case.get("gold_revision"),
        "paths": {
            "inventory": str(inventory_path),
            "source": str(source_docx),
            "field_registry": str(field_registry),
            "gold": str(gold) if gold is not None else None,
            "gold_json": str(gold_json) if gold_json is not None else None,
        },
        "expected_sha256": {
            "source": case.get("source_sha256"),
            "gold": case.get("gold_sha256"),
        },
        "checks": {
            "source_exists": source_exists,
            "field_registry_exists": registry_exists,
            "gold_json_exists": gold_json_exists,
            "ready_for_extraction": source_exists and registry_exists,
            "ready_for_eval": source_exists and registry_exists and gold_json_exists,
        },
        "missing": missing,
    }


def _student_content_e2e_error(
    *,
    case_id: str | None,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": "docfit-student-content-e2e-cli/v1",
        "status": "INPUT_ERROR",
        "case_id": case_id,
        "failure": {"code": code, "message": message},
    }


def _student_content_e2e_main(args: argparse.Namespace) -> int:
    from docfit.app.student_content_fill import (
        StudentContentExtractionRequest,
        run_student_content_extraction,
    )
    from docfit.evals.student_content import (
        GOLD_FILENAME,
        StudentContentEvalInputError,
        run_student_content_eval,
    )

    try:
        inventory_path, cases = _load_student_content_e2e_inventory(args.inventory)
        if args.list_cases:
            payload = {
                "schema_version": "docfit-student-content-e2e-cli/v1",
                "status": "OK",
                "command": "student-content-e2e",
                "ai_contract": {
                    "stdout": "json_only",
                    "primary_product_output": "student-content.json",
                    "run_report_role": "internal_diagnostic",
                    "eval_optional": True,
                    "exit_zero_statuses": ["INPUT_PACKAGE_OK", "OK", "READY", "PASS"],
                },
                "inventory": str(inventory_path),
                "cases": [
                    _student_content_e2e_case_metadata(
                        case,
                        inventory_path=inventory_path,
                        require_gold=False,
                        gold_filename=GOLD_FILENAME,
                    )
                    for case in cases
                ],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        case = _student_content_e2e_case(cases, case_id=args.case_id)
        input_package = _student_content_e2e_case_metadata(
            case,
            inventory_path=inventory_path,
            require_gold=args.eval_mode == "on" or args.validate_inputs_only,
            gold_filename=GOLD_FILENAME,
        )
        if input_package["missing"]:
            raise ValueError(
                "The student content E2E input package is incomplete: "
                + ", ".join(value["path"] for value in input_package["missing"])
            )
        if args.validate_inputs_only:
            payload = {
                "schema_version": "docfit-student-content-e2e-cli/v1",
                "status": "INPUT_PACKAGE_OK",
                "case_id": args.case_id,
                "input_package": input_package,
                "extraction": {"status": "NOT_RUN"},
                "eval": {"mode": args.eval_mode, "status": "NOT_RUN"},
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if not isinstance(args.output_directory, str) or not args.output_directory.strip():
            raise ValueError("student-content-e2e requires --output unless validating inputs.")
    except ValueError as error:
        payload = _student_content_e2e_error(
            case_id=args.case_id,
            code="student_content_e2e_input_package_invalid",
            message=str(error),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    output_directory = Path(args.output_directory)
    source_docx = Path(input_package["paths"]["source"])
    field_registry = Path(input_package["paths"]["field_registry"])
    gold = (
        Path(input_package["paths"]["gold"]) if input_package["paths"]["gold"] is not None else None
    )
    extraction_report = asyncio.run(
        run_student_content_extraction(
            StudentContentExtractionRequest(
                source_docx=source_docx,
                field_registry=field_registry,
                output_directory=output_directory,
            )
        )
    )
    summary: dict[str, Any] = {
        "schema_version": "docfit-student-content-e2e-cli/v1",
        "case_id": args.case_id,
        "status": extraction_report.get("status"),
        "ai_contract": {
            "stdout": "json_only",
            "primary_product_output": "student-content.json",
            "run_report_role": "internal_diagnostic",
            "eval_optional": True,
        },
        "input_package": input_package,
        "extraction": {
            "status": extraction_report.get("status"),
            "student_content": extraction_report.get("student_content"),
            "run_report": str(output_directory / "run-report.json"),
        },
        "eval": {"mode": args.eval_mode},
    }
    if extraction_report.get("status") != "READY":
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    if args.eval_mode == "on":
        eval_output = (
            Path(args.eval_output_directory)
            if args.eval_output_directory
            else output_directory / "eval"
        )
        try:
            eval_result = run_student_content_eval(
                actual_directory=output_directory,
                gold=gold if gold is not None else Path(),
                output_directory=eval_output,
            )
        except StudentContentEvalInputError as error:
            summary["status"] = "INPUT_ERROR"
            summary["eval"] = {
                "mode": args.eval_mode,
                "status": "INPUT_ERROR",
                "failure": {"code": error.code, "message": error.message},
            }
            print(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 2
        summary["status"] = eval_result.report["status"]
        summary["eval"] = {
            "mode": args.eval_mode,
            "status": eval_result.report["status"],
            "gold_id": eval_result.report["gold_id"],
            "gold_revision": eval_result.report["gold_revision"],
            "blockers": eval_result.report["blockers"],
            "json_report": str(eval_result.json_report),
            "markdown_report": str(eval_result.markdown_report),
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] in {"READY", "PASS"} else 2


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
            until_stage=args.until_stage,
            from_stage=args.from_stage,
            resume_proof=Path(args.resume_proof) if args.resume_proof else None,
            force_rebuild_checkpoint=args.force_rebuild_checkpoint,
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
        return 0 if report.status in {"built", "checkpointed"} else 2
    if args.command == "agent-output-contract":
        from dataclasses import asdict

        from docfit.app.agent_output_contract import (
            AgentOutputContractRequest,
            run_agent_output_contract,
        )
        from docfit.tools.runtime import ToolFailure

        contract_request = AgentOutputContractRequest(
            school_template=Path(args.school_template),
            output_directory=Path(args.output_directory),
            school_requirements=(
                Path(args.school_requirements) if args.school_requirements else None
            ),
            field_registry=Path(args.field_registry) if args.field_registry else None,
            resume_proof=Path(args.resume_proof) if args.resume_proof else None,
        )
        try:
            contract_report = asyncio.run(run_agent_output_contract(contract_request))
        except (OSError, ToolFailure) as error:
            payload = (
                error.result()
                if isinstance(error, ToolFailure)
                else {
                    "schema_version": 1,
                    "status": "error",
                    "failure": {
                        "code": "agent_output_contract_io_failed",
                        "message": "Agent-output contract task files could not be prepared.",
                    },
                }
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        print(json.dumps(asdict(contract_report), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
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
    if args.command == "student-content-e2e":
        return _student_content_e2e_main(args)

    if args.command == "generate-final":
        from docfit.app.student_content_fill import (
            FinalGenerationRequest,
            run_final_generation,
        )

        final_report = run_final_generation(
            FinalGenerationRequest(
                source_docx=Path(args.source_docx),
                student_content=Path(args.student_content),
                template_docx=Path(args.template_docx),
                fill_contract=Path(args.fill_contract),
                field_registry=Path(args.field_registry),
                output_directory=Path(args.output_directory),
                quality_patches=Path(args.quality_patches) if args.quality_patches else None,
            )
        )
        stream = sys.stdout if final_report.get("status") == "COMPLETE" else sys.stderr
        print(
            json.dumps(final_report, ensure_ascii=False, indent=2, sort_keys=True),
            file=stream,
        )
        return 0 if final_report.get("status") == "COMPLETE" else 2

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

        if args.suite == "final-generation":
            from docfit.evals.final_generation import (
                FinalGenerationEvalInputError,
                list_final_generation_cases,
                list_final_generation_combinations,
                run_final_generation_combinations,
                run_final_generation_eval,
            )

            repository = project_root()
            if args.list_cases:
                cases = list_final_generation_cases(repository)
                if args.as_json:
                    print(
                        json.dumps(
                            {"suite": "final-generation", "cases": cases},
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                    )
                else:
                    for case in cases:
                        print(case["case_id"])
                return 0
            if args.list_combinations:
                try:
                    combinations = list_final_generation_combinations(
                        repository,
                        base_root=Path(args.base_root),
                    )
                except FinalGenerationEvalInputError as error:
                    payload = {
                        "schema_version": "docfit-final-generation-eval-error/v1",
                        "status": "INPUT_ERROR",
                        "failure": {"code": error.code, "message": error.message},
                    }
                    print(
                        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                        file=sys.stderr,
                    )
                    return 2
                if args.as_json:
                    print(
                        json.dumps(
                            {
                                "suite": "final-generation",
                                "base_root": args.base_root,
                                "combinations": combinations,
                            },
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                    )
                else:
                    for item in combinations:
                        quality = "quality" if item.get("quality_gold") else "no-quality"
                        print(f"{item['student_id']} x {item['school_id']} ({quality})")
                return 0
            combination_requested = bool(args.matrix or args.students or args.schools)
            if args.case_id and combination_requested:
                payload = {
                    "schema_version": "docfit-final-generation-eval-error/v1",
                    "status": "INPUT_ERROR",
                    "failure": {
                        "code": "final_generation_eval_selector_conflict",
                        "message": (
                            "Use either --case or --student/--school/--matrix with "
                            "--suite final-generation, not both."
                        ),
                    },
                }
                print(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                    file=sys.stderr,
                )
                return 2
            if combination_requested:
                try:
                    combination_report = run_final_generation_combinations(
                        repository=repository,
                        base_root=Path(args.base_root),
                        students=args.students,
                        schools=args.schools,
                        checks=args.checks,
                        output_directory=(
                            Path(args.output_directory) if args.output_directory else None
                        ),
                    )
                except FinalGenerationEvalInputError as error:
                    payload = {
                        "schema_version": "docfit-final-generation-eval-error/v1",
                        "status": "INPUT_ERROR",
                        "failure": {"code": error.code, "message": error.message},
                    }
                    print(
                        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                        file=sys.stderr,
                    )
                    return 2
                if args.as_json:
                    print(
                        json.dumps(
                            combination_report,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                    )
                else:
                    selection = combination_report["selection"]
                    release = combination_report["release_summary"]
                    print(
                        "Final Generation Combination Eval "
                        f"{combination_report['check_status']}: "
                        f"{selection['combination_count']} run(s)"
                    )
                    print(
                        "Release cases: "
                        f"{release['release_case_count']} | "
                        f"Releasable: {release['releasable_count']}"
                    )
                    print(f"Report: {combination_report['report_path']}")
                return 0 if combination_report["check_status"] == "PASS" else 2
            if not args.case_id:
                payload = {
                    "schema_version": "docfit-final-generation-eval-error/v1",
                    "status": "INPUT_ERROR",
                    "failure": {
                        "code": "final_generation_eval_selection_required",
                        "message": (
                            "Use --case, --list-cases, --list-combinations, or "
                            "--student/--school/--matrix with --suite final-generation."
                        ),
                    },
                }
                print(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                    file=sys.stderr,
                )
                return 2
            try:
                final_generation_eval_report = run_final_generation_eval(
                    repository=repository,
                    case_id=args.case_id,
                    checks=args.checks,
                    output_directory=(
                        Path(args.output_directory) if args.output_directory else None
                    ),
                )
            except FinalGenerationEvalInputError as error:
                payload = {
                    "schema_version": "docfit-final-generation-eval-error/v1",
                    "status": "INPUT_ERROR",
                    "failure": {"code": error.code, "message": error.message},
                }
                print(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                    file=sys.stderr,
                )
                return 2
            if args.as_json:
                print(
                    json.dumps(
                        final_generation_eval_report,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(
                    "Final Generation Eval checks "
                    f"{final_generation_eval_report['check_status']}: "
                    f"{final_generation_eval_report['case_id']} "
                    f"({', '.join(final_generation_eval_report['checks_requested'])})"
                )
                print(
                    "Generate: "
                    f"{final_generation_eval_report['generate_status']} | "
                    "Quality: "
                    f"{final_generation_eval_report['quality_status']} | "
                    "Release: "
                    f"{final_generation_eval_report['release_status']}"
                )
                print(f"Report: {final_generation_eval_report['report_path']}")
            return 0 if final_generation_eval_report["check_status"] == "PASS" else 2

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
