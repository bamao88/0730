from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.runtime import ToolFailure, sha256_file, sha256_json

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_V2 = (
    REPOSITORY_ROOT
    / "docs"
    / "plans"
    / "docfit-content-field-registry"
    / "content-fields-v0.2.yaml"
)
REGISTRY_V3 = REGISTRY_V2.with_name("content-fields-v0.3.yaml")
REGISTRY_V5 = REGISTRY_V2.with_name("content-fields-v0.5.yaml")


def test_student_002_registry_policy_is_available_to_consumers() -> None:
    registry = FieldRegistrySnapshot.load(REGISTRY_V2)

    assert registry.registry_version == "0.2.0"
    assert registry.sha256 == sha256_file(REGISTRY_V2)
    assert len(registry.fields) == 54
    assert len({field["field_id"] for field in registry.fields}) == 54

    title = registry.lookup("thesis.title.zh")
    assert title["value_sources"] == ["student_source"]
    assert title["student_extraction_policy"] == "required"

    keywords = registry.lookup("keywords.zh")
    assert keywords["normalization"]["normalized_value_excludes_labels"] == [
        "关键词：",
        "关键词:",
    ]


def test_student_002_registry_v3_assigns_caption_numbering_to_target() -> None:
    registry = FieldRegistrySnapshot.load(REGISTRY_V3)

    assert registry.registry_version == "0.3.0"
    assert registry.sha256 == sha256_file(REGISTRY_V3)
    assert len(registry.fields) == 54

    figure_caption = registry.lookup("body.figure.caption")
    assert figure_caption["normalization"] == {
        "preserve_observed_value": True,
        "normalized_value_excludes_generated_prefixes": [
            "图 <chapter>-<sequence>",
            "Fig. <chapter>-<sequence>",
            "Figure <chapter>-<sequence>",
        ],
        "trim_outer_whitespace": True,
        "generation_owner": "target_template_caption_numbering",
    }

    table_caption = registry.lookup("body.table.caption")
    assert table_caption["normalization"]["apply_per_language_line"] is True
    assert table_caption["normalization"]["generation_owner"] == (
        "target_template_caption_numbering"
    )


def test_registry_keeps_materialization_metadata_internal_to_snapshot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.4.0",
                "fields": [
                    {
                        "field_id": "thesis.title.zh",
                        "label": "中文题目",
                        "content_type": "text",
                        "materialization": {"slot_layout": "centered_title"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    registry = FieldRegistrySnapshot.load(path)

    assert registry.lookup("thesis.title.zh")["materialization"] == {
        "slot_layout": "centered_title"
    }
    vocabulary = registry.pre_input_vocabulary()
    assert "materialization" not in vocabulary["fields"][0]


@pytest.mark.parametrize(
    ("field_patch", "expected_code"),
    [
        ({"value_sources": []}, "field_registry_invalid"),
        ({"student_extraction_policy": "guess"}, "field_registry_invalid"),
        ({"parent_field_id": "body.not_registered"}, "field_registry_invalid"),
    ],
)
def test_registry_rejects_invalid_extraction_policy_metadata(
    tmp_path: Path,
    field_patch: dict[str, object],
    expected_code: str,
) -> None:
    path = tmp_path / "registry.yaml"
    field = {
        "field_id": "body.paragraph",
        "content_type": "rich_text",
        **field_patch,
    }
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.2.0",
                "fields": [field],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolFailure) as error:
        FieldRegistrySnapshot.load(path)

    assert error.value.code == expected_code


@pytest.mark.parametrize(
    "materialization",
    [
        "centered_title",
        {"slot_layout": "title"},
        {"slot_layout": ""},
        {"slot_layout": 7},
    ],
)
def test_registry_rejects_invalid_materialization_metadata(
    tmp_path: Path,
    materialization: object,
) -> None:
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.4.0",
                "fields": [
                    {
                        "field_id": "thesis.title.zh",
                        "content_type": "text",
                        "materialization": materialization,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolFailure) as error:
        FieldRegistrySnapshot.load(path)

    assert error.value.code == "field_registry_invalid"


def test_declared_extraction_policy_contract_requires_metadata(tmp_path: Path) -> None:
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "registry_id": "docfit.thesis.content_fields",
                "registry_version": "0.2.0",
                "policy_schema": {"student_extraction_policy_values": ["required"]},
                "fields": [
                    {
                        "field_id": "body.paragraph",
                        "content_type": "rich_text",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolFailure) as error:
        FieldRegistrySnapshot.load(path)

    assert error.value.code == "field_registry_invalid"


def test_pre_input_field_vocabulary_is_derived_from_bound_registry_snapshot() -> None:
    registry = FieldRegistrySnapshot.load(REGISTRY_V3)

    vocabulary = registry.pre_input_vocabulary()
    expected_digest_payload = dict(vocabulary)
    digest = expected_digest_payload.pop("digest")

    assert vocabulary["schema_version"] == "docfit_pre_input_field_vocabulary_v1"
    assert vocabulary["registry"] == registry.identity()
    assert vocabulary["allowed_field_ids"] == [
        field["field_id"] for field in registry.fields
    ]
    assert vocabulary["field_count"] == len(registry.fields)
    assert digest == sha256_json(expected_digest_payload)
    assert vocabulary["fields"][0]["usage_affordance"] == {
        "selectable_by_agent": True,
        "source": "pre_input_field_vocabulary",
        "requires_agent_semantic_part": True,
        "has_parent_field": False,
        "allowed_part_roles": ["fill_slot"],
    }
    body_member = next(
        field
        for field in vocabulary["fields"]
        if field["field_id"] == "body.heading.level1"
    )
    assert body_member["parent_field_id"] == "body.chapters"
    assert body_member["usage_affordance"]["has_parent_field"] is True
    assert body_member["usage_affordance"]["allowed_part_roles"] == ["body_structure"]
    generated = next(
        field
        for field in vocabulary["fields"]
        if field["field_id"] == "generated.toc"
    )
    assert generated["usage_affordance"]["allowed_part_roles"] == ["generated_content"]


def test_pre_input_vocabulary_distinguishes_leaf_sections_from_section_containers() -> None:
    registry = FieldRegistrySnapshot.load(REGISTRY_V5)

    vocabulary = registry.pre_input_vocabulary()
    by_id = {field["field_id"]: field for field in vocabulary["fields"]}

    assert by_id["appendix.body"]["usage_affordance"]["allowed_part_roles"] == [
        "fill_slot"
    ]
    assert by_id["body.chapters"]["usage_affordance"]["allowed_part_roles"] == []


def test_pre_input_field_vocabulary_rejects_ids_outside_bound_registry() -> None:
    registry = FieldRegistrySnapshot.load(REGISTRY_V3)

    with pytest.raises(ToolFailure) as error:
        registry.pre_input_vocabulary(allowed_field_ids=("school.generated.late",))

    assert error.value.code == "field_vocabulary_unknown_field_id"
