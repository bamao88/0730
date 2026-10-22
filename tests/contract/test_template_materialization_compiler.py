from __future__ import annotations

from pathlib import Path

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization import (
    MaterializationIntent,
    MaterializationIntentType,
    ScopeRef,
)
from docfit.template.materialization import (
    compile_materialization_intents as _compile_materialization_intents,
)
from docfit.template.source_spans import SourceSpan, TextSourceExtent, source_span_ref
from docfit.tools.runtime import sha256_json


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
                "  - field_id: body.chapters",
                "    label: 正文章节集合",
                "    content_type: section",
                "  - field_id: body.heading.outline1",
                "    label: 章标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.heading.outline2",
                "    label: 节标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.paragraph",
                "    label: 正文段落",
                "    content_type: rich_text",
                "    parent_field_id: body.chapters",
                "  - field_id: generated.toc",
                "    label: 目录",
                "    content_type: section",
                "    value_sources:",
                "      - system_generated",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _span(
    *,
    block_id: str,
    part_index: int,
    role: str,
    field_id: str | None = None,
) -> dict[str, object]:
    span_ref = f"reading_block_id={block_id};part_index={part_index}"
    result: dict[str, object] = {
        "span_ref": span_ref,
        "scope": {"reading_block_id": block_id},
        "reading_block_id": block_id,
        "part_index": part_index,
        "role": role,
        "text": "x",
    }
    if field_id is not None:
        result["field_id"] = field_id
        result["slot_ref"] = f"{span_ref};field_id={field_id}"
    return result


def _source_entry_span(
    *,
    source_entry_id: str,
    part_index: int,
    role: str,
    field_id: str | None = None,
) -> dict[str, object]:
    span_ref = f"source_entry_id={source_entry_id};part_index={part_index}"
    result: dict[str, object] = {
        "span_ref": span_ref,
        "scope": {"source_entry_id": source_entry_id},
        "source_entry_id": source_entry_id,
        "part_index": part_index,
        "role": role,
        "text": "x",
        "text_start": 0,
        "text_end": 1,
        "covered_object_ids": ["obj-title"],
    }
    if field_id is not None:
        result["field_id"] = field_id
        result["slot_ref"] = f"{span_ref};field_id={field_id}"
    return result


