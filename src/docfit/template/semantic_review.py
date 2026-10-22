"""Current post-unit semantic review shape and span coverage checks."""

from __future__ import annotations

from docfit.template.judgment_shape import validate_ordered_semantic_parts
from docfit.template.source_spans import (
    SourceExtent,
    SourceSpan,
    TextSourceExtent,
    WholeEntrySourceExtent,
    review_resolved_spans_match,
    source_span_ref,
)
from docfit.template.unit_source import validate_inventory_partition
from docfit.tools.runtime import JsonObject, sha256_json


def review_uses_current_semantic_shape(
    *,
    inventory: JsonObject,
    review: JsonObject,
    expected_vocabulary: JsonObject,
    expected_document_sha256: str | None = None,
) -> bool:
    try:
        validate_inventory_partition(inventory)
    except ValueError:
        return False
    if review.get("source_inventory_digest") != inventory["canonical_source_inventory"][
        "inventory_digest"
    ] or review.get("unit_projection_digest") != inventory.get("unit_projection_digest"):
        return False
    if expected_document_sha256 is not None and (
        inventory.get("document_sha256") != expected_document_sha256
        or review.get("document_sha256") != expected_document_sha256
    ):
        return False
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list) or not raw_judgments:
        return False
    semantic_judgments = [item for item in raw_judgments if isinstance(item, dict)]
    if len(semantic_judgments) != len(raw_judgments):
        return False
    if review.get("semantic_judgments_sha256") != sha256_json(raw_judgments):
        return False
    vocabulary = review_field_vocabulary(review)
    if vocabulary is None or vocabulary != expected_vocabulary:
        return False
    if inventory.get("field_id_vocabulary") != expected_vocabulary:
        return False
    vocabulary_digest = vocabulary["digest"]
    if review.get("field_vocabulary_digest") != vocabulary_digest:
        return False
    if inventory.get("field_vocabulary_digest") != vocabulary_digest:
        return False
    raw_allowed = vocabulary.get("allowed_field_ids")
    if not isinstance(raw_allowed, list):
        return False
    allowed_field_ids = [
        item.strip() for item in raw_allowed if isinstance(item, str) and item.strip()
    ]
    source_entry_ids = review_source_entry_ids(inventory)
    agent_judgments = [
        {key: value for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in semantic_judgments
    ]
    feedback = validate_ordered_semantic_parts(
        agent_judgments,
        allowed_field_ids=allowed_field_ids,
        source_entry_ids=source_entry_ids,
        field_vocabulary=vocabulary,
    )
    if feedback.get("status") != "ok":
        return False
    if not review_has_unique_span_refs(semantic_judgments):
        return False
    if not source_entry_ids:
        return False
    if not review_resolved_spans_match(
        inventory=inventory,
        semantic_judgments=semantic_judgments,
    ):
        return False
    flattened_spans = [
        span
        for judgment in semantic_judgments
        for span in judgment.get("resolved_spans", [])
        if isinstance(span, dict)
    ]
    if review.get("resolved_spans") != flattened_spans:
        return False
    return all(
        review_judgment_has_current_resolved_spans(judgment) for judgment in semantic_judgments
    )


def review_source_entry_ids(inventory: JsonObject) -> list[str]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return []
    source_entry_ids: list[str] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            return []
        source_entry_id = entry.get("source_entry_id")
        text = entry.get("text")
        provenance = entry.get("provenance")
        if (
            not isinstance(source_entry_id, str)
            or not source_entry_id.strip()
            or not isinstance(text, str)
            or not isinstance(provenance, list)
            or not provenance
        ):
            return []
        source_entry_ids.append(source_entry_id.strip())
    if len(source_entry_ids) != len(set(source_entry_ids)):
        return []
    return source_entry_ids


def review_field_vocabulary(review: JsonObject) -> JsonObject | None:
    vocabulary = review.get("field_id_vocabulary")
    if not isinstance(vocabulary, dict):
        return None
    raw_allowed = vocabulary.get("allowed_field_ids")
    if not isinstance(raw_allowed, list):
        return None
    digest = vocabulary.get("digest")
    if not isinstance(digest, str) or not digest.strip():
        return None
    return vocabulary


def review_scope_key(judgment: JsonObject) -> tuple[str, str] | None:
    source_entry_id = judgment.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        return "source_entry_id", source_entry_id.strip()
    return None


def review_judgment_has_current_resolved_spans(judgment: JsonObject) -> bool:
    scope_key = review_scope_key(judgment)
    if scope_key is None:
        return False
    scope_kind, scope_id = scope_key
    parts = judgment.get("parts")
    spans = judgment.get("resolved_spans")
    if not isinstance(parts, list) or not isinstance(spans, list):
        return False
    part_indices = set(range(len(parts)))
    span_indices: set[int] = set()
    for span in spans:
        if not isinstance(span, dict):
            return False
        part_index = span.get("part_index")
        if not isinstance(part_index, int) or isinstance(part_index, bool):
            return False
        if part_index < 0 or part_index >= len(parts) or part_index in span_indices:
            return False
        span_ref = span.get("span_ref")
        if not isinstance(span_ref, str) or not span_ref.strip():
            return False
        raw_extent = span.get("extent")
        extent: SourceExtent | None = None
        if isinstance(raw_extent, dict) and raw_extent.get("kind") == "whole_entry":
            extent = WholeEntrySourceExtent()
        elif isinstance(raw_extent, dict) and raw_extent.get("kind") == "text":
            start = raw_extent.get("start")
            end = raw_extent.get("end")
            if (
                isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
            ):
                extent = TextSourceExtent(start, end)
        source_snapshot_sha256 = span.get("source_snapshot_sha256")
        if (
            scope_kind != "source_entry_id"
            or extent is None
            or not isinstance(source_snapshot_sha256, str)
            or span_ref
            != source_span_ref(
                source_snapshot_sha256=source_snapshot_sha256,
                source_span=SourceSpan(
                    source_entry_id=scope_id,
                    extent=extent,
                ),
            )
        ):
            return False
        if span.get("scope") != {scope_kind: scope_id}:
            return False
        part = parts[part_index]
        if not isinstance(part, dict):
            return False
        part_text = part.get("text")
        if not isinstance(part_text, str) or span.get("text") != part_text:
            return False
        part_role = part.get("role")
        if not isinstance(part_role, str) or span.get("role") != part_role.strip():
            return False
        part_field_id = part.get("field_id")
        span_field_id = span.get("field_id")
        if isinstance(part_field_id, str) and part_field_id.strip():
            field_id = part_field_id.strip()
            if span_field_id != field_id:
                return False
            if span.get("slot_ref") != f"{span_ref};field_id={field_id}":
                return False
        elif "field_id" in span or "slot_ref" in span:
            return False
        span_indices.add(part_index)
    return span_indices == part_indices


def review_has_unique_span_refs(semantic_judgments: list[JsonObject]) -> bool:
    span_refs: set[str] = set()
    for judgment in semantic_judgments:
        spans = judgment.get("resolved_spans")
        if not isinstance(spans, list):
            return False
        for span in spans:
            if not isinstance(span, dict):
                return False
            span_ref = span.get("span_ref")
            if not isinstance(span_ref, str) or not span_ref.strip():
                return False
            normalized = span_ref.strip()
            if normalized in span_refs:
                return False
            span_refs.add(normalized)
    return True
