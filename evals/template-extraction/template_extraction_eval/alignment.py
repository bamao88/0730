"""Deterministic Actual-Gold alignment by IDs, locators, anchors, and occurrence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .facts.structure import locate_paragraphs
from .models import (
    ContentControlFact,
    DocumentFacts,
    FillContract,
    ParagraphFact,
    RegionContract,
    SlotContract,
)


class AlignmentStatus(StrEnum):
    MATCHED = "MATCHED"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class RegionAlignment:
    status: AlignmentStatus
    gold_region: RegionContract
    actual_region: RegionContract | None
    gold_paragraph: ParagraphFact | None
    actual_paragraph: ParagraphFact | None
    detail: str | None = None


@dataclass(frozen=True)
class SlotAlignment:
    status: AlignmentStatus
    gold_slot: SlotContract
    actual_slot: SlotContract | None
    gold_control: ContentControlFact | None
    actual_control: ContentControlFact | None
    detail: str | None = None


def _single_paragraph(
    facts: DocumentFacts,
    region: RegionContract,
) -> tuple[AlignmentStatus, ParagraphFact | None]:
    matches = locate_paragraphs(facts.paragraphs, region.locator)
    if not matches:
        return AlignmentStatus.MISSING, None
    if len(matches) != region.locator.expected_match_count or len(matches) != 1:
        return AlignmentStatus.AMBIGUOUS, None
    return AlignmentStatus.MATCHED, matches[0]


def align_region(
    gold_region: RegionContract,
    actual_contract: FillContract,
    gold_facts: DocumentFacts,
    actual_facts: DocumentFacts,
) -> RegionAlignment:
    actual_regions = [
        region for region in actual_contract.regions if region.region_id == gold_region.region_id
    ]
    if not actual_regions:
        gold_status, gold_paragraph = _single_paragraph(gold_facts, gold_region)
        if gold_status is AlignmentStatus.AMBIGUOUS:
            return RegionAlignment(
                AlignmentStatus.AMBIGUOUS,
                gold_region,
                None,
                None,
                None,
                "Gold fallback locator has multiple equivalent matches",
            )
        fallback: list[tuple[RegionContract, ParagraphFact]] = []
        for candidate in actual_contract.regions:
            if candidate.owner is not gold_region.owner:
                continue
            status, paragraph = _single_paragraph(actual_facts, candidate)
            if (
                status is AlignmentStatus.MATCHED
                and paragraph is not None
                and gold_paragraph is not None
                and _paragraph_location(paragraph) == _paragraph_location(gold_paragraph)
            ):
                fallback.append((candidate, paragraph))
        if len(fallback) == 1:
            return RegionAlignment(
                AlignmentStatus.MATCHED,
                gold_region,
                fallback[0][0],
                gold_paragraph,
                fallback[0][1],
                "matched by unique structural fallback locator",
            )
        return RegionAlignment(
            AlignmentStatus.AMBIGUOUS if len(fallback) > 1 else AlignmentStatus.MISSING,
            gold_region,
            None,
            gold_paragraph,
            None,
            (
                "multiple Actual regions match the structural fallback locator"
                if len(fallback) > 1
                else "Actual contract has no matching region_id or unique locator fallback"
            ),
        )
    if len(actual_regions) != 1:
        return RegionAlignment(
            AlignmentStatus.AMBIGUOUS,
            gold_region,
            None,
            None,
            None,
            "Actual contract contains duplicate region_id values",
        )
    actual_region = actual_regions[0]
    gold_status, gold_paragraph = _single_paragraph(gold_facts, gold_region)
    actual_status, actual_paragraph = _single_paragraph(actual_facts, actual_region)
    if AlignmentStatus.AMBIGUOUS in {gold_status, actual_status}:
        return RegionAlignment(
            AlignmentStatus.AMBIGUOUS,
            gold_region,
            actual_region,
            gold_paragraph,
            actual_paragraph,
            "region locator has multiple equivalent matches",
        )
    if AlignmentStatus.MISSING in {gold_status, actual_status}:
        return RegionAlignment(
            AlignmentStatus.MISSING,
            gold_region,
            actual_region,
            gold_paragraph,
            actual_paragraph,
            "region locator has no match",
        )
    return RegionAlignment(
        AlignmentStatus.MATCHED,
        gold_region,
        actual_region,
        gold_paragraph,
        actual_paragraph,
    )


def _paragraph_location(paragraph: ParagraphFact) -> tuple[object, ...]:
    return (
        paragraph.story,
        paragraph.part,
        paragraph.section_index,
        paragraph.paragraph_index,
        paragraph.table_index,
        paragraph.row,
        paragraph.cell,
    )


def _controls_for_slot(
    facts: DocumentFacts,
    slot: SlotContract,
) -> tuple[ContentControlFact, ...]:
    locator = slot.locator
    matches = tuple(
        control
        for control in facts.controls
        if control.story == locator.story
        and control.part == locator.part
        and (locator.value is None or control.tag == locator.value)
        and (
            locator.paragraph_index is None
            or control.paragraph_index == locator.paragraph_index
        )
    )
    if locator.occurrence is not None:
        index = locator.occurrence - 1
        return () if index >= len(matches) else (matches[index],)
    return matches


def align_slot(
    gold_slot: SlotContract,
    actual_contract: FillContract,
    gold_facts: DocumentFacts,
    actual_facts: DocumentFacts,
) -> SlotAlignment:
    actual_slots = [slot for slot in actual_contract.slots if slot.slot_id == gold_slot.slot_id]
    if not actual_slots:
        actual_slots = [
            slot
            for slot in actual_contract.slots
            if slot.locator.value == gold_slot.locator.value
            and slot.locator.story == gold_slot.locator.story
            and slot.locator.part == gold_slot.locator.part
        ]
        if len(actual_slots) > 1:
            return SlotAlignment(
                AlignmentStatus.AMBIGUOUS,
                gold_slot,
                None,
                None,
                None,
                "multiple Actual slots match the tag fallback locator",
            )
        if not actual_slots:
            return SlotAlignment(
                AlignmentStatus.MISSING,
                gold_slot,
                None,
                None,
                None,
                "Actual contract has no matching slot_id or tag fallback",
            )
    if len(actual_slots) != 1:
        return SlotAlignment(
            AlignmentStatus.AMBIGUOUS,
            gold_slot,
            None,
            None,
            None,
            "Actual contract contains duplicate slot_id values",
        )
    actual_slot = actual_slots[0]
    gold_controls = _controls_for_slot(gold_facts, gold_slot)
    actual_controls = _controls_for_slot(actual_facts, actual_slot)
    if len(gold_controls) == len(actual_controls) == 1:
        return SlotAlignment(
            AlignmentStatus.MATCHED,
            gold_slot,
            actual_slot,
            gold_controls[0],
            actual_controls[0],
        )
    if not gold_controls or not actual_controls:
        return SlotAlignment(
            AlignmentStatus.MISSING,
            gold_slot,
            actual_slot,
            gold_controls[0] if len(gold_controls) == 1 else None,
            actual_controls[0] if len(actual_controls) == 1 else None,
            "slot marker has no matching content control",
        )
    return SlotAlignment(
        AlignmentStatus.AMBIGUOUS,
        gold_slot,
        actual_slot,
        None,
        None,
        "slot locator has multiple equivalent content controls",
    )
