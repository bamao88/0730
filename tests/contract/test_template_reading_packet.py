from __future__ import annotations

import json

import pytest

from docfit.template.reading_packet import (
    agent_visible_unit_reading_packet,
    build_unit_reading_packet,
)
from docfit.template.source_entries import build_canonical_source_inventory
from docfit.template.unit_source import resolve_unit_partition
from docfit.tools.runtime import sha256_json


def test_auxiliary_story_regions_remain_visible_without_word_locators() -> None:
    packet = {
        "unit": {
            "unit_id": "auxiliary-header",
            "unit_name": "页眉源区域",
            "scope_kind": "auxiliary_story",
            "story_kind": "header",
            "story_regions": [
                {"region_id": "region-a", "source_entry_ids": ["source-entry-a"]},
                {"region_id": "region-b", "source_entry_ids": ["source-entry-b"]},
            ],
            "start_locator": "/header[1]/p[1]",
        },
    }
    visible = agent_visible_unit_reading_packet(packet)
    assert visible["unit"]["story_regions"] == packet["unit"]["story_regions"]
    assert "start_locator" not in visible["unit"]


def test_source_partition_projects_block_order_when_runs_are_not_interleaved() -> None:
    objects = [
        {
            "type": "paragraph",
            "locator": "/body/p[1]",
            "text": "目录格式说明",
            "object_ref": {"object_id": "p1"},
        },
        {
            "type": "paragraph",
            "locator": "/body/p[2]",
            "text": "目录标题",
            "object_ref": {"object_id": "p2"},
        },
        {
            "type": "paragraph",
            "locator": "/body/p[3]",
            "text": "目录缓存行，不属于本 unit",
            "object_ref": {"object_id": "p3"},
        },
        {
            "type": "run",
            "locator": "/body/p[1]/r[1]",
            "text": "目录格式说明",
            "object_ref": {"object_id": "r1"},
        },
        {
            "type": "run",
            "locator": "/body/p[2]/r[1]",
            "text": "目录标题",
            "object_ref": {"object_id": "r2"},
        },
        {
            "type": "run",
            "locator": "/body/p[3]/r[1]",
            "text": "目录缓存行，不属于本 unit",
            "object_ref": {"object_id": "r3"},
        },
    ]

    canonical = build_canonical_source_inventory(
        source_snapshot_sha256="a" * 64, inspected_objects=objects
    )
    entries = canonical.source_entries
    units = resolve_unit_partition(
        canonical,
        [
            {
                "unit_id": "a",
                "unit_name": "title",
                "start_boundary": {"source_entry_id": entries[0].source_entry_id, "edge": "start"},
                "end_boundary": {"source_entry_id": entries[2].source_entry_id, "edge": "start"},
            },
            {
                "unit_id": "b",
                "unit_name": "cache",
                "start_boundary": {"source_entry_id": entries[2].source_entry_id, "edge": "start"},
                "end_boundary": {"source_entry_id": entries[-1].source_entry_id, "edge": "end"},
            },
        ],
    )
    selected_entries = {span["source_entry_id"] for span in units[0]["source_spans"]}
    selected_ids = {
        item.object_id
        for entry in entries
        if entry.source_entry_id in selected_entries
        for item in entry.provenance
    }
    scoped = [obj for obj in objects if obj["object_ref"]["object_id"] in selected_ids]
    packet = build_unit_reading_packet(
        unit={"unit_id": "u-toc-title", "unit_name": "目录标题与格式说明"},
        scoped_objects=scoped,
    )

    assert [item["locator"] for item in scoped] == [
        "/body/p[1]",
        "/body/p[2]",
        "/body/p[1]/r[1]",
        "/body/p[2]/r[1]",
    ]
    assert [item["text"] for item in packet["reading_blocks"]] == [
        "目录格式说明",
        "目录标题",
    ]
    assert [mapping["covered_object_ids"] for mapping in packet["reading_block_mappings"]] == [
        ["p1", "r1"],
        ["p2", "r2"],
    ]
    assert [mapping["order"] for mapping in packet["reading_block_mappings"]] == [1, 2]


