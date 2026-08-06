from __future__ import annotations

from template_extraction_eval.evaluators import (
    evaluate_forbidden_residue,
    evaluate_protected,
    evaluate_slots,
)


def test_evapi_01_exports_protected_evaluator() -> None:
    assert callable(evaluate_protected)


def test_evapi_02_exports_slot_evaluator() -> None:
    assert callable(evaluate_slots)


def test_evapi_03_exports_forbidden_residue_evaluator() -> None:
    assert callable(evaluate_forbidden_residue)
