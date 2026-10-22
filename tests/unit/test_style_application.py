from __future__ import annotations

from typing import Any

from docfit.content.style_application import build_style_occurrence_manifest
from docfit.styles import StyleContractSet, style_contract_digest


def _contract(style_contract_id: str) -> dict[str, Any]:
    properties = {"paragraph.alignment": "left"}
    value: dict[str, Any] = {
        "style_contract_id": style_contract_id,
        "application_scope": "paragraph",
        "owned_properties": sorted(properties),
        "effective_properties": properties,
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": [],
    }
    value["contract_digest"] = style_contract_digest(value)
    return value


def test_object_projection_occurrences_are_object_only() -> None:
    body_contract = _contract("style.body.paragraph")
    contracts = StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": "a" * 64,
            "styles": [body_contract],
        }
    )
    style_ref = {
        "style_contract_id": body_contract["style_contract_id"],
        "contract_digest": body_contract["contract_digest"],
    }

    manifest = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {"occurrences": []},
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "style_role_refs": {"body.paragraph": style_ref},
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "drawing",
                    "word_style_id": "a",
                },
                {
                    "target_locator": "/body/p[@paraId=00000002]",
                    "presentation_role": "formula",
                    "word_style_id": "a",
                },
                {
                    "target_locator": "/body/p[@paraId=00000003]",
                    "presentation_role": "body",
                    "word_style_id": "a",
                },
            ]
        },
    )

    assert [item["occurrence_id"] for item in manifest["occurrences"]] == [
        "projection:body:1"
    ]


def test_caption_projection_occurrences_ignore_non_caption_fallbacks() -> None:
    body_contract = _contract("style.slot.body.paragraph.1")
    caption_contract = _contract("style.slot.body.figure.caption.1")
    contracts = StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": "a" * 64,
            "styles": [body_contract, caption_contract],
        }
    )
    body_ref = {
        "style_contract_id": body_contract["style_contract_id"],
        "contract_digest": body_contract["contract_digest"],
    }
    caption_ref = {
        "style_contract_id": caption_contract["style_contract_id"],
        "contract_digest": caption_contract["contract_digest"],
    }

    manifest = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {"occurrences": []},
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "style_role_refs": {
                        "body.paragraph": body_ref,
                        "body.figure.caption": body_ref,
                        "body.table.caption": caption_ref,
                    },
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "figure_caption",
                    "word_style_id": "a",
                },
                {
                    "target_locator": "/body/p[@paraId=00000002]",
                    "presentation_role": "table_caption",
                    "word_style_id": "a",
                },
            ]
        },
    )

    assert [item["occurrence_id"] for item in manifest["occurrences"]] == [
        "projection:table_caption:1"
    ]


def test_body_projection_occurrences_ignore_body_slot_fallbacks() -> None:
    slot_body_contract = _contract("style.slot.body.paragraph.1")
    target_body_contract = _contract("style.body.paragraph")
    contracts = StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": "a" * 64,
            "styles": [slot_body_contract, target_body_contract],
        }
    )
    slot_body_ref = {
        "style_contract_id": slot_body_contract["style_contract_id"],
        "contract_digest": slot_body_contract["contract_digest"],
    }
    target_body_ref = {
        "style_contract_id": target_body_contract["style_contract_id"],
        "contract_digest": target_body_contract["contract_digest"],
    }

    skipped = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {
                "occurrences": [
                    {
                        "occurrence_id": "fill:title:1",
                        "locator": "/body/p[@paraId=00000000]",
                        "style_contract_ref": target_body_ref,
                    }
                ]
            },
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "style_role_refs": {"body.paragraph": slot_body_ref},
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "body",
                    "word_style_id": "a",
                }
            ]
        },
    )

    retained = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {
                "occurrences": [
                    {
                        "occurrence_id": "fill:title:1",
                        "locator": "/body/p[@paraId=00000000]",
                        "style_contract_ref": target_body_ref,
                    }
                ]
            },
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "style_role_refs": {"body.paragraph": target_body_ref},
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "body",
                    "word_style_id": "a",
                }
            ]
        },
    )

    assert [item["occurrence_id"] for item in skipped["occurrences"]] == [
        "fill:title:1"
    ]
    assert [item["occurrence_id"] for item in retained["occurrences"]] == [
        "fill:title:1",
        "projection:body:1"
    ]


def test_reference_projection_occurrences_ignore_reference_slot_fallbacks() -> None:
    reference_contract = _contract("style.slot.references.entries.1")
    title_contract = _contract("style.title")
    contracts = StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": "a" * 64,
            "styles": [reference_contract, title_contract],
        }
    )
    reference_ref = {
        "style_contract_id": reference_contract["style_contract_id"],
        "contract_digest": reference_contract["contract_digest"],
    }
    title_ref = {
        "style_contract_id": title_contract["style_contract_id"],
        "contract_digest": title_contract["contract_digest"],
    }

    manifest = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {
                "occurrences": [
                    {
                        "occurrence_id": "fill:title:1",
                        "locator": "/body/p[@paraId=00000000]",
                        "style_contract_ref": title_ref,
                    }
                ]
            },
            "block_operations": [
                {
                    "field_id": "references.entries",
                    "style_contract_ref": reference_ref,
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "reference",
                    "word_style_id": "direct",
                }
            ]
        },
    )

    assert [item["occurrence_id"] for item in manifest["occurrences"]] == [
        "fill:title:1"
    ]


def test_heading_projection_occurrences_ignore_heading_slot_fallbacks() -> None:
    slot_heading_contract = _contract("style.slot.body.heading.level1.1")
    target_heading_contract = _contract("style.body.chapter_title")
    contracts = StyleContractSet.from_mapping(
        {
            "schema_version": "docfit-style-contract-set/v2",
            "template_sha256": "a" * 64,
            "styles": [slot_heading_contract, target_heading_contract],
        }
    )
    slot_heading_ref = {
        "style_contract_id": slot_heading_contract["style_contract_id"],
        "contract_digest": slot_heading_contract["contract_digest"],
    }
    target_heading_ref = {
        "style_contract_id": target_heading_contract["style_contract_id"],
        "contract_digest": target_heading_contract["contract_digest"],
    }

    skipped = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {
                "occurrences": [
                    {
                        "occurrence_id": "fill:title:1",
                        "locator": "/body/p[@paraId=00000000]",
                        "style_contract_ref": target_heading_ref,
                    }
                ]
            },
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "style_role_refs": {"body.heading.outline1": slot_heading_ref},
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "chapter_title",
                    "word_style_id": "1",
                }
            ]
        },
    )

    retained = build_style_occurrence_manifest(
        contracts=contracts,
        fill_result={
            "style_occurrence_manifest": {
                "occurrences": [
                    {
                        "occurrence_id": "fill:title:1",
                        "locator": "/body/p[@paraId=00000000]",
                        "style_contract_ref": target_heading_ref,
                    }
                ]
            },
            "block_operations": [
                {
                    "field_id": "body.ordered_items",
                    "style_role_refs": {"body.heading.outline1": target_heading_ref},
                }
            ],
        },
        projection={
            "style_occurrences": [
                {
                    "target_locator": "/body/p[@paraId=00000001]",
                    "presentation_role": "chapter_title",
                    "word_style_id": "1",
                }
            ]
        },
    )

    assert [item["occurrence_id"] for item in skipped["occurrences"]] == [
        "fill:title:1"
    ]
    assert [item["occurrence_id"] for item in retained["occurrences"]] == [
        "fill:title:1",
        "projection:chapter_title:1",
    ]
