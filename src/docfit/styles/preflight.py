"""Compile one task-local style target before any student content is written."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docfit.content.presentation_roles import (
    PresentationRoleInventory,
    compile_actual_roles_from_student,
    compile_presentation_role_inventory,
)
from docfit.styles.actual_roles import ActualStyleRoleSet
from docfit.styles.contracts import StyleContractSet
from docfit.styles.presets import GeneralStylePreset
from docfit.styles.profiles import (
    DEFAULT_STYLE_PROPERTY_PROFILES,
    StylePropertyProfileRegistry,
)
from docfit.styles.selection import (
    StyleRoleSelectionReceipt,
    compile_selected_style_contracts,
    select_complete_style_roles,
)
from docfit.tools.runtime import JsonObject, sha256_json


@dataclass(frozen=True, slots=True)
class TaskLocalStyleTarget:
    """Digest-bound pre-write result consumed by Fill/Projection materialization."""

    presentation_roles: PresentationRoleInventory
    actual_roles: ActualStyleRoleSet
    selection: StyleRoleSelectionReceipt
    executable_contracts: StyleContractSet
    target_digest: str

    def as_dict(self) -> JsonObject:
        return {
            "schema_version": "docfit-task-local-style-target/v1",
            "presentation_roles": self.presentation_roles.as_dict(),
            "actual_roles": self.actual_roles.as_dict(),
            "selection": self.selection.as_dict(),
            "executable_style_contract_set": self.executable_contracts.as_dict(),
            "task_local_style_target_digest": self.target_digest,
        }


def compile_task_local_style_target(
    *,
    preset: GeneralStylePreset,
    student_content: Mapping[str, Any],
    student_inventory: Mapping[str, Any],
    school_candidates: Sequence[Mapping[str, Any]],
    school_observation_set_digest: str,
    template_sha256: str,
    retained_field_ids: Sequence[str] = (),
    global_field_ids: Sequence[str] = (),
    registry: StylePropertyProfileRegistry = DEFAULT_STYLE_PROPERTY_PROFILES,
) -> TaskLocalStyleTarget:
    """Close selection and executable codecs before Fill mutates the document.

    The function deliberately accepts already loaded domain artifacts instead of a
    public Tool request.  It therefore adds no Agent/runtime input surface.  Any
    missing role, stale digest, incomplete school candidate, or missing Word codec
    fails through the underlying typed domain boundary before content writing.
    """

    presentation_roles = compile_presentation_role_inventory(
        student_content=student_content,
        student_inventory=student_inventory,
    )
    actual_roles = compile_actual_roles_from_student(
        preset=preset,
        student_content=student_content,
        presentation_roles=presentation_roles,
        retained_field_ids=retained_field_ids,
        global_field_ids=global_field_ids,
    )
    selection = select_complete_style_roles(
        actual_roles=actual_roles,
        school_candidates=school_candidates,
        school_observation_set_digest=school_observation_set_digest,
        preset=preset,
        registry=registry,
    )
    executable_contracts = compile_selected_style_contracts(
        receipt=selection,
        template_sha256=template_sha256,
        registry=registry,
    )
    target_payload: JsonObject = {
        "schema_version": "docfit-task-local-style-target/v1",
        "template_sha256": template_sha256,
        "profile_registry_digest": selection.profile_registry_digest,
        "school_observation_set_digest": selection.school_observation_set_digest,
        "presentation_role_inventory_digest": presentation_roles.inventory_digest,
        "actual_role_set_digest": actual_roles.actual_role_set_digest,
        "selected_style_contract_set_digest": (
            selection.selected_style_contract_set_digest
        ),
        "executable_style_contract_set_digest": executable_contracts.digest,
    }
    return TaskLocalStyleTarget(
        presentation_roles=presentation_roles,
        actual_roles=actual_roles,
        selection=selection,
        executable_contracts=executable_contracts,
        target_digest=sha256_json(target_payload),
    )


__all__ = ["TaskLocalStyleTarget", "compile_task_local_style_target"]
