"""Evaluate slot inventory, physical placement, field mapping, and value-style contract."""

from __future__ import annotations

from typing import Any

from ..alignment import AlignmentStatus, align_slot
from ..facts.effective_style import style_differences
from ..markers import managed_marker_tags
from ..models import (
    AssertionResult,
    AssertionStatus,
    ContentControlFact,
    DocumentFacts,
    EffectiveStyle,
    EvalConfig,
    FieldRegistry,
    FillContract,
    SlotContract,
    View,
)


def _marker_style_differences(
    expected: EffectiveStyle,
    control: ContentControlFact,
    tolerances: dict[str, float],
) -> tuple[tuple[str, Any, Any], ...]:
    """Ignore only the display color of a Word placeholder.

    ``w:showingPlcHdr`` marks the current control content as placeholder UI,
    not as a filled value. Its gray font color is allowed to differ from the
    value-style contract; all other effective style properties still apply.
    """

    if not control.showing_placeholder or "color" not in expected.font:
        return style_differences(expected, control.effective_style, tolerances)
    expected_without_placeholder_color = EffectiveStyle(
        font={key: value for key, value in expected.font.items() if key != "color"},
        paragraph=expected.paragraph,
        container=expected.container,
        page=expected.page,
    )
    return style_differences(
        expected_without_placeholder_color,
        control.effective_style,
        tolerances,
    )


def _physical_location(control: Any) -> tuple[Any, ...]:
    return (control.story, control.part, control.paragraph_index)


def _boundary(
    slot: SlotContract,
    control: Any,
    facts: DocumentFacts,
) -> tuple[Any, ...]:
    paragraph = next(
        (
            item
            for item in facts.paragraphs
            if item.story == control.story
            and item.part == control.part
            and item.paragraph_index == control.paragraph_index
        ),
        None,
    )
    left_gap: int | None = None
    right_gap: int | None = None
    if paragraph is not None and slot.locator.left_anchor is not None:
        anchor_start = paragraph.text.rfind(
            slot.locator.left_anchor,
            0,
            control.start + 1,
        )
        if anchor_start >= 0:
            left_gap = control.start - anchor_start - len(slot.locator.left_anchor)
    if paragraph is not None and slot.locator.right_anchor is not None:
        anchor_start = paragraph.text.find(slot.locator.right_anchor, control.end)
        if anchor_start >= 0:
            right_gap = anchor_start - control.end
    return (
        slot.locator.start,
        slot.locator.end,
        control.start,
        control.end,
        left_gap,
        right_gap,
    )


def _prerequisite_failure(
    slot: SlotContract,
    dimension: str,
    message: str,
) -> AssertionResult:
    return AssertionResult(
        assertion_id=f"{slot.slot_id}.{dimension}",
        view=View.SLOT,
        dimension=dimension,
        status=AssertionStatus.FAIL,
        required=slot.required,
        slot_id=slot.slot_id,
        gold_locator=slot.locator,
        message=message,
        failure_code=(
            "required_slot_prerequisite_missing"
            if slot.required
            else "optional_slot_prerequisite_missing"
        ),
    )


