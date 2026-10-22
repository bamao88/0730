"""Current post-unit semantic review shape and span coverage checks."""

from __future__ import annotations

from docfit.template.judgment_shape import validate_ordered_semantic_parts
from docfit.tools.runtime import JsonObject, sha256_json

_STRUCTURAL_CARRIER_OBJECT_TYPES = {"paragraph", "table", "picture", "shape"}
_TEXT_SPAN_REQUIRED_OBJECT_TYPES = {"run", "sdt", "text"}


def review_uses_current_semantic_shape(
    *,
    inventory: JsonObject,
    review: JsonObject,
    expected_vocabulary: JsonObject,
    expected_document_sha256: str | None = None,
) -> bool:
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
    block_ids, range_ids = review_reading_scope_ids(inventory)
    source_entry_ids = review_source_entry_ids(inventory)
    agent_judgments = [
        {key: value for key, value in judgment.items() if key != "resolved_spans"}
        for judgment in semantic_judgments
    ]
    feedback = validate_ordered_semantic_parts(
        agent_judgments,
        allowed_field_ids=allowed_field_ids,
        reading_block_ids=block_ids,
        reading_range_ids=range_ids,
        source_entry_ids=source_entry_ids,
    )
    if feedback.get("status") != "ok":
        return False
    if not review_has_unique_span_refs(semantic_judgments):
        return False
    source_entry_mode = bool(source_entry_ids)
    if source_entry_mode and not review_source_entry_spans_cover_inventory_once(
        inventory=inventory,
        semantic_judgments=semantic_judgments,
    ):
        return False
    if not source_entry_mode and not review_spans_cover_inventory_once(
        inventory=inventory,
        semantic_judgments=semantic_judgments,
    ):
        return False
    return all(
        review_judgment_has_current_resolved_spans(judgment)
        for judgment in semantic_judgments
    )


