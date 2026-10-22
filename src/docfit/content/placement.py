"""Build a hash-bound Placement Actual from student semantics and a fill contract."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from docfit.content.partition import (
    BODY_FLOW_AGGREGATE_FIELD_ID,
    compile_final_content_partition,
)
from docfit.fields.registry import FieldRegistrySnapshot
from docfit.styles import StyleContractSet
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_file


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

    if student_content.get("schema_version") != "docfit-student-content-model/v2":
        raise _invalid(
            "placement_student_content_invalid",
            "Placement requires the ordered Student Content Model.",
        )
    if student_content.get("status") != "READY":
        raise _invalid(
            "placement_student_content_not_ready",
            "Student content must resolve every semantic content item before placement.",
        )
    # Keep the artifact validator on the consumer boundary without introducing
    # the styles.capture -> content package import cycle at module load time.
    from docfit.template.artifact import validate_published_template_artifact

    phase6 = validate_published_template_artifact(
        template_docx=template_docx,
        fill_contract=contract,
    )
    template_hash = phase6["template_sha256"]
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

    if student_content.get("schema_version") != "docfit-student-content-model/v2":
        raise _invalid(
            "placement_student_content_invalid",
            "Placement requires the ordered Student Content Model.",
        )
    if student_content.get("status") != "READY":
        raise _invalid(
            "placement_student_content_not_ready",
            "Student content must resolve every semantic content item before placement.",
        )
    partition = compile_final_content_partition(
        student_content=student_content,
        contract=contract,
        registry=registry,
    )
    named_fields = partition["named_fields"]
    assert isinstance(named_fields, dict)
    body_flow = partition["body_flow"]
    assert isinstance(body_flow, dict)
    body_items = body_flow["items"]
    assert isinstance(body_items, list)

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
    body_roles = partition["template"]["body_flow_roles"]
    assert isinstance(body_roles, list)
    body_present = bool(body_items)
    declared_body_tags = tuple(
        str(slot.get("locator", {}).get("value"))
        for slot in body_roles
        if isinstance(slot, dict)
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
    body_anchor_slot_ref: str | None = None

    body_style_fallbacks: list[str] = []
    ignored_debug_body_style_roles: list[str] = []

    for slot in slots:
        if not isinstance(slot, dict):
            raise _invalid("placement_slot_invalid", "A fill slot has an invalid shape.")
        slot_ref = slot.get("slot_ref")
        field_id = slot.get("field_id")
        locator = slot.get("locator")
        if (
            not isinstance(slot_ref, str)
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
                f"Fill slot {slot_ref} has no complete Style Contract reference.",
            )
        try:
            style_contract = style_contracts.resolve(raw_style_ref)
        except ToolFailure as error:
            raise _invalid(
                "placement_slot_style_contract_invalid",
                f"Fill slot {slot_ref} has no valid Style Contract reference.",
            ) from error
        style_ref: JsonObject = {
            "style_contract_id": style_contract.style_contract_id,
            "contract_digest": style_contract.contract_digest,
        }
        target_status = "missing"
        if tag in declared_body_tag_set:
            matching_body_items = [
                item
                for item in body_items
                if isinstance(item, dict) and item.get("field_id") == field_id
            ]
            target_status = "filled_by_body_items" if matching_body_items else "missing"
            if _is_debug_body_role_binding(slot):
                if matching_body_items:
                    target_status = "debug_role_binding_ignored"
                    ignored_debug_body_style_roles.append(field_id)
                continue
            previous_ref = body_role_refs.get(field_id)
            if previous_ref is not None and previous_ref != style_ref:
                raise _invalid(
                    "placement_body_role_style_conflict",
                    f"Body flow field {field_id} has multiple Style Contract refs.",
                )
            body_role_refs[field_id] = style_ref
            if tag == body_anchor_tag:
                body_anchor_ref = style_ref
                body_anchor_slot_ref = slot_ref
        else:
            field_items = named_fields.get(field_id, [])
            if not isinstance(field_items, list):
                raise _invalid(
                    "placement_partition_invalid",
                    "The final content partition has an invalid named-field group.",
                )
            if field_items:
                target_status = "filled"
                if _requires_block_copy(field_items, registry):
                    operation: JsonObject = {
                        "action": "replace_block_content_control",
                        "slot_ref": slot_ref,
                        "field_id": field_id,
                        "tag": tag,
                        "style_contract_ref": style_ref,
                    }
                    operation.update(_block_source(field_items))
                    operations.append(operation)
                else:
                    operations.append(
                        {
                            "action": "replace_text_content_control",
                            "slot_ref": slot_ref,
                            "field_id": field_id,
                            "tag": tag,
                            "value": "\n".join(
                                str(item["value"])
                                for item in field_items
                                if isinstance(item.get("value"), str)
                            ),
                            "source_object_ids": [
                                str(object_id)
                                for item in field_items
                                for object_id in item.get("source_object_ids", [])
                            ],
                            "source_content_items": [dict(item) for item in field_items],
                            "style_contract_ref": style_ref,
                        }
                    )
        targets.append(
            {
                "slot_ref": slot_ref,
                "field_id": field_id,
                "tag": tag,
                "required": slot.get("required") is True,
                "status": target_status,
                "style_contract_ref": style_ref,
            }
        )
        if slot.get("required") is True and target_status == "missing":
            missing_required.append({"slot_ref": slot_ref, "field_id": field_id, "tag": tag})

    if body_items:
        if body_anchor_ref is None:
            raise _invalid(
                "placement_body_style_contract_missing",
                "The body aggregate has no anchor Style Contract reference.",
            )
        body_style_fallbacks = _body_style_fallbacks(
            body_items=body_items,
            body_role_refs=body_role_refs,
            fallback_ref=body_role_refs.get("body.paragraph") or body_anchor_ref,
        )
        if body_anchor_slot_ref is None:
            raise _invalid(
                "placement_body_slot_ref_missing",
                "The body aggregate has no Harness slot_ref anchor.",
            )
        body_operation: JsonObject = {
            "action": "replace_block_content_control",
            "slot_ref": body_anchor_slot_ref,
            "field_id": BODY_FLOW_AGGREGATE_FIELD_ID,
            "tag": body_anchor_tag,
            "style_contract_ref": body_anchor_ref,
            "style_role_refs": body_role_refs,
            "relations": [dict(value) for value in student_content.get("relations", [])],
            "ordering_policy": "student_source_order_only",
            "remove_tags_after_fill": [tag for tag in declared_body_tags if tag != body_anchor_tag],
        }

        body_operation.update(_block_source(body_items))
        operations.append(body_operation)
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
    if body_style_fallbacks and contract.get("status") != "accepted":
        reasons.append("body_style_roles_missing")
    if unresolved_regions:
        reasons.append("generated_regions_not_materialized")
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
        "content_partition": {
            "schema_version": partition["schema_version"],
            "partition_digest": partition["partition_digest"],
            "body_flow_field_ids": partition["body_flow"]["field_ids"],
            "body_structure_field_ids": partition["body_flow"]["structure_field_ids"],
            "named_field_ids": sorted(partition["named_fields"]),
            "generated_region_ids": [
                str(region.get("region_id"))
                for region in partition["template"]["generated_regions"]
                if isinstance(region, dict)
            ],
            "retained_region_ids": [
                str(region.get("region_id"))
                for region in partition["template"]["retained_regions"]
                if isinstance(region, dict)
            ],
        },
        "operations": operations,
        "missing_required": missing_required,
        "unresolved_regions": unresolved_regions,
        "body_style_fallbacks": body_style_fallbacks,
        "ignored_debug_body_style_roles": sorted(set(ignored_debug_body_style_roles)),
        "partial_reasons": reasons,
    }


def _requires_block_copy(
    items: list[JsonObject],
    registry: FieldRegistrySnapshot,
) -> bool:
    field_id = items[0].get("field_id")
    if not isinstance(field_id, str):
        return False
    return registry.lookup(field_id).get("content_type") != "text"


_DIRECT_BODY_IMPORT_LOCATOR = re.compile(r"^/body/(?:p\[@paraId=[0-9A-Fa-f]+\]|tbl\[\d+\])$")


def _block_source(items: list[JsonObject]) -> JsonObject:
    """Deduplicate transport blocks without changing the first item source order."""

    transport: dict[str, tuple[str, str]] = {}
    for item in items:
        for object_id, locator in _block_import_refs(item):
            current = transport.get(object_id)
            if current is not None and current[1] != locator:
                raise _invalid(
                    "placement_transport_source_conflict",
                    "One source transport object has conflicting locators.",
                )
            transport.setdefault(object_id, (object_id, locator))
    return {
        "source_object_ids": [value[0] for value in transport.values()],
        "source_locators": [value[1] for value in transport.values()],
        "source_content_items": [dict(item) for item in items],
    }


def _block_import_refs(item: JsonObject) -> list[tuple[str, str]]:
    source_object_ids = item.get("source_object_ids")
    source_locators = item.get("source_locators")
    if (
        isinstance(source_object_ids, list)
        and isinstance(source_locators, list)
        and len(source_object_ids) == len(source_locators)
        and source_object_ids
    ):
        direct_refs = [
            (str(object_id), str(locator))
            for object_id, locator in zip(source_object_ids, source_locators, strict=True)
            if isinstance(object_id, str)
            and isinstance(locator, str)
            and _DIRECT_BODY_IMPORT_LOCATOR.fullmatch(locator)
        ]
        if len(direct_refs) == len(source_object_ids):
            return direct_refs

    object_id = item.get("transport_source_object_id")
    locator = item.get("transport_source_locator")
    if not isinstance(object_id, str) or not isinstance(locator, str):
        raise _invalid(
            "placement_transport_source_invalid",
            "A block content item has no source transport reference.",
        )
    return [(object_id, locator)]


def _body_style_fallbacks(
    *,
    body_items: list[JsonObject],
    body_role_refs: dict[str, JsonObject],
    fallback_ref: JsonObject,
) -> list[str]:
    role_fields = {
        "body.equation",
        "body.figure",
        "body.figure.caption",
        "body.table.caption",
    }
    required = sorted(
        {
            str(item["field_id"])
            for item in body_items
            if isinstance(item.get("field_id"), str) and str(item["field_id"]) in role_fields
        }
    )
    fallbacks: list[str] = []
    for field_id in required:
        if field_id not in body_role_refs:
            body_role_refs[field_id] = dict(fallback_ref)
            fallbacks.append(field_id)
    return fallbacks


def _is_debug_body_role_binding(slot: JsonObject) -> bool:
    mapping_status = slot.get("mapping_status")
    if isinstance(mapping_status, str) and mapping_status.startswith("debug_"):
        return True
    value_contract = slot.get("value_contract")
    return isinstance(value_contract, dict) and "debug_role_binding" in value_contract


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="request", code=code, message=message)
