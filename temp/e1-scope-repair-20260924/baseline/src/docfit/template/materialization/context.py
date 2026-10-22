"""Resolve materialization contexts from accepted SourceSpans only."""

from __future__ import annotations

from docfit.template.materialization.models import (
    AcceptedResolvedSpan,
    MaterializationContext,
    MaterializationContextKind,
    MaterializationContextResolution,
    MaterializationIntent,
    MaterializationIntentType,
    UnsupportedMaterialization,
)
from docfit.template.source_spans import (
    SourceSpanResolutionError,
    parse_source_span_ref,
    resolve_source_span,
)
from docfit.tools.runtime import JsonObject, sha256_json


def resolve_materialization_contexts(
    *,
    inventory: JsonObject,
    intents: tuple[MaterializationIntent, ...],
) -> MaterializationContextResolution:
    contexts: list[MaterializationContext] = []
    unsupported: list[UnsupportedMaterialization] = []
    for position, intent in enumerate(intents, start=1):
        error = _resolved_span_error(inventory=inventory, intent=intent)
        if error is not None:
            code, message = error
            unsupported.append(
                UnsupportedMaterialization(
                    unsupported_ref=f"context-unsupported-{position:04d}",
                    source_judgment_refs=intent.source_judgment_refs,
                    scope_refs=intent.scope_refs,
                    reason_code=code,
                    message=message,
                    missing_requirements=("current_resolved_source_spans",),
                )
            )
            continue
        accepted_spans = [span.to_json() for span in intent.resolved_spans]
        contexts.append(
            MaterializationContext(
                context_ref=_context_ref(position, intent.intent_ref),
                kind=_context_kind(intent).value,
                scope_refs=intent.scope_refs,
                facts={
                    "intent_ref": intent.intent_ref,
                    "intent_type": intent.intent_type.value,
                    "resolved_spans": accepted_spans,
                    "word_fragments": [
                        fragment
                        for span in intent.resolved_spans
                        for fragment in span.word_fragments
                    ],
                },
            )
        )
    return MaterializationContextResolution(
        contexts=tuple(contexts),
        unsupported=tuple(unsupported),
    )


def _resolved_span_error(
    *,
    inventory: JsonObject,
    intent: MaterializationIntent,
) -> tuple[str, str] | None:
    if not intent.resolved_spans:
        return (
            "materialization_resolved_span_missing",
            "Intent has no typed Harness-resolved SourceSpans; target selection is blocked.",
        )
    intent_source_entries = {
        scope.ref_id for scope in intent.scope_refs if scope.kind == "source_entry"
    }
    if len(intent_source_entries) != 1:
        return (
            "materialization_legacy_source_scope_unsupported",
            "Intent target scope must be the accepted canonical source_entry_id only.",
        )
    for span in intent.resolved_spans:
        if span.source_entry_id not in intent_source_entries:
            return (
                "materialization_resolved_span_scope_mismatch",
                "Intent scope does not match its accepted resolved SourceSpan target.",
            )
        error = _current_span_error(inventory=inventory, span=span)
        if error is not None:
            return error
    return None


def _current_span_error(
    *,
    inventory: JsonObject,
    span: AcceptedResolvedSpan,
) -> tuple[str, str] | None:
    parsed = parse_source_span_ref(span.span_ref)
    if parsed is None:
        return (
            "materialization_resolved_span_unparseable",
            "Accepted span_ref is not a canonical SourceSpan reference.",
        )
    _, source_span = parsed
    try:
        current = resolve_source_span(inventory=inventory, source_span=source_span)
    except (SourceSpanResolutionError, ValueError):
        return (
            "materialization_resolved_span_unresolvable",
            "Accepted SourceSpan no longer resolves exactly in the current inventory.",
        )
    if not span.matches(current):
        return (
            "materialization_resolved_span_stale",
            (
                "Accepted SourceSpan snapshot, inventory digest, source content, or Word "
                "fragments differ from the current Harness resolution."
            ),
        )
    return None


def _context_kind(intent: MaterializationIntent) -> MaterializationContextKind:
    return {
        MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE: (
            MaterializationContextKind.BODY_STRUCTURE
        ),
        MaterializationIntentType.KEEP_MANUAL_TABLE_CELL: (
            MaterializationContextKind.MANUAL_TABLE_CELL
        ),
        MaterializationIntentType.REFRESH_GENERATED_CONTENT: (
            MaterializationContextKind.GENERATED_CONTENT
        ),
        MaterializationIntentType.TRANSFER_STYLE_ONLY: MaterializationContextKind.STYLE_ONLY,
        MaterializationIntentType.DELETE_BLOCK: MaterializationContextKind.CLEANUP_BLOCK,
        MaterializationIntentType.KEEP_FIXED_CONTENT: MaterializationContextKind.FIXED_CONTENT,
        MaterializationIntentType.MATERIALIZE_SLOT: MaterializationContextKind.FIELD_SLOT,
        MaterializationIntentType.NO_OP: MaterializationContextKind.UNIT_SCOPE,
    }.get(intent.intent_type, MaterializationContextKind.UNKNOWN)


def _context_ref(position: int, intent_ref: str) -> str:
    return f"context-{position:04d}-{sha256_json({'intent_ref': intent_ref})[:8]}"
