from __future__ import annotations

import json
from copy import deepcopy

import pytest

from docfit.template.harness import TemplateHarnessService, _decode_whitespace_parts
from docfit.template.judgment_shape import (
    MECHANICAL_FEEDBACK_V1,
    validate_ordered_semantic_parts,
)
from tests.support.source_identity import persist_source_identity, source_partition

SOURCE_HASH = "39631bb5e5dc9326b23f8c00bf43440a84ce711315c6b799de554c56aa04d133"


def _failure(result: dict[str, object]) -> dict[str, object]:
    assert result["schema_version"] == MECHANICAL_FEEDBACK_V1
    assert result["status"] == "needs_input"
    feedback = result["feedback"]
    assert isinstance(feedback, dict)
    assert feedback["mechanical"] is True
    assert feedback["semantic_authority"] is False
    failure = result["failure"]
    assert isinstance(failure, dict)
    return failure


def test_whitespace_transport_decodes_consecutive_mixed_codepoint_runs() -> None:
    decoded, feedback = _decode_whitespace_parts(
        [
            {
                "source_entry_id": "source-entry-mixed-space",
                "parts": [
                    {
                        "text": "",
                        "role": "manual_region",
                        "whitespace": {"codepoint": "U+00A0", "count": 3},
                    },
                    {
                        "text": "",
                        "role": "manual_region",
                        "whitespace": {"codepoint": "U+0020", "count": 1},
                    },
                ],
            }
        ]
    )

    assert feedback is None
    assert [part["text"] for part in decoded[0]["parts"]] == ["\u00a0" * 3, " "]
    assert all("whitespace" not in part for part in decoded[0]["parts"])


def test_boundary_whitespace_stays_on_one_semantic_part() -> None:
    judgments = [{"source_entry_id": "source-entry-test", "parts": [{
        "text": "Name", "role": "fill_slot", "field_id": "author.name.en",
        "leading_whitespace": [
            {"codepoint": "U+0020", "count": 1}, {"codepoint": "U+0009", "count": 2},
        ],
        "trailing_whitespace": [{"codepoint": "U+00A0", "count": 1}],
    }]}]
    before = deepcopy(judgments)
    decoded, feedback = _decode_whitespace_parts(judgments)
    assert feedback is None
    assert judgments == before
    assert decoded == [{"source_entry_id": "source-entry-test", "parts": [{
        "text": " \t\tName\u00a0", "role": "fill_slot", "field_id": "author.name.en",
    }]}]


@pytest.mark.parametrize("part", [
    {"text": " Name", "leading_whitespace": [{"codepoint": "U+0020", "count": 1}]},
    {"text": "", "leading_whitespace": [{"codepoint": "U+0020", "count": 1}]},
    {"text": "Name", "leading_whitespace": []},
    {"text": "Name", "trailing_whitespace": [{"codepoint": "U+0041", "count": 1}]},
    {"text": "Name", "leading_whitespace": [{"codepoint": "U+0020", "count": True}]},
    {"text": "Name", "leading_whitespace": [{"codepoint": "U+110000", "count": 1}]},
    {"text": "Name", "leading_whitespace": [{"codepoint": "U+0020", "count": 0}]},
    {"text": "", "whitespace": {"codepoint": "U+0020", "count": 1},
     "trailing_whitespace": [{"codepoint": "U+0020", "count": 1}]},
])
def test_boundary_transport_rejects_conflicts_without_guessing(part) -> None:
    judgment = {"source_entry_id": "source-entry-test", "parts": [{**part, "role": "style_only"}]}
    before = deepcopy(judgment)
    _, feedback = _decode_whitespace_parts([judgment])
    assert feedback is not None
    assert feedback["blockers"][0]["code"] == "ordered_part_whitespace_transport_invalid"
    assert judgment == before