def review_reading_range_ids_for_block(block: JsonObject) -> tuple[str, ...]:
    ids: list[str] = []
    for key in ("range_id", "unit_range_id"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    return tuple(dict.fromkeys(ids))


def review_reading_scope_ids(inventory: JsonObject) -> tuple[list[str], list[str]]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return [], []
    block_ids: list[str] = []
    range_ids: list[str] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_id = block.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            block_ids.append(block_id.strip())
        range_ids.extend(review_reading_range_ids_for_block(block))
    return list(dict.fromkeys(block_ids)), list(dict.fromkeys(range_ids))


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
    scope = judgment.get("scope")
    if not isinstance(scope, dict):
        return None
    scoped_source_entry_id = scope.get("source_entry_id")
    if isinstance(scoped_source_entry_id, str) and scoped_source_entry_id.strip():
        return "source_entry_id", scoped_source_entry_id.strip()
    block_id = scope.get("reading_block_id")
    range_id = scope.get("reading_range_id")
    if isinstance(block_id, str) and block_id.strip():
        return "reading_block_id", block_id.strip()
    if isinstance(range_id, str) and range_id.strip():
        return "reading_range_id", range_id.strip()
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
        if span_ref != f"{scope_kind}={scope_id};part_index={part_index}":
            return False
        if span.get("scope") != {scope_kind: scope_id}:
            return False
        part = parts[part_index]
        if not isinstance(part, dict):
            return False
        part_text = part.get("text")
        if not isinstance(part_text, str) or span.get("text") != part_text.strip():
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


def review_spans_cover_inventory_once(
    *,
    inventory: JsonObject,
    semantic_judgments: list[JsonObject],
) -> bool:
    object_ids = _inventory_object_ids(inventory)
    if not object_ids or len(object_ids) != len(set(object_ids)):
        return False
    object_types = _inventory_object_types(inventory)
    objects_by_scope = _scope_objects(inventory)
    required_span_objects_by_scope = _scope_span_required_objects(inventory)
    covered_counts: dict[str, int] = {}
    for judgment in semantic_judgments:
        scope_key = review_scope_key(judgment)
        if scope_key is None:
            return False
        covered = objects_by_scope.get(scope_key)
        if not covered:
            return False
        covered_set = set(covered)
        required_span_coverage = required_span_objects_by_scope.get(scope_key)
        if not required_span_coverage:
            return False
        required_span_coverage_set = set(required_span_coverage)
        if not required_span_coverage_set.issubset(covered_set):
            return False
        if _covered_text_objects_missing_span_mapping(
            covered_set=covered_set,
            required_span_coverage_set=required_span_coverage_set,
            object_types=object_types,
        ):
            return False
        raw_spans = judgment.get("resolved_spans")
        if not isinstance(raw_spans, list):
            return False
        span_covered_object_ids: list[str] = []
        for span in raw_spans:
            if not isinstance(span, dict):
                return False
            span_object_ids = _resolved_span_object_ids(span)
            if span_object_ids is None:
                return False
            if any(object_id not in covered_set for object_id in span_object_ids):
                return False
            span_covered_object_ids.extend(span_object_ids)
        if not required_span_coverage_set.issubset(set(span_covered_object_ids)):
            return False
        for object_id in covered:
            covered_counts[object_id] = covered_counts.get(object_id, 0) + 1
    return all(covered_counts.get(object_id) == 1 for object_id in object_ids) and all(
        object_id in set(object_ids) for object_id in covered_counts
    )


def review_source_entry_spans_cover_inventory_once(
    *,
    inventory: JsonObject,
    semantic_judgments: list[JsonObject],
) -> bool:
    entries_by_id = _inventory_source_entries_by_id(inventory)
    if not entries_by_id:
        return False
    coverage = {
        source_entry_id: [0] * len(str(entry["text"]))
        for source_entry_id, entry in entries_by_id.items()
    }
    for judgment in semantic_judgments:
        scope_key = review_scope_key(judgment)
        if scope_key is None:
            return False
        scope_kind, scope_id = scope_key
        if scope_kind == "source_entry_id" and scope_id not in entries_by_id:
            return False
        raw_spans = judgment.get("resolved_spans")
        if not isinstance(raw_spans, list):
            return False
        for span in raw_spans:
            if not isinstance(span, dict):
                return False
            source_entry_spans = _resolved_span_source_entry_spans(span)
            if not source_entry_spans:
                return False
            for source_entry_span in source_entry_spans:
                source_entry_id = source_entry_span["source_entry_id"]
                if scope_kind == "source_entry_id" and source_entry_id != scope_id:
                    return False
                entry = entries_by_id.get(source_entry_id)
                if entry is None:
                    return False
                text = entry["text"]
                assert isinstance(text, str)
                start = source_entry_span["text_start"]
                end = source_entry_span["text_end"]
                if start < 0 or end <= start or end > len(text):
                    return False
                if not _source_entry_provenance_covers_span(entry, start=start, end=end):
                    return False
                for index in range(start, end):
                    if text[index].strip():
                        coverage[source_entry_id][index] += 1
    return all(
        count == 1
        for source_entry_id, text in (
            (source_entry_id, str(entry["text"]))
            for source_entry_id, entry in entries_by_id.items()
        )
        for index, character in enumerate(text)
        if character.strip()
        for count in (coverage[source_entry_id][index],)
    )


def _inventory_object_ids(inventory: JsonObject) -> list[str]:
    raw_objects = inventory.get("objects")
    if not isinstance(raw_objects, list):
        return []
    object_ids: list[str] = []
    for item in raw_objects:
        if not isinstance(item, dict):
            return []
        object_id = item.get("object_id")
        if not isinstance(object_id, str) or not object_id.strip():
            return []
        object_ids.append(object_id.strip())
    return object_ids


def _inventory_source_entries_by_id(inventory: JsonObject) -> dict[str, JsonObject]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return {}
    entries: dict[str, JsonObject] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            return {}
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
            return {}
        normalized_id = source_entry_id.strip()
        if normalized_id in entries:
            return {}
        entries[normalized_id] = entry
    return entries


def _resolved_span_source_entry_spans(span: JsonObject) -> list[JsonObject]:
    source_entry_id = span.get("source_entry_id")
    text_start = span.get("text_start")
    text_end = span.get("text_end")
    if (
        isinstance(source_entry_id, str)
        and source_entry_id.strip()
        and isinstance(text_start, int)
        and not isinstance(text_start, bool)
        and isinstance(text_end, int)
        and not isinstance(text_end, bool)
    ):
        return [
            {
                "source_entry_id": source_entry_id.strip(),
                "text_start": text_start,
                "text_end": text_end,
            }
        ]
    raw_source_entry_spans = span.get("source_entry_spans")
    if not isinstance(raw_source_entry_spans, list) or not raw_source_entry_spans:
        return []
    source_entry_spans: list[JsonObject] = []
    for item in raw_source_entry_spans:
        if not isinstance(item, dict):
            return []
        source_entry_id = item.get("source_entry_id")
        text_start = item.get("text_start")
        text_end = item.get("text_end")
        if (
            not isinstance(source_entry_id, str)
            or not source_entry_id.strip()
            or not isinstance(text_start, int)
            or isinstance(text_start, bool)
            or not isinstance(text_end, int)
            or isinstance(text_end, bool)
        ):
            return []
        source_entry_spans.append(
            {
                "source_entry_id": source_entry_id.strip(),
                "text_start": text_start,
                "text_end": text_end,
            }
        )
    return source_entry_spans


def _source_entry_provenance_covers_span(
    entry: JsonObject,
    *,
    start: int,
    end: int,
) -> bool:
    raw_provenance = entry.get("provenance")
    if not isinstance(raw_provenance, list):
        return False
    for provenance in raw_provenance:
        if not isinstance(provenance, dict):
            return False
        text_span = provenance.get("text_span")
        if (
            not isinstance(text_span, list | tuple)
            or len(text_span) != 2
            or not all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in text_span
            )
        ):
            return False
        provenance_start, provenance_end = text_span
        if provenance_start <= start and end <= provenance_end:
            return True
    return False


