from __future__ import annotations

from pathlib import Path

import pytest

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import sha256_json
from tests.support.source_identity import review_binding, source_partition


def _write_registry(root: Path) -> FieldRegistrySnapshot:
    path = root / "field-registry.yaml"
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
                "  - field_id: appendix.body",
                "    label: 附录内容",
                "    content_type: section",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _inventory() -> dict[str, object]:
    inventory = {
        "document_sha256": "a" * 64,
        "objects": [
            {"object_id": "obj-slot", "type": "run", "locator": "/body/p[1]/r[1]"},
            {"object_id": "obj-form", "type": "table", "locator": "/body/tbl[1]"},
        ],
        "reading_blocks": [
            {
                "block_id": "u:block-0001",
                "range_id": "u:range-0001",
                "unit_id": "u",
                "text": "论文题目：×××",
                "covered_object_ids": ["obj-slot"],
            },
            {
                "block_id": "u:block-0002",
                "range_id": "u:range-0002",
                "unit_id": "u",
                "text": "开题报告表",
                "covered_object_ids": ["obj-form"],
            },
        ],
    }
    return inventory


def _span(
    *,
    block_id: str,
    part_index: int,
    role: str,
    field_id: str | None = None,
) -> dict[str, object]:
    span_ref = f"reading_block_id={block_id};part_index={part_index}"
    span: dict[str, object] = {
        "span_ref": span_ref,
        "scope": {"reading_block_id": block_id},
        "reading_block_id": block_id,
        "part_index": part_index,
        "role": role,
        "text": "x",
    }
    if field_id is not None:
        span["field_id"] = field_id
        span["slot_ref"] = f"{span_ref};field_id={field_id}"
    return span


