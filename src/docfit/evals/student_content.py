"""Deterministic Actual--Gold evaluation for Student Content Extraction.

Gold remains an oracle-only input.  Reports contain hashes, counts, Registry field
IDs, source object IDs, and run metadata, but never student text or extracted values.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docfit.tools.runtime import JsonObject, atomic_write_json, sha256_file

ACTUAL_FILENAME = "student-content.json"
INVENTORY_FILENAME = "work/student-inventory.json"
EVIDENCE_FILENAME = "work/agent-evidence.json"
GOLD_FILENAME = "student-content.gold.json"
JSON_REPORT_FILENAME = "student-content-eval-report.json"
MARKDOWN_REPORT_FILENAME = "student-content-eval-report.md"

BindingKey = tuple[str, ...]
SemanticKey = tuple[BindingKey, str]
_TOP_LEVEL_HOST = re.compile(r"^(/body/p\[@paraId=[^]]+\]|/body/tbl\[\d+\])(?:/|$)")


class StudentContentEvalInputError(ValueError):
    """A stable, privacy-safe input error raised before comparison."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StudentContentEvalResult:
    """Published report paths and the in-memory evaluation result."""

    report: JsonObject
    json_report: Path
    markdown_report: Path

    @property
    def passed(self) -> bool:
        return self.report.get("status") == "PASS"


