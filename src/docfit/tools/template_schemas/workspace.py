"""Agent-visible schemas for object-driven template preparation."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_OBJECT_ID_SCHEMA: JsonObject = {
    "type": "string",
    "pattern": "^obj-[0-9a-f]{24}$",
}

TEMPLATE_OBJECT_REF_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
    },
    "required": ["object_id"],
    "additionalProperties": False,
}

DOCUMENT_REF_SCHEMA: JsonObject = {
    "type": "string",
    "pattern": "^document:v1:[0-9a-f]{64}$",
}

REGION_REF_SCHEMA: JsonObject = {
    "type": "string",
    "pattern": "^region:v1:[0-9a-f]{64}:[0-9]+:obj-[0-9a-f]{24}$",
}

TEMPLATE_OPEN_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

TEMPLATE_NEXT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "region_ref": REGION_REF_SCHEMA,
        "outcome": {"type": "string", "enum": ["handled", "preserve"]},
        "reason": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": ["region_ref", "outcome"],
    "additionalProperties": False,
}

TEMPLATE_SEARCH_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": ["query"],
    "additionalProperties": False,
}

TEMPLATE_FOCUS_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "scope": {"type": "string", "enum": ["target", "context"]},
    },
    "required": ["object_ref"],
    "additionalProperties": False,
}

TEMPLATE_REGISTRY_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "lookups": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
                    "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "required": ["object_id", "field_id"],
                "additionalProperties": False,
            },
        },
        "searches": {
            "type": "array",
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "object_id": TEMPLATE_OBJECT_ID_SCHEMA,
                    "query": {"type": "string", "minLength": 1, "maxLength": 256},
                },
                "required": ["object_id", "query"],
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
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
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "effective_format": EFFECTIVE_FORMAT_SCHEMA,
    },
    "required": ["object_ref", "field_id"],
    "additionalProperties": False,
}

_TOC_ENTRY_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "level": {"type": "integer", "minimum": 1, "maximum": 3},
    },
    "required": ["object_ref", "level"],
    "additionalProperties": False,
}

_EDIT_OPERATION_SCHEMA: JsonObject = {
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
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
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
    "required": ["action", "object_ref"],
    "additionalProperties": False,
}

TEMPLATE_EDIT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _EDIT_OPERATION_SCHEMA,
        },
    },
    "required": ["operations"],
    "additionalProperties": False,
}

TEMPLATE_PUBLISH_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"document_ref": DOCUMENT_REF_SCHEMA},
    "required": ["document_ref"],
    "additionalProperties": False,
}
