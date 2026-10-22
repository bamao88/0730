from __future__ import annotations

from pathlib import Path

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization import (
    MaterializationContextKind,
    MaterializationIntentType,
)
from docfit.template.materialization import (
    build_shadow_materialization_plan as _build_shadow_materialization_plan,
)
from docfit.template.source_spans import SourceSpanResolutionError, resolve_semantic_judgments
from docfit.tools.runtime import sha256_json
from tests.support.source_identity import review_binding, source_partition


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "field-registry.yaml"
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
                "  - field_id: advisor.name.zh",
                "    label: 导师姓名",
                "    content_type: text",
                "  - field_id: generated.toc",
                "    label: 目录",
                "    content_type: section",
                "    value_sources:",
                "      - system_generated",
                "  - field_id: body.chapters",
                "    label: 正文章节集合",
                "    content_type: section",
                "  - field_id: body.heading.outline1",
                "    label: 章标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.paragraph",
                "    label: 正文段落",
                "    content_type: rich_text",
                "    parent_field_id: body.chapters",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _inventory() -> dict[str, object]:
    inventory = {"reading_blocks": []}
    return inventory


def _judgment(
    *,
    source_entry_id: str,
    role: str,
    field_id: str | None = None,
) -> dict[str, object]:
    part: dict[str, object] = {"text": "x", "role": role}
    if field_id is not None:
        part["field_id"] = field_id
    return {
        "source_entry_id": (
            source_entry_id
            if source_entry_id.startswith("source-entry-")
            else f"source-entry-{source_entry_id}"
        ),
        "parts": [part],
    }


def _mixed_judgment(
    *,
    source_entry_id: str,
    parts: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "source_entry_id": (
            source_entry_id
            if source_entry_id.startswith("source-entry-")
            else f"source-entry-{source_entry_id}"
        ),
        "parts": parts,
    }


