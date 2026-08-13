from __future__ import annotations

from pathlib import Path

import pytest

from template_extraction_eval.contracts import load_fill_contract
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.markers import marker_expectations, validate_markers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES = PROJECT_ROOT / "cases"


@pytest.mark.parametrize(
    ("case_id", "expected_tags"),
    [
        ("01-hunau-undergraduate", 31),
        ("02-njau-undergraduate", 26),
        ("03-pku-graduate", 0),
    ],
)
def test_marker_01_through_03_school_marker_protocol_is_closed(
    case_id: str,
    expected_tags: int,
) -> None:
    root = CASES / case_id / "gold"
    contract_path = root / "fill-contract.yaml"
    contract = load_fill_contract(contract_path)
    expectations = marker_expectations(contract, path=contract_path)
    assert len(expectations) == expected_tags
    validate_markers(
        contract,
        analyze_docx(root / "template.docx"),
        label="Gold",
        path=contract_path,
    )


def test_marker_04_njau_body_region_anchor_is_a_managed_marker() -> None:
    contract = load_fill_contract(
        CASES / "02-njau-undergraduate" / "gold" / "fill-contract.yaml"
    )
    assert "body.chapters.1" in marker_expectations(contract)


def test_marker_05_pku_placeholder_contract_does_not_invent_word_markers() -> None:
    contract = load_fill_contract(
        CASES / "03-pku-graduate" / "gold" / "fill-contract.yaml"
    )
    assert {slot.locator.type for slot in contract.slots} == {"placeholder_anchor"}
    assert marker_expectations(contract) == {}


def test_marker_06_untagged_word_controls_are_not_product_markers() -> None:
    root = CASES / "03-pku-graduate" / "gold"
    contract = load_fill_contract(root / "fill-contract.yaml")
    facts = analyze_docx(root / "template.docx")
    assert any(control.tag is None for control in facts.controls)
    validate_markers(
        contract,
        facts,
        label="Gold",
        path=root / "fill-contract.yaml",
    )
