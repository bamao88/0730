"""Schema and deterministic validation for Agent-produced student semantics."""

from __future__ import annotations

from typing import Any

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.tools.runtime import JsonObject, ToolFailure

FIELD_STATUSES = frozenset({"extracted", "missing", "conflict"})
SEGMENT_STATUSES = frozenset({"extracted", "missing", "conflict"})
SEGMENT_FIELD_IDS = frozenset(
    {
        "body.chapters",
        "references.entries",
        "acknowledgement.body",
        "appendix.body",
    }
)


def extraction_output_schema(expected_field_ids: tuple[str, ...]) -> JsonObject:
    """Return a composition-free schema compatible with configured Agent backends."""

    return {
        "type": "object",
        "properties": {
            "schema_version": {"const": 1},
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string", "enum": list(expected_field_ids)},
                        "status": {
                            "type": "string",
                            "enum": sorted(FIELD_STATUSES),
                        },
                        "value": {"type": ["string", "null"]},
                        "source_object_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True,
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "note": {"type": "string"},
                    },
                    "required": [
                        "field_id",
                        "status",
                        "value",
                        "source_object_ids",
                        "confidence",
                        "note",
                    ],
                    "additionalProperties": False,
                },
            },
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string", "enum": sorted(SEGMENT_FIELD_IDS)},
                        "status": {
                            "type": "string",
                            "enum": sorted(SEGMENT_STATUSES),
                        },
                        "start_object_id": {"type": ["string", "null"]},
                        "end_object_id": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "note": {"type": "string"},
                    },
                    "required": [
                        "field_id",
                        "status",
                        "start_object_id",
                        "end_object_id",
                        "confidence",
                        "note",
                    ],
                    "additionalProperties": False,
                },
            },
            "unmapped_object_ids": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "summary": {"type": "string"},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "schema_version",
            "fields",
            "segments",
            "unmapped_object_ids",
            "summary",
            "uncertainties",
        ],
        "additionalProperties": False,
    }


def validate_extraction(
    payload: Any,
    *,
    inventory: JsonObject,
    registry: FieldRegistrySnapshot,
    expected_field_ids: tuple[str, ...],
) -> JsonObject:
    """Bind semantic output to inventory evidence and expand segment ranges."""

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise _invalid("student_extraction_shape", "The Agent extraction has an invalid shape.")
    objects = inventory.get("objects")
    if not isinstance(objects, list):
        raise _invalid("student_inventory_shape", "The student inventory has an invalid shape.")
    by_id = {
        value["source_object_ref"]["object_id"]: value
        for value in objects
        if isinstance(value, dict)
        and isinstance(value.get("source_object_ref"), dict)
        and isinstance(value["source_object_ref"].get("object_id"), str)
    }
    ordered_transferable = [
        value for value in objects if isinstance(value, dict) and value.get("transferable") is True
    ]
    ordered_transferable.sort(key=_inventory_body_sequence)
    positions = {
        value["source_object_ref"]["object_id"]: index
        for index, value in enumerate(ordered_transferable)
    }
    expected = set(expected_field_ids)
    fields = _validate_fields(payload.get("fields"), by_id, registry, expected)
    segments = _validate_segments(
        payload.get("segments"), ordered_transferable, positions, registry
    )
    unmapped = payload.get("unmapped_object_ids")
    if not isinstance(unmapped, list) or any(value not in by_id for value in unmapped):
        raise _invalid(
            "student_extraction_unmapped_invalid",
            "Unmapped object IDs must reference the current student snapshot.",
        )
    mapped_ids = {
        source_id
        for item in [*fields, *segments]
        for source_id in item.get("source_object_ids", [])
    }
    mapped_locators = {str(by_id[source_id].get("source_locator", "")) for source_id in mapped_ids}
    dependency_ids = {
        object_id
        for object_id, item in by_id.items()
        if item.get("transferable") is not True
        and any(
            str(item.get("source_locator", "")).startswith(f"{locator}/")
            for locator in mapped_locators
            if locator
        )
    }
    normalized_unmapped = list(
        dict.fromkeys(
            [
                *[value for value in unmapped if value not in mapped_ids | dependency_ids],
                *[
                    object_id
                    for object_id in by_id
                    if object_id not in mapped_ids | dependency_ids | set(unmapped)
                ],
            ]
        )
    )
    return {
        "schema_version": "docfit-student-content-actual/v1",
        "source_sha256": inventory.get("source_sha256"),
        "registry": registry.identity(),
        "fields": fields,
        "segments": segments,
        "covered_dependency_object_ids": sorted(dependency_ids),
        "unmapped_object_ids": normalized_unmapped,
        "coverage": {
            "object_count": len(by_id),
            "mapped_object_count": len(mapped_ids),
            "covered_dependency_object_count": len(dependency_ids),
            "unmapped_object_count": len(normalized_unmapped),
            "all_objects_accounted_for": (
                len(mapped_ids | dependency_ids | set(normalized_unmapped)) == len(by_id)
            ),
        },
        "summary": str(payload.get("summary", "")),
        "uncertainties": [str(value) for value in payload.get("uncertainties", [])],
        "privacy": "task_local_contains_student_content",
    }


