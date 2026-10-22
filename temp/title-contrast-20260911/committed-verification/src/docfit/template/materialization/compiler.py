"""Compiler from Harness-accepted ordered semantic parts to materialization intents."""

from __future__ import annotations

from collections.abc import Iterable

from docfit.fields import FieldRegistrySnapshot
from docfit.template.materialization.field_binding import (
    explicit_field_ids_from_source,
    explicit_materialization_field_ids,
    ordered_parts,
)
from docfit.template.materialization.models import (
    MaterializationCompileResult,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
    ScopeRef,
    UnsupportedMaterialization,
)
from docfit.template.materialization.vocabulary import review_vocabulary_provenance_errors
from docfit.tools.runtime import JsonObject, ToolFailure, sha256_json

_LEGACY_COMPILER_KEYS = frozenset(
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
_LEGACY_COMPILER_PART_KEYS = frozenset(
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


def compile_materialization_intents(
    *,
    review: JsonObject,
    registry: FieldRegistrySnapshot,
) -> MaterializationCompileResult:
    """Compile accepted Agent semantics into an internal, deterministic intent plan."""

    vocabulary_errors = review_vocabulary_provenance_errors(review=review, registry=registry)
    if vocabulary_errors:
        plan = MaterializationPlan(
            plan_ref=f"materialization-plan-{sha256_json(review)[:12]}",
            intents=(),
            unsupported=tuple(
                _unsupported_from_vocabulary_error(index, error)
                for index, error in enumerate(vocabulary_errors, start=1)
            ),
            source_review_digest=sha256_json(review),
        )
        return MaterializationCompileResult(plan=plan)

    intents: list[MaterializationIntent] = []
    unsupported: list[UnsupportedMaterialization] = []
    for index, judgment in enumerate(_semantic_judgments(review), start=1):
        compiled = _compile_judgment(
            judgment=judgment,
            registry=registry,
            index=index,
        )
        if isinstance(compiled, MaterializationIntent):
            intents.append(compiled)
        else:
            unsupported.append(compiled)
    plan = MaterializationPlan(
        plan_ref=f"materialization-plan-{sha256_json(review)[:12]}",
        intents=tuple(intents),
        unsupported=tuple(unsupported),
        source_review_digest=sha256_json(review),
    )
    return MaterializationCompileResult(plan=plan)


def _semantic_judgments(review: JsonObject) -> Iterable[JsonObject]:
    raw = review.get("semantic_judgments")
    if not isinstance(raw, list):
        return ()
    return (item for item in raw if isinstance(item, dict))


def _legacy_part_fields(judgment: JsonObject) -> list[str]:
    legacy_fields: set[str] = set()
    for part in ordered_parts(judgment):
        legacy_fields.update(_LEGACY_COMPILER_PART_KEYS.intersection(part))
    return sorted(legacy_fields)


def _compile_judgment(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
) -> MaterializationIntent | UnsupportedMaterialization:
    judgment_refs = _judgment_refs(judgment, index=index)
    legacy_keys = sorted(_LEGACY_COMPILER_KEYS.intersection(judgment))
    legacy_part_keys = _legacy_part_fields(judgment)
    if legacy_keys or legacy_part_keys:
        payload: JsonObject = {}
        if legacy_keys:
            payload["legacy_fields"] = legacy_keys
        if legacy_part_keys:
            payload["legacy_part_fields"] = legacy_part_keys
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=(),
            reason_code="materialization_legacy_shape_unsupported",
            message=(
                "Compiler accepts only Harness-accepted source_entry_id or compatibility "
                "scope, ordered parts, and resolved_spans. Legacy judgment fields are not "
                "migrated."
            ),
            missing_requirements=("scope_parts_resolved_spans",),
            payload=payload,
        )
    scopes = _scope_refs(judgment)
    if not scopes:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_scope_missing",
            message=(
                "Semantic judgment has no source_entry_id or compatibility reading scope."
            ),
            missing_requirements=("source_entry_id_or_compatibility_scope",),
        )
    parts = ordered_parts(judgment)
    if not parts:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_ordered_parts_missing",
            message="Semantic judgment has no accepted ordered parts.",
            missing_requirements=("parts",),
        )
    intent_type = _intent_type_from_parts(parts)
    if intent_type is None:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_intent_unclassified",
            message=(
                "Ordered part roles do not form a single executable materialization intent."
            ),
            missing_requirements=("executable_ordered_part_roles",),
        )
    if intent_type == MaterializationIntentType.MATERIALIZE_SLOT:
        return _compile_slot_intent(
            judgment=judgment,
            registry=registry,
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
        )
    if intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE:
        return _compile_body_structure_intent(
            judgment=judgment,
            registry=registry,
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
        )
    if intent_type == MaterializationIntentType.REFRESH_GENERATED_CONTENT:
        return _compile_generated_content_intent(
            judgment=judgment,
            registry=registry,
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
        )
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=intent_type,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        payload=_typed_payload(judgment),
        classification_basis=("parts.role",),
    )


