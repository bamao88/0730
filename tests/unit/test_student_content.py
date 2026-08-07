from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest
import yaml

from docfit.app.student_content_fill import _force_inline_inspection
from docfit.content.extraction import extraction_output_schema, validate_extraction
from docfit.content.placement import build_placement
from docfit.content.student import build_student_inventory
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import ToolFailure, sha256_file


def _inspection() -> Inspection:
    objects = (
        _object("obj-title", "/body/p[@paraId=00000001]", "A verified title"),
        _object("obj-body-1", "/body/p[@paraId=00000002]", "1 Introduction"),
        _object("obj-picture", "/body/p[@paraId=00000002]/r[1]/drawing[1]", ""),
        _object("obj-body-2", "/body/p[@paraId=00000003]", "Body text"),
        _object("obj-ref", "/body/p[@paraId=00000004]", "References"),
    )
    return Inspection("a" * 64, objects, {"paragraphs": 4, "images": 1}, (), (), {})


def _object(object_id: str, locator: str, text: str) -> InspectedObject:
    kind = "picture" if "drawing" in locator else "table" if "/tbl[" in locator else "paragraph"
    return InspectedObject(
        locator,
        kind,
        text,
        "Normal",
        {},
        {
            "document_sha256": "a" * 64,
            "object_id": object_id,
            "expected_fingerprint": object_id,
        },
    )


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.1.0",
                "fields": [
                    {"field_id": "thesis.title.en", "content_type": "text"},
                    {"field_id": "body.chapters", "content_type": "section"},
                    {"field_id": "references.entries", "content_type": "rich_text"},
                    {"field_id": "acknowledgement.body", "content_type": "rich_text"},
                    {"field_id": "appendix.body", "content_type": "section"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _agent_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "fields": [
            {
                "field_id": "thesis.title.en",
                "status": "extracted",
                "value": "A verified title",
                "source_object_ids": ["obj-title"],
                "confidence": 0.99,
                "note": "Exact visible title.",
            }
        ],
        "segments": [
            {
                "field_id": "body.chapters",
                "status": "extracted",
                "start_object_id": "obj-body-1",
                "end_object_id": "obj-body-2",
                "confidence": 0.9,
                "note": "Continuous body range.",
            },
            {
                "field_id": "references.entries",
                "status": "extracted",
                "start_object_id": "obj-ref",
                "end_object_id": "obj-ref",
                "confidence": 0.95,
                "note": "Reference range.",
            },
        ],
        "unmapped_object_ids": ["obj-picture"],
        "summary": "Synthetic extraction.",
        "uncertainties": [],
    }


def test_inventory_covers_objects_without_treating_nested_picture_as_transferable() -> None:
    inventory = build_student_inventory(_inspection())

    assert inventory["object_count"] == 5
    assert inventory["transferable_object_count"] == 4
    assert len({item["content_id"] for item in inventory["objects"]}) == 5
    picture = inventory["objects"][2]
    assert picture["content_type"] == "image"
    assert picture["transferable"] is False


def test_inventory_uses_ooxml_body_order_for_paragraph_table_interleaving(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    document_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
 <w:body>
  <w:p w14:paraId="00000001"><w:r><w:t>Start</w:t></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  <w:p w14:paraId="00000002"><w:r><w:t>End</w:t></w:r></w:p>
  <w:sectPr/>
 </w:body>
</w:document>"""
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    inspection = Inspection(
        "a" * 64,
        (
            _object("obj-start", "/body/p[@paraId=00000001]", "Start"),
            _object("obj-end", "/body/p[@paraId=00000002]", "End"),
            _object("obj-table", "/body/tbl[1]", "Table"),
        ),
        {},
        (),
        (),
        {},
    )
    inventory = build_student_inventory(inspection, source_docx=source)
    order = {
        item["source_object_ref"]["object_id"]: item["body_sequence"]
        for item in inventory["objects"]
    }

    assert order == {"obj-start": 1, "obj-end": 3, "obj-table": 2}
    payload = {
        "schema_version": 1,
        "fields": [],
        "segments": [
            {
                "field_id": "body.chapters",
                "status": "extracted",
                "start_object_id": "obj-start",
                "end_object_id": "obj-end",
                "confidence": 1.0,
                "note": "Synthetic mixed body.",
            }
        ],
        "unmapped_object_ids": [],
        "summary": "Synthetic.",
        "uncertainties": [],
    }
    actual = validate_extraction(
        payload,
        inventory=inventory,
        registry=_registry(tmp_path),
        expected_field_ids=(),
    )
    body = next(item for item in actual["segments"] if item["field_id"] == "body.chapters")
    assert body["source_object_ids"] == ["obj-start", "obj-table", "obj-end"]


def test_extraction_schema_avoids_composition_keywords() -> None:
    schema = extraction_output_schema(("thesis.title.en",))
    rendered = str(schema)

    assert "oneOf" not in rendered
    assert "anyOf" not in rendered
    assert "allOf" not in rendered


def test_extraction_expands_transferable_ranges_and_normalizes_omissions(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    actual = validate_extraction(
        _agent_payload(),
        inventory=build_student_inventory(_inspection()),
        registry=registry,
        expected_field_ids=("thesis.title.en",),
    )

    body = next(item for item in actual["segments"] if item["field_id"] == "body.chapters")
    assert body["source_object_ids"] == ["obj-body-1", "obj-body-2"]
    assert all("drawing" not in value for value in body["source_locators"])
    acknowledgement = next(
        item for item in actual["segments"] if item["field_id"] == "acknowledgement.body"
    )
    assert acknowledgement["status"] == "missing"


def test_extraction_rejects_untraceable_agent_value(tmp_path: Path) -> None:
    payload = _agent_payload()
    payload["fields"][0]["value"] = "invented title"  # type: ignore[index]

    with pytest.raises(ToolFailure, match="not present") as failure:
        validate_extraction(
            payload,
            inventory=build_student_inventory(_inspection()),
            registry=_registry(tmp_path),
            expected_field_ids=("thesis.title.en",),
        )

    assert failure.value.code == "student_extraction_value_untraceable"


def test_missing_field_may_cite_review_evidence_without_becoming_fill_value(
    tmp_path: Path,
) -> None:
    payload = _agent_payload()
    field = payload["fields"][0]  # type: ignore[index]
    field["status"] = "missing"
    field["value"] = None

    actual = validate_extraction(
        payload,
        inventory=build_student_inventory(_inspection()),
        registry=_registry(tmp_path),
        expected_field_ids=("thesis.title.en",),
    )

    assert actual["fields"][0]["status"] == "missing"
    assert actual["fields"][0]["source_object_ids"] == ["obj-title"]


def test_extraction_hook_removes_inspection_output_side_effect() -> None:
    result = asyncio.run(
        _force_inline_inspection(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "mcp__docfit__docx_inspect",
                "tool_input": {"input_docx": "input/student.docx", "output": "full"},
            },  # type: ignore[arg-type]
            None,
            None,  # type: ignore[arg-type]
        )
    )

    updated = result["hookSpecificOutput"]["updatedInput"]
    assert updated == {"input_docx": "input/student.docx"}


def test_extraction_rejects_overlapping_semantic_segments(tmp_path: Path) -> None:
    payload = _agent_payload()
    payload["segments"][1]["start_object_id"] = "obj-body-2"  # type: ignore[index]

    with pytest.raises(ToolFailure) as failure:
        validate_extraction(
            payload,
            inventory=build_student_inventory(_inspection()),
            registry=_registry(tmp_path),
            expected_field_ids=("thesis.title.en",),
        )

    assert failure.value.code == "student_extraction_segment_overlap"


def test_placement_maps_body_once_and_leaves_required_missing_explicit(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    student_content = validate_extraction(
        _agent_payload(),
        inventory=build_student_inventory(_inspection()),
        registry=registry,
        expected_field_ids=("thesis.title.en",),
    )
    template = tmp_path / "template.docx"
    template.write_bytes(b"hash-bound synthetic template")
    contract = {
        "contract_id": "synthetic",
        "revision": "1",
        "status": "candidate_pending_human_acceptance",
        "template_sha256": sha256_file(template),
        "contract_sha256": "c" * 64,
        "field_registry_ref": registry.identity(),
        "regions": [{"region_id": "region.generated.toc", "required": True}],
        "slots": [
            _slot("slot.title", "thesis.title.en", "docfit.cover.title_en", True),
            _slot("slot.body.title", "body.heading.level1", "docfit.body.chapter_title", True),
            _slot("slot.body.text", "body.paragraph", "docfit.body.chapter_body", True),
            _slot("slot.missing", "thesis.title.en", "docfit.other.title", False),
        ],
    }

    placement = build_placement(
        student_content=student_content,
        contract=contract,
        registry=registry,
        template_docx=template,
    )

    assert placement["status"] == "PARTIAL"
    body_operations = [
        item for item in placement["operations"] if item["field_id"] == "body.chapters"
    ]
    assert len(body_operations) == 1
    assert body_operations[0]["tag"] == "docfit.body.chapter_title"
    assert "template_fill_contract_not_human_accepted" in placement["partial_reasons"]


def test_placement_rejects_stale_template_hash(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")

    with pytest.raises(ToolFailure) as failure:
        build_placement(
            student_content={"registry": registry.identity(), "fields": [], "segments": []},
            contract={"template_sha256": "0" * 64},
            registry=registry,
            template_docx=template,
        )

    assert failure.value.code == "placement_template_stale"


def _slot(slot_id: str, field_id: str, tag: str, required: bool) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "field_id": field_id,
        "required": required,
        "locator": {"type": "content_control_tag", "value": tag},
    }