def _current_review(
    registry: FieldRegistrySnapshot,
    review: dict[str, object],
    *,
    allowed_field_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    vocabulary = registry.pre_input_vocabulary(allowed_field_ids=allowed_field_ids)
    result = {
        **review,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    raw_judgments = result.get("semantic_judgments")
    if not isinstance(raw_judgments, list):
        return result
    judgments: list[dict[str, object]] = []
    flattened_spans: list[dict[str, object]] = []
    source_snapshot_sha256 = "a" * 64
    inventory_digest = "b" * 64
    for judgment_index, raw_judgment in enumerate(raw_judgments):
        if not isinstance(raw_judgment, dict):
            judgments.append(raw_judgment)
            continue
        judgment = dict(raw_judgment)
        source_entry_id = judgment.get("source_entry_id")
        if not isinstance(source_entry_id, str):
            source_entry_id = f"source-entry-test-{judgment_index:04d}"
            judgment["source_entry_id"] = source_entry_id
            judgment.pop("scope", None)
        parts = judgment.get("parts")
        raw_spans = judgment.get("resolved_spans")
        if isinstance(parts, list) and isinstance(raw_spans, list):
            cursor = 0
            spans: list[dict[str, object]] = []
            for part_index, raw_span in enumerate(raw_spans):
                if not isinstance(raw_span, dict):
                    spans.append(raw_span)
                    continue
                span = dict(raw_span)
                part = parts[part_index] if part_index < len(parts) else {}
                part_text = part.get("text") if isinstance(part, dict) else ""
                part_text = part_text if isinstance(part_text, str) else ""
                end = cursor + len(part_text)
                span_ref = source_span_ref(
                    source_snapshot_sha256=source_snapshot_sha256,
                    source_span=SourceSpan(
                        source_entry_id=source_entry_id,
                        extent=TextSourceExtent(cursor, end),
                    ),
                )
                old_span_ref = span.get("span_ref")
                old_slot_ref = span.get("slot_ref")
                span.update(
                    {
                        "span_ref": span_ref,
                        "scope": {"source_entry_id": source_entry_id},
                        "source_entry_id": source_entry_id,
                        "judgment_index": judgment_index,
                        "part_index": part_index,
                        "role": part.get("role") if isinstance(part, dict) else None,
                        "text": part_text,
                        "text_start": cursor,
                        "text_end": end,
                        "extent": {"kind": "text", "start": cursor, "end": end},
                        "expected_source_content": part_text,
                        "source_snapshot_sha256": source_snapshot_sha256,
                        "source_inventory_digest": inventory_digest,
                        "covered_object_ids": [f"obj-{judgment_index}-{part_index}"],
                        "word_fragments": [
                            {
                                "object_id": f"obj-{judgment_index}-{part_index}",
                                "locator": f"/body/p[{judgment_index + 1}]/r[{part_index + 1}]",
                                "text": part_text,
                                "source_text_start": cursor,
                                "source_text_end": end,
                                "object_text_start": 0,
                                "object_text_end": len(part_text),
                                "object_ref": {
                                    "document_sha256": source_snapshot_sha256,
                                    "expected_fingerprint": "c" * 64,
                                    "object_id": f"obj-{judgment_index}-{part_index}",
                                },
                                "fingerprint": "c" * 64,
                            }
                        ],
                    }
                )
                field_id = span.get("field_id")
                if isinstance(field_id, str):
                    canonical_slot_ref = f"{span_ref};field_id={field_id}"
                    span["slot_ref"] = (
                        canonical_slot_ref
                        if old_slot_ref == f"{old_span_ref};field_id={field_id}"
                        else old_slot_ref
                    )
                spans.append(span)
                cursor = end
            judgment["resolved_spans"] = spans
            flattened_spans.extend(spans)
        judgments.append(judgment)
    result["semantic_judgments"] = judgments
    result["semantic_judgments_sha256"] = sha256_json(judgments)
    result["resolved_spans"] = flattened_spans
    result["document_sha256"] = source_snapshot_sha256
    result["source_inventory_digest"] = inventory_digest
    result["unit_projection_digest"] = "d" * 64
    return result


def compile_materialization_intents(
    *,
    review: dict[str, object],
    registry: FieldRegistrySnapshot,
):
    return _compile_materialization_intents(
        review=_current_review(registry, review),
        registry=registry,
    )


def test_compiler_requires_accepted_field_vocabulary(
    tmp_path: Path,
) -> None:
    result = _compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        )
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is False
    assert result.intents == ()
    assert result.unsupported[0].reason_code == (
        "materialization_field_vocabulary_provenance_missing"
    )


def test_materialization_intent_serializes_as_contract_shape() -> None:
    intent = MaterializationIntent(
        intent_ref="intent-0001",
        intent_type=MaterializationIntentType.MATERIALIZE_SLOT,
        source_judgment_refs=("semantic_judgments[0]",),
        scope_refs=(ScopeRef(kind="reading_block", ref_id="u:block-0001"),),
        field_ids=("thesis.title.zh",),
        payload={"field_ids": ["thesis.title.zh"]},
        classification_basis=("parts.role", "parts.field_id", "resolved_spans"),
    )

    assert intent.to_json() == {
        "intent_ref": "intent-0001",
        "intent_type": "materialize_slot",
        "source_judgment_refs": ["semantic_judgments[0]"],
        "scope_refs": [{"kind": "reading_block", "ref_id": "u:block-0001"}],
        "field_ids": ["thesis.title.zh"],
        "payload": {"field_ids": ["thesis.title.zh"]},
        "classification_basis": ["parts.role", "parts.field_id", "resolved_spans"],
    }


def test_materialization_intent_rejects_slot_without_field() -> None:
    with pytest.raises(ValueError, match="requires field_ids"):
        MaterializationIntent(
            intent_ref="intent-0001",
            intent_type=MaterializationIntentType.MATERIALIZE_SLOT,
            source_judgment_refs=("semantic_judgments[0]",),
            scope_refs=(ScopeRef(kind="reading_block", ref_id="u:block-0001"),),
        )


def test_materialization_intent_rejects_generated_content_without_field() -> None:
    with pytest.raises(ValueError, match="requires field_ids"):
        MaterializationIntent(
            intent_ref="intent-0001",
            intent_type=MaterializationIntentType.REFRESH_GENERATED_CONTENT,
            source_judgment_refs=("semantic_judgments[0]",),
            scope_refs=(ScopeRef(kind="reading_block", ref_id="u:block-0001"),),
        )


def test_compiler_materializes_slot_from_accepted_ordered_parts(tmp_path: Path) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [
                        {"text": "论文题目：", "role": "fixed_label"},
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        },
                    ],
                    "resolved_spans": [
                        _span(block_id="u:block-0001", part_index=0, role="fixed_label"),
                        _span(
                            block_id="u:block-0001",
                            part_index=1,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        ),
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    intent = result.intents[0]
    assert intent.intent_type == MaterializationIntentType.MATERIALIZE_SLOT
    assert intent.source_judgment_refs == ("semantic_judgments[0]",)
    assert intent.scope_refs == (ScopeRef(kind="source_entry", ref_id="source-entry-test-0000"),)
    assert intent.field_ids == ("thesis.title.zh",)
    assert intent.payload["field_ids"] == ["thesis.title.zh"]
    assert "registry_field" not in intent.payload
    assert "semantic_parts" not in intent.payload


def test_compiler_materializes_slot_from_source_entry_span(tmp_path: Path) -> None:
    source_entry_id = "source-entry-cover-title"
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "source_entry_id": source_entry_id,
                    "parts": [
                        {"text": "论文题目：", "role": "fixed_label"},
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        },
                    ],
                    "resolved_spans": [
                        _source_entry_span(
                            source_entry_id=source_entry_id,
                            part_index=0,
                            role="fixed_label",
                        ),
                        _source_entry_span(
                            source_entry_id=source_entry_id,
                            part_index=1,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        ),
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    intent = result.intents[0]
    assert intent.intent_type == MaterializationIntentType.MATERIALIZE_SLOT
    assert intent.scope_refs == (ScopeRef(kind="source_entry", ref_id=source_entry_id),)
    assert intent.payload["resolved_spans"][1]["span_ref"].startswith(
        f"source_entry_id={source_entry_id};extent=text[5:8];"
    )
    assert "reading_block_id" not in intent.payload["resolved_spans"][1]


@pytest.mark.parametrize(
    "legacy_shape",
    [
        {"registry_field": "thesis.title.zh"},
        {"bound_field_ids": ["thesis.title.zh"]},
        {"structure_ref": "body.chapters", "members": ["body.heading.outline1"]},
        {"toc_contract": {"generated_field_id": "generated.toc"}},
        {"materialization_intent": "materialize_slot"},
        {"source_content_id": "legacy-content-1"},
        {"source_object_ids": ["obj-1"]},
    ],
)
def test_compiler_rejects_legacy_field_shapes(
    tmp_path: Path,
    legacy_shape: dict[str, object],
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        )
                    ],
                    **legacy_shape,
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    blocker = result.unsupported[0]
    assert result.ready is False
    assert result.intents == ()
    assert blocker.reason_code == "materialization_legacy_shape_unsupported"
    assert blocker.payload["legacy_fields"]