@pytest.mark.parametrize(
    ("scope_key", "scope_value"),
    (
        ("reading_block_id", "u-cover:block-0001"),
        ("reading_range_id", "u-cover:range-0001"),
    ),
)
def test_p0_n06_ordered_semantic_parts_rejects_legacy_reading_scope(
    scope_key: str,
    scope_value: str,
) -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "scope": {scope_key: scope_value},
                "parts": [
                    {"text": "作者：", "role": "fixed_label"},
                    {
                        "text": "张三",
                        "role": "fill_slot",
                        "field_id": "author.name.zh",
                    },
                ],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=(),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "legacy_reading_scope_unsupported"


def test_ordered_semantic_parts_accepts_source_entry_id_from_unit_packet() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-cover-title",
                "parts": [
                    {"text": "论文题目：", "role": "fixed_label"},
                    {
                        "text": "玉米生长研究",
                        "role": "fill_slot",
                        "field_id": "thesis.title.zh",
                    },
                ],
            }
        ],
        allowed_field_ids=("thesis.title.zh",),
        source_entry_ids=("source-entry-cover-title",),
    )

    assert result["status"] == "ok"
    assert result["failure"] is None


def test_ordered_semantic_parts_rejects_fabricated_source_entry_id() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-not-from-packet",
                "parts": [{"text": "论文题目", "role": "fixed_label"}],
            }
        ],
        allowed_field_ids=("thesis.title.zh",),
        source_entry_ids=("source-entry-cover-title",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "ordered_semantic_source_entry_unknown"


def test_ordered_semantic_parts_rejects_source_entry_id_mixed_with_legacy_scope() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-cover-title",
                "scope": {"reading_block_id": "u-cover:block-0001"},
                "parts": [{"text": "论文题目", "role": "fixed_label"}],
            }
        ],
        allowed_field_ids=("thesis.title.zh",),
        source_entry_ids=("source-entry-cover-title",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "legacy_reading_scope_unsupported"


def test_ordered_semantic_parts_rejects_fill_slot_with_leading_label_delimiter() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-abstract-keywords",
                "parts": [
                    {"text": "KEY WORDS", "role": "fixed_label"},
                    {
                        "text": "：×××；×××",
                        "role": "fill_slot",
                        "field_id": "keywords.en",
                    },
                ],
            }
        ],
        allowed_field_ids=("keywords.en",),
        source_entry_ids=("source-entry-abstract-keywords",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "fill_slot_includes_label_delimiter"


def test_ordered_semantic_parts_rejects_legacy_field_aliases_and_agent_ids() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-author-name",
                "judgment_id": "agent-authored",
                "covered_reading_block_ids": ["u-cover:block-0001"],
                "registry_field": "author.name.zh",
                "object_text_spans": [],
                "source_content_id": "legacy-content-1",
                "source_object_ids": ["obj-000000000000000000000001"],
                "parts": [{"text": "张三", "role": "fill_slot", "field_id": "author.name.zh"}],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=("source-entry-author-name",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    blocker = result["blockers"][0]
    assert blocker["code"] == "agent_authored_legacy_or_internal_id"
    assert blocker["forbidden_fields"] == [
        "covered_reading_block_ids",
        "judgment_id",
        "object_text_spans",
        "registry_field",
        "source_content_id",
        "source_object_ids",
    ]


def test_ordered_semantic_parts_rejects_unknown_fields_and_agent_spans() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-author-name",
                "parts": [
                    {
                        "text": "张三",
                        "role": "fill_slot",
                        "field_id": "author.signature",
                        "span_id": "agent-span-1",
                    }
                ],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=("source-entry-author-name",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    codes = [blocker["code"] for blocker in result["blockers"]]
    assert "agent_authored_legacy_or_internal_id" in codes
    assert "field_id_not_in_input_vocabulary" in codes


def test_ordered_semantic_parts_rejects_agent_authored_resolved_spans() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-cover",
                "parts": [{"text": "封面", "role": "manual_region"}],
                "resolved_spans": [
                    {
                        "span_ref": "reading_block_id=u-cover:block-0001;part_index=0",
                        "part_index": 0,
                    }
                ],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=("source-entry-cover",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "agent_authored_legacy_or_internal_id"
    assert result["blockers"][0]["forbidden_fields"] == ["resolved_spans"]


@pytest.mark.parametrize(
    "part_patch",
    (
        {"resolved_spans": [{"span_ref": "reading_block_id=u-cover:block-0001;part_index=0"}]},
        {"covered_object_ids": ["obj-000000000000000000000001"]},
        {"source_content_id": "legacy-content-1"},
        {"source_object_ids": ["obj-000000000000000000000001"]},
        {"reading_block_id": "u-cover:block-0001"},
        {"candidate_hash": "a" * 64},
        {"locator": "/body/p[1]"},
        {"object_text_spans": [{"object_id": "obj-1", "text_start": 0, "text_end": 2}]},
    ),
)
def test_ordered_semantic_parts_rejects_agent_authored_part_internal_refs(
    part_patch: dict[str, object],
) -> None:
    part: dict[str, object] = {"text": "封面", "role": "manual_region"}
    part.update(part_patch)
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-cover",
                "parts": [part],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=("source-entry-cover",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "agent_authored_legacy_or_internal_id"
    assert result["blockers"][0]["forbidden_fields"] == sorted(part_patch)


def test_ordered_semantic_parts_rejects_agent_authored_part_index() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-author-name",
                "semantic_part_index": 0,
                "parts": [
                    {
                        "text": "张三",
                        "role": "fill_slot",
                        "field_id": "author.name.zh",
                        "semantic_part_index": 12,
                    }
                ],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=("source-entry-author-name",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    blockers = result["blockers"]
    assert blockers[0]["code"] == "agent_authored_legacy_or_internal_id"
    assert blockers[0]["forbidden_fields"] == ["semantic_part_index"]
    assert blockers[1]["code"] == "agent_authored_legacy_or_internal_id"
    assert blockers[1]["forbidden_fields"] == ["semantic_part_index"]


def test_ordered_semantic_parts_rejects_missing_source_entry_and_misplaced_field_id() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "parts": [
                    {
                        "text": "固定校名",
                        "role": "fixed_label",
                        "field_id": "author.name.zh",
                    }
                ],
            }
        ],
        allowed_field_ids=("author.name.zh",),
        source_entry_ids=("source-entry-cover",),
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    codes = [blocker["code"] for blocker in result["blockers"]]
    assert "ordered_semantic_source_entry_missing" in codes
    assert "ordered_semantic_part_field_forbidden" in codes


def test_ordered_semantic_parts_allows_empty_text_for_structural_non_field_role() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-break",
                "parts": [{"text": "", "role": "style_only"}],
            }
        ],
        allowed_field_ids=["thesis.title.zh"],
        source_entry_ids=["source-entry-break"],
    )

    assert result["status"] == "ok"


def test_ordered_semantic_parts_allows_empty_text_for_field_role_before_extent_resolution() -> None:
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": "source-entry-break",
                "parts": [
                    {
                        "text": "",
                        "role": "fill_slot",
                        "field_id": "thesis.title.zh",
                    }
                ],
            }
        ],
        allowed_field_ids=["thesis.title.zh"],
        source_entry_ids=["source-entry-break"],
    )

    assert result["status"] == "ok"


