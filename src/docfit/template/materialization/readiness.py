"""Execution readiness checks for post-unit template materialization."""

from __future__ import annotations

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.body_interfaces import body_interfaces, body_paragraph_carrier
from docfit.template.materialization.field_binding import (
    explicit_field_ids_from_source,
    explicit_materialization_field_ids,
    ordered_parts,
    semantic_part_carries_field,
    semantic_part_is_slot,
)
from docfit.template.materialization.models import AcceptedResolvedSpan
from docfit.template.materialization.recovery import readiness_failure, readiness_recovery
from docfit.template.materialization.vocabulary import (
    inventory_review_vocabulary_provenance_errors,
)
from docfit.template.semantic_review import review_uses_current_semantic_shape
from docfit.template.unit_source import source_unit_cut_points, validate_inventory_partition
from docfit.tools.runtime import JsonObject, ToolFailure

_SLOT_CONTENT_TYPES = {"text", "rich_text", "section"}
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


def _materialization_readiness_blocker(
    *,
    judgment: JsonObject,
    code: str,
    missing_requirement: str,
    message: str,
    needed_context: str | None = None,
    field_id: str | None = None,
) -> JsonObject:
    judgment_ref = judgment.get("judgment_ref")
    blocker: JsonObject = {
        "code": code,
        "missing_requirement": missing_requirement,
        "why_it_blocks_execution": message,
        "message": message,
    }
    if isinstance(judgment_ref, str) and judgment_ref.strip():
        blocker["judgment_ref"] = judgment_ref.strip()
    source_entry_id = judgment.get("source_entry_id")
    if isinstance(source_entry_id, str) and source_entry_id.strip():
        blocker["source_entry_id"] = source_entry_id.strip()
    if needed_context is not None:
        blocker["needed_context"] = needed_context
        blocker["evidence_focus"] = needed_context
    if field_id is not None:
        blocker["field_id"] = field_id
    return blocker


