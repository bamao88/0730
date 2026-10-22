"""Typed post-unit materialization planning models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any, Literal

from docfit.tools.runtime import JsonObject


class MaterializationIntentType(StrEnum):
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
    REMOVE_HINT = "remove_hint"
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

    def to_json(self) -> JsonObject:
        return {
            "intent_ref": self.intent_ref,
            "intent_type": self.intent_type.value,
            "source_judgment_refs": list(self.source_judgment_refs),
            "scope_refs": [scope.to_json() for scope in self.scope_refs],
            "field_ids": list(self.field_ids),
            "payload": _json_ready(self.payload),
            "classification_basis": list(self.classification_basis),
        }


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