def test_r2_harness_returns_ordered_shape_feedback_before_coverage_feedback(
    tmp_path,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 论文中文题目",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    harness = TemplateHarnessService(task_root=task_root)
    current = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "objects": [
            {
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-000000000000000000000001",
                    "expected_fingerprint": SOURCE_HASH,
                },
            }
        ],
    }
    current.pop("reading_blocks", None)
    current["source_entries"] = [
        {
            "source_entry_id": f"source-entry-{index}",
            "text": "source",
            "entry_type": "text",
            "source_order": {"block": index, "inline": 0},
            "provenance": [
                {
                    "object_id": obj["object_ref"]["object_id"],
                    "object_ref": obj["object_ref"],
                    "locator": obj["locator"],
                    "fingerprint": obj["object_ref"]["expected_fingerprint"],
                    "text_span": [0, 6],
                }
            ],
        }
        for index, obj in enumerate(current["objects"], 1)
    ]
    for index, obj in enumerate(current["objects"], 1):
        obj["source_entry_id"] = f"source-entry-{index}"
    source_partition(current)
    persist_source_identity(task_root, current)
    harness.handle(current)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "judgment_id": "j-fill",
                    "responsibility": "fill_interface",
                    "covered_object_ids": ["obj-000000000000000000000001"],
                }
            ],
        }
    )

    failure = _failure(result)
    assert failure["code"] == "ordered_semantic_parts_invalid"
    assert result["blockers"][0]["code"] == "agent_authored_legacy_or_internal_id"
    assert "covered_object_ids" in result["blockers"][0]["forbidden_fields"]


