"""Immutable, bounded access to one content-field Registry snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


def _normalize(value: str) -> str:
    return "".join(value.split()).casefold()


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
                    )
                    if key in item
                }
            )
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

    def lookup(self, field_id: str) -> JsonObject:
        item = next((field for field in self.fields if field["field_id"] == field_id), None)
        if item is None:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="field_not_registered",
                message="The requested field is not present in this Registry snapshot.",
                suggested_actions=("search_registry_for_current_object",),
            )
        return dict(item)

    def search(self, text: str, *, limit: int = 5) -> tuple[JsonObject, ...]:
        query = _normalize(text)
        if not query:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="field_query_empty",
                message="Registry search requires a non-empty object-specific query.",
            )
        ranked: list[tuple[int, int, JsonObject]] = []
        for index, item in enumerate(self.fields):
            field_id = _normalize(str(item.get("field_id", "")))
            label = _normalize(str(item.get("label", "")))
            meaning = _normalize(str(item.get("meaning", "")))
            notes = _normalize(str(item.get("notes", "")))
            score = 0
            if query in (field_id, label):
                score = 100
            elif query in field_id or query in label:
                score = 80
            elif query in meaning:
                score = 50
            elif query in notes:
                score = 20
            else:
                tokens = [value for value in (label, meaning, notes) if value]
                score = max(
                    (sum(1 for char in set(query) if char in value) for value in tokens),
                    default=0,
                )
                if score < max(2, len(set(query)) // 2):
                    continue
            ranked.append((score, -index, item))
        ranked.sort(reverse=True, key=lambda value: (value[0], value[1]))
        return tuple(dict(item) for _, _, item in ranked[:limit])


def _invalid_registry() -> ToolFailure:
    return ToolFailure(
        status="error",
        origin="environment",
        code="field_registry_invalid",
        message="The configured field Registry does not match the supported snapshot contract.",
    )
