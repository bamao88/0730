from __future__ import annotations

from pathlib import Path

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.readiness import materialization_readiness_feedback
from docfit.template.source_spans import resolve_semantic_judgments
from docfit.tools.runtime import sha256_json
from tests.support.source_identity import review_binding, source_partition


def _registry(path: Path) -> FieldRegistrySnapshot:
    path.write_text(
        "\n".join(
            (
                "registry_id: test",
                "registry_version: '1'",
                "fields:",
                "  - field_id: thesis.title.zh",
                "    label: 中文题目",
                "    content_type: text",
                "  - field_id: body.chapters",
                "    label: 正文章节集合",
                "    content_type: section",
                "  - field_id: body.heading.outline1",
                "    label: 章标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.heading.outline4",
                "    label: 四级标题",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.paragraph",
                "    label: 正文段落",
                "    content_type: text",
                "    parent_field_id: body.chapters",
                "  - field_id: body.table",
                "    label: 表格",
                "    content_type: table",
                "    parent_field_id: body.chapters",
                "  - field_id: body.equation",
                "    label: 公式",
                "    content_type: equation",
                "    parent_field_id: body.chapters",
            )
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _current_case(
    registry: FieldRegistrySnapshot,
    *,
    role: str,
    field_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    document_sha256 = "a" * 64
    source_entry_id = "source-entry-title"
    text = "论文题目"
    object_id = "obj-title"
    fingerprint = "b" * 64
    locator = "/body/p[1]/r[1]"
    object_ref = {
        "document_sha256": document_sha256,
        "expected_fingerprint": fingerprint,
        "object_id": object_id,
    }
    vocabulary = registry.pre_input_vocabulary()
    inventory = {
        "document_sha256": document_sha256,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
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
        ],
        "objects": [
            {
                "object_id": object_id,
                "type": "run",
                "locator": locator,
                "source_entry_id": source_entry_id,
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        ],
        "reading_blocks": [],
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    agent_judgment = {
        "source_entry_id": source_entry_id,
        "parts": [{"text": text, "role": role, "field_id": field_id}],
    }
    source_partition(inventory)
    resolved_spans = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[agent_judgment],
    )
    accepted_judgments = [{**agent_judgment, "resolved_spans": resolved_spans}]
    review = {
        **review_binding(inventory),
        "document_sha256": document_sha256,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted_judgments,
        "semantic_judgments_sha256": sha256_json(accepted_judgments),
        "resolved_spans": resolved_spans,
    }
    return inventory, review


def test_readiness_allows_picture_cleanup_and_body_interface_on_same_paragraph(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "field-registry.yaml")
    document_sha256 = "a" * 64
    vocabulary = registry.pre_input_vocabulary()
    entries = [
        {
            "source_entry_id": "source-entry-empty-paragraph",
            "text": "",
            "entry_type": "text",
            "source_order": {"block": 1, "inline": 0},
            "provenance": [
                {
                    "object_id": "obj-paragraph",
                    "locator": "/body/p[@paraId=ABC]",
                    "extent": {"kind": "whole_entry"},
                    "fingerprint": "b" * 64,
                    "object_ref": {
                        "document_sha256": document_sha256,
                        "expected_fingerprint": "b" * 64,
                        "object_id": "obj-paragraph",
                    },
                }
            ],
        },
        {
            "source_entry_id": "source-entry-picture",
            "text": "",
            "entry_type": "picture",
            "source_order": {"block": 2, "inline": 0},
            "provenance": [
                {
                    "object_id": "obj-picture",
                    "locator": "/body/p[@paraId=ABC]/r[1]",
                    "extent": {"kind": "whole_entry"},
                    "fingerprint": "c" * 64,
                    "object_ref": {
                        "document_sha256": document_sha256,
                        "expected_fingerprint": "c" * 64,
                        "object_id": "obj-picture",
                    },
                }
            ],
        },
    ]
    inventory: dict[str, object] = {
        "document_sha256": document_sha256,
        "source_entries": entries,
        "objects": [
            {
                "object_id": "obj-paragraph",
                "type": "paragraph",
                "locator": "/body/p[@paraId=ABC]",
                "source_entry_id": "source-entry-empty-paragraph",
                "fingerprint": "b" * 64,
                "object_ref": {
                    "document_sha256": document_sha256,
                    "expected_fingerprint": "b" * 64,
                    "object_id": "obj-paragraph",
                },
            },
            {
                "object_id": "obj-picture",
                "type": "picture",
                "locator": "/body/p[@paraId=ABC]/r[1]",
                "source_entry_id": "source-entry-picture",
                "fingerprint": "c" * 64,
                "object_ref": {
                    "document_sha256": document_sha256,
                    "expected_fingerprint": "c" * 64,
                    "object_id": "obj-picture",
                },
            },
        ],
        "reading_blocks": [],
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    judgments = [
        {
            "source_entry_id": "source-entry-empty-paragraph",
            "parts": [
                {
                    "text": "",
                    "role": "body_structure",
                    "field_id": "body.heading.outline1",
                }
            ],
        },
        {
            "source_entry_id": "source-entry-picture",
            "parts": [{"text": "", "role": "cleanup"}],
        },
    ]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [
        {**judgment, "resolved_spans": [resolved[index]]}
        for index, judgment in enumerate(judgments)
    ]
    review: dict[str, object] = {
        **review_binding(inventory),
        "document_sha256": document_sha256,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is None
    assert review["semantic_judgments"] == accepted


def test_readiness_rejects_accepted_incompatible_body_role(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "field-registry.yaml")
    inventory, review = _current_case(
        registry,
        role="body_structure",
        field_id="thesis.title.zh",
    )
    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is not None
    assert feedback["status"] == "error"
    assert feedback["recovery"] == {
        "kind": "system_state_invalid", "owner": "harness", "action": "stop",
    }
    assert [item["code"] for item in feedback["blockers"]] == [
        "materialization_semantic_review_not_current",
    ]


def test_readiness_feedback_rejects_legacy_source_content_fields(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "field-registry.yaml")
    inventory, review = _current_case(
        registry,
        role="fill_slot",
        field_id="thesis.title.zh",
    )
    judgments = review["semantic_judgments"]
    assert isinstance(judgments, list)
    judgment = judgments[0]
    assert isinstance(judgment, dict)
    judgment["source_content_id"] = "legacy-content-1"
    review["semantic_judgments_sha256"] = sha256_json(judgments)
    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is not None
    assert feedback["status"] == "error"
    assert feedback["recovery"]["owner"] == "harness"
    blocker = feedback["blockers"][0]
    assert blocker["code"] == "materialization_semantic_review_not_current"
    assert blocker["missing_requirement"] == "current_accepted_semantic_review"


def test_readiness_rejects_multiple_body_members_on_one_top_level_carrier(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "field-registry.yaml")
    document_sha256 = "a" * 64
    vocabulary = registry.pre_input_vocabulary()
    entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    judgments: list[dict[str, object]] = []
    for index, (entry_id, text, locator) in enumerate(
        (
            (
                "source-entry-paragraph-part-a",
                "A",
                "/body/p[1]/r[1]",
            ),
            (
                "source-entry-paragraph-part-b",
                "B",
                "/body/p[1]/r[2]",
            ),
        ),
        start=1,
    ):
        object_id = f"obj-{index}"
        fingerprint = str(index) * 64
        object_ref = {
            "document_sha256": document_sha256,
            "expected_fingerprint": fingerprint,
            "object_id": object_id,
        }
        entries.append(
            {
                "source_entry_id": entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": index, "inline": 0},
                "provenance": [
                    {
                        "object_id": object_id,
                        "locator": locator,
                        "text_span": [0, 1],
                        "object_ref": object_ref,
                        "fingerprint": fingerprint,
                    }
                ],
            }
        )
        objects.append(
            {
                "object_id": object_id,
                "source_entry_id": entry_id,
                "type": "run",
                "locator": locator,
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        )
        judgments.append(
            {
                "source_entry_id": entry_id,
                "parts": [
                    {
                        "text": text,
                        "role": "body_structure",
                        "field_id": "body.heading.outline1",
                    }
                ],
            }
        )
    inventory: dict[str, object] = {
        "document_sha256": document_sha256,
        "source_entries": entries,
        "objects": objects,
        "reading_blocks": [],
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=judgments)
    accepted = [
        {**judgment, "resolved_spans": [resolved[index]]}
        for index, judgment in enumerate(judgments)
    ]
    review: dict[str, object] = {
        **review_binding(inventory),
        "document_sha256": document_sha256,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is not None
    conflict = next(
        blocker
        for blocker in feedback["blockers"]
        if blocker["code"] == "materialization_body_structure_carrier_conflict"
    )
    assert conflict["source_entry_ids"] == [
        "source-entry-paragraph-part-a",
        "source-entry-paragraph-part-b",
    ]
    assert "locator" not in conflict
    assert conflict["missing_requirement"] == "one_body_member_per_visible_carrier"


def test_readiness_accepts_ordered_inline_body_members_from_one_source_entry(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "field-registry.yaml")
    document_sha256 = "a" * 64
    vocabulary = registry.pre_input_vocabulary()
    source_entry_id = "source-entry-inline-heading-and-body"
    text = "□□（1）……[1]。（四级标题不单独占行）"
    object_id = "obj-inline-body"
    fingerprint = "b" * 64
    locator = "/body/p[1]/r[1]"
    object_ref = {
        "document_sha256": document_sha256,
        "expected_fingerprint": fingerprint,
        "object_id": object_id,
    }
    inventory: dict[str, object] = {
        "document_sha256": document_sha256,
        "source_entries": [
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
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
        ],
        "objects": [
            {
                "object_id": object_id,
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": locator,
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        ],
        "reading_blocks": [],
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    judgment = {
        "source_entry_id": source_entry_id,
        "parts": [
            {"text": "□□（1）", "role": "body_structure", "field_id": "body.heading.outline4"},
            {"text": "……[1]。", "role": "body_structure", "field_id": "body.paragraph"},
            {"text": "（四级标题不单独占行）", "role": "style_only"},
        ],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=[judgment])
    accepted = [{**judgment, "resolved_spans": resolved}]
    review: dict[str, object] = {
        **review_binding(inventory),
        "document_sha256": document_sha256,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is None


def test_readiness_rejects_field_binding_inside_composite_table(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "field-registry.yaml")
    document_sha256 = "a" * 64
    vocabulary = registry.pre_input_vocabulary()
    source_entry_id = "source-entry-equation-cell"
    object_id = "obj-equation"
    locator = "/body/tbl[1]/tr[1]/tc[1]/p[1]/r[1]"
    fingerprint = "b" * 64
    object_ref = {
        "document_sha256": document_sha256,
        "expected_fingerprint": fingerprint,
        "object_id": object_id,
    }
    entry = {
        "source_entry_id": source_entry_id,
        "text": "E=mc²",
        "entry_type": "equation",
        "source_order": {"block": 1, "inline": 0},
        "provenance": [
            {
                "object_id": object_id,
                "locator": locator,
                "text_span": [0, 5],
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        ],
    }
    judgment = {
        "source_entry_id": source_entry_id,
        "parts": [{"text": "E=mc²", "role": "body_structure", "field_id": "body.equation"}],
    }
    inventory: dict[str, object] = {
        "document_sha256": document_sha256,
        "source_entries": [entry],
        "objects": [
            {
                "object_id": object_id,
                "source_entry_id": source_entry_id,
                "type": "run",
                "locator": locator,
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        ],
        "reading_blocks": [],
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
    }
    source_partition(inventory)
    resolved = resolve_semantic_judgments(inventory=inventory, judgments=[judgment])
    accepted = [{**judgment, "resolved_spans": resolved}]
    review: dict[str, object] = {
        **review_binding(inventory),
        "document_sha256": document_sha256,
        "field_id_vocabulary": vocabulary,
        "field_vocabulary_digest": vocabulary["digest"],
        "semantic_judgments": accepted,
        "semantic_judgments_sha256": sha256_json(accepted),
        "resolved_spans": resolved,
    }

    feedback = materialization_readiness_feedback(
        inventory=inventory,
        review=review,
        registry=registry,
    )

    assert feedback is not None
    blocker = next(
        item
        for item in feedback["blockers"]
        if item["code"] == "materialization_body_structure_nested_composite_member"
    )
    assert blocker["source_entry_id"] == source_entry_id
    assert blocker["field_id"] == "body.equation"
    assert feedback["status"] == "error"
    assert feedback["recovery"]["action"] == "stop"
    assert feedback["recovery"]["owner"] == "tool"
    assert review["semantic_judgments"] == accepted
    assert "locator" not in blocker