def test_template_harness_resolves_source_entry_parts_to_entry_spans(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    source_entry_id = "source-entry-author-name"
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": "姓名：张三",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-paragraph",
                        "locator": "/body/p[1]",
                        "text_span": [0, 5],
                    },
                    {
                        "object_id": "obj-label",
                        "locator": "/body/p[1]/r[1]",
                        "text_span": [0, 3],
                    },
                    {
                        "object_id": "obj-value",
                        "locator": "/body/p[1]/r[2]",
                        "text_span": [3, 5],
                    },
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": source_entry_id,
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-paragraph",
                    "expected_fingerprint": "a" * 64,
                },
            },
            {
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-label",
                    "expected_fingerprint": "b" * 64,
                },
            },
            {
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": "/body/p[1]/r[2]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-value",
                    "expected_fingerprint": "c" * 64,
                },
            },
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [
                        {"text": "姓名：", "role": "fixed_label"},
                        {
                            "text": "张三",
                            "role": "fill_slot",
                            "field_id": "author.name.zh",
                        },
                    ],
                }
            ],
        }
    )

    assert result["status"] == "ok"
    stored = json.loads(
        (task_root / "work/.docfit/harness/semantic-judgments.json").read_text(encoding="utf-8")
    )
    resolved_spans = stored["resolved_spans"]
    assert [span["span_ref"] for span in resolved_spans] == [
        (
            f"source_entry_id={source_entry_id};extent=text[0:3];"
            f"source_snapshot_sha256={SOURCE_HASH}"
        ),
        (
            f"source_entry_id={source_entry_id};extent=text[3:5];"
            f"source_snapshot_sha256={SOURCE_HASH}"
        ),
    ]
    assert [span["source_entry_id"] for span in resolved_spans] == [
        source_entry_id,
        source_entry_id,
    ]
    assert [(span["text_start"], span["text_end"]) for span in resolved_spans] == [
        (0, 3),
        (3, 5),
    ]
    assert resolved_spans[1]["slot_ref"] == (
        f"{resolved_spans[1]['span_ref']};field_id=author.name.zh"
    )


def test_template_harness_rejects_source_entry_part_text_not_in_entry(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    source_entry_id = "source-entry-author-name"
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": "姓名：张三",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-paragraph",
                        "locator": "/body/p[1]",
                        "text_span": [0, 5],
                    }
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": source_entry_id,
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-paragraph",
                    "expected_fingerprint": "a" * 64,
                },
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [{"text": "李四", "role": "fixed_label"}],
                }
            ],
        }
    )

    assert result["schema_version"] == 2
    assert result["status"] == "needs_input"
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert failure["code"] == "template_ordered_span_resolution_incomplete"
    assert result["blockers"][0]["code"] == "ordered_part_text_mismatch"


