from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfit.template.harness import TemplateHarnessService
from docfit.tools.runtime import ToolFailure
from tests.support.source_identity import persist_source_identity, source_partition

SOURCE_HASH = "39631bb5e5dc9326b23f8c00bf43440a84ce711315c6b799de554c56aa04d133"
SOURCE_ENTRY_ID = "source-entry-cover-title"


def _write_registry(task_root: Path) -> None:
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


def _submit_current_inventory(harness: TemplateHarnessService) -> None:
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
        "source_entries": [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "text": "作者张三",
                "entry_type": "text",
                "source_order": {"block": 1, "inline": 0},
                "provenance": [
                    {
                        "object_id": "obj-label",
                        "locator": "/body/p[1]/r[1]",
                        "text_span": [0, 2],
                    },
                    {
                        "object_id": "obj-value",
                        "locator": "/body/p[1]/r[2]",
                        "text_span": [2, 4],
                    },
                ],
            }
        ],
        "objects": [
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-label",
                    "expected_fingerprint": "b" * 64,
                },
            },
            {
                "source_entry_id": SOURCE_ENTRY_ID,
                "type": "run",
                "locator": "/body/p[1]/r[2]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-value",
                    "expected_fingerprint": "c" * 64,
                },
            },
        ],
        "reading_blocks": [
            {
                "unit_id": "u-cover",
                "block_id": "u-cover:block-0001",
                "range_id": "u-cover:range-0001",
                "order": 7,
                "text": "作者张三",
                "covered_object_ids": ["obj-label", "obj-value"],
                "covered_source_entry_ids": [SOURCE_ENTRY_ID],
                "object_text_spans": [
                    {
                        "object_id": "obj-label",
                        "text": "作者",
                        "text_start": 0,
                        "text_end": 2,
                    },
                    {
                        "object_id": "obj-value",
                        "text": "张三",
                        "text_start": 2,
                        "text_end": 4,
                    },
                ],
            }
        ],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    harness.handle(inventory)


def test_harness_resolves_source_entry_parts_and_keeps_reading_blocks_as_context(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    _submit_current_inventory(harness)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "document_sha256": SOURCE_HASH,
            "semantic_judgments": [
                {
                    "source_entry_id": SOURCE_ENTRY_ID,
                    "parts": [
                        {"text": "作者", "role": "fixed_label"},
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
    assert result["harness_state"]["covered_object_count"] == 2
    inventory = json.loads(
        (task_root / "work/.docfit/harness/object-inventory.json").read_text(encoding="utf-8")
    )
    review = json.loads(
        (task_root / "work/.docfit/harness/semantic-judgments.json").read_text(encoding="utf-8")
    )
    assert inventory["reading_blocks"][0]["order"] == 7
    assert review["field_vocabulary_digest"] == inventory["field_vocabulary_digest"]
    assert [span["word_fragments"][0]["object_id"] for span in review["resolved_spans"]] == [
        "obj-label",
        "obj-value",
    ]
    assert review["resolved_spans"][1]["extent"] == {
        "kind": "text",
        "start": 2,
        "end": 4,
    }


def test_harness_rejects_retired_reading_block_scope_without_conversion(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    _submit_current_inventory(harness)

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "semantic_judgments": [
                {
                    "scope": {"reading_block_id": "u-cover:block-0001"},
                    "parts": [{"text": "作者张三", "role": "fixed_label"}],
                }
            ],
        }
    )

    assert result["status"] == "needs_input"
    assert result["blockers"][0]["code"] == "legacy_reading_scope_unsupported"


def test_harness_does_not_accept_object_only_inventory_as_semantic_coverage(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    with pytest.raises(ToolFailure) as caught:
        harness.handle(
            {
                "action": "submit_object_inventory",
                "document_sha256": SOURCE_HASH,
                "objects": [
                    {
                        "type": "run",
                        "locator": "/body/p[1]/r[1]",
                        "object_ref": {
                            "document_sha256": SOURCE_HASH,
                            "object_id": "obj-only",
                            "expected_fingerprint": "b" * 64,
                        },
                    }
                ],
            }
        )
    assert caught.value.code == "initial_source_binding_invalid"
    assert not (task_root / "work/.docfit/harness/object-inventory.json").exists()


def test_harness_requires_and_persists_explicit_whole_entry_structural_judgment(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    harness = TemplateHarnessService(task_root=task_root)
    inventory = {
        "action": "submit_object_inventory",
        "document_sha256": SOURCE_HASH,
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
                "source_entry_id": "source-entry-break",
                "type": "break",
                "locator": "/body/p[1]/r[1]/br[1]",
                "object_ref": {
                    "document_sha256": SOURCE_HASH,
                    "object_id": "obj-break",
                    "expected_fingerprint": "d" * 64,
                },
            }
        ],
        "reading_blocks": [],
    }
    source_partition(inventory)
    persist_source_identity(harness._task_root, inventory)
    inventory_result = harness.handle(inventory)
    assert inventory_result["status"] == "ok"

    missing = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "semantic_judgments": [],
        }
    )
    assert missing["status"] == "needs_input"

    result = harness.handle(
        {
            "action": "submit_semantic_judgments",
            "semantic_judgments": [
                {
                    "source_entry_id": "source-entry-break",
                    "parts": [{"text": "", "role": "style_only"}],
                }
            ],
        }
    )

    assert result["status"] == "ok"
    review = json.loads(
        (task_root / "work/.docfit/harness/semantic-judgments.json").read_text(encoding="utf-8")
    )
    span = review["resolved_spans"][0]
    assert span["extent"] == {"kind": "whole_entry"}
    assert span["word_fragments"][0]["extent"] == {"kind": "whole_entry"}
    assert span["covered_object_ids"] == ["obj-break"]
