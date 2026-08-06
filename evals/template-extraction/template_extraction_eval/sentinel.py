"""Metamorphic diagnostic: treat an untouched source template as product Actual."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import (
    InputContractError,
    InputErrorCode,
    load_case,
    load_eval_config,
    load_field_registry,
    load_fill_contract,
    load_scoring_config,
    sha256_file,
)
from .evaluators import evaluate_forbidden_residue, evaluate_slots
from .facts import analyze_docx
from .markers import validate_markers
from .models import AssertionResult, AssertionStatus, FillContract, View
from .responsibility import (
    build_responsibility_inventory,
    evaluate_exhaustive_protected,
    inventory_summary,
)
from .scoring import score_assertions


def _empty_actual_contract(gold: FillContract, source_template: Path) -> FillContract:
    return FillContract(
        schema_version=gold.schema_version,
        contract_id=f"sentinel.{gold.contract_id}.zero-slot-actual",
        template_sha256=sha256_file(source_template),
        registry_id=gold.registry_id,
        registry_version=gold.registry_version,
        registry_sha256=gold.registry_sha256,
        marker_protocol=gold.marker_protocol,
        regions=(),
        slots=(),
        status="synthetic",
    )


def _view_result(
    view: View,
    assertions: tuple[AssertionResult, ...],
    *,
    score: float,
    weight: float,
    expected: str,
) -> dict[str, Any]:
    relevant = tuple(item for item in assertions if item.view is view)
    counts = {
        status.value: sum(item.status is status for item in relevant)
        for status in AssertionStatus
    }
    if not relevant:
        status = "UNVERIFIED"
    elif counts[AssertionStatus.FAIL.value]:
        status = "FAIL"
    elif counts[AssertionStatus.UNKNOWN.value]:
        status = "UNKNOWN"
    else:
        status = "PASS"
    return {
        "expected": expected,
        "status": status,
        "score": score,
        "weight": weight,
        "assertions": len(relevant),
        "counts": counts,
    }


def _assert_equal(actual: str, expected: str, message: str, *, path: Path) -> None:
    if actual != expected:
        raise InputContractError(InputErrorCode.HASH_MISMATCH, message, path=path)


def run_raw_source_sentinel(case_path: Path, source_template: Path) -> dict[str, Any]:
    """Run scoring internals without weakening the formal accepted-Gold gate.

    The result is always diagnostic-only. Candidate Gold can be inspected, but this
    function cannot publish a formal Eval PASS or alter case acceptance state.
    """

    case = load_case(case_path)
    source = source_template.expanduser().resolve()
    gold = load_fill_contract(case.gold_contract_path)
    registry = load_field_registry(case.registry_ref.path)
    eval_config = load_eval_config(case.eval_config_ref.path)
    scoring_config = load_scoring_config(eval_config.scoring_path)
    _assert_equal(
        sha256_file(case.gold_template_path),
        gold.template_sha256,
        "Gold template hash does not match its fill contract",
        path=case.gold_template_path,
    )
    _assert_equal(
        registry.sha256,
        gold.registry_sha256,
        "Gold contract Registry hash does not match the loaded Registry",
        path=case.gold_contract_path,
    )
    if gold.marker_protocol != eval_config.marker_protocol:
        raise InputContractError(
            InputErrorCode.CONTRACT_MISMATCH,
            "Gold marker protocol does not match Eval configuration",
            path=case.gold_contract_path,
        )

    actual = _empty_actual_contract(gold, source)
    gold_facts = analyze_docx(case.gold_template_path)
    actual_facts = analyze_docx(source)
    validate_markers(
        gold,
        gold_facts,
        label="Gold",
        path=case.gold_contract_path,
    )
    validate_markers(actual, actual_facts, label="Actual", path=source)
    source_inventory = build_responsibility_inventory(actual_facts, actual)
    gold_inventory = build_responsibility_inventory(gold_facts, gold)
    assertions = (
        evaluate_exhaustive_protected(
            source_inventory,
            source_inventory,
            eval_config,
        )
        + evaluate_slots(
            gold,
            actual,
            gold_facts,
            actual_facts,
            registry,
            eval_config,
        )
        + evaluate_forbidden_residue(gold, actual_facts)
    )
    scoring = score_assertions(assertions, scoring_config)
    view_scores = {item.view: item for item in scoring.views}
    warnings: list[str] = []
    protected_result = _view_result(
        View.PROTECTED,
        assertions,
        score=view_scores[View.PROTECTED].score,
        weight=view_scores[View.PROTECTED].weight,
        expected="PASS",
    )
    protected_result["issues"] = [
        {
            "assertion_id": item.assertion_id,
            "dimension": item.dimension,
            "status": item.status.value,
            "message": item.message,
        }
        for item in assertions
        if item.view is View.PROTECTED
        and item.status in {AssertionStatus.FAIL, AssertionStatus.UNKNOWN}
    ]
    protected_result["scope"] = "exhaustive"
    protected_result["responsibility_inventory"] = inventory_summary(source_inventory)
    slot_result = _view_result(
        View.SLOT,
        assertions,
        score=view_scores[View.SLOT].score,
        weight=view_scores[View.SLOT].weight,
        expected="FAIL",
    )
    if protected_result["status"] != protected_result["expected"]:
        warnings.append(
            "protected sentinel outcome differs from expectation; see protected.issues"
        )
    if slot_result["status"] != slot_result["expected"]:
        warnings.append("slot sentinel outcome differs from expectation")
    payload = {
        "schema_version": "docfit-template-extraction-raw-source-sentinel/v1",
        "diagnostic_only": True,
        "case_id": case.case_id,
        "gold_status": {
            "case_status": case.case_status,
            "gold_review_status": case.gold_review_status,
            "contract_status": gold.status,
        },
        "inputs": {
            "source_template": source.as_posix(),
            "source_template_sha256": sha256_file(source),
            "gold_template_sha256": sha256_file(case.gold_template_path),
            "gold_contract_sha256": sha256_file(case.gold_contract_path),
        },
        "result": {
            "verdict": scoring.verdict.value,
            "score": scoring.total_score,
            "analysis_coverage": scoring.analysis_coverage,
            "responsibility_coverage": source_inventory.coverage,
            "protected": protected_result,
            "slot": slot_result,
        },
        "inventories": {
            "source_protected_baseline": inventory_summary(source_inventory),
            "gold_extracted_template": inventory_summary(gold_inventory),
        },
        "warnings": warnings,
    }
    payload["run_id"] = hashlib.sha256(
        json.dumps(payload["inputs"], sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return payload


__all__ = ["run_raw_source_sentinel"]
