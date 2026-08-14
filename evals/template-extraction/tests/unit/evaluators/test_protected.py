from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from template_extraction_eval.contracts import load_eval_inputs
from template_extraction_eval.evaluators.protected import evaluate_protected
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _assertions(sample: str):  # type: ignore[no-untyped-def]
    root = FIXTURES / sample
    inputs = load_eval_inputs(
        root / "case.yaml", root / "actual-template.docx", root / "actual-contract.yaml"
    )
    return evaluate_protected(
        inputs.gold_contract,
        inputs.actual_contract,
        analyze_docx(inputs.case.gold_template_path),
        analyze_docx(inputs.actual_template_path),
        inputs.eval_config,
    )


def test_pro_01_minimal_protected_region_passes() -> None:
    comparable = [
        item
        for item in _assertions("S00-minimal-pass")
        if item.status is not AssertionStatus.NOT_APPLICABLE
    ]
    assert comparable
    assert all(item.status is AssertionStatus.PASS for item in comparable)


@pytest.mark.parametrize(
    ("sample", "failed_dimension"),
    [
        ("S01-protected-text-changed", "protected.content"),
        ("S02-protected-style-changed", "protected.style"),
        ("S09-protected-image-missing", "protected.object"),
    ],
    ids=["content", "style", "object"],
)
def test_pro_02_through_04_single_mutation_has_single_attribution(
    sample: str,
    failed_dimension: str,
) -> None:
    failed = [item for item in _assertions(sample) if item.status is AssertionStatus.FAIL]
    assert [item.dimension for item in failed] == [failed_dimension]


def test_pro_05_unsupported_visible_object_is_unknown() -> None:
    unknown = [
        item
        for item in _assertions("S10-unsupported-object")
        if item.status is AssertionStatus.UNKNOWN
    ]
    assert len(unknown) == 1
    assert unknown[0].dimension == "protected.object"


def test_pro_06_actual_contract_may_omit_protected_metadata() -> None:
    root = FIXTURES / "S00-minimal-pass"
    inputs = load_eval_inputs(
        root / "case.yaml", root / "actual-template.docx", root / "actual-contract.yaml"
    )
    assertions = evaluate_protected(
        inputs.gold_contract,
        replace(inputs.actual_contract, regions=()),
        analyze_docx(inputs.case.gold_template_path),
        analyze_docx(inputs.actual_template_path),
        inputs.eval_config,
    )
    comparable = [item for item in assertions if item.status is not AssertionStatus.NOT_APPLICABLE]
    assert comparable
    assert all(item.status is AssertionStatus.PASS for item in comparable)


def test_pro_07_actual_contract_text_cannot_make_a_changed_document_pass() -> None:
    failed = [
        item
        for item in _assertions("S01-protected-text-changed")
        if item.status is AssertionStatus.FAIL
    ]
    assert [item.dimension for item in failed] == ["protected.content"]


def test_pro_08_gold_truth_drives_actual_content_evidence() -> None:
    assertions = _assertions("S00-minimal-pass")
    content = next(item for item in assertions if item.dimension == "protected.content")
    assert content.expected == "姓名："
    assert content.actual == "姓名："
