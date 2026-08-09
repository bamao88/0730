"""Agent-visible schemas for object-driven template preparation."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_OBJECT_REF_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_id": {"type": "string", "pattern": "^obj-[0-9a-f]{24}$"},
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
        "queries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "items": {
                "type": "object",
                "properties": {
                    "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
                    "field_id": {"type": "string", "maxLength": 128},
                    "query": {"type": "string", "minLength": 1, "maxLength": 256},
                },
                "required": ["object_ref"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["queries"],
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

_SIMPLE_TARGET_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"object_ref": TEMPLATE_OBJECT_REF_SCHEMA},
    "required": ["object_ref"],
    "additionalProperties": False,
}

_FORMAT_TARGET_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "format": EFFECTIVE_FORMAT_SCHEMA,
    },
    "required": ["object_ref", "format"],
    "additionalProperties": False,
}

_MATERIALIZE_SLOT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "effective_format": EFFECTIVE_FORMAT_SCHEMA,
    },
    "required": ["object_ref", "field_id"],
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

_MATERIALIZE_STRUCTURE_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "members": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _STRUCTURE_MEMBER_SCHEMA,
        },
    },
    "required": ["object_ref", "members"],
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

_REFRESH_TOC_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "entries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _TOC_ENTRY_SCHEMA,
        },
        "effective_format": EFFECTIVE_FORMAT_SCHEMA,
    },
    "required": ["object_ref", "entries"],
    "additionalProperties": False,
}

_ENSURE_PAGE_START_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "mode": {"type": "string", "enum": ["new_page"]},
    },
    "required": ["object_ref", "mode"],
    "additionalProperties": False,
}

TEMPLATE_EDIT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "materialize_slots": {
            "type": "array",
            "maxItems": 32,
            "items": _MATERIALIZE_SLOT_SCHEMA,
        },
        "materialize_structures": {
            "type": "array",
            "maxItems": 4,
            "items": _MATERIALIZE_STRUCTURE_SCHEMA,
        },
        "normalize_effective_formats": {
            "type": "array",
            "maxItems": 32,
            "items": _FORMAT_TARGET_SCHEMA,
        },
        "refresh_tocs": {
            "type": "array",
            "maxItems": 1,
            "items": _REFRESH_TOC_SCHEMA,
        },
        "clear_contents": {
            "type": "array",
            "maxItems": 32,
            "items": _SIMPLE_TARGET_SCHEMA,
        },
        "remove_objects": {
            "type": "array",
            "maxItems": 32,
            "items": _SIMPLE_TARGET_SCHEMA,
        },
        "ensure_page_starts": {
            "type": "array",
            "maxItems": 32,
            "items": _ENSURE_PAGE_START_SCHEMA,
        },
    },
    "additionalProperties": False,
}

TEMPLATE_PUBLISH_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"document_ref": DOCUMENT_REF_SCHEMA},
    "required": ["document_ref"],
    "additionalProperties": False,
}
