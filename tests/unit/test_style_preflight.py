from __future__ import annotations

from typing import Any

import pytest

from docfit.styles.preflight import compile_task_local_style_target
from docfit.styles.presets import GeneralStylePreset
from docfit.styles.profiles import (
    PropertyDefinition,
    StylePropertyProfile,
    StylePropertyProfileRegistry,
)
from docfit.tools.runtime import ToolFailure


def _registry() -> StylePropertyProfileRegistry:
    profile = StylePropertyProfile.build(
        role_type="caption",
        properties=(
            PropertyDefinition.build(
                property_path="run.bold",
                applicable_role_types={"caption"},
                value_type="boolean",
                resolver_sources=("run.bold",),
                canonicalization="identity",
                materializer_targets=("run.bold",),
            ),
            PropertyDefinition.build(
                property_path="run.underline",
                applicable_role_types={"caption"},
                allows_none=True,
                resolver_sources=("run.underline",),
                canonicalization="identity",
                materializer_targets=("run.underline",),
            ),
        ),
    )
    return StylePropertyProfileRegistry.build([profile])


def _preset(
    registry: StylePropertyProfileRegistry,
    *,
    include_unsupported_numbering: bool = False,
) -> GeneralStylePreset:
    properties: dict[str, Any] = {
        "run": {"bold": False, "underline": "none"}
    }
    required = ["run.bold", "run.underline"]
    if include_unsupported_numbering:
        properties["numbering"] = {
            "scope": "chapter",
            "sequence": "table",
        }
        required.append("numbering")
    value: dict[str, Any] = {
        "schema_version": "docfit-general-style-preset/v1.0",
        "preset_id": "docfit.preflight-test",
        "preset_version": "1.0.0",
        "status": "product_definition_accepted",
        "parameters": {},
        "complete_style_type_profiles": {"caption": properties},
        "required_effective_properties": {"caption": required},
        "style_roles": {
            "style.caption.table": {
                "role_type": "caption",
                "complete": True,
                "evidence_profile": "accepted",
                "value_authority": "accepted_product_value",
            }
        },
        "field_handling": {
            "body.chapters": {
                "handling": "structured_content_container",
                "components": {},
            },
            "body.table.caption": {
                "handling": "styled_content",
                "components": {"content": "style.caption.table"},
            },
        },
    }
    return GeneralStylePreset.from_mapping(value, registry=registry)


def _student() -> tuple[dict[str, Any], dict[str, Any]]:
    student_content = {
        "fields": [],
        "segments": [
            {
                "field_id": "body.chapters",
                "status": "extracted",
                "source_object_ids": ["p1"],
            }
        ],
    }
    student_inventory = {
        "source_sha256": "a" * 64,
        "objects": [
            {
                "kind": "paragraph",
                "content_type": "rich_text",
                "text": "表 1-1 样本分布",
                "style": "",
                "body_sequence": 1,
                "source_object_ref": {"object_id": "p1"},
            }
        ],
    }
    return student_content, student_inventory


def test_preflight_binds_inventory_selection_and_executable_target_before_fill() -> None:
    registry = _registry()
    student_content, student_inventory = _student()

    target = compile_task_local_style_target(
        preset=_preset(registry),
        student_content=student_content,
        student_inventory=student_inventory,
        school_candidates=[],
        school_observation_set_digest="b" * 64,
        template_sha256="c" * 64,
        registry=registry,
    )

    assert target.presentation_roles.field_ids == ("body.table.caption",)
    assert [item.style_role_id for item in target.actual_roles.roles] == [
        "style.caption.table"
    ]
    assert target.selection.selections[0].source == "preset"
    assert target.executable_contracts.styles[0].effective_properties == {
        "run.bold": False,
        "run.underline": None,
    }
    payload = target.as_dict()
    assert len(payload["task_local_style_target_digest"]) == 64
    assert payload["selection"]["school_observation_set_digest"] == "b" * 64
    assert payload["selection"]["selected_style_contract_set_digest"] != (
        payload["executable_style_contract_set"]["style_contract_set_digest"]
    )


def test_preflight_fails_before_fill_when_semantic_numbering_has_no_word_definition() -> None:
    base_registry = _registry()
    profile = StylePropertyProfile.build(
        role_type="caption",
        properties=(
            *base_registry.for_role_type("caption").properties,
            PropertyDefinition.build(
                property_path="numbering",
                applicable_role_types={"caption"},
                value_type="numbering_definition",
                allows_none=True,
                resolver_sources=("paragraph.numbering",),
                canonicalization="identity",
                materializer_targets=("paragraph.numbering",),
            ),
        ),
    )
    registry = StylePropertyProfileRegistry.build([profile])
    student_content, student_inventory = _student()

    with pytest.raises(ToolFailure) as captured:
        compile_task_local_style_target(
            preset=_preset(registry, include_unsupported_numbering=True),
            student_content=student_content,
            student_inventory=student_inventory,
            school_candidates=[],
            school_observation_set_digest="b" * 64,
            template_sha256="c" * 64,
            registry=registry,
        )

    assert captured.value.code == "style_selection_property_codec_missing"
    assert "compiled Word numbering definition" in captured.value.message
