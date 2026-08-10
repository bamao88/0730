"""Build a hash-bound Placement Actual from student semantics and a fill contract."""

from __future__ import annotations

from pathlib import Path

import yaml

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.styles import StyleContractSet
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file

_BODY_ROLE_FIELDS = frozenset(
    {
        "body.heading.level1",
        "body.heading.level2",
        "body.heading.level3",
        "body.paragraph",
        "body.figure",
        "body.figure.caption",
        "body.table.caption",
        "body.equation",
        "conclusion.title",
        "conclusion.body",
    }
)
_SEGMENT_TAGS = {
    "references.entries": "docfit.references",
    "acknowledgement.body": "docfit.acknowledgement",
    "appendix.body": "docfit.appendix",
}


def load_fill_contract(path: Path) -> JsonObject:
    source = path.expanduser().resolve(strict=True)
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="fill_contract_unreadable",
            message="The target fill contract cannot be read.",
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "docfit-template-fill-contract/v2"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="fill_contract_invalid",
            message="The target fill contract has an unsupported shape.",
        )
    try:
        style_contracts = StyleContractSet.from_fill_contract(payload)
    except ToolFailure as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="fill_contract_style_contracts_invalid",
            message="The target fill contract contains an invalid Style Contract Set.",
        ) from error
    if payload.get("style_contract_set_digest") != style_contracts.digest:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="fill_contract_style_set_stale",
            message="The target fill contract Style Contract Set digest is stale.",
        )
    slots = payload.get("slots")
    if not isinstance(slots, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="fill_contract_slots_invalid",
            message="The target fill contract contains no slot list.",
        )
    for slot in slots:
        if not isinstance(slot, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="fill_contract_slot_invalid",
                message="Every target fill slot must be an object.",
            )
        if "expected_value_style" in slot or "style_id" in slot:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="fill_contract_inline_style_forbidden",
                message="Fill Contract v2 slots may only carry style_contract_ref.",
            )
        reference = slot.get("style_contract_ref")
        if not isinstance(reference, dict):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="fill_contract_style_ref_missing",
                message="Every Fill Contract v2 slot requires a Style Contract reference.",
            )
        style_contracts.resolve(reference)
    payload["contract_path"] = str(source)
    payload["contract_sha256"] = sha256_file(source)
    return payload