@pytest.mark.parametrize(
    "legacy_part_shape",
    [
        {"registry_field": "thesis.title.zh"},
        {"bound_field_ids": ["thesis.title.zh"]},
        {"field_ids": ["thesis.title.zh"]},
        {"covered_object_ids": ["obj-slot"]},
        {"source_content_id": "legacy-content-1"},
        {"source_object_ids": ["obj-1"]},
        {"locator": "/body/p[1]/r[1]"},
        {"span_ref": "reading_block_id=u:block-0001;part_index=0"},
    ],
)
def test_compiler_rejects_legacy_part_field_shapes(
    tmp_path: Path,
    legacy_part_shape: dict[str, object],
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                            **legacy_part_shape,
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        )
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    blocker = result.unsupported[0]
    assert result.ready is False
    assert result.intents == ()
    assert blocker.reason_code == "materialization_legacy_shape_unsupported"
    assert blocker.payload["legacy_part_fields"]


def test_compiler_returns_unsupported_for_slot_missing_part_field(
    tmp_path: Path,
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [{"text": "×××", "role": "fill_slot"}],
                    "resolved_spans": [
                        _span(block_id="u:block-0001", part_index=0, role="fill_slot")
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    blocker = result.unsupported[0]
    assert blocker.reason_code == "materialization_slot_field_missing"
    assert blocker.missing_requirements == ("parts[].field_id",)


def test_compiler_returns_unsupported_for_unknown_part_field(tmp_path: Path) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [{"text": "×××", "role": "fill_slot", "field_id": "unknown.field"}],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fill_slot",
                            field_id="unknown.field",
                        )
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    blocker = result.unsupported[0]
    assert blocker.reason_code == "materialization_field_not_in_vocabulary"
    assert blocker.payload == {"field_ids": ["unknown.field"]}


def test_compiler_rejects_registry_field_outside_accepted_vocabulary(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    result = _compile_materialization_intents(
        review=_current_review(
            registry,
            {
                "semantic_judgments": [
                    {
                        "scope": {"reading_block_id": "u:block-0001"},
                        "parts": [
                            {
                                "text": "×××",
                                "role": "fill_slot",
                                "field_id": "thesis.title.zh",
                            }
                        ],
                        "resolved_spans": [
                            _span(
                                block_id="u:block-0001",
                                part_index=0,
                                role="fill_slot",
                                field_id="thesis.title.zh",
                            )
                        ],
                    }
                ]
            },
            allowed_field_ids=("advisor.name.zh",),
        ),
        registry=registry,
    )

    assert result.ready is False
    assert result.intents == ()
    assert result.unsupported[0].reason_code == "materialization_field_not_in_vocabulary"
    assert result.unsupported[0].payload == {"field_ids": ["thesis.title.zh"]}


def test_compiler_requires_harness_resolved_span_for_executable_parts(
    tmp_path: Path,
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
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

    blocker = result.unsupported[0]
    assert blocker.reason_code == "materialization_semantic_review_not_current"
    assert blocker.missing_requirements == ("current_accepted_semantic_review",)


def test_compiler_rejects_slot_ref_not_derived_from_span_ref_and_field(
    tmp_path: Path,
) -> None:
    span = _span(
        block_id="u:block-0001",
        part_index=0,
        role="fill_slot",
        field_id="thesis.title.zh",
    )
    span["slot_ref"] = "reading_block_id=u:block-0001;part_index=0;field_id=author.name.zh"
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "resolved_spans": [span],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    blocker = result.unsupported[0]
    assert blocker.reason_code == "materialization_resolved_span_invalid"
    assert blocker.missing_requirements == ("resolved_spans[].word_fragments",)


@pytest.mark.parametrize("fallback_key", ["locator", "target_ref", "covered_object_ids"])
def test_compiler_rejects_missing_fragments_without_target_fallback(
    tmp_path: Path,
    fallback_key: str,
) -> None:
    registry = _registry(tmp_path)
    review = _current_review(
        registry,
        {
            "semantic_judgments": [
                {
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        )
                    ],
                }
            ]
        },
    )
    span = review["semantic_judgments"][0]["resolved_spans"][0]
    assert isinstance(span, dict)
    span.pop("word_fragments")
    span[fallback_key] = ["obj-fallback"] if fallback_key == "covered_object_ids" else "fallback"
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])

    result = _compile_materialization_intents(review=review, registry=registry)

    assert result.intents == ()
    assert result.unsupported[0].reason_code == "materialization_resolved_span_invalid"


