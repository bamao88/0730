from __future__ import annotations

from dataclasses import replace

from template_extraction_eval.alignment import (
    AlignmentStatus,
    align_region,
    align_slot,
)
from template_extraction_eval.models import (
    ContentControlFact,
    DocumentFacts,
    EffectiveStyle,
    FillContract,
    Locator,
    Owner,
    ParagraphFact,
    RegionContract,
    RunFact,
    SlotContract,
)

STYLE = EffectiveStyle(font={}, paragraph={}, container={}, page={})
SLOT_REF = (
    "source_entry_id=source-entry-u-all-block-0001;extent=whole_entry;"
    f"source_snapshot_sha256={'3' * 64};field_id=title.zh"
)


def _paragraph(index: int, text: str = "Name:") -> ParagraphFact:
    return ParagraphFact(
        story="document",
        part="word/document.xml",
        paragraph_index=index,
        section_index=0,
        path=f"word/document.xml:document:p[{index}]",
        text=text,
        tokens=(f"TEXT:{text}",),
        runs=(
            RunFact(
                text=text,
                start=0,
                end=len(text),
                style_id=None,
                effective_style=STYLE,
            ),
        ),
    )


def _control(tag: str = "same.tag") -> ContentControlFact:
    return ContentControlFact(
        alias="title.zh",
        tag=tag,
        internal_id="1",
        story="document",
        part="word/document.xml",
        paragraph_index=0,
        start=0,
        end=4,
        text="Name",
        effective_style=STYLE,
        paragraph_indices=(0,),
        block_level=False,
        showing_placeholder=True,
    )


def _region(region_id: str = "protected.name") -> RegionContract:
    return RegionContract(
        region_id=region_id,
        owner=Owner.PROTECTED,
        required=True,
        locator=Locator(
            type="text_anchor",
            story="document",
            part="word/document.xml",
            expected_match_count=1,
            left_anchor="Name:",
        ),
    )


def _facts(
    *,
    paragraphs: tuple[ParagraphFact, ...] = (_paragraph(0),),
    controls: tuple[ContentControlFact, ...] = (_control(),),
) -> DocumentFacts:
    return DocumentFacts(
        document_sha256="2" * 64,
        parts=("word/document.xml",),
        relationships=(),
        paragraphs=paragraphs,
        controls=controls,
        tables=(),
        objects=(),
        unsupported=(),
    )


def test_ali_01_region_and_slot_refs_match_exactly() -> None:
    region_contract = _region()
    slot_contract = _slot_contract(SLOT_REF, tag="same.tag")
    contract = _fill_contract(slot_contract, regions=(region_contract,))
    facts = _facts()

    region = align_region(region_contract, contract, facts, facts)
    slot = align_slot(slot_contract, contract, facts, facts)

    assert region.status is AlignmentStatus.MATCHED
    assert slot.status is AlignmentStatus.MATCHED


def test_ali_02_region_id_mismatch_fails_closed_without_locator_fallback() -> None:
    gold_region = _region()
    gold_slot = _slot_contract(SLOT_REF, tag="same.tag")
    mismatched_slot_ref = (
        "source_entry_id=source-entry-u-all-block-0001;extent=whole_entry;"
        f"source_snapshot_sha256={'3' * 64};field_id=title.en"
    )
    actual = _fill_contract(
        replace(gold_slot, slot_ref=mismatched_slot_ref),
        regions=(replace(gold_region, region_id="protected.changed_id"),),
    )
    facts = _facts()

    region = align_region(gold_region, actual, facts, facts)
    slot = align_slot(gold_slot, actual, facts, facts)

    assert region.status is AlignmentStatus.MISSING
    assert region.detail == "Actual contract has no matching region_id"
    assert slot.status is AlignmentStatus.MISSING
    assert slot.detail == "Actual contract has no matching slot_ref"


def test_ali_03_duplicate_anchor_is_ambiguous_not_first_match() -> None:
    region_contract = _region()
    contract = _fill_contract(
        _slot_contract(SLOT_REF, tag="same.tag"),
        regions=(region_contract,),
    )
    facts = _facts(paragraphs=(_paragraph(0), _paragraph(1)), controls=(_control(),))

    alignment = align_region(
        region_contract,
        contract,
        facts,
        facts,
    )

    assert alignment.status is AlignmentStatus.AMBIGUOUS
    assert alignment.gold_paragraph is None


def test_ali_04_missing_slot_has_no_synthetic_control() -> None:
    gold_slot = _slot_contract(SLOT_REF, tag="same.tag")
    actual = _fill_contract(slots=())
    facts = _facts()

    alignment = align_slot(
        gold_slot,
        actual,
        facts,
        facts,
    )

    assert alignment.status is AlignmentStatus.MISSING
    assert alignment.actual_control is None


def _slot_contract(slot_ref: str, *, tag: str) -> SlotContract:
    return SlotContract(
        slot_ref=slot_ref,
        field_id="title.zh",
        content_type="plain_text",
        required=True,
        locator=Locator(
            type="content_control_tag",
            story="document",
            part="word/document.xml",
            expected_match_count=1,
            value=tag,
        ),
        expected_value_style=STYLE,
    )


def _fill_contract(
    slot: SlotContract | None = None,
    *,
    slots: tuple[SlotContract, ...] | None = None,
    regions: tuple[RegionContract, ...] = (),
) -> FillContract:
    resolved_slots = ((slot,) if slot is not None else ()) if slots is None else slots
    return FillContract(
        schema_version="docfit-template-fill-contract/v2",
        contract_id="contract",
        template_sha256="0" * 64,
        registry_id="registry",
        registry_version="0.5.0",
        registry_sha256="1" * 64,
        marker_protocol="docfit-content-control-marker/v1",
        regions=regions,
        slots=resolved_slots,
    )


def _empty_facts() -> DocumentFacts:
    return DocumentFacts(
        document_sha256="2" * 64,
        parts=("word/document.xml",),
        relationships=(),
        paragraphs=(),
        controls=(),
        tables=(),
        objects=(),
        unsupported=(),
    )


def test_ali_05_slot_ref_mismatch_does_not_fallback_to_matching_locator() -> None:
    gold_slot = _slot_contract("slot.gold", tag="same.tag")
    actual_slot = _slot_contract("slot.actual", tag="same.tag")

    alignment = align_slot(
        gold_slot,
        _fill_contract(actual_slot),
        _empty_facts(),
        _empty_facts(),
    )

    assert alignment.status is AlignmentStatus.MISSING
    assert alignment.actual_slot is None
    assert alignment.detail == "Actual contract has no matching slot_ref"


def test_ali_06_slot_text_anchor_does_not_synthesize_content_control() -> None:
    gold_slot = _slot_contract(SLOT_REF, tag="same.tag")
    actual_slot = replace(
        gold_slot,
        locator=Locator(
            type="text_anchor",
            story="document",
            part="word/document.xml",
            expected_match_count=1,
            left_anchor="Name:",
            paragraph_index=0,
        ),
    )

    alignment = align_slot(
        gold_slot,
        _fill_contract(actual_slot),
        _facts(),
        _facts(controls=()),
    )

    assert alignment.status is AlignmentStatus.MISSING
    assert alignment.actual_slot == actual_slot
    assert alignment.actual_control is None
    assert alignment.detail == "slot marker has no matching content control"