def _compile_slot_intent(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
) -> MaterializationIntent | UnsupportedMaterialization:
    field_ids = tuple(_field_ids_for_role(judgment, "fill_slot"))
    if not field_ids:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_slot_field_missing",
            message="Materialize-slot intent is missing part-level field_id.",
            missing_requirements=("parts[].field_id",),
        )
    unknown = _unknown_registry_fields(registry, field_ids)
    if unknown:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_field_vocabulary_registry_mismatch",
            message=(
                "Materialize-slot intent references field_id values outside the "
                "accepted pre-input field vocabulary."
            ),
            missing_requirements=("field_id_vocabulary.allowed_field_ids",),
            payload={"unknown_field_ids": list(unknown)},
        )
    span_blocker = _span_requirements_blocker(
        judgment=judgment,
        index=index,
        judgment_refs=judgment_refs,
        scopes=scopes,
        roles=("fill_slot",),
    )
    if span_blocker is not None:
        return span_blocker
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=MaterializationIntentType.MATERIALIZE_SLOT,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        field_ids=field_ids,
        payload=_typed_payload(judgment),
        classification_basis=("parts.role", "parts.field_id", "resolved_spans"),
    )


def _compile_body_structure_intent(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
) -> MaterializationIntent | UnsupportedMaterialization:
    members = tuple(_field_ids_for_role(judgment, "body_structure", dedupe=False))
    if not members:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_body_structure_semantics_missing",
            message=(
                "Body-structure intent is missing ordered body_structure parts with field_id."
            ),
            missing_requirements=("parts[].field_id",),
        )
    unknown = _unknown_registry_fields(registry, members)
    if unknown:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_field_vocabulary_registry_mismatch",
            message=(
                "Body-structure intent references field_id values outside the accepted "
                "pre-input field vocabulary."
            ),
            missing_requirements=("field_id_vocabulary.allowed_field_ids",),
            payload={"unknown_field_ids": list(unknown)},
        )
    structure_ref = _common_parent_field_id(registry, members)
    if structure_ref is None:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_body_structure_parent_missing",
            message=(
                "Body-structure parts must point to Registry fields with one common "
                "parent_field_id. The compiler will not supply a default structure field."
            ),
            missing_requirements=("registry_parent_field_id",),
            payload={"member_field_ids": list(members)},
        )
    if _unknown_registry_fields(registry, (structure_ref,)):
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_field_vocabulary_registry_mismatch",
            message=(
                "Body-structure parent_field_id is not bound to the current accepted "
                "field vocabulary Registry snapshot."
            ),
            missing_requirements=("field_id_vocabulary.registry",),
            payload={"unknown_field_ids": [structure_ref]},
        )
    span_blocker = _span_requirements_blocker(
        judgment=judgment,
        index=index,
        judgment_refs=judgment_refs,
        scopes=scopes,
        roles=("body_structure",),
    )
    if span_blocker is not None:
        return span_blocker
    member_bindings = _member_bindings_from_resolved_spans(
        judgment,
        role="body_structure",
        judgment_refs=judgment_refs,
    )
    if len(member_bindings) != len(members):
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_body_structure_block_scope_missing",
            message=(
                "Body-structure materialization requires Harness-resolved spans that "
                "map each member part back to a source-entry execution target."
            ),
            missing_requirements=("resolved_spans[].source_entry_id_or_covered_scope",),
        )
    field_ids = tuple(dict.fromkeys(members))
    payload = {
        **_typed_payload(judgment),
        "structure_ref": structure_ref,
        "members": list(members),
        "member_bindings": member_bindings,
        "structure_ref_provenance": {
            "source": "registry_parent_field_id",
            "member_field_ids": list(members),
        },
    }
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        field_ids=field_ids,
        payload=payload,
        classification_basis=(
            "parts.role",
            "parts.field_id",
            "resolved_spans",
            "registry.parent_field_id",
        ),
    )


