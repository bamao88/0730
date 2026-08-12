"""Role-scoped Agent schemas for application-orchestrated template preparation."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_OBJECT_ID_SCHEMA: JsonObject = {
    "type": "string",
    "pattern": "^obj-[0-9a-f]{24}$",
}

EFFECTIVE_FORMAT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "enum": ["black"]},
        "underline": {"type": "string", "enum": ["none"]},
    },
    "additionalProperties": False,
}

_STRUCTURE_MEMBER_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
        "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "effective_format": EFFECTIVE_FORMAT_SCHEMA,
    },
    "required": ["object_id", "field_id"],
    "additionalProperties": False,
}

_TOC_ENTRY_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
        "level": {"type": "integer", "minimum": 1, "maximum": 3},
    },
    "required": ["object_id", "level"],
    "additionalProperties": False,
}

_DECISION_OPERATION_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "materialize_slot",
                "materialize_structure",
                "normalize_effective_format",
                "refresh_toc",
                "clear_content",
                "remove_object",
                "ensure_page_start",
            ],
        },
        "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
        "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "effective_format": EFFECTIVE_FORMAT_SCHEMA,
        "members": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _STRUCTURE_MEMBER_SCHEMA,
        },
        "entries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _TOC_ENTRY_SCHEMA,
        },
        "mode": {"type": "string", "enum": ["new_page"]},
    },
    "required": ["action", "object_id"],
    "additionalProperties": False,
}

TEMPLATE_GET_CURRENT_WORK_ITEM_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

TEMPLATE_REQUEST_CURRENT_CONTEXT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
        "visual_scope": {"type": "string", "enum": ["target", "context"]},
        "field_query": {"type": "string", "minLength": 1, "maxLength": 256},
        "text_query": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "additionalProperties": False,
}

TEMPLATE_SUBMIT_CURRENT_DECISION_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["apply", "preserve"]},
        "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
        "operations": {
            "type": "array",
            "maxItems": 32,
            "items": _DECISION_OPERATION_SCHEMA,
        },
    },
    "required": ["outcome", "reason"],
    "additionalProperties": False,
}

TEMPLATE_REPORT_AMBIGUITY_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
        "missing_evidence": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {"type": "string", "minLength": 1, "maxLength": 256},
        },
    },
    "required": ["reason", "missing_evidence"],
    "additionalProperties": False,
}

TEMPLATE_GET_REVIEW_BATCH_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
