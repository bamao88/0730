from __future__ import annotations

from docfit.template.materialization import (
    MaterializationContextKind,
    MaterializationIntent,
    MaterializationIntentType,
    ScopeRef,
)
from docfit.template.materialization.context import resolve_materialization_contexts
from docfit.template.materialization.models import AcceptedResolvedSpan
from docfit.template.source_spans import resolve_semantic_judgments
from tests.support.source_identity import source_partition


def _inventory(*entries: tuple[str, str]) -> dict[str, object]:
    document_sha256 = "a" * 64
    source_entries: list[dict[str, object]] = []
    objects: list[dict[str, object]] = []
    for index, (source_entry_id, text) in enumerate(entries):
        object_id = f"obj-{index:04d}"
        fingerprint = f"{index + 1:064x}"
        locator = f"/body/p[{index + 1}]/r[1]"
        object_ref = {
            "document_sha256": document_sha256,
            "expected_fingerprint": fingerprint,
            "object_id": object_id,
        }
        source_entries.append(
            {
                "source_entry_id": source_entry_id,
                "text": text,
                "entry_type": "text",
                "source_order": {"block": index + 1, "inline": 0},
                "extent": {"kind": "text", "start": 0, "end": len(text)},
                "provenance": [
                    {
                        "object_id": object_id,
                        "locator": locator,
                        "text_span": [0, len(text)],
                        "object_ref": object_ref,
                        "fingerprint": fingerprint,
                    }
                ],
            }
        )
        objects.append(
            {
                "object_id": object_id,
                "type": "run",
                "locator": locator,
                "source_entry_id": source_entry_id,
                "object_ref": object_ref,
                "fingerprint": fingerprint,
            }
        )
    return {
        "document_sha256": document_sha256,
        "source_entries": source_entries,
        "objects": objects,
        "reading_blocks": [],
    }


def _intent(
    inventory: dict[str, object],
    intent_type: MaterializationIntentType,
    *,
    source_entry_id: str,
    text: str,
    field_ids: tuple[str, ...] = (),
) -> MaterializationIntent:
    part: dict[str, object] = {"text": text, "role": "fixed_label"}
    if intent_type == MaterializationIntentType.MATERIALIZE_SLOT:
        part["role"] = "fill_slot"
        part["field_id"] = field_ids[0]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=[{"source_entry_id": source_entry_id, "parts": [part]}],
    )
    accepted_spans = tuple(AcceptedResolvedSpan.from_json(span) for span in resolved)
    return MaterializationIntent(
        intent_ref=f"intent-{source_entry_id}",
        intent_type=intent_type,
        source_judgment_refs=("semantic_judgments[0]",),
        scope_refs=(ScopeRef(kind="source_entry", ref_id=source_entry_id),),
        field_ids=field_ids,
        payload={"resolved_spans": resolved},
        resolved_spans=accepted_spans,
    )


def test_context_resolver_classifies_from_intent_without_text_target_selection() -> None:
    source_entry_id = "source-entry-heading"
    text = "致□□谢（小三号黑体，居中）"
    inventory = _inventory((source_entry_id, text))

    result = resolve_materialization_contexts(
        inventory=inventory,
        intents=(
            _intent(
                inventory,
                MaterializationIntentType.KEEP_FIXED_CONTENT,
                source_entry_id=source_entry_id,
                text=text,
            ),
        ),
    )

    assert result.ready is True
    context = result.contexts[0]
    assert context.kind == MaterializationContextKind.FIXED_CONTENT.value
    assert context.facts["resolved_spans"][0]["expected_source_content"] == text
    assert "reading_blocks" not in context.facts


