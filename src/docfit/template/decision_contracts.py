"""Shared strict parsing and Registry binding for template decision compilers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from docfit.template.runtime.paths import task_file
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file

_FLAT_STYLE_FIELDS = {
    "run.font_east_asia": ("font", "east_asia"),
    "run.font_latin": ("font", "latin"),
    "run.font_ascii": ("font", "ascii"),
    "run.font_hansi": ("font", "hansi"),
    "run.font_complex_script": ("font", "complex_script"),
    "run.language": ("font", "language"),
    "run.font_size_pt": ("font", "size_pt"),
    "run.bold": ("font", "bold"),
    "run.italic": ("font", "italic"),
    "run.color": ("font", "color"),
    "paragraph.alignment": ("paragraph", "alignment"),
    "paragraph.first_line_indent_pt": ("paragraph", "first_line_indent_pt"),
    "paragraph.hanging_indent_pt": ("paragraph", "hanging_indent_pt"),
    "paragraph.left_indent_pt": ("paragraph", "left_indent_pt"),
    "paragraph.right_indent_pt": ("paragraph", "right_indent_pt"),
    "paragraph.line_rule": ("paragraph", "line_spacing_rule"),
    "paragraph.line_spacing_rule": ("paragraph", "line_spacing_rule"),
    "paragraph.line_spacing_pt": ("paragraph", "line_spacing_pt"),
    "paragraph.line_value": ("paragraph", "line_value"),
    "paragraph.space_before_pt": ("paragraph", "space_before_pt"),
    "paragraph.space_after_pt": ("paragraph", "space_after_pt"),
    "paragraph.keep_lines": ("paragraph", "keep_lines"),
    "paragraph.keep_next": ("paragraph", "keep_next"),
    "paragraph.widow_control": ("paragraph", "widow_control"),
    "paragraph.outline_level": ("paragraph", "outline_level"),
}
_FONT_STRING_FIELDS = {
    "east_asia",
    "latin",
    "ascii",
    "hansi",
    "complex_script",
    "language",
    "color",
}
_FONT_BOOLEAN_FIELDS = {"bold", "italic"}
_PARAGRAPH_STRING_FIELDS = {"alignment", "line_spacing_rule"}
_PARAGRAPH_BOOLEAN_FIELDS = {"keep_lines", "keep_next", "widow_control"}
_PARAGRAPH_NUMBER_FIELDS = {
    "first_line_indent_pt",
    "hanging_indent_pt",
    "left_indent_pt",
    "right_indent_pt",
    "line_spacing_pt",
    "line_value",
    "space_before_pt",
    "space_after_pt",
}


def _invalid_effective_style(field: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code="invalid_effective_style",
        message=f"{field} does not match the v1 effective-style contract.",
    )


def _validate_style_leaf(group: str, key: str, value: Any, *, field: str) -> None:
    if value is None:
        return
    if group == "font":
        if key in _FONT_STRING_FIELDS and isinstance(value, str):
            if key != "color" or re.fullmatch(r"[0-9A-F]{6}", value):
                return
        elif (
            key == "size_pt"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ) or (key in _FONT_BOOLEAN_FIELDS and isinstance(value, bool)):
            return
    elif group == "paragraph":
        if key in _PARAGRAPH_STRING_FIELDS and isinstance(value, str):
            return
        if key in _PARAGRAPH_BOOLEAN_FIELDS and isinstance(value, bool):
            return
        if key in _PARAGRAPH_NUMBER_FIELDS and isinstance(
            value, (int, float)
        ) and not isinstance(value, bool):
            return
        if (
            key == "outline_level"
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            return
    raise _invalid_effective_style(field)


def normalize_effective_style(value: Any, *, field: str) -> JsonObject:
    """Normalize trusted observation-style facts to the public fill-contract shape."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise _invalid_effective_style(field)
    if not value:
        return {}
    public_groups = {"font", "paragraph", "container", "page"}
    if set(value).issubset(public_groups):
        normalized: JsonObject = {}
        for group, raw_properties in value.items():
            if not isinstance(raw_properties, dict) or not all(
                isinstance(key, str) for key in raw_properties
            ):
                raise _invalid_effective_style(field)
            if group in {"font", "paragraph"}:
                for key, item in raw_properties.items():
                    _validate_style_leaf(group, key, item, field=field)
            normalized[group] = dict(raw_properties)
        return normalized
    if any(key in public_groups for key in value):
        raise _invalid_effective_style(field)
    normalized = {}
    for key, item in value.items():
        target = _FLAT_STYLE_FIELDS.get(key)
        if target is None:
            raise _invalid_effective_style(field)
        group, public_key = target
        properties = normalized.setdefault(group, {})
        if not isinstance(properties, dict) or public_key in properties:
            raise _invalid_effective_style(field)
        _validate_style_leaf(group, public_key, item, field=field)
        properties[public_key] = item
    return normalized


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _StrictLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="invalid_decisions",
                message="Decision object keys must be strings.",
            )
        if key in result:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="duplicate_decision_key",
                message="The decisions file contains a duplicate object key.",
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_decision_object(path: Path) -> JsonObject:
    try:
        raw = path.read_bytes()
        if len(raw) > 2 * 1024 * 1024 or raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("size or BOM")
        text = raw.decode("utf-8")
        value: Any = (
            json.loads(text)
            if path.suffix.casefold() == ".json"
            else yaml.load(text, Loader=_StrictLoader)
        )
    except ToolFailure:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_decisions",
            message="The template decisions file cannot be parsed safely.",
        ) from error
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_decisions",
            message="Template decisions must contain one object.",
        )
    return value


def decision_objects(value: Any, field: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="invalid_artifact_decisions",
            message=f"{field} must be an array of objects.",
        )
    return value


def resolve_registry(
    decisions: JsonObject,
    *,
    task_root: Path,
) -> tuple[JsonObject, set[str]]:
    reference = decisions.get("field_registry_ref")
    if not isinstance(reference, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="A field Registry reference is required.",
        )
    path = task_file(
        reference.get("path"),
        task_root=task_root,
        field="field_registry_ref.path",
        allowed_roots=("input",),
    )
    registry = load_decision_object(path)
    if (
        reference.get("registry_id") != registry.get("registry_id")
        or reference.get("registry_version") != registry.get("registry_version")
        or reference.get("sha256") != sha256_file(path)
        or registry.get("registry_id") != "docfit.thesis.content_fields"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry binding does not match the referenced file.",
        )
    fields = registry.get("fields")
    if not isinstance(fields, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="registry_hash_mismatch",
            message="The field Registry has no valid field inventory.",
        )
    field_ids = {
        item["field_id"]
        for item in fields
        if isinstance(item, dict) and isinstance(item.get("field_id"), str)
    }
    return reference, field_ids