def _current_contract(
    registry: FieldRegistrySnapshot,
    inventory: dict[str, object],
    review: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    vocabulary = registry.pre_input_vocabulary()
    document_sha256 = "a" * 64
    raw_judgments = review.get("semantic_judgments")
    assert isinstance(raw_judgments, list)
    judgments = [dict(item) for item in raw_judgments if isinstance(item, dict)]
    assert len(judgments) == len(raw_judgments)

    source_entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    seen_source_entries: set[str] = set()
    for index, judgment in enumerate(judgments):
        source_entry_id = judgment.get("source_entry_id")
        assert isinstance(source_entry_id, str)
        if source_entry_id in seen_source_entries:
            continue
        seen_source_entries.add(source_entry_id)
        parts = judgment.get("parts")
        assert isinstance(parts, list)
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        object_id = f"obj-current-{index:04d}"
        fingerprint = f"{index + 1:064x}"
        locator = f"/body/p[{index + 1}]/r[1]"
        object_ref = {
            "document_sha256": document_sha256,
            "expected_fingerprint": fingerprint,
            "object_id": object_id,
        }
        source_entries.append(
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {
                    "block": index + 1,
                    "inline": 0,
                },
                "extent": {"kind": "text", "start": 0, "end": len(text)},
                "provenance": [
                    {
                        "object_id": object_id,
                        "locator": locator,
                        "text_span": [0, len(text)],
                        "object_ref": object_ref,
                        "fingerprint": fingerprint,
                    }
                ],
            }
        )
        objects.append(
            {
                "object_id": object_id,
                "type": "run",
                "locator": locator,
                "source_entry_id": source_entry_id,
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        )
    current_inventory = {
        **inventory,
        "document_sha256": document_sha256,
        "source_entries": source_entries,
        "objects": objects,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    source_partition(current_inventory)
    resolved_spans = resolve_semantic_judgments(
        inventory=current_inventory,
        judgments=judgments,
    )
    accepted_judgments = [
        {
            **judgment,
            "resolved_spans": [
                span for span in resolved_spans if span.get("judgment_index") == index
            ],
        }
        for index, judgment in enumerate(judgments)
    ]
    return current_inventory, {
        **review_binding(current_inventory),
        **review,
        "document_sha256": document_sha256,
        "semantic_judgments": accepted_judgments,
        "semantic_judgments_sha256": sha256_json(accepted_judgments),
        "resolved_spans": resolved_spans,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }


def build_shadow_materialization_plan(
    *,
    inventory: dict[str, object],
    review: dict[str, object],
    registry: FieldRegistrySnapshot,
):
    current_inventory, current_review = _current_contract(
        registry,
        inventory,
        review,
    )
    return _build_shadow_materialization_plan(
        inventory=current_inventory,
        review=current_review,
        registry=registry,
    )


def test_shadow_plan_requires_accepted_field_vocabulary(
    tmp_path: Path,
) -> None:
    result = _build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _judgment(
                    source_entry_id="u-cover:block-0001",
                    role="fill_slot",
                    field_id="thesis.title.zh",
                )
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is False
    assert result.intents == ()
    assert result.unsupported[0].reason_code == (
        "materialization_field_vocabulary_provenance_missing"
    )


def test_shadow_plan_is_ready_for_valid_ordered_slot(tmp_path: Path) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _judgment(
                    source_entry_id="u-cover:block-0001",
                    role="fill_slot",
                    field_id="thesis.title.zh",
                )
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.plan.contexts[0].kind == MaterializationContextKind.FIELD_SLOT.value
    assert result.plan.intents[0].intent_type == MaterializationIntentType.MATERIALIZE_SLOT


def test_shadow_plan_is_ready_for_source_entry_slot_without_reading_block(
    tmp_path: Path,
) -> None:
    source_entry_id = "source-entry-cover-title"
    inventory = {
        "objects": [{"object_id": "obj-title", "type": "paragraph"}],
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": "论文题目：×××",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-title",
                        "locator": "/body/p[1]",
                        "text_span": [0, 7],
                    }
                ],
            }
        ],
        "reading_blocks": [],
    }
    result = build_shadow_materialization_plan(
        inventory=inventory,
        review={
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.plan.intents[0].scope_refs[0].kind == "source_entry"
    assert result.plan.contexts[0].facts["resolved_spans"][0]["source_entry_id"] == (
        source_entry_id
    )


def test_shadow_plan_accepts_mixed_fixed_label_and_style_parts(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _mixed_judgment(
                    source_entry_id="u-cover:block-0002",
                    parts=[
                        {"text": "附件1", "role": "fixed_label"},
                        {"text": "格式说明", "role": "style_only"},
                    ],
                )
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.plan.intents[0].intent_type == MaterializationIntentType.KEEP_FIXED_CONTENT


def test_shadow_plan_accepts_mixed_manual_region_and_cleanup_parts(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _mixed_judgment(
                    source_entry_id="u-form:block-0001",
                    parts=[
                        {"text": "……", "role": "manual_region"},
                        {"text": "格式说明", "role": "cleanup"},
                    ],
                )
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.plan.intents[0].intent_type == MaterializationIntentType.KEEP_MANUAL_TABLE_CELL


def test_shadow_plan_accepts_fixed_labels_around_manual_regions(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _mixed_judgment(
                    source_entry_id="u-form:block-0001",
                    parts=[
                        {"text": "论证地点:", "role": "fixed_label"},
                        {"text": "……", "role": "manual_region"},
                        {"text": "论证日期:", "role": "fixed_label"},
                        {"text": "格式说明", "role": "style_only"},
                    ],
                )
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.unsupported == ()
    assert result.plan.intents[0].intent_type == MaterializationIntentType.KEEP_MANUAL_TABLE_CELL


def test_shadow_plan_accepts_multiple_exact_body_spans_in_one_source_entry(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _mixed_judgment(
                    source_entry_id="u-cover:block-0001",
                    parts=[
                        {
                            "text": "1",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        },
                        {"text": "□", "role": "fixed_label"},
                        {
                            "text": "前言",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        },
                    ],
                )
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.unsupported == ()
    intent = result.plan.intents[0]
    assert [span.text for span in intent.resolved_spans] == ["1", "□", "前言"]
    assert [span.role for span in intent.resolved_spans] == [
        "body_structure",
        "fixed_label",
        "body_structure",
    ]


def test_shadow_plan_rejects_duplicate_source_entry_manual_and_slot_judgments(
    tmp_path: Path,
) -> None:
    with pytest.raises(SourceSpanResolutionError, match="could not be resolved exactly"):
        build_shadow_materialization_plan(
            inventory=_inventory(),
            review={
                "semantic_judgments": [
                    _judgment(source_entry_id="u-form:block-0001", role="manual_region"),
                    _judgment(
                        source_entry_id="u-form:block-0001",
                        role="fill_slot",
                        field_id="advisor.name.zh",
                    ),
                ]
            },
            registry=_registry(tmp_path),
        )


def test_shadow_plan_accepts_distinct_manual_and_slot_source_entries(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _judgment(source_entry_id="u-form:block-0001", role="manual_region"),
                _judgment(
                    source_entry_id="u-form:block-0002",
                    role="fill_slot",
                    field_id="advisor.name.zh",
                ),
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.unsupported == ()


def test_shadow_plan_rejects_duplicate_source_entry_manual_and_cleanup_judgments(
    tmp_path: Path,
) -> None:
    with pytest.raises(SourceSpanResolutionError, match="could not be resolved exactly"):
        build_shadow_materialization_plan(
            inventory=_inventory(),
            review={
                "semantic_judgments": [
                    _judgment(source_entry_id="u-form:block-0001", role="manual_region"),
                    _judgment(source_entry_id="u-form:block-0001", role="cleanup"),
                ]
            },
            registry=_registry(tmp_path),
        )


def test_shadow_plan_rejects_duplicate_source_entry_generated_and_slot_judgments(
    tmp_path: Path,
) -> None:
    with pytest.raises(SourceSpanResolutionError, match="could not be resolved exactly"):
        build_shadow_materialization_plan(
            inventory=_inventory(),
            review={
                "semantic_judgments": [
                    _judgment(
                        source_entry_id="u-cover:block-0001",
                        role="generated_content",
                        field_id="generated.toc",
                    ),
                    _judgment(
                        source_entry_id="u-cover:block-0001",
                        role="fill_slot",
                        field_id="thesis.title.zh",
                    ),
                ]
            },
            registry=_registry(tmp_path),
        )


def test_shadow_plan_allows_cleanup_part_without_legacy_cleanup_reason(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [_judgment(source_entry_id="u-cover:block-0002", role="cleanup")]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.unsupported == ()


def test_shadow_plan_allows_style_only_part_without_legacy_style_obligation(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _judgment(source_entry_id="u-cover:block-0002", role="style_only")
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.unsupported == ()


def test_shadow_plan_accepts_contiguous_body_structure_parts_from_multiple_scopes(
    tmp_path: Path,
) -> None:
    result = build_shadow_materialization_plan(
        inventory=_inventory(),
        review={
            "semantic_judgments": [
                _judgment(
                    source_entry_id="u-cover:block-0001",
                    role="body_structure",
                    field_id="body.heading.outline1",
                ),
                _judgment(
                    source_entry_id="u-cover:block-0002",
                    role="body_structure",
                    field_id="body.paragraph",
                ),
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert [
        intent.intent_type
        for intent in result.plan.intents
        if intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
    ] == [
        MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
        MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
    ]


def test_shadow_plan_rejects_retired_reading_block_candidate_selection(
    tmp_path: Path,
) -> None:
    inventory = {
        "objects": [],
        "reading_blocks": [
            {
                "block_id": "body:block-0001",
                "range_id": "body:range-0001",
                "unit_id": "body",
                "order": 1,
                "text": "1□前言",
                "covered_object_ids": ["obj-1"],
            },
            {
                "block_id": "body:block-0002",
                "range_id": "body:range-0002",
                "unit_id": "body",
                "order": 2,
                "text": "以下另一类用",
                "covered_object_ids": ["obj-2"],
            },
            {
                "block_id": "body:block-0003",
                "range_id": "body:range-0003",
                "unit_id": "body",
                "order": 3,
                "text": "一、绪论",
                "covered_object_ids": ["obj-3"],
            },
        ],
    }
    registry = _registry(tmp_path)
    vocabulary = registry.pre_input_vocabulary()
    result = _build_shadow_materialization_plan(
        inventory={
            **inventory,
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
        },
        review={
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "body:block-0001"},
                    "parts": [
                        {
                            "text": "1□前言",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        }
                    ],
                }
            ],
        },
        registry=registry,
    )

    assert result.ready is False
    assert result.unsupported[0].reason_code == "materialization_semantic_review_not_current"
    assert result.unsupported[0].missing_requirements == ("current_accepted_semantic_review",)


def test_shadow_plan_rejects_retired_reading_range_candidate_selection(
    tmp_path: Path,
) -> None:
    inventory = {
        "objects": [],
        "reading_blocks": [
            {
                "block_id": "body-track-a:block-0001",
                "range_id": "body-track-a:range-whole-unit",
                "unit_id": "body-track-a",
                "order": 1,
                "text": "（以下农理工科类用）",
                "covered_object_ids": ["obj-a-note"],
            },
            {
                "block_id": "body-track-a:block-0002",
                "range_id": "body-track-a:range-whole-unit",
                "unit_id": "body-track-a",
                "order": 2,
                "text": "1□前言",
                "covered_object_ids": ["obj-a-heading"],
            },
            {
                "block_id": "body-track-b:block-0001",
                "range_id": "body-track-b:range-whole-unit",
                "unit_id": "body-track-b",
                "order": 3,
                "text": "（以下文法经管类用）",
                "covered_object_ids": ["obj-b-note"],
            },
            {
                "block_id": "body-track-b:block-0002",
                "range_id": "body-track-b:range-whole-unit",
                "unit_id": "body-track-b",
                "order": 4,
                "text": "一、绪论",
                "covered_object_ids": ["obj-b-heading"],
            },
        ],
    }
    registry = _registry(tmp_path)
    vocabulary = registry.pre_input_vocabulary()
    result = _build_shadow_materialization_plan(
        inventory={
            **inventory,
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
        },
        review={
            "field_id_vocabulary": vocabulary,
            "field_vocabulary_digest": vocabulary["digest"],
            "semantic_judgments": [
                {
                    "scope": {"reading_range_id": "body-track-a:range-whole-unit"},
                    "parts": [
                        {"text": "（以下农理工科类用）", "role": "style_only"},
                        {
                            "text": "1□前言",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        },
                    ],
                },
                {
                    "scope": {"reading_range_id": "body-track-b:range-whole-unit"},
                    "parts": [
                        {"text": "（以下文法经管类用）", "role": "style_only"},
                        {
                            "text": "一、绪论",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        },
                    ],
                },
            ],
        },
        registry=registry,
    )

    assert result.ready is False
    assert result.unsupported[0].reason_code == "materialization_semantic_review_not_current"
    assert result.unsupported[0].missing_requirements == ("current_accepted_semantic_review",)


def test_shadow_plan_rejects_stale_source_entry_inventory(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    inventory, review = _current_contract(
        registry,
        _inventory(),
        {
            "semantic_judgments": [
                _judgment(
                    source_entry_id="source-entry-missing",
                    role="fill_slot",
                    field_id="thesis.title.zh",
                )
            ]
        },
    )
    inventory["source_entries"] = []
    result = _build_shadow_materialization_plan(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert result.ready is False
    assert result.unsupported[0].reason_code == "materialization_resolved_span_unresolvable"
