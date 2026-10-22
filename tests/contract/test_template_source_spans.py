from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest

from docfit.template.harness import _decode_whitespace_parts
from docfit.template.source_entries import build_canonical_source_inventory
from docfit.template.source_spans import (
    SourceSpan,
    SourceSpanResolutionError,
    TextSourceExtent,
    WholeEntrySourceExtent,
    parse_source_span_ref,
    resolve_semantic_judgments,
    resolve_source_span,
    source_span_ref,
)
from tests.support.source_identity import source_partition

SOURCE_HASH = "a" * 64
ENTRY_ID = "source-entry-person"


def _inventory() -> dict[str, object]:
    inventory = {
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": ENTRY_ID,
                "text": "姓名：张三",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-parent",
                        "locator": "/body/p[1]",
                        "text_span": [0, 5],
                    },
                    {
                        "object_id": "obj-label",
                        "locator": "/body/p[1]/r[1]",
                        "text_span": [0, 3],
                    },
                    {
                        "object_id": "obj-name",
                        "locator": "/body/p[1]/r[2]",
                        "text_span": [3, 5],
                    },
                ],
            }
        ],
    }
    source_partition(inventory)
    return inventory


def _judgment() -> dict[str, object]:
    return {
        "source_entry_id": ENTRY_ID,
        "parts": [
            {"text": "姓名：", "role": "fixed_label"},
            {"text": "张三", "role": "fill_slot", "field_id": "author.name.zh"},
        ],
    }


def _codes(error: SourceSpanResolutionError) -> set[str]:
    return {str(item.get("code")) for item in error.blockers}


def test_exact_source_span_resolver_returns_ordered_leaf_word_fragments() -> None:
    resolved = resolve_semantic_judgments(
        inventory=_inventory(),
        judgments=[_judgment()],
    )

    assert [(item["text_start"], item["text_end"]) for item in resolved] == [
        (0, 3),
        (3, 5),
    ]
    assert [item["expected_source_content"] for item in resolved] == ["姓名：", "张三"]
    assert [
        [fragment["object_id"] for fragment in item["word_fragments"]] for item in resolved
    ] == [["obj-label"], ["obj-name"]]
    assert all(item["source_snapshot_sha256"] == SOURCE_HASH for item in resolved)


def test_boundary_transport_preserves_exact_span_and_single_slot_identity() -> None:
    inventory = _inventory()
    entry = inventory["source_entries"][0]  # type: ignore[index]
    entry["text"] = "姓名： \t张三\u00a0"
    entry["provenance"] = [{
        "object_id": "obj-parent", "locator": "/body/p[1]", "text_span": [0, len(entry["text"])],
    }]
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    literal = _judgment()
    literal["parts"][1]["text"] = " \t张三\u00a0"
    encoded = _judgment()
    encoded["parts"][1].update(
        leading_whitespace=[{"codepoint": "U+0020", "count": 1},
                            {"codepoint": "U+0009", "count": 1}],
        trailing_whitespace=[{"codepoint": "U+00A0", "count": 1}],
    )
    decoded, feedback = _decode_whitespace_parts([encoded])
    assert feedback is None
    expected = resolve_semantic_judgments(inventory=inventory, judgments=[literal])
    actual = resolve_semantic_judgments(inventory=inventory, judgments=decoded)
    assert actual == expected
    assert sum("slot_ref" in span for span in actual) == 1
    # Incorrect explicit counts are still rejected by the exact source gate.
    encoded["parts"][1]["leading_whitespace"][0]["count"] = 2
    decoded, feedback = _decode_whitespace_parts([encoded])
    assert feedback is None
    with pytest.raises(SourceSpanResolutionError):
        resolve_semantic_judgments(inventory=inventory, judgments=decoded)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda value: value["parts"][1].update(text="李四"), "ordered_part_text_mismatch"),
        (
            lambda value: value.update(source_entry_id="source-entry-other"),
            "ordered_part_source_entry_unknown",
        ),
        (lambda value: value["parts"].pop(0), "ordered_part_text_mismatch"),
        (lambda value: value["parts"].pop(), "ordered_part_text_gap"),
    ],
)
def test_ordered_parts_reject_wrong_text_entry_overlap_or_omission(
    mutation: Callable[[dict[str, object]], object],
    expected_code: str,
) -> None:
    judgment = _judgment()
    mutation(judgment)

    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(inventory=_inventory(), judgments=[judgment])

    assert expected_code in _codes(raised.value)


