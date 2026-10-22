"""Shared Template Extraction Agent/Harness exchange contracts.

This module owns only mechanical envelope checks. It does not judge school
semantics, choose Registry fields, or decide whether a candidate is product-good.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Literal

SEMANTIC_JUDGMENT_V1 = "semantic_judgment_v1"
HOST_COMPLETION_RECEIPT_V1 = "host_completion_receipt_v1"
MECHANICAL_FEEDBACK_V1 = "mechanical_feedback_v1"

EXCHANGE_SCHEMA_VERSIONS = (SEMANTIC_JUDGMENT_V1,)
HOST_RECEIPT_SCHEMA_VERSIONS = (HOST_COMPLETION_RECEIPT_V1,)

HashField = Literal["source_hash", "candidate_hash"]
JsonObject = dict[str, Any]

ORDERED_SEMANTIC_PART_ROLES = (
    "fixed_label",
    "fill_slot",
    "body_structure",
    "generated_content",
    "manual_region",
    "style_only",
    "cleanup",
)

_FIELD_REQUIRED_PART_ROLES = frozenset(
    {
        "fill_slot",
        "body_structure",
        "generated_content",
    }
)
_FIELD_FORBIDDEN_PART_ROLES = frozenset(ORDERED_SEMANTIC_PART_ROLES) - (
    _FIELD_REQUIRED_PART_ROLES
)
_FILL_SLOT_LEADING_LABEL_DELIMITERS = (":", "：")
_FORBIDDEN_AGENT_JUDGMENT_KEYS = frozenset(
    {
        "semantic_field",
        "registry_field",
        "registry_field_id",
        "bound_field_id",
        "bound_field_ids",
        "required_field_ids",
        "generated_field_id",
        "field_id",
        "evidence",
        "judgment_id",
        "semantic_part_index",
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
        "semantic_parts",
        "source_content_id",
        "source_content_ids",
        "parent_content_id",
        "target_content_id",
        "source_object_id",
        "source_object_ids",
        "source_entry_ids",
        "source_entry_ref",
        "source_entry_refs",
        "covered_source_entry_ids",
        "source_entry_text_spans",
        "covered_object_ids",
        "object_ids",
        "object_text_spans",
        "covered_objects",
        "covered_object_refs",
        "object_refs",
        "source_object_refs",
        "target_refs",
        "object_id",
        "object_ref",
        "target",
        "covered_object_locators",
        "object_locators",
        "covered_locators",
        "source_object_locators",
        "target_locators",
        "object_locator",
        "locator",
        "covered_locator_ranges",
        "locator_ranges",
        "covered_object_ranges",
        "object_ranges",
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
    }
)
_FORBIDDEN_AGENT_PART_KEYS = frozenset(
    {
        "semantic_field",
        "registry_field",
        "registry_field_id",
        "bound_field_id",
        "bound_field_ids",
        "required_field_ids",
        "generated_field_id",
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
        "source_entry_id",
        "source_entry_ids",
        "source_entry_ref",
        "source_entry_refs",
        "covered_source_entry_ids",
        "source_entry_text_spans",
        "covered_object_ids",
        "object_ids",
        "object_text_spans",
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

def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def mechanical_feedback(
    *,
    feedback_type: str,
    code: str,
    message: str,
    status: Literal["needs_input", "error"] = "needs_input",
    origin: str = "request",
    retryable: bool = True,
    source_hash: str | None = None,
    candidate_hash: str | None = None,
    blockers: Sequence[JsonObject] = (),
    suggested_actions: Sequence[str] = (),
    hard_failure: bool = False,
    agent_action: str | None = None,
) -> JsonObject:
    """Return one normalized mechanical feedback envelope."""

    normalized_status: Literal["needs_input", "error"] = "error" if hard_failure else status
    normalized_origin = "invariant" if hard_failure and origin == "request" else origin
    feedback: JsonObject = {
        "type": feedback_type,
        "mechanical": True,
        "semantic_authority": False,
    }
    if source_hash is not None:
        feedback["source_hash"] = source_hash
    if candidate_hash is not None:
        feedback["candidate_hash"] = candidate_hash
    if agent_action is not None:
        feedback["agent_action"] = agent_action
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": normalized_status,
        "feedback": feedback,
        "blockers": list(blockers),
        "checks": [{"name": code, "result": normalized_status}],
        "warnings": [],
        "failure": {
            "origin": normalized_origin,
            "code": code,
            "retryable": False if hard_failure else retryable,
            "message": message,
            "suggested_actions": list(suggested_actions),
        },
    }


def _blocker(code: str, field: str, message: str) -> JsonObject:
    return {"code": code, "field": field, "message": message}


def validate_ordered_semantic_parts(
    judgments: Any,
    *,
    allowed_field_ids: Iterable[str],
    reading_block_ids: Iterable[str],
    reading_range_ids: Iterable[str],
    source_entry_ids: Iterable[str] = (),
) -> JsonObject:
    """Validate the Agent-facing post-unit shape once a field vocabulary exists."""

    allowed = set(allowed_field_ids)
    allowed_source_entries = set(source_entry_ids)
    block_ids = set(reading_block_ids)
    range_ids = set(reading_range_ids)
    blockers: list[JsonObject] = []
    if not isinstance(judgments, list):
        return mechanical_feedback(
            feedback_type="ordered_semantic_parts",
            code="ordered_semantic_parts_invalid",
            message="semantic_judgments must be an array.",
            blockers=[
                _blocker(
                    "ordered_semantic_parts_invalid",
                    "semantic_judgments",
                    "semantic_judgments must be an array.",
                )
            ],
            suggested_actions=("Return semantic_judgments as an array.",),
        )

    for judgment_index, judgment in enumerate(judgments):
        path = f"semantic_judgments[{judgment_index}]"
        if not isinstance(judgment, dict):
            blockers.append(
                {
                    "code": "ordered_semantic_judgment_invalid",
                    "field": path,
                    "message": "Each semantic judgment must be an object.",
                }
            )
            continue
        forbidden = sorted(_FORBIDDEN_AGENT_JUDGMENT_KEYS.intersection(judgment))
        if forbidden:
            blockers.append(
                {
                    "code": "agent_authored_legacy_or_internal_id",
                    "field": path,
                    "forbidden_fields": forbidden,
                    "message": (
                        "Post-unit Agent output must use source_entry_id plus ordered parts; "
                        "legacy field aliases, Agent-authored IDs, and internal refs are not "
                        "accepted."
                    ),
                }
            )
        source_entry_id = judgment.get("source_entry_id")
        normalized_source_entry_id = (
            source_entry_id.strip() if isinstance(source_entry_id, str) else ""
        )
        has_source_entry = bool(normalized_source_entry_id)
        scope = judgment.get("scope")
        has_scope = isinstance(scope, dict)
        if source_entry_id is not None and not has_source_entry:
            blockers.append(
                {
                    "code": "ordered_semantic_source_entry_invalid",
                    "field": f"{path}.source_entry_id",
                    "message": (
                        "source_entry_id must be a non-empty source entry from the "
                        "unit packet."
                    ),
                }
            )
        if has_source_entry and has_scope:
            blockers.append(
                {
                    "code": "ordered_semantic_source_ref_invalid",
                    "field": path,
                    "message": (
                        "Each semantic judgment must name either source_entry_id or legacy "
                        "scope, not both."
                    ),
                }
            )
        elif has_source_entry:
            if normalized_source_entry_id not in allowed_source_entries:
                blockers.append(
                    {
                        "code": "ordered_semantic_source_entry_unknown",
                        "field": f"{path}.source_entry_id",
                        "source_entry_id": normalized_source_entry_id,
                        "message": "source_entry_id is not in the current unit packet.",
                    }
                )
        elif not isinstance(scope, dict):
            blockers.append(
                {
                    "code": "ordered_semantic_scope_missing",
                    "field": f"{path}.scope",
                    "message": (
                        "Each semantic judgment must include source_entry_id from the "
                        "unit packet, or a legacy scope object with one reading_block_id "
                        "or reading_range_id."
                    ),
                }
            )
        else:
            scope_block = scope.get("reading_block_id")
            scope_range = scope.get("reading_range_id")
            scope_block_id = scope_block.strip() if isinstance(scope_block, str) else ""
            scope_range_id = scope_range.strip() if isinstance(scope_range, str) else ""
            has_block = bool(scope_block_id)
            has_range = bool(scope_range_id)
            if has_block == has_range:
                blockers.append(
                    {
                        "code": "ordered_semantic_scope_invalid",
                        "field": f"{path}.scope",
                        "message": (
                            "Scope must name exactly one reading_block_id or reading_range_id."
                        ),
                    }
                )
            elif has_block and scope_block_id not in block_ids:
                blockers.append(
                    {
                        "code": "ordered_semantic_scope_unknown",
                        "field": f"{path}.scope.reading_block_id",
                        "reading_ref": scope_block_id,
                        "message": "Scope reading_block_id is not in the current unit packet.",
                    }
                )
            elif has_range and scope_range_id not in range_ids:
                blockers.append(
                    {
                        "code": "ordered_semantic_scope_unknown",
                        "field": f"{path}.scope.reading_range_id",
                        "reading_ref": scope_range_id,
                        "message": "Scope reading_range_id is not in the current unit packet.",
                    }
                )

        parts = judgment.get("parts")
        if not isinstance(parts, list) or not parts:
            blockers.append(
                {
                    "code": "ordered_semantic_parts_missing",
                    "field": f"{path}.parts",
                    "message": (
                        "Each semantic judgment must include a non-empty ordered parts array."
                    ),
                }
            )
            continue
        for part_index, part in enumerate(parts):
            part_path = f"{path}.parts[{part_index}]"
            if not isinstance(part, dict):
                blockers.append(
                    {
                        "code": "ordered_semantic_part_invalid",
                        "field": part_path,
                        "message": "Each ordered semantic part must be an object.",
                    }
                )
                continue
            forbidden_part_fields = sorted(_FORBIDDEN_AGENT_PART_KEYS.intersection(part))
            if forbidden_part_fields:
                blockers.append(
                    {
                        "code": "agent_authored_legacy_or_internal_id",
                        "field": part_path,
                        "forbidden_fields": forbidden_part_fields,
                        "message": (
                            "Semantic parts may only carry visible text, role, and an "
                            "input-vocabulary field_id when the role requires it."
                        ),
                    }
                )
            role = part.get("role")
            if not isinstance(role, str) or role.strip() not in ORDERED_SEMANTIC_PART_ROLES:
                blockers.append(
                    {
                        "code": "ordered_semantic_part_role_invalid",
                        "field": f"{part_path}.role",
                        "allowed_roles": list(ORDERED_SEMANTIC_PART_ROLES),
                        "message": "Part role is not in the ordered semantic part vocabulary.",
                    }
                )
                role_text = ""
            else:
                role_text = role.strip()
            text = part.get("text")
            if not isinstance(text, str) or not text.strip():
                blockers.append(
                    {
                        "code": "ordered_semantic_part_text_missing",
                        "field": f"{part_path}.text",
                        "message": "Part text must be a non-empty visible text segment.",
                    }
                )
            elif role_text == "fill_slot" and text.startswith(
                _FILL_SLOT_LEADING_LABEL_DELIMITERS
            ):
                blockers.append(
                    {
                        "code": "fill_slot_includes_label_delimiter",
                        "field": f"{part_path}.text",
                        "message": (
                            "A fill_slot must begin at the student value or placeholder. "
                            "Move visible label delimiters such as ':' or '：' into a "
                            "fixed_label part."
                        ),
                    }
                )
            field_id = part.get("field_id")
            normalized_field_id = field_id.strip() if isinstance(field_id, str) else ""
            has_field_id = bool(normalized_field_id)
            if role_text in _FIELD_REQUIRED_PART_ROLES:
                if not has_field_id:
                    blockers.append(
                        {
                            "code": "ordered_semantic_part_field_missing",
                            "field": f"{part_path}.field_id",
                            "message": (
                                "This part role requires a field_id selected from the "
                                "pre-input field vocabulary."
                            ),
                        }
                    )
                elif normalized_field_id not in allowed:
                    blockers.append(
                        {
                            "code": "field_id_not_in_input_vocabulary",
                            "field": f"{part_path}.field_id",
                            "field_id": normalized_field_id,
                            "message": (
                                "This field_id was not present in the Agent input vocabulary "
                                "for the current unit packet."
                            ),
                        }
                    )
            elif role_text in _FIELD_FORBIDDEN_PART_ROLES and "field_id" in part:
                blockers.append(
                    {
                        "code": "ordered_semantic_part_field_forbidden",
                        "field": f"{part_path}.field_id",
                        "message": "This part role must not carry a field_id.",
                    }
                )

    if blockers:
        return mechanical_feedback(
            feedback_type="ordered_semantic_parts",
            code="ordered_semantic_parts_invalid",
            message=(
                "Post-unit semantic judgments must use source_entry_id plus ordered parts "
                "and select field IDs only from the pre-input field vocabulary."
            ),
            blockers=blockers,
            suggested_actions=(
                "Return semantic_judgments[].source_entry_id and semantic_judgments[].parts.",
                "Use only field_id values from field_id_vocabulary.allowed_field_ids.",
            ),
            agent_action=(
                "Revise post-unit output to source_entry_id + ordered parts; do not use "
                "Registry lookup, legacy field aliases, Agent-authored IDs, or internal "
                "span/object refs."
            ),
        )
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": "ok",
        "checks": [{"name": "ordered_semantic_parts", "result": "ok"}],
        "warnings": [],
        "failure": None,
    }


def validate_exchange_envelope(
    payload: Any,
    *,
    expected_schema_version: str,
    required_hash_fields: Iterable[HashField],
    feedback_type: str = "exchange_contract",
) -> JsonObject:
    """Validate the common schema/hash envelope for one exchange payload."""

    blockers: list[JsonObject] = []
    if not isinstance(payload, dict):
        return mechanical_feedback(
            feedback_type=feedback_type,
            code="payload_shape_invalid",
            message="Exchange payload must be a JSON object.",
            blockers=[_blocker("payload_shape_invalid", "$", "Payload must be an object.")],
        )

    schema_version = payload.get("schema_version")
    if schema_version != expected_schema_version:
        blockers.append(
            _blocker(
                "schema_version_invalid",
                "schema_version",
                f"Expected {expected_schema_version}.",
            )
        )

    for field in required_hash_fields:
        if not _is_sha256(payload.get(field)):
            blockers.append(
                _blocker(
                    f"{field}_invalid",
                    field,
                    f"{field} must be a lowercase SHA-256 hex digest.",
                )
            )

    if blockers:
        return mechanical_feedback(
            feedback_type=feedback_type,
            code="exchange_envelope_invalid",
            message="Exchange payload is missing a valid schema_version or required hash.",
            blockers=blockers,
            suggested_actions=("Return the payload with schema_version and hash fields.",),
        )
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": "ok",
        "checks": [{"name": "exchange_envelope", "result": "ok"}],
        "warnings": [],
        "failure": None,
    }


def validate_semantic_judgment_v1(payload: Any) -> JsonObject:
    return validate_exchange_envelope(
        payload,
        expected_schema_version=SEMANTIC_JUDGMENT_V1,
        required_hash_fields=("source_hash",),
        feedback_type="semantic_judgment",
    )


def _validate_host_receipt_envelope(payload: Any) -> JsonObject:
    blockers: list[JsonObject] = []
    if not isinstance(payload, dict):
        return mechanical_feedback(
            feedback_type="host_completion_receipt",
            code="payload_shape_invalid",
            message="Host completion receipt must be a JSON object.",
            blockers=[_blocker("payload_shape_invalid", "$", "Payload must be an object.")],
        )
    schema_version = payload.get("schema_version")
    if schema_version not in HOST_RECEIPT_SCHEMA_VERSIONS:
        blockers.append(
            _blocker(
                "schema_version_invalid",
                "schema_version",
                f"Expected one of {HOST_RECEIPT_SCHEMA_VERSIONS}.",
            )
        )
    for field in ("source_hash", "candidate_hash"):
        if not _is_sha256(payload.get(field)):
            blockers.append(
                _blocker(
                    f"{field}_invalid",
                    field,
                    f"{field} must be a lowercase SHA-256 hex digest.",
                )
            )

    if blockers:
        return mechanical_feedback(
            feedback_type="host_completion_receipt",
            code="host_receipt_envelope_invalid",
            message=(
                "Host completion receipt is missing a valid schema_version or required "
                "hash."
            ),
            blockers=blockers,
            suggested_actions=("Rebuild the host-owned completion receipt.",),
        )
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": "ok",
        "checks": [{"name": "host_receipt_envelope", "result": "ok"}],
        "warnings": [],
        "failure": None,
    }


def validate_host_completion_receipt_v1(payload: Any) -> JsonObject:
    """Validate a host/App-owned completion receipt, not runtime Agent output."""

    envelope = _validate_host_receipt_envelope(payload)
    if envelope["status"] != "ok":
        return envelope
    assert isinstance(payload, dict)
    blockers: list[JsonObject] = []
    if payload.get("status") != "complete":
        blockers.append(
            _blocker("completion_status_invalid", "status", "Receipt status must be complete.")
        )
    for field in ("final_docx", "render_ref", "validation"):
        if field not in payload:
            blockers.append(
                _blocker(
                    f"{field}_missing",
                    field,
                    f"Host completion receipt must include {field}.",
                )
            )
    reviewed_pages = payload.get("reviewed_pages")
    if not isinstance(reviewed_pages, list) or not reviewed_pages:
        blockers.append(
            _blocker(
                "reviewed_pages_missing",
                "reviewed_pages",
                "Host completion receipt must include at least one reviewed page.",
            )
        )
    validation = payload.get("validation")
    if isinstance(validation, dict) and validation.get("status") != "ok":
        blockers.append(
            _blocker(
                "validation_not_ok",
                "validation.status",
                "Completion validation must have status ok.",
            )
        )
    if blockers:
        return mechanical_feedback(
            feedback_type="host_completion_receipt",
            code="host_completion_receipt_incomplete",
            message="Host completion receipt is not mechanically closed.",
            source_hash=payload["source_hash"],
            candidate_hash=payload["candidate_hash"],
            blockers=blockers,
            suggested_actions=("Refresh final evidence and rebuild the host receipt.",),
        )
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": "ok",
        "checks": [{"name": "host_completion_receipt", "result": "ok"}],
        "warnings": [],
        "failure": None,
    }


def validate_hash_binding(
    payload: Any,
    *,
    expected_source_hash: str | None = None,
    expected_candidate_hash: str | None = None,
) -> JsonObject:
    """Check whether a payload still belongs to the current source/candidate hashes."""

    if not isinstance(payload, dict):
        return mechanical_feedback(
            feedback_type="hash_binding",
            code="payload_shape_invalid",
            message="Exchange payload must be a JSON object before hash binding can be checked.",
            blockers=[_blocker("payload_shape_invalid", "$", "Payload must be an object.")],
        )
    blockers: list[JsonObject] = []
    if expected_source_hash is not None and payload.get("source_hash") != expected_source_hash:
        blockers.append(
            _blocker("stale_source_ref", "source_hash", "Payload source_hash is stale.")
        )
    if (
        expected_candidate_hash is not None
        and payload.get("candidate_hash") != expected_candidate_hash
    ):
        blockers.append(
            _blocker("stale_candidate_ref", "candidate_hash", "Payload candidate_hash is stale.")
        )
    if blockers:
        return mechanical_feedback(
            feedback_type="hash_binding",
            code="stale_ref",
            message="Payload hash binding does not match the current snapshot.",
            source_hash=payload.get("source_hash")
            if isinstance(payload.get("source_hash"), str)
            else None,
            candidate_hash=payload.get("candidate_hash")
            if isinstance(payload.get("candidate_hash"), str)
            else None,
            blockers=blockers,
            suggested_actions=("Refresh evidence against the current source or candidate hash.",),
        )
    return {
        "schema_version": MECHANICAL_FEEDBACK_V1,
        "status": "ok",
        "checks": [{"name": "hash_binding", "result": "ok"}],
        "warnings": [],
        "failure": None,
    }
