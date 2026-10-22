"""Execution readiness checks for post-unit template materialization."""

from __future__ import annotations

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.field_binding import (
    explicit_field_ids_from_source,
    explicit_materialization_field_ids,
    ordered_parts,
    semantic_part_carries_field,
    semantic_part_is_slot,
)
from docfit.template.materialization.vocabulary import (
    inventory_review_vocabulary_provenance_errors,
)
from docfit.tools.runtime import JsonObject, ToolFailure

_SLOT_CONTENT_TYPES = {"text", "rich_text"}
_LEGACY_READINESS_KEYS = frozenset(
    {
        "judgment_id",
        "judgment_ref",
        "judgment",
        "semantic_judgment",
        "materialization_intent",
        "semantic_part_index",
        "responsibility",
        "semantic_role",
        "clean_template_treatment",
        "output_effect",
        "style_obligation",
        "cleanup_reason",
        "structure_ref",
        "members",
        "semantic_field",
        "registry_field",
        "registry_field_id",
        "bound_field_id",
        "bound_field_ids",
        "required_field_ids",
        "generated_field_id",
        "toc_contract",
        "semantic_parts",
        "source_content_id",
        "source_content_ids",
        "parent_content_id",
        "target_content_id",
        "source_object_id",
        "source_object_ids",
        "covered_reading_block_ids",
        "covered_reading_range_ids",
        "covered_reading_spans",
        "covered_unit_ids",
        "covered_object_ids",
        "covered_object_locators",
        "covered_ranges",
        "field_id",
        "variant_id",
        "variant_role",
        "condition",
        "variant_condition",
    }
)
_LEGACY_READINESS_PART_KEYS = frozenset(
    {
        "semantic_field",
        "registry_field",
        "registry_field_id",
        "bound_field_id",
        "bound_field_ids",
        "required_field_ids",
        "generated_field_id",
        "field_ids",
        "semantic_part_index",
        "source_content_id",
        "source_content_ids",
        "parent_content_id",
        "target_content_id",
        "source_object_id",
        "source_object_ids",
        "span_id",
        "span_ref",
        "resolved_span",
        "resolved_spans",
        "resolved_span_refs",
        "slot_id",
        "slot_ref",
        "intent_id",
        "content_control_tag",
        "tag",
        "covered_reading_block_ids",
        "reading_block_ids",
        "covered_block_ids",
        "block_ids",
        "source_block_ids",
        "semantic_block_ids",
        "reading_block_id",
        "covered_reading_range_ids",
        "reading_range_ids",
        "covered_range_ids",
        "range_ids",
        "source_range_ids",
        "semantic_range_ids",
        "reading_range_id",
        "covered_reading_spans",
        "reading_spans",
        "semantic_ranges",
        "covered_reading_span",
        "covered_unit_ids",
        "unit_coverage_ids",
        "whole_unit_ids",
        "covered_unit_id",
        "covered_object_ids",
        "object_ids",
        "covered_objects",
        "covered_object_refs",
        "object_refs",
        "source_object_refs",
        "target_refs",
        "object_id",
        "object_ref",
        "target_ref",
        "target",
        "covered_object_locators",
        "object_locators",
        "covered_locators",
        "source_object_locators",
        "target_locators",
        "locator",
        "object_locator",
        "covered_locator_ranges",
        "locator_ranges",
        "covered_object_ranges",
        "object_ranges",
        "fingerprint",
        "hash",
        "source_hash",
        "candidate_hash",
        "render_ref",
        "coverage",
        "publish",
        "checkpoint_backend",
        "task_root",
        "stale_ref",
    }
)
_PLAN_BLOCKER_EQUIVALENTS = {
    "materialization_legacy_shape_unsupported": {
        "materialization_legacy_shape_unsupported"
    },
    "materialization_slot_field_missing": {"materialization_part_field_missing"},
    "materialization_generated_content_field_missing": {"materialization_part_field_missing"},
    "materialization_body_structure_semantics_missing": {"materialization_part_field_missing"},
}


