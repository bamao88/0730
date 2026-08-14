from __future__ import annotations

from typing import Any

import pytest

from docfit.styles.actual_roles import ActualStyleRoleSet
from docfit.styles.presets import GeneralStylePreset
from docfit.tools.runtime import ToolFailure


def _preset() -> GeneralStylePreset:
    value: dict[str, Any] = {
        "schema_version": "docfit-general-style-preset/v1.0",
        "preset_id": "docfit.actual-role-test",
        "preset_version": "1.0.0",
        "status": "product_definition_accepted",
        "parameters": {},
        "complete_style_type_profiles": {
            "paragraph": {"run": {"bold": False}},
            "caption": {"run": {"bold": False}},
            "table_cell": {"run": {"bold": False}},
        },
        "required_effective_properties": {
            "paragraph": ["run.bold"],
            "caption": ["run.bold"],
            "table_cell": ["run.bold"],
        },
        "style_roles": {
            "style.body.paragraph": {
                "role_type": "paragraph",
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            },
            "style.caption.table": {
                "role_type": "caption",
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            },
            "style.table.header": {
                "role_type": "table_cell",
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            },
            "style.table.body": {
                "role_type": "table_cell",
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            },
        },
        "field_handling": {
            "body.paragraph": {
                "handling": "styled_content",
                "components": {"content": "style.body.paragraph"},
            },
            "body.table.caption": {
                "handling": "styled_content",
                "components": {"content": "style.caption.table"},
            },
            "body.table": {
                "handling": "preserved_object_with_layout",
                "components": {
                    "header_cell": "style.table.header",
                    "body_cell": "style.table.body",
                    "layout": "layout.table",
                },
            },
            "review.mode": {
                "handling": "task_configuration_only",
                "components": {},
            },
        },
    }
    return GeneralStylePreset.from_mapping(value)


def test_actual_role_set_unions_student_retained_and_global_sources() -> None:
    actual = ActualStyleRoleSet.compile(
        preset=_preset(),
        student_field_ids=["body.table.caption", "body.paragraph"],
        retained_field_ids=["body.table"],
        global_field_ids=["review.mode"],
    )

    assert [item.style_role_id for item in actual.roles] == [
        "style.body.paragraph",
        "style.caption.table",
        "style.table.body",
        "style.table.header",
    ]
    caption = next(
        item for item in actual.roles if item.style_role_id == "style.caption.table"
    )
    assert caption.sources[0].field_id == "body.table.caption"
    assert caption.sources[0].source_kind == "student_content"
    assert actual.non_style_fields == ("review.mode",)


def test_actual_role_set_digest_is_input_order_independent() -> None:
    preset = _preset()
    first = ActualStyleRoleSet.compile(
        preset=preset,
        student_field_ids=["body.table.caption", "body.paragraph"],
    )
    second = ActualStyleRoleSet.compile(
        preset=preset,
        student_field_ids=["body.paragraph", "body.table.caption", "body.paragraph"],
    )

    assert first.actual_role_set_digest == second.actual_role_set_digest


def test_actual_role_set_rejects_unmapped_field() -> None:
    with pytest.raises(ToolFailure, match="no field handling"):
        ActualStyleRoleSet.compile(
            preset=_preset(),
            student_field_ids=["body.unknown"],
        )