def _object_list(value: Any, *, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise StudentContentEvalInputError(
            "invalid_eval_artifact",
            f"{label} must be an array of JSON objects.",
        )
    return [dict(item) for item in value]


def _load_object(path: Path, *, label: str) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StudentContentEvalInputError(
            "eval_artifact_missing",
            f"{label} is missing from the requested evaluation input.",
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise StudentContentEvalInputError(
            "eval_artifact_unreadable",
            f"{label} is not a readable JSON object.",
        ) from error
    if not isinstance(value, dict):
        raise StudentContentEvalInputError(
            "invalid_eval_artifact",
            f"{label} must contain one JSON object.",
        )
    return value


def _source_order(item: JsonObject) -> tuple[int, int] | None:
    value = item.get("source_order")
    if not isinstance(value, dict):
        return None
    block = value.get("block")
    inline = value.get("inline")
    if (
        not isinstance(block, int)
        or isinstance(block, bool)
        or not isinstance(inline, int)
        or isinstance(inline, bool)
    ):
        return None
    return block, inline


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return list(value)


def _actual_source_ids(item: JsonObject) -> list[str]:
    return _string_list(item.get("source_object_ids"))


def _gold_source_ids(item: JsonObject) -> list[str]:
    refs = item.get("source_object_refs")
    if not isinstance(refs, list):
        return []
    return [
        str(ref["object_id"])
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("object_id"), str)
    ]


def _semantic_key(item: JsonObject, source_ids: Any) -> SemanticKey:
    field_id = item.get("field_id")
    semantic_label = (
        str(field_id)
        if isinstance(field_id, str)
        else f"<{item.get('classification_status', 'unclassified')}>"
    )
    return tuple(source_ids(item)), semantic_label


def _semantic_payload(key: SemanticKey) -> JsonObject:
    source_ids, field_id = key
    return {"source_object_ids": list(source_ids), "field_id": field_id}


def _validate_actual(actual: JsonObject) -> list[JsonObject]:
    if actual.get("schema_version") != "docfit-student-content-model/v2":
        raise StudentContentEvalInputError(
            "unsupported_actual_schema",
            "Actual must use docfit-student-content-model/v2.",
        )
    items = _object_list(actual.get("items"), label="Actual items")
    orders = [_source_order(item) for item in items]
    if (
        any(value is None for value in orders)
        or orders != sorted(orders)  # type: ignore[type-var]
        or len(orders) != len(set(orders))
    ):
        raise StudentContentEvalInputError(
            "invalid_actual_order",
            "Actual items must preserve one unique ascending source order.",
        )
    return items


def _validate_gold(gold: JsonObject) -> list[JsonObject]:
    if gold.get("schema_version") != "docfit-student-content-extraction-gold/v2":
        raise StudentContentEvalInputError(
            "unsupported_gold_schema",
            "Gold must use docfit-student-content-extraction-gold/v2.",
        )
    if gold.get("status") != "gold":
        raise StudentContentEvalInputError(
            "gold_not_accepted",
            "Only an accepted Extraction Gold may be used as the oracle.",
        )
    ordering = gold.get("ordering_contract")
    if (
        not isinstance(ordering, dict)
        or ordering.get("version") != "docfit-source-order/v1"
        or ordering.get("truth_source") != "items"
    ):
        raise StudentContentEvalInputError(
            "invalid_gold_order_contract",
            "Gold must bind docfit-source-order/v1 with items as the truth source.",
        )
    items = _object_list(gold.get("items"), label="Gold items")
    orders = [_source_order(item) for item in items]
    if (
        any(value is None for value in orders)
        or orders != sorted(orders)  # type: ignore[type-var]
        or len(orders) != len(set(orders))
    ):
        raise StudentContentEvalInputError(
            "invalid_gold_order",
            "Gold items must have one unique ascending source order.",
        )
    if not isinstance(gold.get("gold_id"), str) or not isinstance(
        gold.get("student_document_sha256"), str
    ):
        raise StudentContentEvalInputError(
            "invalid_gold_identity",
            "Gold must contain a stable gold_id and student document hash.",
        )
    registry_ref = gold.get("field_registry_ref")
    if not isinstance(registry_ref, dict) or any(
        not isinstance(registry_ref.get(key), str)
        for key in ("registry_id", "registry_version", "sha256")
    ):
        raise StudentContentEvalInputError(
            "invalid_gold_registry_binding",
            "Gold must bind one complete Content Field Registry identity.",
        )
    field_results = _object_list(gold.get("field_results"), label="Gold field_results")
    result_field_ids = [item.get("field_id") for item in field_results]
    if (
        not result_field_ids
        or any(not isinstance(field_id, str) for field_id in result_field_ids)
        or len(result_field_ids) != len(set(result_field_ids))
        or any(
            item.get("classification_status") != "registered"
            or item.get("field_id") not in set(result_field_ids)
            for item in items
        )
    ):
        raise StudentContentEvalInputError(
            "invalid_gold_registry_projection",
            "Gold items and field_results must form one registered Registry projection.",
        )
    coverage = gold.get("coverage")
    if (
        not isinstance(coverage, dict)
        or coverage.get("all_objects_accounted_for") is not True
        or coverage.get("unresolved_count") != 0
        or gold.get("unregistered_items") != []
    ):
        raise StudentContentEvalInputError(
            "incomplete_gold_coverage",
            "Accepted Gold must have complete coverage with no unresolved or unregistered items.",
        )
    return items


def _index_actual_by_source(
    items: list[JsonObject],
) -> dict[str, list[JsonObject]]:
    by_source: defaultdict[str, list[JsonObject]] = defaultdict(list)
    for item in items:
        for source_id in _actual_source_ids(item):
            by_source[source_id].append(item)
    return dict(by_source)


def _index_by_semantic_key(
    items: list[JsonObject],
    source_ids: Any,
) -> tuple[dict[SemanticKey, JsonObject], list[SemanticKey], list[JsonObject]]:
    indexed: dict[SemanticKey, JsonObject] = {}
    duplicates: set[SemanticKey] = set()
    synthetic: list[JsonObject] = []
    for item in items:
        key = _semantic_key(item, source_ids)
        if not key[0]:
            synthetic.append(item)
            continue
        if key in indexed:
            duplicates.add(key)
        else:
            indexed[key] = item
    return indexed, sorted(duplicates), synthetic


def _actual_for_field(
    actual_by_source: dict[str, list[JsonObject]],
    source_id: str,
    field_id: Any,
) -> JsonObject | None:
    return next(
        (
            item
            for item in actual_by_source.get(source_id, [])
            if item.get("classification_status") == "classified"
            and item.get("field_id") == field_id
        ),
        None,
    )


def _gold_coverage(gold: JsonObject) -> dict[str, JsonObject]:
    coverage = gold.get("coverage")
    objects = coverage.get("objects") if isinstance(coverage, dict) else None
    if not isinstance(objects, list):
        return {}
    return {
        str(item["object_id"]): dict(item)
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }


def _inventory_locator_aliases(
    inventory_objects: list[JsonObject],
) -> dict[str, set[str]]:
    def sequence(item: JsonObject) -> int:
        value = item.get("sequence")
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    inventory_objects.sort(key=sequence)
    aliases: defaultdict[str, set[str]] = defaultdict(set)
    picture_counts: Counter[str] = Counter()
    for item in inventory_objects:
        ref = item.get("source_object_ref")
        locator = item.get("source_locator")
        if not isinstance(ref, dict) or not isinstance(ref.get("object_id"), str):
            continue
        actual_id = str(ref["object_id"])
        aliases[actual_id]
        if not isinstance(locator, str):
            continue
        aliases[actual_id].add(locator)
        if item.get("kind") not in {"picture", "shape"}:
            continue
        host_match = _TOP_LEVEL_HOST.match(locator)
        if host_match is None:
            continue
        host = host_match.group(1)
        picture_counts[host] += 1
        aliases[actual_id].add(f"{host}/image[{picture_counts[host]}]")
    return dict(aliases)


def _align_gold_to_inventory(
    gold: JsonObject,
    inventory: JsonObject,
) -> tuple[JsonObject, JsonObject]:
    """Map Gold-local object IDs to this run's inventory through hash-bound locators."""

    inventory_objects = _object_list(inventory.get("objects"), label="Inventory objects")
    aliases_by_actual_id = _inventory_locator_aliases(inventory_objects)
    actual_ids = set(aliases_by_actual_id)
    locator_to_ids: defaultdict[str, set[str]] = defaultdict(set)
    for actual_id, aliases in aliases_by_actual_id.items():
        for locator in aliases:
            locator_to_ids[locator].add(actual_id)

    aligned = deepcopy(gold)
    aligned_count = 0
    exact_id_count = 0
    locator_count = 0
    unresolved: list[JsonObject] = []
    id_alignment: dict[str, str] = {}
    aligned_items = _object_list(aligned.get("items"), label="Gold items")
    for item in aligned_items:
        refs = item.get("source_object_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("object_id"), str):
                continue
            gold_id = str(ref["object_id"])
            if gold_id in actual_ids:
                id_alignment[gold_id] = gold_id
                exact_id_count += 1
                aligned_count += 1
                continue
            gold_locator = ref.get("source_locator")
            candidates = (
                sorted(locator_to_ids.get(gold_locator, set()))
                if isinstance(gold_locator, str)
                else []
            )
            if len(candidates) == 1:
                ref["object_id"] = candidates[0]
                id_alignment[gold_id] = candidates[0]
                locator_count += 1
                aligned_count += 1
                continue
            unresolved.append(
                {
                    "gold_source_object_id": gold_id,
                    "candidate_actual_source_object_ids": candidates,
                    "reason": "locator_missing" if not candidates else "locator_ambiguous",
                }
            )
    for item in aligned_items:
        occurrences = item.get("source_occurrences")
        if not isinstance(occurrences, list):
            continue
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                continue
            ref = occurrence.get("source_object_ref")
            if not isinstance(ref, dict) or not isinstance(ref.get("object_id"), str):
                continue
            aligned_id = id_alignment.get(str(ref["object_id"]))
            if aligned_id is not None:
                ref["object_id"] = aligned_id
    aligned["items"] = aligned_items
    total = sum(len(_gold_source_ids(item)) for item in aligned["items"])
    return aligned, {
        "gold_reference_count": total,
        "aligned_reference_count": aligned_count,
        "exact_object_id_count": exact_id_count,
        "locator_crosswalk_count": locator_count,
        "unresolved_reference_count": len(unresolved),
        "unresolved_references": unresolved,
        "complete": aligned_count == total and not unresolved,
    }


def _compare_provenance(
    actual: JsonObject,
    inventory: JsonObject,
    gold: JsonObject,
    actual_items: list[JsonObject],
) -> JsonObject:
    gold_registry = gold.get("field_registry_ref")
    actual_registry = actual.get("registry")
    inventory_items = _object_list(
        inventory.get("content_items"), label="Inventory content_items"
    )
    inventory_objects = _object_list(inventory.get("objects"), label="Inventory objects")
    inventory_ids = [item.get("source_content_id") for item in inventory_items]
    actual_ids = [item.get("source_content_id") for item in actual_items]
    inventory_orders = [_source_order(item) for item in inventory_items]
    actual_orders = [_source_order(item) for item in actual_items]
    inventory_bindings = [
        (
            item.get("source_content_id"),
            _string_list(item.get("source_object_ids")),
            _string_list(item.get("source_locators")),
            _source_order(item),
        )
        for item in inventory_items
    ]
    actual_bindings = [
        (
            item.get("source_content_id"),
            _actual_source_ids(item),
            _string_list(item.get("source_locators")),
            _source_order(item),
        )
        for item in actual_items
    ]
    inventory_by_object_id = {
        str(ref["object_id"]): item
        for item in inventory_objects
        if isinstance((ref := item.get("source_object_ref")), dict)
        and isinstance(ref.get("object_id"), str)
    }
    locator_aliases = _inventory_locator_aliases(inventory_objects)
    reference_mismatches: list[JsonObject] = []
    for gold_item in _object_list(gold.get("items"), label="Gold items"):
        refs = gold_item.get("source_object_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("object_id"), str):
                continue
            source_id = str(ref["object_id"])
            inventory_object = inventory_by_object_id.get(source_id)
            checks = {
                "present_in_inventory": inventory_object is not None,
                "document_sha256_match": inventory_object is not None
                and (
                    not isinstance(ref.get("document_sha256"), str)
                    or ref.get("document_sha256") == inventory.get("source_sha256")
                ),
                "source_locator_match": inventory_object is not None
                and (
                    not isinstance(ref.get("source_locator"), str)
                    or ref.get("source_locator")
                    in locator_aliases.get(source_id, set())
                ),
            }
            if not all(checks.values()):
                reference_mismatches.append(
                    {"source_object_id": source_id, "checks": checks}
                )
    return {
        "source_sha256_match": actual.get("source_sha256")
        == inventory.get("source_sha256")
        == gold.get("student_document_sha256"),
        "registry_identity_match": isinstance(gold_registry, dict)
        and isinstance(actual_registry, dict)
        and actual_registry.get("registry_id") == gold_registry.get("registry_id")
        and actual_registry.get("registry_version") == gold_registry.get("registry_version"),
        "registry_sha256_match": isinstance(gold_registry, dict)
        and isinstance(actual_registry, dict)
        and actual_registry.get("sha256") == gold_registry.get("sha256"),
        "actual_inventory_item_identity_match": actual_ids == inventory_ids,
        "actual_inventory_order_match": actual_orders == inventory_orders,
        "actual_inventory_source_binding_match": actual_bindings == inventory_bindings,
        "gold_inventory_source_reference_match": not reference_mismatches,
        "source_reference_comparison": {
            "gold_reference_count": sum(
                len(_gold_source_ids(item))
                for item in _object_list(gold.get("items"), label="Gold items")
            ),
            "mismatch_count": len(reference_mismatches),
            "mismatches": reference_mismatches,
        },
    }


def _compare_source_coverage(
    *,
    actual_by_source: dict[str, list[JsonObject]],
    gold_items: list[JsonObject],
    coverage: dict[str, JsonObject],
) -> JsonObject:
    expected_mapped = {
        source_id for item in gold_items for source_id in _gold_source_ids(item)
    }
    actual_ids = set(actual_by_source)
    missing = sorted(expected_mapped - actual_ids)
    actual_only = sorted(actual_ids - expected_mapped)
    incorrectly_excluded: list[JsonObject] = []
    unexpected: list[str] = []
    correctly_excluded = 0
    for source_id in actual_only:
        status = coverage.get(source_id, {}).get("status")
        actual_items = actual_by_source[source_id]
        layout_only = (
            all(item.get("classification_status") == "layout_only" for item in actual_items)
            and all(item.get("field_id") is None for item in actual_items)
        )
        if status in {"excluded", "covered_dependency"} or (
            status is None and layout_only
        ):
            if (
                layout_only
            ):
                correctly_excluded += 1
            else:
                incorrectly_excluded.append(
                    {
                        "source_object_id": source_id,
                        "gold_coverage_status": status,
                        "actual_statuses": sorted(
                            {str(item.get("classification_status")) for item in actual_items}
                        ),
                        "actual_field_ids": sorted(
                            {
                                str(item.get("field_id"))
                                for item in actual_items
                                if isinstance(item.get("field_id"), str)
                            }
                        ),
                    }
                )
        else:
            unexpected.append(source_id)
    expected_excluded_count = sum(
        1 for item in coverage.values() if item.get("status") == "excluded"
    )
    return {
        "gold_mapped_source_count": len(expected_mapped),
        "actual_source_count": len(actual_ids),
        "missing_mapped_source_count": len(missing),
        "missing_mapped_source_ids": missing,
        "gold_excluded_source_count": expected_excluded_count,
        "correctly_layout_only_count": correctly_excluded,
        "incorrectly_handled_excluded_count": len(incorrectly_excluded),
        "incorrectly_handled_excluded": incorrectly_excluded,
        "unexpected_actual_source_count": len(unexpected),
        "unexpected_actual_source_ids": unexpected,
    }


def _compare_fields(
    *,
    actual_items: list[JsonObject],
    actual_by_source: dict[str, list[JsonObject]],
    gold_items: list[JsonObject],
) -> JsonObject:
    exact = 0
    missing: list[JsonObject] = []
    mismatches: list[JsonObject] = []
    expected_counts: Counter[str] = Counter()
    for gold_item in gold_items:
        field_id = gold_item.get("field_id")
        if not isinstance(field_id, str):
            continue
        if _gold_source_ids(gold_item):
            expected_counts[field_id] += 1
        for source_id in _gold_source_ids(gold_item):
            candidates = actual_by_source.get(source_id, [])
            actual_item = _actual_for_field(actual_by_source, source_id, field_id)
            if not candidates:
                missing.append({"source_object_id": source_id, "field_id": field_id})
            elif actual_item is not None:
                exact += 1
            else:
                mismatches.append(
                    {
                        "source_object_id": source_id,
                        "gold_field_id": field_id,
                        "actual_field_ids": sorted(
                            {
                                str(item.get("field_id"))
                                for item in candidates
                                if isinstance(item.get("field_id"), str)
                            }
                        ),
                        "actual_statuses": sorted(
                            {str(item.get("classification_status")) for item in candidates}
                        ),
                    }
                )
    actual_counts: Counter[str] = Counter(
        str(item["field_id"])
        for item in actual_items
        if item.get("classification_status") == "classified"
        and isinstance(item.get("field_id"), str)
    )
    count_differences = [
        {
            "field_id": field_id,
            "gold_semantic_item_count": expected_counts[field_id],
            "actual_item_count": actual_counts[field_id],
            "delta": actual_counts[field_id] - expected_counts[field_id],
        }
        for field_id in sorted(set(expected_counts) | set(actual_counts))
        if expected_counts[field_id] != actual_counts[field_id]
    ]
    return {
        "gold_field_occurrence_count": sum(expected_counts.values()),
        "exact_source_field_matches": exact,
        "missing_source_field_count": len(missing),
        "missing_source_fields": missing,
        "field_mismatch_count": len(mismatches),
        "field_mismatches": mismatches,
        "field_count_difference_count": len(count_differences),
        "field_count_differences": count_differences,
    }


def _normalize_text(value: str) -> str:
    return "".join(value.split()).casefold()


def _values_equal(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if not isinstance(actual, str) or not isinstance(expected, str):
        return bool(actual == expected)
    return _normalize_text(actual) == _normalize_text(expected)


def _occurrence_expected_values(item: JsonObject) -> list[tuple[str, Any]]:
    occurrences = item.get("source_occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        return [(source_id, item.get("observed_value")) for source_id in _gold_source_ids(item)]
    normalized: list[tuple[str, Any]] = []
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            continue
        ref = occurrence.get("source_object_ref")
        if isinstance(ref, dict) and isinstance(ref.get("object_id"), str):
            normalized.append((str(ref["object_id"]), occurrence.get("observed_text")))
    if not normalized:
        return [(source_id, item.get("observed_value")) for source_id in _gold_source_ids(item)]
    observed_value = item.get("observed_value")
    joined = "".join(value for _, value in normalized if isinstance(value, str))
    is_fragmented_value = (
        isinstance(observed_value, str)
        and _normalize_text(observed_value) == _normalize_text(joined)
    )
    if is_fragmented_value:
        return normalized
    return [(source_id, observed_value) for source_id, _ in normalized]


def _compare_values(
    *,
    actual_by_source: dict[str, list[JsonObject]],
    actual_by_semantic_key: dict[SemanticKey, JsonObject],
    gold_items: list[JsonObject],
) -> JsonObject:
    compared = 0
    mismatches: list[JsonObject] = []
    for gold_item in gold_items:
        field_id = gold_item.get("field_id")
        semantic_key = _semantic_key(gold_item, _gold_source_ids)
        exact_group = actual_by_semantic_key.get(semantic_key)
        if semantic_key[0] and exact_group is not None:
            compared += 1
            if not _values_equal(exact_group.get("value"), gold_item.get("observed_value")):
                mismatches.append(_semantic_payload(semantic_key))
            continue
        for source_id, expected in _occurrence_expected_values(gold_item):
            actual_item = _actual_for_field(actual_by_source, source_id, field_id)
            if actual_item is None:
                continue
            compared += 1
            if not _values_equal(actual_item.get("value"), expected):
                mismatches.append(
                    {"source_object_id": source_id, "field_id": field_id}
                )
    return {
        "compared_occurrence_count": compared,
        "exact_value_matches": compared - len(mismatches),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "comparison_policy": "whitespace_normalized_no_content_in_report",
    }


def _compare_grouping(
    *,
    actual_by_binding: dict[SemanticKey, JsonObject],
    gold_by_binding: dict[SemanticKey, JsonObject],
    actual_duplicate_bindings: list[SemanticKey],
    gold_duplicate_bindings: list[SemanticKey],
) -> JsonObject:
    gold_keys = set(gold_by_binding)
    actual_keys = set(actual_by_binding)
    missing = sorted(gold_keys - actual_keys)
    gold_source_ids = {
        source_id for binding, _ in gold_keys for source_id in binding
    }
    unexpected = sorted(
        key
        for key in actual_keys - gold_keys
        if any(source_id in gold_source_ids for source_id in key[0])
    )
    return {
        "gold_source_bound_semantic_item_count": len(gold_keys),
        "exact_binding_group_count": len(gold_keys & actual_keys),
        "missing_binding_group_count": len(missing),
        "missing_binding_groups": [_semantic_payload(key) for key in missing],
        "unexpected_binding_group_count": len(unexpected),
        "unexpected_binding_groups": [_semantic_payload(key) for key in unexpected],
        "actual_duplicate_binding_groups": [
            _semantic_payload(key) for key in actual_duplicate_bindings
        ],
        "gold_duplicate_binding_groups": [
            _semantic_payload(key) for key in gold_duplicate_bindings
        ],
    }


def _compare_order(
    *,
    actual_items: list[JsonObject],
    gold_items: list[JsonObject],
    gold_by_binding: dict[SemanticKey, JsonObject],
) -> JsonObject:
    gold_sequence = [
        _semantic_key(item, _gold_source_ids)
        for item in gold_items
        if _gold_source_ids(item)
    ]
    gold_source_ids = {
        source_id for binding, _ in gold_sequence for source_id in binding
    }
    actual_sequence = [
        _semantic_key(item, _actual_source_ids)
        for item in actual_items
        if any(source_id in gold_source_ids for source_id in _actual_source_ids(item))
    ]
    first_mismatch: JsonObject | None = None
    for index in range(max(len(gold_sequence), len(actual_sequence))):
        expected = gold_sequence[index] if index < len(gold_sequence) else None
        observed = actual_sequence[index] if index < len(actual_sequence) else None
        if expected != observed:
            first_mismatch = {
                "index": index,
                "gold_binding": _semantic_payload(expected) if expected else None,
                "actual_binding": _semantic_payload(observed) if observed else None,
            }
            break
    exact = gold_sequence == actual_sequence
    comparable_actual_sequence = [key for key in actual_sequence if key in gold_by_binding]
    expected_comparable_sequence = [
        key for key in gold_sequence if key in set(comparable_actual_sequence)
    ]
    return {
        "gold_semantic_sequence_length": len(gold_sequence),
        "actual_aligned_sequence_length": len(actual_sequence),
        "exact_semantic_sequence_match": exact,
        "matched_binding_relative_order_match": (
            comparable_actual_sequence == expected_comparable_sequence
        ),
        "first_mismatch": first_mismatch,
        "authority": "Gold items[] under docfit-source-order/v1",
    }


def _relation_pairs(actual: JsonObject) -> set[tuple[str, str, str]]:
    relations = actual.get("relations")
    if not isinstance(relations, list):
        return set()
    return {
        (
            str(item.get("relation_type")),
            str(item.get("source_content_id")),
            str(item.get("target_content_id")),
        )
        for item in relations
        if isinstance(item, dict)
    }


def _compare_hierarchy(
    *,
    actual: JsonObject,
    actual_by_binding: dict[SemanticKey, JsonObject],
    gold_items: list[JsonObject],
) -> JsonObject:
    gold_by_content_id = {
        str(item["content_id"]): item
        for item in gold_items
        if isinstance(item.get("content_id"), str)
    }
    relations = _relation_pairs(actual)
    compared = 0
    direct = 0
    semantic = 0
    implicit_structural = 0
    mismatches: list[JsonObject] = []
    for gold_item in gold_items:
        parent_id = gold_item.get("parent_content_id")
        child_key = _semantic_key(gold_item, _gold_source_ids)
        if not isinstance(parent_id, str) or not child_key[0]:
            continue
        actual_child = actual_by_binding.get(child_key)
        gold_parent = gold_by_content_id.get(parent_id)
        if actual_child is None or gold_parent is None:
            continue
        parent_key = _semantic_key(gold_parent, _gold_source_ids)
        compared += 1
        if not parent_key[0]:
            if actual_child.get("parent_content_id") is None:
                implicit_structural += 1
            else:
                mismatches.append(
                    {
                        "child_binding": _semantic_payload(child_key),
                        "field_id": gold_item.get("field_id"),
                        "expected_parent_field_id": gold_parent.get("field_id"),
                    }
                )
            continue
        actual_parent = actual_by_binding.get(parent_key)
        if actual_parent is None:
            continue
        child_content_id = str(actual_child.get("content_id"))
        parent_content_id = str(actual_parent.get("content_id"))
        if actual_child.get("parent_content_id") == parent_content_id:
            direct += 1
            continue
        field_id = str(gold_item.get("field_id"))
        relation_type = (
            "caption_of"
            if field_id.endswith(".caption")
            else "note_of"
            if field_id.endswith(".note")
            else None
        )
        if relation_type and (
            relation_type,
            child_content_id,
            parent_content_id,
        ) in relations:
            semantic += 1
            continue
        mismatches.append(
            {
                "child_binding": _semantic_payload(child_key),
                "field_id": gold_item.get("field_id"),
                "expected_parent_binding": _semantic_payload(parent_key),
            }
        )
    return {
        "compared_relationship_count": compared,
        "direct_parent_matches": direct,
        "semantic_relation_matches": semantic,
        "implicit_structural_root_matches": implicit_structural,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def _api_evidence_summary(evidence: JsonObject) -> JsonObject:
    batches = evidence.get("batches")
    if not isinstance(batches, list):
        batches = []
    valid = [
        item
        for item in batches
        if isinstance(item, dict)
        and isinstance(item.get("backend"), str)
        and bool(item.get("backend"))
        and isinstance(item.get("session_id"), str)
        and bool(item.get("session_id"))
    ]
    return {
        "backend": evidence.get("backend"),
        "batch_count": len(batches),
        "batches_with_backend_and_session": len(valid),
        "session_count": len({str(item["session_id"]) for item in valid}),
        "tool_uses": sorted(
            {
                str(tool)
                for item in batches
                if isinstance(item, dict)
                for tool in _string_list(item.get("tool_uses"))
            }
        ),
        "evidence_complete": bool(batches) and len(valid) == len(batches),
    }


def compare_student_content(
    actual: JsonObject,
    inventory: JsonObject,
    gold: JsonObject,
    evidence: JsonObject,
) -> JsonObject:
    """Compare one saved extraction Actual with one accepted Extraction Gold."""

    actual_items = _validate_actual(actual)
    _validate_gold(gold)
    if inventory.get("schema_version") != "docfit-student-source-inventory/v2":
        raise StudentContentEvalInputError(
            "unsupported_inventory_schema",
            "Inventory must use docfit-student-source-inventory/v2.",
        )
    aligned_gold, source_alignment = _align_gold_to_inventory(gold, inventory)
    gold_items = _object_list(aligned_gold.get("items"), label="Aligned Gold items")
    actual_by_source = _index_actual_by_source(actual_items)
    actual_by_binding, actual_duplicate_bindings, _ = _index_by_semantic_key(
        actual_items, _actual_source_ids
    )
    gold_by_binding, gold_duplicate_bindings, synthetic_gold = _index_by_semantic_key(
        gold_items, _gold_source_ids
    )
    coverage = _gold_coverage(gold)

    provenance = _compare_provenance(actual, inventory, aligned_gold, actual_items)
    provenance["gold_source_alignment_complete"] = source_alignment["complete"]
    source_reference = provenance.pop("source_reference_comparison")
    source_coverage = _compare_source_coverage(
        actual_by_source=actual_by_source,
        gold_items=gold_items,
        coverage=coverage,
    )
    fields = _compare_fields(
        actual_items=actual_items,
        actual_by_source=actual_by_source,
        gold_items=gold_items,
    )
    values = _compare_values(
        actual_by_source=actual_by_source,
        actual_by_semantic_key=actual_by_binding,
        gold_items=gold_items,
    )
    grouping = _compare_grouping(
        actual_by_binding=actual_by_binding,
        gold_by_binding=gold_by_binding,
        actual_duplicate_bindings=actual_duplicate_bindings,
        gold_duplicate_bindings=gold_duplicate_bindings,
    )
    order = _compare_order(
        actual_items=actual_items,
        gold_items=gold_items,
        gold_by_binding=gold_by_binding,
    )
    hierarchy = _compare_hierarchy(
        actual=actual,
        actual_by_binding=actual_by_binding,
        gold_items=gold_items,
    )
    api_evidence = _api_evidence_summary(evidence)

    blockers: list[str] = []
    if not all(value is True for value in provenance.values()):
        blockers.append("provenance_mismatch")
    if actual.get("status") != "READY":
        blockers.append("actual_not_ready")
    if actual_duplicate_bindings or gold_duplicate_bindings:
        blockers.append("duplicate_source_binding")
    if (
        source_coverage["missing_mapped_source_count"]
        or source_coverage["unexpected_actual_source_count"]
    ):
        blockers.append("source_coverage_mismatch")
    if source_coverage["incorrectly_handled_excluded_count"]:
        blockers.append("excluded_source_misclassified")
    if (
        fields["missing_source_field_count"]
        or fields["field_mismatch_count"]
        or fields["field_count_difference_count"]
    ):
        blockers.append("field_semantics_mismatch")
    if values["mismatch_count"]:
        blockers.append("observed_value_mismatch")
    if grouping["missing_binding_group_count"] or grouping["unexpected_binding_group_count"]:
        blockers.append("semantic_item_grouping_mismatch")
    if not order["exact_semantic_sequence_match"]:
        blockers.append("content_order_mismatch")
    if hierarchy["mismatch_count"]:
        blockers.append("hierarchy_mismatch")
    if not api_evidence["evidence_complete"]:
        blockers.append("live_api_evidence_incomplete")

    dimension_status = {
        "provenance": "PASS" if all(value is True for value in provenance.values()) else "FAIL",
        "source_coverage": "PASS"
        if not (
            source_coverage["missing_mapped_source_count"]
            or source_coverage["unexpected_actual_source_count"]
            or source_coverage["incorrectly_handled_excluded_count"]
        )
        else "FAIL",
        "field_semantics": "PASS"
        if not (
            fields["missing_source_field_count"]
            or fields["field_mismatch_count"]
            or fields["field_count_difference_count"]
        )
        else "FAIL",
        "value_fidelity": "PASS" if not values["mismatch_count"] else "FAIL",
        "semantic_grouping": "PASS"
        if not (
            grouping["missing_binding_group_count"]
            or grouping["unexpected_binding_group_count"]
            or actual_duplicate_bindings
            or gold_duplicate_bindings
        )
        else "FAIL",
        "content_order": "PASS" if order["exact_semantic_sequence_match"] else "FAIL",
        "hierarchy": "PASS" if not hierarchy["mismatch_count"] else "FAIL",
        "live_run_evidence": "PASS" if api_evidence["evidence_complete"] else "FAIL",
    }
    return {
        "schema_version": "docfit-student-content-extraction-eval-report/v1",
        "status": "PASS" if not blockers else "FAIL",
        "gold_id": gold.get("gold_id"),
        "gold_revision": gold.get("gold_revision"),
        "actual_model_status": actual.get("status"),
        "blockers": blockers,
        "dimensions": dimension_status,
        "provenance": provenance,
        "source_alignment": source_alignment,
        "source_reference_comparison": source_reference,
        "counts": {
            "inventory_source_object_count": inventory.get("object_count"),
            "inventory_content_item_count": inventory.get("content_item_count"),
            "actual_item_count": len(actual_items),
            "gold_semantic_item_count": len(gold_items),
            "gold_source_bound_semantic_item_count": len(gold_by_binding),
            "gold_synthetic_structure_item_count": len(synthetic_gold),
        },
        "api_evidence": api_evidence,
        "source_binding": {
            "actual_overlapping_source_ids": sorted(
                source_id for source_id, items in actual_by_source.items() if len(items) > 1
            ),
            "synthetic_gold_items": [
                {
                    "content_id": item.get("content_id"),
                    "field_id": item.get("field_id"),
                }
                for item in synthetic_gold
            ],
        },
        "source_coverage_comparison": source_coverage,
        "field_comparison": fields,
        "value_comparison": values,
        "semantic_grouping_comparison": grouping,
        "order_comparison": order,
        "hierarchy_comparison": hierarchy,
        "artifacts": {},
        "privacy": "metadata_only_no_student_content",
    }


_BLOCKER_DESCRIPTIONS = {
    "provenance_mismatch": "Actual、inventory、Gold 的学生源或 Registry 版本不一致",
    "actual_not_ready": "本次提取结果不是 READY",
    "duplicate_source_binding": "存在重复或不唯一的源绑定",
    "source_coverage_mismatch": "Gold 应提取的源对象存在遗漏或 Actual 多出未知源对象",
    "excluded_source_misclassified": "Gold 排除的版式对象被错误识别为用户内容",
    "field_semantics_mismatch": "一个或多个源内容没有映射到 Gold 指定的 Registry 字段",
    "observed_value_mismatch": "字段正确的内容中存在原文值差异",
    "semantic_item_grouping_mismatch": "跨源内容实例被错误拆分、合并或重复",
    "content_order_mismatch": "Actual 内容实例顺序与 Gold items[] 的权威顺序不一致",
    "hierarchy_mismatch": "章节、题注、注释等父子或语义关系不一致",
    "live_api_evidence_incomplete": "缺少完整的真实 Agent batch/session 证据",
}


def render_student_content_markdown(report: JsonObject) -> str:
    """Render a product-readable, student-content-free comparison report."""

    dimensions = report["dimensions"]
    counts = report["counts"]
    fields = report["field_comparison"]
    values = report["value_comparison"]
    coverage = report["source_coverage_comparison"]
    grouping = report["semantic_grouping_comparison"]
    hierarchy = report["hierarchy_comparison"]
    order = report["order_comparison"]
    api = report["api_evidence"]
    alignment = report["source_alignment"]
    lines = [
        f"# {report['gold_id']} 内容提取 Actual–Gold 评测报告",
        "",
        f"- 结论：`{report['status']}`",
        f"- Gold revision：`{report['gold_revision']}`",
        f"- Actual 模型状态：`{report['actual_model_status']}`",
        "- 隐私：报告只包含 hash、计数、field_id、源对象 ID 和运行元数据，不包含学生正文。",
        "",
        "## 评测维度",
        "",
        "| 维度 | 结论 | 核心证据 |",
        "|---|---|---|",
        f"| 来源与版本绑定 | {dimensions['provenance']} | source、Registry、inventory 一致性 |",
        f"| 源内容覆盖 | {dimensions['source_coverage']} | "
        f"Gold 映射 {coverage['gold_mapped_source_count']}；"
        f"遗漏 {coverage['missing_mapped_source_count']}；"
        f"未知多出 {coverage['unexpected_actual_source_count']} |",
        f"| Registry 字段语义 | {dimensions['field_semantics']} | "
        f"命中 {fields['exact_source_field_matches']}/"
        f"{fields['gold_field_occurrence_count']}；"
        f"字段差异 {fields['field_mismatch_count']} |",
        f"| 原文值忠实度 | {dimensions['value_fidelity']} | "
        f"命中 {values['exact_value_matches']}/"
        f"{values['compared_occurrence_count']} |",
        f"| 语义实例拆分/合并 | {dimensions['semantic_grouping']} | "
        f"精确绑定组 {grouping['exact_binding_group_count']}/"
        f"{grouping['gold_source_bound_semantic_item_count']} |",
        f"| 内容顺序 | {dimensions['content_order']} | "
        f"Gold {order['gold_semantic_sequence_length']}；"
        f"Actual 对齐 {order['actual_aligned_sequence_length']} |",
        f"| 父子与题注关系 | {dimensions['hierarchy']} | 差异 {hierarchy['mismatch_count']} |",
        f"| 真实运行证据 | {dimensions['live_run_evidence']} | "
        f"batch {api['batches_with_backend_and_session']}/{api['batch_count']}；"
        f"session {api['session_count']} |",
        "",
        "## 内容规模",
        "",
        f"- Inventory 内容项：{counts['inventory_content_item_count']}",
        f"- Actual 内容项：{counts['actual_item_count']}",
        f"- Gold 语义内容项：{counts['gold_semantic_item_count']}"
        f"（其中无源结构项 {counts['gold_synthetic_structure_item_count']}）",
        f"- Gold 源引用对齐：{alignment['aligned_reference_count']}/"
        f"{alignment['gold_reference_count']}（直接 ID {alignment['exact_object_id_count']}；"
        f"locator crosswalk {alignment['locator_crosswalk_count']}）",
        "",
        "## 阻断项与研发含义",
        "",
    ]
    blockers = report["blockers"]
    if blockers:
        lines.extend(
            f"- `{blocker}`：{_BLOCKER_DESCRIPTIONS.get(str(blocker), '见 JSON 机器报告')}"
            for blocker in blockers
        )
    else:
        lines.append("- 无；本次 Actual 可作为该 Gold revision 下的通过结果。")
    lines.extend(
        [
            "",
            "## 顺序判定",
            "",
            f"- 权威来源：`{order['authority']}`",
            f"- 完整语义序列一致：`{order['exact_semantic_sequence_match']}`",
            f"- 已匹配内容的相对顺序一致：`{order['matched_binding_relative_order_match']}`",
            "- 首个差异位置及对应源对象 ID 见同目录 JSON 的 `order_comparison.first_mismatch`。",
            "",
            "## 详细差异入口",
            "",
            "- 字段漏项/错项：`field_comparison`",
            "- 原文值差异：`value_comparison`",
            "- 拆分/合并差异：`semantic_grouping_comparison`",
            "- 顺序差异：`order_comparison`",
            "- 父子与题注关系：`hierarchy_comparison`",
            "- 源覆盖与排除项：`source_coverage_comparison`",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def run_student_content_eval(
    *,
    actual_directory: Path,
    gold: Path,
    output_directory: Path,
) -> StudentContentEvalResult:
    """Load a saved extraction task, compare it, and publish JSON plus Markdown."""

    try:
        actual_root = actual_directory.expanduser().resolve(strict=True)
    except FileNotFoundError as error:
        raise StudentContentEvalInputError(
            "actual_directory_missing",
            "The requested extraction output directory does not exist.",
        ) from error
    if not actual_root.is_dir():
        raise StudentContentEvalInputError(
            "actual_directory_invalid",
            "The requested extraction output must be a directory.",
        )
    gold_candidate = gold.expanduser()
    if gold_candidate.is_dir():
        gold_candidate = gold_candidate / GOLD_FILENAME
    try:
        gold_path = gold_candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise StudentContentEvalInputError(
            "gold_missing",
            "The requested Extraction Gold does not exist.",
        ) from error
    if not gold_path.is_file():
        raise StudentContentEvalInputError(
            "gold_invalid",
            "The requested Extraction Gold must be a JSON file or Gold package directory.",
        )

    actual_path = actual_root / ACTUAL_FILENAME
    inventory_path = actual_root / INVENTORY_FILENAME
    evidence_path = actual_root / EVIDENCE_FILENAME
    actual = _load_object(actual_path, label="Actual student-content.json")
    inventory = _load_object(inventory_path, label="Actual student inventory")
    evidence = _load_object(evidence_path, label="Actual Agent evidence")
    gold_object = _load_object(gold_path, label="Extraction Gold")
    report = compare_student_content(actual, inventory, gold_object, evidence)
    report["artifacts"] = {
        "actual_sha256": sha256_file(actual_path),
        "inventory_sha256": sha256_file(inventory_path),
        "agent_evidence_sha256": sha256_file(evidence_path),
        "gold_sha256": sha256_file(gold_path),
    }

    output = output_directory.expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise StudentContentEvalInputError(
            "eval_output_invalid",
            "The evaluation output path exists and is not a directory.",
        )
    output.mkdir(parents=True, exist_ok=True)
    json_report = output / JSON_REPORT_FILENAME
    markdown_report = output / MARKDOWN_REPORT_FILENAME
    atomic_write_json(json_report, report)
    _atomic_write_text(markdown_report, render_student_content_markdown(report))
    return StudentContentEvalResult(
        report=report,
        json_report=json_report,
        markdown_report=markdown_report,
    )