def build_placement(
    *,
    student_content: JsonObject,
    contract: JsonObject,
    registry: FieldRegistrySnapshot,
    template_docx: Path,
) -> JsonObject:
    """Map evidence-backed student facts to deterministic template tag operations."""

    template_hash = sha256_file(template_docx)
    if contract.get("template_sha256") != template_hash:
        raise _invalid(
            "placement_template_stale", "The fill contract is bound to another template snapshot."
        )
    registry_ref = contract.get("field_registry_ref")
    if not isinstance(registry_ref, dict) or any(
        registry_ref.get(key) != registry.identity()[key]
        for key in ("registry_id", "registry_version", "sha256")
    ):
        raise _invalid(
            "placement_registry_stale", "The fill contract is bound to another Registry snapshot."
        )
    if student_content.get("registry") != registry.identity():
        raise _invalid(
            "placement_student_registry_stale",
            "Student content is bound to another Registry snapshot.",
        )

    fields = {
        value.get("field_id"): value
        for value in student_content.get("fields", [])
        if isinstance(value, dict) and isinstance(value.get("field_id"), str)
    }
    segments = {
        value.get("field_id"): value
        for value in student_content.get("segments", [])
        if isinstance(value, dict) and isinstance(value.get("field_id"), str)
    }
    operations: list[JsonObject] = []
    targets: list[JsonObject] = []
    missing_required: list[JsonObject] = []
    try:
        style_contracts = StyleContractSet.from_fill_contract(contract)
    except ToolFailure as error:
        raise _invalid(
            "placement_style_contracts_invalid",
            "The fill contract Style Contract Set is invalid or incomplete.",
        ) from error
    slots = contract.get("slots")
    if not isinstance(slots, list):
        raise _invalid("placement_slots_invalid", "The fill contract contains no slot list.")
    body_present = segments.get("body.chapters", {}).get("status") == "extracted"
    declared_body_tags = tuple(
        str(slot.get("locator", {}).get("value"))
        for slot in slots
        if isinstance(slot, dict)
        and slot.get("field_id") in _BODY_ROLE_FIELDS
        and isinstance(slot.get("locator"), dict)
        and isinstance(slot.get("locator", {}).get("value"), str)
    )
    if body_present and not declared_body_tags:
        raise _invalid(
            "placement_body_slots_missing",
            "Extracted body content requires at least one body presentation-role slot.",
        )
    body_anchor_tag = declared_body_tags[0] if declared_body_tags else ""
    declared_body_tag_set = set(declared_body_tags)
    body_role_refs: dict[str, JsonObject] = {}
    body_anchor_ref: JsonObject | None = None
    for slot in slots:
        if not isinstance(slot, dict):
            raise _invalid("placement_slot_invalid", "A fill slot has an invalid shape.")
        slot_id = slot.get("slot_id")
        field_id = slot.get("field_id")
        locator = slot.get("locator")
        if (
            not isinstance(slot_id, str)
            or not isinstance(field_id, str)
            or not isinstance(locator, dict)
        ):
            raise _invalid(
                "placement_slot_invalid", "A fill slot is missing identity or locator data."
            )
        tag = locator.get("value")
        if locator.get("type") != "content_control_tag" or not isinstance(tag, str):
            raise _invalid(
                "placement_locator_unsupported",
                "This debug fill only supports content-control tags.",
            )
        raw_style_ref = slot.get("style_contract_ref")
        if not isinstance(raw_style_ref, dict):
            raise _invalid(
                "placement_slot_style_contract_invalid",
                f"Fill slot {slot_id} has no complete Style Contract reference.",
            )
        try:
            style_contract = style_contracts.resolve(raw_style_ref)
        except ToolFailure as error:
            raise _invalid(
                "placement_slot_style_contract_invalid",
                f"Fill slot {slot_id} has no valid Style Contract reference.",
            ) from error
        style_ref: JsonObject = {
            "style_contract_id": style_contract.style_contract_id,
            "contract_digest": style_contract.contract_digest,
        }
        target_status = "missing"
        if tag in declared_body_tag_set:
            target_status = "filled_by_body_segment" if body_present else "missing"
            body_role_refs[field_id] = style_ref
            if tag == body_anchor_tag:
                body_anchor_ref = style_ref
        elif field_id in _SEGMENT_TAGS:
            segment = segments.get(field_id)
            if isinstance(segment, dict) and segment.get("status") == "extracted":
                target_status = "filled"
                operations.append(
                    {
                        "action": "replace_block_content_control",
                        "slot_id": slot_id,
                        "field_id": field_id,
                        "tag": tag,
                        "source_object_ids": list(segment.get("source_object_ids", [])),
                        "source_locators": list(segment.get("source_locators", [])),
                        "style_contract_ref": style_ref,
                    }
                )
        else:
            field = fields.get(field_id)
            if isinstance(field, dict) and field.get("status") == "extracted":
                target_status = "filled"
                operations.append(
                    {
                        "action": "replace_text_content_control",
                        "slot_id": slot_id,
                        "field_id": field_id,
                        "tag": tag,
                        "value": field.get("value"),
                        "source_object_ids": list(field.get("source_object_ids", [])),
                        "style_contract_ref": style_ref,
                    }
                )
            elif isinstance(field, dict) and field.get("status") == "conflict":
                target_status = "conflict"
        targets.append(
            {
                "slot_id": slot_id,
                "field_id": field_id,
                "tag": tag,
                "required": slot.get("required") is True,
                "status": target_status,
                "style_contract_ref": style_ref,
            }
        )
        if slot.get("required") is True and target_status == "missing":
            missing_required.append({"slot_id": slot_id, "field_id": field_id, "tag": tag})

    body = segments.get("body.chapters")
    if isinstance(body, dict) and body.get("status") == "extracted":
        if body_anchor_ref is None:
            raise _invalid(
                "placement_body_style_contract_missing",
                "The body aggregate has no anchor Style Contract reference.",
            )
        operations.append(
            {
                "action": "replace_block_content_control",
                "slot_id": "slot.body.aggregate",
                "field_id": "body.chapters",
                "tag": body_anchor_tag,
                "source_object_ids": list(body.get("source_object_ids", [])),
                "source_locators": list(body.get("source_locators", [])),
                "style_contract_ref": body_anchor_ref,
                "style_role_refs": body_role_refs,
                "remove_tags_after_fill": [
                    tag for tag in declared_body_tags if tag != body_anchor_tag
                ],
            }
        )
    unresolved_regions = [
        str(value.get("region_id"))
        for value in contract.get("regions", [])
        if isinstance(value, dict) and value.get("required") is True
    ]
    reasons: list[str] = []
    if contract.get("status") != "accepted":
        reasons.append("template_fill_contract_not_human_accepted")
    if missing_required:
        reasons.append("required_slots_missing")
    if unresolved_regions:
        reasons.append("generated_regions_not_materialized")
    if any(value.get("status") == "conflict" for value in targets):
        reasons.append("source_field_conflict")
    return {
        "schema_version": "docfit-placement-actual/v1",
        "status": "COMPLETE" if not reasons else "PARTIAL",
        "source_sha256": student_content.get("source_sha256"),
        "template_sha256": template_hash,
        "contract": {
            "contract_id": contract.get("contract_id"),
            "revision": contract.get("revision"),
            "status": contract.get("status"),
            "sha256": contract.get("contract_sha256"),
            "style_contract_set_digest": style_contracts.digest,
        },
        "registry": registry.identity(),
        "targets": targets,
        "operations": operations,
        "missing_required": missing_required,
        "unresolved_regions": unresolved_regions,
        "partial_reasons": reasons,
    }


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="request", code=code, message=message)