def _inventory_object_types(inventory: JsonObject) -> dict[str, str]:
    raw_objects = inventory.get("objects")
    if not isinstance(raw_objects, list):
        return {}
    result: dict[str, str] = {}
    for item in raw_objects:
        if not isinstance(item, dict):
            return {}
        object_id = item.get("object_id")
        if not isinstance(object_id, str) or not object_id.strip():
            return {}
        object_type = item.get("type")
        if isinstance(object_type, str) and object_type.strip():
            result[object_id.strip()] = object_type.strip()
    return result


def _covered_text_objects_missing_span_mapping(
    *,
    covered_set: set[str],
    required_span_coverage_set: set[str],
    object_types: dict[str, str],
) -> bool:
    for object_id in covered_set:
        if object_id in required_span_coverage_set:
            continue
        object_type = object_types.get(object_id)
        if object_type in _STRUCTURAL_CARRIER_OBJECT_TYPES:
            continue
        if object_type in _TEXT_SPAN_REQUIRED_OBJECT_TYPES or object_type is None:
            return True
        return True
    return False


def _scope_objects(inventory: JsonObject) -> dict[tuple[str, str], list[str]]:
    return _scope_object_map(inventory, prefer_text_spans=False)


def _scope_span_required_objects(inventory: JsonObject) -> dict[tuple[str, str], list[str]]:
    return _scope_object_map(inventory, prefer_text_spans=True)


def _scope_object_map(
    inventory: JsonObject,
    *,
    prefer_text_spans: bool,
) -> dict[tuple[str, str], list[str]]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return {}
    result: dict[tuple[str, str], list[str]] = {}
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        object_ids = _object_ids_for_block(block, prefer_text_spans=prefer_text_spans)
        block_id = block.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            result[("reading_block_id", block_id.strip())] = object_ids
        for range_id in review_reading_range_ids_for_block(block):
            scope_key = ("reading_range_id", range_id)
            result.setdefault(scope_key, []).extend(object_ids)
            result[scope_key] = list(dict.fromkeys(result[scope_key]))
    return result


def _object_ids_for_block(block: JsonObject, *, prefer_text_spans: bool) -> list[str]:
    if prefer_text_spans:
        raw_text_spans = block.get("object_text_spans")
        if not isinstance(raw_text_spans, list) or not raw_text_spans:
            return []
        object_ids: list[str] = []
        for text_span in raw_text_spans:
            if not isinstance(text_span, dict):
                return []
            object_id = text_span.get("object_id")
            if not isinstance(object_id, str) or not object_id.strip():
                return []
            object_ids.append(object_id.strip())
        return list(dict.fromkeys(object_ids))
    raw_object_ids = block.get("covered_object_ids")
    if not isinstance(raw_object_ids, list):
        return []
    return list(
        dict.fromkeys(
            item.strip() for item in raw_object_ids if isinstance(item, str) and item.strip()
        )
    )


def _resolved_span_object_ids(span: JsonObject) -> list[str] | None:
    raw_span_object_ids = span.get("covered_object_ids")
    if not isinstance(raw_span_object_ids, list) or not raw_span_object_ids:
        return None
    object_ids: list[str] = []
    for item in raw_span_object_ids:
        if not isinstance(item, str) or not item.strip():
            return None
        object_ids.append(item.strip())
    return list(dict.fromkeys(object_ids))