def evaluate_slots(
    gold_contract: FillContract,
    actual_contract: FillContract,
    gold_facts: DocumentFacts,
    actual_facts: DocumentFacts,
    field_registry: FieldRegistry,
    eval_config: EvalConfig,
) -> tuple[AssertionResult, ...]:
    assertions: list[AssertionResult] = []
    gold_ids = {slot.slot_id for slot in gold_contract.slots}
    actual_ids = {slot.slot_id for slot in actual_contract.slots}

    for extra_id in sorted(actual_ids - gold_ids):
        extra_slot = next(slot for slot in actual_contract.slots if slot.slot_id == extra_id)
        assertions.append(
            AssertionResult(
                assertion_id=f"{extra_id}.inventory.extra",
                view=View.SLOT,
                dimension="slot.inventory",
                status=AssertionStatus.FAIL,
                required=True,
                actual=extra_id,
                slot_id=extra_id,
                actual_locator=extra_slot.locator,
                message="Actual contains a slot not declared by Gold",
                failure_code="extra_slot",
            )
        )

    declared_tags = managed_marker_tags(actual_contract)
    for control in actual_facts.controls:
        if control.tag is not None and control.tag not in declared_tags:
            assertions.append(
                AssertionResult(
                    assertion_id=f"marker.{control.tag or 'missing-tag'}.inventory.broken",
                    view=View.SLOT,
                    dimension="slot.inventory",
                    status=AssertionStatus.FAIL,
                    required=True,
                    actual=control.tag,
                    message="template marker has no Actual contract slot",
                    failure_code="template_contract_marker_mismatch",
                )
            )

    for gold_slot in gold_contract.slots:
        alignment = align_slot(gold_slot, actual_contract, gold_facts, actual_facts)
        if alignment.status is AlignmentStatus.MISSING:
            assertions.append(
                AssertionResult(
                    assertion_id=f"{gold_slot.slot_id}.inventory",
                    view=View.SLOT,
                    dimension="slot.inventory",
                    status=AssertionStatus.FAIL,
                    required=gold_slot.required,
                    expected=gold_slot.slot_id,
                    actual=None,
                    slot_id=gold_slot.slot_id,
                    gold_locator=gold_slot.locator,
                    actual_locator=(
                        None if alignment.actual_slot is None else alignment.actual_slot.locator
                    ),
                    message=alignment.detail or "required slot is missing",
                    failure_code=(
                        "required_slot_missing"
                        if alignment.actual_slot is None and gold_slot.required
                        else "optional_slot_missing"
                        if alignment.actual_slot is None
                        else "template_contract_marker_mismatch"
                    ),
                )
            )
            for dimension in (
                "slot.location_boundary",
                "slot.field_mapping",
                "slot.value_style",
            ):
                assertions.append(
                    _prerequisite_failure(
                        gold_slot,
                        dimension,
                        "slot is missing, so this required dimension is not satisfied",
                    )
                )
            continue
        if alignment.status is AlignmentStatus.AMBIGUOUS:
            assertions.append(
                AssertionResult(
                    assertion_id=f"{gold_slot.slot_id}.inventory",
                    view=View.SLOT,
                    dimension="slot.inventory",
                    status=AssertionStatus.FAIL,
                    required=gold_slot.required,
                    slot_id=gold_slot.slot_id,
                    gold_locator=gold_slot.locator,
                    message=alignment.detail or "slot marker is ambiguous",
                    failure_code="template_contract_marker_mismatch",
                )
            )
            for dimension in (
                "slot.location_boundary",
                "slot.field_mapping",
                "slot.value_style",
            ):
                assertions.append(
                    _prerequisite_failure(
                        gold_slot,
                        dimension,
                        "ambiguous marker cannot be compared",
                    )
                )
            continue
        actual_slot = alignment.actual_slot
        gold_control = alignment.gold_control
        actual_control = alignment.actual_control
        if actual_slot is None or gold_control is None or actual_control is None:
            raise AssertionError("matched slot alignment must include contracts and controls")
        assertions.append(
            AssertionResult(
                assertion_id=f"{gold_slot.slot_id}.inventory",
                view=View.SLOT,
                dimension="slot.inventory",
                status=AssertionStatus.PASS,
                required=gold_slot.required,
                expected=gold_slot.slot_id,
                actual=actual_slot.slot_id,
                slot_id=gold_slot.slot_id,
                gold_locator=gold_slot.locator,
                actual_locator=actual_slot.locator,
                message="slot exists exactly once in contract and template",
            )
        )

        expected_location = _physical_location(gold_control)
        actual_location = _physical_location(actual_control)
        location_status = (
            AssertionStatus.PASS
            if expected_location == actual_location
            else AssertionStatus.FAIL
        )
        assertions.append(
            AssertionResult(
                assertion_id=f"{gold_slot.slot_id}.location",
                view=View.SLOT,
                dimension="slot.location_boundary",
                status=location_status,
                required=gold_slot.required,
                expected=expected_location,
                actual=actual_location,
                slot_id=gold_slot.slot_id,
                gold_locator=gold_slot.locator,
                actual_locator=actual_slot.locator,
                message=(
                    "slot location matches"
                    if location_status is AssertionStatus.PASS
                    else "slot is in the wrong structural location"
                ),
                failure_code=(
                    "wrong_structural_location"
                    if location_status is AssertionStatus.FAIL
                    else None
                ),
            )
        )
        expected_boundary = _boundary(gold_slot, gold_control, gold_facts)
        actual_boundary = _boundary(actual_slot, actual_control, actual_facts)
        boundary_status = (
            AssertionStatus.PASS
            if expected_boundary == actual_boundary
            else AssertionStatus.FAIL
        )
        assertions.append(
            AssertionResult(
                assertion_id=f"{gold_slot.slot_id}.boundary",
                view=View.SLOT,
                dimension="slot.location_boundary",
                status=boundary_status,
                required=gold_slot.required,
                expected=expected_boundary,
                actual=actual_boundary,
                slot_id=gold_slot.slot_id,
                gold_locator=gold_slot.locator,
                actual_locator=actual_slot.locator,
                message=(
                    "slot boundary matches"
                    if boundary_status is AssertionStatus.PASS
                    else "slot boundary differs from Gold"
                ),
                failure_code=(
                    "slot_overlaps_protected"
                    if boundary_status is AssertionStatus.FAIL
                    else None
                ),
            )
        )

        field = field_registry.by_id.get(actual_slot.field_id)
        field_matches = (
            actual_slot.field_id == gold_slot.field_id
            and actual_control.alias == actual_slot.field_id
            and gold_control.alias == gold_slot.field_id
            and field is not None
            and field.content_type == actual_slot.content_type
        )
        field_status = AssertionStatus.PASS if field_matches else AssertionStatus.FAIL
        assertions.append(
            AssertionResult(
                assertion_id=f"{gold_slot.slot_id}.field_id",
                view=View.SLOT,
                dimension="slot.field_mapping",
                status=field_status,
                required=gold_slot.required,
                expected=gold_slot.field_id,
                actual={
                    "contract_field_id": actual_slot.field_id,
                    "marker_alias": actual_control.alias,
                },
                slot_id=gold_slot.slot_id,
                gold_locator=gold_slot.locator,
                actual_locator=actual_slot.locator,
                message=(
                    "slot field mapping matches"
                    if field_matches
                    else "slot field mapping differs from Gold or Registry"
                ),
                failure_code=(
                    "slot_field_mapping_invalid"
                    if field_status is AssertionStatus.FAIL
                    else None
                ),
            )
        )

        contract_differences = style_differences(
            gold_slot.expected_value_style,
            actual_slot.expected_value_style,
            eval_config.tolerances,
        )
        marker_differences = _marker_style_differences(
            actual_slot.expected_value_style,
            actual_control,
            eval_config.tolerances,
        )
        gold_marker_differences = _marker_style_differences(
            gold_slot.expected_value_style,
            gold_control,
            eval_config.tolerances,
        )
        value_style_status = (
            AssertionStatus.PASS
            if not contract_differences
            and not marker_differences
            and not gold_marker_differences
            else AssertionStatus.FAIL
        )
        assertions.append(
            AssertionResult(
                assertion_id=f"{gold_slot.slot_id}.value_style",
                view=View.SLOT,
                dimension="slot.value_style",
                status=value_style_status,
                required=gold_slot.required,
                expected=gold_slot.expected_value_style,
                actual=actual_slot.expected_value_style,
                slot_id=gold_slot.slot_id,
                gold_locator=gold_slot.locator,
                actual_locator=actual_slot.locator,
                message=(
                    "slot value-style contract matches"
                    if value_style_status is AssertionStatus.PASS
                    else "slot value-style contract or marker effective style differs"
                ),
            )
        )
    return tuple(assertions)