def test_template_harness_reports_invisible_trailing_whitespace_gap(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    source_entry_id = "source-entry-format-note"
    source_text = "格式说明     "
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": source_text,
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-note",
                        "locator": "/body/p[1]",
                        "text_span": [0, len(source_text)],
                    }
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": source_entry_id,
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-note",
                    "expected_fingerprint": "a" * 64,
                },
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [{"text": "格式说明", "role": "style_only"}],
                }
            ],
        }
    )

    assert result["status"] == "needs_input"
    blocker = result["blockers"][0]
    assert blocker == {
        "code": "ordered_part_text_gap",
        "field": "semantic_judgments[0]",
        "message": "Ordered parts must cover the complete source entry without omissions.",
        "source_entry_id": source_entry_id,
        "text_start": 4,
        "text_end": 9,
        "uncovered_text": "     ",
        "source_text_length": 9,
        "covered_text_length": 4,
        "uncovered_text_length": 5,
        "uncovered_whitespace_codepoints": ["U+0020 × 5"],
    }

    accepted = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [
                        {"text": "格式说明", "role": "style_only"},
                        {
                            "text": "",
                            "role": "style_only",
                            "whitespace": {"codepoint": "U+0020", "count": 5},
                        },
                    ],
                }
            ],
        }
    )

    assert accepted["status"] == "ok"
    stored = json.loads(
        (task_root / "work/.docfit/harness/semantic-judgments.json").read_text(encoding="utf-8")
    )
    stored_part = stored["semantic_judgments"][0]["parts"][1]
    assert stored_part["text"] == "     "
    assert "whitespace" not in stored_part

    whole = harness.handle({
        "action": "submit_semantic_judgments", "document_sha256": SOURCE_HASH,
        "semantic_judgments": [{"source_entry_id": source_entry_id,
                                "parts": [{"whole_entry": True, "role": "style_only"}]}],
    })
    assert whole["status"] == "ok"
    whole_stored = json.loads(
        (task_root / "work/.docfit/harness/semantic-judgments.json").read_text(encoding="utf-8")
    )
    assert whole_stored["semantic_judgments"][0]["parts"] == [
        {"text": "格式说明     ", "role": "style_only"},
    ]
    assert stored["resolved_spans"][1]["extent"] == {
        "kind": "text",
        "start": 4,
        "end": 9,
    }


@pytest.mark.parametrize(
    "whitespace",
    [
        {"codepoint": "U+0041", "count": 1},
        {"codepoint": "U+20", "count": 1},
        {"codepoint": "U+0020", "count": 1, "source_offset": 0},
    ],
)
def test_template_harness_rejects_invalid_whitespace_transport(
    tmp_path, whitespace: dict[str, object]
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": "source-entry-space",
                "text": " ",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-space",
                        "locator": "/body/p[1]",
                        "text_span": [0, 1],
                    }
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": "source-entry-space",
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-space",
                    "expected_fingerprint": "a" * 64,
                },
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": "source-entry-space",
                    "parts": [
                        {
                            "text": "",
                            "role": "style_only",
                            "whitespace": whitespace,
                        }
                    ],
                }
            ],
        }
    )

    assert result["status"] == "needs_input"
    assert result["failure"]["code"] == "template_whitespace_transport_invalid"
    assert result["blockers"][0]["code"] == "ordered_part_whitespace_transport_invalid"
    assert result["blockers"][0]["source_entry_id"] == "source-entry-space"


def test_template_harness_source_entry_gate_reports_missing_entry(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": "source-entry-title",
                "text": "论文题目",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-title",
                        "locator": "/body/p[1]",
                        "text_span": [0, 4],
                    }
                ],
            },
            {
                "source_entry_id": "source-entry-author",
                "text": "姓名：张三",
                "entry_type": "text",
                "source_order": {"block": 2, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-author",
                        "locator": "/body/p[2]",
                        "text_span": [0, 5],
                    }
                ],
            },
        ],
        "objects": [
            {
                "source_entry_id": "source-entry-title",
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-title",
                    "expected_fingerprint": "a" * 64,
                },
            },
            {
                "source_entry_id": "source-entry-author",
                "type": "paragraph",
                "locator": "/body/p[2]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-author",
                    "expected_fingerprint": "b" * 64,
                },
            },
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": "source-entry-title",
                    "parts": [{"text": "论文题目", "role": "fixed_label"}],
                }
            ],
        }
    )

    assert result["status"] == "needs_input"
    assert result["blockers"][0]["code"] == "source_span_missing_entry_judgment"
    assert result["blockers"][0]["source_entry_ids"] == ["source-entry-author"]
    assert result["harness_state"]["all_source_entries_have_semantic_coverage"] is False