def _judgment(
    *,
    block_id: str = "u:block-0001",
    role: str = "fill_slot",
    field_id: str | None = "thesis.title.zh",
    resolved_spans: bool = True,
    part_extra: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    part: dict[str, object] = {"text": "x", "role": role}
    if field_id is not None:
        part["field_id"] = field_id
    if part_extra:
        part.update(part_extra)
    judgment: dict[str, object] = {
        "scope": {"reading_block_id": block_id},
        "parts": [part],
    }
    if resolved_spans:
        judgment["resolved_spans"] = [
            _span(block_id=block_id, part_index=0, role=role, field_id=field_id)
        ]
    if extra:
        judgment.update(extra)
    return judgment


def _feedback(
    tmp_path: Path,
    judgments: list[dict[str, object]],
    *,
    inventory: dict[str, object] | None = None,
    with_vocabulary: bool = True,
    stale_inventory: bool = False,
) -> dict[str, object] | None:
    registry = _write_registry(tmp_path)
    source_snapshot_sha256 = "a" * 64
    current_inventory = dict(inventory or {})
    accepted_judgments: list[dict[str, object]] = []
    keep_resolved_spans: list[bool] = []
    source_entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    for index, raw_judgment in enumerate(judgments):
        judgment = dict(raw_judgment)
        keep_resolved_spans.append("resolved_spans" in raw_judgment)
        source_entry_id = f"source-entry-test-{index:04d}"
        judgment["source_entry_id"] = source_entry_id
        judgment.pop("scope", None)
        judgment.pop("resolved_spans", None)
        parts = judgment.get("parts")
        text = (
            "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
            if isinstance(parts, list)
            else ""
        )
        object_id = f"obj-{index:04d}"
        fingerprint = f"{index + 1:064x}"
        locator = f"/body/p[{index + 1}]/r[1]"
        object_ref = {
            "document_sha256": source_snapshot_sha256,
            "expected_fingerprint": fingerprint,
            "object_id": object_id,
        }
        source_entries.append(
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": index, "inline": 0},
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
        accepted_judgments.append(judgment)
    current_inventory.update(
        {
            "document_sha256": source_snapshot_sha256,
            "source_entries": source_entries,
            "objects": objects,
            "reading_blocks": [],
        }
    )
    try:
        source_partition(current_inventory)
        resolved = resolve_semantic_judgments(
            inventory=current_inventory,
            judgments=accepted_judgments,
        )
    except ValueError:
        resolved = []
    for index, judgment in enumerate(accepted_judgments):
        judgment["resolved_spans"] = (
            [span for span in resolved if span.get("judgment_index") == index]
            if keep_resolved_spans[index]
            else []
        )
    review: dict[str, object] = {
        **(
            review_binding(current_inventory)
            if "unit_projection_digest" in current_inventory
            else {}
        ),
        "semantic_judgments": accepted_judgments,
    }
    if with_vocabulary:
        vocabulary = registry.pre_input_vocabulary()
        current_inventory["field_id_vocabulary"] = vocabulary
        current_inventory["field_vocabulary_digest"] = vocabulary["digest"]
        review["field_id_vocabulary"] = vocabulary
        review["field_vocabulary_digest"] = vocabulary["digest"]
    review["document_sha256"] = source_snapshot_sha256
    review["semantic_judgments_sha256"] = sha256_json(accepted_judgments)
    review["resolved_spans"] = [
        span
        for index, judgment in enumerate(accepted_judgments)
        if keep_resolved_spans[index]
        for span in judgment["resolved_spans"]
    ]
    if stale_inventory:
        source_entry = current_inventory["source_entries"][0]
        assert isinstance(source_entry, dict)
        provenance = source_entry["provenance"][0]
        assert isinstance(provenance, dict)
        provenance["locator"] = "/body/p[999]/r[1]"
    return materialization_readiness_feedback(
        inventory=current_inventory,
        review=review,
        registry=registry,
    )


def _codes(feedback: dict[str, object]) -> list[str]:
    blockers = feedback.get("blockers")
    assert isinstance(blockers, list)
    return [str(blocker["code"]) for blocker in blockers if isinstance(blocker, dict)]


def test_materialization_readiness_accepts_resolved_ordered_slot(tmp_path: Path) -> None:
    assert _feedback(tmp_path, [_judgment()]) is None


def test_materialization_readiness_requires_accepted_field_vocabulary(
    tmp_path: Path,
) -> None:
    feedback = _feedback(tmp_path, [_judgment()], with_vocabulary=False)

    assert feedback is not None
    assert _codes(feedback) == [
        "materialization_field_vocabulary_provenance_missing",
        "materialization_field_vocabulary_provenance_missing",
    ]


def test_materialization_readiness_blocks_registry_field_outside_accepted_vocabulary(
    tmp_path: Path,
) -> None:
    registry = _write_registry(tmp_path)
    inventory = _inventory()
    vocabulary = registry.pre_input_vocabulary(allowed_field_ids=("advisor.name.zh",))
    inventory["field_id_vocabulary"] = vocabulary
    inventory["field_vocabulary_digest"] = vocabulary["digest"]
    review = {
        "semantic_judgments": [_judgment(field_id="thesis.title.zh")],
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }

    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is not None
    assert _codes(feedback) == ["materialization_field_not_in_vocabulary"]


def test_materialization_readiness_blocks_unresolved_questions(tmp_path: Path) -> None:
    feedback = _feedback(
        tmp_path,
        [_judgment(extra={"open_questions": ["which field should this be?"]})],
    )

    assert feedback is not None
    assert "materialization_semantic_judgment_unresolved" in _codes(feedback)


def test_materialization_readiness_blocks_legacy_shape(tmp_path: Path) -> None:
    feedback = _feedback(
        tmp_path,
        [
            {
                "judgment_id": "j-old",
                "semantic_role": "fill_slot",
                "clean_template_treatment": "convert_to_field_slot",
                "registry_field": "thesis.title.zh",
                "covered_reading_block_ids": ["u:block-0001"],
            }
        ],
    )

    assert feedback is not None
    assert _codes(feedback) == ["materialization_semantic_review_not_current"]


@pytest.mark.parametrize(
    "legacy_part_shape",
    [
        {"registry_field": "thesis.title.zh"},
        {"bound_field_ids": ["thesis.title.zh"]},
        {"field_ids": ["thesis.title.zh"]},
        {"covered_object_ids": ["obj-slot"]},
        {"locator": "/body/p[1]/r[1]"},
        {"span_ref": "reading_block_id=u:block-0001;part_index=0"},
    ],
)
def test_materialization_readiness_blocks_legacy_part_shape(
    tmp_path: Path,
    legacy_part_shape: dict[str, object],
) -> None:
    feedback = _feedback(tmp_path, [_judgment(part_extra=legacy_part_shape)])

    assert feedback is not None
    assert _codes(feedback) in (
        ["materialization_semantic_review_not_current"],
        ["materialization_legacy_shape_unsupported"],
    )
    blockers = feedback.get("blockers")
    assert isinstance(blockers, list)
    assert isinstance(blockers[0], dict)
    if blockers[0]["code"] == "materialization_legacy_shape_unsupported":
        assert blockers[0]["legacy_part_fields"]


def test_materialization_readiness_blocks_missing_part_field_id(tmp_path: Path) -> None:
    feedback = _feedback(tmp_path, [_judgment(field_id=None)])

    assert feedback is not None
    assert _codes(feedback) == ["materialization_semantic_review_not_current"]


def test_materialization_readiness_blocks_unknown_part_field_id(tmp_path: Path) -> None:
    feedback = _feedback(tmp_path, [_judgment(field_id="unknown.field")])

    assert feedback is not None
    assert _codes(feedback) == ["materialization_field_not_in_vocabulary"]


def test_materialization_readiness_rejects_review_with_invalid_field_role(
    tmp_path: Path,
) -> None:
    feedback = _feedback(tmp_path, [_judgment(field_id="body.heading.outline1")])

    # Field-role compatibility is checked before accepting a semantic review.
    # Materialization must reject that invalid review rather than execute it.
    assert feedback is not None
    assert _codes(feedback) == ["materialization_semantic_review_not_current"]


def test_materialization_readiness_accepts_leaf_section_as_fillable_slot(
    tmp_path: Path,
) -> None:
    assert _feedback(tmp_path, [_judgment(field_id="appendix.body")]) is None


def test_materialization_readiness_blocks_executable_part_without_resolved_span(
    tmp_path: Path,
) -> None:
    feedback = _feedback(tmp_path, [_judgment(resolved_spans=False)])

    assert feedback is not None
    assert _codes(feedback) == ["materialization_semantic_review_not_current"]


def test_materialization_readiness_blocks_stale_resolved_fragments(
    tmp_path: Path,
) -> None:
    feedback = _feedback(tmp_path, [_judgment()], stale_inventory=True)

    assert feedback is not None
    assert _codes(feedback) == ["materialization_semantic_review_not_current"]


def test_materialization_readiness_accepts_generated_content_with_field_and_span(
    tmp_path: Path,
) -> None:
    assert (
        _feedback(
            tmp_path,
            [_judgment(role="generated_content", field_id="generated.toc")],
        )
        is None
    )


def test_materialization_readiness_accepts_body_structure_with_registry_parent(
    tmp_path: Path,
) -> None:
    assert (
        _feedback(
            tmp_path,
            [_judgment(role="body_structure", field_id="body.heading.outline1")],
        )
        is None
    )


def test_materialization_readiness_accepts_disjoint_body_members_for_one_source_entry(
    tmp_path: Path,
) -> None:
    feedback = _feedback(
        tmp_path,
        [
            {
                "parts": [
                    {
                        "text": "×××",
                        "role": "body_structure",
                        "field_id": "body.paragraph",
                    },
                    {"text": "（正文小四宋体）", "role": "style_only"},
                    {
                        "text": "×××",
                        "role": "body_structure",
                        "field_id": "body.paragraph",
                    },
                ],
                "resolved_spans": [],
            }
        ],
    )

    assert feedback is None


def test_materialization_readiness_does_not_merge_targets_by_old_reading_scope(
    tmp_path: Path,
) -> None:
    feedback = _feedback(
        tmp_path,
        [
            _judgment(block_id="u:block-0002", role="manual_region", field_id=None),
            _judgment(block_id="u:block-0002", role="fill_slot", field_id="advisor.name.zh"),
        ],
    )

    assert feedback is None
