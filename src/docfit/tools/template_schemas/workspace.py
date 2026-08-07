"""Agent-visible schemas for object-driven template preparation."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject
from docfit.tools.schemas import OBJECT_REF_SCHEMA

DOCUMENT_REF_SCHEMA: JsonObject = {
    "type": "string",
    "pattern": "^document:v1:[0-9a-f]{64}$",
}

TEMPLATE_VIEW_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["open", "page", "search", "focus"],
        },
        "document_ref": DOCUMENT_REF_SCHEMA,
        "object_ref": OBJECT_REF_SCHEMA,
        "query": {"type": "string", "minLength": 1, "maxLength": 256},
        "page": {"type": "integer", "minimum": 1},
        "quality": {"type": "string", "enum": ["thumbnail", "review", "detail"]},
        "padding": {"type": "integer", "minimum": 0, "maximum": 256},
    },
    "required": ["action"],
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
                    "object_ref": OBJECT_REF_SCHEMA,
                    "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
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

TEMPLATE_EDIT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "materialize_slot",
                            "clear_content",
                            "remove_object",
                        ],
                    },
                    "object_ref": OBJECT_REF_SCHEMA,
                    "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "required": ["action", "object_ref"],
                "additionalProperties": False,
            },
        },
        "review_page": {"type": "integer", "minimum": 1},
    },
    "required": ["operations", "review_page"],
    "additionalProperties": False,
}

TEMPLATE_PUBLISH_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"document_ref": DOCUMENT_REF_SCHEMA},
    "required": ["document_ref"],
    "additionalProperties": False,
}
