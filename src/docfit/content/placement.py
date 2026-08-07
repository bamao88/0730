"""Build a hash-bound Placement Actual from student semantics and a fill contract."""

from __future__ import annotations

from pathlib import Path

import yaml

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file

_BODY_TAGS = (
    "docfit.body.chapter_title",
    "docfit.body.chapter_body",
    "docfit.body.section_title",
    "docfit.body.section_body",
    "docfit.body.subsection_title",
    "docfit.body.subsection_body",
    "docfit.conclusion.title",
    "docfit.conclusion.body",
)
_SEGMENT_TAGS = {
    "body.chapters": _BODY_TAGS[0],
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
        or payload.get("schema_version") != "docfit-template-fill-contract/v1"
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="fill_contract_invalid",
            message="The target fill contract has an unsupported shape.",
        )
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
    slots = contract.get("slots")
    if not isinstance(slots, list):
        raise _invalid("placement_slots_invalid", "The fill contract contains no slot list.")
    declared_body_tags = tuple(
        str(slot.get("locator", {}).get("value"))
        for slot in slots
        if isinstance(slot, dict)
        and isinstance(slot.get("locator"), dict)
        and slot.get("locator", {}).get("value") in _BODY_TAGS
    )
    body_anchor_tag = declared_body_tags[0] if declared_body_tags else _BODY_TAGS[0]
    body_present = segments.get("body.chapters", {}).get("status") == "extracted"
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
        target_status = "missing"
        if tag in _BODY_TAGS:
            target_status = "filled_by_body_segment" if body_present else "missing"
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
            }
        )
        if slot.get("required") is True and target_status == "missing":
            missing_required.append({"slot_id": slot_id, "field_id": field_id, "tag": tag})

    body = segments.get("body.chapters")
    if isinstance(body, dict) and body.get("status") == "extracted":
        operations.append(
            {
                "action": "replace_block_content_control",
                "slot_id": "slot.body.aggregate",
                "field_id": "body.chapters",
                "tag": body_anchor_tag,
                "source_object_ids": list(body.get("source_object_ids", [])),
                "source_locators": list(body.get("source_locators", [])),
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
