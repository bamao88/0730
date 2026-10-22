from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from docfit.content.partition import compile_final_content_partition
from docfit.content.placement import build_placement
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.styles import style_contract_digest
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json


@pytest.fixture(autouse=True)
def _published_package_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "docfit.template.artifact.validate_published_template_artifact",
        lambda *, template_docx, **_kwargs: {"template_sha256": sha256_file(template_docx)},
    )


def _registry(tmp_path: Path) -> FieldRegistrySnapshot:
    path = tmp_path / "content-fields.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.5.0",
                "fields": [
                    _field("thesis.title.en", "text"),
                    _field("abstract.zh", "rich_text"),
                    _field("body.chapters", "section"),
                    _field("body.figure.caption", "text"),
                    _field("body.heading.outline4", "text"),
                    _field("body.paragraph", "rich_text"),
                    _field("references.entries", "rich_text"),
                    _field("generated.toc", "section"),
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
        "meaning": f"Meaning for {field_id}.",
        "content_type": content_type,
    }


def _student_content(registry: FieldRegistrySnapshot) -> dict[str, Any]:
    return {
        "schema_version": "docfit-student-content-model/v2",
        "status": "READY",
        "source_sha256": "a" * 64,
        "registry": registry.identity(),
        "items": [
            _item("c-title", "s-title", "o-title", "thesis.title.en", "text", 1),
            _structure_item("c-chapters", "body.chapters", 2),
            _item("c-h4", "s-h4", "o-h4", "body.heading.outline4", "text", 3),
            _item("c-body", "s-body", "o-body", "body.paragraph", "text", 4),
            _item("c-ref", "s-ref", "o-ref", "references.entries", "text", 5),
        ],
        "relations": [],
        "source_coverage": {"all_source_objects_accounted_for": True},
    }


def _item(
    content_id: str,
    source_content_id: str,
    object_id: str,
    field_id: str,
    physical_type: str,
    block: int,
) -> dict[str, Any]:
    return {
        "content_id": content_id,
        "source_content_id": source_content_id,
        "field_id": field_id,
        "classification_status": "classified",
        "content_type": "rich_text" if field_id.endswith(("paragraph", "entries")) else "text",
        "physical_type": physical_type,
        "value": f"value:{content_id}" if physical_type == "text" else None,
        "source_order": {"block": block, "inline": 0},
        "source_object_ids": [object_id],
        "source_locators": [f"/body/p[@paraId={block:08X}]"],
        "transport_source_object_id": object_id,
        "transport_source_locator": f"/body/p[@paraId={block:08X}]",
        "content_ref": {
            "student_document_sha256": "a" * 64,
            "source_object_ids": [object_id],
            "source_locators": [f"/body/p[@paraId={block:08X}]"],
        },
    }


def _structure_item(content_id: str, field_id: str, block: int) -> dict[str, Any]:
    return {
        "content_id": content_id,
        "source_content_id": f"s-{content_id}",
        "field_id": field_id,
        "classification_status": "classified",
        "content_type": "section",
        "physical_type": "section",
        "value": None,
        "source_order": {"block": block, "inline": 0},
        "source_object_ids": [],
        "source_locators": [],
        "content_ref": {
            "student_document_sha256": "a" * 64,
            "start_body_sequence": block,
            "end_body_sequence": block + 10,
        },
    }