def _slot_field_compatibility_blocker(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
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
    if isinstance(parent_field_id, str) or (
        content_type == "section" and registry.has_children(normalized_field_id)
    ):
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
        source_entry_ids = [
            str(scope["ref_id"])
            for scope in scope_refs
            if scope.get("kind") == "source_entry" and isinstance(scope.get("ref_id"), str)
        ]
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
        if source_entry_ids:
            blocker["source_entry_ids"] = source_entry_ids
            blocker["source_entries"] = [
                {key: entry[key] for key in ("source_entry_id", "entry_type", "text")
                 if key in entry}
                for entry in inventory.get("source_entries", [])
                if isinstance(entry, dict) and entry.get("source_entry_id") in source_entry_ids
            ]
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
        identity = (
            blocker.get("code"),
            blocker.get("source_judgment_ref") or blocker.get("judgment_ref"),
            blocker.get("missing_requirement"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        blockers.append(blocker)


def _field_part_readiness_blockers(
    *,
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
                    judgment=judgment,
                    registry=registry,
                    field_id=field_id,
                    field=field,
                )
                if compatibility is not None:
                    blockers.append(
                        _add_part_context(compatibility, part_index=part_index, part=part)
                    )
    return blockers


def _slot_carrier_blocker(judgment: JsonObject) -> JsonObject | None:
    if not is_materializable_slot_judgment(judgment):
        return None
    paragraphs: set[str] = set()
    missing_paragraph = False
    for span in judgment.get("resolved_spans", []):
        for fragment in span.get("word_fragments", []):
            locator = fragment.get("locator", "")
            segments = locator.split("/") if isinstance(locator, str) else []
            indexes = [index for index, segment in enumerate(segments) if segment.startswith("p[")]
            if not indexes:
                missing_paragraph = True
            else:
                paragraphs.add("/".join(segments[: indexes[-1] + 1]))
    if not missing_paragraph and len(paragraphs) == 1:
        return None
    return _materialization_readiness_blocker(
        judgment=judgment,
        code="materialization_slot_carrier_unsupported",
        missing_requirement="one_exact_paragraph_carrier_for_slot",
        message=(
            "The source object has no single paragraph carrier for a fill slot. "
            "Whole tables and other non-paragraph objects cannot use an arbitrary child. "
            "The execution layer must support this accepted scope before proceeding."
        ),
        needed_context="unit_evidence_packet",
    )


def _body_structure_member_blocker(
    judgment: JsonObject, *, cut_points: dict[str, set[int]],
) -> JsonObject | None:
    part_indexes = [
        index
        for index, part in enumerate(ordered_parts(judgment))
        if _ordered_part_role(part) == "body_structure"
    ]
    if len(part_indexes) <= 1:
        return None
    raw_spans = judgment.get("resolved_spans")
    body_spans = (
        [
            span
            for span in raw_spans
            if isinstance(span, dict) and span.get("role") == "body_structure"
        ]
        if isinstance(raw_spans, list)
        else []
    )
    groups = body_interfaces(
        [AcceptedResolvedSpan.from_json(span) for span in raw_spans]
        if isinstance(raw_spans, list) else [], cut_points=cut_points,
    )
    carriers: set[str] = set()
    for span in body_spans:
        raw_fragments = span.get("word_fragments")
        fragments = raw_fragments if isinstance(raw_fragments, list) else []
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            carrier = body_paragraph_carrier(fragment.get("locator"))
            if carrier is not None:
                carriers.add(carrier)
    if (
        len(body_spans) == len(part_indexes)
        and len(carriers) == 1
        and [span.get("part_index") for span in body_spans] == part_indexes
        and len({group.anchor.field_id for group in groups}) == len(groups)
    ):
        return None
    blocker = _materialization_readiness_blocker(
        judgment=judgment,
        code="materialization_body_structure_member_ambiguous",
        missing_requirement="one_body_structure_member_per_source_entry",
        message=(
            "The accepted body parts cannot be represented by the currently supported "
            "body interfaces. Preserve the judgment and resolve this execution limitation."
        ),
        needed_context="unit_evidence_packet",
    )
    blocker["part_indexes"] = part_indexes
    return blocker


def _top_level_body_carrier(locator: object) -> str | None:
    if not isinstance(locator, str):
        return None
    segments = [segment for segment in locator.split("/") if segment]
    if len(segments) < 2 or segments[0] != "body":
        return None
    return f"/body/{segments[1]}"


def _body_structure_carrier_blockers(
    judgments: list[JsonObject], *, cut_points: dict[str, set[int]],
    registry: FieldRegistrySnapshot,
) -> list[JsonObject]:
    bindings_by_carrier: dict[str, list[JsonObject]] = {}
    blockers: list[JsonObject] = []
    for judgment in judgments:
        source_entry_id = judgment.get("source_entry_id")
        raw_spans = judgment.get("resolved_spans")
        if not isinstance(source_entry_id, str) or not isinstance(raw_spans, list):
            continue
        primary_refs = {
            group.anchor.span_ref for group in body_interfaces(
                [AcceptedResolvedSpan.from_json(span) for span in raw_spans],
                cut_points=cut_points,
            )
        }
        for span in raw_spans:
            if (
                not isinstance(span, dict)
                or span.get("role") != "body_structure"
                or not isinstance(span.get("field_id"), str)
            ):
                continue
            raw_fragments = span.get("word_fragments")
            fragments = raw_fragments if isinstance(raw_fragments, list) else []
            paragraph_carriers = {
                body_paragraph_carrier(fragment.get("locator"))
                for fragment in fragments if isinstance(fragment, dict)
            }
            field = _registry_lookup_or_none(registry, str(span["field_id"]))
            cell_text_supported = (
                len(paragraph_carriers) == 1 and None not in paragraph_carriers
                and field is not None and field.get("content_type") in {"text", "rich_text"}
            )
            carriers = {
                carrier
                for fragment in fragments
                if isinstance(fragment, dict)
                and (carrier := (
                    body_paragraph_carrier(fragment.get("locator")) if cell_text_supported
                    else _top_level_body_carrier(fragment.get("locator"))
                )) is not None
            }
            if len(carriers) != 1:
                absent = not carriers
                blocker = _materialization_readiness_blocker(
                    judgment=judgment,
                    code=(
                        "materialization_body_structure_carrier_unsupported" if absent
                        else "materialization_body_structure_member_crosses_carriers"
                    ),
                    missing_requirement="one_visible_carrier_per_body_member",
                    message=(
                        "This body_structure member has no supported body carrier. "
                        "Its source location is outside the supported body interfaces; "
                        "preserve its judgment and inspect the execution limitation."
                        if absent else
                        "This body_structure member spans multiple supported body carriers. "
                        "The execution layer does not support this multi-object interface; "
                        "preserve its judgment."
                    ),
                    needed_context="unit_evidence_packet",
                    field_id=str(span["field_id"]),
                )
                blocker["supported_carrier_count"] = len(carriers)
                blockers.append(blocker)
                continue
            carrier = next(iter(carriers))
            fragment_locators = [
                fragment.get("locator") for fragment in fragments if isinstance(fragment, dict)
            ]
            if not cell_text_supported and carrier.startswith("/body/tbl[") and not all(
                locator == carrier for locator in fragment_locators
            ):
                blockers.append(
                    _materialization_readiness_blocker(
                        judgment=judgment,
                        code="materialization_body_structure_nested_composite_member",
                        missing_requirement="outer_composite_body_member_interface",
                        message=(
                            "A field-bearing body_structure part resolves inside a "
                            "composite table without a supported paragraph text interface. "
                            "This structural interface is not currently supported by the "
                            "execution layer; preserve the field judgment."
                        ),
                        needed_context="unit_evidence_packet",
                        field_id=str(span["field_id"]),
                    )
                )
                continue
            if span.get("span_ref") not in primary_refs:
                continue
            bindings_by_carrier.setdefault(carrier, []).append(
                {
                    "source_entry_id": source_entry_id,
                    "field_id": span["field_id"],
                    "part_index": span.get("part_index"),
                }
            )
    for carrier, bindings in bindings_by_carrier.items():
        nested_bindings = [
            binding for child, child_bindings in bindings_by_carrier.items()
            if child.startswith(carrier + "/") for binding in child_bindings
        ]
        if nested_bindings:
            bindings = [*bindings, *nested_bindings]
        if len(bindings) <= 1:
            continue
        source_entry_ids = list(
            dict.fromkeys(str(binding["source_entry_id"]) for binding in bindings)
        )
        part_indexes = [binding["part_index"] for binding in bindings]
        if (
            len(source_entry_ids) == 1
            and all(isinstance(index, int) for index in part_indexes)
            and len(set(part_indexes)) == len(part_indexes)
            and len({binding["field_id"] for binding in bindings}) == len(bindings)
        ):
            continue
        message = (
            "Multiple field-bearing body_structure parts resolve to the same visible "
            "body object. The execution layer cannot represent these interfaces together; "
            "preserve the judgments while this limitation is resolved."
        )
        blockers.append(
            {
                "code": "materialization_body_structure_carrier_conflict",
                "missing_requirement": "one_body_member_per_visible_carrier",
                "why_it_blocks_execution": message,
                "message": message,
                "needed_context": "unit_evidence_packet",
                "evidence_focus": "unit_evidence_packet",
                "source_entry_ids": source_entry_ids,
                "field_ids": list(dict.fromkeys(str(binding["field_id"]) for binding in bindings)),
                "part_indexes": part_indexes,
            }
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
    expected_vocabulary = review.get("field_id_vocabulary")
    expected_document_sha256 = inventory.get("document_sha256")
    if not isinstance(expected_vocabulary, dict) or not review_uses_current_semantic_shape(
        inventory=inventory,
        review=review,
        expected_vocabulary=expected_vocabulary,
        expected_document_sha256=(
            expected_document_sha256 if isinstance(expected_document_sha256, str) else None
        ),
    ):
        return _materialization_readiness_feedback(
            [
                {
                    "code": "materialization_semantic_review_not_current",
                    "missing_requirement": "current_accepted_semantic_review",
                    "why_it_blocks_execution": (
                        "Materialization requires the current accepted review with exact "
                        "Harness-resolved SourceSpans and Word fragments."
                    ),
                    "message": (
                        "The semantic review is missing, stale, or does not exactly match "
                        "the current source inventory."
                    ),
                    "needed_context": "unit_evidence_packet",
                    "evidence_focus": "unit_evidence_packet",
                }
            ]
        )
    blockers: list[JsonObject] = []
    judgments = [item for item in raw_judgments if isinstance(item, dict)]
    cut_points = source_unit_cut_points(validate_inventory_partition(inventory))
    has_executable_intent = any(is_materializable_judgment(judgment) for judgment in judgments)
    has_legacy_shape = False
    for raw_judgment in judgments:
        legacy_fields = sorted(_LEGACY_READINESS_KEYS.intersection(raw_judgment))
        legacy_part_fields = _legacy_part_fields(raw_judgment)
        if legacy_fields or legacy_part_fields:
            has_legacy_shape = True
            blocker = _materialization_readiness_blocker(
                judgment=raw_judgment,
                code="materialization_legacy_shape_unsupported",
                missing_requirement="scope_parts_resolved_spans",
                message=(
                    "Accepted semantic judgments must use source_entry_id, ordered parts, "
                    "and exact Harness-resolved spans. Legacy judgment "
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
                judgment=raw_judgment,
                registry=registry,
            )
        )
        slot_carrier_blocker = _slot_carrier_blocker(raw_judgment)
        if slot_carrier_blocker is not None:
            blockers.append(slot_carrier_blocker)
        body_structure_blocker = _body_structure_member_blocker(raw_judgment, cut_points=cut_points)
        if body_structure_blocker is not None:
            blockers.append(body_structure_blocker)
    blockers.extend(_body_structure_carrier_blockers(
        judgments, cut_points=cut_points, registry=registry,
    ))
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
    blockers = [{**blocker, "recovery": readiness_recovery([blocker])} for blocker in blockers]
    recovery = readiness_recovery(blockers)
    revisable = recovery["action"] == "revise"
    return {
        "schema_version": 1,
        "status": "needs_input" if revisable else "error",
        "recovery": recovery,
        "feedback": {
            "type": "materialization_readiness",
            "mechanical": True,
            "semantic_authority": False,
            "agent_action": (
                "Revise semantic_judgments to use source_entry_id, ordered parts, and "
                "field_id values from the pre-input field vocabulary. "
                "Do not proceed to DOCX materialization until Harness-resolved spans are "
                "present."
            )
            if revisable
            else None,
        },
        "checks": [
            {"name": "materialization_readiness", "result": "needs_input" if revisable else "error"}
        ],
        "blockers": blockers,
        "failure": readiness_failure({"blockers": blockers}).result()["failure"],
        "warnings": [],
    }
