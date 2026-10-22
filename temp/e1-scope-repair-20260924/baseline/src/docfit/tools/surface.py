"""DocFit MCP Tool surface contracts.

The prepare-template runtime product Agent uses the template semantic profile:
one read-only context tool and no manual check/apply tools. The broader three-tool
facade is kept for internal services, diagnostics, and tests that exercise
deterministic Tool behavior directly.
"""

from __future__ import annotations

from typing import Any, Final

JsonSchema = dict[str, Any]

TOOL_SURFACE_VERSION: Final = "docfit-tool-surface/v1"
DOCFIT_EVIDENCE_INPUT_V1: Final = "docfit_evidence_input_v1"
DOCFIT_CHECK_INPUT_V1: Final = "docfit_check_input_v1"
DOCFIT_APPLY_INPUT_V1: Final = "docfit_apply_input_v1"

DOCFIT_EVIDENCE_TOOL: Final = "docfit_evidence"
DOCFIT_CHECK_TOOL: Final = "docfit_check"
DOCFIT_APPLY_TOOL: Final = "docfit_apply"

DOCFIT_GENERAL_TOOL_NAMES: Final = (
    DOCFIT_EVIDENCE_TOOL,
    DOCFIT_CHECK_TOOL,
    DOCFIT_APPLY_TOOL,
)
DOCFIT_GENERAL_READ_ONLY_TOOL_NAMES: Final = (
    DOCFIT_EVIDENCE_TOOL,
    DOCFIT_CHECK_TOOL,
)
DOCFIT_GENERAL_WRITE_TOOL_NAMES: Final = (DOCFIT_APPLY_TOOL,)
DOCFIT_GENERAL_SUBAGENT_TOOL_NAMES: Final = (
    DOCFIT_EVIDENCE_TOOL,
    DOCFIT_CHECK_TOOL,
)
TEMPLATE_RUNTIME_AGENT_TOOL_NAMES: Final = (DOCFIT_EVIDENCE_TOOL,)
TEMPLATE_RUNTIME_FULL_AGENT_TOOL_NAMES: Final = tuple(
    f"mcp__docfit__{name}" for name in TEMPLATE_RUNTIME_AGENT_TOOL_NAMES
)
DOCFIT_GENERAL_FULL_TOOL_NAMES: Final = tuple(
    f"mcp__docfit__{name}" for name in DOCFIT_GENERAL_TOOL_NAMES
)
DOCFIT_GENERAL_READ_ONLY_FULL_TOOL_NAMES: Final = tuple(
    f"mcp__docfit__{name}" for name in DOCFIT_GENERAL_READ_ONLY_TOOL_NAMES
)
DOCFIT_GENERAL_WRITE_FULL_TOOL_NAMES: Final = tuple(
    f"mcp__docfit__{name}" for name in DOCFIT_GENERAL_WRITE_TOOL_NAMES
)
DOCFIT_GENERAL_SUBAGENT_FULL_TOOL_NAMES: Final = tuple(
    f"mcp__docfit__{name}" for name in DOCFIT_GENERAL_SUBAGENT_TOOL_NAMES
)

EVIDENCE_FOCUS: Final = (
    "document_map",
    "unit_evidence_packet",
    "object_detail",
    "visual_page",
    "visual_region",
    "render_snapshot",
    "style_evidence",
    "hash_binding",
)
TEMPLATE_SEMANTIC_EVIDENCE_FOCUS: Final = (
    "document_map",
    "unit_evidence_packet",
)
CHECK_KINDS: Final = (
    "schema_envelope",
    "hash_binding",
    "reference_freshness",
    "unit_coverage",
    "visual_coverage",
    "style_evidence",
    "candidate_validation",
    "completion_gate",
    "publication_readiness",
)
SUBAGENT_CHECK_KINDS: Final = (
    "schema_envelope",
    "hash_binding",
    "reference_freshness",
    "unit_coverage",
    "visual_coverage",
    "style_evidence",
)
TOOL_FAILURE_CODES: Final = (
    "stale_ref",
    "scope_violation",
    "target_ambiguity",
    "style_evidence_insufficient",
    "schema_envelope_invalid",
    "hash_binding_mismatch",
    "visual_coverage_incomplete",
    "unit_slice_runtime_removed",
    "unit_evidence_packet_unit_missing",
    "unit_evidence_packet_range_missing",
    "registry_field_runtime_removed",
    "phase_review_required",
    "write_operation_denied",
    "provider_failure",
)

