from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.runtime import ToolFailure, sha256_file

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_V2 = (
    REPOSITORY_ROOT
    / "docs"
    / "plans"
    / "docfit-content-field-registry"
    / "content-fields-v0.2.yaml"
)
REGISTRY_V3 = REGISTRY_V2.with_name("content-fields-v0.3.yaml")


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
