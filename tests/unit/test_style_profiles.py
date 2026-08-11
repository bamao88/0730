from __future__ import annotations

import pytest

from docfit.styles.profiles import (
    DEFAULT_STYLE_PROPERTY_PROFILES,
    DOCUMENT_ROLE_PROPERTY_PATHS,
    STYLE_ROLE_PROPERTY_PATHS,
    PropertyDefinition,
    StylePropertyProfile,
    StylePropertyProfileRegistry,
)
from docfit.tools.runtime import ToolFailure


def test_default_registry_matches_the_accepted_fixed_style_lists() -> None:
    expected_counts = {
        "paragraph": 26,
        "heading": 27,
        "toc_entry": 27,
        "character": 14,
        "table_cell": 28,
        "caption": 30,
        "equation": 29,
        "header_footer": 26,
        "footnote": 32,
    }

    assert set(STYLE_ROLE_PROPERTY_PATHS) == set(expected_counts)
    assert {
        role_type: len(paths) for role_type, paths in STYLE_ROLE_PROPERTY_PATHS.items()
    } == expected_counts
    for role_type, paths in STYLE_ROLE_PROPERTY_PATHS.items():
        assert (
            DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type(role_type).property_paths
            == paths
        )
    assert DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type("caption").property_paths == (
        "run.cjk_font",
        "run.latin_font",
        "run.size_pt",
        "run.bold",
        "run.italic",
        "run.color",
        "run.underline",
        "run.strikethrough",
        "run.vertical_position",
        "run.character_spacing_pt",
        "paragraph.alignment",
        "paragraph.first_line_indent_chars",
        "paragraph.left_indent_chars",
        "paragraph.right_indent_chars",
        "paragraph.hanging_indent_chars",
        "paragraph.line_spacing.mode",
        "paragraph.line_spacing.value",
        "paragraph.space_before_pt",
        "paragraph.space_after_pt",
        "paragraph.page_break_before",
        "paragraph.keep_with_next",
        "paragraph.keep_together",
        "paragraph.widow_control",
        "paragraph.outline_level",
        "numbering",
        "tab_stops",
        "caption.object_type",
        "caption.placement",
        "caption.numbering_scope",
        "caption.numbering_format",
    )


def test_registry_covers_accepted_style_and_document_role_types_without_values() -> None:
    expected_role_types = set(STYLE_ROLE_PROPERTY_PATHS) | set(
        DOCUMENT_ROLE_PROPERTY_PATHS
    )

    assert {item.role_type for item in DEFAULT_STYLE_PROPERTY_PROFILES.profiles} == (
        expected_role_types
    )
    serialized = DEFAULT_STYLE_PROPERTY_PROFILES.as_dict()
    assert "school" not in serialized
    assert "preset_value" not in serialized
    assert len(DEFAULT_STYLE_PROPERTY_PROFILES.registry_digest) == 64


def test_profile_ref_is_digest_bound() -> None:
    profile = DEFAULT_STYLE_PROPERTY_PROFILES.for_role_type("paragraph")
    stale = profile.ref().as_dict()
    stale["profile_digest"] = "0" * 64

    with pytest.raises(ToolFailure, match="stale"):
        DEFAULT_STYLE_PROPERTY_PROFILES.resolve(stale)


def test_profile_requires_non_applicable_properties_to_be_explicit_n_a() -> None:
    definition = PropertyDefinition.build(
        property_path="paragraph.alignment",
        applicable_role_types={"paragraph"},
        allows_n_a=True,
    )

    with pytest.raises(ToolFailure, match="must be N/A"):
        StylePropertyProfile.build(role_type="character", properties=[definition])

    profile = StylePropertyProfile.build(
        role_type="character",
        properties=[definition],
        n_a_properties={"paragraph.alignment"},
    )
    registry = StylePropertyProfileRegistry.build([profile])
    assert registry.for_role_type("character").n_a_properties == frozenset(
        {"paragraph.alignment"}
    )
