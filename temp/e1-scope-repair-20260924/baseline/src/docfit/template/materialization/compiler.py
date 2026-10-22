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
    AcceptedResolvedSpan,
    MaterializationCompileResult,
    MaterializationFieldBinding,
    MaterializationIntent,
    MaterializationIntentType,
    MaterializationPlan,
    ScopeRef,
    UnsupportedMaterialization,
)
from docfit.template.materialization.vocabulary import review_vocabulary_provenance_errors
from docfit.template.semantic_review import (
    review_has_unique_span_refs,
    review_judgment_has_current_resolved_spans,
)
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

    legacy_unsupported = tuple(
        legacy_item
        for index, judgment in enumerate(_semantic_judgments(review), start=1)
        if (legacy_item := _legacy_shape_unsupported(judgment, index=index)) is not None
    )
    if legacy_unsupported:
        plan = MaterializationPlan(
            plan_ref=f"materialization-plan-{sha256_json(review)[:12]}",
            intents=(),
            unsupported=legacy_unsupported,
            source_review_digest=sha256_json(review),
        )
        return MaterializationCompileResult(plan=plan)

    review_shape_error = _accepted_review_shape_error(review)
    if review_shape_error is not None:
        plan = MaterializationPlan(
            plan_ref=f"materialization-plan-{sha256_json(review)[:12]}",
            intents=(),
            unsupported=(
                _unsupported(
                    index=1,
                    judgment_refs=("semantic_judgments",),
                    scopes=(),
                    reason_code="materialization_semantic_review_not_current",
                    message=review_shape_error,
                    missing_requirements=("current_accepted_semantic_review",),
                ),
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


def _accepted_review_shape_error(review: JsonObject) -> str | None:
    raw_judgments = review.get("semantic_judgments")
    if (
        not isinstance(raw_judgments, list)
        or not raw_judgments
        or any(not isinstance(item, dict) for item in raw_judgments)
    ):
        return "Compiler requires a non-empty accepted semantic_judgments list."
    if review.get("semantic_judgments_sha256") != sha256_json(raw_judgments):
        return "Accepted semantic_judgments digest is missing or stale."
    semantic_judgments = [item for item in raw_judgments if isinstance(item, dict)]
    if not review_has_unique_span_refs(semantic_judgments):
        return "Accepted resolved SourceSpan references must be present and globally unique."
    flattened = [
        span
        for judgment in semantic_judgments
        for span in judgment.get("resolved_spans", [])
        if isinstance(span, dict)
    ]
    if review.get("resolved_spans") != flattened:
        return "Accepted review resolved_spans ledger does not match its judgments."
    document_sha256 = _string_value(review.get("document_sha256"))
    if (
        document_sha256 is None
        or len(document_sha256) != 64
        or any(character not in "0123456789abcdef" for character in document_sha256)
    ):
        return "Accepted review is not bound to a source document sha256."
    for key in ("source_inventory_digest", "unit_projection_digest"):
        digest = review.get(key)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            return "Accepted review lacks its initial inventory and unit partition binding."
    if any(
        span.get("source_inventory_digest") != review["source_inventory_digest"]
        for span in flattened
    ):
        return "Accepted spans differ from the initial source inventory."
    if any(span.get("source_snapshot_sha256") != document_sha256 for span in flattened):
        return "Accepted resolved spans do not match the review source snapshot."
    return None


def _legacy_part_fields(judgment: JsonObject) -> list[str]:
    legacy_fields: set[str] = set()
    for part in ordered_parts(judgment):
        legacy_fields.update(_LEGACY_COMPILER_PART_KEYS.intersection(part))
    return sorted(legacy_fields)


def _legacy_shape_unsupported(
    judgment: JsonObject,
    *,
    index: int,
) -> UnsupportedMaterialization | None:
    legacy_keys = sorted(_LEGACY_COMPILER_KEYS.intersection(judgment))
    legacy_part_keys = _legacy_part_fields(judgment)
    if not legacy_keys and not legacy_part_keys:
        return None
    payload: JsonObject = {}
    if legacy_keys:
        payload["legacy_fields"] = legacy_keys
    if legacy_part_keys:
        payload["legacy_part_fields"] = legacy_part_keys
    return _unsupported(
        index=index,
        judgment_refs=_judgment_refs(judgment, index=index),
        scopes=(),
        reason_code="materialization_legacy_shape_unsupported",
        message=(
            "Compiler accepts only Harness-accepted source_entry_id, ordered parts, "
            "and exact resolved SourceSpans. Legacy judgment fields are not migrated."
        ),
        missing_requirements=("scope_parts_resolved_spans",),
        payload=payload,
    )


def _compile_judgment(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
) -> MaterializationIntent | UnsupportedMaterialization:
    judgment_refs = _judgment_refs(judgment, index=index)
    legacy = _legacy_shape_unsupported(judgment, index=index)
    if legacy is not None:
        return legacy
    scopes = _scope_refs(judgment)
    if not scopes:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_scope_missing",
            message="Semantic judgment has no canonical source_entry_id scope.",
            missing_requirements=("source_entry_id",),
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
    try:
        resolved_spans = _accepted_resolved_spans(judgment, judgment_index=index - 1)
    except ValueError as error:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_resolved_span_invalid",
            message=(
                "Accepted ordered parts must carry exact, parseable Harness-resolved "
                f"SourceSpans and Word fragments: {error}"
            ),
            missing_requirements=("resolved_spans[].word_fragments",),
        )
    intent_type = _intent_type_from_parts(parts)
    if intent_type is None:
        return _unsupported(
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            reason_code="materialization_intent_unclassified",
            message=("Ordered part roles do not form a single executable materialization intent."),
            missing_requirements=("executable_ordered_part_roles",),
        )
    if intent_type == MaterializationIntentType.MATERIALIZE_SLOT:
        return _compile_slot_intent(
            judgment=judgment,
            registry=registry,
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            resolved_spans=resolved_spans,
        )
    if intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE:
        return _compile_body_structure_intent(
            judgment=judgment,
            registry=registry,
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            resolved_spans=resolved_spans,
        )
    if intent_type == MaterializationIntentType.REFRESH_GENERATED_CONTENT:
        return _compile_generated_content_intent(
            judgment=judgment,
            registry=registry,
            index=index,
            judgment_refs=judgment_refs,
            scopes=scopes,
            resolved_spans=resolved_spans,
        )
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=intent_type,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        payload=_typed_payload(judgment, resolved_spans),
        classification_basis=("parts.role",),
        resolved_spans=resolved_spans,
        field_bindings=_field_bindings(judgment, resolved_spans),
    )