def test_compiler_rejects_unparseable_source_span_ref(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    review = _current_review(
        registry,
        {
            "semantic_judgments": [
                {
                    "parts": [{"text": "label", "role": "fixed_label"}],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fixed_label",
                        )
                    ],
                }
            ]
        },
    )
    span = review["semantic_judgments"][0]["resolved_spans"][0]
    assert isinstance(span, dict)
    span["span_ref"] = "reading_block_id=u:block-0001;part_index=0"
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])

    result = _compile_materialization_intents(review=review, registry=registry)

    assert result.intents == ()
    assert result.unsupported[0].reason_code == "materialization_resolved_span_invalid"


def test_compiler_materializes_body_structure_from_ordered_parts(
    tmp_path: Path,
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "body:block-0001"},
                    "parts": [
                        {
                            "text": "1 前言",
                            "role": "body_structure",
                            "field_id": "body.heading.outline1",
                        },
                        {
                            "text": "□□……",
                            "role": "body_structure",
                            "field_id": "body.paragraph",
                        },
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="body:block-0001",
                            part_index=0,
                            role="body_structure",
                            field_id="body.heading.outline1",
                        ),
                        _span(
                            block_id="body:block-0002",
                            part_index=1,
                            role="body_structure",
                            field_id="body.paragraph",
                        ),
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    intent = result.intents[0]
    assert intent.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
    assert intent.field_ids == (
        "body.heading.outline1",
        "body.paragraph",
    )
    assert intent.payload["structure_ref"] == "body.chapters"
    assert intent.payload["members"] == ["body.heading.outline1", "body.paragraph"]
    assert intent.payload["structure_ref_provenance"] == {
        "source": "registry_parent_field_id",
        "member_field_ids": ["body.heading.outline1", "body.paragraph"],
    }
    assert [binding["member_field_id"] for binding in intent.payload["member_bindings"]] == [
        "body.heading.outline1",
        "body.paragraph",
    ]
    assert all(
        binding["source_entry_id"] == "source-entry-test-0000"
        and binding["span_ref"].startswith("source_entry_id=source-entry-test-0000;")
        for binding in intent.payload["member_bindings"]
    )


