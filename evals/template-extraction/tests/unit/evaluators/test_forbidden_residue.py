from __future__ import annotations

from pathlib import Path

from template_extraction_eval.contracts import load_eval_inputs
from template_extraction_eval.evaluators.forbidden_residue import (
    evaluate_forbidden_residue,
)
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _sample(name: str):  # type: ignore[no-untyped-def]
    root = FIXTURES / name
    inputs = load_eval_inputs(
        root / "case.yaml", root / "actual-template.docx", root / "actual-contract.yaml"
    )
    return inputs, analyze_docx(inputs.actual_template_path)


def test_rem_01_no_remove_declaration_produces_no_assertion() -> None:
    inputs, facts = _sample("S00-minimal-pass")
    assert evaluate_forbidden_residue(inputs.gold_contract, facts) == ()


def test_rem_02_declared_forbidden_text_remaining_fails() -> None:
    inputs, facts = _sample("S08-forbidden-residue")
    assertions = evaluate_forbidden_residue(inputs.gold_contract, facts)
    assert len(assertions) == 1
    assert assertions[0].status is AssertionStatus.FAIL
    assert assertions[0].failure_code == "forbidden_residue_present"


def test_rem_03_ordinary_text_is_never_inferred_as_removable() -> None:
    s00_inputs, _ = _sample("S00-minimal-pass")
    _, facts_with_instruction = _sample("S08-forbidden-residue")
    assert evaluate_forbidden_residue(s00_inputs.gold_contract, facts_with_instruction) == ()