def _compile_slot_intent(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
    resolved_spans: tuple[AcceptedResolvedSpan, ...],
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
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=MaterializationIntentType.MATERIALIZE_SLOT,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        field_ids=field_ids,
        payload=_typed_payload(judgment, resolved_spans),
        classification_basis=("parts.role", "parts.field_id", "resolved_spans"),
        resolved_spans=resolved_spans,
        field_bindings=_field_bindings(judgment, resolved_spans),
    )


def _compile_body_structure_intent(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
    resolved_spans: tuple[AcceptedResolvedSpan, ...],
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
    member_bindings = _member_bindings_from_resolved_spans(
        resolved_spans,
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
        **_typed_payload(judgment, resolved_spans),
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
        resolved_spans=resolved_spans,
        field_bindings=_field_bindings(judgment, resolved_spans),
    )


def _compile_generated_content_intent(
    *,
    judgment: JsonObject,
    registry: FieldRegistrySnapshot,
    index: int,
    judgment_refs: tuple[str, ...],
    scopes: tuple[ScopeRef, ...],
    resolved_spans: tuple[AcceptedResolvedSpan, ...],
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
    return MaterializationIntent(
        intent_ref=_intent_ref(index, judgment_refs),
        intent_type=MaterializationIntentType.REFRESH_GENERATED_CONTENT,
        source_judgment_refs=judgment_refs,
        scope_refs=scopes,
        field_ids=field_ids,
        payload=_typed_payload(judgment, resolved_spans),
        classification_basis=("parts.role", "parts.field_id", "resolved_spans"),
        resolved_spans=resolved_spans,
        field_bindings=_field_bindings(judgment, resolved_spans),
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
        "fixed_label",
        "manual_region",
        "style_only",
        "cleanup",
    }:
        return MaterializationIntentType.KEEP_MANUAL_TABLE_CELL
    if role_set == {"manual_region"}:
        return MaterializationIntentType.KEEP_MANUAL_TABLE_CELL
    if "style_only" in role_set and role_set <= {"style_only", "cleanup"}:
        # Both roles remove their exact text. Keep the paragraph carrier and
        # style evidence, as for a standalone style note; do not widen cleanup
        # to DELETE_BLOCK or invent a field binding for either part.
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
    return ()


def _judgment_refs(judgment: JsonObject, *, index: int) -> tuple[str, ...]:
    return (f"semantic_judgments[{index - 1}]",)


def _intent_ref(index: int, judgment_refs: tuple[str, ...]) -> str:
    return f"intent-{index:04d}-{sha256_json({'judgment_refs': judgment_refs})[:8]}"


def _typed_payload(
    judgment: JsonObject,
    resolved_spans: tuple[AcceptedResolvedSpan, ...],
) -> JsonObject:
    payload: JsonObject = {}
    field_ids = explicit_materialization_field_ids(judgment)
    if field_ids:
        payload["field_ids"] = field_ids
    parts = ordered_parts(judgment)
    if parts:
        payload["parts"] = [dict(part) for part in parts]
    if resolved_spans:
        payload["resolved_spans"] = [span.to_json() for span in resolved_spans]
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


def _accepted_resolved_spans(
    judgment: JsonObject,
    *,
    judgment_index: int,
) -> tuple[AcceptedResolvedSpan, ...]:
    if not review_judgment_has_current_resolved_spans(judgment):
        raise ValueError("resolved spans do not match accepted ordered parts")
    raw_spans = judgment.get("resolved_spans")
    assert isinstance(raw_spans, list)
    spans = tuple(AcceptedResolvedSpan.from_json(span) for span in raw_spans)
    if any(span.accepted_json.get("judgment_index") != judgment_index for span in spans):
        raise ValueError("resolved span judgment_index does not match its accepted judgment")
    return spans


def _field_bindings(
    judgment: JsonObject,
    resolved_spans: tuple[AcceptedResolvedSpan, ...],
) -> tuple[MaterializationFieldBinding, ...]:
    spans_by_part = {span.part_index: span for span in resolved_spans}
    bindings: list[MaterializationFieldBinding] = []
    for part_index, part in enumerate(ordered_parts(judgment)):
        field_ids = explicit_field_ids_from_source(part)
        if not field_ids:
            continue
        span = spans_by_part[part_index]
        assert span.slot_ref is not None
        bindings.append(
            MaterializationFieldBinding(
                part_index=part_index,
                role=_part_role(part),
                field_id=field_ids[0],
                span_ref=span.span_ref,
                slot_ref=span.slot_ref,
            )
        )
    return tuple(bindings)


def _member_bindings_from_resolved_spans(
    resolved_spans: tuple[AcceptedResolvedSpan, ...],
    *,
    role: str,
    judgment_refs: tuple[str, ...],
) -> list[JsonObject]:
    bindings: list[JsonObject] = []
    for span in resolved_spans:
        if span.role != role or span.field_id is None:
            continue
        binding: JsonObject = {
            "block_id": span.source_entry_id,
            "member_field_id": span.field_id,
            "source_judgment_refs": list(judgment_refs),
            "source_entry_id": span.source_entry_id,
            "span_ref": span.span_ref,
            "slot_ref": span.slot_ref,
        }
        bindings.append(binding)
    return bindings


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
