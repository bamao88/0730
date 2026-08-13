"""Contracts for semantic annotation and the ordered Student Content Model."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

CLASSIFICATION_STATUSES = frozenset(
    {
        "classified",
        "unregistered",
        "layout_only",
        "unresolved",
        "unsupported",
        "conflict",
    }
)
RELATION_TYPES = frozenset(
    {"caption_of", "note_of", "parallel_of", "same_fact_as"}
)
_HEADING_FIELD = re.compile(r"body\.heading\.outline([1-5])\Z")
_PHYSICAL_TO_REGISTRY_TYPES = {
    "text": frozenset({"text", "rich_text", "section"}),
    "image": frozenset({"image", "section"}),
    "table": frozenset({"table", "section"}),
    "equation": frozenset({"equation", "section"}),
    "structured_object": frozenset({"image", "table", "equation", "section"}),
}


def extraction_output_schema(
    inventory: JsonObject,
    registry: FieldRegistrySnapshot,
    *,
    annotation_content_ids: tuple[str, ...] | None = None,
    relation_content_ids: tuple[str, ...] | None = None,
) -> JsonObject:
    """Return a schema in which the Agent can annotate, but never order, items."""

    content_items = _inventory_content_items(inventory)
    all_content_ids = [str(item["source_content_id"]) for item in content_items]
    source_content_ids = list(annotation_content_ids or tuple(all_content_ids))
    relation_ids = list(relation_content_ids or tuple(source_content_ids))
    if (
        len(source_content_ids) != len(set(source_content_ids))
        or len(relation_ids) != len(set(relation_ids))
        or not set(source_content_ids) <= set(all_content_ids)
        or not set(source_content_ids) <= set(relation_ids) <= set(all_content_ids)
    ):
        raise _invalid(
            "student_content_schema_scope_invalid",
            "Annotation and relation schema scopes must reference current source items.",
        )
    if not registry.fields:
        raise _invalid(
            "student_content_registry_empty",
            "Student content extraction requires a non-empty Registry.",
        )
    annotation_schema = _annotation_schema(source_content_ids)
    relation_schema: JsonObject = {
        "type": "object",
        "properties": {
            "relation_type": {
                "type": "string",
                "enum": sorted(RELATION_TYPES),
            },
            "source_content_id": {
                "type": "string",
                "enum": relation_ids,
            },
            "target_content_id": {
                "type": "string",
                "enum": relation_ids,
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "note": {"type": "string"},
        },
        "required": [
            "relation_type",
            "source_content_id",
            "target_content_id",
            "confidence",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema_version": {"const": 3},
            "annotations": {
                "type": "array",
                "items": annotation_schema,
                "minItems": len(source_content_ids),
                "maxItems": len(source_content_ids),
            },
            "relations": {"type": "array", "items": relation_schema},
        },
        "required": [
            "schema_version",
            "annotations",
            "relations",
        ],
        "additionalProperties": False,
    }


def registry_semantic_lexicon(registry: FieldRegistrySnapshot) -> list[JsonObject]:
    """Expose only the Registry's read-only semantic dictionary to extraction."""

    return [
        {
            key: field[key]
            for key in ("field_id", "label", "meaning", "content_type")
            if key in field
        }
        for field in registry.fields
    ]


def _annotation_schema(source_content_ids: list[str]) -> JsonObject:
    return {
        "type": "object",
        "properties": {
            "source_content_id": {
                "type": "string",
                "enum": source_content_ids,
            },
                "classification_status": {
                    "type": "string",
                    "enum": sorted(CLASSIFICATION_STATUSES),
                },
                "field_id": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "note": {"type": "string"},
        },
        "required": [
            "source_content_id",
            "classification_status",
            "field_id",
            "confidence",
        ],
        "additionalProperties": False,
    }