def _style(style_contract_id: str) -> dict[str, Any]:
    value: dict[str, Any] = {
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


def _slot(
    slot_ref: str,
    field_id: str,
    tag: str,
    required: bool,
    style: dict[str, Any],
) -> dict[str, Any]:
    return {
        "slot_ref": slot_ref,
        "field_id": field_id,
        "content_type": "rich_text" if field_id.endswith(("paragraph", "entries")) else "text",
        "required": required,
        "cardinality": "many" if field_id.startswith("body.") else "one",
        "locator": {"type": "content_control_tag", "value": tag},
        "style_contract_ref": {
            "style_contract_id": style["style_contract_id"],
            "contract_digest": style["contract_digest"],
        },
    }


def _contract(
    template: Path,
    registry: FieldRegistrySnapshot,
    styles: list[dict[str, Any]],
    *,
    duplicate_body_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body_paragraph_style = duplicate_body_style or styles[2]
    all_styles = list(styles)
    if duplicate_body_style is not None:
        all_styles.append(duplicate_body_style)
    return {
        "schema_version": "docfit-template-fill-contract/v2",
        "contract_id": "synthetic.final.partition",
        "revision": "1",
        "status": "accepted",
        "template_sha256": sha256_file(template),
        "contract_sha256": "c" * 64,
        "field_registry_ref": registry.identity(),
        "styles": all_styles,
        "style_contract_set_digest": _style_set_digest(template, all_styles),
        "regions": [
            {
                "region_id": "region.generated.toc",
                "owner": "slot",
                "required": True,
                "field_ids": ["generated.toc"],
            },
            {
                "region_id": "region.school.form",
                "owner": "protected",
                "required": True,
                "field_ids": ["abstract.zh"],
            },
        ],
        "slots": [
            _slot("slot.title", "thesis.title.en", "docfit.title", True, styles[0]),
            _slot("slot.body.h4", "body.heading.outline4", "docfit.body.h4", True, styles[1]),
            _slot(
                "slot.body.paragraph",
                "body.paragraph",
                "docfit.body.paragraph",
                True,
                styles[2],
            ),
            _slot(
                "slot.body.paragraph.alt",
                "body.paragraph",
                "docfit.body.paragraph.alt",
                True,
                body_paragraph_style,
            ),
            _slot(
                "slot.references",
                "references.entries",
                "docfit.references",
                True,
                styles[3],
            ),
        ],
    }


def _style_set_digest(template: Path, styles: list[dict[str, Any]]) -> str:
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


def test_partition_splits_body_flow_named_fields_generated_and_retained_regions(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")
    styles = [
        _style("style.title"),
        _style("style.body.heading.4"),
        _style("style.body.paragraph"),
        _style("style.references"),
    ]
    partition = compile_final_content_partition(
        student_content=_student_content(registry),
        contract=_contract(template, registry, styles),
        registry=registry,
    )

    assert partition["schema_version"] == "docfit-final-content-partition/v1"
    assert [item["content_id"] for item in partition["body_flow"]["items"]] == [
        "c-h4",
        "c-body",
    ]
    assert [item["content_id"] for item in partition["body_flow"]["structure_items"]] == [
        "c-chapters"
    ]
    assert partition["body_flow"]["field_ids"] == [
        "body.heading.outline4",
        "body.paragraph",
    ]
    assert partition["body_flow"]["structure_field_ids"] == ["body.chapters"]
    assert sorted(partition["named_fields"]) == [
        "references.entries",
        "thesis.title.en",
    ]
    assert [slot["slot_ref"] for slot in partition["template"]["body_flow_roles"]] == [
        "slot.body.h4",
        "slot.body.paragraph",
        "slot.body.paragraph.alt",
    ]
    assert [region["region_id"] for region in partition["template"]["generated_regions"]] == [
        "region.generated.toc"
    ]
    assert [region["region_id"] for region in partition["template"]["retained_regions"]] == [
        "region.school.form"
    ]


def test_placement_consumes_partition_body_flow_without_static_body_whitelist(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")
    styles = [
        _style("style.title"),
        _style("style.body.heading.4"),
        _style("style.body.paragraph"),
        _style("style.references"),
    ]

    placement = build_placement(
        student_content=_student_content(registry),
        contract=_contract(template, registry, styles),
        registry=registry,
        template_docx=template,
    )

    body = next(
        operation
        for operation in placement["operations"]
        if operation["field_id"] == "body.ordered_items"
    )
    assert [item["field_id"] for item in body["source_content_items"]] == [
        "body.heading.outline4",
        "body.paragraph",
    ]
    assert body["style_role_refs"]["body.heading.outline4"]["style_contract_id"] == (
        "style.body.heading.4"
    )
    assert placement["content_partition"]["body_flow_field_ids"] == [
        "body.heading.outline4",
        "body.paragraph",
    ]
    assert placement["content_partition"]["body_structure_field_ids"] == ["body.chapters"]


def test_placement_ignores_debug_body_role_bindings_in_final_style_refs(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")
    styles = [
        _style("style.title"),
        _style("style.body.heading.4"),
        _style("style.body.paragraph"),
        _style("style.references"),
    ]
    contract = _contract(template, registry, styles)
    debug_caption_slot = _slot(
        "slot.debug.figure.caption",
        "body.figure.caption",
        "docfit.body.paragraph",
        False,
        styles[3],
    )
    debug_caption_slot["mapping_status"] = "debug_e2e_role_binding"
    debug_caption_slot["value_contract"] = {"debug_role_binding": "reuses body aggregate anchor"}
    contract["slots"].append(debug_caption_slot)
    student_content = _student_content(registry)
    student_content["items"].append(
        _item(
            "c-figure-caption",
            "s-figure-caption",
            "o-figure-caption",
            "body.figure.caption",
            "text",
            6,
        )
    )

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
    assert placement["ignored_debug_body_style_roles"] == ["body.figure.caption"]
    assert placement["body_style_fallbacks"] == ["body.figure.caption"]
    assert "body_style_roles_missing" not in placement["partial_reasons"]
    assert body["style_role_refs"]["body.figure.caption"]["style_contract_id"] == (
        "style.body.paragraph"
    )


def test_placement_expands_multiblock_named_rich_text_source_refs(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")
    styles = [
        _style("style.title"),
        _style("style.body.heading.4"),
        _style("style.body.paragraph"),
        _style("style.references"),
    ]
    contract = _contract(template, registry, styles)
    abstract_slot = _slot(
        "slot.abstract.zh",
        "abstract.zh",
        "docfit.abstract.zh",
        True,
        styles[2],
    )
    abstract_slot["content_type"] = "rich_text"
    contract["slots"].append(abstract_slot)
    student_content = _student_content(registry)
    abstract_item = _item(
        "c-abstract",
        "s-abstract",
        "obj-abstract-1",
        "abstract.zh",
        "text",
        6,
    )
    abstract_item["content_type"] = "rich_text"
    abstract_item["source_object_ids"] = ["obj-abstract-1", "obj-abstract-2"]
    abstract_item["source_locators"] = [
        "/body/p[@paraId=00000006]",
        "/body/p[@paraId=00000007]",
    ]
    abstract_item["content_ref"] = {
        "student_document_sha256": "a" * 64,
        "source_object_ids": abstract_item["source_object_ids"],
        "source_locators": abstract_item["source_locators"],
    }
    student_content["items"].append(abstract_item)

    placement = build_placement(
        student_content=student_content,
        contract=contract,
        registry=registry,
        template_docx=template,
    )

    abstract = next(
        operation for operation in placement["operations"] if operation["field_id"] == "abstract.zh"
    )
    assert abstract["source_object_ids"] == ["obj-abstract-1", "obj-abstract-2"]
    assert abstract["source_locators"] == [
        "/body/p[@paraId=00000006]",
        "/body/p[@paraId=00000007]",
    ]


def test_placement_rejects_conflicting_body_role_style_refs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    template = tmp_path / "template.docx"
    template.write_bytes(b"template")
    styles = [
        _style("style.title"),
        _style("style.body.heading.4"),
        _style("style.body.paragraph"),
        _style("style.references"),
    ]

    with pytest.raises(ToolFailure) as failure:
        build_placement(
            student_content=_student_content(registry),
            contract=_contract(
                template,
                registry,
                styles,
                duplicate_body_style=_style("style.body.paragraph.alt"),
            ),
            registry=registry,
            template_docx=template,
        )

    assert failure.value.code == "placement_body_role_style_conflict"
