"""Compile the task-local set of style roles before any content is written."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from docfit.styles.presets import GeneralStylePreset
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

ActualRoleSourceKind = Literal["student_content", "retained_structure", "global_document"]


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_actual_style_role_inputs",),
    )


@dataclass(frozen=True, slots=True)
class ActualRoleSource:
    """Why one field/component makes a style role necessary in this task."""

    source_kind: ActualRoleSourceKind
    field_id: str
    component: str

    def as_dict(self) -> JsonObject:
        return {
            "source_kind": self.source_kind,
            "field_id": self.field_id,
            "component": self.component,
        }


@dataclass(frozen=True, slots=True)
class ActualStyleRole:
    """One complete semantic style role required by the final document."""

    style_role_id: str
    role_type: str
    sources: tuple[ActualRoleSource, ...]

    def as_dict(self) -> JsonObject:
        return {
            "style_role_id": self.style_role_id,
            "role_type": self.role_type,
            "sources": [item.as_dict() for item in self.sources],
        }


@dataclass(frozen=True, slots=True)
class ActualStyleRoleSet:
    """Digest-bound role union from content, retained structure, and global document needs."""

    preset_id: str
    preset_version: str
    preset_digest: str
    roles: tuple[ActualStyleRole, ...]
    non_style_fields: tuple[str, ...]
    actual_role_set_digest: str

    @classmethod
    def compile(
        cls,
        *,
        preset: GeneralStylePreset,
        student_field_ids: Iterable[str],
        retained_field_ids: Iterable[str] = (),
        global_field_ids: Iterable[str] = (),
    ) -> ActualStyleRoleSet:
        source_fields: tuple[tuple[ActualRoleSourceKind, tuple[str, ...]], ...] = (
            ("student_content", _normalized_fields(student_field_ids)),
            ("retained_structure", _normalized_fields(retained_field_ids)),
            ("global_document", _normalized_fields(global_field_ids)),
        )
        role_sources: dict[str, list[ActualRoleSource]] = {}
        non_style_fields: set[str] = set()
        for source_kind, field_ids in source_fields:
            for field_id in field_ids:
                binding = preset.field_binding(field_id)
                style_components = {
                    component: role_id
                    for component, role_id in binding.components.items()
                    if role_id.startswith("style.")
                }
                if not style_components:
                    non_style_fields.add(field_id)
                    continue
                for component, role_id in sorted(style_components.items()):
                    role_sources.setdefault(role_id, []).append(
                        ActualRoleSource(source_kind, field_id, component)
                    )
        roles = tuple(
            ActualStyleRole(
                style_role_id=role_id,
                role_type=preset.resolve_role(role_id).role_type,
                sources=tuple(
                    sorted(
                        set(sources),
                        key=lambda item: (item.source_kind, item.field_id, item.component),
                    )
                ),
            )
            for role_id, sources in sorted(role_sources.items())
        )
        payload: JsonObject = {
            "schema_version": "docfit-actual-style-role-set/v1",
            "preset_ref": {
                "preset_id": preset.preset_id,
                "preset_version": preset.preset_version,
                "preset_digest": preset.digest,
            },
            "roles": [item.as_dict() for item in roles],
            "non_style_fields": sorted(non_style_fields),
        }
        return cls(
            preset_id=preset.preset_id,
            preset_version=preset.preset_version,
            preset_digest=preset.digest,
            roles=roles,
            non_style_fields=tuple(sorted(non_style_fields)),
            actual_role_set_digest=sha256_json(payload),
        )

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": "docfit-actual-style-role-set/v1",
            "preset_ref": {
                "preset_id": self.preset_id,
                "preset_version": self.preset_version,
                "preset_digest": self.preset_digest,
            },
            "roles": [item.as_dict() for item in self.roles],
            "non_style_fields": list(self.non_style_fields),
            "actual_role_set_digest": self.actual_role_set_digest,
        }


def _normalized_fields(values: Iterable[str]) -> tuple[str, ...]:
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise _failure(
                "actual_style_role_field_invalid",
                "Actual style role inputs must be canonical non-empty field IDs.",
            )
        result.add(value)
    return tuple(sorted(result))


__all__ = ["ActualRoleSource", "ActualStyleRole", "ActualStyleRoleSet"]
