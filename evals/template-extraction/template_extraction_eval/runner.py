"""Orchestrate one independent, read-only Actual-Gold evaluation run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    InputContractError,
    InputErrorCode,
    load_eval_inputs,
    sha256_file,
)
from .evaluators import (
    evaluate_forbidden_residue,
    evaluate_protected,
    evaluate_slots,
)
from .facts import PackageValidationError, analyze_docx
from .markers import validate_markers
from .models import EvalInputs
from .reporting import build_report, write_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class RunResult:
    status: str
    run_id: str | None = None
    score: float | None = None
    report_json: Path | None = None
    report_markdown: Path | None = None
    input_error: dict[str, str | None] | None = None


def _run_id(inputs: EvalInputs) -> str:
    payload = json.dumps(
        {
            "case_id": inputs.case.case_id,
            "inputs": inputs.input_hashes,
            "scoring_version": inputs.scoring_config.scoring_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _verify_unchanged_inputs(inputs: EvalInputs) -> None:
    paths = {
        "case_manifest": inputs.case.case_path,
        "actual_template": inputs.actual_template_path,
        "actual_contract": inputs.actual_contract_path,
        "gold_template": inputs.case.gold_template_path,
        "gold_contract": inputs.case.gold_contract_path,
        "field_registry": inputs.case.registry_ref.path,
        "eval_config": inputs.case.eval_config_ref.path,
        "scoring_config": inputs.eval_config.scoring_path,
    }
    changed = [
        name
        for name, path in paths.items()
        if sha256_file(path) != inputs.input_hashes[name]
    ]
    if changed:
        raise InputContractError(
            InputErrorCode.HASH_MISMATCH,
            f"input files changed during evaluation: {', '.join(sorted(changed))}",
        )


def _input_error(error: InputContractError | PackageValidationError) -> RunResult:
    if isinstance(error, InputContractError):
        diagnostic = error.to_dict()
    else:
        diagnostic = {
            "code": InputErrorCode.DOCX_INVALID.value,
            "message": str(error),
            "path": None,
        }
    return RunResult(status="INPUT_ERROR", input_error=diagnostic)


def run_evaluation(
    case_path: Path,
    actual_template_path: Path,
    actual_contract_path: Path,
    *,
    output_dir: Path | None = None,
) -> RunResult:
    try:
        inputs = load_eval_inputs(
            case_path,
            actual_template_path,
            actual_contract_path,
        )
        gold_facts = analyze_docx(inputs.case.gold_template_path)
        actual_facts = analyze_docx(inputs.actual_template_path)
        validate_markers(
            inputs.gold_contract,
            gold_facts,
            label="Gold",
            path=inputs.case.gold_contract_path,
        )
        validate_markers(
            inputs.actual_contract,
            actual_facts,
            label="Actual",
            path=inputs.actual_contract_path,
        )
        assertions = (
            evaluate_protected(
                inputs.gold_contract,
                inputs.actual_contract,
                gold_facts,
                actual_facts,
                inputs.eval_config,
            )
            + evaluate_slots(
                inputs.gold_contract,
                inputs.actual_contract,
                gold_facts,
                actual_facts,
                inputs.field_registry,
                inputs.eval_config,
            )
            + evaluate_forbidden_residue(inputs.gold_contract, actual_facts)
        )
        _verify_unchanged_inputs(inputs)
        run_id = _run_id(inputs)
        report = build_report(
            case_id=inputs.case.case_id,
            run_id=run_id,
            assertions=assertions,
            input_hashes=inputs.input_hashes,
            report_config={
                "scoring_version": inputs.scoring_config.scoring_version,
                "scoring_config_sha256": inputs.scoring_config.sha256,
                "eval_config_id": inputs.eval_config.config_id,
                "eval_config_version": inputs.eval_config.schema_version,
                "eval_config_sha256": inputs.eval_config.sha256,
                "marker_protocol": inputs.eval_config.marker_protocol,
                "tolerances": inputs.eval_config.tolerances,
                "normalization": inputs.eval_config.normalization,
                "registry_id": inputs.field_registry.registry_id,
                "registry_version": inputs.field_registry.registry_version,
                "registry_sha256": inputs.field_registry.sha256,
                "schemas": {
                    "case": inputs.case.schema_version,
                    "actual_contract": inputs.actual_contract.schema_version,
                    "gold_contract": inputs.gold_contract.schema_version,
                },
            },
            scoring_config=inputs.scoring_config,
        )
        destination = (
            output_dir.resolve()
            if output_dir is not None
            else PROJECT_ROOT / ".runs" / run_id / inputs.case.case_id
        )
        json_path, markdown_path = write_report(report, destination)
        return RunResult(
            status=report.status.value,
            run_id=run_id,
            score=report.total_score,
            report_json=json_path,
            report_markdown=markdown_path,
        )
    except (InputContractError, PackageValidationError) as error:
        return _input_error(error)


__all__ = ["RunResult", "run_evaluation"]
