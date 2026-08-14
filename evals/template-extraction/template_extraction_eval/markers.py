"""Validate the content-control marker protocol independently of product code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import InputContractError, InputErrorCode
from .models import DocumentFacts, FillContract, Locator, Owner


@dataclass(frozen=True)
class MarkerExpectation:
    tag: str
    field_id: str
    locator: Locator


def marker_expectations(
    contract: FillContract,
    *,
    path: Path | None = None,
) -> dict[str, MarkerExpectation]:
    """Collect every managed tag from slots, components, and slot regions."""

    expected: dict[str, MarkerExpectation] = {}

    def add(locator: Locator, field_id: str) -> None:
        if locator.type != "content_control_tag":
            return
        if locator.value is None:
            raise InputContractError(
                InputErrorCode.CONTRACT_MISMATCH,
                f"content-control locator for {field_id} has no tag value",
                path=path,
            )
        candidate = MarkerExpectation(locator.value, field_id, locator)
        previous = expected.get(candidate.tag)
        if previous is not None and (
            previous.field_id != candidate.field_id
            or previous.locator.story != candidate.locator.story
            or previous.locator.part != candidate.locator.part
            or previous.locator.expected_match_count
            != candidate.locator.expected_match_count
        ):
            raise InputContractError(
                InputErrorCode.CONTRACT_MISMATCH,
                f"marker tag {candidate.tag!r} has conflicting contract declarations",
                path=path,
            )
        expected[candidate.tag] = candidate

    for slot in contract.slots:
        add(slot.locator, slot.field_id)
        for component in slot.component_locators:
            add(component.locator, slot.field_id)
    for region in contract.regions:
        if region.owner is not Owner.SLOT:
            continue
        locators = tuple(
            locator
            for locator in (region.start_locator, region.end_locator)
            if locator is not None and locator.type == "content_control_tag"
        )
        if not locators:
            continue
        if len(region.field_ids) != 1:
            raise InputContractError(
                InputErrorCode.CONTRACT_MISMATCH,
                f"slot region {region.region_id} must map managed markers to one field",
                path=path,
            )
        for locator in locators:
            add(locator, region.field_ids[0])
    return expected


def managed_marker_tags(contract: FillContract) -> frozenset[str]:
    return frozenset(marker_expectations(contract))


def validate_markers(
    contract: FillContract,
    facts: DocumentFacts,
    *,
    label: str,
    path: Path,
) -> None:
    expected = marker_expectations(contract, path=path)
    actual: dict[str, list[object]] = {}
    for control in facts.controls:
        if control.tag is not None:
            actual.setdefault(control.tag, []).append(control)
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise InputContractError(
            InputErrorCode.CONTRACT_MISMATCH,
            f"{label} template marker closure differs: missing={missing}, extra={extra}",
            path=path,
        )
    for tag, expectation in expected.items():
        controls = actual[tag]
        valid = (
            len(controls) == expectation.locator.expected_match_count
            and all(getattr(control, "alias", None) == expectation.field_id for control in controls)
            and all(
                getattr(control, "story", None) == expectation.locator.story
                for control in controls
            )
            and all(
                getattr(control, "part", None) == expectation.locator.part
                for control in controls
            )
        )
        if not valid:
            raise InputContractError(
                InputErrorCode.CONTRACT_MISMATCH,
                f"{label} marker {tag!r} violates count, alias, story, or part contract",
                path=path,
            )


__all__ = [
    "MarkerExpectation",
    "managed_marker_tags",
    "marker_expectations",
    "validate_markers",
]