def test_ordered_parts_reject_duplicate_source_entry_judgment() -> None:
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(
            inventory=_inventory(),
            judgments=[_judgment(), deepcopy(_judgment())],
        )

    assert "source_span_duplicate_entry_judgment" in _codes(raised.value)


@pytest.mark.parametrize("replacement", ["姓民：", "姓民", "姓名：多余"])
def test_bad_prefix_does_not_invent_suffix_mismatches(replacement: str) -> None:
    judgment = _judgment()
    judgment["parts"][0]["text"] = replacement
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(inventory=_inventory(), judgments=[judgment])

    assert len(raised.value.blockers) == 1
    blocker = raised.value.blockers[0]
    assert blocker["code"] == "ordered_part_text_mismatch"
    assert blocker["field"] == "semantic_judgments[0].parts[0]"
    # Once the prefix is repaired, remaining errors must still be checked.
    judgment["parts"][0]["text"] = "姓名："
    judgment["parts"][1]["text"] = "李四"
    with pytest.raises(SourceSpanResolutionError) as suffix:
        resolve_semantic_judgments(inventory=_inventory(), judgments=[judgment])
    assert suffix.value.blockers[0]["field"] == "semantic_judgments[0].parts[1]"
    assert suffix.value.blockers[0]["expected_text"] == "张三"
    judgment["parts"][1]["text"] = "张三"
    assert len(resolve_semantic_judgments(inventory=_inventory(), judgments=[judgment])) == 2


@pytest.mark.parametrize(
    ("source", "submitted", "expected_character", "submitted_character"),
    [("“字”", '"字”', "“", '"'), ("A\u00a0B", "A B", "\u00a0", " "), ("A", "AX", "", "X")],
)
def test_mismatch_identifies_exact_character_or_end_of_text(
    source: str, submitted: str, expected_character: str, submitted_character: str
) -> None:
    inventory = _inventory()
    entry = inventory["source_entries"][0]  # type: ignore[index]
    entry["text"] = source
    entry["provenance"] = [
        {"object_id": "obj-parent", "locator": "/body/p[1]", "text_span": [0, len(source)]}
    ]
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(
            inventory=inventory,
            judgments=[
                {"source_entry_id": ENTRY_ID, "parts": [{"text": submitted, "role": "cleanup"}]}
            ],
        )
    detail = raised.value.blockers[0]["first_difference"]
    for name, character in (("expected", expected_character), ("submitted", submitted_character)):
        assert detail[name] == {
            "character": character,
            "codepoint": f"U+{ord(character):04X}" if character else None,
            "end_of_text": not character,
        }


def test_mismatch_reports_expected_leading_whitespace_codepoints() -> None:
    inventory = _inventory()
    entry = inventory["source_entries"][0]  # type: ignore[index]
    entry["text"] = "    姓名：张三"  # type: ignore[index]
    judgment = _judgment()

    entry["provenance"] = [
        {"object_id": "obj-parent", "locator": "/body/p[1]", "text_span": [0, len(entry["text"])]}
    ]
    inventory.pop("canonical_source_inventory")
    source_partition(inventory)
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(inventory=inventory, judgments=[judgment])

    blocker = raised.value.blockers[0]
    assert blocker["code"] == "ordered_part_text_mismatch"
    assert blocker["mismatch_offset"] == 0
    assert blocker["expected_leading_whitespace_count"] == 4
    assert blocker["expected_leading_whitespace_codepoints"] == ["U+0020 × 4"]


def _projected_canonical_inventory() -> tuple[dict[str, object], str]:
    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "姓名：张三",
            "object_ref": {
                "document_sha256": SOURCE_HASH,
                "object_id": "obj-person",
                "expected_fingerprint": "1" * 64,
            },
        },
        {
            "type": "paragraph",
            "locator": "/body/p[2]",
            "text": "下一页",
            "object_ref": {
                "document_sha256": SOURCE_HASH,
                "object_id": "obj-next-page",
                "expected_fingerprint": "2" * 64,
            },
        },
    ]
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=SOURCE_HASH,
        inspected_objects=objects,
    )
    selected = canonical.source_entries[0]
    inventory = {
        "document_sha256": SOURCE_HASH,
        "objects": [
            {**obj, "source_entry_id": entry.source_entry_id}
            for obj, entry in zip(objects, canonical.source_entries, strict=True)
        ],
        "source_entries": [entry.to_json() for entry in canonical.source_entries],
        "canonical_source_inventory": canonical.to_json(),
    }
    source_partition(inventory)
    return inventory, selected.source_entry_id