def validate_extraction(
    payload: Any,
    *,
    inventory: JsonObject,
    registry: FieldRegistrySnapshot,
) -> JsonObject:
    """Validate annotations and assemble the sole ordered Student Content Model."""

    if not isinstance(payload, dict) or payload.get("schema_version") != 3:
        raise _invalid(
            "student_content_annotation_shape",
            "The Agent semantic annotation has an invalid shape.",
        )
    content_items = _inventory_content_items(inventory)
    source_items = {
        str(item["source_content_id"]): item
        for item in content_items
    }
    annotations = _annotation_map(payload.get("annotations"), set(source_items))

    validated_annotations = {
        source_content_id: _validate_annotation(
            annotations[source_content_id],
            source_item=source_item,
            registry=registry,
        )
        for source_content_id, source_item in source_items.items()
    }
    _normalize_numbered_heading_consistency(
        validated_annotations,
        source_items=source_items,
    )

    normalized_items: list[JsonObject] = []
    source_to_content: dict[str, str] = {}
    for source_item in content_items:
        source_content_id = str(source_item["source_content_id"])
        annotation = validated_annotations[source_content_id]
        content_id = _content_id(inventory, source_content_id)
        source_to_content[source_content_id] = content_id
        field_id = annotation["field_id"]
        registry_type = None
        if isinstance(field_id, str):
            registry_type = registry.lookup(field_id).get("content_type")
        normalized_items.append(
            {
                "content_id": content_id,
                "source_content_id": source_content_id,
                "field_id": field_id,
                "classification_status": annotation["classification_status"],
                "content_type": registry_type or source_item.get("physical_type"),
                "physical_type": source_item.get("physical_type"),
                "value": _content_value(source_item),
                "source_order": dict(source_item["source_order"]),
                "source_object_ids": list(source_item["source_object_ids"]),
                "source_locators": list(source_item["source_locators"]),
                "transport_source_object_id": source_item[
                    "transport_source_object_id"
                ],
                "transport_source_locator": source_item["transport_source_locator"],
                "content_ref": dict(source_item["content_ref"]),
                "parent_content_id": None,
                "confidence": annotation["confidence"],
                "note": annotation["note"],
            }
        )

    _bind_body_hierarchy(normalized_items)
    relations = _validate_relations(payload.get("relations"), source_to_content)
    relations = _materialize_caption_relations(normalized_items, relations)
    coverage = _source_coverage(inventory, content_items, normalized_items)
    status = _model_status(normalized_items, coverage)
    return {
        "schema_version": "docfit-student-content-model/v2",
        "status": status,
        "source_sha256": inventory.get("source_sha256"),
        "registry": registry.identity(),
        "items": normalized_items,
        "field_results": _field_results(normalized_items),
        "relations": relations,
        "source_coverage": coverage,
        "summary": str(payload.get("summary", "")),
        "uncertainties": [str(value) for value in payload.get("uncertainties", [])],
        "privacy": "task_local_contains_student_content",
    }


def _inventory_content_items(inventory: JsonObject) -> list[JsonObject]:
    content_items = inventory.get("content_items")
    if not isinstance(content_items, list) or any(
        not isinstance(item, dict) for item in content_items
    ):
        raise _invalid(
            "student_source_inventory_invalid",
            "The source inventory has no valid ordered content items.",
        )
    normalized = [dict(item) for item in content_items]
    ids = [item.get("source_content_id") for item in normalized]
    if any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)):
        raise _invalid(
            "student_source_inventory_invalid",
            "Source content item IDs must be unique strings.",
        )
    orders = [_source_order(item) for item in normalized]
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        raise _invalid(
            "student_source_order_invalid",
            "Source content items must have one immutable total order.",
        )
    return normalized


def _annotation_map(raw_annotations: Any, expected_ids: set[str]) -> dict[str, JsonObject]:
    if not isinstance(raw_annotations, list) or any(
        not isinstance(item, dict) for item in raw_annotations
    ):
        raise _invalid(
            "student_content_annotation_keys_invalid",
            "Semantic annotations must be an array of source-bound objects.",
        )
    annotations: dict[str, JsonObject] = {}
    for raw in raw_annotations:
        source_content_id = raw.get("source_content_id")
        if not isinstance(source_content_id, str) or source_content_id in annotations:
            raise _invalid(
                "student_content_annotation_keys_invalid",
                "Every source content item must be annotated exactly once.",
            )
        annotations[source_content_id] = dict(raw)
    if set(annotations) != expected_ids:
        raise _invalid(
            "student_content_annotation_keys_invalid",
            "Every source content item must be annotated exactly once.",
        )
    return annotations