def test_template_harness_source_entry_gate_rejects_duplicate_entry_judgment(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": "source-entry-title",
                "text": "论文题目",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-title",
                        "locator": "/body/p[1]",
                        "text_span": [0, 4],
                    }
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": "source-entry-title",
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-title",
                    "expected_fingerprint": "a" * 64,
                },
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": "source-entry-title",
                    "parts": [{"text": "论文题目", "role": "fixed_label"}],
                },
                {
                    "source_entry_id": "source-entry-title",
                    "parts": [{"text": "论文题目", "role": "fixed_label"}],
                },
            ],
        }
    )

    assert result["status"] == "needs_input"
    assert result["blockers"][0]["code"] == "source_span_duplicate_entry_judgment"
    assert result["blockers"][0]["source_entry_ids"] == ["source-entry-title"]


def test_p0_n06_template_harness_rejects_legacy_scope_without_conversion(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: author.name.zh",
                "    label: 作者中文姓名",
                "    content_type: text",
                "    cardinality: one",
            )
        ),
        encoding="utf-8",
    )
    source_entry_id = "source-entry-author"
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": "姓名：张三",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-label",
                        "locator": "/body/p[1]/r[1]",
                        "text_span": [0, 3],
                    },
                    {
                        "object_id": "obj-value",
                        "locator": "/body/p[1]/r[2]",
                        "text_span": [3, 5],
                    },
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-label",
                    "expected_fingerprint": "a" * 64,
                },
            },
            {
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": "/body/p[1]/r[2]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-value",
                    "expected_fingerprint": "b" * 64,
                },
            },
        ],
        "reading_blocks": [
            {
                "block_id": "u-cover:block-0001",
                "range_id": "u-cover:range-0001",
                "text": "姓名：张三",
                "covered_object_ids": ["obj-label", "obj-value"],
                "object_text_spans": [
                    {
                        "object_id": "obj-label",
                        "text_start": 0,
                        "text_end": 3,
                        "text": "姓名：",
                    },
                    {
                        "object_id": "obj-value",
                        "text_start": 3,
                        "text_end": 5,
                        "text": "张三",
                    },
                ],
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u-cover:block-0001"},
                    "parts": [
                        {"text": "姓名：", "role": "fixed_label"},
                        {
                            "text": "张三",
                            "role": "fill_slot",
                            "field_id": "author.name.zh",
                        },
                    ],
                }
            ],
        }
    )

    assert result["status"] == "needs_input"
    assert result["blockers"][0]["code"] == "legacy_reading_scope_unsupported"
    assert not (task_root / "work/.docfit/harness/semantic-judgments.json").exists()


def test_p0_n06_harness_treats_reading_block_as_source_entry_view(tmp_path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    registry = task_root / "input/field-registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "registry_id: test\n"
        "registry_version: '1'\n"
        "fields:\n"
        "  - field_id: thesis.title.zh\n"
        "    label: 论文题目\n"
        "    content_type: text\n"
    )
    source_entry_id = "source-entry-title"
    harness = TemplateHarnessService(task_root=task_root)

    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": "论文题目",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-title",
                        "locator": "/body/p[1]",
                        "text_span": [0, 4],
                    }
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": source_entry_id,
                "type": "paragraph",
                "locator": "/body/p[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-title",
                    "expected_fingerprint": "b" * 64,
                },
            }
        ],
        "reading_blocks": [
            {
                "block_id": "u-cover:block-0001",
                "text": "论文题目",
                "covered_object_ids": ["obj-title"],
                "covered_source_entry_ids": [source_entry_id],
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    result = harness.handle(inventory)

    assert result["status"] == "ok"
