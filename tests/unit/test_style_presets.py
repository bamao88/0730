from __future__ import annotations

from typing import Any

import pytest

from docfit.styles.presets import GeneralStylePreset
from docfit.tools.runtime import ToolFailure


def _preset() -> dict[str, Any]:
    return {
        "schema_version": "docfit-general-style-preset/v1.0",
        "preset_id": "docfit.test",
        "preset_version": "1.0.0",
        "status": "product_definition_accepted",
        "parameters": {
            "body_font": {"type": "string", "default": "宋体", "enabled": True}
        },
        "complete_style_type_profiles": {
            "caption": {
                "run": {"color": "#000000", "underline": "none"},
                "paragraph": {"space_before_pt": 0, "keep_with_next": False},
                "numbering": "none",
            }
        },
        "required_effective_properties": {
            "caption": [
                "run.cjk_font",
                "run.color",
                "run.underline",
                "paragraph.space_before_pt",
                "paragraph.keep_with_next",
                "numbering",
                "caption.object_type",
            ]
        },
        "style_roles": {
            "style.caption.figure": {
                "role_type": "caption",
                "kind": "paragraph",
                "complete": True,
                "evidence_profile": "accepted_evidence",
                "value_authority": "accepted_product_value",
                "run": {"cjk_font": "${body_font}"},
                "caption": {"object_type": "figure"},
            },
            "style.caption.table": {
                "role_type": "caption",
                "kind": "paragraph",
                "complete": True,
                "based_on": "style.caption.figure",
                "evidence_profile": "accepted_evidence",
                "value_authority": "accepted_product_value",
                "overrides": {
                    "paragraph": {"space_before_pt": 12, "keep_with_next": True},
                    "numbering": {"scope": "chapter"},
                    "caption": {"object_type": "table"},
                },
            },
        },
        "field_handling": {
            "body.table.caption": {
                "handling": "styled_content",
                "components": {
                    "content": "style.caption.table",
                    "layout": "layout.table",
                },
            }
        },
    }


def test_resolves_complete_role_inheritance_and_typed_none() -> None:
    preset = GeneralStylePreset.from_mapping(_preset())

    role = preset.resolve_role("style.caption.table")
    properties = role.property_map()

    assert properties["run.cjk_font"].value == "宋体"
    assert properties["run.underline"].state == "NONE"
    assert properties["paragraph.space_before_pt"].value == 12
    assert properties["paragraph.keep_with_next"].value is True
    assert properties["numbering"].value == {"scope": "chapter"}
    assert properties["caption.object_type"].value == "table"
    assert preset.field_binding("body.table.caption").primary_style_role_id == (
        "style.caption.table"
    )
    assert len(preset.digest) == 64


def test_rejects_unaccepted_preset() -> None:
    value = _preset()
    value["status"] = "draft"

    with pytest.raises(ToolFailure, match="human-accepted"):
        GeneralStylePreset.from_mapping(value)


def test_rejects_incomplete_role_property_closure() -> None:
    value = _preset()
    del value["style_roles"]["style.caption.figure"]["caption"]

    with pytest.raises(ToolFailure, match="caption.object_type"):
        GeneralStylePreset.from_mapping(value)


def test_rejects_role_inheritance_cycle() -> None:
    value = _preset()
    value["style_roles"]["style.caption.figure"]["based_on"] = "style.caption.table"

    with pytest.raises(ToolFailure, match="cycle"):
        GeneralStylePreset.from_mapping(value)
