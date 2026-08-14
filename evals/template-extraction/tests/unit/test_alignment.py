from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from template_extraction_eval.alignment import (
    AlignmentStatus,
    align_region,
    align_slot,
)
from template_extraction_eval.contracts import load_eval_inputs
from template_extraction_eval.facts import analyze_docx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"


def _sample(name: str):  # type: ignore[no-untyped-def]
    root = FIXTURES / name
    inputs = load_eval_inputs(
        root / "case.yaml",
        root / "actual-template.docx",
        root / "actual-contract.yaml",
    )
    return inputs, analyze_docx(inputs.case.gold_template_path), analyze_docx(
        inputs.actual_template_path
    )


def test_ali_01_region_and_slot_ids_match_exactly() -> None:
    inputs, gold_facts, actual_facts = _sample("S00-minimal-pass")
    region = align_region(
        inputs.gold_contract.regions[0],
        inputs.actual_contract,
        gold_facts,
        actual_facts,
    )
    slot = align_slot(
        inputs.gold_contract.slots[0],
        inputs.actual_contract,
        gold_facts,
        actual_facts,
    )
    assert region.status is AlignmentStatus.MATCHED
    assert slot.status is AlignmentStatus.MATCHED


def test_ali_02_unique_locator_fallback_matches_changed_contract_ids() -> None:
    inputs, gold_facts, actual_facts = _sample("S00-minimal-pass")
    actual = replace(
        inputs.actual_contract,
        regions=(
            replace(inputs.actual_contract.regions[0], region_id="protected.changed_id"),
        ),
        slots=(replace(inputs.actual_contract.slots[0], slot_id="slot.changed_id"),),
    )
    region = align_region(
        inputs.gold_contract.regions[0], actual, gold_facts, actual_facts
    )
    slot = align_slot(inputs.gold_contract.slots[0], actual, gold_facts, actual_facts)
    assert region.status is AlignmentStatus.MATCHED
    assert region.detail == "matched by unique structural fallback locator"
    assert slot.status is AlignmentStatus.MATCHED


def test_ali_03_duplicate_anchor_is_ambiguous_not_first_match() -> None:
    inputs, gold_facts, actual_facts = _sample("S07-ambiguous-anchor")
    alignment = align_region(
        inputs.gold_contract.regions[0],
        inputs.actual_contract,
        gold_facts,
        actual_facts,
    )
    assert alignment.status is AlignmentStatus.AMBIGUOUS
    assert alignment.gold_paragraph is None


def test_ali_04_missing_slot_has_no_synthetic_control() -> None:
    inputs, gold_facts, actual_facts = _sample("S03-slot-missing")
    alignment = align_slot(
        inputs.gold_contract.slots[0],
        inputs.actual_contract,
        gold_facts,
        actual_facts,
    )
    assert alignment.status is AlignmentStatus.MISSING
    assert alignment.actual_control is None
