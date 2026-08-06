from __future__ import annotations

from pathlib import Path

import pytest

from template_extraction_eval.contracts import load_eval_inputs
from template_extraction_eval.evaluators.slots import evaluate_slots
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _assertions(sample: str):  # type: ignore[no-untyped-def]
    root = FIXTURES / sample
    inputs = load_eval_inputs(
        root / "case.yaml", root / "actual-template.docx", root / "actual-contract.yaml"
    )
    return evaluate_slots(
        inputs.gold_contract,
        inputs.actual_contract,
        analyze_docx(inputs.case.gold_template_path),
        analyze_docx(inputs.actual_template_path),
        inputs.field_registry,
        inputs.eval_config,
    )


def test_slot_01_minimal_slot_passes_all_comparable_assertions() -> None:
    comparable = [
        item
        for item in _assertions("S00-minimal-pass")
        if item.status is not AssertionStatus.NOT_APPLICABLE
    ]
    assert comparable
    assert all(item.status is AssertionStatus.PASS for item in comparable)


@pytest.mark.parametrize(
    ("sample", "dimension", "failure_code"),
    [
        ("S03-slot-missing", "slot.inventory", "required_slot_missing"),
        ("S04-slot-extra", "slot.inventory", "extra_slot"),
        ("S05-slot-field-wrong", "slot.field_mapping", "slot_field_mapping_invalid"),
        ("S06-slot-boundary-wrong", "slot.location_boundary", "slot_overlaps_protected"),
    ],
    ids=["missing", "extra", "field", "boundary"],
)
def test_slot_02_through_05_mutations_have_precise_failure(
    sample: str,
    dimension: str,
    failure_code: str,
) -> None:
    failed = [item for item in _assertions(sample) if item.status is AssertionStatus.FAIL]
    if sample == "S03-slot-missing":
        assert {item.dimension for item in failed} == {
            "slot.inventory",
            "slot.location_boundary",
            "slot.field_mapping",
            "slot.value_style",
        }
        inventory = next(item for item in failed if item.dimension == "slot.inventory")
        assert inventory.failure_code == failure_code
    else:
        assert len(failed) == 1
        assert (failed[0].dimension, failed[0].failure_code) == (dimension, failure_code)


def test_slot_06_protected_text_change_does_not_become_boundary_failure() -> None:
    failed = [
        item
        for item in _assertions("S01-protected-text-changed")
        if item.status is AssertionStatus.FAIL
    ]
    assert failed == []


@pytest.mark.parametrize(
    "dimension",
    ["slot.location_boundary", "slot.field_mapping", "slot.value_style"],
)
def test_slot_07_missing_required_slot_blocks_each_downstream_dimension(
    dimension: str,
) -> None:
    assertion = next(
        item
        for item in _assertions("S03-slot-missing")
        if item.dimension == dimension
    )
    assert assertion.status is AssertionStatus.FAIL
    assert assertion.required is True
    assert assertion.failure_code == "required_slot_prerequisite_missing"
