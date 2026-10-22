"""Internal action registry for the stable Agent-visible ``docx_edit`` Tool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

OfficeEditAction = Literal["replace_text", "apply_style", "set_properties"]
ImportEditAction = Literal["import_content_objects"]
DomainEditAction = Literal[
    "clear_content",
    "remove_object",
    "materialize_slot",
    "materialize_structure",
    "normalize_effective_format",
    "refresh_toc",
    "ensure_page_start",
]
EditAction = OfficeEditAction | ImportEditAction | DomainEditAction
EditActionFamily = Literal["office", "import", "domain"]

OFFICE_EDIT_ACTIONS: tuple[OfficeEditAction, ...] = (
    "replace_text",
    "apply_style",
    "set_properties",
)
IMPORT_EDIT_ACTIONS: tuple[ImportEditAction, ...] = ("import_content_objects",)
DOMAIN_EDIT_ACTIONS: tuple[DomainEditAction, ...] = (
    "clear_content",
    "remove_object",
    "materialize_slot",
    "materialize_structure",
    "normalize_effective_format",
    "refresh_toc",
    "ensure_page_start",
)
EDIT_ACTIONS: tuple[EditAction, ...] = (
    *OFFICE_EDIT_ACTIONS,
    *IMPORT_EDIT_ACTIONS,
    *DOMAIN_EDIT_ACTIONS,
)
DOMAIN_EDIT_MAX_BATCH_OPERATIONS = 32


@dataclass(frozen=True)
class EditActionSpec:
    name: EditAction
    family: EditActionFamily
    requires_target_ref: bool
    requires_field_registry: bool = False


EDIT_ACTION_SPECS: dict[str, EditActionSpec] = {
    **{
        action: EditActionSpec(action, family="office", requires_target_ref=True)
        for action in OFFICE_EDIT_ACTIONS
    },
    "import_content_objects": EditActionSpec(
        "import_content_objects",
        family="import",
        requires_target_ref=False,
    ),
    "clear_content": EditActionSpec(
        "clear_content",
        family="domain",
        requires_target_ref=True,
    ),
    "remove_object": EditActionSpec(
        "remove_object",
        family="domain",
        requires_target_ref=True,
    ),
    "materialize_slot": EditActionSpec(
        "materialize_slot",
        family="domain",
        requires_target_ref=True,
        requires_field_registry=True,
    ),
    "materialize_structure": EditActionSpec(
        "materialize_structure",
        family="domain",
        requires_target_ref=True,
        requires_field_registry=True,
    ),
    "normalize_effective_format": EditActionSpec(
        "normalize_effective_format",
        family="domain",
        requires_target_ref=True,
    ),
    "refresh_toc": EditActionSpec(
        "refresh_toc",
        family="domain",
        requires_target_ref=True,
    ),
    "ensure_page_start": EditActionSpec(
        "ensure_page_start",
        family="domain",
        requires_target_ref=True,
    ),
}


def edit_action_spec(value: object) -> EditActionSpec | None:
    if not isinstance(value, str):
        return None
    return EDIT_ACTION_SPECS.get(value)


def is_domain_edit_action(value: object) -> bool:
    spec = edit_action_spec(value)
    return spec is not None and spec.family == "domain"


def require_domain_edit_action(value: object) -> DomainEditAction:
    if is_domain_edit_action(value):
        return cast(DomainEditAction, value)
    raise AssertionError(f"unsupported direct object action: {value}")