def test_unit_reading_packet_requires_unit_id_without_default_range_ids() -> None:
    with pytest.raises(ValueError, match="unit\\.unit_id"):
        build_unit_reading_packet(
            unit={"unit_name": "封面"},
            scoped_objects=[
                {
                    "type": "paragraph",
                    "locator": "/body/p[1]",
                    "text": "论文题目",
                    "object_ref": {"object_id": "p1"},
                }
            ],
        )


def test_unit_reading_packet_records_internal_object_text_spans_for_harness() -> None:
    packet = build_unit_reading_packet(
        unit={"unit_id": "u-cover", "unit_name": "封面"},
        scoped_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "姓名：张三",
                "object_ref": {"object_id": "p1"},
            },
            {
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "text": "姓名：",
                "object_ref": {"object_id": "r1"},
            },
            {
                "type": "run",
                "locator": "/body/p[1]/r[2]",
                "text": "张三",
                "object_ref": {"object_id": "r2"},
            },
        ],
    )

    mapping = packet["reading_block_mappings"][0]

    assert mapping["text"] == "姓名：张三"
    assert mapping["covered_object_ids"] == ["p1", "r1", "r2"]
    assert mapping["object_text_spans"] == [
        {"object_id": "r1", "text_start": 0, "text_end": 3, "text": "姓名："},
        {"object_id": "r2", "text_start": 3, "text_end": 5, "text": "张三"},
    ]
    assert "object_text_spans" not in json.dumps(
        agent_visible_unit_reading_packet(packet),
        ensure_ascii=False,
    )


def test_unit_reading_packet_carries_pre_input_field_vocabulary_without_span_ids() -> None:
    vocabulary = {
        "schema_version": "docfit_pre_input_field_vocabulary_v1",
        "registry": {
            "registry_id": "test.registry",
            "registry_version": "1",
            "sha256": "a" * 64,
        },
        "allowed_field_ids": ["thesis.title.zh"],
        "field_count": 1,
        "fields": [
            {
                "field_id": "thesis.title.zh",
                "label": "中文题目",
                "content_type": "text",
                "usage_affordance": {
                    "selectable_by_agent": True,
                    "source": "pre_input_field_vocabulary",
                    "requires_agent_semantic_part": True,
                    "has_parent_field": False,
                },
            }
        ],
    }
    vocabulary["digest"] = sha256_json(vocabulary)

    packet = build_unit_reading_packet(
        unit={"unit_id": "u-cover", "unit_name": "封面"},
        scoped_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "论文题目",
                "object_ref": {"object_id": "p1"},
            }
        ],
        field_id_vocabulary=vocabulary,
    )

    assert packet["field_id_vocabulary"] == vocabulary
    assert packet["field_vocabulary_digest"] == vocabulary["digest"]
    assert packet["reading_blocks"][0]["block_id"] == "u-cover:block-0001"
    assert packet["reading_blocks"][0]["range_id"] == "u-cover:range-0001"
    assert "span_id" not in json.dumps(packet, ensure_ascii=False)


def test_agent_visible_unit_reading_packet_hides_harness_mapping_ledger() -> None:
    packet = build_unit_reading_packet(
        unit={
            "unit_id": "u-cover",
            "unit_name": "封面",
            "start_locator": "/body/p[1]",
            "end_locator": "/body/p[1]",
            "covered_object_ids": ["p1"],
        },
        scoped_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "论文题目",
                "object_ref": {
                    "object_id": "p1",
                    "expected_fingerprint": "a" * 64,
                },
            }
        ],
        coverage_object_ids=["p1"],
    )

    visible = agent_visible_unit_reading_packet(packet)
    encoded = json.dumps(visible, ensure_ascii=False)

    assert [item["text"] for item in visible["reading_blocks"]] == ["论文题目"]
    assert visible["unit"] == {"unit_id": "u-cover", "unit_name": "封面"}
    assert "reading_block_mappings" not in visible
    for token in (
        "covered_object_ids",
        "covered_object_count",
        "object_text_spans",
        "coverage_required",
        "coverage_contract",
        "harness_maps_to",
        "start_locator",
        "end_locator",
        "scope_ref",
        "locator",
        "object_id",
        "object_ref",
        "target_ref",
        "expected_fingerprint",
        "span_ref",
    ):
        assert token not in encoded


