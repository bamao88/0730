from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml

from docfit.app.student_content_fill import _document_visible_text
from docfit.content.extraction import extraction_output_schema, validate_extraction
from docfit.content.placement import build_placement, load_fill_contract
from docfit.content.student import build_student_inventory
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.styles import style_contract_digest
from docfit.tools.inspection import InspectedObject, Inspection
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _inspection() -> Inspection:
    body = "/body/p[@paraId=00000002]"
    return Inspection(
        "a" * 64,
        (
            _object("obj-title", "/body/p[@paraId=00000001]", "A verified title"),
            _object("obj-body-1", body, "1 Introduction"),
            _object("obj-picture", f"{body}/r[1]/drawing[1]", ""),
            _object("obj-body-2", "/body/p[@paraId=00000003]", "Body text"),
            _object("obj-ref", "/body/p[@paraId=00000004]", "Reference entry"),
        ),
        {"paragraphs": 4, "images": 1},
        (),
        (),
        {},
    )


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
                    _field("thesis.title.en", "text"),
                    _field("body.heading.outline1", "text"),
                    _field("body.paragraph", "rich_text"),
                    _field("body.figure", "image"),
                    _field("body.table", "table"),
                    _field("body.equation", "equation"),
                    _field("references.entries", "rich_text"),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return FieldRegistrySnapshot.load(path)


def _field(field_id: str, content_type: str) -> dict[str, str]:
    return {
        "field_id": field_id,
        "label": field_id,
        "meaning": f"Semantic meaning of {field_id}.",
        "content_type": content_type,
    }


def _student_content(tmp_path: Path) -> tuple[dict[str, object], FieldRegistrySnapshot]:
    inventory = build_student_inventory(_inspection())
    ids = [item["source_content_id"] for item in inventory["content_items"]]
    fields = (
        "thesis.title.en",
        "body.figure",
        "body.heading.outline1",
        "body.paragraph",
        "references.entries",
    )
    payload = {
        "schema_version": 3,
        "annotations": [
            {
                "source_content_id": content_id,
                "classification_status": "classified",
                "field_id": field_id,
                "confidence": 1.0,
                "note": "Synthetic exact annotation.",
            }
            for content_id, field_id in zip(ids, fields, strict=True)
        ],
        "relations": [],
        "summary": "Synthetic.",
        "uncertainties": [],
    }
    registry = _registry(tmp_path)
    return validate_extraction(payload, inventory=inventory, registry=registry), registry


def test_inventory_keeps_nested_picture_as_a_separate_ordered_content_item() -> None:
    inventory = build_student_inventory(_inspection())

    assert inventory["object_count"] == 5
    assert inventory["content_item_count"] == 5
    picture = inventory["content_items"][1]
    assert picture["physical_type"] == "image"
    assert picture["source_order"] == {"block": 2, "inline": 0}
    assert picture["transport_source_object_id"] == "obj-body-1"
    assert "field_id" not in picture


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

    assert [
        (item["physical_type"], item["source_order"]["block"])
        for item in inventory["content_items"]
    ] == [("text", 1), ("table", 2), ("text", 3)]


def test_inventory_synthesizes_formula_only_top_level_paragraphs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "student.docx"
    math_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    document_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
 xmlns:m="{math_namespace}">
 <w:body>
  <w:p w14:paraId="00000001"><w:r><w:t>Start</w:t></w:r></w:p>
  <w:p w14:paraId="00000002"><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p>
  <w:p w14:paraId="00000003"><w:r><w:t>End</w:t></w:r></w:p>
  <w:sectPr/>
 </w:body>
