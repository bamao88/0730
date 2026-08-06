"""Public schema for template_compare."""

from __future__ import annotations

from docfit.tools.runtime import JsonObject

TEMPLATE_COMPARE_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1},
        "task_root": {"type": "string", "minLength": 1},
        "action": {"type": "string", "enum": ["create", "images"]},
        "review_mode": {
            "type": "string",
            "enum": ["mutation_review", "final_review"],
        },
        "before_snapshot_ref": {"type": "string"},
        "after_snapshot_ref": {"type": "string"},
        "mutation_ref": {"type": "string"},
        "final_snapshot_ref": {"type": "string"},
        "visual_level": {"type": "string", "enum": ["candidate_verification"]},
        "comparison_ref": {"type": "string"},
        "required_image_ids": {
            "type": "array",
            "maxItems": 4,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "cursor": {"type": ["string", "null"]},
        "max_images": {"type": "integer", "minimum": 1, "maximum": 4},
    },
    "required": ["schema_version", "task_root", "action"],
    "additionalProperties": False,
}
