from __future__ import annotations

from pathlib import Path

import pytest

from template_extraction_eval.contracts import (
    InputContractError,
    InputErrorCode,
    load_fill_contract,
)
from template_extraction_eval.markers import marker_expectations, validate_markers
from template_extraction_eval.models import (
    ContentControlFact,
    DocumentFacts,
    EffectiveStyle,
    FillContract,
    Locator,
    SlotContract,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES = PROJECT_ROOT / "cases"


@pytest.mark.parametrize(
    ("case_id", "error_code"),
    [
        ("01-hunau-undergraduate", InputErrorCode.CONTRACT_MISMATCH),
        ("02-njau-undergraduate", InputErrorCode.SCHEMA_INVALID),
        ("03-pku-graduate", InputErrorCode.CONTRACT_MISMATCH),
    ],
)
def test_marker_01_through_03_retired_school_gold_contracts_fail_closed(
    case_id: str,
    error_code: InputErrorCode,
) -> None:
    root = CASES / case_id / "gold"
    with pytest.raises(InputContractError) as captured:
        load_fill_contract(root / "fill-contract.gold.yaml")

    assert captured.value.code is error_code


def test_marker_04_current_slot_ref_contract_closes_marker_protocol() -> None:
    style = EffectiveStyle(font={}, paragraph={}, container={}, page={})
    slot = SlotContract(
        slot_ref=(
            "source_entry_id=source-entry-u-all-block-0001;extent=whole_entry;"
            f"source_snapshot_sha256={'3' * 64};"
            "field_id=thesis.title.zh"
        ),
        field_id="thesis.title.zh",
        content_type="text",
        required=True,
        locator=Locator(
            type="content_control_tag",
            story="document",
            part="word/document.xml",
            expected_match_count=1,
            value="docfit.cover.title",
        ),
        expected_value_style=style,
    )
    contract = FillContract(
        schema_version="docfit-template-fill-contract/v2",
        contract_id="synthetic.marker",
        template_sha256="0" * 64,
        registry_id="registry",
        registry_version="0.1.0",
        registry_sha256="1" * 64,
        marker_protocol="docfit-content-control-marker/v1",
        regions=(),
        slots=(slot,),
    )
    facts = DocumentFacts(
        document_sha256="0" * 64,
        parts=("word/document.xml",),
        relationships=(),
        paragraphs=(),
        controls=(
            ContentControlFact(
                alias="thesis.title.zh",
                tag="docfit.cover.title",
                internal_id="1",
                story="document",
                part="word/document.xml",
                paragraph_index=0,
                start=0,
                end=4,
                text="Title",
                effective_style=style,
            ),
        ),
        tables=(),
        objects=(),
        unsupported=(),
    )

    assert set(marker_expectations(contract)) == {"docfit.cover.title"}
    validate_markers(
        contract,
        facts,
        label="Current",
        path=PROJECT_ROOT / "synthetic-fill-contract.yaml",
    )


def test_marker_05_placeholder_locator_does_not_invent_word_markers() -> None:
    style = EffectiveStyle(font={}, paragraph={}, container={}, page={})
    slot = SlotContract(
        slot_ref=(
            "source_entry_id=source-entry-u-all-block-0001;extent=whole_entry;"
            f"source_snapshot_sha256={'3' * 64};"
            "field_id=thesis.title.zh"
        ),
        field_id="thesis.title.zh",
        content_type="text",
        required=True,
        locator=Locator(
            type="placeholder_anchor",
            story="document",
            part="word/document.xml",
            expected_match_count=1,
            value="Title",
        ),
        expected_value_style=style,
    )
    contract = FillContract(
        schema_version="docfit-template-fill-contract/v2",
        contract_id="synthetic.marker.placeholder",
        template_sha256="0" * 64,
        registry_id="registry",
        registry_version="0.1.0",
        registry_sha256="1" * 64,
        marker_protocol="docfit-content-control-marker/v1",
        regions=(),
        slots=(slot,),
    )

    assert marker_expectations(contract) == {}


def test_marker_06_untagged_word_controls_are_not_product_markers() -> None:
    style = EffectiveStyle(font={}, paragraph={}, container={}, page={})
    contract = FillContract(
        schema_version="docfit-template-fill-contract/v2",
        contract_id="synthetic.marker.empty",
        template_sha256="0" * 64,
        registry_id="registry",
        registry_version="0.1.0",
        registry_sha256="1" * 64,
        marker_protocol="docfit-content-control-marker/v1",
        regions=(),
        slots=(),
    )
    facts = DocumentFacts(
        document_sha256="0" * 64,
        parts=("word/document.xml",),
        relationships=(),
        paragraphs=(),
        controls=(
            ContentControlFact(
                alias=None,
                tag=None,
                internal_id="1",
                story="document",
                part="word/document.xml",
                paragraph_index=0,
                start=0,
                end=4,
                text="Text",
                effective_style=style,
            ),
        ),
        tables=(),
        objects=(),
        unsupported=(),
    )

    validate_markers(
        contract,
        facts,
        label="Current",
        path=PROJECT_ROOT / "synthetic-fill-contract.yaml",
    )
