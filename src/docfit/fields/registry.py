"""Immutable, bounded access to one content-field Registry snapshot."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


def _normalize(value: str) -> str:
    return "".join(value.split()).casefold()


_SEARCH_STOP_WORDS = {
    "all",
    "available",
    "cover",
    "current",
    "field",
    "fields",
    "fillable",
    "list",
    "object",
    "page",
    "template",
}
_SEARCH_ALIASES = {
    "college": "department",
    "student": "author",
    "supervisor": "advisor",
    "teacher": "advisor",
    "topic": "title",
    "作者": "author",
    "学生": "author",
    "学院": "department",
    "院系": "department",
    "指导教师": "advisor",
    "导师": "advisor",
    "论文题目": "title",
    "题目": "title",
}


def _search_terms(value: str) -> tuple[str, ...]:
    raw = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", value.casefold())
    terms = [_SEARCH_ALIASES.get(term, term) for term in raw if term not in _SEARCH_STOP_WORDS]
    return tuple(dict.fromkeys(terms))


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
        query_terms = _search_terms(text)
        ranked: list[tuple[int, int, JsonObject]] = []
        for index, item in enumerate(self.fields):
            field_id = _normalize(str(item.get("field_id", "")))
            label = _normalize(str(item.get("label", "")))
            meaning = _normalize(str(item.get("meaning", "")))
            notes = _normalize(str(item.get("notes", "")))
            score = 0
            if query in (field_id, label):
                score = 1000
            elif query in field_id or query in label:
                score = 800
            elif query in meaning:
                score = 500
            elif query in notes:
                score = 200
            else:
                matched_terms = 0
                for term in query_terms:
                    normalized_term = _normalize(term)
                    if normalized_term in field_id:
                        score += 100
                        matched_terms += 1
                    elif normalized_term in label:
                        score += 80
                        matched_terms += 1
                    elif normalized_term in meaning:
                        score += 30
                        matched_terms += 1
                    elif normalized_term in notes:
                        score += 10
                        matched_terms += 1
                if matched_terms == 0:
                    continue
                score += matched_terms * 10
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
