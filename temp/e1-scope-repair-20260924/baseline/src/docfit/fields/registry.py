"""Immutable, bounded access to one content-field Registry snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file, sha256_json

FIELD_VOCABULARY_SCHEMA_VERSION = "docfit_pre_input_field_vocabulary_v1"


@dataclass(frozen=True, slots=True)
class FieldRegistrySnapshot:
    path: Path
    sha256: str
    registry_id: str
    registry_version: str
    fields: tuple[JsonObject, ...]

    @classmethod
    def load(cls, path: Path) -> FieldRegistrySnapshot:
        source = path.expanduser().resolve(strict=True)
        try:
            if source.suffix.casefold() == ".json":
                value: Any = json.loads(source.read_text(encoding="utf-8"))
            else:
                value = yaml.safe_load(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="field_registry_unreadable",
                message="The configured field Registry cannot be read.",
            ) from error
        if not isinstance(value, dict):
            raise _invalid_registry()
        registry_id = value.get("registry_id")
        registry_version = value.get("registry_version")
        raw_fields = value.get("fields")
        if (
            not isinstance(registry_id, str)
            or not isinstance(registry_version, str)
            or not isinstance(raw_fields, list)
            or not raw_fields
        ):
            raise _invalid_registry()
        fields: list[JsonObject] = []
        seen: set[str] = set()
        extraction_policy_contract = isinstance(value.get("policy_schema"), dict)
        for item in raw_fields:
            if not isinstance(item, dict) or not isinstance(item.get("field_id"), str):
                raise _invalid_registry()
            field_id = item["field_id"]
            if field_id in seen:
                raise _invalid_registry()
            seen.add(field_id)
            fields.append(
                {
                    key: item[key]
                    for key in (
                        "field_id",
                        "label",
                        "meaning",
                        "content_type",
                        "cardinality",
                        "language",
                        "parent_field_id",
                        "notes",
                        "value_sources",
                        "student_extraction_policy",
                        "normalization",
                        "materialization",
                    )
                    if key in item
                }
            )
        for field in fields:
            parent_field_id = field.get("parent_field_id")
            if parent_field_id is not None and (
                not isinstance(parent_field_id, str) or parent_field_id not in seen
            ):
                raise _invalid_registry()
            value_sources = field.get("value_sources")
            if extraction_policy_contract and value_sources is None:
                raise _invalid_registry()
            if value_sources is not None and (
                not isinstance(value_sources, list)
                or not value_sources
                or not all(isinstance(value, str) and value for value in value_sources)
            ):
                raise _invalid_registry()
            extraction_policy = field.get("student_extraction_policy")
            if extraction_policy_contract and extraction_policy is None:
                raise _invalid_registry()
            if extraction_policy is not None and extraction_policy not in {
                "required",
                "optional",
                "not_applicable",
            }:
                raise _invalid_registry()
            normalization = field.get("normalization")
            if normalization is not None and not isinstance(normalization, dict):
                raise _invalid_registry()
            materialization = field.get("materialization")
            if materialization is not None and not isinstance(materialization, dict):
                raise _invalid_registry()
            if isinstance(materialization, dict):
                slot_layout = materialization.get("slot_layout")
                if slot_layout is not None and slot_layout != "centered_title":
                    raise _invalid_registry()
        return cls(
            source,
            sha256_file(source),
            registry_id,
            registry_version,
            tuple(fields),
        )

    def identity(self) -> JsonObject:
        return {
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "sha256": self.sha256,
        }

    def pre_input_vocabulary(
        self,
        *,
        allowed_field_ids: tuple[str, ...] | None = None,
    ) -> JsonObject:
        """Return the Agent-visible field-id vocabulary for this task snapshot."""

        fields_by_id = {str(field["field_id"]): field for field in self.fields}
        selected_ids = (
            tuple(str(field["field_id"]) for field in self.fields)
            if allowed_field_ids is None
            else tuple(dict.fromkeys(field_id.strip() for field_id in allowed_field_ids))
        )
        unknown = [field_id for field_id in selected_ids if field_id not in fields_by_id]
        if unknown:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="field_vocabulary_unknown_field_id",
                message=(
                    "Pre-input field vocabulary can only be built from the bound "
                    "Registry snapshot."
                ),
            )
        vocabulary: JsonObject = {
            "schema_version": FIELD_VOCABULARY_SCHEMA_VERSION,
            "registry": self.identity(),
            "allowed_field_ids": list(selected_ids),
            "field_count": len(selected_ids),
            "fields": [
                _field_vocabulary_entry(
                    fields_by_id[field_id],
                    has_children=self.has_children(field_id),
                )
                for field_id in selected_ids
            ],
        }
        vocabulary["digest"] = sha256_json(vocabulary)
        return vocabulary

    def has_children(self, field_id: str) -> bool:
        """Return whether this snapshot defines direct semantic child fields."""

        return any(field.get("parent_field_id") == field_id for field in self.fields)

    def lookup(self, field_id: str) -> JsonObject:
        item = next((field for field in self.fields if field["field_id"] == field_id), None)
        if item is None:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="field_not_registered",
                message="The requested field is not present in this Registry snapshot.",
                suggested_actions=(
                    "Select a field_id from the pre-input field_id_vocabulary "
                    "or return needs_input.",
                ),
            )
        return dict(item)


def _invalid_registry() -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="environment",
        code="field_registry_invalid",
        message="The configured field Registry does not match the supported snapshot contract.",
    )


def _field_vocabulary_entry(field: JsonObject, *, has_children: bool) -> JsonObject:
    entry: JsonObject = {
        key: field[key]
        for key in (
            "field_id",
            "label",
            "meaning",
            "content_type",
            "cardinality",
            "parent_field_id",
            "value_sources",
        )
        if key in field
    }
    entry["usage_affordance"] = {
        "selectable_by_agent": True,
        "source": "pre_input_field_vocabulary",
        "requires_agent_semantic_part": True,
        "has_parent_field": isinstance(field.get("parent_field_id"), str),
        "allowed_part_roles": _allowed_part_roles(field, has_children=has_children),
    }
    return entry


def _allowed_part_roles(field: JsonObject, *, has_children: bool) -> list[str]:
    content_type = str(field.get("content_type") or "").strip().casefold()
    raw_value_sources = field.get("value_sources", [])
    value_sources = {
        str(value).strip().casefold()
        for value in raw_value_sources
        if str(value).strip()
    } if isinstance(raw_value_sources, list) else set()
    if "system_generated" in value_sources:
        return ["generated_content"]
    if isinstance(field.get("parent_field_id"), str):
        return ["body_structure"]
    if content_type in {"text", "rich_text"} or (
        content_type == "section" and not has_children
    ):
        return ["fill_slot"]
    return []
