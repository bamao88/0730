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

TEMPLATE_VIEW_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["open", "next", "search", "focus"],
        },
        "document_ref": DOCUMENT_REF_SCHEMA,
        "region_ref": REGION_REF_SCHEMA,
        "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
        "query": {"type": "string", "minLength": 1, "maxLength": 256},
        "quality": {"type": "string", "enum": ["thumbnail", "review", "detail"]},
        "padding": {"type": "integer", "minimum": 0, "maximum": 256},
        "region_outcome": {
            "type": "string",
            "enum": ["handled", "preserve"],
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 256},
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
                            "materialize_structure",
                            "normalize_format",
                            "refresh_toc",
                            "clear_content",
                            "remove_object",
                        ],
                    },
                    "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
                    "field_id": {"type": "string", "minLength": 1, "maxLength": 128},
                    "clear_direct_format": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["color"]},
                        "uniqueItems": True,
                        "maxItems": 1,
                    },
                    "members": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 32,
                        "items": {
                            "type": "object",
                            "properties": {
                                "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
                                "field_id": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 128,
                                },
                                "clear_direct_format": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": ["color"]},
                                    "uniqueItems": True,
                                    "maxItems": 1,
                                },
                            },
                            "required": ["object_ref", "field_id"],
                            "additionalProperties": False,
                        },
                    },
                    "entries": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 64,
                        "items": {
                            "type": "object",
                            "properties": {
                                "object_ref": TEMPLATE_OBJECT_REF_SCHEMA,
                                "level": {"type": "integer", "minimum": 1, "maximum": 3},
                            },
                            "required": ["object_ref", "level"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["action", "object_ref"],
                "additionalProperties": False,
            },
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