def test_agent_visible_unit_reading_packet_exposes_source_entry_projection() -> None:
    packet = build_unit_reading_packet(
        unit={"unit_id": "u-signature", "unit_name": "签名页"},
        scoped_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "作者签名：",
                "object_ref": {"object_id": "obj-paragraph"},
                "source_entry_id": "source-entry-signature",
            }
        ],
        source_entries=[
            {
                "source_entry_id": "source-entry-signature",
                "text": "作者签名：",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "extent": {"kind": "text", "start": 0, "end": 5},
                "provenance": [
                    {
                        "object_id": "obj-paragraph",
                        "locator": "/body/p[1]",
                        "text_span": [0, 5],
                    }
                ],
            }
        ],
    )

    visible = agent_visible_unit_reading_packet(packet)
    encoded = json.dumps(visible, ensure_ascii=False)

    assert visible["source_entries"] == [
        {
            "source_entry_id": "source-entry-signature",
            "text": "作者签名：",
            "text_length": 5,
            "leading_whitespace_count": 0,
            "trailing_whitespace_count": 0,
            "entry_type": "text",
            "source_order": {"block": 1, "inline": 0},
            "semantic_cues": [
                "signature_area_candidate",
                "field_slot_candidate",
                "label_candidate",
            ],
        }
    ]
    for token in (
        "provenance",
        "object_id",
        "object_ref",
        "locator",
        "fingerprint",
        "extent",
        "covered_source_entry_ids",
        "source_entry_text_spans",
    ):
        assert token not in encoded


def test_agent_visible_source_entry_makes_boundary_whitespace_explicit() -> None:
    packet = {
        "source_entries": [
            {
                "source_entry_id": "source-entry-spaced",
                "text": "\t标题  ",
            }
        ]
    }

    visible = agent_visible_unit_reading_packet(packet)

    assert visible["source_entries"] == [
        {
            "source_entry_id": "source-entry-spaced",
            "text": "\t标题  ",
            "text_length": 5,
            "leading_whitespace_count": 1,
            "trailing_whitespace_count": 2,
            "leading_whitespace_codepoints": ["U+0009"],
            "trailing_whitespace_codepoints": ["U+0020 × 2"],
        }
    ]


def test_agent_visible_source_entry_exposes_render_sensitive_codepoints() -> None:
    packet = {
        "source_entries": [
            {
                "source_entry_id": "source-entry-degree-type",
                "text": "\uf06f 学术学位    \uf0fe 专业学位",
            }
        ]
    }

    visible = agent_visible_unit_reading_packet(packet)

    assert visible["source_entries"][0]["render_sensitive_codepoints"] == [
        {"offset": 0, "codepoint": "U+F06F", "unicode_category": "Co"},
        {"offset": 10, "codepoint": "U+F0FE", "unicode_category": "Co"},
    ]
    assert visible["source_entries"][0]["text_length"] == 16


def test_unit_reading_packet_routes_blank_coverage_objects_to_layout_context() -> None:
    packet = build_unit_reading_packet(
        unit={"unit_id": "u-cover", "unit_name": "封面"},
        scoped_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "",
                "object_ref": {"object_id": "p1"},
            },
            {
                "type": "paragraph",
                "locator": "/body/p[2]",
                "text": "学生姓名",
                "object_ref": {"object_id": "p2"},
            },
        ],
        coverage_object_ids=["p1", "p2"],
    )

    assert [item["text"] for item in packet["reading_blocks"]] == ["学生姓名"]
    assert [mapping["covered_object_ids"] for mapping in packet["reading_block_mappings"]] == [
        ["p2"]
    ]
    assert packet["layout_context"][0]["coverage_required"] is False
    assert packet["layout_context"][0]["covered_object_count"] == 1
    assert "blank_layout_candidate" in packet["layout_context"][0]["semantic_cues"]