def materialization_field_ids(judgment: JsonObject) -> list[str]:
    return explicit_materialization_field_ids(judgment)


def is_materializable_slot_judgment(judgment: JsonObject) -> bool:
    return any(semantic_part_is_slot(part) for part in ordered_parts(judgment))


def is_materializable_body_structure_judgment(judgment: JsonObject) -> bool:
    return _has_ordered_part_role(judgment, "body_structure")


def is_materializable_generated_judgment(judgment: JsonObject) -> bool:
    return _has_ordered_part_role(judgment, "generated_content")


def is_materializable_judgment(judgment: JsonObject) -> bool:
    return bool(ordered_parts(judgment))


def _has_ordered_part_role(judgment: JsonObject, role: str) -> bool:
    return any(_ordered_part_role(part) == role for part in ordered_parts(judgment))


def _legacy_part_fields(judgment: JsonObject) -> list[str]:
    legacy_fields: set[str] = set()
    for part in ordered_parts(judgment):
        legacy_fields.update(_LEGACY_READINESS_PART_KEYS.intersection(part))
    return sorted(legacy_fields)


def _ordered_part_role(part: JsonObject) -> str:
    value = part.get("role")
    return value.strip() if isinstance(value, str) else ""


def _normalized_str(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _registry_lookup_or_none(
    registry: FieldRegistrySnapshot,
    field_id: str,
) -> JsonObject | None:
    try:
        return registry.lookup(field_id)
    except ToolFailure:
        return None


def _non_empty_items(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict) and item:
            result.append(str(item))
    return result


def _judgment_reading_block_ids(judgment: JsonObject) -> list[str]:
    scope = judgment.get("scope")
    if isinstance(scope, dict):
        block_id = scope.get("reading_block_id")
        if isinstance(block_id, str) and block_id.strip():
            return [block_id.strip()]
    return []


def _judgment_reading_range_ids(judgment: JsonObject) -> list[str]:
    scope = judgment.get("scope")
    if isinstance(scope, dict):
        range_id = scope.get("reading_range_id")
        if isinstance(range_id, str) and range_id.strip():
            return [range_id.strip()]
    return []


def _reading_block_summaries(
    inventory: JsonObject,
    block_ids: list[str],
) -> list[JsonObject]:
    if not block_ids:
        return []
    wanted = set(block_ids)
    summaries: list[JsonObject] = []
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_id = block.get("block_id")
        if not isinstance(block_id, str) or block_id not in wanted:
            continue
        summary: JsonObject = {"block_id": block_id}
        for key in ("range_id", "unit_range_id", "unit_id", "text"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                summary[key] = value.strip()[:500] if key == "text" else value.strip()
        summaries.append(summary)
    return summaries


def _reading_block_ids_by_unit(inventory: JsonObject) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return result
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_id = block.get("block_id")
        unit_id = block.get("unit_id")
        if isinstance(block_id, str) and block_id.strip() and isinstance(unit_id, str):
            result.setdefault(unit_id.strip(), []).append(block_id.strip())
    return result


def _reading_block_ids_by_range(inventory: JsonObject) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return result
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_id = block.get("block_id")
        if not isinstance(block_id, str) or not block_id.strip():
            continue
        for key in ("range_id", "unit_range_id"):
            range_id = block.get(key)
            if isinstance(range_id, str) and range_id.strip():
                result.setdefault(range_id.strip(), []).append(block_id.strip())
    return result


def _objects_by_id(inventory: JsonObject) -> dict[str, JsonObject]:
    raw_objects = inventory.get("objects")
    if not isinstance(raw_objects, list):
        return {}
    result: dict[str, JsonObject] = {}
    for item in raw_objects:
        if not isinstance(item, dict):
            continue
        object_id = item.get("object_id")
        if isinstance(object_id, str) and object_id.strip():
            result[object_id.strip()] = item
    return result


def _reading_blocks_by_id(inventory: JsonObject) -> dict[str, JsonObject]:
    raw_blocks = inventory.get("reading_blocks")
    if not isinstance(raw_blocks, list):
        return {}
    result: dict[str, JsonObject] = {}
    for item in raw_blocks:
        if not isinstance(item, dict):
            continue
        block_id = item.get("block_id")
        if isinstance(block_id, str) and block_id.strip():
            result[block_id.strip()] = item
    return result


def _reading_block_word_kind(
    inventory: JsonObject,
    block_id: str,
) -> str:
    block = _reading_blocks_by_id(inventory).get(block_id)
    if block is None:
        return ""
    for key in ("word_kind", "carrier_kind", "block_kind"):
        raw_kind = block.get(key)
        if isinstance(raw_kind, str) and raw_kind.strip():
            return raw_kind.strip().casefold()
    objects_by_id = _objects_by_id(inventory)
    raw_object_ids = block.get("covered_object_ids")
    object_ids = (
        [item.strip() for item in raw_object_ids if isinstance(item, str) and item.strip()]
        if isinstance(raw_object_ids, list)
        else []
    )
    kinds: set[str] = set()
    for object_id in object_ids:
        item = objects_by_id.get(object_id)
        if item is None:
            continue
        raw_type = item.get("type")
        object_type = raw_type.strip().casefold() if isinstance(raw_type, str) else ""
        raw_locator = item.get("locator")
        locator = raw_locator.strip().casefold() if isinstance(raw_locator, str) else ""
        if object_type == "table" or "/tbl" in locator:
            kinds.add("table")
            continue
        if object_type in {"paragraph", "run", "sdt", "picture", "shape"} or "/p" in locator:
            kinds.add("paragraph")
    if "table" in kinds:
        return "table"
    if "paragraph" in kinds:
        return "paragraph"
    return ""


def _scope_reading_block_ids(inventory: JsonObject, scope_refs: list[JsonObject]) -> list[str]:
    by_unit = _reading_block_ids_by_unit(inventory)
    by_range = _reading_block_ids_by_range(inventory)
    block_ids: list[str] = []
    seen: set[str] = set()
    for scope in scope_refs:
        kind = scope.get("kind")
        ref_id = scope.get("ref_id")
        if not isinstance(kind, str) or not isinstance(ref_id, str):
            continue
        candidates: list[str]
        if kind == "reading_block":
            candidates = [ref_id]
        elif kind == "reading_range":
            candidates = by_range.get(ref_id, [])
        elif kind == "unit":
            candidates = by_unit.get(ref_id, [])
        else:
            candidates = []
        for block_id in candidates:
            if block_id in seen:
                continue
            seen.add(block_id)
            block_ids.append(block_id)
    return block_ids


def _materialization_readiness_blocker(
    *,
    inventory: JsonObject,
    judgment: JsonObject,
    code: str,
    missing_requirement: str,
    message: str,
    needed_context: str | None = None,
    field_id: str | None = None,
    reading_block_ids: list[str] | None = None,
) -> JsonObject:
    judgment_ref = judgment.get("judgment_ref")
    block_ids = (
        reading_block_ids
        if reading_block_ids is not None
        else _judgment_reading_block_ids(judgment)
    )
    range_ids = _judgment_reading_range_ids(judgment)
    blocker: JsonObject = {
        "code": code,
        "missing_requirement": missing_requirement,
        "why_it_blocks_execution": message,
        "message": message,
    }
    if isinstance(judgment_ref, str) and judgment_ref.strip():
        blocker["judgment_ref"] = judgment_ref.strip()
    if block_ids:
        blocker["reading_block_ids"] = block_ids
        blocker["reading_blocks"] = _reading_block_summaries(inventory, block_ids)
    if range_ids:
        blocker["reading_range_ids"] = range_ids
    if needed_context is not None:
        blocker["needed_context"] = needed_context
        blocker["evidence_focus"] = needed_context
    if field_id is not None:
        blocker["field_id"] = field_id
    return blocker


def _slot_field_compatibility_blocker(
    *,
    inventory: JsonObject,
    judgment: JsonObject,
    field_id: str,
    field: JsonObject,
) -> JsonObject | None:
    normalized_field_id = field_id.strip()
    value_sources = field.get("value_sources")
    value_sources_set = (
        {item for item in value_sources if isinstance(item, str)}
        if isinstance(value_sources, list)
        else set()
    )
    content_type = _normalized_str(field.get("content_type")).casefold()
    parent_field_id = field.get("parent_field_id")
    incompatible_reason = ""
    if isinstance(parent_field_id, str) or content_type == "section":
        incompatible_reason = "body_structure_field"
    elif (
        "system_generated" in value_sources_set
        and "student_source" not in value_sources_set
        and "task_input" not in value_sources_set
    ):
        incompatible_reason = "generated_field"
    elif content_type not in _SLOT_CONTENT_TYPES:
        incompatible_reason = "non_leaf_or_non_text_field"
    if not incompatible_reason:
        return None
    if incompatible_reason == "body_structure_field":
        message = (
            "This fill_slot part references a body structure field. Body structure "
            "fields are only valid on body_structure parts. Revise the part role or "
            "select a fillable leaf field_id from the pre-input vocabulary."
        )
    else:
        message = (
            "This fill_slot part references a field that cannot be used as a plain "
            "fillable slot. Select a fillable leaf field_id from the pre-input "
            "vocabulary, or revise the part role."
        )
    return _materialization_readiness_blocker(
        inventory=inventory,
        judgment=judgment,
        code="materialization_slot_field_incompatible",
        missing_requirement="field_id_vocabulary.fillable_leaf_field_id",
        message=message,
        needed_context="field_id_vocabulary",
        field_id=normalized_field_id,
    )


def _add_part_context(
    blocker: JsonObject,
    *,
    part_index: int,
    part: JsonObject,
) -> JsonObject:
    result = dict(blocker)
    result["part_index"] = part_index
    text = part.get("text")
    if isinstance(text, str) and text.strip():
        result["semantic_part_text"] = text.strip()[:200]
    return result


def _plan_readiness_blockers(
    *,
    inventory: JsonObject,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> list[JsonObject]:
    from docfit.template.materialization.plan import build_shadow_materialization_plan

    result = build_shadow_materialization_plan(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    blockers: list[JsonObject] = []
    for unsupported in result.unsupported:
        unsupported_json = unsupported.to_json()
        reason_code = unsupported_json.get("reason_code")
        source_judgment_refs = unsupported_json.get("source_judgment_refs")
        source_judgment_ref = (
            source_judgment_refs[0]
            if isinstance(source_judgment_refs, list)
            and source_judgment_refs
            and isinstance(source_judgment_refs[0], str)
            else None
        )
        scope_refs = unsupported_json.get("scope_refs")
        scope_refs = scope_refs if isinstance(scope_refs, list) else []
        block_ids = _scope_reading_block_ids(inventory, scope_refs)
        message = unsupported_json.get("message")
        missing_requirements = unsupported_json.get("missing_requirements")
        missing_requirement = (
            ", ".join(item for item in missing_requirements if isinstance(item, str))
            if isinstance(missing_requirements, list)
            else ""
        )
        blocker: JsonObject = {
            "code": reason_code,
            "missing_requirement": missing_requirement or "materialization_plan_repair",
            "why_it_blocks_execution": message if isinstance(message, str) else str(reason_code),
            "message": message if isinstance(message, str) else str(reason_code),
            "needed_context": "unit_evidence_packet",
            "evidence_focus": "unit_evidence_packet",
        }
        if isinstance(source_judgment_ref, str) and source_judgment_ref.strip():
            blocker["source_judgment_ref"] = source_judgment_ref.strip()
        if block_ids:
            blocker["reading_block_ids"] = block_ids
            blocker["reading_blocks"] = _reading_block_summaries(inventory, block_ids)
        if scope_refs:
            blocker["scope_refs"] = scope_refs
        blockers.append(blocker)
    return blockers


def _append_unique_blockers(
    blockers: list[JsonObject],
    seen: set[tuple[object, object, object]],
    new_blockers: list[JsonObject],
) -> None:
    for blocker in new_blockers:
        if _has_equivalent_blocker(blocker, blockers):
            continue
        identity = (
            blocker.get("code"),
            blocker.get("source_judgment_ref") or blocker.get("judgment_ref"),
            blocker.get("missing_requirement"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        blockers.append(blocker)


def _has_equivalent_blocker(candidate: JsonObject, blockers: list[JsonObject]) -> bool:
    code = candidate.get("code")
    if not isinstance(code, str):
        return False
    equivalent_codes = _PLAN_BLOCKER_EQUIVALENTS.get(code)
    if not equivalent_codes:
        return False
    candidate_scope = _blocker_scope_tokens(candidate)
    if not candidate_scope:
        return False
    for blocker in blockers:
        existing_code = blocker.get("code")
        if not isinstance(existing_code, str) or existing_code not in equivalent_codes:
            continue
        if candidate_scope.intersection(_blocker_scope_tokens(blocker)):
            return True
    return False


def _blocker_scope_tokens(blocker: JsonObject) -> set[str]:
    tokens: set[str] = set()
    for key, prefix in (
        ("reading_block_ids", "block"),
        ("reading_range_ids", "range"),
    ):
        raw_values = blocker.get(key)
        if not isinstance(raw_values, list):
            continue
        for value in raw_values:
            if isinstance(value, str) and value.strip():
                tokens.add(f"{prefix}:{value.strip()}")
    return tokens


def _field_part_readiness_blockers(
    *,
    inventory: JsonObject,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
) -> list[JsonObject]:
    blockers: list[JsonObject] = []
    for part_index, part in enumerate(ordered_parts(judgment)):
        if not semantic_part_carries_field(part):
            continue
        field_ids = explicit_field_ids_from_source(part)
        if not field_ids:
            blockers.append(
                _add_part_context(
                    _materialization_readiness_blocker(
                        inventory=inventory,
                        judgment=judgment,
                        code="materialization_part_field_missing",
                        missing_requirement="parts[].field_id",
                        message=(
                            "This executable ordered part is missing field_id from the "
                            "pre-input field vocabulary."
                        ),
                        needed_context="field_id_vocabulary",
                    ),
                    part_index=part_index,
                    part=part,
                )
            )
            continue
        for field_id in field_ids:
            field = _registry_lookup_or_none(registry, field_id)
            if field is None:
                blockers.append(
                    _add_part_context(
                        _materialization_readiness_blocker(
                            inventory=inventory,
                            judgment=judgment,
                            code="materialization_field_not_in_vocabulary",
                            missing_requirement=(
                                "parts[].field_id in field_id_vocabulary.allowed_field_ids"
                            ),
                            message=(
                                "This ordered part references a field_id outside the "
                                "accepted pre-input field_id_vocabulary."
                            ),
                            needed_context="field_id_vocabulary",
                            field_id=field_id,
                        ),
                        part_index=part_index,
                        part=part,
                    )
                )
                continue
            if semantic_part_is_slot(part):
                compatibility = _slot_field_compatibility_blocker(
                    inventory=inventory,
                    judgment=judgment,
                    field_id=field_id,
                    field=field,
                )
                if compatibility is not None:
                    blockers.append(
                        _add_part_context(compatibility, part_index=part_index, part=part)
                    )
    return blockers


def materialization_readiness_feedback(
    *,
    inventory: JsonObject,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> JsonObject | None:
    raw_judgments = review.get("semantic_judgments")
    if not isinstance(raw_judgments, list):
        return None
    vocabulary_blockers = inventory_review_vocabulary_provenance_errors(
        inventory=inventory,
        review=review,
        registry=registry,
    )
    if vocabulary_blockers:
        return _materialization_readiness_feedback(vocabulary_blockers)
    blockers: list[JsonObject] = []
    judgments = [item for item in raw_judgments if isinstance(item, dict)]
    has_executable_intent = any(is_materializable_judgment(judgment) for judgment in judgments)
    has_legacy_shape = False
    for raw_judgment in judgments:
        legacy_fields = sorted(_LEGACY_READINESS_KEYS.intersection(raw_judgment))
        legacy_part_fields = _legacy_part_fields(raw_judgment)
        if legacy_fields or legacy_part_fields:
            has_legacy_shape = True
            blocker = _materialization_readiness_blocker(
                inventory=inventory,
                judgment=raw_judgment,
                code="materialization_legacy_shape_unsupported",
                missing_requirement="scope_parts_resolved_spans",
                message=(
                    "Accepted semantic judgments must use source_entry_id or compatibility "
                    "scope, ordered parts, and Harness-resolved spans. Legacy judgment "
                    "fields are not accepted for materialization readiness."
                ),
                needed_context="unit_evidence_packet",
            )
            if legacy_fields:
                blocker["legacy_fields"] = legacy_fields
            if legacy_part_fields:
                blocker["legacy_part_fields"] = legacy_part_fields
            blockers.append(blocker)
            continue
        unresolved_fields = [
            field
            for field in ("needs_input", "open_questions")
            if _non_empty_items(raw_judgment.get(field))
        ]
        if unresolved_fields:
            blockers.append(
                _materialization_readiness_blocker(
                    inventory=inventory,
                    judgment=raw_judgment,
                    code="materialization_semantic_judgment_unresolved",
                    missing_requirement=", ".join(unresolved_fields),
                    message=(
                        "This semantic_judgment still contains unresolved needs_input or "
                        "open_questions while the Agent result is complete. Revise the "
                        "judgment to resolve the listed semantic gaps, or return "
                        "needs_input at the result level."
                    ),
                        needed_context="unit_evidence_packet",
                    )
                )
        blockers.extend(
            _field_part_readiness_blockers(
                inventory=inventory,
                judgment=raw_judgment,
                registry=registry,
            )
        )
    seen_blockers = {
        (
            blocker.get("code"),
            blocker.get("source_judgment_ref") or blocker.get("judgment_ref"),
            blocker.get("missing_requirement"),
        )
        for blocker in blockers
    }
    if has_executable_intent and not has_legacy_shape:
        _append_unique_blockers(
            blockers,
            seen_blockers,
            _plan_readiness_blockers(
                inventory=inventory,
                review=review,
                registry=registry,
            ),
        )
    if not blockers:
        return None
    return _materialization_readiness_feedback(blockers)


def _materialization_readiness_feedback(blockers: list[JsonObject]) -> JsonObject:
    return {
        "schema_version": 1,
        "status": "needs_input",
        "feedback": {
            "type": "materialization_readiness",
            "mechanical": True,
            "semantic_authority": False,
            "agent_action": (
                "Revise semantic_judgments to use source_entry_id or compatibility scope, "
                "ordered parts, and field_id values from the pre-input field vocabulary. "
                "Do not proceed to DOCX materialization until Harness-resolved spans are "
                "present."
            ),
        },
        "checks": [{"name": "materialization_readiness", "result": "needs_input"}],
        "blockers": blockers,
        "failure": {
            "origin": "harness",
            "code": "template_materialization_readiness_incomplete",
            "retryable": True,
            "message": (
                "Accepted semantic_judgments are not ready for deterministic materialization."
            ),
            "suggested_actions": [
                "return_to_agent_with_materialization_readiness_feedback",
                (
                    "revise_semantic_judgments_for_source_entry_id_ordered_parts_"
                    "field_id_and_span_ref"
                ),
            ],
        },
        "warnings": [],
    }
