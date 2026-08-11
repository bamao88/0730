"""Versioned product Style Property Profiles without school or preset values."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

PROFILE_SCHEMA_VERSION = "docfit-style-property-profile/v1"
PROFILE_REGISTRY_SCHEMA_VERSION = "docfit-style-property-profile-registry/v1"
PROFILE_VERSION = "1.0.0"

ImplicitWordDefaultPolicy = Literal[
    "ALLOW_IF_PORTABLE_AND_EXPLICITLY_MATERIALIZED",
    "GAP",
]

_PORTABLE_IMPLICIT_DEFAULTS = frozenset(
    {
        "run.bold",
        "run.italic",
        "run.color",
        "paragraph.space_before_pt",
        "paragraph.space_after_pt",
        "paragraph.page_break_before",
    }
)


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("use_current_style_property_profile",),
    )


@dataclass(frozen=True, slots=True)
class PropertyDefinition:
    """Product property syntax plus explicit mappings to internal Word codecs."""

    property_path: str
    value_type: str
    applicable_role_types: frozenset[str]
    allows_none: bool
    allows_n_a: bool
    resolution_strategy: str
    resolver_sources: tuple[str, ...]
    canonicalization: str
    materialization_strategy: str
    materializer_targets: tuple[str, ...]
    validation_strategy: str
    implicit_word_default_policy: ImplicitWordDefaultPolicy
    preset_aliases: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        property_path: str,
        applicable_role_types: Iterable[str],
        value_type: str = "string",
        allows_none: bool = False,
        allows_n_a: bool = False,
        resolver_sources: Sequence[str] = (),
        canonicalization: str = "not_implemented",
        materializer_targets: Sequence[str] = (),
        implicit_word_default_policy: ImplicitWordDefaultPolicy = "GAP",
        preset_aliases: Sequence[str] | None = None,
    ) -> PropertyDefinition:
        sources = tuple(resolver_sources)
        targets = tuple(materializer_targets)
        return cls(
            property_path=property_path,
            value_type=value_type,
            applicable_role_types=frozenset(applicable_role_types),
            allows_none=allows_none,
            allows_n_a=allows_n_a,
            resolution_strategy=(
                "effective_style_resolver_v2" if sources else "resolver_unsupported"
            ),
            resolver_sources=sources,
            canonicalization=canonicalization,
            materialization_strategy=(
                "explicit_ooxml_v2" if targets else "materializer_unsupported"
            ),
            materializer_targets=targets,
            validation_strategy=(
                "reopen_effective_style_v2" if sources else "validator_unsupported"
            ),
            implicit_word_default_policy=implicit_word_default_policy,
            preset_aliases=tuple(preset_aliases or (property_path,)),
        )

    @property
    def resolver_supported(self) -> bool:
        return self.resolution_strategy != "resolver_unsupported"

    @property
    def explicitly_materializable(self) -> bool:
        return self.materialization_strategy != "materializer_unsupported"

    @property
    def reopen_validatable(self) -> bool:
        return self.validation_strategy != "validator_unsupported"

    @property
    def implicit_default_is_candidate_eligible(self) -> bool:
        return (
            self.implicit_word_default_policy
            == "ALLOW_IF_PORTABLE_AND_EXPLICITLY_MATERIALIZED"
            and self.explicitly_materializable
            and self.reopen_validatable
        )

    def as_dict(self) -> JsonObject:
        return {
            "property_path": self.property_path,
            "value_type": self.value_type,
            "applicable_role_types": sorted(self.applicable_role_types),
            "allows_none": self.allows_none,
            "allows_n_a": self.allows_n_a,
            "resolution_strategy": self.resolution_strategy,
            "resolver_sources": list(self.resolver_sources),
            "canonicalization": self.canonicalization,
            "materialization_strategy": self.materialization_strategy,
            "materializer_targets": list(self.materializer_targets),
            "validation_strategy": self.validation_strategy,
            "implicit_word_default_policy": self.implicit_word_default_policy,
            "preset_aliases": list(self.preset_aliases),
        }


@dataclass(frozen=True, slots=True)
class StylePropertyProfileRef:
    profile_id: str
    profile_version: str
    profile_digest: str

    @classmethod
    def from_mapping(cls, value: object) -> StylePropertyProfileRef:
        if not isinstance(value, Mapping) or set(value) != {
            "profile_id",
            "profile_version",
            "profile_digest",
        }:
            raise _failure(
                "style_property_profile_ref_invalid",
                "A profile ref requires exactly profile_id, profile_version, and profile_digest.",
            )
        values = tuple(value.values())
        if not all(isinstance(item, str) and item for item in values):
            raise _failure(
                "style_property_profile_ref_invalid",
                "Style Property Profile ref values must be non-empty strings.",
            )
        return cls(
            str(value["profile_id"]),
            str(value["profile_version"]),
            str(value["profile_digest"]),
        )

    def as_dict(self) -> JsonObject:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_digest": self.profile_digest,
        }


@dataclass(frozen=True, slots=True)
class StylePropertyProfile:
    """Fixed product property closure for one semantic role type."""

    profile_id: str
    profile_version: str
    role_type: str
    properties: tuple[PropertyDefinition, ...]
    n_a_properties: frozenset[str]
    profile_digest: str

    @classmethod
    def build(
        cls,
        *,
        role_type: str,
        properties: Sequence[PropertyDefinition],
        n_a_properties: Iterable[str] = (),
        profile_id: str | None = None,
        profile_version: str = PROFILE_VERSION,
    ) -> StylePropertyProfile:
        if not role_type or not properties:
            raise _failure(
                "style_property_profile_invalid",
                "A profile requires a role_type and at least one property.",
            )
        paths = tuple(item.property_path for item in properties)
        if len(set(paths)) != len(paths):
            raise _failure(
                "style_property_profile_invalid",
                f"Profile {role_type} contains duplicate property paths.",
            )
        n_a = frozenset(n_a_properties)
        if unknown := sorted(n_a - set(paths)):
            raise _failure(
                "style_property_profile_invalid",
                f"Profile {role_type} declares unknown N/A properties: " + ", ".join(unknown),
            )
        for item in properties:
            applicable = role_type in item.applicable_role_types
            if item.property_path in n_a:
                if applicable or not item.allows_n_a:
                    raise _failure(
                        "style_property_profile_invalid",
                        f"{item.property_path} has an invalid N/A declaration for {role_type}.",
                    )
            elif not applicable:
                raise _failure(
                    "style_property_profile_invalid",
                    f"{item.property_path} is not applicable to {role_type} and must be N/A.",
                )
        identity = profile_id or f"docfit.style.{role_type}"
        payload: JsonObject = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "profile_id": identity,
            "profile_version": profile_version,
            "role_type": role_type,
            "properties": [item.as_dict() for item in properties],
            "n_a_properties": sorted(n_a),
        }
        return cls(
            profile_id=identity,
            profile_version=profile_version,
            role_type=role_type,
            properties=tuple(properties),
            n_a_properties=n_a,
            profile_digest=sha256_json(payload),
        )

    @property
    def property_paths(self) -> tuple[str, ...]:
        return tuple(item.property_path for item in self.properties)

    def definition(self, property_path: str) -> PropertyDefinition:
        item = next(
            (value for value in self.properties if value.property_path == property_path), None
        )
        if item is None:
            raise _failure(
                "style_property_not_in_profile", f"{property_path} is not in {self.profile_id}."
            )
        return item

    def ref(self) -> StylePropertyProfileRef:
        return StylePropertyProfileRef(
            self.profile_id, self.profile_version, self.profile_digest
        )

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "role_type": self.role_type,
            "properties": [item.as_dict() for item in self.properties],
            "n_a_properties": sorted(self.n_a_properties),
            "profile_digest": self.profile_digest,
        }


@dataclass(frozen=True, slots=True)
class StylePropertyProfileRegistry:
    schema_version: str
    profiles: tuple[StylePropertyProfile, ...]
    registry_digest: str

    @classmethod
    def build(
        cls, profiles: Sequence[StylePropertyProfile]
    ) -> StylePropertyProfileRegistry:
        if not profiles:
            raise _failure(
                "style_property_profile_registry_invalid",
                "Style Property Profile Registry cannot be empty.",
            )
        if len({item.profile_id for item in profiles}) != len(profiles) or len(
            {item.role_type for item in profiles}
        ) != len(profiles):
            raise _failure(
                "style_property_profile_registry_invalid",
                "Profile IDs and role types must be unique.",
            )
        normalized = tuple(sorted(profiles, key=lambda item: item.profile_id))
        payload: JsonObject = {
            "schema_version": PROFILE_REGISTRY_SCHEMA_VERSION,
            "profiles": [item.ref().as_dict() for item in normalized],
        }
        return cls(
            PROFILE_REGISTRY_SCHEMA_VERSION,
            normalized,
            sha256_json(payload),
        )

    def for_role_type(self, role_type: str) -> StylePropertyProfile:
        item = next((value for value in self.profiles if value.role_type == role_type), None)
        if item is None:
            raise _failure(
                "style_property_role_unsupported",
                f"No accepted Style Property Profile exists for role type {role_type}.",
            )
        return item

    def resolve(self, reference: Mapping[str, Any]) -> StylePropertyProfile:
        ref = StylePropertyProfileRef.from_mapping(reference)
        item = next((value for value in self.profiles if value.profile_id == ref.profile_id), None)
        if item is None:
            raise _failure(
                "style_property_profile_not_found",
                f"The registry does not contain {ref.profile_id}.",
            )
        if item.profile_version != ref.profile_version or item.profile_digest != ref.profile_digest:
            raise _failure(
                "style_property_profile_ref_stale",
                f"The profile ref for {ref.profile_id} is stale.",
            )
        return item

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": self.schema_version,
            "profiles": [item.as_dict() for item in self.profiles],
            "registry_digest": self.registry_digest,
        }


_RUN_PATHS = (
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
)
_PARAGRAPH_PATHS = (
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
)
_CELL_PATHS = (
    "cell.vertical_alignment",
    "cell.padding_mm.top",
    "cell.padding_mm.bottom",
    "cell.padding_mm.left",
    "cell.padding_mm.right",
    "cell.text_wrap",
)
_CAPTION_PATHS = (
    "caption.object_type",
    "caption.placement",
    "caption.numbering_scope",
    "caption.numbering_format",
)
_EQUATION_PATHS = (
    "equation.number_alignment",
    "equation.number_delimiters",
    "equation.leader",
)
_FOOTNOTE_PATHS = (
    "footnote.separator.type",
    "footnote.separator.color",
    "footnote.separator.width_mm",
    "footnote.separator.thickness_pt",
    "footnote.separator.alignment",
    "footnote.separator.space_after_pt",
)

STYLE_ROLE_PROPERTY_PATHS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "paragraph": (*_RUN_PATHS, *_PARAGRAPH_PATHS, "numbering", "tab_stops"),
        "heading": (
            *_RUN_PATHS,
            *_PARAGRAPH_PATHS,
            "numbering",
            "tab_stops",
            "toc_inclusion",
        ),
        "toc_entry": (
            *_RUN_PATHS,
            *_PARAGRAPH_PATHS,
            "numbering",
            "tab_stops",
            "toc_source_level",
        ),
        "character": (
            *_RUN_PATHS,
            "paragraph",
            "pagination_controls",
            "numbering",
            "tab_stops",
        ),
        "table_cell": (
            *_RUN_PATHS,
            "paragraph.alignment",
            "paragraph.first_line_indent_chars",
            "paragraph.left_indent_chars",
            "paragraph.right_indent_chars",
            "paragraph.hanging_indent_chars",
            "paragraph.line_spacing.mode",
            "paragraph.line_spacing.value",
            "paragraph.space_before_pt",
            "paragraph.space_after_pt",
            "pagination_controls",
            "numbering",
            "tab_stops",
            *_CELL_PATHS,
        ),
        "caption": (
            *_RUN_PATHS,
            *_PARAGRAPH_PATHS,
            "numbering",
            "tab_stops",
            *_CAPTION_PATHS,
        ),
        "equation": (
            *_RUN_PATHS,
            *_PARAGRAPH_PATHS,
            "numbering",
            "tab_stops",
            *_EQUATION_PATHS,
        ),
        "header_footer": (*_RUN_PATHS, *_PARAGRAPH_PATHS, "numbering", "tab_stops"),
        "footnote": (*_RUN_PATHS, *_PARAGRAPH_PATHS, "numbering", "tab_stops", *_FOOTNOTE_PATHS),
    }
)

_STYLE_ROLE_N_A: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "character": frozenset(
            {"paragraph", "pagination_controls", "numbering", "tab_stops"}
        ),
        "table_cell": frozenset(
            {"pagination_controls", "numbering", "tab_stops"}
        ),
    }
)

DOCUMENT_ROLE_PROPERTY_PATHS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "page_layout": (
            "page_size", "width_mm", "height_mm", "orientation", "print_sides",
            "mirrored_margins", "binding_edge", "margins_mm.top", "margins_mm.bottom",
            "margins_mm.left", "margins_mm.right", "gutter_mm", "header_distance_mm",
            "footer_distance_mm", "header", "footer", "page_number",
        ),
        "pagination": (
            "front_matter.starts_at", "front_matter.ends_before", "front_matter.format",
            "front_matter.restart_at", "body_and_back_matter.starts_at",
            "body_and_back_matter.ends_at", "body_and_back_matter.format",
            "body_and_back_matter.restart_at", "placement", "show_on_first_page_of_section",
        ),
        "header_layout": (
            "starts_at", "ends_at", "first_page", "odd_page_content",
            "even_page_content", "separator_line", "style_role",
        ),
        "footer_layout": (
            "starts_at", "ends_at", "first_page_content", "odd_page_content",
            "even_page_content", "separator_line", "style_role",
        ),
        "section_start": (
            "break_type", "start_side", "page_number_restart",
            "link_header_footer_to_previous", "applies_to",
        ),
        "figure_layout": (
            "object_alignment", "text_wrapping", "max_width_mm", "max_height_mm",
            "allow_upscale", "oversize_action", "caption_placement",
            "keep_object_and_caption_together", "numbering_scope", "numbering_format",
            "subfigure_format",
        ),
        "table_layout": (
            "object_alignment", "max_width_mm", "width_policy", "caption_placement",
            "repeat_header_row", "allow_row_break_across_pages",
            "continuation_caption_prefix", "border_model", "border_width_pt.top",
            "border_width_pt.header_bottom", "border_width_pt.bottom",
            "border_width_pt.internal_horizontal", "border_width_pt.internal_vertical",
            "default_body_alignment", "numbering_scope", "numbering_format",
        ),
        "equation_layout": (
            "equation_alignment", "max_width_mm", "overflow_action", "number_alignment",
            "number_delimiters", "leader_between_equation_and_number", "numbering_scope",
            "numbering_format",
        ),
        "landscape_layout": (
            "page_size", "width_mm", "height_mm", "orientation", "print_sides",
            "mirrored_margins", "binding_edge", "margins_mm.top", "margins_mm.bottom",
            "margins_mm.left", "margins_mm.right", "gutter_mm", "section_break_before",
            "section_break_after", "header_footer_behavior", "page_number_behavior",
            "restore_previous_section_geometry",
        ),
        "protected_page": (
            "insertion_mode", "page_geometry", "content_reflow", "restyling",
            "image_reconstruction", "header", "footer", "page_number",
        ),
        "reviewer_list_layout": (
            "break_type", "start_side", "page_geometry", "preferred_container",
            "table_borders", "repeat_header_row", "allow_row_break_across_pages",
            "signature_required", "header", "footer", "page_number",
        ),
    }
)

_RESOLVER_MAPPINGS: Mapping[str, tuple[tuple[str, ...], str, tuple[str, ...]]] = (
    MappingProxyType(
        {
            "run.cjk_font": (("run.font_east_asia",), "identity", ("run.font_east_asia",)),
            "run.latin_font": (
                ("run.font_ascii", "run.font_hansi"),
                "equal_word_font_pair",
                ("run.font_ascii", "run.font_hansi"),
            ),
            "run.size_pt": (("run.font_size_pt",), "identity", ("run.font_size_pt",)),
            "run.bold": (("run.bold",), "identity", ("run.bold",)),
            "run.italic": (("run.italic",), "identity", ("run.italic",)),
            "run.color": (("run.color",), "word_hex_color_v1", ("run.color",)),
            "paragraph.alignment": (
                ("paragraph.alignment",), "identity", ("paragraph.alignment",)
            ),
            "paragraph.line_spacing.mode": (
                (
                    "paragraph.line_spacing_rule",
                    "paragraph.line_spacing_pt",
                    "paragraph.line_value",
                ),
                "word_line_spacing_mode_v1",
                ("paragraph.line_spacing_rule",),
            ),
            "paragraph.line_spacing.value": (
                (
                    "paragraph.line_spacing_rule",
                    "paragraph.line_spacing_pt",
                    "paragraph.line_value",
                ),
                "word_line_spacing_value_v1",
                ("paragraph.line_spacing_pt", "paragraph.line_value"),
            ),
            "paragraph.space_before_pt": (
                ("paragraph.space_before_pt",), "identity", ("paragraph.space_before_pt",)
            ),
            "paragraph.space_after_pt": (
                ("paragraph.space_after_pt",), "identity", ("paragraph.space_after_pt",)
            ),
            "paragraph.page_break_before": (
                ("paragraph.page_break_before",),
                "identity",
                ("paragraph.page_break_before",),
            ),
        }
    )
)


def _value_type(path: str) -> str:
    if path.endswith(("_pt", "_mm", ".value")):
        return "number"
    if path in {
        "run.bold", "run.italic", "run.strikethrough",
        "paragraph.page_break_before", "paragraph.keep_with_next",
        "paragraph.keep_together", "paragraph.widow_control", "cell.text_wrap",
    }:
        return "boolean"
    if path in {"numbering", "tab_stops"}:
        return "structured"
    return "string"


def _allows_none(path: str) -> bool:
    return path in {
        "run.underline", "run.strikethrough", "numbering", "tab_stops",
        "toc_inclusion", "toc_source_level",
    }


def _build_default_registry() -> StylePropertyProfileRegistry:
    role_paths = {**STYLE_ROLE_PROPERTY_PATHS, **DOCUMENT_ROLE_PROPERTY_PATHS}
    n_a_by_role = dict(_STYLE_ROLE_N_A)
    roles_by_path: dict[str, set[str]] = {}
    n_a_roles_by_path: dict[str, set[str]] = {}
    for role_type, paths in role_paths.items():
        for path in paths:
            if path in n_a_by_role.get(role_type, frozenset()):
                n_a_roles_by_path.setdefault(path, set()).add(role_type)
            else:
                roles_by_path.setdefault(path, set()).add(role_type)
    definitions: dict[str, PropertyDefinition] = {}
    for path in sorted(set().union(*[set(paths) for paths in role_paths.values()])):
        sources, canonicalization, targets = _RESOLVER_MAPPINGS.get(
            path, ((), "not_implemented", ())
        )
        definitions[path] = PropertyDefinition.build(
            property_path=path,
            applicable_role_types=roles_by_path.get(path, set()),
            value_type=_value_type(path),
            allows_none=_allows_none(path),
            allows_n_a=bool(n_a_roles_by_path.get(path)),
            resolver_sources=sources,
            canonicalization=canonicalization,
            materializer_targets=targets,
            implicit_word_default_policy=(
                "ALLOW_IF_PORTABLE_AND_EXPLICITLY_MATERIALIZED"
                if path in _PORTABLE_IMPLICIT_DEFAULTS
                else "GAP"
            ),
        )
    profiles = [
        StylePropertyProfile.build(
            role_type=role_type,
            properties=tuple(definitions[path] for path in paths),
            n_a_properties=n_a_by_role.get(role_type, frozenset()),
        )
        for role_type, paths in sorted(role_paths.items())
    ]
    return StylePropertyProfileRegistry.build(profiles)


DEFAULT_STYLE_PROPERTY_PROFILES = _build_default_registry()
