from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from template_extraction_eval.contracts import load_eval_inputs
from template_extraction_eval.evaluators.slots import evaluate_slots
from template_extraction_eval.facts import analyze_docx
from template_extraction_eval.models import AssertionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "fixtures"


def _assertions(
    sample: str,
    *,
    actual_template: Path | None = None,
):  # type: ignore[no-untyped-def]
    root = FIXTURES / sample
    inputs = load_eval_inputs(
        root / "case.yaml",
        root / "actual-template.docx",
        root / "actual-contract.yaml",
    )
    return evaluate_slots(
        inputs.gold_contract,
        inputs.actual_contract,
        analyze_docx(inputs.case.gold_template_path),
        analyze_docx(
            inputs.actual_template_path if actual_template is None else actual_template
        ),
        inputs.field_registry,
        inputs.eval_config,
    )


def _patched_control_docx(
    source: Path,
    target: Path,
    *,
    showing_placeholder: bool,
    size_half_points: int = 24,
) -> Path:
    with ZipFile(source) as original, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == "word/document.xml":
                if showing_placeholder:
                    content = content.replace(
                        b'<w:id w:val="1001"/><w:text/>',
                        b'<w:id w:val="1001"/><w:showingPlcHdr/><w:text/>',
                    )
                content = content.replace(
                    '<w:r><w:t>【姓名】</w:t></w:r>'.encode(),
                    (
                        '<w:r><w:rPr><w:color w:val="7F7F7F"/>'
                        f'<w:sz w:val="{size_half_points}"/>'
                        f'<w:szCs w:val="{size_half_points}"/>'
                        '</w:rPr><w:t>【姓名】</w:t></w:r>'
                    ).encode(),
                )
            output.writestr(info, content)
    return target


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


def test_slot_08_gray_word_placeholder_does_not_change_value_style(
    tmp_path: Path,
) -> None:
    source = FIXTURES / "S00-minimal-pass" / "actual-template.docx"
    actual = _patched_control_docx(
        source,
        tmp_path / "gray-placeholder.docx",
        showing_placeholder=True,
    )
    value_style = next(
        item
        for item in _assertions("S00-minimal-pass", actual_template=actual)
        if item.dimension == "slot.value_style"
    )
    assert value_style.status is AssertionStatus.PASS


def test_slot_09_gray_filled_value_still_fails_black_value_contract(
    tmp_path: Path,
) -> None:
    source = FIXTURES / "S00-minimal-pass" / "actual-template.docx"
    actual = _patched_control_docx(
        source,
        tmp_path / "gray-filled-value.docx",
        showing_placeholder=False,
    )
    value_style = next(
        item
        for item in _assertions("S00-minimal-pass", actual_template=actual)
        if item.dimension == "slot.value_style"
    )
    assert value_style.status is AssertionStatus.FAIL


def test_slot_10_placeholder_exemption_is_limited_to_color(tmp_path: Path) -> None:
    source = FIXTURES / "S00-minimal-pass" / "actual-template.docx"
    actual = _patched_control_docx(
        source,
        tmp_path / "wrong-size-placeholder.docx",
        showing_placeholder=True,
        size_half_points=30,
    )
    value_style = next(
        item
        for item in _assertions("S00-minimal-pass", actual_template=actual)
        if item.dimension == "slot.value_style"
    )
    assert value_style.status is AssertionStatus.FAIL