def _compile_generated_content_intent(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
) -> MaterializationIntent | UnsupportedMaterialization:
    field_ids = tuple(_field_ids_for_role(judgment, "generated_content"))
    if not field_ids:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_generated_content_field_missing",
            message="Generated-content intent is missing part-level field_id.",
            missing_requirements=("parts[].field_id",),
        )
    unknown = _unknown_registry_fields(registry, field_ids)
    if unknown:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_field_vocabulary_registry_mismatch",
            message=(
                "Generated-content intent references field_id values outside the "
                "accepted pre-input field vocabulary."
            ),
            missing_requirements=("field_id_vocabulary.allowed_field_ids",),
            payload={"unknown_field_ids": list(unknown)},
        )
    span_blocker = _span_requirements_blocker(
        judgment=judgment,
        index=index,
        judgment_refs=judgment_refs,
        scopes=scopes,
        roles=("generated_content",),
    )
    if span_blocker is not None:
        return span_blocker
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=MaterializationIntentType.REFRESH_GENERATED_CONTENT,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        field_ids=field_ids,
        payload=_typed_payload(judgment),
        classification_basis=("parts.role", "parts.field_id", "resolved_spans"),
    )


def _intent_type_from_parts(parts: list[JsonObject]) -> MaterializationIntentType | None:
    roles = [_part_role(part) for part in parts]
    role_set = set(roles)
    if "fill_slot" in role_set:
        return MaterializationIntentType.MATERIALIZE_SLOT
    if "body_structure" in role_set:
        return MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
    if "generated_content" in role_set:
        return MaterializationIntentType.REFRESH_GENERATED_CONTENT
    if "fixed_label" in role_set and role_set <= {"fixed_label", "style_only", "cleanup"}:
        return MaterializationIntentType.KEEP_FIXED_CONTENT
    if "manual_region" in role_set and role_set <= {
        "manual_region",
        "style_only",
        "cleanup",
    }:
        return MaterializationIntentType.KEEP_MANUAL_TABLE_CELL
    if role_set == {"manual_region"}:
        return MaterializationIntentType.KEEP_MANUAL_TABLE_CELL
    if role_set == {"style_only"}:
        return MaterializationIntentType.TRANSFER_STYLE_ONLY
    if role_set == {"cleanup"}:
        return MaterializationIntentType.DELETE_BLOCK
    if role_set == {"fixed_label"}:
        return MaterializationIntentType.KEEP_FIXED_CONTENT
    if not role_set:
        return MaterializationIntentType.NO_OP
    return None


def _scope_refs(judgment: JsonObject) -> tuple[ScopeRef, ...]:
    source_entry_id = _string_value(judgment.get("source_entry_id"))
    if source_entry_id is not None:
        return (ScopeRef(kind="source_entry", ref_id=source_entry_id),)
    scope = judgment.get("scope")
    if not isinstance(scope, dict):
        return ()
    reading_block_id = _string_value(scope.get("reading_block_id"))
    reading_range_id = _string_value(scope.get("reading_range_id"))
    if reading_block_id is not None and reading_range_id is None:
        return (ScopeRef(kind="reading_block", ref_id=reading_block_id),)
    if reading_range_id is not None and reading_block_id is None:
        return (ScopeRef(kind="reading_range", ref_id=reading_range_id),)
    return ()


def _judgment_refs(judgment: JsonObject, *, index: int) -> tuple[str, ...]:
    return (f"semantic_judgments[{index - 1}]",)