_TASK_ROOT: JsonSchema = {
    "type": "string",
    "description": "Authorized task root; defaults to the current application task.",
}
_HASH: JsonSchema = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_REF: JsonSchema = {"type": "string", "minLength": 1}
_RENDER_REF: JsonSchema = {"type": "string", "pattern": "^render:v[0-9]+:[0-9a-f]{64}$"}

DOCFIT_EVIDENCE_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "schema_version": {"const": DOCFIT_EVIDENCE_INPUT_V1},
        "task_root": _TASK_ROOT,
        "candidate_hash": _HASH,
        "focus": {"type": "string", "enum": list(EVIDENCE_FOCUS)},
        "unit_id": _REF,
        "page": {"type": "integer", "minimum": 1},
        "object_ref": _REF,
        "render_ref": _RENDER_REF,
        "offset": {
            "type": "integer",
            "minimum": 0,
            "description": (
                "Object-window offset for paginated document_map evidence; "
                "use summary.object_window.next_offset from the previous evidence card."
            ),
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
    },
    "required": ["schema_version", "focus"],
    "additionalProperties": False,
}

DOCFIT_TEMPLATE_SEMANTIC_EVIDENCE_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "schema_version": {"const": DOCFIT_EVIDENCE_INPUT_V1},
        "focus": {
            "type": "string",
            "enum": list(TEMPLATE_SEMANTIC_EVIDENCE_FOCUS),
        },
        "unit_id": _REF,
        "offset": {
            "type": "integer",
            "minimum": 0,
            "description": (
                "Visible-text window offset for paginated document_map context; "
                "use summary.text_outline_window.next_offset from the previous context card."
            ),
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
    },
    "required": ["schema_version", "focus"],
    "additionalProperties": False,
}

DOCFIT_CHECK_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "schema_version": {"const": DOCFIT_CHECK_INPUT_V1},
        "task_root": _TASK_ROOT,
        "candidate_hash": _HASH,
        "check": {"type": "string", "enum": list(CHECK_KINDS)},
        "payload_ref": _REF,
        "payload": {
            "type": "object",
            "description": (
                "Inline check envelope object for phase-level mechanical feedback; "
                "do not pass a top-level array."
            ),
        },
        "object_ref": _REF,
        "render_ref": _RENDER_REF,
        "evidence_ref": _REF,
        "reviewed_pages": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "uniqueItems": True,
        },
        "strict": {"type": "boolean"},
    },
    "required": ["schema_version", "check"],
    "additionalProperties": False,
}

DOCFIT_APPLY_SCHEMA: JsonSchema = {
    "type": "object",
    "properties": {
        "schema_version": {"const": DOCFIT_APPLY_INPUT_V1},
        "task_root": _TASK_ROOT,
        "candidate_hash": _HASH,
        "batch_ref": _REF,
        "idempotency_key": _REF,
        "output_docx": {"type": "string", "minLength": 1},
    },
    "required": [
        "schema_version",
        "candidate_hash",
        "batch_ref",
        "output_docx",
    ],
    "additionalProperties": False,
}

DOCFIT_TOOL_SURFACE: Final = (
    {
        "name": DOCFIT_EVIDENCE_TOOL,
        "intent": "Collect bounded evidence for template semantic judgment.",
        "read_only": True,
        "subagent_allowed": True,
        "input_schema": DOCFIT_EVIDENCE_SCHEMA,
        "failure_codes": TOOL_FAILURE_CODES,
    },
    {
        "name": DOCFIT_CHECK_TOOL,
        "intent": "Check mechanical contracts without making school semantic judgments.",
        "read_only": True,
        "subagent_allowed": True,
        "input_schema": DOCFIT_CHECK_SCHEMA,
        "failure_codes": TOOL_FAILURE_CODES,
        "subagent_check_kinds": SUBAGENT_CHECK_KINDS,
    },
    {
        "name": DOCFIT_APPLY_TOOL,
        "intent": "Apply one Harness-reviewed template change package to a fresh candidate.",
        "read_only": False,
        "subagent_allowed": False,
        "input_schema": DOCFIT_APPLY_SCHEMA,
        "failure_codes": TOOL_FAILURE_CODES,
    },
)

DOCX_TOOL_ADAPTERS: Final = {
    DOCFIT_EVIDENCE_TOOL: ("docx_inspect", "docx_render", "docx_visual_review"),
    DOCFIT_CHECK_TOOL: ("docx_validate",),
    DOCFIT_APPLY_TOOL: ("docx_edit",),
}
