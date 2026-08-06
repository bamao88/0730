"""Shared strict parsing and Registry binding for template decision compilers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from docfit.template.runtime.paths import task_file
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


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