def test_compiler_does_not_supply_body_structure_default_parent(
    tmp_path: Path,
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "body:block-0001"},
                    "parts": [
                        {
                            "text": "论文题目",
                            "role": "body_structure",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="body:block-0001",
                            part_index=0,
                            role="body_structure",
                            field_id="thesis.title.zh",
                        )
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    blocker = result.unsupported[0]
    assert blocker.reason_code == "materialization_body_structure_parent_missing"
    assert blocker.missing_requirements == ("registry_parent_field_id",)


def test_compiler_materializes_generated_content_from_ordered_part(
    tmp_path: Path,
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u-toc:block-0001"},
                    "parts": [
                        {
                            "text": "目 录",
                            "role": "generated_content",
                            "field_id": "generated.toc",
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="u-toc:block-0001",
                            part_index=0,
                            role="generated_content",
                            field_id="generated.toc",
                        )
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    intent = result.intents[0]
    assert intent.intent_type == MaterializationIntentType.REFRESH_GENERATED_CONTENT
    assert intent.field_ids == ("generated.toc",)
    assert "toc_contract" not in intent.payload


def test_compiler_does_not_infer_intent_or_field_from_natural_language(
    tmp_path: Path,
) -> None:
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "reason": "Replace this with Registry field thesis.title.zh.",
                    "parts": [{"text": "论文题目", "role": "fixed_label"}],
                    "resolved_spans": [
                        _span(block_id="u:block-0001", part_index=0, role="fixed_label")
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.intents[0].intent_type == MaterializationIntentType.KEEP_FIXED_CONTENT
    assert result.intents[0].field_ids == ()


def test_compiler_rejects_compatibility_scope_and_object_ids(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    review = _current_review(
        registry,
        {
            "semantic_judgments": [
                {
                    "parts": [
                        {
                            "text": "×××",
                            "role": "fill_slot",
                            "field_id": "thesis.title.zh",
                        }
                    ],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role="fill_slot",
                            field_id="thesis.title.zh",
                        )
                    ],
                }
            ]
        },
    )
    judgment = review["semantic_judgments"][0]
    assert isinstance(judgment, dict)
    judgment.pop("source_entry_id")
    judgment["scope"] = {"reading_block_id": "u:block-0001"}
    review["semantic_judgments_sha256"] = sha256_json(review["semantic_judgments"])
    result = _compile_materialization_intents(review=review, registry=registry)

    blocker = result.unsupported[0]
    assert result.intents == ()
    assert blocker.reason_code == "materialization_scope_missing"
    assert blocker.missing_requirements == ("source_entry_id",)


@pytest.mark.parametrize(
    ("role", "intent_type", "field_id"),
    [
        ("fixed_label", MaterializationIntentType.KEEP_FIXED_CONTENT, None),
        ("cleanup", MaterializationIntentType.DELETE_BLOCK, None),
        ("manual_region", MaterializationIntentType.KEEP_MANUAL_TABLE_CELL, None),
        ("style_only", MaterializationIntentType.TRANSFER_STYLE_ONLY, None),
        ("generated_content", MaterializationIntentType.REFRESH_GENERATED_CONTENT, "generated.toc"),
    ],
)
def test_compiler_maps_ordered_part_roles(
    tmp_path: Path,
    role: str,
    intent_type: MaterializationIntentType,
    field_id: str | None,
) -> None:
    part: dict[str, object] = {"text": "x", "role": role}
    if field_id is not None:
        part["field_id"] = field_id
    result = compile_materialization_intents(
        review={
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u:block-0001"},
                    "parts": [part],
                    "resolved_spans": [
                        _span(
                            block_id="u:block-0001",
                            part_index=0,
                            role=role,
                            field_id=field_id,
                        )
                    ],
                }
            ]
        },
        registry=_registry(tmp_path),
    )

    assert result.ready is True
    assert result.intents[0].intent_type == intent_type
    assert result.unsupported == ()
