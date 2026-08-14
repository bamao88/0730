from __future__ import annotations

from typing import Any

from docfit.content.presentation_roles import (
    compile_actual_roles_from_student,
    compile_presentation_role_inventory,
)
from docfit.styles.presets import GeneralStylePreset


def _student_content() -> dict[str, Any]:
    return {
        "schema_version": "docfit-student-content-model/v2",
        "source_sha256": "a" * 64,
        "items": [
            _item("c0", "s0", "p0", "thesis.title.zh", "text", 1),
            _item("c1", "s1", "p1", "body.heading.outline1", "text", 2),
            _item("c2", "s2", "p2", "body.table.caption", "text", 3),
            _item("c3", "s3", "p3", "body.equation", "equation", 4),
            _item("c4", "s4", "t1", "body.table", "table", 5),
        ],
    }


def _item(
    content_id: str,
    source_content_id: str,
    source_object_id: str,
    field_id: str,
    physical_type: str,
    block: int,
) -> dict[str, Any]:
    return {
        "content_id": content_id,
        "source_content_id": source_content_id,
        "transport_source_object_id": source_object_id,
        "field_id": field_id,
        "classification_status": "classified",
        "physical_type": physical_type,
        "source_order": {"block": block, "inline": 0},
    }


def _student_inventory() -> dict[str, Any]:
    return {
        "source_sha256": "a" * 64,
    }


def _preset() -> GeneralStylePreset:
    value: dict[str, Any] = {
        "schema_version": "docfit-general-style-preset/v1.0",
        "preset_id": "docfit.presentation-test",
        "preset_version": "1.0.0",
        "status": "product_definition_accepted",
        "parameters": {},
        "complete_style_type_profiles": {
            "heading": {"run": {"bold": True}},
            "caption": {"run": {"bold": False}},
            "equation": {"run": {"bold": False}},
            "table_cell": {"run": {"bold": False}},
            "paragraph": {"run": {"bold": False}},
        },
        "required_effective_properties": {
            role_type: ["run.bold"]
            for role_type in ("heading", "caption", "equation", "table_cell", "paragraph")
        },
        "style_roles": {
            role_id: {
                "role_type": role_type,
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            }
            for role_id, role_type in {
                "style.body.heading.1": "heading",
                "style.caption.table": "caption",
                "style.equation.block": "equation",
                "style.table.header": "table_cell",
                "style.table.body": "table_cell",
                "style.front.title.zh": "paragraph",
            }.items()
        },
        "field_handling": {
            "thesis.title.zh": {
                "handling": "styled_content",
                "components": {"content": "style.front.title.zh"},
            },
            "body.chapters": {"handling": "structured_content_container", "components": {}},
            "body.heading.outline1": {
                "handling": "styled_content",
                "components": {"content": "style.body.heading.1"},
            },
            "body.table.caption": {
                "handling": "styled_content",
                "components": {"content": "style.caption.table"},
            },
            "body.equation": {
                "handling": "styled_content",
                "components": {"content": "style.equation.block"},
            },
            "body.table": {
                "handling": "preserved_object_with_layout",
                "components": {
                    "header_cell": "style.table.header",
                    "body_cell": "style.table.body",
                },
            },
        },
    }
    return GeneralStylePreset.from_mapping(value)


def test_prewrite_inventory_consumes_model_roles_without_reclassification() -> None:
    inventory = compile_presentation_role_inventory(
        student_content=_student_content(),
        student_inventory=_student_inventory(),
    )
    actual = compile_actual_roles_from_student(
        preset=_preset(),
        student_content=_student_content(),
        presentation_roles=inventory,
    )

    assert inventory.field_ids == (
        "body.equation",
        "body.heading.outline1",
        "body.table",
        "body.table.caption",
    )
    assert [item.content_id for item in inventory.occurrences] == ["c1", "c2", "c3", "c4"]
    assert {item.style_role_id for item in actual.roles} == {
        "style.body.heading.1",
        "style.caption.table",
        "style.equation.block",
        "style.front.title.zh",
        "style.table.body",
        "style.table.header",
    }
