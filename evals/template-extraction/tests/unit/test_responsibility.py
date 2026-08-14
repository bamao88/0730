from __future__ import annotations

from pathlib import Path

from template_extraction_eval.contracts import load_eval_config, load_fill_contract
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus, Owner, ResponsibilityInventory
from template_extraction_eval.responsibility import (
    build_responsibility_inventory,
    evaluate_exhaustive_protected,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"


def _inventories(sample: str) -> tuple[ResponsibilityInventory, ResponsibilityInventory]:
    root = FIXTURES / sample
    gold = build_responsibility_inventory(
        analyze_docx(root / "gold-template.docx"),
        load_fill_contract(root / "gold-contract.yaml"),
    )
    actual = build_responsibility_inventory(
        analyze_docx(root / "actual-template.docx"),
        load_fill_contract(root / "actual-contract.yaml"),
    )
    return gold, actual


def test_rsp_01_exact_document_classifies_and_compares_every_fact() -> None:
    gold, actual = _inventories("S00-minimal-pass")
    config = load_eval_config(FIXTURES / "eval-config.yaml")

    assert gold.coverage == 1
    assert gold.unclassified == 0
    assert gold.protected > 3
    assert gold.slot > 0
    assertions = evaluate_exhaustive_protected(gold, actual, config)
    assert assertions
    assert {item.status for item in assertions} == {AssertionStatus.PASS}


def test_rsp_02_changed_label_fails_inside_full_protected_complement() -> None:
    gold, actual = _inventories("S01-protected-text-changed")
    config = load_eval_config(FIXTURES / "eval-config.yaml")

    assertions = evaluate_exhaustive_protected(gold, actual, config)
    failures = [item for item in assertions if item.status is AssertionStatus.FAIL]
    assert failures
    assert any(item.dimension == "protected.content" for item in failures)


def test_rsp_03_unsupported_object_is_classified_but_not_falsely_passed() -> None:
    gold, actual = _inventories("S10-unsupported-object")
    config = load_eval_config(FIXTURES / "eval-config.yaml")

    unsupported = [
        atom
        for atom in gold.atoms
        if atom.owner is Owner.PROTECTED and not atom.analyzable
    ]
    assert unsupported
    assertions = evaluate_exhaustive_protected(gold, actual, config)
    assert any(item.status is AssertionStatus.UNKNOWN for item in assertions)
