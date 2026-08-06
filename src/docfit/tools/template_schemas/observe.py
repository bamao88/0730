"""Public schema for template_observe."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_OBSERVE_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1},
        "task_root": {"type": "string", "minLength": 1},
        "action": {"type": "string", "enum": ["create", "query", "images"]},
        "input_docx": {"type": "string", "minLength": 1},
        "visual_level": {
            "type": "string",
            "enum": ["none", "quick", "candidate_verification"],
        },
        "focus": {
            "type": "array",
            "maxItems": 4,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "enum": ["structure", "visible_objects", "styles", "slot_candidates"],
            },
        },
        "snapshot_ref": {"type": "string", "minLength": 1},
        "query": {"type": "object"},
        "render_ref": {"type": "string", "minLength": 1},
        "pages": {
            "type": "array",
            "maxItems": 16,
            "uniqueItems": True,
            "items": {"type": "integer", "minimum": 1},
        },
        "cursor": {"type": ["string", "null"]},
        "max_images": {"type": "integer", "minimum": 1, "maximum": 4},
    },
    "required": ["schema_version", "task_root", "action"],
    "additionalProperties": False,
}