def _validate_annotation(
    raw: Any,
    *,
    source_item: JsonObject,
    registry: FieldRegistrySnapshot,
) -> JsonObject:
    if not isinstance(raw, dict):
        raise _invalid(
            "student_content_annotation_invalid",
            "Each semantic annotation must be an object.",
        )
    status = raw.get("classification_status")
    field_id = raw.get("field_id")
    if status not in CLASSIFICATION_STATUSES:
        raise _invalid(
            "student_content_classification_status_invalid",
            "A semantic annotation has an invalid classification status.",
        )
    if status == "classified":
        if not isinstance(field_id, str):
            raise _invalid(
                "student_content_field_id_missing",
                "A classified content item must bind to one Registry field_id.",
            )
        field = registry.lookup(field_id)
        _validate_content_type(source_item, field)
    elif field_id is not None:
        field_id = None
        raw = dict(raw)
        raw["note"] = (
            f"{raw.get('note', '')} Ignored field_id because classification_status "
            f"is {status}."
        ).strip()
    return {
        "classification_status": status,
        "field_id": field_id,
        "confidence": _confidence(raw.get("confidence")),
        "note": str(raw.get("note", "")),
    }


def _validate_content_type(source_item: JsonObject, field: JsonObject) -> None:
    physical_type = str(source_item.get("physical_type", ""))
    registry_type = str(field.get("content_type", ""))
    allowed = _PHYSICAL_TO_REGISTRY_TYPES.get(physical_type, frozenset())
    if registry_type not in allowed:
        raise _invalid(
            "student_content_type_mismatch",
            "A content item cannot bind to an incompatible Registry content type.",
        )


def _normalize_numbered_heading_consistency(
    annotations: dict[str, JsonObject],
    *,
    source_items: dict[str, JsonObject],
) -> None:
    """Correct isolated heading-level outliers without changing source order.

    The Agent still owns semantic recognition.  This deterministic pass only
    enforces a strong document-local consensus for one numbering shape when
    every member was already recognized as a heading.  It deliberately does
    nothing when the same shape is used for mixed semantic roles.
    """

    grouped: defaultdict[str, list[JsonObject]] = defaultdict(list)
    for source_content_id, source_item in source_items.items():
        source_facts = source_item.get("source_facts")
        if not isinstance(source_facts, dict):
            continue
        numbering_shape = source_facts.get("numbering_shape")
        if not isinstance(numbering_shape, str) or numbering_shape in {
            "none",
            "not_text",
        }:
            continue
        grouped[numbering_shape].append(annotations[source_content_id])

    for numbering_shape, group in grouped.items():
        if len(group) < 3:
            continue
        field_ids = [annotation.get("field_id") for annotation in group]
        if any(
            annotation.get("classification_status") != "classified"
            or not isinstance(field_id, str)
            or _HEADING_FIELD.fullmatch(field_id) is None
            for annotation, field_id in zip(group, field_ids, strict=True)
        ):
            continue
        counts = Counter(str(field_id) for field_id in field_ids)
        consensus_field_id, consensus_count = counts.most_common(1)[0]
        if consensus_count / len(group) < 0.8:
            continue
        for annotation in group:
            if annotation["field_id"] == consensus_field_id:
                continue
            annotation["field_id"] = consensus_field_id
            annotation["note"] = (
                f"{annotation['note']} Deterministic document-local consistency "
                f"normalization for numbering shape {numbering_shape}."
            ).strip()


def _content_value(source_item: JsonObject) -> str | None:
    if source_item.get("physical_type") != "text":
        return None
    observed = str(source_item.get("observed_text", ""))
    return observed if observed else None


def _content_id(inventory: JsonObject, source_content_id: str) -> str:
    identity = {
        "source_sha256": inventory.get("source_sha256"),
        "source_content_id": source_content_id,
    }
    return f"student-content-{sha256_json(identity)[:24]}"


