from __future__ import annotations

from copy import deepcopy

from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.source_spans import (
    SourceSpan,
    TextSourceExtent,
    resolve_semantic_judgments,
    source_span_ref,
)
from docfit.tools.runtime import sha256_json
from tests.support.source_identity import review_binding, source_partition


def _vocabulary() -> dict[str, object]:
    return {
        "schema_version": 1,
        "registry_id": "test",
        "registry_version": "v1",
        "digest": "d" * 64,
        "allowed_field_ids": ["thesis.title.zh"],
        "fields": [{
            "field_id": "thesis.title.zh",
            "usage_affordance": {"allowed_part_roles": ["fill_slot"]},
        }],
    }


def _accepted_review_fixture() -> tuple[dict[str, object], dict[str, object]]:
    vocabulary = _vocabulary()
    block_id = "u-cover:block-0001"
    semantic_judgments = [
        {
            "scope": {"reading_block_id": block_id},
            "parts": [
                {"text": "论文题目：", "role": "fixed_label"},
                {"text": "×××", "role": "fill_slot", "field_id": "thesis.title.zh"},
            ],
            "resolved_spans": [
                {
                    "span_ref": f"reading_block_id={block_id};part_index=0",
                    "scope": {"reading_block_id": block_id},
                    "part_index": 0,
                    "role": "fixed_label",
                    "text": "论文题目：",
                    "covered_object_ids": ["obj-title"],
                },
                {
                    "span_ref": f"reading_block_id={block_id};part_index=1",
                    "scope": {"reading_block_id": block_id},
                    "part_index": 1,
                    "role": "fill_slot",
                    "field_id": "thesis.title.zh",
                    "slot_ref": (
                        f"reading_block_id={block_id};part_index=1;field_id=thesis.title.zh"
                    ),
                    "text": "×××",
                    "covered_object_ids": ["obj-title"],
                },
            ],
        }
    ]
    inventory = {
        "schema_version": 2,
        "document_sha256": "a" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "objects": [{"object_id": "obj-title", "type": "run"}],
        "reading_blocks": [
            {
                "block_id": block_id,
                "range_id": "u-cover:range-0001",
                "unit_id": "u-cover",
                "text": "论文题目：×××",
                "covered_object_ids": ["obj-title"],
                "object_text_spans": [
                    {
                        "object_id": "obj-title",
                        "text": "论文题目：×××",
                        "text_start": 0,
                        "text_end": len("论文题目：×××"),
                    }
                ],
            }
        ],
    }
    review = {
        "schema_version": 2,
        "document_sha256": "a" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments_sha256": sha256_json(semantic_judgments),
        "semantic_judgments": semantic_judgments,
    }
    return inventory, review


def _source_entry_review_fixture() -> tuple[dict[str, object], dict[str, object]]:
    vocabulary = _vocabulary()
    source_entry_id = "source-entry-title"
    text = "论文题目：×××"
    agent_judgments = [
        {
            "source_entry_id": source_entry_id,
            "parts": [
                {"text": "论文题目：", "role": "fixed_label"},
                {"text": "×××", "role": "fill_slot", "field_id": "thesis.title.zh"},
            ],
        }
    ]
    inventory = {
        "schema_version": 2,
        "document_sha256": "a" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-parent",
                        "locator": "/body/p[1]",
                        "text_span": [0, len(text)],
                    },
                    {
                        "object_id": "obj-label",
                        "locator": "/body/p[1]/r[1]",
                        "text_span": [0, 5],
                    },
                    {
                        "object_id": "obj-value",
                        "locator": "/body/p[1]/r[2]",
                        "text_span": [5, 8],
                    },
                ],
            }
        ],
        "objects": [
            {"object_id": "obj-parent", "type": "paragraph", "source_entry_id": source_entry_id},
            {"object_id": "obj-label", "type": "run", "source_entry_id": source_entry_id},
            {"object_id": "obj-value", "type": "run", "source_entry_id": source_entry_id},
        ],
        "reading_blocks": [],
    }
    source_partition(inventory)
    resolved_spans = resolve_semantic_judgments(
        inventory=inventory,
        judgments=agent_judgments,
    )
    semantic_judgments = [{**agent_judgments[0], "resolved_spans": resolved_spans}]
    review = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": "a" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments_sha256": sha256_json(semantic_judgments),
        "semantic_judgments": semantic_judgments,
        "resolved_spans": resolved_spans,
    }
    return inventory, review


