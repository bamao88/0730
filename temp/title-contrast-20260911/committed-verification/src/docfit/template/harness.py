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
    validate_ordered_semantic_parts,
)
from docfit.template.source_entries import (
    OBJECT_ID_BACKEND_ALIAS_ROLE,
    CanonicalSourceInventory,
    validate_canonical_source_entries,
)
from docfit.tools.inspection import (
    inspect_document_snapshot,
)
from docfit.tools.officecli import OfficeCliAdapter
from docfit.tools.runtime import (
    JsonObject,
    ToolFailure,
    atomic_write_json,
    authorized_path,
    require_docx,
    sha256_json,
    task_root_from_args,
)

HARNESS_SCHEMA_VERSION = 2
HARNESS_DIR = Path("work/.docfit/harness")
OBJECT_INVENTORY_PATH = HARNESS_DIR / "object-inventory.json"
SOURCE_INVENTORY_PATH = HARNESS_DIR / "source-inventory.json"
SEMANTIC_JUDGMENTS_PATH = HARNESS_DIR / "semantic-judgments.json"
COVERAGE_SELECTOR = "run, table, picture, sdt, shape"
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
                        f"{field}[{index}].text must match the referenced reading block "
                        "text slice."
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
            message=(
                f"{field} must cover every non-whitespace character in reading_blocks text."
            ),
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
            source_entry_ref.get("provenance")
            if isinstance(source_entry_ref, dict)
            else None
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