def _intent_ref(index: int, judgment_refs: tuple[str, ...]) -> str:
    return f"intent-{index:04d}-{sha256_json({'judgment_refs': judgment_refs})[:8]}"


def _typed_payload(judgment: JsonObject) -> JsonObject:
    payload: JsonObject = {}
    field_ids = explicit_materialization_field_ids(judgment)
    if field_ids:
        payload["field_ids"] = field_ids
    parts = ordered_parts(judgment)
    if parts:
        payload["parts"] = [dict(part) for part in parts]
    resolved_spans = _resolved_spans(judgment)
    if resolved_spans:
        payload["resolved_spans"] = [dict(span) for span in resolved_spans]
    return payload


def _unsupported(
    *,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
    reason_code: str,
    message: str,
    missing_requirements: tuple[str, ...],
    payload: JsonObject | None = None,
) -> UnsupportedMaterialization:
    return UnsupportedMaterialization(
        unsupported_ref=f"unsupported-{index:04d}",
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        reason_code=reason_code,
        message=message,
        missing_requirements=missing_requirements,
        payload=payload or {},
    )


def _unsupported_from_vocabulary_error(
    index: int,
    error: JsonObject,
) -> UnsupportedMaterialization:
    code = _string_value(error.get("code")) or "materialization_field_vocabulary_invalid"
    message = _string_value(error.get("message")) or (
        "Materialization requires accepted pre-input field vocabulary provenance."
    )
    missing = _string_value(error.get("missing_requirement")) or "field_id_vocabulary"
    payload = error.get("payload")
    return _unsupported(
        index=index,
        judgment_refs=("semantic_judgments",),
        scopes=(),
        reason_code=code,
        message=message,
        missing_requirements=(missing,),
        payload=payload if isinstance(payload, dict) else {},
    )


def _unknown_registry_fields(
    registry: FieldRegistrySnapshot,
    field_ids: tuple[str, ...],
) -> tuple[str, ...]:
    unknown: list[str] = []
    for field_id in field_ids:
        try:
            registry.lookup(field_id)
        except ToolFailure:
            unknown.append(field_id)
    return tuple(unknown)


def _field_ids_for_role(
    judgment: JsonObject,
    role: str,
    *,
    dedupe: bool = True,
) -> list[str]:
    field_ids: list[str] = []
    for part in ordered_parts(judgment):
        if _part_role(part) == role:
            field_ids.extend(explicit_field_ids_from_source(part))
    return list(dict.fromkeys(field_ids)) if dedupe else field_ids


def _part_role(part: JsonObject) -> str:
    role = part.get("role")
    return role.strip() if isinstance(role, str) else ""


def _resolved_spans(judgment: JsonObject) -> list[JsonObject]:
    raw_spans = judgment.get("resolved_spans")
    if not isinstance(raw_spans, list):
        return []
    return [span for span in raw_spans if isinstance(span, dict)]


def _span_requirements_blocker(
    *,
    judgment: JsonObject,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
    roles: tuple[str, ...],
) -> UnsupportedMaterialization | None:
    spans_by_part = {
        span.get("part_index"): span
        for span in _resolved_spans(judgment)
        if isinstance(span.get("part_index"), int)
    }
    missing: list[int] = []
    mismatched: list[int] = []
    incomplete: list[int] = []
    slot_ref_mismatched: list[int] = []
    for part_index, part in enumerate(ordered_parts(judgment)):
        role = _part_role(part)
        if role not in roles:
            continue
        span = spans_by_part.get(part_index)
        if span is None:
            missing.append(part_index)
            continue
        part_field_ids = explicit_field_ids_from_source(part)
        span_field = _string_value(span.get("field_id"))
        if part_field_ids and span_field != part_field_ids[0]:
            mismatched.append(part_index)
        span_ref = _string_value(span.get("span_ref"))
        slot_ref = _string_value(span.get("slot_ref"))
        if span_ref is None or (part_field_ids and slot_ref is None):
            incomplete.append(part_index)
        elif (
            part_field_ids
            and slot_ref != f"{span_ref};field_id={part_field_ids[0]}"
        ):
            slot_ref_mismatched.append(part_index)
    if not missing and not mismatched and not incomplete and not slot_ref_mismatched:
        return None
    payload: JsonObject = {}
    if missing:
        payload["missing_part_indices"] = missing
    if mismatched:
        payload["field_mismatch_part_indices"] = mismatched
    if incomplete:
        payload["incomplete_provenance_part_indices"] = incomplete
    if slot_ref_mismatched:
        payload["slot_ref_mismatch_part_indices"] = slot_ref_mismatched
    return _unsupported(
        index=index,
        judgment_refs=judgment_refs,
        scopes=scopes,
        reason_code="materialization_resolved_span_missing",
        message=(
            "Executable ordered parts must include matching Harness-resolved span_ref "
            "and slot_ref provenance."
        ),
        missing_requirements=("resolved_spans",),
        payload=payload,
    )


