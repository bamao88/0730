"""Typed post-unit materialization planning models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any, Literal

from docfit.template.source_spans import (
    ResolvedSourceSpan,
    TextSourceExtent,
    WholeEntrySourceExtent,
    parse_source_span_ref,
)
from docfit.tools.runtime import JsonObject


class MaterializationIntentType(StrEnum):
    # Legacy name for cleanup-only judgments. It grants no block-level scope:
    # cleanup_kind lowers accepted fragments to text or an exact object.
    DELETE_BLOCK = "delete_block"
    KEEP_FIXED_CONTENT = "keep_fixed_content"
    MATERIALIZE_SLOT = "materialize_slot"
    MATERIALIZE_BODY_STRUCTURE = "materialize_body_structure"
    KEEP_MANUAL_TABLE_CELL = "keep_manual_table_cell"
    TRANSFER_STYLE_ONLY = "transfer_style_only"
    REFRESH_GENERATED_CONTENT = "refresh_generated_content"
    NO_OP = "no_op"
    UNRESOLVED = "unresolved"


class MaterializationContextKind(StrEnum):
    BODY_STRUCTURE = "body_structure"
    CLEANUP_BLOCK = "cleanup_block"
    FIELD_SLOT = "field_slot"
    FIXED_CONTENT = "fixed_content"
    FIXED_HEADING = "fixed_heading"
    GENERATED_CONTENT = "generated_content"
    INSTRUCTION_NOTE = "instruction_note"
    MANUAL_TABLE_CELL = "manual_table_cell"
    PARAGRAPH_INDENT = "paragraph_indent"
    SAMPLE_VALUE = "sample_value"
    STYLE_ONLY = "style_only"
    UNIT_SCOPE = "unit_scope"
    UNKNOWN = "unknown"


class MutationCommandType(StrEnum):
    REMOVE_BLOCK = "remove_block"
    CLEAR_TEXT = "clear_text"
    STRIP_INSTRUCTION_TEXT = "strip_instruction_text"
    MATERIALIZE_SLOT = "materialize_slot"
    MATERIALIZE_STRUCTURE = "materialize_structure"
    TRANSFER_STYLE = "transfer_style"
    NO_OP = "no_op"


MaterializationStatus = Literal["ok", "needs_input", "error"]


def _clean_required(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _clean_tuple(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    cleaned = tuple(dict.fromkeys(item.strip() for item in values if item.strip()))
    if not cleaned:
        raise ValueError(f"{field_name} must contain at least one non-empty value")
    return cleaned


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if hasattr(value, "to_json"):
        return value.to_json()
    return value


@dataclass(frozen=True)
class ScopeRef:
    kind: str
    ref_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _clean_required(self.kind, field_name="kind"))
        object.__setattr__(self, "ref_id", _clean_required(self.ref_id, field_name="ref_id"))

    def to_json(self) -> JsonObject:
        return {"kind": self.kind, "ref_id": self.ref_id}


@dataclass(frozen=True)
class AcceptedResolvedSpan:
    """A validated, lossless view of one Harness-resolved accepted part span."""

    span_ref: str
    source_entry_id: str
    source_snapshot_sha256: str
    source_inventory_digest: str
    part_index: int
    role: str
    text: str
    field_id: str | None
    slot_ref: str | None
    word_fragments: tuple[JsonObject, ...]
    accepted_json: JsonObject = field(repr=False, compare=False)

    @classmethod
    def from_json(cls, value: JsonObject) -> AcceptedResolvedSpan:
        span_ref = _clean_required_string(value.get("span_ref"), "span_ref")
        parsed = parse_source_span_ref(span_ref)
        if parsed is None:
            raise ValueError("span_ref is not a canonical SourceSpan reference")
        parsed_snapshot, source_span = parsed
        source_entry_id = _clean_required_string(
            value.get("source_entry_id"), "source_entry_id"
        )
        source_snapshot_sha256 = _clean_sha256(
            value.get("source_snapshot_sha256"), "source_snapshot_sha256"
        )
        source_inventory_digest = _clean_sha256(
            value.get("source_inventory_digest"), "source_inventory_digest"
        )
        if parsed_snapshot != source_snapshot_sha256:
            raise ValueError("span_ref source snapshot does not match resolved span")
        if source_span.source_entry_id != source_entry_id:
            raise ValueError("span_ref source entry does not match resolved span")
        if value.get("scope") != {"source_entry_id": source_entry_id}:
            raise ValueError("resolved span scope must name only its source_entry_id")
        _validate_extent(value, source_span.extent)

        part_index = value.get("part_index")
        if not isinstance(part_index, int) or isinstance(part_index, bool) or part_index < 0:
            raise ValueError("part_index must be a non-negative integer")
        role = _clean_required_string(value.get("role"), "role")
        text = value.get("text")
        expected_source_content = value.get("expected_source_content")
        if not isinstance(text, str) or expected_source_content != text:
            raise ValueError("resolved span text must equal expected_source_content")

        field_id = _clean_optional_string(value.get("field_id"), "field_id")
        slot_ref = _clean_optional_string(value.get("slot_ref"), "slot_ref")
        if field_id is None:
            if "field_id" in value or "slot_ref" in value:
                raise ValueError("field-less resolved spans cannot carry field_id or slot_ref")
        elif slot_ref != f"{span_ref};field_id={field_id}":
            raise ValueError("slot_ref must derive from span_ref and field_id")

        raw_fragments = value.get("word_fragments")
        if not isinstance(raw_fragments, list) or not raw_fragments:
            raise ValueError("word_fragments must contain exact Harness-resolved fragments")
        fragments = tuple(
            _validated_fragment(
                fragment,
                source_snapshot_sha256=source_snapshot_sha256,
                whole_entry=isinstance(source_span.extent, WholeEntrySourceExtent),
            )
            for fragment in raw_fragments
        )
        _validate_fragment_coverage(
            value=value,
            fragments=fragments,
            extent=source_span.extent,
            text=text,
        )
        return cls(
            span_ref=span_ref,
            source_entry_id=source_entry_id,
            source_snapshot_sha256=source_snapshot_sha256,
            source_inventory_digest=source_inventory_digest,
            part_index=part_index,
            role=role,
            text=text,
            field_id=field_id,
            slot_ref=slot_ref,
            word_fragments=fragments,
            accepted_json=_json_ready(value),
        )

    def to_json(self) -> JsonObject:
        return {key: _json_ready(item) for key, item in self.accepted_json.items()}

    def matches(self, resolved: ResolvedSourceSpan) -> bool:
        return (
            resolved.source_snapshot_sha256 == self.source_snapshot_sha256
            and resolved.inventory_digest == self.source_inventory_digest
            and resolved.source_span.source_entry_id == self.source_entry_id
            and resolved.expected_source_content == self.text
            and [fragment.to_json() for fragment in resolved.word_fragments]
            == list(self.word_fragments)
        )


@dataclass(frozen=True)
class MaterializationFieldBinding:
    part_index: int
    role: str
    field_id: str
    span_ref: str
    slot_ref: str

    def to_json(self) -> JsonObject:
        return {
            "part_index": self.part_index,
            "role": self.role,
            "field_id": self.field_id,
            "span_ref": self.span_ref,
            "slot_ref": self.slot_ref,
        }


@dataclass(frozen=True)
class MaterializationContext:
    context_ref: str
    kind: str
    scope_refs: tuple[ScopeRef, ...]
    facts: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "context_ref",
            _clean_required(self.context_ref, field_name="context_ref"),
        )
        object.__setattr__(self, "kind", _clean_required(self.kind, field_name="kind"))
        if not self.scope_refs:
            raise ValueError("scope_refs must contain at least one ScopeRef")

    def to_json(self) -> JsonObject:
        return {
            "context_ref": self.context_ref,
            "kind": self.kind,
            "scope_refs": [scope.to_json() for scope in self.scope_refs],
            "facts": _json_ready(self.facts),
        }


@dataclass(frozen=True)
class MaterializationIntent:
    intent_ref: str
    intent_type: MaterializationIntentType
    source_judgment_refs: tuple[str, ...]
    scope_refs: tuple[ScopeRef, ...]
    field_ids: tuple[str, ...] = ()
    payload: JsonObject = field(default_factory=dict)
    classification_basis: tuple[str, ...] = ()
    resolved_spans: tuple[AcceptedResolvedSpan, ...] = ()
    field_bindings: tuple[MaterializationFieldBinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intent_ref",
            _clean_required(self.intent_ref, field_name="intent_ref"),
        )
        object.__setattr__(
            self,
            "source_judgment_refs",
            _clean_tuple(self.source_judgment_refs, field_name="source_judgment_refs"),
        )
        if not self.scope_refs:
            raise ValueError("scope_refs must contain at least one ScopeRef")
        if (
            self.intent_type
            in {
                MaterializationIntentType.MATERIALIZE_SLOT,
                MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE,
                MaterializationIntentType.REFRESH_GENERATED_CONTENT,
            }
            and not self.field_ids
        ):
            raise ValueError(f"{self.intent_type.value} requires field_ids")
        if (
            self.intent_type == MaterializationIntentType.MATERIALIZE_BODY_STRUCTURE
            and (
                not isinstance(self.payload.get("structure_ref"), str)
                or not isinstance(self.payload.get("members"), list)
            )
        ):
            raise ValueError(
                "materialize_body_structure requires payload.structure_ref and payload.members"
            )
        if self.resolved_spans:
            payload_spans = self.payload.get("resolved_spans")
            if payload_spans != [span.to_json() for span in self.resolved_spans]:
                raise ValueError("payload.resolved_spans must preserve accepted spans unchanged")
        if self.field_bindings:
            bound_field_ids = tuple(
                dict.fromkeys(binding.field_id for binding in self.field_bindings)
            )
            if bound_field_ids != self.field_ids:
                raise ValueError("field_ids must derive exactly from accepted part bindings")
            span_refs = {span.span_ref for span in self.resolved_spans}
            if any(binding.span_ref not in span_refs for binding in self.field_bindings):
                raise ValueError("field bindings must point to accepted resolved spans")

    def to_json(self) -> JsonObject:
        result: JsonObject = {
            "intent_ref": self.intent_ref,
            "intent_type": self.intent_type.value,
            "source_judgment_refs": list(self.source_judgment_refs),
            "scope_refs": [scope.to_json() for scope in self.scope_refs],
            "field_ids": list(self.field_ids),
            "payload": _json_ready(self.payload),
            "classification_basis": list(self.classification_basis),
        }
        if self.field_bindings:
            result["field_bindings"] = [
                binding.to_json() for binding in self.field_bindings
            ]
        return result


def _clean_required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _clean_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _clean_required_string(value, field_name)


def _clean_sha256(value: object, field_name: str) -> str:
    normalized = _clean_required_string(value, field_name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase sha256")
    return normalized


def _validate_extent(value: JsonObject, extent: object) -> None:
    raw_extent = value.get("extent")
    if isinstance(extent, WholeEntrySourceExtent):
        if raw_extent != {"kind": "whole_entry"}:
            raise ValueError("whole-entry span extent is inconsistent with span_ref")
        return
    assert isinstance(extent, TextSourceExtent)
    if raw_extent != {"kind": "text", "start": extent.start, "end": extent.end}:
        raise ValueError("text span extent is inconsistent with span_ref")
    if value.get("text_start") != extent.start or value.get("text_end") != extent.end:
        raise ValueError("text offsets are inconsistent with span_ref")


def _validated_fragment(
    value: object,
    *,
    source_snapshot_sha256: str,
    whole_entry: bool,
) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("word fragment must be an object")
    object_id = _clean_required_string(value.get("object_id"), "word_fragments[].object_id")
    _clean_required_string(value.get("locator"), "word_fragments[].locator")
    text = value.get("text")
    if not isinstance(text, str):
        raise ValueError("word_fragments[].text must be a string")
    fingerprint = _clean_sha256(value.get("fingerprint"), "word_fragments[].fingerprint")
    object_ref = value.get("object_ref")
    if not isinstance(object_ref, dict) or object_ref != {
        "document_sha256": source_snapshot_sha256,
        "expected_fingerprint": fingerprint,
        "object_id": object_id,
    }:
        raise ValueError("word fragment object_ref is not bound to the source snapshot")
    if whole_entry:
        if value.get("extent") != {"kind": "whole_entry"} or text != "":
            raise ValueError("whole-entry word fragment has an invalid extent")
    else:
        for key in (
            "source_text_start",
            "source_text_end",
            "object_text_start",
            "object_text_end",
        ):
            coordinate = value.get(key)
            if not isinstance(coordinate, int) or isinstance(coordinate, bool):
                raise ValueError(f"word fragment {key} must be an integer")
    return {str(key): _json_ready(item) for key, item in value.items()}


def _validate_fragment_coverage(
    *,
    value: JsonObject,
    fragments: tuple[JsonObject, ...],
    extent: object,
    text: str,
) -> None:
    fragment_object_ids = list(
        dict.fromkeys(str(fragment["object_id"]) for fragment in fragments)
    )
    if value.get("covered_object_ids") != fragment_object_ids:
        raise ValueError("covered_object_ids must derive exactly from word_fragments")
    if isinstance(extent, WholeEntrySourceExtent):
        if len(fragments) != 1:
            raise ValueError("whole-entry spans must resolve to one exact Word fragment")
        return
    assert isinstance(extent, TextSourceExtent)
    cursor = extent.start
    fragment_text: list[str] = []
    for fragment in fragments:
        start = fragment["source_text_start"]
        end = fragment["source_text_end"]
        if start != cursor or not isinstance(end, int) or end <= start:
            raise ValueError("word_fragments must cover the SourceSpan exactly and in order")
        fragment_value = fragment["text"]
        if not isinstance(fragment_value, str) or len(fragment_value) != end - start:
            raise ValueError("word fragment text does not match its source extent")
        fragment_text.append(fragment_value)
        cursor = end
    if cursor != extent.end or "".join(fragment_text) != text:
        raise ValueError("word_fragments do not preserve accepted source content")


@dataclass(frozen=True)
class UnsupportedMaterialization:
    unsupported_ref: str
    source_judgment_refs: tuple[str, ...]
    scope_refs: tuple[ScopeRef, ...]
    reason_code: str
    message: str
    missing_requirements: tuple[str, ...] = ()
    payload: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unsupported_ref",
            _clean_required(self.unsupported_ref, field_name="unsupported_ref"),
        )
        object.__setattr__(
            self,
            "source_judgment_refs",
            _clean_tuple(self.source_judgment_refs, field_name="source_judgment_refs"),
        )
        object.__setattr__(
            self,
            "reason_code",
            _clean_required(self.reason_code, field_name="reason_code"),
        )
        object.__setattr__(
            self,
            "message",
            _clean_required(self.message, field_name="message"),
        )

    def to_json(self) -> JsonObject:
        result: JsonObject = {
            "unsupported_ref": self.unsupported_ref,
            "source_judgment_refs": list(self.source_judgment_refs),
            "scope_refs": [scope.to_json() for scope in self.scope_refs],
            "reason_code": self.reason_code,
            "message": self.message,
            "missing_requirements": list(self.missing_requirements),
            "payload": _json_ready(self.payload),
        }
        return result


@dataclass(frozen=True)
class MutationCommand:
    command_ref: str
    command_type: MutationCommandType
    intent_refs: tuple[str, ...]
    scope_refs: tuple[ScopeRef, ...]
    field_ids: tuple[str, ...] = ()
    payload: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "command_ref",
            _clean_required(self.command_ref, field_name="command_ref"),
        )
        object.__setattr__(
            self,
            "intent_refs",
            _clean_tuple(self.intent_refs, field_name="intent_refs"),
        )
        if not self.scope_refs:
            raise ValueError("scope_refs must contain at least one ScopeRef")

    def to_json(self) -> JsonObject:
        return {
            "command_ref": self.command_ref,
            "command_type": self.command_type.value,
            "intent_refs": list(self.intent_refs),
            "scope_refs": [scope.to_json() for scope in self.scope_refs],
            "field_ids": list(self.field_ids),
            "payload": _json_ready(self.payload),
        }


@dataclass(frozen=True)
class MaterializationPlan:
    plan_ref: str
    intents: tuple[MaterializationIntent, ...]
    contexts: tuple[MaterializationContext, ...] = ()
    commands: tuple[MutationCommand, ...] = ()
    unsupported: tuple[UnsupportedMaterialization, ...] = ()
    source_review_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan_ref",
            _clean_required(self.plan_ref, field_name="plan_ref"),
        )

    @property
    def ready(self) -> bool:
        return not self.unsupported

    def to_json(self) -> JsonObject:
        result: JsonObject = {
            "schema_version": 1,
            "plan_ref": self.plan_ref,
            "ready": self.ready,
            "intent_count": len(self.intents),
            "context_count": len(self.contexts),
            "command_count": len(self.commands),
            "unsupported_count": len(self.unsupported),
            "intents": [intent.to_json() for intent in self.intents],
            "contexts": [context.to_json() for context in self.contexts],
            "commands": [command.to_json() for command in self.commands],
            "unsupported": [item.to_json() for item in self.unsupported],
        }
        if self.source_review_digest is not None:
            result["source_review_digest"] = self.source_review_digest
        return result


@dataclass(frozen=True)
class MaterializationCompileResult:
    plan: MaterializationPlan

    @property
    def intents(self) -> tuple[MaterializationIntent, ...]:
        return self.plan.intents

    @property
    def unsupported(self) -> tuple[UnsupportedMaterialization, ...]:
        return self.plan.unsupported

    @property
    def ready(self) -> bool:
        return self.plan.ready

    def to_json(self) -> JsonObject:
        return self.plan.to_json()


@dataclass(frozen=True)
class MaterializationContextResolution:
    contexts: tuple[MaterializationContext, ...]
    unsupported: tuple[UnsupportedMaterialization, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.unsupported

    def to_json(self) -> JsonObject:
        return {
            "schema_version": 1,
            "ready": self.ready,
            "context_count": len(self.contexts),
            "unsupported_count": len(self.unsupported),
            "contexts": [context.to_json() for context in self.contexts],
            "unsupported": [item.to_json() for item in self.unsupported],
        }


@dataclass(frozen=True)
class MaterializationReceipt:
    receipt_id: str
    status: MaterializationStatus
    plan: MaterializationPlan
    operations: tuple[JsonObject, ...] = ()
    cleanup: tuple[JsonObject, ...] = ()
    evidence: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipt_id",
            _clean_required(self.receipt_id, field_name="receipt_id"),
        )

    def to_json(self) -> JsonObject:
        return {
            "schema_version": 1,
            "receipt_id": self.receipt_id,
            "status": self.status,
            "plan": self.plan.to_json(),
            "operation_count": len(self.operations),
            "cleanup_count": len(self.cleanup),
            "operations": [_json_ready(item) for item in self.operations],
            "cleanup": [_json_ready(item) for item in self.cleanup],
            "evidence": _json_ready(self.evidence),
        }
