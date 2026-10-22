"""Template-extraction semantic coverage harness.

The harness does not judge school meaning. It records a source-object inventory
and checks whether the Agent's semantic judgments mechanically cover that
inventory without gaps, overlap, or empty judgments.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from docfit.fields.registry import FieldRegistrySnapshot
from docfit.template.judgment_shape import (
    is_whole_entry_part,
    mechanical_feedback,
    validate_ordered_semantic_parts,
)
from docfit.template.semantic_recovery import classify_semantic_feedback
from docfit.template.source_entries import (
    OBJECT_ID_BACKEND_ALIAS_ROLE,
    CanonicalSourceInventory,
    validate_canonical_source_entries,
)
from docfit.template.source_spans import (
    SourceSpanResolutionError,
    resolve_semantic_judgments,
)
from docfit.template.unit_source import require_initial_binding
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    sha256_json,
    task_root_from_args,
)

HARNESS_SCHEMA_VERSION = 2
HARNESS_DIR = Path("work/.docfit/harness")
OBJECT_INVENTORY_PATH = HARNESS_DIR / "object-inventory.json"
SEMANTIC_JUDGMENTS_PATH = HARNESS_DIR / "semantic-judgments.json"
_STRUCTURAL_CARRIER_OBJECT_TYPES = {"paragraph", "table", "picture", "shape"}


def _coverage_feedback_metadata() -> JsonObject:
    return {
        "type": "coverage",
        "mechanical": True,
        "semantic_authority": False,
        "agent_action": (
            "Revise semantic judgment source_entry_id, parts, or compatibility reading "
            "view boundaries against the original evidence; change semantic conclusions "
            "only when the coverage gap exposes a real school-template conflict."
        ),
    }


def _non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_argument_invalid",
            message=f"{field} must be a non-empty string.",
        )
    return value.strip()


def _document_sha(value: Any) -> str:
    text = _non_empty_string(value, field="document_sha256")
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_document_sha_invalid",
            message="document_sha256 must be a lowercase SHA-256 hex digest.",
        )
    return text


def _json_object(value: Any, *, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_argument_invalid",
            message=f"{field} must be an object.",
        )
    return value


def _list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_argument_invalid",
            message=f"{field} must be an array.",
        )
    return value


def _object_ref(value: Any, *, field: str) -> JsonObject:
    item = _json_object(value, field=field)
    if isinstance(item.get("object_ref"), dict):
        item = _json_object(item["object_ref"], field=f"{field}.object_ref")
    _non_empty_string(item.get("object_id"), field=f"{field}.object_id")
    return item


def _string_ids_from_array(value: Any, *, field: str) -> list[str]:
    values = _list(value, field=field)
    return [_non_empty_string(item, field=f"{field}[{index}]") for index, item in enumerate(values)]


def _integer(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_argument_invalid",
            message=f"{field} must be an integer.",
        )
    return value


def _inventory_object_text_spans(
    value: Any,
    *,
    field: str,
    block_text: str,
    covered_object_ids: list[str],
) -> list[JsonObject]:
    if value is None:
        return []
    object_ids = set(covered_object_ids)
    spans: list[JsonObject] = []
    for index, raw in enumerate(_list(value, field=field)):
        item = _json_object(raw, field=f"{field}[{index}]")
        object_id = _non_empty_string(item.get("object_id"), field=f"{field}[{index}].object_id")
        if object_id not in object_ids:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message=(
                    f"{field}[{index}].object_id must be listed in the reading block "
                    "covered_object_ids."
                ),
            )
        start = _integer(item.get("text_start"), field=f"{field}[{index}].text_start")
        end = _integer(item.get("text_end"), field=f"{field}[{index}].text_end")
        if start < 0 or end <= start or end > len(block_text):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message=(
                    f"{field}[{index}] must identify a non-empty text range inside "
                    "reading_blocks text."
                ),
            )
        span: JsonObject = {
            "object_id": object_id,
            "text_start": start,
            "text_end": end,
        }
        span_text = item.get("text")
        if isinstance(span_text, str) and span_text:
            if span_text != block_text[start:end]:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_harness_argument_invalid",
                    message=(
                        f"{field}[{index}].text must match the referenced reading block text slice."
                    ),
                )
            span["text"] = span_text
        spans.append(span)
    _require_object_text_spans_cover_block_text(
        spans,
        field=field,
        block_text=block_text,
    )
    return spans


def _require_object_text_spans_cover_block_text(
    spans: list[JsonObject],
    *,
    field: str,
    block_text: str,
) -> None:
    cursor = 0
    for index, span in enumerate(spans):
        start = span.get("text_start")
        end = span.get("text_end")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message=f"{field}[{index}] must identify integer text offsets.",
            )
        if start < cursor:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message=(
                    f"{field} must be ordered and must not overlap inside reading_blocks text."
                ),
            )
        if block_text[cursor:start].strip():
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message=(
                    f"{field} must cover every non-whitespace character in reading_blocks text."
                ),
            )
        cursor = end
    if block_text[cursor:].strip():
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_argument_invalid",
            message=(f"{field} must cover every non-whitespace character in reading_blocks text."),
        )


def _require_reading_block_text_span_object_closure(
    reading_blocks: list[JsonObject],
    *,
    objects: list[JsonObject],
) -> None:
    known_object_ids: set[str] = set()
    object_types: dict[str, str] = {}
    canonical_provenance_object_ids: set[str] = set()
    for item in objects:
        object_id = item.get("object_id")
        if not isinstance(object_id, str) or not object_id.strip():
            continue
        normalized_id = object_id.strip()
        known_object_ids.add(normalized_id)
        object_type = item.get("type")
        if isinstance(object_type, str) and object_type.strip():
            object_types[normalized_id] = object_type.strip()
        source_entry_ref = item.get("source_entry_ref")
        provenance = (
            source_entry_ref.get("provenance") if isinstance(source_entry_ref, dict) else None
        )
        if isinstance(provenance, list) and any(
            isinstance(fragment, dict)
            and fragment.get("object_id") == normalized_id
            and (
                fragment.get("extent") == {"kind": "whole_entry"}
                or isinstance(fragment.get("text_span"), list)
            )
            for fragment in provenance
        ):
            canonical_provenance_object_ids.add(normalized_id)

    for block_index, block in enumerate(reading_blocks):
        block_text = block.get("text")
        if not isinstance(block_text, str) or not block_text.strip():
            continue
        raw_covered_object_ids = block.get("covered_object_ids")
        covered_object_ids = (
            [
                item.strip()
                for item in raw_covered_object_ids
                if isinstance(item, str) and item.strip()
            ]
            if isinstance(raw_covered_object_ids, list)
            else []
        )
        if not covered_object_ids:
            continue
        raw_text_spans = block.get("object_text_spans")
        mapped_object_ids: set[str] = set()
        if isinstance(raw_text_spans, list):
            for item in raw_text_spans:
                if not isinstance(item, dict):
                    continue
                object_id = item.get("object_id")
                if isinstance(object_id, str) and object_id.strip():
                    mapped_object_ids.add(object_id.strip())
        for object_index, object_id in enumerate(covered_object_ids):
            if object_id not in known_object_ids:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_harness_argument_invalid",
                    message=(
                        f"reading_blocks[{block_index}].covered_object_ids[{object_index}] "
                        "must identify an object submitted in objects."
                    ),
                )
            if object_id in mapped_object_ids:
                continue
            object_type = object_types.get(object_id)
            if (
                object_type in _STRUCTURAL_CARRIER_OBJECT_TYPES
                or object_id in canonical_provenance_object_ids
            ):
                continue
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message=(
                    f"reading_blocks[{block_index}].covered_object_ids[{object_index}] "
                    "must appear in object_text_spans unless it is a structural carrier "
                    "object."
                ),
            )


def _inventory_object(
    raw: Any,
    *,
    index: int,
    document_sha256: str,
    canonical_source_entry_ids: set[str] | None = None,
) -> JsonObject:
    item = _json_object(raw, field=f"objects[{index}]")
    ref = _object_ref(item, field=f"objects[{index}]")
    object_id = _non_empty_string(ref.get("object_id"), field=f"objects[{index}].object_id")
    ref_document = ref.get("document_sha256")
    if ref_document is not None and ref_document != document_sha256:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_object_document_mismatch",
            message="An object_ref belongs to a different document snapshot.",
        )
    object_type = item.get("type")
    label = item.get("label")
    locator = item.get("locator")
    if canonical_source_entry_ids is None:
        if "source_entry_id" in item or "source_entry_ref" in item:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_source_entry_inventory_invalid",
                message=(
                    "Raw inspection components cannot supply canonical source-entry "
                    "identity. Submit the persisted canonical source inventory."
                ),
            )
        source_entry_id = None
        source_entry_ref = None
    else:
        source_entry_id = _non_empty_string(
            item.get("source_entry_id"),
            field=f"objects[{index}].source_entry_id",
        )
        source_entry_ref_value = item.get("source_entry_ref")
        if isinstance(source_entry_ref_value, dict):
            source_entry_ref = dict(source_entry_ref_value)
            supplied_entry_id = source_entry_ref.get("source_entry_id")
            if (
                isinstance(supplied_entry_id, str)
                and supplied_entry_id.strip()
                and supplied_entry_id.strip() != source_entry_id
            ):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_source_entry_inventory_invalid",
                    message="source_entry_ref.source_entry_id must match object source_entry_id.",
                )
            source_entry_ref["source_entry_id"] = source_entry_id
            source_entry_ref.setdefault("source_sha256", document_sha256)
        else:
            source_entry_ref = {
                "source_entry_id": source_entry_id,
                "source_sha256": document_sha256,
            }
    stored: JsonObject = {
        "object_id": object_id,
        "object_ref": ref,
    }
    if source_entry_id is not None and source_entry_ref is not None:
        stored.update(
            {
                "source_entry_id": source_entry_id,
                "source_entry_ref": source_entry_ref,
                "object_id_role": OBJECT_ID_BACKEND_ALIAS_ROLE,
                "object_id_alias_for": source_entry_id,
            }
        )
    if isinstance(object_type, str) and object_type.strip():
        stored["type"] = object_type.strip()
    if isinstance(label, str) and label.strip():
        stored["label"] = label.strip()
    if isinstance(locator, str) and locator.strip():
        stored["locator"] = locator.strip()
    return stored


def _inventory_reading_block(raw: Any, *, index: int) -> JsonObject:
    item = _json_object(raw, field=f"reading_blocks[{index}]")
    block_id = _non_empty_string(item.get("block_id"), field=f"reading_blocks[{index}].block_id")
    object_ids = _string_ids_from_array(
        item.get("covered_object_ids"),
        field=f"reading_blocks[{index}].covered_object_ids",
    )
    raw_source_entry_ids = item.get("covered_source_entry_ids")
    source_entry_ids = (
        _string_ids_from_array(
            raw_source_entry_ids,
            field=f"reading_blocks[{index}].covered_source_entry_ids",
        )
        if raw_source_entry_ids is not None
        else []
    )
    stored: JsonObject = {
        "block_id": block_id,
        "covered_object_ids": list(dict.fromkeys(object_ids)),
    }
    if source_entry_ids:
        stored["covered_source_entry_ids"] = list(dict.fromkeys(source_entry_ids))
    range_id = item.get("range_id")
    if isinstance(range_id, str) and range_id.strip():
        stored["range_id"] = range_id.strip()
    unit_range_id = item.get("unit_range_id")
    if isinstance(unit_range_id, str) and unit_range_id.strip():
        stored["unit_range_id"] = unit_range_id.strip()
    order = item.get("order")
    if isinstance(order, int):
        stored["order"] = order
    unit_id = item.get("unit_id")
    if isinstance(unit_id, str) and unit_id.strip():
        stored["unit_id"] = unit_id.strip()
    unit_name = item.get("unit_name")
    if isinstance(unit_name, str) and unit_name.strip():
        stored["unit_name"] = unit_name.strip()[:120]
    text = item.get("text")
    if isinstance(text, str) and text:
        stored["text"] = text
    block_text = str(stored.get("text", ""))
    object_text_spans = _inventory_object_text_spans(
        item.get("object_text_spans"),
        field=f"reading_blocks[{index}].object_text_spans",
        block_text=block_text,
        covered_object_ids=stored["covered_object_ids"],
    )
    if (
        block_text
        and stored["covered_object_ids"]
        and not object_text_spans
        and not source_entry_ids
    ):
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_argument_invalid",
            message=(
                f"reading_blocks[{index}].object_text_spans is required for text "
                "reading blocks with covered_object_ids."
            ),
        )
    if object_text_spans:
        stored["object_text_spans"] = object_text_spans
    return stored


def _inventory_source_entries(value: Any) -> list[JsonObject]:
    if value is None:
        return []
    try:
        entries = validate_canonical_source_entries(value)
    except ValueError as error:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_source_entry_inventory_invalid",
            message=str(error),
        ) from error
    return [entry.to_json() for entry in entries]


def _task_field_registry(root: Path) -> Path:
    for name in (
        "input/field-registry.yaml",
        "input/field-registry.yml",
        "input/field-registry.json",
    ):
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="field_registry_missing",
        message="Harness needs the prepared input field Registry to verify field bindings.",
        suggested_actions=("Ensure input/field-registry.yaml is present.",),
    )


def _task_field_vocabulary(root: Path) -> JsonObject:
    registry_path = _task_field_registry(root)
    return FieldRegistrySnapshot.load(registry_path).pre_input_vocabulary()


def _inventory_field_vocabulary(inventory: JsonObject) -> JsonObject | None:
    vocabulary = inventory.get("field_id_vocabulary")
    if isinstance(vocabulary, dict):
        return vocabulary
    return None


def _field_vocabulary_required_feedback() -> JsonObject:
    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "status": "needs_input",
        "feedback": {
            "type": "field_id_vocabulary",
            "mechanical": True,
            "semantic_authority": False,
            "agent_action": (
                "Prepare the task with input/field-registry.yaml so the Agent receives "
                "field_id_vocabulary before submitting ordered semantic parts."
            ),
        },
        "checks": [{"name": "field_id_vocabulary", "result": "needs_input"}],
        "blockers": [
            {
                "code": "field_id_vocabulary_missing",
                "message": (
                    "Harness semantic submission requires a pre-input field vocabulary; "
                    "legacy field aliases are not accepted."
                ),
            }
        ],
        "failure": {
            "origin": "request",
            "code": "template_field_vocabulary_missing",
            "retryable": True,
            "message": (
                "Semantic judgments cannot be accepted without the task input field vocabulary."
            ),
            "suggested_actions": ["prepare_field_registry_before_post_unit_semantics"],
        },
        "warnings": [],
    }


def _allowed_vocabulary_field_ids(vocabulary: JsonObject) -> tuple[str, ...]:
    raw_ids = vocabulary.get("allowed_field_ids")
    if not isinstance(raw_ids, list):
        return ()
    return tuple(item.strip() for item in raw_ids if isinstance(item, str) and item.strip())


def _source_entry_ids(inventory: JsonObject) -> tuple[str, ...]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return ()
    return tuple(
        str(item["source_entry_id"]).strip()
        for item in raw_entries
        if isinstance(item, dict)
        and isinstance(item.get("source_entry_id"), str)
        and item["source_entry_id"].strip()
    )


def _judgment_source_entry_id(judgment: JsonObject) -> str | None:
    source_entry_id = judgment.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        return source_entry_id.strip()
    return None


def _resolve_ordered_span_refs(
    inventory: JsonObject,
    judgments: list[JsonObject],
) -> tuple[list[JsonObject], JsonObject | None]:
    try:
        return resolve_semantic_judgments(inventory=inventory, judgments=judgments), None
    except SourceSpanResolutionError as error:
        return (
            [],
            {
                "schema_version": HARNESS_SCHEMA_VERSION,
                "status": "needs_input",
                "feedback": {
                    "type": "span_resolution",
                    "mechanical": True,
                    "semantic_authority": False,
                    "agent_action": (
                        "Revise ordered semantic parts so their text segments partition the "
                        "named source entry's exact text in order, including any boundary "
                        "whitespace reported by the current unit packet."
                    ),
                },
                "checks": [{"name": "ordered_span_resolution", "result": "needs_input"}],
                "blockers": error.blockers,
                "failure": {
                    "origin": "request",
                    "code": "template_ordered_span_resolution_incomplete",
                    "retryable": True,
                    "message": (
                        "Harness could not resolve ordered semantic parts to scoped spans."
                    ),
                    "suggested_actions": ["split_parts_against_exact_source_entry_text"],
                },
                "warnings": [],
            },
        )


def _decode_semantic_parts(
    inventory: JsonObject, judgments: list[JsonObject],
) -> tuple[list[JsonObject], JsonObject | None]:
    """Resolve an explicitly declared whole entry before ordinary text decoding."""
    texts = _source_entry_text_by_id(inventory)
    expanded: list[JsonObject] = []
    blockers: list[JsonObject] = []
    for index, judgment in enumerate(judgments):
        parts = judgment.get("parts")
        declaration = isinstance(parts, list) and any(
            isinstance(part, dict) and "whole_entry" in part for part in parts
        )
        if not declaration:
            expanded.append(judgment)
            continue
        assert isinstance(parts, list)
        source_entry_id = judgment.get("source_entry_id")
        if len(parts) != 1 or not is_whole_entry_part(parts[0], part_count=len(parts)):
            blockers.append({
                "code": "ordered_whole_entry_declaration_invalid",
                "field": f"semantic_judgments[{index}].parts",
                "source_entry_id": source_entry_id,
                "message": "Declare whole_entry=true only as the sole part, without text or "
                "whitespace transport. Use text parts for mixed responsibilities.",
            })
        elif not isinstance(source_entry_id, str) or source_entry_id not in texts:
            blockers.append({
                "code": "ordered_semantic_source_entry_unknown",
                "field": f"semantic_judgments[{index}].source_entry_id",
                "source_entry_id": source_entry_id,
                "message": "The declared whole entry must name an entry in the current source.",
            })
        else:
            part = {key: value for key, value in parts[0].items() if key != "whole_entry"}
            part["text"] = texts[source_entry_id]
            expanded.append({**judgment, "parts": [part]})
    if blockers:
        return expanded, mechanical_feedback(
            feedback_type="ordered_semantic_parts", code="ordered_semantic_parts_invalid",
            message="The explicit whole-entry declaration could not be resolved.",
            blockers=blockers,
        )
    return _decode_whitespace_parts(expanded)


def _whitespace_run_text(value: Any) -> str | None:
    if not isinstance(value, dict) or set(value) != {"codepoint", "count"}:
        return None
    codepoint, count = value.get("codepoint"), value.get("count")
    if (
        not isinstance(codepoint, str)
        or not codepoint.startswith("U+")
        or not 4 <= len(codepoint[2:]) <= 6
        or any(digit not in "0123456789ABCDEF" for digit in codepoint[2:])
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
    ):
        return None
    try:
        character = chr(int(codepoint[2:], 16))
    except (ValueError, OverflowError):
        return None
    return character * count if character.isspace() else None


def _whitespace_runs_text(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    runs = [_whitespace_run_text(run) for run in value]
    if any(run is None for run in runs):
        return None
    return "".join(run for run in runs if run is not None)


def _decode_whitespace_parts(
    judgments: list[JsonObject],
) -> tuple[list[JsonObject], JsonObject | None]:
    decoded: list[JsonObject] = []
    blockers: list[JsonObject] = []
    transport_keys = {"whitespace", "leading_whitespace", "trailing_whitespace"}
    for judgment_index, judgment in enumerate(judgments):
        normalized = dict(judgment)
        raw_parts = judgment.get("parts")
        if not isinstance(raw_parts, list):
            decoded.append(normalized)
            continue
        parts: list[Any] = []
        for part_index, raw_part in enumerate(raw_parts):
            if not isinstance(raw_part, dict) or not transport_keys.intersection(raw_part):
                parts.append(raw_part)
                continue
            part = dict(raw_part)
            text = part.get("text")
            rendered: str | None = None
            if "whitespace" in part:
                if text == "" and not {
                    "leading_whitespace", "trailing_whitespace"
                }.intersection(part):
                    rendered = _whitespace_run_text(part["whitespace"])
                field = "whitespace"
                message = (
                    "Whitespace transport requires empty text, one Unicode whitespace "
                    "codepoint, and a positive count; do not combine it with boundary transport."
                )
            else:
                prefix = (
                    _whitespace_runs_text(part["leading_whitespace"])
                    if "leading_whitespace" in part else ""
                )
                suffix = (
                    _whitespace_runs_text(part["trailing_whitespace"])
                    if "trailing_whitespace" in part else ""
                )
                if (
                    isinstance(text, str) and text and text == text.strip()
                    and prefix is not None and suffix is not None
                ):
                    rendered = prefix + text + suffix
                field = (
                    "leading_whitespace" if prefix is None
                    else "trailing_whitespace" if suffix is None else "text"
                )
                message = (
                    "Boundary whitespace transport requires nonempty visible text with no "
                    "edge whitespace and nonempty lists of Unicode whitespace codepoint/count "
                    "runs. Keep these runs on the same part, with its role and field."
                )
            if rendered is None:
                blocker: JsonObject = {
                    "code": "ordered_part_whitespace_transport_invalid",
                    "field": f"semantic_judgments[{judgment_index}].parts[{part_index}].{field}",
                    "message": message,
                }
                source_entry_id = judgment.get("source_entry_id")
                if isinstance(source_entry_id, str) and source_entry_id.strip():
                    blocker["source_entry_id"] = source_entry_id.strip()
                blockers.append(blocker)
            else:
                # Representation only: preserve the part count and semantic ownership.
                part["text"] = rendered
                for key in transport_keys:
                    part.pop(key, None)
            parts.append(part)
        normalized["parts"] = parts
        decoded.append(normalized)
    if not blockers:
        return decoded, None
    return (
        decoded,
        {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "status": "needs_input",
            "feedback": {
                "type": "span_resolution",
                "mechanical": True,
                "semantic_authority": False,
            },
            "checks": [{"name": "whitespace_transport", "result": "needs_input"}],
            "blockers": blockers,
            "failure": {
                "origin": "request",
                "code": "template_whitespace_transport_invalid",
                "retryable": True,
                "message": "Ordered-part whitespace could not be decoded exactly.",
                "suggested_actions": ["revise_whitespace_codepoint_and_count"],
            },
            "warnings": [],
        },
    )


def _attach_resolved_spans(
    judgments: list[JsonObject],
    resolved_spans: list[JsonObject],
) -> list[JsonObject]:
    spans_by_judgment: dict[int, list[JsonObject]] = {}
    for span in resolved_spans:
        judgment_index = span.get("judgment_index")
        if isinstance(judgment_index, int):
            spans_by_judgment.setdefault(judgment_index, []).append(span)
    attached: list[JsonObject] = []
    for index, judgment in enumerate(judgments):
        item = dict(judgment)
        spans = spans_by_judgment.get(index)
        if spans:
            item["resolved_spans"] = [dict(span) for span in spans]
        attached.append(item)
    return attached


def _resolved_spans_from_judgments(judgments: list[JsonObject]) -> list[JsonObject]:
    spans: list[JsonObject] = []
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        raw_spans = judgment.get("resolved_spans")
        if isinstance(raw_spans, list):
            spans.extend(dict(span) for span in raw_spans if isinstance(span, dict))
    return spans


def _ordered_semantic_parts_feedback(
    inventory: JsonObject,
    raw_judgments: list[Any],
) -> JsonObject | None:
    vocabulary = _inventory_field_vocabulary(inventory)
    if vocabulary is None:
        return None
    feedback = validate_ordered_semantic_parts(
        raw_judgments,
        allowed_field_ids=_allowed_vocabulary_field_ids(vocabulary),
        source_entry_ids=_source_entry_ids(inventory),
        field_vocabulary=vocabulary,
    )
    if feedback.get("status") == "ok":
        return None
    return feedback


def _ordered_parts_summary(judgment: JsonObject) -> str:
    raw_parts = judgment.get("parts")
    if not isinstance(raw_parts, list):
        return ""
    summaries: list[str] = []
    for part in raw_parts:
        if not isinstance(part, dict):
            continue
        role = part.get("role")
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            summaries.append(f"{role}: {text.strip()}" if isinstance(role, str) else text.strip())
    return " | ".join(summaries)


def _coverage_judgment_summary(judgment: JsonObject) -> str:
    parts_summary = _ordered_parts_summary(judgment)
    if parts_summary:
        return parts_summary
    raw_judgment = judgment.get("judgment")
    return raw_judgment.strip() if isinstance(raw_judgment, str) else ""


def _source_entry_object_ids_by_id(inventory: JsonObject) -> dict[str, list[str]]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return {}
    result: dict[str, list[str]] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        source_entry_id = entry.get("source_entry_id")
        if not isinstance(source_entry_id, str) or not source_entry_id.strip():
            continue
        object_ids: list[str] = []
        provenance = entry.get("provenance")
        if isinstance(provenance, list):
            for item in provenance:
                if not isinstance(item, dict):
                    continue
                object_id = item.get("object_id")
                if isinstance(object_id, str) and object_id.strip():
                    object_ids.append(object_id.strip())
        result[source_entry_id.strip()] = list(dict.fromkeys(object_ids))
    return result


def _coverage_judgments_from_ordered_parts(
    inventory: JsonObject,
    raw_judgments: list[JsonObject],
) -> list[JsonObject]:
    if _inventory_field_vocabulary(inventory) is None:
        return []
    object_ids_by_source_entry = _source_entry_object_ids_by_id(inventory)
    projected: list[JsonObject] = []
    for index, raw in enumerate(raw_judgments):
        if not isinstance(raw, dict):
            continue
        source_entry_id = _judgment_source_entry_id(raw)
        covered_object_ids = (
            object_ids_by_source_entry.get(source_entry_id, [])
            if source_entry_id is not None
            else []
        )
        projected.append(
            {
                "judgment_ref": f"semantic_judgments[{index}]",
                "judgment": _coverage_judgment_summary(raw),
                "covered_object_ids": list(dict.fromkeys(covered_object_ids)),
            }
        )
    return projected


def _inventory_uses_source_entry_gate(inventory: JsonObject) -> bool:
    return bool(_source_entry_ids(inventory))


def _source_entry_requires_coverage(entry: JsonObject) -> bool:
    return entry.get("coverage_required") is not False


def _source_entry_text_by_id(inventory: JsonObject) -> dict[str, str]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return {}
    result: dict[str, str] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict) or not _source_entry_requires_coverage(entry):
            continue
        source_entry_id = entry.get("source_entry_id")
        text = entry.get("text")
        if isinstance(source_entry_id, str) and source_entry_id.strip() and isinstance(text, str):
            result[source_entry_id.strip()] = text
    return result


def _source_entry_summaries(
    inventory: JsonObject,
    source_entry_ids: list[str],
) -> list[JsonObject]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return [{"source_entry_id": source_entry_id} for source_entry_id in source_entry_ids[:20]]
    by_id = {
        str(entry["source_entry_id"]): entry
        for entry in raw_entries
        if isinstance(entry, dict) and isinstance(entry.get("source_entry_id"), str)
    }
    summaries: list[JsonObject] = []
    for source_entry_id in source_entry_ids[:20]:
        entry = by_id.get(source_entry_id)
        summary: JsonObject = {"source_entry_id": source_entry_id}
        if isinstance(entry, dict):
            text = entry.get("text")
            entry_type = entry.get("entry_type")
            source_order = entry.get("source_order")
            if isinstance(text, str):
                summary["text"] = text[:240]
            if isinstance(entry_type, str):
                summary["entry_type"] = entry_type
            if isinstance(source_order, dict):
                summary["source_order"] = dict(source_order)
        summaries.append(summary)
    return summaries


def _source_entry_spans_from_resolved_span(span: JsonObject) -> list[JsonObject]:
    source_entry_id = span.get("source_entry_id")
    extent = span.get("extent")
    if (
        isinstance(source_entry_id, str)
        and source_entry_id.strip()
        and extent == {"kind": "whole_entry"}
    ):
        return [
            {
                "source_entry_id": source_entry_id.strip(),
                "extent": {"kind": "whole_entry"},
                "span_ref": span.get("span_ref"),
            }
        ]
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
                "span_ref": span.get("span_ref"),
            }
        ]
    raw_spans = span.get("source_entry_spans")
    if isinstance(raw_spans, list):
        return [item for item in raw_spans if isinstance(item, dict)]
    return []


def _source_entry_coverage_feedback(
    inventory: JsonObject,
    resolved_spans: list[JsonObject],
) -> JsonObject:
    text_by_entry = _source_entry_text_by_id(inventory)
    known_ids = list(text_by_entry)
    known_set = set(known_ids)
    coverage = {source_entry_id: [0] * len(text) for source_entry_id, text in text_by_entry.items()}
    structural_coverage = {
        source_entry_id: 0 for source_entry_id, text in text_by_entry.items() if text == ""
    }
    unknown: set[str] = set()
    uncovered_span_refs: list[str] = []

    for span in resolved_spans:
        source_spans = _source_entry_spans_from_resolved_span(span)
        if not source_spans:
            span_ref = span.get("span_ref")
            if isinstance(span_ref, str) and span_ref.strip():
                uncovered_span_refs.append(span_ref.strip())
            continue
        for source_span in source_spans:
            source_entry_id = source_span.get("source_entry_id")
            text_start = source_span.get("text_start")
            text_end = source_span.get("text_end")
            if not isinstance(source_entry_id, str) or not source_entry_id.strip():
                continue
            normalized_id = source_entry_id.strip()
            if normalized_id not in known_set:
                unknown.add(normalized_id)
                continue
            if source_span.get("extent") == {"kind": "whole_entry"}:
                if normalized_id not in structural_coverage:
                    span_ref = span.get("span_ref")
                    if isinstance(span_ref, str) and span_ref.strip():
                        uncovered_span_refs.append(span_ref.strip())
                    continue
                structural_coverage[normalized_id] += 1
                continue
            if (
                not isinstance(text_start, int)
                or isinstance(text_start, bool)
                or not isinstance(text_end, int)
                or isinstance(text_end, bool)
                or text_start < 0
                or text_end <= text_start
                or text_end > len(text_by_entry[normalized_id])
            ):
                span_ref = span.get("span_ref")
                if isinstance(span_ref, str) and span_ref.strip():
                    uncovered_span_refs.append(span_ref.strip())
                continue
            for offset in range(text_start, text_end):
                if text_by_entry[normalized_id][offset].strip():
                    coverage[normalized_id][offset] += 1

    missing = [
        source_entry_id
        for source_entry_id in known_ids
        if (
            structural_coverage.get(source_entry_id) == 0
            if source_entry_id in structural_coverage
            else any(
                character.strip() and coverage[source_entry_id][index] == 0
                for index, character in enumerate(text_by_entry[source_entry_id])
            )
        )
    ]
    overlaps = [
        source_entry_id
        for source_entry_id in known_ids
        if (
            structural_coverage.get(source_entry_id, 0) > 1
            or any(count > 1 for count in coverage[source_entry_id])
        )
    ]

    blockers: list[JsonObject] = []
    suggested_actions: list[str] = []
    if missing:
        blockers.append(
            {
                "code": "missing_source_entry_semantic_judgments",
                "source_entry_ids": missing,
                "source_entries": _source_entry_summaries(inventory, missing),
                "message": "These source entries are not fully covered by semantic judgments.",
            }
        )
        suggested_actions.append("cover_missing_source_entries=" + str(missing[:20]))
    if unknown:
        unknown_ids = sorted(unknown)
        blockers.append(
            {
                "code": "unknown_source_entry_semantic_judgments",
                "source_entry_ids": unknown_ids,
                "source_entries": [
                    {"source_entry_id": source_entry_id} for source_entry_id in unknown_ids[:20]
                ],
                "message": (
                    "These semantic judgments reference source entries outside the inventory."
                ),
            }
        )
        suggested_actions.append("revise_semantic_judgment_source_entry_id_to_current_packet")
    if overlaps:
        blockers.append(
            {
                "code": "overlapping_source_entry_semantic_judgments",
                "source_entry_ids": overlaps,
                "source_entries": _source_entry_summaries(inventory, overlaps),
                "message": "These source entries are covered by overlapping semantic spans.",
            }
        )
        suggested_actions.append(
            "merge_or_split_overlapping_source_entry_judgments=" + str(overlaps[:20])
        )
    if uncovered_span_refs:
        blockers.append(
            {
                "code": "semantic_spans_without_source_entry_coverage",
                "span_refs": sorted(set(uncovered_span_refs)),
                "message": "These resolved spans do not expand to source entry provenance.",
            }
        )
        suggested_actions.append("revise_semantic_judgments_to_source_entry_id_and_parts")
    return {
        "blockers": blockers,
        "suggested_actions": suggested_actions,
    }


def _covered_source_entry_ids_from_spans(
    inventory: JsonObject,
    resolved_spans: list[JsonObject],
) -> set[str]:
    text_by_entry = _source_entry_text_by_id(inventory)
    covered: set[str] = set()
    for span in resolved_spans:
        for source_span in _source_entry_spans_from_resolved_span(span):
            source_entry_id = source_span.get("source_entry_id")
            if (
                isinstance(source_entry_id, str)
                and source_entry_id in text_by_entry
                and text_by_entry[source_entry_id] == ""
                and source_span.get("extent") == {"kind": "whole_entry"}
            ):
                covered.add(source_entry_id)
                continue
            text_start = source_span.get("text_start")
            text_end = source_span.get("text_end")
            if (
                isinstance(source_entry_id, str)
                and source_entry_id in text_by_entry
                and isinstance(text_start, int)
                and isinstance(text_end, int)
                and 0 <= text_start < text_end <= len(text_by_entry[source_entry_id])
            ):
                covered.add(source_entry_id)
    return covered


def _feedback_object_ids(feedback: JsonObject, code: str) -> list[str]:
    blockers = feedback.get("blockers", [])
    if not isinstance(blockers, list):
        return []
    for item in blockers:
        if not isinstance(item, dict) or item.get("code") != code:
            continue
        object_ids = item.get("object_ids", [])
        if isinstance(object_ids, list):
            return [str(object_id) for object_id in object_ids]
    return []


def _feedback_source_entry_ids(feedback: JsonObject, code: str) -> list[str]:
    blockers = feedback.get("blockers", [])
    if not isinstance(blockers, list):
        return []
    for item in blockers:
        if not isinstance(item, dict) or item.get("code") != code:
            continue
        source_entry_ids = item.get("source_entry_ids", [])
        if isinstance(source_entry_ids, list):
            return [str(source_entry_id) for source_entry_id in source_entry_ids]
    return []


class TemplateHarnessService:
    """Task-bound storage for object-level semantic coverage feedback."""

    def __init__(
        self,
        *,
        task_root: Path | None = None,
        office: OfficeCliAdapter | None = None,
    ) -> None:
        self._task_root = (
            task_root.expanduser().resolve(strict=True) if task_root is not None else None
        )
        self._office = office

    @property
    def office(self) -> OfficeCliAdapter:
        if self._office is None:
            self._office = OfficeCliAdapter()
        return self._office

    def _session_root(self, args: dict[str, Any]) -> Path:
        if self._task_root is None:
            return task_root_from_args(args)
        requested = args.get("task_root")
        if requested is not None:
            candidate = task_root_from_args({"task_root": requested})
            if candidate != self._task_root:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="task_root_mismatch",
                    message="task_root does not match the root bound to this application session.",
                )
        return self._task_root

    def handle(self, args: dict[str, Any]) -> JsonObject:
        action = _non_empty_string(args.get("action"), field="action")
        root = self._session_root(args)
        if action == "inspect_objects":
            return self._inspect_objects(root, args)
        if action == "submit_object_inventory":
            return self._submit_object_inventory(root, args)
        if action == "submit_semantic_judgments":
            result = self._submit_semantic_judgments(root, args)
            return result if result.get("status") == "ok" else classify_semantic_feedback(result)
        if action == "status":
            return self._status(root)
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_harness_action_unknown",
            message=(
                "template harness action must be inspect_objects, submit_object_inventory, "
                "submit_semantic_judgments, or status."
            ),
        )

    def _inspect_objects(self, root: Path, args: dict[str, Any]) -> JsonObject:
        raise ToolFailure(
            status="needs_input",
            origin="request",
            code="template_inventory_rebuild_retired",
            message="Use the immutable initial source inventory prepared by App.",
        )

    def _submit_object_inventory(self, root: Path, args: dict[str, Any]) -> JsonObject:
        require_initial_binding(root, args)
        document_sha256 = _document_sha(args.get("document_sha256"))
        raw_objects = _list(args.get("objects"), field="objects")
        if not raw_objects:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_object_inventory_empty",
                message="Submit at least one inspected object before semantic coverage checking.",
            )

        source_entries = _inventory_source_entries(args.get("source_entries"))
        canonical_source_inventory: JsonObject | None = None
        raw_canonical_inventory = args.get("canonical_source_inventory")
        if raw_canonical_inventory is not None:
            try:
                canonical = CanonicalSourceInventory.from_json(raw_canonical_inventory)
            except ValueError as error:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_source_entry_inventory_invalid",
                    message=str(error),
                ) from error
            if canonical.source_snapshot_sha256 != document_sha256:
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_source_entry_inventory_invalid",
                    message="Canonical source inventory belongs to another source snapshot.",
                )
            canonical_ids = {entry.source_entry_id for entry in canonical.source_entries}
            if any(str(entry["source_entry_id"]) not in canonical_ids for entry in source_entries):
                raise ToolFailure(
                    status="needs_input",
                    origin="request",
                    code="template_source_entry_inventory_invalid",
                    message="Projected source entries must come from the canonical inventory.",
                )
            canonical_source_inventory = canonical.to_json()
        known_source_entry_ids = {
            str(item["source_entry_id"]) for item in source_entries if "source_entry_id" in item
        }
        objects = [
            _inventory_object(
                raw,
                index=index,
                document_sha256=document_sha256,
                canonical_source_entry_ids=known_source_entry_ids if source_entries else None,
            )
            for index, raw in enumerate(raw_objects)
        ]
        raw_reading_blocks = args.get("reading_blocks", [])
        if raw_reading_blocks is None:
            raw_reading_blocks = []
        if not isinstance(raw_reading_blocks, list):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_harness_argument_invalid",
                message="reading_blocks must be an array when supplied.",
            )
        reading_blocks = [
            _inventory_reading_block(raw, index=index)
            for index, raw in enumerate(raw_reading_blocks)
        ]
        reading_source_entry_ids = {
            source_entry_id
            for block in reading_blocks
            for source_entry_id in block.get("covered_source_entry_ids", [])
            if isinstance(source_entry_id, str)
        }
        unknown_reading_source_entries = sorted(reading_source_entry_ids - known_source_entry_ids)
        if unknown_reading_source_entries:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_source_entry_inventory_unknown",
                message=("Each reading view source_entry_id must be declared in source_entries."),
                suggested_actions=(
                    f"unknown_source_entry_ids={unknown_reading_source_entries[:20]}",
                ),
            )
        counts = Counter(str(item["object_id"]) for item in objects)
        duplicates = sorted(object_id for object_id, count in counts.items() if count > 1)
        if duplicates:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_object_inventory_duplicate",
                message="Each inspected object may appear only once in the harness inventory.",
                suggested_actions=(f"duplicate_object_ids={duplicates[:20]}",),
            )
        source_entry_counts = Counter(
            str(item["source_entry_id"])
            for item in objects
            if isinstance(item.get("source_entry_id"), str)
        )
        unknown_canonical_entries = sorted(
            source_entry_id
            for source_entry_id in source_entry_counts
            if source_entries and source_entry_id not in known_source_entry_ids
        )
        if unknown_canonical_entries:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_source_entry_inventory_unknown",
                message=(
                    "Each object source_entry_id must be declared in source_entries "
                    "when canonical source entries are submitted."
                ),
                suggested_actions=(f"unknown_source_entry_ids={unknown_canonical_entries[:20]}",),
            )
        duplicate_source_entries = sorted(
            source_entry_id for source_entry_id, count in source_entry_counts.items() if count > 1
        )
        if duplicate_source_entries and not source_entries:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_source_entry_inventory_duplicate",
                message="Each source DOC component may appear only once in the source inventory.",
                suggested_actions=(f"duplicate_source_entry_ids={duplicate_source_entries[:20]}",),
            )
        _require_reading_block_text_span_object_closure(
            reading_blocks,
            objects=objects,
        )

        return self._store_inventory(
            root,
            document_sha256=document_sha256,
            objects=objects,
            reading_blocks=reading_blocks,
            source_entries=source_entries,
            canonical_source_inventory=canonical_source_inventory,
            unit_boundary_proof=args.get("unit_boundary_proof"),
            unit_reading_packets=(
                dict(args["unit_reading_packets"])
                if isinstance(args.get("unit_reading_packets"), dict)
                else None
            ),
            unit_projection_digest=(
                str(args["unit_projection_digest"])
                if isinstance(args.get("unit_projection_digest"), str)
                else None
            ),
            source="submit_object_inventory",
        )

    def _store_inventory(
        self,
        root: Path,
        *,
        document_sha256: str,
        objects: list[JsonObject],
        source: str,
        reading_blocks: list[JsonObject] | None = None,
        source_entries: list[JsonObject] | None = None,
        canonical_source_inventory: JsonObject | None = None,
        unit_boundary_proof: JsonObject | None = None,
        unit_reading_packets: dict[str, JsonObject] | None = None,
        unit_projection_digest: str | None = None,
    ) -> JsonObject:
        field_vocabulary = _task_field_vocabulary(root)
        inventory = {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "source": source,
            "document_sha256": document_sha256,
            "object_count": len(objects),
            "objects": objects,
            "unit_boundary_proof": unit_boundary_proof,
            "source_entry_count": len(source_entries or []),
            "source_entries": list(source_entries or []),
            **(
                {"canonical_source_inventory": canonical_source_inventory}
                if canonical_source_inventory is not None
                else {}
            ),
            **(
                {"unit_reading_packets": unit_reading_packets}
                if unit_reading_packets is not None
                else {}
            ),
            **(
                {"unit_projection_digest": unit_projection_digest}
                if unit_projection_digest is not None
                else {}
            ),
            "reading_block_count": len(reading_blocks or []),
            "reading_blocks": list(reading_blocks or []),
            "field_id_vocabulary": field_vocabulary,
            "field_vocabulary_digest": field_vocabulary["digest"],
        }
        (root / HARNESS_DIR).mkdir(parents=True, exist_ok=True)
        atomic_write_json(root / OBJECT_INVENTORY_PATH, inventory)
        if (root / SEMANTIC_JUDGMENTS_PATH).exists():
            (root / SEMANTIC_JUDGMENTS_PATH).unlink()
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "status": "ok",
            "object_inventory_path": OBJECT_INVENTORY_PATH.as_posix(),
            "source": source,
            "harness_state": self._state(root),
            "checks": [{"name": "object_inventory_unique", "result": "ok"}],
            "warnings": [],
            "failure": None,
        }

    def _submit_semantic_judgments(self, root: Path, args: dict[str, Any]) -> JsonObject:
        inventory = self._read_inventory(root)
        requested_sha = args.get("document_sha256")
        if (
            requested_sha is not None
            and _document_sha(requested_sha) != inventory["document_sha256"]
        ):
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_judgment_document_mismatch",
                message=(
                    "semantic_judgments must belong to the submitted object inventory snapshot."
                ),
            )
        raw_judgments = _list(args.get("semantic_judgments"), field="semantic_judgments")
        if _inventory_field_vocabulary(inventory) is None:
            vocabulary_feedback = _field_vocabulary_required_feedback()
            vocabulary_feedback["harness_state"] = self._state(root)
            return vocabulary_feedback
        decoded_judgments, whitespace_feedback = _decode_semantic_parts(inventory, raw_judgments)
        if whitespace_feedback is not None:
            whitespace_feedback["harness_state"] = self._state(root)
            return whitespace_feedback
        ordered_feedback = _ordered_semantic_parts_feedback(inventory, decoded_judgments)
        if ordered_feedback is not None:
            ordered_feedback["harness_state"] = self._state(root)
            return ordered_feedback
        if not _inventory_uses_source_entry_gate(inventory):
            raise ToolFailure(
                status="needs_input",
                origin="harness",
                code="template_source_entry_inventory_required",
                message=(
                    "Post-unit semantic review requires the canonical source inventory; "
                    "object-only coverage is not accepted."
                ),
            )
        accepted_source_judgments = [
            dict(raw) for raw in decoded_judgments if isinstance(raw, dict)
        ]
        coverage_judgments = _coverage_judgments_from_ordered_parts(
            inventory,
            accepted_source_judgments,
        )
        resolved_spans, span_feedback = _resolve_ordered_span_refs(
            inventory,
            accepted_source_judgments,
        )
        if span_feedback is not None:
            span_feedback["harness_state"] = self._state(
                root,
                draft_judgments=coverage_judgments,
            )
            return span_feedback
        feedback = _source_entry_coverage_feedback(inventory, resolved_spans)
        coverage_message = (
            "Every canonical source entry must be covered by non-overlapping semantic "
            "spans, and each accepted span must expand to provenance."
        )
        if feedback["blockers"]:
            return {
                "schema_version": HARNESS_SCHEMA_VERSION,
                "status": "needs_input",
                "feedback": _coverage_feedback_metadata(),
                "harness_state": self._state(
                    root,
                    draft_judgments=coverage_judgments,
                    resolved_spans=resolved_spans,
                ),
                "checks": [{"name": "semantic_judgment_coverage", "result": "needs_input"}],
                "blockers": feedback["blockers"],
                "failure": {
                    "origin": "request",
                    "code": "template_semantic_judgment_coverage_incomplete",
                    "retryable": True,
                    "message": coverage_message,
                    "suggested_actions": feedback["suggested_actions"],
                },
                "warnings": [],
            }
        accepted_judgments = _attach_resolved_spans(
            accepted_source_judgments,
            resolved_spans,
        )
        harness_state = self._state(
            root,
            draft_judgments=coverage_judgments,
            resolved_spans=resolved_spans,
        )
        stored = {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "source_inventory_digest": inventory["canonical_source_inventory"]["inventory_digest"],
            "unit_projection_digest": inventory["unit_projection_digest"],
            "semantic_judgments_sha256": sha256_json(accepted_judgments),
            "document_sha256": inventory["document_sha256"],
            "judgment_count": len(accepted_judgments),
            "covered_object_count": harness_state["covered_object_count"],
            "semantic_judgments": accepted_judgments,
        }
        covered_source_entry_count = harness_state.get("covered_source_entry_count")
        if isinstance(covered_source_entry_count, int):
            stored["covered_source_entry_count"] = covered_source_entry_count
        if resolved_spans:
            stored["resolved_spans"] = resolved_spans
        field_vocabulary = inventory.get("field_id_vocabulary")
        field_vocabulary_digest = inventory.get("field_vocabulary_digest")
        if isinstance(field_vocabulary, dict) and isinstance(field_vocabulary_digest, str):
            stored["field_id_vocabulary"] = field_vocabulary
            stored["field_vocabulary_digest"] = field_vocabulary_digest
        (root / HARNESS_DIR).mkdir(parents=True, exist_ok=True)
        atomic_write_json(root / SEMANTIC_JUDGMENTS_PATH, stored)
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "status": "ok",
            "semantic_judgments_path": SEMANTIC_JUDGMENTS_PATH.as_posix(),
            "harness_state": harness_state,
            "checks": [{"name": "semantic_judgment_coverage", "result": "ok"}],
            "warnings": [],
            "failure": None,
        }

    def _status(self, root: Path) -> JsonObject:
        state = self._state(root)
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "status": "ok",
            "harness_state": state,
            "checks": [
                {
                    "name": "semantic_judgment_coverage",
                    "result": (
                        "ok"
                        if state.get("all_objects_have_semantic_judgment") is True
                        else "needs_input"
                    ),
                }
            ],
            "warnings": [],
            "failure": None,
        }

    def _read_inventory(self, root: Path) -> JsonObject:
        try:
            inventory = _json_object(
                json.loads((root / OBJECT_INVENTORY_PATH).read_text(encoding="utf-8")),
                field="object_inventory",
            )
            require_initial_binding(root, inventory)
            return inventory
        except (OSError, ValueError) as error:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_object_inventory_missing",
                message="Submit an object inventory before submitting semantic judgments.",
            ) from error

    def _read_judgments(self, root: Path) -> list[JsonObject]:
        try:
            value = _json_object(
                json.loads((root / SEMANTIC_JUDGMENTS_PATH).read_text(encoding="utf-8")),
                field="semantic_judgments",
            )
        except (OSError, ValueError):
            return []
        judgments = value.get("semantic_judgments")
        return judgments if isinstance(judgments, list) else []

    def _coverage_feedback(
        self,
        inventory: JsonObject,
        judgments: list[JsonObject],
    ) -> JsonObject:
        known = [str(item["object_id"]) for item in inventory.get("objects", [])]
        known_set = set(known)
        inventory_objects = {
            str(item["object_id"]): item
            for item in inventory.get("objects", [])
            if isinstance(item, dict) and "object_id" in item
        }
        reading_blocks = [
            item
            for item in inventory.get("reading_blocks", [])
            if isinstance(item, dict) and isinstance(item.get("block_id"), str)
        ]

        def object_summaries(object_ids: list[str]) -> list[JsonObject]:
            summaries: list[JsonObject] = []
            for object_id in object_ids[:20]:
                item = inventory_objects.get(object_id)
                summary: JsonObject = {"object_id": object_id}
                if isinstance(item, dict):
                    object_type = item.get("type")
                    locator = item.get("locator")
                    if isinstance(object_type, str):
                        summary["type"] = object_type
                    if isinstance(locator, str):
                        summary["locator"] = locator
                summaries.append(summary)
            return summaries

        def reading_block_summaries(object_ids: list[str]) -> list[JsonObject]:
            wanted = set(object_ids)
            summaries: list[JsonObject] = []
            for block in reading_blocks:
                raw_ids = block.get("covered_object_ids", [])
                if not isinstance(raw_ids, list) or not wanted.intersection(
                    str(item) for item in raw_ids if isinstance(item, str)
                ):
                    continue
                summary: JsonObject = {"block_id": str(block["block_id"])}
                for key in ("range_id", "unit_range_id"):
                    value = block.get(key)
                    if isinstance(value, str) and value.strip():
                        summary[key] = value.strip()
                unit_id = block.get("unit_id")
                if isinstance(unit_id, str):
                    summary["unit_id"] = unit_id
                text = block.get("text")
                if isinstance(text, str):
                    summary["text"] = text[:240]
                summaries.append(summary)
            return summaries[:20]

        covered_ids = [
            str(object_id) for item in judgments for object_id in item.get("covered_object_ids", [])
        ]
        covered_counts = Counter(covered_ids)
        overlaps = sorted(
            object_id
            for object_id, count in covered_counts.items()
            if object_id in known_set and count > 1
        )
        covered_set = set(covered_ids)
        missing = [object_id for object_id in known if object_id not in covered_set]
        unknown = sorted(object_id for object_id in covered_set if object_id not in known_set)
        empty = sorted(
            {
                str(object_id)
                for item in judgments
                for object_id in item.get("covered_object_ids", [])
                if not isinstance(item.get("judgment"), str) or not item["judgment"].strip()
            }
        )
        uncovered_judgments = sorted(
            str(item.get("judgment_ref", ""))
            for item in judgments
            if not item.get("covered_object_ids")
        )
        blockers: list[JsonObject] = []
        suggested_actions: list[str] = []
        if missing:
            missing_reading_blocks = reading_block_summaries(missing)
            missing_block_ids = [
                item["block_id"]
                for item in missing_reading_blocks
                if isinstance(item.get("block_id"), str)
            ]
            blockers.append(
                {
                    "code": "missing_semantic_judgments",
                    "object_ids": missing,
                    "objects": object_summaries(missing),
                    **(
                        {"reading_blocks": missing_reading_blocks} if missing_reading_blocks else {}
                    ),
                    "message": "These inventory objects are not covered by any semantic judgment.",
                }
            )
            if missing_reading_blocks:
                suggested_actions.append("cover_missing_reading_blocks=" + str(missing_block_ids))
            else:
                suggested_actions.append(
                    "rebuild_reading_packet_for_unmapped_semantic_source_ranges"
                )
        if unknown:
            blockers.append(
                {
                    "code": "unknown_judgment_objects",
                    "object_ids": unknown,
                    "objects": [{"object_id": object_id} for object_id in unknown[:20]],
                    "message": "These semantic judgments cover objects outside the inventory.",
                }
            )
            suggested_actions.append("revise_semantic_judgment_scope_to_current_reading_packet")
        if overlaps:
            overlap_reading_blocks = reading_block_summaries(overlaps)
            overlap_block_ids = [
                item["block_id"]
                for item in overlap_reading_blocks
                if isinstance(item.get("block_id"), str)
            ]
            blockers.append(
                {
                    "code": "overlapping_semantic_judgments",
                    "object_ids": overlaps,
                    "objects": object_summaries(overlaps),
                    **(
                        {"reading_blocks": overlap_reading_blocks} if overlap_reading_blocks else {}
                    ),
                    "message": (
                        "These inventory objects are covered by more than one semantic judgment."
                    ),
                }
            )
            if overlap_block_ids:
                suggested_actions.append(
                    "merge_or_split_overlapping_reading_blocks=" + str(overlap_block_ids)
                )
            else:
                suggested_actions.append(
                    "merge_or_split_overlapping_semantic_scopes_in_current_reading_packet"
                )
        if empty:
            empty_reading_blocks = reading_block_summaries(empty)
            empty_block_ids = [
                item["block_id"]
                for item in empty_reading_blocks
                if isinstance(item.get("block_id"), str)
            ]
            blockers.append(
                {
                    "code": "empty_semantic_judgments",
                    "object_ids": empty,
                    "objects": object_summaries(empty),
                    **({"reading_blocks": empty_reading_blocks} if empty_reading_blocks else {}),
                    "message": "These inventory objects are covered by an empty semantic judgment.",
                }
            )
            if empty_block_ids:
                suggested_actions.append(
                    "fill_empty_semantic_judgments_for_reading_blocks=" + str(empty_block_ids)
                )
            else:
                suggested_actions.append("fill_empty_semantic_judgments_in_current_reading_packet")
        if uncovered_judgments:
            blockers.append(
                {
                    "code": "semantic_judgments_without_coverage",
                    "judgment_refs": uncovered_judgments,
                    "message": "These semantic judgments do not cover any inventory object.",
                }
            )
            suggested_actions.append("revise_scope_to_current_reading_packet")
        return {
            "blockers": blockers,
            "suggested_actions": suggested_actions,
        }

    def _state(
        self,
        root: Path,
        *,
        draft_judgments: list[JsonObject] | None = None,
        resolved_spans: list[JsonObject] | None = None,
    ) -> JsonObject:
        inventory_path = root / OBJECT_INVENTORY_PATH
        if not inventory_path.exists():
            return {
                "object_inventory_submitted": False,
                "object_count": 0,
                "covered_object_count": 0,
                "source_entry_count": 0,
                "covered_source_entry_count": 0,
                "missing_semantic_judgment_object_ids": [],
                "unknown_judgment_object_ids": [],
                "overlap_object_ids": [],
                "missing_source_entry_ids": [],
                "unknown_source_entry_ids": [],
                "overlap_source_entry_ids": [],
                "empty_judgment_object_ids": [],
                "uncovered_judgment_refs": [],
                "all_objects_have_semantic_judgment": False,
                "all_objects_have_semantic_coverage": False,
                "all_source_entries_have_semantic_coverage": False,
            }
        inventory = self._read_inventory(root)
        judgments = draft_judgments if draft_judgments is not None else self._read_judgments(root)
        coverage_judgments = _coverage_judgments_from_ordered_parts(inventory, judgments)
        feedback = self._coverage_feedback(inventory, coverage_judgments)
        source_entry_gate = _inventory_uses_source_entry_gate(inventory)
        current_resolved_spans = (
            resolved_spans
            if resolved_spans is not None
            else _resolved_spans_from_judgments(judgments)
        )
        source_feedback = (
            _source_entry_coverage_feedback(inventory, current_resolved_spans)
            if source_entry_gate
            else {"blockers": [], "suggested_actions": []}
        )
        missing = _feedback_object_ids(feedback, "missing_semantic_judgments")
        unknown = _feedback_object_ids(feedback, "unknown_judgment_objects")
        overlaps = _feedback_object_ids(feedback, "overlapping_semantic_judgments")
        missing_source_entries = _feedback_source_entry_ids(
            source_feedback,
            "missing_source_entry_semantic_judgments",
        )
        unknown_source_entries = _feedback_source_entry_ids(
            source_feedback,
            "unknown_source_entry_semantic_judgments",
        )
        overlap_source_entries = _feedback_source_entry_ids(
            source_feedback,
            "overlapping_source_entry_semantic_judgments",
        )
        empty = _feedback_object_ids(feedback, "empty_semantic_judgments")
        known_ids = {str(item["object_id"]) for item in inventory.get("objects", [])}
        valid_covered_ids = {
            str(object_id)
            for span in current_resolved_spans
            for object_id in span.get("covered_object_ids", [])
            if str(object_id) in known_ids
        }
        blockers = feedback.get("blockers", [])
        uncovered_judgment_refs: list[str] = []
        if isinstance(blockers, list):
            for blocker in blockers:
                if (
                    isinstance(blocker, dict)
                    and blocker.get("code") == "semantic_judgments_without_coverage"
                ):
                    raw_refs = blocker.get("judgment_refs", [])
                    if isinstance(raw_refs, list):
                        uncovered_judgment_refs = [str(item) for item in raw_refs]
        return {
            "object_inventory_submitted": True,
            "object_count": int(inventory.get("object_count", 0)),
            "covered_object_count": len(valid_covered_ids),
            "source_entry_count": len(_source_entry_text_by_id(inventory)),
            "covered_source_entry_count": len(
                _covered_source_entry_ids_from_spans(inventory, current_resolved_spans)
            ),
            "missing_semantic_judgment_object_ids": missing,
            "unknown_judgment_object_ids": unknown,
            "overlap_object_ids": overlaps,
            "missing_source_entry_ids": missing_source_entries,
            "unknown_source_entry_ids": unknown_source_entries,
            "overlap_source_entry_ids": overlap_source_entries,
            "empty_judgment_object_ids": empty,
            "uncovered_judgment_refs": uncovered_judgment_refs,
            "all_objects_have_semantic_judgment": source_entry_gate
            and not source_feedback["blockers"],
            "all_objects_have_semantic_coverage": source_entry_gate
            and not source_feedback["blockers"],
            "all_source_entries_have_semantic_coverage": not source_feedback["blockers"]
            if source_entry_gate
            else False,
        }
