from __future__ import annotations

import json
from pathlib import Path

import pytest

from docfit.template.harness import TemplateHarnessService
from docfit.template.reading_packet import (
    agent_visible_unit_reading_packet,
    build_unit_reading_packet,
)
from docfit.tools import inspection
from docfit.tools.inspection import InspectedObject
from docfit.tools.runtime import ToolFailure


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
            )
        ),
        encoding="utf-8",
    )


def _object_ref(document_sha256: str, suffix: str) -> dict[str, str]:
    return {
        "document_sha256": document_sha256,
        "object_id": f"obj-{int(suffix):024d}",
        "expected_fingerprint": suffix * 64,
    }


def test_public_inspection_object_does_not_publish_component_source_entry_alias() -> None:
    source_sha256 = "a" * 64
    fingerprint = "b" * 64
    object_id = "obj-000000000000000000000001"
    inspected = InspectedObject(
        locator="/body/p[1]/r[1]",
        kind="run",
        text="论文题目",
        style="Title",
        format={"bold": True},
        object_ref={
            "document_sha256": source_sha256,
            "object_id": object_id,
            "expected_fingerprint": fingerprint,
        },
    )

    public = inspected.public()
    assert not hasattr(inspection, "source_entry_id_for")
    assert not hasattr(inspection, "source_entry_ref_for")
    assert "source_entry_id" not in public
    assert "source_entry_ref" not in public
    assert public["object_id"] == object_id
    assert "object_id_alias_for" not in public
    assert public["object_ref"]["object_id"] == object_id


def test_harness_rejects_inspection_component_source_entry_alias_as_canonical(
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir()
    _write_registry(task_root)
    document_sha256 = "a" * 64
    harness = TemplateHarnessService(task_root=task_root)

    with pytest.raises(ToolFailure) as caught:
        harness.handle(
            {
                "action": "submit_object_inventory",
                "document_sha256": document_sha256,
                "objects": [
                    {
                        "source_entry_id": "source-entry-component-credential",
                        "source_entry_ref": {
                            "source_entry_id": "source-entry-component-credential",
                            "source_sha256": document_sha256,
                            "locator": "/body/p[1]",
                            "type": "paragraph",
                            "expected_fingerprint": "1" * 64,
                        },
                        "type": "paragraph",
                        "locator": "/body/p[1]",
                        "object_ref": _object_ref(document_sha256, "1"),
                    }
                ],
                "reading_blocks": [],
            }
        )

    assert caught.value.code == "initial_source_binding_invalid"


def test_reading_packet_keeps_source_entry_mapping_internal() -> None:
    packet = build_unit_reading_packet(
        unit={"unit_id": "u-cover", "unit_name": "封面"},
        scoped_objects=[
            {
                "type": "paragraph",
                "locator": "/body/p[1]",
                "text": "论文题目",
                "object_ref": {"object_id": "obj-paragraph"},
                "source_entry_id": "source-entry-paragraph",
            },
            {
                "type": "run",
                "locator": "/body/p[1]/r[1]",
                "text": "论文题目",
                "object_ref": {"object_id": "obj-run"},
                "source_entry_id": "source-entry-run",
            },
        ],
    )

    mapping = packet["reading_block_mappings"][0]
    assert mapping["covered_source_entry_ids"] == [
        "source-entry-paragraph",
        "source-entry-run",
    ]
    assert mapping["source_entry_text_spans"] == [
        {
            "text_start": 0,
            "text_end": 4,
            "text": "论文题目",
            "source_entry_id": "source-entry-run",
        }
    ]

    visible = agent_visible_unit_reading_packet(packet)
    encoded = json.dumps(visible, ensure_ascii=False)
    assert "covered_source_entry_ids" not in encoded
    assert "source_entry_text_spans" not in encoded