def test_context_resolver_does_not_infer_slot_kind_from_source_text() -> None:
    entries = (
        ("source-entry-abstract", "□□摘□要：……"),
        ("source-entry-advisor", "指导教师及职称"),
    )
    inventory = _inventory(*entries)
    field_ids = ("abstract.zh", "advisor.name.zh")
    judgments = [
        {
            "source_entry_id": source_entry_id,
            "parts": [{"text": text, "role": "fill_slot", "field_id": field_id}],
        }
        for (source_entry_id, text), field_id in zip(entries, field_ids, strict=True)
    ]
    source_partition(inventory)
    resolved = resolve_semantic_judgments(
        inventory=inventory,
        judgments=judgments,
    )
    intents = tuple(
        MaterializationIntent(
            intent_ref=f"intent-{source_entry_id}",
            intent_type=MaterializationIntentType.MATERIALIZE_SLOT,
            source_judgment_refs=(f"semantic_judgments[{index}]",),
            scope_refs=(ScopeRef(kind="source_entry", ref_id=source_entry_id),),
            field_ids=(field_id,),
            payload={
                "resolved_spans": [span for span in resolved if span.get("judgment_index") == index]
            },
            resolved_spans=tuple(
                AcceptedResolvedSpan.from_json(span)
                for span in resolved
                if span.get("judgment_index") == index
            ),
        )
        for index, ((source_entry_id, _), field_id) in enumerate(
            zip(entries, field_ids, strict=True)
        )
    )

    result = resolve_materialization_contexts(
        inventory=inventory,
        intents=intents,
    )

    assert [context.kind for context in result.contexts] == [
        MaterializationContextKind.FIELD_SLOT.value,
        MaterializationContextKind.FIELD_SLOT.value,
    ]


def test_context_resolver_preserves_canonical_source_entry_span_and_fragments() -> None:
    source_entry_id = "source-entry-cover-title"
    text = "论文题目：×××"
    inventory = _inventory((source_entry_id, text))

    result = resolve_materialization_contexts(
        inventory=inventory,
        intents=(
            _intent(
                inventory,
                MaterializationIntentType.MATERIALIZE_SLOT,
                source_entry_id=source_entry_id,
                text=text,
                field_ids=("thesis.title.zh",),
            ),
        ),
    )

    assert result.ready is True
    context = result.contexts[0]
    assert context.scope_refs == (ScopeRef(kind="source_entry", ref_id=source_entry_id),)
    assert context.facts["resolved_spans"][0]["source_entry_id"] == source_entry_id
    assert context.facts["word_fragments"] == context.facts["resolved_spans"][0]["word_fragments"]


def test_context_resolver_rejects_retired_range_and_unit_scopes() -> None:
    source_entry_id = "source-entry-form"
    text = "开题报告表"
    inventory = _inventory((source_entry_id, text))
    current = _intent(
        inventory,
        MaterializationIntentType.KEEP_MANUAL_TABLE_CELL,
        source_entry_id=source_entry_id,
        text=text,
    )
    legacy_intents = tuple(
        MaterializationIntent(
            intent_ref=f"intent-{kind}",
            intent_type=MaterializationIntentType.KEEP_MANUAL_TABLE_CELL,
            source_judgment_refs=("semantic_judgments[0]",),
            scope_refs=(ScopeRef(kind=kind, ref_id=ref_id),),
            payload=current.payload,
            resolved_spans=current.resolved_spans,
        )
        for kind, ref_id in (
            ("reading_range", "u-form:range-0001"),
            ("unit", "u-form"),
        )
    )

    result = resolve_materialization_contexts(
        inventory=inventory,
        intents=legacy_intents,
    )

    assert result.ready is False
    assert [item.reason_code for item in result.unsupported] == [
        "materialization_legacy_source_scope_unsupported",
        "materialization_legacy_source_scope_unsupported",
    ]


def test_context_resolver_rejects_scope_that_disagrees_with_resolved_span() -> None:
    source_entry_id = "source-entry-title"
    text = "论文题目"
    inventory = _inventory((source_entry_id, text))
    current = _intent(
        inventory,
        MaterializationIntentType.KEEP_FIXED_CONTENT,
        source_entry_id=source_entry_id,
        text=text,
    )
    mismatched = MaterializationIntent(
        intent_ref="intent-mismatched",
        intent_type=MaterializationIntentType.KEEP_FIXED_CONTENT,
        source_judgment_refs=current.source_judgment_refs,
        scope_refs=(ScopeRef(kind="source_entry", ref_id="source-entry-other"),),
        payload=current.payload,
        resolved_spans=current.resolved_spans,
    )

    result = resolve_materialization_contexts(
        inventory=inventory,
        intents=(mismatched,),
    )

    assert result.ready is False
    assert result.contexts == ()
    assert result.unsupported[0].reason_code == ("materialization_resolved_span_scope_mismatch")