def test_unit_projection_resolves_against_one_full_canonical_inventory() -> None:
    inventory, source_entry_id = _projected_canonical_inventory()

    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[
            {
                "source_entry_id": source_entry_id,
                "parts": [
                    {"text": "姓名：", "role": "fixed_label"},
                    {"text": "张三", "role": "fill_slot", "field_id": "author.name.zh"},
                ],
            },
            {
                "source_entry_id": inventory["source_entries"][1]["source_entry_id"],
                "parts": [{"text": "下一页", "role": "fixed_label"}],
            },
        ],
    )

    assert len(resolved) == 3
    assert (
        resolved[0]["source_inventory_digest"]
        == inventory["canonical_source_inventory"]["inventory_digest"]
    )  # type: ignore[index]


def test_bad_prefix_does_not_skip_checks_on_other_entries() -> None:
    inventory, first_id = _projected_canonical_inventory()
    second_id = inventory["source_entries"][1]["source_entry_id"]  # type: ignore[index]
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(
            inventory=inventory,
            judgments=[
                {"source_entry_id": first_id, "parts": [{"text": "错误", "role": "cleanup"}]},
                {"source_entry_id": second_id, "parts": [{"text": "下一", "role": "fixed_label"}]},
            ],
        )
    assert [(b["source_entry_id"], b["code"]) for b in raised.value.blockers] == [
        (first_id, "ordered_part_text_mismatch"),
        (second_id, "ordered_part_text_gap"),
    ]


def test_unit_projection_rejects_entry_changed_after_canonical_inventory() -> None:
    inventory, source_entry_id = _projected_canonical_inventory()
    inventory["source_entries"][0]["text"] = "姓名：李四"  # type: ignore[index]

    with pytest.raises(
        ValueError,
        match="preserve every complete canonical entry",
    ):
        resolve_semantic_judgments(
            inventory=inventory,
            judgments=[
                {
                    "source_entry_id": source_entry_id,
                    "parts": [{"text": "姓名：李四", "role": "fixed_label"}],
                }
            ],
        )


def test_source_span_rejects_out_of_bounds() -> None:
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_source_span(
            inventory=_inventory(),
            source_span=SourceSpan(ENTRY_ID, TextSourceExtent(3, 6)),
        )

    assert _codes(raised.value) == {"source_span_out_of_bounds"}


def test_source_span_rejects_ambiguous_equal_precision_fragments() -> None:
    inventory = _inventory()
    provenance = inventory["source_entries"][0]["provenance"]  # type: ignore[index]
    provenance.append(
        {
            "object_id": "obj-name-copy",
            "locator": "/body/p[1]/r[3]",
            "text_span": [3, 5],
        }
    )

    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_source_span(
            inventory=inventory,
            source_span=SourceSpan(ENTRY_ID, TextSourceExtent(3, 5)),
        )

    assert _codes(raised.value) == {"source_span_fragment_ambiguous"}


def test_source_span_rejects_fragment_gap_without_parent_fallback() -> None:
    inventory = _inventory()
    provenance = inventory["source_entries"][0]["provenance"]  # type: ignore[index]
    provenance[:] = [item for item in provenance if item["object_id"] != "obj-parent"]
    provenance[1]["text_span"] = [4, 5]

    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_source_span(
            inventory=inventory,
            source_span=SourceSpan(ENTRY_ID, TextSourceExtent(3, 5)),
        )

    assert _codes(raised.value) == {"source_span_fragment_gap"}


def _structural_inventory() -> dict[str, object]:
    inventory = {
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": "source-entry-break",
                "text": "",
                "entry_type": "break",
                "source_order": {"block": 2, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-break",
                        "locator": "/body/p[2]/r[1]/br[1]",
                        "extent": {"kind": "whole_entry"},
                    }
                ],
            }
        ],
    }
    source_partition(inventory)
    return inventory