def test_shared_review_accepts_explicit_structural_whole_entry_span() -> None:
    vocabulary = _vocabulary()
    inventory = {
        "schema_version": 2,
        "document_sha256": "a" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "source_entries": [
            {
                "source_entry_id": "source-entry-break",
                "text": "",
                "entry_type": "break",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-break",
                        "locator": "/body/p[1]/r[1]/br[1]",
                        "extent": {"kind": "whole_entry"},
                    }
                ],
            }
        ],
        "objects": [
            {
                "object_id": "obj-break",
                "type": "break",
                "source_entry_id": "source-entry-break",
            }
        ],
        "reading_blocks": [],
    }
    agent_judgments = [
        {
            "source_entry_id": "source-entry-break",
            "parts": [{"text": "", "role": "style_only"}],
        }
    ]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=agent_judgments,
    )
    semantic_judgments = [{**agent_judgments[0], "resolved_spans": resolved}]
    review = {
        **review_binding(inventory),
        "schema_version": 2,
        "document_sha256": "a" * 64,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments_sha256": sha256_json(semantic_judgments),
        "semantic_judgments": semantic_judgments,
        "resolved_spans": resolved,
    }

    assert review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=vocabulary,
        expected_document_sha256="a" * 64,
    )


def test_current_semantic_review_rejects_object_only_span_mapping_shape() -> None:
    inventory, review = _accepted_review_fixture()

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_accepts_source_entry_span_mapping_shape() -> None:
    inventory, review = _source_entry_review_fixture()

    assert review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_persisted_review_rechecks_role_even_with_matching_spans_and_digest() -> None:
    inventory, review = _source_entry_review_fixture()
    assert review_uses_current_semantic_shape(
        inventory=inventory, review=review, expected_vocabulary=_vocabulary(),
    )
    judgments = review["semantic_judgments"]
    judgments[0]["parts"][1]["role"] = "body_structure"
    agent_judgments = [
        {key: value for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in judgments
    ]
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=agent_judgments)
    judgments[0]["resolved_spans"] = resolved
    review["resolved_spans"] = resolved
    review["semantic_judgments_sha256"] = sha256_json(judgments)
    assert not review_uses_current_semantic_shape(
        inventory=inventory, review=review, expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_swapped_offsets_and_word_fragments() -> None:
    inventory, review = _source_entry_review_fixture()
    inventory = deepcopy(inventory)
    review = deepcopy(review)
    source_entry = inventory["source_entries"][0]  # type: ignore[index]
    source_entry["provenance"] = [
        {
            "object_id": "obj-label",
            "locator": "/body/p[1]/r[1]",
            "text_span": [0, 5],
        },
        {
            "object_id": "obj-value",
            "locator": "/body/p[1]/r[2]",
            "text_span": [5, 8],
        },
    ]
    spans = review["semantic_judgments"][0]["resolved_spans"]  # type: ignore[index]
    source_snapshot_sha256 = "a" * 64
    forged_inventory_digest = sha256_json(
        {
            "source_snapshot_sha256": source_snapshot_sha256,
            "source_entries": inventory["source_entries"],
        }
    )
    swapped_label_ref = source_span_ref(
        source_snapshot_sha256=source_snapshot_sha256,
        source_span=SourceSpan("source-entry-title", TextSourceExtent(5, 8)),
    )
    swapped_value_ref = source_span_ref(
        source_snapshot_sha256=source_snapshot_sha256,
        source_span=SourceSpan("source-entry-title", TextSourceExtent(0, 5)),
    )
    spans[0].update(
        {
            "span_ref": swapped_label_ref,
            "text_start": 5,
            "text_end": 8,
            "extent": {"kind": "text", "start": 5, "end": 8},
            "expected_source_content": "×××",
            "source_inventory_digest": forged_inventory_digest,
            "word_fragments": [
                {
                    "object_id": "obj-value",
                    "locator": "/body/p[1]/r[2]",
                    "source_text_start": 5,
                    "source_text_end": 8,
                    "text": "×××",
                }
            ],
        }
    )
    spans[1].update(
        {
            "span_ref": swapped_value_ref,
            "slot_ref": f"{swapped_value_ref};field_id=thesis.title.zh",
            "text_start": 0,
            "text_end": 5,
            "extent": {"kind": "text", "start": 0, "end": 5},
            "expected_source_content": "论文题目：",
            "source_inventory_digest": forged_inventory_digest,
            "word_fragments": [
                {
                    "object_id": "obj-label",
                    "locator": "/body/p[1]/r[1]",
                    "source_text_start": 0,
                    "source_text_end": 5,
                    "text": "论文题目：",
                }
            ],
        }
    )
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_parent_range_fragment_expansion() -> None:
    inventory, review = _source_entry_review_fixture()
    review = deepcopy(review)
    span = review["semantic_judgments"][0]["resolved_spans"][0]  # type: ignore[index]
    span["word_fragments"] = [
        {
            "object_id": "obj-parent",
            "locator": "/body/p[1]",
            "source_text_start": 0,
            "source_text_end": 5,
            "object_text_start": 0,
            "object_text_end": 5,
            "text": "论文题目：",
        }
    ]
    span["covered_object_ids"] = ["obj-parent"]
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_overlapping_persisted_extents() -> None:
    inventory, review = _source_entry_review_fixture()
    review = deepcopy(review)
    span = review["semantic_judgments"][0]["resolved_spans"][1]  # type: ignore[index]
    overlapping_ref = source_span_ref(
        source_snapshot_sha256="a" * 64,
        source_span=SourceSpan("source-entry-title", TextSourceExtent(4, 8)),
    )
    span["span_ref"] = overlapping_ref
    span["slot_ref"] = f"{overlapping_ref};field_id=thesis.title.zh"
    span["text_start"] = 4
    span["extent"] = {"kind": "text", "start": 4, "end": 8}
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_source_entry_without_provenance() -> None:
    inventory, review = _source_entry_review_fixture()
    inventory = deepcopy(inventory)
    inventory["source_entries"][0]["provenance"] = []  # type: ignore[index]

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_old_coverage_without_text_spans() -> None:
    inventory, review = _accepted_review_fixture()
    del inventory["reading_blocks"][0]["object_text_spans"]  # type: ignore[index]

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_empty_text_span_mapping() -> None:
    inventory, review = _accepted_review_fixture()
    inventory["reading_blocks"][0]["object_text_spans"] = []  # type: ignore[index]

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_object_only_structural_carrier_coverage() -> None:
    inventory, review = _accepted_review_fixture()
    inventory = deepcopy(inventory)
    inventory["objects"] = [
        {"object_id": "obj-carrier", "type": "paragraph"},
        {"object_id": "obj-title", "type": "run"},
    ]
    inventory["reading_blocks"][0]["covered_object_ids"] = [  # type: ignore[index]
        "obj-carrier",
        "obj-title",
    ]

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )


def test_current_semantic_review_rejects_text_object_missing_span_mapping() -> None:
    inventory, review = _accepted_review_fixture()
    inventory = deepcopy(inventory)
    inventory["objects"].append({"object_id": "obj-extra", "type": "run"})  # type: ignore[union-attr]
    inventory["reading_blocks"][0]["covered_object_ids"].append("obj-extra")  # type: ignore[index,union-attr]

    assert not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=_vocabulary(),
    )