def _validate_fields(
    raw_fields: Any,
    by_id: dict[str, JsonObject],
    registry: FieldRegistrySnapshot,
    expected: set[str],
) -> list[JsonObject]:
    if not isinstance(raw_fields, list):
        raise _invalid("student_extraction_fields_invalid", "Extraction fields must be a list.")
    normalized: list[JsonObject] = []
    seen: set[str] = set()
    for raw in raw_fields:
        if not isinstance(raw, dict):
            raise _invalid(
                "student_extraction_field_invalid", "Each extraction field must be an object."
            )
        field_id = raw.get("field_id")
        status = raw.get("status")
        if not isinstance(field_id, str) or field_id not in expected or field_id in seen:
            raise _invalid(
                "student_extraction_field_unknown", "Extraction fields must be expected and unique."
            )
        registry.lookup(field_id)
        seen.add(field_id)
        if status not in FIELD_STATUSES:
            raise _invalid(
                "student_extraction_status_invalid", "Extraction field status is invalid."
            )
        source_ids = raw.get("source_object_ids")
        if not isinstance(source_ids, list) or any(value not in by_id for value in source_ids):
            raise _invalid(
                "student_extraction_source_invalid", "A field cites a stale source object."
            )
        value = raw.get("value")
        if status == "extracted":
            if not isinstance(value, str) or not value.strip() or not source_ids:
                raise _invalid(
                    "student_extraction_value_missing",
                    "An extracted field needs a value and source evidence.",
                )
            evidence = " ".join(str(by_id[source_id].get("text", "")) for source_id in source_ids)
            if _normalize_text(value) not in _normalize_text(evidence):
                raise _invalid(
                    "student_extraction_value_untraceable",
                    "An extracted field value is not present in its cited source evidence.",
                )
        elif value is not None:
            raise _invalid(
                "student_extraction_nonvalue_invalid",
                "Missing or conflict fields cannot carry a fill value.",
            )
        normalized.append(
            {
                "field_id": field_id,
                "status": status,
                "value": value,
                "source_object_ids": list(dict.fromkeys(source_ids)),
                "confidence": _confidence(raw.get("confidence")),
                "note": str(raw.get("note", "")),
            }
        )
    for field_id in sorted(expected - seen):
        normalized.append(
            {
                "field_id": field_id,
                "status": "missing",
                "value": None,
                "source_object_ids": [],
                "confidence": 1.0,
                "note": "Agent output omitted the expected field; normalized to missing.",
            }
        )
    return normalized


def _validate_segments(
    raw_segments: Any,
    ordered: list[JsonObject],
    positions: dict[str, int],
    registry: FieldRegistrySnapshot,
) -> list[JsonObject]:
    if not isinstance(raw_segments, list):
        raise _invalid("student_extraction_segments_invalid", "Extraction segments must be a list.")
    normalized: list[JsonObject] = []
    seen: set[str] = set()
    occupied: set[int] = set()
    for raw in raw_segments:
        if not isinstance(raw, dict):
            raise _invalid("student_extraction_segment_invalid", "Each segment must be an object.")
        field_id = raw.get("field_id")
        status = raw.get("status")
        if field_id not in SEGMENT_FIELD_IDS or field_id in seen or status not in SEGMENT_STATUSES:
            raise _invalid(
                "student_extraction_segment_unknown",
                "Segments must be registered, supported, and unique.",
            )
        assert isinstance(field_id, str)
        registry.lookup(field_id)
        seen.add(field_id)
        start = raw.get("start_object_id")
        end = raw.get("end_object_id")
        source_ids: list[str] = []
        source_locators: list[str] = []
        if status == "extracted":
            if start not in positions or end not in positions or positions[start] > positions[end]:
                raise _invalid(
                    "student_extraction_segment_range", "A segment range is stale or reversed."
                )
            indexes = set(range(positions[start], positions[end] + 1))
            if occupied & indexes:
                raise _invalid(
                    "student_extraction_segment_overlap",
                    "Extracted semantic segments cannot overlap.",
                )
            occupied |= indexes
            selected = ordered[positions[start] : positions[end] + 1]
            source_ids = [str(value["source_object_ref"]["object_id"]) for value in selected]
            source_locators = [str(value["source_locator"]) for value in selected]
        elif start is not None or end is not None:
            raise _invalid(
                "student_extraction_segment_nonvalue",
                "Missing/conflict segments cannot carry a range.",
            )
        normalized.append(
            {
                "field_id": field_id,
                "status": status,
                "start_object_id": start,
                "end_object_id": end,
                "source_object_ids": source_ids,
                "source_locators": source_locators,
                "confidence": _confidence(raw.get("confidence")),
                "note": str(raw.get("note", "")),
            }
        )
    for field_id in sorted(SEGMENT_FIELD_IDS - seen):
        normalized.append(
            {
                "field_id": field_id,
                "status": "missing",
                "start_object_id": None,
                "end_object_id": None,
                "source_object_ids": [],
                "source_locators": [],
                "confidence": 1.0,
                "note": "Agent output omitted the segment; normalized to missing.",
            }
        )
    return normalized


def _confidence(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise _invalid(
            "student_extraction_confidence", "Extraction confidence must be between zero and one."
        )
    return float(value)


def _inventory_body_sequence(value: JsonObject) -> int:
    body_sequence = value.get("body_sequence")
    if isinstance(body_sequence, int) and not isinstance(body_sequence, bool):
        return body_sequence
    sequence = value.get("sequence")
    return sequence if isinstance(sequence, int) and not isinstance(sequence, bool) else 0


def _normalize_text(value: str) -> str:
    return "".join(value.split()).casefold()


def _invalid(code: str, message: str) -> ToolFailure:
    return ToolFailure(status="needs_input", origin="agent", code=code, message=message)
