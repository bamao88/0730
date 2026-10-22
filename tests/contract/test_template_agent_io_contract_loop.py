from __future__ import annotations

from pathlib import Path
from typing import Any

from docfit.fields import FieldRegistrySnapshot
from docfit.template.judgment_shape import validate_ordered_semantic_parts
from docfit.template.reading_packet import build_unit_reading_packet

JsonObject = dict[str, Any]
SOURCE_ENTRY_ID = "source-entry-cover-title"


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "field-registry.yaml"
    path.write_text(
        "\n".join(
            (
                "registry_id: test.registry",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: Chinese thesis title",
                "    content_type: text",
                "  - field_id: author.name.zh",
                "    label: Chinese author name",
                "    content_type: text",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _cover_title_packet(tmp_path: Path) -> JsonObject:
    vocabulary = _registry(tmp_path).pre_input_vocabulary(
        allowed_field_ids=("thesis.title.zh",)
    )
    return build_unit_reading_packet(
        unit={"unit_id": "u-cover", "unit_name": "封面"},
        scoped_objects=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "论文题目：玉米生长研究",
                "object_ref": {"object_id": "p-cover-title"},
            },
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "text": "论文题目：",
                "object_ref": {"object_id": "r-cover-title-label"},
            },
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "type": "run",
                "locator": "/body/p[1]/r[2]",
                "text": "玉米生长研究",
                "object_ref": {"object_id": "r-cover-title-value"},
            },
        ],
        coverage_object_ids=[
            "p-cover-title",
            "r-cover-title-label",
            "r-cover-title-value",
        ],
        source_entries=[
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "text": "论文题目：玉米生长研究",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
            }
        ],
        field_id_vocabulary=vocabulary,
    )


def _allowed_field_ids(packet: JsonObject) -> tuple[str, ...]:
    vocabulary = packet["field_id_vocabulary"]
    assert isinstance(vocabulary, dict)
    return tuple(
        str(field_id)
        for field_id in vocabulary["allowed_field_ids"]
        if isinstance(field_id, str)
    )


def _cover_title_judgments(
    *,
    source_entry_id: str = SOURCE_ENTRY_ID,
    field_id: str = "thesis.title.zh",
) -> list[JsonObject]:
    return [
        {
            "source_entry_id": source_entry_id,
            "parts": [
                {"text": "论文题目：", "role": "fixed_label"},
                {
                    "text": "玉米生长研究",
                    "role": "fill_slot",
                    "field_id": field_id,
                },
            ],
        }
    ]


def _validate(packet: JsonObject, judgments: list[JsonObject]) -> JsonObject:
    return validate_ordered_semantic_parts(
        judgments,
        allowed_field_ids=_allowed_field_ids(packet),
        source_entry_ids=tuple(
            str(entry["source_entry_id"])
            for entry in packet["source_entries"]
            if isinstance(entry, dict) and isinstance(entry.get("source_entry_id"), str)
        ),
    )


def _codes(feedback: JsonObject) -> list[str]:
    blockers = feedback.get("blockers")
    assert isinstance(blockers, list)
    return [str(item["code"]) for item in blockers if isinstance(item, dict)]


def test_cover_title_agent_input_packet_contains_field_id_vocabulary(
    tmp_path: Path,
) -> None:
    packet = _cover_title_packet(tmp_path)

    vocabulary = packet["field_id_vocabulary"]
    assert isinstance(vocabulary, dict)
    assert vocabulary["allowed_field_ids"] == ["thesis.title.zh"]
    assert packet["field_vocabulary_digest"] == vocabulary["digest"]
    assert packet["reading_blocks"][0]["block_id"] == "u-cover:block-0001"
    assert packet["reading_blocks"][0]["range_id"] == "u-cover:range-0001"
    assert packet["reading_blocks"][0]["text"] == "论文题目：玉米生长研究"


def test_p0_n06_cover_title_agent_output_rejects_packet_block_scope(
    tmp_path: Path,
) -> None:
    packet = _cover_title_packet(tmp_path)
    block_id = packet["reading_blocks"][0]["block_id"]
    judgments = _cover_title_judgments()
    judgments[0].pop("source_entry_id")
    judgments[0]["scope"] = {"reading_block_id": block_id}

    result = _validate(packet, judgments)

    assert result["status"] == "needs_input"
    assert "legacy_reading_scope_unsupported" in _codes(result)


def test_cover_title_agent_output_accepts_ordered_parts_with_source_entry_id(
    tmp_path: Path,
) -> None:
    packet = _cover_title_packet(tmp_path)
    result = validate_ordered_semantic_parts(
        [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
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
        allowed_field_ids=_allowed_field_ids(packet),
        source_entry_ids=(SOURCE_ENTRY_ID,),
    )

    assert result["status"] == "ok"
    assert result["failure"] is None


def test_p0_n06_cover_title_agent_output_rejects_packet_range_scope(
    tmp_path: Path,
) -> None:
    packet = _cover_title_packet(tmp_path)
    range_id = packet["reading_blocks"][0]["range_id"]
    judgments = _cover_title_judgments()
    judgments[0].pop("source_entry_id")
    judgments[0]["scope"] = {"reading_range_id": range_id}

    result = _validate(packet, judgments)

    assert result["status"] == "needs_input"
    assert "legacy_reading_scope_unsupported" in _codes(result)


def test_cover_title_agent_output_rejects_new_field_id_not_in_input_vocabulary(
    tmp_path: Path,
) -> None:
    packet = _cover_title_packet(tmp_path)
    judgments = _cover_title_judgments(
        field_id="thesis.subtitle.zh",
    )

    result = _validate(packet, judgments)

    assert result["status"] == "needs_input"
    assert "field_id_not_in_input_vocabulary" in _codes(result)


def test_cover_title_agent_output_must_bind_to_packet_source_entry(
    tmp_path: Path,
) -> None:
    packet = _cover_title_packet(tmp_path)
    missing_source = _cover_title_judgments()
    missing_source[0].pop("source_entry_id")
    unknown_source = _cover_title_judgments(source_entry_id="source-entry-unknown")

    missing_source_result = _validate(packet, missing_source)
    unknown_source_result = _validate(packet, unknown_source)

    assert missing_source_result["status"] == "needs_input"
    assert "ordered_semantic_source_entry_missing" in _codes(missing_source_result)
    assert unknown_source_result["status"] == "needs_input"
    assert "ordered_semantic_source_entry_unknown" in _codes(unknown_source_result)