def _member_bindings_from_resolved_spans(
    judgment: JsonObject,
    *,
    role: str,
    judgment_refs: tuple[str, ...],
) -> list[JsonObject]:
    spans_by_part = {
        span.get("part_index"): span
        for span in _resolved_spans(judgment)
        if isinstance(span.get("part_index"), int)
    }
    bindings: list[JsonObject] = []
    for part_index, part in enumerate(ordered_parts(judgment)):
        if _part_role(part) != role:
            continue
        span = spans_by_part.get(part_index)
        if span is None:
            continue
        execution_scope_id = _span_execution_scope_id(span)
        field_ids = explicit_field_ids_from_source(part)
        if execution_scope_id is None or not field_ids:
            continue
        binding: JsonObject = {
            "block_id": execution_scope_id,
            "member_field_id": field_ids[0],
            "source_judgment_refs": list(judgment_refs),
        }
        source_entry_id = _span_source_entry_id(span)
        if source_entry_id is not None:
            binding["source_entry_id"] = source_entry_id
        covered_object_ids = _span_covered_object_ids(span)
        if covered_object_ids:
            binding["covered_object_ids"] = covered_object_ids
        span_ref = _string_value(span.get("span_ref"))
        slot_ref = _string_value(span.get("slot_ref"))
        if span_ref is not None:
            binding["span_ref"] = span_ref
        if slot_ref is not None:
            binding["slot_ref"] = slot_ref
        bindings.append(binding)
    return bindings


def _span_execution_scope_id(span: JsonObject) -> str | None:
    source_entry_id = _span_source_entry_id(span)
    if source_entry_id is not None:
        return source_entry_id
    scope = span.get("scope")
    if isinstance(scope, dict):
        block_id = _string_value(scope.get("reading_block_id"))
        if block_id is not None:
            return block_id
    return _string_value(span.get("reading_block_id"))


def _span_source_entry_id(span: JsonObject) -> str | None:
    source_entry_id = _string_value(span.get("source_entry_id"))
    if source_entry_id is not None:
        return source_entry_id
    scope = span.get("scope")
    if isinstance(scope, dict):
        source_entry_id = _string_value(scope.get("source_entry_id"))
        if source_entry_id is not None:
            return source_entry_id
    raw_spans = span.get("source_entry_spans")
    if isinstance(raw_spans, list):
        ids = [
            source_entry_id
            for item in raw_spans
            if isinstance(item, dict)
            and (source_entry_id := _string_value(item.get("source_entry_id")))
            is not None
        ]
        unique = tuple(dict.fromkeys(ids))
        if len(unique) == 1:
            return unique[0]
    return None


def _span_covered_object_ids(span: JsonObject) -> list[str]:
    raw_ids = span.get("covered_object_ids")
    if not isinstance(raw_ids, list):
        return []
    return list(
        dict.fromkeys(
            item.strip() for item in raw_ids if isinstance(item, str) and item.strip()
        )
    )


def _common_parent_field_id(
    registry: FieldRegistrySnapshot,
    field_ids: tuple[str, ...],
) -> str | None:
    parents: list[str] = []
    for field_id in field_ids:
        field = registry.lookup(field_id)
        parent = _string_value(field.get("parent_field_id"))
        if parent is not None:
            parents.append(parent)
    unique = tuple(dict.fromkeys(parents))
    return unique[0] if len(unique) == 1 else None


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None