def _bind_body_hierarchy(items: list[JsonObject]) -> None:
    heading_stack: dict[int, str] = {}
    for item in items:
        field_id = item.get("field_id")
        if not isinstance(field_id, str) or not field_id.startswith("body."):
            continue
        heading = _HEADING_FIELD.fullmatch(field_id)
        if heading is not None:
            level = int(heading.group(1))
            parent = next(
                (
                    heading_stack[index]
                    for index in range(level - 1, 0, -1)
                    if index in heading_stack
                ),
                None,
            )
            item["parent_content_id"] = parent
            heading_stack = {
                index: content_id
                for index, content_id in heading_stack.items()
                if index < level
            }
            heading_stack[level] = str(item["content_id"])
            continue
        item["parent_content_id"] = next(
            (
                heading_stack[index]
                for index in range(5, 0, -1)
                if index in heading_stack
            ),
            None,
        )


def _validate_relations(
    raw_relations: Any,
    source_to_content: dict[str, str],
) -> list[JsonObject]:
    if not isinstance(raw_relations, list):
        raise _invalid(
            "student_content_relations_invalid",
            "Semantic relations must be an array.",
        )
    normalized: list[JsonObject] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_relations:
        if not isinstance(raw, dict):
            raise _invalid(
                "student_content_relation_invalid",
                "Each semantic relation must be an object.",
            )
        relation_type = raw.get("relation_type")
        source = raw.get("source_content_id")
        target = raw.get("target_content_id")
        if (
            relation_type not in RELATION_TYPES
            or source not in source_to_content
            or target not in source_to_content
            or source == target
        ):
            raise _invalid(
                "student_content_relation_invalid",
                "A semantic relation is invalid or cites a stale content item.",
            )
        key = (str(relation_type), str(source), str(target))
        if key in seen:
            raise _invalid(
                "student_content_relation_duplicate",
                "Semantic relations must be unique.",
            )
        seen.add(key)
        normalized.append(
            {
                "relation_type": relation_type,
                "source_content_id": source_to_content[str(source)],
                "target_content_id": source_to_content[str(target)],
                "confidence": _confidence(raw.get("confidence")),
                "note": str(raw.get("note", "")),
            }
        )
    return normalized


def _materialize_caption_relations(
    items: list[JsonObject],
    relations: list[JsonObject],
) -> list[JsonObject]:
    """Bind nearby captions to their typed object using immutable source order."""

    normalized: list[JsonObject] = [
        relation
        for relation in relations
        if relation.get("relation_type") != "caption_of"
    ]
    agent_caption_relations = [
        relation
        for relation in relations
        if relation.get("relation_type") == "caption_of"
    ]
    matched_caption_ids: set[str] = set()
    for index, item in enumerate(items):
        field_id = item.get("field_id")
        if not isinstance(field_id, str) or not field_id.endswith(".caption"):
            continue
        target_field_id = field_id.removesuffix(".caption")
        candidates = [
            (candidate_index, candidate)
            for candidate_index, candidate in enumerate(items)
            if candidate.get("field_id") == target_field_id
            and abs(
                int(candidate["source_order"]["block"])
                - int(item["source_order"]["block"])
            )
            <= 2
        ]
        if not candidates:
            continue
        _, target = min(
            candidates,
            key=lambda pair: (
                abs(
                    int(pair[1]["source_order"]["block"])
                    - int(item["source_order"]["block"])
                ),
                0 if pair[0] < index else 1,
                abs(pair[0] - index),
            ),
        )
        caption_id = str(item["content_id"])
        matched_caption_ids.add(caption_id)
        normalized.append(
            {
                "relation_type": "caption_of",
                "source_content_id": caption_id,
                "target_content_id": str(target["content_id"]),
                "confidence": 1.0,
                "note": "Deterministic typed-caption adjacency binding.",
            }
        )
    normalized.extend(
        relation
        for relation in agent_caption_relations
        if relation.get("source_content_id") not in matched_caption_ids
    )
    return normalized