</w:document>""".encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    inspection = Inspection(
        "a" * 64,
        (
            _object("obj-start", "/body/p[@paraId=00000001]", "Start"),
            _object("obj-end", "/body/p[@paraId=00000003]", "End"),
        ),
        {"equations": 1},
        (),
        (),
        {},
    )

    inventory = build_student_inventory(inspection, source_docx=source)

    assert [item["physical_type"] for item in inventory["content_items"]] == [
        "text",
        "equation",
        "text",
    ]
    assert inventory["synthetic_transferable_object_count"] == 1


def test_extraction_schema_contains_no_agent_order_or_composition_keywords(
    tmp_path: Path,
) -> None:
    inventory = build_student_inventory(_inspection())
    schema = extraction_output_schema(inventory, _registry(tmp_path))
    rendered = str(schema)

    assert schema["properties"]["schema_version"] == {"const": 3}
    assert "source_order" not in str(schema["properties"]["annotations"])
    assert "value" not in schema["properties"]["annotations"]["items"]["properties"]
    assert all(keyword not in rendered for keyword in ("oneOf", "anyOf", "allOf"))


def test_postprocessing_owns_source_value_and_ignores_legacy_agent_value(
    tmp_path: Path,
) -> None:
    inventory = build_student_inventory(_inspection())
    ids = [item["source_content_id"] for item in inventory["content_items"]]
    first = _annotation(ids[0], "thesis.title.en")
    first["value"] = "invented title"
    payload = {
        "schema_version": 3,
        "annotations": [
            first,
            _annotation(ids[1], "body.figure"),
            _annotation(ids[2], "body.heading.outline1"),
            _annotation(ids[3], "body.paragraph"),
            _annotation(ids[4], "references.entries"),
        ],
        "relations": [],
        "summary": "Synthetic.",
        "uncertainties": [],
    }

    model = validate_extraction(payload, inventory=inventory, registry=_registry(tmp_path))

    assert model["items"][0]["value"] == "A verified title"


def _annotation(
    source_content_id: str,
    field_id: str,
) -> dict[str, object]:
    return {
        "source_content_id": source_content_id,
        "classification_status": "classified",
        "field_id": field_id,
        "confidence": 1.0,
        "note": "Synthetic.",
    }


def test_placement_copies_body_transport_once_in_student_source_order(
    tmp_path: Path,
) -> None:
    student_content, registry = _student_content(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"hash-bound synthetic template")
    styles = [
        _style("style.cover.title"),
        _style("style.body.chapter_title"),
        _style("style.body.chapter_body"),
        _style("style.body.figure"),
    ]
    contract = {
        "schema_version": "docfit-template-fill-contract/v2",
        "contract_id": "synthetic",
        "revision": "1",
        "status": "accepted",
        "template_sha256": sha256_file(template),
        "contract_sha256": "c" * 64,
        "field_registry_ref": registry.identity(),
        "styles": styles,
        "style_contract_set_digest": _style_set_digest(template, styles),
        "regions": [],
        "slots": [
            _slot("slot.title", "thesis.title.en", "docfit.title", True, styles[0]),
            _slot(
                "slot.body.h1",
                "body.heading.outline1",
                "docfit.body.h1",
                True,
                styles[1],
            ),
            _slot(
                "slot.body.text",
                "body.paragraph",
                "docfit.body.text",
                True,
                styles[2],
            ),
            _slot(
                "slot.body.figure",
                "body.figure",
                "docfit.body.figure",
                True,
                styles[3],
            ),
        ],
    }

    placement = build_placement(
        student_content=student_content,
        contract=contract,
        registry=registry,
        template_docx=template,
    )

    body = next(
        operation
        for operation in placement["operations"]
        if operation["field_id"] == "body.ordered_items"
    )
    assert body["ordering_policy"] == "student_source_order_only"
    assert body["source_object_ids"] == ["obj-body-1", "obj-body-2"]
    assert [item["field_id"] for item in body["source_content_items"]] == [
        "body.figure",
        "body.heading.outline1",
        "body.paragraph",
    ]
    assert placement["status"] == "COMPLETE"


def test_placement_refuses_unresolved_student_content(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")

    with pytest.raises(ToolFailure) as failure:
        build_placement(
            student_content={
                "schema_version": "docfit-student-content-model/v2",
                "status": "NEEDS_REVIEW",
                "registry": registry.identity(),
                "items": [],
            },
            contract={
                "template_sha256": sha256_file(template),
                "field_registry_ref": registry.identity(),
            },
            registry=registry,
            template_docx=template,
        )

    assert failure.value.code == "placement_student_content_not_ready"


def test_visible_text_audit_includes_omml_formula_text(tmp_path: Path) -> None:
    document = tmp_path / "formula.docx"
    math_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    document_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:m="{math_namespace}">
 <w:body><w:p><w:r><w:t>Before</w:t></w:r><m:oMath><m:r><m:t>x=1</m:t></m:r></m:oMath></w:p></w:body>
</w:document>""".encode()
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    assert _document_visible_text(document) == "Before\nx=1"


def test_fill_contract_v2_rejects_inline_slot_style_even_with_valid_ref(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")
    style = _style("style.title")
    contract = {
        "schema_version": "docfit-template-fill-contract/v2",
        "template_sha256": sha256_file(template),
        "styles": [style],
        "style_contract_set_digest": _style_set_digest(template, [style]),
        "slots": [
            {
                **_slot(
                    "slot.title",
                    "thesis.title.en",
                    "docfit.cover.title_en",
                    True,
                    style,
                ),
                "expected_value_style": {"font": {"size_pt": 12}},
            }
        ],
    }
    path = tmp_path / "fill-contract.yaml"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")

    with pytest.raises(ToolFailure) as failure:
        load_fill_contract(path)

    assert failure.value.code == "fill_contract_inline_style_forbidden"


def _slot(
    slot_id: str,
    field_id: str,
    tag: str,
    required: bool,
    style: dict[str, object],
) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "field_id": field_id,
        "required": required,
        "locator": {"type": "content_control_tag", "value": tag},
        "style_contract_ref": {
            "style_contract_id": style["style_contract_id"],
            "contract_digest": style["contract_digest"],
        },
    }


def _style(style_contract_id: str) -> dict[str, object]:
    value: dict[str, object] = {
        "style_contract_id": style_contract_id,
        "application_scope": "paragraph",
        "owned_properties": ["paragraph.alignment"],
        "effective_properties": {"paragraph.alignment": "left"},
        "override_policy": {
            "managed_direct_formatting": "clear_conflicts",
            "unmanaged_properties": "preserve",
        },
        "dependencies": [],
    }
    value["contract_digest"] = style_contract_digest(value)
    return value


def _style_set_digest(template: Path, styles: list[dict[str, object]]) -> str:
    return sha256_json(
        {
            "schema_version": "docfit-template-fill-contract/v2",
            "template_sha256": sha256_file(template),
            "styles": sorted(
                (
                    {
                        "style_contract_id": style["style_contract_id"],
                        "contract_digest": style["contract_digest"],
                    }
                    for style in styles
                ),
                key=lambda item: str(item["style_contract_id"]),
            ),
        }
    )
