from __future__ import annotations

from typing import Any

from docfit.content.presentation_roles import (
    classify_body_text,
    compile_actual_roles_from_student,
    compile_presentation_role_inventory,
)
from docfit.styles.presets import GeneralStylePreset


def _student_content() -> dict[str, Any]:
    return {
        "fields": [
            {"field_id": "thesis.title.zh", "status": "extracted", "value": "题目"}
        ],
        "segments": [
            {
                "field_id": "body.chapters",
                "status": "extracted",
                "source_object_ids": ["p1", "p2", "p3", "t1"],
            }
        ],
    }


def _student_inventory() -> dict[str, Any]:
    return {
        "source_sha256": "a" * 64,
        "objects": [
            {
                "kind": "paragraph",
                "content_type": "rich_text",
                "text": "第一章 绪论",
                "style": "",
                "body_sequence": 1,
                "source_object_ref": {"object_id": "p1"},
            },
            {
                "kind": "paragraph",
                "content_type": "rich_text",
                "text": "表 1-1 样本分布",
                "style": "",
                "body_sequence": 2,
                "source_object_ref": {"object_id": "p2"},
            },
            {
                "kind": "paragraph",
                "content_type": "equation",
                "text": "E=mc2",
                "style": "",
                "body_sequence": 3,
                "source_object_ref": {"object_id": "p3"},
            },
            {
                "kind": "table",
                "content_type": "table",
                "text": "A B",
                "style": "",
                "body_sequence": 4,
                "source_object_ref": {"object_id": "t1"},
            },
        ],
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
            "body.heading.level1": {
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


def test_classifier_is_shared_product_vocabulary() -> None:
    assert classify_body_text("第一章 绪论") == "body.heading.level1"
    assert classify_body_text("1.1 研究方法") == "body.heading.level3"
    assert classify_body_text("Table 2 Results") == "body.table.caption"
    assert classify_body_text("任意正文", word_style_id="Heading 4") == (
        "body.heading.level4"
    )


def test_prewrite_inventory_and_actual_roles_include_table_caption_before_fill() -> None:
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
        "body.heading.level1",
        "body.table",
        "body.table.caption",
    )
    assert {item.style_role_id for item in actual.roles} == {
        "style.body.heading.1",
        "style.caption.table",
        "style.equation.block",
        "style.front.title.zh",
        "style.table.body",
        "style.table.header",
    }