def _field_results(items: list[JsonObject]) -> list[JsonObject]:
    grouped: defaultdict[str, list[JsonObject]] = defaultdict(list)
    for item in items:
        field_id = item.get("field_id")
        if item.get("classification_status") == "classified" and isinstance(field_id, str):
            grouped[field_id].append(item)
    return [
        {
            "field_id": field_id,
            "status": "extracted",
            "item_count": len(grouped[field_id]),
            "content_ids": [str(item["content_id"]) for item in grouped[field_id]],
        }
        for field_id in sorted(grouped)
    ]


def _source_coverage(
    inventory: JsonObject,
    source_items: list[JsonObject],
    model_items: list[JsonObject],
) -> JsonObject:
    objects = inventory.get("objects")
    if not isinstance(objects, list):
        raise _invalid(
            "student_source_inventory_invalid",
            "The source inventory object graph is invalid.",
        )
    object_ids = {
        str(item["source_object_ref"]["object_id"])
        for item in objects
        if isinstance(item, dict)
        and isinstance(item.get("source_object_ref"), dict)
        and isinstance(item["source_object_ref"].get("object_id"), str)
    }
    mapped = {
        str(object_id)
        for item in source_items
        for object_id in item.get("source_object_ids", [])
    }
    dependencies = {
        str(item.get("transport_source_object_id"))
        for item in source_items
        if str(item.get("transport_source_object_id")) not in mapped
    }
    layout_only: set[str] = set()
    unsupported: set[str] = set()
    object_by_id = {
        str(item["source_object_ref"]["object_id"]): item
        for item in objects
        if isinstance(item, dict)
        and isinstance(item.get("source_object_ref"), dict)
        and isinstance(item["source_object_ref"].get("object_id"), str)
    }
    for object_id in object_ids - mapped - dependencies:
        item = object_by_id[object_id]
        if item.get("kind") == "paragraph" and not str(item.get("text", "")).strip():
            layout_only.add(object_id)
        elif any(
            str(item.get("source_locator", "")).startswith(
                f"{source_item.get('transport_source_locator', '')}/"
            )
            for source_item in source_items
        ):
            dependencies.add(object_id)
        else:
            unsupported.add(object_id)
    accounted = mapped | dependencies | layout_only | unsupported
    classifications = Counter(
        str(item.get("classification_status")) for item in model_items
    )
    return {
        "source_object_count": len(object_ids),
        "mapped_source_object_ids": sorted(mapped),
        "covered_dependency_object_ids": sorted(dependencies),
        "layout_only_source_object_ids": sorted(layout_only),
        "unsupported_source_object_ids": sorted(unsupported),
        "content_item_classifications": dict(sorted(classifications.items())),
        "all_source_objects_accounted_for": accounted == object_ids,
    }


def _model_status(items: list[JsonObject], coverage: JsonObject) -> str:
    statuses = {str(item.get("classification_status")) for item in items}
    if "unsupported" in statuses or coverage.get("unsupported_source_object_ids"):
        return "UNSUPPORTED"
    if statuses - {"classified", "layout_only"}:
        return "NEEDS_REVIEW"
    if coverage.get("all_source_objects_accounted_for") is not True:
        return "NEEDS_REVIEW"
    return "READY"


def _source_order(item: JsonObject) -> tuple[int, int]:
    source_order = item.get("source_order")
    if not isinstance(source_order, dict):
        raise _invalid(
            "student_source_order_invalid",
            "Each content item must preserve its source order.",
        )
    block = source_order.get("block")
    inline = source_order.get("inline")
    if (
        not isinstance(block, int)
        or isinstance(block, bool)
        or not isinstance(inline, int)
        or isinstance(inline, bool)
    ):
        raise _invalid(
            "student_source_order_invalid",
            "Each content item must preserve its source order.",
        )
    return block, inline


def _confidence(value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 <= value <= 1
    ):
        raise _invalid(
            "student_content_confidence_invalid",
            "Semantic confidence must be between zero and one.",
        )
    return float(value)


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="agent", code=code, message=message)