def _locator(value: Any, *, field: str) -> str:
    if isinstance(value, str):
        return _non_empty_string(value, field=field)
    if isinstance(value, dict):
        for key in ("locator", "path"):
            if isinstance(value.get(key), str):
                return _non_empty_string(value[key], field=f"{field}.{key}")
        if isinstance(value.get("object"), dict):
            return _locator(value["object"], field=f"{field}.object")
    raise ToolFailure(
        status="needs_input",
        origin="request",
        code="template_harness_argument_invalid",
        message=f"{field} must identify an object locator.",
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
    stored: JsonObject = {
        "block_id": block_id,
        "covered_object_ids": list(dict.fromkeys(object_ids)),
    }
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
    if block_text and stored["covered_object_ids"] and not object_text_spans:
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


def _unit_boundary(raw: Any, *, index: int) -> JsonObject:
    item = _json_object(raw, field=f"units[{index}]")
    unit_id = _non_empty_string(item.get("unit_id"), field=f"units[{index}].unit_id")
    return {
        **item,
        "unit_id": unit_id,
        "start_locator": _locator(item.get("start_locator"), field=f"units[{index}].start_locator"),
        "end_locator": _locator(item.get("end_locator"), field=f"units[{index}].end_locator"),
    }


def _document_path(args: dict[str, Any], root: Path) -> Path:
    path = authorized_path(args.get("input_docx"), task_root=root, field="input_docx")
    require_docx(path, field="input_docx")
    return path


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
                "Semantic judgments cannot be accepted without the task input field "
                "vocabulary."
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


def _reading_block_ids(inventory: JsonObject) -> tuple[str, ...]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return ()
    return tuple(
        str(item["block_id"]).strip()
        for item in raw_blocks
        if isinstance(item, dict)
        and isinstance(item.get("block_id"), str)
        and item["block_id"].strip()
    )


def _reading_range_ids(inventory: JsonObject) -> tuple[str, ...]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return ()
    return tuple(
        dict.fromkeys(
            range_id
            for item in raw_blocks
            if isinstance(item, dict)
            for range_id in _reading_range_ids_for_block(item)
        )
    )


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


def _reading_range_ids_for_block(block: JsonObject) -> tuple[str, ...]:
    ids: list[str] = []
    for key in ("range_id", "unit_range_id"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
    return tuple(dict.fromkeys(ids))


def _reading_scope_by_ref(inventory: JsonObject) -> dict[str, JsonObject]:
    scopes = _source_entry_scope_by_ref(inventory)
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return scopes
    source_entry_by_object_id = (
        _source_entry_id_by_object_id(inventory)
        if _inventory_uses_source_entry_gate(inventory)
        else {}
    )
    blocks_by_range: dict[str, list[JsonObject]] = {}
    for item in raw_blocks:
        if not isinstance(item, dict):
            continue
        block_id = item.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            scopes[f"reading_block_id:{block_id.strip()}"] = _reading_scope_from_blocks(
                (item,),
                source_entry_by_object_id=source_entry_by_object_id,
            )
        for range_id in _reading_range_ids_for_block(item):
            blocks_by_range.setdefault(range_id, []).append(item)
    for range_id, blocks in blocks_by_range.items():
        scopes[f"reading_range_id:{range_id}"] = _reading_scope_from_blocks(
            tuple(blocks),
            source_entry_by_object_id=source_entry_by_object_id,
        )
    return scopes


def _source_entry_id_by_object_id(inventory: JsonObject) -> dict[str, str]:
    result: dict[str, str] = {}
    objects = inventory.get("objects")
    if not isinstance(objects, list):
        return result
    for item in objects:
        if not isinstance(item, dict):
            continue
        object_id = item.get("object_id")
        source_entry_id = item.get("source_entry_id")
        if (
            isinstance(object_id, str)
            and object_id.strip()
            and isinstance(source_entry_id, str)
            and source_entry_id.strip()
        ):
            result[object_id.strip()] = source_entry_id.strip()
    return result


def _source_entry_scope_by_ref(inventory: JsonObject) -> dict[str, JsonObject]:
    raw_entries = inventory.get("source_entries")
    if not isinstance(raw_entries, list):
        return {}
    scopes: dict[str, JsonObject] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        source_entry_id = entry.get("source_entry_id")
        text = entry.get("text")
        if not isinstance(source_entry_id, str) or not source_entry_id.strip():
            continue
        if not isinstance(text, str):
            continue
        scopes[f"source_entry_id:{source_entry_id.strip()}"] = {
            "text": text,
            "source_entry_id": source_entry_id.strip(),
            "segments": _source_entry_text_segments(entry, entry_text=text),
        }
    return scopes


def _source_entry_text_segments(entry: JsonObject, *, entry_text: str) -> list[JsonObject]:
    raw_provenance = entry.get("provenance")
    if not isinstance(raw_provenance, list):
        return []
    segments: list[JsonObject] = []
    source_entry_id = entry.get("source_entry_id")
    for raw_span in raw_provenance:
        if not isinstance(raw_span, dict):
            continue
        object_id = raw_span.get("object_id")
        text_span = raw_span.get("text_span")
        if (
            not isinstance(source_entry_id, str)
            or not source_entry_id.strip()
            or not isinstance(object_id, str)
            or not object_id.strip()
            or not isinstance(text_span, list | tuple)
            or len(text_span) != 2
        ):
            continue
        text_start, text_end = text_span
        if (
            not isinstance(text_start, int)
            or isinstance(text_start, bool)
            or not isinstance(text_end, int)
            or isinstance(text_end, bool)
            or text_start < 0
            or text_end <= text_start
            or text_end > len(entry_text)
        ):
            continue
        segments.append(
            {
                "text_start": text_start,
                "text_end": text_end,
                "source_entry_id": source_entry_id.strip(),
                "covered_object_ids": [object_id.strip()],
                "mapping_precision": "source_entry_provenance",
            }
        )
    return segments


def _reading_scope_from_blocks(
    blocks: tuple[JsonObject, ...],
    *,
    source_entry_by_object_id: dict[str, str] | None = None,
) -> JsonObject:
    parts: list[str] = []
    segments: list[JsonObject] = []
    covered_object_ids: list[str] = []
    cursor = 0
    for index, block in enumerate(blocks):
        if index:
            parts.append("\n")
            cursor += 1
        text = block.get("text")
        block_text = text if isinstance(text, str) else ""
        start = cursor
        end = start + len(block_text)
        raw_object_ids = block.get("covered_object_ids")
        block_object_ids = (
            [item for item in raw_object_ids if isinstance(item, str)]
            if isinstance(raw_object_ids, list)
            else []
        )
        block_id = block.get("block_id")
        normalized_block_id = block_id.strip() if isinstance(block_id, str) else ""
        segments.extend(
            _reading_block_text_segments(
                block,
                block_start=start,
                block_end=end,
                block_id=normalized_block_id,
                source_entry_by_object_id=source_entry_by_object_id or {},
            )
        )
        covered_object_ids.extend(block_object_ids)
        parts.append(block_text)
        cursor = end
    return {
        "text": "".join(parts),
        "covered_object_ids": list(dict.fromkeys(covered_object_ids)),
        "segments": segments,
    }


def _reading_block_text_segments(
    block: JsonObject,
    *,
    block_start: int,
    block_end: int,
    block_id: str,
    source_entry_by_object_id: dict[str, str],
) -> list[JsonObject]:
    raw_spans = block.get("object_text_spans")
    if isinstance(raw_spans, list):
        segments: list[JsonObject] = []
        for raw_span in raw_spans:
            if not isinstance(raw_span, dict):
                continue
            object_id = raw_span.get("object_id")
            text_start = raw_span.get("text_start")
            text_end = raw_span.get("text_end")
            if (
                not isinstance(object_id, str)
                or not object_id.strip()
                or not isinstance(text_start, int)
                or isinstance(text_start, bool)
                or not isinstance(text_end, int)
                or isinstance(text_end, bool)
            ):
                continue
            if text_start < 0 or text_end <= text_start or block_start + text_end > block_end:
                continue
            segment: JsonObject = {
                "text_start": block_start + text_start,
                "text_end": block_start + text_end,
                "covered_object_ids": [object_id.strip()],
                "mapping_precision": "object_text_span",
            }
            source_entry_id = source_entry_by_object_id.get(object_id.strip())
            if source_entry_id is not None:
                segment["source_entry_id"] = source_entry_id
                segment["source_entry_text_start"] = text_start
                segment["source_entry_text_end"] = text_end
            if block_id:
                segment["block_id"] = block_id
            segments.append(segment)
        if segments:
            return segments
    return []


def _span_text_segments(
    reading_scope: JsonObject,
    *,
    start: int,
    end: int,
) -> list[JsonObject]:
    raw_segments = reading_scope.get("segments")
    if not isinstance(raw_segments, list):
        return []
    segments: list[JsonObject] = []
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        segment_start = segment.get("text_start")
        segment_end = segment.get("text_end")
        if not isinstance(segment_start, int) or not isinstance(segment_end, int):
            continue
        if isinstance(segment_start, bool) or isinstance(segment_end, bool):
            continue
        if segment_end <= start or segment_start >= end:
            continue
        segments.append(segment)
    return segments


def _segment_object_ids(segment: JsonObject) -> list[str]:
    raw_object_ids = segment.get("covered_object_ids")
    if not isinstance(raw_object_ids, list):
        return []
    return list(
        dict.fromkeys(
            item.strip() for item in raw_object_ids if isinstance(item, str) and item.strip()
        )
    )


def _span_covered_segments(
    reading_scope: JsonObject,
    *,
    start: int,
    end: int,
) -> tuple[list[str], list[str]]:
    block_ids: list[str] = []
    object_ids: list[str] = []
    for segment in _span_text_segments(reading_scope, start=start, end=end):
        block_id = segment.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            block_ids.append(block_id.strip())
        object_ids.extend(_segment_object_ids(segment))
    return (list(dict.fromkeys(block_ids)), list(dict.fromkeys(object_ids)))


def _span_covered_source_entry_spans(
    reading_scope: JsonObject,
    *,
    start: int,
    end: int,
) -> list[JsonObject]:
    spans: list[JsonObject] = []
    for segment in _span_text_segments(reading_scope, start=start, end=end):
        source_entry_id = segment.get("source_entry_id")
        segment_start = segment.get("text_start")
        segment_end = segment.get("text_end")
        entry_start = segment.get("source_entry_text_start")
        entry_end = segment.get("source_entry_text_end")
        if (
            not isinstance(source_entry_id, str)
            or not source_entry_id.strip()
            or not isinstance(segment_start, int)
            or not isinstance(segment_end, int)
            or not isinstance(entry_start, int)
            or not isinstance(entry_end, int)
        ):
            continue
        overlap_start = max(start, segment_start)
        overlap_end = min(end, segment_end)
        if overlap_end <= overlap_start:
            continue
        local_start = entry_start + (overlap_start - segment_start)
        local_end = entry_start + (overlap_end - segment_start)
        if local_start < entry_start or local_end > entry_end:
            continue
        spans.append(
            {
                "source_entry_id": source_entry_id.strip(),
                "text_start": local_start,
                "text_end": local_end,
            }
        )
    return spans


def _unmapped_span_text(
    reading_scope: JsonObject,
    segments: list[JsonObject],
    *,
    start: int,
    end: int,
) -> str:
    text = reading_scope.get("text")
    if not isinstance(text, str):
        return ""
    mapped = [False] * max(0, end - start)
    for segment in segments:
        segment_start = segment.get("text_start")
        segment_end = segment.get("text_end")
        if not isinstance(segment_start, int) or not isinstance(segment_end, int):
            continue
        overlap_start = max(start, segment_start)
        overlap_end = min(end, segment_end)
        for offset in range(overlap_start, overlap_end):
            mapped[offset - start] = True
    chars = [
        text[start + offset]
        for offset, is_mapped in enumerate(mapped)
        if not is_mapped and text[start + offset].strip()
    ]
    return "".join(chars[:80])


def _span_mapping_blockers(
    reading_scope: JsonObject,
    *,
    start: int,
    end: int,
    field: str,
    scope: JsonObject,
    submitted_text: str,
) -> list[JsonObject]:
    segments = _span_text_segments(reading_scope, start=start, end=end)
    if not segments:
        return [
            {
                "code": "ordered_part_span_unmapped",
                "field": field,
                "scope": scope,
                "submitted_text": submitted_text,
                "message": (
                    "Harness could not map this ordered part to any source text segment "
                    "inside the scoped reading block or range."
                ),
            }
        ]
    unmapped = _unmapped_span_text(reading_scope, segments, start=start, end=end)
    if unmapped:
        return [
            {
                "code": "ordered_part_span_unmapped",
                "field": field,
                "scope": scope,
                "submitted_text": submitted_text,
                "unmapped_text": unmapped,
                "message": (
                    "Harness could not map every non-whitespace character in this "
                    "ordered part to a source text segment."
                ),
            }
        ]
    return []


def _judgment_scope_key(judgment: JsonObject) -> tuple[str, str] | None:
    source_entry_id = judgment.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        return ("source_entry_id", source_entry_id.strip())
    scope = judgment.get("scope")
    if not isinstance(scope, dict):
        return None
    reading_block_id = scope.get("reading_block_id")
    if isinstance(reading_block_id, str) and reading_block_id.strip():
        return ("reading_block_id", reading_block_id.strip())
    reading_range_id = scope.get("reading_range_id")
    if isinstance(reading_range_id, str) and reading_range_id.strip():
        return ("reading_range_id", reading_range_id.strip())
    return None


def _span_ref(scope_kind: str, scope_id: str, part_index: int) -> str:
    return f"{scope_kind}={scope_id};part_index={part_index}"


def _slot_ref(span_ref: str, field_id: str) -> str:
    return f"{span_ref};field_id={field_id}"


def _text_excerpt(value: str, *, start: int = 0, limit: int = 500) -> str:
    bounded_start = max(0, min(start, len(value)))
    return value[bounded_start : bounded_start + limit]


def _ordered_part_gap_is_structural_separator(value: str, *, scope_kind: str) -> bool:
    if value and not value.strip():
        return True
    return scope_kind == "reading_range_id" and bool(value) and set(value) <= {"\n"}


def _resolve_ordered_span_refs(
    inventory: JsonObject,
    judgments: list[JsonObject],
) -> tuple[list[JsonObject], JsonObject | None]:
    scopes = _reading_scope_by_ref(inventory)
    resolved: list[JsonObject] = []
    blockers: list[JsonObject] = []
    for judgment_index, judgment in enumerate(judgments):
        scope_key = _judgment_scope_key(judgment)
        if scope_key is None:
            continue
        scope_kind, scope_id = scope_key
        reading_scope = scopes.get(f"{scope_kind}:{scope_id}")
        if not isinstance(reading_scope, dict):
            continue
        block_text = reading_scope.get("text")
        if not isinstance(block_text, str):
            block_text = ""
        parts = judgment.get("parts")
        if not isinstance(parts, list):
            continue
        cursor = 0
        for part_index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            part_text = part.get("text")
            if not isinstance(part_text, str):
                continue
            text = part_text.strip()
            start = block_text.find(text, cursor)
            if start < 0:
                blockers.append(
                    {
                        "code": "ordered_part_text_not_found",
                        "field": f"semantic_judgments[{judgment_index}].parts[{part_index}].text",
                        "scope": {scope_kind: scope_id},
                        "submitted_text": text,
                        "scoped_text": _text_excerpt(block_text),
                        "source_text_after_search_start": _text_excerpt(
                            block_text,
                            start=cursor,
                        ),
                        "search_start_offset": cursor,
                        "message": (
                            "Harness could not map this ordered part text inside the scoped "
                            "reading block or range. Copy parts[].text exactly from the "
                            "scoped_text value, preserving punctuation and whitespace."
                        ),
                    }
                )
                continue
            skipped = block_text[cursor:start]
            if skipped and not _ordered_part_gap_is_structural_separator(
                skipped,
                scope_kind=scope_kind,
            ):
                blockers.append(
                    {
                        "code": "ordered_part_text_gap",
                        "field": f"semantic_judgments[{judgment_index}].parts[{part_index}]",
                        "scope": {scope_kind: scope_id},
                        "uncovered_text": skipped,
                        "message": (
                            "Ordered parts must cover scoped visible text without gaps before "
                            "this part."
                        ),
                    }
                )
            end = start + len(text)
            scope = {scope_kind: scope_id}
            mapping_blockers = _span_mapping_blockers(
                reading_scope,
                start=start,
                end=end,
                field=f"semantic_judgments[{judgment_index}].parts[{part_index}]",
                scope=scope,
                submitted_text=text,
            )
            if mapping_blockers:
                blockers.extend(mapping_blockers)
                cursor = end
                continue
            span_ref = _span_ref(scope_kind, scope_id, part_index)
            covered_block_ids, covered_object_ids = _span_covered_segments(
                reading_scope,
                start=start,
                end=end,
            )
            source_entry_spans = _span_covered_source_entry_spans(
                reading_scope,
                start=start,
                end=end,
            )
            span: JsonObject = {
                "span_ref": span_ref,
                "scope": scope,
                "judgment_index": judgment_index,
                "part_index": part_index,
                "role": part.get("role"),
                "text": text,
                "text_start": start,
                "text_end": end,
                "covered_object_ids": covered_object_ids,
            }
            if scope_kind == "source_entry_id":
                span["source_entry_id"] = scope_id
            elif source_entry_spans:
                span["source_entry_spans"] = source_entry_spans
            if len(covered_block_ids) == 1:
                span["reading_block_id"] = covered_block_ids[0]
            elif covered_block_ids:
                span["reading_block_ids"] = covered_block_ids
            field_id = part.get("field_id")
            if isinstance(field_id, str) and field_id.strip():
                normalized_field_id = field_id.strip()
                span["field_id"] = normalized_field_id
                span["slot_ref"] = _slot_ref(span_ref, normalized_field_id)
            resolved.append(span)
            cursor = end
        trailing = block_text[cursor:]
        if trailing and not _ordered_part_gap_is_structural_separator(
            trailing,
            scope_kind=scope_kind,
        ):
            blockers.append(
                {
                    "code": "ordered_part_text_trailing_gap",
                    "field": f"semantic_judgments[{judgment_index}].parts",
                    "scope": {scope_kind: scope_id},
                    "uncovered_text": trailing,
                    "message": (
                        "Ordered parts must cover scoped visible text without trailing gaps."
                    ),
                }
            )

    if blockers:
        return (
            resolved,
            {
                "schema_version": HARNESS_SCHEMA_VERSION,
                "status": "needs_input",
                "feedback": {
                    "type": "span_resolution",
                    "mechanical": True,
                    "semantic_authority": False,
                    "agent_action": (
                        "Revise ordered semantic parts so their text segments partition the "
                        "scoped reading block or range in order."
                    ),
                },
                "checks": [{"name": "ordered_span_resolution", "result": "needs_input"}],
                "blockers": blockers,
                "failure": {
                    "origin": "request",
                    "code": "template_ordered_span_resolution_incomplete",
                    "retryable": True,
                    "message": (
                        "Harness could not resolve ordered semantic parts to scoped spans."
                    ),
                    "suggested_actions": [
                        "split_parts_against_exact_reading_block_or_range_text"
                    ],
                },
                "warnings": [],
            },
        )
    return (resolved, None)


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
        reading_block_ids=_reading_block_ids(inventory),
        reading_range_ids=_reading_range_ids(inventory),
        source_entry_ids=_source_entry_ids(inventory),
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


def _reading_object_ids_by_scope(inventory: JsonObject) -> dict[str, list[str]]:
    result = _source_entry_object_ids_by_scope(inventory)
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return result
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        raw_object_ids = block.get("covered_object_ids")
        object_ids = (
            [item.strip() for item in raw_object_ids if isinstance(item, str) and item.strip()]
            if isinstance(raw_object_ids, list)
            else []
        )
        block_id = block.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            result[f"reading_block_id:{block_id.strip()}"] = list(dict.fromkeys(object_ids))
        for range_id in _reading_range_ids_for_block(block):
            key = f"reading_range_id:{range_id}"
            result.setdefault(key, []).extend(object_ids)
            result[key] = list(dict.fromkeys(result[key]))
    return result


def _source_entry_object_ids_by_scope(inventory: JsonObject) -> dict[str, list[str]]:
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
        result[f"source_entry_id:{source_entry_id.strip()}"] = list(dict.fromkeys(object_ids))
    return result


def _coverage_judgments_from_ordered_parts(
    inventory: JsonObject,
    raw_judgments: list[JsonObject],
) -> list[JsonObject]:
    if _inventory_field_vocabulary(inventory) is None:
        return []
    object_ids_by_scope = _reading_object_ids_by_scope(inventory)
    projected: list[JsonObject] = []
    for index, raw in enumerate(raw_judgments):
        if not isinstance(raw, dict):
            continue
        scope_key = _judgment_scope_key(raw)
        covered_object_ids = (
            object_ids_by_scope.get(f"{scope_key[0]}:{scope_key[1]}", [])
            if scope_key is not None
            else []
        )
        projected.append(
            {
                "judgment_ref": f"semantic_judgments[{index}]",
                "judgment": _coverage_judgment_summary(raw),
                "covered_object_ids": list(dict.fromkeys(covered_object_ids)),
                **({"scope": dict(raw["scope"])} if isinstance(raw.get("scope"), dict) else {}),
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
    coverage = {
        source_entry_id: [0] * len(text)
        for source_entry_id, text in text_by_entry.items()
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
        if any(
            character.strip() and coverage[source_entry_id][index] == 0
            for index, character in enumerate(text_by_entry[source_entry_id])
        )
    ]
    overlaps = [
        source_entry_id
        for source_entry_id in known_ids
        if any(count > 1 for count in coverage[source_entry_id])
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
        suggested_actions.append(
            "cover_missing_source_entries=" + str(missing[:20])
        )
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


def validate_unit_boundary_coverage(
    *,
    document_sha256: str,
    objects: list[JsonObject],
    units: list[Any],
) -> JsonObject:
    """Mechanically validate proposed unit boundaries against inventory order."""

    normalized_units = [_unit_boundary(raw, index=index) for index, raw in enumerate(units)]
    ids_in_order = [
        str(item["object_id"])
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    ]
    locators = [
        str(item.get("locator", ""))
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    ]
    index_by_locator = {locator: index for index, locator in enumerate(locators) if locator}
    inventory_objects = {
        str(item["object_id"]): item
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }

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

    duplicate_unit_ids = sorted(
        unit_id
        for unit_id, count in Counter(str(unit["unit_id"]) for unit in normalized_units).items()
        if count > 1
    )
    covered_ids: list[str] = []
    invalid_ranges: list[JsonObject] = []
    empty_units: list[str] = []
    projected_units: list[JsonObject] = []
    for unit in normalized_units:
        start = str(unit["start_locator"])
        end = str(unit["end_locator"])
        start_index = _locator_endpoint_index(
            start,
            index_by_locator=index_by_locator,
            locators=locators,
            endpoint="start",
        )
        end_index = _locator_endpoint_index(
            end,
            index_by_locator=index_by_locator,
            locators=locators,
            endpoint="end",
        )
        if start_index is None or end_index is None:
            invalid_ranges.append(
                {
                    "unit_id": str(unit["unit_id"]),
                    "start_locator": start,
                    "end_locator": end,
                }
            )
            projected = dict(unit)
            projected["covered_object_ids"] = []
            projected_units.append(projected)
            continue
        lower, upper = sorted((start_index, end_index))
        unit_object_id_set = set(ids_in_order[lower : upper + 1])
        for boundary_locator in (start, end):
            exact_index = index_by_locator.get(boundary_locator)
            if exact_index is not None:
                unit_object_id_set.add(ids_in_order[exact_index])
        unit_object_id_set.update(
            _parent_object_ids_for_covered_descendants(
                unit_object_id_set=unit_object_id_set,
                ids_in_order=ids_in_order,
                locators=locators,
            )
        )
        unit_object_ids = [
            object_id for object_id in ids_in_order if object_id in unit_object_id_set
        ]
        if not unit_object_ids:
            empty_units.append(str(unit["unit_id"]))
        covered_ids.extend(unit_object_ids)
        projected = dict(unit)
        projected["covered_object_ids"] = unit_object_ids
        projected_units.append(projected)

    covered_counts = Counter(covered_ids)
    covered_set = set(covered_ids)
    missing = [object_id for object_id in ids_in_order if object_id not in covered_set]
    overlaps = sorted(
        object_id
        for object_id, count in covered_counts.items()
        if object_id in set(ids_in_order) and count > 1
    )
    blockers: list[JsonObject] = []
    suggested_actions: list[str] = []
    if not normalized_units:
        blockers.append(
            {
                "code": "unit_boundaries_missing",
                "message": "Submit at least one proposed unit boundary.",
            }
        )
        suggested_actions.append("return_units_with_visual_start_and_end_boundaries")
    if duplicate_unit_ids:
        blockers.append(
            {
                "code": "duplicate_unit_ids",
                "unit_ids": duplicate_unit_ids,
                "message": "Each proposed unit_id must be unique.",
            }
        )
        suggested_actions.append(f"deduplicate_unit_ids={duplicate_unit_ids[:20]}")
    if invalid_ranges:
        blockers.append(
            {
                "code": "invalid_unit_ranges",
                "ranges": invalid_ranges,
                "message": "These unit boundaries do not resolve against the source inventory.",
            }
        )
        suggested_actions.append(f"fix_unresolvable_unit_ranges={invalid_ranges[:20]}")
    if missing:
        blockers.append(
            {
                "code": "missing_unit_coverage",
                "object_ids": missing,
                "objects": object_summaries(missing),
                "message": "These inventory objects are not covered by any proposed unit.",
            }
        )
        suggested_actions.append("revise_unit_boundaries_to_cover_all_visible_source_text")
    if overlaps:
        blockers.append(
            {
                "code": "overlapping_unit_boundaries",
                "object_ids": overlaps,
                "objects": object_summaries(overlaps),
                "message": "These inventory objects are covered by more than one proposed unit.",
            }
        )
        suggested_actions.append(f"split_or_merge_overlapping_units={overlaps[:20]}")
    if empty_units:
        blockers.append(
            {
                "code": "empty_unit_boundaries",
                "unit_ids": empty_units,
                "message": "These proposed units cover no inventory object.",
            }
        )
        suggested_actions.append(f"remove_or_retarget_empty_units={empty_units[:20]}")
    if blockers:
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "status": "needs_input",
            "feedback": {
                "type": "unit_coverage",
                "mechanical": True,
                "semantic_authority": False,
                "source_hash": document_sha256,
                "agent_action": (
                    "Revise proposed unit boundaries against the original source evidence; "
                    "do not treat this as a judgment of each unit's school-semantic role."
                ),
            },
            "checks": [{"name": "unit_boundary_coverage", "result": "needs_input"}],
            "blockers": blockers,
            "failure": {
                "origin": "request",
                "code": "unit_boundary_coverage_incomplete",
                "retryable": True,
                "message": (
                    "Every inventory object must be covered by exactly one proposed unit boundary."
                ),
                "suggested_actions": suggested_actions,
            },
            "warnings": [],
            "units": projected_units,
        }
    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "status": "ok",
        "feedback": {
            "type": "unit_coverage",
            "mechanical": True,
            "semantic_authority": False,
            "source_hash": document_sha256,
        },
        "checks": [{"name": "unit_boundary_coverage", "result": "ok"}],
        "warnings": [],
        "failure": None,
        "unit_count": len(normalized_units),
        "covered_object_count": len(set(covered_ids)),
        "units": projected_units,
    }


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


def _locator_covers(parent: str, child: str) -> bool:
    normalized = parent.rstrip("/")
    return child == normalized or child.startswith(f"{normalized}/")


def _parent_object_ids_for_covered_descendants(
    *,
    unit_object_id_set: set[str],
    ids_in_order: list[str],
    locators: list[str],
) -> set[str]:
    covered_locators = [
        locators[index]
        for index, object_id in enumerate(ids_in_order)
        if object_id in unit_object_id_set and locators[index]
    ]
    parent_ids: set[str] = set()
    for index, parent_locator in enumerate(locators):
        parent_object_id = ids_in_order[index]
        if not parent_locator or parent_object_id in unit_object_id_set:
            continue
        normalized_parent = parent_locator.rstrip("/")
        if any(
            child_locator.rstrip("/") != normalized_parent
            and _locator_covers(parent_locator, child_locator)
            for child_locator in covered_locators
        ):
            parent_ids.add(parent_object_id)
    return parent_ids


def _locator_endpoint_index(
    locator: str,
    *,
    index_by_locator: dict[str, int],
    locators: list[str],
    endpoint: str,
) -> int | None:
    normalized = locator.rstrip("/")
    covered = [
        index
        for index, object_locator in enumerate(locators)
        if object_locator
        and object_locator.rstrip("/") != normalized
        and _locator_covers(locator, object_locator)
    ]
    if covered:
        return min(covered) if endpoint == "start" else max(covered)
    exact_index = index_by_locator.get(locator)
    if exact_index is not None:
        return exact_index
    ancestor_indexes = [
        index
        for index, object_locator in enumerate(locators)
        if object_locator
        and object_locator.rstrip("/") != normalized
        and _locator_covers(object_locator, locator)
    ]
    if ancestor_indexes:
        return max(
            ancestor_indexes,
            key=lambda index: len(locators[index].rstrip("/")),
        )
    return None


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
            return self._submit_semantic_judgments(root, args)
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
        document = _document_path(args, root)
        inspection = inspect_document_snapshot(
            document,
            self.office,
            selector=COVERAGE_SELECTOR,
        )
        objects = [
            {
                "object_id": str(item.object_ref["object_id"]),
                "object_ref": item.object_ref,
                "type": item.kind,
                "locator": item.locator,
            }
            for item in inspection.objects
        ]
        return self._store_inventory(
            root,
            document_sha256=inspection.document_sha256,
            objects=objects,
            source="inspect_objects",
        )

    def _submit_object_inventory(self, root: Path, args: dict[str, Any]) -> JsonObject:
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
                canonical_source_entry_ids=known_source_entry_ids
                if source_entries
                else None,
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
                suggested_actions=(
                    f"unknown_source_entry_ids={unknown_canonical_entries[:20]}",
                ),
            )
        duplicate_source_entries = sorted(
            source_entry_id
            for source_entry_id, count in source_entry_counts.items()
            if count > 1
        )
        if duplicate_source_entries and not source_entries:
            raise ToolFailure(
                status="needs_input",
                origin="request",
                code="template_source_entry_inventory_duplicate",
                message="Each source DOC component may appear only once in the source inventory.",
                suggested_actions=(
                    f"duplicate_source_entry_ids={duplicate_source_entries[:20]}",
                ),
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
        if canonical_source_inventory is not None:
            atomic_write_json(root / SOURCE_INVENTORY_PATH, canonical_source_inventory)
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
        ordered_feedback = _ordered_semantic_parts_feedback(inventory, raw_judgments)
        if ordered_feedback is not None:
            ordered_feedback["harness_state"] = self._state(root)
            return ordered_feedback
        accepted_source_judgments = [
            dict(raw) for raw in raw_judgments if isinstance(raw, dict)
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
        if _inventory_uses_source_entry_gate(inventory):
            feedback = _source_entry_coverage_feedback(inventory, resolved_spans)
            coverage_message = (
                "Every canonical source entry must be covered by non-overlapping "
                "semantic spans, and each accepted span must expand to provenance."
            )
        else:
            feedback = self._coverage_feedback(inventory, coverage_judgments)
            coverage_message = (
                "Every inventory object must be covered by exactly one non-empty "
                "semantic judgment."
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
            return _json_object(
                json.loads((root / OBJECT_INVENTORY_PATH).read_text(encoding="utf-8")),
                field="object_inventory",
            )
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
                suggested_actions.append(
                    "cover_missing_reading_blocks=" + str(missing_block_ids)
                )
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
                    "fill_empty_semantic_judgments_for_reading_blocks="
                    + str(empty_block_ids)
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
            for item in coverage_judgments
            for object_id in item.get("covered_object_ids", [])
            if str(object_id) in known_ids
            and isinstance(item.get("judgment"), str)
            and item["judgment"].strip()
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
            "all_objects_have_semantic_judgment": not (
                source_feedback["blockers"] if source_entry_gate else feedback["blockers"]
            ),
            "all_objects_have_semantic_coverage": not (
                source_feedback["blockers"] if source_entry_gate else feedback["blockers"]
            ),
            "all_source_entries_have_semantic_coverage": not source_feedback["blockers"]
            if source_entry_gate
            else False,
        }