def test_structural_whole_entry_is_explicitly_judged_and_resolved() -> None:
    resolved = resolve_semantic_judgments(
        inventory=_structural_inventory(),
        judgments=[
            {
                "source_entry_id": "source-entry-break",
                "parts": [{"text": "", "role": "style_only"}],
            }
        ],
    )

    assert resolved == [
        {
            "span_ref": (
                "source_entry_id=source-entry-break;extent=whole_entry;"
                f"source_snapshot_sha256={SOURCE_HASH}"
            ),
            "scope": {"source_entry_id": "source-entry-break"},
            "judgment_index": 0,
            "part_index": 0,
            "role": "style_only",
            "text": "",
            "source_entry_id": "source-entry-break",
            "extent": {"kind": "whole_entry"},
            "expected_source_content": "",
            "source_snapshot_sha256": SOURCE_HASH,
            "source_inventory_digest": resolved[0]["source_inventory_digest"],
            "word_fragments": [
                {
                    "object_id": "obj-break",
                    "locator": "/body/p[2]/r[1]/br[1]",
                    "text": "",
                    "extent": {"kind": "whole_entry"},
                }
            ],
            "covered_object_ids": ["obj-break"],
        }
    ]
    parsed = parse_source_span_ref(resolved[0]["span_ref"])
    assert parsed == (
        SOURCE_HASH,
        SourceSpan("source-entry-break", WholeEntrySourceExtent()),
    )


def test_empty_whole_entry_can_bind_one_exact_fill_slot() -> None:
    resolved = resolve_semantic_judgments(
        inventory=_structural_inventory(),
        judgments=[
            {
                "source_entry_id": "source-entry-break",
                "parts": [
                    {
                        "text": "",
                        "role": "fill_slot",
                        "field_id": "author.name.zh",
                    }
                ],
            }
        ],
    )

    assert resolved[0]["extent"] == {"kind": "whole_entry"}
    assert resolved[0]["field_id"] == "author.name.zh"
    assert resolved[0]["slot_ref"] == (f"{resolved[0]['span_ref']};field_id=author.name.zh")


def test_empty_part_cannot_turn_a_nonempty_entry_into_a_whole_entry_slot() -> None:
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_semantic_judgments(
            inventory=_inventory(),
            judgments=[
                {
                    "source_entry_id": ENTRY_ID,
                    "parts": [
                        {
                            "text": "",
                            "role": "fill_slot",
                            "field_id": "author.name.zh",
                        }
                    ],
                }
            ],
        )

    assert _codes(raised.value) == {
        "ordered_part_empty_for_text_entry",
        "ordered_part_text_gap",
    }


def test_blank_paragraph_with_nested_empty_runs_resolves_to_outer_carrier() -> None:
    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[29]",
            "text": "",
            "object_ref": {
                "document_sha256": SOURCE_HASH,
                "object_id": "obj-paragraph",
                "expected_fingerprint": "1" * 64,
            },
        },
        {
            "type": "run",
            "locator": "/body/p[29]/r[1]",
            "text": "",
            "object_ref": {
                "document_sha256": SOURCE_HASH,
                "object_id": "obj-run-1",
                "expected_fingerprint": "2" * 64,
            },
        },
        {
            "type": "run",
            "locator": "/body/p[29]/r[2]",
            "text": "",
            "object_ref": {
                "document_sha256": SOURCE_HASH,
                "object_id": "obj-run-2",
                "expected_fingerprint": "3" * 64,
            },
        },
    ]
    canonical = build_canonical_source_inventory(
        source_snapshot_sha256=SOURCE_HASH,
        inspected_objects=objects,
    )
    entry = canonical.source_entries[0]

    inventory = {"document_sha256": SOURCE_HASH, "source_entries": [entry.to_json()]}
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[
            {
                "source_entry_id": entry.source_entry_id,
                "parts": [{"text": "", "role": "style_only"}],
            }
        ],
    )

    assert [fragment["object_id"] for fragment in resolved[0]["word_fragments"]] == [
        "obj-paragraph"
    ]


def test_text_extent_cannot_target_structural_whole_entry() -> None:
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_source_span(
            inventory=_structural_inventory(),
            source_span=SourceSpan("source-entry-break", TextSourceExtent(0, 1)),
        )

    assert _codes(raised.value) == {"source_span_out_of_bounds"}


def test_whole_entry_extent_cannot_expand_text_entry() -> None:
    with pytest.raises(SourceSpanResolutionError) as raised:
        resolve_source_span(
            inventory=_inventory(),
            source_span=SourceSpan(ENTRY_ID, WholeEntrySourceExtent()),
        )

    assert _codes(raised.value) == {"source_span_extent_kind_mismatch"}


def test_whole_entry_ref_round_trips_without_fake_offsets() -> None:
    span = SourceSpan("source-entry-break", WholeEntrySourceExtent())
    ref = source_span_ref(source_snapshot_sha256=SOURCE_HASH, source_span=span)

    assert "part_index" not in ref
    assert "text[" not in ref
    assert parse_source_span_ref(ref) == (SOURCE_HASH, span)
