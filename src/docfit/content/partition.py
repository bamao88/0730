"""Deterministic final-generation partition of student content and template targets."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

BODY_FLOW_AGGREGATE_FIELD_ID = "body.ordered_items"
BODY_FLOW_PREFIXES = ("body.", "conclusion.")
GENERATED_FIELD_PREFIX = "generated."
PARTITION_SCHEMA_VERSION = "docfit-final-content-partition/v1"


def is_body_flow_field(field_id: str) -> bool:
    """Return whether a semantic field participates in the ordered thesis body flow."""

    return field_id.startswith(BODY_FLOW_PREFIXES)


def is_generated_field(field_id: str) -> bool:
    """Return whether a semantic field is generated from the final candidate itself."""

    return field_id.startswith(GENERATED_FIELD_PREFIX)


def compile_final_content_partition(
    *,
    student_content: Mapping[str, Any],
    contract: Mapping[str, Any],
    registry: FieldRegistrySnapshot,
) -> JsonObject:
    """Split final-generation inputs into explicit body, named, generated, and retained lanes.

    Registry field IDs are semantic labels.  This partition is the deterministic
    bridge that turns those labels plus template targets into placement strategy:
    ordered body flow is transported as one stream, while non-body fields remain
    named targets.
    """

    _validate_identity(student_content=student_content, contract=contract, registry=registry)
    raw_items = student_content.get("items")
    if not isinstance(raw_items, list) or any(not isinstance(item, Mapping) for item in raw_items):
        raise _failure(
            "final_content_partition_student_items_invalid",
            "Student Content must contain one ordered item list.",
        )

    body_items: list[JsonObject] = []
    body_structure_items: list[JsonObject] = []
    named_field_items: dict[str, list[JsonObject]] = defaultdict(list)
    generated_field_items: dict[str, list[JsonObject]] = defaultdict(list)
    review_items: list[JsonObject] = []
    previous_order: tuple[int, int] | None = None
    for raw in raw_items:
        item = dict(raw)
        order = _source_order(item)
        if previous_order is not None and order <= previous_order:
            raise _failure(
                "final_content_partition_student_order_invalid",
                "Student Content items must be in strict source order.",
            )
        previous_order = order
        field_id = item.get("field_id")
        if item.get("classification_status") != "classified" or not isinstance(field_id, str):
            review_items.append(item)
            continue
        registry.lookup(field_id)
        if is_body_flow_field(field_id):
            if _has_transport_source(item):
                body_items.append(item)
            else:
                body_structure_items.append(item)
        elif is_generated_field(field_id):
            generated_field_items[field_id].append(item)
        else:
            named_field_items[field_id].append(item)

    raw_slots = contract.get("slots")
    if not isinstance(raw_slots, list) or any(not isinstance(slot, Mapping) for slot in raw_slots):
        raise _failure(
            "final_content_partition_template_slots_invalid",
            "Fill Contract must contain one slot list.",
        )
    body_role_slots: list[JsonObject] = []
    named_field_slots: list[JsonObject] = []
    generated_field_slots: list[JsonObject] = []
    unsupported_slots: list[JsonObject] = []
    for raw_slot in raw_slots:
        slot = _slot_summary(raw_slot)
        field_id = slot.get("field_id")
        if not isinstance(field_id, str):
            unsupported_slots.append(slot)
            continue
        registry.lookup(field_id)
        if is_body_flow_field(field_id):
            body_role_slots.append(slot)
        elif is_generated_field(field_id):
            generated_field_slots.append(slot)
        else:
            named_field_slots.append(slot)

    raw_regions = contract.get("regions", [])
    if raw_regions is None:
        raw_regions = []
    if not isinstance(raw_regions, list) or any(
        not isinstance(region, Mapping) for region in raw_regions
    ):
        raise _failure(
            "final_content_partition_template_regions_invalid",
            "Fill Contract regions must be an array.",
        )
    generated_regions: list[JsonObject] = []
    retained_regions: list[JsonObject] = []
    remove_regions: list[JsonObject] = []
    for raw_region in raw_regions:
        region = _region_summary(raw_region)
        field_ids = [str(value) for value in region.get("field_ids", []) if isinstance(value, str)]
        owner = region.get("owner")
        if any(is_generated_field(field_id) for field_id in field_ids):
            generated_regions.append(region)
        elif owner == "protected":
            retained_regions.append(region)
        elif owner == "remove":
            remove_regions.append(region)

    body_anchor = body_role_slots[0] if body_role_slots else None
    partition: JsonObject = {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "source_sha256": student_content.get("source_sha256"),
        "registry": registry.identity(),
        "contract": {
            "contract_id": contract.get("contract_id"),
            "revision": contract.get("revision"),
            "status": contract.get("status"),
            "template_sha256": contract.get("template_sha256"),
            "contract_sha256": contract.get("contract_sha256"),
            "style_contract_set_digest": contract.get("style_contract_set_digest"),
        },
        "body_flow": {
            "aggregate_field_id": BODY_FLOW_AGGREGATE_FIELD_ID,
            "items": body_items,
            "structure_items": body_structure_items,
            "field_ids": _field_ids(body_items),
            "structure_field_ids": _field_ids(body_structure_items),
            "anchor_slot_ref": (
                body_anchor.get("slot_ref") if isinstance(body_anchor, dict) else None
            ),
            "role_slots": body_role_slots,
        },
        "named_fields": {field_id: items for field_id, items in sorted(named_field_items.items())},
        "generated_fields": {
            field_id: items for field_id, items in sorted(generated_field_items.items())
        },
        "review_items": review_items,
        "template": {
            "body_flow_roles": body_role_slots,
            "named_field_slots": named_field_slots,
            "generated_field_slots": generated_field_slots,
            "unsupported_slots": unsupported_slots,
            "generated_regions": generated_regions,
            "retained_regions": retained_regions,
            "remove_regions": remove_regions,
        },
        "privacy": "task_local_contains_student_content",
    }
    digest_payload = {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "source_sha256": partition["source_sha256"],
        "registry": partition["registry"],
        "contract": partition["contract"],
        "body_flow_field_ids": partition["body_flow"]["field_ids"],
        "body_flow_item_ids": [str(item.get("content_id")) for item in body_items],
        "body_structure_item_ids": [str(item.get("content_id")) for item in body_structure_items],
        "named_field_ids": sorted(named_field_items),
        "generated_field_slot_refs": [str(slot.get("slot_ref")) for slot in generated_field_slots],
        "generated_region_ids": [str(region.get("region_id")) for region in generated_regions],
        "retained_region_ids": [str(region.get("region_id")) for region in retained_regions],
    }
    partition["partition_digest"] = sha256_json(digest_payload)
    return partition


def _validate_identity(
    *,
    student_content: Mapping[str, Any],
    contract: Mapping[str, Any],
    registry: FieldRegistrySnapshot,
) -> None:
    if student_content.get("schema_version") != "docfit-student-content-model/v2":
        raise _failure(
            "final_content_partition_student_content_invalid",
            "Final generation requires Student Content Model v2.",
        )
    if student_content.get("status") != "READY":
        raise _failure(
            "final_content_partition_student_content_not_ready",
            "Final generation can only partition READY Student Content.",
        )
    if student_content.get("registry") != registry.identity():
        raise _failure(
            "final_content_partition_student_registry_stale",
            "Student Content is bound to another Registry snapshot.",
        )
    registry_ref = contract.get("field_registry_ref")
    if not isinstance(registry_ref, Mapping) or any(
        registry_ref.get(key) != registry.identity()[key]
        for key in ("registry_id", "registry_version", "sha256")
    ):
        raise _failure(
            "final_content_partition_contract_registry_stale",
            "Fill Contract is bound to another Registry snapshot.",
        )


def _source_order(item: Mapping[str, Any]) -> tuple[int, int]:
    source_order = item.get("source_order")
    if not isinstance(source_order, Mapping):
        raise _failure(
            "final_content_partition_student_order_invalid",
            "A Student Content item has no source order.",
        )
    block = source_order.get("block")
    inline = source_order.get("inline")
    if (
        not isinstance(block, int)
        or isinstance(block, bool)
        or not isinstance(inline, int)
        or isinstance(inline, bool)
    ):
        raise _failure(
            "final_content_partition_student_order_invalid",
            "A Student Content item has invalid source order.",
        )
    return block, inline


def _has_transport_source(item: Mapping[str, Any]) -> bool:
    return isinstance(item.get("transport_source_object_id"), str) and isinstance(
        item.get("transport_source_locator"),
        str,
    )


def _slot_summary(slot: Mapping[str, Any]) -> JsonObject:
    locator = slot.get("locator")
    return {
        key: slot[key]
        for key in (
            "slot_ref",
            "field_id",
            "content_type",
            "required",
            "cardinality",
            "fill_mode",
            "style_contract_ref",
            "placeholder_policy",
            "empty_policy",
            "mapping_status",
        )
        if key in slot
    } | {"locator": dict(locator) if isinstance(locator, Mapping) else locator}


def _region_summary(region: Mapping[str, Any]) -> JsonObject:
    return {
        key: region[key]
        for key in (
            "region_id",
            "owner",
            "required",
            "field_ids",
            "label",
            "placement_mode",
            "repeat_policy",
            "empty_policy",
        )
        if key in region
    }


def _field_ids(items: list[JsonObject]) -> list[str]:
    return sorted(
        {str(item["field_id"]) for item in items if isinstance(item.get("field_id"), str)}
    )


def _failure(code: str, message: str) -> ToolFailure:
    return ToolFailure(
        status="needs_input",
        origin="request",
        code=code,
        message=message,
        suggested_actions=("repair_final_generation_inputs",),
    )


__all__ = [
    "BODY_FLOW_AGGREGATE_FIELD_ID",
    "PARTITION_SCHEMA_VERSION",
    "compile_final_content_partition",
    "is_body_flow_field",
    "is_generated_field",
]
